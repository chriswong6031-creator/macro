# Basket & Verdict Integrity (BVI) — grandmaster plan (W0)

**Chartered:** 2026-07-16, from the operator-triggered basket/front-board audit (this doc's §0 is the postmortem).
**Goal:** the theme/basket surfaces must (a) stop churning lifecycle labels around stateless thresholds, (b) claim only what each signal is calibrated to claim ("pullback-risk timer" ≠ "topping out"), (c) speak at the right altitude in high-dispersion tapes (basket verdict + within-basket leaders are different reads), (d) stop marking healthy leaders "Extended — don't chase" off cycle-age alone, and (e) reconcile the front board's risk axis with the leadership/rotation axis the repo already measures. Display-tier ships freely; authority changes only through pre-registered gates (house law).

Panel provenance: 5 independent design proposals × 3 judge lenses (house-law, operator-value, engineering-realism), 2026-07-16. Verified-fact citations below were re-derived by adversarial reviewers, not trusted from the audit lanes.

---

## 0. Postmortem — the 2026-07-14 "Big Pharma is topping out" miss (and what it revealed)

**What happened.** big_pharma flipped dominant→fading in the 07-15 run (alert stamped `ts=2026-07-14`, the trailing close date), emitting "⚠️ Big Pharma is topping out … Recommendation now TRIM" — right as the operator watched pharma leaders rip on 07-15/16. The audit found the inputs were *real* (8/10 members negative 07-08→14, XLV −2.47% 5d, JNJ −6.2% 5d, VRTX −9.9% off its 07-06 peak) but the *claim, altitude, timing and churn* were all wrong:

- **Churn:** `_label()` (engine/theme_scoring.py) is stateless with a hard `score>=62` dominant cutoff — big_pharma round-tripped dominant→neutral→dominant→fading in 4 sessions (git history of data/themes/state.json). 17 "topping out" alerts fired in 4 weeks across the US universe; cybersecurity was flagged topping 07-13 and was the #1 dominant theme 07-16; regional_banks "topped" twice and is dominant now.
- **Overclaim:** the FADING read is calibrated as a forward-*drawdown-risk* timer (fwd_dd_21d ≈ −3.7pp, alert precision_oos 0.142), not a directional top call — but the headline said "topping out". (Copy fixed 2026-07-16, same-day PR as this charter.)
- **Wrong altitude:** intra-basket 10-session spread was 10.5pp (REGN +6.6% vs VRTX −4.0%). One basket-level verdict cannot serve a split basket. `engine/basket_member_context.py` already computed the leader/beyond cohort discrimination ("Leader · time the entry") and no user surface consumed it.
- **Leaders suppressed:** `engine/cycles.py:1041` marks any name late in its daily cycle (dc_day≥28) and above MA10 as TOP WATCH — no RSI/stretch/RS witness (the sibling mid-cycle branch *does* require rsi14>70) — which sets `cycle_blocked`, caps the entry axis, neutralizes the theme spotlight, and renders "Extended — don't chase" on exactly the strongest defensive leaders (GILD conviction 4 at +5.95% 20d).
- **Front-board contradiction:** market_state read 79 RISK_ON ("trend-following and adding on strength is supported") while the repo's own display artifacts said: DSPX 98th pctile, COR1M ~0th pctile (index vol suppressed because stocks aren't co-moving), growth-scare "defensive rotation" at watch, sector_bias favor XLV/XLP/XLU avoid XLE/XLY, QQQ −3.7% off ATH vs SPY −0.4%, 23/46 themes deteriorating. None of it reached the hero. (Display chip shipped 2026-07-16.)
- **No accountability loop:** none of the 17 topping alerts were forward-graded; nothing would ever have surfaced the miss.
- **Parity:** all five regions (US/CN/HK/intl/canada) share the same theme_alerts/theme_scoring pipeline and the same detail template; CN showed the same churn class on the emerging side (cn_brokers 4 theme_emerging events in 5 days). HK additionally drops 6/13 hk_banks members from act-now boards for silently missing conviction data.

**Shipped same-day (display-tier, PR of 2026-07-16):** anatomy-bar CSS theme fix (all 5 regions); honest topping-alert copy (risk-timer claim + as-of close disclosure + "leaders inside the theme can keep running", EN/ZH); theme_emerging debounce (constructive side, mirrors ratified reco debounce); hero leadership-context chip; member-row "within-theme leader" chip + conviction-mandate disclosure.

## 1. Rulings (BVI-R1..R10)

- **BVI-R1 — risk-direction immediacy is untouchable.** theme_topping/theme_deteriorating/reco downgrades fire the session they occur; nothing in BVI may buffer, dwell, or debounce them (ratified drawdown-control channel). Every churn fix operates on the CONSTRUCTIVE/continuation side only, with an invariant test proving risk transitions bit-identical.
- **BVI-R2 — claims must match calibration tier.** A headline may only carry directional vocabulary ("topping", "breakdown") if the underlying key is calibrated directional; risk-timer keys speak risk-timer language ("elevated pullback risk"). Enforced by the W6 claim-calibration guard.
- **BVI-R3 — the shim law (graded history is sacred).** Any re-labeling of a calibrated key that feeds pick-lab books, standout gates, or board ledgers ships behind a fold-back shim: the NEW key maps back to the OLD key at every grade/gate boundary (byte-identical grade rows + board eligibility as acceptance) until the swap passes its pre-registered gauntlet. Grades are keep-first-permanent; first pick-lab maturation ~2026-07-21 — the shim must land before any retag.
- **BVI-R4 (inherited kills honored).** No rotation × cycle-position entry-confluence score (DO_NOT_REBUILD §rotation-confluence, DON'T-TEST). No rs-based member-dispersion gates (R-4 zero-sum tautology) — leader/cohort context gates on ext_rel-vs-cohort-median (basket_member_context's deliberate non-rs construction), never rs_rank. Dispersion may be displayed, never gate (MLC-R4). A scored per-name "trend-leadership conviction axis" is NOT chartered — only the display tag ships; anyone re-proposing the axis must first vacate the standing kills at the registry.
- **BVI-R5 — dispersion legs for the front board are ABSOLUTE co-movement constructs** (COR1M/DSPX/index-vs-avg-constituent vol gap), never within-basket relative strength; any calibration is era-split (DT-R16; era-pooled inference forbidden).
- **BVI-R6 — accountability is not optional.** Every lifecycle-label transition alert gets a PIT forward-log row at emit and a matured grade at its calibrated horizon; the scorecard is pure observation (no LLM, no origination) and the receipt shown to users discloses proxy-backtest vs live-sample provenance explicitly ("backtested on 27y sector history; live sample still accruing, n=Y").
- **BVI-R7 — altitude honesty.** When a basket's members split beyond a disclosed dispersion threshold, the glance verdict must say so in plain words (named leader/roller cohorts), not average silently (mirrors MLC-R7 disagreement-disclosure).
- **BVI-R8 — consume, don't rebuild.** BVI consumes VSB organs (cor/vol collectors, vol-weather, breadth split), MLC stance-matrix/leadership reads, basket_member_context, risk_radar/market_state_audit forward-ledger patterns, calibrate_baskets rulers. New pair/ratio math routes through existing registries.
- **BVI-R9 — off the render path.** All new grading/monitor/report lanes run nightly-tail or scheduled workflows, never inside the ~67-min render budget.
- **BVI-R10 — glance tier per DESIGN_DOCTRINE.** Plain-word state + stance under hard word budgets; internal keys (LATE_HEALTHY, ext_rel, DSPX) never appear at glance tier; bilingual EN/ZH; CJK via Write/Edit tools only; no translated `title=`.

## 2. Boundary map

| Program | Owns | BVI's relationship |
|---|---|---|
| MLC (#2576) | megacap tiles, stance matrix, ACT-NOW demotion, rollover_risk texture extension (W4) | BVI basket-verdict disclosures ride the stance-matrix artifact; BVI does NOT extend rollover_risk (MLC W4 owns it) |
| VSB (W0-W6 built) | cboe cor/vol collectors, vol-weather, corr floor-break, AI-vs-rest breadth | BVI W5 consumes as candidate legs; promotion attempts live HERE (BVI), construction stays VSB's |
| RIC (#2527) | event-window engines, radar episode atlas | BVI's alert scorecard is lifecycle-label-scoped; radar legs stay RIC/VSB |
| pick-lab (US/CN) | keep-first graded books, candidates gates | BVI-R3 shim protects it; the LATE_HEALTHY authority swap is a pick-lab-affecting prereg (§4) |
| theme desk (theme_scoring/theme_alerts) | labels, recos, alerts | BVI's primary patient |
| market_state + risk_radar | front-board score/verdict, scares, forward audit | BVI W5 display chip consumes; authority leg only via §4 prereg; market_state_audit's DEFENSE-only ruler (PRIMARY_DD=0.05, RISK_OFF-only) is the wrong ruler for offense/defense — W5's log gets its own return-graded, era-split ruler |

## 3. Waves

### W1 — Entry-truth: LATE_HEALTHY split behind the shim (display + shim; the "leaders suppressed" fix)
- Split the age-only TOP WATCH branch (engine/cycles.py:1041 `elif late and cyc["above_ma10"]`) into a NEW internal key **LATE_HEALTHY** unless a genuine-overbought witness is present (rsi14>70 OR pct_vs_200dma ≥ _STRETCH_WARN OR parabolic ext_z grade OR member_context band=='beyond') — witnesses already computed per-name; the sibling mid-cycle branch already gates on rsi14>70, so this restores symmetry.
- **Fold-back shim per BVI-R3:** at every grade/gate boundary (pick_lab candidates hard-block set, standout signal_gate, board_ledger cycle_state stamp) LATE_HEALTHY maps back to TOP WATCH. Acceptance: byte-identical pick-lab candidate books, grade rows and board eligibility on a replay night; no gate_ver bump.
- Verdict copy: a strong-selection LATE_HEALTHY name reads "Leader · late in cycle — time the entry on a pullback" instead of "Extended — don't chase" (verdict strings live in engine/stock_score.py ~1141-1145, NOT grade.py — panel-verified location).
- Display chip on the per-name card from member_context band (leader/beyond/catch_up/laggard) — single wording source shared with the basket page chip shipped 07-16.

### W2 — Label dwell: asymmetric hysteresis on the DOMINANT side (display-shape; operator-ratify before build)
- `_label()` gains prior-label awareness through the SAME persisted state theme_alerts already keeps (no second store): (a) promotion buffer — DOMINANT requires its predicate to hold N_PROMOTE=2 consecutive sessions; (b) demotion cushion — DOMINANT does not drop to NEUTRAL until score < 58 (4-pt band) or any risk branch fires.
- **Invariant (BVI-R1): every input that produced fading/deteriorating pre-change still produces it the same session — unit-tested bit-for-bit.** DOMINANT is calibration-graded descriptive (rank-IC ~0), so dwell changes no calibrated authority; still, because it alters a label-producing function, it ships only after operator ratification of this wave, with a replay report (big_pharma/cybersecurity/regional_banks tapes: round-trips ≤1 per basket per 4wk; all historical risk alerts fire on identical sessions).
- Same-day: label-churn monitor (flips per theme per trailing 28 sessions, from the alerts ledger) → ops-alert lane on threshold breach + a small "label stability: steady/choppy" glance chip.

### W3 — Alert accountability: theme-label forward-ledger + scorecard (display; retires "unscored alerts")
- New engine/theme_alert_audit.py cloning the market_state_audit/risk_radar_scorecard pattern: PIT row {asof, basket, region, type, from, to} keep-first at emit for theme_topping/theme_deteriorating (and theme_emerging for symmetry); matured grading at h21 against the basket's own realized forward drawdown using calibrate_baskets' DD_RISK constant (same units as the proxy backtest); scorecard = pure observation, per-type live precision + n_graded + lift; nightly-tail only.
- User-facing receipt on the theme panel per BVI-R6 dual-source rule: "this read has flagged real pullbacks X% of the time at 21d" with explicit proxy-vs-live provenance and thin-n honesty.

### W4 — Altitude: split-basket disclosure (display)
- Dispersion detector per basket from member_context aggregates (n_leaders/n_beyond/median_ext + 10-session member return spread — plain arithmetic, already-computed inputs). Above a disclosed threshold, the basket glance verdict becomes two lines: basket stance + named cohorts ("split basket: JNJ/VRTX rolling — REGN/MCK/GILD leading"), under a hard word budget; hover carries the numbers. Riding the MLC stance-matrix artifact where present (BVI-R8), one wording source EN/ZH.
- Flip-fragility disclosure: promote the existing `_flip_distance` meter to a glance-adjacent "on the fence" hint when a label sits within its wobble band.

### W5 — Front board: leadership stance chip now, two-axis study later (display now; authority = §4 gauntlet)
- Display (now): engine/leadership_stance.py — pure reader blending BUILT artifacts (dispersion state, breadth_split AI-vs-rest, index_leadership drivers, COR1M/DSPX pctiles) into {OFFENSE/BALANCED/DEFENSE} + plain-word "so what" line; MIXED-verdict enrichment explains the SPECIFIC divergence ("index calm but stocks not co-moving — narrow tape"); the 07-16 hero chip is the seed of this surface. `is_display_only` stamped; degrade-never-raise.
- Authority (later, only through §4): its own forward-log with a RETURN-graded, era-split ruler (offense/defense is not gradeable on market_state_audit's DEFENSE-only drawdown ruler); honest end-state includes "nothing promotes — stance stays confluence context forever."

### W6 — Standing guards (display/CI; recurrence prevention)
- **Coverage tripwire:** scripts/check_coverage_completeness.py (sibling of surface_freshness) asserting rendered/roster member ratio per board — would have caught HK 6/13 the night it happened. Warn-only, additive.
- **Hardcoded-color linter:** template scan for literal hex/rgb colors on themed surfaces without CSS-var indirection (the .ftr-leg-bar class of bug), grandfathered legacy list that only shrinks.
- **Claim-calibration rule (BVI-R2):** extend check_reliability_contract.py — directional headline vocabulary requires a direction-calibrated key.
- (Deferred, optional) Playwright light-mode screenshot lane off the render path — only if the linter proves insufficient; baseline-rot risk noted.

### W7 — HK/CN parity closure
- HK conviction coverage (6/13 hk_banks) — chip already filed 07-16; fix = coverage or printed null ("conviction data unavailable — not eligible for ranking"), never silent drop; then W6's tripwire holds the line. CN emerging-churn is covered by the 07-16 debounce; W2 dwell + W3 ledger apply to all five regions by construction (shared pipeline).

## 4. Pre-registration requirements (authority tier)

1. **LATE_HEALTHY authority swap** (replacing TOP WATCH at pick-lab hard-block / standout signal_gate / board_ledger): frozen dated prereg BEFORE the swap; registered horizon_role ruler; shadow period with the W1 shim active; acceptance = pre-declared improvement in graded entry outcomes without degrading the drawdown-control channel; explicit non-collision statement vs the rotation-confluence and R-4 kills (the de-escalation construction is ext_rel/absolute-stretch based, not rs). No gate_ver bump until pass.
2. **Any front-board score/verdict change** (leadership leg or 2×2 verdict grid): frozen legs (no post-hoc swaps), h10/h21 only, era-split mandatory, lift gate mirroring VSB §6 (≥1.20 at pre-registered threshold) plus an orthogonality gate vs the existing breadth leg (the likeliest honest null: leadership restates breadth — then it stays display forever).
3. **W2 dwell** is not a promotion (descriptive label shape) but requires operator ratification + the replay report before build, per the house-law judge's hazard flag.

## 5. Fenced / not chartered

- Scored trend-leadership conviction axis — collides with standing kills (BVI-R4); display tag only.
- Debouncing/dwelling any risk-direction transition — forbidden (BVI-R1).
- Cap-weighted basket indices — equal-weight is the deliberate, disclosed design; concentration is a *disclosure* concern only (and the census's cap-weight "flaw" findings were refuted).
- Re-dating alert `ts` semantics — the id/dedup contract depends on it; as-of disclosure rides in copy instead (shipped 07-16).

## 6. Come-backs

- After next nightly: confirm anatomy bars themed on all 5 regions; hero chip renders with live sector_bias; member-row chips present where member_context exists; emerging-debounce state key appears in state.json without churn alerts.
- ~2026-07-21 (pick-lab first maturation): W1 shim MUST be merged before any cycles.py retag; verify byte-identical books on a replay night.
- After W3's first 20 graded rows: publish the first live precision receipt; compare against the 0.142 proxy figure.
- W2 replay report → operator ratification gate.
