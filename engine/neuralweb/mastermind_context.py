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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Schema identity
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = "neural_web_mastermind_context.v1"
ARTIFACT_ID = "neuralweb-mastermind-context"
SITE_ARTIFACT_ID = "site-neuralweb-mastermind-context"

# NW→dashboards export lane: compact site-wide macro header feed (~2KB).
# Mirrors Mastermind's brain/neural_web_context.py market_plane() shape,
# extended with liquidity_plumbing + cortex run-status blocks.
# COMMIT PATH (RUL-P10): data/neuralweb/market_plane.json (canonical) +
# site/neuralwebdata/market_plane.json (public twin) — both git-committed,
# same as siblings. Designed consumer: Terminal top bar + committee hero
# strip (display-only; nothing here may rank, gate, escalate, or size).
MARKET_PLANE_SCHEMA = "neuralweb.market_plane.v1"
MARKET_PLANE_ARTIFACT_ID = "neuralweb-market-plane"

# Lobes whose as_of tracks MARKET DATA dates (nightly market artifacts), as
# opposed to governance/deliberation cadences (reliability = quarterly kernel
# batches, cortex = LLM memo, claim_reliability = accruing ledger grades).
# freshest_market_asof = max over these; the conservative min() as_of
# semantics are deliberately unchanged (ruling §3.3).
_MARKET_DATA_LOBES: tuple[str, ...] = (
    "market", "contradictions", "bottom_sensors", "options_entry", "macro_weather",
)

# Hard row cap for candidate_context (ruling §3.1)
CANDIDATE_ROW_CAP = 250

# Size cap raised from 200KB→300KB (Build 3: analyst block adds rows; prior
# headroom was only ~1.7KB per Build-1 review).
CONTEXT_SIZE_CAP_BYTES = 300 * 1024  # 300 KB

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

_THEMATIC_STATE_STANDING_LAW = (
    "thematic_state is DISPLAY/CONTEXT ONLY (TIL W5). "
    "Nothing here may originate a signal, raise a score, gate, size, or rank. "
    "Falsifier-fired flags are context observations — not trade triggers. "
    "Pathway data: loser legs are AVOID-shaped evidence, never short calls "
    "(TI-R5 fence). No runtime shock-to-beneficiary escalation."
)

# Risk Radar reliability standing law (display context only — graded forward-ledger history)
_RISK_RADAR_RELIABILITY_STANDING_LAW = (
    "risk_radar_reliability is DISPLAY/CONTEXT ONLY. "
    "Rates are graded forward-ledger history (deterministic math over committed rows). "
    "No LLM, no model scores, no signal origination anywhere in this lobe. "
    "hit_rate=null means insufficient_n (< 5 graded rows) — not a confirmed miss. "
    "Nothing here may gate, rank, size, or escalate any alert or position. "
    "Use 'hit rate' and 'track record' in user-facing copy (CI-guards bar the v-word)."
)

# Minimum graded-row count before a rate is meaningful (honest-null floor)
_RR_MIN_N = 5

# How many top scares to surface per market (by alert count)
_RR_TOP_SCARES_N = 2

# Market-structure standing law (MSP-W3, MSP-R2/R3 — display context only)
# Embedding this in the lobe ensures every consumer that loads the lobe also loads the law.
_MARKET_STRUCTURE_STANDING_LAW = (
    "market_structure is DISPLAY/CONTEXT ONLY (MSP-R1). "
    "Positioning keys (vc_*, cta_*, agreement) are model estimates of mechanical behavior "
    "(vol-control proxies, CTA trend models) — NOT observed dealer or fund books. "
    "FUSION LAW (MSP-R2/R3, Signal Commons restated): fusing gamma, VC, or CTA keys into "
    "any score, regime verdict, rank, gate, or allocation is ILLEGAL. "
    "VC and CTA are context only — always shown side-by-side, never blended into a composite. "
    "No LLM may originate, escalate, or de-escalate from these keys. "
    "Nothing here may gate, rank, size, or escalate any authority surface."
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


def _is_stale(
    asof_str: str | None,
    sla_hours: float = LOBE_FRESHNESS_SLA_HOURS,
    now: datetime | None = None,
) -> bool:
    """Weekend-aware staleness: age is measured in TRADING time.

    Markets don't print new data over the weekend, so a Friday as_of is the
    freshest possible market data all of Saturday/Sunday. Simple weekday-aware
    allowance: when as_of falls on Fri/Sat/Sun, the SLA clock starts on the
    following Monday ("as_of Friday → allow until Monday + SLA"). Weekday
    as_of behaviour is unchanged.

    `now` is injectable for test determinism; defaults to UTC now.
    """
    if not asof_str:
        return True
    try:
        asof_date = datetime.fromisoformat(asof_str[:10])
        # Fri(4)/Sat(5)/Sun(6) → advance the SLA base to the following Monday.
        wd = asof_date.weekday()
        if wd >= 4:
            asof_date = asof_date + timedelta(days=7 - wd)
        if now is None:
            now = datetime.now(timezone.utc)
        now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
        age_hours = (now_naive - asof_date).total_seconds() / 3600
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
    # liquidity_plumbing: RRP/TGA/netliq quality numbers so bot/ask surfaces
    # can cite them (already display-only labels upstream — no recompute here).
    for key in ("verdict", "radar", "vol", "breadth", "rotation", "rotation_events",
                "liquidity", "liquidity_plumbing",
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
        fx_deltas = fx_ws.get("deltas") or {}
        # MSX-1 additions — null-tolerant; keys absent in old artifacts degrade to None
        _fx_sc = fx_ws.get("state_changes") or {}
        _fx_dom_sc = fx_ws.get("regime_radar_dominant_scenario") or {}
        _fx_st_ext = fx_ws.get("strength_extremes") or {}
        fx_block = {
            "regime": fx_ws.get("regime"),
            "usd_trend": (fx_ws.get("dollar_desk") or {}).get("trend"),
            "headwind_for": (tx_ws.get("headwind_for") or [])[:5],
            "tailwind_for": (tx_ws.get("tailwind_for") or [])[:5],
            # v2 compact delta fields for LLM context
            # calendar days from streak start to latest ledger asof (inclusive)
            "usd_trend_days": (fx_deltas.get("usd_trend") or {}).get("days_in_state"),
            "regime_since": (fx_deltas.get("usd_regime") or {}).get("since"),
            "top_scenario": (
                (fx_ws.get("scenario_intensity") or [{}])[0].get("name")
                if fx_ws.get("scenario_intensity") else None
            ),
            # MSX-1: state_changes compact summary (current states only; producer-
            # stamped flips — complements the ledger-derived delta fields above)
            "state_changes_summary": {
                k: (v.get("current") if isinstance(v, dict) else None)
                for k, v in _fx_sc.items()
            } if _fx_sc else None,
            # dominant stress scenario + intensity
            "dominant_stress_scenario": _fx_dom_sc.get("key"),
            "dominant_stress_intensity": _fx_dom_sc.get("intensity"),
            # strength extremes
            "strength_strongest": _fx_st_ext.get("strongest"),
            "strength_weakest": _fx_st_ext.get("weakest"),
            "strength_horizon": _fx_st_ext.get("horizon"),
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
        cc_deltas = cc_ws.get("deltas") or {}
        cc_conf = cc_ws.get("confluence") or {}
        cc_breadth = cc_ws.get("breadth") or {}
        cc_ratios = cc_ws.get("ratios") or {}
        commodity_block = {
            "regime": cc_ws.get("regime"),
            "favored": cc_ws.get("favored"),
            # v2 compact fields for LLM context
            "breadth_bucket": cc_breadth.get("bucket"),
            "shock_state": (cc_ws.get("index") or {}).get("shock_state"),
            "shock_state_days": (cc_deltas.get("commodity_shock_state") or {}).get("days_in_state"),
            "confluence_standouts": [
                {"name": s.get("name"), "state": s.get("state")}
                for s in (cc_conf.get("standouts") or [])[:3]
            ],
            "copper_gold_dir": (cc_ratios.get("copper_gold") or {}).get("dir"),
            "gold_silver_dir": (cc_ratios.get("gold_silver") or {}).get("dir"),
        }

        # ── Cross-asset block from cross_asset_flows (R6) ─────────────────────
        ca_ws = ws.get("cross_asset_flows") or {}
        ca_corr = ca_ws.get("correlation") or {}
        ca_im_raw = ca_ws.get("intermarket") or []
        # one_bet_cluster: dominant_cluster[:3] (flows.v2 additive, None-safe)
        _dc_raw = ca_ws.get("dominant_cluster")
        _one_bet_cluster = _dc_raw[:3] if isinstance(_dc_raw, list) and _dc_raw else None
        ca_block = {
            "regime": ca_ws.get("regime"),
            "correlation_concentration": ca_corr.get("verdict") if isinstance(ca_corr, dict) else None,
            "absorption_pctile": ca_corr.get("absorption_pctile") if isinstance(ca_corr, dict) else None,
            "intermarket_top": ca_im_raw[:3] if isinstance(ca_im_raw, list) else [],
            "breadth": ca_ws.get("breadth"),
            "leadlag_verdict": (ca_ws.get("leadlag") or {}).get("verdict"),
            "one_bet_cluster": _one_bet_cluster,
            "funding_state": ca_ws.get("funding_state"),
        }

        # ── Label deltas from macro_deltas ────────────────────────────────────
        md_ws = ws.get("macro_deltas") or {}
        deltas_raw = md_ws.get("transitions") or []
        deltas_14d = deltas_raw[:10]

        # ── Contradiction note from world_state contradictions ────────────────
        contra_ws = ws.get("contradictions") or {}
        n_contra = contra_ws.get("n") or 0
        contradiction_note = f"{n_contra} contradiction pairs active" if n_contra else "no contradictions"

        # ── China spine labels (CN-SYS W7 NW adapter) ────────────────────────
        # Read site/chinastatedata/market_state.json for sovereign spine fields.
        # Labels-only per the FB counts-only privacy contract (no raw series).
        # CN-SYS-R1/R13/R14: context_only, no fused score, no LLM origination.
        china_spine_path = repo / "site" / "chinastatedata" / "market_state.json"
        china_spine_block: dict = {
            "china_quad": china_labels.get("china_quad"),
            "phase_label": None,
            "who_controls": None,
            "policy_impulse": None,
            "source": "site/chinastatedata/market_state.json",
        }
        _cn_spine_gap: str | None = None
        if china_spine_path.exists():
            try:
                _cn_raw = json.loads(china_spine_path.read_text(encoding="utf-8"))
                if isinstance(_cn_raw, dict):
                    _ph = _cn_raw.get("phase") or {}
                    _part = _cn_raw.get("participation") or {}
                    _pol = _cn_raw.get("policy") or {}
                    china_spine_block["phase_label"] = _ph.get("phase")
                    china_spine_block["who_controls"] = _part.get("who_controls")
                    china_spine_block["policy_impulse"] = _pol.get("policy_impulse")
                    china_spine_block["as_of"] = _cn_raw.get("as_of")
            except Exception as _exc:  # noqa: BLE001
                _cn_spine_gap = f"china_market_state: read error ({_exc})"
                log.warning("mastermind_context: china spine labels read failed — %s", _exc)
        else:
            _cn_spine_gap = "china_market_state: site/chinastatedata/market_state.json absent (CN-SYS W6 pending)"

        lobe: dict = {
            "asof": asof,
            "macro_context_id": macro_context_id,
            "us_quad": us_labels.get("us_quad"),
            "china_quad": china_labels.get("china_quad"),
            "china": china_spine_block,  # CN-SYS W7: sovereign China spine labels
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
        if _cn_spine_gap:
            lobe["_gap_china_spine"] = _cn_spine_gap

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


def _summarize_thematic_state(repo: Path) -> tuple[dict, str | None]:
    """TIL W5 NW citizenship: compact thematic-state context.

    Reads data/neuralweb/theme_state.json (primary) and
    site/neuralwebdata/theme_thesis.json (for falsifier counts).
    Both produced nightly by scripts/build_thematic_state.py.

    Counts-only pattern (mirrors _summarize_cycle_pattern discipline):
    stage distribution, fired falsifiers, stale-legs count, and a
    short noteworthy list (falsifier fired OR non-WATCH stage).
    Full per-theme payload stays in the artifact (read_theme_state
    cortex/ask_brain tool). Display/context only; may never originate,
    score, or escalate.
    """
    state = _read_json(repo / "data" / "neuralweb" / "theme_state.json")
    if not state:
        return {}, "data/neuralweb/theme_state.json absent or unreadable"

    themes: list = state.get("themes") or []
    stale_legs: list = state.get("stale_legs") or []

    # Stage counts (normalize: strip text/fingerprint suffix)
    stage_counts: dict[str, int] = {}
    for th in themes:
        if not isinstance(th, dict):
            continue
        stage = (th.get("foresight") or {}).get("stage") or "UNKNOWN"
        stage_key = stage.split(" ")[0]
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1

    # Falsifier data from site/neuralwebdata/theme_thesis.json
    n_falsifiers_fired = 0
    fired_list: list[dict] = []
    thesis_path = repo / "site" / "neuralwebdata" / "theme_thesis.json"
    if thesis_path.exists():
        try:
            raw_thesis = _read_json(thesis_path)
            if raw_thesis:
                n_falsifiers_fired = raw_thesis.get("n_falsifier_fired") or 0
                for t in (raw_thesis.get("theses") or []):
                    if not isinstance(t, dict):
                        continue
                    tid = t.get("theme_id", "")
                    for f in (t.get("falsifiers") or []):
                        if isinstance(f, dict) and f.get("fired"):
                            fired_list.append({"theme_id": tid, "falsifier_id": f.get("id")})
        except Exception:  # noqa: BLE001
            pass

    # Noteworthy: falsifier fired OR non-WATCH stage (cap to 6 for size)
    noteworthy: list[dict] = []
    fired_ids = {r["theme_id"] for r in fired_list}
    for th in themes:
        if not isinstance(th, dict):
            continue
        tid = th.get("theme_id", "")
        stage = (th.get("foresight") or {}).get("stage") or "UNKNOWN"
        stage_key = stage.split(" ")[0]
        reasons = []
        if tid in fired_ids:
            reasons.append("falsifier_fired")
        if stage_key not in ("WATCH", "UNKNOWN"):
            reasons.append(f"stage={stage_key}")
        if reasons and len(noteworthy) < 6:
            noteworthy.append({"theme_id": tid, "reason": ", ".join(reasons)})

    lobe: dict = {
        "as_of": state.get("as_of"),
        "n_themes": state.get("n_themes") or len(themes),
        "stage_counts": stage_counts,
        "n_falsifiers_fired": n_falsifiers_fired,
        "falsifiers_fired": fired_list,
        "n_stale_legs": len(stale_legs),
        "noteworthy": noteworthy,
        "standing_law": _THEMATIC_STATE_STANDING_LAW,
    }
    return lobe, None


def _summarize_mastermind_ai(repo: Path) -> tuple[dict, str | None]:
    """W-AI: the Mastermind AI reflection lobe — the trading bot as a lobe of the web.

    Reads ONLY data/governance/mastermind_feedback_summary.json (the whitelisted,
    staleness-gated reverse-bridge summary built by engine/neuralweb/mastermind_feedback.py)
    — never site/mastermind/ directly. Carries (a) the bot's reflection/nudge state in
    counts+codes, and (b) the ACK block the bot reads back to advance its directive
    statuses — this lobe IS the macro→bot half of the two-way dialogue.

    Counts/codes only (the reverse bridge already enforces the leak-proof whitelist).
    Display/context only: may never originate, score, or escalate.
    """
    summ = _read_json(repo / "data" / "governance" / "mastermind_feedback_summary.json")
    if not summ:
        return {}, "data/governance/mastermind_feedback_summary.json absent or unreadable"

    state = summ.get("state") or "absent"
    lobe: dict = {
        "as_of": summ.get("asof") or (summ.get("generated_utc") or "")[:10] or None,
        "state": state,
        "source_schema": summ.get("source_schema"),
    }
    if state == "present":
        nudges = summ.get("nudges") or []
        by_sev: dict[str, int] = {}
        for n in nudges:
            if isinstance(n, dict):
                sev = n.get("severity") or "low"
                by_sev[sev] = by_sev.get(sev, 0) + 1
        directives = summ.get("operator_directives") or []
        rf = summ.get("reflection") or {}
        lobe.update({
            "nudges": {
                "n": len(nudges),
                "by_severity": by_sev,
                "top_codes": [n.get("code") for n in nudges[:5] if isinstance(n, dict)],
            },
            "directives": {
                "n": len(directives),
                "ids": [d.get("id") for d in directives[:10] if isinstance(d, dict)],
            },
            "reflection": {
                "state": rf.get("state"),
                "contract_drift_n": len(rf.get("contract_drift") or []),
                "coverage_rate": (rf.get("coverage") or {}).get("coverage_rate"),
                "context_seen_rate": (rf.get("context_quality") or {}).get("seen_rate"),
                "attribution_state": (rf.get("attribution") or {}).get("state"),
            },
            # THE ACK — the bot's reader keys directive/nudge status advancement off this.
            "ack": summ.get("ack") or {"nudge_codes_seen": [], "directive_ids_seen": []},
        })
    return lobe, None


def _summarize_rr_market(sc_market: dict) -> dict:
    """Distil one MARKET block from the scorecard into the lobe shape.

    Returns a dict with monitoring health, y1 alert stats, top-2 scares,
    watch/caution precursor stats, and recovery rate.  All rates are null
    when n < _RR_MIN_N; the caller will emit 'insufficient_n' markers.
    """
    monitoring: dict = sc_market.get("monitoring") or {}
    windows: dict = sc_market.get("windows") or {}
    y1: dict = windows.get("y1") or {}

    # ---- alerts (y1 window) ----
    y1_alerts: dict = y1.get("alerts") or {}
    alert_n = y1_alerts.get("n") or 0
    alert_tp = y1_alerts.get("tp") or 0
    alert_hit_rate = y1_alerts.get("hit_rate")  # null when n<5 per scorecard contract

    # ---- watch/caution precursor (y1) ----
    y1_wc: dict = y1.get("watch_caution") or {}
    wc_n = y1_wc.get("n") or 0
    wc_tp = y1_wc.get("tp") or 0
    wc_rate = y1_wc.get("precursor_rate")  # null when n<5

    # ---- top-2 scares by alert count (y1) ----
    by_scare: dict = y1.get("by_scare") or {}
    scare_list = sorted(
        ((k, (v or {}).get("n") or 0, (v or {})) for k, v in by_scare.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    top_scares: list[dict] = []
    for scare_key, scare_n, scare_data in scare_list[:_RR_TOP_SCARES_N]:
        scare_tp = scare_data.get("tp") or 0
        top_scares.append({
            "scare": scare_key,
            "n": scare_n,
            "hit_rate": scare_data.get("hit_rate"),  # null when n<5
            "insufficient_n": scare_n < _RR_MIN_N,
        })

    # ---- recovery (y1) ----
    y1_rec: dict | None = y1.get("recovery")
    recovery_out: dict | None = None
    if y1_rec is not None:
        rec_n = y1_rec.get("n") or 0
        recovery_out = {
            "n": rec_n,
            "rate": y1_rec.get("rate"),  # null when n<5
            "insufficient_n": rec_n < _RR_MIN_N,
        }

    out: dict = {
        "monitoring": {
            "log_fresh": monitoring.get("log_fresh", False),
            "last_logged_days_ago": monitoring.get("last_logged_days_ago"),
            "ungraded_backlog": monitoring.get("ungraded_backlog") or 0,
            "graded_n": monitoring.get("graded_n") or 0,
        },
        "y1_alerts": {
            "n": alert_n,
            "tp": alert_tp,
            "hit_rate": alert_hit_rate,
            "insufficient_n": alert_n < _RR_MIN_N,
        },
        "y1_watch_caution": {
            "n": wc_n,
            "tp": wc_tp,
            "precursor_rate": wc_rate,
            "insufficient_n": wc_n < _RR_MIN_N,
        },
        "top_scares": top_scares,
    }
    if recovery_out is not None:
        out["recovery"] = recovery_out

    asof_last = sc_market.get("asof_last_row")
    if asof_last:
        out["asof_last_row"] = asof_last

    return out


def _summarize_risk_radar_reliability(repo: Path) -> tuple[dict, str | None]:
    """Distil site/riskdata/scorecard.json into the risk_radar_reliability lobe.

    Source: the frozen cross-builder scorecard artifact (schema risk_radar_scorecard.v1).
    The artifact carries us + every intl radar market (additive-only key set).
    Market order: us/cn/hk/ca first (existing order preserved), then any
    additional keys found in the scorecard sorted alphabetically (CSP-W1
    dynamic order — additive-only #2687 pattern, never pattern-match/limit).
    Distils each market via _summarize_rr_market().

    Standing laws:
    - 100% deterministic math over already-graded rows (no LLM, no invented scores).
    - hit_rate=null → emit insufficient_n=True (honest-null floor; n < _RR_MIN_N).
    - Absent/malformed file → fail-soft (gap note returned, empty lobe).
    - The word 'validated' is banned from all emitted text.
    """
    path = repo / "site" / "riskdata" / "scorecard.json"
    sc = _read_json(path)
    if sc is None:
        return {}, "site/riskdata/scorecard.json absent or unreadable"

    if not isinstance(sc, dict):
        return {}, "site/riskdata/scorecard.json: unexpected top-level type (not dict)"

    schema = sc.get("schema")
    markets_raw: dict = sc.get("markets") or {}
    if not isinstance(markets_raw, dict):
        return {}, (
            f"site/riskdata/scorecard.json: 'markets' field missing or wrong type "
            f"(schema={schema!r})"
        )

    markets_out: dict = {}
    # Dynamic market order: us/cn/hk/ca first (existing order preserved), then
    # any additional market keys found in the scorecard sorted alphabetically.
    # Additive-only #2687 pattern — never pattern-match/limit the key set.
    _CORE_MARKETS = ("us", "cn", "hk", "ca")
    _extra_markets = sorted(
        k for k in markets_raw if k not in _CORE_MARKETS
    )
    _MARKET_ORDER = _CORE_MARKETS + tuple(_extra_markets)
    for mkt in _MARKET_ORDER:
        mkt_data = markets_raw.get(mkt)
        if not isinstance(mkt_data, dict):
            # Market absent (no ledger yet) — emit a minimal absent marker
            markets_out[mkt] = {
                "monitoring": {"log_fresh": False},
                "_absent": True,
            }
            continue
        try:
            markets_out[mkt] = _summarize_rr_market(mkt_data)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "mastermind_context: risk_radar_reliability market=%s failed — %s", mkt, exc
            )
            markets_out[mkt] = {"_error": str(exc)}

    lobe: dict = {
        "generated_at": sc.get("generated_at"),
        "markets": markets_out,
        "standing_law": _RISK_RADAR_RELIABILITY_STANDING_LAW,
    }
    return lobe, None


def _summarize_contagion(repo: Path) -> tuple[dict, str | None]:
    """Distil world_state.contagion_regime into the contagion lobe (CSP-W1).

    Source: data/neuralweb/world_state.json (contagion_regime sub-block).
    All fields are engine-originated, is_context_only=True, display_only=True.
    LLM consumers read this — they never originate or escalate from it (CSP-R4).
    Fail-soft: absent world_state or absent contagion_regime sub-block → empty
    lobe with gap note.

    Standing laws:
    - 100% deterministic re-projection of already-computed RSR organs.
    - No LLM-originated content; no invented scores.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    """
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    ws = _read_json(ws_path)
    if ws is None:
        return {}, "data/neuralweb/world_state.json absent or unreadable"

    cr = (ws.get("contagion_regime") or {}) if isinstance(ws, dict) else {}
    if not cr:
        return {}, "world_state.contagion_regime absent (pre-CSP-W1 build)"

    state = cr.get("state")
    leadership_state = cr.get("leadership_state")
    us_spillover = cr.get("us_spillover")
    n_alert = cr.get("n_alert")
    d3_alert = cr.get("d3_alert")
    n_mature = cr.get("n_mature")
    origin_complex = cr.get("origin_complex")
    intl_markets = cr.get("intl_markets_in_alert") or []
    degraded = cr.get("degraded") or []
    asof = cr.get("asof")

    lobe: dict = {
        "is_context_only": True,
        "display_only": True,
        "asof": asof,
        "state": state,
        "origin_complex": origin_complex,
        "leadership_state": leadership_state,
        "us_spillover": us_spillover,
        "n_alert": n_alert,
        "d3_alert": d3_alert,
        "n_mature": n_mature,
        "intl_markets_in_alert": intl_markets,
        "honesty_note": "accruing — unproven; does not change the score",
    }
    if degraded:
        lobe["degraded"] = degraded

    return lobe, None


def _summarize_fx_dollar(repo: Path) -> tuple[dict, str | None]:
    """Distil world_state.fx_dollar into the fx_dollar lobe.

    Source: data/neuralweb/world_state.json (fx_dollar sub-block, composed by
    world_state._compose_fx_dollar from data/forex/latest.json).
    All fields are engine-originated, is_context_only=True, display_only=True.
    LLM consumers read this — they never originate or escalate from it.
    Fail-soft: absent world_state or absent fx_dollar sub-block → empty lobe
    with gap note.

    Standing laws:
    - 100% deterministic re-projection of already-computed RSR organs.
    - No LLM-originated content; no invented scores.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    """
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    ws = _read_json(ws_path)
    if ws is None:
        return {}, "data/neuralweb/world_state.json absent or unreadable"

    fx = (ws.get("fx_dollar") or {}) if isinstance(ws, dict) else {}
    if not fx:
        return {}, "world_state.fx_dollar absent (pre-FX-transmission build)"

    tx  = (fx.get("transmission") or {}) if isinstance(fx.get("transmission"), dict) else {}
    dd  = (fx.get("dollar_desk") or {}) if isinstance(fx.get("dollar_desk"), dict) else {}
    rr  = (fx.get("regime_radar") or {}) if isinstance(fx.get("regime_radar"), dict) else {}
    asof = fx.get("asof")

    lobe: dict = {
        "is_context_only":    True,
        "display_only":       True,
        "asof":               asof,
        "usd_dir":            tx.get("usd_dir"),
        "lean":               dd.get("lean"),
        "real_rate_regime":   dd.get("real_rate_regime"),
        "usd_valuation":      dd.get("usd_valuation"),
        "trend":              dd.get("trend"),
        "fed_path_lean":      dd.get("fed_path_lean"),
        "liquidity_dir":      dd.get("liquidity_dir"),
        "headwind_for":       (tx.get("headwind_for") or [])[:4],
        "tailwind_for":       (tx.get("tailwind_for") or [])[:4],
        "fx_stress_dominant": rr.get("dominant"),
        "honesty_note":       "context only — measured correlations, not a trade signal",
    }
    return lobe, None


def _summarize_rates_command(repo: Path) -> tuple[dict, str | None]:
    """Distil world_state.rates_command into the rates_command lobe.

    Source: data/neuralweb/world_state.json (rates_command sub-block, composed by
    world_state._compose_rates_command from data/rates_command/latest.json).
    All fields are display_only=True, authority=False.
    LLM consumers read this — they never originate or escalate from it.
    Fail-soft: absent world_state or absent rates_command sub-block -> empty lobe
    with gap note.

    Standing laws:
    - 100% deterministic re-projection of already-computed artifact values.
    - No LLM-originated content; no invented scores; no forward guidance.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    - MRI-R4: never originates a projection/probability; reads existing values only.
    """
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    ws = _read_json(ws_path)
    if ws is None:
        return {}, "data/neuralweb/world_state.json absent or unreadable"

    rc = (ws.get("rates_command") or {}) if isinstance(ws, dict) else {}
    if not rc:
        return {}, "world_state.rates_command absent (pre-rates-command build)"

    lobe: dict = {
        "is_context_only":    True,
        "display_only":       True,
        "authority":          False,
        "asof":               rc.get("asof"),
        "net_state":          rc.get("net_state"),
        "state_label_en":     rc.get("state_label_en"),
        "state_label_zh":     rc.get("state_label_zh"),
        "hawk_score":         rc.get("hawk_score"),
        "ease_score":         rc.get("ease_score"),
        "stance_en":          rc.get("stance_en"),
        "stance_zh":          rc.get("stance_zh"),
        "implied_m12":        rc.get("implied_m12"),
        "policy_rate":        rc.get("policy_rate"),
        "path_plain_en":      rc.get("path_plain_en"),
        "futures_plain_en":   rc.get("futures_plain_en"),
        "honesty_note":       "context only — measured rates data, not a trade signal or forecast",
    }
    return lobe, None


def _summarize_special_sits(repo: Path) -> tuple[dict, str | None]:
    """Distil special_situations context into the special_sits lobe.

    Source: data/special_situations/context/latest.json (special_sits_context.v1).
    Written by scripts/build_special_situations.py; absent until first nightly run.
    Fail-soft: absent or unreadable artifact → empty lobe with gap note.

    Standing laws:
    - 100% deterministic re-projection; no LLM-originated content.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    - is_context_only=True always; display_only=True always.
    """
    ctx_path = repo / "data" / "special_situations" / "context" / "latest.json"
    raw = _read_json(ctx_path)
    if raw is None:
        return {}, "data/special_situations/context/latest.json absent or unreadable"

    try:
        counts = raw.get("counts") or {}
        top_raw = raw.get("top_setups") or []
        arb_raw = raw.get("risk_arb_top") or []
        changes = (raw.get("changes") or {}).get("items") or []

        lobe: dict = {
            "is_context_only": True,
            "display_only": True,
            "asof": raw.get("asof"),
            "n_total": counts.get("total"),
            "n_new_today": counts.get("new_today"),
            "n_grade_a": counts.get("grade_a"),
            "n_grade_b": counts.get("grade_b"),
            "setups_display": [
                {k: s.get(k) for k in ("ticker", "company", "category", "stage", "grade", "score", "why")}
                for s in top_raw[:6] if isinstance(s, dict)
            ],
            "risk_arb_top": arb_raw[:3],
            "n_changes": len(changes) if isinstance(changes, list) else 0,
            "honesty_note": "context only — event tracking, never a signal or sizing input",
        }
        return lobe, None
    except Exception as exc:  # noqa: BLE001
        return {}, f"special_sits summarize failed: {exc}"
def _summarize_theme_rotation(repo: Path) -> tuple[dict, str | None]:
    """Distil world_state.theme_rotation into the theme_rotation lobe.

    Source: data/neuralweb/world_state.json (theme_rotation sub-block, composed
    by world_state._compose_theme_rotation from site/basketdata/theme_context.json).
    All fields are engine-originated, display_only=True, is_context_only=True.
    LLM consumers read this — they never originate or escalate from it.
    Fail-soft: absent world_state or absent theme_rotation sub-block → empty lobe
    with gap note.

    Standing laws:
    - 100% deterministic re-projection of already-computed display-tier keys.
    - No LLM-originated content; no invented scores.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    """
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    ws = _read_json(ws_path)
    if ws is None:
        return {}, "data/neuralweb/world_state.json absent or unreadable"

    tr = (ws.get("theme_rotation") or {}) if isinstance(ws, dict) else {}
    if not tr:
        return {}, "world_state.theme_rotation absent (pre-theme-context build)"

    tl = (tr.get("trailing_leader") or {}) if isinstance(tr.get("trailing_leader"), dict) else {}
    strength = (tr.get("strength") or [])[:4]
    migration = tr.get("migration") or {}
    alignment = tr.get("alignment") or {}

    # China sub-block — compact; None when absent (no gap entry)
    cn = tr.get("china")
    china_lobe: dict | None = None
    if cn and isinstance(cn, dict):
        cn_lead_state = cn.get("leadership_state")
        cn_tl_raw = cn.get("trailing_leader") or {}
        cn_tl = cn_tl_raw if isinstance(cn_tl_raw, dict) and cn_tl_raw else {}
        cn_strength = (cn.get("strength") or [])[:4]
        cn_migration = cn.get("migration") or {}
        cn_alignment = cn.get("alignment") or {}
        if cn_lead_state is not None or cn.get("stance_en") is not None:
            china_lobe = {
                "leadership_state": cn_lead_state,
                "stance_en": cn.get("stance_en"),
                "stance_zh": cn.get("stance_zh"),
                "as_of": cn.get("as_of"),
                "trailing_leader_id": cn_tl.get("id"),
                "trailing_leader_name": cn_tl.get("name"),
                "trailing_leader_health": cn_tl.get("health"),
                "trailing_leader_breadth": cn_tl.get("breadth"),
                "trailing_leader_r10": cn_tl.get("r10"),
                "strength_names": [s.get("name") for s in cn_strength if isinstance(s, dict)] or None,
                "migration_absorbing": [x.get("category") for x in (cn_migration.get("absorbing") or []) if isinstance(x, dict)] or None,
                "migration_bleeding": [x.get("category") for x in (cn_migration.get("bleeding") or []) if isinstance(x, dict)] or None,
                "sector_rotation_agrees": cn_alignment.get("sector_rotation_agrees"),
            }

    lobe: dict = {
        "is_context_only": True,
        "display_only": True,
        "as_of": tr.get("as_of"),
        "leadership_state": tr.get("leadership_state"),
        "days_in_state": tr.get("days_in_state"),
        "stance_en": tr.get("stance_en"),
        "stance_zh": tr.get("stance_zh"),
        "trailing_leader_id": tl.get("id"),
        "trailing_leader_name": tl.get("name"),
        "trailing_leader_health": tl.get("health"),
        "trailing_leader_breadth": tl.get("breadth"),
        "trailing_leader_r10": tl.get("r10"),
        "strength_names": [s.get("name") for s in strength if isinstance(s, dict)] or None,
        "migration_absorbing": [
            x.get("category") for x in (migration.get("absorbing") or [])
            if isinstance(x, dict)
        ] or None,
        "migration_bleeding": [
            x.get("category") for x in (migration.get("bleeding") or [])
            if isinstance(x, dict)
        ] or None,
        "sector_rotation_agrees": alignment.get("sector_rotation_agrees"),
        "china": china_lobe,
        "honesty_note": "context only — display-tier leadership read, not a trade signal",
    }
    return lobe, None


def _summarize_market_structure(repo: Path) -> tuple[dict, str | None]:
    """Distil world_state.market_structure into the market_structure lobe.

    Source: data/neuralweb/world_state.json (market_structure sub-block, composed
    by world_state._compose_market_structure from data/market_structure/latest.json).
    All fields are engine-originated, is_context_only=True, display_only=True.
    LLM consumers read this — they never originate or escalate from it.
    Fail-soft: absent world_state or absent market_structure sub-block → empty lobe
    with gap note.

    Standing law (_MARKET_STRUCTURE_STANDING_LAW — MSP-R2/R3):
    - Positioning keys (vc_*, cta_*, agreement) are model estimates, NOT observed books.
    - Fusion into any score/regime verdict is ILLEGAL (Signal Commons restated).
    - 100% deterministic re-projection; no LLM-originated content.
    - Nothing here may gate, rank, size, or escalate any authority surface.
    - The word 'validated' is banned from all emitted text.
    """
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    ws = _read_json(ws_path)
    if ws is None:
        return {}, "data/neuralweb/world_state.json absent or unreadable"

    ms = (ws.get("market_structure") or {}) if isinstance(ws, dict) else {}
    if not ms or ms.get("absent"):
        return {}, "world_state.market_structure absent (pre-MSP-W1 build)"

    g   = (ms.get("gamma") or {}) if isinstance(ms.get("gamma"), dict) else {}
    sys = (ms.get("systematic") or {}) if isinstance(ms.get("systematic"), dict) else {}
    v   = (ms.get("vol") or {}) if isinstance(ms.get("vol"), dict) else {}
    d   = (ms.get("dispersion") or {}) if isinstance(ms.get("dispersion"), dict) else {}

    lobe: dict = {
        "is_context_only":    True,
        "display_only":       True,
        "asof":               ms.get("asof"),
        # gamma sub-block (compact)
        "gamma_regime":       g.get("regime"),
        "net_gex_bn":         g.get("net_gex_bn"),
        "net_gex_pctile":     g.get("net_gex_pctile"),
        "dist_to_flip_pct":   g.get("dist_to_flip_pct"),
        "days_in_regime":     g.get("days_in_regime"),
        # systematic sub-block (MSP-R3: VC and CTA separate, no fused composite)
        "vc_state":           sys.get("vc_state"),
        "vc_alloc_bn":        sys.get("vc_alloc_bn"),
        "cta_state":          sys.get("cta_state"),
        "cta_z":              sys.get("cta_z"),
        "agreement":          sys.get("agreement"),
        # vol sub-block
        "rv_cross_state":     v.get("rv_cross_state"),
        # dispersion sub-block
        "cor1m_regime":       d.get("cor1m_regime"),
        "cor1m_pctile_2y":    d.get("cor1m_pctile_2y"),
        # standing law (embedded so every consumer carries it)
        "standing_law":       _MARKET_STRUCTURE_STANDING_LAW,
        "honesty_note":       "context only — model estimates, never observed books or signal inputs",
    }
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
    "thematic_state": _summarize_thematic_state,
    "mastermind_ai": _summarize_mastermind_ai,
    "risk_radar_reliability": _summarize_risk_radar_reliability,
    "contagion": _summarize_contagion,  # CSP-W1 contagion context lobe
    "fx_dollar": _summarize_fx_dollar,  # FX/dollar transmission context lobe
    "special_sits": _summarize_special_sits,  # SS-NW-W1 special-situations event context lobe
    "theme_rotation": _summarize_theme_rotation,  # theme_context.v1 NW integration
    "market_structure": _summarize_market_structure,  # MSP-W3 market-structure context lobe
    "rates_command": _summarize_rates_command,  # RCB Forward Path board lobe
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
    "thematic_state": ["theme-state"],
    "mastermind_ai": ["mastermind-feedback-summary"],
    "risk_radar_reliability": ["site-riskdata-scorecard"],
    "contagion": ["world-state"],  # CSP-W1: reads world_state.contagion_regime
    "fx_dollar": ["world-state"],  # reads world_state.fx_dollar (from data/forex/latest.json)
    "special_sits": ["special-sits-context-latest"],  # SS-NW-W1: reads context artifact directly
    "theme_rotation": ["theme-context-latest"],  # reads world_state.theme_rotation
    "market_structure": ["market-structure-latest"],  # MSP-W3: reads world_state.market_structure
    "rates_command": ["rates-command-latest"],  # RCB: reads world_state.rates_command (data/rates_command/latest.json)
}


# ─────────────────────────────────────────────────────────────────────────────
# Analyst targets loader (Build 3 — data/analyst/targets.parquet)
# ─────────────────────────────────────────────────────────────────────────────

# Columns projected from the parquet into each candidate row.
# Upstream (collector) pre-computes implied_upside_pct + target_dispersion.
# The builder is a pure projection — no arithmetic here.
_ANALYST_CONTEXT_COLS = (
    "target_mean",
    "implied_upside_pct",
    "target_dispersion",
    "recommendation",
    "num_analysts",
)


def _load_analyst_map(repo: Path, gap_notes: list[str]) -> dict[str, dict]:
    """Load data/analyst/targets.parquet into a {ticker: {...}} index.

    Fail-open: absent or unreadable parquet → empty dict + gap_note (honest-null).
    The builder treats a missing analyst block the same as absent data — the
    candidate row is unaffected and no downstream surface is gated on this.

    DISPLAY/CONTEXT only: fields carry allowed_behavior='annotate_only' in the
    candidate row and may never feed any scored surface.
    """
    path = repo / "data" / "analyst" / "targets.parquet"
    if not path.exists():
        gap_notes.append(
            "candidate_context.analyst: data/analyst/targets.parquet absent "
            "(run collectors/yf_analyst.py to populate)"
        )
        return {}
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        if "ticker" not in df.columns:
            gap_notes.append(
                "candidate_context.analyst: targets.parquet missing 'ticker' column"
            )
            return {}
        out: dict[str, dict] = {}
        cols = [c for c in _ANALYST_CONTEXT_COLS if c in df.columns]
        for _, row in df[["ticker"] + cols].iterrows():
            ticker = row["ticker"]
            if not ticker:
                continue
            entry = {c: row[c] for c in cols if c in row.index}
            # Coerce numpy scalars (pandas returns numpy dtypes from parquet)
            entry = _coerce_numpy(entry)
            # Remove None / NaN values — _sparse contract
            clean: dict = {}
            for k, v in entry.items():
                if v is None:
                    continue
                if isinstance(v, float) and math.isnan(v):
                    continue
                clean[k] = v
            if clean:
                out[str(ticker)] = clean
        return out
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(
            f"candidate_context.analyst: targets.parquet read failed — {exc}"
        )
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Candidate context sub-block helpers (pure projections — no scoring)
# ─────────────────────────────────────────────────────────────────────────────

def _earnings_ctx_for_ticker(
    ticker: str,
    earnings_map: dict[str, Any],
    asof: datetime,
    br_full: dict,
) -> dict:
    """Compute earnings_ctx sub-block for one ticker.

    Pure projection: reads next_date from earnings_map (pre-loaded once).
    days_to_earnings = (next_date - asof).days; is_blackout = 0 < days <= 30.
    shareholder_yield surfaced from bottom_map if present (no recompute).
    Returns {} when no earnings row exists.
    """
    row: dict = {}
    rec = earnings_map.get(ticker)
    if rec is not None:
        next_date_raw = rec.get("next_date")
        if next_date_raw is not None:
            try:
                from datetime import date as _date  # noqa: PLC0415
                if hasattr(next_date_raw, "date"):
                    nd = next_date_raw.date()
                elif isinstance(next_date_raw, str):
                    nd = _date.fromisoformat(str(next_date_raw)[:10])
                else:
                    nd = _date.fromisoformat(str(next_date_raw)[:10])
                asof_date = asof.date() if hasattr(asof, "date") else asof
                days_to = (nd - asof_date).days
                # next_date is already in bottom.earnings_next_date — omit here to
                # avoid duplication and keep payload within 200KB cap.
                row["days_to_earnings"] = days_to
                row["is_blackout"] = bool(0 < days_to <= 30)
            except Exception:  # noqa: BLE001
                pass
    sy = br_full.get("shareholder_yield")
    if sy is not None:
        row["shareholder_yield"] = sy
    return _sparse(row)


def _load_earnings_map(repo: Path, gap_notes: list[str]) -> dict[str, dict]:
    """Load data/earnings/earnings.parquet once; return {ticker: {next_date, ...}}.

    Honest-null on absence (per nwqs-c graceful pattern).
    """
    earnings_map: dict[str, dict] = {}
    ep = repo / "data" / "earnings" / "earnings.parquet"
    if not ep.exists():
        gap_notes.append("candidate_context.earnings_ctx: earnings.parquet absent — block omitted")
        return earnings_map
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(ep, columns=["next_date"])
        for ticker, row in df.iterrows():
            earnings_map[str(ticker)] = {"next_date": row["next_date"]}
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context.earnings_ctx: earnings.parquet read failed — {exc}")
    return earnings_map


def _rpo_ctx_for_ticker(ticker: str, rpo_map: dict[str, dict]) -> dict:
    """Compute visibility sub-block for one ticker from pre-loaded RPO map.

    rpo_rev_ratio = rpo / revenue (guarded: revenue > 0).
    rpo_yoy_pct computed if prior-year RPO exists; else omitted.
    Returns {} when ticker absent from rpo_map.
    """
    rec = rpo_map.get(ticker)
    if rec is None:
        return {}
    row: dict = {}
    rpo = rec.get("rpo")
    revenue = rec.get("revenue")
    prior_rpo = rec.get("prior_rpo")
    # rpo_rev_ratio and rpo_yoy_pct are the display-useful derived values; raw rpo
    # is a large absolute float (e.g. 2.25e+10) and is omitted to keep payload compact.
    if rpo is not None and revenue is not None and isinstance(revenue, (int, float)) and revenue > 0:
        row["rpo_rev_ratio"] = round(rpo / revenue, 4)
    if rpo is not None and prior_rpo is not None and isinstance(prior_rpo, (int, float)) and prior_rpo > 0:
        row["rpo_yoy_pct"] = round((rpo - prior_rpo) / prior_rpo * 100, 2)
    return _sparse(row)


def _load_rpo_map(repo: Path, gap_notes: list[str]) -> dict[str, dict]:
    """Load data/edgar/rpo.parquet once; return {ticker: {rpo, revenue, prior_rpo}}.

    Takes the latest fiscal year per ticker; prior_rpo is the immediately
    preceding year's value (for yoy pct). Honest-null on absence.
    """
    rpo_map: dict[str, dict] = {}
    rp = repo / "data" / "edgar" / "rpo.parquet"
    if not rp.exists():
        gap_notes.append("candidate_context.visibility: rpo.parquet absent — block omitted")
        return rpo_map
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(rp, columns=["ticker", "fy", "rpo", "revenue"])
        df = df.sort_values(["ticker", "fy"])
        for ticker, grp in df.groupby("ticker"):
            rows = grp.reset_index(drop=True)
            latest = rows.iloc[-1]
            rec: dict = {
                "rpo": _coerce_numpy(latest["rpo"]),
                "revenue": _coerce_numpy(latest["revenue"]),
            }
            if len(rows) >= 2:
                rec["prior_rpo"] = _coerce_numpy(rows.iloc[-2]["rpo"])
            rpo_map[str(ticker)] = rec
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context.visibility: rpo.parquet read failed — {exc}")
    return rpo_map


# ─────────────────────────────────────────────────────────────────────────────
# Candidate context builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_candidate_context(
    repo: Path,
    gap_notes: list[str],
    now: datetime | None = None,
) -> dict:
    """Build per-ticker candidate_context following the scope rule (ruling §3.1).

    Universe = standouts (buy/watch/laggards) ∪ altdata signals/broken_signals
               ∪ radar_ticker tickers where actionable NW context exists.

    Per-row: bottom (from bottom_sensors), options (from state.parquet),
             leverage/structural/dilution (from bottom_sensors extended fields),
             earnings_ctx (from earnings.parquet + bottom_sensors),
             visibility (from edgar/rpo.parquet),
             graph_conflicts (contradiction records mentioning ticker/sector),
             kernel caveat, allowed_behavior='annotate_only'.

    All sub-blocks are pure projections — no arithmetic combining fields into
    a composite/score; no field may gate, rank, or size any board surface.
    """
    asof = now or datetime.now(timezone.utc)

    # --- One-shot data loads (outside per-ticker loop) ---
    earnings_map = _load_earnings_map(repo, gap_notes)
    rpo_map = _load_rpo_map(repo, gap_notes)
    # Analyst targets (Build 3 — free yfinance, display/context only, PIT snapshot)
    analyst_map = _load_analyst_map(repo, gap_notes)
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

    # --- CN standouts tickers (SA-W3: parity with us_standouts; context-only) ---
    # site/factordata/china_standouts.json — display-context intake, never gates/ranks.
    # Authority: is_context_only=True; NW-scope wired via mastermind:context tag in
    # synapse.yml (SA-R1 prerequisite).  Never raises.
    #
    # F7 FIX: china_standouts.json has keys buy/laggards/ripening/ripening_falling
    # (no 'watch' key).  Candidate set = buy + ripening (active buy candidates +
    # names approaching buy territory); laggards excluded as they are below-line
    # names not yet at candidate status; ripening_falling excluded as declining
    # momentum names that may be heading off the board.
    cn_standouts_path = repo / "site" / "factordata" / "china_standouts.json"
    try:
        cs = _read_json(cn_standouts_path)
        if isinstance(cs, dict):
            for key in ("buy", "ripening"):
                lst = cs.get(key) or []
                if isinstance(lst, list):
                    for item in lst:
                        if isinstance(item, dict):
                            t = item.get("ticker") or item.get("symbol")
                        else:
                            t = str(item)
                        if t:
                            standouts_tickers.add(t)
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"candidate_context: cn_standouts read failed — {exc}")

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
            # Valuation context slice — display/annotate only; no origination.
            # Pulled from the SAME bottom_sensors row (no new source) so size budget
            # and null hygiene are maintained.  Whole key omitted when all values
            # are None/missing (so the cortex never reads absence as "fairly valued").
            _VALUATION_CONTEXT_COLS = ("ev_sales", "ev_ebit", "p_fcf", "pe")
            val_raw = {k: br_full.get(k) for k in _VALUATION_CONTEXT_COLS if br_full.get(k) is not None}
            val_sparse = _sparse(val_raw)
            if val_sparse:
                row["valuation"] = val_sparse

            # --- leverage block (pure allowlist from bottom_sensors; no arithmetic) ---
            _LEVERAGE_COLS = ("interest_coverage", "net_debt_to_ebitda", "net_debt_to_op_income")
            lev_raw = {k: br_full.get(k) for k in _LEVERAGE_COLS if br_full.get(k) is not None}
            lev_sparse = _sparse(lev_raw)
            if lev_sparse:
                row["leverage"] = lev_sparse

            # --- structural block (decline geometry + underwater state + sponsorship) ---
            # sponsorship_state folded here — do NOT create a separate sponsorship block.
            _STRUCTURAL_COLS = (
                "decline_geometry", "underwater_state",
                "decline_herf", "sponsorship_state",
            )
            struct_raw = {k: br_full.get(k) for k in _STRUCTURAL_COLS if br_full.get(k) is not None}
            struct_sparse = _sparse(struct_raw)
            if struct_sparse:
                row["structural"] = struct_sparse

            # --- dilution block (shelf / takedown / dilution events) ---
            _DILUTION_COLS = ("days_since_shelf", "days_since_takedown", "dilution_events_365d")
            dil_raw = {k: br_full.get(k) for k in _DILUTION_COLS if br_full.get(k) is not None}
            dil_sparse = _sparse(dil_raw)
            if dil_sparse:
                row["dilution"] = dil_sparse

            # --- earnings_ctx block (earnings proximity + optional shareholder_yield) ---
            ec = _earnings_ctx_for_ticker(ticker, earnings_map, asof, br_full)
            if ec:
                row["earnings_ctx"] = ec
        else:
            # No bottom_map row — still attempt earnings_ctx from earnings.parquet only
            ec = _earnings_ctx_for_ticker(ticker, earnings_map, asof, {})
            if ec:
                row["earnings_ctx"] = ec

        # --- visibility block (RPO / revenue visibility from edgar) ---
        vis = _rpo_ctx_for_ticker(ticker, rpo_map)
        if vis:
            row["visibility"] = vis

        # Analyst context block (Build 3 — display/context only, PIT snapshot).
        # Fields are pre-computed upstream by collectors/yf_analyst.py; the builder
        # is a pure projection (no arithmetic here). Omit the whole block when
        # analyst_map has no entry for this ticker (honest-null contract).
        if ticker in analyst_map:
            analyst_entry = analyst_map[ticker]
            analyst_sparse = _sparse({
                "target_mean":          analyst_entry.get("target_mean"),
                "implied_upside_pct":   analyst_entry.get("implied_upside_pct"),
                "target_dispersion":    analyst_entry.get("target_dispersion"),
                "recommendation":       analyst_entry.get("recommendation"),
                "num_analysts":         analyst_entry.get("num_analysts"),
            })
            if analyst_sparse:
                row["analyst"] = analyst_sparse

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
        "data/earnings/earnings.parquet",
        "data/edgar/rpo.parquet",
        "data/analyst/targets.parquet",
    ]

    # ── Candidate context ─────────────────────────────────────────────────────
    candidate_context = _build_candidate_context(repo, gap_notes, now=now)

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

    # Companion freshness stamp: max over MARKET-DATA lobes only (see
    # _MARKET_DATA_LOBES). The conservative min() as_of above is unchanged
    # (ruling §3.3) — freshest_market_asof exists so consumers can show
    # "market data through <date>" without a quarterly kernel batch or an
    # old cortex memo dragging the visible date backwards.
    _mkt_asofs = [
        freshness[name]["as_of"][:10]
        for name in _MARKET_DATA_LOBES
        if isinstance(freshness.get(name), dict)
        and isinstance(freshness[name].get("as_of"), str)
        and freshness[name]["as_of"]
    ]
    _freshest_market_asof: str | None = max(_mkt_asofs) if _mkt_asofs else None

    # ── Assemble payload ──────────────────────────────────────────────────────
    payload: dict = {
        "schema": SCHEMA,
        "as_of": _data_asof,
        "freshest_market_asof": _freshest_market_asof,
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

    # NW→dashboards export lane: market_plane.json (site-wide macro header
    # feed). Fail-open — a plane failure must never block the main context
    # write. Paths derive from `repo`, so test isolation via root=tmp_path
    # keeps the plane inside the tmp tree as well.
    try:
        build_and_write_market_plane(root=repo, now=now)
    except Exception as exc:  # noqa: BLE001
        log.warning("mastermind_context: market_plane build failed (non-fatal) — %s", exc)

    return stamped


# ─────────────────────────────────────────────────────────────────────────────
# market_plane.json — NW→dashboards export lane
# ─────────────────────────────────────────────────────────────────────────────

def _plane_liquidity_block(repo: Path, gaps: list[str]) -> dict:
    """Distill the liquidity_plumbing block for the market plane.

    Primary source: data/neuralweb/liquidity_plumbing.json (nested schema).
    Fallback: world_state.json's embedded liquidity_plumbing block (flat keys).
    Fail-open: all-null block + gaps[] entry when both are absent.
    """
    nulls = {
        "state": None,
        "netliq_bn": None,
        "netliq_d20_bn": None,
        "rrp_buffer_state": None,
        "tga_bn": None,
        "entry_effect": None,
    }
    lp = _read_json(repo / "data" / "neuralweb" / "liquidity_plumbing.json")
    if isinstance(lp, dict):
        return {
            "state": (lp.get("headline") or {}).get("state"),
            "netliq_bn": (lp.get("quantity") or {}).get("netliq_bn"),
            "netliq_d20_bn": (lp.get("quantity") or {}).get("netliq_chg_20d_bn"),
            "rrp_buffer_state": (lp.get("rrp") or {}).get("buffer_state"),
            "tga_bn": (lp.get("treasury") or {}).get("tga_bn"),
            "entry_effect": lp.get("entry_effect"),
        }
    ws = _read_json(repo / "data" / "neuralweb" / "world_state.json")
    ws_lp = (ws or {}).get("liquidity_plumbing")
    if isinstance(ws_lp, dict) and ws_lp.get("available"):
        gaps.append(
            "liquidity_plumbing: liquidity_plumbing.json absent — "
            "fell back to world_state embedded block"
        )
        return {
            "state": ws_lp.get("state"),
            "netliq_bn": ws_lp.get("netliq_bn"),
            "netliq_d20_bn": ws_lp.get("netliq_chg_20d_bn"),
            "rrp_buffer_state": ws_lp.get("rrp_buffer_state"),
            "tga_bn": ws_lp.get("tga_bn"),
            "entry_effect": _sparse({
                "direction": ws_lp.get("entry_effect_direction"),
                "quality": ws_lp.get("entry_effect_quality"),
                "measured_basis": ws_lp.get("entry_effect_basis"),
                "use": ws_lp.get("entry_effect_use"),
            }) or None,
        }
    gaps.append("liquidity_plumbing: liquidity_plumbing.json absent or unreadable")
    return nulls


def build_market_plane(
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict:
    """Assemble the ~2KB market_plane payload (unstamped).

    Site-wide macro header feed for the Terminal top bar + committee hero
    strip. Mirrors Mastermind's brain/neural_web_context.py market_plane()
    shape, sourced from artifacts the bridge compiler already loads:
    world_state.json, liquidity_plumbing.json, confluence_graph.json
    (contradiction_summary), cortex/memo.json (run_status).

    DISPLAY-ONLY: every field is context; is_context_only=True and no
    authority boolean is ever emitted true. Fail-open: each missing input
    produces nulls for its block plus a gaps[] entry — never an exception.
    """
    repo = _repo_root(root)
    now = now or datetime.now(timezone.utc)
    gaps: list[str] = []

    # ── world_state blocks (verdict / regime / vol / breadth) ────────────────
    ws = _read_json(repo / "data" / "neuralweb" / "world_state.json")
    if not isinstance(ws, dict):
        ws = {}
        gaps.append("world_state: data/neuralweb/world_state.json absent or unreadable")

    verdict_raw = ws.get("verdict") or {}
    verdict = {
        "verdict": verdict_raw.get("verdict"),
        "score": verdict_raw.get("score"),
        "label_en": verdict_raw.get("label_en"),
        "label_zh": verdict_raw.get("label_zh"),
    }

    regime_raw = ws.get("regime") or {}
    regime = {
        "quad": regime_raw.get("quad"),
        "quad_name": regime_raw.get("quad_name"),
        "confidence": regime_raw.get("confidence"),
        "cycle_tag": regime_raw.get("cycle_tag"),
        "transition_state": regime_raw.get("transition_state"),
        "flip_margin": regime_raw.get("flip_margin"),
        "liquidity_overlay": regime_raw.get("liquidity_overlay"),
    }

    vol_raw = ws.get("vol") or {}
    vol = {
        "regime": vol_raw.get("regime"),
        "risk_score": vol_raw.get("risk_score"),
    }

    breadth = ws.get("breadth") if isinstance(ws.get("breadth"), dict) else None
    if ws and breadth is None:
        gaps.append("breadth: world_state.breadth absent")

    # ── liquidity plumbing ───────────────────────────────────────────────────
    liquidity_plumbing = _plane_liquidity_block(repo, gaps)

    # ── contradiction count (confluence_graph contradiction_summary) ─────────
    contradiction_count: int | None = None
    cg = _read_json(repo / "data" / "neuralweb" / "confluence_graph.json")
    if isinstance(cg, dict):
        summary = cg.get("contradiction_summary") or {}
        n = summary.get("n")
        if isinstance(n, int):
            contradiction_count = n
        else:
            recs = cg.get("contradiction_records")
            contradiction_count = len(recs) if isinstance(recs, list) else None
    else:
        gaps.append("contradictions: confluence_graph.json absent or unreadable")

    # ── cortex run status ─────────────────────────────────────────────────────
    cortex = {"status": None, "degradation_reason": None}
    memo = _read_json(repo / "data" / "neuralweb" / "cortex" / "memo.json")
    if isinstance(memo, dict):
        rs = memo.get("run_status")
        if isinstance(rs, dict):
            cortex = {
                "status": rs.get("status"),
                "degradation_reason": rs.get("degradation_reason"),
            }
        else:
            gaps.append("cortex: memo.json has no run_status block")
    else:
        gaps.append("cortex: cortex/memo.json absent or unreadable")

    # ── asof + weekend-aware staleness ────────────────────────────────────────
    asof = _asof_of(ws) or verdict_raw.get("asof") or None
    stale = _is_stale(asof, now=now)

    return {
        "schema": MARKET_PLANE_SCHEMA,
        "asof": asof,
        "is_context_only": True,
        "verdict": verdict,
        "regime": regime,
        "vol": vol,
        "breadth": breadth,
        "liquidity_plumbing": liquidity_plumbing,
        "contradiction_count": contradiction_count,
        "cortex": cortex,
        "stale": stale,
        "gaps": gaps,
    }


def build_and_write_market_plane(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_canonical: Path | None = None,
    out_site: Path | None = None,
) -> dict:
    """Build market_plane, stamp envelope, dual-write, return stamped payload.

    Writes (same dual-write pattern as mastermind_context — RUL-P10 commit path):
    - data/neuralweb/market_plane.json  (canonical, git-committed)
    - site/neuralwebdata/market_plane.json  (public copy, byte-identical)
    """
    repo = _repo_root(root)
    now = now or datetime.now(timezone.utc)

    payload = build_market_plane(root=repo, now=now)

    # Envelope stamp (in-place sibling keys, never a wrapper). Registration of
    # MARKET_PLANE_ARTIFACT_ID in config/synapse.yml is owned by a later stage;
    # until it lands, stamp via an inline one-entry registry so the artifact
    # still carries all five envelope keys from day one.
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        registry: dict
        try:
            from engine.neuralweb.synapse import load_registry  # noqa: PLC0415
            registry = load_registry(repo)
        except Exception:  # noqa: BLE001
            registry = {"artifacts": {}}
        if MARKET_PLANE_ARTIFACT_ID not in (registry.get("artifacts") or {}):
            registry = {"artifacts": {MARKET_PLANE_ARTIFACT_ID: {
                "producer": "engine/neuralweb/mastermind_context.py",
                "tier": "display",
            }}}
        stamped = stamp(payload, artifact_id=MARKET_PLANE_ARTIFACT_ID,
                        registry=registry, now=now)
    except Exception as exc:  # noqa: BLE001
        log.warning("market_plane: envelope stamp failed — %s; writing unstamped", exc)
        stamped = payload

    canonical = out_canonical or (repo / "data" / "neuralweb" / "market_plane.json")
    site_copy = out_site or (repo / "site" / "neuralwebdata" / "market_plane.json")

    _write_json_bytes(canonical, stamped)
    log.info("market_plane: written canonical → %s", canonical)

    site_copy.parent.mkdir(parents=True, exist_ok=True)
    import shutil  # noqa: PLC0415
    shutil.copy2(canonical, site_copy)
    log.info("market_plane: written site copy → %s", site_copy)

    return stamped
