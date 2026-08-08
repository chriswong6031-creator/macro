"""Golden-vector + invariant tests for engine/canon.py (audit #7 #12 #28 #40 #45).

canon is the single source of truth for concepts computed divergently across engines.
These tests (a) pin every canon function to its committed golden vector so a silent math
change is caught, (b) assert the cross-engine invariants (net-liq 3-term + mixed-unit
guard, credit-impulse LEVEL≠ACCEL, one VIX basis, XLC impossible-prior retired), and
(c) prove canon byte-matches the consumers it is migrating (anticipation netliq loader,
china credit-impulse locals, vol_regime/conditions VIX ratio).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import canon

GOLDEN = json.loads((Path(__file__).parent / "golden" / "canon_vectors.json").read_text())


def _close(nan_ok=True):
    return  # placeholder for parametrization symmetry


def _eq(a, b, atol=1e-6):
    a = [np.nan if x is None else x for x in a]
    b = [np.nan if x is None else x for x in b]
    return np.allclose(np.asarray(a, float), np.asarray(b, float), atol=atol, equal_nan=True)


# ── 1 · NET LIQUIDITY ────────────────────────────────────────────────────────
def test_net_liquidity_golden():
    g = GOLDEN["net_liquidity_bn"]
    i = g["inputs"]
    out = canon.net_liquidity_bn(pd.Series(i["walcl_bn"]), pd.Series(i["rrp_bn"]),
                                 pd.Series(i["tga_bn"]))
    assert _eq(out.round(4).to_list(), g["expected"])


def test_net_liquidity_is_three_term():
    """WALCL − RRP − TGA, not the 2-term forex variant (which dropped TGA — a bug)."""
    idx = pd.date_range("2024-01-01", periods=5)
    walcl = pd.Series([7000.0] * 5, idx)
    rrp = pd.Series([50.0] * 5, idx)
    tga = pd.Series([500.0] * 5, idx)
    assert (canon.net_liquidity_bn(walcl, rrp, tga) == 6450.0).all()
    # dropping TGA (the forex bug) would give 6950 — canon must include it
    assert (canon.net_liquidity_bn(walcl, rrp, tga) != 6950.0).all()


def test_net_liquidity_mixed_unit_guard_fires():
    """The #28 mixed-unit subtraction (WALCL trillions − RRP billions) fails LOUDLY."""
    with pytest.raises(ValueError, match="audit #28"):
        canon.net_liquidity_bn(pd.Series([6.7, 6.75, 6.8, 6.85]),
                               pd.Series([26.9, 27.0, 28.0, 29.0]), None)


def test_net_liquidity_missing_drain_does_not_annihilate():
    """A missing RRP/TGA contributes 0 — the balance-sheet trend must survive."""
    walcl = pd.Series([7000.0, 7050.0, 7100.0])
    out = canon.net_liquidity_bn(walcl, None, None)
    assert out.equals(walcl)  # no drain → net == balance sheet, trend intact


def test_dollar_liquidity_roc_is_negated_change():
    """forex framing = −Δ net-liq: falling liquidity ⇒ positive (USD supportive)."""
    g = GOLDEN["dollar_liquidity_roc"]
    i = GOLDEN["net_liquidity_bn"]["inputs"]
    nl = canon.net_liquidity_bn(pd.Series(i["walcl_bn"]), pd.Series(i["rrp_bn"]),
                                pd.Series(i["tga_bn"]))
    out = canon.dollar_liquidity_roc(nl, g["window_d"])
    assert _eq(out.round(4).to_list(), g["expected"])
    # sign contract: it is exactly the negative of the raw change
    raw = canon.net_liquidity_bn_change(nl, g["window_d"])
    assert _eq((-raw).round(4).to_list(), out.round(4).to_list())


def test_net_liquidity_loader_matches_anticipation():
    """canon.load_net_liquidity_components byte-matches anticipation's migrated local."""
    fred = Path("data/fred")
    if not (fred / "WALCL.parquet").exists():
        pytest.skip("no local FRED store")
    from engine import anticipation
    idx = pd.bdate_range("2015-01-01", "2026-06-30")
    c = canon.load_net_liquidity_components(idx)
    a = anticipation._net_liquidity_bn(idx)
    for k in ("walcl_bn", "rrp_bn", "tga_bn", "netliq_bn"):
        assert np.allclose(c[k].fillna(-999.0), a[k].fillna(-999.0)), k


# ── 2 · CREDIT IMPULSE (label collision) ─────────────────────────────────────
def test_credit_impulse_golden():
    g = GOLDEN["credit_impulse"]
    tsf = pd.Series(g["inputs"]["tsf_total"],
                    index=pd.date_range("2020-01-31", periods=len(g["inputs"]["tsf_total"]),
                                        freq="ME"))
    assert _eq(canon.credit_impulse_level(tsf).to_list(), g["level_expected"])
    assert _eq(canon.credit_impulse_accel(tsf).to_list(), g["accel_expected"])


def test_credit_impulse_level_and_accel_differ():
    """The whole point of the fix: they are mathematically DIFFERENT series."""
    tsf = pd.Series(GOLDEN["credit_impulse"]["inputs"]["tsf_total"],
                    index=pd.date_range("2020-01-31",
                                        periods=len(GOLDEN["credit_impulse"]["inputs"]["tsf_total"]),
                                        freq="ME"))
    lvl = canon.credit_impulse_level(tsf).dropna()
    acc = canon.credit_impulse_accel(tsf).dropna()
    common = lvl.index.intersection(acc.index)
    assert not np.allclose(lvl.loc[common], acc.loc[common])


def test_credit_impulse_matches_radar_and_strategies_locals():
    """LEVEL == china_radar local; ACCEL == china_strategies local (pre-migration math)."""
    tsf = pd.Series(np.linspace(100, 400, 60),
                    index=pd.date_range("2019-01-31", periods=60, freq="ME"))
    radar_local = tsf.rolling(12).sum().pct_change(6)
    strat_local = (tsf.rolling(12).sum().pct_change(12) * 100.0).diff(6)
    assert _eq(canon.credit_impulse_level(tsf).to_list(), radar_local.to_list())
    assert _eq(canon.credit_impulse_accel(tsf).to_list(), strat_local.to_list())


# ── 3 · VIX TERM ─────────────────────────────────────────────────────────────
def test_vix_term_golden():
    g = GOLDEN["vix_term"]
    out = canon.vix_term(pd.Series(g["inputs"]["vix"]), pd.Series(g["inputs"]["vix3m"]))
    assert _eq(out.to_list(), g["expected"])
    assert abs(canon.vix_term_scalar(20, 19) - g["scalar_20_19"]) < 1e-6


def test_vix_term_backwardation_semantics():
    """≥ 1 = backwardation (stress); < 1 = contango (calm) — the one basis."""
    assert canon.vix_term_scalar(30, 24) > 1.0   # spike front-month → backwardation
    assert canon.vix_term_scalar(14, 18) < 1.0   # calm → contango
    assert canon.vix_term_scalar(20, 0) is None  # degenerate → None, never a div-by-zero


# ── 4 · SECTOR MACRO BETA (shadow) ───────────────────────────────────────────
def test_sector_macro_beta_blend_golden():
    g = GOLDEN["sector_macro_beta_blend"]
    i = g["inputs"]
    out = canon.sector_macro_beta_blend(i["prior"], i["measured"],
                                        shrink_k=i["shrink_k"], measured_n=i["measured_n"])
    assert out == g["expected"]


def test_sector_macro_beta_retires_impossible_xlc():
    """XLC=1.0 predates XLC's 2018 launch → retired to 0.0, flagged."""
    out = canon.sector_macro_beta_blend({"XLC": 1.0}, {}, measured_n={})
    assert out["XLC"]["blended"] == 0.0
    assert out["XLC"]["retired_impossible_prior"] is True


def test_sector_macro_beta_shrinks_toward_prior_when_unmeasured():
    out = canon.sector_macro_beta_blend({"XLE": 0.16}, {}, measured_n={})
    assert out["XLE"]["w"] == 0.0 and out["XLE"]["blended"] == 0.16


def test_sector_macro_beta_blend_is_convex():
    """blended is a convex combination of measured and prior (never extrapolates)."""
    out = canon.sector_macro_beta_blend({"XLF": 1.0}, {"XLF": 0.5},
                                        shrink_k=8.0, measured_n={"XLF": 100})
    r = out["XLF"]
    assert min(r["measured"], r["prior"]) <= r["blended"] <= max(r["measured"], r["prior"])


# ── 5 · CORRECTED CONFLUENCE PRIMITIVES ──────────────────────────────────────
def _golden_close():
    g = GOLDEN["confluence_primitives"]["inputs"]
    return pd.Series(g["close"], pd.bdate_range(g["start"], periods=len(g["close"])))


def test_confluence_primitives_golden():
    g = GOLDEN["confluence_primitives"]
    c = _golden_close()
    assert _eq(canon.rma(c, 14).to_numpy()[-10:], g["rma14_tail"])
    assert _eq(canon.ema(c, 14).to_numpy()[-10:], g["ema14_tail"])
    assert _eq(canon.rsi(c, 14).to_numpy()[-10:], g["rsi14_tail"])
    b, _ = canon.resample_sessions(c, 3)
    assert len(b) == g["session3_len"]
    assert str(b.index[-1].date()) == g["session3_last_date"]


def test_rma_is_sma_seeded():
    """The seed is the SMA of the first n bars (Pine ta.rma), not ewm-from-bar-0."""
    c = pd.Series(np.arange(1, 21, dtype=float))
    r = canon.rma(c, 5)
    assert r.iloc[:4].isna().all()          # warm-up NaN before the seed
    assert abs(r.iloc[4] - 3.0) < 1e-9      # SMA of 1..5 == 3.0
    # bare ewm(alpha=1/5) would give a different, non-3.0 value at bar 4
    bare = c.ewm(alpha=1 / 5, min_periods=5).mean()
    assert abs(bare.iloc[4] - 3.0) > 1e-6


def test_ema_is_adjust_false():
    c = pd.Series(np.arange(1, 21, dtype=float))
    assert canon.ema(c, 5).equals(c.ewm(span=5, adjust=False, min_periods=5).mean())
    # and differs from the adjust=True default
    assert not np.allclose(canon.ema(c, 5).dropna(),
                           c.ewm(span=5, min_periods=5).mean().dropna())


def test_session_resample_not_calendar_3b():
    """Session-grouping every 3rd BAR ≠ calendar resample('3B') across gaps.

    A holiday/gap makes the calendar bin re-anchor; session-grouping does not.  We insert
    a gap and assert the two produce different bucket COUNTS (the audit's ~80%-relocation
    root cause on NVDA)."""
    idx = list(pd.bdate_range("2024-01-01", periods=30))
    # drop a week mid-series to simulate a listing/holiday gap
    idx = idx[:10] + idx[20:]
    c = pd.Series(np.arange(len(idx), dtype=float), index=pd.DatetimeIndex(idx))
    session_buckets = len(canon.resample_sessions(c, 3)[0])
    calendar_buckets = len(c.resample("3B").last().dropna())
    assert session_buckets != calendar_buckets


def test_confluence_signals_columns_match_terminal():
    """The oracle frame carries exactly the columns golden_gate diffs 1:1."""
    c = _golden_close()
    # extend to ≥90 3D buckets so compute doesn't early-return
    long_c = pd.concat([c, c.iloc[-1] * (1 + pd.Series(
        np.cumsum(np.random.RandomState(1).randn(400) * 0.01),
        index=pd.bdate_range(c.index[-1] + pd.Timedelta(days=1), periods=400)))])
    sig = canon.confluence_signals(long_c)
    if sig.empty:
        pytest.skip("insufficient history for the fixture")
    for col in ("macd", "sig", "k", "d", "rsi14", "CB", "CS", "revBuy", "revSell",
                "w_bull", "above200", "mo_bull", "w2_bull"):
        assert col in sig.columns, col


# ═════════════════════════════════════════════════════════════════════════════
# 5b · THE n-SESSION GRID IS IMPLEMENTED TWICE — pin the tie AND the difference
# ═════════════════════════════════════════════════════════════════════════════
# canon's law (module docstring): "Every consumer either imports the function here or is
# validated byte-for-byte against its committed golden vector.  A concept computed two ways
# is a bug the moment the two disagree."
#
# ``confluence_tiers._tf_bars`` — the n-session grid the SHIPPED cascade, the not-topped veto,
# Door R, hold.py, setup_tier.py and grade_us_board's `_ob_mask` all ride — does NEITHER.  It
# neither imports ``resample_sessions`` nor was pinned against it.  Closing that hole is what
# this section is for, and it is the guard canon's own docstring demanded and never got.
#
# It does NOT assert the two are interchangeable.  They are not, and the difference is
# deliberate and RULED:
#
#   canon.resample_sessions      bucket = np.arange(len(s)) // n        <- ordinal from the
#                                                                          SERIES' first bar
#   confluence_tiers._tf_bars    bucket = session_positions(d) // n     <- absolute session
#                                                                          calendar
#
# canon's phase follows the caller's slice; ``_tf_bars``' phase is fixed to a reference
# calendar.  That is the whole of PR #4732 (era ``abs-session-2026-08-06``, ruling
# ``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md``): one dropped leading
# bar used to flip the tier on 13/232 names and the not-topped veto on 27/232, and the two
# production loaders disagreed about live buyability on the SAME night.  canon deliberately
# stays phase-relative because it is the CROSS-REPO oracle: ``CONFLUENCE_PARAMS["resample"]``
# is exported to the Terminal by ``scripts/export_signal_contracts.py`` and gated against
# committed golden vectors, so re-phasing it is a contract break, not a refactor.
#
# MEASURED on data/stocks (237 names, trailing 900 sessions each, 2026-08-07):
#   * as production calls them the two grids agree on only 1/237 names at n=3 (0.4%) and
#     2/237 at n=2 — the ones whose window happens to open on a bucket boundary;
#   * trimmed so each window OPENS on an absolute bucket boundary they are IDENTICAL on
#     236/237 at both n=2 and n=3.  The single residual is a name whose tape skips a
#     reference session, where canon packs across the hole and the absolute grid leaves the
#     bucket short — so the equivalence needs a CONTIGUOUS window as well as an aligned one;
#   * dropping k ∈ {1,2,4,5,7} leading sessions flips a cascade field on:
#         _tf_bars as shipped (absolute anchor)     0/1185   0.00%
#         a canon.resample_sessions delegate      152/1185  12.83%   (tier 43, veto 132)
#         the PRE-#4732 calendar {n}B bin         153/1185  12.91%   (tier 63, veto 131)
#     i.e. delegating to canon would forfeit essentially ALL of what #4732 bought — it is a
#     REGRESSION dressed as a simplification, which is why test 3 below exists.
#
# So: the same function on an aligned, contiguous window (1), never the calendar bin (2),
# and NOT substitutable in production (3) — a delegate would re-import the #4732 defect.


def _nyse(n_sessions: int, end="2026-08-04") -> pd.DatetimeIndex:
    """The last ``n_sessions`` REAL NYSE sessions ending ``end`` — real phases, real holidays.

    Contiguous in the reference calendar by construction, which is exactly the precondition
    the equivalence below needs (a tape that skips a reference session is the documented
    residual)."""
    from datetime import date

    from lib import nyse_calendar
    sessions = pd.DatetimeIndex(pd.to_datetime(
        nyse_calendar.sessions_between(date(2015, 1, 1), date.fromisoformat(end))))
    return sessions[len(sessions) - n_sessions:]


def _walk(idx: pd.DatetimeIndex, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    i = np.arange(len(idx))
    return pd.Series(
        100 * np.exp(0.3 * i / len(idx) + 0.1 * np.sin(2 * np.pi * i / 45)
                     + np.cumsum(rng.normal(0.0, 0.006, len(idx)))), index=idx)


def _aligned(c: pd.Series, n: int, market: str = "US") -> pd.Series:
    """Trim leading rows so the window OPENS on an absolute n-session bucket boundary."""
    from engine.session_anchor import session_positions
    return c.iloc[int((-int(session_positions(c.index, market)[0])) % n):]


@pytest.mark.parametrize("n", [2, 3])
def test_tf_bars_equals_canon_on_an_aligned_contiguous_window(n):
    """THE TIE.  On a contiguous window that opens on a bucket boundary, the shipped grid and
    canon's are the SAME FUNCTION — bar for bar, value and known-date.

    This is the byte-for-byte validation canon's module docstring requires of a consumer that
    does not import it.  It fails the moment either side changes what "an n-session bucket"
    means: a calendar-bin regression in ``_tf_bars`` (the pre-#4732 disease) and a redefinition
    of ``canon.resample_sessions`` both land here."""
    from engine.confluence_tiers import _tf_bars

    c = _aligned(_walk(_nyse(600)), n)
    tf_v, tf_k = _tf_bars(c, n)
    cn_v, cn_k = canon.resample_sessions(c, n)

    assert len(tf_v) == len(cn_v), f"bucket COUNT differs: {len(tf_v)} vs {len(cn_v)}"
    assert list(tf_k.to_numpy()) == list(cn_k.to_numpy()), "bucket CLOSE DATES differ"
    assert list(tf_v.index) == list(cn_v.index), "bucket LABELS differ"
    assert np.allclose(tf_v.to_numpy(), cn_v.to_numpy(), rtol=0, atol=0), "bucket CLOSES differ"


@pytest.mark.parametrize("n", [2, 3])
def test_tf_bars_is_not_a_calendar_business_day_bin(n):
    """THE REGRESSION GUARD.  ``_tf_bars`` must never go back to ``resample("{n}B")``.

    Calendar bins re-anchor on holidays and listing gaps, so which sessions share a bucket
    becomes a function of the calendar instead of the sessions present — the defect canon's
    ``resample_sessions`` was built against (~80% of NVDA signal dates relocated, audit #7)
    and the one PR #4732 removed from this module.  Real NYSE sessions carry real holidays,
    so the two bucket counts must disagree."""
    from engine.confluence_tiers import _tf_bars

    c = _walk(_nyse(600))
    assert len(_tf_bars(c, n)[0]) != len(c.resample(f"{n}B").last().dropna()), (
        f"_tf_bars produced the same bucket count as calendar resample('{n}B') over a window "
        f"containing NYSE holidays — the session grid has regressed to a calendar bin"
    )


@pytest.mark.parametrize("n", [2, 3])
def test_tf_bars_is_start_invariant_and_a_canon_delegate_would_not_be(n):
    """THE DIFFERENCE, both halves asserted separately so a reader can tell which guarantee is
    which (the house pattern from tests/test_session_anchor_invariance.py).

    ``_tf_bars`` bucket closes are a function of (reference calendar, date) alone, so dropping
    leading sessions cannot move them.  ``canon.resample_sessions`` counts ordinals from the
    series' own first bar, so a drop that is not a multiple of ``n`` re-phases every bucket.

    This is why ``_tf_bars`` MUST NOT be simplified into a ``canon.resample_sessions``
    delegate: measured on data/stocks (237 names, trailing 900 sessions), the shipped anchor
    flips a cascade field on 0/1185 (name, drop) pairs and the delegate on 152/1185 (12.83%)
    — 43 tier, 132 not_topped, 41 eligible.  It re-imports #4732's defect.

    If canon is ever re-anchored to an absolute calendar too, the SECOND half fails — that is
    a wanted notification, not a nuisance: it means the cross-repo oracle's phase moved and
    ``CONFLUENCE_PARAMS["resample"]`` plus the committed golden vectors must move with it."""
    from engine.confluence_tiers import _tf_bars

    c = _aligned(_walk(_nyse(600)), n)
    tail = lambda k: list(pd.Series(k).to_numpy()[-50:])   # noqa: E731
    drops = [k for k in (1, 2, 3, 4, 5) if k % n]          # non-multiples re-phase canon

    base_tf = tail(_tf_bars(c, n)[1])
    for k in drops:
        assert tail(_tf_bars(c.iloc[k:], n)[1]) == base_tf, (
            f"dropping {k} leading sessions moved _tf_bars' bucket closes — the absolute "
            f"session anchor (era abs-session-2026-08-06) has been lost"
        )

    base_cn = tail(canon.resample_sessions(c, n)[1])
    moved = [k for k in drops if tail(canon.resample_sessions(c.iloc[k:], n)[1]) != base_cn]
    assert moved == drops, (
        f"canon.resample_sessions was expected to re-phase on every non-multiple-of-{n} drop "
        f"{drops} but only moved on {moved}. If canon was deliberately re-anchored, "
        f"CONFLUENCE_PARAMS['resample'] and tests/golden/canon_vectors.json must change too — "
        f"scripts/export_signal_contracts.py ships that string to the Terminal as the oracle."
    )
    assert canon.CONFLUENCE_PARAMS["resample"] == "session_grouped_3", (
        "the exported cross-repo resample contract changed — regenerate the golden vectors "
        "(scripts/gen_canon_golden.py) and re-export the signal contracts deliberately"
    )


@pytest.mark.parametrize("n", [2, 3])
def test_tf_bars_and_canon_share_a_return_contract(n):
    """Shape parity is what makes the swap LOOK safe — pin it, so the file records that the
    two are drop-in compatible in SHAPE and not in SEMANTICS.  Both return
    ``(values, known_dates)`` as equal-length Series indexed by each bucket's closing session.
    ``_tf_bars`` additionally takes ``market``; canon has no such parameter, so a delegate
    would silently bucket CN/HK/CA names on whatever grid the caller's slice implied."""
    from engine.confluence_tiers import _tf_bars

    c = _aligned(_walk(_nyse(400)), n)
    for v, k in (_tf_bars(c, n), canon.resample_sessions(c, n)):
        assert isinstance(v, pd.Series) and isinstance(k, pd.Series)
        assert len(v) == len(k)
        assert isinstance(v.index, pd.DatetimeIndex)
        assert list(v.index) == list(k.index)
        assert list(k.to_numpy()) == list(pd.DatetimeIndex(v.index).to_numpy())
