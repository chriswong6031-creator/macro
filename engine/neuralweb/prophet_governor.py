"""engine.neuralweb.prophet_governor — Prophet NW lobe: cross-market governor.

PR-W2 (Prophet program, Fable ruling PR-R1/R4/R5/R6/R10).

Produces TWO committed artifacts (single writer, never-raise per input, freshness
stamp, lib.procutil.hard_exit() at end since it reads parquet):

  A. data/neuralweb/prophet_status.json    (schema prophet.status/v1)
  B. data/neuralweb/prophet_suggestions.json  (schema prophet.suggestions/v1)

NEVER-RAISE CONTRACT: every per-market block catches all exceptions and returns
a data_gap entry.  A market failure never aborts the others.

CROSS-MARKET HONESTY (PR-R5 hard law): no pooled return statistics across fill
conventions.  Each market block carries its own benchmark, fill_basis, ledger_born,
and data_gaps.  The cross_market block contains counts/coverage/process-fault rates
ONLY — no excess/return keys.  Test-enforced.

COMMITTED STORES ONLY (SA-R15): absent store => data_gap entry, NEVER fabricated
zeros.

Entry points:
  build_status(root=None)       -> dict (prophet.status/v1)
  build_suggestions(status)     -> list[dict] (suggestion rows)
  build_and_write(root=None)    -> {"status_path": ..., "suggestions_path": ...}

Run as module: python -m engine.neuralweb.prophet_governor
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema identity
# ---------------------------------------------------------------------------
SCHEMA_STATUS = "prophet.status/v1"
SCHEMA_SUGGESTIONS = "prophet.suggestions/v1"

# Artifact paths relative to repo root
_STATUS_PATH = Path("data") / "neuralweb" / "prophet_status.json"
_SUGGESTIONS_PATH = Path("data") / "neuralweb" / "prophet_suggestions.json"

# Insight bus emitter id
_EMITTER = "prophet_governor"

# Public display labels per market (en, zh).
# Internal keys (us/cn/hk/ca/intl) and all file paths are UNCHANGED.
_PROPHET_MARKET_LABEL: dict[str, tuple[str, str]] = {
    "us":   ("Prophet US",    "先知美股"),
    "cn":   ("Prophet China", "先知A股"),
    "hk":   ("Prophet HK",   "先知港股"),
    "ca":   ("Prophet CA",   "先知加股"),
    "intl": ("Prophet Intl", "先知国际"),
}

# Suggestion constraints (mirrors mastermind_feedback.py)
_MAX_SUGGESTIONS = 10
_DETAIL_MAX_CHARS = 160

# Nudge kind vocabulary (from mastermind_feedback._NUDGE_KIND_ALLOWED)
_SUGGESTION_KINDS = frozenset({"contract_drift", "coverage_gap", "staleness",
                               "lobe_request", "other"})
_SEVERITIES = frozenset({"high", "medium", "low"})

# Default SLA hours for artifacts without synapse entries
_DEFAULT_SLA_HOURS = 48


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_json(p: Path) -> dict | None:
    """Read JSON file; return None on any error."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl_tail(p: Path, n: int = 50) -> list[dict]:
    """Read last n lines of a JSONL file; return [] on any error."""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        rows: list[dict] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception:  # noqa: BLE001
        return []


def _data_gap(field: str, note: str) -> dict:
    """Return a standardized data_gap entry (SA-R15)."""
    return {"field": field, "note": note}


def _artifact_age_hours(p: Path) -> float | None:
    """Return artifact age in hours (content stamp first, mtime fallback)."""
    now = datetime.now(timezone.utc).timestamp()
    try:
        if p.exists():
            try:
                raw = json.loads(p.read_bytes())
                for key in ("as_of", "generated_at", "built_at", "asof"):
                    val = raw.get(key)
                    if val and isinstance(val, str):
                        try:
                            ts = datetime.fromisoformat(val.replace("Z", "+00:00"))
                            if ts.tzinfo is None:
                                from datetime import timezone as tz
                                ts = ts.replace(tzinfo=tz.utc)
                            return (now - ts.timestamp()) / 3600.0
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001
                pass
            return (now - p.stat().st_mtime) / 3600.0
    except Exception:  # noqa: BLE001
        pass
    return None


def _load_synapse_sla(repo: Path) -> dict[str, float]:
    """Load freshness_sla_hours from synapse.yml for standout artifacts.
    Returns dict mapping artifact_id -> sla_hours.  Never raises."""
    try:
        from engine.neuralweb.synapse import load_registry  # type: ignore[import]
        reg = load_registry(repo)
        artifacts = reg.get("artifacts") or {}
        sla_map: dict[str, float] = {}
        for art_id, art in artifacts.items():
            if isinstance(art, dict) and art.get("freshness_sla_hours"):
                try:
                    sla_map[art_id] = float(art["freshness_sla_hours"])
                except Exception:  # noqa: BLE001
                    pass
        return sla_map
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Per-market block builders (each is NEVER-RAISE, returns a dict with data_gaps)
# ---------------------------------------------------------------------------

def _build_us_block(repo: Path) -> dict:
    """Build the US market accountability block."""
    block: dict[str, Any] = {
        "market": "us",
        "benchmark": "SPY",
        "fill_basis": "next_bar_close",
        "ledger_born": "2026-07-10",
        "data_gaps": [],
        "maturity_state": "accruing",
    }
    gaps: list[dict] = []

    # 1. data/us_board_ledger/retro_grades.parquet — matured row counts only
    retro_path = repo / "data" / "us_board_ledger" / "retro_grades.parquet"
    if retro_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(retro_path)
            # Graded columns only (have numeric forward returns)
            graded_cols = [c for c in df.columns if "fwd_ret" in c or "excess" in c]
            # Matured rows = rows where any graded column is non-null
            if graded_cols:
                matured_mask = df[graded_cols].notna().any(axis=1)
                matured_df = df[matured_mask]
                row_counts: dict[str, int] = {}
                for col in graded_cols:
                    n = int(matured_df[col].notna().sum())
                    if n > 0:
                        row_counts[col] = n
                block["retro_grades"] = {
                    "total_rows": int(len(df)),
                    "matured_rows": int(len(matured_df)),
                    "graded_col_counts": row_counts,
                    "note": "one-grader law (SA-R14); win_rate from committed scoreboard only",
                }
            else:
                block["retro_grades"] = {
                    "total_rows": int(len(df)),
                    "matured_rows": 0,
                    "graded_col_counts": {},
                    "note": "no graded columns found yet — accruing",
                }
        except Exception as exc:  # noqa: BLE001
            gaps.append(_data_gap("retro_grades", f"parquet read error: {exc}"))
    else:
        gaps.append(_data_gap("retro_grades", "data/us_board_ledger/retro_grades.parquet absent"))

    # 2. site/factordata/us_board_track.json
    track_path = repo / "site" / "factordata" / "us_board_track.json"
    if track_path.exists():
        d = _read_json(track_path)
        if d is not None:
            block["board_track"] = {
                "status": d.get("status"),
                "as_of": d.get("as_of"),
                "n_matured": d.get("n_matured"),
                "horizons_available": list(d.get("horizons", {}).keys()) if isinstance(d.get("horizons"), dict) else [],
            }
        else:
            gaps.append(_data_gap("board_track", "us_board_track.json parse error"))
    else:
        gaps.append(_data_gap("board_track", "site/factordata/us_board_track.json absent"))

    # 3. site/factordata/us_board_outcomes.json
    outcomes_path = repo / "site" / "factordata" / "us_board_outcomes.json"
    if outcomes_path.exists():
        d = _read_json(outcomes_path)
        if d is not None:
            block["board_outcomes"] = {
                "as_of": d.get("as_of"),
                "n_picks": d.get("n_picks"),
                "status": d.get("status"),
            }
        else:
            gaps.append(_data_gap("board_outcomes", "us_board_outcomes.json parse error"))
    else:
        gaps.append(_data_gap("board_outcomes", "site/factordata/us_board_outcomes.json absent"))

    # 4. site/factordata/us_audit_scoreboard.json
    scoreboard_path = repo / "site" / "factordata" / "us_audit_scoreboard.json"
    if scoreboard_path.exists():
        d = _read_json(scoreboard_path)
        if d is not None:
            block["audit_scoreboard"] = {
                "as_of": d.get("as_of"),
                "status": d.get("status"),
                "n_matured": d.get("n_matured"),
                "win_rate": d.get("win_rate"),  # carry if present; deterministic from committed store
            }
        else:
            gaps.append(_data_gap("audit_scoreboard", "us_audit_scoreboard.json parse error"))
    else:
        gaps.append(_data_gap("audit_scoreboard", "site/factordata/us_audit_scoreboard.json absent"))

    # 5. data/metabolism/fitness/standouts_us.json
    fitness_path = repo / "data" / "metabolism" / "fitness" / "standouts_us.json"
    if fitness_path.exists():
        d = _read_json(fitness_path)
        if d is not None:
            block["fitness_card"] = {
                "as_of": d.get("as_of"),
                "hit_quality": d.get("hit_quality"),
                "coverage_health": d.get("coverage_health"),
                "process_integrity": d.get("process_integrity"),
            }
        else:
            gaps.append(_data_gap("fitness_card", "standouts_us.json parse error"))
    else:
        gaps.append(_data_gap("fitness_card", "data/metabolism/fitness/standouts_us.json absent"))

    # 6. site/factordata/us_track_history.json
    history_path = repo / "site" / "factordata" / "us_track_history.json"
    if history_path.exists():
        d = _read_json(history_path)
        if d is not None:
            block["track_history"] = {
                "as_of": d.get("as_of"),
                "n_cohorts": d.get("n_cohorts"),
                "status": d.get("status"),
            }
        else:
            gaps.append(_data_gap("track_history", "us_track_history.json parse error"))
    else:
        gaps.append(_data_gap("track_history", "site/factordata/us_track_history.json absent"))

    block["data_gaps"] = gaps
    return block


def _build_cn_block(repo: Path) -> dict:
    """Build the CN market accountability block."""
    block: dict[str, Any] = {
        "market": "cn",
        "benchmark": "CSI300",
        "fill_basis": "t1_hl2",  # CN grader uses next-day HL2 fill
        "ledger_born": "2026-07-12",
        "data_gaps": [],
        "maturity_state": "accruing",
    }
    gaps: list[dict] = []

    # 1. data/china_standout_track/board.parquet
    cn_board_path = repo / "data" / "china_standout_track" / "board.parquet"
    if cn_board_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(cn_board_path)
            graded_cols = [c for c in df.columns if "fwd_ret" in c or "excess" in c]
            if graded_cols:
                matured_mask = df[graded_cols].notna().any(axis=1)
                matured_df = df[matured_mask]
                block["cn_board"] = {
                    "total_rows": int(len(df)),
                    "matured_rows": int(len(matured_df)),
                    "fill_basis_note": "t1_hl2 — T+1 HL2 fill, NEVER pooled with next-bar-close markets (PR-R5)",
                }
            else:
                block["cn_board"] = {
                    "total_rows": int(len(df)),
                    "matured_rows": 0,
                    "fill_basis_note": "t1_hl2 — accruing",
                }
        except Exception as exc:  # noqa: BLE001
            gaps.append(_data_gap("cn_board", f"parquet read error: {exc}"))
    else:
        gaps.append(_data_gap("cn_board", "data/china_standout_track/board.parquet absent"))

    # 2. data/metabolism/fitness/standouts_cn.json
    fitness_path = repo / "data" / "metabolism" / "fitness" / "standouts_cn.json"
    if fitness_path.exists():
        d = _read_json(fitness_path)
        if d is not None:
            block["fitness_card"] = {
                "as_of": d.get("as_of"),
                "hit_quality": d.get("hit_quality"),
                "process_integrity": d.get("process_integrity"),
            }
        else:
            gaps.append(_data_gap("fitness_card_cn", "standouts_cn.json parse error"))
    else:
        gaps.append(_data_gap("fitness_card_cn", "data/metabolism/fitness/standouts_cn.json absent"))

    # 3. CN audit scoreboard (path mirrors US convention)
    cn_scoreboard_path = repo / "site" / "factordata" / "cn_audit_scoreboard.json"
    if cn_scoreboard_path.exists():
        d = _read_json(cn_scoreboard_path)
        if d is not None:
            block["audit_scoreboard"] = {
                "as_of": d.get("as_of"),
                "status": d.get("status"),
                "n_matured": d.get("n_matured"),
            }
        else:
            gaps.append(_data_gap("cn_audit_scoreboard", "cn_audit_scoreboard.json parse error"))
    else:
        gaps.append(_data_gap("cn_audit_scoreboard", "site/factordata/cn_audit_scoreboard.json absent — expected after 2026-10-15"))

    block["data_gaps"] = gaps
    return block


def _build_hk_block(repo: Path) -> dict:
    """Build the HK market accountability block via board_ledger.scorecard()."""
    block: dict[str, Any] = {
        "market": "hk",
        "benchmark": "_HSI",
        "fill_basis": "next_bar_close",
        "ledger_born": "2026-06-01",
        "data_gaps": [],
        "maturity_state": "accruing",
    }
    gaps: list[dict] = []

    # Use board_ledger.scorecard("HK") — reuse, do not reimplement
    try:
        from engine import board_ledger  # type: ignore[import]
        sc = board_ledger.scorecard("HK")
        if sc:
            block["scorecard"] = {
                "status": sc.get("status"),
                "n_matured": sc.get("n_matured"),
                "as_of": sc.get("as_of"),
                "survivorship_note": sc.get("survivorship_note"),
            }
        else:
            gaps.append(_data_gap("hk_scorecard", "board_ledger.scorecard(HK) returned empty"))
    except Exception as exc:  # noqa: BLE001
        gaps.append(_data_gap("hk_scorecard", f"board_ledger.scorecard error: {exc}"))

    # Fitness card if present
    fitness_path = repo / "data" / "metabolism" / "fitness" / "standouts_hk.json"
    if fitness_path.exists():
        d = _read_json(fitness_path)
        if d is not None:
            block["fitness_card"] = {"as_of": d.get("as_of"), "status": d.get("status")}
        else:
            gaps.append(_data_gap("hk_fitness", "standouts_hk.json parse error"))
    # Absence is not a gap — HK fitness card accrues later

    block["data_gaps"] = gaps
    return block


def _build_ca_block(repo: Path) -> dict:
    """Build the CA market accountability block via board_ledger.scorecard()."""
    block: dict[str, Any] = {
        "market": "ca",
        "benchmark": "_GSPTSE",
        "fill_basis": "next_bar_close",
        "ledger_born": "2026-06-01",
        "data_gaps": [],
        "maturity_state": "accruing",
    }
    gaps: list[dict] = []

    try:
        from engine import board_ledger  # type: ignore[import]
        sc = board_ledger.scorecard("CA")
        if sc:
            block["scorecard"] = {
                "status": sc.get("status"),
                "n_matured": sc.get("n_matured"),
                "as_of": sc.get("as_of"),
                "survivorship_note": sc.get("survivorship_note"),
            }
        else:
            gaps.append(_data_gap("ca_scorecard", "board_ledger.scorecard(CA) returned empty"))
    except Exception as exc:  # noqa: BLE001
        gaps.append(_data_gap("ca_scorecard", f"board_ledger.scorecard error: {exc}"))

    # Fitness card if present
    fitness_path = repo / "data" / "metabolism" / "fitness" / "standouts_ca.json"
    if fitness_path.exists():
        d = _read_json(fitness_path)
        if d is not None:
            block["fitness_card"] = {"as_of": d.get("as_of"), "status": d.get("status")}

    block["data_gaps"] = gaps
    return block


def _build_intl_block(repo: Path) -> dict:
    """Build the intl market accountability block.

    Coverage/counts only.  Per PR-R5 hard law: no pooled return statistics.
    The residual-alpha base score is context, not a graded ranker (PR-R5).
    """
    block: dict[str, Any] = {
        "market": "intl",
        "benchmark": None,
        "fill_basis": "n/a — no intl stock-level forward ledger",
        "ledger_born": None,
        "data_gaps": [],
        "maturity_state": "no_stock_ledger",
        "disclosure": (
            "Prophet Intl signals are a context read, not a graded ranker "
            "— no forward ledger accrues for this board yet."
        ),
    }
    gaps: list[dict] = []

    # site/factordata/intl_setups.json — coverage/counts only
    intl_path = repo / "site" / "factordata" / "intl_setups.json"
    if intl_path.exists():
        d = _read_json(intl_path)
        if d is not None:
            markets = d.get("markets") or d.get("setups") or {}
            block["coverage"] = {
                "n_markets": len(markets) if isinstance(markets, dict) else None,
                "as_of": d.get("as_of"),
                "status": d.get("status"),
            }
        else:
            gaps.append(_data_gap("intl_setups", "intl_setups.json parse error"))
    else:
        gaps.append(_data_gap("intl_setups", "site/factordata/intl_setups.json absent"))

    block["data_gaps"] = gaps
    return block


def _build_momoedge_block(repo: Path) -> dict:
    """Build the momoedge Prophet trade plans cross-link block (display-only)."""
    block: dict[str, Any] = {
        "block_id": "momoedge_trade_plans",
        "note": (
            "Cross-connected Mastermind-Charts lane. Prophet manages US buy-lane → "
            "trade-plan envelopes. Display-only crosslink; Prophet reads, never writes "
            "these stores (PR-R2)."
        ),
        "data_gaps": [],
    }
    gaps: list[dict] = []

    # data/prophet/ledger.jsonl
    ledger_path = repo / "data" / "prophet" / "ledger.jsonl"
    if ledger_path.exists():
        rows = _read_jsonl_tail(ledger_path, n=100)
        open_count = sum(1 for r in rows if r.get("outcome") is None)
        closed_count = sum(1 for r in rows if r.get("outcome") is not None)
        outcome_mix: dict[str, int] = {}
        for r in rows:
            oc = r.get("outcome")
            if oc:
                outcome_mix[oc] = outcome_mix.get(oc, 0) + 1
        block["ledger"] = {
            "total_rows_sampled": len(rows),
            "open_count": open_count,
            "closed_count": closed_count,
            "outcome_mix": outcome_mix,
        }
    else:
        gaps.append(_data_gap("prophet_ledger", "data/prophet/ledger.jsonl absent"))

    # site/prophet/index.json
    index_path = repo / "site" / "prophet" / "index.json"
    if index_path.exists():
        d = _read_json(index_path)
        if d is not None:
            plans = d.get("plans") or []
            block["index"] = {
                "as_of": d.get("as_of"),
                "plan_count": len(plans) if isinstance(plans, list) else d.get("plan_count"),
            }
        else:
            gaps.append(_data_gap("prophet_index", "site/prophet/index.json parse error"))
    else:
        gaps.append(_data_gap("prophet_index", "site/prophet/index.json absent"))

    block["data_gaps"] = gaps
    return block


def _build_pick_lab_block(repo: Path) -> dict:
    """Build the pick lab summary block."""
    block: dict[str, Any] = {
        "block_id": "pick_lab",
        "data_gaps": [],
    }
    gaps: list[dict] = []

    for market, fname in [("us", "pick_lab.json"), ("cn", "china_pick_lab.json")]:
        lab_path = repo / "site" / "labdata" / fname
        if lab_path.exists():
            d = _read_json(lab_path)
            if d is not None:
                books = d.get("books") or []
                fires = d.get("fires") or []
                block[f"{market}_lab"] = {
                    "as_of": d.get("as_of"),
                    "book_count": len(books) if isinstance(books, list) else None,
                    "fire_count": len(fires) if isinstance(fires, list) else None,
                    "status": d.get("status"),
                }
            else:
                gaps.append(_data_gap(f"{market}_pick_lab", f"{fname} parse error"))
        else:
            gaps.append(_data_gap(f"{market}_pick_lab", f"site/labdata/{fname} absent"))

    block["data_gaps"] = gaps
    return block


def _build_dashboard_integrity(repo: Path, market_blocks: dict[str, dict],
                                sla_map: dict[str, float]) -> dict:
    """Build per-market dashboard integrity block (PR-R6, SA-R11 extended).

    Deterministic only: artifact freshness vs SLA, data_gap sentinel counts,
    stale-store flags.
    """
    integrity: dict[str, dict] = {}

    # Artifact paths to check per market
    artifacts_by_market: dict[str, list[tuple[str, str]]] = {
        "us": [
            ("us-audit-scoreboard", "site/factordata/us_audit_scoreboard.json"),
            ("us-track-history", "site/factordata/us_track_history.json"),
            ("us-board-outcomes", "site/factordata/us_board_outcomes.json"),
        ],
        "cn": [
            ("site-china-standouts", "data/metabolism/fitness/standouts_cn.json"),
        ],
        "hk": [
            ("hk-board-ledger", "data/board_ledger/hk_board.parquet"),
        ],
        "ca": [
            ("ca-board-ledger", "data/board_ledger/ca_board.parquet"),
        ],
        "intl": [
            ("intl-setups", "site/factordata/intl_setups.json"),
        ],
    }

    for market, art_list in artifacts_by_market.items():
        market_integrity: dict[str, Any] = {
            "market": market,
            "artifact_checks": [],
            "data_gap_count": len(market_blocks.get(market, {}).get("data_gaps", [])),
            "overall_health": "ok",
        }
        stale_count = 0
        for art_id, art_path in art_list:
            p = repo / art_path
            sla_hours = sla_map.get(art_id, _DEFAULT_SLA_HOURS)
            if not p.exists():
                market_integrity["artifact_checks"].append({
                    "artifact": art_id,
                    "path": art_path,
                    "status": "missing",
                })
                stale_count += 1
            else:
                age = _artifact_age_hours(p)
                if age is None:
                    status = "age_unknown"
                elif age > sla_hours:
                    status = "stale"
                    stale_count += 1
                else:
                    status = "ok"
                market_integrity["artifact_checks"].append({
                    "artifact": art_id,
                    "path": art_path,
                    "status": status,
                    "age_hours": round(age, 1) if age is not None else None,
                    "sla_hours": sla_hours,
                })

        if stale_count > 0 or market_integrity["data_gap_count"] > 0:
            market_integrity["overall_health"] = "degraded"
        integrity[market] = market_integrity

    return integrity


# ---------------------------------------------------------------------------
# Cross-market block (counts/coverage/process-fault rates only — no returns)
# ---------------------------------------------------------------------------

def _build_cross_market(market_blocks: dict[str, dict]) -> dict:
    """Build cross-market summary block.

    PR-R5 HARD LAW: no pooled return statistics across fill conventions.
    Only counts, coverage, and process-fault rates.
    """
    totals = {
        "markets_covered": len(market_blocks),
        "markets_with_data_gaps": 0,
        "total_data_gap_count": 0,
        "per_market_receipts": {},
    }

    for mkt, block in market_blocks.items():
        gaps = block.get("data_gaps", [])
        n_gaps = len(gaps)
        totals["total_data_gap_count"] += n_gaps
        if n_gaps > 0:
            totals["markets_with_data_gaps"] += 1
        totals["per_market_receipts"][mkt] = {
            "data_gap_count": n_gaps,
            "fill_basis": block.get("fill_basis"),
            "maturity_state": block.get("maturity_state"),
            "benchmark": block.get("benchmark"),
        }

    totals["cross_market_honesty_note"] = (
        "No pooled return statistics across fill conventions (PR-R5 hard law). "
        "CN uses T+1 HL2; US/HK/CA use next-bar-close; intl has no stock ledger. "
        "Per-market return statistics live in each market's own block only."
    )
    return totals


# ---------------------------------------------------------------------------
# Suggestions builder (PR-R4)
# ---------------------------------------------------------------------------

def _stable_code(base: str, market: str) -> str:
    """Build a stable suggestion code from base + market."""
    raw = f"{base}_{market}"
    return raw[:40].lower().replace("-", "_").replace("/", "_")


def _build_suggestions(status: dict) -> list[dict]:
    """Build suggestion rows from deterministic detections.

    Sources: SLA breaches, data_gap clusters, ledger freeze detection,
    HK/CA duplicate-row detection.  Stable codes so rows dedupe across
    nights (keep first_seen).  Max 10 rows.
    """
    today = _today_utc()
    suggestions: list[dict] = []

    integrity = status.get("dashboard_integrity") or {}
    markets = status.get("markets") or {}

    # 1. Staleness suggestions from dashboard integrity
    for market, mint in integrity.items():
        if not isinstance(mint, dict):
            continue
        for check in (mint.get("artifact_checks") or []):
            if check.get("status") in ("stale", "missing"):
                age = check.get("age_hours")
                art_id = check.get("artifact", "")
                detail = (
                    f"{art_id} is {'missing' if check['status'] == 'missing' else f'{age:.0f}h old'} "
                    f"(SLA {check.get('sla_hours', _DEFAULT_SLA_HOURS)}h) [{market.upper()}]"
                )[:_DETAIL_MAX_CHARS]
                suggestions.append({
                    "code": _stable_code(f"stale_{art_id.replace('-', '_')}", market),
                    "kind": "staleness",
                    "severity": "high" if check["status"] == "missing" else "medium",
                    "detail": detail,
                    "market": market,
                    "first_seen": today,
                    "asof": today,
                })

    # 2. Data gap cluster suggestions
    for market, block in markets.items():
        if not isinstance(block, dict):
            continue
        gaps = block.get("data_gaps") or []
        if len(gaps) >= 2:
            detail = (
                f"{len(gaps)} data gaps in {market.upper()} block: "
                + "; ".join(g.get("field", "?") for g in gaps[:3])
            )[:_DETAIL_MAX_CHARS]
            suggestions.append({
                "code": _stable_code("data_gap_cluster", market),
                "kind": "coverage_gap",
                "severity": "high" if len(gaps) >= 4 else "medium",
                "detail": detail,
                "market": market,
                "first_seen": today,
                "asof": today,
            })

    # 3. Ledger freeze detection — check if board_ledger as_of is very stale
    for market in ("hk", "ca"):
        block = markets.get(market, {})
        sc = block.get("scorecard") or {}
        asof = sc.get("as_of")
        if asof:
            try:
                dt = datetime.fromisoformat(str(asof).split("T")[0])
                now = datetime.now(timezone.utc)
                delta_days = (now.date() - dt.date()).days
                if delta_days > 5:
                    suggestions.append({
                        "code": _stable_code("ledger_freeze", market),
                        "kind": "contract_drift",
                        "severity": "high" if delta_days > 10 else "medium",
                        "detail": (
                            f"{market.upper()} board ledger last updated {asof} "
                            f"({delta_days}d stale) — check lane gate arming"
                        )[:_DETAIL_MAX_CHARS],
                        "market": market,
                        "first_seen": today,
                        "asof": today,
                    })
            except Exception:  # noqa: BLE001
                pass

    # Deduplicate by code, preserve first occurrence, cap at _MAX_SUGGESTIONS
    seen_codes: set[str] = set()
    unique: list[dict] = []
    for s in suggestions:
        code = s.get("code", "")
        if code not in seen_codes:
            seen_codes.add(code)
            unique.append(s)
        if len(unique) >= _MAX_SUGGESTIONS:
            break

    return unique


# ---------------------------------------------------------------------------
# Insight bus emission for high-severity suggestions (PR-R4)
# ---------------------------------------------------------------------------

def _emit_suggestion_bus_rows(suggestions: list[dict], repo: Path) -> list[str]:
    """Emit insight_bus rows for high-severity suggestions.

    Mirrors how standout_auditor.py emits its rows (same guard/never-raise pattern).
    Uses existing kinds from insight_bus._KINDS vocabulary — 'freshness_sla_breach'
    for staleness, 'contradiction' for contract_drift, 'health_transition' for other
    high-severity items.
    """
    emitted: list[str] = []
    try:
        from engine.metabolism.insight_bus import (  # type: ignore[import]
            build_row, append_row,
        )

        kind_map = {
            "staleness": "freshness_sla_breach",
            "contract_drift": "contradiction",
            "coverage_gap": "health_transition",
            "lobe_request": "health_transition",
            "other": "health_transition",
        }

        for s in suggestions:
            if s.get("severity") != "high":
                continue
            kind = kind_map.get(s.get("kind", "other"), "health_transition")
            row = build_row(
                emitter=_EMITTER,
                kind=kind,
                severity="high",
                entities=[f"prophet.{s.get('market', 'cross')}", s.get("code", "")],
                summary=s.get("detail", "")[:200],
                evidence_ref=str(_SUGGESTIONS_PATH),
                cycle_id=None,
            )
            try:
                if append_row(row, root=repo):
                    emitted.append(row.get("insight_id", ""))
            except Exception as exc:  # noqa: BLE001
                log.warning("prophet_governor: insight_bus emit: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_governor: _emit_suggestion_bus_rows: %s", exc)
    return emitted


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------

def build_status(root: Path | None = None) -> dict:
    """Build prophet_status.json content.  NEVER raises.

    Per-market blocks fail-soft: absent store => data_gap, never fabricated zeros
    (SA-R15).  Cross-market block contains counts only (PR-R5 hard law).
    """
    repo = _repo_root(root)
    ts = _now_utc()
    sla_map = _load_synapse_sla(repo)

    market_blocks: dict[str, dict] = {}

    for market, builder in [
        ("us", _build_us_block),
        ("cn", _build_cn_block),
        ("hk", _build_hk_block),
        ("ca", _build_ca_block),
        ("intl", _build_intl_block),
    ]:
        try:
            blk = builder(repo)
        except Exception as exc:  # noqa: BLE001
            log.warning("prophet_governor: %s block failed: %s", market, exc)
            blk = {
                "market": market,
                "data_gaps": [_data_gap("block_error", f"block builder raised: {exc}")],
            }
        # Inject public display labels (PR-R2 Amendment 1 rebrand)
        en_label, zh_label = _PROPHET_MARKET_LABEL.get(market, (market.upper(), market.upper()))
        blk["engine_label"] = en_label
        blk["engine_label_zh"] = zh_label
        market_blocks[market] = blk

    cross_market = _build_cross_market(market_blocks)

    # Dashboard integrity block (PR-R6)
    try:
        dashboard_integrity = _build_dashboard_integrity(repo, market_blocks, sla_map)
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_governor: dashboard_integrity failed: %s", exc)
        dashboard_integrity = {"error": str(exc)}

    # Momoedge trade plans block (display-only crosslink, PR-R2)
    try:
        momoedge_block = _build_momoedge_block(repo)
    except Exception as exc:  # noqa: BLE001
        momoedge_block = {"block_id": "momoedge_trade_plans",
                          "data_gaps": [_data_gap("block_error", str(exc))]}

    # Pick lab block
    try:
        pick_lab_block = _build_pick_lab_block(repo)
    except Exception as exc:  # noqa: BLE001
        pick_lab_block = {"block_id": "pick_lab",
                          "data_gaps": [_data_gap("block_error", str(exc))]}

    status = {
        "schema": SCHEMA_STATUS,
        "as_of": ts,
        "built_by": "engine.neuralweb.prophet_governor",
        "markets": market_blocks,
        "cross_market": cross_market,
        "dashboard_integrity": dashboard_integrity,
        "momoedge_trade_plans": momoedge_block,
        "pick_lab": pick_lab_block,
    }
    return status


def build_suggestions(status: dict) -> list[dict]:
    """Build prophet_suggestions.json rows from a status dict.

    Returns a list of suggestion rows mirroring the Mastermind nudge schema.
    NEVER raises.
    """
    try:
        return _build_suggestions(status)
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_governor: build_suggestions failed: %s", exc)
        return []


def _atomic_write(p: Path, content: str) -> None:
    """Atomic write: temp file then rename.  Raises on error."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.stem}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, str(p))
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp)
        except Exception:  # noqa: BLE001
            pass
        raise


def build_and_write(root: Path | None = None) -> dict:
    """Build both artifacts and write atomically.  NEVER raises.

    Returns dict with status_path, suggestions_path, n_suggestions, data_gaps.
    Emits insight_bus rows for high-severity suggestions.

    first_seen semantics: load the prior suggestions artifact (fail-soft), build a
    {code: first_seen} lookup, and carry those dates forward for codes that persist
    across runs.  New codes receive today's date.  This makes ``first_seen`` the
    genuine discovery date rather than the last-run date.
    """
    repo = _repo_root(root)
    result: dict[str, Any] = {
        "status_path": None,
        "suggestions_path": None,
        "n_suggestions": 0,
        "data_gaps": [],
        "as_of": _now_utc(),
    }

    # Load prior first_seen values (fail-soft — missing / corrupt → empty map)
    prior_first_seen: dict[str, str] = {}
    try:
        prior_path = repo / _SUGGESTIONS_PATH
        if prior_path.exists():
            prior_doc = json.loads(prior_path.read_text(encoding="utf-8"))
            for row in (prior_doc.get("suggestions") or []):
                code = row.get("code", "")
                fs = row.get("first_seen", "")
                if code and fs:
                    prior_first_seen[code] = fs
    except Exception as exc:  # noqa: BLE001
        log.debug("prophet_governor: could not load prior first_seen map: %s", exc)

    try:
        status = build_status(repo)
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_governor: build_status raised (should not happen): %s", exc)
        result["data_gaps"].append(str(exc))
        return result

    try:
        suggestions = build_suggestions(status)
        # Preserve first_seen for codes that persist across runs
        for s in suggestions:
            code = s.get("code", "")
            if code in prior_first_seen:
                s["first_seen"] = prior_first_seen[code]
        suggestions_doc = {
            "schema": SCHEMA_SUGGESTIONS,
            "as_of": status.get("as_of", _now_utc()),
            "built_by": "engine.neuralweb.prophet_governor",
            "suggestions": suggestions,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_governor: build_suggestions raised: %s", exc)
        suggestions = []
        suggestions_doc = {
            "schema": SCHEMA_SUGGESTIONS,
            "as_of": status.get("as_of", _now_utc()),
            "built_by": "engine.neuralweb.prophet_governor",
            "suggestions": [],
            "build_error": str(exc),
        }

    # Write both artifacts atomically
    status_path = repo / _STATUS_PATH
    sug_path = repo / _SUGGESTIONS_PATH

    try:
        _atomic_write(status_path, json.dumps(status, indent=2, default=str))
        result["status_path"] = str(status_path)
        log.info("prophet_governor: wrote %s", status_path)
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_governor: write status failed: %s", exc)
        result["data_gaps"].append(f"status write failed: {exc}")

    try:
        _atomic_write(sug_path, json.dumps(suggestions_doc, indent=2, default=str))
        result["suggestions_path"] = str(sug_path)
        result["n_suggestions"] = len(suggestions)
        log.info("prophet_governor: wrote %s (%d suggestions)", sug_path, len(suggestions))
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_governor: write suggestions failed: %s", exc)
        result["data_gaps"].append(f"suggestions write failed: {exc}")

    # Emit insight_bus rows for high-severity suggestions
    try:
        emitted = _emit_suggestion_bus_rows(suggestions, repo)
        if emitted:
            log.info("prophet_governor: emitted %d insight_bus rows", len(emitted))
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_governor: insight_bus emit failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s %(message)s")

    result = build_and_write()
    print(json.dumps(result, indent=2, default=str))

    from lib.procutil import hard_exit  # noqa: PLC0415
    hard_exit(0)
