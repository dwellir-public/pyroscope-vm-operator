# Development

Python dependencies and tooling live in `pyproject.toml` and the committed
`uv.lock`. Use Python 3.12 for Ubuntu 24.04 parity.

```bash
uv sync --locked --group dev --python 3.12
uv run tox -e format
uv run tox -e lint,static,unit
charmcraft pack
```

Charmcraft builds inside its managed LXD environment. Tests use pytest and
`ops.testing` for events, and direct filesystem/subprocess interception for host
operations. No test installs APT packages or controls the developer's systemd.
Vendored upstream libraries stay byte-identical to their provenance record.

## Retained-model integration tests

Use the existing nonproduction reference model. The suite deploys the local
artifact or refreshes only its `pyroscope-vm` application. It never removes apps,
relations, storage, or the model. It records before/after status in pytest's temp
directory and retains test profiles. Existing backend data is not erased.

```bash
JUJU_TEST_MODEL=localhost-localhost:admin/machine-observability-v3-reference \
CHARM_PATH="$PWD/pyroscope-vm_amd64.charm" \
GRAFANA_APP=grafana-vm \
uv run tox -e integration
```

Set `PYROSCOPE_APP` to change the backend application's name. `COLLECTOR_APP`
identifies an already deployed OpenTelemetry collector to integrate through
`send-profiles`. `JUJU_BIN` can select another installed Juju executable. An
existing backend is refreshed only if its charm name is `pyroscope-vm`.

The native ingestion test uploads a current synthetic pprof CPU profile. Both
profile tests require a fresh service name and nonzero stack samples. Set
`COLLECTOR_APP` to run OTLP ingestion through that collector. The default fixture
uses the OTLP v0.3.0 schema matching Pyroscope 1.21.0. Canonical collector
0.130.0 uses an older incompatible format.

For a custom protocol fixture, supply `OTLP_PROFILE_FIXTURE` as a binary
ExportProfilesServiceRequest with current sample timestamps and a unique
`OTLP_PROFILE_SERVICE` label and nonzero CPU samples. Set `COLLECTOR_OTLP_HTTP_PORT` if the collector's
HTTP receiver differs from 4318. Without either `COLLECTOR_APP` or
`TEST_COLLECTOR_UNIT`, the OTLP path is explicitly skipped. The suite waits for both backend and collector readiness.

For a separate version-matched collector fixture on a retained unit, set
`TEST_COLLECTOR_UNIT` and `COLLECTOR_OTLP_HTTP_PORT` instead of `COLLECTOR_APP`.
This verifies that explicit fixture pipeline and does not claim the incompatible
Canonical stable collector forwarded profiles. The fixture's version and lifecycle
must be recorded in docs/validation.md. No custom collector ships in the charm.
