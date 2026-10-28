"""Test host operations with filesystem fixtures and intercepted subprocess calls."""

import os
import subprocess
from unittest.mock import Mock

import pytest

import pyroscope


def test_preflight_uses_parser_and_version_without_starting_server(tmp_path, monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(pyroscope, "_run", run)
    pyroscope.verify_config(tmp_path / "candidate.yml")
    assert run.call_args.args[0] == [
        "/usr/bin/pyroscope",
        "-config.file",
        str(tmp_path / "candidate.yml"),
        "-version",
    ]
    assert run.call_args.kwargs["timeout"] == 30


def test_atomic_write_private_and_idempotent(tmp_path):
    path = tmp_path / "config.yml"
    pyroscope.write_config("secret-key: SENTINEL\n", path=path)
    assert path.read_text() == "secret-key: SENTINEL\n"
    assert path.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [path]
    pyroscope.write_config("new: value\n", path=path)
    assert path.read_text() == "new: value\n"


def test_write_failure_retains_previous_file_and_cleans_candidate(tmp_path, monkeypatch):
    path = tmp_path / "config.yml"
    path.write_text("previous")
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("full")))
    with pytest.raises(OSError):
        pyroscope.write_config("candidate", path=path)
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]


def test_install_pins_package_without_unbounded_shell_pipeline(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pyroscope, "_run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(pyroscope, "KEY_PATH", tmp_path / "key.gpg")
    monkeypatch.setattr(pyroscope, "SOURCE_PATH", tmp_path / "grafana.list")
    monkeypatch.setattr(pyroscope, "download_key", lambda: b"PUBLIC KEY")
    pyroscope.install("1.21.0")
    assert ["apt-get", "install", "-y", "pyroscope=1.21.0"] in calls
    assert ["systemctl", "stop", "pyroscope"] in calls
    assert "https://apt.grafana.com" in (tmp_path / "grafana.list").read_text()


def test_readiness_http_failure_is_not_ready(monkeypatch):
    monkeypatch.setattr(pyroscope.request, "urlopen", Mock(side_effect=OSError("unreachable")))
    assert pyroscope.is_ready(4040) is False


def test_readiness_requires_success(monkeypatch):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status = 200
    monkeypatch.setattr(pyroscope.request, "urlopen", Mock(return_value=response))
    assert pyroscope.is_ready(4040) is True


def test_readiness_wait_is_bounded(monkeypatch):
    monkeypatch.setattr(pyroscope, "is_ready", lambda port: False)
    times = iter([0, 0, 2])
    monkeypatch.setattr(pyroscope.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(pyroscope.time, "sleep", lambda _: None)
    assert pyroscope.wait_ready(4040, timeout=1) is False


def test_default_config_preserved_once(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("package default")
    pyroscope.preserve_default_config(path)
    path.write_text("managed")
    pyroscope.preserve_default_config(path)
    assert path.with_suffix(".yml.package-default").read_text() == "package default"


def test_runtime_failure_reports_false_and_stop_is_bounded(monkeypatch):
    run = Mock(side_effect=subprocess.CalledProcessError(1, ["systemctl"]))
    monkeypatch.setattr(pyroscope, "_run", run)
    assert pyroscope.is_active() is False
    with pytest.raises(subprocess.CalledProcessError):
        pyroscope.stop()
    assert run.call_args.kwargs["timeout"] == 120


def test_data_directory_rejects_workload_symlink_without_touching_target(tmp_path, monkeypatch):
    from types import SimpleNamespace

    root = tmp_path / "profiles"
    root.mkdir()
    victim = tmp_path / "outside"
    victim.mkdir(mode=0o700)
    (root / "blocks").symlink_to(victim, target_is_directory=True)
    monkeypatch.setattr(
        pyroscope.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
    )
    with pytest.raises((OSError, ValueError)):
        pyroscope.ensure_data_dir(str(root))
    assert victim.stat().st_mode & 0o777 == 0o700
