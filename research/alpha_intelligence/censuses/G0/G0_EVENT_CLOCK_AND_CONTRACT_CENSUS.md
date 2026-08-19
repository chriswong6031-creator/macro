# GROK-G0 — Event Clock and Contract Census

**Executed by macro-fleet researcher (sonnet) on FABLE-00 commission, 2026-08-19; Grok lane was undispatched.**

Program: `WS:EARNINGS-INTELLIGENCE-OS` (Mastermind Alpha Intelligence estate). Scope: read-only audit
of Earnings Intelligence + FIF + market-reaction capabilities, and a legal-information-frontier map,
in support of a future Post-Event Reinterpretation extension that would be queued behind E2 under the
existing Earnings owner. No code, config, or `data/` was touched. Repo base: `origin/main` @
`aa9ee6cd3f68` (2026-08-19, tree clean at session start).

Verification tags used throughout: **CODE VERIFIED** (path:line read this session),
**PRODUCTION VERIFIED** (a live production artifact/receipt was inspected — none were, this worktree
is sparse and `data/`/`site/` are off disk; every claim that would need one is marked UNKNOWN below),
**PRIMARY SOURCE VERIFIED** (named external publisher/filing confirmed via WebSearch this session),
**INFERRED** (reasoned from adjacent verified facts, not itself directly read), **UNKNOWN** (could not
verify in this worktree/session; not guessed).

---

## 1. Repository audit — what exists today, exactly where

### 1.1 Earnings Intelligence OS (owner: `WS:EARNINGS-INTELLIGENCE-OS`)

- **Ownership and freeze.** `agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md` — CODE VERIFIED.
  `owns_paths`: `research/earnings_intelligence/**`, `engine/earnings_narrative/**`,
  `engine/company_intelligence/**`, `templates/earnings_wire/**`. Status: E0 done (frozen), E1 done
  (PR #5817), E1P done/live (PR #5841, generation `f709a0a6ec514282d5769e7d`), **E2 = `todo`, next_action
  = "Implement E2 exactly as frozen ... do not broaden scope into E3+."** `do_not_redo` explicitly bars
  rebuilding Terminal transcripts/Stage/Group Reads/TIL, re-reading the closed v1 score overlay for the
  E2 glance, and broadening E2 into E3+/slides/Q&A ML/a second publisher — the last of these three
  directly bounds any G-wave ambition. — CODE VERIFIED,
  `agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md:1-45`.
- **Authority.** `config/mastermind_programs.yml:2046-2079` — key `earnings-intelligence`, kind
  `semantic_rail`, `decision_boundary.authority_class: context_only`, `does_not_own`: "Selection,
  ranking, sizing, gates, or execution." — CODE VERIFIED. `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`
  (`agentos/decisions/DEC-EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP.md`) affirms this is the single owner
  key; no second key may be minted for a G-wave. — CODE VERIFIED.
- **Capability ledger (E0, dated 2026-08-16, code base `3b16672fcfee`).**
  `research/earnings_intelligence/E0_CAPABILITY_LEDGER.md` is the closest existing artifact to this
  census and should be read alongside it, not duplicated. Load-bearing rows for G0 (all CODE VERIFIED
  via that ledger's own path:line receipts, reproduced here for traceability):
  - **Market reaction: `SPEC_ONLY`.** "Stub in `digest.py`; forbidden in `promotion.py`" —
    `E0_CAPABILITY_LEDGER.md:40`, receipts `digest.py:397-400`, `promotion.py:52`.
  - **Q&A exchange structure: `PARTIAL`.** Prepared-vs-Q&A markers exist; "no exchange object" —
    `E0_CAPABILITY_LEDGER.md:57`.
  - **Non-answer / deflection: `NOT_BUILT`.** — `E0_CAPABILITY_LEDGER.md:59`.
  - **Guidance extraction: `PARTIAL`, lexical only** (`digest.py` `guidance` category bucket, not a
    structured `guidance_item.v1` range) — `E0_CAPABILITY_LEDGER.md:52`.
  - **Consensus snapshots: `PARTIAL`**, free calendar EPS only, "licensed estimates" and CEI
    `consensus: unlicensed_absent" — `E0_CAPABILITY_LEDGER.md:39`.
  - **Contradictions (claim vs later claim/filing): `NOT_BUILT`** — `E0_CAPABILITY_LEDGER.md:64`.
  - **Price incorporation/catch-up (PEAD-adjacent): `PARTIAL`**, "Stock PEAD copy; group `drift`" —
    not a CEI field — `E0_CAPABILITY_LEDGER.md:104`.
  - **Release / 8-K binding: `PARTIAL`**, CEI digest hard-codes `release: not_ingested`,
    `filing: not_ingested` — `E0_CAPABILITY_LEDGER.md:34-35`.
  This session independently re-read `digest.py` and `promotion.py` and confirms the ledger's
  claims still hold on current `origin/main` (§1.2 below) — CODE VERIFIED, not merely relied upon.

### 1.2 `event_workspace` contracts (E1/E1P, live)

- `engine/company_intelligence/event_workspace.py` (472 lines) defines `event_workspace.v1`. Schema
  keys include `lifecycle`, `facts`, `deltas`, `guidance`, `claims`, `sources`, `qa_exchanges`,
  `claim_citations_pending`, `prophet_flags` (all four flags forced `False`). — CODE VERIFIED,
  `event_workspace.py:33-97`.
- **Beat/miss is legally forbidden absent a licensed basis.** `validate_event_workspace` raises if any
  delta carries `beat`/`miss`/`beat_miss` unless `basis_match is True`, and raises if `basis_match` is
  `True` at all ("not minted in E1 without a licensed consensus"). — CODE VERIFIED,
  `event_workspace.py:272-278`. This is the single strongest legal-frontier constraint in the estate:
  **no code path may currently mint a beat/miss verdict for the flagship AAPL event or any other.**
- `_lifecycle_payload` carries exactly `state`, `observed_at`, `source_available_at` per event — CODE
  VERIFIED, `event_workspace.py:234-241`. This is the closest existing analog to the commissioned
  event-clock, but it is a single two-timestamp pair per lifecycle `state`, not the eight-state
  PRE_EVENT→ANALYST_REVISION_STATE frontier the commission asks for (§2).
- `engine/company_intelligence/event_workspace_build.py` (459 lines): `build_event_workspace(...,
  observed_at, source_available_at, ...)` raises `WorkspaceError("observed_at precedes
  source_available_at")` — CODE VERIFIED, `event_workspace_build.py:150-153`. This is the mechanical
  PIT firewall: a transition cannot be recorded before its source existed.
- Publication path: `DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT` — publishes under
  `company_intelligence/event_workspaces/`, marker-last immutable generation, real consumer is
  `engine.neuralweb.company_intelligence_reader.read_event_workspace`. — CODE VERIFIED (decision file
  read in full).

### 1.3 `engine/earnings_release/` — the only body-level release ingester found

- **Nothing else in the estate ingests a release BODY** (per the module's own docstring, cross-checked
  against the E0 ledger's "release: not_ingested" row) — `engine/earnings_release/binding.py:1-6`.
  CODE VERIFIED.
- `bind_release_document(...)` is pure/offline: the body is supplied, never fetched — CODE VERIFIED,
  `binding.py:244-262`.
- `FILING` vs `EVENT` identity is explicit and load-bearing: a filing is `(cik, accession)` exact; an
  event is `(cik, report_date)`; an 8-K/A is a different filing of the same event — CODE VERIFIED,
  `binding.py:14-28`.
- `normalize_acceptance()` normalizes EDGAR's `acceptanceDateTime` (its own two spellings) to UTC ISO —
  this is the SOURCE's own clock, never a processing clock — CODE VERIFIED, `binding.py:57-76`.
- `collapse_release_events()` groups by `(cik, report_date)`, ordering revisions by
  `(acceptance_datetime, filing_date, accession)` — the acceptance timestamp is authoritative for
  ordering, filing_date and accession are tie-breaks — CODE VERIFIED, `binding.py:123-127, 298-385`.
- `receipts.py` (285 lines): every figure receipt is byte/char-span-replayable against the exact source
  bytes before it is allowed to leave the module (`receipt_for_char_span` calls `replay_receipt` on
  itself before returning) — CODE VERIFIED, `receipts.py:191-218`. This is a strong PIT-adjacent
  guarantee for **document identity** (a figure receipt cannot silently drift onto a later revision's
  bytes) but says nothing about **when** the body became available to a consumer — that is carried
  separately in `ReleaseRevision.acceptance_datetime`/`filing_date`.
- **Gap:** `engine/earnings_release/` binds a release body to a filing; it does not itself determine
  premarket/after-hours timing, nor whether an EX-99.1 body was disseminated by newswire before the
  EDGAR accession posted (a real-world race the estate has not measured) — UNKNOWN.

### 1.4 FIF / Financial Intelligence Packet (`engine/fundamental_forensics/`) — Sol-frozen, read-only

- **FIF-1R3 is frozen** as of `ef2554c9909f` ("FIF-1R3: freeze revision lineage at the v1 63/64 wire
  bound", 2026-08-18) and `e2a584496b08` ("record FIF-1R3 63/64 landing proof counts") — CODE VERIFIED
  via `git log`. This census treats `engine/fundamental_forensics/financial_intelligence_packet.py` and
  its sibling FIF-1R3 modules as **read-only contact points**; no change is proposed here.
- `financial_intelligence_packet.py` (packet schema `financial_intelligence_packet.v1`) is explicitly
  **bitemporal**: `GOLDEN_SOURCE_CUTOFF = "2025-12-31T23:59:59Z"` vs
  `GOLDEN_RECORDED_CUTOFF = "2026-08-05T12:00:02Z"`, policy `BitemporalPolicy.LATEST_KNOWN_AS_OF` — CODE
  VERIFIED, `financial_intelligence_packet.py:88-90`. This source/recorded split is architecturally the
  same shape the commission's `source_available_at` / `system_recorded_at` pair needs, and should be
  the reference pattern for any G-wave frontier spec rather than a new bitemporal design.
- `engine/fundamental_forensics/companyfacts_ledger.py` docstring is explicit that **SEC Company Facts
  has no acceptance timestamp and no XBRL context/unit identifiers** — the acceptance clock must come
  from a separate Submissions join, and "a missing Submissions join is visible and fails closed... via
  `TemporalClocks.accepted_at is None`." — CODE VERIFIED, `companyfacts_ledger.py:1-19`. This is a
  second, independent confirmation (alongside `earnings_release/binding.py`) that EDGAR's two clocks
  (filing acceptance vs company-facts occurrence) are NOT interchangeable and the estate already treats
  them as such.
- `engine/fundamental_forensics/disclosure_diff.py` (deterministic, offline 10-K/10-Q structural diff
  engine) is explicitly **not** a narrative classifier and "does not make an assertion about management
  intent, legal materiality, or an economic outcome" — CODE VERIFIED, `disclosure_diff.py:1-7`. This is
  the FILING_RECONCILED-state building block for an "accounting contradiction" class (§ Casebook) but
  it is not currently joined to `event_workspace.v1` or to the Earnings claim graph.

### 1.5 Analyst revisions

- `collectors/yf_analyst.py` (532 lines) — US analyst price-target/rating collector, **display/context
  only**, `allowed_behavior: annotate_only`, no field may feed `board_rank`/`eq_score`/sizing — CODE
  VERIFIED, `yf_analyst.py:9-21`.
- **Not historically PIT.** yfinance `.info` returns the *current* consensus at fetch time; "there is no
  historical series" — every row is stamped `provenance_note = "yfinance_info_pit_snapshot"` meaning
  point-in-time-of-fetch, not a reconstructable historical PIT series — CODE VERIFIED, `yf_analyst.py:11-14,
  71`. A forward-accruing history exists: `data/narrative/analyst_snapshots.parquet`, appended once per
  run since the W2 addition (`_append_analyst_snapshots`, `yf_analyst.py:407-479`) — CODE VERIFIED for
  the code path; the parquet's actual contents/start date are UNKNOWN in this sparse worktree (`data/`
  is off disk; see Deviations).
  **Implication for G0:** any ANALYST_REVISION_STATE frontier state can only be reconstructed
  historically from whatever accrual window `analyst_snapshots.parquet` covers going forward from its
  addition — there is no vendor-backed historical analyst-revision PIT panel in this repo today.

### 1.6 Price / options reaction

- **Price reaction is explicitly not joined to any Earnings claim/digest object.**
  `engine/earnings_narrative/digest.py:397-400` forces `event_digest.market_reaction ==
  {"status": "not_joined", "as_of": None, "security_ids": []}` — CODE VERIFIED (read directly, not only
  via the E0 ledger). `engine/earnings_narrative/promotion.py:52` — `_FORBIDDEN_INPUTS` includes
  `"market_data"`, `"market_reaction"`, `"trading_action"` — CODE VERIFIED (read directly).
- A **separate, display-only** PEAD/reaction module exists outside the Earnings claim graph:
  `engine/expectation_state.py` (LT-2c) computes `pead_drift_20d` (stock-minus-SPY cumulative return
  from event+1 session), `bad_news_absorption`, `good_news_hold` per ticker, keyed off
  `earnings_8k_dates` + `sue.py`'s SUE construction — every output field carries `_display_only=True`,
  `_horizon_role='hold_thesis'`, and MUST NOT feed ranking/sizing/gating — CODE VERIFIED,
  `expectation_state.py:1-40`. This is the one place in the estate where price reaction to an earnings
  event is actually computed and shipped, and it lives entirely outside `engine/company_intelligence/`
  and `engine/earnings_narrative/` — a second, disconnected plane from the Earnings claim graph (echoes
  `DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`).
- `engine/sue.py` and `scripts/research/pead_sue_pit.py` implement Standardized Unexpected Earnings /
  PEAD research using a seasonal-random-walk proxy (`EPS_q − EPS_{q-4}`), strictly PIT-gated to
  `asof_date ≤ event date` — CODE VERIFIED, `sue.py:1-20`, `pead_sue_pit.py:1-27`. `pead_sue_pit.py` is
  a **scratch research script** (hardcoded path to an unrelated worktree, `agitated-nightingale-3cf266`)
  — not a production module; its own honesty note flags survivorship bias (114 current survivors, 95
  with EPS coverage) — CODE VERIFIED, `pead_sue_pit.py:1-27`.
- **Options reaction: no earnings-specific join found.** `git grep` for `options_reaction`,
  `earnings_gap`, `overnight_gap` returned no hits in `engine/`/`scripts/`/`collectors/`. A large options
  engine exists (`engine/options_*.py`, 20+ modules — `options_desk.py`, `options_flow.py`,
  `options_skew.py`, `options_ivspread.py`, `options_dislocation.py`, `options_matrix.py`, etc.) — CODE
  VERIFIED as a file-existence census only; this session did **not** open each of these ~20 modules to
  confirm none of them independently join to an earnings event date (that would be a wider audit than
  this commission's read budget allows). **Tagged UNKNOWN, not NOT_BUILT** — a targeted grep for the
  obvious names found nothing, but a deeper module-by-module read could still surface an implied-move or
  IV-crush computation that is earnings-adjacent without using those literal names. This is named as an
  explicit open question (§ G0_OPEN_QUESTIONS.md).

### 1.7 Q&A structure

- `engine/earnings_narrative/digest.py` distinguishes prepared-remarks facts from `q_and_a`-category
  facts and emits a `qa_exchanges` list of fact IDs — CODE VERIFIED, `digest.py:614`. This is a
  **category tag on individual facts**, not a structured question→answer pair object (who asked, which
  analyst/firm, what was answered) — confirmed by the E0 ledger's own language, "no exchange object"
  (`E0_CAPABILITY_LEDGER.md:57`), and by `event_workspace.py`'s `qa_exchanges` key being present in the
  schema (`WORKSPACE_KEYS`, `event_workspace.py:65`) but populated `[]` in the one live build path
  inspected (`event_workspace_build.py:453`) — CODE VERIFIED.
- Terminal (`terminal/` repo, not audited directly here — cross-repo, out of scope per commission) is
  reported by the E0 ledger to have speaker/Q&A display **filters** in `TranscriptDrawer.tsx`, not an
  exchange object either — INFERRED from the E0 ledger's own citation, not independently re-verified
  this session (Terminal repo is outside this worktree).

---

## 2. Event clock — legal information frontier per native source

Every row below states whether the FRONTIER STATE VOCABULARY itself (PRE_EVENT →
ANALYST_REVISION_STATE) exists in the codebase today. **It does not.** `engine/company_intelligence/
events.py` defines a *different*, already-closed state vocabulary —
`EVENT_STATES = {discovered, scheduled, rescheduled, started, completed_partial, complete, corrected,
superseded, derived_ready, distributed, cancelled}` with an explicit transition table
(`_TRANSITIONS`, `events.py:58-69`) — CODE VERIFIED, `events.py:44-56`. `blocked_rights` and
`source_missing` are reserved as **coverage states**, explicitly not event states
(`events.py:71-75`). The commission's eight-state frontier is therefore a **new, finer-grained view**
that would have to either (a) be built as a derived read atop `company_event.v1` lifecycle +
`event_workspace.v1` timestamps without touching the closed `EVENT_STATES` enum, or (b) require an
authority-changing edit to `events.py` (which would trip `authority_changed=true` and the associated
fleet-law constraints — see `G0_OPEN_QUESTIONS.md`). This census does not resolve which; it names the
choice as the first thing the Earnings owner must adjudicate.

| Frontier state (commissioned vocabulary) | Native source(s) | `source_available_at` | `system_recorded_at` | AH/premarket/open timing available? | Historically PIT? | Verification |
|---|---|---|---|---|---|---|
| PRE_EVENT | `data/earnings/earnings.parquet` (`collectors/equity_earnings.py`) — scheduled date/time | Calendar provider publish time | Nightly `daily.yml` build stamp | Provider-dependent; not verified this session | **No** — E0 ledger: coverage SLA failing, 17.9% within 2-trading-day SLA as of 2026-08-13 (`E0_CAPABILITY_LEDGER.md:33`) | INFERRED (ledger citation) / UNKNOWN (parquet contents, sparse worktree) |
| HEADLINE_AVAILABLE | Newswire/8-K Item 2.02 headline (EPS/rev topline) — **no ingester found** for the headline-only moment distinct from full release | UNKNOWN — not modeled | UNKNOWN — not modeled | UNKNOWN | UNKNOWN — no code path exists to answer this | UNKNOWN |
| FULL_RELEASE | EDGAR Exhibit 99.1 body via `engine/earnings_release/binding.py` | `ReleaseRevision.acceptance_datetime` (EDGAR's own clock, normalized UTC) — CODE VERIFIED, `binding.py:57-76,86` | Not modeled in this module; would be the ingester's fetch/process timestamp — UNKNOWN | Not modeled — EDGAR acceptance time is a UTC instant, not classified into premarket/AH/open buckets by this module | **Yes, for document identity** (byte-exact, replay-checked receipts); **NOT for timing** — nothing prevents a body from being processed hours or days after acceptance | CODE VERIFIED (identity) / UNKNOWN (timing classification) |
| PREPARED_REMARKS | Terminal `mastermind.tx/v1` transcript body, ingested via `earnings_narrative/contracts.py`; `binding.py` explicitly says filings, not transcripts | Terminal transcript index + body SHA-256 (E0 ledger: `PROVEN_LIVE`, `E0_CAPABILITY_LEDGER.md:36`) | Not modeled at the segment level in modules read this session | UNKNOWN | Transcript body identity is receipt-bound; call *timing* (premarket/AH/live) not confirmed in code read this session | INFERRED (ledger) / UNKNOWN (this session's own code read) |
| QA_AVAILABLE | Same transcript body, `q_and_a` category tag on facts (`digest.py:614`) | Same as PREPARED_REMARKS — the transcript is one flat document; there is **no evidence in code read this session that Q&A arrives as a separately timestamped later artifact** than prepared remarks | Same | UNKNOWN | Same identity guarantee, same timing gap | CODE VERIFIED (no separate Q&A timestamp field exists in `event_workspace.py`'s `qa_exchanges` schema — it is a bare list, `event_workspace.py:65`) |
| FILING_RECONCILED | SEC 10-Q/10-K via `disclosure_diff.py` / `companyfacts_ledger.py` | `acceptanceDateTime` for the periodic filing; EPS panel median filing lag **~34 days** after quarter-end for `EarningsPerShareDiluted` via `companyconcept` earliest `filed` date (not the 8-K date) — CODE VERIFIED, `collectors/edgar_eps.py:1-16` | Nightly collector run stamp — UNKNOWN in sparse worktree | N/A (filings are not intraday events) | **Yes** for the filing-date overlay described in `edgar_eps.py`; the 10-Q/10-K itself is not currently bound to the CEI event (E0 ledger: "10-Q/10-K unbound", `E0_CAPABILITY_LEDGER.md:35`) | CODE VERIFIED |
| FIRST_SESSION_CLOSE | **No dedicated module found.** `expectation_state.py` computes drift from "event+1 session" onward, implying an entry point *after* the first session, not a first-session-close capture itself | UNKNOWN | UNKNOWN | UNKNOWN — the digest's `market_reaction` stub (`status: not_joined`) is the closest thing, and it is a forced-empty placeholder, not a computed value (`digest.py:397-400`) | UNKNOWN | CODE VERIFIED (stub exists) / UNKNOWN (no live computation found) |
| ANALYST_REVISION_STATE | `collectors/yf_analyst.py` snapshot + `data/narrative/analyst_snapshots.parquet` accrual | `as_of` = UTC date of the collector run, **not** the analyst's own revision timestamp (yfinance `.info` carries no per-analyst revision clock) — CODE VERIFIED, `yf_analyst.py:339,417-421` | Same `as_of` field doubles as both — no source/recorded split exists here, unlike FIF's bitemporal pair | N/A | **No** — explicitly a current-snapshot-at-fetch-time collector; historical series only exists from whenever the snapshot accrual started running, not retroactively | CODE VERIFIED |

**Cross-cutting finding:** the estate has TWO different disciplined patterns for a source/recorded
clock pair — `earnings_release/binding.py`'s `acceptance_datetime` (SOURCE clock, EDGAR's own) vs a
processing timestamp (not modeled in that module), and FIF's explicit bitemporal
`GOLDEN_SOURCE_CUTOFF`/`GOLDEN_RECORDED_CUTOFF` pair. Neither pattern currently reaches
`event_workspace.v1`'s `qa_exchanges`, the transcript ingestion path, or the analyst-revision collector.
A G-wave frontier spec has two existing precedents to imitate and zero existing code to inherit
directly.

---

## 3. What this file does NOT claim

- No claim is made about whether any of these sources are legally licensed for redistribution beyond
  their current `context_only` authority — that is a RIGHTS question, not addressed here except to flag
  it (see `G0_OPEN_QUESTIONS.md`).
- No claim is made about production freshness of any `data/` parquet named above — this worktree is
  sparse (`data/`, `site/`, `mockups/`, `verify_shots/` omitted from disk per
  `config/sparse_worktree.json`), and per the commission's OUT OF SCOPE instruction this census did not
  run `scripts/worktree_sparse.py` to pull them. Every claim that would require reading `data/` bytes is
  tagged UNKNOWN above rather than guessed.
