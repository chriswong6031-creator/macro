"""CHINA INTELLIGENCE HUB — the China command apparatus.

Mirror of engine/intel_hub.py for China names.  Fuses five per-ticker legs
(news · altdata convergence · divergence radar sector→member crosswalk ·
stocks-board membership · special-situations flags) into an EDGE-REMAINING-
ranked command list, plus four off-desk discovery lanes.

INTELLIGENCE_HUB_V2 rulings are LAW here (masterplan R-2):
  • Sort key: (edge_remaining-weighted opportunity, conviction)
  • LEADING desks: altdata + radar.  LAGGING: news + board.
  • leading_gap = lead_up − lag_up; gap_mult = 1 + 0.15×clamp(gap, -2, +2)
  • opportunity = signal_core × falsifier_penalty × edge_remaining × gap_mult
  • NO term may reward raw agreement count
  • 5-desk-agree RANKS BELOW 2-leading-desk + high-edge by design

Price veto: a name rolling over (20d return < VETO_RETURN_THRESH and RS falling)
is staged "faltering" — never "emerging" or "early".

CONTEXT-ONLY · DEGRADE-NEVER-RAISE · display-only until gauntleted.
schema: china_intel.command.v1
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_intel.command.v1"
DISCLAIMER = (
    "Context only. Fuses five China intelligence desks (news flow, altdata convergence "
    "kernel, divergence radar sector crosswalk, stocks-board membership, special-sits "
    "flags) into a per-ticker command list ranked by EDGE REMAINING × opportunity. "
    "Off-desk discovery lanes (LHB first-seat, margin velocity [EXPERIMENTAL], "
    "southbound delta, THS emerging concepts) surface names not yet on any desk. "
    "Nothing here sizes or scores a position."
)

# VETO: 20d return below this and RS falling → rolling_over → stage = faltering
VETO_RETURN_THRESH = -0.08   # −8% over 20 days

# Leading/lagging desk assignments (see Intel Hub V2 research)
_LEADING = ("altdata", "radar")
_LAGGING = ("news", "board")

# stage lifecycle → how much of move is still ahead
_LIFECYCLE_EDGE = {"emerging": 1.0, "forming": 0.82, "mature": 0.34, "fading": 0.12}

# board label → edge fraction (mirrors _LABEL_EDGE in intel_hub.py)
_LABEL_EDGE = (
    ("BOTTOMING", 0.95), ("NEARING A LOW", 0.95), ("EMERGING", 0.92),
    ("BUY ZONE", 0.74), ("TURN", 0.70), ("ACCUMULAT", 0.80),
    ("UPTREND", 0.40), ("CONFIRMED", 0.40), ("EXTENDED", 0.12),
)

# Margin velocity discovery: EXPERIMENTAL — contributes zero to opportunity/ranking
# Appears with experimental=True flag; UI must show caveat chip.
MARGIN_VELOCITY_EXPERIMENTAL = True

# Discovery caps
_LANE_EMIT_CAP = 12          # cap per discovery lane
_DISCOVERY_TOP = 10          # top names surfaced overall


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _f(x):
    """Safely convert to float; return None on failure."""
    if x is None or isinstance(x, (dict, list, bool)):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _root() -> Path:
    return config.ROOT


def _read_json(rel: str) -> dict | list | None:
    """Read a JSON artifact relative to the repo root. Degrade-safe."""
    try:
        p = _root() / rel
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: read %s failed (%s)", rel, e)
        return None


# ── Input loaders ─────────────────────────────────────────────────────────── #

def _load_news_by_ticker() -> dict:
    """site/chinanews/by_ticker.json → {ticker: [headline_items]}."""
    try:
        d = _read_json("site/chinanews/by_ticker.json")
        if isinstance(d, dict):
            return d.get("by_ticker") or {}
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: news by_ticker failed (%s)", e)
    return {}


def _load_altdata_by_ticker() -> dict:
    """site/chinaaltdata/by_ticker.json → {ticker: row} from top+bottom+triple lists."""
    try:
        d = _read_json("site/chinaaltdata/by_ticker.json")
        if not isinstance(d, dict):
            return {}
        out: dict = {}
        for row in ((d.get("triple") or []) + (d.get("top") or []) + (d.get("bottom") or [])):
            if isinstance(row, dict) and row.get("ticker"):
                t = str(row["ticker"]).upper().strip()
                if t not in out:
                    out[t] = row
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: altdata by_ticker failed (%s)", e)
    return {}


def _load_radar_by_sector() -> list:
    """site/chinaradar/radar.json → list of divergence rows (sector-level only)."""
    try:
        d = _read_json("site/chinaradar/radar.json")
        if isinstance(d, dict):
            return [r for r in (d.get("divergences") or [])
                    if r.get("family") != "venue"]   # exclude venue rows per masterplan
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: radar by_sector failed (%s)", e)
    return []


def _build_radar_by_ticker(radar_rows: list) -> dict:
    """Map each radar divergence's member candidates → {ticker: radar_row}.

    Uses the candidates list already in radar.json (populated by china_radar engine).
    For tickers without a candidates list, cross-walks via china_basket_spine.
    """
    try:
        from engine import china_basket_spine as sp
        etf_to_basket = sp.etf_to_basket()
        basket_members = sp.basket_members
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: basket_spine import failed (%s)", e)
        etf_to_basket = {}
        def basket_members(_): return []  # noqa: E731

    out: dict = {}
    for row in radar_rows:
        # prefer the candidates list that the radar engine already computed
        candidates = row.get("candidates") or []
        tickers_for_row = []
        if candidates:
            tickers_for_row = [c.get("ticker") for c in candidates if c.get("ticker")]
        else:
            # fallback: sector ETF → basket → members
            etf = row.get("sector_etf")
            if etf:
                for bid in (etf_to_basket.get(etf) or []):
                    tickers_for_row += basket_members(bid)
        for t in tickers_for_row:
            if t and str(t) not in out:
                out[str(t).upper().strip()] = row
    return out


def _load_board_membership() -> set:
    """Current buy-board members from site/factordata/china_standouts.json → {ticker}."""
    try:
        d = _read_json("site/factordata/china_standouts.json")
        if isinstance(d, dict):
            return {str(r.get("ticker", "")).upper().strip()
                    for r in (d.get("buy") or []) if r.get("ticker")}
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: board membership failed (%s)", e)
    return set()


def _load_board_rows() -> dict:
    """Buy-board rows keyed by ticker {ticker: row}."""
    try:
        d = _read_json("site/factordata/china_standouts.json")
        if isinstance(d, dict):
            return {str(r.get("ticker", "")).upper().strip(): r
                    for r in (d.get("buy") or []) if r.get("ticker")}
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: board rows failed (%s)", e)
    return {}


def _load_special_by_ticker() -> dict:
    """site/chinaspecialdata/special.json → by_ticker flags {ticker: {flags}}."""
    try:
        d = _read_json("site/chinaspecialdata/special.json")
        if isinstance(d, dict):
            return d.get("by_ticker") or {}
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: special by_ticker failed (%s)", e)
    return {}


# ── Price trajectories ────────────────────────────────────────────────────── #

def _load_closes_and_benchmark() -> tuple:
    """Load closes.parquet and 510300.SS as CSI300 benchmark.
    Returns (closes_df, bench_series) or (None, None) on failure.
    """
    try:
        import pandas as pd
        closes = pd.read_parquet(_root() / "data" / "china_search" / "closes.parquet")
        bench_path = _root() / "data" / "china" / "510300.SS.parquet"
        bench = None
        if bench_path.exists():
            bf = pd.read_parquet(bench_path)
            bench = bf["close"].rename("bench")
        return closes, bench
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: price data load failed (%s)", e)
        return None, None


def _load_per_stock_close(ticker: str) -> "pd.Series | None":
    """Fallback price loader from data/china_stocks/<ticker>.parquet.

    Used when the ticker is absent from closes.parquet.  Only the 'close' column
    is read.  Returns a Series indexed by date or None on failure.
    """
    try:
        import pandas as pd
        p = _root() / "data" / "china_stocks" / f"{ticker}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p, columns=["close"])
        s = df["close"].dropna()
        # ensure datetime index
        if not isinstance(s.index, pd.DatetimeIndex):
            s.index = pd.to_datetime(s.index, errors="coerce")
            s = s[s.index.notna()].sort_index()
        return s if len(s) >= 21 else None
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: per-stock close load for %s failed (%s)", ticker, e)
        return None


def _price_trajectory(ticker: str, closes, bench) -> dict | None:
    """Compute per-name trajectory fields: rs_20d, rs_60d, off_high_pct, ret_20d, rolling_over.

    LAYERED LOOKUP: first tries closes.parquet; falls back to
    data/china_stocks/<ticker>.parquet for names missing from closes.

    rs_Xd = cumulative return of ticker minus CSI300 over X sessions (pct),
    computed on the dropna-aligned joined index (same trailing sessions for both legs).
    off_high_pct = (price / 120-session-high − 1) * 100 — requires len >= 120.
    rolling_over = ret_20d < VETO_RETURN_THRESH AND rs_20d < rs_60d (momentum fading).
    Returns None if fewer than 21 rows after lookup.
    """
    import pandas as pd

    s: pd.Series | None = None

    # Primary: closes.parquet
    if closes is not None and ticker in closes.columns:
        s = closes[ticker].dropna()
        if len(s) < 21:
            s = None

    # Fallback: per-stock parquet
    if s is None:
        s = _load_per_stock_close(ticker)

    if s is None:
        return None

    try:
        ret_20 = float(s.iloc[-1] / s.iloc[-21] - 1.0) if len(s) >= 21 else None
        ret_60 = float(s.iloc[-1] / s.iloc[-61] - 1.0) if len(s) >= 61 else None

        rs_20: float | None = None
        rs_60: float | None = None
        if bench is not None:
            # rs_20: align both legs over last 21 rows on the shared index
            if len(s) >= 21:
                s20 = s.iloc[-21:]
                b20_raw = bench.reindex(s20.index)
                joined20 = pd.concat([s20, b20_raw], axis=1, join="inner").dropna()
                joined20.columns = ["stk", "bnch"]
                if len(joined20) >= 2:
                    rs_20 = (float(joined20["stk"].iloc[-1] / joined20["stk"].iloc[0] - 1.0)
                             - float(joined20["bnch"].iloc[-1] / joined20["bnch"].iloc[0] - 1.0)) * 100.0
            # rs_60: same aligned approach over last 61 rows
            if len(s) >= 61:
                s60 = s.iloc[-61:]
                b60_raw = bench.reindex(s60.index)
                joined60 = pd.concat([s60, b60_raw], axis=1, join="inner").dropna()
                joined60.columns = ["stk", "bnch"]
                if len(joined60) >= 2:
                    rs_60 = (float(joined60["stk"].iloc[-1] / joined60["stk"].iloc[0] - 1.0)
                             - float(joined60["bnch"].iloc[-1] / joined60["bnch"].iloc[0] - 1.0)) * 100.0

        # off_high: require at least 120 sessions — avoid labelling a short-window high
        off_high: float | None = None
        if len(s) >= 120:
            high_252 = float(s.tail(252).max())
            if high_252 > 0:
                off_high = float(s.iloc[-1] / high_252 - 1.0) * 100.0

        # rolling_over: 20d return below veto threshold AND RS falling (rs_20d < rs_60d)
        rolling_over = False
        if ret_20 is not None and ret_20 < VETO_RETURN_THRESH:
            if rs_20 is not None and rs_60 is not None and rs_20 < rs_60:
                rolling_over = True
            elif rs_20 is not None and rs_20 < -10.0:
                rolling_over = True  # extreme RS drawdown even without 60d comparison

        return {
            "ret_20d": round(ret_20 * 100.0, 2) if ret_20 is not None else None,
            "ret_60d": round(ret_60 * 100.0, 2) if ret_60 is not None else None,
            "rs_20d": round(rs_20, 2) if rs_20 is not None else None,
            "rs_60d": round(rs_60, 2) if rs_60 is not None else None,
            "off_high_pct": round(off_high, 2) if off_high is not None else None,
            "rolling_over": rolling_over,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: trajectory for %s failed (%s)", ticker, e)
        return None


# ── Per-desk directions ───────────────────────────────────────────────────── #

def _dirs(altdata_row: dict | None, radar_row: dict | None,
          news_items: list | None, board_row: dict | None) -> dict:
    """Direction per desk: 1 (bullish), -1 (bearish), 0 (neutral), None (absent).
    Absent = desk has no data for this ticker at all.
    """
    # altdata
    ad: int | None = None
    if altdata_row is not None:
        side = altdata_row.get("side")
        ad = 1 if side == "accumulate" else -1 if side == "distribute" else 0

    # radar: positive divergence → bullish, negative → bearish
    rd: int | None = None
    if radar_row is not None:
        sign = radar_row.get("sign")
        rd = 1 if sign == "positive" else -1 if sign == "negative" else 0

    # news: presence indicator — no sentiment is computed from by_ticker, so direction is None
    # for gap purposes (news dir must NOT count toward lag_up, only toward desk_matrix presence).
    # The dot in the desk matrix shows neutral presence; a data-tip notes sentiment-less.
    nd: int | None = None
    # news_items present (even empty list) = desk present, but dir stays None (no sentiment).
    # Desk absent (news_items is None) = nd stays None.

    # board: membership on buy board = bullish
    bd: int | None = None
    if board_row is not None:
        lab = (board_row.get("label") or "").upper()
        bd = -1 if "AVOID" in lab or (board_row.get("dir") or "") == "down" else 1

    return {"altdata": ad, "radar": rd, "news": nd, "board": bd}


# ── Edge remaining ────────────────────────────────────────────────────────── #

def _edge_remaining(dirs: dict, altdata_row: dict | None,
                    radar_row: dict | None, board_row: dict | None,
                    special_flags: dict | None, traj: dict | None,
                    board_member: bool = False) -> dict:
    """Edge remaining in [0,1]: how much of the move is still AHEAD.

    Components:
    - board label edge (BOTTOMING / EMERGING etc.)
    - off-high room (trajectory)
    - RS not yet stretched (traj.rs_20d)
    - board-absent BONUS: name not on buy-board = crowd hasn't found it
    - unlock/pledge overhang PENALTY (special-sits)
    - crowding PENALTY (altdata crowding flag)
    """
    comps: list[tuple[float, float, str]] = []   # (weight, score, driver)
    traj = traj or {}
    rolling_over = bool(traj.get("rolling_over"))

    # board label → lifecycle edge score
    if board_row:
        lab = (board_row.get("label") or "").upper()
        le = next((s for k, s in _LABEL_EDGE if k in lab), 0.5)
        comps.append((0.9, le, f"board {lab.lower()[:20]}"))

    # off-high room: -8% to -20%+ → meaningful room
    oh = _f(traj.get("off_high_pct"))
    if oh is not None:
        oh_score = 0.1 if rolling_over else _clamp01(0.15 + (-oh) / 22.0)
        comps.append((0.6, oh_score,
                      f"{oh:.0f}% off high (falling)" if rolling_over else
                      f"{oh:.0f}% off high"))

    # RS vs CSI300: the more RS already stretched, the less room
    rs = _f(traj.get("rs_20d"))
    if rs is not None:
        comps.append((0.7, _clamp01(1.0 - max(rs, 0.0) / 35.0) if rs > 0 else 1.0,
                      f"RS {rs:+.1f}% vs CSI300 (20d)"))

    # 20d return extension proxy: big run-up = priced-in
    ret20 = _f(traj.get("ret_20d"))
    if ret20 is not None and ret20 > 12.0:
        comps.append((0.6, _clamp01(1.0 - ret20 / 30.0),
                      f"{ret20:.0f}% 20d return (extended)"))

    # board-absent bonus: name NOT yet on buy board = edge not widely priced
    if not board_member:
        comps.append((0.5, 0.75, "not on buy-board (crowd absent)"))

    # special-sits overhang penalties
    if special_flags:
        if special_flags.get("unlock_large"):
            comps.append((0.8, 0.15, "large unlock overhang"))
        elif special_flags.get("unlock"):
            comps.append((0.5, 0.30, "unlock overhang"))
        if special_flags.get("pledge_stress"):
            comps.append((0.6, 0.10, "pledge stress"))

    # altdata crowding flag
    if altdata_row and altdata_row.get("flags"):
        flags = altdata_row.get("flags") or []
        if any("crowd" in str(f).lower() for f in flags):
            comps.append((0.7, 0.15, "altdata crowding flag"))

    if not comps:
        return {"score": 0.4, "n_components": 0, "drivers": []}

    wsum = sum(w for w, _, _ in comps)
    score = sum(w * s for w, s, _ in comps) / wsum
    ranked = sorted(comps, key=lambda c: c[1], reverse=True)
    drivers = [c[2] for c in ranked[:2]]
    if len(comps) > 2 and ranked[-1][1] < 0.30:
        drivers.append("drag: " + ranked[-1][2])
    return {"score": round(_clamp01(score), 3), "n_components": len(comps), "drivers": drivers}


# ── Leading-vs-lagging gap ────────────────────────────────────────────────── #

def _leading_gap(dirs: dict) -> dict:
    """Leading desks hot, lagging silent = pre-consensus edge.
    lead_up counts leading desks pointing up.
    lag_up counts lagging desks already pointing up.
    gap = lead_up - lag_up; positive → flow ahead of crowd.
    """
    lead_up = ((1 if dirs.get("altdata") == 1 else 0)
               + (1 if dirs.get("radar") == 1 else 0))
    lag_up = ((1 if dirs.get("news") == 1 else 0)
              + (1 if dirs.get("board") == 1 else 0))
    lag_present = ((1 if dirs.get("news") is not None else 0)
                   + (1 if dirs.get("board") is not None else 0))
    return {"lead_up": lead_up, "lag_up": lag_up,
            "gap": lead_up - lag_up, "lag_present": lag_present}


# ── Stage ─────────────────────────────────────────────────────────────────── #

def _stage(edge_score: float, gap: int, lean: int, rolling_over: bool,
           n_components: int, lag_present: int) -> str:
    """Lifecycle stage: emerging / early / consensus / exhausted / distribution / faltering / quiet."""
    if rolling_over:
        return "faltering" if lean >= 0 else "exhausted"
    if lean < 0:
        return "exhausted" if edge_score < 0.30 else "distribution"
    if lean == 0:
        return "quiet"
    # bullish
    if edge_score < 0.30:
        return "exhausted"
    if edge_score >= 0.66 and gap >= 1 and n_components >= 2 and lag_present >= 1:
        return "emerging"
    if edge_score >= 0.50 and gap >= 0:
        return "early"
    return "consensus"


# ── Falsifier string ──────────────────────────────────────────────────────── #

def _falsifier(altdata_row: dict | None, radar_row: dict | None,
               traj: dict | None, special_flags: dict | None) -> str | None:
    """The most important unanswered disconfirming observation for this name."""
    parts = []
    traj = traj or {}
    if traj.get("rolling_over"):
        parts.append("price is rolling over (20d drawdown + RS falling)")
    if altdata_row:
        conv = _f(altdata_row.get("convergence"))
        if conv is not None and altdata_row.get("side") == "accumulate" and conv < 0.4:
            parts.append("weak altdata convergence score")
    if radar_row:
        rel = radar_row.get("reliability") or {}
        if rel.get("basis") == "unproven":
            parts.append("radar signal unproven (0 resolved outcomes)")
    if special_flags:
        if special_flags.get("unlock_large"):
            parts.append("large lock-up unlock imminent")
        if special_flags.get("pledge_stress"):
            parts.append("pledge stress overhang")
    return "; ".join(parts) if parts else None


# ── Read string ───────────────────────────────────────────────────────────── #

def _read_for(stage: str, lean: int, dirs: dict, edge_score: int, gap: int,
              altdata_row: dict | None) -> str:
    """Plain-language synthesis for this name."""
    pct = int(round(edge_score * 100))
    if stage == "emerging":
        return (f"Altdata/radar leading while news/board are still quiet — pre-consensus, "
                f"~{pct}% of the move still ahead.")
    if stage == "early":
        return f"A leading desk is ahead of the crowd — early, ~{pct}% edge remaining."
    if stage == "faltering":
        return "Price rolling over while desks remain constructive — wait for stabilization."
    if stage == "exhausted":
        return f"Already priced-in across desks — late, only ~{pct}% edge remaining."
    if stage == "distribution":
        return "Desks lean bearish and price is rolling over — distribution phase."
    if stage == "consensus":
        return f"Multiple desks agree with price confirmed — consensus, ~{pct}% edge remaining."
    if stage == "quiet":
        return "No strong cross-desk signal — monitoring."
    return f"Modestly constructive (~{pct}% edge remaining)."


# ── Per-ticker dossier ────────────────────────────────────────────────────── #

def _dossier(ticker: str, altdata_row: dict | None, radar_row: dict | None,
             news_items: list | None, board_row: dict | None,
             special_flags: dict | None, traj: dict | None,
             board_member: bool) -> dict:
    """Build the per-ticker command dossier."""
    dirs = _dirs(altdata_row, radar_row, news_items, board_row)
    gap_rec = _leading_gap(dirs)
    edge_rec = _edge_remaining(dirs, altdata_row, radar_row, board_row,
                               special_flags, traj, board_member)
    traj = traj or {}
    rolling_over = bool(traj.get("rolling_over"))

    # lean: dominant direction
    nz = [d for d in dirs.values() if d not in (None, 0)]
    up = sum(1 for d in nz if d > 0)
    dn = sum(1 for d in nz if d < 0)
    lean = 1 if up > dn else -1 if dn > up else 0

    stage = _stage(edge_rec["score"], gap_rec["gap"], lean, rolling_over,
                   edge_rec["n_components"], gap_rec["lag_present"])

    # signal_core: altdata convergence strength is the one calibrated signal we have
    signal_core = 0.0
    if altdata_row:
        conv = abs(_f(altdata_row.get("convergence")) or 0.0)
        c100 = _f(altdata_row.get("conviction100")) or 0.0
        signal_core = max(conv, c100 / 100.0) * 0.85   # bounded, never full 1.0
    elif radar_row:
        signal_core = float(radar_row.get("strength") or 0.0) * 0.6   # radar alone is weaker

    # falsifier penalty
    fals = _falsifier(altdata_row, radar_row, traj, special_flags)
    fals_pen = 0.85 if fals else 1.0

    # gap multiplier: ±15% per net leading desk, clamped ±2
    gap_mult = 1.0 + 0.15 * max(-2, min(2, gap_rec["gap"]))
    opportunity = round(min(100.0, 100.0 * signal_core * fals_pen * edge_rec["score"] * gap_mult), 1)

    read = _read_for(stage, lean, dirs, edge_rec["score"], gap_rec["gap"], altdata_row)

    # desk directions matrix for display (present=True/False + direction)
    desk_matrix = {
        "news":    {"present": news_items is not None,   "dir": dirs["news"]},
        "altdata": {"present": altdata_row is not None,  "dir": dirs["altdata"]},
        "radar":   {"present": radar_row is not None,    "dir": dirs["radar"]},
        "board":   {"present": board_row is not None,    "dir": dirs["board"]},
        "special": {"present": special_flags is not None,
                    "dir": None},   # special is salience-only; no direction
    }

    # ticker name
    name = ticker
    if altdata_row and altdata_row.get("name") and altdata_row["name"] != ticker:
        name = altdata_row["name"]
    elif board_row and board_row.get("name"):
        nm = board_row.get("name") or ""
        # china names are "English / 中文"; take the zh part if present
        if "/" in nm:
            name = nm.split("/", 1)[1].strip() or nm
        else:
            name = nm

    return {
        "ticker": ticker,
        "name": name,
        "lean": lean,
        "stage": stage,
        "opportunity_score": opportunity,
        "edge_remaining": edge_rec["score"],
        "edge_drivers": edge_rec["drivers"],
        "edge_components": edge_rec["n_components"],
        "leading_gap": gap_rec["gap"],
        "lead_up": gap_rec["lead_up"],
        "lag_up": gap_rec["lag_up"],
        "signal_core": round(signal_core, 3),
        "falsifier": fals,
        "falsifier_penalty": fals_pen,
        "directions": dirs,
        "desk_matrix": desk_matrix,
        "off_desk": not board_member,
        "traj": {
            "ret_20d": traj.get("ret_20d"),
            "rs_20d": traj.get("rs_20d"),
            "rs_60d": traj.get("rs_60d"),
            "off_high_pct": traj.get("off_high_pct"),
            "rolling_over": rolling_over,
        } if traj else None,
        "read": read,
        # raw desk payloads (for transparency, stripped in the compact export)
        "_altdata": altdata_row,
        "_radar": radar_row,
        "_board": board_row,
        "_special": special_flags,
    }


# ── Universe builder ──────────────────────────────────────────────────────── #

def _build_universe(news_bt: dict, altdata_bt: dict, radar_bt: dict,
                    board_rows: dict, board_members: set) -> set:
    """Union of all ticker namespaces. Radar by_ticker already keyed by member ticker."""
    universe = set(altdata_bt.keys()) | set(radar_bt.keys()) | set(board_members)
    # only add news tickers if they also have altdata or radar backing
    # (news-only would flood the list with low-signal names)
    news_with_backing = {t for t in news_bt.keys()
                         if t.upper() in altdata_bt or t.upper() in radar_bt}
    universe |= news_with_backing
    return universe


# ── Discovery lanes ───────────────────────────────────────────────────────── #

def _disc_lhb_first_seat(today: date | None = None) -> list:
    """LHB first-seat: names appearing on LHB for first time in ≥90d (or first inst seat).

    Source: data/china_lhb/events.parquet + detail.parquet.
    Returns list of {ticker, name, disc_score, source, reason, off_desk, experimental}.

    Recent window is SESSION-BASED: events with date >= (max date in events parquet minus
    1 session).  This avoids the calendar-days window failing on Mondays/holidays.
    """
    try:
        import pandas as pd
        td = today or date.today()
        cutoff_90 = pd.Timestamp(td) - pd.Timedelta(days=90)

        events_p = _root() / "data" / "china_lhb" / "events.parquet"
        detail_p = _root() / "data" / "china_lhb" / "detail.parquet"
        if not events_p.exists():
            return []

        ev = pd.read_parquet(events_p)
        ev["date"] = pd.to_datetime(ev["date"], errors="coerce")
        ev = ev.dropna(subset=["date", "ticker"])

        if ev.empty:
            return []

        # SESSION-BASED recent window: anchor on the DATA max date.
        # "Recent" = events with date == max_date in the parquet (the most-recent session).
        # This fixes the Monday/holiday gap: even if the last session was 3 calendar days
        # ago, any event on that session date is picked up.
        all_dates = ev["date"].sort_values().unique()
        max_date = all_dates[-1]
        cutoff_ref = max_date  # include only the most-recent session

        # tickers appearing in the most-recent session
        recent = ev[ev["date"] >= cutoff_ref]
        if recent.empty:
            return []

        # for each recent ticker, check if it appeared before cutoff_90
        candidates = []
        for ticker in recent["ticker"].unique():
            hist = ev[(ev["ticker"] == ticker) & (ev["date"] < cutoff_90)]
            is_first = len(hist) == 0  # first appearance in 90d window

            # also check for first institutional seat
            inst_first = False
            if detail_p.exists():
                try:
                    detail = pd.read_parquet(detail_p)
                    row = detail[detail["ticker"] == ticker]
                    if not row.empty:
                        n_inst = int(row["n_inst_buy"].iloc[0] or 0)
                        inst_first = n_inst > 0 and len(hist) < 3  # few prior appearances + inst seat
                except Exception:  # noqa: BLE001
                    pass

            if is_first or inst_first:
                # disc_score: higher if both first-time AND has institutional seat
                dsc = 0.75 if (is_first and inst_first) else (0.65 if is_first else 0.50)
                rec = recent[recent["ticker"] == ticker].iloc[0]
                reason = ("First LHB + institutional seat" if inst_first and is_first
                          else "First LHB seat in 90+ days" if is_first
                          else "First institutional seat on LHB")
                candidates.append({
                    "ticker": str(ticker),
                    "name": str(rec.get("name") or ticker),
                    "disc_score": round(dsc, 2),
                    "source": "lhb_first_seat",
                    "reason": reason,
                    "off_desk": True,
                    "experimental": False,
                    "lhb_date": str(rec["date"])[:10],
                })

        candidates.sort(key=lambda x: x["disc_score"], reverse=True)
        return candidates[:_LANE_EMIT_CAP]
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: LHB first-seat lane failed (%s)", e)
        return []


def _disc_margin_velocity(today: date | None = None) -> list:
    """Margin velocity: per-name financing-balance 20d delta z.

    EXPERIMENTAL — contributes ZERO to opportunity/ranking.  Always carries
    experimental=True.  The lane lists names but is display-gated with a caveat chip.
    Phase-0 clock: 60-session minimum before any ranking contribution.
    """
    try:
        import pandas as pd
        import math
        p = _root() / "data" / "china_margin_detail" / "detail.parquet"
        if not p.exists():
            return []

        df = pd.read_parquet(p)
        df = df.dropna(subset=["ticker", "fin_balance", "fin_balance_prior"])
        if df.empty:
            return []

        # take the most recent snapshot date
        recent_date = df["date"].max()
        recent = df[df["date"] == recent_date].copy()

        # 20d delta = fin_balance - fin_balance_prior; z-score
        recent["delta"] = recent["fin_balance"] - recent["fin_balance_prior"]
        mu = float(recent["delta"].mean())
        std = float(recent["delta"].std())
        if std == 0 or math.isnan(std):
            return []

        recent["delta_z"] = (recent["delta"] - mu) / std
        top = recent.nlargest(20, "delta_z")

        candidates = []
        for _, row in top.iterrows():
            dz = float(row["delta_z"])
            if dz < 1.0:
                break
            dsc = _clamp01(0.4 + min(dz / 4.0, 0.4))
            candidates.append({
                "ticker": str(row["ticker"]),
                "name": str(row["ticker"]),
                "disc_score": round(dsc, 2),
                "source": "margin_velocity",
                "reason": f"Margin financing delta z={dz:.1f} (20d increase vs peers)",
                "off_desk": True,
                "experimental": True,
                "caveat": "EXPERIMENTAL — Phase-0 accruing (60-session gate). Contributes zero to opportunity ranking.",
            })

        return candidates[:_LANE_EMIT_CAP]
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: margin velocity lane failed (%s)", e)
        return []


def _disc_southbound_delta(today: date | None = None) -> list:
    """Southbound holdings delta: largest 20d holding increases (HK-listed names).

    Source: data/hk_southbound/holdings.parquet. venue='HK'.
    """
    try:
        import pandas as pd
        p = _root() / "data" / "hk_southbound" / "holdings.parquet"
        if not p.exists():
            return []

        df = pd.read_parquet(p)
        if df.empty:
            return []

        dates = df.index.get_level_values("date").unique().sort_values()
        if len(dates) < 2:
            return []

        recent_date = dates[-1]
        # look for ~20d-ago date
        target_prior = recent_date - pd.Timedelta(days=22)
        prior_dates = dates[dates <= target_prior]
        if prior_dates.empty:
            prior_date = dates[0]
        else:
            prior_date = prior_dates[-1]

        recent_df = df.xs(recent_date, level="date")
        prior_df = df.xs(prior_date, level="date")

        # align and compute delta in hold_shares
        merged = recent_df[["name", "hold_shares"]].join(
            prior_df[["hold_shares"]].rename(columns={"hold_shares": "hold_shares_prior"}),
            how="inner")
        merged = merged.dropna()
        merged["delta_shares"] = merged["hold_shares"] - merged["hold_shares_prior"]
        merged["delta_pct"] = merged["delta_shares"] / (merged["hold_shares_prior"].abs() + 1.0) * 100.0
        top = merged.nlargest(20, "delta_pct")

        candidates = []
        for ticker, row in top.iterrows():
            dp = float(row["delta_pct"])
            if dp < 2.0:
                break
            dsc = _clamp01(0.35 + min(dp / 30.0, 0.45))
            candidates.append({
                "ticker": str(ticker),
                "name": str(row.get("name") or ticker),
                "disc_score": round(dsc, 2),
                "source": "southbound_delta",
                "reason": f"Southbound holdings +{dp:.1f}% over 20d",
                "off_desk": True,
                "experimental": False,
                "venue": "HK",
            })

        candidates.sort(key=lambda x: x["disc_score"], reverse=True)
        return candidates[:_LANE_EMIT_CAP]
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: southbound delta lane failed (%s)", e)
        return []


def _disc_ths_emerging_concepts(today: date | None = None) -> list:
    """THS emerging concepts: concepts newly firing, mapped to 2-3 member names max.

    Source: data/emergence_china/alerts.jsonl + state.json.
    """
    try:
        import json as _json
        td = today or date.today()
        alerts_p = _root() / "data" / "emergence_china" / "alerts.jsonl"
        if not alerts_p.exists():
            return []

        # read last 30 lines of alerts
        lines = alerts_p.read_text(encoding="utf-8").splitlines()[-30:]
        candidates = []
        seen_tickers: set = set()

        for line in reversed(lines):
            try:
                alert = _json.loads(line.strip())
            except Exception:  # noqa: BLE001
                continue

            # recency gate: within last 7 days
            ts_str = str(alert.get("ts") or "")[:10]
            try:
                from datetime import date as _date
                ts_date = _date.fromisoformat(ts_str)
                if (td - ts_date).days > 7:
                    continue
            except (ValueError, TypeError):
                pass

            context = alert.get("context") or {}
            recommended_str = str(context.get("recommended") or "")
            if not recommended_str:
                continue

            tickers_in_concept = [t.strip() for t in recommended_str.split(",")
                                   if t.strip()][:3]   # cap at 3 per concept

            score = _clamp01(float(context.get("score") or 0.0) / 100.0)
            concept_name = alert.get("headline_zh") or alert.get("headline") or "Emerging concept"
            # strip emoji prefix
            concept_name = concept_name.lstrip("🔥 ").strip()

            for t in tickers_in_concept:
                if t in seen_tickers:
                    continue
                seen_tickers.add(t)
                dsc = _clamp01(0.30 + score * 0.35)
                candidates.append({
                    "ticker": t,
                    "name": t,
                    "disc_score": round(dsc, 2),
                    "source": "ths_emerging_concepts",
                    "reason": f"THS emerging concept: {concept_name[:60]}",
                    "off_desk": True,
                    "experimental": False,
                })

        candidates.sort(key=lambda x: x["disc_score"], reverse=True)
        return candidates[:_LANE_EMIT_CAP]
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: THS emerging concepts lane failed (%s)", e)
        return []


# ── Snapshot ledger ───────────────────────────────────────────────────────── #

def _append_snapshot_ledger(command: list, today: date, guard_env: bool = True) -> None:
    """Append {date, ticker, opportunity, edge, stage, lean} rows to
    data/china_hub/signal_snapshots.jsonl.

    Idempotent by date: skips if today's rows already exist.
    Guard: only writes under CN_LANE=asia (set in asia-close.yml).
    """
    if guard_env and os.environ.get("CN_LANE") != "asia":
        log.debug("china_intel_hub: snapshot ledger skipped (CN_LANE != asia)")
        return
    try:
        out_dir = _root() / "data" / "china_hub"
        out_dir.mkdir(parents=True, exist_ok=True)
        snap_path = out_dir / "signal_snapshots.jsonl"
        today_str = today.isoformat()

        # idempotency: check the LAST WRITTEN date by reading the final non-empty line
        if snap_path.exists():
            content = snap_path.read_text(encoding="utf-8")
            # find last non-empty line (not a fixed 5-line tail)
            last_date = None
            for line in reversed(content.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    last_date = row.get("date")
                except Exception:  # noqa: BLE001
                    pass
                break  # stop after first non-empty line from end
            if last_date == today_str:
                log.debug("china_intel_hub: snapshot already written for %s", today_str)
                return

        rows = []
        for d in command:
            rows.append(json.dumps({
                "date": today_str,
                "ticker": d["ticker"],
                "opportunity": d["opportunity_score"],
                "edge": d["edge_remaining"],
                "stage": d["stage"],
                "lean": d["lean"],
            }))

        with snap_path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(row + "\n")
        log.info("china_intel_hub: wrote %d snapshot rows for %s", len(rows), today_str)
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: snapshot ledger write failed (%s)", e)


# ── Analogs block ─────────────────────────────────────────────────────────── #

def _analogs_block() -> dict | None:
    """Read site/china_intel/analogs.json (schema china_intel.analogs.v1).

    Contract with parallel program — this file is absent today; the block returns None
    and the hub card is hidden.  When the parallel program ships the artifact, this reader
    auto-lights it up without code changes.

    FORBIDDEN words in this card: 'expected', 'predicts', 'signal' — descriptive fan only.
    """
    try:
        d = _read_json("site/china_intel/analogs.json")
        if not isinstance(d, dict):
            return None
        if d.get("schema") != "china_intel.analogs.v1":
            log.debug("china_intel_hub: analogs schema mismatch: %s", d.get("schema"))
            return None
        # validate minimal required keys
        if not d.get("fan") or not d.get("query"):
            return None
        return {
            "as_of": d.get("as_of"),
            "coverage": d.get("coverage"),
            "query": d.get("query"),
            "analogs": (d.get("analogs") or [])[:12],
            "fan": d.get("fan"),
            "method_note": d.get("method_note"),
            "disclaimer_en": d.get("disclaimer_en"),
            "disclaimer_zh": d.get("disclaimer_zh"),
            "n_analogs": len(d.get("analogs") or []),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_intel_hub: analogs block failed (%s)", e)
        return None


# ── Desks summary matrix ──────────────────────────────────────────────────── #

def _desks_summary(command: list) -> dict:
    """Compact desk-status summary for the hub card."""
    return {
        "news":    {"live": any(d["desk_matrix"]["news"]["present"] for d in command)},
        "altdata": {"live": any(d["desk_matrix"]["altdata"]["present"] for d in command)},
        "radar":   {"live": any(d["desk_matrix"]["radar"]["present"] for d in command)},
        "board":   {"live": any(d["desk_matrix"]["board"]["present"] for d in command)},
        "special": {"live": any(d["desk_matrix"]["special"]["present"] for d in command)},
    }


# ── Compact export ────────────────────────────────────────────────────────── #

def _compact(d: dict) -> dict:
    """Strip internal _* fields for the command list export."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ── Main build ────────────────────────────────────────────────────────────── #

def build(today: date | None = None, top: int = 30) -> dict:
    """Fuse all China intelligence legs into the command view.

    Never raises.  Returns a dict with schema=china_intel.command.v1.
    """
    today = today or date.today()
    try:
        return _build_inner(today, top)
    except Exception as e:  # noqa: BLE001
        log.error("china_intel_hub.build failed (%s); returning empty command", e)
        return _empty(today)


def _empty(today: date) -> dict:
    return {
        "schema": SCHEMA, "is_context_only": True,
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "command": [], "discovery": [], "n_universe": 0,
        "desks": {}, "counts": {}, "disclaimer": DISCLAIMER,
    }


def _build_inner(today: date, top: int) -> dict:
    # ── 1. Load all inputs ──────────────────────────────────────────────── #
    news_bt = _load_news_by_ticker()
    altdata_bt = _load_altdata_by_ticker()
    radar_rows = _load_radar_by_sector()
    radar_bt = _build_radar_by_ticker(radar_rows)
    board_members = _load_board_membership()
    board_rows = _load_board_rows()
    special_bt = _load_special_by_ticker()

    # normalize keys to upper-case for all dicts
    def _norm(d: dict) -> dict:
        return {str(k).upper().strip(): v for k, v in (d or {}).items()}

    news_bt = _norm(news_bt)
    altdata_bt = _norm(altdata_bt)
    radar_bt = _norm(radar_bt)
    board_members = {str(t).upper().strip() for t in board_members}
    board_rows = _norm(board_rows)
    special_bt = _norm(special_bt)

    # ── 2. Build universe ───────────────────────────────────────────────── #
    universe = _build_universe(news_bt, altdata_bt, radar_bt, board_rows, board_members)

    # ── 3. Load price data once ─────────────────────────────────────────── #
    closes, bench = _load_closes_and_benchmark()

    # ── 4. Per-ticker dossiers ──────────────────────────────────────────── #
    dossiers = []
    for ticker in universe:
        altdata_row = altdata_bt.get(ticker)
        radar_row = radar_bt.get(ticker)
        news_items = news_bt.get(ticker)    # None = desk absent; [] = present but empty
        board_row = board_rows.get(ticker)
        board_member = ticker in board_members
        special_flags = special_bt.get(ticker)
        traj = _price_trajectory(ticker, closes, bench)
        d = _dossier(ticker, altdata_row, radar_row, news_items, board_row,
                     special_flags, traj, board_member)

        # ── BLOCKER 3b: price-plane missing → veto_blind, honest opportunity ── #
        veto_blind = traj is None  # No price data from either source
        d["veto_blind"] = veto_blind
        if veto_blind:
            # opportunity computed WITHOUT the edge multiplier (the 0.75 board-absent constant
            # must NOT be awarded as sole edge component when price is absent)
            edge_rec_score = d["edge_remaining"]
            if d.get("edge_components", 0) == 1 and not d.get("traj"):
                # sole component is board-absent bonus — that's the flat 0.75 constant
                # Do NOT count it when price plane is absent: opportunity = 0
                d["opportunity_score"] = 0.0
            # else: keep opportunity as computed (there's a board_row or other component)

        dossiers.append(d)

    # ── 5. MAJOR 5: exclude signal_core==0 board-only names from command ── #
    # They stay in n_universe and counts.board_only_unranked.
    # No leading signal ⇒ no opportunity claim in the ranked list.
    board_only_unranked = [d for d in dossiers if d.get("signal_core", 0) == 0]
    ranked_dossiers = [d for d in dossiers if d.get("signal_core", 0) > 0]

    # ── 5a. Anti-echo-chamber ranking (the law) ─────────────────────────── #
    # Sort key: (veto_blind ASC so priced rows rank above veto-blind at equal signal,
    #            opportunity_score DESC, edge_remaining DESC)
    ranked_dossiers.sort(
        key=lambda d: (d.get("veto_blind", False), -d["opportunity_score"], -d["edge_remaining"])
    )

    # ── 6. Command list (compact, strip _* fields) ──────────────────────── #
    command = [_compact(d) for d in ranked_dossiers[:top]]

    # ── 7. Discovery lanes ──────────────────────────────────────────────── #
    lhb = _disc_lhb_first_seat(today)
    margin_vel = _disc_margin_velocity(today)
    sb_delta = _disc_southbound_delta(today)
    ths_concepts = _disc_ths_emerging_concepts(today)

    # mark off_desk relative to command list tickers
    cmd_tickers = {d["ticker"] for d in command}
    for lane in (lhb, margin_vel, sb_delta, ths_concepts):
        for c in lane:
            c["off_desk"] = c.get("ticker") not in cmd_tickers

    # interleave top discoveries (source-diversified, experimental last)
    discovery_queue: list = []
    seen_disc: set = set()
    for cand in sorted(lhb + sb_delta + ths_concepts,
                       key=lambda c: c["disc_score"], reverse=True):
        t = cand.get("ticker")
        if t and t not in seen_disc:
            seen_disc.add(t)
            discovery_queue.append(cand)
        if len(discovery_queue) >= _DISCOVERY_TOP:
            break
    # experimental margin lane appended separately (always last, clearly labeled)
    discovery_queue += margin_vel[:3]

    # ── 8. Analogs block ────────────────────────────────────────────────── #
    analogs = _analogs_block()

    # ── 9. Snapshot ledger (ranked rows only — already top-top cap) ─────── #
    _append_snapshot_ledger(ranked_dossiers, today)

    # ── 10. Counts ──────────────────────────────────────────────────────── #
    # Stage counts over ALL dossiers (universe = ranked + board_only_unranked)
    all_dossiers = ranked_dossiers + board_only_unranked
    counts = {
        "emerging": sum(1 for d in ranked_dossiers if d["stage"] == "emerging"),
        "early": sum(1 for d in ranked_dossiers if d["stage"] == "early"),
        "consensus": sum(1 for d in ranked_dossiers if d["stage"] == "consensus"),
        "exhausted": sum(1 for d in ranked_dossiers if d["stage"] == "exhausted"),
        "faltering": sum(1 for d in ranked_dossiers if d["stage"] == "faltering"),
        "distribution": sum(1 for d in ranked_dossiers if d["stage"] == "distribution"),
        "quiet": sum(1 for d in ranked_dossiers if d["stage"] == "quiet"),
        "board_members": len(board_members),
        "with_price": sum(1 for d in ranked_dossiers if d.get("traj") is not None),
        "veto_blind": sum(1 for d in command if d.get("veto_blind")),
        "board_only_unranked": len(board_only_unranked),
    }

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_universe": len(all_dossiers),
        "command": command,
        "discovery": discovery_queue,
        "analogs": analogs,
        "desks": _desks_summary(command),
        "counts": counts,
        "how_to_use": (
            "Ranked by OPPORTUNITY = signal_core × edge_remaining × leading_gap_multiplier. "
            "'emerging' = altdata/radar lead while board/news are still quiet (pre-consensus). "
            "'exhausted' = priced-in across all desks. Discovery lanes surface off-desk names. "
            "Margin velocity lane is EXPERIMENTAL (Phase-0 accruing, contributes zero to ranking). "
            "board_only_unranked = names with signal_core==0 excluded from ranking (no leading signal)."
        ),
        "disclaimer": DISCLAIMER,
    }


def load_and_build(today: date | None = None, top: int = 30) -> dict:
    """Entry point for the builder script. Calls build(). Never raises."""
    return build(today, top)
