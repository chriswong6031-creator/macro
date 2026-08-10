# Macro Dashboard — shared agent operating rules

This repository is operated by multiple Claude accounts and Codex sessions. Repository files are the durable, shared source of instructions; promises or “memory” recorded only inside one chat do not carry to another session.

## Required context at the start of every task

1. Read `CLAUDE.md` in full and follow it as the authoritative project guide.
2. Search the Claude project memory index at
   `~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/memory/MEMORY.md`
   and open the entries relevant to the task. For delivery work, always include
   `session-finish-full-git-chain`, `auto-finish-commit-push-pr`, and
   `go-live-deploy-mechanics`.
3. Treat `/Users/chriswong/Documents/Cluade/charting-app` as the connected Terminal
   repository. Authentication, subscriptions, data contracts, APIs, and deployment
   changes may require checking both repositories.

## Navigation source-of-truth

There are exactly two global navigation families:

- Authenticated/product pages use `templates/_site_nav.html.j2`. Its inventory
  lives in `templates/_navlinks.html.j2`; shared geometry, responsive behavior,
  mega menus, ticker search and motion live in
  `templates/navigation-refresh.css`, `templates/nav_market.js`, and
  `templates/theme.js`.
- Anonymous/corporate pages use `templates/_public_nav.html.j2` with
  `templates/_public_chrome_css.html.j2` and
  `templates/_public_chrome_js.html.j2`. The hand-authored landing page mirrors
  that family in `templates/index.html`/`templates/landing.css`, guarded by
  `tests/test_public_chrome.py`.

Do not hand-copy or restyle a third header inside a page template. A page may
provide a relative `nav_prefix`, but page CSS must not change the global
header's width, typography, menu dimensions, search behavior, breakpoints or
motion. Change the appropriate shared family and its parity tests instead.

## Workspace and git

- The canonical project home is `/Users/chriswong/Documents/Cluade`.
- Never create project work in `~/.codex/worktrees`, `/private/tmp`, or another
  Codex-only location. Never use a `codex/` branch for these repositories.
- The primary checkout is shared and commonly dirty or detached. Do not change its
  files or git state. Fetch the remote default branch, then create a fresh worktree
  under this repository's `.claude/worktrees/<task>/` and use a `claude/<task>`
  branch.
- Macro branches start from fresh `origin/main`; Terminal branches start from fresh
  `origin/master`. Never reuse a squash-merged branch.
- Do not use the repo-global stash stack.
- Session worktrees are garbage-collected by `scripts/worktree_gc.py` per
  `research/WORKTREE_GC_POLICY.md` (report-first; deletion only while
  `config/worktree_gc.json` is `armed:true` — an operator ratification act). The
  sweeper honors `git worktree lock`, live process cwds, uncommitted/unpushed
  work, open PRs, and <7-day activity. To park a checkout long-term, lock it:
  `git worktree lock --reason "<why>" <path>`.

## Kill-registry citations (DO_NOT_REBUILD.md)

Rows in `research/DO_NOT_REBUILD.md` carry a stable `Key` column (`KILL-…` §1–2,
`LAW-…` §3, `HOLD-…` §4). Cite rows as `DNR:<KEY>` — for example
`DNR:KILL-PROPHET-POP-MERGE` — never by row or line number: numbers shift on
every append/reflow, and row-number citations have already mis-resolved in the
wild (2026-08-05). An adjudication that kills, forbids, or defers a topic
appends its row inside sections 1–4 only, mints a new unique Key, and commits
the regenerated `config/compiled_kill_registry.yml` and
`config/signal_foundry_blocklist.yml` in the same PR (manual heal:
`python3 scripts/check_blocklist_drift.py --fix`).

## Context economy (frontier burn is CONTEXT × TURNS)

Measured 2026-08-06 across 3,043 local transcripts (week of 07-30→08-06): of all
Fable burn, **62% was cache reads, 21% cache writes, only 17% output**. Cache
reads are the discount (0.1× fresh input), not the waste — never try to avoid
caching. The cost driver is `context size × turn count`, and the per-turn floor
is `0.1 × context`: ~15k units/turn at 150k context, ~80k at 800k.

The worst measured session ran 3,539 turns at a median 419k context (max 879k)
over 43h and 16 branches, costing 11.6% of the week's frontier budget on its
own. Its turns at ≥400k context were 52% of turns but 67% of its burn. Riding
context up to auto-compaction is the most expensive possible pattern: compaction
fires near the ceiling, so every turn on the approach bills at the ceiling rate.
There is no configurable compaction threshold and a session cannot compact
itself on demand.

- **Delegate execution; the orchestrator adjudicates.** 76% of that session's
  main-loop tool calls were `Bash`/`Edit`/`Read`/`Write`, and delegation was
  2.6%. A subagent's context is discarded on return — only its report lands — so
  delegating keeps tool output out of the orchestrator permanently.
- **Budget what enters context.** A tool result of size S landing at turn N is
  re-read on every remaining turn. Prefer targeted `grep`/line-ranged reads over
  whole files, cap command output (`head`, `--limit`, `--jq`), and keep browser
  screenshots and full page dumps inside a subagent.
- **One session = one task boundary.** A long program needs durable state on
  disk, not a long session. Run it as a chain of short sessions over a
  `research/*_CONTINUATION_HANDOFF_<date>.md`, one wave per session. Keep an
  orchestrator under ~200k; past ~250k, checkpoint to a handoff and let the
  operator clear rather than grinding to the ceiling.

Do NOT save tokens by reducing reasoning effort — output is only 17% of burn, so
cutting thinking degrades quality for at most a sixth of the cost. The savings
are in where work happens and how large the context is.

## Definition of done

For every substantive, verified change, complete the full delivery chain without
asking the operator to finish it:

1. commit;
2. push;
3. open a pull request;
4. check CI and resolve genuine failures;
5. same-day squash-merge and delete the remote branch;
6. deploy or wait for the repository's normal deploy lane, then verify the change
   on the real live URL.

Do not stop at a local commit or an open PR. The only holds are an explicit operator
request to hold, a genuine non-spurious failing check, or a real deployment blocker.
For Macro, the `Workers Builds: macro` red X is known-spurious. Template/source
changes must include their paired `site/` artifact when required, and “merged” is
not “live” until the VPS/render path and live marker are verified.

**Healing a red pack: claim the lane FIRST, and heal the WHOLE pack (2026-08-07,
#4850 closed unmerged).** A fleet-wide red is being worked by the whole fleet, so
before writing a line: identify every red job **by name** and confirm its pack
(`python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
--pack-index N --pack-count 12 --validate-only`) — never trust the pack index in a
failure report, `run_ci_pack.py` rebalances whenever any job's weight moves — then
check `gh pr list --search "<filename>"` and `docs/ACTIVE_BUILD_MAP.md` for an open
lane on the files you are about to touch. The "before proposing new work" rule is
scoped to NEW work and does not cover heals, which is exactly how this was missed.

**A pack is ONE check, so two partial heals DEADLOCK.** With two independent reds
in `ci-pack-3`, the ITR-only PR stayed red from the stale report and the
report-only PR stayed red from ITR: neither could ever go green, so neither could
merge. One PR must carry every fix the pack needs. Cherry-pick a sibling with `-x`
(authorship preserved) rather than rewriting it, and read its diff first — the
sibling's version is often the better one.

**Re-fetch `origin/main` and re-run the job line before pushing OR merging.** On a
red main the tree moves in hours (five heal PRs landed mid-session here), and a
`merge-blocked` "real content conflict" on a heal PR usually means the heal already
landed rather than that you must resolve anything. Diff against fresh main
(`git diff --stat origin/main HEAD -- <files>`; empty = already there) and **close
rather than force through** — a superseded regeneration silently reverts the better
fix that landed behind you (#4850's live-cache report would have reverted #4842's
frozen-slice render).

**Merge on CONCLUDED checks, never mid-flight (operator 2026-07-28).** A pending
check is not a pass: an `--admin` squash-merge while the PR's packs are still
running used to fire a `pull_request: closed` event into the live concurrency
group and cancel the PR's own proof run — the merged head then carried
`cancelled` packs forever (PR #3867), unproven merges stacked up red on main, and
every ship-loop session pinned on the next full-CI dispatch (measured 2026-07-28:
100 ci.yml runs in 8h, 6 successes). ci.yml now fences merged-close events into
their own concurrency group so a fast merge no longer destroys its own evidence,
but the discipline stands: wait for the packs to conclude (green, or spurious-only
red) before squash-merging. Do NOT arm `gh pr merge --auto --squash` as the wait:
main carries no branch protection, so auto-merge has no required checks to gate on
and merges IMMEDIATELY (verified PR #3889, 2026-07-28 — merged ~1 min after arming
with packs still pending).

**DEFAULT FINISH — hand the wait to the sweeper, do not sit on it.** After opening
the pull request, run `gh pr edit <n> --add-label merge-on-green` and stop.
`.github/workflows/merge-on-green.yml` (GitHub-hosted `ubuntu-latest`, every 10 minutes,
deliberately off every self-hosted render pool) squash-merges the
pull request once every check has CONCLUDED clean, with the known-spurious
`Workers Builds: macro` X excluded. A genuine red or a merge conflict gets the
`merge-blocked` label plus ONE explanatory comment instead of a merge; the
`merge-on-green` label stays armed, so a rerun that greens the head merges on the
next sweep. `ship_loop_guard.py` releases a session whose armed pull request
carries no concluded red — a head with NO non-spurious checks at all is unproven
and still blocks, because the sweeper will never merge that either. This is what
ends the 20-60 minute CI-hostage wait; the merge-on-CONCLUDED discipline itself is
unchanged, only who waits. Merging by hand on concluded-green stays valid whenever
you prefer to watch it. After any accidental fast merge, the surviving PR proof run
is the merge's evidence — watch it to conclusion. `--admin` remains only for the
spurious Workers X, docs-only pull requests that trigger no pack checks, and
genuine wedges — never to outrun CI.

**A `merge-blocked` backlog means main is UNPROVEN, not that the pull requests are
bad (#5037, 2026-08-08).** The sweeper's base-inherited-red refresh — the mechanism
that drains an armed backlog once main is healed — can only tell an inherited red
from a real one against a RECENT proof of main. `ci.yml` has no `push` trigger, so
main is proven ONLY by a `workflow_dispatch`, while the nightly/wire lanes push ~24
`[skip ci]` commits per 2 hours — so any commit-window heuristic ages out in ~100
minutes. Measured 2026-08-08: main's newest proof sat **117 commits / 12 HOURS**
back, the refresh resolved zero pack names, and 61 pull requests sat armed with 60
of them red on `ci-pack-2`/`ci-pack-3` that main's own last run had proven green.
Three properties now hold and must not be regressed: the proof is resolved from the
newest completed `ci.yml`/`fences.yml` **RUN on main** (velocity-independent, and
cheaper than the walk it replaced); a refresh additionally requires that proof to
**POSTDATE** the pull request's failing checks (correctness — a green that predates
your red does not excuse it — and the loop guard, because `update-branch`'s
422-on-current-head does NOT prevent loops when main moves every few minutes); and
the sweeper **dispatches its own main baseline** when its proof is too stale to
answer the reds it just saw. **Diagnose a fresh backlog from the sweep log first:** a
summary reading `0 main commit(s) classified`, or a proof set carrying no
`ci-pack-*`, means the refresh path is closed no matter how green main is. Operator
lever unchanged: `gh workflow run ci.yml --ref main`.

**But NEVER dispatch over a live baseline (livelock, measured 2026-08-09).**
Main-ref ci.yml dispatches share ONE concurrency group with
`cancel-in-progress: true`, so every re-dispatch KILLS the in-flight proof: the
11:00Z baseline died 44 min in — likely minutes from concluding — to a sibling
session's re-dispatch, whose own run died 4 min later to the next session's. With
several pinned sessions each firing the lever, no proof ever concludes, the
sweeper keeps reading `0 main commit(s) classified`, and the entire fleet stays
pinned — the escape hatch IS the lock. (fences.yml's main-push runs were dying
the same way under main's ~1/min push cadence, closing the other proof source;
structural fix = event-conditional cancel-in-progress, in flight 2026-08-09.)
Preflight before the lever:
`gh run list --workflow ci.yml --branch main --json databaseId,status,createdAt --jq '[.[]|select(.status!="completed")]'`
— anything `queued`/`in_progress` → WATCH it (`gh run watch <id> --interval 60`)
instead of dispatching. Dispatch only over a clear field, or over a run stuck
`queued` >40 min with the pool otherwise moving (orphaned-run escape — your
dispatch is then the mercy kill, not a murder).

### Waiting on CI without jamming every other session

`gh` authenticates as ONE account token, so GitHub REST's 5,000/hr `core` pool is a
single bucket shared by every parallel session, the babysitter lane, and the hooks.
Exhausting it 403s all of them for up to an hour — including `ship_loop_guard.py`,
which spends up to four REST calls per Stop evaluation and **fails closed** when
rate-limited, so over-polling blocks the very Stop the polling was meant to reach.
A ci.yml run here takes 30–34 minutes; there is no reason to poll it faster than a
couple of times per minute.

`.claude/hooks/gh_quota_guard.py` (PreToolUse on Bash) denies the three shapes that
emptied the pool on 2026-07-26:

- `gh run watch` at its **default `--interval 3`** — nothing on the command line
  says "3 seconds", which is exactly why it passed review. Use `--interval 60`+.
- a `gh` call inside a loop sleeping under 90s (two watchers on one endpoint at 45s
  went 4,488 → 0 in under an hour);
- `--paginate` over check-runs/jobs — ~130 checks per PR, where one page already
  answers "is it still running".

Preflight `gh api rate_limit --jq '.resources.core.remaining'` before arming any long
watch, run ONE watcher per endpoint, and never read an empty or 403 response as a
settled/green result. REST and GraphQL are separate 5,000/hr pools, so `gh pr view`
continuing to work does not mean `gh api` will.

When an operating standard changes, update the repository's `AGENTS.md` and
`CLAUDE.md` together so both Codex and every Claude account inherit it.

### GitHub annotations must start the line (CI-guarded)

Emit `::warning` / `::error` / `::notice` with a bare
`print("::warning title=<slug>::<msg>", flush=True)` — never through a logger.
GitHub only parses a workflow command when `::` is the first thing on the line,
and every builder here logs with a prefixing format, so
`log.warning("::warning ...")` emits `WARNING ::warning ...` and the annotation
is silently dropped. The call reviews as an alarm, runs without error, and
produces nothing in the Actions summary — the worst failure mode for a
fail-soft, which ships degraded output with its only signal gone.

This shipped dead five separate times (#3487, #3515, #3562, #3563, #3570) before
#3587 swept 69 sites across 21 modules and added the guard at
`tests/test_gh_annotation_line_start.py`. Notes:

- `flush=True` is load-bearing: stdout is block-buffered when piped in CI, and
  these sit on paths that may precede a crash.
- Modules that never execute inside an Actions step (FastAPI request paths —
  `brain_gateway`, `download_quota`, `view_ratelimit`) are EXEMPT and listed in
  that test; check `app/` / `admin/` imports before converting an `engine/`
  module, because adding a `print` to a request path is wrong.
- Converting breaks any test that asserts the annotation via `caplog`. Switch it
  to `capsys` AND assert `line.startswith("::")`, so the test pins the property
  that was actually broken rather than the message wording.
- To prove an annotation is live, use GitHub's annotations API — it returns only
  lines it actually parsed:
  `gh api "repos/<o>/<r>/actions/runs/<id>/jobs" --jq '.jobs[].id'` then
  `gh api "repos/<o>/<r>/check-runs/<job_id>/annotations"`.

### Shared render-lane safety

`render.yml` is one shared, coalescing deploy lane. A successful push render at
a merge SHA or any later main descendant covers the earlier merge because the
workflow unions every dirty scope since its last covering watermark. Monitor
that shared covering run; do not demand a dedicated successful run for every
merge SHA.

A **paired plain-copy asset PR needs no render at all.** A non-`.j2` file under
`templates/` that also ships as `site/<name>` — the 56 pairs
`scripts/check_template_site_sync.py` enumerates: `theme.js`, `mm_brain.js`,
`onboard.js`, `index.html`, the `*.css` — has its `site/` copy committed straight
to main, and the VPS `macro-update` cron pulls main every 3 minutes, so it is live
within minutes whether render ever completes or not. render.yml produces only two
things: re-baked `.j2` pages and the `?v=` content-hash re-stamp. Do not wait on a
perpetually superseded render for such a PR, and do not report it as a blocker.
The one thing you forfeit is that re-stamp: the Caddyfile pins `?v=`-carrying
requests to `immutable, max-age=1y` for an enumerated list (`theme.js`, `live.js`,
`theme.css`, `product-nav-icons.css`, `onboard.*`, `landing.css`, `account.js`,
`nav_market.js`, `supabase.js`, `data_base.js`, `chat*.css`,
`assets/{css,landing}/*`), so for those a warm-cache visitor keeps the old body
until a later render re-hashes the pages that reference them. New visitors always
get fresh bytes. `.j2` pages, `scripts/build_*.py`, and the page-rewriting sweeps
(`optimize_assets.py`, `externalize_css.py`, `inject_data_base.py`, `lib/pages.py`)
still require the render before they are live.

Never cancel or manually re-run an in-progress `render`, `engine-render`, or
`daily` solely to unblock a session. A long job inside its declared timeout is
not wedged evidence. Re-run only after the job has concluded unsuccessfully,
the cause has been identified or corrected, and one session owns the recovery.
Parallel sessions must reuse that recovery instead of launching retries of
their own.

The contract is actively enforced for Claude by the tracked `SessionStart` and
`Stop` hook in `.claude/hooks/ship_loop_guard.py`. It snapshots pre-existing dirty
files, then refuses a normal stop while session-created work is uncommitted,
unpushed, unmerged, awaiting a render, or absent from production.
The dirty snapshot judges only this checkout's own work. Untracked entries under
another fleet's worktree roots (`.claude/worktrees/`, `.claire/worktrees/`,
`.codex-worktrees/`) are excluded — a blocked session can neither commit another
session's checkout nor delete it without destroying live work — and a path that
LEAVES `git status`, whether committed or newly ignored, stops counting as
outstanding. Both stay fail-closed: tracked content under those roots gates
normally, and a tracked file the session deleted is still reported by git as
` D`, so it still blocks.
Codex must follow the same chain directly from this file. A genuine repeated
external blocker must be reported as `SHIP LOOP BLOCKED:` with concrete evidence;
ordinary local cleanup, authentication setup, and waiting are not blockers.
The CI gate is base-side-aware: a red on the merged head that provably pre-existed
on main (same check failing on ≥2 independent concurrent PR heads pre-merge, or a
green ci.yml run on a main descendant) is excluded by name rather than pinning the
session forever; the operator lever for a healed base is
`gh workflow run ci.yml --ref main` — one green dispatched run clears every pinned
merge at once, but preflight for an in-flight baseline first (see the livelock
note above: a re-dispatch cancels the very proof every pinned session is waiting
on). Unknown or lone-sibling evidence stays `ci_failed` (fail-closed).

An IN-FLIGHT covering render DEFERS rather than blocks (operator ruling
2026-07-27): a queued or running render whose head covers this merge satisfies the
render gate and the session proceeds to the live check, because the VPS pulls main
every 3 minutes so the merge is live regardless, the shared lane owns the re-bake,
house law forbids a waiting session from cancelling or re-running it, and the
nightly `scope=all` re-render is the backstop. A render lane that NEVER started
(the dead-wire trap) or that concluded FAILED with no in-flight successor still
blocks. Every blocker also carries an escape ladder so an unsatisfiable gate can no
longer trap a session indefinitely: an EXTERNAL blocker escapes at 2 consecutive OR
3 cumulative external blocks; ANY code (including the internal ones —
unmerged/unpushed/uncommitted/unsafe_branch/guard_error) escapes at 10 consecutive
OR 15 total blocks. Every escape still requires an explicit `SHIP LOOP BLOCKED:`
evidence report with `stop_hook_active` set, so a session cannot bail on the first
attempt.
