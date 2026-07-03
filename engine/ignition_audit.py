"""Sector-ignition forward ledger — per-market snapshot + deterministic grading.

The sibling of engine/risk_radar_intl_audit.py, for the sector-ignition strip
(engine/sector_ignition.py). Every render APPENDS one row per basket to
data/ignition_log/<market>_ignition.jsonl (idempotent by (as-of, basket)). Once an entry's
horizon matures it is GRADED against the basket's OWN realized forward excess return vs the
market benchmark: 4-week (h20) and 8-week (h40) basket-minus-benchmark return from the as-of
close. An "igniting"/"running" call is a true-positive when its forward excess is positive.

DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED — the strip never scores off these grades until
the log matures (first single 4w grade ~Aug 2026). Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

HORIZONS = {"h20": 20, "h40": 40}          # 4-week / 8-week business-day forward windows
ALERT_STATES = ("igniting", "running")     # the loud tiers — the ones a scoreboard grades


def _path(market: str, root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "ignition_log" / f"{market}_ignition.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _write(p: Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n")


def _entries_from_snapshot(ign: dict, market: str) -> list[dict]:
    if not ign or not ign.get("as_of") or not ign.get("items"):
        return []
    asof = str(ign["as_of"])
    out = []
    for it in ign["items"]:
        if it.get("ignition_score") is None:
            continue
        out.append({
            "asof": asof,
            "market": market,
            "basket": it.get("id"),
            "name": it.get("name"),
            "ignition_score": it.get("ignition_score"),
            "state": it.get("state"),
            "alert": it.get("state") in ALERT_STATES,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graded": None,
        })
    return out


def log_snapshot(ign: dict, market: str, root=None) -> int:
    """Append today's ignition strip to the market's forward log (idempotent by (asof, basket))."""
    try:
        entries = _entries_from_snapshot(ign, market)
        if not entries:
            return 0
        p = _path(market, root)
        rows = _read(p)
        seen = {(r.get("asof"), r.get("basket")) for r in rows}
        added = [e for e in entries if (e["asof"], e["basket"]) not in seen]
        if not added:
            return 0
        rows.extend(added)
        _write(p, rows)
        return len(added)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit log(%s) failed: %s", market, e)
        return 0


def _grade_entry(entry: dict, basket_lvl: pd.Series, bench_lvl: pd.Series) -> dict | None:
    """Realized forward basket-minus-benchmark excess per horizon from the as-of date.
    None until the longest horizon has matured."""
    asof = pd.Timestamp(entry["asof"])

    def _base_loc(px: pd.Series):
        loc = px.index.searchsorted(asof, side="right")
        return loc

    bl, bnl = basket_lvl.dropna(), bench_lvl.dropna()
    if bl.empty or bnl.empty:
        return None
    loc_b, loc_n = _base_loc(bl), _base_loc(bnl)
    maxH = max(HORIZONS.values())
    if loc_b + maxH > len(bl) or loc_n + maxH > len(bnl):
        return None
    base_b = float(bl.iloc[max(0, loc_b - 1)])
    base_n = float(bnl.iloc[max(0, loc_n - 1)])
    if base_b <= 0 or base_n <= 0:
        return None
    excess, win = {}, {}
    for hk, hd in HORIZONS.items():
        fb = float(bl.iloc[min(loc_b + hd - 1, len(bl) - 1)])
        fn = float(bnl.iloc[min(loc_n + hd - 1, len(bnl) - 1)])
        ex = (fb / base_b - 1.0) - (fn / base_n - 1.0)
        excess[hk] = round(ex, 4)
        win[hk] = bool(ex > 0)
    st = entry.get("state")
    any_pos = any(excess[hk] > 0 for hk in HORIZONS)
    if st in ALERT_STATES:
        outcome = "true_positive" if any_pos else "false_positive"
    else:
        outcome = "quiet_up" if any_pos else "quiet_flat"
    return {"excess": excess, "beat_bench": win, "outcome": outcome,
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def grade_log(market: str, level_of, bench_series, root=None) -> int:
    """Grade every matured, ungraded entry against realized basket + benchmark paths.

    level_of      callable(basket_id) -> that basket's level Series (or None)
    bench_series  the benchmark level Series
    """
    try:
        p = _path(market, root)
        rows = _read(p)
        if not rows or bench_series is None:
            return 0
        bench = pd.Series(bench_series).dropna()
        if bench.empty:
            return 0
        cache: dict[str, pd.Series | None] = {}
        n = 0
        for r in rows:
            if r.get("graded"):
                continue
            bid = r.get("basket")
            if bid not in cache:
                try:
                    cache[bid] = level_of(bid)
                except Exception:  # noqa: BLE001
                    cache[bid] = None
            lvl = cache[bid]
            if lvl is None or getattr(lvl, "empty", True):
                continue
            g = _grade_entry(r, pd.Series(lvl), bench)
            if g is not None:
                r["graded"] = g
                n += 1
        if n:
            _write(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit grade(%s) failed: %s", market, e)
        return 0


def scorecard(market: str, root=None) -> dict:
    """Rolling realized-accuracy scorecard from the graded log. Never raises."""
    try:
        rows = [r for r in _read(_path(market, root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"market": market, "n_graded": 0,
                "note": "scoreboard accruing — first read ~Aug 2026 (4w grades mature ~+20 sessions)"}
    n = len(rows)
    alerts = [r for r in rows if r.get("alert")]
    tp = [r for r in alerts if r["graded"]["outcome"] == "true_positive"]
    by_state: dict[str, dict] = {}
    for r in rows:
        d = by_state.setdefault(r.get("state"), {"n": 0, "beat": 0})
        d["n"] += 1
        d["beat"] += int(bool((r["graded"].get("beat_bench") or {}).get("h20")))
    by_state = {k: {"n": v["n"], "beat_rate_4w": round(v["beat"] / v["n"], 3)}
                for k, v in by_state.items()}
    return {
        "market": market,
        "n_graded": n,
        "n_alerts": len(alerts),
        "alert_precision_4w": round(len(tp) / len(alerts), 3) if alerts else None,
        "by_state": by_state,
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
    }


def snapshot_and_grade(ign: dict, market: str, level_of, bench_series, root=None) -> dict:
    """Log today's ignition strip, grade matured entries, return the scorecard."""
    n_logged = log_snapshot(ign, market, root=root)
    grade_log(market, level_of, bench_series, root=root)
    sc = scorecard(market, root=root)
    sc["n_logged_today"] = n_logged
    return sc
