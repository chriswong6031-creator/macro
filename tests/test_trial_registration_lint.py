"""The W1d trial-registration CI lint + walk_forward ledger-sourced n_trials.

Guards audit #21: a harness that deflates a Sharpe without registering a trial budget makes
the DSR/kill/FDR deflation near-inert. The lint must (a) pass on the current tree (the ~33
offenders are grandfathered) and (b) FAIL a synthetic new offender.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_lint():
    sys.path.insert(0, str(_ROOT / "scripts"))
    import check_trial_registration as m  # noqa: E402
    return m


def test_lint_passes_on_current_tree():
    m = _load_lint()
    # every current offender must be grandfathered — the ratchet holds.
    new = m.current_offenders() - m.LEGACY_UNREGISTERED
    assert not new, f"new unregistered multiple-testing harnesses: {sorted(new)}"


def test_allowlist_only_shrinks():
    m = _load_lint()
    stale = m.LEGACY_UNREGISTERED - m.current_offenders()
    assert not stale, f"grandfathered files now register — prune them: {sorted(stale)}"


def test_lint_flags_a_synthetic_new_offender(tmp_path, monkeypatch):
    m = _load_lint()
    # a fake harness that deflates a Sharpe but never registers a budget.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    offender = scripts / "validate_synthetic_offender.py"
    offender.write_text(
        "from engine.validation import deflated_sharpe\n"
        "def main():\n"
        "    return deflated_sharpe(0.05, 0.0, 3.0, 500, n_trials=40)\n")
    monkeypatch.setattr(m, "_ROOT", tmp_path)
    monkeypatch.setattr(m, "_SCRIPTS", scripts)
    off = m.current_offenders()
    assert "scripts/validate_synthetic_offender.py" in off
    # and a registered twin must NOT be flagged
    clean = scripts / "validate_synthetic_clean.py"
    clean.write_text(
        "from engine.trial_ledger import register_trials\n"
        "from engine.validation import deflated_sharpe\n"
        "@register_trials('synthetic', budget=40)\n"
        "def main():\n"
        "    return deflated_sharpe(0.05, 0.0, 3.0, 500, n_trials=40)\n")
    off2 = m.current_offenders()
    assert "scripts/validate_synthetic_clean.py" not in off2


def test_walk_forward_sources_n_trials_from_ledger(tmp_path):
    """_ledger_n_trials must return a real family's summed budget, and never below the floor."""
    sys.path.insert(0, str(_ROOT / "research" / "signal_engine"))
    sys.path.insert(0, str(_ROOT))
    import walk_forward as W  # noqa: E402
    from engine.trial_ledger import TrialLedger

    led = TrialLedger(tmp_path / "led.jsonl")
    led.log_declared_budget(24, family="famX", reason="test")
    led.log_declared_budget(6, family="famX:sub", reason="test")  # prefix-matched, summed

    assert W._ledger_n_trials("famX", ledger=led) == 24 + 6      # prefix families summed
    assert W._ledger_n_trials("absent", ledger=led) == W.UNREGISTERED_TRIALS_FLOOR
    # a real budget must lift the multiple-testing bump above 0 (deflation has teeth)
    assert W._mt_bump(W._ledger_n_trials("famX", ledger=led)) > 0.0
