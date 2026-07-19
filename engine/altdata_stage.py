"""Read-only alt-data projection for the Stage Analysis page (SGA masterplan §W4).

`attention_for(tickers, root)` joins three DISPLAY-ONLY attention substrates into a
per-ticker dict the page renders as fade-risk / crowding chips (never a gate — SGA-R2/R4;
these are context, never scored legs, never sizing inputs):

  trends  data/google_trends/<TICKER>.parquet  weekly Google search interest (0-100)
          -> {latest, wow_pct, spark:[...≤12 weekly points]}
  wiki    data/attention/<TICKER>.parquet      offshore (en.wikipedia.org) pageviews
          -> {z_90d, note}   robust median/MAD abnormal-attention z (mirrors
                             scripts.build_site._attention_z math; NOT imported)
  wsb     data/quiver/wallstreetbets.parquet   Quiver r/wallstreetbets mention counts
          -> {mentions, rank}   latest-day mention count + cross-sectional rank

EVERYTHING fail-open: a missing file / column / bad row degrades that leg to None; a
missing ticker degrades all three to None; NO network, NO writes. Safe to call from a
render path — a broken store never crashes the build.

HONEST FRAMING (SGA-R2/R4, wiki_pageviews docstring law): an attention SPIKE is a
CROWDING CAUTION — over-extension / fade-risk — not a buy signal. The `note` field
carries that plain-word framing so the page can never present attention as bullish.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_SPARK_WEEKS = 12          # weekly points kept for the trends sparkline
_Z_WINDOW = 90             # wiki abnormal-attention baseline window (matches config.yml)
_RECENT_D = 5              # wiki trailing-mean window (matches build_site._attention_z)

# The one honest framing line the page must carry beside any attention chip. Attention
# is a fade-risk / crowding caution, never a directional buy signal (Da-Engelberg-Gao;
# wiki_pageviews docstring law).
_FADE_NOTE = "attention spike = crowding caution, not a buy sign"
_FADE_NOTE_ZH = "关注度飙升 = 拥挤警示，不是买入信号"


def _data_root(root: str | Path | None) -> Path:
    """Resolve the data root: an explicit override (tests) or config.data_dir()."""
    if root is not None:
        return Path(root)
    try:
        return config.data_dir()
    except Exception:  # noqa: BLE001 — config unreadable -> a non-existent path (all None)
        return Path("/nonexistent-altdata-root")


def _norm_ticker(tk: str) -> str:
    return str(tk).strip().upper()


# ------------------------------------------------------------------ Google Trends ----

def _trends_leg(root: Path, ticker: str) -> dict | None:
    """{latest, wow_pct, spark:[...≤12 weekly points]} from data/google_trends/<T>.parquet.

    `latest` = most-recent weekly interest (0-100). `wow_pct` = week-over-week percent
    change of interest (None when the prior week is absent or zero). `spark` = up to the
    last 12 weekly interest points (oldest→newest) for the row sparkline."""
    p = root / "google_trends" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001 — unreadable parquet -> no leg
        return None
    if df is None or df.empty or "interest" not in df.columns:
        return None
    s = pd.to_numeric(df["interest"], errors="coerce").dropna()
    if s.empty:
        return None
    try:
        s = s.sort_index()
    except Exception:  # noqa: BLE001 — odd index -> keep native order
        pass
    vals = [float(v) for v in s.tolist()]
    latest = vals[-1]
    wow_pct: float | None = None
    if len(vals) >= 2:
        prev = vals[-2]
        if prev and prev != 0.0:
            wow_pct = round((latest - prev) / prev * 100.0, 1)
    spark = [round(v, 1) for v in vals[-_SPARK_WEEKS:]]
    return {"latest": round(latest, 1), "wow_pct": wow_pct, "spark": spark}


# ------------------------------------------------------------------ Wikipedia ----

def _abnormal_z(views: pd.Series, z_window: int = _Z_WINDOW,
                recent_d: int = _RECENT_D) -> float | None:
    """Causal robust abnormal-attention z: trailing-`recent_d` log-views mean vs a
    median/MAD baseline over the STRICTLY-PRIOR `z_window` days (no look-ahead).

    Mirrors scripts.build_site._attention_z EXACTLY (re-implemented, not imported, to
    keep this engine free of the build_site render module): pageview counts are heavily
    right-skewed → log1p + median/MAD; clipped to [-3, +6] for display."""
    try:
        s = np.log1p(pd.to_numeric(views, errors="coerce").dropna().astype(float))
    except Exception:  # noqa: BLE001
        return None
    if len(s) < z_window // 2 + recent_d:
        return None
    recent = float(s.iloc[-recent_d:].mean())
    base = s.iloc[-(z_window + recent_d):-recent_d].dropna()   # strictly prior → causal
    if len(base) < 20:
        return None
    med = float(base.median())
    mad = float((base - med).abs().median())
    scale = 1.4826 * mad if mad > 0 else float(base.std() or 0.0)
    if not scale:
        return None
    return float(np.clip((recent - med) / scale, -3.0, 6.0))


def _wiki_leg(root: Path, ticker: str) -> dict | None:
    """{z_90d, note, note_zh} from data/attention/<T>.parquet (offshore pageviews).

    z_90d is the abnormal-attention z (median/MAD, causal). The note is the mandatory
    fade-risk framing — an attention spike is a crowding CAUTION, not a buy sign."""
    p = root / "attention" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or "views" not in df.columns:
        return None
    try:
        z = _abnormal_z(df["views"])
    except Exception:  # noqa: BLE001
        return None
    if z is None:
        return None
    return {"z_90d": round(z, 2), "note": _FADE_NOTE, "note_zh": _FADE_NOTE_ZH}


# ------------------------------------------------------------------ WSB (Quiver) ----

@lru_cache(maxsize=8)
def _wsb_latest(path_str: str, mtime: float) -> dict[str, dict]:
    """{TICKER: {mentions, rank}} for the most-recent WSB collection date.

    Cached on (path, mtime) so a render pass reads the shared parquet once, not once
    per ticker. Rank is a dense cross-sectional rank by mention count (1 = most-
    mentioned that day). Empty dict on any read/shape problem (fail-open)."""
    try:
        df = pd.read_parquet(path_str)
    except Exception:  # noqa: BLE001
        return {}
    if df is None or df.empty:
        return {}
    cols = {c.lower(): c for c in df.columns}
    tk_col = cols.get("ticker")
    ct_col = cols.get("count")
    if tk_col is None or ct_col is None:
        return {}
    dt_col = cols.get("_collected") or cols.get("date")
    try:
        if dt_col is not None:
            latest_val = df[dt_col].max()
            day = df[df[dt_col] == latest_val].copy()
        else:
            day = df.copy()
    except Exception:  # noqa: BLE001
        day = df.copy()
    if day.empty:
        return {}
    day = day.copy()
    day["_ct"] = pd.to_numeric(day[ct_col], errors="coerce")
    day = day.dropna(subset=["_ct"])
    if day.empty:
        return {}
    # dense rank by mention count, most-mentioned = 1
    day["_rank"] = day["_ct"].rank(method="min", ascending=False).astype(int)
    out: dict[str, dict] = {}
    for _, r in day.iterrows():
        tk = _norm_ticker(r[tk_col])
        if not tk:
            continue
        # first occurrence wins if a ticker appears twice in one day snapshot
        out.setdefault(tk, {"mentions": int(r["_ct"]), "rank": int(r["_rank"])})
    return out


def _wsb_map(root: Path) -> dict[str, dict]:
    """The cached latest-day WSB map, keyed on the parquet's current mtime."""
    p = root / "quiver" / "wallstreetbets.parquet"
    if not p.exists():
        return {}
    try:
        mtime = p.stat().st_mtime
    except Exception:  # noqa: BLE001
        return {}
    return _wsb_latest(str(p), mtime)


# ------------------------------------------------------------------ public API ----

def attention_for(tickers, root: str | Path | None = None) -> dict[str, dict]:
    """Per-ticker alt-data attention projection for the Stage Analysis page.

    Returns {TICKER: {"trends": {...}|None, "wiki": {...}|None, "wsb": {...}|None}} for
    every requested ticker. READ-ONLY, NO network, fully fail-open — a missing store,
    column, or ticker just yields None for that leg (never raises).

    Args:
        tickers: iterable of ticker symbols (case-insensitive; deduped, order-preserving).
        root:    data-root override (tests); defaults to config.data_dir().
    """
    data_root = _data_root(root)

    # order-preserving dedupe of the requested tickers
    seen: set[str] = set()
    order: list[str] = []
    for tk in (tickers or []):
        n = _norm_ticker(tk)
        if n and n not in seen:
            seen.add(n)
            order.append(n)

    # WSB is one shared parquet → read it ONCE for the whole batch (not per ticker)
    try:
        wsb_map = _wsb_map(data_root)
    except Exception:  # noqa: BLE001 — the whole map fails open
        wsb_map = {}

    out: dict[str, dict] = {}
    for tk in order:
        try:
            trends = _trends_leg(data_root, tk)
        except Exception:  # noqa: BLE001
            trends = None
        try:
            wiki = _wiki_leg(data_root, tk)
        except Exception:  # noqa: BLE001
            wiki = None
        wsb = wsb_map.get(tk)
        out[tk] = {"trends": trends, "wiki": wiki, "wsb": wsb}
    return out
