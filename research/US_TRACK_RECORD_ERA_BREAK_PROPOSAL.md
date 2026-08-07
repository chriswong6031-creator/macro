# US track record — era break proposal (`_ob_mask` start-anchor)

**Status: PROPOSAL. Not a ruling, and nothing here has been executed.** No history has been
re-graded; `site/factordata/us_track_ledger.json` is untouched by the PR that carries this
document. What follows is the measured case for an era boundary and the pre-registration
that should be fixed *before* any recompute.

Sibling of `research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`
(era `abs-session-2026-08-06`, PR #4732 — **open, not merged as of 2026-08-06**).

---

## §0 Acceptance gates — this is not done unless

1. The era boundary is **ruled on** (Fable/operator) before any recompute of
   `us_track_ledger.json`. A recompute that lands without a ruling is the silent re-bake
   R5 forbids.
2. The era string is **carried in the artifact** (`meta.anchor_era`), not only in a commit
   message, so a reader can tell which anchor produced the numbers in front of them.
3. The pre-era headline is **preserved and shown**, not overwritten — the old and new
   numbers appear side by side with the reason for the change.
4. The re-measurement is run **after** #4732 merges, on the real panel, and its output is
   committed alongside the recompute in one PR.
5. `tests/test_ob_mask_start_invariance.py::test_start_invariance` has its `xfail` marker
   dropped in the same PR that stamps the era — the tripwire is spent once it has fired.
6. The direction of the move (§4) is disclosed in the PR body **before** anyone argues the
   new numbers are better.

---

## §1 The defect

`scripts/grade_us_board._ob_mask` is the incumbent episode's TARGET EXIT leg in
`emit_ledger` — the 3D StochRSI overbought flag that decides which bar an episode sells on,
and therefore its realised P&L. It reads `engine.confluence_tiers._tf_bars(c, 3)`, i.e.
`daily.resample("3B")`, whose bin edges anchor to the **series' first timestamp**.

`emit_ledger` calls it on the full rolling close cache
(`_ob_cache[tk] = _ob_mask(ser)`), and the smallcap/midcap
`data/*/_closes_cache.parquet` stores are a **rolling window** — their first date moved
`2023-06-27 -> 2023-07-03` across three sessions in early August 2026.

So each night, as the cache's start rolls off, every 3D bucket in the *whole* history
re-phases. Overbought flags from weeks ago flip, and the exit bar and P&L of episodes that
closed long ago change — with no new information about those episodes.

The docstring claimed the leg was *"Known-date mapped (causal — a 3D bucket is only
readable once complete), so it can never peek."* Causal it is; that half is true and is now
pinned by a test. Stable it is not, and the docstring never claimed stability — which is
exactly why the defect survived. Both properties are now stated.

**Scope.** `_ob_mask` is used **only** in `emit_ledger`. The horizon-graded
`data/us_board_ledger/retro_grades.parquet` and `site/factordata/us_board_track.json` do
not read it and do not move. The affected artifact is `site/factordata/us_track_ledger.json`
— the Track-record dialog, plus the hero win-rate / expectancy / CI on the Track-record page
(`scripts/build_track_record_page.py`) and the dashboard Track-record chip
(`templates/dashboard.html.j2`). Those are public numbers.

---

## §2 Measured movement

Full report: `reports/ob_mask_track_record_blast_radius.md`. Regenerate with
`scripts/measure_ob_mask_track_record_blast_radius.py`. Cohort held FIXED (one
`collect_boards()` read) in every arm, so each diff is a pure price-panel-vintage effect.
Only episodes that matured in **both** arms are compared — a row that matured in one and not
the other moved because time passed, which is legitimate.

| arm | matured in both | exit bar moved | P&L moved | median \|ΔP&L\| | max \|ΔP&L\| |
|---|---:|---:|---:|---:|---:|
| NATURAL — collection `ca9251861b4` vs `361136284f2` | 275 | 99 | **99 (36.0%)** | 1.8 pp | 14.2 pp |
| CONTROLLED — same panel, 4 leading sessions dropped | 359 | 127 | **126 (35.1%)** | 1.9 pp | 28.9 pp |

The CONTROLLED arm is the decisive one: same end date, same cohort, every retained price
byte-identical. Its movement is re-phasing alone, on **zero** new information.

Attribution for the natural arm: on the shared window only **37 of 1,540** tickers carried
any revised price, while **975** had their own history start move. Mask census on the
controlled arm: **974 of 1,492 graded tickers (65.3%)** changed their overbought mask on
shared dates, flipping **64,121** daily flags. The ~35% complement is the large-cap
`breadth` cache, whose start is fixed — it does not re-phase, which is why the share is not
100%.

A detail worth keeping: the phase depends on `(leading bars dropped) mod 3`. Dropping a full
bucket width leaves the grid untouched, so a re-phase is not monotone in how much history
rolls off — a quiet night and a disruptive one are indistinguishable without measuring.

---

## §3 Why this needs an era break, not a silent recompute

**The fix is already in flight and reaches this consumer for free.** PR #4732 migrates
`_tf_bars` to an absolute session anchor **in place**, with a backward-compatible signature.
`_ob_mask` imports `_tf_bars` directly from `engine.confluence_tiers`, so the repair lands
here whether or not anyone intends it. Verified against that branch: the controlled movement
drops **126 -> 0** of 359, and the natural arm falls to 3 of 275 — and those three include
`OHI`, which PR #4744 independently identified as a genuine vendor revision. The migration
is a real fix for this leg.

**And that is precisely the hazard.** Merging #4732 changes every published historical
number in `us_track_ledger.json`, silently:

- `scripts/grade_us_board.py` is **not** in #4732's file list, so the change is invisible in
  its diff.
- `reports/session_anchor_blast_radius.md` measures tier / veto / eligible flips on the
  confluence path. It contains **no** mention of `grade_us_board`, `_ob_mask`, the track
  ledger, or `exit_policy_study` — this consumer was never in the blast radius.
- R5's era stamp propagates via `cascade` returns, `tier_stream` columns, and `signal_gate`
  verdicts. `_ob_mask` touches **none** of those three. It calls `_tf_bars` directly, so it
  inherits the new buckets **without** inheriting the field that would tell a reader the
  buckets changed.

The ruling's own language covers this case squarely: a change that re-phases buckets under
already-graded rows *"is a graded-population change and REQUIRES a new era stamp; never
backfill the reference silently"*, and pre-era measurements are *"cited as such, queued for
re-measurement; never silently re-baked"*. Adjudication note A3 scopes
`abs-session-2026-08-06` to **confluence_tiers' buckets only**, with each downstream repair
its own charter and its own era stamp. This is that charter for the US track record.

---

## §4 The direction of the move — disclosed first, on purpose

Under the controlled arm the anchor repair moves the headline **up**:

| metric | start-anchored (today) | absolute anchor |
|---|---:|---:|
| `expectancy_pct` | 0.94 | **1.29** |
| `profit_factor` | 1.49 | **1.70** |
| `win_pct` | 61.8 | **62.7** |
| `capture` | 0.60 | **0.68** |

A correctness fix that happens to flatter the desk is the exact circumstance in which a
pre-registered gate is worth having, so the direction is stated here **before** the
recompute rather than discovered after it. The case for the era break rests on the record
being *well-defined*, not on it being better; if the numbers had moved the other way the
proposal would read identically.

**These are not the shipped headline.** The shipped artifact is stale — `as_of 2026-07-31`,
`n_matured 173`, `expectancy_pct 1.19`, `win_pct 63.6` — and the US board lane appears
frozen (also flagged in PR #4744). The table above comes from re-grading with the full board
history available at `origin/main` (275–359 matured), so it measures **movement**, not the
published level. The published level must be re-measured after #4732 lands and the board
lane is unfrozen; that is gate §0.4.

---

## §5 Proposed form

1. **Era string** `us-track-abs-session-2026-08-06` — its own string, not a reuse of
   `abs-session-2026-08-06`, per A3 (one charter, one era) and because the boundary date in
   this stream is the date this leg's buckets changed.
2. **Carried as** `meta.anchor_era` on `us_track_ledger.json`, written through the existing
   `extra_meta` channel in `engine.track_ledger.build_shell` (already used for `exit_rule`,
   `history`, `continuity`) — no schema surgery, and the field's first appearance in the
   stream is the operative boundary exactly as R5 specifies.
3. **Pre-era numbers preserved** as a committed frozen snapshot beside the report, so the
   old headline stays readable rather than being overwritten.
4. **Re-measurement committed with the recompute** — one PR carrying the new numbers and the
   data state that produced them, following the frozen-slice idiom PR #4744 established for
   `exit_policy_study`.
5. **Reader-facing disclosure** on the Track-record surface: one quiet line that the record
   was re-graded on a corrected timeframe grid, with the prior headline shown alongside.
   Wording is a design-lane question (`docs/DESIGN_DOCTRINE.md`), not settled here; it
   should avoid falsifier/refutation vocabulary per the standing operator order.

---

## §6 Explicitly NOT proposed

- **No re-grade in this PR.** The artifact is untouched; only the docstring, the
  measurement tooling, the report, and the tripwire ship.
- **No change to any grading rule** — entry, stop, horizon, fill offset, and the overbought
  threshold are all unchanged. This is about *which bucket grid* the existing rule reads.
- **No change to `retro_grades.parquet` or `us_board_track.json`** — they do not read
  `_ob_mask` (§1) and are outside this boundary.
- **No fix to `_ob_mask` here.** The repair belongs to #4732, in place, where every other
  `_tf_bars` caller gets it too. A local patch in `grade_us_board.py` would fork the grid and
  is the wrong shape.
- **The other drift source stays open.** Vendor revisions at or below the as-of move P&L on
  an unchanged cohort too (PR #4744, names `OHI` / `REZI`); the frozen-slice idiom addresses
  it for the *study*, not for the *grader*. Out of this charter's fence.

---

## §7 The tripwire

`tests/test_ob_mask_start_invariance.py` carries `test_start_invariance` as
`xfail(strict=True)`. It fails today for the right reason and flips to XPASS — i.e. **red** —
the moment #4732 lands, which is the notification that the published record has moved and
this proposal is due. Verified in both directions: red under `origin/main`, `[XPASS(strict)]`
under main + #4732's anchor.

Its sibling `test_causal_trailing_truncation_never_moves_past_flags` is green in both eras
and stays green — it pins the half of the docstring that was always true, so a future change
cannot quietly trade causality for stability.

Precedent for the pattern: `tests/test_shock_override_attainable.py`.
