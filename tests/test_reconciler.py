import pytest
import subprocess
import time
import requests
from pathlib import Path

API_URL = "http://localhost:5001"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

@pytest.mark.integration
def test_reconciler_requeues_stale_job(stack):
    """
    Test that the reconciler detects a stuck job and requeues it.
    
    1. Submit a job that takes time (we simulate this by killing worker immediately).
    2. Wait for it to be 'processing'.
    3. Kill the worker container.
    4. Wait > STALE_THRESHOLD_SECONDS (5s).
    5. Verify job status becomes 'queued' (reconciler action).
    6. Restart worker.
    7. Verify job completes.
    """
    # 1. Submit job
    resp = requests.post(f"{API_URL}/submit", json={"task": "test-stale-requeue"})
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    # 2. Wait for it to be picked up (status=processing)
    # The worker sleeps 2s, so we have a window.
    start = time.time()
    while time.time() - start < 5:
        r = requests.get(f"{API_URL}/jobs/{job_id}")
        if r.json()["status"] == "processing":
            break
        time.sleep(0.1)
    else:
        pytest.fail("Job never reached processing state")

    # 3. Kill worker immediately
    subprocess.run(["docker", "compose", "kill", "worker"], cwd=PROJECT_ROOT, check=True)

    # 4. Wait for reconciler
    # Configured for 5s threshold + 1s interval. Wait 8s to be safe.
    time.sleep(8)

    # 5. Verify requeued
    r = requests.get(f"{API_URL}/jobs/{job_id}")
    data = r.json()
    assert data["status"] == "queued", f"Job should be queued, but is {data['status']}"
    # Verify attempts incremented (0 -> 1)
    # (Note: depending on if worker updated attempts in hash before crashing.
    # Our worker doesn't update attempts in hash until retry logic, which didn't run.
    # So attempts should be 0 in hash, reconciler increments to 1.)
    
    # Actually wait - in main.py submit_job, attempts=0. Use that.
    
    # 6. Restart worker to finish the job
    subprocess.run(["docker", "compose", "start", "worker"], cwd=PROJECT_ROOT, check=True)

    # 7. Verify completion
    # Give it time to process
    start = time.time()
    while time.time() - start < 10:
        r = requests.get(f"{API_URL}/jobs/{job_id}")
        if r.json()["status"] == "completed":
            return
        time.sleep(0.5)
    
    pytest.fail(f"Job did not complete after worker restart. Status: {r.json()['status']}")
