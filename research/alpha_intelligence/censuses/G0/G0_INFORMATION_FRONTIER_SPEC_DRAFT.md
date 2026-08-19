# GROK-G0 — Information Frontier Spec (DRAFT, not authoritative)

**Executed by macro-fleet researcher (sonnet) on FABLE-00 commission, 2026-08-19; Grok lane was undispatched.**

**Status: DRAFT.** This is a research-lane sketch of what a legal-information-frontier contract could
look like if the Earnings owner chooses to build it. It is **not** a frozen contract, is **not** wired
to any code, and does not carry `authority_class` weight — only `WS:EARNINGS-INTELLIGENCE-OS` (or a
successor DEC record it issues) can promote any of this to a real contract. Everything here is
INFERRED design reasoning built on top of the CODE VERIFIED facts in
`G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md`, not a new source of truth.

## 0. Why a new object, not a new `EVENT_STATES` value

`engine/company_intelligence/events.py` closes its `EVENT_STATES` enum with an explicit transition
table (CODE VERIFIED, `events.py:44-69`, cited in full in the Event Clock census). Adding
`HEADLINE_AVAILABLE`, `QA_AVAILABLE`, etc. as new members of that enum would be an authority-changing
edit to a frozen contract and would trip the estate's `authority_changed=true` fleet-law path (see
`agentos memory: any-scripts-edit-sets-authority-changed-and-hard-blocks-stop.md`, referenced for
context only, not as a repo receipt). The lower-risk design — proposed here, not decided — is a
**derived, read-only VIEW** keyed by `event_id` that sits alongside `event_workspace.v1` and computes
frontier-state timestamps from existing fields (`ReleaseRevision.acceptance_datetime`,
`CompanyEvent.observed_at`/`source_available_at`, transcript ingestion timestamps, filing acceptance
timestamps, analyst-snapshot `as_of`) without ever writing back into `events.py`'s own state machine.

## 1. Draft frontier-state → source mapping (draft field names, NOT contract-frozen)

```
information_frontier.v0_draft = {
  "event_id": "<same evt_cikNNNNNNNNNN_YYYYqN_kind id as company_event.v1>",
  "states": {
    "PRE_EVENT":            { "source_available_at": <calendar date/time>, "system_recorded_at": <collector run>, "pit_class": "not_pit (17.9% SLA coverage per E0 ledger)" },
    "HEADLINE_AVAILABLE":   { "source_available_at": null, "system_recorded_at": null, "pit_class": "unmodeled" },
    "FULL_RELEASE":         { "source_available_at": "<ReleaseRevision.acceptance_datetime>", "system_recorded_at": null, "pit_class": "pit_for_identity_not_for_timing" },
    "PREPARED_REMARKS":     { "source_available_at": "<transcript ingestion clock, not found in code read this session>", "system_recorded_at": null, "pit_class": "unmodeled" },
    "QA_AVAILABLE":         { "source_available_at": "<same flat document as PREPARED_REMARKS — no separate timestamp field exists in event_workspace.py:65>", "system_recorded_at": null, "pit_class": "unmodeled" },
    "FILING_RECONCILED":    { "source_available_at": "<10-Q/10-K acceptanceDateTime, per companyfacts_ledger.py>", "system_recorded_at": null, "pit_class": "pit (EPS panel filing-date overlay, edgar_eps.py, median ~34d lag)" },
    "FIRST_SESSION_CLOSE":  { "source_available_at": null, "system_recorded_at": null, "pit_class": "unmodeled — digest.py market_reaction stub is forced empty" },
    "ANALYST_REVISION_STATE": { "source_available_at": "<not carried by yfinance .info>", "system_recorded_at": "<yf_analyst.py as_of, collector-run clock>", "pit_class": "current-snapshot-at-fetch, not historically PIT before accrual start" }
  }
}
```

Every `null`/`unmodeled` cell above is a genuine gap this session found in the codebase, not an
omission of this draft — see §2.

## 2. Named gaps a real spec would have to close

1. **No HEADLINE_AVAILABLE ingester.** Nothing in `engine/earnings_release/` or
   `engine/earnings_narrative/` distinguishes a bare EPS/revenue headline (the newswire flash, seconds
   after the print) from the FULL_RELEASE body. `earnings_release/binding.py` only models the full
   Exhibit 99.1 body. If a G-wave cares about "did the market react to the headline number alone before
   the full release/call," this state has no data source today.
2. **No separately timestamped QA_AVAILABLE state.** The transcript is one flat document
   (`event_workspace.py`'s `qa_exchanges` field is a bare list, not a sub-object with its own
   `source_available_at`) — CODE VERIFIED. A frontier spec that wants to distinguish "market has read
   prepared remarks" from "market has read Q&A" needs either (a) a segment-level timestamp the current
   transcript ingestion does not carry, or (b) an approximation from the call's structural markers
   (prepared-vs-Q&A category tags already exist per `digest.py:614`) combined with an assumed dwell
   time — the latter would be an ESTIMATE, not a PIT fact, and must be labeled as such if built.
3. **No FIRST_SESSION_CLOSE computation anywhere in the Earnings claim graph.** The only place price
   reaction is computed at all is `engine/expectation_state.py` (`pead_drift_20d`, entry point at
   event+1 session, not the first session itself) — and that module is architecturally disconnected
   from `event_workspace.v1`/`digest.py` (different directory, different authority note, no shared
   `event_id`). `digest.py`'s own `market_reaction` field is a **forced-empty typed absence**, not a
   partial implementation — CODE VERIFIED, `digest.py:397-400`.
4. **ANALYST_REVISION_STATE has no historical PIT panel.** `yf_analyst.py` snapshots the CURRENT
   consensus at fetch time; there is no way to ask "what was the average analyst target on date D in
   2023" unless D postdates whenever the `analyst_snapshots.parquet` accrual began. Any G-wave backtest
   using analyst-revision timing before that accrual start is not historically PIT and must say so.
5. **Options reaction is entirely unmodeled in this frontier.** See
   `G0_REACTION_GEOMETRY_INPUT_MATRIX.md` — no earnings-specific options join was found (grep-level
   search only, not exhaustive).

## 3. Draft PIT-safety rule (proposed, not binding)

Following the existing pattern in `event_workspace_build.py` (`observed_at` may never precede
`source_available_at`, CODE VERIFIED `event_workspace_build.py:150-153`) and FIF's bitemporal cutoff
pair, any future frontier-state object should carry the SAME invariant per state: a state transition
timestamped `observed_at` must never precede that state's own `source_available_at`, and any consumer
reading the frontier object for a historical backtest must filter on `system_recorded_at <=
backtest_as_of`, never on `source_available_at` alone — the existing `expectation_state.py` module
already does the PIT-correct version of this for its one live field (`pead_drift_20d` uses "today" as
the query anchor and only reads events within a trailing window, `expectation_state.py:38-70`).

## 4. What this draft explicitly refuses to specify

- It does not propose a beat/miss basis-resolution algorithm — the existing `basis_match` legal gate
  (`event_workspace.py:272-278`) already forbids minting one without a licensed consensus, and nothing
  in this census changes that.
- It does not propose an options-reaction schema — that requires the audit gap in §2.5 to be closed
  first (a real module-by-module read of the ~20 `engine/options_*.py` files), which this commission's
  read budget did not cover exhaustively.
- It does not propose where this object would be published, under what authority, or which consumer
  would read it — those are `WS:EARNINGS-INTELLIGENCE-OS` decisions, not research-lane decisions (see
  `G0_OPEN_QUESTIONS.md` Q1-Q3).
