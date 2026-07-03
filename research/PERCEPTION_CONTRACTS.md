# Perception contracts — machine-consumable data-plane conventions (2026-07-02)

Origin: the 2026-07-02 semis-breakdown incident (Mastermind
`research/incidents/2026-07-02-semis-breakdown/` + handoff spec
`research/eyes/dashboard_spec.md`). Every "all-clear" the books traded on was a
lagging or mislabeled artifact — Q1 from sign-vote democracy + hysteresis,
STABLE from a memoryless flag oscillator, "expanding" liquidity from base-effect
noise over an exhausted RRP, "risk receding" from the wrong scare fading — while
the dashboard's own radar had the right answer in a leg consumers couldn't see.
These contracts make what the dashboard already knows *legible to machines*.

## 1. Conventions (apply to every artifact below, and to all new contracts)

- **`asof`** — the TRUE data timestamp (last session of real data), never build
  time. Build time lives in `generated_utc` / `built_at` fields only. One
  spelling: `asof` (existing producers with `as_of` are read leniently by
  `scripts/build_feeds.py`, but new writers must emit `asof`).
- **`schema_version`** — integer, on every new contract object. Additive fields
  never bump it; renames/removals do (and renames are forbidden — add, never
  rename: `latest.json` consumers include books trading real money).
- **`degraded` / `degrade_reason`** — wrong data DEGRADES, never sharpens (P2).
  A missing input must widen distributions toward uniform / lower confidence /
  mark the object degraded. The inverse — missing data silently reading as
  full-confidence — is the exact `missing-stockdata → confluence=1.0` failure.
- **One source of truth per concept (P7)** — classification logic lives at the
  source engine; consumers read the published label and may recompute only as a
  fail-closed fallback when the field is absent.

## 2. The contracts shipped 2026-07-02 (handoffs H1–H6)

### H1 — transition ratchet (`engine/transition.py`, fields in `data/regime/latest.json`)
`transition_state` (headline enum, unchanged values) is now the RATCHETED read:
escalation instant, de-escalation one level per `clear_dwell_days` (5) clean
sessions, flag re-fire resets the countdown, `max_dwell_days` (15) auto-release.
Additive audit fields: `transition_state_raw` (the memoryless read, for A/B),
`transition_ratcheted` (bool), `transition_dwell_remaining` (int). New 7th flag
`transition_flags.flag_rotation_persistence` — cyc/def slope contra-quad for
`rotation_persist_days` (10) straight, a LEVEL condition that cannot roll off
mid-rotation. A `{cyclical_defensive, wei_trend}` contra-growth pair floors the
state at WEAKENING regardless of flag windows (`contradiction_floor`). Config:
`engine.transition.{ratchet_enabled, clear_dwell_days, rotation_persist_days,
max_dwell_days, contradiction_floor}` — dwell values `(unverified-prior)`.

### H2 — `latest.quad_vector` (`engine/quad_vector.py`)
The published continuous-P(Quad) contract. Probabilities are OWNED by the
hedgeye program (`engine/regime_one._causal_filtered_pquad`, causal filtered
HMM; `engine/regime_hmm` is the smoothed sibling) — this key only publishes the
stable consumer shape: `{schema_version, asof, p{Q1..Q4} (sums to 1), source,
hard_label, hard_label_agrees, confidence (= max(p) × axis agreement),
drivers{growth[], inflation[]} (signed per-leg contribs, slow legs flagged),
transition_momentum{gaining, gaining_rate, losing, losing_rate}, degraded,
degrade_reason}`. NOT named `next_quad_probs` — that key is taken twice by
historical Markov objects (`playbook.next_quad_probs`,
`regime_hmm.next_quad_probs`); do not overload. `hard_label ≠ argmax(p)` is a
legitimate state and a WEAKENING tell (shrink-only consumption, never a flip).

### H3 — `latest.liquidity_quality` (`engine/regime.liquidity_quality`) + top-level fields
`liquidity_overlay` (string) is UNCHANGED. The new quality plane classifies it:
`label ∈ {benign-expansion, stress-expansion, neutral, neutral-hollow,
contracting, unknown}` — `expanding` reclassifies to `stress-expansion` iff
RRP buffer exhausted (`rrp_bn < rrp_floor_bn`) OR the RoC composition is
mechanical (TGA/RRP-driven, `fed_share < benign_fed_share_min`) OR credit is
confirming (HY-OAS 20d-chg z ≥ `stress_oas_z`, or NFCI > 0 and tightening);
`neutral` splits to `neutral-hollow` when the buffer/composition is hollow.
Carries `quantity_roc_bn, rrp_buffer_bn, rrp_exhausted, composition{d_walcl,
d_neg_rrp, d_neg_tga, fed_share, mechanical}, stress_overlay{...},
walcl_stale_days, degraded`. Consumption is shrink-only: `stress-expansion`
may shrink an offensive budget, never un-cap one.
Also top-level in `latest.json`: `schema_version` (1), `asof` (== freshness.asof),
`flip_margin` (mirror of `flip_condition.margin`; null when the axis is mixed).

### H4 — the `feeds/` R2 plane (`scripts/build_feeds.py` → `site/feeds/` → R2 `feeds/`)
Flat dir, `_manifest.json` is the authoritative name list (publish_r2 grammar).
Artifacts: `risk_radar.json` (verbatim radar snapshot — the leg the bot's sparse
set stripped through the incident), `froth_fragility_log.jsonl`,
`dislocation_state_log.parquet`, `group_flow_validation_meta.json`,
`subsector_rotation.json` (the RRG plane, 268 subsectors × 8 timeframes),
`event_calendar.json` (first persistent artifact of engine/event_calendar),
`intl_spillover.json` (per-market risk_radar_intl snapshots cn/hk/ca),
`sector_breadth.json` (H5), `feeds_meta.json` (per-artifact asof + build stamp).
R2-only (gitignored, stripped from Pages); freshness-tripwired via the `feeds`
anchor in `config.yml:r2_data_plane.anchors`.

### H5 — per-sector breadth (`collectors/breadth.py:compute_sectors`)
`data/breadth/sector_breadth.parquet` (history; flat `<GICS sector>|pct_above_50
/ pct_above_200 / n` columns) + `feeds/sector_breadth.json` latest snapshot.
Closes the rotation-tensor breadth-migration gap: on 2026-07-01 this read
Financials 81 / Utilities 77 / Health Care 76 vs Energy 19 / Comm Svcs 27 /
Tech 51 — the defensive rotation the market-wide 55% hid.

### H6 — asof standardization
This document is the convention (see §1). New producers emit `asof`; the
`latest.json` top level now carries it.

### Incident §4 — one risk voice per page (`risk_radar.deescalation`)
`latest.risk_radar.deescalation = {eligible, reason, receding_scare,
dominant_velocity, drawdown_prob_h21, drawdown_prob_trend}` — the page's "risk
receding" verdict is DERIVED at the radar, and `engine/risk_radar_recovery`
renders green only when `eligible`. Suppression rule: dominant scare is
risk-off-flavored (growth/credit/rates/vol) AND the h21 pullback-odds trend is
rising (or the dominant sub-score itself still climbing). The panel may narrate
what IS fading (`receding_scare`) as context; it may not present an all-clear.
Threshold review knob (default false, owner decision):
`engine.risk_radar.cap_leadership_on_rotation_caution` — extends
`cap_leadership` to `caution` on a rising growth-rotation scare (the 07-01 tape).

## 3. Ship-blocker guards for the hedgeye P(Quad) engine (owner handoff)

The magnitude-weighting of axis votes was deliberately NOT patched into
`engine/axes.py` / `indicators.score_from_z` — a magnitude-weighted axis mean is
the raw material of a soft-quad score, and building it beside the hedgeye
program's continuous P(Quad) would create two sources of truth for "how bullish
is growth" (P7). The magnitude fix lands INSIDE the P(Quad) engine. Two guards
are ship-blockers there, or magnitude-weighting reintroduces the incident:

1. **Single-leg domination guard.** Cap each leg at
   `|w_i · clip(z_i/z_threshold, −M, +M)|` with **M = 1.5**, and require ≥ 2
   non-zero same-sign legs before |axis| may exceed its ±1-democracy value.
   No single deeply-trending leg (copper_gold at z=3) may flip the label.
2. **Fast/slow split.** The lagging monthlies (`payrolls_trend, indpro_trend,
   gdpnow_trend, wei_trend`) enter at decayed weight (×0.5) while
   `transition_state ∈ {WEAKENING, TRANSITIONING}` so market legs lead when the
   tape turns; and sticky-CPI's growth-relevant signal must be routed — rising
   sticky CPI with falling growth pulls mass toward Q3, which the hard-label
   architecture cannot express. (`quad_vector.drivers` already flags the slow
   legs so consumers can see the split today.)

Interim hedge until that lands: the contradiction floor (H1) forces ≥ WEAKENING
on the `{cyclical_defensive, wei_trend}` contra-growth pair.

## 4. Consumers

Primary: the Mastermind bot (`vendor/macro` sparse set + the R2 `feeds/`
manifest). But every field here is for ALL consumers — the site templates, the
regional books, the admin console. The bot degrades to its pre-contract
behavior when any field is absent (its masterplan guardrail 11); nothing here
is load-bearing for the dashboard render itself.
