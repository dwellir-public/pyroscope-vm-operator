# Pyroscope VM

Dwellir's Ubuntu machine charm for Grafana Pyroscope. It receives profiles using
native Pyroscope HTTP and OpenTelemetry OTLP gRPC, and publishes a Grafana
profiling datasource. The charm follows the Loki VM package, systemd and
configuration-management patterns.

The first release supports one monolithic unit on Ubuntu 24.04 amd64, with
filesystem storage or a related S3 bucket. It pins Pyroscope 1.21.0. Pyroscope
2.x storage architecture migration and clustering are outside this release.

## Deploy and integrate

The published development channel is `latest/edge`:

```bash
juju deploy pyroscope-vm --channel latest/edge
```

Build in Charmcraft's managed LXD environment:

```bash
charmcraft pack
juju deploy ./pyroscope-vm_amd64.charm pyroscope-vm
juju integrate opentelemetry-collector:send-profiles pyroscope-vm:profiling
juju integrate grafana-vm:grafana-source pyroscope-vm:grafana-source
```

Select the actual generated artifact filename if Charmcraft uses another name.
For object storage, use a dedicated bucket through the standard relation:

```bash
juju integrate garage-vm:s3 pyroscope-vm:s3
```

Changing the storage backend does not migrate existing profiles. Configure the
intended backend before sending production profiles. Removing an established S3
relation leaves the unit waiting for credentials; it does not fall back to local
storage. Detaching persistent storage stops the workload until reattachment.

Publish the backend's own metrics and journal to existing Alloy collectors:

```bash
juju integrate pyroscope-vm:juju-info alloy-sub:juju-info
juju integrate pyroscope-vm:machine-observability alloy-sub:machine-observability
```

A machine-local `alloy-vm` can consume `machine-observability` instead. These
relations collect Pyroscope's operational metrics and logs. No profiling source
extension is added to Dwellir's v3 schema.

## Interfaces

| Endpoint | Direction | Interface | Purpose |
| --- | --- | --- | --- |
| `profiling` | provides | `profiling` | Canonical OTLP gRPC ingestion endpoint |
| `grafana-source` | provides | `grafana_datasource` | Pyroscope datasource for Grafana VM or K8s |
| `send-datasource` | provides | `grafana_datasource_exchange` | Grafana-assigned datasource UID mappings |
| `machine-observability` | provides | `machine_observability` | v3 metrics, journal and source topology |
| `s3` | requires | `s3` | Dedicated object storage bucket and credentials |
| `replicas` | peers | `pyroscope_replica` | Juju peer lifecycle; clustering is unsupported |

`profiling` uses Canonical's unchanged provider library. Its application databag
contains JSON-encoded `otlp_grpc_endpoint_url` and `insecure`. Pyroscope serves
OTLP gRPC on the HTTP listener, normally port 4040. Its separate internal gRPC
listener is not the advertised OTLP endpoint.

The listener uses plaintext on the trusted model network, with `insecure=true`
and multitenancy disabled. The charm does not expose the application through
`juju expose`, ingress, or public TLS. Bind the relation to the intended private
network. A standard HTTP proxy must support cleartext HTTP/2 to proxy OTLP gRPC.

## Iris and profile collection

The intended route is Iris profiling, a suitable collector, and this backend.
The existing OpenTelemetry collector charm forwards OTLP profiles through its
`send-profiles` relation. Iris currently exposes Go pprof; that is a different
protocol from OTLP. The forwarding relation alone does not add pprof scraping to
the collector or instrument Iris. This repository changes neither Iris nor the
collectors and does not claim Iris-to-Pyroscope delivery without a compatible
source pipeline.

Native Alloy `pyroscope.write` can send to `http://<pyroscope-address>:4040` when
configured externally. Existing Alloy charms do not yet discover this backend
through a profiling relation. No Alloy charm changes are included.

## Version compatibility

The `profiling` endpoint matches Canonical's name, interface and JSON databag
contract. Actual OTLP profile delivery also requires compatible experimental
protobuf versions. Canonical collector charm `2/stable`, revision 333, installs
collector 0.130.0. Its profile encoding is incompatible with Pyroscope 1.21.0.
The unchanged interface name does not imply wire-format compatibility.

Use a collector version compatible with Pyroscope's OTLP Profiles v0.3.0 format,
or native Pyroscope ingestion. See [validation](docs/validation.md) for the tested
collector version and remaining Iris collection work. No collector source changes
or Dwellir schema changes are included in this charm.

## Operations

```bash
juju run pyroscope-vm/leader health
juju config pyroscope-vm retention-period=30d
juju ssh pyroscope-vm/0 -- sudo journalctl -u pyroscope -n 100
```

The charm validates candidates before replacing `/etc/pyroscope/config.yml`.
Rejected changes retain the working file. A failed replacement restart restores
the prior file and attempts service recovery. Periodic status reports manual
configuration drift. A subsequent config change reconciles managed config.
Charm refresh does not upgrade the APT workload. Changing `package-version`
requests an exact supported 1.x workload release; test upgrades before use.

See [architecture](docs/charm-architecture.md), [development](DEVELOPING.md),
[library provenance](docs/library-provenance.md), and [validation](docs/validation.md).
