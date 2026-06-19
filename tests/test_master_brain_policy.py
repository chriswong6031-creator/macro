"""master_brain is policy-aware: gather_state surfaces fed_stance + the policy layer."""
from __future__ import annotations

import json

from engine import master_brain as mb


def _seed(tmp, *, fed_stance=None, intel=None):
    (tmp / "data" / "regime").mkdir(parents=True)
    latest = {"date": "2026-06-18", "quad_name": "Goldilocks"}
    if fed_stance:
        latest["fed_stance"] = fed_stance
    (tmp / "data" / "regime" / "latest.json").write_text(json.dumps(latest))
    if intel is not None:
        (tmp / "data" / "policy").mkdir(parents=True)
        (tmp / "data" / "policy" / "intel.json").write_text(json.dumps(intel))


def test_policy_intel_summary_compact(tmp_path):
    _seed(tmp_path, intel={"thesis": {"en": "low-yield + reindustrialization"},
                           "regime_read": {"en": "revealed > narrative"},
                           "rotation": {"targeted": [{"theme_en": "Defense"}, {"theme_en": "Nuclear"}],
                                        "starved": [{"theme_en": "Long duration"}]},
                           "predictions": [{"status": "open"}, {"status": "hit"}, {"status": "open"}]})
    pol = mb._policy_intel_summary(tmp_path)
    assert pol["thesis"].startswith("low-yield")
    assert pol["targeted"] == ["Defense", "Nuclear"] and pol["starved"] == ["Long duration"]
    assert pol["open_predictions_n"] == 2


def test_gather_state_surfaces_fed_stance_and_policy(tmp_path):
    _seed(tmp_path,
          fed_stance={"stance": "hawkish", "label_en": "Hawkish", "guidance": "tightening",
                      "implied_cuts_12m": -0.6, "market_vs_fed_en": "market more hawkish", "extra": "dropped"},
          intel={"thesis": {"en": "T"}, "rotation": {"targeted": [{"theme_en": "Defense"}]},
                 "predictions": [{"status": "open"}]})
    st = mb.gather_state(tmp_path)
    assert st["fed_stance"]["stance"] == "hawkish" and "extra" not in st["fed_stance"]
    assert st["policy_intel"]["thesis"] == "T" and st["policy_intel"]["targeted"] == ["Defense"]


def test_gather_state_omits_when_absent(tmp_path):
    _seed(tmp_path)                       # no fed_stance, no intel.json
    st = mb.gather_state(tmp_path)
    assert "fed_stance" not in st and "policy_intel" not in st
