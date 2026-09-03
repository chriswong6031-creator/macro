# R3 Materiality Contract V1 — Live Risk Envelope (first vertical)

**Program:** `modernize-mastermind-architecture-20260830-sol-001` · completion operation `modernize-mastermind-reactive-production-completion-20260901-fable-001`
**Selection (2026-09-02, COO Fable, from owner archaeology):** the R3 "materiality-gated live assessment" requirement is satisfied by NAMING and CONTRACT-FREEZING the existing **GD-3 live risk envelope** vertical — not by building a new one. The estate already runs the chain; R3's law (freeze §8 Layer C) demands the chain be *named, fielded, and production-proven*, which this record does. Grey Deer (`WS:GREY-DEER` program owner) retains code ownership; this record adds NO producer, NO trigger plane, NO authority.

## Why this vertical (evidence-ranked)
- Real intraday evidence change through an existing lane: VIX/VIX3M/VIX9D/MOVE legs splice live every ~30 min RTH (`scripts/build_risk_state.py` `_live_vix_term` ~:184-193, `source_event_time` ~:309; `.github/workflows/intraday-fastpath.yml:21` cron `*/30 11-21 * * 1-5`).
- A working materiality/hysteresis machine on that evidence: `scripts/build_live_risk_envelope.py` `_DEBOUNCE_TICKS_DEFAULT = 3` (:119), `_dwell_state()` (:383-457) — escalation/de-escalation accepted only after N **distinct** confirming observations (fires ≠ observations), freeze-on-repeat, re-baseline-on-new-session; minute-cadence host lane (`scripts/vps_live_orchestrator.py:298-346`, weekdays 11-22 UTC).
- A real consumer already live: `templates/risk_envelope_live.js` + `templates/_risk_envelope_band.html.j2` render `site/live/risk_envelope.json` on-page.
- Rejected alternatives: economic-release assessment (no intraday lane exists today — `scripts/build_release_forecast.py` is nightly-only with a release-day *grading* sweep at :2138; the recompute owner would have to be invented, violating extend-don't-invent); hot-tape radar (5-min live detector, but a marketing/social organ, not an assessment).

## The frozen contract (freeze §8 Layer C field list)
| Field | Binding value (existing code, by name) |
|---|---|
| Canonical producers | `scripts/build_risk_state.py` (evidence assembler; live VIX-family splice) → `engine/risk_envelope.py::compose_envelope` via `scripts/build_live_risk_envelope.py` (GD-3 recompute) |
| Real consumers | `site/live/risk_envelope.json` → `templates/risk_envelope_live.js` / `_risk_envelope_band.html.j2` (product); Grey Deer reads (machine) |
| Input fingerprint | the DISTINCT-observation key `_dwell_state` already discriminates: `risk_state.json`'s `observed_built` identity for the spliced live legs (`live.source_event_time` + leg values). GAP-1 below makes the hash explicit in the firing record. |
| Materiality predicate | candidate hazard-stage differs from published stage AND precedence=="live" AND live_active AND the observation is DISTINCT (`_dwell_state` gate) |
| Hysteresis / debounce | `_DEBOUNCE_TICKS_DEFAULT = 3` distinct confirmations (~6 min at the odd-minute refresh cadence); freeze-on-repeat; session re-baseline |
| Clocks | source/market time = `live.source_event_time` (quote_ts); recompute/publish time = envelope build stamp; baseline = nightly `build_risk_envelope.py` as-of. Request time never freshens anything. |
| Null / degraded | precedence ladder live→nightly (composer refuses live when inputs unfit; breadth/liquidity remain nightly_asof by design — `build_risk_state.py:348` — and are never faked live) |
| Correction | a later distinct observation with changed values supersedes through the same dwell gate; nightly settle re-baselines the canonical record (nightly remains the forward-ledger advancer) |
| Method | deterministic composition + deterministic dwell machine; zero LLM in the loop |
| Authority class | display/context instrument (instrument-verdict law: a state read is never a market verdict; no rank/size/gate authority; Prophet/entry untouched) |
| SLO | producer cadence ≤30 min RTH for evidence, ≤2 min recompute reaction (minute lane) when material; envelope publish visible on-page next fetch |
| Telemetry | orchestrator per-module latency (`vps_live_orchestrator.py:279`), coverage validators (:89-131), `engine/neuralweb/reflexes.py::record_firing` ledger precedent (GAP-1 routes the materiality firing through it) |

## Gaps to close before R3 is claimed complete (bounded, owner-safe)
- **GAP-1 (small code, Grey-Deer-coordinated):** emit one `record_firing("risk_envelope_materiality", …)` row per accepted dwell transition, carrying the explicit input-fingerprint hash (sha256 of the distinct-observation key) + stage-from/to + clocks — making trigger firings a durable, auditable ledger rather than implicit state. Single module touch in `build_live_risk_envelope.py`; no behavior change to the dwell law itself.
- **GAP-2 (proof, no code):** one production receipt of the full chain on a genuine session: material VIX-leg change → fastpath tick updates `risk_state.json` → dwell machine accepts after N distinct observations → envelope stage recomputes and publishes → live band updates → clocks honest → a degraded case visibly falls to nightly precedence → zero authority fingerprints move. Target: session 2/3 of the acceptance window (2026-09-03/04).

## Non-goals
No new trigger/scheduler plane; no second risk producer; no LLM assessment; no cadence change to Grey Deer's lanes; no release-forecast intraday build (recorded as R3-candidate-2, deliberately not built until a real owner emerges).
