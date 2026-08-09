# Prophet US — admission-gate counterfactual replay

> **2026-08-09 revalidation:** current-main gate reconstruction still passes its equality
> control (zero LIVE / not-topped / FRESH4 mismatches across 139,948 sampled cells). The full
> output is not byte-reproducible, however: the live local Yahoo inventory moved from 741 files
> / 713 graded names to 751 / 732, and previously absent exhibit names became available. The
> historical tables below remain a frozen display-tier receipt, not current cohort evidence.
> Do not regenerate or promote their rates until the instrument binds an immutable universe and
> source-content manifest; the equality PASS validates gate algebra, not metric stability.

**MEASUREMENT ONLY — no engine, config, gate or board change follows from this file. Display tier under house epistemics; a null here blocks nothing**
Frozen pin `REPRO_ASOF = 2026-08-06` · window `2025-11-17 → 2026-08-06` (180 sessions) · runtime 58.4s · generated from `research/prophet_us_audit/gate_counterfactual_replay.py`

## 0. Equality gate (this instrument vs the engine)

`PASS` — 123,685 cells over 30 names (deterministic seeded sample). LIVE eligible mismatches **0**, not_topped mismatches **0**, FRESH4 eligible mismatches **0**. Non-zero would mean the re-derivation is not the gate and every table below is void.

## 1. Definitions (all stated, none inferred)

- **window** — the last 180 trading sessions of the shared session calendar ending at REPRO_ASOF
- **admission** — a name-day on which tier_stream assigns a tier — i.e. `eligible` is True — under the variant's gate. Identically: not_topped_VARIANT & tier_reachable
- **tier_reachable** — t1_fresh | t2_active | t3_active | t4_active — computed WITHOUT any reference to a veto leg (engine/confluence_tiers.py l.684-707)
- **excess** — excess := (name close-to-close return over the next 10 sessions) minus (SPY return over the same 10 sessions), in percentage points
- **precision** — P(excess >= +8.0pp | admission day) — STATED, inclusive bound
- **loser_rate** — P(excess <= -3.0pp | admission day) — STATED, inclusive bound
- **lateness_runup** — 100 * (close / min(close over the 10 sessions STRICTLY prior) - 1), in percent, on the admission day. Higher = the gate arrived later into an already-extended move
- **deep_base_state** — min(k3_d, d3_d) <= 20 at ANY point in the last 7 sessions (3D StochRSI %K/%D mapped to daily, the engine's own k3_d/d3_d) AND close >= its own close 5 sessions ago (turning up). In that state variant (c) waives all three veto legs; outside it all three apply exactly as live
- **scored_denominator** — an admission day is SCORED iff the frame carries 10 forward sessions for it. That is a TIME truncation — a function of the calendar alone, identical across all five variants, and it cannot know which way a trade went. Admission days it excludes are counted and PRINTED as `unscorable_no_forward`, never silently dropped
- **per_name_first** — the metric is computed inside each name, then the median is taken across names — one vote per name. Printed BESIDE the pooled cell, which is dominated by whichever names sit in a state for weeks
- **thin** — a cell with n < 20 is labelled thin and is a directional read only

**Variants.** `LIVE` the shipped gate: fresh_ticks=2, not_topped = ~(stoch_ob|stoch_bear|macd_bear) · `NO_MACD` macd_bear dropped; stoch_ob and stoch_bear still veto · `BASE_STATE_CONDITIONED` all three legs apply EXCEPT in the deep-base state (see definitions.deep_base_state), where all three are waived · `FRESH4` fresh_ticks 2 -> 4 (tier_stream's own knob); vetoes unchanged · `NO_STOCHBEAR_MACD` stoch_bear AND macd_bear dropped; stoch_ob kept — the pure anti-extension guard alone

**Universe.** `site/factordata/us_standouts.json`'s `universe` field is `1586` — NOT enumerable — the field is an integer COUNT, not a ticker list, so the brief's fallback rule applies. Used instead: every data/yahoo/*.parquet with >= 200 daily closes at REPRO_ASOF → 713 of 741 files (28 dropped). NO SUBSET — the universe fits the runtime budget. Board as-of on that file: 2026-08-06.

**Coverage nulls (printed, not hidden).** 0 of 713 names sit below the engine's MIN_HISTORY and are gradable by NO variant. 0 names carry fewer than 232 bars, so `macd_bear` fails open there — a name with < 232 daily bars has a NaN 3D RSI-MACD, and `macd_bear = m3n < s3n` reads False on NaN — the leg cannot FIRE there, so LIVE and NO_MACD are identical for those names by construction, and the NO_MACD delta is carried entirely by the warm names. The last 10 sessions of the window carry no H=10 forward, so admissions on them are counted and reported as `unscorable`, never dropped from a numerator alone.

**Gate pressure.** 31,910 name-days reached a tier in the window; 19,277 of them (60.4%) were vetoed by the live not-topped triple.

## 2. Variant metrics

Pooled cells. `adm/day` = admission name-days per session; `prec` = P(excess ≥ +8pp); `loser` = P(excess ≤ -3pp); `run-up` = median lateness over ALL admission days; `names` = distinct names admitted; `unscored` = admission days with no H=10 forward in the frame.

| variant | adm/day | names | adm-days | scored | unscored | prec % | loser % | median excess pp | run-up % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `LIVE` | 70.18 | 708 | 12633 | 11851 | 770 | 14.3 | 32.6 | -0.06 | 6.9 |
| `NO_MACD` | 129.05 | 711 | 23229 | 21911 | 1304 | 13.4 | 33.7 | -0.35 | 6.7 |
| `BASE_STATE_CONDITIONED` | 116.24 | 711 | 20924 | 19650 | 1260 | 13.3 | 33.9 | -0.35 | 7.4 |
| `FRESH4` | 78.72 | 708 | 14170 | 13271 | 887 | 14.5 | 32.6 | -0.08 | 6.5 |
| `NO_STOCHBEAR_MACD` | 148.04 | 711 | 26648 | 25175 | 1459 | 13.4 | 33.7 | -0.32 | 6.3 |

Per-name-first cells (each name votes once) and the delta against LIVE.

| variant | names scored | prec % (pnf) | loser % (pnf) | median excess pp (pnf) | run-up % (pnf) | med adm-days/name | Δ prec pp | Δ loser pp | +name-days | −name-days | +names | thin |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `LIVE` | 707 | 7.4 | 27.8 | 0.35 | 7.6 | 18 | — | — | — | — | — |  |
| `NO_MACD` | 709 | 9.3 | 32 | -0.16 | 7.1 | 32 | -0.9 | 1.1 | 10596 | 0 | 707 |  |
| `BASE_STATE_CONDITIONED` | 709 | 8.8 | 31.8 | -0.3 | 7.6 | 29 | -1 | 1.3 | 8291 | 0 | 703 |  |
| `FRESH4` | 707 | 8.3 | 27.8 | 0.37 | 7.2 | 18 | 0.2 | 0 | 1537 | 0 | 334 |  |
| `NO_STOCHBEAR_MACD` | 709 | 10 | 31 | -0.26 | 6.6 | 37 | -0.9 | 1.1 | 14015 | 0 | 708 |  |

## 3. The 14-name exhibit

the 14 names are an EXHIBIT, not a cohort — 14 names cannot carry a verdict and none of their numbers enters section 1. Names outside the graded universe are priced off the source printed on their row; two lineages are not one series.

First admission date inside the window per name × variant. `—` = no admission under that variant.

| name | source | bars | status | LIVE | NO_MACD | BASE_STATE | FRESH4 | NO_SB_MACD |
|---|---|---:|---|---|---|---|---|---|
| **SBSW** | ABSENT | — | ABSENT | n/a | n/a | n/a | n/a | n/a |
| **NEM** | data/yahoo | 3167 | graded | 2025-12-17 | 2025-12-04 | 2025-11-28 | 2025-12-17 | 2025-11-28 |
| **HL** | data/midcap_breadth/_closes_cache.parquet | 777 | graded | 2025-12-17 | 2025-12-17 | 2025-12-17 | 2025-12-17 | 2025-12-17 |
| **FSM** | ABSENT | — | ABSENT | n/a | n/a | n/a | n/a | n/a |
| **CDE** | data/midcap_breadth/_closes_cache.parquet | 55 | UNDER MIN-HISTORY | n/a | n/a | n/a | n/a | n/a |
| **GDX** | data/yahoo | 5084 | graded | 2025-12-17 | 2025-12-01 | 2025-11-25 | 2025-12-17 | 2025-11-25 |
| **AG** | ABSENT | — | ABSENT | n/a | n/a | n/a | n/a | n/a |
| **PAAS** | ABSENT | — | ABSENT | n/a | n/a | n/a | n/a | n/a |
| **EXK** | ABSENT | — | ABSENT | n/a | n/a | n/a | n/a | n/a |
| **SPCX** | data/yahoo | 38 | UNDER MIN-HISTORY | n/a | n/a | n/a | n/a | n/a |
| **RKLB** | data/yahoo | 1430 | graded | 2025-12-12 | 2025-12-04 | 2025-12-04 | 2025-12-12 | 2025-12-04 |
| **ASTS** | data/yahoo | 1698 | graded | 2025-12-12 | 2025-12-04 | 2025-12-04 | 2025-12-12 | 2025-12-04 |
| **MRNA** | data/breadth/_closes_cache.parquet | 349 | graded | 2026-06-16 | 2026-04-16 | 2026-04-16 | 2026-06-16 | 2026-04-16 |
| **CRCL** | data/yahoo | 294 | graded | 2026-02-13 | 2026-02-13 | 2026-02-13 | 2026-02-13 | 2026-02-13 |

**Names the gate could never see.**
- `SBSW` — ABSENT — no close series on disk in data/yahoo, data/stocks or any production closes cache; NOT gradable, and no network read is permitted in this instrument.
- `FSM` — ABSENT — no close series on disk in data/yahoo, data/stocks or any production closes cache; NOT gradable, and no network read is permitted in this instrument.
- `CDE` — UNDER MIN-HISTORY — 55 daily bars < engine MIN_HISTORY 159; tier_stream returns an EMPTY frame, so NO variant can admit this name. The gate never saw it.
- `AG` — ABSENT — no close series on disk in data/yahoo, data/stocks or any production closes cache; NOT gradable, and no network read is permitted in this instrument.
- `PAAS` — ABSENT — no close series on disk in data/yahoo, data/stocks or any production closes cache; NOT gradable, and no network read is permitted in this instrument.
- `EXK` — ABSENT — no close series on disk in data/yahoo, data/stocks or any production closes cache; NOT gradable, and no network read is permitted in this instrument.
- `SPCX` — UNDER MIN-HISTORY — 38 daily bars < engine MIN_HISTORY 159; tier_stream returns an EMPTY frame, so NO variant can admit this name. The gate never saw it.

**Admitted cells — what the name actually did.** `max fwd10` = the best 10-session forward return from any admission day under that variant; `excess` is against SPY.

| name | variant | first admission | adm-days | run-up at first % | max fwd10 % | max fwd10 excess pp | unscored |
|---|---|---|---:|---:|---:|---:|---:|
| NEM | `LIVE` | 2025-12-17 | 20 | 11.7 | 7.8 | 6.2 | 8 |
| NEM | `NO_MACD` | 2025-12-04 | 57 | 11 | 17.8 | 17.4 | 9 |
| NEM | `BASE_STATE_CONDITIONED` | 2025-11-28 | 45 | 11 | 11.9 | 12.8 | 9 |
| NEM | `FRESH4` | 2025-12-17 | 21 | 11.7 | 7.8 | 6.2 | 9 |
| NEM | `NO_STOCHBEAR_MACD` | 2025-11-28 | 71 | 11 | 17.8 | 17.4 | 9 |
| HL | `LIVE` | 2025-12-17 | 18 | 22.5 | 13.2 | 11.6 | 0 |
| HL | `NO_MACD` | 2025-12-17 | 34 | 22.5 | 13.2 | 11.6 | 0 |
| HL | `BASE_STATE_CONDITIONED` | 2025-12-17 | 33 | 22.5 | 13.2 | 11.6 | 0 |
| HL | `FRESH4` | 2025-12-17 | 21 | 22.5 | 13.2 | 11.6 | 0 |
| HL | `NO_STOCHBEAR_MACD` | 2025-12-17 | 43 | 22.5 | 33.5 | 33.7 | 0 |
| GDX | `LIVE` | 2025-12-17 | 15 | 8.4 | 11.9 | 7.7 | 7 |
| GDX | `NO_MACD` | 2025-12-01 | 42 | 13.5 | 11.9 | 8.8 | 7 |
| GDX | `BASE_STATE_CONDITIONED` | 2025-11-25 | 34 | 6.6 | 11.9 | 7.7 | 7 |
| GDX | `FRESH4` | 2025-12-17 | 18 | 8.4 | 11.9 | 7.7 | 10 |
| GDX | `NO_STOCHBEAR_MACD` | 2025-11-25 | 47 | 6.6 | 11.9 | 8.8 | 7 |
| RKLB | `LIVE` | 2025-12-12 | 12 | 52.3 | 40.8 | 38.8 | 0 |
| RKLB | `NO_MACD` | 2025-12-04 | 30 | 25.1 | 50.4 | 49.9 | 2 |
| RKLB | `BASE_STATE_CONDITIONED` | 2025-12-04 | 30 | 25.1 | 50.4 | 49.9 | 2 |
| RKLB | `FRESH4` | 2025-12-12 | 15 | 52.3 | 40.8 | 38.8 | 0 |
| RKLB | `NO_STOCHBEAR_MACD` | 2025-12-04 | 32 | 25.1 | 50.4 | 49.9 | 2 |
| ASTS | `LIVE` | 2025-12-12 | 18 | 45.8 | 39.4 | 37.9 | 0 |
| ASTS | `NO_MACD` | 2025-12-04 | 43 | 43.3 | 39.4 | 37.9 | 2 |
| ASTS | `BASE_STATE_CONDITIONED` | 2025-12-04 | 48 | 43.3 | 45 | 43.7 | 2 |
| ASTS | `FRESH4` | 2025-12-12 | 21 | 45.8 | 39.4 | 37.9 | 0 |
| ASTS | `NO_STOCHBEAR_MACD` | 2025-12-04 | 54 | 43.3 | 45 | 43.7 | 2 |
| MRNA | `LIVE` | 2026-06-16 | 6 | 21.4 | 34.4 | 34 | 0 |
| MRNA | `NO_MACD` | 2026-04-16 | 20 | 12.1 | 39.7 | 39.5 | 0 |
| MRNA | `BASE_STATE_CONDITIONED` | 2026-04-16 | 19 | 12.1 | 39.7 | 39.5 | 0 |
| MRNA | `FRESH4` | 2026-06-16 | 6 | 21.4 | 34.4 | 34 | 0 |
| MRNA | `NO_STOCHBEAR_MACD` | 2026-04-16 | 20 | 12.1 | 39.7 | 39.5 | 0 |
| CRCL | `LIVE` | 2026-02-13 | 6 | 19.5 | 82.8 | 83.4 | 0 |
| CRCL | `NO_MACD` | 2026-02-13 | 12 | 19.5 | 82.8 | 83.4 | 4 |
| CRCL | `BASE_STATE_CONDITIONED` | 2026-02-13 | 10 | 19.5 | 82.8 | 83.4 | 2 |
| CRCL | `FRESH4` | 2026-02-13 | 10 | 19.5 | 92.4 | 93.9 | 0 |
| CRCL | `NO_STOCHBEAR_MACD` | 2026-02-13 | 14 | 19.5 | 82.8 | 83.4 | 4 |

**Near-miss attribution for the `—` cells** — the most recent session in the window on which a tier was reachable, and the veto legs firing there.

(none — every graded name admitted under every variant inside the window; the `—` case did not occur. The seven n/a rows above are ABSENT/UNDER-MIN-HISTORY, attributed name-by-name in the list that precedes this table.)

## 4. Reading rules

- Nothing here promotes anything. Under house epistemics the gauntlet is a PROMOTION gate, not a build gate; these are display-tier measurements and a null blocks nothing.
- Denominators are TIME-truncated, never outcome-truncated. Admission days without an H=10 forward are counted in `unscored` and excluded from BOTH the numerator and the denominator of every rate, identically across variants.
- Pooled cells double-count a name that sits in a state for weeks; read the per-name-first column beside them, and treat any row marked THIN as directional only.
- The 14 names are an exhibit. They enter no cohort statistic.

Raw: `research/prophet_us_audit/GATE_COUNTERFACTUAL_2026-08-07.json`
