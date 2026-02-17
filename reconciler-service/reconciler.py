import redis
import json
import time
import os
from datetime import datetime, timezone
import logging
from pythonjsonlogger.json import JsonFormatter

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
STALE_THRESHOLD_SECONDS = int(os.getenv("STALE_THRESHOLD_SECONDS", 300))  # 5 min
RECONCILER_INTERVAL = int(os.getenv("RECONCILER_INTERVAL", 60))  # 1 min
MAX_ATTEMPTS = 4

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

log = logging.getLogger("reconciler")
log.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = JsonFormatter("%(message)s %(asctime)s %(levelname)s")
handler.setFormatter(formatter)
log.addHandler(handler)

log.info("Reconciler starting", extra={"interval": RECONCILER_INTERVAL, "threshold": STALE_THRESHOLD_SECONDS})

def reconcile_jobs():
    """Check processing_jobs ZSET for stale entries."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff_ts = now_ts - STALE_THRESHOLD_SECONDS # Jobs older than this are stale

    # 1. atomic fetch of stale jobs (score < cutoff)
    # ZRANGEBYSCORE processing_jobs -inf <cutoff>
    stale_job_ids = r.zrangebyscore("processing_jobs", "-inf", cutoff_ts)

    if not stale_job_ids:
        return

    log.info(f"Found {len(stale_job_ids)} potential stale jobs")

    for job_id in stale_job_ids:
        try:
            reconcile_job(job_id)
        except Exception as e:
            log.error(f"Error reconciling job {job_id}", extra={"error": str(e)})

def reconcile_job(job_id: str):
    """Requeue or DLQ a single stale job."""
    
    # 2. Key check - is it still processing?
    job_data = r.hgetall(f"job:{job_id}")
    
    if not job_data:
        # Job key expired or deleted?
        log.warning("Stale job in ZSET but no job hash found", extra={"job_id": job_id})
        r.zrem("processing_jobs", job_id)
        return

    status = job_data.get("status")
    if status != "processing":
        # Race condition: worker updated status but maybe failed ZREM?
        log.info("Job no longer processing, removing from ZSET", extra={"job_id": job_id, "status": status})
        r.zrem("processing_jobs", job_id)
        return

    # 3. It is genuinely stale.
    attempts = int(job_data.get("attempts", 0))
    payload_str = job_data.get("payload")
    
    # If payload is missing, we can't requeue properly.
    if not payload_str:
        log.error("Job payload missing, cannot requeue", extra={"job_id": job_id})
        fail_job_missing_payload(job_id, "Reconciler: Payload missing", attempts)
        return

    payload = json.loads(payload_str)
    task = payload.get("task", "unknown")
    
    attempts += 1
    
    extra_log = {
        "job_id": job_id, 
        "task": task, 
        "attempts": attempts, 
        "worker_id": job_data.get("worker_id"),
        "stale_seconds": STALE_THRESHOLD_SECONDS
    }

    if attempts < MAX_ATTEMPTS:
        # REQUEUE
        payload["attempts"] = attempts
        
        pipeline = r.pipeline()
        pipeline.hset(f"job:{job_id}", mapping={"status": "queued", "attempts": str(attempts)})
        pipeline.rpush("job_queue", json.dumps(payload))
        pipeline.zrem("processing_jobs", job_id) # Remove from processing set
        pipeline.execute()
        
        log.warning("Stale job requeued", extra=extra_log)
    else:
        # DLQ
        fail_job_dlq(job_id, payload, attempts, f"Reconciler: Stale after {STALE_THRESHOLD_SECONDS}s")


def fail_job_missing_payload(job_id, error_msg, attempts):
    """Fail a job that has no payload to push to DLQ."""
    r.hset(
        f"job:{job_id}",
        mapping={
            "status": "failed",
            "error": error_msg,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    r.zrem("processing_jobs", job_id)
    r.incr("metrics:jobs_failed")
    log.error("Stale job failed (no payload)", extra={"job_id": job_id, "error": error_msg})


def fail_job_dlq(job_id, payload, attempts, error_msg):
    """Move job to failed state and DLQ."""
    payload["attempts"] = attempts
    
    pipeline = r.pipeline()
    pipeline.hset(
        f"job:{job_id}",
        mapping={
            "status": "failed",
            "error": error_msg,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    pipeline.rpush("dead_letter", json.dumps(payload))
    pipeline.zrem("processing_jobs", job_id)
    pipeline.incr("metrics:jobs_failed")
    pipeline.execute()
    
    log.error("Stale job moved to DLQ", extra={"job_id": job_id, "error": error_msg})


while True:
    try:
        reconcile_jobs()
    except Exception as e:
        log.error("Reconciler loop error", extra={"error": str(e)})
    
    time.sleep(RECONCILER_INTERVAL)
