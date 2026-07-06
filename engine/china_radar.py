"""China Divergence Radar — management-independent demand/policy signal vs sector price.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS · NO VALIDATED EDGE (Phase-0 candidate). The China
build of the narrative-radar idea: for a curated set of (macro/policy/flow signal → the
sector it transmits to) pairs, compare the SIGNAL direction (a free, forward-looking,
management-independent indicator already on disk) against the sector ETF's relative
strength vs CSI 300. A 2×2 kernel flags:

  POSITIVE divergence — support IMPROVING but price LAGGING  (potential catch-up)
  NEGATIVE divergence — support FADING but price LEADING     (potential vulnerability)
  IN LINE (silent)    — signal and price agree               (confirming, no edge)

Winsorised z, a falsifiable per-pair hypothesis seed, and a ledger that accrues on the
fire date (engine/china_radar_ledger.py). Nothing here is scored into an allocation.
See research/CHINA_INTEL_POWERHOUSE.md §4.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import store

log = logging.getLogger(__name__)

SCHEMA = "china_radar.v1"
BENCH = "510300.SS"   # CSI 300 ETF
_WINSOR = 3.0


def _winz(x: float) -> float:
    return max(-_WINSOR, min(_WINSOR, x))


# --------------------------------------------------------------------------- #
# price relative strength: sector ETF 63d return minus benchmark, + its z
# --------------------------------------------------------------------------- #
def _price_rs(etf: str, lookback: int = 63):
    try:
        import numpy as np
        import pandas as pd
        a = store.read("china", etf)
        b = store.read("china", BENCH)
        if a is None or b is None or "close" not in a.columns or "close" not in b.columns:
            return None, None
        ca, cb = a["close"].dropna(), b["close"].dropna()
        rel = (ca / cb.reindex(ca.index).ffill()).dropna()
        if len(rel) < lookback + 60:
            return None, None
        roll = rel.pct_change(lookback).dropna()    # rolling 63d relative return
        cur = float(roll.iloc[-1])
        hist = roll.tail(504)
        mu, sd = float(hist.mean()), float(hist.std(ddof=0))
        z = _winz((cur - mu) / sd) if sd > 1e-9 else 0.0
        return round(cur * 100, 2), round(z, 2)
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar price_rs %s failed (%s)", etf, e)
        return None, None


# --------------------------------------------------------------------------- #
# signal-A computations — each returns {value, dir(+1/-1/0), strength(0..1), detail}
# All are free, forward-looking, management-INDEPENDENT macro/policy/flow indicators.
# --------------------------------------------------------------------------- #
def _sig_credit_impulse():
    try:
        import pandas as pd
        from engine import canon
        df = store.read("china_credit", "tsf")
        if df is None or "tsf_total" not in df.columns:
            return None
        s = pd.to_numeric(df["tsf_total"], errors="coerce").dropna()
        if s.rolling(12).sum().dropna().shape[0] < 18:
            return None
        # Credit-impulse LEVEL (1st-derivative) via the canon (audit #12) — the "6m chg of
        # the 12m sum". This is a DIFFERENT series than china_strategies' credit-impulse
        # ACCEL (2nd-derivative); the shared "credit impulse" label used to hide that.
        # Byte-identical to the prior local.
        impulse = canon.credit_impulse_level(s).dropna()
        if impulse.empty:
            return None
        cur = float(impulse.iloc[-1])
        sd = float(impulse.tail(36).std(ddof=0))
        strength = min(1.0, abs(cur) / (2 * sd)) if sd > 1e-9 else 0.4
        return {"value": round(cur * 100, 1), "dir": 1 if cur > 0 else (-1 if cur < 0 else 0),
                "strength": round(strength, 2),
                "detail_en": f"TSF impulse {cur*100:+.1f}% (6m chg of 12m sum)",
                "detail_zh": f"社融脉冲 {cur*100:+.1f}%（12月滚动和的6月变化）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_pboc_easing():
    try:
        import pandas as pd
        lpr = store.read("china_macro", "lpr_rate")
        rrr = store.read("china_macro", "rrr")
        lpr_chg = 0.0
        if lpr is not None and "lpr_1y" in lpr.columns:
            s = lpr["lpr_1y"].dropna()
            cutoff = s.index.max() - pd.Timedelta(days=365)
            past = s[s.index <= cutoff]
            if not past.empty:
                lpr_chg = float(s.iloc[-1] - past.iloc[-1])
        rrr_chg = 0.0
        if rrr is not None and "rrr_change" in rrr.columns:
            r = rrr["rrr_change"].dropna()
            cutoff = r.index.max() - pd.Timedelta(days=365)
            rrr_chg = float(r[r.index >= cutoff].sum())
        easing = -(lpr_chg * 100) - (rrr_chg * 20)   # bp + RRR-pp scaled; >0 = easing
        strength = min(1.0, abs(easing) / 40.0)
        return {"value": round(easing, 1), "dir": 1 if easing > 1 else (-1 if easing < -1 else 0),
                "strength": round(strength, 2),
                "detail_en": f"12m easing score {easing:+.0f} (LPR {lpr_chg*100:+.0f}bp, RRR {rrr_chg:+.2f}pp)",
                "detail_zh": f"12月宽松分 {easing:+.0f}（LPR {lpr_chg*100:+.0f}基点，准备金 {rrr_chg:+.2f}pp）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_pmi():
    try:
        import pandas as pd
        df = store.read("china_macro", "pmi")
        if df is None or "pmi_mfg" not in df.columns:
            return None
        s = pd.to_numeric(df["pmi_mfg"], errors="coerce").dropna()
        if len(s) < 6:
            return None
        cur = float(s.iloc[-1])
        chg3 = float(s.iloc[-1] - s.iloc[-4]) if len(s) > 4 else 0.0
        above = cur - 50.0
        strength = min(1.0, (abs(above) + abs(chg3)) / 2.0)
        d = 1 if (above > 0 and chg3 >= 0) else (-1 if (above < 0 and chg3 <= 0) else (1 if chg3 > 0 else -1))
        return {"value": round(cur, 1), "dir": d, "strength": round(strength, 2),
                "detail_en": f"Mfg PMI {cur:.1f} ({chg3:+.1f} 3m)",
                "detail_zh": f"制造业PMI {cur:.1f}（3月{chg3:+.1f}）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_ppi():
    try:
        import pandas as pd
        df = store.read("china_macro", "ppi")
        if df is None or "ppi_yoy" not in df.columns:
            return None
        s = pd.to_numeric(df["ppi_yoy"], errors="coerce").dropna()
        if len(s) < 6:
            return None
        # data-quality guard: China PPI YoY is slow-moving. A >2.5pp single-month jump (parse
        # explosion) OR a >5pp swing over the trailing 6 months (vintage/base-effect artifact —
        # the implausible -1.9→+3.9 reflation the audit flagged) is data-suspect → skip, don't fire.
        if abs(float(s.iloc[-1]) - float(s.iloc[-2])) > 2.5:
            return None
        win6 = s.tail(6)
        if float(win6.max() - win6.min()) > 5.0:
            return None
        cur = float(s.iloc[-1])
        chg3 = float(s.iloc[-1] - s.iloc[-4])
        strength = min(1.0, abs(chg3) / 2.0)
        return {"value": round(cur, 1), "dir": 1 if chg3 > 0 else (-1 if chg3 < 0 else 0),
                "strength": round(strength, 2),
                "detail_en": f"PPI YoY {cur:+.1f}% ({chg3:+.1f} 3m, reflation tilt)",
                "detail_zh": f"PPI同比 {cur:+.1f}%（3月{chg3:+.1f}，再通胀倾向）"}
    except Exception:  # noqa: BLE001
        return None


def _sig_southbound():
    try:
        import pandas as pd
        df = store.read("china_connect", "southbound")
        if df is None or "net" not in df.columns:
            return None
        s = pd.to_numeric(df["net"], errors="coerce").dropna()
        if len(s) < 80:
            return None
        flow20 = s.rolling(20).sum().dropna()
        cur = float(flow20.iloc[-1])
        mu, sd = float(flow20.tail(252).mean()), float(flow20.tail(252).std(ddof=0))
        z = _winz((cur - mu) / sd) if sd > 1e-9 else 0.0
        return {"value": round(cur / 1e8, 1) if abs(cur) > 1e6 else round(cur, 1),
                "dir": 1 if z > 0.3 else (-1 if z < -0.3 else 0),
                "strength": round(min(1.0, abs(z) / 2.0), 2),
                "detail_en": f"Southbound 20d flow z {z:+.2f}",
                "detail_zh": f"南向20日净流入 z {z:+.2f}"}
    except Exception:  # noqa: BLE001
        return None


def _sector_flow_boards():
    """{board_name: net_amount_rate} for 东财 INDUSTRY boards (GATED Tushare moneyflow_ind_dc snapshot).
    {} when the token / cache is absent. Sector net-flow rate (% of turnover) for the latest day."""
    out: dict = {}
    try:
        import pandas as pd
        from lib import config
        p = config.data_dir() / "tushare" / "moneyflow_sector.parquet"
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        ind = df[df.get("content_type") == "行业"] if "content_type" in df.columns else df
        for _, r in ind.iterrows():
            nm = str(r.get("name") or "")
            v = r.get("net_amount_rate")
            if nm and v is not None and v == v:
                out[nm] = float(v)
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar sector-flow boards failed (%s)", e)
    return out


def _sector_flow_signal(board: str, boards: dict):
    """signal-A from a sector's own 东财 net-flow rate (daily). Deadbanded so a small move stays
    silent. None when the board is absent."""
    rate = boards.get(board)
    if rate is None:
        return None
    d = 1 if rate > 1.0 else (-1 if rate < -1.0 else 0)
    return {"value": round(rate, 2), "dir": d, "strength": round(min(1.0, abs(rate) / 3.0), 2),
            "detail_en": f"Sector net-flow {rate:+.1f}% (东财 board, daily)",
            "detail_zh": f"板块净流入 {rate:+.1f}%（东财行业板块，当日）"}


# Sector ETF → 东财 industry board (exact name) for the sector-flow radar pairs. Reuses the radar's
# existing sector ETFs so the price-RS leg is identical.
_SECTOR_FLOW_MAP = [
    ("512800.SS", "Banks", "银行", "银行"),
    ("512200.SS", "Real estate", "房地产", "房地产"),
    ("512880.SS", "Brokers", "券商", "证券Ⅱ"),
    ("512400.SS", "Nonferrous metals", "有色金属", "有色金属"),
    ("515030.SS", "New-energy vehicle", "新能源车", "锂电池"),
    ("512760.SS", "Semiconductors", "半导体", "半导体"),
    ("512660.SS", "Defense", "国防军工", "国防军工"),
    ("515220.SS", "Coal", "煤炭", "煤炭"),
]
_SECTOR_FLOW_THESIS = ("Sector smart-money net-flow tends to lead the sector's price when it "
                       "diverges from current relative strength.")


# --------------------------------------------------------------------------- #
# VENUE DIVERGENCE FAMILY
# Three cross-venue pairs: A/H premium z, offshore-ETF-vs-onshore gap, southbound intensity.
# Each emits a row tagged family="venue" so future ledger slices can filter.
# Ledger accrual rides the EXISTING radar ledger (same path, same grading).
# --------------------------------------------------------------------------- #

def _sig_ah_premium_z():
    """Signal-A+B: A/H premium z (signal-A) vs CSI 300 own-history z (signal-B).

    A genuine TWO-LEG pair: fires ONLY when the premium z and onshore price z disagree
    (opposite signs, both |z| ≥ 1.0). When both agree the divergence is in_line.

    Uses data/hk_ah_official/ah_premium.parquet (reconstructed liquid-10 daily index, col
    `hsahp`). Falls back to ah_spot.parquet if ah_premium is shallow or missing.
    CSI 300 own-history: data/china/510300.SS.parquet 63d return z vs its own 252-day history.

    DATA CAVEAT: ah_premium reconstructs CNY-equivalent H prices from USDCNY/USDHKD FX; the
    level embeds FX moves. We report the z of the daily LEVEL series (not FX-stripped).
    """
    try:
        import numpy as np
        import pandas as pd
        from lib import store

        df = store.read("hk_ah_official", "ah_premium")
        if df is None or "hsahp" not in df.columns:
            # fall back to the accrued spot series (shallow but real)
            df = store.read("hk_ah_official", "ah_spot")
        if df is None or "hsahp" not in df.columns:
            return None
        s = pd.to_numeric(df["hsahp"], errors="coerce").dropna().sort_index()
        if len(s) < 60:
            return None
        cur = float(s.iloc[-1])
        # signal-A: premium z vs trailing 1y (252 trading days, or all available if < 252)
        window = s.tail(252)
        mu, sd = float(window.mean()), float(window.std(ddof=0))
        z = _winz((cur - mu) / sd) if sd > 1e-9 else 0.0
        asof = s.index[-1].date()

        # signal-B: CSI 300 own-history z (63d return z vs its own 252-day trailing window)
        csi = store.read("china", "510300.SS")
        csi_z = None
        if csi is not None and "close" in csi.columns:
            csi_close = csi["close"].dropna().sort_index()
            if len(csi_close) >= 252 + 63:
                csi_ret63 = csi_close.pct_change(63).dropna()
                csi_cur = float(csi_ret63.iloc[-1])
                csi_hist = csi_ret63.tail(252)
                csi_mu, csi_sd = float(csi_hist.mean()), float(csi_hist.std(ddof=0))
                csi_z = _winz((csi_cur - csi_mu) / csi_sd) if csi_sd > 1e-9 else 0.0

        # TWO-LEG divergence: fire ONLY when legs DISAGREE and both exceed |z| >= 1.0
        # premium_z > +1.0 AND csi_z < -1.0 → premium bidding up A-shares while onshore price lags
        # premium_z < -1.0 AND csi_z > +1.0 → premium collapsed while onshore price still elevated
        if csi_z is None:
            # can't compute signal-B → fall back to single-leg with threshold 1.0
            d = 1 if z > 1.0 else (-1 if z < -1.0 else 0)
        elif z > 1.0 and csi_z < -1.0:
            d = 1   # premium elevated, onshore price lagging
        elif z < -1.0 and csi_z > 1.0:
            d = -1  # premium compressed, onshore price still leading
        else:
            d = 0   # legs agree or within noise floor → in_line

        return {
            "value": round(cur, 2), "z": round(z, 2), "csi_z": round(csi_z, 2) if csi_z is not None else None,
            "dir": d,
            "strength": round(min(1.0, abs(z) / 2.0), 2),
            "data_asof": str(asof),
            "detail_en": (f"A/H premium {cur:.1f}% (z {z:+.2f} vs 1y history); "
                          f"CSI 300 price z {csi_z:+.2f}" if csi_z is not None else
                          f"A/H premium {cur:.1f}% (z {z:+.2f} vs 1y history); CSI 300 z unavailable"),
            "detail_zh": (f"A/H溢价 {cur:.1f}%（z {z:+.2f}，相对1年历史）；"
                          f"沪深300价格z {csi_z:+.2f}" if csi_z is not None else
                          f"A/H溢价 {cur:.1f}%（z {z:+.2f}）；沪深300z不可用"),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar _sig_ah_premium_z failed (%s)", e)
        return None


def _sig_offshore_etf_gap(lookback_days: int = 5):
    """Signal-A: equal-weight offshore ETF total-return gap vs CSI 300 onshore.

    Offshore basket: KWEB, MCHI, CQQQ (US-listed offshore China ETFs).
    NOTE: ASHR and GXC are EXCLUDED — they hold A-shares directly, so they track onshore
    price action rather than offshore investor sentiment. FXI is also excluded per brief scope
    (brief specifies KWEB/MCHI/CQQQ only).

    Data: data/yahoo/*.parquet (close col = dividend-adjusted total return per repo memory).
    Onshore benchmark: data/china/510300.SS.parquet (close col, also dividend-adjusted).

    FX CAVEAT: the gap embeds USDCNY moves — a weak CNY inflates the USD return of offshore
    ETFs relative to onshore CNY prices. We do NOT silently adjust; the hypothesis text states
    this. If data/china_pboc/cny_fix.parquet is fresh (within 5 trading days) we compute and
    report a FX-adjusted gap alongside as `gap_fx_adj` in the detail, but the primary z and
    direction use the raw gap.

    Two lookbacks (5d and 20d); we fire on the stronger z.
    Minimum 252 trading days of shared history required to compute a stable 1y z.
    """
    try:
        import numpy as np
        import pandas as pd
        from lib import store, config

        # Offshore basket
        OFFSHORE = ["KWEB", "MCHI", "CQQQ"]
        csi = store.read("china", "510300.SS")
        if csi is None or "close" not in csi.columns:
            return None
        csi_close = csi["close"].dropna().sort_index()

        etf_series = []
        etf_used = []
        for ticker in OFFSHORE:
            df = store.read("yahoo", ticker)
            if df is None:
                continue
            col = "close" if "close" in df.columns else "close_price"
            if col not in df.columns:
                continue
            s = df[col].dropna().sort_index()
            etf_series.append(s)
            etf_used.append(ticker)

        if not etf_series:
            return None

        # Align all series to a common date index
        combined = pd.concat(etf_series, axis=1, keys=etf_used, sort=True)
        if len(combined.dropna(how="all")) < 252 + 20:
            return None

        # Compute trailing returns for both lookbacks — EQUAL-WEIGHT IN RETURN SPACE:
        # average each ETF's pct_change, then diff with onshore. This gives each ETF
        # equal weight regardless of price level (KWEB ~$20 vs MCHI/CQQQ ~$40-50).
        results = []
        for lb in (5, 20):
            ret_frame = combined.pct_change(lb).dropna(how="all")
            off_ret = ret_frame.mean(axis=1).dropna()
            on_ret = csi_close.pct_change(lb).dropna()
            gap = (off_ret - on_ret).dropna()
            if len(gap) < 252:
                continue
            cur_gap = float(gap.iloc[-1])
            hist = gap.tail(252)
            mu, sd = float(hist.mean()), float(hist.std(ddof=0))
            z = _winz((cur_gap - mu) / sd) if sd > 1e-9 else 0.0
            results.append((lb, cur_gap, z, gap))

        if not results:
            return None

        # Use the lookback with the stronger |z|
        best = max(results, key=lambda x: abs(x[2]))
        lb, cur_gap, z, gap_series = best

        # Optional FX-adjustment report (informational only — does not change direction signal)
        fx_note = ""
        fx_note_zh = ""
        try:
            from pathlib import Path
            cny_path = config.data_dir() / "china_pboc" / "cny_fix.parquet"
            if cny_path.exists():
                cny_df = pd.read_parquet(cny_path)
                cny_df.index = pd.to_datetime(cny_df.index)
                cny_s = cny_df["usd_cny"].dropna().sort_index()
                if len(cny_s) >= lb + 1:
                    cny_chg = float(cny_s.iloc[-1] / cny_s.iloc[-1 - lb] - 1.0)
                    # FX-adjusted offshore return = raw equal-weight return - CNY appreciation (approx)
                    ret_frame_fx = combined.pct_change(lb).dropna(how="all")
                    off_ret_raw = float(ret_frame_fx.mean(axis=1).dropna().iloc[-1])
                    off_ret_adj = off_ret_raw - cny_chg
                    on_ret_last = float(csi_close.pct_change(lb).dropna().iloc[-1])
                    gap_adj = off_ret_adj - on_ret_last
                    staleness = (pd.Timestamp.today() - cny_s.index[-1]).days
                    if staleness <= 7:
                        fx_note = f"; FX-adj gap {gap_adj*100:+.1f}% (CNY {cny_chg*100:+.2f}%)"
                        fx_note_zh = f"；汇率调整后差价 {gap_adj*100:+.1f}%（人民币 {cny_chg*100:+.2f}%）"
        except Exception:  # noqa: BLE001
            pass

        asof = gap_series.index[-1].date() if len(gap_series) > 0 else combined.index[-1].date()
        d = 1 if z > 1.0 else (-1 if z < -1.0 else 0)
        etf_str = "/".join(etf_used)
        composition_note = (
            " Composition note: basket is tech/internet-tilted (KWEB=internet, CQQQ=tech-heavy) "
            "vs CSI 300's financials tilt — gap partly reflects sector rotation, not pure venue sentiment."
        )
        return {
            "value": round(cur_gap * 100, 2), "z": round(z, 2), "dir": d,
            "strength": round(min(1.0, abs(z) / 2.0), 2),
            "lookback_days": lb, "etf_used": etf_used,
            "data_asof": str(asof),
            "detail_en": (f"Offshore ({etf_str}) {lb}d equal-weight ret gap vs CSI300: "
                          f"{cur_gap*100:+.2f}% (z {z:+.2f}){fx_note}. "
                          f"FX note: gap embeds USDCNY moves — see FX-adj if available.{composition_note}"),
            "detail_zh": (f"离岸ETF({etf_str}) {lb}日等权收益差 vs 沪深300: "
                          f"{cur_gap*100:+.2f}%（z {z:+.2f}）{fx_note_zh}。"
                          f"注：差值包含人民币汇率影响；篮子偏科技/互联网，与沪深300金融偏重有差异。"),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar _sig_offshore_etf_gap failed (%s)", e)
        return None


def _sig_southbound_vs_hk():
    """Signal-A: southbound flow intensity z vs HSCEI relative strength.

    Southbound: data/china_connect/southbound.parquet, `net` col (RMB mn), 20d rolling sum z
    vs trailing 1y. Uses the same computation as the existing _sig_southbound() used for the
    sector-pair radar, but targets the HSCEI (hk/_HSCE) directly rather than a single sector.

    HK leg (signal-B proxy): HSCEI 20d return z vs its own 1y history. This is the price-leg
    the divergence tests — we compare flow intensity direction vs HSCEI price momentum direction.

    NOTE: northbound Connect was suspended 2024-08 (R-6); this pair uses SOUTHBOUND only.
    HSCEI (_HSCE) is in the hk store with clean history back to 1993.
    """
    try:
        import numpy as np
        import pandas as pd
        from lib import store

        # Southbound flow z (20d sum)
        sb = store.read("china_connect", "southbound")
        if sb is None or "net" not in sb.columns:
            return None
        s_net = pd.to_numeric(sb["net"], errors="coerce").dropna().sort_index()
        if len(s_net) < 80:
            return None
        flow20 = s_net.rolling(20).sum().dropna()
        if len(flow20) < 252:
            return None
        cur_flow = float(flow20.iloc[-1])
        mu_f, sd_f = float(flow20.tail(252).mean()), float(flow20.tail(252).std(ddof=0))
        flow_z = _winz((cur_flow - mu_f) / sd_f) if sd_f > 1e-9 else 0.0

        # HSCEI (signal-B / price leg)
        hsce = store.read("hk", "_HSCE")
        if hsce is None or "close" not in hsce.columns:
            return None
        h_close = hsce["close"].dropna().sort_index()
        if len(h_close) < 252 + 20:
            return None
        hk_ret20 = h_close.pct_change(20).dropna()
        cur_hk = float(hk_ret20.iloc[-1])
        mu_h, sd_h = float(hk_ret20.tail(252).mean()), float(hk_ret20.tail(252).std(ddof=0))
        hk_z = _winz((cur_hk - mu_h) / sd_h) if sd_h > 1e-9 else 0.0

        # Use flow_z as the signal direction; hk_z as the price-leg z
        d = 1 if flow_z > 1.0 else (-1 if flow_z < -1.0 else 0)
        flow_asof = s_net.index[-1].date()
        hk_asof = h_close.index[-1].date()
        data_asof = str(min(flow_asof, hk_asof))
        return {
            "value": round(cur_flow / 1e8, 1),
            "z": round(flow_z, 2),
            "hk_z": round(hk_z, 2),
            "dir": d,
            "strength": round(min(1.0, abs(flow_z) / 2.0), 2),
            "data_asof": data_asof,
            "detail_en": (f"Southbound 20d flow z {flow_z:+.2f}; "
                          f"HSCEI 20d ret z {hk_z:+.2f}"),
            "detail_zh": (f"南向20日净流 z {flow_z:+.2f}；"
                          f"恒生国企20日收益 z {hk_z:+.2f}"),
            # expose hk_z for the divergence kernel (used instead of price_rs_z for this pair)
            "_hk_z": hk_z,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar _sig_southbound_vs_hk failed (%s)", e)
        return None


# Venue pair definitions: (signal_key, signal_fn, signal_en, signal_zh,
#                          proxy_en, proxy_zh, thesis)
# Each entry is resolved in scan() with special logic for the venue-pair divergence kernel.
# "proxy" = what the signal is measured against (not a sector ETF, but a cross-venue price leg).
_VENUE_PAIRS = [
    (
        "venue_ah_premium",
        _sig_ah_premium_z,
        "A/H premium z",
        "A/H溢价z值",
        "CSI 300 (onshore)",
        "沪深300（境内）",
        ("A/H premium z vs CSI 300 price z — a two-leg pair. Premium widening (A-shares bid vs H) "
         "while CSI 300 price z is lagging its own history suggests onshore-relative demand has not yet "
         "been confirmed by price. Fires only when both legs disagree and |z| >= 1.0. "
         "DATA NOTE: premium embeds USDCNY/USDHKD FX, not FX-stripped. Direction unproven — accruing as Phase-0 candidate."),
    ),
    (
        "venue_offshore_gap",
        _sig_offshore_etf_gap,
        "Offshore ETF gap (KWEB/MCHI/CQQQ)",
        "离岸ETF差价(KWEB/MCHI/CQQQ)",
        "CSI 300 (onshore)",
        "沪深300（境内）",
        ("Offshore China ETF basket (KWEB/MCHI/CQQQ — US-listed offshore listings; ASHR/GXC "
         "excluded as they hold A-shares directly) total-return equal-weight gap vs CSI 300. "
         "A strongly positive gap (offshore outperforming) while onshore lags = offshore sentiment "
         "leading. FX caveat: gap embeds USDCNY. Composition note: basket is tech/internet-tilted "
         "(KWEB=internet, CQQQ=tech-heavy) vs CSI 300's financials tilt — gap partly reflects sector "
         "rotation, not pure venue sentiment. Hypothesis: sustained offshore leadership tends to attract "
         "onshore catch-up over ~3 months."),
    ),
    (
        "venue_southbound",
        _sig_southbound_vs_hk,
        "Southbound flow vs HSCEI",
        "南向资金 vs 恒生国企",
        "HSCEI (HK)",
        "恒生国企指数（港股）",
        ("Southbound Connect 20d flow intensity z vs HSCEI 20d momentum z. Strong inflow "
         "(high flow z) while HSCEI price lags (low hk_z) = mainland capital deploying into "
         "HK before local price confirms. NOTE: Northbound suspended 2024-08 (R-6); "
         "southbound remains live. Hypothesis: HSCEI should outperform over ~3 months when "
         "southbound flow leads price."),
    ),
]


# (signal_key, signal_fn, signal_en, signal_zh, [(etf, sector_en, sector_zh)...], thesis)
_PAIRS = [
    ("credit_impulse", _sig_credit_impulse, "Credit impulse (TSF)", "信用脉冲(社融)",
     [("512800.SS", "Banks", "银行"), ("512200.SS", "Real estate", "房地产")],
     "Credit impulse leads cyclicals/financials by 2-4 quarters."),
    ("pboc_easing", _sig_pboc_easing, "PBoC easing", "央行宽松",
     [("512880.SS", "Brokers", "券商"), ("512200.SS", "Real estate", "房地产")],
     "Easing (RRR/LPR cuts) lifts rate-sensitive brokers + property."),
    ("pmi", _sig_pmi, "Mfg PMI", "制造业PMI",
     [("512400.SS", "Nonferrous metals", "有色金属"), ("515030.SS", "New-energy vehicle", "新能源车")],
     "Manufacturing expansion supports industrial cyclicals."),
    ("ppi", _sig_ppi, "PPI reflation", "PPI再通胀",
     [("512400.SS", "Nonferrous metals", "有色金属"), ("515220.SS", "Coal", "煤炭")],
     "PPI inflecting up reflates upstream-resource margins."),
    ("southbound", _sig_southbound, "Southbound flow", "南向资金",
     [("512760.SS", "Semiconductors", "半导体"), ("512660.SS", "Defense", "国防军工")],
     "Sustained southbound inflow tends to lead the names it chases."),
]


def _divergence(sig: dict, rs_pct, rs_z):
    """2×2 verdict from signal direction vs price relative strength. PURE.

    price direction is taken from rs_z (the sector's OWN-history-normalized relative return)
    with a deadband, NOT the raw 63d rel return — otherwise in a broad-underperformance regime
    every sector reads pdir=-1 and the radar is structurally one-sided (the 6/6-positive bug)."""
    if sig is None or sig.get("dir", 0) == 0 or rs_z is None:
        return "in_line", 0.0
    sdir = sig["dir"]
    z = rs_z or 0.0
    pdir = 1 if z > 0.3 else (-1 if z < -0.3 else 0)   # deadband → mild moves stay silent
    if pdir == 0:
        return "in_line", 0.0
    strength = round(sig.get("strength", 0.0) * min(1.0, abs(z) / 2.0), 3)
    if sdir > 0 and pdir < 0:
        return "positive", strength      # support improving, price lagging
    if sdir < 0 and pdir > 0:
        return "negative", strength      # support fading, price extended
    return "in_line", strength


def _ledger_reliability():
    """(by_pair, by_signal) → {key: {n_resolved, hits, hit_rate}} from the falsification
    ledger. Both {} when nothing has matured (n_resolved 0). Lazy + degrade-to-empty."""
    by_pair, by_signal = {}, {}
    try:
        from engine import china_radar_ledger as rl
        tr = rl.track_record()
        for r in (tr or {}).get("rows", []):
            if r.get("status") not in ("hit", "miss"):
                continue
            hit = 1 if r["status"] == "hit" else 0
            for d, k in ((by_pair, r.get("pair")), (by_signal, r.get("signal_key"))):
                if not k:
                    continue
                cur = d.setdefault(k, {"n_resolved": 0, "hits": 0})
                cur["n_resolved"] += 1
                cur["hits"] += hit
        for d in (by_pair, by_signal):
            for v in d.values():
                v["hit_rate"] = round(v["hits"] / v["n_resolved"], 2) if v["n_resolved"] else None
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar reliability unavailable (%s)", e)
    return by_pair, by_signal


def _candidates(etf, sign, conv_map, n=3):
    """Per-divergence candidate names — the basket members the divergence implicates, joined to
    alt-data convergence (top by accumulation for positive, bottom for negative). Bilingual why."""
    try:
        from engine import china_basket_spine as sp
        bids = sp.etf_to_basket().get(etf, [])
        members = []
        for b in bids:
            members += sp.basket_members(b)
        members = list(dict.fromkeys(members))
        cand = [(t, conv_map[t]) for t in members if t in conv_map]
        if not cand:
            return []
        cand.sort(key=lambda x: x[1]["convergence"], reverse=(sign == "positive"))
        out = []
        for t, info in cand[:n]:
            acc = info.get("side") == "accumulate"
            out.append({
                "ticker": t, "name": info.get("name", t),
                "convergence": info.get("convergence"),
                "why_en": f"{'leads' if sign == 'positive' else 'lags'} cohort · alt-data {info.get('side','')}",
                "why_zh": f"{'领先' if sign == 'positive' else '落后'}同业 · 另类数据{'吸筹' if acc else '派发'}",
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def _build_row(cv, key, sen, szh, etf, sec_en, sec_zh, sig, thesis,
               by_pair, by_signal, conv_map) -> dict:
    """One radar row: signal-A direction vs the sector ETF's price RS → divergence verdict,
    conviction-scored (strength × ledger reliability) with falsifiable hypothesis + candidates.
    Shared by the macro/policy/flow pairs AND the per-sector sector-flow pairs. PURE-ish (reads
    price + ledger + convergence)."""
    rs_pct, rs_z = _price_rs(etf)
    sign, strength = _divergence(sig, rs_pct, rs_z)
    pair = f"{key}->{etf}"
    if sign == "positive":
        hyp_en = f"If {sen} is leading, {sec_en} should outperform CSI 300 over ~3 months."
        hyp_zh = f"若{szh}领先，{sec_zh}未来约3个月应跑赢沪深300。"
    elif sign == "negative":
        hyp_en = f"If {sen} is fading, {sec_en}'s lead over CSI 300 should fade over ~3 months."
        hyp_zh = f"若{szh}转弱，{sec_zh}相对沪深300的领先应在约3个月内消退。"
    else:
        hyp_en = hyp_zh = ""
    # reliability: per-pair, fall back to per-signal, else unproven
    rel = by_pair.get(pair) or by_signal.get(key) or {}
    n_res = rel.get("n_resolved", 0)
    hr = rel.get("hit_rate")
    basis = ("pair" if pair in by_pair else ("signal_key" if key in by_signal else "unproven"))
    if n_res >= 3 and hr is not None:
        # proven-good rewarded up to 1.5×; proven-BAD (hr→0) collapses toward 0,
        # so a demonstrably-falsified signal drops out of Moderate+ (not floored at 0.5×)
        rel_factor = max(0.15, min(1.5, 1.5 * hr))
    else:
        rel_factor = 1.0
        basis = "unproven"
    conviction100 = cv.to_100(strength * rel_factor) if sign != "in_line" else 0
    return {
        "pair": pair, "signal_key": key,
        "signal_en": sen, "signal_zh": szh,
        "sector": sec_en, "sector_etf": etf, "sector_en": sec_en, "sector_zh": sec_zh,
        "sign": sign, "strength": strength, "conviction100": conviction100,
        "signal_value": sig.get("value"), "signal_dir": sig.get("dir"),
        "signal_detail_en": sig.get("detail_en"), "signal_detail_zh": sig.get("detail_zh"),
        "price_rs": rs_pct, "price_rs_z": rs_z,
        "reliability": {"hit_rate": hr, "n_resolved": int(n_res), "basis": basis},
        "candidates": _candidates(etf, sign, conv_map) if sign != "in_line" else [],
        "thesis": thesis, "hypothesis_en": hyp_en, "hypothesis_zh": hyp_zh,
    }


def _build_venue_row(cv, key, sen, szh, proxy_en, proxy_zh, sig, thesis,
                     by_pair, by_signal) -> dict | None:
    """Build one venue-family radar row.

    Venue pairs differ from sector pairs: there is no single sector ETF price-RS leg.
    Instead:
    - venue_ah_premium: divergence = premium z direction vs 0 (CSI 300 is the benchmark
      itself, so we treat it as an independent regime signal; fire when |premium_z| > 0.4
      — the threshold is encoded in _sig_ah_premium_z itself).
    - venue_offshore_gap: divergence = offshore gap z direction (positive z = offshore
      leading, negative = onshore leading); we fire when |z| > 0.5 per signal function.
    - venue_southbound: divergence = flow z vs HSCEI z — we apply the 2x2 kernel:
      flow leading (dir=+1) vs HSCEI lagging (hk_z < -0.3) = positive divergence.

    For the ledger, we record the signal z as `rs_at_fire` (repurposed field) since there
    is no true "price RS" in the sector sense.
    """
    # None signal = no data → skip entirely
    if sig is None:
        return None

    sdir = sig["dir"]
    z_val = sig.get("z", 0.0) or 0.0
    strength = sig.get("strength", 0.0)

    # Venue-specific divergence logic
    if key == "venue_southbound":
        # 2x2 kernel: flow vs HSCEI price momentum
        hk_z = sig.get("_hk_z", 0.0) or 0.0
        pdir = 1 if hk_z > 0.3 else (-1 if hk_z < -0.3 else 0)
        if pdir == 0:
            sign = "in_line"
        elif sdir > 0 and pdir < 0:
            sign = "positive"   # flow strong, HSCEI lagging
        elif sdir < 0 and pdir > 0:
            sign = "negative"   # flow weak, HSCEI still leading
        else:
            sign = "in_line"
        price_rs_z = hk_z
        price_rs_pct = None  # not a CSI300 relative return
    else:
        # For AH premium and offshore gap: direction IS the divergence signal.
        # Positive dir (premium high OR offshore leading) = potential onshore catch-up.
        # Negative dir = potential onshore lag. Zero = in_line (both legs agree or within noise floor).
        if sdir > 0:
            sign = "positive"
        elif sdir < 0:
            sign = "negative"
        else:
            sign = "in_line"
        price_rs_z = z_val   # report signal z in the rs_z field for consistency
        price_rs_pct = sig.get("value")

    pair = f"{key}->china"
    if sign == "positive":
        hyp_en = (f"If {sen} leads, the onshore/HK price leg ({proxy_en}) should "
                  f"close the gap over ~3 months. {thesis}")
        hyp_zh = f"若{szh}领先，境内/港股价格（{proxy_zh}）应在约3个月内收敛。"
    elif sign == "negative":
        hyp_en = (f"If {sen} diverges negatively, the price leg ({proxy_en}) should "
                  f"pull back over ~3 months. {thesis}")
        hyp_zh = f"若{szh}出现负向背离，价格腿（{proxy_zh}）应在约3个月内回落。"
    else:
        # Return in-line row so it surfaces in scan()["in_line"] and n_pairs count
        return {
            "pair": pair, "signal_key": key, "family": "venue",
            "signal_en": sen, "signal_zh": szh,
            "sector": proxy_en, "sector_etf": None, "sector_en": proxy_en, "sector_zh": proxy_zh,
            "sign": "in_line", "strength": 0.0, "conviction100": 0,
            "signal_value": sig.get("value") if sig else None, "signal_dir": 0,
            "signal_detail_en": sig.get("detail_en") if sig else None,
            "signal_detail_zh": sig.get("detail_zh") if sig else None,
            "price_rs": None, "price_rs_z": None,
            "data_asof": sig.get("data_asof", "") if sig else "",
            "reliability": {"hit_rate": None, "n_resolved": 0, "basis": "unproven"},
            "candidates": [], "thesis": thesis, "hypothesis_en": "", "hypothesis_zh": "",
        }

    rel = by_pair.get(pair) or by_signal.get(key) or {}
    n_res = rel.get("n_resolved", 0)
    hr = rel.get("hit_rate")
    basis = ("pair" if pair in by_pair else ("signal_key" if key in by_signal else "unproven"))
    if n_res >= 3 and hr is not None:
        rel_factor = max(0.15, min(1.5, 1.5 * hr))
    else:
        rel_factor = 1.0
        basis = "unproven"

    conviction100 = cv.to_100(strength * rel_factor)
    data_asof = sig.get("data_asof", "")

    return {
        "pair": pair, "signal_key": key, "family": "venue",
        "signal_en": sen, "signal_zh": szh,
        "sector": proxy_en, "sector_etf": None, "sector_en": proxy_en, "sector_zh": proxy_zh,
        "sign": sign, "strength": round(strength, 3), "conviction100": conviction100,
        "signal_value": sig.get("value"), "signal_dir": sdir,
        "signal_detail_en": sig.get("detail_en"), "signal_detail_zh": sig.get("detail_zh"),
        "price_rs": price_rs_pct, "price_rs_z": price_rs_z,
        "data_asof": data_asof,
        "reliability": {"hit_rate": hr, "n_resolved": int(n_res), "basis": basis},
        "candidates": [],   # venue pairs have no basket member candidates
        "thesis": thesis, "hypothesis_en": hyp_en, "hypothesis_zh": hyp_zh,
    }


def scan(asof: date | str | None = None) -> dict | None:
    """Run all radar pairs → divergence verdicts + falsifiable hypotheses, conviction-scored
    (strength × ledger reliability) with per-name candidates. Never raises."""
    try:
        from engine import china_conviction as cv
        by_pair, by_signal = _ledger_reliability()
        try:
            from engine import china_altdata
            conv_map = china_altdata.convergence_map()
        except Exception:  # noqa: BLE001
            conv_map = {}
        rows: list[dict] = []
        for key, fn, sen, szh, targets, thesis in _PAIRS:
            sig = fn()
            if sig is None:
                continue
            for etf, sec_en, sec_zh in targets:
                rows.append(_build_row(cv, key, sen, szh, etf, sec_en, sec_zh, sig, thesis,
                                       by_pair, by_signal, conv_map))
        # sector-flow pairs (GATED Tushare): each sector's OWN 东财 net-flow vs its price RS.
        # Absent without a token / cache → simply no sector-flow rows.
        boards = _sector_flow_boards()
        for etf, sec_en, sec_zh, board in _SECTOR_FLOW_MAP:
            sig = _sector_flow_signal(board, boards)
            if sig is None:
                continue
            rows.append(_build_row(cv, "sector_flow", "Sector net-flow", "板块净流入",
                                   etf, sec_en, sec_zh, sig, _SECTOR_FLOW_THESIS,
                                   by_pair, by_signal, conv_map))
        # venue divergence family — additive, tagged family="venue"
        for key, fn, sen, szh, proxy_en, proxy_zh, thesis in _VENUE_PAIRS:
            sig = fn()
            row = _build_venue_row(cv, key, sen, szh, proxy_en, proxy_zh, sig, thesis,
                                   by_pair, by_signal)
            if row is not None:
                rows.append(row)
            else:
                log.debug("china_radar venue pair %s: no data, skipping", key)
        if not rows:
            return None
        active = [r for r in rows if r["sign"] != "in_line"]
        active.sort(key=lambda r: (r["conviction100"], r["strength"]), reverse=True)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "asof": str(asof) if asof else str(date.today()),
            "built": datetime.now(timezone.utc).isoformat(),
            "divergences": active,
            "in_line": [r for r in rows if r["sign"] == "in_line"],
            "n_active": len(active), "n_pairs": len(rows),
            "disclaimer_en": "Context only — a divergence is a falsifiable hypothesis, not a trade. "
                             "No validated edge; the ledger tracks whether these calls hold.",
            "disclaimer_zh": "仅作背景——背离是可证伪的假设，而非交易。无已验证优势；台账追踪这些判断是否成立。",
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_radar.scan failed (%s)", e)
        return None
