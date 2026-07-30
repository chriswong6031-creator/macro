"""scripts/build_flow_desk.py — P3.1 Group Flow Heatmap & Market Tide page builder.

Reads:
  data/options_flow/summary_<KEY>.parquet  — 1 row/day per name (premium_mn, net_premium_mn,
                                             zerodte_share; history accrues daily)
  site/flow/index.json                     — freshest flow manifest (353 names, today's read)
  data/baskets/membership.json             — sector & theme group membership
  data/tape_flow/daily/<ROOT>.parquet      — signed columns if present (auto-upgrade as
                                             accrual grows; absent-safe)
  data/flows/etf_flow_proxy.parquet        — sector-ETF creation/redemption proxy
  data/flows/<T>.parquet                   — per-ticker SO snapshots (written by BroadFlowAdapter)

Writes (additions for RLT-R3):
  data/flows/broad_flow_proxy.parquet      — broad-index ETF proxy (SPY/QQQ/IWM/RSP/DIA);
                                             rebuilt here via rebuild_broad()
                                             (COLLECT_LANE=nightly-gated, HOUSE-U5)
  data/flows/etf_flow_proxy.parquet        — sector-ETF proxy (11 SPDRs); rebuilt here via
                                             rebuild() under the same gate — this builder is
                                             P1.7's missing writer call site
  data/options_flow/cohorts_<key>.parquet  — cohort accrual via engine.flow_cohorts.
                                             build_cohorts (COLLECT_LANE=nightly-gated,
                                             HOUSE-U5)

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
from lib import config, options_coverage
from lib.pages import write_page  # noqa: E402
from engine.flow_cohorts import build_cohorts
from engine.ledger_lane import nightly_advance_enabled

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
        # OIP R8 — the shared options coverage object, ADDITIVE. This desk published its
        # coverage as a STRING only, so no machine could read it and no surface could put
        # it beside the workspace's or the board's. `coverage_note` is untouched; this is
        # the same fact in the family's one comparable shape (lib/options_coverage.py),
        # persisted into site/flow_desk.json. Surfaces adopt it in a later OIP wave.
        "coverage_v1": options_coverage.coverage_object(
            universe_name_en="Names with options tape",
            universe_name_zh="有期权成交数据的标的",
            # M8 (review): passing n_covered as BOTH sides published a fabricated
            # "100%" — the desk does not know its own denominator (options_flow only
            # has files for names that traded), and lib/options_coverage's contract is
            # that an unknown universe is None so coverage_pct comes back None.
            universe_n=None,
            covered_n=n_covered,
            asof=asof_date,
            sources=[
                options_coverage.source(
                    "options_flow", "Options tape", "期权成交",
                    asof=asof_date, n=n_covered,
                ),
            ],
        ),
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


def _rebuild_broad_proxy() -> None:
    """RLT-R3: rebuild broad_flow_proxy.parquet (SPY/QQQ/IWM/RSP/DIA).

    Called from build() each nightly run so broad_flow_proxy.parquet is
    produced by the existing build_flow_desk step without adding a new DAG
    node.  That call site is gated on COLLECT_LANE=nightly (HOUSE-U5), so
    express/intraday lanes never reach this function.  Non-fatal: a missing
    per-ticker parquet simply means that ticker is skipped this run and
    accrues on the next collection cycle.
    """
    try:
        from engine.etf_flows import rebuild_broad
        path = rebuild_broad()
        if path is not None:
            log.info("flow_desk: broad ETF proxy rebuilt -> %s", path)
        else:
            log.info("flow_desk: broad ETF proxy skipped (no SO data yet)")
    except Exception as e:  # noqa: BLE001
        log.warning("flow_desk: broad ETF proxy rebuild failed (non-fatal): %s", e)


def _rebuild_sector_proxy() -> None:
    """Rebuild etf_flow_proxy.parquet (11 sector SPDRs) each nightly run.

    P1.7 shipped engine.etf_flows.rebuild() and the reader (proxy_json →
    build_etf_tile) but never wired the writer into any builder, so the store
    froze at its seed commit while the per-ticker inputs kept advancing.  This
    is the missing production call site — same placement and non-fatal
    contract as _rebuild_broad_proxy(), and it must run before
    build_etf_tile() so the tile reads today's rows.  That call site is gated
    on COLLECT_LANE=nightly (HOUSE-U5), so express/intraday lanes never reach
    this function.
    """
    try:
        from engine.etf_flows import rebuild
        path = rebuild()
        if path is not None:
            log.info("flow_desk: sector ETF proxy rebuilt -> %s", path)
        else:
            log.info("flow_desk: sector ETF proxy skipped (no SO data yet)")
    except Exception as e:  # noqa: BLE001
        log.warning("flow_desk: sector ETF proxy rebuild failed (non-fatal): %s", e)


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


# ── flow score glance panel (FS-4 Lane C) ──────────────────────────────────────

def build_flow_score_panel(data_dir: Path) -> dict | None:
    """Build the flow-score glance panel from gate.json.

    Returns None when gate.json is absent (panel omitted from payload entirely).
    All fields are derived defensively — the scoring block may be absent (Lane B
    adds it later); never raises.

    Copy laws (DESIGN_DOCTRINE + amendment §2.3 / §9):
    - Glance tier: plain words, unsigned outcome only — no directional/bullish/bearish wording.
    - Banned at glance tier: ECE, isotonic, AUC, cohort, era, calibration, S-FLOWML,
      model names, competitor names (MomoEdge debrand law), untranslated stats.
    - "validated" never in affirmative copy (CI-enforced).
    - PRE-GATE LAW (FS-R3): score is display-only — must not feed any ranker/sizer/gate.
    - ZH copy written only via Write/Edit tools (not bash heredoc — mojibake law).
    """
    try:
        gate_path = data_dir / "flow_signals" / "gate.json"
        if not gate_path.exists():
            log.info("flow_score panel: gate.json absent — panel omitted")
            return None
        gate = json.loads(gate_path.read_text())
        ledger_block = gate.get("ledger") or {}
        n_total = int(ledger_block.get("n_rows") or 0)
        n_sessions = int(ledger_block.get("n_sessions") or 0)
        last_ts = ledger_block.get("last_ts")
        n_by_dte = ledger_block.get("n_by_dte_bucket") or {}
        asof = gate.get("asof") or ""

        # Derive since date: earliest session from events_per_day keys if present,
        # else fall back to asof (both acceptable for the display copy).
        events_per_day = ledger_block.get("events_per_day") or {}
        since_date = min(events_per_day.keys()) if events_per_day else asof

        # ── scoring block — defensive: may be absent (Lane B writes it) ────────────
        scoring = gate.get("scoring") or {}          # .get() everywhere; never crash on missing
        is_scored = bool(scoring.get("enabled"))
        n_scored_total = scoring.get("n_scored_total")
        n_scored_this_run = scoring.get("n_scored_this_run")
        by_status = scoring.get("by_status") or {}
        cal_by_bucket = scoring.get("calibration") or {}

        # Per-DTE-bucket event counts (for Tier-2 hover receipt)
        # Bilingual bucket labels (FS4-C1 fix): emit en/zh twins so the CSS-driven
        # bilingual idiom works (html[data-lang=zh] .l-en{display:none}).
        _BUCKET_LABEL: dict[str, tuple[str, str]] = {
            "0d":    ("Same-day (0DTE)", "当日到期 (0DTE)"),
            "1_7d":  ("1–7 days", "1–7天"),
            "8_30d": ("8–30 days", "8–30天"),
            "31_90d": ("31–90 days", "31–90天"),
        }
        # Sort by numeric DTE order, not lexicographic string order
        _BUCKET_ORDER = {"0d": 0, "1_7d": 1, "8_30d": 2, "31_90d": 3}
        bucket_receipt: list[dict] = [
            {
                "bucket_en": _BUCKET_LABEL.get(k, (k, k))[0],
                "bucket_zh": _BUCKET_LABEL.get(k, (k, k))[1],
                "n": int(v),
            }
            for k, v in sorted(
                n_by_dte.items(),
                key=lambda x: _BUCKET_ORDER.get(x[0], 99),
            )
            if v
        ]

        # ── glance copy: building-history (today's state) ───────────────────────────
        # If scoring block present and has scored events, use scored copy; else building-history.
        # Amendment §2.3: outcome is UNSIGNED — copy must not assert directional thesis.
        if is_scored and n_scored_total:
            # Future branch — defended now but will only show once Lane B runs
            status = "scored"
        else:
            status = "building_history"

        panel: dict[str, Any] = {
            "schema": "flow_score.panel/v1",
            "status": status,
            "n_events_total": n_total,
            "n_sessions": n_sessions,
            "since": since_date,
            "asof": asof,
            "last_ts": last_ts,
            "bucket_receipt": bucket_receipt,
            # Scoring fields — all defensive; only populated when Lane B has run
            "n_scored_total": n_scored_total,
            "n_scored_this_run": n_scored_this_run,
            "by_status": by_status,
            "calibration_by_bucket": cal_by_bucket,
        }
        log.info("flow_score panel: status=%s, n_events=%d, n_sessions=%d",
                 status, n_total, n_sessions)
        return panel
    except Exception as e:  # noqa: BLE001 — additive; never fatal
        log.warning("flow_score panel build failed (non-fatal): %s", e)
        return None


# ── daily flow read (hero scorecard) ────────────────────────────────────────────

# Intensity gauge bands (0-100 score). The score is a SOLID magnitude read:
# gross-premium-weighted mean of per-sector premium z-scores, mapped z→score by
# score = 50 + z*25 (z 0 → 50 average, z +2 → 100 heavy, z -2 → 0 dead-quiet).
_INTENSITY_BANDS = [(72, "heavy"), (58, "busy"), (40, "average"), (25, "light"), (0, "quiet")]


def _intensity_band(score: float | None) -> str:
    if score is None:
        return "building"
    for lo, key in _INTENSITY_BANDS:
        if score >= lo:
            return key
    return "quiet"


def build_flow_read(market_tide: dict, sector_heatmap: list[dict],
                    cohorts: list[dict]) -> dict:
    """Section 0: the day's one-glance read of the whole options tape.

    Display-tier only — never feeds a rank/size/gate (same law as every other
    section here). Two honest dimensions:

    * INTENSITY (solid): how much options money changed hands vs the tape's own
      recent norm — the gross-premium-weighted mean of per-sector premium
      z-scores, mapped to a 0-100 gauge score. Magnitude is reliable, so this is
      the headline gauge. Falls back to a "building history" state when no sector
      has ≥MIN_Z_HISTORY observations.
    * LEAN (semi-solid → soft): buying vs selling pressure. Primary read is the
      gross-weighted tape-flow breadth (fraction of names with positive signed
      premium, from ThetaData tape where present — more reliable than net
      premium); net premium is the soft cross-check and is always labelled ~.

    The stance is deliberately capped at "watch — don't chase" / "stand aside":
    direction here is approximate and the desk never issues a buy, so the honest
    ceiling is a heads-up, never "act". Plain-word copy + receipts are rendered
    in the template (enum keys + numbers only cross the Python boundary).
    """
    gross = market_tide.get("gross_premium_mn")
    net = market_tide.get("net_premium_mn")
    zerodte = market_tide.get("zerodte_share")
    n_names = market_tide.get("n_names")
    asof = market_tide.get("asof")

    # ── INTENSITY: gross-weighted mean sector premium z (solid magnitude) ──────
    zw = [(c.get("gross_premium_mn") or 0.0, c["premium_z"])
          for c in sector_heatmap
          if c.get("premium_z") is not None and (c.get("gross_premium_mn") or 0) > 0]
    if zw:
        tot_w = sum(w for w, _ in zw)
        mean_z = sum(w * z for w, z in zw) / tot_w if tot_w > 0 else 0.0
        intensity_score = int(round(max(0.0, min(100.0, 50.0 + mean_z * 25.0))))
        intensity_raw = False
    else:
        mean_z = None
        intensity_score = None
        intensity_raw = True
    intensity_key = _intensity_band(intensity_score)

    # ── LEAN: gross-weighted tape breadth (semi-solid), net premium soft ───────
    bw = [(c.get("gross_premium_mn") or 0.0, c["tape_breadth"])
          for c in sector_heatmap
          if c.get("tape_breadth") is not None and (c.get("gross_premium_mn") or 0) > 0]
    if bw:
        tot_bw = sum(w for w, _ in bw)
        breadth = sum(w * b for w, b in bw) / tot_bw if tot_bw > 0 else None
    else:
        breadth = None
    if breadth is not None:
        breadth_pct = int(round(breadth * 100))
        if breadth >= 0.58:
            lean_key = "buyers"
        elif breadth <= 0.42:
            lean_key = "sellers"
        else:
            lean_key = "balanced"
    else:
        breadth_pct = None
        # No tape breadth → fall back to the SOFT net-premium sign only
        lean_key = "buyers" if (net or 0) > 0 else ("sellers" if (net or 0) < 0 else "balanced")

    # ── DAY-OVER-DAY: gross vs prior session (index-ETF tape proxy spark) ──────
    spark = market_tide.get("spark") or []
    gross_hist = [s.get("premium_mn") for s in spark if s.get("premium_mn") is not None]
    dod_pct = None
    dod_key = None
    if len(gross_hist) >= 2 and gross_hist[-2]:
        dod_pct = round((gross_hist[-1] / gross_hist[-2] - 1.0) * 100.0, 0)
        dod_key = "heavier" if dod_pct > 15 else ("lighter" if dod_pct < -15 else "steady")

    # ── STANCE: honest ceiling — watch / stand-aside only (soft direction) ─────
    if intensity_key in ("quiet", "light") and lean_key == "balanced":
        stance_key = "stand_aside"
    else:
        stance_key = "watch"

    # ── CALLOUTS: up to 2 notable, honest divergences (optional) ───────────────
    callouts: list[dict] = []
    # (a) a cohort hedged against the tape (put-tilted while market leans to buyers)
    for c in cohorts or []:
        if c.get("pc_tone") == "put-tilted" and lean_key == "buyers":
            callouts.append({"key": "hedged_cohort", "name_en": c.get("name_en"),
                             "name_zh": c.get("name_zh"),
                             "pc_ratio": c.get("pc_ratio")})
            break
    # (b) the single most unusual sector by |z| (>=1σ from its own norm)
    unusual = sorted(
        [c for c in sector_heatmap if c.get("premium_z") is not None
         and abs(c["premium_z"]) >= 1.0 and (c.get("gross_premium_mn") or 0) > 0],
        key=lambda c: abs(c["premium_z"]), reverse=True)
    if unusual:
        u = unusual[0]
        callouts.append({"key": "crowded_sector" if u["premium_z"] > 0 else "quiet_sector",
                         "sector": u["sector"], "z": u["premium_z"]})

    return {
        "schema": "flow_read.v1",
        "asof": asof,
        "gross_premium_mn": gross,
        "net_premium_mn": net,             # soft
        "zerodte_share": zerodte,
        "n_names": n_names,
        "intensity_score": intensity_score,   # 0-100 or None (building)
        "intensity_key": intensity_key,        # heavy|busy|average|light|quiet|building
        "intensity_z": round(mean_z, 2) if mean_z is not None else None,
        "intensity_raw_fallback": intensity_raw,
        "lean_key": lean_key,                  # buyers|sellers|balanced
        "lean_breadth": round(breadth, 3) if breadth is not None else None,
        "lean_breadth_pct": breadth_pct,       # e.g. 62
        "dod_pct": dod_pct,                    # gross day-over-day %
        "dod_key": dod_key,                    # heavier|lighter|steady|None
        "stance_key": stance_key,              # watch|stand_aside
        "callouts": callouts,
    }


# ── kill-switch & stub ─────────────────────────────────────────────────────────

def _write_noindex_stub(site_dir: Path) -> None:
    stub = """<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="robots" content="noindex">
<title>Flow Desk (disabled)</title></head>
<body><p>Flow Desk is currently disabled.</p></body></html>"""
    write_page(site_dir / "flow_desk.html", stub)
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

    # Rebuild both flow-proxy stores FIRST — before the flow-rows early return —
    # so they accrue even on nights with no options-flow index: broad (RLT-R3,
    # read by the RLT-R2 classifier) and sector (read by build_etf_tile below).
    # HOUSE-U5 (FD-EXP): both rebuilds UPSERT committed data/flows/ parquets, so
    # they are lane-gated to the nightly collector — express/intraday lanes bake
    # site/ from the committed vintage and must leave data/ untouched. Their
    # per-ticker SO inputs (data/flows/<T>.parquet) only advance at nightly
    # collect anyway, so an off-nightly rebuild could never produce new rows.
    if nightly_advance_enabled():
        _rebuild_broad_proxy()
        _rebuild_sector_proxy()
    else:
        log.info("flow_desk: COLLECT_LANE!=nightly — skipping proxy store rebuilds "
                 "(broad_flow_proxy/etf_flow_proxy stay at committed vintage)")

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

    # FL-B: cohort-level aggregation (Mag7 / Memory / AI chips / Software).
    # Aggregate for the flow index's own as-of session — NOT date.today(): the
    # per-ticker summary parquets carry EOD rows through the last close, so
    # defaulting to today (build runs the morning after close) missed every row
    # and every cohort came back 0-of-N covered. Parse the tide as-of; fall back
    # to today only if it is absent/unparseable.
    site_flowdata_dir = site_dir / "flowdata"
    _asof_str = market_tide.get("asof")
    try:
        cohort_asof = date.fromisoformat(_asof_str) if _asof_str else None
    except (TypeError, ValueError):
        cohort_asof = None
    try:
        cohorts = build_cohorts(data_dir, asof=cohort_asof,
                                site_flowdata_dir=site_flowdata_dir)
        log.info("flow_desk: cohorts built — %d cohorts (asof=%s)",
                 len(cohorts), cohort_asof)
    except Exception as e:  # noqa: BLE001
        log.warning("flow_desk: cohort build failed (non-fatal): %s", e)
        cohorts = []

    # Section 0: the day's one-glance read (intensity + lean + stance) — powers
    # the hero scorecard. Display-tier; derived from the tide + heatmap + cohorts.
    flow_read = build_flow_read(market_tide, sector_heatmap, cohorts)

    # FS-4 Lane C: flow-score glance panel (display-only; never feeds rank/gate)
    flow_score_panel = build_flow_score_panel(data_dir)

    payload = {
        "schema": "flow_desk.v1",
        "built": str(date.today()),
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "asof": market_tide.get("asof"),
        "direction_reliable": False,
        "magnitude_reliable": True,
        "direction_note": "net premium direction is SOFT — approximate (minute tick-rule signing)",
        "read": flow_read,
        "cohorts": cohorts,
        "market_tide": market_tide,
        "sector_heatmap": sector_heatmap,
        "top_movers": top_movers,
        "etf_tile": etf_tile,
        "flow_score": flow_score_panel,
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
    # write_page, not write_text: flow_desk.html.j2 carries no data-base shim of
    # its own, so a raw write ships the page with its per-ticker fetches pointed
    # at Pages instead of R2 in any run outside the render lane's
    # inject_data_base sweep. The kill-switch stub above already writes this way.
    out = write_page(site_dir / "flow_desk.html", rendered)
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
