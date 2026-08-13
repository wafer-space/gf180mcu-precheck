"""Docker client wrapper for container management."""

from typing import Any, Dict, List, Optional

import docker
from docker.models.containers import Container


class DockerClient:
    """Wrapper around Docker SDK for precheck container management."""

    def __init__(
        self,
        container_prefix: str = "precheck-",
        image: str = "ghcr.io/wafer-space/gf180mcu-precheck:latest",
    ):
        self.container_prefix = container_prefix
        self.image = image
        self._client = docker.from_env()

    def list_precheck_containers(self) -> List[Container]:
        """List all containers with the precheck prefix."""
        return self._client.containers.list(
            all=True,
            filters={"name": self.container_prefix},
        )

    def count_running(self) -> int:
        """Count running precheck containers."""
        containers = self.list_precheck_containers()
        return sum(1 for c in containers if c.status == "running")

    def run_precheck(
        self,
        run_id: str,
        run_dir: str,
        top_cell: str,
        die_id: str,
    ) -> Container:
        """Start a precheck container."""
        container = self._client.containers.run(
            image=self.image,
            name=f"{self.container_prefix}{run_id}",
            detach=True,
            volumes={
                run_dir: {"bind": "/workdir", "mode": "rw"},
            },
            command=[
                "python",
                "precheck.py",
                "--input",
                "/workdir/input.gds",
                "--top",
                top_cell,
                "--id",
                die_id,
                "--dir",
                "/workdir",
            ],
        )
        return container

    def get_container(self, container_id: str) -> Optional[Container]:
        """Get container by ID."""
        try:
            return self._client.containers.get(container_id)
        except docker.errors.NotFound:
            return None

    def get_container_status(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container status and exit info."""
        container = self.get_container(container_id)
        if not container:
            return None

        container.reload()
        state = container.attrs.get("State", {})
        return {
            "status": container.status,
            "running": state.get("Running", False),
            "exit_code": state.get("ExitCode", 0),
            "error": state.get("Error", ""),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
        }

    def get_stats(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container resource stats."""
        container = self.get_container(container_id)
        if not container:
            return None

        try:
            return container.stats(stream=False)
        except docker.errors.APIError:
            return None

    def get_logs(
        self,
        container_id: str,
        since: Optional[int] = None,
        tail: Optional[int] = None,
        timestamps: bool = False,
    ) -> Optional[str]:
        """Get container logs."""
        container = self.get_container(container_id)
        if not container:
            return None

        kwargs = {
            "stdout": True,
            "stderr": True,
            "timestamps": timestamps,
        }
        if since is not None:
            kwargs["since"] = since
        if tail is not None:
            kwargs["tail"] = tail

        logs = container.logs(**kwargs)
        return logs.decode("utf-8") if isinstance(logs, bytes) else logs

    def stop_and_remove(self, container_id: str, timeout: int = 10) -> bool:
        """Stop and remove a container."""
        container = self.get_container(container_id)
        if not container:
            return False

        try:
            if container.status == "running":
                container.stop(timeout=timeout)
            container.remove()
            return True
        except docker.errors.APIError:
            return False

    def cleanup_orphans(self) -> List[str]:
        """Remove all precheck containers (orphan cleanup)."""
        removed = []
        for container in self.list_precheck_containers():
            try:
                if container.status == "running":
                    container.stop(timeout=10)
                container.remove()
                removed.append(container.name)
            except docker.errors.APIError:
                pass
        return removed

    def has_orphans(self) -> List[str]:
        """Check for orphaned containers."""
        return [c.name for c in self.list_precheck_containers()]
