"""The stretch/extension oracle disclosure contract.

Contract: docs/site_semantics/stretch_oracles.md

`ladder.alignment.overextended` is a 4-leg OR in which THREE legs are fast oscillators
and only one is distance-above-the-200-day. Consumers that had only the boolean narrated
the distance as its cause — printing a "Stretched" chip above a sentence reading
"about 9% BELOW its 200-day line". These tests pin the fix: the boolean is derived from
the named legs, so the brake and its disclosed cause cannot drift apart, and the checker
that enforces it can actually FAIL (each invariant gets a mutated fixture).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.cycles import (  # noqa: E402
    _EG_DAILY_RSI_MAX,
    _EG_OSC_EXEMPT_BELOW,
    _EG_STOCH_OB,
    _EG_STRETCH_BLOCK,
    OVEREXTENSION_LEG_RSI_D,
    OVEREXTENSION_LEG_STOCH_3D,
    OVEREXTENSION_LEG_STOCH_D,
    OVEREXTENSION_LEG_STRETCH,
    _overextended,
    _overextension_legs,
    mtf_alignment,
    overextension_basis,
)
from scripts.check_stretch_oracle_contract import check  # noqa: E402


def _mtf(d_stoch=10.0, t3_stoch=10.0, d_rsi=40.0):
    return {
        "D": {"stoch": d_stoch, "rsi14": d_rsi, "macd_pos": True, "macd_cross_up": True},
        "3D": {"stoch": t3_stoch, "rsi14": 50.0},
        "W": {"stoch": 50.0, "rsi14": 50.0},
    }


# --------------------------------------------------------------------------
# producer: the boolean IS the legs
# --------------------------------------------------------------------------

_GRID = [
    (d, t3, r, e)
    for d in (10.0, 85.0, None)
    for t3 in (10.0, 85.0, None)
    for r in (40.0, 70.0, None)
    for e in (None, -40.0, -12.0, -5.0, 0.0, 12.0, 35.0)
]


@pytest.mark.parametrize("d_stoch,t3_stoch,d_rsi,ext_pct", _GRID)
def test_overextended_is_exactly_bool_of_legs(d_stoch, t3_stoch, d_rsi, ext_pct):
    """The brake and its disclosed cause are ONE evaluation — they cannot disagree."""
    mtf = _mtf(d_stoch, t3_stoch, d_rsi)
    assert _overextended(mtf, ext_pct) is bool(_overextension_legs(mtf, ext_pct))


def test_matches_the_pre_disclosure_implementation():
    """Value-identity with the original short-circuiting OR, over the same grid.

    This is the regression that matters: the disclosure refactor must not have moved a
    single flag, because `overextended` gates standout-strip SELECTION (authority tier).
    """
    def original(mtf, ext_pct=None):
        d = mtf.get("D") or {}
        if not (ext_pct is not None and ext_pct <= _EG_OSC_EXEMPT_BELOW):
            for tf in (d, mtf.get("3D") or {}):
                st = tf.get("stoch")
                if st is not None and st > _EG_STOCH_OB:
                    return True
            rsi = d.get("rsi14")
            if rsi is not None and rsi > _EG_DAILY_RSI_MAX:
                return True
        return bool(ext_pct is not None and ext_pct >= _EG_STRETCH_BLOCK)

    for d_stoch, t3_stoch, d_rsi, ext_pct in _GRID:
        mtf = _mtf(d_stoch, t3_stoch, d_rsi)
        assert _overextended(mtf, ext_pct) == original(mtf, ext_pct), (
            d_stoch, t3_stoch, d_rsi, ext_pct)


def test_legs_are_named_from_the_vocabulary():
    legs = _overextension_legs(_mtf(d_stoch=85.0, t3_stoch=85.0, d_rsi=70.0), ext_pct=35.0)
    assert legs == [
        OVEREXTENSION_LEG_STOCH_D,
        OVEREXTENSION_LEG_STOCH_3D,
        OVEREXTENSION_LEG_RSI_D,
        OVEREXTENSION_LEG_STRETCH,
    ]


def test_oscillator_exempt_below_suppresses_only_the_oscillator_legs():
    """#2509: deep below the 200-day, range compression pins StochRSI — osc legs off.
    The distance leg is unreachable there, so it is unaffected."""
    hot = _mtf(d_stoch=95.0, t3_stoch=95.0, d_rsi=75.0)
    assert _overextension_legs(hot, ext_pct=_EG_OSC_EXEMPT_BELOW - 1.0) == []
    assert _overextension_legs(hot, ext_pct=_EG_OSC_EXEMPT_BELOW + 1.0)
    # ext_pct=None (the ladder de-escalation caller) keeps the legacy behaviour
    assert OVEREXTENSION_LEG_STOCH_D in _overextension_legs(hot, ext_pct=None)
    assert OVEREXTENSION_LEG_STRETCH not in _overextension_legs(hot, ext_pct=None)


def test_basis_never_licenses_distance_prose_for_an_oscillator_flag():
    """The RIVN case: flagged at +8.9% above the 200-day, where the distance leg
    (>= +30%) cannot possibly have fired. The basis must say so."""
    al = mtf_alignment(_mtf(d_stoch=97.0, d_rsi=58.0), ext_pct=8.9)
    assert al["overextended"] is True
    assert al["overextended_legs"] == [OVEREXTENSION_LEG_STOCH_D]
    assert al["overextended_basis"] == "oscillator"
    assert al["ext_pct_used"] == 8.9


@pytest.mark.parametrize("legs,want", [
    ([], None),
    (None, None),
    ([OVEREXTENSION_LEG_STOCH_D], "oscillator"),
    ([OVEREXTENSION_LEG_RSI_D], "oscillator"),
    ([OVEREXTENSION_LEG_STRETCH], "stretch"),
    ([OVEREXTENSION_LEG_STOCH_3D, OVEREXTENSION_LEG_STRETCH], "both"),
])
def test_basis_classification(legs, want):
    assert overextension_basis(legs) == want


def test_alignment_emits_the_contract_fields():
    al = mtf_alignment(_mtf(), ext_pct=1.0)
    for key in ("overextended", "overextended_legs", "overextended_basis", "ext_pct_used"):
        assert key in al, f"alignment dropped the contract field {key}"


# --------------------------------------------------------------------------
# the checker can actually FAIL — one mutated fixture per invariant
# --------------------------------------------------------------------------

def _store(tmp_path: Path, *rows: dict) -> Path:
    d = tmp_path / "stockdata"
    d.mkdir(exist_ok=True)
    for i, al in enumerate(rows):
        (d / f"T{i}.json").write_text(json.dumps({
            "ticker": f"T{i}", "asof": "2026-08-13",
            "ladder": {"alignment": al},
            "entry_signal": {"status": "buy_now"},
            "tech": {"pct_vs_200dma": 8.9},
        }))
    return d


_CLEAN = {"overextended": True, "overextended_legs": [OVEREXTENSION_LEG_STOCH_D],
          "overextended_basis": "oscillator", "ext_pct_used": 8.9}


def test_clean_store_passes(tmp_path):
    code, viol, stats = check(_store(tmp_path, _CLEAN))
    assert code == 0, viol
    assert stats["n_contract"] == 1


@pytest.mark.parametrize("mutation,marker", [
    ({"overextended_legs": []}, "I1"),                                    # flagged, no cause
    ({"overextended": False}, "I2"),                                      # cause, not flagged
    ({"overextended_basis": "stretch"}, "I3"),                            # basis contradicts legs
    ({"ext_pct_used": _EG_STRETCH_BLOCK + 5}, "I4"),                      # distance leg missed
    ({"overextended_legs": ["made_up_leg"]}, "unknown leg"),
])
def test_each_invariant_can_fail(tmp_path, mutation, marker):
    """A guard that cannot fail is not a guard — mutate the artifact, expect exit 1."""
    row = {**_CLEAN, **mutation}
    code, viol, _ = check(_store(tmp_path, row))
    assert code == 1, f"mutation {mutation} slipped through the contract"
    assert any(marker in v for v in viol), viol


def test_precontract_store_warns_but_passes_unless_strict(tmp_path):
    """A store baked before the fields existed must not red CI — but it must be loud,
    and --strict must refuse it (the vintage trap this contract exists to close)."""
    old = {"overextended": True}
    store = _store(tmp_path, old)
    assert check(store, strict=False)[0] == 0
    assert check(store, strict=True)[0] == 1


def test_empty_store_is_exit_2(tmp_path):
    d = tmp_path / "stockdata"
    d.mkdir()
    assert check(d)[0] == 2


def test_annotations_start_the_line(tmp_path, capsys):
    """House law: `::notice`/`::warning` must START the line or GitHub drops them
    silently (tests/test_gh_annotation_line_start.py swept 69 sites for this)."""
    from scripts.check_stretch_oracle_contract import main
    main(["prog", str(_store(tmp_path, _CLEAN))])
    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if "::notice" in ln or "::warning" in ln]
    assert ann, "no annotation emitted"
    for ln in ann:
        assert ln.startswith("::"), f"annotation does not start the line: {ln!r}"


def test_checker_cli_runs_clean_on_a_good_store(tmp_path):
    store = _store(tmp_path, _CLEAN)
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_stretch_oracle_contract.py"), str(store)],
        capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "stretch-oracle-divergence" in r.stdout
