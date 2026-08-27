"""Agent OS Phase 2 — `agentos.py status` and `agentos.py brief`.

What is pinned here, and why each one is worth a test:

* **I1** — nothing added can gate, block, dispatch, or start execution.  Both commands
  exit 0 on every input this suite can construct, including a malformed record set, and
  no artifact they write is read by a runtime.
* **I3** — the generated artifacts carry a DO-NOT-EDIT banner and are a PURE FUNCTION of
  their inputs.  The comparison is partitioned: `generated_at`, `inputs.worktrees`,
  `inputs.active_builds_age_hours` and `inputs.degraded` sit in an ENVELOPE and are
  excluded, because a byte-identity test that needed a frozen clock to pass would hide
  real nondeterminism in the records themselves.  With the clock frozen, the whole file
  is compared.
* **I4** — fail-OPEN on join (missing active_builds, absent sibling repo, unwritable
  output), fail-CLOSED on schema.  Both directions.
* **Zero network** — proven twice: statically (no network module is importable from the
  new code paths) and at runtime (the command completes with sockets disabled).  The
  5,000/hr REST bucket is shared with `ship_loop_guard.py`, which fails CLOSED when it
  is exhausted, so a CEO command that burned quota could block the Stop it reports on.
* The **record-vs-execution join** — the one thing this generator adds that nothing else
  in the org has.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "agentos"
CLI = REPO / "scripts" / "agentos.py"
GENERATOR = REPO / "scripts" / "agentos.py"

pytestmark = pytest.mark.skipif(
    not STORE.exists(),
    reason="agentos/ outside this sparse checkout — run: git sparse-checkout add agentos",
)

FROZEN = "2026-08-12T14:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    work = tmp_path / "agentos"
    shutil.copytree(STORE, work)
    return work


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environ = dict(os.environ)
    # Pin the sibling lookups so the result does not depend on which checkouts happen to
    # exist on the machine running the suite.
    environ.setdefault("MACRO_TERMINAL_REPO", "/nonexistent-terminal-checkout")
    environ.setdefault("MACRO_MASTERMIND_REPO", "/nonexistent-mastermind-checkout")
    if env:
        environ.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, cwd=REPO, env=environ,
    )


def _status(store_root: Path, out: Path, *extra: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return _run(
        "status", "--root", str(store_root),
        "--json-out", str(out), "--md-out", str(out.with_suffix(".md")),
        *extra, **kwargs,
    )


def _state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


ACTIVE_BUILDS = {
    "schema": "active_builds.v1",
    "generated_at": "2026-08-12T06:00:00+00:00",
    "base": {"sha": "deadbeef"},
    "merged_days": 14,
    "merged_truncated": False,
    "open_prs": [
        {"number": 5438, "title": "CN P-A1", "head_ref": "cn/p-a1",
         "updated_at": "2026-08-12T05:00:00Z", "is_draft": False,
         "merge_state": "CLEAN", "files": []},
    ],
    "collisions": [],
    "recent_merged": [
        {"number": 5370, "title": "Prophet queue drain", "merged_at": "2026-08-12T03:00:00Z"},
        {"number": 5402, "title": "GMI R1", "merged_at": "2026-08-11T09:00:00Z"},
        {"number": 5457, "title": "Watchlist W0", "merged_at": "2026-08-10T09:00:00Z"},
        {"number": 5463, "title": "Watchlist husk", "merged_at": "2026-08-12T08:00:00Z"},
    ],
}


@pytest.fixture()
def builds(tmp_path: Path) -> Path:
    path = tmp_path / "active_builds.json"
    path.write_text(json.dumps(ACTIVE_BUILDS), encoding="utf-8")
    return path


# ------------------------------------------------------------------ I3: purity


def test_status_output_is_byte_identical_with_a_frozen_clock(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """Whole-file identity: with the clock pinned, nothing else may vary."""
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    assert _status(store, first, "--now", FROZEN, "--active-builds", str(builds)).returncode == 0
    assert _status(store, second, "--now", FROZEN, "--active-builds", str(builds)).returncode == 0
    assert first.read_bytes() == second.read_bytes()
    assert first.with_suffix(".md").read_bytes() == second.with_suffix(".md").read_bytes()


def test_records_section_is_identical_without_a_frozen_clock(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """The PARTITION is the real claim: the pure half must not move with the clock.

    Freezing the clock is a convenience for the whole-file test above.  This one runs
    the generator twice with the wall clock live and compares only the section that is
    supposed to be a pure function — which is what makes the split honest rather than a
    way to make a flaky test pass.
    """
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert _status(store, first, "--active-builds", str(builds)).returncode == 0
    assert _status(store, second, "--active-builds", str(builds)).returncode == 0
    one, two = _state(first), _state(second)
    pure = ("schema", "generator", "workstreams", "needs_ceo", "warnings")
    for section in pure:
        assert one[section] == two[section], f"{section} is not a pure function of its inputs"
    assert one["readiness"] == two["readiness"]


def test_generated_artifacts_carry_the_do_not_edit_banner(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    out = tmp_path / "state.json"
    _status(store, out, "--now", FROZEN, "--active-builds", str(builds))
    markdown = out.with_suffix(".md").read_text(encoding="utf-8")
    assert markdown.startswith("<!-- GENERATED — DO NOT EDIT BY HAND.")
    assert "scripts/agentos.py status" in markdown
    assert _state(out)["generator"] == "scripts/agentos.py status"
    assert _state(out)["schema"] == "agent_os_state.v1"


# ---------------------------------------------------------- I4: fail-open join


def test_absent_active_builds_degrades_and_still_reports(
    store: Path, tmp_path: Path
) -> None:
    """The common LOCAL case: data/ is outside a sparse worktree entirely."""
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN,
                     "--active-builds", str(tmp_path / "no-such-file.json"))
    assert result.returncode == 0, result.stdout + result.stderr
    state = _state(out)
    assert state["workstreams"], "records must still be reported without PR state"
    assert any("absent" in item for item in state["inputs"]["degraded"])
    assert state["inputs"]["active_builds_age_hours"] is None
    assert state["readiness"]["records"], "readiness must fail open with the records"
    assert state["readiness"]["degraded"] == [], (
        "missing PR state does not make the authored dependency graph incomplete"
    )


def test_brief_renders_without_active_builds(store: Path, tmp_path: Path) -> None:
    result = _run("brief", "--root", str(store), "--now", FROZEN, "--no-remember",
                  "--active-builds", str(tmp_path / "no-such-file.json"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MASTERMIND STATUS" in result.stdout
    assert "DEGRADED" in result.stdout, "a missing input must never render as quiet"
    assert "active_builds MISSING" in result.stdout


def test_absent_sibling_repo_degrades_and_neutralises_p0(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds),
                     env={"MACRO_MASTERMIND_REPO": str(tmp_path / "gone")})
    assert result.returncode == 0
    state = _state(out)
    assert any("p0" in item for item in state["inputs"]["degraded"])
    assert all(row["p0_active"] is None for row in state["workstreams"] if row["p0"])
    assert state["readiness"]["degraded"] == [], (
        "P0 is priority context and is deliberately absent from readiness"
    )


def test_auxiliary_truncation_degrades_parent_but_not_readiness(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    payload = json.loads(builds.read_text(encoding="utf-8"))
    payload["open_prs_truncated"] = True
    payload["merged_truncated"] = True
    builds.write_text(json.dumps(payload), encoding="utf-8")

    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    state = _state(out)
    assert any("TRUNCATED" in item for item in state["inputs"]["degraded"])
    assert state["readiness"]["degraded"] == []


def test_malformed_non_workstream_degrades_parent_only(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """Only authoring that can remove readiness identities belongs in its envelope."""
    (store / "decisions" / "DEC-NOT-READINESS.md").write_text(
        "not frontmatter\n", encoding="utf-8"
    )
    assert _run("validate", "--root", str(store)).returncode == 1

    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    state = _state(out)
    assert any("DEC-NOT-READINESS.md" in item for item in state["inputs"]["degraded"])
    assert state["readiness"]["degraded"] == []


def test_unwritable_output_leaves_the_previous_artifact_untouched(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """`degraded` is the report; the last good view is NOT clobbered."""
    out = tmp_path / "locked" / "state.json"
    out.parent.mkdir()
    out.write_text('{"schema": "agent_os_state.v1", "sentinel": true}\n', encoding="utf-8")
    before = out.read_bytes()
    out.chmod(0o444)
    try:
        result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds))
    finally:
        out.chmod(0o644)
    assert result.returncode == 0, "an unwritable output must never fail the nightly"
    assert out.read_bytes() == before, "the previous artifact was overwritten"
    assert "could not write" in result.stdout


def test_missing_store_exits_zero_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "state.json"
    result = _status(tmp_path / "no-store", out, "--now", FROZEN)
    assert result.returncode == 0
    assert not out.exists()


# --------------------------------------------------------- I4: fail-closed schema


def test_schema_stays_fail_closed_while_the_view_stays_fail_open(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """A malformed record reds `validate` and is EXCLUDED from — never blanks — the view."""
    target = store / "workstreams" / "WS-GMI-THEME-GRAPH.md"
    # Mutate whatever status the live record carries; pinning its literal value made the
    # fixture a silent no-op when the record's status legitimately changed (2026-08-17).
    target.write_text(
        re.sub(r"(?m)^status: \S+", "status: humming", target.read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )
    validated = _run("validate", "--root", str(store))
    assert validated.returncode == 1, "schema must still fail closed"

    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds))
    assert result.returncode == 0, "the VIEW must not go dark because one record is bad"
    state = _state(out)
    assert any("malformed" in item for item in state["inputs"]["degraded"])
    assert [row["key"] for row in state["workstreams"]], "the other records still report"
    assert any("malformed" in item for item in state["readiness"]["degraded"])
    assert not any(
        item["workstream"] == "GMI-THEME-GRAPH"
        for item in state["readiness"]["records"]
    ), "a malformed source must not produce a readiness assertion"


def test_duplicate_workstream_fails_validation_but_readiness_keeps_one_identity(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """Duplicate authored truth is a hard error; the view stays deterministic and degraded."""
    original = store / "workstreams" / "WS-GMI-THEME-GRAPH.md"
    dependent = store / "workstreams" / "WS-WATCHLIST-PORTFOLIO-CEO.md"
    dependent.write_text(
        dependent.read_text(encoding="utf-8")
        .replace("status: active", "status: proposed", 1)
        .replace(
            "ambiguity: scoped\nwaves:",
            "ambiguity: scoped\ndepends_on: [WS:GMI-THEME-GRAPH]\nwaves:",
            1,
        ),
        encoding="utf-8",
    )
    # Sort after the canonical file so the loader's deterministic first-record rule is
    # explicit rather than accidentally exercising a filename-mismatch-first variant.
    duplicate = store / "workstreams" / "WS-ZZZ-GMI-THEME-GRAPH-COPY.md"
    duplicate.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")

    validated = _run("validate", "--root", str(store))
    assert validated.returncode == 1
    assert "duplicate-key" in validated.stdout

    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds))
    assert result.returncode == 0
    readiness = _state(out)["readiness"]
    assert any("duplicate-key" in item for item in readiness["degraded"])
    records = {
        (item["workstream"], item["wave"]): item
        for item in readiness["records"]
    }
    identities = [identity for identity in records if identity[0] == "GMI-THEME-GRAPH"]
    assert identities.count(("GMI-THEME-GRAPH", None)) == 1
    assert all(records[identity]["state"] == "unknown" for identity in identities)
    assert all(records[identity]["reason_code"] == "status_unknown"
               for identity in identities)
    for identity in (("WATCHLIST-PORTFOLIO-CEO", None),
                     ("WATCHLIST-PORTFOLIO-CEO", "W1")):
        assert records[identity]["state"] == "unknown"
        assert records[identity]["reason_code"] == "status_unknown"
        assert "WS:GMI-THEME-GRAPH" in records[identity]["reason"]
        assert "WS:GMI-THEME-GRAPH" in records[identity]["unmet_dependencies"]


def test_malformed_dependency_target_makes_surviving_dependents_unknown(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    target = store / "workstreams" / "WS-GMI-THEME-GRAPH.md"
    # Status-agnostic mutation — see the fail-closed test above.
    target.write_text(
        re.sub(r"(?m)^status: \S+", "status: malformed", target.read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )
    dependent = store / "workstreams" / "WS-WATCHLIST-PORTFOLIO-CEO.md"
    dependent.write_text(
        dependent.read_text(encoding="utf-8")
        .replace("status: active", "status: proposed", 1)
        .replace(
            "ambiguity: scoped\nwaves:",
            "ambiguity: scoped\ndepends_on: [WS:GMI-THEME-GRAPH]\nwaves:",
            1,
        ),
        encoding="utf-8",
    )
    assert _run("validate", "--root", str(store)).returncode == 1

    out = tmp_path / "state.json"
    status = _status(store, out, "--now", FROZEN, "--active-builds", str(builds))
    brief = _run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--active-builds", str(builds),
    )
    assert status.returncode == 0
    assert brief.returncode == 0
    readiness = _state(out)["readiness"]
    assert readiness == json.loads(brief.stdout)["readiness"]
    assert any("WS-GMI-THEME-GRAPH.md" in item
               for item in readiness["degraded"])
    records = {
        (item["workstream"], item["wave"]): item
        for item in readiness["records"]
    }
    assert ("GMI-THEME-GRAPH", None) not in records
    for identity in (("WATCHLIST-PORTFOLIO-CEO", None),
                     ("WATCHLIST-PORTFOLIO-CEO", "W1")):
        item = records[identity]
        assert item["state"] == "unknown"
        assert item["reason_code"] == "status_unknown"
        assert item["unmet_dependencies"] == ["WS:GMI-THEME-GRAPH"]
        assert "WS:GMI-THEME-GRAPH" in item["reason"]


def test_missing_readiness_dependency_fails_closed_but_view_stays_degraded(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    target = store / "workstreams" / "WS-WATCHLIST-PORTFOLIO-CEO.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "ambiguity: scoped\nwaves:",
            "ambiguity: scoped\ndepends_on: [WS:DOES-NOT-EXIST]\nwaves:",
            1,
        ),
        encoding="utf-8",
    )
    validated = _run("validate", "--root", str(store))
    assert validated.returncode == 1
    assert "dangling-ref" in validated.stdout

    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    readiness = _state(out)["readiness"]
    assert any("dangling-ref" in item for item in readiness["degraded"])
    assert readiness["records"], "unaffected readiness records must still emit"
    assert not any(
        item["workstream"] == "WATCHLIST-PORTFOLIO-CEO"
        for item in readiness["records"]
    )


# ------------------------------------------------------------- I1: no execution


def test_status_and_brief_always_exit_zero(store: Path, tmp_path: Path) -> None:
    """Nothing added here can block anything, including on a store full of garbage."""
    (store / "workstreams" / "WS-GARBAGE.md").write_text("not even frontmatter\n",
                                                         encoding="utf-8")
    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN).returncode == 0
    assert _run("brief", "--root", str(store), "--now", FROZEN,
                "--no-remember").returncode == 0


def test_generator_holds_no_gate_vocabulary() -> None:
    """A reviewer's check that I1 is structural: no dispatch/exec surface exists here."""
    source = GENERATOR.read_text(encoding="utf-8")
    for forbidden in ("subprocess.Popen", "os.execv", "os.system", "sys.exit(1)"):
        assert forbidden not in source, f"{forbidden} has no business in a knowledge plane"
    # The only subprocess use is local git, read-only.
    assert source.count("subprocess.run") == 1, "one local-git call site, no others"


# ----------------------------------------------------------------- zero network


NETWORK_MODULES = ("requests", "urllib.request", "urllib3", "http.client", "httpx", "aiohttp")


def test_no_network_module_is_imported_by_the_new_code_paths() -> None:
    """Static half: the module cannot reach the network because it never imports it."""
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import importlib; importlib.import_module('scripts.agentos');"
        "bad=[m for m in %r if m in sys.modules];"
        "print('LOADED:'+','.join(bad))" % (str(REPO), NETWORK_MODULES)
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            cwd=REPO)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LOADED:", (
        f"a network module reached sys.modules: {result.stdout}"
    )


def test_no_gh_invocation_in_the_generator() -> None:
    """PR state comes ONLY from the local active_builds.json."""
    source = GENERATOR.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("*"):
            continue
        assert '"gh"' not in stripped and "'gh'" not in stripped, (
            f"gh invocation found — the REST bucket is shared with ship_loop_guard.py: {line}"
        )


def test_status_completes_with_sockets_disabled(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """Runtime half: block the socket layer and the command must still succeed."""
    sitedir = tmp_path / "nonet"
    sitedir.mkdir()
    (sitedir / "sitecustomize.py").write_text(
        "import socket\n"
        "def _deny(*a, **k):\n"
        "    raise RuntimeError('network access attempted by a zero-network command')\n"
        "socket.socket = _deny\n"
        "socket.create_connection = _deny\n"
        "socket.getaddrinfo = _deny\n",
        encoding="utf-8",
    )
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds),
                     env={"PYTHONPATH": str(sitedir)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "network access attempted" not in (result.stdout + result.stderr)
    assert _state(out)["workstreams"]


# ------------------------------------------------- the record-vs-execution join


def test_merged_pr_under_an_unfinished_wave_is_reported(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """The join nothing else in the org performs.

    ABM knows PR state and never reads the record; the record knows the intent and never
    reads the PR.  A wave left `in_progress` behind a merged PR is invisible to both.
    """
    record = store / "workstreams" / "WS-PROPHET-US-ENTRY-TIMING.md"
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "    title: Queue drain + backfill\n    status: done",
            "    title: Queue drain + backfill\n    status: in_progress", 1),
        encoding="utf-8",
    )
    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN, "--active-builds", str(builds)).returncode == 0
    warnings = _state(out)["warnings"]
    assert any("record_disagrees_with_execution" in w and "#5370" in w for w in warnings), warnings


def test_wave_pr_absent_from_active_builds_is_reported(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    payload = json.loads(builds.read_text(encoding="utf-8"))
    payload["recent_merged"] = [m for m in payload["recent_merged"] if m["number"] != 5370]
    builds.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN, "--active-builds", str(builds)).returncode == 0
    warnings = _state(out)["warnings"]
    assert any("#5370" in w and "absent from active_builds.v1" in w for w in warnings), warnings


def test_staleness_comes_from_git_not_from_a_typed_field(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """`updated` is DERIVED; no record may still be carrying a hand-typed one."""
    for record in (STORE / "workstreams").glob("*.md"):
        head = record.read_text(encoding="utf-8").split("---", 2)[1]
        assert "\nupdated:" not in head, f"{record.name} still hand-types `updated`"
        assert "\ncreated:" not in head, f"{record.name} still hand-types `created`"
    out = tmp_path / "state.json"
    _status(STORE, out, "--now", FROZEN, "--active-builds", str(builds))
    rows = _state(out)["workstreams"]
    undated = [row["key"] for row in rows if not row["updated"]]
    assert not undated, f"git dates did not resolve for tracked workstreams: {undated}"


# ------------------------------------------------------- non-ranked readiness


READINESS_FIELDS = {
    "workstream", "wave", "state", "reason_code", "reason",
    "depends_on", "unmet_dependencies", "source",
}
READINESS_STATES = {"ready", "blocked", "in_progress", "done", "unknown"}
READINESS_REASON_CODES = {
    "dependencies_satisfied", "unmet_dependencies", "status_in_progress",
    "status_done", "workstream_blocked", "status_unknown",
}


def _identity(item: dict) -> tuple[str, bool, str]:
    return item["workstream"], item["wave"] is not None, item["wave"] or ""


def test_readiness_envelope_is_complete_canonical_and_identity_sorted(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    state = _state(out)
    readiness = state["readiness"]

    assert set(readiness) == {"schema", "records", "degraded"}
    assert readiness["schema"] == "agentos.readiness.v1"
    assert readiness["degraded"] == [], (
        "normal auxiliary join warnings must not masquerade as readiness degradation"
    )
    assert readiness["records"] == sorted(readiness["records"], key=_identity)

    expected_identities: list[tuple[str, str | None]] = []
    by_key = {row["key"]: row for row in state["workstreams"]}
    for row in state["workstreams"]:
        expected_identities.append((row["key"], None))
        expected_identities.extend((row["key"], wave["id"]) for wave in row["wave_detail"])
    actual_identities = [(item["workstream"], item["wave"])
                         for item in readiness["records"]]
    assert actual_identities == sorted(
        expected_identities,
        key=lambda identity: (identity[0], identity[1] is not None, identity[1] or ""),
    )

    for item in readiness["records"]:
        assert set(item) == READINESS_FIELDS
        assert item["state"] in READINESS_STATES
        assert item["reason_code"] in READINESS_REASON_CODES
        assert item["reason"]
        assert item["depends_on"] == sorted(set(item["depends_on"]))
        assert item["unmet_dependencies"] == sorted(set(item["unmet_dependencies"]))
        assert set(item["unmet_dependencies"]).issubset(item["depends_on"])
        row = by_key[item["workstream"]]
        expected = [f"WS:{dep}" for dep in row["depends_on"]]
        if item["wave"] is not None:
            wave = next(w for w in row["wave_detail"] if w["id"] == item["wave"])
            expected += [f"WS:{row['key']}#{dep}" for dep in wave["depends_on"]]
        assert item["depends_on"] == sorted(set(expected))
        assert item["source"] == row["source"]


def test_readiness_states_explain_graph_and_authored_progress(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    # The blocked-parent case is SYNTHESIZED: force GMI-THEME-GRAPH to blocked in the
    # fixture copy so the assertion no longer rides the live record's current status
    # (which legitimately flipped to active on 2026-08-17 and silently un-blocked it).
    parent = store / "workstreams" / "WS-GMI-THEME-GRAPH.md"
    parent_text = re.sub(
        r"(?m)^status: \S+",
        'status: blocked\nblocked_by:\n  - "fixture: parent held blocked for the readiness case"',
        parent.read_text(encoding="utf-8"),
        count=1,
    )
    parent.write_text(parent_text, encoding="utf-8")

    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    records = {
        (item["workstream"], item["wave"]): item
        for item in _state(out)["readiness"]["records"]
    }

    ready = records[("WATCHLIST-PORTFOLIO-CEO", "W1")]
    assert ready["state"] == "ready"
    assert ready["reason_code"] == "dependencies_satisfied"
    assert ready["unmet_dependencies"] == []

    waiting = records[("MACRO-CONTEXT-INDEX", "W2")]
    assert waiting["state"] == "blocked"
    assert waiting["reason_code"] == "unmet_dependencies"
    assert waiting["unmet_dependencies"] == ["WS:MACRO-CONTEXT-INDEX#W1"]

    parent_blocked = records[("GMI-THEME-GRAPH", "TRANSMISSION")]
    assert parent_blocked["state"] == "blocked"
    assert parent_blocked["reason_code"] == "workstream_blocked"
    assert parent_blocked["unmet_dependencies"] == []

    assert records[("MACRO-CONTEXT-INDEX", None)]["state"] == "in_progress"
    assert records[("GMI-THEME-GRAPH", "R1")]["state"] == "done"


def test_readiness_ignores_p0_claim_and_non_graph_join_inputs(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """Readiness is graph state, never a disguised priority or liveness ranking."""
    before = tmp_path / "before.json"
    assert _status(store, before, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0

    strategic = tmp_path / "mm" / "config"
    strategic.mkdir(parents=True)
    (strategic / "strategic_state.yml").write_text(
        "p0:\n  - id: PRODUCT_TRUST_COHERENCE\n    status: active\n", encoding="utf-8")
    record = store / "workstreams" / "WS-WATCHLIST-PORTFOLIO-CEO.md"
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "needs_ceo:",
            "claim:\n  by: claude/readiness-must-ignore-this\n  at: 2026-08-12T10:00:00Z\n"
            "  expires: 2026-08-15T10:00:00Z\nneeds_ceo:",
            1,
        ),
        encoding="utf-8",
    )
    after = tmp_path / "after.json"
    assert _status(
        store, after, "--now", FROZEN, "--active-builds", str(builds),
        env={"MACRO_MASTERMIND_REPO": str(tmp_path / "mm")},
    ).returncode == 0

    assert (_state(before)["readiness"]["records"]
            == _state(after)["readiness"]["records"])


def test_readiness_maps_every_authored_status_and_keeps_unknown_fail_soft() -> None:
    agentos = _load_cli()

    workstream_states = {
        "proposed": ("ready", "dependencies_satisfied"),
        "active": ("in_progress", "status_in_progress"),
        "blocked": ("blocked", "workstream_blocked"),
        "awaiting_ci": ("in_progress", "status_in_progress"),
        "awaiting_review": ("in_progress", "status_in_progress"),
        "done": ("done", "status_done"),
        "parked": ("blocked", "workstream_blocked"),
        "killed": ("done", "status_done"),
    }
    assert set(workstream_states) == agentos.WORKSTREAM_STATUS
    for status, (expected_state, expected_reason) in workstream_states.items():
        envelope = agentos.compute_readiness([{
            "key": "SAMPLE",
            "status": status,
            "depends_on": [],
            "wave_detail": [],
            "source": "agentos/workstreams/WS-SAMPLE.md",
        }])
        item = envelope["records"][0]
        assert (item["state"], item["reason_code"]) == (
            expected_state, expected_reason
        ), status

    wave_states = {
        "todo": ("ready", "dependencies_satisfied"),
        "in_progress": ("in_progress", "status_in_progress"),
        "awaiting_ci": ("in_progress", "status_in_progress"),
        "done": ("done", "status_done"),
        "dropped": ("done", "status_done"),
    }
    assert set(wave_states) == agentos.WAVE_STATUS
    for status, (expected_state, expected_reason) in wave_states.items():
        envelope = agentos.compute_readiness([{
            "key": "SAMPLE",
            "status": "active",
            "depends_on": [],
            "wave_detail": [{"id": "W0", "status": status, "depends_on": []}],
            "source": "agentos/workstreams/WS-SAMPLE.md",
        }])
        wave = next(item for item in envelope["records"] if item["wave"] == "W0")
        assert (wave["state"], wave["reason_code"]) == (
            expected_state, expected_reason
        ), status

    for record in (
        {"key": "SAMPLE", "status": "not-a-schema-status", "depends_on": [],
         "wave_detail": [], "source": "agentos/workstreams/WS-SAMPLE.md"},
        {"key": "SAMPLE", "status": "active", "depends_on": [],
         "wave_detail": [{"id": "W0", "status": "not-a-schema-status",
                          "depends_on": []}],
         "source": "agentos/workstreams/WS-SAMPLE.md"},
    ):
        unknown = next(
            item for item in agentos.compute_readiness([record])["records"]
            if (record["status"] != "active" and item["wave"] is None)
            or (record["status"] == "active" and item["wave"] == "W0")
        )
        assert (unknown["state"], unknown["reason_code"]) == (
            "unknown", "status_unknown"
        )


def test_phase2b_closeout_makes_w4_eligible_without_starting_it(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """The deployed E2E closes W2B; it does not silently begin the hook wave."""
    agentos = _load_cli()
    authored, _ = agentos.parse_record(
        store / "workstreams" / "WS-AGENT-OS.md"
    )
    waves = {wave["id"]: wave for wave in authored["waves"]}
    assert waves["W2B"]["status"] == "done"
    assert waves["W2B"]["pr"] == 5649
    assert waves["W4"]["status"] == "todo"
    assert waves["W4"]["depends_on"] == ["W1", "W2", "W2B"]

    output = tmp_path / "closed.json"
    assert _status(
        store, output, "--now", FROZEN, "--active-builds", str(builds)
    ).returncode == 0
    readiness = {
        (item["workstream"], item["wave"]): item
        for item in _state(output)["readiness"]["records"]
    }
    assert (
        readiness[("AGENT-OS", "W2B")]["state"],
        readiness[("AGENT-OS", "W2B")]["reason_code"],
    ) == ("done", "status_done")
    assert (
        readiness[("AGENT-OS", "W4")]["state"],
        readiness[("AGENT-OS", "W4")]["reason_code"],
        readiness[("AGENT-OS", "W4")]["unmet_dependencies"],
    ) == ("ready", "dependencies_satisfied", [])


def test_terminal_records_keep_dependencies_but_report_no_unmet_dependencies() -> None:
    agentos = _load_cli()
    records = [{
        "key": "UPSTREAM",
        "status": "active",
        "depends_on": [],
        "wave_detail": [{"id": "W0", "status": "todo", "depends_on": []}],
        "source": "agentos/workstreams/WS-UPSTREAM.md",
    }, {
        "key": "TERMINAL",
        "status": "done",
        "depends_on": ["UPSTREAM"],
        "wave_detail": [
            {"id": "W-DONE", "status": "done", "depends_on": ["W-MISSING"]},
            {"id": "W-DROPPED", "status": "dropped", "depends_on": ["W-MISSING"]},
        ],
        "source": "agentos/workstreams/WS-TERMINAL.md",
    }, {
        "key": "KILLED",
        "status": "killed",
        "depends_on": ["UPSTREAM"],
        "wave_detail": [],
        "source": "agentos/workstreams/WS-KILLED.md",
    }]
    terminal = {
        (item["workstream"], item["wave"]): item
        for item in agentos.compute_readiness(records)["records"]
        if item["workstream"] in {"TERMINAL", "KILLED"}
    }

    for item in terminal.values():
        assert item["state"] == "done"
        assert item["reason_code"] == "status_done"
        assert item["depends_on"], "authored graph provenance must remain visible"
        assert item["unmet_dependencies"] == []
    assert "killed" in terminal[("KILLED", None)]["reason"]


def test_brief_and_status_retire_every_ranked_readiness_surface(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    status_out = tmp_path / "state.json"
    assert _status(store, status_out, "--now", FROZEN,
                   "--active-builds", str(builds)).returncode == 0
    state = _state(status_out)
    assert "unblocked" not in state
    status_markdown = status_out.with_suffix(".md").read_text(encoding="utf-8")
    assert "## Unblocked work" not in status_markdown

    text = _run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember",
        "--active-builds", str(builds),
    ).stdout
    assert "━━ UNBLOCKED" not in text
    assert "READY TO START" not in text
    assert "START NEXT" not in text

    brief = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--active-builds", str(builds),
    ).stdout)
    assert "unblocked" not in brief
    assert "unblocked_scope" not in brief
    assert brief["readiness"] == state["readiness"]


# ------------------------------------------------- stale sibling checkout (2026-08-13)


def _git_in(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """git inside a throwaway clone, identity pinned so a bare host config cannot fail it."""
    return subprocess.run(
        ["git",
         "-c", "user.email=agentos-tests@example.invalid",
         "-c", "user.name=agentos tests",
         "-c", "commit.gpgsign=false",
         *args],
        cwd=str(repo), check=True, capture_output=True, text=True,
    )


def _stale_mastermind(tmp_path: Path) -> Path:
    """A Mastermind clone whose WORKING TREE predates ``config/strategic_state.yml``.

    The live 2026-08-13 shape: local `master` sat 43 commits behind while
    `refs/remotes/origin/master` already carried the file — and nothing here may fetch
    to find that out.
    """
    mm = tmp_path / "Mastermind"
    mm.mkdir()
    _git_in(mm, "init", "-b", "master")
    (mm / "README.md").write_text("Mastermind\n", encoding="utf-8")
    _git_in(mm, "add", "README.md")
    _git_in(mm, "commit", "-m", "base")
    (mm / "config").mkdir()
    (mm / "config" / "strategic_state.yml").write_text(
        "p0:\n  - id: US_PROPHET_ENTRY_TIMING\n    status: active\n", encoding="utf-8")
    _git_in(mm, "add", "config/strategic_state.yml")
    _git_in(mm, "commit", "-m", "strategic state")
    head = _git_in(mm, "rev-parse", "HEAD").stdout.strip()
    _git_in(mm, "update-ref", "refs/remotes/origin/master", head)
    # The worktree goes back before the file; origin/master keeps it.
    _git_in(mm, "reset", "--hard", "HEAD~1")
    return mm


def test_stale_mastermind_worktree_reads_p0_from_a_local_ref(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """A checkout parked behind must not discard P0 activity it can still read.

    The state is in the clone on a local ref; degrading over which branch that clone
    happens to be sitting on discards a P0 join that costs one fetch-free `git show`.
    """
    mm = _stale_mastermind(tmp_path)
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds),
                     env={"MACRO_MASTERMIND_REPO": str(mm)})
    assert result.returncode == 0, result.stdout + result.stderr
    state = _state(out)
    row = next(r for r in state["workstreams"] if r["p0"] == "US_PROPHET_ENTRY_TIMING")
    assert row["p0_active"] is True, "the ref copy marks this objective active"
    degraded = state["inputs"]["degraded"]
    assert any("read from local ref origin/master" in item for item in degraded), degraded
    assert not any("strategic_state.yml" in item and "p0_active unknown" in item
                   for item in degraded), (
        "p0_active is known once the ref copy is read", degraded)


def test_strategic_state_absent_from_every_local_ref_neutralises_p0(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """A clone that genuinely predates the file: the old degrade is still the right answer."""
    mm = tmp_path / "Mastermind"
    mm.mkdir()
    _git_in(mm, "init", "-b", "master")
    (mm / "README.md").write_text("Mastermind\n", encoding="utf-8")
    _git_in(mm, "add", "README.md")
    _git_in(mm, "commit", "-m", "base")
    _git_in(mm, "update-ref", "refs/remotes/origin/master",
            _git_in(mm, "rev-parse", "HEAD").stdout.strip())
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds),
                     env={"MACRO_MASTERMIND_REPO": str(mm)})
    assert result.returncode == 0, result.stdout + result.stderr
    state = _state(out)
    row = next(r for r in state["workstreams"] if r["p0"] == "US_PROPHET_ENTRY_TIMING")
    assert row["p0_active"] is None
    degraded = state["inputs"]["degraded"]
    assert any("all local refs" in item and "p0_active unknown" in item
               for item in degraded), degraded


def test_mastermind_dir_without_git_refs_neutralises_p0(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    """A sibling path that is not a checkout at all — the fallback must say so, not crash."""
    mm = tmp_path / "Mastermind"
    mm.mkdir()
    (mm / "README.md").write_text("not a checkout\n", encoding="utf-8")
    out = tmp_path / "state.json"
    result = _status(store, out, "--now", FROZEN, "--active-builds", str(builds),
                     env={"MACRO_MASTERMIND_REPO": str(mm)})
    assert result.returncode == 0, result.stdout + result.stderr
    state = _state(out)
    row = next(r for r in state["workstreams"] if r["p0"] == "US_PROPHET_ENTRY_TIMING")
    assert row["p0_active"] is None
    degraded = state["inputs"]["degraded"]
    assert any("no readable git refs" in item and "p0_active unknown" in item
               for item in degraded), degraded


# ------------------------------------------------------------------- claims


def test_expired_claim_reports_unclaimed_and_blocks_nothing(
    store: Path, builds: Path, tmp_path: Path
) -> None:
    record = store / "workstreams" / "WS-MACRO-CONTEXT-INDEX.md"
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "landmines:",
            "claim:\n  by: claude/long-gone\n  at: 2026-01-01\n"
            "  expires: 2026-01-02\nlandmines:", 1),
        encoding="utf-8",
    )
    out = tmp_path / "state.json"
    assert _status(store, out, "--now", FROZEN, "--active-builds", str(builds)).returncode == 0
    state = _state(out)
    row = next(r for r in state["workstreams"] if r["key"] == "MACRO-CONTEXT-INDEX")
    assert row["claim"]["stale"] is True
    assert row["claim"]["worktree_live"] is False


# -------------------------------------------------------- house annotation law


def test_annotations_start_the_line(store: Path, tmp_path: Path) -> None:
    """Emitted by a bare print or GitHub silently drops them (five prior incidents)."""
    result = _status(store, tmp_path / "state.json", "--now", FROZEN,
                     "--active-builds", str(tmp_path / "missing.json"))
    annotations = [ln for ln in result.stdout.splitlines()
                   if "::warning" in ln or "::error" in ln]
    assert annotations, "a degraded input emitted no annotation"
    for line in annotations:
        assert line.startswith("::"), f"annotation does not start the line: {line!r}"


# ------------------------------------------------------------------ brief shape


def test_brief_json_is_the_documented_schema(store: Path, builds: Path) -> None:
    payload = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--active-builds", str(builds),
    ).stdout)
    assert payload["schema"] == "ceo_brief.v1"
    for field in ("generated_at", "since", "counts", "inputs", "needs_ceo", "blocked",
                  "finished", "readiness", "warnings"):
        assert field in payload, f"ceo_brief.v1 is missing {field}"
    assert "unblocked" not in payload
    assert "unblocked_scope" not in payload
    assert payload["readiness"]["schema"] == "agentos.readiness.v1"
    for field in ("total", "active", "awaiting_ci", "blocked", "done_in_window"):
        assert field in payload["counts"]


def test_brief_finished_window_uses_merge_time_not_a_typed_field(
    store: Path, builds: Path
) -> None:
    """FINISHED is windowed on the PR's merged_at, so it cannot be gamed by a record."""
    wide = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--since", "30d", "--active-builds", str(builds),
    ).stdout)
    narrow = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--since", "1h", "--active-builds", str(builds),
    ).stdout)
    assert wide["counts"]["done_in_window"] > narrow["counts"]["done_in_window"]
    assert narrow["counts"]["done_in_window"] == 0
    assert all(item["done_at"] for item in wide["finished"])


def test_brief_needs_ceo_is_authored_never_inferred(store: Path, builds: Path) -> None:
    """Escalation is a declared field.  Nothing heuristic may promote a workstream."""
    payload = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--active-builds", str(builds),
    ).stdout)
    authored = {
        path.stem[3:] for path in (store / "workstreams").glob("*.md")
        if "needs_ceo:" in path.read_text(encoding="utf-8")
    }
    assert {item["workstream"] for item in payload["needs_ceo"]} == authored


def test_brief_does_not_write_the_check_in_marker_when_asked_not_to(
    store: Path, builds: Path
) -> None:
    marker = REPO / "data" / "governance" / ".ceo_brief_last"
    before = marker.read_bytes() if marker.exists() else None
    _run("brief", "--root", str(store), "--now", FROZEN, "--no-remember",
         "--active-builds", str(builds))
    after = marker.read_bytes() if marker.exists() else None
    assert before == after


# ---------------------------------------------------------------- brief correctness
#
# Three defects found by adversarial review of the first Phase 2 build.  Each test below
# FAILED on the code as originally written; they pin the fix, not the wording.


def _load_cli():
    """Import scripts/agentos.py as a module so pure helpers can be unit-tested."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("agentos_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recommendation_never_marks_an_option_it_rejects() -> None:
    """The arrow is what the CEO acts on, so a wrong arrow is worse than none.

    The original test was `option in recommendation` — a substring match — so prose that
    names an option in order to REJECT it ("Ship now, rejecting Wait for the nightly")
    marked both options as recommended.
    """
    agentos = _load_cli()

    options = ["Ship the fix now", "Wait for the nightly"]

    # The rejected option is named in the prose; only the opening option may be marked.
    assert agentos._recommended_option(
        options, "Ship the fix now, rejecting the option to Wait for the nightly."
    ) == "Ship the fix now"

    # Prose that opens with neither option designates nothing — no arrow at all.
    assert agentos._recommended_option(
        options, "Side with the census on both, for the reasons below."
    ) is None

    # Trailing punctuation and whitespace must not defeat the match.
    assert agentos._recommended_option(
        ["Single positions table"], "  Single positions table.  Migration cost is zero."
    ) == "Single positions table"

    assert agentos._recommended_option(options, "") is None


def test_capped_sections_say_what_they_dropped() -> None:
    """Silent truncation reads exactly like 'there were only N' — the CEO cannot tell."""
    agentos = _load_cli()

    out: list[str] = []
    agentos._overflow(out, total=7, shown=5, noun="blocked")
    assert out == ["    … +2 more blocked (--full)"]

    out = []
    agentos._overflow(out, total=5, shown=5, noun="blocked")
    assert out == [], "nothing was dropped, so nothing may be announced"


def test_ceo_brief_envelope_keys_match_the_spec(store: Path, builds: Path) -> None:
    """Every section names its workstream the same way — `needs_ceo` diverged alone."""
    payload = json.loads(_run(
        "brief", "--root", str(store), "--now", FROZEN, "--no-remember", "--json",
        "--active-builds", str(builds),
    ).stdout)
    for section in ("needs_ceo", "blocked", "finished"):
        for item in payload[section]:
            assert "workstream" in item, f"{section} item lacks 'workstream': {sorted(item)}"
            assert "key" not in item, f"{section} item still emits legacy 'key': {sorted(item)}"
    for item in payload["blocked"]:
        assert "record_stale_days" in item, "blocked must not claim an unmeasured block age"
        assert "blocked_days" not in item
