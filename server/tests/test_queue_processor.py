"""Tests for queue processor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from precheck_server.queue_processor import QueueProcessor
from precheck_server.database import Database
from precheck_server.docker_client import DockerClient


@pytest.fixture
async def db():
    """Create test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.initialize()
        yield db
        await db.close()


@pytest.fixture
def mock_docker():
    """Create mock Docker client."""
    docker = MagicMock(spec=DockerClient)
    docker.count_running.return_value = 0
    return docker


async def test_processor_starts_queued_job(db, mock_docker):
    """Test that processor starts a queued job when capacity available."""
    # Create a queued run
    await db.create_upload("u1", "test.gds", "/path", 100, {"sha256": "abc"})
    await db.create_run("run-1", "u1", "chip", "ID", "/runs/run-1")

    # Mock container creation
    mock_container = MagicMock()
    mock_container.id = "container-123"
    mock_docker.run_precheck.return_value = mock_container

    processor = QueueProcessor(db, mock_docker, max_concurrent=1)
    await processor.process_once()

    # Verify container was started
    mock_docker.run_precheck.assert_called_once()

    # Verify run status updated
    run = await db.get_run("run-1")
    assert run["State"]["Status"] == "running"
    assert run["ContainerId"] == "container-123"


async def test_processor_respects_concurrency_limit(db, mock_docker):
    """Test that processor doesn't exceed max concurrent."""
    await db.create_upload("u1", "test.gds", "/path", 100, {"sha256": "abc"})
    await db.create_run("run-1", "u1", "chip", "ID", "/runs/run-1")

    # Simulate max concurrent already reached
    mock_docker.count_running.return_value = 1

    processor = QueueProcessor(db, mock_docker, max_concurrent=1)
    await processor.process_once()

    # Should not start new container
    mock_docker.run_precheck.assert_not_called()


async def test_processor_detects_completed_container(db, mock_docker):
    """Test that processor detects and updates completed runs."""
    await db.create_upload("u1", "test.gds", "/path", 100, {"sha256": "abc"})
    await db.create_run("run-1", "u1", "chip", "ID", "/runs/run-1")
    await db.update_run("run-1", status="running", container_id="container-123")

    # Mock container as exited
    mock_docker.get_container_status.return_value = {
        "status": "exited",
        "running": False,
        "exit_code": 0,
        "error": "",
        "finished_at": "2024-01-15T10:35:00Z",
    }
    mock_docker.get_logs.return_value = "log output"
    mock_docker.stop_and_remove.return_value = True

    processor = QueueProcessor(db, mock_docker, max_concurrent=1)
    await processor.process_once()

    # Verify run status updated
    run = await db.get_run("run-1")
    assert run["State"]["Status"] == "completed"
    assert run["State"]["ExitCode"] == 0
