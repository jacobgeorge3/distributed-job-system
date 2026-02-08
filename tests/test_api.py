"""Unit tests for the API service."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Flask test client with mocked Redis."""
    from main import app
    mock_redis = MagicMock()
    with patch("main.r", mock_redis):
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, mock_redis


def test_health_ok(client):
    """GET /health returns 200 when Redis is reachable."""
    c, mock_r = client
    mock_r.ping.return_value = True

    resp = c.get("/health")
    assert resp.status_code == 200


def test_health_redis_down(client):
    """GET /health returns 503 when Redis is unreachable."""
    import redis
    c, mock_r = client
    mock_r.ping.side_effect = redis.ConnectionError("connection refused")

    resp = c.get("/health")
    assert resp.status_code == 503


def test_submit_missing_task(client):
    """POST /submit returns 400 when 'task' field is missing."""
    c, mock_r = client

    resp = c.post("/submit", json={})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Missing 'task' field"}

    resp = c.post("/submit", json={"other": "field"})
    assert resp.status_code == 400


def test_submit_valid(client):
    """POST /submit returns 200 and job id when task is valid."""
    c, mock_r = client

    resp = c.post("/submit", json={"task": "hello world"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "queued"
    assert data["task"] == "hello world"
    assert "id" in data
    # UUID format
    assert len(data["id"]) == 36
    assert data["id"].count("-") == 4
    mock_r.incr.assert_called_once_with("metrics:jobs_submitted")


def test_get_job_not_found(client):
    """GET /jobs/:id returns 404 when job does not exist."""
    c, mock_r = client
    mock_r.exists.return_value = 0

    resp = c.get("/jobs/some-uuid")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Job not found"}


def test_get_job_ok(client):
    """GET /jobs/:id returns 200 with job data when found."""
    c, mock_r = client
    mock_r.exists.return_value = 1
    mock_r.hgetall.return_value = {
        "status": "completed",
        "task": "hello",
        "created_at": "2025-02-03T12:00:00+00:00",
        "result": "done",
        "completed_at": "2025-02-03T12:00:02+00:00",
    }

    resp = c.get("/jobs/some-uuid")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "some-uuid"
    assert data["status"] == "completed"
    assert data["task"] == "hello"
    assert data["result"] == "done"
    assert "completed_at" in data


def test_metrics_ok(client):
    """GET /metrics returns 200 with jobs_submitted, jobs_completed, jobs_failed, queue_depth."""
    c, mock_r = client
    mock_r.get.side_effect = lambda k: {"metrics:jobs_submitted": "10", "metrics:jobs_completed": "8", "metrics:jobs_failed": "1"}.get(k)
    mock_r.llen.return_value = 2

    resp = c.get("/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["jobs_submitted"] == 10
    assert data["jobs_completed"] == 8
    assert data["jobs_failed"] == 1
    assert data["queue_depth"] == 2


def test_metrics_missing_counters(client):
    """GET /metrics returns 0 for counters when Redis keys are missing."""
    c, mock_r = client
    mock_r.get.return_value = None
    mock_r.llen.return_value = 0

    resp = c.get("/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["jobs_submitted"] == 0
    assert data["jobs_completed"] == 0
    assert data["jobs_failed"] == 0
    assert data["queue_depth"] == 0


def test_metrics_redis_down(client):
    """GET /metrics returns 503 when Redis is unreachable."""
    import redis
    c, mock_r = client
    mock_r.get.side_effect = redis.ConnectionError("connection refused")

    resp = c.get("/metrics")
    assert resp.status_code == 503
    assert resp.get_json() == {"error": "Redis unreachable"}
