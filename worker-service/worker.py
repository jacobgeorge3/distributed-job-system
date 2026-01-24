import redis
import json
import time
import os

# Connect to Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

print("Worker started, polling for jobs...")

while True:
    _, job_json = r.blpop("job_queue")  # Blocking pop
    job = json.loads(job_json)
    task = job.get("task")
    print(f"Processing job: {task}")
    # Simulate work
    time.sleep(2)
    print(f"Finished job: {task}")
