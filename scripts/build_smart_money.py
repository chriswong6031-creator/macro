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


def _build_grand_portfolio(sm: dict) -> list[dict]:
    """Issuer-collapsed consensus board sorted by aggregate $."""
    if not sm:
        return []
    by_ticker = sm.get("by_ticker", {})
    most_held = sm.get("most_held", [])
    out = []
    for m in most_held:
        ticker = m.get("ticker", "")
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
    """Activist situation monitor from the 13D/G wire axis."""
    bt = (sm or {}).get("by_ticker", {})
    slug_to_funds: dict[str, list[str]] = {}
    for tk, rec in bt.items():
        for h in rec.get("holders", []):
            slug_to_funds.setdefault(tk, []).append(h.get("fund", ""))

    out = []
    for row in wire_rows:
        if row.get("axis") != "13dg":
            continue
        if row.get("signal") not in ("high", "low"):
            continue
        ticker = row.get("ticker") or ""
        sf = bt.get(ticker, {}).get("since_filing", {})
        n_tracked = len(slug_to_funds.get(ticker, []))
        out.append({
            "date_filed": row.get("date", ""),
            "filer": row.get("fund", ""),
            "ticker": ticker,
            "issuer": row.get("issuer", ""),
            "form": row.get("type", ""),
            "state": row.get("action", ""),
            "signal": row.get("signal", ""),
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

    # ---- Phase 5: ledger advance (nightly-only) ----
    t5 = time.monotonic()
    ledger_added: dict = {}
    try:
        from engine.ownership_ledger import advance_ledgers, ledger_summary
        ledger_added = advance_ledgers(funds, sm)
        ledger = ledger_summary()
    except Exception as e:  # noqa: BLE001
        log.warning("ledger advance/summary failed: %s", e)
        ledger = {}
    phase_times["ledger"] = round(time.monotonic() - t5, 2)
    phase_times["boards"] = round(time.monotonic() - t4 - phase_times["ledger"], 2)

    built = datetime.now(timezone.utc).isoformat()

    # Freshness block (SM2-R11 required)
    freshness_block = {
        "axes": freshness,
        "next_deadline": clock.get("next_deadline", _STALE),
        "days_to_deadline": clock.get("days_to_deadline"),
        "quarter_state": clock.get("quarter_state", _STALE),
        "filed_pending": clock.get("filed_pending", []),
    }

    desk: dict = {
        "built": built,
        "freshness": freshness_block,
        "wire": wire,
        "initiations": initiations,
        "grand_portfolio": grand_portfolio,
        "crowding": crowding,
        "activists": activists,
        "managers": managers,
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

    # Benchmark log (SM2-R12)
    log.info(
        "build_smart_money BENCHMARK: total=%.1fs | tracker=%.1fs smart_money=%.1fs "
        "wire=%.1fs boards=%.1fs ledger=%.1fs | "
        "desk=%dKB wire_rows=%d initiations=%d crowding=%d activists=%d "
        "ledger_added=%s",
        phase_times["total"],
        phase_times.get("tracker", 0),
        phase_times.get("smart_money", 0),
        phase_times.get("wire", 0),
        phase_times.get("boards", 0),
        phase_times.get("ledger", 0),
        desk_kb,
        len(wire),
        len(initiations),
        len(crowding),
        len(activists),
        ledger_added,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
