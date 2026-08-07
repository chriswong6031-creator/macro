"""OHLC basis-coherence guard — scripts/check_ohlc_basis_coherence.py.

Pins the 2026-08-06 incident class: the breadth ``_high_cache``/``_low_cache``
extras drifting onto a different yfinance adjustment basis than
``_closes_cache``, which no scanner in the tree can see (both
``BreadthAdapter._merge_refreshed`` and ``scripts/heal_breadth_split_seams.py``
run ``seam_suspects`` over the CLOSES matrix alone). Close-only consumers are
unaffected — which is what made it silent — while ATR's true range is dominated
by the basis gap.

Every assertion drives the REAL classifier/runner, never a re-implementation of
the rule: a mirrored predicate here would pass while the guard shipped broken.
Nothing asserts a verdict over the live committed caches (those advance nightly;
a value assertion over them is an assertion about today) — the one live-data test
pins that the reader survives the real schema, not what it finds.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_ohlc_basis_coherence.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_ohlc_basis_coherence", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load()

IDX = pd.date_range("2024-01-01", periods=60, freq="B")
BASE = pd.Series(100.0, index=IDX)


def _f(vals: dict, index=IDX) -> pd.DataFrame:
    return pd.DataFrame(vals, index=index)


def _panel(tmp_path: Path, name: str, closes, high, low) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    closes.to_parquet(d / "_closes_cache.parquet")
    high.to_parquet(d / "_high_cache.parquet")
    low.to_parquet(d / "_low_cache.parquet")
    return tmp_path


# ── classifier ────────────────────────────────────────────────────────────────

def test_coherent_panel_yields_no_findings():
    assert guard.classify(_f({"A": BASE}), _f({"A": BASE * 1.02}),
                          _f({"A": BASE * 0.98})) == []


def test_rezi_shape_is_a_split():
    """The reported signature: close 1.29-1.44x high on 773 of 773 bars."""
    out = guard.classify(_f({"REZI": BASE * 1.35}), _f({"REZI": BASE}),
                         _f({"REZI": BASE * 0.98}))
    assert [r["verdict"] for r in out] == ["split"]
    assert out[0]["bad_bars"] == 60 and out[0]["bad_share"] == 1.0
    assert out[0]["worst_excess"] == pytest.approx(0.35, abs=1e-3)


def test_isolated_bad_bar_stays_noise():
    """The ex-dividend rounding floor the panels genuinely carry (17 bars, worst
    2.5%, at 2026-08-06). Escalating these would make the guard a scheduled red."""
    high = BASE * 1.02
    high.iloc[3] = BASE.iloc[3] * 0.975
    out = guard.classify(_f({"N": BASE}), _f({"N": high}), _f({"N": BASE * 0.98}))
    assert [r["verdict"] for r in out] == ["noise"]
    assert out[0]["bad_bars"] == 1


def test_low_magnitude_whole_history_split_caught_by_share_limb():
    """A 3% basis drift never trips the 10% magnitude limb — the share limb is
    the only thing standing between it and a silent ship."""
    out = guard.classify(_f({"S": BASE * 1.03}), _f({"S": BASE}), _f({"S": BASE * 0.9}))
    assert [r["verdict"] for r in out] == ["split"]
    assert out[0]["worst_excess"] < guard.HARD_TOL


def test_share_limb_needs_min_bad_bars():
    """67% of six bars is not evidence of a basis; it is a thin column."""
    short = pd.date_range("2024-01-01", periods=6, freq="B")
    out = guard.classify(
        _f({"T": 100.0}, short),
        _f({"T": [99.0, 99.0, 99.0, 99.0, 101.0, 101.0]}, short),
        _f({"T": 90.0}, short))
    assert [r["verdict"] for r in out] == ["noise"]
    assert out[0]["bad_bars"] == 4 and out[0]["bad_share"] > guard.SHARE_TOL


def test_inverted_low_above_high_is_reported():
    out = guard.classify(_f({"I": BASE}), _f({"I": BASE * 0.90}), _f({"I": BASE * 1.10}))
    assert out and out[0]["inverted_bars"] == 60


def test_missing_cells_are_never_violations():
    """high/low are forward-accruing (median 55 bars vs 777 closes) — the guard
    must judge only the all-present cells, or every panel reds on coverage."""
    closes = BASE.copy()
    closes.iloc[:30] = float("nan")
    assert guard.classify(_f({"A": closes}), _f({"A": BASE * 1.02}),
                          _f({"A": BASE * 0.98})) == []


def test_disjoint_columns_do_not_crash():
    assert guard.classify(_f({"A": BASE}), _f({"B": BASE}), _f({"C": BASE})) == []


# ── runner: exit codes, annotations, marker ──────────────────────────────────

def test_clean_panel_exits_zero_and_writes_marker(tmp_path, capsys):
    data = _panel(tmp_path, "breadth", _f({"A": BASE}), _f({"A": BASE * 1.02}),
                  _f({"A": BASE * 0.98}))
    assert guard.run(data) == 0
    assert "::error" not in capsys.readouterr().out
    marker = json.loads((data / "quality" / "ohlc_basis_coherence.json").read_text())
    assert marker["status"] == "coherent" and marker["splits"] == 0


def test_split_exits_three_with_error_annotation(tmp_path, capsys):
    data = _panel(tmp_path, "smallcap_breadth", _f({"REZI": BASE * 1.35}),
                  _f({"REZI": BASE}), _f({"REZI": BASE * 0.98}))
    assert guard.run(data) == 3
    out = capsys.readouterr().out
    assert "::error title=ohlc-basis-split::" in out
    assert "REZI" in out and "heal_breadth_split_seams" in out
    marker = json.loads((data / "quality" / "ohlc_basis_coherence.json").read_text())
    assert marker["status"] == "split" and marker["splits"] == 1


def test_noise_annotates_warning_but_does_not_gate(tmp_path, capsys):
    high = BASE * 1.02
    high.iloc[3] = BASE.iloc[3] * 0.975
    data = _panel(tmp_path, "midcap_breadth", _f({"N": BASE}), _f({"N": high}),
                  _f({"N": BASE * 0.98}))
    assert guard.run(data) == 0
    out = capsys.readouterr().out
    assert "::warning title=ohlc-basis-noise::" in out and "::error" not in out


def test_every_annotation_starts_its_line(tmp_path, capsys):
    """CLAUDE.md: an annotation emitted through a logger is prefixed and GitHub
    silently drops it. This pins the bare-print form for BOTH tiers at once."""
    noisy = BASE * 1.02
    noisy.iloc[3] = BASE.iloc[3] * 0.975
    data = _panel(tmp_path, "breadth", _f({"N": BASE, "R": BASE * 1.35}),
                  _f({"N": noisy, "R": BASE}), _f({"N": BASE * 0.98, "R": BASE * 0.98}))
    assert guard.run(data) == 3
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert lines, "guard emitted no annotations"
    assert [ln for ln in lines if ln.startswith("::error")]
    assert [ln for ln in lines if ln.startswith("::warning")]
    for ln in lines:
        assert ln.startswith("::"), f"annotation not at line start: {ln!r}"


def test_unreadable_panel_is_skipped_not_fatal(tmp_path, capsys):
    d = tmp_path / "breadth"
    d.mkdir(parents=True)
    for f in ("closes", "high", "low"):
        (d / f"_{f}_cache.parquet").write_bytes(b"not a parquet file")
    assert guard.run(tmp_path) == 0
    assert "::warning title=ohlc-basis-coherence::" in capsys.readouterr().out


def test_no_panels_warns_rather_than_silently_passing(tmp_path, capsys):
    assert guard.run(tmp_path) == 0
    assert "no breadth panel" in capsys.readouterr().out


# ── discovery + selftest + live schema ───────────────────────────────────────

def test_discovery_requires_the_full_triple(tmp_path):
    partial = tmp_path / "half"
    partial.mkdir()
    _f({"A": BASE}).to_parquet(partial / "_closes_cache.parquet")
    _f({"A": BASE}).to_parquet(partial / "_high_cache.parquet")
    _panel(tmp_path, "whole", _f({"A": BASE}), _f({"A": BASE}), _f({"A": BASE}))
    assert guard.discover_panels(tmp_path) == ["whole"]


def test_selftest_passes():
    assert guard._selftest() == 0


def test_discovery_finds_the_real_us_breadth_panels():
    """Structure, not values: if a panel is renamed or an extras store stops
    shipping, the guard must not quietly narrow to nothing."""
    found = guard.discover_panels(ROOT / "data")
    assert {"breadth", "midcap_breadth", "smallcap_breadth"} <= set(found)


def test_guard_survives_the_live_committed_caches():
    """Reader-level pin only. The verdict is deliberately not asserted — these
    caches advance nightly, so asserting one would assert about today."""
    assert guard.run(ROOT / "data") in (0, 3)
