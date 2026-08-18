"""The base-freshness fence for append-only evidence artifacts.

Reproduces the measured 2026-08-18 lost update end to end (two overlapping collect
jobs, the later one pushing over a base that moved) and pins the properties that keep
the fence from firing on an ordinary night.

See scripts/ci/append_only_base_fence.py and
agentos/discoveries/DSC-OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS.md.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ci import append_only_base_fence as fence  # noqa: E402

REGISTRY = ROOT / "config" / "append_only_artifacts.json"
RECEIPTS = "data/government_revenue/collection_receipts.jsonl"
EVENTS = "data/government_revenue/award_event_snapshots.parquet"
LEDGER = "data/government_revenue/candidate_ledger.jsonl"


# ── fixtures ───────────────────────────────────────────────────────────────────
def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, check=True
    )
    return done.stdout.decode()


def _receipt_lines(run_id: str, count: int, start: int = 0) -> bytes:
    return b"".join(
        json.dumps(
            {"receipt_id": f"{run_id}-{index:04d}", "response_sha256": f"{index:064x}"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for index in range(start, start + count)
    )


def _event_frame(rows: list[tuple[str, str, str]]) -> bytes:
    frame = pd.DataFrame(
        rows, columns=["award_key", "known_at", "event_state_sha256"]
    ).assign(source_receipt_id="r")
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _write(repo: Path, path: str, payload: bytes) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


@pytest.fixture
def lane(tmp_path: Path) -> dict:
    """A repo whose `origin/main` carries run A's push and whose HEAD is run B's commit.

    Exactly the measured shape: both runs checked out `base`, both appended their own
    rows to the same append-only artifacts, run A pushed first.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(origin)], check=True)

    runner = tmp_path / "runner"
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(runner)], check=True)
    _git(runner, "config", "user.email", "bot@example.invalid")
    _git(runner, "config", "user.name", "dashboard-bot")
    _git(runner, "remote", "add", "origin", str(origin))

    base_receipts = _receipt_lines("base", 4)
    base_events = _event_frame([("A1", "2026-08-14T00:00:00Z", "aa")])
    _write(runner, RECEIPTS, base_receipts)
    _write(runner, EVENTS, base_events)
    _write(runner, LEDGER, b'{"candidate_id":"grc1-base"}\n')
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "base: 2026-08-14 collection")
    _git(runner, "push", "--quiet", "origin", "main")
    base = _git(runner, "rev-parse", "HEAD").strip()

    # Run A: appends its rows on top of the shared base and lands on origin/main first.
    a_receipts = base_receipts + _receipt_lines("runA", 3)
    a_events = _event_frame(
        [("A1", "2026-08-14T00:00:00Z", "aa"), ("A2", "2026-08-18T01:37:55Z", "bb")]
    )
    _write(runner, RECEIPTS, a_receipts)
    _write(runner, EVENTS, a_events)
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "data: daily collection 2026-08-18 (run A)")
    _git(runner, "push", "--quiet", "origin", "main")

    # Run B's workspace: still standing on `base`, with its own rows committed.
    _git(runner, "reset", "--hard", "--quiet", base)
    b_receipts = base_receipts + _receipt_lines("runB", 3)
    b_events = _event_frame(
        [("A1", "2026-08-14T00:00:00Z", "aa"), ("A2", "2026-08-18T01:55:22Z", "bb")]
    )
    _write(runner, RECEIPTS, b_receipts)
    _write(runner, EVENTS, b_events)
    _git(runner, "add", "-A")
    _git(runner, "commit", "--quiet", "-m", "data: daily collection 2026-08-18 (run B)")
    _git(runner, "fetch", "--quiet", "origin", "main")
    return {
        "repo": runner,
        "base": base,
        "a_receipts": a_receipts,
        "a_events": a_events,
        "b_receipts": b_receipts,
    }


def _run(repo: Path, **kwargs) -> int:
    defaults = dict(onto="origin/main", head="HEAD", registry=REGISTRY, restore=True, amend=False)
    defaults.update(kwargs)
    return fence.run(repo, **defaults)


# ── the measured incident ──────────────────────────────────────────────────────
def test_unfenced_rebase_reproduces_the_measured_lost_update(lane):
    """`-X theirs` on a file both runs appended to REPLACES, it does not union."""
    repo = lane["repo"]
    subprocess.run(
        ["git", "pull", "--rebase", "--autostash", "-X", "theirs", "origin", "main"],
        cwd=str(repo),
        capture_output=True,
        check=True,
    )
    published = (repo / RECEIPTS).read_bytes()
    assert not published.startswith(lane["a_receipts"]), "expected run A's rows to survive"
    assert b"runA-0000" not in published
    assert b"runB-0000" in published

    events = pd.read_parquet(repo / EVENTS)
    assert "2026-08-18T01:37:55Z" not in set(events["known_at"])
    assert "2026-08-18T01:55:22Z" in set(events["known_at"])


def test_fence_withholds_the_stale_base_generation_and_run_a_survives(lane, capsys):
    repo = lane["repo"]
    assert _run(repo) == 0

    out = capsys.readouterr().out
    assert "::error title=append-only-base-fence::" in out
    assert "WITHHELD" in out
    assert RECEIPTS in out

    # The withhold is committed, so the rebase has nothing left to resolve.
    subprocess.run(
        ["git", "pull", "--rebase", "--autostash", "-X", "theirs", "origin", "main"],
        cwd=str(repo),
        capture_output=True,
        check=True,
    )
    published = (repo / RECEIPTS).read_bytes()
    assert published == lane["a_receipts"]
    assert b"runB-0000" not in published

    events = pd.read_parquet(repo / EVENTS)
    assert set(events["known_at"]) == {"2026-08-14T00:00:00Z", "2026-08-18T01:37:55Z"}


def test_fence_withholds_every_annotation_line_at_column_zero(lane, capsys):
    _run(lane["repo"])
    for line in capsys.readouterr().out.splitlines():
        if "append-only-base-fence" in line and "::" in line:
            assert line.startswith("::"), line


def test_check_only_reports_without_touching_the_tree(lane, capsys):
    repo = lane["repo"]
    before = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo, restore=False) == 1
    assert _git(repo, "rev-parse", "HEAD").strip() == before
    assert (repo / RECEIPTS).read_bytes() == lane["b_receipts"]
    assert "::error title=append-only-base-fence::" in capsys.readouterr().out


# ── the properties that keep it quiet on an ordinary night ─────────────────────
def test_ordinary_extension_passes(lane, capsys):
    """Run B rebuilt on run A's base: its artifacts extend main, nothing is withheld."""
    repo = lane["repo"]
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    _write(repo, RECEIPTS, lane["a_receipts"] + _receipt_lines("runB", 3))
    _write(
        repo,
        EVENTS,
        _event_frame(
            [
                ("A1", "2026-08-14T00:00:00Z", "aa"),
                ("A2", "2026-08-18T01:37:55Z", "bb"),
                ("A3", "2026-08-18T01:55:22Z", "cc"),
            ]
        ),
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "data: daily collection (clean base)")
    head = _git(repo, "rev-parse", "HEAD").strip()

    assert _run(repo) == 0
    assert _git(repo, "rev-parse", "HEAD").strip() == head, "a clean run must not be touched"
    assert "government-revenue ok" in capsys.readouterr().out


def test_a_member_this_run_did_not_touch_is_never_flagged(lane, capsys):
    """The 30-minute govrev-live lane appends candidate_ledger.jsonl mid-nightly.

    The nightly collect job does not write that file, so its commit cannot clobber it —
    and flagging it would withhold the night's whole collection every single night.
    """
    repo = lane["repo"]
    # main gains ledger rows the runner has never seen; the runner's own commit is clean.
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    _write(repo, LEDGER, b'{"candidate_id":"grc1-base"}\n{"candidate_id":"grc1-live"}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "govrev: live candidate issuance")
    _git(repo, "push", "--quiet", "origin", "main")
    _git(repo, "reset", "--hard", "--quiet", "HEAD~1")

    _write(repo, RECEIPTS, lane["a_receipts"] + _receipt_lines("runB", 3))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "data: daily collection (ledger untouched)")
    _git(repo, "fetch", "--quiet", "origin", "main")
    head = _git(repo, "rev-parse", "HEAD").strip()

    assert _run(repo) == 0
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    out = capsys.readouterr().out
    assert "WITHHELD" not in out
    assert LEDGER not in out


def test_nothing_to_publish_is_a_no_op(lane, capsys):
    repo = lane["repo"]
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    assert _run(repo) == 0
    assert "nothing to publish" in capsys.readouterr().out


def test_first_publish_of_a_new_artifact_is_an_extension(lane, capsys):
    repo = lane["repo"]
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    _write(repo, "data/government_revenue/sbir_collection_receipts.jsonl", _receipt_lines("sbir", 2))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "data: first sbir receipts")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo) == 0
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    assert "WITHHELD" not in capsys.readouterr().out


def test_deleting_an_artifact_main_still_carries_is_withheld(lane, capsys):
    repo = lane["repo"]
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    _git(repo, "rm", "--quiet", RECEIPTS)
    _git(repo, "commit", "--quiet", "-m", "data: drop the receipt ledger")
    assert _run(repo) == 0
    assert (repo / RECEIPTS).read_bytes() == lane["a_receipts"]
    assert "WITHHELD" in capsys.readouterr().out


def test_withhold_removes_files_the_base_does_not_carry(lane, capsys):
    """A withheld generation must not leave its own new files behind, tracked."""
    repo = lane["repo"]
    _write(repo, "data/government_revenue/runB_only.jsonl", b'{"receipt_id":"x"}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "--amend", "--no-edit")

    assert _run(repo) == 0
    tracked = _git(repo, "ls-files", "--", "data/government_revenue").split()
    assert "data/government_revenue/runB_only.jsonl" not in tracked
    assert RECEIPTS in tracked


def test_withhold_never_sweeps_unrelated_dirty_files(lane, capsys):
    """The collect job pushes with capital-structure paths DIRTY, parked by --autostash.

    The withhold commits the index, so a tracked file dirty at that moment must stay
    dirty and OUT of the commit — sweeping it would publish a tree no compiler accepted
    (the #4600 carve-out this lane exists to preserve).
    """
    repo = lane["repo"]
    _write(repo, "data/capital_structure/source_manifest.jsonl", b'{"row":"unaccepted"}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "--amend", "--no-edit")
    (repo / "data/capital_structure/source_manifest.jsonl").write_bytes(b'{"row":"tonight"}\n')

    assert _run(repo) == 0
    assert "WITHHELD" in capsys.readouterr().out
    committed = _git(repo, "show", "HEAD:data/capital_structure/source_manifest.jsonl")
    assert committed == '{"row":"unaccepted"}\n', "the dirty edit must not have been swept in"
    assert "data/capital_structure/source_manifest.jsonl" in _git(
        repo, "diff", "--name-only"
    ), "the dirty edit must still be dirty, for --autostash to park"


def test_amend_folds_the_withhold_into_head(lane):
    repo = lane["repo"]
    before = _git(repo, "rev-list", "--count", "origin/main..HEAD").strip()
    assert _run(repo, amend=True) == 0
    assert _git(repo, "rev-list", "--count", "origin/main..HEAD").strip() == before


def test_an_over_long_local_range_refuses_to_answer(lane, capsys, monkeypatch):
    """A truncated graph makes the changed set a SUPERSET — never withhold on that."""
    monkeypatch.setattr(fence, "MAX_LOCAL_COMMITS", 0)
    repo = lane["repo"]
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo) == 0
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    out = capsys.readouterr().out
    assert "NOT withholding" in out
    assert "WITHHELD" not in out


def test_an_unresolvable_onto_ref_fails_open_loudly(lane, capsys):
    repo = lane["repo"]
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo, onto="origin/does-not-exist") == 0
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    assert "NOT withholding" in capsys.readouterr().out


# ── unit level ─────────────────────────────────────────────────────────────────
def test_jsonl_prefix_verdicts():
    member = fence.Member(path="p", check="jsonl_prefix")
    assert fence.jsonl_prefix_verdict(member, None, b"a\n").status == fence.OK
    assert fence.jsonl_prefix_verdict(member, b"a\n", b"a\nb\n").status == fence.OK
    assert fence.jsonl_prefix_verdict(member, b"a\n", b"a\n").status == fence.OK
    assert fence.jsonl_prefix_verdict(member, b"a\nb\n", b"a\n").status == fence.STALE_BASE
    assert fence.jsonl_prefix_verdict(member, b"a\n", None).status == fence.STALE_BASE
    swapped = fence.jsonl_prefix_verdict(member, b"a\nb\n", b"a\nc\n")
    assert swapped.status == fence.STALE_BASE
    assert swapped.lost == ("b",)


def test_parquet_rows_verdict_is_order_independent():
    member = fence.Member(
        path="p", check="parquet_rows", identity=("award_key", "known_at", "event_state_sha256")
    )
    rows = [("A1", "t1", "aa"), ("A2", "t2", "bb")]
    base = _event_frame(rows)
    assert fence.parquet_rows_verdict(member, base, _event_frame(rows[::-1])).status == fence.OK
    grown = fence.parquet_rows_verdict(member, base, _event_frame([*rows, ("A3", "t3", "cc")]))
    assert grown.status == fence.OK
    restamped = fence.parquet_rows_verdict(
        member, base, _event_frame([("A1", "t1", "aa"), ("A2", "t9", "bb")])
    )
    assert restamped.status == fence.STALE_BASE
    assert "1 of 2 base identities dropped" in restamped.detail


def test_parquet_rows_verdict_is_indeterminate_when_identity_is_absent():
    member = fence.Member(path="p", check="parquet_rows", identity=("nope",))
    verdict = fence.parquet_rows_verdict(member, _event_frame([("A1", "t1", "aa")]), _event_frame([]))
    assert verdict.status == fence.INDETERMINATE
    assert "nope" in verdict.detail


def test_an_indeterminate_member_withholds(lane, capsys):
    repo = lane["repo"]
    _git(repo, "reset", "--hard", "--quiet", "origin/main")
    _write(repo, EVENTS, b"not a parquet file")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "data: torn event ledger")
    assert _run(repo) == 0
    assert "WITHHELD" in capsys.readouterr().out
    assert (repo / EVENTS).read_bytes() == lane["a_events"]


# ── registry ↔ reality ─────────────────────────────────────────────────────────
def test_registry_loads_and_declares_the_govrev_family():
    families = fence.load_registry(REGISTRY)
    keys = {family.key for family in families}
    assert "government-revenue" in keys
    govrev = next(family for family in families if family.key == "government-revenue")
    paths = {member.path for member in govrev.members}
    assert RECEIPTS in paths
    assert EVENTS in paths
    assert LEDGER in paths
    assert "data/government_revenue" in govrev.withhold_paths


def test_every_registry_member_lives_under_a_withhold_path():
    for family in fence.load_registry(REGISTRY):
        for member in family.members:
            assert any(
                member.path == root or member.path.startswith(root.rstrip("/") + "/")
                for root in family.withhold_paths
            ), f"{member.path} is checked but never withheld"


def test_registry_identity_columns_exist_in_the_committed_artifacts():
    """Read from HEAD, not the worktree: a sparse checkout still carries the bytes."""
    repo = ROOT
    checked = 0
    for family in fence.load_registry(REGISTRY):
        for member in family.members:
            if member.check != "parquet_rows":
                continue
            blob = fence.blob_at(repo, "HEAD", member.path)
            if blob is None:
                continue  # declared ahead of its first publish
            frame = pd.read_parquet(io.BytesIO(blob))
            missing = [column for column in member.identity if column not in frame.columns]
            assert not missing, f"{member.path} lost identity column(s) {missing}"
            identities = frame[list(member.identity)].astype("string").fillna("")
            assert not identities.duplicated().any(), (
                f"{member.path}: declared identity is not unique — the fence would "
                f"under-count losses"
            )
            checked += 1
    assert checked >= 4, "expected the govrev parquet spine to be present"
