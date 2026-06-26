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
    p = _data("sp500_heatmap", "gics_industry.json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("industry map unreadable: %s", e)
    return {}


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


def refresh_caps(constituents: pd.DataFrame) -> None:
    """(Re)build data/sp500_heatmap/reference.parquet with shares + SIC industry
    from Polygon /v3/reference/tickers/{ticker}. Best-effort; never fatal."""
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
    caps = _load_caps(closes)
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
                    help="rebuild the real market-cap reference cache via Polygon")
    args = ap.parse_args(argv)

    if args.refresh_caps:
        refresh_caps(_load_constituents())
    build(live=not args.no_live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
