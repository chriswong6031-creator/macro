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
    if not isinstance(board, list) or not isinstance(watch, list):
        raise ValueError(f"{market}: checked-in owner fixture is not list-backed")
    if market == "ca":
        board_rows = board
    else:
        lanes = (board, setups.get("ripening"), setups.get("ran"), setups.get("vetoed"))
        if any(not isinstance(lane, list) for lane in lanes):
            raise ValueError("hk: priority owner lanes are not all list-backed")
        board_rows = [row for lane in lanes for row in lane]
    board_ids = [str(row["ticker"]).strip().upper() for row in board_rows]
    watch_ids = [str(row["ticker"]).strip().upper() for row in watch]
    intersection = sorted(set(board_ids).intersection(watch_ids))
    return {
        "board": len(board_ids),
        "watch": len(watch_ids),
        "intersection": intersection,
        "unique_total": len(set(board_ids).union(watch_ids)),
    }


def input_row(path: Path, role: str) -> dict[str, str]:
    return {"path": repo_path(path), "role": role, "sha256": sha256(path)}


def render_market(market: str, out_dir: Path) -> dict[str, Any]:
    from engine import i18n

    spec = MARKETS[market]
    setups, owner_path = load_owner_fixture(market)
    actions, action_path = load_action_fixture(market)

    loader = TrackingLoader(TEMPLATES)
    env = Environment(loader=loader, autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    context = (
        hk_context(setups, actions)
        if market == "hk"
        else canada_context(setups, actions)
    )
    html = env.get_template(spec["template"]).render(**context)

    output = out_dir / spec["output"]
    output.write_text(html, encoding="utf-8")
    inputs = [
        input_row(Path(__file__), "recipe"),
        input_row(ROOT / "engine" / "i18n.py", "jinja_globals"),
        input_row(owner_path, "frozen_owner_fixture"),
        input_row(action_path, "frozen_action_fixture"),
    ]
    inputs.extend(input_row(path, "jinja_template") for path in sorted(loader.loaded))
    inputs = sorted({row["path"]: row for row in inputs}.values(), key=lambda row: row["path"])
    return {
        "route": f"/{spec['output']}",
        "output": spec["output"],
        "output_sha256": sha256(output),
        "owner_population": owner_population(market, setups),
        "inputs": inputs,
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
