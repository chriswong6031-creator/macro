"""engine.research_factory.adapter_oracle — Oracle domain adapter (W3, RF-2/RF-13).

ROUTES and RECORDS — never re-implements an evaluator.

RF-2 (Projection law)
---------------------
Domain status is RE-READ at call time from the live compounds registry and
projected to a factory state via a fixed mapping.  The projection is NEVER
persisted as a factory status field for domain-homed candidates.

Mapping (oracle domain status → factory state):
  screened             → screened
  accruing             → paper
  promoted             → promote_eligible
  refuted              → numeric_rejected
  blocked_missing_column → awaiting_data
  exploratory          → registered   (default; compound exists but not screened)

RF-13 (Domain seams — Oracle)
------------------------------
Two-track routing determined by the ``reversion`` block in the registry row:
  - reversion track : compound.get("reversion", {}).get("gauntlet") == "PASS"
                      → oracle_reversion_screen (READ-ONLY; never counted)
  - 63d track       : all others
                      → oracle_screen (COUNTED trial; gated behind count=True)

Re-screen refusal per RF-13: if the compound already has status 'screened' (or
beyond), the 63d adapter REFUSES to invoke oracle_screen unless count=True is
explicitly passed.  Even with count=True, a compound already at status
'screened' is refused (keep-first + params_hash law).

RF-10 (Kill evidence)
----------------------
numeric_rejected transitions carry kill_evidence.  n_at_kill is sourced from
the reversion screen artifact (``all.n`` from screen_compound result).
kill_class mapping from reversion UNDERPOWERED-ACCRUING verdict class:
  UNDERPOWERED-ACCRUING → underpowered_accruing
  REFUTED               → falsified
  (default)             → falsified

RF-13 (promotion_queue.json)
-----------------------------
data/oracle/promotion_queue.json is read as screened-evidence.
search_width_at_scan is captured into every candidate artifact dict returned
(REQUIRED in every oracle review packet later, per charter §6 W3).

Pure stdlib + lazy heavy imports.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain-status → factory-state projection mapping (RF-2, canonical)
# ---------------------------------------------------------------------------

#: Fixed mapping: oracle compound status → research_factory state.
#: On conflict, the domain registry wins (RF-2).
ORACLE_STATUS_TO_FACTORY_STATE: dict[str, str] = {
    "screened":              "screened",
    "accruing":              "paper",
    "promoted":              "promote_eligible",
    "refuted":               "numeric_rejected",
    "blocked_missing_column": "awaiting_data",
    "exploratory":           "registered",   # default: compound exists but not screened
}

# Fallback for any unknown domain status
_FALLBACK_FACTORY_STATE = "registered"


def project_oracle_status(domain_status: str) -> str:
    """Project an oracle compound status to a factory state (RF-2).

    Returns the projected factory state string.  Unknown domain statuses
    fall back to 'registered'.
    """
    return ORACLE_STATUS_TO_FACTORY_STATE.get(domain_status, _FALLBACK_FACTORY_STATE)


# ---------------------------------------------------------------------------
# Kill-class mapping from reversion screen verdict classes (RF-10)
# ---------------------------------------------------------------------------

def _kill_class_from_verdict(verdict_label: str | None) -> str:
    """Map a reversion screen verdict label to an RF-10 kill_class.

    Reversion screen verdict classes seen in oracle_reversion_screen.py:
      UNDERPOWERED-ACCRUING → underpowered_accruing
      REFUTED / FAIL        → falsified
      (default)             → falsified
    """
    if verdict_label is None:
        return "falsified"
    v = verdict_label.upper().replace("-", "_").replace(" ", "_")
    if "UNDERPOWERED" in v or "ACCRUING" in v:
        return "underpowered_accruing"
    return "falsified"


# ---------------------------------------------------------------------------
# Track discriminator (RF-13)
# ---------------------------------------------------------------------------

def is_reversion_track(compound: dict) -> bool:
    """Return True if this compound belongs to the reversion track.

    Discriminator: compound['reversion']['gauntlet'] == 'PASS'.
    All other compounds (missing 'reversion' block, or gauntlet != 'PASS')
    are routed to the 63d track.
    """
    reversion_block = compound.get("reversion")
    if not reversion_block or not isinstance(reversion_block, dict):
        return False
    return reversion_block.get("gauntlet") == "PASS"


# ---------------------------------------------------------------------------
# Promotion queue reader (RF-13)
# ---------------------------------------------------------------------------

def load_promotion_queue(data_dir: Path | None = None) -> dict:
    """Load data/oracle/promotion_queue.json absent-safely.

    Returns the parsed dict, or an empty structure on any read error.
    Captures search_width_at_scan from the queue root.
    """
    _dir = Path(data_dir) if data_dir else Path("data")
    path = _dir / "oracle" / "promotion_queue.json"
    if not path.exists():
        log.debug("promotion_queue.json not found at %s — returning empty", path)
        return {"candidates": [], "search_width": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("load_promotion_queue: failed to parse %s: %s", path, exc)
        return {"candidates": [], "search_width": None}


def _extract_pq_entry(compound_id: str,
                      pq_candidates: list[dict]) -> dict | None:
    """Return the promotion-queue entry for compound_id, or None."""
    for entry in pq_candidates:
        if entry.get("compound_id") == compound_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Registry loader wrapper (absent-file-safe)
# ---------------------------------------------------------------------------

def load_oracle_registry(data_dir: Path | None = None) -> list[dict]:
    """Load data/oracle/compounds/registry.jsonl absent-safely.

    Returns list of compound dicts.  Falls back to engine.oracle.compounds
    load_registry when the direct path exists; otherwise returns [].
    """
    _dir = Path(data_dir) if data_dir else Path("data")
    compounds_dir = _dir / "oracle" / "compounds"
    reg_path = compounds_dir / "registry.jsonl"
    if not reg_path.exists():
        log.debug("oracle registry not found at %s — returning []", reg_path)
        return []
    try:
        from engine.oracle.compounds import load_registry
        return load_registry(compounds_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("load_oracle_registry: import/load failed: %s", exc)
        # Fallback: pure stdlib read
        rows: list[dict] = []
        try:
            for line in reg_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        except OSError:
            pass
        return rows


# ---------------------------------------------------------------------------
# Reversion track: read-only projection + artifact capture
# ---------------------------------------------------------------------------

def _reversion_artifact(compound: dict, pq_entry: dict | None,
                        search_width: int | None) -> dict:
    """Build an artifact dict for a reversion-track compound.

    This is READ-ONLY — never invokes screen_compound.
    The reversion block embedded in the registry row IS the screen artifact.
    """
    rev = compound.get("reversion") or {}
    artifact: dict[str, Any] = {
        "track": "reversion",
        "source": "registry_reversion_block",
        "compound_id": compound.get("id"),
        "n": rev.get("n"),
        "wr": rev.get("wr"),
        "asym": rev.get("asym"),
        "ret_exit": rev.get("ret_exit"),
        "gauntlet": rev.get("gauntlet"),
        "asof": rev.get("asof"),
        # search_width_at_scan REQUIRED per charter §6 W3
        "search_width_at_scan": (
            pq_entry.get("search_width_at_scan") if pq_entry
            else search_width
        ),
        "pq_entry": pq_entry,
    }
    return artifact


# ---------------------------------------------------------------------------
# 63d track: counted screen gate (RF-13, RF-6)
# ---------------------------------------------------------------------------

def _run_63d_screen(
    compound: dict,
    data_dir: Path,
    count: bool,
) -> dict | None:
    """Invoke oracle_screen for a 63d-track compound.

    Gated: raises PermissionError unless count=True.
    Returns the screen result dict or None on error.

    NEVER called for reversion-track compounds.
    """
    if not count:
        raise PermissionError(
            f"63d oracle screen for compound {compound.get('id')!r} is a "
            f"COUNTED trial — invoke with count=True to explicitly allow it "
            f"(RF-13; default factory mode is read-only)"
        )
    try:
        from scripts.oracle_screen import screen_compound as _screen_63d
    except ImportError as exc:
        log.error("_run_63d_screen: cannot import oracle_screen: %s", exc)
        return None
    try:
        result = _screen_63d(compound, data_dir)
        return result
    except Exception as exc:  # noqa: BLE001
        log.error("_run_63d_screen: %s failed: %s", compound.get("id"), exc)
        return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def route_compound(
    compound: dict,
    *,
    data_dir: Path | None = None,
    count: bool = False,
) -> dict:
    """Route a single oracle compound through the factory adapter.

    Parameters
    ----------
    compound  : A single compound dict from the oracle registry.
    data_dir  : Optional root data directory (default: Path("data")).
    count     : If True, allows a counted 63d oracle_screen invocation.
                Default False per RF-13 (factory default is read-only observer).

    Returns
    -------
    dict with keys:
      compound_id    : str — the oracle compound id
      spec_ref       : str — same as compound_id (oracle is the authority)
      domain_status  : str — raw domain status from registry
      projected_state: str — factory state projected via RF-2 mapping
      track          : str — 'reversion' or '63d'
      artifact       : dict — screen/registry evidence (includes search_width_at_scan)
      kill_evidence  : dict | None — populated when projected_state == 'numeric_rejected'
      re_screen_refused: bool — True if 63d re-screen was refused per RF-13
    """
    _dir = Path(data_dir) if data_dir else Path("data")
    compound_id = compound.get("id", "?")
    domain_status = compound.get("status", "exploratory")
    projected_state = project_oracle_status(domain_status)
    track = "reversion" if is_reversion_track(compound) else "63d"

    # Load promotion queue for search_width_at_scan evidence
    pq = load_promotion_queue(_dir)
    pq_candidates = pq.get("candidates") or []
    search_width = pq.get("search_width")
    pq_entry = _extract_pq_entry(compound_id, pq_candidates)

    artifact: dict = {}
    kill_evidence: dict | None = None
    re_screen_refused: bool = False

    if track == "reversion":
        # Reversion track: read-only — use registry reversion block as artifact
        artifact = _reversion_artifact(compound, pq_entry, search_width)

        # Build kill_evidence when numeric_rejected (RF-10)
        if projected_state == "numeric_rejected":
            rev = compound.get("reversion") or {}
            n_at_kill = rev.get("n") or 0
            # Determine kill_class from reversion verdict (best proxy from block)
            gauntlet_result = rev.get("gauntlet", "")
            verdict_label = "REFUTED" if gauntlet_result != "PASS" else None
            kill_evidence = {
                "n_at_kill": n_at_kill,
                "kill_class": _kill_class_from_verdict(verdict_label),
                "mde_at_n": None,   # computable by challenger (W4), not here
                "regime_split": {
                    "risk_on": rev.get("risk_on"),
                    "risk_off": rev.get("risk_off"),
                },
                "source": "registry_reversion_block",
            }

    else:
        # 63d track
        # Re-screen refusal: if already screened or beyond, refuse unless explicit
        _SCREENED_OR_BEYOND = frozenset({
            "screened", "accruing", "promoted", "refuted"
        })
        if domain_status in _SCREENED_OR_BEYOND:
            re_screen_refused = True
            log.info(
                "route_compound: refusing 63d re-screen for %s "
                "(domain_status=%r — already screened per RF-13)",
                compound_id, domain_status,
            )
            # Still produce artifact from promotion-queue evidence (read-only)
            artifact = {
                "track": "63d",
                "source": "read_only_pq_evidence",
                "compound_id": compound_id,
                "pq_entry": pq_entry,
                "search_width_at_scan": (
                    pq_entry.get("search_width_at_scan") if pq_entry
                    else search_width
                ),
                "note": "re-screen refused per RF-13 (compound already screened)",
            }
        else:
            # Compound is exploratory — invoke counted screen if allowed
            if count:
                screen_result = _run_63d_screen(compound, _dir, count=True)
                artifact = {
                    "track": "63d",
                    "source": "oracle_screen",
                    "compound_id": compound_id,
                    "screen_result": screen_result,
                    "pq_entry": pq_entry,
                    "search_width_at_scan": (
                        pq_entry.get("search_width_at_scan") if pq_entry
                        else search_width
                    ),
                }
            else:
                # Default read-only: project from registry without counting
                artifact = {
                    "track": "63d",
                    "source": "read_only_registry",
                    "compound_id": compound_id,
                    "pq_entry": pq_entry,
                    "search_width_at_scan": (
                        pq_entry.get("search_width_at_scan") if pq_entry
                        else search_width
                    ),
                    "note": "read-only mode (count=False); no 63d screen invoked",
                }

        # Kill evidence for numeric_rejected on 63d track (RF-10)
        if projected_state == "numeric_rejected":
            kill_evidence = {
                "n_at_kill": 0,     # not computable read-only; challenger fills this
                "kill_class": "falsified",
                "mde_at_n": None,
                "regime_split": None,
                "source": "domain_registry_refuted",
            }

    return {
        "compound_id": compound_id,
        "spec_ref": compound_id,   # oracle is the authority; spec_ref = compound_id
        "domain_status": domain_status,
        "projected_state": projected_state,
        "track": track,
        "artifact": artifact,
        "kill_evidence": kill_evidence,
        "re_screen_refused": re_screen_refused,
    }


def route_all(
    compounds: list[dict],
    *,
    data_dir: Path | None = None,
    count: bool = False,
) -> list[dict]:
    """Route all compounds in ``compounds`` through the oracle adapter.

    Parameters match ``route_compound``.  Returns a list of result dicts.
    """
    results: list[dict] = []
    for compound in compounds:
        try:
            result = route_compound(compound, data_dir=data_dir, count=count)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            log.error(
                "route_all: route_compound failed for %s: %s",
                compound.get("id", "?"), exc,
            )
    return results
