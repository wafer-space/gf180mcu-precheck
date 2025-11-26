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
