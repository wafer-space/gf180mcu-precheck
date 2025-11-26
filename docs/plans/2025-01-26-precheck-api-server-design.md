# Precheck API Server Design

**Date:** 2025-01-26
**Status:** Draft

## Overview

A Python API server that allows users to upload GDS/OAS files, request precheck runs, monitor status, and retrieve results. The server queues precheck requests and runs them in Docker containers with configurable concurrency.

## Requirements

### Functional
- Upload GDS/OAS files for prechecking
- Request precheck runs against uploaded files
- Check status and queue position of precheck runs
- Stream/poll logs while precheck is running
- Get resource usage (CPU, memory, I/O) of running prechecks
- Cancel queued or running precheck runs
- Download output GDS after successful precheck
- Clean up expired uploads automatically

### Non-Functional
- Configurable concurrent precheck limit (default: 1)
- Configurable upload expiry time (default: 15 minutes)
- Multiple API keys for authentication
- IP-based access restrictions
- Manual cleanup of completed runs via CLI tool
- Server restart clears ephemeral state (DB recreated fresh)

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server                        │
│                                                          │
│  ┌──────────┐         ┌─────────────────────────────┐   │
│  │ API      │────────▶│      SQLite Database        │   │
│  │ Endpoints│         │  (uploads, runs - ephemeral)│   │
│  └──────────┘         └─────────────────────────────┘   │
│                                    ▲                     │
│                                    │ poll + update       │
│                                    │                     │
│                       ┌────────────┴────────────┐       │
│                       │   Queue Processor       │       │
│                       │   (async poll loop)     │       │
│                       └────────────┬────────────┘       │
│                                    │                     │
│                                    ▼                     │
│                       ┌─────────────────────────┐       │
│                       │     Docker API          │       │
│                       │  - container lifecycle  │       │
│                       │  - stats                │       │
│                       │  - logs                 │       │
│                       └─────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Framework:** FastAPI (async support, automatic OpenAPI docs, Pydantic validation)

2. **Task Queue:** Poll-based using SQLite + Docker
   - SQLite stores queue state (rows with `Status='queued'`)
   - Poll loop checks for capacity and starts Docker containers
   - No in-memory queue needed - Docker is the process manager

3. **State Management:** SQLite (ephemeral)
   - Database recreated on server restart
   - No migration concerns - schema changes just require restart
   - Run directories persist on disk for debugging

4. **Docker Integration:**
   - Each precheck runs in its own container
   - Stats from Docker stats API
   - Logs from Docker logs API
   - Container lifecycle managed by poll loop

5. **API Shape:** Docker-aligned
   - Response shapes mirror Docker API where applicable
   - Field names match Docker conventions
   - Familiar to anyone who knows Docker API

## API Endpoints

### Uploads

```
POST   /api/v1/uploads              Upload single file
GET    /api/v1/uploads              List uploads
GET    /api/v1/uploads/{id}         Get upload metadata
DELETE /api/v1/uploads/{id}         Delete upload
```

### Precheck Runs

```
POST   /api/v1/prechecks            Create and queue run
GET    /api/v1/prechecks            List runs (?status=queued,running,...)
GET    /api/v1/prechecks/{id}       Inspect run (full state)
DELETE /api/v1/prechecks/{id}       Cancel/stop run
GET    /api/v1/prechecks/{id}/logs  Get logs (?since, ?tail, ?timestamps)
GET    /api/v1/prechecks/{id}/stats Get resource stats
POST   /api/v1/prechecks/{id}/wait  Long-poll until done (?timeout)
GET    /api/v1/prechecks/{id}/output Download output GDS
```

### Queue & Debug

```
GET    /api/v1/queue                     Global queue status
GET    /api/v1/debug/prechecks/{id}      Full run directory as tarball
```

## Data Model

### SQLite Schema (Ephemeral)

```sql
-- Uploaded files awaiting precheck
CREATE TABLE uploads (
    Id              TEXT PRIMARY KEY,
    Name            TEXT NOT NULL,
    Filepath        TEXT NOT NULL,
    Size            INTEGER NOT NULL,
    Checksums       TEXT NOT NULL,  -- JSON: {"sha256": "..."}
    Created         TEXT NOT NULL,
    ExpiresAt       TEXT NOT NULL
);

-- Precheck run requests
CREATE TABLE runs (
    Id              TEXT PRIMARY KEY,
    UploadId        TEXT NOT NULL,
    TopCell         TEXT NOT NULL,
    DieId           TEXT NOT NULL DEFAULT 'FFFFFFFF',
    Status          TEXT NOT NULL,  -- queued|running|completed|failed|cancelled
    ContainerId     TEXT,
    RunDir          TEXT,
    Created         TEXT NOT NULL,
    StartedAt       TEXT,
    FinishedAt      TEXT,
    ExitCode        INTEGER,
    Error           TEXT,
    FOREIGN KEY (UploadId) REFERENCES uploads(Id)
);
```

### Configuration File (config.toml)

```toml
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
required = true
allowed_ips = [
  "192.168.1.0/24",
  "10.0.0.5",
]

[[auth.api_keys]]
name = "ci-server"
key = "ws_key_abc123..."

[[auth.api_keys]]
name = "developer"
key = "${PRECHECK_API_KEY}"  # From environment
```

## Response Shapes (Docker-Aligned)

### Upload Inspect

```json
{
  "Id": "xyz789",
  "Name": "chip_top.gds",
  "Created": "2024-01-15T10:25:00.000Z",
  "Size": 52428800,
  "Checksums": {
    "sha256": "a9f3b2c1d..."
  },
  "ExpiresAt": "2024-01-15T10:40:00.000Z",
  "State": {
    "Status": "available",
    "Expired": false
  }
}
```

### Run Inspect

```json
{
  "Id": "abc123",
  "Name": "precheck-abc123",
  "Created": "2024-01-15T10:30:00.000Z",
  "State": {
    "Status": "running",
    "Running": true,
    "Paused": false,
    "StartedAt": "2024-01-15T10:30:05.000Z",
    "FinishedAt": "0001-01-01T00:00:00Z",
    "ExitCode": 0,
    "Error": ""
  },
  "Config": {
    "Image": "ghcr.io/wafer-space/gf180mcu-precheck:latest",
    "Cmd": ["python", "precheck.py", "--input", "..."],
    "Labels": {
      "upload_id": "xyz789",
      "top_cell": "chip_top",
      "die_id": "ABCD1234"
    }
  },
  "HostConfig": {
    "Binds": ["/storage/runs/abc123:/workdir:rw"]
  },
  "Queue": {
    "Position": null,
    "Length": 2
  },
  "Input": {
    "Filename": "chip_top.gds",
    "Size": 52428800,
    "Checksums": {"sha256": "a9f3b2c1d..."}
  },
  "Output": {
    "Available": true,
    "Filename": "chip_top.gds",
    "Size": 53477376,
    "Checksums": {"sha256": "b8e4a3f2c..."}
  }
}
```

### Stats (Docker passthrough)

```json
{
  "read": "2024-01-15T10:30:00.000Z",
  "cpu_stats": {
    "cpu_usage": {
      "total_usage": 123456789,
      "percpu_usage": [30000000, 40000000, 25000000, 28456789]
    },
    "system_cpu_usage": 987654321000000,
    "online_cpus": 4
  },
  "memory_stats": {
    "usage": 52428800,
    "max_usage": 67108864,
    "limit": 2147483648
  },
  "blkio_stats": {
    "io_service_bytes_recursive": [
      {"op": "read", "value": 10485760},
      {"op": "write", "value": 5242880}
    ]
  },
  "networks": {
    "eth0": {
      "rx_bytes": 1048576,
      "tx_bytes": 524288
    }
  },
  "pids_stats": {
    "current": 5
  }
}
```

### Logs Response

```json
{
  "lines": [
    "2024-01-15T10:30:05.123Z PDK_ROOT = /pdk",
    "2024-01-15T10:30:05.124Z PDK = gf180mcuD",
    "..."
  ],
  "since": 1705315805.0,
  "last_timestamp": 1705315810.5,
  "has_more": true
}
```

### Wait Response

```json
{
  "StatusCode": 0,
  "Error": null
}
```

### Error Response

```json
{
  "message": "No such precheck: abc123"
}
```

## Queue Processing

```python
async def queue_processor():
    """Poll-based queue processor."""
    while True:
        # 1. Check capacity
        running = docker.containers.list(
            filters={"name": "precheck-", "status": "running"}
        )

        # 2. Start new jobs if room
        if len(running) < config.max_concurrent:
            job = db.get_next_queued_job()
            if job:
                container = docker.containers.run(
                    image=config.docker_image,
                    name=f"precheck-{job.Id}",
                    detach=True,
                    volumes={
                        str(job.run_dir): {"bind": "/workdir", "mode": "rw"},
                    },
                    command=[
                        "python", "precheck.py",
                        "--input", "/workdir/input.gds",
                        "--top", job.TopCell,
                        "--id", job.DieId,
                        "--dir", "/workdir",
                    ],
                )
                db.update_run(job.Id, Status="running",
                             ContainerId=container.id, StartedAt=now())

        # 3. Check for completed containers
        for job in db.get_running_jobs():
            try:
                container = docker.containers.get(job.ContainerId)
                if container.status == "exited":
                    exit_code = container.attrs["State"]["ExitCode"]

                    # Save logs before removing container
                    logs = container.logs(stdout=True, stderr=True)
                    save_logs(job.RunDir, logs)

                    # Compute output checksum
                    output_checksum = compute_output_checksum(job)

                    db.update_run(job.Id,
                                 Status="completed" if exit_code == 0 else "failed",
                                 FinishedAt=now(),
                                 ExitCode=exit_code)
                    container.remove()
            except docker.errors.NotFound:
                db.update_run(job.Id, Status="failed", Error="Container disappeared")

        await asyncio.sleep(1)
```

## Authentication & Security

### Request Flow

```
Request
   │
   ▼
┌─────────────────┐
│ IP Check        │──── IP not in allowed_ips ──▶ 403 Forbidden
└────────┬────────┘
         │ pass
         ▼
┌─────────────────┐
│ API Key Check   │──── Missing/invalid key ────▶ 401 Unauthorized
└────────┬────────┘     (if auth.required=true)
         │ pass
         ▼
    Route Handler
```

### API Key Format

- Prefix: `ws_key_` (easily identifiable)
- Body: 32+ character random string
- Example: `ws_key_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

### Request Header

```
Authorization: Bearer ws_key_abc123...
```

## File Management

### Directory Structure

```
{storage_path}/
├── uploads/
│   ├── {upload_id}/
│   │   ├── metadata.json
│   │   └── input.gds
│   └── .../
├── runs/
│   ├── {run_id}/
│   │   ├── metadata.json
│   │   ├── input.gds
│   │   └── ... (LibreLane output)
│   └── .../
└── precheck.db
```

### Checksums

- Algorithm: SHA-256
- Computed for: uploaded files, copied inputs, output GDS
- Stored in: metadata.json and API responses

## CLI Admin Tool

```bash
# Start server (fails if orphaned containers exist)
uv run python -m precheck_server serve [--config config.toml]

# Clean up orphaned containers
uv run python -m precheck_server cleanup [--dry-run]

# Show current state
uv run python -m precheck_server status [--json]

# List runs
uv run python -m precheck_server runs list [--status completed,failed]

# Inspect a run
uv run python -m precheck_server runs inspect <run_id>

# Delete runs
uv run python -m precheck_server runs delete <run_id> [--force]
uv run python -m precheck_server runs prune [--before DATE] [--status STATUS] [--dry-run]

# Generate API key
uv run python -m precheck_server apikey generate [--name NAME]
```

## Startup Sequence

1. Load config file
2. Check for orphaned containers (`docker ps --filter "name=precheck-*"`)
3. If orphans found → error, require `cleanup` command first
4. Delete and recreate SQLite database (fresh state)
5. Start background tasks:
   - Queue processor (1-second poll loop)
   - Upload expiry cleanup (1-minute poll loop)
6. Start FastAPI server

## Graceful Shutdown

1. Stop accepting new requests
2. Wait for running prechecks to complete (configurable timeout)
3. If timeout: stop containers, mark runs as failed
4. Close database connection
5. Exit

## Future Considerations

- Webhook notifications on run completion
- Priority queues
- Resource limits per API key
- Metrics/observability (Prometheus endpoint)
