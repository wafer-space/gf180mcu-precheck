"""SQLite database operations."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

# Type aliases for Docker-style responses
UploadRecord = Dict[str, Any]
RunRecord = Dict[str, Any]


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path, upload_expiry_minutes: int = 15):
        self.db_path = db_path
        self.upload_expiry_minutes = upload_expiry_minutes
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Initialize database and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Delete existing database (ephemeral on restart)
        if self.db_path.exists():
            self.db_path.unlink()

        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.executescript(
            """
            CREATE TABLE uploads (
                Id TEXT PRIMARY KEY,
                Name TEXT NOT NULL,
                Filepath TEXT NOT NULL,
                Size INTEGER NOT NULL,
                Checksums TEXT NOT NULL,
                Created TEXT NOT NULL,
                ExpiresAt TEXT NOT NULL
            );

            CREATE TABLE runs (
                Id TEXT PRIMARY KEY,
                UploadId TEXT NOT NULL,
                TopCell TEXT NOT NULL,
                DieId TEXT NOT NULL DEFAULT 'FFFFFFFF',
                Status TEXT NOT NULL DEFAULT 'queued',
                ContainerId TEXT,
                RunDir TEXT,
                Created TEXT NOT NULL,
                StartedAt TEXT,
                FinishedAt TEXT,
                ExitCode INTEGER,
                Error TEXT,
                InputChecksums TEXT,
                OutputChecksums TEXT,
                FOREIGN KEY (UploadId) REFERENCES uploads(Id)
            );

            CREATE INDEX idx_runs_status ON runs(Status);
            CREATE INDEX idx_runs_created ON runs(Created);
            CREATE INDEX idx_uploads_expires ON uploads(ExpiresAt);
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _now_iso(self) -> str:
        """Get current UTC time in ISO format."""
        return datetime.utcnow().isoformat() + "Z"

    # Upload operations

    async def create_upload(
        self,
        id: str,
        name: str,
        filepath: str,
        size: int,
        checksums: Dict[str, str],
    ) -> UploadRecord:
        """Create a new upload record."""
        now = self._now_iso()
        expires = (
            datetime.utcnow() + timedelta(minutes=self.upload_expiry_minutes)
        ).isoformat() + "Z"

        await self._conn.execute(
            """
            INSERT INTO uploads (Id, Name, Filepath, Size, Checksums, Created, ExpiresAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, name, filepath, size, json.dumps(checksums), now, expires),
        )
        await self._conn.commit()

        return {
            "Id": id,
            "Name": name,
            "Created": now,
            "Size": size,
            "Checksums": checksums,
            "ExpiresAt": expires,
            "State": {"Status": "available", "Expired": False},
        }

    async def get_upload(self, id: str) -> Optional[UploadRecord]:
        """Get upload by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM uploads WHERE Id = ?", (id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        now = datetime.utcnow()
        expires_at = datetime.fromisoformat(row["ExpiresAt"].rstrip("Z"))
        expired = now > expires_at

        return {
            "Id": row["Id"],
            "Name": row["Name"],
            "Created": row["Created"],
            "Size": row["Size"],
            "Checksums": json.loads(row["Checksums"]),
            "ExpiresAt": row["ExpiresAt"],
            "State": {"Status": "expired" if expired else "available", "Expired": expired},
            "_filepath": row["Filepath"],  # Internal use
        }

    async def list_uploads(self) -> List[UploadRecord]:
        """List all uploads."""
        cursor = await self._conn.execute("SELECT * FROM uploads ORDER BY Created DESC")
        rows = await cursor.fetchall()

        results = []
        now = datetime.utcnow()
        for row in rows:
            expires_at = datetime.fromisoformat(row["ExpiresAt"].rstrip("Z"))
            expired = now > expires_at
            results.append({
                "Id": row["Id"],
                "Name": row["Name"],
                "Created": row["Created"],
                "Size": row["Size"],
                "Checksums": json.loads(row["Checksums"]),
                "ExpiresAt": row["ExpiresAt"],
                "State": {"Status": "expired" if expired else "available", "Expired": expired},
            })
        return results

    async def delete_upload(self, id: str) -> bool:
        """Delete an upload."""
        cursor = await self._conn.execute("DELETE FROM uploads WHERE Id = ?", (id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_expired_uploads(self) -> List[UploadRecord]:
        """Get uploads that have expired and have no associated runs."""
        now = self._now_iso()
        cursor = await self._conn.execute(
            """
            SELECT u.* FROM uploads u
            LEFT JOIN runs r ON u.Id = r.UploadId
            WHERE u.ExpiresAt < ? AND r.Id IS NULL
            """,
            (now,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "Id": row["Id"],
                "Name": row["Name"],
                "Filepath": row["Filepath"],
            }
            for row in rows
        ]

    # Run operations

    async def create_run(
        self,
        id: str,
        upload_id: str,
        top_cell: str,
        die_id: str,
        run_dir: str,
    ) -> RunRecord:
        """Create a new precheck run."""
        now = self._now_iso()

        # Get upload checksums for input reference
        upload = await self.get_upload(upload_id)
        input_checksums = json.dumps(upload["Checksums"]) if upload else "{}"

        await self._conn.execute(
            """
            INSERT INTO runs (Id, UploadId, TopCell, DieId, RunDir, Created, InputChecksums, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
            """,
            (id, upload_id, top_cell, die_id, run_dir, now, input_checksums),
        )
        await self._conn.commit()

        queue_pos = await self.get_queue_position(id)

        return self._build_run_response(
            id=id,
            upload_id=upload_id,
            top_cell=top_cell,
            die_id=die_id,
            run_dir=run_dir,
            status="queued",
            created=now,
            input_checksums=json.loads(input_checksums),
            queue_position=queue_pos,
        )

    async def get_run(self, id: str) -> Optional[RunRecord]:
        """Get run by ID."""
        cursor = await self._conn.execute("SELECT * FROM runs WHERE Id = ?", (id,))
        row = await cursor.fetchone()
        if not row:
            return None

        queue_pos = None
        if row["Status"] == "queued":
            queue_pos = await self.get_queue_position(id)

        return self._build_run_response(
            id=row["Id"],
            upload_id=row["UploadId"],
            top_cell=row["TopCell"],
            die_id=row["DieId"],
            run_dir=row["RunDir"],
            status=row["Status"],
            created=row["Created"],
            started_at=row["StartedAt"],
            finished_at=row["FinishedAt"],
            exit_code=row["ExitCode"],
            error=row["Error"],
            container_id=row["ContainerId"],
            input_checksums=json.loads(row["InputChecksums"] or "{}"),
            output_checksums=json.loads(row["OutputChecksums"] or "{}") if row["OutputChecksums"] else None,
            queue_position=queue_pos,
        )

    async def list_runs(self, status: Optional[List[str]] = None) -> List[RunRecord]:
        """List runs, optionally filtered by status."""
        if status:
            placeholders = ",".join("?" * len(status))
            cursor = await self._conn.execute(
                f"SELECT * FROM runs WHERE Status IN ({placeholders}) ORDER BY Created DESC",
                status,
            )
        else:
            cursor = await self._conn.execute("SELECT * FROM runs ORDER BY Created DESC")

        rows = await cursor.fetchall()
        results = []
        for row in rows:
            queue_pos = None
            if row["Status"] == "queued":
                queue_pos = await self.get_queue_position(row["Id"])
            results.append(
                self._build_run_response(
                    id=row["Id"],
                    upload_id=row["UploadId"],
                    top_cell=row["TopCell"],
                    die_id=row["DieId"],
                    run_dir=row["RunDir"],
                    status=row["Status"],
                    created=row["Created"],
                    started_at=row["StartedAt"],
                    finished_at=row["FinishedAt"],
                    exit_code=row["ExitCode"],
                    error=row["Error"],
                    container_id=row["ContainerId"],
                    input_checksums=json.loads(row["InputChecksums"] or "{}"),
                    queue_position=queue_pos,
                )
            )
        return results

    async def update_run(
        self,
        id: str,
        status: Optional[str] = None,
        container_id: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        exit_code: Optional[int] = None,
        error: Optional[str] = None,
        output_checksums: Optional[Dict[str, str]] = None,
    ) -> None:
        """Update run fields."""
        updates = []
        params = []

        if status is not None:
            updates.append("Status = ?")
            params.append(status)
        if container_id is not None:
            updates.append("ContainerId = ?")
            params.append(container_id)
        if started_at is not None:
            updates.append("StartedAt = ?")
            params.append(started_at)
        if finished_at is not None:
            updates.append("FinishedAt = ?")
            params.append(finished_at)
        if exit_code is not None:
            updates.append("ExitCode = ?")
            params.append(exit_code)
        if error is not None:
            updates.append("Error = ?")
            params.append(error)
        if output_checksums is not None:
            updates.append("OutputChecksums = ?")
            params.append(json.dumps(output_checksums))

        if updates:
            params.append(id)
            await self._conn.execute(
                f"UPDATE runs SET {', '.join(updates)} WHERE Id = ?",
                params,
            )
            await self._conn.commit()

    async def delete_run(self, id: str) -> bool:
        """Delete a run."""
        cursor = await self._conn.execute("DELETE FROM runs WHERE Id = ?", (id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_next_queued_run(self) -> Optional[RunRecord]:
        """Get the next queued run (FIFO)."""
        cursor = await self._conn.execute(
            "SELECT * FROM runs WHERE Status = 'queued' ORDER BY Created ASC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None

        return self._build_run_response(
            id=row["Id"],
            upload_id=row["UploadId"],
            top_cell=row["TopCell"],
            die_id=row["DieId"],
            run_dir=row["RunDir"],
            status=row["Status"],
            created=row["Created"],
            input_checksums=json.loads(row["InputChecksums"] or "{}"),
            queue_position=1,
        )

    async def get_running_runs(self) -> List[RunRecord]:
        """Get all currently running runs."""
        return await self.list_runs(status=["running"])

    async def get_queue_position(self, id: str) -> Optional[int]:
        """Get queue position for a run (1-indexed)."""
        cursor = await self._conn.execute(
            """
            SELECT COUNT(*) + 1 as position FROM runs
            WHERE Status = 'queued'
            AND Created < (SELECT Created FROM runs WHERE Id = ?)
            """,
            (id,),
        )
        row = await cursor.fetchone()
        return row["position"] if row else None

    async def get_queue_length(self) -> int:
        """Get total number of queued runs."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*) as count FROM runs WHERE Status = 'queued'"
        )
        row = await cursor.fetchone()
        return row["count"]

    def _build_run_response(
        self,
        id: str,
        upload_id: str,
        top_cell: str,
        die_id: str,
        run_dir: str,
        status: str,
        created: str,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        exit_code: Optional[int] = None,
        error: Optional[str] = None,
        container_id: Optional[str] = None,
        input_checksums: Optional[Dict[str, str]] = None,
        output_checksums: Optional[Dict[str, str]] = None,
        queue_position: Optional[int] = None,
    ) -> RunRecord:
        """Build Docker-style run response."""
        is_running = status == "running"
        is_queued = status == "queued"

        response = {
            "Id": id,
            "Name": f"precheck-{id}",
            "Created": created,
            "State": {
                "Status": status,
                "Running": is_running,
                "Paused": False,
                "StartedAt": started_at or "0001-01-01T00:00:00Z",
                "FinishedAt": finished_at or "0001-01-01T00:00:00Z",
                "ExitCode": exit_code if exit_code is not None else 0,
                "Error": error or "",
            },
            "Config": {
                "Labels": {
                    "upload_id": upload_id,
                    "top_cell": top_cell,
                    "die_id": die_id,
                },
            },
            "HostConfig": {
                "Binds": [f"{run_dir}:/workdir:rw"],
            },
            "Queue": {
                "Position": queue_position if is_queued else None,
                "Length": 0,  # Filled by caller if needed
            },
        }

        if container_id:
            response["ContainerId"] = container_id

        if input_checksums:
            response["Input"] = {"Checksums": input_checksums}

        if output_checksums:
            response["Output"] = {
                "Available": True,
                "Checksums": output_checksums,
            }

        response["_run_dir"] = run_dir  # Internal use

        return response
