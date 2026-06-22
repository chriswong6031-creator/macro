"""China predictive-validation harness — forward-return scorecard for the China signal legs.

LEAF · CONTEXT-ONLY · keyless · never raises into a build. The keystone Stage-3 honesty
layer: for every China signal that is RECONSTRUCTABLE from stored history it measures
whether the signal actually predicted forward returns, using the SAME institutional
primitives the US/vector calibrators use (engine.validation — imported and called VERBATIM,
never re-derived: rank_ic, ic_summary, newey_west_tstat, incremental_ic, benjamini_hochberg).

Signal families, each reconstructed from what is actually on disk today:

  * fundflow         — per-name 主力 (超大+大单) net inflow rate (GATED Tushare moneyflow_dc), a
                      CROSS-SECTIONAL signal validated like valuation off the weekly-grid history in
                      data/tushare/flow_hist.parquet (collectors/tushare_history backfills it from
                      the paid history). sign_expected +1 (inflow → continuation). `accruing` when
                      the token / history is absent.
  * chips            — per-name 获利比例 win-rate (GATED Tushare cyq_perf), same cross-sectional path
                      off data/tushare/chips_hist.parquet. sign_expected −1 (euphoric → contrarian).


  * valuation       — per-name P/E·P/B own-history percentile (cheap = low pctile). A
                      CROSS-SECTIONAL signal → daily cross-sectional rank-IC vs each name's
                      forward CSI-300-relative return, summarized over a date grid, plus an
                      incremental-IC neutralization against {momentum_252, reversal_21, size}
                      (the honest "is value just reversal?" number — A-share value Sharpe is
                      known negative, so the leg is EXPECTED to wash out / validate wrong-sign).
  * margin          — whole-market financing balance as a share of float (fin_pct_float). A
                      MARKET-WIDE timing series, NOT a cross-section → validated as a market
                      timer: signed forward CSI-300 return regressed on the leg, pooled
                      Newey-West HAC t (high leverage = contrarian risk → sign_expected -1).
  * news_sentiment  — blended CCTV+wire media-sentiment z-score. Also MARKET-WIDE → same
                      market-timer path (rich sentiment = contrarian fade → sign_expected -1).

Forward returns come from the wide panel data/china_search/closes.parquet (cols = tickers),
benched to CSI 300 (510300.SS, resolved via store.read because it is NOT a panel column).
Leakage-guarded throughout: every forward return is measured PAST→FUTURE only, and a date
is only scored once the panel actually covers its forward end (mirrors china_radar_ledger._fwd_rel).

Anything without enough reconstructable history degrades to status "accruing" (n_obs 0) — the
conviction/hub LEDGERS (snapshot-forward) are the rigorous path that accrues from go-live.

validate_all() writes data/china_validation/scorecard.json (schema china_validation.v1) and
returns the same dict. Every public fn returns plain data / None and NEVER raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_validation.v1"
BENCH = "510300.SS"                       # CSI 300 ETF — same bench as china_radar / its ledger
FDR_ALPHA = 0.10
_MIN_PROVEN_N = 40                        # cross-sectional families (mirror hub_track_record._MIN_PROVEN_N)
_MIN_PROVEN_N_TS = 25                     # pooled time-series families (looser, fewer obs)
_TD_PER_YEAR = 252

# (family -> expected SIGN of mean predictive IC / regression slope). A leg that validates
# to the WRONG sign is actively misleading; signal_lab will zero its weight. A-share value /
# leverage / sentiment all carry a contrarian prior (cheap or de-levered or fearful outperforms).
_SIGN_EXPECTED = {"valuation": +1, "margin": -1, "news_sentiment": -1,
                  "fundflow": +1, "chips": -1}
# fundflow: 主力 net inflow → continuation (+1, the accumulation prior).
# chips:    high 获利比例 win-rate → euphoric/profit-taking → contrarian fade (−1).
# Both are PRIORS only — the harness measures the realized sign and signal_lab zeros a
# proven wrong-sign leg regardless.


# --------------------------------------------------------------------------- #
# leak-guarded forward returns from the wide panel  (mirror china_radar_ledger._fwd_rel)
# --------------------------------------------------------------------------- #
def _bench_close():
    """CSI-300 close Series (the bench is NOT a panel column). None on miss."""
    try:
        b = store.read("china", BENCH)
        if b is None or b.empty or "close" not in b.columns:
            return None
        import pandas as pd  # noqa: F401
        return b["close"].dropna()
    except Exception:  # noqa: BLE001
        return None


def _panel():
    """Wide close panel (Date index, cols = tickers). None on miss."""
    try:
        df = store.read("china_search", "closes")
        if df is None or df.empty:
            return None
        return df
    except Exception:  # noqa: BLE001
        return None


def _fwd_rel_panel(panel, bench, horizon: int):
    """Per-name forward CSI-300-RELATIVE return over `horizon` trading days, as a DataFrame
    aligned to the panel (row d, col t = name return d->d+h MINUS bench return d->d+h).
    Vectorized: one pct_change(horizon) on the whole panel, shifted to land the forward
    window on its START date. Leakage-safe — the value at date d uses only dates >= d, and
    callers must additionally drop dates whose forward end the panel does not yet cover.
    """
    try:
        import numpy as np  # noqa: F401
        import pandas as pd
        px = panel.apply(pd.to_numeric, errors="coerce")
        # forward h-day return realized over (d, d+h], stamped on START date d
        fwd = px.pct_change(horizon).shift(-horizon)
        # bench forward return aligned to the SAME row index
        bc = pd.to_numeric(bench, errors="coerce").reindex(px.index).ffill()
        bfwd = bc.pct_change(horizon).shift(-horizon)
        rel = fwd.sub(bfwd, axis=0) * 100.0
        return rel
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._fwd_rel_panel failed (%s)", e)
        return None


def _last_covered(panel, horizon: int):
    """Last panel date whose forward end (+horizon rows) is still inside the panel — the
    leak guard: any signal date AFTER this has no realized forward return yet."""
    try:
        if panel is None or len(panel.index) <= horizon:
            return None
        return panel.index[-(horizon + 1)]
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# reconstructable cross-sectional signal: own-history valuation percentile
# --------------------------------------------------------------------------- #
def _valuation_cross_sections():
    """{asof_date(Timestamp): Series(ticker -> cheapness)} from the valuation percentile
    cache. cheapness = -(mean of pe.pctile, pb.pctile)/100 so that a HIGHER signal = CHEAPER
    (sign_expected +1 means cheap predicts positive forward returns). Empty dict on miss.

    Only the snapshots actually stored are returned (today this is a few asof days — that
    yields < MIN_DATES cross-sections, so the family honestly reports `accruing`)."""
    out: dict = {}
    try:
        import pandas as pd
        p = config.data_dir() / "china_valuation" / "percentiles.parquet"
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        if df.empty or "asof" not in df.columns:
            return out
        for asof, grp in df.groupby(df["asof"].astype(str)):
            ser = {}
            for _, r in grp.iterrows():
                try:
                    pay = json.loads(r["payload"])
                except Exception:  # noqa: BLE001
                    continue
                pe = (pay.get("pe") or {}).get("pctile")
                pb = (pay.get("pb") or {}).get("pctile")
                vals = [v for v in (pe, pb) if isinstance(v, (int, float))]
                if not vals:
                    continue
                ser[str(r["ticker"])] = -(sum(vals) / len(vals)) / 100.0
            if len(ser) >= 10:
                out[pd.Timestamp(asof)] = pd.Series(ser, dtype=float)
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._valuation_cross_sections failed (%s)", e)
    return out


def _factor_loadings(panel, asof, horizon_lookback: int = 252):
    """{ticker -> {momentum_252, reversal_21, size}} cross-section AS OF `asof` for the
    incremental-IC neutralization. Uses only PAST prices (<= asof) — leakage-safe. None/empty
    if the panel doesn't reach back far enough."""
    try:
        import pandas as pd
        px = panel[panel.index <= asof].apply(pd.to_numeric, errors="coerce")
        if len(px) < 30:
            return None
        last = px.iloc[-1]
        # momentum_252: 12m return skipping the most recent ~21d (12-1, the robust leg)
        mom_win = min(horizon_lookback, len(px) - 1)
        skip = min(21, mom_win - 1)
        past = px.iloc[-(mom_win + 1)] if mom_win + 1 <= len(px) else px.iloc[0]
        recent = px.iloc[-(skip + 1)] if skip + 1 <= len(px) else last
        mom = (recent / past) - 1.0
        # reversal_21: short-term reversal (NEGATIVE of last-21d return)
        rev_base = px.iloc[-(skip + 1)] if skip + 1 <= len(px) else px.iloc[0]
        rev = -((last / rev_base) - 1.0)
        # size proxy: log price level (no shares-out on disk) — coarse but orthogonalizes scale
        import numpy as np
        size = pd.Series(np.log(last.where(last > 0)), index=last.index)
        load = pd.concat([mom.rename("momentum_252"), rev.rename("reversal_21"),
                          size.rename("size")], axis=1)
        return load.dropna(how="all")
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._factor_loadings failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# reconstructable market-wide timing series (margin leverage, media sentiment)
# --------------------------------------------------------------------------- #
def _margin_series():
    """Whole-market financing-balance-as-%-of-float, z-scored on its own trailing history.
    Market-wide → validated as a TIMER, not a cross-section. None on miss."""
    try:
        import pandas as pd
        m = store.read("china_margin", "balance")
        if m is None or m.empty or "fin_pct_float" not in m.columns:
            return None
        s = pd.to_numeric(m["fin_pct_float"], errors="coerce").dropna()
        if len(s) < 60:
            return None
        z = (s - s.rolling(252, min_periods=60).mean()) / s.rolling(252, min_periods=60).std()
        return z.dropna()
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._margin_series failed (%s)", e)
        return None


def _news_sentiment_series():
    """Blended media-sentiment z (reuses china_news_intel's own blended-tone series). Market-wide.
    None on miss."""
    try:
        import pandas as pd
        from engine import china_news_intel as cni
        s = cni._blended_tone_series()
        if s is None or len(s) < 60:
            return None
        s = pd.to_numeric(s, errors="coerce").dropna()
        z = (s - s.rolling(252, min_periods=60).mean()) / s.rolling(252, min_periods=60).std()
        return z.dropna()
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._news_sentiment_series failed (%s)", e)
        return None


def _bench_fwd_series(bench, horizon: int):
    """Bench forward h-day return stamped on the START date (leak-safe, value at d uses d->d+h)."""
    try:
        import pandas as pd
        bc = pd.to_numeric(bench, errors="coerce").dropna()
        return bc.pct_change(horizon).shift(-horizon).dropna()
    except Exception:  # noqa: BLE001
        return None


def _accruing(family: str, reason: str = "no reconstructable history") -> dict:
    return {"family": family, "status": "accruing", "tier": "display", "proven": False,
            "n_obs": 0, "by_horizon": {}, "sign_expected": _SIGN_EXPECTED.get(family),
            "reason": reason, "is_context_only": True}


def _tier_for(t_hac, q_fdr, n_obs, proven) -> str:
    """Computed tier the signal_lab consumes: scored / confirmer / pending / display."""
    if proven:
        return "scored"
    try:
        if t_hac is not None and abs(t_hac) >= 1.5 and (q_fdr is None or q_fdr <= 0.20):
            return "confirmer"
    except (TypeError, ValueError):
        pass
    return "pending" if n_obs else "display"


# --------------------------------------------------------------------------- #
# per-family validators  (call engine.validation primitives VERBATIM)
# --------------------------------------------------------------------------- #
def _hist_cross_sections(name: str, col: str) -> dict:
    """{asof(Timestamp): Series(ticker->signal)} from a data/tushare/<name>.parquet ({ticker,date,col})
    accruing-history cache (collectors/tushare_history). Empty dict on miss / token-absent (no history)."""
    out: dict = {}
    try:
        import pandas as pd
        p = config.data_dir() / "tushare" / f"{name}.parquet"
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        if df.empty or "date" not in df.columns or col not in df.columns or "ticker" not in df.columns:
            return out
        for dt, grp in df.groupby(df["date"].astype(str)):
            ser = {str(t): float(v) for t, v in zip(grp["ticker"], grp[col])
                   if isinstance(v, (int, float)) and v == v}
            if len(ser) >= 10:
                out[pd.Timestamp(dt)] = pd.Series(ser, dtype=float)
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation._hist_cross_sections(%s) failed (%s)", name, e)
    return out


def _validate_xs(V, family, xs, panel, bench, horizons, neutralize: bool = True) -> dict:
    """Generic CROSS-SECTIONAL forward-return rank-IC over a {asof: Series(ticker->signal)} grid,
    vs each name's forward CSI-300-relative return, with an optional incremental-IC neutralization
    against {momentum_252, reversal_21, size}. Leak-guarded (a date is scored only once its forward
    end is realized in the panel). Shared by valuation / fundflow / chips."""
    try:
        if not xs:
            return _accruing(family, f"{family} history empty")
        if panel is None or bench is None:
            return _accruing(family, "price panel / bench missing")
        by_h: dict = {}
        max_n = 0
        for h in horizons:
            rel = _fwd_rel_panel(panel, bench, h)
            covered = _last_covered(panel, h)
            if rel is None or covered is None:
                continue
            sig_by_date, fwd_by_date, load_by_date = {}, {}, {}
            ics = []
            for asof, sig in xs.items():
                if asof > covered:
                    continue                             # leak guard: forward end not realized
                # align the cross-section to the nearest panel row on/after asof
                idx = rel.index[rel.index >= asof]
                if len(idx) == 0:
                    continue
                row = rel.loc[idx[0]].dropna()
                if len(row) < 10:
                    continue
                ics.append(V.rank_ic(sig, row))
                sig_by_date[asof] = sig
                fwd_by_date[asof] = row
                if neutralize:
                    load = _factor_loadings(panel, idx[0])
                    if load is not None and len(load):
                        load_by_date[asof] = load
            summ = V.ic_summary(ics, periods_per_year=12)
            n = summ.get("n", 0)
            max_n = max(max_n, n)
            block = {"mean_ic": summ.get("mean_ic"), "ic_ir": summ.get("ic_ir"),
                     "t_hac": summ.get("t_hac"), "p_hac": summ.get("p_hac"),
                     "hit": summ.get("hit"), "n": n}
            if neutralize and len(load_by_date) >= 6:
                inc = V.incremental_ic(sig_by_date, fwd_by_date, load_by_date, periods_per_year=12)
                block["incremental"] = {"surviving_frac": inc.get("surviving_frac"),
                                        "ic_delta": inc.get("ic_delta")}
            by_h[str(h)] = block
        if not by_h or max_n < 6:
            return _accruing(family, f"only {max_n} cross-sections (< MIN_DATES 6)")
        return _finalize(family, by_h, max_n, _MIN_PROVEN_N)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation._validate_xs(%s) failed (%s)", family, e)
        return _accruing(family, "exception")


def _validate_timer(V, family, sig, panel, bench, horizons) -> dict:
    """Market-wide TIMER validation: regress signed forward CSI-300 return on the (lagged)
    signal level; pooled Newey-West HAC t on signal·fwd_return product per horizon. Sign of
    the mean product is the predictive sign. Leak-safe (forward stamped on signal date)."""
    try:
        if sig is None:
            return _accruing(family, "signal series missing")
        if bench is None:
            return _accruing(family, "bench missing")
        import pandas as pd
        by_h: dict = {}
        max_n = 0
        for h in horizons:
            bfwd = _bench_fwd_series(bench, h)
            if bfwd is None or bfwd.empty:
                continue
            j = pd.concat([sig.rename("s"), bfwd.rename("f")], axis=1).dropna()
            if len(j) < 8:
                continue
            # standardize signal so the product is a comparable predictive contribution
            s = (j["s"] - j["s"].mean()) / (j["s"].std(ddof=1) or 1.0)
            prod = (s * j["f"]).rename("sf")
            nw = V.newey_west_tstat(prod, lags=max(1, h - 1))
            n = nw.get("n", 0)
            max_n = max(max_n, n)
            mean = nw.get("mean")
            by_h[str(h)] = {"mean_ic": mean, "ic_ir": None,
                            "t_hac": nw.get("t"), "p_hac": nw.get("p"),
                            "hit": None, "n": n}
        if not by_h or max_n < 8:
            return _accruing(family, f"only {max_n} obs")
        return _finalize(family, by_h, max_n, _MIN_PROVEN_N_TS)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation._validate_timer(%s) failed (%s)", family, e)
        return _accruing(family, "exception")


def _finalize(family, by_h, n_obs, min_proven) -> dict:
    """Pick the headline horizon (prefer 21d), compute PROVEN gate + computed tier."""
    sign_expected = _SIGN_EXPECTED.get(family)
    head = by_h.get("21") or next(iter(by_h.values()))
    t_hac = head.get("t_hac")
    mean_ic = head.get("mean_ic")
    sign_ok = (mean_ic is not None and sign_expected is not None
               and (mean_ic > 0) == (sign_expected > 0))
    proven = bool(n_obs >= min_proven and t_hac is not None and abs(t_hac) >= 2.0 and sign_ok)
    tier = _tier_for(t_hac, head.get("p_hac"), n_obs, proven)
    status = "scored" if proven else ("validated" if tier == "confirmer" else "tested")
    return {"family": family, "status": status, "tier": tier, "proven": proven,
            "n_obs": int(n_obs), "by_horizon": by_h, "sign_expected": sign_expected,
            "sign_ok": sign_ok, "t_hac": t_hac, "mean_ic": mean_ic,
            "is_context_only": True}


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def validate_all(root=None, horizons=(5, 10, 21, 63)) -> dict:
    """Run every reconstructable China signal family through the forward-return gauntlet.

    Returns (and writes to data/china_validation/scorecard.json) the china_validation.v1
    scorecard: {schema, generated_utc, is_context_only, fdr_alpha, families:{name:{...}}}.
    Each family carries status/tier/proven + a by_horizon block of {mean_ic,t_hac,p_hac,hit,n}.
    Benjamini-Hochberg q across families' headline p_hac sets each family's q_fdr. A trial-ledger
    budget is logged so any downstream DSR is honestly counted. Degrades family-by-family to
    `accruing`; NEVER raises."""
    try:
        import engine.validation as V
    except Exception as e:  # noqa: BLE001
        log.error("china_validation: cannot import engine.validation (%s)", e)
        return {"schema": SCHEMA, "is_context_only": True, "families": {},
                "fdr_alpha": FDR_ALPHA, "error": "validation primitives unavailable"}

    panel = _panel()
    bench = _bench_close()

    families: dict = {}
    try:
        families["valuation"] = _validate_xs(V, "valuation", _valuation_cross_sections(),
                                             panel, bench, horizons)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation valuation family failed (%s)", e)
        families["valuation"] = _accruing("valuation", "exception")
    # Tushare GATED cross-sectional legs (validate from the accruing/backfilled history; degrade to
    # `accruing` when the token / history is absent — e.g. keyless CI before the secret is set).
    try:
        families["fundflow"] = _validate_xs(V, "fundflow", _hist_cross_sections("flow_hist", "flow"),
                                            panel, bench, horizons)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation fundflow family failed (%s)", e)
        families["fundflow"] = _accruing("fundflow", "exception")
    try:
        families["chips"] = _validate_xs(V, "chips", _hist_cross_sections("chips_hist", "winner"),
                                         panel, bench, horizons)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation chips family failed (%s)", e)
        families["chips"] = _accruing("chips", "exception")
    try:
        families["margin"] = _validate_timer(V, "margin", _margin_series(), panel, bench, horizons)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation margin family failed (%s)", e)
        families["margin"] = _accruing("margin", "exception")
    try:
        families["news_sentiment"] = _validate_timer(
            V, "news_sentiment", _news_sentiment_series(), panel, bench, horizons)
    except Exception as e:  # noqa: BLE001
        log.error("china_validation news_sentiment family failed (%s)", e)
        families["news_sentiment"] = _accruing("news_sentiment", "exception")

    # FDR across families on the headline (21d, else first) p_hac
    try:
        pvals = {}
        for name, fam in families.items():
            by_h = fam.get("by_horizon") or {}
            head = by_h.get("21") or (next(iter(by_h.values())) if by_h else {})
            p = head.get("p_hac")
            if p is not None:
                pvals[name] = p
        bh = V.benjamini_hochberg(pvals, alpha=FDR_ALPHA) if pvals else {}
        for name, fam in families.items():
            q = (bh.get(name) or {}).get("q") if bh else None
            fam["q_fdr"] = q
            # re-gate PROVEN with the FDR q now available
            if fam.get("proven") and q is not None and q > FDR_ALPHA:
                fam["proven"] = False
                fam["status"] = "tested"
                fam["tier"] = _tier_for(fam.get("t_hac"), head.get("p_hac"),
                                        fam.get("n_obs", 0), False)
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation FDR step failed (%s)", e)

    # honest multiple-testing budget (#families × #horizons cells)
    try:
        from engine.trial_ledger import TrialLedger
        led = TrialLedger()
        led.log_declared_budget(n=max(1, len(families) * len(horizons)),
                                family="china_validation",
                                reason="china signal × horizon predictive grid")
    except Exception as e:  # noqa: BLE001
        log.debug("china_validation trial-ledger budget skipped (%s)", e)

    out = {"schema": SCHEMA, "is_context_only": True,
           "generated_utc": datetime.now(timezone.utc).isoformat(),
           "fdr_alpha": FDR_ALPHA, "horizons": list(horizons), "families": families}
    try:
        p = config.data_dir() / "china_validation" / "scorecard.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.error("china_validation: could not write scorecard (%s)", e)
    return out


def load_scorecard() -> dict | None:
    """Read the last-written scorecard (for signal_lab / pages). None on miss. Never raises."""
    try:
        p = config.data_dir() / "china_validation" / "scorecard.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
