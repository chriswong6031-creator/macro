# F04-X1 ontology-explorer fixtures — SYNTHETIC ONLY

Nothing in this directory is a current owner reading. Every series name, value,
threshold and date is invented, and the chain slug is `synthetic_*` so it can
never collide with a real `knowledge/transmission/*.yaml` chain.

The reason is the operation's privacy law: current tenant-neutral snapshot
values are served only through the authenticated API, and must never appear in
the public repository, in a pull request, or in CI logs. Test fixtures are the
easiest place for a real value to leak in by accident, so this directory is
held to "invented values only" and the builders live in
`tests/ontology_explorer_fixtures.py`.
