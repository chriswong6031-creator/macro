# Flow Intelligence v2 — detection engine + calibrated scoring (spec of record)

Status: DESIGN RULING (Fable, 2026-07-09). Supersedes flow_score_v1's tier semantics.
Trigger: operator report "Elite 90+ is empty … add a comprehensive and groundbreaking
analysis engine that is able to detect unusual flow and flow that is extremely useful."

## 1. Why v1's tiers are empty (measured, not guessed)

flow_score_v1 (terminal `lib/flowScore.ts`) is client-side, transparent, and honestly
weighted — but its tier cutoffs (ELITE ≥90, STRONG ≥80) were never calibrated against
the real joint distribution. Measured on the full 2026-07-08 session (n=2,000 events,
the prod feed):

    max=74  p99=68  p98=66  p95=63  p90=60  median=50  |  ≥80: 0 events  ≥90: 0 events

A ≥90 score requires simultaneously: premium ≥$5M, z≥4, 1–45 DTE, vol>OI, ATM, and a
repeated cluster — a joint event that essentially never occurs. ELITE and STRONG are
*structurally* empty; the dev fixture masked it. Lesson (standing law from the 3/10
pass): fixtures must mirror prod pathologies — and now also: **tier cutoffs must be
derived from measured distributions, not aspiration.**

## 2. Design tenets

1. **Never structurally empty, never fake-full.** Tiers come from measured trailing
   percentiles (data-side thresholds), with absolute floors so a dead tape can't
   manufacture "Elite".
2. **Detection > scoring.** A single composite hides more than it reveals. v2 leads
   with deterministic, named detections (badges) and uses the score for ranking.
3. **Honesty is the differentiator.** Direction stays a soft lean (tick-rule 0.41, no
   NBBO). Multi-leg detection *discounts* directional reads instead of shouting them —
   the classic retail-flow-service failure is reading spread legs as naked conviction.
4. **Feedback loop.** The genuinely novel part: next-day OI confirmation tells the user
   which of yesterday's flow was real positioning. No competitor closes that loop.
5. **LLM-free.** Every detector is a deterministic rule on tape fields. Display-tier;
   no market-outcome claims; the word "validated" never appears.

## 3. Scoring v2 (two layers)

- **Quality score q (0–100)** = v1's component sum, unchanged weights (they are sane;
  the *cutoffs* were the flaw). Components remain user-visible in the inspector.
- **Salience tier** = percentile of q within the trailing 5 sessions' event population,
  computed data-side and shipped as thresholds:

```json
"thresholds": { "elite_q": 66, "strong_q": 60, "high_q": 55, "medium_q": 48 }
```

  ELITE = top ~2% AND premium ≥$1M; STRONG = top 10%; HIGH = top 25%; MEDIUM = top 50%.
  Client maps q → tier via thresholds; UI label becomes "Elite (top 2% of tape)" — the
  "90+" copy dies. Thresholds update nightly (trailing 5 sessions, so day-one quirks
  don't whipsaw tiers intraday).

## 4. Detection grammar (flow.enrich/v1 badges — all deterministic)

| Badge | Rule (exact) | Read |
|---|---|---|
| MULTI_LEG | same root, prints within ≤60s, 2+ strikes or both rights, leg size ratio ≤1.25× | direction DISCOUNTED (spread, not naked) |
| LADDER | same root+right, ≥3 distinct strikes, same direction of lean, within 30 min | staged accumulation |
| REPEAT_HITTER | same OCC contract in ≥3 separate events this session | conviction re-load |
| SIZE_VS_OI | event size ≥ 2 × OI[t-1] of that contract | size can't hide — new positioning |
| WHALE | single-event premium ≥ $1M | keep from v1 |
| FRESH | vol_gt_oi true | keep from v1 |
| Z_OUTLIER | root-level prem_z ≥ 2 (already in feed meta) | root is running hot vs 252d self |
| OI_CONFIRMED (t+1) | contract appears in `options_hub/oi_confirmed.json` next morning | yesterday's flow that actually built OI — the feedback lens |
| EARNINGS_WINDOW (optional) | root reports within ±5 sessions, from an existing PIT-clean source in the repo (builder scouts `mastermind_context` earnings block); if no clean source, SKIP honestly | event risk context |
| IV_ENTRY (phase 2) | premium paid with root's EOD IV in top quartile of its 1y range (theta store nightly join) | paying up for vol |

Every badge carries a one-line `why` string (EN/ZH) rendered in the inspector.

## 5. Architecture — enrichment overlay, zero poller changes

New sibling job `com.mastermind.flowenrich` (5-min RTH cadence offset ~90s after poller
cycles, flow-ops-wt pattern, fail-soft): reads `live_flow/feed_current.json` from R2,
runs cross-event detectors + threshold table, publishes:

```json
R2: live_flow/enrich_current.json
{ "schema": "flow.enrich/v1", "asof": "...", "session_date": "YYYY-MM-DD",
  "thresholds": { "elite_q": 66, "strong_q": 60, "high_q": 55, "medium_q": 48 },
  "events": { "<event id>": { "badges": ["MULTI_LEG","WHALE"],
               "q_pctl": 0.97, "direction_discounted": true } },
  "confirmed_yesterday": [ { "id": "...", "root": "...", "contract": "...",
               "oi_change": 12345 } ] }
```

The nightly hub lane (16:45 ET) recomputes thresholds from trailing 5 sessions and does
the OI-confirmation join for the completed session. The engine module lives in
`engine/flow_enrich.py` (pure functions + tests); the job script only does I/O.
Poller untouched. Feed absent/stale → job logs + republishes last good with honest asof.

Terminal joins by event id: tier from thresholds, badges on cards, a **Detections
filter lens** (filter by badge), Elite preset reads the tier. Graceful absent-file
fallback: v1 behavior with v1 labels removed ("top of tape" copy, no fake tiers).

## 6. Sequencing

1. **Lane H (macro)**: `engine/flow_enrich.py` + job + plist + nightly threshold/OI
   pass. Independent of running pass-4 lanes.
2. **Lane I (terminal)**: AFTER pass-4 lane C merges (same files): P0s first — PRISM
   40-depth scroll containment, GEX open-at-spot (third attempt: root-cause on the
   PROD data path incl. SWR-cache-hit timing, not fixture) — then the v2 UI (tier
   mapping, badges, Detections lens, inspector why-strings, EN/ZH).
3. Chain-heat publisher ships separately (already dispatched — P0 heal).

## 7. What "groundbreaking" cashes out to vs MomoEdge

They ship a 0–10 intensity score + sweep/whale badges on a paid NBBO tape. We cannot
buy direction (no NBBO) — so v2 wins on what direction-blind data CAN prove: multi-leg
honesty (they mislabel spread legs as naked flow), the t+1 OI-confirmation feedback
loop (nobody closes it), percentile-calibrated tiers that mean something ("top 2% of
tape" beats an uncalibrated 90+), and full component+badge transparency in the
inspector. Magnitude-first, direction-as-lean stays the house read.
