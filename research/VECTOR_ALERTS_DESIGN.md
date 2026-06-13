# Bitcoin Vector — Real-Time Alerts + Live Timeline (design doc)

Status: **DESIGN ONLY — build deferred to Phase 3** (alerts depend on calibrated
signals from Phase 2). Written 2026-06-12. Endpoints referenced here were
live-tested today (see `VECTOR_DATA_AUDIT.md`).

What Glassnode/Swissblock ship: "Flash Crash Alert" (acute volatility warning +
stabilization follow-up) and "Flash Update" (brief on structural shifts — what
changed and why), both pushed via Telegram. We replicate both, plus a **live
alert timeline on vector.html** (which they don't have — they're Telegram-only).

---

## 1. Honest definition of "real-time" on zero cost

Two loops, both on GitHub Actions (public repo → free minutes):

| Loop | Cadence | Inputs | Evaluates |
|------|---------|--------|-----------|
| **Daily run** (existing, 22:40 UTC) | 1×/day | full collector suite | Structure Shift triggers, Risk Index 25-crossings, allocation changes, environment flips, cross-asset extremes |
| **Sentinel** (new, lightweight) | cron every 15–30 min (Actions cron is best-effort; expect 15–45 min effective) | ONE cheap call: Coinbase spot `api.coinbase.com/v2/prices/BTC-USD/spot` (✅ tested, keyless) + last hours of candles | Flash Crash state machine, Impulse sign |

LIMITATIONS.md entry: alerts are near-real-time (~15–45 min), price-based only
intraday; on-chain signals refresh daily. Their "real-time" is likely
minute-level — we are honest about ours.

Sentinel mechanics: restores `data/vector/alert_state.json` from the repo,
fetches price, updates state machines, and **commits only on state change**
(alerts are rare events → no commit spam, no wasted Pages deploys). A state
change also: appends to `data/vector/alerts.jsonl`, sends Telegram via the
existing `scripts/notify.py`, rebuilds + pushes `site/` so the timeline updates.

## 2. Alert taxonomy

| Type | Loop | Trigger (calibrated in Phase 2) | Severity |
|------|------|--------------------------------|----------|
| `flash_crash` state change | sentinel | state machine below | high |
| `impulse_flip` | sentinel | sign change of short-horizon impulse, only while in non-normal flash state (avoid noise) | medium |
| `structure_shift` | daily | Structure Shift oscillator confirmed cross of ±0.5 → "Bullish/Bearish Trigger"; payload includes days since last episode (their 60d/40d/53d annotation) | high |
| `risk_regime` | daily | Risk Index crosses 25 (either direction, with confirmation rule) | high |
| `allocation_change` | daily | any strategy variant changes {0, ½, 1} | medium |
| `environment_flip` | daily | mid-term Bull↔Bear classifier flip | medium |
| `risk_extreme` | daily | sustained Risk Index ≥ X for N days → contrarian capitulation watch (their documented contrarian use) | info |

### Flash Crash state machine (price-only → fully backtestable)

States: `normal → flash_crash → tail_risk_event → stabilizing_price → normal`

Sketch (thresholds k₁..k₄, N₁..N₂ calibrated on hourly history vs known
episodes — May 2021, June 2022, FTX Nov 2022, Aug 2024, etc.):
- `normal → flash_crash`: short-window return < −k₁·σ_hourly (acute drop vs
  trailing realized vol) or 24h return < −k₂%
- `flash_crash → tail_risk_event`: continued lower lows + 24h return < −k₃% (their
  card example: −4.61% 24h)
- `* → stabilizing_price`: N₁ hours without new low AND hourly vol decayed below
  k₄ × trigger vol (their card example: −3.35% 24h, recovering)
- `stabilizing_price → normal`: N₂ quiet hours
- **Impulse** = sign of short-horizon momentum (e.g. EMA-of-returns over ~24–72h),
  displayed on every flash card: "Impulse: positive/negative"

Calibration data: Coinbase hourly candles ✅ (tested; daily history reaches 2016;
hourly backfill ~95k rows one-time into parquet — added to Phase 1 collector list).

### Idempotency & schema (engine/alerts.py pattern)

```json
{"id": "flash_crash:2026-03-25T14:30Z:tail_risk_event",
 "ts": "2026-03-25T14:30:00Z", "type": "flash_crash", "severity": "high",
 "from": "flash_crash", "to": "tail_risk_event",
 "headline": "Flash Crash Index changed to: tail risk event",
 "context": {"price": 66432, "chg_24h_pct": -4.61, "impulse": "negative"},
 "anchor": "#flash-crash-card"}
```

ID = type + transition + timestamp-bucket → re-runs never double-fire (the
existing alert-log dedup rule). Telegram message mirrors their card wording:
headline + price + 24h% + impulse + one templated context line. **No LLM in the
alert path by default (D33 rescinded — LLM prose now allowed if we add an API
key to CI)** — baseline "what changed and why" = template filled with the exact
component values that flipped (e.g. "30d cost basis lost at $X; structure score
−0.62 → −0.38 over 5d").

## 3. Live timeline UI (vector.html section: "Alert Timeline")

Their UX (Telegram feed of cards) → our translation, in their visual language
(Inter, light theme, #285FFF ramp):

- **Vertical timeline, newest first**, day-grouped with sticky date headers —
  reads like their Telegram channel scrollback.
- Each entry = a compact flash-card row:
  - left: timeline rail with a colored node (red-tint `#FEB5B5/#D30B0B` =
    flash crash/tail risk; indigo = structure shift bullish; light periwinkle =
    bearish; blue = risk regime; gray = allocation/info)
  - chip with alert type, then the headline in their typography
    ("Flash Crash Index changed to: **tail risk event**" — state word colored)
  - sub-row: `$66,432 · ▼4.61% (24h) · Impulse negative · 14:30 UTC`
  - click → scrolls to the relevant dashboard card (anchor)
- **Filter chips** across the top (All / Flash / Structure / Risk / Allocation),
  CSS-only like the macro dashboard's tooltips — no JS framework.
- **Freshness indicator**: "Last evaluation: <ts of last sentinel/daily run that
  pushed>" — sourced from run_status.json; never fake a live websocket.
- Timeline section shows last ~30 days; full history paginated on a
  `vector-alerts.html` subpage (same pattern as history.html).
- Each `structure_shift` entry renders a mini annotation like their chart:
  "53 days since last bearish episode".
- Daily brief gets an "Alerts (last 24h)" block.

## 4. Build staging

- **Phase 1 (collectors)**: add Coinbase hourly-candle backfill + daily append
  (needed for flash-crash calibration later). Zero alert logic.
- **Phase 2 (signals + calibration)**: calibrate state-machine thresholds on
  2016→2026 hourly history against known crash episodes; publish hit/false-alarm
  table in tooltips (house rule).
- **Phase 3 (alerts + timeline)**: sentinel workflow, alert log, Telegram wiring,
  timeline UI. Risk: Actions cron jitter — measure actual cadence for a week and
  print it honestly in the timeline footer.
