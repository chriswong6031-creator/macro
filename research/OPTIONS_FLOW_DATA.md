# Options flow — data access, entitlements, and the measured-dealer architecture

_Empirically probed 2026-06-21 against the live massive.com account. These are hard facts
(GET/REST entitlement tests), not vendor marketing._

## What our massive.com plan actually grants

| Data | REST | S3 flat-file | Status |
|---|---|---|---|
| Options **snapshot** (OI, IV, per-contract Δ/Γ, day vol) | ✅ 200 | — | **entitled** |
| Options **minute aggregates** (per-contract OHLCV+vol+txns, ~18 MB/day) | — | ✅ GET OK | **entitled** (window ~2025→present) |
| Options **day aggregates** (~3 MB/day) | — | ✅ GET OK | **entitled** (~2025→present) |
| Stock **day aggregates** | — | ✅ GET OK | entitled |
| Options **per-trade tape** (`trades_v1`) | ❌ 403 | ❌ 403 | **NOT entitled** |
| Options **NBBO quotes** (`quotes_v1`, ~107 GB/day) | ❌ 403 | ❌ 403 | **NOT entitled** (also a firehose) |
| Real-time stream | ❌ | — | not entitled |

S3: `files.massive.com`, bucket `flatfiles`, creds in env `MASSIVE_S3_*`. Listing is open
across all datasets; **GET is entitlement-gated per dataset AND time-windowed** (recent
aggregates only). The error on gated data points to `massive.com/pricing`.

## Procurement answer

- **A genuinely institutional EOD flow desk needs $0 of new spend.** It is buildable on the
  aggregates + snapshots we already have.
- **True trade-level signing** (Lee-Ready from the NBBO, real sweep/block detection) needs the
  trades+quotes tape we lack. Cheapest path: **Databento `tbbo`** (each trade stamped with the
  prevailing NBBO), pay-as-you-go, **~$0 under the $125 signup credit** for a focused universe.
- Recurring subscriptions (Massive Developer ~$79–99/mo, ThetaData ~$80–160/mo realtime) buy
  only latency/convenience — defer until the product goes intraday/live. Turnkey products
  (Unusual Whales etc.) mostly resell the same OPRA tape with a UI + the same dealer-sign
  heuristic we now own outright; skip for the build.

## Architecture (what we built on the free data)

- `collectors/massive_flatfiles.py` — S3 reader for the minute/day option aggregates
  (universe-aware cache; graceful 403/no-creds → empty).
- `engine/options_flow.py` — **MEASURED dealer positioning**: signs each minute's per-contract
  volume by the option's own minute-close tick (the honest fallback with no NBBO), infers the
  dealer side as the opposite of net customer flow, and emits measured dealer Γ/Δ FLOW + net
  signed premium + signed P/C + 0DTE concentration + Vol>OI new-positioning + the
  **divergence-from-assumption** (strikes where measured flow disagrees with the
  long-call/short-put assumption the GEX map uses).
- `scripts/build_options_flow.py` — daily desk → `site/flow/<KEY>.json` + manifest +
  `mastermind.json`; accrues `data/options_flow/summary_*`.
- gex.html — a "📊 Today's measured flow" card on each name's panel.

## Calibration result (Databento tcbbo, 2026-06-21)

Pulled a cost-guarded 20-min SPY slice via Databento `tcbbo` (trade + consolidated NBBO) —
**101,934 real trades, $1.60, cached** — and signed it two ways (`scripts/calibrate_flow_signing`):

- **Per-trade tick-rule vs NBBO quote-rule agreement: 0.777** (size-weighted 0.808) — exactly
  the literature's ~0.77–0.84.
- **Minute net-sign recovery: 0.41** — BELOW a coin flip.

**Why, and what it means (the important finding):** an option's minute-to-minute price ticks
are dominated by the underlying's **delta-driven** move, not by buy/sell pressure, so the tick
rule mis-signs net DIRECTION on bar data. Therefore:

- The flow **DIRECTION** (net signed premium, signed P/C, dealer γ-flow SIGN) is **SOFT** —
  shown dashed/`~` in the UI, labeled with the measured accuracy, never colored strongly.
- The flow **MAGNITUDE / positioning** (gross premium, volume, P/C, 0DTE share, Vol>OI fresh
  positions, gamma EXPOSURE) needs **no signing** and is **reliable**. The engine verdict LEADS
  with these.
- `data/options_flow/signing_gate.json` carries `direction_reliable:false / magnitude_reliable:true`;
  `engine/options_flow` reads it and frames the payload accordingly.

**Delta-adjustment was TESTED and REJECTED.** The obvious fix — sign by the residual after
removing the underlying's delta move (Δoption − delta·Δunderlying, using the stock minute aggs
we're entitled to + BS delta) — was validated against the Databento NBBO truth on two samples:

| Test | Tick-rule | Delta-adjusted |
|---|---|---|
| 20-min cross-section (1,167 contracts) | 0.41 | 0.39 |
| Full RTH day, 13 non-0DTE contracts, 4,889 minute-obs | 0.556 | 0.526 (net recovery 0.62 = 0.62) |

It does **not** beat the plain tick rule. Reason: on both affordable test days the underlying
barely moved (2026-06-18: SPY +0.48 all session), so delta-drift was negligible and the
dominant noise is **bid-ask bounce** — the minute close is a random draw from bid/ask, which
delta-adjustment cannot fix. A model-midpoint (level-space) rule looked better on net recovery
(0.69) but its per-trade agreement vs the quote rule was only 0.48 — i.e. the apparent gain was
a spurious artifact of IV drifting up on a net-buying day, not genuine signing. `delta_adjusted_sign`
is kept as a labelled building block (it should help on high-underlying-move days), but production
signs with the plain tick rule and labels DIRECTION soft. **Reliable direction requires the
trade-level NBBO tape (paid)** — there is no $0 bar-only path. Total Databento spend to settle
this: ~$3.56 (the full-day per-name pull would be ~$19 because 0DTE contracts are huge).

## The calibration gate (Databento, opt-in)

- `engine/flow_signing.py` — pure tick-rule vs quote-rule signing + the calibration math.
- `collectors/databento_tbbo.py` — pulls a tbbo sample (INERT until `DATABENTO_API_KEY` +
  `pip install databento`).
- `scripts/calibrate_flow_signing.py` — measures per-trade agreement AND, the decision-relevant
  metric, whether the MINUTE tick rule recovers the same NET daily sign per contract as full
  NBBO signing → `data/options_flow/signing_gate.json` + `reports/flow-signing-calibration.md`.

## Honest limits (carried in every payload)

- Tick-rule signing is APPROXIMATE (~77–83% per-trade vs ~81–84% full Lee-Ready; errors roughly
  symmetric so they wash in daily aggregates) — weakest on illiquid / wide-spread / deep-ITM /
  sparse-0DTE strikes. EOD/T+1, not intraday-live. Display/context until the calibration gate
  passes; never a stand-alone buy/sell. No FINRA off-exchange ("dark pool") equity prints (not
  in OPRA). 0DTE read is EOD-aggregated, so it lags the true intraday picture.
