# Breathing Platform — continuation handoff (2026-08-09, session 3 close)

**Program:** `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (merged #4975,
operator-RATIFIED 2026-08-08). Prior handoffs: session 1 #5003 (merged), session 2
`research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-09.md` (#5127).
Run the program as a session chain over the masterplan + this doc.

Session 3 ran 2026-08-09 ~11:34Z → close. Charter: session 2's §0 three items, then
land the remaining W-L0 gates, then start W-L1.

---

## §0 START HERE — the first three things to do

1. **Check whether the hosted-runner backlog has drained** before anything else
   (§5). At session-3 close, `ci` + `fences` were queued fleet-wide with ~150
   hosted jobs outstanding and near-zero pickup. Nothing merges until it drains.
   ```
   gh api "repos/{owner}/{repo}/actions/runs?per_page=100" \
     --jq '[.workflow_runs[]|.status]|group_by(.)|map("\(.[0])=\(length)")|join("  ")'
   ```
   **Do NOT re-push, re-arm, or re-dispatch to "fix" it** — every extra run makes
   the queue longer, and a second push cancels the first run's packs.
2. **W-L0 gates 2 (#4978) and 3 (#5089) are both armed and correct — just
   unproven.** Verify they merged; if they did, W-L1a (§6) is unblocked and is the
   next build. If a pack came back genuinely red, read §2 before touching
   `live_states.py` — the fade branch now carries a union that is easy to undo.
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
| 2 — fade hysteresis | **#4978** | OPEN, armed, head `7ce6dd33efa`. **Rebased onto gate 5 this session with a real semantic conflict resolved as a UNION (§2).** 329 tests pass locally. Packs queued behind the hosted backlog. |
| 3 — one price basis (F3) | **#5089** | OPEN, armed, head `feae810136c`. Already carried gate 5 as a parent; §2 union invariants verified intact, 343 tests pass at its own head. **Deliberately not re-pushed** — it had live queued runs and a push would have cancelled them. |
| 4 — sentinel + engine timing rows | ~~#4981~~ | **DELIVERED via merged #5071.** Do not resurrect #4981. |
| 5 — dormant honesty (F5) | **#5088** | **MERGED** 2026-08-09 as `d71551c124e`, mid-session. Its merge is what forced §2. |

### W-L1
- Design spec merged (#5027): `research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md` +
  16 reference crops in `mockups/refs/breathing-platform/`.
- **W-L1b (surface) — BUILD COMMISSIONED this session**, opus `builder`, against
  the pinned spec with all 12 acceptance gates inline. Instructed **not** to
  self-merge: flagship UI returns its PR + visual artifact to the commissioning
  session (spawn-handoff law §4).
- **W-L1c (collect attribution rider) — BUILD COMMISSIONED this session**, opus
  `builder`, armed `merge-on-green` on completion. Independent of the gates.
- **W-L1a (close-pass engine lane) — deliberately NOT started.** It is the one
  piece that genuinely depends on gate 3: the lane must name its price basis at
  every seam, and gate 3 defines those seams. Building it against pre-gate-3 code
  buys rework. Commission it first thing once #5089 merges. §6 has the scope,
  which is much smaller than the masterplan implies — read it before writing code.

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

**Diagnosed carefully, because the obvious read is wrong.** Everything that was
completing ran self-hosted (`merge-on-green` on `self-hosted,render-linux` succeeded
11:51; `vector-sentinel/flash-crash` on `self-hosted,macstudio-light` succeeded
11:53), which looks exactly like "the hosted pool is dead — revert #5124". It is
not. **`fences.yml` has always been `ubuntu-latest` on all four jobs, and its runs
were still STARTING at 11:41–11:44Z** — after #5124 merged. Hosted pickup works;
the pool is saturated by the surge #5124 added (4 pack jobs × ~30 open PRs landing
on hosted at once, on top of the existing fences load).

githubstatus was all-operational throughout, so this is ours, not an incident.

**Therefore: wait. Do not revert #5124, do not re-push, do not re-dispatch.** The
correct move is the standing one — arm `merge-on-green` and let the sweeper merge
when checks conclude. Both gates are armed. If the backlog is still not draining
after a few hours, that is new evidence and worth an operator conversation about
the org's hosted concurrency ceiling; it is not a same-session revert.

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
