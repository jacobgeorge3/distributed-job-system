import redis
import json
import time
import os
import socket
from datetime import datetime, timezone
import logging
from pythonjsonlogger.json import JsonFormatter

# Connect to Redis (decode_responses=True so BLPOP yields strings)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# Max total attempts before DLQ: 4 attempts = 1 initial + 3 retries ("retried up to 3x")
MAX_ATTEMPTS = 4

# Structured logging: JSON to stdout for containers and log collectors
WORKER_ID = f"worker-{socket.gethostname()}-{os.getpid()}"
log = logging.getLogger("worker")
log.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = JsonFormatter("%(message)s %(asctime)s %(levelname)s")
handler.setFormatter(formatter)
log.addHandler(handler)


def job_extra(job_id: str, task: str, status: str, **kwargs) -> dict:
    """Build extra dict for structured log fields."""
    return {"job_id": job_id, "task": task, "status": status, "worker_id": WORKER_ID, **kwargs}


log.info("Worker starting, connecting to Redis", extra={"worker_id": WORKER_ID, "status": "startup"})

while True:
    _, job_json = r.blpop("job_queue")
    job = json.loads(job_json)
    job_id = job.get("id")
    if not job_id:
        log.warning("Job missing 'id', skipping", extra={"worker_id": WORKER_ID})
        continue

    task = job.get("task", "")
    attempts = job.get("attempts", 0)
    created_at = job.get("created_at", "")

    r.hset(f"job:{job_id}", "status", "processing")
    log.info("Job claimed", extra=job_extra(job_id, task, "processing"))

    try:
        if task == "fail":
            raise RuntimeError("Simulated failure for testing")

        time.sleep(2)
        result = "completed"
        r.hset(
            f"job:{job_id}",
            mapping={
                "status": "completed",
                "result": result,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        r.incr("metrics:jobs_completed")
        log.info("Job completed", extra=job_extra(job_id, task, "completed"))

    except Exception as e:
        attempts = attempts + 1
        # Retry when under max: 4 total attempts = 3 retries. DLQ only when attempts >= MAX_ATTEMPTS.
        if attempts < MAX_ATTEMPTS:
            r.hset(f"job:{job_id}", "status", "queued")
            r.rpush(
                "job_queue",
                json.dumps({"id": job_id, "task": task, "attempts": attempts, "created_at": created_at}),
            )
            log.warning(
                "Job retrying",
                extra=job_extra(job_id, task, "queued", attempts=attempts, max_attempts=MAX_ATTEMPTS, error=str(e)),
            )
        else:
            r.hset(
                f"job:{job_id}",
                mapping={
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            r.rpush(
                "dead_letter",
                json.dumps({"id": job_id, "task": task, "attempts": attempts, "created_at": created_at}),
            )
            r.incr("metrics:jobs_failed")
            log.error(
                "Job failed, moved to DLQ",
                extra=job_extra(job_id, task, "failed", attempts=attempts, error=str(e)),
            )
