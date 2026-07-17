"""Pick Lab nightly runner (spec §5, PL-R7/R7b/R10).

Steps
-----
(a) Load latest producer-core snapshot via engine.pick_lab.snapshot.latest_snapshot();
    if none, log honest no-op and return 0.
(b) ENRICHMENT JOIN (PL-R7b): fill sector_phase/sector_stage/sector_rs_mom20/sector_bucket
    + calm/stress/liquidity_overlay/spy_close from that same night's committed artifacts
    (data/regime/latest.json for regime scalars; playbook.stages from the same file for
    per-sector phase/stage). Persist the enriched frame via write_snapshot.
(c) Run all 23 books via candidates.run_book; apply refire lockout from ledger;
    append fires (entry vs lh files per horizon_role).
(d) Grading pass: load closes from the broad-universe close caches; grade matured fires;
    append grades. Degrades gracefully if price store unavailable.
(e) Compute scoreboards via book.py; write site/labdata/pick_lab.json +
    pick_lab_longhold.json.
(f) Render the page via engine.pick_lab.render.

Always returns 0 — a failure must never break the nightly render (PL-R10).
Authority: display_only throughout.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from lib import config

log = logging.getLogger("build_pick_lab")

# ------------------------------------------------------------------ constants ---

# Sector ETF → GICS sector name (inverse of grade._GICS_ETF; same map)
_ETF_TO_SECTOR: dict[str, str] = {
    "XLE":  "Energy",
    "XLK":  "Information Technology",
    "XLF":  "Financials",
    "XLV":  "Health Care",
    "XLI":  "Industrials",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication Services",
}

# Reverse: sector name → ETF ticker
_SECTOR_TO_ETF: dict[str, str] = {v: k for k, v in _ETF_TO_SECTOR.items()}

# Broad-universe close cache directories (same tiers as build_impulse.py)
_CLOSE_CACHE_TIERS = ("breadth", "midcap_breadth", "smallcap_breadth")

# GICS sector ETF tickers to include in the close panel for grading
_SECTOR_ETF_TICKERS = list(_ETF_TO_SECTOR.keys())

# Labdata output directory
_LABDATA_DIR = Path("site") / "labdata"

# Recent fires to show per book in the UI (last N fires with grades attached)
_RECENT_FIRES_PER_BOOK = 30


# ------------------------------------------------------------------ helpers ---


def _load_regime() -> dict:
    """Load data/regime/latest.json; return {} on failure."""
    p = config.data_dir() / "regime" / "latest.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("pick_lab: regime/latest.json unreadable (%s)", exc)
        return {}


def _load_close_panel() -> Optional[pd.DataFrame]:
    """Load the broad-universe close panel from per-tier _closes_cache.parquet files.

    Returns a DataFrame[date x ticker] or None if no caches found.
    """
    frame: Optional[pd.DataFrame] = None
    for tier in _CLOSE_CACHE_TIERS:
        p = config.data_dir() / tier / "_closes_cache.parquet"
        if not p.exists():
            continue
        try:
            d = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("pick_lab: close cache %s unreadable (%s) — skipped", p, exc)
            continue
        d = d.loc[:, ~d.columns.duplicated()]
        if frame is None:
            frame = d
        else:
            new = [c for c in d.columns if c not in frame.columns]
            frame = frame.join(d[new], how="outer")
    if frame is None:
        return None
    return frame.sort_index()


def _build_sector_phase_map(regime: dict) -> dict[str, dict]:
    """Return {sector_name: {phase, stage, rs_mom20}} from playbook.stages.

    playbook.stages is a list of sector ETF records from data/regime/latest.json.
    Each record carries 'ticker' (ETF), 'stage' (leading/weakening/improving/lagging),
    'mom_20d_pct'. 'phase' is not stored per-ETF; the whole-macro cycle phase
    (Trough/Recovery/Expansion/Peak/Downturn) comes from sector_cycles elsewhere.
    For this enrichment we map:
      - sector_stage <- playbook.stages[ticker].stage
      - sector_rs_mom20 <- playbook.stages[ticker].mom_20d_pct
      - sector_phase <- null (sector_cycle Trough/Recovery data not available
                         in a committed artifact tonight; leave null per PL-R7b
                         honesty rule — books 3/10 that depend on it fire on
                         their fallback conditions only)
    """
    playbook = regime.get("playbook") or {}
    stages = playbook.get("stages") or []
    result: dict[str, dict] = {}
    for rec in stages:
        etf = rec.get("ticker")
        sector = _ETF_TO_SECTOR.get(etf)
        if not sector:
            continue
        result[sector] = {
            "sector_stage": rec.get("stage"),
            "sector_rs_mom20": rec.get("mom_20d_pct"),
            "sector_phase": None,  # cycle-phase not in tonight's committed artifact
        }
    return result


def _build_action_bucket_map(regime: dict) -> dict[str, str]:
    """Derive sector_bucket from regime playbook or sector_rs where available.

    This is a best-effort proxy: the authoritative action-board bucket is
    computed inside build_site.py and not persisted to a committed JSON artifact.
    We approximate it from playbook.stages:
      - stage='leading' → 'on_the_run' (leading sector, actively running)
      - stage='weakening' → 'take_profits' (momentum fading)
      - stage='improving' → 'buy_soon' (mapped to null, not a defined bucket)
      - stage='lagging' → 'hold' (mapped to null for bucket purposes)

    The spec (PL-R7b) says "if only embedded in HTML, derive on_the_run/take_profits
    sector sets from the same engine functions IF cheap, else leave sector_bucket null".
    We use the cheap playbook.stages proxy.

    Returns {sector_name: bucket} where bucket ∈ {'on_the_run', 'take_profits'} or None.
    """
    playbook = regime.get("playbook") or {}
    stages = playbook.get("stages") or []
    result: dict[str, str] = {}
    _STAGE_TO_BUCKET = {
        "leading": "on_the_run",
        "weakening": "take_profits",
    }
    for rec in stages:
        etf = rec.get("ticker")
        sector = _ETF_TO_SECTOR.get(etf)
        if not sector:
            continue
        stage = rec.get("stage")
        bucket = _STAGE_TO_BUCKET.get(stage)  # None for improving/lagging
        if bucket:
            result[sector] = bucket
    return result


def _enrich_snapshot(snap: pd.DataFrame, regime: dict) -> pd.DataFrame:
    """Fill sector_phase/stage/bucket and regime scalars from tonight's committed artifacts.

    Per PL-R7b: enrichment join is additive; a join failure leaves the column null.
    The enriched frame is persisted as the snapshot of record.
    """
    df = snap.copy()

    # ── Regime scalars (repeated on every row) ──────────────────────────────
    vol_regime = regime.get("vol_regime") or {}
    risk_state = regime.get("risk_state") or {}

    # calm: world_state.vol.calm / vol_regime.calm_regime flag
    calm: Optional[float] = (
        vol_regime.get("calm")
        or (1.0 if vol_regime.get("state") == "calm" else None)
        or risk_state.get("calm")
    )
    # stress: complement scalar
    stress_flag = vol_regime.get("stress") or risk_state.get("stress")
    stress: Optional[float] = (
        float(stress_flag) if isinstance(stress_flag, (int, float)) else
        (1.0 if stress_flag else None)
    )
    liquidity_overlay: Optional[str] = regime.get("liquidity_overlay")

    # SPY close from sector_rs (ranked list of ETFs in regime)
    spy_close: Optional[float] = None
    sector_rs = regime.get("sector_rs") or []
    # sector_rs does not store SPY directly; use calm context instead
    # The canonical SPY close isn't in latest.json; the producer fills it from
    # _ext_closes at snapshot time. If it's null in the snapshot, leave null.

    # Only fill columns that are still null (producer set them null explicitly)
    _REGIME_MAP = {
        "calm": calm,
        "stress": stress,
        "liquidity_overlay": liquidity_overlay,
    }
    for col, val in _REGIME_MAP.items():
        if col in df.columns and val is not None:
            null_mask = df[col].isna()
            if null_mask.any():
                df.loc[null_mask, col] = val
        elif col not in df.columns and val is not None:
            df[col] = val

    # ── Per-sector enrichment ────────────────────────────────────────────────
    sector_phase_map = _build_sector_phase_map(regime)
    bucket_map = _build_action_bucket_map(regime)

    if "sector" in df.columns and not df["sector"].isna().all():
        # sector_stage
        if "sector_stage" in df.columns:
            null_mask = df["sector_stage"].isna()
            if null_mask.any():
                df.loc[null_mask, "sector_stage"] = df.loc[null_mask, "sector"].map(
                    lambda s: (sector_phase_map.get(s) or {}).get("sector_stage")
                )
        # sector_rs_mom20
        if "sector_rs_mom20" in df.columns:
            null_mask = df["sector_rs_mom20"].isna()
            if null_mask.any():
                df.loc[null_mask, "sector_rs_mom20"] = df.loc[null_mask, "sector"].map(
                    lambda s: (sector_phase_map.get(s) or {}).get("sector_rs_mom20")
                )
        # sector_phase — honest null per analysis above
        # sector_bucket
        if "sector_bucket" in df.columns:
            null_mask = df["sector_bucket"].isna()
            if null_mask.any():
                df.loc[null_mask, "sector_bucket"] = df.loc[null_mask, "sector"].map(
                    bucket_map.get
                )

    return df


# ------------------------------------------------------------------ fire pass ---


def _fire_all_books(
    snap: pd.DataFrame,
    asof: str,
    fires_entry: list[dict],
    fires_lh: list[dict],
    trading_dates: pd.DatetimeIndex,
) -> tuple[list[dict], list[dict]]:
    """Run all 23 books against the snapshot; apply refire lockout.

    Returns (new_entry_fires, new_lh_fires).
    """
    from engine.pick_lab.candidates import run_book
    from engine.pick_lab.ledger import is_open
    from engine.pick_lab.registry import REGISTRY

    new_entry: list[dict] = []
    new_lh: list[dict] = []

    snap_with_asof = snap.copy()
    snap_with_asof.attrs["asof"] = asof

    for book in REGISTRY:
        engine_id = book["engine_id"]
        horizon_role = book["horizon_role"]
        is_lh = horizon_role == "hold_thesis"
        existing_fires = fires_lh if is_lh else fires_entry
        lockout = book["refire_lockout_sessions"]

        try:
            picks = run_book(book, snap_with_asof)
        except Exception as exc:  # noqa: BLE001
            log.error("pick_lab: run_book %s error (%s)", engine_id, exc)
            picks = []

        for pick in picks:
            ticker = pick.get("ticker")
            if not ticker:
                continue

            # Refire lockout check (PL-R4)
            if is_open(engine_id, ticker, trading_dates, existing_fires, lockout):
                log.debug(
                    "pick_lab: %s/%s lockout — skip fire", engine_id, ticker
                )
                continue

            fire_row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": asof,
                "exec_date": None,   # filled by grade.py next-session logic
                "rank": pick.get("rank"),
                "close_at_fire": pick.get("close"),
                "sector": pick.get("sector"),
                "why": pick.get("why") or [],
                "features": pick.get("features") or {},
                "liq_unknown": bool(pick.get("liq_unknown")),
                # Regime stamp AT fire_date
                "regime_calm": float(snap_with_asof["calm"].iloc[0])
                    if "calm" in snap_with_asof.columns and not snap_with_asof["calm"].isna().all()
                    else None,
                "regime_stress": float(snap_with_asof["stress"].iloc[0])
                    if "stress" in snap_with_asof.columns and not snap_with_asof["stress"].isna().all()
                    else None,
                "config_hash": book["config_hash"],
                "authority": "display_only",
            }

            if is_lh:
                new_lh.append(fire_row)
                fires_lh.append(fire_row)  # so later books see this fire for lockout
            else:
                new_entry.append(fire_row)
                fires_entry.append(fire_row)

    log.info(
        "pick_lab: fires this run — %d entry, %d LH",
        len(new_entry), len(new_lh),
    )
    return new_entry, new_lh


# ------------------------------------------------------------------ grade pass ---


def _grade_pass(
    close_panel: Optional[pd.DataFrame],
    fires_entry: list[dict],
    grades_entry: list[dict],
    fires_lh: list[dict],
    grades_lh: list[dict],
) -> tuple[int, int]:
    """Run the maturation pass; return (new_entry_grades, new_lh_grades) counts."""
    if close_panel is None or close_panel.empty:
        log.info(
            "pick_lab: price store unavailable — grade pass skipped (honest counter)"
        )
        return 0, 0

    from engine.pick_lab.grade import grade_fires
    from engine.pick_lab.ledger import append_grades

    spy_closes = (
        close_panel["SPY"].dropna()
        if "SPY" in close_panel.columns
        else pd.Series(dtype=float)
    )

    # Build already-graded key set (keep-first dedup prevents re-grading)
    from engine.pick_lab.ledger import GRADE_KEY
    already_entry: set[tuple] = {
        tuple(g.get(f) for f in GRADE_KEY) for g in grades_entry
    }
    already_lh: set[tuple] = {
        tuple(g.get(f) for f in GRADE_KEY) for g in grades_lh
    }

    # Entry grades
    n_new_entry = 0
    try:
        new_grades, n_ung = grade_fires(
            fires_entry,
            close_panel,
            spy_closes,
            hold_thesis=False,
            already_graded=already_entry,
        )
        if new_grades:
            n_new_entry = append_grades(new_grades, hold_thesis=False)
        if n_ung:
            log.info("pick_lab: %d entry fires ungradeable (ticker absent)", n_ung)
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab: entry grade pass error (%s)", exc)

    # LH grades
    n_new_lh = 0
    try:
        new_lh_grades, n_ung_lh = grade_fires(
            fires_lh,
            close_panel,
            spy_closes,
            hold_thesis=True,
            already_graded=already_lh,
        )
        if new_lh_grades:
            n_new_lh = append_grades(new_lh_grades, hold_thesis=True)
        if n_ung_lh:
            log.info("pick_lab: %d LH fires ungradeable (ticker absent)", n_ung_lh)
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab: LH grade pass error (%s)", exc)

    log.info(
        "pick_lab: new grades written — %d entry, %d LH", n_new_entry, n_new_lh
    )
    return n_new_entry, n_new_lh


# ------------------------------------------------------------------ site JSON ---


def _build_picks_today(fires_entry: list[dict], asof: str) -> dict[str, list[dict]]:
    """Return {engine_id: [pick dicts]} for today's fires."""
    result: dict[str, list[dict]] = {}
    for f in fires_entry:
        if f.get("fire_date") != asof:
            continue
        eid = f.get("engine_id", "")
        result.setdefault(eid, []).append(f)
    return result


def _build_grade_map(grades: list[dict], engine_id: str) -> dict[tuple, dict]:
    """Build {(ticker, fire_date): grade_dict} for engine_id, preferring h=21/126."""
    grade_map: dict[tuple, dict] = {}
    for g in grades:
        if g.get("engine_id") != engine_id:
            continue
        k = (g.get("ticker"), g.get("fire_date"))
        h = g.get("horizon")
        if k not in grade_map or h in (21, 126):
            grade_map[k] = g
    return grade_map


def _attach_grade(fire_row: dict, grade_map: dict[tuple, dict]) -> dict:
    """Return a copy of fire_row with ret21_excess/ret21_abs/matured attached."""
    k = (fire_row.get("ticker"), fire_row.get("fire_date"))
    g = grade_map.get(k)
    row = dict(fire_row)
    if g:
        row["ret21_excess"] = g.get("ret_excess_spy")
        row["ret21_abs"] = g.get("ret_abs")
        row["matured"] = bool(g.get("matured"))
    else:
        row["ret21_excess"] = None
        row["ret21_abs"] = None
        row["matured"] = False
    return row


def _build_recent_fires_with_grades(
    fires: list[dict],
    grades: list[dict],
    engine_id: str,
    n: int = _RECENT_FIRES_PER_BOOK,
) -> list[dict]:
    """Return the N most recent fires for engine_id, with h=21 grade attached if matured."""
    my_fires = sorted(
        [f for f in fires if f.get("engine_id") == engine_id],
        key=lambda x: x.get("fire_date", ""),
        reverse=True,
    )[:n]

    grade_map = _build_grade_map(grades, engine_id)

    result = []
    for f in my_fires:
        result.append(_attach_grade(f, grade_map))
    return result


def _build_fires_export(
    fires_entry: list[dict],
    fires_lh: list[dict],
    grades_entry: list[dict],
    grades_lh: list[dict],
    asof: str,
) -> dict:
    """Build the dict written to site/labdata/pick_lab_fires.json.

    Groups ALL fires (no cap) by engine_id from both entry and LH ledgers.
    Attaches grade columns using the same grade-map logic as _build_recent_fires_with_grades.
    Keeps only the compact field set (no 'why', 'features', 'config_hash', etc.)
    to bound payload size.
    """
    # Combined fires and grades across both ledgers
    all_fires = fires_entry + fires_lh
    all_grades = grades_entry + grades_lh

    # Collect all engine_ids present
    engine_ids: list[str] = []
    seen: set[str] = set()
    for f in all_fires:
        eid = f.get("engine_id", "")
        if eid and eid not in seen:
            engine_ids.append(eid)
            seen.add(eid)

    fires_by_book: dict[str, list[dict]] = {}
    for eid in engine_ids:
        grade_map = _build_grade_map(all_grades, eid)
        my_fires = sorted(
            [f for f in all_fires if f.get("engine_id") == eid],
            key=lambda x: (x.get("fire_date", ""), x.get("ticker", "")),
            reverse=True,
        )
        rows = []
        for f in my_fires:
            enriched = _attach_grade(f, grade_map)
            rows.append({
                "ticker": enriched.get("ticker"),
                "fire_date": enriched.get("fire_date"),
                "sector": enriched.get("sector"),
                "rank": enriched.get("rank"),
                "close_at_fire": enriched.get("close_at_fire"),
                "ret21_excess": enriched.get("ret21_excess"),
                "ret21_abs": enriched.get("ret21_abs"),
                "matured": enriched.get("matured", False),
            })
        fires_by_book[eid] = rows

    return {
        "as_of": asof,
        "fires_by_book": fires_by_book,
        "authority": "display_only",
    }


def _build_entry_lanes(snap: pd.DataFrame, fires_entry: list[dict], asof: str) -> dict:
    """Build on_the_run_stocks and take_profits_stocks context lanes from the snapshot."""
    on_the_run: list[dict] = []
    take_profits: list[dict] = []

    if snap.empty or "sector_bucket" not in snap.columns:
        return {"on_the_run_stocks": [], "take_profits_stocks": []}

    today_fires_tickers = {
        f.get("ticker")
        for f in fires_entry
        if f.get("fire_date") == asof
    }

    for ticker in snap.index:
        row = snap.loc[ticker]
        bucket = row.get("sector_bucket") if hasattr(row, "get") else None
        if pd.isna(bucket) if not isinstance(bucket, str) else not bucket:
            continue
        pick = {
            "ticker": str(ticker),
            "sector": row.get("sector") if hasattr(row, "get") else None,
            "close": row.get("close") if hasattr(row, "get") else None,
            "sector_bucket": bucket,
            "composite_z": row.get("composite_z") if hasattr(row, "get") else None,
            "rsi14": row.get("rsi14") if hasattr(row, "get") else None,
            "authority": "display_only",
        }
        if bucket == "on_the_run":
            on_the_run.append(pick)
        elif bucket == "take_profits":
            take_profits.append(pick)

    # Sort and cap
    on_the_run.sort(key=lambda x: -(x.get("composite_z") or 0))
    take_profits.sort(key=lambda x: -(x.get("rsi14") or 0))

    return {
        "on_the_run_stocks": on_the_run[:30],
        "take_profits_stocks": take_profits[:30],
    }


def _build_entry_site_payload(
    snap: pd.DataFrame,
    asof: str,
    scoreboards_entry: list[dict],
    fires_entry: list[dict],
    grades_entry: list[dict],
    regime: dict,
) -> dict:
    """Build the dict written to site/labdata/pick_lab.json."""
    from engine.pick_lab.registry import REGISTRY

    # ── picks_today per book ──────────────────────────────────────────────────
    picks_today_by_book = _build_picks_today(fires_entry, asof)

    # ── books dict: picks_today + recent_fires per entry book ────────────────
    books: dict = {}
    for book in REGISTRY:
        if book["horizon_role"] != "entry":
            continue
        eid = book["engine_id"]
        books[eid] = {
            "engine_id": eid,
            "name_en": book["name_en"],
            "name_zh": book["name_zh"],
            "family": book["family"],
            "picks_today": picks_today_by_book.get(eid) or [],
            "recent_fires": _build_recent_fires_with_grades(
                fires_entry, grades_entry, eid
            ),
        }

    # ── context lanes ─────────────────────────────────────────────────────────
    lanes = _build_entry_lanes(snap, fires_entry, asof)

    # ── regime scalar summary ─────────────────────────────────────────────────
    # The template's regime chips read calm/stress/liquidity — every key must
    # exist even when its value is null (a missing key raises UndefinedError
    # inside `{% if regime.stress is not none %}` and kills the page render).
    vol_regime = regime.get("vol_regime") or {}
    risk_state = regime.get("risk_state") or {}
    stress = vol_regime.get("stress")
    if stress is None:
        stress = risk_state.get("stress")
    regime_summary = {
        "quad": regime.get("quad"),
        "quad_name": regime.get("quad_name"),
        "liquidity_overlay": regime.get("liquidity_overlay"),
        "vol_state": vol_regime.get("state"),
        "calm": vol_regime.get("calm"),
        "stress": stress,
        "liquidity": regime.get("liquidity_overlay"),
    }

    # ── scoreboard (entry only) with name/family denormalized ────────────────
    book_meta = {b["engine_id"]: b for b in REGISTRY}
    scoreboard_out = []
    for sb in scoreboards_entry:
        eid = sb.get("engine_id", "")
        bm = book_meta.get(eid, {})
        row = dict(sb)
        row["name_en"] = bm.get("name_en", eid)
        row["name_zh"] = bm.get("name_zh", eid)
        row["family"] = bm.get("family", "")
        row["horizon_role"] = bm.get("horizon_role", "entry")
        row["ruler"] = bm.get("ruler", "")
        # Remap book.py scoreboard keys → schema expected by render.py
        row["wr21_abs"] = sb.get("h21_wr_abs")
        row["wr21_excess"] = sb.get("h21_wr_exc")
        row["med_excess21"] = sb.get("h21_med_exc")
        row["mfe_med"] = sb.get("h21_med_mfe")
        row["mae_med"] = sb.get("h21_med_abs_mae")
        row["asym"] = sb.get("h21_asym")
        row["nav_excess_cum"] = (sb.get("nav_final") or 1.0) - 1.0 if sb.get("nav_final") else None
        row["max_dd"] = sb.get("nav_max_drawdown")
        row["vs_random_lift"] = sb.get("lift_vs_ctrl")
        row["vs_universe_lift"] = sb.get("lift_vs_universe_base")
        row["n_dates"] = sb.get("n_distinct_fire_dates")
        scoreboard_out.append(row)

    return {
        "as_of": asof,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "scoreboard": scoreboard_out,
        "books": books,
        "lanes": lanes,
        "regime": regime_summary,
        "method_note": (
            "Display-only forward-evidence lab. "
            "All books ACCRUING until n≥25 fires / ≥3 months / ≥6 distinct fire dates. "
            "plab_random_ctrl = yardstick (buy-anytime base rate). "
            "Authority: display_only. Never gates or scores anything."
        ),
        "authority": "display_only",
    }


def _build_longhold_site_payload(
    asof: str,
    scoreboards_lh: list[dict],
    fires_lh: list[dict],
    grades_lh: list[dict],
) -> dict:
    """Build the dict written to site/labdata/pick_lab_longhold.json (PL-R6)."""
    from engine.pick_lab.registry import REGISTRY

    lh_books = [b for b in REGISTRY if b["horizon_role"] == "hold_thesis"]

    # picks_today per LH book
    picks_today_by_book = _build_picks_today(fires_lh, asof)

    books: dict = {}
    for book in lh_books:
        eid = book["engine_id"]
        books[eid] = {
            "engine_id": eid,
            "name_en": book["name_en"],
            "name_zh": book["name_zh"],
            "family": book["family"],
            "picks_today": picks_today_by_book.get(eid) or [],
            "recent_fires": _build_recent_fires_with_grades(
                fires_lh, grades_lh, eid, n=20
            ),
        }

    # First maturation ETA from scoreboards (min across LH books)
    eta_dates = [
        sb.get("first_maturation_eta")
        for sb in scoreboards_lh
        if sb.get("first_maturation_eta")
    ]
    first_eta = min(eta_dates) if eta_dates else "~2027-01"

    return {
        "as_of": asof,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "first_maturation_eta": first_eta,
        "scoreboards": scoreboards_lh,
        "books": books,
        # PL-R6 firewall note — never consumed by entry surfaces
        "authority": "display_only",
        "horizon_role": "hold_thesis",
        "firewall_note": (
            "LH grids are FIREWALLED from entry surfaces (PL-R6). "
            "Ruler: 126/252d sector-relative + SPY-excess, DESCRIPTIVE only. "
            "First maturation ETA: ~2027-01."
        ),
    }


def _write_site_artifact(path: Path, payload: dict) -> None:
    """Atomically write a JSON site artifact."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        import os
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            import os as _os
            _os.unlink(tmp)
        except OSError:
            pass
        raise
    log.info("pick_lab: wrote %s (%.0f KB)", path, path.stat().st_size / 1024)


# ------------------------------------------------------------------ main -------


def _build() -> None:
    """Core build logic (all exceptions propagate to main's try/except)."""
    from engine.pick_lab import snapshot as snap_mod
    from engine.pick_lab.ledger import (
        append_fires,
        load_fires,
        load_grades,
    )
    from engine.pick_lab.book import all_scoreboards
    from engine.pick_lab.registry import REGISTRY

    # (a) Load latest snapshot
    snap, asof = snap_mod.latest_snapshot()
    if snap is None or asof is None:
        log.info(
            "pick_lab: no snapshot found in %s — honest no-op (first run after "
            "build_stock_library produces one)",
            snap_mod.SNAPSHOT_DIR,
        )
        return

    log.info("pick_lab: snapshot asof=%s, %d rows", asof, len(snap))

    # (b) Enrichment join (PL-R7b)
    regime = _load_regime()
    snap_enriched = _enrich_snapshot(snap, regime)

    # Persist enriched frame as snapshot of record (PL-R7).
    # mode='upsert' replaces the core rows already written by build_stock_library so
    # the persisted partition carries sector_stage/sector_bucket/calm/stress/etc.
    # (keep_first would silently no-op because the core producer already wrote those
    # (asof, ticker) pairs, leaving the enrichment columns as None in the store.)
    try:
        snap_mod.write_snapshot(snap_enriched.reset_index(), asof, mode="upsert")
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "pick_lab: enriched snapshot persist failed (%s) — proceeding with "
            "in-memory enriched frame",
            exc,
        )

    # Build a trading-date index for lockout calculations.
    # Primary source: the close panel (most accurate, includes market anomalies).
    # Fallback: NYSE calendar — keeps PL-R4 no-refire-while-open active even when
    # the price store is unavailable (avoids silent lockout bypass, Finding 10).
    close_panel: Optional[pd.DataFrame] = None
    trading_dates: pd.DatetimeIndex = pd.DatetimeIndex([])
    try:
        close_panel = _load_close_panel()
        if close_panel is not None and not close_panel.empty:
            trading_dates = pd.DatetimeIndex(
                close_panel.index
            ).sort_values()
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab: close panel load error (%s)", exc)
        close_panel = None

    if len(trading_dates) == 0:
        # Fallback: generate ~6 months of NYSE calendar dates so lockout still fires.
        try:
            from lib.nyse_calendar import is_session
            import datetime as _dt
            _end = _dt.date.fromisoformat(asof) if asof else _dt.date.today()
            _start = _end - _dt.timedelta(days=180)
            _cal_dates = [
                _start + _dt.timedelta(days=d)
                for d in range((_end - _start).days + 1)
                if is_session(_start + _dt.timedelta(days=d))
            ]
            if _cal_dates:
                trading_dates = pd.DatetimeIndex(
                    pd.Timestamp(d) for d in _cal_dates
                )
                log.info(
                    "pick_lab: close panel unavailable; using NYSE calendar for "
                    "lockout (%d sessions)", len(trading_dates)
                )
        except Exception as exc2:  # noqa: BLE001
            log.warning("pick_lab: NYSE calendar fallback also failed (%s)", exc2)

    # (c) Fire pass
    fires_entry = load_fires(hold_thesis=False)
    fires_lh = load_fires(hold_thesis=True)

    new_entry, new_lh = _fire_all_books(
        snap_enriched, asof, fires_entry, fires_lh, trading_dates
    )

    written_entry = append_fires(new_entry, hold_thesis=False)
    written_lh = append_fires(new_lh, hold_thesis=True)
    log.info(
        "pick_lab: appended %d entry fires, %d LH fires",
        written_entry, written_lh,
    )

    # Reload fires after appending (for scoreboard / grade pass)
    fires_entry = load_fires(hold_thesis=False)
    fires_lh = load_fires(hold_thesis=True)

    # (d) Grade pass
    grades_entry = load_grades(hold_thesis=False)
    grades_lh = load_grades(hold_thesis=True)

    _grade_pass(close_panel, fires_entry, grades_entry, fires_lh, grades_lh)

    # Reload grades after appending
    grades_entry = load_grades(hold_thesis=False)
    grades_lh = load_grades(hold_thesis=True)

    # (e) Scoreboard computation
    horizon_role_map = {b["engine_id"]: b["horizon_role"] for b in REGISTRY}
    ruler_map = {b["engine_id"]: b.get("ruler", "21d_spy_excess") for b in REGISTRY}

    ctrl_fires_e = [f for f in fires_entry if f.get("engine_id") == "plab_random_ctrl"]
    ctrl_grades_e = [g for g in grades_entry if g.get("engine_id") == "plab_random_ctrl"]

    all_sbs = all_scoreboards(
        fires_entry + fires_lh,
        grades_entry + grades_lh,
        horizon_role_map,
        ruler_map=ruler_map,
        ctrl_fires=ctrl_fires_e,
        ctrl_grades=ctrl_grades_e,
    )

    sbs_entry = [s for s in all_sbs if s.get("horizon_role") != "hold_thesis"]
    sbs_lh = [s for s in all_sbs if s.get("horizon_role") == "hold_thesis"]

    # Build site payloads
    entry_payload = _build_entry_site_payload(
        snap_enriched, asof, sbs_entry, fires_entry, grades_entry, regime
    )
    lh_payload = _build_longhold_site_payload(
        asof, sbs_lh, fires_lh, grades_lh
    )

    # Write site artifacts
    site = config.ROOT / "site"
    labdata = site / "labdata"
    _write_site_artifact(labdata / "pick_lab.json", entry_payload)
    _write_site_artifact(labdata / "pick_lab_longhold.json", lh_payload)

    # Write full-history fires export (pick_lab_fires.json)
    fires_payload = _build_fires_export(
        fires_entry, fires_lh, grades_entry, grades_lh, asof
    )
    _write_site_artifact(labdata / "pick_lab_fires.json", fires_payload)

    # (f) Render the page
    try:
        from engine.pick_lab.render import build_vm, render_page, _load_audit_scoreboard
        # Load T0 beta-screen artifact (graceful absent -> None)
        t0_dict = None
        t0_path = site / "factordata" / "t0_indicator.json"
        if t0_path.exists():
            try:
                t0_dict = json.loads(t0_path.read_text())
            except Exception as exc_t0:  # noqa: BLE001
                log.warning("pick_lab: could not load t0_indicator.json (%s)", exc_t0)
        # SA-W5 F1: load the committed scoreboard explicitly so build_vm injects real
        # coverage data (trailing_4wk, weekly_history, gate_suppressed).  Without this
        # the default audit_scoreboard=None → {"present": False} and render_page's
        # "not in vm" guard never fires (key IS present, just {"present": False}).
        audit_sb = _load_audit_scoreboard(site)
        vm = build_vm(
            entry_payload, lh_payload,
            t0_dict=t0_dict, audit_scoreboard=audit_sb,
            fires_dict=fires_payload,
        )
        render_page(vm, site)
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab: page render failed (%s) — data artifacts are good", exc)


def main() -> int:
    """Nightly pick-lab runner. Always returns 0 (PL-R10 never-break contract)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s :: %(message)s",
    )
    try:
        _build()
    except Exception:  # noqa: BLE001
        log.warning(
            "pick_lab: build failed — traceback below (non-fatal, returning 0)\n%s",
            traceback.format_exc(),
        )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
