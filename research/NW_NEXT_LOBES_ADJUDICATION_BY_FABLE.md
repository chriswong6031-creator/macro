# Codex "Next Five Lobes" — Adjudication & Complementary Build Waves (by Fable)

**Ratified:** 2026-07-06 (post 5-lane Sonnet census + 5-lens Opus red-team + Opus cross-cutting synthesis; corrections printed in §0.5/§7 per house law)
**Input:** Codex memo `NEURAL_WEB_NEXT_LOBES_PRIORITY_BY_CODEX.md` (2026-07-06, written in a Codex worktree; referenced, not committed here — same convention as #1664).
**Sibling program (same day):** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md` (#1664) adjudicated a *different* Codex memo (the signal-discovery gap map) ~1h before this one and chartered 8 PRs. The two memos overlap heavily; §3 reconciles every shared disposition so nothing double-registers. **Where the two programs touch the same surface, #1664 owns it** — it ratified first.
**Method:** memo → 6-lane census (Sonnet, file-level evidence) → 5 per-lobe adversarial reviews (Opus, dual lens: house-law/taxonomy + duplication/alpha-realism) → cross-cutting synthesis (Opus, xhigh) → this Fable adjudication.

---

## §0. Census ground truth

1. **CONFIRMED (all of Codex's data evidence):** `bottom_sensors.parquet` 1,722 rows with `sponsorship_state`/`rs_repair_state` 100% unavailable; `long_hold_labels.parquet` 113,542 rows with label mix matching Codex's figures exactly (compounder=195, cheap_trap=4,409, tactical_only=4,406); replay registry = `exit_grid_v1` only (15 pooled trials).
2. **ROOT CAUSE (sponsorship, sharper than the memo):** the §C3 connector (`engine/neuralweb/bottom_sensors.py:263-367`) is complete and frozen; `data/oracle/panel_s.parquet`/`panel_m.parquet` are gitignored (`.gitignore:220`) and built off-render (`daily.yml:962 --skip-panel`), and the self-hosted runner's virtualized checkout never sees them — so the nightly build degrades to `unavailable` **structurally**, every night. Independently confirmed by #1664 §0.2. **Fable smoke test (this program):** with the Mac-local panels (panel_s 11 nodes 1998→2026-07-01; panel_m 354 nodes →2026-07-02), the frozen C3 code returns real states on 400 sampled mapped tickers — 223 tailwind / 106 neutral / 71 headwind / 0 unavailable. The entire "lobe" is a publish gap.
3. **`rs_repair_state`** is an explicit stub (`bottom_sensors.py:622-623`), owned by entry-intelligence #1302 W0.4. Documented, not fixed, here.
4. **Operator instrumentation is LIVE, not missing:** PR-8/#1550 shipped `admin/actions.py` (append + fsync), `POST /api/actions` behind `_guard(write=True)` (`admin/server.py:378-394`), Experiments-tab capture buttons (`admin/static/app.js:212-226`). `data/operator/` is gitignored **by design** (RUL-P10 path a). Codex's "action_ledger.jsonl does not exist yet" is a worktree-visibility artifact.
5. **`trigger_tier` (136) / `entry_quality_band` (57) low counts are NOT a defect:** they are populated live from `signal_gate.json`/`us_standouts.json` (`bottom_sensors.py:636,669`) — the counts are how many *current* names carry an active trigger/band.
6. **Thesis layer exists and operates:** `engine/thesis_funnel.py`, `moat_falsifiers.py`, `expectation_state.py`, `sue.py`, `long_hold_clocks.py`, `capital_allocation.py`, `falsifier_tripwires.py` all live (mtime 2026-07-06); per-stock surface at `templates/stock.html.j2:1423/1503`; G1 kill-test RUN and DEFERRED on honest n-floor (#1544, 4 compounder clusters vs ≥25); A2 G1-Retest frozen (~2027-H2); expect-drift F3 Ruler-P run and corrected (#1642: only ED-2 sue_streak DESCRIPTIVE_PASS; ED-1/3/4/5/6/7 NULL).
7. **Dilution substrate is landing, not absent:** `collectors/edgar_dilution.py` registered `_SLOW` nightly-only (`scripts/collect.py:137`, shipped #1462); `data/edgar/dilution_events.parquet` absent because no nightly sweep has completed since go-live. First materialization expected the next nightly. The three dilution columns in `bottom_sensors` (`days_since_shelf`/`days_since_takedown`/`dilution_events_365d`) populate then.

## §0.5 Corrections to our own census (printed per house law)

1. **FALSE (abstention census):** "qledger has zero graded claims; first resolutions ~2026-09." `data/qledger/grades.jsonl` holds **2,815 directional excess-return grade rows** (`run_status.json n_already_graded=2811`); `status='open'` in `claims.jsonl` is claim *lifecycle*, not grading state. Caught by the operator-lane review; verified by the synthesis critic. Any operator-grading harness joins `grades.jsonl` to `claims.jsonl` by `claim_id` (grades carry `claim_id` but not `claim_family`).
2. **WRONG BASIS (abstention census):** "dispersion regime history reconstructs minutes-scale via `.tail(280)`." `dispersion.assess()` uses an **expanding-window** percentile (`engine/dispersion.py:45`); L3_PREREG declares expanding as the PIT-primary; `regime.json` history has len=2. The trailing re-run is only the sensitivity arm. (Now moot here — #1664 PR-B2 owns the reconstruction and its §6.2 spec carries the same correction.)
3. **INCOMPLETE (sponsorship review):** "regenerate + commit the panels; zero code cost." Panels are gitignored and 45MB combined — they cannot ride git, and a local regen is invisible to the runner (virtualized FS). Caught by Fable inline; #1664 RUL-7 resolves the publish path (R2 + nightly download shim). A ~20KB committed compact artifact (latest `vel_1m`/`accel` per node — all the C3 connector reads) remains a cheaper fallback if the R2-creds fragility bites (expired-secrets precedent); recorded as an option for #1664's PR-C1 builder, **not** built here.

---

## §1. Adjudication table (the five proposed lobes)

| # | Codex lobe | Verdict | True classification | Disposition |
|---|---|---|---|---|
| 1 | Sponsorship / Forced-Flow Absorption | **GO-MODIFIED** | data-ops publish gap + existing wave | Publish path = #1664 PR-C1. Science verdict on sector vel/accel = the already-registered `esx_sponsorship` reserve (RUL-16, budget 8, entry-stack program) — no new prereg here. Ownership/13F leg **struck** (§2 RUL-N3). Short-covering leg stays docket-L10-parked (~2027+, PIT short interest). |
| 2 | Fragility / Solvency / Event-Hazard | **GO-MODIFIED** | one wave + two duplicates | F-HZ-1 (dilution hazard) is the only unbuilt, non-conflicting piece → **PR-2 this program** (§5.2). F-HZ-2 = the frozen A2 G1-Retest (~2027-H2) — re-running it would double-dip `fdr_family='long_hold'`. F-HZ-3 = shipped `esx_ev_blackout` (+8.7pp stop5 inside earnings window; **mae21/mae63 NULL** — Codex's clean-21/63 base-rate mechanism is already contradicted at forward horizons). |
| 3 | Cash-Patience / Abstention | **GO-MODIFIED** | R1 experiment waves, not a lobe | Unconditional delay ladder = #1664 PR-B1 (WAIT-GRID-1, 10 cells, frozen spec). Regime-conditioned skip = #1664 PR-B2 (DISP-GATE-1). The lean_out-conditioned delay contrast (this memo's ABS-1) is recorded as a **batch-3 follow-on** after B1+B2 land (§3). Opportunity-cost symmetry is a report law (§2 RUL-N6), not an experiment. |
| 4 | Long-Term Thesis / Expectations-Drift | **KILL** (as charter) | existing-program work | Duplicates the chartered, mostly-shipped long-hold thesis program (G1 run+DEFERRED; F3 Ruler-P run; A2 roster frozen Σ=29 of 40 ceiling). LT-THESIS-1 = G1; LT-THESIS-2 = F3 (SUE live via `engine/sue.py`; analyst *revenue* revisions are LH-R9 paid-data SKIP-ALL); LT-THESIS-3 = `moat_falsifiers` + A2 falsifiers. One salvage: the **reverse-DCF "what must be true" card** (W3 PR-N) is genuinely unbuilt and computable on ~785 names — routed as a recommendation to the long-hold program's amendment process (its W3 lock is theirs to lift), NOT built here. |
| 5 | Realized Decision / Execution / Operator-Feedback | **GO-MODIFIED** | live rail + queued harness + blocked half | Instrumentation live (#1550). Capture completion (alert IDs, admin Alerts tab, `overrode` button) = #1664 PR-C4. The **DQ-2 grading harness** (rails post-Fable queue item) is accelerated → **PR-1 this program** (§5.1), display-empty until the Wilson floor. Execution-realism half (fill_slippage/spread/tax-lot vs realized fills) is **blocked on a non-existent R4 Mastermind fills-bridge contract** — deferred with that named unblock; tax-lot sensitivity stays in the rails queue as an R1 experiment. |

**Meta-verdict on the memo:** the institutional framing (decision-specific organs, consequence, labels, replay, realized-decision attribution) is sound and worth keeping as prose. The build content mis-files everything as lobes: zero of five clear the docket §1 lobe bar, and the memo's exclusion list omits four active programs that own most of the territory (long-hold thesis, entry-stack Amendment-2, the rails post-Fable queue, L1 phase-1). The one genuinely valuable un-docketed find — sponsorship as a publish gap — was independently found and chartered by #1664 the same hour.

---

## §2. Program rulings

- **RUL-N1 (zero lobes):** this program charters ZERO lobes. L1/L3 remain the chartered set (two-lobe cap, RUL-P1). Both build waves here are rail-consumers: PR-1 executes a rails-queue item; PR-2 is a preregistered descriptive study on existing nwqs-c machinery.
- **RUL-N2 (decision chain struck):** the memo's operating-stack chain (`fire → sponsorship → fragility → abstention → thesis → realized`, memo line 570) is the prohibited fused-escalation shape in narrative form — it contradicts the memo's own red-team warning #1. **Struck.** Each organ ships as a parallel display column; no organ's output may condition another organ's escalation, gating, or sizing. Any pairwise interaction requires its own prereg naming both parents (factor-kill-interaction precedent).
- **RUL-N3 (sponsorship vocabulary + sign):** only the frozen C3 neutral vocabulary (`tailwind/headwind/neutral/stale/unavailable`) may surface. The memo's supportive mechanism labels (`forced_flow_reversal`, `ownership_breadth_repair`, `insider_or_management_support`, `short_covering_fuel`) are barred by entry-stack RUL-28 until evidence supports them. The ownership/13F leg is struck on three stacked priors: `esx_insider_sponsor` 3-for-3 refuted/null at 21d (#1566), `long_hold.insider_sponsor_lh` F4 null at 252d, and the standing `smart_money` CONTEXT-ONLY/contrarian-crowding ruling — 13F-as-positive-sponsorship proposes the *opposite sign* to a filed phase-0 verdict.
- **RUL-N4 (qledger substrate):** `grades.jsonl` (2,815 rows) is the live counterfactual substrate for operator grading; the "zero graded" framing is discarded (§0.5.1). The DQ-2 harness joins by `claim_id` and prints the coverage-blocked caveat (n_blocked_by_coverage=14,738) honestly.
- **RUL-N5 (n-before-stat):** PR-2 (and any successor study here) prints achieved fire-n and episode-cluster-n BEFORE any statistic; DEFER on a floor miss is an expected, printed outcome, not a failure.
- **RUL-N6 (abstention prior + symmetric cost):** the prior for all wait/skip studies is **wait_costs** — EXIT-GRID-1's lesson is that drawdown control is an ENTRY problem, and delay most plausibly forfeits MFE. Every abstention-flavored report prints foregone upside symmetric with avoided drawdown. This binds #1664's WAIT-GRID-1 reports too (consistent with its §6.1 obligations).
- **RUL-N7 (F-HZ-1 lane):** F-HZ-1 runs as a standalone preregistered phase-0 (esx-study pattern), NOT through R1 (its conditioning column is an external join, and the R1 CohortFilter v1 vocabulary is frozen to replay_boarded columns). It registers a **new flat family `fdr_family='hazard'`** with declared budget 3, descriptive-first. It must NOT touch `fdr_family='long_hold'` (frozen) or `'replay'` (not a rule replay).
- **RUL-N8 (DQ-2 shape):** the harness is pure after-the-fact measurement. No summary statistic publishes below **n≥25 graded operator actions** (the cortex A2 Wilson floor); below floor the artifact carries `{state:'accruing', n}` only. Operator overrides are graded, never treated as authority. Output artifact is git-committed small JSON with a named single writer (RUL-P10 path b); the harness runs on the ops lane where the gitignored ledger lives — never the CI render band.
- **RUL-N9 (no re-litigation):** nothing in this program re-tests: G1's frozen family, esx_insider_sponsor's null, esx_ev_blackout's mae nulls, the exit-routing NO-GO, or the crowding split-half FAIL. Where the memo proposes any of these, the disposition is the existing clock.
- **RUL-N10 (merge discipline):** PR-1 and PR-2 build in separate pre-created worktrees off fresh origin/main; any synapse.yml-touching PR regenerates SIGNAL_BUS.md in-PR and rebase-checks before merge; same-day squash-merge; #1664's in-flight waves have merge priority on any contested file.

---

## §3. Cross-program reconciliation (#1664)

| Surface | Owner | This program's action |
|---|---|---|
| Sponsorship publish path (panels → runner) | #1664 PR-C1 (RUL-7: R2 + download shim) | None. Compact-artifact fallback recorded (§0.5.3) for their builder if R2-creds fragility bites. |
| qa_bottom_sensors / measurement coverage surfaces | #1664 PR-C1 + PR-A1 | None. |
| WAIT-GRID-1 delay ladder | #1664 PR-B1 (frozen §6.1) | None. RUL-N6 report symmetry noted. |
| DISP-GATE-1 registration + PIT basis reconstruction | #1664 PR-B2 (frozen §6.2) | None. |
| **Batch-3 follow-on (recorded, not registered):** lean_out-conditioned delay contrast (this memo's ABS-1: delay {1,5} × cohort {lean_out} × hold(21)) | next replay batch after B1+B2 land | Registration deferred until both parents' surfaces exist; will carry `derived_from_surface: wait_grid_v1 + disp_gate_v1` and consume PR-B2's reconstructed basis so regime labels cannot diverge. |
| Operator capture UI (alert IDs, admin Alerts tab, overrode button) | #1664 PR-C4 | None. PR-1's harness consumes what C4 captures. |
| DQ-2 grading harness | **this program PR-1** (rails queue item, accelerated) | Build (§5.1). No file overlap with C4 (engine/script vs admin UI). |
| Dilution/fragility veto study | **this program PR-2** | #1664 deferred its fragility-veto variant pending B2's join pattern; PR-2 needs no R1 join (RUL-N7) and its data gate (first `edgar_dilution` nightly sweep) resolves independently. If both later want a replay-tape dilution column, it registers through their B2 extension pattern, once. |

---

## §4. Wave plan

| Wave | PR | What | Model lane | Risk |
|---|---|---|---|---|
| W0 | PR-0 | This adjudication doc | Fable + Opus review | — |
| W1 | PR-1 | DQ-2 operator-action grading harness (§5.1): engine module + ops-lane script + synthetic-fixture tests + committed summary artifact (accruing state) | Sonnet build, Opus review | MED |
| W1 | PR-2 | F-HZ-1 dilution-hazard prereg + study harness (§5.2): prereg doc committed BEFORE any run; harness run-gated on `dilution_events.parquet` materializing | Sonnet build, Opus stats review | MED |

Deferred ledger (with named unblocks): ABS-1b options-hostile arm (S-TOP_RISK accrual ~2026-Q4); F-HZ-2 → A2 G1-Retest clock (~2027-H2); F-HZ-3 clean-flag extension (prior mae-null; only as `esx_ev_blackout` extension with `derived_from_surface`, low priority); reverse-DCF card → long-hold program amendment (their W3 lock); L5 execution realism → R4 Mastermind fills-bridge contract (does not exist; Mastermind-repo charter); public alerts.html capture → cross-origin/auth architecture decision (#1664 RUL-8 holds); sponsorship lifecycle grammar → docket L10 (~2027+); thesis anything → long-hold program.

---

## §5. Frozen specs (Fable)

### §5.1 PR-1 — DQ-2 operator-action grading harness

- **Module:** `engine/operator_grading.py` + runner `scripts/grade_operator_actions.py`. Template: `engine/btc_override_ledger.py` — reuse its `_bh()` (BH q=0.10) and `_bootstrap_null()` (PIT circular block-bootstrap, BOOT_BLOCK=21, BOOT_B=2000, seed=7) **verbatim by import**; never re-implement.
- **Inputs:** `data/operator/action_ledger.jsonl` (gitignored server-local; the harness runs on the host that has it — Mac ops lane, manual/ops cadence). Machine counterfactual: `data/qledger/claims.jsonl` joined to `data/qledger/grades.jsonl` on `claim_id` (RUL-N4).
- **Matching:** an action row (`surface`, `action`, server `ts`) matches claims whose `surface`/id fields correspond and whose claim window contains or immediately precedes `ts`; unmatched actions are counted and printed, never silently dropped.
- **Pre-declared contrasts (family `fdr_family='operator'`, declared budget 3, logged before any run):** (1) `overrode` — operator direction vs machine-claim graded outcome at the claim's horizon; (2) `dismissed`-then-worked rate vs matched acted base rate; (3) `acted`-then-failed rate vs matched dismissed base rate. Descriptive-only until the registered floor.
- **Floor (RUL-N8):** n≥25 graded operator actions per contrast before any Wilson/bootstrap statistic publishes. Below floor: `{state:'accruing', n_actions, n_matched, n_graded}` only. No site surface this wave; the artifact is consumable later by #1664's evidence panel as an accrual clock row.
- **Output:** `data/governance/operator_grading.json` — committed, small, single-writer = the runner script (RUL-P10 path b). Vintage-stamped (rails PR-1 helper). The word "validated" never appears.
- **Tests:** synthetic fixtures only (fake ledger + fake claims/grades): matching, unmatched accounting, floor gating, BH/bootstrap import parity, artifact schema stability.

### §5.2 PR-2 — F-HZ-1 dilution-hazard phase-0

- **Prereg doc:** `research/hazard/F_HZ1_PREREG.md`, committed in the PR BEFORE any run; it is the numeric freeze authority (thresholds live there, not here — two sources drift).
- **Question (frozen):** do production fires carrying an active dilution hazard at fire date — (a) shelf registered ≤365d, (b) takedown ≤90d, (c) ≥1 dilution event trailing 365d — show higher stop5 and dead_money_21 at 21d than fires without, episode-clustered?
- **Tape & join:** `replay_boarded` production fires (ERA LAW: verdict_grade=True cohort for absolute rates) joined to `data/edgar/dilution_events.parquet` at fire_date on **filing_date PIT stamps** (no revision risk). Coverage, dead-name limitations (cheap_trap survivorship caveat per DEAD_NAME_SPIKE), and the collector's backfill depth are printed BEFORE any outcome table; if backfill is forward-only, the study converts to an accrual prereg with an arrival-rate clock — a valid printed outcome (RUL-N5).
- **Family & budget:** `fdr_family='hazard'` (new flat family), `declared_budget=3` (one per hazard predicate), logged via TrialLedger before the run. Descriptive-only this batch; display-only forever until a separate promotion prereg (which would carry `derived_from_surface: f_hz1`).
- **Floors:** n≥300 fires and ≥25 episode clusters per arm; printed before stats; DEFER branch pre-committed.
- **Output:** summary JSON (committed, vintage-stamped) + `research/hazard/F_HZ1_REPORT.md` (plain-language, "In plain English" box, nulls printed). NO bottom-sensor column changes, NO composite hazard score, NO site surface this wave (RUL-N2).
- **Run gate:** `dilution_events.parquet` exists with ≥1 successful sweep. If absent at build time, the PR ships prereg + harness + tests with the run gated; the run + report land as a follow-up commit/PR once the nightly materializes it.

---

## §6. Scope fences

- No new lobes, no meta-models, no fused/composite scores, no sizing changes, no board chips.
- No re-tests of frozen or nulled families (RUL-N9). No supportive sponsorship vocabulary (RUL-N3).
- No public write endpoints; no touching #1664's owned surfaces (§3).
- No LLM-originated signals anywhere; de-escalation-only consumption shape for anything downstream.
- Nightly render band untouched: PR-1 runs ops-lane; PR-2 runs Mac-local off-render.

## §7. Corrections ledger — Codex memo (printed per house law)

1. **STALE:** "action_ledger.jsonl does not exist yet" → shipped #1550, gitignored-by-design (§0.4). The memo's DQ-1 is built.
2. **BLIND SPOT:** the exclusion list omits the long-hold thesis program (chartered 2026-07-05, W0-W2 + LT-1..4 shipped) — lobe #4 re-proposes an operating program.
3. **WRONG SIGN:** 13F/ownership as positive sponsorship contradicts `esx_insider_sponsor` null (#1566), F4 252d null, and the smart_money contrarian ruling.
4. **ALREADY ANSWERED:** F-HZ-2 = frozen A2 G1-Retest; F-HZ-3's forward-horizon mechanism already null (esx_ev_blackout mae21 p=0.653).
5. **NOT A DEFECT:** trigger_tier=136 / entry_quality_band=57 are live-state counts, not coverage holes (§0.5).
6. **SELF-CONTRADICTION:** the operating-stack decision chain (line 570) vs "do not combine into a master score" (warning #1) — the chain is struck (RUL-N2).
7. **UNACKNOWLEDGED CAP:** five lobe charters vs the docket's two-lobe concurrency cap — never mentioned in the memo.
8. **RIGHT AND KEPT:** consequence framing; sponsorship coverage embarrassment (real, un-docketed until today); abstention as under-graded counterfactual; opportunity-cost symmetry; "unavailable as first-class state"; red-team warnings 1-7 (adopted — they match standing rulings).

## §8. Status log

- 2026-07-06: 6-lane census + 5 Opus reviews + synthesis complete; #1664 collision detected mid-adjudication and reconciled (§3); program ratified; PR-1/PR-2 dispatched (Sonnet build, Opus review, Fable merge).
