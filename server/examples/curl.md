# API Usage with curl

## Basic Workflow

### 1. Upload a GDS file

```bash
curl -X POST http://localhost:8000/api/v1/uploads -F "file=@chip_top.gds"
```

Response:
```json
{"Id": "abc123...", "Name": "chip_top.gds", "Size": 1234567, "CreatedAt": "..."}
```

### 2. Create a precheck run

```bash
curl -X POST http://localhost:8000/api/v1/prechecks \
  -H "Content-Type: application/json" \
  -d '{"upload_id": "abc123...", "top_cell": "chip_top", "die_id": "TEST0001"}'
```

Response:
```json
{"Id": "def456...", "State": {"Status": "queued"}, ...}
```

### 3. Check run status

```bash
curl http://localhost:8000/api/v1/prechecks/def456...
```

### 4. Wait for completion (blocking)

```bash
curl -X POST "http://localhost:8000/api/v1/prechecks/def456.../wait?timeout=600"
```

Response:
```json
{"StatusCode": 0, "Error": null}
```

### 5. Download output GDS

```bash
curl -o output.gds http://localhost:8000/api/v1/prechecks/def456.../output
```

## With Authentication

Set the `PRECHECK_API_KEY` environment variable:

```bash
export PRECHECK_API_KEY="ws_key_..."
```

Then include it in requests:

```bash
curl -H "Authorization: Bearer $PRECHECK_API_KEY" \
  -X POST http://localhost:8000/api/v1/uploads -F "file=@chip_top.gds"
```

## Other Endpoints

### Health check

```bash
curl http://localhost:8000/health
```

### Queue status

```bash
curl http://localhost:8000/api/v1/queue
```

### List uploads

```bash
curl http://localhost:8000/api/v1/uploads
```

### List runs

```bash
curl http://localhost:8000/api/v1/prechecks
```

### Get logs

```bash
curl http://localhost:8000/api/v1/prechecks/def456.../logs
```

### Cancel a run

```bash
curl -X DELETE http://localhost:8000/api/v1/prechecks/def456...
```

### Download debug tarball (for failed runs)

```bash
curl -o debug.tar.gz http://localhost:8000/api/v1/debug/prechecks/def456...
```
