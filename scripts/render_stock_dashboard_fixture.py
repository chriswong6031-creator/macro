#!/usr/bin/env python3
"""Reproduce the P0B stock-dashboard browser fixture without ambient state.

This is an evidence recipe, not a production builder.  It renders the candidate
HK and Canada Jinja templates with fixed auxiliary context and the named,
checked-in ``site/factordata/*_standouts.json`` owner fixtures.  It never reads a
developer VM cache, runs a collector, publishes into ``site/``, or advances a
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
        "owner_fixture": "site/factordata/hk_standouts.json",
        "output": "hk_stocks.html",
    },
    "ca": {
        "template": "canada.html.j2",
        "owner_fixture": "site/factordata/canada_standouts.json",
        "output": "canada_stocks.html",
    },
}


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
    return {
        "buy_now": [],
        "buy_soon": [],
        "on_the_run": [],
        "take_profits": [],
        "hold": [],
        "avoid": [],
    }


def hk_context(setups: dict[str, Any]) -> dict[str, Any]:
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
        "actions": common_actions(),
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


def canada_context(setups: dict[str, Any]) -> dict[str, Any]:
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
        "actions": common_actions(),
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


def owner_population(market: str, setups: dict[str, Any]) -> dict[str, int]:
    board = setups.get("buy")
    watch = setups.get("watch")
    if not isinstance(board, list) or not isinstance(watch, list):
        raise ValueError(f"{market}: checked-in owner fixture is not list-backed")
    if market == "ca":
        board_count = len(board)
    else:
        lanes = (board, setups.get("ripening"), setups.get("ran"), setups.get("vetoed"))
        if any(not isinstance(lane, list) for lane in lanes):
            raise ValueError("hk: priority owner lanes are not all list-backed")
        board_count = sum(len(lane) for lane in lanes)
    return {"board": board_count, "watch": len(watch)}


def input_row(path: Path, role: str) -> dict[str, str]:
    return {"path": repo_path(path), "role": role, "sha256": sha256(path)}


def render_market(market: str, out_dir: Path) -> dict[str, Any]:
    from engine import i18n

    spec = MARKETS[market]
    owner_path = ROOT / spec["owner_fixture"]
    setups = json.loads(owner_path.read_text(encoding="utf-8"))
    if not isinstance(setups, dict):
        raise ValueError(f"{market}: owner fixture root must be an object")

    loader = TrackingLoader(TEMPLATES)
    env = Environment(loader=loader, autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    context = hk_context(setups) if market == "hk" else canada_context(setups)
    html = env.get_template(spec["template"]).render(**context)

    output = out_dir / spec["output"]
    output.write_text(html, encoding="utf-8")
    inputs = [
        input_row(Path(__file__), "recipe"),
        input_row(ROOT / "engine" / "i18n.py", "jinja_globals"),
        input_row(owner_path, "owner_fixture"),
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
        "transform": "jinja2_candidate_template_render",
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
