"""Import the */5 Prophet Live lane's closure with the heavy deps unimportable.

The prophet-live.yml workflow installs ``pyyaml boto3`` and nothing else, ~80 times a
session. A stray ``import pandas`` anywhere in the closure would make every pass
ModuleNotFoundError — and the lane is fail-soft, so it would go quietly dark instead
of turning anything red. Driven as a subprocess by
tests/test_prophet_live_evaluator.py because pytest's own process has pandas loaded
long before any test runs.
"""
from __future__ import annotations

import importlib.abc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

BLOCKED = {"pandas", "numpy", "pyarrow", "scipy", "requests", "jinja2", "plotly"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, D102
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError(f"blocked by the thin-lane probe: {fullname}")
        return None


sys.meta_path.insert(0, Blocker())

import scripts.prophet_live_evaluator as E  # noqa: E402
from engine.prophet_live import interval, live_states, r2io  # noqa: E402

assert callable(E.run)
assert live_states.PUBLIC_STATES
assert interval.interval_contains({}, 1.0) is None
assert r2io.PACK_KEY and r2io.LIVE_KEY and r2io.EVENTS_PREFIX
for mod in BLOCKED:
    assert mod not in sys.modules, f"{mod} was imported after all"

print("prophet-live thin import OK")
