"""Tests for engine/china_national_team.py — National Team Radar (display-tier).

The 7 contract tests from research/NATIONAL_TEAM_RADAR_SPEC.md §Tests:
  1. snapshot() returns the v1 schema with all contract keys; is_context_only is True.
  2. Score is in [0,100]; band matches the threshold table.
  3. On a synthetic ETF-surge fixture, etf_creation fires and score rises (fail-then-pass power).
  4. Null handling: a tell's source absent => state:"null", have_data:False, excluded from the
     renormalized composite (no crash, no NaN).
  5. Accent maps to a NON-FLIPPING token (never up/down).
  6. No user-facing string contains "validated".
  7. Ledgers append idempotently (same-day rerun does not duplicate a row).

Fixture tests redirect the engine's data root to a tmp dir and/or monkeypatch a single tell
loader, so nothing here touches the real data/ tree or the network.

Run: python -m pytest tests/test_china_national_team.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from engine import china_national_team as nt


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _all_strings(obj) -> list[str]:
    """Recursively collect every str in a nested dict/list (for the 'validated' scan)."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_all_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_all_strings(v))
    return out


def _surge_etf_frame() -> pd.DataFrame:
    """5 weeks of flat ETF units, then a sharp 2-session creation burst in CSI 300 + STAR 50."""
    idx = pd.date_range("2026-06-13", periods=30, freq="B")
    cols = ["sh_510300", "sh_588000", "sh_510050", "sh_510500", "sh_159915", "sh_512880"]
    rng = np.random.default_rng(7)
    base = {c: 2.0e10 + rng.uniform(-1e8, 1e8, len(idx)).cumsum() for c in cols}
    df = pd.DataFrame(base, index=idx)
    # Rescue: CSI 300 +12% and STAR 50 +22% on the final session (concentrated state buy).
    df.iloc[-1, df.columns.get_loc("sh_510300")] = df["sh_510300"].iloc[-2] * 1.12
    df.iloc[-1, df.columns.get_loc("sh_588000")] = df["sh_588000"].iloc[-2] * 1.22
    return df


# --------------------------------------------------------------------------- #
# Test 1 — schema + contract keys + is_context_only
# --------------------------------------------------------------------------- #
def test_schema_and_contract_keys():
    s = nt.snapshot()
    assert s["schema"] == "china_national_team.v1"
    assert s["is_context_only"] is True
    # Authority must be display-tier and non-escalating (house law).
    auth = s["authority"]
    assert auth["may_originate"] is False and auth["may_escalate"] is False

    for k in ("asof", "built", "pressure", "stance", "tells", "tell_counts",
              "top_footprint", "history", "gaps"):
        assert k in s, f"missing top-level key {k}"

    p = s["pressure"]
    for k in ("score", "band", "band_en", "band_zh", "accent", "arc_frac"):
        assert k in p, f"missing pressure key {k}"

    assert set(s["stance"].keys()) == {"en", "zh"}

    # Every tell carries the full per-tell contract with bilingual strings.
    assert len(s["tells"]) == len(nt.TELLS)
    for t in s["tells"]:
        for k in ("key", "tier", "label_en", "label_zh", "state", "strength",
                  "value_fmt", "receipt_en", "receipt_zh", "have_data", "weight"):
            assert k in t, f"tell {t.get('key')} missing key {k}"
        assert t["state"] in ("firing", "quiet", "null")
        assert t["tier"] in ("leading", "coincident", "confirming")

    tc = s["tell_counts"]
    assert tc["total"] == len(s["tells"])
    assert tc["firing"] + tc["null"] <= tc["total"]


# --------------------------------------------------------------------------- #
# Test 2 — score in [0,100] and band matches the threshold table
# --------------------------------------------------------------------------- #
def test_score_bounds_and_band_match():
    s = nt.snapshot()
    score = s["pressure"]["score"]
    assert isinstance(score, int)
    assert 0 <= score <= 100
    # Recompute the expected band from the spec threshold table.
    if score >= 68:
        expected = "on"
    elif score >= 42:
        expected = "elevated"
    elif score >= 18:
        expected = "quiet"
    else:
        expected = "dormant"
    assert s["pressure"]["band"] == expected
    assert 0.0 <= s["pressure"]["arc_frac"] <= 1.0


# --------------------------------------------------------------------------- #
# Test 3 — ETF-surge fixture fires etf_creation and lifts the score (fail-then-pass)
# --------------------------------------------------------------------------- #
def test_etf_surge_fires_and_lifts_score(monkeypatch, tmp_path):
    # Redirect all store reads to an empty tmp dir, and force the two sub-engine tells null so
    # etf_creation is the ONLY mover — isolating its contribution (fail-then-pass power).
    monkeypatch.setattr(nt, "_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(nt, "_eval_market_rescue",
                        lambda: (nt._tell("market_rescue", "null", have_data=False), None))
    monkeypatch.setattr(nt, "_eval_pboc_posture",
                        lambda: (nt._tell("pboc_posture", "null", have_data=False), None))

    # Baseline: NO etf_shares file — etf_creation reads null, EVERY tell is null => score 0.
    base = nt.snapshot()
    etf_base = next(t for t in base["tells"] if t["key"] == "etf_creation")
    assert etf_base["state"] == "null" and etf_base["have_data"] is False
    assert base["pressure"]["score"] == 0

    # Now drop the surge fixture on disk and rebuild.
    flows = tmp_path / "china_flows"
    flows.mkdir(parents=True, exist_ok=True)
    _surge_etf_frame().to_parquet(flows / "etf_shares.parquet")

    surged = nt.snapshot()
    etf = next(t for t in surged["tells"] if t["key"] == "etf_creation")
    assert etf["state"] == "firing", "the concentrated CSI300/STAR50 creation burst must fire"
    assert etf["strength"] > 0.0 and etf["have_data"] is True
    # The receipt must name the index ETFs the state bought.
    assert "CSI 300" in etf["receipt_en"] and "STAR 50" in etf["receipt_en"]
    # etf_creation going null -> firing must strictly lift the renormalized composite off 0.
    assert surged["pressure"]["score"] > base["pressure"]["score"]


# --------------------------------------------------------------------------- #
# Test 4 — null handling renormalizes; no crash, no NaN
# --------------------------------------------------------------------------- #
def test_null_handling_renormalizes(monkeypatch, tmp_path):
    # Empty data root => every store-backed tell is null. The two sub-engine tells
    # (market_rescue, pboc_posture) still read real stores; force them null too so we can
    # assert the fully-degraded path is well-formed.
    monkeypatch.setattr(nt, "_data_root", lambda: str(tmp_path))
    monkeypatch.setattr(nt, "_eval_market_rescue",
                        lambda: (nt._tell("market_rescue", "null", have_data=False),
                                 "market_rescue: forced null (test)"))
    monkeypatch.setattr(nt, "_eval_pboc_posture",
                        lambda: (nt._tell("pboc_posture", "null", have_data=False),
                                 "pboc_posture: forced null (test)"))

    s = nt.snapshot()
    # All tells null => denom 0 => score 0 (defined), band dormant, no NaN anywhere.
    assert all(t["state"] == "null" and t["have_data"] is False for t in s["tells"])
    assert s["pressure"]["score"] == 0
    assert s["pressure"]["band"] == "dormant"
    for v in _all_strings({"score": str(s["pressure"]["score"])}):
        assert "nan" not in v.lower()
    for t in s["tells"]:
        assert not (isinstance(t["strength"], float) and math.isnan(t["strength"]))

    # Partial: give the composite exactly ONE firing tell and assert renormalization ignores
    # the null weights (a single firing tell at strength 1.0 => score 100 regardless of others).
    monkeypatch.setattr(nt, "_eval_market_rescue",
                        lambda: (nt._tell("market_rescue", "firing", strength=1.0,
                                          value_fmt="market rescue", receipt_en="x", receipt_zh="x",
                                          have_data=True), None))
    s2 = nt.snapshot()
    assert s2["pressure"]["score"] == 100, "renormalized composite ignores null-weighted tells"


# --------------------------------------------------------------------------- #
# Test 5 — accent is a non-flipping token (never up/down)
# --------------------------------------------------------------------------- #
def test_accent_non_flipping_token():
    valid = {"act", "warn", "ok", "muted"}
    # The live read.
    assert nt.snapshot()["pressure"]["accent"] in valid
    # Every band in the table maps to a non-flipping token.
    for score in (5, 20, 50, 80):
        band, accent, _en, _zh = nt._band(score)
        assert accent in valid
        assert accent not in ("up", "down"), "accent must NOT use direction tokens (they flip in zh)"


# --------------------------------------------------------------------------- #
# Test 6 — no user-facing string contains "validated"
# --------------------------------------------------------------------------- #
def test_no_validated_in_strings():
    s = nt.snapshot()
    for text in _all_strings(s):
        assert "validated" not in text.lower(), f"user-facing string contains 'validated': {text!r}"
        assert "已验证" not in text, f"user-facing string contains '已验证': {text!r}"


# --------------------------------------------------------------------------- #
# Test 7 — ledgers append idempotently (same-day rerun does not duplicate)
# --------------------------------------------------------------------------- #
def test_ledgers_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(nt, "_data_root", lambda: str(tmp_path))
    monkeypatch.setenv("CN_LANE", "asia")  # forward ledgers advance only on the nightly asia lane
    # Seed a buyback source so the buyback ledger actually writes a row.
    bb = tmp_path / "china_buyback"
    bb.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "ticker": ["600000.SS", "000001.SZ", "600519.SS"],
        "progress": ["董事会预案", "完成实施", "董事会预案"],
        "plan_amt_yi": [1.5, 2.0, 3.0],
    }).to_parquet(bb / "buyback.parquet")

    asof = "2026-07-22"
    nt.snapshot(asof)
    nt.snapshot(asof)
    nt.snapshot(asof)  # three same-day runs

    bdf = pd.read_parquet(tmp_path / "china_national_team" / "buyback_daily.parquet")
    pdf = pd.read_parquet(tmp_path / "china_national_team" / "pressure_daily.parquet")
    assert len(bdf) == 1, "same-day buyback ledger row must not duplicate"
    assert len(pdf) == 1, "same-day pressure ledger row must not duplicate"
    # Content sanity: 2 board proposals seeded, plan sum = 6.5.
    assert int(bdf["n_board_proposal"].iloc[0]) == 2
    assert abs(float(bdf["plan_amt_yi_sum"].iloc[0]) - 6.5) < 1e-6

    # A DIFFERENT date appends a second row (forward accrual works).
    nt.snapshot("2026-07-23")
    pdf2 = pd.read_parquet(tmp_path / "china_national_team" / "pressure_daily.parquet")
    assert len(pdf2) == 2, "a new date must accrue a new pressure row"


# --------------------------------------------------------------------------- #
# Extra hardening — a raising evaluator recovers to an honest null tell under its
# OWN key (the buyback tell is a lambda; a name-based recovery would mislabel it).
# --------------------------------------------------------------------------- #
def test_raising_evaluator_recovers_to_own_key(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("injected")

    monkeypatch.setattr(nt, "_eval_largecap_divergence", _boom)
    monkeypatch.setattr(nt, "_eval_buyback_cascade", _boom)  # the lambda-wrapped tell

    s = nt.snapshot()
    keys = [t["key"] for t in s["tells"]]
    # No duplicates, registry order preserved, all 8 present.
    assert keys == [k for (k, *_rest) in nt.TELLS]
    for key in ("largecap_divergence", "buyback_cascade"):
        t = next(x for x in s["tells"] if x["key"] == key)
        assert t["state"] == "null" and t["have_data"] is False
        assert any(g.startswith(f"{key}: evaluator error") for g in s["gaps"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
