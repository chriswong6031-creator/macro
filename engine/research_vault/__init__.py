"""Research Vault — ingestion spine (RV W1).

A gated vault + feed of third-party buy-/sell-side research PDFs. PDFs arrive
~hourly from an upstream engine into a PRIVATE R2 inbox, are ingested, indexed
(full-text), and the public-safe metadata is published as a catalog + FTS corpus.

This package is the pure engine half (namespace ``research_vault`` everywhere —
never ``research/``, ``research_factory``, or ``reports``):

  - :mod:`sidecar`  — parse/normalize the ``research_vault.sidecar.v1`` contract (§5).
  - :mod:`r2_store` — thin boto3 wrapper for the private research bucket + a local
                      filesystem backend for tests/dry-runs (§4).
  - :mod:`corpus`   — standalone FTS5 ``corpus.sqlite`` search index (§8; CXI-R23:
                      code-copy only, never touches the CXI databases).
  - :mod:`catalog`  — the public-safe ``catalog.json`` list metadata (§6).
  - :mod:`ingest`   — the hourly, idempotent, never-raise-per-item pipeline (§7).

Display-tier content surface: ships NO signals, scores, or escalations — the
gauntlet/epistemics promotion law does not apply. See
``research/RESEARCH_VAULT_MASTERPLAN.md``.
"""
