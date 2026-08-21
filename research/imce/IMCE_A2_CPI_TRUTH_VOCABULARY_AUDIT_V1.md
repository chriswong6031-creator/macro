# IMCE A2 — CPI Truth-Contract Vocabulary Audit (D-4)
## Full token enumeration and disposition of `allowed_consumers`/`forbidden_consumers` across the CPI truth registry — precondition for any issuer truth

**Status:** Records-only audit. No `data/`, `engine/`, `scripts/`, `config/` edits. Applies zero heals — every fix below is a PROPOSAL for Fable adjudication, not an applied change.
**Commissioned by:** freeze `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §13 wave A2, authorized after Sol's release of PR #6127 (merged `ec44ae7d1659`, 2026-08-21T03:55Z).
**Owner:** CPI (`cycle-intelligence`) — this audit is CPI-owned heal input; IMCE composes and cites CPI truths but does not own the registry.
**Precondition binding:** freeze D1 condition (c) — no issuer truth may be appended to `data/cycle_pattern/truths.jsonl` until this audit lands.
**Scope of this document:** enumeration + disposition + reconciliation proposal only. Mechanical application (editing the registry, the schema doc, or the matrix) is explicitly out of scope and named as CPI-owned follow-on work in §6.

---

## 0. Method and sources

| Artifact | Path | How read |
|---|---|---|
| CPI truth registry | `data/cycle_pattern/truths.jsonl` | `git show origin/main:data/cycle_pattern/truths.jsonl` (this worktree is sparse; `data/` is intentionally omitted on disk per `config/sparse_worktree.json` — read via git object store only, never materialized, never written) |
| Consumer matrix | `config/cycle_pattern/consumer_matrix.yml` | `git show origin/main:config/cycle_pattern/consumer_matrix.yml` |
| Truth schema doc | `config/cycle_pattern/truth_schema.md` | `git show origin/main:config/cycle_pattern/truth_schema.md` |
| Authority guard | `scripts/check_cycle_pattern_authority.py` | `git show origin/main:scripts/check_cycle_pattern_authority.py` |
| Schema validator | `engine/cycle_pattern/truths.py` (`validate_truth`) | `git show origin/main:engine/cycle_pattern/truths.py` |
| Registry writers (provenance) | `scripts/seed_cycle_truths.py`, `scripts/run_falsosc_trial_v1.py`, `scripts/run_har1_eval.py`, `scripts/build_phase_clock_eval.py`, `scripts/apply_cycle_pattern_{ix1,lattice_batch2,tr1}_outcomes.py` | `git grep`/`git show` against `origin/main` |

All reads used `origin/main` at `ec44ae7d1659` (the freeze merge commit; `git fetch origin && git log --oneline -1` confirmed this worktree's `HEAD` equals `origin/main` before any work began — no rebase was needed). No file under `data/` was written; the worktree's sparse cone was never widened.

**Row count:** the registry holds **29 rows** (`git show origin/main:data/cycle_pattern/truths.jsonl | wc -l` → 29; parsed with `json.loads` per line, all 29 parse cleanly). This matches the freeze's stated count exactly — **no delta**. Two `truth_id`s carry two versions each within the 29 rows (`cycle_truth_lattice1_confirmatory_and_baseline_confound_v1` v1→v2, status unchanged `display`→`display`; `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1` v1→v2, `candidate`→`retired`) — append-only versioning per `truth_schema.md`, both counted as distinct rows below since each carries its own `allowed_consumers`/`forbidden_consumers` literal (identical between versions in both cases).

---

## 1. Full token enumeration

Extracted programmatically (`json.loads` per line, `set().update()` over `allowed_consumers` and `forbidden_consumers`):

**Distinct `allowed_consumers` tokens observed (18):**
`cone_rendering`, `cycle_docs`, `display`, `display_descriptive`, `display_only`, `hazard_cone_display`, `honesty_display`, `hypothesis_generation`, `measurement_page`, `measurement_surface`, `mechanism_summary`, `monitoring`, `neuralweb_context`, `research_factory`, `research_factory_intake`, `risk_context_strip`, `sync_gauge_display`, `tripwire_context`

**Distinct `forbidden_consumers` tokens observed (11):**
`board_rank`, `forward_allocation`, `hazard_cone_display`, `hazard_score_design`, `high_authority_truth_evidence`, `ladder_calibration_input`, `lead_lag_interaction_layer`, `oracle_escalation`, `position_sizing`, `sector_central_direction_score`, `signal_generation`

(`hazard_cone_display` appears in both lists — allowed on CPI-004/CPI-005, forbidden on CPI-006 — a legitimate per-row usage, not a contradiction within any single row.)

**Union of both fields: 28 distinct tokens** across the 29 rows.

---

## 2. The two named authorities

The freeze instructs disposition against `consumer_matrix.yml`'s `surfaces:` section. Reading it and `truth_schema.md` together shows the registry actually answers to **two separate, disagreeing documents**, so both are quoted in full before any row is dispositioned.

### 2a. `config/cycle_pattern/consumer_matrix.yml` — `surfaces:` section (verbatim)

```yaml
surfaces:
  money_path:
    - board_rank
    - oracle_escalation
    - sector_central_direction_score
    - position_sizing
  display:
    - measurement_page
    - cycle_docs
    - neuralweb_context
  research:
    - research_factory
```

Eight tokens total. The matrix's own docstring: *"Surface names are consistent with the seed truths in `data/cycle_pattern/truths.jsonl` and the forbidden_consumers list in `config/cycle_pattern/truth_schema.md`."* — this claim is checked in §3 and does not hold for most of the registry.

Separately, every `artifact_classes` entry in the same file (`promoted_null`, `display`, `confirmer`, `scored`, `candidates`, `lake_artifacts`) states its own `allowed_consumers`/`forbidden_consumers`, and **every single one of them is drawn exclusively from the `surfaces:` vocabulary** (`measurement_page`, `cycle_docs`, `research_factory`, `neuralweb_context`, plus the four money-path names) — the matrix never once uses `measurement_surface`, `honesty_display`, or any of the other schema-doc tokens in §2b below, anywhere in the file.

### 2b. `config/cycle_pattern/truth_schema.md` — "Consumer categories (non-exhaustive)" (verbatim)

> Allowed: `measurement_surface`, `honesty_display`, `research_factory`, `hazard_cone_display`, `risk_context_strip`, `tripwire_context`, `sync_gauge_display`, `cone_rendering`, `mechanism_summary`, `hypothesis_generation`, `monitoring`
>
> Forbidden (must appear in `forbidden_consumers` for null/structural truths): `board_rank`, `oracle_escalation`, `sector_central_direction_score`, `position_sizing`, `lead_lag_interaction_layer`, `ladder_calibration_input`, `high_authority_truth_evidence`

Eleven allowed + seven forbidden = 18 tokens, explicitly flagged "non-exhaustive."

### 2c. Where the two authorities agree — verified

The freeze claims agreement on `research_factory` and the four money-path forbidden names. Checked directly:

- `research_factory` — present in the matrix's `research:` group AND in the schema doc's allowed list. **Confirmed shared.**
- `board_rank`, `oracle_escalation`, `sector_central_direction_score`, `position_sizing` — present verbatim, same four, in the matrix's `money_path:` group AND in the schema doc's forbidden list. **Confirmed shared, byte-identical.**

That is the full overlap: **5 of the 21 tokens named across both authorities are shared.** Every other named token belongs to exactly one authority (schema doc: `measurement_surface`, `honesty_display`, `hazard_cone_display`, `risk_context_strip`, `tripwire_context`, `sync_gauge_display`, `cone_rendering`, `mechanism_summary`, `hypothesis_generation`, `monitoring`, `lead_lag_interaction_layer`, `ladder_calibration_input`, `high_authority_truth_evidence` — 13 tokens; matrix: `measurement_page`, `cycle_docs`, `neuralweb_context` — 3 tokens). Union of both authorities: **21 named tokens.**

---

## 3. Per-row disposition table

Disposition legend: **[S]** = canonical per §2b (schema-doc); **[X]** = canonical per §2a (matrix `surfaces:`); **[S+X]** = canonical in both (the 5-token shared core); **[ORPHAN]** = absent from both §2a and §2b.

| # | `truth_id` (version) | status | `allowed_consumers` (dispositioned) | `forbidden_consumers` (dispositioned) | Vocabulary family |
|---|---|---|---|---|---|
| 1 | CPI-001 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | board_rank[S+X], oracle_escalation[S+X], sector_central_direction_score[S+X], position_sizing[S+X] | **FAM-A** (schema-doc root) |
| 2 | CPI-002 (v1) | display | measurement_surface[S], honesty_display[S], risk_context_strip[S], research_factory[S+X] | board_rank, oracle_escalation, sector_central_direction_score, position_sizing (all S+X) | FAM-A |
| 3 | CPI-003 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | + ladder_calibration_input[S] (plus the 4 S+X) | FAM-A |
| 4 | CPI-004 (v1) | display | measurement_surface[S], hazard_cone_display[S], research_factory[S+X], tripwire_context[S] | the 4 S+X | FAM-A |
| 5 | CPI-005 (v1) | display | measurement_surface[S], hazard_cone_display[S], research_factory[S+X], tripwire_context[S] | the 4 S+X | FAM-A |
| 6 | CPI-006 (v1) | promoted_null | measurement_surface[S], research_factory[S+X] | the 4 S+X + hazard_cone_display[S] | FAM-A |
| 7 | CPI-007 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | the 4 S+X + ladder_calibration_input[S] | FAM-A |
| 8 | CPI-008 (v1) | promoted_null | measurement_surface[S], sync_gauge_display[S], research_factory[S+X] | the 4 S+X + lead_lag_interaction_layer[S] | FAM-A |
| 9 | CPI-009 (v1) | candidate | measurement_surface[S], research_factory[S+X] | the 4 S+X | FAM-A |
| 10 | CPI-010 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | the 4 S+X | FAM-A |
| 11 | CPI-011 (v1) | display | measurement_surface[S], cone_rendering[S], honesty_display[S], research_factory[S+X] | board_rank, oracle_escalation, position_sizing (S+X; **note: `sector_central_direction_score` is omitted from this row's forbidden list** — see §5 finding F5) | FAM-A |
| 12 | CPI-012 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | the 4 S+X | FAM-A |
| 13 | CPI-013 (v1) | display | measurement_surface[S], **display_descriptive[ORPHAN]**, research_factory[S+X] | the 4 S+X + high_authority_truth_evidence[S] | FAM-A / orphan-bearing |
| 14 | CPI-014 (v1) | display | measurement_surface[S], honesty_display[S], research_factory[S+X], monitoring[S] | the 4 S+X | FAM-A |
| 15 | CPI-015 (v1) | display | mechanism_summary[S], hypothesis_generation[S], **research_factory_intake[ORPHAN]** | the 4 S+X + high_authority_truth_evidence[S] | FAM-A / orphan-bearing, structurally divergent (drops `measurement_surface`/`research_factory` entirely — see §5 finding F4) |
| 16 | ft1_breadth_hazard_null_v1 (v1) | promoted_null | neuralweb_context[X], cycle_docs[X], research_factory[S+X], measurement_page[X] | the 4 S+X | **FAM-B** (matrix root) |
| 17 | ft4_structure_hazard_null_v1 (v1) | promoted_null | same FAM-B set | the 4 S+X | FAM-B |
| 18 | ft2_credit_hazard_null_v1 (v1) | promoted_null | same FAM-B set | the 4 S+X | FAM-B |
| 19 | lattice1_confirmatory…_v1 (v1) | display | same FAM-B set | the 4 S+X | FAM-B |
| 20 | cn_downturn_broken_trend_tail_candidate_v1 (v1) | candidate | same FAM-B set | the 4 S+X | FAM-B |
| 21 | cn_downturn_broken_trend_tail_candidate_v1 (v2) | retired | same FAM-B set | the 4 S+X | FAM-B |
| 22 | cn_downturn_broken_trend_tail_null_v1 (v1) | promoted_null | same FAM-B set | the 4 S+X | FAM-B |
| 23 | lattice2_within_family_structure_v1 (v1) | display | same FAM-B set | the 4 S+X | FAM-B |
| 24 | lattice1_confirmatory…_v1 (v2) | display | same FAM-B set | the 4 S+X | FAM-B |
| 25 | tr1_next_phase_softmax_skill_v1 (v1) | display | same FAM-B set | the 4 S+X | FAM-B |
| 26 | ix1_index_transfer_null_v1 (v1) | promoted_null | same FAM-B set | the 4 S+X | FAM-B |
| 27 | falsosc_osc_covariate_null_v1 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | the 4 S+X + **hazard_score_design[ORPHAN]** | FAM-A |
| 28 | **CPI-016** (v1) | promoted_null | **display[ORPHAN]**, **display_only[ORPHAN]** | **forward_allocation[ORPHAN]**, **signal_generation[ORPHAN]** | **FAM-C** (wholly independent private vocabulary — 0 canonical tokens on either side) |
| 29 | CPI-017 (v1) | promoted_null | measurement_surface[S], honesty_display[S], research_factory[S+X] | the 4 S+X | FAM-A |

Row 27 is truth_id `cycle_truth_falsosc_osc_covariate_null_v1`; rows 16–26 are the `cycle_truth_*_v1` family listed with abbreviated names for table width (full IDs in §1 of the freeze's own reconciliation ledger and in the raw registry).

**Every one of the 29 rows appears above; every distinct token from §1 is dispositioned above.**

---

## 4. Verifying the freeze's specific claims

| Freeze claim | Verdict | Evidence |
|---|---|---|
| CPI-013 carries orphan `display_descriptive` | **CONFIRMED** | row 13 above; `display_descriptive` is absent from both §2a and §2b |
| CPI-015 carries orphan `research_factory_intake` | **CONFIRMED, and stronger than stated** | row 15; `research_factory_intake` is orphan, AND the row drops `measurement_surface`/`research_factory` entirely rather than merely adding an extra token — it is the single most vocabulary-divergent row in FAM-A |
| CPI-016 carries orphan `display`/`display_only` | **CONFIRMED, and stronger than stated** | row 28; both allowed tokens are orphan, AND both `forbidden_consumers` tokens (`forward_allocation`, `signal_generation`) are ALSO orphan — CPI-016 is the only row in the registry with zero canonical tokens on either side (see §5 F1) |
| "the guard (`scripts/check_cycle_pattern_authority.py:34-38`) is a literal-path scan that cannot catch any of this" | **CONFIRMED** | §5 below, code quoted |
| "CPI-017, the newest CPI-nnn row, carries the schema-doc vocabulary" | **CONFIRMED** | row 29 — `measurement_surface`/`honesty_display`/`research_factory` + the 4 money-path names, exact FAM-A set |
| Schema doc and matrix "agree on `research_factory` and all four money-path forbidden names" | **CONFIRMED** | §2c |
| "at least FOUR coexisting consumer vocabularies" | **CONFIRMED, count corrected upward with receipts** | §5 finding F2 |

---

## 5. Findings beyond the freeze's stated examples

The freeze's D-4 scoping (§13 A2) commissioned a *full* enumeration precisely because its own text only gave three worked examples. Enumerating all 29 rows and 28 tokens surfaces material the freeze did not have in hand:

**F1 — CPI-016 is orphaned on BOTH sides, and its forbidden list contains none of the four money-path names.** Every other row in the registry (28 of 29) carries `board_rank`/`oracle_escalation`/`sector_central_direction_score`/`position_sizing` (or a documented subset — see F5) in `forbidden_consumers`. CPI-016 instead carries `forward_allocation`/`signal_generation` — tokens that appear nowhere else in the registry, nowhere in the matrix, and nowhere in the schema doc. Per `truth_schema.md`'s own house rule ("Forbidden … must appear in `forbidden_consumers` for null/structural truths" naming exactly the four money-path tokens), and CPI-016's `status=promoted_null`/`effect_class=null`, **CPI-016 is non-compliant with the schema doc's own binding rule for null truths** — not merely vocabulary-divergent, but missing the specific tokens the doc says a null-status row must carry. Traced to its writer: `scripts/build_phase_clock_eval.py:690-691` hard-codes `"allowed_consumers": ["display", "hazard_baseline_override" if verdict_status == "scored" else "display_only"]` and `"forbidden_consumers": ["forward_allocation", "signal_generation"]` — a wholly independent, never-reconciled vocabulary invented by this one script. Note also the **latent, not-yet-materialized 8th allowed token `hazard_baseline_override`**: the `if verdict_status == "scored"` branch has never fired (CPI-016 has only ever been `promoted_null`), so this orphan token exists in code today and would enter the registry silently the moment a phase-clock trial scores — before this audit's heal plan (§6) would catch it, since the heal plan below is not code that runs, only research material.

**F2 — vocabulary-family count, corrected: at least four, and the finer partition supports more.** Grouping the 29 rows by their *exact* `allowed_consumers` set yields 11 distinct sets. Collapsing those into naming families by shared root token:

- **FAM-A** (`measurement_surface`/`honesty_display`/`research_factory` root, schema-doc vocabulary): 17 rows (9 distinct exact-token variants) — CPI-001–014, CPI-017, the falsosc row.
- **FAM-B** (`neuralweb_context`/`cycle_docs`/`measurement_page`/`research_factory`, matrix vocabulary): 11 rows, one exact set, no internal variation.
- **FAM-C** (CPI-016's private `display`/`display_only` + `forward_allocation`/`signal_generation`): 1 row, wholly independent of both named authorities on both sides.
- Within FAM-A, CPI-015 is structurally distinct enough (zero overlap with the FAM-A anchor tokens `measurement_surface`/`research_factory`) to be read as a **fourth-or-fifth sub-family** on its own rather than a mere variant; CPI-013 (one added orphan token, anchor tokens retained) is a milder within-family drift by comparison.

However this is split, the observed floor is **≥ 4** (FAM-A, FAM-B, FAM-C, FAM-A/CPI-015), confirming the freeze's "at least four" without needing the finer 9-variant read. The freeze's parenthetical "split by naming family rather than age" is corroborated precisely by provenance: FAM-A (CPI-001 through CPI-015) was seeded in **one single script** (`scripts/seed_cycle_truths.py`, `truth_id` values confirmed at fixed line numbers by `git grep -n '"truth_id"'`), meaning CPI-013's and CPI-015's divergence from their FAM-A siblings is **within-script inconsistency by the same author in the same wave**, not drift across eras. CPI-017 (`scripts/run_har1_eval.py`) and the falsosc row (`scripts/run_falsosc_trial_v1.py`) reused the FAM-A vocabulary correctly, later. FAM-B's three most recent transitions are traceable to `scripts/apply_cycle_pattern_{ix1,lattice_batch2,tr1}_outcomes.py`; the earlier FAM-B rows (FT1/FT4/FT2/lattice-batch-1 v1, both `cn_downturn` versions) could **not** be traced to a live writer script by literal grep across the current tree (`git grep -ln '"neuralweb_context"' -- 'scripts/*'` returns only the three `apply_cycle_pattern_*` scripts) — this worktree's blobless partial clone could not confirm whether the original writer was deleted, renamed, or run as an untracked one-off; **typed as a provenance gap**, not asserted either way.

**F3 — the matrix is itself the minority-vocabulary artifact.** `consumer_matrix.yml`'s docstring claims its surface names are "consistent with the seed truths" — but only 11 of 29 rows (38%) use the matrix's vocabulary (FAM-B); 17 of 29 (59%) use a vocabulary (FAM-A) the matrix's `surfaces:` section and every one of its `artifact_classes` entries never once reference. The document that `scripts/check_cycle_pattern_authority.py`'s own docstring calls the enforced authority is a minority dialect of what the registry actually contains.

**F4 — no code anywhere validates these token values.** This is broader than the guard named in the freeze (§6 below). `engine/cycle_pattern/truths.py`'s `validate_truth()` — the function every `append_truth`/`transition_truth` call runs — checks `allowed_consumers`/`forbidden_consumers` only for **presence as required fields** (membership in `REQUIRED_FIELDS`); it never inspects their list *contents* against `consumer_matrix.yml`, `truth_schema.md`, or any enumerated vocabulary. Confirmed by reading the full function body (`git show origin/main:engine/cycle_pattern/truths.py`, docstring: "Enum fields within allowed values" — `status`/`effect_class`/`era_stability`/`pit_class` are checked against `VALID_*` sets; `allowed_consumers`/`forbidden_consumers` are conspicuously absent from that enum-checking block). And no consumer of the truth registry (`scripts/build_measurement.py`, `scripts/build_cycle_pattern_state.py`) reads these two fields programmatically at all — `build_cycle_pattern_state.py`'s only reference to the matrix is a docstring comment (`consumer_matrix.yml, lake_artifacts class` — prose, not a function call). **The `allowed_consumers`/`forbidden_consumers` fields are pure governance documentation, consumed by no code path in the repository** — which is *why* seven tokens absent from both named authorities could accumulate across three separate authoring scripts undetected: nothing anywhere checks them, not the schema validator, not the CI guard, not any downstream reader.

**F5 — CPI-011 silently drops one money-path token.** `forbidden_consumers` for CPI-011 is `["board_rank", "oracle_escalation", "position_sizing"]` — three of the four canonical money-path names, missing `sector_central_direction_score`. Every other row in the registry that carries the money-path block carries all four. This could be a deliberate scope narrowing (CPI-011 is the cone-recalibration truth; sector_central plausibly not applicable) or a seeding omission; this audit does not adjudicate which — it is flagged as a finding for the heal plan, not resolved here.

---

## 6. Guard coverage statement

`scripts/check_cycle_pattern_authority.py`, docstring lines 32–38 (freeze cites 34–38; both quoted for the full paragraph):

> ```
> Pattern
> -------
> Modelled on scripts/check_research_factory_authority.py.  This is a LITERAL-
> PATH scan: it looks for the string ``data/cycle_pattern/`` in .py source files
> under engine/, scripts/, collectors/, and tests/.  Dynamic path construction
> without a matching literal is not detected (AST tracing is deferred to a
> future hardening wave).
> ```

Reading the full `scan()` function confirms the docstring precisely:

- It walks `.py` files under `engine/`, `scripts/`, `collectors/`, `tests/` (`_scan_dirs`), and for each file checks `if _PATTERN not in source_text: continue`, where `_PATTERN = "data/cycle_pattern/"` — a bare substring test, no AST, no import graph.
- For every file containing that literal, it classifies the **file's own module path** — not the file's *content* — against two hardcoded lists: `_MONEY_PATH_MODULES` (an 8-entry frozenset of specific `.py` paths, e.g. `engine/sector_central.py`) always yields a `HARD` finding regardless of anything else; `_ALLOWED_READER_PREFIXES` (a 9-entry tuple of path prefixes, e.g. `engine/cycle_pattern/`) yields silence; anything else yields a `WARN`.
- **It never opens `data/cycle_pattern/truths.jsonl` itself.** The one place that literal filename string appears in the script is inside a synthetic in-memory selftest fixture (`_run_selftest`, a fabricated source string used to prove the WARN path fires) — not a real file read.
- **It never loads `config/cycle_pattern/consumer_matrix.yml`.** No `yaml.safe_load` or file-open call on that path exists anywhere in the script; the matrix is referenced only in prose (module docstring, `_MONEY_PATH_MODULES` comment "Mirrors the forbidden_consumers in consumer_matrix.yml").
- **It has no concept of `allowed_consumers`/`forbidden_consumers` at all.** The string `allowed_consumers` appears exactly once in the file, inside a `WARN` finding's human-readable `reason` text pointing an operator at the matrix file for manual review — never parsed, never compared.

**What it does check:** which *Python modules* are permitted to contain the literal path string `data/cycle_pattern/` in their source, with an absolute HARD-fail carve-out for eight named money-path modules.

**What it structurally cannot check, by design, regardless of future maintenance:** anything about the *content* of `truths.jsonl` rows — vocabulary consistency between `allowed_consumers`/`forbidden_consumers` and any named authority, orphan tokens, cross-row drift, or the two-vocabulary split documented in §3–§5. This is not a bug the guard happens to have; it is outside the class of thing a literal-path-by-reader-module scan can express. §5 finding F4 additionally shows the schema-level `validate_truth()` function — the only other gate a registry write passes through — is equally blind to these fields' contents, so **no code path in the repository validates truth-registry consumer-token vocabulary today.**

---

## 7. `truth_schema.md` reconciliation — proposed diff (NOT applied)

The schema doc's "Consumer categories (non-exhaustive)" section (§2b) is stale in three ways: (1) it omits the matrix's three `display:` surface names (`measurement_page`, `cycle_docs`, `neuralweb_context`) entirely, even though 11 of 29 registry rows use them; (2) it does not disclose that it is one of two disagreeing vocabularies rather than *the* vocabulary; (3) the seven orphan tokens found in §1/§5 (`display`, `display_descriptive`, `display_only`, `research_factory_intake`, `forward_allocation`, `hazard_score_design`, `signal_generation`) are not in it and never will be reconciled by reading it alone.

**Proposed reconciled canonical list (embedded here for Fable's review; not written to `truth_schema.md` in this wave):**

```markdown
## Consumer categories (canonical, reconciled A2)

Allowed — display/measurement/research tier:
  measurement_surface, measurement_page, honesty_display, cycle_docs,
  neuralweb_context, research_factory, hazard_cone_display,
  risk_context_strip, tripwire_context, sync_gauge_display, cone_rendering,
  mechanism_summary, hypothesis_generation, monitoring

Forbidden — money-path tier (must appear in full on every null/structural
truth's forbidden_consumers; no row may narrow this set — see F5):
  board_rank, oracle_escalation, sector_central_direction_score,
  position_sizing

Forbidden — narrow/contextual (row-specific, not universally required):
  lead_lag_interaction_layer, ladder_calibration_input,
  high_authority_truth_evidence

RETIRED / DO NOT USE (orphans found by A2 audit, 2026-08-2x; every
occurrence must be remapped per §8 heal mapping before this line is
removed): display, display_descriptive, display_only,
research_factory_intake, forward_allocation, hazard_score_design,
signal_generation, hazard_baseline_override (latent — see F1)
```

This is a proposal only. Whether `measurement_surface` or `measurement_page` becomes the single surviving canonical token (they are almost certainly meant to be the same referent — "the measurement surface/page that renders `measurement.html`" — named twice by two authoring lineages that never spoke to each other) is exactly the kind of call this wave is scoped to surface, not make; §8 leaves it open with both options costed.

---

## 8. Heal plan (proposal; mechanical application is CPI-owned follow-on work)

### 8a. Old token → canonical mapping (covers all 28 enumerated tokens)

| Old token | Canonical target | Basis |
|---|---|---|
| `measurement_surface` | keep, OR merge into `measurement_page` | FAM-A anchor; schema-doc canonical; used by 17/29 rows — majority |
| `measurement_page` | keep, OR merge into `measurement_surface` | FAM-B anchor; matrix canonical; used by 11/29 rows — the file that's supposed to be authoritative |
| `honesty_display` | keep, OR merge into `cycle_docs` | schema-doc canonical; FAM-A's display-doc token |
| `cycle_docs` | keep, OR merge into `honesty_display` | matrix canonical; FAM-B's display-doc token |
| `neuralweb_context` | keep as-is | matrix canonical; carries row-specific caveat (F-status-conditional forbid on `promoted_null`/`candidates` classes) — do not fold into anything, preserve the caveat |
| `research_factory` | keep as-is | shared canonical (both authorities) |
| `hazard_cone_display` | keep as-is | schema-doc canonical |
| `risk_context_strip` | keep as-is | schema-doc canonical |
| `tripwire_context` | keep as-is | schema-doc canonical |
| `sync_gauge_display` | keep as-is | schema-doc canonical |
| `cone_rendering` | keep as-is | schema-doc canonical |
| `mechanism_summary` | keep as-is | schema-doc canonical |
| `hypothesis_generation` | keep as-is | schema-doc canonical |
| `monitoring` | keep as-is | schema-doc canonical |
| `board_rank` / `oracle_escalation` / `sector_central_direction_score` / `position_sizing` | keep as-is | shared canonical, money-path; CPI-011 must be corrected to carry all four (F5) |
| `lead_lag_interaction_layer` / `ladder_calibration_input` / `high_authority_truth_evidence` | keep as-is | schema-doc canonical, narrow forbidden |
| `display_descriptive` (CPI-013) | → `honesty_display` (or its merge target) | closest semantic match in FAM-A; CPI-013 already carries `measurement_surface`/`research_factory` so this is a pure token substitution, one row |
| `research_factory_intake` (CPI-015) | → `research_factory` | CPI-015 also needs `measurement_surface` (or merge target) added back — see F2, it dropped the anchor token entirely, not just this one substitution |
| `display` (CPI-016) | → `honesty_display` (or merge target) + add `research_factory` | CPI-016 is missing the research-factory-lifecycle consumer entirely under either authority |
| `display_only` (CPI-016) | → drop (redundant with `display` after remap) or → `measurement_surface`/`measurement_page` if a narrower display-only semantic is intended — **needs an actual decision, not a mechanical rename**, since "display" and "display_only" plausibly encoded a real distinction (full vs restricted display) that neither authority's vocabulary currently expresses |
| `hazard_baseline_override` (latent, `build_phase_clock_eval.py:690`) | → define explicitly before the `scored` branch ever fires, or retire the branch | not yet in any live row; F1 |
| `forward_allocation` (CPI-016) | → `position_sizing` (closest money-path analog) or add as a genuinely new named money-path surface if `forward_allocation` is a real, distinct pipeline surface | needs CPI to confirm whether `forward_allocation` names a real surface (F1) — if real, it belongs in the matrix's `money_path:` list, not invented ad hoc in one script |
| `signal_generation` | → `board_rank`/`oracle_escalation` (closest money-path analog) or add as new named money-path surface | same open question as `forward_allocation` |
| `hazard_score_design` (falsosc row) | → `hazard_cone_display`'s forbidden counterpart, or confirm as a real distinct surface needing its own matrix entry | one row only; low blast radius |

**Coverage check: all 28 tokens enumerated in §1 appear in the table above — 100% covered**, either as "keep" (14 canonical or shared canonical tokens) or as a remap/decision row (14 orphan or narrowing tokens: `display_descriptive`, `research_factory_intake`, `display`, `display_only`, `hazard_baseline_override`, `forward_allocation`, `signal_generation`, `hazard_score_design` = 8 orphans, plus the `measurement_surface`/`measurement_page` and `honesty_display`/`cycle_docs` merge-or-keep pairs = 4 more, plus CPI-011's F5 narrowing and the money-path four already counted under "keep").

### 8b. Where each heal must be applied

1. **`data/cycle_pattern/truths.jsonl` rows** — CPI-013, CPI-015, CPI-016 (and CPI-011 for F5) each need a new **version line** (append-only per `truth_schema.md` — never mutate existing rows) with corrected `allowed_consumers`/`forbidden_consumers`. This is the "issuer truth" precondition freeze D1(c) refers to indirectly: it is a `data/` write and is out of this wave's scope.
2. **`config/cycle_pattern/truth_schema.md`** — replace the "Consumer categories (non-exhaustive)" section with the reconciled list (§7), once Fable resolves the `measurement_surface` vs `measurement_page` (and `honesty_display` vs `cycle_docs`) merge-or-keep decision.
3. **`config/cycle_pattern/consumer_matrix.yml`** — extend `surfaces:` to include the FAM-A tokens the matrix currently omits entirely (`measurement_surface` or its merge target, `honesty_display` or its merge target, `hazard_cone_display`, `risk_context_strip`, `tripwire_context`, `sync_gauge_display`, `cone_rendering`, `mechanism_summary`, `hypothesis_generation`, `monitoring`), and every `artifact_classes` entry's `allowed_consumers` list needs the same extension so the matrix's promise ("consistent with the seed truths") becomes true.
4. **`scripts/check_cycle_pattern_authority.py`** — F4 shows the guard cannot see any of this by construction (literal module-path scan only). A real fix needs a **second, new check** (not an edit to this file's existing scan) that loads `truths.jsonl` and `consumer_matrix.yml` and asserts every row's `allowed_consumers`/`forbidden_consumers` tokens are drawn from the reconciled canonical list — this is new code, out of this wave's scope, and is itself a separate CI-authority change requiring its own review (`agentos` CI-authority inventory, per house law).
5. **`engine/cycle_pattern/truths.py` `validate_truth()`** — F4's second half: add vocabulary-membership checks to the existing enum-checking block (alongside `status`/`effect_class`/`era_stability`/`pit_class`) so no future `append_truth`/`transition_truth` call can introduce a ninth orphan token. Also out of this wave's scope; also a `scripts_ci_authority` inventory item.

### 8c. Explicit statement — mechanical application is CPI-owned follow-on work

This wave (A2) writes no runtime state, no `data/`, no `config/`, no `scripts/`, no `engine/`. Everything in §7 and §8a/8b is a **proposal for Fable's review**, not an applied fix. Applying it is a separate, CPI-owned wave that must itself be preregistered as a `data/` write (per freeze D3.3: "when a later accepted wave writes derived research views, they live under `data/cycle_pattern/` per CPI convention") and must resolve, before writing a single new registry line: (i) `measurement_surface` vs `measurement_page` as the single canonical display-surface token (or a deliberate decision to keep both with a documented distinction); (ii) `honesty_display` vs `cycle_docs` similarly; (iii) whether `forward_allocation`/`signal_generation`/`hazard_score_design` name real, distinct pipeline surfaces that belong in the matrix, or are typos/one-off inventions to be discarded; (iv) CPI-011's F5 narrowing (deliberate scope limit vs seeding omission); (v) the `hazard_baseline_override` latent token in `build_phase_clock_eval.py:690` before any phase-clock trial reaches `scored` status. Only after those five decisions is a mechanical remap safe. **Until this heal lands, freeze D1(c) continues to bind: no issuer truth is appended to the CPI registry.**

---

## 9. What this audit did not do (explicit non-scope)

No file under `data/`, `config/`, `scripts/`, or `engine/` was edited. No registry row was transitioned. No new consumer token was minted into any live file. No CI check was added or modified. No IMCE trial was registered and no outcome data was accessed — this audit is entirely about the pre-existing CPI vocabulary, not about IMCE's own content. The reconciled list in §7 and the mapping in §8a are inputs to a future, separately-scoped CPI heal wave; this document does not authorize that wave to start.
