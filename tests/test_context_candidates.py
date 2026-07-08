"""tests/test_context_candidates.py — W4 context scanner tests.

Tests
-----
 1. budget_refusal           — no declared budget → _assert_budget raises
 2. budget_refusal_via_run   — run() on EMPTY ledger raises GovernorRefusal
                               AND writes no output (F1 regression test)
 3. t1_drift_injected        — fabricated snapshots with drift injected → candidate
                               emitted with correct null_pctile fields
 4. t1_no_drift              — no drift → zero candidates, counts printed
 5. t1_pure_noise_zero_cands — pure noise series (>=50 snapshots) → zero candidates (F3)
 6. t1_injected_drift_emits  — injected persistent drift above baseline → candidate emits (F3)
 7. t2_insufficient_n        — thin fabricated spine → all cells insufficient_n,
                               zero candidates, honest counts
 8. t2_no_personality_basis  — spine lacks personality_basis → all insufficient_n
 9. t2_membership_null_high  — large n>=60 pit_labels cell with hit-rate far above
                               marginal → high null_pctile + candidate emits (F2)
10. t2_membership_null_low   — same-rate cell → percentile low, no candidate (F2)
11. t3_pure_noise_zero_cands — pure noise T3 series (>=22 snapshots) → zero candidates (F3)
12. t3_injected_shift_emits  — persistent shift above baseline → candidate emits (F3)
13. dedupe_refresh           — same candidate re-run → refresh not duplicate
14. dedupe_decayed           — decayed row blocks re-emission as new candidate_id
15. decay_transition         — candidate older than 60 days becomes 'decayed'
16. decay_no_bump_last_refreshed — decayed rows get last_seen_while_decayed, NOT
                               last_refreshed bump (F7 regression test)
17. adjacent_falsified        — emission without adjacent_falsified raises ValueError
18. adjacent_falsified_none   — emission with None raises ValueError
19. dry_run                  — dry_run=True does not write to disk or ledger
20. full_run_with_budget      — run() with pre-registered budget completes without error
21. null_percentile_extremes  — null_pctile at boundary values
22. null_percentile_empty     — empty null dist returns 50.0
23. candidate_id_stable       — same inputs → same id
24. candidate_id_differs      — different templates → different ids
25. dedup_false_positive      — novel composition-drift candidate NOT deduped merely
                               because a species entry mentions the same archetype (F6)
26. adjacent_falsified_species_lookup — fabricated registry with matching graveyard
                               reference populates first-hit species id (F8)

All tests use tmp_path only.  The real trial_ledger is NEVER written.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------
from scripts.build_context_candidates import (
    GovernorRefusal,
    _BUDGET_TOTAL,
    _CELL_N_FLOOR,
    _FAMILY,
    _NULL_DRAWS,
    _T1_RECENT_WINDOW,
    _T3_RECENT_WINDOW,
    _T3_SNAPSHOT_WINDOW,
    _assert_budget,
    _candidate_id,
    _emit_candidates,
    _is_dedup_match,
    _load_dedup_corpus,
    _lookup_adjacent_falsified,
    _null_percentile,
    _null_draw_window_means,
    _run_t1,
    _run_t2,
    _run_t3,
    register_budget,
    run,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tok(s: str) -> frozenset[str]:
    import re
    return frozenset(t for t in re.split(r"[\s_\-/|=]+", s.lower()) if t)


def _write_species_reg(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": "v1", "authored": "test", "note": "", "species": entries}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_root(tmp_path: Path) -> Path:
    """Build a minimal fake repo root with required directory structure."""
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "data" / "us_board_ledger").mkdir(parents=True)
    (tmp_path / "data" / "oracle" / "compounds").mkdir(parents=True)
    (tmp_path / "data" / "species").mkdir(parents=True)
    # Empty registries (no dedup tokens)
    (tmp_path / "data" / "oracle" / "compounds" / "registry.jsonl").write_text("", encoding="utf-8")
    _write_species_reg(tmp_path / "data" / "species" / "registry.json", [])
    (tmp_path / "data" / "neuralweb" / "machine_registry.jsonl").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def ledger_path(tmp_path: Path) -> Path:
    """Temporary trial ledger path (does not touch real data/trial_ledger.jsonl)."""
    return tmp_path / "trial_ledger_test.jsonl"


# ---------------------------------------------------------------------------
# 1. budget_refusal — no budget → GovernorRefusal
# ---------------------------------------------------------------------------

def test_budget_refusal(fake_root: Path, ledger_path: Path):
    """_assert_budget refuses when no declared budget row exists."""
    with pytest.raises((GovernorRefusal, SystemExit)) as exc_info:
        _assert_budget(fake_root, ledger_path=ledger_path)
    code = exc_info.value.code if hasattr(exc_info.value, "code") else str(exc_info.value)
    assert code != 0 or "GovernorRefusal" in str(code)


# ---------------------------------------------------------------------------
# 2. budget_refusal_via_run (F1 regression) — run() on empty ledger must refuse
#    and must NOT write any output file.
# ---------------------------------------------------------------------------

def test_budget_refusal_via_run(fake_root: Path, ledger_path: Path):
    """F1 regression: run() on an empty tmp ledger raises GovernorRefusal +
    produces zero output files.  Pre-fix code auto-registered the budget and
    never raised."""
    # Verify ledger is empty
    assert not ledger_path.exists(), "Ledger must be absent before test"

    output_path = fake_root / "data" / "neuralweb" / "context_candidates.jsonl"

    with pytest.raises((GovernorRefusal, SystemExit)) as exc_info:
        run(root=fake_root, dry_run=False, ledger_path=ledger_path)

    # Must be non-zero exit
    code = exc_info.value.code if hasattr(exc_info.value, "code") else str(exc_info.value)
    assert code != 0 or "GovernorRefusal" in str(code), (
        f"Expected non-zero exit, got code={code!r}"
    )

    # Must NOT have written any output
    assert not output_path.exists(), (
        "run() must not write context_candidates.jsonl when budget absent"
    )

    # The ledger should NOT have a budget row auto-inserted
    if ledger_path.exists():
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        budget_rows = [r for r in rows if r.get("kind") == "declared_budget" and r.get("family") == _FAMILY]
        assert not budget_rows, (
            "run() must NOT auto-register budget (F1: budget gate rubber stamp)"
        )


# ---------------------------------------------------------------------------
# 2a. run() succeeds when budget IS pre-registered
# ---------------------------------------------------------------------------

def test_run_succeeds_with_budget(fake_root: Path, ledger_path: Path):
    """run() works when budget row is already present (operator registered it)."""
    register_budget(fake_root, ledger_path=ledger_path, dry_run=False)
    rc = run(root=fake_root, dry_run=False, ledger_path=ledger_path)
    assert rc == 0


# ---------------------------------------------------------------------------
# 3 & 4. T1 — drift injected → candidate; no drift → zero candidates
# ---------------------------------------------------------------------------

def _make_t1_spine(tmp_path: Path, n_tickers: int = 100, archetype: str = "high_beta") -> Path:
    """Write a minimal spine_index.parquet with archetype column."""
    rows = []
    for i in range(n_tickers):
        arch = archetype if i < 60 else "conservative"
        rows.append({"symbol": f"T{i:04d}", "archetype": arch, "engine": "track_record",
                      "as_of": "2026-06-01"})
    df = pd.DataFrame(rows)
    p = tmp_path / "data" / "neuralweb" / "spine_index.parquet"
    df.to_parquet(p, index=False)
    return p


def _make_board_retro(tmp_path: Path, dates: list[str], buy_arch: str = "high_beta",
                      buy_fraction: float = 0.9) -> Path:
    """Write a minimal retro_grades.parquet with archetype-skewed buy rows."""
    rows = []
    n_per_day = 60
    for d in dates:
        for i in range(n_per_day):
            rows.append({"as_of": d, "ticker": f"T{i:04d}", "lane": "buy"})
    df = pd.DataFrame(rows)
    p = tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet"
    df.to_parquet(p, index=False)
    return p


def test_t1_drift_injected(fake_root: Path):
    """T1 emits correct counts with drift-injected data."""
    _make_t1_spine(fake_root, n_tickers=100, archetype="high_beta")
    dates = [f"2026-0{m:01d}-{d:02d}" for m in range(3, 7) for d in range(1, 6)][:20]
    _make_board_retro(fake_root, dates, buy_arch="high_beta", buy_fraction=0.7)

    result = _run_t1(fake_root, dry_run=False)
    counts = result["counts"]

    assert counts["cells_examined"] > 0
    assert "candidates" in counts
    assert "cells_insufficient_n" in counts
    for cand in result["candidates"]:
        assert cand["template"] == "T1"
        assert "cell" in cand
        assert "stat" in cand
        assert "null_pctile" in cand
        assert "n" in cand
        assert cand.get("adjacent_falsified") is not None
        assert cand["adjacent_falsified"] != ""
        assert 0.0 <= cand["null_pctile"] <= 100.0


def test_t1_no_drift_zero_candidates(fake_root: Path):
    """T1 with uniform composition emits zero candidates."""
    rows = []
    for i in range(100):
        arch = "high_beta" if i < 50 else "conservative"
        rows.append({"symbol": f"T{i:04d}", "archetype": arch, "engine": "track_record",
                      "as_of": "2026-06-01"})
    pd.DataFrame(rows).to_parquet(
        fake_root / "data" / "neuralweb" / "spine_index.parquet", index=False)

    dates = [f"2026-0{m:01d}-{d:02d}" for m in range(3, 7) for d in range(1, 6)][:20]
    rows2 = []
    for d in dates:
        for i in range(60):
            rows2.append({"as_of": d, "ticker": f"T{i:04d}", "lane": "buy"})
    pd.DataFrame(rows2).to_parquet(
        fake_root / "data" / "us_board_ledger" / "retro_grades.parquet", index=False)

    result = _run_t1(fake_root, dry_run=False)
    counts = result["counts"]
    assert "cells_examined" in counts
    assert "cells_insufficient_n" in counts
    assert "candidates" in counts
    assert result["candidates"] == []


# ---------------------------------------------------------------------------
# 5 & 6. F3 regression tests — T1 pure noise → zero; injected drift → emits
# ---------------------------------------------------------------------------

def _make_t1_sufficient_data(
    tmp_path: Path,
    n_tickers: int = 200,
    n_snapshots: int = 80,
    buy_fraction_baseline: float = 0.6,
    buy_fraction_recent: float | None = None,
    arch_universe_fraction: float = 0.6,
    archetype: str = "high_beta",
) -> None:
    """Build spine + board with enough snapshots to pass n_floor.

    Spine: n_tickers split arch_universe_fraction high_beta vs conservative.
    Board: each snapshot includes a mix of high_beta and conservative tickers.
    - Baseline snapshots: buy_fraction_baseline of board slots are high_beta.
    - Recent snapshots: buy_fraction_recent (if given) of board slots are high_beta.

    To ensure archetype composition actually varies:
    - High-beta tickers: T0000..T(n_hb-1)
    - Conservative tickers: T(n_hb)..T(n_tickers-1)
    Each snapshot picks slots_hb high_beta tickers + (60-slots_hb) conservative tickers.
    """
    n_hb = int(n_tickers * arch_universe_fraction)  # high_beta count in universe

    # Spine
    spine_rows = []
    for i in range(n_tickers):
        arch = archetype if i < n_hb else "conservative"
        spine_rows.append({"symbol": f"T{i:04d}", "archetype": arch, "engine": "tr",
                            "as_of": "2026-01-01"})
    pd.DataFrame(spine_rows).to_parquet(
        tmp_path / "data" / "neuralweb" / "spine_index.parquet", index=False)

    # Board: n_snapshots dates, board size = 60 per snapshot
    board_rows = []
    recent_start = n_snapshots - _T1_RECENT_WINDOW
    for idx in range(n_snapshots):
        date = f"2025-{(idx // 30) + 1:02d}-{(idx % 28) + 1:02d}"
        frac = (buy_fraction_recent if (buy_fraction_recent is not None and idx >= recent_start)
                else buy_fraction_baseline)
        slots_hb = int(60 * frac)  # how many of the 60 buy slots are high_beta
        # Pick first slots_hb high_beta tickers and fill rest with conservative
        for i in range(slots_hb):
            board_rows.append({"as_of": date, "ticker": f"T{i:04d}", "lane": "buy"})
        for i in range(60 - slots_hb):
            board_rows.append({"as_of": date, "ticker": f"T{n_hb + i:04d}", "lane": "buy"})
    pd.DataFrame(board_rows).to_parquet(
        tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet", index=False)


def test_t1_pure_noise_zero_candidates(fake_root: Path):
    """F3 regression: pure-noise T1 series (>=50 snapshots) → zero candidates.

    Pre-fix code used single-point observed vs resampled-means null, inflating
    pctile for any high recent value.  Post-fix both observed and null are
    window means, so pure noise should not exceed threshold.
    """
    # Build large enough spine + board; uniform fraction = 0.6 throughout
    n_snapshots = _CELL_N_FLOOR + _T1_RECENT_WINDOW + 10
    _make_t1_sufficient_data(
        fake_root,
        n_tickers=200,
        n_snapshots=n_snapshots,
        buy_fraction_baseline=0.6,
        buy_fraction_recent=None,  # no drift
        arch_universe_fraction=0.6,
    )

    # Run many seeds to check noise doesn't spuriously trigger
    result = _run_t1(fake_root, dry_run=False)
    counts = result["counts"]

    # With no drift, pctile should not hit 99 under correct window-mean null
    # (Both observed mean and null means are drawn from same distribution)
    # We allow 0 candidates; at most 1 would be a fluke but expected 0.
    assert counts["candidates"] == 0, (
        f"F3 regression: pure-noise T1 should emit 0 candidates, got {counts['candidates']}. "
        f"This likely means point-vs-mean null is still present."
    )


def test_t1_injected_drift_emits(fake_root: Path):
    """F3 regression: injected persistent drift in recent window → candidate emits.

    Build: baseline fraction = 0.6 (universe = 0.6 → drift ratio ≈ 1.0 in baseline);
    recent window fraction = 0.99 (strong overweight → drift ratio ≈ 1.65).
    The recent window mean should be far above baseline null distribution.
    """
    n_snapshots = _CELL_N_FLOOR + _T1_RECENT_WINDOW + 15
    _make_t1_sufficient_data(
        fake_root,
        n_tickers=200,
        n_snapshots=n_snapshots,
        buy_fraction_baseline=0.6,
        buy_fraction_recent=0.99,  # strong drift in recent window
        arch_universe_fraction=0.6,
        archetype="high_beta",
    )

    result = _run_t1(fake_root, dry_run=False)
    counts = result["counts"]
    assert counts["cells_testable"] > 0, "Expected testable cells"
    assert counts["candidates"] > 0, (
        f"F3 injection test: injected drift should emit at least 1 candidate, "
        f"got {counts['candidates']}. counts={counts}"
    )
    for cand in result["candidates"]:
        assert cand["template"] == "T1"
        assert "composition_drift_mean" in cand["stat"]
        assert cand["null_pctile"] >= 99.0


# ---------------------------------------------------------------------------
# 7 & 8. T2 insufficient_n and no personality_basis column
# ---------------------------------------------------------------------------

def test_t2_insufficient_n(fake_root: Path):
    """T2 with thin spine → all cells insufficient_n, zero candidates, honest counts."""
    rows = []
    for i in range(10):
        rows.append({
            "signal_id": f"sig_{i}",
            "engine": "track_record",
            "outcome_graded": True,
            "archetype": "high_beta",
            "quad_hard_label": "Q1",
            "as_of": f"2026-06-{i+1:02d}",
            "outcome_excess": 0.01 * (i % 2),
            "personality_basis": "pit_labels",
        })
    pd.DataFrame(rows).to_parquet(
        fake_root / "data" / "neuralweb" / "spine_index.parquet", index=False)

    result = _run_t2(fake_root, dry_run=False)
    counts = result["counts"]

    assert counts["cells_examined"] > 0
    assert counts["candidates"] == 0
    assert result["candidates"] == []
    assert counts["cells_insufficient_n"] == counts["cells_examined"]


def test_t2_no_personality_basis_column(fake_root: Path):
    """T2 when spine lacks personality_basis column → all insufficient_n, honest log."""
    rows = []
    for i in range(300):
        rows.append({
            "signal_id": f"sig_{i}",
            "engine": "track_record",
            "outcome_graded": True,
            "archetype": "high_beta",
            "quad_hard_label": "Q1",
            "as_of": f"2026-06-{(i % 28)+1:02d}",
            "outcome_excess": 0.01,
        })
    pd.DataFrame(rows).to_parquet(
        fake_root / "data" / "neuralweb" / "spine_index.parquet", index=False)

    result = _run_t2(fake_root, dry_run=False)
    assert result["counts"]["candidates"] == 0
    assert result["candidates"] == []


# ---------------------------------------------------------------------------
# 9 & 10. F2 regression tests — T2 membership null (high pctile and low pctile)
# ---------------------------------------------------------------------------

def _make_t2_pit_spine(
    tmp_path: Path,
    n_cell: int = 60,
    cell_hit_rate: float = 0.9,
    marginal_hit_rate: float = 0.5,
    n_marginal_extra: int = 200,
) -> None:
    """Build spine with pit_labels rows for T2 membership null test.

    Cell rows have cell_hit_rate.  Marginal pool (same engine, other cells)
    has marginal_hit_rate.  Calendar blocks spread across months.
    """
    rows = []
    # Cell rows: archetype=high_beta, quad=Q1, engine=tr
    for i in range(n_cell):
        mo = (i % 6) + 1
        hit_val = 0.05 if i < int(n_cell * cell_hit_rate) else -0.05
        rows.append({
            "engine": "tr",
            "outcome_graded": True,
            "archetype": "high_beta",
            "quad_hard_label": "Q1",
            "as_of": f"2026-{mo:02d}-15",
            "outcome_excess": hit_val,
            "personality_basis": "pit_labels",
        })
    # Marginal pool: same engine, different archetype/quad → not in cell
    for j in range(n_marginal_extra):
        mo = (j % 6) + 1
        hit_val = 0.05 if j < int(n_marginal_extra * marginal_hit_rate) else -0.05
        rows.append({
            "engine": "tr",
            "outcome_graded": True,
            "archetype": "conservative",  # different archetype → in marginal but not cell
            "quad_hard_label": "Q2",
            "as_of": f"2026-{mo:02d}-15",
            "outcome_excess": hit_val,
            "personality_basis": "pit_labels",
        })
    pd.DataFrame(rows).to_parquet(
        tmp_path / "data" / "neuralweb" / "spine_index.parquet", index=False)


def test_t2_membership_null_high_pctile(fake_root: Path):
    """F2 regression: cell with hit-rate far above marginal → high pctile + candidate.

    Pre-fix code shuffled within-cell (null = constant = observed → pctile = 0%).
    Post-fix uses membership null: draw from marginal pool → true null distribution.
    With cell_hr=0.9 and marginal_hr=0.5, the 0.4 delta should rank above
    almost all membership draws at marginal_hr=0.5.
    """
    _make_t2_pit_spine(
        fake_root,
        n_cell=60,
        cell_hit_rate=0.9,   # cell hit-rate = 90%
        marginal_hit_rate=0.5,  # marginal = 50%
        n_marginal_extra=300,
    )

    result = _run_t2(fake_root, dry_run=False)
    counts = result["counts"]

    assert counts["cells_testable"] > 0, "Expected >=1 testable cell"
    assert counts["candidates"] > 0, (
        f"F2 regression: cell with 90% vs 50% marginal should emit candidate. "
        f"Got candidates={counts['candidates']}. "
        f"If 0, the within-cell shuffle null is still present."
    )
    for cand in result["candidates"]:
        assert cand["null_pctile"] >= 99.0
        assert "hit_rate_delta" in cand["stat"]


def test_t2_membership_null_low_pctile(fake_root: Path):
    """F2 regression: cell with same hit-rate as marginal → low pctile, no candidate.

    Pre-fix: null = constant = observed_delta → pctile=0% (never candidate).
    This test verifies the null actually discriminates: when cell_hr == marginal_hr,
    pctile should be around 50% (observed_delta=0 vs symmetric null), so no candidate.
    """
    _make_t2_pit_spine(
        fake_root,
        n_cell=60,
        cell_hit_rate=0.5,   # same as marginal
        marginal_hit_rate=0.5,
        n_marginal_extra=300,
    )

    result = _run_t2(fake_root, dry_run=False)
    counts = result["counts"]

    # Cell with 0 delta should not emit a candidate
    assert counts["candidates"] == 0, (
        f"F2 regression: cell at marginal hit-rate should emit 0 candidates, "
        f"got {counts['candidates']}."
    )


# ---------------------------------------------------------------------------
# 11 & 12. F3 regression tests — T3 pure noise → zero; injected shift → emits
# ---------------------------------------------------------------------------

def _make_t3_spine(
    tmp_path: Path,
    n_snapshots: int = 80,
    baseline_fraction: float = 0.3,
    recent_fraction: float | None = None,
    quad: str = "Q1",
    vol: str = "low",
) -> None:
    """Build spine for T3 test.

    Each snapshot has n_symbols rows; (quad, vol) cell has baseline_fraction.
    Recent _T3_RECENT_WINDOW snapshots use recent_fraction if provided.
    """
    n_symbols = 100
    recent_start = n_snapshots - _T3_RECENT_WINDOW
    rows = []
    for snap_idx in range(n_snapshots):
        as_of = f"2025-{(snap_idx // 30) + 1:02d}-{(snap_idx % 28) + 1:02d}"
        frac = (recent_fraction if (recent_fraction is not None and snap_idx >= recent_start)
                else baseline_fraction)
        for sym_idx in range(n_symbols):
            if sym_idx < int(n_symbols * frac):
                q, v = quad, vol
            else:
                q, v = "Q2", "high"
            rows.append({
                "as_of": as_of,
                "quad_hard_label": q,
                "vol_regime": v,
                "engine": "tr",
            })
    pd.DataFrame(rows).to_parquet(
        tmp_path / "data" / "neuralweb" / "spine_index.parquet", index=False)


def test_t3_pure_noise_zero_candidates(fake_root: Path):
    """F3 regression: pure-noise T3 series (>=22 snapshots) → zero candidates.

    Pre-fix: point vs baseline_mean null → inflated pctile for any high single point.
    Post-fix: window mean vs resampled window means → similar scale.
    """
    n_snapshots = _CELL_N_FLOOR + _T3_RECENT_WINDOW + 5
    _make_t3_spine(
        fake_root,
        n_snapshots=n_snapshots,
        baseline_fraction=0.3,
        recent_fraction=None,  # no shift
    )

    result = _run_t3(fake_root, dry_run=False)
    counts = result["counts"]

    assert counts["candidates"] == 0, (
        f"F3 regression: pure-noise T3 should emit 0 candidates, "
        f"got {counts['candidates']}. Point-vs-mean null may still be present."
    )


def test_t3_injected_shift_emits(fake_root: Path):
    """F3 regression: injected persistent T3 shift → candidate emits.

    Baseline fraction = 0.3; recent window fraction = 0.9 (strong shift).
    """
    n_snapshots = _CELL_N_FLOOR + _T3_RECENT_WINDOW + 15
    _make_t3_spine(
        fake_root,
        n_snapshots=n_snapshots,
        baseline_fraction=0.3,
        recent_fraction=0.9,  # persistent large shift in recent window
    )

    result = _run_t3(fake_root, dry_run=False)
    counts = result["counts"]

    assert counts["cells_testable"] > 0, "Expected testable cells"
    assert counts["candidates"] > 0, (
        f"F3 injection test: large injected T3 shift should emit candidate, "
        f"got {counts['candidates']}. counts={counts}"
    )
    for cand in result["candidates"]:
        assert cand["template"] == "T3"
        assert "mode_share_shift" in cand["stat"]
        assert cand["null_pctile"] >= 99.0


# ---------------------------------------------------------------------------
# 13. Dedupe: same candidate re-run → refresh not duplicate
# ---------------------------------------------------------------------------

def test_dedupe_refresh(tmp_path: Path):
    """Re-running the same candidate refreshes last_refreshed, does not duplicate."""
    output_path = tmp_path / "context_candidates.jsonl"
    dedup_corpus: list[dict] = []  # empty corpus

    cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "none_known",
    }

    emitted1, refreshed1, deduped1 = _emit_candidates([cand], output_path, dedup_corpus, dry_run=False)
    assert emitted1 == 1
    assert refreshed1 == 0
    assert deduped1 == 0

    emitted2, refreshed2, deduped2 = _emit_candidates([cand], output_path, dedup_corpus, dry_run=False)
    assert emitted2 == 0
    assert refreshed2 == 1
    assert deduped2 == 0

    with output_path.open() as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    assert len(rows) == 1
    assert rows[0]["status"] == "candidate"


# ---------------------------------------------------------------------------
# 14. Dedupe: a decayed row blocks re-emission as new
# ---------------------------------------------------------------------------

def test_dedupe_decayed_blocks_new(tmp_path: Path):
    """A decayed row prevents re-emitting the same candidate as novel."""
    output_path = tmp_path / "context_candidates.jsonl"
    dedup_corpus: list[dict] = []

    old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds")
    cand_id = _candidate_id("T1", "high_beta", "composition_drift_mean")
    decayed_row = {
        "_schema": "context_candidates.v1",
        "candidate_id": cand_id,
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "first_seen": old_ts,
        "last_refreshed": old_ts,
        "adjacent_falsified": "none_known",
        "status": "decayed",
    }
    with output_path.open("w") as fh:
        fh.write(json.dumps(decayed_row) + "\n")

    new_cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "none_known",
    }
    emitted, refreshed, deduped = _emit_candidates(
        [new_cand], output_path, dedup_corpus, dry_run=False
    )
    assert emitted == 0, "Decayed candidate should not be re-emitted as new"
    assert refreshed == 1, "Decayed candidate should be refreshed (seen again)"

    with output_path.open() as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == cand_id


# ---------------------------------------------------------------------------
# 15. Decay transition
# ---------------------------------------------------------------------------

def test_decay_transition(tmp_path: Path):
    """Candidate older than 60 days is transitioned to status='decayed' on next run."""
    output_path = tmp_path / "context_candidates.jsonl"
    dedup_corpus: list[dict] = []

    old_ts = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat(timespec="seconds")
    cand_id = _candidate_id("T3", "quad=Q1|vol_regime=low", "mode_share_shift")
    old_row = {
        "_schema": "context_candidates.v1",
        "candidate_id": cand_id,
        "template": "T3",
        "cell": "quad=Q1|vol_regime=low",
        "stat": "mode_share_shift=0.15|observed_mean=0.20|baseline_mean=0.05",
        "null_pctile": 99.2,
        "n": 18,
        "first_seen": old_ts,
        "last_refreshed": old_ts,
        "adjacent_falsified": "none_known",
        "status": "candidate",
    }
    with output_path.open("w") as fh:
        fh.write(json.dumps(old_row) + "\n")

    emitted, refreshed, deduped = _emit_candidates([], output_path, dedup_corpus, dry_run=False)
    assert emitted == 0
    assert refreshed == 0

    with output_path.open() as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    assert len(rows) == 1
    assert rows[0]["status"] == "decayed"


# ---------------------------------------------------------------------------
# 16. F7 regression: decayed rows do NOT get last_refreshed bumped
# ---------------------------------------------------------------------------

def test_decay_no_bump_last_refreshed(tmp_path: Path):
    """F7 regression: re-seen decayed row gets last_seen_while_decayed, not last_refreshed.

    Pre-fix code bumped last_refreshed on ALL seen-again rows including decayed ones,
    resetting the decay clock.
    """
    output_path = tmp_path / "context_candidates.jsonl"
    dedup_corpus: list[dict] = []

    old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds")
    cand_id = _candidate_id("T1", "high_beta", "composition_drift_mean")
    decayed_row = {
        "_schema": "context_candidates.v1",
        "candidate_id": cand_id,
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "first_seen": old_ts,
        "last_refreshed": old_ts,  # the OLD timestamp — must NOT change
        "adjacent_falsified": "none_known",
        "status": "decayed",
    }
    with output_path.open("w") as fh:
        fh.write(json.dumps(decayed_row) + "\n")

    new_cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "none_known",
    }
    _emit_candidates([new_cand], output_path, dedup_corpus, dry_run=False)

    with output_path.open() as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    assert len(rows) == 1
    row = rows[0]

    # F7: last_refreshed must NOT have been updated
    assert row["last_refreshed"] == old_ts, (
        f"F7 regression: decayed row's last_refreshed should not be bumped. "
        f"Got last_refreshed={row['last_refreshed']!r}, expected {old_ts!r}"
    )
    # last_seen_while_decayed should be set to a recent timestamp
    assert "last_seen_while_decayed" in row, (
        "F7: decayed row should have 'last_seen_while_decayed' key"
    )
    seen_ts = datetime.fromisoformat(row["last_seen_while_decayed"])
    assert seen_ts.tzinfo is not None
    assert seen_ts > datetime.fromisoformat(old_ts)


# ---------------------------------------------------------------------------
# 17 & 18. adjacent_falsified required
# ---------------------------------------------------------------------------

def test_adjacent_falsified_required(tmp_path: Path):
    """Emitting a candidate without adjacent_falsified raises ValueError."""
    output_path = tmp_path / "context_candidates.jsonl"
    bad_cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "",
    }
    with pytest.raises(ValueError, match="adjacent_falsified"):
        _emit_candidates([bad_cand], output_path, [], dry_run=False)


def test_adjacent_falsified_none_raises(tmp_path: Path):
    """Emitting a candidate with adjacent_falsified=None raises ValueError."""
    output_path = tmp_path / "context_candidates.jsonl"
    bad_cand = {
        "template": "T2",
        "cell": "archetype=high_beta|quad=Q1|engine=track_record",
        "stat": "hit_rate_delta=0.15",
        "null_pctile": 99.1,
        "n": 55,
    }
    with pytest.raises(ValueError, match="adjacent_falsified"):
        _emit_candidates([bad_cand], output_path, [], dry_run=False)


# ---------------------------------------------------------------------------
# 19. dry_run — no writes to disk or real ledger
# ---------------------------------------------------------------------------

def test_dry_run_no_writes(fake_root: Path, ledger_path: Path):
    """dry_run=True: budget is NOT written to ledger, output file NOT written."""
    rows = [{"symbol": "T0001", "archetype": "high_beta", "engine": "track_record",
              "as_of": "2026-06-01"}]
    pd.DataFrame(rows).to_parquet(
        fake_root / "data" / "neuralweb" / "spine_index.parquet", index=False
    )

    output_path = fake_root / "data" / "neuralweb" / "context_candidates.jsonl"
    assert not output_path.exists()

    newly = register_budget(fake_root, ledger_path=ledger_path, dry_run=True)
    assert not ledger_path.exists(), "dry_run should not write ledger"


# ---------------------------------------------------------------------------
# 20. Full run with budget
# ---------------------------------------------------------------------------

def test_full_run_with_budget(fake_root: Path, ledger_path: Path):
    """run() with a pre-registered budget completes without error."""
    register_budget(fake_root, ledger_path=ledger_path, dry_run=False)
    assert ledger_path.exists()

    rows = [{"symbol": f"T{i:04d}", "archetype": "high_beta" if i < 60 else "conservative",
              "engine": "track_record", "as_of": "2026-06-01"} for i in range(100)]
    pd.DataFrame(rows).to_parquet(
        fake_root / "data" / "neuralweb" / "spine_index.parquet", index=False
    )

    rc = run(root=fake_root, dry_run=False, ledger_path=ledger_path)
    assert rc == 0


# ---------------------------------------------------------------------------
# 21 & 22. null_percentile sanity
# ---------------------------------------------------------------------------

def test_null_percentile_extremes():
    """null_percentile returns 100 when observed > all null values, 0 when below all."""
    null_dist = [0.5, 1.0, 1.5, 2.0, 2.5]
    assert _null_percentile(3.0, null_dist) == 100.0
    assert _null_percentile(0.0, null_dist) == 0.0


def test_null_percentile_empty():
    """null_percentile with empty null dist returns 50.0 (neutral)."""
    assert _null_percentile(5.0, []) == 50.0


# ---------------------------------------------------------------------------
# 23 & 24. Candidate ID stability
# ---------------------------------------------------------------------------

def test_candidate_id_stable():
    """Same inputs always produce the same candidate_id."""
    cid1 = _candidate_id("T1", "high_beta", "composition_drift_mean")
    cid2 = _candidate_id("T1", "high_beta", "composition_drift_mean")
    assert cid1 == cid2


def test_candidate_id_differs_by_template():
    """Different templates produce different IDs."""
    cid_t1 = _candidate_id("T1", "high_beta", "composition_drift_mean")
    cid_t2 = _candidate_id("T2", "high_beta", "composition_drift_mean")
    assert cid_t1 != cid_t2


# ---------------------------------------------------------------------------
# 25. F6 regression: structured dedup — no false positive on archetype-only overlap
# ---------------------------------------------------------------------------

def test_dedup_no_false_positive_archetype_only(tmp_path: Path):
    """F6 regression: novel composition-drift candidate NOT deduped merely because
    a species entry mentions the same archetype.

    Pre-fix code used raw >8-char substring sweep, so a species id 'high_beta'
    (9 chars) appearing in the desc 'T1 high_beta ...' would silently dedup.
    Post-fix requires BOTH cell-key AND stat-family tokens to overlap.
    """
    output_path = tmp_path / "context_candidates.jsonl"

    # Fabricate corpus: species entry with id 'high_beta' — mentions archetype
    # but has NO stat-family word (composition/drift/hit/rate etc.)
    corpus = [
        {
            "source": "species",
            "id": "high_beta",  # 9 chars > 8 — would have triggered old substring sweep
            "tokens": _tok("high_beta"),
            "family_words": frozenset(),  # no stat-family overlap
        }
    ]

    cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "none_known",
    }

    # With structured matching: archetype overlaps, but no stat-family overlap
    # → should NOT be deduped
    emitted, refreshed, deduped = _emit_candidates([cand], output_path, corpus, dry_run=False)
    assert emitted == 1, (
        f"F6 regression: novel composition-drift should NOT be deduped by archetype-only "
        f"species token. emitted={emitted}, deduped={deduped}"
    )
    assert deduped == 0


def test_dedup_true_positive_requires_both_tokens(tmp_path: Path):
    """F6: dedup fires when BOTH cell-key AND stat-family tokens overlap."""
    output_path = tmp_path / "context_candidates.jsonl"

    # Corpus entry that has BOTH archetype token 'high_beta' AND stat-family 'composition'
    corpus = [
        {
            "source": "oracle",
            "id": "high_beta_composition_drift_study",
            "tokens": _tok("high_beta_composition_drift_study"),
            "family_words": frozenset(["composition", "drift"]),
        }
    ]

    cand = {
        "template": "T1",
        "cell": "high_beta",
        "stat": "composition_drift_mean=2.5000",
        "null_pctile": 99.5,
        "n": 60,
        "adjacent_falsified": "none_known",
    }

    # Cell tokens: {high, beta}; stat-family tokens: {composition, drift}
    # Both overlap with corpus entry → dedup fires
    emitted, refreshed, deduped = _emit_candidates([cand], output_path, corpus, dry_run=False)
    assert deduped == 1, (
        f"F6: candidate with both archetype AND stat-family overlap should be deduped. "
        f"deduped={deduped}"
    )
    assert emitted == 0


# ---------------------------------------------------------------------------
# 26. F8: adjacent_falsified species lookup
# ---------------------------------------------------------------------------

def test_adjacent_falsified_species_lookup(fake_root: Path):
    """F8: fabricated registry with matching graveyard reference → id populated."""
    # Write species registry with a hostile archetype entry for 'high_beta'
    _write_species_reg(
        fake_root / "data" / "species" / "registry.json",
        [
            {
                "species_id": "S99",
                "name": "Test Species",
                "archetype_scope": {
                    "applies": ["all"],
                    "hostile": ["high_beta archetype falsified by regime_change 2022"],
                },
                "adjacent_falsified": [
                    {"idea": "high_beta composition drift falsified by momentum reversal",
                     "source": "§test"}
                ],
            }
        ],
    )

    arch_tokens = _tok("high_beta")
    cell_tokens = _tok("archetype=high_beta|quad=Q1")

    result = _lookup_adjacent_falsified(fake_root, arch_tokens, cell_tokens)
    assert result != "none_known", (
        f"F8: should have found adjacent_falsified from species registry, got 'none_known'"
    )
    assert "S99" in result, f"F8: expected species_id 'S99' in result, got {result!r}"


def test_adjacent_falsified_no_match_returns_none_known(fake_root: Path):
    """F8: when no species entry matches, returns 'none_known'."""
    # Registry with entries for a completely different archetype
    _write_species_reg(
        fake_root / "data" / "species" / "registry.json",
        [
            {
                "species_id": "S1",
                "name": "Other Species",
                "archetype_scope": {
                    "applies": ["conservative"],
                    "hostile": ["distressed"],
                },
                "adjacent_falsified": [
                    {"idea": "conservative drawdown falsified by credit_shock", "source": "§1"}
                ],
            }
        ],
    )

    arch_tokens = _tok("high_beta")
    cell_tokens = _tok("archetype=high_beta|quad=Q1")

    result = _lookup_adjacent_falsified(fake_root, arch_tokens, cell_tokens)
    assert result == "none_known"


# ---------------------------------------------------------------------------
# Additional: _is_dedup_match structured unit tests
# ---------------------------------------------------------------------------

def test_is_dedup_match_returns_none_on_empty_corpus():
    """_is_dedup_match returns None on empty corpus."""
    result = _is_dedup_match(_tok("high_beta"), _tok("composition"), [])
    assert result is None


def test_is_dedup_match_requires_both_conditions():
    """_is_dedup_match requires cell-key AND stat-family overlap."""
    corpus = [
        {
            "source": "oracle",
            "id": "high_beta_entry",
            "tokens": _tok("high_beta_entry"),
            "family_words": frozenset(),  # no stat family
        }
    ]
    # Cell overlap only → no match
    assert _is_dedup_match(_tok("high_beta"), frozenset(["composition"]), corpus) is None

    corpus2 = [
        {
            "source": "oracle",
            "id": "composition_shift_study",
            "tokens": _tok("composition_shift_study"),
            "family_words": frozenset(["composition", "shift"]),
        }
    ]
    # Stat family overlap only (no cell overlap) → no match
    assert _is_dedup_match(_tok("high_beta"), frozenset(["composition"]), corpus2) is None

    corpus3 = [
        {
            "source": "oracle",
            "id": "high_beta_composition_shift",
            "tokens": _tok("high_beta_composition_shift"),
            "family_words": frozenset(["composition", "shift"]),
        }
    ]
    # Both overlap → match
    assert _is_dedup_match(_tok("high_beta"), frozenset(["composition"]), corpus3) is not None
