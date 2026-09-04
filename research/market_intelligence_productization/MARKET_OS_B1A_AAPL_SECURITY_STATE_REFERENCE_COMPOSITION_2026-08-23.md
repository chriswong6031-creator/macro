# Market OS B1A — AAPL Security State Reference Composition

**Status:** Reference composition for the B1A implementation commission  
**Authority:** UX/product contract only

## Desktop first viewport

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ AAPL  Apple Inc.                      $...   as of ...   WATCHED / OWNED     │
│ CURRENT STATE: [typed state]          DATA: CURRENT / PARTIAL / STALE        │
│ Prophet: [owner state]                Entry: [ENTRY_OPEN / WAIT / UNKNOWN]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ CHART — existing Terminal-grade / dossier chart remains primary             │
├───────────────────────┬───────────────────────┬──────────────────────────────┤
│ STATE                 │ CHANGE                │ OPPORTUNITY CONTEXT          │
│ What it is doing now  │ What newly happened   │ What favorable context      │
│ owner-backed state    │ exact event clock     │ remains; no fused score     │
├───────────────────────┼───────────────────────┼──────────────────────────────┤
│ RISK                  │ CATALYST              │ PERSONAL IMPACT              │
│ failed gates          │ next observables      │ owned/watched/none           │
│ unresolved fact       │ timing/deadlines      │ private overlay only         │
├──────────────────────────────────────────────────────────────────────────────┤
│ EVIDENCE & RECEIPTS                                                     [>] │
│ 3 available · 1 stale · 1 unavailable · source frontier ...                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Required interaction

### Select a Decision Spine card

The right inspector or accessible drawer opens:

```text
field status
plain-language explanation
canonical owner
owner object ID/version
source
published / available / observed / compiled clocks
coverage
correction/conflict state
why this field is or is not actionable
```

### Open Evidence

The user sees exact supported claims and source links.

No evidence drawer invents new calculations.

### Open Failed Gates

The user sees deterministic codes and what would clear each gate.

A missing owner result appears as unavailable, not “pass.”

## Compact/tablet

- chart remains first;
- header and dominant state remain visible;
- Decision Spine becomes a two-column card grid;
- evidence opens as a full-height drawer;
- all six axes remain present.

## Mobile

- identity/current state;
- chart;
- one card per axis;
- strongest unresolved fact before secondary detail;
- next observable;
- evidence as bottom sheet;
- no miniature table or hidden horizontal rail.

## Failure-state examples

### Prophet unavailable

```text
OPPORTUNITY CONTEXT
Prophet context unavailable
This does not change the event or current price state.
No rank or neutral value substituted.
```

### Event stale

```text
CHANGE — STALE
Latest supported company event is older than the event freshness policy.
Showing last-known event with source clock; no “current change” claim.
```

### Source corrected

```text
CHANGE — CORRECTED
The source event was revised.
Prior Security State remains replayable; current version uses corrected evidence.
```

### No user context

```text
PERSONAL IMPACT
No Portfolio or Watchlist context for this session.
Public security intelligence remains available.
```

## Visual laws

1. Chart and security identity remain primary.
2. Decision Spine axes remain separate.
3. No giant single composite score.
4. Dominant degradation is visible in the header.
5. Every conclusion drills to evidence.
6. Empty, stale, corrected, conflicted, and unavailable are designed states.
7. Private Portfolio data never enters public payloads or screenshots.
