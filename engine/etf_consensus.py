"""Cross-fund consensus over the ETF holdings radar — "which stocks are the
curated/active funds collectively favoring, and where is real position-sizing
moving?"

This sits ON TOP of ``engine.holdings_signals`` (the per-fund flow-normalized
share-decision engine, D71) and adds three read-only, display-only aggregations
for the rebuilt ``etfs.html``:

  * ``consensus_favored`` — group every flagged fund decision by the STOCK it
    touched, so a name accumulated by several funds at once (real cross-manager
    conviction) rises above a single fund's idiosyncratic add.
  * ``weight_trajectory`` — the last N daily weight_pct readings for one
    (fund, ticker) pair, so the page can draw a sparkline of position sizing
    growing / shrinking over time.
  * ``fund_coverage`` — per-fund freshness + depth (latest snapshot, #snapshots,
    sponsor, theme), so the page can show the whole tracked universe and surface
    any feed that has gone stale.

Everything here is additive and degrade-never-raise: a missing store, an
unreadable parquet, or an engine error yields ``[]`` / ``None`` and the page
simply hides that panel. It NEVER feeds a score, size, or allocation path — same
contract as the rest of the holdings plane.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Ladder states that confirm an accumulation read (mirror holdings_signals so the
# ✅ on the consensus board means the same thing as on the per-fund tables).
try:  # pragma: no cover - trivial import guard
    from engine.holdings_signals import BULLISH_STATES
except Exception:  # noqa: BLE001
    BULLISH_STATES = {"FRESH BUY", "TURN SIGNALED", "RALLY ON", "BOTTOM WATCH"}


def _cfg() -> dict:
    return config.load().get("etf_holdings", {}) or {}


# --------------------------------------------------------------------------- #
# W1 roll-up helpers — the flow/selection decomposition each fund row carries
# (engine.holdings_signals), aggregated across the funds touching one stock. The
# equal-weight fund COUNTS stay the primary read (masterplan §4: breadth is the
# most manipulation-resistant stat); dollars and the flow/selection split are the
# secondary lens beside them, and every one of them degrades to a printed null
# when the sponsor publishes no market values.
# --------------------------------------------------------------------------- #
def _roll_decomposition(g: dict, r: dict) -> None:
    """Accumulate one fund's decomposition into the ticker's group."""
    g["n_funds_any"] += 1
    driver = r.get("driver")
    if driver == "flow":
        g["n_funds_flow"] += 1
    elif driver == "selection":
        g["n_funds_selection"] += 1
    total_usd = r.get("total_usd")
    if total_usd is not None:
        g["n_funds_usd"] += 1
        g["total_usd"] += total_usd
        g["flow_usd"] += r.get("flow_usd") or 0.0
        g["selection_usd"] += r.get("selection_usd") or 0.0
    g["net_flow_pp"] += r.get("flow_pp") or 0.0
    g["net_selection_pp"] += r.get("selection_pp") or 0.0
    streak = int(r.get("streak") or 0)
    if streak > 0:
        g["breadth"] += 1
    if abs(streak) > abs(g["max_streak"]):
        g["max_streak"] = streak
    if r.get("is_stale"):
        g["n_stale"] += 1
    if r.get("split_adjusted"):
        g["n_split_adjusted"] += 1
    if r.get("exit_confirmed"):
        g["n_exit_confirmed"] += 1
    accel = r.get("accel_pct_per_day")
    if accel is not None:
        g["_accel"].append(accel)


def _finish_decomposition(g: dict) -> None:
    """Round the roll-up and set the two derived reads: whether the dollar
    estimate covers every fund on the row, and whether investor flow and manager
    selection point OPPOSITE ways — a real disagreement inside one stock that the
    plain accum-vs-trim `contested` flag cannot see."""
    for k in ("total_usd", "flow_usd", "selection_usd"):
        g[k] = round(g[k], 2)
    g["net_flow_pp"] = round(g["net_flow_pp"], 4)
    g["net_selection_pp"] = round(g["net_selection_pp"], 4)
    accel = g.pop("_accel", [])
    g["accel_pct_per_day"] = round(sum(accel) / len(accel), 4) if accel else None
    g["usd_complete"] = g["n_funds_usd"] == g["n_funds_any"]
    g["contested_components"] = bool(
        g["flow_usd"] * g["selection_usd"] < 0
        and min(abs(g["flow_usd"]), abs(g["selection_usd"])) > 0.05 * abs(g["total_usd"] or 1.0))


# --------------------------------------------------------------------------- #
# 1. Cross-fund consensus — favored stocks
# --------------------------------------------------------------------------- #
def consensus_favored(rows: list[dict] | None = None,
                      limit: int | None = None,
                      min_funds: int | None = None) -> list[dict]:
    """Aggregate every flagged fund decision by the underlying stock.

    Input rows are ``engine.holdings_signals.all_etf_signals()`` output (or a
    caller-supplied equivalent). For each ticker we count how many funds are
    accumulating vs trimming, sum the conviction (percentage points of fund
    weight committed, signed), and carry the per-fund detail so the page can list
    "3 funds adding, led by BUG +5.3pp". Ranked so broad, high-conviction
    accumulation surfaces first.

    ``min_funds`` (default 1) filters out single-fund names from the headline
    board — a name multiple funds touch is the stronger cross-manager read.

    Each row additionally carries the W1 roll-up: ``total_usd``/``flow_usd``/
    ``selection_usd`` (with ``n_funds_usd``/``usd_complete`` disclosing how much
    of the row the dollar estimate actually covers), ``n_funds_flow`` vs
    ``n_funds_selection`` (which component drove each fund's move),
    ``breadth``/``max_streak``/``accel_pct_per_day`` (persistence) and
    ``contested_components``. Ranking is unchanged — still breadth of
    accumulation, then net conviction — so none of this promotes anything.
    """
    cfg = _cfg()
    limit = limit or cfg.get("consensus_top_n", 40)
    min_funds = min_funds if min_funds is not None else cfg.get("consensus_min_funds", 1)

    if rows is None:
        try:
            from engine.holdings_signals import all_etf_signals
            rows = all_etf_signals()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("consensus_favored: all_etf_signals failed: %s", e)
            return []
    if not rows:
        return []

    by_ticker: dict[str, dict] = {}
    for r in rows:
        tk = r.get("ticker")
        if not tk:
            continue
        conv = r.get("conviction_pp")
        if conv is None:
            continue
        direction = r.get("direction", "")
        g = by_ticker.get(tk)
        if g is None:
            g = by_ticker[tk] = {
                "ticker": tk,
                "name": r.get("name", ""),
                "sector": r.get("sector", ""),
                "ladder": r.get("ladder"),
                "confirmed": False,
                "funds": [],
                "n_accum": 0, "n_trim": 0, "n_new": 0, "n_exit": 0,
                "net_conviction_pp": 0.0, "gross_conviction_pp": 0.0,
                "is_active_any": False,
                # W1 decomposition roll-up (masterplan §3): dollars beside the
                # equal-weight counts, and flow kept apart from selection.
                "total_usd": 0.0, "flow_usd": 0.0, "selection_usd": 0.0,
                "net_flow_pp": 0.0, "net_selection_pp": 0.0,
                "n_funds_any": 0, "n_funds_flow": 0, "n_funds_selection": 0,
                "n_funds_usd": 0, "breadth": 0, "max_streak": 0,
                "n_stale": 0, "n_split_adjusted": 0, "n_exit_confirmed": 0,
                "_accel": [],
            }
        # keep the richest name / sector / ladder we see for this ticker
        if r.get("name") and len(str(r.get("name"))) > len(str(g["name"])):
            g["name"] = r["name"]
        if not g["sector"] and r.get("sector"):
            g["sector"] = r["sector"]
        if g["ladder"] is None and r.get("ladder"):
            g["ladder"] = r["ladder"]
        g["confirmed"] = g["confirmed"] or bool(r.get("confirmed"))
        g["is_active_any"] = g["is_active_any"] or bool(r.get("is_active"))
        g["funds"].append({
            "fund": r.get("etf"), "fund_name": r.get("etf_name", r.get("etf")),
            "category": r.get("category", ""), "is_active": bool(r.get("is_active")),
            "conviction_pp": conv, "direction": direction,
            "weight_pct": r.get("weight_pct"),
            "is_new": bool(r.get("is_new")), "is_exit": bool(r.get("is_exit")),
            "active_chg_pct": r.get("active_chg_pct"),
            "flow_usd": r.get("flow_usd"), "selection_usd": r.get("selection_usd"),
            "total_usd": r.get("total_usd"), "driver": r.get("driver"),
            "streak": r.get("streak") or 0, "is_stale": bool(r.get("is_stale")),
        })
        if conv > 0:
            g["n_accum"] += 1
        elif conv < 0:
            g["n_trim"] += 1
        if r.get("is_new"):
            g["n_new"] += 1
        if r.get("is_exit"):
            g["n_exit"] += 1
        g["net_conviction_pp"] += conv
        g["gross_conviction_pp"] += abs(conv)
        _roll_decomposition(g, r)

    out = []
    for g in by_ticker.values():
        if (g["n_accum"] + g["n_trim"]) < min_funds:
            continue
        g["funds"].sort(key=lambda f: -abs(f.get("conviction_pp") or 0))
        g["net_conviction_pp"] = round(g["net_conviction_pp"], 4)
        g["gross_conviction_pp"] = round(g["gross_conviction_pp"], 4)
        # net direction across funds
        g["direction"] = ("accumulating" if g["net_conviction_pp"] > 0
                          else "distributing" if g["net_conviction_pp"] < 0 else "mixed")
        # a stock is "contested" when funds disagree — worth flagging honestly
        g["contested"] = g["n_accum"] > 0 and g["n_trim"] > 0
        _finish_decomposition(g)
        out.append(g)

    # headline ranking: breadth of accumulation first, then net conviction. A name
    # several funds are adding to outranks one fund's large idiosyncratic add.
    out.sort(key=lambda g: (-g["n_accum"], -g["net_conviction_pp"], -g["gross_conviction_pp"]))
    return out[:limit]


# --------------------------------------------------------------------------- #
# 2. Weight trajectory — position sizing over time (for a sparkline)
# --------------------------------------------------------------------------- #
def _fund_snapshot_dir(fund: str) -> Path | None:
    """Locate the daily-snapshot directory for a fund across both stores:
    curated/thematic (data/etf_holdings/<FUND>) and active watchlist
    (data/holdings/<FUND>, e.g. ARK). Returns None if neither exists."""
    cfg = config.load()
    cand = [config.data_dir() / "etf_holdings" / fund]
    try:
        cand.append(config.ROOT / cfg["storage"]["holdings_dir"] / fund)
    except Exception:  # noqa: BLE001
        pass
    for d in cand:
        if d.exists() and any(d.glob("*.parquet")):
            return d
    return None


def weight_trajectory(fund: str, ticker: str, k: int = 12) -> list[dict]:
    """Last ``k`` (as_of, weight_pct) points for one (fund, ticker), oldest→newest,
    for a position-sizing sparkline. Reads the daily snapshots directly. Returns
    [] on any problem (never raises). The weight column name varies by sponsor, so
    we resolve it flexibly (weight_pct / weight / '% ...')."""
    d = _fund_snapshot_dir(fund)
    if d is None:
        return []
    snaps = sorted(d.glob("*.parquet"))[-k:]
    tk = str(ticker)
    pts: list[dict] = []
    for p in snaps:
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001 — a corrupt snapshot must not break the row
            continue
        if "ticker" not in df.columns:
            continue
        wcol = next((c for c in df.columns if "weight" in c.lower()), None)
        if wcol is None:
            continue
        sub = df[df["ticker"].astype(str) == tk]
        if sub.empty:
            continue
        w = pd.to_numeric(
            sub[wcol].astype(str).str.replace(r"[,%$]", "", regex=True),
            errors="coerce").dropna()
        if w.empty:
            continue
        pts.append({"as_of": p.stem, "weight_pct": round(float(w.iloc[-1]), 4)})
    return pts


def attach_trajectories(rows: list[dict], k: int = 12, cap: int | None = None) -> None:
    """Mutate ``rows`` in place, attaching ``weight_series`` (list of weight_pct
    floats, oldest→newest) to each — bounded to the first ``cap`` rows because the
    parquet reads are the expensive part. Rows beyond the cap get an empty series."""
    for i, r in enumerate(rows):
        if cap is not None and i >= cap:
            r["weight_series"] = []
            continue
        traj = weight_trajectory(r.get("etf") or r.get("fund"), r.get("ticker"), k=k)
        r["weight_series"] = [p["weight_pct"] for p in traj]


# --------------------------------------------------------------------------- #
# 3. Fund coverage — the tracked universe + freshness
# --------------------------------------------------------------------------- #
def fund_coverage() -> list[dict]:
    """Every tracked fund with its snapshot depth + freshness, so the page can
    show the full coverage universe and surface any feed that has gone stale.
    Spans both stores (curated etf_holdings + active watchlist)."""
    cfg = config.load()
    out: list[dict] = []
    latest_seen: list[pd.Timestamp] = []

    def _scan(root: Path, spec_map: dict, active: bool) -> None:
        for fund, spec in spec_map.items():
            d = root / fund
            snaps = sorted(d.glob("*.parquet")) if d.exists() else []
            asof = snaps[-1].stem if snaps else None
            ts = None
            if asof:
                try:
                    ts = pd.to_datetime(asof)
                    latest_seen.append(ts)
                except Exception:  # noqa: BLE001
                    ts = None
            out.append({
                "fund": fund,
                "fund_name": spec.get("name", fund),
                "sponsor": spec.get("sponsor", "watchlist" if active else ""),
                "category": spec.get("category", "Active / Innovation" if active else ""),
                "is_active": active,
                "unofficial": bool(spec.get("sponsor") == "stockanalysis"),
                "n_snapshots": len(snaps),
                "latest_asof": asof,
                "_ts": ts,
            })

    try:
        _scan(config.data_dir() / "etf_holdings",
              cfg.get("etf_holdings", {}).get("universe", {}), active=False)
    except Exception as e:  # noqa: BLE001
        log.error("fund_coverage etf_holdings scan failed: %s", e)
    try:
        _scan(config.ROOT / cfg["storage"]["holdings_dir"],
              cfg.get("holdings", {}).get("watchlist", {}), active=True)
    except Exception as e:  # noqa: BLE001
        log.error("fund_coverage watchlist scan failed: %s", e)

    # freshness relative to the newest snapshot anywhere (avoids clock/timezone
    # arguments about "today" — staleness is measured against the fleet's own edge)
    fleet_latest = max(latest_seen) if latest_seen else None
    for r in out:
        ts = r.pop("_ts", None)
        if ts is not None and fleet_latest is not None:
            r["stale_days"] = int((fleet_latest - ts).days)
        else:
            r["stale_days"] = None
    # order: freshest & deepest first, dead feeds (0 snapshots) last
    out.sort(key=lambda r: (r["n_snapshots"] == 0,
                            r["stale_days"] if r["stale_days"] is not None else 1e9,
                            -r["n_snapshots"]))
    return out
