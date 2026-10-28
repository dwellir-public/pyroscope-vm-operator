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
[validation](../validation.md). CI publication and store-refresh results will be
recorded below after execution.
