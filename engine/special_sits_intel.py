"""Special Situations Intelligence Layer (display-tier context, never a signal).

Exposes:
  enrich(sits, root=None) -> dict
      Mutates each situation dict IN PLACE, adding keys 'tech', 'ident', 'favor', 'setup'.
      Returns {'coverage': {...counts...}}.

  build_context_feed(sits, asof=None, root=None) -> dict
      Computes + writes data/special_situations/context/latest.json (same-day idempotent).
      Returns the written dict.

DISPLAY-TIER ONLY:
  - is_context_only = True always
  - LLMs may only DE-ESCALATE scores (v1_direction < 0 caps at 49)
  - Never imports engine.regime / engine.conditions / engine.run
  - Never calls 'validated' in user-facing copy
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.technicals import rsi as _wilder_rsi  # safe: technicals.py imports only lib.config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data root
# ---------------------------------------------------------------------------

def _data_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from lib import config as _cfg
        return _cfg.data_dir()
    except Exception:
        return Path(__file__).resolve().parent.parent / "data"


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root).parent  # root is data dir, repo root is parent
    try:
        from lib import config as _cfg
        return _cfg.ROOT
    except Exception:
        return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# StochRSI helper (14, 3, 3) — mirrors coiled.py exactly, no import needed
# ---------------------------------------------------------------------------

_STOCH_LEN = 14
_SMOOTH_K  = 3
_SMOOTH_D  = 3


def _stoch_rsi_kd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """14/3/3 StochRSI KD — identical formula to coiled.py._stoch_rsi_kd."""
    r    = _wilder_rsi(c, _STOCH_LEN)
    lo   = r.rolling(_STOCH_LEN).min()
    hi   = r.rolling(_STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k    = rawk.rolling(_SMOOTH_K).mean()
    d    = k.rolling(_SMOOTH_D).mean()
    return k, d


# ---------------------------------------------------------------------------
# Closes panel — built once, cached in module scope per enrich() call
# ---------------------------------------------------------------------------

def _load_closes_panel(root: Path) -> pd.DataFrame:
    """Build a merged wide-format daily closes panel from available caches."""
    frames: list[pd.DataFrame] = []

    # Breadth caches (wide, tickers as columns)
    for sub in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = root / sub / "_closes_cache.parquet"
        try:
            if p.exists():
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                frames.append(df)
        except Exception as e:
            log.warning("closes panel: %s read failed: %s", p, e)

    # Special situations price files (also wide)
    for name in ("bt_prices", "arb_prices"):
        p = root / "special_situations" / f"{name}.parquet"
        try:
            if p.exists():
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                # Drop columns with empty/non-ticker names
                df = df[[c for c in df.columns if c and str(c).strip() and not str(c).startswith("(")]]
                frames.append(df)
        except Exception as e:
            log.warning("closes panel: %s read failed: %s", p, e)

    if not frames:
        return pd.DataFrame()

    # Merge: combine_first cascades left-to-right; later frames fill gaps
    panel = frames[0]
    for f in frames[1:]:
        new_cols = [c for c in f.columns if c not in panel.columns]
        if new_cols:
            panel = panel.join(f[new_cols], how="outer")
        # Overwrite with fresh data where both have a col
        overlap = [c for c in f.columns if c in panel.columns]
        if overlap:
            panel[overlap] = panel[overlap].combine_first(f[overlap])

    return panel.sort_index()


def _get_ticker_closes(ticker: str, panel: pd.DataFrame, root: Path) -> pd.Series | None:
    """Return daily close series for ticker; fallback to per-ticker yahoo parquet."""
    if ticker in panel.columns:
        s = panel[ticker].dropna()
        if len(s) >= 10:
            return s

    # Fallback: per-ticker yahoo parquet
    try:
        p = root / "yahoo" / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            for col in ("close", "close_price"):
                if col in df.columns:
                    s = df[col].dropna()
                    if len(s) >= 10:
                        return s
    except Exception as e:
        log.warning("yahoo fallback %s: %s", ticker, e)

    return None


# ---------------------------------------------------------------------------
# Weekly technical indicators
# ---------------------------------------------------------------------------

_MIN_WEEKLY_BARS = 40   # StochRSI / MACD need this many resampled bars
_MIN_DAILY_BARS  = 200  # covered=True threshold


def _washout_flag(daily: pd.Series, freq: str, threshold: float = 35.0) -> bool | None:
    """StochRSI D <= threshold on the specified resample freq. None if insufficient bars."""
    try:
        s = daily.dropna()
        s.index = pd.to_datetime(s.index)
        rs = s.resample(freq).last().dropna()
        if len(rs) < _MIN_WEEKLY_BARS:
            return None
        _, d = _stoch_rsi_kd(rs)
        val = d.iloc[-1]
        if pd.isna(val):
            return None
        return bool(float(val) <= threshold)
    except Exception:
        return None


def _w1_macd(daily: pd.Series) -> str | None:
    """Weekly MACD(12,26,9) state: 'crossed'|'near'|None."""
    try:
        s = daily.dropna()
        s.index = pd.to_datetime(s.index)
        wk = s.resample("W-FRI").last().dropna()
        if len(wk) < _MIN_WEEKLY_BARS:
            return None

        ema12 = wk.ewm(span=12, min_periods=12).mean()
        ema26 = wk.ewm(span=26, min_periods=26).mean()
        macd  = ema12 - ema26
        sig   = macd.ewm(span=9, min_periods=9).mean()
        hist  = macd - sig

        hist = hist.dropna()
        if len(hist) < 3:
            return None

        h_now  = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])

        # Crossed: histogram >= 0 and was < 0 within last 2 bars
        if h_now >= 0 and h_prev < 0:
            return "crossed"

        # Near: histogram still negative but rising toward zero; linear extrap <=2 bars away
        if h_now < 0:
            h_m2 = float(hist.iloc[-3]) if len(hist) >= 3 else h_prev
            rising = h_now > h_prev and h_prev > h_m2
            if rising:
                # Linear extrapolation: bars to zero from current slope
                slope = h_now - h_m2  # 2-bar slope
                if slope > 0:
                    bars_to_zero = -h_now / slope
                    if bars_to_zero <= 2:
                        return "near"

        return None
    except Exception:
        return None


def _w1_stoch(daily: pd.Series) -> str | None:
    """Weekly StochRSI k/d cross state: 'crossed'|'near'|None."""
    try:
        s = daily.dropna()
        s.index = pd.to_datetime(s.index)
        wk = s.resample("W-FRI").last().dropna()
        if len(wk) < _MIN_WEEKLY_BARS:
            return None

        k, d = _stoch_rsi_kd(wk)
        k = k.dropna()
        d = d.dropna()
        if len(k) < 2 or len(d) < 2:
            return None

        k_now, k_prev = float(k.iloc[-1]), float(k.iloc[-2])
        d_now, d_prev = float(d.iloc[-1]), float(d.iloc[-2])

        # Crossed: k > d now and (prev k <= prev d) within last 2 bars
        if k_now > d_now and k_prev <= d_prev:
            return "crossed"

        # Near: k < d, k rising, gap <= 8
        if k_now < d_now and k_now > k_prev and (d_now - k_now) <= 8:
            return "near"

        return None
    except Exception:
        return None


def _compute_tech(ticker: str, panel: pd.DataFrame, root: Path) -> dict:
    """Compute tech dict for one ticker. Never raises."""
    base: dict[str, Any] = {
        "covered": False, "tier": None, "tier_eligible": False,
        "tier_provisional": False,
        "washout_2w": None, "washout_1m": None,
        "w1_macd": None, "w1_stoch": None, "asof": None,
    }
    if not ticker:
        return base

    # Confluence tier from site/factordata/signal_gate.json
    try:
        repo = _repo_root(root)
        sg_path = repo / "site" / "factordata" / "signal_gate.json"
        if sg_path.exists():
            sg = json.loads(sg_path.read_text())
            v = sg.get("verdicts", {}).get(ticker, {})
            base["tier_eligible"] = bool(v.get("eligible", False))
            base["tier_provisional"] = bool(v.get("provisional", False))
            base["asof"] = sg.get("as_of")
            tc = v.get("tier_cascade") or v.get("tier_sub")
            if tc:
                base["tier"] = tc  # e.g. 'T1','T2','T3','T4'
    except Exception as e:
        log.warning("signal_gate read error for %s: %s", ticker, e)

    # Price series for weekly indicators
    closes = _get_ticker_closes(ticker, panel, root)
    if closes is None or len(closes) < 10:
        return base

    base["covered"] = len(closes) >= _MIN_DAILY_BARS

    try:
        base["washout_2w"] = _washout_flag(closes, "2W-FRI")
    except Exception:
        pass

    try:
        base["washout_1m"] = _washout_flag(closes, "ME")
    except Exception:
        pass

    try:
        base["w1_macd"] = _w1_macd(closes)
    except Exception:
        pass

    try:
        base["w1_stoch"] = _w1_stoch(closes)
    except Exception:
        pass

    return base


# ---------------------------------------------------------------------------
# Ident
# ---------------------------------------------------------------------------

def _mc_bucket(mc_musd: Any) -> str | None:
    try:
        mc = float(mc_musd)
        if mc < 300:
            return "micro"
        if mc < 2000:
            return "small"
        if mc < 10000:
            return "mid"
        return "large"
    except (TypeError, ValueError):
        return None


def _build_themes_index(root: Path) -> dict[str, list[str]]:
    """Returns {ticker: [theme_name, ...]} (up to 3 themes per ticker)."""
    out: dict[str, list[str]] = {}
    try:
        p = root / "themes_heatmap" / "themes_tree.json"
        if not p.exists():
            return out
        data = json.loads(p.read_text())
        if not isinstance(data, list):
            return out
        for entry in data:
            theme_name = entry.get("key") or entry.get("theme") or ""
            for sub in (entry.get("subsectors") or []):
                for member in (sub.get("members") or []):
                    if isinstance(member, str):
                        tlist = out.setdefault(member, [])
                        if theme_name and len(tlist) < 3 and theme_name not in tlist:
                            tlist.append(theme_name)
    except Exception as e:
        log.warning("themes_tree read error: %s", e)
    return out


def _compute_ident(ticker: str, mc_musd: Any, root: Path,
                   sector_map: dict[str, str],
                   industry_map: dict[str, dict],
                   themes_index: dict[str, list[str]]) -> dict:
    return {
        "sector":       sector_map.get(ticker),
        "sub_industry": (industry_map.get(ticker) or {}).get("sub_industry"),
        "themes":       list(themes_index.get(ticker, [])),
        "mc_bucket":    _mc_bucket(mc_musd),
    }


# ---------------------------------------------------------------------------
# Favor
# ---------------------------------------------------------------------------

# GICS-ish -> calls.parquet 'name' normalisation map
_SECTOR_NORM: dict[str, str] = {
    "Health Care":               "Health Care",
    "Healthcare":                "Health Care",
    "Information Technology":    "Technology",
    "Technology":                "Technology",
    "Consumer Discretionary":    "Consumer Discretionary",
    "Consumer Staples":          "Consumer Staples",
    "Financials":                "Financials",
    "Financial Services":        "Financials",
    "Industrials":               "Industrials",
    "Energy":                    "Energy",
    "Materials":                 "Materials",
    "Utilities":                 "Utilities",
    "Real Estate":               "Real Estate",
    "Communication Services":    "Communication Services",
    "Comm Services":             "Communication Services",
    "Telecommunications":        "Communication Services",
}

# subsector_rotation.json 'name' -> 'quadrant' (sector-level)
# Built lazily at first enrich() call


def _build_sector_stance_map(root: Path) -> dict[str, str]:
    """Returns {normalised_sector_name: stance_label} from latest sector calls."""
    out: dict[str, str] = {}
    try:
        p = root / "sector_central" / "calls.parquet"
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        if "kind" not in df.columns:
            return out
        df_s = df[df["kind"] == "sector"]
        if df_s.empty:
            return out
        maxdate = df_s["date"].max()
        latest = df_s[df_s["date"] == maxdate]
        for _, row in latest.iterrows():
            raw_name = str(row.get("name") or "")
            label    = str(row.get("label") or "")
            # Store under the canonical name directly
            out[raw_name] = label
    except Exception as e:
        log.warning("sector_central calls read error: %s", e)
    return out


def _build_rotation_map(root: Path) -> dict[str, str]:
    """Returns {normalised_sector_name: quadrant} from subsector_rotation.json."""
    out: dict[str, str] = {}
    try:
        repo = _repo_root(root)
        p = repo / "site" / "marketdata" / "subsector_rotation.json"
        if not p.exists():
            return out
        data = json.loads(p.read_text())
        for entry in (data.get("sectors") or []):
            name     = str(entry.get("name") or "")
            quadrant = str(entry.get("quadrant") or "")
            if name and quadrant:
                out[name] = quadrant
    except Exception as e:
        log.warning("subsector_rotation read error: %s", e)
    return out


def _build_standout_map(root: Path) -> dict[str, str]:
    """Returns {ticker: 'buy_now'|'partial'|'watch'} from us_standouts.json."""
    out: dict[str, str] = {}
    try:
        repo = _repo_root(root)
        p = repo / "site" / "factordata" / "us_standouts.json"
        if not p.exists():
            return out
        data = json.loads(p.read_text())
        for row in (data.get("buy") or []):
            t = str(row.get("ticker") or "")
            if not t:
                continue
            es = (row.get("entry_signal") or {})
            status = str(es.get("status") or "")
            if status in ("buy_now", "partial"):
                out[t] = status
            elif t not in out:
                out[t] = "watch"
    except Exception as e:
        log.warning("us_standouts read error: %s", e)
    return out


def _build_theme_ready_map(root: Path,
                           themes_index: dict[str, list[str]]) -> dict[str, tuple[bool | None, float | None]]:
    """Returns {ticker: (theme_ready, theme_score)} from foresight_cascade + themes_index."""
    out: dict[str, tuple[bool | None, float | None]] = {}
    try:
        repo = _repo_root(root)
        p = repo / "site" / "basketdata" / "foresight_cascade.json"
        if not p.exists():
            return out
        data = json.loads(p.read_text())

        # Build a map from foresight theme id -> (entry_ready, score)
        fc_themes: dict[str, tuple[bool, float | None]] = {}
        for th in (data.get("themes") or []):
            tid   = str(th.get("theme") or "")
            ready = bool(th.get("entry_ready", False))
            score = th.get("score")
            fc_themes[tid] = (ready, float(score) if score is not None else None)

        # Build ticker->theme mapping also from crosswalk where possible
        # crosswalk: theme.id -> theme.subsector_keys (list of theme name strings)
        # themes_tree: theme.key == theme name used in themes_index

        # Simple approach: for each ticker, check its themes (from themes_index) against crosswalk
        try:
            repo2 = _repo_root(root)
            cw_path = repo2 / "config" / "theme_crosswalk.yml"
            if cw_path.exists():
                import yaml  # stdlib-available in this repo
                cw = yaml.safe_load(cw_path.read_text())
                # crosswalk themes list: [{'id': str, 'foresight_id': str, 'subsector_keys': [...]}]
                # subsector_keys are theme names (from themes_tree.key)
                key_to_foresight: dict[str, str] = {}
                for entry in (cw.get("themes") or []):
                    fid = str(entry.get("foresight_id") or entry.get("id") or "")
                    for sk in (entry.get("subsector_keys") or []):
                        key_to_foresight[str(sk)] = fid
            else:
                key_to_foresight = {}
        except Exception as e2:
            log.warning("theme_crosswalk read error: %s", e2)
            key_to_foresight = {}

        # Now map each ticker's themes -> foresight theme readiness
        for ticker, theme_names in themes_index.items():
            best_ready: bool | None = None
            best_score: float | None = None
            for tn in theme_names:
                fid = key_to_foresight.get(tn)
                if fid and fid in fc_themes:
                    rd, sc = fc_themes[fid]
                    if best_ready is None or (rd and not best_ready):
                        best_ready = rd
                        best_score = sc
                    elif best_score is None or (sc is not None and sc > best_score):
                        best_score = sc
            # Only set if we found a clean crosswalk match
            if best_ready is not None or best_score is not None:
                out[ticker] = (best_ready, best_score)

    except Exception as e:
        log.warning("foresight_cascade read error: %s", e)
    return out


def _lookup_sector_stance(sector: str | None,
                          stance_map: dict[str, str]) -> str | None:
    """Normalise sector name and look up stance label."""
    if not sector:
        return None
    # direct lookup
    if sector in stance_map:
        return stance_map[sector]
    # normalise via _SECTOR_NORM
    normalised = _SECTOR_NORM.get(sector)
    if normalised and normalised in stance_map:
        return stance_map[normalised]
    # fuzzy: lower-case prefix match
    sl = sector.lower()
    for k, v in stance_map.items():
        if sl in k.lower() or k.lower() in sl:
            return v
    return None


def _lookup_rotation(sector: str | None,
                     rotation_map: dict[str, str]) -> str | None:
    if not sector:
        return None
    # direct
    if sector in rotation_map:
        return rotation_map[sector]
    normalised = _SECTOR_NORM.get(sector)
    if normalised and normalised in rotation_map:
        return rotation_map[normalised]
    sl = sector.lower()
    for k, v in rotation_map.items():
        if sl in k.lower() or k.lower() in sl:
            return v
    return None


_VALID_STANCE = frozenset({"Accumulate", "Constructive", "Neutral", "Cautious", "Reduce"})
_VALID_ROTATION = frozenset({"leading", "improving", "weakening", "lagging"})


def _compute_favor(ticker: str, sector: str | None,
                   stance_map: dict[str, str],
                   rotation_map: dict[str, str],
                   standout_map: dict[str, str],
                   theme_ready_map: dict[str, tuple]) -> dict:
    stance_raw = _lookup_sector_stance(sector, stance_map)
    stance     = stance_raw if stance_raw in _VALID_STANCE else None
    rot_raw    = _lookup_rotation(sector, rotation_map)
    rotation   = rot_raw if rot_raw in _VALID_ROTATION else None

    tr_pair = theme_ready_map.get(ticker)
    if tr_pair is not None:
        theme_ready  = tr_pair[0]
        theme_score  = tr_pair[1]
    else:
        theme_ready  = None
        theme_score  = None

    standout = standout_map.get(ticker)

    return {
        "sector_stance": stance,
        "rotation":      rotation,
        "theme_ready":   theme_ready,
        "theme_score":   theme_score,
        "standout":      standout,
    }


# ---------------------------------------------------------------------------
# Setup score
# ---------------------------------------------------------------------------

def _ev_score(s: dict) -> float:
    """0-30 evidence value component."""
    pr   = s.get("prior") or {}
    win  = pr.get("win_20d_pct")
    med  = pr.get("med_ret_20d_pct")
    conf = s.get("confidence") or ""
    live = bool(s.get("live"))
    slane = s.get("source_lane") or ""

    if win is not None and med is not None:
        if win >= 60 and med > 0:
            base = 18
        elif win >= 50:
            base = 12
        else:
            base = 8
        if win < 45 or med < 0:
            base = 3
    else:
        base = 8

    conf_bonus = {"high": 6, "medium": 3}.get(conf, 0)
    live_bonus = 3 if live else 0
    struct_bonus = 3 if (conf == "high" and slane in ("edgar", "digest")) else 0

    return min(30, base + conf_bonus + live_bonus + struct_bonus)


def _gate_score(tech: dict) -> float:
    """0-30 tier gate component."""
    tier = tech.get("tier")
    if tier == "T2":
        return 30.0
    if tier == "T1":
        return 27.0
    if tier == "T3":
        return 18.0
    if tier == "T4":
        return 8.0
    if tech.get("tier_eligible"):
        return 4.0
    return 0.0


def _timing_score(tech: dict) -> float:
    """0-20 (capped) timing component."""
    pts = 0.0
    if tech.get("washout_2w"):
        pts += 6
    if tech.get("washout_1m"):
        pts += 4
    w1m = tech.get("w1_macd")
    if w1m == "crossed":
        pts += 5
    elif w1m == "near":
        pts += 3
    w1s = tech.get("w1_stoch")
    if w1s == "crossed":
        pts += 5
    elif w1s == "near":
        pts += 3
    return min(20, pts)


def _align_score(favor: dict) -> float:
    """0-20 (capped) alignment component."""
    pts = 0.0
    stance = favor.get("sector_stance")
    if stance == "Accumulate":
        pts += 8
    elif stance == "Constructive":
        pts += 5
    elif stance == "Neutral":
        pts += 2
    rot = favor.get("rotation")
    if rot == "leading":
        pts += 4
    elif rot == "improving":
        pts += 2
    if favor.get("theme_ready"):
        pts += 4
    elif (favor.get("theme_score") or 0) >= 60:
        pts += 2
    so = favor.get("standout")
    if so in ("buy_now", "partial"):
        pts += 4
    return min(20, pts)


def _compute_setup(s: dict, tech: dict, ident: dict, favor: dict) -> dict:
    """Compute setup dict: score, grade, why, why_zh."""
    ev      = _ev_score(s)
    gate    = _gate_score(tech)
    timing  = _timing_score(tech)
    align   = _align_score(favor)

    raw = ev + gate + timing + align

    # Multipliers / caps
    conf = s.get("confidence") or ""
    if conf == "low":
        raw *= 0.75

    mc_musd = s.get("mc_musd")
    try:
        float(mc_musd)
    except (TypeError, ValueError):
        raw *= 0.9

    terminal = s.get("terminal") or ""
    score = round(float(raw), 1)
    if terminal in ("closed", "terminated"):
        score = round(float(min(raw, 25)), 1)
        grade: str | None = None
    else:
        # LLM de-escalation: v1_direction < 0 caps at 49
        v1d = s.get("v1_direction")
        try:
            if v1d is not None and float(v1d) < 0:
                score = round(float(min(raw, 49)), 1)
        except (TypeError, ValueError):
            pass

        tier = tech.get("tier")
        if score >= 70 and tier in ("T1", "T2", "T3"):
            grade = "A"
        elif score >= 55:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = None

    # why/why_zh: pick top 3 contributing components in plain words
    why: list[str] = []
    why_zh: list[str] = []

    if tech.get("tier") in ("T1", "T2", "T3"):
        why.append("Buy setup live")
        why_zh.append("买点设置已触发")
    elif tech.get("tier_eligible"):
        why.append("Setup approaching entry level")
        why_zh.append("设置趋近入场条件")

    if tech.get("washout_2w") or tech.get("washout_1m"):
        why.append("Deeply oversold (weeks)")
        why_zh.append("周线深度超卖")

    stance = favor.get("sector_stance")
    if stance in ("Accumulate", "Constructive"):
        why.append("Sector in favor")
        why_zh.append("板块获看好")

    rot = favor.get("rotation")
    if rot == "leading":
        why.append("Sector leading rotation")
        why_zh.append("板块领跑轮动")

    so = favor.get("standout")
    if so in ("buy_now", "partial"):
        why.append("On active buy list")
        why_zh.append("列于当前买入名单")

    pr = s.get("prior") or {}
    win = pr.get("win_20d_pct")
    if win is not None and win >= 60:
        why.append("Strong history for this event type")
        why_zh.append("此类事件历史表现强")

    if s.get("live"):
        why.append("EDGAR filing confirmed")
        why_zh.append("EDGAR申报已确认")

    if favor.get("theme_ready"):
        why.append("Theme ready for entry")
        why_zh.append("主题已具备入场条件")

    # Trim to 3
    why    = why[:3]
    why_zh = why_zh[:3]

    # If nothing positive and score is positive, add fallback
    if not why and score >= 40:
        why    = ["Event filed with structured data"]
        why_zh = ["已提交结构化事件申报"]

    return {"score": score, "grade": grade, "why": why, "why_zh": why_zh}


# ---------------------------------------------------------------------------
# JSON sanitizer
# ---------------------------------------------------------------------------

def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# ---------------------------------------------------------------------------
# enrich()
# ---------------------------------------------------------------------------

def enrich(sits: list[dict], root: Path | None = None) -> dict:
    """Mutate each situation dict IN PLACE adding keys 'tech','ident','favor','setup'.

    Returns {'coverage': {counts}}.
    """
    data_root = _data_root(root)

    # Build panel once
    panel = _load_closes_panel(data_root)

    # Build lookup tables
    sector_map: dict[str, str] = {}
    try:
        p = data_root / "breadth" / "ticker_sectors.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "ticker" in df.columns and "sector" in df.columns:
                sector_map = dict(zip(df["ticker"], df["sector"]))
    except Exception as e:
        log.warning("ticker_sectors read error: %s", e)

    industry_map: dict[str, dict] = {}
    try:
        p = data_root / "sp500_heatmap" / "industry_map.json"
        if p.exists():
            industry_map = json.loads(p.read_text())
    except Exception as e:
        log.warning("industry_map read error: %s", e)

    themes_index = _build_themes_index(data_root)
    stance_map   = _build_sector_stance_map(data_root)
    rotation_map = _build_rotation_map(data_root)
    standout_map = _build_standout_map(data_root)
    theme_ready_map = _build_theme_ready_map(data_root, themes_index)

    # Per-sit enrichment
    n_covered = n_graded = n_a = n_b = 0
    for s in sits:
        ticker = s.get("ticker") or ""

        try:
            tech = _compute_tech(ticker, panel, data_root) if ticker else {
                "covered": False, "tier": None, "tier_eligible": False,
                "tier_provisional": False,
                "washout_2w": None, "washout_1m": None,
                "w1_macd": None, "w1_stoch": None, "asof": None,
            }
        except Exception as e:
            log.warning("tech compute error %s: %s", ticker, e)
            tech = {"covered": False, "tier": None, "tier_eligible": False,
                    "tier_provisional": False,
                    "washout_2w": None, "washout_1m": None,
                    "w1_macd": None, "w1_stoch": None, "asof": None}

        try:
            sector = sector_map.get(ticker)
            ident = _compute_ident(ticker, s.get("mc_musd"), data_root,
                                   sector_map, industry_map, themes_index)
        except Exception as e:
            log.warning("ident compute error %s: %s", ticker, e)
            ident = {"sector": None, "sub_industry": None, "themes": [], "mc_bucket": None}
            sector = None

        try:
            sector = ident.get("sector")
            favor = _compute_favor(ticker, sector, stance_map, rotation_map,
                                   standout_map, theme_ready_map)
        except Exception as e:
            log.warning("favor compute error %s: %s", ticker, e)
            favor = {"sector_stance": None, "rotation": None,
                     "theme_ready": None, "theme_score": None, "standout": None}

        try:
            setup = _compute_setup(s, tech, ident, favor)
        except Exception as e:
            log.warning("setup compute error %s: %s", ticker, e)
            setup = {"score": 0.0, "grade": None, "why": [], "why_zh": []}

        s["tech"]  = _json_safe(tech)
        s["ident"] = _json_safe(ident)
        s["favor"] = _json_safe(favor)
        s["setup"] = _json_safe(setup)

        if tech.get("covered"):
            n_covered += 1
        g = setup.get("grade")
        if g is not None:
            n_graded += 1
            if g == "A":
                n_a += 1
            elif g == "B":
                n_b += 1

    return {
        "coverage": {
            "total":    len(sits),
            "covered":  n_covered,
            "grade_a":  n_a,
            "grade_b":  n_b,
            "graded":   n_graded,
        }
    }


# ---------------------------------------------------------------------------
# build_context_feed()
# ---------------------------------------------------------------------------

def _prev_state_from_sits(sits: list[dict]) -> dict[str, dict]:
    """Build by_key dict {TICKER|Category: {stage, grade}} from current sits."""
    out: dict[str, dict] = {}
    for s in sits:
        t  = s.get("ticker") or ""
        c  = s.get("category") or ""
        if not t or not c:
            continue
        key = f"{t}|{c}"
        out[key] = {
            "stage": s.get("stage") or "",
            "grade": (s.get("setup") or {}).get("grade"),
        }
    return out


def _diff_by_key(base_by_key: dict[str, dict],
                 new_by_key: dict[str, dict]) -> list[dict]:
    """Compute change items by diffing base snapshot -> new snapshot."""
    items: list[dict] = []
    for key, cur in new_by_key.items():
        t, cat = key.split("|", 1) if "|" in key else (key, "")
        if key not in base_by_key:
            items.append({"kind": "new", "ticker": t, "category": cat,
                          "from": None, "to": cur.get("stage")})
            continue
        old = base_by_key[key]
        # Stage change — detect terminal transition first, fall through to generic stage
        if old.get("stage") != cur.get("stage"):
            _TERMINAL = {"terminated", "closed", "completed"}
            if cur.get("stage") in _TERMINAL and old.get("stage") not in _TERMINAL:
                # Transition into a terminal stage: emit kind='terminal' (not kind='stage')
                items.append({"kind": "terminal", "ticker": t, "category": cat,
                              "from": old.get("stage"), "to": cur.get("stage")})
            else:
                # Non-terminal stage change (or already-terminal→terminal shift)
                items.append({"kind": "stage", "ticker": t, "category": cat,
                              "from": old.get("stage"), "to": cur.get("stage")})
        # Grade change
        old_g = old.get("grade")
        new_g = cur.get("grade")
        if old_g != new_g and (old_g is not None or new_g is not None):
            _GRADE_ORDER = {None: 0, "C": 1, "B": 2, "A": 3}
            kind = "grade_up" if _GRADE_ORDER.get(new_g, 0) > _GRADE_ORDER.get(old_g, 0) else "grade_down"
            items.append({"kind": kind, "ticker": t, "category": cat,
                          "from": old_g, "to": new_g})
    return items


def _build_changes_block(old_contract: dict | None,
                         new_by_key: dict[str, dict],
                         new_asof: str) -> tuple[dict, dict]:
    """Same-day-idempotent changes block (mirrors transmission_context.build_changes logic).

    Returns (changes_block, prev_state_block).

    Storage semantics:
    - contract.prev_state.by_key = the diff BASE (yesterday's state) — frozen for the day.
    - contract._current_by_key   = current day's snapshot — used as base by NEXT day.

    Same-day idempotence: re-runs reuse prev_state.by_key (unchanged) as diff base
    so the change set accumulates instead of being wiped.
    """
    if old_contract is None:
        # First run: no phantom 'new' flood.  prev_state has no history yet.
        return (
            {"items": [], "n": 0},
            {"asof": None, "by_key": {}},
        )

    old_asof = old_contract.get("asof")

    if old_asof != new_asof:
        # New day: diff old day's CURRENT snapshot (stored as _current_by_key) -> new
        # Fallback to prev_state.by_key for contracts written before _current_by_key existed.
        base_by_key = (old_contract.get("_current_by_key")
                       or (old_contract.get("prev_state") or {}).get("by_key")
                       or {})
        base_asof   = old_asof
    else:
        # Same-day rebuild: keep yesterday's diff base unchanged (prev_state.by_key)
        # so the change set is stable across same-day re-runs.
        stored_ps   = old_contract.get("prev_state") or {}
        base_by_key = stored_ps.get("by_key") or {}
        base_asof   = stored_ps.get("asof")

    if not base_by_key or base_asof is None:
        return (
            {"items": [], "n": 0},
            {"asof": base_asof, "by_key": base_by_key},
        )

    items     = _diff_by_key(base_by_key, new_by_key)
    changes   = {"items": items, "n": len(items)}
    prev_state = {"asof": base_asof, "by_key": base_by_key}
    return changes, prev_state


def build_context_feed(sits: list[dict],
                       asof: str | None = None,
                       root: Path | None = None) -> dict:
    """Compute + write data/special_situations/context/latest.json.

    Same-day idempotent: re-run on the same asof reuses old prev_state so
    re-renders don't wipe the day's accumulated changes.

    Returns the written dict.
    """
    data_root = _data_root(root)
    outdir    = data_root / "special_situations" / "context"
    outpath   = outdir / "latest.json"
    built     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Enrich in place (also computes tech/ident/favor/setup).
    # Skip situations already enriched (carry 'setup' key) to avoid double
    # weekly-tech compute against the render budget.
    unenriched = [s for s in sits if "setup" not in s]
    if unenriched:
        coverage = enrich(unenriched, root=root)
    else:
        coverage = {"coverage": {}}

    # Read old contract for idempotence
    old_contract: dict | None = None
    if outpath.exists():
        try:
            old_contract = json.loads(outpath.read_text())
        except Exception as e:
            log.warning("context feed: could not read old latest.json: %s", e)

    # Build counts
    n_total    = len(sits)
    n_grade_a  = sum(1 for s in sits if (s.get("setup") or {}).get("grade") == "A")
    n_grade_b  = sum(1 for s in sits if (s.get("setup") or {}).get("grade") == "B")
    n_arb      = sum(1 for s in sits if s.get("arb"))
    n_cross    = sum(1 for s in sits if s.get("cross_border"))

    # Changes block
    new_by_key = _prev_state_from_sits(sits)
    changes, prev_state = _build_changes_block(old_contract, new_by_key, asof)
    n_new_today = sum(1 for item in changes["items"] if item.get("kind") == "new")

    # Top setups (any graded name A/B/C, score desc, up to 10 — the grade word on the
    # card keeps an 'Early' name honest; A/B-only left the strip near-empty on calm tapes)
    graded = [s for s in sits if (s.get("setup") or {}).get("grade") in ("A", "B", "C")]
    graded.sort(key=lambda s: (s.get("setup") or {}).get("score") or 0, reverse=True)
    top_setups = []
    for s in graded[:10]:
        setup = s.get("setup") or {}
        tech  = s.get("tech") or {}
        top_setups.append({
            "ticker":     s.get("ticker"),
            "company":    s.get("company"),
            "category":   s.get("category"),
            "stage":      s.get("stage"),
            "grade":      setup.get("grade"),
            "score":      setup.get("score"),
            "tier":       tech.get("tier"),
            "mc_musd":    s.get("mc_musd"),
            "date_filed": s.get("date_filed"),
            "why":        setup.get("why") or [],
            "why_zh":     setup.get("why_zh") or [],
        })

    # Risk-arb top (up to 5: ticker, company, gross_spread_pct, annualized_pct, days_to_close)
    arb_rows = [s for s in sits if s.get("arb")]
    arb_rows.sort(key=lambda s: (s.get("arb") or {}).get("annualized_pct") or 0, reverse=True)
    risk_arb_top = []
    for s in arb_rows[:5]:
        arb = s.get("arb") or {}
        risk_arb_top.append({
            "ticker":           s.get("ticker"),
            "company":          s.get("company"),
            "gross_spread_pct": arb.get("gross_spread_pct"),
            "annualized_pct":   arb.get("annualized_pct"),
            "days_to_close":    arb.get("days_to_close"),
        })

    contract = {
        "schema":     "special_sits_context.v1",
        "asof":       asof,
        "built":      built,
        "is_context_only": True,
        "disclaimer": ("Context only — event tracking + display-tier setup ranking, "
                       "never a signal or sizing input."),
        "counts": {
            "total":         n_total,
            "new_today":     n_new_today,
            "grade_a":       n_grade_a,
            "grade_b":       n_grade_b,
            "with_arb":      n_arb,
            "cross_border":  n_cross,
        },
        "top_setups":    top_setups,
        "changes":       changes,
        # prev_state.by_key = the diff base (frozen at the start of the day).
        # _current_by_key   = today's current snapshot (used as base by the NEXT day).
        "prev_state":      prev_state,
        "_current_by_key": new_by_key,
        "risk_arb_top":    risk_arb_top,
    }

    contract = _json_safe(contract)

    # Write
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        outpath.write_text(json.dumps(contract, indent=2, ensure_ascii=False))
    except Exception as e:
        log.error("context feed: failed to write %s: %s", outpath, e)

    return contract
