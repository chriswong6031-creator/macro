"""Deal-target price backfill for the merger-arb lane (P1.2).

Most US deal targets are already priced by the breadth caches, and foreign ones by the
stock-search closes — but some (cross-listed ADRs from 6-K filers, small/OTC names) sit in
none of those panels, so the arb lane has no live price for them. This fetches recent closes
for exactly those deal-target tickers via yfinance and caches them where engine._closes_panel
reads them. Bounded (only arb-category situations carrying a deal price), best-effort, no key.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from lib import config

log = logging.getLogger(__name__)
GROUP = "special_situations"
# common-stock-ish symbol (optionally exchange-suffixed); excludes the "NAN" null artifact and
# hyphenated preferred classes (e.g. NSA-PB) which aren't clean arb targets.
_TKR_RE = re.compile(r"[A-Z0-9]{1,6}(\.[A-Z]{1,3})?$")


def _plausible_ticker(t: str) -> bool:
    return bool(t) and t != "NAN" and bool(_TKR_RE.fullmatch(t))


def deal_target_tickers() -> list[str]:
    """Tickers of arb-category situations (Acquisitions / Tender Offers / Going-Private) that
    carry an LLM-extracted deal price — the ones the arb lane needs a live price for."""
    import json
    from engine import special_situations as sse
    from engine import special_arb as arb
    df = sse.build_situations()
    if df is None or df.empty:
        return []
    ok = df[(df.status == "ok") & df.category.isin(list(arb.ARB_CATEGORIES))]
    out: set[str] = set()
    for _, r in ok.iterrows():
        lt = r.get("llm_terms")
        if not lt or (isinstance(lt, float) and pd.isna(lt)):
            continue
        try:
            terms = arb.parse_terms(json.loads(lt) if isinstance(lt, str) else lt)
        except Exception:  # noqa: BLE001
            continue
        if not terms.get("price_per_share"):
            continue
        tk = str(r.get("ticker") or "").upper().strip()
        if _plausible_ticker(tk):
            out.add(tk)
    return sorted(out)


def _path():
    p = config.data_dir() / GROUP / "arb_prices.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch_arb_prices(start: str = "2026-01-01") -> int:
    """Backfill closes (yfinance) for deal-target tickers NOT already in the close panel.
    Appends to data/special_situations/arb_prices.parquet. Returns tickers added; 0 / no-op
    on outage. Best-effort — degrades silently so it never breaks the build."""
    from engine import special_situations as sse
    need = deal_target_tickers()
    if not need:
        return 0
    try:
        panel = sse._closes_panel()
        have = set(panel.columns) if panel is not None and not panel.empty else set()
    except Exception:  # noqa: BLE001
        have = set()
    todo = [t for t in need if t not in have and t.split(".")[0] not in have]
    if not todo:
        return 0
    try:
        import yfinance as yf
    except Exception:  # noqa: BLE001
        return 0
    frames = []
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        try:
            df = yf.download(batch, start=start, auto_adjust=True, progress=False, threads=True)
            close = df["Close"] if "Close" in df else df
            if isinstance(close, pd.Series):
                close = close.to_frame(batch[0])
            frames.append(close)
        except Exception as e:  # noqa: BLE001
            log.warning("special_situations arb price backfill batch failed: %s", e)
    if not frames:
        return 0
    new = pd.concat(frames, axis=1)
    new = new.loc[:, ~new.columns.duplicated()].dropna(how="all")
    out = _path()
    if out.exists():
        try:
            old = pd.read_parquet(out)
            new = pd.concat([old, new], axis=1)
            new = new.loc[:, ~new.columns.duplicated()]
        except Exception:  # noqa: BLE001
            pass
    new.to_parquet(out)
    log.info("special_situations arb price backfill: +%d deal-target tickers (%d total)",
             len(todo), new.shape[1])
    return len(todo)
