# Feature List (Current) and Suggested Roadmap

## 1. Current Feature List

### API

- **`POST /submit`:** Accepts JSON body with `task` (required). Validates presence of `task`; returns `400` with `{"error": "Missing 'task' field"}` when invalid.
- **Queue write:** Serializes payload to JSON and `RPUSH`es to Redis list `job_queue`.
- **Response:** `{"status": "queued", "task": "<value>"}` on success.
- **Stack:** Flask, Redis client. Config via `REDIS_HOST`, `REDIS_PORT` (env).

### Worker

- **Queue read:** `BLPOP job_queue` for blocking, FIFO consumption. One job per `BLPOP`.
- **Processing:** Parses JSON, reads `task`, runs placeholder work (`time.sleep(2)`), logs "Processing" and "Finished" to stdout.
- **Stack:** Redis client only. Same `REDIS_HOST`, `REDIS_PORT` as API.

### Infrastructure

- **Redis:** Image `redis:7`. Exposes `6379`. Used as single list `job_queue`.
- **Docker Compose:** Defines `redis`, `api`, `worker`. `api` and `worker` `depends_on: redis` with `condition: service_started`.
- **Scaling:** `docker compose up -d --scale worker=N`; workers share `job_queue`; `BLPOP` ensures exactly-once delivery per job.

### Documentation

- **README:** Project structure, Quick Start (`docker compose up --build`), `curl` example for `/submit`, config table, scaling instructions.
- **Architecture doc:** Components, data flow (submit → queue → BLPOP → process), `RPUSH`/`BLPOP` protocol, deployment, possible extensions (retries, DLQ, health, persistence, priorities).

---

## 2. Suggested Feature Roadmap

### Foundation

- **`.gitignore`:** `__pycache__`, `*.pyc`, `.env`, `venv`, `.venv`, `.pytest_cache`, `*.egg-info`, `.DS_Store`.
- **Pinned `requirements.txt`:** Pin `flask`, `redis` (and `pytest`, `pytest-cov`, `requests` when tests are added) to specific versions for reproducible builds.
- **`/health` (API):** `GET /health` that returns `200` when Redis `PING` succeeds; `503` or `500` on Redis failure.
- **Compose `healthcheck`:** For `api`: HTTP GET to `/health`. For `worker`: script that verifies Redis connectivity or exits 0 if the worker process is running (e.g., simple `redis-cli PING` or a small sidecar-style check).
- **Optional:** Worker heartbeat (e.g., periodic key in Redis) for liveness; can follow after basic `healthcheck`.

### Reliability

- **Job ID on submit:** Generate UUID in `submit_job`; include in response and in the JSON stored in the queue.
- **Status store:** Worker writes outcome to Redis (e.g., `HSET job:<id> status completed|failed result ...`) with TTL or retention policy.
- **`GET /jobs/:id`:** Reads from Redis; returns `{ "id", "status", "task", "result"?, "created_at"? }` or `404`.
- **Retries:** Attempt counter in job payload; on exception or explicit failure, re-`RPUSH` to `job_queue` until max attempts (e.g., 3); then `RPUSH` to `dead_letter` (or `job_queue:dlq`).
- **DLQ:** Separate list or key pattern for failed jobs; optional `GET /jobs/:id` or admin view to inspect.

### DevOps / SDLC

- **Unit tests (pytest):** `POST /submit` (valid, invalid, missing `task`); `GET /health` (with mocked Redis); optionally `GET /jobs/:id` once implemented.
- **Integration tests:** `docker compose up` (or `run`) + submit job + poll `GET /jobs/:id` until `completed` or timeout; optionally test retry/DLQ path.
- **GitHub Actions:** On push/PR: `pip install -r requirements.txt`, `pytest`, `docker compose build`; optionally `docker compose up` for integration.
- **Structured logging:** Replace `print` in worker with a logger (JSON or key-value fields: `job_id`, `task`, `level`, `message`); add request/response logging in Flask (e.g., `job_id`, `status_code`, `path`).

### Observability

- **Metrics:** In-memory counters for `jobs_submitted`, `jobs_completed`, `jobs_failed`; `LLEN job_queue` for queue depth. Expose via `GET /metrics` (Prometheus-style) or a minimal JSON endpoint.
- **Optional:** OpenTelemetry or tracing later; start with counts and queue depth.

### Cloud / Scalability

- **Azure deployment:**
  - **Option A — Azure Container Apps:** Use Compose or `az containerapp` to deploy `api`, `worker`, and Redis (or Azure Cache for Redis). Document in a "Deploy to Azure" section.
  - **Option B — AKS:** Kubernetes manifests (Deployment + Service) for `api`, `worker`, and Redis (or Azure Cache for Redis). Good for "enterprise" and K8s discussions.
- **README:** Short "Deploy to Azure" with prerequisites (`az`, `az containerapp` or `kubectl`) and commands or links to manifests.

### Differentiators (Pick 1–2)

- **OpenAPI / Swagger:** Use `flask-openapi3`, `apispec`, or similar to document `POST /submit`, `GET /jobs/:id`, `GET /health`, `GET /metrics`. Serve Swagger UI; link from README. Supports "API-first" and "developer experience" talking points.
- **AI job type:** A job type (e.g., `{"task": "summarize", "type": "ai", "input": "..."}`) where the worker calls an Azure AI / OpenAI-style API (or a stub) and stores the result. Positions the system as "AI-workload ready" or "Foundry-friendly."
- **Multi-queue / priority:** A second list (e.g., `job_queue:high`) and `BLPOP` with multiple keys (`job_queue:high`, `job_queue`) for priority ordering. Demonstrates scalable solution design and more advanced queue patterns.
