---
key: HK-G1-FIXTURE-BANDS-THE-REFRESH-SUFFIX
question: >
  tests/test_hk_board_rank.py::TestG1FixtureIsNotStale::test_source_panel_history_is_unchanged
  pinned the frozen G1 close window by exact equality against the live, nightly-rewritten
  data/hk_search/closes_deep.parquet, and went red when 2359.HK's trailing rows were
  re-based by an ex-dividend. Regenerate the fixture, widen to a relative tolerance, or
  band a different quantity?
answer: >
  Band the SHAPE the collector can actually produce. The check keeps its exact date
  assertion and now classifies close drift with `rescale_diagnosis`: drift is admissible
  only when every changed row runs contiguously to the END of the window, shares one
  factor to within the fixture's own 3dp quantum, and that factor lies inside a routine
  cash-dividend band of [0.90, 1.10]. Anything else — a rewrite that stops short of the
  newest row, a non-uniform move, or a corporate-action-scale factor — is reported as a
  REVISION and fails, demanding re-adjudication rather than a re-stamp. The fixture
  itself is NOT regenerated and no committed number moves.
rationale: >
  The suffix constraint is derived from the collector's mechanism, not fitted to the
  observed drift, which is what separates this from widening a tolerance until the red
  goes away. HkClosesDeepAdapter re-fetches _INCREMENTAL_PERIOD="2mo" with
  auto_adjust=True and merge-upserts it, so the ONLY rows it can re-base are a trailing
  suffix of the column; a genuine historical revision has no reason to respect that
  boundary and cannot fake one, because it would have to move a contiguous suffix
  uniformly to the last stored bar. That gives the band a falsifiable structure a scalar
  tolerance does not have: the shipped classifier still fires on a one-cent restatement
  of the cheapest name in the panel (4.81), which a level band wide enough to survive a
  dividend would swallow. Regenerating the fixture — what the old failure message
  literally instructed — was rejected on the same ground DEC:SI-LIVE-PLANE-BAND-IS-
  UNIFORMITY-NOT-LEVEL rejected a level band: it is a red with a due date, re-arming on
  the next ex-date, and it would additionally have erased the only surviving evidence of
  DSC:HK-DEEP-PANEL-SPLICES-ADJUSTMENT-VINTAGES. Tolerating the re-base here is scoped
  and is not a claim that the panel is clean: the seam is real, it costs exactly one
  return at one date, and the collector-side heal is owned separately because nightly is
  the sole advancer of data/ and a PR must not re-stamp its artifacts.
alternatives:
  - option: Regenerate tests/fixtures/hk_board_2026_07_31.json against today's panel
    why_not: >
      What the failure message told you to do, and it re-arms the identical red on the
      next HK ex-date — measured cause here was a routine 0.29% dividend, and the panel
      carries 157 names. It also destroys the evidence: the fixture is the only place the
      pre-re-base vintage still exists, and the collector seam would have gone back to
      being invisible.
  - option: Replace equality with a relative band on the close LEVEL
    why_not: >
      Already adjudicated against in DEC:SI-LIVE-PLANE-BAND-IS-UNIFORMITY-NOT-LEVEL. A
      band loose enough to pass 2.9e-03 swallows a one-cent restatement at this panel's
      cheap end (4.81 -> 2.08e-03), trading a scheduled false positive for a permanent
      false negative.
  - option: Reuse the SI residual-against-window-median clause unchanged
    why_not: >
      It assumes the rescale covers the WHOLE window, which holds for the SI B prefix
      because that plane is re-fetched whole. Here 311 of 341 rows sit at factor 1.0, so
      the window median is 1.0 and the 30 genuinely re-based rows read as 2.9e-03
      residuals — the clause fires on exactly the benign event it was written to ignore.
  - option: Delete the check, or downgrade it to a warning
    why_not: >
      It is the G1 gate's only staleness tripwire; without it a silently rotted fixture
      keeps nine G1 gates green, which is precisely the 2026-08-04 incident the class
      docstring records.
  - option: Fix the collector in this PR so the panel stops splicing vintages
    why_not: >
      Correct and still owed, but it is a nightly data-plane change with its own blast
      radius and it cannot green this pack on its own — the stored history would still
      need a heal pass, and nightly is the sole advancer of data/. Tracked as its own
      lane; this PR is the pack heal.
evidence:
  - "collectors/hk_closes_deep.py:39 _INCREMENTAL_PERIOD = '2mo'; :59-62 auto_adjust=True"
  - "collectors/hk_closes_deep.py:75-84 _heal_store_seams docstring names the same failure for splits"
  - "collectors/breadth.py:51 _SEAM_LO, _SEAM_HI = 0.60, 1.65 — a split detector, ~200x wider than the measured 0.29% re-base"
  - "measured drift vs tests/fixtures/hk_board_2026_07_31.json: 1 of 157 columns (2359.HK), 30 of 341 rows from 2026-06-18 = collection date minus 2mo, uniform x0.997101, per-row residual <= 4e-4 against a 1e-3 fixture quantum"
  - "tests/test_hk_board_rank.py::TestRescaleDiagnosis — 8 cases pinning the classifier on synthetic windows, incl. a one-cent restatement at 4.81 still classified revision"
  - "tests/test_hk_board_rank.py: 203 passed (was 195 passed / 1 failed)"
affects:
  - tests/test_hk_board_rank.py
  - data/hk_search/closes_deep.parquet
  - collectors/hk_closes_deep.py
discoveries:
  - DSC:HK-DEEP-PANEL-SPLICES-ADJUSTMENT-VINTAGES
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
---

## The transferable half

Two checks in one week failed the same way: an exact pin over a vendor-adjusted price
history, broken by an ordinary dividend. The SI record already drew the right general
lesson — band the invariant the conclusion depends on, not the raw quantity. This case
adds the next question to ask after that one: **what shapes can the pipeline that writes
this file actually produce?**

The SI plane is re-fetched whole, so its admissible drift is a whole-window rescale and a
median residual expresses that exactly. The HK deep panel is refreshed over a rolling
trailing window and merge-upserted, so its admissible drift is a *suffix* rescale — and
the SI clause, applied unchanged, would have fired on the benign event. Same principle,
different mechanism, different band. Reading the writer before choosing the tolerance is
what keeps a band from being a number fitted to whatever drift happened to be on disk the
day the test went red.
