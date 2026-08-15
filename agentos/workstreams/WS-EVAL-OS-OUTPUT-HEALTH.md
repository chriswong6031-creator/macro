---
key: EVAL-OS-OUTPUT-HEALTH
title: Intelligence Evaluation OS — T4 output-level health contract (derived per-output substrate + admin surface)
objective: >
  One honest health verdict per engine output artifact — healthy / degraded / stale /
  unavailable — or the explicit admission that Eval OS could not determine it
  (assessment_status=could_not_look), derived on demand over the T1 engine registry and the
  Synapse artifact estate, with reader-side evidence outranking producer-side freshness,
  dependency-bound honesty (exact vs upper), lawful time-basis handling (no calendar
  guessing), and zero committed generated state. Exposed read-only through the existing
  admin console as the Intelligence OS surface (CEO amendment 2026-08-14). Consumed later
  by T7; T4 grants no live authority and changes nothing any engine predicts.
status: active
program: qualitative-intelligence
repos:
  - macro
owner: Eval-OS T4 session (COO Fable lane)
class: build
blast_radius: reversible
ambiguity: specified
depends_on:
  - "WS:EVAL-OS-T1-ENGINE-REGISTRY"
owns_paths:
  - engine/output_health.py
  - scripts/build_output_health.py
  - tests/test_output_health.py
  - admin/intelligence_os.py
  - tests/test_admin_intelligence_os.py
decisions:
  - "DEC:EVAL-OS-T4-ADMIN-SURFACE"
waves:
  - id: W1
    title: Pure resolver + CLI adapter + acceptance/mutation suite + admin Intelligence OS page
    status: in_progress
    next_action: "Adversarial review (opus) over the full diff; then PR, CI, merge, live verification."
do_not_redo:
  - "Do not build another monitor/registry/graph/dead-man switch — Neural Web health (engine/neuralweb/health.py), Foresight health (engine/foresight_health.py), provider health (engine/provider_health.py), the external freshness sentinel (scripts/freshness_sentinel.py), and the R2 audit (scripts/audit_r2.py) are EVIDENCE PROVIDERS; T4 only normalizes their evidence."
  - "Do not commit a generated health artifact or add a --check/equality mode — the T1 lesson (two scheduled fleet-wide reds) applies verbatim; the resolver is a derived on-demand view."
  - "Do not generalize Neural Web's weekend staleness shortcut or its _AS_OF_KEYS fallback list estate-wide — the estate spans US/China/HK/crypto/filings/event-pinned artifacts; a date-only watermark beyond its conservative SLA reading resolves could_not_look (date_only_calendar_unknown), never a guessed calendar verdict."
  - "Do not let the sentinel import or depend on T4 — dependency direction is sentinel → evidence, T4 reads evidence."
  - "Do not hand-author complete input lists — upstream sets derive mechanically from config/synapse.yml consumers; health_optional_upstreams expresses only the validated optional delta and had ZERO live entries at ship time."
  - "Do not treat support_map.upstream()'s bound='exact' note as true for multi-output producers — 136/365 producers are multi-output covering 412/642 artifacts; T4 computes its own dependency_bound."
landmines:
  - "asof_field is free-form (82 distinct names live; the _VALID_ASOF_FIELDS set in synapse.py is dead code); staleness_from (6 artifacts) overrides which field freshness is measured from and must be honored."
  - "30 artifacts promise an asof_field their content does not carry (e.g. site-foresight-cascade declares as_of, file has asof) — T4 surfaces these as promised_asof_field_absent; healing the declarations is registry curation, a separate wave."
  - "mtime is lawful evidence only under a write-time contract (asof_field null + SLA non-null) AND only when trusted (live estate; ADMIN_DEPLOYED=1 or --trust-mtime) — a fresh-checkout mtime is checkout time and reads false-fresh."
next_action: "W1 in flight: core + admin built on claude/eval-os-t4-output-health; adversarial review, Agent OS handoff, PR → merge → live verify."
---

## State (2026-08-14)

T1 (378 engines, derived view) is the unit-of-account substrate; W3 closed output_class at
107/109 with 2 deliberate nulls. T4 adds the per-output health layer: unit of account
`(engine_id, artifact_id)`, schema `mastermind.output_health.v1`, four states + separate
assessment_status, precedence pinned by mutation tests, reader-plane evidence sovereign over
producer-plane, dependency bounds honest, nothing committed. CEO amendment 2026-08-14 folds a
read-only admin console surface (Intelligence OS page, cross-linked with the Neural Web
Observatory, fixture-reflective, no persisted admin state) into the same wave. Pre-build
census and per-wave receipts live in the PR body and the session handoff.
