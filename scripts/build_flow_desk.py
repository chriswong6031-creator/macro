"""scripts/build_flow_desk.py — P3.1 Group Flow Heatmap & Market Tide page builder.

Reads:
  data/options_flow/summary_<KEY>.parquet  — 1 row/day per name (premium_mn, net_premium_mn,
                                             zerodte_share; history accrues daily)
  site/flow/index.json                     — freshest flow manifest (353 names, today's read)
  data/baskets/membership.json             — sector & theme group membership
  data/tape_flow/daily/<ROOT>.parquet      — signed columns if present (auto-upgrade as
                                             accrual grows; absent-safe)
  data/flows/etf_flow_proxy.parquet        — sector-ETF creation/redemption proxy

Writes:
  site/flow_desk.json      — data payload (Market Tide + cohorts + sector heatmap + top movers + ETF)
  site/flow_desk.html      — page (rendered from templates/flow_desk.html.j2)
  site/flowdata/cohorts.json — cohort-level snapshot + 10-session sparklines (FL-B)

Display-tier only — never feeds any score or rank path.
Coverage + lag labels are emitted in the JSON and rendered in the HTML.

Kill-switch:
  Config flag  flow_desk.enabled  (default: true when absent).
  If false → writes a noindex stub (site/flow_desk.html) and skips the JSON.

Run:  .venv/bin/python -m scripts.build_flow_desk
"""
from __future__ import annotations

import glob
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Allow running standalone
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader
from lib import config
from engine.flow_cohorts import build_cohorts

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────
MIN_Z_HISTORY = 20        # minimum obs for z-score; below → show raw premium
SECTOR_ETF_MAP: dict[str, str] = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLI": "Industrials", "XLU": "Utilities", "XLV": "Health Care",
    "XLY": "Consumer Disc.", "XLP": "Staples", "XLB": "Materials",
    "XLC": "Communication", "XLRE": "Real Estate",
}
# Baskets where category = "US Sectors (EW)" contain GICS members
SECTOR_BASKET_MAP: dict[str, str] = {
    "us_sector_tech": "Technology", "us_sector_financials": "Financials",
    "us_sector_health": "Health Care", "us_sector_discretionary": "Consumer Disc.",
    "us_sector_comm": "Communication", "us_sector_industrials": "Industrials",
    "us_sector_staples": "Staples", "us_sector_energy": "Energy",
    "us_sector_utilities": "Utilities", "us_sector_realestate": "Real Estate",
    "us_sector_materials": "Materials",
}
TOP_MOVERS_N = 15          # size of Top Net Impact board
ETF_LABEL = "proxy (creation/redemption)"


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_flow_index(site_dir: Path) -> list[dict]:
    """Load site/flow/index.json rows (today's live flow manifest)."""
    p = site_dir / "flow" / "index.json"
    if not p.exists():
        log.warning("flow_desk: site/flow/index.json absent — no flow data")
        return []
    d = json.loads(p.read_text())
    return d.get("rows", [])


def _load_membership(data_dir: Path) -> dict[str, str]:
    """Return {ticker: gics_sector} from the us_sector_* baskets."""
    p = data_dir / "baskets" / "membership.json"
    if not p.exists():
        log.warning("flow_desk: membership.json absent")
        return {}
    mb = json.loads(p.read_text())
    baskets = mb.get("baskets", {})
    gics: dict[str, str] = {}
    for basket_key, sector_label in SECTOR_BASKET_MAP.items():
        basket = baskets.get(basket_key, {})
        for m in basket.get("members", []):
            if m.get("removed") is None:
                gics[m["ticker"]] = sector_label
    # ETF anchors map directly
    for etf, label in SECTOR_ETF_MAP.items():
        gics[etf] = label
    # Index ETFs go to a special group
    for idx_etf in ("SPY", "QQQ", "IWM", "DIA"):
        gics.setdefault(idx_etf, "Index ETFs")
    return gics


def _load_theme_groups(data_dir: Path) -> dict[str, list[str]]:
    """Return {theme_name: [tickers]} for non-sector baskets."""
    p = data_dir / "baskets" / "membership.json"
    if not p.exists():
        return {}
    mb = json.loads(p.read_text())
    baskets = mb.get("baskets", {})
    groups: dict[str, list[str]] = {}
    sector_keys = set(SECTOR_BASKET_MAP.keys())
    for basket_key, basket in baskets.items():
        if basket_key in sector_keys:
            continue
        name = basket.get("name", basket_key)
        members = [m["ticker"] for m in basket.get("members", []) if m.get("removed") is None]
        if members:
            groups[name] = members
    return groups


def _load_summary_history(data_dir: Path, ticker: str) -> pd.DataFrame | None:
    """Load data/options_flow/summary_<TICKER>.parquet (1 row/day history)."""
    p = data_dir / "options_flow" / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df = df.sort_index()
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("flow_desk: summary %s read error: %s", ticker, e)
        return None


def _load_tape_flow(data_dir: Path, ticker: str) -> pd.Series | None:
    """Load tape_flow daily row for a ticker (absent-safe). Returns latest row or None."""
    p = data_dir / "tape_flow" / "daily" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p).sort_index()
        if df.empty:
            return None
        return df.iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.debug("flow_desk: tape_flow %s read error: %s", ticker, e)
        return None


def _z_score(series: pd.Series, value: float, min_obs: int = MIN_Z_HISTORY) -> float | None:
    """Compute z-score of value against series. None if insufficient history."""
    clean = series.dropna()
    if len(clean) < min_obs:
        return None
    mu = float(clean.mean())
    sigma = float(clean.std(ddof=1))
    if sigma < 1e-9:
        return None
    return round((value - mu) / sigma, 2)


def _soft_tone(net_prem_mn: float | None) -> str:
    """Return tone chip label for soft net premium direction."""
    if net_prem_mn is None:
        return "neutral"
    if net_prem_mn > 50:
        return "pos~"
    if net_prem_mn < -50:
        return "neg~"
    return "neutral"


# ── section builders ───────────────────────────────────────────────────────────

def build_market_tide(flow_rows: list[dict], data_dir: Path) -> dict:
    """Section 1: whole-market gross premium + soft net tone + 0DTE share, sparkline."""
    # Aggregate across all names in today's flow manifest
    gross_pm = 0.0
    net_pm = 0.0
    zerodte_weights: list[tuple[float, float]] = []   # (weight=gross_pm, z_share)
    n_covered = 0
    asof_date: str | None = None

    for row in flow_rows:
        key = row.get("key", "")
        # Gross premium_mn is only in per-name files; net_premium_mn is in index
        net = row.get("net_premium_mn")
        z_share = row.get("zerodte_share")
        asof = row.get("asof")
        if asof and (asof_date is None or asof > asof_date):
            asof_date = asof

        # Load per-name file to get gross
        per_file = config.ROOT / config.load()["storage"]["site_dir"] / "flow" / f"{key}.json"
        gross = None
        if per_file.exists():
            try:
                pd_ = json.loads(per_file.read_text())
                gross = pd_.get("premium_mn")
            except Exception:  # noqa: BLE001
                pass

        if gross is not None:
            gross_pm += gross
        if net is not None:
            net_pm += net
        if z_share is not None and gross is not None and gross > 0:
            zerodte_weights.append((gross, z_share))
        n_covered += 1

    # Weighted 0DTE share
    if zerodte_weights:
        total_w = sum(w for w, _ in zerodte_weights)
        zerodte_share_wt = sum(w * z for w, z in zerodte_weights) / total_w if total_w > 0 else None
    else:
        zerodte_share_wt = None

    # Build sparkline from per-ticker summary histories summed across index ETFs (SPY/QQQ/IWM/DIA)
    spark_etfs = ["SPY", "QQQ", "IWM", "DIA"]
    spark_data: list[dict] = []
    for etf in spark_etfs:
        hist = _load_summary_history(data_dir, etf)
        if hist is not None and not hist.empty:
            for idx, hist_row in hist.iterrows():
                d_str = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
                spark_data.append({
                    "date": d_str,
                    "premium_mn": float(hist_row["premium_mn"]) if not pd.isna(hist_row.get("premium_mn", float("nan"))) else None,
                    "net_premium_mn": float(hist_row["net_premium_mn"]) if not pd.isna(hist_row.get("net_premium_mn", float("nan"))) else None,
                })
    # Group by date (aggregate across spark_etfs)
    spark_by_date: dict[str, dict] = {}
    for item in spark_data:
        d = item["date"]
        if d not in spark_by_date:
            spark_by_date[d] = {"premium_mn": 0.0, "net_premium_mn": 0.0}
        if item["premium_mn"] is not None:
            spark_by_date[d]["premium_mn"] += item["premium_mn"]
        if item["net_premium_mn"] is not None:
            spark_by_date[d]["net_premium_mn"] += item["net_premium_mn"]

    spark = sorted(
        [{"date": d, **v} for d, v in spark_by_date.items()],
        key=lambda x: x["date"]
    )[-30:]  # last 30 sessions

    return {
        "gross_premium_mn": round(gross_pm, 1) if gross_pm else None,
        "net_premium_mn": round(net_pm, 1) if net_pm else None,
        "zerodte_share": round(zerodte_share_wt, 3) if zerodte_share_wt is not None else None,
        "tone": _soft_tone(net_pm),
        "n_names": n_covered,
        "asof": asof_date,
        "spark": spark,
        "coverage_note": f"{n_covered} names · EOD · direction approx",
        "lag_note": "EOD; built after market close",
    }


def build_sector_heatmap(flow_rows: list[dict], gics_map: dict[str, str],
                          data_dir: Path) -> list[dict]:
    """Section 2: sector heatmap — premium z vs own history, ~-soft tone chips."""
    # Bucket flow rows into sectors
    sectors: dict[str, list[dict]] = {}
    for row in flow_rows:
        key = row.get("key", "")
        sector = gics_map.get(key)
        if sector is None:
            continue
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append(row)

    heatmap: list[dict] = []
    for sector_name in sorted(sectors.keys()):
        rows = sectors[sector_name]
        # Aggregate premium
        total_gross = 0.0
        total_net = 0.0
        n = 0
        asof_latest: str | None = None
        tape_breadth_vals: list[float] = []
        zerodte_w: list[tuple[float, float]] = []
        history_gross: list[float] = []

        # Gather per-ticker history for z-score
        per_ticker_hist: list[pd.Series] = []
        for row in rows:
            key = row.get("key", "")
            net = row.get("net_premium_mn", 0.0) or 0.0
            asof = row.get("asof")
            if asof and (asof_latest is None or asof > asof_latest):
                asof_latest = asof

            # Gross from per-name file
            per_file = config.ROOT / config.load()["storage"]["site_dir"] / "flow" / f"{key}.json"
            gross = 0.0
            z_share = row.get("zerodte_share")
            if per_file.exists():
                try:
                    pd_ = json.loads(per_file.read_text())
                    gross = pd_.get("premium_mn") or 0.0
                except Exception:  # noqa: BLE001
                    pass

            total_gross += gross
            total_net += net
            if z_share is not None and gross > 0:
                zerodte_w.append((gross, z_share))
            n += 1

            # tape_flow breadth (net_signed_premium_z252 present → above zero = net buying)
            tape = _load_tape_flow(data_dir, key)
            if tape is not None and "net_signed_premium" in tape.index:
                val = tape.get("net_signed_premium")
                if val is not None and not pd.isna(val):
                    tape_breadth_vals.append(1.0 if float(val) > 0 else 0.0)

            # History for z-score computation
            hist = _load_summary_history(data_dir, key)
            if hist is not None and "premium_mn" in hist.columns:
                per_ticker_hist.append(hist["premium_mn"])

        # Build sector-level history by summing aligned dates
        if per_ticker_hist:
            combined = pd.concat(per_ticker_hist, axis=1)
            sector_hist = combined.sum(axis=1, min_count=1)
        else:
            sector_hist = pd.Series(dtype=float)

        # Z-score with min-history gate
        z_score = _z_score(sector_hist, total_gross) if total_gross else None
        obs = int(sector_hist.dropna().__len__())

        # Weighted 0DTE share
        if zerodte_w:
            total_w = sum(w for w, _ in zerodte_w)
            sec_zerodte = sum(w * z for w, z in zerodte_w) / total_w if total_w > 0 else None
        else:
            sec_zerodte = None

        # Tape breadth
        tape_breadth = round(float(np.mean(tape_breadth_vals)), 2) if tape_breadth_vals else None
        tape_n = len(tape_breadth_vals)

        heatmap.append({
            "sector": sector_name,
            "gross_premium_mn": round(total_gross, 1) if total_gross else None,
            "net_premium_mn": round(total_net, 1) if total_net else None,
            "tone": _soft_tone(total_net),
            "premium_z": z_score,           # None → show raw (min-history gate)
            "z_obs": obs,
            "z_raw_fallback": obs < MIN_Z_HISTORY,
            "tape_breadth": tape_breadth,   # fraction of names with positive tape flow
            "tape_n": tape_n,
            "zerodte_share": round(sec_zerodte, 3) if sec_zerodte is not None else None,
            "n_names": n,
            "asof": asof_latest,
        })

    # Sort by gross_premium descending
    heatmap.sort(key=lambda x: x.get("gross_premium_mn") or 0, reverse=True)
    return heatmap


def _load_leaders_recurrence(site_dir: Path) -> dict[str, dict]:
    """Load recurrence_count, zerodte_dominated, signing_source from leaders.json.

    Absent-safe: returns {} when the artifact does not yet exist.
    Used by build_top_movers to add FL-R10b additive badges.
    """
    p = site_dir / "flowleaders" / "leaders.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        rows = d.get("board_a") or []
        return {
            r["ticker"]: {
                "recurrence_count": r.get("recurrence_count"),
                "zerodte_dominated": r.get("zerodte_dominated", False),
                "signing_source": r.get("signing_source"),
            }
            for r in rows
            if r.get("ticker")
        }
    except Exception as e:  # noqa: BLE001
        log.debug("flow_desk: leaders.json load failed: %s", e)
        return {}


def build_top_movers(flow_rows: list[dict], n: int = TOP_MOVERS_N,
                     site_dir: Path | None = None) -> list[dict]:
    """Section 3: Top Net Impact board — largest |net premium| names (soft-labeled).

    Additive FL-R10b fields per row:
      recurrence_count   int | None   — trailing-10 recurrence from leaders.json
      zerodte_dominated  bool          — 0DTE chip flag
      signing_source     str           — 'tape' | 'minute_tick'
    Schema flow_desk.v1 is preserved (additive only; sort unchanged).
    """
    recur_map = _load_leaders_recurrence(site_dir) if site_dir is not None else {}

    candidates = []
    for row in flow_rows:
        net = row.get("net_premium_mn")
        if net is None:
            continue
        ticker = row.get("key")
        recur_info = recur_map.get(ticker) or {}
        candidates.append({
            "ticker": ticker,
            "asof": row.get("asof"),
            "net_premium_mn": round(float(net), 1),
            "tone": row.get("tone") or _soft_tone(float(net)),
            "zerodte_share": row.get("zerodte_share"),
            "verdict": row.get("verdict"),
            # FL-R10b additive fields
            "recurrence_count": recur_info.get("recurrence_count"),
            "zerodte_dominated": bool(recur_info.get("zerodte_dominated", False)),
            "signing_source": recur_info.get("signing_source", "minute_tick"),
        })
    candidates.sort(key=lambda x: abs(x["net_premium_mn"]), reverse=True)
    return candidates[:n]


def build_etf_tile(data_dir: Path) -> dict | None:
    """Section 4: ETF flows tile — proxy-labeled creation/redemption flows."""
    try:
        from engine.etf_flows import proxy_json
        payload = proxy_json()
        if payload is None:
            log.info("flow_desk: ETF flow proxy unavailable (store absent)")
            return None
        payload["proxy_label"] = ETF_LABEL
        payload["coverage_note"] = "11 Sector SPDRs · delta(SO)×NAV proxy · SSGA fundfinder · EOD"
        return payload
    except Exception as e:  # noqa: BLE001
        log.warning("flow_desk: ETF tile error: %s", e)
        return None


# ── kill-switch & stub ─────────────────────────────────────────────────────────

def _write_noindex_stub(site_dir: Path) -> None:
    stub = """<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="robots" content="noindex">
<title>Flow Desk (disabled)</title></head>
<body><p>Flow Desk is currently disabled.</p></body></html>"""
    (site_dir / "flow_desk.html").write_text(stub)
    log.info("flow_desk: kill-switch active — wrote noindex stub")


# ── main build ─────────────────────────────────────────────────────────────────

def build() -> dict:
    """Build the flow desk data payload. Returns the payload dict."""
    cfg = config.load()
    flow_cfg = (cfg.get("flow_desk") or {})
    if not flow_cfg.get("enabled", True):
        site_dir = config.ROOT / cfg["storage"]["site_dir"]
        _write_noindex_stub(site_dir)
        return {}

    data_dir = config.data_dir()
    site_dir = config.ROOT / cfg["storage"]["site_dir"]
    site_dir.mkdir(parents=True, exist_ok=True)

    flow_rows = _load_flow_index(site_dir)
    if not flow_rows:
        log.warning("flow_desk: no flow rows — writing empty stub")
        return {}

    gics_map = _load_membership(data_dir)

    log.info("flow_desk: building with %d flow rows, %d gics mappings",
             len(flow_rows), len(gics_map))

    market_tide = build_market_tide(flow_rows, data_dir)
    sector_heatmap = build_sector_heatmap(flow_rows, gics_map, data_dir)
    top_movers = build_top_movers(flow_rows, site_dir=site_dir)
    etf_tile = build_etf_tile(data_dir)

    # FL-B: cohort-level aggregation (Mag7 / Memory / AI chips / Software)
    site_flowdata_dir = site_dir / "flowdata"
    try:
        cohorts = build_cohorts(data_dir, site_flowdata_dir=site_flowdata_dir)
        log.info("flow_desk: cohorts built — %d cohorts", len(cohorts))
    except Exception as e:  # noqa: BLE001
        log.warning("flow_desk: cohort build failed (non-fatal): %s", e)
        cohorts = []

    payload = {
        "schema": "flow_desk.v1",
        "built": str(date.today()),
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "asof": market_tide.get("asof"),
        "direction_reliable": False,
        "magnitude_reliable": True,
        "direction_note": "net premium direction is SOFT — approximate (minute tick-rule signing)",
        "cohorts": cohorts,
        "market_tide": market_tide,
        "sector_heatmap": sector_heatmap,
        "top_movers": top_movers,
        "etf_tile": etf_tile,
    }

    out_path = site_dir / "flow_desk.json"
    out_path.write_text(json.dumps(payload, separators=(",", ":"), default=float))
    log.info("flow_desk: wrote %s (%d bytes)", out_path, out_path.stat().st_size)

    # Render HTML
    _render_html(payload, site_dir)

    return payload


def _render_html(payload: dict, site_dir: Path) -> None:
    """Render flow_desk.html from template."""
    tpl_dir = config.ROOT / "templates"
    env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
    try:
        tpl = env.get_template("flow_desk.html.j2")
    except Exception as e:  # noqa: BLE001
        log.error("flow_desk: template not found: %s", e)
        return
    rendered = tpl.render(flow_desk=payload)
    out = site_dir / "flow_desk.html"
    out.write_text(rendered)
    log.info("flow_desk: rendered %s (%d bytes)", out, out.stat().st_size)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    payload = build()
    if payload:
        log.info("flow_desk: done. asof=%s, sectors=%d, top_movers=%d",
                 payload.get("asof"),
                 len(payload.get("sector_heatmap", [])),
                 len(payload.get("top_movers", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
