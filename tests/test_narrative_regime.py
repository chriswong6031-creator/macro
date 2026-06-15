"""Tests for engine/narrative_regime.py — the NDI display banner (P1).

Gate A (scripts/narrative_regime_phase0.py) showed the text-uncertainty leg is
redundant-or-worse with VIX for forward vol, so NDI is DISPLAY-ONLY. The load-
bearing invariant these tests protect: `gate_multiplier` is PINNED to 1.0 — NDI
must never silently become a scored conditioner — and the module stays a LEAF.

Run as a plain script:  python tests/test_narrative_regime.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import narrative_regime as nr  # noqa: E402


def test_band_thresholds():
    assert nr._band(10) == "calm" and nr._band(49.9) == "calm"
    assert nr._band(50) == "elevated" and nr._band(79.9) == "elevated"
    assert nr._band(80) == "high" and nr._band(100) == "high"
    assert nr._band(None) == "unknown"


def test_pct_of_history():
    import pandas as pd
    s = pd.Series(range(1000))
    assert nr._pct_of_history(s, 499) == 50.0
    assert nr._pct_of_history(s, 999) == 100.0
    assert nr._pct_of_history(pd.Series([1, 2, 3]), 2) is None     # < 250 obs
    assert nr._pct_of_history(s, None) is None


def test_compute_shape_and_gate_pinned():
    """compute() reads the real store; whatever it returns must be a context-only
    dict with a PINNED no-op gate, or None — never a scored value."""
    out = nr.compute()
    if out is None:
        return                              # no data in this env — acceptable
    assert out["is_context_only"] is True
    assert out["schema"] == "narrative_regime.v1"
    # THE invariant: the gate is a no-op and advertises itself as off
    assert out["gate_multiplier"] == 1.0, "NDI gate must stay pinned at 1.0 (no scoring)"
    assert out["gate_status"] == "pinned_off"
    assert out["band"] in {"calm", "elevated", "high", "unknown"}
    if out.get("ndi") is not None:
        assert 0.0 <= out["ndi"] <= 100.0
    # legs, when present, are percentile reads in [0,100]
    for leg in (out.get("legs") or {}).values():
        if leg.get("pct") is not None:
            assert 0.0 <= leg["pct"] <= 100.0


def test_gate_multiplier_is_literally_pinned_in_source():
    """Defense in depth: the source must not compute gate_multiplier from data — it
    is a hard literal 1.0. (Guards against a future edit quietly wiring it.)"""
    src = (ROOT / "engine" / "narrative_regime.py").read_text()
    assert '"gate_multiplier": 1.0' in src


# --------------------------------------------------------------------------- #
# LEAF discipline
# --------------------------------------------------------------------------- #
_FORBIDDEN_ROOTS = {"engine.conditions", "engine.regime", "engine.run", "engine.inputs",
                    "engine.cycles", "engine.equity_alloc", "engine.calibrate"}


def test_narrative_regime_is_a_leaf():
    tree = ast.parse((ROOT / "engine" / "narrative_regime.py").read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    for m in mods:
        assert m not in _FORBIDDEN_ROOTS, f"LEAF violation: imports core {m}"
        assert not m.startswith("engine."), f"NDI should import no engine modules, got {m}"


def test_no_engine_module_imports_narrative_regime():
    offenders = [p.name for p in (ROOT / "engine").glob("*.py")
                 if p.name != "narrative_regime.py" and "narrative_regime" in p.read_text()]
    assert not offenders, f"scoring-core modules import NDI: {offenders}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
