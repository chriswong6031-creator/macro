"""Build the Odds Desk — historical base-rate Analyzer + Factor Match screener.

Nightly lane (registered in daily.yml as `run_py "odds desk (build_odds)"
scripts.build_odds`):

  1. Ensure the dedicated OHLCV store ``data/odds_ohlcv/<T>.parquet`` per
     universe ticker (yfinance, auto_adjust=True): ``period="max"`` when the
     stored series is missing/shallow, else a 1-month overlap window upserted
     (mirrors collectors/yahoo.py). Batched politely; degrades per ticker.
     The store is gitignored + R2-backed (the massive_stock_day pattern).
     Upserts are ADJUSTMENT-BASIS GUARDED (deliberate deviation from the spec's
     bare 1-mo splice): auto_adjust rebases the whole series at every fetch, so
     after any dividend/split the stored history sits on a stale basis and a
     bare splice corrupts every factor spanning the seam. Overlap closes are
     compared first; a shift beyond ``upsert_basis_tol`` (or no overlap at all)
     triggers a per-ticker ``period="max"`` refetch instead — cheap, self-healing.
  2. Cache name/sector once into ``data/odds_ohlcv/_meta.json`` (yfinance
     .info; degrades to ticker-only).
  3. Build the market frame (SPY trend state, VIX bands, macro quad from
     data/regime/regime_history.parquet) and the per-ticker factor matrices
     via engine/odds_lab.py — full recompute every run (vectorized, seconds;
     forward returns self-fill as future bars arrive).
  4. Publish: site/oddsmatrix/<T>.json (R2 data plane — NEVER commit),
     site/oddsdata/catalog.json + site/oddsdata/factor_match.json (git/Pages).
  5. Render templates/odds.html.j2 → site/odds.html via lib.pages.write_page
     (data-base shim injection, same as build_congress.py). A missing template
     degrades quietly — the data files are already on disk.

Universe/params live in config.yml under ``odds:`` — no magic numbers here.
Display / research only — never trades. Returns 0 on ANY error so it can
never break the daily build (mirrors build_congress.py / build_alt_data.py).
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from jinja2 import Environment, FileSystemLoader  # noqa: E402

from engine import odds_lab  # noqa: E402
from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_odds")


def _cfg() -> dict:
    return config.load().get("odds") or {}


# ---------------------------------------------------------------------------
# OHLCV store (data/odds_ohlcv/<T>.parquet)
# ---------------------------------------------------------------------------

def _norm_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase OHLCV columns, tz-naive ascending unique DatetimeIndex."""
    out = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in out.columns]
    out = out[keep]
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out[out["close"].notna()] if "close" in out.columns else out


def _yf_slice(raw: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Per-ticker frame out of a (possibly MultiIndex) yf.download result."""
    try:
        sub = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
    except KeyError:
        return None
    sub = _norm_ohlcv(sub.dropna(how="all"))
    return sub if len(sub) else None


def _download(tickers: list[str], period: str, batch_size: int,
              pause_s: float) -> dict[str, pd.DataFrame]:
    """Polite batched yfinance download (auto_adjust=True). Degrades per batch."""
    import yfinance as yf  # lazy: module import stays clean without it

    frames: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            raw = yf.download(batch, period=period, auto_adjust=True,
                              group_by="ticker", threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            log.warning("odds: yfinance batch failed (%s...): %s", batch[0], e)
            continue
        if raw is None or raw.empty:
            log.warning("odds: empty yfinance batch (%s...)", batch[0])
            continue
        for t in batch:
            sub = _yf_slice(raw, t)
            if sub is not None:
                frames[t] = sub
        if i + batch_size < len(tickers):
            time.sleep(pause_s)
    return frames


def _stale_days(last: pd.Timestamp) -> int:
    today = datetime.now(timezone.utc).date()
    try:
        return int(np.busday_count(last.date(), today))
    except Exception:  # noqa: BLE001
        return 999


def ensure_store(cfg: dict, store: Path) -> list[str]:
    """Backfill/refresh the OHLCV store; return tickers with a usable parquet."""
    universe = [str(t) for t in (cfg.get("universe") or [])]
    shallow = int(cfg.get("shallow_rows", 300))
    stale_limit = int(cfg.get("stale_trading_days", 0))
    need_max, need_win = [], []
    for t in universe:
        p = store / f"{t}.parquet"
        try:
            if not p.exists():
                need_max.append(t)
                continue
            df = pd.read_parquet(p)
            if len(df) < shallow:
                need_max.append(t)
            elif _stale_days(pd.Timestamp(df.index.max())) > stale_limit:
                need_win.append(t)
        except Exception as e:  # noqa: BLE001
            log.warning("odds: store read %s failed (%s) — refetching max", t, e)
            need_max.append(t)

    bs = int(cfg.get("batch_size", 40))
    pause = float(cfg.get("batch_pause_s", 1.0))
    if need_max:
        log.info("odds: full backfill for %d tickers", len(need_max))
        for t, df in _download(need_max, "max", bs, pause).items():
            try:
                df.to_parquet(store / f"{t}.parquet")
            except Exception as e:  # noqa: BLE001
                log.warning("odds: write %s failed: %s", t, e)
    if need_win:
        log.info("odds: 1mo upsert for %d tickers", len(need_win))
        basis_tol = float(cfg.get("upsert_basis_tol", 1e-3))
        rebase: list[str] = []
        for t, new in _download(need_win, "1mo", bs, pause).items():
            try:
                old = _norm_ohlcv(pd.read_parquet(store / f"{t}.parquet"))
                # Adjustment-basis guard: yfinance auto_adjust rebases the WHOLE
                # series to the current basis at every fetch. After a dividend or
                # split between fetches, splicing a fresh window onto old-basis
                # history corrupts the seam return and biases everything derived
                # from pre-seam closes (pct_move, magnitude, fwd*, dist_52w, SPY
                # SMAs). Compare closes on the overlap dates first; on a shift —
                # or when there is no overlap to verify (stored series ended more
                # than a window ago: splice would also leave a bar gap) — discard
                # the splice and refetch full history for that ticker instead.
                overlap = old.index.intersection(new.index)
                if len(overlap) == 0:
                    log.info("odds: %s has no overlap with the 1mo window — full refetch", t)
                    rebase.append(t)
                    continue
                oc = old.loc[overlap, "close"].astype(float)
                nc = new.loc[overlap, "close"].astype(float)
                rel = (oc - nc).abs() / nc.abs().clip(lower=1e-9)
                if float(rel.max()) > basis_tol:
                    log.info("odds: %s adjustment basis shifted (max overlap diff "
                             "%.4f%%) — discarding splice, full refetch",
                             t, float(rel.max()) * 100.0)
                    rebase.append(t)
                    continue
                merged = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
                merged.to_parquet(store / f"{t}.parquet")
            except Exception as e:  # noqa: BLE001
                log.warning("odds: upsert %s failed: %s", t, e)
        if rebase:
            log.info("odds: basis re-backfill (period=max) for %d tickers", len(rebase))
            for t, df in _download(rebase, "max", bs, pause).items():
                try:
                    df.to_parquet(store / f"{t}.parquet")
                except Exception as e:  # noqa: BLE001
                    log.warning("odds: basis re-backfill write %s failed: %s", t, e)
    return [t for t in universe if (store / f"{t}.parquet").exists()]


def ensure_meta(cfg: dict, store: Path, tickers: list[str]) -> dict:
    """Cache {ticker: {name, sector}} once into _meta.json (degrade to ticker)."""
    path = store / "_meta.json"
    meta: dict = {}
    try:
        if path.exists():
            meta = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("odds: meta read failed: %s", e)
    missing = [t for t in tickers if t not in meta]
    if not missing:
        return meta
    pause = float(cfg.get("meta_pause_s", 0.15))
    try:
        import yfinance as yf
        for t in missing:
            try:
                info = yf.Ticker(t).info or {}
                sector = info.get("sector") or (
                    "ETF" if info.get("quoteType") in ("ETF", "MUTUALFUND") else "")
                meta[t] = {"name": info.get("shortName") or info.get("longName") or t,
                           "sector": sector}
            except Exception:  # noqa: BLE001
                meta[t] = {"name": t, "sector": ""}
            time.sleep(pause)
    except Exception as e:  # noqa: BLE001
        log.warning("odds: meta fetch degraded (%s)", e)
        for t in missing:
            meta.setdefault(t, {"name": t, "sector": ""})
    try:
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001
        log.warning("odds: meta write failed: %s", e)
    return meta


# ---------------------------------------------------------------------------
# market inputs
# ---------------------------------------------------------------------------

def _close_series(path: Path, col: str = "close") -> pd.Series | None:
    try:
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if col not in df.columns:
            return None
        s = df[col].astype(float)
        idx = pd.to_datetime(s.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        s.index = idx.normalize()
        return s[~s.index.duplicated(keep="last")].sort_index().dropna()
    except Exception as e:  # noqa: BLE001
        log.warning("odds: read %s failed: %s", path, e)
        return None


def _load_spy(store: Path) -> pd.Series | None:
    s = _close_series(store / "SPY.parquet")
    if s is not None and len(s):
        return s
    return _close_series(config.ROOT / "data" / "yahoo" / "SPY.parquet")


def _load_regime() -> pd.DataFrame | None:
    p = config.ROOT / "data" / "regime" / "regime_history.parquet"
    try:
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex):
            for c in ("date", "Date", "asof"):
                if c in df.columns:
                    df = df.set_index(c)
                    break
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        df.index = idx.normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df if "quad" in df.columns else None
    except Exception as e:  # noqa: BLE001
        log.warning("odds: regime read failed: %s", e)
        return None


def _market_today(market: pd.DataFrame | None) -> dict:
    """Today's market buckets + raw context for the catalog / factor_match."""
    if market is None or market.empty:
        return {}
    m = market[market["mkt_trend"].notna()] if "mkt_trend" in market.columns else market
    if m.empty:
        m = market
    row = m.iloc[-1]

    def iv(k):
        v = row.get(k)
        return None if v is None or pd.isna(v) else int(v)

    def fv(k, nd=2):
        v = row.get(k)
        return None if v is None or pd.isna(v) else round(float(v), nd)

    return {
        "date": str(pd.Timestamp(m.index[-1]).date()),
        "mkt_trend": iv("mkt_trend"), "vix_level": iv("vix_level"),
        "vix_move": iv("vix_move"), "month": iv("month"), "quad": iv("quad"),
        "raw": {"vix": fv("vix"), "vix_chg_pct": fv("vix_chg_pct"),
                "spy": fv("spy"), "spy_sma50": fv("spy_sma50"),
                "spy_sma200": fv("spy_sma200")},
    }


# ---------------------------------------------------------------------------
# catalog (bucket display labels are generated here — display strings, not params)
# ---------------------------------------------------------------------------

_MKT_TREND_LABELS = {0: ("Full Bull", "全面多头"), 1: ("Bull Correction", "多头回调"),
                     2: ("Bear Rally", "空头反弹"), 3: ("Full Bear", "全面空头")}
_VIX_LABELS = {0: ("<12", "低于12"), 1: ("12–15", "12–15"), 2: ("15–20", "15–20"),
               3: ("20–25", "20–25"), 4: ("25–35", "25–35"), 5: ("≥35", "35以上")}
_QUAD_LABELS = {1: ("Q1 Goldilocks", "Q1 金发姑娘"), 2: ("Q2 Reflation", "Q2 再通胀"),
                3: ("Q3 Stagflation", "Q3 滞胀"), 4: ("Q4 Deflation", "Q4 通缩")}
_RSI_LABELS = {-2: ("<30 oversold", "超卖 <30"), -1: ("30–45", "30–45"),
               0: ("45–55 neutral", "中性 45–55"), 1: ("55–70", "55–70"),
               2: ("≥70 overbought", "超买 ≥70")}
_RSI_SLOPE_LABELS = {-2: ("Falling fast", "快速走弱"), -1: ("Falling", "走弱"),
                     0: ("Flat", "走平"), 1: ("Rising", "走强"), 2: ("Rising fast", "快速走强")}
_REL_VOL_LABELS = {-2: ("<0.5×", "<0.5×"), -1: ("0.5–0.8×", "0.5–0.8×"),
                   0: ("0.8–1.2×", "0.8–1.2×"), 1: ("1.2–1.75×", "1.2–1.75×"),
                   2: ("1.75–2.5×", "1.75–2.5×"), 3: ("≥2.5×", "≥2.5×")}
_TREND_LABELS = {-2: ("Strong downtrend", "强空头结构"), -1: ("Downtrend", "偏空"),
                 0: ("Flat", "中性"), 1: ("Uptrend", "偏多"), 2: ("Strong uptrend", "强多头结构")}
_DIST_LABELS = {0: ("At 52w high (≥−1%)", "接近52周高点（≥−1%）"),
                -1: ("−1% … −5%", "回撤1–5%"), -2: ("−5% … −10%", "回撤5–10%"),
                -3: ("−10% … −20%", "回撤10–20%"), -4: ("≤−20%", "回撤超20%")}
_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _bucket_labels(fid: str) -> dict:
    """{bucket: {label_en, label_zh}} per factor (generated for step buckets)."""
    def pair(d):
        return {int(k): {"label_en": en, "label_zh": zh} for k, (en, zh) in d.items()}

    if fid == "mkt_trend":
        return pair(_MKT_TREND_LABELS)
    if fid == "vix_level":
        return pair(_VIX_LABELS)
    if fid == "quad":
        return pair(_QUAD_LABELS)
    if fid == "rsi_zone":
        return pair(_RSI_LABELS)
    if fid == "rsi_slope":
        return pair(_RSI_SLOPE_LABELS)
    if fid == "rel_vol":
        return pair(_REL_VOL_LABELS)
    if fid == "trend_structure":
        return pair(_TREND_LABELS)
    if fid == "dist_52w":
        return pair(_DIST_LABELS)
    if fid == "month":
        return {m: {"label_en": _MONTHS_EN[m - 1], "label_zh": f"{m}月"} for m in range(1, 13)}
    if fid == "vix_move":
        out = {}
        for k in range(-8, 9):
            en = "≤−16%" if k == -8 else ("≥+16%" if k == 8 else f"≈{2 * k:+d}%")
            out[k] = {"label_en": en, "label_zh": en if k else "≈0%（持平）"}
        return out
    if fid == "pct_move":
        out = {}
        for k in range(-12, 13):
            en = "≤−3%" if k == -12 else ("≥+3%" if k == 12 else f"≈{0.25 * k:+.2f}%")
            out[k] = {"label_en": en, "label_zh": en}
        return out
    if fid == "gap":
        out = {}
        for k in range(-6, 7):
            en = "≤−1.5%" if k == -6 else ("≥+1.5%" if k == 6 else f"≈{0.25 * k:+.2f}%")
            out[k] = {"label_en": en, "label_zh": en if k else "平开"}
        return out
    if fid == "magnitude":
        out = {}
        for k in range(-6, 7):
            en = "≤−3 ATR" if k == -6 else ("≥+3 ATR" if k == 6 else f"≈{0.5 * k:+.1f} ATR")
            out[k] = {"label_en": en, "label_zh": en}
        return out
    if fid == "streak":
        out = {}
        for k in range(-5, 6):
            if k > 0:
                en, zh = (f"≥{k} up" if k == 5 else f"{k} up"), (f"连涨≥{k}天" if k == 5 else f"连涨{k}天")
            elif k < 0:
                en, zh = (f"≥{-k} down" if k == -5 else f"{-k} down"), (f"连跌≥{-k}天" if k == -5 else f"连跌{-k}天")
            else:
                en, zh = "Flat", "持平"
            out[k] = {"label_en": en, "label_zh": zh}
        return out
    if fid == "vol_streak":
        out = {}
        for k in range(-8, 9):
            if k > 0:
                en, zh = (f"≥{k}d above avg" if k == 8 else f"{k}d above avg"), (f"高于均量≥{k}天" if k == 8 else f"高于均量{k}天")
            elif k < 0:
                en, zh = (f"≥{-k}d below avg" if k == -8 else f"{-k}d below avg"), (f"低于均量≥{-k}天" if k == -8 else f"低于均量{-k}天")
            else:
                en, zh = "At average", "持平均量"
            out[k] = {"label_en": en, "label_zh": zh}
        return out
    return {}


def _catalog(cfg: dict, matrices: dict, meta: dict, market_today: dict,
             asof: str) -> dict:
    factors = []
    for f in (cfg.get("factors") or []):
        fid = str(f.get("id"))
        factors.append({
            "id": fid, "group": f.get("group", "asset"),
            "label_en": f.get("label_en", fid), "label_zh": f.get("label_zh", fid),
            "desc_en": f.get("desc_en", ""), "desc_zh": f.get("desc_zh", ""),
            "buckets": _bucket_labels(fid),
            "ordered": bool(f.get("ordered", True)),
        })
    universe = [{"t": t, "name": (meta.get(t) or {}).get("name", t),
                 "sector": (meta.get(t) or {}).get("sector", "")}
                for t in matrices]
    defaults = cfg.get("defaults") or {}
    return {
        "schema": "odds_catalog.v1",
        "asof": asof,
        "market": market_today,
        "factors": factors,
        "universe": universe,
        "ranges": list(cfg.get("ranges") or ["5y", "10y", "20y", "max"]),
        "horizons": list(cfg.get("horizons") or ["1d", "5d", "20d"]),
        "defaults": {
            "active": list(defaults.get("active") or ["magnitude", "vix_level", "mkt_trend"]),
            "range": defaults.get("range", "10y"),
            "horizon": defaults.get("horizon", "1d"),
        },
    }


# ---------------------------------------------------------------------------
# page render (write_page injects the data-base shim — build_congress pattern)
# ---------------------------------------------------------------------------

def _render(catalog: dict, site: Path) -> None:
    tpl = config.ROOT / "templates" / "odds.html.j2"
    if not tpl.exists():
        log.warning("odds: templates/odds.html.j2 absent — page render skipped "
                    "(data files already written)")
        return
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        html = env.get_template("odds.html.j2").render(
            catalog=catalog, market=catalog.get("market") or {},
            universe=catalog.get("universe") or [], defaults=catalog.get("defaults") or {},
            asof=catalog.get("asof"), generated_utc=built,
            active_section="research", active_page="odds",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("odds render failed — skipping (additive): %s", e)
        return
    site.mkdir(exist_ok=True)
    write_page(site / "odds.html", html)
    log.info("wrote %s/odds.html (%d KB)", site, len(html) // 1024)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        cfg = _cfg()
        if not cfg or not cfg.get("enabled", True):
            log.info("odds: disabled/unconfigured — skipping")
            return 0
        root = config.ROOT
        store = root / cfg.get("store_dir", "data/odds_ohlcv")
        store.mkdir(parents=True, exist_ok=True)

        tickers = ensure_store(cfg, store)
        if not tickers:
            log.warning("odds: no tickers in store — nothing to build")
            return 0
        meta = ensure_meta(cfg, store, tickers)

        spy = _load_spy(store)
        vix = _close_series(root / "data" / "yahoo" / "_VIX.parquet")
        regime = _load_regime()
        market = odds_lab.compute_market_frame(spy, vix, regime) if spy is not None else None
        if market is None:
            log.warning("odds: no SPY series — market factors will be null")

        matrix_dir = root / cfg.get("matrix_dir", "site/oddsmatrix")
        matrix_dir.mkdir(parents=True, exist_ok=True)
        min_rows = int(cfg.get("min_rows", 60))
        matrices: dict[str, dict] = {}
        for t in tickers:
            try:
                df = _norm_ohlcv(pd.read_parquet(store / f"{t}.parquet"))
                if len(df) < min_rows:
                    log.info("odds: %s has %d rows (<%d) — skipped", t, len(df), min_rows)
                    continue
                m = odds_lab.build_matrix(t, df, market)
                (matrix_dir / f"{t}.json").write_text(json.dumps(m, separators=(",", ":")))
                matrices[t] = m
            except Exception as e:  # noqa: BLE001
                log.warning("odds: matrix %s failed: %s", t, e)
        log.info("odds: built %d/%d matrices → %s", len(matrices), len(tickers), matrix_dir)
        if not matrices:
            log.warning("odds: no matrices built — skipping artifacts")
            return 0

        data_dir = root / cfg.get("data_dir", "site/oddsdata")
        data_dir.mkdir(parents=True, exist_ok=True)
        asof = max(m["asof"] for m in matrices.values())
        market_today = _market_today(market)

        catalog = _catalog(cfg, matrices, meta, market_today, asof)
        (data_dir / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
        log.info("odds: wrote catalog.json (%d universe, asof %s)", len(matrices), asof)

        fm_cfg = cfg.get("factor_match") or {}
        fm = odds_lab.run_factor_match(
            matrices,
            templates=fm_cfg.get("templates") or [],
            meta=meta,
            horizons=tuple(cfg.get("horizons") or ("1d", "5d", "20d")),
            range_key=fm_cfg.get("range", "20y"),
            min_n=int(fm_cfg.get("min_n", 10)),
            market=market_today,
            asof=asof,
        )
        (data_dir / "factor_match.json").write_text(
            json.dumps(fm, ensure_ascii=False, separators=(",", ":")))
        log.info("odds: wrote factor_match.json (%d rows, %d templates)",
                 len(fm.get("rows") or []), len(fm.get("templates") or []))

        _render(catalog, root / "site")
        return 0
    except Exception as e:  # noqa: BLE001 — never break the daily build
        log.warning("odds desk build failed — skipping (additive): %s", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
