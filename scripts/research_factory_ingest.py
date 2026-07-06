"""scripts/research_factory_ingest.py — W2 deterministic ingest.

Sources
-------
(a) --manual <path>     : JSON file or dir of candidate proposal dicts.
(b) --oracle-scratch <dir> : oracle_ingest_brainstorm registry.jsonl output;
    --oracle-inbox <dir>   : original inbox dir for pre-strip mechanism capture
                             (absent-safe: falls back to hypothesis text + flag).
(c) --research-queue    : data/neuralweb/research_queue.json high_ev_build_now;
    --nominate <id>        : nominate a specific row id from any bin.

Dedup pipeline (RF-14, in fixed order):
  1. data/oracle/compounds/registry.jsonl  (canonical rule-hash)
  2. data/species/registry.json           (species_registry.load())
  3. data/neuralweb/machine_registry.jsonl (absent-safe)
  4. trial-ledger family strings

Structural near-dup: largest-common-subtree ratio ≥ 0.8 → flag 'near_dup_review'
Mechanism↔spec alignment: column names not mentioned in mechanism → flag
'mechanism_spec_mismatch'

Respins: --respin-of <candidate_id>; --actor / --actor-ref for human gate.
rf.* family declaration: --declare-family rf.<domain>.<slug>

Exit gate: dry-run prints every drop with reason; --write commits to disk.

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §6 W2 + rulings
RF-13/RF-14/RF-15.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# W1 engine imports
from engine.research_factory.schema import (
    validate_candidate,
    validate_transition,
    is_valid_rf_family_name,
)
from engine.research_factory.state import transition as state_transition, IllegalTransition
from engine.research_factory import ledger as rf_ledger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_RF_DIR = ROOT / "data" / "research_factory"
DEFAULT_ORACLE_REGISTRY = ROOT / "data" / "oracle" / "compounds" / "registry.jsonl"
DEFAULT_SPECIES_REGISTRY = ROOT / "data" / "species" / "registry.json"
DEFAULT_MACHINE_REGISTRY = ROOT / "data" / "neuralweb" / "machine_registry.jsonl"
DEFAULT_TRIAL_LEDGER = ROOT / "data" / "trial_ledger.jsonl"
DEFAULT_RESEARCH_QUEUE = ROOT / "data" / "neuralweb" / "research_queue.json"

# Frozen oracle reversion gate rulers (RF-13; read from oracle_reversion_screen._FROZEN_GATES)
REVERSION_FROZEN_RULERS: dict[str, Any] = {
    "primary_metric": "WR",
    "secondary_metrics": ["asym", "ret_exit"],
    "min_n": 100,         # Leg 1: n >= 100 (_FROZEN_GATES["leg1_n"])
    "gate_WR": 0.62,      # Leg 2 (_FROZEN_GATES["leg2_wr"])
    "gate_asym": 1.5,     # Leg 3 (_FROZEN_GATES["leg3_asym"])
    "gate_ret": 0.01,     # Leg 4: ret_exit >= +1.0% (_FROZEN_GATES["leg4_ret"])
    "holdout_min_n": 100, # Leg 5
    "holdout_min_WR": 0.58,
    "source": "scripts/oracle_reversion_screen.py _FROZEN_GATES + screen_compound()",
}

# Column synonym map for mechanism↔spec alignment (RF-7)
_COL_SYNONYMS: dict[str, set[str]] = {
    "breadth": {"breadth", "breadth_50"},
    "turnover": {"turnover", "turnover_z"},
    "vix": {"vix", "vix_pctile"},
    "flow": {"flow", "vel_1w", "vel_4w"},
    "momentum": {"momentum", "mom", "rs", "rs_chg"},
    "volume": {"volume", "vol", "turnover"},
    "cohesion": {"cohesion", "cohesion_chg", "cohesion_rebuild"},
    "washout": {"washout_w", "washout"},
    "macd": {"macd", "macd_signal"},
    "stochrsi": {"stochrsi_w_k", "stochrsi_w_d"},
}
# Build reverse: col_name -> set of synonym words to check in mechanism text
_COL_TO_WORDS: dict[str, set[str]] = {}
for _words, _cols in _COL_SYNONYMS.items():
    for _col in _cols:
        _COL_TO_WORDS.setdefault(_col, set()).add(_words)
        _COL_TO_WORDS[_col].add(_col.split("_")[0])  # first part of col name


# ---------------------------------------------------------------------------
# Canonical helpers (RF-14 — reuse oracle_ingest_brainstorm._canonical)
# ---------------------------------------------------------------------------

def _canonical(rule: dict) -> str:
    """Deterministic canonical hash string for an entry_rule dict (RF-14)."""
    try:
        from scripts.oracle_ingest_brainstorm import _canonical as _ib_canonical
        return _ib_canonical(rule)
    except Exception:
        # Fallback replication if import fails
        return json.dumps(rule, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Structural near-dup: largest-common-subtree (pure stdlib)
# ---------------------------------------------------------------------------

def _subtree_nodes(tree: Any) -> int:
    """Count nodes in a dict/list/scalar tree."""
    if isinstance(tree, dict):
        return 1 + sum(_subtree_nodes(v) for v in tree.values())
    if isinstance(tree, list):
        return 1 + sum(_subtree_nodes(i) for i in tree)
    return 1


def _common_subtree_nodes(a: Any, b: Any) -> int:
    """Count nodes shared between two trees (largest-common-subtree approximation).

    Uses structural recursion: two nodes match if they are the same type and
    value at leaves, or both dicts/lists with matching keys/indices.
    Returns the count of shared nodes.
    """
    if type(a) != type(b):
        return 0
    if isinstance(a, dict):
        shared = 1  # root dict node matches
        for k in set(a) & set(b):
            shared += _common_subtree_nodes(a[k], b[k])
        return shared
    if isinstance(a, list):
        if len(a) == 0 and len(b) == 0:
            return 1
        shared = 1
        # Pair up items by position (structural match)
        for i in range(min(len(a), len(b))):
            shared += _common_subtree_nodes(a[i], b[i])
        return shared
    # Scalar leaf: match iff equal
    return 1 if a == b else 0


def _near_dup_score(rule_a: dict, rule_b: dict) -> float:
    """Compute structural near-dup ratio: shared nodes / max(nodes_a, nodes_b)."""
    n_a = _subtree_nodes(rule_a)
    n_b = _subtree_nodes(rule_b)
    denom = max(n_a, n_b)
    if denom == 0:
        return 0.0
    shared = _common_subtree_nodes(rule_a, rule_b)
    return shared / denom


# ---------------------------------------------------------------------------
# Dedup registry loaders (RF-14)
# ---------------------------------------------------------------------------

def _load_oracle_canonical_rules(oracle_registry_path: Path) -> set[str]:
    """Load canonical rule-hashes from the live oracle compounds registry."""
    if not oracle_registry_path.exists():
        return set()
    seen: set[str] = set()
    try:
        with oracle_registry_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                rule = row.get("entry_rule")
                if isinstance(rule, dict):
                    seen.add(_canonical(rule))
    except OSError:
        pass
    return seen


def _load_oracle_entry_rules(oracle_registry_path: Path) -> list[dict]:
    """Load all entry_rule dicts from the oracle registry (for near-dup scoring)."""
    if not oracle_registry_path.exists():
        return []
    rules: list[dict] = []
    try:
        with oracle_registry_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                rule = row.get("entry_rule")
                if isinstance(rule, dict):
                    rules.append(rule)
    except OSError:
        pass
    return rules


def _load_species_names(species_registry_path: Path) -> set[str]:
    """Load hypothesis/name strings from species registry for dedup (RF-14)."""
    if not species_registry_path.exists():
        return set()
    try:
        import engine.species_registry as sr
        reg = sr.load(species_registry_path)
        names: set[str] = set()
        for s in reg.get("species", []):
            sid = s.get("species_id", "")
            name = s.get("name", "")
            mechanism = s.get("mechanism", "")
            if sid:
                names.add(sid.lower().strip())
            if name:
                names.add(name.lower().strip())
            if mechanism:
                names.add(mechanism.lower().strip()[:120])
        return names
    except Exception:
        return set()


def _load_machine_registry_hypotheses(machine_registry_path: Path) -> set[str]:
    """Load hypothesis strings from machine_registry.jsonl (absent-safe, RF-14)."""
    if not machine_registry_path.exists():
        return set()
    hyps: set[str] = set()
    try:
        with machine_registry_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                hyp = row.get("hypothesis") or row.get("name") or ""
                if hyp:
                    hyps.add(hyp.lower().strip()[:120])
    except OSError:
        pass
    return hyps


def _load_trial_ledger_families(trial_ledger_path: Path) -> set[str]:
    """Load known family strings from data/trial_ledger.jsonl (RF-14)."""
    if not trial_ledger_path.exists():
        return set()
    families: set[str] = set()
    try:
        with trial_ledger_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                fam = row.get("family")
                if fam and isinstance(fam, str):
                    families.add(fam.lower().strip())
    except OSError:
        pass
    return families


# ---------------------------------------------------------------------------
# Mechanism↔spec alignment check (RF-7)
# ---------------------------------------------------------------------------

def _rule_columns(rule: Any, acc: set | None = None) -> set[str]:
    """Recursively extract all column references from an entry_rule dict."""
    if acc is None:
        acc = set()
    if not isinstance(rule, dict):
        if isinstance(rule, list):
            for item in rule:
                _rule_columns(item, acc)
        return acc
    for key in ("all", "any"):
        for sub in rule.get(key, []):
            _rule_columns(sub, acc)
    col = rule.get("col")
    if col:
        acc.add(col)
    vcol = rule.get("value_col")
    if vcol:
        acc.add(vcol)
    return acc


def _mechanism_spec_mismatch(mechanism: str, entry_rule: dict | None) -> bool:
    """True if none of the entry_rule columns (or synonyms) appear in mechanism text.

    Returns False (no mismatch) if entry_rule is absent or has no columns.
    """
    if not entry_rule or not isinstance(entry_rule, dict):
        return False
    cols = _rule_columns(entry_rule)
    if not cols:
        return False
    mech_lower = mechanism.lower() if mechanism else ""
    for col in cols:
        # Check direct col name
        if col.lower() in mech_lower:
            return False
        # Check synonyms
        words = _COL_TO_WORDS.get(col, set())
        for w in words:
            if w.lower() in mech_lower:
                return False
    return True


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

def _make_candidate_id(source_tag: str, slug: str) -> str:
    """Generate a deterministic-ish candidate_id: rf-<date>-<source>-<slug>."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    # Sanitise slug: lowercase, alphanum + dash
    safe_slug = "".join(c if c.isalnum() or c == "-" else "_" for c in slug.lower())[:32]
    return f"rf-{date_str}-{source_tag}-{safe_slug}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Evaluation plan read-back (RF-13, RF-5)
# ---------------------------------------------------------------------------

def _evaluation_plan_for_oracle_reversion() -> dict:
    """Return the frozen evaluation_plan for oracle reversion-track candidates.

    Values are read back from oracle_reversion_screen.py constants — never
    authored by the factory. Divergences from a submitted plan are flagged as
    schema warnings, not instructions to the evaluator.
    """
    return {
        "primary_metric": REVERSION_FROZEN_RULERS["primary_metric"],
        "secondary_metrics": list(REVERSION_FROZEN_RULERS["secondary_metrics"]),
        "min_n": REVERSION_FROZEN_RULERS["min_n"],
        "gate_WR": REVERSION_FROZEN_RULERS["gate_WR"],
        "gate_asym": REVERSION_FROZEN_RULERS["gate_asym"],
        "gate_ret": REVERSION_FROZEN_RULERS["gate_ret"],
        "horizon_d": 21,
        "horizon_role": "reversion",
        "fdr_scope": "batch",
        "expected_half_life_d": None,
        "defaulted": True,
        "ruler_source": REVERSION_FROZEN_RULERS["source"],
    }


def _default_evaluation_plan() -> dict:
    return {
        "primary_metric": None,
        "horizon_d": 21,
        "min_n": 25,
        "fdr_scope": "batch",
        "expected_half_life_d": None,
        "defaulted": True,
    }


# ---------------------------------------------------------------------------
# Proposal → candidate dict builder
# ---------------------------------------------------------------------------

def _build_candidate(
    *,
    source: str,
    candidate_type: str,
    domain: str,
    hypothesis: str,
    mechanism: str,
    spec_ref: str | None,
    entry_rule: dict | None,
    candidate_id: str | None = None,
    evaluation_plan: dict | None = None,
    respin_of: str | None = None,
    extra_flags: list[str] | None = None,
    mechanism_missing_from_inbox: bool = False,
) -> dict:
    """Build a research_factory.candidate.v1 dict at status='proposed'."""
    cid = candidate_id or _make_candidate_id(source, hypothesis[:32])
    flags: list[str] = list(extra_flags or [])
    if mechanism_missing_from_inbox:
        flags.append("mechanism_missing_from_inbox")

    row: dict = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "created_at": _now_iso(),
        "source": source,
        "candidate_type": candidate_type,
        "domain": domain,
        "status": "proposed",
        "hypothesis": hypothesis,
        "mechanism": mechanism,
        "claim_shape": None,
        "spec_ref": spec_ref,
        "expected_failure_modes": [],
        "decay_conditions": [],
        "falsifiers": [],
        "trial_accounting": {"mode": "read_only", "family": None, "declared_at": None},
        "evaluation_plan": evaluation_plan or _default_evaluation_plan(),
        "lineage": {
            "respin_of": respin_of,
            "superseded_by": None,
            "refinement_generation": 1 if respin_of else 0,
        },
        "flags": flags,
        "artifacts": {},
        "transition_log": [],
    }
    return row


def _build_transition(
    candidate_id: str,
    from_state: str,
    to_state: str,
    reason_code: str,
    reason_text: str,
    actor: str,
    actor_ref: str | None = None,
    **extra,
) -> dict:
    row: dict = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": from_state,
        "to": to_state,
        "reason_code": reason_code,
        "reason_text": reason_text,
        "actor": actor,
        "actor_ref": actor_ref,
        "kill_evidence": None,
        "artifact_refs": [],
        "as_of": _now_iso(),
    }
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# Source (a): manual JSON proposals
# ---------------------------------------------------------------------------

def _load_manual_proposals(path: Path) -> list[dict]:
    """Load manual proposals from a JSON file or dir of JSON files."""
    paths: list[Path] = []
    if path.is_dir():
        paths = sorted(path.glob("*.json"))
    elif path.exists():
        paths = [path]
    else:
        return []

    proposals: list[dict] = []
    for p in paths:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [WARN] manual: failed to parse {p}: {exc}", file=sys.stderr)
            continue
        if isinstance(raw, list):
            proposals.extend(raw)
        elif isinstance(raw, dict):
            proposals.append(raw)
    return proposals


def _ingest_manual(
    proposal: dict,
    *,
    respin_of: str | None = None,
    actor: str = "script",
    actor_ref: str | None = None,
) -> dict:
    """Convert a manual proposal dict to a candidate row."""
    source = "human" if respin_of else proposal.get("source", "human")
    ctype = proposal.get("candidate_type", "external_idea")
    domain = proposal.get("domain", "oracle")
    hypothesis = proposal.get("hypothesis", proposal.get("name", ""))
    mechanism = proposal.get("mechanism", hypothesis)
    spec_ref = proposal.get("spec_ref")
    entry_rule = proposal.get("entry_rule")
    cid = proposal.get("candidate_id")

    ep = proposal.get("evaluation_plan") or _default_evaluation_plan()

    return _build_candidate(
        source=source,
        candidate_type=ctype,
        domain=domain,
        hypothesis=hypothesis,
        mechanism=mechanism,
        spec_ref=spec_ref,
        entry_rule=entry_rule,
        candidate_id=cid,
        evaluation_plan=ep,
        respin_of=respin_of,
    )


# ---------------------------------------------------------------------------
# Source (b): oracle scratch-registry + inbox mechanism capture
# ---------------------------------------------------------------------------

def _capture_inbox_mechanisms(inbox_dir: Path) -> dict[str, str]:
    """Read original inbox JSON files (pre-8-field strip) to capture mechanism text.

    Returns dict: canonical(entry_rule) -> mechanism_text.
    Absent-safe: returns {} if inbox_dir is None or absent.
    """
    if not inbox_dir or not inbox_dir.exists():
        return {}
    result: dict[str, str] = {}
    try:
        from scripts.oracle_ingest_brainstorm import _parse_json_multi
    except Exception:
        def _parse_json_multi(text):  # type: ignore[misc]
            try:
                val = json.loads(text)
                return val if isinstance(val, list) else [val]
            except Exception:
                return []

    for fp in sorted(inbox_dir.glob("*.json")):
        try:
            raw_text = fp.read_text(encoding="utf-8")
            specs = _parse_json_multi(raw_text)
        except Exception:
            continue
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            rule = spec.get("entry_rule")
            if not isinstance(rule, dict):
                continue
            key = _canonical(rule)
            # Capture pre-strip fields: mechanism, mechanism_en, description, rationale
            mech = (
                spec.get("mechanism")
                or spec.get("mechanism_en")
                or spec.get("description")
                or spec.get("rationale")
                or ""
            )
            if mech and key not in result:
                result[key] = mech
    return result


def _ingest_oracle_scratch(
    scratch_dir: Path,
    inbox_mechanisms: dict[str, str],
) -> list[dict]:
    """Load oracle_ingest_brainstorm scratch registry.jsonl and build candidates."""
    registry_path = scratch_dir / "compounds" / "registry.jsonl"
    if not registry_path.exists():
        # Try direct registry.jsonl at root of scratch_dir
        registry_path = scratch_dir / "registry.jsonl"
    if not registry_path.exists():
        print(f"  [WARN] oracle-scratch: no registry.jsonl found under {scratch_dir}", file=sys.stderr)
        return []

    candidates: list[dict] = []
    try:
        with registry_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                rule = row.get("entry_rule")
                canon_key = _canonical(rule) if isinstance(rule, dict) else None

                # Mechanism capture: inbox first, then fallback
                mechanism_missing = False
                mechanism = ""
                if canon_key and canon_key in inbox_mechanisms:
                    mechanism = inbox_mechanisms[canon_key]
                else:
                    # Fallback to hypothesis / name / mechanism_en in scratch row
                    mechanism = (
                        row.get("mechanism_en")
                        or row.get("mechanism")
                        or row.get("name", "")
                        or ""
                    )
                    if not mechanism:
                        mechanism = row.get("name", "")
                    mechanism_missing = True

                hypothesis = row.get("name") or row.get("id", "")
                spec_ref = row.get("id")

                cand = _build_candidate(
                    source="oracle_brainstorm",
                    candidate_type="oracle_compound",
                    domain="oracle",
                    hypothesis=hypothesis,
                    mechanism=mechanism,
                    spec_ref=spec_ref,
                    entry_rule=rule,
                    evaluation_plan=_evaluation_plan_for_oracle_reversion(),
                    mechanism_missing_from_inbox=mechanism_missing,
                )
                # Attach entry_rule into artifacts for near-dup scoring
                cand["artifacts"]["entry_rule"] = rule
                # Propagate extra oracle flags from scratch row
                existing_flags = set(cand["flags"])
                if row.get("lineage") and "recent_only" in str(row.get("lineage", "")):
                    existing_flags.add("recent_only_columns")
                cand["flags"] = sorted(existing_flags)
                candidates.append(cand)
    except OSError as exc:
        print(f"  [WARN] oracle-scratch: failed to read {registry_path}: {exc}", file=sys.stderr)
    return candidates


# ---------------------------------------------------------------------------
# Source (c): research_queue
# ---------------------------------------------------------------------------

def _load_research_queue(queue_path: Path, nominate_ids: list[str]) -> list[dict]:
    """Load high_ev_build_now rows + operator-nominated rows from research_queue.json."""
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [WARN] research-queue: failed to parse {queue_path}: {exc}", file=sys.stderr)
        return []

    if not isinstance(data, dict):
        return []

    selected: list[dict] = []
    seen_ids: set[str] = set()

    def _add_rows(rows: list) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = row.get("id") or row.get("candidate_id") or ""
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            selected.append(row)

    # high_ev_build_now
    high_ev = data.get("high_ev_build_now", [])
    if isinstance(high_ev, list):
        _add_rows(high_ev)

    # operator-nominated from any bin
    if nominate_ids:
        nominate_set = set(nominate_ids)
        for bin_key, bin_rows in data.items():
            if not isinstance(bin_rows, list):
                continue
            for row in bin_rows:
                if not isinstance(row, dict):
                    continue
                rid = row.get("id") or row.get("candidate_id") or ""
                if rid in nominate_set and rid not in seen_ids:
                    seen_ids.add(rid)
                    selected.append(row)

    return selected


def _ingest_research_queue_row(row: dict) -> dict:
    """Convert a research_queue row to a candidate dict."""
    hypothesis = row.get("hypothesis") or row.get("name") or row.get("id", "")
    mechanism = row.get("mechanism") or hypothesis
    domain = row.get("domain", "oracle")
    ctype = row.get("candidate_type", "external_idea")
    spec_ref = row.get("id") or row.get("spec_ref")

    return _build_candidate(
        source="research_queue",
        candidate_type=ctype,
        domain=domain,
        hypothesis=hypothesis,
        mechanism=mechanism,
        spec_ref=spec_ref,
        entry_rule=row.get("entry_rule"),
        evaluation_plan=row.get("evaluation_plan") or _default_evaluation_plan(),
    )


# ---------------------------------------------------------------------------
# Dedup engine (RF-14 — deterministic, in fixed order)
# ---------------------------------------------------------------------------

class DedupeResult:
    __slots__ = ("matched", "registry", "matched_id", "reason")

    def __init__(self, matched: bool, registry: str, matched_id: str, reason: str):
        self.matched = matched
        self.registry = registry
        self.matched_id = matched_id
        self.reason = reason


def _check_dedup(
    cand: dict,
    oracle_canonical_rules: set[str],
    species_names: set[str],
    machine_hyps: set[str],
    trial_families: set[str],
    existing_candidate_ids: set[str],
) -> DedupeResult | None:
    """Run RF-14 dedup in fixed order.  Returns DedupeResult if matched, None if clean."""
    # 0. Factory ledger (idempotent re-ingest guard, RF-14) — checked FIRST so a
    #    candidate that already exists in the ledger is caught before any external-
    #    registry check.  Without this ordering, a candidate whose candidate_id is
    #    already on disk but whose hypothesis also collides with the oracle/species/
    #    machine/trial registry would return a non-factory_ledger registry, bypass the
    #    disk-write skip, and append a duplicate row on every re-ingest run.
    cid = cand.get("candidate_id", "")
    if cid and cid in existing_candidate_ids:
        return DedupeResult(
            matched=True,
            registry="factory_ledger",
            matched_id=cid[:32],
            reason="candidate_id already in factory ledger (idempotent re-ingest)",
        )

    # 1. Oracle compounds registry (canonical rule-hash)
    entry_rule = cand.get("artifacts", {}).get("entry_rule") or (
        cand.get("evaluation_plan", {}).get("_entry_rule")  # fallback
    )
    if not entry_rule:
        # Check spec_ref as fallback for manual proposals
        pass
    if entry_rule and isinstance(entry_rule, dict):
        key = _canonical(entry_rule)
        if key in oracle_canonical_rules:
            return DedupeResult(
                matched=True,
                registry="oracle_compounds_registry",
                matched_id=key[:32],
                reason="entry_rule matches live oracle registry (canonical hash)",
            )

    # 2. Species registry (name/mechanism string match)
    hyp_key = (cand.get("hypothesis") or "").lower().strip()[:120]
    mech_key = (cand.get("mechanism") or "").lower().strip()[:120]
    if hyp_key and hyp_key in species_names:
        return DedupeResult(
            matched=True,
            registry="species_registry",
            matched_id=hyp_key[:32],
            reason="hypothesis matches species registry name/mechanism",
        )
    if mech_key and mech_key in species_names:
        return DedupeResult(
            matched=True,
            registry="species_registry",
            matched_id=mech_key[:32],
            reason="mechanism matches species registry name/mechanism",
        )

    # 3. Machine registry (hypothesis string match)
    if hyp_key and hyp_key in machine_hyps:
        return DedupeResult(
            matched=True,
            registry="machine_registry",
            matched_id=hyp_key[:32],
            reason="hypothesis matches machine registry hypothesis",
        )
    if mech_key and mech_key in machine_hyps:
        return DedupeResult(
            matched=True,
            registry="machine_registry",
            matched_id=mech_key[:32],
            reason="mechanism matches machine registry hypothesis",
        )

    # 4. Trial-ledger family strings
    spec_ref = (cand.get("spec_ref") or "").lower().strip()
    if spec_ref and spec_ref in trial_families:
        return DedupeResult(
            matched=True,
            registry="trial_ledger",
            matched_id=spec_ref[:32],
            reason="spec_ref matches trial-ledger family string",
        )

    return None


def _check_near_dup(
    cand: dict,
    oracle_entry_rules: list[dict],
    threshold: float = 0.8,
) -> tuple[bool, float]:
    """Check structural near-dup against oracle registry entry_rules.

    Returns (is_near_dup, max_score).
    """
    entry_rule = cand.get("artifacts", {}).get("entry_rule")
    if not entry_rule or not isinstance(entry_rule, dict):
        return False, 0.0
    max_score = 0.0
    for oracle_rule in oracle_entry_rules:
        score = _near_dup_score(entry_rule, oracle_rule)
        if score > max_score:
            max_score = score
    return max_score >= threshold, max_score


# ---------------------------------------------------------------------------
# Main ingest pipeline
# ---------------------------------------------------------------------------

class IngestResult:
    """Accumulates candidates and transition records for dry-run vs write."""

    def __init__(self) -> None:
        self.registered: list[tuple[dict, dict]] = []   # (candidate, transition)
        self.dropped: list[tuple[dict, str, str]] = []  # (candidate, reason_code, reason_text)

    def add_registered(self, cand: dict, trans: dict) -> None:
        self.registered.append((cand, trans))

    def add_dropped(self, cand: dict, reason_code: str, reason_text: str) -> None:
        self.dropped.append((cand, reason_code, reason_text))

    def print_summary(self) -> None:
        print(f"\nIngest summary: {len(self.registered)} registered, {len(self.dropped)} dropped")
        if self.dropped:
            print("Dropped candidates:")
            for cand, rc, rt in self.dropped:
                cid = cand.get("candidate_id", "?")
                print(f"  DROP [{rc}] {cid}: {rt}")
        if self.registered:
            print("Registered candidates:")
            for cand, trans in self.registered:
                cid = cand.get("candidate_id", "?")
                hyp = (cand.get("hypothesis") or "")[:60]
                flags = cand.get("flags") or []
                print(f"  REG  {cid}: {hyp}" + (f" (flags: {flags})" if flags else ""))


def run_ingest(
    proposals: list[dict],
    *,
    oracle_registry_path: Path | None = None,
    species_registry_path: Path | None = None,
    machine_registry_path: Path | None = None,
    trial_ledger_path: Path | None = None,
    existing_candidate_ids: set[str] | None = None,
    respin_of: str | None = None,
    actor: str = "script",
    actor_ref: str | None = None,
    declare_family: str | None = None,
    rf_dir: Path | None = None,
    dry_run: bool = True,
) -> IngestResult:
    """Run the full ingest pipeline over a list of candidate dicts.

    Parameters
    ----------
    proposals          : Pre-built candidate dicts (output of _build_candidate).
    oracle_registry_path : Override for data/oracle/compounds/registry.jsonl.
    species_registry_path: Override for data/species/registry.json.
    machine_registry_path: Override for data/neuralweb/machine_registry.jsonl.
    trial_ledger_path  : Override for data/trial_ledger.jsonl.
    existing_candidate_ids : candidate_ids already in the factory ledger (dedup).
    respin_of          : If set, all proposals are respins of this candidate_id.
    actor              : Transition actor.
    actor_ref          : Required for human actors.
    declare_family     : rf.* family name; triggers TrialLedger.log_declared_budget.
    rf_dir             : Override for data/research_factory/.
    dry_run            : If True, print results without writing to disk.
    """
    oracle_reg_path = oracle_registry_path or DEFAULT_ORACLE_REGISTRY
    species_reg_path = species_registry_path or DEFAULT_SPECIES_REGISTRY
    machine_reg_path = machine_registry_path or DEFAULT_MACHINE_REGISTRY
    trial_led_path = trial_ledger_path or DEFAULT_TRIAL_LEDGER
    out_dir = rf_dir or DEFAULT_RF_DIR
    existing_ids = existing_candidate_ids or set()

    # Load dedup registries
    oracle_canonical = _load_oracle_canonical_rules(oracle_reg_path)
    oracle_rules = _load_oracle_entry_rules(oracle_reg_path)
    species_names = _load_species_names(species_reg_path)
    machine_hyps = _load_machine_registry_hypotheses(machine_reg_path)
    trial_families = _load_trial_ledger_families(trial_led_path)

    # Build a dict of existing candidates for respin lineage + generation cap (RF-15).
    # Loaded lazily from disk only when respin_of is set and the ledger may exist.
    existing_cands_by_id: dict[str, dict] = {}
    if respin_of:
        candidates_path = out_dir / "candidates.jsonl"
        if candidates_path.exists():
            for _ec in rf_ledger.load_jsonl(candidates_path):
                _cid = _ec.get("candidate_id")
                if _cid:
                    existing_cands_by_id[_cid] = _ec

    # Handle respin: inject respin_of into lineage + enforce human gate
    if respin_of and actor in ("script", "codex", "sonnet"):
        print(
            f"  [ERROR] respin_of={respin_of!r} requires a human actor "
            f"(fable/operator) with --actor-ref. Script actors are not permitted. "
            f"(RF-5/RF-15)",
            file=sys.stderr,
        )
        result = IngestResult()
        for cand in proposals:
            result.add_dropped(
                cand,
                "respin_gate_violation",
                f"respin registration requires human actor; got actor={actor!r}",
            )
        return result

    # Declare rf.* family budget BEFORE any writes (RF-6).
    # OPERATOR-ONLY ACTION: --declare-family writes a kind:declared_budget row to
    # data/trial_ledger.jsonl (a domain forward ledger outside data/research_factory/).
    # The n=1 placeholder is inert (floor semantics) but persists into the audited
    # ledger.  Re-declare with the real budget at screening (W3) before running trials.
    if declare_family and not dry_run:
        from engine.trial_ledger import TrialLedger
        errs = __import__("engine.research_factory.schema", fromlist=["validate_rf_family"]).validate_rf_family(
            declare_family, trial_led_path
        )
        if errs:
            raise ValueError(
                f"--declare-family {declare_family!r} failed validation: {errs}"
            )
        tl = TrialLedger(path=trial_led_path, family=declare_family)
        tl.log_declared_budget(
            n=1,  # placeholder; re-declare with real budget at screening (W3)
            family=declare_family,
            reason="research_factory W2 ingest declaration (placeholder; re-declare at screening)",
        )
        print(
            f"  [OPERATOR] Declared rf.* family budget: {declare_family!r} "
            f"(n=1 placeholder written to {trial_led_path}; re-declare at W3 screening)",
            file=sys.stderr,
        )

    result = IngestResult()
    local_seen_rules: set[str] = set()  # within-batch dedup
    local_seen_hyps: set[str] = set()

    for raw_cand in proposals:
        # Ensure respin_of is set in lineage if requested, enforcing RF-15 gen cap.
        if respin_of:
            raw_cand = dict(raw_cand)
            lineage = dict(raw_cand.get("lineage") or {})
            lineage["respin_of"] = respin_of

            # RF-15: child generation = parent.refinement_generation + 1.
            # Resolve the parent from the factory ledger.
            #
            # FAIL-CLOSED rule: if the factory ledger exists (candidates.jsonl was
            # loaded) but the parent candidate_id is not found in it, the respin is
            # dropped with reason_code 'rf15_parent_not_found'.  We only allow the
            # gen-1 default when the ledger is provably absent/empty (genuine first-
            # generation respin where no ledger exists yet).
            #
            # This closes the anti-p-hacking rail: a researcher cannot silently
            # register a gen-3 respin as gen-1 by supplying a parent_id that doesn't
            # exist in the target rf_dir (fresh worktree, --rf-dir override, typo, or
            # uncommitted candidates.jsonl).
            ledger_exists = bool(existing_cands_by_id) or (
                out_dir / "candidates.jsonl"
            ).exists()
            if ledger_exists and respin_of not in existing_cands_by_id:
                cid_for_drop = raw_cand.get("candidate_id") or _make_candidate_id(
                    raw_cand.get("source", "unknown"), raw_cand.get("hypothesis", "")[:32]
                )
                raw_cand["candidate_id"] = cid_for_drop
                result.add_dropped(
                    raw_cand,
                    "rf15_parent_not_found",
                    f"respin_of={respin_of!r} not found in factory ledger; "
                    f"cannot compute generation — RF-15 fail-closed to prevent "
                    f"silent gen-1 registration of a higher-generation respin",
                )
                print(
                    f"  [DROP rf15_parent_not_found] {cid_for_drop}: "
                    f"parent {respin_of!r} absent from ledger (RF-15 fail-closed)",
                    file=sys.stderr,
                )
                continue

            parent_cand = existing_cands_by_id.get(respin_of, {})
            parent_gen = (parent_cand.get("lineage") or {}).get("refinement_generation", 0)
            child_gen = parent_gen + 1
            lineage["refinement_generation"] = child_gen
            raw_cand["lineage"] = lineage

            # RF-15: generation > 2 → terminal rejected (anti-p-hacking rail)
            if child_gen > 2:
                cid_for_drop = raw_cand.get("candidate_id") or _make_candidate_id(
                    raw_cand.get("source", "unknown"), raw_cand.get("hypothesis", "")[:32]
                )
                raw_cand["candidate_id"] = cid_for_drop
                result.add_dropped(
                    raw_cand,
                    "rf15_generation_cap",
                    f"respin of {respin_of!r} is generation {child_gen} (parent gen {parent_gen}); "
                    f"RF-15 cap is 2 — terminal rejected",
                )
                print(
                    f"  [DROP rf15_generation_cap] {cid_for_drop}: gen {child_gen} > 2 (RF-15)",
                    file=sys.stderr,
                )
                continue

        cand = raw_cand
        cid = cand.get("candidate_id") or _make_candidate_id(
            cand.get("source", "unknown"), cand.get("hypothesis", "")[:32]
        )
        cand["candidate_id"] = cid

        # --- Schema validation ---
        schema_errs = validate_candidate(cand)
        if schema_errs:
            result.add_dropped(
                cand,
                "schema_rejected",
                "schema validation failed: " + "; ".join(schema_errs),
            )
            print(f"  [DROP schema_rejected] {cid}: {schema_errs[:2]}", file=sys.stderr)
            continue

        # --- Within-batch dedup ---
        entry_rule = cand.get("artifacts", {}).get("entry_rule")
        batch_key_rule = _canonical(entry_rule) if isinstance(entry_rule, dict) else None
        batch_key_hyp = (cand.get("hypothesis") or "").lower().strip()[:120]

        if batch_key_rule and batch_key_rule in local_seen_rules:
            result.add_dropped(cand, "deduped", "duplicate entry_rule within ingest batch")
            continue
        if batch_key_hyp and batch_key_hyp in local_seen_hyps:
            result.add_dropped(cand, "deduped", "duplicate hypothesis within ingest batch")
            continue

        # --- RF-14 cross-registry dedup ---
        dup = _check_dedup(
            cand,
            oracle_canonical,
            species_names,
            machine_hyps,
            trial_families,
            existing_ids,
        )
        if dup:
            reason_text = f"matched in {dup.registry}: {dup.reason}"
            cand_deduped = dict(cand)
            cand_deduped["status"] = "deduped"
            trans = _build_transition(
                candidate_id=cid,
                from_state="proposed",
                to_state="deduped",
                reason_code="deduped_cross_registry",
                reason_text=reason_text,
                actor=actor,
                actor_ref=actor_ref,
                matched_registry=dup.registry,
                matched_entity_id=dup.matched_id,
            )
            # Validate the deduped transition through the state machine for
            # symmetry with the registered path; deduped has no mandatory fields
            # and no human-gate, so this is a no-op enforcement check today but
            # ensures future mandatory-field or actor rules on 'deduped' are
            # enforced rather than silently bypassed.
            try:
                state_transition(
                    from_state="proposed",
                    to_state="deduped",
                    actor=actor,
                    transition_row=trans,
                    candidate=cand_deduped,
                    ledger_path=trial_led_path,
                )
            except IllegalTransition as exc:
                result.add_dropped(cand, "transition_rejected", str(exc))
                print(f"  [DROP transition_rejected(deduped)] {cid}: {exc}", file=sys.stderr)
                continue
            result.add_dropped(cand, "deduped", reason_text)
            # Never write deduped rows to disk: the source-of-truth already
            # lives in the external registry (oracle, species, machine, trial)
            # or in the factory ledger itself. Writing would cause unbounded
            # row growth on every re-ingest because date-stamped candidate_ids
            # (from _make_candidate_id) change daily while the entry_rule stays
            # constant — so the factory_ledger step-0 guard misses, step-1
            # oracle_canonical fires, and without this guard a fresh row would
            # be appended for every run. This applies to ALL registry types,
            # including oracle_compounds_registry (the primary Oracle source).
            continue

        # --- Structural near-dup flag (RF-14/RF-7) ---
        flags = list(cand.get("flags") or [])
        is_near_dup, nd_score = _check_near_dup(cand, oracle_rules)
        if is_near_dup and "near_dup_review" not in flags:
            flags.append("near_dup_review")

        # --- Mechanism↔spec alignment flag (RF-7) ---
        mech = cand.get("mechanism") or ""
        if _mechanism_spec_mismatch(mech, entry_rule) and "mechanism_spec_mismatch" not in flags:
            flags.append("mechanism_spec_mismatch")

        cand = dict(cand)
        cand["flags"] = sorted(flags)

        # --- State transition: proposed → registered ---
        cand["status"] = "registered"
        trans_row: dict = {
            "artifact_refs": [],
        }
        trans = _build_transition(
            candidate_id=cid,
            from_state="proposed",
            to_state="registered",
            reason_code="ingest_registered",
            reason_text="candidate passed schema validation and cross-registry dedup",
            actor=actor,
            actor_ref=actor_ref,
            **trans_row,
        )

        # Validate transition
        try:
            state_transition(
                from_state="proposed",
                to_state="registered",
                actor=actor,
                transition_row=trans,
                candidate=cand,
                ledger_path=trial_led_path,
            )
        except IllegalTransition as exc:
            result.add_dropped(cand, "transition_rejected", str(exc))
            print(f"  [DROP transition_rejected] {cid}: {exc}", file=sys.stderr)
            continue

        # Mark within-batch seen
        if batch_key_rule:
            local_seen_rules.add(batch_key_rule)
        if batch_key_hyp:
            local_seen_hyps.add(batch_key_hyp)

        result.add_registered(cand, trans)

        if not dry_run:
            _write_candidate_and_transition(cand, trans, out_dir)

    return result


def _write_candidate_and_transition(cand: dict, trans: dict, out_dir: Path) -> None:
    """Append candidate and transition rows to their respective ledgers."""
    candidates_path = out_dir / "candidates.jsonl"
    transitions_path = out_dir / "transitions.jsonl"
    rf_ledger.append_row(candidates_path, cand, validate_fn=validate_candidate)
    rf_ledger.append_row(transitions_path, trans, validate_fn=validate_transition)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Source flags
    ap.add_argument("--manual", type=Path, default=None,
                    help="JSON file or dir of manual candidate proposals")
    ap.add_argument("--oracle-scratch", type=Path, default=None,
                    help="Dir containing oracle_ingest_brainstorm output (registry.jsonl)")
    ap.add_argument("--oracle-inbox", type=Path, default=None,
                    help="Original inbox dir for pre-strip mechanism capture (absent-safe)")
    ap.add_argument("--research-queue", action="store_true", default=False,
                    help="Ingest high_ev_build_now rows from research_queue.json")
    ap.add_argument("--nominate", nargs="*", default=[],
                    help="Nominate specific IDs from research_queue (any bin)")
    # Respin / actor
    ap.add_argument("--respin-of", default=None,
                    help="Candidate ID this ingest is a respin of (RF-15)")
    ap.add_argument("--actor", default="script",
                    choices=["script", "codex", "sonnet", "fable", "operator"],
                    help="Actor class for transitions (RF-5)")
    ap.add_argument("--actor-ref", default=None,
                    help="Session/PR ref (required for human actors)")
    # Trial accounting
    ap.add_argument("--declare-family", default=None,
                    help="rf.* family name to declare budget before ingesting (RF-6)")
    # I/O overrides
    ap.add_argument("--rf-dir", type=Path, default=None,
                    help="Override data/research_factory/ output dir")
    ap.add_argument("--oracle-registry", type=Path, default=None,
                    help="Override data/oracle/compounds/registry.jsonl")
    ap.add_argument("--species-registry", type=Path, default=None,
                    help="Override data/species/registry.json")
    ap.add_argument("--machine-registry", type=Path, default=None,
                    help="Override data/neuralweb/machine_registry.jsonl")
    ap.add_argument("--trial-ledger", type=Path, default=None,
                    help="Override data/trial_ledger.jsonl")
    ap.add_argument("--research-queue-path", type=Path, default=None,
                    help="Override data/neuralweb/research_queue.json")
    # Dry-run control (forward-ledger law RF-8: manual default is --dry-run)
    ap.add_argument("--write", action="store_true", default=False,
                    help="Write to disk (default: dry-run only)")
    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()

    dry_run = not args.write

    if not any([args.manual, args.oracle_scratch, args.research_queue, args.nominate]):
        ap.print_help()
        print("\n[ERROR] At least one source flag is required.", file=sys.stderr)
        return 1

    proposals: list[dict] = []

    # Source (a): manual
    if args.manual:
        raw_proposals = _load_manual_proposals(args.manual)
        print(f"Manual: loaded {len(raw_proposals)} proposals from {args.manual}")
        for p in raw_proposals:
            proposals.append(_ingest_manual(p, respin_of=args.respin_of,
                                            actor=args.actor, actor_ref=args.actor_ref))

    # Source (b): oracle scratch
    if args.oracle_scratch:
        inbox_mechanisms: dict[str, str] = {}
        if args.oracle_inbox:
            inbox_mechanisms = _capture_inbox_mechanisms(args.oracle_inbox)
            print(f"Oracle-inbox: captured {len(inbox_mechanisms)} mechanism entries from {args.oracle_inbox}")
        oracle_cands = _ingest_oracle_scratch(args.oracle_scratch, inbox_mechanisms)
        print(f"Oracle-scratch: loaded {len(oracle_cands)} candidates from {args.oracle_scratch}")
        # Apply respin_of lineage if set
        for c in oracle_cands:
            if args.respin_of:
                lin = dict(c.get("lineage") or {})
                lin["respin_of"] = args.respin_of
                lin["refinement_generation"] = max(1, lin.get("refinement_generation", 1))
                c["lineage"] = lin
        proposals.extend(oracle_cands)

    # Source (c): research_queue
    if args.research_queue or args.nominate:
        rq_path = args.research_queue_path or DEFAULT_RESEARCH_QUEUE
        rq_rows = _load_research_queue(rq_path, args.nominate or [])
        print(f"Research-queue: loaded {len(rq_rows)} rows from {rq_path}")
        for row in rq_rows:
            proposals.append(_ingest_research_queue_row(row))

    if not proposals:
        print("[INFO] No proposals to ingest.", file=sys.stderr)
        return 0

    print(f"\nTotal proposals to process: {len(proposals)}")
    print(f"Mode: {'DRY-RUN (use --write to commit)' if dry_run else 'WRITE'}")

    # Load existing candidate IDs from disk for within-factory dedup
    out_dir = args.rf_dir or DEFAULT_RF_DIR
    existing_ids: set[str] = set()
    existing_cands = rf_ledger.load_jsonl(out_dir / "candidates.jsonl")
    for ec in existing_cands:
        cid = ec.get("candidate_id")
        if cid:
            existing_ids.add(cid)
    if existing_ids:
        print(f"Factory ledger: {len(existing_ids)} existing candidates loaded for dedup")

    try:
        result = run_ingest(
            proposals,
            oracle_registry_path=args.oracle_registry,
            species_registry_path=args.species_registry,
            machine_registry_path=args.machine_registry,
            trial_ledger_path=args.trial_ledger,
            existing_candidate_ids=existing_ids,
            respin_of=args.respin_of,
            actor=args.actor,
            actor_ref=args.actor_ref,
            declare_family=args.declare_family,
            rf_dir=out_dir,
            dry_run=dry_run,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    result.print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
