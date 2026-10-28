"""Manage the upstream Pyroscope APT package, files and systemd service."""

from __future__ import annotations

import contextlib
import hashlib
import os
import pwd
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib import error, request

from config_builder import DEFAULT_CONFIG_PATH, validate_package_version

CONFIG_PATH = Path(DEFAULT_CONFIG_PATH)
KEY_PATH = Path("/etc/apt/keyrings/grafana.gpg")
SOURCE_PATH = Path("/etc/apt/sources.list.d/grafana.list")
BINARY = "/usr/bin/pyroscope"


def _run(args: list[str], *, timeout: int = 300, **kwargs) -> subprocess.CompletedProcess:
    """Execute an argument list with bounded runtime and no command or output logging."""
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        **kwargs,
    )


def download_key() -> bytes:
    """Read Grafana's signing key over HTTPS with a size and time limit."""
    with request.urlopen("https://apt.grafana.com/gpg.key", timeout=30) as response:
        content = response.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("Grafana APT signing key exceeds size limit")
    return content


def install(version: str) -> None:
    """Install an exact supported APT release and leave it stopped for configuration."""
    validate_package_version(version)
    _run(["apt-get", "update"])
    _run(["apt-get", "install", "-y", "ca-certificates", "gpg"])
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _run(["gpg", "--batch", "--yes", "--dearmor", "--output", str(KEY_PATH)], input=download_key())
    SOURCE_PATH.write_text(f"deb [signed-by={KEY_PATH}] https://apt.grafana.com stable main\n")
    _run(["apt-get", "update"])
    _run(["apt-get", "install", "-y", f"pyroscope={version}"])
    stop()


def preserve_default_config(path: Path = CONFIG_PATH) -> None:
    """Retain the first package configuration once without replacing an earlier backup."""
    saved = path.with_suffix(path.suffix + ".package-default")
    if path.exists() and not saved.exists():
        shutil.copy2(path, saved)
        saved.chmod(0o600)


def ensure_data_dir(data_dir: str) -> None:
    """Prepare writable directories using no-follow descriptors to reject symlink races."""
    account = pwd.getpwnam("pyroscope")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(data_dir, flags)
    try:
        os.fchown(root_fd, account.pw_uid, account.pw_gid)
        os.fchmod(root_fd, 0o750)
        for directory in ("data", "blocks", "compactor"):
            with contextlib.suppress(FileExistsError):
                os.mkdir(directory, mode=0o750, dir_fd=root_fd)
            child_fd = os.open(directory, flags, dir_fd=root_fd)
            try:
                os.fchown(child_fd, account.pw_uid, account.pw_gid)
                os.fchmod(child_fd, 0o750)
            finally:
                os.close(child_fd)
    finally:
        os.close(root_fd)


def write_config(content: str, *, path: Path = CONFIG_PATH) -> None:
    """Atomically replace a private configuration, cleaning temporary files on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o640)
            try:
                account = pwd.getpwnam("pyroscope")
            except KeyError:
                account = None
            if account is not None:
                os.fchown(stream.fileno(), 0, account.pw_gid)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def read_config() -> str:
    """Return current managed file contents, or an empty string before installation."""
    try:
        return CONFIG_PATH.read_text()
    except FileNotFoundError:
        return ""


def config_digest(content: str) -> str:
    """Hash configuration for drift detection without persisting credentials in charm state."""
    return hashlib.sha256(content.encode()).hexdigest()


def verify_config(path: Path) -> None:
    """Parse and validate with Pyroscope's version exit path without starting modules."""
    _run([BINARY, "-config.file", str(path), "-version"], timeout=30)


def validate_candidate(content: str) -> None:
    """Validate a private temporary YAML file and remove it on either outcome."""
    with tempfile.TemporaryDirectory(prefix="pyroscope-config-") as directory:
        path = Path(directory) / "candidate.yml"
        path.write_text(content)
        path.chmod(0o600)
        verify_config(path)


def start() -> None:
    """Enable the package service and start it with a bounded systemd call."""
    _run(["systemctl", "enable", "--now", "pyroscope"], timeout=120)


def restart() -> None:
    """Restart the package service after configuration changes."""
    _run(["systemctl", "restart", "pyroscope"], timeout=120)


def stop() -> None:
    """Stop the package service before unit removal or storage detach."""
    _run(["systemctl", "stop", "pyroscope"], timeout=120)


def is_active() -> bool:
    """Check systemd without turning an inactive service into a failed Juju hook."""
    try:
        _run(["systemctl", "is-active", "--quiet", "pyroscope"], timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def is_ready(port: int) -> bool:
    """Check local readiness without retaining or logging HTTP response content."""
    try:
        with request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=5) as response:
            return response.status == 200
    except (OSError, error.URLError):
        return False


def wait_ready(port: int, *, timeout: int = 30) -> bool:
    """Poll local readiness within a bounded startup grace period."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_ready(port):
            return True
        time.sleep(1)
    return False


def get_version() -> str:
    """Extract the package binary's version without requiring a running service."""
    result = _run([BINARY, "-version"], timeout=10)
    output = result.stdout.decode() + result.stderr.decode()
    match = re.search(r"version\s+([0-9]+(?:\.[0-9]+){2})", output)
    if not match:
        raise ValueError("Unable to determine installed Pyroscope version")
    return match.group(1)
