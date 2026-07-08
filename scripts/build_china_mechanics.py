"""Build the China Mechanics cockpit page (W8 — china_mechanics.html).

Reads the spine artifacts from site/chinastatedata/ and the data lobes from
data/china_*/  to assemble a control-room cockpit — participation trends,
limit mechanics, cycle memory, policy tape, cross-market — then renders
templates/china_mechanics.html.j2.

Authority: context_only (CN-SYS-R1).  No fused scores (CN-SYS-R13).
LLMs never feed the page (CN-SYS-R14).

Usage: python -m scripts.build_china_mechanics
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_china_mechanics")

_ROOT = Path(__file__).resolve().parent.parent
_SITE = _ROOT / "site"
_CHINASTATE = _SITE / "chinastatedata"
_OUT_DIR = _SITE / "chinamechanicsdata"
_TMPL = "china_mechanics.html.j2"

ASSETS = ("theme.css", "theme.js", "chart_i18n.js", "charts.js", "tablesort.js")

# ── helpers ────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("JSON unreadable (%s): %s", path, e)
    return None


def _clean_float(v: object) -> float | None:
    """Return None for nan/inf, else float."""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _series_to_chart(series: pd.Series, n: int = 120) -> list[dict]:
    """Last n rows of a float series -> [{d: date_str, v: float|null}]."""
    tail = series.dropna().tail(n)
    out = []
    for idx, val in tail.items():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({"d": d, "v": _clean_float(val)})
    return out


def _series_with_nulls(series: pd.Series, n: int = 120) -> list[dict]:
    """Last n rows including nulls."""
    tail = series.tail(n)
    out = []
    for idx, val in tail.items():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({"d": d, "v": _clean_float(val)})
    return out


# ── panel (a): participation ───────────────────────────────────────────────────

def _participation_panel() -> dict:
    """Build the participation panel payload."""
    try:
        tape = pd.read_parquet(_ROOT / "data" / "china_participation" / "tape.parquet")
        tape.index = pd.to_datetime(tape.index)
        tail = tape.tail(120)
        participation_json = _read_json(_CHINASTATE / "participation.json")
        return {
            "turnover_z20": _series_with_nulls(tail["turnover_z20"]),
            "margin_balance": _series_to_chart(tail["margin_balance"]),
            "margin_chg_5d": _series_with_nulls(tail["margin_chg_5d"]),
            "southbound_z": _series_with_nulls(tail["southbound_z"]),
            "qvix": _series_to_chart(tail["qvix"]),
            "latest": participation_json,
            "as_of": str(tape.index[-1].date()) if len(tape) > 0 else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("participation panel failed (%s); degrading", e)
        return {"latest": _read_json(_CHINASTATE / "participation.json")}


# ── panel (b): limit mechanics ─────────────────────────────────────────────────

def _limit_panel() -> dict:
    """Build the limit mechanics panel payload."""
    try:
        tape = pd.read_parquet(_ROOT / "data" / "china_microstructure" / "limit_tape.parquet")
        # tape uses a 'date' column (not the index); coerce
        if "date" in tape.columns:
            tape["date"] = pd.to_datetime(tape["date"])
            tape = tape.set_index("date").sort_index()
        tail = tape.tail(120)
        events_raw = pd.read_parquet(_ROOT / "data" / "china_microstructure" / "limit_events.parquet")
        events_raw["date"] = pd.to_datetime(events_raw["date"])
        events_raw = events_raw.sort_values("date")

        # latest session events table
        latest_date = events_raw["date"].max()
        latest_events = events_raw[events_raw["date"] == latest_date].to_dict("records")
        # limit up/down breadth series
        lup_series = _series_with_nulls(tail["limit_up_breadth_pct"])
        ldn_series = _series_with_nulls(tail["limit_down_breadth_pct"])
        # failed seal ratio = failed_up_seal_count / limit_up_count (avoid div0)
        fsr = (tail["failed_up_seal_count"] / tail["limit_up_count"].clip(lower=1)).where(
            tail["limit_up_count"] > 0
        )
        fsr_series = _series_with_nulls(fsr)
        lianban_series = _series_with_nulls(tail["lianban_2plus"])

        micro_json = _read_json(_CHINASTATE / "microstructure.json")
        latest_agg = (micro_json or {}).get("latest_aggregate") or {}

        # clean events for display (stringify dates)
        clean_events = []
        for ev in latest_events[:20]:
            clean_events.append({
                "ticker": ev.get("ticker", ""),
                "board": ev.get("board", ""),
                "event": ev.get("event", ""),
                "lianban_count": int(ev.get("lianban_count", 0) or 0),
                "close_off_limit_pct": _clean_float(ev.get("close_off_limit_pct")),
            })

        return {
            "lup_series": lup_series,
            "ldn_series": ldn_series,
            "fsr_series": fsr_series,
            "lianban_series": lianban_series,
            "latest_events": clean_events,
            "latest_date": str(latest_date.date()) if pd.notna(latest_date) else None,
            "latest_agg": latest_agg,
            "as_of": str(tape.index[-1].date()) if len(tape) > 0 else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("limit panel failed (%s); degrading", e)
        micro_json = _read_json(_CHINASTATE / "microstructure.json")
        return {"latest_agg": (micro_json or {}).get("latest_aggregate") or {}}


# ── panel (c): phase memory ────────────────────────────────────────────────────

def _phase_panel() -> dict:
    """Build the phase memory panel payload (90-session strip + falsifier ledger + ERA analogs)."""
    cp = _read_json(_CHINASTATE / "cycle_phase.json")
    phase_strip: list[dict] = []
    ledger_held = 0
    ledger_fired = 0

    try:
        tape_path = _ROOT / "data" / "china_cycle_phase" / "phase_tape.parquet"
        if tape_path.exists():
            tape = pd.read_parquet(tape_path)
            tape.index = pd.to_datetime(tape.index)
            tail = tape.tail(90)
            for idx, row in tail.iterrows():
                phase_strip.append({
                    "d": idx.strftime("%Y-%m-%d"),
                    "phase": str(row.get("phase", "")),
                    "confidence": _clean_float(row.get("confidence")),
                })

        ledger_path = _ROOT / "data" / "china_cycle_phase" / "falsifier_ledger.parquet"
        if ledger_path.exists():
            ledger = pd.read_parquet(ledger_path)
            ledger_held = int((ledger["outcome"] == "held").sum()) if "outcome" in ledger.columns else 0
            ledger_fired = int((ledger["outcome"] == "fired").sum()) if "outcome" in ledger.columns else 0
    except Exception as e:  # noqa: BLE001
        log.warning("phase tape/ledger read failed (%s); degrading", e)

    # if tape empty, use snapshot from cycle_phase.json
    if not phase_strip and cp:
        phase_strip = [{"d": cp.get("asof", ""), "phase": cp.get("phase", ""), "confidence": cp.get("confidence")}]

    era_table = (cp or {}).get("era_table", [])
    ledger_summary = (cp or {}).get("ledger_summary") or {"held": ledger_held, "fired": ledger_fired, "total_graded": ledger_held + ledger_fired}

    return {
        "current": cp,
        "phase_strip": phase_strip,
        "era_table": era_table,
        "ledger_summary": ledger_summary,
    }


# ── panel (d): policy tape ─────────────────────────────────────────────────────

def _policy_panel() -> dict:
    """Build the policy tape panel payload."""
    pt = _read_json(_CHINASTATE / "policy_transmission.json") or {}
    return {
        "policy_impulse": pt.get("policy_impulse"),
        "transmission_channel": pt.get("transmission_channel", []),
        "recent_events": pt.get("recent_events", []),
        "staleness": pt.get("staleness", {}).get("per_source_days", {}),
        "asof": pt.get("asof"),
    }


# ── panel (e): cross-market ────────────────────────────────────────────────────

def _cross_market_panel() -> dict:
    """Build the cross-market panel from market_state.json external block."""
    ms = _read_json(_CHINASTATE / "market_state.json") or {}
    ext = ms.get("external") or {}
    return {
        "yield_curve": ext.get("yield_curve") or {},
        "cgb_curve": ext.get("cgb_curve") or {},
        "usdcnh": ext.get("usdcnh") or {},
        "dxy": ext.get("dxy"),
        "as_of": ms.get("as_of"),
        "data_gaps": ms.get("data_gaps", []),
    }


# ── payload builder ────────────────────────────────────────────────────────────

def build_payload() -> dict:
    """Assemble all panel payloads into a single VM dict."""
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ms = _read_json(_CHINASTATE / "market_state.json") or {}
    return {
        "built": built,
        "as_of": ms.get("as_of", ""),
        "authority": "context_only",
        "participation": _participation_panel(),
        "limits": _limit_panel(),
        "phase": _phase_panel(),
        "policy": _policy_panel(),
        "cross_market": _cross_market_panel(),
        "data_gaps": ms.get("data_gaps", []),
    }


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)

        payload = build_payload()

        # write the JSON payload (committed artifact)
        payload_path = _OUT_DIR / "mechanics.json"
        payload_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("wrote %s", payload_path)

        # render the template
        env = Environment(
            loader=FileSystemLoader(str(_ROOT / "templates")), autoescape=False
        )
        from engine import i18n  # noqa: E402
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        tmpl = env.get_template(_TMPL)
        html = tmpl.render(**payload)
        write_page(_SITE / "china_mechanics.html", html)
        log.info(
            "wrote site/china_mechanics.html (%d KB)", len(html) // 1024
        )

        # copy assets
        for a in ASSETS:
            src = _ROOT / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, _SITE)

    except Exception as e:  # noqa: BLE001
        log.error("build_china_mechanics failed (%s); skipping", e)
        return 0  # non-fatal per CN-SYS-R11
    return 0


if __name__ == "__main__":
    sys.exit(main())
