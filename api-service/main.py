from flask import Flask, request, jsonify
import redis
import json
import os
import uuid
from datetime import datetime, timezone

app = Flask(__name__)

# Connect to Redis (decode_responses=True for string values in hashes/lists)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# TTL for job status hashes (7 days)
JOB_TTL_SECONDS = 604800

# Redis key for the job queue (LLEN = queue depth)
JOB_QUEUE_KEY = "job_queue"
METRICS_KEYS = ("metrics:jobs_submitted", "metrics:jobs_completed", "metrics:jobs_failed")


@app.route("/health", methods=["GET"])
def health():
    """Return 200 if Redis is reachable, 503 otherwise."""
    try:
        r.ping()
        return "", 200
    except (redis.ConnectionError, redis.TimeoutError):
        return "", 503


@app.route("/submit", methods=["POST"])
def submit_job():
    data = request.json
    if not data or "task" not in data:
        return jsonify({"error": "Missing 'task' field"}), 400

    job_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {"id": job_id, "task": data["task"], "attempts": 0, "created_at": created_at}

    r.hset(f"job:{job_id}", mapping={"status": "queued", "task": data["task"], "created_at": created_at})
    r.expire(f"job:{job_id}", JOB_TTL_SECONDS)

    r.rpush(JOB_QUEUE_KEY, json.dumps(payload))
    r.incr("metrics:jobs_submitted")
    return jsonify({"status": "queued", "task": data["task"], "id": job_id})


@app.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Return job status from Redis. 404 if not found."""
    key = f"job:{job_id}"
    if not r.exists(key):
        return jsonify({"error": "Job not found"}), 404

    d = r.hgetall(key)
    resp = {"id": job_id, "status": d["status"], "task": d["task"], "created_at": d.get("created_at")}
    if d.get("result") is not None:
        resp["result"] = d["result"]
    if d.get("completed_at") is not None:
        resp["completed_at"] = d["completed_at"]
    if d.get("error") is not None:
        resp["error"] = d["error"]
    if d.get("failed_at") is not None:
        resp["failed_at"] = d["failed_at"]
    return jsonify(resp)


@app.route("/metrics", methods=["GET"])
def metrics():
    """Return job counters and queue depth (LLEN job_queue). Counters are updated by API (submitted) and workers (completed, failed)."""
    try:
        counts = {}
        for key in METRICS_KEYS:
            val = r.get(key)
            counts[key.replace("metrics:", "")] = int(val) if val is not None else 0
        queue_depth = r.llen(JOB_QUEUE_KEY)
        return jsonify({
            "jobs_submitted": counts["jobs_submitted"],
            "jobs_completed": counts["jobs_completed"],
            "jobs_failed": counts["jobs_failed"],
            "queue_depth": queue_depth,
        })
    except (redis.ConnectionError, redis.TimeoutError):
        return jsonify({"error": "Redis unreachable"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
