import redis
import json
import time
import os
from datetime import datetime, timezone

# Connect to Redis (decode_responses=True so BLPOP yields strings)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

MAX_ATTEMPTS = 3

print(f"Worker starting, connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")

while True:
    _, job_json = r.blpop("job_queue")
    job = json.loads(job_json)
    job_id = job.get("id")
    if not job_id:
        print("Job missing 'id', skipping")
        continue

    task = job.get("task", "")
    attempts = job.get("attempts", 0)
    created_at = job.get("created_at", "")

    r.hset(f"job:{job_id}", "status", "processing")

    try:
        # Simulated failure for testing: task "fail" raises so we can exercise retry and DLQ
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
        print(f"Finished job: {job_id} ({task})")

    except Exception as e:
        attempts = attempts + 1
        if attempts < MAX_ATTEMPTS:
            r.hset(f"job:{job_id}", "status", "queued")
            r.rpush(
                "job_queue",
                json.dumps({"id": job_id, "task": task, "attempts": attempts, "created_at": created_at}),
            )
            print(f"Retrying job {job_id} ({task}) attempt {attempts}/{MAX_ATTEMPTS}")
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
            print(f"Job {job_id} failed after {MAX_ATTEMPTS} attempts, moved to DLQ: {e}")
