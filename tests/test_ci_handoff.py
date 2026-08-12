"""The terminal CI handoff — classifier, leak gate, sinks, and the one-shot CLI.

WHAT THIS PINS
--------------
`scripts/ci_handoff.py` is the point where a worker stops. Every defect here is
silent and expensive in one of two directions:

  * released too early — the head is unproven or red, the sweeper will never
    merge it, and the work is ORPHANED with nobody waiting on it;
  * released with a leak — the receipt's private continuation context reaches a
    surface on a PUBLIC repository, where it is world-readable forever.

So the suite is written to catch mutations, not to exercise happy paths. Three in
particular must turn it red: deleting the exact-head comparison in the CLI,
flipping `classify_check_runs`'s skipped-only branch to `armed`, and adding
`payload_ref` to the public projection.

The CLI is driven through exactly two seams: `ci_handoff._gh_json` (the ONE
function that shells out to `gh`) and a real temporary git repository with a
`file://` origin, so the git half runs for real without a network. Every test
that writes a sentinel or a receipt points MASTERMIND_CI_HANDOFF_DIR at
`tmp_path` — nothing here may touch the real `~/.mastermind`.

Run: python -m pytest tests/test_ci_handoff.py -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ci_handoff  # noqa: E402
from scripts import ci_handoff_contract as contract  # noqa: E402

BRANCH = "claude/ci-handoff-wave-a"
REPO = "acme/macro"
BASE_SHA = "b" * 40
OTHER_HEAD = "0123456789abcdef0123456789abcdef01234567"

#: A fake private control-plane primitive, matching the real signature
#: ``append(event: dict, *, root=None) -> str | None``. It records every call so a
#: test can prove the sink appends exactly ONCE per handoff_id.
FAKE_RUN_EVENTS = '''
import json
import os
from pathlib import Path


def append(event, *, root=None):
    log = Path(os.environ["FAKE_RUN_EVENTS_LOG"])
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"root": None if root is None else str(root),
                                 "event": event}) + "\\n")
    return "evt-" + str(event.get("idempotency_key"))
'''


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", *args),
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    """A real repo whose `origin` is a local bare repo reachable over ``file://``.

    The `file://` shape is deliberate: `contract.normalize_repo` returns "" for a
    bare local path (a local clone has no canonical owner), so a plain path remote
    would key the whole handoff to a repo identity that does not exist. A
    `file://` URL both resolves to `acme/macro` AND lets `git ls-remote`/`git push`
    run for real with no network.
    """
    origin = tmp_path / "origin" / "acme" / "macro.git"
    origin.mkdir(parents=True)
    _git(origin, "init", "--bare", "-b", "main")

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ):
        _git(repo, "config", key, value)
    _git(repo, "remote", "add", "origin", origin.as_uri())

    (repo / "kept.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "push", "origin", "main")

    _git(repo, "checkout", "-b", BRANCH)
    (repo / "feature.txt").write_text("work\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "push", "origin", BRANCH)
    return repo


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _check(name: str, status: str = "completed", conclusion: str | None = "success") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def _pull(
    head: str,
    *,
    number: int = 4242,
    labels: tuple[str, ...] = (contract.MERGE_ON_GREEN_LABEL,),
    state: str = "OPEN",
    draft: bool = False,
    base: str = "main",
) -> dict:
    return {
        "number": number,
        "headRefOid": head,
        "baseRefOid": BASE_SHA,
        "baseRefName": base,
        "isDraft": draft,
        "state": state,
        "labels": [{"name": name} for name in labels],
        "url": f"https://github.com/{REPO}/pull/{number}",
    }


class FakeGh:
    """A stand-in for the ONE function in `ci_handoff` that shells out to `gh`.

    Records every call, so a test can assert the snapshot is BOUNDED — the whole
    point of the handoff is that it asks GitHub a fixed number of questions and
    leaves, rather than joining the fleet on the shared 5,000/hr REST bucket.
    """

    def __init__(self, pull: dict | None, runs=()) -> None:
        self.pull = pull
        self.runs = list(runs)
        self.calls: list[list[str]] = []

    def __call__(self, args, **_kwargs):
        argv = [str(a) for a in args]
        self.calls.append(argv)
        if argv[:2] == ["pr", "list"]:
            return [] if self.pull is None else [dict(self.pull)]
        if argv[:2] == ["pr", "view"]:
            return None if self.pull is None else dict(self.pull)
        if argv[:1] == ["api"]:
            match = re.search(r"[?&]page=(\d+)", argv[1])
            assert match, f"check-run request carries no page: {argv[1]}"
            page = int(match.group(1))
            size = ci_handoff.CHECK_RUN_PAGE_SIZE
            chunk = self.runs[(page - 1) * size : page * size]
            return {"total_count": len(self.runs), "check_runs": chunk}
        raise AssertionError(f"unexpected gh call: {argv}")

    @property
    def api_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[:1] == ["api"]]


def _invoke(monkeypatch, tmp_path: Path, repo: Path, fake: FakeGh, argv=(), *, actions=False) -> int:
    """Run the CLI in-process against `repo`, with private state under tmp_path.

    GITHUB_ACTIONS is pinned rather than inherited: it decides whether a refusal
    lands as a stdout annotation or a stderr message, and this suite itself runs
    inside Actions.
    """
    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(tmp_path / "private-state"))
    monkeypatch.setenv("GITHUB_ACTIONS", "true" if actions else "false")
    monkeypatch.delenv("MASTERMIND_CONTROL_PLANE_ROOT", raising=False)
    monkeypatch.delenv("MASTERMIND_ROOT", raising=False)
    monkeypatch.setattr(ci_handoff, "_gh_json", fake)
    monkeypatch.chdir(repo)
    return ci_handoff.main(list(argv))


def _marker(out: str) -> str:
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines, "the CLI printed nothing"
    return lines[-1]


# ---------------------------------------------------------------------------
# the classifier — armed / red / unproven
# ---------------------------------------------------------------------------
def test_no_considered_checks_is_unproven():
    verdict = contract.classify_check_runs([])
    assert verdict.state == "unproven"
    assert not verdict.is_armed


def test_only_skipped_and_neutral_is_unproven():
    """A head whose checks all finished proving NOTHING must never be armed.

    This is the #4779 rule: an absence of red is not a pass. The sweeper will not
    merge such a head, so releasing the worker here orphans the work.
    """
    verdict = contract.classify_check_runs(
        [
            _check("ci-pack-1", conclusion="skipped"),
            _check("ci-pack-2", conclusion="neutral"),
            _check("fences", conclusion="skipped"),
        ]
    )
    assert verdict.state == "unproven", (
        "every considered check COMPLETED and none succeeded — that head has "
        "finished proving nothing and must not be handed off"
    )
    assert verdict.successes == ()
    assert verdict.pending == ()


def test_pending_only_is_armed():
    verdict = contract.classify_check_runs(
        [_check("ci-pack-1", status="queued", conclusion=None),
         _check("ci-pack-2", status="in_progress", conclusion=None)]
    )
    assert verdict.state == "armed"
    assert verdict.pending == ("ci-pack-1", "ci-pack-2")
    assert verdict.successes == ()


def test_one_success_plus_pending_is_armed():
    verdict = contract.classify_check_runs(
        [_check("ci-pack-1"), _check("ci-pack-2", status="in_progress", conclusion=None)]
    )
    assert verdict.state == "armed"
    assert verdict.successes == ("ci-pack-1",)
    assert verdict.pending == ("ci-pack-2",)


def test_one_success_all_complete_is_armed():
    verdict = contract.classify_check_runs(
        [_check("ci-pack-1"), _check("ci-pack-2", conclusion="skipped")]
    )
    assert verdict.state == "armed"
    assert verdict.successes == ("ci-pack-1",)
    assert verdict.pending == ()


def test_red_outranks_pending():
    """Red wins over pending here — the reverse of the sweeper's own ordering.

    The worker can act on a red immediately, so telling it early is pure benefit;
    the sweeper gates an irreversible merge and therefore waits for everything.
    """
    verdict = contract.classify_check_runs(
        [
            _check("ci-pack-1", status="in_progress", conclusion=None),
            _check("ci-pack-3", conclusion="failure"),
            _check("fences"),
        ]
    )
    assert verdict.state == "red"
    assert verdict.red == ("ci-pack-3 (failure)",)
    assert verdict.pending == ("ci-pack-1",)
    assert verdict.successes == ("fences",)


def test_known_spurious_workers_check_is_ignored():
    verdict = contract.classify_check_runs(
        [_check("Workers Builds: macro", conclusion="failure"), _check("ci-pack-1")]
    )
    assert verdict.state == "armed"
    assert verdict.red == ()
    assert verdict.ignored_spurious == ("Workers Builds: macro",)


def test_spurious_only_red_head_is_unproven_not_armed():
    """Ignoring the one spurious X must not manufacture proof out of nothing."""
    verdict = contract.classify_check_runs(
        [_check("Workers Builds: macro", conclusion="failure")]
    )
    assert verdict.state == "unproven"
    assert verdict.ignored_spurious == ("Workers Builds: macro",)


@pytest.mark.parametrize(
    "name",
    [
        "ci-pack-3",
        "Workers Builds: charting-app",   # right family, wrong project
        "workers builds",                 # no project at all
        "Cloudflare Pages: macro",        # right project, wrong family
        "macro",
    ],
)
def test_an_unknown_failure_name_is_not_ignored(name):
    """The spurious allowlist is ONE check. Widening it is a ruling, not a refactor."""
    assert not contract.is_spurious_check(name)
    verdict = contract.classify_check_runs([_check(name, conclusion="failure")])
    assert verdict.state == "red"
    assert verdict.red == (f"{name} (failure)",)


# ---------------------------------------------------------------------------
# receipt identity + the leak gate
# ---------------------------------------------------------------------------
def _receipt(head: str, *, payload_ref: str | None = None, accepted_at="2026-08-11T19:00:00Z"):
    return contract.build_receipt(
        repo=REPO,
        pr_number=4242,
        branch=BRANCH,
        base_ref="main",
        base_sha=BASE_SHA,
        head_sha=head,
        verdict=contract.classify_check_runs([_check("ci-pack-1")]),
        accepted_at=accepted_at,
        continuation_id="cont-abc",
        resume_on="merged",
        payload_ref=payload_ref,
    )


def test_receipt_identity_is_deterministic_and_head_scoped():
    head = "a" * 40
    first = _receipt(head, accepted_at="2026-08-11T19:00:00Z")
    second = _receipt(head, accepted_at="2026-08-11T23:59:59Z")
    moved = _receipt("c" * 40)

    assert first["handoff_id"] == second["handoff_id"], (
        "identity must not depend on when the snapshot was taken — the sink and "
        "the controller dedupe on it"
    )
    assert first["handoff_id"] == contract.receipt_id(REPO, 4242, head)
    assert moved["handoff_id"] != first["handoff_id"], (
        "a new commit describes a head the sweeper would merge instead, so it must "
        "mint a NEW handoff"
    )


def test_public_receipt_drops_the_payload_and_every_private_field():
    """THE LEAK GATE. Macro is public; everything on it is readable forever."""
    secret = "private://payload/continuation-prompt-body"
    receipt = _receipt("a" * 40, payload_ref=secret)

    assert "payload_ref" not in contract.PUBLIC_RECEIPT_FIELDS, (
        "the public projection is built FROM this allowlist — a private field "
        "listed here reaches every public surface at once"
    )

    projected = contract.public_receipt(receipt)
    assert "payload_ref" not in projected
    assert set(projected) == {
        "schema",
        "handoff_id",
        "pr_number",
        "head_sha",
        "continuation_id",
        "resume_on",
    }, "the public projection grew a field; every one of them is world-readable"

    blob = contract.compact_json(projected)
    for private_value in (secret, receipt["base_sha"], receipt["branch"], receipt["repo"]):
        assert private_value not in blob, f"public projection leaks {private_value!r}"
    assert secret not in contract.terminal_marker(receipt)


@pytest.mark.parametrize(
    "injected",
    [
        {"payload_ref": "private://payload/body"},        # the private field, by name
        {"base_sha": "a" * 40},                            # any other private field
        {"api_key": "sk-live-1234"},                       # a secret-smelling key
        {"continuation": {"payload_ref": "x"}},            # the private container
        {"resume_on": {"nested": "payload"}},              # a container in a public slot
        {"handoff_id": "private://local/cih_macro_1_abc"},  # a private URI value
        {"handoff_id": "/Users/agent/.mastermind/receipt.json"},  # an absolute path
        {"handoff_id": "~/.mastermind/receipt.json"},      # a home-relative path
    ],
)
def test_assert_public_safe_rejects_anything_private(injected):
    safe = contract.public_receipt(_receipt("a" * 40, payload_ref="private://payload/body"))
    with pytest.raises(ValueError):
        contract.assert_public_safe({**safe, **injected})


def test_terminal_marker_is_exactly_one_parseable_line():
    receipt = _receipt("a" * 40, payload_ref="private://payload/body")
    marker = contract.terminal_marker(receipt)

    assert "\n" not in marker and "\r" not in marker
    assert marker.startswith(contract.MARKER_PREFIX)
    parsed = contract.parse_terminal_marker("prose above\n" + marker + "\nprose below")
    assert parsed == {
        "schema": contract.PUBLIC_SCHEMA,
        "handoff_id": receipt["handoff_id"],
        "pr_number": 4242,
        "head_sha": "a" * 40,
        "continuation_id": "cont-abc",
        "resume_on": "merged",
        "state": contract.STATE_WAITING_CI,
    }


# ---------------------------------------------------------------------------
# sinks
# ---------------------------------------------------------------------------
def test_local_sink_is_idempotent_and_writes_outside_the_repo(tmp_path, monkeypatch):
    state = tmp_path / "private-state"
    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(state))
    receipt = _receipt("a" * 40, payload_ref="private://payload/body")
    sink = ci_handoff.LocalPrivateSink()

    first = sink.publish(receipt)
    second = sink.publish(receipt)

    assert first == second == f"private://local/{receipt['handoff_id']}"
    written = sorted((state / "receipts").glob("*.json"))
    assert len(written) == 1, "re-publishing the same handoff_id must be a no-op"
    assert written[0].name == f"{receipt['handoff_id']}.json"
    assert json.loads(written[0].read_text(encoding="utf-8"))["handoff_id"] == receipt["handoff_id"]
    assert ROOT not in written[0].parents, "a receipt inside the checkout gets COMMITTED"


def _control_plane(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mastermind"
    module = root / "control_plane" / "run_events.py"
    module.parent.mkdir(parents=True)
    module.write_text(FAKE_RUN_EVENTS, encoding="utf-8")
    monkeypatch.setenv("MASTERMIND_CONTROL_PLANE_ROOT", str(root))
    monkeypatch.setenv("FAKE_RUN_EVENTS_LOG", str(tmp_path / "events.jsonl"))
    return root


def test_control_plane_sink_appends_once_per_handoff(tmp_path, monkeypatch):
    """`run_events.append` has no idempotency, so the sink must supply it."""
    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(tmp_path / "private-state"))
    root = _control_plane(tmp_path, monkeypatch)
    receipt = _receipt("a" * 40, payload_ref="private://payload/body")

    sink = ci_handoff.resolve_sink("control-plane", continuation_requested=True)
    first = sink.publish(receipt)
    second = sink.publish(receipt)

    assert first == second == f"private://control-plane/run_events/{receipt['handoff_id']}"
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(events) == 1, "the second publish must be skipped by the key pointer"
    assert events[0]["root"] == str(root)
    assert events[0]["event"]["idempotency_key"] == receipt["handoff_id"]


def test_auto_sink_is_null_when_no_continuation_was_requested(tmp_path, monkeypatch):
    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(tmp_path / "private-state"))
    _control_plane(tmp_path, monkeypatch)

    sink = ci_handoff.resolve_sink("auto", continuation_requested=False)
    assert isinstance(sink, ci_handoff.NullSink)
    assert sink.publish(_receipt("a" * 40)) == ""
    assert not (tmp_path / "events.jsonl").exists()


def test_auto_sink_falls_back_to_local_without_a_control_plane(tmp_path, monkeypatch):
    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(tmp_path / "private-state"))
    monkeypatch.delenv("MASTERMIND_CONTROL_PLANE_ROOT", raising=False)
    monkeypatch.delenv("MASTERMIND_ROOT", raising=False)

    sink = ci_handoff.resolve_sink("auto", continuation_requested=True)
    assert isinstance(sink, ci_handoff.LocalPrivateSink)


# ---------------------------------------------------------------------------
# the CLI — one finite snapshot
# ---------------------------------------------------------------------------
def test_cli_hands_off_an_armed_head_and_prints_one_marker(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(
        _pull(head),
        [_check("ci-pack-1"), _check("ci-pack-2", status="in_progress", conclusion=None)],
    )

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0

    out = capsys.readouterr().out
    marker = _marker(out)
    assert marker.startswith(contract.MARKER_PREFIX)
    assert "\n" not in marker
    parsed = contract.parse_terminal_marker(out)
    assert parsed["handoff_id"] == contract.receipt_id(REPO, 4242, head)
    assert parsed["head_sha"] == head
    assert parsed["state"] == contract.STATE_WAITING_CI
    assert "payload_ref" not in parsed
    # A human-readable paragraph precedes the marker; the marker is the LAST line.
    assert len(out.splitlines()) > 1
    assert contract.MERGE_ON_GREEN_LABEL in out

    sentinel = contract.sentinel_path(REPO, BRANCH)
    written = json.loads(sentinel.read_text(encoding="utf-8"))
    accepted_at = written.pop("accepted_at")
    assert written == {
        "repo": REPO,
        "branch": BRANCH,
        "head_sha": head,
        "pr_number": 4242,
        "handoff_id": parsed["handoff_id"],
    }
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", accepted_at)
    assert ROOT not in sentinel.parents, "the sentinel must live OUTSIDE the checkout"


def test_cli_json_mode_prints_the_private_receipt_before_the_marker(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(_pull(head), [_check("ci-pack-1")])

    assert _invoke(
        monkeypatch, tmp_path, repo, fake,
        ["--json", "--continuation-id", "cont-1", "--payload-ref", "private://payload/body"],
    ) == 0

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    receipt = json.loads(lines[-2])
    assert receipt["schema"] == contract.SCHEMA
    assert receipt["continuation"]["payload_ref"] == "private://payload/body"
    assert receipt["base_sha"] == BASE_SHA
    # …and none of that reached the marker.
    assert "private://payload/body" not in lines[-1]
    assert contract.parse_terminal_marker(out)["continuation_id"] == "cont-1"


def test_cli_takes_one_bounded_snapshot_and_never_polls(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(_pull(head), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0
    capsys.readouterr()

    assert len(fake.api_calls) == 1, "one page of check runs is one snapshot"
    assert len(fake.calls) == 2, f"the CLI made {len(fake.calls)} gh calls: {fake.calls}"

    source = Path(ci_handoff.__file__).read_text(encoding="utf-8")
    assert "time.sleep" not in source, "a handoff that sleeps is a poll"
    assert "while True" not in source, "a handoff that loops is a watch"


def test_cli_paginates_check_runs_and_stops_at_the_cap(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    size = ci_handoff.CHECK_RUN_PAGE_SIZE

    many = [_check(f"ci-pack-{i}") for i in range(size * 2 + 5)]
    fake = FakeGh(_pull(head), many)
    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0
    capsys.readouterr()
    assert len(fake.api_calls) == 3, "stop on the short page, never guess the tail away"

    runaway = [_check(f"ci-pack-{i}") for i in range(size * 20)]
    fake = FakeGh(_pull(head), runaway)
    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0
    capsys.readouterr()
    assert len(fake.api_calls) == ci_handoff.MAX_CHECK_RUN_PAGES, (
        "a pathological head may not spend the whole shared API budget"
    )


def test_cli_red_head_exits_2_and_names_the_checks(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(
        _pull(head),
        [_check("ci-pack-3", conclusion="failure"),
         _check("ci-pack-1", status="in_progress", conclusion=None)],
    )

    assert _invoke(monkeypatch, tmp_path, repo, fake, actions=True) == 2

    out = capsys.readouterr().out
    annotations = [line for line in out.splitlines() if line.startswith("::error title=")]
    assert annotations, (
        "a nonzero exit must emit a line-START annotation in Actions — a logger "
        "prefix makes GitHub drop it silently"
    )
    assert "ci-pack-3 (failure)" in annotations[0]
    assert contract.parse_terminal_marker(out) is None, "a refusal is not a handoff"
    assert not contract.sentinel_path(REPO, BRANCH).exists()


def test_cli_unproven_head_exits_3(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(_head(repo)), [])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 3
    err = capsys.readouterr().err
    assert "UNPROVEN" in err
    assert not contract.sentinel_path(REPO, BRANCH).exists()


def test_cli_skipped_only_head_exits_3(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    fake = FakeGh(
        _pull(_head(repo)),
        [_check("ci-pack-1", conclusion="skipped"), _check("fences", conclusion="neutral")],
    )

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 3
    capsys.readouterr()


def test_cli_requires_the_exact_local_head(tmp_path, monkeypatch, capsys):
    """The pull request head must EQUAL local HEAD — string equality, fail closed.

    A force-moved branch reaches this point with a clean ahead-count, so an armed
    pull request whose head is older than the worktree would hand off work the
    sweeper is not going to merge.
    """
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(OTHER_HEAD), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4

    err = capsys.readouterr().err
    assert "head" in err.lower()
    assert not contract.sentinel_path(REPO, BRANCH).exists()


def test_cli_rejects_an_empty_remote_head(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    pull = _pull(_head(repo))
    pull["headRefOid"] = ""
    fake = FakeGh(pull, [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4
    capsys.readouterr()


def test_cli_dirty_tree_exits_4(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    (repo / "scratch.txt").write_text("session dirt\n", encoding="utf-8")
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4
    assert "scratch.txt" in capsys.readouterr().err
    assert fake.calls == [], "a dirty tree is refused before any GitHub call"


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/worktrees/other-session/scratch.txt",
        ".claire/worktrees/other-session/scratch.txt",
        ".codex-worktrees/other-session/scratch.txt",
    ],
)
def test_cli_ignores_other_fleets_worktrees(tmp_path, monkeypatch, capsys, relative):
    """A session can neither commit nor safely delete another fleet's checkout."""
    repo = _repo(tmp_path)
    path = repo / relative
    path.parent.mkdir(parents=True)
    path.write_text("another session's work\n", encoding="utf-8")
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0
    capsys.readouterr()


def test_cli_tracked_content_under_a_worktree_root_still_gates(tmp_path, monkeypatch, capsys):
    """The exclusion covers UNTRACKED entries only — it must fail closed."""
    repo = _repo(tmp_path)
    path = repo / ".claude" / "worktrees" / "note.md"
    path.parent.mkdir(parents=True)
    path.write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "-f", str(path))
    _git(repo, "commit", "-m", "track a file under the worktree root")
    _git(repo, "push", "origin", BRANCH)
    path.write_text("modified after the commit\n", encoding="utf-8")

    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])
    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4
    assert "note.md" in capsys.readouterr().err


def test_cli_unpushed_commit_exits_4(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    (repo / "later.txt").write_text("after the push\n", encoding="utf-8")
    _git(repo, "add", "later.txt")
    _git(repo, "commit", "-m", "unpushed")
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4
    assert "origin/" in capsys.readouterr().err
    assert fake.calls == []


def test_cli_unpushed_branch_exits_4(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "claude/never-pushed")
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 4
    assert "does not exist on origin" in capsys.readouterr().err


def test_cli_missing_merge_on_green_label_exits_5(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(_head(repo), labels=("hold",)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 5

    err = capsys.readouterr().err
    assert contract.MERGE_ON_GREEN_LABEL in err
    assert not contract.sentinel_path(REPO, BRANCH).exists()
    assert fake.api_calls == [], "an unarmed pull request is refused before the snapshot"


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"state": "CLOSED"}, "not OPEN"),
        ({"state": "MERGED"}, "not OPEN"),
        ({"draft": True}, "DRAFT"),
        ({"base": "release/2026-08"}, "`main`"),
    ],
)
def test_cli_rejects_a_pull_request_no_sweeper_will_merge(
    tmp_path, monkeypatch, capsys, overrides, needle
):
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(_head(repo), **overrides), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 5
    assert needle in capsys.readouterr().err
    assert not contract.sentinel_path(REPO, BRANCH).exists()


def test_cli_without_an_open_pull_request_exits_5(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    fake = FakeGh(None)

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 5
    assert "no OPEN pull request" in capsys.readouterr().err


def test_cli_pr_flag_uses_pr_view(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(_pull(head, number=5361), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake, ["--pr", "5361"]) == 0
    capsys.readouterr()
    assert fake.calls[0][:3] == ["pr", "view", "5361"]


def test_cli_sink_failure_with_a_continuation_exits_6(tmp_path, monkeypatch, capsys):
    """A continuation nobody recorded is a continuation nobody resumes."""
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    code = _invoke(
        monkeypatch, tmp_path, repo, fake,
        ["--sink", "control-plane", "--continuation-id", "cont-1"],
    )
    assert code == 6
    assert "sink" in capsys.readouterr().err
    assert not contract.sentinel_path(REPO, BRANCH).exists()


def test_cli_sink_failure_without_a_continuation_is_not_a_failure(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    fake = FakeGh(_pull(_head(repo)), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake, ["--sink", "control-plane"]) == 0
    assert contract.parse_terminal_marker(capsys.readouterr().out) is not None


def test_cli_gh_failure_exits_7(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)

    def _boom(args, **_kwargs):
        raise ci_handoff.HandoffError(
            ci_handoff.EXIT_INFRA, "gh-failed", "API rate limit exceeded"
        )

    monkeypatch.setenv(contract.SENTINEL_DIR_ENV, str(tmp_path / "private-state"))
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.setattr(ci_handoff, "_gh_json", _boom)
    monkeypatch.chdir(repo)

    assert ci_handoff.main([]) == 7
    assert "rate limit" in capsys.readouterr().err


def test_sentinel_is_invalidated_by_a_new_head(tmp_path, monkeypatch, capsys):
    """The worker handed off ONE head; work done after it is covered by nothing."""
    repo = _repo(tmp_path)
    head = _head(repo)
    fake = FakeGh(_pull(head), [_check("ci-pack-1")])

    assert _invoke(monkeypatch, tmp_path, repo, fake) == 0
    capsys.readouterr()

    assert contract.active_sentinel(REPO, BRANCH, head) is not None

    (repo / "more.txt").write_text("a later commit\n", encoding="utf-8")
    _git(repo, "add", "more.txt")
    _git(repo, "commit", "-m", "more work")
    moved = _head(repo)

    assert moved != head
    assert contract.active_sentinel(REPO, BRANCH, moved) is None
    assert contract.read_sentinel(REPO, BRANCH) is not None, "the file itself survives"


def test_help_runs_bare_from_any_directory(tmp_path):
    """`python3 scripts/ci_handoff.py --help` must resolve its own repo imports.

    Invoked by file path, `sys.path[0]` is `<repo>/scripts` and the repo root is
    NOWHERE — the contract import only resolves because the script pins its own
    root. Run from a neutral cwd so nothing ambient can supply it.
    """
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ci_handoff.py"), "--help"],
        cwd=str(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for flag in (
        "usage: ci_handoff.py",
        "--pr NUMBER",
        "--resume-on {merged,live,manual}",
        "--continuation-id ID",
        "--payload-ref PRIVATE_REF",
        "--sink {auto,control-plane,local,none}",
        "--json",
    ):
        assert flag in proc.stdout, f"missing {flag!r} from --help"
