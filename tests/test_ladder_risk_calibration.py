"""tests/test_ladder_risk_calibration.py — W4.6 risk-channel binding calibration.

Covers (masterplan W4.6 SHIP list, item 7):
  1. vol-residualization math: rdd = fwd_maxdd / trailing_vol, PIT (leak-free), sign & scale.
  2. embargo IMMUTABILITY: refitting with MORE data never moves the embargo split (a fixed
     calendar date, not a data-dependent quantile) — the R1 containment.
  3. binding fallback: no artifact ⇒ risk_size_mult == 1.0 for every state (byte-identical);
     artifact present-but-all-1.0 ⇒ still 1.0.
  4. grep gate: catches a synthetic unearned 'validated' in EN and in zh; ignores negation.
  5. null-cell discipline: a cell whose DD-gap CI INCLUDES the null gets weight 1.0; a
     non-1.0 weight requires an FDR-surviving CI that excludes the null.
  6. artifact shape: schema/channel/embargo/validated fields present and honest.
  7. additive binding: ladder_state emits risk_size_mult without altering the directional score.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import engine.cycles as C
from scripts import fit_ladder_risk_calibration as FIT
from scripts import check_validated_claims as GATE

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "data" / "regime" / "ladder_risk_calibration.json"


# ── 1. vol-residualization math ───────────────────────────────────────────────

def test_trailing_vol_pit_and_scale():
    """trailing_vol is annualized, positive, and uses ONLY tape <= stamp (leak-free)."""
    idx = pd.bdate_range("2020-01-01", periods=400)
    rng = np.random.default_rng(0)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
    closes = pd.DataFrame({"AAA": px})
    stamp = idx[300]
    v = FIT.trailing_vol(closes, "AAA", stamp)
    assert v > 0 and np.isfinite(v)
    # leak-free: adding a huge spike AFTER the stamp must not change the value
    closes2 = closes.copy()
    closes2.loc[idx[350], "AAA"] = px.iloc[350] * 5
    v2 = FIT.trailing_vol(closes2, "AAA", stamp)
    assert v == pytest.approx(v2), "trailing vol must ignore tape after the stamp (PIT leak)"


def test_trailing_vol_insufficient_history_nan():
    idx = pd.bdate_range("2020-01-01", periods=10)
    closes = pd.DataFrame({"AAA": pd.Series(range(1, 11), index=idx, dtype=float)})
    assert np.isnan(FIT.trailing_vol(closes, "AAA", idx[-1]))
    assert np.isnan(FIT.trailing_vol(closes, "MISSING", idx[-1]))


def test_residualize_divides_dd_by_vol_and_keeps_sign():
    """rdd = fwd_maxdd / trailing_vol: non-positive (drawdowns), and the 'deep drawdown =
    volatile instrument' confound is removed (higher vol ⇒ smaller |rdd| for the same dd)."""
    df = pd.DataFrame({
        "ticker": ["AAA", "BBB"], "date": [pd.Timestamp("2020-06-01")] * 2,
        "family": ["us_sector", "us_sector"], "timing_state": ["DECLINE", "DECLINE"],
        "phase": ["Downturn", "Downturn"],
        "fwd_maxdd_21": [-0.10, -0.10], "fwd_maxdd_63": [-0.10, -0.10],
        "fwd_maxdd_126": [-0.10, -0.10],
        "fwd_ret_21": [0.0, 0.0], "fwd_ret_63": [0.0, 0.0], "fwd_ret_126": [0.0, 0.0],
    })
    idx = pd.bdate_range("2018-01-01", periods=400)
    rng = np.random.default_rng(1)
    lo = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.005, len(idx)))), index=idx)   # low vol
    hi = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx)))), index=idx)    # high vol
    closes = pd.DataFrame({"AAA": lo, "BBB": hi})
    out = FIT.residualize(df, closes)
    a = out[out.ticker == "AAA"].iloc[0]
    b = out[out.ticker == "BBB"].iloc[0]
    assert a["rdd_63"] <= 0 and b["rdd_63"] <= 0
    # same raw dd, but the HIGHER-vol instrument gets a SMALLER-magnitude residualized dd
    assert abs(b["rdd_63"]) < abs(a["rdd_63"]), "vol-residualization must shrink the high-vol dd"


# ── 2. embargo immutability (R1 containment) ─────────────────────────────────

def _synthetic_cohort(end="2025-12-31"):
    """A small leak-free-ish cohort spanning START..end, both families, all states."""
    months = pd.date_range("2010-01-31", end, freq="ME")
    rng = np.random.default_rng(7)
    rows = []
    for d in months:
        for fam, tks in (("us_sector", ["XLK", "XLF"]), ("country", ["EWG", "EWJ"])):
            for tk in tks:
                st = FIT.LADDER[rng.integers(0, len(FIT.LADDER))]
                ph = FIT.PHASE_ORDER[rng.integers(0, len(FIT.PHASE_ORDER))]
                dd = float(-abs(rng.normal(0.06, 0.03)))
                rows.append({"date": d, "ticker": tk, "id": tk.lower(), "family": fam,
                             "timing_state": st, "phase": ph,
                             "fwd_ret_21": rng.normal(0, 0.03), "fwd_maxdd_21": dd,
                             "fwd_ret_63": rng.normal(0, 0.05), "fwd_maxdd_63": dd,
                             "fwd_ret_126": rng.normal(0, 0.07), "fwd_maxdd_126": dd,
                             "trailing_vol": abs(rng.normal(0.2, 0.05)) + 0.05})
    df = pd.DataFrame(rows)
    df["month"] = df["date"].values.astype("datetime64[M]")
    for h in FIT.HORIZONS:
        df[f"rdd_{h}"] = df[f"fwd_maxdd_{h}"] / df["trailing_vol"]
    return df


def test_embargo_split_is_immutable_under_more_data():
    """The embargo split is a FIXED calendar date; refitting with 2 extra years of data
    must leave the artifact's declared holdout START unchanged (R1)."""
    short = FIT.build_artifact(_synthetic_cohort("2024-12-31"))
    longer = FIT.build_artifact(_synthetic_cohort("2026-06-30"))
    assert short["embargo"]["holdout"][0] == str(FIT.EMBARGO_START.date())
    assert longer["embargo"]["holdout"][0] == str(FIT.EMBARGO_START.date())
    assert short["embargo"]["holdout"][0] == longer["embargo"]["holdout"][0], \
        "adding data must NEVER move the embargo split"
    assert short["embargo"]["immutable"] is True


def test_fit_window_grows_but_embargo_stays():
    """More data extends the fit window's right edge, but the embargo start is fixed."""
    short = FIT.build_artifact(_synthetic_cohort("2022-12-31"))
    longer = FIT.build_artifact(_synthetic_cohort("2023-11-30"))
    assert pd.Timestamp(longer["fit_window"][1]) >= pd.Timestamp(short["fit_window"][1])
    assert short["embargo"]["holdout"][0] == longer["embargo"]["holdout"][0]


# ── 3. binding fallback (byte-identical when absent / all-1.0) ────────────────

def _reset_cache():
    C._RISK_CALIB = {}
    C._RISK_CALIB_LOADED = False
    C._RISK_CALIB_LOGGED = set()


def test_binding_absent_artifact_all_ones(monkeypatch, tmp_path):
    """No artifact on disk ⇒ risk_size_mult == 1.0 for every (state, family)."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)  # empty dir, no artifact
    _reset_cache()
    for st in C.LADDER:
        for fam in ("us_sector", "country", "sector", None, "basket"):
            assert C.risk_size_mult(st, fam) == 1.0
    _reset_cache()


def test_binding_present_all_ones_is_noop():
    """The committed artifact currently ships all 1.0 ⇒ every lookup is 1.0 (no-op)."""
    _reset_cache()
    art = json.loads(ARTIFACT.read_text())
    assert art["any_cell_bound"] is False, "committed artifact must be all-1.0 (null verdict)"
    for st in C.LADDER:
        assert C.risk_size_mult(st, "us_sector") == 1.0
        assert C.risk_size_mult(st, "country") == 1.0
    _reset_cache()


def test_binding_clamped_and_family_aliased(monkeypatch, tmp_path):
    """A crafted artifact with an out-of-range weight is clamped; family aliasing works."""
    (tmp_path / "regime").mkdir()
    art = {"risk_size_mult": {"us_sector": {"DECLINE": {"risk_size_mult": 9.0},
                                            "FRESH BUY": {"risk_size_mult": 0.01}}},
           "mult_clamp": [0.5, 1.5]}
    (tmp_path / "regime" / "ladder_risk_calibration.json").write_text(json.dumps(art))
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    _reset_cache()
    assert C.risk_size_mult("DECLINE", "us_sector") == 1.5          # clamped from 9.0
    assert C.risk_size_mult("FRESH BUY", "us_sector") == 0.5        # clamped from 0.01
    assert C.risk_size_mult("DECLINE", "sector") == 1.5             # 'sector' -> 'us_sector'
    assert C.risk_size_mult("DECLINE", "country") == 1.0            # no country cells -> 1.0
    _reset_cache()


def test_ladder_state_emits_additive_field_without_changing_score():
    """ladder_state gains risk_size_mult additively; the directional score is unchanged and
    family-independent (the mult is a separate field, never folded into the score)."""
    _reset_cache()
    from engine.inputs import yahoo_closes
    c = yahoo_closes(basis="tr")["XLK"].dropna()
    r_fam = C.analyze(c, kind="equity", family="sector")["ladder"]
    r_none = C.analyze(c, kind="equity")["ladder"]
    assert "risk_size_mult" in r_fam
    assert r_fam["risk_size_mult"] == 1.0
    assert r_fam["score"] == r_none["score"], "directional score must not depend on family"
    _reset_cache()


# ── 4. the grep gate (EN + zh; negation ignored) ─────────────────────────────

def test_grep_gate_fires_on_synthetic_en_and_zh():
    allow = GATE._load_allowlist()

    def _fires(line):
        for m in GATE.TOKEN.finditer(line):
            if GATE._is_negated(line, m.start()):
                continue
            if GATE._allow_match(line, allow) is None and not GATE._artifact_backed(line):
                return True
        return False

    assert _fires("This new signal is validated as a cross-sectional alpha.")   # EN unearned
    assert _fires("这个全新信号是已验证的横截面阿尔法。")                              # zh unearned
    assert not _fires("The rank has no validated forward edge here.")           # EN negation
    assert not _fires("此处无已验证方向信号。")                                     # zh negation
    assert not _fires("Descriptive — this factor is unvalidated until W6.")     # 'unvalidated'
    assert not _fires("The CIT invalidated it on May 7.")                       # 'invalidated'


def test_grep_gate_selftest_passes():
    assert GATE.selftest() == 0


def test_grep_gate_whole_tree_clean():
    """The whole committed tree passes BC-2 (no unearned 'validated')."""
    assert GATE.scan(list_all=False) == [], "committed tree has an unearned 'validated' claim"


# ── 5. null-cell discipline ──────────────────────────────────────────────────

def test_null_cell_ci_includes_null_gives_weight_one():
    """A cell that is NOT an FDR survivor keeps weight 1.0 regardless of point-estimate gap."""
    mult, why = FIT._mult_from_gap([-0.4, 0.2], survived=False)   # CI straddles 0
    assert mult == 1.0 and "null" in why.lower()


def test_survivor_ci_excludes_null_gets_nonunit_weight_in_range():
    """A survivor whose CI is entirely negative (deeper tail) → shrink (<1.0), clamped [0.5,1.5]."""
    mult, why = FIT._mult_from_gap([-0.6, -0.2], survived=True)
    assert 0.5 <= mult < 1.0 and "shrink" in why
    mult2, _ = FIT._mult_from_gap([0.2, 0.6], survived=True)      # shallower tail → grow
    assert 1.0 < mult2 <= 1.5


def test_committed_artifact_null_verdict_all_weights_one():
    """The committed artifact records the honest null verdict: 0 FDR survivors, all 1.0."""
    art = json.loads(ARTIFACT.read_text())
    assert art["fdr"]["survivors"] == [], "no cell should survive FDR (the W4.6 verdict)"
    for fam in art["risk_size_mult"].values():
        for cell in fam.values():
            assert cell["risk_size_mult"] == 1.0


# ── 6. artifact shape + honesty ──────────────────────────────────────────────

def test_artifact_schema_and_honesty():
    art = json.loads(ARTIFACT.read_text())
    assert art["schema"] == "calibration.v1"
    assert art["channel"] == "risk"                       # SIZE only, never directional
    assert art["validated"] is False                      # BC-1 failed → not validated
    assert art["bc1"]["verdict"] == "FAIL"                # §6.5 pre-registered expectation
    assert art["bc1"]["rank_corr_train_vs_holdout"] is not None
    assert art["embargo"]["immutable"] is True
    assert art["mult_clamp"] == [0.5, 1.5]
    # stance evidence attached for the ontology
    assert art["stance_evidence"]["cells"], "stance evidence table must be populated"


def test_stance_matrix_carries_evidence():
    sm = json.loads((ROOT / "data" / "cycle_ontology" / "stance_matrix.json").read_text())
    with_ev = [c for c in sm["matrix"] if isinstance(c.get("evidence"), dict)
               and c["evidence"].get("n_rows", 0) > 0]
    assert with_ev, "stance matrix cells must carry backfilled vol-residualized evidence"
