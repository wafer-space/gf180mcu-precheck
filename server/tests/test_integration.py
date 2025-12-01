"""Integration tests for full workflow."""

import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

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
                upload_expiry_minutes=60,
            ),
            docker=DockerConfig(
                image="test-image:latest",
                container_prefix="test-precheck-",
            ),
            auth=AuthConfig(required=False),
        )


@pytest.fixture
async def client(test_config):
    """Create test client with mocked Docker."""
    with patch("precheck_server.app.DockerClient") as mock_docker_class:
        mock_docker = MagicMock()
        mock_docker.count_running.return_value = 0
        mock_docker.has_orphans.return_value = []
        mock_docker_class.return_value = mock_docker

        app = create_app(test_config)

        # Manually trigger lifespan startup
        async with app.router.lifespan_context(app):
            # Use AsyncClient which properly triggers lifespan events
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client


async def test_full_workflow(client, test_config):
    """Test complete upload -> precheck -> status workflow."""
    # 1. Upload a file
    test_content = b"GDS file content"
    response = await client.post(
        "/api/v1/uploads",
        files={"file": ("test.gds", test_content, "application/octet-stream")},
    )
    assert response.status_code == 200
    upload = response.json()
    assert upload["Name"] == "test.gds"
    assert upload["Size"] == len(test_content)
    upload_id = upload["Id"]

    # 2. Create precheck run
    response = await client.post(
        "/api/v1/prechecks",
        json={
            "upload_id": upload_id,
            "top_cell": "chip_top",
            "die_id": "TEST1234",
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["State"]["Status"] == "queued"
    assert run["Config"]["Labels"]["top_cell"] == "chip_top"
    run_id = run["Id"]

    # 3. Check queue status
    response = await client.get("/api/v1/queue")
    assert response.status_code == 200
    queue = response.json()
    assert queue["queued"] >= 1

    # 4. Get run status
    response = await client.get(f"/api/v1/prechecks/{run_id}")
    assert response.status_code == 200
    run = response.json()
    assert run["Queue"]["Position"] == 1

    # 5. List runs
    response = await client.get("/api/v1/prechecks")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) >= 1

    # 6. Cancel run
    response = await client.delete(f"/api/v1/prechecks/{run_id}")
    assert response.status_code == 200

    # 7. Verify cancelled
    response = await client.get(f"/api/v1/prechecks/{run_id}")
    run = response.json()
    assert run["State"]["Status"] == "cancelled"


async def test_upload_not_found(client):
    """Test creating precheck with nonexistent upload."""
    response = await client.post(
        "/api/v1/prechecks",
        json={
            "upload_id": "nonexistent",
            "top_cell": "chip",
        },
    )
    assert response.status_code == 404
    assert "No such upload" in response.json()["detail"]


async def test_run_not_found(client):
    """Test getting nonexistent run."""
    response = await client.get("/api/v1/prechecks/nonexistent")
    assert response.status_code == 404
