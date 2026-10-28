# Charm architecture

## Modules

`src/charm.py` owns Juju events, desired service state and health-gated endpoint
publication. `src/config_builder.py` validates options and renders Pyroscope 1.x
configuration independently of ops. `src/pyroscope.py` owns APT, systemd, atomic
files, native configuration preflight and bounded HTTP readiness checks.

## Install and runtime

Install the exact `package-version` from Grafana's signed APT repository. Keep
the package binary `/usr/bin/pyroscope`, configuration `/etc/pyroscope/config.yml`,
service `pyroscope`, and account `pyroscope`. Preserve the package configuration
once as `config.yml.package-default`. A failed initial install can be retried by
a corrected config change. The start hook sets intended-running state; config
changes and refresh honor that state. The stop hook withdraws endpoints and
stops the service.

## Configuration and recovery

Validate charm option values, render deterministic YAML, and preflight a private
temporary candidate using `pyroscope -config.file PATH -version`. Pyroscope has
no Loki-style `-verify-config` flag. The version path parses configuration and
exits without starting the workload's modules. Replace the configuration using
an atomic rename only after successful preflight. The file is root-owned and
readable by the package group, mode 0640; temporary candidates are private.

Compare content before writing or restarting. If a replacement restart fails,
restore the previous file and attempt recovery. If an accepted deployment fails
readiness after a config replacement, restore its previous file as well. Initial
startup readiness remains retryable. Periodic status checks detect manual drift
without replacing files. Only configuration digests are stored in Juju local
state; S3 credentials are not copied into StoredState, logs, or action output.

## Storage and scaling

One monolithic unit is supported. More units cause blocked status and withdraw
ingestion advertisements. No clustering or high-availability claim is made.
`pyroscope-persisted` mounts at `/var/lib/pyroscope`. Local blocks, ingester data
and compactor scratch files live in its `blocks`, `data` and `compactor`
subdirectories. Ownership updates use no-follow directory descriptors, including
for service-owned children, so a workload-created symlink cannot redirect a root
ownership change.

The standard `s3` library supplies credentials, bucket, endpoint and region.
Normalize the HTTP(S) origin and use path-style lookup for Garage compatibility.
Reject bucket paths rather than silently ignore them. An incomplete relation
waits; removal after accepting S3 never silently selects filesystem storage.
Backend changes do not migrate existing profiles. Detach stops the service and
blocks until a storage mount is attached again. No path recursively deletes or
moves workload data.

## Relations

`profiling` is Canonical's provider contract, including application databag JSON
encoding and the `insecure` flag. Pyroscope's HTTP port handles OTLP gRPC, native
push, query and readiness. The separate internal gRPC listener stays on loopback.
Publish the bound profiling address only when active and ready. Remove ingestion
and Grafana host entries when unavailable. The service uses plaintext inside the
trusted model network; ingress and TLS termination are not part of this release.

`grafana-source` uses the standard upstream library and the plugin ID
`grafana-pyroscope-datasource`. `send-datasource` exchanges Grafana-assigned UID
mappings through cosl. `machine-observability` serializes a source-only v3 payload
with the authoritative reference library, explicit source topology, `/metrics`,
`pyroscope.service` journal collection and an empty alert-artifact list. It
publishes backend self-observability rather than extending v3 with profile sources.
Application-level publication is leader-only. Metrics use the applied port,
not a pending or rejected configuration value.

## Upgrades and validation

Charm refresh reconciles charm-owned configuration without an APT workload
upgrade. Explicit package-version changes install the requested supported 1.x
version. Profile protobuf compatibility must be checked separately from the
relation schema. Canonical collector 0.130.0 cannot export profiles to this
Pyroscope 1.21.0 pin. 2.x requires a separately designed storage migration. Unit tests cover
lifecycle, contract serialization, recovery and filesystem operations. Jubilant
tests use a local packed artifact and the explicitly selected retained reference
model. See [validation evidence](validation.md) for tested and untested paths.
