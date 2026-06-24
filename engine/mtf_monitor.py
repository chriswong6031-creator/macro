"""Multi-timeframe technical monitor — monthly / weekly / daily / 4h breakdown,
divergence and momentum-roll watch across major indexes, asset classes and ALL
sector ETFs.

WHY: the 2026-06-23 unwind started as a price/momentum roll in the leaders while
the macro read stayed calm. A disciplined, intricate technical watch across every
major index, asset class and sector — on multiple timeframes — is the layer that
sees a breakdown forming. This is the mirror of the merged bottoming-ALIGNMENT
engine (engine/cycles.mtf_alignment): instead of "is a bottom aligning?" it asks
"is a TOP / breakdown forming?" across timeframes.

REUSE (no new MACD math): engine/cycles.py — mtf_snapshot (D/3D/W/M MACD/RSI/StochRSI
states), _tf_phase (rising/turning/basing/rolling/falling), rsi_divergence (bearish
price/RSI divergence), mtf_alignment (the bottoming read). 4h is read from the
optional intraday store (data/intraday/<T>.parquet) and is omitted when absent.

Display-first (site/riskdata/mtf_monitor.json → a dashboard grid) PLUS a bounded
top-level `technical_intensity` that feeds a leg into engine/risk_state.py on the
next build (one-build lag, like the GEX leg). Never raises into the build.
"""
from __future__ import annotations

import json
import logging

from lib import config, store

log = logging.getLogger(__name__)

# (ticker, en, zh, kind) — kind selects the cycles preset (3-day calendar etc.)
_INDEXES = [
    ("SPY", "S&P 500", "标普500", "equity"),
    ("QQQ", "Nasdaq 100", "纳指100", "equity"),
    ("IWM", "Russell 2000", "罗素2000", "equity"),
    ("DIA", "Dow Jones", "道指", "equity"),
]
_ASSETS = [
    ("BTC-USD", "Bitcoin", "比特币", "crypto"),
    ("GC=F", "Gold", "黄金", "equity"),
    ("CL=F", "Oil (WTI)", "原油(WTI)", "equity"),
    ("TLT", "Long Treasuries", "长期美债", "equity"),
    ("DX-Y.NYB", "US Dollar (DXY)", "美元指数", "fx"),
]
_SECTORS = [
    ("XLK", "Technology", "科技", "equity"), ("XLC", "Communications", "通讯", "equity"),
    ("XLY", "Consumer Disc.", "可选消费", "equity"), ("XLP", "Consumer Staples", "必需消费", "equity"),
    ("XLE", "Energy", "能源", "equity"), ("XLF", "Financials", "金融", "equity"),
    ("XLV", "Health Care", "医疗", "equity"), ("XLI", "Industrials", "工业", "equity"),
    ("XLB", "Materials", "材料", "equity"), ("XLRE", "Real Estate", "地产", "equity"),
    ("XLU", "Utilities", "公用事业", "equity"),
]

_TFS = ("M", "W", "3D", "D")  # 4H appended per-symbol when intraday is present
# per-timeframe deterioration intensity (the mirror of the bottoming phase value)
_PHASE_WARN = {"falling": 1.0, "rolling": 0.7, "basing": 0.2,
               "turning": 0.0, "rising": 0.0, "unknown": None}
_PHASE_EN = {"rising": "firm", "rolling": "rolling over", "turning": "turning up",
             "basing": "basing", "falling": "breaking down", "unknown": "—"}
_PHASE_ZH = {"rising": "走强", "rolling": "走弱中", "turning": "转向上", "basing": "筑底",
             "falling": "破位下行", "unknown": "—"}
# higher timeframes dominate the warning blend
_TF_WARN_W = {"M": 0.34, "W": 0.34, "3D": 0.16, "D": 0.16, "4H": 0.0}


def _cfg() -> dict:
    try:
        c = (config.load().get("engine") or {}).get("mtf_monitor") or {}
    except Exception:
        c = {}
    return c


def _read_ohlc(ticker: str):
    df = store.read("yahoo", ticker)
    if df is None or "close" not in df:
        return None, None
    close = df["close"].dropna()
    high = df["high"].dropna() if "high" in df.columns else None
    return (close if len(close) else None), high


def _intraday_4h(ticker: str):
    """Optional 4h timeframe from the hourly intraday store (data/intraday/<T>.parquet).
    Returns a _tf_state dict or None when the store is absent (the common local case)."""
    try:
        import pandas as pd
        p = config.data_dir() / "intraday" / f"{ticker}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        col = next((c for c in ("close", "c", "Close") if c in df.columns), None)
        if col is None:
            return None
        s = df[col].dropna()
        if not isinstance(s.index, pd.DatetimeIndex):
            return None
        s4 = s.resample("4h").last().dropna()
        from engine.cycles import _tf_state
        return _tf_state(s4) or None
    except Exception:  # pragma: no cover - intraday is best-effort
        return None


def _ma_below(close, win: int) -> bool | None:
    if close is None or len(close) < win:
        return None
    ma = close.rolling(win).mean()
    return bool(close.iloc[-1] < ma.iloc[-1])


def _tag(mph: str, wph: str, t3ph: str, dph: str, aligned: bool = False) -> str:
    """Pure tag taxonomy, highest-TF deterioration first. NOTE: a healthy uptrend is
    'firm', NOT 'bottoming' — bottoming means emerging from weakness (weekly basing/
    turning). mtf_alignment.near is True for any uptrend, so it is NOT used here."""
    if "falling" in (mph, wph):
        return "breakdown"
    if "rolling" in (mph, wph):
        return "rolling-over"
    if dph in ("falling", "rolling") or t3ph in ("falling", "rolling"):
        return "weakening"               # higher TFs ok, short-term rolling
    if wph in ("basing", "turning") and (t3ph in ("turning", "rising") or aligned):
        return "bottoming"               # genuinely emerging from a base
    if wph == "rising":
        return "firm"
    return "neutral"


def _symbol(ticker: str, en: str, zh: str, kind: str = "equity") -> dict | None:
    """Per-symbol multi-timeframe technical read. None when history is too thin."""
    from engine.cycles import (mtf_snapshot, _tf_phase, rsi_divergence, mtf_alignment,
                               cycle_state)
    close, high = _read_ohlc(ticker)
    if close is None or len(close) < 60:
        return None
    mtf = mtf_snapshot(close, kind=kind)

    tfs: dict[str, dict] = {}
    for tf in _TFS:
        st = mtf.get(tf) or {}
        ph = _tf_phase(st) if st else "unknown"
        tfs[tf] = {"phase": ph, "phase_en": _PHASE_EN[ph], "phase_zh": _PHASE_ZH[ph],
                   "rsi": st.get("rsi14")}
    fh = _intraday_4h(ticker)
    if fh:
        ph = _tf_phase(fh)
        tfs["4H"] = {"phase": ph, "phase_en": _PHASE_EN[ph], "phase_zh": _PHASE_ZH[ph],
                     "rsi": fh.get("rsi14")}

    div = rsi_divergence(close) or {}
    bear_div = bool(div.get("bear"))
    below_50 = _ma_below(close, 50)
    below_200 = _ma_below(close, 200)

    # warning intensity: weighted deterioration across timeframes (higher TFs heavier)
    num = den = 0.0
    for tf, st in tfs.items():
        wv = _PHASE_WARN.get(st["phase"])
        w = _TF_WARN_W.get(tf, 0.0)
        if wv is None or w <= 0:
            continue
        num += wv * w
        den += w
    intensity = (num / den) if den > 0 else 0.0
    if bear_div:
        intensity = min(1.0, intensity + 0.12)
    if below_200:
        intensity = min(1.0, intensity + 0.10)

    wph, mph = tfs["W"]["phase"], tfs["M"]["phase"]
    dph, t3 = tfs["D"]["phase"], tfs["3D"]["phase"]
    # bottoming context (reuse the merged alignment engine)
    try:
        align = mtf_alignment(mtf, lad=cycle_state(close, high, kind=kind))
    except Exception:  # pragma: no cover
        align = {}

    tag = _tag(mph, wph, t3, dph, bool(align.get("aligned")))

    flags = []
    if bear_div:
        flags.append("bearish RSI divergence")
    if below_200:
        flags.append("below 200dma")
    elif below_50:
        flags.append("below 50dma")

    line = (f"M {_PHASE_EN[mph]} · W {_PHASE_EN[wph]} · 3D {_PHASE_EN[t3]} · D {_PHASE_EN[dph]}")
    return {
        "ticker": ticker, "en": en, "zh": zh,
        "tfs": tfs, "tag": tag, "intensity": round(float(intensity), 3),
        "bear_div": bear_div, "below_50": bool(below_50), "below_200": bool(below_200),
        "flags": flags, "line": line,
        "align_bottoming": bool(align.get("aligned") or align.get("near")),
    }


def monitor(universe: dict | None = None) -> dict:
    """Build the full multi-timeframe technical monitor. Groups: indexes / assets /
    sectors. Returns the serializable dict written to site/riskdata/mtf_monitor.json
    and read back by risk_state. Never raises."""
    cfg = _cfg()
    u = universe or {}
    groups_spec = {
        "indexes": u.get("indexes") or cfg.get("indexes") or _INDEXES,
        "assets": u.get("assets") or cfg.get("assets") or _ASSETS,
        "sectors": u.get("sectors") or cfg.get("sectors") or _SECTORS,
    }
    groups: dict[str, list] = {}
    for gname, spec in groups_spec.items():
        rows = []
        for row in spec:
            try:
                tkr, en, zh = row[0], row[1], row[2]
                kind = row[3] if len(row) > 3 else "equity"
                r = _symbol(tkr, en, zh, kind)
                if r:
                    rows.append(r)
            except Exception as e:  # noqa: BLE001 — one symbol must not kill the grid
                log.warning("mtf_monitor: %s failed: %s", row[0] if row else "?", e)
        rows.sort(key=lambda r: -r["intensity"])
        groups[gname] = rows

    idx = groups.get("indexes", [])
    # technical intensity = how broadly the MAJOR INDEXES are deteriorating on the
    # higher timeframes (the bounded leg risk_state consumes). Weight breakdown(W/M
    # falling) full, rolling-over half.
    def _w_state(r):
        wph, mph = r["tfs"]["W"]["phase"], r["tfs"]["M"]["phase"]
        if "falling" in (wph, mph):
            return 1.0
        if "rolling" in (wph, mph):
            return 0.5
        return 0.0
    tech = (sum(_w_state(r) for r in idx) / len(idx)) if idx else None
    breakdown_count = sum(1 for g in groups.values() for r in g if r["tag"] == "breakdown")
    rolling_count = sum(1 for g in groups.values() for r in g if r["tag"] == "rolling-over")
    total = sum(len(g) for g in groups.values())

    return {
        "schema": "mtf_monitor.v1",
        "groups": groups,
        "technical_intensity": None if tech is None else round(float(tech), 3),
        "breakdown_count": breakdown_count,
        "rolling_count": rolling_count,
        "n_symbols": total,
        "has_4h": any("4H" in r["tfs"] for g in groups.values() for r in g),
        "is_context_only": True,
        "disclaimer": ("Multi-timeframe MACD/RSI posture (engine/cycles.py), display + a "
                       "bounded technical leg into the risk state. Phases describe momentum, "
                       "not a price target."),
    }


def build(root=None) -> dict:
    """Compute + persist site/riskdata/mtf_monitor.json. Returns the dict."""
    out = monitor()
    try:
        base = (root if root is not None else config.ROOT)
        p = base / "site" / "riskdata" / "mtf_monitor.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001 — never fatal
        log.error("mtf_monitor: write failed: %s", e)
    return out


def published(root=None) -> dict | None:
    """Read the last-published mtf_monitor.json (for risk_state's technical leg)."""
    try:
        base = (root if root is not None else config.ROOT)
        p = base / "site" / "riskdata" / "mtf_monitor.json"
        if not p.exists():
            return None
        return json.loads(p.read_text())
    except Exception:  # pragma: no cover
        return None


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
