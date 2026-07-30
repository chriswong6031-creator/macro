"""The heavy render lane admits only builders that can affect its output.

The old ``scripts/build_*.py`` push glob matched 283 entrypoints. render.yml
directly executed 63 and imported another 38 transitively, so unrelated nightly,
research, marketing, and live-flow changes repeatedly queued a 50-100 minute
self-hosted render that never invoked the changed module.

This suite makes the positive allowlist executable:

* every directly invoked builder must be admitted;
* every statically imported builder dependency must be admitted;
* every admitted builder must exist and be reachable;
* the broad wildcard must never return.

Run:
    python -m pytest tests/test_render_builder_ownership.py -q
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDER_PATH = ROOT / ".github" / "workflows" / "render.yml"
RENDER = RENDER_PATH.read_text(encoding="utf-8")

_TRIGGER_ITEM = re.compile(
    r'^\s+- "(scripts/build_[A-Za-z0-9_]+\.py)"\s*$',
    re.MULTILINE,
)
_MODULE = re.compile(r"\bscripts\.(build_[A-Za-z0-9_]+)\b")

# build_flow_desk is being admitted to render.yml by PR #4045. Keeping its trigger
# ownership in this queue-fix branch is safe before that merge (one conservative
# over-render) and becomes an ordinary direct member as soon as #4045 lands.
_MANUAL_TRANSITION = {"build_flow_desk"}


def _owned_modules() -> set[str]:
    return {
        path.removeprefix("scripts/").removesuffix(".py")
        for path in _TRIGGER_ITEM.findall(RENDER)
    }


def _direct_modules() -> set[str]:
    """Builders invoked by a run block, excluding prose outside run scalars."""
    import yaml

    workflow = yaml.safe_load(RENDER)
    run_bodies: list[str] = []
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                run_bodies.append(step["run"])
    return set(_MODULE.findall("\n".join(run_bodies)))


def _static_builder_imports(module: str) -> set[str]:
    """Top-level scripts.build_* files imported by ``module``.

    AST parsing avoids false edges from aliases such as
    ``build_detail_pages`` and from comments that merely name another builder.
    Direct subprocess modules are already visible in render.yml's run body; we
    intentionally ignore arbitrary string constants because builder docstrings
    frequently name upstream data producers that render does not execute.
    """
    path = ROOT / "scripts" / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                match = re.fullmatch(r"scripts\.(build_[A-Za-z0-9_]+)", alias.name)
                if match:
                    found.add(match.group(1))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "scripts":
                found.update(alias.name for alias in node.names if alias.name.startswith("build_"))
            elif node.module:
                match = re.fullmatch(r"scripts\.(build_[A-Za-z0-9_]+)", node.module)
                if match:
                    found.add(match.group(1))
    return {
        name
        for name in found
        if (ROOT / "scripts" / f"{name}.py").is_file()
    }


def _reachable_modules() -> set[str]:
    reachable = _direct_modules()
    pending = list(reachable)
    while pending:
        module = pending.pop()
        for dependency in _static_builder_imports(module):
            if dependency not in reachable:
                reachable.add(dependency)
                pending.append(dependency)
    return reachable


def test_render_uses_positive_builder_ownership_not_the_repo_wide_wildcard():
    assert '- "scripts/build_*.py"' not in RENDER
    assert '- "!scripts/build_public_pages.py"' not in RENDER
    assert _owned_modules(), "the explicit builder ownership list vanished"


def test_every_owned_builder_exists():
    missing = sorted(
        module
        for module in _owned_modules()
        if not (ROOT / "scripts" / f"{module}.py").is_file()
    )
    assert not missing, f"render owns deleted/nonexistent builders: {missing}"


def test_direct_and_transitive_render_dependencies_are_owned():
    missing = sorted(_reachable_modules() - _owned_modules())
    assert not missing, (
        "render invokes or imports builders that its push filter does not own; "
        f"a change would merge without starting render.yml: {missing}"
    )


def test_allowlist_has_no_unreachable_queue_entries():
    extra = sorted(_owned_modules() - _reachable_modules() - _MANUAL_TRANSITION)
    assert not extra, (
        "render's push filter owns builders the lane neither invokes nor imports; "
        f"these recreate the false queue-admission problem: {extra}"
    )


def test_recent_false_admissions_stay_out_of_the_heavy_lane():
    owned = _owned_modules()
    assert {
        "build_session_digest",
        "build_live_quotes",
        "build_flow_archive",
        "build_marketing",
        "build_press_properties",
    }.isdisjoint(owned)


def test_known_transitive_render_dependencies_stay_owned():
    owned = _owned_modules()
    assert {
        "build_stock_library",
        "build_chart_data",
        "build_china_library",
        "build_research_pages",
        "build_theme_detail",
    } <= owned
