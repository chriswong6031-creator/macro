"""Foresight Earliness Engine — Q3 of the Foresight Desk Upgrade (research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md §1 Q3).

Measures ATTENTION, not revisions. The idea: a theme that nobody is watching yet is early;
one that is already loud/crowded/re-rated is late. Four legs, each independently rank-
percentiled cross-sectionally (no absolute thresholds) — missing legs shrink the denominator
and never default-fill (house rule: degrade to None, never launder absence as measurement).

Legs:
  coverage_arrival — n_covering from data/revisions/latest.parquet IF the field exists
                     (W2a PR adds it). Absent → leg absent. NEVER falls back to n_analysts
                     (that is the audited saturated-reviser count, not coverage arrival).
  news_flow       — per-theme velocity from engine/news_flow.theme_flow (quiet = early).
                     Only themes with a BASKET_TO_GDELT_THEME mapping have this leg.
  ownership_breadth — count of theme members with 13f_add channel in data/altdata/by_ticker.json.
                      More 13f-adds = more crowded = later (inverse: fewer = earlier).
  tape_extension  — member-EW distance from 52-week high from data/yahoo/*.parquet closes.
                     Near the high = already re-rated = late (inverse: far from high = earlier).

earliness = 1 − rank_pct(mean of available attention legs), cross-sectionally.
So the MOST-attended theme (highest mean) gets earliness=0; least-attended gets earliness=1.

Output: {themes: {k: {earliness, legs: {...}, n_legs_live}}, note}
Side-effect (write_log=True only): appends one row per theme per day to
data/foresight/earliness_log.jsonl (append-only, deduped by theme+date) for
forward-grading by engine/foresight_leadlag.py. The display callers
(foresight_score/sizing/convergence) all pass write_log=False; the nightly
append is driven by scripts/grade_thematic.py stage 1 — the log's sole advancer.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)


from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

# Legs that are scaled 0..1 where HIGHER = MORE attention (later / more crowded).
# earliness = 1 - rank_pct(mean of available attention legs).
# "inverse" legs (where more = EARLIER) are inverted before entering the mean.
_LEG_NAMES = ("coverage_arrival", "news_flow", "ownership_breadth", "tape_extension")
# A leg counts only when at least this many themes carry it — a percentile over a
# 2-3 theme cross-section is noise, not measurement (review Bug B gate i).
LEG_MIN_COVERAGE = 6


def _rank_pct(values: list[float | None]) -> list[float | None]:
    """Cross-sectional rank-percentile. None → None (absent theme-leg stays absent).
    Ties broken by averaging ranks. Returns floats in [0, 1]."""
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(indexed) < 2:
        # a percentile over <2 valid values is undefined — absent, never a fabricated
        # midpoint (review minor: 0.5 here would launder absence as measurement)
        return [None] * len(values)
    n = len(indexed)
    sorted_vals = sorted(indexed, key=lambda x: x[1])
    ranks: dict[int, float] = {}
    j = 0
    while j < n:
        k = j
        while k + 1 < n and sorted_vals[k + 1][1] == sorted_vals[j][1]:
            k += 1
        # ties: average rank (0-indexed / (n-1))
        avg_rank = (j + k) / 2 / (n - 1) if n > 1 else 0.5
        for idx in range(j, k + 1):
            ranks[sorted_vals[idx][0]] = avg_rank
        j = k + 1
    result = [None] * len(values)
    for i, _ in indexed:
        result[i] = ranks[i]
    return result


# ---------------------------------------------------------------------------
# Leg 1: coverage arrival — n_covering from revisions/latest.parquet
# ---------------------------------------------------------------------------

def _leg_coverage_arrival(theme_members: dict[str, list[str]]) -> dict[str, float | None]:
    """Count of analysts covering members of each theme from n_covering field.
    ONLY reads n_covering — never n_analysts (audited saturated-reviser count).
    If the field is absent (W2a not yet merged), returns {theme: None} for all."""
    p = config.data_dir() / "revisions" / "latest.parquet"
    if not p.exists():
        return {k: None for k in theme_members}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("earliness: coverage_arrival parquet unreadable: %s", e)
        return {k: None for k in theme_members}
    if "n_covering" not in df.columns:
        # W2a has not merged — field absent; leg absent per spec
        return {k: None for k in theme_members}
    out = {}
    for theme, members in theme_members.items():
        present = [m for m in members if m in df.index]
        if not present:
            out[theme] = None
            continue
        vals = df.loc[present, "n_covering"].dropna()
        if vals.empty:
            out[theme] = None
        else:
            out[theme] = float(vals.mean())
    return out


# ---------------------------------------------------------------------------
# Leg 2: news flow — quiet tape = early; loud = crowded/late
# ---------------------------------------------------------------------------

def _leg_news_flow(theme_keys: list[str]) -> dict[str, float | None]:
    """Per-theme news velocity from engine/news_flow.theme_flow.
    Only foresight themes with a BASKET_TO_GDELT_THEME entry can have this leg.
    None when the mapping or events are absent."""
    try:
        from engine import news_flow as nf
    except Exception:  # noqa: BLE001
        return {k: None for k in theme_keys}
    try:
        events = nf.load_events()
    except Exception as e:  # noqa: BLE001
        log.debug("earliness: news events load failed: %s", e)
        events = None
    if events is None or events.empty:
        return {k: None for k in theme_keys}
    out = {}
    for key in theme_keys:
        try:
            result = nf.theme_flow(key, events)
        except Exception as e:  # noqa: BLE001
            log.debug("earliness: news_flow[%s] failed: %s", key, e)
            result = None
        if result is None:
            out[key] = None
        else:
            # velocity ≥ 0; louder = higher = later; we want attention score = velocity
            out[key] = max(0.0, float(result.get("velocity") or 0.0))
    return out


# ---------------------------------------------------------------------------
# Leg 3: ownership breadth — 13f_add count per theme
# ---------------------------------------------------------------------------

def _leg_ownership_breadth(theme_members: dict[str, list[str]]) -> dict[str, float | None]:
    """Count of theme members with 13f_add channel in data/altdata/by_ticker.json.
    More 13f-adds = more crowded = later. None when substrate absent."""
    p = config.data_dir() / "altdata" / "by_ticker.json"
    if not p.exists():
        return {k: None for k in theme_members}
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("earliness: by_ticker.json unreadable: %s", e)
        return {k: None for k in theme_members}
    tickers = (d or {}).get("tickers") or {}
    if not tickers:
        return {k: None for k in theme_members}
    out = {}
    for theme, members in theme_members.items():
        if not members:
            out[theme] = None
            continue
        count = sum(
            1 for m in members
            if "13f_add" in (tickers.get(m, {}).get("channels") or [])
        )
        # Return the count (more = later/crowded); leg is None only if no members
        out[theme] = float(count)
    return out


# ---------------------------------------------------------------------------
# Leg 4: tape extension — distance from 52-week high (member-EW)
# ---------------------------------------------------------------------------

def _closes(ticker: str) -> pd.Series | None:
    """Read close series from data/yahoo/<ticker>.parquet.
    Reuses the same pattern as engine/foresight_grader.py:_closes."""
    p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _leg_tape_extension(theme_members: dict[str, list[str]]) -> dict[str, float | None]:
    """Member-EW mean distance from 52-week high (0 = at high = late, 1 = very far from high = early).

    For the EARLINESS direction: near high = re-rated = late → HIGH attention score.
    So we return (1 − pct_from_high) as the attention proxy: 1.0 if at the 52-week high,
    0.0 if maximally far from it. This is then treated as POSITIVE attention (higher = later)
    and will be inverted by the rank-pct inversion in the earliness formula."""
    out = {}
    for theme, members in theme_members.items():
        ratios = []
        for m in members:
            s = _closes(m)
            if s is None or len(s) < 2:
                continue
            s = s.iloc[-252:] if len(s) >= 252 else s
            high_52w = float(s.max())
            last = float(s.iloc[-1])
            if high_52w <= 0:
                continue
            # pct_from_high in [0, 1]: 0 = AT high, 1 = far from high
            pct_from_high = (high_52w - last) / high_52w
            pct_from_high = float(np.clip(pct_from_high, 0.0, 1.0))
            # attention score = 1 - pct_from_high: 1 = AT high (re-rated = late)
            ratios.append(1.0 - pct_from_high)
        if not ratios:
            out[theme] = None
        else:
            out[theme] = float(np.mean(ratios))
    return out


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_foresight_earliness(
    themes_cfg: dict | None = None,
    *,
    write_log: bool = True,
) -> dict | None:
    """Compute per-theme earliness ∈ [0, 1] for foresight themes.

    earliness = 1 − rank_pct(mean attention score across available legs).
    Missing legs reduce the denominator; they NEVER contribute a 0.4/0.5 default.
    Returns None only on catastrophic failure (no theme config).
    """
    if themes_cfg is None:
        try:
            cfg = config.load() or {}
            themes_cfg = cfg.get("themes") or {}
        except Exception as e:  # noqa: BLE001
            log.warning("earliness: config load failed: %s", e)
            return None
    if not themes_cfg:
        return None

    theme_keys = list(themes_cfg.keys())
    theme_members: dict[str, list[str]] = {
        k: list(v.get("tickers") or []) for k, v in themes_cfg.items()
    }

    # --- compute each leg -----------------------------------------------
    cov = _leg_coverage_arrival(theme_members)
    news = _leg_news_flow(theme_keys)
    own = _leg_ownership_breadth(theme_members)
    tape = _leg_tape_extension(theme_members)

    # --- per-LEG cross-sectional rank-pct FIRST (review Bug A) -----------
    # Legs are incommensurable in raw units (news velocity ~31 vs ownership counts
    # {0,1,2} vs tape [0,1]) — a raw mean lets news swamp everything. Each leg is
    # rank-percentiled independently across themes (per the module contract), THEN
    # the per-leg percentiles are averaged. A leg is USABLE only when
    # (i) >= LEG_MIN_COVERAGE themes carry it (a 3-theme percentile is noise), and
    # (ii) its live values are not all tied (an all-zero ownership leg carries zero
    # discrimination and would fabricate a shared "measurement" for 12+ themes —
    # review Bug B).
    raw_legs = {
        "coverage_arrival": cov,
        "news_flow": news,
        "ownership_breadth": own,
        "tape_extension": tape,
    }
    leg_pcts: dict[str, dict[str, float | None]] = {}
    # coverage floor scales down for small desks: a leg covering 3 of 18 themes is
    # noise, but 3 of 3 is the full cross-section
    cov_floor = min(LEG_MIN_COVERAGE, len(theme_keys))
    for name, series in raw_legs.items():
        vals = [series.get(k) for k in theme_keys]
        live_vals = [v for v in vals if v is not None]
        usable = (len(live_vals) >= cov_floor
                  and len(set(live_vals)) > 1)         # all-tied leg = no information
        if not usable:
            leg_pcts[name] = {k: None for k in theme_keys}
            continue
        pcts = _rank_pct(vals)
        leg_pcts[name] = {k: pcts[i] for i, k in enumerate(theme_keys)}

    raw_scores: dict[str, float | None] = {}
    leg_values: dict[str, dict] = {}
    usable_counts: dict[str, int] = {}
    for k in theme_keys:
        legs = {name: raw_legs[name].get(k) for name in raw_legs}
        live_pcts = [leg_pcts[name][k] for name in raw_legs
                     if leg_pcts[name][k] is not None]
        raw_scores[k] = float(np.mean(live_pcts)) if live_pcts else None
        usable_counts[k] = len(live_pcts)
        leg_values[k] = legs

    # --- cross-sectional rank-pct of the combined attention score --------
    score_list = [raw_scores[k] for k in theme_keys]
    rp_list = _rank_pct(score_list)

    result_themes: dict[str, dict] = {}
    for i, k in enumerate(theme_keys):
        rp = rp_list[i]
        earliness = (1.0 - rp) if rp is not None else None
        if earliness is not None:
            earliness = round(float(np.clip(earliness, 0.0, 1.0)), 4)
        legs = leg_values[k]
        result_themes[k] = {
            "earliness": earliness,
            # n_legs_live counts USABLE legs (post coverage/tie gates) — the number a
            # downstream consumer must gate on; raw availability is in legs[..].available
            "n_legs_live": usable_counts[k],
            "legs": {
                name: {
                    "value": round(float(v), 4) if v is not None else None,
                    "available": v is not None,
                    "usable": leg_pcts[name][k] is not None,
                    "rank_pct": (round(leg_pcts[name][k], 4)
                                 if leg_pcts[name][k] is not None else None),
                }
                for name, v in legs.items()
            },
        }

    today_str = date.today().isoformat()
    payload = {
        "asof": today_str,
        "themes": result_themes,
        "note": (
            "display-only; earliness = 1 - rank_pct(mean attention score). "
            "Higher earliness = less attention = earlier opportunity. "
            "Missing legs shrink denominator; never default-filled. "
            "Crowding is NEGATIVE per house rule (ownership_breadth leg inverts)."
        ),
    }

    if write_log:
        try:
            _append_log(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("earliness: log append failed: %s", e)

    return payload


# ---------------------------------------------------------------------------
# Append-only log for forward-grading
# ---------------------------------------------------------------------------

def _append_log(payload: dict) -> None:
    """Append one row per theme per day to data/foresight/earliness_log.jsonl.
    Deduped by (theme, asof) so re-runs are idempotent."""
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "earliness_log.jsonl"

    # build dedup index from existing rows
    seen: set[tuple[str, str]] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                t, a = e.get("theme"), e.get("asof")
                if t and a:
                    seen.add((t, a))
            except Exception:  # noqa: BLE001
                continue

    asof = payload.get("asof", date.today().isoformat())
    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    for theme, data in (payload.get("themes") or {}).items():
        if (theme, asof) in seen:
            continue
        row = {
            "theme": theme,
            "asof": asof,
            "ts": ts,
            "earliness": data.get("earliness"),
            "n_legs_live": data.get("n_legs_live"),
            "legs": {
                name: leg.get("value")
                for name, leg in (data.get("legs") or {}).items()
            },
        }
        lines.append(json.dumps(row, separators=(",", ":")))

    if lines:
        if not _ledger_advance_enabled():
            log.debug(
                "foresight_earliness._append_log: write skipped "
                "(COLLECT_LANE != nightly)"
            )
            return
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
