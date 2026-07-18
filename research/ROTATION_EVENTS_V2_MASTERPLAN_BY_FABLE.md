# Rotation Events v2 — cross-sector, into-strength, contagion, faltering

Status: ADJUDICATED MASTERPLAN (Fable, 2026-07-18). Operator-initiated: "the SMH->MAGS
rotation event is frozen at receipts from 06-22/06-25 and shows as major while the thesis
is clearly stale; XLK->XLV, SMH->XLV, and MAGS->XLV rotation into healthcare strength is
completely undetected; contagion from the GOOG EU ruling is spreading to MSFT, IGV, and
AAPL with no surface; there are no momentum, velocity, or flow inputs; and the page only
ever shows two rotations."

Companion programs this plan coordinates: Rotation Command (research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md, 2026-07-11), XSR (this program OWNS XSR-W2 cross-sector container + W3 breadth receiver logic where subsumed). S1/S2 preregs: research/ROTATION_COMMAND_S1_S2_PREREG.md. Universe prereg: research/ROTATION_UNIVERSE_EXTENSION_PREREG.md (ships BEFORE any expanded-universe forward returns are computed — Constraint 4).

---

## 0. Incident of record — point-in-time verified (2026-07-17)

Method: ground truth from `data/yahoo/*.parquet` and `data/stocks/*.parquet` (last bar 2026-07-17) cross-checked against `data/rotation_events/state.json`. All lane2 arithmetic verified against live stores; findings accepted or rejected by the judge's arithmetic; no current-file state trusted for the historical reconstruction.

### 0.1 Momentum table (as of 2026-07-17, verified by Lane 2)

| Ticker | 5d% | 10d% | 20d% | 60d% | 10d_accel |
|--------|-----|------|------|------|-----------|
| SMH | −8.92 | −6.04 | −10.81 | +19.77 | −0.96 |
| MAGS | −1.14 | +2.78 | +3.67 | N/A (25-session store) | +1.91 |
| XLV | +0.16 | −1.62 | +7.36 | +10.40 | −10.74 |
| XLK | −5.48 | −2.77 | −5.38 | +13.51 | −0.08 |
| IGV | +0.42 | −0.82 | +4.08 | +7.08 | −5.77 |
| AAPL | +5.84 | +8.14 | +12.77 | +25.50 | +3.85 |
| GOOGL | −2.91 | −3.65 | −4.68 | +4.42 | −2.58 |
| SPY | −1.54 | −0.20 | +0.57 | +5.57 | −0.97 |

XLK and SMH are BOTH at their exact 40-session lows as of 07-17. XLV is +10.52% above its 40-session low and within 0.03% of a 20-session HIGH.

### 0.2 The SMH~MAGS correlation regime shift (verified)

SMH vs EW mag7-basket 10d rolling daily-return correlation:

| Date | 10d_corr |
|------|----------|
| 2026-07-01 | 0.033 |
| 2026-07-08 | 0.017 |
| 2026-07-09 | 0.055 |
| 2026-07-10 | 0.331 |
| 2026-07-13 | 0.442 |
| 2026-07-16 | 0.595 |
| 2026-07-17 | 0.538 |

Unconditional 25-session correlation: 0.275. Correlation rose from near-zero (0.02) to 0.54–0.59 in seven sessions — a regime change from diversifying to coupling. SPY-residual correlation rise: +0.493 (idiosyncratic component of the coupling, not just beta-driven co-movement). Both-fell count: 3 of 10 sessions using the EW basket (corrected from the MAGS-ETF count of 4 — the MAGS ETF has only 25 sessions of history and must not be used directly; the EW mag7 basket composite is the mandatory substitute per Constraint 7).

### 0.3 XLK→XLV rotation-into-strength: the blind spot proven (verified)

XLV/XLK ratio 20-session change: +13.47% (from the Lane 2 rs_table). XLV off its 40-session low: +10.52%. XLV relative-strength vs SPY over 20 sessions (rs20): +6.79%. XLK rs20: −5.96% (SPY-relative, at exact 40d low).

**Judge's verified finding:** the v1 `turn_up` function at `engine/rotation_events.py` requires the receiver to be AT or near a fresh 40-session low (parameter `low_lookback=40`). XLV is +10.52% above its 40-session low — the condition is structurally impossible to satisfy. Even if cross-sector pairs (XLK→XLV, SMH→XLV) existed in `config/sector_legs.json`, the v1 detector could not fire on this tape. This is not a threshold calibration question — it is an architectural gap. The into-strength rotation blind spot is proven on the 07-17 numbers.

### 0.4 The v1 handoff kernel also does NOT fire on 07-17 (verified)

The judge's red-team arithmetic on live stores (final_spec.md FINDING 1): `blowoff_crash(XLK)` → runup 10.92% (<15% `runup_min`), z=0.53, drawdown 8.62% (<10% `crash_min`) → **False**. `blowoff_crash(SMH)` → runup 22.97% (≥15%), drawdown 16.8% (≥10%), but z=1.15 (<2.0 `z_min`) AND runup 22.97% (<30% `runup_strong`) → abnormal=False → **False**. The entire 07-17 cross-sector detection coverage depends exclusively on the new into-strength and contagion families, not the reused blowoff kernel. Neither XLK→XLV nor SMH→XLV produces a `cross_handoff` on 07-17 tape.

### 0.5 Faltering: confirmed NOT firing on 07-17 (correct behavior)

Live state.json: pair `xlk:ai_semis->mag7`, lapse_count=1, receipts frozen at blowoff.peak_date 2026-06-22 / turn.low_date 2026-06-25. Both designs specify faltering at lapse≥2. With lapse=1, the event is `active`/`major` — this is correct per the adjudicated rule (RV2-R1 PARAMS_V2). The operator's complaint is about the lack of a decay indicator on the displayed event, not about the faltering-fire threshold. The fix: surface `sessions_since_confirm` and `sessions_to_close` as the decay countdown visible before any state demotion.

### 0.6 XLP negative control (verified)

XLP (Consumer Staples) receiver rs20: +1.94% vs the into_strength threshold `rel_lead=0.05` (5%). On the broad-down day of 07-17 (SPY −1.54%), into_strength correctly does NOT fire for XLK→XLP. The SPY-relative `rel_lead` gate is doing its job. No false-fire on defensive sectors.

---

## 1. Root causes, ranked (from critic.json, verbatim rank, with code references)

**#1 (highest leverage) — PAIR-UNIVERSE ABSTRACTION is hardcoded intra-sector.**
`engine/rotation_events.py:249-256` nests `legs.items()` inside a single `skey` loop; `config/sector_legs.json` exposes only per-sector `legs` (no cross-sector `pairs` key — grep confirms zero matches). This single architectural choice simultaneously forecloses cross-sector rotation (XLK→XLV), MAGS/SMH→XLV, and any donor→receiver contagion construction. Fixing the universe to a registry of arbitrary ordered (donor_series → receiver_series) pairs decoupled from the sector→legs tree is the single highest-leverage change — it unlocks all four operator-requested event kinds in one structural move. This is the XSR-W2 container.

**#2 — SIGNATURE COUPLING: receiver must be at a fresh 40-session low.**
`engine/rotation_events.py` `turn_up()` requires the in-leg to be at or near a fresh 40-session low (`low_lookback=40`, `low_within=15`). This is the mathematical reason rotation-into-strength is undetectable — XLV is +10.52% above its 40d low on 07-17 (§0.3). Decoupling the receiver signature from the fresh-low reclaim into a family that fires on leading-strength conditions (rs20 ≥ +5%, ratio 20d-high or +5%, breadth rising > donor) is the second unlock. The existing `turn_up` is retained unchanged for the classic blowoff→fresh-low handoff.

**#3 — SINGLE EVENT KIND / BINARY AND.**
There is exactly one event pattern (blowoff_crash + turn_up + pair_confirm, all three required) and one severity axis. No faltering event kind, no correlation-regime event, no single-sided velocity read. The detector emits creation/close only. Adding an `event_type` discriminator to the payload (additive per the scorecard.v1 lesson) so multiple detector families coexist under one schema is the enabling refactor. Without it, every new kind needs a parallel surface, which the `sector_rotation_schedule.v1` kill forbids.

**#4 — NO LIFECYCLE / DECAY SURFACING.**
`lapse_count` and `neg_run` are computed at `engine/rotation_events.py:271-289` but stripped from the display payload (`events_active.append` at `:321` omits them). The `severity()` function does not decay with `lapse_count`. This is the direct cause of the operator complaint: a frozen "major" event shows full-severity receipts from 06-22/06-25 with no indicator that the thesis is weakening. Surfacing these fields and making severity decay-aware at lapse≥2 answers the complaint directly and provides the substrate for the faltering event kind.

**#5 — ORPHANED TRIAGE ROUTING.**
`alert_triage.py:105` `_ROTATION_TIER = {"rotation_emerging":"watch","rotation_fading":"context"}` has no `rotation_event` key. Line `:511` defaults unknown types to `context`. The rotation_event alert type has never exercised the triage path in production (created_tonight has been empty). The moment a v2 event fires for the first time, its highest-severity signal will debut at the lowest triage band. A one-line fix (`_ROTATION_TIER['rotation_event']='watch'`) must ship in the same PR that enables cross-sector creation.

---

## 2. Doctrine position and boundary map

All families in this wave ship at **display/context tier** and require no promotion gate to build. Detection infrastructure ships freely under the Epistemics law — a null result never blocks building or accrual; the gauntlet applies only when promoting to authority (rank/size/gate). No construct in `research/DO_NOT_REBUILD.md` is rebuilt.

### 2.1 Relationship to Rotation Command (RC-R1..R15)

| RC requirement | Status entering this build | v2 action |
|---|---|---|
| RC-R1 (rotation event + detector) | SHIPPED #2319 | v2 extends engine, additive |
| RC-R2 (append-only marker integrity) | SHIPPED #2320 | no change |
| RC-R3 (rotation lane on surfaces) | SHIPPED #2322/#2399 | v2 extends rail + chips |
| RC-R4 (mega-cap node in taxonomy) | SHIPPED #2322 | no change |
| RC-R5 (alert severity + routing) | SHIPPED #2322 | v2 fixes orphaned triage |
| RC-R6 (fragmentation chips) | SHIPPED #2319 | no change |
| RC-R7 (dual-membership chip) | SHIPPED #2399 | no change |
| RC-R8 (PIT replay + forward log) | SHIPPED #2358 | v2 adds new event families; new prereg required before expanded-universe returns |
| RC-R9 (S1/S2 preregs) | BOTH ACCRUE — n=13<20 | no authority change; promotion clock reset for new families |
| RC-R10 (honest late-classing) | SHIPPED #2358 | no change |
| RC-R11 (washout counter-read) | SHIPPED #2399 | no change |
| RC-R12 (promotion/kill to gate) | BLOCKED — S1/S2 ACCRUE | CLOSED; not touched |
| RC-R13 (ontology adoption) | PARTIAL #2708 | no change in this build |
| RC-R14 (China/HK ports) | SHIPPED #2386/#2445 | US-only in this wave; ports are deliberate W2+ |
| RC-R15 (self-grading registry) | SHIPPED #2358 | new families register independently |

### 2.2 XSR wave ownership

- **XSR-W2 (this program owns):** cross-sector pair registration (config/rotation_universe.json) + Turn Desk Family-D fold-in + rotation-events cross-sector lane. Events route through the existing Turn Desk surface; no parallel `sector_rotation_schedule.v1` surface (DO_NOT_REBUILD kill).
- **XSR-W3 (subsumed in this build):** receiving-sector breadth detector — the into_strength family uses `data/breadth/sector_breadth.parquet` (`pct_above_50` mapped to GICS sectors) as a gate component. This is the W3 breadth-receiver logic integrated into the v2 detector.
- **XSR-W4 (coordination note):** the correlation_regime_break family maps to XSR-W4 dispersion-regime (COR1M/DSPX/SPY-QQQ RV spread). Coordinate with VSB (vol_weather organ from VSB-W5 #2537) before promoting. This build emits the detection only; the dispersion-regime HARD-GATE requires separate operator ratification per the kill boundary.
- **Turn Desk Family-D fold:** cross-sector pair events fold into Turn Desk as Family-D columns per `ORACLE_ROTATION_TM_CODEX_ADJUDICATION.md` and the XSR-R3 kill boundary. This is a later wave; v2 ships the payload and display surface; the Turn Desk column integration is a sequenced follow-on.

### 2.3 Binding kills (all from DO_NOT_REBUILD.md and lane4 audit)

Every kill below is a hard boundary. Violations of these are rejected at review.

1. **Rotation × cycle-position entry-confluence** — DO NOT TEST at any tier. Rotation events may not be wired into the ENTRY-NOW double gate, any cycle-stance input, or any confluence term. The precise allowed boundary: display chips on cards, split-view disclosure copy, fragmentation-representativeness chip. RC-R12 flag-gated experiment requires S1 GO first — S1 ACCRUE means this gate is CLOSED.

2. **`sector_rotation_schedule.v1` parallel surface** — DO NOT BUILD. Cross-sector pairs fold into Turn Desk / oracle_state.json as Family-D. Not a parallel uncalibrated surface.

3. **Count-conjunction bundle** — KILLED. The "4-of-4 defensive-lean floor bundle" (radar-caution × ≥3-intl-alerts × rotation-bottom × weekly-roll) is dead; the claimed lead collapsed on verification. No new rotation-bottom + multi-signal conjunction without its own prereg.

4. **Positioning fusion** — ILLEGAL. Flow/options/gamma are receipts surfaced in Tier-2 hover only. They never enter any classifier, score, or state machine.

5. **LLM-originated signals, escalations, or contagion context** — FORBIDDEN. No LLM call anywhere in detection code.

6. **China connect-flow (southbound/northbound) as detector input or gate** — REJECTED. Southbound net z shown as one-line context receipt on China surfaces only.

7. **Gating A-share reversal by subsector rotation state** — FALSIFIED.

8. **Defensive-rotation Phase-0 (vol-shock predictor)** — FALSIFIED, construction-scoped. Does NOT block the into_strength and corr_regime families on other constructions.

9. **MAGS ETF as the mag7 series** — FORBIDDEN (25-session store; data-starved). The mandatory path is the EW mag7 basket composite (`data/baskets/ohlcv`, `engine/basket_index.consolidated_candle`). Resolver hard-asserts and rejects any spec naming ticker MAGS.

10. **Peeking at expanded-universe forward returns before the prereg is frozen and merged** — gate poison. The prereg (research/ROTATION_UNIVERSE_EXTENSION_PREREG.md) must be merged BEFORE any expanded-universe forward returns are computed (Constraint 4).

---

## 3. Requirements — RV2-R1..R11

### RV2-R1 — Merged detector spec adopted

The final_spec.md adjudication is adopted verbatim. Families: **A/v1** (intra-sector handoff, byte-identical kernel), **B** (into_strength, receiver-leading), **C** (donor_state: blowoff | contagion_bleed), **D** (correlation_regime_break, two-part gate), **E** (event_health / faltering, surfacing), **F** (velocity_board, always-on, emits no events). Universe registry: `config/rotation_universe.json` (new, region-portable, 12 series + 7 cross-sector pairs + 3 contagion pairs + 1 complex). PARAMS_V2 frozen (all values disclosed in final_spec.md §4). No design freedom remains for the builder — spec is authoritative.

Verified on 07-17 tape: into_strength fires for XLK→XLV (off_low +10.52%, rs20 +6.79%, ratio 20d +13.47%, breadth 81.4% rising); corr_break fires for SMH~mag7-EW (raw 0.654, rise +0.495, resid-rise +0.493, both-fell 3); faltering does NOT fire for ai_semis→mag7 at lapse=1 (correct — countdown surfaces instead); XLP negative control correctly silent.

### RV2-R2 — v1 kernel frozen byte-identical

The following functions in `engine/rotation_events.py` stay byte-identical: `blowoff_crash`, `turn_up`, `pair_confirm`, `evaluate_pair`, `find_start`, `severity`, `step_pairs`, `to_alerts`. Acceptance i (Replay A) asserts the 06-25 handoff fires identically under v2. Any diff touching these functions is rejected. New code goes into new functions (`donor_state`, `into_strength`, `evaluate_cross`, `step_cross_pairs`, `decay_severity`, `_health`, `emit_v2`) or new modules (`engine/rotation_universe.py`, `engine/rotation_corr.py`, `engine/rotation_velocity.py`, `engine/rotation_flows.py`).

### RV2-R3 — Lane-gated ledger + coldstart seed idempotency

The `events.jsonl` append (`engine/rotation_events.py:425`) is wrapped in `if _ledger_lane_armed():` (checks `COLLECT_LANE=nightly`). Off-lane: payload + state.json render, no ledger advance. Nightly runs `COLLECT_LANE=nightly brun build_rotation_events`. Coldstart replay rows go to `data/rotation_events/coldstart_seed.jsonl` (separate file, never events.jsonl). Fingerprint dedup ensures running cold twice yields identical line counts in both files. This implements the pattern established by the ignition-ledger-lane-gate and us-audit-ledger-lane-gates precedents.

### RV2-R4 — Prereg-first: no expanded-universe forward returns in this build

`research/ROTATION_UNIVERSE_EXTENSION_PREREG.md` ships BEFORE any expanded-universe events accrue (the prereg merge is a precondition, not an afterthought). The new event families (into_strength, cross_handoff, correlation_break, event_faltering, single_sided_velocity) each accrue independently to their own floor (n≥20) in the forward ledger. No historical hit-rate may be examined before that floor. Peeking poisons the promotion gate. The RC-R8 replay census covers v1 intra-sector events only; the new families start at n=0.

### RV2-R5 — Additive-only schema; SCHEMA string stays "rotation_events.v1"

No v1 field is removed or renamed. New fields added per-event: `event_type`, `to_sector`, `from_sector`, `donor_signature`, `severity_effective`, `health{state, lapse_count, neg_run, sessions_since_confirm, sessions_to_close}`, `flow_receipts{donor, receiver}`. New top-level fields: `n_cross_pairs_scanned`, `contagion[]`, `velocity_board{}`, `closed_recent[]`. V1 events back-filled `event_type:"handoff"`, `to_sector:sector`, `from_sector:sector` so all events carry them. All 6 consumers (`world_state._compose_rotation_events`, `subsector_rotation.html.j2`, `sector_cycles.js`, `to_alerts`, china/hk templates) use optional chaining — no KeyError on new fields.

Unknown event_type values in consumers: switch on `event_type` with cautious-default (render as handoff-lane "Watch — don't chase") per the UI spec. NEVER pattern-match the key set.

### RV2-R6 — Flow / options / gamma: receipts only

ETF flow receipts computed fresh from `data/flows/{etf}.parquet` via `implied = (df.so_mn.diff() * df.nav).tail(N).sum()` with its own `flow_asof` distinct from the price asof. NEVER reads `etf_flow_proxy.parquet` (16 days stale as of 07-17). Basket/SMH/IGV series with no flows file emit `flow:null, flow_note:"no ETF flow feed"`. Options `net_premium_mn` from `data/options_flow/summary_{etf}`; gamma regime from `data/polygon_gex/summary_{etf}` — each carry their own asof.

Unit test #9 enforces this rule: monkeypatching `etf_flow_receipt` to wild values produces zero change in any state/`created_tonight` output. Flow columns appear only in Tier-2 hover receipts, explicitly labeled "context, not a trigger."

### RV2-R7 — MAGS ETF forbidden; EW mag7 basket labeled honestly

`engine/rotation_universe.resolve_series` hard-asserts and raises on any spec with `ticker:"MAGS"`. The mandatory path for the mag7 leg is `basket_composite` kind with `basket:"mag7"` → EW `consolidated_candle` from `data/baskets/ohlcv`. The UI labels this series "Mag-7 basket" (EN) / "七巨头篮子" (ZH) everywhere — never "MAGS". The hero pill for the mag7 leg reads "Mag-7 basket" / "七巨头等权篮子". This is a defense-in-depth assertion of Constraint 7.

### RV2-R8 — UI doctrine overhaul per UI spec

The UI spec (ui_spec.md) is authoritative; all 13 doctrine fixes (D-1..D-13) and 9 dead-end wirings ship in the same PR as the engine. The verdict badge display label changes from "Validated" to "Clears the bar" / "已达标" — the `verdict` key logic is untouched, only the display label map changes. Before the PR, run `python scripts/check_validated_claims.py` to confirm no new rendered occurrence of "validated"/"Validated".

The word "validated" must not appear in any new user-facing copy. Internal state names (RC-R9, W1, A15), raw variable names (`accel_z`, `vel_1w`, `HAC t`), and the phrases "expected-NULL", "display-tier", "ledgered", "prereg" are removed from all Tier-1 at-rest copy.

### RV2-R9 — Cycles and NW: display-context only

Rotation events may contribute to sector_cycles.html surface only as: (a) a display chip on the affected sector card (both from-sector and to-sector — the to_sector field enables this), (b) a fragmentation/representativeness disclosure chip. The existing RC-R3 chips (#2399) are the template. No wiring into the cycle stance, ENTRY-NOW gate, or any confluence term. RC-R12 is BLOCKED. The Neural Web `market_plane.json` lobe wiring (RC OQ #2) is a follow-on after v2 renders stabilize.

### RV2-R10 — US-only wave 1

This build is US-only. China/HK ports (`rotation_universe_china.json`, `rotation_universe_hk.json`) are deliberate later waves. The `config/rotation_universe.json` shape is region-portable by construction (`region`, `data_subdir` fields), but the ports are a 3-region render-treadmill change with different contagion-receipt rules (southbound net z = context only, binding kill). Turn Desk Family-D fold-in of cross-sector events is sequenced as a separate wave after the Turn Desk authors confirm the column integration. Intraday fastpath is XSR-W6, not this build.

### RV2-R11 — Alert triage un-orphaning ships with creation-enable

`alert_triage.py:105` gains `'rotation_event':'watch'` and `:574` gains `('rotation','rotation_event'):'rotation'` cluster entry. These changes are in the same PR as the engine changes that enable cross-sector event creation. A cross-sector or into-strength event must not debut at the `context` default band when it fires for the first time — that is the exact scenario the critic identified as highest-risk.

---

## 4. The 07-17 episode walked through the v2 detector

Using the judge's verified receipts from final_spec.md and lane2.md:

**Step 1 — Donor state (Family C):**
XLK: `close <= min(last 40) * 1.01` ✓ (at exact 40d low); `rs20 = −5.96%` ≤ −3% (SPY-relative, FINDING 8 fix) ✓; `not blowoff` ✓ (blowoff_crash(XLK) = False, §0.4). → `donor_state = contagion_bleed`.

**Step 2 — Receiver state (Family B, into_strength):**
XLV: `off_low = +10.52%` ≥ 8% ✓; `rs20 = +6.79%` ≥ 5% ✓; ratio XLV/XLK 20d change `+13.47%` ≥ 5% ✓ (20d-high OR-branch: ratio at 0.91742 vs 20d max 0.91774 → **False**, 0.03% below; ratio-chg OR-branch **True** — honest receipt, FINDING 4); breadth_above50 = 81.4% ≥ 65%, rising over 5d ✓. 2-session hysteresis: both sessions confirm before creation. → `into_strength` fires for XLK→XLV.

XLP negative control: `rs20 = +1.94%` < 5% → `into_strength` correctly does NOT fire (FINDING 7).

**Step 3 — Event creation:**
`event_type = "into_strength"` (b via into_strength, NOT cross_handoff — FINDING 1); `donor_signature = "contagion_bleed"`; `blowoff = null`; `turn = null`. Corrected receipt: `{ratio_chg_10s: 0.0118, inflected: true, ratio_20s_high: false, ratio_chg_20s: 0.1347}` (FINDING 4). State: `active`, severity `notable` (correlation_regime family, Constraint kill boundary cap).

**Step 4 — Contagion break (Family D):**
SMH~mag7-EW: raw `corr10 = 0.654` ≥ 0.45 ✓; `corr_rise = +0.495` ≥ 0.25 ✓; SPY-residual `corr_rise = +0.493` ≥ 0.20 ✓ (FINDING 2 fix — idiosyncratic component rising, not just beta co-movement); `both_fell_10 = 3` ≥ 3 ✓ (EW basket, not MAGS ETF — FINDING 3 fix); prior 20d baseline corr ≤ 0.30 ✓. → `correlation_regime_break` fires for SMH~mag7-EW (xlk_complex).

Attribution (idio-only, FINDING 5): probe set {AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA}; idio-7d decomposition (SPY + complex-common adjusted): GOOGL **−4.58%** = argmin. `detail_en = "GOOGL idiosyncratic decline (−4.6% over 7 sessions) led the coupling"`. Severity capped at `notable` (regime description, no forecast authority).

Broad-selloff negative control: a pair co-moving only via SPY has residual-rise ≈ 0 → RESID gate blocks it.

**Step 5 — Faltering for active ai_semis→mag7 event:**
Live state: `lapse_count = 1`. Rule: `weakening` requires `lapse_count ≥ 2` OR `neg_run ≥ 2` OR ratio neg-run ≥ 3 (FINDING 6 — strict). At lapse=1: `health.state = "active"`, `severity = "major"` unchanged. Countdown surfaces: `sessions_since_confirm = 2`, `sessions_to_close` (distance to TTL/lapse close criterion) shown as decay indicator. Faltering does NOT fire tonight — this is correct. The operator's complaint is answered by the countdown indicator, not by forcing a premature state demotion.

**Step 6 — Closures:**
`closed_recent[]` reads the rolling 5-session tail of events.jsonl. The 4 events that closed tonight are surfaced in the `#rc-closures` strip with `close_reason` plainified (ratio_slope_flipped → "the move reversed", conditions_lapsed → "signals faded", ttl → "ran its course").

---

## 5. Acceptance

### 5.1 Unit tests (`tests/test_rotation_universe.py`, `tests/test_rotation_events_v2.py`)

1. `resolve_series`: mag7 spec → basket composite; any spec naming ticker `MAGS` raises.
2. `donor_state`: XLK-shape (40d low, rs20 −6%) → `contagion_bleed`; broad-selloff donor (at low, rs20 ≈ 0) → `None`; blowoff-shape → `blowoff`.
3. `into_strength`: XLV-shape fires; XLP negative control (rs20 +1.94%) → `None`; 1-session breadth blip (confirm=1) → no creation (hysteresis).
4. `corr_break`: raw 0.16→0.65, resid-rise +0.49, both-fell 3 → fires; broad-selloff control (resid-rise ≈ 0) → `None`; `both_fell` forced to 2 → `None`.
5. `attribute_break`: GOOGL most-negative idio → `leader` names GOOGL.
6. `decay_severity` / `_health`: lapse=1 → `active`/`major`; lapse=2 → `weakening`/demoted once; closing_soon → `standard`.
7. Lane gate: `COLLECT_LANE` unset → events.jsonl NOT written; `=nightly` → written.
8. Coldstart: run cold twice → identical events.jsonl line count; replay in coldstart_seed.jsonl.
9. Flow-not-a-trigger: monkeypatch `etf_flow_receipt` to wild values → zero change in state/created_tonight.
10. Additive schema: every v1 key present on each v2 event; `world_state._compose_rotation_events` over v2 payload → no KeyError.

### 5.2 Real-episode replay assertions (`scripts/verify_rotation_v2_episodes.py --scratch`)

- **Replay A (06-25 regression):** truncate ≤ 2026-06-30, run intra-sector `step_pairs`. Assert `xlk:ai_semis→mag7` created with `event_type="handoff"`, `blowoff.peak_date ≈ 2026-06-22`, `turn.low_date ≈ 2026-06-25`. Byte-compare receipts to v1-only run (the kernel is frozen byte-identical).
- **Replay B (07-17 detection):** run as_of 2026-07-17. Assert: `xlk→xlv` and/or `smh→xlv` created with `event_type="into_strength"` (NOT handoff), `donor_signature="contagion_bleed"`, `receiver.off_40d_low_pct ≈ 0.1052`, `ratio_chg_20s ≈ 0.1347`, `ratio_20s_high == false`, `ratio.inflected == true`, `blowoff == null`. Contagion: xlk_complex break with `corr10_raw ≈ 0.65`, `corr_resid_rise ≈ 0.49`, `both_fell_10 == 3`, `attribution.leader == "mag7_basket"` with GOOGL in detail_en. ai_semis→mag7: `health.state == "active"`, `severity == "major"` (lapse=1). closed_recent populated. Negatives: no into_strength on a receiver at a 40d low; no into_strength for XLP; no contagion for a pure-beta pair.

### 5.3 Degrade-mode UI

Empty state (no active events): "No money-flow events right now — a quiet tape is a valid read. Nothing to do." / "当前无资金流向事件——安静的盘面也是有效读数。无需操作." This is a first-class displayed state, not a missing section.

### 5.4 CI checks

- `python scripts/check_validated_claims.py` — no new "validated"/"Validated" in rendered HTML.
- `python -m scripts.check_template_site_sync` — templates/subsector_rotation.js and site/subsector_rotation.js byte-match.
- Unit tests all green.
- No `title=` attribute carrying bilingual translated text (check_title_i18n).

---

## 6. Open questions (parked, not blockers)

1. **Event decay TTL:** current close criteria (lapse_count≥5 OR neg_run≥3 OR day_n>20) allowed the ai_semis→mag7 event to persist as "major" for 15+ sessions after receipts froze. The `sessions_to_close` countdown is the near-term fix. Revisiting whether the TTL should shorten for events whose donor and receiver receipts are both absent is a W2 census question — the v1 replay data (#2358) can inform this after the expanded universe is running.

2. **ETF flow collector extension:** `data/flows/{XLK,XLV}.parquet` reach 07-16; SMH and IGV have no `data/flows/` file (null receipt). Extending the ETF flow collector to cover SMH and IGV is a follow-on infrastructure task, not a blocker for v2.

3. **Options cohort store empty:** `data/options_flow/summary_{XLV,SMH}` may be empty if the options screener has not run for those ETFs. The v2 receipt carries its own asof and falls back to null gracefully; this is a data availability gap, not a code gap.

4. **China/HK port timing:** China port (#2386) and HK port (#2445) shipped the intra-sector architecture. The v2 cross-sector and into-strength families need `rotation_universe_china.json` and `rotation_universe_hk.json` to unlock for those regions. This is sequenced as W2+ with the constraint that southbound/northbound connect-flow remains context-receipt-only (binding kill §2.3 item 6).

5. **Fragmentation vs breadth-divergence census:** RC open question #3 (does the fragmentation index subsume basket_breadth_divergence or complement it?). The RC-R8 replay census covers intra-sector events; the cross-sector events that this build adds will require a separate census pass before either construct can be promoted. Parked per the masterplan's OQ#3.

6. **intraday fastpath:** the operator's velocity/flow asks invite an intraday cadence. This must route through XSR-W6 only. The lane-gate mechanism (RV2-R3) is the blocker that prevents accidental advance if any intraday script erroneously calls `build_rotation_events.py` — it will render the payload without advancing the ledger.
