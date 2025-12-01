"""Tests for FastAPI application."""

import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from precheck_server.app import create_app
from precheck_server.config import Config, ServerConfig, DockerConfig, AuthConfig


@pytest.fixture
def test_config():
    """Create test configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Config(
            server=ServerConfig(
                host="127.0.0.1",
                port=8000,
                storage_path=Path(tmpdir),
                max_concurrent=1,
                upload_expiry_minutes=15,
            ),
            docker=DockerConfig(
                image="test-image:latest",
                container_prefix="test-precheck-",
            ),
            auth=AuthConfig(required=False),
        )


@pytest.fixture
async def client(test_config):
    """Create test client."""
    # Mock DockerClient to avoid needing real Docker
    with patch("precheck_server.app.DockerClient") as MockDockerClient:
        mock_docker = Mock()
        mock_docker.count_running.return_value = 0
        MockDockerClient.return_value = mock_docker

        app = create_app(test_config)

        # Manually trigger lifespan startup
        async with app.router.lifespan_context(app):
            # Use AsyncClient which properly triggers lifespan events
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client


async def test_health_check(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


async def test_queue_status(client):
    """Test queue status endpoint."""
    response = await client.get("/api/v1/queue")
    assert response.status_code == 200
    data = response.json()
    assert "queued" in data
    assert "running" in data
    assert "max_concurrent" in data
