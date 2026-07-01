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
