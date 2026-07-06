# Codex "Three Additional Crucial Lobes" — Adjudication & Wave Program (by Fable)

**Ratified:** 2026-07-06
**Source docket:** `research/NEURAL_WEB_ADDITIONAL_CRUCIAL_LOBES_BY_CODEX.md` (Codex, 2026-07-06; committed alongside this adjudication). Codex proposed three new Neural Web lobes: (6) Claim Reliability / Narrative Truth, (7) Macro & Policy Transmission Fingerprints, (8) Portfolio & Thesis-Independence.
**Method:** 4-lane Sonnet census (`wf_e740408e`, file-level verification of every Codex evidence claim) → Fable draft → 2-lens Opus red-team (house-law/stats lens; build-executability lens — both APPROVE_WITH_EDITS) → Fable adjudication. §2 prints census corrections to the Codex doc; §2.5 prints what the red-team falsified in the Fable draft, per house law.
**Taxonomy authority:** `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md`. **Build authority for chartered lobes:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`. This document is the build authority for the WAVES it authorizes below — it charters no lobe.

---

## §1. Executive verdict

**Zero new lobes are chartered.** The docket's two-lobe concurrency cap is fully consumed (L1 short-side + L3 dispersion, both chartered 2026-07-06), and two of Codex's three proposals are already docketed entries with standing gates (Codex-7 = L6; Codex-8 = L8). Sorting against the LOBE/RAIL/WAVE taxonomy:

| Codex proposal | Taxonomy verdict | What IS authorized |
|---|---|---|
| 6. Claim Reliability / Narrative Truth | **NOT a lobe** — decomposes into: already-built (QI's `track_record.json`), an R2-rail wave, a bridge wave, and two accrual-gated future experiments | W-A claim-accountability audit; W-B `claim_reliability` bridge lobe key; NARR-2/NARR-3 registered as come-back experiments (no build) |
| 7. Macro & Policy Transmission | **IS docket L6** (Tier-2, gated). Gate unchanged: Phase-0 must beat the noisy-sector precedent OOS. No charter. | W-C: L6-P0 gate-clearing Phase-0 study (sector/basket grain, per-axis, governor-registered, prereg-frozen) |
| 8. Portfolio & Thesis-Independence | **IS docket L8** (mostly out-of-scope; held-book = Mastermind repo). In-scope slice already ~70% built (`reflexivity.py` + board chips) | W-D reflexivity wave: five-candidates-one-thesis detector + N_eff history (+ earnings-week leg if data exists) |

Codex's three killer questions are real institutional questions and the house should hold them. But the correct organs are mostly waves on existing tissue, not new lobes — misfiling waves as lobes is how program sprawl happens (docket §1).

---

## §2. Census corrections to the Codex doc (printed per house law)

What the 4-lane census confirmed exactly and what it falsified or found missing:

1. **EXACT:** falsifier is None for 8,923/9,069 claims; direction=0 is 71.0% (6,438); claims/grades counts 9,069/2,815. Codex's qledger arithmetic is fully confirmed.
2. **MISSED SUBSTRATE (Codex-6):** `site/qledger/track_record.json` (built nightly by `scripts/grade_qledger.py`) already IS a per-desk/per-family claim-reliability scorecard — hit_rate, wilson_ci_low, excess_mean, ACCRUING/UNGRADED states, promotion_readiness at 5/21/63d, and a challenger-vs-placebo duel context. Codex's "not yet a full narrative-trust lobe" underweights that the scoring core exists and is accruing; what is missing is coverage/accountability diagnostics and NW integration, not the scorecard.
3. **NOT COMPUTABLE YET (Codex-6 / NARR-2):** ALL 2,815 grades are horizon_d=5. No 21d/63d grade has matured anywhere. "Measure claim usefulness after 5, 21, and 63 sessions" cannot be run today at two of its three horizons; it is calendar-gated, not build-gated.
4. **PARTIAL (Codex-6):** "source/channel dimensions are not a real reliability ontology" — the fields exist (`source_tier` 9.0% fill, `channels` 1.5%, `source_id` 1.6%) but carry near-zero discriminative power today (all 812 source_tier rows are china_news tier=2). A per-tier reliability curve is unbuildable from current data; the QI masterplan already names this as its deferred keystone (≥500 graded labels gate).
5. **MISSED SUBSTRATE (Codex-7):** Codex cited the two weakest macro assets (`event_risk.py`, `hk_global_beta.py`) and missed the five load-bearing ones: `engine/rate_inflation_transmission.py` + `data/transmission/calibration.json` (cross-asset pass-through map), `engine/sector_rate_inflation.py` (per-sector SPDR rate/inflation chips — the "noisy-sector precedent" the L6 gate names), `engine/stock_macro_sensitivity.py` (per-name rate-beta tier / duration bucket / regime read, display-only, OOS beta persistence 0.36), the factor panel's `rate_duration_sensitive` DNA class, and `engine/risk_radar_intl.py` (the one macro-conditioned signal with a measured drawdown edge: CN composite 2.07× lift, p=0.01). Half of Codex's proposed "owns" vocabulary (`rate_sensitive`, `usd_sensitive`, `global_risk_beta`, `macro_headwind_active`) already exists display-only.
6. **SUBSTANTIALLY BUILT (Codex-8):** BOOK-1/BOOK-2 largely exist. `engine/reflexivity.py` computes pairwise similarity (membership-Jaccard + high-tier factor cosine) and N_eff (eigenvalue participation ratio) over the US candidate board; `us_stocks_v2.html.j2` renders per-card duplicate/partial/new chips and an n_eff_by_lane banner today. What's genuinely missing is the docket L8 in-scope residue: a named five-candidates-one-thesis aggregation, N_eff history, and the earnings-week leg (omitted v1 by ruling R-D).
7. **REFUTED (Codex-8):** any implication that book/held data flows exist — `mastermind_context.py` is entirely outbound; no held-book, no bot.db read path exists in this repo (rulings R-A, two-organisms law). Codex's BOOK-3 held-book bridge is a Mastermind-repo charter, not buildable here.
8. **PROCESS:** Codex proposed lobes without sorting against the docket taxonomy; two of three were already docketed (L6, L8) with gates it did not cite. (Fair note: the docket ratified the same day the Codex doc was prepared.)

---

## §2.5 Red-team corrections to the Fable draft (printed per house law)

The 2-lens Opus red-team (2026-07-06) falsified the following draft claims; all are fixed in the specs below:

1. **FALSE (would be silently destroyed):** "PR-B appends a markdown table to `docs/GRADING_CLOSURE.md`." That file is fully REGENERATED by its single writer (`audit_grading_closure.py:664-667`, `write_text`) every end-of-collect run — an appended section dies on the next nightly. PR-B ships its own `docs/CLAIM_ACCOUNTABILITY.md`, regenerated from its own JSON.
2. **FALSE (no such mechanism):** "schema bump per the bridge's versioning rules." No bridge versioning rules exist; `SCHEMA` is hardcoded v1 and `tests/test_mastermind_context.py` pins `schema_version == 1`. Adding a lobe key is backward-compatible additive: NO bump, tests extended not broken.
3. **UNBUILDABLE AS WRITTEN:** registering L6-P0 through `scripts/register_rule_experiment.py`. The CLI is RuleSpec-shaped (`--spec-hashes` required per exit/cohort grid; `declared_budget = len(spec_hashes)` hardcoded; family internal). House precedent for conditioning studies (`net_liq_regime_gate.py`, `entry_strata_phase0.py`, DISP-GATE-1) integrates `engine.trial_ledger.TrialLedger` directly from a standalone harness. Registration redesigned per RUL-C11.
4. **FALSE (column does not exist):** "spine_index supports per-sector splits." `data/neuralweb/spine_index.parquet` (288,666 rows) has NO sector column and is 99.9% entity-grain (`scope_type='entity'`). The prereg must name the symbol→sector join source, state its PIT limitation, and aggregate to sector BEFORE any cell is formed.
5. **MISLEADING:** RUL-C8's "zero render-path additions." `build_reflexivity_overlay.py:233/253` re-renders `site/us_stocks_v2.html` via `build_stock_board_v2.render()` — W-D is display/render work on an existing page (seconds-scale). RUL-C8 restated honestly.
6. **STALE (data exists):** the earnings-week leg's "IF a source exists" conditionality. `data/earnings/earnings.parquet` and `data/edgar/earnings_8k_dates.parquet` exist (plus `engine/earnings_blackout.py`). Leg 3 is authorized unconditionally; R-D's "omitted v1" was a scoping choice, not a data gap.
7. **HAZARD (durability):** N_eff history inside the `site/` overlay JSON — degraded runs emit `_empty_overlay()` (no history) and the builder is a pure rewriter, so history would silently reset. History moves to `data/reflexivity/n_eff_history.json` (dispersion `regime.json` pattern verbatim: bounded array, dedup by as_of, nightly single-writer).
8. **PIT defects in the axis series:** `data/ofr_fsi/fsi_credit.parquet` carries no publication vintage and publishes at ~1-business-day lag — axis reads must be lagged by frozen publication offsets in the prereg; the FRED 10y column is `us10y`, not `DGS10`. Also: PR-B wiring is a `run_as_collect_step()` call inside `scripts/collect.py` (sibling pattern, ~line 756), NOT a daily.yml/dag.yml lane entry; and `gradeable_share` must be labeled "not hit-gradeable (direction=0 claims are graded on excess only)" so it cannot be read as contradicting the R2 audit's CLOSED verdict on the same ledger.

---

## §3. Rulings

- **RUL-C1 (no charters):** no new lobe is chartered by this program. The two-lobe cap (docket §6) stays at L1+L3. Everything below is a rail wave, an existing-artifact wave, or a registered study — the same accounting RUL-P1 used for L4 instrumentation.
- **RUL-C2 (naming):** the bridge lobe key is `claim_reliability`, never `reliability` — `lobes['reliability']` already exists in `mastermind_context.py` with kernel-FDR-governance scope and a test-enforced standing_law string. Clobbering it is forbidden.
- **RUL-C3 (QI ownership boundary):** qledger and its grading semantics belong to the QI program (frozen since #1180; joint substrate ruling open). Legal here: read-only coverage/accountability diagnostics (W-A) and read-only NW bridge integration (W-B). ILLEGAL here: any learned source-reliability score, any per-source weighting, any change to grading semantics — that work is the QI masterplan's deferred keystone (≥500 graded labels) and stays theirs. W-A/W-B PRs must not modify `scripts/grade_qledger.py` or claim schemas.
- **RUL-C4 (L6-P0 legal shape):** the Phase-0 is a registered measurement, not a live conditioner. Constraints it must carry: (a) **per-axis, never fused** — the Signal Commons R3 positioning-fusion ruling applies to macro axes with full force; no composite macro-hostility score may be formed, each axis reads out separately; (b) **sector/basket/board grain only** — no per-name regressions (docket L6 gate); (c) **PIT flags at fire date** with frozen thresholds committed in the prereg BEFORE any overlap is computed (BD_PHASE0 pattern); (d) **governor-registered** through `scripts/register_rule_experiment.py`, pooled flat `fdr_family='replay'`, declared budget = verdict cells only; (e) **kernel untouched** — no kernel cells, no kernel consumers (Signal Commons R1 denial stands until 2026-10); (f) **drawdown-covariate control** — macro-hostile windows correlate mechanically with stressed tapes; the study must control contemporaneous market drawdown exactly as DISP-GATE-1's prereg does, or it merely rediscovers that stressed tapes are stressed; (g) **"beats the noisy-sector precedent" is operationalized**, not vibes: the sector-level precedent (`sector_rate_inflation` / canon shadow) failed on split-sample instability of its forward-IC, so an axis PASSES Phase-0 only if its hostile-vs-benign delta at the primary horizon is sign-stable with episode-clustered CI excluding 0 in BOTH OOS halves, at pre-registered n/episode floors. A pass re-opens the L6 charter question at the docket (still subject to the cap); a fail prints the null and L6 stays gated. Either way the study succeeds by being honest.
- **RUL-C5 (NARR-3 contradiction arbitration — no build):** "when narrative and price disagree, who wins" is retro-gradeable: contradiction records land in committed artifacts (`world_state.json`, confluence graph) whose git history is the PIT tape. No new nightly grader ships (the cap protects nightly/review bandwidth). Registered as a come-back experiment: earliest useful read ~2026-10-01 (needs ~3 months of contradiction records + matured 21d qledger grades).
- **RUL-C6 (NARR-2 story decay — no build):** family-level decay curves for qledger claims are calendar-gated on 21d/63d grade maturation. Registered as a come-back experiment (~2026-10-01). The kernel already ships family decay curves for spine families (`kernel_families.json`); qledger families join that surface when their grades mature, they do not get a parallel apparatus.
- **RUL-C7 (reflexivity wave stays under its rulings):** R-A (held-agnostic), R-E (US board only), R-F/R7 (display-only, `is_context_only`, no behavioral consumer) all stand. The earnings-week leg ships only if an earnings-calendar source already exists in-repo; if not, the builder prints the gap in the PR and ships the other two legs — no new collector is authorized by this program.
- **RUL-C8 (bandwidth accounting, restated per red-team):** zero new lobes, zero new nightly graders. W-A rides the existing end-of-collect audit call chain in `scripts/collect.py` (seconds); W-B is an additive key in an existing nightly compiler; W-D extends the existing reflexivity overlay build — which ALREADY re-renders `site/us_stocks_v2.html`, so W-D is seconds-scale work on an existing render step, not "off-render"; W-C is an off-render manual study. Net new nightly cost: seconds. This is the RUL-P9 discipline, stated honestly.
- **RUL-C9 (registration hygiene):** every new artifact registers in `config/synapse.yml` (tier, horizon_role, scored_path_surfaces, weights) with `docs/SIGNAL_BUS.md` regenerated in the same PR; every new write path declares its commit path per RUL-P10 (gitignored / single-writer git / R2); come-back experiments register in the experiments registry so the admin Experiments tab carries their dates.
- **RUL-C10 (LLM law):** nothing in this program lets an LLM score, escalate, or originate. W-B carries qledger *measured* statistics into the bridge (display tier, additive); the cortex may cite them, never adjust them.
- **RUL-C11 (L6-P0 FDR family — a considered deviation, logged):** the flat `fdr_family='replay'` mandated by the docket governs the **rule-replay tape** (exit/cohort/delay grids over replay_boarded); L6-P0 is a **conditioning contrast study** on a different tape (spine index) with no RuleSpec grid, and the register CLI structurally cannot carry it (§2.5.3). Following the standalone-harness precedent (net_liq_regime_gate, entry_strata_phase0, DISP-GATE-1), L6-P0 integrates `TrialLedger` directly under a NEW flat pooled family **`fdr_family='macro_tx'`** — the single family for ALL present and future macro-conditioning studies, sub-scoping prohibited for exactly the reason the replay family is flat (TrialLedger keys on exact strings; islands defeat the budget). Declared budget counts every computed cell that could feed a verdict or a future prereg: 4 axes × 3 horizons = **12** (h21 = the 4 verdict cells under BH q=0.10; h5/h63 printed as descriptive but budget-counted — labeling computed cells "descriptive" to exempt them from the budget is the forking-paths laundering RUL-P3 exists to prevent). Per-sector splits are descriptive-only and stamp the report as a contamination surface: any later prereg on this tape carries `derived_from_surface: macro_tx_phase0_v1`. The study ALSO registers a row in the experiments registry seed (admin visibility + verdict date), which is the house mechanism for non-replay studies.

---

## §4. Wave plan

| Wave | PR | What | Model lane | Risk |
|---|---|---|---|---|
| W-0 | PR-A | Commit Codex source doc + this adjudication; register NARR-2/NARR-3 come-back experiments | Fable | — |
| W-A | PR-B | Claim-accountability audit: falsifier coverage, gradeability, maturity mix per desk/family → `data/governance/claim_accountability.json` + docs table | Sonnet build, Opus review | LOW |
| W-B | PR-C | Bridge lobe key `claim_reliability` in `mastermind_context.py` reading `site/qledger/track_record.json` (display, additive, standing-law honesty string) | Sonnet build, Opus review | LOW |
| W-C | PR-D | L6-P0: prereg doc (Fable-frozen) → governor registration → study harness → run → report | Fable prereg, Sonnet build, **Opus stats review**, Fable verdict | **HIGH** |
| W-D | PR-E | Reflexivity wave: five-candidates-one-thesis detector + N_eff history (+ earnings-week leg if data exists) | Sonnet build, Opus review | LOW |

Merge sequencing: PR-A first (provenance). PR-B/C/E may build in parallel worktrees but merge serially with synapse.yml rebase-check (registry-drift law) — each of PR-B/E adds a synapse artifact, so each bumps the pinned artifact count in `tests/test_signal_bus_doc.py` (currently 187) and regenerates `docs/SIGNAL_BUS.md`; whoever merges second rebases and re-bumps. PR-D's prereg must be committed (in PR-A or a standalone first commit) BEFORE its harness runs.

---

## §5. PR-B spec — claim-accountability audit (W-A)

**What:** `scripts/audit_claim_accountability.py`, an end-of-collect audit sibling of `scripts/audit_grading_closure.py` (R2 rail family). Read-only over `data/qledger/claims.jsonl` + `grades.jsonl` + `site/qledger/track_record.json`.

Per desk and per claim_family, emit:
- `n_claims`, `falsifier_coverage` (fraction with non-null falsifier — today 146/9,069 = 1.6% global),
- `hit_gradeable_share` (direction≠0 — the 71% direction=0 population is **not hit-gradeable** (graded on excess only); label it exactly that way so it cannot be read as contradicting the R2 audit's CLOSED verdict on qledger),
- `maturity_mix` (share graded at 5d; 21d/63d matured counts — today 0),
- `fill_convention_split` (asof_legacy vs next_bar grade counts — the #1180 discontinuity),
- `source_ontology_fill` (source_tier/channels/source_id fill rates — honesty row showing why per-source reliability is not yet computable).

Output: `data/governance/claim_accountability.json` (git-committed, single-writer = this audit step; RUL-P10 path b) + its OWN `docs/CLAIM_ACCOUNTABILITY.md` regenerated from that JSON (§2.5.1 — never co-own `docs/GRADING_CLOSURE.md`, which its single writer fully regenerates). Synapse registration: infrastructure tier, `horizon_role: context`, `scored_path_surfaces: []` (+ count bump + SIGNAL_BUS regen). Wiring: a `run_as_collect_step()` call added in `scripts/collect.py` immediately after the grading-closure audit call (~line 756; sibling pattern) — dag.yml needs NO new entry (conformance tracks workflow-YAML invocations, not intra-module calls). CLI mirrors the sibling (`--check`, `--root`, `--json`). Tests: fixture-based (synthetic claims/grades), zero dependence on real data files. **Scope fence: read-only — this PR must not modify `scripts/grade_qledger.py`, claim schemas, or any QI-owned semantics (RUL-C3).**

**Why this and not more:** the audit is the missing "can we trust the story?" *coverage* instrument — it makes falsifier-starvation and structural ungradeability standing and visible instead of rediscovered per-program (the same move R2 made for grader closure). The scoring itself already exists (track_record.json) and the learned layer is QI-gated.

---

## §6. PR-C spec — `claim_reliability` bridge lobe key (W-B)

**What:** add `lobes['claim_reliability']` to `engine/neuralweb/mastermind_context.py` LOBE_SUMMARIZERS, reading `site/qledger/track_record.json` (+ `data/governance/claim_accountability.json` if present, fail-open).

Emit per desk (bounded, top families only): `hit_rate`, `wilson_ci_low`, `n`, `state` (ACCRUING/UNGRADED), `horizon_d=5` explicit, plus a **mandatory standing_law string**: qledger reliability is 5d-only and ACCRUING; no family is promotion-ready; per-source reliability does not exist yet (ontology fill printed by the accountability audit); nothing here may rank or gate. Mirror the existing `lobes['reliability']` test pattern (standing-law-present test; `tests/test_mastermind_context.py`). The key is ADDITIVE and backward-compatible — **NO schema/version bump** (§2.5.2: `SCHEMA` stays `neural_web_mastermind_context.v1`, `schema_version` stays 1, the pinned test stands); `is_context_only` untouched (true), all authority booleans stay FALSE. Builder must also: add the matching `_LOBE_TO_ARTIFACT_IDS` entry (else `lobe_manifest.has_rich_summary` silently misses it) and add `mastermind:context` to the `site-qledger-track-record` synapse entry's `external_consumers`. The bridge remains dark (MASTERMIND_NW_CONTEXT defaults OFF; arming gate unchanged, come-back 2026-07-19 — this PR does not touch arming).

**Why:** the census found qledger's track record is consumed by NOTHING in the Neural Web bridge — Mastermind's reliability context is kernel-only. Claim-desk trust context is exactly what the bridge's charter says belongs there, and it is measured, not narrated.

---

## §7. PR-D spec — L6-P0 gate-clearing Phase-0 (W-C)

**Prereg:** `research/macro_tx/L6_PHASE0_PREREG.md`, Fable-written and committed BEFORE the harness runs. The prereg is the single numeric authority (BD_PHASE0 pattern — this section deliberately does not restate thresholds it will freeze). It must freeze:

1. **Axes (separate, never fused — RUL-C4a):** rates_shock (Δ 10y yield — `data/fred/DGS10.parquet`, column **`us10y`**), usd_shock (dollar 20d move, factor-panel USD source), credit_stress (`data/ofr_fsi/fsi_credit.parquet`, column `fsi_credit`, and/or HY OAS `BAMLH0A0HYM2`), liquidity (the existing liquidity_overlay basis). Each axis defines hostile/benign at fire date from PIT-available series with frozen windows/thresholds/σ. **PIT law (§2.5.8):** each axis read is lagged by its frozen publication offset — OFR FSI carries no vintage stamps and publishes at ~1-business-day lag (lag ≥1BD, frozen in prereg); market yields/prices are same-day-close safe for nightly fires; any revisable macro series must either use `data/fred_vintage/vintages.parquet` or be excluded.
2. **Fire tape:** primary = `data/neuralweb/spine_index.parquet` via `engine/neuralweb/query.py` (288,666 rows, graded at spine horizons, deep history on the track_record ledger) with ERA-LAW splits and survivorship stamps; sensitivity = `data/replay/replay_boarded.parquet` modern cohort (**Mac-local, absent from git checkouts BY DESIGN** — the harness prints tape-absent honestly on non-Mac runs). Vintage stamp (`engine/vintage_stamp.py`) mandatory on all outputs. The prereg prints achieved graded-fire and episode counts per era BEFORE any OOS statistic.
3. **Grain:** pooled board + per-sector descriptive splits. NO per-name cells (docket gate). **The spine index has NO sector column (§2.5.4)** — the prereg names the symbol→sector join source (e.g., the factor panel / stock library sector map), states its PIT limitation (a current-date sector map applied to historical fires is an anachronism accepted as a declared limitation, sectors being slow-moving), and mandates aggregation to sector/pooled grain BEFORE any cell is formed.
4. **Endpoints:** primary = hostile-vs-benign delta in stop-rate / hit-rate at h21 (secondary h5/h63 descriptive but budget-counted per RUL-C11), episode-clustered — the cluster unit is the contiguous hostile WINDOW (calendar episode), never the fire, because fires across all sectors on the same macro dates are one draw, not hundreds — with the contemporaneous-market-drawdown covariate control (RUL-C4f): hostile-vs-benign contrasts are computed within market-drawdown strata (stratification, not regression residualization — frozen strata in the prereg), so "hostile macro predicts worse fires" cannot reduce to "drawdowns predict drawdowns."
5. **Verdict gates (per axis):** sign-stable + episode-clustered CI excluding 0 in both OOS halves + n/episode floors (numbers frozen in prereg; episode floor is the binding scarcity — hostile episodes are countable on two hands per half even at full depth; expect and honestly print P0-DEFER where the floor fails).
6. **Registration (RUL-C11, replacing the draft's governor route — §2.5.3):** the harness integrates `engine.trial_ledger.TrialLedger` directly (standalone-harness precedent), `fdr_family='macro_tx'` flat pooled, `log_declared_budget(12)` BEFORE the run; BH q=0.10 across the 4 primary h21 cells; every results summary prints the cumulative pooled `macro_tx` trial count. A row is added to the experiments registry seed (exp id `macro-tx-phase0`, verdict/come-back date) for admin visibility. `derived_from_surface: null` (first registered question on macro axes); the report itself becomes a contamination surface for any later prereg on this tape.
7. **Pre-committed branches:** P0-PASS(axis list) → re-open L6 charter question at the docket (subject to cap; NOT an automatic charter); P0-FAIL → null printed, L6 stays gated; P0-DEFER on episode floor → remediation notes + come-back date. The report (`research/macro_tx/L6_PHASE0_REPORT.md`) prints all cells including nulls; the word "validated" may not appear (research/*.md is not CI-scanned — discipline, not automation).

**Harness:** `scripts/research/macro_tx_phase0.py`, Mac-local, off-render. Sonnet builds; **Opus stats review is mandatory before the report merges** (episode-clustering honesty, stratified covariate control correctness, era-law splits); Fable adjudicates the verdict.

**Explicitly out of scope:** any live flag, chip, or world_state key from this study; any composite macro score; any kernel cell; any per-name output. Display integration happens only if L6 is ever chartered.

---

## §8. PR-E spec — reflexivity wave (W-D)

Three legs on `engine/reflexivity.py` + `scripts/build_reflexivity_overlay.py` + `site/factordata/reflexivity_overlay.json` (schema minor-bump; all legs display-only under R-F/R7):

1. **Five-candidates-one-thesis detector:** connected components over the existing pairwise-similarity matrix at the existing duplicate threshold (`DUPLICATE_THRESH = 0.65`, reflexivity.py:64); emit `same_thesis_groups: [{members, size, basis, label}]` for components of size ≥3; board banner line when any group ≥5 ("N candidates, one thesis: <basis>"), EN/ZH, no `title=` translation (CI law). Banner text lives in the existing template macros (`rx_board_banner()`/`conc_banner()` in `templates/us_stocks_v2.html.j2:61-87` — server-side Jinja; the builder only passes `rx=overlay`). This is the docket L8 in-scope item verbatim. No ordering/ranking effect — annotation only (Article 2).
2. **N_eff history:** NEW `data/reflexivity/n_eff_history.json` following the dispersion `regime.json` pattern verbatim (bounded history array `{as_of, n_eff_by_lane, same_thesis_group_count}`, `_HISTORY_LEN=252`, dedup-by-as_of, tail-trim), single-writer = `build_reflexivity_overlay.py` reading-prior-then-appending, git-committed nightly (RUL-P10 path b; §2.5.7 — NOT inside the `site/` overlay, which degraded/express runs rewrite from scratch). Synapse-registered (infrastructure tier, count bump). This is the accrual substrate for Codex's BOOK-1 "N_eff by regime" — measurable in ~2 quarters, not today.
3. **Earnings-week leg (authorized unconditionally — §2.5.6):** populate the R-D field (same-earnings-week cluster flag) as a Jaccard-adjacent annotation from the EXISTING stores (`data/earnings/earnings.parquet`, `data/edgar/earnings_8k_dates.parquet`; `engine/earnings_blackout.py` shows the read pattern). No new collector (RUL-C7). If coverage over the current board proves thin at build time, the leg ships with its coverage fraction printed in the overlay rather than being dropped.

Tests: extend `tests/test_reflexivity_overlay.py` — component detection, history bounding + dedup, empty/degraded-run-preserves-history guard, banner render. CN/HK stay excluded (R-E). No behavioral consumer may read any of it (R-F).

---

## §9. What this program does NOT do (scope fences)

- No lobe charters; the cap stays L1+L3 (RUL-C1).
- No learned source-reliability model, no per-source weights, no qledger semantic changes (QI-owned, ≥500-label gate; RUL-C3).
- No kernel cells, consumers, or conditioning before the 2026-10 FDR batch (Signal Commons R1 denial stands).
- No fused macro composite (Signal Commons R3 stands); no per-name macro fingerprints (L6 gate stands until P0 passes AND a charter is issued).
- No held-book anything (L8 → Mastermind repo; two-organisms law); no sizing, no gross_mult unclamping; no CN/HK reflexivity expansion (R-E stands).
- No LLM-scored narrative truth (Article 1 + LLM de-escalation-only law): "narrative truth" in this house means measured forward outcomes of registered claims, nothing else.
- No new nightly graders, no render-path additions (RUL-C8).

## §10. Status log

- 2026-07-06: Census complete (4 lanes, every Codex evidence claim verified/refuted at file level); draft adjudication written; 2-lens Opus red-team returned APPROVE_WITH_EDITS ×2; all blocking/major findings adjudicated and folded (§2.5); program ratified. Waves dispatching.
