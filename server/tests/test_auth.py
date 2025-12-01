"""Tests for authentication middleware."""

import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from precheck_server.app import create_app
from precheck_server.config import Config, ServerConfig, DockerConfig, AuthConfig, ApiKey


@pytest.fixture
def auth_config():
    """Create config with auth enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Config(
            server=ServerConfig(
                host="127.0.0.1",
                port=8000,
                storage_path=Path(tmpdir),
            ),
            docker=DockerConfig(image="test:latest"),
            auth=AuthConfig(
                required=True,
                api_keys=[
                    ApiKey(name="test-key", key="ws_key_test123"),
                ],
                allowed_ips=["127.0.0.1"],
            ),
        )


@pytest.fixture
async def auth_client(auth_config):
    """Create client with auth-enabled app."""
    # Mock DockerClient to avoid needing real Docker
    with patch("precheck_server.app.DockerClient") as MockDockerClient:
        mock_docker = Mock()
        mock_docker.count_running.return_value = 0
        MockDockerClient.return_value = mock_docker

        app = create_app(auth_config)

        # Manually trigger lifespan startup
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client


async def test_request_without_auth_rejected(auth_client):
    """Test that requests without auth are rejected."""
    response = await auth_client.get("/api/v1/queue")
    assert response.status_code == 401
    assert "API key required" in response.json()["message"]


async def test_request_with_valid_key_allowed(auth_client):
    """Test that requests with valid API key succeed."""
    response = await auth_client.get(
        "/api/v1/queue",
        headers={"Authorization": "Bearer ws_key_test123"},
    )
    assert response.status_code == 200


async def test_request_with_invalid_key_rejected(auth_client):
    """Test that requests with invalid API key are rejected."""
    response = await auth_client.get(
        "/api/v1/queue",
        headers={"Authorization": "Bearer ws_key_wrong"},
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["message"]


async def test_health_endpoint_bypasses_auth(auth_client):
    """Test that health check doesn't require auth."""
    response = await auth_client.get("/health")
    assert response.status_code == 200


async def test_docs_endpoint_bypasses_auth(auth_client):
    """Test that docs endpoint doesn't require auth."""
    response = await auth_client.get("/docs")
    assert response.status_code == 200


async def test_openapi_endpoint_bypasses_auth(auth_client):
    """Test that openapi.json doesn't require auth."""
    response = await auth_client.get("/openapi.json")
    assert response.status_code == 200


async def test_redoc_endpoint_bypasses_auth(auth_client):
    """Test that redoc doesn't require auth."""
    response = await auth_client.get("/redoc")
    assert response.status_code == 200


async def test_api_key_from_x_api_key_header(auth_client):
    """Test that API key can be provided via X-API-Key header."""
    response = await auth_client.get(
        "/api/v1/queue",
        headers={"X-API-Key": "ws_key_test123"},
    )
    assert response.status_code == 200


@pytest.fixture
def ip_restricted_config():
    """Create config with IP restrictions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Config(
            server=ServerConfig(
                host="127.0.0.1",
                port=8000,
                storage_path=Path(tmpdir),
            ),
            docker=DockerConfig(image="test:latest"),
            auth=AuthConfig(
                required=True,
                api_keys=[
                    ApiKey(name="test-key", key="ws_key_test123"),
                ],
                allowed_ips=["192.168.1.0/24"],  # Different subnet
            ),
        )


@pytest.fixture
async def ip_restricted_client(ip_restricted_config):
    """Create client with IP-restricted app."""
    # Mock DockerClient to avoid needing real Docker
    with patch("precheck_server.app.DockerClient") as MockDockerClient:
        mock_docker = Mock()
        mock_docker.count_running.return_value = 0
        MockDockerClient.return_value = mock_docker

        app = create_app(ip_restricted_config)

        # Manually trigger lifespan startup
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client


async def test_ip_restriction_blocks_unauthorized_ip(ip_restricted_client):
    """Test that requests from non-allowed IPs are blocked."""
    # The test client will have IP 127.0.0.1 which is not in 192.168.1.0/24
    response = await ip_restricted_client.get(
        "/api/v1/queue",
        headers={"Authorization": "Bearer ws_key_test123"},
    )
    assert response.status_code == 403
    assert "not allowed" in response.json()["message"]


@pytest.fixture
def no_ip_restriction_config():
    """Create config without IP restrictions (empty list)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Config(
            server=ServerConfig(
                host="127.0.0.1",
                port=8000,
                storage_path=Path(tmpdir),
            ),
            docker=DockerConfig(image="test:latest"),
            auth=AuthConfig(
                required=True,
                api_keys=[
                    ApiKey(name="test-key", key="ws_key_test123"),
                ],
                allowed_ips=[],  # Empty = allow all IPs
            ),
        )


@pytest.fixture
async def no_ip_restriction_client(no_ip_restriction_config):
    """Create client without IP restrictions."""
    # Mock DockerClient to avoid needing real Docker
    with patch("precheck_server.app.DockerClient") as MockDockerClient:
        mock_docker = Mock()
        mock_docker.count_running.return_value = 0
        MockDockerClient.return_value = mock_docker

        app = create_app(no_ip_restriction_config)

        # Manually trigger lifespan startup
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client


async def test_empty_ip_list_allows_all_ips(no_ip_restriction_client):
    """Test that empty allowed_ips list allows all IPs."""
    response = await no_ip_restriction_client.get(
        "/api/v1/queue",
        headers={"Authorization": "Bearer ws_key_test123"},
    )
    assert response.status_code == 200
