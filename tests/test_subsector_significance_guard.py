"""The subsector-rotation significance claim must be earned — 2026-08-03 experiments audit.

WHAT SHIPPED. site/marketdata/subsector_rotation.json carried verdict="validated" and the
front-facing sentence "Emerging-score IC is significant at the 21d horizon (measured)" off
TEN IC-days spanning TWELVE calendar days — about 0.4 non-overlapping 21-day windows, i.e.
one market episode graded ten times. Two separate things let it through:

  * `_MIN_PROVEN_N = 40` counts matured cross-sectional ROWS while gating a TIME-SERIES
    statistic. One date of 268 subsectors clears it outright, buying no independent evidence.
  * the HAC t was ANTICONSERVATIVE — t_hac exceeded the plain iid t at all three horizons
    (1.392>1.208 @5d, 4.638>3.600 @10d, 4.850>3.179 @21d) because the Bartlett long-run
    variance landed below gamma0/n on a short positively-overlapping series. A "correction"
    that raises t is not a correction.

WHAT GUARDS IT. An independent-window floor on the promotion gate, an iid cap on the t the
gate may read, and `note_violation` — which audits a STORED payload against its own numbers
so the sentence cannot reach site/ without something failing. BC-2
(scripts/check_validated_claims.py) structurally cannot see this claim: it never uses the
word "validated", and it reaches the page through a runtime fetch of a 758 KB single-line
JSON that no SCAN_GLOB covers.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from engine import subsector_track_record as S


# --------------------------------------------------------------------------- #
# fixtures: a snapshot ledger whose IC-days span a chosen number of calendar days
# --------------------------------------------------------------------------- #
def _fake_prices(monkeypatch):
    """Members named W* rise 10%, L* fall 10%, SPY flat — so a subsector's forward return
    is decided by its member prefix and the cross-sectional IC is essentially perfect."""
    exit_px = {"W": 110.0, "L": 90.0, "SPY": 100.0}
    monkeypatch.setattr(S, "_covers", lambda t, root, end: True)
    monkeypatch.setattr(S, "_level_asof", lambda t, root, start: 100.0)
    monkeypatch.setattr(S, "_close_at",
                        lambda t, root, end: exit_px.get(t[0] if t != "SPY" else "SPY", 100.0))


def _ledger(tmp_path, *, n_ic_days: int, day_step: int, today: date, horizon_gap: int = 90):
    """Write `n_ic_days` daily cross-sections `day_step` calendar days apart.

    Each date carries 12 subsectors (>= the 10 the IC needs) whose emerging_score ranks
    perfectly with the realized forward return, so every horizon gets a strong positive IC
    and the ONLY thing separating a promotable ledger from an unpromotable one is how much
    calendar the IC-days span.
    """
    rows = []
    first = today - timedelta(days=horizon_gap + (n_ic_days - 1) * day_step)
    for i in range(n_ic_days):
        d = (first + timedelta(days=i * day_step)).isoformat()
        for j in range(12):
            winner = j < 6
            rows.append({
                "date": d, "key": f"s{j}", "name": f"S{j}", "theme": "T",
                # winners score high, losers low → rank IC ≈ +1 every date
                "score": 10.0 - j, "lean": 1 if winner else -1,
                "stage": "emerging" if winner else "fading",
                "members": [f"{'W' if winner else 'L'}{j}{k}" for k in range(3)],
            })
    p = tmp_path / "data/subsector_rotation/snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return rows


_TODAY = date(2026, 8, 2)
_SIG_EN = "significant"
_SIG_ZH = "显著"


# --------------------------------------------------------------------------- #
# 1. the shape that actually shipped must resolve to "measuring"
# --------------------------------------------------------------------------- #
def test_ten_back_to_back_ic_days_cannot_claim_significance(tmp_path, monkeypatch):
    """The 2026-08-03 artifact shape, reproduced: 10 daily IC-days back to back.

    Every OTHER gate condition is satisfied on purpose — thousands of matured rows, a large
    positive IC, a t far above 2 — so this test fails for exactly one reason if the floor is
    removed: the span buys under one independent 21-day window.
    """
    _fake_prices(monkeypatch)
    _ledger(tmp_path, n_ic_days=10, day_step=1, today=_TODAY)
    tr = S.compute(today=_TODAY.isoformat(), root=tmp_path)

    h21 = tr["horizons"]["21"]
    assert h21["n_matured"] >= S._MIN_PROVEN_N, "fixture must clear the ROW floor to be a real test"
    assert h21["score_ic"] > 0 and h21["score_ic_t_hac"] >= 2.0, (
        "fixture must clear the t bar to be a real test — "
        f"ic={h21['score_ic']}, t_hac={h21['score_ic_t_hac']}")
    assert h21["indep_windows"] < S._MIN_INDEP_WINDOWS

    assert tr["verdict"] == "measuring", (
        f"ten readings of one stretch of market is one episode, not evidence. "
        f"indep_windows={h21['indep_windows']} < {S._MIN_INDEP_WINDOWS}")
    assert not any(tr["proven"].values())
    assert tr["lead_time_d"] is None
    # "significance" (the negated measuring copy) is not "significant" (the claim)
    assert _SIG_EN not in tr["note"] and _SIG_ZH not in tr["note_zh"].replace("显著性检验", "")
    assert tr["note"] == S._NOTES["measuring"][0]
    assert tr["note_zh"] == S._NOTES["measuring"][1]
    assert S.note_violation(tr) is None


def test_row_floor_alone_is_satisfied_by_a_single_date(tmp_path, monkeypatch):
    """Why the row count was never the guard: ONE cross-section clears _MIN_PROVEN_N."""
    _fake_prices(monkeypatch)
    _ledger(tmp_path, n_ic_days=1, day_step=1, today=_TODAY)
    tr = S.compute(today=_TODAY.isoformat(), root=tmp_path)
    # a single date of 12 subsectors is only 12 rows here; the shipped ledger had 268 per
    # date, so one date cleared a 40-row floor outright. Either way it is one window.
    assert tr["horizons"]["21"]["indep_windows"] == 0.0
    assert tr["verdict"] == "measuring"


# --------------------------------------------------------------------------- #
# 2. positive control — the gate is a floor, not a wall
# --------------------------------------------------------------------------- #
def test_a_span_covering_six_windows_can_still_promote(tmp_path, monkeypatch):
    """Same signal quality, spread over enough calendar to be six separate 21-day episodes.
    Without this the floor could be satisfied by refusing every promotion forever."""
    _fake_prices(monkeypatch)
    # 12 IC-days, 21 calendar days apart → span 231d vs a 29.4d window ≈ 7.9 windows
    _ledger(tmp_path, n_ic_days=12, day_step=21, today=_TODAY)
    tr = S.compute(today=_TODAY.isoformat(), root=tmp_path)

    h21 = tr["horizons"]["21"]
    assert h21["indep_windows"] >= S._MIN_INDEP_WINDOWS
    assert tr["verdict"] == "validated", (
        f"an honestly-spanned ledger must still be promotable — "
        f"indep={h21['indep_windows']}, t_gate={h21['score_ic_t_gate']}, ic={h21['score_ic']}")
    assert tr["proven"]["21"] is True
    assert tr["lead_time_d"] in (5, 10, 21, 63)
    assert _SIG_EN in tr["note"] and _SIG_ZH in tr["note_zh"]
    assert S.note_violation(tr) is None


# --------------------------------------------------------------------------- #
# 3. the anticonservative-HAC cap
# --------------------------------------------------------------------------- #
def test_gate_t_falls_back_to_iid_when_hac_is_anticonservative(capsys):
    """t_hac > |t_iid| on an overlapping series means the Bartlett LRV came out BELOW
    gamma0/n — the corrected t is inflated, not corrected. The gate reads the iid t."""
    ic = {"mean_ic": 0.3341, "ic_vol": 0.3324, "n": 10, "t_hac": 4.85,
          "hac_lags": 9, "hac_lags_requested": 21}
    t_gate, anticon = S._gate_t(ic, 21)
    assert anticon is True
    assert t_gate == pytest.approx(S._iid_t(ic), rel=1e-9)
    assert t_gate == pytest.approx(3.178, abs=0.01)   # the audit's measured iid t
    assert t_gate < ic["t_hac"], "the substitution must only ever LOWER the gate input"

    out = capsys.readouterr().out
    line = next((ln for ln in out.splitlines() if "hac anticonservative" in ln), "")
    assert line, f"a promotion-grade anticonservative t must be announced; got {out!r}"
    # GitHub drops an annotation that does not START the line (CLAUDE.md house law)
    assert line.startswith("::warning title=subsector_track_record::")
    assert "effective lag 9 of 21 requested" in line


def test_no_annotation_when_the_inflated_t_could_not_promote_anyway(capsys):
    """5d in the audit: t_hac 1.392 > t_iid 1.208 but nowhere near the 2.0 bar. Still capped,
    deliberately not announced — an alarm that fires on every horizon every night is noise."""
    ic = {"mean_ic": 0.1044, "ic_vol": 0.3862, "n": 20, "t_hac": 1.392,
          "hac_lags": 5, "hac_lags_requested": 5}
    t_gate, anticon = S._gate_t(ic, 5)
    assert anticon is True and t_gate == pytest.approx(1.209, abs=0.01)
    assert "hac anticonservative" not in capsys.readouterr().out


def test_a_genuinely_corrected_hac_is_left_alone():
    """The normal case: HAC widens the se and lowers t. Nothing is substituted."""
    ic = {"mean_ic": 0.05, "ic_vol": 0.10, "n": 25, "t_hac": 1.10}
    t_gate, anticon = S._gate_t(ic, 21)
    assert anticon is False and t_gate == 1.10
    assert S._iid_t(ic) > 1.10          # iid t is 2.5 — the HAC really did correct downward


# --------------------------------------------------------------------------- #
# 4. the publish guard — what the builder runs before the note reaches site/
# --------------------------------------------------------------------------- #
def _shipped_shape() -> dict:
    """The 2026-08-03 artifact's track_record block, reduced to the fields the guard reads.
    Numbers are the ones that actually shipped."""
    return {
        "verdict": "validated",
        "lead_time_d": 21,
        "peak_score_ic": 0.3341,
        "note": S._NOTES["validated"][0].format(h=21),
        "note_zh": S._NOTES["validated"][1].format(h=21),
        "horizons": {
            "5":  {"n_matured": 4835, "score_ic": 0.1044, "score_ic_t_gate": 1.209,
                   "indep_windows": 4.0},
            "10": {"n_matured": 4106, "score_ic": 0.253, "score_ic_t_gate": 3.6,
                   "indep_windows": 1.64},
            "21": {"n_matured": 2405, "score_ic": 0.3341, "score_ic_t_gate": 3.178,
                   "indep_windows": 0.41},
            "63": {"n_matured": 0, "score_ic": None, "score_ic_t_gate": None,
                   "indep_windows": 0.0},
        },
    }


def test_guard_fails_on_the_artifact_that_shipped():
    """PRE-FIX CONTENT: the exact payload live on sector_central.html on 2026-08-03."""
    viol = S.note_violation(_shipped_shape())
    assert viol is not None, "the guard must fail on the content it exists to catch"
    assert "verdict='validated'" in viol and "'measuring'" in viol
    assert "indep_windows=0.41" in viol


def test_guard_passes_on_the_withdrawn_note():
    """POST-FIX CONTENT: same numbers, honest verdict."""
    p = _shipped_shape()
    viol = S.withdraw_unbacked_note(p)
    assert viol is not None                       # something WAS withdrawn
    assert p["verdict"] == "measuring"
    assert p["lead_time_d"] is None
    assert _SIG_EN not in p["note"].replace("no horizon clears the Newey-West significance", "")
    assert p["note"] == S._NOTES["measuring"][0] and p["note_zh"] == S._NOTES["measuring"][1]
    assert S.note_violation(p) is None            # ...and the result is clean


def test_guard_catches_a_hand_edited_note_under_an_honest_verdict():
    """The other half: pasting the significance sentence onto a 'measuring' payload. The
    verdict check alone would pass this — the copy check is what closes it."""
    p = _shipped_shape()
    S.withdraw_unbacked_note(p)
    p["note"] = S._NOTES["validated"][0].format(h=21)
    viol = S.note_violation(p)
    assert viol is not None and "note copy does not match" in viol


def test_guard_is_silent_on_a_degrade_safe_error_payload():
    """compute()'s except-branch claims nothing; it must not read as a violation."""
    p = {"verdict": "accruing", "horizons": {}, "compute_error": "boom",
         "note": "compute error (boom) — accruing, degrade-safe.", "note_zh": "x"}
    assert S.note_violation(p) is None


# --------------------------------------------------------------------------- #
# 5. the effective-lag disclosure this rests on
# --------------------------------------------------------------------------- #
def test_ic_summary_publishes_the_effective_lag_not_the_request():
    """A 21-lag request on a 10-point series applies 9. Publishing 21 is how an
    under-corrected t reads as fully corrected (engine/validation.py:739 pre-fix)."""
    from engine import validation as V
    ics = [0.30, 0.35, 0.28, 0.40, 0.31, 0.36, 0.33, 0.29, 0.38, 0.34]
    out = V.ic_summary(ics, periods_per_year=42)      # default lag = 42 // 2 = 21
    assert out["n"] == 10
    assert out["hac_lags_requested"] == 21
    assert out["hac_lags"] == 9, "the Bartlett kernel cannot weight lags the sample lacks"
