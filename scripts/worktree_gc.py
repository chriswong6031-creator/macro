"""scripts/worktree_gc.py — fleet session-worktree GC (report-first, ratification-gated).

The agent fleets accumulate one checkout per session under the worktree roots
named in .claude/hooks/ship_loop_guard.py (`.claude/worktrees/`,
`.claire/worktrees/`, `.codex-worktrees/`) plus the legacy `~/.codex/worktrees`
home root.  Nothing ever deleted them: 2026-08-05 the Studio carried 186
checkouts / ~580G under `.claude/worktrees` alone with the disk at 96%, and the
M1 runner host hit ENOSPC (2026-08-04) which killed mac-builder-1/2/3 mid-run.

This tool is the sweeper.  It is REPORT-FIRST and RATIFICATION-GATED:

  * `--report` (default) mutates nothing — it classifies every registered
    worktree under the configured roots and writes a packet (markdown + json)
    with a measured reclaim estimate.
  * `--apply` deletes only worktrees whose verdict is provably safe, and only
    when config/worktree_gc.json carries `"armed": true` — the operator's
    ratification switch.  Shipped disarmed.

SAFETY MODEL (fail-closed).  A worktree is deleted only when EVERY probe
succeeded and EVERY proof holds; any error, timeout, or unknown → KEEP.
Verdict lattice (first match wins):

  PRIMARY      the primary checkout — never a candidate
  SELF         the sweeper's own cwd lives inside it
  MISSING      registered but directory gone → metadata prune only
  LOCKED       `git worktree lock` present (sessions lock their checkouts)
  ERROR        a probe failed → keep
  LIVE_PROC    a process has its cwd inside the worktree (one global
               `lsof -d cwd` pass — never per-tree `+D` descents)
  RECENT       STRONG activity newer than min_age_days.  Strong = the last
               reflog ENTRY's embedded epoch (real HEAD movement) and the
               session transcript dir ~/.claude/projects/<slug>.  File
               mtimes never gate: repo-global `reflog expire` stamps every
               tree's logs/HEAD at once, and observer sweeps (dashboards
               running `git status`, Finder .DS_Store) stamp index/HEAD/dir
               mtimes — measured pinning 137/143 dead trees "fresh"
  DIRTY        `git status --porcelain` non-empty (tracked changes or
               non-ignored untracked files) → unsubmitted work, keep
  OPEN_PR      branch has an open PR → live lane, keep (v1)
  UNPUSHED     HEAD holds commits reachable from no origin ref and no merged
               PR proof → unique work, keep
  SAFE_MERGED  content provably in main: HEAD is an ancestor of origin/main,
               or a MERGED PR exists whose headRefOid == HEAD (squash-merge
               proof — delete_branch_on_merge=true erases the remote branch,
               so ancestry alone cannot see a squash)
  SAFE_REMOTE  HEAD is contained in a still-existing origin branch and no PR
               is open for it → content recoverable from the remote
  ORPHAN       directory under a root with no live worktree registration —
               reported; deleted only when config include_orphans=true

Squash-merge proof is PR-state based on purpose: `branch..origin/main`-style
ancestry reads are blind to squashes (and inverted checks reap rebased
branches — see scripts/metabolism_gc.py history).  PR states come from
`gh pr list` (3 calls, quota-cheap) or an injected --pr-states-file so an
offline host (the M1) can consume a map emitted on a connected host.

Distinct from scripts/metabolism_gc.py, which reaps only the autonomy loop's
wf_*/metabolism-* worktrees on journal-based proofs.  This tool never touches
journals, ledgers, data/, or site/.

Scheduling: launchd per host (see ops/worktree-gc.launchd.plist +
scripts/install_worktree_gc_launchd.sh), NOT a repo workflow — a disk-full
host takes its own runners offline (the M1 failure mode), so the sweeper must
not depend on the runner fleet it exists to protect.

Usage:
    python3 scripts/worktree_gc.py --report [--json-out P] [--md-out P]
    python3 scripts/worktree_gc.py --report --emit-pr-states P   # for offline hosts
    python3 scripts/worktree_gc.py --apply                       # requires armed:true
"""
from __future__ import annotations

import argparse
import glob as globmod
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import worktree_storage
except ModuleNotFoundError:
    import worktree_storage

log = logging.getLogger("worktree_gc")

DEFAULT_CONFIG_REL = "config/worktree_gc.json"

DEFAULT_CONFIG = {
    "armed": False,
    "min_age_days": 7,
    "include_open_pr": False,
    "include_orphans": False,
    "delete_local_branches": True,
    "max_delete_per_run": 200,
    "pr_limit": 1000,
    "roots": [
        ".claude/worktrees",
        ".claire/worktrees",
        ".codex-worktrees",
        "~/.codex/worktrees",
    ],
}

KEEP_VERDICTS = {
    "PRIMARY", "SELF", "LOCKED", "ERROR", "LIVE_PROC", "RECENT",
    "DIRTY", "OPEN_PR", "UNPUSHED", "OUT_OF_SCOPE",
}
SAFE_VERDICTS = {"SAFE_MERGED", "SAFE_REMOTE"}

LEDGER_DIR = Path.home() / "Library" / "Logs" / "macro_worktree_gc"


# ── subprocess helpers ───────────────────────────────────────────────────────

def _run(args: list[str], cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command; (rc, stdout, stderr).  rc=-1 on timeout/OSError."""
    try:
        p = subprocess.run(
            args, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, p.stdout, p.stderr
    except (subprocess.TimeoutExpired, OSError) as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"


def _git(repo: Path, *args: str, timeout: int = 30) -> tuple[int, str, str]:
    return _run(["git", "-C", str(repo), *args], timeout=timeout)


# ── discovery ────────────────────────────────────────────────────────────────

@dataclass
class Worktree:
    path: Path
    head: str = ""
    branch: str | None = None       # short name, e.g. claude/foo
    locked: bool = False
    lock_reason: str = ""
    prunable: bool = False
    detached: bool = False
    root: str = ""                  # which configured root it fell under
    size_kb: int | None = None
    age_days: float | None = None   # most recent activity, any source
    age_sources: dict = field(default_factory=dict)
    procs: list[str] = field(default_factory=list)
    verdict: str = ""
    proof: str = ""
    reasons: list[str] = field(default_factory=list)
    orphan: bool = False            # directory with no registration


def resolve_primary_root(start: Path | None = None) -> Path:
    """Primary checkout root = parent of the common git dir."""
    rc, out, err = _git(start or Path.cwd(), "rev-parse", "--path-format=absolute", "--git-common-dir")
    if rc != 0:
        raise SystemExit(f"cannot resolve git common dir: {err.strip()}")
    common = Path(out.strip())
    return common.parent


def path_under_session_root(path: Path, rel_roots: list[str]) -> bool:
    """True when ``path`` sits inside one of the repo-relative session roots."""
    parts = Path(path).parts
    for rel in rel_roots:
        marker = tuple(rel.strip("/").split("/"))
        span = len(marker)
        for index in range(len(parts) - span + 1):
            if parts[index:index + span] == marker:
                return True
    return False


def host_checkouts(primary: Path, registered: list["Worktree"], rel_roots: list[str]) -> list[Path]:
    """Every checkout that can HOST session worktrees, primary first.

    The configured roots are repo-RELATIVE, and until 2026-08-20 they were only
    ever expanded under the primary checkout. That silently scoped the sweeper to
    one folder: a session tree planted under any other checkout of the same clone
    matched no root, so it never entered ``in_scope``, never reached the report,
    and would have been refused at the deletion belt as "outside configured
    roots" even if it had. A clone with two checkouts (here: the occupied primary
    and the operator's designated local root) has two places worktrees are
    planted, and the sweeper has to sweep both.

    A registration that is ITSELF under a session root is a session tree, not a
    host — including it would let the sweeper expand roots inside the very trees
    it reclaims.
    """
    hosts = [primary.resolve()]
    for wt in registered:
        try:
            path = wt.path.resolve()
        except OSError:
            continue
        if path in hosts or path_under_session_root(path, rel_roots):
            continue
        hosts.append(path)
    return hosts


def parse_worktree_list(text: str) -> list[Worktree]:
    out: list[Worktree] = []
    cur: Worktree | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("worktree "):
            if cur is not None:
                out.append(cur)
            cur = Worktree(path=Path(line[len("worktree "):]))
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur.head = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            b = line[len("branch "):].strip()
            cur.branch = b[len("refs/heads/"):] if b.startswith("refs/heads/") else b
        elif line == "detached":
            cur.detached = True
        elif line.startswith("locked"):
            cur.locked = True
            cur.lock_reason = line[len("locked"):].strip()
        elif line.startswith("prunable"):
            cur.prunable = True
    if cur is not None:
        out.append(cur)
    return out


def expand_roots(hosts: Path | list[Path], roots: list[str]) -> list[Path]:
    """Absolute sweep roots. A relative root expands under EVERY host checkout."""
    if isinstance(hosts, (str, Path)):
        hosts = [Path(hosts)]
    out: list[Path] = []
    for r in roots:
        p = Path(os.path.expanduser(r))
        if p.is_absolute():
            if p not in out:
                out.append(p)
            continue
        for host in hosts:
            q = Path(host) / r
            if q not in out:
                out.append(q)
    return out


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


# ── probes ───────────────────────────────────────────────────────────────────

def proc_cwd_map(roots: list[Path]) -> dict[str, list[str]] | None:
    """One global lsof pass: worktree-root-prefixed cwd → ["pid:cmd", ...].

    Returns None when the scan itself failed (fail-closed upstream: apply mode
    refuses to run without liveness data).
    """
    rc, out, err = _run(["lsof", "-d", "cwd", "-Fpcn"], timeout=90)
    # lsof exits 1 when some processes could not be inspected — output is
    # still usable; only an empty stdout means the scan truly failed.
    if not out.strip():
        log.warning("lsof cwd scan produced no output (rc=%s err=%s)", rc, err.strip()[:200])
        return None
    hits: dict[str, list[str]] = {}
    pid = cmd = ""
    root_strs = [str(r.resolve()) + os.sep for r in roots]
    for line in out.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid = val
        elif tag == "c":
            cmd = val
        elif tag == "n":
            for rs in root_strs:
                if val.startswith(rs):
                    hits.setdefault(val, []).append(f"{pid}:{cmd}")
                    break
    return hits


def _slugs(path: Path) -> list[str]:
    s = str(path)
    base = s.replace("/", "-").replace(".", "-").replace(" ", "-")
    variants = {base, base.replace("_", "-")}
    return sorted(variants)


def session_activity_mtime(path: Path) -> float | None:
    """Newest mtime among the harness's per-worktree session dirs, if any."""
    bases = [Path.home() / ".claude" / "projects"]
    bases += [Path(p) for p in globmod.glob("/private/tmp/claude-*")]
    newest: float | None = None
    for b in bases:
        for slug in _slugs(path):
            d = b / slug
            try:
                if not d.is_dir():
                    continue
                mt = d.stat().st_mtime
                for e in os.scandir(d):
                    try:
                        mt = max(mt, e.stat().st_mtime)
                    except OSError:
                        continue
                newest = mt if newest is None else max(newest, mt)
            except OSError:
                continue
    return newest


def _reflog_last_epoch(gitdir: Path) -> float | None:
    """Timestamp embedded in the LAST reflog entry (real HEAD movement).

    The reflog file's mtime is NOT usable as an activity signal: repo-global
    maintenance (`git gc` → `reflog expire`) rewrites every worktree's
    logs/HEAD in one sweep — measured 2026-08-04 15:38:24 stamping all 186
    trees at once, which made every dead worktree look 0.2 d old.  The entry
    content carries its own epoch and survives such sweeps.
    """
    try:
        lines = (gitdir / "logs" / "HEAD").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if not lines:
            return None
        toks = lines[-1].split("\t", 1)[0].split()
        return float(toks[-2])  # "<old> <new> <ident> <epoch> <tz>"
    except (OSError, ValueError, IndexError):
        return None


def activity_age_days(wt: Worktree, gitdir: Path | None, now: float) -> tuple[float | None, dict]:
    """Age in days of the most recent STRONG activity signal.

    Strong signals — things only real usage produces:
      * the last reflog ENTRY's embedded epoch (actual HEAD movement), and
      * the session transcript dir's newest mtime (the harness writes it for
        the owning session only).

    File mtimes (gitdir HEAD/index, the worktree dir, .git) are recorded for
    the report but NEVER gate: they are observer-stampable.  Measured on the
    Studio 2026-08-05: 137 of 143 long-dead trees read "active < 2 d" purely
    from index/HEAD/dir mtimes (fleet dashboards running plain `git status`
    write the index; Finder drops .DS_Store into the dir) while reflog entries
    and transcripts sat weeks old — a gate on file mtimes never opens, which
    is not conservatism but a dead detector.  Content proofs (clean tree +
    merged/remote) remain the actual loss-prevention layer; locks and live
    process cwds still veto independently.

    Returns (strong_age_days | None, sources).  None = no strong signal
    readable — callers fail closed for registered trees; orphans (no git
    metadata at all) fall back to the weak file mtimes recorded in sources.
    """
    strong: dict[str, float] = {}
    weak: dict[str, float] = {}

    def _stat(label: str, p: Path) -> None:
        try:
            weak[label] = p.stat().st_mtime
        except OSError:
            pass

    _stat("worktree_dir", wt.path)
    _stat("dot_git", wt.path / ".git")
    if gitdir is not None:
        _stat("gitdir_HEAD", gitdir / "HEAD")
        _stat("gitdir_index", gitdir / "index")
        re_epoch = _reflog_last_epoch(gitdir)
        if re_epoch is not None:
            strong["reflog_entry"] = re_epoch
    sm = session_activity_mtime(wt.path)
    if sm is not None:
        strong["session_dir"] = sm

    sources = {f"weak:{k}": round((now - v) / 86400.0, 2) for k, v in weak.items()}
    sources.update({k: round((now - v) / 86400.0, 2) for k, v in strong.items()})
    if not strong:
        return None, sources
    return (now - max(strong.values())) / 86400.0, sources


def gitdir_for(wt: Worktree) -> Path | None:
    """Resolve the worktree's private gitdir from its .git pointer file."""
    dot = wt.path / ".git"
    try:
        txt = dot.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in txt.splitlines():
        if line.startswith("gitdir:"):
            p = Path(line[len("gitdir:"):].strip())
            return p if p.is_dir() else None
    return None


def status_clean(wt: Worktree) -> bool | None:
    """True = clean, False = dirty, None = unknown (fail-closed to keep)."""
    rc, out, err = _run(
        ["git", "--no-optional-locks", "-C", str(wt.path), "status", "--porcelain"],
        timeout=120,
    )
    if rc != 0:
        log.warning("status failed for %s: %s", wt.path.name, err.strip()[:200])
        return None
    return not out.strip()


def du_kb(path: Path) -> int | None:
    rc, out, _ = _run(["du", "-sk", str(path)], timeout=900)
    if rc != 0 or not out.strip():
        return None
    try:
        return int(out.split()[0])
    except (ValueError, IndexError):
        return None


# ── remote / PR state ────────────────────────────────────────────────────────

def fetch_origin(primary: Path) -> bool:
    rc, _, err = _git(primary, "fetch", "--prune", "--quiet", "origin", timeout=600)
    if rc != 0:
        log.warning("git fetch --prune failed (continuing with stale refs): %s", err.strip()[:200])
        return False
    return True


def load_pr_states(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items()}


def gh_pr_states(primary: Path, limit: int) -> dict[str, dict] | None:
    """branch → {state, number, headRefOid}.  MERGED > OPEN > CLOSED precedence.

    None on any gh failure (fail-closed: PR-dependent proofs become unknown).
    """
    rc, out, err = _run(["gh", "api", "rate_limit", "--jq", ".resources.graphql.remaining"], timeout=30)
    if rc != 0:
        log.warning("gh rate_limit preflight failed: %s", err.strip()[:200])
        return None
    try:
        if int(out.strip()) < 200:
            log.warning("graphql quota low (%s) — skipping PR-state fetch", out.strip())
            return None
    except ValueError:
        return None

    states: dict[str, dict] = {}
    rank = {"CLOSED": 0, "OPEN": 1, "MERGED": 2}
    for state, lim in (("closed", limit), ("open", 200), ("merged", limit)):
        rc, out, err = _run(
            ["gh", "pr", "list", "--state", state, "--limit", str(lim),
             "--json", "number,headRefName,state,headRefOid"],
            cwd=primary, timeout=900,
        )
        if rc != 0:
            log.warning("gh pr list --state %s failed: %s", state, err.strip()[:200])
            return None
        for pr in json.loads(out):
            b = pr.get("headRefName") or ""
            cur = states.get(b)
            if cur is None or rank.get(pr["state"], -1) >= rank.get(cur["state"], -1):
                states[b] = {"state": pr["state"], "number": pr["number"],
                             "headRefOid": pr.get("headRefOid", "")}
    return states


# ── classification ───────────────────────────────────────────────────────────

def classify(
    wt: Worktree,
    primary: Path,
    cfg: dict,
    procs: dict[str, list[str]] | None,
    pr_states: dict[str, dict] | None,
    remote_fresh: bool,
    self_cwd: Path,
    now: float,
) -> None:
    """Assign wt.verdict / wt.proof / wt.reasons.  Fail-closed at every step."""
    if wt.path.resolve() == primary.resolve():
        wt.verdict = "PRIMARY"
        return
    if _under(self_cwd, wt.path):
        wt.verdict = "SELF"
        return
    policy = cfg.get("_storage_policy")
    external = policy is not None and Path(policy["root"]) in wt.path.parents
    if external:
        try:
            worktree_storage.check_storage(policy, wt.path, check_space=False)
        except (worktree_storage.StorageError, OSError) as exc:
            wt.verdict = "ERROR"
            wt.reasons.append(f"external volume unverified: {exc}")
            return
    if not wt.path.exists():
        wt.verdict = "MISSING"
        wt.reasons.append("registered but directory gone (git worktree prune)")
        return
    if wt.locked and not (external and wt.lock_reason == worktree_storage.LOCK_REASON):
        wt.verdict = "LOCKED"
        wt.reasons.append(wt.lock_reason or "git worktree lock present")
        return

    # Age is computed before the process check so pinned trees still REPORT
    # their idle age (the LIVE_PROC pile is an operator lever and needs the
    # number); the verdict priority is unchanged — processes always veto.
    gitdir = gitdir_for(wt)
    wt.age_days, wt.age_sources = activity_age_days(wt, gitdir, now)

    if procs is None:
        wt.verdict = "ERROR"
        wt.reasons.append("process scan unavailable — liveness unknown")
        return
    prefix = str(wt.path.resolve()) + os.sep
    exact = str(wt.path.resolve())
    live = [p for cwd, ps in procs.items() for p in ps if cwd == exact or cwd.startswith(prefix)]
    if live:
        wt.procs = sorted(set(live))[:8]
        wt.verdict = "LIVE_PROC"
        wt.reasons.append(f"{len(live)} process(es) cwd inside")
        return

    if gitdir is None and not wt.orphan:
        wt.verdict = "ERROR"
        wt.reasons.append(".git pointer unreadable or gitdir missing")
        return
    if wt.age_days is None and wt.orphan:
        # Orphans carry no git metadata; their only readable signals are the
        # weak file mtimes.  Use those for the recency courtesy — deletion is
        # separately gated behind include_orphans anyway.
        weak_ages = [v for k, v in wt.age_sources.items() if k.startswith("weak:")]
        wt.age_days = min(weak_ages) if weak_ages else None
    if wt.age_days is None:
        wt.verdict = "ERROR"
        wt.reasons.append("no readable strong activity signal (reflog entry / session dir)")
        return
    if wt.age_days < float(cfg["min_age_days"]):
        wt.verdict = "RECENT"
        wt.reasons.append(f"strong activity {wt.age_days:.1f}d < min_age {cfg['min_age_days']}d")
        return

    if wt.orphan:
        wt.verdict = "ORPHAN"
        wt.reasons.append("directory has no live worktree registration")
        return

    clean = status_clean(wt)
    if clean is None:
        wt.verdict = "ERROR"
        wt.reasons.append("git status failed")
        return
    if not clean:
        wt.verdict = "DIRTY"
        wt.reasons.append("uncommitted changes or untracked files")
        return

    if not wt.head:
        wt.verdict = "ERROR"
        wt.reasons.append("no HEAD recorded")
        return

    # Content proofs (any one suffices for SAFE_MERGED).
    rc, _, _ = _git(primary, "merge-base", "--is-ancestor", wt.head, "origin/main")
    if rc == 0:
        wt.verdict = "SAFE_MERGED"
        wt.proof = "ancestor-of-origin/main"
        return

    pr = (pr_states or {}).get(wt.branch or "")
    if pr and pr.get("state") == "MERGED" and pr.get("headRefOid") == wt.head:
        wt.verdict = "SAFE_MERGED"
        wt.proof = f"PR #{pr['number']} merged at this exact head"
        return

    if pr and pr.get("state") == "OPEN":
        wt.verdict = "OPEN_PR"
        wt.reasons.append(f"PR #{pr['number']} open")
        if not cfg.get("include_open_pr"):
            return
        # fall through only when the operator armed open-PR reclaim; the
        # pushed-to-remote proof below still has to hold.

    if wt.branch and remote_fresh:
        rc, out, _ = _git(primary, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{wt.branch}")
        if rc == 0:
            remote_sha = out.strip()
            rc2, _, _ = _git(primary, "merge-base", "--is-ancestor", wt.head, remote_sha)
            if rc2 == 0:
                if wt.verdict == "OPEN_PR":
                    wt.verdict = "SAFE_REMOTE"
                    wt.proof = "open-PR head pushed to origin (include_open_pr armed)"
                    return
                if pr_states is None:
                    wt.verdict = "UNPUSHED"
                    wt.reasons.append("pushed to origin but PR state unknown — fail closed")
                    return
                wt.verdict = "SAFE_REMOTE"
                wt.proof = f"HEAD contained in origin/{wt.branch}; no open PR"
                return

    if wt.verdict == "OPEN_PR":
        return
    wt.verdict = "UNPUSHED"
    why = "HEAD not on origin/main, no merged-PR proof"
    if not remote_fresh:
        why += " (remote refs stale — fetch failed)"
    if pr_states is None:
        why += " (PR states unavailable)"
    if pr and pr.get("state") == "MERGED":
        why += f" (PR #{pr['number']} merged but head moved past merged oid)"
    wt.reasons.append(why)


# ── orphan scan ──────────────────────────────────────────────────────────────

def scan_orphans(hosts: Path | list[Path], roots: list[Path],
                 registered: list[Worktree]) -> list[Worktree]:
    """Depth-1 entries under the in-repo roots not covered by any registration."""
    if isinstance(hosts, (str, Path)):
        hosts = [Path(hosts)]
    reg_paths = [w.path.resolve() for w in registered]
    out: list[Worktree] = []
    for root in roots:
        # Only scan roots inside the repo — under ANY host checkout, not just the
        # primary, or orphans beside a second checkout are never seen.
        if not any(_under(root, h) for h in hosts):
            continue
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            ep = Path(e.path).resolve()
            covered = any(rp == ep or _under(rp, ep) for rp in reg_paths)
            if not covered:
                o = Worktree(path=Path(e.path), orphan=True, root=str(root))
                out.append(o)
    return out


# ── apply (deletion) ─────────────────────────────────────────────────────────

def _ledger_write(row: dict) -> None:
    try:
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_DIR / "ledger.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as exc:
        log.warning("ledger write failed: %s", exc)


def apply_deletions(
    primary: Path,
    worktrees: list[Worktree],
    cfg: dict,
    roots: list[Path],
    dry_run: bool = False,
    hosts: list[Path] | None = None,
) -> dict:
    summary = {"deleted": [], "pruned": False, "branches_deleted": [], "errors": [], "skipped_cap": 0}
    policy = cfg.get("_storage_policy")
    if policy is not None:
        try:
            worktree_storage.check_storage(policy, check_space=False)
        except (worktree_storage.StorageError, OSError) as exc:
            summary["errors"].append(f"external storage unverified; deletion and prune refused: {exc}")
            return summary
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    host = socket.gethostname()

    eligible = [w for w in worktrees if w.verdict in SAFE_VERDICTS]
    if cfg.get("include_orphans"):
        eligible += [w for w in worktrees if w.verdict == "ORPHAN"]
    eligible.sort(key=lambda w: -(w.size_kb or 0))

    cap = int(cfg.get("max_delete_per_run", 200))
    if len(eligible) > cap:
        summary["skipped_cap"] = len(eligible) - cap
        eligible = eligible[:cap]

    for wt in eligible:
        # Final belt: target must sit strictly under a configured root and
        # must not be the primary checkout or the sweeper's own tree.
        if wt.path.resolve() == primary.resolve() or not any(_under(wt.path, r) for r in roots):
            summary["errors"].append(f"{wt.path}: refused — outside configured roots")
            continue
        # A host is a CHECKOUT, never a session tree. It cannot reach the belt
        # (no host sits under a root) — this is the belt behind the belt, because
        # the operator's designated local root is one of them and deleting it
        # destroys every sibling worktree at once.
        if any(wt.path.resolve() == Path(h).resolve() for h in (hosts or ())):
            summary["errors"].append(f"{wt.path}: refused — host checkout")
            continue
        if _under(Path.cwd(), wt.path):
            summary["errors"].append(f"{wt.path}: refused — sweeper cwd inside")
            continue
        if dry_run:
            log.info("[DRY-RUN] would remove %s (%s, %s)", wt.path.name, wt.verdict, wt.proof)
            summary["deleted"].append(str(wt.path))
            continue

        external = policy is not None and Path(policy["root"]) in wt.path.parents
        storage_unlocked = False
        if external:
            try:
                worktree_storage.check_storage(policy, wt.path, check_space=False)
            except (worktree_storage.StorageError, OSError) as exc:
                summary["errors"].append(f"{wt.path}: {exc}")
                continue
            # Never recurse over external grouping directories as if they were
            # individual orphan checkouts. Only registered Git worktrees qualify.
            if wt.orphan or wt.verdict == "ORPHAN":
                summary["errors"].append(f"{wt.path}: external orphan retained")
                continue
            rc, listing, err = _git(primary, "worktree", "list", "--porcelain")
            current = next((w for w in parse_worktree_list(listing) if w.path == wt.path), None)
            rc2, status, _ = _git(wt.path, "status", "--porcelain", "--untracked-files=all")
            procs = proc_cwd_map([wt.path])
            if (rc or rc2 or current is None or current.head != wt.head or status.strip()
                    or procs is None or any(ps for cwd, ps in procs.items() if _under(Path(cwd), wt.path))):
                summary["errors"].append(f"{wt.path}: external deletion revalidation failed")
                continue
            if current.locked:
                if current.lock_reason != worktree_storage.LOCK_REASON:
                    summary["errors"].append(f"{wt.path}: foreign lock retained")
                    continue
                rc, _, err = _git(primary, "worktree", "unlock", str(wt.path))
                if rc:
                    summary["errors"].append(f"{wt.path}: storage unlock failed: {err}")
                    continue
                storage_unlocked = True

        if wt.verdict == "ORPHAN":
            try:
                shutil.rmtree(wt.path)
                ok, err = True, ""
            except OSError as exc:
                ok, err = False, str(exc)
        else:
            remove_args = ("worktree", "remove", str(wt.path)) if external else ("worktree", "remove", "--force", str(wt.path))
            ok, err = False, ""
            try:
                rc, _, err = _git(primary, *remove_args, timeout=600)
                ok = rc == 0
            except (OSError, subprocess.SubprocessError) as exc:
                err = str(exc)
            finally:
                if not ok and storage_unlocked:
                    # The registration lives in the shared Git store. It needs
                    # its lock most when the external directory is unavailable.
                    rc, listing, relock_error = _git(primary, "worktree", "list", "--porcelain")
                    retained = next((w for w in parse_worktree_list(listing) if w.path == wt.path), None)
                    if rc:
                        err += f"; storage registration recheck failed: {relock_error}"
                    elif retained and not retained.locked:
                        relock_rc, _, relock_error = _git(primary, "worktree", "lock", "--reason", worktree_storage.LOCK_REASON, str(wt.path))
                        if relock_rc:
                            err += f"; storage relock failed: {relock_error}"

        _ledger_write({
            "ts": now_iso, "host": host, "path": str(wt.path), "branch": wt.branch,
            "head": wt.head, "size_kb": wt.size_kb, "verdict": wt.verdict,
            "proof": wt.proof, "ok": ok, "err": err.strip()[:300] if err else "",
        })
        if ok:
            summary["deleted"].append(str(wt.path))
            log.info("removed %s (%s; %s; %s kB)", wt.path.name, wt.verdict, wt.proof, wt.size_kb)
        else:
            summary["errors"].append(f"{wt.path}: {err.strip()[:200]}")
            if storage_unlocked:
                # Stop this sweep on a failed removable-volume transaction.
                # Do not prune after an uncertain removal/recovery boundary.
                return summary
            continue

        # Local branch cleanup — only when the merge proof held and the branch
        # tip still equals the head we just proved safe.
        if (
            cfg.get("delete_local_branches")
            and wt.verdict == "SAFE_MERGED"
            and wt.branch
        ):
            rc, out, _ = _git(primary, "rev-parse", "--verify", "--quiet", f"refs/heads/{wt.branch}")
            if rc == 0 and out.strip() == wt.head:
                rc2, _, err2 = _git(primary, "branch", "-D", wt.branch)
                if rc2 == 0:
                    summary["branches_deleted"].append(wt.branch)
                else:
                    log.info("branch -D %s refused: %s", wt.branch, err2.strip()[:120])

    if not dry_run:
        if policy is not None:
            try:
                worktree_storage.check_storage(policy, check_space=False)
            except (worktree_storage.StorageError, OSError) as exc:
                summary["errors"].append(f"prune refused: {exc}")
                return summary
        rc, _, err = _git(primary, "worktree", "prune", timeout=120)
        summary["pruned"] = rc == 0
        if rc != 0:
            summary["errors"].append(f"worktree prune: {err.strip()[:200]}")
    return summary


# ── report ───────────────────────────────────────────────────────────────────

def display_name(w: Worktree) -> str:
    """Root-relative path — codex-home trees all end in '<slug>/Macro Dashboard',
    so the bare dirname is ambiguous in reports."""
    if w.root:
        try:
            return str(w.path.resolve().relative_to(Path(w.root).resolve()))
        except (ValueError, OSError):
            pass
    return w.path.name


def summarize(worktrees: list[Worktree]) -> dict:
    by: dict[str, dict] = {}
    for w in worktrees:
        b = by.setdefault(w.verdict or "?", {"count": 0, "kb": 0})
        b["count"] += 1
        b["kb"] += w.size_kb or 0
    return by


def _gib(kb: int | None) -> str:
    return f"{(kb or 0) / 1024 / 1024:.1f}"


def render_markdown(worktrees: list[Worktree], cfg: dict, meta: dict) -> str:
    by = summarize(worktrees)
    lines = [
        f"# worktree GC report — {meta['host']} — {meta['ts']}",
        "",
        f"mode: **{meta['mode']}** · armed: **{cfg.get('armed')}** · min_age_days: {cfg['min_age_days']}"
        f" · fetch_ok: {meta['fetch_ok']} · proc_scan: {meta['proc_scan']} · pr_states: {meta['pr_states']}",
        "",
        "| verdict | count | GiB |",
        "|---|---:|---:|",
    ]
    for v in sorted(by, key=lambda k: -by[k]["kb"]):
        lines.append(f"| {v} | {by[v]['count']} | {_gib(by[v]['kb'])} |")
    safe_kb = sum(by.get(v, {}).get("kb", 0) for v in SAFE_VERDICTS)
    orphan_kb = by.get("ORPHAN", {}).get("kb", 0)
    lines += [
        "",
        f"**Reclaimable now (SAFE_MERGED + SAFE_REMOTE): {_gib(safe_kb)} GiB "
        f"across {sum(by.get(v, {}).get('count', 0) for v in SAFE_VERDICTS)} worktrees.**",
        f"ORPHAN (needs include_orphans ratification): {_gib(orphan_kb)} GiB.",
        "",
        "## Largest kept worktrees",
        "",
        "| worktree | verdict | GiB | age d | detail |",
        "|---|---|---:|---:|---|",
    ]
    kept = [w for w in worktrees if w.verdict in KEEP_VERDICTS and w.verdict not in ("PRIMARY", "SELF")]
    for w in sorted(kept, key=lambda w: -(w.size_kb or 0))[:15]:
        detail = "; ".join(w.reasons[:2]) or w.proof
        if w.procs:
            detail += f" [{', '.join(w.procs[:3])}]"
        age = f"{w.age_days:.0f}" if w.age_days is not None else "?"
        lines.append(f"| {display_name(w)} | {w.verdict} | {_gib(w.size_kb)} | {age} | {detail[:100]} |")
    lines += ["", "## Sample of safe deletions", ""]
    for w in [w for w in worktrees if w.verdict in SAFE_VERDICTS][:20]:
        lines.append(f"- `{display_name(w)}` {_gib(w.size_kb)} GiB — {w.proof} (branch {w.branch or '—'})")
    return "\n".join(lines) + "\n"


# ── main ─────────────────────────────────────────────────────────────────────

def load_config(primary: Path, override: str | None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = Path(override) if override else primary / DEFAULT_CONFIG_REL
    try:
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        log.info("no config at %s — using built-in defaults (disarmed)", path)
    except (OSError, ValueError) as exc:
        # An unreadable config must not un-arm into a broken apply run.
        raise SystemExit(f"config unreadable: {path}: {exc}")
    policy = worktree_storage.load_policy()
    if policy is not None:
        cfg["_storage_policy"] = policy
        cfg["roots"] = list(cfg["roots"]) + [str(Path(policy["root"]) / client) for client in ("claude", "codex", "manual")]
    return cfg


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Fleet session-worktree GC (report-first)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="classify + report only (default)")
    mode.add_argument("--apply", action="store_true", help="delete SAFE worktrees (requires armed config)")
    ap.add_argument("--dry-run", action="store_true", help="with --apply: log actions without deleting")
    ap.add_argument("--repo-root", default=None, help="primary checkout (default: resolve from cwd)")
    ap.add_argument("--config", default=None, help=f"config path (default: <repo>/{DEFAULT_CONFIG_REL})")
    ap.add_argument("--min-age-days", type=float, default=None, help="override config min_age_days")
    ap.add_argument("--pr-limit", type=int, default=None, help="gh pr list page depth per state")
    ap.add_argument("--pr-states-file", default=None, help="use this JSON map instead of gh")
    ap.add_argument("--emit-pr-states", default=None, help="write the fetched PR-state map here")
    ap.add_argument("--no-fetch", action="store_true", help="skip git fetch --prune")
    ap.add_argument("--no-gh", action="store_true", help="skip gh PR-state fetch")
    ap.add_argument("--no-sizes", action="store_true", help="skip du sizing")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)

    primary = Path(args.repo_root).resolve() if args.repo_root else resolve_primary_root()
    cfg = load_config(primary, args.config)
    if args.min_age_days is not None:
        cfg["min_age_days"] = args.min_age_days
    if args.pr_limit is not None:
        cfg["pr_limit"] = args.pr_limit
    do_apply = bool(args.apply)

    now = time.time()

    # The registration list comes FIRST: the hosts that relative roots expand
    # under are themselves registrations of this clone.
    rc, out, err = _git(primary, "worktree", "list", "--porcelain", timeout=60)
    if rc != 0:
        raise SystemExit(f"git worktree list failed: {err.strip()}")
    registered = parse_worktree_list(out)

    rel_roots = [r for r in cfg["roots"]
                 if not r.startswith("~") and not os.path.isabs(r)]
    hosts = host_checkouts(primary, registered, rel_roots)
    roots = expand_roots(hosts, list(cfg["roots"]))

    in_scope: list[Worktree] = []
    for w in registered:
        for r in roots:
            if _under(w.path, r):
                w.root = str(r)
                in_scope.append(w)
                break
    # External roots contain app/repository grouping directories; the Git
    # registry is authoritative there, not a depth-one orphan directory scan.
    policy = cfg.get("_storage_policy")
    orphan_roots = [r for r in roots if policy is None or not _under(r, Path(policy["root"]))]
    orphans = scan_orphans(hosts, orphan_roots, registered)

    fetch_ok = False if args.no_fetch else fetch_origin(primary)
    pr_states: dict[str, dict] | None = None
    if args.pr_states_file:
        pr_states = load_pr_states(Path(args.pr_states_file))
    elif not args.no_gh:
        pr_states = gh_pr_states(primary, int(cfg["pr_limit"]))
    if args.emit_pr_states and pr_states is not None:
        Path(args.emit_pr_states).write_text(json.dumps(pr_states, indent=1), encoding="utf-8")

    procs = proc_cwd_map(roots)
    self_cwd = Path.cwd()

    candidates = in_scope + orphans
    for w in candidates:
        classify(w, primary, cfg, procs, pr_states, fetch_ok, self_cwd, now)
        if not args.no_sizes and w.path.exists() and w.verdict not in ("PRIMARY", "SELF"):
            w.size_kb = du_kb(w.path)

    meta = {
        "host": socket.gethostname(),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "apply" if do_apply else "report",
        "fetch_ok": fetch_ok,
        "proc_scan": procs is not None,
        "pr_states": "file" if args.pr_states_file else ("none" if pr_states is None else f"gh:{len(pr_states)}"),
        "primary": str(primary),
        "registered_total": len(registered),
        "in_scope": len(in_scope),
        "orphans": len(orphans),
    }

    apply_summary = None
    refused = None
    if do_apply:
        if not cfg.get("armed"):
            refused = (f"apply refused: config {args.config or DEFAULT_CONFIG_REL} is not armed "
                       "(armed:false). Operator ratification required — see "
                       "research/WORKTREE_GC_POLICY.md")
        elif procs is None:
            refused = "apply refused: process scan unavailable — cannot prove liveness"
        if refused:
            log.error(refused)
        else:
            apply_summary = apply_deletions(primary, candidates, cfg, roots,
                                            dry_run=args.dry_run, hosts=hosts)

    payload = {
        "meta": meta,
        "summary": summarize(candidates),
        "apply": apply_summary,
        "worktrees": [
            {
                "path": str(w.path), "name": display_name(w), "branch": w.branch,
                "head": w.head, "verdict": w.verdict, "proof": w.proof,
                "reasons": w.reasons, "size_kb": w.size_kb,
                "age_days": round(w.age_days, 2) if w.age_days is not None else None,
                "age_sources": w.age_sources,
                "procs": w.procs, "root": w.root, "orphan": w.orphan,
            }
            for w in candidates
        ],
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    md = render_markdown(candidates, cfg, meta)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    print(md)
    if refused:
        print(refused)
        return 2
    if apply_summary is not None:
        print(f"apply: deleted={len(apply_summary['deleted'])} "
              f"branches={len(apply_summary['branches_deleted'])} "
              f"errors={len(apply_summary['errors'])} over_cap={apply_summary['skipped_cap']}")
        if apply_summary["errors"]:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
