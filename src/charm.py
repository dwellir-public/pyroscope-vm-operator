#!/usr/bin/env python3
"""Orchestrate the Pyroscope VM backend and its standard Juju integrations."""

from __future__ import annotations

import logging
import subprocess

import ops
import yaml
from charms.dwellir_observability.v0.machine_observability import (
    MachineObservabilityPayload,
    MetricsEndpoint,
    SourceTopology,
    serialize_machine_observability_payload,
)
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.pyroscope_coordinator_k8s.v0.profiling import ProfilingEndpointProvider
from cosl.interfaces.datasource_exchange import DatasourceDict, DatasourceExchange
from object_storage import S3Requirer

import pyroscope
from config_builder import (
    DEFAULT_DATA_DIR,
    S3StorageConfig,
    build_config,
    validate_package_version,
)

logger = logging.getLogger(__name__)
DATASOURCE_TYPE = "grafana-pyroscope-datasource"


class StorageNotReadyError(Exception):
    """Signal missing S3 configuration without selecting a different backend."""


class ReadinessError(RuntimeError):
    """Signal that a replacement configuration failed its startup grace period."""


class PyroscopeVmCharm(ops.CharmBase):
    """Manage a single Pyroscope instance with health-gated endpoint publication."""

    _stored = ops.StoredState()

    def __init__(self, framework: ops.Framework):
        """Wire lifecycle and relation events to a common reconciliation path."""
        super().__init__(framework)
        self._stored.set_default(
            installed_version="",
            intended_running=False,
            data_dir=DEFAULT_DATA_DIR,
            storage_detached=False,
            s3_configured=False,
            config_digest="",
            applied_port=4040,
        )
        self.profiling = ProfilingEndpointProvider(self.model.relations["profiling"], self.app)
        self.grafana = GrafanaSourceProvider(
            self,
            relation_name="grafana-source",
            source_type=DATASOURCE_TYPE,
            source_url=self._base_url("grafana-source"),
        )
        self.exchange = DatasourceExchange(
            self,
            provider_endpoint="send-datasource",
            requirer_endpoint=None,
        )
        self.s3 = S3Requirer(self, relation_name="s3")
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.config_changed, self._on_reconcile)
        self.framework.observe(self.on.upgrade_charm, self._on_reconcile)
        self.framework.observe(self.on.leader_elected, self._on_reconcile)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.health_action, self._on_health)
        self.framework.observe(
            self.on.pyroscope_persisted_storage_attached, self._on_storage_attached
        )
        self.framework.observe(
            self.on.pyroscope_persisted_storage_detaching, self._on_storage_detaching
        )
        for endpoint in (
            "profiling",
            "machine-observability",
            "grafana-source",
            "send-datasource",
            "replicas",
            "s3",
        ):
            for event in (
                "relation_created",
                "relation_joined",
                "relation_changed",
                "relation_departed",
                "relation_broken",
            ):
                self.framework.observe(getattr(self.on[endpoint], event), self._on_reconcile)
        self.framework.observe(self.s3.on.storage_connection_info_changed, self._on_reconcile)
        self.framework.observe(self.s3.on.storage_connection_info_gone, self._on_reconcile)

    def _on_install(self, _: ops.EventBase) -> None:
        """Install the pinned workload and preserve its original package configuration."""
        self.unit.status = ops.MaintenanceStatus("Installing Pyroscope")
        try:
            version = validate_package_version(str(self.config["package-version"]))
            pyroscope.install(version)
            pyroscope.preserve_default_config()
            self._stored.installed_version = version
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            self._failure("Pyroscope package installation failed; inspect unit logs", exc)

    def _on_start(self, event: ops.StartEvent) -> None:
        """Record desired service state and reconcile before starting it."""
        self._stored.intended_running = True
        self._on_reconcile(event)

    def _on_stop(self, _: ops.StopEvent) -> None:
        """Stop the service and withdraw public endpoints while preserving data."""
        self._stored.intended_running = False
        self._withdraw()
        pyroscope.stop()
        self.unit.status = ops.MaintenanceStatus("Pyroscope stopped")

    def _on_reconcile(self, event: ops.EventBase) -> None:
        """Resolve configuration, apply only validated candidates and refresh health."""
        if self.app.planned_units() != 1:
            self._withdraw()
            self.unit.status = ops.BlockedStatus("Only one Pyroscope unit is supported")
            return
        if self._stored.storage_detached:
            self._withdraw()
            self.unit.status = ops.BlockedStatus("Persistent storage detached; reattach to resume")
            return
        if not self._ensure_installed(event):
            return
        try:
            version = validate_package_version(str(self.config["package-version"]))
            storage = self._storage(event)
            config = build_config(
                data_dir=str(self._stored.data_dir),
                http_port=int(self.config["http-port"]),
                grpc_port=int(self.config["grpc-port"]),
                log_level=str(self.config["log-level"]),
                retention_period=str(self.config["retention-period"]),
                reporting_enabled=bool(self.config["reporting-enabled"]),
                s3=storage,
            )
            candidate = "# Generated by Juju. Configure through charm options.\n" + yaml.safe_dump(
                config,
                sort_keys=False,
            )
            if version != self._stored.installed_version:
                if not isinstance(event, ops.ConfigChangedEvent):
                    raise ValueError("package-version changes require config-changed")
                self._withdraw()
                pyroscope.install(version)
                self._stored.installed_version = version
            pyroscope.ensure_data_dir(str(self._stored.data_dir))
            self._apply(candidate)
            self._stored.applied_port = int(self.config["http-port"])
            if storage is not None:
                self._stored.s3_configured = True
            self._publish_observability()
            self.unit.set_workload_version(pyroscope.get_version())
            self._refresh_health()
        except StorageNotReadyError:
            self._withdraw()
            self.unit.status = ops.WaitingStatus(
                "Waiting for complete s3 relation; keeping current storage"
            )
        except (ValueError, OSError, subprocess.SubprocessError, ReadinessError) as exc:
            self._failure("Pyroscope configuration failed; previous configuration retained", exc)

    def _ensure_installed(self, event: ops.EventBase) -> bool:
        """Retry failed initial installation on config changes and preserve failure status."""
        if self._stored.installed_version:
            return True
        if isinstance(event, ops.ConfigChangedEvent):
            self._on_install(event)
            return bool(self._stored.installed_version)
        self._withdraw()
        if not isinstance(self.unit.status, ops.BlockedStatus):
            self.unit.status = ops.WaitingStatus("Waiting for package installation")
        return False

    def _storage(self, event: ops.EventBase) -> S3StorageConfig | None:
        """Read complete S3 settings and prevent silent fallback after relation removal."""
        relation = self.model.get_relation("s3")
        broken = isinstance(event, ops.RelationBrokenEvent) and event.relation.name == "s3"
        if relation is None or broken:
            if self._stored.s3_configured:
                raise StorageNotReadyError()
            return None
        details = self.s3.get_storage_connection_info(relation)
        if not all(details.get(key) for key in ("bucket", "endpoint", "access-key", "secret-key")):
            raise StorageNotReadyError()
        return S3StorageConfig.from_relation(dict(details))

    def _apply(self, candidate: str) -> None:
        """Preflight before replacement and restore the previous file if restart fails."""
        previous = pyroscope.read_config()
        changed = previous != candidate
        if changed:
            pyroscope.validate_candidate(candidate)
            pyroscope.write_config(candidate)
        if self._stored.intended_running:
            try:
                if not pyroscope.is_active():
                    pyroscope.start()
                elif changed:
                    pyroscope.restart()
                if changed:
                    ready = pyroscope.wait_ready(int(self.config["http-port"]))
                    if not ready and self._stored.config_digest:
                        raise ReadinessError()
            except (OSError, subprocess.SubprocessError, ReadinessError):
                if changed and previous:
                    pyroscope.write_config(previous)
                    try:
                        pyroscope.restart()
                    except (OSError, subprocess.SubprocessError):
                        logger.error("Pyroscope recovery restart failed")
                raise
        self._stored.config_digest = pyroscope.config_digest(candidate)

    def _on_update_status(self, _: ops.UpdateStatusEvent) -> None:
        """Check drift and runtime health without rewriting operator-edited files."""
        if (
            self._stored.config_digest
            and pyroscope.config_digest(pyroscope.read_config()) != self._stored.config_digest
        ):
            self._withdraw()
            self.unit.status = ops.BlockedStatus(
                "Configuration drift; use config-changed to reconcile"
            )
            return
        # Reconcile administrative gates without applying config on periodic status.
        if self.app.planned_units() != 1 or self._stored.storage_detached:
            self._withdraw()
            self.unit.status = ops.BlockedStatus("Check unit count and persistent storage")
            return
        if not self._stored.installed_version:
            self._ensure_installed(_)
            return
        if isinstance(self.unit.status, (ops.BlockedStatus, ops.WaitingStatus)) and (
            "configuration failed" in self.unit.status.message
            or "s3 relation" in self.unit.status.message
        ):
            return
        self._refresh_health()

    def _refresh_health(self) -> None:
        """Publish integrations only when the intended workload is active and ready."""
        if not self._stored.intended_running:
            self._withdraw()
            self.unit.status = ops.MaintenanceStatus("Pyroscope stopped")
        elif not pyroscope.is_active() or not pyroscope.is_ready(int(self._stored.applied_port)):
            self._withdraw()
            self.unit.status = ops.WaitingStatus("Waiting for Pyroscope readiness")
        else:
            self._publish()
            self.unit.status = ops.ActiveStatus(
                "ready, storage(s3)" if self._stored.s3_configured else "ready, storage(local)"
            )

    def _address(self, endpoint: str) -> str:
        """Resolve an integration's bound address and format IPv6 authority safely."""
        binding = self.model.get_binding(endpoint)
        address = (
            str(binding.network.bind_address) if binding and binding.network.bind_address else ""
        )
        return f"[{address}]" if ":" in address else address

    def _base_url(self, endpoint: str) -> str:
        """Construct a base URL using the applied listener rather than pending configuration."""
        address = self._address(endpoint)
        return f"http://{address}:{self._stored.applied_port}" if address else ""

    def _publish(self) -> None:
        """Advertise canonical profiling and Grafana data with explicit leader ownership."""
        address = self._address("profiling")
        if self.unit.is_leader() and address:
            self.profiling.publish_endpoint(
                f"{address}:{self._stored.applied_port}", insecure=True
            )
        self.grafana.update_source(self._base_url("grafana-source"))
        self._publish_observability()
        if self.unit.is_leader():
            sources: list[DatasourceDict] = [
                {"type": DATASOURCE_TYPE, "uid": uid, "grafana_uid": grafana_uid}
                for grafana_uid, source in self.grafana.get_source_data().items()
                for uid in source.datasource_uids.values()
            ]
            self.exchange.publish(datasources=sources)

    def _publish_observability(self) -> None:
        """Publish validated v3 source declarations without inventing unapproved alerts."""
        if not self.unit.is_leader():
            return
        payload = MachineObservabilityPayload(
            schema_version=3,
            charm_name=self.meta.name,
            source_topology=SourceTopology(
                model=self.model.name,
                model_uuid=self.model.uuid,
                application=self.app.name,
                unit=self.unit.name,
                charm_name=self.meta.name,
            ),
            metrics_endpoints=[
                MetricsEndpoint(targets=[f"localhost:{self._stored.applied_port}"])
            ],
            systemd_units=["pyroscope.service"],
            artifacts=[],
        )
        encoded = serialize_machine_observability_payload(payload)
        for relation in self.model.relations["machine-observability"]:
            relation.data[self.app]["payload"] = encoded

    def _withdraw(self) -> None:
        """Withdraw ingestion and datasource entries while retaining diagnostic telemetry."""
        for relation in self.model.relations["grafana-source"]:
            relation.data[self.unit].pop("grafana_source_host", None)
        if self.unit.is_leader():
            for relation in self.model.relations["profiling"]:
                for key in ("otlp_grpc_endpoint_url", "insecure"):
                    relation.data[self.app].pop(key, None)
            self.exchange.publish(datasources=[])

    def _failure(self, message: str, exc: Exception) -> None:
        """Report a failed operation without echoing credentials from command output."""
        self._withdraw()
        logger.error("Pyroscope operation failed (%s)", type(exc).__name__)
        self.unit.status = ops.BlockedStatus(message)

    def _on_storage_attached(self, event: ops.StorageAttachedEvent) -> None:
        """Use the attached mount for future config writes without moving or deleting data."""
        if event.storage.location is None:
            self.unit.status = ops.WaitingStatus("Waiting for persistent storage mount")
            return
        self._stored.data_dir = str(event.storage.location)
        self._stored.storage_detached = False
        self._on_reconcile(event)

    def _on_storage_detaching(self, _: ops.StorageDetachingEvent) -> None:
        """Stop before detach and prohibit fallback to an empty data directory."""
        self._stored.storage_detached = True
        self._withdraw()
        pyroscope.stop()
        self.unit.status = ops.BlockedStatus("Persistent storage detached; reattach to resume")

    def _on_health(self, event: ops.ActionEvent) -> None:
        """Return only service and readiness booleans for operator diagnostics."""
        event.set_results(
            {
                "service-active": pyroscope.is_active(),
                "ready": pyroscope.is_ready(int(self._stored.applied_port)),
            }
        )


if __name__ == "__main__":
    ops.main(PyroscopeVmCharm)
