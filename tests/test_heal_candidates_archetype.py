"""Archetype coverage pipeline: fac-less classification, store freshness, stamp heal.

Pins the three legs of the 2026-08 archetype-coverage fix (1,625/2,932 candidates
NaN, MCD included):

  (1) _archetype fac-less path — names with EDGAR panel coverage but no
      factor-table row classify through the ni-veto + anchored PIT buckets, and
      must NEVER read "mixed" (that label claims factors were measured).
  (2) archetypes_history_refresh_if_stale — the derived store follows the
      panel's (ticker, fy) key set mechanically; the frozen-store rot mode
      (built 2026-07-03, panel kept growing) cannot recur silently. Failure
      prints a line-start ::warning (annotation law) and keeps the last store.
  (3) scripts/heal_candidates_archetype — fill-null-only PIT re-join at each
      row's OWN stamp_date; labeled rows and still-unresolvable receipts are
      byte-for-byte untouched; a second run is a no-op.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from engine import stock_fundamentals as SF
from scripts.heal_candidates_archetype import heal_part


# ---------------------------------------------------------------------------
# (1) fac-less classification
# ---------------------------------------------------------------------------

def test_facless_unprofitable_veto_fires():
    a = SF._archetype(None, ni=-50.0, net_margin=None, nm_top_thr=None)
    assert a is not None and a["key"] == "speculative_unprofitable"


def test_facless_anchored_buckets_fire():
    my_d = {"altman": {"z": 1.2, "zone": "distress", "approx": False}}
    assert SF._archetype({}, ni=10.0, net_margin=None, nm_top_thr=None,
                         my=my_d)["key"] == "distressed"
    assert SF._archetype(None, ni=10.0, net_margin=None, nm_top_thr=None,
                         betas={"rates": 0.7, "raw": {}})["key"] == "rate_sensitive"
    my_sg = {"rev_cagr": 20.0, "eps_cagr": 15.0}
    assert SF._archetype(None, ni=10.0, net_margin=None, nm_top_thr=None,
                         my=my_sg)["key"] == "secular_growth"


def test_facless_never_reads_mixed():
    # nothing anchored fires -> None (honestly unlabeled), never "mixed"
    assert SF._archetype(None, ni=10.0, net_margin=5.0, nm_top_thr=30.0) is None
    assert SF._archetype({}, ni=None, net_margin=None, nm_top_thr=None) is None
    # fac-present mixed unchanged
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    assert SF._archetype(base, 10, 5, 30)["key"] == "mixed"


# ---------------------------------------------------------------------------
# (2) archetypes_history_refresh_if_stale
# ---------------------------------------------------------------------------

def _write_keys(path: Path, keys: list[tuple[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": t, "fy": y, "archetype": "mixed"} for t, y in keys]) \
        .to_parquet(path, index=False)


def test_refresh_noop_when_keysets_match(tmp_path):
    panel, hist = tmp_path / "panel.parquet", tmp_path / "hist.parquet"
    _write_keys(panel, [("MCD", 2024), ("MCD", 2025)])
    _write_keys(hist, [("MCD", 2025), ("MCD", 2024)])
    calls = []
    assert SF.archetypes_history_refresh_if_stale(
        panel, hist, rebuild=lambda out_path=None: calls.append(out_path)) is False
    assert not calls, "fresh store must not rebuild"


def test_refresh_rebuilds_on_panel_growth_and_missing_store(tmp_path):
    panel, hist = tmp_path / "panel.parquet", tmp_path / "hist.parquet"
    _write_keys(panel, [("MCD", 2024), ("MCD", 2025)])
    _write_keys(hist, [("MCD", 2024)])
    calls = []

    def rebuild(out_path=None):
        calls.append(out_path)
        return pd.DataFrame({"ticker": ["MCD"]})

    assert SF.archetypes_history_refresh_if_stale(panel, hist, rebuild=rebuild) is True
    assert calls == [hist]
    hist.unlink()
    assert SF.archetypes_history_refresh_if_stale(panel, hist, rebuild=rebuild) is True
    assert len(calls) == 2, "missing store must rebuild"
    # orphaned history keys (panel shrank) also count as stale
    _write_keys(hist, [("MCD", 2024), ("MCD", 2025), ("GONE", 2020)])
    assert SF.archetypes_history_refresh_if_stale(panel, hist, rebuild=rebuild) is True


def test_refresh_failure_prints_line_start_warning(tmp_path):
    panel, hist = tmp_path / "panel.parquet", tmp_path / "hist.parquet"
    _write_keys(panel, [("MCD", 2025)])

    def boom(out_path=None):
        raise RuntimeError("synthetic")

    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = SF.archetypes_history_refresh_if_stale(panel, hist, rebuild=boom)
    assert ok is False
    lines = [ln for ln in buf.getvalue().splitlines() if "::warning" in ln]
    assert lines and lines[0].startswith("::warning"), \
        "annotation must START the line (GH drops logger-prefixed annotations)"


def test_refresh_missing_panel_is_not_stale(tmp_path):
    calls = []
    assert SF.archetypes_history_refresh_if_stale(
        tmp_path / "absent.parquet", tmp_path / "hist.parquet",
        rebuild=lambda out_path=None: calls.append(out_path)) is False
    assert not calls


# ---------------------------------------------------------------------------
# (3) heal_candidates_archetype
# ---------------------------------------------------------------------------

def _candidates_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A repo-root shaped tmp dir: PIT store + one candidates part.

    Rows: MCD  — absent at stamp time, PIT row now resolves -> must fill.
          AAPL — already labeled -> must stay byte-identical.
          ZZZZ — still no history -> receipt must stay untouched.
    """
    root = tmp_path
    _hist = root / "data" / "archetypes" / "history.parquet"
    _hist.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": "MCD", "fy": 2025, "asof_date": "2026-04-30",
         "archetype": "cyclical", "confidence": 0.83},
        {"ticker": "MCD", "fy": 2024, "asof_date": "2025-04-30",
         "archetype": "cyclical", "confidence": 0.83},
        # a row NEWER than the stamp: the PIT join must ignore it
        {"ticker": "ZZZZ", "fy": 2026, "asof_date": "2026-09-30",
         "archetype": "mixed", "confidence": 0.5},
    ]).to_parquet(_hist, index=False)

    part = root / "candidates" / "2026-07.parquet"
    part.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": "MCD", "stamp_date": "2026-07-31", "archetype__absent": True,
         "archetype__as_of": None, "archetype__basis": None,
         "archetype__archetype": None, "archetype__confidence": None,
         "archetype__fy": None, "archetype__reason": "no archetype history for MCD"},
        {"ticker": "AAPL", "stamp_date": "2026-07-31", "archetype__absent": False,
         "archetype__as_of": "2026-04-30", "archetype__basis": "pit_labels",
         "archetype__archetype": "quality_compounder", "archetype__confidence": 0.9,
         "archetype__fy": 2025, "archetype__reason": None},
        {"ticker": "ZZZZ", "stamp_date": "2026-07-31", "archetype__absent": True,
         "archetype__as_of": None, "archetype__basis": None,
         "archetype__archetype": None, "archetype__confidence": None,
         "archetype__fy": None, "archetype__reason": "no archetype history for ZZZZ"},
    ]).to_parquet(part, index=False)
    return root, part


def test_heal_fills_only_resolvable_nulls(tmp_path):
    root, part = _candidates_fixture(tmp_path)
    r = heal_part(part, root=root, write=True)
    assert (r["null_before"], r["filled"], r["still_absent"], r["null_after"]) == (2, 1, 1, 1)

    df = pd.read_parquet(part).set_index("ticker")
    assert df.at["MCD", "archetype__archetype"] == "cyclical"
    assert df.at["MCD", "archetype__absent"] == False  # noqa: E712 — parquet round-trip value
    assert df.at["MCD", "archetype__as_of"] == "2026-04-30"
    assert df.at["MCD", "archetype__basis"] == "pit_labels"
    assert pd.isna(df.at["MCD", "archetype__reason"])
    # labeled row untouched
    assert df.at["AAPL", "archetype__archetype"] == "quality_compounder"
    # unresolvable receipt untouched (its only history row post-dates the stamp)
    assert pd.isna(df.at["ZZZZ", "archetype__archetype"])
    assert df.at["ZZZZ", "archetype__reason"] == "no archetype history for ZZZZ" or \
        "asof_date" in str(df.at["ZZZZ", "archetype__reason"])


def test_heal_is_idempotent_and_dry_run_writes_nothing(tmp_path):
    root, part = _candidates_fixture(tmp_path)
    before = part.read_bytes()
    r_dry = heal_part(part, root=root, write=False)
    assert r_dry["filled"] == 1 and part.read_bytes() == before, "dry-run must not write"
    heal_part(part, root=root, write=True)
    healed = part.read_bytes()
    r2 = heal_part(part, root=root, write=True)
    assert r2["filled"] == 0 and part.read_bytes() == healed, "second run must be a no-op"
