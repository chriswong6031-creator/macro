---
key: LER-LIVE-LANE-VPS-5MIN-REST
question: >
  What cadence, compute plane, and market-data path does Live Entry Radar's intraday lane
  use — and does it open a vendor WebSocket?
answer: >
  A 5-minute VPS systemd timer (sibling of macro-live-prophet.{service,timer}, offset
  behind the :00/5 snapshot lane), with the GitHub workflow as a self-disabling backstop
  only. Market data is REST/snapshot only — Radar opens NO WebSocket. The live lane never
  recomputes indicators intraday: oscillator-state conditions are inverted nightly into
  per-name price thresholds (the armed_pack pattern), and the 5-min pass compares delayed
  snapshots to them plus derives path stats (session low, rebound-in-ATR). Payload =
  live/entry_radar.json via the MACRO_LIVE_DIR ladder, gated by omission from the Caddy
  allowlist; events spool to R2 (live_flow/entry_radar_events/**); the nightly reconciler
  is the sole durable writer, gated by ledger_lane.nightly_advance_enabled(). One-minute
  cadence is not pursued until research proves 5 minutes materially misses the turn.
rationale: >
  Every element reuses a measured, production-proven pattern (Track D census,
  research/live_entry_radar/TRACK_D_LIVE_PLANE_CENSUS.md): GitHub cron measured 90min-3h12m
  gaps on */5 schedules, so it cannot carry product cadence; the VPS prophet-live lane
  already runs this exact shape at 0.006s compute/95MB RSS against a 1,742-name pack; the
  Massive stocks WebSocket slot is unclaimed estate-wide and the vendor EVICTS THE OLDEST
  connection on overflow (TP-0.5 measured) — a silent-kill hazard with zero benefit at
  5-minute cadence; REST/snapshot is the pattern of every existing collector; and the
  threshold-inversion architecture (armed_pack: "the intraday lane never re-derives a
  signal") makes live bar math unnecessary while guaranteeing parity with confirmed-bar
  math by construction.
alternatives:
  - option: GitHub Actions cron as the product cadence
    why_not: "Measured 90min-3h12m firing gaps with ~58 workflows in-repo; prophet-live.yml's own header documents it as not purchasable at any price."
  - option: Open a Massive WebSocket for the Probe Set now
    why_not: >
      The single slot is unclaimed and overflow evicts the incumbent silently; singleton
      discipline is existential per the Massive masterplan; a 5-min decision refresh gains
      nothing from tick delivery. If TP-1 ships, Radar migrates to its derived stream.
  - option: Couple Radar's live lane to the Breathing Platform evening/breathing lanes
    why_not: "W-L1 is unproven end-to-end as of the last narrative doc; the breathing lane is a sibling pattern to copy, not shared infrastructure."
  - option: Recompute full indicators intraday (1-min or 5-min bar math)
    why_not: >
      Violates the house live law without evidence of need; the signal is daily/4H/2D/3D
      and threshold inversion answers the same question with parity by construction.
evidence:
  - "research/live_entry_radar/TRACK_D_LIVE_PLANE_CENSUS.md — full receipts (prophet-live.yml header, macro-live-prophet.{service,timer}, Caddyfile allowlist + 401 verification, r2io spool, TP-0 entitlement table, TP-0.5 eviction finding, ledger_lane)"
  - "research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §7 (frozen consequence)"
  - "engine/prophet_live/armed_pack.py:3-8 — the never-re-derives law this decision extends to Radar"
affects: ["engine/entry_radar/", "app/deploy/", "scripts/entry_radar_live_evaluator.py", "data/entry_radar/"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-13
---

## Grounds

PR-0 orchestration decision, taken after the Track D census resolved every open
infrastructure question: entitlements real (minute aggs ≥2010-06-15, ticks to 2005),
minute store unbuilt (TP-B), WebSocket unowned with a measured eviction hazard, VPS lane
proven at larger scale than Radar needs (1,730-name nightly arming in 420s), and the
gated-by-omission payload path costing zero new gate code.

## What would reopen this

Research evidence that 5-minute refresh materially misses the turn (reopens cadence);
TP-1 shipping (Radar migrates to the derived stream — a planned migration, not a
reversal); or the REST soft ceiling proving insufficient for the Probe Set's snapshot
needs during RTH (would force the tick-plane dependency forward).
