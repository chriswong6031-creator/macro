---
key: RATES-INFLATION-COMMAND
title: Rates & Inflation Command plus Macro Release Intelligence completion
objective: >
  Deliver one correction-safe, evidence-calibrated premium Rates & Inflation workflow spanning
  releases, rates/curve momentum, dealer/OPEX context, canonical transmission, policy/Fed path,
  Forward Path synthesis and learning. Done means real current inputs traverse production into the
  actual user/machine consumers with all authority ceilings, nulls, evidence clocks and failure states
  intact; CI or merged infrastructure alone is not completion.
status: active
program: rates-inflation-command
repos: [macro]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - engine/release_forecast*.py
  - engine/event_calendar.py
  - engine/event_window.py
  - engine/opex*.py
  - engine/options_surface.py
  - engine/rate_inflation_transmission.py
  - engine/rates_inflation_command.py
  - scripts/build_rates_command.py
  - data/release_forecast/**
  - data/rates_command/**
  - data/options_surface/**
  - data/transmission/**
  - site/macro.html
depends_on: []
waves:
  - id: F0
    title: Recovery, capability ledger and architecture freeze
    status: in_progress
    next_action: >
      Independently review and accept the records-only recovery carrier; no product/runtime behavior
      is changed by F0.
  - id: F1
    title: Release and event truth/intelligence closure
    status: todo
    depends_on: [F0]
  - id: F2
    title: Dealer/OPEX state and HS3/HS4 historical priors
    status: todo
    depends_on: [F0]
  - id: F3
    title: Yield momentum and canonical Transmission extension
    status: todo
    depends_on: [F0]
  - id: F4
    title: Forward Path canonical composition
    status: todo
    depends_on: [F1, F3]
  - id: F5
    title: Unified premium Rates & Inflation experience
    status: todo
    depends_on: [F2, F4]
  - id: F6
    title: Evaluation, learning and evidence-clock composition
    status: todo
    depends_on: [F1, F2, F3, F4]
  - id: F7
    title: End-to-end production reliability and acceptance
    status: todo
    depends_on: [F5, F6]
decisions:
  - DEC:RIC-CANONICAL-COMPOSITION-BOUNDARIES
discoveries:
  - DSC:RIC-RECOVERY-FOUND-STATUS-DRIFT-AND-W3-W4-DISCONNECT
landmines:
  - "Old July W-number status is not current capability truth; see DSC:RIC-RECOVERY-FOUND-STATUS-DRIFT-AND-W3-W4-DISCONNECT."
  - "Calendar/OPEX proximity may not rank, score, gate or size risk; preserve DNR:KILL-CALENDAR-GATED-RISK."
  - "MRI current accuracy is withheld under the repaired target epoch; do not cite superseded legacy backtests as current efficacy."
  - "Slack delivery/membership is not runtime claim or worker execution; current Autonomy V1 dispatch law applies."
do_not_redo:
  - "Do not create a second release/calendar truth plane; compose MRI + event_calendar."
  - "Do not create a second options/dealer store or resurrect retired Polygon source assumptions; current ThetaData/options_surface owns the broad surface."
  - "Do not create the July-style parallel rates-to-cohort engine; canonical Transmission owns pass-through and per-name sensitivity."
  - "Do not build a policy-timing predictor or calendar/OPEX directional signal."
artifacts:
  - research/RATES_INFLATION_COMMAND_RECOVERY_AND_COMPLETION_FREEZE_2026-08-27.md
  - research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
  - research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md
  - research/TRANSMISSION_INTELLIGENCE_MASTERPLAN_BY_FABLE.md
next_action: >
  Complete F0 independent review/merge, then submit the frozen RIC-F1, RIC-F2 and RIC-F3 packets
  through canonical Executive admission/routing as three disjoint operations and call a lane active
  only after its concrete Fable/worker carrier/session ACK is proven.
---

## Why this workstream exists

Rates & Inflation Command accumulated real implementation across multiple July/August programs, but
there was no durable Agent OS workstream tying current product intent, authority law, current gaps and
continuation together. The result was a stale W-number masterplan coexisting with newer canonical
release/transmission/options systems and disconnected implementation seams.

## Current frontier

F0 is records-only and has no product/runtime effect. F1/F2/F3 are the first independently useful
capability lanes, but as of the recovery they are not runtime-claimed. F4-F7 remain CEO-owned
integration waves and may not be treated as commissioned merely because this record names them.

The complete capability ledger, exact first commission packets and production acceptance contract are
in `research/RATES_INFLATION_COMMAND_RECOVERY_AND_COMPLETION_FREEZE_2026-08-27.md`.
