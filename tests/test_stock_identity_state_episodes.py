"""Stock Identity W1 — the state tagger is total and exclusive; the catalog segments.

Two claims the registration makes that would otherwise be assertions:

* **Totality + mutual exclusivity.** Every input row maps to exactly one of the eight
  states, including all-missing warm-up rows. First-match-wins precedence gives
  exclusivity; ``range`` as the residual gives totality. A synthetic grid over the
  variables checks both, rather than trusting the reading of the if-chain.
* **Segmentation behavior.** Durable-low detection, censoring at truncation, reclaim
  held vs failed, failed-breakdown recovery, and tier assignment are each exercised
  on a hand-built path where the right answer is known by construction.

Synthetic frames only — fast, offline, no committed-artifact dependency.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity import episodes as ep
from engine.stock_identity import dossier
from engine.stock_identity import state as st

# Small constants so a synthetic path can be short and still resolve.
SC = st.StateConstants(
    g=3.0, theta_dw=0.35, theta_bd=0.15, theta_pb=0.08, theta_up=0.0,
    J=40.0, V=21, E=5, R=126,
)
EC = ep.EpisodeConstants(
    X=1.0, Y=0.10, N=5, k=0.5, z=0.02, M=10, m=5, D1=20, D2=10, S_reclaim=3,
)


def _frame_from_close(close: np.ndarray, start: str = "2020-01-01",
                      wobble: float = 0.005) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(close), name="Date")
    close = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {
            "close": close,
            "high": close * (1.0 + wobble),
            "low": close * (1.0 - wobble),
            "volume": np.full(len(close), 1_000_000.0),
        },
        index=idx,
    )


class TestStateTotalityAndExclusivity:
    def test_every_grid_point_maps_to_exactly_one_known_state(self):
        gaps = (False, True)
        dds = (None, float("nan"), 0.0, -0.05, -0.09, -0.20, -0.35, -0.60)
        d200s = (None, float("nan"), -0.40, -0.15, -0.01, 0.0, 0.02, 0.30)
        slopes = (float("nan"), -1.0, 0.0, 1.0)
        recents = (False, True)
        jumps = (float("nan"), 0.0, 39.9, 40.0, 80.0)

        seen: set[str] = set()
        n = 0
        for gap, dd, d200, slope, recent, jump in itertools.product(
            gaps, dds, d200s, slopes, recents, jumps
        ):
            s = st.classify_single(
                gap_recent=gap, dd=dd, d200=d200, sma200_slope=slope,
                washout_or_breakdown_recent=recent, volp_jump=jump, const=SC,
            )
            assert s in st.STATES, (s, gap, dd, d200, slope, recent, jump)
            seen.add(s)
            n += 1
        assert n > 5000
        # every state must be REACHABLE, or the tagger silently has fewer than eight
        assert seen == set(st.STATES), f"unreachable states: {set(st.STATES) - seen}"

    def test_precedence_is_first_match_wins(self):
        # A row satisfying several rules at once must return the earliest one. Here the
        # gap rule (1) and the deep-washout rule (2) both hold.
        s = st.classify_single(
            gap_recent=True, dd=-0.60, d200=-0.40, sma200_slope=-1.0,
            washout_or_breakdown_recent=True, volp_jump=90.0, const=SC,
        )
        assert s == "post_event_dislocation"
        s2 = st.classify_single(
            gap_recent=False, dd=-0.60, d200=-0.40, sma200_slope=-1.0,
            washout_or_breakdown_recent=True, volp_jump=90.0, const=SC,
        )
        assert s2 == "deep_washout"

    def test_warm_up_rows_fall_through_to_the_residual_state(self):
        s = st.classify_single(
            gap_recent=False, dd=None, d200=None, sma200_slope=None,
            washout_or_breakdown_recent=False, volp_jump=None, const=SC,
        )
        assert s == "range"

    def test_tag_states_assigns_one_state_to_every_row(self):
        rng = np.random.default_rng(3)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 900)))
        df = _frame_from_close(close)
        out = st.tag_states(df, "stocks_tr_v1", SC)
        assert len(out) == len(df)
        assert out["state"].notna().all()
        assert set(out["state"].unique()) <= set(st.STATES)

    def test_gap_basis_follows_the_plane(self):
        df = _frame_from_close(100 + np.arange(300, dtype=float))
        df.insert(0, "open", df["close"])
        assert st.state_variables(df, "baskets_ohlcv_v1")["gap_basis"].iloc[0] == st.GAP_BASIS_OPEN
        # the open-less curated plane must use close-to-close even when `open` exists
        assert st.state_variables(df, "stocks_tr_v1")["gap_basis"].iloc[0] == st.GAP_BASIS_CLOSE

    @staticmethod
    def _render_gap_basis(basis: str) -> str:
        return dossier.render_markdown(
            symbol="X",
            plane_id="test",
            snapshot_row={"n_rows": 0},
            hygiene={},
            raw={},
            percentiles={},
            coverage={},
            unstable={},
            catalog=pd.DataFrame(),
            state_shares=pd.DataFrame(),
            constants_meta={"gap_basis": basis},
            chart_rel=None,
        )

    def test_dossier_gap_prose_matches_the_recorded_basis(self):
        open_text = self._render_gap_basis(st.GAP_BASIS_OPEN)
        open_line = next(line for line in open_text.splitlines() if "Gap basis" in line)
        assert "opening print is compared with the previous close" in open_line
        assert "close-to-close proxy" not in open_line

        close_text = self._render_gap_basis(st.GAP_BASIS_CLOSE)
        close_line = next(line for line in close_text.splitlines() if "Gap basis" in line)
        assert "close-to-close proxy" in close_line


class TestDurableLowDetection:
    def _v_path(self) -> np.ndarray:
        # 200 sessions to seed the 126d high, a 30% fall, then a rebound brisk enough to
        # clear BOTH durable-low gates (k*A0 and z%) inside the N-session window — a
        # slower drift would legitimately leave the leg censored, which is a different
        # test (see TestCensoring).
        up = np.linspace(100.0, 120.0, 200)
        down = np.linspace(120.0, 84.0, 60)
        snapback = np.linspace(84.0, 96.0, 12)
        drift = np.linspace(96.0, 108.0, 60)
        return np.concatenate([up, down, snapback, drift])

    def test_a_qualifying_leg_resolves_at_its_durable_low(self):
        df = _frame_from_close(self._v_path())
        eps = ep.reset_decline_episodes(df, symbol="T", plane_id="stocks_tr_v1", const=EC)
        assert len(eps) >= 1
        e = eps[0]
        assert e.episode_type == "reset_decline"
        assert e.resolution == "durable_low"
        assert e.censored is False
        assert e.anchor_date is not None
        assert e.depth_pct == pytest.approx(0.30, abs=0.02)
        # the anchor must sit at the actual minimum of the leg
        low_date = df["close"].loc[e.start_date : e.end_date].idxmin()
        assert e.anchor_date == low_date

    def test_resolution_is_knowable_only_after_the_survival_window(self):
        df = _frame_from_close(self._v_path())
        e = ep.reset_decline_episodes(df, symbol="T", plane_id="stocks_tr_v1", const=EC)[0]
        assert e.resolution_known_date is not None
        assert e.resolution_known_date > e.anchor_date
        idx = list(df.index)
        assert idx.index(e.resolution_known_date) - idx.index(e.anchor_date) == EC.N

    def test_a_shallow_dip_does_not_qualify(self):
        close = np.concatenate([
            np.linspace(100.0, 120.0, 200),
            np.linspace(120.0, 116.0, 30),   # ~3%, below Y
            np.linspace(116.0, 125.0, 40),
        ])
        eps = ep.reset_decline_episodes(
            _frame_from_close(close), symbol="T", plane_id="stocks_tr_v1", const=EC
        )
        assert eps == []


class TestCensoring:
    def test_a_leg_still_falling_at_truncation_is_censored_with_no_anchor(self):
        close = np.concatenate([
            np.linspace(100.0, 120.0, 200),
            np.linspace(120.0, 45.0, 150),  # never stops falling
        ])
        df = _frame_from_close(close)
        eps = ep.reset_decline_episodes(
            df, symbol="T", plane_id="stocks_tr_v1", const=EC,
            terminated_reason="tape_ended (cause unverified)",
        )
        assert len(eps) == 1
        e = eps[0]
        assert e.resolution == "censored"
        assert e.censored is True
        assert e.anchor_date is None, "a censored episode must carry no anchor"
        assert e.resolution_known_date is None
        assert e.terminated_reason == "tape_ended (cause unverified)"
        assert e.end_date == df.index[-1]

    def test_censored_episodes_are_kept_not_dropped(self):
        close = np.concatenate([np.linspace(100.0, 120.0, 200), np.linspace(120.0, 45.0, 150)])
        cat = ep.build_catalog(
            _frame_from_close(close), symbol="T", plane_id="stocks_tr_v1", const=EC
        )
        decl = cat[cat["episode_type"] == "reset_decline"]
        assert len(decl) == 1
        assert bool(decl.iloc[0]["censored"]) is True


class TestReclaim:
    def _reclaim_frame(self, hold: bool):
        # 260 sessions to seed the 200DMA, then a decline deep enough to hold a
        # `breakdown` state run. The tail is built RELATIVE to the realized 200DMA so
        # the recapture and its outcome are deterministic rather than a lucky
        # intersection of two independently chosen slopes.
        base = np.concatenate([np.linspace(100.0, 130.0, 260), np.linspace(130.0, 88.0, 120)])
        ma = float(pd.Series(base).rolling(200, min_periods=200).mean().iloc[-1])
        if hold:
            tail = np.concatenate([np.linspace(88.0, ma * 1.10, 12), np.full(60, ma * 1.15)])
        else:
            tail = np.concatenate([
                np.linspace(88.0, ma * 1.06, 8),          # recapture
                np.full(4, ma * 1.06),                    # sustained for S_reclaim
                np.linspace(ma * 1.06, ma * 0.70, 8),     # lost again inside M
                np.full(40, ma * 0.70),
            ])
        df = _frame_from_close(np.concatenate([base, tail]))
        states = st.tag_states(df, "stocks_tr_v1", SC)["state"]
        return df, states

    def test_a_held_recapture_resolves_held(self):
        df, states = self._reclaim_frame(hold=True)
        eps = ep.reclaim_episodes(df, states, symbol="T", plane_id="stocks_tr_v1", const=EC)
        assert eps, "no reclaim episode produced"
        assert any(e.resolution == "held" for e in eps)
        e = next(e for e in eps if e.resolution == "held")
        assert e.anchor_date is not None
        assert e.censored is False

    def test_a_lost_recapture_resolves_failed(self):
        df, states = self._reclaim_frame(hold=False)
        eps = ep.reclaim_episodes(df, states, symbol="T", plane_id="stocks_tr_v1", const=EC)
        assert eps, "no reclaim episode produced"
        assert any(e.resolution == "failed" for e in eps)

    def test_one_reclaim_per_breakdown_run(self):
        df, states = self._reclaim_frame(hold=True)
        eps = ep.reclaim_episodes(df, states, symbol="T", plane_id="stocks_tr_v1", const=EC)
        runs = (states == "breakdown").astype(int).diff().eq(1).sum() + int(
            states.iloc[0] == "breakdown"
        )
        assert len(eps) <= int(runs)


class TestFailedBreakdown:
    def test_an_undercut_recovered_within_m_is_a_failed_breakdown(self):
        flat = np.full(80, 100.0) + np.linspace(0, 2, 80)
        dip = np.array([98.0, 96.0, 95.0])
        back = np.array([99.0, 101.0, 103.0, 104.0])
        close = np.concatenate([flat, dip, back, np.full(30, 105.0)])
        eps = ep.failed_breakdown_episodes(
            _frame_from_close(close), symbol="T", plane_id="stocks_tr_v1", const=EC
        )
        assert eps
        e = eps[0]
        assert e.episode_type == "failed_breakdown"
        assert e.resolution == "recovered"
        assert e.anchor_date is not None
        assert e.censored is False

    def test_an_undercut_that_never_recovers_is_not_a_failed_breakdown(self):
        flat = np.full(80, 100.0) + np.linspace(0, 2, 80)
        down = np.linspace(97.0, 60.0, 60)
        eps = ep.failed_breakdown_episodes(
            _frame_from_close(np.concatenate([flat, down])),
            symbol="T", plane_id="stocks_tr_v1", const=EC,
        )
        # registration §7 defines this type BY its recovery; a non-recovering undercut is
        # decline-leg material, and only a truncated window may be emitted as censored.
        assert all(e.censored for e in eps)


class TestTiers:
    def test_tier_assignment_follows_depth_and_duration(self):
        assert ep._tier(0.40, 25, EC) == 1        # deep + long
        assert ep._tier(0.40, 5, EC) == 3         # deep but too short for D1 or D2
        assert ep._tier(0.25, 15, EC) == 2        # tier-2 depth + D2
        assert ep._tier(0.25, 5, EC) == 3
        assert ep._tier(0.05, 500, EC) == 3       # shallow is always the floor tier

    def test_tier1_requires_the_deeper_floor(self):
        assert ep.TIER1_DEPTH > ep.TIER2_DEPTH
        assert ep._tier(ep.TIER2_DEPTH, 999, EC) == 2
        assert ep._tier(ep.TIER1_DEPTH, 999, EC) == 1


class TestA0Basis:
    def test_a0_is_the_prior_confirmed_close(self):
        df = _frame_from_close(100 + np.arange(60, dtype=float))
        a0 = ep.a0_series(df)
        from engine.stock_technicals import atr as _atr

        raw = _atr(df["high"], df["low"], df["close"], n=14)
        assert a0.iloc[20] == pytest.approx(raw.iloc[19])
        assert pd.isna(a0.iloc[0])

    def test_episodes_record_both_a0s_and_the_basis_string(self):
        close = np.concatenate([
            np.linspace(100.0, 120.0, 200), np.linspace(120.0, 84.0, 60),
            np.linspace(84.0, 108.0, 80),
        ])
        e = ep.reset_decline_episodes(
            _frame_from_close(close), symbol="T", plane_id="stocks_tr_v1", const=EC
        )[0]
        assert e.atr_basis == ep.ATR_BASIS
        assert np.isfinite(e.a0_leg) and e.a0_leg > 0
        assert e.a0_anchor is not None and e.a0_anchor > 0
