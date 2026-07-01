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
