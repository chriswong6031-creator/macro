"""Owner-produced content identity for direct Agent OS source records."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "scripts" / "agentos.py"


def _load_agentos():
    spec = importlib.util.spec_from_file_location("agentos_source_digest", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    records = repo / "agentos"
    target = records / "workstreams" / "WS-TARGET.md"
    other = records / "workstreams" / "WS-OTHER.md"
    clock = records / "discoveries" / "DSC-CLOCK.md"
    target.parent.mkdir(parents=True)
    clock.parent.mkdir(parents=True)
    target.write_bytes(b"target-v1\n")
    other.write_bytes(b"other-v1\n")
    clock.write_bytes(b"clock-v1\n")
    return repo, records, target, clock


def _context_store(agentos, records: Path, target: Path, clock: Path):
    other = records / "workstreams" / "WS-OTHER.md"
    store = agentos.Store(records)
    store.records = {
        "WS/TARGET": {
            "key": "TARGET",
            "title": "Target",
            "objective": "Prove direct-record identity.",
            "status": "active",
            "program": None,
            "repos": ["macro"],
            "owner": "sol",
            "class": "build",
            "blast_radius": "reversible",
            "ambiguity": "specified",
            "waves": [],
            "next_action": "Run the identity proof.",
            "depends_on": [],
            "decisions": [],
            "discoveries": ["DSC:CLOCK"],
            "artifacts": [],
            "owns_paths": [],
            "landmines": [],
            "do_not_redo": [],
            "_body": "Target body.",
        },
        "WS/OTHER": {
            "key": "OTHER",
            "title": "Other",
            "status": "active",
            "program": None,
            "repos": ["macro"],
            "_body": "Unrelated body.",
        },
        "DSC/CLOCK": {
            "key": "CLOCK",
            "kind": "runtime",
            "claim": "The source bytes are unchanged.",
            "so_what": "Acquisition clocks must not move content identity.",
            "confidence": "verified",
            "verified_at": "2026-01-01",
            "expires": "2026-06-01",
            "scope": ["TARGET"],
            "falsifier": "Change the authored bytes.",
            "_body": "Clock body.",
        },
    }
    store.paths = {
        "WS/TARGET": target,
        "WS/OTHER": other,
        "DSC/CLOCK": clock,
    }
    store.counts = {
        "workstreams": 2,
        "decisions": 0,
        "discoveries": 1,
        "handoffs": 0,
    }
    return store


def test_digest_envelope_is_order_independent_and_binds_path_and_exact_bytes(
    tmp_path: Path,
) -> None:
    """Removing sorting, the path, or the exact file hash must change this literal."""
    agentos = _load_agentos()
    repo, _records, target, clock = _source_tree(tmp_path)

    digest = agentos._source_records_digest([target, clock], repository_root=repo)

    assert digest == "sha256:bdc09aa0ca00d32f39423fd1049f03930b811b000373960d9228251e8b5161a6"
    assert agentos._source_records_digest(
        [clock, target], repository_root=repo
    ) == digest
    target.write_bytes(b"target-v2\n")
    assert agentos._source_records_digest(
        [target, clock], repository_root=repo
    ) == "sha256:61b1b11fa25e4d866871429f5e82c1583245eb3733c64d977ce8914c235f50e5"


def test_state_projects_every_direct_record_into_the_pure_contract(tmp_path: Path) -> None:
    """Omitting a direct file or PURE_SECTIONS membership must fail this contract."""
    agentos = _load_agentos()
    _repo, records, _target, _clock = _source_tree(tmp_path)
    store = agentos.Store(records)
    now = agentos._parse_moment("2026-01-01T00:00:00Z")
    assert now is not None

    state = agentos.build_state(
        store,
        now=now,
        degraded=agentos.Degraded(),
        builds=None,
        p0_status=None,
        worktrees={"count": 0, "branches": [], "uncommitted": []},
    )

    expected = "sha256:41bacffd3a25258ac30ecacd9d5eb75e25c74370c92ab11549863173f9f4e3aa"
    assert state["source_records_digest"] == expected
    assert agentos.pure_section(state)["source_records_digest"] == expected


def test_context_digest_tracks_candidates_not_clock_filter_or_unrelated_records(
    tmp_path: Path,
) -> None:
    """Expiry movement may move projection rows, never the candidate-source identity."""
    agentos = _load_agentos()
    _repo, records, target, clock = _source_tree(tmp_path)
    store = _context_store(agentos, records, target, clock)
    before_bytes = {
        path: path.read_bytes()
        for path in (target, clock, records / "workstreams" / "WS-OTHER.md")
    }
    january = agentos._parse_moment("2026-01-01T00:00:00Z")
    july = agentos._parse_moment("2026-07-01T00:00:00Z")
    assert january is not None and july is not None

    fresh = agentos.compile_bundle(store, workstream="TARGET", now=january)
    expired = agentos.compile_bundle(store, workstream="TARGET", now=july)

    expected = "sha256:bdc09aa0ca00d32f39423fd1049f03930b811b000373960d9228251e8b5161a6"
    assert fresh["source_records_digest"] == expected
    assert expired["source_records_digest"] == expected
    assert any(row["key"] == "DSC:CLOCK" for row in expired["excluded"])
    assert all(path.read_bytes() == value for path, value in before_bytes.items())

    target.write_bytes(b"target-v2\n")
    changed = agentos.compile_bundle(store, workstream="TARGET", now=july)
    assert changed["source_records_digest"] == (
        "sha256:61b1b11fa25e4d866871429f5e82c1583245eb3733c64d977ce8914c235f50e5"
    )
