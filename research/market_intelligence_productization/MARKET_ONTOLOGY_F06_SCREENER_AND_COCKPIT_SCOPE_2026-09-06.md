# Market Ontology F06 — Research Screener and Second-Issuer Cockpit Scope Freeze

**Date:** 2026-09-06
**Status:** `SCOPE_FREEZE / RECORDS_ONLY / NO PRODUCT EFFECT`
**Lane:** `marketontology-b4-f06-screener-cockpit-scope` (wave B4, Meta-CEO B)
**Coordinating workstream:** `WS:MARKET-OS` (F06 lane)
**Ledger rows dispositioned:** `MO-DELTA-002`, `MO-PAID-021`
**Merge gates:** `#6920` (second issuer), `#6905` (valuation posture V1)
**Capability delta of this document:** `NONE`

## 0. Acceptance gates

Not done unless:

1. This doc states, in plain product words, what the screener answers
   ("which names deserve a look first, and why") and states explicitly that it
   never emits a rank, score, size, or gate.
2. It enumerates the second-issuer cockpit's B1B panels and marks each as
   display-only over a frozen `security_state.v1` object.
3. It names the two DNR keys as binding and records the exact merge gate
   (`#6920`, `#6905`) each build slice waits on.
4. A test asserts the doc contains both ledger row ids, an explicit
   "no ranker / no score / no size" line, and the two DNR keys; pytest green.
5. LIVE PROOF: after squash-merge the file is readable at its blob URL on
   main and the new test appears green in the merged-head ci.yml pack run.
6. Neither build slice begins here — this packet ships zero code, zero
   template, zero pixel, and does not edit the F00C ledger CSV.

## 1. What the research screener answers

One sentence, plain product words:

> **The research screener answers one question: which names deserve a look first, and why.**

MO-DELTA-002 names four filter families. Each is a plain-word lens over
existing owner-attributed signal, not a discovered score:

| Filter family | Plain-word description | Owner |
|---|---|---|
| Theme | Which macro/sector theme a name sits inside | GMI theme owners (unbuilt on main) |
| Catalyst | What dated event is coming up for a name | `legs.catalyst` (`security_state.v1`) |
| Exposure | Whether the reader already holds the name | `legs.personal_impact` |
| Valuation posture | Whether the name looks cheap/rich against reported fundamentals, under stated assumptions | `engine/valuation_scenario.py` (OPEN `#6905`) |

## 2. The no-ranker ceiling (BINDING)

**Ceiling (binding): the research screener emits no ranker / no score / no size and
no gate.** It orders nothing, scores nothing, sizes nothing and gates nothing. It is
`research_priority_only` and is **never a trade ranker**. Every "why" it prints is an
owner-attributed, checkable reason — not a number the product invented.

Raising this ceiling is a PROMOTION, not a build: it requires the epistemics gauntlet
(pre-registered gates, held-out evidence, printed nulls) and an explicit adjudication.
Display-tier ships freely; authority does not.

## 3. Second-issuer cockpit — the B1B panel map (all display-only)

The cockpit is a projection. It composes nothing: every panel reads the frozen
`security_state.v1` object and renders it.

`legs.opportunity_context.dislocation` and `legs.opportunity_context.market_incorporation` are OUT of panel 5 for this packet — no B1B panel reads them yet; a future slice that surfaces either needs its own scope record.

| # | Panel | Frozen source in `security_state.v1` | Tier |
|---|---|---|---|
| 1 | Overview | `coverage` + `dominant_degradation` + `legs.state.summary` | `display_only` |
| 2 | Evidence | `legs.evidence` (K1 `EvidenceRef` / `EvidenceBlock` ids only) | `display_only` |
| 3 | Event chronology | `legs.change` (`event_refs`, `source_available_at`, `correction_state`) | `display_only` |
| 4 | Company drivers | `legs.state.deterministic_state_refs` | `display_only` |
| 5 | Prophet and availability | `legs.opportunity_context.prophet.{ref, state, reason}` and `legs.opportunity_context.entry.{state, available, null_reason}` | `display_only` |
| 6 | Risks / failed gates | `legs.risk` (`risk_refs`, `failed_gates`, `strongest_unresolved_fact`) | `display_only` |
| 7 | Next observables | `legs.catalyst` (`next_observables`, `deadlines`) | `display_only` |
| 8 | Owner/model receipts | `identity_proof`, `as_of`, `content_sha256`, per-leg receipts | `display_only` |

**Ruling on the seventh leg.** `legs.personal_impact` gets NO panel of its own. It
renders as one exposure row inside Overview and prints `NOT_APPLICABLE` in plain words
when the reader holds nothing. It is never a ninth panel and never a new header —
the site has exactly two nav families and this packet adds no third.

**Authority echo (verbatim from the shipped compiler).** Every panel inherits
`can_rank: false`, `can_gate: false`, `can_size: false`, `can_originate_signal: false`,
`can_execute: false` from the object's `authority` block. A panel may not add authority
the object does not carry.

## 3b. Disposition: chart-first Terminal/Desk projection is NOT in this map (and why)

`agentos/workstreams/WS-MARKET-OS.md` defines wave **B1B-B6** as "Terminal/Desk
projection and chart-first security cockpit over frozen `security_state.v1`", and
`MARKET_ONTOLOGY_F00B_CURRENT_CAPABILITY_CROSSWALK_2026-08-28.csv:25` records
"Chart-first security cockpit (B1B-B6) unbuilt". The eight-panel map in §3 above is
deliberately **not** that surface, and this section is the disposition the crosswalk
row is missing:

- **What §3 freezes:** the *first* B1B slice only — a plain-word, tabular reading of
  `security_state.v1` (Overview through Owner/model receipts). No chart renders
  anywhere in that map; every row is text/table, by design of this scope freeze.
- **What is deferred, not dropped:** the chart-first Terminal/Desk projection
  (candlestick/series view, cross-linked to the Terminal per the funnel-follows-the-
  experience law) is **wave B1B-B6's own later slice**, gated the same way every
  other build slice in this doc is gated — behind `#6920` (second issuer) plus a
  dedicated design pass, because a chart panel is a taste-as-deliverable surface
  under the Design lane, not a mechanical table row.
  - **Disposition recorded:** the B1B-B6 chart/Terminal-Desk panel is
    `SCOPE_DEFERRED` — no ceiling change, no ranker, no authority; it inherits the
    same `can_rank: false` / `can_gate: false` / `can_size: false` block as every
    panel in §3 once it ships. It is out of scope for *this* records-only packet,
    which ships zero code, zero template, and zero pixel (§0.6, §7).
  - **Why it is not a ninth row in the §3 table:** §3 enumerates the panels this
    scope freeze is dispositioning *now*; a chart panel with no design spec pinned
    would be exactly the "component assembly on unpinned design" failure this
    program's spawn-handoff law forbids. Freezing its scope here, without inventing
    its markup, keeps the ceiling honest.

## 4. Nulls are printed, in plain words

All nine `coverage_state` values and their reader-facing wording:

| `coverage_state` | What the reader sees |
|---|---|
| `AVAILABLE` | (no chip — the panel just shows its content) |
| `NOT_COVERED` | "We do not cover this for this company yet." |
| `NOT_APPLICABLE` | "This does not apply to you right now." |
| `UNAVAILABLE` | "We could not read this. Nothing is being hidden — it is missing." |
| `STALE` | "This has not refreshed since <time>. Treat it as old." |
| `RIGHTS_BLOCKED` | "We are not allowed to republish this source here." |
| `CONFLICTED` | "Two sources disagree. We are not picking a winner." |
| `CORRECTED` | "The source corrected this. You are seeing the corrected read." |
| `PARTIAL` | "Some of this is here, some is not." |

A null is DISCLOSED. It is never blanked, never back-filled, never guessed. No
falsifier/refutation vocabulary appears on any reader-facing surface.

## 5. Binding DO-NOT-REBUILD keys

Both rows are BINDING on every F06 build slice:

- `KILL-CAUSAL-DAG-ALPHA` (`research/DO_NOT_REBUILD.md:52`) — no discovered graph, no
  screener output, and no cockpit panel may become an alpha score, a trade, or a
  portfolio construction. Proposal/audit tier only.
- `KILL-LLM-CONFIDENCE` (`research/DO_NOT_REBUILD.md:54`) — no LLM numeric confidence
  anywhere. The LLM may de-escalate a calibrated key; it may never originate a signal,
  a score, or an escalation.

## 6. Merge gates each build slice waits on

| Slice | Waits on | Why |
|---|---|---|
| Second-issuer cockpit (MO-PAID-021, B1B) | `#6920` | The cockpit needs a real second-issuer `security_state.v1` object; #6920 is the ListingAlias→ListingKey renderer + `issuer_cik` reader exposure that mints one (MSFT). Until it merges there is exactly one issuer to render. |
| Screener valuation-posture filter (MO-DELTA-002) | `#6905` | The valuation-posture axis has no owner on main; #6905 lands `engine/valuation_scenario.py` (reported SEC fundamentals, one issuer). |
| Screener theme / catalyst / exposure filters | GMI theme owners (unbuilt) | Named as a dependency, not as a gate PR. No build begins until an owner exists. |

Both gate PRs are OPEN as of 2026-09-06. This record states the gate; it does not
predict a merge.

## 7. What this packet does NOT do

- ships no code, no template, no pixel, and no route;
- does not edit the F00C ledger CSV (see §8);
- does not begin either build slice;
- copies no proprietary Market Ontology code, text, data, or asset — the URL
  `https://marketontology.com/stock-research` is cited as a capability observation only.

## 8. Ledger disposition

| Row | Disposition recorded here | CSV state (unchanged by this packet) |
|---|---|---|
| `MO-DELTA-002` | SCOPE FROZEN — `research_priority_only`, ceiling written, build deferred to the #6905 gate + GMI theme owners | `NOT_BUILT` |
| `MO-PAID-021` | SCOPE FROZEN — `display_only`, 8-panel map bound to the frozen object, build deferred to the #6920 gate | `PARTIAL` |

The CSVs are not this packet's to write. "Closed" means the scope question is
answered in writing; the ledger row's build state changes when the build lands.

## 9. Theme obligations inherited by the build slices (nothing ships here)

This packet renders zero UI, so it owes no evidence matrix. Every future slice does,
and may not treat token substitution as a light design:

- **Dark (command center):** luminance depth, instrument calm, restrained glow; the
  degradation chips read as instrument states, not as alarms.
- **Light (research workspace):** cool canvas, white material, hairline discipline,
  shadow instead of glow; the same chips read as printed annotations.
- **Intentionally different mechanisms:** chip elevation (glow vs. hairline+shadow) and
  panel separation (luminance step vs. rule).
- **Evidence matrix required at build:** dark/light x EN/ZH x desktop 1440 / mobile 390.

## 10. Entry point and live URL

Reachable from the `research/market_intelligence_productization/` directory listing,
where this filename sorts among its `MARKET_ONTOLOGY_F0*` siblings.

Live: https://github.com/mastermindx-market-intelligence/macro/blob/main/research/market_intelligence_productization/MARKET_ONTOLOGY_F06_SCREENER_AND_COCKPIT_SCOPE_2026-09-06.md
