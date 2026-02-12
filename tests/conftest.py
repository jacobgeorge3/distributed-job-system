import subprocess
import time
import os
from pathlib import Path
import pytest
import requests

# Project root (parent of tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_URL = "http://localhost:5001"
HEALTH_TIMEOUT = 60

@pytest.fixture(scope="session")
def stack():
    """
    Start Docker Compose stack with test config.
    Wait for API health.
    Teardown after session.
    """
    # Override reconciler settings for fast tests
    env = os.environ.copy()
    env["STALE_THRESHOLD_SECONDS"] = "5"
    env["RECONCILER_INTERVAL"] = "1"
    
    subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=PROJECT_ROOT,
        check=True,
        env=env,
        capture_output=True,
    )

    # Wait for API /health
    start = time.time()
    while time.time() - start < HEALTH_TIMEOUT:
        try:
            r = requests.get(f"{API_URL}/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        subprocess.run(["docker", "compose", "down"], cwd=PROJECT_ROOT, capture_output=True)
        pytest.fail("API did not become healthy in time")

    yield

    subprocess.run(
        ["docker", "compose", "down"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
