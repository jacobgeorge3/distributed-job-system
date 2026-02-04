# API Service Usage

The API service is the HTTP entry point for the distributed job system. It runs on **port 5001** when using Docker Compose (mapped from 5000 in the container).

**Base URL:** `http://localhost:5001`

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (200 if Redis is reachable, 503 otherwise) |
| POST | `/submit` | Submit a new job |
| GET | `/jobs/<job_id>` | Get job status and details |

---

## Health Check

Checks if the API can reach Redis. Returns an empty body with status 200 on success, or 503 on failure.

### cURL

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5001/health
# 200 = healthy, 503 = Redis unreachable

# Or simply:
curl http://localhost:5001/health
```

### wget

```bash
wget -q -O - http://localhost:5001/health
# Check exit code: 0 = 2xx, 1 = 4xx/5xx (e.g. 503)
```

### HTTPie

```bash
http GET http://localhost:5001/health
```

---

## Submit a Job

Submit a job by sending a JSON body with a `task` field. The API returns a job `id` you can use to poll status.

**Request:** `POST /submit`  
**Body:** `{"task": "<string>"}`  
**Success (200):** `{"status": "queued", "task": "...", "id": "<uuid>"}`  
**Error (400):** `{"error": "Missing 'task' field"}`

### cURL

```bash
# Basic submission
curl -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "process-data"}'

# Example response:
# {"id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","status":"queued","task":"process-data"}

# Save the job ID for later (using jq)
JOB_ID=$(curl -s -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "my-task"}' | jq -r '.id')
echo "Job ID: $JOB_ID"
```

### wget

```bash
wget -q -O - --post-data='{"task": "process-data"}' \
  --header='Content-Type: application/json' \
  http://localhost:5001/submit
```

### HTTPie

```bash
http POST http://localhost:5001/submit task=process-data

# Or with explicit JSON:
http POST http://localhost:5001/submit 'task=process-data'
```

---

## Get Job Status

Fetch the current status and details of a job by ID.

**Request:** `GET /jobs/<job_id>`  
**Success (200):** JSON with `id`, `status`, `task`, `created_at`, and optionally `result`, `completed_at`, `error`, `failed_at`  
**Error (404):** `{"error": "Job not found"}`

**Status values:** `queued` → `processing` → `completed` or `failed`

### cURL

```bash
# Replace <JOB_ID> with the UUID from /submit
curl http://localhost:5001/jobs/<JOB_ID>

# Example with a variable:
curl http://localhost:5001/jobs/$JOB_ID

# Pretty-print with jq
curl -s http://localhost:5001/jobs/$JOB_ID | jq
```

### wget

```bash
wget -q -O - http://localhost:5001/jobs/<JOB_ID>
```

### HTTPie

```bash
http GET http://localhost:5001/jobs/<JOB_ID>
```

---

## Complete Workflow Examples

### cURL: Submit and Poll Until Completed

```bash
# 1. Submit
RESP=$(curl -s -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "hello-world"}')
JOB_ID=$(echo "$RESP" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
echo "Submitted job: $JOB_ID"

# 2. Poll status
while true; do
  STATUS=$(curl -s "http://localhost:5001/jobs/$JOB_ID" | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 1
done

# 3. Get final result
curl -s "http://localhost:5001/jobs/$JOB_ID" | jq
```

### One-liner: Submit and Fetch Status

```bash
# Submit, extract ID, wait 2 seconds, then get status
JOB_ID=$(curl -s -X POST http://localhost:5001/submit -H "Content-Type: application/json" -d '{"task":"test"}' | jq -r '.id') && sleep 2 && curl -s "http://localhost:5001/jobs/$JOB_ID"
```

---

## Running the API

With Docker Compose (from the project root):

```bash
docker compose up -d
# API: http://localhost:5001
```

Run only the API and Redis:

```bash
docker compose up -d redis api
```

Run the API locally (requires Redis on `localhost:6379` or `REDIS_HOST`/`REDIS_PORT` set):

```bash
cd api-service
pip install -r requirements.txt
python main.py
# API: http://localhost:5000 (or 5001 if you map it)
```

---

## Response Field Reference

### POST /submit (200)

| Field   | Type   | Description                    |
|---------|--------|--------------------------------|
| `id`    | string | UUID of the created job        |
| `status`| string | `"queued"`                     |
| `task`  | string | The task string you submitted  |

### GET /jobs/<id> (200)

| Field         | Type   | Description                              |
|---------------|--------|------------------------------------------|
| `id`          | string | Job UUID                                 |
| `status`      | string | `queued`, `processing`, `completed`, or `failed` |
| `task`        | string | The task payload                         |
| `created_at`  | string | ISO 8601 timestamp (UTC)                 |
| `result`      | string | *(if completed)* Worker output           |
| `completed_at`| string | *(if completed)* ISO 8601 timestamp      |
| `error`       | string | *(if failed)* Error message              |
| `failed_at`   | string | *(if failed)* ISO 8601 timestamp         |

---

## Special Task: Simulate Failure

For testing retries and failure handling, submit a job with `task: "fail"`. The worker will raise an exception: it retries up to 3 times (4 attempts total), then marks the job as `failed` and moves it to the dead-letter queue.

```bash
curl -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "fail"}'
```
