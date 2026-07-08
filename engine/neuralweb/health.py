"""engine.neuralweb.health — NW lobe-status surface (PR-C, RUL-NW1..14).

Produces one machine-readable operating-truth file for all Neural Web lobes.

Design notes
------------
- Fail-open: per-lobe exceptions produce status='unknown' with an error note;
  synapse.yml missing → writes a minimal skeleton and exits without raising.
- Scope selection is deterministic (no hand-list): entries where
    owner_program == 'neural-web'
    OR path starts with 'data/neuralweb/' or 'site/neuralwebdata/'
    OR external_consumers includes 'mastermind:context'
  PLUS the cortex section (cortex memo + probation — special-cased, not synapse-registered).
- Row count strategy (CHEAP — runs on the render path):
    JSON n_rows key → use it
    JSON rows/candidate_context arrays → len(...)
    JSONL → buffered line count
    parquet → envelope sidecar n_rows if present, else pyarrow metadata only, else None
- Status enum: fresh | fresh_partial | stale | missing | degraded |
               not_locally_verifiable | unknown
- Two-phase health:
    engine job  → cortex_source='previous_run' (previous run's cortex status)
    cortex job  → --refresh-cortex rewrites only the cortex section + overall + produced_at
                  setting cortex_source='current_run'
- workflow_conformance: only daily-engine cadence checked (no false alarms on
  other shards like asia-close).

Schema: 'neuralweb.health.v1'
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---- repo root ---------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_NW = _ROOT / "data" / "neuralweb"
_CONFIG = _ROOT / "config"
_SYNAPSE_YML = _CONFIG / "synapse.yml"
_DAILY_YML = _ROOT / ".github" / "workflows" / "daily.yml"
_CORTEX_MEMO = _DATA_NW / "cortex" / "memo.json"
_CORTEX_PROBATION = _DATA_NW / "cortex" / "probation.json"
_OUTPUT_DATA = _DATA_NW / "health.json"
_OUTPUT_SITE = _ROOT / "site" / "neuralwebdata" / "health.json"

SCHEMA = "neuralweb.health.v1"

# ---- as_of key priority list (same as mastermind_context.py) ----------------
_AS_OF_KEYS = ("as_of", "asof", "produced_at", "generated_at", "generated_utc", "date")


# ---- helpers -----------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _mtime_hours_ago(p: Path) -> float | None:
    try:
        mtime = p.stat().st_mtime
        now = datetime.now(timezone.utc).timestamp()
        return round((now - mtime) / 3600, 2)
    except Exception:  # noqa: BLE001
        return None


def _iso_hours_ago(ts_str: str | None) -> float | None:
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        return round((now - dt).total_seconds() / 3600, 2)
    except Exception:  # noqa: BLE001
        return None


def _extract_as_of(obj: dict | None) -> str | None:
    """Extract as_of using the same key-priority list as mastermind_context.py."""
    if not obj:
        return None
    for k in _AS_OF_KEYS:
        v = obj.get(k)
        if v:
            return str(v)
    return None


def _row_count(p: Path, fmt: str) -> int | None:
    """Cheap row count — never loads a full table."""
    try:
        if fmt == "json":
            obj = _read_json(p)
            if obj is None:
                return None
            # explicit n_rows key
            if "n_rows" in obj:
                return int(obj["n_rows"])
            # rows / candidate_context arrays
            for key in ("rows", "candidate_context"):
                if key in obj and isinstance(obj[key], list):
                    return len(obj[key])
            return None
        elif fmt == "jsonl":
            count = 0
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.strip():
                        count += 1
            return count
        elif fmt == "parquet":
            # Try envelope sidecar first
            sidecar = Path(str(p) + ".envelope.json")
            if sidecar.exists():
                env = _read_json(sidecar)
                if env and "n_rows" in env:
                    return int(env["n_rows"])
            # Try pyarrow metadata only (no table load)
            try:
                import pyarrow.parquet as pq  # noqa: PLC0415
                pf = pq.ParquetFile(str(p))
                return pf.metadata.num_rows
            except Exception:  # noqa: BLE001
                return None
        else:
            return None
    except Exception:  # noqa: BLE001
        return None


def _byte_size(p: Path) -> int | None:
    try:
        return p.stat().st_size
    except Exception:  # noqa: BLE001
        return None


def _parse_yaml_synapse(path: Path) -> dict | None:
    try:
        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw
    except Exception:  # noqa: BLE001
        return None


# ---- scope selection ---------------------------------------------------------

def _is_nw_scope(art_id: str, art: dict) -> bool:
    """Determine if this synapse artifact is in the NW health scope."""
    op = art.get("owner_program", "")
    path = art.get("path", "")
    ec = art.get("external_consumers") or []
    return (
        op == "neural-web"
        or path.startswith("data/neuralweb/")
        or path.startswith("site/neuralwebdata/")
        or "mastermind:context" in ec
    )


# ---- per-lobe record ---------------------------------------------------------

def _lobe_record(art_id: str, art: dict, root: Path) -> dict:
    """Build one per-lobe health record."""
    path_rel = art.get("path", "")
    fmt = (art.get("format") or "").lower()
    storage = art.get("storage", "git")
    sla_h = art.get("freshness_sla_hours")
    full_path = root / path_rel if path_rel else None

    rec: dict[str, Any] = {
        "id": art_id,
        "path": path_rel,
        "producer": art.get("producer"),
        "cadence": art.get("cadence"),
        "tier": art.get("tier"),
        "horizon_role": art.get("horizon_role"),
        "storage": storage,
        "as_of": None,
        "produced_at": None,
        "age_hours": None,
        "freshness_sla_hours": sla_h,
        "status": "unknown",
        "row_count": None,
        "byte_size": None,
        "gaps": [],
    }

    # R2 artifacts — never 'missing'; skip local verification
    if storage == "r2":
        rec["status"] = "not_locally_verifiable"
        return rec

    if not full_path or not full_path.exists():
        rec["status"] = "missing"
        return rec

    # File exists — compute age
    try:
        obj = None
        if fmt == "json":
            obj = _read_json(full_path)

        # as_of from artifact content
        as_of = _extract_as_of(obj) if obj else None
        produced_at = None
        if obj:
            produced_at = obj.get("produced_at") or obj.get("generated_utc")

        rec["as_of"] = as_of
        rec["produced_at"] = produced_at
        rec["byte_size"] = _byte_size(full_path)
        rec["row_count"] = _row_count(full_path, fmt)

        # Age: prefer content as_of, fallback to mtime
        age_h = _iso_hours_ago(as_of) if as_of else _mtime_hours_ago(full_path)
        rec["age_hours"] = age_h

        # Check self-reported degraded/gaps
        gaps = []
        degraded_self = False
        if obj and isinstance(obj, dict):
            if obj.get("degraded") or obj.get("is_degraded"):
                degraded_self = True
                reason = obj.get("degradation_reason") or obj.get("degraded_reason") or "self-reported"
                gaps.append(f"degraded: {reason}")
            raw_gaps = obj.get("gaps") or []
            if isinstance(raw_gaps, list):
                gaps.extend(str(g) for g in raw_gaps)
        rec["gaps"] = gaps

        # Determine status
        if degraded_self:
            rec["status"] = "degraded"
        elif sla_h is not None and age_h is not None and age_h > sla_h:
            rec["status"] = "stale"
        elif gaps:
            rec["status"] = "fresh_partial"
        else:
            rec["status"] = "fresh"

    except Exception as exc:  # noqa: BLE001
        rec["status"] = "unknown"
        rec["gaps"] = [f"error: {exc}"]

    return rec


# ---- cortex section ----------------------------------------------------------

def _derive_run_status_legacy(memo: dict) -> dict:
    """Derive run_status from tool_call_census for legacy memos (mirrors admin pattern)."""
    tcc = memo.get("tool_call_census") or {}
    has_tools = bool(tcc) and not (len(tcc) == 1 and "fallback_call" in tcc)
    return {
        "status": "warn" if has_tools else "degraded",
        "degraded": not has_tools,
        "degradation_reason": "zero_tool_calls" if not has_tools else None,
        "provider_attempts": [],
        "tool_call_batches": 0,
        "individual_tool_calls": sum(tcc.values()) if tcc else 0,
        "expected_min_tool_calls": 1,
        "context_stale": False,
        "context_as_of": None,
        "_legacy_memo": True,
    }


def _cortex_section(root: Path, cortex_source: str = "previous_run") -> dict:
    """Build the cortex health section."""
    memo_path = root / "data" / "neuralweb" / "cortex" / "memo.json"
    prob_path = root / "data" / "neuralweb" / "cortex" / "probation.json"

    out: dict[str, Any] = {
        "cortex_source": cortex_source,
        "memo_as_of": None,
        "run_status": None,
        "probation": None,
        "status": "unknown",
    }

    memo = _read_json(memo_path)
    if memo:
        out["memo_as_of"] = memo.get("as_of") or memo.get("generated_at")
        raw_rs = memo.get("run_status")
        run_status = raw_rs if raw_rs else _derive_run_status_legacy(memo)
        out["run_status"] = run_status
        degraded = run_status.get("degraded", False)
        out["status"] = "degraded" if degraded else "fresh"
    else:
        out["status"] = "missing"

    # probation — may live in memo or separate file
    prob = None
    if memo:
        prob = memo.get("probation")
    if prob is None:
        prob_json = _read_json(prob_path)
        if prob_json:
            prob = prob_json

    if prob:
        out["probation"] = {
            "granted": prob.get("granted", False),
            "n": (prob.get("attention_track_record") or {}).get("n"),
            "min_n": prob.get("min_n", 30),
        }

    return out


# ---- workflow conformance check ----------------------------------------------

def _workflow_conformance(in_scope: list[dict], root: Path) -> list[dict]:
    """For daily-engine cadence in-scope artifacts, check producer appears in daily.yml."""
    daily_yml = root / ".github" / "workflows" / "daily.yml"
    if not daily_yml.exists():
        return [{"note": "daily.yml not found — conformance check skipped"}]

    try:
        daily_text = daily_yml.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return [{"note": f"daily.yml unreadable: {exc}"}]

    misses = []
    for rec in in_scope:
        if rec.get("cadence") != "daily-engine":
            continue
        producer = rec.get("producer") or ""
        if not producer:
            continue
        # Strip path separators to a module name for matching
        producer_stem = producer.replace("/", ".").replace("\\", ".").rstrip(".py").rstrip(".")
        # Also try the bare filename
        producer_base = Path(producer).stem
        if producer not in daily_text and producer_stem not in daily_text and producer_base not in daily_text:
            misses.append({
                "id": rec.get("id"),
                "producer": producer,
                "note": "producer not found in daily.yml text (daily-engine cadence)",
            })
    return misses


# ---- overall status ----------------------------------------------------------

def _overall_status(lobes: list[dict], cortex: dict, world_state_id: str = "world-state") -> str:
    """
    ok       — no stale/missing/degraded
    warn     — stale or fresh_partial present, cortex not degraded
    degraded — cortex degraded OR world_state missing/stale OR any core lobe missing
    """
    cortex_degraded = cortex.get("status") == "degraded"
    if cortex_degraded:
        return "degraded"

    lobe_map = {r["id"]: r for r in lobes}
    ws = lobe_map.get(world_state_id, {})
    ws_status = ws.get("status", "unknown")
    if ws_status in ("missing", "stale"):
        return "degraded"

    any_missing = any(r["status"] == "missing" for r in lobes)
    if any_missing:
        return "degraded"

    any_bad = any(r["status"] in ("stale", "fresh_partial", "degraded") for r in lobes)
    if any_bad:
        return "warn"

    return "ok"


# ---- summary counts ----------------------------------------------------------

def _summary_counts(lobes: list[dict], cortex: dict) -> dict:
    statuses = [r["status"] for r in lobes]
    return {
        "total_lobes": len(lobes),
        "fresh": statuses.count("fresh"),
        "fresh_partial": statuses.count("fresh_partial"),
        "stale": statuses.count("stale"),
        "missing": statuses.count("missing"),
        "degraded": statuses.count("degraded"),
        "not_locally_verifiable": statuses.count("not_locally_verifiable"),
        "unknown": statuses.count("unknown"),
        "cortex_status": cortex.get("status", "unknown"),
    }


# ---- support-impact enrichment (RUL-CC-14) -----------------------------------

_SUPPORT_MAP_TOP_N = 10  # max items in transitive_downstream_top


def _embed_support_impact(lobes: list[dict], root: Path) -> None:
    """Embed a compact support_impact block into each stale/missing/degraded lobe.

    Mutates the lobe dicts in-place.  Fail-open: if support_map is unavailable
    or raises, the block is set to {available: False, note: <reason>} and the
    overall build is not interrupted.

    Block shape (on success):
      {
        direct_consumers: [module_path, ...],
        transitive_downstream_count: int,
        transitive_downstream_top: [{artifact_id, hop, via_module}, ...],
        bound: "upper",
        note: "<overattribution explanation>",
        available: true,
      }

    RUL-CC-14: bound='upper' is mandatory; the note explains the over-attribution.
    Language law: results described as downstream surfaces that read this artifact.
    """
    _AFFECTED = frozenset({"stale", "missing", "degraded"})
    affected_lobes = [lobe for lobe in lobes if lobe.get("status") in _AFFECTED]
    if not affected_lobes:
        return

    try:
        from engine.neuralweb.support_map import (  # noqa: PLC0415
            consumers_direct,
            downstream,
            load_graph,
        )
        graph = load_graph(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("health: support_map unavailable — skipping support_impact: %s", exc)
        _err_note = f"support_map unavailable: {exc}"
        for lobe in affected_lobes:
            lobe["support_impact"] = {"available": False, "note": _err_note}
        return

    for lobe in affected_lobes:
        art_id = lobe.get("id", "")
        try:
            direct = consumers_direct(graph, art_id)
            transitive = downstream(graph, art_id)
            top = [
                {"artifact_id": r["artifact_id"], "hop": r["hop"], "via_module": r["via_module"]}
                for r in transitive[:_SUPPORT_MAP_TOP_N]
            ]
            lobe["support_impact"] = {
                "direct_consumers": [c["module"] for c in direct],
                "transitive_downstream_count": len(transitive),
                "transitive_downstream_top": top,
                "bound": "upper",
                "note": (
                    "Downstream surfaces that read this artifact directly or transitively. "
                    "Bound is upper: shared-producer inversion may fold in additional "
                    "artifacts beyond those that directly depend on this one."
                ),
                "available": True,
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("health: support_impact failed for %s: %s", art_id, exc)
            lobe["support_impact"] = {"available": False, "note": f"error: {exc}"}


# ---- context accrual heartbeat (R-CI12) ---------------------------------------

def _context_accrual_heartbeat(root: Path) -> dict:
    """R-CI12: verify accrual plumbing for personality + fire_coordinates.

    Fail-open: every sub-block catches its own exceptions and returns honest
    absent markers.  Never raises.  Returns a dict embedded in health.json
    under 'context_accrual'.

    Checks:
      personality_forward_ledger: data/stock_personality/forward_ledger.parquet
        exists, n_rows, last_append date.
      fire_coordinates: data/factordata/fire_coordinates.jsonl
        exists, n_rows, last_as_of, dna_nonnull_pct (% rows where dna_class != null).
      panel_partitions: data/factordata/panel/*/panel.parquet
        latest partition month, n_partitions.
      stamper_gap: true when track_record has buy/rebuy fires on a date
        where the personality forward_ledger has NO row that date.
    """
    result: dict[str, Any] = {}

    # --- personality_forward_ledger ---
    fl_path = root / "data" / "stock_personality" / "forward_ledger.parquet"
    try:
        fl_exists = fl_path.exists()
        fl_rows: int | None = None
        fl_last_append: str | None = None
        if fl_exists:
            fl_rows = _row_count(fl_path, "parquet")
            try:
                import pyarrow.parquet as pq  # noqa: PLC0415
                pf = pq.ParquetFile(str(fl_path))
                # read only date/as_of columns
                schema_names = list(pf.schema_arrow.names)
                date_cols = [c for c in schema_names if c in ("as_of", "date", "fire_date", "asof")]
                if date_cols:
                    tbl = pf.read(columns=date_cols[:1])
                    col = tbl.column(0).to_pylist()
                    non_null = [str(v) for v in col if v is not None]
                    fl_last_append = max(non_null) if non_null else None
            except Exception:  # noqa: BLE001
                pass
        result["personality_forward_ledger"] = {
            "exists": fl_exists,
            "rows": fl_rows,
            "last_append": fl_last_append,
        }
    except Exception as exc:  # noqa: BLE001
        result["personality_forward_ledger"] = {"exists": None, "rows": None,
                                                  "last_append": None, "error": str(exc)}

    # --- fire_coordinates ---
    fc_path = root / "data" / "factordata" / "fire_coordinates.jsonl"
    try:
        fc_exists = fc_path.exists()
        fc_rows: int | None = None
        fc_last_asof: str | None = None
        fc_dna_nonnull_pct: float | None = None
        if fc_exists:
            rows_parsed: list[dict] = []
            try:
                with fc_path.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                rows_parsed.append(json.loads(line))
                            except Exception:  # noqa: BLE001
                                pass
            except Exception:  # noqa: BLE001
                pass
            fc_rows = len(rows_parsed)
            if rows_parsed:
                asofs = [r.get("as_of") for r in rows_parsed if r.get("as_of")]
                fc_last_asof = max(str(a) for a in asofs) if asofs else None
                n_dna = sum(1 for r in rows_parsed if r.get("dna_class") is not None)
                fc_dna_nonnull_pct = round(100 * n_dna / fc_rows, 1) if fc_rows else None
        result["fire_coordinates"] = {
            "exists": fc_exists,
            "rows": fc_rows,
            "last_asof": fc_last_asof,
            "dna_nonnull_pct": fc_dna_nonnull_pct,
        }
    except Exception as exc:  # noqa: BLE001
        result["fire_coordinates"] = {"exists": None, "rows": None,
                                       "last_asof": None, "dna_nonnull_pct": None,
                                       "error": str(exc)}

    # --- panel_partitions ---
    panel_dir = root / "data" / "factordata" / "panel"
    try:
        parts = sorted(panel_dir.glob("*/panel.parquet")) if panel_dir.exists() else []
        result["panel_partitions"] = {
            "latest": parts[-1].parent.name if parts else None,
            "n": len(parts),
        }
    except Exception as exc:  # noqa: BLE001
        result["panel_partitions"] = {"latest": None, "n": None, "error": str(exc)}

    # --- stamper_gap: track_record buy/rebuy fires on dates with no forward-ledger append ---
    try:
        stamper_gap = False
        gap_dates: list[str] = []
        tr_path = root / "data" / "signal_archive" / "track_record.parquet"
        if tr_path.exists() and fl_path.exists():
            try:
                import pyarrow.parquet as pq  # noqa: PLC0415
                import pandas as _pd  # noqa: PLC0415
                # buy/rebuy fire dates from track_record
                tr_pf = pq.ParquetFile(str(tr_path))
                tr_schema = list(tr_pf.schema_arrow.names)
                tr_cols = [c for c in tr_schema if c in ("date", "type", "first_seen_asof")]
                if "date" in tr_cols and "type" in tr_cols:
                    tr_tbl = tr_pf.read(columns=["date", "type"])
                    tr_df = tr_tbl.to_pandas()
                    buy_dates = set(
                        str(d) for d in tr_df.loc[tr_df["type"].isin(["buy", "rebuy"]), "date"].dropna().unique()
                    )
                    # forward_ledger dates
                    fl_pf = pq.ParquetFile(str(fl_path))
                    fl_schema_names = list(fl_pf.schema_arrow.names)
                    fl_date_cols = [c for c in fl_schema_names if c in ("as_of", "date", "fire_date", "asof")]
                    if fl_date_cols:
                        fl_tbl = fl_pf.read(columns=fl_date_cols[:1])
                        fl_dates = set(str(v) for v in fl_tbl.column(0).to_pylist() if v is not None)
                        gap_dates = sorted(buy_dates - fl_dates)[-5:]  # show last 5
                        if gap_dates:
                            stamper_gap = True
            except Exception:  # noqa: BLE001
                pass
        result["stamper_gap"] = stamper_gap
        if gap_dates:
            result["stamper_gap_dates_sample"] = gap_dates
    except Exception as exc:  # noqa: BLE001
        result["stamper_gap"] = None
        result["stamper_gap_error"] = str(exc)

    return result


# ---- main build function -----------------------------------------------------

def build(root: Path | None = None, cortex_source: str = "previous_run") -> dict:
    """
    Build the full NW health artifact.

    Parameters
    ----------
    root : repo root (auto-detected from this module's location if None)
    cortex_source : 'previous_run' (engine job) or 'current_run' (cortex job)

    Returns
    -------
    health dict matching schema neuralweb.health.v1
    """
    if root is None:
        root = _ROOT

    now = _now_utc()

    # Load synapse.yml
    synapse = _parse_yaml_synapse(root / "config" / "synapse.yml")
    if not synapse or not isinstance(synapse.get("artifacts"), dict):
        log.warning("health: synapse.yml missing or unparseable — writing skeleton")
        return {
            "schema": SCHEMA,
            "produced_at": now,
            "as_of": now,
            "overall_status": "unknown",
            "lobes": [],
            "cortex": {"status": "unknown", "cortex_source": cortex_source},
            "workflow_conformance_misses": [],
            "summary_counts": _summary_counts([], {"status": "unknown"}),
        }

    artifacts = synapse["artifacts"]

    # Select in-scope lobes (deterministic)
    in_scope_ids = [
        art_id for art_id, art in artifacts.items()
        if _is_nw_scope(art_id, art)
    ]

    # Build per-lobe records (fail-open)
    lobes: list[dict] = []
    for art_id in in_scope_ids:
        try:
            rec = _lobe_record(art_id, artifacts[art_id], root)
        except Exception as exc:  # noqa: BLE001
            log.warning("health: lobe %s raised unexpectedly: %s", art_id, exc)
            rec = {
                "id": art_id,
                "path": artifacts[art_id].get("path"),
                "status": "unknown",
                "gaps": [f"error: {exc}"],
            }
        lobes.append(rec)

    # Support-impact enrichment (RUL-CC-14): embed compact blast-radius block
    # for each stale/missing/degraded lobe.  Load graph once per build.
    _embed_support_impact(lobes, root)

    # Cortex section
    cortex = _cortex_section(root, cortex_source=cortex_source)

    # Workflow conformance (daily-engine only)
    conformance_misses = _workflow_conformance(lobes, root)

    overall = _overall_status(lobes, cortex)
    counts = _summary_counts(lobes, cortex)

    # R-CI12: context accrual heartbeat (fail-open)
    try:
        context_accrual = _context_accrual_heartbeat(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("health: context_accrual_heartbeat failed: %s", exc)
        context_accrual = {"error": str(exc)}

    # Conservative as_of: oldest fresh data timestamp across lobes
    fresh_times = [
        r["as_of"] for r in lobes
        if r.get("as_of") and r.get("status") in ("fresh", "fresh_partial")
    ]
    if cortex.get("memo_as_of"):
        fresh_times.append(cortex["memo_as_of"])
    as_of = min(fresh_times) if fresh_times else now

    return {
        "schema": SCHEMA,
        "produced_at": now,
        "as_of": as_of,
        "overall_status": overall,
        "lobes": lobes,
        "cortex": cortex,
        "workflow_conformance_misses": conformance_misses,
        "summary_counts": counts,
        "context_accrual": context_accrual,
    }


def refresh_cortex(existing: dict, root: Path | None = None) -> dict:
    """
    Load existing health.json, recompute only the cortex section +
    overall_status + produced_at. Set cortex_source='current_run'.

    Used by the cortex job's --refresh-cortex step.
    """
    if root is None:
        root = _ROOT

    cortex = _cortex_section(root, cortex_source="current_run")
    lobes = existing.get("lobes", [])
    overall = _overall_status(lobes, cortex)
    counts = _summary_counts(lobes, cortex)

    updated = dict(existing)
    updated["produced_at"] = _now_utc()
    updated["cortex"] = cortex
    updated["overall_status"] = overall
    updated["summary_counts"] = counts
    return updated


def write(payload: dict, root: Path | None = None) -> None:
    """Write health.json to both data/ and site/ locations."""
    if root is None:
        root = _ROOT

    data_path = root / "data" / "neuralweb" / "health.json"
    site_path = root / "site" / "neuralwebdata" / "health.json"

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    for dest in (data_path, site_path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        log.info("health: wrote %s", dest)
