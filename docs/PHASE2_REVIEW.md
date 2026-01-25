# Phase 2 Implementation Review: Reliability

A short review of the Phase 2 (Reliability) implementation, with a **mentorship lens** on why these design choices were made. The goal is to make the reasoning reusable when you discuss the system in interviews or with peers.

---

## What Was Implemented

| Roadmap item | Implementation |
|--------------|----------------|
| **Job ID on submit** | `uuid.uuid4()` in `submit_job`; included in the API response and in the JSON enqueued to `job_queue`. |
| **Store status in Redis** | `HSET job:<id>` with `status`, `task`, `created_at`; worker adds `result`/`completed_at` on success or `error`/`failed_at` on final failure. `EXPIRE job:<id> 604800` (7 days) on creation. |
| **GET /jobs/:id** | `GET /jobs/<job_id>` reads `HGETALL job:<id>`, returns `{id, status, task, created_at, result?, completed_at?, error?, failed_at?}` or `404`. |
| **Retries + DLQ** | `attempts` in the queue payload; worker on exception increments `attempts`, re-`RPUSH` to `job_queue` if `attempts < MAX_ATTEMPTS` (4), else `RPUSH dead_letter` and `HSET status=failed, error, failed_at`. Four total attempts = 3 retries ("retried up to 3x"). `task == "fail"` raises to simulate failure. |

---

## Mentorship Lens: Why These Choices?

### 1. UUID for job ID (instead of a numeric or in-memory counter)

**What we did:** `job_id = str(uuid.uuid4())` at submit time.

**Why it matters:** In a distributed system, the API and workers don’t share a single database or in-memory counter. A numeric ID would require a central store (e.g. Redis `INCR`) and extra round-trips and failure modes. A **UUID is generated locally**, needs no coordinator, and is globally unique with very high probability. You can also generate IDs in a worker or in another service without conflicting. For interviews: “We use UUIDs so we can create IDs in the API without a shared sequence and so the system can grow to more producers or regions later.”

---

### 2. Status in a separate hash (`job:<id>`) instead of only in the queue

**What we did:** The API creates `job:<id>` with `status=queued` before `RPUSH` to `job_queue`. The worker updates the same hash. `GET /jobs/<id>` does `HGETALL job:<id>`.

**Why it matters:** The queue is for **work to be done**; it’s consumed and mutated by `BLPOP`. If status lived only in the queue, you’d have to scan the list to find a job by ID, or keep a separate index. A **dedicated key per job** gives:

- **O(1) lookups** by ID for `GET /jobs/<id>`.
- **No need to touch the queue** for reads, so consumers aren’t affected.
- **Clear lifecycle**: one key per job, updated as it moves through queued → processing → completed/failed.

The queue payload stays small (`{id, task, attempts, created_at}`); the “source of truth” for status is `job:<id>`. For interviews: “We store status in a hash keyed by job ID so we can look up any job in O(1) without scanning the queue, and so the worker can update status without changing the queue structure.”

---

### 3. `attempts` in the queue payload (instead of only in the hash)

**What we did:** Each enqueue and re-enqueue carries `{id, task, attempts, created_at}`. The worker reads `attempts` from the message and, on failure, increments and re-`RPUSH`es that updated JSON.

**Why it matters:** The **message is the contract** between producer and consumer. The worker must know how many attempts have already been made **when it pops the message**, without a separate read. If `attempts` lived only in `job:<id>`, the worker would have to `HGET job:<id> attempts` before every process. Putting it in the payload:

- Keeps **one read** (`BLPOP`) to get both the work and its attempt count.
- Avoids races where the worker pops, then checks the hash, and another process has already retried.
- Keeps retry logic **local to the message**: “this message has already been tried N times.”

For interviews: “We carry `attempts` in the queue payload so the worker can decide retry vs DLQ in one place, without an extra read, and so the decision is based on the exact message it’s processing.”

---

### 4. Dead-letter queue (DLQ) instead of discarding or infinite retry

**What we did:** After 4 total attempts (3 retries), the worker `RPUSH`es the same JSON to `dead_letter` and sets `job:<id>` to `status=failed` with `error` and `failed_at`. We use `MAX_ATTEMPTS = 4` and `if attempts < MAX_ATTEMPTS` so that "retried up to 3x" means 3 retries, 4 total attempts.

**Why it matters:** Failed jobs often need **inspection and manual or automated handling**. If you drop them or retry forever, you lose visibility and can create unbounded load. A **DLQ**:

- **Preserves the failed message** for debugging and replay.
- **Stops retrying** so one bad job doesn’t spin forever.
- **Keeps the main queue clean** so healthy jobs aren’t blocked.

The `job:<id>` hash gives you a **status view** (e.g. in a UI or `GET /jobs/<id>`); the DLQ gives you the **raw message** for replay or analysis. For interviews: “We use a DLQ so we never lose a failed job and can debug or replay it without impacting the main queue.”

---

### 5. TTL on `job:<id>`

**What we did:** `EXPIRE job:<id> 604800` (7 days) when the API creates the hash.

**Why it matters:** Without a TTL, every job would leave a key in Redis forever. Over time that means **unbounded memory use** and key growth. A **TTL**:

- Bounds storage and helps with capacity planning.
- Implements a simple **retention policy**: “we care about recent jobs.”

7 days is a placeholder; in production you’d tune this to operational and compliance needs. For interviews: “We set a TTL on the job hash so we don’t accumulate state indefinitely and to keep a predictable retention window.”

---

### 6. Create `job:<id>` on submit (before the worker runs)

**What we did:** The API does `HSET job:<id>` and `EXPIRE` before `RPUSH job_queue`.

**Why it matters:** If we only created `job:<id>` when the worker finished, `GET /jobs/<id>` would 404 for **queued or in-flight** jobs. Creating it at submit with `status=queued` means:

- **Every valid ID has a status** from the moment it’s created.
- Clients can **poll** `GET /jobs/<id>` as soon as they get the `id` from `POST /submit`.

For interviews: “We create the status hash at submit time so clients can poll status immediately, and so we have a single place to represent the full lifecycle.”

---

### 7. Simulated failure: `task == "fail"`

**What we did:** In the worker, `if task == "fail": raise RuntimeError("Simulated failure for testing")`.

**Why it matters:** Retry and DLQ are only useful if you can **trigger failures** in a controlled way. A special `task` value lets you:

- **Test retries** (see attempt logs and `status=queued` then `completed` or `failed`).
- **Test DLQ** (after 4 total attempts / 3 retries, `status=failed`, `GET /jobs/<id>`, and `dead_letter`).
- **Demo the behavior** without depending on real infrastructure failures.

For interviews: “We support a test-only `task` value that forces an exception so we can validate retry and DLQ without relying on real failures.”

---

## Limitations and “What’s next”

**Worker crash after `BLPOP` but before `HSET completed`:** The job is removed from the queue and never re-queued; `job:<id>` can stay `status=processing`. A future improvement is a **reconciler** that finds stale `processing` jobs (e.g. older than N minutes) and either re-queues them or marks them `failed` and pushes to the DLQ. Phase 2 does not implement this; it’s called out in the architecture doc.

**At-least-once delivery:** Retries and re-queue mean the same logical job can be processed more than once. If the worker is not idempotent, you can get duplicates. For the current “sleep and log” workload this is fine; for side effects (e.g. charging, sending email) you’d add idempotency (e.g. by `id`) or stronger guarantees.

**`decode_responses=True` on the Redis client:** Both the API and worker use `decode_responses=True` so `HGETALL` and `BLPOP` return strings. That simplifies JSON and response handling. If you later need raw bytes (e.g. binary payloads), you’d use a different key or a client without `decode_responses` for that usage.

---

## Summary

Phase 2 adds **traceability** (job ID, status, `GET /jobs/<id>`), **resilience** (retries, DLQ), and **operational bounds** (TTL, DLQ instead of infinite retry). The mentorship lens highlights: **UUIDs for distribution and no single point of coordination**, **status in a hash for O(1) reads and a clear lifecycle**, **attempts in the payload for simple, local retry decisions**, **DLQ for preserving and isolating failures**, **TTL for retention**, and **creating the job at submit** so clients can poll immediately. Understanding these reasons will help you explain the design in architecture discussions and interviews.
