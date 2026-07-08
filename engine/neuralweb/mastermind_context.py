"""engine.neuralweb.mastermind_context — Neural Web → Mastermind bridge compiler.

PURPOSE
-------
Assembles one compact, versioned, authority-stamped context artifact from
committed NW outputs so the Mastermind bot can consume Neural Web synthesis
as pure advisory context — without the bot having to parse a dozen raw stores.

AUTHORITY CONTRACT (standing law for this bridge)
-------------------------------------------------
All five authority booleans are FALSE. Every field is context-only.
Promotions require: pre-registered shadow definitions, accrued shadow evidence,
Fable review, registry come-back date. This ruling IS the review for the
prompt-text-only promotion at the pre-registered arming condition (§1.7).

TWO-TIER LOBE MODEL (ruling §3.1)
-----------------------------------
(a) AUTO-MANIFEST (zero-touch tier)
    Scans config/synapse.yml for artifacts whose external_consumers list
    contains 'mastermind:context'. Each tagged artifact gets a generic
    envelope row {artifact_id, path, asof, stale, tier, horizon_role,
    storage, has_rich_summary}. Tagging an artifact is the entire cost of
    making a new lobe visible to Mastermind.

(b) REGISTERED SUMMARIZERS (rich tier)
    LOBE_SUMMARIZERS: ordered dict of {lobe_name: (source_paths, fn)}.
    Each summarizer is try/except-wrapped — a failure adds a gap_notes
    entry and never aborts the build.

CANDIDATE UNIVERSE RULE (ruling §3.1)
--------------------------------------
ALL tickers on us_standouts (buy/watch/laggards — note: eligible/universe
are scalar counts, not lists) UNION altdata/mastermind (signals +
broken_signals), PLUS radar_ticker tickers ONLY where:
  - bottom_state != 'WATCH', OR
  - trigger_tier is non-null, OR
  - an options row exists.
Rows are sparse (null fields omitted). Hard cap 250 rows. gap_notes on
truncation.

NUMPY JSON GOTCHA (house law)
------------------------------
data/options_entry/state.parquet contains numpy dtypes (int64, float64,
bool). json.dumps raises TypeError on these. Coerce all values to native
Python before serialisation.

ENVELOPE STAMP
--------------
Applied via engine.neuralweb.envelope.stamp(). artifact_id must be
pre-registered in config/synapse.yml.

WRAPPER PROHIBITION
-------------------
Envelope keys are siblings on the top-level dict, never a nested wrapper.
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

# ─────────────────────────────────────────────────────────────────────────────
# Schema identity
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = "neural_web_mastermind_context.v1"
ARTIFACT_ID = "neuralweb-mastermind-context"
SITE_ARTIFACT_ID = "site-neuralweb-mastermind-context"

# Hard row cap for candidate_context (ruling §3.1)
CANDIDATE_ROW_CAP = 250

# Freshness threshold in hours for lobe stale determination
LOBE_FRESHNESS_SLA_HOURS = 30.0

# Top-N contradiction records for book_context
TOP_CONTRADICTIONS_N = 6

# Kernel FDR note
_KERNEL_STANDING_LAW = (
    "kernel 'armed' means display-ready (sufficient history), NOT FDR-cleared. "
    "No survivor has FDR clearance before the 2026-10-01 batch. "
    "Never use kernel signals for sizing or entry gating until fdr_cleared=True."
)

# Claim reliability standing law (RUL-C2, RUL-C10 — display context only)
_CLAIM_RELIABILITY_STANDING_LAW = (
    "qledger reliability is 5d-only and ACCRUING. "
    "No family is promotion-ready. "
    "Per-source reliability does not exist yet (source_tier/channel ontology fill is near-zero). "
    "Nothing here may rank, gate, or condition any signal or allocation (display context only). "
    "Horizon 5d is the sole graded horizon; 21d/63d grades have not yet matured. "
    "Desks without a hit_rate are salience-only (direction=0 claims, not hit-gradeable — "
    "graded on excess only)."
)

# Top-N families per desk to include in claim_reliability lobe (keep payload small)
_CLAIM_RELIABILITY_TOP_FAMILIES_N = 5

# Cycle-pattern standing law (CPI P6 wave 1 — display context only)
_CYCLE_PATTERN_STANDING_LAW = (
    "cycle-pattern turn-hazard is DISPLAY/CONTEXT ONLY (CPI consumer matrix). "
    "Only cells with gate_status PASS carry validated model probabilities "
    "(W4.2 vs family-stratified KM); PRIOR cells are KM base rates. "
    "Nothing here may originate, score, escalate, rank, gate, or size — "
    "board_rank / oracle_escalation / sector_central_direction_score / "
    "position_sizing are forbidden consumers."
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    # engine/neuralweb/mastermind_context.py → up 3 → repo root
    return Path(__file__).resolve().parent.parent.parent


def _read_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on any failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("mastermind_context: cannot read %s — %s", path, exc)
        return None


def _asof_of(obj: dict | None) -> str | None:
    if not isinstance(obj, dict):
        return None
    for k in ("as_of", "asof", "produced_at", "generated_at", "generated_utc", "date"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v[:10]
    return None


def _is_stale(asof_str: str | None, sla_hours: float = LOBE_FRESHNESS_SLA_HOURS) -> bool:
    if not asof_str:
        return True
    try:
        asof_date = datetime.fromisoformat(asof_str[:10])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_hours = (now - asof_date).total_seconds() / 3600
        return age_hours > sla_hours
    except Exception:  # noqa: BLE001
        return True


def _sparse(d: dict) -> dict:
    """Return dict with None/NaN values removed (sparse rows)."""
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        out[k] = v
    return out


def _coerce_numpy(obj: Any) -> Any:
    """Recursively coerce numpy scalar types to native Python for json.dumps.

    House gotcha (qledger-numpy-json-dumps-zeroes-ledger memory): np.int64
    and friends raise TypeError in json.dumps. This traverses the structure
    and converts them all to native Python types. Works without importing
    numpy at module level (optional dep).
    """
    try:
        import numpy as np  # noqa: PLC0415
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _coerce_numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_numpy(v) for v in obj]
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Auto-manifest scanner
# ─────────────────────────────────────────────────────────────────────────────

def _build_lobe_manifest(registry: dict, repo: Path, now: datetime) -> list[dict]:
    """Scan synapse.yml for artifacts tagged mastermind:context; build manifest rows."""
    artifacts = registry.get("artifacts") or {}
    rows = []
    for artifact_id, entry in artifacts.items():
        consumers = entry.get("external_consumers") or []
        if "mastermind:context" not in consumers:
            continue
        path_str = entry.get("path", "")
        artifact_path = repo / path_str if path_str else None
        asof = None
        stale = None  # unknown until we read the file
        if artifact_path and artifact_path.exists():
            if path_str.endswith(".parquet"):
                # Parquet artifacts cannot be read via json.loads.
                # Leave asof=None and stale=None (unknown) rather than
                # reporting stale=True, which would produce a spurious
                # perma-stale flag (e.g. options-entry-state).
                pass
            else:
                try:
                    obj = json.loads(artifact_path.read_text(encoding="utf-8"))
                    asof = _asof_of(obj)
                    stale = _is_stale(asof)
                except Exception:  # noqa: BLE001
                    stale = None
        rows.append({
            "artifact_id": artifact_id,
            "path": path_str,
            "asof": asof,
            "stale": stale,
            "tier": entry.get("tier", ""),
            "horizon_role": entry.get("horizon_role", ""),
            "storage": entry.get("storage", ""),
            "has_rich_summary": False,  # will be patched by summarizers below
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Lobe summarizers — each independently try/except-wrapped
# ─────────────────────────────────────────────────────────────────────────────

def _summarize_market(repo: Path) -> tuple[dict, str | None]:
    """Distill data/neuralweb/world_state.json into the market lobe."""
    ws = _read_json(repo / "data" / "neuralweb" / "world_state.json")
    if not ws:
        return {}, "world_state.json absent or unreadable"
    # Distill the required sub-blocks
    lobe: dict = {}
    for key in ("verdict", "radar", "vol", "breadth", "rotation", "liquidity",
                "alerts", "data_health", "contradictions", "live_overlay", "sources"):
        v = ws.get(key)
        if v is not None:
            lobe[key] = v
    # Regime — subset only (ruling §3.1 exact subset keys)
    regime_raw = ws.get("regime") or {}
    lobe["regime"] = {
        "quad": regime_raw.get("quad"),
        "quad_name": regime_raw.get("quad_name", ""),
        "confidence": regime_raw.get("confidence"),
        "cycle_tag": regime_raw.get("cycle_tag", ""),
        "transition_state": regime_raw.get("transition_state", ""),
        "flip_margin": regime_raw.get("flip_margin"),
        "liquidity_overlay": regime_raw.get("liquidity_overlay", ""),
        "asof": regime_raw.get("asof", ""),
    }
    return lobe, None


def _summarize_reliability(repo: Path) -> tuple[dict, str | None]:
    """Distill kernel_families.json + kernel_decisions.json.

    MANDATORY re-labeling (ruling §1.4):
    - 'armed' from families → 'display_armed' (means display-ready, NOT FDR)
    - 'fdr_cleared' = membership in kernel_decisions.survivors[] (empty until 2026-10-01)
    - NEVER emit a bare 'armed' key.
    """
    kf = _read_json(repo / "data" / "neuralweb" / "kernel_families.json")
    kd = _read_json(repo / "data" / "neuralweb" / "kernel_decisions.json")
    if not kf and not kd:
        return {}, "kernel_families.json and kernel_decisions.json both absent"

    survivors: list[str] = []
    if isinstance(kd, dict):
        survivors = kd.get("survivors") or []

    families_out: dict = {}
    if isinstance(kf, dict):
        for name, fam in (kf.get("families") or {}).items():
            if not isinstance(fam, dict):
                continue
            entry: dict = {}
            # Re-label: display_armed from 'armed'; NEVER emit bare 'armed'
            entry["display_armed"] = bool(fam.get("armed", False))
            entry["fdr_cleared"] = name in survivors
            for fld in ("horizon_curve", "recency_trend", "staleness"):
                v = fam.get(fld)
                if v is not None:
                    entry[fld] = v
            families_out[name] = entry

    lobe: dict = {
        "families": families_out,
        "kernel_decisions": _sparse({
            "batch_id": kd.get("batch_id") if kd else None,
            "run_at": kd.get("run_at") if kd else None,
            "n_survivors": kd.get("n_survivors") if kd else None,
            "n_eligible": kd.get("n_eligible") if kd else None,
            "next_batch_due": kd.get("next_batch_due") if kd else None,
        }) if kd else {},
        "standing_law": _KERNEL_STANDING_LAW,
    }
    return lobe, None


def _summarize_contradictions(repo: Path) -> tuple[dict, str | None]:
    """Extract contradiction_summary + records from confluence_graph.json."""
    cg = _read_json(repo / "data" / "neuralweb" / "confluence_graph.json")
    if not cg:
        return {}, "confluence_graph.json absent or unreadable"
    lobe = {
        "summary": cg.get("contradiction_summary") or {},
        "records": cg.get("contradiction_records") or [],
    }
    return lobe, None


def _summarize_bottom_sensors(repo: Path) -> tuple[dict, str | None]:
    """Global counts-only summary from site/neuralwebdata/bottom_sensors.json.

    Per ruling §3.1: book_context gets counts-only, no ticker lists. The full
    per-ticker rows are exposed in candidate_context (per-ticker bottom row).
    """
    bs = _read_json(repo / "site" / "neuralwebdata" / "bottom_sensors.json")
    if not bs:
        return {}, "site/neuralwebdata/bottom_sensors.json absent or unreadable"

    rows = bs.get("rows") or []
    # Count distribution of bottom_state and trigger_tier
    bottom_state_counts: dict[str, int] = {}
    trigger_tier_counts: dict[str, int] = {}
    for row in rows:
        bs_val = row.get("bottom_state") or "unknown"
        bottom_state_counts[bs_val] = bottom_state_counts.get(bs_val, 0) + 1
        tt_val = row.get("trigger_tier")
        if tt_val is not None:
            trigger_tier_counts[str(tt_val)] = trigger_tier_counts.get(str(tt_val), 0) + 1

    lobe = {
        "as_of": bs.get("as_of"),
        "counts": {
            "bottom_state": bottom_state_counts,
            "trigger_tier": trigger_tier_counts,
        },
        "n_rows": bs.get("n_rows") or len(rows),
    }
    return lobe, None


def _summarize_options_entry(repo: Path) -> tuple[dict, str | None]:
    """Gate summary from data/options_entry/gate.json."""
    gate_path = repo / "data" / "options_entry" / "gate.json"
    gate = _read_json(gate_path)
    if not gate:
        return {}, "data/options_entry/gate.json absent or unreadable"
    lobe = {
        "gate": _sparse({
            "scored": gate.get("scored"),
            "status": gate.get("status"),
            "weight": gate.get("weight"),
            "note": gate.get("note"),
        }),
        "as_of": gate.get("generated_at"),
    }
    return lobe, None


def _summarize_cortex(repo: Path) -> tuple[dict, str | None]:
    """Verbatim cortex memo + probation (ruling §3.1)."""
    memo = _read_json(repo / "data" / "neuralweb" / "cortex" / "memo.json")
    prob = _read_json(repo / "data" / "neuralweb" / "cortex" / "probation.json")
    if not memo and not prob:
        return {}, "cortex/memo.json and cortex/probation.json both absent"
    lobe = {}
    if memo:
        lobe["memo"] = memo
    if prob:
        lobe["probation"] = prob
    return lobe, None


def _summarize_macro_weather(repo: Path) -> tuple[dict, str | None]:
    """Distill macro climate from world_state.json + data/macro_snapshots/latest.json.

    Returns a gap when data/macro_snapshots/latest.json is absent — the snapshot
    file is created by PR-C; absence means PR-C has not yet landed, so
    ``has_rich_summary`` must NOT be patched onto the manifest row (red-team §5.4).

    Serialised lobe budget: ≤ 12 KB (RUL-M8).
    Macro ETF/futures tickers are admissible as macro-level records per RUL-M8;
    they are NOT candidate names.  The no-new-names invariant is tested by
    tests/test_macro_context_authority.py.
    """
    snapshot_path = repo / "data" / "macro_snapshots" / "latest.json"
    if not snapshot_path.exists():
        return {}, "data/macro_snapshots/latest.json absent (PR-C not landed)"

    try:
        snapshot = _read_json(snapshot_path)
        if not isinstance(snapshot, dict):
            return {}, "data/macro_snapshots/latest.json unreadable or not a dict"

        ws = _read_json(repo / "data" / "neuralweb" / "world_state.json")
        if not isinstance(ws, dict):
            return {}, "world_state.json absent — cannot build macro_weather"

        # ── Core identity ─────────────────────────────────────────────────────
        asof = snapshot.get("asof")
        macro_context_id = snapshot.get("macro_context_id")
        labels = snapshot.get("labels") or {}

        # ── Quads per market (snapshot v1 domain keys: us/china/hk/canada) ────
        us_labels = labels.get("us") or {}
        china_labels = labels.get("china") or {}
        hk_labels = labels.get("hk") or {}
        canada_labels = labels.get("canada") or {}

        # ── FX block from world_state fx_dollar lobe ──────────────────────────
        fx_ws = ws.get("fx_dollar") or {}
        tx_ws = fx_ws.get("transmission") or {}
        fx_block = {
            "regime": fx_ws.get("regime"),
            "usd_trend": (fx_ws.get("dollar_desk") or {}).get("trend"),
            "headwind_for": (tx_ws.get("headwind_for") or [])[:5],
            "tailwind_for": (tx_ws.get("tailwind_for") or [])[:5],
        }

        # ── Rates block from world_state rates_transmission + rates_credit ────
        rt_ws = ws.get("rates_transmission") or {}
        rc_ws = ws.get("rates_credit") or {}
        yc = rt_ws.get("yield_curve") or {}
        yc_regime = yc.get("regime") or {}
        yc_recession = yc.get("recession") or {}

        # Transmission headwinds/tailwinds: compact list of asset names
        hw_assets = [h.get("asset") for h in (rt_ws.get("headwinds") or []) if isinstance(h, dict) and h.get("asset")]
        tw_assets = [t.get("asset") for t in (rt_ws.get("tailwinds") or []) if isinstance(t, dict) and t.get("asset")]

        rates_block = {
            "yield_curve_regime": yc_regime.get("key"),
            "recession_risk": yc_recession.get("risk"),
            "transmission_headwinds": hw_assets[:5],
            "transmission_tailwinds": tw_assets[:3],
        }

        # ── Credit block from rates_credit ────────────────────────────────────
        credit_block = {
            "health_label": rc_ws.get("health_label"),
            "cycle_phase": rc_ws.get("cycle_phase"),
        }

        # ── Commodity block from commodity_context ────────────────────────────
        cc_ws = ws.get("commodity_context") or {}
        commodity_block = {
            "regime": cc_ws.get("regime"),
            "favored": cc_ws.get("favored"),
        }

        # ── Cross-asset block from cross_asset_flows (R6) ─────────────────────
        ca_ws = ws.get("cross_asset_flows") or {}
        ca_corr = ca_ws.get("correlation") or {}
        ca_im_raw = ca_ws.get("intermarket") or []
        ca_block = {
            "regime": ca_ws.get("regime"),
            "correlation_concentration": ca_corr.get("verdict") if isinstance(ca_corr, dict) else None,
            "absorption_pctile": ca_corr.get("absorption_pctile") if isinstance(ca_corr, dict) else None,
            "intermarket_top": ca_im_raw[:3] if isinstance(ca_im_raw, list) else [],
            "breadth": ca_ws.get("breadth"),
            "leadlag_verdict": (ca_ws.get("leadlag") or {}).get("verdict"),
        }

        # ── Label deltas from macro_deltas ────────────────────────────────────
        md_ws = ws.get("macro_deltas") or {}
        deltas_raw = md_ws.get("transitions") or []
        deltas_14d = deltas_raw[:10]

        # ── Contradiction note from world_state contradictions ────────────────
        contra_ws = ws.get("contradictions") or {}
        n_contra = contra_ws.get("n") or 0
        contradiction_note = f"{n_contra} contradiction pairs active" if n_contra else "no contradictions"

        lobe: dict = {
            "asof": asof,
            "macro_context_id": macro_context_id,
            "us_quad": us_labels.get("us_quad"),
            "china_quad": china_labels.get("china_quad"),
            "hk_quad": hk_labels.get("hk_quad"),
            "canada_quad": canada_labels.get("canada_quad"),
            "fx": fx_block,
            "rates": rates_block,
            "credit": credit_block,
            "commodity": commodity_block,
            "cross_asset": ca_block,
            "deltas_14d": deltas_14d,
            "contradiction_note": contradiction_note,
            "display_only": True,
        }

        return lobe, None

    except Exception as exc:  # noqa: BLE001
        log.warning("mastermind_context: macro_weather summarizer failed — %s", exc)
        return {}, f"macro_weather: {exc}"
def _summarize_claim_reliability(repo: Path) -> tuple[dict, str | None]:
    """Distill site/qledger/track_record.json into the claim_reliability lobe.

    Per RUL-C2: key is 'claim_reliability', never 'reliability'.
    Per RUL-C3: read-only over qledger; no semantic changes.
    Per RUL-C10: LLM may cite these stats, never adjust them.

    Fail-open: data/governance/claim_accountability.json is written by the
    sibling PR-B (W-A) and may not yet exist — its absence is noted via
    gap_notes, not a lobe failure.
    """
    tr = _read_json(repo / "site" / "qledger" / "track_record.json")
    if not tr:
        return {}, "site/qledger/track_record.json absent or unreadable"

    by_desk_raw = tr.get("by_desk")
    by_desk_raw = by_desk_raw if isinstance(by_desk_raw, dict) else {}

    # Build per-desk summary — horizon_d=5 only (all graded claims are 5d)
    desks_out: dict = {}
    for desk, horizon_map in by_desk_raw.items():
        h5 = horizon_map.get("5") if isinstance(horizon_map, dict) else None
        if not isinstance(h5, dict):
            continue
        entry: dict = {"horizon_d": 5}
        hit_rate = h5.get("hit_rate")
        if hit_rate is not None:
            entry["hit_rate"] = hit_rate
        wilson_ci_low = h5.get("wilson_ci_low")
        if wilson_ci_low is not None:
            entry["wilson_ci_low"] = wilson_ci_low
        n_obs = h5.get("n_obs")
        if n_obs is not None:
            entry["n"] = n_obs
        state = h5.get("state")
        if state is not None:
            entry["state"] = state
        desks_out[desk] = entry

    # Top-N families by n_obs (bounded payload)
    by_family_raw = tr.get("by_family")
    by_family_raw = by_family_raw if isinstance(by_family_raw, dict) else {}
    families_with_n: list[tuple[str, int, dict]] = []
    for fam, horizon_map in by_family_raw.items():
        h5 = horizon_map.get("5") if isinstance(horizon_map, dict) else None
        if not isinstance(h5, dict):
            continue
        n_obs = h5.get("n_obs") or 0
        families_with_n.append((fam, n_obs, h5))
    families_with_n.sort(key=lambda x: x[1], reverse=True)

    families_out: dict = {}
    for fam, _n, h5 in families_with_n[:_CLAIM_RELIABILITY_TOP_FAMILIES_N]:
        entry: dict = {"horizon_d": 5}
        hit_rate = h5.get("hit_rate")
        if hit_rate is not None:
            entry["hit_rate"] = hit_rate
        wilson_ci_low = h5.get("wilson_ci_low")
        if wilson_ci_low is not None:
            entry["wilson_ci_low"] = wilson_ci_low
        n_obs = h5.get("n_obs")
        if n_obs is not None:
            entry["n"] = n_obs
        state = h5.get("state")
        if state is not None:
            entry["state"] = state
        families_out[fam] = entry

    lobe: dict = {
        "desks": desks_out,
        "top_families": families_out,
        "as_of": tr.get("generated_at") or tr.get("as_of"),
        "standing_law": _CLAIM_RELIABILITY_STANDING_LAW,
    }

    # Fail-open: claim_accountability.json built by sibling PR-B (W-A)
    # Absence is noted inside the lobe (accountability_gap key) — this is the
    # bridge's gap_notes pattern for missing sibling artifacts.  The lobe itself
    # succeeds (returns None gap) because track_record.json was read OK.
    ca = _read_json(repo / "data" / "governance" / "claim_accountability.json")
    if ca is None:
        lobe["accountability_gap"] = (
            "data/governance/claim_accountability.json absent — "
            "sibling PR-B (W-A audit) has not yet merged; "
            "falsifier_coverage and gradeability metrics not yet available"
        )
    else:
        # Include summary-level accountability stats (coverage only, no semantic change)
        summary = ca.get("summary") or {}
        if summary:
            lobe["accountability_summary"] = _sparse({
                "falsifier_coverage": summary.get("falsifier_coverage"),
                "hit_gradeable_share": summary.get("hit_gradeable_share"),
                "as_of": summary.get("as_of"),
            })

    return lobe, None


def _summarize_cycle_pattern(repo: Path) -> tuple[dict, str | None]:
    """CPI P6 wave 1: compact cycle-pattern turn-hazard context.

    Reads ONLY the committed adapter artifact
    data/neuralweb/cycle_pattern_state.json (scripts/build_cycle_pattern_state.py)
    — never the cycle-pattern lake directly (CPI consumer-matrix rule).

    Counts-only in the lobe (the bottom_sensors discipline): gate verdicts,
    entity/family counts, and the truth-registry summary. Per-entity hazard
    rows stay in the artifact (read_cycle_pattern_state cortex tool).
    Every probability downstream must carry its gate verdict — PRIOR cells
    are KM base rates, not validated model output (UI-HZ-1: no naked
    probabilities). Display/context only: may never originate, score, or
    escalate.
    """
    state = _read_json(repo / "data" / "neuralweb" / "cycle_pattern_state.json")
    if not state:
        return {}, "data/neuralweb/cycle_pattern_state.json absent or unreadable"

    entities = state.get("entities") or []
    families: dict[str, int] = {}
    n_with_hazard = 0
    for e in entities:
        if not isinstance(e, dict):
            continue
        fam = e.get("family") or "unknown"
        families[fam] = families.get(fam, 0) + 1
        if any(e.get(k) is not None for k in ("hazard_1m_p", "hazard_3m_p", "hazard_6m_p")):
            n_with_hazard += 1

    lobe: dict = {
        "as_of": state.get("asof"),
        "model_epoch": state.get("model_epoch"),
        "gate_status": state.get("gate_status") or {},
        "n_entities": len(entities),
        "n_with_hazard": n_with_hazard,
        "families": dict(sorted(families.items())),
        "truth_summary": state.get("truth_summary") or {},
        "standing_law": _CYCLE_PATTERN_STANDING_LAW,
    }
    if state.get("degraded_notes"):
        lobe["degraded_notes"] = state["degraded_notes"]
    return lobe, None


# Registry: ordered list of (lobe_name, summarizer_fn)
# Each fn signature: (repo: Path) -> (lobe_dict, gap_note | None)
LOBE_SUMMARIZERS: dict[str, Any] = {
    "market": _summarize_market,
    "reliability": _summarize_reliability,
    "contradictions": _summarize_contradictions,
    "bottom_sensors": _summarize_bottom_sensors,
    "options_entry": _summarize_options_entry,
    "cortex": _summarize_cortex,
    "macro_weather": _summarize_macro_weather,
    "claim_reliability": _summarize_claim_reliability,
    "cycle_pattern": _summarize_cycle_pattern,
}

# Map summarizer lobe names to their primary artifact IDs for manifest patching
_LOBE_TO_ARTIFACT_IDS: dict[str, list[str]] = {
    "market": ["world-state"],
    "reliability": ["kernel-families", "kernel-decisions"],
    "contradictions": ["confluence-graph"],
    "bottom_sensors": ["bottom-sensors-json"],
    "options_entry": ["options-entry-gate"],
    "cortex": ["cortex-memo"],
    "macro_weather": ["macro-snapshots-latest"],
    "claim_reliability": ["site-qledger-track-record"],
    "cycle_pattern": ["cycle-pattern-state"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Candidate context builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_candidate_context(repo: Path, gap_notes: list[str]) -> dict:
    """Build per-ticker candidate_context following the scope rule (ruling §3.1).

    Universe = standouts (buy/watch/laggards) ∪ altdata signals/broken_signals
               ∪ radar_ticker tickers where actionable NW context exists.

    Per-row: bottom (from bottom_sensors), options (from state.parquet),
             graph_conflicts (contradiction records mentioning ticker/sector),
             kernel caveat, allowed_behavior='annotate_only'.
    """
    # --- Standouts tickers ---
    standouts_path = repo / "site" / "factordata" / "us_standouts.json"
    standouts_tickers: set[str] = set()
    try:
        ss = _read_json(standouts_path)
        if isinstance(ss, dict):
            for key in ("buy", "watch", "laggards"):
                lst = ss.get(key) or []
                if isinstance(lst, list):
                    for item in lst:
                        if isinstance(item, dict):
                            t = item.get("ticker") or item.get("symbol")
                        else:
                            t = str(item)
                        if t:
                            standouts_tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: us_standouts read failed — {exc}")

    # --- Altdata mastermind tickers ---
    altdata_path = repo / "site" / "altdata" / "mastermind.json"
    altdata_tickers: set[str] = set()
    try:
        am = _read_json(altdata_path)
        if isinstance(am, dict):
            for key in ("signals", "broken_signals"):
                lst = am.get(key) or []
                if isinstance(lst, list):
                    for item in lst:
                        if isinstance(item, dict):
                            t = item.get("ticker") or item.get("symbol")
                            if t:
                                altdata_tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: altdata mastermind read failed — {exc}")

    # --- Bottom sensors index ---
    bottom_map: dict[str, dict] = {}
    try:
        bs = _read_json(repo / "site" / "neuralwebdata" / "bottom_sensors.json")
        if isinstance(bs, dict):
            for row in (bs.get("rows") or []):
                ticker = row.get("symbol") or row.get("ticker")
                if ticker:
                    bottom_map[ticker] = row
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: bottom_sensors index failed — {exc}")

    # --- Options state index (compact summary subset for size budget) ---
    # Full per-ticker options data is at data/options_entry/state.parquet.
    # We keep only the most contextually meaningful fields to stay within the 200KB budget.
    _OPTIONS_CONTEXT_COLS = (
        "as_of", "iv30", "ivspread_rel", "skew", "net_doi", "doi_pc",
        "fresh_contracts", "fresh_premium_mn", "zerodte_share", "gamma_regime",
        "pin_risk", "gex_confirm_verdict", "evidence_quality",
        "wall_up_dist_pct", "wall_down_dist_pct",
    )
    options_map: dict[str, dict] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        opts_path = repo / "data" / "options_entry" / "state.parquet"
        if opts_path.exists():
            df = pd.read_parquet(opts_path)
            # Only load context columns that exist
            cols = [c for c in _OPTIONS_CONTEXT_COLS if c in df.columns]
            if "ticker" in df.columns:
                df_sub = df[["ticker"] + cols]
            else:
                df_sub = df[cols]
            for _, row in df_sub.iterrows():
                ticker = row.get("ticker") if "ticker" in df_sub.columns else None
                if ticker:
                    row_dict = {c: row[c] for c in cols if c in row.index}
                    options_map[str(ticker)] = _coerce_numpy(row_dict)
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: options state read failed — {exc}")

    # --- Contradiction records ---
    contradiction_records: list[dict] = []
    try:
        cg = _read_json(repo / "data" / "neuralweb" / "confluence_graph.json")
        if isinstance(cg, dict):
            contradiction_records = cg.get("contradiction_records") or []
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: confluence_graph read failed — {exc}")

    # --- Radar tickers with actionable NW context ---
    radar_actionable: set[str] = set()
    try:
        rt = _read_json(repo / "site" / "basketdata" / "radar_ticker.json")
        if isinstance(rt, dict):
            for item in (rt.get("tickers") or []):
                ticker = item.get("ticker") if isinstance(item, dict) else None
                if not ticker:
                    continue
                bottom_row = bottom_map.get(ticker, {})
                bottom_state = bottom_row.get("bottom_state") if bottom_row else None
                trigger_tier = bottom_row.get("trigger_tier") if bottom_row else None
                has_options = ticker in options_map
                # Include only if actionable NW context exists
                if bottom_state != "WATCH" or trigger_tier is not None or has_options:
                    radar_actionable.add(ticker)
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: radar_ticker read failed — {exc}")

    # --- Combined universe ---
    candidate_universe = standouts_tickers | altdata_tickers | radar_actionable

    # --- Build per-ticker rows ---
    result: dict[str, dict] = {}
    for ticker in sorted(candidate_universe):
        row: dict = {}

        # Bottom row — compact context subset for size budget.
        # Full schema: site/neuralwebdata/bottom_sensors.json
        _BOTTOM_CONTEXT_COLS = (
            "as_of", "bottom_state", "trigger_tier", "trigger_age_ticks",
            "coiled", "star", "coiled_fire", "hold_state",
            "dist_21d_low_pct", "dist_126d_high_pct",
            "earnings_next_date", "earnings_days_to",
            "entry_quality_band", "squeeze_state",
        )
        if ticker in bottom_map:
            br_full = bottom_map[ticker]
            br = {k: br_full[k] for k in _BOTTOM_CONTEXT_COLS if k in br_full}
            row["bottom"] = _sparse(br)

        # Options row (sparse, numpy-coerced)
        if ticker in options_map:
            or_ = dict(options_map[ticker])
            or_.pop("ticker", None)
            row["options"] = _sparse(_coerce_numpy(or_))

        # Graph conflicts mentioning this ticker (word-boundary match on original case
        # to avoid substring false-positives: 'F'⊂'growth', 'ON'⊂'transition' etc.)
        conflicts = []
        _ticker_pat = re.compile(
            r"(?<![A-Za-z])" + re.escape(ticker) + r"(?![A-Za-z])"
        )
        for rec in contradiction_records:
            rec_str = json.dumps(rec, default=str)
            if _ticker_pat.search(rec_str):
                conflicts.append(rec)
        if conflicts:
            row["graph_conflicts"] = conflicts

        # Kernel caveat (brief ref; full standing_law in lobes.reliability.standing_law)
        row["kernel"] = {"fdr_cleared": False, "note": "see lobes.reliability.standing_law"}

        row["allowed_behavior"] = "annotate_only"
        result[ticker] = row

    # Hard cap
    if len(result) > CANDIDATE_ROW_CAP:
        original_count = len(result)
        # Keep standouts + altdata first (highest priority), then radar
        priority = list(standouts_tickers | altdata_tickers)
        priority_set = set(priority)
        others = [t for t in sorted(result.keys()) if t not in priority_set]
        keep = sorted(priority_set & set(result.keys()))[:CANDIDATE_ROW_CAP]
        remaining = CANDIDATE_ROW_CAP - len(keep)
        if remaining > 0:
            keep += others[:remaining]
        result = {t: result[t] for t in keep}
        gap_notes.append(
            f"candidate_context: truncated from {original_count} to {CANDIDATE_ROW_CAP} rows "
            f"(standouts+altdata prioritised)"
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Book context builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_book_context(
    lobes: dict,
    candidate_context: dict,
    gap_notes: list[str],
) -> dict:
    """Build book_context: counts and macro contradiction records, NO ticker lists.

    Per ruling §3.1 red-team: book_context must carry NO bottom-sensors symbol
    outside the candidate intake union (standouts ∪ altdata ∪ radar). The test
    'book_context no-new-names' asserts this. We never include bottom_state
    symbol lists — only count dictionaries.
    """
    # Top macro contradictions (records from contradictions lobe, ≤6)
    top_macro_contradictions: list[dict] = []
    try:
        cont_lobe = lobes.get("contradictions") or {}
        records = cont_lobe.get("records") or []
        top_macro_contradictions = records[:TOP_CONTRADICTIONS_N]
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"book_context: top_macro_contradictions failed — {exc}")

    # Decaying families (from cortex memo if available)
    decaying_families: list = []
    try:
        cortex_lobe = lobes.get("cortex") or {}
        memo = cortex_lobe.get("memo") or {}
        decaying_families = memo.get("decaying_families") or []
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"book_context: decaying_families failed — {exc}")

    # Bottom summary counts — from bottom_sensors lobe (counts only, never ticker lists)
    bottom_summary_counts: dict = {}
    try:
        bs_lobe = lobes.get("bottom_sensors") or {}
        bottom_summary_counts = bs_lobe.get("counts") or {}
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"book_context: bottom_summary_counts failed — {exc}")

    return {
        "top_macro_contradictions": top_macro_contradictions,
        "decaying_families": decaying_families,
        "bottom_summary_counts": bottom_summary_counts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Freshness index
# ─────────────────────────────────────────────────────────────────────────────

def _build_freshness(lobes: dict, lobe_manifest: list[dict]) -> dict:
    """Build per-lobe freshness entries."""
    freshness: dict = {}

    # From summarized lobes
    asof_sources: dict[str, tuple[str | None, bool]] = {
        "market": (
            _asof_of(lobes.get("market", {}).get("regime")),
            False,
        ),
        "reliability": (
            _asof_of(lobes.get("reliability", {}).get("kernel_decisions")),
            False,
        ),
        "contradictions": (
            _asof_of(lobes.get("contradictions", {}).get("summary")),
            False,
        ),
        "bottom_sensors": (
            lobes.get("bottom_sensors", {}).get("as_of"),
            False,
        ),
        "options_entry": (
            lobes.get("options_entry", {}).get("as_of"),
            False,
        ),
        "cortex": (
            _asof_of(lobes.get("cortex", {}).get("memo")),
            False,
        ),
        "macro_weather": (
            lobes.get("macro_weather", {}).get("asof"),
            False,
        ),
        "claim_reliability": (
            lobes.get("claim_reliability", {}).get("as_of"),
            False,
        ),
    }
    for lobe_name, (asof, _stale_override) in asof_sources.items():
        stale = _is_stale(asof)
        freshness[lobe_name] = {"as_of": asof, "stale": stale}

    return freshness


# ─────────────────────────────────────────────────────────────────────────────
# Main build function
# ─────────────────────────────────────────────────────────────────────────────

def build_context(
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict:
    """Assemble the mastermind context artifact. Returns the (unstamped) payload dict.

    All errors in sub-blocks are absorbed — the function always returns a
    partial artifact rather than raising.

    Parameters
    ----------
    root:
        Repo root override.
    now:
        UTC datetime for the artifact timestamp.

    Returns
    -------
    dict
        Payload conforming to the neural_web_mastermind_context.v1 schema.
        Envelope keys are NOT yet applied — caller must call stamp().
    """
    repo = _repo_root(root)
    now = now or datetime.now(timezone.utc)
    gap_notes: list[str] = []
    source_artifacts: list[str] = []

    # Load synapse registry for auto-manifest
    try:
        from engine.neuralweb.synapse import load_registry  # noqa: PLC0415
        registry = load_registry(repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("mastermind_context: synapse registry load failed — %s", exc)
        registry = {"artifacts": {}}
        gap_notes.append(f"lobe_manifest: synapse registry unavailable — {exc}")

    # ── Auto-manifest (zero-touch tier) ──────────────────────────────────────
    lobe_manifest = _build_lobe_manifest(registry, repo, now)

    # Track which artifact IDs have rich summaries
    artifact_id_to_manifest_idx: dict[str, int] = {
        row["artifact_id"]: i for i, row in enumerate(lobe_manifest)
    }

    # ── Registered summarizers (rich tier) ───────────────────────────────────
    lobes: dict = {}
    for lobe_name, summarizer_fn in LOBE_SUMMARIZERS.items():
        try:
            lobe_data, gap = summarizer_fn(repo)
            lobes[lobe_name] = lobe_data
            if gap:
                gap_notes.append(f"lobe.{lobe_name}: {gap}")
            else:
                # Mark all associated artifacts in the manifest as has_rich_summary
                for aid in _LOBE_TO_ARTIFACT_IDS.get(lobe_name, []):
                    idx = artifact_id_to_manifest_idx.get(aid)
                    if idx is not None:
                        lobe_manifest[idx]["has_rich_summary"] = True
        except Exception as exc:  # noqa: BLE001
            lobes[lobe_name] = {}
            gap_notes.append(f"lobe.{lobe_name}: summarizer raised — {exc}")
            log.warning("mastermind_context: lobe '%s' summarizer failed — %s", lobe_name, exc)

    # Source artifacts list
    source_artifacts = [
        "data/neuralweb/world_state.json",
        "data/neuralweb/kernel_families.json",
        "data/neuralweb/kernel_decisions.json",
        "data/neuralweb/confluence_graph.json",
        "site/neuralwebdata/bottom_sensors.json",
        "data/options_entry/gate.json",
        "data/options_entry/state.parquet",
        "data/neuralweb/cortex/memo.json",
        "data/neuralweb/cortex/probation.json",
        "data/neuralweb/cycle_pattern_state.json",
        "site/factordata/us_standouts.json",
        "site/altdata/mastermind.json",
        "site/basketdata/radar_ticker.json",
    ]

    # ── Candidate context ─────────────────────────────────────────────────────
    candidate_context = _build_candidate_context(repo, gap_notes)

    # ── Freshness index ───────────────────────────────────────────────────────
    freshness = _build_freshness(lobes, lobe_manifest)

    # ── Book context ──────────────────────────────────────────────────────────
    book_context = _build_book_context(lobes, candidate_context, gap_notes)

    # ── True data timestamp for top-level as_of ───────────────────────────────
    # Must be the oldest lobe data timestamp, NOT build time (ruling §3.3 /
    # PERCEPTION_CONTRACTS: 'asof = TRUE data timestamp per artifact').
    # W2 reader gates whole-artifact staleness on this field (age > 4 days →
    # absent-stale). Using build time would make the gate permanently green even
    # when all lobes carry stale data. We take min() over non-None freshness
    # asof values so the field is conservative: if any lobe is stale, as_of
    # reflects the oldest data date. generated_utc remains the build stamp.
    _lobe_asofs = [
        v["as_of"]
        for v in freshness.values()
        if isinstance(v, dict) and isinstance(v.get("as_of"), str) and v["as_of"]
    ]
    _data_asof: str = min(_lobe_asofs) if _lobe_asofs else now.strftime("%Y-%m-%d")

    # ── Assemble payload ──────────────────────────────────────────────────────
    payload: dict = {
        "schema": SCHEMA,
        "as_of": _data_asof,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_context_only": True,
        "authority": {
            "can_add_candidates": False,
            "can_raise_size": False,
            "can_lower_size": False,
            "can_block_entry": False,
            "can_force_exit": False,
            "notes": "All fields advisory until explicit Fable-approved promotion.",
        },
        "freshness": freshness,
        "lobes": lobes,
        "lobe_manifest": lobe_manifest,
        "candidate_context": candidate_context,
        "book_context": book_context,
        "gap_notes": gap_notes,
        "source_artifacts": source_artifacts,
        # Envelope keys added by stamp() below
        "schema_version": 1,
        "produced_by": "",
        "produced_at": "",
        "inputs_hash": "",
        "tier": "display",
    }
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Write helper
# ─────────────────────────────────────────────────────────────────────────────

def _write_json_bytes(path: Path, obj: dict) -> bytes:
    """Write JSON artifact. Uses compact serialisation (no indent) to stay within
    the 200KB size budget — this artifact is machine-consumed by the Mastermind
    bot, not human-browsed. Consistency check: json.loads(text) round-trips cleanly.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # separators=(',', ': ') gives compact JSON (no trailing spaces after colons)
    # while remaining RFC-compliant. ensure_ascii=False preserves any non-ASCII.
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)
    path.write_text(raw, encoding="utf-8")
    return raw.encode("utf-8")


def build_and_write(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_canonical: Path | None = None,
    out_site: Path | None = None,
) -> dict:
    """Build context, stamp envelope, write both copies, return stamped payload.

    Writes:
    - data/neuralweb/mastermind_context.json  (canonical)
    - site/neuralwebdata/mastermind_context.json  (public copy, byte-identical)

    Parameters
    ----------
    root:
        Repo root override.
    now:
        UTC datetime for the envelope stamp. Injectable for test determinism.
    out_canonical, out_site:
        Path overrides for test isolation.

    Raises
    ------
    OSError
        Only if writing the artifact itself fails.
    """
    repo = _repo_root(root)
    now = now or datetime.now(timezone.utc)

    payload = build_context(root=repo, now=now)

    # Apply envelope stamp
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        from engine.neuralweb.synapse import load_registry  # noqa: PLC0415
        registry = load_registry(repo)
        stamped = stamp(payload, artifact_id=ARTIFACT_ID, registry=registry, now=now)
    except Exception as exc:  # noqa: BLE001
        log.warning("mastermind_context: envelope stamp failed — %s; writing unstamped", exc)
        stamped = payload

    # Determine output paths
    canonical = out_canonical or (repo / "data" / "neuralweb" / "mastermind_context.json")
    site_copy = out_site or (repo / "site" / "neuralwebdata" / "mastermind_context.json")

    # Write canonical
    _write_json_bytes(canonical, stamped)
    log.info("mastermind_context: written canonical → %s", canonical)

    # Write byte-identical site copy (same bytes = same hash = same public contract)
    site_copy.parent.mkdir(parents=True, exist_ok=True)
    import shutil  # noqa: PLC0415
    shutil.copy2(canonical, site_copy)
    log.info("mastermind_context: written site copy → %s", site_copy)

    return stamped
