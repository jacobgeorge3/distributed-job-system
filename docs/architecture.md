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
- **Endpoints:** `POST /submit` (body: `{"task": "..."}`; returns `{"status": "queued", "task", "id"}` or `400`); `GET /jobs/<id>` (returns `{id, status, task, created_at, result?, completed_at?, error?, failed_at?}` or `404`); `GET /health`.
- **Queue write:** `RPUSH job_queue` with JSON `{id, task, attempts, created_at}`. Before enqueue, `HSET job:<id>` with `status=queued`, `task`, `created_at` and `EXPIRE` (7 days) so `GET /jobs/<id>` works immediately.
- **Deployment:** Port 5000; in `docker-compose` mapped to 5001.

### Worker Service (`worker-service/`)

- **Role:** Queue consumer. Blocks on `job_queue`, deserializes JSON, runs the job logic, updates `job:<id>` status, and handles retries/DLQ.
- **Stack:** Redis client only (no HTTP server).
- **Queue read:** `BLPOP job_queue`; payload is `{id, task, attempts, created_at}`.
- **Processing:** Sets `job:<id>` to `processing`; on success, `HSET` `status=completed`, `result`, `completed_at`; on exception, `attempts+1`; if `attempts < 3`, `RPUSH job_queue` (retry) and `status=queued`; else `HSET status=failed`, `error`, `failed_at` and `RPUSH dead_letter`. `task == "fail"` raises to simulate failure.
- **Deployment:** No exposed ports; `REDIS_HOST`, `REDIS_PORT`.

### Redis

- **Lists:** `job_queue` (FIFO; JSON `{id, task, attempts, created_at}`), `dead_letter` (same schema for jobs that failed after 3 attempts).
- **Hashes:** `job:<id>` — `status`, `task`, `created_at`; when done: `result`, `completed_at` or `error`, `failed_at`. `EXPIRE job:<id> 604800` (7 days) set on creation.
- **Protocol:** API `RPUSH job_queue` and `HSET job:<id>` on submit; worker `BLPOP`, `HSET` for status, `RPUSH job_queue` (retry) or `RPUSH dead_letter` (DLQ).
- **Persistence:** Default in-memory; use `appendonly`/volume for durability.

## Data Flow

1. **Submit:** Client sends `POST /submit` with `{"task": "name"}`. API generates `id`, `created_at`, `HSET job:<id>`, `EXPIRE`, `RPUSH job_queue {id,task,attempts:0,created_at}`, returns `{status, task, id}`.
2. **Queue:** Jobs sit in `job_queue` until a worker is free. `GET /jobs/<id>` reads `job:<id>` (e.g. `queued`, then `processing`, then `completed` or `failed`).
3. **Process:** Worker `BLPOP`s, `HSET job:<id> status=processing`, runs the job. On success: `HSET status=completed, result, completed_at`. On failure: `attempts+1`; if `< 3` then `RPUSH job_queue` and `status=queued`; else `HSET status=failed, error, failed_at` and `RPUSH dead_letter`.
4. **Ordering:** FIFO per list. Retries re-enter at the tail.

## Job Payload

- **Submit body:** `{"task": "<string>"}`. API generates `id` (UUID), `created_at` (ISO), `attempts=0`.
- **Queue/DLQ JSON:** `{id, task, attempts, created_at}`. Worker uses `attempts` to decide retry vs DLQ.
- **Extensibility:** Extra fields in the submit body can be passed through; worker can be extended for priorities, routing, etc.

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

- **Priorities:** Multiple lists (`job_queue:high`, `job_queue`) and `BLPOP` over several keys; or a sorted set.
- **Healthchecks in Compose:** `healthcheck` for `api` (HTTP `/health`) and `worker` (e.g. Redis `PING`).
- **Persistence:** Redis `appendonly yes` and a volume so the queue and `job:<id>` (and `dead_letter`) survive restarts.
- **Reconciliation:** Worker can crash after `BLPOP` but before `HSET completed`; `job:<id>` stays `processing`. A periodic job could scan for stale `processing` and re-queue or mark failed.
