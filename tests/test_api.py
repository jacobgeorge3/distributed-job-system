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
