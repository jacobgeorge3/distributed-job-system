# Architecture

## Overview

The system is a **distributed job queue**: clients submit jobs over HTTP, a central Redis list holds pending work, and one or more Python workers consume and process jobs. No job scheduler or extra messaging broker is used beyond Redis.

```
┌─────────┐     POST /submit      ┌─────────────┐     RPUSH      ┌───────┐     BLPOP      ┌────────┐
│ Client  │ ──────────────────►  │ API Service │ ─────────────► │ Redis │ ◄──────────── │ Worker │
└─────────┘                      │  (Flask)    │                │ List  │                │ (×N)   │
                                 └─────────────┘                └───────┘                └────────┘
```

## Components

### API Service (`api-service/`)

- **Role:** HTTP ingress for job submission.
- **Stack:** Flask, Redis client.
- **Endpoint:** `POST /submit` — body must include `task` (or equivalent job payload). Responds with `{"status": "queued", "task": "..."}` or `400` on invalid input.
- **Queue write:** Uses `RPUSH` to append serialized JSON to the Redis list `job_queue`.
- **Deployment:** Exposes port 5000; in `docker-compose` it is mapped to 5001.

### Worker Service (`worker-service/`)

- **Role:** Queue consumer. Blocks on `job_queue`, deserializes JSON, runs the job logic, and repeats.
- **Stack:** Redis client only (no HTTP server).
- **Queue read:** Uses `BLPOP job_queue` for blocking, FIFO consumption. One worker claims one job at a time.
- **Processing:** Current implementation sleeps 2 seconds per job and logs start/finish. Job logic can be extended in `worker.py`.
- **Deployment:** No exposed ports; receives `REDIS_HOST` and `REDIS_PORT` from the environment.

### Redis

- **Role:** In-memory list used as a FIFO queue.
- **Key:** `job_queue` (Redis `LIST`).
- **Protocol:**
  - **Producers (API):** `RPUSH job_queue <json>`.
  - **Consumers (workers):** `BLPOP job_queue [timeout]` → one JSON string per pop.
- **Persistence:** Default Redis image keeps data in memory; configure `redis.conf` / volume if persistence is required.

## Data Flow

1. **Submit:** Client sends `POST /submit` with `{"task": "name"}` (or richer payload). API validates, `RPUSH`es to `job_queue`, returns immediately.
2. **Queue:** Jobs sit in `job_queue` until a worker is free.
3. **Process:** A worker `BLPOP`s, gets one JSON, parses it, runs the job (e.g. `time.sleep(2)`), then loops. Other workers block on `BLPOP` and take the next job when one becomes available.
4. **Ordering:** FIFO per list. If stronger ordering or partitions are needed, the design would need additional keys or structures.

## Job Payload

- **Current schema:** `{"task": "<string>"}`. The API checks for the presence of `task`.
- **Extensibility:** Extra fields in the JSON are passed through to the worker. The worker uses `job.get("task")` and can be extended to handle more fields (retries, priorities, routing, etc.).

## Deployment

- **Docker Compose:** Defines `redis`, `api`, and `worker`. `api` and `worker` `depends_on: redis` with `condition: service_started`.
- **Scaling:** Multiple `worker` replicas (`--scale worker=N`) share the same `job_queue`; `BLPOP` ensures each job is taken by only one worker.
- **Networking:** All services on the same Compose network; `REDIS_HOST=redis` resolves to the Redis container.

## Project Layout

```
distributed-job-system/
├── api-service/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── worker-service/
│   ├── worker.py
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
├── docs/
│   └── architecture.md
└── README.md
```

## Possible Extensions

- **Retries / DLQ:** On failure, `RPUSH` to a `dead_letter` list or re-queue with attempt count.
- **Priorities:** Use multiple lists (e.g. `job_queue:high`, `job_queue:low`) and `BLPOP` several keys; or a sorted set with a score.
- **Result storage:** Worker writes outcomes to Redis (e.g. `HSET result:<id> ...`) or to a DB; API or another service can poll or be notified.
- **Health checks:** API: HTTP `/health`; worker: heartbeat key or sidecar. Add `healthcheck` in `docker-compose` for each service.
- **Persistence:** Configure Redis `appendonly yes` and a volume so the queue survives restarts.
