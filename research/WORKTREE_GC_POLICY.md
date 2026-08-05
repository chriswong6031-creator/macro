# Worktree GC policy — fleet session-checkout sweeper

**Status: PROPOSED — awaiting operator ratification. Nothing has been deleted.**
Tool: `scripts/worktree_gc.py` (shipped disarmed: `config/worktree_gc.json` → `"armed": false`).

## §0 Ratification box (operator decisions)

| # | Decision | Default shipped | Operator act |
|---|---|---|---|
| R1 | Arm deletion of `SAFE_MERGED` + `SAFE_REMOTE` worktrees, `min_age_days: 7` | disarmed | flip `"armed": true` in `config/worktree_gc.json` (one-line PR) |
| R2 | Install the daily launchd sweeper on the Studio | not installed | run `bash scripts/install_worktree_gc_launchd.sh` on the Studio |
| R3 | Same for the M1 host when it returns (currently unreachable) | not installed | same installer over ssh; feed it `--pr-states-file` if gh is unauthenticated there |
| R4 | Reclaim `ORPHAN` husks (unregistered dirs under the roots) | off | `"include_orphans": true` |
| R5 | Reclaim clean+pushed worktrees of OPEN PRs (branch/PR survive; only the local checkout goes) | off | `"include_open_pr": true` |
| R6 | charting-app: same sweep for its 103 GiB `.claude/worktrees` | report-only | arm a `config/worktree_gc.json` there (tool takes `--repo-root`) |

First armed run on the Studio: suggest `--apply --dry-run` once, eyeball the log, then `--apply`.
`max_delete_per_run: 200` caps a single pass; the daily schedule drains any remainder.

## 1. The problem (measured 2026-08-05, Studio)

Disk at **96 %** (1.7 Ti / 1.8 Ti, 89 Gi free). Session worktrees are never deleted, one per session since ~June:

| Root | Entries | Size |
|---|---:|---:|
| Macro `.claude/worktrees/` | 186 dirs (217 registrations repo-wide) | **597.5 GiB** |
| Macro `.codex-worktrees/` | 13 | 37.0 GiB |
| `~/.codex/worktrees/` (legacy home root) | 14 | 34.4 GiB |
| Macro `.claire/worktrees/` | 3 husks | ~0 |
| charting-app `.claude/worktrees/` | ~edge | 103.3 GiB |
| **Fleet sprawl total** | | **≈ 772 GiB** |

A typical checkout is ~3.2 GiB (site/ + data/ working copies). The M1 runner host
(mac-builder-1/2/3) hit **ENOSPC 2026-08-04**, killing the runner Worker mid-collect
(run 30960328285) and severing the nightly collection lane; it very likely carries the
same sprawl. As of this audit the M1 is unreachable over ssh (Tailscale timeout) and
its three runners are offline; Studio spares mac-builder-4/5 are online carrying load.

## 2. Safety model (what "provably safe to remove" means)

Deleting a worktree directory can lose exactly two things: **uncommitted files** and
**commits reachable only from its local branch**. The branch ref itself lives in the
shared `.git` and is deleted only under its own proof. So a worktree is safe iff it is
**not in use** and **holds no unique content**:

**Liveness (all must clear):**
- No `git worktree lock` (sessions annotate locks with pid — honored unconditionally).
- No process with cwd inside (one global `lsof -d cwd` pass; never per-tree `+D` descents over 600 GiB).
- No STRONG activity within `min_age_days` (7 d). Strong = the last reflog **entry's embedded
  epoch** (real HEAD movement) and the harness session dir `~/.claude/projects/<path-slug>/`
  newest mtime. File mtimes are recorded but never gate — the audit caught two systematic
  stampers that would otherwise hold the gate shut forever: a repo-global `reflog expire`
  rewrote all 186 trees' `logs/HEAD` at 2026-08-04 15:38:24 (every dead tree read "0.2 d
  old"), and observer sweeps (`git status` from dashboards writes the index; Finder drops
  `.DS_Store`) kept 137/143 dead trees under 2 d by index/HEAD/dir mtimes while their
  reflog entries and transcripts sat weeks old. House law is same-day merge; 7 d without
  ref movement or transcript writes is dead by a wide margin — and the content proofs
  below, not the age gate, are the actual loss-prevention layer.

**Content (any one proof suffices):**
- `HEAD` is an **ancestor of `origin/main`** — nothing unique by construction; or
- a **MERGED PR exists whose `headRefOid` equals `HEAD` exactly** — squash-merge proof.
  Ancestry cannot see squashes and `delete_branch_on_merge=true` erases the remote branch,
  so PR state (via `gh pr list`, 3 quota-cheap calls) is the only sound proof here.
  Oid-exact matching means a head that moved past the merged commit stays kept; or
- `HEAD` is **contained in a still-existing origin branch** and **no PR is open** for it
  (`SAFE_REMOTE`: the checkout is a cache; content survives on the remote).

**Fail-closed everywhere:** any probe error/timeout, unreadable config, missing PR data,
stale remote refs after a failed `git fetch --prune`, or an unavailable lsof scan ⇒ KEEP
(and apply mode refuses outright without liveness data). Verdicts for kept trees:
`LOCKED / LIVE_PROC / RECENT / DIRTY / OPEN_PR / UNPUSHED / ERROR / ORPHAN`.

**Never candidates:** the primary checkout, the sweeper's own cwd, anything outside the
configured roots (`~/hub-ops-wt`, `/private/tmp` scratch registrations are out of scope;
dead registrations get `git worktree prune`d, which is metadata-only).

## 3. Mechanism

`git worktree remove --force` from the primary root (our proofs are stricter than git's;
`--force` only clears gitignored build junk objections), then one `git worktree prune`.
Local branch `git branch -D` **only** when the merge proof held and the branch tip still
equals the proven head. `ORPHAN` husks (dir without registration — git cannot status them)
use `rm -rf` and are **off by default** (R4). Every deletion appends a JSONL row
(path/branch/head/size/verdict/proof) to `~/Library/Logs/macro_worktree_gc/ledger.jsonl`.

## 4. Scheduling: launchd per host, not a repo workflow

The failure mode this tool exists for — disk full — **takes the host's own runners
offline** (that is how the M1 died), so a runner-scheduled workflow can never save the
host that needs it. GitHub cron also delivers ~15 % of slots in this repo. Hence
per-host launchd (`scripts/worktree_gc.launchd.plist` via the installer, daily 05:17
local, `Nice 15`, logs under `~/Library/Logs/macro_worktree_gc/`). Installing before R1
is safe: apply self-gates to report-only while disarmed. `scripts/metabolism_gc.py`
(wf_* autonomy-loop trees, journal-based proofs) stays as is — different scope; its
inverted ancestry check is flagged separately.

## 5. Measured classification & reclaim estimate (Studio)

<!-- AUDIT_TABLE -->

## 6. M1 plan (R3)

When reachable: `scp scripts/worktree_gc.py m1:` and run `--report --repo-root <primary>`
with `--pr-states-file pr_states_macro.json` (map emitted on the Studio) if `gh` is not
authenticated there — offline hosts consume Studio-fetched PR proofs; a failed fetch
marks remote refs stale and `SAFE_REMOTE` fails closed, but merged-PR and
ancestor-of-last-known-main proofs (both under-approve, never over-approve) still land.
If its disk is still wedged at 100 %, the report run needs no free space to speak of;
present its numbers, then arm.

## 7. Explicitly out of scope (v1)

- `git gc` / repack of the shared 29 GiB `.git` (concurrent-session risk; separate ask).
- Runner `_work` directories (bounded per-workflow reuse; separate lever).
- Killing orphaned shells whose cwd pins a worktree (`LIVE_PROC` pile) — surfaced in the
  report for manual window-closing; a "shell-only + git-idle ≥ 14 d doesn't count as
  live" rule is a possible R7 once the pile size is known.
- Preventing accumulation at the source (harness-side worktree lifecycle) — the daily
  sweeper makes steady-state ≈ (sessions/day × 3.2 GiB × 7 d) ≈ manageable; revisit only
  if that proves wrong.
