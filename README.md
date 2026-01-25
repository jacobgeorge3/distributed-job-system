# Distributed Job System

A small distributed job queue using **Flask**, **Redis**, and Python workers. Jobs are submitted via HTTP, queued in Redis, and processed asynchronously by one or more workers.

## Architecture

- **API service** — accepts job submissions (`POST /submit`) and pushes them to a Redis list
- **Worker service** — blocks on the queue, processes jobs, and logs progress
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

## Submitting a Job

```bash
curl -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "my-job-name"}'
```

Response:

```json
{"status": "queued", "task": "my-job-name"}
```

Workers process jobs in order; each run simulates 2 seconds of work and logs to stdout.

## Project Structure

```
distributed-job-system/
├── api-service/
│   ├── main.py           # Flask app, /submit handler
│   ├── requirements.txt
│   └── Dockerfile
├── worker-service/
│   ├── worker.py         # Queue consumer loop
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml    # Redis, API, worker
├── docs/
│   └── architecture.md
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
