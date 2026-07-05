# News Intelligence Upgrade — Assessment & Fable Handoff Brief

**Source:** external ChatGPT "Mastermind News Intelligence Upgrade Plan" (`~/Downloads/news_intelligence_upgrade_plan.md`) — written from the *live site only, no repo context*.
**Author of this brief:** Opus 4.8, grounded against the actual codebase (2026-07-04).
**Purpose:** tell Fable what's real, what's already built, and where the genuine gaps are — so the upgrade program starts from evidence, not the doc's (partly wrong) theory.

---

## 1. One-paragraph verdict

The doc's architectural instincts are *right* and match what we already run (deterministic-filter-first → event-study/ledger-graded → context-only, never alpha → routed into engines). That convergence is validation, and it also means **~60–70% of the doc is already built, usually more maturely.** Its central *diagnosis* — "the filter over-weights source reputation and keeps finance-looking headlines" — **is wrong for our system** (verified): hard-reject runs *before* source scoring; tier never launders garbage. The real problem is narrow and specific: a handful of **reject-family gaps** + **no macro-surprise parser**. Take the doc as a problem statement and Phase-0 punch list, not an architecture to adopt wholesale.

---

## 2. Verified findings (all reproduced against the code)

The page the doc critiqued is the **macro** feed: `macro_news.macro_headlines()` → `news.html.j2` (rendered by `scripts/build_site.py:3115`). It is **theme-tagged, not ticker-tagged** — this changes several of the doc's ticker-centric fixes.

| Doc complaint | Verified root cause | Status |
|---|---|---|
| Nuveen dividend survives | `"dividend"` is a **positive** `capital_return` keyword (`macro_news.py:83,162`); no fund-distribution reject | real gap — **fixed in Phase-0 PoC** |
| Netflix streaming guide survives | NFLX is a tracked entity (`macro_news.py:206`); no lifestyle reject family | real gap — **fixed** |
| Walmart payroll-tax survives | `_ADVICE_OPENER_RE` is an anchored fixed-verb whitelist; misses "At 76, I'm…" / "'I claimed…'" | real gap — **fixed** |
| "Ahead of earnings" preview survives | `_PREVIEW_RE` had no "what you need to know ahead of" branch | real gap — **fixed** |
| Raw macro-release titles ("Manufacturing and Trade Inventories and Sales") | **no actual/prior/consensus/surprise parser exists** anywhere in `engine/` | real gap — **Phase 2 (Fable)** |
| "Filter over-weights source tier" | **False** — `is_low_value()` runs first (`macro_news.py:539`); tier can't override | doc premise wrong |

The filter *is* already wired into the critiqued page and is sophisticated (`news_common.is_low_value`, regex families for roundups/previews/advice/pickmill bylines). The leaks are **category gaps, not an unwired filter.**

---

## 3. Already built — DO NOT rebuild (boring-baseline trap)

The doc proposes scaffolding we have in more mature form. Building its version = a parallel system.

| Doc proposes | We already have | Note |
|---|---|---|
| Structured event store + clustering + novelty (§5, §12) | `engine/qbus.py` — `event_key` shingled-title clustering, `novelty_z()`, `echo_stats()`, no LLM | wire, don't rebuild |
| Falsifiable forward-return ledger (§8, §15) | `engine/qledger.py` — forward 1d/5d/21d, PIT keep-first embargoes | the doc's best idea, already live |
| Route into engines (§11) | `intel_hub.py` (per-ticker dossier), `alert_triage.py` (0–100 triage), `master_brain.py` | substantially done |
| Deterministic-first, LLM-for-borderline (§14) | exactly our design: `news_common` gate + `news_llm` re-rank-only | done |
| New SQL tables + `scripts/news/` + `config/news/` tree (§12, §17.3) | parquet + `engine/` modules, PIT keep-first | **skip entirely** |
| Special Situations dedup (§11.1) | EDGAR + newswire desk, keep-first `first_seen` | done |

**Hard firewall the doc doesn't know about:** news engines are `LEAF` / `is_context_only=True` — *nothing in the scoring/allocation path imports them* (PIT integrity). The doc's "route news into allocation/BRAIN scoring" language must be constrained to **context-injection only**. Non-negotiable.

---

## 4. Genuine net-new builds (worth doing)

1. **Macro-release surprise parser — highest value, mostly plumbing.** We have the *calendar* (`event_calendar.py`) and `news_vector` stamps `scheduled_ref`, but never parse **actual/prior/consensus/surprise**. Data plumbing already exists (FRED access + `real_activity_nowcast`). Doc's fallback hierarchy (consensus → revised prior → trailing trend → z-score → nowcast deviation) maps directly onto assets we own. This is the doc's single best build. Suppress raw release stubs until parsed.

2. **Theme/entity centrality — reframed for our macro feed.** Doc frames it as *ticker* centrality (primary/secondary/incidental). Our macro feed is **theme-tagged**, so the analog is **theme incidentalness** (Nuveen hit `capital_return` on "dividend"; Walmart hit `labor` on "payroll"). Cheap deterministic first (keyword-in-title-subject-position + `entity_resolver` confidence), LLM only for borderline.

3. **Reject-reason log + regression tests.** We reject silently. A logged `reject_reason` per drop is how you *catch* leaks systematically. **Started in the PoC** (`low_value_reason()` + `tests/test_news_reject_leaks.py`). Adopt the doc's regression headlines verbatim.

---

## 5. Additions / better-than-doc ideas

- **Diagnose-then-patch, not new architecture.** The fastest 80% win = the three reject gaps + reject log (done in PoC), not a rebuild.
- **Grade the *rejects*, not just the keeps.** Run rejected items through `qledger` occasionally — if a reject class hides forward-edge items, we're over-filtering. Guards the failure mode the doc's aggressive-reject philosophy creates.
- **"dividend" keyword scoping > blocklist.** The clean Nuveen fix is also to scope `capital_return`'s bare `"dividend"` to *changes* ("raises/cuts/initiates") and exclude fund issuers — narrower and more correct than a reject rule alone.
- **Reuse `qbus.novelty_z` / `echo_stats`** for the doc's "novelty_score" and "event clustering" instead of new clustering.

---

## 6. Roadmap mapping (doc's 5 phases → our reality)

- **Phase 0 (immediate cleanup):** DONE in PoC (4 of 6 leaks) + reject log seed.
- **Phase 1 (structured event object):** largely exists (`qbus`); add semantic `event_type`/materiality/direction/horizon layer only where routing needs it.
- **Phase 2 (macro parser):** **real work — the priority build.**
- **Phase 3 (engine routing):** mostly exists (`intel_hub`/`alert_triage`); respect the LEAF firewall.
- **Phase 4 (ledger/calibration):** exists (`qledger`); extend to grade rejects.
- **Phase 5 (BRAIN integration):** exists (`master_brain`); context-only.

Net: the doc's roadmap telescopes to **Phase 0 (done) + Phase 2 (macro parser)**; the rest is wire-up of live systems.

---

## 7. Phase-0 PoC delivered with this brief (uncommitted seed)

Verified, on the current working tree (needs landing on a fresh branch off `main` at merge time):

- `engine/news_common.py` — added `low_value_reason()` (reject-reason core; `is_low_value()` now delegates), reject families `_FUND_DIST_RE`+`_FUND_VEHICLE_RE`, `_LIFESTYLE_RE`, `_PF_TOKEN_RE`+`_FIRST_PERSON_RE`; extended `_PREVIEW_RE` for "ahead of earnings".
- `tests/test_news_reject_leaks.py` — 12 tests: 5 doc garbage headlines DROP with expected reason, 6 real stories KEEP (false-positive guard incl. "Apple raises dividend", "Netflix raises streaming prices", "Social Security trust fund depletes"), 1 documents the macro-stub Phase-2 boundary.
- **Result:** `12 passed`; broader news suite `83 passed` (no regressions).
- **Known boundary:** macro-release stubs still leak the title-only gate by design — suppressing needs the Phase-2 release registry, not a title regex.

**Next wire-up (small):** have the three `is_low_value()` call sites (`macro_news.py:539`, `financial_news.py:186`, `news_rss.py:186`) capture `low_value_reason()` into a rejected-items artifact → the doc's "Rejected Garbage Log" UI section.
