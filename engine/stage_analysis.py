"""Stage Analysis (SGA) — universe fan-out + stage_context.v1 feed.

Program: research/STAGE_ANALYSIS_MASTERPLAN.md (rulings SGA-R1..R8).

This engine classifies the full equity universe (SGA-R3) with the Weinstein
weekly state machine (`engine/weinstein_stage.classify`, built by a sibling
lane — its API is pinned below), computes a deterministic, display-tier
`sga_score` (SGA-R4), joins earnings-call context (SGA-R5, context-only) and
the T1/T2/T3 confluence cascade (read-only from signal_gate.json), and
assembles the `stage_context.v1` contract (masterplan §2) with a same-day
idempotent change feed (mirrors engine/special_sits_intel.py:1018-1134).

Everything here is DISPLAY-TIER and CONTEXT-ONLY: no scored surface, gate, or
sizing consumes any number written by this module. Every input is fail-open —
a missing store, absent signal_gate.json, absent SPY, or a classifier that is
not yet on disk never crashes a build; the affected names simply drop out or
carry null context.

classify() contract (pinned — engine/weinstein_stage.py, sibling lane):

    classify(close: pd.Series, volume: pd.Series, bench_close: pd.Series) -> dict

    with (at least) these keys:
        stage            int in {1,2,3,4} or None (None = unclassifiable)
        weeks_in_stage   int  (completed weekly bars in the current stage)
        fresh            bool (Stage 2 AND weeks_in_stage <= 10)
        n_weeks          int  (completed weekly bars of history)
        ma30_slope_pct5w float (30w SMA slope per 5 weeks, %)
        pct_vs_ma30      float (close/ma30 - 1, %)
        mansfield_rs     float (Mansfield RS vs bench, %)
        vol_ratio        float (recent vol / baseline vol)
        event            str|None  breakout|trendline_recapture|pullback_resume
        arc_pos          float in [0,1)  position along the idealized cycle arc

A name with n_weeks < 45 (SGA-R3 floor) is "too young to stage" — counted,
never hidden.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Repo root = two levels up from this file (engine/stage_analysis.py -> repo).
_ENGINE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ENGINE_DIR.parent

# ── Constants (SGA-R3 / SGA-R4 — pinned; change only with a ruling amendment) ──
MIN_WEEKS = 45          # SGA-R3 history floor (completed weekly bars)
FRESH_MAX_WEEKS = 10    # SGA-R1 fresh Stage 2 ceiling
MAX_WORKERS_CAP = 4     # masterplan W1 — off the render-critical path, capped at 4

# sga_score weights (SGA-R4 — deterministic blend, sum of positive components).
W_FRESHNESS = 25
W_SLOPE_PCTILE = 25
W_MANSFIELD_CHIP = 10
W_VOLUME = 15
W_GATE_T1T2 = 25
W_GATE_T3 = 15
EXTENSION_PENALTY_MAX = 20   # up to -20 beyond |pct_vs_ma30| > 15%
EXTENSION_THRESH = 15.0      # % from ma30 where the penalty starts

# Capped-list sizes (masterplan §2 — keep the artifact well under 1 MB).
TOP_STAGE2_CAP = 60
WARNINGS_CAP = 20
CHANGES_CAP = 80

# Earnings tone thresholds (masterplan §2).
TONE_UP = 0.3
TONE_DOWN = -0.3


# ---------------------------------------------------------------------------
# Paths / roots
# ---------------------------------------------------------------------------
def _data_root(root: Path | None = None) -> Path:
    """Resolve the data/ root (override for tests)."""
    if root is not None:
        return Path(root)
    env = os.environ.get("MACRO_DATA_ROOT")
    if env:
        return Path(env)
    return _REPO_ROOT / "data"


def _repo_root(root: Path | None = None) -> Path:
    """Resolve the repo root (data root's parent) so site/ is reachable."""
    dr = _data_root(root)
    return dr.parent


# ---------------------------------------------------------------------------
# Universe (SGA-R3)
# ---------------------------------------------------------------------------
def build_universe(root: Path | None = None) -> dict[str, dict]:
    """Union of tickers across the three stores (SGA-R3), deduped.

    Returns {TICKER: {"company": str, "sector": str, "sources": [..]}}.
    Company + sector come from membership.parquet where known; otherwise
    fallback company = ticker, sector = 'Unknown'. Fail-open: any unreadable
    store is skipped, never fatal.
    """
    dr = _data_root(root)
    meta: dict[str, dict] = {}

    # --- membership.parquet: names + sectors for SP1500 actives ---
    name_by: dict[str, str] = {}
    sector_by: dict[str, str] = {}
    active_tickers: set[str] = set()
    mem_path = dr / "universe" / "membership.parquet"
    if mem_path.exists():
        try:
            import pandas as pd
            m = pd.read_parquet(mem_path)
            for _, r in m.iterrows():
                tk = str(r.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                nm = r.get("name")
                sec = r.get("sector")
                if nm is not None and str(nm).strip():
                    name_by.setdefault(tk, str(nm).strip())
                if sec is not None and str(sec).strip():
                    sector_by.setdefault(tk, str(sec).strip())
                if bool(r.get("active")):
                    active_tickers.add(tk)
        except Exception as e:  # noqa: BLE001 — fail-open
            log.warning("stage_analysis: membership.parquet unreadable (%s)", e)

    # --- name/sector fallback for names outside SP1500 (Russell, baskets, intl) ---
    # The committed EquityDesk overview yardstick carries a clean company name
    # (name_ui) and a GICS sector (same taxonomy as membership.parquet) for the
    # whole universe. Reference facts only — never their computed stage/scores.
    # setdefault: membership's canonical GICS labels win where present.
    ov_path = dr / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    if ov_path.exists():
        try:
            import pandas as pd
            ov = pd.read_parquet(ov_path, columns=["ticker", "name_ui", "gics_sector"])
            for _, r in ov.iterrows():
                tk = str(r.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                nm = r.get("name_ui")
                sec = r.get("gics_sector")
                if pd.notna(nm) and str(nm).strip():
                    name_by.setdefault(tk, str(nm).strip())
                if pd.notna(sec) and str(sec).strip() and str(sec).strip().lower() != "nan":
                    sector_by.setdefault(tk, str(sec).strip())
        except Exception as e:  # noqa: BLE001 — fail-open; names simply fall back to ticker
            log.warning("stage_analysis: overview name/sector fallback unreadable (%s)", e)

    def _add(tk: str, source: str) -> None:
        tk = tk.strip().upper()
        if not tk:
            return
        d = meta.setdefault(tk, {"company": None, "sector": None, "sources": []})
        if source not in d["sources"]:
            d["sources"].append(source)

    # --- data/baskets/ohlcv/*.parquet ---
    ohlcv_dir = dr / "baskets" / "ohlcv"
    if ohlcv_dir.is_dir():
        try:
            for p in ohlcv_dir.glob("*.parquet"):
                _add(p.stem, "ohlcv")
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: baskets/ohlcv glob failed (%s)", e)

    # --- SP1500 actives from membership ---
    for tk in active_tickers:
        _add(tk, "membership")

    # --- data/stocks/*.parquet ---
    stocks_dir = dr / "stocks"
    if stocks_dir.is_dir():
        try:
            for p in stocks_dir.glob("*.parquet"):
                _add(p.stem, "stocks")
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: stocks glob failed (%s)", e)

    # Attach company/sector (fallback ticker / 'Unknown').
    for tk, d in meta.items():
        d["company"] = name_by.get(tk) or tk
        d["sector"] = sector_by.get(tk) or "Unknown"

    return meta


# ---------------------------------------------------------------------------
# Per-ticker price loader (SGA-R3 — baskets/ohlcv preferred, deep store fallback)
# ---------------------------------------------------------------------------
def _load_prices(ticker: str, dr: Path):
    """Return (close, volume) daily series for a ticker, or (None, None).

    Prefers baskets/ohlcv (full adjusted series per masterplan trap §7); falls
    back to data/stocks/. Fail-open on any read error.
    """
    import pandas as pd

    for sub in ("baskets/ohlcv", "stocks"):
        p = dr / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: %s unreadable (%s)", p, e)
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        close = df["close"].dropna()
        vol = df["volume"].dropna() if "volume" in df.columns else pd.Series(dtype="float64")
        if len(close) == 0:
            continue
        return close, vol
    return None, None


def _load_bench_close(dr: Path):
    """SPY daily close (single benchmark, SGA-R2). Fail-open -> None."""
    import pandas as pd

    p = dr / "yahoo" / "SPY.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_analysis: SPY.parquet unreadable (%s)", e)
        return None
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else ("close_price" if "close_price" in df.columns else None)
    if col is None:
        return None
    s = df[col].dropna()
    return s if len(s) else None


# ---------------------------------------------------------------------------
# classify shim (calls the sibling-lane weinstein_stage.classify)
# ---------------------------------------------------------------------------
def _classify(close, volume, bench_close) -> dict | None:
    """Call engine.weinstein_stage.classify, fail-open to None.

    Kept as a thin indirection so tests can monkeypatch this symbol (or the
    underlying module) and the suite runs standalone before the sibling lane
    lands weinstein_stage.py.
    """
    try:
        from engine import weinstein_stage  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — module not built yet in this lane
        return None
    try:
        return weinstein_stage.classify(close, volume, bench_close)
    except Exception as e:  # noqa: BLE001 — a single bad name never breaks the fan-out
        log.warning("stage_analysis: classify raised (%s)", e)
        return None


# ---------------------------------------------------------------------------
# Multiprocessing fan-out (mirrors build_stock_library worker pattern)
# ---------------------------------------------------------------------------
# Read-only per-worker context, installed once via the pool initializer.
_SHARED: dict = {}


def _winit(data_root_str: str) -> None:
    _SHARED["dr"] = Path(data_root_str)
    _SHARED["bench"] = _load_bench_close(_SHARED["dr"])


def _classify_one(ticker: str) -> tuple[str, dict | None]:
    """Worker: load prices, classify one ticker against the shared bench."""
    dr = _SHARED.get("dr")
    bench = _SHARED.get("bench")
    if dr is None:
        return ticker, None
    close, vol = _load_prices(ticker, dr)
    if close is None:
        return ticker, None
    res = _classify(close, vol, bench)
    return ticker, res


def _classify_universe(tickers: list[str], dr: Path,
                       max_workers: int | None = None) -> dict[str, dict | None]:
    """Fan classify across processes (capped at 4). Serial fallback on any
    pool failure or tiny universe."""
    if not tickers:
        return {}

    workers = _resolve_workers(max_workers)
    results: dict[str, dict | None] = {}

    if workers > 1 and len(tickers) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_winit,
                initargs=(str(dr),),
            ) as ex:
                for tk, res in ex.map(_classify_one, tickers, chunksize=16):
                    results[tk] = res
            return results
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("stage_analysis: parallel classify failed (%s) — serial fallback", e)
            results = {}

    # Serial path (also the test path): prime shared context in-process.
    _winit(str(dr))
    for tk in tickers:
        try:
            results[tk] = _classify_one(tk)[1]
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: serial classify %s failed (%s)", tk, e)
            results[tk] = None
    return results


def _resolve_workers(max_workers: int | None) -> int:
    """Resolve worker count. Precedence: explicit arg > STAGE_WORKERS env >
    cpu_count. Always capped at MAX_WORKERS_CAP (=4)."""
    n = max_workers
    if n is None:
        env = os.environ.get("STAGE_WORKERS")
        if env:
            try:
                n = int(env)
            except ValueError:
                n = None
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), MAX_WORKERS_CAP))


# ---------------------------------------------------------------------------
# Confluence gate tiers (SGA-R4 — read-only join, CSP read-gate precedent)
# ---------------------------------------------------------------------------
def _load_gate_tiers(repo_root: Path) -> dict[str, str]:
    """Read site/factordata/signal_gate.json -> {TICKER: 'T1'|'T2'|'T3'}.

    Read-only, fail-open (absent/unreadable/malformed -> {}). Only names with
    a non-null tier_cascade in {T1,T2,T3} are returned (T4 is a decline tier,
    not a confirmation).
    """
    p = repo_root / "site" / "factordata" / "signal_gate.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("stage_analysis: signal_gate.json unreadable (%s)", e)
        return {}
    verdicts = (d or {}).get("verdicts")
    if not isinstance(verdicts, dict):
        return {}
    out: dict[str, str] = {}
    for tk, v in verdicts.items():
        if not isinstance(v, dict):
            continue
        tier = v.get("tier_cascade")
        if tier in ("T1", "T2", "T3"):
            out[str(tk).strip().upper()] = tier
    return out


# ---------------------------------------------------------------------------
# Earnings-call scores join (SGA-R5 — context-only, fail-open)
# ---------------------------------------------------------------------------
def _tone_word(sentiment: float | None) -> str | None:
    """Map sentiment -> plain tone word (masterplan §2)."""
    if sentiment is None:
        return None
    try:
        s = float(sentiment)
    except (TypeError, ValueError):
        return None
    if s >= TONE_UP:
        return "upbeat"
    if s <= TONE_DOWN:
        return "downbeat"
    return "steady"


def _load_earnings_scores(dr: Path) -> dict[str, dict]:
    """Latest earnings-call score row per ticker.

    Merges two stores, live winning per ticker:
      1. committed cold-start SEED — data/stage_analysis/backfill/earnings_seed.parquet
         (the EquityDesk W5 backfill, present on every render/nightly so the earnings
         desk is populated from day one, before the Qwen worker has produced anything).
      2. live R2-fetched store — data/earnings_calls/scores.parquet (the Windows-PC Qwen
         worker's fresh calls, pulled by scripts/fetch_earnings_scores; absent until the
         worker runs). A live row for a ticker overrides its seed row.

    Fail-open per file -> {}. Returns {TICKER: {present, sentiment, performance,
    tone_word, tags, quarter, summary}}.
    """
    seed = _parse_earnings_parquet(dr / "stage_analysis" / "backfill" / "earnings_seed.parquet")
    live = _parse_earnings_parquet(dr / "earnings_calls" / "scores.parquet")
    seed.update(live)  # live (fresh worker output) overlays the backfill seed per ticker
    return seed


def _parse_earnings_parquet(p: Path) -> dict[str, dict]:
    """Parse one earnings-scores parquet into {TICKER: card}. Fail-open -> {}."""
    import pandas as pd

    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_analysis: earnings scores unreadable (%s) at %s", e, p.name)
        return {}
    if df is None or df.empty or "ticker" not in df.columns:
        return {}

    out: dict[str, dict] = {}
    # Latest by call_date if present, else last row wins.
    try:
        if "call_date" in df.columns:
            df = df.sort_values("call_date")
    except Exception:  # noqa: BLE001
        pass
    for _, r in df.iterrows():
        tk = str(r.get("ticker") or "").strip().upper()
        if not tk:
            continue
        sent = r.get("sentiment")
        perf = r.get("performance")
        sent = None if (sent is None or pd.isna(sent)) else float(sent)
        perf = None if (perf is None or pd.isna(perf)) else float(perf)
        tags = r.get("tags")
        tags = _coerce_tags(tags)
        qv = r.get("quarter")
        quarter = None if (qv is None or (not isinstance(qv, str) and pd.isna(qv))) else str(qv)
        tone = r.get("tone_word")
        tone = str(tone) if (tone is not None and not pd.isna(tone)) else _tone_word(sent)
        summ = r.get("summary")
        # Truncate to ~280 chars for the card; None when absent or NaN.
        if summ is None or (not isinstance(summ, str) and pd.isna(summ)):
            summ_card = None
        else:
            s = str(summ).strip()
            summ_card = (s[:277] + "…") if len(s) > 280 else (s or None)
        out[tk] = {
            "present": True,
            "sentiment": sent,
            "performance": perf,
            "tone_word": tone,
            "tags": tags,
            "quarter": quarter,
            "summary": summ_card,  # SGA W5: call_summary truncated to 280 chars
        }
    return out


def _coerce_tags(tags: Any) -> list[str]:
    """Tags may be a JSON string, a list, or NaN. Fail-open -> []."""
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, str):
        s = tags.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(t) for t in v]
        except Exception:  # noqa: BLE001
            return [s]
        return [s]
    # numpy array or other iterable
    try:
        return [str(t) for t in list(tags)]
    except Exception:  # noqa: BLE001
        return []


def _empty_earnings() -> dict:
    return {"present": False, "sentiment": None, "performance": None,
            "tone_word": None, "tags": [], "quarter": None, "summary": None}


# ---------------------------------------------------------------------------
# sga_score (SGA-R4 — deterministic blend, 0..100)
# ---------------------------------------------------------------------------
def _pctile(value: float | None, sorted_vals: list[float]) -> float:
    """Cross-sectional percentile of value in sorted_vals, in [0,1].
    Fail-open (empty population or null value) -> 0.5 (neutral)."""
    if value is None or not sorted_vals:
        return 0.5
    import bisect
    lo = bisect.bisect_left(sorted_vals, value)
    hi = bisect.bisect_right(sorted_vals, value)
    rank = (lo + hi) / 2.0
    return rank / len(sorted_vals)


def _compute_sga_score(rec: dict, slope_pctile: float, gate_tier: str | None) -> int:
    """Deterministic 0..100 blend (SGA-R4).

    Components (weights pinned in module constants):
      freshness       25  — fresh Stage 2 full credit; Stage 2 non-fresh scaled
      slope pctile    25  — cross-sectional ma30-slope-strength percentile
      mansfield chip  10  — mansfield_rs > 0
      volume conf     15  — vol_ratio scaled (>=1.5 full credit)
      gate presence   25  — T1/T2; 15 — T3
      extension pen  -20  — beyond |pct_vs_ma30| > 15%, linear decay to floor
    """
    stage = rec.get("stage")
    weeks = rec.get("weeks_in_stage") or 0
    fresh = bool(rec.get("fresh"))

    # Freshness component.
    if stage == 2 and fresh:
        freshness = W_FRESHNESS
    elif stage == 2:
        # Non-fresh Stage 2 decays with weeks past the fresh ceiling.
        over = max(0, weeks - FRESH_MAX_WEEKS)
        freshness = max(0.0, W_FRESHNESS * (1.0 - over / 40.0))
    else:
        freshness = 0.0

    # Slope strength (cross-sectional percentile, already in [0,1]).
    slope_comp = W_SLOPE_PCTILE * max(0.0, min(1.0, slope_pctile))

    # Mansfield RS chip.
    mrs = rec.get("mansfield_rs")
    mansfield_comp = W_MANSFIELD_CHIP if (mrs is not None and mrs > 0) else 0.0

    # Volume confirmation (vol_ratio >= 1.5 = full credit).
    vr = rec.get("vol_ratio")
    if vr is None:
        vol_comp = 0.0
    else:
        vol_comp = W_VOLUME * max(0.0, min(1.0, (float(vr) - 1.0) / 0.5))

    # Gate presence.
    if gate_tier in ("T1", "T2"):
        gate_comp = W_GATE_T1T2
    elif gate_tier == "T3":
        gate_comp = W_GATE_T3
    else:
        gate_comp = 0.0

    # Extension penalty (negative), up to -20 beyond |pct_vs_ma30| > 15%.
    pv = rec.get("pct_vs_ma30")
    if pv is None:
        ext_pen = 0.0
    else:
        excess = abs(float(pv)) - EXTENSION_THRESH
        if excess <= 0:
            ext_pen = 0.0
        else:
            # Linear decay: reaches full -20 at ~15pp beyond the threshold.
            ext_pen = -min(EXTENSION_PENALTY_MAX, EXTENSION_PENALTY_MAX * excess / 15.0)

    raw = freshness + slope_comp + mansfield_comp + vol_comp + gate_comp + ext_pen
    return int(round(max(0.0, min(100.0, raw))))


# ---------------------------------------------------------------------------
# Plain-word rationale (doctrine — no jargon)
# ---------------------------------------------------------------------------
def _why_bullets(rec: dict, gate_tier: str | None, earnings: dict,
                 blackout: bool) -> tuple[list[str], list[str]]:
    """2-3 plain-word EN/ZH bullet pairs. NO jargon (no z-score / n= / percentile /
    study names). Doctrine glance-tier language."""
    en: list[str] = []
    zh: list[str] = []
    weeks = rec.get("weeks_in_stage") or 0
    fresh = bool(rec.get("fresh"))
    pv = rec.get("pct_vs_ma30")

    # 1) Where it is in the cycle.
    if fresh:
        en.append(f"Early in its climb — {weeks} weeks up so far")
        zh.append(f"上升初期 — 已上行 {weeks} 周")
    else:
        en.append(f"Climbing for {weeks} weeks now")
        zh.append(f"已上行 {weeks} 周")

    # 2) Price vs the 30-week line, in plain words.
    if pv is not None:
        if pv > EXTENSION_THRESH:
            en.append("Already stretched well above its 30-week line — may need a rest")
            zh.append("已明显高于 30 周均线 — 可能需要回踩")
        elif pv > 0:
            en.append("Trading above its 30-week line — the trend is with it")
            zh.append("位于 30 周均线之上 — 趋势向好")
        else:
            en.append("Still near its 30-week line — not clear of it yet")
            zh.append("仍接近 30 周均线 — 尚未站稳")

    # 3) One extra confirming note (gate / earnings / blackout).
    if blackout:
        en.append("Earnings soon — wait, don't chase")
        zh.append("财报临近 — 先等待，不要追高")
    elif gate_tier in ("T1", "T2"):
        en.append("Also shows a strong confirmation from our other checks")
        zh.append("其他多项验证同样给出强确认")
    elif earnings.get("present") and earnings.get("tone_word") == "upbeat":
        en.append("Its last earnings call read upbeat")
        zh.append("最近一次财报电话会语气积极")

    return en[:3], zh[:3]


# ---------------------------------------------------------------------------
# Market weather + sectors
# ---------------------------------------------------------------------------
def _weather(pct_stage2: float, pct_stage4: float) -> str:
    """advancing / mixed / deteriorating (masterplan §2).

    'mixed' remains the expected common state — advancing requires both a broad
    Stage-2 share (>=40%, FIX 7d floor) AND Stage-2 dominance over Stage-4.
    """
    if pct_stage2 >= 40.0 and pct_stage2 > pct_stage4 * 1.5:
        return "advancing"
    if pct_stage4 >= 40.0:
        return "deteriorating"
    return "mixed"


def _sector_rollup(recs: list[dict]) -> list[dict]:
    """Per-sector Stage-2 share + trend (up/flat/down by relative Stage2 vs Stage4).

    Names whose sector is unknown (long-tail micro-caps outside our name sources)
    are excluded from the tiles — they still count in the market-weather totals,
    but an 'Unknown' pseudo-sector tile is machine junk at rest (design doctrine).
    """
    by_sec: dict[str, dict] = {}
    for r in recs:
        sec = (r.get("sector") or "").strip()
        if not sec or sec == "Unknown":
            continue
        d = by_sec.setdefault(sec, {"n": 0, "s2": 0, "s4": 0})
        d["n"] += 1
        if r.get("stage") == 2:
            d["s2"] += 1
        elif r.get("stage") == 4:
            d["s4"] += 1
    out: list[dict] = []
    for sec, d in by_sec.items():
        n = d["n"]
        pct2 = round(100.0 * d["s2"] / n, 1) if n else 0.0
        pct4 = 100.0 * d["s4"] / n if n else 0.0
        if pct2 >= 45.0 and pct2 > pct4 * 1.5:
            trend = "up"
        elif pct4 >= 40.0:
            trend = "down"
        else:
            trend = "flat"
        out.append({"sector": sec, "n": n, "pct_stage2": pct2, "trend": trend})
    out.sort(key=lambda x: (-x["pct_stage2"], -x["n"], x["sector"]))
    return out


# ---------------------------------------------------------------------------
# Change feed (same-day idempotent — mirrors special_sits_intel:1018-1134)
# ---------------------------------------------------------------------------
# Change kinds keyed on ticker (masterplan §2):
#   entered_stage2 | left_stage2 | breakout | topping | entered_stage4
def _by_key_from_recs(recs: list[dict]) -> dict[str, dict]:
    """Current snapshot keyed on ticker: {stage, fresh, event}."""
    out: dict[str, dict] = {}
    for r in recs:
        tk = r.get("ticker") or ""
        if not tk:
            continue
        out[tk] = {
            "stage": r.get("stage"),
            "fresh": bool(r.get("fresh")),
            "event": r.get("event"),
        }
    return out


def _diff_by_key(base: dict[str, dict], new: dict[str, dict]) -> list[dict]:
    """Change items diffing base snapshot -> new snapshot (ticker keyed)."""
    items: list[dict] = []
    for tk, cur in new.items():
        old = base.get(tk)
        cur_stage = cur.get("stage")
        # Event chip fires whenever a breakout newly appears (or changes into one).
        if cur.get("event") == "breakout" and (old is None or old.get("event") != "breakout"):
            items.append({"kind": "breakout", "ticker": tk,
                          "detail": "Broke out of its base on volume"})
        if old is None:
            # First sighting: only announce the meaningful stage arrivals.
            if cur_stage == 2:
                items.append({"kind": "entered_stage2", "ticker": tk,
                              "detail": "Now in an advancing stage"})
            elif cur_stage == 4:
                items.append({"kind": "entered_stage4", "ticker": tk,
                              "detail": "Now in a declining stage"})
            continue
        old_stage = old.get("stage")
        if old_stage == cur_stage:
            continue
        # ONE change item per ticker transition (FIX 7a): when both a generic
        # (left_stage2) and a specific (topping / entered_stage4) kind apply,
        # emit ONLY the specific one.
        if cur_stage == 2 and old_stage != 2:
            items.append({"kind": "entered_stage2", "ticker": tk,
                          "detail": "Moved into an advancing stage"})
        elif cur_stage == 3 and old_stage == 2:
            items.append({"kind": "topping", "ticker": tk,
                          "detail": "Advance is stalling — topping out"})
        elif cur_stage == 4 and old_stage != 4:
            items.append({"kind": "entered_stage4", "ticker": tk,
                          "detail": "Rolled over into a declining stage"})
        elif old_stage == 2 and cur_stage != 2:
            items.append({"kind": "left_stage2", "ticker": tk,
                          "detail": "No longer advancing"})
    return items


def _build_changes_block(old_contract: dict | None,
                         new_by_key: dict[str, dict],
                         new_asof: str) -> tuple[dict, dict]:
    """Same-day-idempotent changes block (mirrors special_sits_intel logic).

    Returns (changes_block, prev_state_block).
      - prev_state.by_key = the diff BASE (yesterday's state), frozen for the day.
      - _current_by_key   = today's snapshot, used as base by NEXT day.
    Same-day re-runs reuse prev_state.by_key so the change set is preserved,
    not wiped.
    """
    if old_contract is None:
        return {"items": [], "n": 0}, {"asof": None, "by_key": {}}

    old_asof = old_contract.get("asof")

    if old_asof != new_asof:
        base_by_key = (old_contract.get("_current_by_key")
                       or (old_contract.get("prev_state") or {}).get("by_key")
                       or {})
        base_asof = old_asof
    else:
        stored_ps = old_contract.get("prev_state") or {}
        base_by_key = stored_ps.get("by_key") or {}
        base_asof = stored_ps.get("asof")

    if not base_by_key or base_asof is None:
        return {"items": [], "n": 0}, {"asof": base_asof, "by_key": base_by_key}

    items = _diff_by_key(base_by_key, new_by_key)[:CHANGES_CAP]
    return ({"items": items, "n": len(items)},
            {"asof": base_asof, "by_key": base_by_key})


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------
def _json_safe(obj: Any) -> Any:
    """Recursively coerce numpy / non-JSON scalars to plain Python."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (bool, str, int)) or obj is None:
        return obj
    if isinstance(obj, float):
        # NaN/Inf -> None
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    # numpy scalar / other
    try:
        import numpy as np
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            f = float(obj)
            return None if (f != f) else f
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(obj)
    except Exception:  # noqa: BLE001
        return str(obj)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write JSON via tmp-then-rename (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Forward ledger (SGA-R7)
# ---------------------------------------------------------------------------
def append_forward_ledger(contract: dict, root: Path | None = None) -> int:
    """Append one JSONL row per fresh-Stage-2 name to
    data/stage_analysis/forward_ledger.jsonl, DEDUPED on (date,ticker).

    Same-day re-runs never duplicate (existing (date,ticker) keys are skipped).
    Returns the number of new rows appended. Fail-open: any error logs
    ::warning:: and returns 0 without raising.
    """
    try:
        dr = _data_root(root)
        asof = contract.get("asof")
        path = dr / "stage_analysis" / "forward_ledger.jsonl"

        # Load existing (date,ticker) keys for idempotence.
        seen: set[tuple[str, str]] = set()
        if path.exists():
            try:
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:  # noqa: BLE001 — skip a corrupt line, keep the rest
                        continue
                    key = (str(row.get("date")), str(row.get("ticker")))
                    seen.add(key)
            except Exception as e:  # noqa: BLE001
                log.warning("::warning:: stage ledger read failed (%s)", e)

        new_rows: list[str] = []
        for row in (contract.get("top_stage2") or []):
            if not row.get("fresh"):
                continue
            tk = row.get("ticker")
            if not tk:
                continue
            key = (str(asof), str(tk))
            if key in seen:
                continue
            seen.add(key)
            earn = row.get("earnings") or {}
            led = {
                "date": asof,
                "ticker": tk,
                "sga_score": row.get("sga_score"),
                "gate_tier": row.get("gate_tier"),
                "weeks_in_stage": row.get("weeks_in_stage"),
                "earnings_present": bool(earn.get("present")),
                "sentiment": earn.get("sentiment"),
                "performance": earn.get("performance"),
            }
            new_rows.append(json.dumps(_json_safe(led), ensure_ascii=False))

        if not new_rows:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for r in new_rows:
                fh.write(r + "\n")
        return len(new_rows)
    except Exception as e:  # noqa: BLE001 — ledger append must never break a build
        log.warning("::warning:: stage forward-ledger append failed (%s)", e)
        return 0


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def build_context_feed(root: Path | None = None,
                       asof: str | None = None,
                       max_workers: int | None = None) -> dict:
    """Classify the universe, score, assemble stage_context.v1, write it, and
    return the contract. Fail-open throughout.
    """
    dr = _data_root(root)
    rr = _repo_root(root)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    universe = build_universe(root)
    tickers = sorted(universe.keys())

    # --- fan-out classify ---
    classified = _classify_universe(tickers, dr, max_workers=max_workers)

    # --- side inputs (all fail-open) ---
    gate_tiers = _load_gate_tiers(rr)
    earnings_map = _load_earnings_scores(dr)

    # earnings-blackout assess needs a date object.
    try:
        asof_date = date.fromisoformat(asof)
    except Exception:  # noqa: BLE001
        asof_date = None

    # --- assemble per-name records ---
    recs: list[dict] = []
    too_young = 0
    counts = {"stage1": 0, "stage2": 0, "stage2_fresh": 0, "stage3": 0, "stage4": 0}
    # Null until SPY classifies cleanly — a failed SPY read must NOT masquerade
    # as "Stage 2" (FIX 3). The template already guards `spy_stage is not none`.
    spy_stage = None
    spy_weeks = None

    # Cross-sectional slope population (Stage-2 names) for the percentile.
    slope_pop: list[float] = []
    for tk, res in classified.items():
        if not res:
            continue
        if res.get("stage") == 2:
            sl = res.get("ma30_slope_pct5w")
            if sl is not None:
                try:
                    slope_pop.append(float(sl))
                except (TypeError, ValueError):
                    pass
    slope_pop.sort()

    roster: dict[str, list] = {}

    for tk in tickers:
        res = classified.get(tk)
        meta = universe.get(tk) or {}
        company = meta.get("company") or tk
        sector = meta.get("sector") or "Unknown"

        if not res:
            too_young += 1
            continue

        # A name is "too young to stage" (SGA-R3) when the classifier flags it,
        # when it has too little weekly history, or when it is unclassifiable
        # (stage 0/None). Counted, never hidden.
        if res.get("too_young"):
            too_young += 1
            continue
        n_weeks = res.get("n_weeks")
        if n_weeks is not None and int(n_weeks) < MIN_WEEKS:
            too_young += 1
            continue

        stage = res.get("stage")
        if stage in (None, 0):
            too_young += 1
            continue

        weeks = int(res.get("weeks_in_stage") or 0)
        fresh = bool(res.get("fresh"))

        # counts + roster
        if stage == 1:
            counts["stage1"] += 1
        elif stage == 2:
            counts["stage2"] += 1
            if fresh:
                counts["stage2_fresh"] += 1
        elif stage == 3:
            counts["stage3"] += 1
        elif stage == 4:
            counts["stage4"] += 1
        roster[tk] = [stage, weeks]

        gate_tier = gate_tiers.get(tk)
        slope = res.get("ma30_slope_pct5w")
        slope_pctile = _pctile(
            None if slope is None else float(slope), slope_pop)

        rec = {
            "ticker": tk,
            "company": company,
            "sector": sector,
            "stage": stage,
            "weeks_in_stage": weeks,
            "fresh": fresh,
            "ma30_slope_pct5w": None if slope is None else round(float(slope), 3),
            "pct_vs_ma30": None if res.get("pct_vs_ma30") is None else round(float(res["pct_vs_ma30"]), 2),
            "mansfield_rs": None if res.get("mansfield_rs") is None else round(float(res["mansfield_rs"]), 2),
            "vol_ratio": None if res.get("vol_ratio") is None else round(float(res["vol_ratio"]), 2),
            "event": res.get("event"),
            "gate_tier": gate_tier,
            "arc_pos": None if res.get("arc_pos") is None else round(float(res["arc_pos"]), 4),
        }
        rec["sga_score"] = _compute_sga_score(rec, slope_pctile, gate_tier)

        # blackout (SGA-R8) — fail-open.
        blackout = False
        try:
            from engine import earnings_blackout  # noqa: PLC0415
            bo = earnings_blackout.assess(tk, today=asof_date)
            blackout = bool(bo.get("in_blackout"))
        except Exception:  # noqa: BLE001
            blackout = False
        rec["blackout"] = blackout

        # earnings context (SGA-R5, context-only).
        rec["earnings"] = earnings_map.get(tk) or _empty_earnings()

        # plain-word rationale.
        en, zh = _why_bullets(rec, gate_tier, rec["earnings"], blackout)
        rec["why"] = en
        rec["why_zh"] = zh

        recs.append(rec)

    total = len(recs)
    counts_full = {
        "total": total,
        "stage1": counts["stage1"],
        "stage2": counts["stage2"],
        "stage2_fresh": counts["stage2_fresh"],
        "stage3": counts["stage3"],
        "stage4": counts["stage4"],
        "too_young": too_young,
        "new_today": 0,  # filled from the change feed below
    }

    # --- SPY market context (single benchmark) ---
    # SPY lives in data/yahoo/ as the benchmark, not the roster universe, so it
    # is rarely in `classified`. Classify it directly against itself so the
    # market block reports SPY's own stage honestly. Fail-open on any error.
    spy_res = classified.get("SPY")
    if not spy_res:
        try:
            bench = _load_bench_close(dr)
            if bench is not None and len(bench):
                spy_res = _classify(bench, None, bench)
        except Exception:  # noqa: BLE001
            spy_res = None
    if spy_res and spy_res.get("stage"):
        spy_stage = spy_res.get("stage")
        spy_weeks = int(spy_res.get("weeks_in_stage") or 0)

    pct_stage2 = round(100.0 * counts["stage2"] / total, 1) if total else 0.0
    pct_stage4 = round(100.0 * counts["stage4"] / total, 1) if total else 0.0
    market = {
        "pct_stage2": pct_stage2,
        "pct_stage4": pct_stage4,
        "weather": _weather(pct_stage2, pct_stage4),
        "spy_stage": spy_stage,
        "spy_weeks": spy_weeks,
    }

    # --- top_stage2 board (fresh first, then by sga_score) ---
    stage2 = [r for r in recs if r.get("stage") == 2]
    stage2.sort(key=lambda r: (not r.get("fresh"), -(r.get("sga_score") or 0), r.get("ticker")))
    top_stage2 = [_top_row(r) for r in stage2[:TOP_STAGE2_CAP]]

    # --- warnings (Stage 3, topping) ---
    stage3 = [r for r in recs if r.get("stage") == 3]
    stage3.sort(key=lambda r: (-(r.get("sga_score") or 0), r.get("ticker")))
    warnings_stage3 = [
        {"ticker": r["ticker"], "company": r["company"],
         "weeks_in_stage": r["weeks_in_stage"], "sga_score": r["sga_score"]}
        for r in stage3[:WARNINGS_CAP]
    ]

    sectors = _sector_rollup(recs)

    # --- change feed (same-day idempotent) ---
    outpath = dr / "stage_analysis" / "context" / "latest.json"
    old_contract: dict | None = None
    if outpath.exists():
        try:
            old_contract = json.loads(outpath.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: could not read old latest.json (%s)", e)

    new_by_key = _by_key_from_recs(recs)
    changes, prev_state = _build_changes_block(old_contract, new_by_key, asof)
    counts_full["new_today"] = sum(
        1 for it in changes["items"]
        if it.get("kind") in ("entered_stage2", "breakout"))

    contract = {
        "schema": "stage_context.v1",
        "asof": asof,
        "built": built,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — stage classification display, "
                       "never a signal or sizing input."),
        "counts": counts_full,
        "market": market,
        "top_stage2": top_stage2,
        "warnings_stage3": warnings_stage3,
        "sectors": sectors,
        "roster": roster,
        "changes": changes,
        "prev_state": prev_state,
        "_current_by_key": new_by_key,
    }

    contract = _json_safe(contract)

    try:
        _atomic_write_json(outpath, contract)
    except Exception as e:  # noqa: BLE001 — write failure must not break a build
        log.warning("::warning:: stage_analysis: failed to write %s (%s)", outpath, e)

    return contract


def _top_row(r: dict) -> dict:
    """Project a full record onto the top_stage2 contract shape (§2)."""
    return {
        "ticker": r["ticker"],
        "company": r["company"],
        "sector": r["sector"],
        "stage": r["stage"],
        "weeks_in_stage": r["weeks_in_stage"],
        "fresh": r["fresh"],
        "sga_score": r["sga_score"],
        "ma30_slope_pct5w": r["ma30_slope_pct5w"],
        "pct_vs_ma30": r["pct_vs_ma30"],
        "mansfield_rs": r["mansfield_rs"],
        "vol_ratio": r["vol_ratio"],
        "event": r["event"],
        "gate_tier": r["gate_tier"],
        "blackout": r["blackout"],
        "arc_pos": r["arc_pos"],
        "earnings": r["earnings"],
        "why": r["why"],
        "why_zh": r["why_zh"],
    }
