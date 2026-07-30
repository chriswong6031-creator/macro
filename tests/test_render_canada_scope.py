"""build_canada must be a FIRST-CLASS pipeline step, not a swallowed build_vector hook.

Until 2026-07-27 ``scripts/build_canada.py`` was invoked by NO workflow.  site/canada.html
existed only as a side effect of ``scripts/build_vector.py`` calling ``build_canada.main()``
inside a ``try/except Exception: log.error(...)``.  Two defects rode on that:

1. **No scope of its own.**  render.yml's picker had no ``canada`` region, so a Canada-only
   template fix fell through ``region_of()``'s catch-all to ``all`` — a 40-85m full render
   for a ~10m builder — while a DISPATCHED narrow scope that happens not to call ``hub()``
   (``intl``, ``sits``) re-rendered everything EXCEPT canada.html and reported green.
   Recovering macro#3820 needed a hand-dispatched ``scope=hk`` purely because that scope
   calls ``hub()``.
2. **Silent failure.**  The hook logged through ``log.error``, and this repo's logging
   format prefixes ``"%(levelname)s "`` — so even an explicit ``::error`` would have been
   pushed off the line start and dropped by GitHub (see
   tests/test_gh_annotation_line_start.py).  A dead build_canada shipped a stale
   canada.html behind a green run.

These assertions pin the shape of the fix.  ``region_of`` is EXECUTED (not grepped): the
picker is inline shell, i.e. untested code unless a test runs it.

Run: .venv/bin/python -m pytest tests/test_render_canada_scope.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / ".github" / "workflows" / "render.yml").read_text()
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
WEEKLY = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
BUILD_VECTOR = (ROOT / "scripts" / "build_vector.py").read_text()
BUILD_CANADA = (ROOT / "scripts" / "build_canada.py").read_text()


def test_automatic_render_uses_reserved_heavy_runner() -> None:
    assert "default: render-heavy" in RENDER
    assert "github.event.inputs.runner || 'render-heavy'" in RENDER
    assert "      - self-hosted\n" in RENDER


def test_shared_mac_and_render_linux_remain_explicit_fallbacks() -> None:
    assert "options: [render-heavy, render-linux, macstudio]" in RENDER
    assert "shared Mac pool and" in RENDER
    assert "render-linux as explicit operator fallbacks" in RENDER


def _region_of_fn() -> str:
    """The literal `region_of() { ... }` shell function lifted out of render.yml."""
    lines = RENDER.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "region_of() {")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "}")
    return "\n".join(ln.strip() for ln in lines[start:end + 1])


def _region_of(path: str) -> str:
    out = subprocess.run(
        ["bash", "-c", f'{_region_of_fn()}\nregion_of "$1"', "_", path],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


# ---------------------------------------------------------------- scope picker


@pytest.mark.parametrize("path", [
    "templates/canada.html.j2",
    "templates/canada_stock.html.j2",
    "templates/canada_history.html.j2",
    "templates/canada_sector.html.j2",
    "scripts/build_canada.py",
    "scripts/build_canada_library.py",
])
def test_canada_files_auto_select_the_canada_scope(path):
    """A push touching these must resolve to `canada`, not the catch-all `all`."""
    assert _region_of(path) == "canada"


@pytest.mark.parametrize("path,region", [
    ("templates/china.html.j2", "china"),
    ("templates/hk.html.j2", "hk"),
    ("templates/intl.html.j2", "intl"),
    ("templates/dashboard.html.j2", "macro"),
    # Not promoted with this change: the baskets_canada page is still a build_vector
    # hook, so its files must keep falling through to `all` (over-render = safe).
    ("templates/baskets_canada.html.j2", "all"),
    ("scripts/build_baskets_canada.py", "all"),
])
def test_the_new_canada_arm_did_not_steal_another_region(path, region):
    assert _region_of(path) == region


def test_canada_is_in_the_dirty_region_loop():
    """region_of returning `canada` is inert unless the union loop iterates it."""
    assert "for R in macro intl china hk canada markets gex baskets sits; do" in RENDER


def test_canada_is_a_dispatchable_scope():
    assert "options: [all, macro, intl, china, hk, canada, markets, gex, baskets, sits]" in RENDER


# ------------------------------------------------------------- render wiring


def test_canada_scope_builds_canada_then_the_hub():
    # hub() must follow: build_vector's _canada_state() reads the regime JSON written
    # here. crypto() follows hub() because H6 consumes the BTC authority contract.
    assert "canada)\n              canada; hub; crypto ;;" in RENDER


def test_canada_builder_runs_before_hub_in_a_full_render():
    assert "spine; intl; canada; band;" in RENDER
    all_branch = RENDER.split("spine; intl; canada; band;")[1].split(";;")[0]
    assert "hub" in all_branch, "scope=all must still run the hub after canada"


def test_render_canada_exports_the_hook_skip():
    """Without this the ~10m builder runs twice in scope=all (canada() then hub())."""
    fn = next(ln for ln in RENDER.splitlines() if ln.strip().startswith("canada() {"))
    assert "export SKIP_CANADA_HOOK=1" in fn
    assert "scripts.build_canada" in fn


# --------------------------------------------------------- nightly / weekly


def test_daily_has_a_first_class_canada_step_before_build_vector():
    assert "python -m scripts.build_canada" in DAILY
    assert DAILY.index("python -m scripts.build_canada") < DAILY.index("python -m scripts.build_vector"), \
        "build_canada must precede build_vector — the landing hub reads canada_regime/latest.json"
    assert "SKIP_CANADA_HOOK=1" in DAILY


def test_weekly_has_a_first_class_canada_step_before_build_vector():
    assert 'run_py "build canada" scripts.build_canada' in WEEKLY
    assert WEEKLY.index('run_py "build canada" scripts.build_canada') \
        < WEEKLY.index('run_py "build vector + landing hub" scripts.build_vector')
    assert "export SKIP_CANADA_HOOK=1" in WEEKLY


# ---------------------------------------------- the surviving fallback hook


def test_build_vector_hook_is_skippable():
    """Kept as the fallback for closing-bell / earlyclose / sentinel / engine-render,
    but it must no-op in the lanes that now run the builder first-class."""
    assert 'os.environ.get("SKIP_CANADA_HOOK") == "1"' in BUILD_VECTOR


def test_build_vector_hook_failure_is_annotated_not_just_logged():
    hook = BUILD_VECTOR.split("Canada / S&P-TSX dashboard — FALLBACK ONLY")[1][:2000]
    assert 'print(f"::error title=canada dashboard (via build_vector) failed::' in hook, \
        "the hook must annotate with a bare print — a logger prefix drops the annotation"


def test_build_canada_reports_hard_failures():
    """main() still never raises, but a dead engine/render must not exit 0."""
    assert "::error title=build_canada engine failed::" in BUILD_CANADA
    assert "::error title=build_canada page render failed::" in BUILD_CANADA
    assert "return 0\n\n    try:" not in BUILD_CANADA, \
        "the engine-failure arm must return non-zero so run_py raises its own ::error"
