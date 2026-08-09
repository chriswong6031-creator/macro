# Breathing Platform — continuation handoff (2026-08-09, session 3 close)

**Program:** `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (merged #4975,
operator-RATIFIED 2026-08-08). Prior handoffs: session 1 #5003 (merged), session 2
`research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-09.md` (#5127).
Run the program as a session chain over the masterplan + this doc.

Session 3 ran 2026-08-09 ~11:34Z → close. Charter: session 2's §0 three items, then
land the remaining W-L0 gates, then start W-L1.

---

## §0 START HERE — the first three things to do

1. **Confirm GitHub-hosted runners are still serving this repo** (§5). For roughly
   09:25Z→12:05Z today NO `ubuntu-latest` job was picked up — `ci` + `fences`
   queued fleet-wide — while self-hosted lanes ran normally, so nothing could go
   green and nothing could merge. **It recovered on its own at ~12:05–12:10Z.** If
   it recurs, confirm at JOB level and wait; §5 has the evidence and why the
   obvious diagnosis is wrong.
   ```
   gh api "repos/{owner}/{repo}/actions/runs?per_page=100" \
     --jq '[.workflow_runs[]|.status]|group_by(.)|map("\(.[0])=\(length)")|join("  ")'
   # then confirm at JOB level — run-level timestamps lie (§5):
   gh api "repos/{owner}/{repo}/actions/runs/<id>/jobs" \
     --jq '.jobs[]|"\(.name) \(.status) started=\(.started_at) labels=\(.labels|join(","))"'
   ```
   **Do NOT re-push, re-arm, or re-dispatch to "fix" it** — it cannot help, and a
   second push cancels the first run's packs. This is an operator/org-settings
   question; §5 has the evidence and the options.
2. **Gate 2 (#4978) is the last W-L0 gate open** — armed and correct, rebase it onto
   the post-gate-3 main and let it merge. Gate 3 merged at 12:08Z, so **W-L1a (§6)
   is UNBLOCKED and is the next build.** If a pack comes back genuinely red on
   #4978, read §2 before touching `live_states.py` — the fade branch now carries a
   union that is easy to undo by accident.
3. **Do NOT merge mastermind-terminal #363.** Still `hold`, still unmerged,
   verified this session. Two gates, neither satisfiable by CI: an RTH
   live-session freshness measurement (impossible over the weekend) and the
   real-time redistribution/serving policy (open operator decision). All checks
   green is not permission.

---

## §1 State at handoff

### W-L0 (truth) — masterplan §0 gates

| Gate | PR | State |
|---|---|---|
| 1 — append semantics | #4982 | **MERGED** 2026-08-09 (session 2). |
| 2 — fade hysteresis | **#4978** | OPEN, armed, head **`0a49516f080`**. **Rebased onto gate 5 with a real semantic conflict resolved as a UNION (§2).** 329 tests pass. Merges cleanly against current main (post gate-3, post #5135) — no rebase needed. Carries `merge-blocked` from a sweep that read the checks MY force-push cancelled; `merge-on-green` is still armed, so it merges once the new head's packs conclude. **See §2.1 — the first push of this head was incomplete.** |
| 3 — one price basis (F3) | **#5089** | **MERGED** 2026-08-09T12:08Z as `f5a3580aa1`. Union invariants verified intact this session (all ten `armed_pack.py` re-exports resolve, `interval.py` stdlib-only), 343 tests pass at its head. Merged BY THE OPERATOR with its packs still queued — an admin merge over the hosted-runner outage (§5), not a sweeper merge on concluded green. |
| 4 — sentinel + engine timing rows | ~~#4981~~ | **DELIVERED via merged #5071.** Do not resurrect #4981. |
| 5 — dormant honesty (F5) | **#5088** | **MERGED** 2026-08-09 as `d71551c124e`, mid-session. Its merge is what forced §2. |

### W-L1
- Design spec merged (#5027): `research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md` +
  16 reference crops in `mockups/refs/breathing-platform/`.
- **W-L1b (surface) — BUILD COMMISSIONED this session**, opus `builder`, against
  the pinned spec with all 12 acceptance gates inline. Instructed **not** to
  self-merge: flagship UI returns its PR + visual artifact to the commissioning
  session (spawn-handoff law §4).
- **W-L1c (collect attribution rider) — SHIPPED AND MERGED as #5135.** Per-source
  `elapsed_sec` from `run_status.json` into the timings ledger, plus a
  `--sources`/`--job` reader so the data has a consumer. Its measurements are in
  §4.1 and they reshape W-L4's decomposition plan.
- **W-L1a (close-pass engine lane) — COMMISSIONED this session** (opus `builder`,
  branch `claude/wl1a-close-pass-provisional-board`), unblocked the moment gate 3
  merged. It was deliberately held until then: the lane must name its price basis
  at every seam and gate 3 defines those seams. §6 + §6.1 carry the corrected
  scope, which is much smaller than the masterplan implies — read before reviewing.

### Adjacent, shipped this session
- **Massive §0 global licensing gate CLOSED — PR #5139** (armed). An Enterprise
  Market Data License + Redistribution Addendum (effective 2026-08-09) plus operator
  confirmation of full licensing and distribution rights unblocks TP-2…TP-6. Record:
  `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md`. **The executed instrument is
  deliberately NOT committed** — this repo is PUBLIC and the agreement is mutually
  confidential; do not "complete the filing" by pasting the contract in. The debrand
  law and the epistemic gauntlet are explicitly unchanged by it.

---

## §2 The gate-2 / gate-5 union — READ BEFORE TOUCHING `live_states.py`

Gate 5 merged while gate 2 was in flight, and the collision at the fade branch was
**semantic, not textual**. Gate 5 emits `fade_unconfirmed` — the fourth internal
marker — from exactly the branch gate 2 deletes: the one-sided
`lo*(1-buf) <= px < lo` special case, which under two-sided hysteresis is subsumed
by the general branch and would shadow it from earlier in the `elif` chain.

**Either side alone is a regression:**
- Gate 2's side alone leaves `FADE_UNCONFIRMED` defined and never assigned — dead
  code, and `tests/test_prophet_live_reconcile.py` (untouched by #4978) asserts the
  marker still spools, so it is also red.
- Gate 5's side alone keeps the lower-edge-only asymmetry gate 2 exists to kill.

**Resolution:** the marker moved INTO gate 2's generalised suppressed branch, so it
now fires on **both** edges — gate 5's own charter ("a suppression nobody records is
a suppression nobody can measure") applied to the half of the buffer no spool row
could previously see. `internal_via` still rides the spool row, never the display
field `via`.

Three assertions written before the marker existed were updated, **not weakened**:
the marginal-overrun case pins one `fade_unconfirmed` row with `via == "overrun"`;
the straddle case pins exactly ONE row across six oscillating passes (no-flap AND
dedup in one probe); and gate 5's own dedup tail — which used a second CONSECUTIVE
in-buffer pass, a real fade under gate 2's debounce — is re-cut as
hold-then-suppress, with the two-consecutive-failing-passes fade pinned separately.

**Filed, not fixed (deliberate):** the spool dedup keys on the marker NAME alone
(`transitions()` skips when `marker not in seen_before`). That was exactly right
while `fade_unconfirmed` could only mean *drop*. Widened to both edges the key is
slightly too coarse — a name suppressed on the drop edge early is deduped for the
day, so a later **overrun** suppression is never recorded. Counts stay right; the
side histogram under-reports overruns. Re-keying to `(marker, via)` changes the row
population gate 5's measurement is calibrated against, so it belongs in its own PR
with before/after counts. Settle it once the lane has run a few sessions: if
`fade_unconfirmed` rows split meaningfully by `via`, re-key.

### §2.1 The first push of that head was HALF the fix — check this shape

The resolution had two halves: the `live_states.py` union, and three test assertions
updated to match. The first was `git add`ed before `rebase --continue`; the tests were
edited after, and the commit was finished with `git commit --amend`. **`--amend`
rewrites from the INDEX and stages nothing**, so the pushed commit carried the product
change with the OLD assertions — exactly the combination that fails, and precisely the
three tests already diagnosed. Every check run afterwards read the WORKING TREE (329
passing), which was correct; nothing that reads the working tree can see this.

It surfaced only because gate 3 merged into the same file and the branch was
test-merged against fresh main rather than trusting a clean `git merge-tree` exit.
**A clean `merge-tree` says two trees combine; it says nothing about whether what you
pushed is what you tested.** Verify the COMMIT, not the tree:
`git show origin/<branch>:<file> | grep -c '<string unique to each half>'`, for every
half.

`interval.py` must stay **stdlib-only** (the `*/5` lane installs no pandas) —
verified this session: `math` + `typing` only. `armed_pack.py`'s re-export must
carry the UNION of both eras' symbols (`membership_anchor` from gate 1 plus
`ADJUSTED` / `UNADJUSTED` / `DEFAULT_PACK_ADJUSTMENT` from gate 3) — verified by
import probe, all ten names resolve.

---

## §3 Two session-2 items that are now CLOSED — do not redo them

1. **`engine/signal_lab.py` `_resolve_vector_live_stats` (session 2 §5-5) is
   ALREADY FIXED on main.** #5079 (`fdd43487455`, "build_scorecard must not resolve
   into the module registry") added `registry = copy.deepcopy(REGISTRY)` at the
   sole production call site, so each `build_scorecard()` starts from the pristine
   frozen row and the "renders the PREVIOUS live figures under a frozen-quote
   label" path is unreachable. `build_scorecard` is the only non-test caller. **No
   standalone PR needed.** A sibling landed it while session 2 was writing the
   handoff — the recurring lesson: diff against fresh main before building a heal.
2. **The "CLAUDE.md still says 4 Linux render boxes" item is not reproducible.**
   The claim is absent from `CLAUDE.md`, `AGENTS.md`, and the masterplan. Nothing
   to correct. (Separately, #5124 states `render-linux` is FOUR runners, which
   contradicts session 2's "measured: ONE (`pc-render-1`)" — if that number matters
   to a decision, measure it again rather than trusting either doc.)

---

## §4 The masterplan's W-L1 premise is FALSE — and it makes W-L1a much smaller

**`.github/workflows/closing-bell.yml` ("Build A") is a live, scheduled evening
page-rebuild lane.** DST cron pair `5 20 * * 1-5` + `5 21 * * 1-5` with a
session-day guard that self-skips the wrong-season line. **Measured wall-time 109
min** (spine 81m long pole, parallel band 18m) → the site lands **~17:55 ET**. It
superseded the retired `earlyclose` lane.

So the session-2 ruling's stated reason — "live-plane hydration, not re-render,
because no evening page-rebuild lane exists" — rests on a false premise.

**The ruling still STANDS, for a better reason.** Two measured facts:

1. closing-bell **deliberately EXCLUDES** `build_prophet`, `grade_us_board`,
   `us_pages`/LLM brains, `cl_china`, `cl_hk`, `cl_special` (EDGAR ~28m), library
   rebuilds and `scripts.collect`. Verified against the STEPS, not just the header
   comment — those names appear only in the comment block and never as a step,
   while `daily.yml` references `build_prophet` 13×. **The one thing that lane does
   not refresh is exactly the US Prophet picks W-L1 is about.**
2. 16:05 ET + 109 min = 17:55 ET against an 18:30 ET SLA — **35 minutes of
   headroom**, behind an 81-minute spine. Putting the prophet board on that render
   critical path spends the entire margin and makes the SLA fragile. Hydration lets
   the provisional board land ~30–60 min after the close, independent of the spine.

**closing-bell is a precedent to reuse, not a thing to rebuild.** It already proves
the contract W-L1 needs: every `data/` write discarded via `git checkout -- .` +
narrow staging (it commits `site/` plus only `data/regime/latest.json` +
`data/market_state/latest.json`), `RENDER_NO_DRIP=1` job-wide, `COLLECT_LANE`
deliberately UNSET so every engine ledger writer self-gates off, an optionshub
mutex, a holiday/weekend gate that does NOT use `expected_last_session()` (it fires
before the 17:00 ET settle buffer), and output stamped
`{as_of, provisional: true, lane: "closingbell"}` — a provisional-stamp convention
that exists before W-L1 invents one.

Also worth knowing: the live evaluator's own window ends at **16:15 ET**
(`_DEFAULTS["window_et"]`), which is exactly where the masterplan's close-pass lane
picks up. The handoff between the two lanes is a seam, not a gap.

---

## §5 The hosted-runner backlog (the session's binding constraint)

At ~11:28Z #5124 returned every `ci` pack from `["self-hosted","render-linux"]` to
`ubuntu-latest`. By 11:58Z the repo showed **56 runs queued, 1 in progress** — `ci`
= 30 queued, `fences` = 29 queued (~150 hosted jobs). Both W-L0 gates sat queued
behind it.

**GitHub-hosted (`ubuntu-latest`) jobs are not being picked up, and it PREDATES
#5124.** Every job observed completing ran self-hosted (`merge-on-green` on
`self-hosted,render-linux` 12:02; `attested-history` and `vector-sentinel/flash-crash`
on `self-hosted,macstudio-light` 12:02/11:53). No `ubuntu-latest` job was observed
starting at all.

**Do not date the break to #5124.** `fences.yml` has always been `ubuntu-latest` on
all four jobs, and its **oldest still-queued run was created 10:35Z** — roughly 90
minutes BEFORE #5124 merged at 11:28Z. The oldest queued `ci` run is 09:25Z. So the
hosted pool was already not serving this repo; what #5124 did was move every pack
off the *working* self-hosted pool onto the stuck one, converting a partial outage
into a fleet-wide stoppage.

**Beware the two weak signals that nearly produced the wrong diagnosis**, both
recorded because they will recur:
- A run's `run_started_at` is set when the RUN is created, not when its JOBS get a
  runner. "fences started at 11:41" proves nothing about pickup. Only job-level
  `started_at` + `labels` (`/actions/runs/<id>/jobs`) answers it.
- "Things are completing" is not "hosted is working" — check the completing job's
  `labels`. Here, everything green was self-hosted.

githubstatus was all-operational throughout, so this is ours, not an incident. Note
this repo is PUBLIC, so hosted minutes are free and billing is an unlikely cause;
the likelier candidates are an org-level Actions runner/permissions setting after
the MastermindX enterprise transfer, or a hosted-concurrency ceiling that is not
what #5124's message assumed.

**It recovered on its own at ~12:05–12:10Z.** Within five minutes the repo went from
`queued=58, in_progress=0` to `queued=37, in_progress=3, completed=56` — pickup
resumed and the backlog began draining, with no revert and no intervention. So the
outage window was roughly **09:25Z → 12:05Z**, and the correct action during it
(wait, change nothing) was also the one that worked.

**Keep the lesson, not the alarm.** If it recurs: confirm at JOB level, check the
completing jobs' `labels`, and wait. Only escalate to an operator if it persists
well beyond a couple of hours — the standing lever, putting packs back on the
self-hosted pool that demonstrably kept working, reverses a deliberate and
well-argued decision (#5124) and is an operator call, not a session's unilateral
one. Do NOT re-push, re-arm, or re-dispatch armed PRs while it is dark: it cannot
help, and a second push cancels the first run's packs.

**One artifact worth someone's attention:** the check list on #5089's head carried a
literal `ci-pack-${{ matrix.pack }}` (completed/skipped) alongside the four real
`ci-pack-N` checks — an unexpanded matrix expression surviving into a check NAME.
It was skipped and harmless here, but a check whose name is a template is exactly
the kind of thing that makes `merge_on_green.main_proof`'s name-matching miss.

---

## §6 Next wave — W-L1a, scoped by §4

Masterplan §3-2 + §4 W-L1, gate §0 W-L1. **Do not start until #5089 (gate 3)
merges** — the lane must name its price basis at every seam and gate 3 defines
them.

Scope, corrected by §4:

- **Not** "build an evening lane" — one exists. Add the **provisional Prophet /
  US-standouts board** to (or beside) `closing-bell.yml`, **off its render critical
  path**, so it does not sit behind the 81-minute spine.
- Recompute ADMISSION + the price-derived score legs from the day's closes only
  (no FINRA / OI / fundamental inputs — that is what makes it zero score
  authority). Publish to the **live plane** (R2 → VPS) per the hydration ruling,
  which the W-L1b surface is already built against.
- Emit the sentinel stamps that let the 18:30 ET SLA be measured from the
  sentinel's own record (gate: five consecutive green sessions).
- Publish the per-name provisional→nightly confirmation delta (integrity metric,
  free).
- **Zero `data/` writes** — reuse closing-bell's proven discard contract rather
  than inventing one.

Route per §Model routing: `builder` (opus) implements; design choices stay with
`designer`/the main loop. Acceptance gates go INLINE in the spawn prompt.

### §4.1 What W-L1c actually measured — it rewrites W-L4's decomposition plan

Now that per-source attribution exists (#5135), the nightly's shape is measured
rather than assumed. Collectors band **130.1m** = 126 sources **107.0m** + residue
**23.1m (18%)**. Top: `massive_stock_day` 21.8m, `sec_capital_structure` 10.7m,
`wiki_pageviews` 8.7m, `finnhub_altdata` 8.4m, `edgar_8k` 7.4m.

Three findings that cut against the masterplan:

1. **`finra_short_volume` costs 1.3 SECONDS.** §1 anchors the entire 22:30Z nightly
   fire time on waiting for that file. The constraint is pure **availability, not
   cost** — moving that one adapter to its own post-6pm-ET cadence detaches the whole
   nightly fire time and gives up 1.3s. Same shape: `cboe_gex` 10.9s, `cboe_putcall`
   4.7s. **This is the cheapest large win in the program and it is not in any wave.**
2. **The tail is not the problem.** Top 5 = 50% of adapter time, top 16 = 80%; **103
   of 124 timed sources finish under 60s and are 12.4% of the total** (79 under 10s,
   31 under 1s). Decomposing ~120 adapters onto per-source cadences moves ~13 minutes.
   The real cut is `massive_stock_day` (21.8m, 20% of all adapter time, T+1 by nature,
   zero score authority) plus four others. W-L4's "collect decomposition" should be
   re-scoped from "the monolith" to those five.
3. **23.1m of the band is not adapter time at all**, and that is a **floor**, not an
   estimate — the concurrent host-group phase overlaps, so attributed time over-counts
   against the band. Moving every adapter off still leaves ≥23m.

**Filed, not fixed:** `asia-close.yml` runs `scripts.collect --group asia` — 55
sources, 46.1m of adapter wall-clock — with **no `nightly_timings` instrumentation at
all**. Those minutes are in no timings band on any job. W-L4's gate ("per-source
collect attribution rows exist in the timings ledger") is only satisfiable for
`daily.yml` until asia-close gets a start-mark + finish step. Small, self-contained.

### §6.1 Three masterplan assumptions a census refuted — read before scoping W-L1a

1. **`closing-bell.yml` is absent from the masterplan entirely** (zero hits for
   "closing-bell" or "Build A"), yet it fires 16:05 ET on the exact
   `[self-hosted, macstudio]` pool §1 calls "idle through the entire US session",
   runs 109 measured minutes, and its window (16:05–17:55 ET) almost fully covers
   the proposed 16:15–17:30 ET close-pass. It is the closest existing precedent for
   "provisional EOD build" — closer in spirit than `prophet_live` — and it
   deliberately carves out exactly what W-L1 wants added.
2. **The "idle mac pool" premise is weaker than stated.** `render.yml:224`'s own
   comment says `macstudio` "currently represents logical agents on only **two
   physical Macs**", not five hosts; and `smart-money-13f-census.yml`
   (`7,37 12-23 * * 1-5`) plus `smart-money-filings.yml` (`17 13-23/2 * * 1-5`)
   also cron-fire on `macstudio` through the session. **Measure real idle capacity
   in the 16:15–17:30 ET window before assuming free compute.**
3. **The freshness sentinel CANNOT yet measure the W-L1 SLA — this is an unstated
   build item.** §0 W-L1 says the SLA is "measured by the sentinel's own stamps",
   but `scripts/freshness_sentinel.py` overwrites both `live/staleness.json` and
   `state.json` every 30-min pass with **no session-keyed history**, so nothing can
   answer "on each of the last 5 sessions, when did surface X first read fresh."
   There is also no `SURFACES` entry for a close-pass artifact — post-#5071
   `prophet_us` watches the *nightly* store on a 1-session budget, which is a
   staleness budget, not a clock-time SLA. **W-L1a must build the first-fresh-at
   per-session log, or the gate is unmeasurable.** (Adjacent to, but not the same
   as, W-L0 §0-4.)

Also useful for scoping: ADMISSION is `engine/signal_gate.gate()`
(`scripts/build_stock_library.py:3040`), all five score legs in
`engine/us_board_rank.py` are price/close-derived (`SCORE_WEIGHTS:105-111`), and
every non-price input (FINRA, GEX/OI, fundamentals, SUE, insider, 13F) is already
in `ZERO_SCORE_AUTHORITY:174-192` — so the masterplan's "100% price-derived"
close-pass claim checks out. The live-plane precedent chain is
`engine/prophet_live/r2io.py` → `scripts/prophet_live_evaluator.py` (`SERVED_PATH`,
atomic rename) → `app/deploy/macro-live-prophet.{service,timer}`, and
`tests/test_prophet_live_vps_lane.py` is the richest guard set a new lane must
replicate (it pins "writes nothing under `data/`", "the only write is the served
path", and "public live exceptions are exactly the reviewed files" against the
Caddyfile allow-list).

---

## §7 Loose ends

- **W-L1b surface PR needs a visual review by the commissioning session** — it was
  told not to self-merge. Do not let it sit; flagship UI that merges unreviewed is
  the exact failure the spawn-handoff law was written for.
- **November DST cron race** (`daily.yml:10-11`): correctly DOCUMENTED, not fixed —
  the comment names the remedy (`"30 23 * * *"`) and it must be applied AT the
  November flip, not before. Nothing to do now; put it on the calendar.
- `docs/VPS_LIVE_ORCHESTRATION.md` china.html board-stamp claim — still unverified
  against merged #5071.
- Terminal follow-ups chip: `StockAnalysis.tsx:188` / `OverviewPage.tsx:713` still
  read income raw, bypassing the market-aware normalization; **HK may not actually
  be cumulative** (Tencent publishes discrete quarterlies) — that assumption also
  feeds W-L3 China; `fetch_financials` sorts on a null column.
- Operator decisions still open (masterplan §6): D2 Polygon real-time upgrade, D3
  VPS tier / ThetaData re-home, D5 alert channels, D6 era discipline; plus the
  chartered-not-ratified survivorship-true universe + minute-resolution
  track-record self-audit.
- **M1 real-time-label flip** (masterplan §7½) still waiting on Monday premarket,
  same as Terminal #363's first gate.
