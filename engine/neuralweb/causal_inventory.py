"""engine.neuralweb.causal_inventory — CHF-R4 feature inventory builder.

PURPOSE
-------
Builds the causal feature inventory artifact: a versioned, authority-stamped
catalogue of every candidate feature for the causal scout, annotated with
roles, eras, pit_basis, lag constraints, collider risk, and file presence.

AUTHORITY CONTRACT (CHF-R1 — display-only infrastructure)
----------------------------------------------------------
This module produces an INFRASTRUCTURE artifact, not an authority output.
All five authority booleans are unconditionally False.  The inventory is
input to the scout and to human-readable review — it does not rank, gate,
size, or escalate anything.

ROLE VOCABULARY
---------------
candidate_cause    : eligible input cause for edge batteries
target             : outcome variable only (never a cause)
conditioner        : conditioning variable for environment splits
environment_split  : declared split axis (era, quad, regime, etc.)
confounder         : must-adjust-for third variable
mediator           : on the causal path between cause and target
collider           : downstream of two causes — conditioning on it opens a back-door
proxy              : imperfect measure of the true construct
lagged_outcome_echo: a lagged version of the outcome that may create spurious Granger signal
negative_control   : should be null by design — used for specification tests
forbidden_future   : forward-realized outcome; ONLY valid role is target

HARD VALIDATION RULES
---------------------
1. Any feature matching forbidden_causes patterns (from causal_priors.yml)
   may NEVER carry candidate_cause in allowed_roles.  Pattern matching is
   case-insensitive substring match (not prefix).
2. Any feature with 'forbidden_future' in allowed_roles must list ONLY 'target'
   in allowed_roles — no other roles permitted.
3. min_lag_days is stamped by time_grain first (monthly → monthly_grain floor
   21), falling back to cadence (weekly → weekly_publication 5, else
   daily_engine 1).  Values come from causal_priors.yml min_lag_days_by_cadence.

PIT BASIS VOCABULARY (reused from panel_manifest.json, RUL-CC-8)
-----------------------------------------------------------------
pit_live | recomputed_history | vintage | current_snapshot_backfill | display_only

Schema: neuralweb.causal_feature_inventory.v1
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema identity
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.causal_feature_inventory.v1"
ARTIFACT_ID = "causal-feature-inventory"

# ---------------------------------------------------------------------------
# Priors config path (relative to repo root)
# ---------------------------------------------------------------------------

_PRIORS_PATH = Path("config") / "causal_priors.yml"
_NULLS_PATH = Path("data") / "neuralweb" / "causal_nulls.jsonl"

# ---------------------------------------------------------------------------
# Role vocabulary constants
# ---------------------------------------------------------------------------

VALID_ROLES = frozenset({
    "candidate_cause",
    "target",
    "conditioner",
    "environment_split",
    "confounder",
    "mediator",
    "collider",
    "proxy",
    "lagged_outcome_echo",
    "negative_control",
    "forbidden_future",
})

# ---------------------------------------------------------------------------
# Authority block (frozen — CHF-R1)
# ---------------------------------------------------------------------------

_AUTHORITY = {
    "tier": "infrastructure",
    "display_only": True,
    "not_a_signal": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "scored_path_surfaces": [],
}

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Infer repo root from this file's location: engine/neuralweb/causal_inventory.py."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Priors loaders + validators
# ---------------------------------------------------------------------------

def load_priors(root: Path | None = None) -> dict:
    """Load config/causal_priors.yml relative to root."""
    r = root if root is not None else _repo_root()
    priors_file = r / _PRIORS_PATH
    if not priors_file.exists():
        raise FileNotFoundError(f"causal_priors.yml not found at {priors_file}")
    with priors_file.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_priors(cfg: dict) -> list[str]:
    """Schema-check a parsed causal_priors.yml dict.

    Returns a list of human-readable error strings (empty = clean).
    """
    errors: list[str] = []

    if cfg.get("schema") != "causal_priors.v1":
        errors.append(
            f"causal_priors.yml: schema must be 'causal_priors.v1', "
            f"got {cfg.get('schema')!r}"
        )

    # Required top-level sections
    for section in ("tiers", "min_lag_days_by_cadence", "forbidden_causes", "kill_mask"):
        if section not in cfg:
            errors.append(f"causal_priors.yml: missing required section '{section}'")

    tiers = cfg.get("tiers")
    if not isinstance(tiers, list) or len(tiers) == 0:
        errors.append("causal_priors.yml: tiers must be a non-empty list")
    else:
        for t in tiers:
            if not isinstance(t, dict) or "name" not in t:
                errors.append(
                    f"causal_priors.yml: each tier entry must have 'name', got {t!r}"
                )

    lags = cfg.get("min_lag_days_by_cadence")
    if not isinstance(lags, dict):
        errors.append("causal_priors.yml: min_lag_days_by_cadence must be a dict")
    else:
        for key in ("weekly_publication", "daily_engine"):
            if key not in lags:
                errors.append(
                    f"causal_priors.yml: min_lag_days_by_cadence missing key '{key}'"
                )

    forbidden = cfg.get("forbidden_causes")
    if not isinstance(forbidden, list):
        errors.append("causal_priors.yml: forbidden_causes must be a list")
    else:
        for fc in forbidden:
            if not isinstance(fc, dict) or "pattern" not in fc or "reason" not in fc:
                errors.append(
                    f"causal_priors.yml: each forbidden_causes entry needs "
                    f"'pattern' and 'reason', got {fc!r}"
                )

    kill_mask = cfg.get("kill_mask")
    if not isinstance(kill_mask, dict):
        errors.append("causal_priors.yml: kill_mask must be a dict")
    else:
        if "curated" not in kill_mask:
            errors.append("causal_priors.yml: kill_mask missing 'curated' sub-section")
        if "compiled" not in kill_mask:
            errors.append("causal_priors.yml: kill_mask missing 'compiled' sub-section")

    return errors


# ---------------------------------------------------------------------------
# Kill mask compiler
# ---------------------------------------------------------------------------

def compile_kill_mask(root: Path | None = None) -> list[dict]:
    """Regenerate the compiled kill-mask from data/neuralweb/causal_nulls.jsonl.

    Returns a deterministically-ordered list of dicts.  If the file is absent
    or empty, returns [].  Ordering: sort by (edge_id, scanned_at) for
    reproducibility across runs.
    """
    r = root if root is not None else _repo_root()
    nulls_path = r / _NULLS_PATH
    if not nulls_path.exists():
        return []

    rows: list[dict] = []
    try:
        for line in nulls_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("causal_nulls.jsonl: bad JSON line skipped — %s", exc)
                continue
            rows.append(row)
    except OSError as exc:
        log.warning("compile_kill_mask: could not read nulls file — %s", exc)
        return []

    # Deterministic ordering: (edge_id, scanned_at, verdict) as tiebreakers
    rows.sort(key=lambda r: (
        r.get("edge_id", ""),
        r.get("scanned_at", ""),
        r.get("verdict", ""),
    ))
    return rows


def kill_mask_in_sync(root: Path | None = None) -> bool:
    """Check whether the committed compiled section matches regeneration.

    Returns True if in sync (or if priors file is absent — no sync to check).
    Returns False if the committed compiled section diverges from what
    compile_kill_mask() would produce.
    """
    r = root if root is not None else _repo_root()
    priors_file = r / _PRIORS_PATH
    if not priors_file.exists():
        return True  # Nothing to check

    try:
        cfg = load_priors(r)
    except Exception:  # noqa: BLE001
        return False

    committed: list = (cfg.get("kill_mask") or {}).get("compiled") or []
    regenerated = compile_kill_mask(r)
    return committed == regenerated


# ---------------------------------------------------------------------------
# Forbidden-cause pattern matching
# ---------------------------------------------------------------------------

def _matches_forbidden(feature_id: str, columns: list[str], forbidden_causes: list[dict]) -> str | None:
    """Return the matched pattern string if the feature matches any forbidden_causes entry.

    Checks both feature_id and column names against each pattern (substring match).
    Returns None if no match.
    """
    candidates_to_check = [feature_id] + (columns or [])
    for fc in forbidden_causes:
        pat = fc.get("pattern", "")
        if not pat:
            continue
        for candidate in candidates_to_check:
            if pat.lower() in candidate.lower():
                return pat
    return None


# ---------------------------------------------------------------------------
# Feature source catalogue
# ---------------------------------------------------------------------------
# Each entry defines one logical "feature source" in the inventory.
# Fields that are computed at build time (first_available_date, present) are
# filled in by _build_feature_entry() at runtime.
#
# Keys:
#   feature_id     str   unique identifier
#   family         str   logical grouping
#   path           str   repo-relative file path
#   columns        list  key columns used
#   producer       str   synapse artifact_id or "unregistered"
#   cadence        str   daily-engine | weekly | on-demand | collect
#   time_grain     str   daily | weekly | monthly | snapshot
#   asof_field     str   column name for the date index
#   declared_first str   fallback first_available_date when file is absent
#   pit_basis      str   pit_live | recomputed_history | vintage |
#                        current_snapshot_backfill | display_only
#   era_coverage   list  which eras this covers
#   tier           str   macro_plumbing | asset_class | sector_complex | stock | fire_outcome
#   allowed_roles  list  roles this feature may play
#   forbidden_roles list  roles this feature must never play (informational)
#   collider_risk  str   low | medium | high
#   notes          str   brief note
#
# Era labels: "pre-2000" | "2000-08" | "2009-16" | "2017-20" | "2021+" | "2022-07+"
# ---------------------------------------------------------------------------

FEATURE_SOURCES: list[dict] = [

    # ---- MACRO PLUMBING tier -----------------------------------------------

    {
        "feature_id": "regime_v2_pit__growth_inflation",
        "family": "regime_macro",
        "path": "data/regime/regime_v2_pit.parquet",
        "columns": ["growth_score", "inflation_score", "quad", "recession",
                    "transition_state", "liquidity"],
        "producer": "regime-v2-pit",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "date",
        "declared_first": "1971-01-04",
        "pit_basis": "recomputed_history",
        "era_coverage": ["pre-2000", "2000-08", "2009-16", "2017-20", "2021+", "2022-07+"],
        "tier": "macro_plumbing",
        "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "low",
        "notes": (
            "Recomputed_history: single-vintage rebuild from current code applied to historical dates. "
            "growth_score/inflation_score sparse pre-1980 due to missing macro leg inputs. "
            "recession flag uses NBER dates (PIT by publication with ~6-12m announcement lag)."
        ),
    },

    {
        "feature_id": "regime_latest__liquidity_quality",
        "family": "regime_macro",
        "path": "data/regime/latest.json",
        "columns": ["label", "rrp_buffer_bn", "rrp_exhausted"],
        "producer": "regime-latest",
        "cadence": "daily-engine",
        "time_grain": "snapshot",
        "asof_field": "asof",
        "declared_first": "2022-01-01",
        "pit_basis": "current_snapshot_backfill",
        "era_coverage": ["2022-07+"],
        "tier": "macro_plumbing",
        "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "low",
        "notes": (
            "current_snapshot_backfill: latest.json is a nightly snapshot. "
            "Liquidity quality block (label, rrp_buffer_bn, rrp_exhausted) is "
            "the liquidity-quality sub-object. "
            "For backtesting, the regime_history.parquet analogue is recomputed_history. "
            "Treat as 2022+ feature."
        ),
    },

    {
        "feature_id": "fed_net_liquidity",
        "family": "macro_plumbing",
        "path": "data/macro/fed_net_liquidity.parquet",
        "columns": ["netliq_bn", "netliq_d13w", "netliq_d26w", "netliq_pctile_expanding"],
        "producer": "fed-net-liquidity",
        "cadence": "weekly",
        "time_grain": "weekly",
        "asof_field": "date",
        "declared_first": "2002-12-18",
        "pit_basis": "pit_live",
        "era_coverage": ["2000-08", "2009-16", "2017-20", "2021+", "2022-07+"],
        "tier": "macro_plumbing",
        "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "low",
        "notes": (
            "pit_live: WALCL/RRP/TGA published H.4.1 Wednesdays without revision. "
            "Expanding percentile recomputed at each date from available history. "
            "Null before 2002-12-18. Weekly cadence → min_lag_days=5 (weekly_publication rule)."
        ),
    },

    {
        "feature_id": "liquidity_plumbing",
        "family": "macro_plumbing",
        "path": "data/neuralweb/liquidity_plumbing.json",
        "columns": ["quantity", "quality", "funding"],
        "producer": "liquidity-plumbing",
        "cadence": "daily-engine",
        "time_grain": "snapshot",
        "asof_field": "asof",
        "declared_first": "2022-01-01",
        "pit_basis": "current_snapshot_backfill",
        "era_coverage": ["2022-07+"],
        "tier": "macro_plumbing",
        "allowed_roles": ["conditioner", "environment_split"],
        "forbidden_roles": ["candidate_cause", "target", "forbidden_future"],
        "collider_risk": "medium",
        "notes": (
            "Composite lobe artifact — quantity/quality/funding blocks aggregate "
            "multiple upstream sources (fed_net_liquidity, regime/latest.json, "
            "net_issuance, tga). As a composite it carries medium collider risk "
            "(conditioning on it may open back-doors through parent sources). "
            "Use for environment conditioning only; do not treat as a primitive cause."
        ),
    },

    # ---- ASSET CLASS tier --------------------------------------------------

    {
        "feature_id": "breadth__market_breadth",
        "family": "breadth",
        "path": "data/breadth/breadth.parquet",
        "columns": ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"],
        "producer": "breadth-breadth",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "Date",
        "declared_first": "1962-03-13",
        "pit_basis": "recomputed_history",
        "era_coverage": ["pre-2000", "2000-08", "2009-16", "2017-20", "2021+", "2022-07+"],
        "tier": "asset_class",
        "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "low",
        "notes": (
            "SURVIVORSHIP CAVEAT: pre-2002 breadth uses current sp1500 membership "
            "backfilled to historical prices — NOT PIT-membership-aware. "
            "Post-2002 uses sp1500_pit_membership.parquet (cleaner). "
            "Whole series classified recomputed_history to avoid misleading callers "
            "about pre-2002 data quality."
        ),
    },

    {
        "feature_id": "gex_history__spy",
        "family": "gex",
        "path": "data/index_gex_history/SPY.parquet",
        "columns": ["net_gex_bn", "gamma_regime", "dist_to_flip_pct"],
        "producer": "gex-state-history",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "date",
        "declared_first": "2017-01-01",
        "pit_basis": "pit_live",
        "era_coverage": ["2017-20", "2021+", "2022-07+"],
        "tier": "asset_class",
        "allowed_roles": ["candidate_cause", "conditioner"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "medium",
        "notes": (
            "ERA FLAG: 2017+ only. GEX data is not reliable pre-2017 (ThetaData "
            "coverage and methodology constraints). Any edge using this feature must "
            "be auto-stamped era_specific and may not claim pre-2017 inference. "
            "dist_to_flip_pct captures proximity to the gamma flip level — "
            "medium collider risk because it is a function of price, spot GEX, and "
            "dealer positioning simultaneously."
        ),
    },

    # ---- SECTOR COMPLEX tier -----------------------------------------------

    {
        "feature_id": "cycle_pattern__state_monthly",
        "family": "cycle",
        "path": "data/cycle_pattern/state_monthly.parquet",
        "columns": ["phase", "pos", "osc_slope"],
        "producer": "cycle-pattern-state-monthly",
        "cadence": "on-demand",
        "time_grain": "monthly",
        "asof_field": "date",
        "declared_first": "2010-12-31",
        "pit_basis": "recomputed_history",
        "era_coverage": ["2009-16", "2017-20", "2021+", "2022-07+"],
        "tier": "sector_complex",
        "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "medium",
        "notes": (
            "Cycle patterns are fit retrospectively from current code applied to "
            "historical price data. A pattern detected in 2012 may have been "
            "identified using future-available data if the fitting window extended "
            "beyond 2012. Medium collider risk: phase is partially determined by "
            "the return history it may be used to predict."
        ),
    },

    # ---- STOCK tier --------------------------------------------------------

    {
        "feature_id": "options_entry__state",
        "family": "options_entry",
        "path": "data/options_entry/state.parquet",
        "columns": ["iv30", "ivspread_rel", "skew", "net_doi", "gamma_regime",
                    "dist_to_flip_pct", "gex_confirm_verdict", "evidence_quality"],
        "producer": "options-entry-state",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "as_of",
        "declared_first": "2022-07-01",
        "pit_basis": "pit_live",
        "era_coverage": ["2022-07+"],
        "tier": "stock",
        "allowed_roles": ["candidate_cause", "conditioner"],
        "forbidden_roles": ["target", "forbidden_future"],
        "collider_risk": "medium",
        "notes": (
            "RECENT_ONLY: effective window is 2022-07-01+ (Oracle RECENT_ONLY pattern). "
            "Any edge using this feature is auto-stamped era_specific by construction "
            "and the era-split leg returns insufficient_era_span. "
            "Medium collider risk: options-entry features co-vary strongly with "
            "contemporaneous price momentum and may reflect the same underlying "
            "dealer-positioning parent."
        ),
    },

    # ---- FIRE OUTCOME tier (targets only) ----------------------------------

    {
        "feature_id": "replay__entry_quality_outcomes",
        "family": "entry_quality",
        "path": "data/replay/replay_boarded.parquet",
        "columns": ["good_21d", "fwd_mdd_21", "fwd_ret_21", "fwd_ret_63"],
        "producer": "unregistered",
        "cadence": "daily-engine",
        "time_grain": "daily",
        "asof_field": "date",
        "declared_first": "2022-06-30",
        "pit_basis": "recomputed_history",
        "era_coverage": ["2022-07+"],
        "tier": "fire_outcome",
        "allowed_roles": ["target"],
        "forbidden_roles": [
            "candidate_cause", "conditioner", "environment_split",
            "confounder", "mediator", "collider", "proxy",
            "lagged_outcome_echo", "negative_control",
        ],
        "collider_risk": "high",
        "notes": (
            "GITIGNORED / RUNNER-LOCAL: replay_boarded.parquet is not git-tracked. "
            "The causal job resolves it via REPLAY_BOARDED_PATH env override "
            "(THETADATA_STORE pattern). Absent → data_absent null printed (CHF-R6). "
            "EFFECTIVE window ≈ 2022-06-30+ (P0 memo §6 v1.1 — nominal 2021-07-06 "
            "window does not exist in the ledger). "
            "ERA: all edges targeting this feature are auto-stamped era_specific "
            "and return insufficient_era_span on the era-split leg. "
            "forward-outcome columns: fwd_mdd_21, fwd_ret_21, fwd_ret_63 are "
            "forward-realized outcomes and match the forbidden_causes fwd_ pattern."
        ),
    },
]


# ---------------------------------------------------------------------------
# Build a single feature entry (probing the actual file when present)
# ---------------------------------------------------------------------------

def _build_feature_entry(
    src: dict,
    root: Path,
    priors: dict,
    min_lag_by_cadence: dict,
) -> dict:
    """Build a complete inventory entry from a FEATURE_SOURCES spec.

    Probes the actual file for first_available_date when possible.
    Emits present=False with a note when the file is absent (honest).
    """
    path_str: str = src["path"]
    abs_path = root / path_str

    # Presence check
    present = abs_path.exists()

    # First available date: probe from file when present and it's a parquet
    first_available = src["declared_first"]
    first_available_probed = False
    if present and path_str.endswith(".parquet"):
        try:
            import pyarrow.parquet as pq
            asof_col = src.get("asof_field", "date")
            meta = pq.read_metadata(str(abs_path))
            # Try to get min date from row group statistics (fast, no full read)
            min_val = None
            for rg_idx in range(meta.num_row_groups):
                rg = meta.row_group(rg_idx)
                for col_idx in range(rg.num_columns):
                    col = rg.column(col_idx)
                    if col.path_in_schema == asof_col:
                        stats = col.statistics
                        if stats and stats.has_min_max:
                            candidate = stats.min
                            if candidate is not None:
                                if min_val is None or candidate < min_val:
                                    min_val = candidate
            if min_val is not None:
                if hasattr(min_val, "as_py"):
                    min_val = min_val.as_py()
                if hasattr(min_val, "date"):
                    first_available = str(min_val.date())
                else:
                    first_available = str(min_val)
                first_available_probed = True
        except Exception as exc:  # noqa: BLE001
            log.debug("first_available probe failed for %s: %s", path_str, exc)

    # Forbidden-cause check: can this feature carry candidate_cause?
    forbidden_causes: list[dict] = priors.get("forbidden_causes") or []
    matched_pattern = _matches_forbidden(
        src["feature_id"], src.get("columns", []), forbidden_causes
    )
    allowed_roles = list(src.get("allowed_roles", []))
    forbidden_roles = list(src.get("forbidden_roles", []))

    if matched_pattern and "candidate_cause" in allowed_roles:
        # Strip candidate_cause and add a note
        allowed_roles = [r for r in allowed_roles if r != "candidate_cause"]
        log.warning(
            "feature %s matched forbidden_causes pattern '%s' — "
            "candidate_cause removed from allowed_roles",
            src["feature_id"],
            matched_pattern,
        )

    # forbidden_future rule: if feature has forbidden_future, ONLY target allowed
    if "forbidden_future" in allowed_roles:
        allowed_roles = ["target"]
        forbidden_roles = sorted(r for r in VALID_ROLES if r != "target")

    # time_grain → min_lag_days  (time_grain takes priority; cadence is fallback)
    cadence = src.get("cadence", "daily-engine")
    time_grain = src.get("time_grain", "daily")
    if time_grain == "monthly":
        min_lag = min_lag_by_cadence.get("monthly_grain", 21)
    elif cadence == "weekly" or time_grain == "weekly":
        min_lag = min_lag_by_cadence.get("weekly_publication", 5)
    else:
        min_lag = min_lag_by_cadence.get("daily_engine", 1)

    # Note for absent runner-local files
    notes = src.get("notes", "")
    if not present:
        notes = (
            f"FILE ABSENT on this checkout (present=false). "
            f"This may be a runner-local store (e.g. replay_boarded.parquet) "
            f"or a path not yet produced. Scout emits data_absent null when "
            f"this path is unresolvable. | {notes}"
        ).strip(" |")

    return {
        "feature_id": src["feature_id"],
        "family": src["family"],
        "path": path_str,
        "producer": src.get("producer", "unregistered"),
        "cadence": cadence,
        "time_grain": src.get("time_grain", "daily"),
        "asof_field": src.get("asof_field", "date"),
        "first_available_date": first_available,
        "first_available_date_probed": first_available_probed,
        "pit_basis": src.get("pit_basis", "recomputed_history"),
        "era_coverage": src.get("era_coverage", []),
        "tier": src.get("tier", "stock"),
        "allowed_roles": allowed_roles,
        "forbidden_roles": forbidden_roles,
        "min_lag_days": min_lag,
        "collider_risk": src.get("collider_risk", "low"),
        "present": present,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Role validation
# ---------------------------------------------------------------------------

def _validate_feature_roles(entry: dict, forbidden_causes: list[dict]) -> list[str]:
    """Return validation errors for a single inventory entry."""
    errors: list[str] = []
    fid = entry["feature_id"]
    allowed = entry.get("allowed_roles", [])

    # Rule 1: forbidden-cause pattern → no candidate_cause
    matched = _matches_forbidden(fid, entry.get("columns", []), forbidden_causes)
    if matched and "candidate_cause" in allowed:
        errors.append(
            f"{fid}: matches forbidden_causes pattern '{matched}' but "
            f"candidate_cause is in allowed_roles — illegal"
        )

    # Rule 2: forbidden_future → only target
    if "forbidden_future" in allowed:
        non_target = [r for r in allowed if r != "target"]
        if non_target:
            errors.append(
                f"{fid}: has forbidden_future in allowed_roles — only 'target' "
                f"is permitted, but found {non_target!r}"
            )

    # Rule 3: all roles must be in vocabulary
    unknown = [r for r in allowed if r not in VALID_ROLES]
    if unknown:
        errors.append(
            f"{fid}: unknown roles in allowed_roles: {unknown!r}"
        )

    return errors


# ---------------------------------------------------------------------------
# Build the full inventory artifact
# ---------------------------------------------------------------------------

def build_inventory(root: Path | None = None) -> dict:
    """Build and return the causal feature inventory artifact dict.

    Parameters
    ----------
    root : Path | None
        Repo root.  Defaults to the repo root inferred from this file's location.

    Returns
    -------
    dict
        Full artifact dict matching schema neuralweb.causal_feature_inventory.v1.
        gap_notes contains honest gaps (absent files, validation warnings).
        Never raises on partial gaps — those become gap_notes.
    """
    r = root if root is not None else _repo_root()
    gap_notes: list[str] = []

    # Load priors
    try:
        priors = load_priors(r)
    except FileNotFoundError as exc:
        gap_notes.append(f"causal_priors.yml absent: {exc}")
        priors = {"schema": "causal_priors.v1", "tiers": [], "min_lag_days_by_cadence": {},
                  "forbidden_causes": [], "kill_mask": {"curated": [], "compiled": []}}

    # Validate priors schema
    priors_errors = validate_priors(priors)
    for err in priors_errors:
        gap_notes.append(f"priors schema error: {err}")

    min_lag_by_cadence: dict = priors.get("min_lag_days_by_cadence") or {}
    forbidden_causes: list[dict] = priors.get("forbidden_causes") or []

    # Build feature entries
    features: list[dict] = []
    for src in FEATURE_SOURCES:
        try:
            entry = _build_feature_entry(src, r, priors, min_lag_by_cadence)
        except Exception as exc:  # noqa: BLE001
            gap_notes.append(
                f"feature {src.get('feature_id', '?')}: build error — {exc}"
            )
            continue

        # Role validation
        role_errors = _validate_feature_roles(entry, forbidden_causes)
        for err in role_errors:
            gap_notes.append(f"role validation: {err}")

        # Absent-file note
        if not entry["present"]:
            gap_notes.append(
                f"feature {entry['feature_id']}: file absent at {entry['path']}"
            )

        features.append(entry)

    # Kill mask sync check
    try:
        in_sync = kill_mask_in_sync(r)
        if not in_sync:
            gap_notes.append(
                "kill_mask compiled section out of sync with causal_nulls.jsonl — "
                "run build_causal_inventory.py and commit the updated priors"
            )
    except Exception as exc:  # noqa: BLE001
        gap_notes.append(f"kill_mask sync check failed: {exc}")

    asof = datetime.now(tz=timezone.utc).isoformat()

    return {
        "schema": SCHEMA,
        "artifact_id": ARTIFACT_ID,
        "asof": asof,
        "authority": dict(_AUTHORITY),
        "features": features,
        "feature_count": len(features),
        "gap_notes": gap_notes,
        "produced_by": "engine.neuralweb.causal_inventory.build_inventory",
    }
