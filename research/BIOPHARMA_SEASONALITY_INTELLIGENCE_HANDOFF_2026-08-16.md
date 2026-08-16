# Biopharma Seasonality Intelligence — handoff, 2026-08-16

| Field | Binding value |
|---|---|
| Status | Session-close handoff; every claim below re-verified against `origin/main` today |
| As of | 2026-08-16 |
| Verified against | `origin/main` at `ba6a6665a971` |
| Supersedes | `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_CONTINUATION_HANDOFF_2026-08-07.md` |
| Original charter | `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md` |
| Authority ceiling | Unchanged. Shadow/context only. Every decision-authority boolean is false |
| Check-in mechanism | Admin console → Overview → **Seasonality program watch** |

> **Read this first.** Everything in §0 was re-checked against `origin/main` on
> 2026-08-16, not recalled from the session that built it. Where a later session
> corrected this work, §2 says so by name. Do not trust the 08-07 handoff's
> "remaining work" list — nine days of other sessions have moved past it.

---

## 0. What shipped

Twelve pull requests, built 2026-08-06/07, all merged and all present on `origin/main`
today. `engine/seasonality/` grew from 7 modules to 17.

Module paths in the two tables below are relative to `engine/seasonality/` unless
otherwise qualified.

| Wave | Deliverable | Module |
|---|---|---|
| W2A0 | `biopharma.event.v2` temporal contract | `contracts.py` |
| W2A | Dark fail-closed BioCatalyst adapter | `event_clock.py` |
| W2B | Event-study core, SPA/Reality Check, CAR | `event_study.py` |
| W1A/W1C | Point-in-time universe adapter | `universe.py` |
| W4 | Shadow market-response model + calibration | `model.py`, `calibration.py`, `regime.py` |
| W5 | Multi-clock Neural Web state v2 | `state.py` |
| W6 | Prophet narrative/attention overlay | `prophet_bridge.py` |
| W7 | Cross-symbol research browser + API | `screener.py`, `app/seasonality.py` |
| W2C/W3 | Catalyst mode + workstation UX | `templates/stock_seasonality.*` |
| — | Program watch + admin console panel | `program_watch.py`, `admin/program_watch.py` |

Fourteen seasonality test suites exist under `tests/`, plus 33 adversarial fixtures
under `tests/fixtures/seasonality/event_clock/`.

### The one idea worth carrying forward

The contract work is the part that will still matter in a year. `biopharma.event.v2`
makes fabricated precision **structurally impossible** rather than merely forbidden:
a source temporal carries `{precision, lower_bound, upper_bound, bound_rule}` and
**there is deliberately no single `value` field**. A consumer cannot collapse "Q3 2025"
to an instant because the contract never offers one. Everything downstream inherits
that property for free.

Three defects were caught by adversarial review before that PR landed, and each is
the kind that ships silently:

1. `upgrade_event_v1_to_v2` laundered v1's declared imprecision into a certified exact
   instant — a `date_precision="quarter"` row became `exact_time` with a **0-second
   span**, and downgrading it then *succeeded*. A one-way precision ratchet that
   erased the only surviving evidence of the fabrication.
2. Calendar spans used `fold=0` at `23:59:59.999999`, so in the **138 zone/date pairs
   since 2015** whose DST transition lands at midnight (Cairo, Khartoum, Asunción,
   Almaty) a span ended an hour early and consecutive spans left an hour of wall clock
   belonging to no period at all.
3. `validate_source_temporal` checked only bound *ordering*, so a one-second window
   could declare itself a `month_span`.

---

## 1. The largest gap: three engines are built but never run

This is the single most important thing on this page.

| Module | Production caller | Reality |
|---|---|---|
| `universe.py` | `scripts/build_stock_seasonality.py` | **Runs nightly** |
| `event_clock.py` | `state.py`, `program_watch.py` | **Runs nightly** (dark by design — no producer yet) |
| `screener.py` | `app/seasonality.py` | **Served on request**, no nightly artifact |
| `event_study.py` | *only the `__init__` re-export* | **Never executes** |
| `model.py` / `calibration.py` | each other, and tests | **Never produces a forecast** |
| `prophet_bridge.py` | **nothing at all** | **Dead** |

`scripts/build_seasonality_event_studies.py` and `scripts/build_seasonality_forecasts.py`
were specified in the original charter and **were never written**. The engines they
were meant to drive exist, are tested, and have no runner. Nothing appends to
`data/seasonality/forecasts.jsonl` because nothing calls the model.

This is why the availability flags in `site/seasonalitydata/methodology.json` are still,
correctly, `live_forecasts: false`, `live_screener: false`, `live_event_graph: false`.
They are honest. **Do not flip them to make the product look finished** — they describe
real absences, and the absence is the missing builder, not a missing flag.

**Next session's highest-value engineering task:** write those two builders, register
them in `config/dag.yml`, and let them accrue. That converts three tested-but-inert
engines into a system that produces evidence every night. Until then W2B and W4 are
libraries, not capabilities.

`prophet_bridge.py` is a separate case — see §3, the workflow-order defect.

---

## 2. What later sessions corrected in this work

Two commits after the build found real defects. Both are worth internalising because
the *shape* of each recurs.

**#5594 — a claim that was its own evidence.** `calibration.evaluate()` published
*"The forward ledger has zero matured grades"* as a standing fact. It became false on
2026-08-14 when `BDX:2026:219-224` graded, and nothing noticed — because **the only
test asserted the hardcoded literal against itself**. `evaluate()` never reads the
ledger, so a ledger fact never belonged in its output at all. The promotion decision
(`NONE`, shadow tier) was unchanged; the unowned claim was dropped and the test now
pins the decision instead of the sentence.

The general lesson, and it is the one I would most want the next session to hold: **a
receipt derived from the same variable it checks cannot fail.** If a test asserts a
string that the code also hardcodes, it is testing nothing. Ask of every claim in
output: *which artifact would have to change for this sentence to become false, and
does anything read that artifact?*

**#5592/#5594 — a field that went missing on one of two exits.** `grade_rows` has two
return paths; `tier=shadow` was stamped on both but tested on only one. The ungradable
close-out is a separate dict literal — which is exactly how the field went missing in
the first place.

**#5195** closed the three deferred follow-ups this session left open (the
`spa_reality_check` naming mismatch, the stale `config/synapse.yml` v1 notes, and Catalyst-mode
live verification). Those are done; do not redo them.

---

## 3. What is genuinely blocked, and cannot be unblocked by building

Three things. None of them yields to more code, and attempting to code around any of
them produces a fabrication.

**Point-in-time price adjustment does not exist.** `data/yahoo/*.parquet` is
current-vendor-vintage — retroactively adjusted for splits and dividends as of today —
so it cannot answer `asof(D)` for any historical D. `universe.py` therefore answers
identity questions from `data/symbol_directory/snapshots/` (real dated snapshots,
earliest `2026-07-13`) and returns an explicit **unavailable** for everything before
that, rather than falling back to the current roster. That fallback would be the exact
backward ticker leak the charter forbids. `foundation.py` already discloses this
truthfully (`price_adjustment_is_point_in_time: false`,
`universe_is_survivorship_biased: true`). **Leave those disclosures alone until replay
proof closes them**, which current data cannot produce.

**No BioCatalyst source is live.** `contracts/biocatalyst/` still contains no
seasonality event-projection schema. `clinicaltrials_gov_v2` is the only source with
`production_ingest_allowed: true` and it is globally dark. `event_clock.py` is
consequently correct and inert: it refuses wholesale anything whose `contract_id` or
`schema_version` does not match exactly, so the failure mode of an unratified contract
is *reads nothing*, never *reads it wrong*. **This is the sister session's lane. Do not
build a producer here** — that would create a second competing read plane.

**Evidence, not code, is the promotion bottleneck.** The forward ledger now holds 70
rows and **one** matured grade (`BDX:2026:219-224`, graded 2026-08-13). One grade
supports no promotion of anything. Nothing in this program is promotable, and no amount
of building changes that. Product completion is not promotion evidence.

**The W6 workflow-order defect remains open.** `build_prophet` runs *before*
`build_stock_seasonality` and `build_seasonality_shadow_state` in the nightly, so a
same-night overlay is structurally impossible. `prophet_bridge.py` has zero callers
partly for this reason. Fixing it needs a reviewed dependency-order change in a small
rebased wiring PR — `config/dag.yml` and `.github/workflows/daily.yml` are
high-collision files and belong in their own late PR.

---

## 4. How you will be told to come back

The operator asked not to have to poll. That is wired.

`scripts/build_program_watch.py` runs nightly (registered in `config/dag.yml`) and
evaluates four tripwires against **real artifact state**, never a static checklist.
`admin/program_watch.py` serves them to the authed admin console, where each fired row
carries a **copy-to-clipboard button** producing a self-contained prompt naming this
document.

The admin console is the right home precisely because it is password + signed-cookie
authed: operator prompts, PR numbers, and module paths are safe there in a way they
were not on the public Calibration Lab.

Current state of the four tripwires as of today:

| Tripwire | State |
|---|---|
| `first_matured_grade` | **FIRED** — the first grade landed 2026-08-13 |
| `catalyst_render` | **FIRED** — Catalyst mode is live on the built page |
| `deferred_followups` | unavailable |
| `biocatalyst_event_contract` | waiting — sister session has not landed it |

Two design decisions in that watch are load-bearing and should not be "simplified":

- **An absent or corrupt artifact renders loudly**, headed *"Watch unread — no artifact
  to read"*, because an empty panel is indistinguishable from a quiet one. The corrupt
  branch says outright: *this is not an all-clear.*
- **The as-of lag threshold is 5 days, not 2.** At 2 the panel would fly a stale banner
  every night against normal data latency, which is precisely how an alert trains its
  reader to ignore it. Freshness is tracked as two separate questions — the artifact's
  market as-of, and when the file was last written — because "built last night from
  two-day-old data" and "built five days ago" are different problems.

`deferred_followups` reading `unavailable` rather than `waiting` is worth one look: it
means the checker cannot currently evaluate that condition. An unavailable tripwire is
an honest state, but a *permanently* unavailable one is a broken check.

---

## 5. What I want the next session to know

**Read `docs/ACTIVE_BUILD_MAP.md` and `research/DO_NOT_REBUILD.md` before proposing
anything.** Nine days of other sessions have moved main a long way past this work.

**The gauntlet is a promotion gate, not a build gate.** Context, data, detection, and
tagging infrastructure ship display-tier freely. A null never blocks building or
accrual. This program's remaining work is almost entirely display-tier and can proceed
without waiting on evidence — but it also cannot claim authority from having shipped.

**Resist the pull toward W8.** Options-implied geometry, analogue integration, portfolio
clustering — it is the obvious "keep building" answer and it is the wrong one. W8 adds
surface area to a system whose every estimate is currently unpromotable, and it was
always gated on real ledgers. The ledgers hold one grade.

**Prefer wiring what exists over writing what does not.** The highest-value work
available is unglamorous: two builder scripts and a DAG registration that turn three
tested engines into nightly evidence. That is worth more than any new module.

**Adversarial review earned its cost here.** Every one of the three W2A0 defects, the
`TypeError` that let one malformed row destroy an entire batch in `event_clock.py`, and
the `RecursionError` at 0.48% of the size ceiling were found by review, not by the
build. Mutation-test the guards: on this program, 20 of 34 adversarial mutations
survived the first test suite. A guard that has never been watched to fail is a guess.

**Say what is absent.** The most valuable single property of this codebase is that
`unknown`, `unavailable`, `unresolved`, and `quarantined` are output states rather than
silent zeros. Preserve that. The temptation to make a surface look complete by
defaulting a missing value is how a research product becomes a liar.

---

## 6. Definition of completion, restated honestly

The product is substantially built. It is not finished, and finishing it is not the
same as making it trustworthy.

- **Built and running:** calendar clock, selection accounting, PIT universe adapter
  with honest unavailable states, dark event adapter, Neural Web shadow lobe, Catalyst
  mode, program watch.
- **Built and inert:** event studies, market-response model and calibration, Prophet
  overlay. Needs two builder scripts and one dependency-order fix.
- **Blocked on data, not effort:** point-in-time price vintage, live clinical sources.
- **Blocked on time:** calibration evidence. One matured grade.

Full product completion does not authorise signal promotion. If the promotion gates
remain unpassed, the completed system stays a superior context and research product —
**and must say so plainly on every surface that shows a number.**
