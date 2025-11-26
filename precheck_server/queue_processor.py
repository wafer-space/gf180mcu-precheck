"""Background queue processor for precheck runs."""

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from precheck_server.database import Database
from precheck_server.docker_client import DockerClient


class QueueProcessor:
    """Processes queued precheck runs."""

    def __init__(
        self,
        db: Database,
        docker: DockerClient,
        max_concurrent: int = 1,
        poll_interval: float = 1.0,
    ):
        self.db = db
        self.docker = docker
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the queue processor."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the queue processor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                await self.process_once()
            except Exception as e:
                # Log error but keep running
                print(f"Queue processor error: {e}")
            await asyncio.sleep(self.poll_interval)

    async def process_once(self) -> None:
        """Process one iteration of the queue."""
        # Check for completed containers
        await self._check_completed()

        # Start new jobs if capacity available
        await self._start_queued()

    async def _check_completed(self) -> None:
        """Check running containers for completion."""
        running_runs = await self.db.get_running_runs()

        for run in running_runs:
            container_id = run.get("ContainerId")
            if not container_id:
                continue

            status = self.docker.get_container_status(container_id)
            if not status:
                # Container disappeared
                await self.db.update_run(
                    run["Id"],
                    status="failed",
                    error="Container disappeared",
                    finished_at=datetime.utcnow().isoformat() + "Z",
                )
                continue

            if status["status"] == "exited":
                # Container finished
                exit_code = status["exit_code"]
                final_status = "completed" if exit_code == 0 else "failed"

                # Compute output checksum if completed successfully
                output_checksums = None
                if final_status == "completed":
                    output_checksums = self._compute_output_checksums(run)

                await self.db.update_run(
                    run["Id"],
                    status=final_status,
                    exit_code=exit_code,
                    error=status.get("error") or None,
                    finished_at=status.get("finished_at") or datetime.utcnow().isoformat() + "Z",
                    output_checksums=output_checksums,
                )

                # Remove container
                self.docker.stop_and_remove(container_id)

    async def _start_queued(self) -> None:
        """Start queued jobs if capacity available."""
        running_count = self.docker.count_running()

        if running_count >= self.max_concurrent:
            return

        # Get next queued job
        run = await self.db.get_next_queued_run()
        if not run:
            return

        # Start container
        try:
            container = self.docker.run_precheck(
                run_id=run["Id"],
                run_dir=run["_run_dir"],
                top_cell=run["Config"]["Labels"]["top_cell"],
                die_id=run["Config"]["Labels"]["die_id"],
            )

            await self.db.update_run(
                run["Id"],
                status="running",
                container_id=container.id,
                started_at=datetime.utcnow().isoformat() + "Z",
            )
        except Exception as e:
            await self.db.update_run(
                run["Id"],
                status="failed",
                error=str(e),
                finished_at=datetime.utcnow().isoformat() + "Z",
            )

    def _compute_output_checksums(self, run: dict) -> Optional[dict]:
        """Compute checksums for output GDS."""
        run_dir = Path(run["_run_dir"])
        top_cell = run["Config"]["Labels"]["top_cell"]

        output_candidates = list(run_dir.glob(f"**/KLayout.GenerateID/{top_cell}.gds"))
        if not output_candidates:
            return None

        output_path = output_candidates[0]
        sha256 = hashlib.sha256()
        with open(output_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        return {"sha256": sha256.hexdigest()}
