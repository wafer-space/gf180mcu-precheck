# Precheck API Server

HTTP API server for running gf180mcu prechecks. Orchestrates precheck jobs inside Docker containers from `ghcr.io/wafer-space/gf180mcu-precheck`.

## Quick Start

```bash
cd server
uv sync
cp config.example.toml config.toml
uv run precheck-server serve --config config.toml
```

Server runs at `http://localhost:8000`.

## CLI Commands

```bash
# Start server
uv run precheck-server serve --config config.toml

# Server status
uv run precheck-server status --config config.toml

# List runs
uv run precheck-server runs list --config config.toml

# Generate API key
uv run precheck-server apikey generate --name "my-key"

# Cleanup orphaned containers
uv run precheck-server cleanup --config config.toml
```

## API Usage

See the [examples/](examples/) directory:

- **[curl.md](examples/curl.md)** - API usage with curl
- **[run_precheck.py](examples/run_precheck.py)** - Python client (stdlib only, no dependencies)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/queue` | Queue status |
| POST | `/api/v1/uploads` | Upload GDS file |
| GET | `/api/v1/uploads` | List uploads |
| GET | `/api/v1/uploads/{id}` | Get upload |
| DELETE | `/api/v1/uploads/{id}` | Delete upload |
| POST | `/api/v1/prechecks` | Create precheck run |
| GET | `/api/v1/prechecks` | List runs |
| GET | `/api/v1/prechecks/{id}` | Get run status |
| DELETE | `/api/v1/prechecks/{id}` | Cancel run |
| GET | `/api/v1/prechecks/{id}/logs` | Get logs |
| POST | `/api/v1/prechecks/{id}/wait` | Wait for completion |
| GET | `/api/v1/prechecks/{id}/output` | Download output GDS |
| GET | `/api/v1/debug/prechecks/{id}` | Download debug tarball |

## Configuration

```toml
[server]
host = "0.0.0.0"
port = 8000
storage_path = "./data"
max_concurrent = 1

[docker]
image = "ghcr.io/wafer-space/gf180mcu-precheck:latest"

[auth]
required = false
# [[auth.api_keys]]
# name = "my-key"
# key = "ws_key_..."
```

## Authentication

When `auth.required = true`, include API key in requests:

```bash
curl -H "Authorization: Bearer ws_key_..." http://localhost:8000/api/v1/queue
```

Or in Python:

```python
req = urllib.request.Request(url, headers={"Authorization": "Bearer ws_key_..."})
```

## Development

```bash
cd server
uv run pytest
```

## License

Apache 2.0
