"""Build the 13F Smart-Money TRADE TRACKER desk + Ownership Intelligence Desk.

STAGE FLOW
----------
1. compute_tracker()     — per-trade scorecard / leaderboard / best-worst / rotation
2. compute_smart_money() — by-ticker consensus / most-held / trend (SM2-R10: called
                           HERE and smartmoney.json written here; build_site.py later
                           overwrites — that overwrite is idempotent)
3. Desk assembly         — build smartmoney_desk.json (frozen interface, masterplan §4)
4. Ledger advance        — nightly-only (COLLECT_LANE guard inside ownership_ledger.py)
5. Template render       — current smart_money.html.j2; desk payload passed as `desk`
                           so stage E3 can consume it when the template is rebuilt

NEVER-BREAK CONTRACT: returns 0 on ANY error (mirrors build_alt_data.py). Each new
block is wrapped in try/except with an honest 'unavailable' degradation.

SM2-R10: smartmoney.json produced here; build_site.py's later write is idempotent.
SM2-R11: per-axis freshness stamps in the desk payload; the filing-season clock and
  filed-vs-pending grid are REQUIRED — built here and embedded in `freshness`.
SM2-R3: no blending across axes; crowding keeps short_volume and short_interest as
  SEPARATE sub-dict keys. A unit test asserts no numeric field mixes axes.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_smart_money")

_STALE = "unavailable"


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _jdump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def _site_dir() -> Path:
    d = config.ROOT / "site" / "factordata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _funddata_dir() -> Path:
    d = config.ROOT / "site" / "funddata"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Board assembly helpers (pure given resolved data)                             #
# --------------------------------------------------------------------------- #

def _build_initiations(sm: dict, tracker: dict) -> list[dict]:
    """SM2-R2 neutral initiations board: new/material-add ≥ 1% book, filing_date DESC.

    Issuer-collapsed (if multiple funds initiate the same ticker, they appear as one
    row with a funds list). n_funds_initiating = fund count. Default sort = filing_date
    DESC (neutral chronology). The word 'validated' is banned from all strings.
    """
    MIN_PCT = 1.0
    by_ticker: dict[str, dict] = {}

    # Build leaderboard turnover index for cross-referencing
    lb = tracker.get("leaderboard", []) if tracker else []
    tt_index = {r["slug"]: r.get("turnover_tier") for r in lb}

    funds_cfg = (config.load().get("smart_money", {}) or {}).get("funds", {}) or {}

    try:
        from engine.smart_money import _read_two, diff_snapshots, resolve_tickers
        from engine.smart_money import name_ticker_map, full_cusip_map, _snapshot_filing_date
        from engine.smart_money import position_rank_and_tilt, window_dressing_flag
        name_map = name_ticker_map()
        cusip_map, _ = full_cusip_map()
    except Exception:  # noqa: BLE001
        return []

    for slug, spec in funds_cfg.items():
        prev, latest = _read_two(slug)
        if latest is None or latest.empty:
            continue
        fd = _snapshot_filing_date(latest)
        if not fd:
            continue
        diff = diff_snapshots(prev, latest)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        diff = diff[diff["ticker"].notna()]
        if diff.empty:
            continue
        diff = position_rank_and_tilt(diff)

        for r in diff.itertuples(index=False):
            if r.action not in ("new", "add"):
                continue
            pct = float(r.pct_portfolio) if r.pct_portfolio is not None else 0.0
            if pct < MIN_PCT:
                continue
            ticker = str(r.ticker)
            fund_entry = {
                "slug": slug,
                "name": spec.get("name", slug),
                "action": r.action,
                "rank": int(r.rank) if hasattr(r, "rank") and r.rank is not None else None,
                "tilt": round(float(r.tilt_pp), 3) if hasattr(r, "tilt_pp") and r.tilt_pp is not None else None,
                "pct_book": round(pct, 2),
                "turnover_tier": tt_index.get(slug),
            }
            if ticker not in by_ticker:
                by_ticker[ticker] = {
                    "ticker": ticker,
                    "issuer": str(getattr(r, "issuer", "") or ""),
                    "funds": [],
                    "filing_date": fd,
                    "since_excess": None,
                    "persistence": None,
                }
            by_ticker[ticker]["funds"].append(fund_entry)
            # Take the latest filing_date across funds initiating this ticker
            if fd > by_ticker[ticker]["filing_date"]:
                by_ticker[ticker]["filing_date"] = fd

    # Enrich with since_filing from the sm payload
    sm_bt = (sm or {}).get("by_ticker", {})
    for ticker, rec in by_ticker.items():
        sf = sm_bt.get(ticker, {}).get("since_filing")
        if sf:
            rec["since_excess"] = sf.get("ex_spy_pct")

    # n_funds_initiating per issuer
    result = []
    for ticker, rec in by_ticker.items():
        rec["n_funds_initiating"] = len(rec["funds"])
        result.append(rec)

    # SM2-R2: default sort = filing_date DESC (neutral chronology)
    result.sort(key=lambda r: r.get("filing_date", ""), reverse=True)
    return result


# Index / sector / commodity ETFs are excluded from the CROSS-STOCK consensus and
# crowding boards (GS-style single-stock convention): an SPY line is cash parking,
# not a stock pick, and it distorts holder counts. Fund-book views (accordion,
# rotation) still show them — this filter applies only to the cross-sectional boards.
_INDEX_ETFS = frozenset({
    "SPY", "IVV", "VOO", "QQQ", "IWM", "DIA", "VTI", "RSP", "MDY", "IJR", "IJH",
    "EEM", "EFA", "VEA", "VWO", "FXI", "KWEB", "EWJ", "EWZ", "INDA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "IBB", "KRE", "XOP", "XME", "GDX", "GDXJ", "ARKK",
    "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND",
})


def _build_grand_portfolio(sm: dict) -> list[dict]:
    """Issuer-collapsed consensus board sorted by aggregate $."""
    if not sm:
        return []
    by_ticker = sm.get("by_ticker", {})
    most_held = sm.get("most_held", [])
    out = []
    n_etf_skipped = 0
    for m in most_held:
        ticker = m.get("ticker", "")
        if ticker in _INDEX_ETFS:
            n_etf_skipped += 1
            continue
        bt = by_ticker.get(ticker, {})
        trend = bt.get("trend", {})
        holders_series = trend.get("holders_series", []) if trend else []
        # QoQ holder delta
        h_first = trend.get("holders_first", 0) if trend else 0
        h_last = trend.get("holders_last", 0) if trend else 0
        d_funds_qoq = (h_last - h_first) if trend else None
        # n_top10: how many current holders have this in their top-10 (approx from rank)
        holders = bt.get("holders", [])
        n_top10 = sum(1 for h in holders if (h.get("position_rank") or 99) <= 10)
        # since_excess from since_filing
        since_excess = bt.get("since_filing", {}).get("ex_spy_pct") if bt.get("since_filing") else None
        # HHI from overlap_stats already in bt
        hhi = bt.get("ownership_hhi")
        max_book_pct = bt.get("max_book_pct")
        agg_value_usd = float(m.get("total_value", 0))
        # Issuer: take from first holder that carries it (propagated by compute_smart_money fix)
        issuer_gp = next((h.get("issuer", "") for h in holders if h.get("issuer")), "")
        out.append({
            "ticker": ticker,
            "issuer": issuer_gp,
            "n_funds": int(m.get("n_funds", 0)),
            "d_funds_qoq": d_funds_qoq,
            "holders_series": holders_series,
            "agg_value_usd": round(agg_value_usd, 0),
            "max_book_pct": max_book_pct,
            "hhi": hhi,
            "n_top10": n_top10,
            "since_excess": since_excess,
            "asof": bt.get("as_of", ""),
        })
    out.sort(key=lambda r: -(r.get("agg_value_usd") or 0))
    if n_etf_skipped:
        log.info("grand_portfolio: %d index-ETF lines excluded from cross-stock board",
                 n_etf_skipped)
    return out


def _build_crowding(sm: dict) -> list[dict]:
    """Crowding/unwind radar rows.

    SM2-R3: short_volume and short_interest are SEPARATE sub-dict keys — they must
    never share a column or an as-of. The `short_volume` sub-dict carries its own
    `asof` key; `short_interest` carries `settlement_date` as its stamp. No numeric
    field crosses the two axes.
    """
    if not sm:
        return []

    try:
        from engine.ownership_crowding import (adv_shares, days_to_exit as _dte,
                                               crowding_tier as _ct, implied_entry_band)
        from engine.short_volume import signal_map as sv_map
    except Exception:  # noqa: BLE001
        return []

    try:
        sv = sv_map()
    except Exception:  # noqa: BLE001
        sv = {}

    # Load short interest
    si_data: dict = {}
    try:
        import pandas as pd
        p = config.data_dir() / "finra" / "short_interest.parquet"
        if p.exists():
            si_df = pd.read_parquet(p)
            for idx, row in si_df.iterrows():
                si_data[str(idx)] = {
                    "days_to_cover": row.get("days_to_cover"),
                    "si_change_pct": row.get("si_change_pct"),
                    "settlement_date": str(row.get("settlement_date", "")) if row.get("settlement_date") else None,
                }
    except Exception:  # noqa: BLE001
        pass

    # ClosePanel for entry_band latest_close (reuse same price plumbing as enrich_since_filing)
    close_panel = None
    try:
        from engine.manager_trades import ClosePanel
        close_panel = ClosePanel()
    except Exception:  # noqa: BLE001
        log.debug("_build_crowding: ClosePanel unavailable — entry_band n_underwater will be None")

    by_ticker = sm.get("by_ticker", {})
    most_held = sm.get("most_held", [])

    # Build universe DTE distribution for quintile calibration
    # Uses aggregate shares directly from holder records (propagated in E2.5 fix).
    dte_universe: list[float] = []
    ticker_dte_map: dict[str, float | None] = {}
    for m in most_held:
        ticker = m.get("ticker", "")
        if ticker in _INDEX_ETFS:
            continue
        bt = by_ticker.get(ticker, {})
        holders = [h for h in bt.get("holders", []) if h.get("action") != "exit"]
        as_of = bt.get("as_of", "")
        adv_meta = adv_shares(ticker, as_of=as_of)
        adv = adv_meta["adv"] if adv_meta else None
        # Aggregate shares: sum from holder records (shares propagated by compute_smart_money)
        agg_shares = sum(float(h.get("shares") or 0) for h in holders)
        dte_val = _dte(agg_shares if agg_shares > 0 else None, adv)
        ticker_dte_map[ticker] = dte_val
        if dte_val is not None:
            dte_universe.append(dte_val)

    out = []
    for m in most_held:
        ticker = m.get("ticker", "")
        bt = by_ticker.get(ticker, {})
        holders = [h for h in bt.get("holders", []) if h.get("action") != "exit"]
        as_of = bt.get("as_of", "")
        dte_val = ticker_dte_map.get(ticker)
        ct = _ct(dte_val, dte_universe if len(dte_universe) >= 5 else None)

        # Issuer: take from first non-exit holder (populated by compute_smart_money fix)
        issuer = next((h.get("issuer", "") for h in holders if h.get("issuer")), "")

        # Implied entry band: pass latest close from ClosePanel (reuse existing price plumbing)
        ieb = None
        try:
            latest_close = None
            if close_panel is not None:
                cs = close_panel.get(ticker)
                if cs is not None and len(cs) > 0:
                    latest_close = float(cs.iloc[-1])
            ieb = implied_entry_band(holders, latest_close=latest_close)
        except Exception:  # noqa: BLE001
            pass

        # short_volume sub-dict — its own asof, strictly separate (SM2-R3)
        sv_rec = sv.get(ticker)
        sv_sub = None
        if sv_rec:
            sv_sub = {
                "ratio": sv_rec.get("short_ratio"),
                "trend_pp": sv_rec.get("trend_pp"),
                "ratio_z": sv_rec.get("ratio_z"),
                "asof": sv_rec.get("asof"),    # daily as-of, independent stamp
            }

        # short_interest sub-dict — settlement_date stamp, strictly separate (SM2-R3)
        si_rec = si_data.get(ticker)
        si_sub = None
        if si_rec:
            si_sub = {
                "days_to_cover": si_rec.get("days_to_cover"),
                "si_change_pct": si_rec.get("si_change_pct"),
                "settlement_date": si_rec.get("settlement_date"),  # bi-monthly as-of
            }

        out.append({
            "ticker": ticker,
            "issuer": issuer,
            "n_funds": int(m.get("n_funds", 0)),
            "agg_value_usd": round(float(m.get("total_value", 0)), 0),
            "hhi": bt.get("ownership_hhi"),
            "max_book_pct": bt.get("max_book_pct"),
            "days_to_exit": dte_val,
            "crowding_tier": ct,
            "entry_band": ieb,
            "short_volume": sv_sub,    # separate sub-dict, own asof (SM2-R3)
            "short_interest": si_sub,  # separate sub-dict, settlement_date (SM2-R3)
        })

    return out


def _build_activists(wire_rows: list[dict], sm: dict) -> list[dict]:
    """Activist situation monitor from the 13D/G wire axis.

    State comes from engine.beneficial_ownership.load_regime() — the per-ticker
    regime machine (activist / flip / passive / custodial), which is the classifier
    that carries the 13G→13D flip detection. The wire row's own form-derived label
    is only the fallback when a ticker has no regime entry.
    """
    bt = (sm or {}).get("by_ticker", {})
    slug_to_funds: dict[str, list[str]] = {}
    for tk, rec in bt.items():
        for h in rec.get("holders", []):
            slug_to_funds.setdefault(tk, []).append(h.get("fund", ""))

    regime: dict[str, dict] = {}
    try:
        from engine.beneficial_ownership import load_regime
        regime = load_regime() or {}
    except Exception as e:  # noqa: BLE001 — board degrades to form-derived labels
        log.warning("load_regime unavailable for activist board: %s", e)

    out = []
    for row in wire_rows:
        if row.get("axis") != "13dg":
            continue
        if row.get("signal") not in ("high", "low"):
            continue
        ticker = row.get("ticker") or ""
        reg = regime.get(ticker) or {}
        state = reg.get("regime") or reg.get("state") or ""
        if not state:
            # form-derived fallback: 13D from a non-custodian reads activist-form,
            # everything else passive-form (custodial rows never reach here — their
            # signal is 'noise').
            state = "activist" if row.get("action") == "13d" else "passive"
        sf = bt.get(ticker, {}).get("since_filing", {})
        n_tracked = len(slug_to_funds.get(ticker, []))
        out.append({
            "date_filed": row.get("date", ""),
            "filer": row.get("fund", ""),
            "ticker": ticker,
            "issuer": row.get("issuer", ""),
            "form": row.get("type", ""),
            "state": state,
            "signal": reg.get("signal") or row.get("signal", ""),
            "n_tracked_holders": n_tracked,
            "since_excess": sf.get("ex_spy_pct") if sf else None,
        })
    return out


def _build_managers(tracker: dict) -> dict:
    """Per-slug manager dict from the leaderboard."""
    out: dict[str, dict] = {}
    if not tracker:
        return out
    for r in tracker.get("leaderboard", []):
        slug = r.get("slug", "")
        if not slug:
            continue
        out[slug] = {
            "turnover_pct": r.get("turnover_pct"),
            "turnover_tier": r.get("turnover_tier"),
            "holding_period_q": r.get("holding_period_q"),
            "concentration_pct": r.get("concentration_pct"),
            "n_holdings": r.get("n_holdings"),
            "style": r.get("style"),
            "status": r.get("status"),
            "coverage_pct": r.get("coverage_pct"),
            "sell_skill": r.get("sell_skill"),
            "n_buys_h": r.get("n_buys_h"),
            "decay": r.get("decay"),
        }
    return out


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    t0 = time.monotonic()
    phase_times: dict[str, float] = {}

    cfg = config.load()
    sm_cfg = cfg.get("smart_money", {}) or {}
    funds = sm_cfg.get("funds", {}) or {}

    # ---- Phase 1: compute_tracker ----
    t1 = time.monotonic()
    tracker = None
    try:
        from engine.manager_trades import compute_tracker
        tracker = compute_tracker()
        if not tracker:
            log.info("smart-money tracker: nothing to score — skipping tracker JSON")
    except Exception as e:  # noqa: BLE001
        log.warning("compute_tracker failed — continuing: %s", e)
    phase_times["tracker"] = round(time.monotonic() - t1, 2)

    if tracker:
        try:
            (_site_dir() / "smartmoney_tracker.json").write_text(_jdump(tracker))
        except Exception as e:  # noqa: BLE001
            log.warning("write smartmoney_tracker.json failed: %s", e)

    # ---- Phase 2: compute_smart_money (SM2-R10: called here) ----
    t2 = time.monotonic()
    sm = None
    try:
        from engine.smart_money import compute_smart_money
        sm = compute_smart_money(sm_cfg)
        if not sm:
            log.info("compute_smart_money: no data — degraded desk")
    except Exception as e:  # noqa: BLE001
        log.warning("compute_smart_money failed — continuing: %s", e)
    phase_times["smart_money"] = round(time.monotonic() - t2, 2)

    if sm:
        try:
            (_site_dir() / "smartmoney.json").write_text(_jdump(sm))
        except Exception as e:  # noqa: BLE001
            log.warning("write smartmoney.json failed: %s", e)

    # ---- Phase 3: event wire + filing-season clock ----
    t3 = time.monotonic()
    wire: list[dict] = []
    clock: dict = {}
    wire_13dg_activists: list[dict] = []
    try:
        from engine.ownership_event_wire import (build_wire, freshness_axes,
                                                 _13dg_rows, _13DG_LOOKBACK_ACTIVISTS)
        wire, clock = build_wire(funds)
        freshness = freshness_axes(wire, clock)
        # Activists board keeps its own 45-day 13D/G feed (independent of main wire cap)
        try:
            wire_13dg_activists = _13dg_rows(lookback_days=_13DG_LOOKBACK_ACTIVISTS)
        except Exception as e_act:  # noqa: BLE001
            log.warning("activists 45d 13D/G feed failed — falling back to main wire: %s", e_act)
            wire_13dg_activists = [r for r in wire if r.get("axis") == "13dg"]
    except Exception as e:  # noqa: BLE001
        log.warning("ownership_event_wire failed — continuing: %s", e)
        freshness = []
    phase_times["wire"] = round(time.monotonic() - t3, 2)

    # ---- Phase 4: assemble desk payload ----
    t4 = time.monotonic()
    try:
        initiations = _build_initiations(sm or {}, tracker or {})
    except Exception as e:  # noqa: BLE001
        log.warning("initiations build failed: %s", e)
        initiations = []

    try:
        grand_portfolio = _build_grand_portfolio(sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("grand_portfolio build failed: %s", e)
        grand_portfolio = []

    try:
        crowding = _build_crowding(sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("crowding build failed: %s", e)
        crowding = []

    try:
        # Activists board uses the 45-day 13D/G feed (independent of the capped 14d main wire)
        activists = _build_activists(wire_13dg_activists, sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("activists build failed: %s", e)
        activists = []

    try:
        managers = _build_managers(tracker or {})
    except Exception as e:  # noqa: BLE001
        log.warning("managers build failed: %s", e)
        managers = {}

    # ---- Phase 4.2: insider intelligence (two lanes, two clocks — SM2-R3) ----
    t42 = time.monotonic()
    insider_intel: dict = {}
    try:
        from engine.insider_intel import build_insider_intel
        # Roster = tickers currently held (non-exit holder) by any tracked fund.
        # Lets the market-wide quiver lane carry an honest "held by tracked funds"
        # flag (roster_hit) without blending lanes numerically. Empty → None so
        # "unknown" is never displayed as "not held".
        roster: set[str] = set()
        try:
            roster = {
                tk for tk, rec in ((sm or {}).get("by_ticker", {}) or {}).items()
                if any(h.get("action") != "exit" for h in rec.get("holders", []))
            }
        except Exception as e:  # noqa: BLE001
            log.warning("insider roster derivation failed — roster_hit degrades: %s", e)
        try:
            insider_intel = build_insider_intel(sm_cfg, roster=roster or None) or {}
        except TypeError:
            # Older engine signature without the roster kwarg — degrade politely.
            insider_intel = build_insider_intel(sm_cfg) or {}
        if not insider_intel:
            log.info("insider_intel: no data — desk section degrades to hidden")
    except Exception as e:  # noqa: BLE001
        log.warning("insider_intel build failed — continuing: %s", e)
        insider_intel = {}
    phase_times["insider_intel"] = round(time.monotonic() - t42, 2)

    # ---- Phase 4.3: per-fund intelligence (full books / conviction / theme reads) ----
    t43 = time.monotonic()
    fund_intel: dict = {}
    fund_intel_index: dict = {}
    try:
        from engine.fund_intelligence import build_fund_intel
        fund_intel = build_fund_intel(sm_cfg, tracker) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("fund_intel build failed — continuing: %s", e)
        fund_intel = {}
    if fund_intel.get("funds"):
        _lb_grades = {r.get("slug"): r.get("grade")
                      for r in (tracker or {}).get("leaderboard", [])}
        for slug, fi in (fund_intel.get("funds") or {}).items():
            # Per-fund JSON page payload — the 50 full books never ride in the
            # desk JSON (small pages; the dossier/template hydrates from here).
            try:
                (_funddata_dir() / f"{slug}.json").write_text(_jdump(fi))
            except Exception as e:  # noqa: BLE001
                log.warning("write funddata/%s.json failed: %s", slug, e)
            # Compact index row for the desk payload (directory grid + links).
            try:
                meta = fi.get("book_meta") or {}
                core = (fi.get("theme_read") or {}).get("core") or {}
                series = fi.get("sector_series") or []
                weights = ((series[-1] or {}).get("weights") or {}) if series else {}
                top_sector = max(weights, key=weights.get) if weights else None
                fund_intel_index[slug] = {
                    "core_lean_label": core.get("label"),
                    "core_lean_label_zh": core.get("label_zh"),
                    "book_value_usd": meta.get("book_value_usd"),
                    "n_positions": meta.get("n_positions"),
                    "top_sector": top_sector,
                    "grade": _lb_grades.get(slug),
                }
            except Exception as e:  # noqa: BLE001
                log.warning("fund_intel_index row failed for %s: %s", slug, e)
    phase_times["fund_intel"] = round(time.monotonic() - t43, 2)

    # ---- Phase 4.4: consolidated cross-fund flow + descriptive models ----
    t44 = time.monotonic()
    flow: dict = {}
    try:
        from engine.ownership_flow import (group_flow, models, rotation_history,
                                           stock_flow)
        flow_cfg = sm_cfg.get("flow", {}) or {}
        top_grades = flow_cfg.get("top_grades", ["A", "B"]) or ["A", "B"]
        top_slugs = [r.get("slug") for r in (tracker or {}).get("leaderboard", [])
                     if r.get("grade") in set(top_grades)]

        cls = None
        try:
            from engine.fund_intelligence import load_classifications
            cls = load_classifications()
        except Exception as e:  # noqa: BLE001
            log.warning("load_classifications failed — models degrade: %s", e)

        def _flow_part(name: str, default, fn, *args, **kwargs):
            """One flow sub-board; degrades honestly on failure (NEVER-BREAK)."""
            try:
                out = fn(*args, **kwargs)
                return out if out is not None else default
            except Exception as e_part:  # noqa: BLE001
                log.warning("flow.%s failed — continuing: %s", name, e_part)
                return default

        stock_flow_d = _flow_part("stock", {}, stock_flow, sm or {}, tracker or {})
        flow = {
            "stock": stock_flow_d,
            "sector": _flow_part("sector", {}, group_flow, fund_intel,
                                 tracker or {}, level="sector"),
            "theme": _flow_part("theme", {}, group_flow, fund_intel,
                                tracker or {}, level="theme"),
            "sector_top": _flow_part("sector_top", {}, group_flow, fund_intel,
                                     tracker or {}, level="sector",
                                     top_grades=top_grades),
            "theme_top": _flow_part("theme_top", {}, group_flow, fund_intel,
                                    tracker or {}, level="theme",
                                    top_grades=top_grades),
            "history": _flow_part("history", [], rotation_history, fund_intel),
            "history_top": _flow_part("history_top", [], rotation_history,
                                      fund_intel, top_slugs=top_slugs),
            "models": _flow_part("models", {}, models, sm or {}, tracker or {},
                                 stock_flow_d, crowding, fund_intel, cls),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("flow build failed — continuing: %s", e)
        flow = {}
    phase_times["flow"] = round(time.monotonic() - t44, 2)

    # ---- Phase 5: ledger advance (nightly-only) ----
    t5 = time.monotonic()
    ledger_added: dict = {}
    try:
        from engine.ownership_ledger import advance_ledgers, ledger_summary
        # L5 cohort: the conviction-buys composite earns a forward record
        # (additive kwarg — advance_ledgers(funds, sm) still works without it).
        ledger_added = advance_ledgers(funds, sm, models=flow.get("models"))
        ledger = ledger_summary()
    except Exception as e:  # noqa: BLE001
        log.warning("ledger advance/summary failed: %s", e)
        ledger = {}
    phase_times["ledger"] = round(time.monotonic() - t5, 2)
    # "boards" keeps meaning the Phase-4 board assembly only — the new v3
    # phases are timed separately and subtracted so the benchmark stays honest.
    phase_times["boards"] = round(
        time.monotonic() - t4 - phase_times["ledger"]
        - phase_times.get("insider_intel", 0)
        - phase_times.get("fund_intel", 0)
        - phase_times.get("flow", 0), 2)

    built = datetime.now(timezone.utc).isoformat()

    # Freshness block (SM2-R11 required)
    freshness_block = {
        "axes": freshness,
        "next_deadline": clock.get("next_deadline", _STALE),
        "days_to_deadline": clock.get("days_to_deadline"),
        "quarter_state": clock.get("quarter_state", _STALE),
        "filed_pending": clock.get("filed_pending", []),
    }

    # Balanced display slice: the wire itself is newest-first across ALL axes, so a
    # naive top-60 render would show only the fast axes (daily insider/13dg) between
    # 13F filing windows. wire_display keeps the newest 20 rows PER normalized axis
    # (13f incl. amendments / 13dg / insider), merged newest-first — additive key,
    # display concern only.
    def _axis_norm(r: dict) -> str:
        ax = r.get("axis") or ""
        if ax.startswith("form4"):
            return "insider"
        if ax == "13f" and r.get("type") == "13f_amendment":
            return "13fa"     # amendments are dated later than the originals and
                              # would otherwise crowd out every rotation delta
        return ax
    _DISPLAY_CAPS = {"13f": 20, "13fa": 8, "13dg": 20, "insider": 20}
    wire_display: list[dict] = []
    for ax_key, cap in _DISPLAY_CAPS.items():
        ax_rows = [r for r in wire if _axis_norm(r) == ax_key]
        wire_display.extend(ax_rows[:cap])
    wire_display.sort(key=lambda r: r.get("date", ""), reverse=True)
    # F4: fold marking — these rows are the SAME dict objects as in `wire`, so
    # the flag lands in both lists. The template renders the FULL wire and folds
    # to data-fold="1" rows by default; "See more" reveals the rest client-side.
    for _r in wire_display:
        _r["_fold"] = 1

    desk: dict = {
        "built": built,
        "freshness": freshness_block,
        "wire": wire,
        "wire_display": wire_display,
        "initiations": initiations,
        "grand_portfolio": grand_portfolio,
        "crowding": crowding,
        "activists": activists,
        "managers": managers,
        "insider_intel": insider_intel,
        "flow": flow,
        "fund_intel_index": fund_intel_index,
        "ledger": ledger,
    }

    try:
        (_site_dir() / "smartmoney_desk.json").write_text(_jdump(desk))
        desk_kb = len(_jdump(desk)) // 1024
    except Exception as e:  # noqa: BLE001
        log.warning("write smartmoney_desk.json failed: %s", e)
        desk_kb = 0

    phase_times["total"] = round(time.monotonic() - t0, 2)

    # ---- Phase 6: template render ----
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        html = env.get_template("smart_money.html.j2").render(
            trk=tracker or {},
            generated_utc=generated_utc,
            active_section="us",
            active_page="smart_money",
            desk=desk,  # E3 template will consume this; current template ignores unknown vars
        )
        write_page(config.ROOT / "site" / "smart_money.html", html)
        log.info("wrote smart_money.html (%d KB)", len(html) // 1024)
    except Exception as e:  # noqa: BLE001
        log.warning("smart-money render failed — JSONs written, page skipped: %s", e)

    # ---- Phase 6.5: fund dossier pages AT SITE ROOT (F6: report_base.html.j2
    # hardcodes root-relative theme.css/theme.js, so site/fund_<slug>.html needs
    # no nav_prefix). Per-fund try/except — one bad book never kills the rest. ----
    t65 = time.monotonic()
    n_dossiers = 0
    if ((sm_cfg.get("dossier", {}) or {}).get("enabled", True)) and fund_intel.get("funds"):
        _lb_rows = {r.get("slug"): r for r in (tracker or {}).get("leaderboard", [])}
        _by_fund = (tracker or {}).get("by_fund", {}) or {}
        dossier_tpl = None
        try:
            dossier_tpl = env.get_template("fund_dossier.html.j2")
        except Exception as e:  # noqa: BLE001
            log.warning("fund_dossier template unavailable — dossiers skipped: %s", e)
        if dossier_tpl is not None:
            for slug, fi in (fund_intel.get("funds") or {}).items():
                try:
                    html_fund = dossier_tpl.render(
                        slug=slug,
                        fi=fi,
                        lb_row=_lb_rows.get(slug) or {},
                        bf=_by_fund.get(slug) or {},
                        desk=desk,
                        generated_utc=generated_utc,
                        active_section="us",
                        active_page="smart_money",
                    )
                    write_page(config.ROOT / "site" / f"fund_{slug}.html", html_fund)
                    n_dossiers += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("fund dossier render failed for %s: %s", slug, e)
        # Fund directory page — own try/except, degrades to no page.
        try:
            index_rows = []
            for slug, fi in (fund_intel.get("funds") or {}).items():
                lb = _lb_rows.get(slug) or {}
                sc = (_by_fund.get(slug) or {}).get("scorecard") or {}
                meta = fi.get("book_meta") or {}
                core = (fi.get("theme_read") or {}).get("core") or {}
                index_rows.append({
                    "slug": slug,
                    "name": (funds.get(slug) or {}).get("name", slug),
                    "style": (funds.get(slug) or {}).get("style"),
                    "status": (funds.get(slug) or {}).get("status"),
                    "grade": lb.get("grade"),
                    "reliability": lb.get("reliability") or sc.get("reliability"),
                    "core_lean_label": core.get("label"),
                    "core_lean_label_zh": core.get("label_zh"),
                    "book_value_usd": meta.get("book_value_usd"),
                    "n_positions": meta.get("n_positions"),
                    "href": f"fund_{slug}.html",
                })
            index_rows.sort(key=lambda r: -(r.get("book_value_usd") or 0))
            html_idx = env.get_template("fund_index.html.j2").render(
                rows=index_rows,
                desk=desk,
                generated_utc=generated_utc,
                active_section="us",
                active_page="smart_money",
            )
            write_page(config.ROOT / "site" / "fund_index.html", html_idx)
            log.info("wrote fund_index.html (%d funds) + %d dossier pages",
                     len(index_rows), n_dossiers)
        except Exception as e:  # noqa: BLE001
            log.warning("fund_index render failed — directory page skipped: %s", e)
    phase_times["dossiers"] = round(time.monotonic() - t65, 2)

    # Benchmark log (SM2-R12)
    log.info(
        "build_smart_money BENCHMARK: total=%.1fs | tracker=%.1fs smart_money=%.1fs "
        "wire=%.1fs boards=%.1fs insider_intel=%.1fs fund_intel=%.1fs flow=%.1fs "
        "ledger=%.1fs dossiers=%.1fs | "
        "desk=%dKB wire_rows=%d initiations=%d crowding=%d activists=%d "
        "dossier_pages=%d ledger_added=%s",
        phase_times["total"],
        phase_times.get("tracker", 0),
        phase_times.get("smart_money", 0),
        phase_times.get("wire", 0),
        phase_times.get("boards", 0),
        phase_times.get("insider_intel", 0),
        phase_times.get("fund_intel", 0),
        phase_times.get("flow", 0),
        phase_times.get("ledger", 0),
        phase_times.get("dossiers", 0),
        desk_kb,
        len(wire),
        len(initiations),
        len(crowding),
        len(activists),
        n_dossiers,
        ledger_added,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
