# Initial Pyroscope VM publication

User authorized creating a public repository, filing an Iris bug issue, exporting
Charmcraft credentials for CI, releasing latest/edge through GitHub Actions, and
refreshing the retained localhost-localhost deployment from that channel.

The release workflow follows Loki VM's current release.yml. Keep its dispatch
trigger, Ubuntu 24.04 amd64 build, artifact transfer, Charmhub upload/release and
GitHub release jobs. Rename the workload/artifact references. Use managed LXD
instead of Loki's destructive build command to preserve the user's earlier build
constraint. Reuse the Loki unit/lint/static workflow.

## Before/target matrix

| Requirement | Authority / applicability | Before | Disposition | Target | Verification |
| --- | --- | --- | --- | --- | --- |
| Loki release workflow structure | task-required / CI | GAP: checks only | Add release.yml and matching charm-tests.yml | PASS with managed-build adaptation | Workflow comparison and successful dispatch |
| Managed builds | task-required / build | PASS locally | Preserve in CI | PASS | No destructive-mode command; managed LXD build logs |
| Repository publication | task-required / release | GAP: local repository only | Create public dwellir-public/pyroscope-vm-operator and push main | PASS | GitHub repository identity and source commit |
| CI credential installation | task-required / release | GAP: no secret | Export package/channel-restricted token using authorized login, store as CHARMHUB_TOKEN | PASS | Secret metadata and successful upload; no credential content in evidence |
| Iris profiling gap tracking | task-required / follow-up | GAP: no open issue | File bug with verified findings, fix options and acceptance checks | PASS | Issue URL |
| latest/edge initial publication | task-required / release | UNKNOWN Charmhub registration | Resolve registration, dispatch release action | PASS | Workflow success, revision/channel and artifact digest |
| Retained reference model refresh | task-required / deployment | Local charm revision 6 | Refresh pyroscope-vm from verified Charmhub revision | PASS | Store origin/channel, readiness, unchanged workload PID where applicable |

## Execution

1. Confirm account/repository ownership, workflow source and existing registration.
2. Create repository and Iris issue with actionable profiling instructions.
3. Install workflows; validate locally, commit and push to main.
4. Export a restricted CI token without logging it; install the GitHub secret.
5. Dispatch the release workflow and verify Charmhub channel plus GitHub artifact.
6. Refresh only Pyroscope in the retained reference model and verify health,
   source/artifact correspondence, telemetry and model preservation.
7. Record exact release commit, action run, artifact checksum, revision and issue URL.

## Actual result

All listed tasks completed. The source, action run, artifact digest, revision,
Iris issue and verified retained-model refresh are recorded in
[the release record](../../releases/2026-10-28-initial-edge.md).
