"""Ratchet: no NEW code may deflate a Sharpe by a caller-asserted literal n_trials.

The honest multiple-testing N must come from the Trial Ledger (counted at generation),
not from a number the caller picks and can lowball. Enforcing that on all ~45 existing
callers at once would be a flag-day; instead this test FREEZES the current offenders in
an allowlist that can only ever SHRINK. A new file (or a newly-added literal call in a
previously-clean file) that calls ``deflated_sharpe`` without ``ledger=`` fails the
build. Migrating a file to the ledger (dropping its literal calls) is always allowed.

This is the enforced invariant the whole autonomy argument rests on — see
research/SELF_IMPROVING_AI_SUITE.md (P3, "the keystone"). To migrate a file: pass
``ledger=<TrialLedger>`` + ``family=`` to deflated_sharpe, log the full grid at
generation, then delete that file's entry from ``LEGACY_LITERAL_NTRIALS`` below.
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("engine", "scripts")

# Frozen 2026-06-21 against origin/main. These files call deflated_sharpe with a literal
# n_trials and are grandfathered. THIS LIST MUST ONLY SHRINK — never add to it; migrate
# to the ledger. (A new caller is meant to fail this test, not be appended here.)
LEGACY_LITERAL_NTRIALS = frozenset({
    "engine/meta_label.py",
    "scripts/active_commodity_lev_phase0.py",
    "scripts/anticipation_phase0.py",
    "scripts/btc_onchain_dd_phase0.py",
    "scripts/btc_vector_optimal_phase0.py",
    "scripts/build_strategies.py",
    "scripts/calibrate_regime.py",
    "scripts/calibrate_spvector_phase3.py",
    "scripts/calibrate_spvector_phase4.py",
    "scripts/calibrate_spvector_pit.py",
    "scripts/capitulation_overlay_phase0.py",
    "scripts/commodity_carry_phase0.py",
    "scripts/commodity_tsmom_phase0.py",
    "scripts/commodity_xsec_carry_phase0.py",
    "scripts/commodity_xsec_mom_phase0.py",
    "scripts/commodity_xsec_mom_refute.py",
    "scripts/credit_duration_verify_phase0.py",
    "scripts/cross_asset_confirmation_phase0.py",
    "scripts/cross_asset_phase0.py",
    "scripts/crypto_voltarget_phase0.py",
    "scripts/eth_vector_phase0.py",
    "scripts/hk_southbound_phase0.py",
    "scripts/hyoas_z_timer_phase0.py",
    "scripts/index_direction_phase0.py",
    "scripts/insider_phase0.py",
    "scripts/insider_phase1.py",
    "scripts/intl_macro_sleeve_phase0.py",
    "scripts/intl_tr_trend_phase0.py",
    "scripts/intl_trend_overlay_phase0.py",
    "scripts/mastermind_moderate_phase0.py",
    "scripts/naaim_overlay_phase0.py",
    "scripts/okx_retail_phase0.py",
    "scripts/quad_nfci_phase0.py",
    "scripts/residual_alpha_phase0.py",
    "scripts/stock_conviction_phase0.py",
    "scripts/sue_insider_deep_phase0.py",
    "scripts/thematic_rotation_phase0.py",
    "scripts/top_picks_phase0.py",
    "scripts/turn_of_month_phase0.py",
    "scripts/value_growth_phase0.py",
})

# Files that call the literal path ON PURPOSE — and always will — to contrast it with
# the honest ledger path (the keystone demo). Exempt, not grandfathered: never migrate.
DELIBERATE_LITERAL = frozenset({
    "scripts/trial_ledger_demo.py",
})


def _calls_literal_ntrials(path: Path) -> bool:
    """True if `path` calls deflated_sharpe WITHOUT a ledger= keyword (i.e. relies on a
    caller-asserted literal N — the path we are ratcheting out)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name == "deflated_sharpe":
                kw = {k.arg for k in node.keywords if k.arg}
                if "ledger" not in kw:
                    return True
    return False


def _current_offenders() -> set[str]:
    offenders = set()
    for d in _SCAN_DIRS:
        for path in (_ROOT / d).rglob("*.py"):
            if _calls_literal_ntrials(path):
                offenders.add(path.relative_to(_ROOT).as_posix())
    return offenders


def test_no_new_literal_ntrials_callers():
    offenders = _current_offenders()
    new = offenders - LEGACY_LITERAL_NTRIALS - DELIBERATE_LITERAL
    assert not new, (
        "New code deflates a Sharpe by a literal n_trials — use the Trial Ledger "
        "(deflated_sharpe(..., ledger=<TrialLedger>, family=...)) so N is counted at "
        f"generation, not asserted. Offending file(s): {sorted(new)}")


def test_legacy_allowlist_only_shrinks():
    """If a grandfathered file was migrated to the ledger, prune it from the allowlist
    so the ratchet keeps tightening (and we notice progress)."""
    offenders = _current_offenders()
    stale = LEGACY_LITERAL_NTRIALS - offenders
    assert not stale, (
        "These files no longer call deflated_sharpe with a literal n_trials — remove "
        f"them from LEGACY_LITERAL_NTRIALS so the ratchet stays tight: {sorted(stale)}")
