# US track record — era break proposal (`_ob_mask` start-anchor)

**Status: RULED — EXECUTED (PR #4942).** Ruled by the Fable main-loop adjudication of
2026-08-07 (session `us-board-mining-detection`) and executed in the same PR: the record was
re-measured on the real panel, `site/factordata/us_track_ledger.json` now carries
`meta.anchor_era` and the frozen pre-era headline, both surfaces show the old numbers beside
the new ones, and a permanent fail-closed guard refuses any future unstamped re-bake.

Sibling of `research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`
(era `abs-session-2026-08-06`, PR #4732).

> **RULING (Fable, 2026-08-07):** The `abs-session-2026-08-06` anchor era extends to
> `site/factordata/us_track_ledger.json`. The incumbent exit leg (`_ob_mask` on
> `resample("3B")` over a rolling-start close cache) re-phases the entire published history
> whenever the cache's first date rolls — the realised P&L of long-closed episodes mutates
> nightly with no new information about those episodes. That is not a preserved track
> record; it is a moving target already in breach of measurement stability. Adopting the
> ratified absolute session anchor restores stability; refusing the break would preserve the
> instability, not the numbers. Conditions binding per §0: (2) `meta.anchor_era =
> "abs-session-2026-08-06"` carried in the artifact; (3) the pre-era headline (as_of
> 2026-07-31: expectancy_pct 1.19, win_pct 63.6, and its CI) is preserved in the artifact and
> SHOWN alongside the new numbers with the reason, on every consuming surface (full
> side-by-side on the Track-record page; a Tier-2 receipt/hover is acceptable for the
> dashboard chip); (4) the re-measurement runs on the real panel post-#4732 and lands in the
> SAME PR as this ruling's execution; (6) the direction of the move (disclosed up, expectancy
> 0.94 → 1.29 measured pre-ruling) is stated in the PR body ahead of any quality claim.
> Additionally ruled: a permanent fail-closed guard ships in the same PR — any future write
> of `us_track_ledger.json` whose headline numbers move beyond a small tolerance without a
> matching `meta.anchor_era` for the active grading construction must refuse to publish and
> print a line-start ::error annotation. Operator retains veto: nothing pre-era is deleted,
> so a reversal is a re-render away.

> **THE PRE-REGISTERED DIRECTION DID NOT SURVIVE THE RE-MEASUREMENT — §4 was wrong about the
> sign.** The ruling records §4's pre-ruling finding that the era arm moved the headline UP
> (`expectancy_pct` 0.94 → 1.29). Measured on the real panel and the real published cohort
> (gate §0.4), it moves **DOWN**, and so does the published level. Full attribution in
> `reports/us_track_ledger_era_recompute_2026-08-07.md`; the numbers are in the §4 addendum
> below. This is exactly what a pre-registration is for: the direction was fixed in writing
> before the recompute, so the flip is a finding rather than a negotiation. The case for the
> break never rested on the numbers being better — it rested on them being well-defined —
> and it reads identically now that they are worse.

> **HISTORY — how the trigger fired.** #4732 merged as `2a0c5e27184` (00:11:05), and #4747 —
> which carries this document and the tripwire — merged as `4b98aeb7123` **28 seconds later**
> (00:11:33). Each was green against a base that did not contain the other, so the tripwire
> never spent a day armed: it went red on main on arrival and pinned the `unrun-picks-boards`
> CI job for the whole fleet. The `xfail` marker was therefore dropped by the CI-heal PR
> rather than by the era-stamp PR (§0.5, closed early). Until this PR the shipped artifact
> was FROZEN at `as_of 2026-07-31` on PRE-anchor numbers (`expectancy_pct 1.19`,
> `win_pct 63.6`), which is the only reason the exposure stayed theoretical: the first
> nightly to re-grade the US board lane would have moved every published number under the new
> grid with no era stamp — the silent re-bake §3 forbids.

---

## §0 Acceptance gates — ALL SATISFIED 2026-08-07 (PR #4942)

1. **SATISFIED.** The era boundary is **ruled on** (Fable/operator) before any recompute of
   `us_track_ledger.json`. A recompute that lands without a ruling is the silent re-bake
   R5 forbids.
   → Ruling quoted verbatim in the Status block above; Fable main-loop adjudication
   2026-08-07, session `us-board-mining-detection`. The recompute is in the same PR, after
   the ruling, never before it.
2. **SATISFIED.** The era string is **carried in the artifact** (`meta.anchor_era`), not only
   in a commit message, so a reader can tell which anchor produced the numbers in front of
   them.
   → `meta.anchor_era = "abs-session-2026-08-06"`, `meta.era_from = "2026-08-07"`, written
   through `emit_ledger`'s `extra_meta` on EVERY return path including the degenerate one
   (`engine/track_era.py::us_era_meta`, `scripts/grade_us_board.py`). Pinned by
   `tests/test_track_ledger_era.py::test_shipped_artifact_carries_the_active_era_stamp` and
   `::test_emit_path_stamps_the_era_on_the_degenerate_return_too`.
3. **SATISFIED.** The pre-era headline is **preserved and shown**, not overwritten — the old
   and new numbers appear side by side with the reason for the change.
   → Preserved: `meta.pre_era` carries the full frozen pre-era summary, and the last pre-era
   artifact is committed whole (rows included) at
   `reports/us_track_ledger_pre_era_2026-07-31.json`. It is a frozen CONSTANT, not a copy of
   the outgoing file — the obvious "copy the outgoing summary" implementation self-erases
   after one night, pinned by `::test_pre_era_block_is_byte_stable_across_repeated_recomputes`.
   Shown: full side-by-side on the Track-record page (`templates/us_track_record.html.j2`
   `.tr-basis`) and in the Track-record dialog (`templates/_track_record_dlg.html.j2`
   `.trd-basis`); Tier-2 hover receipt on the dashboard chip (`.trd-basis-chip`,
   `data-tip-en`/`data-tip-zh`). EN + ZH, glance-tier wording, no grid/anchor vocabulary
   front-facing. Pinned by the surface tests in `tests/test_track_ledger_era.py`.
4. **SATISFIED.** The re-measurement is run **after** #4732 merges, on the real panel, and
   its output is committed alongside the recompute in one PR.
   → `scripts/recompute_us_track_ledger.py` (writes only this artifact — no snapshot append,
   no `retro_grades.parquet` write, per §6) over the committed panel `2023-07-03..2026-08-06`
   (777 sessions, 32 board dates, 1,555 priced tickers). Attribution measured by
   `scripts/measure_us_track_era_recompute.py` → `reports/us_track_ledger_era_recompute_2026-08-07.md`
   + `.json`, all in this PR.
5. ~~`tests/test_ob_mask_start_invariance.py::test_start_invariance` has its `xfail` marker
   dropped in the same PR that stamps the era~~ — **CLOSED EARLY 2026-08-07, gate spent.**
   The 28-second merge race (see History) fired the tripwire before any era-stamp PR could
   exist, so the marker was dropped by the CI heal instead; the test now stands as a live
   regression guard on start-invariance.
6. **SATISFIED — and it flipped.** The direction of the move (§4) is disclosed in the PR body
   **before** anyone argues the new numbers are better.
   → The PR body opens with the disclosure. It reports the OPPOSITE of §4's pre-registered
   direction: measured on the real cohort the move is **down**, on both legs. See the §4
   addendum.

**Additionally ruled — the permanent guard. SATISFIED.** `engine.track_ledger.atomic_write`
(the one path every ledger writer takes; house law forbids `open('w')` truncation) calls
`engine.track_era.check_publish`. A write of `us_track_ledger.json` whose published headline
moves beyond a small per-key tolerance without carrying the active construction's
`meta.anchor_era` is REFUSED — the previously published file is left in place and a
line-start `::error title=track-ledger-era::` annotation is printed by a bare `print(...,
flush=True)`, never a logger. Fail-closed in both directions: a guard that cannot RUN also
refuses, for this artifact only, so a broken US guard cannot wedge the CN/HK/CA nightly.
Sample counts are excluded from the moved-check (they grow nightly by ordinary accrual).
Mutation-verified: disabling the guard call reds exactly
`::test_guard_refuses_an_unstamped_write_that_moves_the_headline`,
`::test_guard_refuses_a_stale_stamp_that_moves_the_headline`, and
`::test_guard_fails_closed_when_it_cannot_run`, and nothing else.

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

### §4a ADDENDUM — the re-measurement (gate §0.4, executed 2026-08-07). The sign flipped.

Full report: `reports/us_track_ledger_era_recompute_2026-08-07.md`; regenerate with
`scripts/measure_us_track_era_recompute.py`. Three arms over ONE cohort (32 board dates) and
ONE panel (`2023-07-03..2026-08-06`, 777 sessions):

| | SHIPPED (frozen) | LEGACY grid | NEW absolute anchor |
|---|---:|---:|---:|
| what it is | the artifact as published, `as_of 2026-07-31` | the FULL current cohort on the pre-#4732 series-first grid | the same cohort, same prices, same rule, on the absolute anchor |
| `n_matured` | 173 | 374 | 374 |
| `n_board_days` | 8 | 18 | 18 |
| `win_pct` | 63.6 | 61.5 | **59.4** |
| `expectancy_pct` | 1.19 | 0.92 | **0.75** |
| `profit_factor` | 1.70 | 1.49 | **1.38** |
| `capture` | 0.71 | 0.43 | **0.38** |
| `exp_lo_pct` | 0.21 | 0.14 | **−0.10** |

SHIPPED → LEGACY is the **unfreeze** (201 episodes that matured because time passed — real
new information). LEGACY → NEW is the **era**, isolated: identical boards, admissions, and
prices; only the bucket grid differs.

**Both legs move down, and so the published level moves down: `expectancy_pct` 1.19 → 0.75,
`win_pct` 63.6 → 59.4.** §4's controlled arm measured the era going UP on a smaller cohort at
an older panel vintage; on the real published cohort the same arm goes DOWN
(0.92 → 0.75). An isolated-arm direction does not survive to the published level, and the
pre-registration is what makes that legible instead of arguable.

Era effect at row level: **122 of 374** episodes matured in both arms had their P&L move
(32.6%), median |Δ| 2.00 pp, max |Δ| 19.10 pp; 123 exit bars and 58 exit reasons moved. Every
one of those is a trade that had already closed — under the retired grid they would keep
moving as leading history rolled off, and under the absolute anchor they are fixed.

One consequence worth naming: `exp_lo_pct` is now **−0.10**, so the honest range for what a
trade returns spans a loss. The dialog's `_confident` gate already reads that field and
withholds the green accent and the "worth following" line on its own. The Track-record page's
hero stance did NOT — it keyed only on the win-rate interval, so at `ci_lo 52.6` it would
have printed "more winners than losers" over an average-trade range reaching below zero. That
page now applies the same interval rule the dialog does. Not a scope expansion: the numbers
this PR publishes are what put that branch in reach.

---

## §5 Proposed form

1. ~~**Era string** `us-track-abs-session-2026-08-06` — its own string, not a reuse of
   `abs-session-2026-08-06`, per A3 (one charter, one era) and because the boundary date in
   this stream is the date this leg's buckets changed.~~ — **SUPERSEDED BY THE RULING.** The
   ruling names the string explicitly: `meta.anchor_era = "abs-session-2026-08-06"`, i.e. the
   ratified era EXTENDS here rather than forking a per-consumer one. The proposal's A3
   reading is not wrong in general, but this leg inherits the anchor by direct import of
   `_tf_bars` — it is the same construction, not a sibling of it — so a second string would
   have named a boundary that does not exist. `meta.era_from = "2026-08-07"` carries the date
   this stream crossed it, which is the fact the separate string was reaching for.
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

> **Scope note, 2026-08-07.** §6 was written for the PROPOSAL PR (#4747), which deliberately
> shipped no re-grade. The first bullet is therefore spent: the execution PR #4942 *is* the
> re-grade, run under the ruling. Every other bullet below still binds and was honoured —
> no grading rule changed, `retro_grades.parquet` and `us_board_track.json` were not
> written (which is why the recompute has its own entrypoint instead of
> `grade_us_board --nightly`), no local patch was made to `_ob_mask`, and the vendor-revision
> drift source remains out of this charter's fence.

- ~~**No re-grade in this PR.** The artifact is untouched; only the docstring, the
  measurement tooling, the report, and the tripwire ship.~~ — spent; see the scope note.
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

**SPENT 2026-08-07 — see the Status block at the top of this file.**

`tests/test_ob_mask_start_invariance.py` carried `test_start_invariance` as
`xfail(strict=True)`. It failed for the right reason and flipped to XPASS — i.e. **red** —
the moment #4732 landed, which was the notification that the published record had moved and
this proposal was due. Verified in both directions before the merge: red under `origin/main`,
`[XPASS(strict)]` under main + #4732's anchor. It then behaved exactly as designed, only far
faster than intended — #4732 and #4747 merged 28 seconds apart, so the notification arrived
as a fleet-wide CI red rather than as a considered signal to one session.

**Lesson for the next tripwire of this shape.** An `xfail(strict=True)` armed against a
SPECIFIC in-flight PR is a bet on merge ORDER, and this repo merges concurrently — a race it
lost by 28 seconds. The tripwire correctly refused to let the change be silent, but its blast
radius was every open PR in the repo, not the one lane that owed the follow-up. A tripwire
that blocks the whole fleet also creates pressure to disarm it carelessly, which is the one
outcome it exists to prevent. Prefer a form whose failure is scoped to the artifact or lane
that owes the work — the obligation is now carried by this document's Status block instead.

The marker is gone; the test remains as a live regression guard, so a revert of the absolute
anchor on this path fails loudly rather than silently moving published P&L.

**The lesson is now implemented, 2026-08-07.** "Prefer a form whose failure is scoped to the
artifact or lane that owes the work" is exactly what the permanent guard is:
`engine.track_era.check_publish`, fired from the shared writer, refuses the ONE artifact whose
record is at stake and leaves the previously published file in place. It cannot be lost to a
merge race — it is not armed against a specific in-flight PR, it evaluates the actual write —
and its blast radius is one file, not every open PR in the repo. An `xfail(strict=True)` bets
on merge ORDER; a writer-side refusal does not bet on anything.

Its sibling `test_causal_trailing_truncation_never_moves_past_flags` is green in both eras
and stays green — it pins the half of the docstring that was always true, so a future change
cannot quietly trade causality for stability.

Precedent for the pattern: `tests/test_shock_override_attainable.py`.
