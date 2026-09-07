#!/usr/bin/env python3
"""Reproduce the P0B stock-dashboard browser fixture without ambient state.

This is an evidence recipe, not a production builder.  It renders the candidate
HK and Canada Jinja templates with fixed auxiliary context and small immutable
owner-identity fixtures committed beside the evidence.  It never reads a live
``site/factordata`` snapshot, developer VM cache, collector, publish target, or
ledger.  The receipt binds every repository input actually loaded by Jinja and
the exact output bytes with SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

MARKETS = {
    "hk": {
        "template": "hk.html.j2",
        "owner_fixture": (
            "mockups/evidence/prophet-p0b-zero-fouc/inputs/hk-owner-fixture.json"
        ),
        "action_fixture": (
            "mockups/evidence/prophet-p0b-zero-fouc/inputs/hk-action-fixture.json"
        ),
        "output": "hk_stocks.html",
    },
    "ca": {
        "template": "canada.html.j2",
        "owner_fixture": (
            "mockups/evidence/prophet-p0b-zero-fouc/inputs/"
            "canada-owner-fixture.json"
        ),
        "action_fixture": (
            "mockups/evidence/prophet-p0b-zero-fouc/inputs/"
            "canada-action-fixture.json"
        ),
        "output": "canada_stocks.html",
    },
}

OWNER_CASES = ("normal", "watch-only", "null-buy")

MEMBERSHIP_OVERLAYS = {
    "hk": {
        "group": {
            "kind": "sector",
            "id": "FIXTURE-FINANCE",
            "name": "Fixture finance",
            "research_href": "sectors/FIXTURE-FINANCE.html",
        },
        "members": (
            {"ticker": "2318.HK", "owner_lane": "ran"},
            {"ticker": "2331.HK", "owner_lane": "watch"},
        ),
        "control": {
            "selector": (
                '[data-action-id="FIXTURE-FINANCE"] '
                ".anv2-name.hk-v37-an-row"
            ),
            "remove_attributes": ["disabled"],
            "set_attributes": {"data-hk-lead-id": "FIXTURE-FINANCE"},
        },
    },
    "ca": {
        "group": {
            "kind": "sector",
            "id": "FIXTURE-FINANCE",
            "name": "Fixture finance",
            "research_href": "sectors/FIXTURE-FINANCE.html",
        },
        "members": (
            {"ticker": "PMZ-UN.TO", "owner_lane": "watch"},
            {"ticker": "MTL.TO", "owner_lane": "watch"},
        ),
        "control": {
            "selector": (
                '[data-action-id="FIXTURE-FINANCE"] '
                ".anv2-name.ca-v36-an-row"
            ),
            "remove_attributes": ["disabled"],
            "set_attributes": {
                "data-ca-lead-kind": "sector",
                "data-ca-lead-id": "FIXTURE-FINANCE",
            },
        },
    },
}

OWNER_LANES = {
    "hk": ("buy", "ripening", "ran", "vetoed", "watch"),
    "ca": ("buy", "watch"),
}

ACTION_LANES = (
    "buy_now",
    "buy_soon",
    "on_the_run",
    "take_profits",
    "hold",
    "avoid",
)

OWNER_SOURCES = {
    "hk": "site/factordata/hk_standouts.json",
    "ca": "site/factordata/canada_standouts.json",
}

IDENTITY_EXTRACTION = (
    "identity fields only from the named owner lanes; non-owner presentation "
    "fields are neutral fixture values"
)


class FixtureBlank:
    """False/empty scalar used only for deliberately absent non-owner fields.

    The frozen input records owner identity and membership, while this sentinel
    lets the existing templates render their unrelated numeric and collection
    decorations deterministically.  It never enters the receipt or owner-count
    calculation; those use the explicit JSON lanes only.
    """

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return "FixtureBlank()"

    def __len__(self) -> int:
        return 0

    def __iter__(self):
        return iter(())

    def __float__(self) -> float:
        return 0.0

    def __int__(self) -> int:
        return 0

    def __format__(self, spec: str) -> str:
        return format(0.0, spec)

    def __getitem__(self, _key: object) -> "FixtureBlank":
        return self

    def __getattr__(self, _key: str) -> "FixtureBlank":
        return self

    def get(self, _key: object, default: Any = None) -> Any:
        return default

    def keys(self) -> tuple[()]:
        return ()

    def values(self) -> tuple[()]:
        return ()

    def items(self) -> tuple[()]:
        return ()

    def __call__(self, *_args: object, **_kwargs: object) -> "FixtureBlank":
        return self

    def __eq__(self, _other: object) -> bool:
        return False

    def __lt__(self, _other: object) -> bool:
        return False

    def __le__(self, _other: object) -> bool:
        return False

    def __gt__(self, _other: object) -> bool:
        return False

    def __ge__(self, _other: object) -> bool:
        return False

    def __add__(self, other: Any) -> Any:
        return other

    def __radd__(self, other: Any) -> Any:
        return other

    def __sub__(self, other: Any) -> Any:
        return -other

    def __rsub__(self, other: Any) -> Any:
        return other

    def __mul__(self, _other: object) -> int:
        return 0

    def __rmul__(self, _other: object) -> int:
        return 0

    def __truediv__(self, _other: object) -> int:
        return 0

    def __rtruediv__(self, _other: object) -> int:
        return 0


FIXTURE_BLANK = FixtureBlank()


class FixtureRow(dict[str, Any]):
    """Mapping whose absent presentation-only fields degrade deterministically."""

    def __missing__(self, _key: str) -> FixtureBlank:
        return FIXTURE_BLANK


def _fixture_row(identity: dict[str, Any], lane: str, ordinal: int) -> FixtureRow:
    """Expand one immutable owner identity into a neutral presentation row."""
    row = FixtureRow(identity)
    fixture_sector = (
        "Fixture sector"
        if lane != "buy" or ordinal <= 2
        else "Fixture growth"
    )
    stage = identity.get("stage") or {
        "ripening": "setting_up",
        "ran": "ran",
        "vetoed": "blocked",
    }.get(lane, lane)
    row.update(
        {
            "alpha": 0.0,
            "board_pos": ordinal,
            "conviction": FixtureRow(
                {
                    "score": 0,
                    "verdict": "Fixture",
                    "verdict_zh": "固定样本",
                }
            ),
            "display_only": True,
            "display_rank": ordinal,
            "label": "Fixture",
            "label_zh": "固定样本",
            "lane": lane,
            "price": 100.0 + ordinal,
            "score_rank": ordinal,
            "sector": fixture_sector,
            "sector_zh": "固定板块",
            "stage": stage,
            "stance": "Fixture",
            "stance_zh": "固定样本",
        }
    )
    return row


def load_owner_fixture(market: str) -> tuple[FixtureRow, Path]:
    """Validate and expand the immutable identity fixture for one market."""
    spec = MARKETS[market]
    path = ROOT / spec["owner_fixture"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{market}: owner fixture root must be an object")
    if payload.get("schema") != "mastermind.stock_dashboard_owner_fixture.v1":
        raise ValueError(f"{market}: unknown owner fixture schema")
    if payload.get("market") != market:
        raise ValueError(f"{market}: owner fixture market mismatch")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(f"{market}: owner fixture provenance must be an object")
    if provenance.get("source_path") != OWNER_SOURCES[market]:
        raise ValueError(f"{market}: owner fixture source path mismatch")
    if provenance.get("extraction") != IDENTITY_EXTRACTION:
        raise ValueError(f"{market}: owner fixture extraction contract mismatch")
    for key, length in (("source_git_commit", 40), ("source_sha256", 64)):
        value = provenance.get(key)
        if (
            not isinstance(value, str)
            or len(value) != length
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError(f"{market}: owner fixture {key} is not lowercase hex")
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(OWNER_LANES[market]):
        raise ValueError(f"{market}: owner fixture lanes mismatch")

    setups = FixtureRow({"as_of": payload.get("as_of")})
    if market == "hk":
        board_definition = payload.get("board_definition")
        if not isinstance(board_definition, str) or not board_definition.startswith(
            "hk_prophet_v"
        ):
            raise ValueError("hk: owner fixture requires a Prophet board definition")
        setups["board_definition"] = board_definition
    seen: set[str] = set()
    for lane in OWNER_LANES[market]:
        identities = lanes[lane]
        if not isinstance(identities, list):
            raise ValueError(f"{market}.{lane}: owner lane must be a list")
        rows: list[FixtureRow] = []
        for ordinal, identity in enumerate(identities, start=1):
            if not isinstance(identity, dict):
                raise ValueError(f"{market}.{lane}: owner identity must be an object")
            ticker = identity.get("ticker")
            name = identity.get("name")
            if (
                not isinstance(ticker, str)
                or not ticker.strip()
                or not isinstance(name, str)
                or not name.strip()
            ):
                raise ValueError(f"{market}.{lane}: owner identity requires ticker/name")
            normalized_ticker = ticker.strip().upper()
            if normalized_ticker in seen:
                raise ValueError(f"{market}: duplicate owner ticker {normalized_ticker}")
            if market == "hk" and lane == "buy" and identity.get("stage") not in {
                "live",
                "setting_up",
            }:
                raise ValueError("hk.buy: owner identity requires a valid stage")
            seen.add(normalized_ticker)
            normalized_identity = dict(identity)
            normalized_identity["ticker"] = normalized_ticker
            rows.append(_fixture_row(normalized_identity, lane, ordinal))
        setups[lane] = rows
    return setups, path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def inside(path: Path, parent: Path) -> bool:
    resolved = path.resolve()
    base = parent.resolve()
    return resolved == base or base in resolved.parents


class TrackingLoader(FileSystemLoader):
    """File-system loader that records every template Jinja actually opens."""

    def __init__(self, searchpath: Path) -> None:
        super().__init__(str(searchpath))
        self.loaded: set[Path] = set()

    def get_source(self, environment: Environment, template: str):  # type: ignore[override]
        source, filename, uptodate = super().get_source(environment, template)
        resolved = Path(filename).resolve()
        if not inside(resolved, TEMPLATES):
            raise RuntimeError(f"template escaped templates/: {resolved}")
        self.loaded.add(resolved)
        return source, filename, uptodate


def common_actions() -> dict[str, list[Any]]:
    return {lane: [] for lane in ACTION_LANES}


def load_action_fixture(market: str) -> tuple[dict[str, list[FixtureRow]], Path]:
    """Load a typed, explicitly synthetic action classification for browser QA."""
    path = ROOT / MARKETS[market]["action_fixture"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{market}: action fixture root must be an object")
    if payload.get("schema") != "mastermind.stock_dashboard_action_fixture.v1":
        raise ValueError(f"{market}: unknown action fixture schema")
    if payload.get("market") != market:
        raise ValueError(f"{market}: action fixture market mismatch")
    if payload.get("classification") != "frozen_browser_contract_fixture_only":
        raise ValueError(f"{market}: action fixture classification mismatch")
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, dict) or set(raw_actions) != set(ACTION_LANES):
        raise ValueError(f"{market}: action fixture lanes mismatch")
    actions: dict[str, list[FixtureRow]] = {}
    seen: set[str] = set()
    for lane in ACTION_LANES:
        raw_rows = raw_actions[lane]
        if not isinstance(raw_rows, list):
            raise ValueError(f"{market}.{lane}: action lane must be a list")
        rows: list[FixtureRow] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                raise ValueError(f"{market}.{lane}: action row must be an object")
            ticker = raw.get("ticker")
            name = raw.get("name")
            direction = raw.get("dir")
            label = raw.get("label")
            days = raw.get("days")
            if (
                not isinstance(ticker, str)
                or not ticker.strip()
                or not isinstance(name, str)
                or not name.strip()
                or direction not in {"up", "dn", "flat"}
                or not isinstance(label, str)
                or isinstance(days, bool)
                or not isinstance(days, int)
                or days < 0
            ):
                raise ValueError(f"{market}.{lane}: malformed action row")
            normalized_ticker = ticker.strip().upper()
            if normalized_ticker in seen:
                raise ValueError(f"{market}: duplicate action id {normalized_ticker}")
            seen.add(normalized_ticker)
            row = FixtureRow(raw)
            row["ticker"] = normalized_ticker
            rows.append(row)
        actions[lane] = rows
    if not actions["buy_now"]:
        raise ValueError(f"{market}: browser fixture must exercise Buy Now")
    return actions, path


def hk_context(
    setups: dict[str, Any], actions: dict[str, list[Any]] | None = None
) -> dict[str, Any]:
    """Fixed non-owner context matching the production Jinja environment."""
    return {
        "mode": "stocks",
        "latest": {
            "date": "2026-09-03",
            "quad_name": "fixture",
            "quad": "Q1",
            "liquidity_overlay": "neutral",
            "pending_quad": None,
        },
        "actions": common_actions() if actions is None else actions,
        "setups": setups,
        "gv": None,
        "market_state": None,
        "hk_scoreboard": None,
        "sectors_by_ticker": {},
        "velocity_desk": None,
        "built": "2026-09-03T00:00:00Z",
        "hk_breadth": None,
        "hk_full_breadth": None,
        "benchmark": None,
        "hk_sectors": [],
        "hk_flow": None,
        "track_record": None,
        "hk_ab": None,
        "hk_dispersion": None,
        "hk_cycles": None,
        "hk_indicators": None,
        "state_display_json": "{}",
        "washout_desk": None,
        "freshness": None,
        "hk_history": None,
        "hk_news": None,
        "hk_policy": None,
        "hk_macro": None,
        "hk_property": None,
        "hk_alerts": None,
        "hk_market_drivers": None,
        "hk_conditions": None,
        "hk_signal_stack": None,
        "hk_event_calendar": None,
        "hk_context_chips": None,
        "velocity_desk_picks": None,
        "hk_lab_button": None,
        "index_health": None,
        "hk_1d_velocity_desk": None,
    }


def canada_context(
    setups: dict[str, Any], actions: dict[str, list[Any]] | None = None
) -> dict[str, Any]:
    """Fixed non-owner context; owner rows come only from the checked-in JSON."""
    mtf = "{}"
    return {
        "mode": "stocks",
        "latest": {
            "date": "2026-09-03",
            "quad": "Q1",
            "quad_name": "fixture",
            "growth_score": 0.0,
            "inflation_score": 0.0,
            "confidence": 0.0,
            "liquidity_overlay": "neutral",
            "cycle_tag": "fixture",
            "confirming": [],
            "contradicting": [],
        },
        "built": "2026-09-03T00:00:00Z",
        "quad_meaning": ("fixture", "固定样本"),
        "overlay": {"state": "Neutral", "score": 0.0, "factors": []},
        "coupling": {
            "boc_rate": None,
            "goc_curve_2s10s": None,
            "goc_2y": None,
            "goc_10y": None,
            "us_2y": None,
            "us_10y": None,
            "goc_minus_ust_2y": None,
            "goc_minus_ust_10y": None,
        },
        "curve_chart": "",
        "axes_chart": "",
        "sectors": [],
        "actions": common_actions() if actions is None else actions,
        "setups": setups,
        "top_setups": [],
        "stocks_health": [],
        "board_health": [],
        "breadth": {
            "pct_above_50": None,
            "pct_above_200": None,
            "nh": None,
            "nl": None,
            "net_nh": None,
            "adv": None,
            "dec": None,
            "ad_trend": None,
            "pct50_chg20": None,
            "n_members": None,
            "state": "unavailable",
            "tone": "neutral",
            "full": False,
        },
        "benchmark": {
            "name": "S&P/TSX Composite",
            "ticker": "^GSPTSE",
            "price": None,
            "chg": None,
            "dc_day": None,
            "label": "UNAVAILABLE",
            "state": "UNAVAILABLE",
            "mtf_json": mtf,
        },
        "housing": None,
        "health": [],
        "pair": {},
        "pref": {},
        "lifespan_rows": [],
        "radar_dlg": {},
        "ca_aibrief_href": None,
    }


def owner_population(market: str, setups: dict[str, Any]) -> dict[str, Any]:
    board = setups.get("buy")
    watch = setups.get("watch")
    if market == "ca":
        board_rows = board if isinstance(board, list) else None
    else:
        lanes = (board, setups.get("ripening"), setups.get("ran"), setups.get("vetoed"))
        board_rows = (
            [row for lane in lanes for row in lane]
            if all(isinstance(lane, list) for lane in lanes)
            else None
        )
    board_ids = (
        [str(row["ticker"]).strip().upper() for row in board_rows]
        if board_rows is not None
        else None
    )
    watch_ids = (
        [str(row["ticker"]).strip().upper() for row in watch]
        if isinstance(watch, list)
        else None
    )
    intersection = (
        sorted(set(board_ids).intersection(watch_ids))
        if board_ids is not None and watch_ids is not None
        else None
    )
    return {
        "board": len(board_ids) if board_ids is not None else None,
        "watch": len(watch_ids) if watch_ids is not None else None,
        "intersection": intersection,
        "unique_total": (
            len(set(board_ids).union(watch_ids))
            if board_ids is not None and watch_ids is not None
            else None
        ),
    }


def input_row(path: Path, role: str) -> dict[str, str]:
    return {"path": repo_path(path), "role": role, "sha256": sha256(path)}


def canonical_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    """Bind an in-receipt transform to one documented canonical byte string."""
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "canonicalization": "utf-8 JSON; sort_keys=true; separators=(',', ':'); no trailing newline",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "payload": payload,
    }


def owner_case_setups(
    source: dict[str, Any], owner_case: str
) -> dict[str, Any]:
    """Apply one closed, presentation-proof-only owner-input transform."""
    if owner_case not in OWNER_CASES:
        raise ValueError(f"unknown owner case: {owner_case}")
    transformed = FixtureRow(source)
    if owner_case == "watch-only":
        transformed["buy"] = []
    elif owner_case == "null-buy":
        transformed["buy"] = None
    return transformed


def owner_lane_identities(
    market: str, setups: dict[str, Any]
) -> dict[str, list[str] | None]:
    """Serialize only stable owner identity, including an explicit null lane."""
    result: dict[str, list[str] | None] = {}
    for lane in OWNER_LANES[market]:
        rows = setups.get(lane)
        result[lane] = (
            [str(row["ticker"]).strip().upper() for row in rows]
            if isinstance(rows, list)
            else None
        )
    return result


def case_transform_receipt(
    market: str,
    owner_case: str,
    source: dict[str, Any],
    transformed: dict[str, Any],
) -> dict[str, Any]:
    operation = {
        "normal": "preserve frozen owner input",
        "watch-only": "replace buy with an explicit empty list; preserve every independent owner lane",
        "null-buy": "replace buy with JSON null; preserve every independent owner lane",
    }[owner_case]
    return canonical_receipt(
        {
            "schema": "mastermind.stock_dashboard_owner_case.v1",
            "market": market,
            "owner_case": owner_case,
            "operation": operation,
            "source_owner_identities": owner_lane_identities(market, source),
            "rendered_owner_identities": owner_lane_identities(market, transformed),
        }
    )


def membership_overlay_receipt(
    market: str, source: dict[str, Any]
) -> dict[str, Any]:
    """Admit the finite known-group/zero-card diagnostic overlay by exact bytes."""
    spec = MEMBERSHIP_OVERLAYS[market]
    source_ids = owner_lane_identities(market, source)
    for member in spec["members"]:
        lane = member["owner_lane"]
        if member["ticker"] not in (source_ids.get(lane) or []):
            raise ValueError(
                f"{market}: diagnostic member {member['ticker']} is not in {lane}"
            )
        if lane == "buy":
            raise ValueError(f"{market}: diagnostic member must not be an actionable card")
    payload = {
        "schema": "mastermind.stock_dashboard_membership_overlay.v1",
        "classification": "browser_contract_fixture_only",
        "market": market,
        "owner_case": "normal",
        "group": spec["group"],
        "members": list(spec["members"]),
        "composer_rows": [
            {"ticker": member["ticker"], "sector": spec["group"]["name"]}
            for member in spec["members"]
        ],
        "control": spec["control"],
        "card_population_mutation": "none",
        "table_population_mutation": "none",
        "delivery": (
            "verifier-scoped JSON.parse overlay only when the call stack names the "
            "exact entitled composer and the input bytes equal #stocktable-data; "
            "the wrapper is removed after one consumption"
        ),
        "source_identity_requirement": (
            "every member must remain in its original server-owned watch/stage "
            "anchor and must not be an actionable card"
        ),
    }
    return canonical_receipt(payload)


def case_output_name(market: str, owner_case: str) -> str:
    canonical = MARKETS[market]["output"]
    if owner_case == "normal":
        return canonical
    stem = Path(canonical).stem
    return f"{stem}.{owner_case}.html"


def render_market(market: str, out_dir: Path) -> dict[str, Any]:
    from engine import i18n

    spec = MARKETS[market]
    source_setups, owner_path = load_owner_fixture(market)
    actions, action_path = load_action_fixture(market)
    loaded_templates: set[Path] = set()
    owner_cases: dict[str, Any] = {}
    for owner_case in OWNER_CASES:
        setups = owner_case_setups(source_setups, owner_case)
        loader = TrackingLoader(TEMPLATES)
        env = Environment(loader=loader, autoescape=False)
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        context = (
            hk_context(setups, actions)
            if market == "hk"
            else canada_context(setups, actions)
        )
        html = env.get_template(spec["template"]).render(**context)
        output_name = case_output_name(market, owner_case)
        output = out_dir / output_name
        output.write_text(html, encoding="utf-8")
        loaded_templates.update(loader.loaded)
        owner_cases[owner_case] = {
            "route": f"/{spec['output']}",
            "output": output_name,
            "output_sha256": sha256(output),
            "owner_population": owner_population(market, setups),
            "input_transform": case_transform_receipt(
                market, owner_case, source_setups, setups
            ),
        }

    inputs = [
        input_row(Path(__file__), "recipe"),
        input_row(ROOT / "engine" / "i18n.py", "jinja_globals"),
        input_row(owner_path, "frozen_owner_fixture"),
        input_row(action_path, "frozen_action_fixture"),
    ]
    inputs.extend(
        input_row(path, "jinja_template") for path in sorted(loaded_templates)
    )
    inputs = sorted({row["path"]: row for row in inputs}.values(), key=lambda row: row["path"])
    normal = owner_cases["normal"]
    return {
        "route": f"/{spec['output']}",
        "output": spec["output"],
        "output_sha256": normal["output_sha256"],
        "owner_population": normal["owner_population"],
        "inputs": inputs,
        "owner_cases": owner_cases,
        "diagnostic_membership_overlay": membership_overlay_receipt(
            market, source_setups
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=("hk", "ca", "all"), default="all")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if inside(out_dir, SITE) or inside(out_dir, DATA):
        raise SystemExit("refusing fixture output under site/ or data/")
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = tuple(MARKETS) if args.market == "all" else (args.market,)
    markets = {market: render_market(market, out_dir) for market in selected}
    receipt = {
        "schema": "mastermind.stock_dashboard_rendered_fixture.v1",
        "proof_class": "rendered_fixture",
        "transform": "jinja2_candidate_template_render_from_frozen_owner_and_action_fixtures",
        "ambient_inputs": [],
        "effects": {"publish": False, "ledger_advance": False, "collectors": False},
        "runtime": {
            "jinja2": importlib.metadata.version("jinja2"),
        },
        "markets": markets,
    }
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    receipt_path = args.receipt.resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
