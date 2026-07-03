"""Ratchet: no import-time logging.disable() in engine/, lib/, scripts/, research/.

``logging.disable()`` is PROCESS-GLOBAL state: executed at import time it mutes every
logger in the process for the rest of the run. Research/scripts CLIs that silence
themselves at module level therefore poison any process that merely *imports* them —
pytest collection, a guarded import from engine/ (donor.py -> tuning_harness, PR #1115),
a research harness importing a sibling — producing order-dependent test flakes. This has
bitten twice (research/signal_engine/walk_forward.py, then tuning_harness.py); this test
makes the third time a red build instead of a flake.

The rule: CLI silencers live under ``if __name__ == "__main__":`` (or inside a function),
never in straight-line module scope. Copy the comment idiom from
research/signal_engine/walk_forward.py. Anything else that runs at import — class bodies,
try/except, loops, non-__main__ ifs — counts as module level here, because it is.

A companion ratchet covers import-time ``warnings.filterwarnings("ignore")`` /
``simplefilter("ignore")`` — the warnings filter list is process-global the same way.
That one grandfathers existing CLIs (pytest.warns installs its own catch_warnings
context, so the blast radius is smaller) behind an allowlist that may only shrink.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("engine", "lib", "scripts", "research")


def _is_main_guard(test: ast.expr) -> bool:
    """True for ``__name__ == "__main__"`` (either operand order)."""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)):
        return False
    operands = (test.left, *test.comparators)
    return (any(isinstance(o, ast.Name) and o.id == "__name__" for o in operands)
            and any(isinstance(o, ast.Constant) and o.value == "__main__" for o in operands))


def _is_logging_disable(call: ast.Call) -> bool:
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "disable"
            and isinstance(f.value, ast.Name) and f.value.id == "logging")


def _is_warnings_ignore(call: ast.Call) -> bool:
    """``warnings.filterwarnings("ignore", ...)`` or ``warnings.simplefilter("ignore")``
    — the warnings filter list is process-global exactly like logging's disable level."""
    f = call.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    if name not in ("filterwarnings", "simplefilter"):
        return False
    return (bool(call.args) and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == "ignore")


def _import_time_hits(node: ast.AST, hits: list[int], match) -> None:
    """Collect line numbers of matching calls that execute at import time.

    Recurses through everything that runs on import (class bodies, try/except, loops,
    plain ifs) and stops at the two things that don't: function bodies and the body of
    an ``if __name__ == "__main__":`` guard (whose else-branch still runs on import).
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.If) and _is_main_guard(child.test):
            for stmt in child.orelse:
                _import_time_hits(stmt, hits, match)
            continue
        if isinstance(child, ast.Call) and match(child):
            hits.append(child.lineno)
        _import_time_hits(child, hits, match)


def _offenders(match=_is_logging_disable) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for d in _SCAN_DIRS:
        root = _ROOT / d
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            hits: list[int] = []
            _import_time_hits(tree, hits, match)
            if hits:
                out[path.relative_to(_ROOT).as_posix()] = hits
    return out


# Frozen 2026-07-03 against origin/main (post-#1120). These CLIs mute the process-global
# warnings filter at import. Less destructive than logging.disable (pytest.warns installs
# its own catch_warnings context, so warning-asserting tests survive), so they are
# grandfathered instead of flag-day'd. THIS LIST MUST ONLY SHRINK — never add to it. To
# migrate a file: move the silencer under `if __name__ == "__main__":` (walk_forward.py
# idiom) and delete its entry. Engine modules get a scoped catch_warnings block instead
# (see engine/donor.py::donor_state).
LEGACY_IMPORT_TIME_WARNINGS_IGNORE = frozenset({
    "research/entry_timing/wave5b.py",
    "research/signal_engine/multicountry_poc.py",
    "scripts/_novel_edge_probe.py",
    "scripts/_novel_edge_probe2.py",
    "scripts/_reversal_netcost_probe.py",
    "scripts/active_commodity_lev_phase0.py",
    "scripts/backfill_forward_logs.py",
    "scripts/build_factor_series.py",
    "scripts/calibrate_bonds.py",
    "scripts/calibrate_bottom_confidence.py",
    "scripts/calibrate_bottom_radar.py",
    "scripts/calibrate_commodities.py",
    "scripts/calibrate_forex.py",
    "scripts/calibrate_rate_inflation.py",
    "scripts/calibrate_regime.py",
    "scripts/calibrate_vector.py",
    "scripts/canada_residual_alpha_phase0.py",
    "scripts/china_basket_breadth_phase0.py",
    "scripts/china_basket_momentum_backtest.py",
    "scripts/china_lowvol_phase0.py",
    "scripts/china_residual_alpha_deep.py",
    "scripts/china_residual_alpha_phase0.py",
    "scripts/china_reversal_phase0.py",
    "scripts/china_sector_pathway_phase0.py",
    "scripts/china_turnover_surge_phase0.py",
    "scripts/commodity_tsmom_phase0.py",
    "scripts/commodity_xsec_carry_phase0.py",
    "scripts/commodity_xsec_mom_phase0.py",
    "scripts/commodity_xsec_mom_refute.py",
    "scripts/conviction_v2_regime.py",
    "scripts/cross_asset_confirm_phase0.py",
    "scripts/factor_exposure_phase0.py",
    "scripts/factor_ic_scorecard.py",
    "scripts/fit_ladder_risk_calibration.py",
    "scripts/group_flow_validation.py",
    "scripts/hk_residual_alpha_phase0.py",
    "scripts/hk_southbound_phase0.py",
    "scripts/insider_phase0.py",
    "scripts/insider_phase1.py",
    "scripts/integration_lab.py",
    "scripts/intl_macro_sleeve_phase0.py",
    "scripts/intl_phase0.py",
    "scripts/ipo_lockup_phase0.py",
    "scripts/keystone_position_gate_phase0.py",
    "scripts/market_drivers_preview.py",
    "scripts/mastermind_moderate_phase0.py",
    "scripts/measure_incremental_ic.py",
    "scripts/meta_label_btc.py",
    "scripts/name_direction_phase0.py",
    "scripts/okx_retail_phase0.py",
    "scripts/pead_freshness_phase0.py",
    "scripts/quad_nfci_phase0.py",
    "scripts/regime_snap_history.py",
    "scripts/research/breakout_52w_volume.py",
    "scripts/research/calendar_seasonality_tom_moy.py",
    "scripts/research/residual_short_term_reversal.py",
    "scripts/research_commodity_conviction.py",
    "scripts/research_conviction.py",
    "scripts/research_dislocation.py",
    "scripts/residual_alpha_phase0.py",
    "scripts/setup_score_phase0.py",
    "scripts/shadow_pit_regime.py",
    "scripts/stock_conviction_phase0.py",
    "scripts/strategy_lab.py",
    "scripts/sue_deep_phase0.py",
    "scripts/sue_insider_deep_phase0.py",
    "scripts/top_picks_freshness_phase0.py",
    "scripts/top_picks_phase0.py",
    "scripts/tsmom_phase0.py",
    "scripts/turn_of_month_phase0.py",
    "scripts/validate_composite.py",
    "scripts/validate_drawdown_risk_pit.py",
    "scripts/validate_provisional_replay.py",
    "scripts/validate_reversal.py",
    "scripts/validate_reversal_nonsurvivor.py",
    "scripts/validate_sue.py",
    "scripts/validate_timing_overlay.py",
    "scripts/value_growth_phase0.py",
})


def test_no_new_import_time_warnings_ignore():
    """Companion ratchet: the warnings filter list is process-global too. New files (or a
    newly-added module-level silencer in a previously-clean file) fail; migrating a file
    under __main__ is always allowed."""
    offenders = set(_offenders(_is_warnings_ignore))
    new = offenders - LEGACY_IMPORT_TIME_WARNINGS_IGNORE
    assert not new, (
        "warnings.filterwarnings('ignore')/simplefilter('ignore') at module level mutes "
        "the process-global warnings filter for any importer. Move it under `if __name__ "
        "== \"__main__\":` (walk_forward.py idiom); in engine modules use a scoped "
        "catch_warnings block (see engine/donor.py::donor_state). Do NOT add to the "
        f"allowlist. Offending file(s): {sorted(new)}")


def test_warnings_ignore_allowlist_only_shrinks():
    offenders = set(_offenders(_is_warnings_ignore))
    stale = LEGACY_IMPORT_TIME_WARNINGS_IGNORE - offenders
    assert not stale, (
        "These files no longer silence warnings at import time — remove them from "
        f"LEGACY_IMPORT_TIME_WARNINGS_IGNORE so the ratchet stays tight: {sorted(stale)}")


def test_no_module_level_logging_disable():
    offenders = _offenders()
    assert not offenders, (
        "logging.disable() at module level mutes every logger in the process for any "
        "importer (order-dependent pytest flakes — bitten twice: walk_forward.py, then "
        "tuning_harness.py in PR #1115). Move it (and its warnings.filterwarnings "
        "sibling) under `if __name__ == \"__main__\":` — copy the comment idiom from "
        f"research/signal_engine/walk_forward.py. Offenders (file: lines): {offenders}")


def test_checker_positive_control():
    """Guard the guard: a silently broken walker would make the lint pass forever."""
    src = textwrap.dedent("""
        import logging
        logging.disable(logging.CRITICAL)          # line 3: BAD, straight-line module scope
        class C:
            logging.disable(logging.CRITICAL)      # line 5: BAD, class bodies run on import
        try:
            logging.disable(logging.CRITICAL)      # line 7: BAD, try bodies run on import
        except Exception:
            pass
        if some_flag:
            logging.disable(logging.CRITICAL)      # line 11: BAD, non-__main__ if
        def f():
            logging.disable(logging.CRITICAL)      # ok: only runs when called
        if __name__ == "__main__":
            logging.disable(logging.CRITICAL)      # ok: the sanctioned CLI idiom
        else:
            logging.disable(logging.CRITICAL)      # line 17: BAD, else-branch runs on import
        if "__main__" == __name__:
            logging.disable(logging.CRITICAL)      # ok: reversed operands
    """)
    hits: list[int] = []
    _import_time_hits(ast.parse(src), hits, _is_logging_disable)
    assert hits == [3, 5, 7, 11, 17], hits

    wsrc = textwrap.dedent("""
        import warnings
        warnings.filterwarnings("ignore")           # line 3: BAD
        warnings.simplefilter("ignore")             # line 4: BAD
        warnings.filterwarnings("default")          # ok: not muting
        warnings.filterwarnings("ignore", category=DeprecationWarning)  # line 6: BAD
        if __name__ == "__main__":
            warnings.filterwarnings("ignore")       # ok: CLI idiom
        def f():
            warnings.simplefilter("ignore")         # ok: scoped-by-caller is on them
    """)
    whits: list[int] = []
    _import_time_hits(ast.parse(wsrc), whits, _is_warnings_ignore)
    assert whits == [3, 4, 6], whits
