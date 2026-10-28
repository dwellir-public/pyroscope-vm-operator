# Library provenance

Vendored files are copied unchanged from the listed repositories and revisions.

| File under lib/ | Source repository | Commit | SHA-256 |
| --- | --- | --- | --- |
| `charms/dwellir_observability/v0/machine_observability.py` | `dwellir-observability-reference` | `bc5df52238e35c74681637884065e51709d83bf8` | `f93196c38bbd8343b1d72173e860e1adf5ddf04ce728fae36d6e57fc3916e679` |
| `charms/grafana_k8s/v0/grafana_source.py` | `loki-vm-operator` | `20b9192c065e73a798bd3e829d52b6561b5c8f19` | `2c8d1b72f9c2e5b99a143ab4a62b9acb004d50375598cb2c2d7b9570383863a8` |
| `charms/pyroscope_coordinator_k8s/v0/profiling.py` | `opentelemetry-collector-operator` | `c5d10698835f8b23a3cb346ae54fe0760b1a1c4b` | `c6b673586b12ab7503ae4f465082828845bb7957e5d029f009f4a6f3bde49ab2` |

The observability reference is the schema authority. Only its models and serializer
are reused; application publication is explicitly leader-owned in this charm.
Canonical profiling library LIBID `a04f470b17b64e9abcdb102f5458df55`, API 0,
patch 5 supplies the exact provider payload and JSON encoding. Grafana uses the
standard provider library and cosl datasource exchange. Source URLs are
https://github.com/dwellir-public/dwellir-observability-reference,
https://github.com/dwellir-public/loki-vm-operator and
https://github.com/dwellir-public/opentelemetry-collector-operator.
