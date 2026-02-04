# Multi-Machine Demo Setup

This guide walks you through running the distributed job system across two (or more) machines: the API on one laptop, workers on another. This is a strong demo for showing horizontal scaling and distributed processing.

---

## Prerequisites

- Both machines on the same network (same Wi‑Fi or LAN)
- Docker and Docker Compose installed on both
- Laptop A's IP address (e.g. `192.168.1.100`) — run `ipconfig` (Windows) or `ifconfig` / `ip addr` (Mac/Linux) to find it

---

## Architecture

```
┌─────────────────────────────────────────┐
│  Laptop A (API Host)                    │
│  ┌─────────┐  ┌─────────────┐           │
│  │ Redis   │  │ API Service │           │
│  │ :6379   │  │ :5001       │           │
│  └────┬────┘  └──────┬──────┘           │
│       │              │                   │
│       └──────────────┼───────────────────┼─── Your machine: curl POST here
│                      │                   │
└──────────────────────┼───────────────────┘
                       │
         Same network  │  REDIS_HOST=<LAPTOP_A_IP>
                       │
┌──────────────────────┼───────────────────┐
│  Laptop B (Worker)   │                   │
│  ┌───────────────────▼──────┐            │
│  │ Worker (connects to      │            │
│  │ Redis on Laptop A)       │            │
│  └──────────────────────────┘            │
└──────────────────────────────────────────┘
```

---

## Step 1: Firewall on Laptop A

Laptop A must accept inbound connections on:

- **6379** — Redis (for workers)
- **5001** — API (for you to submit jobs)

**Windows:**  
- Windows Defender Firewall → Advanced settings → Inbound Rules  
- New Rule → Port → TCP → 6379, 5001 → Allow

**Mac:**  
- System Preferences → Security & Privacy → Firewall → Firewall Options  
- Allow incoming connections for Docker (or temporarily disable for demo)

**Linux:**  
```bash
sudo ufw allow 6379
sudo ufw allow 5001
sudo ufw reload
```

---

## Step 2: Run API + Redis on Laptop A

On **Laptop A**:

```bash
cd distributed-job-system
docker compose up redis api
```

Leave this running. You should see:
- Redis listening
- API listening on port 5000 (mapped to 5001 on the host)

Verify locally:
```bash
curl http://localhost:5001/health
# Empty response with 200 = OK
```

---

## Step 3: Build Worker Image on Laptop B

On **Laptop B**, clone the repo (or copy it) and build:

```bash
cd distributed-job-system
docker compose build worker
```

---

## Step 4: Run Worker on Laptop B

Replace `LAPTOP_A_IP` with Laptop A's actual IP (e.g. `192.168.1.100`):

```bash
docker run --rm -e REDIS_HOST=LAPTOP_A_IP -e REDIS_PORT=6379 distributed-job-system-worker
```

You should see:
```
Worker starting, connecting to Redis at LAPTOP_A_IP:6379
```

The worker is now blocking on `BLPOP`, waiting for jobs.

---

## Step 5: Submit a Job

From **any machine** on the network (your main laptop, Laptop A, or Laptop B):

```bash
curl -X POST http://LAPTOP_A_IP:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "hello-from-demo"}'
```

Expected response:
```json
{"status": "queued", "task": "hello-from-demo", "id": "550e8400-e29b-41d4-a716-446655440000"}
```

**Watch the logs:**
- **Laptop A (API):** No special output for the request unless you add logging
- **Laptop B (Worker):** You should see `Finished job: <id> (hello-from-demo)` after ~2 seconds

---

## Step 6: Poll Job Status

Use the `id` from the submit response:

```bash
curl http://LAPTOP_A_IP:5001/jobs/550e8400-e29b-41d4-a716-446655440000
```

You'll see status progress: `queued` → `processing` → `completed` (or `failed`).

---

## Step 7: Demo Failure & Retries

Submit a job that forces a failure:

```bash
curl -X POST http://LAPTOP_A_IP:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"task": "fail"}'
```

**On Laptop B (Worker):** You'll see:
```
Retrying job <id> (fail) attempt 1/4
Retrying job <id> (fail) attempt 2/4
Retrying job <id> (fail) attempt 3/4
Job <id> failed after 4 attempts, moved to DLQ: Simulated failure for testing
```

Poll `GET /jobs/<id>` — status will eventually be `failed` with an `error` field.

---

## Step 8: Scale Workers

Open a **second terminal** on Laptop B (or use a third machine):

```bash
docker run --rm -e REDIS_HOST=LAPTOP_A_IP -e REDIS_PORT=6379 distributed-job-system-worker
```

Now you have two workers. Submit several jobs in quick succession:

```bash
curl -X POST http://LAPTOP_A_IP:5001/submit -H "Content-Type: application/json" -d '{"task": "job-1"}'
curl -X POST http://LAPTOP_A_IP:5001/submit -H "Content-Type: application/json" -d '{"task": "job-2"}'
curl -X POST http://LAPTOP_A_IP:5001/submit -H "Content-Type: application/json" -d '{"task": "job-3"}'
```

Jobs will be distributed across workers via `BLPOP` — each job is consumed by exactly one worker. Watch both worker terminals; they'll process different jobs.

---

## Troubleshooting

| Problem | Check |
|--------|-------|
| Worker can't connect to Redis | Verify Laptop A's IP, firewall allows 6379, both on same network |
| `curl` to API times out | Firewall allows 5001; try `curl` from Laptop A first (`localhost:5001`) |
| Jobs never complete | Worker logs on Laptop B — is it connected? Did it print "Worker starting..."? |
| "Connection refused" | Redis may not be exposed; ensure `docker compose up redis api` is running on Laptop A |

---

## Summary

- **Laptop A:** `docker compose up redis api` — Redis + API
- **Laptop B:** `docker run --rm -e REDIS_HOST=<A_IP> -e REDIS_PORT=6379 distributed-job-system-worker`
- **Submit:** `curl -X POST http://<A_IP>:5001/submit -H "Content-Type: application/json" -d '{"task": "..."}'`
- **Status:** `curl http://<A_IP>:5001/jobs/<id>`
- **Fail demo:** `{"task": "fail"}`
- **Scale:** Run multiple `docker run ... worker` instances
