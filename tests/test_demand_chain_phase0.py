"""Tests for scripts/demand_chain_phase0.py — the demand-chain validation harness."""
from __future__ import annotations

import json

from scripts import demand_chain_phase0 as p0


def test_binomial_extremes():
    assert p0._binom_two_sided(0, 0) is None
    assert p0._binom_two_sided(10, 10) < 0.01          # all hits → highly significant
    assert p0._binom_two_sided(5, 10) == 1.0           # exactly half → p=1


def _write(tmp_path, scored, theses=None):
    d = tmp_path / "data" / "demand_chain"
    d.mkdir(parents=True)
    (d / "scored.jsonl").write_text("\n".join(json.dumps(s) for s in scored))
    (d / "theses.jsonl").write_text("\n".join(json.dumps(t) for t in (theses or [])))
    return d


def _scored(n, hits):
    out = []
    for i in range(n):
        oc = "hit" if i < hits else "miss"
        out.append({"id": f"t{i}", "outcome": oc, "directionally_correct": oc == "hit"})
    return out


def test_pending_below_min_n(tmp_path):
    _write(tmp_path, _scored(5, 5),
           theses=[{"id": "o1", "status": "open"}])
    v = p0.validate(root=tmp_path)
    assert v["verdict"] == "PENDING" and v["n_decided"] == 5 and v["open"] == 1
    assert v["historically_backtestable"] is False


def test_neutral_when_coinflip(tmp_path):
    _write(tmp_path, _scored(24, 12))
    v = p0.validate(root=tmp_path)
    assert v["verdict"] == "NEUTRAL" and v["binom_p_two_sided"] > 0.05


def test_edge_candidate_when_significant(tmp_path):
    _write(tmp_path, _scored(24, 21))                  # 87.5% hit rate
    v = p0.validate(root=tmp_path)
    assert v["verdict"] == "EDGE_CANDIDATE"
    assert v["hit_rate"] > 0.5 and v["binom_p_two_sided"] < 0.05
