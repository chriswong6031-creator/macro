# Washout Counter-Read — TIER REGISTRATION (display / context)

**Program:** Rotation Command (research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md, #2286), RC-R11.
**Organ:** `engine/oracle/washout_counterread.py` · **Schema:** `washout_counterread.v1`.
**Status:** REGISTERED — merged BEFORE any forward outcome is graded (Constitution §I.3).
**Tier:** display / context. Authority `{may_rank, may_gate, may_size, may_escalate}` all False.

## 1. What it is

On **2026-06-26 — the exact session the Mag-7 complex bottomed — the risk radar printed its
maximum growth-scare reading (90.8, risk-off band).** A defensive-rotation score peaking on a
low is not a malfunction; it is what that scare measures. But nothing labeled it, so the
extreme read as an unqualified "get out" beside a tape that was turning. This organ prints one
honest counter-read chip beside the risk banner:

> when the growth scare is at an extreme **AND** a major US index or cohort simultaneously sits
> at a depth extreme → **"capitulation-zone reading — historically two-sided."**

A washout can precede a bounce about as often as a further leg down. The chip is context, not a
forecast and not a buy signal. It **never suppresses or modifies the risk banner, state, or
bands** — it sits beside them, exactly like the election-cycle modulator.

## 2. The firing rule (frozen)

Fires (`show=True`) iff BOTH:
- **Growth extreme:** `growth_scare_score ≥ 88` (the risk-off band boundary,
  `engine/risk_radar.py _DEFAULT_BANDS`). Read from `data/regime/latest.json`
  `risk_radar.scares[scare=="growth"].score`. The score is already a percentile-composite, so
  no external normalization is applied.
- **Depth extreme on ≥1 US index/cohort**, via EITHER (the masterplan's "IHM washout_turn OR
  63d drawdown; index or cohort"):
  - **Price depth** — trailing-63-session drawdown in the deepest decile (`depth_pctile ≥ 90`)
    of a 10-year self-history, computed from `data/yahoo/{SPY,QQQ,XLK}` close. XLK is included
    because it is NOT in the IHM roster.
  - **Momentum depth (corroboration)** — from `data/index_momentum/latest.json` (IHM), US
    roster {SPY,QQQ,IWM,SOXX,MAG7}: a `1D` grid `depth_pctile ≤ 10` (low MACD-histogram depth)
    OR a recent `washout_turn` quality-tagged event. Labeled separately from the price metric —
    the two quantities are never conflated in the payload or copy.

Thresholds (88 / 90 / 10) are frozen here and are NOT tuned against outcomes.

## 3. Honesty notes (measured, not assumed)

- **2026-06-26 was a shallow-price / defensive-rotation capitulation.** On that date SPY was
  only −3.8% off its 63d high, QQQ −5.2%, XLK −8.5% — 63d-drawdown percentiles of 26/26/17,
  NOT price-depth extremes. The growth scare hit 90.8 from **defensive-rotation composition**
  (XLU/SPY, XLY/XLP rolldown velocity), not index drawdown. This is precisely why the depth
  input is an **OR that includes the IHM momentum/washout path**: a cohort (MAG7/SOXX) can be
  washed out at the momentum grain while the broad index drawdown stays shallow. The organ does
  not claim to relabel 06-26 retroactively — it is graded prospectively (§4).
- The word **"validated" never appears** on these surfaces (matches the ratio_lens / tape_onset
  disclosure law). The chip copy is "historically two-sided," "context only," never a direction.

## 4. Ledger + expected-NULL pre-registration

`data/oracle/washout_counterread_ledger.jsonl` — append-only, keep-first per firing `as_of`,
COLLECT_LANE=nightly gated. **Pre-registered EXPECTED-NULL:** the forward return distribution
after a co-occurrence is declared two-sided in advance. Any promotion beyond display tier
requires a separate registered gauntlet (a pre-registered study of forward returns conditioned
on the firing), never a tuning of §2 against this ledger. As of registration the ledger is
empty (today's growth scare is 38.1 — quiet is the normal state).

## 5. Surfaces

- Server-rendered chip in `templates/_risk_radar_card.html.j2` (the `.rrx-washout` variant of
  the modulator row), inheriting all pages that include the card (macro dashboard / US stocks /
  China / Canada). The full two-sided caveat + depth detail live in the `help()` tooltip so the
  chip cannot overclaim. It reaches the template as `rd.counterread` via
  `engine/risk_radar.py` → `engine/market_state.py` (same path as `rd.cycle`).
- Machine feed `site/oracledata/washout_counterread.json` (the current payload).

## 6. Clock

Registered 2026-07-12. First forward grades mature ~21 sessions after the first firing. No
promotion study runs before the ledger has matured firings (there are none yet).
