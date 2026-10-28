# Validation

This is the initial local-validation record. Publication and the subsequent
Charmhub refresh are recorded in the [initial edge release](releases/2026-10-28-initial-edge.md).

Evidence date: 2026-10-28. Scope is this new backend, its interfaces and deployment
in the retained localhost-localhost reference model. Iris and collector source
changes are excluded. No alert artifacts are shipped.

## Local checks

`uv` resolved the committed lock and installed dependencies for Python 3.12.
`tox -e lint,static,unit` passed. The unit suite has 48 tests, including invalid
config preservation, failed-install recovery, restart/readiness rollback,
leader-only publication, Canonical profiling databag decoding, v3 identity,
storage detach, and rejection of service-controlled directory symlinks.

`charmcraft pack` succeeded in its managed Ubuntu 24.04 LXD environment for amd64.
The final artifact is `pyroscope-vm_amd64.charm`, SHA-256
`711446e66a198e6b4bad4d6fa8ce971864b82f83677978f8f1f432b333756e9e`.
This is a local artifact; no Charmhub publication or GitHub push occurred.

The actual Grafana APT Pyroscope 1.21.0 binary accepted generated configuration
using `-config.file PATH -version`. S3 validation caught that Pyroscope requires
`bucket_lookup_type: path-style`; the renderer and regression assertion use
that value. The deployed configuration is mode 0640, owned by root:pyroscope.
Deployed source hashes match the artifact and checkout for all three modules.

## Retained deployment

Controller-qualified model:
`localhost-localhost:admin/machine-observability-v3-reference`.

The final local charm revision is 6. The initial stack already contained
Grafana, Loki, Mimir, their gateways,
Garage, Alloy subordinate, and reference workloads. They were reused. Added
`pyroscope-vm/0` on machine 63 and a Canonical `pyroscope-collector` subordinate
for compatibility testing. The latter remains its unmodified 2/stable revision
333 with collector snap 0.130.0. It exports host metrics to the existing Mimir
gateway. The incompatible profiling relation added during testing was removed;
no pre-existing application, relation, storage or model was removed.

Pyroscope consumes a dedicated Garage S3 bucket and publishes its datasource to
the existing Grafana. Alloy subordinate unit `alloy-sub/3` consumes the backend's
v3 declaration and forwards its metrics/journal to the existing backends.
[Initial model status](evidence/status-before.json) and
[final model status](evidence/status-after.json) preserve the application inventory.
Test profiles and backend storage remain available for inspection.

## Live results

The final retained-model Jubilant run passed both tests in 275.34 seconds.
Native pprof ingestion and OTLP ingestion through the explicit collector 0.148.0
fixture each produced a fresh service and nonzero CPU flamegraph samples with
the expected function name. The final workload was Pyroscope 1.21.0 backed by
Garage S3. A subsequent `ingester.v1.IngesterService/Flush` RPC returned HTTP 200,
and Garage reported 10 objects in the dedicated bucket.

Grafana provisioned datasource UID `PC47E7D3D99F2AF64` and its health API returned
HTTP 200 with `Data source is working`. The backend metrics scrape had up=1
with source topology labels; Loki returned fresh backend journal entries.
[Telemetry summary](evidence/telemetry-summary.json) records the queries without
credentials. [Final model status](evidence/status-after.json) records the retained
applications. All pre-existing applications remain present.

## Profiling protocol findings

Canonical's `profiling` endpoint name, interface and JSON application databag
contract are implemented using its unchanged library, API 0 patch 5. Unit tests
decode the published data with Canonical's model. This relation contract does
not define an experimental profiling protobuf revision.

Canonical collector 0.130.0 uses an earlier profile layout. Pyroscope 1.21.0
uses the versioned OTLP Profiles v0.3.0 layout. A real request to collector
0.130.0 returned HTTP 400 with `wrong wireType` for the newer profile sample.
Trying Pyroscope 1.17.4 also exposed an incompatible intermediate layout.
A direct test of 1.14.1 accepted the older encoding but rejected ordinary
resource `service.name` attributes as duplicate `service_name` labels. These
experiments do not establish a supported older backend recommendation.

The deployed workload was returned to 1.21.0. Synthetic data from the initial
1.21 test was retained in `/var/lib/pyroscope-initial-1.21-smoke.tgz` before
changing the new test workload's version. Those temporary version changes
only affected the new Pyroscope unit, not the pre-existing stack.

For the matching-protocol test, an official collector-contrib 0.148.0 binary
runs in the new backend's container as transient service `pyroscope-otlp-test`,
under the pyroscope account. It listens only on `127.0.0.1:14318` and forwards
OTLP gRPC to the backend. It is a test fixture, not part of the charm, and does
not replace Canonical's snap service. Its release archive checksum was verified
against the [upstream release checksums](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.148.0):
`224be33baa9eb534838e3d742d5327eff6a6bb60cdf4a16daf9c4e70d438fe00`.
The [fixture configuration](../tests/integration/fixtures/otelcol-0.148.yaml)
and integration tests make the selected path explicit.

## Before/target/actual matrix

| Requirement | Authority / applicability | Before | Disposition | Target | Actual evidence |
| --- | --- | --- | --- | --- | --- |
| BUILD-001 dependency ownership and uv packaging | required-baseline / shared | GAP: absent charm | Implement | PASS | Locked uv dependencies, tox lint/static/unit and managed Charmcraft pack passed |
| OBS-001 source ownership | required-baseline / telemetry | GAP | Implement | PASS | v3 unit assertions; live Mimir up=1 for localhost:4040 with source model/application/unit labels; fresh Loki entries |
| Canonical profiling contract | contract-required / profiling | GAP | Implement unchanged library | PASS contract; runtime conditional | Databag round-trip passed; Canonical collector 0.130.0 protobuf incompatibility remains explicit |
| Requested v3 schema | task-required / self-observability | GAP | Implement without schema changes | PASS | Unchanged authoritative library, schema_version=3, explicit topology and empty artifacts |
| Loki implementation pattern | task-required / structure | GAP | Adopt package/systemd/helper boundaries and recovery | PASS | Three focused modules, native preflight and recovery tests; private config permissions verified |
| Grafana datasource | contract-required / visualization | GAP | Reuse standard libraries | PASS | Provisioned plugin type grafana-pyroscope-datasource; Grafana health API returned 200, Data source is working |
| Preserve retained model | task-required / live validation | Existing stack active | Preserve | PASS | Initial/final inventory, no model or pre-existing app/relation/storage cleanup |
| Existing collectors, Iris and schema unchanged | task-required / scope | Clean source checkouts | Preserve | PASS | No code changes in those repositories; matching collector binary is an isolated test fixture |

This matrix covers the new backend and selected interfaces. It does not claim a
full estate compliance audit, a production rollout, or a tested Iris pipeline.

## Reproduce and inspect

Use the built local artifact and the existing model, with no cleanup fixture:

```bash
JUJU_TEST_MODEL=localhost-localhost:admin/machine-observability-v3-reference \
CHARM_PATH="$PWD/pyroscope-vm_amd64.charm" \
GRAFANA_APP=grafana-vm \
TEST_COLLECTOR_UNIT=pyroscope-vm/0 \
COLLECTOR_OTLP_HTTP_PORT=14318 \
uv run tox -e integration

juju status -m localhost-localhost:admin/machine-observability-v3-reference
juju run -m localhost-localhost:admin/machine-observability-v3-reference pyroscope-vm/leader health
```

The fixture can be stopped independently with
`sudo systemctl stop pyroscope-otlp-test` on the new backend unit. No production
collector upgrade is part of this work. Iris currently exposes Go pprof;
collecting or converting it remains separate work. Neither interface publication
nor the synthetic profile tests prove Iris-to-Pyroscope delivery.
