"""engine.metabolism.scout — Uncovered-Domain Scout (V2-C Unit 6, R-V2-3/R-V2-7/R-V2-9).

WHAT IT DOES
------------
Scans the curated NW-scope domain universe (config/nw_information_domains.yml)
against the ACTIVE lobe roster (lobe_charters.yml), the organism_state trajectory
rollup, and the insight bus, and emits a DISPLAY-TIER charter PROPOSAL for any
domain that has been uncovered for >= min_uncovered_cycles distinct scout cycles.
"Auto-charter from a *recurring coverage gap*, not a whim" (masterplan §4 V2-C).

It ALSO reports (context only, never proposed) domains that are technically
covered but only by lobes in a weak trajectory — "thinly covered" — by reading
per-lobe trajectory labels from data/metabolism/organism_state.json.

WHY IT IS SAFE (the load-bearing properties)
--------------------------------------------
  * DETERMINISTIC, NO LLM.  The scout only detects gaps and counts persistence;
    it never originates a signal, score, or escalation (R-V2-9 / R-AUT-1).  Any
    LLM enrichment of a fired proposal happens downstream in the normal
    PROPOSE→ADJUDICATE gauntlet, never here.
  * INERT.  A charter proposal is a display-tier artifact for the gauntlet.  It
    is `proposed_tier: display` and `proposed_lifecycle_state: proposed` — the
    module CANNOT propose a confirmer/scored tier.  Promotion to authority stays
    T2 + gauntlet + operator (R-V2-3).  Nothing changes until the operator taps.
  * PERSISTENCE-GATED.  A single-cycle gap never fires.  The gap must recur
    across >= K distinct cycles (honest-null "accruing" below K, mirroring
    anomaly_monitor's n>=n_min contract).
  * NEVER-RAISE.  Every public function returns safe defaults on any error.
  * ROSTER-AWARE, NEVER BLOCKS.  A proposal that would exceed the roster cap is
    still emitted with an advisory budget snapshot; the cap surfaces as a digest
    ASK at onboarding (roster_governor), never as a silent block here (R-V2-7).

COVERAGE MODEL
--------------
Because the `information_domain` tag in lobe_charters.yml is coarse (in
production almost every lobe is tagged "context"), coverage is determined by
SIGNATURE MATCH: a domain is COVERED iff at least one ACTIVE charter's identity
string (lobe_id + information_domain + owner_program + notes, lowercased)
contains any of the domain's `coverage_match` substrings.

Artifacts (all under data/metabolism/, git-tracked, append-only where noted):
  * scout/observations.jsonl        — one row per scan (append-only)
  * charter_proposals/<domain>.json — one standing proposal per fired domain

Schemas:
  metabolism.scout_observation.v1
  metabolism.charter_proposal.v1
  metabolism.scout_scan.v1
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_OBSERVATION = "metabolism.scout_observation.v1"
SCHEMA_CHARTER_PROPOSAL = "metabolism.charter_proposal.v1"
SCHEMA_SCAN = "metabolism.scout_scan.v1"

_DOMAINS_CFG = ("config", "nw_information_domains.yml")
_BUDGET_CFG = ("config", "metabolism_budget.yml")
SCOUT_DIR = ("data", "metabolism", "scout")
CHARTER_PROPOSAL_DIR = ("data", "metabolism", "charter_proposals")
OBSERVATIONS_FILE = "observations.jsonl"

DEFAULT_MIN_UNCOVERED_CYCLES = 3

# The scout can ONLY ever propose a display-tier lobe in the `proposed` state.
# These are hard constants, not parameters — a tier-raising proposal is
# structurally impossible from this module (R-V2-3).
_PROPOSED_TIER = "display"
_PROPOSED_LIFECYCLE_STATE = "proposed"

_AUTHORITY_BLOCK = {
    "is_context_only": True,
    "display_only": True,
    "not_a_signal": True,
    "note": (
        "Charter PROPOSAL for the normal gauntlet. Display-tier only; promotion "
        "to confirmer/scored/authority is T2+gauntlet+operator (R-V2-3). "
        "Auto-charter from a recurring coverage gap (>=K distinct cycles), never "
        "a whim. Nothing changes until the operator taps."
    ),
}


# ── Root + IO helpers (mirror the sibling modules) ────────────────────────────

def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_yaml(path: Path) -> dict | None:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("scout: failed to load %s: %s", path, exc)
        return None


def _load_domains(root: Path) -> dict[str, Any]:
    """Load the curated domain universe.  Returns {default_min, domains:[...]}.

    NEVER raises; missing/unreadable config → empty universe (scout stays silent).
    """
    out: dict[str, Any] = {"default_min": DEFAULT_MIN_UNCOVERED_CYCLES, "domains": []}
    raw = _load_yaml(root.joinpath(*_DOMAINS_CFG))
    if not isinstance(raw, dict):
        return out
    if raw.get("schema") != "nw_information_domains.v1":
        # Warn on an unexpected schema; still fail-open on the domains list.
        log.warning("scout: unexpected nw_information_domains schema: %r", raw.get("schema"))
    defaults = raw.get("defaults") or {}
    try:
        out["default_min"] = int(defaults.get("min_uncovered_cycles", DEFAULT_MIN_UNCOVERED_CYCLES))
    except Exception:  # noqa: BLE001
        out["default_min"] = DEFAULT_MIN_UNCOVERED_CYCLES
    domains = raw.get("domains")
    if isinstance(domains, list):
        out["domains"] = [d for d in domains if isinstance(d, dict) and d.get("domain_id")]
    return out


def _as_list(v: Any) -> list[str]:
    """Coerce a match spec to a list of strings.

    A bare string (a config typo) would otherwise iterate character-by-character
    and match on single letters — coerce it to a single-element list instead.
    """
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v.strip():
        return [v]
    return []


def _domain_min_cycles(domain: dict, default_min: int) -> int:
    try:
        v = domain.get("min_uncovered_cycles")
        return int(v) if v is not None else int(default_min)
    except Exception:  # noqa: BLE001
        return int(default_min)


# ── Coverage determination ────────────────────────────────────────────────────

def _active_identities(root: Path) -> dict[str, str]:
    """Return {lobe_id: lowercased identity string} for every ACTIVE charter.

    Identity = lobe_id + information_domain + owner_program.  Used for substring
    signature matching (the coarse `information_domain` tag is not a reliable
    coverage key on its own).  Free-text `notes` is DELIBERATELY excluded: an
    incidental mention there ("tracks the health of the china book") must not
    falsely mark a domain covered — for a gap-finder, a false-positive coverage
    silences a real proposal, which is the dangerous direction.  NEVER raises.
    """
    out: dict[str, str] = {}
    try:
        from engine.metabolism.lobe_registry import load as load_charters  # noqa: PLC0415
        charters = load_charters(root).get("charters", {})
        for lobe_id, ch in charters.items():
            if not isinstance(ch, dict):
                continue
            if ch.get("lifecycle_state") != "active":
                continue
            parts = [
                str(lobe_id),
                str(ch.get("information_domain", "")),
                str(ch.get("owner_program", "")),
            ]
            out[str(lobe_id)] = " ".join(parts).lower()
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._active_identities: %s", exc)
    return out


def _covering_lobes(domain: dict, identities: dict[str, str]) -> list[str]:
    """Return the lobe_ids whose identity matches any coverage_match substring.

    Empty list when the domain has no coverage_match (unspecified) OR no active
    lobe matches.  Use with `_has_coverage_spec` to distinguish the two.
    """
    matches = [m.lower() for m in _as_list(domain.get("coverage_match")) if m.strip()]
    if not matches:
        return []
    hits: list[str] = []
    for lobe_id, ident in identities.items():
        if any(sub in ident for sub in matches):
            hits.append(lobe_id)
    return hits


def _has_coverage_spec(domain: dict) -> bool:
    return bool([m for m in _as_list(domain.get("coverage_match")) if m.strip()])


# ── Trajectory (organism_state.json — for thin-coverage detection) ────────────

# A domain whose covering lobes are ALL in a WEAK trajectory (and at least one is
# actively degrading) is "thinly covered": technically covered, but by dying
# organs.  A single compounding/accruing covering lobe means healthy coverage.
_WEAK_LABELS = frozenset({"degrading", "stagnating"})


def _trajectory_labels(root: Path) -> dict[str, str]:
    """Return {lobe_id: trajectory_label} from data/metabolism/organism_state.json.

    Reads the already-built artifact (the scout is a downstream consumer, not a
    recomputer).  Fail-open: a missing/unreadable/garbage file → {} (no domain is
    ever flagged thin, which is the safe direction).  NEVER raises.
    """
    out: dict[str, str] = {}
    try:
        p = root / "data" / "metabolism" / "organism_state.json"
        if not p.exists():
            return out
        raw = json.loads(p.read_text(encoding="utf-8"))
        lobes = (raw or {}).get("lobes")
        if not isinstance(lobes, dict):
            return out
        for lobe_id, lobe in lobes.items():
            if not isinstance(lobe, dict):
                continue
            traj = lobe.get("trajectory")
            label = traj.get("label") if isinstance(traj, dict) else None
            if label:
                out[str(lobe_id)] = str(label)
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._trajectory_labels: %s", exc)
    return out


# ── Demand evidence (optional, from the insight bus) ──────────────────────────

def _count_evidence(domain: dict, root: Path) -> tuple[int, list[str]]:
    """Count OPEN insight-bus rows whose summary/entities match evidence_match.

    Returns (count, sample_insight_ids[:5]).  Advisory only — never a gate.
    NEVER raises.
    """
    matches = [m.lower() for m in _as_list(domain.get("evidence_match")) if m.strip()]
    if not matches:
        return 0, []
    hits: list[str] = []
    try:
        from engine.metabolism.insight_bus import get_open_rows  # noqa: PLC0415
        for row in get_open_rows(root=root):
            if not isinstance(row, dict):
                continue
            # Don't count the scout's OWN emitted rows as external demand — that
            # would be self-reinforcing.
            if row.get("emitter") == "metabolism_scout":
                continue
            hay = (
                str(row.get("summary", "")) + " " + " ".join(str(e) for e in row.get("entities", []))
            ).lower()
            if any(sub in hay for sub in matches):
                iid = row.get("insight_id")
                if iid:
                    hits.append(str(iid))
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._count_evidence(%s): %s", domain.get("domain_id"), exc)
    return len(hits), hits[:5]


# ── Observation ledger (persistence gate) ─────────────────────────────────────

def _observations_path(root: Path) -> Path:
    return root.joinpath(*SCOUT_DIR) / OBSERVATIONS_FILE


def _read_observations(root: Path) -> list[dict]:
    """Read all prior scout observation rows.  Returns [] on any error."""
    try:
        p = _observations_path(root)
        if not p.exists():
            return []
        rows: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            # Keep only well-formed object rows — a valid-JSON-but-non-object line
            # (a bare list/number/null) must not later crash `.get` and silently
            # suppress ALL scout emission for the cycle.
            if isinstance(obj, dict):
                rows.append(obj)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._read_observations: %s", exc)
        return []


def _prior_distinct_uncovered_cycles(domain_id: str, observations: list[dict]) -> int:
    """Count DISTINCT cycle_ids in prior observations where domain_id was uncovered."""
    cycles: set[str] = set()
    for row in observations:
        if domain_id in (row.get("uncovered") or []):
            cid = row.get("cycle_id")
            if cid:
                cycles.add(str(cid))
    return len(cycles)


def _append_observation(row: dict, root: Path) -> bool:
    try:
        d = root.joinpath(*SCOUT_DIR)
        d.mkdir(parents=True, exist_ok=True)
        with (d / OBSERVATIONS_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._append_observation: %s", exc)
        return False


# ── Roster budget (advisory snapshot; never blocks — R-V2-7) ──────────────────

def _roster_snapshot(root: Path) -> dict[str, Any]:
    """Read-only roster budget snapshot.  Does NOT write a tap card (that ASK
    fires at onboarding via roster_governor).  NEVER raises."""
    snap: dict[str, Any] = {
        "active_nonscored": None,
        "max_active_nonscored_lobes": None,
        "would_exceed_active_cap": None,
    }
    try:
        from engine.metabolism.lobe_registry import active_nonscored_count  # noqa: PLC0415
        cur = active_nonscored_count(root)
        snap["active_nonscored"] = cur
        cfg = _load_yaml(root.joinpath(*_BUDGET_CFG)) or {}
        cap = cfg.get("max_active_nonscored_lobes")
        if cap is not None:
            cap = int(cap)
            snap["max_active_nonscored_lobes"] = cap
            # A new lobe onboards to `probation` first, but its eventual `active`
            # state would occupy one active slot; flag if the roster is already full.
            snap["would_exceed_active_cap"] = cur >= cap
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._roster_snapshot: %s", exc)
    return snap


# ── Charter proposal emission ─────────────────────────────────────────────────

def _charter_proposal_path(domain_id: str, root: Path) -> Path:
    slug = str(domain_id).replace("/", "_")
    return root.joinpath(*CHARTER_PROPOSAL_DIR) / f"{slug}.json"


def _build_charter_proposal(
    domain: dict,
    *,
    cycle_id: str | None,
    uncovered_for_cycles: int,
    min_cycles: int,
    evidence_count: int,
    evidence_refs: list[str],
    roster: dict,
    ts: str,
) -> dict[str, Any]:
    domain_id = domain.get("domain_id")
    label = domain.get("label", domain_id)
    return {
        "schema": SCHEMA_CHARTER_PROPOSAL,
        "ts": ts,
        "cycle_id": cycle_id,
        "domain_id": domain_id,
        "label": label,
        "description": str(domain.get("description", "")).strip(),
        "proposed_tier": _PROPOSED_TIER,
        "proposed_lifecycle_state": _PROPOSED_LIFECYCLE_STATE,
        "uncovered_for_cycles": uncovered_for_cycles,
        "min_uncovered_cycles": min_cycles,
        "demand_evidence_count": evidence_count,
        "evidence_refs": evidence_refs,
        "roster_budget": roster,
        "rationale": (
            f"Domain {domain_id!r} ({label}) has had ZERO active covering lobes "
            f"across {uncovered_for_cycles} distinct scout cycles "
            f"(threshold={min_cycles}); {evidence_count} open insight-bus row(s) "
            f"reference this domain. Proposing a display-tier lobe charter for the "
            f"normal gauntlet. This is a recurring coverage gap, not a whim."
        ),
        "generated_by": "metabolism_scout",
        "authority": dict(_AUTHORITY_BLOCK),
    }


def _emit_insight(domain_id: str, summary: str, evidence_ref: str, cycle_id: str | None, root: Path) -> bool:
    try:
        from engine.metabolism.insight_bus import append_row, build_row  # noqa: PLC0415
        row = build_row(
            emitter="metabolism_scout",
            kind="uncovered_domain",
            severity="medium",
            entities=[f"domain:{domain_id}"],
            summary=summary,
            evidence_ref=evidence_ref,
            cycle_id=cycle_id,
        )
        return append_row(row, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("scout._emit_insight(%s): %s", domain_id, exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def scan(
    cycle_id: str,
    *,
    root: str | Path | None = None,
    emit: bool = True,
) -> dict[str, Any]:
    """Run one uncovered-domain scan.

    Parameters
    ----------
    cycle_id : str
        This scout cycle's id.  Persistence is counted over DISTINCT cycle_ids.
    root : str | Path | None
        Project root (None = production paths).
    emit : bool
        If True (default), append the observation row and write charter proposals
        + insight-bus rows for domains that cross the persistence threshold.
        If False, compute the decision with ZERO I/O (dry-run).

    Returns
    -------
    dict (schema metabolism.scout_scan.v1) with keys:
        cycle_id, universe_size,
        covered           : list[domain_id]
        uncovered         : list[domain_id]   — zero active covering lobes THIS cycle
        thinly_covered    : list[dict]        — covered, but every covering lobe is
                                                 in a weak trajectory (context only,
                                                 NOT proposed — the domain IS covered)
        emitted           : list[dict]        — proposals written this run
        already_proposed  : list[domain_id]   — uncovered + a standing proposal exists
        accruing          : list[dict]        — uncovered but below the persistence gate
        authority         : AUTHORITY_BLOCK

    NEVER raises.
    """
    ts = _now_utc()
    result: dict[str, Any] = {
        "schema": SCHEMA_SCAN,
        "ts": ts,
        "cycle_id": cycle_id,
        "universe_size": 0,
        "covered": [],
        "uncovered": [],
        "thinly_covered": [],
        "emitted": [],
        "already_proposed": [],
        "accruing": [],
        "authority": dict(_AUTHORITY_BLOCK),
    }
    try:
        r = _resolve_root(root)
        uni = _load_domains(r)
        domains = uni["domains"]
        default_min = uni["default_min"]
        result["universe_size"] = len(domains)
        if not domains:
            return result

        identities = _active_identities(r)
        labels = _trajectory_labels(r)
        observations = _read_observations(r)

        covered_ids: list[str] = []
        uncovered_ids: list[str] = []
        thinly_covered: list[dict] = []
        for domain in domains:
            did = domain.get("domain_id")
            covering = _covering_lobes(domain, identities)
            covered = bool(covering) or not _has_coverage_spec(domain)
            if covered:
                covered_ids.append(did)
                # Thin coverage: EVERY covering lobe has a KNOWN weak trajectory
                # label and at least one is actively degrading. A single
                # compounding/accruing covering lobe = healthy coverage → not thin;
                # an UNLABELED covering lobe = unknown health → honest-null, not thin.
                known = [labels[l] for l in covering if l in labels]
                if (
                    covering
                    and len(known) == len(covering)
                    and all(lbl in _WEAK_LABELS for lbl in known)
                    and any(lbl == "degrading" for lbl in known)
                ):
                    thinly_covered.append({
                        "domain_id": did,
                        "covering_lobes": covering,
                        "labels": {l: labels.get(l) for l in covering},
                    })
            else:
                uncovered_ids.append(did)
        result["covered"] = covered_ids
        result["uncovered"] = uncovered_ids
        result["thinly_covered"] = thinly_covered

        # Append THIS cycle's observation first so it counts toward persistence.
        # Skip a redundant append on an intraday re-run of the SAME cycle with an
        # identical uncovered set (the distinct-cycle count is unaffected either way).
        last = observations[-1] if observations else None
        redundant = (
            isinstance(last, dict)
            and last.get("cycle_id") == cycle_id
            and (last.get("uncovered") or []) == uncovered_ids
        )
        if emit and not redundant:
            _append_observation(
                {
                    "schema": SCHEMA_OBSERVATION,
                    "ts": ts,
                    "cycle_id": cycle_id,
                    "covered": covered_ids,
                    "uncovered": uncovered_ids,
                    "authority": dict(_AUTHORITY_BLOCK),
                },
                r,
            )

        roster = _roster_snapshot(r)
        domain_by_id = {d.get("domain_id"): d for d in domains}

        for did in uncovered_ids:
            domain = domain_by_id.get(did, {})
            min_cycles = _domain_min_cycles(domain, default_min)

            # Effective distinct-uncovered-cycle count INCLUDING this cycle.
            prior = _prior_distinct_uncovered_cycles(did, observations)
            prior_had_this_cycle = any(
                (row.get("cycle_id") == cycle_id and did in (row.get("uncovered") or []))
                for row in observations
            )
            effective = prior + (0 if prior_had_this_cycle else 1)

            if effective < min_cycles:
                result["accruing"].append(
                    {"domain_id": did, "uncovered_cycles": effective, "min_uncovered_cycles": min_cycles}
                )
                continue

            # Threshold met. Idempotent: one standing proposal per domain.
            prop_path = _charter_proposal_path(did, r)
            if prop_path.exists():
                result["already_proposed"].append(did)
                continue

            ev_count, ev_refs = _count_evidence(domain, r)
            proposal = _build_charter_proposal(
                domain,
                cycle_id=cycle_id,
                uncovered_for_cycles=effective,
                min_cycles=min_cycles,
                evidence_count=ev_count,
                evidence_refs=ev_refs,
                roster=roster,
                ts=ts,
            )

            if emit:
                try:
                    prop_path.parent.mkdir(parents=True, exist_ok=True)
                    prop_path.write_text(
                        json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    proposal["_written_to"] = str(prop_path)
                except Exception as exc:  # noqa: BLE001
                    log.warning("scout.scan: failed to write proposal for %s: %s", did, exc)
                _emit_insight(
                    did,
                    summary=(
                        f"Uncovered domain {did!r} recurred for {effective} cycles "
                        f"(>= {min_cycles}); display-tier charter proposed for the gauntlet."
                    ),
                    evidence_ref=str(prop_path),
                    cycle_id=cycle_id,
                    root=r,
                )
            result["emitted"].append(proposal)

    except Exception as exc:  # noqa: BLE001
        log.warning("scout.scan: unexpected error: %s", exc)
        result["error"] = str(exc)

    return result
