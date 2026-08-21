# G0 Information Frontier Spec Draft

**Status:** research draft under `earnings-intelligence`. Not an implementation freeze.  
**Does not supersede** `research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md`. If this draft conflicts with that freeze, the freeze wins.  
**Authority:** `context_only`. `may_rank=false`, `may_size=false`, `may_gate=false`, `prophet_authority=false`.

---

## 0. Problem

The estate can say “the event is `complete`” while the *legal information set* is still moving: headline vs full exhibit, prepared remarks vs Q&A, 8-K vs 10-Q, first regular-session close, later estimate revisions.

Post-event reinterpretation is the job of **re-reading the same `event_id` as later sources arrive**, without forking identity and without silently using later knowledge in earlier states.

That job is not a new organ. It is an orthogonal projection on `event_workspace.v1`.

---

## 1. Objects (draft names — do not mint until E-wave owns them)

| Object | Purpose | Must not become |
|---|---|---|
| `information_frontier.v1` | Derived state of what was legally knowable | A lifecycle replacement for `company_event.state` |
| `frontier_source.v1` | One native source’s two clocks + PIT class | A second document store |
| `reinterpretation.v1` | A later reading that cites **new** spans/packets against the **same** event | A score, beat/miss, or Prophet feature |
| `reaction_geometry.v1` | Display-only tape/options/revision vector joined by `security_id` | A trading signal |

All four stay `authority=context_only`. LLM prose may only de-escalate; it may not originate a reinterpretation (`DNR:KILL-LLM-ORIGINATION`).

---

## 2. Frontier state machine

Closed vocabulary, in this order. States are **prefixes of knowable evidence**, not quality grades.

```
PRE_EVENT
HEADLINE_AVAILABLE
FULL_RELEASE
PREPARED_REMARKS
QA_AVAILABLE
FILING_RECONCILED
FIRST_SESSION_CLOSE
ANALYST_REVISION_STATE
```

Rules:

1. A state is `reached` only when its required source has `source_available_at` and a receipt (`byte_replayed` | `address_only` | `typed_absence`).
2. A state is `blocked` when the source is known-missing (`no_source_document`, `unlicensed`, `blocked_rights`).
3. A state is `unknown` when the estate has not looked. **Unknown is not blocked.**
4. A state is `accruing` when a vintage series exists only after a named start date (revisions/options mid-2026).
5. Advancing the frontier **never** changes `event_id`. Correction remains `lifecycle.state=corrected` + new `generation_id`.
6. `observed_at < source_available_at` is still refused (existing firewall).
7. Consumers that render a past frontier must query FIF with `evaluation_mode=historical_replay` and both cutoffs ≤ that frontier’s `source_available_at`. `latest_known_as_of` / `latest_restated` are later-knowledge modes and must be labeled as such.

### 2.1 Admission per state

| State | Required evidence | Honest blocked form |
|---|---|---|
| `PRE_EVENT` | Calendar or `scheduled_at` | `calendar_unofficial` |
| `HEADLINE_AVAILABLE` | First legal text (8-K header / Exhibit 99.1 first bytes / issuer IR). **Not** a newswire paraphrase | `headline_not_held` |
| `FULL_RELEASE` | Full Exhibit 99.1 (or equivalent) SHA | `release_not_ingested` (already on Wire) |
| `PREPARED_REMARKS` | Transcript chapter `prepared` with span receipts | `transcript_absent` |
| `QA_AVAILABLE` | Transcript chapter `q_and_a` **or** structured `qa_exchange.v1` | `qa_unstructured` (live warning already exists) |
| `FILING_RECONCILED` | FIF packet (or typed absence) for the same `company_id` + period, `source_event_cutoff` ≥ 10-Q/10-K `accepted_at` | `filing_unjoined` / `pit_ineligible` |
| `FIRST_SESSION_CLOSE` | PIT bar for `security_id` covering the first regular session after `source_available_at` of `FULL_RELEASE` | `reaction_not_joined` (already exists) |
| `ANALYST_REVISION_STATE` | PIT revision vintage **after** the print | `revisions_unlicensed` / `accruing` |

`HEADLINE_AVAILABLE` without `FULL_RELEASE` is a first-class cell. Do not collapse them because one 8-K accession often carries both.

---

## 3. Binding to existing fields

Reuse; do not rename.

| Draft field | Bind to |
|---|---|
| `event_id` | `evt_cik…` |
| `security_ids` | workspace issuer listings |
| `source_available_at` | document `available_at` / SEC `accepted_at` / IR `published_at` — **never** `generated_at` |
| `system_recorded_at` | document `fetched_at` or ledger `recorded_at` |
| `observed_at` | existing lifecycle observation (consumer saw the transition) |
| `session_phase` | **new optional enum** `pre_open \| regular \| after_hours \| unknown` computed from `source_available_at` + exchange calendar. Absent today. Default `unknown` |
| `pit_class` | `source_event \| recorded_only \| snapshot \| unavailable` (FIF language) |
| Filing facts | FIF packet by `cik` + period; do not copy cells into the workspace |
| Reaction | join key `security_id` + window; store `not_joined` when bars/options vintages are missing |

Live AAPL lesson: do not stamp `source_available_at = generated_at`. That collapses the frontier to a single instant and makes every later reinterpretation look contemporaneous.

---

## 4. Reinterpretation contract (display / research)

A `reinterpretation.v1` row:

```
event_id
as_of_frontier          # the latest G0 state this reading is allowed to use
prior_reading_id | null
claim_ids[]             # event_claim.v1 or typed absence
fif_packet_id | typed_absence
reaction_geometry_id | not_joined
change_kind             # guidance | qa | filing | accounting | basis | reaction_confirm | reaction_reject | none
basis_match             # still required for any beat/miss language
authority               # context_only
```

`change_kind` is a **routing label for which source arrived**, not a causal claim. Co-movement of price and a Q&A sentence is not proof the Q&A caused the move.

If `basis_match` is false, the reading may say “headline number exists; legal beat/miss is withheld.” It may not say beat or miss. Already enforced on `metric_delta.v1`.

---

## 5. What this draft refuses

- A second R2 nest or program key.
- Promoting PEAD / fade / recovery to rank, size, or gate.
- Using Wire excerpt time as `source_available_at`.
- Using Company Facts without `accepted_at` as `FILING_RECONCILED`.
- Filling missing options/revisions with zero (`E0` incorporation law: unavailable ≠ 0).
- Implementing this before E2 renders the live AAPL workspace (`WS:EARNINGS-INTELLIGENCE-OS` next_action).
- Starting FIF-2 / FIF-7 from this draft.

---

## 6. Suggested later wave (not this PR)

Informational only. Product sequencing stays:

1. E2 — render live `event_workspace.v1` (already unblocked).
2. Per-source clocks on workspace `sources[]` (stop collapsing to `generated_at`).
3. `session_phase` helper + `FIRST_SESSION_CLOSE` join as display `not_joined`/`joined`.
4. FIF-7 convergence, then `FILING_RECONCILED`.
5. Structured `qa_exchange.v1` if E6 still wants it.
6. Only then: `reinterpretation.v1` as a research/display overlay.

---

## 7. Open implementation questions

Moved to `G0_OPEN_QUESTIONS.md`. The load-bearing one: **is `HEADLINE_AVAILABLE` a distinct document kind, or the first N bytes of the same Exhibit 99.1?** Default if unanswered: same document, two receipts (alert hash vs full-body hash), not a second kind.
