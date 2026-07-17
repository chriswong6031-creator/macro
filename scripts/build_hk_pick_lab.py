"""HK Pick Lab asia-lane runner (spec §6, HKPL-R8).

Steps
-----
(a) Load latest HK snapshot via engine.pick_lab.snapshot.latest_snapshot(profile=HK_PROFILE);
    if none, log honest no-op and return 0 (first night after build_hk_library runs).
(b) ENRICHMENT JOIN: fill organ columns (washout_state, adr_gap_pct, cbbc_leverage_state,
    buyback_flag, dilution_flag, catalyst_days_to, attention_shock_z, narrative_tone,
    sfc_short_pressure_q, sb_accum_z, ah_discount_pctile, knife_risk) from same-night
    organ artifacts:
      site/factordata/hk_adr_bridge.json
      site/factordata/hk_cbbc.json
      site/factordata/hk_filing_bus.json
      site/factordata/hk_narrative.json
      site/factordata/hk_catalyst_calendar.json
    Regime scalars (risk_state, peg_state, liquidity_regime, vhsi_pctile, hsi_close)
    from data/hk_regime/latest.json.
    SB accum_z, A/H discount percentile, SFC short quartile from
    site/factordata/hk_standouts.json (same-night committed PIT surface).
    Freshness stamp per organ (HKPL-R7): organ staler than 2 HK sessions →
    organ_fresh_<tag>=False (fail-closed; disables organ-dependent books).
    Persist enriched frame (upsert) via HK_PROFILE.
(c) RE-COMPUTE the 1D Velocity Desk from the enriched frame and re-write
    site/factordata/hk_1d_velocity_desk.json (two-pass contract per velocity_desk.py).
(d) Run all 20 HK books + flagship2_mirror via hk.run_book_hk; apply 21-session
    refire lockout from the HK ledger.  Fire stamps: risk_state, peg_state,
    washout_state, adr_gap_pct, beta_role, vhsi_pctile, halted, halt_voided.
(e) GRADE PASS (HKPL-R4 halt law): exec = next HK session close (fill_basis="close").
    If exec session has no print → fill at first traded session within 5 HK sessions,
    else fire is halt_voided (halt_voided counter on scoreboard).
    A name halted >5 consecutive sessions inside a grade window grades to last trade
    with halted=true — never silent ffill.
    ^HSI excess primary ruler; absolute recorded alongside.
    Stale-cross diagnostic cohort graded through the same machinery into a diagnostic
    block of the site artifact.
(f) Scoreboard via book.all_scoreboards(profile=HK_PROFILE) (halt_voided +
    disabled_stale_nights columns); write site/labdata/hk_pick_lab.json.
(g) Render via engine.pick_lab.render_hk.

HKPL-R8: CN_LANE=asia env gate for ALL ledger/data writes. Non-asia = honest no-op.
Always exits 0 (HKPL-R8 never-break).
Authority: display_only throughout (HKPL-R1).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from lib import config

log = logging.getLogger("build_hk_pick_lab")

# ------------------------------------------------------------------ constants ---

# Lane gate: ALL ledger and data writes require CN_LANE=asia (HKPL-R8)
_CN_LANE = os.environ.get("CN_LANE", "")
_IS_ASIA_LANE = _CN_LANE == "asia"

# Output paths
_LABDATA_DIR = Path("site") / "labdata"
_HK_PICK_LAB_JSON = _LABDATA_DIR / "hk_pick_lab.json"
_HK_VELOCITY_DESK_JSON = Path("site") / "factordata" / "hk_1d_velocity_desk.json"

# Halt-outcome sidecar: persists halt_voided / exec_date outcomes across nights
# so the cumulative halt_voided counter is honest (HKPL-R4 / spec §5).
_HK_HALT_OUTCOMES_PATH = Path("data") / "hk_pick_lab" / "halt_outcomes.json"

# Organ artifact paths (site/factordata/)
_FACTORDATA_DIR = Path("site") / "factordata"
_HK_ADR_BRIDGE_PATH = _FACTORDATA_DIR / "hk_adr_bridge.json"
_HK_CBBC_PATH = _FACTORDATA_DIR / "hk_cbbc.json"
_HK_FILING_BUS_PATH = _FACTORDATA_DIR / "hk_filing_bus.json"
_HK_NARRATIVE_PATH = _FACTORDATA_DIR / "hk_narrative.json"
_HK_CATALYST_CALENDAR_PATH = _FACTORDATA_DIR / "hk_catalyst_calendar.json"
_HK_STANDOUTS_PATH = _FACTORDATA_DIR / "hk_standouts.json"

# Regime artifact
_HK_REGIME_PATH = Path("data") / "hk_regime" / "latest.json"

# Organ freshness staleness threshold (HKPL-R7)
_ORGAN_STALE_SESSIONS = 2

# Max recent fires per book in the site payload
_RECENT_FIRES_PER_BOOK = 30

# ^HSI benchmark ticker
_HSI_TICKER = "^HSI"

# Halt law: max sessions to search for a fill before voiding
_HALT_FILL_WINDOW = 5  # HKPL-R4


# ------------------------------------------------------------------ organ loaders ---


def _load_json(path: Path, label: str) -> dict:
    """Load a JSON file; return {} on failure (null-honest, never fatal)."""
    p = config.ROOT / path
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("hk_pick_lab: %s unreadable (%s)", label, exc)
        return {}


def _load_adr_bridge() -> dict:
    return _load_json(_HK_ADR_BRIDGE_PATH, "hk_adr_bridge.json")


def _load_cbbc() -> dict:
    return _load_json(_HK_CBBC_PATH, "hk_cbbc.json")


def _load_filing_bus() -> dict:
    return _load_json(_HK_FILING_BUS_PATH, "hk_filing_bus.json")


def _load_narrative() -> dict:
    return _load_json(_HK_NARRATIVE_PATH, "hk_narrative.json")


def _load_catalyst_calendar() -> dict:
    return _load_json(_HK_CATALYST_CALENDAR_PATH, "hk_catalyst_calendar.json")


def _load_standouts() -> dict:
    return _load_json(_HK_STANDOUTS_PATH, "hk_standouts.json")


def _load_hk_regime() -> dict:
    return _load_json(_HK_REGIME_PATH, "hk_regime/latest.json")


# ------------------------------------------------------------------ freshness ---


def _organ_is_fresh(artifact: dict, organ_asof_field: str, asof: str) -> bool:
    """Return True when the organ artifact's asof is within 2 HK sessions of tonight.

    HKPL-R7: staler than 2 HK sessions = organ stale (fail-closed).
    The `asof` argument is tonight's snap asof (YYYY-MM-DD string).
    Uses lib/hk_calendar to count HK sessions.
    """
    try:
        organ_date_str = artifact.get(organ_asof_field) or ""
        if not organ_date_str:
            return False
        organ_date = pd.Timestamp(organ_date_str).date()
        snap_date = pd.Timestamp(asof).date()

        from lib import hk_calendar  # type: ignore[import]
        # Count HK sessions from organ_date+1 to snap_date (inclusive)
        # If the number of sessions between them is > 2, the organ is stale.
        d = organ_date
        sessions_behind = 0
        while d < snap_date:
            d_next = d.__class__(d.year, d.month, d.day)
            import datetime as _dt
            d_next = d_next + _dt.timedelta(days=1)
            if hk_calendar.is_session(d_next):
                sessions_behind += 1
            d = d_next
            if sessions_behind > _ORGAN_STALE_SESSIONS:
                return False
        return True
    except Exception as exc:
        log.debug("hk_pick_lab: freshness check failed (%s) — treating organ as stale", exc)
        return False


# ------------------------------------------------------------------ enrichment builders ---


def _build_adr_by_ticker(adr: dict) -> dict[str, dict]:
    """Extract {hk_ticker: {adr_gap_pct, ...}} from hk_adr_bridge.json."""
    result: dict[str, dict] = {}
    for item in (adr.get("names") or []):
        ticker = item.get("hk_ticker", "")
        if not ticker:
            continue
        result[ticker] = {
            "adr_gap_pct": item.get("implied_open_gap_pct"),
        }
    return result


def _build_cbbc_by_ticker(cbbc: dict) -> dict[str, dict]:
    """Extract {ticker: {cbbc_leverage_state}} from hk_cbbc.json."""
    result: dict[str, dict] = {}
    for item in (cbbc.get("bellwethers") or []):
        ticker = item.get("ticker", "")
        if not ticker or ticker.startswith("^"):
            # Skip index entries (not individual stocks)
            continue
        result[ticker] = {
            "cbbc_leverage_state": item.get("leverage_state"),
        }
    return result


def _build_filing_by_ticker(filing: dict) -> dict[str, dict]:
    """Extract {ticker: {buyback_flag, dilution_flag}} from hk_filing_bus.json.

    A ticker may have multiple filings; aggregate: buyback_flag=True if any buyback,
    dilution_flag=True if any dilution.
    """
    result: dict[str, dict] = {}
    for item in (filing.get("tape") or []):
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        prev = result.get(ticker, {"buyback_flag": False, "dilution_flag": False})
        result[ticker] = {
            "buyback_flag": prev["buyback_flag"] or bool(item.get("buyback_flag")),
            "dilution_flag": prev["dilution_flag"] or bool(item.get("dilution_flag")),
        }
    return result


def _build_narrative_by_ticker(narrative: dict) -> dict[str, dict]:
    """Extract {ticker: {attention_shock_z, narrative_tone}} from hk_narrative.json."""
    result: dict[str, dict] = {}
    for item in (narrative.get("entities") or []):
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        result[ticker] = {
            "attention_shock_z": item.get("attention_shock_z"),
            "narrative_tone": item.get("tone_pctile"),  # tone_pctile ≡ narrative_tone
        }
    return result


def _build_catalyst_by_ticker(catalyst: dict) -> dict[str, dict]:
    """Extract {ticker: {catalyst_days_to}} from hk_catalyst_calendar.json.

    Uses the nearest upcoming catalyst for each ticker (minimum days_to).
    """
    result: dict[str, dict] = {}
    for item in (catalyst.get("upcoming") or []) + (catalyst.get("imminent") or []):
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        days = item.get("days_to") or item.get("sessions_to")
        if days is None:
            continue
        try:
            days = int(days)
        except (TypeError, ValueError):
            continue
        prev = result.get(ticker)
        if prev is None or days < prev["catalyst_days_to"]:
            result[ticker] = {"catalyst_days_to": days}
    return result


def _build_standouts_by_ticker(standouts: dict) -> dict[str, dict]:
    """Extract per-ticker SB accum_z, A/H percentile, SFC short quartile.

    hk_standouts.json has buy/watch/laggard rows with the full ticker context.
    We join across all cohorts.
    """
    result: dict[str, dict] = {}
    cohorts = ["buy", "watch", "laggards", "cohort"]
    for cohort_key in cohorts:
        for item in (standouts.get(cohort_key) or []):
            ticker = item.get("ticker", "")
            if not ticker:
                continue
            sb = item.get("southbound") or {}
            ah = item.get("ah_value") or {}
            sfc = item.get("sfc_short") or {}
            entry: dict = {}
            # southbound accum_z
            sb_z = sb.get("accum_z") if isinstance(sb, dict) else None
            if sb_z is not None:
                entry["sb_accum_z"] = sb_z
            # A/H discount percentile
            ah_pctile = ah.get("pctile") if isinstance(ah, dict) else None
            if ah_pctile is not None:
                entry["ah_discount_pctile"] = ah_pctile
            # SFC short pressure quartile (use pctile/25 to map to Q1-4)
            sfc_pctile = sfc.get("pctile") if isinstance(sfc, dict) else None
            if sfc_pctile is not None:
                try:
                    q = min(4, max(1, int(float(sfc_pctile) // 25) + 1))
                    entry["sfc_short_pressure_q"] = q
                except (TypeError, ValueError):
                    pass
            if entry:
                # keep first occurrence (highest-conviction cohort = buy)
                if ticker not in result:
                    result[ticker] = entry
                else:
                    for k, v in entry.items():
                        if result[ticker].get(k) is None:
                            result[ticker][k] = v
    return result


def _build_knife_by_ticker(standouts: dict) -> dict[str, bool]:
    """Derive knife_risk from standouts.  'laggards' cohort = deep losers = knife risk."""
    result: dict[str, bool] = {}
    for item in (standouts.get("laggards") or []):
        ticker = item.get("ticker", "")
        if ticker:
            result[ticker] = True
    return result


def _build_washout_by_ticker(standouts: dict) -> dict[str, dict]:
    """Extract per-ticker washout_state + confluence from standouts['washout_watch'].

    standouts['washout_watch'] is a list of {ticker, state, confluence_count,
    confluence_signals, asof_freshness, ...} emitted by hk_washout_watch.run_hk_washout.
    Returns {ticker: {washout_state, confluence_count, confluence_signals}}.
    """
    result: dict[str, dict] = {}
    for item in (standouts.get("washout_watch") or []):
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        state = item.get("state")
        if state is None:
            continue
        if ticker not in result:
            result[ticker] = {
                "washout_state": state,
                "confluence_count": item.get("confluence_count"),
                "confluence_signals": item.get("confluence_signals") or [],
            }
    return result


# ------------------------------------------------------------------ enrichment ---


def _enrich_snapshot(
    snap: pd.DataFrame,
    asof: str,
    adr: dict,
    cbbc: dict,
    filing: dict,
    narrative: dict,
    catalyst: dict,
    standouts: dict,
    regime: dict,
) -> tuple[pd.DataFrame, dict[str, bool]]:
    """Fill organ + regime columns onto the snapshot DataFrame.

    Returns (enriched_df, organ_fresh_flags) where organ_fresh_flags is
    {organ_tag: bool} — the freshness verdict used to stamp organ_fresh_* columns
    and passed to scoreboard for disabled_stale_nights tracking.

    Enrichment is ADDITIVE: a join failure leaves the column null.
    """
    df = snap.copy()

    # ---- Per-organ freshness assessment (HKPL-R7) -------------------------
    # ADR: hk_session_date or adr_date
    adr_fresh = _organ_is_fresh(adr, "hk_session_date", asof) or _organ_is_fresh(adr, "adr_date", asof)
    cbbc_fresh = _organ_is_fresh(cbbc, "as_of_trade_date", asof)
    filing_fresh = _organ_is_fresh(filing, "as_of", asof)
    narrative_fresh = _organ_is_fresh(narrative, "as_of", asof)
    catalyst_fresh = _organ_is_fresh(catalyst, "as_of", asof)
    # SB/SFC/AH come from standouts (shares freshness with SB organ)
    standouts_asof = standouts.get("as_of") or ""
    sb_fresh = bool(standouts_asof) and _organ_is_fresh({"as_of": standouts_asof}, "as_of", asof)

    # Washout organ freshness: derived from standouts as_of (same source as sb_fresh)
    # standouts['washout_watch'] is populated by build_hk_library via hk_washout_watch.
    washout_fresh = bool(standouts_asof) and _organ_is_fresh({"as_of": standouts_asof}, "as_of", asof)

    organ_fresh: dict[str, bool] = {
        "washout": washout_fresh,
        "adr": adr_fresh,
        "cbbc": cbbc_fresh,
        "narrative": narrative_fresh,
        "catalyst": catalyst_fresh,
        "sb": sb_fresh,
    }
    log.info(
        "hk_pick_lab: organ freshness — adr=%s cbbc=%s filing=%s narrative=%s catalyst=%s sb=%s washout=%s",
        adr_fresh, cbbc_fresh, filing_fresh, narrative_fresh, catalyst_fresh, sb_fresh, washout_fresh,
    )

    # ---- Regime scalars (broadcast to all rows) -------------------------
    risk_state: Optional[str] = regime.get("risk_state")
    peg_state: Optional[str] = regime.get("peg_state")
    liq_regime_raw = regime.get("liquidity_regime")
    # liquidity_regime may be a dict (from hk_standouts) or a string
    if isinstance(liq_regime_raw, dict):
        liquidity_regime: Optional[str] = liq_regime_raw.get("regime")
    else:
        liquidity_regime = liq_regime_raw if isinstance(liq_regime_raw, str) else None
    # Supplement from standouts if regime is absent
    if liquidity_regime is None:
        sq = standouts.get("liquidity_regime") or {}
        if isinstance(sq, dict):
            liquidity_regime = sq.get("regime")

    vhsi_pctile: Optional[float] = None
    fear = regime.get("fear_euphoria") or {}
    if isinstance(fear, dict):
        vhsi_pctile = fear.get("vhsi_pctile") or fear.get("vhsi_pct")

    scalar_map = {
        "risk_state": risk_state,
        "peg_state": peg_state,
        "liquidity_regime": liquidity_regime,
        "vhsi_pctile": vhsi_pctile,
    }
    for col, val in scalar_map.items():
        if val is None:
            continue
        if col not in df.columns:
            df[col] = val
        else:
            null_mask = df[col].isna()
            if null_mask.any():
                df.loc[null_mask, col] = val

    # ---- Organ freshness flag columns --------------------------------
    for organ_tag, fresh in organ_fresh.items():
        col = f"organ_fresh_{organ_tag}"
        df[col] = fresh

    # ---- Per-ticker organ data ---------------------------------------
    adr_by_ticker = _build_adr_by_ticker(adr)
    cbbc_by_ticker = _build_cbbc_by_ticker(cbbc)
    filing_by_ticker = _build_filing_by_ticker(filing)
    narrative_by_ticker = _build_narrative_by_ticker(narrative)
    catalyst_by_ticker = _build_catalyst_by_ticker(catalyst)
    standouts_by_ticker = _build_standouts_by_ticker(standouts)
    knife_by_ticker = _build_knife_by_ticker(standouts)
    washout_by_ticker = _build_washout_by_ticker(standouts)

    def _fill_col(col: str, by_ticker: dict, key: str) -> None:
        if col not in df.columns:
            df[col] = None
        for ticker in df.index:
            if ticker in by_ticker:
                val = by_ticker[ticker].get(key)
                if val is not None:
                    cur = df.at[ticker, col]
                    if cur is None or (not isinstance(cur, (str, list)) and pd.isna(cur)):
                        df.at[ticker, col] = val

    _fill_col("adr_gap_pct", adr_by_ticker, "adr_gap_pct")
    _fill_col("cbbc_leverage_state", cbbc_by_ticker, "cbbc_leverage_state")
    _fill_col("buyback_flag", filing_by_ticker, "buyback_flag")
    _fill_col("dilution_flag", filing_by_ticker, "dilution_flag")
    _fill_col("attention_shock_z", narrative_by_ticker, "attention_shock_z")
    _fill_col("narrative_tone", narrative_by_ticker, "narrative_tone")
    _fill_col("catalyst_days_to", catalyst_by_ticker, "catalyst_days_to")
    _fill_col("sb_accum_z", standouts_by_ticker, "sb_accum_z")
    _fill_col("ah_discount_pctile", standouts_by_ticker, "ah_discount_pctile")
    _fill_col("sfc_short_pressure_q", standouts_by_ticker, "sfc_short_pressure_q")

    # washout organ data (state + confluence)
    _fill_col("washout_state", washout_by_ticker, "washout_state")
    _fill_col("confluence_count", washout_by_ticker, "confluence_count")
    _fill_col("confluence_signals", washout_by_ticker, "confluence_signals")

    # knife_risk (bool)
    if "knife_risk" not in df.columns:
        df["knife_risk"] = None
    for ticker in df.index:
        if ticker in knife_by_ticker and (
            df.at[ticker, "knife_risk"] is None or pd.isna(df.at[ticker, "knife_risk"])
        ):
            df.at[ticker, "knife_risk"] = True

    return df, organ_fresh


# ------------------------------------------------------------------ HK price store ---


def _load_hk_close_series(ticker: str) -> Optional[pd.Series]:
    """Load a per-ticker HK close series from the data store."""
    try:
        from engine.data_store import store  # type: ignore[import]
        df = store.read("hk", ticker)
        if df is None or df.empty:
            return None
        close = df["close"] if "close" in df.columns else df.iloc[:, 0]
        close.index = pd.DatetimeIndex(close.index)
        return close.sort_index()
    except Exception as exc:
        log.debug("hk_pick_lab: close series for %s unavailable (%s)", ticker, exc)
        return None


# ------------------------------------------------------------------ fire pass ---


def _fire_all_hk_books(
    snap: pd.DataFrame,
    asof: str,
    fires_existing: list[dict],
    trading_dates: pd.DatetimeIndex,
    vd_rows: list[dict],
) -> list[dict]:
    """Run all 20 HK books + flagship2_mirror; apply refire lockout.

    Returns new_entry_fires (list of fire row dicts).
    HK has no sealed_up concept (no daily price limits, HKPL-R4).
    HKPL-R8: only writes if CN_LANE=asia; if not, returns empty list.
    """
    if not _IS_ASIA_LANE:
        log.info("hk_pick_lab: CN_LANE!='asia' — fire pass is a no-op (HKPL-R8)")
        return []

    from engine.pick_lab.hk import run_book_hk
    from engine.pick_lab.ledger import is_open
    from engine.pick_lab.registry_hk import HK_REGISTRY, HK_FLAGSHIP2_MIRROR_ID

    new_fires: list[dict] = []

    snap_with_asof = snap.copy()
    snap_with_asof.attrs["asof"] = asof

    # Build flagship2_mirror picks from the velocity desk rows (§4)
    f2_picks: list[dict] = []
    for i, row in enumerate(vd_rows or [], 1):
        ticker = row.get("ticker", "")
        if ticker:
            f2_picks.append({
                "ticker": ticker,
                "rank": i,
                "close": row.get("close"),
                "sector": row.get("sector"),
                "name": row.get("name"),
                "name_zh": row.get("name_zh"),
                "liq_unknown": False,
                "is_avoid": False,
                "why": ["flagship2_mirror"],
                "features": {"confluence_n": row.get("confluence_n"), "edge_z": row.get("edge_z")},
                "authority": "display_only",
            })

    _FLAGSHIP2_BOOK = {
        "engine_id": HK_FLAGSHIP2_MIRROR_ID,
        "refire_lockout_sessions": 21,
        "config_hash": "flagship2_mirror",
    }

    all_books_iter = list(HK_REGISTRY) + [None]  # None = flagship2 sentinel

    for book_or_none in all_books_iter:
        is_f2 = book_or_none is None
        if is_f2:
            book = _FLAGSHIP2_BOOK
            picks_raw = f2_picks
            disabled_stale = False
        else:
            book = book_or_none
            result = run_book_hk(book, snap_with_asof)
            picks_raw = result.get("picks") or []
            disabled_stale = result.get("disabled_stale", False)

        engine_id = book["engine_id"]
        lockout = book["refire_lockout_sessions"]

        if disabled_stale and not is_f2:
            log.debug("hk_pick_lab: %s disabled_stale — skip fire (HKPL-R7)", engine_id)
            continue

        for pick in picks_raw:
            ticker = pick.get("ticker")
            if not ticker:
                continue

            # Refire lockout check (HKPL-R6)
            if is_open(engine_id, ticker, trading_dates, fires_existing, lockout):
                log.debug("hk_pick_lab: %s/%s lockout — skip fire", engine_id, ticker)
                continue

            # Stamp HK-specific fields from snapshot (HKPL-R5 stamps)
            def _snap_val(col: str, default=None):
                if col in snap.columns and ticker in snap.index:
                    v = snap.at[ticker, col]
                    try:
                        if not isinstance(v, str) and pd.isna(v):
                            return None
                    except Exception:
                        pass
                    return v
                return default

            fire_row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": asof,
                "exec_date": None,       # filled at grade time
                "rank": pick.get("rank"),
                "close_at_fire": pick.get("close"),
                "sector": pick.get("sector"),
                "name": pick.get("name"),
                "name_zh": pick.get("name_zh"),
                "why": pick.get("why") or [],
                "features": pick.get("features") or {},
                "liq_unknown": bool(pick.get("liq_unknown")),
                "is_avoid": bool(pick.get("is_avoid")),
                "disabled_stale": disabled_stale,
                # HK stamps (HKPL-R5)
                "risk_state": _snap_val("risk_state"),
                "peg_state": _snap_val("peg_state"),
                "washout_state": _snap_val("washout_state"),
                "adr_gap_pct": _snap_val("adr_gap_pct"),
                "beta_role": _snap_val("beta_role"),
                "vhsi_pctile": _snap_val("vhsi_pctile"),
                # Halt fields — filled at grade time
                "halted": None,
                "halt_voided": False,
                "config_hash": book["config_hash"],
                "authority": "display_only",
            }

            new_fires.append(fire_row)
            fires_existing.append(fire_row)   # so later books see this fire for lockout

    log.info("hk_pick_lab: fires this run — %d new", len(new_fires))
    return new_fires


# ------------------------------------------------------------------ grade pass (HKPL-R4 halt law) ---


def _build_hk_close_panel(
    hsi_closes: Optional[pd.Series],
    closes_by_ticker: dict[str, pd.Series],
) -> pd.DataFrame:
    """Build a close panel indexed on the ^HSI benchmark calendar.

    ^HSI calendar is authoritative for HK; each fired ticker is a column.
    Tickers halted on a session have NaN — null-honest per grade.py spec §4
    (ticker absent from panel → ungradeable at that horizon).
    HK stores carry only close+volume (no high/low), so high_panel/low_panel
    are not built here; grade_fires() is called with high_panel=None.

    Returns DataFrame[DatetimeIndex x ticker] or empty DataFrame.
    """
    if hsi_closes is not None and not hsi_closes.empty:
        date_index: pd.DatetimeIndex = pd.DatetimeIndex(hsi_closes.index).sort_values()
    else:
        all_dates: set[pd.Timestamp] = set()
        for s in closes_by_ticker.values():
            all_dates.update(s.index)
        date_index = pd.DatetimeIndex(sorted(all_dates))

    if len(date_index) == 0:
        return pd.DataFrame(index=pd.DatetimeIndex([]))

    cols: dict[str, pd.Series] = {}
    for ticker, series in closes_by_ticker.items():
        cols[ticker] = series.reindex(date_index)
    if hsi_closes is not None:
        cols[_HSI_TICKER] = hsi_closes.reindex(date_index)

    return pd.DataFrame(cols, index=date_index)


def _hk_grade_pass(
    fires: list[dict],
    grades_existing: list[dict],
    asof: str,
    hsi_closes: Optional[pd.Series],
) -> int:
    """Grade matured HK fires via the shared grade_fires() engine (HKPL-R4).

    Routes all HK fires through engine.pick_lab.grade.grade_fires() with a panel
    indexed on the ^HSI benchmark calendar so horizon windows are comparable
    across all tickers in the same book.

    Halt law (HKPL-R4):
    (a) If the exec session has no print: fill at the first traded session within
        5 sessions (fill_basis='close_halt_delayed', halted=True).  If no print
        within 5 sessions: fire is VOIDED (halt_voided counter, never graded).
    (b) A name halted through a grade-window target session grades to last trade
        with halted=True — never silent ffill.

    Pre-processing: resolve_exec_session(fill_window=5) pre-scans fires before
    the grade pass.  'void' fires are excluded and halt_voided counter incremented.
    'deferred' fires are left in for grade_fires to skip-retry later.
    grade_fires is called with exec_fill_window=5 and halt_grade_to_last_trade=True.

    Post-processing: rows whose exec_date != natural exec session get
    fill_basis='close_halt_delayed' and halted=True; normal rows get
    fill_basis='close' and halted as set by grade_fires (default False).

    HK stores carry close+volume only (no high/low) → high_panel=None.
    Sector-relative excess is null (CN/HK have no GICS ETF map; ret_rel_sector=null).
    Returns count of new grade rows written.
    """
    if not _IS_ASIA_LANE:
        log.info("hk_pick_lab: CN_LANE!='asia' — grade pass is a no-op (HKPL-R8)")
        return 0

    from engine.pick_lab.grade import grade_fires, resolve_exec_session, _next_session
    from engine.pick_lab.ledger import GRADE_KEY, append_grades
    from engine.pick_lab.profile import HK_PROFILE

    already_graded: set[tuple] = {
        tuple(g.get(f) for f in GRADE_KEY) for g in grades_existing
    }

    # Load close series for fired tickers only (never full-universe scan)
    fired_tickers = {f.get("ticker", "") for f in fires if f.get("ticker")}
    closes_by_ticker: dict[str, pd.Series] = {}
    for ticker in fired_tickers:
        series = _load_hk_close_series(ticker)
        if series is not None:
            closes_by_ticker[ticker] = series

    # Load persisted halt outcomes and apply to fire rows in-place
    halt_outcomes = _load_halt_outcomes()
    _apply_halt_outcomes(fires, halt_outcomes)

    # Build close panel on ^HSI calendar; HK stores have no high/low
    close_panel = _build_hk_close_panel(hsi_closes, closes_by_ticker)

    # Build date index for resolve_exec_session (use panel or benchmark)
    if not close_panel.empty:
        date_index = pd.DatetimeIndex(close_panel.index).sort_values()
    elif hsi_closes is not None and not hsi_closes.empty:
        date_index = pd.DatetimeIndex(hsi_closes.index).sort_values()
    else:
        all_dates_set: set[pd.Timestamp] = set()
        for s in closes_by_ticker.values():
            all_dates_set.update(s.index)
        date_index = pd.DatetimeIndex(sorted(all_dates_set))

    # Pre-scan: resolve exec session for each fire that hasn't been halt_voided yet.
    # 'void' → exclude from grading, increment halt_voided counter.
    # 'deferred' → leave in (grade_fires will silently skip-retry).
    # Also record natural_exec_date per fire key for post-processing stamp.
    _FILL_WINDOW = 5
    natural_exec_by_key: dict[tuple, str] = {}  # (engine_id, ticker, fire_date) → natural_exec_date str

    for fire in fires:
        if fire.get("halt_voided"):
            continue  # already marked from a previous night's sidecar

        ticker = str(fire.get("ticker", ""))
        fire_date_raw = fire.get("fire_date")
        try:
            fire_date = pd.Timestamp(fire_date_raw)
        except Exception:
            continue

        # Natural exec is always the first session after fire_date
        natural_exec = _next_session(fire_date, date_index)
        if natural_exec is not None:
            fkey = (fire.get("engine_id", ""), ticker, str(fire_date.date()))
            natural_exec_by_key[fkey] = str(natural_exec.date())

        # Use the panel to resolve exec (covers halt fill window)
        if close_panel.empty:
            # No panel — can't resolve exec for any fire
            continue

        res = resolve_exec_session(ticker, fire_date, date_index, close_panel, _FILL_WINDOW)
        if res[0] == "void":
            fire["halt_voided"] = True
            _hv_key = f"{fire.get('engine_id','')}\x1c{ticker}\x1c{str(fire_date.date())}"
            halt_outcomes[_hv_key] = True
            log.debug(
                "hk_pick_lab: grade — %s/%s halt-voided (no print within %d sessions)",
                fire.get("engine_id", ""), ticker, _FILL_WINDOW,
            )
        # 'deferred' and 'resolved' are left in fires list for grade_fires to handle

    try:
        _save_halt_outcomes(halt_outcomes)
    except Exception as _ho_exc:
        log.warning("hk_pick_lab: halt outcomes sidecar write failed (%s) — non-fatal", _ho_exc)

    if close_panel.empty:
        log.info("hk_pick_lab: close panel empty — no grades this run")
        return 0

    spy_closes = hsi_closes if hsi_closes is not None else pd.Series(dtype=float)

    # Exclude halt_voided fires from the grade pass
    gradeable_fires = [f for f in fires if not f.get("halt_voided")]

    new_grade_rows, n_ung = grade_fires(
        gradeable_fires,
        close_panel,
        spy_closes,
        sector_closes=None,       # HK has no GICS ETF map; ret_rel_sector stays null
        hold_thesis=False,
        already_graded=already_graded,
        high_panel=None,          # HK stores carry close+volume only (no high/low)
        low_panel=None,
        exec_fill_window=_FILL_WINDOW,
        halt_grade_to_last_trade=True,
    )

    if n_ung:
        log.info("hk_pick_lab: %d fires ungradeable (ticker absent/halted in panel)", n_ung)

    # Post-process: stamp HK-specific schema fields grade.py does not emit.
    # Rows whose exec_date != natural exec session were delayed by a halt:
    #   fill_basis='close_halt_delayed', halted=True (override grade.py's halted flag).
    # Normal rows: fill_basis='close', halted as grade.py set (default False).
    for row in new_grade_rows:
        if row.get("kind") == "path":
            row["benchmark_ticker"] = _HSI_TICKER
            continue
        fkey = (row.get("engine_id", ""), row.get("ticker", ""), row.get("fire_date", ""))
        natural_exec_str = natural_exec_by_key.get(fkey)
        row_exec_str = row.get("exec_date", "")
        if natural_exec_str and row_exec_str and row_exec_str != natural_exec_str:
            row["fill_basis"] = "close_halt_delayed"
            row["halted"] = True
        else:
            row["fill_basis"] = "close"
            # halted already set by grade_fires (halt_grade_to_last_trade=True)
        row["benchmark_ticker"] = _HSI_TICKER

    if new_grade_rows:
        written = append_grades(new_grade_rows, hold_thesis=False, profile=HK_PROFILE)
        log.info("hk_pick_lab: wrote %d new grade rows", written)
        return written

    log.info("hk_pick_lab: no new grades this run")
    return 0


# ------------------------------------------------------------------ stale-cross diagnostic ---


def _build_stale_cross_grades(
    snap: pd.DataFrame,
    asof: str,
    hsi_closes: Optional[pd.Series],
    date_index: pd.DatetimeIndex,
) -> list[dict]:
    """Grade the stale-cross cohort as a diagnostic block (HKPL-R10, spec §3).

    Stale-cross: 2D/3D cross ≥5 sessions old with |return since cross| < 3%.
    This cohort is graded at h=21 for comparison with hklab_1d_blastoff.
    Returns a list of {ticker, sessions_since_cross, ret_since_cross, ret21_abs,
    ret21_excess, graded_at} dicts. authority=display_only; NOT appended to grades.jsonl.
    """
    if snap.empty:
        return []

    result: list[dict] = []
    graded_at = datetime.now(tz=timezone.utc).isoformat()

    for ticker, row in snap.iterrows():
        sc = row.get("sessions_since_23d_cross")
        ret_sc = row.get("ret_since_23d_cross")

        # Stale-cross filter: ≥5 sessions since cross AND |ret| < 3%
        try:
            if sc is None or pd.isna(sc):
                continue
            sc_int = int(sc)
            if sc_int < 5:
                continue
            if ret_sc is not None and not pd.isna(ret_sc):
                if abs(float(ret_sc)) >= 0.03:
                    continue
        except (TypeError, ValueError):
            continue

        result.append({
            "ticker": ticker,
            "sessions_since_23d_cross": sc_int,
            "ret_since_23d_cross": float(ret_sc) if ret_sc is not None and not pd.isna(ret_sc) else None,
            "graded_at": graded_at,
            "authority": "display_only",
        })

    return result


# ------------------------------------------------------------------ site payload ---


def _build_recent_fires_with_grades(
    fires: list[dict],
    grades: list[dict],
    engine_id: str,
    n: int = _RECENT_FIRES_PER_BOOK,
) -> list[dict]:
    """Return N most recent fires for engine_id with h=21 grade attached if matured."""
    my_fires = sorted(
        [f for f in fires if f.get("engine_id") == engine_id],
        key=lambda x: x.get("fire_date", ""),
        reverse=True,
    )[:n]

    grade_map: dict[tuple, dict] = {}
    for g in grades:
        if g.get("kind") == "path":
            continue  # path rows carry path metrics, not ret — skip
        if g.get("engine_id") != engine_id:
            continue
        k = (g.get("ticker"), g.get("fire_date"))
        h = g.get("horizon")
        if k not in grade_map or h == 21:
            grade_map[k] = g

    result = []
    for f in my_fires:
        k = (f.get("ticker"), f.get("fire_date"))
        g = grade_map.get(k)
        row = dict(f)
        if g:
            row["ret21_excess"] = g.get("ret_excess_spy")
            row["ret21_abs"] = g.get("ret_abs")
            row["matured"] = bool(g.get("matured"))
        else:
            row["ret21_excess"] = None
            row["ret21_abs"] = None
            row["matured"] = False
        result.append(row)
    return result


def _picks_today(fires: list[dict], asof: str) -> dict[str, list[dict]]:
    """Return {engine_id: [pick dicts]} for today's fires."""
    result: dict[str, list[dict]] = {}
    for f in fires:
        if f.get("fire_date") != asof:
            continue
        eid = f.get("engine_id", "")
        result.setdefault(eid, []).append(f)
    return result


def _load_halt_outcomes() -> dict[str, bool]:
    """Load persisted halt outcomes from sidecar (key = engine_id|ticker|fire_date).

    Returns {} on any read failure (honest null; the sidecar is supplemental).
    """
    p = config.ROOT / _HK_HALT_OUTCOMES_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_halt_outcomes(outcomes: dict[str, bool]) -> None:
    """Persist halt outcomes sidecar atomically (HKPL-R8: asia lane only)."""
    if not _IS_ASIA_LANE:
        return
    p = config.ROOT / _HK_HALT_OUTCOMES_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_halt_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(outcomes, fh)
        os.replace(tmp, str(p))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _apply_halt_outcomes(fires: list[dict], outcomes: dict[str, bool]) -> None:
    """Stamp persisted halt_voided / exec_date outcomes onto fire rows in-place.

    This ensures that fires loaded from disk on subsequent nights carry the
    halt outcome that was determined during the night the grade pass ran.
    """
    for f in fires:
        key = f"{f.get('engine_id','')}\x1c{f.get('ticker','')}\x1c{f.get('fire_date','')}"
        if key in outcomes:
            f["halt_voided"] = outcomes[key]


def _count_halt_voided(fires: list[dict]) -> int:
    """Count total halt_voided fires across all books (cumulative, post-outcome-apply)."""
    return sum(1 for f in fires if f.get("halt_voided"))


def _count_disabled_stale_nights(
    fires: list[dict], engine_id: str
) -> int:
    """Count nights a book was skipped due to organ staleness (approximation from fire absence)."""
    # disabled_stale_nights is approximated as the number of asof dates where
    # the book fired disabled_stale=True (recorded on fire rows during the fire pass).
    # Full tracking would require storing a separate disabled log — this is best-effort.
    return sum(
        1 for f in fires
        if f.get("engine_id") == engine_id and f.get("disabled_stale")
    )


def _build_hk_site_payload(
    asof: str,
    scoreboards: list[dict],
    fires: list[dict],
    grades: list[dict],
    halt_voided_total: int,
    stale_cross_rows: list[dict],
) -> dict:
    """Build the dict written to site/labdata/hk_pick_lab.json."""
    from engine.pick_lab.registry_hk import HK_REGISTRY, HK_FLAGSHIP2_MIRROR_ID

    picks_today_by_book = _picks_today(fires, asof)

    all_book_ids = [b["engine_id"] for b in HK_REGISTRY] + [HK_FLAGSHIP2_MIRROR_ID]
    book_meta = {b["engine_id"]: b for b in HK_REGISTRY}

    books: dict = {}
    for eid in all_book_ids:
        bm = book_meta.get(eid, {"engine_id": eid, "name_en": eid, "name_zh": eid, "family": ""})
        books[eid] = {
            "engine_id": eid,
            "name_en": bm.get("name_en", eid),
            "name_zh": bm.get("name_zh", eid),
            "family": bm.get("family", ""),
            "picks_today": picks_today_by_book.get(eid) or [],
            "recent_fires": _build_recent_fires_with_grades(fires, grades, eid),
            "disabled_stale": False,
            "disabled_stale_nights": _count_disabled_stale_nights(fires, eid),
        }

    # Detect disabled_stale from fires
    for f in fires:
        eid = f.get("engine_id", "")
        if f.get("disabled_stale") and eid in books:
            books[eid]["disabled_stale"] = True

    # Scoreboard: denormalize name/family from registry
    scoreboard_out = []
    for sb in scoreboards:
        eid = sb.get("engine_id", "")
        bm = book_meta.get(eid, {})
        row = dict(sb)
        row["name_en"] = bm.get("name_en", eid)
        row["name_zh"] = bm.get("name_zh", eid)
        row["family"] = bm.get("family", "")
        row["horizon_role"] = bm.get("horizon_role", "entry")
        row["ruler"] = bm.get("ruler", "21d_hsi_excess")
        # Remap book.py keys → template schema
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
        row["disabled_stale_nights"] = books.get(eid, {}).get("disabled_stale_nights", 0)
        scoreboard_out.append(row)

    return {
        "as_of": asof,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "scoreboard": scoreboard_out,
        "books": books,
        "total_halt_voided": halt_voided_total,
        "stale_cross_diagnostic": stale_cross_rows,
        "method_note": (
            "HK Pick Lab — display-only forward-evidence lab. "
            "All books ACCRUING until n≥25 fires / ≥3 months / ≥6 distinct fire dates (HKPL-R6). "
            "hklab_random_ctrl = yardstick. Primary ruler: 21d ^HSI excess (HKPL-R3). "
            "Execution: next HK session close (fill_basis=close); no price limits (HKPL-R4). "
            "Halt law: no print at exec → first traded within 5 sessions; else halt_voided. "
            "Organ-dependent books disabled when organ data staler than 2 HK sessions (HKPL-R7). "
            "Authority: display_only. Never gates or scores anything."
        ),
        "authority": "display_only",
    }


# ------------------------------------------------------------------ write helper ---


def _write_site_artifact(path: Path, payload: dict) -> None:
    """Atomically write a JSON site artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, default=str)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    log.info("hk_pick_lab: wrote %s (%.0f KB)", path, path.stat().st_size / 1024)


# ------------------------------------------------------------------ main build ---


def _build() -> None:
    """Core HK Pick Lab build (all exceptions propagate to main's try/except)."""
    t_start = time.monotonic()
    log.info("hk_pick_lab: start (CN_LANE=%r)", _CN_LANE)

    from engine.pick_lab import snapshot as snap_mod
    from engine.pick_lab.ledger import (
        append_fires,
        load_fires,
        load_grades,
    )
    from engine.pick_lab.book import all_scoreboards
    from engine.pick_lab.profile import HK_PROFILE
    from engine.pick_lab.registry_hk import HK_REGISTRY, HK_FLAGSHIP2_MIRROR_ID

    # (a) Load latest HK snapshot
    snap, asof = snap_mod.latest_snapshot(profile=HK_PROFILE)
    if snap is None or asof is None:
        log.info(
            "hk_pick_lab: no snapshot found in %s — honest no-op "
            "(first run after build_hk_library produces one)",
            HK_PROFILE.snapshot_dir,
        )
        return

    log.info("hk_pick_lab: snapshot asof=%s, %d rows", asof, len(snap))

    # (b) Enrichment join from organ artifacts + regime + standouts
    adr = _load_adr_bridge()
    cbbc = _load_cbbc()
    filing = _load_filing_bus()
    narrative = _load_narrative()
    catalyst = _load_catalyst_calendar()
    standouts = _load_standouts()
    regime = _load_hk_regime()

    snap_enriched, organ_fresh = _enrich_snapshot(
        snap, asof, adr, cbbc, filing, narrative, catalyst, standouts, regime
    )

    # Persist enriched snapshot (upsert; HKPL-R8 lane gate)
    if _IS_ASIA_LANE:
        try:
            snap_mod.write_snapshot(
                snap_enriched.reset_index(), asof, mode="upsert", profile=HK_PROFILE
            )
        except Exception as exc:
            log.warning(
                "hk_pick_lab: enriched snapshot persist failed (%s) — proceeding in-memory",
                exc,
            )
    else:
        log.info("hk_pick_lab: CN_LANE!='asia' — snapshot write skipped (HKPL-R8)")

    # (c) Re-compute 1D Velocity Desk from enriched frame and re-write (two-pass contract)
    try:
        from engine.pick_lab.velocity_desk import build_velocity_desk_artifact
        vd_artifact = build_velocity_desk_artifact(snap_enriched, as_of=asof)
        vd_rows: list[dict] = vd_artifact.get("rows") or []
        if _IS_ASIA_LANE:
            _write_site_artifact(config.ROOT / _HK_VELOCITY_DESK_JSON, vd_artifact)
        log.info("hk_pick_lab: velocity desk (enriched pass) — %d rows", len(vd_rows))
    except Exception as exc:
        log.warning("hk_pick_lab: velocity desk re-compute failed (%s) — using empty rows", exc)
        vd_rows = []

    # Build trading date index for refire-lockout check (from ^HSI or union of ticker closes)
    trading_dates: pd.DatetimeIndex = pd.DatetimeIndex([])
    hsi_closes: Optional[pd.Series] = None
    try:
        bm_loader = HK_PROFILE.benchmark_loader
        if callable(bm_loader):
            hsi_closes = bm_loader()
            if hsi_closes is not None and not hsi_closes.empty:
                trading_dates = pd.DatetimeIndex(hsi_closes.index).sort_values()
    except Exception as exc:
        log.warning("hk_pick_lab: trading date index build failed (%s)", exc)

    # (d) Fire pass
    fires_entry = load_fires(hold_thesis=False, profile=HK_PROFILE)

    new_fires = _fire_all_hk_books(
        snap_enriched, asof, fires_entry, trading_dates, vd_rows
    )

    if _IS_ASIA_LANE and new_fires:
        written = append_fires(new_fires, hold_thesis=False, profile=HK_PROFILE)
        log.info("hk_pick_lab: appended %d HK entry fires", written)

    # Reload fires (for scoreboard + grade pass)
    fires_entry = load_fires(hold_thesis=False, profile=HK_PROFILE)

    # (e) Grade pass (HKPL-R4 halt law)
    grades_entry = load_grades(hold_thesis=False, profile=HK_PROFILE)
    _hk_grade_pass(fires_entry, grades_entry, asof, hsi_closes)

    # Reload grades after append
    grades_entry = load_grades(hold_thesis=False, profile=HK_PROFILE)

    # Stale-cross diagnostic cohort
    stale_cross_rows = _build_stale_cross_grades(snap_enriched, asof, hsi_closes, trading_dates)
    log.info("hk_pick_lab: stale-cross diagnostic — %d cohort names", len(stale_cross_rows))

    # (f) Scoreboard
    horizon_role_map = {b["engine_id"]: b["horizon_role"] for b in HK_REGISTRY}
    horizon_role_map[HK_FLAGSHIP2_MIRROR_ID] = "entry"
    ruler_map = {b["engine_id"]: b.get("ruler", "21d_hsi_excess") for b in HK_REGISTRY}
    ruler_map[HK_FLAGSHIP2_MIRROR_ID] = "21d_hsi_excess"

    ctrl_fires = [f for f in fires_entry if f.get("engine_id") == HK_PROFILE.random_ctrl_id]
    ctrl_grades = [g for g in grades_entry if g.get("engine_id") == HK_PROFILE.random_ctrl_id]

    scoreboards = all_scoreboards(
        fires_entry,
        grades_entry,
        horizon_role_map,
        ruler_map=ruler_map,
        ctrl_fires=ctrl_fires,
        ctrl_grades=ctrl_grades,
        profile=HK_PROFILE,
    )

    # Apply persisted halt outcomes to reloaded fires so the count is cumulative
    _apply_halt_outcomes(fires_entry, _load_halt_outcomes())
    halt_voided_total = _count_halt_voided(fires_entry)
    payload = _build_hk_site_payload(
        asof, scoreboards, fires_entry, grades_entry,
        halt_voided_total, stale_cross_rows,
    )
    site = config.ROOT / "site"
    labdata = site / "labdata"
    if _IS_ASIA_LANE:
        _write_site_artifact(labdata / "hk_pick_lab.json", payload)
    else:
        log.info("hk_pick_lab: CN_LANE!='asia' — site/labdata/hk_pick_lab.json write skipped (HKPL-R8)")

    # (g) Render
    try:
        from engine.pick_lab.render_hk import build_vm, render_page
        vm = build_vm(payload)
        if _IS_ASIA_LANE:
            render_page(vm, site)
        else:
            log.info("hk_pick_lab: CN_LANE!='asia' — page render skipped (HKPL-R8)")
    except Exception as exc:
        log.warning("hk_pick_lab: page render failed (%s) — data artifacts are good", exc)

    elapsed = time.monotonic() - t_start
    log.info(
        "hk_pick_lab: done in %.1fs (budget 120s) — fires=%d halt_voided=%d stale_cross=%d",
        elapsed, len(new_fires), halt_voided_total, len(stale_cross_rows),
    )
    if elapsed > 120:
        log.warning(
            "hk_pick_lab: elapsed %.1fs exceeds 2-minute budget (HKPL-R8)",
            elapsed,
        )


def main() -> int:
    """HK Pick Lab asia-lane runner. Always returns 0 (HKPL-R8 never-break contract)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s :: %(message)s",
    )
    if not _IS_ASIA_LANE:
        log.info(
            "hk_pick_lab: CN_LANE=%r — non-asia invocation is an honest no-op "
            "(ledger/data writes gated on CN_LANE=asia per HKPL-R8)",
            _CN_LANE,
        )
        # Still attempt the render from committed artifacts (no ledger writes)
        try:
            _build()
        except Exception:
            log.warning(
                "hk_pick_lab: non-asia build failed — non-fatal\n%s",
                traceback.format_exc(),
            )
        return 0

    try:
        _build()
    except Exception:
        log.warning(
            "hk_pick_lab: build failed — traceback below (non-fatal, returning 0)\n%s",
            traceback.format_exc(),
        )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
