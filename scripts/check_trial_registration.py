#!/usr/bin/env python3
"""CI lint: every multiple-testing harness must REGISTER its trial budget (W1d).

A ``validate_*`` / ``*_phase0`` / ``*_phase1`` harness that deflates a Sharpe (calls
``deflated_sharpe``) OR sweeps a grid is spending a multiple-testing budget. If it never
records that budget in the Trial Ledger, the DSR/kill/FDR gates it feeds are deflated by a
number nobody maintains (audit #21) — "effective deflation is ~zero and lucky configs pass".

This check makes registering cheaper than skipping: a NEW harness that deflates a Sharpe but
does not register (via ``@register_trials`` / ``TrialLedger.log_declared_budget`` /
``log_grid`` / ``with_declared_budget`` / a ``ledger=`` kwarg on ``deflated_sharpe``) fails
the build. The ~44 pre-existing offenders are grandfathered in ``LEGACY_UNREGISTERED`` (seeded
retrospectively in ``data/trial_ledger.jsonl`` with ``basis: estimated`` budgets) — that list
can only ever SHRINK. Migrating a harness = add one ``register_trials(...)`` line, then delete
its allowlist entry.

Run:  python3 scripts/check_trial_registration.py          # lint (exit 1 on a new offender)
      python3 scripts/check_trial_registration.py --list    # show the current offender set
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"

# a harness "spends a budget" if it deflates a Sharpe or logs a walk-forward with n_trials.
_SEARCH_CALLS = {"deflated_sharpe"}
# it "registers" if it touches any of these.
_REGISTER_NAMES = {
    "register_trials", "log_declared_budget", "log_grid", "log_trial",
    "with_declared_budget", "TrialLedger",
}


def _is_harness(path: Path) -> bool:
    n = path.name
    return (n.startswith("validate_") or "_phase0" in n or "_phase1" in n) and n.endswith(".py")


def _analyze(path: Path) -> tuple[bool, bool]:
    """(spends_budget, registers) for a harness file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return (False, True)  # unparseable → don't block on it here (other CI catches syntax)
    spends = False
    registers = False
    for node in ast.walk(tree):
        # a call to a registration helper, or a deflated_sharpe with ledger=
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name in _SEARCH_CALLS:
                spends = True
                if any(k.arg == "ledger" for k in node.keywords):
                    registers = True
            if name in _REGISTER_NAMES:
                registers = True
        # decorator form: @register_trials(...) or @<mod>.register_trials(...)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                d = dec.func if isinstance(dec, ast.Call) else dec
                dn = d.attr if isinstance(d, ast.Attribute) else d.id if isinstance(d, ast.Name) else None
                if dn in _REGISTER_NAMES:
                    registers = True
        # a bare import of register_trials / TrialLedger counts as intent to register
        if isinstance(node, ast.ImportFrom) and node.module and "trial_ledger" in node.module:
            for a in node.names:
                if a.name in _REGISTER_NAMES:
                    registers = True
    return (spends, registers)


def current_offenders() -> set[str]:
    """Harnesses that SPEND a multiple-testing budget but do NOT register it."""
    off = set()
    for p in sorted(_SCRIPTS.rglob("*.py")):
        if not _is_harness(p):
            continue
        spends, registers = _analyze(p)
        if spends and not registers:
            off.add(p.relative_to(_ROOT).as_posix())
    return off


# Frozen 2026-07-01: harnesses that deflate a Sharpe without registering a budget. Seeded
# retrospectively in data/trial_ledger.jsonl (basis: estimated). THIS LIST ONLY SHRINKS.
LEGACY_UNREGISTERED = frozenset({
    "scripts/active_commodity_lev_phase0.py",
    "scripts/anticipation_phase0.py",
    "scripts/btc_onchain_dd_phase0.py",
    "scripts/btc_vector_optimal_phase0.py",
    "scripts/capitulation_overlay_phase0.py",
    "scripts/commodity_carry_phase0.py",
    "scripts/commodity_tsmom_phase0.py",
    "scripts/commodity_xsec_carry_phase0.py",
    "scripts/commodity_xsec_mom_phase0.py",
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


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    offenders = current_offenders()
    if "--list" in argv:
        print(f"{len(offenders)} harness(es) spend a budget without registering:")
        for f in sorted(offenders):
            grand = " (grandfathered)" if f in LEGACY_UNREGISTERED else " *** NEW ***"
            print(f"  {f}{grand}")
        return 0

    new = offenders - LEGACY_UNREGISTERED
    stale = LEGACY_UNREGISTERED - offenders
    rc = 0
    if new:
        print("FAIL: these harnesses deflate a Sharpe but never register a trial budget.", file=sys.stderr)
        print("Add register_trials(family, budget=...) (or pass ledger= to deflated_sharpe) so the", file=sys.stderr)
        print("DSR/kill/FDR deflation reflects the real search space (W1d, audit #21):", file=sys.stderr)
        for f in sorted(new):
            print(f"  {f}", file=sys.stderr)
        rc = 1
    if stale:
        print("NOTE: these grandfathered harnesses now register — prune them from "
              "LEGACY_UNREGISTERED so the ratchet stays tight:", file=sys.stderr)
        for f in sorted(stale):
            print(f"  {f}", file=sys.stderr)
        rc = 1
    if rc == 0:
        print(f"OK: no new unregistered multiple-testing harness ({len(offenders)} grandfathered).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
