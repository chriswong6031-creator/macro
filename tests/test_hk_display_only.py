"""Display-only invariant for the HK leaf family.

The new display-only leaves (conditions / market_drivers / signal_stack / alerts /
event_calendar / property) must NEVER be imported by the HK SCORING path
(engine/hk_axes.py, engine/hk_regime.py, engine/hk_playbook.py). They are
descriptive panels, attached only in engine/hk_run.py. Asserted by source grep so a
future refactor that wires one into a score fails loudly.
"""
from __future__ import annotations

from lib import config

_SCORING_MODULES = ["hk_axes.py", "hk_regime.py", "hk_playbook.py"]
_DISPLAY_LEAVES = [
    "hk_conditions", "hk_market_drivers", "hk_signal_stack",
    "hk_alerts", "hk_event_calendar", "hk_property",
]


def test_scoring_modules_do_not_import_display_leaves():
    eng = config.ROOT / "engine"
    for mod in _SCORING_MODULES:
        src = (eng / mod).read_text()
        for leaf in _DISPLAY_LEAVES:
            assert leaf not in src, (
                f"{mod} imports/references {leaf} — display-only invariant violated")


def test_hk_run_attaches_leaves():
    """The leaves ARE wired into engine/hk_run.py (the only place they attach)."""
    src = (config.ROOT / "engine" / "hk_run.py").read_text()
    for leaf in ("hk_market_drivers", "hk_conditions", "hk_alerts", "hk_property"):
        assert leaf in src, f"hk_run.py should attach {leaf}"
