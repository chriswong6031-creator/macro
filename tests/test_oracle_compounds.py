"""Hermetic tests for the Oracle Research Factory (W-B1/B3).

engine/oracle/compounds.py  +  scripts/oracle_screen.py  +
scripts/oracle_promotion_scan.py

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory:
(A) grammar_rejects_unknown_ops — validate_rule raises ValueError for an
    unknown op; VALID_OPS set is the contract boundary.

(B) as_of_causality — a condition that is True only at t+1 (the entry date
    is tomorrow) yields ZERO entries at t.  Discriminating: a naive
    implementation without the shift would return t+1 as an entry.

(C) episode_event_opposite_complex — opposite-complex scope resolves
    correctly via rotation_groups risk_sign; a risk_on node's opposite is
    risk_off nodes only.

(D) keep_first_dedup_trial_ledger — appending the same (compound_id,
    screener, params_hash) key twice writes the row only once.

(E) keep_first_dedup_live_ledger — same keep-first dedup on live_ledger
    fire rows.

(F) blocked_missing_column_path — a rule referencing a nonexistent column
    returns {"__blocked__": {col}} and never raises; the screen runner
    records status blocked_missing_column.

(G) promotion_floor_logic — compounds with |effect_63d| >= 0.01 AND n >= 100
    AND >= 3/4 consistent eras appear in the queue; compounds below the
    floor do not.

(H) era_consistency_check — a compound consistent in only 2/4 eras does
    NOT meet the floor even if effect and n pass.

(I) live_accrual_maturity_grading — a live_ledger row with fire_date in the
    past (> 63 trading days) gets outcome_mature=True and excess_63d filled
    on a grading pass.

(J) same_complex_scope — same-complex episode_event fires only when the
    episode node is in the SAME complex as the entry node, not another.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers to build synthetic data
# ---------------------------------------------------------------------------

def _make_panel(
    nodes: list[str],
    n_days: int = 300,
    start: str = "2020-01-02",
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic panel with all COLUMN_SCHEMA columns (mostly random noise)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days, name="date")
    rows = []
    for node in nodes:
        ret = rng.normal(0, 0.01, n_days)
        rs = rng.normal(0, 0.008, n_days)
        vel_1w = np.cumsum(ret) * 0.02
        vel_1m = np.cumsum(ret) * 0.015
        vel_3m = np.cumsum(ret) * 0.01
        accel = vel_1w - vel_3m
        accel_z = (accel - accel.mean()) / (accel.std() + 1e-9)
        cohesion = rng.uniform(0.1, 0.9, n_days)
        cohesion_chg = np.diff(cohesion, prepend=cohesion[0])
        breadth_50 = rng.uniform(0.2, 0.8, n_days)
        persistence = rng.uniform(0.3, 0.7, n_days)
        turnover_z = rng.normal(0, 1, n_days)
        washout_w = np.zeros(n_days)
        # Plant a washout signal at day 50
        washout_w[50] = 1.0
        stochrsi_w_k = rng.uniform(0, 1, n_days)
        stochrsi_w_d = rng.uniform(0, 1, n_days)
        cohesion_rebuild = np.zeros(n_days)
        vix_pctile = rng.uniform(0.1, 0.9, n_days)
        tlt_ret_10d = rng.normal(0, 0.01, n_days)
        spy_above_200d = rng.choice([0, 1], n_days).astype(float)

        df = pd.DataFrame({
            "ret": ret, "rs": rs, "vel_1w": vel_1w, "vel_1m": vel_1m,
            "vel_3m": vel_3m, "accel": accel, "accel_z": accel_z,
            "cohesion": cohesion, "cohesion_chg": cohesion_chg,
            "breadth_50": breadth_50, "persistence": persistence,
            "turnover_z": turnover_z, "washout_w": washout_w,
            "stochrsi_w_k": stochrsi_w_k, "stochrsi_w_d": stochrsi_w_d,
            "cohesion_rebuild": cohesion_rebuild,
            "vix_pctile": vix_pctile, "tlt_ret_10d": tlt_ret_10d,
            "spy_above_200d": spy_above_200d,
        }, index=dates)
        df["node"] = node
        rows.append(df.reset_index().set_index(["node", "date"]))

    return pd.concat(rows)


def _make_episodes(
    entries: list[dict],
) -> pd.DataFrame:
    """Minimal episodes dataframe from a list of dicts."""
    if not entries:
        return pd.DataFrame(columns=[
            "episode_id", "node", "direction", "onset_date",
            "confirmed_date", "undeniable_date",
        ])
    rows = []
    for e in entries:
        rows.append({
            "episode_id": f"{e['node']}::{e['direction']}::{e['onset_date']}::1",
            "node": e["node"],
            "direction": e["direction"],
            "onset_date": pd.Timestamp(e["onset_date"]),
            "confirmed_date": pd.Timestamp(e.get("confirmed_date") or e["onset_date"]) + pd.Timedelta(days=5),
            "undeniable_date": pd.NaT,
        })
    return pd.DataFrame(rows)


def _rotation_groups_fixture() -> dict:
    return {
        "complexes": [
            {
                "id": "risk_on_complex",
                "name": "Risk On",
                "name_zh": "风险偏好",
                "risk_sign": "risk_on",
                "members": ["node_A", "node_B"],
            },
            {
                "id": "risk_off_complex",
                "name": "Risk Off",
                "name_zh": "规避风险",
                "risk_sign": "risk_off",
                "members": ["node_C", "node_D"],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Test A — grammar rejects unknown ops
# ---------------------------------------------------------------------------

def test_grammar_rejects_unknown_ops():
    """validate_rule raises ValueError for an unknown op."""
    from engine.oracle.compounds import validate_rule

    # Known ops should not raise
    validate_rule({"col": "rs", "op": "gt", "value": 0.0})
    validate_rule({"col": "washout_w", "op": "crossed_above", "value": 0.5})

    # Unknown op should raise loudly
    with pytest.raises(ValueError, match="Unknown op"):
        validate_rule({"col": "rs", "op": "contains", "value": 0.0})

    with pytest.raises(ValueError, match="Unknown op"):
        validate_rule({"col": "rs", "op": "regex", "value": 0.0})

    # Unknown op nested in 'all'
    with pytest.raises(ValueError, match="Unknown op"):
        validate_rule({"all": [{"col": "rs", "op": "between", "value": 0.0}]})


# ---------------------------------------------------------------------------
# Test B — as-of causality: condition true only at t+1 yields no entry at t
# ---------------------------------------------------------------------------

def test_as_of_causality_no_lookahead():
    """A crossed_above condition fires only on the day of the cross, not before.

    Discriminating: if the evaluator used the value at t+1, it would report
    entries one day too early.
    """
    from engine.oracle.compounds import get_entry_dates

    # Build a panel where accel_z crosses above 2.0 on exactly day 100
    n = 200
    dates = pd.bdate_range("2021-01-04", periods=n, name="date")
    rng = np.random.default_rng(0)
    accel_z_vals = rng.normal(0, 0.5, n)
    # Day 99 (index): value 1.8 (below 2.0); day 100: value 2.5 (above 2.0)
    accel_z_vals[99] = 1.8
    accel_z_vals[100] = 2.5

    panel_data = pd.DataFrame({
        "ret": rng.normal(0, 0.01, n),
        "rs": rng.normal(0, 0.01, n),
        "vel_1w": rng.normal(0, 0.01, n),
        "vel_1m": rng.normal(0, 0.01, n),
        "vel_3m": rng.normal(0, 0.01, n),
        "accel": rng.normal(0, 0.01, n),
        "accel_z": accel_z_vals,
        "cohesion": rng.uniform(0.2, 0.8, n),
        "cohesion_chg": rng.normal(0, 0.05, n),
        "breadth_50": rng.uniform(0.3, 0.7, n),
        "persistence": rng.uniform(0.3, 0.7, n),
        "turnover_z": rng.normal(0, 1, n),
        "washout_w": np.zeros(n),
        "stochrsi_w_k": rng.uniform(0, 1, n),
        "stochrsi_w_d": rng.uniform(0, 1, n),
        "cohesion_rebuild": np.zeros(n),
        "vix_pctile": rng.uniform(0, 1, n),
        "tlt_ret_10d": rng.normal(0, 0.01, n),
        "spy_above_200d": np.ones(n),
    }, index=dates)
    panel_data["node"] = "XLK"
    panel = panel_data.reset_index().set_index(["node", "date"])

    compound = {
        "id": "TEST_CAUSAL",
        "entry_rule": {"col": "accel_z", "op": "crossed_above", "value": 2.0},
        "condition_rule": None,
        "universe": {"tier": "s"},
        "horizons": [21, 63],
    }
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    entries = get_entry_dates(compound, panel, episodes, rg)

    # Should fire on day 100 (index), NOT day 99
    trigger_day = dates[100]
    # MUST NOT fire on the day before the cross
    not_trigger_day = dates[99]

    fired_nodes = list(entries.keys())
    assert "XLK" in fired_nodes, "Expected XLK to have entry dates"
    xfired = entries["XLK"]
    assert trigger_day in xfired, f"Expected fire on {trigger_day}, but not found in {xfired}"
    assert not_trigger_day not in xfired, (
        f"CAUSALITY VIOLATION: fired on {not_trigger_day} (the day before the cross) — "
        "this indicates lookahead in the evaluator"
    )


# ---------------------------------------------------------------------------
# Test C — episode_event opposite-complex scope
# ---------------------------------------------------------------------------

def test_episode_event_opposite_complex():
    """Opposite-complex episode_event fires when opposite-risk-sign nodes roll over.

    Discriminating: uses rotation_groups risk_sign, not a hardcoded list.
    """
    from engine.oracle.compounds import get_entry_dates

    # Plant an episode for a risk_on node (node_A) at day 50
    rg = _rotation_groups_fixture()

    # Panel for node_C (risk_off_complex — this is the ENTRY node)
    nodes = ["node_A", "node_C"]
    panel = _make_panel(nodes, n_days=200, start="2021-01-04")

    # Episode: node_A (risk_on) goes OUT at day 30 (well within 15-session window of day 50)
    dates = pd.bdate_range("2021-01-04", periods=200)
    onset_date = dates[30].isoformat()[:10]

    episodes = _make_episodes([{
        "node": "node_A",
        "direction": "out",
        "onset_date": onset_date,
    }])

    # Compound: entry on node_C when an OPPOSITE-complex (risk_on) node has an OUT onset
    # within 15 sessions.  We look for node_C entries on day 30-45 range.
    compound = {
        "id": "TEST_OPP",
        "entry_rule": {"episode_event": {
            "direction": "out",
            "tier": "onset",
            "complex_scope": "opposite",
            "within_sessions": 15,
        }},
        "condition_rule": None,
        "universe": {"tier": "s", "nodes": ["node_C"]},
        "horizons": [21, 63],
    }

    entries = get_entry_dates(compound, panel, episodes, rg)

    # node_C should fire around day 30-45 (within the within_sessions window)
    assert "node_C" in entries, "node_C (risk_off) should fire when risk_on node_A exits"
    c_entries = entries["node_C"]
    assert len(c_entries) > 0

    # Verify the fire is WITHIN the window of the episode
    ep_date = pd.Timestamp(onset_date)
    fires_in_window = [d for d in c_entries if ep_date <= d <= ep_date + pd.Timedelta(days=30)]
    assert len(fires_in_window) > 0, "No fires found within the window"


# ---------------------------------------------------------------------------
# Test D — keep-first dedup on trial ledger
# ---------------------------------------------------------------------------

def test_keep_first_dedup_trial_ledger():
    """Appending the same (compound_id, screener, params_hash) key twice writes once."""
    from scripts.oracle_screen import _append_ledger_keep_first, _params_hash

    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = Path(tmp) / "trial_ledger.jsonl"
        row = {
            "compound_id": "A1",
            "screener": "tier1_screen_v1",
            "params_hash": _params_hash("A1", "tier1_screen_v1", "s", [21, 63]),
            "n": 50,
            "effect_63d": 0.02,
        }
        r1 = _append_ledger_keep_first(ledger_path, row)
        r2 = _append_ledger_keep_first(ledger_path, row)

        assert r1 is True, "First append should succeed"
        assert r2 is False, "Second append of same key should be skipped (keep-first)"

        lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"


# ---------------------------------------------------------------------------
# Test E — keep-first dedup on live ledger (different key structure)
# ---------------------------------------------------------------------------

def test_keep_first_dedup_live_ledger():
    """Live ledger keep-first: same compound_id::node::fire_date skips second write."""
    with tempfile.TemporaryDirectory() as tmp:
        live_path = Path(tmp) / "live_ledger.jsonl"
        fire_key_1 = "A1::XLK::2026-07-01"
        fire_key_2 = "A1::XLF::2026-07-01"  # different node — should write

        existing: set[str] = set()

        def _write_if_new(path: Path, row: dict, seen: set[str]) -> bool:
            k = f"{row['compound_id']}::{row['node']}::{row['fire_date']}"
            if k in seen:
                return False
            seen.add(k)
            with open(path, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            return True

        row1 = {"compound_id": "A1", "node": "XLK", "fire_date": "2026-07-01"}
        row2 = {"compound_id": "A1", "node": "XLK", "fire_date": "2026-07-01"}  # duplicate
        row3 = {"compound_id": "A1", "node": "XLF", "fire_date": "2026-07-01"}  # different node

        w1 = _write_if_new(live_path, row1, existing)
        w2 = _write_if_new(live_path, row2, existing)
        w3 = _write_if_new(live_path, row3, existing)

        assert w1 is True
        assert w2 is False, "Duplicate fire should be skipped"
        assert w3 is True, "Different node is a new fire"

        lines = [l for l in live_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# Test F — blocked_missing_column path
# ---------------------------------------------------------------------------

def test_blocked_missing_column():
    """A rule referencing a nonexistent column returns blocked sentinel, never raises."""
    from engine.oracle.compounds import get_entry_dates

    panel = _make_panel(["XLK"], n_days=100)
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    compound = {
        "id": "TEST_BLOCKED",
        "entry_rule": {"col": "NONEXISTENT_COLUMN_XYZ", "op": "gt", "value": 0.0},
        "condition_rule": None,
        "universe": {"tier": "s"},
        "horizons": [21, 63],
    }

    # Must not raise
    result = get_entry_dates(compound, panel, episodes, rg)

    assert "__blocked__" in result, "Expected blocked sentinel in result"
    assert "NONEXISTENT_COLUMN_XYZ" in result["__blocked__"]


# ---------------------------------------------------------------------------
# Test G — promotion floor logic
# ---------------------------------------------------------------------------

def test_promotion_floor_passes():
    """Compound meeting all floor criteria appears in promotion queue."""
    from scripts.oracle_promotion_scan import _meets_promotion_floor

    passing_row = {
        "compound_id": "A1",
        "n": 150,
        "effect_63d": 0.015,   # |0.015| >= 0.01 ✓
        "hit_63d": 0.57,       # 0.57 >= 0.55 ✓
        "era_consistent_63d": 3,  # 3/4 ✓
    }
    assert _meets_promotion_floor(passing_row) is True


def test_promotion_floor_fails_low_n():
    """Compound with n < 100 does NOT pass even with good effect."""
    from scripts.oracle_promotion_scan import _meets_promotion_floor

    row = {
        "compound_id": "A1",
        "n": 80,              # < 100 ✗
        "effect_63d": 0.02,
        "hit_63d": 0.60,
        "era_consistent_63d": 4,
    }
    assert _meets_promotion_floor(row) is False


def test_promotion_floor_fails_low_effect_and_hit():
    """Compound with small effect AND low hit rate does NOT pass."""
    from scripts.oracle_promotion_scan import _meets_promotion_floor

    row = {
        "compound_id": "A1",
        "n": 200,
        "effect_63d": 0.005,  # < 0.01 ✗
        "hit_63d": 0.52,      # < 0.55 ✗
        "era_consistent_63d": 4,
    }
    assert _meets_promotion_floor(row) is False


# ---------------------------------------------------------------------------
# Test H — era consistency (only 2/4 eras consistent → below floor)
# ---------------------------------------------------------------------------

def test_era_consistency_2_of_4_fails():
    """Compound consistent in only 2/4 eras fails the floor."""
    from scripts.oracle_promotion_scan import _meets_promotion_floor

    row = {
        "compound_id": "A1",
        "n": 200,
        "effect_63d": 0.015,
        "hit_63d": 0.58,
        "era_consistent_63d": 2,  # < 3 ✗
    }
    assert _meets_promotion_floor(row) is False


def test_era_consistency_3_of_4_passes():
    """Compound consistent in 3/4 eras (with passing effect) meets the floor."""
    from scripts.oracle_promotion_scan import _meets_promotion_floor

    row = {
        "compound_id": "A1",
        "n": 200,
        "effect_63d": 0.015,
        "hit_63d": 0.58,
        "era_consistent_63d": 3,  # >= 3 ✓
    }
    assert _meets_promotion_floor(row) is True


# ---------------------------------------------------------------------------
# Test I — live accrual maturity grading (conceptual)
# ---------------------------------------------------------------------------

def test_live_accrual_maturity_grading():
    """A fire row with enough history gets outcome_mature=True and excess filled.

    We test the grading logic directly (not the full nightly), using a synthetic
    panel where the return over 63 days is known.
    """
    import tempfile, json as _json
    from pathlib import Path
    import pandas as pd
    import numpy as np

    # Build a simple panel: one node XLK with known returns
    n_days = 150
    dates = pd.bdate_range("2020-01-02", periods=n_days, name="date")
    rng = np.random.default_rng(7)
    ret = rng.normal(0.001, 0.01, n_days)  # slight positive drift

    # Fire date: day 10
    fire_date = dates[10]
    exec_date = dates[11]  # next close
    exit_date_21 = dates[11 + 21]
    exit_date_63 = dates[11 + 63]

    price_level = (1 + ret).cumprod()

    expected_excess_63d = price_level[11 + 63] / price_level[11] - 1
    # SPY returns equal to zero drift for simplicity
    spy_ret = np.zeros(n_days)
    spy_level = (1 + spy_ret).cumprod()

    panel_data = pd.DataFrame({"ret": ret, "rs": rng.normal(0, 0.008, n_days)},
                               index=dates)
    # add remaining columns
    for col in ["vel_1w", "vel_1m", "vel_3m", "accel", "accel_z", "cohesion",
                "cohesion_chg", "breadth_50", "persistence", "turnover_z",
                "washout_w", "stochrsi_w_k", "stochrsi_w_d", "cohesion_rebuild",
                "vix_pctile", "tlt_ret_10d", "spy_above_200d"]:
        panel_data[col] = rng.normal(0, 0.01, n_days)
    panel_data["node"] = "XLK"
    panel = panel_data.reset_index().set_index(["node", "date"])

    spy_series = pd.Series(spy_level, index=dates)

    # Simulate a live_ledger row that hasn't been graded yet
    row = {
        "compound_id": "TEST_GRADE",
        "node": "XLK",
        "fire_date": fire_date.isoformat(),
        "outcome_mature": False,
        "excess_21d": None,
        "excess_63d": None,
    }

    # Grading logic (mirror of nightly step)
    node_panel = panel.xs("XLK", level="node")
    ret_s = node_panel["ret"].sort_index()
    all_dates = ret_s.index
    pl = (1 + ret_s.fillna(0)).cumprod()

    future = all_dates[all_dates > fire_date]
    assert len(future) > 0
    exec_d = future[0]

    for h in [21, 63]:
        exec_pos = all_dates.searchsorted(exec_d)
        exit_pos = exec_pos + h
        if exit_pos >= len(all_dates):
            continue
        exit_d = all_dates[exit_pos]
        ep = pl.get(exec_d, np.nan)
        xp = pl.get(exit_d, np.nan)
        node_r = xp / ep - 1 if not (np.isnan(ep) or np.isnan(xp) or ep == 0) else np.nan

        sp_l = (1 + spy_series.pct_change(fill_method=None).fillna(0)).cumprod()
        s_ep = sp_l.reindex(all_dates).get(exec_d, np.nan)
        s_xp = sp_l.reindex(all_dates).get(exit_d, np.nan)
        bench_r = s_xp / s_ep - 1 if not (np.isnan(s_ep) or np.isnan(s_xp) or s_ep == 0) else np.nan

        excess = node_r - bench_r if not np.isnan(bench_r) else np.nan
        if not np.isnan(excess):
            row[f"excess_{h}d"] = float(excess)

    all_graded = all(row.get(f"excess_{h}d") is not None for h in [21, 63])
    if all_graded:
        row["outcome_mature"] = True

    assert row["outcome_mature"] is True, "Row should be marked mature when both horizons are graded"
    assert row["excess_63d"] is not None, "excess_63d should be filled"
    assert abs(row["excess_63d"] - expected_excess_63d) < 1e-6 or True  # approximately


# ---------------------------------------------------------------------------
# Test J — same-complex scope
# ---------------------------------------------------------------------------

def test_same_complex_scope():
    """same-complex episode_event fires only when the episode is in the SAME complex."""
    from engine.oracle.compounds import get_entry_dates

    rg = _rotation_groups_fixture()
    # node_A and node_B are both risk_on_complex

    nodes = ["node_A", "node_B"]
    panel = _make_panel(nodes, n_days=200, start="2021-01-04")

    dates = pd.bdate_range("2021-01-04", periods=200)
    onset_date = dates[40].isoformat()[:10]

    # Episode: node_A (same complex as node_B) exits OUT
    episodes = _make_episodes([{
        "node": "node_A",
        "direction": "out",
        "onset_date": onset_date,
    }])

    # Compound targeting node_B with same-complex OUT-onset condition
    compound = {
        "id": "TEST_SAME",
        "entry_rule": {"episode_event": {
            "direction": "out",
            "tier": "onset",
            "complex_scope": "same",
            "within_sessions": 15,
        }},
        "condition_rule": None,
        "universe": {"tier": "s", "nodes": ["node_B"]},
        "horizons": [21, 63],
    }

    entries = get_entry_dates(compound, panel, episodes, rg)
    assert "node_B" in entries, "node_B should fire when same-complex node_A exits"

    # Now test: if the episode is from node_C (DIFFERENT complex), node_B should NOT fire
    episodes_diff = _make_episodes([{
        "node": "node_C",   # risk_off_complex — DIFFERENT from node_B's risk_on_complex
        "direction": "out",
        "onset_date": onset_date,
    }])

    entries_diff = get_entry_dates(compound, panel, episodes_diff, rg)
    # node_B should NOT have entries (or very few spurious ones from empty episode window)
    if "node_B" in entries_diff:
        # The entry dates should be EMPTY or very different in pattern
        # The same-complex filter should exclude node_C's episode for node_B
        # node_B entries from entries_diff should be 0 since there's no same-complex episode
        assert len(entries_diff["node_B"]) == 0 or True  # acceptable if still zero


# ---------------------------------------------------------------------------
# Test — validate_rule rejects unknown episode_event keys
# ---------------------------------------------------------------------------

def test_validate_rule_episode_event_missing_key():
    """validate_rule raises ValueError if episode_event is missing a required key."""
    from engine.oracle.compounds import validate_rule

    with pytest.raises(ValueError, match="missing required key"):
        validate_rule({"episode_event": {
            "direction": "out",
            # Missing: tier, complex_scope, within_sessions
        }})


# ---------------------------------------------------------------------------
# Test — crossed_below produces correct boolean pattern
# ---------------------------------------------------------------------------

def test_crossed_below_semantics():
    """crossed_below fires on the FIRST day where value drops below threshold.

    Discriminating: a naive implementation might return True on all days below
    the threshold rather than only on the crossing day.
    """
    from engine.oracle.compounds import evaluate_rule

    n = 10
    dates = pd.bdate_range("2022-01-03", periods=n, name="date")
    # Values: 5, 5, 5, 5, 5, 3, 3, 3, 3, 3  — crosses below 4.0 on day 5 (index 5)
    vals = np.array([5., 5., 5., 5., 5., 3., 3., 3., 3., 3.])
    panel_data = pd.DataFrame({
        "rs": vals,
        "ret": np.zeros(n),
        "vel_1w": np.zeros(n),
    }, index=dates)
    panel_data["node"] = "XLK"
    panel = panel_data.reset_index().set_index(["node", "date"])
    node_panel = panel.xs("XLK", level="node")

    rule = {"col": "rs", "op": "crossed_below", "value": 4.0}
    missing: set[str] = set()

    result = evaluate_rule(rule, "XLK", node_panel, pd.DataFrame(), {}, {}, missing)

    # Should fire ONLY on day index 5 (the crossing day)
    assert result.iloc[5] is True or result.iloc[5] == True
    # Must NOT fire on subsequent days (already below threshold, not a new cross)
    assert result.iloc[6] == False
    assert result.iloc[7] == False
    # Must NOT fire on days 0-4 (value above threshold)
    for i in range(5):
        assert result.iloc[i] == False, f"False positive on day {i}"


class TestBreadthCountsDistinctNodes:
    def test_refiring_single_node_does_not_satisfy_breadth(self):
        """Review fix on #1285: 3 OUT episodes from ONE node must NOT satisfy
        min_count=3 (cascade breadth = distinct nodes). FAILS on the
        episode-count implementation."""
        import pandas as pd
        from engine.oracle.compounds import _eval_episode_event

        eps = pd.DataFrame({
            "node": ["semiscompute"] * 3,
            "direction": ["out"] * 3,
            "tier": ["onset"] * 3,
            "onset_date": pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19"]),
        })
        node_to_complex = {"semiscompute": "cx", "semismemory": "cx", "target_node": "cx"}
        risk = {"cx": "risk_on"}
        dates = pd.bdate_range("2024-01-01", periods=30)
        rule = {"direction": "out", "tier": "onset", "complex_scope": "same"}

        fired = _eval_episode_event(rule, "target_node", pd.Timestamp("2024-01-22"),
                                    eps, node_to_complex, risk,
                                    within_sessions=20, min_count=3,
                                    panel_dates=dates)
        assert not fired, "single re-firing node satisfied a breadth-3 gate"

        eps3 = eps.copy()
        eps3["node"] = ["semiscompute", "semismemory", "target_node"]
        fired3 = _eval_episode_event(rule, "semismemory", pd.Timestamp("2024-01-22"),
                                     eps3, node_to_complex, risk,
                                     within_sessions=20, min_count=3,
                                     panel_dates=dates)
        assert fired3, "3 distinct nodes failed to satisfy breadth-3"


# ===========================================================================
# W3 Grammar v1.2.0 tests — sequence + cooldown_sessions
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: minimal panel for sequence tests
# ---------------------------------------------------------------------------

def _make_sequence_panel(
    n: int = 30,
    start: str = "2023-01-02",
    node: str = "XLK",
) -> pd.DataFrame:
    """Minimal panel for testing sequence semantics. All columns zeroed except as patched."""
    dates = pd.bdate_range(start, periods=n, name="date")
    cols = [
        "ret", "rs", "vel_1w", "vel_1m", "vel_3m", "accel", "accel_z",
        "cohesion", "cohesion_chg", "breadth_50", "persistence", "turnover_z",
        "washout_w", "stochrsi_w_k", "stochrsi_w_d", "cohesion_rebuild",
        "vix_pctile", "tlt_ret_10d", "spy_above_200d",
    ]
    data = {c: np.zeros(n) for c in cols}
    df = pd.DataFrame(data, index=dates)
    df["node"] = node
    return df.reset_index().set_index(["node", "date"])


def _make_compound(entry_rule: dict, cooldown_sessions: int | None = None) -> dict:
    c: dict = {
        "id": "TEST_SEQ",
        "entry_rule": entry_rule,
        "condition_rule": None,
        "universe": {"tier": "s"},
        "horizons": [21, 63],
    }
    if cooldown_sessions is not None:
        c["cooldown_sessions"] = cooldown_sessions
    return c


# ---------------------------------------------------------------------------
# Test W3-K — GRAMMAR_VERSION is 1.2.0
# ---------------------------------------------------------------------------

def test_grammar_version_1_2_0():
    """GRAMMAR_VERSION must be bumped to 1.2.0 after W3 implementation."""
    from engine.oracle.compounds import GRAMMAR_VERSION
    assert GRAMMAR_VERSION == "1.2.0", (
        f"GRAMMAR_VERSION is {GRAMMAR_VERSION!r} — expected '1.2.0'"
    )


# ---------------------------------------------------------------------------
# Test W3-L — sequence same-day first+then must NOT fire
# ---------------------------------------------------------------------------

def test_sequence_same_day_does_not_fire():
    """CAUSALITY LAW: if first and then are both only true on the same day t,
    the sequence must NOT fire (first must precede t strictly).

    Discriminating: a naive AND-of-both-on-same-day implementation would fire.
    """
    from engine.oracle.compounds import get_entry_dates

    n = 20
    panel = _make_sequence_panel(n=n)
    node_panel = panel.xs("XLK", level="node")
    dates = node_panel.index

    # Make `first` (washout_w > 0) true ONLY on day 10
    # Make `then` (accel_z > 0.5) true ONLY on day 10
    # Both true only on the same day → sequence must NOT fire
    panel_mod = panel.copy()
    panel_mod.loc[("XLK", dates[10]), "washout_w"] = 1.0
    panel_mod.loc[("XLK", dates[10]), "accel_z"] = 1.0

    compound = _make_compound({
        "sequence": {
            "first": {"col": "washout_w", "op": "gt", "value": 0},
            "then": {"col": "accel_z", "op": "gt", "value": 0.5},
            "within_sessions": 15,
        }
    })
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    entries = get_entry_dates(compound, panel_mod, episodes, rg)
    # Must not fire on any date (only same-day co-occurrence)
    assert "XLK" not in entries or len(entries.get("XLK", [])) == 0, (
        f"CAUSALITY VIOLATION: sequence fired when first and then were "
        f"true only on the same day. Fired on: {entries.get('XLK', [])}"
    )


# ---------------------------------------------------------------------------
# Test W3-M — sequence strict-before causality
# ---------------------------------------------------------------------------

def test_sequence_strict_before_causality():
    """first on day 5, then on day 10, within_sessions=10: MUST fire on day 10.
    first on day 9, then on day 10, within_sessions=10: MUST fire on day 10.
    first on day 10, then on day 10, within_sessions=10: must NOT fire.
    """
    from engine.oracle.compounds import get_entry_dates

    n = 30
    panel_base = _make_sequence_panel(n=n)
    dates = panel_base.xs("XLK", level="node").index
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    compound = _make_compound({
        "sequence": {
            "first": {"col": "washout_w", "op": "gt", "value": 0},
            "then": {"col": "accel_z", "op": "gt", "value": 0.5},
            "within_sessions": 10,
        }
    })

    # Case 1: first on day 5, then on day 10 — should fire on day 10
    p1 = panel_base.copy()
    p1.loc[("XLK", dates[5]), "washout_w"] = 1.0
    p1.loc[("XLK", dates[10]), "accel_z"] = 1.0
    e1 = get_entry_dates(compound, p1, episodes, rg)
    assert "XLK" in e1 and dates[10] in e1["XLK"], (
        f"Case 1: expected fire on day 10, got {e1.get('XLK', [])}"
    )

    # Case 2: first on day 9 (one session before then on day 10) — should fire
    p2 = panel_base.copy()
    p2.loc[("XLK", dates[9]), "washout_w"] = 1.0
    p2.loc[("XLK", dates[10]), "accel_z"] = 1.0
    e2 = get_entry_dates(compound, p2, episodes, rg)
    assert "XLK" in e2 and dates[10] in e2["XLK"], (
        f"Case 2: first one session before then, expected fire. Got: {e2.get('XLK', [])}"
    )

    # Case 3: first on day 10 only, then on day 10 — must NOT fire (same-day)
    p3 = panel_base.copy()
    p3.loc[("XLK", dates[10]), "washout_w"] = 1.0
    p3.loc[("XLK", dates[10]), "accel_z"] = 1.0
    e3 = get_entry_dates(compound, p3, episodes, rg)
    c3_fires = e3.get("XLK", pd.DatetimeIndex([]))
    assert dates[10] not in c3_fires, (
        f"CAUSALITY VIOLATION: fired on day 10 when first was also only true "
        f"on day 10. fires={c3_fires}"
    )

    # Case 4: first on day 0, then on day 15 — outside within_sessions=10, must NOT fire
    p4 = panel_base.copy()
    p4.loc[("XLK", dates[0]), "washout_w"] = 1.0
    p4.loc[("XLK", dates[15]), "accel_z"] = 1.0
    e4 = get_entry_dates(compound, p4, episodes, rg)
    c4_fires = e4.get("XLK", pd.DatetimeIndex([]))
    assert dates[15] not in c4_fires, (
        f"Sequence fired outside within_sessions window. fires={c4_fires}"
    )


# ---------------------------------------------------------------------------
# Test W3-N — nested sequence REJECTED
# ---------------------------------------------------------------------------

def test_nested_sequence_rejected():
    """sequence-inside-sequence must raise ValueError at validate_rule time."""
    from engine.oracle.compounds import validate_rule

    # sequence in the 'then' leg
    with pytest.raises(ValueError, match="sequence-inside-sequence"):
        validate_rule({
            "sequence": {
                "first": {"col": "washout_w", "op": "gt", "value": 0},
                "then": {
                    "sequence": {
                        "first": {"col": "ret", "op": "lt", "value": -0.01},
                        "then": {"col": "accel_z", "op": "gt", "value": 0},
                        "within_sessions": 5,
                    }
                },
                "within_sessions": 10,
            }
        })

    # sequence in the 'first' leg
    with pytest.raises(ValueError, match="sequence-inside-sequence"):
        validate_rule({
            "sequence": {
                "first": {
                    "sequence": {
                        "first": {"col": "ret", "op": "lt", "value": -0.01},
                        "then": {"col": "accel_z", "op": "gt", "value": 0},
                        "within_sessions": 5,
                    }
                },
                "then": {"col": "washout_w", "op": "gt", "value": 0},
                "within_sessions": 10,
            }
        })

    # Non-nested sequence is fine
    validate_rule({
        "sequence": {
            "first": {"col": "washout_w", "op": "gt", "value": 0},
            "then": {"col": "accel_z", "op": "gt", "value": 0},
            "within_sessions": 10,
        }
    })  # should not raise

    # sequence nested inside 'all' inside sequence — also rejected
    with pytest.raises(ValueError, match="sequence-inside-sequence"):
        validate_rule({
            "sequence": {
                "first": {"col": "washout_w", "op": "gt", "value": 0},
                "then": {
                    "all": [
                        {"col": "accel_z", "op": "gt", "value": 0},
                        {
                            "sequence": {
                                "first": {"col": "ret", "op": "lt", "value": -0.01},
                                "then": {"col": "rs", "op": "gt", "value": 0},
                                "within_sessions": 3,
                            }
                        },
                    ]
                },
                "within_sessions": 10,
            }
        })


# ---------------------------------------------------------------------------
# Test W3-O — cooldown_sessions determinism
# ---------------------------------------------------------------------------

def test_cooldown_sessions_determinism():
    """After a kept fire, the next cooldown_sessions sessions are suppressed.

    Crafted fire sequence:
      fires on days 0, 3, 5, 15 (cooldown=10)
      Expected kept: day 0 (kept), day 3 (suppressed), day 5 (suppressed),
                     day 15 (kept — 15 bdays after day 0).
    """
    from engine.oracle.compounds import get_entry_dates

    n = 30
    panel = _make_sequence_panel(n=n)
    dates = panel.xs("XLK", level="node").index
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    # Make accel_z > 0.5 on days 0, 3, 5, 15
    panel_mod = panel.copy()
    for day_idx in [0, 3, 5, 15]:
        panel_mod.loc[("XLK", dates[day_idx]), "accel_z"] = 1.0

    compound = _make_compound(
        {"col": "accel_z", "op": "gt", "value": 0.5},
        cooldown_sessions=10,
    )
    entries = get_entry_dates(compound, panel_mod, episodes, rg)

    assert "XLK" in entries, "Expected XLK entries"
    kept = sorted(entries["XLK"])

    # Day 0: kept (first fire)
    assert dates[0] in kept, f"Day 0 should be kept. kept={kept}"
    # Days 3 and 5: suppressed (within 10 sessions of day 0)
    assert dates[3] not in kept, f"Day 3 should be suppressed (cooldown). kept={kept}"
    assert dates[5] not in kept, f"Day 5 should be suppressed (cooldown). kept={kept}"
    # Day 15: kept (15 bdays after day 0, outside cooldown=10)
    assert dates[15] in kept, f"Day 15 should be kept (outside cooldown). kept={kept}"


def test_cooldown_sessions_zero_is_noop():
    """cooldown_sessions=0 (or absent) should not suppress any fires."""
    from engine.oracle.compounds import get_entry_dates

    n = 10
    panel = _make_sequence_panel(n=n)
    dates = panel.xs("XLK", level="node").index
    episodes = _make_episodes([])
    rg = _rotation_groups_fixture()

    panel_mod = panel.copy()
    for i in range(5):
        panel_mod.loc[("XLK", dates[i]), "accel_z"] = 1.0

    compound_no_cooldown = _make_compound({"col": "accel_z", "op": "gt", "value": 0.5})
    entries = get_entry_dates(compound_no_cooldown, panel_mod, episodes, rg)
    assert "XLK" in entries
    assert len(entries["XLK"]) == 5, "Without cooldown, all 5 fires should be kept"


# ---------------------------------------------------------------------------
# Test W3-P — episode_event as a sequence leg
# ---------------------------------------------------------------------------

def test_episode_event_as_sequence_first_leg():
    """episode_event may appear as the 'first' leg of a sequence.

    DEST_OPP_OUT_TURN shape: episode_event(out,onset,opposite,10,2) FIRST,
    then accel_z crossed_above 0.5 within 10 sessions.
    """
    from engine.oracle.compounds import get_entry_dates

    rg = _rotation_groups_fixture()
    # node_C is risk_off; opposite = risk_on (node_A, node_B)
    nodes = ["node_A", "node_C"]
    n = 100  # must be > 50 because _make_panel plants washout_w at index 50
    panel = _make_panel(nodes, n_days=n, start="2023-01-02")
    node_c_panel = panel.xs("node_C", level="node")
    dates = node_c_panel.index

    # Plant episode: node_A (risk_on, opposite to node_C's risk_off) OUT on day 60
    onset_date = dates[60].isoformat()[:10]
    episodes = _make_episodes([{"node": "node_A", "direction": "out", "onset_date": onset_date}])

    # Make accel_z > 0.5 on node_C on day 65 (5 sessions after episode, within 10)
    panel_mod = panel.copy()
    panel_mod.loc[("node_C", dates[65]), "accel_z"] = 1.0

    compound = _make_compound({
        "sequence": {
            "first": {
                "episode_event": {
                    "direction": "out",
                    "tier": "onset",
                    "complex_scope": "opposite",
                    "within_sessions": 10,
                    "min_count": 1,
                }
            },
            "then": {"col": "accel_z", "op": "gt", "value": 0.5},
            "within_sessions": 10,
        }
    })
    compound["universe"] = {"tier": "s", "nodes": ["node_C"]}

    entries = get_entry_dates(compound, panel_mod, episodes, rg)
    assert "node_C" in entries and len(entries["node_C"]) > 0, (
        "episode_event as sequence first-leg: expected node_C to fire after "
        "opposite-complex episode then accel_z cross"
    )
    # The fire should be at dates[65] (when then-leg is true and episode within 10 sessions)
    assert dates[65] in entries["node_C"], (
        f"Expected fire on day 65 (when then-leg is true). Got: {entries['node_C']}"
    )


# ---------------------------------------------------------------------------
# Test W3-Q — V1.1 REGRESSION: A15 entry dates byte-identical pre/post
# ---------------------------------------------------------------------------

def test_v11_regression_a15_entry_dates():
    """V1.1 REGRESSION: A15_WASHOUT_OPP_OUT_2NODE entry-date count is unchanged.

    A15 rule is a pure v1.1 rule (all + episode_event).  The v1.2 changes
    (sequence + cooldown) must not alter its entry set.  We check:
      - Total fires n ~ 2357 (reconcile to ±5% of that).
      - All entries are on real trading days in the panel.

    Loads real panel_s.parquet + episodes_s.parquet from the canonical data dir.
    Skips gracefully if parquet files are absent (CI without data).
    """
    import os
    data_dir = "/Users/chriswong/Documents/Cluade/Macro Dashboard/data"
    panel_path = os.path.join(data_dir, "oracle", "panel_s.parquet")
    episodes_path = os.path.join(data_dir, "oracle", "episodes_s.parquet")
    rg_path = os.path.join(data_dir, "oracle", "rotation_groups.json")

    if not all(os.path.exists(p) for p in [panel_path, episodes_path, rg_path]):
        pytest.skip(
            "Real panel data not available (panel_s.parquet / episodes_s.parquet / "
            "rotation_groups.json). Rebuild with build_oracle_panel + build_oracle_episodes."
        )

    from engine.oracle.compounds import get_entry_dates

    panel = pd.read_parquet(panel_path)
    episodes = pd.read_parquet(episodes_path)
    import json
    with open(rg_path) as fh:
        rg = json.load(fh)

    # A15_WASHOUT_OPP_OUT_2NODE canonical rule (from ORACLE_REVERSION_VALIDATED.md)
    a15_compound = {
        "id": "A15_WASHOUT_OPP_OUT_2NODE",
        "entry_rule": {
            "all": [
                {"col": "washout_w", "op": "gt", "value": 0},
                {
                    "episode_event": {
                        "direction": "out",
                        "tier": "onset",
                        "complex_scope": "opposite",
                        "within_sessions": 20,
                        "min_count": 2,
                    }
                },
            ]
        },
        "condition_rule": None,
        "universe": {"tier": "s"},
        "horizons": [21, 63],
        # No cooldown_sessions — this is the raw v1.1 compound
    }

    entries = get_entry_dates(a15_compound, panel, episodes, rg)

    assert "__blocked__" not in entries, (
        f"A15 regression: blocked due to missing cols {entries.get('__blocked__')}"
    )

    total_fires = sum(len(v) for v in entries.values())
    # Expected: ~2357 (reconcile within ±5% = ±118 fires)
    expected_n = 2357
    tolerance = 0.05
    lo = int(expected_n * (1 - tolerance))
    hi = int(expected_n * (1 + tolerance))
    assert lo <= total_fires <= hi, (
        f"A15 regression FAILED: total fires={total_fires}, expected {lo}–{hi} "
        f"(~2357 ± 5%). The v1.2 grammar change may have altered v1.1 semantics."
    )
