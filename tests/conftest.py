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

sys.modules eviction tripwire (MM_MODULE_GUARD)
-----------------------------------------------
A test that removes a name from sys.modules, or rebinds one to a different
module object, and does not put the original back poisons every LATER test in
the process.  The victim lands in an unrelated FILE, so the failure only appears
when the collected file set happens to pair culprit and victim — the failure set
moves as files are added, which reads as flake and gives a real regression
somewhere to hide.  Measured 2026-08-06: a `requests` eviction in
test_admin_live_runs.py killed test_capital_structure_share_count_materializer.py
three files later, and both suites are green in isolation.

Checked after EVERY test, in the post-yield half of the teardown hookwrapper —
the only window where all fixture finalizers, monkeypatch.undo included, have
already run.  Additions are ignored, and importlib.reload() keeps a module's
identity, so the ~40 files that reload are unaffected.  Modes via the
MM_MODULE_GUARD env var: (unset) on | off disable entirely.
See tests/test_no_module_leak.py for the static half and the mechanism pins.
"""
import os
import subprocess
import sys
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
    # Unit tests must never consume the developer/runner's attached Codex
    # subscription merely because ~/.codex/auth.json exists on the host.
    # Provider-specific tests opt back in and stub run_codex explicitly.
    monkeypatch.setenv("CODEX_PROVIDER_ENABLED", "0")


@pytest.fixture(autouse=True)
def _isolate_gdelt_stamps(monkeypatch):
    """engine.gdelt_client persists two stamps under data_dir()/gdelt as call-time
    side effects on the repo's REAL data/ tree: the cross-process throttle stamp
    (last_request) and the rate-limit circuit-breaker stamp (rate_limit_until).

    The breaker stamp is RESULT-CHANGING: a persistent-429 test
    (test_failed_fetch_result_is_not_cached) arms it, and without isolation every
    later GDELT test in the session then short-circuits to rate_limited (4 news_vector
    tests failed exactly this way). Redirect both to a private per-test temp dir —
    FUNCTION scope, so an arm in one test never leaks into the next; a SYSTEM temp
    dir (not the shared tmp_path), so a test that audits tmp_path for leftovers
    (test_share_cards.test_save_card_leaves_no_temp) never sees the stamp dir.
    _penalty_path() derives from _stamp_path().parent, so patching _stamp_path
    isolates both. Tests that patch _stamp_path themselves override this in-context.

    ImportError guard: runs for EVERY pytest invocation, including the minimal-deps
    CI jobs whose suites never import gdelt_client.
    """
    try:
        from engine import gdelt_client as _gc
    except Exception:  # noqa: BLE001 — minimal-deps job without engine deps
        yield
        return
    import tempfile
    with tempfile.TemporaryDirectory(prefix="gdelt_stamps_") as d:
        monkeypatch.setattr(_gc, "_stamp_path", lambda: Path(d) / "last_request")
        yield


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


@pytest.fixture(autouse=True, scope="session")
def _redirect_provider_health_ledger(tmp_path_factory):
    """engine.llm_auth.make_call records one provider_health row per rung
    ATTEMPT (W2, 2026-08-08), which means every test anywhere in the suite that
    drives a mocked waterfall appends the repo's real
    data/ai_costs/provider_health.jsonl as a call-time side effect. Six suites
    do (test_marketing_copy_v2, test_llm_auth, the copy critic/auditor lanes,
    the publish-time wire lane), and the repo's own data guard fails the run for
    it — correctly: a test must never write a production ledger.

    Redirected here rather than by teaching the writer to recognise pytest: the
    module under test should not carry test-detection, and an env redirect is
    structurally stronger anyway (it holds for a subprocess a test spawns, which
    an in-process monkeypatch would not). tests/test_provider_health.py sets its
    own PROVIDER_HEALTH_PATH per test and is unaffected.
    """
    target = tmp_path_factory.mktemp("provider_health") / "provider_health.jsonl"
    mp = pytest.MonkeyPatch()
    mp.setenv("PROVIDER_HEALTH_PATH", str(target))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _neutralize_implicit_account_overrides(monkeypatch):
    """engine.marketing.accounts.load_overrides() reads the repo's REAL
    data/marketing/account_overrides.json whenever the caller passes no explicit
    root — and the deployed admin panel COMMITS that file to main (admin/
    marketing.py, GitHub Contents API).  So live operator state silently
    overrides the synthetic cfg a unit test constructed, and a routine admin
    click turns CI red on main with no code change at all.

    Not hypothetical: on 2026-07-26T00:16Z the operator switched five desks off
    (receipts, theme_desk, research_a/b/c) and three test_marketing_content.py
    tests went red on a pristine main — tests whose entire point is "an account
    with no ``enabled`` key defaults on".  The accounts each test declared were
    overwritten by whatever the operator had last toggled.

    Neutralize the IMPLICIT read only (root=None).  An explicit root still hits
    the real function, so the tests that genuinely exercise the override file
    (TestEffectiveAccounts.test_override_file_flips_enabled /
    _malformed_override_file_is_ignored / _missing_override_file_is_no_overrides,
    all of which build a tmp root) keep their coverage intact, as do the admin
    tests that write a tmp overrides file.

    Covers every suite reaching this shared seam with an implicit root:
    content_studio.content_plan (test_marketing_content, test_marketing_links),
    sentinel.gate_plan (test_marketing_sentinel), publication.desk_network and
    accounts.effective_accounts (test_marketing_engine) — the latter three were
    latent, green only because the operator had not yet toggled the specific
    desks they assert on.

    A test that wants override behaviour passes a root it owns; asserting on
    whatever the live file happens to say is the bug this removes.

    ImportError guard: runs for EVERY pytest invocation, including the
    minimal-deps CI jobs whose suites never import the marketing engine.
    """
    try:
        from engine.marketing import accounts as _accounts
    except Exception:  # noqa: BLE001 — minimal-deps job without engine deps
        return
    _real_load_overrides = _accounts.load_overrides

    def _implicit_root_reads_no_overrides(root=None):
        return _real_load_overrides(root) if root is not None else {}

    monkeypatch.setattr(_accounts, "load_overrides", _implicit_root_reads_no_overrides)


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


# ---------------------------------------------------------------------------
# sys.modules eviction tripwire (MM_MODULE_GUARD)
# ---------------------------------------------------------------------------
# A test that removes a name from sys.modules — or rebinds one to a DIFFERENT
# module object — and does not put the original back poisons every later test in
# the same pytest process.  The damage lands in an unrelated FILE, so it only
# appears when the collected file set happens to put culprit and victim in one
# invocation: the failure set moves as files are added, which reads as "that
# flaky batch thing" and gives a genuine regression somewhere to hide.
#
# Measured instance (2026-08-06).  tests/test_admin_live_runs.py
# ::test_probe_bot_no_requests_lib popped `requests` out of sys.modules and THEN
# called monkeypatch.setitem(sys.modules, "requests", None).  monkeypatch
# snapshots the mapping at CALL time, so it recorded "key absent" and its
# teardown DELETED the key — and because monkeypatch runs after the test body it
# silently undid the test's own finally-block restore.  The next `import
# requests` re-executed requests/__init__.py against still-cached submodules:
# `from .sessions import Session, session` binds the NAMES it lists, and nothing
# re-runs the submodule loader that sets the `sessions` attribute on the fresh
# parent.  The result is a `requests` with `.session` but no `.sessions`, and
# tests/test_capital_structure_share_count_materializer.py died three files later
# on `requests.sessions.Session`.
#
# Legitimate idioms are untouched.  monkeypatch.setitem and mock.patch.dict on
# their own restore the original object; importlib.reload() re-executes a module
# IN PLACE, so its entry keeps both its key and its identity.  Additions are
# never leaks — importing a module for the first time is what tests do.
#
# Modes via MM_MODULE_GUARD:  (unset) on  |  off  disable entirely.

_MODULE_GUARD_MSG = (
    "A test must leave sys.modules exactly as it found it.  Use\n"
    "monkeypatch.setitem(sys.modules, name, value) or mock.patch.dict on their\n"
    "own — both restore the original object.  Never pop/del the key first: the\n"
    "pop is what makes monkeypatch record 'absent' and DELETE the name at\n"
    "teardown, after any finally-block restore has already run.\n"
    "To make `import name` raise ImportError, setitem it to None; the key must\n"
    "still be present for monkeypatch to restore.\n"
    "Bypass (never in CI): MM_MODULE_GUARD=off"
)


def _module_guard_mode() -> str:
    return os.environ.get("MM_MODULE_GUARD", "").strip().lower()


def _module_identities() -> dict[str, int]:
    """name -> id() of every currently-imported module.

    list() first: an import triggered on another thread mid-iteration would
    otherwise raise "dictionary changed size during iteration".
    """
    return {name: id(mod) for name, mod in list(sys.modules.items())}


def _module_leaks(
    before: dict[str, int],
    after: dict[str, int],
    inherited: set[str] | None = None,
) -> list[str]:
    """Names a test EVICTED or REBOUND, comparing what it inherited to what it left.

    Additions are not leaks, so they are ignored.  Identity is compared by id()
    because that is what distinguishes a restored module from a re-imported
    twin: importlib.reload() keeps the object, a delete + re-import does not.

    ``inherited`` scopes the result to names that existed when collection
    finished — the modules the suite genuinely shares.  A name a test file
    MINTED for itself is its own scratch space: tests/test_capital_structure
    _share_count_r2_operator.py loads the operator script under the synthetic
    name ``_share_count_r2_operator_test`` once per test, rebinding it every
    time, and nothing outside that file can hold a stale reference to it.
    Trade-off, stated rather than hidden: a module first imported mid-session
    and evicted later is not reported.  The shared surface — everything the test
    modules pulled in at import time, which is where a cross-file victim's
    dependencies actually live — is covered.
    """
    names = set(before) - set(after)
    names |= {n for n in set(before) & set(after) if before[n] != after[n]}
    if inherited is not None:
        names &= inherited
    return sorted(
        f"evicted  {n}" if n not in after
        else f"rebound  {n} (a DIFFERENT module object — the original is gone)"
        for n in names
    )


def pytest_sessionstart(session):
    if _data_guard_mode() == "off" or hasattr(session.config, "workerinput"):
        return
    session.config._mm_data_guard_baseline = _data_status()
    session.config._mm_data_guard_hits = []


def pytest_collection_finish(session):
    # Baseline AFTER collection: importing the test modules is itself a large
    # burst of additions, and additions are not what this guard measures.
    if _module_guard_mode() == "off":
        return
    session.config._mm_module_baseline = _module_identities()
    # The shared surface, frozen: every module the collected test files pulled in
    # at import time. Names minted later by a test belong to that test.
    session.config._mm_module_inherited = set(session.config._mm_module_baseline)
    session.config._mm_module_leaks = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    # PRE-yield keeps the data-guard trace check exactly where it was, ahead of
    # _pytest.runner's own teardown implementation.
    if _data_guard_mode() == "trace":
        config = item.session.config
        baseline = getattr(config, "_mm_data_guard_baseline", None)
        fresh = _new_entries(baseline)
        if fresh:
            config._mm_data_guard_hits.append((item.nodeid, fresh))
            # advance the baseline so each culprit is reported exactly once
            config._mm_data_guard_baseline = _data_status()

    yield

    # POST-yield is the only correct window for the module check: every fixture
    # finalizer for this test has now run, monkeypatch.undo included, so what
    # sys.modules looks like here is exactly what the next test inherits.
    config = item.session.config
    before = getattr(config, "_mm_module_baseline", None)
    if before is None:
        return
    after = _module_identities()
    leaks = _module_leaks(before, after, getattr(config, "_mm_module_inherited", None))
    if leaks:
        config._mm_module_leaks.append((item.nodeid, leaks))
    # roll the baseline forward so each culprit is reported exactly once
    config._mm_module_baseline = after


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

    module_leaks = getattr(session.config, "_mm_module_leaks", [])
    if module_leaks:
        body = "\n".join(
            f"  {nodeid}\n" + "\n".join(f"    {line}" for line in lines)
            for nodeid, lines in module_leaks
        )
        print(
            f"\n{'=' * 70}\n"
            f"MM_MODULE_GUARD: test(s) left sys.modules poisoned for every later\n"
            f"test in this process — the victim is usually in an UNRELATED file:\n"
            f"{body}\n{_MODULE_GUARD_MSG}\n{'=' * 70}"
        )
        # Same reasoning as the data-guard annotation below: on Actions this
        # banner sits far above the green "N passed" line and the job otherwise
        # dies as what reads as a silent exit 1.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            nodeid, lines = module_leaks[0]
            print(f"::error title=MM_MODULE_GUARD::{nodeid} left sys.modules "
                  f"poisoned ({'; '.join(line.strip() for line in lines)}) — exit "
                  f"forced to 1; see the MM_MODULE_GUARD banner above the pytest "
                  f"summary")
        if session.exitstatus == 0:
            session.exitstatus = 1

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
# tests opt out by name to exercise the real helpers under tmp_path.
#
# An opted-out test MUST isolate itself (root=tmp / absolute reply_cache_dir).
# Keep this set in sync when a roundtrip test is added: an un-listed one reads
# GREEN while asserting nothing (get is stubbed to always-miss, put to a no-op)
# — test_w7_llm_determinism.py::test_master_brain_cache_hit sat that way until
# its check() ledger was gated (2026-08-09).
# --------------------------------------------------------------------------- #
_REAL_MB_REPLY_CACHE_TESTS = frozenset({
    "test_reply_cache_roundtrip_root_aware",   # tests/test_master_brain.py
    "test_master_brain_cache_hit",             # tests/test_w7_llm_determinism.py
})


@pytest.fixture(autouse=True)
def _hermetic_master_brain_reply_cache(request, monkeypatch):
    if request.node.name in _REAL_MB_REPLY_CACHE_TESTS:
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


# --------------------------------------------------------------------------- #
# data/marketing/account_overrides.json is LIVE OPERATOR STATE — the admin
# panel's per-account ARM/DISARM toggle commits it straight to main. Unit tests
# must assert what the CODE does, never which desks the operator happened to
# have switched on when CI ran.
#
# 2026-07-26: during the flagship-post incident the operator disabled 5 of the 6
# desks (receipts, theme_desk, research_a/b/c) at 00:16Z. The file appeared on
# main, effective_accounts() picked it up, and the `marketing-engine` CI job went
# red — 8 failures asserting cross-account near-dup quarantines and non-empty
# `receipts` queues that can only hold while those desks are enabled. Nothing in
# the marketing engine had changed. Worse, that job is path-filtered to
# engine/marketing/**, so it fires ONLY on marketing PRs: the breakage was
# invisible on every other PR and would have ambushed the next marketing change.
#
# Only DEFAULT-root reads are neutralized. Every test that deliberately
# exercises the override mechanism passes an explicit tmp root and keeps the
# real loader (tests/test_marketing_engine.py, tests/test_admin_marketing.py).
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _hermetic_marketing_account_overrides(monkeypatch):
    try:
        from engine.marketing import accounts as _accounts
    except Exception:  # minimal-deps CI lanes may lack engine imports
        yield
        return
    _real_load_overrides = _accounts.load_overrides

    def _no_live_operator_state(root=None):
        if root is None:
            return {}
        return _real_load_overrides(root)

    monkeypatch.setattr(_accounts, "load_overrides", _no_live_operator_state)
    yield
