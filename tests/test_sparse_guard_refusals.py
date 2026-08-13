"""Seven guards must refuse a VACUOUS pass on a sparse tree — scripts/sparse_guard.py.

Session worktrees are sparse by default (policy R8): `data/`, `site/`, `mockups/`
and `verify_shots/` are omitted from the cone. Every guard below enumerates its
own work set by walking one of those trees, so in a session worktree each one
found ZERO items, could not tell that from a clean result, and printed an
affirmative OK with exit 0. Measured in a sparse worktree on 2026-08-13, before
this change — all seven exited 0:

    check_site_js              "OK — all standalone JS bundles under site/ parse cleanly."
    check_nav_gap              "OK — every menu page under site/ keeps a ≥14px top gap."
    check_nav_mega             "OK — every shared-nav page carries the Research mega-menu."
    check_badge_passport       "OK: site dir <abs>/site absent (nothing rendered yet)."
    check_cycle_consistency    "CYCLE-CONSISTENCY: PASS — 0 same-tape group(s) agree…"
    check_ms_board_coherence   "ms-board coherence: OK (0 page(s) scanned)"
    check_ohlc_basis_coherence "…nothing to check" (after WRITING its marker)

WHAT IS PINNED, AND WHY EACH HALF MATTERS
-----------------------------------------
The refusal is conditional on the CONJUNCTION — zero items checked AND a tree the
guard reads is sparse-omitted. So every guard carries four cases here, and the
last two are what keep this from degrading into a blanket "refuse whenever site/
is missing" entry guard:

  * empty result + SPARSE tree -> REFUSES, naming the opt-in command;
  * real items + FULL tree     -> passes, unchanged;
  * empty result + FULL tree   -> passes (an honest zero is still a zero);
  * real items + SPARSE tree   -> passes (work was really inspected).

HOW THESE RUN THE SAME IN A SPARSE WORKTREE AND IN FULL CI
----------------------------------------------------------
Every assertion is made against a SYNTHETIC git repo in tmp_path that is sparsed
with REAL `git sparse-checkout` cone mode, and the modules' repo roots are
redirected at it — so the ambient checkout's own sparseness never decides a
verdict. Faking sparseness by deleting directories would not reproduce this at
all: `data/` measurably survives as a 0-byte husk, `is_dir()` lies in both
directions, and the detector deliberately answers from git's sparse state rather
than from directory presence.

Nothing here mirrors a constant or re-implements the predicate: the remedy string
is asserted through `worktree_sparse.FULL_CHECKOUT_CMD`, and every verdict comes
from calling the guard's own entry point.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import check_badge_passport as badge
from scripts import check_cycle_consistency as ccc
from scripts import check_ms_board_coherence as ms
from scripts import check_nav_gap as nav_gap
from scripts import check_nav_mega as nav_mega
from scripts import check_ohlc_basis_coherence as ohlc
from scripts import check_site_js as site_js
from scripts import sparse_guard as SG
from scripts import worktree_sparse as WS

_HAS_NODE = shutil.which("node") is not None


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(("git", "-C", str(repo)) + args,
                          capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repo carrying the heavy trees, so sparseness is exercised for real."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    for name in ("scripts", "site", "data"):
        d = r / name
        d.mkdir()
        # Not an item for ANY of the seven (no .html/.js/.json, no cache triple),
        # so a full tree with only this in it is a genuinely EMPTY result set.
        (d / "keep.txt").write_text(f"{name}\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _make_sparse(repo: Path) -> None:
    """Omit site/ and data/ for real — the profile a session worktree gets."""
    _git(repo, "sparse-checkout", "init", "--cone")
    _git(repo, "sparse-checkout", "set", "--cone", "--", "scripts")
    assert set(WS.missing_dirs(repo)) == {"site", "data"}, "fixture is not actually sparse"


def _redirect(monkeypatch, repo: Path) -> None:
    """Point every module-level repo root at the synthetic repo.

    The guards resolve their sparse check against `sparse_guard.ROOT`, and two of
    them additionally anchor their own paths on `_ROOT` / `SITE_DIR`. Redirecting
    all of them is what lets the REAL functions run against a REAL sparse git repo
    rather than against this checkout.
    """
    monkeypatch.setattr(SG, "ROOT", repo)
    monkeypatch.setattr(badge, "_ROOT", repo)
    monkeypatch.setattr(ms, "ROOT", repo)
    monkeypatch.setattr(ms, "SITE_DIR", repo / "site")


# ── per-guard fixtures: how to give each one exactly ONE real item ───────────

_PAGE = "<html><body><p>a page with no shared nav</p></body></html>\n"


def _items_site_js(repo: Path) -> None:
    (repo / "site").mkdir(exist_ok=True)
    (repo / "site" / "bundle.js").write_text("console.log(1);\n", encoding="utf-8")


def _items_page(repo: Path) -> None:
    (repo / "site").mkdir(exist_ok=True)
    (repo / "site" / "page.html").write_text(_PAGE, encoding="utf-8")


def _items_badge(repo: Path) -> None:
    (repo / "site").mkdir(exist_ok=True)
    (repo / "site" / "desk.json").write_text(json.dumps({
        "schema": "ai_desk", "conviction": "high",
        "passport": {"state": "measured"},
    }), encoding="utf-8")


def _items_cycle(repo: Path) -> None:
    d = repo / "site" / "countrycyclesdata"
    d.mkdir(parents=True, exist_ok=True)
    (d / "country_cycles.json").write_text(json.dumps({
        "EWJ": {"ticker": "EWJ",
                "now": {"pos_v2": 51.0, "phase_v2": "Expansion", "basis": "etf_tr"}},
    }), encoding="utf-8")


def _items_ohlc(repo: Path) -> None:
    import pandas as pd

    d = repo / "data" / "breadth"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2024-01-01", periods=8, freq="B")
    base = pd.Series(100.0, index=idx)
    for field, frame in (("closes", base), ("high", base * 1.02), ("low", base * 0.98)):
        pd.DataFrame({"AAA": frame}).to_parquet(d / f"_{field}_cache.parquet")


# ── per-guard invocation: the REAL entry point, and its non-zero refusal code ──

def _run_site_js(repo: Path) -> int:
    return site_js.main([str(repo / "site")])


def _run_nav_gap(repo: Path) -> int:
    return nav_gap.main([str(repo / "site")])


def _run_nav_mega(repo: Path) -> int:
    return nav_mega.main([str(repo / "site")])


def _run_badge(repo: Path) -> int:
    return badge.main([str(repo / "site")])


def _run_cycle(repo: Path) -> int:
    return ccc.main([str(repo / "site")])


def _run_ms(repo: Path) -> int:
    return ms.main([])


def _run_ohlc(repo: Path) -> int:
    return ohlc.run(repo / "data")


# id -> (populate one real item, invoke, exit code the refusal returns)
GUARDS = {
    "check_site_js": (_items_site_js, _run_site_js, 1),
    "check_nav_gap": (_items_page, _run_nav_gap, 1),
    "check_nav_mega": (_items_page, _run_nav_mega, 1),
    "check_badge_passport": (_items_badge, _run_badge, 1),
    "check_cycle_consistency": (_items_cycle, _run_cycle, 1),
    "check_ms_board_coherence": (_items_page, _run_ms, 1),
    # 2 is this guard's "could not evaluate" code; 3 means a split was found and
    # would be a lie about a tree it never read.
    "check_ohlc_basis_coherence": (_items_ohlc, _run_ohlc, 2),
}

ALL_GUARDS = sorted(GUARDS)
# check_site_js shells out to `node --check` on its pass paths; its REFUSAL path
# (the mutation-critical one) is hermetic and never skips.
NODE_GUARDS = {"check_site_js"}


def _commit_items(repo: Path, populate) -> None:
    populate(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "items")


def _needs_node(name: str) -> None:
    if name in NODE_GUARDS and not _HAS_NODE:
        pytest.skip("`node` not on PATH — this guard shells out to `node --check`")


# ── 1. the bug: empty result set on a sparse tree must REFUSE ────────────────

@pytest.mark.parametrize("name", ALL_GUARDS)
def test_guard_refuses_a_vacuous_pass_on_a_sparse_tree(name, repo, monkeypatch, capsys):
    """The tree HAS content at HEAD and is simply not materialized — the exact
    session-worktree shape. Zero items must not read as zero problems."""
    populate, invoke, want_rc = GUARDS[name]
    _commit_items(repo, populate)
    _make_sparse(repo)
    _redirect(monkeypatch, repo)

    rc = invoke(repo)
    out = capsys.readouterr()
    blob = out.out + out.err

    assert rc == want_rc, f"{name} did not refuse (rc={rc}); output:\n{blob}"
    assert WS.FULL_CHECKOUT_CMD in blob, (
        f"{name} refused without naming the opt-in command:\n{blob}")


@pytest.mark.parametrize("name", ALL_GUARDS)
def test_refusal_emits_a_github_annotation_at_line_start(name, repo, monkeypatch, capsys):
    """GitHub only parses a workflow command when `::` opens the line — a refusal
    routed through a logger would be silently dropped from the Actions summary."""
    populate, invoke, _ = GUARDS[name]
    _commit_items(repo, populate)
    _make_sparse(repo)
    _redirect(monkeypatch, repo)

    invoke(repo)
    out = capsys.readouterr()
    errors = [ln for ln in (out.out + out.err).splitlines() if "::error" in ln]
    assert errors, f"{name} refused with no ::error annotation"
    assert any(ln.startswith("::error") for ln in errors), (
        f"{name} emitted its annotation mid-line, so GitHub will drop it: {errors}")


# ── 2. the guard still works: real items on a full tree PASS ─────────────────

@pytest.mark.parametrize("name", ALL_GUARDS)
def test_guard_passes_on_a_full_tree_with_real_items(name, repo, monkeypatch, capsys):
    _needs_node(name)
    populate, invoke, _ = GUARDS[name]
    _commit_items(repo, populate)
    _redirect(monkeypatch, repo)
    assert WS.missing_dirs(repo) == [], "precondition: the fixture is a FULL checkout"

    rc = invoke(repo)
    out = capsys.readouterr()
    assert rc == 0, f"{name} failed on a clean full fixture (rc={rc}):\n{out.out + out.err}"


# ── 3. the two cases that stop this becoming a blanket entry guard ───────────

@pytest.mark.parametrize("name", ALL_GUARDS)
def test_empty_result_on_a_full_tree_still_passes(name, repo, monkeypatch, capsys):
    """An honest zero is still a zero. Nothing is populated here, so every guard
    checks nothing — and a full checkout must NOT be refused for that."""
    _needs_node(name)
    _, invoke, _ = GUARDS[name]
    _redirect(monkeypatch, repo)
    assert WS.missing_dirs(repo) == [], "precondition: the fixture is a FULL checkout"

    rc = invoke(repo)
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, f"{name} refused an honest empty result in a full tree:\n{blob}"
    assert WS.FULL_CHECKOUT_CMD not in blob, f"{name} named the sparse remedy in a full tree"


@pytest.mark.parametrize("name", ALL_GUARDS)
def test_real_items_on_a_sparse_tree_still_pass(name, repo, monkeypatch, capsys):
    """Work really WAS inspected, so sparseness alone must not refuse.

    The items are written back into the omitted tree after sparsing — a stray
    write, which is precisely how a guard can still have something to look at
    while git's cone says the tree is not checked out.
    """
    _needs_node(name)
    populate, invoke, _ = GUARDS[name]
    _commit_items(repo, populate)
    _make_sparse(repo)
    populate(repo)  # stray write: content on disk, tree still cone-omitted
    _redirect(monkeypatch, repo)
    assert set(WS.missing_dirs(repo)) == {"site", "data"}, (
        "precondition: git still reports both trees omitted")

    rc = invoke(repo)
    out = capsys.readouterr()
    blob = out.out + out.err
    assert rc == 0, f"{name} refused despite finding real items:\n{blob}"
    assert WS.FULL_CHECKOUT_CMD not in blob, (
        f"{name} named the sparse remedy on a run that inspected real items")


# ── 3b. the husk: a site/ that EXISTS and holds nothing ─────────────────────

def test_badge_passport_refuses_over_a_husk_site_dir(repo, monkeypatch, capsys):
    """`check_badge_passport` has a SECOND vacuity exit, and it needs its own kill.

    The guard returns early on `not site_dir.exists()`, so the sparse fixture above
    never reaches the zero-briefs path. `git reset --hard` in a sparse tree leaves
    `site/` behind as a 0-entry HUSK — `exists()` is then True, `scan()` still finds
    nothing, and the ratchet reports green over an empty tree by the other door.
    Without this case that refusal could be deleted with every other test still green.
    """
    _commit_items(repo, _items_badge)
    _make_sparse(repo)
    (repo / "site").mkdir(exist_ok=True)  # the husk
    _redirect(monkeypatch, repo)
    assert (repo / "site").is_dir(), "precondition: the husk exists on disk"
    assert not any((repo / "site").iterdir()), "precondition: and it holds nothing"

    rc = badge.main([str(repo / "site")])
    blob = "".join(capsys.readouterr())
    assert rc == 1, f"husk site/ passed the ratchet vacuously:\n{blob}"
    assert WS.FULL_CHECKOUT_CMD in blob


# ── 4. the shared helper's own contract ─────────────────────────────────────

def test_refuse_if_vacuous_needs_both_halves(repo, monkeypatch):
    """Neither half alone is evidence of a lie; only the conjunction is."""
    _make_sparse(repo)
    monkeypatch.setattr(SG, "ROOT", repo)

    assert SG.refuse_if_vacuous(0, ["site"], "t") is not None, "empty + omitted must refuse"
    assert SG.refuse_if_vacuous(1, ["site"], "t") is None, "items found -> proceed"
    assert SG.refuse_if_vacuous(0, ["scripts"], "t") is None, "present tree -> proceed"
    assert SG.refuse_if_vacuous(0, [], "t") is None, "no tree needed -> proceed"


def test_trees_for_ignores_paths_outside_the_checkout(repo, tmp_path, monkeypatch):
    """A guard pointed at a scratch directory must not inherit this repo's sparseness."""
    monkeypatch.setattr(SG, "ROOT", repo)
    assert SG.trees_for(repo / "site") == ["site"]
    assert SG.trees_for(repo / "site" / "sub" / "deep.html") == ["site"]
    assert SG.trees_for(tmp_path / "elsewhere") == []
    assert SG.trees_for(repo) == [], "the root itself is not a top-level tree"


def test_detector_never_breaks_a_guard(monkeypatch):
    """Every failure mode of the detector answers None, so a guard runs normally.

    The profile module can legitimately be absent (this change may land before or
    after the sparse-profile PR), git may be missing, HEAD may be unreadable.
    None of those may be the thing that reds a lane.
    """
    def boom(*_a, **_k):
        raise RuntimeError("git exploded")

    monkeypatch.setattr(WS, "missing_dirs", boom)
    assert SG.sparse_refusal(["site"]) is None
    assert SG.refuse_if_vacuous(0, ["site"], "t") is None


def test_every_wired_guard_imports_the_shared_helper():
    """A guard that stops importing the helper has silently lost its refusal."""
    modules = {"check_site_js": site_js, "check_nav_gap": nav_gap,
               "check_nav_mega": nav_mega, "check_badge_passport": badge,
               "check_cycle_consistency": ccc, "check_ms_board_coherence": ms,
               "check_ohlc_basis_coherence": ohlc}
    assert set(modules) == set(GUARDS), "GUARDS and the wiring census disagree"
    for name, mod in modules.items():
        assert getattr(mod, "refuse_if_vacuous", None) is SG.refuse_if_vacuous, (
            f"{name} no longer imports the shared refusal")
