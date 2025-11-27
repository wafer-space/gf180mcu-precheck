"""Tests for Docker client wrapper."""

import pytest
from unittest.mock import MagicMock, patch

from precheck_server.docker_client import DockerClient


@pytest.fixture
def mock_docker():
    """Create mock Docker client."""
    with patch("precheck_server.docker_client.docker") as mock:
        yield mock


def test_list_precheck_containers(mock_docker):
    """Test listing precheck containers."""
    mock_container = MagicMock()
    mock_container.name = "precheck-abc123"
    mock_container.status = "running"
    mock_docker.from_env.return_value.containers.list.return_value = [mock_container]

    client = DockerClient(container_prefix="precheck-")
    containers = client.list_precheck_containers()

    assert len(containers) == 1
    mock_docker.from_env.return_value.containers.list.assert_called_once_with(
        all=True,
        filters={"name": "precheck-"}
    )


def test_count_running_containers(mock_docker):
    """Test counting running containers."""
    mock_container1 = MagicMock()
    mock_container1.status = "running"
    mock_container2 = MagicMock()
    mock_container2.status = "exited"
    mock_docker.from_env.return_value.containers.list.return_value = [
        mock_container1,
        mock_container2,
    ]

    client = DockerClient(container_prefix="precheck-")
    count = client.count_running()

    assert count == 1


def test_get_container_stats(mock_docker):
    """Test getting container stats."""
    mock_container = MagicMock()
    mock_container.stats.return_value = {
        "read": "2024-01-15T10:30:00Z",
        "cpu_stats": {"cpu_usage": {"total_usage": 100}},
        "memory_stats": {"usage": 1024},
    }
    mock_docker.from_env.return_value.containers.get.return_value = mock_container

    client = DockerClient(container_prefix="precheck-")
    stats = client.get_stats("container-id")

    assert stats["read"] == "2024-01-15T10:30:00Z"
    mock_container.stats.assert_called_once_with(stream=False)


def test_get_container_logs(mock_docker):
    """Test getting container logs."""
    mock_container = MagicMock()
    mock_container.logs.return_value = b"line1\nline2\nline3"
    mock_docker.from_env.return_value.containers.get.return_value = mock_container

    client = DockerClient(container_prefix="precheck-")
    logs = client.get_logs("container-id", since=1000, tail=10, timestamps=True)

    assert logs == "line1\nline2\nline3"
    mock_container.logs.assert_called_once_with(
        stdout=True,
        stderr=True,
        since=1000,
        tail=10,
        timestamps=True,
    )


def test_stop_and_remove_container(mock_docker):
    """Test stopping and removing container."""
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.from_env.return_value.containers.get.return_value = mock_container

    client = DockerClient(container_prefix="precheck-")
    client.stop_and_remove("container-id")

    mock_container.stop.assert_called_once_with(timeout=10)
    mock_container.remove.assert_called_once()
