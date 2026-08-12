"""Guard suite for the stop-curvature study — the gates must be able to FAIL.

Why this file exists. Every load-bearing claim in ``stop_curvature_study.py`` is made by a
gate that reports on itself: the parity gate says the recomputed histogram matches the
replay's column, the PIT test says no feature input resolves past the confirm bar, and the
ordering proof says outcomes were unreadable until G5 concluded. A self-report is worth
nothing until it has been shown to go RED on a planted defect (house memory:
``receipt-written-from-the-same-variable-cannot-fail`` — a receipt derived from the thing it
checks cannot fail, and an empty run passes ``all()`` vacuously). So the tests below are
mostly MUTATIONS: plant the exact defect each gate claims to catch, and require the gate to
catch it.

The G5 gate gets the same treatment in the other direction. Its published verdict is that
all five chartered forms MISS the motivating exemplars — a result that would look identical
if the gate were simply hard-wired to fail. ``test_g5_passes_when_a_form_really_covers_the
_exemplars`` plants a name whose histogram genuinely arches on both exemplar dates and
requires G5 to PASS, so the null is a measurement and not a stuck switch.

Everything here is SYNTHETIC — hand-built frames, planted paths, no network and no ``data/``
(CI packs carry no data tree). The one real-store test skips with a reason and its shape is
pinned synthetically by a twin that never skips, per the house pattern in
``test_price_ladder.py`` (a gate hung on a skipping fixture is dark).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (str(REPO), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import stop_curvature_study as S  # noqa: E402

STORE = Path("/Users/chriswong/actions-runner-2/_work/macro/macro/data/baskets/ohlcv")


# ---------------------------------------------------------------- fixtures
def _frame(n: int = 420, seed: int = 7) -> pd.DataFrame:
    """A synthetic OHLCV frame on real business days, long enough for the 3D leg."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.012, n))), index=idx)
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    return pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]), "high": high,
                         "low": low, "close": close,
                         "volume": rng.integers(1e5, 1e6, n).astype(float)}, index=idx)


def _mk(ticker: str = "SYNTH", seed: int = 7) -> S.NameCurv:
    """A NameCurv whose derived arrays are WRITABLE so defects can be planted in them.

    The engine hands back read-only numpy views (pandas copy-on-write), which is the right
    default for production and useless for mutation testing — so the test, not the study,
    takes the copies.
    """
    n = S.NameCurv(ticker, _frame(seed=seed), "synthetic")
    n.hist = np.array(n.hist, dtype="float64")
    n.m3_sa = np.array(n.m3_sa, dtype=bool)
    n.m3_src = np.array(n.m3_src, dtype="datetime64[ns]")
    return n


@pytest.fixture()
def nd() -> S.NameCurv:
    return _mk()


def _plant(nd: S.NameCurv, T: int, path: list[float]) -> None:
    """Plant an exact histogram path ending AT bar T (``path[-1]`` is ``hist[T]``)."""
    nd.hist[T - len(path) + 1: T + 1] = np.array(path, dtype="float64")


def _stops_for(nd: S.NameCurv, positions: list[int]) -> pd.DataFrame:
    """A stops frame whose stored columns are the TRUTH the parity gate checks against."""
    rows = []
    for T in positions:
        h = nd.hist
        rows.append({
            "ticker": nd.ticker, "date": nd.idx[T], "close": float(nd.c[T]),
            "stop_level": float(nd.c[T]) * 1.01, "argmin_date": nd.idx[T], "gap": 0,
            "near_low_stop": True, "full_window": True,
            "hist_rising": bool(T >= 2 and np.isfinite(h[T]) and np.isfinite(h[T - 1])
                                and np.isfinite(h[T - 2]) and h[T] > h[T - 1] > h[T - 2]),
            "m3_bull": bool(nd.m3_sa[T]), "fwd10": 0.01, "fwd21": 0.02, "addon": False,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the outcome seal
def test_outcome_vault_raises_before_unseal_and_serves_after():
    """The ex-ante ordering is enforced, not merely documented (charter §1)."""
    f = pd.DataFrame({"ticker": ["A"], "near_low_stop": [True], "gap": [0],
                      "argmin_date": [pd.Timestamp("2024-01-02")], "fwd10": [0.1],
                      "fwd21": [0.2], "hist_rising": [False]})
    stripped, vault = S.OutcomeVault.seal(f)

    # structural: the columns are GONE from the working frame, so a stray read is a KeyError
    for col in S.OutcomeVault.OUTCOME_COLS:
        assert col not in stripped.columns
    assert "hist_rising" in stripped.columns          # feature columns are untouched

    with pytest.raises(S.OutcomeSealError):
        vault.get("near_low_stop")
    assert vault.reads == 0                            # a refused read is not a read

    vault.unseal()
    assert bool(vault.get("near_low_stop")[0]) is True
    assert vault.reads == 1


def test_vault_positional_slice_matches_the_working_frame():
    """The frame is sliced to R4b rows; the vault must serve the SAME rows, not the union."""
    f = pd.DataFrame({"ticker": list("ABCD"), "near_low_stop": [True, False, True, False],
                      "gap": [0, 1, 2, 3], "argmin_date": [pd.Timestamp("2024-01-02")] * 4,
                      "fwd10": [0.1, 0.2, 0.3, 0.4], "fwd21": [0.0] * 4,
                      "keep": [True, False, True, True]})
    stripped, vault = S.OutcomeVault.seal(f)
    vault.unseal()
    pos = np.flatnonzero(stripped["keep"].to_numpy())
    got = vault.get("fwd10", pos)
    assert got.tolist() == [0.1, 0.3, 0.4]
    assert len(got) == len(stripped[stripped["keep"]])


# ---------------------------------------------------------------- form arithmetic (charter §2)
def test_k1_fires_on_an_arch_and_not_on_a_fresh_low(nd):
    T = 300
    _plant(nd, T, [-2.0, -3.0, -2.5])          # bottomed at -3.0, now ABOVE it, still < 0
    assert nd.k1(T, 15) is True

    _plant(nd, T, [-2.0, -2.5, -3.0])          # still making new lows -> the charter's NO
    assert nd.k1(T, 15) is False


def test_k1_requires_both_the_low_and_the_bar_below_zero(nd):
    T = 300
    _plant(nd, T, [1.0, 0.5, 0.8])             # tmin_w > 0: not an off-a-washout-low arch
    assert nd.k1(T, 15) is False
    _plant(nd, T, [-2.0, -3.0, 0.5])           # recovered ABOVE zero: no longer the form
    assert nd.k1(T, 15) is False


def test_k1_excludes_the_confirm_bar_from_the_trailing_minimum(nd):
    """Charter §2's knowability clause. With T inside the window a fresh low would compare
    against ITSELF and read TRUE-ish; excluding it is what makes 'off the low' meaningful —
    and is exactly why the STLD exemplars read FALSE."""
    T = 300
    _plant(nd, T, [-1.0, -1.5, -2.0])          # hist[T] IS the minimum of the window
    tm = nd.tmin(T, 15)
    assert tm == pytest.approx(-1.5)           # the minimum EXCLUDING T
    assert nd.hist[T] < tm
    assert nd.k1(T, 15) is False


def test_k2_rejects_a_staircase_and_accepts_an_arch_under_both_readings(nd):
    T = 300
    # An ARCH is an ACCELERATING recovery: the first differences themselves grow, so the
    # mean second difference is >= 0. (A decelerating rise is concave and K2 rejects it —
    # the charter asks for the turn, not the tail of one.)
    _plant(nd, T, [-3.0, -2.6, -1.9, -1.0])
    assert nd.k2(T, 3) is True
    assert nd.k2(T, 3, tight=True) is True

    _plant(nd, T, [-1.0, -1.4, -1.9, -2.5])    # monotone DOWN: >1 negative first-difference
    assert nd.k2(T, 3) is False
    assert nd.k2(T, 3, tight=True) is False


def test_k2_tight_and_wide_readings_are_actually_different_lenses(nd):
    """The charter's 'over the last m bars' is ambiguous; the study prints both. If the two
    readings could never disagree, printing both would be theatre — this pins that they can."""
    T = 300
    _plant(nd, T, [-9.0, -1.0, -1.2, -1.1])    # the far bar only enters the WIDE window
    assert nd.k2(T, 3) != nd.k2(T, 3, tight=True)


def test_k3_threshold_is_a_fraction_of_the_trailing_low_depth(nd):
    T = 300
    _plant(nd, T, [-1.0, -2.0, -1.5])          # recovery = (-1.5 - -2.0)/2.0 = 0.25
    assert nd.k3(T, theta=0.15, w=15) is True
    assert nd.k3(T, theta=0.30, w=15) is False  # 0.25 < 0.30 -> the primary cell says no


def test_k5_is_exactly_k1_or_k4(nd):
    T = 300
    _plant(nd, T, [-2.0, -2.5, -3.0])          # K1 False
    nd.m3_sa[T] = False
    assert nd.k5(T) is False
    nd.m3_sa[T] = True                          # K4 alone carries the union
    assert nd.k5(T) is True
    nd.m3_sa[T] = False
    _plant(nd, T, [-2.0, -3.0, -2.5])          # K1 alone carries the union
    assert nd.k5(T) is True


def test_forms_return_none_rather_than_false_when_history_is_short(nd):
    """An unavailable window is UNAVAILABLE, not a silent False — the coverage table counts
    the two differently and a False would understate coverage while overstating the frame."""
    assert nd.k1(3, 15) is None
    assert nd.k3(3, w=15) is None
    assert nd.k2(1, 3) is None


# ---------------------------------------------------------------- MUTATION: the parity gate
def test_parity_gate_passes_on_an_honest_frame(nd):
    ok, res = S.parity_gate(_stops_for(nd, [280, 300, 320]), {"SYNTH": nd})
    assert ok is True
    assert res["hist_match"] == res["rows"] == 3


def test_parity_gate_fails_when_one_stored_flag_diverges(nd):
    """MUTATION. Flip a single stored ``hist_rising`` and the gate must go red — otherwise
    its 12,940/12,940 PASS is a tautology and the study rests on nothing."""
    stops = _stops_for(nd, [280, 300, 320])
    stops.loc[1, "hist_rising"] = not bool(stops.loc[1, "hist_rising"])
    ok, res = S.parity_gate(stops, {"SYNTH": nd})
    assert ok is False
    assert res["hist_match"] == 2 and res["rows"] == 3
    assert res["hist_mismatch_examples"], "a divergence must be REPORTED, not just counted"


def test_parity_gate_fails_when_a_row_cannot_be_resolved(nd):
    """A row whose name or date is absent is UNRESOLVED, never quietly dropped: dropping it
    would let a shrinking frame read as a rising match rate (memory: shrink-direction can
    mean the detector went blind)."""
    stops = _stops_for(nd, [280, 300])
    stops.loc[1, "ticker"] = "GHOST"
    ok, res = S.parity_gate(stops, {"SYNTH": nd})
    assert ok is False
    assert res["unresolved"] == 1


# ---------------------------------------------------------------- MUTATION: the PIT leak test
def test_pit_leak_test_passes_on_the_causal_series(nd):
    ok, res = S.pit_leak_test(_stops_for(nd, [280, 300, 320]), {"SYNTH": nd}, sample=0)
    assert ok is True
    assert res["truncation_violations"] == 0 and res["knowability_violations"] == 0
    assert res["truncation_checked"] == 3, "a vacuous zero-row pass is not a pass"


def test_pit_leak_test_fails_on_a_forward_looking_series(nd):
    """MUTATION. Plant the exact defect class the parent had to RETRACT — a feature whose
    value at T depends on bars after T (here a centred window). Truncating at T must change
    the value, and the gate must see it."""
    centred = pd.Series(nd.hist).rolling(9, center=True, min_periods=1).mean().to_numpy()
    nd.hist = centred
    ok, res = S.pit_leak_test(_stops_for(nd, [280, 300, 320]), {"SYNTH": nd}, sample=0)
    assert ok is False
    assert res["truncation_violations"] > 0
    assert res["worst_abs_dev"] > S.PIT_TOL


def test_pit_knowability_leg_fails_when_3d_state_is_stamped_before_its_bucket_closes(nd):
    """MUTATION on leg (b). Stamp a 3D value as knowable on a session AFTER the confirm bar
    — the bucket-open-label defect — and the leg must red."""
    stops = _stops_for(nd, [280, 300, 320])
    T = nd.pos[pd.Timestamp(stops.loc[1, "date"])]
    nd.m3_src[T] = np.datetime64(pd.Timestamp(nd.idx[T + 2]), "ns")
    ok, res = S.pit_leak_test(stops, {"SYNTH": nd}, sample=0)
    assert ok is False
    assert res["knowability_violations"] == 1


def test_pit_truncation_leg_reports_its_true_scope(nd):
    """A sampled leg must SAY it sampled — an unlabelled sample reads as full coverage."""
    stops = _stops_for(nd, list(range(280, 330)))
    _, res = S.pit_leak_test(stops, {"SYNTH": nd}, sample=5)
    assert "sample" in res["truncation_scope"] and "5/" in res["truncation_scope"]
    _, res_all = S.pit_leak_test(stops, {"SYNTH": nd}, sample=0)
    assert res_all["truncation_scope"].startswith("ALL")


# ---------------------------------------------------------------- MUTATION: the G5 gate
def test_g5_passes_when_a_form_really_covers_the_exemplars(monkeypatch):
    """MUTATION in the PASS direction. The published verdict is that every chartered form
    misses both exemplars; a gate hard-wired to FAIL would print exactly that. Plant a name
    whose histogram genuinely arches off a below-zero low on both exemplar dates and require
    K1/K5 to clear G5 — so the real null is evidence, not a stuck switch."""
    name = _mk("EXEMPLAR")
    d1, d2 = name.idx[300], name.idx[340]
    for T in (300, 340):
        _plant(name, T, [-2.0, -3.0, -2.5])
        name.m3_sa[T] = True
    monkeypatch.setattr(S, "EXEMPLARS", (("EXEMPLAR", str(d1.date())),
                                         ("EXEMPLAR", str(d2.date()))))
    monkeypatch.setattr(S, "EXEMPLAR_NARRATIVE", ("EXEMPLAR", str(name.idx[360].date())))

    _, vault = S.OutcomeVault.seal(pd.DataFrame({"near_low_stop": [True], "fwd10": [0.0],
                                                 "fwd21": [0.0], "gap": [0],
                                                 "argmin_date": [d1]}))
    verdicts, ordering = S.g5_exemplar_gate({"EXEMPLAR": name}, vault)
    assert verdicts["K1"]["pass"] is True
    assert verdicts["K4"]["pass"] is True
    assert verdicts["K5"]["pass"] is True
    assert ordering["unsealed"] is not None


def test_g5_fails_when_the_exemplar_bar_is_a_fresh_low(monkeypatch):
    """The measured shape of the real STLD receipts, reproduced synthetically so the finding
    stays pinned on a runner with no store."""
    name = _mk("EXEMPLAR")
    d1, d2 = name.idx[300], name.idx[340]
    for T in (300, 340):
        _plant(name, T, [-1.97, -2.22, -2.65])   # the STLD May-19 shape: a NEW low at T
        name.m3_sa[T] = False
    monkeypatch.setattr(S, "EXEMPLARS", (("EXEMPLAR", str(d1.date())),
                                         ("EXEMPLAR", str(d2.date()))))
    monkeypatch.setattr(S, "EXEMPLAR_NARRATIVE", ("EXEMPLAR", str(name.idx[360].date())))

    _, vault = S.OutcomeVault.seal(pd.DataFrame({"near_low_stop": [True], "fwd10": [0.0],
                                                 "fwd21": [0.0], "gap": [0],
                                                 "argmin_date": [d1]}))
    verdicts, _ = S.g5_exemplar_gate({"EXEMPLAR": name}, vault)
    assert [verdicts[f]["pass"] for f in S.FORMS] == [False] * 5


# ---------------------------------------------------------------- 3D legs
def test_session_anchored_and_phased_3d_legs_are_different_computations(nd):
    """The charter's §4.6 reconciliation row only means something if the two grids CAN
    disagree. If they were identical by construction the 'phase divergence' would be a
    guaranteed zero and the reconciliation would be decorative."""
    assert nd.m3_sa.shape == nd.m3_ph.shape == (len(nd.idx),)
    assert int((nd.m3_sa != nd.m3_ph).sum()) > 0


def test_knowability_dates_never_lead_their_bar(nd):
    ok = ~pd.isna(pd.Series(nd.m3_src))
    src = pd.Series(nd.m3_src)[ok]
    bars = pd.Series(nd.idx)[ok]
    assert bool((src.to_numpy() <= bars.to_numpy()).all())


# ---------------------------------------------------------------- real-store receipt (skips)
@pytest.mark.skipif(not (STORE / "STLD.parquet").exists(),
                    reason="adjusted OHLCV store absent (CI packs carry no data/ tree)")
def test_stld_exemplars_reproduce_the_published_g5_receipt():
    """The measured finding, against the real store: at BOTH motivating confirms the 1D
    MACD-RSI histogram sits at or below its 15-session trailing minimum — the shape the
    synthetic twin above pins. Jan-07 additionally reads 3D-bull FALSE, which is what takes
    K4 (and therefore K5) down."""
    df, src = S.load_ohlc("STLD", STORE, STORE.parents[1] / "stocks")
    assert df is not None
    name = S.NameCurv("STLD", df, src)
    for d in ("2026-05-19", "2026-01-07"):
        T = name.pos[pd.Timestamp(d)]
        assert name.hist[T] <= name.tmin(T, S.K1_W_PRIMARY)
        assert name.k1(T, S.K1_W_PRIMARY) is False
        assert name.k2(T, S.K2_M_PRIMARY) is False
        assert name.k3(T, theta=S.K3_PRIMARY[0], w=S.K3_PRIMARY[1]) is False
    assert name.k4(name.pos[pd.Timestamp("2026-05-19")]) is True
    assert name.k4(name.pos[pd.Timestamp("2026-01-07")]) is False
