"""Tests for the healthy-app Flask routes that don't require a database."""

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    """Provide a Flask test client. No real network or DB."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def test_root_returns_200(client):
    """The root route should respond with HTTP 200."""
    response = client.get("/")
    assert response.status_code == 200


def test_root_contains_hostname(client):
    """The root route should include 'Hello from container' in its body."""
    response = client.get("/")
    assert b"Hello from container" in response.data


def test_unknown_route_returns_404(client):
    """Flask should 404 a route that doesn't exist."""
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
