from flask import Flask, request, jsonify
import redis
import json
import os

app = Flask(__name__)

# Connect to Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

@app.route("/submit", methods=["POST"])
def submit_job():
    data = request.json
    if not data or "task" not in data:
        return jsonify({"error": "Missing 'task' field"}), 400

    # Push job into Redis list
    r.rpush("job_queue", json.dumps(data))
    return jsonify({"status": "queued", "task": data["task"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
