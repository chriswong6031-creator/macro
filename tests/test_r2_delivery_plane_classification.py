from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections import Counter
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "r2_delivery_plane_classification.v1.json"
REPORT_PATH = ROOT / "research" / "R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md"
PUBLISHER_PATH = ROOT / "scripts" / "publish_r2.py"
DATA_BASE_PATH = ROOT / "templates" / "data_base.js"
EXTERNAL_EVIDENCE_PATH = ROOT / "tests" / "fixtures" / "r2_delivery_external_evidence.v1.json"
MACRO_RECEIPTS_PATH = ROOT / "tests" / "fixtures" / "r2_delivery_macro_evidence_files.v1.tsv"
TERMINAL_PATHS_PATH = ROOT / "tests" / "fixtures" / "terminal_public_data_b383.paths"
TERMINAL_FIXTURE_TAXONOMY_PATH = (
    ROOT / "tests" / "fixtures" / "terminal_fixture_taxonomy_b383.tsv"
)

EXPECTED_TERMINAL_R2_MAPPINGS = (
    ("meta", "live_flow/meta.json", "live_flow_meta_and_manifest"),
    ("tide", "live_flow/tide_current.json", "live_flow_current"),
    ("dte", "live_flow/dte_tide_current.json", "live_flow_current"),
    ("ticker:ROOT", "live_flow/tickers/ROOT.json", "live_flow_current"),
    ("vol:ROOT", "options_hub/vol/ROOT.json", "options_hub_current"),
    ("gex_dates:ROOT", "options_hub/gex_history/ROOT/dates.json", "options_hub_history"),
    ("gex_at:ROOT:DATE", "options_hub/gex_history/ROOT/DATE.json", "options_hub_history"),
    ("gex:ROOT", "options_hub/gex/ROOT.json", "options_hub_current"),
    ("levels:ROOT", "levels/ROOT.json", "levels_product_and_proof"),
    ("agg:ROOT", "options_hub/aggtrend/ROOT.json", "options_hub_deep_history"),
    ("quad", "options_hub/quad.json", "options_hub_current"),
    ("grades:ROOT", "options_hub/level_grades/ROOT.json", "options_hub_current"),
    ("grades_universe", "options_hub/level_grades/_universe.json", "options_hub_current"),
    ("oi", "options_hub/oi_movers.json", "options_hub_current"),
    ("hot", "options_hub/hot_contracts.json", "options_hub_current"),
    ("ctx", "options_hub/context.json", "options_hub_current"),
    ("oiconf", "options_hub/oi_confirmed.json", "options_hub_current"),
    ("darkpool", "darkpool/eod.json", "terminal_eod_context"),
    ("volregime", "vol/regime.json", "terminal_eod_context"),
    ("moves:ROOT", "options_hub/moves/ROOT.json", "options_hub_current"),
    ("oi_time:ROOT", "options_hub/oi_time/ROOT.json", "options_hub_deep_history"),
    ("max_pain:ROOT", "options_hub/max_pain/ROOT.json", "options_hub_current"),
    ("oi_change", "options_hub/oi_change.json", "options_hub_current"),
    ("oi_change:ROOT", "options_hub/oi_change/ROOT.json", "options_hub_current"),
    ("tctx:ROOT", "options_hub/tickers_ctx/ROOT.json", "options_hub_current"),
    ("chainheat", "live_flow/chain_heat_current.json", "live_flow_current"),
    ("gexstate:ROOT", "options_structure/gex_state/ROOT.json", "options_structure_current"),
    ("gexstate_index", "options_structure/gex_state/_index.json", "options_structure_current"),
    ("matrix:ROOT", "options_structure/matrix/ROOT.json", "options_structure_current"),
    ("surface_dates:ROOT", "live_flow/surface/ROOT/dates.json", "live_flow_surface_history"),
    ("surface_idx_at:ROOT:DATE", "live_flow/surface/ROOT/DATE/idx.json", "live_flow_surface_history"),
    ("surface_at:ROOT:DATE:STAMP", "live_flow/surface/ROOT/DATE/STAMP.json", "live_flow_surface_history"),
    ("surface_idx:ROOT", "live_flow/surface/ROOT/idx.json", "live_flow_surface_history"),
    ("surface:ROOT:STAMP", "live_flow/surface/ROOT/STAMP.json", "live_flow_surface_history"),
    ("manifest", "live_flow/manifest.json", "live_flow_meta_and_manifest"),
    ("flow_idx", "live_flow/flow_idx.json", "flow_leaders_and_radar"),
    ("prophet_idx", "prophet/index.json", "prophet_full_board_product"),
    ("prophet_marks", "live_flow/prophet_marks.json", "prophet_live_product_state"),
    ("options_prophet_idx", "options_prophet/index.json", "options_prophet"),
    ("enrich", "live_flow/enrich_current.json", "live_flow_current"),
    ("leaders", "flowleaders/leaders.json", "flow_leaders_and_radar"),
    ("radar", "leaderradar/radar.json", "flow_leaders_and_radar"),
    ("feed", "live_flow/feed_current.json", "live_flow_current"),
    ("heat", "live_flow/heat_current.json", "live_flow_current"),
)

CLASSIFICATIONS = {
    "PUBLIC_FACT",
    "PREMIUM_PRODUCT",
    "PRIVATE_OPERATIONAL",
    "VENDOR_RAW",
    "UNRESOLVED",
}
TIERS = {
    "ANONYMOUS",
    "FREE",
    "ESSENTIAL",
    "PRO",
    "PRIVATE_SERVICE",
    "OPERATOR_ONLY",
    "HOLD_PRIVATE_PENDING_REVIEW",
}
REQUIRED_FIELDS = {
    "id",
    "key_family",
    "classification",
    "producer",
    "source_directory",
    "publisher",
    "consumers",
    "browser_direct",
    "terminal_or_server_consumer",
    "current_public_url",
    "current_cache_behavior",
    "sensitivity",
    "required_tier",
    "safe_public_schema",
    "migration_dependency",
    "current_plane",
    "covers_publish_r2_dirs",
    "evidence",
}
ANCHOR_RE = re.compile(
    r"^(?P<repo>macro|terminal|mastermind):(?P<path>.+):(?P<line>[1-9][0-9]*)$"
)


@cache
def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@cache
def _external_evidence() -> dict:
    return json.loads(EXTERNAL_EVIDENCE_PATH.read_text(encoding="utf-8"))


def _publisher_dirs() -> set[str]:
    tree = ast.parse(PUBLISHER_PATH.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        name = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        if name in {"DEFAULT_DIRS", "_DATA_DIRS"} and value is not None:
            values[name] = ast.literal_eval(value)
    assert set(values) == {"DEFAULT_DIRS", "_DATA_DIRS"}
    return set(values["DEFAULT_DIRS"]) | set(values["_DATA_DIRS"])


def _rows_by_id() -> dict[str, dict]:
    rows = _registry()["families"]
    return {row["id"]: row for row in rows}


def _all_anchors() -> list[tuple[str, str]]:
    return [
        (row["id"], anchor)
        for row in _registry()["families"]
        for anchor in row["evidence"]
    ]


def _parse_anchor(anchor: str) -> tuple[str, str, int]:
    match = ANCHOR_RE.fullmatch(anchor)
    assert match is not None, anchor
    return match["repo"], match["path"], int(match["line"])


def _macro_receipts() -> tuple[str, dict[str, tuple[int, str]]]:
    lines = MACRO_RECEIPTS_PATH.read_text(encoding="utf-8").splitlines()
    snapshot = lines[0].removeprefix("# source_snapshot=")
    receipts: dict[str, tuple[int, str]] = {}
    for raw in lines[2:]:
        path, line_count, digest = raw.split("\t")
        receipts[path] = (int(line_count), digest)
    return snapshot, receipts


def _terminal_fixture_taxonomy() -> tuple[str, list[dict[str, str]]]:
    lines = TERMINAL_FIXTURE_TAXONOMY_PATH.read_text(encoding="utf-8").splitlines()
    snapshot = lines[0].removeprefix("# source_snapshot=")
    fields = lines[1].removeprefix("# ").split("\t")
    rows = [dict(zip(fields, raw.split("\t"), strict=True)) for raw in lines[2:]]
    return snapshot, rows


@cache
def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    parens = braces = brackets = 0
    for index, char in enumerate(value):
        if char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "," and parens == braces == brackets == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


@cache
def _expand_braces(value: str) -> list[str]:
    stack: list[int] = []
    for index, char in enumerate(value):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            start = stack.pop()
            body = value[start + 1 : index]
            if re.fullmatch(r"[0-9]+(?:,[0-9]*)?", body):
                continue
            choices = _split_top_level(body)
            if len(choices) == 1:
                continue
            expanded: list[str] = []
            for choice in choices:
                expanded.extend(_expand_braces(value[:start] + choice + value[index + 1 :]))
            return expanded
    return [value]


@cache
def _expression_atoms(
    value: str,
    *,
    scope: str = "R2",
    is_default: bool = False,
) -> list[tuple[bool, str, str]]:
    if value.startswith("DEFAULT_DENY:"):
        return _expression_atoms(value.removeprefix("DEFAULT_DENY:"), scope=scope, is_default=True)

    scope_names = tuple(_registry()["key_expression_grammar"]["scopes"])
    for prefix in scope_names:
        if value.startswith(prefix):
            return _expression_atoms(
                value[len(prefix) :],
                scope=prefix.removesuffix(":"),
                is_default=is_default,
            )

    if value.startswith("UNION(") and value.endswith(")"):
        inner = value[len("UNION(") : -1]
        return [
            atom
            for member in _split_top_level(inner)
            for atom in _expression_atoms(member, scope=scope, is_default=is_default)
        ]

    return [(is_default, scope, expanded) for expanded in _expand_braces(value)]


@cache
def _pattern_regex(pattern: str) -> re.Pattern[str]:
    tokens = _registry()["key_expression_grammar"]["tokens"]
    pattern = _replace_named_tokens_once(pattern, tokens)

    out = ""
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            out += ".*"
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            out += "[^/]*"
        elif char == "[":
            end = pattern.index("]", index)
            out += pattern[index : end + 1]
            index = end
        elif char == "{" and re.match(r"\{[0-9]+(?:,[0-9]*)?\}", pattern[index:]):
            match = re.match(r"\{[0-9]+(?:,[0-9]*)?\}", pattern[index:])
            assert match is not None
            out += match.group(0)
            index += len(match.group(0)) - 1
        elif char == "+":
            out += "+"
        else:
            out += re.escape(char)
        index += 1
    return re.compile(f"^{out}$")


@cache
def _compiled_rows() -> tuple[tuple[str, tuple[tuple[bool, str, str], ...]], ...]:
    return tuple(
        (row["id"], tuple(_expression_atoms(row["key_family"])))
        for row in _registry()["families"]
    )


def _effective_family_ids(scope: str, path: str) -> list[str]:
    positive: list[str] = []
    defaults: list[str] = []
    for family_id, atoms in _compiled_rows():
        for is_default, atom_scope, pattern in atoms:
            if atom_scope != scope or _pattern_regex(pattern).fullmatch(path) is None:
                continue
            (defaults if is_default else positive).append(family_id)
            break
    if positive:
        return sorted(set(positive))
    return defaults[:1]


def _replace_named_tokens_once(value: str, replacements: dict[str, str]) -> str:
    names = sorted(replacements, key=len, reverse=True)
    expression = re.compile("|".join(re.escape(name) for name in names))
    return expression.sub(lambda match: replacements[match.group(0)], value)


def _concrete_path(pattern: str) -> str:
    samples = {
        "H64": "a" * 64,
        "H24": "a" * 24,
        "H16": "a" * 16,
        "YEAR": "2026",
        "MONTH": "08",
        "NCT": "NCT00000001",
        "RUN": "ctgov_run_20260812T123456123456Z_" + "a" * 12,
        "HRUN": "ctgov_history_run_NCT00000001_20260812T123456123456Z",
        "EPOCH": "ctgov_coverage_" + "a" * 24,
        "REL": "drugs_at_fda_release_" + "a" * 24,
    }
    pattern = _replace_named_tokens_once(pattern, samples)

    def character_sample(match: re.Match[str]) -> str:
        character_class = match.group(1)
        count = match.group(2)
        if "A-Z" in character_class:
            char = "A"
        elif "a-z" in character_class or "a-f" in character_class:
            char = "a"
        elif "0-9" in character_class:
            char = "0"
        else:
            char = character_class.lstrip("^")[0]
        return char * (int(count) if count else 3)

    pattern = re.sub(r"\[([^]]+)\](?:\{([0-9]+)\}|\+)", character_sample, pattern)
    return pattern.replace("**", "sample/deep").replace("*", "sample")


def test_registry_contract_is_closed_and_complete() -> None:
    registry = _registry()
    assert registry["schema"] == "mastermind.r2_delivery_plane_classification/v1"
    assert registry["census_id"] == "R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08"
    assert registry["as_of"] == "2026-08-12"
    assert set(registry["classification_enum"]) == CLASSIFICATIONS
    assert set(registry["tier_enum"]) == TIERS
    assert registry["policy"]["unknown_default"].startswith("UNRESOLVED")

    snapshots = registry["source_snapshots"]
    assert set(snapshots) == {"macro", "terminal", "mastermind"}
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in snapshots.values())

    projection = registry["projection_contract"]
    assert set(projection) == TIERS | {"required_tier_semantics"}
    assert "complete stored key family" in projection["required_tier_semantics"]
    assert "approximately three" in projection["FREE"]
    assert "zero paid-only remainder" in projection["FREE"]

    grammar = registry["key_expression_grammar"]
    assert "DEFAULT_DENY:x" in grammar["operators"]
    assert set(grammar["tokens"]) == {
        "H64", "H24", "H16", "YEAR", "MONTH", "NCT", "RUN", "HRUN", "EPOCH", "REL",
    }

    rows = registry["families"]
    assert len(rows) >= 100
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["key_family"] for row in rows}) == len(rows)

    forbidden_key_prose = (
        "<",
        " and ",
        " excluding ",
        "not explicitly",
        "equivalent approved",
        "public repository raw path",
        "Terminal /",
    )
    for row in rows:
        assert set(row) == REQUIRED_FIELDS, row["id"]
        assert row["classification"] in CLASSIFICATIONS, row["id"]
        assert row["required_tier"] in TIERS, row["id"]
        assert isinstance(row["browser_direct"], bool), row["id"]
        assert not any(token in row["key_family"] for token in forbidden_key_prose), row["id"]
        for field in REQUIRED_FIELDS - {"browser_direct", "covers_publish_r2_dirs", "evidence"}:
            assert isinstance(row[field], str) and row[field].strip(), (row["id"], field)
        assert isinstance(row["covers_publish_r2_dirs"], list), row["id"]
        assert all(isinstance(item, str) and item for item in row["covers_publish_r2_dirs"])
        assert isinstance(row["evidence"], list) and row["evidence"], row["id"]
        for anchor in row["evidence"]:
            _parse_anchor(anchor)


def test_classification_and_tier_semantics_fail_closed() -> None:
    for row in _registry()["families"]:
        classification = row["classification"]
        tier = row["required_tier"]
        if classification == "PUBLIC_FACT":
            assert tier == "ANONYMOUS", row["id"]
            assert not row["safe_public_schema"].startswith(("None", "Unapproved")), row["id"]
        elif classification == "PREMIUM_PRODUCT":
            assert tier in {"ESSENTIAL", "PRO"}, row["id"]
        elif classification in {"PRIVATE_OPERATIONAL", "VENDOR_RAW"}:
            assert tier in {"PRIVATE_SERVICE", "OPERATOR_ONLY"}, row["id"]
        else:
            assert classification == "UNRESOLVED"
            assert tier == "HOLD_PRIVATE_PENDING_REVIEW", row["id"]

        if row["browser_direct"] and classification != "PUBLIC_FACT":
            assert row["migration_dependency"].strip(), row["id"]
            assert row["safe_public_schema"].strip(), row["id"]


def test_every_generic_publisher_directory_is_registered() -> None:
    covered = {
        directory
        for row in _registry()["families"]
        for directory in row["covers_publish_r2_dirs"]
    }
    assert covered == _publisher_dirs()


def test_browser_data_base_and_registry_share_the_same_public_origin() -> None:
    registry = _registry()
    source = DATA_BASE_PATH.read_text(encoding="utf-8")
    quoted_urls = re.findall(r'https://[^"\s]+', source)
    assert registry["public_r2_base"] in quoted_urls

    match = re.search(r"var RE = /(.+?)/;", source)
    assert match is not None
    browser_pattern = re.compile(match.group(1).replace(r"\/", "/"))
    routed = {
        directory
        for directory in _publisher_dirs()
        if browser_pattern.match(f"{directory}/probe.json")
    }
    assert routed == {
        "ohlc", "chinaohlc", "hkohlc", "intlohlc", "canadaohlc",
        "subsectorohlc", "subsectorohlc_china", "subsectorohlc_russell",
        "subsectorohlc_nasdaq", "stockdata", "chinastockdata", "hkstockdata",
        "canadastockdata", "intlstockdata", "intraday",
    }


def test_security_critical_families_cannot_silently_weaken() -> None:
    rows = _rows_by_id()
    expected = {
        "bulk_market_ohlc": ("PUBLIC_FACT", "ANONYMOUS"),
        "per_ticker_stock_intelligence": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "intraday_chart_bars": ("UNRESOLVED", "HOLD_PRIVATE_PENDING_REVIEW"),
        "attention_raw_store": ("UNRESOLVED", "HOLD_PRIVATE_PENDING_REVIEW"),
        "thetadata_eod_raw_store": ("VENDOR_RAW", "OPERATOR_ONLY"),
        "prophet_full_board_product": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "prophet_full_board_repository_static": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "prophet_repository_operational_state": ("PRIVATE_OPERATIONAL", "OPERATOR_ONLY"),
        "prophet_live_product_state": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "prophet_live_operational_state": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "prophet_mark_observations": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "live_flow_current": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "live_flow_history": ("PREMIUM_PRODUCT", "PRO"),
        "options_hub_current": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "options_hub_deep_history": ("PREMIUM_PRODUCT", "PRO"),
        "options_structure_current": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "options_prophet": ("PRIVATE_OPERATIONAL", "OPERATOR_ONLY"),
        "repository_static_internal_options_state": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "repository_static_internal_options_accruals": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "mastermind_response_logs": ("PRIVATE_OPERATIONAL", "OPERATOR_ONLY"),
        "biocatalyst_vendor_source_evidence": ("VENDOR_RAW", "PRIVATE_SERVICE"),
        "biocatalyst_derived_product_lineage": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "terminal_seed_demo": ("PREMIUM_PRODUCT", "PRO"),
        "terminal_signal_slices": ("PREMIUM_PRODUCT", "PRO"),
        "terminal_fixture_mode_bypass": ("PRIVATE_OPERATIONAL", "OPERATOR_ONLY"),
        "terminal_intraday_gateway": ("UNRESOLVED", "HOLD_PRIVATE_PENDING_REVIEW"),
        "terminal_quote_gateway": ("UNRESOLVED", "HOLD_PRIVATE_PENDING_REVIEW"),
        "terminal_extended_quote_gateway": ("UNRESOLVED", "HOLD_PRIVATE_PENDING_REVIEW"),
        "terminal_washout_state": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "terminal_transcript_corpus": ("VENDOR_RAW", "OPERATOR_ONLY"),
        "terminal_client_proprietary_source": ("PRIVATE_OPERATIONAL", "PRIVATE_SERVICE"),
        "neural_web_market_plane": ("PREMIUM_PRODUCT", "ESSENTIAL"),
        "research_vault": ("PREMIUM_PRODUCT", "PRO"),
        "marketing_chart_media": ("PUBLIC_FACT", "ANONYMOUS"),
    }
    for family_id, disposition in expected.items():
        row = rows[family_id]
        assert (row["classification"], row["required_tier"]) == disposition


def test_open_ended_planes_have_ordered_fail_closed_rows() -> None:
    rows = _rows_by_id()
    expected_defaults = {
        "feeds_unreserved_future_keys",
        "stockdata_reserved_and_future_artifacts",
        "repository_static_internal_options_unregistered",
        "biocatalyst_unregistered_keys",
        "shared_r2_unregistered_objects",
        "macro_public_repository_unregistered_artifacts",
        "terminal_public_data_unregistered_artifacts",
        "primary_static_unregistered_data_artifacts",
    }
    for family_id in expected_defaults:
        assert rows[family_id]["classification"] == "UNRESOLVED"
        assert "DEFAULT_DENY:" in rows[family_id]["key_family"]


def test_every_positive_key_expression_resolves_to_exactly_its_own_family() -> None:
    for row in _registry()["families"]:
        for is_default, scope, pattern in _expression_atoms(row["key_family"]):
            if is_default:
                continue
            path = _concrete_path(pattern)
            assert _effective_family_ids(scope, path) == [row["id"]], (
                row["id"],
                scope,
                pattern,
                path,
                _effective_family_ids(scope, path),
            )


def test_every_default_expression_wins_its_ordered_remainder() -> None:
    for row in _registry()["families"]:
        for is_default, scope, pattern in _expression_atoms(row["key_family"]):
            if not is_default:
                continue
            path = _concrete_path(pattern)
            assert _effective_family_ids(scope, path) == [row["id"]], (
                row["id"],
                scope,
                pattern,
                path,
                _effective_family_ids(scope, path),
            )


def test_every_tracked_macro_site_and_data_path_resolves_exactly_once() -> None:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "site", "data"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = completed.stdout.decode("utf-8").removesuffix("\0").split("\0")
    assert paths and all(path.startswith(("site/", "data/")) for path in paths)
    for path in paths:
        assert len(_effective_family_ids("MACRO_GIT_RAW", path)) == 1, path


def test_all_evidence_anchors_are_pinned_to_reproducible_file_receipts() -> None:
    registry = _registry()
    snapshot, macro_receipts = _macro_receipts()
    external = _external_evidence()
    assert snapshot == registry["source_snapshots"]["macro"]
    assert external["source_snapshots"] == registry["source_snapshots"]

    used_macro_paths: set[str] = set()
    used_external_paths: set[str] = set()
    for family_id, anchor in _all_anchors():
        repo, path, line = _parse_anchor(anchor)
        if repo == "macro":
            assert path in macro_receipts, (family_id, anchor)
            line_count, digest = macro_receipts[path]
            used_macro_paths.add(path)
            # Generated product/state artifacts move normally; their receipt stays tied
            # to the audited SHA. Source and control evidence must not drift silently.
            if not path.startswith(("data/", "site/")):
                current_bytes = (ROOT / path).read_bytes()
                assert len(current_bytes.splitlines()) == line_count, (family_id, anchor)
                assert hashlib.sha256(current_bytes).hexdigest() == digest, (family_id, anchor)
        else:
            receipt_key = f"{repo}:{path}"
            assert receipt_key in external["files"], (family_id, anchor)
            receipt = external["files"][receipt_key]
            line_count, digest = receipt["line_count"], receipt["sha256"]
            used_external_paths.add(receipt_key)
        assert 1 <= line <= line_count, (family_id, anchor)
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (family_id, anchor)

    assert used_macro_paths == set(macro_receipts)
    registry_external_paths = {
        f"{repo}:{path}"
        for _, anchor in _all_anchors()
        for repo, path, _ in [_parse_anchor(anchor)]
        if repo != "macro"
    }
    assert registry_external_paths <= set(external["files"])
    assert used_external_paths == registry_external_paths

    feed_search = external["mastermind_feed_reader_search"]
    assert feed_search["source_snapshot"] == registry["source_snapshots"]["mastermind"]
    assert feed_search["tracked_path_candidates"] == 688
    assert len(feed_search["needles"]) == len(set(feed_search["needles"])) == 13
    assert feed_search["result_line_count"] == 0
    assert feed_search["result_sha256"] == hashlib.sha256(b"").hexdigest()
    assert "bounded source search" in feed_search["claim_boundary"]

    for section_anchor in [
        external["terminal_r2_resolver"]["source_anchor"],
        external["terminal_r2_resolver"]["r2_base_anchor"],
        *external["terminal_r2_resolver"]["qualifications"].values(),
        external["terminal_fixture_controls"]["playwright_assignment_anchor"],
        *(row["anchor"] for row in external["terminal_fixture_controls"]["additional_controls"]),
        external["terminal_alerts_engine"]["deployment_anchor"],
        external["terminal_alerts_engine"]["source_order_anchor"],
        external["terminal_alerts_engine"]["fixture_cli_anchor"],
        *(
            anchor
            for row in external["terminal_alerts_engine"]["mappings"]
            for anchor in (row["fixture_anchor"], row["r2_anchor"])
        ),
        external["terminal_washout_bridge"]["state_puller_anchor"],
        external["terminal_washout_bridge"]["history_puller_anchor"],
        *(anchor for route in external["terminal_route_controls"] for anchor in route["anchors"]),
    ]:
        if not isinstance(section_anchor, str) or not section_anchor.startswith("terminal:"):
            continue
        repo, path, line = _parse_anchor(section_anchor)
        receipt = external["files"][f"{repo}:{path}"]
        assert line <= receipt["line_count"]

    for occurrence in external["terminal_fixture_controls"]["terminal_e2e_fixture_occurrences"]:
        receipt = external["files"][f"terminal:{occurrence['path']}"]
        assert all(1 <= line <= receipt["line_count"] for line in occurrence["lines"])


def test_terminal_inventory_and_resolver_are_complete_and_non_overlapping() -> None:
    external = _external_evidence()
    inventory = external["terminal_public_data"]
    raw_paths = TERMINAL_PATHS_PATH.read_bytes()
    paths = raw_paths.decode("utf-8").splitlines()
    assert raw_paths.endswith(b"\n")
    assert paths == sorted(paths)
    assert len(paths) == inventory["tracked_file_count"] == 134
    assert hashlib.sha256(raw_paths).hexdigest() == inventory["relative_paths_sha256"]
    assert sum(inventory["family_counts"].values()) == 134
    assert inventory["family_counts"] == {
        "base_symbol_json": 34,
        "slice_json": 34,
        "insider_json": 24,
        "intel_json": 2,
        "fixture_json": 38,
        "manifest_json": 1,
        "seed_js": 1,
    }
    fixture_receipt = inventory["fixture_taxonomy"]
    assert fixture_receipt["path"] == str(TERMINAL_FIXTURE_TAXONOMY_PATH.relative_to(ROOT))
    assert fixture_receipt["file_count"] == 38
    assert fixture_receipt["sha256"] == hashlib.sha256(
        TERMINAL_FIXTURE_TAXONOMY_PATH.read_bytes()
    ).hexdigest()

    for relative in paths:
        assert len(_effective_family_ids("TERMINAL_STATIC", f"/data/{relative}")) == 1, relative
        assert len(_effective_family_ids("TERMINAL_GIT_RAW", f"terminal/public/data/{relative}")) == 1, relative

    mappings = external["terminal_r2_resolver"]["mappings"]
    mapping_tuples = tuple(tuple(item) for item in mappings)
    assert mapping_tuples == EXPECTED_TERMINAL_R2_MAPPINGS
    canonical_tsv = "".join("\t".join(item) + "\n" for item in mapping_tuples).encode()
    assert hashlib.sha256(canonical_tsv).hexdigest() == (
        "fe3980a0c2465660db7fc1a52581301b1b1cbaa79ad068b30283ae61bf3b3747"
    )
    assert len({selector for selector, _, _ in mappings}) == len(mappings)
    assert len({(selector, key) for selector, key, _ in mappings}) == len(mappings)
    rows = _rows_by_id()
    for selector, key, family_id in mappings:
        assert family_id in rows, selector
        concrete = key.replace("ROOT", "SPY").replace("DATE", "2026-08-11").replace("STAMP", "1030")
        assert _effective_family_ids("R2", concrete) == [family_id], (selector, concrete)

    exact_options = {(selector, key) for selector, key, _ in mappings}
    assert {
        ("oi", "options_hub/oi_movers.json"),
        ("hot", "options_hub/hot_contracts.json"),
        ("ctx", "options_hub/context.json"),
        ("oiconf", "options_hub/oi_confirmed.json"),
        ("quad", "options_hub/quad.json"),
        ("oi_change", "options_hub/oi_change.json"),
    } <= exact_options

    qualifications = external["terminal_r2_resolver"]["qualifications"]
    assert qualifications["manifest_runtime_source"] == "TERMINAL_STATIC:/data/manifest.json"
    assert qualifications["default_source_order"] == ["backend", "r2"]
    assert qualifications["options_prophet_source_order"] == ["r2", "backend"]
    assert qualifications["flow_idx_final_fallback"] == (
        "https://mastermindx-market-intelligence.github.io/macro/flow/index.json"
    )


def test_terminal_fixtures_are_classified_by_content_not_suffix() -> None:
    snapshot, taxonomy = _terminal_fixture_taxonomy()
    assert snapshot == _registry()["source_snapshots"]["terminal"]
    assert len(taxonomy) == 38
    paths = [row["path"] for row in taxonomy]
    expected_paths = {
        f"terminal/public/data/{path}"
        for path in TERMINAL_PATHS_PATH.read_text(encoding="utf-8").splitlines()
        if path.endswith("_fixture.json")
    }
    assert len(paths) == len(set(paths))
    assert set(paths) == expected_paths

    registry_rows = _rows_by_id()
    tier_counts = Counter(row["required_tier"] for row in taxonomy)
    assert tier_counts == {
        "ESSENTIAL": 30,
        "PRO": 6,
        "OPERATOR_ONLY": 1,
        "HOLD_PRIVATE_PENDING_REVIEW": 1,
    }
    for fixture in taxonomy:
        assert int(fixture["bytes"]) > 0
        assert re.fullmatch(r"[0-9a-f]{64}", fixture["sha256"])
        assert fixture["content_basis"].strip()
        family = registry_rows[fixture["family_id"]]
        assert fixture["classification"] == family["classification"]
        assert fixture["required_tier"] == family["required_tier"]
        relative = fixture["path"].removeprefix("terminal/public/data/")
        assert _effective_family_ids("TERMINAL_STATIC", f"/data/{relative}") == [
            fixture["family_id"]
        ]
        assert _effective_family_ids("TERMINAL_GIT_RAW", fixture["path"]) == [
            fixture["family_id"]
        ]


def test_terminal_fixture_and_alert_controls_are_complete() -> None:
    external = _external_evidence()
    controls = external["terminal_fixture_controls"]
    search = controls["terminal_e2e_fixture_search"]
    assert search == {
        "source_snapshot": _registry()["source_snapshots"]["terminal"],
        "tracked_path_candidates": 67,
        "scope": "git grep -n -I TERMINAL_E2E_FIXTURE at the pinned tree under terminal/app",
        "result_line_count": 11,
        "result_path_count": 8,
        "result_sha256": "402b034428176192fa64d7fdbe3830080742c8b36db558135b212d31a07bf31c",
    }
    occurrences = controls["terminal_e2e_fixture_occurrences"]
    assert {row["path"] for row in occurrences} == {
        "terminal/app/api/company-institutional-context/[symbol]/route.ts",
        "terminal/app/api/company-theme-context/[symbol]/route.ts",
        "terminal/app/api/company-source-search/[ticker]/route.ts",
        "terminal/app/(shell)/discover/page.tsx",
        "terminal/app/(shell)/alerts/page.tsx",
        "terminal/app/(shell)/portfolio/page.tsx",
        "terminal/app/api/me/route.ts",
        "terminal/app/terminal/page.tsx",
    }
    assert len(occurrences) == search["result_path_count"]
    assert sum(len(row["lines"]) for row in occurrences) == search["result_line_count"]
    assert sum("bypass" in row["behavior"] for row in occurrences) == 6
    assert any(row["behavior"] == "nonproduction_only_entitlement_stub" for row in occurrences)
    assert any(row["behavior"] == "guest_open_page_deterministic_ui_data" for row in occurrences)

    additional = {row["control"] for row in controls["additional_controls"]}
    assert additional == {
        "FLOW_FIXTURE=1",
        "NW_FIXTURE=1",
        "COMPANY_INTELLIGENCE_FIXTURE=1",
        "ANALYSIS_LOCAL_PREVIEW=1",
        "alerts_engine.py --flow-fixtures",
    }
    registry_control = _rows_by_id()["terminal_fixture_mode_bypass"]
    for token in (
        "FLOW_FIXTURE=1",
        "NW_FIXTURE=1",
        "TERMINAL_E2E_FIXTURE=1",
        "TERMINAL_E2E_ENTITLEMENT=*",
        "COMPANY_INTELLIGENCE_FIXTURE=1",
        "ANALYSIS_LOCAL_PREVIEW=1",
        "--flow-fixtures",
    ):
        assert token in registry_control["key_family"]
    assert "absent or false" in controls["launch_assertion"]

    alerts = external["terminal_alerts_engine"]
    assert alerts["source_order"] == ["backend", "r2"]
    assert "no-cache" in alerts["request_cache"]
    assert "eight-second" in alerts["request_cache"]
    expected = (
        ("options_structure_current", "/api/hub/gexstate/ROOT", "options_structure/gex_state/ROOT.json"),
        ("options_hub_current", "/api/hub/gex/ROOT", "options_hub/gex/ROOT.json"),
        ("live_flow_current", "/api/flow/tide", "live_flow/tide_current.json"),
        ("live_flow_current", "/api/flow/dte", "live_flow/dte_tide_current.json"),
        ("live_flow_surface_history", "/api/flow/surface/ROOT/idx", "live_flow/surface/ROOT/idx.json"),
        ("live_flow_surface_history", "/api/flow/surface/ROOT/STAMP", "live_flow/surface/ROOT/STAMP.json"),
    )
    assert tuple(
        (row["family_id"], row["backend_path"], row["r2_key"])
        for row in alerts["mappings"]
    ) == expected
    rows = _rows_by_id()
    taxonomy = {
        row["path"].removeprefix("terminal/public/data/"): row["family_id"]
        for row in _terminal_fixture_taxonomy()[1]
    }
    for mapping in alerts["mappings"]:
        concrete = mapping["r2_key"].replace("ROOT", "SPY").replace("STAMP", "1030")
        assert _effective_family_ids("R2", concrete) == [mapping["family_id"]]
        assert "Alerts Engine" in rows[mapping["family_id"]]["consumers"]
        for fixture in mapping["fixture_paths"]:
            if fixture in taxonomy:
                assert taxonomy[fixture] == mapping["family_id"]


def test_washout_aliases_and_legacy_factordata_are_exact() -> None:
    bridge = _external_evidence()["terminal_washout_bridge"]
    assert bridge["classification"] == "PRIVATE_OPERATIONAL"
    assert bridge["required_tier"] == "PRIVATE_SERVICE"
    aliases = {tuple(row) for row in bridge["aliases"]}
    assert aliases == {
        ("R2", "factordata/basket_washout_state.json", "terminal_washout_state"),
        ("R2", "factordata/basket_washout_history.json", "terminal_washout_state"),
        ("PRIMARY_STATIC", "/factordata/basket_washout_state.json", "terminal_washout_state"),
        ("PRIMARY_STATIC", "/factordata/basket_washout_history.json", "terminal_washout_state"),
        ("MACRO_GIT_RAW", "site/factordata/basket_washout_state.json", "terminal_washout_state"),
        ("MACRO_GIT_RAW", "site/factordata/basket_washout_history.json", "terminal_washout_state"),
        ("TERMINAL_STATIC", "/data/washout_state.json", "terminal_washout_state"),
        ("TERMINAL_STATIC", "/data/washout_history.json", "terminal_washout_state"),
    }
    for scope, path, family_id in aliases:
        assert _effective_family_ids(scope, path) == [family_id]

    rows = _rows_by_id()
    washout = rows["terminal_washout_state"]
    assert (washout["classification"], washout["required_tier"]) == (
        bridge["classification"], bridge["required_tier"]
    )
    assert _effective_family_ids("PRIMARY_STATIC", "/factordata/tech_lab.json") == [
        "terminal_legacy_factordata"
    ]
    assert _effective_family_ids(
        "PRIMARY_STATIC", "/factordata/tech_events/NVDA.json"
    ) == ["terminal_legacy_factordata"]
    assert _effective_family_ids("MACRO_GIT_RAW", "site/factordata/tech_lab.json") == [
        "terminal_legacy_factordata"
    ]
    assert _effective_family_ids(
        "MACRO_GIT_RAW", "site/factordata/tech_events/NVDA.json"
    ) == ["terminal_legacy_factordata"]
    assert _effective_family_ids("PRIMARY_STATIC", "/factordata/new_unknown.json") == [
        "primary_static_unregistered_data_artifacts"
    ]
    assert _effective_family_ids("R2", "factordata/new_unknown.json") == [
        "shared_r2_unregistered_objects"
    ]


def test_unknown_keys_resolve_once_to_unresolved_default_deny() -> None:
    probes = {
        ("R2", "totally_new/key.json"): "shared_r2_unregistered_objects",
        ("R2", "feeds/new_unknown.json"): "feeds_unreserved_future_keys",
        ("R2", "stockdata/new_unknown.bin"): "stockdata_reserved_and_future_artifacts",
        ("MACRO_GIT_RAW", "site/new_private.json"): "macro_public_repository_unregistered_artifacts",
        ("MACRO_GIT_RAW", "data/options_flow/new_unknown.bin"):
            "repository_static_internal_options_unregistered",
        ("TERMINAL_STATIC", "/data/new_unknown.bin"): "terminal_public_data_unregistered_artifacts",
        ("TERMINAL_GIT_RAW", "terminal/public/data/new_unknown.bin"): "terminal_public_data_unregistered_artifacts",
        ("PRIMARY_STATIC", "/feeds/new_unknown.json"): "primary_static_unregistered_data_artifacts",
        ("PRIMARY_STATIC", "/factordata/new_unknown.json"): "primary_static_unregistered_data_artifacts",
        ("PRIMARY_STATIC", "/prophet/new_unknown.json"): "primary_static_unregistered_data_artifacts",
        ("PRIMARY_STATIC", "/live/new_unknown.json"): "primary_static_unregistered_data_artifacts",
        ("PRIMARY_STATIC", "/options_prophet/new_unknown.json"): "primary_static_unregistered_data_artifacts",
        ("PRIMARY_STATIC", "/chinastockdata/new_unknown.bin"): "primary_static_unregistered_data_artifacts",
        ("PRIVATE_STORE", "biocatalyst/new_unknown.json"): "biocatalyst_unregistered_keys",
    }
    rows = _rows_by_id()
    for (scope, path), family_id in probes.items():
        assert _effective_family_ids(scope, path) == [family_id]
        assert rows[family_id]["classification"] == "UNRESOLVED"


def test_biocatalyst_exact_shapes_reject_malformed_near_misses() -> None:
    run_id = "ctgov_run_20260812T123456123456Z_" + "a" * 12
    history_run = "ctgov_history_run_NCT00000001_20260812T123456123456Z"
    valid = {
        (
            "biocatalyst/source_snapshots/clinicaltrials/NCT00000001/"
            f"ctgov_snapshot_NCT00000001_{run_id.removeprefix('ctgov_run_')}_{'b' * 64}.json"
        ): "biocatalyst_vendor_source_evidence",
        (
            "biocatalyst/receipts/clinicaltrials/2026/08/"
            f"{run_id}/0.json"
        ): "biocatalyst_operational_receipts",
        (
            "biocatalyst/receipts/clinicaltrials/history/2026/08/"
            f"{history_run}/ctgov_history_receipt_"
            "NCT00000001_20260812T123456123456Z_index_pre.json"
        ): "biocatalyst_operational_receipts",
        (
            "biocatalyst/manifests/drugs_at_fda/"
            f"drugs_at_fda_release_{'c' * 24}/Applications.txt.json"
        ): "biocatalyst_operational_receipts",
        (
            "biocatalyst/raw/clinicaltrials/v2/failed-fetch/2026/08/"
            f"{run_id}/studies/0/{'d' * 64}.bin"
        ): "biocatalyst_reserved_failure_evidence",
    }
    for path, family_id in valid.items():
        assert _effective_family_ids("PRIVATE_STORE", path) == [family_id]

    malformed = (
        ("biocatalyst/raw/clinicaltrials/v2/version/2026/08/"
        f"{run_id}/during/{'b' * 64}.json"),
        ("biocatalyst/raw/clinicaltrials/v2/pages/2026/08/"
        f"{run_id}/page/{'b' * 64}.json"),
        f"biocatalyst/raw/clinicaltrials/v2/NCT00000001/nested/{'b' * 64}.json",
        ("biocatalyst/raw/clinicaltrials/history/NCT00000001/"
        f"version-latest/{'b' * 64}.json"),
        f"biocatalyst/raw/drugs_at_fda/landing/{'b' * 64}.zip",
        "biocatalyst/source_snapshots/clinicaltrials/NCT00000001/foo/bar.json",
        ("biocatalyst/source_snapshots/clinicaltrials/history/"
        "NCT00000001/foo/bar.json"),
        ("biocatalyst/receipts/clinicaltrials/version/2026/08/"
        f"{run_id}/during.json"),
        ("biocatalyst/receipts/clinicaltrials/2026/08/"
        f"{run_id}/page.json"),
        ("biocatalyst/receipts/clinicaltrials/history/2026/08/"
        f"{history_run}/unexpected.json"),
        "biocatalyst/runs/clinicaltrials/garbage.bin",
        "biocatalyst/runs/clinicaltrials/history/2026/08/garbage.json",
        f"biocatalyst/attempts/drugs_at_fda/{'b' * 64}/short.json",
        f"biocatalyst/receipts/drugs_at_fda/drugs_at_fda_release_{'b' * 23}.json",
        ("biocatalyst/manifests/drugs_at_fda/"
        f"drugs_at_fda_release_{'c' * 24}/Unexpected.txt.json"),
        ("biocatalyst/commits/drugs_at_fda/"
        f"drugs_at_fda_release_{'c' * 24}/{'b' * 63}.json"),
        f"biocatalyst/activation-preflight/r2_preflight_{'b' * 23}.json",
        "biocatalyst/mirror_receipts/ctgov_run_freeform.json",
        ("biocatalyst/derived/clinicaltrials/history/NCT00000001/"
        f"models/{'b' * 64}.json"),
        ("biocatalyst/derived/clinicaltrials/prospective/epochs/"
        f"ctgov_coverage_{'b' * 24}/ctgov_run_freeform.json"),
        ("biocatalyst/derived/clinicaltrials/prospective/"
        f"ctgov_coverage_{'b' * 24}/NCT00000001/models/nested/{'b' * 64}.json"),
        ("biocatalyst/derived/clinicaltrials/prospective/"
        f"ctgov_coverage_{'b' * 24}/NCT00000001/observations/short.json"),
        ("biocatalyst/derived/clinicaltrials/prospective/"
        f"ctgov_coverage_{'b' * 24}/NCT00000001/diffs/{'b' * 64}.bin"),
        ("biocatalyst/raw/clinicaltrials/v2/failed-fetch/2026/08/"
        f"{run_id}/version/during/{'d' * 64}.bin"),
        ("biocatalyst/raw/clinicaltrials/v2/failed-fetch/2026/08/"
        f"{run_id}/unknown/0/{'d' * 64}.bin"),
        ("biocatalyst/incidents/clinicaltrials/2026/08/"
        f"{run_id}.unknown.json"),
    )
    for path in malformed:
        assert _effective_family_ids("PRIVATE_STORE", path) == [
            "biocatalyst_unregistered_keys"
        ]


def test_machine_registry_pins_exact_root_options_and_repository_aliases() -> None:
    rows = _rows_by_id()
    options = rows["options_hub_current"]["key_family"]
    for key in (
        "oi_change.json", "oi_movers.json", "hot_contracts.json",
        "context.json", "oi_confirmed.json", "quad.json",
    ):
        assert key in options

    assert rows["prophet_full_board_repository_static"]["key_family"] == (
        "UNION(MACRO_GIT_RAW:site/prophet/{index.json,plans/*.json,states/*.json},"
        "PRIMARY_STATIC:/prophet/{plans/*.json,states/*.json})"
    )
    assert rows["prophet_repository_operational_state"]["key_family"] == (
        "MACRO_GIT_RAW:data/{prophet/**,prophet_arena/**}"
    )
    assert rows["prophet_showcase"]["key_family"] == (
        "UNION(PRIMARY_STATIC:/prophet/showcase.json,MACRO_GIT_RAW:site/prophet/showcase.json)"
    )
    assert "site/options_prophet/index.json" in rows["options_prophet"]["key_family"]
    assert "tape_signing_sessions.jsonl" in rows["repository_static_internal_options_state"]["key_family"]
    assert "raw/_manifest.json" in rows["repository_static_internal_options_state"]["key_family"]


def test_known_primary_and_repository_aliases_keep_the_same_disposition() -> None:
    rows = _rows_by_id()
    alias_groups = (
        (
            ("R2", "prophet/index.json", "prophet_full_board_product"),
            ("PRIMARY_STATIC", "/prophet/index.json", "prophet_full_board_product"),
            ("MACRO_GIT_RAW", "site/prophet/index.json", "prophet_full_board_repository_static"),
        ),
        (
            ("PRIMARY_STATIC", "/prophet/plans/NVDA-BULL-20260812.json", "prophet_full_board_repository_static"),
            ("MACRO_GIT_RAW", "site/prophet/plans/NVDA-BULL-20260812.json", "prophet_full_board_repository_static"),
        ),
        (
            ("R2", "stockdata/SPY.json", "per_ticker_stock_intelligence"),
            ("PRIMARY_STATIC", "/stockdata/SPY.json", "per_ticker_stock_intelligence"),
        ),
        (
            ("R2", "chinastockdata/0700.json", "per_ticker_stock_intelligence"),
            ("PRIMARY_STATIC", "/chinastockdata/0700.json", "per_ticker_stock_intelligence"),
        ),
        (
            ("R2", "stockdata/index.json", "stock_search_indices"),
            ("PRIMARY_STATIC", "/stockdata/index.json", "stock_search_indices"),
        ),
        (
            ("R2", "stockdata/calibration.json", "stockdata_calibration_state"),
            ("PRIMARY_STATIC", "/stockdata/calibration.json", "stockdata_calibration_state"),
        ),
        (
            ("R2", "live_flow/prophet_live.json", "prophet_live_product_state"),
            ("PRIMARY_STATIC", "/live/prophet_live.json", "prophet_live_product_state"),
        ),
        (
            ("R2", "options_prophet/index.json", "options_prophet"),
            ("PRIMARY_STATIC", "/options_prophet/index.json", "options_prophet"),
            ("MACRO_GIT_RAW", "site/options_prophet/index.json", "options_prophet"),
        ),
    )
    for aliases in alias_groups:
        dispositions = set()
        for scope, path, family_id in aliases:
            assert _effective_family_ids(scope, path) == [family_id]
            row = rows[family_id]
            dispositions.add((row["classification"], row["required_tier"]))
        assert len(dispositions) == 1, aliases


def test_terminal_route_controls_preserve_auth_and_cache_truth() -> None:
    controls = {row["route"]: row for row in _external_evidence()["terminal_route_controls"]}
    assert set(controls) == {
        "TERMINAL_ROUTE:/api/flow",
        "TERMINAL_ROUTE:/api/flow/stream",
        "TERMINAL_ROUTE:/api/intraday",
        "TERMINAL_ROUTE:/api/nw",
        "TERMINAL_ROUTE:/api/company-institutional-context/[symbol]",
        "TERMINAL_ROUTE:/api/company-theme-context/[symbol]",
        "TERMINAL_ROUTE:/api/company-source-search/[ticker]",
        "TERMINAL_ROUTE:/api/quote",
        "TERMINAL_ROUTE:/api/ext-quote",
    }
    assert "FLOW_FIXTURE=1" in controls["TERMINAL_ROUTE:/api/flow"]["auth"]
    assert "FLOW_FIXTURE=1" in controls["TERMINAL_ROUTE:/api/intraday"]["auth"]
    assert "fixture-success" in controls["TERMINAL_ROUTE:/api/intraday"]["cache"]
    assert controls["TERMINAL_ROUTE:/api/nw"]["auth"] == "none"
    assert "invalid-f 400" in controls["TERMINAL_ROUTE:/api/nw"]["cache"]
    assert "not Pro-aware" in controls[
        "TERMINAL_ROUTE:/api/company-institutional-context/[symbol]"
    ]["auth"]
    assert "30 seconds" in controls[
        "TERMINAL_ROUTE:/api/company-institutional-context/[symbol]"
    ]["cache"]
    assert "not plan-aware" in controls[
        "TERMINAL_ROUTE:/api/company-theme-context/[symbol]"
    ]["auth"]
    assert "deterministic test source" in controls[
        "TERMINAL_ROUTE:/api/company-source-search/[ticker]"
    ]["auth"]
    assert controls["TERMINAL_ROUTE:/api/ext-quote"]["auth"] == "none"
    assert "after cache miss" in controls["TERMINAL_ROUTE:/api/quote"]["auth"]
    assert "unauthenticated-401" in controls["TERMINAL_ROUTE:/api/quote"]["cache"]
    assert "omits explicit cache control" in controls["TERMINAL_ROUTE:/api/ext-quote"]["cache"]


def test_human_report_and_machine_counts_do_not_drift() -> None:
    registry = _registry()
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert registry["census_id"].replace("_", " ").title() not in report
    assert "r2_delivery_plane_classification.v1.json" in report
    assert f"**{len(registry['families'])} non-overlapping delivery families**" in report
    counts = Counter(row["classification"] for row in registry["families"])
    for classification in sorted(CLASSIFICATIONS):
        assert f"| `{classification}` | {counts[classification]} |" in report
