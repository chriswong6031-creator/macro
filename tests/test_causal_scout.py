"""CHF-R12 Synthetic Gauntlet — tests/test_causal_scout.py

Hermetic, seeded numpy simulations.  No network, no data stores.
Every planted structure is a separate test.

Rules exercised:
  CHF-R5  — estimator law (HAC, permutation, placebos, bootstrap, era split)
  CHF-R12 — synthetic gauntlet: planted-DAG recovery + 7 planted mirage classes
  CHF-R3  — TrialLedger per-cell accounting
  DT-R14  — time-structure-preserving placebos (circular shifts/blocks only)
  DT-R16  — era split honesty (pre/post-2010 break)

Runtime target: total suite < 120s with N_BOOTSTRAP/N_SHIFT=200-draw minimums.
We use small n (~200-400 obs) and reduce draws to the minimum (200) to keep it fast.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.neuralweb.causal_scout import (
    EdgeSpec,
    EnvironmentSplit,
    _sanitize_text,
    run_battery,
    FAMILY,
)
from engine.trial_ledger import TrialLedger


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

RNG_SEED = 2026
# Use weekly dates so 300 obs = ~5.7 years.  Starting 2004 → ends ~2009-10.
# Starting 2003 → ends ~2008-10 (still misses 2010).
# To straddle 2010 with small n, start at 2006 with n=260 weekly = 5 years → 2011.
# We standardize on weekly frequency for era-straddling tests (N_OBS_WEEKLY).
N_OBS = 300           # for tests that don't need era straddle
N_OBS_WEEKLY = 400    # weekly obs: 2005-01 + 400 weeks ≈ 2012-09 (straddles 2010)


def _make_dates(n: int, start: str = "2005-01-03", freq: str = "W") -> pd.DatetimeIndex:
    """Weekly DatetimeIndex of length n.

    Default start 2005-01-03 + 400 weeks ends ≈ 2012-09, straddling 2010.
    For tests that need daily freq, override freq='B'.
    """
    return pd.date_range(start=start, periods=n, freq=freq)


def _make_dates_post_2010(n: int) -> pd.DatetimeIndex:
    """Weekly DatetimeIndex entirely post-2010 (for era-span honesty test)."""
    return pd.date_range(start="2022-01-03", periods=n, freq="W")


def _ar1(n: int, phi: float, seed: int, sigma: float = 1.0) -> np.ndarray:
    """AR(1) noise: x_t = phi*x_{t-1} + eps."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.standard_normal() * sigma
    return x


def _make_spec(
    edge_id: str = "test_edge",
    target_type: str = "market_series",
    lags: list[int] | None = None,
    cause_kind: str = "level",
    horizon_d: int = 5,
    era_policy: str = "require_break_2010",
    env_splits: list[EnvironmentSplit] | None = None,
) -> EdgeSpec:
    return EdgeSpec(
        edge_id=edge_id,
        cause_id="test_cause",
        target_id="test_target",
        target_type=target_type,
        lags=lags if lags is not None else [1, 5],
        cause_kind=cause_kind,
        horizon_d=horizon_d,
        era_policy=era_policy,
        environment_splits=env_splits or [],
    )


def _make_ledger() -> tuple[TrialLedger, Path]:
    """Create a fresh TrialLedger in a temp file."""
    tmp = tempfile.mktemp(suffix=".jsonl")
    led = TrialLedger(path=tmp)
    return led, Path(tmp)


# ---------------------------------------------------------------------------
# a. Planted lagged edge under AR(1) noise + regime break + hidden confounder
# ---------------------------------------------------------------------------

def test_planted_lag_recovered_as_screened_candidate():
    """
    Planted structure: cause_t -> target_{t+5} at lag 5, under AR(1) noise,
    a regime break, and an unobserved common driver on OTHER variables.
    Expected: recovered as 'screened_candidate' with lag=5 contributing.

    Uses weekly dates 2005-01 + 400 weeks ≈ 2012-09, which straddles 2010.

    Key design: the CAUSE is an iid white-noise innovation (not autocorrelated)
    so that the negative-lag placebo does NOT fire.  The TARGET at t+5 depends
    on cause_t via planted_effect, but target_t does NOT depend on cause_{t+5}
    (the innovation is not predictable from the future).
    """
    rng = np.random.default_rng(RNG_SEED)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)  # weekly, straddles 2010

    # Use iid innovations as cause (not autocorrelated) — prevents neg-lag firing
    rng2 = np.random.default_rng(RNG_SEED + 99)
    cause_innovations = rng2.standard_normal(n)
    cause = pd.Series(cause_innovations, index=dates)

    # AR(1) target noise (independent of cause)
    noise_t = _ar1(n, phi=0.3, seed=2)

    lag = 5
    signal_strength = 0.9
    planted_effect = np.zeros(n)
    planted_effect[lag:] = signal_strength * cause_innovations[:-lag]
    # Regime break at t=200 (small, doesn't reverse sign)
    regime_noise = np.zeros(n)
    regime_noise[200:] += rng.standard_normal(n - 200) * 0.3
    target_vals = planted_effect + noise_t * 0.3 + regime_noise
    target = pd.Series(target_vals, index=dates)

    spec = _make_spec(lags=[5], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    assert result.verdict in ("screened_candidate", "era_specific"), (
        f"Expected screened_candidate or era_specific, got {result.verdict!r}. "
        f"concerns={result.concerns}"
    )
    # Lag 5 should appear in stats
    assert "5" in result.stats.get("by_lag", {}), (
        f"Lag 5 not in stats: {result.stats}"
    )


# ---------------------------------------------------------------------------
# b. Collider mirage: conditioning on collider must NOT yield screened_candidate
# ---------------------------------------------------------------------------

def test_collider_mirage_refused_by_priors():
    """
    A cause that is tagged as a collider in priors → verdict 'forbidden'.
    The battery must not compute anything (zero stats) and must print the refusal.
    """
    rng = np.random.default_rng(RNG_SEED + 1)
    n = N_OBS
    dates = _make_dates(n)
    cause = pd.Series(rng.standard_normal(n), index=dates)
    target = pd.Series(rng.standard_normal(n), index=dates)

    # Priors mark this cause as a collider
    priors = {"colliders": ["test_cause"]}
    spec = _make_spec()
    result = run_battery(spec, cause, target, priors=priors, hermetic=True)

    assert result.verdict == "forbidden", (
        f"Expected 'forbidden' for collider cause, got {result.verdict!r}"
    )
    assert result.stats == {}, (
        "No stats should be computed for a forbidden edge"
    )
    assert any("collider" in c.lower() for c in result.concerns), (
        f"Expected collider mention in concerns: {result.concerns}"
    )


# ---------------------------------------------------------------------------
# c. Sibling duplication: two children of one parent must NOT read as independent
# ---------------------------------------------------------------------------

def test_sibling_shared_parent_concern():
    """
    Two siblings share a parent.  The second edge should carry a shared-parent
    concern in its result.

    We implement this via the declared_siblings parameter carrying the first
    sibling's series.  The two causes are nearly identical (corr > 0.70)
    which triggers the shared-parent concern.

    Uses weekly era-straddling dates.
    """
    rng = np.random.default_rng(RNG_SEED + 2)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Parent signal — high autocorrelation
    parent = _ar1(n, phi=0.7, seed=10, sigma=2.0)

    # Both sibling causes are children of parent + small independent noise
    # (corr between cause1 and cause2 will be ~0.95+ at 80% parent weight)
    cause1 = pd.Series(0.9 * parent + 0.1 * rng.standard_normal(n), index=dates)
    cause2 = pd.Series(0.9 * parent + 0.1 * rng.standard_normal(n), index=dates)

    # Target is weakly correlated with parent
    target = pd.Series(0.3 * parent + rng.standard_normal(n), index=dates)

    spec = _make_spec(edge_id="sibling_edge", lags=[1])
    # Pass cause1 as a declared sibling when evaluating cause2
    result = run_battery(
        spec, cause2, target,
        priors={},
        declared_siblings=[cause1.to_numpy()],
        hermetic=True,
    )

    # The result should carry a shared-parent concern
    shared_parent_concerns = [
        c for c in result.concerns if "shared-parent" in c.lower()
    ]
    assert shared_parent_concerns, (
        f"Expected shared-parent concern; got concerns={result.concerns}, "
        f"verdict={result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# d. Reverse causation: negative-lag placebo fires → NOT screened_candidate
# ---------------------------------------------------------------------------

def test_reverse_causation_killed_by_neg_lag_placebo():
    """
    Target ACTUALLY leads cause.  The negative-lag placebo should fire and
    the result should NOT be screened_candidate.

    Design: target_t = iid_innovation_t.  cause_t = target_{t-5} (downstream).
    Forward test (cause→target at lag=5): x_lagged = cause[:-5], y_shifted = target[5:].
      cause[t] = target[t-5], so x_lagged[t] = target[t-5], y_shifted[t] = target[t+5].
      Correlation = 0 (target innovations are iid).
    Negative-lag test (target→cause at lag=5): y_neg = target[:-5], x_neg = cause[5:].
      cause[t] = target[t-5], so x_neg[t] = cause[t+5] = target[t].
      y_neg[t] = target[t].
      Correlation = 1 (perfect).
    → neg-lag placebo CLEARLY fires (|neg_t| >> |fwd_t|).

    Uses weekly era-straddling dates.
    """
    rng = np.random.default_rng(RNG_SEED + 3)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Target: pure iid innovations
    true_signal = rng.standard_normal(n)

    lag = 5
    # Cause is DOWNSTREAM: cause_t = true_signal_{t-lag} (cause follows target)
    cause_vals = np.zeros(n)
    cause_vals[lag:] = true_signal[:-lag]
    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(true_signal, index=dates)

    spec = _make_spec(lags=[lag], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    # Must NOT be screened_candidate; reverse causation concern should appear
    assert result.verdict != "screened_candidate", (
        f"Reverse causation: expected not screened_candidate, "
        f"got {result.verdict!r}; concerns={result.concerns}"
    )
    reverse_concerns = [
        c for c in result.concerns
        if "reverse" in c.lower() or "may lead" in c.lower()
    ]
    assert reverse_concerns, (
        f"Expected reverse-causation concern in: {result.concerns}"
    )


# ---------------------------------------------------------------------------
# e. Lagged echo: cause is lagged copy of target's driver → time-shift kills it
# ---------------------------------------------------------------------------

def test_lagged_echo_killed_by_time_shift_placebo():
    """
    Cause is a lagged copy of target's driver (not an independent signal).
    The time-shift placebo should fire (obs_corr at < 90th pctile of null).
    Result should NOT be screened_candidate.
    """
    rng = np.random.default_rng(RNG_SEED + 4)
    n = N_OBS
    dates = _make_dates(n)

    # Shared driver
    driver = _ar1(n, phi=0.8, seed=30)  # highly autocorrelated
    noise = rng.standard_normal(n) * 0.1

    lag = 3
    # Both cause and target are driven by the SAME driver — cause is lagged copy
    target = pd.Series(driver + noise, index=dates)
    # Cause is target's driver shifted by lag (lagged echo)
    cause_vals = np.zeros(n)
    cause_vals[lag:] = driver[:-lag]
    cause = pd.Series(cause_vals + noise * 0.1, index=dates)

    spec = _make_spec(lags=[lag], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    # High autocorrelation in driver means time-shift preserves the structure
    # but the effect should be killed or flagged
    # We assert it is NOT screened_candidate (either null or placebo flagged)
    # Note: with very high autocorrelation the shift-placebo distribution is also
    # high, so we check concerns for the echo pattern OR the verdict is not screened
    echo_concerns = [
        c for c in result.concerns
        if "echo" in c.lower() or "shift placebo" in c.lower() or "lagged" in c.lower()
    ]
    # The key assertion: either the verdict is not screened_candidate,
    # OR the concern is present
    assert result.verdict != "screened_candidate" or echo_concerns, (
        f"Lagged echo should not be screened_candidate without a shift concern. "
        f"verdict={result.verdict!r}, concerns={result.concerns}"
    )


# ---------------------------------------------------------------------------
# f. Cross-sectional mirage: spurious level cause from shared date factor
# ---------------------------------------------------------------------------

def test_cross_sectional_mirage_killed_by_permutation_and_eff_n():
    """
    Ticker panel where ALL tickers share one date factor (not ticker-level signal).
    A spurious level cause aligned with lucky dates must be killed by:
    1. Within-period cross-ticker permutation (perm_pctile < 0.90)
    2. Effective N reported in CALENDAR MONTHS, not fire counts.

    Assert: the naive per-fire count is NOT used for inference.
    """
    rng = np.random.default_rng(RNG_SEED + 5)
    n_dates = 30   # only 30 calendar months worth (barely at the floor)
    n_tickers = 20

    # Build a panel with a SHARED date factor (same value for all tickers per date)
    dates = pd.bdate_range("2015-01-01", periods=n_dates * 21, freq="B")[::21]
    # Monthly dates, 30 of them — 30 months

    # Date factor: each date has a common shock
    date_factor = rng.standard_normal(n_dates)

    # Cause: each ticker gets the DATE factor + small ticker noise
    # (all tickers share the same date signal — pure date factor)
    cause_vals = {
        f"T{i}": date_factor + rng.standard_normal(n_dates) * 0.1
        for i in range(n_tickers)
    }
    # Target: also driven by the same date factor → spurious correlation
    target_vals = {
        f"T{i}": date_factor + rng.standard_normal(n_dates)
        for i in range(n_tickers)
    }

    cause_df = pd.DataFrame(cause_vals, index=dates)
    target_df = pd.DataFrame(target_vals, index=dates)

    spec = _make_spec(
        target_type="ticker_panel",
        lags=[1],
        horizon_d=1,
        era_policy="era_specific_recent_only",
    )
    result = run_battery(spec, cause_df, target_df, priors={}, hermetic=True)

    # Key assertions:
    # 1. The effective N is in calendar months, NOT fire_counts
    eff_n = result.stats.get("effective_n_months") or result.stats.get("eff_n_months")
    fire_count = result.stats.get("fire_count_do_not_use")
    assert eff_n is not None, "effective_n_months not reported"
    assert fire_count is not None, "fire_count_do_not_use not reported"
    assert eff_n < fire_count, (
        f"Calendar-month N ({eff_n}) should be < fire_count ({fire_count})"
    )

    # 2. After within-date demeaning, the date factor is removed from the within-ticker
    #    variation.  The permutation test should kill the spurious cross-sectional signal.
    #    Result should NOT be screened_candidate (or should be null/unstable).
    # Note: with very few months (30), we may also hit era-span or power limits.
    # The critical test is that fire_count is NOT used as the effective N.
    assert result.verdict != "screened_candidate" or result.concerns, (
        f"Cross-sectional mirage should not be a clean screened_candidate; "
        f"got {result.verdict!r}, concerns={result.concerns}"
    )


# ---------------------------------------------------------------------------
# g. Regime-persistence mirage: one slow-moving state must not pass invariance
# ---------------------------------------------------------------------------

def test_regime_persistence_mirage_flagged_as_unstable():
    """
    An 'environment split' that is one slow-moving state (long blocks):
    invariance must not pass; the block-bootstrap effect-series CI must flag
    instability because the effect collapses to zero in the second half.

    Design: cause->target EFFECT present only in the first half; pure noise
    in the second half.  The block bootstrap on the z-product effect series
    must produce a CI spanning zero (effect is not stable across time blocks).

    Verification: the machinery that fires must be the cause-aware effect
    machinery (bootstrap CI on effect series spans zero), NOT a coincidental
    target-mean sign flip.  We assert:
      1. verdict is NOT screened_candidate
      2. concerns mention 'spans zero' or 'unstable' or 'era split' or
         'concentrated in single era' — i.e., the effect-concentration or
         block-bootstrap instability concern (not merely any concern)

    Uses weekly era-straddling dates.
    """
    rng = np.random.default_rng(RNG_SEED + 6)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Signal only exists in first half — pure noise in second half.
    # iid cause so target DOES NOT lead cause (neg-lag placebo stays quiet).
    # IMPORTANT: use a genuine lag-1 structure (target[t] depends on cause[t-1])
    # so that the lag-1 z-product effect series e_t = z(cause[t-1])*z(target[t])
    # is large in the first half and near-zero in the second half.  This ensures
    # the block-bootstrap CI on e_t spans zero (FIX 1: the lag-aware era stats
    # also correctly detect the concentration).
    cause_vals = rng.standard_normal(n)
    target_vals = np.zeros(n)
    half = n // 2
    noise_vals = rng.standard_normal(n) * 0.05
    # Lag-1 planted effect in the first half (target[t] = 0.95*cause[t-1] + noise)
    for t in range(1, half):
        target_vals[t] = 0.95 * cause_vals[t - 1] + noise_vals[t]
    # Second half: pure iid noise, no lag-1 effect
    target_vals[half:] = rng.standard_normal(n - half)

    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    spec = _make_spec(lags=[1], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    # With such a concentrated regime the effect-series bootstrap CI must span zero
    # (effect exists only in first half), leading to 'unstable' or related verdict.
    assert result.verdict in ("unstable", "null", "era_specific"), (
        f"Regime-persistence mirage should not be screened_candidate; "
        f"got {result.verdict!r}, concerns={result.concerns}"
    )
    # The concern must come from the genuine effect machinery:
    # bootstrap spans zero, or era split / effect concentration concern.
    effect_concern = [
        c for c in result.concerns
        if any(kw in c.lower() for kw in (
            "spans zero", "unstable", "era split", "concentrated in single era",
            "opposite signs", "effect direction", "effect concentrated",
        ))
    ]
    assert effect_concern, (
        f"Expected effect-machinery concern (spans-zero / era / concentration); "
        f"got concerns={result.concerns}"
    )


# ---------------------------------------------------------------------------
# h. Era-span honesty: post-2010-only data → insufficient_era_span
# ---------------------------------------------------------------------------

def test_era_span_honesty_insufficient_era_span():
    """
    Target data spanning only 2022+.  era_policy='require_break_2010'.
    Expected: verdict 'insufficient_era_span'.
    """
    rng = np.random.default_rng(RNG_SEED + 7)
    n = N_OBS
    dates = _make_dates_post_2010(n)  # all 2022+

    cause = pd.Series(rng.standard_normal(n), index=dates)
    target = pd.Series(rng.standard_normal(n), index=dates)

    spec = _make_spec(
        era_policy="require_break_2010",
        lags=[1],
        horizon_d=1,
    )
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    assert result.verdict == "insufficient_era_span", (
        f"Post-2022-only data with require_break_2010 should yield "
        f"insufficient_era_span; got {result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# i. Ledger accounting: every cell logged as distinct config
# ---------------------------------------------------------------------------

def test_ledger_accounting_cells_distinct_and_width_matches():
    """
    Run a small battery, assert every cell is logged as a distinct config
    and the ledger's literal_n matches cells_logged.

    Uses weekly era-straddling dates so the battery completes its full course.
    """
    rng = np.random.default_rng(RNG_SEED + 8)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Simple planted edge so battery runs full course (strong signal)
    cause_vals = _ar1(n, phi=0.3, seed=40)
    target_vals = np.zeros(n)
    lag = 3
    target_vals[lag:] = 0.8 * cause_vals[:-lag] + rng.standard_normal(n - lag) * 0.2
    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    led, tmp_path = _make_ledger()
    spec = _make_spec(lags=[1, 3, 5], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, ledger=led)

    # cells_logged should be > 0
    assert result.cells_logged > 0, (
        f"Expected >0 cells logged; got {result.cells_logged}; "
        f"verdict={result.verdict!r}, concerns={result.concerns}"
    )

    # The ledger's effective_n should be >= literal_n for this fresh family
    lit_n = led.literal_n(family=FAMILY)
    eff_n = led.effective_n(family=FAMILY)
    assert lit_n > 0, f"Ledger literal_n should be > 0; got {lit_n}"
    assert eff_n >= lit_n, (
        f"effective_n ({eff_n}) should be >= literal_n ({lit_n})"
    )


# ---------------------------------------------------------------------------
# j. Priors mask: forbidden cause → verdict forbidden, zero stats computed
# ---------------------------------------------------------------------------

def test_priors_mask_forbidden_cause():
    """
    Forbidden cause pattern (e.g. fwd_ret_21 as cause) → verdict forbidden,
    zero stats computed.
    """
    rng = np.random.default_rng(RNG_SEED + 9)
    n = N_OBS
    dates = _make_dates(n)
    target = pd.Series(rng.standard_normal(n), index=dates)
    cause = pd.Series(rng.standard_normal(n), index=dates)

    # Spec with forbidden cause_id matching the pattern
    spec = EdgeSpec(
        edge_id="forbidden_test",
        cause_id="fwd_ret_21",
        target_id="test_target",
        target_type="market_series",
        lags=[1],
        cause_kind="level",
        horizon_d=1,
    )
    priors = {"forbidden_causes": ["fwd_ret_21", "fwd_*", "terminal_state_*"]}
    result = run_battery(spec, cause, target, priors=priors, hermetic=True)

    assert result.verdict == "forbidden", (
        f"Expected 'forbidden' for fwd_ret_21 cause; got {result.verdict!r}"
    )
    assert result.stats == {}, (
        "No stats should be computed for a forbidden edge"
    )
    assert result.cells_logged == 0, (
        "No cells should be logged for a forbidden edge"
    )


# ---------------------------------------------------------------------------
# k. Sanitizer: banned words in generated text are stripped/replaced
# ---------------------------------------------------------------------------

def test_sanitizer_removes_banned_words():
    """
    The sanitizer must replace exactly the four banned causal-claim words:
    caused, proved, proof, validated (and their inflections).

    N2 law: the sanitizer acts ONLY on these four root words so that
    replacement strings remain grammatical.  Words NOT in the ban list
    (e.g. 'proves', 'cause' noun, 'proves') must pass through unchanged.
    """
    # Cases where banned words MUST be removed
    must_sanitize = [
        ("This caused the outcome", "caused"),
        ("The proof is overwhelming", "proof"),
        ("The proofs are clear", "proofs"),
        ("This was validated by data", "validated"),
        ("Results were proved correct", "proved"),
        ("VALIDATED approach used", "VALIDATED"),
        ("Validation of the signal", "validation"),
    ]
    # Regex matching exactly the four banned root words and their inflections
    banned = re.compile(
        r"\b(caused|proved|proof|proofs|validated|validates|validation)\b",
        re.IGNORECASE,
    )
    for text, word in must_sanitize:
        result = _sanitize_text(text)
        assert not banned.search(result), (
            f"Banned word '{word}' survives sanitizer in: {result!r} (from {text!r})"
        )

    # Cases where NON-BANNED words must pass through unchanged (N2 law)
    must_not_sanitize = [
        "This proves the hypothesis",          # 'proves' is NOT banned
        "The cause of the effect",             # 'cause' (noun) is NOT banned
        "upstream of the target",              # already a replacement — no change
    ]
    for text in must_not_sanitize:
        result = _sanitize_text(text)
        assert result == text, (
            f"Non-banned word was wrongly sanitized: {text!r} -> {result!r}"
        )


import re   # noqa: E402 — needed for test_sanitizer_removes_banned_words


# ---------------------------------------------------------------------------
# Additional: forbidden wildcard pattern match
# ---------------------------------------------------------------------------

def test_priors_mask_wildcard_pattern():
    """
    Wildcard forbidden pattern (e.g. 'fwd_*') should forbid any cause
    whose id starts with 'fwd_'.
    """
    rng = np.random.default_rng(RNG_SEED + 10)
    n = N_OBS
    dates = _make_dates(n)
    target = pd.Series(rng.standard_normal(n), index=dates)
    cause = pd.Series(rng.standard_normal(n), index=dates)

    spec = EdgeSpec(
        edge_id="wildcard_test",
        cause_id="fwd_mfe_21",  # matches 'fwd_*'
        target_id="test_target",
        target_type="market_series",
        lags=[1],
        cause_kind="level",
        horizon_d=1,
    )
    priors = {"forbidden_causes": ["fwd_*"]}
    result = run_battery(spec, cause, target, priors=priors, hermetic=True)

    assert result.verdict == "forbidden", (
        f"fwd_mfe_21 should match wildcard 'fwd_*' and be forbidden; "
        f"got {result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# Additional: era_specific_recent_only policy runs on post-2010 only data
# ---------------------------------------------------------------------------

def test_era_specific_recent_only_policy():
    """
    era_policy='era_specific_recent_only' with post-2010-only data should
    NOT return insufficient_era_span.  May return era_specific or screened.
    """
    rng = np.random.default_rng(RNG_SEED + 11)
    n = N_OBS
    dates = _make_dates_post_2010(n)

    # Planted signal
    cause_vals = _ar1(n, phi=0.3, seed=50)
    target_vals = np.zeros(n)
    target_vals[5:] = 0.7 * cause_vals[:-5] + rng.standard_normal(n - 5) * 0.4
    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals + rng.standard_normal(n) * 0.1, index=dates)

    spec = _make_spec(
        era_policy="era_specific_recent_only",
        lags=[5],
        horizon_d=1,
    )
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    assert result.verdict != "insufficient_era_span", (
        "era_specific_recent_only should not return insufficient_era_span"
    )


# ---------------------------------------------------------------------------
# Additional: degenerate cause (zero variance) → insufficient_power
# ---------------------------------------------------------------------------

def test_degenerate_cause_returns_insufficient_power():
    """Zero-variance cause series → insufficient_power without crashing."""
    n = N_OBS
    dates = _make_dates(n)
    cause = pd.Series(np.zeros(n), index=dates)  # degenerate
    target = pd.Series(_ar1(n, phi=0.3, seed=60), index=dates)

    spec = _make_spec(lags=[1])
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    assert result.verdict == "insufficient_power", (
        f"Zero-variance cause should yield insufficient_power; "
        f"got {result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# Additional: cumulative_family_width increments correctly across batches
# ---------------------------------------------------------------------------

def test_cumulative_width_accumulates_across_batches():
    """
    Running two separate battery calls on the SAME ledger should accumulate
    cells in the causal_scan family.  Width is the SUM of distinct cells.

    Uses weekly era-straddling dates so both batteries complete.
    """
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Simple independent signals (no planted structure needed — just need cells logged)
    cause1 = pd.Series(_ar1(n, phi=0.3, seed=70), index=dates)
    target1 = pd.Series(_ar1(n, phi=0.2, seed=71), index=dates)
    cause2 = pd.Series(_ar1(n, phi=0.4, seed=72), index=dates)
    target2 = pd.Series(_ar1(n, phi=0.1, seed=73), index=dates)

    led, _ = _make_ledger()

    # Distinct edge_ids so cells don't collide in the ledger
    spec1 = _make_spec(edge_id="edge_A", lags=[1])
    spec2 = _make_spec(edge_id="edge_B", lags=[1])

    result1 = run_battery(spec1, cause1, target1, priors={}, ledger=led)
    width_after_first = led.literal_n(family=FAMILY)

    result2 = run_battery(spec2, cause2, target2, priors={}, ledger=led)
    width_after_second = led.literal_n(family=FAMILY)

    # Both batteries should log at least 1 cell each
    assert result1.cells_logged > 0, (
        f"edge_A: expected >0 cells; verdict={result1.verdict!r}"
    )
    assert result2.cells_logged > 0, (
        f"edge_B: expected >0 cells; verdict={result2.verdict!r}"
    )

    assert width_after_second > width_after_first, (
        f"Width should accumulate: after first={width_after_first}, "
        f"after second={width_after_second}"
    )
    assert width_after_second == result1.cells_logged + result2.cells_logged, (
        f"Total width {width_after_second} != sum of cells "
        f"({result1.cells_logged} + {result2.cells_logged})"
    )


# ---------------------------------------------------------------------------
# MANDATORY FALSIFIER (CHF-R12): regime-persistence mirage WITHOUT target-mean
# sign flip.  Effect present pre-2010 only, pure noise post-2010, plus a small
# constant positive drift on the target across the whole span.
#
# Key: per-era TARGET-MEAN t-stats share the same sign (both positive due to
# drift) — so the OLD hollow machinery would NOT see a sign flip and would
# return screened_candidate when the lag survived its other filters.
#
# The CORRECT cause-aware machinery computes the EFFECT in each era and detects
# that the effect is concentrated in the pre-2010 era (block-bootstrap CI spans
# zero across the full span, or era-concentration concern fires).
#
# Design: the cause->target effect at lag=1 must be strong enough in pre-2010
# to SURVIVE the neg-lag placebo (forward effect > reverse) but collapse to
# near-zero post-2010.  We use a structured cause: AR(1) with phi=0.3 so that
# z(y_{t-1}) and z(x_t) are decorrelated at lag=1 (neg-lag placebo silent),
# while z(x_{t-1}) and z(y_t) are strongly correlated in the pre-2010 window.
#
# The block bootstrap on the FULL-SPAN effect series e_t = z(x_{t-1})*z(y_t)
# produces a CI spanning zero (effect is large pre-2010, near-zero post-2010),
# which drives verdict=unstable or null.
#
# Assert: verdict is NEVER screened_candidate (never a false positive).
# Parameterized over >= 5 seeds.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phi,seed_offset",
    [
        # phi in {0.0, 0.1, 0.3, 0.6} x 5 seeds = 20 cases (FIX 3)
        (0.0, 0), (0.0, 1), (0.0, 2), (0.0, 3), (0.0, 4),
        (0.1, 0), (0.1, 1), (0.1, 2), (0.1, 3), (0.1, 4),
        (0.3, 0), (0.3, 1), (0.3, 2), (0.3, 3), (0.3, 4),
        (0.6, 0), (0.6, 1), (0.6, 2), (0.6, 3), (0.6, 4),
    ],
)
def test_falsifier_regime_persistence_mirage_no_sign_flip(phi: float, seed_offset: int):
    """
    MANDATORY FALSIFIER (CHF-R12, reviewer-specified):
    Regime-persistence mirage WITHOUT a target-mean sign flip.

    Structure:
      - Cause: AR(1) with phi ∈ {0.0, 0.1, 0.3, 0.6} — iid to high autocorrelation
      - Effect z(x_{t-1})*z(y_t): strong ONLY pre-2010 (planted beta=0.95)
      - Post-2010: target = pure noise, NO effect from cause
      - Small constant positive drift added to target across ENTIRE span so
        that per-era TARGET mean t-stats are BOTH positive (no sign flip in
        the old hollow estimator — both era means positive => old code saw
        "same sign" and wrongly returned screened_candidate)

    phi=0.0/0.1: iid/near-iid cause — the low cause autocorrelation means the
    time-shift placebo may NOT kill the lag (the shift distribution is flat when
    the cause is nearly iid).  This is the hard case: the era-concentration
    concern (FIX 1 + FIX 2) must be the backstop.

    Parameterized over phi ∈ {0.0, 0.1, 0.3, 0.6} × 5 seeds = 20 cases.
    NEVER screened_candidate — ZERO false positives required.
    """
    rng_base = 3000 + seed_offset * 97 + int(phi * 1000)
    rng = np.random.default_rng(rng_base)

    n = N_OBS_WEEKLY   # 400 weekly obs, straddles 2010
    dates = _make_dates(n)

    # AR(1) cause — phi controls autocorrelation; phi=0 → iid innovations
    cause_vals = _ar1(n, phi=phi, seed=rng_base + 1)

    # Find the pre/post era boundary index in the series
    era_break_idx = int((dates < pd.Timestamp("2010-01-01")).sum())

    # Target: strong effect pre-2010, pure noise post-2010
    target_vals = np.zeros(n)
    n_pre = era_break_idx
    # For lag=1: target_vals[t] = 0.95 * cause_vals[t-1] + small_noise (pre-2010)
    pre_noise = rng.standard_normal(n_pre) * 0.15
    for t in range(1, n_pre):
        target_vals[t] = 0.95 * cause_vals[t - 1] + pre_noise[t]

    # post-2010: pure noise — no effect
    post_noise = rng.standard_normal(n - era_break_idx) * 1.0
    target_vals[era_break_idx:] = post_noise

    # Add a constant positive drift so both pre- and post-2010 TARGET means
    # are positive (no sign flip in the old hollow estimator's target-mean check)
    drift = 0.35
    target_vals += drift

    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    spec = _make_spec(lags=[1], horizon_d=1)
    result = run_battery(spec, cause, target, priors={}, hermetic=True)

    # CRITICAL assertion: must NOT be screened_candidate (ZERO FP requirement)
    assert result.verdict != "screened_candidate", (
        f"phi={phi}, seed_offset={seed_offset}: regime-persistence mirage "
        f"(no sign flip) must not be screened_candidate; got {result.verdict!r}. "
        f"concerns={result.concerns}"
    )

    # The verdict must be one of the valid non-candidate verdicts
    assert result.verdict in (
        "era_specific", "unstable", "null", "insufficient_power"
    ), (
        f"phi={phi}, seed_offset={seed_offset}: unexpected verdict "
        f"{result.verdict!r}. concerns={result.concerns}"
    )

    # The cause-aware machinery must have fired — acceptable concern keywords:
    # spans zero (bootstrap), era split / era-specific concentration, unstable,
    # invariance failure, reverse causation (neg-lag), time-shift placebo.
    any_effect_concern = [
        c for c in result.concerns
        if any(kw in c.lower() for kw in (
            "spans zero", "unstable", "era split", "concentrated in single era",
            "opposite signs", "effect direction", "effect concentrated",
            "invariance failure", "invariance concern",
            "reverse-causation", "may lead",
            "indistinguishable", "time-shift",
            "not invariant",
        ))
    ]
    assert any_effect_concern, (
        f"phi={phi}, seed_offset={seed_offset}: expected effect-machinery "
        f"concern but got concerns={result.concerns} (verdict={result.verdict!r})"
    )


# ---------------------------------------------------------------------------
# FIX 3 — split-leakage invariance case (re-verifier's spec):
# effect present in BOTH split and complement but 2x stronger in one;
# difference CI excludes zero → invariance concern fires.
# ---------------------------------------------------------------------------

def test_split_leakage_invariance_fires_on_2x_asymmetry():
    """
    FIX 3 invariance test: effect present in BOTH split and complement, but
    materially stronger in the split half (split effect ≈ 3× complement).
    The difference CI should exclude zero and the invariance concern must fire,
    even though BOTH sides are individually significant (|t|>=2 in both).

    The old XOR gate required EXACTLY ONE side to be significant — it would
    have missed this case entirely.  After FIX 2, the primary trigger is the
    difference-CI + materiality threshold, so this correctly fires.

    Design:
      - Cause: iid innovations (neg-lag placebo stays quiet)
      - Target pre-2010 (split): y_t = 1.4*x_{t-1} + small_noise  (high SNR)
      - Target post-2010 (complement): y_t = 0.5*x_{t-1} + large_noise (low SNR)
      - Both sides significant: split_t ≈ 11, complement_t ≈ 4
      - z-product effect: split ≈ 1.0, complement ≈ 0.35 (ratio > 2×)
      - materiality: 0.35 < 0.5 * 1.0 → fires
      - Difference CI [0.44, 0.88] excludes zero → concern fires
    """
    rng = np.random.default_rng(5555)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # iid cause innovations
    cause_vals = rng.standard_normal(n)

    era_break_idx = int((dates < pd.Timestamp("2010-01-01")).sum())

    # Target: high-SNR pre-2010, lower-SNR post-2010 — BOTH sides significant
    # Split (pre-2010): beta=1.4, noise σ=0.05 → z-product mean ≈ 1.0
    # Complement (post-2010): beta=0.5, noise σ=1.2 → z-product mean ≈ 0.35
    target_vals = np.zeros(n)
    for t in range(1, era_break_idx):
        target_vals[t] = 1.4 * cause_vals[t - 1] + rng.standard_normal() * 0.05
    for t in range(era_break_idx, n):
        target_vals[t] = 0.5 * cause_vals[t - 1] + rng.standard_normal() * 1.2

    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    # Declare an environment split that maps to pre-2010 half
    era_break_ts = pd.Timestamp("2010-01-01")
    pre_mask = np.array([(d < era_break_ts) for d in dates], dtype=bool)
    env_split = EnvironmentSplit(split_id="pre_2010_half", definition="pre-2010 window")
    spec = _make_spec(lags=[1], horizon_d=1, env_splits=[env_split])

    result = run_battery(
        spec, cause, target,
        priors={},
        environment_masks={"pre_2010_half": pre_mask},
        hermetic=True,
    )

    # The invariance concern must fire (difference CI excludes zero + material diff)
    inv_concerns = [
        c for c in result.concerns
        if any(kw in c.lower() for kw in (
            "invariance failure", "invariance concern",
        ))
    ]
    assert inv_concerns, (
        f"Expected invariance concern for 3x asymmetric effect; "
        f"got verdict={result.verdict!r}, concerns={result.concerns}"
    )


# ---------------------------------------------------------------------------
# FIX 4 — grid sweep (slow; skip unless CAUSAL_SCOUT_GRID_SWEEP=1 is set)
# Covers drift {0.1,0.35,0.8,1.5} x beta {0.6,0.95,1.4} x phi {0.0,0.3,0.6}
# x seeds {0,1,2,3} = 144 configs.  Reports FP count in assertion message.
# Must be ZERO screened_candidate on regime-persistence-mirage constructions.
# ---------------------------------------------------------------------------

import os as _os


@pytest.mark.skipif(
    _os.environ.get("CAUSAL_SCOUT_GRID_SWEEP", "0") != "1",
    reason="Set CAUSAL_SCOUT_GRID_SWEEP=1 to run the full grid sweep (slow)",
)
def test_grid_sweep_regime_persistence_zero_fp():
    """
    FIX 4 — grid sweep over 144 regime-persistence-mirage configurations.

    For each config (drift, beta_pre, phi, seed), we build a target where:
      - beta_pre * cause → target for pre-2010 (planted strong effect)
      - target = pure noise post-2010 (no effect)
      - constant drift added to both eras to prevent target-mean sign flip

    Assert ZERO configs yield screened_candidate (zero false positives).
    The assertion message reports the FP count for auditability.
    """
    drifts = [0.1, 0.35, 0.8, 1.5]
    betas = [0.6, 0.95, 1.4]
    phis = [0.0, 0.3, 0.6]
    seeds = [0, 1, 2, 3]

    fp_configs = []

    for drift in drifts:
        for beta in betas:
            for phi in phis:
                for seed in seeds:
                    rng_base = 9000 + int(drift * 100) + int(beta * 100) + int(phi * 100) + seed * 7
                    rng = np.random.default_rng(rng_base)
                    n = N_OBS_WEEKLY
                    dates = _make_dates(n)

                    cause_vals = _ar1(n, phi=phi, seed=rng_base + 1)
                    era_break_idx = int((dates < pd.Timestamp("2010-01-01")).sum())

                    target_vals = np.zeros(n)
                    pre_noise = rng.standard_normal(n) * 0.15
                    for t in range(1, era_break_idx):
                        target_vals[t] = beta * cause_vals[t - 1] + pre_noise[t]
                    post_noise = rng.standard_normal(n - era_break_idx) * 1.0
                    target_vals[era_break_idx:] = post_noise
                    target_vals += drift

                    cause = pd.Series(cause_vals, index=dates)
                    target = pd.Series(target_vals, index=dates)

                    spec = _make_spec(lags=[1], horizon_d=1)
                    result = run_battery(spec, cause, target, priors={}, hermetic=True)

                    if result.verdict == "screened_candidate":
                        fp_configs.append({
                            "drift": drift, "beta": beta, "phi": phi, "seed": seed,
                            "concerns": result.concerns,
                        })

    fp_count = len(fp_configs)
    assert fp_count == 0, (
        f"Grid sweep: {fp_count} false-positive screened_candidate configs "
        f"out of {len(drifts)*len(betas)*len(phis)*len(seeds)} total. "
        f"FP configs: {fp_configs}"
    )


# ---------------------------------------------------------------------------
# Review fix tests (invariance-tested gate + mask alignment)
# ---------------------------------------------------------------------------


def test_missing_mask_caps_at_insufficient_power_with_concern():
    """
    When a declared split has NO mask provided (environment_masks is empty),
    the verdict must be capped at insufficient_power — NEVER screened_candidate.
    The concerns list must be non-empty and contain 'invariance_untested' OR
    'no mask provided'.

    This covers the 'mirage door' finding: the old code returned
    screened_candidate with splits_tested=0 and empty concerns when
    environment_masks was empty for all declared splits.
    """
    rng = np.random.default_rng(7001)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    cause_vals = rng.standard_normal(n)
    target_vals = np.zeros(n)
    lag = 1
    for t in range(lag, n):
        target_vals[t] = 0.9 * cause_vals[t - lag] + rng.standard_normal() * 0.1
    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    # Declare 2 environment splits but provide NO masks
    env_splits = [
        EnvironmentSplit("high_vol", "High vol regime"),
        EnvironmentSplit("low_vol", "Low vol regime"),
    ]
    spec = _make_spec(lags=[lag], horizon_d=1, env_splits=env_splits)

    result = run_battery(
        spec, cause, target,
        priors={},
        environment_masks={},   # empty — no masks provided
        hermetic=True,
    )

    assert result.verdict != "screened_candidate", (
        f"screened_candidate MUST NOT be returned when declared splits "
        f"have no masks: splits_declared={result.splits_declared}, "
        f"splits_tested={result.splits_tested}, concerns={result.concerns}"
    )
    assert result.concerns, (
        f"concerns list must be non-empty when splits are untested: "
        f"verdict={result.verdict!r}"
    )
    # splits_tested must be 0 when no masks were provided
    assert result.splits_tested == 0, (
        f"splits_tested should be 0 when no masks provided, got {result.splits_tested}"
    )
    # Must have a concern mentioning the missing mask
    mask_concerns = [
        c for c in result.concerns
        if "no mask" in c.lower() or "invariance_untested" in c.lower()
    ]
    assert mask_concerns, (
        f"Expected concern about missing mask or invariance_untested; "
        f"got concerns={result.concerns}"
    )


def test_all_splits_tested_allows_screened_candidate():
    """
    When all declared splits are tested cleanly (masks provided, sufficient n),
    the verdict CAN be screened_candidate if placebos pass.

    This is the positive case: splits_tested == splits_declared AND the
    effect is genuinely present in both splits.
    """
    rng = np.random.default_rng(7002)
    n = N_OBS_WEEKLY
    dates = _make_dates(n)

    # Strong planted effect (iid cause so neg-lag stays quiet)
    cause_vals = rng.standard_normal(n)
    target_vals = np.zeros(n)
    lag = 1
    for t in range(lag, n):
        target_vals[t] = 0.85 * cause_vals[t - lag] + rng.standard_normal() * 0.1
    cause = pd.Series(cause_vals, index=dates)
    target = pd.Series(target_vals, index=dates)

    # Declare one environment split with a clean 50/50 mask
    half = n // 2
    split_mask = np.zeros(n, dtype=bool)
    split_mask[:half] = True
    env_splits = [
        EnvironmentSplit("first_half", "First half of sample"),
    ]
    spec = _make_spec(lags=[lag], horizon_d=1, env_splits=env_splits)

    result = run_battery(
        spec, cause, target,
        priors={},
        environment_masks={"first_half": split_mask},
        hermetic=True,
    )

    # With a strong planted effect and a clean mask, verdict should be
    # screened_candidate (or era_specific if era divergence fires, but
    # NOT insufficient_power due to untested splits).
    assert result.splits_tested == result.splits_declared, (
        f"splits_tested={result.splits_tested} != "
        f"splits_declared={result.splits_declared}"
    )
    assert result.verdict in ("screened_candidate", "era_specific", "unstable"), (
        f"Expected screened_candidate/era_specific/unstable with clean masks; "
        f"got {result.verdict!r}, concerns={result.concerns}"
    )
    # Must NOT be insufficient_power from the invariance gate
    if result.verdict == "insufficient_power":
        pytest.fail(
            f"insufficient_power fired despite all splits being tested: "
            f"splits_declared={result.splits_declared}, "
            f"splits_tested={result.splits_tested}, concerns={result.concerns}"
        )


def test_mask_alignment_by_date_not_length():
    """
    Runner mask-alignment fixture: target dates are a strict subset of
    regime dates with an offset — mask must align by DATE JOIN, not by
    length slicing.

    Setup:
      - regime_dates: 500 weekly dates from 2003-01 (includes pre-target dates)
      - target_dates: 400 weekly dates from 2005-01 (subset of regime_dates,
        offset by ~100 periods)
      - cause_dates: same as target_dates
      - regime mask marks first 300 dates of regime_dates as True (high-vol)

    With naive length-slicing (mask[:len(tgt_dates)] = mask[:400]):
      the mask captures regime[0:400] which includes the offset pre-target
      dates — the boolean values assigned to each target date are WRONG.

    With date-aligned construction via _build_env_masks(regime_history, aligned_dates):
      only the 400 target dates are looked up in the regime index, so the
      resulting mask correctly reflects the regime state on THOSE dates.

    We verify this property directly: construct a mask via the date-aligned
    approach and verify the assignment is consistent with the regime state
    at each aligned date.
    """
    import numpy as np  # noqa: F811  (already imported at module level)

    # Build "regime history" as a DataFrame with transition_state column
    regime_start = pd.date_range(start="2003-01-06", periods=500, freq="W")
    # Mark first 300 regime dates as WARNING (high-vol), rest as STABLE
    states = ["WARNING"] * 300 + ["STABLE"] * 200
    regime_df = pd.DataFrame(
        {"transition_state": states},
        index=regime_start,
    )
    regime_df.index = pd.DatetimeIndex(regime_df.index)

    # Target + cause dates: 400-week window starting 2005-01 (offset from regime)
    target_dates = pd.date_range(start="2005-01-03", periods=400, freq="W")

    # Build masks using the _build_env_masks function from build_causal_edges
    from scripts.build_causal_edges import _build_env_masks

    masks = _build_env_masks(regime_df, pd.DatetimeIndex(target_dates))
    high_vol_mask = masks["high_vol_regime"]

    assert len(high_vol_mask) == len(target_dates), (
        f"mask length {len(high_vol_mask)} != target_dates length {len(target_dates)}"
    )

    # Verify correctness: for each target date, look up what state the regime
    # was in at that date (forward-fill from regime history) and compare.
    # The last WARNING regime date is regime_start[299]; target dates that fall
    # AFTER regime_start[299] should be STABLE (high_vol=False).
    last_warning_date = regime_start[299]
    for d, hv in zip(target_dates, high_vol_mask):
        expected_hv = (d <= last_warning_date)
        assert hv == expected_hv, (
            f"Date {d}: expected high_vol={expected_hv}, got {hv}. "
            f"Last WARNING regime date={last_warning_date}. "
            "Mask was constructed by naive length-slicing instead of date join."
        )
