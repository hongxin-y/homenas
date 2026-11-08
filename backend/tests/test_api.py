import os

os.environ["HOMENAS_ADMIN_PASSWORD"] = "test-password"

from fastapi.testclient import TestClient

from homenas.main import app


def test_health_is_public_and_dashboard_requires_login():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert client.get("/api/overview").status_code == 401


def test_login_and_overview():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"})
        assert response.status_code == 200
        assert "homenas_session" in response.cookies
        overview = client.get("/api/overview")
        assert overview.status_code == 200
        data = overview.json()
        assert "system" in data and "storage" in data and "network" in data


def test_wrong_password_does_not_login():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401

