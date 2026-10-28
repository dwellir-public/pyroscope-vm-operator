"""Render Pyroscope 1.x monolithic configuration without Juju dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_DATA_DIR = "/var/lib/pyroscope"
DEFAULT_CONFIG_PATH = "/etc/pyroscope/config.yml"


def validate_package_version(value: str) -> str:
    """Require an exact supported 1.x pin to prevent implicit storage migrations."""
    if not re.fullmatch(r"1\.[0-9]+\.[0-9]+", value):
        raise ValueError("package-version must be an exact Pyroscope 1.x release")
    if tuple(int(part) for part in value.split(".")) < (1, 21, 0):
        raise ValueError("package-version requires Pyroscope >= 1.21.0 and < 2")
    return value


@dataclass(frozen=True)
class S3StorageConfig:
    """Hold normalized relation storage settings without exposing credentials in repr."""

    bucket: str
    endpoint: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = ""
    insecure: bool = False

    @classmethod
    def from_relation(cls, details: dict) -> S3StorageConfig:
        """Validate relation fields and normalize endpoint TLS and path-style access."""
        for key in ("bucket", "endpoint", "access-key", "secret-key"):
            if not isinstance(details.get(key), str) or not details[key].strip():
                raise ValueError(f"s3 relation requires {key}")
        if details.get("path"):
            raise ValueError("s3 relation path is unsupported; use a dedicated bucket")
        endpoint = urlsplit(details["endpoint"])
        if (
            endpoint.scheme not in ("http", "https")
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.path not in ("", "/")
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("s3 endpoint must be an HTTP(S) origin without credentials or path")
        try:
            endpoint.port
        except ValueError as exc:
            raise ValueError("s3 endpoint port is invalid") from exc
        return cls(
            bucket=details["bucket"],
            endpoint=endpoint.netloc,
            access_key_id=details["access-key"],
            secret_access_key=details["secret-key"],
            region=details.get("region", ""),
            insecure=endpoint.scheme == "http",
        )

    def as_dict(self) -> dict:
        """Translate normalized S3 settings into Pyroscope's object-store configuration."""
        return {
            "bucket_name": self.bucket,
            "endpoint": self.endpoint,
            "access_key_id": self.access_key_id,
            "secret_access_key": self.secret_access_key,
            "region": self.region,
            "insecure": self.insecure,
            "bucket_lookup_type": "path-style",
        }


def build_config(
    *,
    data_dir: str = DEFAULT_DATA_DIR,
    http_port: int = 4040,
    grpc_port: int = 9095,
    log_level: str = "info",
    retention_period: str = "14d",
    reporting_enabled: bool = False,
    s3: S3StorageConfig | None = None,
) -> dict:
    """Build one monolithic instance with explicit local paths and bounded retention."""
    if any(type(port) is not int or not 1 <= port <= 65535 for port in (http_port, grpc_port)):
        raise ValueError("http-port and grpc-port must be between 1 and 65535")
    if http_port == grpc_port:
        raise ValueError("http-port and grpc-port must differ")
    if log_level not in ("debug", "info", "warn", "error"):
        raise ValueError("log-level must be debug, info, warn or error")
    if not re.fullmatch(r"(?:0s|[1-9][0-9]*(?:s|m|h|d|w))", retention_period):
        raise ValueError("retention-period must be a positive duration or 0s")
    root = Path(data_dir)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("data directory must be an absolute path without traversal")
    return {
        "target": "all",
        "multitenancy_enabled": False,
        "server": {
            "http_listen_address": "0.0.0.0",
            "http_listen_port": http_port,
            "grpc_listen_address": "127.0.0.1",
            "grpc_listen_port": grpc_port,
            "log_level": log_level,
        },
        "pyroscopedb": {"data_path": str(root / "data")},
        "compactor": {"data_dir": str(root / "compactor")},
        "storage": (
            {"backend": "s3", "s3": s3.as_dict()}
            if s3
            else {"backend": "filesystem", "filesystem": {"dir": str(root / "blocks")}}
        ),
        "limits": {"compactor_blocks_retention_period": retention_period},
        "analytics": {"reporting_enabled": reporting_enabled},
        "tracing": {"enabled": False},
    }
