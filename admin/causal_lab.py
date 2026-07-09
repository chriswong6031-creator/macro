"""Causal Lab admin panel (CHF-R13).

Reads committed JSON/JSONL artifacts only — no engine imports, no parquet,
no subprocess.  Fail-open on every artifact: missing/corrupt → the panel
carries an honest note but panel() always returns {"ok": True, ...}.

Primary artifact:
  site/neuralwebdata/causal_lab_state.json  (preferred — committed after nightly)
  data/neuralweb/causal_lab_state.json      (fallback)

Supplementary artifacts (all optional, fail-open):
  data/neuralweb/causal_edges.jsonl         — latest edges with verdict + concerns
  data/neuralweb/causal_nulls.jsonl         — null library
  data/neuralweb/causal_mechanisms.jsonl    — mechanism cards
  data/neuralweb/causal_confluence_audit.json — anti-mirage annotations (W6)

CHF-R13 authority:
  is_context_only: True
  annotate_only:   True  (W6 audit annotations)
  not_a_signal:    True
  All five authority booleans False.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA, SITE

# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------
_LAB_PRIMARY  = SITE / "neuralwebdata" / "causal_lab_state.json"
_LAB_FALLBACK = DATA / "neuralweb" / "causal_lab_state.json"
_EDGES        = DATA / "neuralweb" / "causal_edges.jsonl"
_NULLS        = DATA / "neuralweb" / "causal_nulls.jsonl"
_MECHANISMS   = DATA / "neuralweb" / "causal_mechanisms.jsonl"
_AUDIT        = DATA / "neuralweb" / "causal_confluence_audit.json"

# Display caps (prevent overwhelming the panel)
_EDGE_CAP = 5
_AUDIT_ANN_CAP = 5


# ---------------------------------------------------------------------------
# Helpers (mirror context_lobe.py exactly)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    """Read + parse JSON from path. Returns None on any error."""
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: Path) -> list[dict]:
    """Read + parse JSONL from path. Returns [] on any error."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return rows


def _age_hours(stamp: str | None) -> float | None:
    """Return hours since an ISO-8601 stamp, or None on any problem."""
    if not stamp:
        return None
    try:
        s = str(stamp).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
    except Exception:  # noqa: BLE001
        return None


def _file_mtime_iso(path: Path) -> str | None:
    """Return the file's mtime as an ISO-8601 UTC string, or None."""
    try:
        mt = os.path.getmtime(str(path))
        return datetime.fromtimestamp(mt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Sub-block extractors (each fail-open)
# ---------------------------------------------------------------------------

def _funnel_block(lab: dict) -> dict:
    """Extract funnel counts from lab state. Fail-open."""
    try:
        funnel = lab.get("funnel") or {}
        return {
            "edges_by_verdict": funnel.get("edges_by_verdict") or {},
            "total_edges": funnel.get("total_edges") or 0,
            "nulls_count": funnel.get("nulls_count") or 0,
            "mechanisms_by_status": funnel.get("mechanisms_by_status") or {},
            "total_mechanisms": funnel.get("total_mechanisms") or 0,
        }
    except Exception:  # noqa: BLE001
        return {}


def _scan_width_block(lab: dict) -> dict:
    """Extract cumulative causal_scan width. Fail-open."""
    try:
        cs = lab.get("causal_scan") or {}
        return {
            "cumulative_width": cs.get("cumulative_width") or 0,
            "description": cs.get("description") or "",
        }
    except Exception:  # noqa: BLE001
        return {"cumulative_width": 0, "description": ""}


def _frontier_block(lab: dict) -> dict:
    """Extract frontier summary. Fail-open."""
    try:
        fr = lab.get("frontier") or {}
        return {
            "total_cells": fr.get("total_cells") or 0,
            "cells_by_state": fr.get("cells_by_state") or {},
            "target_families": fr.get("target_families") or [],
            "environments": fr.get("environments") or [],
        }
    except Exception:  # noqa: BLE001
        return {}


def _surprise_queue_block(lab: dict) -> dict:
    """Extract surprise queue summary. Fail-open."""
    try:
        sq = lab.get("surprise_queue") or {}
        return {
            "size": sq.get("size") or 0,
            "stalest_source": sq.get("stalest_source") or "",
            "stalest_source_asof": sq.get("stalest_source_asof") or "",
        }
    except Exception:  # noqa: BLE001
        return {}


def _llm_lane_block(lab: dict) -> dict:
    """Extract LLM lane status. Fail-open."""
    try:
        ll = lab.get("llm_lane") or {}
        return {
            "status": ll.get("status") or "unknown",
            "description": ll.get("description") or "",
        }
    except Exception:  # noqa: BLE001
        return {"status": "unknown", "description": ""}


def _latest_edges(edges: list[dict]) -> list[dict]:
    """Return the latest _EDGE_CAP edges with verdict and concerns count."""
    try:
        # Sort by scanned_at descending if available, else take last N
        sorted_edges = sorted(
            edges,
            key=lambda e: e.get("scanned_at") or "",
            reverse=True,
        )
        rows = []
        for e in sorted_edges[:_EDGE_CAP]:
            rows.append({
                "edge_id": e.get("edge_id") or "?",
                "cause_feature_id": e.get("cause_feature_id") or "?",
                "target_id": e.get("target_id") or "?",
                "verdict": e.get("verdict") or "?",
                "n_concerns": len(e.get("concerns") or []),
                "scanned_at": e.get("scanned_at") or "",
            })
        return rows
    except Exception:  # noqa: BLE001
        return []


def _latest_audit_annotations(audit: dict | None) -> list[dict]:
    """Return up to _AUDIT_ANN_CAP recent annotations across all categories."""
    if audit is None:
        return []
    try:
        all_anns: list[dict] = []
        for category in ("duplicate_exposure", "shared_parent_suspect", "collider_risk"):
            for ann in (audit.get(category) or []):
                all_anns.append({
                    "rule_id": ann.get("rule_id") or "?",
                    "annotation_type": ann.get("annotation_type") or category,
                    "display_text": (ann.get("display_text") or "")[:120],  # truncate for UI
                })
        return all_anns[:_AUDIT_ANN_CAP]
    except Exception:  # noqa: BLE001
        return []


def _audit_counts(audit: dict | None) -> dict:
    """Extract annotation counts from the audit artifact. Fail-open."""
    if audit is None:
        return {"available": False}
    try:
        counts = audit.get("counts") or {}
        return {
            "available": True,
            "duplicate_exposure": counts.get("duplicate_exposure", 0),
            "shared_parent_suspect": counts.get("shared_parent_suspect", 0),
            "collider_risk": counts.get("collider_risk", 0),
            "total": counts.get("total", 0),
            "asof": audit.get("asof"),
        }
    except Exception:  # noqa: BLE001
        return {"available": False}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def panel() -> dict:
    """Causal Lab operator panel. Never raises. Always ok=True."""
    # Try primary then fallback
    lab: dict | None = _read_json(_LAB_PRIMARY)
    artifact_path = _LAB_PRIMARY

    if lab is None:
        lab = _read_json(_LAB_FALLBACK)
        artifact_path = _LAB_FALLBACK

    # Load supplementary artifacts (all optional)
    edges = _read_jsonl(_EDGES)
    nulls = _read_jsonl(_NULLS)
    mechanisms = _read_jsonl(_MECHANISMS)
    audit = _read_json(_AUDIT)

    # Freshness
    freshness_ts: str | None = None
    age_hours: float | None = None
    if lab is not None:
        freshness_ts = lab.get("asof") or _file_mtime_iso(artifact_path)
        age_hours = _age_hours(freshness_ts)

    if lab is None:
        return {
            "ok": True,
            "error": (
                "causal_lab_state.json not yet written — "
                "runs on Mac host nightly; absent in fresh CI checkouts."
            ),
            "is_context_only": True,
            "annotate_only": True,
            "not_a_signal": True,
            "freshness": None,
            "age_hours": None,
            "heartbeat": None,
            "funnel": {},
            "scan_width": {"cumulative_width": 0},
            "frontier": {},
            "surprise_queue": {},
            "llm_lane": {"status": "unknown"},
            "latest_edges": [],
            "data_absent_notes": [],
            "audit_counts": _audit_counts(audit),
            "latest_audit_annotations": _latest_audit_annotations(audit),
            "n_nulls": len(nulls),
            "n_mechanisms": len(mechanisms),
            "n_edges": len(edges),
        }

    return {
        "ok": True,
        "schema": lab.get("schema"),
        "asof": lab.get("asof"),
        "is_context_only": True,
        "annotate_only": True,
        "not_a_signal": True,
        "freshness": freshness_ts,
        "age_hours": age_hours,
        "heartbeat": lab.get("heartbeat"),
        "funnel": _funnel_block(lab),
        "scan_width": _scan_width_block(lab),
        "frontier": _frontier_block(lab),
        "surprise_queue": _surprise_queue_block(lab),
        "llm_lane": _llm_lane_block(lab),
        "latest_edges": _latest_edges(edges),
        "data_absent_notes": list(lab.get("data_absent_notes") or []),
        "audit_counts": _audit_counts(audit),
        "latest_audit_annotations": _latest_audit_annotations(audit),
        "n_nulls": len(nulls),
        "n_mechanisms": len(mechanisms),
        "n_edges": len(edges),
    }
