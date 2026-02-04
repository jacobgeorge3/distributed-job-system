# Unified Roadmap — Distributed Job System

**Single source of truth** for the project roadmap. Consolidates FEATURE_LIST_AND_ROADMAP, PRIORITIZED_ROADMAP, and REPO_ANALYSIS into one document.

---

## Phase 0 — Baseline (COMPLETE ✅)

- Containerized API + Worker
- Redis-backed queue
- Horizontal worker scaling (`docker compose --scale worker=N`)
- Job lifecycle (queued → processing → completed | failed)
- UUID job IDs, status hashes, `GET /jobs/<id>`
- Retries + DLQ (4 total attempts = 3 retries)
- API usage + architecture docs
- `/health` endpoint

---

## Phase 1 — Production Hygiene (⚡ FAST WINS)

**Goal:** Make the system *operationally credible*

| Item | Status |
|------|--------|
| Compose `healthcheck` (API: `/health`, Worker: Redis PING) | ✅ Done |
| Pin dependencies in `requirements.txt` | ✅ Done |
| `.gitignore` | ✅ Done |

**Outcome:** Ready for orchestration, CI, and cloud deployment

---

## Phase 2 — Testability & CI (Critical Gap → In Progress)

**Goal:** Support refactoring, demos, and CI/CD claims

| Item | Status |
|------|--------|
| Unit tests (pytest): `/health`, `POST /submit`, `GET /jobs/:id` | ✅ Done |
| Integration test: compose up → submit → poll → completed | 🔜 Next |
| GitHub Actions: install deps, pytest, docker build | ✅ Done |

**Outcome:** Resume-worthy DevOps story

---

## Phase 3 — Observability

**Goal:** Visibility into system behavior

- `/metrics` endpoint:
  - `jobs_submitted`, `jobs_completed`, `jobs_failed`
  - Queue depth (`LLEN job_queue`)
- Structured logging (JSON): `job_id`, `task`, `status`, `worker_id`

**Outcome:** "Production-ready" credibility

---

## Phase 4 — Failure Reconciliation (Advanced Reliability)

**Goal:** Close the biggest known failure mode

- Background reconciler:
  - Scan for `status=processing` older than N minutes
  - Requeue or mark failed
- Document delivery semantics explicitly

**Outcome:** Strong distributed-systems talking point

---

## Phase 5 — Cloud Deployment (Pick One)

- Azure Container Apps **or** AKS manifests
- Redis → Azure Cache for Redis
- "Deploy to Azure" README section

**Outcome:** Cloud-native proof

---

## Phase 6 — Differentiators (Optional, Strategic)

Pick **one**, not all:

- OpenAPI + Swagger UI
- Priority queues (`job_queue:high`)
- AI job type (stubbed or real)

**Outcome:** Tailored to Cloud & AI SE roles

---

## Resume & Interview Angles

| Topic | Where it shows up |
|-------|-------------------|
| **Cloud-native** | Containers, microservices, scaling; Azure (Phase 5) |
| **DevOps / CI/CD** | GitHub Actions, tests, healthchecks (Phases 1–2) |
| **Secure, scalable design** | Retries, DLQ, status, metrics, health |
| **APIs, containers, microservices** | REST API, Docker, API vs. worker vs. Redis |
| **AI** (optional) | AI job type (Phase 6) |

---

## Related Docs

- [architecture.md](architecture.md) — Component design, data flow, `RPUSH`/`BLPOP` protocol
- [API_USAGE.md](API_USAGE.md) — API reference and examples
- [PHASE2_REVIEW.md](PHASE2_REVIEW.md) — Mentorship lens on reliability implementation (UUIDs, status hash, retries, DLQ)
