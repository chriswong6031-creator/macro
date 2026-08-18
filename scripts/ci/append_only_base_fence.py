"""Refuse to publish an append-only artifact computed over a base that has moved.

WHY THIS EXISTS (2026-08-18, DSC-OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS)
--------------------------------------------------------------------------------------
Every lane here publishes with ``git pull --rebase --autostash -X theirs origin main``.
That strategy is right for the bulk market plane -- a freshly collected store should beat
a stale one on any conflicting hunk -- and it is CATASTROPHIC for an append-only ledger,
because "prefer ours" on a file both sides appended to REPLACES the other side's rows
instead of unioning them.

Measured twice on ``data/government_revenue/``:

  * 2026-08-07  1fc6d1181e4c -> 08ad4d836d6a  ``collection_receipts.jsonl`` 720 -> 720
    lines with 360 receipt ids dropped and 360 substituted -- the two halves swapped
    wholesale, same byte count, no growth.
  * 2026-08-18  59ccb9c774c8 -> 93ab221b81dd  the EDT cron run's collect job
    (01:07:12Z->04:08:26Z, committed 04:01:49Z) and a workflow_dispatch run's collect job
    (01:27:00Z->04:28:57Z, committed 04:21:53Z) overlapped. Run B had checked out ~2.5h
    before run A's commit existed. Its push dropped 376 receipts and re-stamped run A's
    16 newly appended ``award_event_snapshots.parquet`` rows -- identical
    ``event_state_sha256``, run B's ``known_at`` -- which moved ``_event_id``, therefore
    ``candidate_id``, therefore orphaned a 26-row ``candidate_ledger.jsonl`` issuance
    batch and redded ci-pack-6 through ci-gate for every armed PR in the fleet.

The overlap is BY DESIGN and must not be "fixed" by merging concurrency groups:
``.github/workflows/daily.yml`` gives each DST cron and each manual dispatch its own
group precisely so the DST pair cannot cancel each other's slot (the 2026-08-14/15 kill).
The fix belongs at the artifact layer.

WHY THE EXISTING WRITE-PATH GUARDS CANNOT SEE THIS
---------------------------------------------------
``collectors/usaspending_awards.py`` is careful and all of it is scoped to one process's
disk: the torn-generation refusal (:3956-3972) compares the on-disk state binding to the
on-disk ledgers, and the staged-replay check (:4030-4044) proves the bytes a reader will
load reproduce the generation this run computed. A run whose entire base is stale is
PERFECTLY SELF-CONSISTENT and passes both. Nothing asked whether ``origin/main`` moved
under the artifact between checkout and push. This does.

WHAT IT CHECKS
--------------
For each family in ``config/append_only_artifacts.json``, and only for members THIS run's
local commits actually changed (``<onto>..HEAD``):

  * ``jsonl_prefix`` -- ``origin/main``'s bytes must be a prefix of the bytes about to be
    pushed. This is the contract the repo already asserts for ``collection_receipts.jsonl``
    (tests/test_usaspending_awards.py) and enforces byte-exactly for
    ``candidate_ledger.jsonl`` via its ``prior_sha256`` state receipt.
  * ``parquet_rows`` -- every identity tuple on ``origin/main`` must still be present.
    Order-independent: parquet re-encodes, so a positional prefix is not a contract the
    writers promise, while "no published row disappears" is.

Scoping to CHANGED members is load-bearing, not an optimization. A member this run did
not touch cannot be clobbered by the rebase -- ``-X theirs`` only resolves conflicting
hunks -- and flagging it would fire on every ordinary night, because the 30-minute
``government-revenue-live`` lane appends ``candidate_ledger.jsonl`` rows while the
nightly collect job is still running.

WHAT IT DOES ON A VIOLATION
---------------------------
It WITHHOLDS the family: every path in ``withhold_paths`` is restored from ``origin/main``
and committed, so the rebase has nothing to resolve and main's coherent generation
survives. The run's own rows are dropped, deliberately -- the collector re-fetches an
1826-day window every night, so a withheld generation costs one cycle, while a published
lost-update costs evidence permanently and is not repairable by a session.

The withhold is the WHOLE family, never one file: reverting individual artifacts leaves
the generation entangled (measured -- reverting ``award_event_snapshots.parquet`` alone,
then + the projection state, then + the receipts, then all 25 changed artifacts, each
rebuilt to a different broken shape).

FAILURE DIRECTIONS, ON PURPOSE
------------------------------
  * A member we changed that cannot be READ or whose identity columns are absent is
    ``indeterminate`` and withholds. We changed a file we cannot prove extends main.
  * An INFRASTRUCTURE fault -- ``git rev-list`` failing, so the changed-set is unknown --
    does NOT withhold. Without the changed-set a withhold could destroy a legitimate
    generation, and declining to act merely leaves the pre-fence behaviour in place. It
    prints ``::error`` and exits 0, so the fault is visible in the run summary.
  * The fence never fails the step. The market plane must publish; the annotation is the
    signal. Exit status is 0 unless ``--check-only`` was asked for.

The fence does NOT inherit the 2026-08-18 corruption. It compares this run's build against
``origin/main``; it never walks history. (For the record, PR #5870 restored run A's
generation, so ``origin/main``'s ``collection_receipts.jsonl`` is byte-identical to
59ccb9c774c8 again -- but nothing here depends on that.)
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

REGISTRY_PATH = "config/append_only_artifacts.json"

OK = "ok"
STALE_BASE = "stale_base"
INDETERMINATE = "indeterminate"

# A publishing lane owns one or two commits. Anything past this is a truncated or
# unexpected graph, not a lane -- see changed_paths().
MAX_LOCAL_COMMITS = 25

# Sample size for the annotation. A withhold that names nothing is a withhold nobody
# can triage at 3am; a withhold that dumps 376 identities is one nobody reads.
_SAMPLE = 3


class FenceError(RuntimeError):
    """The fence could not establish what this run changed."""


@dataclass(frozen=True)
class Member:
    path: str
    check: str
    identity: tuple[str, ...] = ()


@dataclass(frozen=True)
class Family:
    key: str
    withhold_paths: tuple[str, ...]
    members: tuple[Member, ...]
    why: str = ""


@dataclass
class MemberVerdict:
    member: Member
    status: str
    detail: str = ""
    lost: tuple[str, ...] = ()


@dataclass
class FamilyVerdict:
    family: Family
    members: list[MemberVerdict] = field(default_factory=list)

    @property
    def violated(self) -> bool:
        return any(row.status != OK for row in self.members)

    @property
    def offenders(self) -> list[MemberVerdict]:
        return [row for row in self.members if row.status != OK]


# ── registry ───────────────────────────────────────────────────────────────────
def load_registry(path: Path) -> list[Family]:
    payload = json.loads(path.read_text())
    families: list[Family] = []
    for raw in payload.get("families", []):
        members = tuple(
            Member(
                path=str(entry["path"]),
                check=str(entry["check"]),
                identity=tuple(str(column) for column in entry.get("identity", ())),
            )
            for entry in raw.get("members", [])
        )
        for member in members:
            if member.check not in ("jsonl_prefix", "parquet_rows"):
                raise ValueError(f"unknown append-only check kind: {member.check}")
            if member.check == "parquet_rows" and not member.identity:
                raise ValueError(f"parquet_rows member declares no identity: {member.path}")
        families.append(
            Family(
                key=str(raw["key"]),
                withhold_paths=tuple(str(item) for item in raw.get("withhold_paths", ())),
                members=members,
                why=str(raw.get("why", "")),
            )
        )
    return families


# ── git plumbing ───────────────────────────────────────────────────────────────
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, check=False
    )


def _git_text(repo: Path, *args: str) -> str:
    done = _git(repo, *args)
    if done.returncode != 0:
        raise FenceError(
            f"git {' '.join(args)} failed ({done.returncode}): "
            f"{done.stderr.decode(errors='replace').strip()[:200]}"
        )
    return done.stdout.decode(errors="replace")


def blob_at(repo: Path, rev: str, path: str) -> bytes | None:
    """Bytes of ``path`` at ``rev``, or None when the tree does not carry it."""
    done = _git(repo, "cat-file", "blob", f"{rev}:{path}")
    if done.returncode != 0:
        return None
    return done.stdout


def changed_paths(repo: Path, onto: str, head: str) -> set[str]:
    """Paths the commits in ``<onto>..<head>`` change, unioned over those commits.

    Deliberately NOT ``git diff <onto>...<head>``: three-dot needs a merge-base, and
    ``actions/checkout`` clones at depth 1, so the merge-base may not exist on the
    runner at all. ``rev-list`` plus per-commit ``diff-tree`` needs neither.

    A range longer than ``MAX_LOCAL_COMMITS`` is not a lane's local work -- it means the
    graph is truncated or ``onto`` is not where we think it is, and the walk would return
    a SUPERSET of what this run changed, which is the one error that can make the fence
    withhold a legitimate generation. Refuse to answer instead.
    """
    revs = _git_text(repo, "rev-list", f"{onto}..{head}").split()
    if len(revs) > MAX_LOCAL_COMMITS:
        raise FenceError(
            f"{onto}..{head} spans {len(revs)} commits (> {MAX_LOCAL_COMMITS}); the "
            f"changed set would be a superset of this run's own work"
        )
    touched: set[str] = set()
    for rev in revs:
        out = _git_text(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", rev
        )
        touched.update(line for line in out.splitlines() if line.strip())
    return touched


# ── checks ─────────────────────────────────────────────────────────────────────
def jsonl_prefix_verdict(member: Member, base: bytes | None, head: bytes | None) -> MemberVerdict:
    if base is None:
        # Nothing on main to lose. A first publish is an extension of the empty file.
        return MemberVerdict(member, OK, "absent on the base")
    if head is None:
        return MemberVerdict(
            member, STALE_BASE, f"present on the base ({len(base)} bytes) and absent here"
        )
    if head.startswith(base):
        return MemberVerdict(member, OK, f"{len(base)} -> {len(head)} bytes")
    lost = _lost_jsonl_lines(base, head)
    return MemberVerdict(
        member,
        STALE_BASE,
        f"base is not a prefix: {len(base)} bytes on the base, {len(head)} here, "
        f"{len(lost)} base line(s) dropped",
        lost=tuple(lost[:_SAMPLE]),
    )


# Row-identity fields, in preference order, for naming a dropped JSONL line in an
# annotation. A full receipt body is ~300 characters of URL and hashes; three of them
# make the annotation unreadable at 3am, which is the only time anyone reads it.
_JSONL_LABEL_FIELDS = ("receipt_id", "candidate_id", "id")


def _lost_jsonl_lines(base: bytes, head: bytes) -> list[str]:
    head_lines = {line for line in head.split(b"\n") if line.strip()}
    return [
        _jsonl_label(line)
        for line in base.split(b"\n")
        if line.strip() and line not in head_lines
    ]


def _jsonl_label(line: bytes) -> str:
    try:
        row = json.loads(line)
    except Exception:  # noqa: BLE001 - a label is never worth raising over
        row = None
    if isinstance(row, dict):
        for field in _JSONL_LABEL_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and value:
                return value
    return line.decode(errors="replace")[:80]


def parquet_rows_verdict(member: Member, base: bytes | None, head: bytes | None) -> MemberVerdict:
    if base is None:
        return MemberVerdict(member, OK, "absent on the base")
    if head is None:
        return MemberVerdict(member, STALE_BASE, "present on the base and absent here")
    try:
        base_ids = _identity_set(base, member.identity)
        head_ids = _identity_set(head, member.identity)
    except Exception as exc:  # noqa: BLE001 - an unreadable ledger we changed withholds
        return MemberVerdict(member, INDETERMINATE, f"unreadable: {type(exc).__name__}: {exc}"[:200])
    lost = sorted(base_ids - head_ids)
    if not lost:
        return MemberVerdict(member, OK, f"{len(base_ids)} -> {len(head_ids)} identities")
    return MemberVerdict(
        member,
        STALE_BASE,
        f"{len(lost)} of {len(base_ids)} base identities dropped "
        f"({len(base_ids)} -> {len(head_ids)})",
        lost=tuple(lost[:_SAMPLE]),
    )


def _identity_set(blob: bytes, identity: tuple[str, ...]) -> set[str]:
    import pandas as pd  # local: keeps a jsonl-only run off the pandas import cost

    frame = pd.read_parquet(io.BytesIO(blob))
    missing = [column for column in identity if column not in frame.columns]
    if missing:
        raise KeyError(f"identity column(s) absent: {', '.join(missing)}")
    if frame.empty:
        return set()
    # " | " rather than a control character: these tuples are printed into GitHub
    # annotations, and \x1f renders as nothing at all.
    return {
        " | ".join(values)
        for values in frame[list(identity)].astype("string").fillna("").itertuples(
            index=False, name=None
        )
    }


_CHECKS = {"jsonl_prefix": jsonl_prefix_verdict, "parquet_rows": parquet_rows_verdict}


def evaluate_family(
    repo: Path, family: Family, onto: str, head: str, touched: set[str]
) -> FamilyVerdict:
    verdict = FamilyVerdict(family=family)
    for member in family.members:
        if member.path not in touched:
            continue
        verdict.members.append(
            _CHECKS[member.check](
                member, blob_at(repo, onto, member.path), blob_at(repo, head, member.path)
            )
        )
    return verdict


# ── remedy ─────────────────────────────────────────────────────────────────────
def withhold_family(repo: Path, family: Family, onto: str, *, amend: bool) -> bool:
    """Restore every coherence path from ``onto`` and commit. True when a commit landed."""
    for root in family.withhold_paths:
        on_base = _git_text(repo, "ls-tree", "-r", "--name-only", onto, "--", root).split("\n")
        on_base = [line for line in on_base if line.strip()]
        if on_base:
            _git_text(repo, "checkout", onto, "--", root)
        indexed = [
            line
            for line in _git_text(repo, "ls-files", "--", root).split("\n")
            if line.strip()
        ]
        extra = sorted(set(indexed) - set(on_base))
        if extra:
            _git_text(repo, "rm", "-q", "--cached", "--ignore-unmatch", "--", *extra)
    if _git(repo, "diff", "--cached", "--quiet").returncode == 0:
        return False
    message = (
        f"govrev: withhold {family.key} append-only generation (base moved under this run)"
        if family.key == "government-revenue"
        else f"data: withhold {family.key} append-only generation (base moved under this run)"
    )
    if amend:
        _git_text(repo, "commit", "--amend", "--no-edit", "--no-verify", "--allow-empty")
    else:
        _git_text(repo, "commit", "--no-verify", "-m", message)
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────
def _announce(level: str, message: str) -> None:
    # Bare line-start print, never a logger: a prefixing formatter pushes "::" off
    # column 0 and GitHub drops the annotation (tests/test_gh_annotation_line_start.py).
    print(f"::{level} title=append-only-base-fence::{message}", flush=True)


def run(
    repo: Path,
    *,
    onto: str,
    head: str,
    registry: Path,
    restore: bool,
    amend: bool,
) -> int:
    families = load_registry(registry)
    try:
        touched = changed_paths(repo, onto, head)
    except FenceError as exc:
        _announce(
            "error",
            f"could not determine what {head} changed against {onto} ({exc}) — NOT "
            f"withholding, because a withhold without the changed set can discard a "
            f"legitimate generation; the push proceeds with pre-fence behaviour",
        )
        return 0
    if not touched:
        print("append-only-base-fence: nothing to publish", flush=True)
        return 0

    violations = 0
    checked = 0
    for family in families:
        verdict = evaluate_family(repo, family, onto, head, touched)
        if not verdict.members:
            continue
        checked += len(verdict.members)
        if not verdict.violated:
            print(
                f"append-only-base-fence: {family.key} ok "
                f"({len(verdict.members)} member(s) checked against {onto})",
                flush=True,
            )
            continue
        violations += 1
        for row in verdict.offenders:
            sample = f" e.g. {', '.join(row.lost)}" if row.lost else ""
            _announce(
                "error",
                f"{family.key}: {row.member.path} would drop rows {onto} already carries "
                f"— {row.detail}{sample}",
            )
        if not restore:
            continue
        try:
            committed = withhold_family(repo, family, onto, amend=amend)
        except FenceError as exc:
            _announce("error", f"{family.key}: WITHHOLD FAILED ({exc}) — refusing to push it")
            return 1
        _announce(
            "error",
            f"{family.key}: WITHHELD this run's generation and restored "
            f"{', '.join(family.withhold_paths)} from {onto}"
            + ("" if committed else " (already identical — no commit needed)")
            + ". This run's rows are dropped on purpose; the next collection re-derives "
            "them. Overlapping runs are the cause — preflight `gh run list --workflow "
            "daily.yml --json status` before dispatching.",
        )
    if not checked:
        # Say so out loud. A fence that prints nothing is indistinguishable from a
        # fence that never ran, and this one is silent on almost every push.
        print(
            "append-only-base-fence: no registered append-only artifact in this push",
            flush=True,
        )
    return 1 if (violations and not restore) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository root (default: cwd)")
    parser.add_argument("--onto", default="origin/main", help="the ref being pushed onto")
    parser.add_argument("--head", default="HEAD", help="the commit being pushed")
    parser.add_argument("--registry", default=None, help=f"default: {REGISTRY_PATH}")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report and exit non-zero on a violation; never touch the tree",
    )
    parser.add_argument(
        "--amend",
        action="store_true",
        help="fold the withhold into HEAD instead of adding a commit (lanes that amend)",
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.registry:
        registry = Path(args.registry)
    else:
        registry = repo / REGISTRY_PATH
        if not registry.exists():
            # A lane may run the fence from a worktree that does not carry the registry;
            # the copy beside this file is the one CI ships.
            registry = _ROOT / REGISTRY_PATH
    return run(
        repo,
        onto=args.onto,
        head=args.head,
        registry=registry,
        restore=not args.check_only,
        amend=args.amend,
    )


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
