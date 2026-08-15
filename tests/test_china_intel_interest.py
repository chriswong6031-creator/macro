"""The board-independent China Intelligence interest composite (CN Prophet v4).

The load-bearing property under test is the FENCE: this composite must be computable
without any Prophet output, so ranking the board by it cannot close a feedback loop.
The fence is tested structurally (the module never reads the board or the hub's own
composite) as well as behaviourally (identical evidence scores identically no matter
what the board says about the name).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from engine import china_intel_interest as CII


# ── The fence ─────────────────────────────────────────────────────────────── #

def test_scorer_signature_admits_no_board_input():
    """The pure scorer cannot be handed a board row even by accident."""
    params = set(inspect.signature(CII.interest_score).parameters)
    assert params == {"altdata_row", "radar_row", "special_flags", "traj"}


def _read_tokens(module) -> set[str]:
    """Every name the module actually READS: attributes, ``.get`` keys, subscripts,
    and path-like literals.

    AST rather than grep on purpose. The module NAMES the forbidden terms in its
    docstring and in ``BOARD_DERIVED_TERMS_EXCLUDED`` — declaring an exclusion is the
    opposite of performing a read, and a substring scan cannot tell the two apart.
    """
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    # Docstrings NAME the excluded terms on purpose — that is documentation of the
    # fence, not a read of anything. Collect them so the literal scan below skips them.
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            for stmt in getattr(node, "body", []):
                if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    prose.add(id(stmt.value))
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in prose:
            continue
        if isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                tokens.add(node.slice.value)
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "get"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                tokens.add(node.args[0].value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "/" in node.value:            # a file path is always a read
                tokens.add(node.value)
    return tokens


def test_module_never_reads_the_board_or_the_hub_composite():
    """Structural: no board artifact, no command artifact, no opportunity_score.

    A structural assertion is the right shape here — the fence is about what this
    module is ALLOWED to read, and a behavioural test cannot prove the absence of a
    read that only happens on some other code path.
    """
    tokens = _read_tokens(CII)
    forbidden = (
        "china_standouts",           # the Prophet board artifact
        "site/china_intel/command",  # the hub's own ranked output
        "opportunity_score",         # the hub composite this module replaces
        "prophet_score",
        "prophet_rank",
        "board_row",
        "board_member",
        "_load_board_membership",
        "_load_board_rows",
        "_dossier",
    )
    leaked = sorted(token for token in forbidden
                    if any(token in read for read in tokens))
    assert not leaked, f"board-derived read leaked into the scorer: {leaked}"


def test_excluded_terms_are_declared_for_the_reader():
    assert set(CII.BOARD_DERIVED_TERMS_EXCLUDED) >= {
        "board_row_direction", "board_label_edge", "board_absent_bonus",
        "board_lagging_desk_gap", "prophet_score", "prophet_rank",
        "hub_opportunity_score",
    }


def test_hub_import_contract_is_pinned():
    """The hub INPUT loaders this module reuses must keep existing.

    They are reused (rather than copied) so the two scorers can never disagree about
    what a desk said. A hub rename must therefore fail HERE, loudly, instead of
    silently darkening the board's ordering into all-fallback.
    """
    hub = pytest.importorskip("engine.china_intel_hub")
    for name in ("_load_radar_by_sector", "_build_radar_by_ticker",
                 "_load_special_by_ticker", "_load_closes_and_benchmark",
                 "_price_trajectory"):
        assert callable(getattr(hub, name, None)), f"china_intel_hub.{name} is gone"


def test_altdata_full_rows_accessor_exists():
    """The FULL universe accessor, not the top-30 display slice."""
    ca = pytest.importorskip("engine.china_altdata")
    assert callable(getattr(ca, "full_rows", None))


# ── Nulls are not zeros ───────────────────────────────────────────────────── #

def test_no_desk_evidence_is_a_fallback_not_a_zero():
    record = CII.interest_score(traj={"off_high_pct": -30.0, "rs_20d": 1.0})
    assert record["basis"] == CII.BASIS_FALLBACK
    assert record["score"] is None
    assert record["unavailable_reason"] == "no_desk_evidence"


def test_desk_present_but_no_edge_evidence_is_also_a_fallback():
    """A name with a desk read but no price plane has no second half to the composite.

    The hub awards a 0.4 default edge when its component list is empty; here an empty
    list is genuinely empty (the board legs that could have filled it are excluded),
    so awarding a middling constant would manufacture the very number this module
    exists to avoid.
    """
    record = CII.interest_score(altdata_row={"convergence": 0.9, "side": "accumulate"})
    assert record["basis"] == CII.BASIS_FALLBACK
    assert record["unavailable_reason"] == "no_edge_evidence"
    assert record["score"] is None


def test_desk_present_and_bearish_is_a_MEASURED_zero():
    """Distinct from the fallback: the desk looked and had nothing bullish to say."""
    record = CII.interest_score(
        altdata_row={"convergence": -0.9, "side": "distribute", "conviction100": 90},
        traj={"off_high_pct": -30.0, "rs_20d": 1.0},
    )
    assert record["basis"] == CII.BASIS_MEASURED
    assert record["score"] == 0.0
    assert record["signal_core"] == 0.0


# ── Direction ─────────────────────────────────────────────────────────────── #

def test_distribute_never_outranks_accumulate_at_equal_magnitude():
    """The v4 board is a one-sided BUY shelf; |signal| is the wrong core for it.

    Measured 2026-08-15 on the live board: an unsigned core put the three most
    strongly-DISTRIBUTED names in the top three slots. This is the regression guard.
    """
    traj = {"off_high_pct": -30.0, "rs_20d": 2.0}
    up = CII.interest_score(
        altdata_row={"convergence": 0.8, "side": "accumulate", "conviction100": 80},
        traj=traj)
    down = CII.interest_score(
        altdata_row={"convergence": -0.8, "side": "distribute", "conviction100": 80},
        traj=traj)
    assert up["score"] > down["score"]
    assert down["score"] == 0.0


def test_conviction100_is_not_credited_on_the_distribute_side():
    """``conviction100`` is an UNSIGNED magnitude — crediting it either way would
    smuggle bearish conviction into a buy-shelf ranking."""
    record = CII.interest_score(
        altdata_row={"convergence": -0.05, "side": "distribute", "conviction100": 99},
        traj={"off_high_pct": -30.0, "rs_20d": 1.0})
    assert record["signal_core"] == 0.0


def test_radar_only_names_score_off_positive_divergences_only():
    traj = {"off_high_pct": -20.0, "rs_20d": 0.0}
    pos = CII.interest_score(radar_row={"sign": "positive", "strength": 0.9}, traj=traj)
    neg = CII.interest_score(radar_row={"sign": "negative", "strength": 0.9}, traj=traj)
    assert pos["signal_source"] == "radar"
    assert pos["score"] > 0
    assert neg["score"] == 0.0


# ── Composite behaviour ───────────────────────────────────────────────────── #

def test_score_is_bounded_and_deterministic():
    kwargs = dict(
        altdata_row={"convergence": 1.0, "side": "accumulate", "conviction100": 100},
        radar_row={"sign": "positive", "strength": 1.0},
        traj={"off_high_pct": -80.0, "rs_20d": -20.0, "ret_20d": -5.0},
    )
    first = CII.interest_score(**kwargs)
    second = CII.interest_score(**kwargs)
    assert first == second
    assert 0.0 <= first["score"] <= 100.0


def test_off_high_room_and_unspent_rs_raise_interest():
    base = {"altdata_row": {"convergence": 0.6, "side": "accumulate"}}
    deep = CII.interest_score(**base, traj={"off_high_pct": -50.0, "rs_20d": 0.0})
    shallow = CII.interest_score(**base, traj={"off_high_pct": -5.0, "rs_20d": 30.0})
    assert deep["score"] > shallow["score"]


def test_crowding_and_overhang_are_drags():
    traj = {"off_high_pct": -30.0, "rs_20d": 1.0}
    clean = CII.interest_score(
        altdata_row={"convergence": 0.6, "side": "accumulate", "flags": []}, traj=traj)
    crowded = CII.interest_score(
        altdata_row={"convergence": 0.6, "side": "accumulate",
                     "flags": ["leverage_crowded"]}, traj=traj)
    unlocked = CII.interest_score(
        altdata_row={"convergence": 0.6, "side": "accumulate", "flags": []},
        special_flags={"unlock_large": True}, traj=traj)
    assert crowded["score"] < clean["score"]
    assert unlocked["score"] < clean["score"]


def test_rolling_over_applies_the_falsifier_haircut_once():
    record = CII.interest_score(
        altdata_row={"convergence": 0.6, "side": "accumulate"},
        special_flags={"unlock_large": True, "pledge_stress": True},
        traj={"off_high_pct": -30.0, "rs_20d": 1.0, "rolling_over": True})
    assert record["falsifier_penalty"] == 0.85
    assert len(record["falsifiers"]) >= 3   # several observations, ONE haircut


def test_leading_gap_has_no_lagging_board_term():
    """The board is the hub's second LAGGING desk; excluding it is the whole point."""
    record = CII.interest_score(
        altdata_row={"convergence": 0.6, "side": "accumulate"},
        radar_row={"sign": "positive", "strength": 0.5},
        traj={"off_high_pct": -30.0, "rs_20d": 1.0})
    assert record["lead_up"] == 2
    assert record["gap"] == 2
    assert record["gap_mult"] == pytest.approx(1.3)


def test_weak_convergence_is_its_own_falsifier():
    record = CII.interest_score(
        altdata_row={"convergence": 0.2, "side": "accumulate"},
        traj={"off_high_pct": -30.0, "rs_20d": 1.0})
    assert record["falsifier_penalty"] == 0.85


# ── Coverage receipt ──────────────────────────────────────────────────────── #

def test_coverage_reports_the_fallback_split_honestly():
    interest = {
        "A.SS": CII.interest_score(
            altdata_row={"convergence": 0.6, "side": "accumulate"},
            traj={"off_high_pct": -30.0, "rs_20d": 1.0}),
        "B.SS": CII.interest_score(),
        "C.SS": CII.interest_score(),
    }
    cov = CII.coverage(interest)
    assert cov["n_rows"] == 3
    assert cov["n_measured"] == 1
    assert cov["n_fallback_v3"] == 2
    assert cov["fallback_reasons"] == {"no_desk_evidence": 2}
    assert cov["measured_rate_pct"] == pytest.approx(33.3)


def test_build_interest_map_degrades_to_all_fallback_without_evidence():
    """Total evidence failure must order the board exactly as v3 would, not dark it."""
    result = CII.build_interest_map(
        ["AAA.SS", "BBB.SZ"], altdata_by={}, radar_by={}, special_by={}, traj_by={})
    assert set(result) == {"AAA.SS", "BBB.SZ"}
    assert all(r["basis"] == CII.BASIS_FALLBACK for r in result.values())


def test_build_interest_map_upper_cases_tickers():
    result = CII.build_interest_map(
        ["aaa.ss"],
        altdata_by={"AAA.SS": {"convergence": 0.6, "side": "accumulate"}},
        radar_by={}, special_by={}, traj_by={"AAA.SS": {"off_high_pct": -30.0}})
    assert result["AAA.SS"]["basis"] == CII.BASIS_MEASURED


def test_no_module_level_io_at_import_time():
    """Importing the scorer must not touch disk — it is a pure module with loaders."""
    tree = ast.parse(Path(CII.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        assert not isinstance(node, (ast.Expr, ast.With)) or isinstance(
            getattr(node, "value", None), ast.Constant
        ), "module-level statement performs work at import time"
