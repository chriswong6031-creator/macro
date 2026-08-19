# G0 Reaction Geometry Input Matrix

**Question:** what inputs could a display-only `reaction_geometry.v1` consume, who owns them, and which G0 frontier state they may legally speak at?

**Law:** this is not a trading model. Co-movement ≠ causation. Unavailable ≠ 0. PEAD copy on the stock page is not a CEI field.

---

## 1. Geometry legs (research enum)

| Leg | User question | May speak at frontier | In-estate owner | Join key | PIT class today | CEI status |
|---|---|---|---|---|---|---|
| G0 pre-event drift | Did the tape move before any legal text? | `PRE_EVENT` only | daily bars (`data/massive_stock_day`, Yahoo) via winner-case tape; **not** CEI | `security_id` + calendar | Daily bars exist; no event join | not_joined |
| G1 overnight / AH print | First print after `FULL_RELEASE.source_available_at` | `FULL_RELEASE`+ | same bars; open often missing (CHWY case: open prices null) | `security_id` | UNKNOWN session phase | not_joined |
| G2 first regular close | Close of first NYSE session after release | `FIRST_SESSION_CLOSE` | same | `security_id` + exchange calendar | UNKNOWN without session calendar join | not_joined |
| G3 hold vs fade 3/5/10d | Did the gap hold? | after G2 matures | winner-case local tape | `security_id` | CODE VERIFIED in winner cases; not CEI | not_joined |
| G4 implied move vs realized | Was the move large vs options’ ex-ante | `PRE_EVENT` (implied) vs `FIRST_SESSION_CLOSE` (realized) | `engine/event_window.py` `ex_ante_read` / `implied_move_pct`; GEX JSON from ~2026-06 | ticker, not `security_id` | ACCRUING 2026-06+; earlier **unavailable** | not_joined |
| G5 IV crush / straddle | Did options reprice after? | after G2 | GEX / options sparse selector (Advanced Data Options). Prophet display-only | ticker | ACCRUING 2026-06+ | not_joined |
| G6 revision breadth | Did the Street move after the print? | `ANALYST_REVISION_STATE` | `engine/analyst_revisions.py`; `collectors/equity_revisions.py`; Finnhub recommendation parquet | ticker | ACCRUING 2026-06-16+; yfinance snapshots lookahead-contaminated historically (intelligence-hub research) | unlicensed on CEI |
| G7 peer / group | Did silent peers move? | never a CEI verdict; consume `group-reads` | `engine/group_earnings.py` | basket, not event | live group pulse; not event-mechanism | SPEC_ONLY at event level (E0 ledger) |
| G8 attention | Did the print get read? | optional display | Quiver / Hot Tape — thin historically | ticker | PARTIAL | not a CEI field |

---

## 2. Existing reaction surfaces (do not fork)

| Surface | What it is | Authority | May G0 read it? |
|---|---|---|---|
| `event_digest.market_reaction` | Forced `{status: not_joined, as_of: None, security_ids: []}` | context_only | Yes — this **is** the honest CEI default. CODE VERIFIED `digest.py` L397–400 |
| `event_workspace.completeness.reaction` | `{status: not_joined}` + warning `reaction_not_joined` | context_only | Yes — live AAPL. PRODUCTION VERIFIED |
| `promotion.py` `_FORBIDDEN_INPUTS` | `consensus`, `market_data`, `market_reaction`, `theme_context`, `trading_action` | n/a | Do not feed these into Wire promotion |
| Stock-page PEAD copy | `templates/stock.html.j2` ~1580–1645 (E0 ledger) | display | Consume as a **different product sentence**, not as CEI geometry |
| `engine/event_window.py` | 1-day implied move from ATM IV; `ex_ante_read` | context / MRI-adjacent | Display only; not event-joined |
| Winner cases `research/winners/cases/*.md` | 154 YAML `winner_case.v1` with local tape | research | **Primary historical geometry library**. Owner is winners / opportunity-evidence, not Earnings |
| E0 incorporation casebook | I1–I7 legs | research | Cite, do not copy-own |
| Advanced Data Options intel brief | implied-move / skew / OI heuristics; Prophet multiplier removed | display, uncalibrated | Do not import into CEI as authority (`WS:ADVANCED-DATA-OPTIONS`) |
| Prophet / SUE | SUE is a confirmer floor in `stock_score` US edge (docs/site_semantics) | scored path **outside** CEI | **Do not** route G0 geometry into Prophet. Commission: no Prophet change |

---

## 3. Mapping G0 archetypes → required legs

Commission archetypes. A row is **gradable** only if the named legs are not `unavailable`.

| Archetype | Min legs | CEI may currently grade? |
|---|---|---|
| Negative gap / full recovery | G1 or G2 + G3 hold | No — reaction not_joined |
| Positive gap / fade | G1/G2 + G3 fade | No |
| Headline beat / deep weakness | `basis_match` + G2 | No — consensus unlicensed **and** reaction not_joined |
| Headline miss / deep strength | same | No |
| Accounting contradiction | FIF `disclosure_changes` / cells vs release facts | No — FIF-7 todo; live workspace has 2 facts |
| Guidance reinterpretation | `guidance_item.v1` vs later item | Partial — live AAPL has one introduced range; no history series |
| Q&A-driven reinterpretation | `qa_exchange.v1` + later geometry | No — `qa_exchanges: []` |
| Basis mismatch / no legal beat-miss | `metric_delta.basis_match=false` | **Yes, already** — live AAPL delta is this cell |
| Reaction confirmed | G3 hold + no later FIF contradiction | No |
| Reaction rejected | G3 fade **or** later filing/QA/guidance change | No as a CEI verdict; winner `failed_breakaway` is a **research** label |

The only archetype the live estate can emit without lying is **basis mismatch / no legal beat-miss**. That is a feature, not a gap.

---

## 4. Session timing

No CEI field records after-hours vs premarket vs open.

Draft helper (not built):

```
session_phase(source_available_at, mic) -> pre_open | regular | after_hours | unknown
```

Until that exists, G1 (overnight) and G2 (first close) cannot be distinguished. Winner cases that report “gap +26.15% prior close to open” (NVDA 2023) are CODE VERIFIED **in that file**, not in CEI.

CHWY 2022 explicitly nulls opening gaps because Yahoo opens were absent. Treat open-gap as UNKNOWN unless the named price file has opens.

---

## 5. PIT fences for a future join

| Input | Fence |
|---|---|
| Daily bar | Bar date ≥ calendar date of `source_available_at` in the listing TZ; do not use `generated_at` |
| Intraday | Required for true AH prints; **UNKNOWN whether CEI will ever hold it** |
| Options | If `source_available_at` < 2026-06-15 → `unavailable`, not 0 |
| Revisions | If as-of < 2026-06-16 → `unlicensed_absent` / `accruing` |
| Consensus | Stay typed absence until a licensed vintage exists |
| FIF cells | `historical_replay` + both cutoffs; CF rows with `accepted_at is None` are not PIT |

---

## 6. Recommended CEI shape when a join is cheap (E2-or-later, display)

```
reaction: {
  status: not_joined | joined | unavailable,
  security_ids: [...],
  as_of: <first_session_close | null>,
  session_phase: unknown | after_hours | ...,
  legs: { g1: typed_absence|number, g2: ..., g3: ... },
  options: unavailable | not_joined | snapshot,
  revisions: unlicensed_absent | accruing | joined
}
```

Do not add `beat`, `alpha`, or `confirmed: true`. Confirmation is a research label on a casebook row, not a workspace field.

---

## 7. No-build warnings

- Do not rebuild PEAD inside Earnings (`stock.html` already speaks).
- Do not infer signed options flow without NBBO (`research/OPTIONS_FLOW_DATA.md`, cited by NVDA 2023 case).
- Do not use 13F as episode-timely sponsorship (`DNR:KILL-OWNERSHIP-BREAKAWAY` / NEXTL-U13; winner cases already refuse this).
- Do not calendar-gate risk-radar with this geometry (`DNR:KILL-CALENDAR-GATED-RISK`).
