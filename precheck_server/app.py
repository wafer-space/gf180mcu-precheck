"""FastAPI application factory."""

import hashlib
import io
import shutil
import tarfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from precheck_server import __version__
from precheck_server.auth import AuthMiddleware
from precheck_server.cleanup import UploadCleanup
from precheck_server.config import Config
from precheck_server.database import Database
from precheck_server.docker_client import DockerClient
from precheck_server.queue_processor import QueueProcessor
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
    processor = QueueProcessor(
        db=db,
        docker=docker,
        max_concurrent=config.server.max_concurrent,
    )
    cleanup = UploadCleanup(
        db=db,
        uploads_dir=config.server.storage_path / "uploads",
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

        # Start queue processor and cleanup
        await processor.start()
        await cleanup.start()

        yield

        # Shutdown
        await cleanup.stop()
        await processor.stop()
        await db.close()

    app = FastAPI(
        title="Precheck API Server",
        description="API server for gf180mcu precheck runs",
        version=__version__,
        lifespan=lifespan,
    )

    # Add auth middleware
    app.add_middleware(AuthMiddleware, auth_config=config.auth)

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

        return StreamingResponse(
            tar_buffer,
            media_type="application/x-tar",
            headers={
                "Content-Disposition": f'attachment; filename="precheck-{run_id}.tar.gz"'
            },
        )

    return app
