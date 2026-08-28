---
key: CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS
claim: >
  P1-R2 (PR #6229, merge c11b16500c15) made malformed-announcementId exclusions
  typed and counted but gave them PER-RUN, PLANE-GLOBAL temporal semantics, which
  produces two opposite lifecycle failures depending only on WHERE the malformed
  row sits. (LATCH) A malformed institutional_visit row already inside
  data/china_filings/filings.parquet is re-read as a candidate on every
  subsequent run — collectors/china_visits.py refresh() computes typed_exclusions
  over the whole ACCRUED candidate set, not a nightly delta — so
  `upstream_degraded` fires forever with no in-code exit; measured over five
  consecutive simulated nights the plane returned upstream_degraded every night,
  never reached _stamp_coverage_start_once(), and left coverage_start=None and
  last_success_utc=None, which renders EVERY A-share name `no_coverage`
  permanently: the plane can never start. (FORGETFULNESS) A NEWLY malformed row
  is excluded by china_filings.write_filings() at the store boundary, so it never
  enters filings.parquet and china_visits never sees it as a candidate; its only
  trace is the process-local LAST_RUN_OUTCOME.key_integrity of the SAME run.
  china_filings._NIGHTLY_LOOKBACK_DAYS == 3, so once the announcement ages out of
  the CNInfo re-pull window the plane returns clean `ok`; measured over five
  simulated nights, night 1 degraded and nights 2-5 read status `ok` with
  coverage_start stamped and candidate_accounting
  {eligible:1, represented_downstream:1, typed_exclusions:0} — arithmetic
  perfectly balanced and completely blind to the excluded company, which then
  satisfies engine/china_intel_hub.py _visit_block()'s measured_no_event
  precondition (status ok + coverage_start set + zero rows) and renders a FALSE
  clean "no institutional-visit filing observed for this name".
falsifier: >
  Run the reproduction directly against the merged bytes, independent of any
  working tree: read collectors/china_filings.py and collectors/china_visits.py
  from `git show c11b16500c15:<path>`, exec each into a module registered in
  sys.modules under its real dotted name (so china_visits' lazy
  `from collectors import china_filings as _cf` resolves to the same bytes),
  point lib.config.data_dir at a tmp dir, and drive the two scenarios.
  LATCH: write a filings.parquet holding one category=='institutional_visit' row
  with announcementId=="" plus one well-keyed visit row, set
  cf.LAST_RUN_OUTCOME=None, call cv.refresh() five times. If any run returns a
  status other than "upstream_degraded", or cv.read_coverage_start() is ever
  non-None, the latch is disproven. FORGETFULNESS: call cf.write_filings() with
  one malformed and one well-keyed visit row, run cv.refresh() with
  LAST_RUN_OUTCOME carrying that key_integrity, then run it four more times with
  a zeroed key_integrity. If any artifact under data/china_visits/ still names
  the excluded company after night 5, or health.status is not "ok", the
  forgetfulness is disproven. Script preserved at
  scratchpad/probe_p1r2_defects.py (session 24e6d425).
so_what: >
  Never treat a typed exclusion as sufficient. An exclusion that is only COUNTED
  is not REMEMBERED: its truth has to outlive both the process that observed it
  and the upstream re-pull window that re-supplied it, or the instrument silently
  changes meaning as time passes. Two design rules follow for any absence-
  authority plane in this repo. (1) Compute a degradation signal over the DELTA
  you actually processed, never over an accrued store you re-read every night —
  a store-wide predicate turns one bad historical row into a permanent global
  outage with no exit. (2) Scope negative-authority suppression to the entities
  whose evidence is actually incomplete whenever scope is knowable; a plane-
  global refusal is honest only when the affected identity cannot be bounded.
  Concretely: a "does the current run look clean" boolean can never carry an
  absence claim across nights — that requires a durable, deterministically
  reconcilable record, which is what P1-R3 adds
  (DEC:CHINA-COVERAGE-EXCEPTION-LEDGER). Note both failures are REPAIR-INDUCED:
  the pre-#6229 code had neither, because it had no exclusion semantics at all
  (it silently dropped the row) — fixing a silent drop without designing its
  lifecycle moved the lie rather than removing it.
kind: landmine
verified_at: 2026-08-22
verified_by: >
  Session 24e6d425 (P1-R3 commission), 2026-08-22: scratchpad/probe_p1r2_defects.py
  executed against `git show c11b16500c15:collectors/china_{filings,visits}.py`
  exec'd into sys.modules under their real dotted names, lib.config.data_dir
  redirected to a tmp dir. LATCH output: nights 1-5 all
  `status=upstream_degraded n_excluded=1 coverage_start=None
  last_success_utc=None`. FORGETFULNESS output: night 1
  `status=upstream_degraded`, nights 2-5 `status=ok n_excluded=0
  coverage_start='2026-08-22' health='ok'`, final
  `candidate_accounting={'eligible': 1, 'represented_downstream': 1,
  'typed_exclusions': 0, 'exclusions_by_type': {}}`, 0 visits.parquet rows for
  the excluded company, and only health.json / visits.parquet / coverage.json
  on disk — none naming it. The dossier half was then closed first-hand by
  scratchpad/probe_p1r2_hub_half.py, which loads engine/china_intel_hub.py from
  the SAME merged commit and feeds _visit_block() exactly that end state
  (health ok, last_success fresh, coverage_start stamped, zero rows for the
  affected code): Company A returns state 'measured_no_event', detail "no
  institutional-visit filing observed for this name since coverage start",
  while the genuinely covered Company B returns state 'ok' n_total=1. The
  product therefore asserts a clean measured absence about a company whose
  visit filing the system did in fact observe. (The same precondition is
  independently pinned by
  tests/test_china_intel_hub_visits.py::test_measured_no_event_when_healthy_and_absent.)
scope: [macro, collectors/china_visits.py, collectors/china_filings.py,
        engine/china_intel_hub.py]
confidence: verified
---

Why this is the interesting half of the repair, not a footnote on it: #6229 was
correct about the MECHANISM (a malformed key must never be silently deduplicated,
discarded, or converted into clean absence authority) and it closed
[[DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP]] exactly as commissioned. What it
did not have to answer — because the commission bounded it to the two write
boundaries — is *how long the exclusion is true for, and over whom*. Those two
questions have no default answer, and the defaults it inherited (per-run,
plane-global) are each wrong in the opposite direction.

The two failure modes are mutually exclusive per row and jointly exhaustive: a
malformed visit observation either sits in the store (→ latch) or is stopped at
the boundary (→ forgetfulness). There is no third place for it to be, so #6229's
semantics could not be right for any malformed visit row at all. Only the
measured production reality — 54,078 accrued rows, zero malformed keys ever
(DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION evidence) — kept both branches
unreachable in practice, which is also why nothing in CI or in the accepted
145-row P1 production receipt could have surfaced them.

Related: [[DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP]] — the originating
finding, whose specific mechanism #6229 genuinely did repair.

## P1-R3A — a THIRD mode of the same defect, found by Sol reviewing the repair

The two modes above are exhaustive over WHERE a malformed visit row can sit.
They are not exhaustive over WHEN it is remembered. Sol's adversarial review of
the repair (PR #6242) found the remaining window, and it is the forgetfulness
mode again, one layer down:

**(CRASH WINDOW)** P1-R3 made the coverage exception durable, but only inside
`china_visits.refresh()` — AFTER `china_filings.write_filings()` had already
committed a filtered canonical store that omitted the observation. The only
bridge between the two was the PROCESS-LOCAL
`china_filings.LAST_KEY_INTEGRITY["excluded_rows"]` handoff. A hard kill between
the filtered `filings.parquet` write and the ledger write therefore erased the
observation from EVERY durable store at once: absent from `filings.parquet` by
construction (key integrity excluded it), never written to
`coverage_exceptions.parquet`, and aged out of CNInfo's 3-day re-pull
(`_NIGHTLY_LOOKBACK_DAYS == 3`) within days. The asia lane runs under a hard job
kill, so the window is operational, not theoretical.

The general shape worth carrying forward: **a durable repair for a forgetting
bug is not durable until the write that CAUSES the forgetting is ordered behind
it.** Making the memory durable and making it durable *first* are different
properties, and only the second one survives a crash. Repaired in P1-R3A by
inverting the order — `durable coverage exception -> canonical filtered commit`
— and by refusing the canonical commit outright when the exception cannot be
persisted; see [[DEC:CHINA-COVERAGE-EXCEPTION-LEDGER]] §"Amended by P1-R3A".

Falsifier for this third mode: call `china_filings.write_filings()` with one
malformed `institutional_visit` row, then never call `china_visits.refresh()` at
all (the crash). If `data/china_visits/coverage_exceptions.parquet` does not
already hold the observation, the window is open. Pinned live by
`tests/test_china_visits_collector.py::TestP1R3ACrashConsistencyFence`.
