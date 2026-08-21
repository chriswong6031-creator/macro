# IMCE D1(c) Release Record — CPI-H1 Consumer-Authority Heal

**Status:** Heal applied. D1(c) is RELEASED **upon this PR's merge and verification** — not upon this record's landing alone (same discipline the A2 audit itself was held to; see "Release timing" below).
**Wave:** CPI-H1 (CPI truth-consumer authority heal).
**Authority:** Sol's CPI-H1 authorization, accepting the IMCE A-wave closure (`agentos` A1/A2/A3/A4 records) and issuing 13 binding rulings that resolve every open decision left in `research/imce/IMCE_A2_CPI_TRUTH_VOCABULARY_AUDIT_V1.md` §8c.
**Owner:** CPI (`cycle-intelligence`) — this is CPI-owned heal input, same as the A2 audit it completes.

## What this record closes

`research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` D1 condition (c) reads:

> no issuer truth is appended to the CPI registry until the D-4 vocabulary audit (§13 wave A2) lands — the registry's rows carry at least four consumer vocabularies including orphan tokens (§1).

The A2 audit (merged, records-only) enumerated the defect and proposed but did NOT apply a reconciliation, per its own adjudicated release condition:

> freeze D1(c) releases only when the applied heal has landed and been verified in a CPI-owned follow-on wave — not on this audit's landing.

This wave (CPI-H1) is that follow-on: the heal is applied, versioned, and tested here.

## Sol's 13 rulings — applied

| # | Ruling | Applied |
|---|---|---|
| 1 | `config/cycle_pattern/consumer_matrix.yml` becomes the single canonical registry; `truth_schema.md` documents, doesn't compete | `consumer_matrix.yml` `surfaces:` extended to the full 19-token canonical vocabulary + `retired_aliases:` map; `truth_schema.md`'s "Consumer categories" section rewritten to point at the matrix and state the enforced rules |
| 2 | Canonicalizations: `measurement_surface`→`measurement_page`, `honesty_display`→`cycle_docs`, `research_factory_intake`→`research_factory`, `display_descriptive`→`cycle_docs` | Applied via versioned heal rows (17 FAM-A rows: CPI-001–015, CPI-017, falsosc null) + writer literals healed in `scripts/seed_cycle_truths.py`, `scripts/run_falsosc_trial_v1.py` |
| 3 | CPI-016's private `display`/`display_only` vocabulary retired; heal to the ordinary `promoted_null` surface contract | CPI-016 v2: `allowed_consumers=[measurement_page, cycle_docs, research_factory]`, `forbidden_consumers=` the 4 universal tokens — matches CPI-001's healed shape exactly |
| 4 | `forward_allocation`, `signal_generation`, `hazard_score_design`, `hazard_baseline_override` are NOT established pipeline surfaces — retired outright, not minted into the matrix | All four listed in `consumer_matrix.yml`'s `retired_aliases:` mapped to `null` (no replacement); `engine/cycle_pattern/consumer_authority.py` rejects each by name; `scripts/build_phase_clock_eval.py` no longer emits `hazard_baseline_override`; `scripts/run_falsosc_trial_v1.py` no longer emits `hazard_score_design` |
| 5 | Every truth row carries the four universal money-path forbids; CPI-011's missing fourth token is a seeding omission — healed | CPI-011 v2 forbidden_consumers gains `sector_central_direction_score`; `engine/cycle_pattern/consumer_authority.py`'s `UNIVERSAL_MONEY_PATH_FORBIDS` hard-enforces this on every row going forward; `truth_schema.md` documents the money-path-four reading of A2 F7 explicitly |
| 6 | The five `promoted_null` F6 rows remove `neuralweb_context` from `allowed_consumers`; matrix wins | All five (`ft1`/`ft4`/`ft2` hazard nulls, `cn_downturn_broken_trend_tail_null_v1`, `ix1_index_transfer_null_v1`) healed via versioned append; writer scripts `apply_cycle_pattern_ix1_outcomes.py` and `apply_cycle_pattern_lattice_batch2_outcomes.py` healed so future re-runs don't reintroduce the grant |
| 7 | Explicit `retired`/`superseded` class behavior added to the matrix | Two new `artifact_classes` entries added (least-privilege: `cycle_docs`/`research_factory` allowed, universal 4 + `neuralweb_context` forbidden) |
| 8 | Row allowlists stay least-privilege subsets of their class; never mechanically widen | CPI-015's heal is a pure token substitution (`research_factory_intake`→`research_factory`) — `measurement_page` was NOT added back even though CPI-015's class (`display`) would permit it; CPI-016 got exactly the ordinary `promoted_null` contract, no more |
| 9 | Registry discipline: append-only, never rewrite/delete historical rows | 23 new versioned rows appended via `transition_truth()` (registry's own versioning convention); `git diff data/cycle_pattern/truths.jsonl` shows 23 insertions, 0 deletions — see EVIDENCE in the commissioning PR |
| 10 | Eliminate future writer emissions of retired aliases | `scripts/seed_cycle_truths.py`, `scripts/build_phase_clock_eval.py`, `scripts/run_falsosc_trial_v1.py`, `scripts/apply_cycle_pattern_ix1_outcomes.py`, `scripts/apply_cycle_pattern_lattice_batch2_outcomes.py` all healed; `scripts/apply_cycle_pattern_tr1_outcomes.py` audited — no retired-alias literal found, no change needed |
| 11 | One canonical consumer-authority validator, reused by `validate_truth` AND CI | `engine/cycle_pattern/consumer_authority.py` — single module; `engine/cycle_pattern/truths.py::validate_truth()` calls it (new `check_consumer_vocabulary` kwarg, default `True`); `scripts/check_cycle_pattern_authority.py` calls the same module via a new `scan_registry_vocabulary()` function |
| 12 | Preserve the literal-path scan; extend, never replace; strike the matrix's false "re-reads truths.jsonl at scan time" claim | `check_cycle_pattern_authority.py`'s `scan()` function is untouched; `scan_registry_vocabulary()` is additive, wired into `main()` alongside it; `consumer_matrix.yml`'s `scored` class `notes:` corrected with the accurate mechanism description; human_review-only-expansion doctrine preserved verbatim |
| 13 | Record D1(c) released on this PR's merge + verification | This document |

## What was NOT done (explicitly out of scope)

- No IMCE issuer truth is appended in this wave. This release **enables** — but does not perform — a future issuer-truth append; that remains a separately-scoped, separately-reviewed act.
- No `data/trial_ledger.jsonl` writes, no outcome access, no Radar/Prophet/screener/scoring/sizing path, no UI.
- The matrix's per-status `artifact_classes` `allowed_consumers` lists were NOT widened to include every canonical narrow-display token (e.g. `hazard_cone_display`) that some existing rows already use — only `surfaces:` (the token vocabulary) was extended, and the two new `retired`/`superseded` classes were added. A2 §8b item 3's broader proposal to extend every class's per-status allowlist so the matrix's "consistent with the seed truths" docstring claim becomes fully true for EVERY row was not adopted; it is not among Sol's 13 rulings and risked scope creep beyond the commissioned heal.
- Two rows carrying `neuralweb_context` under a matrix-forbidden status were left unhealed because Sol's ruling 6 named exactly five `promoted_null` rows, not these: `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1` v1 (`status=candidate`; the matrix's `candidates` class also forbids `neuralweb_context`) and v2 (`status=retired`; the new `retired` class also forbids it). Both are historical, already-superseded/retired lines with no live writer traceable in the current tree (A2 §5 F2 provenance gap). Flagged for a future named ruling if this is judged worth a dedicated heal wave — not taken unilaterally here.

## Verification

See the commissioning PR body / EVIDENCE for the full command output. Summary:

- `data/cycle_pattern/truths.jsonl`: 29 → 52 lines, 23 append-only heal rows, 0 historical lines changed or removed (`git diff` proof).
- `engine/cycle_pattern/consumer_authority.py::validate_registry()` run over all 27 latest-version truth_id rows: 0 errors.
- `scripts/check_cycle_pattern_authority.py` (extended): exit 0 against the current tree — 0 HARD findings (literal-path scan, unchanged behavior) and 0 registry-vocabulary errors (new).
- `tests/test_cpi_h1_consumer_authority.py`: 28 tests, including the 5 Sol-mandated discriminating tests (orphan token fails, promoted_null+neuralweb_context fails, missing universal forbid fails, `hazard_baseline_override` fails, full healed registry passes).
- `tests/test_cycle_pattern_truths.py`, `tests/test_check_cycle_pattern_authority.py`: unchanged pass count plus the updated `test_seeded_truths_all_valid` (now version-aware for consumer-vocabulary checking).

## Release timing

Per the same discipline the A2 audit's own release condition was held to: **this record documents that the heal is APPLIED and locally verified; D1(c) is RELEASED when this PR is merged into `origin/main` and that merge is verified live** (house completion law — commit → push → PR → CI → merge → live verification is one unbroken chain owned by one session). This document does not itself flip the freeze condition before that merge lands.
