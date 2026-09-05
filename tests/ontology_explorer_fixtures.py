"""Synthetic builders for the F04-X1 ontology-explorer tests.

EVERY value in here is INVENTED. Nothing in this module, and nothing in
``tests/fixtures/ontology_explorer/``, is a copy of a current owner reading from
``data/transmission/chain_state.json``. The tests must be able to run, fail and
be read in a public pull request, so the fixtures deliberately use a synthetic
chain slug (``synthetic_*``), synthetic series names (``SYN-*``) and round
numbers that could not be mistaken for a real print.

The synthetic chains mirror the SHAPE of the real WTI chain — a linear
``n1 -> n2 -> n3 -> n4`` path whose order is carried by the ordered ``hops``
list, not by the unordered ``nodes`` mapping — because path order is what the
first-blocking-leg rule is required to use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SLUG = "synthetic_linear_probe"
STATE_SCHEMA = "transmission_chains.v1"


def _bi(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def chain_yaml(slug: str = SLUG, *, cycle: bool = False, rev: int = 2) -> dict[str, Any]:
    """A four-node linear chain in the real knowledge-file shape."""
    hops = [
        {
            "from": "n1", "to": "n2", "sign": "+", "lag_d": [5, 60],
            "label": _bi("Leg one -> leg two", "环节一 -> 环节二"),
            "condition": _bi("synthetic condition one", "合成条件一"),
            "mechanism": _bi("synthetic mechanism one", "合成机制一"),
        },
        {
            "from": "n2", "to": "n3", "sign": "+", "lag_d": [10, 90],
            "label": _bi("Leg two -> leg three", "环节二 -> 环节三"),
            "condition": _bi("synthetic condition two", "合成条件二"),
            "mechanism": _bi("synthetic mechanism two", "合成机制二"),
        },
        {
            "from": "n3", "to": "n4", "sign": "-", "lag_d": [0, 30],
            "label": _bi("Leg three -> leg four", "环节三 -> 环节四"),
            "condition": _bi("synthetic condition three", "合成条件三"),
            "mechanism": _bi("synthetic mechanism three", "合成机制三"),
        },
    ]
    if cycle:
        hops.append({
            "from": "n4", "to": "n2", "sign": "+", "lag_d": [1, 5],
            "label": _bi("Leg four -> leg two (cycle)", "环节四 -> 环节二（环）"),
            "condition": _bi("synthetic cycle condition", "合成环条件"),
            "mechanism": _bi("synthetic cycle mechanism", "合成环机制"),
        })
    return {
        "chain": slug,
        "rev": rev,
        "tier": "hypothesis",
        "title": _bi("Synthetic linear probe", "合成线性探针"),
        "nodes": {
            "n1": {"title": _bi("Node one", "节点一"), "src": "synthetic",
                   "test": {"all": [{"series": "SYN-A", "metric": "ret",
                                     "window": 60, "op": "gt", "value": 10}]}},
            "n2": {"title": _bi("Node two", "节点二"), "src": "synthetic",
                   "test": {"all": [{"series": "SYN-B", "metric": "ret_bp",
                                     "window": 22, "op": "gt", "value": 10}]}},
            "n3": {"title": _bi("Node three", "节点三"), "src": "synthetic",
                   "test": {"all": [{"series": "SYN-C", "metric": "ret_bp",
                                     "window": 63, "op": "gt", "value": 10}]}},
            "n4": {"title": _bi("Node four", "节点四"), "src": "synthetic",
                   "test": {"all": [{"series": "SYN-D", "vs": "SYN-E", "metric": "rs",
                                     "window": 63, "op": "lt", "value": 0}]}},
        },
        "hops": hops,
        "falsifiers": [{
            "when": {"series": "SYN-B", "metric": "ret_bp", "window": 22,
                     "op": "lt", "value": 1},
            "src": "synthetic",
            "note": "synthetic invalidator note",
        }],
        "null_model": "synthetic null model question",
        "exposure_screens": {
            "synthetic_screen": {
                "label": _bi("Synthetic screen", "合成筛选"),
                "note": _bi("synthetic screen note", "合成筛选说明"),
                "any": [{"path": "synthetic.field", "op": "==", "value": "yes"}],
            },
        },
        "provenance": {"theory": ["synthetic theory"], "episodes": ["1900"],
                       "added_by": "test", "added_on": "2026-01-01"},
        "changelog": [{"rev": 2, "on": "2026-01-01", "what": "synthetic"}],
    }


def _node(node_id: str, *, confirmed: bool, resolved: bool = True,
          value: float = 0.0, threshold: float = 10.0) -> dict[str, Any]:
    return {
        "id": node_id,
        "resolved": resolved,
        "confirmed": confirmed,
        "receipts": [{"series": f"SYN-{node_id.upper()}", "metric": "ret",
                      "window": 60, "value": value, "op": "gt",
                      "threshold": threshold, "passed": confirmed}],
    }


def _hop(hop_from: str, hop_to: str, *, confirmed: bool) -> dict[str, Any]:
    return {
        "id": f"{hop_from}->{hop_to}",
        "from": hop_from,
        "to": hop_to,
        "lag_d": [5, 60],
        "confirmed": confirmed,
        "asof": "2026-01-02" if confirmed else None,
        "value_receipt": [{"series": f"SYN-{hop_to.upper()}", "metric": "ret_bp",
                           "window": 22, "value": 1.0, "op": "gt",
                           "threshold": 10, "passed": confirmed}],
        "base_rate": {"p_confirm": 0.5, "n": 10, "regime_split": "unavailable"},
    }


def chain_state(slug: str = SLUG, *, confirmed: tuple[bool, ...] = (False, False, False, True),
                state: str = "dormant", rev: int = 2,
                omit_nodes: tuple[str, ...] = (),
                cycle: bool = False) -> dict[str, Any]:
    """A ``transmission_chains.v1`` artifact carrying only synthetic readings."""
    ids = ["n1", "n2", "n3", "n4"]
    nodes = [_node(node_id, confirmed=flag, value=1.0 * i)
             for i, (node_id, flag) in enumerate(zip(ids, confirmed, strict=True))
             if node_id not in omit_nodes]
    hop_pairs = [("n1", "n2"), ("n2", "n3"), ("n3", "n4")]
    if cycle:
        hop_pairs.append(("n4", "n2"))
    by_id = dict(zip(ids, confirmed, strict=True))
    hops = [_hop(a, b, confirmed=bool(by_id[a] and by_id[b])) for a, b in hop_pairs]
    return {
        "schema": STATE_SCHEMA,
        "asof": "2026-01-02",
        "built": "2026-01-03 02:10 UTC",   # the house format, not ISO
        "chains": [{
            "chain": slug,
            "rev": rev,
            "tier": "calibrated_context",
            "title": _bi("Synthetic linear probe", "合成线性探针"),
            "state": state,
            "state_label": _bi(state.title(), "合成状态"),
            "hop": 0,
            "n_hops": len(hop_pairs),
            "armable": True,
            "episode_id": None,
            "hops": hops,
            "nodes": nodes,
            "falsifier_fired": None,
            "base_rates": {},
            "display_only": True,
        }],
        "caveats": [],
        "display_only": True,
    }


def build_root(tmp_path: Path, *, yaml_doc: dict[str, Any] | None = None,
               state_doc: dict[str, Any] | None = None,
               slug: str = SLUG) -> Path:
    """Materialize a minimal repo root the composer can read."""
    yaml_doc = chain_yaml(slug) if yaml_doc is None else yaml_doc
    state_doc = chain_state(slug) if state_doc is None else state_doc
    knowledge = tmp_path / "knowledge" / "transmission"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / f"{slug}.yaml").write_text(
        yaml.safe_dump(yaml_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    data = tmp_path / "data" / "transmission"
    data.mkdir(parents=True, exist_ok=True)
    (data / "chain_state.json").write_text(
        json.dumps(state_doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return tmp_path
