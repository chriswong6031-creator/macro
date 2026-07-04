"""Sector Pulse — shared sector-rotation data product.

Reads the live theme_intel output (from site/basketdata/baskets.json or the equivalent
regional JSON) plus the append-only signal archive to produce a compact, per-theme
"pulse" row that any engine — Mastermind bot, Terminal, downstream scorers — can import
without pulling in the full scoring stack.

API surface
-----------
build_pulse(region="us") -> dict | None
    Returns a top-level pulse payload with a "themes" list; each theme carries the
    core identifiers, lifecycle state, rank/score (including archive-derived deltas),
    relative performance, breadth, and a "heat" tier.

    heat tier — descriptive, not a forecast (see _heat_tier docstring).

ticker_themes(region="us") -> dict[str, list[str]]
    Maps each live ticker → list of theme ids it currently belongs to, respecting
    point-in-time membership (added/removed dates).

for_ticker(ticker, region="us") -> dict | None
    Returns the strongest-pulse theme row for a ticker, plus "theme_ids" listing every
    theme it belongs to.  None when the ticker is not a live member of any theme.

write_pulse(ti, region, out_dir) -> None
    Persistence hook: writes site/basketdata/sector_pulse.json (US) or
    sector_pulse_<region>.json from a freshly-computed theme_intel dict.
    Additive and never-fatal; callers wrap in try/except.

Design notes
------------
- Additive, never fatal: every public function catches all exceptions and degrades to
  None / empty dict / empty list.  The persistence hook is wrapped by callers too.
- NO module-level logging.disable — module logger only; the `__main__` guard is
  irrelevant here (no disable call), but we call it out so linters stay happy.
- History is "accruing" semantics: rank/score deltas are None when the archive holds
  fewer rows than required for the requested look-back.
- Do not modify engine.theme_scoring outputs — this module is read-only w.r.t. scoring.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heat-tier thresholds (simple, documented, deterministic).
# ALL labels are DESCRIPTIVE — they characterise the current rank/score
# trajectory, never imply a forward-return forecast.
#
# Phase-0 kill-test (scripts.calibrate_sector_pulse_heat, 27y SPDR proxy,
# 2026-07-03): heating/hot showed NO forward-return edge vs same-day idle and,
# if anything, slightly DEEPER 21d drawdowns; cooling was not separately
# confirmed (the rank-drop leg dilutes the validated fading label); broken
# precedes measurably deeper drawdowns (consistent with the deteriorating
# label's baskets_calibration verdict). Tiers therefore stay display-only;
# _heat_strength() grades each tier from data/strategies/sector_pulse_heat.json.
# ---------------------------------------------------------------------------
# "heating": rank is improving fast (moved up ≥3 rank positions in 5 sessions
#            OR score rose ≥6 points in 5 sessions) AND the lifecycle label is
#            consistent with an upward phase (emerging or dominant).
_HEAT_RANK_DELTA = 3      # rank-position improvement over 5 sessions
_HEAT_SCORE_DELTA = 6     # score-point improvement over 5 sessions

# "hot": rank is in the top quartile of all themes (rank <= n/4, min 1) AND
#        the label is dominant or emerging AND the theme is not already cooling.
# Quartile boundary computed dynamically from n_themes at call time.

# "cooling": rank dropped ≥3 positions in 5 sessions OR the lifecycle label is "fading".
_COOL_RANK_DELTA = -3     # rank-position drop over 5 sessions (negative = worse rank)

# "broken": lifecycle label is "deteriorating" — structure is breaking down.
# "idle": everything else.

_HOT_LABELS = {"dominant", "emerging"}
_COOL_LABEL = "fading"
_BROKEN_LABEL = "deteriorating"

# ---------------------------------------------------------------------------
# Schema version — increment when the pulse payload shape changes materially.
# ---------------------------------------------------------------------------
SCHEMA = 1

# Archive stream names (must match signal_archive label keys).
_ARCHIVE_STREAM = {
    "us": "baskets",
    "china": "baskets_china",
    "hk": "baskets_hk",
    "canada": "baskets_canada",
    "intl": "baskets_intl",
}

# How many archive rows we need for each look-back window.
# N sessions ≈ N trading days; we request N+1 to have both endpoints.
_LOOKBACKS = {1: 2, 5: 6, 20: 21}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_theme_intel(region: str) -> dict | None:
    """Load the current theme_intel dict for a region.

    US: reads site/basketdata/baskets.json and extracts theme_intel.
    Other regions: reads site/basketdata/baskets_<region>.json similarly.
    Falls back to calling compute_theme_intel() when the file is absent.
    Returns None on any failure.
    """
    try:
        from lib import config
        site_dir = config.ROOT / "site" / "basketdata"
        fname = "baskets.json" if region == "us" else f"baskets_{region}.json"
        p = site_dir / fname
        if p.exists():
            payload = json.loads(p.read_text())
            ti = payload.get("theme_intel") if isinstance(payload, dict) else None
            if ti and ti.get("themes"):
                return ti
        # Fallback: recompute live (slower but correct when file is stale/absent)
        from engine.theme_scoring import compute_theme_intel
        return compute_theme_intel(region)
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse: could not load theme_intel for region=%s", region,
                    exc_info=True)
        return None


def _load_archive_snapshots(region: str) -> list[dict]:
    """Return archive snapshot rows as a list of dicts {asof, themes[]} sorted oldest→newest.

    Each row's 'themes' is the slim list written by _write_score_snapshot in build_baskets.py
    (keys: id, name, score, label, reco, rank, net_ad, components, bull_days, overbought,
    clean_entry, rollover).  Returns [] when the archive is absent or empty.
    """
    try:
        from engine.signal_archive import load_archive
        stream = _ARCHIVE_STREAM.get(region, f"baskets_{region}")
        df = load_archive(stream)
        if df is None or df.empty or "snapshot_json" not in df.columns:
            return []
        rows = []
        for _, row in df.sort_values("asof").iterrows():
            try:
                snap = json.loads(row["snapshot_json"])
                asof = str(row.get("asof") or snap.get("as_of") or "")
                themes = snap.get("themes") or []
                if asof and themes:
                    rows.append({"asof": asof, "themes": themes})
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception:  # noqa: BLE001
        log.debug("sector_pulse: archive unavailable for region=%s", region)
        return []


def _rank_map_at(snapshots: list[dict], offset_sessions: int) -> dict[str, int]:
    """Return {theme_id: rank} from `offset_sessions` rows before the last snapshot.

    offset_sessions=5 → use the snapshot that is ≥5 rows back (0-indexed from end).
    Returns {} when there are not enough rows.
    """
    needed = offset_sessions + 1   # need at least this many rows to have an "N ago" row
    if len(snapshots) < needed:
        return {}
    snap = snapshots[-(needed)]
    return {t["id"]: t["rank"] for t in snap.get("themes", []) if t.get("id") and t.get("rank")}


def _score_map_at(snapshots: list[dict], offset_sessions: int) -> dict[str, int | float]:
    """Return {theme_id: score} from `offset_sessions` rows before the last snapshot."""
    needed = offset_sessions + 1
    if len(snapshots) < needed:
        return {}
    snap = snapshots[-(needed)]
    return {t["id"]: t["score"] for t in snap.get("themes", []) if t.get("id") and t.get("score") is not None}


def _heat_tier(rank: int, n_themes: int, label: str,
               rank_delta_5d: int | None, score_delta_5d: float | None) -> str:
    """Classify this theme's current momentum state into one of five descriptive tiers.

    Tiers (mutually exclusive, tested in priority order):
      "broken"  — label is 'deteriorating'; structure breaking down.
      "cooling" — rank dropped ≥3 positions in 5 sessions, OR label is 'fading'.
                  Takes precedence over "hot" so a formerly-hot theme rolling over
                  reads as cooling rather than hot.
      "heating" — rank improved ≥3 positions in 5 sessions (positive rank_delta means
                  better rank, i.e. lower number) OR score rose ≥6 points, AND the
                  label is in the upward-phase set (emerging / dominant).
      "hot"     — rank is in the top quartile (rank ≤ max(1, n_themes // 4)), label is
                  dominant or emerging, and not cooling.
      "idle"    — everything else.

    All tiers are DESCRIPTIVE: they characterise the current rank/score trajectory
    and label state.  They carry no forward-return forecast.  rank_delta_5d and
    score_delta_5d are None when archive history is too short — treated as 0 (no
    signal either way) so new themes default to "idle" until history accrues.
    """
    if label == _BROKEN_LABEL:
        return "broken"

    rd5 = rank_delta_5d if rank_delta_5d is not None else 0
    sd5 = score_delta_5d if score_delta_5d is not None else 0.0

    # rank_delta_5d is defined as (rank_N_sessions_ago − rank_now):
    # positive → rank number DECREASED (i.e. moved up the board) → improvement.
    is_cooling_delta = rd5 <= _COOL_RANK_DELTA   # rank worsened ≥3 positions
    if is_cooling_delta or label == _COOL_LABEL:
        return "cooling"

    top_n = max(1, n_themes // 4)
    is_top_quartile = rank <= top_n
    is_upward_label = label in _HOT_LABELS

    is_heating = (rd5 >= _HEAT_RANK_DELTA or sd5 >= _HEAT_SCORE_DELTA) and is_upward_label
    if is_heating:
        return "heating"

    if is_top_quartile and is_upward_label:
        return "hot"

    return "idle"


# ----------------------------------------------- backtested heat-tier grading
def _heat_calibration() -> dict:
    """The phase-0 heat-tier kill-test verdict from scripts.calibrate_sector_pulse_heat
    (data/strategies/sector_pulse_heat.json — 27y SPDR-proxy, paired-vs-idle HAC t + BH).
    Display/grade only, additive — returns {} if absent so every tier keeps the honest
    'descriptive' framing. The tier logic (_heat_tier) is shared across regions, so the
    US-proxy verdict is cited cross-market, exactly as theme_scoring._signal_calibration
    cites baskets_calibration.json."""
    try:
        from lib import config
        p = config.data_dir() / "strategies" / "sector_pulse_heat.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        return d.get("verdict", {}) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — grading is enrichment, never fatal
        return {}


def _heat_strength(heat: str | None, cal: dict) -> dict | None:
    """Grade a theme's CURRENT heat tier by what the kill-test measured about it —
    mirrors theme_scoring._signal_strength. Phase-0 verdict (2026-07-03, 27y proxy):
    heating/hot showed NO forward-return edge vs same-day idle, and if anything slightly
    DEEPER forward drawdowns (the inverted tripwire) → 'descriptive'; cooling was NOT
    separately confirmed (the rank-drop leg dilutes the validated fading label) →
    'unconfirmed'; broken precedes measurably deeper drawdowns → 'backtested' risk.
    cal {} → None (payload keeps its existing honest framing); idle carries no claim."""
    if not cal or heat in (None, "idle"):
        return None
    v = cal.get(heat) or {}
    if not v or v.get("verdict") in (None, "baseline"):
        return None
    measured = v.get("verdict") == "measurable_edge"
    inverted = bool(v.get("inverted"))
    common = {"measured": bool(measured), "metric": v.get("claim"),
              "mean_pct": v.get("mean_pct"), "t_hac": v.get("t_hac"),
              "n_days": v.get("n_days")}
    if heat in ("cooling", "broken"):
        return {"grade": "backtested" if measured else "unconfirmed", "kind": "risk",
                **common,
                "en": ("Backtested risk read — on 27y of proxy history this tier precedes "
                       "measurably deeper 21-day drawdowns than same-day idle themes "
                       "(a risk timer, not a return forecast)." if measured else
                       "Risk read — not separately confirmed vs idle on the proxy; the "
                       "fading/deteriorating LABEL grades remain the backtested risk reads."),
                "zh": ("已回测的风险信号 — 在27年代理历史上，该档位领先于比同日闲置主题"
                       "更深的21日回撤（风险计时器，非收益预测）。" if measured else
                       "风险信号 — 代理上未相对闲置档单独验证；已回测的风险读数仍是"
                       "退潮/走弱标签本身。")}
    if heat in ("heating", "hot"):
        if measured:
            return {"grade": "backtested", "kind": "continuation", **common,
                    "en": ("Backtested — this tier preceded measurable forward strength "
                           "vs same-day idle themes on the 27y proxy."),
                    "zh": "已回测 — 在27年代理上该档位领先于相对闲置档的可测前向优势。"}
        caution_en = (" If anything, it drew slightly DEEPER 21-day drawdowns than idle "
                      "— a chase caution, never an entry signal.") if inverted else ""
        caution_zh = ("（若有差异，其21日回撤反而略深于闲置档 — 追高警示，绝非入场信号。）"
                      if inverted else "")
        return {"grade": "descriptive", "kind": "continuation", **common,
                "en": ("Descriptive — the phase-0 kill-test found no forward-return or "
                       "drawdown edge vs same-day idle themes on the 27y proxy."
                       + caution_en),
                "zh": ("描述性 — 阶段0检验在27年代理上未发现相对同日闲置主题的前向收益"
                       "或回撤优势。" + caution_zh)}
    return None


def _build_theme_row(th: dict, n_themes: int,
                     rank_1d: dict[str, int], rank_5d: dict[str, int], rank_20d: dict[str, int],
                     score_5d: dict[str, float], score_20d: dict[str, float],
                     heat_cal: dict | None = None) -> dict:
    """Assemble one pulse row from a full theme_intel theme entry + archive look-ups."""
    tid = th["id"]
    cur_rank = th.get("rank")
    cur_score = th.get("score")

    def _delta(cur, hist_map):
        """rank_delta = rank_N_ago − rank_now; positive means rank improved (number went down)."""
        if cur is None or tid not in hist_map:
            return None
        return hist_map[tid] - cur

    def _score_delta(cur, hist_map):
        if cur is None or tid not in hist_map:
            return None
        return cur - hist_map[tid]   # positive means score improved

    rank_delta_1d = _delta(cur_rank, rank_1d)
    rank_delta_5d = _delta(cur_rank, rank_5d)
    rank_delta_20d = _delta(cur_rank, rank_20d)
    score_delta_5d = _score_delta(cur_score, score_5d)
    score_delta_20d = _score_delta(cur_score, score_20d)

    label = th.get("label", "neutral")
    heat = _heat_tier(cur_rank or 9999, n_themes, label, rank_delta_5d, score_delta_5d)

    perf = th.get("perf") or {}
    breadth = th.get("breadth") or {}
    textures = th.get("textures") or {}
    mtf = th.get("mtf") or {}
    confluence = mtf.get("confluence") or {}
    ce_raw = textures.get("clean_entry") or {}

    return {
        "id": tid,
        "name": th.get("name", tid),
        "name_zh": th.get("name_zh", th.get("name", tid)),
        "category": th.get("category", "Other"),
        "label": label,
        "reco": th.get("reco", "hold"),
        "score": cur_score,
        "rank": cur_rank,
        # Archive-derived rank deltas (None = history accruing)
        "rank_delta_1d": rank_delta_1d,
        "rank_delta_5d": rank_delta_5d,
        "rank_delta_20d": rank_delta_20d,
        # Archive-derived score deltas (None = history accruing)
        "score_delta_5d": score_delta_5d,
        "score_delta_20d": score_delta_20d,
        # 5-day relative return (from the live theme_intel, not the archive)
        "rel_5d": (perf.get("5d") or {}).get("rel"),
        # Breadth
        "net_ad": th.get("net_ad"),
        "pct50": breadth.get("pct50"),
        # Clean-entry composite
        "clean_entry": {
            "flag": ce_raw.get("flag"),
            "quality": ce_raw.get("quality"),
        },
        # Multi-timeframe momentum
        "momentum_score": mtf.get("momentum_score"),
        "long_sign": confluence.get("long_sign"),
        # Descriptive heat tier + its kill-test grade (None = no calibration / no claim)
        "heat": heat,
        "heat_strength": _heat_strength(heat, heat_cal or {}),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_pulse(region: str = "us") -> dict | None:
    """Build the Sector Pulse payload for a region.

    Returns a dict with schema/as_of/region/n_themes, plus:
      "themes"  — list of pulse rows (one per theme, sorted by rank ascending)
      "heating" — list of theme ids currently in the 'heating' tier
      "cooling" — list of theme ids currently in the 'cooling' tier

    Returns None (never raises) on any failure or when data is unavailable.
    Rank/score deltas are None when the signal archive has fewer sessions than
    the requested look-back ("history accruing" semantics).
    """
    try:
        ti = _load_theme_intel(region)
        if not ti:
            return None
        themes_raw = ti.get("themes") or []
        if not themes_raw:
            return None

        as_of = ti.get("as_of") or datetime.now(timezone.utc).date().isoformat()
        n = len(themes_raw)

        # Load archive snapshots for rank/score delta computation.
        snapshots = _load_archive_snapshots(region)

        rank_1d = _rank_map_at(snapshots, 1)
        rank_5d = _rank_map_at(snapshots, 5)
        rank_20d = _rank_map_at(snapshots, 20)
        score_5d = _score_map_at(snapshots, 5)
        score_20d = _score_map_at(snapshots, 20)
        heat_cal = _heat_calibration()

        rows: list[dict] = []
        for th in themes_raw:
            try:
                row = _build_theme_row(th, n, rank_1d, rank_5d, rank_20d, score_5d, score_20d,
                                       heat_cal)
                rows.append(row)
            except Exception:  # noqa: BLE001
                log.debug("sector_pulse: skipping theme %s due to error", th.get("id"), exc_info=True)
                continue

        if not rows:
            return None

        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 9999))

        heating = [r["id"] for r in rows if r["heat"] == "heating"]
        cooling = [r["id"] for r in rows if r["heat"] == "cooling"]

        return {
            "schema": SCHEMA,
            "as_of": as_of,
            "region": region,
            "n_themes": n,
            "themes": rows,
            "heating": heating,
            "cooling": cooling,
            # Per-tier kill-test grades (backtested vs descriptive/unconfirmed); {} when
            # the calibration artifact is absent — consumers fall back to descriptive.
            "heat_grades": {t: (_heat_strength(t, heat_cal) or {}).get("grade")
                            for t in ("heating", "hot", "cooling", "broken")} if heat_cal else {},
        }
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse.build_pulse failed for region=%s", region, exc_info=True)
        return None


def _live_members(membership_data: dict, today_iso: str | None = None) -> dict[str, list[dict]]:
    """Return {basket_id: [member_dicts for live members as of today]}.

    Respects added/removed dates: a member is live if added <= today < removed
    (or removed is None/absent).  today_iso defaults to today's UTC date.
    """
    if today_iso is None:
        today_iso = datetime.now(timezone.utc).date().isoformat()
    baskets = membership_data.get("baskets") or {}
    if isinstance(baskets, list):
        baskets = {b["id"]: b for b in baskets if "id" in b}

    result: dict[str, list[dict]] = {}
    for bid, bdata in baskets.items():
        live = []
        for m in (bdata.get("members") or []):
            added = m.get("added") or "1900-01-01"
            removed = m.get("removed")
            if added <= today_iso and (removed is None or today_iso < removed):
                live.append(m)
        result[bid] = live
    return result


def _load_membership() -> dict:
    """Load data/baskets/membership.json.  Returns {} on failure."""
    try:
        from lib import config
        p = config.data_dir() / "baskets" / "membership.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        log.debug("sector_pulse: could not load membership.json", exc_info=True)
    return {}


def ticker_themes(region: str = "us") -> dict[str, list[str]]:
    """Map each live ticker → list of theme ids it currently belongs to.

    Uses data/baskets/membership.json and respects added/removed dates.
    Returns {} on any failure.  For non-US regions the membership file is the
    same (the full multi-region basket registry), filtered to the baskets that
    appear in that region's theme_intel.
    """
    try:
        membership = _load_membership()
        if not membership:
            return {}

        live_by_basket = _live_members(membership)

        # If not US, restrict to baskets that actually appear in that region's themes.
        if region != "us":
            ti = _load_theme_intel(region)
            if ti:
                known_ids = {t["id"] for t in (ti.get("themes") or [])}
                live_by_basket = {bid: mems for bid, mems in live_by_basket.items()
                                  if bid in known_ids}

        result: dict[str, list[str]] = {}
        for bid, members in live_by_basket.items():
            for m in members:
                ticker = m.get("ticker") or ""
                if not ticker:
                    continue
                result.setdefault(ticker, []).append(bid)
        return result
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse.ticker_themes failed for region=%s", region, exc_info=True)
        return {}


def for_ticker(ticker: str, region: str = "us") -> dict | None:
    """Return the strongest-pulse theme row for a ticker plus its full theme list.

    "Strongest" = lowest rank number (highest rank position) among the ticker's themes.
    Returns None when the ticker is not a live member of any theme, or on failure.

    The returned dict has all keys from a pulse row plus "theme_ids" listing every
    theme the ticker belongs to (not just the strongest one).
    """
    try:
        tk_map = ticker_themes(region)
        theme_ids = tk_map.get(ticker.upper()) or tk_map.get(ticker) or []
        if not theme_ids:
            return None

        pulse = build_pulse(region)
        if not pulse:
            return None

        # Find the highest-ranked theme (lowest rank number) for this ticker.
        theme_lookup = {r["id"]: r for r in pulse.get("themes") or []}
        candidates = [theme_lookup[tid] for tid in theme_ids if tid in theme_lookup]
        if not candidates:
            return None

        best = min(candidates, key=lambda r: (r["rank"] is None, r["rank"] or 9999))
        return {**best, "theme_ids": theme_ids}
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse.for_ticker failed ticker=%s region=%s", ticker, region,
                    exc_info=True)
        return None


def merge_pulse_into_theme_intel(ti: dict, region: str) -> None:
    """Merge per-theme velocity/heat keys from the pulse into a freshly-computed theme_intel dict.

    Adds the following keys to each theme row IN PLACE (additive — existing keys are never
    modified, missing keys default to None so JS can degrade safely on pre-W4 payloads):

        pulse_heat          — str: "heating" | "hot" | "cooling" | "broken" | "idle" | None
        pulse_heat_grade    — str | None: "backtested" | "descriptive" | "unconfirmed"
                              (the kill-test grade for the tier; None = no calibration
                              artifact or the tier carries no claim, e.g. idle)
        pulse_rank_delta_1d — int | None   (positive = rank improved, i.e. number went down)
        pulse_rank_delta_5d — int | None
        pulse_rank_delta_20d — int | None
        pulse_score_delta_5d — float | None

    Keys use a `pulse_` prefix to avoid shadowing the existing `rank_5d` / `delta_5d` keys
    that engine.theme_scoring already writes on each theme row.

    Additive and never-fatal: a failure logs a warning and leaves theme_intel untouched.
    """
    try:
        themes_raw = ti.get("themes") or []
        if not themes_raw:
            return

        n = len(themes_raw)
        snapshots = _load_archive_snapshots(region)
        rank_1d = _rank_map_at(snapshots, 1)
        rank_5d = _rank_map_at(snapshots, 5)
        rank_20d = _rank_map_at(snapshots, 20)
        score_5d = _score_map_at(snapshots, 5)
        score_20d = _score_map_at(snapshots, 20)
        heat_cal = _heat_calibration()

        for th in themes_raw:
            try:
                tid = th.get("id")
                cur_rank = th.get("rank")
                cur_score = th.get("score")
                label = th.get("label", "neutral")

                def _rd(cur, hist):
                    return (hist[tid] - cur) if (cur is not None and tid in hist) else None

                def _sd(cur, hist):
                    return (cur - hist[tid]) if (cur is not None and tid in hist) else None

                rd1 = _rd(cur_rank, rank_1d)
                rd5 = _rd(cur_rank, rank_5d)
                rd20 = _rd(cur_rank, rank_20d)
                sd5 = _sd(cur_score, score_5d)
                heat = _heat_tier(cur_rank or 9999, n, label, rd5, sd5)

                hs = _heat_strength(heat, heat_cal)

                # Additive: set only if not already present (never overwrite existing data)
                th.setdefault("pulse_heat", heat)
                th.setdefault("pulse_heat_grade", (hs or {}).get("grade"))
                th.setdefault("pulse_rank_delta_1d", rd1)
                th.setdefault("pulse_rank_delta_5d", rd5)
                th.setdefault("pulse_rank_delta_20d", rd20)
                th.setdefault("pulse_score_delta_5d", sd5)
            except Exception:  # noqa: BLE001
                log.debug("merge_pulse_into_theme_intel: skipping theme %s", th.get("id"),
                          exc_info=True)
    except Exception:  # noqa: BLE001
        log.warning("merge_pulse_into_theme_intel failed for region=%s", region, exc_info=True)


def write_pulse(ti: dict, region: str, out_dir: Any) -> None:
    """Write the Sector Pulse JSON for a region to out_dir.

    File names:
      US      → sector_pulse.json
      other   → sector_pulse_<region>.json

    Always writes "schema" and "as_of".  Additive — callers should wrap in
    try/except so a failure here can never break the containing build step.
    """
    try:
        from lib import config as _cfg
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        fname = "sector_pulse.json" if region == "us" else f"sector_pulse_{region}.json"

        # Build the pulse from the freshly-computed theme_intel dict.
        # We monkeypatch _load_theme_intel by temporarily injecting ti directly
        # to avoid redundant file I/O inside write_pulse.
        as_of = ti.get("as_of") or datetime.now(timezone.utc).date().isoformat()
        themes_raw = ti.get("themes") or []
        n = len(themes_raw)

        snapshots = _load_archive_snapshots(region)
        rank_1d = _rank_map_at(snapshots, 1)
        rank_5d = _rank_map_at(snapshots, 5)
        rank_20d = _rank_map_at(snapshots, 20)
        score_5d = _score_map_at(snapshots, 5)
        score_20d = _score_map_at(snapshots, 20)
        heat_cal = _heat_calibration()

        rows: list[dict] = []
        for th in themes_raw:
            try:
                rows.append(_build_theme_row(th, n, rank_1d, rank_5d, rank_20d,
                                             score_5d, score_20d, heat_cal))
            except Exception:  # noqa: BLE001
                log.debug("write_pulse: skipping theme %s", th.get("id"), exc_info=True)

        if not rows:
            log.warning("write_pulse: no rows built for region=%s — file not written", region)
            return

        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 9999))
        heating = [r["id"] for r in rows if r["heat"] == "heating"]
        cooling = [r["id"] for r in rows if r["heat"] == "cooling"]

        payload = {
            "schema": SCHEMA,
            "as_of": as_of,
            "region": region,
            "n_themes": n,
            "themes": rows,
            "heating": heating,
            "cooling": cooling,
            "heat_grades": {t: (_heat_strength(t, heat_cal) or {}).get("grade")
                            for t in ("heating", "hot", "cooling", "broken")} if heat_cal else {},
        }
        (p / fname).write_text(json.dumps(payload, separators=(",", ":"), default=str))
        log.info("sector_pulse: wrote %s (%d themes)", fname, len(rows))
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse.write_pulse failed for region=%s", region, exc_info=True)


def write_score_snapshot(ti: dict, region: str) -> None:
    """Slim per-theme score snapshot → data/baskets_<region>/latest.json (US uses
    data/baskets/latest.json, written by build_baskets' own writer — kept separate for
    archive continuity). scripts.archive_signals snapshots these daily into the
    'baskets_<region>' streams, which is where THIS module's rank/score velocity comes
    from. Without the snapshot the regional streams never accrue and every regional
    rank_delta_* stays None forever. Same slim shape as the US writer. Additive —
    callers wrap in try/except; a failure can never break a build."""
    try:
        from lib import config as _cfg
        slim = {"as_of": ti.get("as_of"), "themes": []}
        for t in ti.get("themes") or []:
            tx = t.get("textures") or {}
            slim["themes"].append({
                "id": t.get("id"), "name": t.get("name"), "score": t.get("score"),
                "label": t.get("label"), "reco": t.get("reco"), "rank": t.get("rank"),
                "net_ad": t.get("net_ad"), "components": t.get("components"),
                "bull_days": (tx.get("bull_age") or {}).get("days"),
                "overbought": (tx.get("overbought") or {}).get("value"),
                "clean_entry": (tx.get("clean_entry") or {}).get("flag"),
                "rollover": (tx.get("rollover_risk") or {}).get("risk"),
            })
        sub = "baskets" if region == "us" else f"baskets_{region}"
        p = _cfg.data_dir() / sub / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(slim, separators=(",", ":"), default=str))
        log.info("sector_pulse: wrote %s score snapshot (%d themes)", sub, len(slim["themes"]))
    except Exception:  # noqa: BLE001
        log.warning("sector_pulse.write_score_snapshot failed for region=%s", region, exc_info=True)
