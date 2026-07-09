"""Context Lobe panel — Neural Web per-ticker context layer.

Reads committed JSON artifacts only (no engine imports, no parquet, no subprocess).
Fail-open on every artifact: missing/corrupt -> the panel carries an error note but
panel() always returns {"ok": True, ...}.

Primary artifact:
  site/neuralwebdata/mastermind_context.json   (preferred — committed after nightly)
  data/neuralweb/mastermind_context.json       (fallback)

Artifact shape (top-level):
  schema / as_of / produced_at / is_context_only / lobes / lobe_manifest /
  candidate_context (dict: ticker -> row) / gap_notes

Each candidate_context row may have grouped sub-blocks:
  bottom, options, graph_conflicts, kernel, allowed_behavior
  (valuation, leverage, structural, dilution, earnings_ctx, visibility
   may appear in future builds — all null-safe)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA, SITE

# ---------------------------------------------------------------------------
# Module-level path constants — monkeypatched in tests
# ---------------------------------------------------------------------------
_CTX_PRIMARY  = SITE / "neuralwebdata" / "mastermind_context.json"
_CTX_FALLBACK = DATA / "neuralweb" / "mastermind_context.json"

# Cap candidate rows for display
_CANDIDATE_CAP = 25


# ---------------------------------------------------------------------------
# Helpers (mirror long_hold.py exactly)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    """Read + parse JSON from path. Returns None on any error."""
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


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


def _row_richness(row: dict) -> int:
    """Count non-empty sub-blocks for sorting richest rows first."""
    score = 0
    for k, v in row.items():
        if k == "allowed_behavior":
            continue
        if v and v != {}:
            score += 1
    return score


# ---------------------------------------------------------------------------
# Sub-block extractors (each fail-open)
# ---------------------------------------------------------------------------

def _lobes_block(raw: dict) -> dict:
    """Extract a compact summary of each lobe. Fail-open."""
    try:
        lobes_raw = raw.get("lobes") or {}
        out: dict = {}
        for name, lobe in lobes_raw.items():
            if not isinstance(lobe, dict):
                out[name] = {"available": False}
                continue
            # Extract a concise per-lobe summary without hardcoding every key
            entry: dict = {"available": True}
            # Common top-level freshness / asof
            for key in ("as_of", "asof"):
                if lobe.get(key):
                    entry["as_of"] = lobe[key]
                    break
            # Market lobe: extract verdict summary
            if name == "market":
                verdict = lobe.get("verdict") or {}
                entry["verdict"] = verdict.get("verdict")
                entry["score"]   = verdict.get("score")
                entry["label"]   = verdict.get("label_en")
                radar = lobe.get("radar") or {}
                entry["radar_state"] = radar.get("state")
            # Reliability lobe
            elif name in ("reliability", "claim_reliability"):
                entry["standing_law"] = lobe.get("standing_law")
            # Bottom sensors lobe
            elif name == "bottom_sensors":
                counts = lobe.get("counts") or {}
                entry["n_rows"]  = lobe.get("n_rows")
                entry["counts"]  = counts
                entry["as_of"]   = lobe.get("as_of")
            # Options entry
            elif name == "options_entry":
                gate = lobe.get("gate") or {}
                entry["gate"] = gate
                entry["as_of"] = lobe.get("as_of")
            # Cortex
            elif name == "cortex":
                memo = lobe.get("memo") or {}
                entry["probation"] = lobe.get("probation", False)
                entry["active_signals"] = memo.get("active_signals")
            # Macro weather
            elif name == "macro_weather":
                entry["us_quad"]    = lobe.get("us_quad")
                entry["china_quad"] = lobe.get("china_quad")
                entry["hk_quad"]    = lobe.get("hk_quad")
                entry["as_of"]      = lobe.get("asof")
            # Contradictions
            elif name == "contradictions":
                summary = lobe.get("summary") or {}
                entry["n_records"] = summary.get("n_records") or len(lobe.get("records") or [])
            # Cycle pattern
            elif name == "cycle_pattern":
                entry["gate_status"]    = lobe.get("gate_status")
                entry["n_entities"]     = lobe.get("n_entities")
                entry["n_with_hazard"]  = lobe.get("n_with_hazard")
                entry["model_epoch"]    = lobe.get("model_epoch")
                entry["as_of"]          = lobe.get("as_of")
            out[name] = entry
        return out
    except Exception:  # noqa: BLE001
        return {}


def _lobe_manifest_block(raw: dict) -> list:
    """Pass through lobe_manifest as-is. Fail-open."""
    try:
        return list(raw.get("lobe_manifest") or [])
    except Exception:  # noqa: BLE001
        return []


def _candidate_block(raw: dict) -> list:
    """
    Extract up to _CANDIDATE_CAP candidate_context rows, sorted richest-first.
    Each entry is a flat dict with the ticker prepended + key sub-block fields
    null-safe.
    """
    try:
        cc = raw.get("candidate_context") or {}
        if not isinstance(cc, dict) or not cc:
            return []

        # Sort by richness descending so we surface the most-complete rows
        ranked = sorted(cc.items(), key=lambda kv: _row_richness(kv[1]), reverse=True)
        rows = []
        for ticker, row in ranked[:_CANDIDATE_CAP]:
            if not isinstance(row, dict):
                continue
            bottom    = row.get("bottom")    or {}
            val       = row.get("valuation") or {}
            opts      = row.get("options")   or {}
            lev       = row.get("leverage")  or {}
            struct    = row.get("structural") or {}
            dil       = row.get("dilution")  or {}
            earn      = row.get("earnings_ctx") or {}
            vis       = row.get("visibility") or {}
            graph_c   = row.get("graph_conflicts") or []
            kernel    = row.get("kernel")    or {}

            rows.append({
                "ticker":                  ticker,
                # bottom
                "bottom_state":            bottom.get("bottom_state"),
                "trigger_age_ticks":       bottom.get("trigger_age_ticks"),
                "coiled":                  bottom.get("coiled"),
                "star":                    bottom.get("star"),
                "earnings_days_to":        bottom.get("earnings_days_to") or earn.get("days_to_earnings"),
                "earnings_next_date":      bottom.get("earnings_next_date"),
                # valuation (may be absent in Build 1)
                "ev_sales":                val.get("ev_sales"),
                "ev_ebit":                 val.get("ev_ebit"),
                "p_fcf":                   val.get("p_fcf"),
                "pe":                      val.get("pe"),
                # options
                "gex_confirm_verdict":     opts.get("gex_confirm_verdict"),
                "iv30":                    opts.get("iv30"),
                "net_doi":                 opts.get("net_doi"),
                # leverage (may be absent in Build 1)
                "interest_coverage":       lev.get("interest_coverage"),
                "net_debt_to_ebitda":      lev.get("net_debt_to_ebitda"),
                # structural (may be absent in Build 1)
                "underwater_state":        struct.get("underwater_state"),
                "decline_geometry":        struct.get("decline_geometry"),
                # graph conflicts count
                "n_graph_conflicts":       len(graph_c),
                # kernel
                "kernel_fdr_cleared":      kernel.get("fdr_cleared"),
                # meta
                "allowed_behavior":        row.get("allowed_behavior"),
                "bottom_as_of":            bottom.get("as_of"),
            })
        return rows
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def panel() -> dict:
    """Context Lobe operator panel. Never raises."""
    # Try primary then fallback
    raw: dict | None = _read_json(_CTX_PRIMARY)
    artifact_path = _CTX_PRIMARY

    if raw is None:
        raw = _read_json(_CTX_FALLBACK)
        artifact_path = _CTX_FALLBACK

    if raw is None:
        return {
            "ok":            True,
            "error":         (
                "mastermind_context.json not yet written — "
                "runs on Mac host nightly; absent in fresh CI checkouts."
            ),
            "schema":         None,
            "as_of":          None,
            "produced_at":    None,
            "is_context_only": True,
            "freshness":      None,
            "age_hours":      None,
            "lobes":          {},
            "lobe_manifest":  [],
            "candidates":     [],
            "n_candidates_total": 0,
            "n_candidates_shown": 0,
            "gap_notes":      [],
        }

    produced_at   = raw.get("produced_at")
    # Freshness: prefer produced_at, fall back to file mtime
    freshness_ts  = produced_at or _file_mtime_iso(artifact_path)
    age_hours     = _age_hours(freshness_ts)

    candidates    = _candidate_block(raw)
    cc_total      = len(raw.get("candidate_context") or {})

    return {
        "ok":                 True,
        "schema":             raw.get("schema"),
        "as_of":              raw.get("as_of"),
        "produced_at":        produced_at,
        "is_context_only":    raw.get("is_context_only", True),
        "freshness":          freshness_ts,
        "age_hours":          age_hours,
        "lobes":              _lobes_block(raw),
        "lobe_manifest":      _lobe_manifest_block(raw),
        "candidates":         candidates,
        "n_candidates_total": cc_total,
        "n_candidates_shown": len(candidates),
        "gap_notes":          list(raw.get("gap_notes") or []),
    }
