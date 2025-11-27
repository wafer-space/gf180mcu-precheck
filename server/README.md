# Precheck API Server

An HTTP API server that provides a REST interface to the gf180mcu precheck tool. The server orchestrates precheck runs inside Docker containers, providing file uploads, async job processing, and result retrieval.

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────────────────┐
│   Client    │────▶│   API Server    │────▶│  precheck Docker container   │
│  (HTTP)     │     │   (FastAPI)     │     │  (ghcr.io/wafer-space/...)   │
└─────────────┘     └─────────────────┘     └──────────────────────────────┘
                           │                            │
                           ▼                            ▼
                    ┌─────────────┐              ┌─────────────┐
                    │   SQLite    │              │  PDK + EDA  │
                    │  (state)    │              │   tools     │
                    └─────────────┘              └─────────────┘
```

The API server acts as a thin orchestration layer:

1. Accepts layout file uploads via HTTP
2. Queues precheck jobs for processing
3. Spawns `ghcr.io/wafer-space/gf180mcu-precheck` Docker containers to execute the actual precheck
4. Collects results and makes them available via the API

Each precheck run gets its own isolated container with:
- Network isolation (`--network=none`)
- The uploaded layout mounted as a volume
- The pre-built gf180mcu PDK already included in the container image

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (with access to pull images and run containers)
- The precheck Docker image: `ghcr.io/wafer-space/gf180mcu-precheck:latest`

### Installation

```bash
cd server
uv sync
```

### Configuration

Copy the example configuration:

```bash
cp config.example.toml config.toml
```

Edit `config.toml` as needed:

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
required = false
```

### Start the Server

```bash
uv run precheck-server serve --config config.toml
```

The server will be available at `http://localhost:8000`.

## Command Line Interface

The `precheck-server` CLI provides commands for server management:

### Server Commands

```bash
# Start the API server
uv run precheck-server serve --config config.toml

# Check server status
uv run precheck-server status --config config.toml
uv run precheck-server status --config config.toml --json

# Clean up orphaned Docker containers
uv run precheck-server cleanup --config config.toml
uv run precheck-server cleanup --config config.toml --dry-run
```

### Run Management

```bash
# List precheck runs
uv run precheck-server runs list --config config.toml
uv run precheck-server runs list --config config.toml --status queued --status running
uv run precheck-server runs list --config config.toml --json

# Inspect a specific run
uv run precheck-server runs inspect <run-id> --config config.toml

# Delete a run
uv run precheck-server runs delete <run-id> --config config.toml
uv run precheck-server runs delete <run-id> --config config.toml --force

# Prune old runs
uv run precheck-server runs prune --config config.toml
uv run precheck-server runs prune --config config.toml --status completed --status failed
uv run precheck-server runs prune --config config.toml --dry-run
```

### API Key Management

```bash
# Generate a new API key
uv run precheck-server apikey generate
uv run precheck-server apikey generate --name "ci-server"
```

## API Reference

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Queue Status

```bash
curl http://localhost:8000/api/v1/queue
```

Response:
```json
{
  "queued": 2,
  "running": 1,
  "max_concurrent": 1
}
```

### Upload a Layout File

```bash
curl -X POST http://localhost:8000/api/v1/uploads \
  -F "file=@chip_top.gds"
```

Response:
```json
{
  "Id": "550e8400-e29b-41d4-a716-446655440000",
  "Name": "chip_top.gds",
  "Size": 1048576,
  "Created": "2024-01-15T10:30:00Z",
  "Checksums": {
    "sha256": "abc123..."
  },
  "State": {
    "Expired": false,
    "ExpiresAt": "2024-01-15T10:45:00Z"
  }
}
```

### Create a Precheck Run

```bash
curl -X POST http://localhost:8000/api/v1/prechecks \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "550e8400-e29b-41d4-a716-446655440000",
    "top_cell": "chip_top",
    "die_id": "ABCD1234"
  }'
```

Response:
```json
{
  "Id": "660e8400-e29b-41d4-a716-446655440001",
  "Created": "2024-01-15T10:30:05Z",
  "State": {
    "Status": "queued",
    "ExitCode": null,
    "Error": null,
    "StartedAt": null,
    "FinishedAt": null
  },
  "Config": {
    "Labels": {
      "upload_id": "550e8400-e29b-41d4-a716-446655440000",
      "top_cell": "chip_top",
      "die_id": "ABCD1234"
    }
  },
  "Queue": {
    "Position": 1,
    "Length": 3
  }
}
```

### Get Run Status

```bash
curl http://localhost:8000/api/v1/prechecks/660e8400-e29b-41d4-a716-446655440001
```

### List Runs

```bash
# All runs
curl http://localhost:8000/api/v1/prechecks

# Filter by status
curl "http://localhost:8000/api/v1/prechecks?status=running&status=queued"
```

### Get Run Logs

```bash
# Get all logs
curl http://localhost:8000/api/v1/prechecks/<run-id>/logs

# Stream new logs (with timestamps)
curl "http://localhost:8000/api/v1/prechecks/<run-id>/logs?since=1705315800&timestamps=true"

# Get last N lines
curl "http://localhost:8000/api/v1/prechecks/<run-id>/logs?tail=100"
```

### Wait for Completion

```bash
curl -X POST "http://localhost:8000/api/v1/prechecks/<run-id>/wait?timeout=300"
```

Response (on completion):
```json
{
  "StatusCode": 0,
  "Error": null
}
```

### Download Output

```bash
# Download output GDS (after successful completion)
curl -o output.gds http://localhost:8000/api/v1/prechecks/<run-id>/output

# Download full debug tarball (all run files)
curl -o debug.tar.gz http://localhost:8000/api/v1/debug/prechecks/<run-id>
```

### Cancel a Run

```bash
curl -X DELETE http://localhost:8000/api/v1/prechecks/<run-id>
```

### Delete an Upload

```bash
curl -X DELETE http://localhost:8000/api/v1/uploads/<upload-id>
```

## Complete Workflow Example

Here's a complete example using curl:

```bash
#!/bin/bash
set -e

SERVER="http://localhost:8000"

# 1. Upload the GDS file
echo "Uploading layout..."
UPLOAD=$(curl -s -X POST "$SERVER/api/v1/uploads" -F "file=@chip_top.gds")
UPLOAD_ID=$(echo "$UPLOAD" | jq -r '.Id')
echo "Upload ID: $UPLOAD_ID"

# 2. Create a precheck run
echo "Creating precheck run..."
RUN=$(curl -s -X POST "$SERVER/api/v1/prechecks" \
  -H "Content-Type: application/json" \
  -d "{\"upload_id\": \"$UPLOAD_ID\", \"top_cell\": \"chip_top\", \"die_id\": \"TEST0001\"}")
RUN_ID=$(echo "$RUN" | jq -r '.Id')
echo "Run ID: $RUN_ID"

# 3. Wait for completion (or poll status)
echo "Waiting for completion..."
RESULT=$(curl -s -X POST "$SERVER/api/v1/prechecks/$RUN_ID/wait?timeout=600")
EXIT_CODE=$(echo "$RESULT" | jq -r '.StatusCode')

if [ "$EXIT_CODE" = "0" ]; then
  echo "Precheck passed!"

  # 4. Download output
  echo "Downloading output..."
  curl -s -o output.gds "$SERVER/api/v1/prechecks/$RUN_ID/output"
  echo "Output saved to output.gds"
else
  echo "Precheck failed with exit code: $EXIT_CODE"

  # Download debug tarball for investigation
  curl -s -o debug.tar.gz "$SERVER/api/v1/debug/prechecks/$RUN_ID"
  echo "Debug tarball saved to debug.tar.gz"
fi
```

## Authentication

### Enabling Authentication

Set `auth.required = true` in your config:

```toml
[auth]
required = true

[[auth.api_keys]]
name = "ci-server"
key = "ws_key_abc123def456..."

[[auth.api_keys]]
name = "from-environment"
key = "${PRECHECK_API_KEY}"
```

### Using API Keys

Include the API key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer ws_key_abc123def456..." \
  http://localhost:8000/api/v1/queue
```

Or use the `X-API-Key` header:

```bash
curl -H "X-API-Key: ws_key_abc123def456..." \
  http://localhost:8000/api/v1/queue
```

### IP Allowlist

Restrict access to specific IPs:

```toml
[auth]
required = true
allowed_ips = ["192.168.1.0/24", "10.0.0.5"]
```

## Development

### Running Tests

```bash
cd server
uv run pytest
```

### Project Structure

```
server/
├── README.md              # This file
├── config.example.toml    # Example configuration
├── pyproject.toml         # Python project config
├── uv.lock                # Locked dependencies
├── docs/                  # Design documents
│   ├── 2025-01-26-precheck-api-server-design.md
│   └── 2025-01-26-api-server-implementation.md
├── precheck_server/       # Main package
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── app.py             # FastAPI application
│   ├── auth.py            # Authentication middleware
│   ├── cleanup.py         # Upload expiry cleanup
│   ├── config.py          # Configuration loading
│   ├── database.py        # SQLite database layer
│   ├── docker_client.py   # Docker integration
│   ├── models.py          # Pydantic models
│   └── queue_processor.py # Background job processor
└── tests/                 # Test suite
    ├── conftest.py
    ├── test_app.py
    ├── test_auth.py
    ├── test_cleanup.py
    ├── test_config.py
    ├── test_database.py
    ├── test_docker_client.py
    ├── test_integration.py
    └── test_queue_processor.py
```

## License

Apache 2.0 - See LICENSE file in the repository root.
