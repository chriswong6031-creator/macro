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

import json
import logging
import os
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


# ====================================================================
# Alt-data trending builder (SGA-2 §E — the Alt-Data surface artifact)
# ====================================================================
# Reads the four EquityDesk seed match tables (altdata_{gt,reddit,tiktok,wiki})
# joined to their raw trending-topic tables, and emits
# data/stage_analysis/altdata_trending.json — a per-source list of trending
# topics matched (by their LLM) to a ticker, with the growth metrics and the
# match explanation preserved. DISPLAY-TIER: context/curiosity only, never a
# gate, score leg, or sizing input (SGA-R2/R4). TikTok is flagged 'seed_only'
# because we have no lawful live TikTok source yet — the page must disclose it.
#
# EVERYTHING fail-open: a missing seed dir/file/column degrades that source to
# an empty list; the artifact always writes with the full source scaffold so a
# broken store never blanks the page or crashes the build.

_BACKFILL_SUBDIR = ("stage_analysis", "backfill")
_TRENDING_REL = ("stage_analysis", "altdata_trending.json")

# Per-source seed-table + join spec. Each source maps its raw trending-topic
# table (yoy/chg metrics) to the matched table (topic -> ticker + explanation).
#   match_file  : altdata_<src>.parquet  (topic-key, ticker, company_name, explanation, classifier/type, page_description)
#   topic_key   : the column both tables share for the join
#   live        : do we have a lawful forward collector? tiktok = False -> seed_only
_SOURCE_SPEC = {
    "google": {
        "match_file": "altdata_gt.parquet",
        "topic_key": "google_query",
        "trend_file": "trending_gt.parquet",
        "trend_key": "google_query",
        "label_col": "request_name",       # human-readable topic name
        "type_col": "request_type",
        "desc_col": "description_by_llm",
        "yoy_col": "index_growth_yoy_w1",   # already a percent
        "yoy_scale": 1.0,
        "chg_col": "gt_index_growth_change_w1",
        "chg_scale": 1.0,
        "live": True,
    },
    "reddit": {
        "match_file": "altdata_reddit.parquet",
        "topic_key": "subreddit",
        "trend_file": "top_growing_subreddits.parquet",
        "trend_key": "subreddit",
        "label_col": "subreddit",
        "type_col": "tag_classification",
        "desc_col": "subreddit_description",
        "yoy_col": "subscriber_yoy_growth_pct",       # 0-1 fraction
        "yoy_scale": 100.0,
        "chg_col": None,                              # derived: (yoy - yoy_2w_ago)
        "chg_2w_ago_col": "subscriber_yoy_growth_pct_2w_ago",
        "chg_scale": 100.0,
        "live": True,
    },
    "wikipedia": {
        "match_file": "altdata_wiki.parquet",
        "topic_key": "wikipage",
        "trend_file": "wiki_top_pages.parquet",
        "trend_key": "wikipage",
        "label_col": "wikipage",
        "type_col": "classifier",
        "desc_col": "page_description",
        "yoy_col": "momentum",              # traffic momentum percent
        "yoy_scale": 1.0,
        "chg_col": None,
        "chg_scale": 1.0,
        "live": True,
    },
    "tiktok": {
        "match_file": "altdata_tiktok.parquet",
        "topic_key": "hashtag",
        "trend_file": "top_growing_tiktok.parquet",
        "trend_key": "main_hashtag",
        "label_col": "hashtag",
        "type_col": "short_classification_by_chatgpt",
        "desc_col": "description_by_chatgpt",
        "yoy_col": None,                    # derived: current_value vs value_1y_ago
        "yoy_cur_col": "current_value",
        "yoy_prev_col": "value_1y_ago",
        "chg_col": None,                    # derived: grid_current vs grid_1w_ago
        "chg_cur_col": "grid_current",
        "chg_prev_col": "grid_1w_ago",
        "chg_scale": 1.0,
        "live": False,                      # NO lawful live TikTok source -> seed_only
    },
}

# per-source cap on rows emitted (page density — keep the strongest movers)
_MAX_ROWS_PER_SOURCE = 150


def _seed_dir(root: Path) -> Path:
    return root.joinpath(*_BACKFILL_SUBDIR)


def _atomic_write_json(path: Path, obj) -> None:
    """Write JSON via tmp-then-rename (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _read_seed(seed_dir: Path, fname: str) -> pd.DataFrame | None:
    p = seed_dir / fname
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001 — unreadable seed -> no rows
        return None
    if df is None or df.empty:
        return None
    return df


def _clean_str(v) -> str | None:
    if v is None:
        return None
    try:
        if isinstance(v, float) and np.isnan(v):
            return None
    except Exception:  # noqa: BLE001
        pass
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    return s


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return f


def _latest_per_key(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Collapse to one row per topic key — the most-recent by any date-ish column."""
    date_col = None
    for c in ("period", "as_of_date", "created", "matching_date", "created_date"):
        if c in df.columns:
            date_col = c
            break
    if date_col is not None:
        try:
            order = pd.to_datetime(df[date_col], errors="coerce")
            df = df.assign(_ord=order).sort_values("_ord")
        except Exception:  # noqa: BLE001
            pass
    return df.drop_duplicates(subset=[key], keep="last")


def _source_rows(src: str, spec: dict, seed_dir: Path) -> list[dict]:
    """Build the trending-topic row list for one source (fail-open -> [])."""
    match = _read_seed(seed_dir, spec["match_file"])
    if match is None or spec["topic_key"] not in match.columns:
        return []
    match = _latest_per_key(match, spec["topic_key"])

    trend = _read_seed(seed_dir, spec["trend_file"])
    trend_idx: dict = {}
    if trend is not None and spec["trend_key"] in trend.columns:
        trend = _latest_per_key(trend, spec["trend_key"])
        for _, tr in trend.iterrows():
            k = _clean_str(tr.get(spec["trend_key"]))
            if k is not None:
                trend_idx.setdefault(k, tr)

    rows: list[dict] = []
    for _, m in match.iterrows():
        topic_key = _clean_str(m.get(spec["topic_key"]))
        if topic_key is None:
            continue
        ticker = _clean_str(m.get("ticker"))
        company = _clean_str(m.get("company_name"))
        explanation = _clean_str(m.get("explanation"))
        # a match with no ticker is not useful on the ticker-linked surface
        if ticker is None:
            continue
        tr = trend_idx.get(topic_key)

        # human label + type + description: prefer the trending table, fall back to match
        label = None
        typ = None
        desc = None
        if tr is not None:
            label = _clean_str(tr.get(spec["label_col"]))
            typ = _clean_str(tr.get(spec.get("type_col")))
            desc = _clean_str(tr.get(spec.get("desc_col")))
        if label is None:
            label = _clean_str(m.get(spec["label_col"])) or topic_key
        if typ is None:
            typ = _clean_str(m.get("classifier")) or _clean_str(m.get("request_type"))
        if desc is None:
            desc = _clean_str(m.get("page_description"))

        yoy = _source_yoy(spec, tr)
        chg = _source_chg(spec, tr)

        rows.append({
            "topic": label,
            "yoy_pct": yoy,
            "chg_2w_pct": chg,
            "type": typ,
            "description": desc,
            "matched_ticker": ticker,
            "matched_company": company,
            "explanation": explanation,
        })

    # rank strongest movers first (yoy desc, None last), cap
    rows.sort(key=lambda r: (r["yoy_pct"] is None, -(r["yoy_pct"] or 0.0)))
    return rows[:_MAX_ROWS_PER_SOURCE]


def _source_yoy(spec: dict, tr) -> float | None:
    if tr is None:
        return None
    if spec.get("yoy_col"):
        v = _num(tr.get(spec["yoy_col"]))
        return round(v * spec.get("yoy_scale", 1.0), 1) if v is not None else None
    # derived yoy: current vs 1y-ago index
    cur = _num(tr.get(spec.get("yoy_cur_col")))
    prev = _num(tr.get(spec.get("yoy_prev_col")))
    if cur is None or prev is None or prev == 0.0:
        return None
    return round((cur - prev) / prev * 100.0, 1)


def _source_chg(spec: dict, tr) -> float | None:
    if tr is None:
        return None
    if spec.get("chg_col"):
        v = _num(tr.get(spec["chg_col"]))
        return round(v * spec.get("chg_scale", 1.0), 1) if v is not None else None
    if spec.get("chg_2w_ago_col") and spec.get("yoy_col"):
        cur = _num(tr.get(spec["yoy_col"]))
        ago = _num(tr.get(spec["chg_2w_ago_col"]))
        if cur is None or ago is None:
            return None
        return round((cur - ago) * spec.get("chg_scale", 1.0), 1)
    if spec.get("chg_cur_col"):
        cur = _num(tr.get(spec["chg_cur_col"]))
        prev = _num(tr.get(spec["chg_prev_col"]))
        if cur is None or prev is None:
            return None
        return round(cur - prev, 1)
    return None


def build_altdata_trending(root: str | Path | None = None) -> dict:
    """Build + write data/stage_analysis/altdata_trending.json (SGA-2 §E).

    Returns the artifact dict (also written to disk). DISPLAY-TIER, read-only
    over the committed EquityDesk seeds, fully fail-open: a missing seed dir or
    unreadable table degrades that source to an empty list; the artifact always
    carries the full four-source scaffold + a per-ticker rollup.

    Args:
        root: data-root override (tests); defaults to config.data_dir().
    """
    data_root = _data_root(root)
    seed_dir = _seed_dir(data_root)

    sources: dict[str, dict] = {}
    per_ticker: dict[str, dict] = {}
    for src, spec in _SOURCE_SPEC.items():
        try:
            rows = _source_rows(src, spec, seed_dir)
        except Exception:  # noqa: BLE001 — one bad source never sinks the others
            log.warning("altdata_trending: source %s failed open", src, exc_info=True)
            rows = []
        seed_only = not spec["live"]
        sources[src] = {
            "source": src,
            "live": spec["live"],
            "seed_only": seed_only,
            "note": ("seed backfill only — no lawful live source yet"
                     if seed_only else "seeded from backfill; live collector forward"),
            "topics": rows,
        }
        # per-ticker rollup: which sources mention each ticker
        for r in rows:
            tk = r["matched_ticker"]
            entry = per_ticker.setdefault(tk, {"ticker": tk, "sources": [], "topics": []})
            if src not in entry["sources"]:
                entry["sources"].append(src)
            entry["topics"].append({
                "source": src,
                "topic": r["topic"],
                "yoy_pct": r["yoy_pct"],
                "explanation": r["explanation"],
            })

    artifact = {
        "schema": "altdata_trending.v1",
        "is_context_only": True,
        "display_only": True,
        "note": ("Alt-data trending topics matched to tickers by the source LLM. "
                 "Context/curiosity only — never a signal, gate, or sizing input."),
        "note_zh": "另类数据热门话题（LLM 匹配到个股）。仅供参考，绝非信号、门槛或仓位依据。",
        "sources": sources,
        "by_ticker": per_ticker,
        "counts": {src: len(sources[src]["topics"]) for src in sources},
    }

    try:
        out_path = data_root.joinpath(*_TRENDING_REL)
        _atomic_write_json(out_path, artifact)
    except Exception:  # noqa: BLE001 — a write failure never crashes the build
        log.warning("altdata_trending: write failed (fail-open)", exc_info=True)
    return artifact
