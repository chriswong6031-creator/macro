"""Build the S&P 500 sector-treemap heatmap data feed.

Reads the local close matrix + sector classification (offline-safe) and, when a
Polygon key is present, splices a fresh 15-min-delayed snapshot for a live 1D
read. Writes ``site/marketdata/sp500_heatmap.json`` consumed by
``site/sector_heatmap.html``.

Usage
-----
    python -m scripts.build_sp500_heatmap            # daily build (auto-live if key)
    python -m scripts.build_sp500_heatmap --no-live  # force offline close-only
    python -m scripts.build_sp500_heatmap --refresh-caps  # rebuild real-cap cache via Polygon
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import sp500_heatmap as hm  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_sp500_heatmap")

_CAP_REFRESH_DAYS = 7  # reference (shares/industry) cache staleness ceiling


def _data(*parts: str) -> Path:
    return config.data_dir().joinpath(*parts)


def _load_constituents() -> pd.DataFrame:
    df = pd.read_parquet(_data("breadth", "constituents.parquet"))
    if df.index.name != "symbol" and "symbol" in df.columns:
        df = df.set_index("symbol")
    return df


def _load_closes() -> pd.DataFrame:
    df = pd.read_parquet(_data("breadth", "_closes_cache.parquet"))
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _load_industry_map() -> dict:
    """ticker -> {'sector': finviz_sector, 'sub_industry': finviz_industry}.

    Prefers the curated Finviz-taxonomy map (``industry_map.json``) that drives
    the Sector → Subsector grouping; falls back to the legacy GICS sub-industry
    file when only that is present.
    """
    for name in ("industry_map.json", "gics_industry.json"):
        p = _data("sp500_heatmap", name)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception as e:  # noqa: BLE001
                log.warning("industry map %s unreadable: %s", name, e)
    return {}


# Dual-class pairs whose nightly cap (when present) reflects the whole company —
# the static fallback splits these by float so each tile sizes sensibly.
_DUAL_CLASS = {"GOOGL", "GOOG", "FOXA", "FOX", "NWSA", "NWS"}


def _load_static_caps() -> dict[str, float]:
    """Curated offline market-cap fallback (USD) for names the nightly records
    miss. Always overridden by a live/reference cap; only fills gaps."""
    p = _data("sp500_heatmap", "market_caps_fallback.json")
    if not p.exists():
        return {}
    try:
        return {str(k).strip().upper(): float(v) for k, v in json.loads(p.read_text()).items() if v}
    except Exception as e:  # noqa: BLE001
        log.warning("static caps unreadable: %s", e)
        return {}


def _load_caps_from_stockdata(site: Path, symbols: list[str]) -> dict[str, float]:
    """Real market caps harvested from the nightly per-stock records
    (``site/stockdata/<T>.json`` -> profile.mktcap_bn). Offline + leak-free, and
    keyed to the same names the hover card reads, so the treemap sizes by true
    market cap without any network. Returns {} if the directory is absent."""
    sdir = site / "stockdata"
    if not sdir.exists():
        return {}
    caps: dict[str, float] = {}
    for s in symbols:
        fp = sdir / f"{str(s).replace('=', '_').replace('^', '_')}.json"
        if not fp.exists():
            continue
        try:
            prof = (json.loads(fp.read_text()) or {}).get("profile") or {}
        except Exception:  # noqa: BLE001
            continue
        cap = prof.get("mktcap_bn")
        if cap is not None and cap == cap and float(cap) > 0:  # finite + positive
            caps[s] = float(cap) * 1e9
    return caps


def _load_caps_from_prev_payload(site: Path) -> dict[str, float]:
    """Real caps recycled from the last committed heatmap payload. The intraday
    refresh lane runs on a fresh checkout where neither the Polygon reference
    cache nor the stockdata records exist; the nightly payload's tile sizes ARE
    the nightly real caps, so reusing them keeps intraday tiles on market-cap
    sizing instead of visibly re-sizing to the weight proxy mid-session."""
    p = site / "marketdata" / "sp500_heatmap.json"
    if not p.exists():
        return {}
    try:
        prev = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("previous heatmap payload unreadable: %s", e)
        return {}
    if prev.get("size_basis") != "marketcap":
        return {}
    caps: dict[str, float] = {}
    for t in prev.get("tiles") or []:
        sym, size = t.get("t"), t.get("size")
        if sym and size is not None and float(size) > 0:
            caps[str(sym)] = float(size)
    return caps


def _load_sector_weights() -> dict[str, float]:
    """ticker -> latest SPDR within-sector weight_pct (offline cap proxy input)."""
    out: dict[str, float] = {}
    hdir = _data("sector_holdings")
    if not hdir.exists():
        return out
    for fp in sorted(hdir.glob("XL*.parquet")):
        try:
            df = pd.read_parquet(fp)
        except Exception:  # noqa: BLE001
            continue
        if df.empty or "ticker" not in df.columns or "weight_pct" not in df.columns:
            continue
        # files are date-indexed snapshots; keep the latest date's rows
        if df.index.name is not None or not isinstance(df.index, pd.RangeIndex):
            try:
                df = df.loc[[df.index.max()]]
            except Exception:  # noqa: BLE001
                pass
        for _, r in df.iterrows():
            t = str(r["ticker"]).strip().upper().replace(".", "-")
            w = r.get("weight_pct")
            if pd.notna(w):
                out[t] = float(w)
    return out


def _load_weights_by_etf() -> dict[str, dict[str, float]]:
    """{ETF: {ticker: latest within-sector weight_pct}} — kept per-ETF so a cap
    proxy can be calibrated against each fund's own scale."""
    out: dict[str, dict[str, float]] = {}
    hdir = _data("sector_holdings")
    if not hdir.exists():
        return out
    for fp in sorted(hdir.glob("XL*.parquet")):
        try:
            df = pd.read_parquet(fp)
        except Exception:  # noqa: BLE001
            continue
        if df.empty or "ticker" not in df.columns or "weight_pct" not in df.columns:
            continue
        if df.index.name is not None or not isinstance(df.index, pd.RangeIndex):
            try:
                df = df.loc[[df.index.max()]]
            except Exception:  # noqa: BLE001
                pass
        wmap: dict[str, float] = {}
        for _, r in df.iterrows():
            t = str(r["ticker"]).strip().upper().replace(".", "-")
            w = r.get("weight_pct")
            if pd.notna(w) and float(w) > 0:
                wmap[t] = float(w)
        if wmap:
            out[fp.stem.upper()] = wmap
    return out


def _complete_caps(caps: dict[str, float], symbols: list[str]) -> dict[str, float]:
    """Fill missing market caps so every constituent sizes on one real-cap scale.

    Roughly a third of the nightly records carry no ``mktcap_bn``. For those we
    estimate a cap from the SPDR sector-ETF within-weight, calibrated per fund
    against the names that *do* have a real cap (cap ≈ k_etf · weight_pct). This
    keeps mega-caps like V / LLY / XOM / BRK-B sized correctly instead of
    collapsing to a floor, while real caps win wherever present."""
    if not caps:
        return caps
    weights_by_etf = _load_weights_by_etf()
    if not weights_by_etf:
        return caps
    # per-ETF scale from names with a real cap; global median as a backstop.
    all_ratios: list[float] = []
    k_etf: dict[str, float] = {}
    for etf, wmap in weights_by_etf.items():
        ratios = [caps[t] / wmap[t] for t in wmap if t in caps and caps[t] > 0]
        all_ratios.extend(ratios)
        if ratios:
            k_etf[etf] = float(np.median(ratios))
    if not all_ratios:
        return caps
    k_global = float(np.median(all_ratios))

    def _implied(s: str) -> float:
        # best (largest-weight) ETF placement, scaled by that fund's own ratio.
        best_w, best_k = 0.0, k_global
        for etf, wmap in weights_by_etf.items():
            w = wmap.get(s, 0.0)
            if w > best_w:
                best_w, best_k = w, k_etf.get(etf, k_global)
        return best_k * best_w

    filled = dict(caps)
    # Plausibility screen: the weight proxy is calibrated on cap/weight ratios, so a
    # correct real cap cannot sit 8x UNDER its ETF-weight-implied value — one that does
    # is a poisoned upstream record (e.g. BKNG's nightly mktcap_bn arriving ~30x low)
    # and would otherwise "win" over the estimate and ship a visibly wrong tile.
    for s in symbols:
        cap = filled.get(s, 0)
        if cap <= 0:
            continue
        imp = _implied(s)
        if imp > 0 and cap < imp / 8:
            log.info("cap screen: %s real cap %.1fbn << implied %.0fbn — re-estimated",
                     s, cap / 1e9, imp / 1e9)
            filled[s] = imp
    n = 0
    for s in symbols:
        if filled.get(s, 0) > 0:
            continue
        imp = _implied(s)
        if imp > 0:
            filled[s] = imp
            n += 1
    if n:
        log.info("cap-completion: estimated %d caps from ETF weights", n)
    return filled


def _load_intraday(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """ticker -> hourly bar frame (close col) where a cache file exists."""
    idir = _data("intraday")
    if not idir.exists():
        return {}
    bars: dict[str, pd.DataFrame] = {}
    for s in symbols:
        fp = idir / f"{s.replace('.', '-')}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp).sort_index()
            if "close" in df.columns:
                bars[s] = df
        except Exception:  # noqa: BLE001
            continue
    return bars


def _cap_cache_age_days() -> float | None:
    """Age of the reference cache via its embedded ``asof`` stamp (git checkouts
    don't preserve mtimes, so file age is meaningless on CI). None = cache absent
    or unstamped — both count as stale."""
    p = _data("sp500_heatmap", "reference.parquet")
    if not p.exists():
        return None
    try:
        ref = pd.read_parquet(p, columns=["asof"])
        asof = pd.to_datetime(ref["asof"].iloc[0]).date()
    except Exception:  # noqa: BLE001 — pre-asof caches refresh once, gaining the stamp
        return None
    return float((datetime.now(timezone.utc).date() - asof).days)


def _load_caps(closes: pd.DataFrame) -> dict[str, float]:
    """Real market caps = shares x latest close, from the Polygon reference
    cache when present. Returns {} (-> proxy sizing) otherwise."""
    p = _data("sp500_heatmap", "reference.parquet")
    if not p.exists():
        return {}
    try:
        ref = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("reference cache unreadable: %s", e)
        return {}
    if "shares" not in ref.columns:
        return {}
    caps: dict[str, float] = {}
    for t, row in ref.iterrows():
        shares = row.get("shares")
        if shares is None or pd.isna(shares) or t not in closes.columns:
            continue
        col = closes[t].dropna()
        if col.empty:
            continue
        caps[t] = float(shares) * float(col.iloc[-1])
    return caps


def _fetch_live(symbols: list[str]) -> dict[str, dict]:
    """Fresh 15-min-delayed Polygon snapshot. No key -> {} (offline-safe)."""
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")
    if not key:
        log.info("no Polygon key — live splice skipped (close-cache 1D)")
        return {}
    try:
        from engine import live_quotes
    except Exception as e:  # noqa: BLE001
        log.warning("live_quotes import failed: %s", e)
        return {}
    try:
        q = live_quotes.fetch_quotes(symbols, us_source="polygon")
    except Exception as e:  # noqa: BLE001
        log.warning("live fetch failed: %s", e)
        return {}
    return q or {}


def refresh_caps(constituents: pd.DataFrame, *, force: bool = False) -> None:
    """(Re)build data/sp500_heatmap/reference.parquet with shares + SIC industry
    from Polygon /v3/reference/tickers/{ticker}. Best-effort; never fatal.
    Shares outstanding move slowly, so a cache younger than _CAP_REFRESH_DAYS is
    kept as-is unless forced — the nightly step calls this every run and only
    actually sweeps Polygon weekly."""
    if not force:
        age = _cap_cache_age_days()
        if age is not None and age < _CAP_REFRESH_DAYS:
            log.info("reference cache fresh (%.0fd < %dd) — refresh skipped",
                     age, _CAP_REFRESH_DAYS)
            return
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")
    if not key:
        log.warning("--refresh-caps needs a Polygon key; skipping")
        return
    try:
        from collectors.polygon_options import PolygonOptions
    except Exception as e:  # noqa: BLE001
        log.warning("PolygonOptions import failed: %s", e)
        return
    client = PolygonOptions()
    recs = []
    for sym in constituents.index:
        poly_sym = str(sym).replace("-", ".")
        try:
            r = client._get(f"/v3/reference/tickers/{poly_sym}", {})
            res = (r or {}).get("results") or {}
            shares = (res.get("weighted_shares_outstanding")
                      or res.get("share_class_shares_outstanding"))
            recs.append({
                "ticker": sym,
                "shares": float(shares) if shares else None,
                "sic": res.get("sic_code"),
                "sic_desc": res.get("sic_description"),
            })
        except Exception as e:  # noqa: BLE001
            log.debug("ref %s failed: %s", sym, e)
            recs.append({"ticker": sym, "shares": None})
    df = pd.DataFrame(recs).set_index("ticker")
    df["asof"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = _data("sp500_heatmap", "reference.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    log.info("wrote reference cache: %d tickers, %d with shares",
             len(df), int(df["shares"].notna().sum()))


def build(site: Path | None = None, *, live: bool = True,
          generated_utc: str | None = None) -> dict:
    """Assemble + write the heatmap JSON. Returns the payload."""
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    constituents = _load_constituents()
    closes = _load_closes()
    symbols = list(constituents.index)

    industry_map = _load_industry_map()
    weights = _load_sector_weights()
    # Real caps: Polygon reference cache first, else harvest from the nightly
    # per-stock records, else recycle the last committed payload's sizes (the
    # intraday lane's fresh checkout has neither cache). All three give true
    # market-cap sizing; the gaps are filled from calibrated ETF weights so
    # every tile sizes on one scale rather than collapsing to a floor.
    caps = (_load_caps(closes) or _load_caps_from_stockdata(site, symbols)
            or _load_caps_from_prev_payload(site))
    if not caps:
        log.warning("no real-cap source (reference.parquet / site/stockdata / prev "
                    "marketcap payload all absent) — tiles degrade to weight_proxy")
    if caps:
        static = _load_static_caps()
        if static:
            for t in symbols:
                # fill gaps everywhere; force the dual-class split even when the
                # nightly record carried a whole-company cap for one class.
                if caps.get(t, 0) <= 0 or t in _DUAL_CLASS:
                    if t in static:
                        caps[t] = static[t]
        caps = _complete_caps(caps, symbols)
    intraday = _load_intraday(symbols)
    live_q = _fetch_live(symbols) if live else {}

    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    payload = hm.build_heatmap(
        constituents, closes,
        industry_map=industry_map,
        caps=caps or None,
        weights_in_sector=weights or None,
        intraday_bars=intraday or None,
        live=live_q or None,
        generated_utc=generated_utc,
    )
    payload["size_basis"] = "marketcap" if caps else "weight_proxy"
    # Tile clicks open the Terminal (not the retired single-stock analyzer) — matches
    # the cn/hk/ca heatmaps in engine/market_heatmap.py.
    payload["stock_url"] = "https://app.mastermind-x.com/terminal?symbol="

    outdir = site / "marketdata"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "sp500_heatmap.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s — %d tiles, %d/%d timeframes live, size=%s, src=%s",
             out, payload["n_tiles"],
             sum(1 for t in payload["timeframes"] if t["available"]),
             len(payload["timeframes"]), payload["size_basis"], payload["source"])
    return payload


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build the S&P 500 sector heatmap feed")
    ap.add_argument("--no-live", action="store_true", help="skip the live snapshot splice")
    ap.add_argument("--refresh-caps", action="store_true",
                    help="rebuild the real market-cap reference cache via Polygon "
                         "(no-op while the cache is fresh; see --force)")
    ap.add_argument("--refresh-caps-only", action="store_true",
                    help="refresh the cap cache and exit without building the payload "
                         "(the nightly pre-render step)")
    ap.add_argument("--force", action="store_true",
                    help="refresh the cap cache even when it is fresh")
    args = ap.parse_args(argv)

    if args.refresh_caps or args.refresh_caps_only:
        refresh_caps(_load_constituents(), force=args.force)
        if args.refresh_caps_only:
            return 0
    build(live=not args.no_live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
