# Entry-Stack Expansion — Amendment 2: Non-Technical Bottom Sponsorship (by Fable)

**Status:** RATIFIED 2026-07-05. Amends `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md` (#1356) and rides on Amendment 1 (RUL-13..17, same day).
**Adjudicates:** `research/nontech_bottom/NON_TECH_DURABLE_BOTTOM_SIGNALS_FOR_FABLE.md` (Codex, 2026-07-05, rescued into repo with this PR). Verdict: **ADOPTED AS AMENDED** — the economic thesis (sponsorship + solvency repair + event hygiene as confirmation of an existing technical fire) is correct and orthogonal; the paper's program identity, horizons, promotion bars, NW engine design, and build queue are all superseded below.
**Inventory:** `research/nontech_bottom/W0_INVENTORY.md` (12-lane census, workflow wf_ec6648eb, 2026-07-05). Red-team: 3 opus lenses (doctrine/collision, stats design, data feasibility) + one opus pre-merge collision/legality pass — SHIP-WITH-FIXES, all findings integrated, marked ⟦RV⟧.
**New rulings:** RUL-18 through RUL-26. Prior rulings unchanged.

---

## A. What the census established (one paragraph per layer)

The paper's raw materials are far more built than it assumed, and far less connected than it hoped. **Sponsor layer:** a strict-PIT per-transaction SEC Form 4 panel exists (2.31M rows, 16,834 tickers, 2006q1–2026q1, filing_date-keyed, `collectors/sec_insider.py`) with a completed factor program whose binding verdict is "orthogonal confirmer, LONG-ONLY, never standalone" (`research/INSIDER_FACTOR.md` §6); a daily 13D/13G sweep + activist regime classifier is live and display-only (SCORED=False) with a monthly event-study gate that has not yet reached `_MIN_EVENTS=40`; buyback *authorizations* are already keyword-classified from 8-Ks (`special_situations.py` Capital Returns), while buyback *actuals* sit 90%-built in `scripts/backfill_edgar_quarterly.py` → `statements_quarterly.parquet` with zero downstream readers. **Repair layer:** SUE has a full PIT panel but a binding deep-history null (IC 0.038→0.0006, HAC t 0.06 — demoted to display); revisions/guidance feeds exist with accrual caveats; Piotroski/Altman/Sloan exist display-only, with a hostile CN prior (`cn_reversal_sleeve._FORBIDDEN_GATE_FIELDS`: quality gating flipped a reversal edge negative). **Event layer:** the earnings-blackout family `esx_ev_blackout` landed its study the same afternoon as this census (#1432, `research/entry_stack/W1_SEV_REPORT.md`): hygiene evidence PRESENT — vetoed fires degrade stop5 by +8.7pp (CI [+7.9, +9.9] excluding 0) at 6.0% veto volume; reviewer sign-off and W1.5 wiring belong to the in-flight ESX lane. Lockups have a display calendar with a display-only phase0 verdict; forward dilution/debt/regulatory calendars do not exist. **Weather layer:** every F5 stress series is already collected and consumed by conditions.py/risk_radar (OFR FSI ruled *coincident, display-only*; `credit_oas_roc` is a calibrated Tier-A *de-risk* leg — the repo carries an internal contradiction on its 2020+ vitality, immaterial here since the bottom-side **turn** is what's genuinely absent); NAAIM (1,043 wk) and COT (1997+) are studied confirmers, AAII is bot-walled at 22 rows, FINRA SI has one vintage (PIT accrual armed but empty), ICI/margin have no collectors. **Alt-data:** five of six F8 forms ride live Quiver channels, but stores are 2 weeks–5 months deep — zero historical fires. **Wiring:** none of the above emits into Neural Web; `bottom_sensors.py` (Amendment 1 lane B0) is being built in-flight as of ratification (open PRs #1436/#1437); the fire tape (deep 38,250 / baskets 113,542 fires) and harness are frozen and ready — RUL-14's zone_held_21/stop_vol_21 landed with the #1408→#1432 chain, but `mae21` is still absent from EFFECT_OUTCOMES (fwd_mdd_21 computed, never surfaced) and NC-2's `eq_band` remains DEFERRED.

The user's framing is confirmed verbatim: **the signals exist; the fire-anchored conditioning layer and the NW conversion layer do not.** That layer — not new collectors — is this amendment.

---

## B. Rulings

### RUL-18 — Identity: this is an ESX amendment, not a program

Per RUL-17.1, all non-technical bottom inference rides inside Entry-Stack Expansion: families are `esx_*` keys in the trial ledger, studies run on the frozen fire tape under the frozen grader (RUL-9), reports live under `research/entry_stack/` with `research/nontech_bottom/` for program docs. The paper's §6–§8 (own program, own wave plan, own feature parquet, eight NW engines) are superseded. The only separate-identity artifacts are **data-plane builds** (per-fire conditioning panels, the statements_quarterly wiring, accrual-starter collectors) — separate PRs, same program owner. ⟦RV⟧ No parallel `nontech_bottom_features.parquet` fire-set: all study features join the existing tape via the `run_w1_sts.py` extra_columns pattern (RUL-11: no fire testifies twice).

### RUL-19 — Two-layer Neural Web collapse

The paper's eight engines collapse into two layers:
- **Display layer:** bound descriptive fields on the single RUL-15 `bottom_sensors` envelope — `sponsor_present`, `repair_present`, `event_clear`, `macro_relief`, `support_legs` (ordinal 0–3+), plus the existing reserved `sponsorship_state` and `EVENT_BLACKOUT` overlay. Bind-first law applies to **Amendment-2 field additions**: every field this amendment adds binds an existing emitted artifact; no new recomputation on the render path. ⟦RV⟧ `sponsorship_state` itself is the Amendment-1 §C3-sanctioned computed descriptor (frozen vel-sign × accel-sign off `panel_s.parquet`, owned by the in-flight B0-3/B2 lane, #1437) — it is not an Amendment-2 field and its computation is not a bind-law violation. These fields land **when lane B0's envelope merges**; they do not create a second envelope.
- **Inference layer:** pre-registered `esx_*` stratum families (§C) in the existing trial ledger. Only families with a filed phase0 verdict may emit `SpinePrediction` rows (display-first, `size_binding=false`), and **every** bottom-context row carries `event_key = "{TICKER}:{date}:bottom_context"` so co-firing sensors collapse to ONE observation per fire×horizon cell (else n_eff inflates ~8×). Backfill rows carry `version: backfill-v1` (RUL-8) and are excluded from FDR/confluence evidence where their fire-set already testified (RUL-11).

No engine named `bottom_*` is registered in `config/synapse.yml`; the `bottom_sponsor`/`bottom_macro_release` names are retired to avoid collision with `esx_sponsorship` (RUL-16, a different construct: Oracle sector velocity).

### RUL-20 — Horizon routing (application of RUL-13)

Entry-verdict claims for every family run at **21d primary** (stop5 + mae21 co-primary; zone_held_21/stop_vol_21 per RUL-14, already wired on main; clean8_21 supporting). The paper's 63/126d framings route as follows: F3 `quality_floor` folds into the existing `esx_ql_overlay` holdability lane (budget 12, already declared) and may never gate an entry — the CN forbidden-gate finding rides as its hostile prior; F7 ownership and F8 real-activity claims are holdability/display until live accrual matures; clean-liftoff/dead-money at 63/126d are holdability-lane secondaries, never promotion gates. Insider Phase-0/1 (63d primary) stand as grandfathered prior evidence; every NEW conditional study is 21d-primary.

### RUL-21 — One reconciled bar set (paper §5.3 deleted)

House floor wins wherever the two differ; per RUL-7 bars may be raised, never lowered:
- **HYGIENE VETO:** vetoed-set FE degradation on stop5 (primary) AND mae21 (co-primary) ≥2pp, block-bootstrap 95% CI excluding 0; vetoed volume ≤10% of fires; per-row freshness fail-open (F1 rule). Only S-EV may target a hard gate (RUL-4) — every Amendment-2 hygiene candidate ceilings at chip/context. ⟦RV⟧ This bar binds **Amendment-2 families only**; the shipped W1-SEV study is grandfathered under the masterplan §5 bar (stop5 OR mae63) per RUL-13.4 and is not retroactively re-scoped.
- **CONFIRMER CHIP:** stop5 FE-coef ≥2pp, CI excluding 0, BH q≤0.10 within the declared family, sign-stable ≥3/4 eras, n≥400 date-deduped treatment fires, beats NC-1 AND NC-2, MFE/|MAE| conjunctive. Clean-liftoff/dead-money ≥3pp (the paper's bar) is a holdability descriptor only.
- **KERNEL LANE:** n_eff ≥12 per marginal cell; quarterly FDR batch (2026-10 first read); §7.6 coarse-cell fallback.
- **BOARD/RANK:** live-ledger maturity + shrunken posterior CI support; nothing before the FDR clock.

BH family = the declared per-family budget, not the union across families.

### RUL-22 — Power triage (binding; drives the tranche plan)

| Tier | Families / forms | Basis | Disposition |
|---|---|---|---|
| **A — tape-armable now** | `esx_insider_sponsor`; (`esx_ev_blackout` — in flight, consumed) | 2.31M insider rows 2006+ × baskets tape 2014+ (113,542 fires) + deep 2006–2026 slice | Full phase0 in T1; regime cells where n allows |
| **B — coarse-cell only** | `esx_macro_release`, `esx_pos_reset` | market-level; ~400–700 stress-turn fires 2003+; NAAIM/COT weekly | Phase0 at engine×horizon only, R1-M estimator (RUL-24), conditioning ceiling |
| **C — live-accrual only** | activist 13D (<40 priced events), buyback_actual (store off-pipeline, no history join), all F8 Quiver forms (stores 2wk–5mo), F7 13F forms (6q depth), revision_turn (vintage accrual law) | zero or sub-floor historical fires | NO phase0 now; shadow display rows at most; come-back dates in §E |
| **CUT / indefinite** | short_interest forms (PIT panel 12–24mo away), AAII (bot-wall, 22 rows), `developer_activity` (17+9 tickers — display-forever), F9 narrative (no multi-year ticker tone series; EPU/GPR family retired; any future attempt must prove fire-conditioned ticker-level increment over VIX and may not cite the retired NDI), forward dilution/debt/regulatory calendars (data-plane futures, separate memo) | — | Graveyard/backlog with re-open conditions |

### RUL-23 — Per-feed known-date law (mandatory, machine-checked)

Every signal form carries a `(source_event_date, known_date, pit_basis)` triple in spine meta and `feature_meta.json`; a study lacking it is invalid per RUL-2. Frozen table:

| Feed | known_date | Trap pinned |
|---|---|---|
| Insider Form 4 | **filing_date** (windows defined on it) | ≤2-business-day legal trade→file lag |
| SUE / guidance | **8-K Item 2.02 acceptance date** (`earnings_8k_dates.parquet` / guidance_gap plumbing) | synthetic `asof_date` (period_end+60d) is **VOID** as a PIT anchor |
| Buyback authorization | 8-K date (special_situations CAP) | authorization ≠ execution |
| Buyback actual | 10-Q/10-K **filed** date | ~35–45d lag behind the quarter |
| 13F forms | `smart_money.as_of_for_scoring()` (filing date, ~45d lag) | reuse the accessor, never reimplement |
| COT | **Friday publish** (Tuesday as-of) | 3-day lag |
| NAAIM / AAII | Thursday publish + the existing 7-day forward lag convention | weekly self-dating |
| NFCI-family conditioning | **STLFSI4 ALFRED-vintaged only** | NFCI re-revises all history; excluded from vintage by design |

### RUL-24 — R1-M: the market-level estimator variant ⟦Fable addition⟧

A market-level regressor is constant within a date, so the R1 date-FE estimator **absorbs it completely** — Tier-B families cannot legally use R1 as-is. R1-M is pre-registered here: unit = fire; no date FE; mandatory controls in the regression = VIX level, SPY 126d drawdown, market_state/risk_regime state (this operationalizes the paper's own F5 kill rule); SEs episode-clustered (fire-date ±10 bars); block-bootstrap CIs; era table mandatory. ⟦RV⟧ **Shared-source control exclusion:** when a mandatory control shares its underlying source series with the family's treatment definition, that control is DROPPED for that family and the drop pre-registered per definition — conditioning a treatment on a control built from the treatment's own series partials out the estimand (bad-control bias toward null). Concretely: `esx_macro_release` M2 (HY-OAS turn) drops the market_state/risk_regime control (its credit component is `credit_oas_roc` = the same HY-OAS 21d ROC) and retains VIX + SPY drawdown; M1 (FSI turn) analogously drops any FSI-family control component and retains VIX + SPY drawdown + the OAS level. FE-granularity law (RUL-12) applies to the choice R1 vs R1-M: fixed per family at registration, never switched post-hoc. R1-M families ceiling at **regime-conditioning context** — never a ticker-level chip.

### RUL-25 — Anti-fusion + dose-response

Per Signal Commons R3, no fused "positioning/macro permission" score, leg, or tier may be constructed — each F5/F6 ingredient is an independent family. The paper's FULL_SUPPORT conjunction tier is statistically dead (4-way AND of sparse sensors ⇒ single-digit N; S7 triple-lock precedent: −11.7pp, recall amputation) and is **replaced as an inference target** by `esx_support_dose`: ordinal `n_support_legs ∈ {0,1,2,3+}` tested for monotone stop5/mae21 improvement, runnable only after ≥2 leg families have filed verdicts. The categorical tiers (NONE/…/VETOED) survive as **display-only** envelope labels (RUL-15 descriptive law; Amendment 1 §B adopted the taxonomy for display).

### RUL-26 — Trial-budget amendment (RUL-7 ceiling change, logged)

`esx_sponsorship` (8, ratified in RUL-16) is added to `FAMILY_BUDGETS` (census: absent). New declared families below raise the program ceiling **115 → 165**:

| Family | Budget | Itemization (thresholds frozen at registration PR) |
|---|---|---|
| `esx_sponsorship` | 8 | RUL-16 (unchanged; codified into harness in T0) |
| `esx_insider_sponsor` | 12 | 3 frozen forms (I1 cluster_after_washout: ≥2 distinct open-market buyers in 45td post ≥20% drawdown-from-126d-high, filing_date windows, ≥3-buyer sensitivity counted; I2 cluster_near_fire: cluster within −20..+15td of fire; I3 net_usd_mcap\|SN trailing percentile ≥80 — the FDR-survivor construction, **not** the negative-IC opportunistic filter) × 2 panels × 2 contrasts |
| `esx_fund_repair` | 12 | 3 forms (SUE z≥+1 at last 2.02 date ≤63td pre-fire; SUE less-bad decile→median repair; revision_turn — registered but Tier-C blocked on vintage accrual) × 2 panels × 2 contrasts; hostile priors (SUE deep-PIT null) cited in-report |
| `esx_macro_release` | 8 | 2 turn-defs (FSI pctile≥80 & 15d momentum down; HY-OAS 21d ROC turning negative from ≥80th-pctile level — the inverse of the validated de-risk leg) × 2 panels × 2 contrasts; R1-M |
| `esx_pos_reset` | 8 | 2 ingredients (NAAIM ≤20th pctile then rising; COT ES+NDX spec net ≤20th pctile then rising) × 2 panels × 2 contrasts; ⟦RV⟧ frozen: pctile lookback = trailing 3y (156 weekly obs), "rising" = latest publish > publish 2 weeks prior, both publish-lagged per RUL-23; R1-M; no claim against the existing SPY-overlay confirmer verdicts |
| `esx_support_dose` | 2 | 1 ordinal monotonicity test × 2 panels; unlocked after ≥2 leg verdicts |
| **New total** | **165** | BH per family; program summary printed per report |

---

## C. Harness prerequisites (gate W2-class studies; the #1408 chain merged 2026-07-05 — edits are unblocked)

1. **mae21 into `EFFECT_OUTCOMES`** (post-#1432 check: zone_held_21/stop_vol_21 and clean8_21-as-state_rot are already in; `fwd_mdd_21` is computed in grade_fires but never surfaced as an effect outcome — mae21 is the one missing RUL-13 co-primary). No Amendment-2 study reads a verdict without it.
2. **`computable_mask` parameter** ⟦RV⟧ for r1_estimate/grade_fires: both arms restricted to fires where the sensor is *in principle computable* (ticker in feed universe, PIT anchor available, window observable). Treatment = fired; control = computable-but-silent; out-of-mask fires dropped, not zero-coded. Mask definition per family in feature_meta.json. This is the S7 same-computable-subset lesson made mechanical — without it every sparse family's FE contrast conflates "absent" with "not applicable".
3. **eq_band lookup for NC-2** (currently DEFERRED; r1_estimate raises without it). Until it lands, Amendment-2 families may run phase0 and ship shadow/display but **no CHIP promotion** (NC-2 unbeatable-because-uncomputable).
4. **Insider flat-file dead-path fix** in the same PR as the I-panel build: `engine/equity_factors.py` silently falls through to the single-quarter aggregate (cluster=False) when gitignored `insider_panel.parquet` is absent — a phase0 on a fresh worktree would measure the degraded fallback.

## D. Tranche plan (replaces paper §7–§8)

- **T0 — unblock (≤1 PR):** FAMILY_BUDGETS additions (esx_sponsorship + §B RUL-26 table) + this doc + W0 inventory + paper rescue. W1-SEV is **consumed, never rebuilt** — its runner belongs to the in-flight ESX W1 lane.
- **T1 — conditioning layer on existing feeds (off-path, ~3–4 PRs):** (a) per-fire **insider context panel** builder (I1/I2/I3 columns via extra_columns; dead-path fix; off-path script); (b) per-fire **macro-conditioning join** (VIX, SPY drawdown, market_state/risk_regime, STLFSI4-vintage, OFR-FSI pctile + the two frozen turn flags) — also the prerequisite that makes the F5 kill-rule testable at all; (c) harness prerequisites §C (unblocked — #1408 chain merged); (d) **studies:** esx_insider_sponsor phase0 (Tier A), then esx_macro_release/esx_pos_reset (R1-M, Tier B). Every study prints nulls, recall, era tables, survivor stamps.
- **T2 — the one cheap data unlock (~1–2 PRs):** wire `statements_quarterly.parquet` into nightly collect (≤8 req/s), emit `repurchases_trailing_q/mcap` + the balance-sheet veto (leverage/cash/maturities from the same store — a buyback under balance-sheet stress is not support); `buyback_authorization_after_washout` as a drawdown-filtered view of special_situations CAP (no new parser). Registers no family until history joins the tape; shadow accrual first.
- **T3 — shadow accrual (display-only):** washout-conditional join engine over existing Quiver channels + `smart_money` forms (~config rows on one shared join layer); envelope fields per RUL-19 ride lane B0 when it builds; optional accrual-starter collectors (ICI weekly, FINRA margin monthly) whose only job is to start the PIT clock — no display, no study.
- **Come-back dates:** activist gate re-check when `validate_activist_ownership` reaches _MIN_EVENTS=40 (~late-2026); F8 phase0 when stores hold ≥2y or a `/beta/bulk/` backfill lands; short-interest when `short_interest_history.parquet` holds ≥24 vintages; revision_turn per the 1-yr vintage law; kernel lanes at the 2026-10 FDR batch.

## E. Coordination, compute, non-goals

**Coordination:** in-flight ESX W1 (#1408 chain, S-EV/S-TS) untouched — harness edits queue behind it; lane B0 owns the envelope build; #1302 owns RS-repair fields (`rs_repair_state` stays `unavailable`); Oracle artifacts consumed read-only (B2); provenance sidecar needs a new `_row` builder + qual_ladder SHADOW entries before any new display field ⟦RV⟧. **Compute:** all phase0 studies, PIT panels, and fire-joins are off-path `scripts/research/`; heavy per-ticker panels go to R2 (r2-data-plane law); the only on-path artifact is the envelope bind (≤+30s, benchmarked, RUL-15); new stores git-added + sentinel staging list in the same PR. **Non-goals:** no master score; no fused positioning/permission leg; no new oscillators; no HK/CA (every US bottom mechanism tested there has failed or inverted); no options lane; no LLM-originated signals (extract/classify/cite/de-escalate only, quote-span-verified); no news-tone collector under this amendment (separate memo if wanted); no Committee View surface before the QA surface accrues.

## F. Addendum 1 — T1 verdicts + T2/T3 re-adjudication (Fable, 2026-07-06; RUL-27..29)

**T1 executed and verdicted in full** (#1454 harness, #1478 insider panels v1.2, #1496 macro/positioning panel v1.1, #1566 esx_insider_sponsor, #1599 esx_macro_release + esx_pos_reset): the paper's entry-time thesis is **3-for-3 refuted or null at 21d** — insider sponsorship (adversity attributed to the washout state by the I1w reserve contrast; cluster marginal = tight null), macro stress release (NULL 8/8 incl. the within-elevated contrast), positioning reset (P1 null; P2 COT-reset mildly ADVERSE, +3.2pp stop5, q=0.096, 4/4 baskets eras). Surviving entry-time value: S-EV event hygiene (ESX lane, +8.7pp confirmed). `esx_support_dose` stays LOCKED (zero qualifying legs). Long-hold's F4 (`long_hold.insider_sponsor_lh`) Ruler-P adds: insider NULL at 252d display-ruler as well.

### RUL-27 — T2 ceded/deferred

The hold-side buyback substance is **owned by the Long-Hold program's LT-3a** (`engine/capital_allocation.py`: buyback_yield, net_buyback_after_sbc, share_count_reduction_confirmed, debt_funded_buyback_flag; PIT filed-date gates; display-only, horizon_role=hold_thesis) — this amendment BINDS it read-only and builds no parallel artifact. The entry-anchored buyback study and `buyback_authorization_after_washout` are **DEFERRED indefinitely**: they instantiate the same sponsor-at-entry mechanism class the T1 studies just refuted three ways; re-open conditions = a favorable long-hold Ruler-H insider/buyback verdict (~2027-H2) OR live-accrual kernel evidence. Two recommendations FORWARDED to long-hold (theirs to build, not ours): (a) complete the balance-sheet veto beyond the debt-trend flag (leverage/cash/maturity inputs exist in the same store); (b) wire the `backfill_edgar_quarterly.py` refresh into the nightly collect (their reader consumes the parquet nightly but nothing refreshes it).

### RUL-28 — T3 shrunk; evidence-hostile display barred

No washout-conditional join engine is built (Tier-C come-backs stand unchanged). The RUL-19 envelope display fields (`sponsor_present`, `repair_present`, `event_clear`, `macro_relief`, `support_legs`) are **NOT added this wave**: `macro_relief` and any positive positioning field are not built this wave — a supportive-framed descriptor is disallowed until evidence supports it (a relief chip would contradict this program's own filed reports); the remaining fields require a written display-value case citing A2_INSIDER_REPORT.md / A2_MACRO_POS_REPORT.md before any build. Display-first never meant display-despite-evidence.

### RUL-29 — Insider horizon partition (coordination)

Entry ruler (21d) = this program, DONE (null, #1566). 252d hold ruler = `long_hold.insider_sponsor_lh` (F4; their prereg cites RUL-26 and forbids double-counting; Ruler-P null, Ruler-H ~2027-H2). The intermediate 63/126d insider-holdability hypothesis is **not elevated into any ESX budget** — it was adjudication-note language, never an itemized trial; if it earns a future life it enters via a new RUL-7-compliant budget amendment citing long-hold's Ruler-H outcome. No ESX trial slot exists or is reserved for it.

**Program state after Addendum 1:** build phase CLOSED; the program moves to **accrual/consumption mode**. Standing items: consume the W1-SEV wiring when the ESX lane ships it (W1.5); come-backs — activist 13D at _MIN_EVENTS=40 (~late-2026), F8 stores at ≥2y depth, short interest at ≥24 vintages, revision_turn per the vintage law, kernel lanes at the 2026-10 FDR batch, long-hold Ruler-H ~2027-H2. Reserves held: esx_insider_sponsor 2, esx_pos_reset 4, esx_fund_repair 12 (untouched — SUE forms remain runnable if ever re-prioritized), esx_support_dose 2 (locked), esx_sponsorship 8 (B2 lane, Amendment 1's), esx_macro_release 0 (consumed 8/8, exhausted).

*Addendum filed by Fable, 2026-07-06, after the long-hold collision census (Explore agent, same session). One opus review pass before merge.*

---

*Filed by Fable, 2026-07-05. Census: workflow wf_ec6648eb (12 lanes, sonnet). Red-team: 3 opus lenses; blockers/majors integrated ⟦RV⟧. Companion: Codex paper (same-PR rescue), W0_INVENTORY.md.*
