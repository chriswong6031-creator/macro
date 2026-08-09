# Breathing Platform — continuation handoff (2026-08-09, session 2 close)

**Program:** `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (merged #4975,
operator-RATIFIED 2026-08-08). Session 1 handoff:
`research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-08.md` (#5003, merged).
Run the program as a session chain over the masterplan + this doc.

Session 2 ran ~2026-08-08 23:00Z → 2026-08-09 11:30Z. Its charter was: spawn
F3+F5, then W-L1. Both builders shipped and W-L1's design is pinned and merged.

---

## §0 START HERE — the first three things to do

1. **Re-arm #5089 and check #5088/#4978 have LIVE runs.** Their packs were
   CANCELLED by ci.yml's concurrency group (`ci.yml:3426`) when rapid rebase
   pushes superseded them. **Cancelled is not a pass and the sweeper will not
   merge it.** #5088 was re-armed with an empty commit (`323f908645f`); **#5089
   was NOT** — do it first. Verify by HEAD SHA, never by run count:
   ```
   git rev-parse origin/<branch> | head -c 12
   gh api "repos/{owner}/{repo}/commits/<sha>/check-runs?per_page=100" \
     --jq '[.check_runs[]|select(.name|startswith("ci-pack"))]|map("\(.name)=\(.status)/\(.conclusion)")|join(" ")'
   ```
   Re-arm with `git commit --allow-empty -m "ci: re-arm ..."` + push. Space the
   pushes — two pushes to the same PR inside one pack run cancel the first.
2. **Do NOT merge mastermind-terminal #363.** It carries an operator `hold`
   (§4). All its checks are green; that is not permission.
3. **When any W-L0 PR merges, immediately rebase the others** (§2 collision map).

---

## §1 State at handoff (11:30Z Sun 2026-08-09)

### W-L0 (truth) — masterplan §0 gates

| Gate | PR | State |
|---|---|---|
| 1 — append semantics | **#4982** | **MERGED 2026-08-09.** Highest-severity fix in the wave: the armed probe now APPENDS tonight's bar. Re-measured on the 08-08 store — 45/180 probed names answer differently at their own close (42/72 board names); armed count moved 98 → 68 with nothing about the tape changing. |
| 2 — fade hysteresis | **#4978** | OPEN, armed `merge-on-green`, head `4afa0dcb69`. Rebased post-merge, 149 tests pass locally. **Run state unverified — check per §0-1.** |
| 3 — one price basis (F3) | **#5089** | OPEN, armed, head `f593c9c8b9`. Rebased post-merge with a real conflict resolved (§2). 230 tests pass. **NOT re-armed — packs cancelled.** |
| 4 — sentinel + engine timing rows | ~~#4981~~ | **DELIVERED via merged #5071.** #4981 closed 03:39Z as superseded — #5071 adds the served-file NYSE-session sentinel and requires `source_asof=staleness.price_through` with `source_basis=panel_majority`. Do not resurrect #4981. |
| 5 — dormant honesty (F5) | **#5088** | OPEN, armed, head `323f908645f` (empty re-arm commit). 203 tests pass. |

### W-L1 (evening SLA)
- **Design spec MERGED (#5027)**: `research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md`
  + 16 reference crops in `mockups/refs/breathing-platform/`. §0 acceptance
  gates are builder-facing and inline.
- **My binding ruling on §9-1 (publication mechanism), posted on the PR:**
  **live-plane hydration, not re-render.** Masterplan §3-2 already publishes the
  evening board to the live plane (R2 → VPS) and the render budget is law — no
  evening page-rebuild lane exists. States 1/3/4 (ahead/behind/closed stamps)
  hydrate client-side into reserved slots; **state 2** (confirmed receipt + `adj`
  marks + dropped list) is carried by the **nightly render** server-side, because
  that is the record's own build stamping its own receipt. Zero `data/` writes.
- **W-L1 BUILD IS NOT STARTED.** That is the next substantive wave.

### Terminal (mastermind-terminal, `/Users/chriswong/Documents/Cluade/charting-app`)
- **#364 financials 17y — MERGED.** All five reviewed defects fixed, incl. the
  blocker: the backfill crossed an 8-period guard that armed a dormant
  YTD-differencing heuristic on US names (executed repro: MSFT 82.9B rendering
  as 1.6B). Fix is market-aware gating via `markets.marketOf`; math extracted to
  `terminal/lib/finStatementMath.ts` so it is actually testable.
- **#363 live prices + 1s bars — OPEN, `hold`. See §4.**
- **#372 e2e de-flake — MERGED.** Root-caused a real `ChartPanel` bug (the pane
  can drop an already-registered crosshair, so the badge returns to its exact
  pre-transition baseline — no timeout increase could have fixed it).

---

## §2 Collision map — `engine/prophet_live/live_states.py` (READ BEFORE REBASING)

Hunk ranges in ORIGINAL line numbers, measured 2026-08-09:

- **#4978**: `@@ -507`, `@@ -514` (fade branch)
- **#5088 (F5)**: `@@ -427`, `@@ -495`, `@@ -514` — overlaps **#4978 at -514** and
  **#5089 at the early guard + import block**
- **#5089 (F3)**: `@@ -106`, `@@ -116`, `@@ -192`, `@@ -423`, `@@ -663`, `@@ -683`,
  `@@ -716` — **no overlap with #4978**

**Already-resolved conflict, for reference:** rebasing #5089 after #4982 merged
hit `engine/prophet_live/armed_pack.py`'s re-export from the stdlib-only
`interval` sibling. #4982 added `membership_anchor`; F3 adds `ADJUSTED`,
`UNADJUSTED`, `DEFAULT_PACK_ADJUSTMENT`. **Resolved as the UNION** — either side
alone drops the other's symbol and fails at import. Verify every name resolves
in `interval.py` before continuing a rebase; do not trust the merge.

`interval.py` must stay **stdlib-only** (the `*/5` lane installs no pandas). F3
adds `math` and nothing else. Guard this in review.

---

## §3 Builder findings worth carrying (both PRs reviewed and approved)

**F5 (#5088) — added a public `unknown` state, and the reasoning is the point.**
It tried `dark` first, then read what the surface *does* with dark counts:
`dashboard.html.j2` spends them twice as a fault claim — the rule-6 mode flip at
`sum/evaluated_n >= 0.5` (:17815) and the footer's "N could not be read"
(:17958). A name trading below its swept region has a healthy quote, so `dark`
would state a confidently wrong cause on every red day. `unknown` gets its own
`meta.unknown_counts`. **Verified independently: it renders nowhere** —
`_plvPick` (:17607) requires `entered==='cross'` + forming/faded; card chips
require `entered==='board'`. **Do not fold `unknown_counts` into `dark_counts`**
— that re-introduces the wrong cause.
F5 also ruled the down-band exception does NOT hold, structurally: a published
`fade_hi_px` + an `irregular` state mean the buyable set is an interval, not an
up-ray. Its 198-call sweep found zero witnesses and is reported as *plausible
and unrefuted, therefore not knowledge* — the right posture, not a null result.

**F3 (#5089) — the price-basis defect was wider than dividend days.**
Back-adjustment rescales every close BEFORE an ex-date, so `maturing_rows` was
silently restating already-published ledger numbers. Fix freezes the anchor at
`cross_basis_close` so the factor is 1.0 by construction on the event night — no
existing number moves the day it is written. Tolerance 0.25% is sited between
measured anchors (floor: ≤0.05% four-source agreement; ceiling: the 0.649% CFG
receipt). Mismatch darks **per-name**, not the whole pack, because
`dark_artifact` publishes no states at all and would erase healthy names' banked
debounce counters.
**F3's report claimed #4978/#4982 "had already merged" — they had not.** Its
no-collision conclusion happened to survive (its hunk is at -423, #4978's at
-507/-514), but the premise was false. Check hunk ranges, not builder beliefs.

**Open follow-ups, filed not blocking:** F5 — `out["fails"]` resets across a
dark pass; `unknown`↔`near` oscillation for a name hovering at its as-of close
(needs a debounce decision when `unknown` gets a surface). F3 — the mirror case
(pack built pre-ex-date, tape opens lower) needs the M5 forward corporate-actions
calendar; Stooq secondary fill into `curated_extras` documents no basis; legacy
ledger rows stay `unaligned_no_anchor` (correct refusal, don't invent an anchor).

---

## §4 mastermind-terminal #363 — HELD BY OPERATOR, do not merge

`hold` applied 2026-08-09T01:44:32Z with a written rationale. Two gates, neither
satisfiable by CI:
1. **Live-session freshness measurement** — impossible over the weekend; needs RTH.
2. **Real-time redistribution / serving policy** — operator decision, open.

The label exists specifically to stop the merge controller reading a later green
check as product approval. **Remove `hold` only after an RTH measurement passes
AND the serving policy is decided.**

Status for whoever lifts it: all three checks green on head `fc20f735`, rebased
onto the de-flaked master. State is `BEHIND` — deliberately not rebased, since
that only re-arms CI without moving either gate. The feature ships **dark**
regardless: `HUB_REALTIME_QUOTES` defaults off and now gates the second-resolution
band too, refusing as an entitlement (200 + empty bars + note), never a 5xx, with
the client degrading to its honest "no intraday data" path.

This dovetails with the M1 real-time-label flip (masterplan §7½), also waiting on
Monday premarket.

---

## §5 CI mechanics learned the hard way this session (all cost real time)

1. **A push can schedule ZERO runs.** Happened three times on one branch, with
   `git push` reporting success and githubstatus all-green. Runs existed but were
   all stamped with the PREVIOUS head SHA, so the PR page and the sweeper read
   obsolete checks as current. **Always compare by `headSha`.** Remedy: empty
   commit, or `gh workflow run ci.yml --ref <branch>` — but note a
   `workflow_dispatch` run does **not** attach to the PR's `statusCheckRollup`,
   so it proves content to you while the sweeper still sees nothing.
2. **The concurrency group cancels on rapid pushes** (`ci.yml:3426`). Two rebase
   pushes in quick succession leave the head with cancelled packs = unproven.
3. **The sweeper blocks when main changes the CHECK DEFINITIONS.** #5106 touched
   `daily.yml` + checkpoint tests, so every existing green described a check set
   that no longer existed. The block is correct, not a failure — rebase and
   re-green. (It cites PR #4583, where a 15-hour-old honest green turned main red.)
4. **Fleet-wide identical reds across independent branches = stale base.** Three
   packs red on both #4978 and #4982 with the same failures; both reproduced
   PASSING at fresh main. Rebase, don't fix.
5. **My heal PR #5023 was superseded mid-flight and closed.** Siblings #5032 and
   #5065 landed the same four fixes, several better than mine (a reusable
   `_days_ago()` helper + `_prior_quarter()` for QoQ correctness). **Diff against
   fresh main before pushing a heal** — a superseded regeneration silently
   reverts the better fix. One fix of mine was genuinely unique and is NOT on
   main: `engine/signal_lab.py`'s `_resolve_vector_live_stats` fallback warns
   "rendering the frozen quote" **without writing the frozen quote into the row**,
   so after a successful resolve in the same process the data-less path renders
   the PREVIOUS live figures under a frozen-quote label. #5032 fixed the test
   (pristine snapshot), not the product. Worth a small standalone PR.
6. **Flake vs "I broke it" is a RATE question.** A single local pass proved
   nothing; the honest probe is the full file (CI runs it with parallel workers)
   plus a `--repeat-each` on a detached `origin/master` worktree. The suspect
   spec failed **2 of 3 on clean master** vs 1 of 1 on the branch — more flaky
   without the change. Never re-run CI until green without that baseline.

---

## §6 Next wave — W-L1 build (the actual next task)

Masterplan §4 W-L1 + gates §0 W-L1. Spec is pinned in
`research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md`; the builder implements it and
does **not** re-choose palette, copy, hue, or which state gets which treatment.

- Close-pass provisional board (~16:15–17:30 ET) on the idle mac pool; publish
  via R2 → VPS per the hydration ruling in §1.
- Gate: fresh US picks live by **18:30 ET on five consecutive green sessions**,
  measured by the sentinel's own stamps; per-name provisional→nightly
  confirmation delta published; **zero `data/` writes** from the close-pass lane.
- Rides along: per-source `elapsed_sec` from `run_status.json` into the collect
  timings bands (attribution BEFORE decomposition).
- Route per §Model routing: `builder` (opus) implements the pinned spec;
  design choices stay with `designer`/main loop.

**Do not start W-L1 until the W-L0 gates are merged** — they are the truth layer
W-L1's board is built on, and gate 1's 98→68 armed-count shift is exactly the
kind of correction that would invalidate a board built on the old semantics.

---

## §7 Loose ends (unchanged or new)

- **November DST cron race** (`daily.yml:10-11`): 22:30Z races the FINRA file at
  EDT→EST. A chip session was started for it 2026-08-09; verify it landed.
- CLAUDE.md still says "4 Linux render boxes" — measured: ONE (`pc-render-1`).
- `docs/VPS_LIVE_ORCHESTRATION.md` china.html board-stamp claim — re-check now
  that #5071 landed.
- Terminal follow-ups chip (task filed): two surfaces still read income raw
  (`StockAnalysis.tsx:188`, `OverviewPage.tsx:713`) bypassing the new
  market-aware normalization; **HK may not actually be cumulative** (Tencent
  publishes discrete quarterlies) — that assumption also feeds W-L3 China;
  `fetch_financials` sorts on a null column, which may make vendor pagination
  non-deterministic.
- Operator decisions still open (masterplan §6): D2 Polygon real-time upgrade,
  D3 VPS tier / ThetaData re-home, D5 alert channels, D6 era discipline; plus
  the chartered-not-ratified survivorship-true universe + minute-resolution
  track-record self-audit.
