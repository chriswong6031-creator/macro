"""engine.neuralweb.entity_thesis_mechanism_registry — Entity/Thesis/Mechanism crosswalk.

Schema: neuralweb.entity_thesis_mechanism.v1

DISPLAY-ONLY conceptual crosswalk joining existing local ID systems.  No authority
to gate, rank, score, size, originate signals, or promote candidates.  Every
cross-reference carries source provenance from a real field in a real file.

Rulings:
  ETM-R1 — display_only strictly; claim_cluster type reserved, never emitted.
  ETM-R2 — mechanism IDs minted only from ID-like spec_ref fields (not from prose).
  ETM-R3 — curated thesis rows require source_refs + curated_by; rows missing either
            are skipped and a conflict is recorded.
  ETM-R4 — entity rows emitted only for tickers referenced by thesis rows; never
            enumerates the full funnel parquet.
  ETM-R5 — no invented links; every edge source.path is a real input file.
  ETM-R6 — spec_ref containing characters outside [A-Za-z0-9_-] cannot form a
            mechanism: ID; such candidates get rf: rows instead.
  ETM-R7 — deterministic output; generated_utc is the only nondeterministic field.
  ETM-R8 — graceful degradation; every loader tolerates missing/empty/malformed input.

Handoff reference: research/fable_exit/05_ENTITY_THESIS_MECHANISM_REGISTRY_HANDOFF.md
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / authority constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.entity_thesis_mechanism.v1"

AUTHORITY_BLOCK: dict[str, Any] = {
    "role": "display_only",
    "can_gate": False,
    "can_rank": False,
    "can_size": False,
    "allowed_actions": ["display", "explain", "dedup_context"],
    "forbidden_actions": ["score", "size", "originate", "gate", "rank", "promote"],
}

# ---------------------------------------------------------------------------
# Namespace regex constants (imported by Wave B2 check script)
# ---------------------------------------------------------------------------

NAMESPACE_PATTERNS: dict[str, re.Pattern] = {
    "entity":   re.compile(r"^entity:(US|CN|HK|CA|INTL):[A-Z0-9.\-]+$"),
    "thesis":   re.compile(r"^thesis:[a-z0-9_\-]+$"),
    "mechanism": re.compile(r"^mechanism:[A-Za-z0-9_\-]+$"),
    "species":  re.compile(r"^species:[A-Za-z0-9_\-]+@[0-9][0-9.]*$"),
    "rf":       re.compile(r"^rf:rf-[0-9]{8}-[a-z_]+-[a-z0-9_]+$"),
    "gov":      re.compile(r"^gov:[0-9a-f]{16}$"),
    "claim":    re.compile(r"^claim:[0-9a-f]{16}$"),
}

REGISTRY_TYPES = frozenset(
    ["entity", "thesis", "mechanism", "species_link", "claim_cluster"]
)
# claim_cluster is reserved — the builder never emits it.
_RESERVED_TYPES = frozenset(["claim_cluster"])

# Mechanism spec_ref: only [A-Za-z0-9_-] chars allowed
_MECHANISM_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")

# PR extraction: #NNN..#NNNNN
_PR_RE = re.compile(r"#(\d{3,5})")

# Token normalizer for possible_duplicates / lookup
_TOKENIZE_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(["the", "and", "for", "with", "node", "2node"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(p: Path) -> tuple[Any, bool]:
    """Return (parsed, present).  present=False when file is absent or unreadable."""
    if not p.exists():
        return None, False
    try:
        return json.loads(p.read_text(encoding="utf-8")), True
    except Exception as exc:  # noqa: BLE001
        log.warning("etm_registry: unreadable %s — %s", p, exc)
        return None, True  # present but malformed → present=True, n=0


def _read_jsonl(p: Path) -> tuple[list[dict], bool]:
    """Return (rows, present).  Tolerates trailing whitespace and blank lines."""
    if not p.exists():
        return [], False
    rows: list[dict] = []
    try:
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("etm_registry: unreadable %s — %s", p, exc)
        return [], True  # present but malformed
    return rows, True


def _ticker_market(ticker: str) -> str:
    """Infer market from ticker suffix; returns US/CN/HK/CA/INTL."""
    t = ticker.upper()
    if "." not in t:
        return "US"
    suffix = t.rsplit(".", 1)[1]
    if suffix in ("SS", "SZ", "BJ"):
        return "CN"
    if suffix == "HK":
        return "HK"
    if suffix in ("TO", "V"):
        return "CA"
    return "INTL"


def _entity_id(ticker: str) -> str:
    return f"entity:{_ticker_market(ticker)}:{ticker.upper()}"


def _thesis_slug(label: str) -> str:
    """Deterministic slug: lowercase, spaces→_, strip non [a-z0-9_-]."""
    s = label.lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s


def _tokenize(text: str) -> set[str]:
    tokens = _TOKENIZE_RE.split(text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _extract_prs(text: str, path: str, field: str) -> list[dict]:
    return [
        {"pr": int(m), "extracted_from": f"{path}:{field}"}
        for m in _PR_RE.findall(str(text))
    ]


def _max_ts(*timestamps: str | None) -> str | None:
    """Return the lexicographically largest non-None timestamp."""
    valid = [t for t in timestamps if t]
    return max(valid) if valid else None


# ---------------------------------------------------------------------------
# Source loaders
# ---------------------------------------------------------------------------

def _load_species(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "data" / "species" / "registry.json"
    raw, present = _read_json(path)
    rows = (raw or {}).get("species", []) if present else []
    return rows, {"present": present, "n": len(rows)}


def _load_candidates(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "data" / "research_factory" / "candidates.jsonl"
    rows, present = _read_jsonl(path)
    return rows, {"present": present, "n": len(rows)}


def _load_transitions(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "data" / "research_factory" / "transitions.jsonl"
    rows, present = _read_jsonl(path)
    return rows, {"present": present, "n": len(rows)}


def _load_trial_ledger(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "data" / "trial_ledger.jsonl"
    rows, present = _read_jsonl(path)
    return rows, {"present": present, "n": len(rows)}


def _load_governance(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "data" / "neuralweb" / "governance.jsonl"
    rows, present = _read_jsonl(path)
    return rows, {"present": present, "n": len(rows)}


def _load_claim_accountability(repo: Path) -> tuple[dict, dict]:
    path = repo / "data" / "governance" / "claim_accountability.json"
    raw, present = _read_json(path)
    if not present or raw is None:
        return {}, {"present": present, "n": 0}
    context = {
        "global": raw.get("global"),
        "by_family": raw.get("by_family"),
    }
    return context, {"present": present, "n": 1}


def _load_reflexivity(repo: Path) -> tuple[list[dict], dict]:
    path = repo / "site" / "factordata" / "reflexivity_overlay.json"
    raw, present = _read_json(path)
    groups = (raw or {}).get("same_thesis_groups", []) if present else []
    return groups, {"present": present, "n": len(groups)}


def _load_funnel(repo: Path) -> tuple[dict[str, dict], dict]:
    """Returns ticker→{state, as_of} dict.  Tolerates missing pandas/parquet."""
    path = repo / "data" / "research" / "thesis_funnel_states.parquet"
    if not path.exists():
        return {}, {"present": False, "n": 0}
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(str(path))
        result = {
            row["ticker"]: {"state": row.get("state"), "as_of": row.get("as_of")}
            for _, row in df.iterrows()
        }
        return result, {"present": True, "n": len(df)}
    except Exception as exc:  # noqa: BLE001
        log.warning("etm_registry: funnel parquet unreadable — %s", exc)
        return {}, {"present": True, "n": 0}


def _load_experiments(repo: Path) -> tuple[dict[str, dict], dict]:
    """Returns {experiment_id: row} dict."""
    path = repo / "data" / "experiments" / "registry_seed.json"
    raw, present = _read_json(path)
    exps = (raw or {}).get("experiments", []) if present else []
    return {e["id"]: e for e in exps if "id" in e}, {"present": present, "n": len(exps)}


def _load_config(repo: Path) -> tuple[dict, dict]:
    """Load config/entity_thesis_mechanism_registry.yml.  Returns (parsed, status)."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return {}, {"present": False, "n": 0}
    path = repo / "config" / "entity_thesis_mechanism_registry.yml"
    if not path.exists():
        return {}, {"present": False, "n": 0}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return raw, {"present": True, "n": 1}
    except Exception as exc:  # noqa: BLE001
        log.warning("etm_registry: config yml unreadable — %s", exc)
        return {}, {"present": True, "n": 0}


# ---------------------------------------------------------------------------
# trial_families builder
# ---------------------------------------------------------------------------

def _build_trial_families(ledger_rows: list[dict]) -> dict[str, dict]:
    families: dict[str, dict] = defaultdict(lambda: {
        "n_trials": 0, "n_config_hashes": set(), "first_ts": None, "last_ts": None
    })
    for row in ledger_rows:
        fam = row.get("family")
        if not fam:
            continue
        d = families[fam]
        d["n_trials"] += 1
        h = row.get("config_hash")
        if h:
            d["n_config_hashes"].add(h)
        ts = row.get("ts")
        if ts:
            d["first_ts"] = _max_ts(d["first_ts"], ts) if d["first_ts"] else ts
            # track both min and max
    # Second pass to get proper first/last
    ts_by_family: dict[str, list[str]] = defaultdict(list)
    for row in ledger_rows:
        fam = row.get("family")
        ts = row.get("ts")
        if fam and ts:
            ts_by_family[fam].append(ts)
    result = {}
    for fam, d in families.items():
        tss = sorted(ts_by_family[fam])
        result[fam] = {
            "n_trials": d["n_trials"],
            "n_config_hashes": len(d["n_config_hashes"]),
            "first_ts": tss[0] if tss else None,
            "last_ts": tss[-1] if tss else None,
        }
    return dict(sorted(result.items()))


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _build_species_links(
    species_rows: list[dict],
    experiments: dict[str, dict],
    conflicts: list[dict],
) -> tuple[dict[str, dict], list[dict]]:
    """Build species_link rows.  Returns (rows_dict, edges)."""
    rows: dict[str, dict] = {}
    edges: list[dict] = []
    seen: dict[str, str] = {}  # species_id@version → registry_id, for conflict detection

    for sp in species_rows:
        sid = sp.get("species_id", "")
        ver = sp.get("version", "1.0")
        rid = f"species:{sid}@{ver}"

        if rid in seen:
            conflicts.append({
                "kind": "duplicate_species_id_version",
                "detail": f"duplicate {rid}",
                "source_paths": ["data/species/registry.json"],
            })
            continue
        seen[rid] = rid

        # experiment mirror: species-<species_id> convention
        exp_key = f"species-{sid}"
        exp_ref = experiments.get(exp_key)
        exp_id = exp_ref["id"] if exp_ref else None

        row: dict[str, Any] = {
            "registry_id": rid,
            "registry_type": "species_link",
            "authority": "display_only",
            "source_paths": ["data/species/registry.json"],
            "species_id": sid,
            "version": ver,
            "name": sp.get("name"),
            "validation_status": sp.get("validation_status"),
            "deployment_status": sp.get("deployment_status"),
            "mechanism": sp.get("mechanism"),  # verbatim prose — never minted to ID
            "horizon_class": sp.get("horizon_class"),
            "market_scope": sp.get("market_scope"),
            "evidence_stack": sp.get("evidence_stack"),
            "rejection_rules": sp.get("rejection_rules"),
            "trial_count": sp.get("trial_count"),
            "experiment_ref": exp_id,
            "source_prs": [],
            "governance_refs": [],
        }

        # PR extraction from evidence_stack (items are dicts, not strings — scan all str vals)
        ev_stack = sp.get("evidence_stack") or []
        for item in ev_stack if isinstance(ev_stack, list) else [ev_stack]:
            for prs in [_extract_prs(str(v), "data/species/registry.json", "evidence_stack")
                        for v in (item.values() if isinstance(item, dict) else [item])]:
                row["source_prs"].extend(prs)

        rows[rid] = row

        if exp_id:
            edges.append({
                "src": rid,
                "dst": exp_id,
                "kind": "mirrored_experiment",
                "source": {
                    "path": "data/experiments/registry_seed.json",
                    "detail": f"id == 'species-{sid}'",
                },
            })

    return rows, edges


def _build_mechanism_rows(
    candidates: list[dict],
    transitions: list[dict],
    trial_families: dict[str, dict],
    conflicts: list[dict],
) -> tuple[dict[str, dict], list[dict]]:
    """Build mechanism and rf rows.  Returns (rows_dict, edges)."""
    rows: dict[str, dict] = {}
    edges: list[dict] = []

    # Build latest-state per candidate from transitions
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for t in transitions:
        cid = t.get("candidate_id")
        if cid:
            by_cid[cid].append(t)

    def _latest_state(cid: str) -> str | None:
        txns = by_cid.get(cid, [])
        if not txns:
            return None
        return sorted(txns, key=lambda x: (x.get("as_of", ""), transitions.index(x)))[-1].get("to")

    def _state_history(cid: str) -> list[dict]:
        txns = sorted(by_cid.get(cid, []), key=lambda x: x.get("as_of", ""))
        return [
            {
                "candidate_id": t.get("candidate_id"),
                "from": t.get("from"),
                "to": t.get("to"),
                "as_of": t.get("as_of"),
            }
            for t in txns
        ]

    # Group candidates by spec_ref
    by_spec: dict[str, list[dict]] = defaultdict(list)
    no_spec: list[dict] = []

    for c in candidates:
        spec_ref = c.get("spec_ref")
        if spec_ref:
            by_spec[spec_ref].append(c)
        else:
            no_spec.append(c)

    # Conflict: same spec_ref across different domains
    for spec_ref, cands in by_spec.items():
        domains = list({c.get("domain") for c in cands if c.get("domain")})
        if len(domains) > 1:
            conflicts.append({
                "kind": "spec_ref_multi_domain",
                "detail": f"spec_ref {spec_ref!r} shared across domains {domains}",
                "source_paths": ["data/research_factory/candidates.jsonl"],
            })

    # Build mechanism rows (one per spec_ref when spec_ref is mechanism-safe)
    for spec_ref, cands in sorted(by_spec.items()):
        if not _MECHANISM_SAFE.match(spec_ref):
            # ETM-R6: spec_ref has illegal chars → treat as no-spec_ref candidates
            for c in cands:
                no_spec.append(c)
            continue

        rid = f"mechanism:{spec_ref}"
        cand_ids = sorted(c["candidate_id"] for c in cands)
        domains = sorted({c.get("domain") for c in cands if c.get("domain")})
        # hypothesis from first candidate by sorted candidate_id
        first_cand = min(cands, key=lambda c: c["candidate_id"])

        row: dict[str, Any] = {
            "registry_id": rid,
            "registry_type": "mechanism",
            "authority": "display_only",
            "source_paths": ["data/research_factory/candidates.jsonl"],
            "spec_ref": spec_ref,
            "candidate_ids": cand_ids,
            "domain": domains,
            "hypothesis": first_cand.get("hypothesis"),
            "current_rf_state": {cid: _latest_state(cid) for cid in cand_ids},
            "state_history": {cid: _state_history(cid) for cid in cand_ids},
            "trial_accounting": {
                cid: c.get("trial_accounting") for cid, c in zip(
                    sorted(c["candidate_id"] for c in cands),
                    sorted(cands, key=lambda c: c["candidate_id"])
                )
            },
            "source_prs": [],
            "governance_refs": [],
        }

        # PR extraction from reason_text / note in transitions
        for cid in cand_ids:
            for t in by_cid.get(cid, []):
                row["source_prs"].extend(
                    _extract_prs(t.get("reason_text", ""),
                                 "data/research_factory/transitions.jsonl", "reason_text")
                )
                row["source_prs"].extend(
                    _extract_prs(t.get("note", "") or "",
                                 "data/research_factory/transitions.jsonl", "note")
                )

        rows[rid] = row

        # Edges: rf candidates → mechanism
        for cid in cand_ids:
            edges.append({
                "src": f"rf:{cid}",
                "dst": rid,
                "kind": "rf_candidate_of_mechanism",
                "source": {
                    "path": "data/research_factory/candidates.jsonl",
                    "detail": f"candidate_id == '{cid}' with spec_ref == '{spec_ref}'",
                },
            })

        # Edges: mechanism → trial_family (only exact match)
        for cid in cand_ids:
            ta = next((c.get("trial_accounting") for c in cands if c["candidate_id"] == cid), {})
            fam = (ta or {}).get("family")
            if fam and fam in trial_families:
                edges.append({
                    "src": rid,
                    "dst": fam,
                    "kind": "trial_family_of",
                    "source": {
                        "path": "data/research_factory/candidates.jsonl",
                        "detail": f"trial_accounting.family == '{fam}' for candidate {cid}",
                    },
                })

    # Build rf rows for no-spec_ref candidates (incl. ETM-R6 rejects)
    for c in no_spec:
        cid = c.get("candidate_id", "")
        rid = f"rf:{cid}"

        row = {
            "registry_id": rid,
            "registry_type": "mechanism",
            "authority": "display_only",
            "source_paths": ["data/research_factory/candidates.jsonl"],
            "candidate_id": cid,
            "spec_ref": c.get("spec_ref"),  # may be set but unsafe
            "domain": c.get("domain"),
            "hypothesis": c.get("hypothesis"),
            "mechanism_prose": c.get("mechanism"),
            "current_rf_state": _latest_state(cid),
            "state_history": _state_history(cid),
            "trial_accounting": c.get("trial_accounting"),
            "source_prs": [],
            "governance_refs": [],
            "note": "no spec_ref; candidate-scoped" if not c.get("spec_ref")
                    else f"spec_ref '{c.get('spec_ref')}' contains non-ID chars (ETM-R6); candidate-scoped",
        }

        for t in by_cid.get(cid, []):
            row["source_prs"].extend(
                _extract_prs(t.get("reason_text", ""),
                             "data/research_factory/transitions.jsonl", "reason_text")
            )

        rows[rid] = row

    return rows, edges


def _build_thesis_rows(
    reflexivity_groups: list[dict],
    config: dict,
    conflicts: list[dict],
) -> tuple[dict[str, dict], list[dict], set[str]]:
    """Build thesis rows + entity refs.  Returns (rows, edges, referenced_tickers)."""
    rows: dict[str, dict] = {}
    edges: list[dict] = []
    referenced_tickers: set[str] = set()

    # (a) Reflexivity same_thesis_groups
    for group in reflexivity_groups:
        label = group.get("label", "")
        slug = _thesis_slug(label)
        # F3: skip unsluggable labels (e.g. CN-only unicode labels)
        if not slug:
            conflicts.append({
                "kind": "unsluggable_thesis_label",
                "detail": label,
                "source_paths": ["site/factordata/reflexivity_overlay.json"],
            })
            continue
        rid = f"thesis:{slug}"
        members = group.get("members", [])
        if rid in rows:
            # F2: slug collision — UNION members deterministically; record conflict
            existing = rows[rid]
            existing_label = existing.get("label", "")
            if existing.get("source") == "reflexivity_overlay.same_thesis_groups":
                # Both are reflexivity rows — union members, keep both labels
                unioned_members = sorted(set(existing.get("members", [])) | set(members))
                conflicts.append({
                    "kind": "thesis_slug_collision",
                    "detail": f"{existing_label!r}|{label!r} -> {rid}",
                    "source_paths": ["site/factordata/reflexivity_overlay.json"],
                })
                existing["members"] = unioned_members
                # Keep existing label (first-sorted label for back-compat), record both
                all_labels = sorted({existing_label, label})
                existing["label"] = all_labels[0]
                existing["labels"] = all_labels
                # Emit edges for newly added members only
                for ticker in members:
                    referenced_tickers.add(ticker)
                    if ticker not in set(existing.get("members", [])):
                        edges.append({
                            "src": _entity_id(ticker),
                            "dst": rid,
                            "kind": "member_of_thesis",
                            "source": {
                                "path": "site/factordata/reflexivity_overlay.json",
                                "detail": "same_thesis_groups.members",
                            },
                        })
            else:
                # Curated row already exists for this slug — curated wins (ETM-R3)
                conflicts.append({
                    "kind": "thesis_slug_collision",
                    "detail": f"{existing_label!r}|{label!r} -> {rid}",
                    "source_paths": ["site/factordata/reflexivity_overlay.json"],
                })
                # Still register referenced tickers + emit edges
                for ticker in members:
                    referenced_tickers.add(ticker)
                    edges.append({
                        "src": _entity_id(ticker),
                        "dst": rid,
                        "kind": "member_of_thesis",
                        "source": {
                            "path": "site/factordata/reflexivity_overlay.json",
                            "detail": "same_thesis_groups.members",
                        },
                    })
        else:
            row = {
                "registry_id": rid,
                "registry_type": "thesis",
                "authority": "display_only",
                "source_paths": ["site/factordata/reflexivity_overlay.json"],
                "label": label,
                "members": sorted(members),
                "size": group.get("size"),
                "basis": group.get("basis"),
                "source": "reflexivity_overlay.same_thesis_groups",
            }
            rows[rid] = row
            for ticker in members:
                referenced_tickers.add(ticker)
                edges.append({
                    "src": _entity_id(ticker),
                    "dst": rid,
                    "kind": "member_of_thesis",
                    "source": {
                        "path": "site/factordata/reflexivity_overlay.json",
                        "detail": "same_thesis_groups.members",
                    },
                })

    # (b) Curated rows from config yml
    curated = config.get("curated_theses", []) or []
    for entry in curated:
        label = entry.get("label", "")
        slug = _thesis_slug(label)
        # F3: skip unsluggable labels
        if not slug:
            conflicts.append({
                "kind": "unsluggable_thesis_label",
                "detail": label,
                "source_paths": ["config/entity_thesis_mechanism_registry.yml"],
            })
            continue
        rid = f"thesis:{slug}"
        # ETM-R3 enforcement: source_refs + curated_by required
        if not entry.get("source_refs") or not entry.get("curated_by"):
            conflicts.append({
                "kind": "curated_thesis_missing_provenance",
                "detail": (
                    f"curated thesis '{label}' missing "
                    f"{'source_refs' if not entry.get('source_refs') else 'curated_by'}; "
                    f"row skipped (ETM-R3)"
                ),
                "source_paths": ["config/entity_thesis_mechanism_registry.yml"],
            })
            continue
        row = {
            "registry_id": rid,
            "registry_type": "thesis",
            "authority": "display_only",
            "source_paths": ["config/entity_thesis_mechanism_registry.yml"],
            "label": label,
            "thesis_family": entry.get("thesis_family"),
            "tickers": sorted(entry.get("tickers", [])),
            "curated_by": entry.get("curated_by"),
            "state": entry.get("state"),
            "source_refs": entry.get("source_refs"),
        }
        if rid in rows:
            # Merge source_paths if reflexivity already created this slug
            existing = rows[rid]
            existing["source_paths"] = sorted(
                set(existing["source_paths"] + ["config/entity_thesis_mechanism_registry.yml"])
            )
            existing["curated_by"] = entry.get("curated_by")
            existing["state"] = entry.get("state")
            existing["source_refs"] = entry.get("source_refs")
        else:
            rows[rid] = row
        for ticker in entry.get("tickers", []):
            referenced_tickers.add(ticker)
            edges.append({
                "src": _entity_id(ticker),
                "dst": rid,
                "kind": "member_of_thesis",
                "source": {
                    "path": "config/entity_thesis_mechanism_registry.yml",
                    "detail": "curated_theses[].tickers",
                },
            })

    return rows, edges, referenced_tickers


def _build_entity_rows(
    referenced_tickers: set[str],
    funnel: dict[str, dict],
    thesis_rows: dict[str, dict],
    conflicts: list[dict],
) -> tuple[dict[str, dict], list[dict]]:
    """Build entity rows only for referenced tickers (ETM-R4)."""
    rows: dict[str, dict] = {}
    edges: list[dict] = []
    seen_ids: dict[str, str] = {}  # registry_id → ticker

    # Gather back-refs: entity → list of thesis_ids
    entity_thesis_map: dict[str, list[str]] = defaultdict(list)
    for tid, trow in thesis_rows.items():
        for ticker in trow.get("members", []) + trow.get("tickers", []):
            entity_thesis_map[_entity_id(ticker)].append(tid)

    for ticker in sorted(referenced_tickers):
        eid = _entity_id(ticker)
        if eid in seen_ids:
            conflicts.append({
                "kind": "entity_id_collision",
                "detail": f"{eid} would be duplicated by tickers {seen_ids[eid]} and {ticker}",
                "source_paths": ["site/factordata/reflexivity_overlay.json",
                                  "config/entity_thesis_mechanism_registry.yml"],
            })
            continue
        seen_ids[eid] = ticker
        market = _ticker_market(ticker)
        funnel_info = funnel.get(ticker, {})
        row = {
            "registry_id": eid,
            "registry_type": "entity",
            "authority": "display_only",
            "source_paths": [],  # populated from thesis source_paths
            "ticker": ticker,
            "market": market,
            "funnel_state": funnel_info.get("state"),
            "funnel_as_of": funnel_info.get("as_of"),
            "thesis_ids": sorted(set(entity_thesis_map.get(eid, []))),
        }
        rows[eid] = row

    return rows, edges


def _apply_governance_refs(
    rows: dict[str, dict],
    gov_events: list[dict],
    edges: list[dict],
) -> None:
    """Mutate rows in-place: attach governance_refs and add governed_by edges."""
    # Build lookup sets for matching
    candidate_ids = set()
    spec_refs = set()
    for rid, row in rows.items():
        if row["registry_type"] == "mechanism":
            if row.get("spec_ref"):
                spec_refs.add(row["spec_ref"])
            for cid in row.get("candidate_ids", []):
                candidate_ids.add(cid)
            if row.get("candidate_id"):
                candidate_ids.add(row["candidate_id"])

    for ev in gov_events:
        target = ev.get("target", "")
        event_id = ev.get("event_id", "")
        if not event_id:
            continue

        matched_rows: list[str] = []
        for cid in candidate_ids:
            if cid in target:
                # find the row that owns this candidate_id
                for rid, row in rows.items():
                    if row.get("candidate_id") == cid or cid in row.get("candidate_ids", []):
                        matched_rows.append(rid)
                        break
        for spec_ref in spec_refs:
            if spec_ref in target:
                mrid = f"mechanism:{spec_ref}"
                if mrid in rows and mrid not in matched_rows:
                    matched_rows.append(mrid)

        gov_id = f"gov:{event_id}"
        for rid in matched_rows:
            row = rows[rid]
            row.setdefault("governance_refs", []).append({
                "event_id": event_id,
                "event_type": ev.get("event_type"),
                "target": target,
                "ts": ev.get("ts"),
                "article": ev.get("article"),
            })
            edges.append({
                "src": rid,
                "dst": gov_id,
                "kind": "governed_by",
                "source": {
                    "path": "data/neuralweb/governance.jsonl",
                    "detail": f"event_id == '{event_id}' target contains candidate/spec_ref",
                },
            })


def _build_possible_duplicates(rows: dict[str, dict]) -> list[dict]:
    """Compare token sets across rows; emit suggestion pairs with ≥2 shared tokens."""
    # Collect token sets per row
    token_map: list[tuple[str, set[str]]] = []
    for rid, row in rows.items():
        tokens: set[str] = set()
        rtype = row.get("registry_type")
        if rtype == "species_link":
            tokens |= _tokenize(row.get("name", ""))
            tokens |= _tokenize(row.get("species_id", ""))
        elif rtype == "mechanism":
            if row.get("spec_ref"):
                tokens |= _tokenize(row["spec_ref"])
            if row.get("hypothesis"):
                tokens |= _tokenize(row["hypothesis"])
        elif rtype == "thesis":
            tokens |= _tokenize(row.get("label", ""))
        if tokens:
            token_map.append((rid, tokens))

    # Also include trial_families key tokens
    # (handled separately to avoid circular import — skip for row-level dedup)

    pairs: list[dict] = []
    seen: set[frozenset[str]] = set()
    for i in range(len(token_map)):
        for j in range(i + 1, len(token_map)):
            rid_a, tok_a = token_map[i]
            rid_b, tok_b = token_map[j]
            shared = tok_a & tok_b
            if len(shared) >= 2:
                key = frozenset([rid_a, rid_b])
                if key not in seen:
                    seen.add(key)
                    pairs.append({
                        "a": rid_a,
                        "b": rid_b,
                        "shared_tokens": sorted(shared),
                        "basis": "token_overlap_suggestion_only",
                        "suggestion_only": True,
                        "note": "suggestion only — not a merge",
                    })
    # Sort deterministically, cap at 200
    pairs.sort(key=lambda p: (p["a"], p["b"]))
    return pairs[:200]


def _dedup_edges(edges: list[dict]) -> list[dict]:
    """Deduplicate edges preserving first occurrence, then sort."""
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []
    for e in edges:
        key = (e.get("src", ""), e.get("dst", ""), e.get("kind", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return sorted(deduped, key=lambda e: (e.get("src", ""), e.get("dst", ""), e.get("kind", "")))


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(root: Path | None = None) -> dict:
    """Build the entity/thesis/mechanism registry artifact.

    Pure given the input files.  generated_utc is the only nondeterministic field.
    """
    repo = _repo_root(root)

    # ---- load all inputs ----
    species_rows, sp_status = _load_species(repo)
    candidates, cand_status = _load_candidates(repo)
    transitions, trans_status = _load_transitions(repo)
    ledger_rows, ledger_status = _load_trial_ledger(repo)
    gov_events, gov_status = _load_governance(repo)
    claim_ctx, claim_status = _load_claim_accountability(repo)
    reflex_groups, reflex_status = _load_reflexivity(repo)
    funnel, funnel_status = _load_funnel(repo)
    experiments, exp_status = _load_experiments(repo)
    config, cfg_status = _load_config(repo)

    sources = {
        "data/species/registry.json": sp_status,
        "data/research_factory/candidates.jsonl": cand_status,
        "data/research_factory/transitions.jsonl": trans_status,
        "data/trial_ledger.jsonl": ledger_status,
        "data/neuralweb/governance.jsonl": gov_status,
        "data/governance/claim_accountability.json": claim_status,
        "site/factordata/reflexivity_overlay.json": reflex_status,
        "data/research/thesis_funnel_states.parquet": funnel_status,
        "data/experiments/registry_seed.json": exp_status,
        "config/entity_thesis_mechanism_registry.yml": cfg_status,
    }

    # ---- trial families ----
    trial_families = _build_trial_families(ledger_rows)

    # ---- conflicts / possible_duplicates accumulators ----
    conflicts: list[dict] = []
    all_edges: list[dict] = []

    # ---- build rows ----
    species_link_rows, sp_edges = _build_species_links(species_rows, experiments, conflicts)
    all_edges.extend(sp_edges)

    mechanism_rows, mech_edges = _build_mechanism_rows(
        candidates, transitions, trial_families, conflicts
    )
    all_edges.extend(mech_edges)

    thesis_rows, thesis_edges, referenced_tickers = _build_thesis_rows(
        reflex_groups, config, conflicts
    )
    all_edges.extend(thesis_edges)

    entity_rows, _ = _build_entity_rows(
        referenced_tickers, funnel, thesis_rows, conflicts
    )

    # Merge all rows
    all_rows: dict[str, dict] = {}
    all_rows.update(species_link_rows)
    all_rows.update(mechanism_rows)
    all_rows.update(thesis_rows)
    all_rows.update(entity_rows)

    # ---- governance ----
    _apply_governance_refs(all_rows, gov_events, all_edges)

    # ---- finalize edges ----
    all_edges = _dedup_edges(all_edges)

    # ---- possible duplicates ----
    possible_duplicates = _build_possible_duplicates(all_rows)

    # ---- counts ----
    rows_by_type: dict[str, int] = defaultdict(int)
    for row in all_rows.values():
        rows_by_type[row["registry_type"]] += 1

    edges_by_kind: dict[str, int] = defaultdict(int)
    for e in all_edges:
        edges_by_kind[e.get("kind", "unknown")] += 1

    # ---- as_of: max ts seen across all inputs ----
    ts_candidates: list[str] = []
    for row in species_rows:
        pass  # no ts in species
    for t in transitions:
        if t.get("as_of"):
            ts_candidates.append(t["as_of"])
    for row in ledger_rows:
        if row.get("ts"):
            ts_candidates.append(row["ts"])
    for ev in gov_events:
        if ev.get("ts"):
            ts_candidates.append(ev["ts"])
    as_of_ts = max(ts_candidates) if ts_candidates else _now_utc()
    # Truncate to date for display
    as_of_date = as_of_ts[:10] if len(as_of_ts) >= 10 else as_of_ts

    artifact = {
        "schema": SCHEMA,
        "as_of": as_of_date,
        "generated_utc": _now_utc(),
        "is_context_only": True,
        "authority": AUTHORITY_BLOCK,
        "sources": dict(sorted(sources.items())),
        "counts": {
            "rows_by_type": dict(sorted(rows_by_type.items())),
            "edges_by_kind": dict(sorted(edges_by_kind.items())),
        },
        "rows": dict(sorted(all_rows.items())),
        "edges": all_edges,
        "trial_families": trial_families,
        "claim_context": claim_ctx,
        "possible_duplicates": possible_duplicates,
        "conflicts": sorted(conflicts, key=lambda c: (c.get("kind", ""), c.get("detail", ""))),
        "notes": (
            "Crosswalk only; local systems remain authoritative. "
            "No invented links; unknowns stay null."
        ),
    }

    return artifact


def build_and_write(root: Path | None = None) -> Path:
    """Build artifact and write to data/neuralweb/entity_thesis_mechanism_registry.json."""
    repo = _repo_root(root)
    artifact = build(root)
    out = repo / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------

def lookup(artifact: dict, query: str) -> dict:
    """Tokenized lookup against all rows.

    Returns matched rows sorted by registry_id with possible_duplicates touching.
    Purely descriptive — no scoring beyond match/no-match.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return {
            "query": query,
            "matches": [],
            "possible_duplicates_touching": [],
            "verdict_hint": "no prior rows matched",
        }

    rows: dict[str, dict] = artifact.get("rows", {})
    trial_families: dict[str, dict] = artifact.get("trial_families", {})
    possible_duplicates: list[dict] = artifact.get("possible_duplicates", [])

    matches: list[dict] = []
    matched_ids: set[str] = set()

    for rid, row in rows.items():
        matched_on: list[str] = []

        # Match registry_id tokens
        if query_tokens & _tokenize(rid):
            matched_on.append("registry_id")

        rtype = row.get("registry_type")
        if rtype == "species_link":
            if query_tokens & _tokenize(row.get("species_id", "")):
                matched_on.append("species_id")
            if query_tokens & _tokenize(row.get("name", "")):
                matched_on.append("species_name")
        elif rtype == "mechanism":
            if row.get("spec_ref") and query_tokens & _tokenize(row["spec_ref"]):
                matched_on.append("spec_ref")
            if row.get("hypothesis") and query_tokens & _tokenize(row["hypothesis"]):
                matched_on.append("hypothesis")
            if row.get("candidate_id") and query_tokens & _tokenize(row["candidate_id"]):
                matched_on.append("candidate_id")
        elif rtype == "thesis":
            if query_tokens & _tokenize(row.get("label", "")):
                matched_on.append("thesis_label")
        elif rtype == "entity":
            if query_tokens & _tokenize(row.get("ticker", "")):
                matched_on.append("ticker")

        if matched_on:
            matched_ids.add(rid)
            row_summary = {
                "id": rid,
                "registry_type": rtype,
                "matched_on": matched_on,
            }
            if rtype == "species_link":
                row_summary["validation_status"] = row.get("validation_status")
                row_summary["deployment_status"] = row.get("deployment_status")
                row_summary["source_prs"] = row.get("source_prs")
            elif rtype == "mechanism":
                row_summary["current_rf_state"] = row.get("current_rf_state")
                row_summary["spec_ref"] = row.get("spec_ref")
                row_summary["source_prs"] = row.get("source_prs")
                # trial families touching this mechanism
                ta_families = []
                for ta_info in (row.get("trial_accounting") or {}).values():
                    if isinstance(ta_info, dict):
                        f = ta_info.get("family")
                        if f and f in trial_families:
                            ta_families.append(f)
                row_summary["trial_families"] = ta_families or None
            elif rtype == "thesis":
                row_summary["state"] = row.get("state")
            elif rtype == "entity":
                row_summary["funnel_state"] = row.get("funnel_state")

            matches.append(row_summary)

    # Also match trial family names
    for fam_name in trial_families:
        if query_tokens & _tokenize(fam_name):
            matched_ids.add(fam_name)

    # Sort by registry_id
    matches.sort(key=lambda m: m["id"])

    # Possible duplicates touching matched rows
    dup_touching = [
        d for d in possible_duplicates
        if d.get("a") in matched_ids or d.get("b") in matched_ids
    ]

    verdict_hint = (
        "prior work exists — cite it" if matches
        else "no prior rows matched"
    )

    return {
        "query": query,
        "matches": matches,
        "possible_duplicates_touching": dup_touching,
        "verdict_hint": verdict_hint,
    }
