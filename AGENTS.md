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
`.github/workflows/merge-on-green.yml` (GitHub-hosted, every 10 minutes,
deliberately off the mac pool so it never queues behind a render) squash-merges the
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
Codex must follow the same chain directly from this file. A genuine repeated
external blocker must be reported as `SHIP LOOP BLOCKED:` with concrete evidence;
ordinary local cleanup, authentication setup, and waiting are not blockers.
The CI gate is base-side-aware: a red on the merged head that provably pre-existed
on main (same check failing on ≥2 independent concurrent PR heads pre-merge, or a
green ci.yml run on a main descendant) is excluded by name rather than pinning the
session forever; the operator lever for a healed base is
`gh workflow run ci.yml --ref main` — one green dispatched run clears every pinned
merge at once. Unknown or lone-sibling evidence stays `ci_failed` (fail-closed).

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
