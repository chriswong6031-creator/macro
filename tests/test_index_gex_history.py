"""Index dealer-gamma HISTORY reconstruction (roadmap P1.1b / scripts.build_index_gex_history)
+ the engine.market_gamma context upgrade.

Pins the four things the roadmap requires:
  1. greeks ⋈ oi join correctness on a synthetic fixture (keys, oi>0, T formula, iv units);
  2. the dealer-sign / net-GEX / regime convention is IDENTICAL to engine.gex_engine on a
     synthetic chain — a call-heavy chain is +GEX/long, a put-heavy one is -GEX, and the
     reconstruction summary equals compute_gex fed the same chain (no divergent basis);
  3. the overlap-audit helper runs and returns correlation + regime sign-agreement;
  4. engine.market_gamma.snapshot() falls back to the pre-upgrade current-day-only verdict
     when the reconstructed history store is absent, and attaches a context block when present.
"""
import numpy as np
import pandas as pd
import pytest

from engine.gex_engine import compute_gex
import scripts.build_index_gex_history as B
from scripts.build_index_gex_history import audit_overlap


# ---------------------------------------------------------------- fixtures --

def _greeks_oi_fixture(tmp_path, root="TST", year=2020):
    """Write a minimal greeks + oi parquet pair mirroring the ThetaData store schema,
    then point the builder at tmp_path. One trading date, a small call/put chain."""
    date = pd.Timestamp(f"{year}-03-16")
    exp = pd.Timestamp(f"{year}-04-17")
    spot = 100.0
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            rows.append(dict(root=root, expiration=exp, strike=k, right=right,
                             date=date, underlying_price=spot, implied_vol=0.20))
    greeks = pd.DataFrame(rows)
    # oi: call-heavy (calls carry more OI than puts) + one zero-OI row that must drop.
    oi_rows = []
    for k in strikes:
        oi_rows.append(dict(root=root, expiration=exp, strike=k, right="C",
                            date=date, open_interest=1000))
        oi_rows.append(dict(root=root, expiration=exp, strike=k, right="P",
                            date=date, open_interest=200))
    oi_rows.append(dict(root=root, expiration=exp, strike=999.0, right="C",
                        date=date, open_interest=0))  # zero-OI -> dropped
    oi = pd.DataFrame(oi_rows)

    (tmp_path / "greeks" / root).mkdir(parents=True)
    (tmp_path / "oi" / root).mkdir(parents=True)
    greeks.to_parquet(tmp_path / "greeks" / root / f"{year}.parquet")
    oi.to_parquet(tmp_path / "oi" / root / f"{year}.parquet")
    return date, exp, spot, strikes


# ------------------------------------------------------------ join + parse --

def test_read_year_chain_join_correctness(tmp_path, monkeypatch):
    date, exp, spot, strikes = _greeks_oi_fixture(tmp_path)
    monkeypatch.setattr(B, "THETA_ROOT", tmp_path)
    ch = B._read_year_chain("TST", 2020)
    assert ch is not None
    # 5 strikes x 2 rights = 10 joined rows; the zero-OI row is dropped.
    assert len(ch) == 10
    assert set(ch.columns) >= {"date", "expiry", "K", "T", "iv", "oi", "is_call", "underlying_price"}
    # T = calendar days / 365 (matches collectors/polygon_options.parse_chain exactly).
    assert ch["T"].round(6).eq(round((exp - date).days / 365.0, 6)).all()
    assert ch["iv"].eq(0.20).all()                       # decimal iv preserved
    assert ch["is_call"].sum() == 5 and (~ch["is_call"]).sum() == 5
    assert ch["oi"].min() > 0                            # zero-OI purged


# --------------------------------------------- dealer-sign / regime parity --

def _synth_chain(call_oi, put_oi, spot=100.0):
    exp = pd.Timestamp("2020-04-17")
    rows = []
    for k in [90.0, 95.0, 100.0, 105.0, 110.0]:
        rows.append(dict(K=k, T=32 / 365.0, iv=0.20, oi=float(call_oi), is_call=True, expiry=exp))
        rows.append(dict(K=k, T=32 / 365.0, iv=0.20, oi=float(put_oi), is_call=False, expiry=exp))
    return pd.DataFrame(rows)


def test_summary_equals_compute_gex_exactly(tmp_path, monkeypatch):
    """The reconstruction summary for a day MUST equal engine.gex_engine.compute_gex fed
    the same chain — same dealer sign (call +1 / put -1), same net-GEX $, same flip/regime.
    This is the anti-divergence guarantee: no independent GEX math in the reconstructor."""
    _greeks_oi_fixture(tmp_path)
    monkeypatch.setattr(B, "THETA_ROOT", tmp_path)
    ch = B._read_year_chain("TST", 2020)
    day = ch[ch["date"] == ch["date"].max()]
    got = B._summarise_day(day, "TST")

    spot = float(day["underlying_price"].iloc[0])
    ref = compute_gex(day[["K", "T", "iv", "oi", "is_call", "expiry"]].copy(), spot, symbol="TST")
    for key in ("net_gex_bn", "gamma_flip", "gamma_regime", "n_strikes", "spot", "max_pain"):
        assert got[key] == ref[key] or (
            isinstance(got[key], float) and np.isclose(got[key], ref[key])), key
    assert got["reconstructed"] is True


def test_dealer_sign_call_heavy_positive_put_heavy_negative():
    """Pin the dealer long-call/short-put convention: call-dominated OI -> net GEX > 0
    (dealers net long gamma); put-dominated OI -> net GEX < 0 — same as gex_engine."""
    call_heavy = compute_gex(_synth_chain(call_oi=5000, put_oi=100), 100.0, symbol="TST")
    put_heavy = compute_gex(_synth_chain(call_oi=100, put_oi=5000), 100.0, symbol="TST")
    assert call_heavy["net_gex_bn"] > 0
    assert put_heavy["net_gex_bn"] < 0


# ------------------------------------------------------------ overlap audit --

def test_overlap_audit_runs_and_reports_agreement():
    """The blocking overlap audit (reconstructed vs live polygon summary) computes a
    net-GEX correlation and a regime sign-agreement rate. Feed two aligned frames."""
    idx = pd.to_datetime(["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"])
    recon = pd.DataFrame({"net_gex_bn": [1.0, -0.5, -0.2, 0.8],
                          "gamma_regime": ["long", "short", "short", "long"]}, index=idx)
    live = pd.DataFrame({"net_gex_bn": [0.9, -0.6, -0.1, 0.7],
                         "gamma_regime": ["long", "short", "long", "long"]}, index=idx)
    rep = audit_overlap(recon, live)
    assert rep["n_overlap"] == 4
    assert -1.0 <= rep["net_gex_corr_raw"] <= 1.0
    assert rep["regime_agreement_raw"] == pytest.approx(0.75)  # 3/4 regimes agree


def test_same_spot_filter_isolates_timing_matched_rows():
    """Same-spot filter: rows where reconstructed and live spot differ >= 0.5% are
    excluded from net_gex_corr_same_spot.  This separates T-1-lag mismatch from
    model mismatch.  Synthetic: two timing-matched rows (high corr) + one mismatched
    row (spot shifts by >0.5%) that would drag the raw corr down."""
    idx = pd.to_datetime(["2026-06-15", "2026-06-16", "2026-06-17"])
    # Reconstructed (T+0 same-session spot)
    recon = pd.DataFrame({
        "net_gex_bn": [5.0, -3.0, 8.0],
        "spot":        [100.0, 101.0, 102.0],  # spot_r
        "gamma_regime": ["long", "short", "long"],
    }, index=idx)
    # Live (T-1 settlement): first two rows match spot; third shifts by >1% (timing lag)
    live = pd.DataFrame({
        "net_gex_bn": [4.8, -2.9, 2.0],   # last row is divergent (timing lag)
        "spot":        [100.05, 101.02, 99.5],  # third spot differs >0.5% from 102.0
        "gamma_regime": ["long", "short", "short"],
    }, index=idx)
    rep = audit_overlap(recon, live)
    assert rep["n_overlap"] == 3
    # Same-spot filter: only first two rows pass (|102-99.5|/102 ~2.45% > 0.5%)
    assert rep["n_same_spot"] == 2
    # Same-spot corr should be near-perfect on the two matched rows
    assert rep["net_gex_corr_same_spot"] is not None
    assert rep["net_gex_corr_same_spot"] > 0.99
    # Regime agreement on same-spot rows: both are "long"/"short" matching -> 1.0
    assert rep["regime_agreement_same_spot"] == pytest.approx(1.0)
    # Raw corr includes the bad row and is lower
    assert rep["net_gex_corr_raw"] < rep["net_gex_corr_same_spot"]


# ---------------------------------------------- market_gamma context upgrade --

def _cboe_gex(net_gex_bn=17.7, flip=8100, spot=7394.3, svf=-8.71):
    return pd.DataFrame({"net_gex_bn": [net_gex_bn], "flip_strike": [flip],
                         "spot": [spot], "spot_vs_flip_pct": [svf]},
                        index=pd.to_datetime(["2026-06-13"]))


def test_snapshot_falls_back_when_history_absent(monkeypatch):
    """No reconstructed store -> context is None and the verdict is otherwise the
    pre-upgrade current-day-only object (regime/flip/net_gex intact)."""
    from engine import market_gamma

    def fake_read(group, name):
        if group == "cboe":
            return _cboe_gex()
        return None  # index_gex_history absent

    monkeypatch.setattr(market_gamma.store, "read", fake_read)
    mg = market_gamma.snapshot()
    assert mg is not None
    assert mg["regime"] == "short" and mg["flip"] == 8100
    assert mg["context"] is None


def test_snapshot_attaches_context_when_history_present(monkeypatch):
    """With a reconstructed SPY history, snapshot() attaches net-GEX percentile +
    standing-regime persistence WITHOUT changing the current-day regime source."""
    from engine import market_gamma

    # SIX SESSIONS. This fixture used to end on 2026-06-13, a SATURDAY, so
    # _history_context saw 6 rows where the exchange calendar has 5 — and market_gamma
    # now session-filters the history (the #3721 weekend-row class: `.iloc[-1]` is the
    # standing reading and the percentile below is an own-history distribution, so both
    # must be session-true). Mon 06-08 → Mon 06-15 gives six real sessions and keeps the
    # last three 'short' (persistence 3) the assertions below depend on.
    hist = pd.DataFrame(
        {"net_gex_bn": [50.0, 40.0, 30.0, -5.0, -8.0, -8.5],
         "gamma_regime": ["long", "long", "long", "short", "short", "short"]},
        index=pd.to_datetime(["2026-06-08", "2026-06-09", "2026-06-10",
                              "2026-06-11", "2026-06-12", "2026-06-15"]))

    def fake_read(group, name):
        if group == "cboe":
            return _cboe_gex(net_gex_bn=17.7, svf=-8.71)  # current: short
        if group == "index_gex_history":
            return hist
        return None

    monkeypatch.setattr(market_gamma.store, "read", fake_read)
    mg = market_gamma.snapshot()
    ctx = mg["context"]
    assert ctx is not None and ctx["reconstructed"] is True
    assert ctx["n_days"] == 6
    # own-history percentile of the reconstructed latest (-8.5, the minimum) -> ~16.7 pct
    assert ctx["net_gex_latest_bn"] == -8.5
    assert 0.0 <= ctx["net_gex_pctile"] <= 100.0
    # reconstructed last 3 days are 'short' -> persistence 3; current-day (SPX) is 'short' too
    assert ctx["recon_regime_last"] == "short"
    assert ctx["regime_persistence_days"] == 3
    assert ctx["regime_agrees_current"] is True


# ============================================================================
# OIP E3c — store-path resolution + market_gamma window/staleness disclosure.
#
# The defect: THETA_ROOT was a module-level constant pinned to
# /Users/chriswong/theta-ops-wt/data/thetadata_eod. That is the fragmented
# per-module resolution the options_witness empty-store incident came from — on
# any other host the builder exits and the committed artifact silently freezes,
# which is exactly what happened (the store sat at 2026-07-02 for 18 sessions
# while engine.market_gamma kept serving percentiles off it as if current).
# ============================================================================

import datetime as _dt   # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

import lib.config as _libconfig  # noqa: E402
from engine import thetadata_store as _tds  # noqa: E402


def _mk_store(p, tiers=("greeks", "oi")):
    for t in tiers:
        (p / t).mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture()
def _isolated_theta(tmp_path, monkeypatch):
    """Point every resolver tier at tmp_path and clear the builder's caches, so
    these tests never depend on whether THIS host happens to hold the store
    (the self-hosted macstudio runners DO hold it — a host-sensitive assertion
    here would be green locally and red in CI, or the reverse)."""
    repo_data = tmp_path / "repo_data"
    repo_data.mkdir()
    monkeypatch.setattr(_libconfig, "data_dir", lambda: repo_data)
    monkeypatch.setattr(_tds, "_OPS_WT_STORE", tmp_path / "no_ops_wt")
    monkeypatch.delenv("THETADATA_STORE", raising=False)
    monkeypatch.setattr(B, "THETA_ROOT", None)
    monkeypatch.setattr(B, "_RESOLVED", None)
    return tmp_path


class TestStorePathRoutesThroughTheResolver:
    def test_no_hardcoded_ops_wt_path_remains(self):
        """Regression shape: the ops-host store path may live in exactly ONE place
        (engine/thetadata_store._OPS_WT_STORE), never in this builder."""
        src = _Path(B.__file__).read_text()
        assert "theta-ops-wt" not in src, (
            "build_index_gex_history re-hardcodes the ops-host store path — route it "
            "through engine.thetadata_store.resolve_thetadata_store() instead")

    def test_env_store_is_used_when_it_has_content(self, _isolated_theta, monkeypatch):
        env_store = _mk_store(_isolated_theta / "env_store")
        monkeypatch.setenv("THETADATA_STORE", str(env_store))
        assert B._theta_root() == env_store
        assert B._state_path() == env_store / "_backfill_state.json"

    def test_env_stub_falls_through_to_the_data_dir_store(self, _isolated_theta,
                                                          monkeypatch):
        """A directory that EXISTS but holds no eod/ oi/ greeks/ is a stub, not a
        store — resolving it would produce empty frames everywhere downstream."""
        stub = _isolated_theta / "stub"
        stub.mkdir()
        monkeypatch.setenv("THETADATA_STORE", str(stub))
        repo_store = _mk_store(_libconfig.data_dir() / "thetadata_eod")
        assert B._theta_root() == repo_store

    def test_ops_wt_tier_resolves_last(self, _isolated_theta, monkeypatch):
        ops = _mk_store(_isolated_theta / "ops_store")
        monkeypatch.setattr(_tds, "_OPS_WT_STORE", ops)
        assert B._theta_root() == ops

    def test_nothing_resolves_exits_naming_the_situation(self, _isolated_theta):
        with pytest.raises(SystemExit) as e:
            B._theta_root()
        msg = str(e.value)
        assert "did not resolve" in msg
        assert "THETADATA_STORE" in msg
        # names the coexistence law so the operator is not left guessing
        assert "committed" in msg

    def test_test_override_still_wins(self, _isolated_theta, monkeypatch):
        """The existing fixture tests set B.THETA_ROOT directly; that hook must keep
        working so the join/parity tests above stay hermetic."""
        fixture = _isolated_theta / "fixture_store"
        fixture.mkdir()
        monkeypatch.setattr(B, "THETA_ROOT", fixture)
        assert B._theta_root() == fixture

    def test_read_year_chain_reads_from_the_resolved_store(self, _isolated_theta,
                                                           monkeypatch):
        """End-to-end: a store reached through the ENV tier (not the override hook)
        is the one _read_year_chain actually opens."""
        env_store = _isolated_theta / "env_store2"
        env_store.mkdir()
        _greeks_oi_fixture(env_store, root="TST", year=2020)
        monkeypatch.setenv("THETADATA_STORE", str(env_store))
        ch = B._read_year_chain("TST", 2020)
        assert ch is not None and len(ch) == 10


class TestMarketGammaWindowDisclosure:
    """§0.7: nulls, staleness and coverage printed in plain words, calmly."""

    def _hist(self, last):
        return pd.DataFrame(
            {"net_gex_bn": [50.0, 40.0, -8.5],
             "gamma_regime": ["long", "long", "short"]},
            index=pd.to_datetime(["2017-01-03", "2020-06-15", last]))

    def _snapshot(self, monkeypatch, last, now):
        from engine import market_gamma

        def fake_read(group, name):
            if group == "cboe":
                return _cboe_gex()
            if group == "index_gex_history":
                return self._hist(last)
            return None

        monkeypatch.setattr(market_gamma.store, "read", fake_read)
        return market_gamma.snapshot(now=now)

    def test_frozen_store_prints_the_lag_in_plain_words(self, monkeypatch):
        """The live condition this wave found: the store sat at 2026-07-02 while the
        context block read as current. It must now say how far behind it is."""
        now = _dt.datetime(2026, 7, 29, 23, 0, tzinfo=_dt.timezone.utc)
        ctx = self._snapshot(monkeypatch, "2026-07-02", now)["context"]
        assert ctx["hist_start"] == "2017-01-03"
        assert ctx["hist_end"] == "2026-07-02"
        assert ctx["sessions_behind"] == 18
        assert ctx["stale"] is True
        assert "18 trading sessions behind the latest close" in ctx["note_en"]
        assert "落后 18 个交易日" in ctx["note_zh"]

    def test_current_store_says_current(self, monkeypatch):
        now = _dt.datetime(2026, 7, 29, 23, 0, tzinfo=_dt.timezone.utc)
        ctx = self._snapshot(monkeypatch, "2026-07-28", now)["context"]
        assert ctx["stale"] is False
        assert "is current" in ctx["note_en"]
        assert "数据为最新" in ctx["note_zh"]

    def test_a_weeks_lag_is_normal_for_a_weekly_job(self, monkeypatch):
        """The rebuild runs WEEKLY, so ~5 sessions of lag is the steady state — the
        threshold must not flag it, or the disclosure becomes background noise."""
        now = _dt.datetime(2026, 7, 29, 23, 0, tzinfo=_dt.timezone.utc)
        ctx = self._snapshot(monkeypatch, "2026-07-23", now)["context"]
        assert 0 < ctx["sessions_behind"] <= 7
        assert ctx["stale"] is False

    def test_disclosure_is_calm_not_an_alarm(self, monkeypatch):
        now = _dt.datetime(2026, 7, 29, 23, 0, tzinfo=_dt.timezone.utc)
        ctx = self._snapshot(monkeypatch, "2026-07-02", now)["context"]
        low = ctx["note_en"].lower()
        for banned in ("error", "failed", "broken", "alert", "warning", "stale",
                       "falsifier", "refuted", "validated"):
            assert banned not in low, f"alarm/banned word {banned!r} in the disclosure"

    def test_absent_store_still_degrades_to_a_none_context(self, monkeypatch):
        """Unchanged pre-existing contract: no store -> context is None (NOT a note
        block), so the machine-readable field keeps its documented shape."""
        from engine import market_gamma

        monkeypatch.setattr(market_gamma.store, "read",
                            lambda g, n: _cboe_gex() if g == "cboe" else None)
        assert market_gamma.snapshot()["context"] is None

    def test_percentile_is_still_the_series_against_itself(self, monkeypatch):
        """The SCALE NOTE stands: the block percentiles the rebuilt series' own latest
        value, never today's Cboe reading against the rebuilt distribution."""
        now = _dt.datetime(2026, 7, 29, 23, 0, tzinfo=_dt.timezone.utc)
        ctx = self._snapshot(monkeypatch, "2026-07-02", now)["context"]
        assert ctx["net_gex_latest_bn"] == -8.5          # the rebuild's own latest
        assert 0.0 <= ctx["net_gex_pctile"] <= 100.0
        assert "against itself" in ctx["note_en"]


class TestShrinkGuard:
    """The years a run reads come from a LIVE-MUTATING _backfill_state.json and
    build_root skips an absent/unreadable year with only a log.warning — so a truncated
    rebuild is valid-but-short and used to overwrite ~10 years of committed history,
    which the weekly lane would then push and mirror to R2, destroying every copy."""

    def _existing(self, tmp_path, n=100, start="2020-01-01"):
        p = tmp_path / "SPY.parquet"
        df = pd.DataFrame({"net_gex_bn": [1.0] * n},
                          index=pd.date_range(start, periods=n, freq="D"))
        df.to_parquet(p)
        return p, df

    def test_fewer_rows_is_refused(self, tmp_path):
        p, df = self._existing(tmp_path)
        ok, why = B.shrink_verdict(df.iloc[:50], p)
        assert not ok and "would shrink 100 -> 50 rows" in why
        assert "--allow-shrink" in why

    def test_regressed_end_date_is_refused_even_with_more_rows(self, tmp_path):
        """The worse shape: a rebuild that grew at the old end but lost the recent one.
        The downstream staleness disclosure keys off exactly that endpoint."""
        p, _ = self._existing(tmp_path)
        longer_but_older = pd.DataFrame(
            {"net_gex_bn": [1.0] * 150},
            index=pd.date_range("2019-01-01", periods=150, freq="D"))
        ok, why = B.shrink_verdict(longer_but_older, p)
        assert not ok and "latest date regresses" in why

    def test_growth_is_allowed(self, tmp_path):
        p, _ = self._existing(tmp_path)
        grown = pd.DataFrame({"net_gex_bn": [1.0] * 110},
                             index=pd.date_range("2020-01-01", periods=110, freq="D"))
        ok, why = B.shrink_verdict(grown, p)
        assert ok and "100 -> 110 rows" in why

    def test_equal_size_same_end_is_allowed(self, tmp_path):
        p, df = self._existing(tmp_path)
        assert B.shrink_verdict(df, p)[0]

    def test_missing_or_unreadable_existing_file_is_writable(self, tmp_path):
        df = pd.DataFrame({"net_gex_bn": [1.0]}, index=pd.to_datetime(["2020-01-01"]))
        assert B.shrink_verdict(df, tmp_path / "nope.parquet")[0]
        junk = tmp_path / "junk.parquet"
        junk.write_bytes(b"not a parquet")
        assert B.shrink_verdict(df, junk)[0]

    def test_refused_root_is_kept_out_of_roots_read(self, tmp_path, monkeypatch, capsys):
        """The runner gates its git push on manifest roots_read, so a refused root must
        NOT appear there — otherwise the truncation reaches the commit anyway."""
        outdir = tmp_path / "out"
        outdir.mkdir()
        existing = pd.DataFrame({"net_gex_bn": [1.0] * 100},
                                index=pd.date_range("2020-01-01", periods=100, freq="D"))
        existing.to_parquet(outdir / "SPY.parquet")
        short = existing.iloc[:10]

        monkeypatch.setattr(B, "_completed_map", lambda: {"SPY": ["2020"]})
        monkeypatch.setattr(B, "build_root", lambda root, c, y: (short, [2020]))
        monkeypatch.setattr(B, "run_audit", lambda outdir, roots: {})
        monkeypatch.setattr(B, "_theta_root", lambda: tmp_path)
        monkeypatch.setattr(sys, "argv", ["x", "--out", str(outdir)])
        B.main()

        man = json.loads((outdir / "_manifest.json").read_text())
        assert "SPY" not in (man.get("roots_read") or {})
        assert "SPY" in (man.get("roots_refused_shrink") or {})
        # the committed parquet is untouched
        assert len(pd.read_parquet(outdir / "SPY.parquet")) == 100
        line = next((ln for ln in capsys.readouterr().out.splitlines()
                     if "index-gex-shrink-guard" in ln), "")
        assert line.startswith("::warning"), "annotation must start the line"

    def test_allow_shrink_overrides_it(self, tmp_path, monkeypatch):
        outdir = tmp_path / "out2"
        outdir.mkdir()
        existing = pd.DataFrame({"net_gex_bn": [1.0] * 100},
                                index=pd.date_range("2020-01-01", periods=100, freq="D"))
        existing.to_parquet(outdir / "SPY.parquet")
        short = existing.iloc[:10]
        monkeypatch.setattr(B, "_completed_map", lambda: {"SPY": ["2020"]})
        monkeypatch.setattr(B, "build_root", lambda root, c, y: (short, [2020]))
        monkeypatch.setattr(B, "run_audit", lambda outdir, roots: {})
        monkeypatch.setattr(B, "_theta_root", lambda: tmp_path)
        monkeypatch.setattr(sys, "argv", ["x", "--out", str(outdir), "--allow-shrink"])
        B.main()
        assert len(pd.read_parquet(outdir / "SPY.parquet")) == 10
        man = json.loads((outdir / "_manifest.json").read_text())
        assert man["roots_read"]["SPY"] == [2020]


class TestRunnerManifestGate:
    """The launchd runner must gate its push on the manifest's roots_read from THIS run.
    File existence cannot be the gate: the parquets are git-tracked, so all four are on
    disk from the checkout even when the run wrote none of them."""

    RUNNER = _Path(__file__).resolve().parent.parent / "ops/launchd/run_index_gex_history.sh"

    def test_runner_gates_on_roots_read_not_file_existence(self):
        src = self.RUNNER.read_text(encoding="utf-8")
        assert "roots_read" in src, "the completeness gate must read the manifest"
        assert "roots_refused_shrink" in src, "a shrink-refused run must not push"
        assert "File EXISTENCE is NOT the gate" in src

    def test_runner_publishes_and_pushes_the_whole_store(self):
        src = self.RUNNER.read_text(encoding="utf-8")
        assert "--dirs index_gex_history" in src
        assert "--no-manifest" in src, "a partial-tree publish must not clobber the list"
        assert "indexgex-push-repo" in src, "its own push repo (TCC law)"
