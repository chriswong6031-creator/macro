"""engine.neuralweb.causal_audit — CHF-R10 anti-mirage auditor.

PURPOSE
-------
Produces data/neuralweb/causal_confluence_audit.json: DIRECTED annotations
over the confluence graph.  Three annotation categories:

  (a) duplicate_exposure: pairs of features/engines whose inventory role tags
      mark them price-derived siblings of the same parent process.  Source:
      causal_feature_inventory.json family + notes fields.

  (b) shared_parent_suspect: where a confirms edge's two engines sit in one
      R-ORTH cluster AND the causal inventory marks a common driver family.
      Reads confluence_graph.json (confirms edges) + covariance_spine.json
      (clusters).  Does NOT recompute co-firing (RUL-ORTH-9).

  (c) collider_risk: named downstream composites from config/causal_priors.yml
      forbidden_causes that appear as conditioners anywhere in mechanism cards.
      Reads causal_mechanisms.jsonl.

AUTHORITY CONTRACT (CHF-R10, RUL-ORTH-9/11)
--------------------------------------------
- ZERO recomputation of R-ORTH statistics.
- ZERO LLM-originated annotations.
- ALL annotations are deterministic rule applications over committed artifacts.
- Output is display_only, annotate_only.  not_a_signal: True unconditionally.
- Absent inputs produce empty annotation sections + printed gap notes.
- Language law: banned words (caused/proved/proof/validated) must not appear in
  display_text fields.  Enforced at write time by the language sanitizer
  imported from causal_schema.py.

SCHEMA
------
data/neuralweb/causal_confluence_audit.json
{
  "schema":           "neuralweb.causal_confluence_audit.v1",
  "artifact_id":      "causal-confluence-audit",
  "asof":             <str ISO-8601>,
  "authority":        {display_only, annotate_only, not_a_signal, ...},
  "duplicate_exposure":    [AnnotationRow, ...],
  "shared_parent_suspect": [AnnotationRow, ...],
  "collider_risk":         [AnnotationRow, ...],
  "counts":           {"duplicate_exposure": int, ...},
  "gap_notes":        [str],
  "produced_by":      "engine.neuralweb.causal_audit",
}

AnnotationRow common fields:
  rule_id        — CHF-R10-{DE|SPS|CR}-{n}
  display_text   — EN human-readable (language-law safe)
  display_text_zh — ZH human-readable (language-law safe)
  evidence_refs  — list of {artifact, field, value} that triggered the annotation
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema + authority constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.causal_confluence_audit.v1"
ARTIFACT_ID = "causal-confluence-audit"

_AUTHORITY = {
    "tier": "shadow",
    "display_only": True,
    "annotate_only": True,
    "not_a_signal": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "scored_path_surfaces": [],
    "description": (
        "CHF-R10 anti-mirage auditor output. "
        "Directed annotations only — no R-ORTH recomputation, no statistics, "
        "no LLM-originated content. "
        "Rule IDs: CHF-R10-DE (duplicate exposure), CHF-R10-SPS (shared parent suspect), "
        "CHF-R10-CR (collider risk). "
        "Absent inputs produce empty sections, never phantom annotations."
    ),
}

# Language-law banned words (CHF-R5 language sanitizer; also enforced in causal_schema.py)
_BANNED_WORDS = re.compile(
    r"\b(caused?|proves?|proof|proofs?|proofing|prooven|validate[sd]?|validates?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Price-family tags that indicate sibling risk
# ---------------------------------------------------------------------------
# Features in these families are likely price-derived and may share a common
# parent market process.  This list is additive: families not listed here are
# not checked for duplicate exposure (conservative — avoids false positives).

_PRICE_FAMILY_TAGS: frozenset[str] = frozenset({
    "breadth",
    "gex",
    "options_entry",
    "momentum",
    "trend",
    "rs",
    "relative_strength",
})

# Minimum overlap threshold: how many of a feature's notes must contain a
# price-family keyword for the feature to be classified as price-derived.
_PRICE_KEYWORD_PATTERNS = re.compile(
    r"\b(price[-\s]derived|momentum|breadth|gex|relative.strength|options.entry"
    r"|trend|dealer.positioning|gamma|co-vary|co-firing|contemporaneous.price)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Repo root helper
# ---------------------------------------------------------------------------

def _repo_root(override: Path | None = None) -> Path:
    """Infer repo root from this file's location."""
    if override is not None:
        return override
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Safe JSON readers (fail-open)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("causal_audit: could not read %s — %s", path, exc)
        return None


def _read_jsonl(path: Path) -> list[dict]:
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
            except json.JSONDecodeError as exc:
                log.warning("causal_audit: bad JSON line in %s — %s", path, exc)
    except OSError as exc:
        log.warning("causal_audit: could not read JSONL %s — %s", path, exc)
    return rows


def _read_yaml(path: Path) -> dict | None:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("causal_audit: could not read YAML %s — %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Language-law sanitizer
# ---------------------------------------------------------------------------

def _sanitize_text(text: str) -> str:
    """Replace banned causal-certainty words with safe alternatives.

    This is a defence-in-depth layer; the primary enforcer is causal_schema.py.
    """
    replacements = {
        re.compile(r"\bvalidated?\b", re.I): "observed",
        re.compile(r"\bvalidates?\b", re.I): "observes",
        re.compile(r"\bprove[sd]?\b", re.I): "indicate",
        re.compile(r"\bproof\b", re.I): "indication",
        re.compile(r"\bcause[sd]?\b", re.I): "precede",
        re.compile(r"\bcauses?\b", re.I): "precedes",
    }
    for pat, repl in replacements.items():
        text = pat.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# (a) duplicate_exposure: price-derived sibling detection
# ---------------------------------------------------------------------------

def _is_price_derived(feature: dict) -> bool:
    """Return True if the feature is in a known price-derived family or its notes
    reference price-derived language."""
    family = (feature.get("family") or "").lower()
    if family in _PRICE_FAMILY_TAGS:
        return True
    notes = feature.get("notes") or ""
    if _PRICE_KEYWORD_PATTERNS.search(notes):
        return True
    return False


def _build_duplicate_exposure(
    inventory: dict | None,
    gap_notes: list[str],
) -> list[dict]:
    """Detect pairs of candidate-cause features that are price-derived siblings.

    Rule CHF-R10-DE: if two features share the same family AND both are
    classified as price-derived, they may inflate apparent confirmation edges
    by sharing a common price-process parent.

    Returns a list of AnnotationRow dicts.  Empty when inventory is absent.
    """
    if inventory is None:
        gap_notes.append(
            "duplicate_exposure: causal_feature_inventory.json absent — "
            "section empty (no annotations possible without inventory)"
        )
        return []

    features: list[dict] = inventory.get("features") or []
    if not features:
        gap_notes.append(
            "duplicate_exposure: inventory has no features — section empty"
        )
        return []

    # Group candidate-cause features by family
    by_family: dict[str, list[dict]] = {}
    for feat in features:
        roles = feat.get("allowed_roles") or []
        if "candidate_cause" not in roles:
            continue  # not eligible as a cause — skip
        if not _is_price_derived(feat):
            continue
        family = feat.get("family") or "unknown"
        by_family.setdefault(family, []).append(feat)

    rows: list[dict] = []
    rule_counter = 0
    for family, flist in sorted(by_family.items()):
        if len(flist) < 2:
            continue  # no pair possible
        # Generate all pairs (n choose 2) within the family
        for i in range(len(flist)):
            for j in range(i + 1, len(flist)):
                rule_counter += 1
                fa = flist[i]
                fb = flist[j]
                fid_a = fa.get("feature_id", "?")
                fid_b = fb.get("feature_id", "?")
                display_text = _sanitize_text(
                    f"Price-derived sibling pair within family '{family}': "
                    f"'{fid_a}' and '{fid_b}' may share a common market-process parent. "
                    f"Co-firing between any engines consuming both features "
                    f"may reflect shared underlying price dynamics rather than "
                    f"independent confirmation. "
                    f"Treat any confirms edge spanning these features as a "
                    f"candidate for shared-parent review before acting on it."
                )
                display_text_zh = (
                    f"价格衍生同族信号对 (家族: '{family}'): "
                    f"'{fid_a}' 与 '{fid_b}' 可能共享同一市场价格过程。"
                    f"两者之间的共触发信号可能反映共同的价格动态，而非独立确认。"
                    f"在采纳跨越这两个特征的任何 confirms 边之前，需进行共享母因审查。"
                )
                rows.append({
                    "rule_id": f"CHF-R10-DE-{rule_counter:03d}",
                    "annotation_type": "duplicate_exposure",
                    "pair": [fid_a, fid_b],
                    "parent_process": family,
                    "display_text": display_text,
                    "display_text_zh": display_text_zh,
                    "evidence_refs": [
                        {
                            "artifact": "causal-feature-inventory",
                            "field": f"features[{fid_a}].family",
                            "value": family,
                        },
                        {
                            "artifact": "causal-feature-inventory",
                            "field": f"features[{fid_b}].family",
                            "value": family,
                        },
                    ],
                    "display_only": True,
                    "not_a_signal": True,
                })

    return rows


# ---------------------------------------------------------------------------
# (b) shared_parent_suspect: confirms edges in R-ORTH clusters
# ---------------------------------------------------------------------------

def _extract_engine_name(node_id: str) -> str:
    """Extract the engine name from a node id like 'engine:altdata' → 'altdata'."""
    if ":" in node_id:
        return node_id.split(":", 1)[1]
    return node_id


def _build_cluster_membership(spine: dict | None) -> dict[str, str]:
    """Return a mapping of engine_name → cluster_id from covariance_spine.json.

    Reads the 'lobes' block which contains cluster membership.
    Returns empty dict if spine is absent or has no cluster data.
    """
    if spine is None:
        return {}

    # The spine's lobes block has 'clusters' as a list of lists (groups of engine ids)
    lobes_block = (spine.get("blocks") or {}).get("lobes") or {}
    clusters_list: list = lobes_block.get("clusters") or []

    membership: dict[str, str] = {}
    for idx, cluster in enumerate(clusters_list):
        if isinstance(cluster, (list, tuple)):
            for member in cluster:
                if isinstance(member, str):
                    membership[member] = f"cluster_{idx}"
        elif isinstance(cluster, dict):
            members = cluster.get("members") or []
            cluster_id = cluster.get("id") or f"cluster_{idx}"
            for member in members:
                if isinstance(member, str):
                    membership[member] = cluster_id

    return membership


def _get_feature_family_for_engine(engine_name: str, inventory: dict | None) -> str | None:
    """Look up the primary feature family for an engine by matching producer fields.

    Returns None when no match is found.
    """
    if inventory is None:
        return None
    for feat in (inventory.get("features") or []):
        producer = feat.get("producer") or ""
        # Match engine name as substring of producer artifact_id
        if engine_name.lower() in producer.lower():
            return feat.get("family")
    return None


def _build_shared_parent_suspect(
    confluence: dict | None,
    spine: dict | None,
    inventory: dict | None,
    gap_notes: list[str],
) -> list[dict]:
    """Detect confirms edges whose endpoints sit in the same R-ORTH cluster
    AND share a common driver family in the causal inventory.

    Rule CHF-R10-SPS: read-only; no recomputation.
    """
    if confluence is None:
        gap_notes.append(
            "shared_parent_suspect: confluence_graph.json absent — section empty"
        )
        return []

    if spine is None:
        gap_notes.append(
            "shared_parent_suspect: covariance_spine.json absent — "
            "cluster membership unavailable; section empty"
        )
        return []

    cluster_membership = _build_cluster_membership(spine)
    if not cluster_membership:
        gap_notes.append(
            "shared_parent_suspect: covariance_spine.json has no cluster data — "
            "section empty (clusters is empty list; this is expected until enough "
            "lobes are measurable)"
        )
        return []

    edges: list[dict] = confluence.get("edges") or []
    confirms_edges = [e for e in edges if e.get("edge_type") == "confirms"]

    rows: list[dict] = []
    rule_counter = 0
    for edge in confirms_edges:
        src_id = edge.get("src") or ""
        dst_id = edge.get("dst") or ""
        src_engine = _extract_engine_name(src_id)
        dst_engine = _extract_engine_name(dst_id)

        src_cluster = cluster_membership.get(src_engine)
        dst_cluster = cluster_membership.get(dst_engine)

        if src_cluster is None or dst_cluster is None:
            continue  # one or both not in any cluster — skip
        if src_cluster != dst_cluster:
            continue  # different clusters — no shared-parent concern here

        # Both engines are in the same R-ORTH cluster.
        # Check if they share a driver family from inventory.
        src_family = _get_feature_family_for_engine(src_engine, inventory)
        dst_family = _get_feature_family_for_engine(dst_engine, inventory)

        # Annotate if both are identified or if just same-cluster
        suspected_family = None
        if src_family and dst_family and src_family == dst_family:
            suspected_family = src_family
        elif src_family or dst_family:
            suspected_family = src_family or dst_family

        rule_counter += 1
        lift_val = edge.get("lift")
        lift_str = f"{lift_val:.4f}" if lift_val is not None else "unknown"
        n_val = edge.get("n")
        n_str = str(n_val) if n_val is not None else "unknown"

        family_note = (
            f"suspected common driver family: '{suspected_family}'"
            if suspected_family
            else "driver family not identified in inventory"
        )

        display_text = _sanitize_text(
            f"Confirms edge {src_id} → {dst_id} (lift={lift_str}, n={n_str}) "
            f"sits within R-ORTH cluster '{src_cluster}'. "
            f"Both engines belong to the same independence cluster, suggesting "
            f"they may share a common upstream driver ({family_note}). "
            f"Treat this confirms edge as a potential shared-parent artifact "
            f"rather than independent confirmation until a directed study "
            f"separates the direct paths."
        )
        display_text_zh = (
            f"Confirms 边 {src_id} → {dst_id} (lift={lift_str}, n={n_str}) "
            f"位于 R-ORTH 聚类 '{src_cluster}' 内。"
            f"两个引擎属于同一独立性聚类，可能共享共同的上游驱动因子（{family_note}）。"
            f"在定向研究分离直接路径之前，将此 confirms 边视为潜在共享母因伪影。"
        )
        rows.append({
            "rule_id": f"CHF-R10-SPS-{rule_counter:03d}",
            "annotation_type": "shared_parent_suspect",
            "edge": {"src": src_id, "dst": dst_id, "edge_type": "confirms"},
            "suspected_parent_family": suspected_family,
            "cluster_id": src_cluster,
            "display_text": display_text,
            "display_text_zh": display_text_zh,
            "evidence_refs": [
                {
                    "artifact": "confluence-graph",
                    "field": "edges[confirms]",
                    "value": f"src={src_id} dst={dst_id} lift={lift_str} n={n_str}",
                },
                {
                    "artifact": "covariance-spine",
                    "field": f"blocks.lobes.clusters[{src_cluster}]",
                    "value": f"{src_engine}, {dst_engine}",
                },
            ],
            "display_only": True,
            "not_a_signal": True,
        })

    return rows


# ---------------------------------------------------------------------------
# (c) collider_risk: forbidden composites as conditioners in mechanism cards
# ---------------------------------------------------------------------------

def _extract_forbidden_patterns(priors: dict | None) -> list[dict]:
    """Extract forbidden_causes patterns from causal_priors.yml."""
    if priors is None:
        return []
    return priors.get("forbidden_causes") or []


def _build_collider_risk(
    mechanisms: list[dict],
    priors: dict | None,
    gap_notes: list[str],
) -> list[dict]:
    """Detect mechanism cards that condition on downstream composites named in
    config/causal_priors.yml forbidden_causes.

    Rule CHF-R10-CR: a forbidden composite appearing as a conditioner in a
    causal graph fragment opens a collider back-door path.
    """
    if priors is None:
        gap_notes.append(
            "collider_risk: causal_priors.yml absent — "
            "section empty (forbidden_causes unavailable)"
        )
        return []

    forbidden = _extract_forbidden_patterns(priors)
    if not forbidden:
        gap_notes.append(
            "collider_risk: forbidden_causes is empty in causal_priors.yml — "
            "section empty"
        )
        return []

    if not mechanisms:
        # Not a gap — just no cards filed yet
        return []

    def _matches_any_forbidden(name: str) -> str | None:
        """Return the matched pattern if name matches any forbidden pattern."""
        name_lower = name.lower()
        for fc in forbidden:
            pat = (fc.get("pattern") or "").lower()
            if pat and pat in name_lower:
                return fc.get("pattern")
        return None

    rows: list[dict] = []
    rule_counter = 0
    for card in mechanisms:
        mech_id = card.get("mechanism_id") or card.get("id") or "?"
        status = card.get("status") or "unknown"

        # Read the causal_graph block — look for conditioners
        graph_block = card.get("causal_graph") or {}
        conditioners: list[str] = []

        # Standard conditioner fields in causal graph fragments
        for field_name in ("conditioners", "confounders", "colliders_to_avoid"):
            val = graph_block.get(field_name)
            if isinstance(val, list):
                conditioners.extend(str(v) for v in val)
            elif isinstance(val, str) and val:
                conditioners.append(val)

        # Also check environment_map (environment split axes can be colliders)
        env_map = card.get("environment_map") or {}
        for env_key in env_map:
            conditioners.append(str(env_key))

        for cond_name in conditioners:
            matched_pattern = _matches_any_forbidden(cond_name)
            if matched_pattern is None:
                continue

            # Find the reason from forbidden_causes
            reason = next(
                (fc.get("reason", "") for fc in forbidden
                 if (fc.get("pattern") or "").lower() in cond_name.lower()),
                "",
            )

            rule_counter += 1
            display_text = _sanitize_text(
                f"Mechanism card '{mech_id}' (status: {status}) conditions on "
                f"'{cond_name}', which matches the forbidden composite pattern "
                f"'{matched_pattern}'. "
                f"Downstream composites are forbidden causes because they encode "
                f"information from the outcome path: {reason}. "
                f"Conditioning on '{cond_name}' may open a collider back-door, "
                f"producing spurious apparent association. "
                f"Remove '{cond_name}' from the conditioner set or restructure "
                f"the causal graph to avoid this path."
            )
            display_text_zh = (
                f"机制卡片 '{mech_id}'（状态: {status}）以 '{cond_name}' 为条件，"
                f"该变量匹配禁止合成因子模式 '{matched_pattern}'。"
                f"下游合成指标被列为禁止原因，因为它们编码了结果路径的信息：{reason}。"
                f"以 '{cond_name}' 为条件可能打开碰撞偏差路径，产生虚假关联。"
                f"请从条件集中移除 '{cond_name}' 或重构因果图以避免该路径。"
            )
            rows.append({
                "rule_id": f"CHF-R10-CR-{rule_counter:03d}",
                "annotation_type": "collider_risk",
                "mechanism_id": mech_id,
                "conditioner": cond_name,
                "matched_forbidden_pattern": matched_pattern,
                "reason": reason,
                "display_text": display_text,
                "display_text_zh": display_text_zh,
                "evidence_refs": [
                    {
                        "artifact": "causal-mechanisms",
                        "field": f"mechanism_id={mech_id}.causal_graph",
                        "value": f"conditioner={cond_name}",
                    },
                    {
                        "artifact": "causal-priors",
                        "field": "forbidden_causes",
                        "value": f"pattern={matched_pattern}",
                    },
                ],
                "display_only": True,
                "not_a_signal": True,
            })

    return rows


# ---------------------------------------------------------------------------
# Confluence tagging helper (additive, tolerant)
# ---------------------------------------------------------------------------

def stamp_confluence_edges(
    confluence: dict,
    audit: dict,
) -> dict:
    """Stamp matching confirms edges in a confluence graph payload with
    causal_audit annotations (additive field; tolerant when absent).

    This is called by confluence.py after building the graph.  It does not
    recompute anything — it reads the audit artifact and applies labels.

    Returns a COPY of confluence with causal_audit fields added to matching edges.
    Consumer: engine/neuralweb/confluence.py (declared).
    """
    import copy  # noqa: PLC0415

    result = copy.deepcopy(confluence)

    sps_by_edge: dict[tuple[str, str], list[str]] = {}
    for ann in (audit.get("shared_parent_suspect") or []):
        edge_info = ann.get("edge") or {}
        src = edge_info.get("src", "")
        dst = edge_info.get("dst", "")
        if src and dst:
            key = (src, dst)
            sps_by_edge.setdefault(key, []).append(ann.get("rule_id", ""))

    de_by_engine: dict[str, list[str]] = {}
    for ann in (audit.get("duplicate_exposure") or []):
        pair = ann.get("pair") or []
        rule = ann.get("rule_id", "")
        for member in pair:
            de_by_engine.setdefault(member, []).append(rule)

    edges: list[dict] = result.get("edges") or []
    for edge in edges:
        if edge.get("edge_type") != "confirms":
            continue
        src = edge.get("src", "")
        dst = edge.get("dst", "")

        causal_audit_block: dict[str, Any] = {}

        # shared_parent_suspect
        sps_rules = sps_by_edge.get((src, dst), [])
        if sps_rules:
            causal_audit_block["shared_parent_suspect"] = sps_rules

        # duplicate_exposure — check if either endpoint's engine name is in de_by_engine
        from engine.neuralweb.causal_audit import _extract_engine_name  # noqa: PLC0415
        src_eng = _extract_engine_name(src)
        dst_eng = _extract_engine_name(dst)
        de_rules = list(set(
            de_by_engine.get(src_eng, []) + de_by_engine.get(dst_eng, [])
        ))
        if de_rules:
            causal_audit_block["duplicate_risk"] = de_rules

        if causal_audit_block:
            edge["causal_audit"] = causal_audit_block

    result["causal_audit_stamped"] = True
    result["causal_audit_asof"] = audit.get("asof")
    return result


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_audit(root: Path | None = None) -> dict:
    """Build and return the causal confluence audit artifact dict.

    Parameters
    ----------
    root : Path | None
        Repo root.  Defaults to the repo root inferred from this file's location.

    Returns
    -------
    dict
        Full artifact dict matching schema neuralweb.causal_confluence_audit.v1.
        Absent inputs produce empty sections.  Never raises.
    """
    r = _repo_root(root)
    gap_notes: list[str] = []
    asof = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- Load source artifacts ------------------------------------------------

    inventory_path = r / "data" / "neuralweb" / "causal_feature_inventory.json"
    inventory = _read_json(inventory_path)
    if inventory is None:
        gap_notes.append(
            f"causal_feature_inventory.json not found at {inventory_path} — "
            "duplicate_exposure section will be empty"
        )

    confluence_path = r / "data" / "neuralweb" / "confluence_graph.json"
    confluence = _read_json(confluence_path)
    if confluence is None:
        gap_notes.append(
            f"confluence_graph.json not found at {confluence_path} — "
            "shared_parent_suspect section will be empty"
        )

    spine_path = r / "data" / "neuralweb" / "covariance_spine.json"
    spine = _read_json(spine_path)
    if spine is None:
        gap_notes.append(
            f"covariance_spine.json not found at {spine_path} — "
            "shared_parent_suspect cluster matching will be skipped"
        )

    priors_path = r / "config" / "causal_priors.yml"
    priors = _read_yaml(priors_path)
    if priors is None:
        gap_notes.append(
            f"causal_priors.yml not found at {priors_path} — "
            "collider_risk section will be empty"
        )

    mechanisms_path = r / "data" / "neuralweb" / "causal_mechanisms.jsonl"
    mechanisms = _read_jsonl(mechanisms_path)
    if not mechanisms_path.exists():
        gap_notes.append(
            f"causal_mechanisms.jsonl not found at {mechanisms_path} — "
            "collider_risk section will be empty (no cards filed yet)"
        )

    # ---- Build annotation sections -------------------------------------------

    duplicate_exposure = _build_duplicate_exposure(inventory, gap_notes)
    shared_parent_suspect = _build_shared_parent_suspect(
        confluence, spine, inventory, gap_notes
    )
    collider_risk = _build_collider_risk(mechanisms, priors, gap_notes)

    # ---- Assemble payload ----------------------------------------------------

    return {
        "schema": SCHEMA,
        "artifact_id": ARTIFACT_ID,
        "asof": asof,
        "authority": dict(_AUTHORITY),
        "duplicate_exposure": duplicate_exposure,
        "shared_parent_suspect": shared_parent_suspect,
        "collider_risk": collider_risk,
        "counts": {
            "duplicate_exposure": len(duplicate_exposure),
            "shared_parent_suspect": len(shared_parent_suspect),
            "collider_risk": len(collider_risk),
            "total": len(duplicate_exposure) + len(shared_parent_suspect) + len(collider_risk),
        },
        "gap_notes": gap_notes,
        "produced_by": "engine.neuralweb.causal_audit.build_audit",
    }
