"""Capital-flow VELOCITY — how fast (and accelerating) big money is moving into China /
Hong Kong names and sectors, off data the build already collects.

The user's ask: *"track how big money is flowing into certain equities and sectors —
daily / weekly / monthly — and track velocity."* This engine turns the existing net-flow
series into a kinetics read:

  • LEVEL      — net flow over a window (¥ for the aggregate channels; a normalized
                 main-money net-RATE for the per-name A-share grid).
  • VELOCITY   — the standardized recent net-flow rate (t-stat of the trailing drift of
                 cumulative flow vs its own vol). + = money flowing IN faster than normal.
  • ACCELERATION — the 2nd derivative: is that velocity itself rising or fading.

Four panels, each from a source ALREADY on disk (keyless at build time — no Tushare call):

  aggregate      data/china_connect/{southbound,northbound}  — the whole-channel "all
                 mainland / all foreign money" tape. Southbound is live & deep (2014→);
                 NORTHBOUND aggregate net was discontinued 2024-08-16 under the Stock
                 Connect "home-market" rule, so it is surfaced as HISTORICAL-ONLY.
  ashare_names   data/tushare/flow_hist.parquet  — weekly per-name 主力 (super-large +
                 large order) net-RATE grid; velocity/acceleration per name, ranked.
  ashare_sectors the same grid rolled into the 22 curated baskets_china sectors
                 (equal-weight member mean) — "which sector is big money rushing into".
  ashare_seats   data/china_lhb/detail.parquet  — Dragon-Tiger 机构专用 institutional-seat
                 net buys: the closest free *institution-level* read for A-shares (seats
                 are anonymous; a recent-window snapshot, not a velocity).
  hk_names       data/hk_southbound/holdings.parquet — mainland's per-name southbound
                 holdings; the daily history is still SHALLOW, so multi-horizon velocity
                 unlocks as it accrues — until then the 5/10-day accumulation board shows.

HONESTY GATE (house rule, [[signal-contract-gate]]): this is a DISPLAY / CONTEXT desk.
Flow is NEVER scored into an allocation signal (the codebase tested per-name fund-flow:
rank-IC ≈ −0.008, no edge — research/CHINA_HK_STOCK_SIGNALS.md). Velocity here is a
*positioning lens*, not alpha. All transforms are causal & point-in-time; every loader is
None-safe so a missing/stale parquet drops its panel and the page still builds.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine import indicators
from lib import config

log = logging.getLogger(__name__)

# ── horizon configs (windows are in the SOURCE's native bars) ─────────────────
# aggregate channels are DAILY; the per-name / sector grid is WEEKLY (~5th trading day).
_AGG = {"horizons": {"1w": 5, "1m": 21, "3m": 63}, "primary": "1m",
        "base": 126, "accel_w": 21, "min_obs": 80}
_WK = {"horizons": {"4wk": 4, "13wk": 13}, "primary": "4wk",
       "base": 13, "accel_w": 6, "min_obs": 20}

NORTHBOUND_FROZEN = "2024-08-16"   # last aggregate northbound net (home-market rule)


# ── kinetics primitive ────────────────────────────────────────────────────────
def _kinetics(flow: pd.Series, cfg: dict) -> dict | None:
    """Velocity + acceleration of a per-period NET-FLOW series.

    Velocity at window w = ``slope_z(cumflow, w, base)`` — because d(cumflow) = flow, this
    is the t-stat of the recent average net-flow vs its own vol (a unit-free, cross-source
    comparable "how fast is money moving" read). Acceleration = the trailing slope of the
    primary-horizon velocity series (is the inflow speeding up). None when too short.
    """
    flow = pd.to_numeric(flow, errors="coerce").dropna()
    if len(flow) < cfg["min_obs"]:
        return None
    cum = flow.cumsum()
    base = min(cfg["base"], max(8, len(flow) // 2))
    vel: dict[str, float | None] = {}
    for lab, w in cfg["horizons"].items():
        if len(flow) < w + 2:
            vel[lab] = None
            continue
        z = indicators.slope_z(cum, w, base, use_log=False)
        v = z.iloc[-1] if len(z) else np.nan
        vel[lab] = round(float(v), 2) if v is not None and np.isfinite(v) else None
    pw = cfg["horizons"][cfg["primary"]]
    vser = indicators.slope_z(cum, pw, base, use_log=False)
    accel = np.nan
    if len(vser.dropna()) > cfg["accel_w"] + 2:
        a = indicators.rolling_slope(vser, cfg["accel_w"]).iloc[-1]
        accel = float(a) if a is not None and np.isfinite(a) else np.nan
    vmid = vel.get(cfg["primary"])
    en, zh = _classify(vmid, accel)
    return {"vel": vel, "vel_primary": vmid, "primary": cfg["primary"],
            "accel": round(accel, 3) if np.isfinite(accel) else None,
            "state": en, "state_zh": zh, "n": int(len(flow))}


def _classify(vel: float | None, accel: float) -> tuple[str, str]:
    """Direction (velocity sign) × momentum-of-direction (acceleration sign)."""
    if vel is None or not np.isfinite(vel):
        return "n/a", "无数据"
    a = accel if np.isfinite(accel) else 0.0
    if vel >= 0.5:
        return ("accelerating in", "加速流入") if a > 0 else ("inflow cooling", "流入降温")
    if vel <= -0.5:
        return ("accelerating out", "加速流出") if a < 0 else ("outflow easing", "流出趋缓")
    return ("balanced", "均衡")


def _spark(vals: list[float], w: int = 120, h: int = 28, pad: int = 2) -> str | None:
    """Inline-SVG polyline points (server-side, no client JS) normalized into a w×h box."""
    xs = [float(v) for v in vals if v is not None and np.isfinite(v)]
    if len(xs) < 3:
        return None
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1.0
    n = len(xs)
    pts = []
    for i, v in enumerate(xs):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)   # higher value = higher on screen
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def _series_tail(s: pd.Series, n: int = 60) -> list[float]:
    return [round(float(v), 1) for v in s.dropna().tail(n)]


# ── 1) aggregate Connect channels ─────────────────────────────────────────────
def _read_connect(name: str) -> pd.DataFrame | None:
    p = config.data_dir() / "china_connect" / f"{name}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        return df.sort_index() if "net" in df.columns else None
    except Exception as e:  # noqa: BLE001
        log.debug("connect %s unreadable (%s)", name, e)
        return None


def _channel(name: str, label: str, label_zh: str) -> dict | None:
    df = _read_connect(name)
    if df is None:
        return None
    net = df["net"].dropna()
    if len(net) < 30:
        return None
    last_valid = net.index.max()
    live = bool(last_valid >= (df.index.max() - pd.Timedelta(days=10)))
    cum20 = net.rolling(20).sum()
    out = {
        "key": name, "label": label, "label_zh": label_zh,
        "live": live, "as_of": str(last_valid.date()),
        "spark": _spark(_series_tail(cum20, 60)),
    }
    if live:
        # only compute live velocity for a current series — a frozen channel's last value
        # is years stale and a velocity chip would read as "now" when it isn't.
        kin = _kinetics(net, _AGG)
        out["flow_1m_b"] = round(float(net.tail(21).sum()) / 1e3, 1)   # ¥millions → ¥B (~1m net)
        out["pos_days_20"] = int((net.tail(20) > 0).sum())
        if kin:
            out.update(vel=kin["vel"], accel=kin["accel"], vel_primary=kin["vel_primary"],
                       primary=kin["primary"], state=kin["state"], state_zh=kin["state_zh"])
    else:
        out["frozen_since"] = NORTHBOUND_FROZEN
        out["note"] = ("Aggregate northbound net disclosure ended 19 Aug 2024 (Stock "
                       "Connect home-market rule) — historical only, no live velocity.")
        out["note_zh"] = "北向资金净额披露于2024年8月19日停止（互联互通本地市场规则）——仅历史，无实时流速。"
    return out


def aggregate_velocity() -> list[dict] | None:
    chans = [_channel("southbound", "Southbound — mainland money into HK", "南向 · 内地资金入港"),
             _channel("northbound", "Northbound — foreign money into A-shares", "北向 · 外资入A股")]
    chans = [c for c in chans if c]
    return chans or None


# ── 2) A-share per-name + 3) sector velocity (weekly grid) ────────────────────
def _flow_panel() -> pd.DataFrame | None:
    """Wide [date × ticker] A-share 主力 net-rate (%) grid from the accrued weekly history."""
    p = config.data_dir() / "tushare" / "flow_hist.parquet"
    if not p.exists():
        return None
    try:
        fh = pd.read_parquet(p)
        fh["date"] = pd.to_datetime(fh["date"].astype(str))
        wide = fh.pivot_table(index="date", columns="ticker", values="flow").sort_index()
        return wide if len(wide) >= _WK["min_obs"] else None
    except Exception as e:  # noqa: BLE001
        log.debug("flow_hist unreadable (%s)", e)
        return None


def _name_map() -> dict[str, str]:
    """ticker → display name. Base = the full-universe moneyflow snapshot (~5.9k names),
    overlaid with the curated baskets name_zh. Best-effort; missing names fall back to the
    ticker in the template."""
    out: dict[str, str] = {}
    try:
        mf = config.data_dir() / "tushare" / "moneyflow.parquet"
        if mf.exists():
            d = pd.read_parquet(mf, columns=["ticker", "name"]).dropna()
            out.update(dict(zip(d["ticker"], d["name"])))
    except Exception as e:  # noqa: BLE001
        log.debug("name map (moneyflow) skipped (%s)", e)
    try:
        from engine.baskets_china import _membership
        mem = _membership() or {}
        for b in (mem.get("baskets") or {}).values():
            for m in b.get("members", []):
                if isinstance(m, dict) and m.get("ticker") and m.get("name_zh"):
                    out[m["ticker"]] = m["name_zh"]
    except Exception as e:  # noqa: BLE001
        log.debug("name map (membership) skipped (%s)", e)
    return out


def ashare_name_velocity(wide: pd.DataFrame | None = None, top: int = 14) -> dict | None:
    if wide is None:
        wide = _flow_panel()
    if wide is None:
        return None
    names = _name_map()
    rows = []
    for tk in wide.columns:
        kin = _kinetics(wide[tk], _WK)
        if not kin or kin["vel_primary"] is None:
            continue
        rate = pd.to_numeric(wide[tk], errors="coerce").dropna()
        rows.append({
            "ticker": tk, "name": names.get(tk),
            "vel": kin["vel_primary"], "accel": kin["accel"],
            "rate_now": round(float(rate.iloc[-1]), 1) if len(rate) else None,
            "rate_4wk": round(float(rate.tail(4).mean()), 1) if len(rate) >= 4 else None,
            "state": kin["state"], "state_zh": kin["state_zh"],
        })
    if len(rows) < 10:
        return None
    df = pd.DataFrame(rows)
    inflow = df.sort_values("vel", ascending=False).head(top).to_dict("records")
    outflow = df.sort_values("vel").head(top).to_dict("records")
    return {"cadence": "weekly", "as_of": str(wide.index.max().date()),
            "n": int(len(df)), "primary": _WK["primary"],
            "note": "主力 net-rate (super-large + large orders); velocity = standardized 4-week inflow rate, acceleration = its trend.",
            "note_zh": "主力净占比（超大单+大单）；流速＝标准化4周流入率，加速度＝其趋势。",
            "inflow": inflow, "outflow": outflow}


def ashare_sector_velocity(wide: pd.DataFrame | None = None) -> dict | None:
    if wide is None:
        wide = _flow_panel()
    if wide is None:
        return None
    try:
        from engine.baskets_china import _membership
        mem = _membership()
    except Exception as e:  # noqa: BLE001
        log.debug("membership unavailable (%s)", e)
        return None
    if not mem or not mem.get("baskets"):
        return None
    rows = []
    for bid, b in mem["baskets"].items():
        members = [m["ticker"] for m in b.get("members", [])
                   if isinstance(m, dict) and m.get("ticker") and not m.get("removed")]
        cols = [t for t in members if t in wide.columns]
        if len(cols) < 3:
            continue
        sect_flow = wide[cols].mean(axis=1)          # equal-weight member net-rate
        kin = _kinetics(sect_flow, _WK)
        if not kin or kin["vel_primary"] is None:
            continue
        rows.append({
            "id": bid, "name": b.get("name"), "name_zh": b.get("name_zh"),
            "category": b.get("category"), "n_members": len(cols),
            "vel": kin["vel_primary"], "accel": kin["accel"],
            "rate_4wk": round(float(sect_flow.tail(4).mean()), 1),
            "state": kin["state"], "state_zh": kin["state_zh"],
            "spark": _spark(_series_tail(sect_flow.cumsum(), 52)),
        })
    if len(rows) < 4:
        return None
    rows.sort(key=lambda r: (r["vel"] is None, -(r["vel"] or 0)))
    return {"cadence": "weekly", "as_of": str(wide.index.max().date()),
            "n": len(rows), "primary": _WK["primary"],
            "note": "Per-sector big-money flow = equal-weight member main-money net-rate, ranked by 4-week velocity.",
            "note_zh": "板块主力资金＝等权成分股主力净占比，按4周流速排序。",
            "rows": rows}


# ── 4) A-share Dragon-Tiger institutional seats (snapshot, not velocity) ───────
def ashare_inst_seats(top: int = 12) -> dict | None:
    """Closest free *institution-level* A-share read: net buys by 机构专用 seats on the
    Dragon-Tiger board over its recent window. A snapshot of where institutional seats
    showed up — anonymous, so context not attribution. Display-only."""
    p = config.data_dir() / "china_lhb" / "detail.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("china_lhb unreadable (%s)", e)
        return None
    need = {"ticker", "name", "inst_net_buy_yi"}
    if not need.issubset(df.columns):
        return None
    d = df.copy()
    d["inst_net_buy_yi"] = pd.to_numeric(d["inst_net_buy_yi"], errors="coerce")
    d = d[d["inst_net_buy_yi"].abs() > 0].dropna(subset=["inst_net_buy_yi"])
    if len(d) < 4:
        return None

    def rows(frame):
        out = []
        for _, r in frame.iterrows():
            out.append({"ticker": r["ticker"], "name": r.get("name"),
                        "inst_net_yi": round(float(r["inst_net_buy_yi"]), 2),
                        "n_buy": int(r.get("n_inst_buy") or 0),
                        "n_sell": int(r.get("n_inst_sell") or 0)})
        return out
    buy = d.sort_values("inst_net_buy_yi", ascending=False).head(top)
    sell = d.sort_values("inst_net_buy_yi").head(top)
    asof = str(d["asof"].iloc[0]) if "asof" in d.columns and len(d) else None
    return {"as_of": asof, "n": int(len(d)),
            "note": "Dragon-Tiger (龙虎榜) 机构专用 institutional-seat net buys over the recent abnormal-volume window — anonymous seats, context not attribution.",
            "note_zh": "龙虎榜机构专用席位近期净买入（异动窗口）——匿名席位，仅作背景参考。",
            "buying": rows(buy), "selling": rows(sell)}


# ── 5) HK southbound per-name (accruing → velocity when deep enough) ──────────
def hk_name_flow() -> dict | None:
    """Mainland's per-name southbound positioning. The daily holdings history is still
    shallow, so we show the accumulation board now and compute net-share-flow VELOCITY
    once the accrued history clears a depth floor."""
    try:
        from engine import hk_southbound_stocks as hk
    except Exception as e:  # noqa: BLE001
        log.debug("hk_southbound import failed (%s)", e)
        return None
    ms = None
    try:
        ms = hk.market_summary()
    except Exception as e:  # noqa: BLE001
        log.debug("hk market_summary failed (%s)", e)
    if not ms:
        return None
    # depth of the accrued daily history (for the velocity-readiness note)
    depth, vel_ready = 0, False
    try:
        p = config.data_dir() / "hk_southbound" / "holdings.parquet"
        if p.exists():
            hist = pd.read_parquet(p, columns=["hold_shares"])
            depth = int(hist.index.get_level_values("date").nunique()) \
                if isinstance(hist.index, pd.MultiIndex) else 0
    except Exception:  # noqa: BLE001
        depth = 0
    vel_ready = depth >= 8
    ms["depth"] = depth
    ms["vel_ready"] = vel_ready
    ms["basis"] = ("net-share flow velocity" if vel_ready
                   else "5-day holding-value change (velocity accrues as history deepens)")
    ms["basis_zh"] = ("净持股流速" if vel_ready else "5日持仓市值变化（流速随历史积累解锁）")
    return ms


# ── public snapshot ───────────────────────────────────────────────────────────
def snapshot() -> dict | None:
    """Assemble the whole flow-velocity desk. Each panel is independently None-safe; the
    desk renders as long as ANY panel resolves."""
    wide = _flow_panel()
    panels = {
        "aggregate": aggregate_velocity(),
        "ashare_names": ashare_name_velocity(wide),
        "ashare_sectors": ashare_sector_velocity(wide),
        "ashare_seats": ashare_inst_seats(),
        "hk_names": hk_name_flow(),
    }
    if not any(panels.values()):
        return None
    asof = None
    for k in ("ashare_names", "ashare_sectors"):
        if panels.get(k):
            asof = panels[k].get("as_of")
            break
    if asof is None and panels.get("aggregate"):
        asof = panels["aggregate"][0].get("as_of")
    panels["as_of"] = asof
    panels["note"] = ("Display-only positioning lens — flow is never scored into an "
                      "allocation signal. Velocity = standardized net-flow rate; "
                      "acceleration = its 2nd derivative.")
    return panels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    snap = snapshot()
    if not snap:
        print("flow_velocity.snapshot(): None (no source parquets)")
    else:
        print("as_of:", snap.get("as_of"))
        for c in snap.get("aggregate") or []:
            print(f"  {c['label']:<42} live={c['live']} vel={c.get('vel')} state={c.get('state')}")
        nm = snap.get("ashare_names")
        if nm:
            print(f"  A-share names: {nm['n']} ranked; top inflow:")
            for r in nm["inflow"][:5]:
                print(f"    {r['ticker']:>10} {str(r.get('name')):<8} vel={r['vel']} accel={r['accel']} ({r['state']})")
        sec = snap.get("ashare_sectors")
        if sec:
            print(f"  sectors: {sec['n']} ranked; top:")
            for r in sec["rows"][:5]:
                print(f"    {str(r['name']):<22} vel={r['vel']} accel={r['accel']} ({r['state']})")
        seats = snap.get("ashare_seats")
        if seats:
            print(f"  inst seats: {seats['n']} names; top buy {seats['buying'][0]['ticker']} {seats['buying'][0]['inst_net_yi']}亿")
        hk = snap.get("hk_names")
        if hk:
            print(f"  HK southbound: depth={hk.get('depth')} ready={hk.get('vel_ready')} n_sized={hk.get('n_sized')}")
