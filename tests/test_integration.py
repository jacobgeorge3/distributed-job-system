"""
Integration tests: full stack (API + Redis + Worker) via Docker Compose.

Requires Docker. Run from project root: pytest tests/test_integration.py -v
"""
import subprocess
import time
from pathlib import Path

import pytest
import requests

# Project root (parent of tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

API_URL = "http://localhost:5001"
HEALTH_TIMEOUT = 60  # seconds to wait for API to become healthy
POLL_TIMEOUT = 30    # seconds to wait for job completion
POLL_INTERVAL = 0.5  # seconds between status polls



def test_submit_and_complete(stack):
    """Submit a job, poll until status is completed."""
    resp = requests.post(
        f"{API_URL}/submit",
        json={"task": "integration-test"},
        headers={"Content-Type": "application/json"},
        timeout=5,
    )
    assert resp.status_code == 200
    data = resp.json()
    job_id = data["id"]
    assert data["status"] == "queued"
    assert data["task"] == "integration-test"

    # Poll until completed (worker sleeps 2s, so ~3–5s total)
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        r = requests.get(f"{API_URL}/jobs/{job_id}", timeout=5)
        assert r.status_code == 200
        status = r.json()["status"]
        if status == "completed":
            assert "result" in r.json()
            return
        if status == "failed":
            pytest.fail(f"Job failed: {r.json().get('error', 'unknown')}")
        time.sleep(POLL_INTERVAL)

    pytest.fail(f"Job did not complete in {POLL_TIMEOUT}s; last status: {status}")


@pytest.mark.integration
def test_submit_fail_moves_to_dlq(stack):
    """Submit task 'fail', poll until status is failed (after retries and DLQ)."""
    resp = requests.post(
        f"{API_URL}/submit",
        json={"task": "fail"},
        headers={"Content-Type": "application/json"},
        timeout=5,
    )
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    # Poll until failed (4 attempts × ~2s + processing ≈ 15–20s)
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        r = requests.get(f"{API_URL}/jobs/{job_id}", timeout=5)
        assert r.status_code == 200
        data = r.json()
        if data["status"] == "failed":
            assert "error" in data
            assert "Simulated failure" in data["error"]
            return
        time.sleep(POLL_INTERVAL)

    pytest.fail(f"Job did not reach failed status in {POLL_TIMEOUT}s")
