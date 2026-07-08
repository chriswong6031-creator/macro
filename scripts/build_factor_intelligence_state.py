"""scripts/build_factor_intelligence_state.py — Factor Intelligence state artifact builder.

PURPOSE
-------
Builds and commits the NW integration state artifact for factor intelligence.
Runs INSIDE the factor_panel job (the only tree where data/factordata/panel/ exists).
Implements §D PR-1 under rulings RUL-NW1, RUL-NW9, RUL-NW10, RUL-NW11, RUL-NW12.

FAIL-OPEN CONTRACT
------------------
Never raises. Every missing input appends a structured note to the gaps list.
Always writes the state artifact even on total failure (partial payload with all-null
blocks and a populated gaps list).

OUTPUTS
-------
1. data/neuralweb/factor_intelligence_state.json
   Schema: neuralweb.factor_intelligence_state.v1
2. site/neuralwebdata/factor_intelligence_state.json  (byte-identical mirror)
3. data/factordata/factor_state_history.jsonl  (append-only daily digest, idempotent)
4. data/factordata/fire_coordinates.jsonl  (append-only per-fire, idempotent on (as_of, ticker))

DISPLAY-ONLY LAW
----------------
- is_context_only: true, display_only: true at top level.
- allowed_actions hard-codes may_rank=false, may_originate=false, may_deescalate=false.
- No rank/score/recommendation fields anywhere.
- The CI-enforced validation word never appears in any string.

USAGE
-----
  python -m scripts.build_factor_intelligence_state [--root PATH] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA = "neuralweb.factor_intelligence_state.v1"
# R-CI2a fix: real panel columns are contrib_<stream>_20d (e.g. contrib_mkt_20d,
# contrib_sector_20d) — NOT contrib_20d_<stream>.  Use a regex to match the correct
# shape and extract the stream name between 'contrib_' and '_20d'.
_CONTRIB_PATTERN = re.compile(r"^contrib_([a-z_]+)_20d$")
_TOP_CONTRIB_N = 3

# Personality JSON path (same-night snapshot, snapshot_fresh basis per R-CI3)
def _personality_path(repo: Path) -> Path:
    return repo / "site" / "factordata" / "stock_personality.json"


def _load_personality_index(repo: Path) -> dict[str, dict]:
    """Load per_ticker personality dict from stock_personality.json. Fail-open → {}."""
    try:
        p = _personality_path(repo)
        if not p.exists():
            return {}
        raw = json.loads(p.read_text(encoding="utf-8"))
        pt = raw.get("per_ticker")
        if isinstance(pt, dict):
            return pt
        return {}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# JSON-safety helpers (mirrors factor_contradictions.py convention)
# ---------------------------------------------------------------------------

def _json_safe(obj: Any) -> Any:
    """Recursively convert numpy scalars/NaN/Inf to JSON-safe Python types."""
    try:
        import numpy as np  # noqa: PLC0415
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [_json_safe(x) for x in obj.tolist()]
    except ImportError:
        pass
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return obj


def _dumps_safe(obj: Any) -> str:
    return json.dumps(_json_safe(obj), allow_nan=False)


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("build_factor_intelligence_state: unreadable json %s — %s", p, exc)
        return None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _panel_dir(repo: Path) -> Path:
    return repo / "data" / "factordata" / "panel"

def _scorecard_path(repo: Path) -> Path:
    return repo / "data" / "edgar" / "ic_scorecard.json"

def _contradictions_path(repo: Path) -> Path:
    return repo / "data" / "neuralweb" / "factor_contradictions.jsonl"

def _firings_path(repo: Path) -> Path:
    return repo / "data" / "reflexes" / "factor_attention" / "firings.jsonl"

def _grades_path(repo: Path) -> Path:
    return repo / "data" / "reflexes" / "factor_attention" / "grades.jsonl"

def _probation_path(repo: Path) -> Path:
    return repo / "data" / "reflexes" / "factor_attention" / "probation.json"

def _machine_registry_path(repo: Path) -> Path:
    return repo / "data" / "neuralweb" / "machine_registry.jsonl"

def _standouts_path(repo: Path) -> Path:
    return repo / "site" / "factordata" / "us_standouts.json"

def _state_data_path(repo: Path) -> Path:
    return repo / "data" / "neuralweb" / "factor_intelligence_state.json"

def _state_site_path(repo: Path) -> Path:
    return repo / "site" / "neuralwebdata" / "factor_intelligence_state.json"

def _history_path(repo: Path) -> Path:
    return repo / "data" / "factordata" / "factor_state_history.jsonl"

def _fire_coords_path(repo: Path) -> Path:
    return repo / "data" / "factordata" / "fire_coordinates.jsonl"


# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------

def _load_panel_full(panel_dir: Path, as_of_date: str, gaps: list[str]) -> "Any | None":
    """Load full panel (all columns) for dates <= as_of_date. Returns DataFrame or None."""
    try:
        import pandas as pd  # noqa: PLC0415
        if not panel_dir.exists():
            return None
        as_of_month = as_of_date[:7]
        parts = sorted(panel_dir.glob("*/panel.parquet"))
        if not parts:
            return None
        dfs = []
        for p in parts:
            if p.parent.name > as_of_month:
                continue
            try:
                dfs.append(pd.read_parquet(p))
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"panel partition {p.name}: {exc}")
        if not dfs:
            return None
        combined = pd.concat(dfs, ignore_index=True)
        return combined[combined["date"] <= as_of_date]
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"panel load failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Panel info block
# ---------------------------------------------------------------------------

def _build_panel_block(panel_df: "Any | None", as_of_date: str, gaps: list[str]) -> dict[str, Any]:
    _empty = {
        "available": False, "n_partitions": None, "n_dates": None,
        "latest_date": None, "history_floor_met": False, "n_tickers_latest": None,
        "storage": "runner-local-panel-plus-committed-summary", "gaps": [],
    }
    if panel_df is None or (hasattr(panel_df, "empty") and panel_df.empty):
        return _empty
    try:
        n_dates = int(panel_df["date"].nunique())
        latest_date = str(panel_df["date"].max())
        n_tickers_latest = int(panel_df[panel_df["date"] == latest_date]["ticker"].nunique())
        return {
            "available": True, "n_partitions": None, "n_dates": n_dates,
            "latest_date": latest_date, "history_floor_met": n_dates >= 60,
            "n_tickers_latest": n_tickers_latest,
            "storage": "runner-local-panel-plus-committed-summary", "gaps": [],
        }
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"panel block build failed: {exc}")
        return {**_empty, "available": True}


# ---------------------------------------------------------------------------
# Scorecard block
# ---------------------------------------------------------------------------

def _build_scorecard_block(repo: Path, gaps: list[str]) -> dict[str, Any]:
    _note = "Scorecard is an optimistic survivorship-biased bound; not a buy list."
    _empty = {"span": None, "rebalances": None, "survivors": [], "negative_ic_legs": [],
               "composite_tradeable": False, "note": _note}
    p = _scorecard_path(repo)
    if not p.exists():
        gaps.append("data/edgar/ic_scorecard.json: absent")
        return _empty
    try:
        sc = _read_json(p)
        if not isinstance(sc, dict):
            gaps.append("data/edgar/ic_scorecard.json: unreadable")
            return _empty
        survivors, negative_ic_legs = [], []
        for fname, fdata in (sc.get("factors") or {}).items():
            if not isinstance(fdata, dict):
                continue
            mean_ic = fdata.get("mean_ic")
            if fdata.get("fdr_passed") or fdata.get("bh_fdr_passed"):
                survivors.append(fname)
            elif mean_ic is not None:
                try:
                    if float(mean_ic) < 0:
                        negative_ic_legs.append(fname)
                except (TypeError, ValueError):
                    pass
        return {
            "span": sc.get("span"), "rebalances": sc.get("rebalances"),
            "survivors": survivors, "negative_ic_legs": negative_ic_legs,
            "composite_tradeable": bool(sc.get("composite_tradeable", False)),
            "note": _note,
        }
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"scorecard build failed: {exc}")
        return _empty


# ---------------------------------------------------------------------------
# Factor weather block (reuse _compose_factor_weather from world_state)
# ---------------------------------------------------------------------------

def _build_factor_weather_block(repo: Path, gaps: list[str]) -> dict[str, Any]:
    """Call _compose_factor_weather from engine.neuralweb.world_state (RUL-NW2 reuse).

    IMPORTANT: always passes prefer_artifact=False so the builder recomputes
    factor_weather fresh from the panel on every run, rather than reading and
    re-emitting the prior night's committed artifact verbatim.  The artifact
    path (prefer_artifact=True, the default) is intentionally reserved for the
    world_state lobe which consumes the committed state as its canonical source
    (RUL-NW2).  Using the default here would freeze style_regime, factor_leader,
    factor_leader_ic, and ETF ratios at day-1 values forever — the circular-
    staleness freeze caught during Opus review of PR-2.
    """
    try:
        from engine.neuralweb.world_state import _compose_factor_weather  # type: ignore[import]
        result = _compose_factor_weather(root=repo, prefer_artifact=False)
        return result if isinstance(result, dict) else {}
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"factor_weather: _compose_factor_weather failed: {exc}")
        return {
            "style_regime": None, "style_regime_pending": None,
            "style_regime_hold_days": None, "factor_leader": None,
            "factor_leader_ic": None, "etf_pulse_summary": None,
            "ratio_iwf_iwd_20d": None, "ratio_qqq_spy_20d": None,
            "ratio_iwm_spy_20d": None, "display_only": True,
        }


# ---------------------------------------------------------------------------
# Contradictions block
# ---------------------------------------------------------------------------

def _build_contradictions_block(repo: Path, as_of_date: str, gaps: list[str]) -> dict[str, Any]:
    _dormant = {"pair_g": {"dormant": True, "n_today": 0, "latest": []}}
    p = _contradictions_path(repo)
    if not p.exists():
        return _dormant
    try:
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        today_rows = [r for r in rows if r.get("date") == as_of_date or r.get("as_of") == as_of_date]
        n_today = len(today_rows)
        latest = []
        for r in today_rows[:5]:
            b_reading = (r.get("b") or {}).get("reading", "")
            alibi_val = q80_val = None
            try:
                m_a = re.search(r"alibi_share_20d=([\d.]+)", b_reading)
                m_q = re.search(r"Q80=([\d.]+)", b_reading)
                if m_a:
                    alibi_val = float(m_a.group(1))
                if m_q:
                    q80_val = float(m_q.group(1))
            except Exception:  # noqa: BLE001
                pass
            latest.append({
                "ticker": r.get("ticker"), "pair_id": r.get("pair_id"),
                "severity": r.get("severity"), "alibi_share_20d": alibi_val,
                "q80": q80_val, "display_only": True,
            })
        return {"pair_g": {"dormant": n_today == 0, "n_today": n_today, "latest": latest}}
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"contradictions block failed: {exc}")
        return _dormant


# ---------------------------------------------------------------------------
# Attention block
# ---------------------------------------------------------------------------

def _build_attention_block(repo: Path, gaps: list[str]) -> dict[str, Any]:
    n_firings, n_graded = 0, 0
    granted, tier, reason = False, "A0/A1 shadow", "insufficient-n"
    latest_firings: list[dict] = []
    try:
        fp = _firings_path(repo)
        if fp.exists():
            firings = []
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    firings.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
            n_firings = len(firings)
            for f in firings[-3:]:
                latest_firings.append({
                    "trigger_key": f.get("trigger_key"),
                    "asof": f.get("asof"), "scope_key": f.get("scope_key"),
                })
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"factor_attention firings read failed: {exc}")
    try:
        gp = _grades_path(repo)
        if gp.exists():
            n_graded = sum(1 for l in gp.read_text(encoding="utf-8").splitlines() if l.strip())
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"factor_attention grades read failed: {exc}")
    try:
        pp = _probation_path(repo)
        if pp.exists():
            prob = _read_json(pp)
            if isinstance(prob, dict):
                granted = bool(prob.get("granted", False))
                tier = str(prob.get("tier", tier))
                reason = str(prob.get("reason", reason))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"factor_attention probation read failed: {exc}")
    return {"factor_attention": {
        "n_firings": n_firings, "n_graded": n_graded, "granted": granted,
        "tier": tier, "reason": reason, "latest_firings": latest_firings,
    }}


# ---------------------------------------------------------------------------
# Hypotheses block
# ---------------------------------------------------------------------------

def _build_hypotheses_block(repo: Path, gaps: list[str]) -> dict[str, Any]:
    _not_visible = {f"h{i}": {"status": "not-visible-in-tree", "authority": "display"} for i in range(1, 6)}
    reg_p = _machine_registry_path(repo)
    if not reg_p.exists():
        return _not_visible
    try:
        registry_rows: list[dict] = []
        for line in reg_p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                registry_rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
        h_map: dict[str, dict] = {}
        for row in registry_rows:
            hyp_id = str(row.get("id") or row.get("hypothesis_id") or "").lower()
            hyp_text = (row.get("hypothesis") or "").lower()
            claim_shape = (row.get("claim_shape") or "").lower()
            for i in range(1, 6):
                tag = f"factor_h{i}"
                if tag in hyp_id or f"h{i}" == hyp_id or tag in hyp_text or tag in claim_shape:
                    h_map[f"h{i}"] = {
                        "status": row.get("status", "registered"),
                        "authority": "display",
                        "registered_at": row.get("registered_at"),
                    }
        return {f"h{i}": h_map.get(f"h{i}", {"status": "not-visible-in-tree", "authority": "display"}) for i in range(1, 6)}
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"hypotheses block failed: {exc}")
        return _not_visible


# ---------------------------------------------------------------------------
# Panel row accessor
# ---------------------------------------------------------------------------

def _get_row_col(row: Any, col: str) -> Any:
    try:
        if hasattr(row, "get"):
            return row.get(col)
        if hasattr(row, "index") and col in row.index:
            return row[col]
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Latest board coordinates block
# ---------------------------------------------------------------------------

def _build_board_coordinates(
    repo: Path, panel_df: "Any | None", as_of_date: str, gaps: list[str],
) -> list[dict[str, Any]]:
    standouts_p = _standouts_path(repo)
    if not standouts_p.exists():
        gaps.append("site/factordata/us_standouts.json: absent — board coordinates empty")
        return []
    try:
        raw = _read_json(standouts_p)
        if not isinstance(raw, dict):
            gaps.append("us_standouts.json: unreadable")
            return []
        buy_lane: list[dict] = raw.get("buy") or []
        board_as_of = str(raw.get("as_of") or as_of_date)
        if panel_df is None or (hasattr(panel_df, "empty") and panel_df.empty):
            if buy_lane:
                gaps.append(f"latest_board_coordinates: panel absent — {len(buy_lane)} buy-lane tickers skipped")
            return []
        coords, missing = [], []
        for entry in buy_lane:
            ticker = str(entry.get("ticker") or "")
            if not ticker:
                continue
            tier = (entry.get("signal") or {}).get("tier_cascade")
            try:
                panel_pit = panel_df[panel_df["date"] <= board_as_of]
                ticker_rows = panel_pit[panel_pit["ticker"] == ticker]
                if hasattr(ticker_rows, "empty") and ticker_rows.empty:
                    missing.append(ticker)
                    continue
                row = ticker_rows[ticker_rows["date"] == ticker_rows["date"].max()].iloc[0]
                coords.append({
                    "ticker": ticker, "tier": tier,
                    "panel_date": str(ticker_rows["date"].max()),
                    "dna_class": _json_safe(_get_row_col(row, "dna_class")),
                    "style_regime": _json_safe(_get_row_col(row, "style_regime")),
                    "alibi_share_20d": _json_safe(_get_row_col(row, "alibi_share_20d")),
                    "twin_bleed_flag": _json_safe(_get_row_col(row, "twin_bleed_flag")),
                    "twin_rel_20d": _json_safe(_get_row_col(row, "twin_rel_20d")),
                    "alpha_z_house": _json_safe(_get_row_col(row, "alpha_z_house")),
                })
            except Exception as exc:  # noqa: BLE001
                missing.append(ticker)
                log.debug("board_coordinates: failed for %s — %s", ticker, exc)
        if missing:
            gaps.append(
                f"latest_board_coordinates: {len(missing)} tickers missing from panel at {board_as_of}: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
            )
        return coords
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"board_coordinates block failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Allowed actions block (RUL-NW9)
# ---------------------------------------------------------------------------

def _build_allowed_actions() -> dict[str, Any]:
    return {
        "may_explain": True, "may_flag_attention": True,
        "may_deescalate": False, "may_rank": False, "may_originate": False,
        "authority_source": (
            "constitution.grant_authority + prereg gates; "
            "this block is a mirror, never a switch"
        ),
    }


# ---------------------------------------------------------------------------
# History digest row (RUL-NW10)
# ---------------------------------------------------------------------------

def _build_history_digest(
    panel_df: "Any | None",
    factor_weather: dict[str, Any],
    contradictions_block: dict[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    panel_n_dates = panel_n_tickers_latest = panel_latest_date = None
    alibi_cross_median = alibi_cross_q80 = None
    dna_distribution: dict[str, int] = {}
    if panel_df is not None and not (hasattr(panel_df, "empty") and panel_df.empty):
        try:
            panel_n_dates = int(panel_df["date"].nunique())
            panel_latest_date = str(panel_df["date"].max())
            latest_rows = panel_df[panel_df["date"] == panel_latest_date]
            panel_n_tickers_latest = int(latest_rows["ticker"].nunique())
            if "alibi_share_20d" in panel_df.columns:
                a = latest_rows["alibi_share_20d"].dropna()
                if len(a) > 0:
                    alibi_cross_median = _json_safe(float(a.median()))
                    alibi_cross_q80 = _json_safe(float(a.quantile(0.80)))
            if "dna_class" in panel_df.columns:
                for cls, cnt in latest_rows["dna_class"].value_counts().items():
                    dna_distribution[str(cls)] = int(cnt)
        except Exception as exc:  # noqa: BLE001
            log.warning("history digest panel stats failed — %s", exc)
    pair_g = contradictions_block.get("pair_g") or {}
    return {
        "as_of": as_of_date,
        "style_regime": factor_weather.get("style_regime"),
        "style_regime_pending": factor_weather.get("style_regime_pending"),
        "style_regime_hold_days": factor_weather.get("style_regime_hold_days"),
        "factor_leader": factor_weather.get("factor_leader"),
        "factor_leader_ic": factor_weather.get("factor_leader_ic"),
        "ratio_iwf_iwd_20d": factor_weather.get("ratio_iwf_iwd_20d"),
        "ratio_qqq_spy_20d": factor_weather.get("ratio_qqq_spy_20d"),
        "ratio_iwm_spy_20d": factor_weather.get("ratio_iwm_spy_20d"),
        "panel_n_dates": panel_n_dates,
        "panel_n_tickers_latest": panel_n_tickers_latest,
        "panel_latest_date": panel_latest_date,
        "pair_g_n_today": pair_g.get("n_today", 0),
        "alibi_cross_median": alibi_cross_median,
        "alibi_cross_q80": alibi_cross_q80,
        "dna_distribution": dna_distribution,
    }


# ---------------------------------------------------------------------------
# Fire coordinates builder (RUL-NW10)
# ---------------------------------------------------------------------------

def _build_fire_coordinates(
    repo: Path, panel_df: "Any | None", as_of_date: str, gaps: list[str],
) -> list[dict[str, Any]]:
    """Build fire_coordinates rows — PIT: carry-forward panel row for each ticker
    at or before standouts as_of date (schema v2, additive personality+regime coords).

    R-CI2a fix: contrib columns are contrib_<stream>_20d not contrib_20d_<stream>.
    R-CI2b fix: use carry-forward (date <= board_as_of) not exact-date match, so
      rows are found even when the panel's latest date lags behind the board as_of.
    R-CI3: personality coordinates are from the same-night snapshot (snapshot_fresh
      basis); regime coordinates from _regime_stamp_for_asof.
    """
    standouts_p = _standouts_path(repo)
    if not standouts_p.exists():
        return []
    try:
        raw = _read_json(standouts_p)
        if not isinstance(raw, dict):
            return []
        buy_lane: list[dict] = raw.get("buy") or []
        board_as_of = str(raw.get("as_of") or as_of_date)
        if panel_df is None or (hasattr(panel_df, "empty") and panel_df.empty):
            if buy_lane:
                gaps.append(f"fire_coordinates: panel absent — {len(buy_lane)} buy-lane tickers skipped")
            return []

        # R-CI3: load personality snapshot once for this run
        personality_index = _load_personality_index(repo)

        # R-CI3: load regime stamp for board_as_of once
        regime_stamp: dict[str, Any] = {}
        try:
            from engine.qledger import _regime_stamp_for_asof  # noqa: PLC0415
            regime_stamp = _regime_stamp_for_asof(board_as_of)
        except Exception:  # noqa: BLE001
            pass

        # Pre-compute: identify contrib_*_20d columns ONCE (R-CI2a fix)
        # Real column pattern: contrib_<stream>_20d (e.g. contrib_mkt_20d)
        contrib_cols = [c for c in panel_df.columns if _CONTRIB_PATTERN.match(c)]

        # Pre-build a PIT panel view: only dates <= board_as_of
        panel_pit = panel_df[panel_df["date"] <= board_as_of]

        # Heartbeat diagnostic: log non-null rates per run (R-CI12)
        _fire_coord_diagnostics(panel_pit, contrib_cols)

        coords, agg_gaps = [], []
        null_tier_skipped = 0
        for entry in buy_lane:
            ticker = str(entry.get("ticker") or "")
            if not ticker:
                continue
            tier = (entry.get("signal") or {}).get("tier_cascade")
            # B2: only record fire_coordinates rows for entries the gate actually emitted
            # (tier_cascade is not None).  held/topped names (tier_cascade=null / eligible=false)
            # are buy-lane entries but NOT fires — recording them would pollute the fire tape.
            if tier is None:
                null_tier_skipped += 1
                continue
            try:
                # R-CI2b fix: carry-forward — find latest panel row for this ticker at
                # or before board_as_of (not exact-date match which fails when panel lags).
                ticker_pit = panel_pit[panel_pit["ticker"] == ticker]
                if hasattr(ticker_pit, "empty") and ticker_pit.empty:
                    agg_gaps.append(ticker)
                    continue
                panel_date = str(ticker_pit["date"].max())
                row = ticker_pit[ticker_pit["date"] == panel_date].iloc[0]

                # R-CI2a fix: extract stream name between 'contrib_' and '_20d'
                top_contrib: list[str] = []
                try:
                    if contrib_cols:
                        cv: dict[str, float] = {}
                        for c in contrib_cols:
                            v = _get_row_col(row, c)
                            if v is not None:
                                try:
                                    fv = float(v)
                                    if not (math.isnan(fv) or math.isinf(fv)):
                                        m = _CONTRIB_PATTERN.match(c)
                                        if m:
                                            cv[m.group(1)] = abs(fv)
                                except (TypeError, ValueError):
                                    pass
                        top_contrib = sorted(cv, key=lambda k: cv[k], reverse=True)[:_TOP_CONTRIB_N]
                except Exception:  # noqa: BLE001
                    pass

                # R-CI3: personality coordinates (snapshot_fresh basis — same-night snapshot)
                # personality_basis vocabulary:
                #   'snapshot_fresh' — joined from the same-night snapshot (PIT-equivalent
                #                      for today's fires; snapshot produced the same nightly run)
                #   'absent'         — ticker not present in snapshot
                pdata = personality_index.get(ticker, {})
                if pdata:
                    personality_basis = "snapshot_fresh"
                    arch = pdata.get("arch")
                    chart_primary = pdata.get("chart") or []
                    micro_primary = pdata.get("micro") or []
                    modes = pdata.get("modes") or []
                else:
                    personality_basis = "absent"
                    arch = chart_primary = micro_primary = modes = None

                coords.append({
                    # v1 fields (preserved)
                    "as_of": board_as_of, "ticker": ticker, "tier": tier,
                    "panel_date": panel_date,
                    "dna_class": _json_safe(_get_row_col(row, "dna_class")),
                    "style_regime": _json_safe(_get_row_col(row, "style_regime")),
                    "alibi_share_20d": _json_safe(_get_row_col(row, "alibi_share_20d")),
                    "twin_bleed_flag": _json_safe(_get_row_col(row, "twin_bleed_flag")),
                    "twin_rel_20d": _json_safe(_get_row_col(row, "twin_rel_20d")),
                    "alpha_z_house": _json_safe(_get_row_col(row, "alpha_z_house")),
                    "top_contrib_streams": top_contrib, "factor_model": "v1",
                    # v2 additive: personality coordinates (R-CI3)
                    "archetype": arch,
                    "chart_primary": chart_primary,
                    "micro_primary": micro_primary,
                    "modes": modes,
                    "personality_basis": personality_basis,
                    # v2 additive: regime coordinates (R-CI3)
                    "quad_hard_label": regime_stamp.get("quad_hard_label"),
                    "vol_regime": regime_stamp.get("vol_regime"),
                    "risk_radar_state": regime_stamp.get("risk_radar_state"),
                    "rate_pressure": regime_stamp.get("rate_pressure"),
                    "fused_risk_label": regime_stamp.get("fused_risk_label"),
                    "vector_asof": regime_stamp.get("vector_asof"),
                    "fire_coord_schema": "fire_coordinates.v2",
                })
            except Exception as exc:  # noqa: BLE001
                agg_gaps.append(ticker)
                log.debug("fire_coordinates: failed for %s — %s", ticker, exc)
        if null_tier_skipped:
            gaps.append(
                f"fire_coordinates: {null_tier_skipped} buy-lane entries skipped "
                f"(tier_cascade=null — held/topped, not fires)"
            )
        if agg_gaps:
            gaps.append(
                f"fire_coordinates: {len(agg_gaps)} tickers had no panel row at {board_as_of}: "
                f"{agg_gaps[:5]}{'...' if len(agg_gaps) > 5 else ''}"
            )
        return coords
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"fire_coordinates build failed: {exc}")
        return []


def _fire_coord_diagnostics(panel_pit: "Any", contrib_cols: list[str]) -> None:
    """R-CI12 heartbeat diagnostic: log non-null rates for key columns per run.

    Printed to the INFO log so operators can confirm enrichment is working.
    Fail-open: any exception is swallowed.
    """
    try:
        if panel_pit is None or (hasattr(panel_pit, "empty") and panel_pit.empty):
            log.info("fire_coordinates diagnostics: panel_pit empty, skipping")
            return
        n_rows = len(panel_pit)
        if n_rows == 0:
            return
        for col in ("dna_class", "style_regime"):
            if col in panel_pit.columns:
                nonnull = int(panel_pit[col].notna().sum())
                pct = round(100 * nonnull / n_rows, 1)
                log.info("fire_coordinates diagnostics: %s non-null %d/%d (%.1f%%)", col, nonnull, n_rows, pct)
            else:
                log.info("fire_coordinates diagnostics: %s column ABSENT from panel_pit", col)
        n_contrib = len(contrib_cols)
        log.info("fire_coordinates diagnostics: contrib_*_20d cols found: %d %s",
                 n_contrib, contrib_cols[:4])
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Append-only JSONL helpers (idempotent)
# ---------------------------------------------------------------------------

def _load_jsonl_as_of_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                as_of = str(json.loads(line).get("as_of") or "")
                if as_of:
                    keys.add(as_of)
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load as_of keys from %s — %s", path, exc)
    return keys


def _load_jsonl_ticker_keys(path: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not path.exists():
        return keys
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                as_of = str(rec.get("as_of") or "")
                ticker = str(rec.get("ticker") or "")
                if as_of and ticker:
                    keys.add((as_of, ticker))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load ticker keys from %s — %s", path, exc)
    return keys


def _append_jsonl_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_dumps_safe(row) + "\n")


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_factor_intelligence_state(
    root: Path | str | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Build the factor intelligence state artifact. Always returns a dict, never raises."""
    repo = _repo_root(root)
    gaps: list[str] = []

    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date().isoformat()
    produced_at = datetime.now(timezone.utc).isoformat()

    log.info("build_factor_intelligence_state: as_of=%s", as_of_date)

    # Load panel
    panel_df = _load_panel_full(_panel_dir(repo), as_of_date, gaps)
    if panel_df is None or (hasattr(panel_df, "empty") and panel_df.empty):
        gaps.append("data/factordata/panel/: absent or empty — operating in no-panel mode")
        log.info("build_factor_intelligence_state: no panel — honest gaps mode")

    # Build sub-blocks — ALL gap-producing work (including coordinates) runs BEFORE
    # state serialization and before the history digest gaps_count is computed (B1).
    panel_block = _build_panel_block(panel_df, as_of_date, gaps)
    scorecard_block = _build_scorecard_block(repo, gaps)
    factor_weather = _build_factor_weather_block(repo, gaps)
    contradictions_block = _build_contradictions_block(repo, as_of_date, gaps)
    attention_block = _build_attention_block(repo, gaps)
    hypotheses_block = _build_hypotheses_block(repo, gaps)
    allowed_actions = _build_allowed_actions()
    board_coordinates = _build_board_coordinates(repo, panel_df, as_of_date, gaps)

    # Build fire_coordinates BEFORE serialization so any gap notes it appends
    # (e.g. "fire_coordinates: panel absent — N buy-lane tickers skipped") are
    # captured in the state artifact and in the history digest's gaps_count (B1).
    fire_coords_path = _fire_coords_path(repo)
    fire_rows_pending: list[dict[str, Any]] = []
    try:
        fire_rows_pending = _build_fire_coordinates(repo, panel_df, as_of_date, gaps)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_factor_intelligence_state: fire_coordinates build failed — %s", exc)

    state: dict[str, Any] = {
        "schema": _SCHEMA,
        "as_of": as_of_date,
        "produced_at": produced_at,
        "is_context_only": True,
        "display_only": True,
        "panel": panel_block,
        "scorecard": scorecard_block,
        "factor_weather": factor_weather,
        "contradictions": contradictions_block,
        "attention": attention_block,
        "hypotheses": hypotheses_block,
        "latest_board_coordinates": board_coordinates,
        "allowed_actions": allowed_actions,
        "gaps": gaps,
    }

    # Write state artifact to data/ and site/ (byte-identical mirror)
    data_path = _state_data_path(repo)
    site_path = _state_site_path(repo)
    try:
        payload_str = _dumps_safe(state) + "\n"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(payload_str, encoding="utf-8")
        site_path.parent.mkdir(parents=True, exist_ok=True)
        site_path.write_text(payload_str, encoding="utf-8")
        log.info("build_factor_intelligence_state: wrote state artifact")
    except Exception as exc:  # noqa: BLE001
        log.error("build_factor_intelligence_state: FAILED to write state artifact — %s", exc)

    # Append history digest (idempotent on as_of) — gaps_count uses the FINAL gaps
    # list (after fire_coordinates ran above), so it matches the persisted artifact (B1).
    history_path = _history_path(repo)
    try:
        if as_of_date not in _load_jsonl_as_of_keys(history_path):
            digest = _build_history_digest(panel_df, factor_weather, contradictions_block, as_of_date)
            digest["gaps_count"] = len(gaps)
            _append_jsonl_row(history_path, digest)
            log.info("build_factor_intelligence_state: appended history digest for %s", as_of_date)
        else:
            log.info("build_factor_intelligence_state: history digest already present for %s", as_of_date)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_factor_intelligence_state: history append failed — %s", exc)

    # Persist fire coordinates (idempotent on (as_of, ticker)) — rows already built above (B1).
    try:
        if fire_rows_pending:
            existing_keys = _load_jsonl_ticker_keys(fire_coords_path)
            n_written = 0
            for row in fire_rows_pending:
                key = (str(row.get("as_of") or ""), str(row.get("ticker") or ""))
                if key not in existing_keys:
                    _append_jsonl_row(fire_coords_path, row)
                    n_written += 1
            log.info(
                "build_factor_intelligence_state: wrote %d/%d fire coordinates for %s",
                n_written, len(fire_rows_pending), as_of_date,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("build_factor_intelligence_state: fire_coordinates append failed — %s", exc)

    return state


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [build_factor_intelligence_state] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Build factor intelligence state artifact (NW integration W1 PR-1)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--as-of", default=None, dest="as_of", help="ISO date YYYY-MM-DD")
    args = parser.parse_args()
    state = build_factor_intelligence_state(root=args.root, as_of_date=args.as_of)
    gaps = state.get("gaps") or []
    print(_dumps_safe({
        "status": "ok",
        "as_of": state.get("as_of"),
        "panel_available": (state.get("panel") or {}).get("available", False),
        "gaps_count": len(gaps),
        "gaps": gaps,
    }))


if __name__ == "__main__":
    _main()
