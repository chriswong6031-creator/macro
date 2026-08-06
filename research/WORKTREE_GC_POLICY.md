# Worktree GC policy — fleet session-checkout sweeper

**Status: PROPOSED — awaiting operator ratification. Nothing has been deleted.**
Tool: `scripts/worktree_gc.py` (shipped disarmed: `config/worktree_gc.json` → `"armed": false`).

## §0 Ratification box (operator decisions)

| # | Decision | Default shipped | Operator act | Measured effect today |
|---|---|---|---|---|
| R1 | Arm deletion of `SAFE_MERGED` + `SAFE_REMOTE` and set `min_age_days` — **recommend 2** (3 = conservative, 7 = insurance-only) | disarmed, 7 d | flip `"armed": true` + set `"min_age_days"` in `config/worktree_gc.json` (one-line PR) | at 2 d: **51.3 GiB** now + caps the leak tail forever; at 7 d: ~0 today (nothing unpinned survives 7 d — see §5) |
| R2 | Install the daily launchd sweeper on the Studio | not installed | `bash scripts/install_worktree_gc_launchd.sh` on the Studio | keeps the tail drained daily |
| R3 | Same for the M1 host when it returns (unreachable at audit time, runners offline) | not installed | same installer over ssh; feed `--pr-states-file` if gh is unauthenticated there | unknown until reachable |
| R4 | Reclaim `ORPHAN` husks (unregistered dirs under the roots) | off | `"include_orphans": true` | ~0 GiB (4 empty husks) |
| R5 | Reclaim clean+pushed worktrees of OPEN PRs (branch/PR survive; only the local checkout goes) | off | `"include_open_pr": true` | small; open lanes are mostly RECENT anyway |
| R6 | charting-app: same sweep for its 103 GiB `.claude/worktrees` | report-only | arm a `config/worktree_gc.json` there (tool takes `--repo-root`) | **9.6 GiB** at 7 d already (16 trees); more at 2 d |
| R7 | Session-closing hygiene: **24 open sessions / 78.1 GiB** have their PR already squash-merged at the worktree head but stay pinned by their processes. Closing finished sessions releases them to the sweeper (all 62 pinned trees are < 2 d strong-active, so this is workflow, not archaeology) | keep all pinned | close finished sessions in FleetView as a habit | ~78 GiB now; keeps the done-pool draining |
| R8 | Structural: each checkout is 3.27 GiB, of which `data/` 2.10 + `site/` 0.67 = **85 %**. The ~0–2 d active window (~330 GiB at the measured ~40 sessions/day cadence) is a capacity requirement GC cannot reduce — a sparse-checkout session profile could cut it ~5×. Proposal note only | — | commission separately if wanted | ~250+ GiB of standing working set |

First armed run on the Studio: suggest `--apply --dry-run` once, eyeball the log, then `--apply`.
`max_delete_per_run: 200` caps a single pass; the daily schedule drains any remainder.

## 1. The problem (measured 2026-08-05, Studio)

Disk at **96 %** (1.7 Ti / 1.8 Ti, 89 Gi free). The fleet worktree roots hold:

| Root | Entries | Size |
|---|---:|---:|
| Macro `.claude/worktrees/` | 186 dirs (217 registrations repo-wide) | **597.5 GiB** |
| Macro `.codex-worktrees/` | 13 | 37.0 GiB |
| `~/.codex/worktrees/` (legacy home root) | 14 | 34.4 GiB |
| Macro `.claire/worktrees/` | 3 husks | ~0 |
| charting-app `.claude/worktrees/` | 130 | 103.3 GiB |
| **Fleet sprawl total** | | **≈ 772 GiB** |

**Corrected model (what the audit actually found):** this is *not* months of quiet
accumulation. The harness already recycles most closed sessions (at the measured
cadence of ~40 session worktrees/day, two months of pure leakage would be ~2,400
trees — only 186 exist). The pile decomposes into three different problems:

1. **The active window** — ~132 unpinned trees / ~417 GiB with strong activity
   < 3 d, plus 62 process-pinned trees / 203 GiB that are ALL < 2 d strong-active
   too (49 carry a live `claude` process). Fleet cadence × 3.27 GiB per checkout.
   GC cannot shrink the genuinely-working part; only R8 can.
2. **The done-but-still-here pool** — sessions whose PR is already squash-merged
   at exactly the worktree head: **64 idle trees / 201.4 GiB** (aging toward the
   min_age bar; 17 / 51.3 GiB past 2 d today) plus **24 still-open trees /
   78.1 GiB** whose processes pin them until the session is closed (→ R7).
   This ~280 GiB pool is what the sweeper + session hygiene continuously drain.
3. **The leak tail** — 4 DIRTY trees / 8.7 GiB idle 7–60 d holding uncommitted
   files (operator-review pile, listed in the report; never auto-deleted).

A typical checkout is 3.27 GiB: `data/` 2.10 + `site/` 0.67 (85 %) + code.
The M1 runner host (mac-builder-1/2/3) hit **ENOSPC 2026-08-04**, killing the
runner Worker mid-collect (run 30960328285) and severing the nightly collection
lane; it likely carries its own mix of the same three piles plus runner `_work`
churn. As of this audit the M1 is unreachable over ssh (Tailscale timeout) and
its three runners are offline; Studio spares mac-builder-4/5 are online carrying
the load.

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

## 5. Measured classification & reclaim estimate (Studio, 2026-08-05)

Receipts: `research/worktree_gc/2026-08-05_studio_*.{md,json}` (full per-tree verdicts).

**Macro root** (186 trees + husks; shipped default min_age 7 d; verdicts stable across
three audit passes):

| verdict | count | GiB | note |
|---|---:|---:|---|
| RECENT | 143 | 450.6 | strong activity < 7 d (histogram below) |
| LIVE_PROC | 62 | 203.0 | all < 2 d strong-active; 49 with live `claude` proc |
| DIRTY | 4 | 8.7 | idle 7–60 d, uncommitted files — operator-review pile |
| LOCKED | 1 | 3.3 | `x-growth-overhaul`, session lock honored |
| ORPHAN / SELF / MISSING | 4 / 1 / 1 | ~0 | husks; metadata prune only |
| **SAFE now (7 d)** | **0** | **0.0** | nothing unpinned survives 7 d — see below |

Strong-age histogram of unpinned trees (count / GiB): <1 d 36/117 · 1–2 d 68/215 ·
2–3 d 28/85 · 3–5 d 7/22 · 5–7 d 4/12 · ≥7 d 4/8.7 (the DIRTY pile).

**Why 7 d reclaims zero here and why that is not failure:** the harness already
recycles most closed sessions; what remains is the live fleet plus the done-pool.
The done-pool is real and measured — **64 idle trees / 201.4 GiB are oid-exact
squash-merged** (of which 17 / **51.3 GiB** already ≥ 2 d idle) and **24 pinned
trees / 78.1 GiB** more are merged but still open. R1 at min_age 2 d harvests the
idle half continuously; R7 releases the pinned half.

**charting-app root** (130 trees, min_age 7 d): SAFE_MERGED 14 + SAFE_REMOTE 2 =
**9.6 GiB reclaimable immediately**; RECENT 93 / 76.6 GiB; DIRTY 19 / 9.7 GiB;
UNPUSHED 14 / 7.1 GiB; LIVE_PROC 4. A smaller, older fleet → a genuine dead tail;
validates every verdict class on a second repo.

**Detector integrity (why the first two audit passes were discarded):** pass 1
read all trees "0.2 d old" — a repo-global `reflog expire` had stamped every
`logs/HEAD` file at 2026-08-04 15:38:24; pass 2 still read 137/143 "fresh" off
index/HEAD/dir file mtimes written by observer sweeps (`git status` from
dashboards, Finder `.DS_Store`). Both stampers are now regression-pinned in
`tests/test_worktree_gc.py`; the shipped probe gates on reflog ENTRY epochs +
session transcript mtimes only.

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
- Killing processes that pin `LIVE_PROC` trees — the sweeper only reports them (R7 is
  operator hygiene; a rule change would be its own ratified PR).
- Shrinking the active window (R8 sparse-checkout proposal) — capacity question, not GC.
- Steady state with R1 armed at 2 d ≈ active window (~330 GiB) + parked pile until R7
  acted on. The tail no longer grows; the window tracks fleet cadence.
