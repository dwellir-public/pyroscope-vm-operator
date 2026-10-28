"""Verify lifecycle and interface behavior through Juju event simulation."""

import dataclasses
import json
import subprocess
from typing import cast
from unittest.mock import Mock

import ops
import pytest
from charms.pyroscope_coordinator_k8s.v0.profiling import ProfilingAppDatabagModel
from ops.testing import Context, Model, Relation, State, Storage, StoredState

import pyroscope
from charm import PyroscopeVmCharm


@pytest.fixture
def host(monkeypatch):
    memory = {"text": "", "active": True, "ready": True}
    mocks = {}
    for name in (
        "install",
        "preserve_default_config",
        "ensure_data_dir",
        "validate_candidate",
        "start",
        "stop",
        "restart",
    ):
        mocks[name] = Mock()
        monkeypatch.setattr(pyroscope, name, mocks[name])
    monkeypatch.setattr(pyroscope, "read_config", lambda: memory["text"])
    monkeypatch.setattr(pyroscope, "write_config", lambda content: memory.update(text=content))
    monkeypatch.setattr(pyroscope, "is_active", lambda: memory["active"])
    monkeypatch.setattr(pyroscope, "is_ready", lambda port: memory["ready"])
    monkeypatch.setattr(pyroscope, "wait_ready", lambda port: memory["ready"])
    monkeypatch.setattr(pyroscope, "get_version", lambda: "1.21.0")
    return memory, mocks


@pytest.fixture
def ctx():
    return Context(PyroscopeVmCharm, charm_root=".")


def installed(**kwargs):
    return State(
        leader=True,
        model=Model(name="reference", uuid="00000000-0000-4000-8000-000000000001", type="lxd"),
        stored_states=[
            StoredState(
                owner_path="PyroscopeVmCharm",
                content={
                    "installed_version": "1.21.0",
                    "intended_running": True,
                },
            )
        ],
        **kwargs,
    )


def test_install_pins_package_but_does_not_start(ctx, host):
    result = ctx.run(ctx.on.install(), State())
    host[1]["install"].assert_called_once_with("1.21.0")
    host[1]["preserve_default_config"].assert_called_once()
    host[1]["start"].assert_not_called()
    assert isinstance(result.unit_status, ops.MaintenanceStatus)


def test_start_publishes_canonical_otlp_and_v3(ctx, host):
    profiling = Relation(endpoint="profiling")
    observability = Relation(endpoint="machine-observability")
    result = ctx.run(ctx.on.start(), installed(relations=[profiling, observability]))
    assert isinstance(result.unit_status, ops.ActiveStatus)
    data = result.get_relation(profiling.id).local_app_data
    model = ProfilingAppDatabagModel.model_validate(
        {key: json.loads(value) for key, value in data.items()}
    )
    assert model.otlp_grpc_endpoint_url.endswith(":4040")
    assert "http://" not in model.otlp_grpc_endpoint_url
    assert model.insecure is True
    payload = json.loads(result.get_relation(observability.id).local_app_data["payload"])
    assert payload["schema_version"] == 3
    assert payload["artifacts"] == []
    assert payload["source_topology"]["model"] == "reference"
    assert payload["source_topology"]["unit"] == "pyroscope-vm/0"
    assert payload["systemd_units"] == ["pyroscope.service"]
    assert payload["metrics_endpoints"][0]["targets"] == ["localhost:4040"]


def test_nonleader_does_not_write_app_databags(ctx, host):
    relation = Relation(endpoint="profiling")
    state = dataclasses.replace(installed(relations=[relation]), leader=False)
    result = ctx.run(ctx.on.start(), state)
    assert result.get_relation(relation.id).local_app_data == {}


def test_invalid_config_preserves_working_file(ctx, host):
    host[0]["text"] = "working"
    result = ctx.run(ctx.on.config_changed(), installed(config={"retention-period": "bad"}))
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert host[0]["text"] == "working"
    host[1]["restart"].assert_not_called()


def test_failed_preflight_does_not_write_or_log_candidate(ctx, host, caplog):
    host[0]["text"] = "previous"
    host[1]["validate_candidate"].side_effect = subprocess.CalledProcessError(
        1, ["pyroscope"], stderr=b"SECRET_SENTINEL"
    )
    result = ctx.run(ctx.on.config_changed(), installed())
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert host[0]["text"] == "previous"
    assert "SECRET_SENTINEL" not in caplog.text


def test_restart_failure_restores_previous_configuration(ctx, host):
    host[0]["text"] = "previous"
    host[1]["restart"].side_effect = [subprocess.CalledProcessError(1, ["systemctl"]), None]
    result = ctx.run(ctx.on.config_changed(), installed())
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert host[0]["text"] == "previous"
    assert host[1]["restart"].call_count == 2


def test_not_ready_withdraws_advertised_endpoint(ctx, host):
    host[0]["ready"] = False
    profiling = Relation(
        endpoint="profiling",
        local_app_data={"otlp_grpc_endpoint_url": json.dumps("old:4040"), "insecure": "true"},
    )
    result = ctx.run(ctx.on.start(), installed(relations=[profiling]))
    assert isinstance(result.unit_status, ops.WaitingStatus)
    assert result.get_relation(profiling.id).local_app_data == {}


def test_update_status_preserves_drift(ctx, host):
    host[0]["text"] = "manual edit"
    state = installed()
    stored = next(iter(state.stored_states))
    cast(dict, stored.content)["config_digest"] = pyroscope.config_digest("expected")
    result = ctx.run(ctx.on.update_status(), state)
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert "drift" in result.unit_status.message
    assert host[0]["text"] == "manual edit"


def test_extra_units_block_without_reconfiguring(ctx, host):
    result = ctx.run(ctx.on.config_changed(), installed(planned_units=2))
    assert isinstance(result.unit_status, ops.BlockedStatus)
    host[1]["validate_candidate"].assert_not_called()


def test_charm_refresh_does_not_upgrade_package(ctx, host):
    result = ctx.run(ctx.on.upgrade_charm(), installed())
    host[1]["install"].assert_not_called()
    assert isinstance(result.unit_status, ops.ActiveStatus)


def test_stopped_unit_remains_stopped_on_config_change(ctx, host):
    state = installed()
    cast(dict, next(iter(state.stored_states)).content)["intended_running"] = False
    ctx.run(ctx.on.config_changed(), state)
    host[1]["start"].assert_not_called()
    host[1]["restart"].assert_not_called()


def test_stop_withdraws_endpoint(ctx, host):
    relation = Relation(
        endpoint="profiling",
        local_app_data={"otlp_grpc_endpoint_url": json.dumps("old:4040"), "insecure": "true"},
    )
    result = ctx.run(ctx.on.stop(), installed(relations=[relation]))
    host[1]["stop"].assert_called_once()
    assert result.get_relation(relation.id).local_app_data == {}


def test_storage_detach_stops_without_falling_back(ctx, host):
    storage = Storage("pyroscope-persisted")
    state = installed(storages=[storage])
    result = ctx.run(ctx.on.storage_detaching(storage), state)
    host[1]["stop"].assert_called_once()
    assert isinstance(result.unit_status, ops.BlockedStatus)
    host[1]["validate_candidate"].assert_not_called()


def test_s3_removal_does_not_silently_switch_to_local(ctx, host):
    relation = Relation(endpoint="s3")
    state = installed(relations=[relation])
    cast(dict, next(iter(state.stored_states)).content)["s3_configured"] = True
    result = ctx.run(ctx.on.relation_broken(relation), state)
    assert isinstance(result.unit_status, ops.WaitingStatus)
    host[1]["validate_candidate"].assert_not_called()


def test_health_action_has_no_config_or_credentials(ctx, host):
    ctx.run(ctx.on.action("health"), installed())
    assert ctx.action_results == {"service-active": True, "ready": True}


def test_corrected_config_retries_initial_package_install(ctx, host):
    failed = ctx.run(ctx.on.install(), State(config={"package-version": "bad"}))
    assert isinstance(failed.unit_status, ops.BlockedStatus)
    corrected = dataclasses.replace(failed, config={"package-version": "1.21.0"})
    result = ctx.run(ctx.on.config_changed(), corrected)
    host[1]["install"].assert_called_once_with("1.21.0")
    assert not isinstance(result.unit_status, ops.WaitingStatus)


def test_readiness_timeout_rolls_back_previously_accepted_config(ctx, host):
    host[0]["text"] = "previous"
    host[0]["ready"] = False
    state = installed()
    cast(dict, next(iter(state.stored_states)).content)["config_digest"] = pyroscope.config_digest(
        "previous"
    )
    result = ctx.run(ctx.on.config_changed(), state)
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert host[0]["text"] == "previous"
    assert host[1]["restart"].call_count == 2


def test_start_preserves_initial_install_error(ctx, host):
    failed = ctx.run(ctx.on.install(), State(config={"package-version": "bad"}))
    result = ctx.run(ctx.on.start(), failed)
    assert isinstance(result.unit_status, ops.BlockedStatus)
    assert result.unit_status.message == failed.unit_status.message
