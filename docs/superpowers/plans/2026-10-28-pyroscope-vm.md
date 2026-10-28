# Pyroscope VM implementation plan

Execute inline with executing-plans. User has approved implementation and testing against the retained localhost-localhost stack.

**Goal:** Deliver a standalone Pyroscope machine backend with Canonical profiling integration and Dwellir v3 self-observability.

**Architecture:** Juju orchestration in charm.py; host operations in pyroscope.py; pure rendering in config_builder.py. Reuse authoritative relation libraries unchanged.

**Tech stack:** Python >=3.10, ops 3, pydantic, object-storage-charmlib, cosl, pytest/ops.testing, Jubilant, uv/tox, Charmcraft uv plugin.

## Before/target matrix

Scope: new backend only, evidence 2026-10-28. Before is absent for every new-charm capability. Actual results belong in docs/validation.md.

| Requirement/source | Authority / applicability | Before | Disposition | Target | Verification |
| --- | --- | --- | --- | --- | --- |
| BUILD-001, installed dwellir-charm-development generic/standards.md | required-baseline / shared | GAP: no charm | Implement packaging and lock | PASS | uv lock check, lint/unit, pack |
| OBS-001, installed skill juju-topology.md | required-baseline / telemetry | GAP | Publish backend identity | PASS static, live conditional | source topology unit assertions, backend metrics query |
| Canonical profiling library LIBID a04f470b17b64e9abcdb102f5458df55 patch 5 | contract-required / profiling | GAP | Vendor unchanged, publish actual OTLP endpoint | PASS static, live conditional | requirer round-trip and collector ingestion |
| v3 reference bc5df52238e35c74681637884065e51709d83bf8 | task-required / self telemetry | GAP | Vendor unchanged, publish v3 with empty artifacts | PASS | reference validator and bytes hash |
| Loki VM 20b9192c065e73a798bd3e829d52b6561b5c8f19 | task-required / structure | GAP | Adopt helper boundaries, APT, systemd, config preservation | PASS | lifecycle and recovery tests |
| Standard Grafana datasource/exchange | contract-required / visualization | GAP | Reuse standard libraries | PASS static, live conditional | databags and Grafana provisioning |
| Preserve retained models, user instruction | task-required / live testing | UNKNOWN model access | Explicit controller/model, no cleanup | PASS conditional on access | record status before/after |
| Existing collectors/schema/Iris unchanged | task-required / scope | PASS clean references | Preserve | PASS | repository status |

Outcome: backend capabilities added. Existing consumers stay unchanged. Live claims depend on controller access. No alerts, clustering, source-collection changes or workload storage migrations are included.

## Tasks

- [x] Record design, source provenance and create repository tooling. Copy unchanged profiling, grafana_source and machine_observability libraries. Declare consolidated metadata and uv dependencies.
- [x] Write failing tests for filesystem/S3 rendering, invalid values and canonical endpoint data. Run pytest and capture missing implementation failures. Implement config_builder.py and endpoint helpers until those tests pass.
- [x] Write failing helper tests for config preflight, atomic writes, readiness and package installation. Implement pyroscope.py using upstream paths; verify candidate with `pyroscope -config.file PATH -version` because Pyroscope has no Loki `-verify-config` flag.
- [ ] Write ops.testing event tests for lifecycle, v3 identity, profiling publication, rollback, relation removal and storage safety. Implement charm.py and verify those tests.
- [x] Add retained-model Jubilant tests requiring explicit localhost-localhost model and CHARM_PATH. Inspect existing status first. Deploy or refresh only the test backend, integrate with existing collector/Grafana, and query newly ingested profiles. Never run temp_model cleanup against the retained stack.
- [x] Run format/lint/static/unit, lock validation and Charmcraft build. Run live tests if controller access is available. Record exact commands, failures and residual limits in docs/validation.md, then review code and changed files.

## Execution notes

User approved implementation and retained-model reuse. Later permission changes enabled
network/controller access. All successful Charmcraft builds used managed LXD,
without destructive-mode builds after the user specified that constraint.
Runtime profiling protocol incompatibility is recorded in ../../validation.md.
Final check and live results are maintained there.
