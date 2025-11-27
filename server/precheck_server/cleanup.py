"""Background cleanup tasks."""

import asyncio
import shutil
from pathlib import Path
from typing import List, Optional

from precheck_server.database import Database


class UploadCleanup:
    """Cleans up expired uploads."""

    def __init__(
        self,
        db: Database,
        uploads_dir: Path,
        poll_interval: float = 60.0,
    ):
        self.db = db
        self.uploads_dir = uploads_dir
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start cleanup background task."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop cleanup background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Main cleanup loop."""
        while self._running:
            try:
                await self.cleanup_once()
            except Exception as e:
                print(f"Cleanup error: {e}")
            await asyncio.sleep(self.poll_interval)

    async def cleanup_once(self) -> List[str]:
        """Run one cleanup iteration."""
        removed = []
        expired = await self.db.get_expired_uploads()

        for upload in expired:
            upload_id = upload["Id"]
            upload_dir = self.uploads_dir / upload_id

            # Remove files
            if upload_dir.exists():
                shutil.rmtree(upload_dir)

            # Remove from database
            await self.db.delete_upload(upload_id)
            removed.append(upload_id)

        return removed
