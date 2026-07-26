"""Regression guards for production deploy reconciliation."""
from __future__ import annotations

import ast
import subprocess
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app" / "deploy" / "update.sh"
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def test_update_script_has_valid_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)


def test_repository_noop_does_not_skip_reconciliation():
    assert '[ "$OLD" = "$NEW" ] && exit 0' not in SCRIPT
    assert 'if [ "$OLD" != "$NEW" ]; then' in SCRIPT
    assert SCRIPT.index("# Self-update:") < SCRIPT.index("API_UNIT_UPDATED=0")


def test_caddy_source_is_validated_before_install():
    validate = 'caddy validate --config "$APP_DIR/app/deploy/Caddyfile"'
    install = 'install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile'
    assert validate in SCRIPT
    assert SCRIPT.index(validate) < SCRIPT.index(install)


def test_changed_systemd_unit_forces_api_restart():
    assert "API_UNIT_UPDATED=1" in SCRIPT
    restart_condition = (
        'if [ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | '
        "grep -qE"
    )
    assert restart_condition in SCRIPT


# --------------------------------------------------------------------------
# macro-api restart trigger: a module import-cached by uvicorn but missing from
# the trigger regex deploys to the VPS and never goes live (sys.modules pins the
# old object).  These guards pin the regex's behaviour, not its spelling.
# --------------------------------------------------------------------------

def _api_restart_regex() -> str:
    """The ERE from the macro-api restart line in update.sh."""
    marker = '[ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '
    line = next(
        ln for ln in SCRIPT.splitlines()
        if marker in ln and ln.lstrip().startswith("if ")
    )
    body = line.split(marker, 1)[1]
    assert body.startswith("'"), body
    return body[1: body.index("'", 1)]


def _triggers_restart(path: str) -> bool:
    """Run the real grep so the test sees POSIX ERE semantics, not Python's."""
    return subprocess.run(
        ["grep", "-qE", _api_restart_regex()],
        input=path, text=True, check=False,
    ).returncode == 0


# Import-cached by the macro-api process -> a change here MUST restart it.
MUST_RESTART = [
    # app/ routers (all import-cached by uvicorn)
    "app/main.py",
    "app/research.py",
    "app/regwall.py",
    "app/paywall.py",
    "app/tape.py",
    "app/requirements.txt",
    "app/deploy/macro-api.service",
    "config/site_access.yml",
    # research vault serving layer — imported at MODULE level by app/research.py.
    # These were the 2026-07-26 gap: download caps / anti-scrape limits / watermark
    # policy deployed to the VPS and stayed dead until an unrelated app/ change.
    "engine/research_vault/download_quota.py",
    "engine/research_vault/view_ratelimit.py",
    "engine/research_vault/watermark.py",
    "engine/research_vault/catalog.py",
    "engine/research_vault/corpus.py",
    "engine/research_vault/r2_store.py",
    "engine/research_vault/sidecar.py",
    # /api/ask + /api/brain engine closure
    "engine/neuralweb/ask_brain.py",
    "engine/neuralweb/brain_gateway.py",
    "engine/neuralweb/cortex.py",
    "engine/neuralweb/chart_perception.py",
    "engine/neuralweb/doctrine.py",
    "engine/neuralweb/envelope.py",
    "engine/neuralweb/synapse.py",
    "engine/neuralweb/key_pool.py",
    "engine/llm_auth.py",
    "engine/portfolio_brief.py",
    "engine/tushare_freshness.py",
    # CXI packet build reached from brain_gateway (+ its module-level siblings)
    "engine/context_index/packet.py",
    "engine/context_index/fusion.py",
    "engine/context_index/gitinfo.py",
    "engine/context_index/lexical.py",
    "engine/context_index/structured.py",
    # brain_gateway chart path
    "engine/marketing/chart_render.py",
    "engine/marketing/confluence_source.py",
    # app/tape.py REST quotes, and lib modules on the chat path
    "engine/live_quotes.py",
    "lib/config.py",
    "lib/ai_costs.py",
    "lib/mastermind_response_log.py",
]

# NOT import-cached by macro-api -> restarting would blip /api for nothing.
MUST_NOT_RESTART = [
    # doctrine prose hot-reloads on mtime; only doctrine.py is cached
    "engine/neuralweb/doctrine/00_identity.md",
    # rendered site + data artifacts are read from disk per request
    "site/index.html",
    "site/feeds/risk_radar.json",
    "data/qbus/items.parquet",
    "research/DO_NOT_REBUILD.md",
    "docs/DESIGN_DOCTRINE.md",
    # nightly-only closure behind cortex.run() — never in the API's sys.modules
    "engine/master_brain.py",
    "engine/ai_desk.py",
    "engine/qledger.py",
    "engine/china_radar.py",
    "engine/neuralweb/constitution.py",
    # nightly-only builders inside packages whose serving modules ARE listed
    "engine/context_index/ingest.py",
    "engine/context_index/chunking.py",
    "engine/context_index/health.py",
    # other lanes
    "scripts/build_site.py",
    "engine/spine.py",
    "admin/server.py",
    "templates/index.html.j2",
]


@pytest.mark.parametrize("path", MUST_RESTART)
def test_import_cached_module_triggers_api_restart(path):
    assert (ROOT / path).exists(), f"stale test fixture: {path} no longer exists"
    assert _triggers_restart(path), (
        f"{path} is import-cached by macro-api but does not match the restart "
        "regex in app/deploy/update.sh — a change would deploy and never go live"
    )


@pytest.mark.parametrize("path", MUST_NOT_RESTART)
def test_non_api_path_does_not_trigger_api_restart(path):
    assert not _triggers_restart(path), (
        f"{path} is not import-cached by macro-api; restarting on it blips /api "
        "for nothing and defeats the narrow-restart intent"
    )


# --------------------------------------------------------------------------
# Drift guard: recompute the LOAD-TIME import closure of app/*.py and require
# the regex to cover it.  Load-time is objective (module-level imports always
# execute), so this can be machine-checked; request-time imports need human
# judgement about whether an API endpoint reaches them and stay in MUST_RESTART.
# --------------------------------------------------------------------------

_TRACKED_ROOTS = ("engine", "lib", "scripts")


def _tracked_modules(node: ast.AST, path: Path) -> set[str]:
    if isinstance(node, ast.Import):
        return {a.name for a in node.names
                if a.name.split(".")[0] in _TRACKED_ROOTS}
    if node.level:  # relative: resolve against the file's own package
        parts = list(path.relative_to(ROOT).parent.parts)
        for _ in range(node.level - 1):
            parts = parts[:-1]
        module = ".".join(parts) + (f".{node.module}" if node.module else "")
    else:
        module = node.module or ""
    if module.split(".")[0] not in _TRACKED_ROOTS:
        return set()
    # `from engine.research_vault import catalog` -> the submodule, too
    return {module} | {f"{module}.{a.name}" for a in node.names}


def _module_level_imports(path: Path) -> set[str]:
    """Imports that run when `path` is loaded (incl. module-level try/if guards)."""
    found: set[str] = set()
    for stmt in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            found |= _tracked_modules(stmt, path)
        elif isinstance(stmt, (ast.Try, ast.If, ast.With)):
            for inner in ast.walk(stmt):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    found |= _tracked_modules(inner, path)
    return found


def _all_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found |= _tracked_modules(node, path)
    return found


def _module_files(dotted: str) -> list[Path]:
    rel = dotted.replace(".", "/")
    return [p for p in (ROOT / f"{rel}.py", ROOT / rel / "__init__.py")
            if p.exists()]


def _is_inert_package_init(path: Path) -> bool:
    """A docstring-only __init__.py holds no behaviour that can go stale."""
    if path.name != "__init__.py":
        return False
    body = ast.parse(path.read_text(encoding="utf-8")).body
    return all(
        (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
         and isinstance(s.value.value, str))
        or (isinstance(s, ast.ImportFrom) and s.module == "__future__")
        for s in body
    )


def _api_load_time_closure() -> set[str]:
    """engine/lib modules guaranteed present in the macro-api sys.modules.

    Seeded from EVERY engine/lib import in app/ (app/ is the API, so even a
    function-level import there executes in-process on some request), then
    expanded through module-level imports only.
    """
    queue = deque()
    for router in sorted((ROOT / "app").glob("*.py")):
        queue.extend(_all_imports(router))

    seen: set[str] = set()
    reached: set[str] = set()
    while queue:
        dotted = queue.popleft()
        if dotted in seen:
            continue
        seen.add(dotted)
        for path in _module_files(dotted):       # skips symbols (funcs/classes)
            reached.add(str(path.relative_to(ROOT)))
            queue.extend(_module_level_imports(path))
    return reached


def test_api_load_time_import_closure_is_covered_by_restart_regex():
    """Every module macro-api loads at import time must force a restart.

    Fails when someone adds a module-level `from engine...`/`from lib...` import
    to an app/ router (or to a module already in the closure) without extending
    the trigger regex — the 2026-07-26 engine/research_vault gap, which shipped
    dead download-cap changes to production with no signal.
    """
    uncovered = sorted(
        rel for rel in _api_load_time_closure()
        if not _triggers_restart(rel)
        and not _is_inert_package_init(ROOT / rel)
    )
    assert not uncovered, (
        "import-cached by macro-api but missing from the restart regex in "
        f"app/deploy/update.sh: {uncovered}\n"
        "Add them (or, if a path is genuinely content read per request, document "
        "the exemption in the comment above the regex)."
    )


def test_load_time_closure_probe_is_not_vacuous():
    """Guard the guard: an AST/glob regression must not silently pass the above."""
    closure = _api_load_time_closure()
    assert "engine/research_vault/download_quota.py" in closure, closure
    assert "engine/neuralweb/brain_gateway.py" in closure, closure
    # nightly-only modules must stay OUT, else the closure is over-broad
    assert "engine/master_brain.py" not in closure
    assert "engine/china_radar.py" not in closure
