# Precheck API Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a FastAPI server that manages GDS/OAS file uploads and precheck runs via Docker containers.

**Architecture:** Poll-based queue using SQLite for state and Docker API for container lifecycle, logs, and stats. API shape mirrors Docker API conventions.

**Tech Stack:** FastAPI, uvicorn, docker-py, click, tomli, aiosqlite, pydantic

---

## Task 1: Project Structure and Dependencies

**Files:**
- Create: `precheck_server/__init__.py`
- Create: `precheck_server/__main__.py`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml with dependencies**

```toml
[project]
name = "precheck-server"
version = "0.1.0"
description = "API server for gf180mcu precheck runs"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "docker>=7.0.0",
    "click>=8.1.0",
    "tomli>=2.0.0",
    "aiosqlite>=0.19.0",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
]

[project.scripts]
precheck-server = "precheck_server.__main__:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create package structure**

```python
# precheck_server/__init__.py
"""Precheck API Server for gf180mcu."""

__version__ = "0.1.0"
```

```python
# precheck_server/__main__.py
"""CLI entry point."""

import click


@click.group()
def cli():
    """Precheck server management CLI."""
    pass


@cli.command()
def serve():
    """Start the API server."""
    click.echo("Server not implemented yet")


if __name__ == "__main__":
    cli()
```

```python
# tests/__init__.py
"""Tests for precheck_server."""
```

```python
# tests/conftest.py
"""Pytest fixtures for precheck_server tests."""

import pytest
```

**Step 3: Verify package installs**

Run: `cd .worktrees/api-server && uv pip install -e ".[dev]"`
Expected: Successfully installed precheck-server and dependencies

**Step 4: Verify CLI entry point works**

Run: `cd .worktrees/api-server && uv run precheck-server serve`
Expected: "Server not implemented yet"

**Step 5: Commit**

```bash
cd .worktrees/api-server
git add pyproject.toml precheck_server/ tests/
git commit -m "feat: initial project structure and dependencies"
```

---

## Task 2: Configuration Module

**Files:**
- Create: `precheck_server/config.py`
- Create: `tests/test_config.py`
- Create: `config.example.toml`

**Step 1: Write failing test for config loading**

```python
# tests/test_config.py
"""Tests for configuration loading."""

import pytest
from pathlib import Path
import tempfile

from precheck_server.config import load_config, Config, AuthConfig, ApiKey


def test_load_config_minimal():
    """Test loading a minimal valid config."""
    config_content = """
[server]
host = "127.0.0.1"
port = 8080

[docker]
image = "ghcr.io/wafer-space/gf180mcu-precheck:latest"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8080
    assert config.server.storage_path == Path("./data")  # default
    assert config.server.max_concurrent == 1  # default
    assert config.server.upload_expiry_minutes == 15  # default
    assert config.docker.image == "ghcr.io/wafer-space/gf180mcu-precheck:latest"
    assert config.docker.container_prefix == "precheck-"  # default


def test_load_config_with_auth():
    """Test loading config with API keys and IP restrictions."""
    config_content = """
[server]
host = "0.0.0.0"
port = 8000
storage_path = "/var/data"
max_concurrent = 2

[docker]
image = "myimage:latest"

[auth]
required = true
allowed_ips = ["192.168.1.0/24", "10.0.0.5"]

[[auth.api_keys]]
name = "ci-server"
key = "ws_key_abc123"

[[auth.api_keys]]
name = "developer"
key = "ws_key_xyz789"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.auth.required is True
    assert config.auth.allowed_ips == ["192.168.1.0/24", "10.0.0.5"]
    assert len(config.auth.api_keys) == 2
    assert config.auth.api_keys[0].name == "ci-server"
    assert config.auth.api_keys[0].key == "ws_key_abc123"


def test_load_config_expands_env_vars(monkeypatch):
    """Test that environment variables in keys are expanded."""
    monkeypatch.setenv("TEST_API_KEY", "ws_key_from_env")
    config_content = """
[server]
host = "0.0.0.0"
port = 8000

[docker]
image = "myimage:latest"

[[auth.api_keys]]
name = "from-env"
key = "${TEST_API_KEY}"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.auth.api_keys[0].key == "ws_key_from_env"


def test_load_config_missing_file():
    """Test that missing config file raises error."""
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.toml"))
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/api-server && uv run pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'precheck_server.config'"

**Step 3: Implement config module**

```python
# precheck_server/config.py
"""Configuration loading and validation."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import tomli


@dataclass
class ServerConfig:
    """Server configuration."""

    host: str
    port: int
    storage_path: Path = field(default_factory=lambda: Path("./data"))
    max_concurrent: int = 1
    upload_expiry_minutes: int = 15


@dataclass
class DockerConfig:
    """Docker configuration."""

    image: str
    container_prefix: str = "precheck-"


@dataclass
class ApiKey:
    """API key configuration."""

    name: str
    key: str


@dataclass
class AuthConfig:
    """Authentication configuration."""

    required: bool = False
    allowed_ips: List[str] = field(default_factory=list)
    api_keys: List[ApiKey] = field(default_factory=list)


@dataclass
class Config:
    """Root configuration."""

    server: ServerConfig
    docker: DockerConfig
    auth: AuthConfig = field(default_factory=AuthConfig)


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} patterns in string values."""
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return pattern.sub(replacer, value)


def load_config(path: Path) -> Config:
    """Load configuration from TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        data = tomli.load(f)

    # Parse server config
    server_data = data.get("server", {})
    server = ServerConfig(
        host=server_data.get("host", "0.0.0.0"),
        port=server_data.get("port", 8000),
        storage_path=Path(server_data.get("storage_path", "./data")),
        max_concurrent=server_data.get("max_concurrent", 1),
        upload_expiry_minutes=server_data.get("upload_expiry_minutes", 15),
    )

    # Parse docker config
    docker_data = data.get("docker", {})
    docker = DockerConfig(
        image=docker_data.get("image", "ghcr.io/wafer-space/gf180mcu-precheck:latest"),
        container_prefix=docker_data.get("container_prefix", "precheck-"),
    )

    # Parse auth config
    auth_data = data.get("auth", {})
    api_keys = []
    for key_data in auth_data.get("api_keys", []):
        api_keys.append(
            ApiKey(
                name=key_data.get("name", ""),
                key=_expand_env_vars(key_data.get("key", "")),
            )
        )

    auth = AuthConfig(
        required=auth_data.get("required", False),
        allowed_ips=auth_data.get("allowed_ips", []),
        api_keys=api_keys,
    )

    return Config(server=server, docker=docker, auth=auth)
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/api-server && uv run pytest tests/test_config.py -v`
Expected: 4 passed

**Step 5: Create example config**

```toml
# config.example.toml
# Example configuration for precheck API server

[server]
host = "0.0.0.0"
port = 8000
storage_path = "./data"
max_concurrent = 1
upload_expiry_minutes = 15

[docker]
image = "ghcr.io/wafer-space/gf180mcu-precheck:latest"
container_prefix = "precheck-"

[auth]
# Set to true to require API key authentication
required = false

# IP allowlist (empty = allow all)
# allowed_ips = ["192.168.1.0/24", "10.0.0.5"]

# API keys (can use ${ENV_VAR} syntax)
# [[auth.api_keys]]
# name = "ci-server"
# key = "ws_key_abc123..."
#
# [[auth.api_keys]]
# name = "from-env"
# key = "${PRECHECK_API_KEY}"
```

**Step 6: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/config.py tests/test_config.py config.example.toml
git commit -m "feat: add configuration module with TOML loading"
```

---

## Task 3: Database Module

**Files:**
- Create: `precheck_server/database.py`
- Create: `tests/test_database.py`

**Step 1: Write failing tests for database operations**

```python
# tests/test_database.py
"""Tests for database operations."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from precheck_server.database import Database


@pytest.fixture
async def db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.initialize()
        yield db
        await db.close()


async def test_create_upload(db):
    """Test creating an upload record."""
    upload = await db.create_upload(
        id="test-upload-id",
        name="chip.gds",
        filepath="/data/uploads/test-upload-id/input.gds",
        size=1024,
        checksums={"sha256": "abc123"},
    )

    assert upload["Id"] == "test-upload-id"
    assert upload["Name"] == "chip.gds"
    assert upload["Size"] == 1024
    assert "Created" in upload
    assert "ExpiresAt" in upload


async def test_get_upload(db):
    """Test retrieving an upload by ID."""
    await db.create_upload(
        id="test-id",
        name="chip.gds",
        filepath="/path/to/file",
        size=1024,
        checksums={"sha256": "abc"},
    )

    upload = await db.get_upload("test-id")
    assert upload is not None
    assert upload["Id"] == "test-id"

    missing = await db.get_upload("nonexistent")
    assert missing is None


async def test_list_uploads(db):
    """Test listing uploads."""
    await db.create_upload("id1", "a.gds", "/path/a", 100, {"sha256": "a"})
    await db.create_upload("id2", "b.gds", "/path/b", 200, {"sha256": "b"})

    uploads = await db.list_uploads()
    assert len(uploads) == 2


async def test_delete_upload(db):
    """Test deleting an upload."""
    await db.create_upload("to-delete", "x.gds", "/path/x", 100, {"sha256": "x"})

    deleted = await db.delete_upload("to-delete")
    assert deleted is True

    upload = await db.get_upload("to-delete")
    assert upload is None


async def test_create_run(db):
    """Test creating a precheck run."""
    await db.create_upload("upload-1", "chip.gds", "/path", 1000, {"sha256": "x"})

    run = await db.create_run(
        id="run-1",
        upload_id="upload-1",
        top_cell="chip_top",
        die_id="ABCD1234",
        run_dir="/data/runs/run-1",
    )

    assert run["Id"] == "run-1"
    assert run["State"]["Status"] == "queued"
    assert run["Config"]["Labels"]["upload_id"] == "upload-1"
    assert run["Config"]["Labels"]["top_cell"] == "chip_top"


async def test_get_next_queued_run(db):
    """Test getting the next queued run in FIFO order."""
    await db.create_upload("u1", "a.gds", "/path", 100, {"sha256": "a"})

    await db.create_run("run-1", "u1", "cell1", "ID1", "/runs/1")
    await db.create_run("run-2", "u1", "cell2", "ID2", "/runs/2")

    next_run = await db.get_next_queued_run()
    assert next_run["Id"] == "run-1"


async def test_update_run_status(db):
    """Test updating run status."""
    await db.create_upload("u1", "a.gds", "/path", 100, {"sha256": "a"})
    await db.create_run("run-1", "u1", "cell", "ID", "/runs/1")

    await db.update_run(
        "run-1",
        status="running",
        container_id="docker-abc123",
        started_at=datetime.utcnow().isoformat() + "Z",
    )

    run = await db.get_run("run-1")
    assert run["State"]["Status"] == "running"
    assert run["State"]["Running"] is True


async def test_get_running_runs(db):
    """Test getting all running runs."""
    await db.create_upload("u1", "a.gds", "/path", 100, {"sha256": "a"})
    await db.create_run("run-1", "u1", "cell", "ID", "/runs/1")
    await db.create_run("run-2", "u1", "cell", "ID", "/runs/2")

    await db.update_run("run-1", status="running", container_id="c1")

    running = await db.get_running_runs()
    assert len(running) == 1
    assert running[0]["Id"] == "run-1"


async def test_get_queue_position(db):
    """Test getting queue position for a run."""
    await db.create_upload("u1", "a.gds", "/path", 100, {"sha256": "a"})
    await db.create_run("run-1", "u1", "cell", "ID", "/runs/1")
    await db.create_run("run-2", "u1", "cell", "ID", "/runs/2")
    await db.create_run("run-3", "u1", "cell", "ID", "/runs/3")

    pos1 = await db.get_queue_position("run-1")
    pos2 = await db.get_queue_position("run-2")
    pos3 = await db.get_queue_position("run-3")

    assert pos1 == 1
    assert pos2 == 2
    assert pos3 == 3
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/api-server && uv run pytest tests/test_database.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'precheck_server.database'"

**Step 3: Implement database module**

```python
# precheck_server/database.py
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
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/api-server && uv run pytest tests/test_database.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/database.py tests/test_database.py
git commit -m "feat: add async SQLite database module"
```

---

## Task 4: Docker Client Wrapper

**Files:**
- Create: `precheck_server/docker_client.py`
- Create: `tests/test_docker_client.py`

**Step 1: Write tests for Docker client (with mocking)**

```python
# tests/test_docker_client.py
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
    mock_docker.from_env.return_value.containers.get.return_value = mock_container

    client = DockerClient(container_prefix="precheck-")
    client.stop_and_remove("container-id")

    mock_container.stop.assert_called_once_with(timeout=10)
    mock_container.remove.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/api-server && uv run pytest tests/test_docker_client.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement Docker client wrapper**

```python
# precheck_server/docker_client.py
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
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/api-server && uv run pytest tests/test_docker_client.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/docker_client.py tests/test_docker_client.py
git commit -m "feat: add Docker client wrapper"
```

---

## Task 5: FastAPI Application Shell

**Files:**
- Create: `precheck_server/app.py`
- Create: `precheck_server/models.py`
- Modify: `precheck_server/__main__.py`
- Create: `tests/test_app.py`

**Step 1: Write basic API test**

```python
# tests/test_app.py
"""Tests for FastAPI application."""

import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile

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
    app = create_app(test_config)
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
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/api-server && uv run pytest tests/test_app.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create Pydantic models**

```python
# precheck_server/models.py
"""Pydantic models for API request/response validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Request models

class CreatePrecheckRequest(BaseModel):
    """Request to create a precheck run."""

    upload_id: str = Field(..., description="ID of uploaded file")
    top_cell: str = Field(..., description="Top-level cell name")
    die_id: str = Field(default="FFFFFFFF", description="Die ID for QR code")


# Response models - Docker-aligned

class StateResponse(BaseModel):
    """Container/run state."""

    Status: str
    Running: bool = False
    Paused: bool = False
    StartedAt: str = "0001-01-01T00:00:00Z"
    FinishedAt: str = "0001-01-01T00:00:00Z"
    ExitCode: int = 0
    Error: str = ""


class UploadStateResponse(BaseModel):
    """Upload state."""

    Status: str  # available, expired
    Expired: bool


class ChecksumsResponse(BaseModel):
    """File checksums."""

    sha256: str


class UploadResponse(BaseModel):
    """Upload metadata response."""

    Id: str
    Name: str
    Created: str
    Size: int
    Checksums: ChecksumsResponse
    ExpiresAt: str
    State: UploadStateResponse


class QueueResponse(BaseModel):
    """Queue position info."""

    Position: Optional[int] = None
    Length: int = 0


class LabelsResponse(BaseModel):
    """Run configuration labels."""

    upload_id: str
    top_cell: str
    die_id: str


class ConfigResponse(BaseModel):
    """Run configuration."""

    Image: Optional[str] = None
    Cmd: Optional[List[str]] = None
    Labels: LabelsResponse


class HostConfigResponse(BaseModel):
    """Host configuration."""

    Binds: List[str] = []


class InputResponse(BaseModel):
    """Input file info."""

    Filename: Optional[str] = None
    Size: Optional[int] = None
    Checksums: Optional[Dict[str, str]] = None


class OutputResponse(BaseModel):
    """Output file info."""

    Available: bool = False
    Filename: Optional[str] = None
    Size: Optional[int] = None
    Checksums: Optional[Dict[str, str]] = None


class RunResponse(BaseModel):
    """Precheck run response (Docker-aligned)."""

    Id: str
    Name: str
    Created: str
    State: StateResponse
    Config: ConfigResponse
    HostConfig: HostConfigResponse
    Queue: QueueResponse
    ContainerId: Optional[str] = None
    Input: Optional[InputResponse] = None
    Output: Optional[OutputResponse] = None


class QueueStatusResponse(BaseModel):
    """Global queue status."""

    queued: int
    running: int
    max_concurrent: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


class WaitResponse(BaseModel):
    """Wait endpoint response (Docker-aligned)."""

    StatusCode: int
    Error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response (Docker-aligned)."""

    message: str


class LogsResponse(BaseModel):
    """Logs polling response."""

    lines: List[str]
    since: float
    last_timestamp: float
    has_more: bool
```

**Step 4: Create FastAPI application**

```python
# precheck_server/app.py
"""FastAPI application factory."""

import hashlib
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from precheck_server import __version__
from precheck_server.config import Config
from precheck_server.database import Database
from precheck_server.docker_client import DockerClient
from precheck_server.models import (
    CreatePrecheckRequest,
    ErrorResponse,
    HealthResponse,
    LogsResponse,
    QueueStatusResponse,
    RunResponse,
    UploadResponse,
    WaitResponse,
)


def create_app(config: Config) -> FastAPI:
    """Create FastAPI application with given configuration."""

    # Initialize components
    db = Database(
        config.server.storage_path / "precheck.db",
        upload_expiry_minutes=config.server.upload_expiry_minutes,
    )
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        # Startup
        await db.initialize()

        # Create storage directories
        uploads_dir = config.server.storage_path / "uploads"
        runs_dir = config.server.storage_path / "runs"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        yield

        # Shutdown
        await db.close()

    app = FastAPI(
        title="Precheck API Server",
        description="API server for gf180mcu precheck runs",
        version=__version__,
        lifespan=lifespan,
    )

    # Store config and components in app state
    app.state.config = config
    app.state.db = db
    app.state.docker = docker

    # Health check
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(status="healthy", version=__version__)

    # Queue status
    @app.get("/api/v1/queue", response_model=QueueStatusResponse)
    async def get_queue_status():
        """Get global queue status."""
        queued = await db.get_queue_length()
        running = docker.count_running()
        return QueueStatusResponse(
            queued=queued,
            running=running,
            max_concurrent=config.server.max_concurrent,
        )

    # Upload endpoints
    @app.post("/api/v1/uploads", response_model=UploadResponse)
    async def create_upload(file: UploadFile = File(...)):
        """Upload a GDS/OAS file."""
        upload_id = str(uuid.uuid4())
        upload_dir = config.server.storage_path / "uploads" / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Determine filename
        original_name = file.filename or "input.gds"
        filepath = upload_dir / "input.gds"

        # Save file and compute checksum
        sha256 = hashlib.sha256()
        size = 0
        with open(filepath, "wb") as f:
            while chunk := await file.read(8192):
                f.write(chunk)
                sha256.update(chunk)
                size += len(chunk)

        checksums = {"sha256": sha256.hexdigest()}

        upload = await db.create_upload(
            id=upload_id,
            name=original_name,
            filepath=str(filepath),
            size=size,
            checksums=checksums,
        )

        return UploadResponse(**upload)

    @app.get("/api/v1/uploads", response_model=List[UploadResponse])
    async def list_uploads():
        """List all uploads."""
        uploads = await db.list_uploads()
        return [UploadResponse(**u) for u in uploads]

    @app.get(
        "/api/v1/uploads/{upload_id}",
        response_model=UploadResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_upload(upload_id: str):
        """Get upload by ID."""
        upload = await db.get_upload(upload_id)
        if not upload:
            raise HTTPException(status_code=404, detail=f"No such upload: {upload_id}")
        return UploadResponse(**upload)

    @app.delete(
        "/api/v1/uploads/{upload_id}",
        responses={404: {"model": ErrorResponse}},
    )
    async def delete_upload(upload_id: str):
        """Delete an upload."""
        upload = await db.get_upload(upload_id)
        if not upload:
            raise HTTPException(status_code=404, detail=f"No such upload: {upload_id}")

        # Delete files
        upload_dir = config.server.storage_path / "uploads" / upload_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)

        await db.delete_upload(upload_id)
        return {"message": "Upload deleted"}

    # Precheck run endpoints
    @app.post("/api/v1/prechecks", response_model=RunResponse)
    async def create_precheck(request: CreatePrecheckRequest):
        """Create and queue a precheck run."""
        # Verify upload exists
        upload = await db.get_upload(request.upload_id)
        if not upload:
            raise HTTPException(
                status_code=404, detail=f"No such upload: {request.upload_id}"
            )

        if upload["State"]["Expired"]:
            raise HTTPException(status_code=400, detail="Upload has expired")

        run_id = str(uuid.uuid4())
        run_dir = config.server.storage_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Copy input file to run directory
        src_path = Path(upload["_filepath"])
        dst_path = run_dir / "input.gds"
        shutil.copy2(src_path, dst_path)

        run = await db.create_run(
            id=run_id,
            upload_id=request.upload_id,
            top_cell=request.top_cell,
            die_id=request.die_id,
            run_dir=str(run_dir),
        )

        # Update queue length
        run["Queue"]["Length"] = await db.get_queue_length()

        return RunResponse(**run)

    @app.get("/api/v1/prechecks", response_model=List[RunResponse])
    async def list_prechecks(status: Optional[List[str]] = Query(None)):
        """List precheck runs."""
        runs = await db.list_runs(status=status)
        queue_length = await db.get_queue_length()
        for run in runs:
            run["Queue"]["Length"] = queue_length
        return [RunResponse(**r) for r in runs]

    @app.get(
        "/api/v1/prechecks/{run_id}",
        response_model=RunResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_precheck(run_id: str):
        """Get precheck run by ID."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        run["Queue"]["Length"] = await db.get_queue_length()
        return RunResponse(**run)

    @app.delete(
        "/api/v1/prechecks/{run_id}",
        responses={404: {"model": ErrorResponse}},
    )
    async def cancel_precheck(run_id: str):
        """Cancel a precheck run."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        status = run["State"]["Status"]

        if status == "running" and run.get("ContainerId"):
            docker.stop_and_remove(run["ContainerId"])

        if status in ("queued", "running"):
            await db.update_run(
                run_id,
                status="cancelled",
                finished_at=datetime.utcnow().isoformat() + "Z",
            )

        return {"message": "Precheck cancelled"}

    @app.get(
        "/api/v1/prechecks/{run_id}/logs",
        response_model=LogsResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_precheck_logs(
        run_id: str,
        since: float = Query(0, description="Unix timestamp"),
        tail: Optional[int] = Query(None, description="Number of lines"),
        timestamps: bool = Query(False),
    ):
        """Get precheck logs."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        if not run.get("ContainerId"):
            return LogsResponse(
                lines=[],
                since=since,
                last_timestamp=since,
                has_more=False,
            )

        logs = docker.get_logs(
            run["ContainerId"],
            since=int(since) if since > 0 else None,
            tail=tail,
            timestamps=timestamps,
        )

        lines = logs.strip().split("\n") if logs and logs.strip() else []
        last_ts = since

        # Parse last timestamp if available
        if lines and timestamps:
            # Docker timestamp format: 2024-01-15T10:30:00.123456789Z
            try:
                ts_str = lines[-1].split(" ")[0]
                dt = datetime.fromisoformat(ts_str.rstrip("Z"))
                last_ts = dt.timestamp()
            except (ValueError, IndexError):
                pass

        return LogsResponse(
            lines=lines,
            since=since,
            last_timestamp=last_ts,
            has_more=len(lines) == tail if tail else False,
        )

    @app.get(
        "/api/v1/prechecks/{run_id}/stats",
        responses={404: {"model": ErrorResponse}},
    )
    async def get_precheck_stats(run_id: str):
        """Get precheck resource stats."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        if run["State"]["Status"] != "running" or not run.get("ContainerId"):
            raise HTTPException(
                status_code=400, detail="Precheck is not running"
            )

        stats = docker.get_stats(run["ContainerId"])
        if not stats:
            raise HTTPException(status_code=404, detail="Stats not available")

        return stats

    @app.post(
        "/api/v1/prechecks/{run_id}/wait",
        response_model=WaitResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def wait_for_precheck(
        run_id: str,
        timeout: int = Query(300, description="Timeout in seconds"),
    ):
        """Wait for precheck to complete."""
        import asyncio

        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        start = datetime.utcnow()
        while True:
            run = await db.get_run(run_id)
            status = run["State"]["Status"]

            if status in ("completed", "failed", "cancelled"):
                return WaitResponse(
                    StatusCode=run["State"]["ExitCode"],
                    Error=run["State"]["Error"] or None,
                )

            elapsed = (datetime.utcnow() - start).total_seconds()
            if elapsed >= timeout:
                raise HTTPException(status_code=408, detail="Wait timeout")

            await asyncio.sleep(1)

    @app.get(
        "/api/v1/prechecks/{run_id}/output",
        responses={404: {"model": ErrorResponse}},
    )
    async def get_precheck_output(run_id: str):
        """Download precheck output GDS."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        if run["State"]["Status"] != "completed":
            raise HTTPException(status_code=400, detail="Precheck not completed")

        # Find output GDS in run directory
        run_dir = Path(run["_run_dir"])
        top_cell = run["Config"]["Labels"]["top_cell"]

        # LibreLane output structure: {run_dir}/{top_cell}/{timestamp}/KLayout.GenerateID/{top_cell}.gds
        output_candidates = list(run_dir.glob(f"**/KLayout.GenerateID/{top_cell}.gds"))

        if not output_candidates:
            raise HTTPException(status_code=404, detail="Output GDS not found")

        output_path = output_candidates[0]
        return FileResponse(
            output_path,
            media_type="application/octet-stream",
            filename=f"{top_cell}.gds",
        )

    return app
```

**Step 5: Update __main__.py**

```python
# precheck_server/__main__.py
"""CLI entry point."""

from pathlib import Path

import click
import uvicorn

from precheck_server.config import load_config
from precheck_server.docker_client import DockerClient


@click.group()
def cli():
    """Precheck server management CLI."""
    pass


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
def serve(config_path: Path):
    """Start the API server."""
    config = load_config(config_path)

    # Check for orphaned containers
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )
    orphans = docker.has_orphans()
    if orphans:
        click.echo(f"Error: Found {len(orphans)} orphaned containers:", err=True)
        for name in orphans:
            click.echo(f"  - {name}", err=True)
        click.echo("\nRun 'precheck-server cleanup' first", err=True)
        raise SystemExit(1)

    # Import here to avoid circular imports
    from precheck_server.app import create_app

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
    )


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
@click.option("--dry-run", is_flag=True, help="Show what would be done")
def cleanup(config_path: Path, dry_run: bool):
    """Remove orphaned Docker containers."""
    config = load_config(config_path)
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )

    orphans = docker.has_orphans()
    if not orphans:
        click.echo("No orphaned containers found")
        return

    click.echo(f"Found {len(orphans)} orphaned containers:")
    for name in orphans:
        click.echo(f"  - {name}")

    if dry_run:
        click.echo("\nDry run - no containers removed")
        return

    removed = docker.cleanup_orphans()
    click.echo(f"\nRemoved {len(removed)} containers")


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(config_path: Path, as_json: bool):
    """Show current server status."""
    import json as json_module

    config = load_config(config_path)
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )

    containers = docker.list_precheck_containers()
    running = [c for c in containers if c.status == "running"]

    status_data = {
        "storage_path": str(config.server.storage_path),
        "max_concurrent": config.server.max_concurrent,
        "containers": {
            "total": len(containers),
            "running": len(running),
        },
    }

    if as_json:
        click.echo(json_module.dumps(status_data, indent=2))
    else:
        click.echo(f"Storage: {status_data['storage_path']}")
        click.echo(f"Max concurrent: {status_data['max_concurrent']}")
        click.echo(f"Containers: {len(running)} running, {len(containers)} total")


if __name__ == "__main__":
    cli()
```

**Step 6: Run tests to verify they pass**

Run: `cd .worktrees/api-server && uv run pytest tests/test_app.py -v`
Expected: All tests pass

**Step 7: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/models.py precheck_server/app.py precheck_server/__main__.py tests/test_app.py
git commit -m "feat: add FastAPI application with core endpoints"
```

---

## Task 6: Queue Processor Background Task

**Files:**
- Create: `precheck_server/queue_processor.py`
- Modify: `precheck_server/app.py`
- Create: `tests/test_queue_processor.py`

**Step 1: Write tests for queue processor**

```python
# tests/test_queue_processor.py
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
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/api-server && uv run pytest tests/test_queue_processor.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement queue processor**

```python
# precheck_server/queue_processor.py
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
```

**Step 4: Update app.py to include queue processor**

Add to `precheck_server/app.py` in the lifespan handler:

```python
# In create_app function, update the lifespan:

from precheck_server.queue_processor import QueueProcessor

# ... inside create_app ...

    processor = QueueProcessor(
        db=db,
        docker=docker,
        max_concurrent=config.server.max_concurrent,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        # Startup
        await db.initialize()

        # Create storage directories
        uploads_dir = config.server.storage_path / "uploads"
        runs_dir = config.server.storage_path / "runs"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        # Start queue processor
        await processor.start()

        yield

        # Shutdown
        await processor.stop()
        await db.close()
```

**Step 5: Run tests**

Run: `cd .worktrees/api-server && uv run pytest tests/test_queue_processor.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/queue_processor.py precheck_server/app.py tests/test_queue_processor.py
git commit -m "feat: add background queue processor"
```

---

## Task 7: Authentication Middleware

**Files:**
- Create: `precheck_server/auth.py`
- Modify: `precheck_server/app.py`
- Create: `tests/test_auth.py`

**Step 1: Write auth tests**

```python
# tests/test_auth.py
"""Tests for authentication middleware."""

import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import tempfile

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
    app = create_app(auth_config)
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
```

**Step 2: Run tests to verify they fail**

Run: `cd .worktrees/api-server && uv run pytest tests/test_auth.py -v`
Expected: FAIL (requests not rejected)

**Step 3: Implement auth middleware**

```python
# precheck_server/auth.py
"""Authentication and authorization middleware."""

import ipaddress
from typing import Callable, List, Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from precheck_server.config import AuthConfig


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key and IP-based authentication."""

    # Paths that don't require authentication
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, auth_config: AuthConfig):
        super().__init__(app)
        self.auth_config = auth_config
        self._valid_keys = {key.key for key in auth_config.api_keys}
        self._allowed_networks = self._parse_allowed_ips(auth_config.allowed_ips)

    def _parse_allowed_ips(self, allowed_ips: List[str]) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse IP addresses and CIDR notation."""
        networks = []
        for ip_str in allowed_ips:
            try:
                # Try as network (CIDR)
                networks.append(ipaddress.ip_network(ip_str, strict=False))
            except ValueError:
                # Try as single IP
                try:
                    addr = ipaddress.ip_address(ip_str)
                    # Convert to /32 or /128 network
                    prefix = 32 if isinstance(addr, ipaddress.IPv4Address) else 128
                    networks.append(ipaddress.ip_network(f"{ip_str}/{prefix}"))
                except ValueError:
                    pass
        return networks

    def _is_ip_allowed(self, client_ip: str) -> bool:
        """Check if client IP is in allowed list."""
        if not self._allowed_networks:
            return True  # Empty list = allow all

        try:
            addr = ipaddress.ip_address(client_ip)
            return any(addr in network for network in self._allowed_networks)
        except ValueError:
            return False

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request headers."""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Try X-API-Key header
        return request.headers.get("X-API-Key")

    async def dispatch(self, request: Request, call_next: Callable):
        """Process the request through auth checks."""
        # Skip auth for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Check IP allowlist
        client_ip = request.client.host if request.client else "unknown"
        if not self._is_ip_allowed(client_ip):
            return JSONResponse(
                status_code=403,
                content={"message": f"Forbidden: IP {client_ip} not allowed"},
            )

        # Check API key if required
        if self.auth_config.required:
            api_key = self._extract_api_key(request)
            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"message": "Unauthorized: API key required"},
                )
            if api_key not in self._valid_keys:
                return JSONResponse(
                    status_code=401,
                    content={"message": "Unauthorized: Invalid API key"},
                )

        return await call_next(request)
```

**Step 4: Add middleware to app**

Update `precheck_server/app.py`:

```python
# Add import at top
from precheck_server.auth import AuthMiddleware

# In create_app, after creating app:
    app = FastAPI(...)

    # Add auth middleware
    app.add_middleware(AuthMiddleware, auth_config=config.auth)
```

**Step 5: Run tests**

Run: `cd .worktrees/api-server && uv run pytest tests/test_auth.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/auth.py precheck_server/app.py tests/test_auth.py
git commit -m "feat: add authentication middleware"
```

---

## Task 8: Upload Expiry Cleanup

**Files:**
- Create: `precheck_server/cleanup.py`
- Modify: `precheck_server/app.py`
- Create: `tests/test_cleanup.py`

**Step 1: Write cleanup tests**

```python
# tests/test_cleanup.py
"""Tests for upload expiry cleanup."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from precheck_server.cleanup import UploadCleanup
from precheck_server.database import Database


@pytest.fixture
async def db():
    """Create test database with short expiry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db", upload_expiry_minutes=0)  # Immediate expiry
        await db.initialize()
        yield db
        await db.close()


async def test_cleanup_removes_expired_uploads(db, tmp_path):
    """Test that expired uploads are removed."""
    # Create upload directory
    upload_dir = tmp_path / "uploads" / "expired-upload"
    upload_dir.mkdir(parents=True)
    (upload_dir / "input.gds").write_text("test")

    # Create expired upload in DB (expiry_minutes=0 means already expired)
    await db.create_upload(
        id="expired-upload",
        name="test.gds",
        filepath=str(upload_dir / "input.gds"),
        size=4,
        checksums={"sha256": "abc"},
    )

    cleanup = UploadCleanup(db, tmp_path / "uploads")
    removed = await cleanup.cleanup_once()

    assert "expired-upload" in removed
    assert not upload_dir.exists()


async def test_cleanup_preserves_uploads_with_runs(db, tmp_path):
    """Test that uploads with associated runs are preserved."""
    upload_dir = tmp_path / "uploads" / "with-run"
    upload_dir.mkdir(parents=True)
    (upload_dir / "input.gds").write_text("test")

    await db.create_upload(
        id="with-run",
        name="test.gds",
        filepath=str(upload_dir / "input.gds"),
        size=4,
        checksums={"sha256": "abc"},
    )
    await db.create_run("run-1", "with-run", "cell", "ID", str(tmp_path / "runs/run-1"))

    cleanup = UploadCleanup(db, tmp_path / "uploads")
    removed = await cleanup.cleanup_once()

    assert "with-run" not in removed
    assert upload_dir.exists()
```

**Step 2: Implement cleanup**

```python
# precheck_server/cleanup.py
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
```

**Step 3: Add to app lifespan**

Update `precheck_server/app.py` lifespan:

```python
from precheck_server.cleanup import UploadCleanup

# In create_app:
    cleanup = UploadCleanup(
        db=db,
        uploads_dir=config.server.storage_path / "uploads",
    )

    # In lifespan, after processor.start():
        await cleanup.start()

    # In lifespan shutdown, before processor.stop():
        await cleanup.stop()
```

**Step 4: Run tests**

Run: `cd .worktrees/api-server && uv run pytest tests/test_cleanup.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/cleanup.py precheck_server/app.py tests/test_cleanup.py
git commit -m "feat: add upload expiry cleanup background task"
```

---

## Task 9: CLI Runs Commands

**Files:**
- Modify: `precheck_server/__main__.py`

**Step 1: Add runs commands to CLI**

```python
# Add to precheck_server/__main__.py

@cli.group()
def runs():
    """Manage precheck runs."""
    pass


@runs.command("list")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--status", multiple=True, help="Filter by status")
@click.option("--json", "as_json", is_flag=True)
def runs_list(config_path: Path, status: tuple, as_json: bool):
    """List precheck runs."""
    import asyncio
    import json as json_module

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found. Is the server running?", err=True)
        return

    async def _list():
        from precheck_server.database import Database

        db = Database(db_path, upload_expiry_minutes=config.server.upload_expiry_minutes)
        # Don't reinitialize - just connect
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        status_filter = list(status) if status else None
        runs = await db.list_runs(status=status_filter)
        await db.close()
        return runs

    import aiosqlite
    runs_data = asyncio.run(_list())

    if as_json:
        click.echo(json_module.dumps(runs_data, indent=2, default=str))
    else:
        click.echo(f"{'ID':<36} {'STATUS':<12} {'CREATED':<24} {'TOP_CELL':<20}")
        click.echo("-" * 92)
        for run in runs_data:
            click.echo(
                f"{run['Id']:<36} {run['State']['Status']:<12} "
                f"{run['Created']:<24} {run['Config']['Labels']['top_cell']:<20}"
            )


@runs.command("inspect")
@click.argument("run_id")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
def runs_inspect(run_id: str, config_path: Path):
    """Inspect a precheck run."""
    import asyncio
    import json as json_module

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _get():
        import aiosqlite
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row
        run = await db.get_run(run_id)
        await db.close()
        return run

    run = asyncio.run(_get())

    if not run:
        click.echo(f"No such run: {run_id}", err=True)
        return

    click.echo(json_module.dumps(run, indent=2, default=str))


@runs.command("delete")
@click.argument("run_id")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--force", is_flag=True, help="Skip confirmation")
def runs_delete(run_id: str, config_path: Path, force: bool):
    """Delete a precheck run."""
    import asyncio
    import shutil

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _delete():
        import aiosqlite
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        run = await db.get_run(run_id)
        if not run:
            return None

        if not force:
            click.confirm(f"Delete run {run_id}?", abort=True)

        # Delete files
        run_dir = Path(run["_run_dir"])
        if run_dir.exists():
            shutil.rmtree(run_dir)

        await db.delete_run(run_id)
        await db.close()
        return run_id

    deleted = asyncio.run(_delete())

    if deleted:
        click.echo(f"Deleted run: {deleted}")
    else:
        click.echo(f"No such run: {run_id}", err=True)


@runs.command("prune")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--status", multiple=True, help="Only prune runs with these statuses")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def runs_prune(config_path: Path, status: tuple, dry_run: bool):
    """Delete old precheck runs."""
    import asyncio
    import shutil

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _prune():
        import aiosqlite
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        status_filter = list(status) if status else ["completed", "failed", "cancelled"]
        runs = await db.list_runs(status=status_filter)

        if not runs:
            click.echo("No runs to prune")
            return []

        click.echo(f"Found {len(runs)} runs to prune:")
        total_size = 0
        for run in runs:
            run_dir = Path(run["_run_dir"])
            size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file()) if run_dir.exists() else 0
            total_size += size
            click.echo(f"  {run['Id']}  {run['State']['Status']:<12}  {size / 1024 / 1024:.1f} MB")

        click.echo(f"\nTotal: {total_size / 1024 / 1024:.1f} MB")

        if dry_run:
            click.echo("\nDry run - no runs deleted")
            return []

        if not click.confirm("\nDelete these runs?"):
            return []

        deleted = []
        for run in runs:
            run_dir = Path(run["_run_dir"])
            if run_dir.exists():
                shutil.rmtree(run_dir)
            await db.delete_run(run["Id"])
            deleted.append(run["Id"])

        await db.close()
        return deleted

    deleted = asyncio.run(_prune())
    if deleted:
        click.echo(f"\nDeleted {len(deleted)} runs")
```

**Step 2: Test CLI manually**

Run: `cd .worktrees/api-server && uv run precheck-server runs --help`
Expected: Shows subcommands list, inspect, delete, prune

**Step 3: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/__main__.py
git commit -m "feat: add CLI runs management commands"
```

---

## Task 10: API Key Generation Command

**Files:**
- Modify: `precheck_server/__main__.py`

**Step 1: Add apikey command**

```python
# Add to precheck_server/__main__.py

import secrets


@cli.group()
def apikey():
    """Manage API keys."""
    pass


@apikey.command("generate")
@click.option("--name", default="", help="Optional name for the key")
def apikey_generate(name: str):
    """Generate a new API key."""
    key = f"ws_key_{secrets.token_hex(24)}"

    click.echo(f"\nGenerated API key:")
    click.echo(f"  Name: {name or '(unnamed)'}")
    click.echo(f"  Key:  {key}")
    click.echo(f"\nAdd to config.toml:")
    click.echo(f'  [[auth.api_keys]]')
    click.echo(f'  name = "{name}"')
    click.echo(f'  key = "{key}"')
    click.echo(f"\n⚠️  Save this key now - it cannot be retrieved later")
```

**Step 2: Test**

Run: `cd .worktrees/api-server && uv run precheck-server apikey generate --name test`
Expected: Shows generated key and config snippet

**Step 3: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/__main__.py
git commit -m "feat: add API key generation command"
```

---

## Task 11: Debug Endpoint

**Files:**
- Modify: `precheck_server/app.py`

**Step 1: Add debug tarball endpoint**

Add to `precheck_server/app.py`:

```python
import tarfile
import io

# Add debug endpoint in create_app:

    @app.get(
        "/api/v1/debug/prechecks/{run_id}",
        responses={404: {"model": ErrorResponse}},
    )
    async def get_debug_tarball(run_id: str):
        """Download full run directory as tarball."""
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"No such precheck: {run_id}")

        run_dir = Path(run["_run_dir"])
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="Run directory not found")

        # Create tarball in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            tar.add(run_dir, arcname=run_id)
        tar_buffer.seek(0)

        from fastapi.responses import StreamingResponse

        return StreamingResponse(
            tar_buffer,
            media_type="application/x-tar",
            headers={
                "Content-Disposition": f'attachment; filename="precheck-{run_id}.tar.gz"'
            },
        )
```

**Step 2: Commit**

```bash
cd .worktrees/api-server
git add precheck_server/app.py
git commit -m "feat: add debug tarball endpoint"
```

---

## Task 12: Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
# tests/test_integration.py
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
```

**Step 2: Run integration tests**

Run: `cd .worktrees/api-server && uv run pytest tests/test_integration.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
cd .worktrees/api-server
git add tests/test_integration.py
git commit -m "test: add integration tests for full workflow"
```

---

## Task 13: Run All Tests and Final Cleanup

**Step 1: Run full test suite**

Run: `cd .worktrees/api-server && uv run pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Run type checking (optional)**

Run: `cd .worktrees/api-server && uv run mypy precheck_server/ --ignore-missing-imports`

**Step 3: Final commit with all files**

```bash
cd .worktrees/api-server
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: final cleanup and formatting"
```

---

## Summary

This plan creates a complete precheck API server with:

1. **Project structure** with pyproject.toml and dependencies
2. **Configuration** module for TOML config loading
3. **Database** module with async SQLite operations
4. **Docker client** wrapper for container management
5. **FastAPI application** with all endpoints
6. **Queue processor** background task
7. **Authentication** middleware for API keys and IP restrictions
8. **Upload cleanup** background task
9. **CLI tool** with serve, cleanup, status, runs, and apikey commands
10. **Debug endpoint** for downloading run directories
11. **Integration tests** for full workflow validation

Each task follows TDD: write failing test, implement, verify passing, commit.
