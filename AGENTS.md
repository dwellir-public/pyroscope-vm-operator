# Pyroscope VM development

Use the installed dwellir-charm-development skill. Keep Juju orchestration in
src/charm.py, host operations in src/pyroscope.py, and pure configuration in
src/config_builder.py. Preserve Canonical relation contracts and vendor bytes.

Run uv/tox lint, static and unit checks, then charmcraft pack using the managed
LXD environment. Do not use destructive builds. Integration tests reuse only the
explicit localhost-localhost reference model and must never destroy it or remove
pre-existing apps, relations or storage. Keep docs/validation.md current with actual
evidence and distinguish native ingestion, OTLP forwarding and Iris collection.
