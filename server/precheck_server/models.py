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
