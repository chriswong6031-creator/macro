# Codex Buy-Decision Docket — Two-Memo Adjudication (by Fable)

**Date:** 2026-07-06 · **Adjudicator:** Fable (main loop) · **Method:** 20 census+verify lanes (Sonnet census → Opus adversarial verify, 42 agents; every cited evidence path opened) + 2 completeness critics · **Scope:** two external "Codex" memos proposing a stock-buy decision layer (buy dossiers, role firewall, redundancy map, T2 meta-router, exit/trim, dispersion, liquidity realism, trust-by-family; then 15 "near-term ROI" systems).

**Headline verdict:** ~70% of the combined asks already exist under other names; 2 ideas are forbidden by standing rulings; 2 were killed by studies the memos didn't know about; 1 is data-blocked. The buildable-now core is 6 items of display/join/diff plumbing — no gauntlets required.

---

## 1. Memo-1 verdicts

| Recommendation | Verdict | Key evidence |
|---|---|---|
| Buy Decision Overlay (per-row action + 7 fields) | PARTIAL — ingredients live, JOIN missing | stock_view.py `_action()` 4 verbs live on stock.html; falsifiers[] ≈ why_not; trust_tier ≈ authority_level; us_standouts.json rows carry none of the 7 field names; no `trim-only` verb |
| Role Firewall | LARGELY IMPLEMENTED | Spine role flags + schema-enforced horizon_role + unit-tested bidirectional firewall; context tier can't reach scored surfaces (Article-2 CI hard-fail). Gaps: `is_timing` always False; no exit/trim role tag |
| Alpha Overlap / Redundancy Map | IMPLEMENTED as governance; partially machine | NW_QUANT §3 dup table (FR-2), RF-14 ingest dedup, metabolism.py chokepoint, covariance spine nightly (R-ORTH). research_queue novelty gate registered but artifact absent. Auto-reject-at-registration = forbidden (FR-6) |
| T2 Meta-Router (take/wait/downsize/ignore) | FORBIDDEN (FR-1 + Constitution A7_ORIGINATE) | Shrink-only residue already live in rule form: not_topped_veto, freshness_expired, _risk_veto (stressed-tape chase veto), _ENTRY_SIZE_CAP, earnings_blackout. G-T2X OV3/OV4 were NOT-RUN (data gaps), not killed |
| Exit & Trim Intelligence | SUBSTRATE RICH; per-position absent | EXIT-GRID-1 (49,939 fires) / TRIM-GRID / NET-REPLAY on measurement.html; W6-C hold chip + moat falsifiers live per-name. Blocked: no held-position ledger (RUL-F3.2); L2 lobe blocked by two-lobe cap (RUL-F3.1) |
| Dispersion / Selection-Regime | COMPUTED, EFFECTIVELY INVISIBLE | lean_in/out nightly in covariance spine; dashboard chip hard-disabled (`false and`, since #1672); DISP-GATE-1 DEFER (34.8% basis non-stationarity); T2×dispersion conditioning deferred by RUL-F3.8 |
| Liquidity & Execution Realism | MORE BUILT THAN ASSUMED | liquidity_chip (ADV/tier/days-to-build), Amihud + Corwin-Schultz primitives live, earnings-blackout veto live, cost_bps friction across backtests. Gaps: no S-LQ gate study; no unified passport |
| Trust-by-family + calibrated routing | ACCRUING / FORBIDDEN | by_family WR live (altdata promotion readiness ~2026-08-30); desk by_regime live-but-near-empty; fused routing composite verbatim-rejected (FR-1); NARR-2/3 clocked 2026-10-01 |

## 2. Memo-2 verdicts (15 ideas)

| # | Idea | Verdict |
|---|---|---|
| 1 | No-Buy Shield | FORBIDDEN as fused verdict (Signal Commons R3; FR-1 clock-gates even shrink-only composition past kernel arming 2026-10-01). Residue: display-only reasons panel. Ingredient maturity: freshness_expired LIVE, not_topped LIVE, earnings_blackout LIVE, anti-chase ext_z SHADOW (flip ≥2026-Q4), macro-tape rates-axis-only, DISP-GATE-1 DEFER, S-LQ gate MISSING, reduce-gate LIVE (sector) |
| 2 | Buy Decision Packet | = memo-1 Overlay + freshness + hold.py invalidation + contradiction. Mastermind DecisionPacket NOT reusable (separate repo, allocation-centric) |
| 3 | Freshness / Did-I-Miss-It | PARTIAL — FRESH_TICKS, entry_signal statuses, RAN_LATE, _eq_freshness, entry_glyph (shadow) live but scattered. "Wait for pullback" bucket CONTAMINATED: WAIT-GRID-1 shows waiting does NOT sharpen edge; staleness half-life UNMEASURED |
| 4 | Exit & Trim Cockpit | PARTIAL — thesis-break/crowding/extension live; EMA/trend-decay input missing; unified cockpit wrapper missing; per-position blocked (RUL-F3.2) |
| 5 | Event Landmine | HALF-LIVE — earnings blackout + FOMC gating enforce on board; CPI/NFP partial; FDA/PDUFA + legal + debt-refi ABSENT (F-HZ-1 come-back 2026-07-20). BD-ECON-1 kill scoped to breakdown-event gating only |
| 6 | Contradiction Engine | SUBFIELD of #2 (why_not) — collapse; stock_score §6.3 disagreement table + _RISK_VETO already behave as contradiction detection |
| 7 | Conviction Delta | BEST NET-NEW IDEA — deltas live at lobe/hub/theme/cross-asset levels (daily brief, china hub, alert_triage, allocation_alerts); per-ticker funnel-state diff ABSENT. Deterministic reason-code diff = buildable; LLM narrative leg forbidden |
| 8 | Watchlist Sentinel | PARTIAL — buy-zones + watchlist UI live; server-side Supabase watchlist read + ticker push dispatch ABSENT (path pre-named in catalyst_stock.py) |
| 9 | Portfolio/Theme Overlap | LIVE at 3 levels (reflexivity same-thesis Jaccard/cosine #1401; foresight_enb ENB; cross-asset absorption). Held-vs-candidate = forbidden here (two-organisms law, R-A → Mastermind charter). Named macro-bet labels = rotation_state.py unbuilt |
| 10 | Insider × T2 Sync | KILLED-BY-PRIOR-RULING — the exact confirmer reframe WAS the tested design (esx_insider_sponsor I1w tight NULL +0.5pp CI[−0.8,+1.8]); T2 base null (G-T2X); OV5 "not extended" killed. Re-open: Ruler-H ~2027-H2. Insider data itself live (PIT Form-4 panel + confirmer chips + top_picks tilt) |
| 11 | Revisions/Estimates + Entry Gate | DATA-BLOCKED per-stock (consensus = paid = W6 SKIP-ALL; free-EDGAR SUE failed deep validation; PIT breadth come-back 2027-01-15). Principle already built at THEME level (theme_revisions + foresight ordering) |
| 12 | Liquidity Passport | MOSTLY EXISTS — days-to-build IS max-practical-size inverted (MAX_ADV_PCT=10%); options-liquidity join = small addition |
| 13 | Re-Entry Regret | BLOCKED — R1 replay/EXIT-GRID work the fire tape, not operator exits; needs position ledger (RUL-F3.2) + pre-outcome trigger spec (RUL-F3.4); look-ahead labels barred (RUL-F3.3) |
| 14 | Great Company Trap | BUILT BUT INVISIBLE — great_company_trap() 3-leg de-escalation computes nightly to per-ticker JSON with zero render surface; crowding_z hard-coded None; legs 2-3 watchlist-coverage-only. Quality×valuation SCORING composite stays CUT (G1-DEFERRED, retest ~2027-H2) |
| 15 | Operator Feedback Capture | LARGELY BUILT — admin/actions.py ledger (acted/dismissed/overrode/snoozed, #1550/#1714) + Oracle operator tape (nightly-graded) + DQ-2 (n≥25) + exposure log. Gaps: no `buy`/`regret` tokens; no reason taxonomy. Feedback→NW-weights FORBIDDEN (RUL-N2) |

## 3. Where our evidence corrects Codex

1. **"Wait for pullback" is contaminated advice** — WAIT-GRID-1: delays 1–5 bars flat, 10 bars hurts. A "wait" recommendation needs fresh prereg against our own null.
2. **Insider-as-confirmer is a settled null**, not an open idea.
3. **"Event edge upgrades entries" is already doctrine at theme level** (foresight: bottleneck leads, revision confirms, entry timed separately).
4. **The meta-advice (frontier model judges, cheap models build, no random backtests) is already house law.**

## 4. Build docket

**Wave 1 (dispatched 2026-07-06, this adjudication):**
- **B1** Render great-company trap on stock.html (mirror moat_falsifiers pattern) + activate crowding_z at the panels() call site. Display-only.
- **B2** Buy Decision Packet v0: compact `dossier` join onto us_standouts rows (action / why_now / why_not / stale_flags / authority_level / no_buy_reasons) + `trim-only` fifth verb in stock_view._action(). Composition only — no new arithmetic.
- **B3** "Not now because…" reasons line on the board expander, composed from live deterministic veto reason-codes. Downgrade-only.

**Wave 2 (queued):** B4 per-ticker conviction-delta (PIT gate-snapshot store + diff engine + board strip; nightly advances the store); B5 event-landmine tail (EDGAR debt-maturity panel + forward-FDA source assessment + display chip).

**Wave 3 (needs operator decision / dispatch):** B6 watchlist push spine (push-channel choice); B7 rotation_state.py named-bet labels (dispatch existing audit); B8 operator-capture `buy`/`regret` tokens + reason taxonomy. Chips: EMA/trend-decay (display-only), options-liquidity passport join.

**Do NOT build:** fused No-Buy verdict (R3/FR-1); 4-way meta-router (FR-1/A7_ORIGINATE); insider×T2 (null; recheck ~2027-H2); per-stock revisions gate (data + prereg); quality×valuation scoring composite (G1-DEFERRED); feedback→NW-weights (RUL-N2); "wait N days" recommendations (WAIT-GRID-1 contamination).

## 5. Ops findings (side discoveries)

- Dispersion dashboard chip hard-disabled via `false and` since #1672 while its pipeline runs nightly — confirm whether intentional.
- `htf_s1` key absent from committed signal_gate.json despite #1766 — verify after next nightly render.
- Committee independence chip (#1768) template-committed, awaiting next render (self-heals).

## 6. Clocks

| Date | Event |
|---|---|
| 2026-07-20 | W-OVC options-caution build; F-HZ-1 dilution-hazard come-back |
| 2026-08-30 | altdata family promotion-readiness (n_dates 25) |
| 2026-09-15 | exposure-conditioned operator contrasts |
| 2026-10-01 | kernel arming — FR-1 re-proposals (de-escalation-only veto), NARR-2/3 |
| 2026-10-06 | DISP-GATE-1 basis-stationarity review |
| ≥2026-Q4 | anti-chase ext_z hard-gate flip (EI P3) |
| 2027-01-15 | revisions PIT history come-back (SLF-036) |
| ~2027-H2 | G1-Retest / Ruler-H (unlocks quality-composite + insider re-open) |
