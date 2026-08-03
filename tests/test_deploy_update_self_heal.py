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


def test_codex_runtime_setup_has_valid_shell_syntax():
    runtime_setup = ROOT / "app" / "deploy" / "codex-runtime-setup.sh"
    subprocess.run(["bash", "-n", str(runtime_setup)], check=True)
    text = runtime_setup.read_text(encoding="utf-8")
    assert '@openai/codex@$CODEX_CLI_VERSION' in text
    assert "CODEX_STATE_DIRS" in text
    assert '$state_dir/auth.json' in text
    assert "/var/lib/macro-codex:/var/lib/macro-codex-2" in text


def test_live_setup_installs_press_scoring_backend():
    live_setup = ROOT / "app" / "deploy" / "live-setup.sh"
    subprocess.run(["bash", "-n", str(live_setup)], check=True)
    assert "datasketch" in live_setup.read_text(encoding="utf-8")


def test_deployed_services_share_root_only_codex_state():
    for relative in (
        "app/deploy/macro-api.service",
        "admin/deploy/admin.service",
    ):
        unit = (ROOT / relative).read_text(encoding="utf-8")
        assert "Environment=CODEX_HOME=/var/lib/macro-codex" in unit
        assert (
            "Environment=CODEX_ACCOUNT_HOMES="
            "/var/lib/macro-codex:/var/lib/macro-codex-2"
        ) in unit
        assert "Environment=CODEX_PROVIDER_ENABLED=1" in unit
        assert "StateDirectory=macro-codex macro-codex-2" in unit
        assert "StateDirectoryMode=0700" in unit


def test_update_reconciles_codex_runtime_and_admin_unit():
    assert 'bash "$APP_DIR/app/deploy/codex-runtime-setup.sh" --quiet' in SCRIPT
    assert 'cmp -s "$APP_DIR/admin/deploy/admin.service"' in SCRIPT
    assert "ADMIN_UNIT_UPDATED=1" in SCRIPT


def test_update_reconciles_api_requirements_with_retryable_content_stamp():
    assert 'sha256sum "$APP_DIR/app/requirements.txt"' in SCRIPT
    assert '/opt/macro-api/.venv/bin/pip install -q -r "$APP_DIR/app/requirements.txt"' in SCRIPT
    assert "API_REQ_STAMP=/opt/macro-api/.requirements.sha256" in SCRIPT
    assert 'if [ "$API_DEPS_OK" -ne 1 ]; then' in SCRIPT


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

_GREP = "grep -qE "


def _ere_on_line(line: str) -> str:
    """Pull the single-quoted ERE out of a `grep -qE '...'` shell line."""
    body = line.split(_GREP, 1)[1]
    assert body.startswith("'"), body
    return body[1: body.index("'", 1)]


def _api_restart_regex() -> str:
    """The ERE from the macro-api restart line in update.sh."""
    marker = '[ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | ' + _GREP
    return _ere_on_line(next(
        ln for ln in SCRIPT.splitlines()
        if marker in ln and ln.lstrip().startswith("if ")
    ))


def _admin_restart_regex() -> str:
    """The ERE guarding `systemctl restart admin`.

    Anchored on the restart it guards rather than on the regex's own spelling, so
    reordering the alternation can never silently point this at another line.
    """
    lines = SCRIPT.splitlines()
    restart = next(i for i, ln in enumerate(lines)
                   if "systemctl is-enabled admin " in ln)
    guard = next(i for i in range(restart - 1, -1, -1) if _GREP in lines[i])
    return _ere_on_line(lines[guard])


def _press_restart_regex() -> str:
    """The ERE guarding the long-running PRESS-FEEDS daemon restart."""
    lines = SCRIPT.splitlines()
    restart = next(i for i, ln in enumerate(lines)
                   if "systemctl restart marketing-press-feeds" in ln)
    guard = next(i for i in range(restart - 1, -1, -1) if _GREP in lines[i])
    return _ere_on_line(lines[guard])


def _matches(regex: str, path: str) -> bool:
    """Run the real grep so the test sees POSIX ERE semantics, not Python's."""
    return subprocess.run(
        ["grep", "-qE", regex], input=path, text=True, check=False,
    ).returncode == 0


def _triggers_restart(path: str) -> bool:
    return _matches(_api_restart_regex(), path)


def _triggers_admin_restart(path: str) -> bool:
    return _matches(_admin_restart_regex(), path)


def _triggers_press_restart(path: str) -> bool:
    return _matches(_press_restart_regex(), path)


# Import-cached by the macro-api process -> a change here MUST restart it.
MUST_RESTART = [
    # app/ routers (all import-cached by uvicorn)
    "app/main.py",
    "app/research.py",
    "app/regwall.py",
    "app/paywall.py",
    "app/tape.py",
    "app/biocatalyst.py",
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
    # BioCatalyst serving validates and projects the immutable public generation.
    "engine/biocatalyst/publication.py",
    "engine/biocatalyst/trials.py",
    "engine/sector_intelligence/__init__.py",
    "engine/sector_intelligence/contracts.py",

    # Capital Structure serving closure — imported by app/capital_structure.py.
    "engine/capital_structure/__init__.py",
    "engine/capital_structure/event_spine.py",
    "engine/capital_structure/projection.py",
    # Government Revenue serving modules are imported by app/government_revenue.py.
    "engine/government_revenue/budget_program.py",
    "engine/government_revenue/idv_dossiers.py",
    "engine/government_revenue/subaward_dossiers.py",
    # The public Company Intelligence API imports the reader plus this
    # non-inert package at process startup (contracts, health, and views).
    "engine/neuralweb/company_intelligence_reader.py",
    "engine/company_intelligence/__init__.py",
    "engine/company_intelligence/contracts.py",
    "engine/company_intelligence/health.py",
    "engine/company_intelligence/views.py",
    # /api/ask + /api/brain engine closure
    "engine/neuralweb/ask_brain.py",
    "engine/neuralweb/chat_plain_words.py",
    "engine/neuralweb/brain_gateway.py",
    "engine/neuralweb/cortex.py",
    "engine/neuralweb/chart_perception.py",
    "engine/neuralweb/doctrine.py",
    "engine/neuralweb/envelope.py",
    "engine/neuralweb/synapse.py",
    "engine/neuralweb/key_pool.py",
    "engine/codex_lane/runner.py",
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
    # ...plus the substrate the PACKAGE __init__ drags in: importing any
    # engine.marketing submodule runs __init__ -> state -> these ten.  Invisible
    # to an import-line scan; confirmed against a live interpreter's sys.modules.
    "engine/marketing/__init__.py",
    "engine/marketing/state.py",
    "engine/marketing/authority.py",
    "engine/marketing/charter.py",
    "engine/marketing/claims.py",
    "engine/marketing/cmo.py",
    "engine/marketing/departments.py",
    "engine/marketing/economics.py",
    "engine/marketing/events.py",
    "engine/marketing/ledgers.py",
    "engine/marketing/opportunity_bus.py",
    "engine/marketing/publication.py",
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
    # nightly-only marketing modules — the package is named, not globbed
    "engine/marketing/seo_director.py",
    "engine/marketing/social_publisher.py",
    # outbox/rejections back the ADMIN outbox endpoints and sit on no API path
    "engine/marketing/outbox.py",
    "engine/marketing/rejections.py",
    # other lanes
    "scripts/build_site.py",
    "scripts/marketing_publisher.py",
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
# admin console restart trigger.  Same trap, separate (narrower) regex: the
# panel is a long-running process, so sys.modules pins whatever a request-time
# import loaded and an engine-side fix stays dead until something restarts it.
# --------------------------------------------------------------------------

# Import-cached by the admin process -> a change here MUST restart it.
ADMIN_MUST_RESTART = [
    # panel code (all import-cached by the running process)
    "admin/server.py",
    "admin/marketing.py",
    "admin/metabolism_panel.py",
    "admin/neural_web.py",
    "admin/orchestrator_chat.py",
    "admin/ai_cost.py",
    "admin/mastermind_logs.py",
    "admin/prophet.py",
    "admin/trade_memory.py",
    # outbox approve / reject / decide endpoints (admin/marketing.py).  This was
    # the 2026-07-26 gap: an outbox.py fix deployed to the VPS and the running
    # panel kept serving the previous module, with no signal.
    "engine/marketing/outbox.py",
    "engine/marketing/rejections.py",
    # ...and the substrate `from engine.marketing import outbox` executes on the
    # way in (package __init__ -> state -> these ten)
    "engine/marketing/__init__.py",
    "engine/marketing/state.py",
    "engine/marketing/authority.py",
    "engine/marketing/charter.py",
    "engine/marketing/claims.py",
    "engine/marketing/cmo.py",
    "engine/marketing/departments.py",
    "engine/marketing/economics.py",
    "engine/marketing/events.py",
    "engine/marketing/ledgers.py",
    "engine/marketing/opportunity_bus.py",
    "engine/marketing/publication.py",
    # publish dry-run report (admin/marketing.py)
    "scripts/marketing_publisher.py",
    # deliberation-spend panel (admin/prophet.py)
    "engine/codex_provider.py",
    "engine/codex_lane/runner.py",
    "engine/llm_auth.py",
    # private episode validator imported by admin/trade_memory.py
    "engine/neuralweb/trade_memory.py",
    # reached via importlib.import_module("...") string literals — a grep for
    # `from engine`/`from lib` does not see these at all
    "engine/neuralweb/support_map.py",
    "engine/neuralweb/orchestrator_log.py",
    "engine/neuralweb/ask_brain.py",
    "lib/ai_costs.py",
    # static request-time imports
    "engine/neuralweb/key_pool.py",
    "engine/metabolism/throttle.py",
    "engine/metabolism/budget_gate.py",
    "lib/mastermind_response_log.py",
]

# NOT import-cached by admin -> restarting would blip the panel for nothing.
ADMIN_MUST_NOT_RESTART = [
    # rendered site + data artifacts are read from disk per request
    "site/index.html",
    "data/qbus/items.parquet",
    "engine/neuralweb/doctrine/00_identity.md",
    # the panel's only entry into ask_brain is _post_filter_advice(); the
    # tool-schema / dispatch paths that lazily import cortex are never called
    # from admin, which ships its own tool dispatcher
    "engine/neuralweb/cortex.py",
    "engine/master_brain.py",
    "engine/china_radar.py",
    # nightly-only marketing modules — the package is named, not globbed
    "engine/marketing/seo_director.py",
    "engine/marketing/social_publisher.py",
    "engine/marketing/breaking_feed.py",
    # macro-api's chart path, on no panel path
    "engine/marketing/chart_render.py",
    "engine/marketing/confluence_source.py",
    # the API and site-build lanes
    "app/main.py",
    "app/research.py",
    "lib/config.py",
    "scripts/build_site.py",
    "templates/index.html.j2",
]


@pytest.mark.parametrize("path", ADMIN_MUST_RESTART)
def test_import_cached_module_triggers_admin_restart(path):
    assert (ROOT / path).exists(), f"stale test fixture: {path} no longer exists"
    assert _triggers_admin_restart(path), (
        f"{path} is import-cached by the admin panel but does not match the "
        "admin restart regex in app/deploy/update.sh — a change would deploy "
        "and never go live"
    )


@pytest.mark.parametrize("path", ADMIN_MUST_NOT_RESTART)
def test_non_admin_path_does_not_trigger_admin_restart(path):
    assert not _triggers_admin_restart(path), (
        f"{path} is not import-cached by admin; restarting on it blips the panel "
        "for nothing and defeats the narrow-restart intent"
    )


def test_api_and_admin_regexes_are_distinct():
    """Guard the extractor: both helpers must not resolve to the same line."""
    assert _api_restart_regex() != _admin_restart_regex()
    assert _admin_restart_regex().startswith("^(admin/")


# --------------------------------------------------------------------------
# PRESS-FEEDS deployment lifecycle. The service is intentionally operator-armed,
# but once active it is a long-running Python process and must not keep stale
# import-cached code after the checkout advances.
# --------------------------------------------------------------------------

PRESS_MUST_RESTART = [
    "app/deploy/marketing-press-feeds.service",
    "scripts/marketing_fastlane_daemon.py",
    "engine/news_translate.py",
    "engine/marketing/breaking_feed.py",
    "engine/marketing/press_providers.py",
    "engine/marketing/press_lane.py",
    "engine/marketing/story_spine.py",
    "engine/marketing/sentinel.py",
    "engine/marketing/__init__.py",
    "engine/codex_provider.py",
    "engine/llm_auth.py",
    "engine/codex_lane/runner.py",
    "lib/ai_costs.py",
    "lib/config.py",
]

PRESS_MUST_NOT_RESTART = [
    # Re-read on every tick.
    "config/marketing.yml",
    "config/press_sources.yml",
    # Artifacts/templates never enter the daemon interpreter.
    "site/news.html",
    "templates/news.html.j2",
    "data/qbus/items.parquet",
    "scripts/build_site.py",
    "admin/server.py",
]


def test_update_reconciles_only_an_installed_press_unit():
    assert '[ -f /etc/systemd/system/marketing-press-feeds.service ]' in SCRIPT
    assert 'systemd-analyze verify "$APP_DIR/app/deploy/marketing-press-feeds.service"' in SCRIPT
    assert "systemctl enable marketing-press-feeds" not in SCRIPT
    assert "systemctl start marketing-press-feeds" not in SCRIPT
    assert "systemctl is-active --quiet marketing-press-feeds" in SCRIPT


@pytest.mark.parametrize("path", PRESS_MUST_RESTART)
def test_press_import_cached_path_triggers_daemon_restart(path):
    assert (ROOT / path).exists(), f"stale test fixture: {path} no longer exists"
    assert _triggers_press_restart(path), (
        f"{path} is import-cached by marketing-press-feeds but does not match "
        "the restart regex in app/deploy/update.sh"
    )


@pytest.mark.parametrize("path", PRESS_MUST_NOT_RESTART)
def test_non_press_path_does_not_restart_daemon(path):
    assert not _triggers_press_restart(path), (
        f"{path} is re-read or unused by marketing-press-feeds; restarting on it "
        "would defeat the narrow lifecycle contract"
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


def _dynamic_modules(tree: ast.AST) -> set[str]:
    """`importlib.import_module("engine.x")` targets, by string literal.

    An Import/ImportFrom scan is blind to these, and admin/ai_cost.py,
    admin/orchestrator_chat.py and admin/neural_web.py reach lib.ai_costs,
    engine.neuralweb.ask_brain, support_map and orchestrator_log ONLY this way —
    so without this the admin closure would silently miss half its seeds.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else None)
        if name != "import_module" or not node.args:
            continue
        arg = node.args[0]
        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                and arg.value.split(".")[0] in _TRACKED_ROOTS):
            found.add(arg.value)
    return found


def _all_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found |= _tracked_modules(node, path)
    return found | _dynamic_modules(tree)


def _ancestor_packages(dotted: str) -> set[str]:
    """Importing a.b.c executes a/__init__.py and a/b/__init__.py first.

    engine/marketing/__init__.py is not inert — it imports state, which pulls in
    ten more modules — so every one of them is pinned in sys.modules by a single
    `from engine.marketing import outbox`.
    """
    parts = dotted.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts))}


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


def _load_time_closure(seed_dir: str) -> set[str]:
    """engine/lib modules guaranteed present in a service's sys.modules.

    Seeded from EVERY engine/lib import in `seed_dir` — the whole directory is
    that service's own code, so even a function-level import there executes
    in-process on some request — then expanded through module-level imports
    only, plus the parent packages Python runs on the way to a submodule.
    Deeper function-level imports need human judgement about whether an endpoint
    reaches them and live in the MUST_RESTART lists instead.
    """
    queue = deque()
    for module in sorted((ROOT / seed_dir).glob("*.py")):
        queue.extend(_all_imports(module))

    seen: set[str] = set()
    reached: set[str] = set()
    while queue:
        dotted = queue.popleft()
        if dotted in seen:
            continue
        seen.add(dotted)
        queue.extend(_ancestor_packages(dotted))
        for path in _module_files(dotted):       # skips symbols (funcs/classes)
            reached.add(str(path.relative_to(ROOT)))
            queue.extend(_module_level_imports(path))
    return reached


def _api_load_time_closure() -> set[str]:
    return _load_time_closure("app")


def _admin_load_time_closure() -> set[str]:
    return _load_time_closure("admin")


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


def test_admin_load_time_import_closure_is_covered_by_restart_regex():
    """Every module the admin panel import-caches must force a restart.

    Fails when someone adds an `engine`/`lib` import to an admin/ panel (or a
    module-level import to something already in the closure) without extending
    the admin trigger regex — the 2026-07-26 engine/marketing/outbox.py gap,
    which shipped dead outbox approve/reject/decide code to the running panel.
    """
    uncovered = sorted(
        rel for rel in _admin_load_time_closure()
        if not _triggers_admin_restart(rel)
        and not _is_inert_package_init(ROOT / rel)
    )
    assert not uncovered, (
        "import-cached by the admin panel but missing from the admin restart "
        f"regex in app/deploy/update.sh: {uncovered}\n"
        "Add them (or, if a path is genuinely content read per request, document "
        "the exemption in the comment above the regex)."
    )


def test_admin_closure_probe_is_not_vacuous():
    """Guard the guard: each seed form the admin closure depends on must work."""
    closure = _admin_load_time_closure()
    # static function-level import (admin/marketing.py)
    assert "engine/marketing/outbox.py" in closure, closure
    # importlib.import_module("...") literals — invisible to an import-line scan
    assert "engine/neuralweb/support_map.py" in closure, closure
    assert "lib/ai_costs.py" in closure, closure
    # package __init__ side effect: `from engine.marketing import outbox` runs
    # __init__ -> state -> the substrate
    assert "engine/marketing/__init__.py" in closure, closure
    assert "engine/marketing/state.py" in closure, closure
    # nightly-only lanes must stay OUT, else the closure is over-broad and the
    # narrow-restart intent is lost
    assert "engine/neuralweb/cortex.py" not in closure
    assert "engine/marketing/seo_director.py" not in closure
    assert "engine/master_brain.py" not in closure


def test_dotted_import_still_reaches_the_package_init():
    """A dotted-only import names no package, but Python still runs its __init__.

    Tested directly because today both spellings appear in admin/marketing.py, so
    `engine.marketing` is seeded either way and the closure probe above cannot
    tell the ancestor walk apart from the plain seed.  It becomes load-bearing the
    moment the last `from engine.marketing import outbox` form goes away — as is
    already the case for macro-api, where brain_gateway only ever writes
    `from engine.marketing.chart_render import ...` and the package __init__ (and
    the twelve-module substrate behind it) is reachable no other way.
    """
    assert _ancestor_packages("engine.marketing.outbox") == {
        "engine", "engine.marketing",
    }
    assert _ancestor_packages("lib") == set()
