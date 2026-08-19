---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: claude/cs-v2-w1-evidence-identity
model: sonnet
ended_because: complete
mission: >
  Implement Capital Structure V2 Wave 1 remaining production wiring and
  mandatory hostile tests: wire collector, event compiler, ingestion health,
  and tests so repeated or concurrent observation of the same SEC
  occurrence+bytes cannot create two economic evidence identities or duplicate
  Capital Structure events, and a stale overlapping CS generation cannot
  overwrite a newer coherent generation.
state_before: >
  Core evidence_id functions (source_identity.py), schemas, CS append-only
  family (config/append_only_artifacts.json), and daily.yml CS push-loop fence
  call already existed. Collector, event compiler, ingestion health, and hostile
  tests were not yet wired with W1 identity semantics. W0 was accepted by
  Sol/Chairman.
changed:
  - path: collectors/sec_capital_structure.py
    what: >
      Stamp new complete-submission and child manifests with evidence_id,
      evidence_key_format=1, evidence_occurrence, first_known_at BEFORE calling
      manifest_id_for. parse_submission binds byte_start/byte_end from
      document_inner_spans(raw). Re-observation detection (same evidence_id +
      same content_sha256 → no new manifest revision). Attempt columns
      observed_evidence_ids and retained_available_at added. _read_table
      tolerates old parquets missing the new columns. re_observed counter
      propagated into health.
  - path: engine/capital_structure/ingestion_health.py
    what: >
      decide_verdict third progress term: re_observed>0 counts as progressed.
      build_ingestion_run accepts re_observed/unique_evidence_count/
      manifest_revision_count/observation_count; counters.re_observed always
      emitted (default 0).
  - path: engine/capital_structure/event_spine.py
    what: >
      build_event_version reads evidence_ids from observation and attaches to
      source_block when present. Uses first_known_at from observation for
      point_in_time.first_seen_at/system_available_at/available_at so a later
      observation cannot move the published PIT boundary backward.
  - path: scripts/compile_capital_structure_events.py
    what: >
      _semantic_event_body pops source.manifest_ids and evidence[].manifest_id
      so clock-contaminated fields do not drive economic identity comparison.
      _project_evidence_ids_into_event projects evidence_ids into historical
      events for first-W1-compile comparison. compile_manifest_records collects
      evidence_ids from manifest rows via evidence_id_from_manifest and passes
      canonical first_known_at through observation dict.
  - path: tests/test_capital_structure_evidence_identity.py
    what: >
      NEW — 25 hostile tests covering all required scenarios: clock isolation,
      identity separation, re-observation idempotency, correction generation,
      PIT semantics, fence withhold, #5792 fail-closed regression.
  - path: tests/fixtures/capital_structure/evidence_identity/two_document_submission.txt
    what: >
      NEW — SGML fixture with SEC-DOCUMENT envelope and two DOCUMENT blocks for
      document_inner_spans test coverage.
  - path: tests/test_append_only_base_fence.py
    what: >
      Added test_registry_loads_and_declares_capital_structure_family and
      test_cs_stale_generation_withholds_whole_family_not_one_file.
  - path: tests/test_daily_capital_structure_job.py
    what: >
      Added test_cs_push_loop_calls_append_only_fence and
      test_cs_push_fence_is_after_fetch_before_rebase.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: W0 wave → done; W1 wave → in_progress with branch + next_action.
  - path: agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-19.md
    what: this handoff
verified:
  - claim: all required tests pass
    command: >
      python3.12 -m pytest tests/test_capital_structure_evidence_identity.py
      tests/test_capital_structure_source_identity.py
      tests/test_capital_structure_ingestion_health.py
      tests/test_append_only_base_fence.py
      tests/test_daily_capital_structure_job.py
      tests/test_capital_structure_event_spine.py
      tests/test_capital_structure_compiler.py
      tests/test_sec_capital_structure.py
      tests/test_capital_structure_contracts.py -q
    result: 212 passed, 3 warnings in 124.27s (0 failures)
  - claim: evidence_id_for rejects unexpected kwargs
    command: "python3.12 -c \"from engine.capital_structure.source_identity import evidence_id_for, EvidenceIdentityError; import pytest; pytest.raises((TypeError, EvidenceIdentityError))\""
    result: confirmed by test_evidence_id_for_rejects_unexpected_kwargs passing
  - claim: manifest_id_for is byte-identical for historical-shaped records
    command: engine/capital_structure/source_identity.py not edited; manifest_id_for unchanged
    result: confirmed by tests/test_capital_structure_source_identity.py 25 passed
  - claim: no W2 code introduced
    command: git diff --stat HEAD origin/main -- collectors/ engine/ scripts/ | grep -E "LIVE_TAIL|RECOVERY|BACKFILL"
    result: no matches
unverified:
  - claim: production nightly will not regress on real SEC data
    what_would_verify: first nightly run after W1 merge; re_observed counter in health output
  - claim: parse_submission byte binding is correct on all live SEC submission variants
    what_would_verify: nightly collector error rate monitoring after deploy
unresolved:
  - "W1 PR not yet merged. CI must conclude green before squash-merge."
  - "Production proof pending: first nightly run with W1 code is the live verification."
next_actions:
  - "Open PR from branch claude/cs-v2-w1-evidence-identity; add merge-on-green label."
  - "Wait for CI to conclude (not pending) — all packs must be green or spurious-only."
  - "After squash-merge: verify nightly runs cleanly and health output includes re_observed=0 (no re-observations on first clean night) or re_observed>0 (concurrent race detected and handled)."
  - "Do not start W2 before merge is verified live."
do_not_redo:
  - "Do not rewrite historical evidence_occurrences or manifest_ids: legacy children project as legacy:{source_id} and that string must remain unchanged."
  - "Do not make evidence_id / first_known_at / evidence_occurrence required in schemas — that invalidates the full v1 historical ledger."
  - "Do not start W2 (LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL) before W1 is squash-merged and the first nightly has run."
  - "Do not change manifest_id_for — it hashes the full body minus manifest_id and that spec is frozen."
danger_areas:
  - "_project_evidence_ids_into_event is O(n manifests) per prior event on first W1 compile. For large ledgers this could be slow at compile time. Acceptable for batch; cache if W2 requires real-time compile."
  - "parse_submission now calls document_inner_spans(raw) on every complete submission fetch. Malformed SEC content causes fail-closed. Monitor collector error rates after deploy."
  - "Re-observation detection is O(n ledger rows) per fetch. Acceptable at current scale; profile before W2 backfill lane."
---

# W1 Evidence Identity — session handoff 2026-08-19

Cold-stranger summary: Wave 1 production wiring is complete and all 212 required
tests pass. The branch is `claude/cs-v2-w1-evidence-identity` and needs a PR opened,
CI, and squash-merge before W2 may start.

## What changed and why

The core problem W1 solves: `manifest_id_for` hashes retrieval clocks
(`retrieved_at`, `first_seen_at`), so two observations of the same SEC filing at
different wall times produce different manifest IDs. Without W1, the event compiler
treated these as different economic events and would generate spurious correction
events for every re-observation.

**Collector**: now stamps each new manifest with `evidence_id` (stable
occurrence+bytes hash), `evidence_key_format=1`, `evidence_occurrence`, and
`first_known_at` BEFORE computing `manifest_id_for`. Re-observation detection
checks whether any existing ledger row projects to the same `evidence_id` and
`content_sha256`; if so, it records the attempt but does NOT append a new manifest
revision. The `re_observed` counter flows into ingestion health as a third progress
term.

**Ingestion health**: `decide_verdict` now accepts `re_observed>0` as progress so
a clean idempotent night (all already-retained, all re-observed) does not false-fail
the #5792 guard.

**Event spine**: `build_event_version` reads `evidence_ids` from the observation
dict and attaches them to `source` when present. It also reads `first_known_at`
from the observation so PIT timestamps are frozen to the canonical first-known time,
not the latest retrieval clock.

**Compiler**: `_semantic_event_body` now pops `source.manifest_ids` and
`evidence[].manifest_id` before comparing events for correction detection. This
means two compilations of the same accession with different manifest IDs (different
clocks, same bytes) produce the same semantic body and no spurious correction is
generated. `_project_evidence_ids_into_event` back-fills evidence_ids into
historical events that predate W1, so the first W1 nightly compile does not mint
a correction for every historical accession.
