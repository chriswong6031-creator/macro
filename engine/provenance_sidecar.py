"""engine/provenance_sidecar.py — Build the view.provenance[] sidecar for each US ticker.

The provenance sidecar surfaces the 5–10 load-bearing signals for a ticker as a
list of structured rows, each traceable back to a spine row, kernel cell, and
qual_ladder state.  It is the data contract for the Committee View flagship page
(site/committee.html).

Design constraints:
- Fail-open per field: a missing parquet, missing kernel cell, or missing
  qual_ladder entry yields null fields rather than raising.
- US-only (v1): this module only assembles US ticker provenance; regional
  variants (CA/HK/CN) are out of scope and documented as such.
- Display-only law: all kernel shrunken_ic values are display-only estimates
  (first FDR decision batch runs 2026-10-01); every row carries is_display_only=true.
- Never gates a money path: the provenance list is consumed only by the
  Committee View (a research/explanation surface), never by ranking, alerting, or
  allocation engines.

Usage (called by scripts/build_stock_library.py in the deferred write loop):
    from engine.provenance_sidecar import build_provenance
    rec["view"]["provenance"] = build_provenance(ticker, rec, ctx)

where ctx = ProvenanceContext (shared across all tickers, loaded once in main()).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger("provenance_sidecar")

# ---------------------------------------------------------------------------
# Qual-ladder state map (static at build time; sourced from config/qual_ladder.yml)
# We embed the key facts here rather than re-parsing YAML at runtime to keep
# the module dependency-free.  If qual_ladder.yml changes, update this dict.
# ---------------------------------------------------------------------------
_QUAL_LADDER: dict[str, dict] = {
    "altdata":               {"ladder_state": "DISPLAY", "grandfathered": True},
    "radar.edge_score":      {"ladder_state": "DISPLAY", "grandfathered": False},
    "radar.divergence_z":    {"ladder_state": "SHADOW",  "grandfathered": False},
    "us_importance_v0":      {"ladder_state": "SHADOW",  "grandfathered": False,
                               "note": "superseded by us_importance_v0_pit (W3 look-ahead bug)"},
    "us_importance_v0_pit":  {"ladder_state": "SHADOW",  "grandfathered": False,
                               "note": "W4 PIT-corrected re-backfill; current authoritative challenger"},
    "us_board":              {"ladder_state": "DISPLAY",  "grandfathered": False,
                               "note": "scored surface with retro_grades OOS pass"},
    "track_record":          {"ladder_state": "DISPLAY",  "grandfathered": False,
                               "note": "deep archive 1962-present"},
    "sector_central":        {"ladder_state": "DISPLAY",  "grandfathered": False},
    "oracle":                {"ladder_state": "DISPLAY",  "grandfathered": False},
}

# Synapse tier for each signal family (from config/synapse.yml; display-surfaced families only).
_SYNAPSE_TIER: dict[str, str] = {
    "altdata":               "infrastructure",
    "radar":                 "infrastructure",
    "us_importance_v0":      "infrastructure",
    "us_importance_v0_pit":  "infrastructure",
    "us_board":              "infrastructure",
    "track_record":          "infrastructure",
    "sector_central":        "display",
    "oracle":                "display",
}


def _safe(v: Any) -> Any:
    """Convert numpy/pandas scalars to plain Python; None stays None."""
    if v is None:
        return None
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return None if (v != v) else float(v)  # NaN → None
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except ImportError:
        pass
    if isinstance(v, float) and (v != v):
        return None  # NaN guard without numpy
    return v


def _today_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class ProvenanceContext:
    """Shared data loaded ONCE in main() and passed to each ticker's build_provenance().

    All attributes default to empty / None so a caller that skips loading a
    source gracefully degrades without raising.
    """
    # data/neuralweb/kernel_estimates.parquet — indexed as {(engine, horizon): row}
    kernel: dict[tuple[str, int], dict] = field(default_factory=dict)
    # data/neuralweb/kernel_families.json — {family_name: family_dict}
    kernel_families: dict[str, dict] = field(default_factory=dict)
    # data/neuralweb/spine_index.parquet — filtered to the latest row per (symbol, engine)
    # accessed as spine_latest[ticker][engine] = row_dict
    spine_latest: dict[str, dict[str, dict]] = field(default_factory=dict)
    # data/sector_central/calls.parquet — {(basket_id, date): row}
    sector_calls: pd.DataFrame | None = None
    # data/baskets/membership.json — {basket_id: {"members": [...]}}
    basket_membership: dict[str, list[str]] = field(default_factory=dict)
    # data/altdata/by_ticker.json — {ticker: {...}}
    altdata_by_ticker: dict[str, dict] = field(default_factory=dict)
    # Latest as_of date for sector_central calls
    sector_asof: str | None = None


def load_context(root: Path) -> ProvenanceContext:
    """Load all shared inputs for the provenance sidecar.  Fail-open per source."""
    ctx = ProvenanceContext()

    # 1. Kernel estimates
    ke_path = root / "data" / "neuralweb" / "kernel_estimates.parquet"
    if ke_path.exists():
        try:
            ke = pd.read_parquet(ke_path)
            for _, row in ke[ke["regime"] == "__all__"].iterrows():
                engine = str(row["engine"])
                horizon = int(row["horizon"])
                ctx.kernel[(engine, horizon)] = {
                    "shrunken_ic": _safe(row.get("shrunken_ic")),
                    "wilson_ci_low": _safe(row.get("wilson_ci_low")),
                    "n_eff": _safe(row.get("n_eff")),
                    "armed": bool(row.get("armed")),
                    "reliability": _safe(row.get("reliability")),
                }
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: kernel_estimates load failed (%s)", e)

    # 2. Kernel families
    kf_path = root / "data" / "neuralweb" / "kernel_families.json"
    if kf_path.exists():
        try:
            raw = json.loads(kf_path.read_text())
            ctx.kernel_families = raw.get("families", {})
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: kernel_families load failed (%s)", e)

    # 3. Spine index — latest row per (symbol, engine) for US stocks only
    si_path = root / "data" / "neuralweb" / "spine_index.parquet"
    if si_path.exists():
        try:
            si = pd.read_parquet(si_path, columns=[
                "signal_id", "engine", "family", "ledger", "as_of",
                "symbol", "universe", "horizon", "direction", "score",
                "outcome_excess", "outcome_graded", "graded_at",
            ])
            # Restrict to US entity-level rows (universe vocabulary: us_track_record,
            # qledger, us_1500, us_altdata; excludes cn_stocks, ca_stocks, hk_stocks)
            _US_UNIVERSES = {"us_track_record", "qledger", "us_1500", "us_altdata",
                             "us_stocks", "us_board", ""}
            us = si[si["universe"].isin(_US_UNIVERSES) | si["universe"].isna()]
            us = us[us["symbol"].notna() & (us["symbol"] != "")]
            # Latest row per (symbol, engine) by as_of
            latest_idx = (us.sort_values("as_of", ascending=False)
                           .groupby(["symbol", "engine"])
                           .head(1)
                           .index)
            latest = us.loc[latest_idx]
            for _, row in latest.iterrows():
                sym = str(row["symbol"])
                eng = str(row["engine"])
                if sym not in ctx.spine_latest:
                    ctx.spine_latest[sym] = {}
                ctx.spine_latest[sym][eng] = {
                    "signal_id": str(row["signal_id"]),
                    "engine": eng,
                    "family": str(row["family"]),
                    "ledger": _safe(row.get("ledger")),
                    "as_of": str(row["as_of"]) if row.get("as_of") else None,
                    "horizon": _safe(row.get("horizon")),
                    "direction": _safe(row.get("direction")),
                    "score": _safe(row.get("score")),
                    "outcome_excess": _safe(row.get("outcome_excess")),
                    "outcome_graded": bool(row.get("outcome_graded")),
                    "graded_at": str(row["graded_at"]) if row.get("graded_at") and str(row.get("graded_at")) not in ("nan", "None", "") else None,
                }
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: spine_index load failed (%s)", e)

    # 4. Sector central calls — latest date
    sc_path = root / "data" / "sector_central" / "calls.parquet"
    if sc_path.exists():
        try:
            ctx.sector_calls = pd.read_parquet(sc_path)
            if "date" in ctx.sector_calls.columns:
                ctx.sector_asof = str(ctx.sector_calls["date"].max())
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: sector_calls load failed (%s)", e)

    # 5. Basket membership — membership.json has shape {"baskets": {id: {"members": [...]}}}
    bm_path = root / "data" / "baskets" / "membership.json"
    if bm_path.exists():
        try:
            raw = json.loads(bm_path.read_text())
            # Support both {"baskets": {...}} and flat {basket_id: {...}}
            basket_map = raw.get("baskets") if isinstance(raw.get("baskets"), dict) else raw
            for basket_id, basket_data in basket_map.items():
                if not isinstance(basket_data, dict):
                    continue
                members = [
                    m["ticker"] for m in basket_data.get("members", [])
                    if isinstance(m, dict) and m.get("ticker") and not m.get("removed")
                ]
                ctx.basket_membership[basket_id] = members
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: basket_membership load failed (%s)", e)

    # 6. Altdata by_ticker
    ad_path = root / "data" / "altdata" / "by_ticker.json"
    if ad_path.exists():
        try:
            raw = json.loads(ad_path.read_text())
            # by_ticker.json is {ticker: {...}} or {"tickers": {ticker: {...}}}
            if "tickers" in raw:
                ctx.altdata_by_ticker = raw["tickers"]
            else:
                ctx.altdata_by_ticker = raw
        except Exception as e:  # noqa: BLE001
            log.warning("provenance: altdata by_ticker load failed (%s)", e)

    return ctx


def _kernel_cell(ctx: ProvenanceContext, engine: str, horizon: int | None = None) -> dict:
    """Return kernel cell fields for the given engine+horizon; null fields on miss."""
    if horizon is not None:
        cell = ctx.kernel.get((engine, horizon))
        if cell:
            return dict(cell)
    # Try all horizons for the engine, pick smallest
    for h in [5, 10, 21, 63, 126]:
        cell = ctx.kernel.get((engine, h))
        if cell:
            return dict(cell)
    return {"shrunken_ic": None, "wilson_ci_low": None, "n_eff": None, "armed": None}


def _qual_state(family_key: str) -> dict:
    """Return qual_ladder fields for a family key; empty dict on miss."""
    entry = _QUAL_LADDER.get(family_key, {})
    return {
        "ladder_state": entry.get("ladder_state", "UNKNOWN"),
        "grandfathered": entry.get("grandfathered", False),
        "note": entry.get("note"),
    }


def _staleness_days(as_of_str: str | None) -> int | None:
    """Days since as_of (positive = stale).  None if as_of absent or unparseable."""
    if not as_of_str:
        return None
    try:
        as_of = date.fromisoformat(str(as_of_str)[:10])
        today = date.today()
        return (today - as_of).days
    except Exception:  # noqa: BLE001
        return None


def _spine_row(ctx: ProvenanceContext, ticker: str, engine: str) -> dict | None:
    """Latest spine row for ticker+engine; None if absent."""
    return (ctx.spine_latest.get(ticker) or {}).get(engine)


def build_provenance(
    ticker: str,
    rec: dict,
    ctx: ProvenanceContext,
) -> list[dict]:
    """Build the view.provenance[] list for a US ticker.

    Returns a list of 0–10 provenance rows.  Each row carries:
        claim_source   — which data source this line traces to
        family         — engine family key (spine vocabulary)
        qual_ladder    — {"ladder_state", "grandfathered", "note"} from qual_ladder.yml
        synapse_tier   — tier from synapse.yml (all infrastructure for engine families)
        kernel         — {"shrunken_ic", "wilson_ci_low", "n_eff", "armed"} from kernel_estimates
        spine_ref      — signal_id (spine row ID) where available
        graded_at      — ISO date the claim was graded (if graded)
        staleness_days — days since as_of (for freshness fade)
        as_of          — the date this signal was registered
        direction      — +1 / -1 / 0 (signal direction)
        is_display_only — always true (FDR batch pending until 2026-10-01)
        [source-specific fields]
    """
    rows: list[dict] = []

    try:
        rows.extend(_row_altdata(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance altdata row failed (%s): %s", ticker, e)

    try:
        rows.extend(_row_radar(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance radar row failed (%s): %s", ticker, e)

    try:
        rows.extend(_row_us_board(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance us_board row failed (%s): %s", ticker, e)

    try:
        rows.extend(_row_sector_central(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance sector_central row failed (%s): %s", ticker, e)

    try:
        rows.extend(_row_oracle(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance oracle row failed (%s): %s", ticker, e)

    try:
        rows.extend(_row_fundamentals(ticker, rec, ctx))
    except Exception as e:  # noqa: BLE001
        log.debug("provenance fundamentals row failed (%s): %s", ticker, e)

    return rows


# ---------------------------------------------------------------------------
# Per-source row builders
# ---------------------------------------------------------------------------

def _row_altdata(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """Altdata convergence row."""
    ad = ctx.altdata_by_ticker.get(ticker) or rec.get("altdata_ctx") or {}
    if not ad:
        return []
    conv_score = ad.get("convergence_score") or 0
    if conv_score < 1:
        return []
    spine = _spine_row(ctx, ticker, "altdata")
    kernel = _kernel_cell(ctx, "altdata", horizon=5)
    qual = _qual_state("altdata")
    as_of = (spine or {}).get("as_of") or ad.get("as_of")
    _dir_altdata = _safe((spine or {}).get("direction"))
    return [{
        "claim_source": "altdata",
        "family": "altdata",
        "qual_ladder": qual,
        "synapse_tier": _SYNAPSE_TIER.get("altdata", "infrastructure"),
        "kernel": {
            "shrunken_ic": kernel.get("shrunken_ic"),
            "wilson_ci_low": kernel.get("wilson_ci_low"),
            "n_eff": kernel.get("n_eff"),
            "armed": kernel.get("armed"),
        },
        "spine_ref": (spine or {}).get("signal_id"),
        "graded_at": (spine or {}).get("graded_at"),
        "staleness_days": _staleness_days(as_of),
        "as_of": as_of,
        "direction": _dir_altdata if _dir_altdata is not None else 1,
        "is_display_only": True,
        # source-specific
        "convergence_score": _safe(conv_score),
        "channels": ad.get("channels"),
        "weighted_score": _safe(ad.get("weighted_score")),
        "graded_5d_excess": _safe((spine or {}).get("outcome_excess")),
        "outcome_graded": bool((spine or {}).get("outcome_graded", False)),
    }]


def _row_radar(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """Divergence Radar row."""
    spine = _spine_row(ctx, ticker, "radar")
    if not spine:
        return []
    kernel = _kernel_cell(ctx, "radar", horizon=5)
    qual = _qual_state("radar.edge_score")
    # radar edge state from rec (already assembled in build_stock_library)
    radar_score = None
    radar_state = None
    radar_ctx = rec.get("radar_ctx") or {}
    if radar_ctx:
        radar_score = radar_ctx.get("edge_score")
        radar_state = radar_ctx.get("state")
    _dir_radar = _safe(spine.get("direction"))
    return [{
        "claim_source": "radar",
        "family": "radar",
        "qual_ladder": qual,
        "synapse_tier": _SYNAPSE_TIER.get("radar", "infrastructure"),
        "kernel": {
            "shrunken_ic": kernel.get("shrunken_ic"),
            "wilson_ci_low": kernel.get("wilson_ci_low"),
            "n_eff": kernel.get("n_eff"),
            "armed": kernel.get("armed"),
        },
        "spine_ref": spine.get("signal_id"),
        "graded_at": spine.get("graded_at"),
        "staleness_days": _staleness_days(spine.get("as_of")),
        "as_of": spine.get("as_of"),
        "direction": _dir_radar if _dir_radar is not None else 1,
        "is_display_only": True,
        # source-specific
        "edge_score": _safe(radar_score),
        "state": radar_state,
        "graded_5d_excess": _safe(spine.get("outcome_excess")),
        "outcome_graded": bool(spine.get("outcome_graded", False)),
    }]


def _row_us_board(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """US Board (cycle-ladder) — returns a single provenance row for the ticker."""
    spine = _spine_row(ctx, ticker, "us_board")
    if not spine:
        return []
    kernel = _kernel_cell(ctx, "us_board", horizon=5)
    qual = _qual_state("us_board")
    _dir_us_board = _safe(spine.get("direction"))
    return [{
        "claim_source": "us_board",
        "family": spine.get("family", "us_board:buy"),
        "qual_ladder": qual,
        "synapse_tier": _SYNAPSE_TIER.get("us_board", "infrastructure"),
        "kernel": {
            "shrunken_ic": kernel.get("shrunken_ic"),
            "wilson_ci_low": kernel.get("wilson_ci_low"),
            "n_eff": kernel.get("n_eff"),
            "armed": kernel.get("armed"),
        },
        "spine_ref": spine.get("signal_id"),
        "graded_at": spine.get("graded_at"),
        "staleness_days": _staleness_days(spine.get("as_of")),
        "as_of": spine.get("as_of"),
        "direction": _dir_us_board if _dir_us_board is not None else 1,
        "is_display_only": True,
        # source-specific
        "board_score": _safe(spine.get("score")),
        "outcome_graded": bool(spine.get("outcome_graded", False)),
        "graded_5d_excess": _safe(spine.get("outcome_excess")),
    }]


def _row_sector_central(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """Sector Central call rows — one per basket the ticker is active in."""
    if ctx.sector_calls is None or ctx.basket_membership is None:
        return []
    # Find baskets containing this ticker
    member_baskets = [
        bid for bid, members in ctx.basket_membership.items()
        if ticker in members
    ]
    if not member_baskets:
        return []
    # Get latest sector central calls for those baskets
    sc = ctx.sector_calls
    if "date" not in sc.columns or "basket_id" not in sc.columns:
        return []
    asof = sc["date"].max()
    latest = sc[sc["date"] == asof]
    # Filter to baskets that have a live call row at asof, then rank by score
    # descending, then cap at 4 — prevents arbitrary dict-order silencing a
    # basket with a valid call (e.g. NVDA's us_sector_tech as 5th member).
    live_rows: list[tuple[str, float, object]] = []
    for bid in member_baskets:
        row = latest[latest["basket_id"] == bid]
        if row.empty:
            continue
        r = row.iloc[0]
        score = r.get("score") if r.get("score") is not None else 0
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        live_rows.append((bid, score, r))
    live_rows.sort(key=lambda x: x[1], reverse=True)
    rows = []
    for bid, _score, r in live_rows[:4]:  # cap at 4 after filter+rank
        rows.append({
            "claim_source": f"sector_central:{bid}",
            "family": "sector_central",
            "qual_ladder": _qual_state("sector_central"),
            "synapse_tier": _SYNAPSE_TIER.get("sector_central", "display"),
            "kernel": {"shrunken_ic": None, "wilson_ci_low": None, "n_eff": None, "armed": None},
            "spine_ref": None,
            "graded_at": None,
            "staleness_days": _staleness_days(str(asof)[:10] if asof is not None else None),
            "as_of": str(asof)[:10] if asof is not None else ctx.sector_asof,
            "direction": _safe(1 if str(r.get("dir", "")) in ("up", "bullish") else -1 if str(r.get("dir", "")) in ("down", "bearish") else 0),
            "is_display_only": True,
            # source-specific
            "basket_id": bid,
            "basket_score": _safe(r.get("score")),
            "basket_label": str(r.get("label", "")),
            "basket_dir": str(r.get("dir", "")),
            "confluence": _safe(r.get("confluence")),
        })
    return rows


def _row_oracle(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """Oracle episode row — from basket_alloc in rec."""
    # Oracle episodes are at basket/sector level; we surface the most relevant one
    # from rec["basket_alloc"] which build_stock_library already assembles.
    ba = rec.get("basket_alloc") or {}
    if not ba:
        return []
    # Pick the highest-score basket alloc row that has an oracle_episode field
    best_ep = None
    for _bid, brow in ba.items():
        if isinstance(brow, dict) and brow.get("oracle_episode"):
            ep = brow["oracle_episode"]
            if best_ep is None or (ep.get("outcome_rs_5d") or 0) > (best_ep.get("outcome_rs_5d") or 0):
                best_ep = ep
                best_ep["_basket_id"] = _bid
    if not best_ep:
        return []
    bid = best_ep.get("_basket_id", "")
    ep_direction = best_ep.get("direction", "out")
    return [{
        "claim_source": f"oracle:{bid}",
        "family": "oracle",
        "qual_ladder": _qual_state("oracle"),
        "synapse_tier": _SYNAPSE_TIER.get("oracle", "display"),
        "kernel": {"shrunken_ic": None, "wilson_ci_low": None, "n_eff": None, "armed": None},
        "spine_ref": None,
        "graded_at": None,
        "staleness_days": _staleness_days(best_ep.get("onset")),
        "as_of": best_ep.get("onset"),
        "direction": 1 if ep_direction == "in" else -1,
        "is_display_only": True,
        # source-specific
        "basket_id": bid,
        "episode_direction": ep_direction,
        "onset": best_ep.get("onset"),
        "confirmed": best_ep.get("confirmed"),
        "outcome_rs_5d": _safe(best_ep.get("outcome_rs_5d")),
    }]


def _row_fundamentals(ticker: str, rec: dict, ctx: ProvenanceContext) -> list[dict]:
    """Fundamentals snapshot row — from rec["fundamentals"] if present."""
    fund = rec.get("fundamentals") or {}
    if not fund:
        return []
    as_of = fund.get("as_of")
    return [{
        "claim_source": "fundamentals",
        "family": "fundamentals",
        "qual_ladder": {"ladder_state": "DISPLAY", "grandfathered": False, "note": "display-only snapshot"},
        "synapse_tier": "infrastructure",
        "kernel": {"shrunken_ic": None, "wilson_ci_low": None, "n_eff": None, "armed": None},
        "spine_ref": None,
        "graded_at": None,
        "staleness_days": _staleness_days(as_of),
        "as_of": as_of,
        "direction": None,
        "is_display_only": True,
        # source-specific
        "fwd_pe": _safe(fund.get("fwd_pe")),
        "pe": _safe(fund.get("pe")),
        "profit_margin": _safe(fund.get("profit_margin")),
        "rev_growth": _safe(fund.get("rev_growth")),
        "mkt_cap": _safe(fund.get("mkt_cap")),
    }]
