# Market Truth Registry — Artifact Schema

File: `data/cycle_pattern/truths.jsonl`  
Schema version: `v0` (2026-07-06)  
Owner: `cycle-intelligence` (`engine/cycle_pattern/truths.py`)

## Design principles

- **Append-only versioning.** A transition writes a NEW line (`version+1`); old lines are never mutated. Memory is permanent; authority is revocable.
- **Evidence-gated.** All `evidence_refs` must point to files that exist on disk at validation time.
- **Falsifier-required.** Every truth must carry at least one concrete falsifier; unfalsifiable claims are not accepted.
- **Status is the authority gate.** `promoted_null` and `retired` truths are excluded from `active_truths()`; `scored` requires a gate artifact in `evidence_refs`.

## Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `truth_id` | str | yes | Stable identifier (e.g. `CPI-001`). Never reused. |
| `version` | int ≥ 1 | yes | Increments on every transition. |
| `status` | enum | yes | `candidate` / `display` / `confirmer` / `scored` / `promoted_null` / `retired` / `superseded` |
| `owner_program` | str | yes | Must be `"cycle-intelligence"`. |
| `statement` | str | yes | One falsifiable sentence. |
| `effect_class` | enum | yes | `positive` / `risk_only` / `null` / `structural` |
| `scope` | dict | yes | Must contain `families` (list), `regions` (list), `sample` (str). |
| `target` | str | yes | The specific outcome or quantity the statement addresses. |
| `evidence_refs` | list[str] | yes | Repo-relative paths to verdict docs or data artifacts. Validated on disk. |
| `n_summary` | str | yes | Free text: sample sizes, n_months, draws. |
| `ci_summary` | str | yes | Free text: key CI values and verdicts. |
| `era_stability` | enum | yes | `stable` / `decayed` / `fragile` / `unknown` |
| `pit_class` | enum | yes | `pit_pure` / `revision_optimistic` / `mixed` |
| `allowed_consumers` | list[str] | yes | Surfaces permitted to cite this truth. |
| `forbidden_consumers` | list[str] | yes | Surfaces explicitly barred. Must be non-empty. |
| `falsifiers` | list[str] | yes | Concrete conditions under which the truth is invalidated. Min 1. |
| `monitoring` | dict | yes | Must have keys `metric`, `cadence`, `auto_demote_rule` (values nullable). |
| `created` | str (YYYY-MM-DD) | yes | ISO date of first version. |
| `last_reviewed` | str (YYYY-MM-DD) | yes | Updated on each transition. |
| `next_review_due` | str (YYYY-MM-DD) | yes | Monitoring trigger date. |
| `notes` | str | yes | Free text; transition history appended here. |

## Status semantics

| Status | Meaning | active_truths? |
|---|---|---|
| `candidate` | Proposed; not yet display-eligible | yes |
| `display` | Approved for measurement surfaces | yes |
| `confirmer` | Used as a confirming gate in a pipeline | yes |
| `scored` | Passed a pre-registered gate (gate artifact required) | yes |
| `promoted_null` | Adjudicated null; actively displayed as honest null | yes |
| `retired` | No longer active; memory preserved | **no** |
| `superseded` | Replaced by a newer truth | **no** |

## `scored` gate rule

`status = "scored"` requires at least one entry in `evidence_refs` that:
- ends in `.json`
- contains `data/` in the path
- has one of `verdict`, `gate`, `model`, `calibration` in the filename

This ensures a machine-readable verdict artifact backs the claim.

## `pit_class` values

| Value | Meaning |
|---|---|
| `pit_pure` | All features computed from tape ≤ t; no revision risk |
| `revision_optimistic` | Some features use revised macro/regime data without ALFRED vintages (P-D5-1) |
| `mixed` | PIT-pure for the primary signal; revision-optimistic for regime features (e.g. hazard model) |

## Consumer categories — canonical authority lives in `consumer_matrix.yml`

**`config/cycle_pattern/consumer_matrix.yml` is the SINGLE canonical registry
of `allowed_consumers`/`forbidden_consumers` vocabulary (CPI-H1, Sol ruling
1).** This section used to carry its own competing "non-exhaustive" token
list, which silently diverged from the matrix for years: 17 of the
registry's 29 rows used this doc's vocabulary while 11 used the matrix's, and
no code path checked either against the other (`research/imce/
IMCE_A2_CPI_TRUTH_VOCABULARY_AUDIT_V1.md` findings F3/F4). This doc now
documents the RULES; it does not maintain a second list.

**The rules, enforced by `engine/cycle_pattern/consumer_authority.py`
(reused by both `validate_truth()` and the CI-wired
`scripts/check_cycle_pattern_authority.py` scan — CPI-H1 ruling 11):**

- Every `allowed_consumers`/`forbidden_consumers` token must be one of the
  names declared in `consumer_matrix.yml`'s `surfaces:` section. Any other
  token is rejected — with a specific "retired alias" message for the tokens
  named in `consumer_matrix.yml`'s `retired_aliases:` map, or a generic
  "orphan token" message otherwise.
- **Universal money-path floor (CPI-H1 ruling 5):** `forbidden_consumers`
  must carry all four of `board_rank`, `oracle_escalation`,
  `sector_central_direction_score`, `position_sizing` on EVERY row,
  regardless of `status` or `effect_class` — this resolves A2 finding F7's
  ambiguity in favor of the "money-path-four" reading. The other three
  schema-doc tokens (`lead_lag_interaction_layer`, `ladder_calibration_input`,
  `high_authority_truth_evidence`) remain row/class-level narrow forbids —
  not part of the universal floor.
- **Row allowlists are least-privilege subsets of their status class** — a
  row is never mechanically widened just because its status class could
  permit a surface (CPI-H1 ruling 8).
- A `promoted_null`-status row may never grant `neuralweb_context` in
  `allowed_consumers` — the matrix's `promoted_null` class forbid wins over
  any row-level grant (CPI-H1 ruling 6 / A2 finding F6).
- `retired` and `superseded` status rows now have explicit
  `artifact_classes` entries in the matrix (CPI-H1 ruling 7 — previously
  undefined, A2 §3 nit).

See `config/cycle_pattern/consumer_matrix.yml` for the full canonical token
list and per-status contracts, and `research/imce/IMCE_D1C_RELEASE_RECORD.md`
for the heal record.

## API (`engine/cycle_pattern/truths.py`)

```python
load_truths(path=None)            # list of all rows (all versions)
validate_truth(dict, *, check_refs_exist=True)  # raises ValueError on violation
append_truth(dict, path=None)     # validate + write one row
transition_truth(truth_id, new_status, actor, reason, path=None, *, extra_fields=None)
active_truths(path=None)          # latest-version rows not retired/superseded
```

## House rules (binding)

- Pure `numpy`/`pandas` in all engine code — no `sklearn`/`statsmodels`/`scipy.stats`.
- Bootstrap: month-block, 800 draws, seed=7 (`engine/grading_stats.py`).
- Wilson-on-raw-n is forbidden (ruling A2).
- PIT discipline: any stamp is a pure function of tape ≤ t.
- Backfill and live cohorts never blend in one badge.
- All new data artifacts are committed JSON/parquet; keep small and deterministic.
