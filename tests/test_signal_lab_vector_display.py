"""Signal-Lab BTC Vector card: the DISPLAY hop of the promotion-stat chain.

``tests/test_btc_vector_w1.py`` pins ledger-vs-registry agreement (the trial
budget the calibrator charges == the dof_cost config.yml declares).  This file
pins the hop AFTER that one: what the Signal Lab page actually SHOWS must equal
what the calibrator computed.

That hop was unpinned and it drifted.  The card shipped "DSR 0.9945 (n=68 = 65
base + 3 override dof_cost)" while data/vector/calibration.json carried DSR
0.9661 at n=71 — the Override Registry had grown midterm_blackout to dof_cost=6
AND the headline DSR had moved onto the block-bootstrap T_eff basis.  Both moves
make the haircut HARSHER, so the published figure was optimistic against the
engine's own output: exactly the direction a promotion stat must never drift.

Run: python -m pytest tests/test_signal_lab_vector_display.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import signal_lab  # noqa: E402

CAL_PATH = Path("data/vector/calibration.json")
TRIAL_PATH = Path("data/vector/trial_log.json")


def _row() -> dict:
    r = next((r for r in signal_lab.REGISTRY
              if r["name"] == signal_lab._BTC_VECTOR_ROW_NAME), None)
    assert r is not None, "BTC Vector row missing from the Signal Lab registry"
    return r


def _live_figures():
    if not (CAL_PATH.exists() and TRIAL_PATH.exists()):
        pytest.skip("data/vector artifacts absent — run calibrate_vector first")
    fig = signal_lab._btc_vector_figures(
        json.loads(CAL_PATH.read_text(encoding="utf-8")),
        json.loads(TRIAL_PATH.read_text(encoding="utf-8")),
    )
    if fig is None:
        pytest.skip("data/vector artifacts incomplete — card renders its frozen quote")
    return fig


# ---------------------------------------------------------------------------
# 1. The card is DERIVED, not typed
# ---------------------------------------------------------------------------
def test_card_stats_match_the_calibrator_artifacts():
    """Rendered DSR / Sharpe / n must equal the calibrator's raw-track output."""
    fig = _live_figures()
    scorecard = signal_lab.build_scorecard()
    row = next(r for t in scorecard["tiers"] for r in t["rows"]
               if r["name"] == signal_lab._BTC_VECTOR_ROW_NAME)
    assert row["dsr"] == pytest.approx(fig["dsr_raw"]), (
        f"card DSR {row['dsr']} != calibration.json raw DSR {fig['dsr_raw']}"
    )
    assert row["sharpe"] == pytest.approx(fig["sharpe_raw"])
    assert row["n"] == fig["n_obs"]


def test_card_prose_quotes_the_declared_trial_budget():
    """The n= budget in BOTH language strings must be the ledger's declared budget.

    This is the assertion the shipped card failed: it read "n=68 = 65 base + 3
    override dof_cost" against a registry declaring 71 = 65 + 6.
    """
    fig = _live_figures()
    copy = signal_lab._btc_vector_copy(fig)
    budget = (f"n={fig['n_trials_declared']} = {fig['n_trials_config']} base "
              f"+ {fig['override_dof']} override dof_cost")
    assert budget in copy["why"], f"EN prose does not quote the declared budget ({budget})"
    zh_budget = (f"n={fig['n_trials_declared']}={fig['n_trials_config']}基础"
                 f"+{fig['override_dof']}覆盖自由度")
    assert zh_budget in copy["why_zh"], f"ZH prose does not quote the declared budget ({zh_budget})"


def test_no_stale_figure_survives_in_the_copy():
    """The retired figures must never reappear as CURRENT numbers.

    They are allowed only inside the PROVENANCE clause that explicitly retires
    them, so assert they are absent from every other sentence.
    """
    copy = signal_lab._btc_vector_copy(_live_figures())
    retired = ("0.9945", "0.9986", "0.9236", "0.9622", "n=68")
    for text_key in ("why", "why_zh"):
        text = copy[text_key]
        for token in retired:
            for sentence in text.replace("。", ".").split("."):
                if token in sentence:
                    assert ("retired" in sentence.lower() or "退役" in sentence), (
                        f"{text_key}: retired figure {token!r} appears outside a "
                        f"retirement clause: {sentence.strip()[:160]}"
                    )


# ---------------------------------------------------------------------------
# 2. EN/ZH cannot drift apart on a number
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key,fmt", [
    ("dsr_raw", "{:.4f}"), ("dsr_gated", "{:.4f}"),
    ("eff_n_raw", "{:.4f}"), ("eff_n_gated", "{:.4f}"),
    ("sharpe_raw", "{:.2f}"), ("sharpe_gated", "{:.2f}"),
])
def test_both_languages_carry_the_same_figure(key, fmt):
    fig = _live_figures()
    copy = signal_lab._btc_vector_copy(fig)
    token = fmt.format(fig[key])
    assert token in copy["why"], f"EN prose missing {key}={token}"
    assert token in copy["why_zh"], f"ZH prose missing {key}={token}"


# ---------------------------------------------------------------------------
# 3. Promotion authority — the tier must match the multiple-testing verdict
# ---------------------------------------------------------------------------
def test_scored_tier_requires_both_tracks_to_survive():
    """`scored` is a PROMOTION claim: the gauntlet grants it only at DSR>=0.95.

    If either track drops below the SURVIVES bar this test fails LOUDLY — a
    re-tiering is an adjudication, never a copy refresh.  build_scorecard also
    emits a build warning for the same condition.
    """
    fig = _live_figures()
    assert _row()["tier"] == "scored", "row re-tiered — update this gate deliberately"
    for label in ("dsr_raw", "dsr_gated"):
        assert fig[label] >= 0.95, (
            f"{label}={fig[label]:.4f} < 0.95: the BTC Vector row is still tiered "
            "`scored` but no longer SURVIVES its multiple-testing haircut — this "
            "needs adjudication (promotion authority), not a copy edit"
        )


def test_frozen_fallback_agrees_with_the_live_artifact():
    """The frozen quote must be a faithful stamp of the artifact, not a stale one.

    It is what a data-less build renders, so it may lag the live data span only
    on the figures the span moves — never on the DECLARED trial budget, which is
    a config/registry fact available without the data store.
    """
    fig = _live_figures()
    frozen = signal_lab._BTC_VECTOR_FROZEN
    for key in ("n_trials_declared", "n_trials_config", "override_dof"):
        assert frozen[key] == fig[key], (
            f"frozen fallback {key}={frozen[key]} != live {fig[key]} — re-stamp "
            "_BTC_VECTOR_FROZEN from data/vector/*.json"
        )


# ---------------------------------------------------------------------------
# 4. Degrade-safe: a missing artifact must not fabricate numbers
# ---------------------------------------------------------------------------
def test_missing_artifact_falls_back_to_the_frozen_quote(tmp_path, monkeypatch):
    """No artifact -> frozen quote + a build warning, never a crash or a blank."""
    monkeypatch.setattr(signal_lab.config, "data_dir", lambda: tmp_path)
    registry = [dict(_row())]
    warnings: list[str] = []
    signal_lab._resolve_vector_live_stats(registry, warnings)
    frozen = signal_lab._btc_vector_copy(signal_lab._BTC_VECTOR_FROZEN)
    assert registry[0]["why"] == frozen["why"]
    assert any("frozen quote" in w for w in warnings), (
        f"no build warning for the absent artifact: {warnings}"
    )


def test_eth_cross_reference_tracks_the_btc_figure():
    """The ETH port's "vs BTC DSR (raw)" chip is a cross-reference, not a quote.

    It was quoting the retired 0.9945 too — a second copy of the same stale
    number, in a different row.
    """
    fig = _live_figures()
    scorecard = signal_lab.build_scorecard()
    eth = next((r for t in scorecard["tiers"] for r in t["rows"]
                if r["name"] == signal_lab._ETH_VECTOR_ROW_NAME), None)
    if eth is None:
        pytest.skip("ETH Vector row not in the registry")
    chip = dict(eth["extra"]).get(signal_lab._ETH_VS_BTC_CHIP)
    assert chip is not None, f"{signal_lab._ETH_VS_BTC_CHIP!r} chip missing from the ETH row"
    assert f"{fig['dsr_raw']:.4f}" in chip, (
        f"ETH chip {chip!r} does not cite the live BTC raw DSR {fig['dsr_raw']:.4f}"
    )


def test_frozen_fallback_announces_its_own_staleness(tmp_path, monkeypatch):
    """Past its expiry the fallback must read EXPIRED, not merely "frozen".

    A frozen number that does not announce its own staleness is exactly how this
    card drifted: it kept publishing 0.9945 long after the engine moved on. The
    n_trials passport already escalates an expired quote (_resolve_dsr_provenance);
    the figures fallback must too, or the two halves of the same card disagree
    about whether their numbers can still be trusted.
    """
    monkeypatch.setattr(signal_lab.config, "data_dir", lambda: tmp_path)
    frozen = dict(signal_lab._BTC_VECTOR_FROZEN)
    assert frozen.get("expiry"), "_BTC_VECTOR_FROZEN carries no expiry to check"

    # before the expiry: plain frozen quote, no false alarm
    monkeypatch.setitem(signal_lab._BTC_VECTOR_FROZEN, "expiry", "2999-01-01")
    fresh: list[str] = []
    signal_lab._resolve_vector_live_stats([dict(_row())], fresh)
    assert fresh and "frozen quote" in fresh[0]
    assert "EXPIRED" not in fresh[0], f"not yet expired but warned as such: {fresh[0]}"

    # past the expiry: escalated, and it names the remedy
    monkeypatch.setitem(signal_lab._BTC_VECTOR_FROZEN, "expiry", "2000-01-01")
    stale: list[str] = []
    signal_lab._resolve_vector_live_stats([dict(_row())], stale)
    assert stale and "EXPIRED" in stale[0], f"expired quote not escalated: {stale}"
    assert "REFRESH IT" in stale[0], f"escalation does not name the remedy: {stale[0]}"


def test_partial_artifact_is_rejected():
    """A calibration.json missing the raw track must not render a half-live card."""
    trial = {"n_trials_declared": 71, "n_trials_config": 65,
             "overrides_dof": {"midterm_blackout": 6}}
    assert signal_lab._btc_vector_figures({"allocation": {"optimal": {}}}, trial) is None
    assert signal_lab._btc_vector_figures(None, trial) is None
    assert signal_lab._btc_vector_figures({}, None) is None
