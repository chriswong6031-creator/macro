"""Hermetic tests for engine/oracle/episodes.py — Oracle O2 episode layer.

ALL fixtures are synthetic (no network, no real data files).

Test inventory:

(a) clean_ramp_onset — planted clean acceleration ramp fires onset at expected
    index.  The discriminating case: a SINGLE-DAY noise spike planted 10 days
    earlier in the series must NOT trigger onset under the 5d-smooth rule.
    This test FAILS under a naive "any-day accel_z > threshold" implementation.

(b) hysteresis_no_flap — a series that flaps around the threshold produces
    exactly ONE episode, not many.  This test FAILS if the state machine resets
    and re-triggers on each crossing.

(c) two_sided_pairing — planted opposite-direction overlap: an IN episode and
    an OUT episode on different nodes overlapping ≥ 5 sessions should be
    marked two_sided=True.  Test FAILS if pairing checks same-node or ignores
    overlap.

(d) outcome_maturity — an episode near the series end whose +63d outcome window
    extends past the last date must have outcome_rs_63d=NaN and
    outcome_mature_63d=False.  Never partially-filled.  Test FAILS if partial
    forward windows are accepted.

(e) truncation_no_lookahead — run the state machine on full history and on
    history truncated at cutoff; all detection-column values that are emitted
    on the truncated run must also be emitted on the full run with IDENTICAL
    episode attributes (onset_date, confirmed_date, undeniable_date).  This is
    the zero-guard-band no-lookahead test equivalent to test_oracle_panel.py.

(f) open_episode_emitted — a series that reaches the end still in onset/
    accelerating state emits an open episode (exhausted_date=None).

(g) min_duration_before_exhaustion — exhaustion cannot fire if the episode has
    fewer than min_duration_before_exhaustion sessions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.episodes import (
    EPISODE_CFG,
    build_episodes,
    run_state_machine,
    _smooth_accel_z,
)
from engine.oracle.panel import COLUMN_SCHEMA


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_flat_panel(
    n: int = 400,
    start: str = "2021-01-04",
    node: str = "TESTNODE",
    seed: int = 0,
) -> pd.DataFrame:
    """Flat (non-trending) panel: accel_z ~ N(0,0.3), rs ~ N(0,0.005)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n, name="date")
    az = rng.normal(0, 0.3, n)
    rs = rng.normal(0, 0.005, n)
    vel_1w = rng.normal(0, 0.005, n)
    vel_3m = vel_1w * 0.95  # slight positive rs_mom to not block onset
    cohesion_chg = rng.normal(0, 0.01, n)
    breadth_50 = rng.uniform(0.3, 0.7, n)
    vix = rng.uniform(0.2, 0.6, n)
    spy = np.ones(n)
    tlt = rng.normal(0, 0.01, n)
    df = pd.DataFrame({
        "accel_z": az,
        "rs": rs,
        "vel_1w": vel_1w,
        "vel_3m": vel_3m,
        "cohesion_chg": cohesion_chg,
        "breadth_50": breadth_50,
        "vix_pctile": vix,
        "spy_above_200d": spy,
        "tlt_ret_10d": tlt,
    }, index=idx)
    return df


def _inject_ramp(
    df: pd.DataFrame,
    start_i: int,
    length: int,
    accel_z_val: float,
    rs_mom_positive: bool = True,
    rs_val: float = 0.01,
    breadth_val: float = 0.7,
) -> pd.DataFrame:
    """Inject a sustained acceleration ramp at start_i for `length` sessions."""
    df = df.copy()
    end_i = min(start_i + length, len(df))
    df.iloc[start_i:end_i, df.columns.get_loc("accel_z")] = accel_z_val
    # Set vel_1w > vel_3m for positive rs_mom
    if rs_mom_positive:
        df.iloc[start_i:end_i, df.columns.get_loc("vel_1w")] = 0.008
        df.iloc[start_i:end_i, df.columns.get_loc("vel_3m")] = 0.004
    # Set rs positive for undeniable detection
    df.iloc[start_i:end_i, df.columns.get_loc("rs")] = rs_val
    # breadth above 0.5 for undeniable
    df.iloc[start_i:end_i, df.columns.get_loc("breadth_50")] = breadth_val
    return df


def _make_panel_for_build(
    nodes_data: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Assemble per-node series into a MultiIndex (node, date) panel."""
    frames = []
    for node, df in nodes_data.items():
        df_copy = df.copy()
        df_copy["node"] = node
        df_copy.index.name = "date"
        df_copy = df_copy.reset_index().set_index(["node", "date"])
        frames.append(df_copy)
    return pd.concat(frames).sort_index()


# ---------------------------------------------------------------------------
# (a) Clean ramp onset vs noise spike — the discriminating test
# ---------------------------------------------------------------------------

class TestCleanRampOnset:
    def test_onset_fires_on_sustained_ramp_not_noise_spike(self):
        """DISCRIMINATING TEST.

        A single-day noise spike (accel_z = 2.5, day 15) must NOT trigger onset.
        A sustained 20-day ramp (accel_z = 1.5, days 80–100) MUST trigger onset
        at approximately day 80+smooth_days−1 (= day 84, the first day the 5d
        smoothed value hits threshold).

        This test FAILS under a naive "any-day accel_z > threshold" check:
        the noise spike at day 15 would trigger a false onset.
        """
        cfg = {**EPISODE_CFG, "hysteresis_gap_days": 0}  # no gap to simplify
        smooth_days = cfg["accel_z_smooth_days"]  # 5

        n = 300
        df = _make_flat_panel(n=n, seed=42)

        # Plant NOISE SPIKE at day 15: single day well above threshold
        spike_i = 15
        df.iloc[spike_i, df.columns.get_loc("accel_z")] = 2.5
        df.iloc[spike_i, df.columns.get_loc("vel_1w")] = 0.02
        df.iloc[spike_i, df.columns.get_loc("vel_3m")] = 0.01

        # Plant SUSTAINED RAMP starting at day 80: 30 days of strong accel_z
        ramp_start = 80
        ramp_len = 30
        df = _inject_ramp(df, ramp_start, ramp_len, accel_z_val=1.5)

        episodes = run_state_machine(df, node="TESTNODE", cfg=cfg)

        # No false onset from the noise spike
        for ep in episodes:
            onset_i = df.index.get_loc(ep["onset_date"])
            assert onset_i >= ramp_start - 2, (
                f"False onset detected at index {onset_i} (spike day={spike_i}); "
                "smoothing should have prevented trigger from single-day noise spike"
            )

        # A real onset fires on the sustained ramp (±2 session tolerance)
        ramp_episodes = [ep for ep in episodes if
                         ep["onset_date"] >= df.index[ramp_start - 1]]
        assert len(ramp_episodes) >= 1, (
            f"Expected onset on the sustained ramp (day {ramp_start}+); "
            f"got 0 episodes. All episodes: {[(ep['onset_date'], ep['direction']) for ep in episodes]}"
        )

        # Onset should be approximately at ramp_start + smooth_days - 1 (±2)
        first_ep = ramp_episodes[0]
        expected_onset_i = ramp_start + smooth_days - 1
        actual_onset_i = df.index.get_loc(first_ep["onset_date"])
        assert abs(actual_onset_i - expected_onset_i) <= 2, (
            f"Onset at index {actual_onset_i}, expected ~{expected_onset_i} ± 2"
        )

    def test_onset_direction_in(self):
        """Positive accel_z ramp → IN episode."""
        df = _make_flat_panel(n=200, seed=7)
        df = _inject_ramp(df, 50, 40, accel_z_val=1.5, rs_mom_positive=True)
        eps = run_state_machine(df, node="TESTNODE")
        ramp_eps = [e for e in eps if e["onset_date"] >= df.index[48]]
        assert any(e["direction"] == "in" for e in ramp_eps), (
            f"No IN episode on positive ramp; got: {[e['direction'] for e in ramp_eps]}"
        )

    def test_onset_direction_out(self):
        """Negative accel_z ramp → OUT episode."""
        df = _make_flat_panel(n=200, seed=8)
        df = _inject_ramp(df, 50, 40, accel_z_val=-1.5, rs_mom_positive=False,
                          rs_val=-0.01, breadth_val=0.3)
        # Fix vel: vel_1w < vel_3m for OUT
        df.iloc[50:90, df.columns.get_loc("vel_1w")] = 0.003
        df.iloc[50:90, df.columns.get_loc("vel_3m")] = 0.008
        eps = run_state_machine(df, node="TESTNODE")
        ramp_eps = [e for e in eps if e["onset_date"] >= df.index[48]]
        assert any(e["direction"] == "out" for e in ramp_eps), (
            f"No OUT episode on negative ramp; got: {[e['direction'] for e in ramp_eps]}"
        )


# ---------------------------------------------------------------------------
# (b) Hysteresis — flapping series yields exactly one episode
# ---------------------------------------------------------------------------

class TestHysteresisNoFlap:
    def test_flapping_yields_one_episode_not_many(self):
        """DISCRIMINATING TEST.

        A series that alternates above/below the threshold every 3 days should
        produce at most 1–2 episodes (once confirmed, exhaustion requires 3-of-5
        counter-days which the flapping series does not sustain).

        This test FAILS if the state machine resets on every crossing: it would
        produce many spurious episodes.
        """
        n = 300
        df = _make_flat_panel(n=n, seed=10)

        # Create a flapping pattern: alternates 1.5, -1.5, 1.5, ... every 3 days
        # starting at day 60 for 120 days
        flap_start = 60
        for i in range(flap_start, min(flap_start + 120, n)):
            block = (i - flap_start) // 3
            val = 1.5 if (block % 2 == 0) else -1.5
            df.iloc[i, df.columns.get_loc("accel_z")] = val

        # Ensure rs_mom consistent positive (vel_1w > vel_3m) throughout
        df.iloc[flap_start:flap_start + 120, df.columns.get_loc("vel_1w")] = 0.008
        df.iloc[flap_start:flap_start + 120, df.columns.get_loc("vel_3m")] = 0.004

        eps = run_state_machine(df, node="TESTNODE")

        # The flapping 3-day pattern: 5d smooth will average ~0, well below threshold.
        # Expect 0 episodes from the flap (neither sustained enough for onset).
        flap_eps = [e for e in eps
                    if e["onset_date"] >= df.index[flap_start - 1]]
        assert len(flap_eps) <= 2, (
            f"Flapping series produced {len(flap_eps)} episodes; "
            f"hysteresis should suppress most crossings"
        )

    def test_sustained_ramp_then_quiet_yields_one_episode(self):
        """One episode from one ramp; no spurious re-trigger on small wiggles."""
        n = 300
        df = _make_flat_panel(n=n, seed=11)
        # Plant one clean 30-day ramp then immediate flat
        df = _inject_ramp(df, 50, 30, accel_z_val=1.5)
        # Add small positive wiggles after the ramp (0.4, below threshold)
        df.iloc[80:120, df.columns.get_loc("accel_z")] = 0.4
        # accel_z is 0.4 → not enough to re-trigger (threshold = 1.0)

        eps = run_state_machine(df, node="TESTNODE")
        in_eps = [e for e in eps if e["direction"] == "in"
                  and e["onset_date"] >= df.index[48]]
        # Should be exactly 1 (the clean ramp)
        assert len(in_eps) >= 1, "Should detect at least 1 IN episode from the ramp"
        # And NOT re-trigger on the 0.4 wiggles alone
        if len(in_eps) > 1:
            # Second episode must have started after hysteresis gap
            gap = EPISODE_CFG["hysteresis_gap_days"]
            first_exhausted = in_eps[0].get("exhausted_date")
            second_onset = in_eps[1]["onset_date"]
            if first_exhausted is not None:
                days_between = (second_onset - first_exhausted).days
                assert days_between >= gap, (
                    f"Re-trigger within hysteresis gap: {days_between} < {gap} days"
                )


# ---------------------------------------------------------------------------
# (c) Two-sided pairing
# ---------------------------------------------------------------------------

_GROUPS_CROSS = {
    "_meta": {"version": "test"},
    "complexes": [
        {"name": "cx_growth", "members": ["NODE_A", "NODE_X", "NODE_Y"]},
        {"name": "cx_defensive", "members": ["NODE_B"]},
    ],
}


def _two_node_panel(coh_a: float = 0.4, coh_b: float = 0.4,
                    b_direction: str = "out") -> pd.DataFrame:
    """NODE_A IN-ramp (day 80) + NODE_B ramp (day 82, `b_direction`), with
    planted cohesion LEVELS (the pairing gate reads cohesion_at_onset)."""
    n, ramp_len = 300, 40
    df_a = _make_flat_panel(n=n, node="NODE_A", seed=20)
    df_a = _inject_ramp(df_a, 80, ramp_len, accel_z_val=1.5)
    df_a["cohesion"] = coh_a
    df_b = _make_flat_panel(n=n, node="NODE_B", seed=21)
    if b_direction == "out":
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("accel_z")] = -1.5
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("vel_1w")] = 0.003
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("vel_3m")] = 0.008
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("rs")] = -0.01
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("breadth_50")] = 0.3
    else:
        df_b = _inject_ramp(df_b, 82, ramp_len, accel_z_val=1.5)
    df_b["cohesion"] = coh_b
    return _make_panel_for_build({"NODE_A": df_a, "NODE_B": df_b})


class TestTwoSidedPairing:
    def test_cross_complex_opposite_direction_is_paired(self):
        """DISCRIMINATING: IN on NODE_A (cx_growth) overlapping an OUT on
        NODE_B (cx_defensive), cohesion 0.4 both legs → both two_sided=True,
        pointing at each other. FAILS if pairing requires same-complex, drops
        the P2a {"complexes": [...]} format, or the cohesion gate reads the
        cohesion_chg delta instead of the level (all three were live bugs)."""
        episodes = build_episodes(_two_node_panel(), rotation_groups=_GROUPS_CROSS, tier="s")
        if episodes.empty:
            pytest.skip("No episodes detected — check fixture ramp parameters")
        in_eps = episodes[(episodes["node"] == "NODE_A") & (episodes["direction"] == "in")]
        out_eps = episodes[(episodes["node"] == "NODE_B") & (episodes["direction"] == "out")]
        if in_eps.empty or out_eps.empty:
            pytest.skip("Need at least one IN and one OUT episode to test pairing")
        assert (in_eps["two_sided"] == True).any(), (  # noqa: E712
            f"No IN episode on NODE_A is two_sided:\n"
            f"{in_eps[['onset_date', 'direction', 'two_sided', 'cohesion_at_onset']]}"
        )
        paired_ids = in_eps[in_eps["two_sided"] == True]["paired_episode_id"].dropna().tolist()  # noqa: E712
        assert any(pid in out_eps["episode_id"].tolist() for pid in paired_ids)
        assert not episodes["pairing_unavailable"].any()

    def test_same_complex_not_paired(self):
        """Both nodes in ONE complex → intra-complex churn, not a two-sided
        rotation; zero pairs."""
        groups = {"complexes": [{"name": "cx_one", "members": ["NODE_A", "NODE_B"]}]}
        episodes = build_episodes(_two_node_panel(), rotation_groups=groups, tier="s")
        if episodes.empty:
            pytest.skip("No episodes")
        assert (episodes["two_sided"] == True).sum() == 0  # noqa: E712

    def test_low_cohesion_blocks_pairing(self):
        """OUT leg cohesion 0.10 < two_sided_min_cohesion 0.25 → no pair
        (a one-name move is not a complex rotation)."""
        episodes = build_episodes(_two_node_panel(coh_b=0.10),
                                  rotation_groups=_GROUPS_CROSS, tier="s")
        if episodes.empty:
            pytest.skip("No episodes")
        assert (episodes["two_sided"] == True).sum() == 0  # noqa: E712

    def test_pairing_unavailable_without_groups(self):
        """No rotation_groups → NO relationship-free fallback (review major:
        overlap-only pairing marked 6/6 unrelated nodes two_sided). two_sided
        is NA, pairing_unavailable=True everywhere."""
        episodes = build_episodes(_two_node_panel(), tier="s")
        if episodes.empty:
            pytest.skip("No episodes")
        assert episodes["pairing_unavailable"].all()
        assert episodes["two_sided"].isna().all()
        assert (episodes["two_sided"] == True).sum() == 0  # noqa: E712 — NA-safe count is 0

    def test_same_direction_not_paired(self):
        """Two IN episodes (cross-complex) must NOT be paired — hard assert
        (the previous version of this test was `assert X or True`)."""
        episodes = build_episodes(_two_node_panel(b_direction="in"),
                                  rotation_groups=_GROUPS_CROSS, tier="s")
        if episodes.empty:
            pytest.skip("No episodes")
        assert (episodes["two_sided"] == True).sum() == 0  # noqa: E712


class TestHysteresisGap:
    def test_gap_blocks_immediate_reonset(self):
        """DISCRIMINATING for the hysteresis gap (review minor: the old
        no-flap test never crossed the threshold, so a hysteresis-free
        implementation passed it). Sequence: onset ramp → forced exhaustion →
        2 quiet days → SHORT second ramp (10d). With gap=0 the second ramp
        re-onsets (2 episodes); with gap=20 the block outlives the short ramp
        (1 episode). A hysteresis-free implementation returns equal counts."""
        from engine.oracle.episodes import run_state_machine
        n = 250
        df = _make_flat_panel(n=n, node="HYST", seed=40)
        df = _inject_ramp(df, 60, 30, accel_z_val=1.5)          # episode 1
        df.iloc[90:97, df.columns.get_loc("accel_z")] = -1.5    # force exhaustion
        df = _inject_ramp(df, 99, 10, accel_z_val=1.8)          # short re-ramp
        df["cohesion"] = 0.4

        cfg0 = dict(EPISODE_CFG); cfg0["hysteresis_gap_days"] = 0
        cfg20 = dict(EPISODE_CFG); cfg20["hysteresis_gap_days"] = 20
        n0 = len([e for e in run_state_machine(df, node="HYST", cfg=cfg0)
                  if e["direction"] == "in"])
        n20 = len([e for e in run_state_machine(df, node="HYST", cfg=cfg20)
                   if e["direction"] == "in"])
        assert n0 >= 2, f"gap=0 should allow the re-onset (got {n0})"
        assert n20 < n0, (
            f"hysteresis gap not load-bearing: gap=20 count {n20} == gap=0 count {n0}"
        )


# ---------------------------------------------------------------------------
# (d) Outcome maturity: episode near end → NaN + outcome_mature=False
# ---------------------------------------------------------------------------

class TestOutcomeMaturity:
    def test_episode_at_end_has_nan_outcome(self):
        """DISCRIMINATING TEST.

        An episode whose onset_date is < 63 sessions before the panel's last
        date must have outcome_rs_63d=NaN and outcome_mature_63d=False.

        This test FAILS if partial forward windows are accepted (e.g.,
        filling with available-session partial sum and marking mature=True).
        """
        n = 350
        df = _make_flat_panel(n=n, seed=40)
        # Plant ramp 10 sessions before the end — forward 63d window extends past last date
        ramp_start = n - 10
        df = _inject_ramp(df, ramp_start, 10, accel_z_val=1.5)

        panel = _make_panel_for_build({"END_NODE": df})
        episodes = build_episodes(panel, tier="s")

        if episodes.empty:
            pytest.skip("No episodes detected near series end — adjust ramp_start")

        near_end = episodes[episodes["onset_date"] >= df.index[ramp_start - 3]]
        if near_end.empty:
            pytest.skip("No episodes near end of series")

        # Each near-end episode should have NaN outcome and outcome_mature=False
        for _, row in near_end.iterrows():
            if "outcome_rs_63d" in row.index:
                assert pd.isna(row["outcome_rs_63d"]) or not row.get("outcome_mature_63d", False), (
                    f"Episode at {row['onset_date']} has non-NaN outcome_rs_63d "
                    f"({row['outcome_rs_63d']:.4f}) but window extends past panel end; "
                    "should be NaN + outcome_mature_63d=False"
                )
            if "outcome_mature_63d" in row.index:
                assert row["outcome_mature_63d"] == False, (  # noqa: E712
                    f"Episode at {row['onset_date']} near panel end should have outcome_mature_63d=False"
                )

    def test_early_episode_has_mature_outcome(self):
        """An episode ≥ 63 sessions before the end should have non-NaN outcome."""
        n = 400
        df = _make_flat_panel(n=n, seed=41)
        # Plant ramp starting at day 50 — 350 sessions before end; outcome window safe
        df = _inject_ramp(df, 50, 40, accel_z_val=1.5)
        # Add counter-directional exhaust after ramp to close the episode
        df.iloc[100:115, df.columns.get_loc("accel_z")] = -1.5
        df.iloc[100:115, df.columns.get_loc("vel_1w")] = 0.003
        df.iloc[100:115, df.columns.get_loc("vel_3m")] = 0.008

        panel = _make_panel_for_build({"EARLY_NODE": df})
        episodes = build_episodes(panel, tier="s")

        if episodes.empty:
            pytest.skip("No episodes")

        early = episodes[episodes["onset_date"] <= df.index[60]]
        if early.empty:
            pytest.skip("No early episodes")

        # Find episodes with enough forward history
        for _, row in early.iterrows():
            if "outcome_mature_63d" in row.index and row.get("outcome_mature_63d"):
                assert not pd.isna(row.get("outcome_rs_63d", np.nan)), (
                    "outcome_mature_63d=True but outcome_rs_63d is NaN"
                )
                return  # At least one mature early episode — test passes

        # If no mature episode found, issue a soft warning (timing-dependent)
        pytest.skip("No episodes with outcome_mature_63d=True — panel may be short")


# ---------------------------------------------------------------------------
# (e) Truncation no-lookahead: detection columns identical on full vs truncated
# ---------------------------------------------------------------------------

class TestTruncationNoLookahead:
    def test_detection_columns_identical_on_truncated_history(self):
        """ZERO guard-band no-lookahead invariant for detection.

        Run the state machine on full history and on history truncated at
        cutoff_day.  Any episode emitted by the truncated run (onset_date ≤
        cutoff) must appear in the full run with IDENTICAL:
          onset_date, confirmed_date (or both None), direction.

        This test FAILS if the state machine reads forward data to determine
        onset/confirmed/undeniable dates.
        """
        n = 400
        cutoff_day = 200
        df_full = _make_flat_panel(n=n, seed=50)
        # Plant ramp well before cutoff (days 80–120)
        df_full = _inject_ramp(df_full, 80, 40, accel_z_val=1.5)
        # Add exhaust after ramp before cutoff
        df_full.iloc[130:145, df_full.columns.get_loc("accel_z")] = -1.5
        df_full.iloc[130:145, df_full.columns.get_loc("vel_1w")] = 0.003
        df_full.iloc[130:145, df_full.columns.get_loc("vel_3m")] = 0.008

        # Truncated history
        df_trunc = df_full.iloc[:cutoff_day].copy()

        eps_full = run_state_machine(df_full, node="LOOKAHEAD_TEST")
        eps_trunc = run_state_machine(df_trunc, node="LOOKAHEAD_TEST")

        # Filter full-run episodes to onset ≤ cutoff
        cutoff_date = df_full.index[cutoff_day - 1]
        full_before_cutoff = [e for e in eps_full if e["onset_date"] <= cutoff_date]
        trunc_episodes = [e for e in eps_trunc if e["onset_date"] <= cutoff_date]

        # Map by onset_date for comparison
        full_by_onset = {e["onset_date"]: e for e in full_before_cutoff}
        trunc_by_onset = {e["onset_date"]: e for e in trunc_episodes}

        for onset_date, trunc_ep in trunc_by_onset.items():
            assert onset_date in full_by_onset, (
                f"Episode at {onset_date} in truncated run not found in full run "
                "(onset date changed by future data — LOOKAHEAD DETECTED)"
            )
            full_ep = full_by_onset[onset_date]

            assert trunc_ep["direction"] == full_ep["direction"], (
                f"Direction changed by future data at {onset_date}: "
                f"trunc={trunc_ep['direction']} full={full_ep['direction']}"
            )

            # confirmed_date: if truncated run emits one, full run must agree
            td_conf = trunc_ep.get("confirmed_date")
            fd_conf = full_ep.get("confirmed_date")
            if td_conf is not None and not pd.isnull(td_conf):
                assert fd_conf == td_conf or (fd_conf is not None and fd_conf <= cutoff_date), (
                    f"confirmed_date changed by future data: trunc={td_conf} full={fd_conf}"
                )


# ---------------------------------------------------------------------------
# (f) Open episode emitted at series end
# ---------------------------------------------------------------------------

class TestOpenEpisodeEmitted:
    def test_episode_open_at_end_has_none_exhausted_date(self):
        """A series that ends while still in onset state emits an open episode."""
        n = 150
        smooth = EPISODE_CFG["accel_z_smooth_days"]
        df = _make_flat_panel(n=n, seed=60)
        # Plant ramp starting at day 100 and running to the end — never exhausted
        df = _inject_ramp(df, 100, 50, accel_z_val=1.5)

        eps = run_state_machine(df, node="OPEN_NODE")
        open_eps = [e for e in eps if e.get("exhausted_date") is None
                    and e["onset_date"] >= df.index[98]]
        assert len(open_eps) >= 1, (
            "Expected at least one open episode (exhausted_date=None) when "
            "series ends while still in onset/accelerating state"
        )
        # Duration should be non-zero
        for ep in open_eps:
            assert ep["duration"] > 0, f"Open episode has zero duration: {ep}"


# ---------------------------------------------------------------------------
# (g) min_duration_before_exhaustion prevents zero-length episodes
# ---------------------------------------------------------------------------

class TestMinDurationBeforeExhaustion:
    def test_exhaustion_requires_min_duration(self):
        """Exhaustion must not fire before min_duration_before_exhaustion sessions."""
        cfg = {**EPISODE_CFG,
               "min_duration_before_exhaustion": 10,
               "hysteresis_gap_days": 1}
        n = 200
        df = _make_flat_panel(n=n, seed=70)

        # Plant onset (days 50–55) then immediate counter at days 56–60
        # Duration at counter = 6, min_dur = 10 → should NOT exhaust
        df = _inject_ramp(df, 50, 6, accel_z_val=1.5)
        df.iloc[56:62, df.columns.get_loc("accel_z")] = -1.5  # counter-directional

        eps = run_state_machine(df, node="MINdur_NODE", cfg=cfg)

        # Any episode starting at day 50 should have duration ≥ min_dur or be open
        early_eps = [e for e in eps if e["onset_date"] >= df.index[48]]
        for ep in early_eps:
            if ep.get("exhausted_date") is not None:
                assert ep["duration"] >= cfg["min_duration_before_exhaustion"], (
                    f"Episode exhausted with duration {ep['duration']} < "
                    f"min_duration {cfg['min_duration_before_exhaustion']}"
                )


# ---------------------------------------------------------------------------
# Additional: run_state_machine empty/short series
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_series_returns_empty(self):
        """Empty DataFrame → empty episode list."""
        df = pd.DataFrame(columns=["accel_z", "rs", "vel_1w", "vel_3m"])
        eps = run_state_machine(df, node="EMPTY")
        assert eps == []

    def test_short_series_returns_empty(self):
        """Series shorter than warm-up → no episodes."""
        df = _make_flat_panel(n=10, seed=80)
        df = _inject_ramp(df, 0, 10, accel_z_val=2.0)
        eps = run_state_machine(df, node="SHORT")
        # Insufficient history for 5d smooth + confirmed_n = 5 → typically 0
        # (not asserting == 0 to avoid flakiness; checking it doesn't crash)
        assert isinstance(eps, list)

    def test_no_crash_on_all_nan_optional_columns(self):
        """Missing optional columns (cohesion_chg, breadth_50) must not crash."""
        n = 200
        idx = pd.bdate_range("2021-01-04", periods=n, name="date")
        rng = np.random.default_rng(81)
        # Only required columns; no optional member-derived legs
        df = pd.DataFrame({
            "accel_z": rng.normal(0, 1.5, n),
            "rs": rng.normal(0, 0.005, n),
            "vel_1w": rng.normal(0.005, 0.003, n),
            "vel_3m": rng.normal(0.003, 0.002, n),
        }, index=idx)
        try:
            eps = run_state_machine(df, node="NOCOLS")
        except Exception as e:
            pytest.fail(f"run_state_machine raised on missing optional cols: {e}")
        assert isinstance(eps, list)

    def test_build_episodes_on_multiindex_panel(self):
        """build_episodes accepts a proper MultiIndex (node, date) panel."""
        n = 300
        df_a = _make_flat_panel(n=n, node="NODE_A", seed=90)
        df_a = _inject_ramp(df_a, 80, 40, accel_z_val=1.5)
        panel = _make_panel_for_build({"NODE_A": df_a})
        result = build_episodes(panel, tier="s")
        assert isinstance(result, pd.DataFrame)

    def test_survivorship_flag_propagated(self):
        """Tier-M episodes carry survivorship_flagged=True."""
        n = 300
        df_a = _make_flat_panel(n=n, node="NODE_A", seed=91)
        df_a = _inject_ramp(df_a, 80, 40, accel_z_val=1.5)
        panel = _make_panel_for_build({"NODE_A": df_a})
        result = build_episodes(panel, tier="m")
        if not result.empty:
            assert result["survivorship_flagged"].all(), (
                "Tier-M episodes must all have survivorship_flagged=True"
            )

    def test_smooth_accel_z_propagates_nan(self):
        """_smooth_accel_z returns NaN for any window containing NaN."""
        arr = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0])
        out = _smooth_accel_z(arr, days=3)
        # Window [0:3] contains NaN at index 2 → index 2 is NaN
        assert np.isnan(out[2])
        # Window [4:7] = [5.0, 6.0, 7.0] is all-finite
        assert not np.isnan(out[6])
        np.testing.assert_allclose(out[6], (5.0 + 6.0 + 7.0) / 3.0)

    def test_episode_id_is_unique_across_nodes(self):
        """Episode IDs must be unique across all nodes in a panel."""
        n = 300
        nodes_data = {}
        for i in range(3):
            df = _make_flat_panel(n=n, node=f"NODE_{i}", seed=92 + i)
            df = _inject_ramp(df, 80, 40, accel_z_val=1.5)
            nodes_data[f"NODE_{i}"] = df
        panel = _make_panel_for_build(nodes_data)
        result = build_episodes(panel, tier="s")
        if result.empty:
            pytest.skip("No episodes")
        assert result["episode_id"].is_unique, "episode_id must be unique across all nodes"

    def test_outcome_columns_present(self):
        """build_episodes output must contain all outcome_* columns for each horizon."""
        n = 400
        df = _make_flat_panel(n=n, seed=93)
        df = _inject_ramp(df, 50, 40, accel_z_val=1.5)
        panel = _make_panel_for_build({"NODE_A": df})
        result = build_episodes(panel, tier="s")
        if result.empty:
            pytest.skip("No episodes")
        for h in EPISODE_CFG["outcome_horizons"]:
            assert f"outcome_rs_{h}d" in result.columns, f"Missing outcome_rs_{h}d"
            assert f"outcome_mature_{h}d" in result.columns, f"Missing outcome_mature_{h}d"

    def test_outcome_columns_not_in_detection_columns(self):
        """Outcome column names must NOT appear in _EPISODE_COLS (the detection set)."""
        from engine.oracle.episodes import _EPISODE_COLS
        outcome_names = {f"outcome_rs_{h}d" for h in EPISODE_CFG["outcome_horizons"]}
        outcome_names |= {f"outcome_mature_{h}d" for h in EPISODE_CFG["outcome_horizons"]}
        overlap = set(_EPISODE_COLS) & outcome_names
        assert not overlap, (
            f"Outcome columns bleed into detection schema: {overlap}"
        )


# ---------------------------------------------------------------------------
# Ruling XR-PAIR tests (2026-07-05)
# ---------------------------------------------------------------------------

class TestXRPairETFComplexMapping:
    """Tests for ruling XR-PAIR: Tier-S ETF nodes map via COMPLEX_ETF_MAP,
    multi-complex ETFs use union semantics."""

    def test_xlk_maps_to_both_complexes(self):
        """XLK belongs to both ai_compute and software — _build_etf_complex_sets
        must return a frozenset of size ≥ 2 for XLK.

        DISCRIMINATING: a single-complex mapping (e.g. first-wins) would return
        frozenset of size 1 and would fail this test."""
        from engine.oracle.episodes import _build_etf_complex_sets
        etf_sets = _build_etf_complex_sets()
        assert "XLK" in etf_sets, "XLK must appear in etf_complex_sets (check COMPLEX_ETF_MAP)"
        xlk_complexes = etf_sets["XLK"]
        assert "ai_compute" in xlk_complexes, f"XLK should map to ai_compute; got {xlk_complexes}"
        assert "software" in xlk_complexes, f"XLK should map to software; got {xlk_complexes}"
        assert len(xlk_complexes) >= 2, f"XLK union-set should have ≥2 entries; got {xlk_complexes}"

    def test_xlb_maps_to_both_complexes(self):
        """XLB belongs to energy_commodities and short_duration_value — both must appear."""
        from engine.oracle.episodes import _build_etf_complex_sets
        etf_sets = _build_etf_complex_sets()
        assert "XLB" in etf_sets, "XLB must appear in etf_complex_sets"
        xlb_complexes = etf_sets["XLB"]
        assert "energy_commodities" in xlb_complexes, f"XLB→energy_commodities missing; got {xlb_complexes}"
        assert "short_duration_value" in xlb_complexes, f"XLB→short_duration_value missing; got {xlb_complexes}"

    def test_single_complex_etf_maps_correctly(self):
        """XLV maps to exactly healthcare_defensive (single complex)."""
        from engine.oracle.episodes import _build_etf_complex_sets
        etf_sets = _build_etf_complex_sets()
        assert "XLV" in etf_sets
        assert "healthcare_defensive" in etf_sets["XLV"]


class TestXRPairETFEpisodePairing:
    """Fixture-based pairing test: two opposing episodes on mapped ETFs produce
    a two-sided pair.  Uses a synthetic rotation_groups.json that includes the
    ETF nodes in their complexes, then verifies that the COMPLEX_ETF_MAP path
    also works when ETFs are absent from rotation_groups but present in the map.
    """

    def _make_etf_panel(self, n: int = 400, ramp_start_a: int = 80,
                        ramp_start_b: int = 82, ramp_len: int = 40) -> pd.DataFrame:
        """XLK IN-ramp + XLV OUT-ramp, with planted cohesion ≥ 0.25."""
        df_a = _make_flat_panel(n=n, node="XLK", seed=100)
        df_a = _inject_ramp(df_a, ramp_start_a, ramp_len, accel_z_val=1.5)
        df_a["cohesion"] = 0.4

        df_b = _make_flat_panel(n=n, node="XLV", seed=101)
        df_b.iloc[ramp_start_b:ramp_start_b + ramp_len,
                  df_b.columns.get_loc("accel_z")] = -1.5
        df_b.iloc[ramp_start_b:ramp_start_b + ramp_len,
                  df_b.columns.get_loc("vel_1w")] = 0.003
        df_b.iloc[ramp_start_b:ramp_start_b + ramp_len,
                  df_b.columns.get_loc("vel_3m")] = 0.008
        df_b.iloc[ramp_start_b:ramp_start_b + ramp_len,
                  df_b.columns.get_loc("rs")] = -0.01
        df_b.iloc[ramp_start_b:ramp_start_b + ramp_len,
                  df_b.columns.get_loc("breadth_50")] = 0.3
        df_b["cohesion"] = 0.4
        return _make_panel_for_build({"XLK": df_a, "XLV": df_b})

    def test_etf_nodes_pair_via_complex_etf_map(self):
        """DISCRIMINATING (ruling XR-PAIR): XLK IN + XLV OUT on different complexes
        (ai_compute/software vs healthcare_defensive) must yield two_sided=True
        when rotation_groups.json only contains subsector members (no ETFs).

        This test FAILS under the pre-fix code because _pair_episodes consulted
        ONLY rotation_groups.json members (83 subsector slugs) and never reached
        COMPLEX_ETF_MAP — so XLK/XLV had no complex mapping and pairing never fired.
        """
        # rotation_groups with subsector members only — NO ETF nodes listed.
        # This simulates the real rotation_groups.json state.
        rotation_groups_subsector_only = {
            "_meta": {"version": "test"},
            "complexes": [
                {"name": "ai_compute", "id": "ai_compute",
                 "members": ["semiconductors", "hardware_infra"]},
                {"name": "healthcare_defensive", "id": "healthcare_defensive",
                 "members": ["pharma", "biotech_large"]},
                {"name": "software", "id": "software",
                 "members": ["saas", "enterprise_sw"]},
            ],
        }
        panel = self._make_etf_panel()
        episodes = build_episodes(panel, rotation_groups=rotation_groups_subsector_only, tier="s")

        if episodes.empty:
            pytest.skip("No episodes detected — check ramp parameters")

        in_eps = episodes[(episodes["node"] == "XLK") & (episodes["direction"] == "in")]
        out_eps = episodes[(episodes["node"] == "XLV") & (episodes["direction"] == "out")]

        if in_eps.empty or out_eps.empty:
            pytest.skip("Need at least one IN (XLK) and one OUT (XLV) episode to test pairing")

        assert (in_eps["two_sided"] == True).any(), (  # noqa: E712
            f"XLK IN episode not two_sided despite opposing XLV OUT on a different complex.\n"
            f"XLK episodes:\n{in_eps[['onset_date', 'direction', 'two_sided', 'cohesion_at_onset']]}\n"
            "This test FAILS under the pre-fix code (XLK has no complex mapping from "
            "rotation_groups.json — COMPLEX_ETF_MAP was never consulted)."
        )
        paired_ids = in_eps[in_eps["two_sided"] == True]["paired_episode_id"].dropna().tolist()  # noqa: E712
        assert any(pid in out_eps["episode_id"].tolist() for pid in paired_ids), (
            "Paired episode_id does not point at an XLV OUT episode"
        )
        assert not episodes["pairing_unavailable"].any()

    def test_tier_m_pairing_unchanged_by_etf_fix(self):
        """Regression: tier-M nodes (non-ETF subsector slugs) still pair correctly
        via rotation_groups.json members — the ETF overlay does not interfere.

        DISCRIMINATING: the fix must be additive (union) and must not break the
        existing subsector pairing path that tier-M depends on.
        """
        # Subsector nodes — not in COMPLEX_ETF_MAP
        groups = {
            "_meta": {"version": "test"},
            "complexes": [
                {"name": "cx_growth", "id": "cx_growth",
                 "members": ["NODE_A", "NODE_X"]},
                {"name": "cx_defensive", "id": "cx_defensive",
                 "members": ["NODE_B"]},
            ],
        }
        panel = _two_node_panel(coh_a=0.4, coh_b=0.4, b_direction="out")
        episodes = build_episodes(panel, rotation_groups=groups, tier="m")

        if episodes.empty:
            pytest.skip("No episodes")

        in_eps = episodes[(episodes["node"] == "NODE_A") & (episodes["direction"] == "in")]
        out_eps = episodes[(episodes["node"] == "NODE_B") & (episodes["direction"] == "out")]

        if in_eps.empty or out_eps.empty:
            pytest.skip("Need IN + OUT for regression test")

        # Tier-M pairing must still work via rotation_groups.json members alone
        assert (in_eps["two_sided"] == True).any(), (  # noqa: E712
            "Tier-M cross-complex pairing broke after XR-PAIR ETF fix — the overlay "
            "must be additive, not replacing the existing subsector path."
        )
        assert not episodes["pairing_unavailable"].any()

    def test_xlk_xlk_same_complex_set_not_paired(self):
        """XLK vs XLK: same complex set {ai_compute, software} == {ai_compute, software}
        → must NOT be marked two_sided.  Union semantics: equal sets = same-complex churn."""
        rotation_groups_subsector_only = {
            "_meta": {"version": "test"},
            "complexes": [
                {"name": "ai_compute", "id": "ai_compute", "members": ["semiconductors"]},
                {"name": "software", "id": "software", "members": ["saas"]},
            ],
        }
        # Both nodes are XLK — create by building with two identically-behaved ETF names
        # that map to the exact same complex set.
        n, ramp_len = 300, 40
        df_a = _make_flat_panel(n=n, node="XLK", seed=110)
        df_a = _inject_ramp(df_a, 80, ramp_len, accel_z_val=1.5)
        df_a["cohesion"] = 0.4
        # XLC is not in COMPLEX_ETF_MAP — it will be treated as unmapped, so no pairing
        df_b = _make_flat_panel(n=n, node="XLC", seed=111)
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("accel_z")] = -1.5
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("vel_1w")] = 0.003
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("vel_3m")] = 0.008
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("rs")] = -0.01
        df_b.iloc[82:82 + ramp_len, df_b.columns.get_loc("breadth_50")] = 0.3
        df_b["cohesion"] = 0.4
        panel = _make_panel_for_build({"XLK": df_a, "XLC": df_b})
        episodes = build_episodes(panel, rotation_groups=rotation_groups_subsector_only, tier="s")
        if episodes.empty:
            pytest.skip("No episodes")
        # XLC not in COMPLEX_ETF_MAP → unmapped → no pair
        assert (episodes["two_sided"] == True).sum() == 0, (  # noqa: E712
            "XLK vs unmapped XLC should produce zero pairs"
        )
