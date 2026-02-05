# Distributed Job System

A small distributed job queue using **Flask**, **Redis**, and Python workers. Jobs are submitted via HTTP, queued in Redis, and processed asynchronously by one or more workers.

## Architecture

- **API service** — `POST /submit` (returns job `id`), `GET /jobs/<id>` (status), `GET /health`; pushes jobs to a Redis list; status stored in `job:<id>` hashes
- **Worker service** — blocks on the queue, processes jobs, updates `job:<id>` status, retries up to 3 times (4 total attempts) on failure, then moves to `dead_letter`
- **Redis** — in-memory queue and broker

See [docs/architecture.md](docs/architecture.md) for a detailed design.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

## Quick Start

```bash
docker compose up --build
```

- API: <http://localhost:5001>
- Redis: `localhost:6379`

**Health check:** `curl http://localhost:5001/health` — returns 200 when Redis is reachable, 503 otherwise.

## Submitting a Job

```bash
curl -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "my-job-name"}'
```

Response:

```json
{"status": "queued", "task": "my-job-name", "id": "550e8400-e29b-41d4-a716-446655440000"}
```

Use `id` to poll status: `GET /jobs/<id>` returns `{ "id", "status", "task", "created_at", "result"?, "completed_at"?, "error"?, "failed_at"? }`. Status is `queued`, `processing`, `completed`, or `failed`. `404` if not found.

Workers process jobs in order; each run simulates 2 seconds of work and logs to stdout. Failed jobs are retried up to 3 times (4 total attempts), then moved to `dead_letter`. Use `{"task": "fail"}` to simulate failure and exercise retry/DLQ.

## Project Structure

```
distributed-job-system/
├── api-service/
│   ├── main.py           # Flask app, /submit, /health, /jobs/<id>
│   ├── requirements.txt
│   └── Dockerfile
├── worker-service/
│   ├── worker.py         # Queue consumer loop
│   ├── requirements.txt
│   └── Dockerfile
├── tests/
│   ├── conftest.py         # Pytest path setup
│   ├── test_api.py         # Unit tests (mocked Redis)
│   └── test_integration.py # Integration tests (Docker Compose)
├── .github/workflows/
│   └── ci.yml            # GitHub Actions: pytest, docker build
├── docker-compose.yml    # Redis, API, worker (with healthchecks)
├── docs/
│   ├── architecture.md
│   └── UNIFIED_ROADMAP.md  # Single roadmap (phases, gaps, next steps)
└── README.md
```

## Configuration

| Variable      | Default | Description        |
|---------------|---------|--------------------|
| `REDIS_HOST`  | `redis` | Redis host (service name in Compose) |
| `REDIS_PORT`  | `6379`  | Redis port         |

Override in `docker-compose.yml` or via the environment for each service.

## Scaling Workers

To run multiple workers:

```bash
docker compose up --build -d && docker compose up -d --scale worker=3
```

Jobs are distributed across workers via `BLPOP` on the shared queue.

## Running Tests

**Unit tests** (no Docker, mocked Redis):
```bash
pip install -r api-service/requirements.txt
pytest tests/ -v -m "not integration"
```

**Integration tests** (requires Docker, spins up full stack):
```bash
pip install -r api-service/requirements.txt
pytest tests/test_integration.py -v -m integration
```
