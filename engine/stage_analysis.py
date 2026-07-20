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
# SGA-2 flagship screener / stage-board row cap (surface A/B). The full universe
# (~2.7k names) at ~20 compact fields/row is well under 1 MB; keep an explicit
# cap so a runaway universe can never blow the artifact budget.
SCREENER_CAP = 3000

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
    """Return (close, volume, high, low) daily series for a ticker, or Nones.

    Prefers baskets/ohlcv (full adjusted series per masterplan trap §7); falls
    back to data/stocks/. High/low power the SGA-2 14-week ATR (atr_ext); they
    are None when absent (classify degrades to a close-only ATR). Fail-open on
    any read error.
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
        high = df["high"].dropna() if "high" in df.columns else None
        low = df["low"].dropna() if "low" in df.columns else None
        if len(close) == 0:
            continue
        return close, vol, high, low
    return None, None, None, None


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
def _classify(close, volume, bench_close, high=None, low=None) -> dict | None:
    """Call engine.weinstein_stage.classify, fail-open to None.

    Kept as a thin indirection so tests can monkeypatch this symbol (or the
    underlying module) and the suite runs standalone before the sibling lane
    lands weinstein_stage.py. high/low feed the SGA-2 14-week ATR; they are
    optional (a classify build without them degrades the extension fields).
    """
    try:
        from engine import weinstein_stage  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — module not built yet in this lane
        return None
    try:
        return weinstein_stage.classify(close, volume, bench_close, high, low)
    except TypeError:
        # A monkeypatched/older classify without the high/low params — retry.
        try:
            return weinstein_stage.classify(close, volume, bench_close)
        except Exception as e:  # noqa: BLE001
            log.warning("stage_analysis: classify raised (%s)", e)
            return None
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
    close, vol, high, low = _load_prices(ticker, dr)
    if close is None:
        return ticker, None
    res = _classify(close, vol, bench, high, low)
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
# Industry-percentile join (SGA-2 — from the industry-ranks lane, fail-open)
# ---------------------------------------------------------------------------
def _load_industry_pctile(dr: Path) -> dict[str, float]:
    """Read data/stage_analysis/industry_name_pctile.json -> {TICKER: pct}.

    Produced by the sibling industry-ranks lane (engine/stage_industry.py):
    the name's RS-strength percentile within its GICS industry (0..100). This
    is the flagship "Ind %ile" column. Read-only, fail-open: an absent /
    unreadable / malformed artifact -> {} (the column simply nulls out).
    """
    p = dr / "stage_analysis" / "industry_name_pctile.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("stage_analysis: industry_name_pctile.json unreadable (%s)", e)
        return {}
    pcts = (d or {}).get("percentiles")
    if not isinstance(pcts, dict):
        return {}
    out: dict[str, float] = {}
    for tk, v in pcts.items():
        try:
            out[str(tk).strip().upper()] = float(v)
        except (TypeError, ValueError):
            continue
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
def _atomic_write_json(path: Path, obj: Any, compact: bool = False) -> None:
    """Write JSON via tmp-then-rename (atomic on POSIX).

    compact=True drops indentation and inter-token whitespace (separators
    (",", ":")) — used for the large screener/board tables so the artifact
    stays well under the 1 MB budget; the small context feed stays pretty.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if compact:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    else:
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
# SGA-2 screener / stage-board projection (surface A + B, masterplan §1)
# ---------------------------------------------------------------------------
# UI stage labels (masterplan §1): the two flagship Stage-2 chips.
#   2X_fallback_bullish     -> "2X Bullish"  (established uptrend)
#   2X_catch_price_above_ma -> "2X Catch"    (fresh recapture / early entry)
_STAGE_UI_LABEL = {
    "1X_fallback_base": "1X Base",
    "2A_strong_breakout": "2A Breakout",
    "2D_extended_run": "2D Extended",
    "2X_catch_price_above_ma": "2X Catch",
    "2X_fallback_bullish": "2X Bullish",
    "3A_sideways_exhaustion": "3A Topping",
    "3C_volatility_blowoff": "3C Blowoff",
    "4B_steady_decline": "4B Decline",
    "4X_fallback_bearish": "4X Bearish",
}


def _stage_ui_label(stage_detailed: str | None, stage: int | None) -> str | None:
    """Plain UI chip for the stage column. Falls back to a bare stage word when
    stage_detailed is absent (name stageable but detail-mapping declined)."""
    if stage_detailed and stage_detailed in _STAGE_UI_LABEL:
        return _STAGE_UI_LABEL[stage_detailed]
    return {1: "Stage 1", 2: "Stage 2", 3: "Stage 3", 4: "Stage 4"}.get(stage)


# ---------------------------------------------------------------------------
# FIX 1b — EU / ASIA seed screener rows (from the committed EquityDesk overview)
# ---------------------------------------------------------------------------
# Our live engine only classifies US-listed OHLCV, so the flagship region toggle
# (N.America / Europe / Asia) had ZERO rows for EU / Asia. EquityDesk covers all
# three regions and we carry their EU (799) + Asia (3,171) rows in the committed
# overview seed. We APPEND them to the screener/board — mapped to our column
# schema, carrying THEIR scores — tagged source="seed" so the UI can flag them as
# "EquityDesk seed" (our live US rows carry source="live"). This makes the
# transfer genuinely 3-region: US = our live engine, EU/Asia = their seed until we
# wire non-US OHLCV. DISPLAY-TIER / CONTEXT-ONLY — a seed row is never a signal,
# gate, or sizing input (SGA-R5), same as every other row on these surfaces.
#
# Per-region cap by their combined_rating (their overall quality rank), so a
# runaway region can never blow the ~1.3MB screener budget. The cap + the full
# per-region counts are disclosed in the artifact's `counts` block.
#
# BUDGET MATH (measured): the live US screener is already ~1.09MB at ~2.7k rows,
# and a non-US seed row costs ~475 B (long international company names dominate,
# not the numbers). Headroom to ~1.3MB is ~250KB → ~500 seed rows. We keep the
# top 250 per region by combined_rating (the highest-quality names — exactly what
# a screener surfaces first) so the ONE screener.json stays under budget. The
# uncapped per-region availability is disclosed in `counts.by_region`. EU=799 and
# ASIA=3,171 upstream; the full non-US set stays in the committed overview seed /
# R2 detail lane. Seed `tags` are trimmed to 4 (the full tag set lives on the
# Earnings-Calls surfaces + earnings_table.json).
_SEED_REGION_CAP = 250           # per non-US region (first-pass cap; see math above)
_SEED_TAGS_KEEP = 4              # trim seed level1 tags to keep the row compact
_SEED_SCREENER_REGIONS = ("EUROPE", "ASIA")
# Hard ceiling for screener.json (task budget ~1.3MB). The live US block alone is
# ~1.18MB, so after the per-region cap we still BYTE-TRIM the seed rows (dropping
# the lowest-rated first, balanced across regions) until the whole artifact fits.
# This keeps the ONE screener.json under budget no matter how the US block grows.
# The trim measures against a live-only base that is a few hundred bytes SMALLER
# than the final contract (it lacks the surface/by_region/cadence envelope added
# later), so we hold back a safety margin to guarantee the on-disk file fits.
_SCREENER_BYTE_MARGIN = 4096
_SCREENER_BYTE_CEILING = int(1.3 * 1024 * 1024) - _SCREENER_BYTE_MARGIN

# EquityDesk stage_flag (int 1..4) → coarse stage; their stage_detailed strings
# reuse our _STAGE_UI_LABEL taxonomy (same W5 label set), so the UI chip is shared.
_OVERVIEW_COLS = [
    "ticker", "region", "name_ui", "gics_sector", "gics_industry",
    "industry_percentile", "sata_score", "sata_change_1w", "stage_flag",
    "stage_detailed", "weeks_in_stage", "atr_ext", "atr_14w", "close",
    "earnings_call_sent", "earnings_call_perf", "combined_rating",
    "mansfield_rs", "level1_tags",
]


def _num(v):
    """Coerce a possibly-NaN/None seed cell to a float, else None."""
    try:
        import pandas as pd  # noqa: PLC0415
        if v is None or (isinstance(v, float) and v != v) or pd.isna(v):
            return None
    except Exception:  # noqa: BLE001
        if v is None:
            return None
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _seed_screener_rows(root: Path | None = None) -> tuple[list[dict], dict]:
    """Build EU + ASIA screener rows from the committed EquityDesk overview seed.

    Returns (rows, region_meta) where region_meta = {region: {available, kept}}
    for the artifact's counts disclosure. Rows carry source="seed" and match the
    _screener_row column schema. Fail-open: a missing/unreadable seed yields
    ([], {}) so the US-only board still renders.
    """
    import pandas as pd  # noqa: PLC0415

    dr = _data_root(root)
    p = dr / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    if not p.exists():
        return [], {}
    try:
        ov = pd.read_parquet(p, columns=_OVERVIEW_COLS)
    except Exception as e:  # noqa: BLE001 — fail-open; US-only board still ships
        log.warning("stage_analysis: overview seed unreadable (%s) — no EU/ASIA rows", e)
        return [], {}

    rows: list[dict] = []
    region_meta: dict[str, dict] = {}
    for region in _SEED_SCREENER_REGIONS:
        sub = ov[ov["region"] == region]
        available = int(len(sub))
        if available == 0:
            continue
        # Rank by their combined_rating (overall quality) desc, cap per region.
        sub = sub.sort_values("combined_rating", ascending=False, na_position="last")
        if available > _SEED_REGION_CAP:
            sub = sub.head(_SEED_REGION_CAP)
        region_meta[region] = {"available": available, "kept": int(len(sub))}
        for _, r in sub.iterrows():
            tk = str(r.get("ticker") or "").strip().upper()
            if not tk:
                continue
            stage_flag = r.get("stage_flag")
            try:
                stage = int(stage_flag) if stage_flag is not None and not pd.isna(stage_flag) else None
            except (TypeError, ValueError):
                stage = None
            if stage == 0:
                stage = None
            weeks = _num(r.get("weeks_in_stage"))
            stage_det = r.get("stage_detailed")
            stage_det = None if (stage_det is None or pd.isna(stage_det)) else str(stage_det)
            # atr_pct_price = 14w ATR / close (their atr_14w is an absolute band).
            atr14 = _num(r.get("atr_14w"))
            close = _num(r.get("close"))
            atr_pct = (atr14 / close) if (atr14 is not None and close not in (None, 0)) else None
            sata = _num(r.get("sata_score"))
            sata_chg = _num(r.get("sata_change_1w"))
            ind_pct = _num(r.get("industry_percentile"))
            rating = _num(r.get("combined_rating"))
            tags = _parse_tag_list(r.get("level1_tags"))[:_SEED_TAGS_KEEP]
            rows.append({
                "ticker": tk,
                "name": (str(r.get("name_ui")).strip()
                         if r.get("name_ui") is not None and not pd.isna(r.get("name_ui")) else tk),
                "sector": (str(r.get("gics_sector")).strip()
                           if r.get("gics_sector") is not None and not pd.isna(r.get("gics_sector"))
                           and str(r.get("gics_sector")).strip().lower() != "nan" else "Unknown"),
                "region": region,
                "source": "seed",
                "industry": (str(r.get("gics_industry")).strip()
                             if r.get("gics_industry") is not None and not pd.isna(r.get("gics_industry"))
                             and str(r.get("gics_industry")).strip().lower() != "nan" else None),
                "industry_percentile": round(ind_pct, 1) if ind_pct is not None else None,
                "sata_score": int(sata) if sata is not None else None,
                "sata_change_1w": round(sata_chg, 2) if sata_chg is not None else None,
                "stage": stage,
                "stage_detailed": stage_det,
                "stage_label": _stage_ui_label(stage_det, stage),
                "weeks_in_stage": int(weeks) if weeks is not None else None,
                # A seed row is "fresh" on the same rule our engine uses: fresh
                # Stage-2 with <= FRESH_MAX_WEEKS completed weeks (SGA-R1).
                "fresh": bool(stage == 2 and weeks is not None and weeks <= FRESH_MAX_WEEKS),
                "atr_ext": round(_num(r.get("atr_ext")), 3) if _num(r.get("atr_ext")) is not None else None,
                "atr_pct_price": round(atr_pct, 5) if atr_pct is not None else None,
                "mansfield_rs": round(_num(r.get("mansfield_rs")), 2) if _num(r.get("mansfield_rs")) is not None else None,
                "ec_sent": _num(r.get("earnings_call_sent")),
                "ec_perf": _num(r.get("earnings_call_perf")),
                "rating": int(rating) if rating is not None else None,
                "gate_tier": None,     # our confluence gate is US-only
                "event": None,
                "blackout": False,
                "tags": tags,
            })
    return rows, region_meta


def _byte_trim_seed_rows(base_contract: dict, seed_rows: list[dict],
                         ceiling: int) -> tuple[list[dict], dict]:
    """Drop the lowest-rated seed rows (balanced across regions) until the
    serialized contract fits `ceiling` bytes. Returns (kept_seed_rows, kept_by_region).

    The live rows are already in base_contract["rows"]; we only trim the SEED tail
    so the US block is never touched. Balanced round-robin removal by region keeps
    each region proportionally represented rather than starving one. Fail-open: if
    measurement raises, returns the input unchanged.
    """
    try:
        def _size(rows: list[dict]) -> int:
            c = dict(base_contract)
            c["rows"] = base_contract["rows"] + rows
            return len(json.dumps(_json_safe(c), ensure_ascii=False,
                                  separators=(",", ":")).encode("utf-8"))

        kept = list(seed_rows)
        if _size(kept) <= ceiling:
            by_region = _count_by_region(kept)
            return kept, by_region

        # Bucket per region, lowest-rated LAST so we pop the weakest first.
        buckets: dict[str, list[dict]] = {}
        for r in kept:
            buckets.setdefault(r["region"], []).append(r)
        for reg in buckets:
            buckets[reg].sort(key=lambda x: (x.get("rating") or 0))  # weakest first
        regions_cycle = [r for r in _SEED_SCREENER_REGIONS if r in buckets]

        # Round-robin pop the weakest from the largest-remaining region until it fits.
        while _size([r for b in buckets.values() for r in b]) > ceiling:
            # pick the region with the most rows remaining (keep balance)
            regions_cycle.sort(key=lambda reg: len(buckets.get(reg, [])), reverse=True)
            popped = False
            for reg in regions_cycle:
                if buckets.get(reg):
                    buckets[reg].pop(0)   # remove weakest
                    popped = True
                    break
            if not popped:
                break
        kept = [r for b in buckets.values() for r in b]
        return kept, _count_by_region(kept)
    except Exception as e:  # noqa: BLE001 — never break the build on a size trim
        log.warning("::warning:: stage_analysis: seed byte-trim failed (%s)", e)
        return seed_rows, _count_by_region(seed_rows)


def _count_by_region(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["region"]] = out.get(r["region"], 0) + 1
    return out


def _parse_tag_list(raw: Any) -> list[str]:
    """Coerce a seed tags cell (JSON-string / list / None) into a list[str].
    Mirrors earnings_qual._parse_tag_list; kept local so this module has no
    cross-engine import."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw if str(t).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(t) for t in v if str(t).strip()]
        except Exception:  # noqa: BLE001
            return [t.strip() for t in s.split(",") if t.strip()]
    return []


def _screener_row(r: dict) -> dict:
    """Project a full record onto the flagship screener/board row (surface A).

    Column parity with EquityDesk Overview (masterplan §1): Ticker · Name ·
    Industry(sector) · Ind %ile · SATA · Δ SATA · Stage(2X Bullish/2X Catch) ·
    Weeks · ATR Ext · ATR % Price · EC Sent/Perf · Rating · Mansfield RS + Δ.
    Every field is display-tier / context-only.
    """
    earn = r.get("earnings") or {}
    return {
        "ticker": r["ticker"],
        "name": r["company"],
        "sector": r["sector"],
        # FIX 1a: our live-classified universe is US-listed OHLCV, so every live
        # row is region "USA" with source "live". EU/ASIA rows are appended from
        # the EquityDesk seed (source "seed") by _seed_screener_rows() below.
        "region": r.get("region") or "USA",
        "source": r.get("source") or "live",
        "industry": r.get("industry"),         # seed carries GICS industry; live nulls
        "industry_percentile": r.get("industry_percentile"),
        "sata_score": r.get("sata_score"),
        "sata_change_1w": r.get("sata_change_1w"),
        "stage": r["stage"],
        "stage_detailed": r.get("stage_detailed"),
        "stage_label": _stage_ui_label(r.get("stage_detailed"), r.get("stage")),
        "weeks_in_stage": r["weeks_in_stage"],
        "fresh": r["fresh"],
        "atr_ext": r.get("atr_ext"),
        "atr_pct_price": r.get("atr_pct_price"),
        "mansfield_rs": r.get("mansfield_rs"),
        "ec_sent": earn.get("sentiment"),
        "ec_perf": earn.get("performance"),
        "rating": r.get("sga_score"),          # our 0..100 combined-rating analogue
        "gate_tier": r.get("gate_tier"),
        "event": r.get("event"),
        "blackout": r.get("blackout"),
        "tags": earn.get("tags") or [],
    }


# Honest calibration note shared by the screener + both boards (item 7): discloses
# the WEAK stage_detailed top-label agreement, not only the strong SATA/atr_ext.
_CALIBRATION_NOTE = (
    "Reproduced from our OHLCV vs the EquityDesk seed (display-tier only): "
    "atr_ext r≈1.0, SATA Spearman≈0.92, coarse stage (1–4) agree≈73%. The fine "
    "stage_detailed top-label agrees only ≈0.40 (their ~16 labels vs our 9) — a "
    "read may land on a neighbouring detailed label with the same coarse stage."
)
# Daily board cadence disclosure (item 14): the classifier is weekly-native, so
# the daily board currently mirrors the weekly stage read.
_DAILY_CADENCE_NOTE = (
    "This daily board currently mirrors the weekly stage read — the classifier "
    "is weekly-native (completed Friday bars); there is no separate daily-cadence "
    "stage machine yet, so the daily and weekly boards share the same stages."
)


def _stage_board_contract(schema_tag: str, asof: str, built: str,
                          recs: list[dict], counts_full: dict,
                          market: dict, cadence_note: str | None = None,
                          seed_rows: list[dict] | None = None,
                          region_counts: dict | None = None) -> dict:
    """Assemble one stage-board contract (daily or weekly variant).

    Rows sorted fresh-first then by rating (sga_score) so the board leads with
    the freshest, highest-quality Stage-2 names — matching the EquityDesk
    Trending Stocks default order. Non-stage-2 names still ship (filterable
    client-side) but sink below the Stage-2 block.

    seed_rows: pre-built EU/ASIA rows from the EquityDesk overview seed (FIX 1b),
    already in _screener_row shape with source="seed"; appended AFTER the live US
    rows so the region toggle is genuinely 3-region. region_counts: the per-region
    live/seed disclosure attached to the contract's `counts`.

    cadence_note: an extra plain-word disclosure appended to calibration (the
    daily board passes _DAILY_CADENCE_NOTE — item 14 honesty).
    """
    rows = [_screener_row(r) for r in recs]
    if seed_rows:
        rows = rows + list(seed_rows)
    # Sort. `source` leads the key so the LIVE US engine (our flagship) always
    # heads the default/unfiltered view — the seed `rating` (EquityDesk
    # combined_rating, mean≈78) and our live `rating` (sga_score, mean≈23) are on
    # DIFFERENT 0-100 scales, so interleaving them by rating would bury every US
    # name under the seed block. The region toggle is the primary filter; within
    # each region the existing stage/fresh/rating order is preserved. Stage may be
    # None on a seed row → treated as non-Stage-2 (sinks below within its block).
    rows.sort(key=lambda x: (
        x.get("source") != "live",             # live US block first
        x.get("stage") != 2,                   # Stage 2 first
        not x.get("fresh"),                    # fresh first within Stage 2
        -(x.get("rating") or 0),               # then by rating (within same scale)
        x["ticker"],
    ))
    calibration = {
        "target": "EquityDesk stage_daily.parquet (seed yardstick)",
        "note": _CALIBRATION_NOTE,
    }
    if cadence_note:
        calibration["cadence_note"] = cadence_note
    # Per-region live/seed counts for the toggle (FIX 1b disclosure). Computed
    # from the assembled rows so it always matches what actually shipped.
    counts_out = dict(counts_full)
    if region_counts is not None:
        counts_out["by_region"] = region_counts
    return {
        "schema": schema_tag,
        "asof": asof,
        "built": built,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — stage classification display, "
                       "never a signal or sizing input."),
        "calibration": calibration,
        "counts": counts_out,
        "market": market,
        "rows": rows,
        "n": len(rows),
    }


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
    industry_pctile = _load_industry_pctile(dr)

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
            # SGA-2 EquityDesk yardstick fields (display-tier / context-only).
            "atr_14w": None if res.get("atr_14w") is None else round(float(res["atr_14w"]), 4),
            "atr_ext": None if res.get("atr_ext") is None else round(float(res["atr_ext"]), 3),
            "atr_pct_price": None if res.get("atr_pct_price") is None else round(float(res["atr_pct_price"]), 5),
            "sata_score": res.get("sata_score"),
            "sata_change_1w": res.get("sata_change_1w"),
            "stage_detailed": res.get("stage_detailed"),
            # Ind %ile joined from the industry-ranks lane (null if absent).
            "industry_percentile": industry_pctile.get(tk),
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

    # --- SGA-2 flagship artifacts: screener.json + stage_board_{daily,weekly} ---
    # Surface A (Screener) is the full combined table; surfaces B are the daily /
    # weekly stage boards. Our classifier is weekly-native (completed W-FRI bars),
    # so both variants derive from the same weekly stage read — the daily variant
    # carries the freshest daily-close position, the weekly variant is the pure
    # weekly-resampled view (documented in each contract's calibration.note).
    # Capped, ranked, display-tier; fail-open per file.
    #
    # FIX 1b: our live rows are all US ("USA"/"live"); APPEND the EU + ASIA rows
    # from the EquityDesk overview seed ("seed") so the region toggle is genuinely
    # 3-region. Built once, shared across the screener + both boards.
    try:
        seed_rows, seed_meta = _seed_screener_rows(root)
    except Exception as e:  # noqa: BLE001 — fail-open; US-only board still ships
        log.warning("::warning:: stage_analysis: seed screener rows failed (%s)", e)
        seed_rows, seed_meta = [], {}
    n_live = len(recs[:SCREENER_CAP] if len(recs) > SCREENER_CAP else recs)

    # BYTE-TRIM the seed rows against the screener's ~1.3MB ceiling: the live US
    # block alone is ~1.18MB, so after the per-region cap we still drop the
    # lowest-rated seed rows (balanced across regions) until the ONE screener.json
    # fits. Measured against a live-only base so the US block is never touched.
    live_rows = [_screener_row(r) for r in
                 (recs[:SCREENER_CAP] if len(recs) > SCREENER_CAP else recs)]
    _base_for_trim = {
        "schema": "stage_screener.v1", "asof": asof, "built": built,
        "is_context_only": True, "display_only": True, "surface": "A",
        "calibration": {"target": "EquityDesk stage_daily.parquet (seed yardstick)",
                        "note": _CALIBRATION_NOTE},
        "counts": counts_full, "market": market, "rows": live_rows,
    }
    seed_rows, kept_by_region = _byte_trim_seed_rows(
        _base_for_trim, seed_rows, _SCREENER_BYTE_CEILING)

    region_counts = {
        "USA": {"live": n_live, "seed": 0, "cap": None},
    }
    for reg, m in (seed_meta or {}).items():
        kept = kept_by_region.get(reg, 0)
        available = m.get("available")
        region_counts[reg] = {
            "live": 0,
            "seed": kept,
            "available": available,
            # Disclose the binding cap: either the per-region cap or the tighter
            # byte-trim, whichever actually limited the kept count.
            "cap": kept if (available is not None and kept < available) else None,
        }

    try:
        capped = recs[:SCREENER_CAP] if len(recs) > SCREENER_CAP else recs
        screener = _stage_board_contract(
            "stage_screener.v1", asof, built, capped, counts_full, market,
            seed_rows=seed_rows, region_counts=region_counts)
        screener["surface"] = "A"
        _atomic_write_json(
            dr / "stage_analysis" / "screener.json", _json_safe(screener),
            compact=True)
    except Exception as e:  # noqa: BLE001
        log.warning("::warning:: stage_analysis: failed to write screener.json (%s)", e)

    for variant, fname in (("daily", "stage_board_daily.json"),
                           ("weekly", "stage_board_weekly.json")):
        try:
            capped = recs[:SCREENER_CAP] if len(recs) > SCREENER_CAP else recs
            # The daily board mirrors the weekly stage read (weekly-native
            # classifier) — disclose it honestly in the daily contract (item 14).
            cadence = _DAILY_CADENCE_NOTE if variant == "daily" else None
            board = _stage_board_contract(
                f"stage_board_{variant}.v1", asof, built, capped,
                counts_full, market, cadence_note=cadence,
                seed_rows=seed_rows, region_counts=region_counts)
            board["variant"] = variant
            _atomic_write_json(
                dr / "stage_analysis" / fname, _json_safe(board),
                compact=True)
        except Exception as e:  # noqa: BLE001
            log.warning("::warning:: stage_analysis: failed to write %s (%s)", fname, e)

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
        # SGA-2 yardstick fields.
        "atr_14w": r.get("atr_14w"),
        "atr_ext": r.get("atr_ext"),
        "atr_pct_price": r.get("atr_pct_price"),
        "sata_score": r.get("sata_score"),
        "sata_change_1w": r.get("sata_change_1w"),
        "stage_detailed": r.get("stage_detailed"),
        "industry_percentile": r.get("industry_percentile"),
    }
