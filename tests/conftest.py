"""Test-suite conftest.py — repo-wide pytest configuration.

COLLECT_LANE sentinel
---------------------
Forward-ledger writers gate on ``COLLECT_LANE=nightly`` (or the legacy alias
``US_LANE=nightly``).  All pre-existing tests that call a writer function and
expect a write to succeed were written before the gate existed; rather than
touching every test file we set the sentinel here at session scope via an
autouse fixture.

Tests that explicitly verify the *blocked* path (e.g. TestUsLaneGate in
test_basket_turn_watch.py) pop COLLECT_LANE / US_LANE directly via
``os.environ.pop`` — that overrides the autouse value and the gate fires as
expected.  Monkeypatch-based gate tests work identically (``monkeypatch.delenv``
removes the key before the assertion, and monkeypatch restores after).

data/ + site/ write tripwire (MM_DATA_GUARD)
--------------------------------------------
Because COLLECT_LANE=nightly is armed for every test, any test that reaches a
writer WITHOUT isolation (root= param, monkeypatched lib.config
data_dir/ROOT) mutates the repo's REAL data/ tree.  Those writes ride any
later ``git add data/`` from the same checkout (nightly data commits, agent
sweeps) and permanently pollute forward ledgers —
data/foresight/policy_calendar_ledger.jsonl carries a committed synthetic
test row (theme=solar, asof=2026-07-03, logged 2026-07-04T00:30:49Z) from
exactly this failure mode.

The tracked site/ tree has the same failure mode through builder entry
points that default their output dir to the repo's real site/ (render
helpers, snapshot writers): synthetic test fixtures overwrite committed
pages/JSON and ride any later ``git add site/``.  Render-oriented tests are
legitimate — they must redirect output (tmp_path out dir, monkeypatched
lib.config ROOT/SITE), never write the real tree.

The guard snapshots ``git status --porcelain`` for each watched tree
(``data/``, ``site/``) at session start and fails the run (exit 1) when NEW
entries appear by session end.  Modes via the MM_DATA_GUARD env var:

  (unset)  session-level tripwire (default; two git calls per session)
  off      disable entirely (deliberate data-writing local flows only)
  trace    per-test attribution — re-checks after EVERY test and reports the
           offending nodeids in the session-end summary (slow: one git status
           per test; use it to hunt a culprit, not in CI)

Known limitation: a file already dirty at session start that is modified
*further* during the session produces an identical porcelain line and is not
detected.  Fresh checkouts (CI, new worktrees) start clean, which is the main
protection surface.  Writes under gitignored paths are invisible to git and
likewise not detected (they also cannot be committed).
"""
import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _set_nightly_lane(monkeypatch):
    """Ensure forward-ledger writes are allowed in all tests by default.

    Tests that need to verify the gate is *off* must pop COLLECT_LANE (and
    US_LANE) explicitly inside their body — the pop takes precedence because
    monkeypatch.setenv uses the live os.environ dict.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")


@pytest.fixture(autouse=True, scope="session")
def _redirect_breadth_divergence_stamp(tmp_path_factory):
    """compute_theme_intel() stamps elevated/high breadth-divergence textures
    into data/breadth_divergence/forward_log.parquet as a call-time side
    effect (engine/theme_scoring.py -> basket_breadth_divergence.log_stamp),
    so ANY test that reaches theme intel through any depth of indirection
    appends the repo's real forward ledger (three separate suites did:
    test_theme_regionalize, test_flip_distance, test_theme_scoring).  Redirect
    the default stamp target to a session tmp for every test; unit tests of
    log_stamp itself pass an explicit path= and are unaffected.

    ImportError guard: this autouse-session fixture executes for EVERY pytest
    run, including the ~8 minimal-deps CI jobs (pip install pytest pyyaml
    only) whose suites never touch theme-intel paths — the engine import
    chain needs numpy/pandas and errored ALL their tests at session start
    (self-mod-fence red, 2026-07-16). No deps -> no net needed: nothing in
    those jobs can reach compute_theme_intel."""
    try:
        from engine import basket_breadth_divergence as bd
    except ImportError:
        yield
        return
    target = tmp_path_factory.mktemp("bd_stamp") / "forward_log.parquet"
    mp = pytest.MonkeyPatch()
    mp.setattr(bd, "_log_path", lambda: target)
    yield
    mp.undo()


# ---------------------------------------------------------------------------
# data/ write tripwire
# ---------------------------------------------------------------------------

_WATCHED_TREES = ("data/", "site/")


def _data_guard_mode() -> str:
    return os.environ.get("MM_DATA_GUARD", "").strip().lower()


def _data_status() -> list[str] | None:
    """Sorted ``git status --porcelain`` lines for watched trees; None if git unusable."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", *_WATCHED_TREES],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return sorted(line for line in out.stdout.splitlines() if line.strip())


def _new_entries(baseline: list[str] | None) -> list[str]:
    if baseline is None:
        return []
    current = _data_status()
    if current is None:
        return []
    known = set(baseline)
    return [line for line in current if line not in known]


_GUARD_MSG = (
    "Tests must never write the repo's real data/ or site/ trees: pass\n"
    "root=tmp_path / an explicit out dir, or monkeypatch lib.config\n"
    "data_dir/ROOT, or pass explicit empty payloads to entry points that\n"
    "lazily recompute tiers (compute_foresight_cascade et al.).  Render\n"
    "tests redirect output to tmp_path — site/ output is legitimate, the\n"
    "destination is not.\n"
    "Heal the tree:  git checkout -- data/ site/ && git clean -fd data/ site/\n"
    "Hunt a culprit: MM_DATA_GUARD=trace python -m pytest <suspect files>\n"
    "Bypass (deliberate local data flows only): MM_DATA_GUARD=off"
)


def pytest_sessionstart(session):
    if _data_guard_mode() == "off" or hasattr(session.config, "workerinput"):
        return
    session.config._mm_data_guard_baseline = _data_status()
    session.config._mm_data_guard_hits = []


def pytest_runtest_teardown(item, nextitem):
    if _data_guard_mode() != "trace":
        return
    config = item.session.config
    baseline = getattr(config, "_mm_data_guard_baseline", None)
    fresh = _new_entries(baseline)
    if fresh:
        config._mm_data_guard_hits.append((item.nodeid, fresh))
        # advance the baseline so each culprit is reported exactly once
        config._mm_data_guard_baseline = _data_status()


def pytest_sessionfinish(session, exitstatus):
    # pytest>=9 installs an unraisable-exception hook for the whole process: a
    # collectable cycle that survives to interpreter shutdown runs its __del__
    # against torn-down module globals, raises, and silently flips the exit code
    # to 1 AFTER the summary prints ("2067 passed" + exit 1, engine-render-guards
    # 2026-07-18). Collecting here tears those cycles down inside the session,
    # where destructors run against live globals and any genuine failure is
    # reported as a visible PytestUnraisableExceptionWarning instead.
    import gc

    gc.collect()

    if _data_guard_mode() == "off" or hasattr(session.config, "workerinput"):
        return
    baseline = getattr(session.config, "_mm_data_guard_baseline", None)
    hits = getattr(session.config, "_mm_data_guard_hits", [])
    fresh = _new_entries(baseline)
    if not fresh and not hits:
        return
    report = []
    for nodeid, changed in hits:
        report.append(f"  {nodeid}")
        report.extend(f"    {line}" for line in changed)
    if fresh:
        report.extend(f"  {line}" for line in fresh)
    body = "\n".join(report)
    print(
        f"\n{'=' * 70}\n"
        f"MM_DATA_GUARD: test session dirtied the real data/ or site/ tree:\n{body}\n"
        f"{_GUARD_MSG}\n{'=' * 70}"
    )
    # On GitHub Actions the banner sits ~60 log lines above the green "N
    # passed" summary and the job dies with what reads as a silent exit 1 —
    # exactly how the 2026-07-18 engine-render-guards red got misdiagnosed as
    # a pytest-9 shutdown bug. Emit a workflow error annotation so the trip
    # is visible on the run page without reading the step log.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        lines = fresh or [line for _, changed in hits for line in changed]
        dirtied = ", ".join(line.strip() for line in lines) or "see step log"
        print(f"::error title=MM_DATA_GUARD::test session dirtied the real "
              f"data/ or site/ tree ({dirtied}) — exit forced to 1; "
              f"see the MM_DATA_GUARD banner above the pytest summary")
    if session.exitstatus == 0:
        session.exitstatus = 1


# --------------------------------------------------------------------------- #
# ABX: hermetic master_brain reply cache. synthesize() is the SOLE reply-cache
# writer (root-aware); a test that drives it without a tmp root would write the
# REAL data/master_brain/reply_cache tree — the exact class this guard exists
# for. DISABLE the cache for every test (get misses, put drops) rather than
# emulate it in memory: an emulated cache makes two same-prompt stubbed calls
# inside one test serve the first reply to the second, breaking tests that
# stub different replies per call (producer suite). The dedicated roundtrip
# test opts out by name to exercise the real helpers under tmp_path.
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _hermetic_master_brain_reply_cache(request, monkeypatch):
    if request.node.name == "test_reply_cache_roundtrip_root_aware":
        yield
        return
    try:
        from engine import master_brain as _mb
    except Exception:  # minimal-deps CI lanes may lack engine imports
        yield
        return
    monkeypatch.setattr(_mb, "_mb_reply_cache_get",
                        lambda ph, cfg, root=None: None)
    monkeypatch.setattr(_mb, "_mb_reply_cache_put",
                        lambda ph, text, cfg, root=None: None)
    yield
