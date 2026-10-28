# Initial latest/edge release

## Preparation

The user authorized publication to `latest/edge` and refreshing the existing
`localhost-localhost:admin/machine-observability-v3-reference` deployment from
that channel. The public source repository is
[dwellir-public/pyroscope-vm-operator](https://github.com/dwellir-public/pyroscope-vm-operator).
The profiling source and protocol compatibility gaps are tracked in
[iris-operator issue 20](https://github.com/dwellir-public/iris-operator/issues/20).

The release action follows Loki VM's release.yml from source commit
`08ce2f3eaa3a60ba4141e86128136aa03e379557`. It preserves manual dispatch,
Ubuntu 24.04 amd64 artifacts, Charmhub upload to latest/edge, and a GitHub release
named from the Charmhub revision. It replaces the destructive build invocation
with a managed LXD build to preserve the user's earlier build constraint.
The matching Loki charm-tests.yml is used for push and pull-request checks.

Charmcraft confirmed that `pyroscope-vm` was already registered to the Dwellir
account. Authorized credentials were used to export an Actions token restricted
to that package and channel, with package-view/package-manage permissions and a
one-year lifetime. The token is stored as the repository secret CHARMHUB_TOKEN.
Its private temporary export was removed after installation. No credential
content is stored in this repository.

Local format, lint, static and all 48 unit tests passed before publication.
The initial backend build and retained-model profiling evidence is recorded in
[validation](../validation.md). The publication and store-refresh results follow.

## Published artifacts

- Release source commit: `2c64a70e616df95c68b47852b61495ca5666967b`.
- [GitHub test run](https://github.com/dwellir-public/pyroscope-vm-operator/actions/runs/40729130213): successful, including 48 unit tests, lint and static checks.
- [Release action](https://github.com/dwellir-public/pyroscope-vm-operator/actions/runs/40729273725): all three jobs successful.
- Base/architecture: Ubuntu 24.04 amd64.
- [Charmhub package](https://charmhub.io/pyroscope-vm): `latest/edge`, revision **1**. Stable, candidate and beta remain closed.
- [GitHub release](https://github.com/dwellir-public/pyroscope-vm-operator/releases/tag/latest-edge-r1): `latest-edge-r1`, including `pyroscope-vm_amd64.charm`.
- Published artifact SHA-256: `900fcb1dfbe0f65f3479465c460b7ddd7efa82a65e55cf8f97dc89e230517e5e`.

The Charmhub download and GitHub Actions artifact were byte-for-byte identical.
Their runtime modules also match the locally tested source. The action built with
`charmcraft pack --platform amd64 --quiet` using its managed LXD environment.
No local artifact was uploaded manually.

## Store refresh and runtime verification

The existing `pyroscope-vm` application in
`localhost-localhost:admin/machine-observability-v3-reference` was refreshed with:

```bash
juju refresh -m localhost-localhost:admin/machine-observability-v3-reference \
  pyroscope-vm --switch ch:pyroscope-vm --channel latest/edge
```

Juju reports Charmhub origin, revision 1, channel latest/edge, and workload version
1.21.0. The application is active with `ready, storage(s3)`. The health action
reports service-active=True and ready=True. The workload retained PID 35438 and
its original start timestamp `2026-10-28 16:14:36 UTC` across the refresh.
All application names present before this publication refresh remain present.

Fresh native pprof and OTLP fixture requests were then ingested and queried
against the store-installed charm. Both paths returned nonzero CPU stacks with
the expected function names. These checks called the integration test bodies
without the fixture that deploys a local charm, so the application retained its
Charmhub origin and channel. The separate collector-contrib 0.148.0 fixture was
used for OTLP; Canonical collector 0.130.0 remains incompatible as documented.

### Actual outcomes against the release plan

| Requirement | Before | Target | Actual |
| --- | --- | --- | --- |
| Public repository | Local code only | Published source | PASS: main and release source commit available in dwellir-public |
| Loki-style release pipeline | Check workflow only | Manual edge release with managed build | PASS: release action succeeded; only artifact names and managed-build setup differ from the reference |
| CI credentials | Missing repository secret | Restricted CHARMHUB_TOKEN | PASS: Charmcraft export installed through GitHub secrets; action authenticated successfully |
| Iris follow-up | No open tracking issue | Actionable bug report | PASS: issue 20 describes source collection, protocol compatibility and acceptance tests |
| Initial edge publication | Registered name, no releases | Ubuntu 24.04 amd64 release | PASS: revision 1 published to latest/edge; matching GitHub artifact |
| Retained model update | Local charm revision 6 | Store revision tracking edge | PASS: Charmhub revision 1, active, same workload process, fresh profiling checks passed |

The runtime source files did not change in this publication task. No production
rollout or stable-channel promotion was performed. The Iris collection fix is
tracked in its issue and is not implemented by publishing this backend.
