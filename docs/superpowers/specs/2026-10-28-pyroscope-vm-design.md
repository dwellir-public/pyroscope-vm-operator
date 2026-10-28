# Pyroscope VM design

Approved in conversation on 2026-10-28. Build `pyroscope-vm` in this independent repository using Loki VM's module and lifecycle patterns. No changes to Alloy, Iris, the collector, or the observability schema.

## Architecture

`src/charm.py` handles Juju events, relation publication and statuses. `src/pyroscope.py` handles APT installation, systemd, atomic files, configuration preflight and readiness. `src/config_builder.py` renders and validates a single-binary deployment. Use the upstream package paths `/usr/bin/pyroscope`, `/etc/pyroscope/config.yml`, `/var/lib/pyroscope`, and service `pyroscope`.

Provide Canonical `profiling` using its unchanged library and application databag model. Publish an actual OTLP gRPC endpoint, never relabel a native HTTP push URL as OTLP. Preserve native HTTP ingestion as part of Pyroscope. Publish `grafana-source` using type `grafana-pyroscope-datasource` and `send-datasource` using the standard exchange library. Publish v3 `machine-observability` for this backend's metrics and journal, with explicit source topology and `artifacts=[]`.

Start with one monolithic unit, local filesystem or related S3 storage. Block multi-unit deployment explicitly rather than advertise unsupported clustering. Persistent storage is `pyroscope-persisted`; detach stops the workload rather than silently replacing its data directory. Existing data is never deleted. Storage backend changes are configuration changes, not automatic data migrations.

## Lifecycle and configuration

Install from Grafana APT. Preserve package defaults before replacing configuration. Pin the package version through charm configuration and keep workload upgrades separate from charm refresh. Validate candidate YAML and the workload's parse-only command before writing it. Retain the prior valid file when a candidate is rejected. Roll back the file and attempt service recovery after restart failure. Report configuration drift on periodic status without overwriting it. Readiness failures are retryable waiting status. Never publish an unavailable endpoint as healthy.

## Validation

Use pytest with ops.testing for event behavior and plain tests for workload/configuration helpers. Verify exact compatibility with Canonical's profiling library, v3 serialization, invalid configuration, S3 credential handling, storage lifecycle, recovery and endpoint withdrawal. Use uv, tox and Charmcraft. Reuse the user-selected `localhost-localhost` controller and existing nonproduction observability/reference models; never destroy models or remove existing applications. Live tests must use an explicit model and built charm, preserve added resources and verify actual ingestion and queryability. OTLP protocol revisions must match between collector and Pyroscope; forwarding support alone does not prove Iris pprof collection.
