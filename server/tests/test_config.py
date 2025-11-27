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
