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

## Consumer categories (non-exhaustive)

Allowed: `measurement_surface`, `honesty_display`, `research_factory`, `hazard_cone_display`, `risk_context_strip`, `tripwire_context`, `sync_gauge_display`, `cone_rendering`, `mechanism_summary`, `hypothesis_generation`, `monitoring`

Forbidden (must appear in `forbidden_consumers` for null/structural truths): `board_rank`, `oracle_escalation`, `sector_central_direction_score`, `position_sizing`, `lead_lag_interaction_layer`, `ladder_calibration_input`, `high_authority_truth_evidence`

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
