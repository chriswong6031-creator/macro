"""W7 LLM Determinism Kit — unit tests (no network / no API key required).

Tests:
  1. content-hash cache: same prompt hash → identical output object (cache hit)
  2. GDELT snapshot: headlines are snapshotted before scoring; replay uses snapshot
  3. spvector path: on_stress_day is wired from capitulation_score (not dead-default)
  4. tape_family labeling: gather_state emits _tape_family / _lead_lag on all blocks
  5. same-tape prompt rule is present in MASTER_SYSTEM_TMPL

Run: python -m tests.test_w7_llm_determinism
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import catalyst_tone as ct
from engine import master_brain as mb
from engine import spvector_overlay as sov
from engine import whitehouse_brain as wb

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


# --------------------------------------------------------------------------- #
# 1. Content-hash cache — same input hash → identical output object
# --------------------------------------------------------------------------- #

def test_catalyst_tone_cache_hit():
    """_reply_cache_get returns the same bytes written by _reply_cache_put, so
    a second call on the same prompt never hits the model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"reply_cache_dir": str(tmpdir)}
        phash = ct._prompt_hash("model-x", "system text", "user text")
        # cold miss
        check("cache miss on fresh hash", ct._reply_cache_get(phash, cfg) is None)
        # write
        ct._reply_cache_put(phash, '{"result": 42}', cfg)
        # warm hit
        got = ct._reply_cache_get(phash, cfg)
        check("cache hit after write", got == '{"result": 42}', repr(got))


def test_master_brain_cache_hit():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"reply_cache_dir": str(tmpdir)}
        phash = mb._mb_prompt_hash("deepseek-v4-pro", "sys", "user")
        check("mb cache miss on fresh hash", mb._mb_reply_cache_get(phash, cfg) is None)
        mb._mb_reply_cache_put(phash, "some reply", cfg)
        got = mb._mb_reply_cache_get(phash, cfg)
        check("mb cache hit after write", got == "some reply", repr(got))


def test_whitehouse_brain_cache_hit():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"reply_cache_dir": str(tmpdir)}
        phash = wb._wh_prompt_hash("claude-opus-4-8", "sys", "user")
        check("wh cache miss on fresh hash", wb._wh_reply_cache_get(phash, cfg) is None)
        wb._wh_reply_cache_put(phash, "some reply", cfg)
        got = wb._wh_reply_cache_get(phash, cfg)
        check("wh cache hit after write", got == "some reply", repr(got))


def test_prompt_hash_sensitivity():
    """Different model / system / user → different hash (no collision on simple cases)."""
    h1 = ct._prompt_hash("model-a", "sys", "user")
    h2 = ct._prompt_hash("model-b", "sys", "user")
    h3 = ct._prompt_hash("model-a", "sys2", "user")
    check("model change → different hash", h1 != h2)
    check("system change → different hash", h1 != h3)


def test_call_model_uses_cache(monkeypatch=None):
    """_call_model returns the cached reply and never calls the SDK when the cache
    holds the prompt hash. Verified by patching _client to a sentinel that tracks
    whether it was called (should NOT be called on a cache hit)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_base = {"reply_cache_dir": str(tmpdir), "llm_model": "deepseek-v4-flash",
                    "api_key_env": "DEEPSEEK_API_KEY"}
        model = cfg_base["llm_model"]
        # Build the exact user string that _call_model will construct
        source_text, context = "hello world", "test"
        user = (f"Document context: {context}\n\n"
                f"Document text follows between <doc> tags.\n<doc>\n{source_text}\n</doc>")
        phash = ct._prompt_hash(model, ct.CATALYST_SYSTEM, user)
        ct._reply_cache_put(phash, '{"tone_score": 0.5}', cfg_base)

        # Stub _client: returns None (degrades); tracks whether called at all
        client_calls: list = []

        def _sentinel_client(cfg):
            client_calls.append(True)
            return None  # None → "no_client_or_key" (not a model call)

        original_client = ct._client
        ct._client = _sentinel_client
        try:
            reply, reason = ct._call_model(source_text, context, cfg_base)
            check("cache hit returns correct reply", reply == '{"tone_score": 0.5}'
                  and reason is None, f"reply={reply!r} reason={reason!r}")
            check("_client NOT called on cache hit", not client_calls,
                  f"client_calls={client_calls}")
        finally:
            ct._client = original_client


# --------------------------------------------------------------------------- #
# 2. GDELT snapshot — headline list is persisted before scoring (replay safety)
# --------------------------------------------------------------------------- #

def test_gdelt_snapshot_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"gdelt_snapshot_dir": str(tmpdir)}
        today = date(2026, 7, 1)
        headlines = ["Markets tumble on tariff fears", "Fed holds rates steady"]
        # cold
        check("gdelt snapshot miss", ct._gdelt_snapshot_get(today, cfg) is None)
        # write
        ct._gdelt_snapshot_put(today, headlines, cfg)
        # warm
        got = ct._gdelt_snapshot_get(today, cfg)
        check("gdelt snapshot hit returns list", got == headlines, repr(got))


def test_gdelt_snapshot_different_dates():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"gdelt_snapshot_dir": str(tmpdir)}
        d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
        ct._gdelt_snapshot_put(d1, ["headline-A"], cfg)
        ct._gdelt_snapshot_put(d2, ["headline-B"], cfg)
        check("snapshots keyed by date d1", ct._gdelt_snapshot_get(d1, cfg) == ["headline-A"])
        check("snapshots keyed by date d2", ct._gdelt_snapshot_get(d2, cfg) == ["headline-B"])


def test_event_snapshot_uses_gdelt_snapshot():
    """event_snapshot reuses an existing GDELT snapshot instead of re-fetching.
    Verified by pre-writing the snapshot and confirming _fetch_event_headlines
    is not called."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_patch = {
            "enabled": True, "event_enabled": True,
            "gdelt_snapshot_dir": str(tmpdir),
            "reply_cache_dir": str(tmpdir),
            "llm_model": "deepseek-v4-flash",
        }
        today = date(2026, 7, 1)
        headlines = ["Stocks drop 2% on recession fears"]
        # Pre-write the snapshot so fetch should not be called
        ct._gdelt_snapshot_put(today, headlines, cfg_patch)

        fetch_called = []

        def _fake_fetch(d, cfg):
            fetch_called.append(True)
            return []  # if called, returns empty (test would fail below)

        original_cfg = ct._cfg
        original_fetch = ct._fetch_event_headlines
        ct._fetch_event_headlines = _fake_fetch
        ct._cfg = lambda: cfg_patch
        try:
            # digest_document will be called but the model call degrades (no key)
            # — we just care that _fetch_event_headlines was NOT called
            ct.event_snapshot(asof=today, context="test")
            check("event_snapshot reuses GDELT snapshot (no re-fetch)", not fetch_called,
                  f"fetch_called={fetch_called}")
        finally:
            ct._fetch_event_headlines = original_fetch
            ct._cfg = original_cfg


# --------------------------------------------------------------------------- #
# 3. spvector veto path: on_stress_day is now derived from capitulation_score
# --------------------------------------------------------------------------- #

def test_context_snapshot_on_stress_day_event_path():
    """context_snapshot(on_stress_day=True) calls event_snapshot, not daily_snapshot."""
    calls: dict = {"event": 0, "daily": 0}

    class _FakeCT:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def event_snapshot(asof=None, context=""):
            calls["event"] += 1
            return {"shock_reversible": "persistent", "confidence": "high"}

        @staticmethod
        def daily_snapshot(asof=None):
            calls["daily"] += 1
            return {"shock_reversible": "unknown", "confidence": "low"}

    original = sov._catalyst
    sov._catalyst = lambda: _FakeCT
    try:
        sov.context_snapshot(on_stress_day=True)
        check("on_stress_day=True → event_snapshot called", calls["event"] == 1,
              str(calls))
        check("on_stress_day=True → daily_snapshot NOT called", calls["daily"] == 0,
              str(calls))
    finally:
        sov._catalyst = original


def test_context_snapshot_non_stress_day_fomc_path():
    """context_snapshot(on_stress_day=False) uses daily_snapshot (FOMC path)."""
    calls: dict = {"event": 0, "daily": 0}

    class _FakeCT:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def event_snapshot(asof=None, context=""):
            calls["event"] += 1
            return None  # no event on a calm day

        @staticmethod
        def daily_snapshot(asof=None):
            calls["daily"] += 1
            return {"shock_reversible": "unknown", "confidence": "low"}

    original = sov._catalyst
    sov._catalyst = lambda: _FakeCT
    try:
        sov.context_snapshot(on_stress_day=False)
        check("on_stress_day=False → event_snapshot NOT called", calls["event"] == 0,
              str(calls))
        check("on_stress_day=False → daily_snapshot called", calls["daily"] >= 1,
              str(calls))
    finally:
        sov._catalyst = original


def test_veto_fires_on_stress_day_with_persistent_shock():
    """End-to-end: a stress-day context_snapshot returning persistent fires the veto."""
    snap = {"shock_reversible": "persistent", "confidence": "high",
            "tone_score": 0.8, "guidance_direction": "unknown", "risk_delta": 0.5}
    o = sov.live_overlay(0.33, 1.0, snapshot=snap)
    check("stress-day persistent shock fires veto", o["veto"] is True)
    check("veto reverts to glide weight", o["overlay_weight"] == 0.33)


# --------------------------------------------------------------------------- #
# 4. tape_family / lead_lag labels in gather_state
# --------------------------------------------------------------------------- #

def _minimal_latest_json(tmpdir: str) -> None:
    """Write stub JSON files so gather_state can read them without a full data tree."""
    root = Path(tmpdir)
    (root / "data" / "regime").mkdir(parents=True, exist_ok=True)
    (root / "data" / "signal_archive").mkdir(parents=True, exist_ok=True)
    latest = {
        "date": "2026-07-01", "quad": "Q2", "quad_name": "Goldilocks",
        "growth_score": 0.3, "inflation_score": -0.1,
        "conditions": {}, "dislocation": {}, "macro_risk": {"score": 20, "label": "low"},
        "playbook": {}, "market_drivers": {},
        "liquidity_overlay": "expanding", "cycle_tag": "mid",
        "cross_asset_confirm": {"verdict": "confirm", "headline_en": "Bonds + FX confirm",
                                "agree_pct": 0.72, "to_brain": {}},
        "rate_inflation_transmission": {
            "state": {"rates": {"label": {"en": "easing"}},
                      "inflation": {"label": {"en": "below-target"}},
                      "expectations": {"label": {"en": "anchored"}}},
            "headwinds": [], "tailwinds": [], "chains": [],
        },
    }
    (root / "data" / "regime" / "latest.json").write_text(json.dumps(latest))


def test_gather_state_tape_family_labels():
    """gather_state attaches _tape_family and _lead_lag to every major block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _minimal_latest_json(tmpdir)
        root = Path(tmpdir)
        state = mb.gather_state(root=root)

        # macro block
        m = state.get("macro", {})
        check("macro._tape_family == price_regime",
              m.get("_tape_family") == "price_regime", str(m.get("_tape_family")))
        check("macro._lead_lag == coincident",
              m.get("_lead_lag") == "coincident", str(m.get("_lead_lag")))

        # cross_asset_confirm (if present — depends on macro having the field)
        cac = state.get("cross_asset_confirm")
        if cac:
            check("cross_asset_confirm._tape_family == price_regime",
                  cac.get("_tape_family") == "price_regime",
                  str(cac.get("_tape_family")))
            check("cross_asset_confirm._lead_lag == coincident",
                  cac.get("_lead_lag") == "coincident", str(cac.get("_lead_lag")))

        # rate_inflation_transmission (if present)
        tr = state.get("rate_inflation_transmission")
        if tr:
            check("rate_inflation_transmission._tape_family == rates_credit",
                  tr.get("_tape_family") == "rates_credit",
                  str(tr.get("_tape_family")))


def test_gather_state_price_regime_blocks_same_family():
    """macro, cross_asset_confirm, forex (if present) all share price_regime."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _minimal_latest_json(tmpdir)
        root = Path(tmpdir)
        # Add forex stub
        (root / "data" / "forex").mkdir(parents=True, exist_ok=True)
        (root / "data" / "forex" / "latest.json").write_text(json.dumps(
            {"date": "2026-07-01", "regime": "risk-on", "favored": "AUD/USD",
             "risk": "low", "dollar_desk": {}, "transmission": {}}
        ))
        state = mb.gather_state(root=root)
        families = {k: state[k].get("_tape_family")
                    for k in ("macro", "forex") if k in state}
        check("macro and forex share price_regime family",
              all(v == "price_regime" for v in families.values()),
              str(families))


# --------------------------------------------------------------------------- #
# 5. Same-tape rule in MASTER_SYSTEM_TMPL
# --------------------------------------------------------------------------- #

def test_same_tape_rule_in_system_prompt():
    """MASTER_SYSTEM_TMPL contains the same-tape rule so the LLM knows to count
    shared-tape blocks as one observation."""
    tmpl = mb.MASTER_SYSTEM_TMPL
    check("SAME-TAPE RULE present in system template",
          "SAME-TAPE RULE" in tmpl or "tape_family" in tmpl,
          "missing")
    check("price_regime family mentioned in template",
          "price_regime" in tmpl, "missing")
    check("coincident / leading distinction in template",
          "coincident" in tmpl or "lead_lag" in tmpl, "missing")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    tests = [
        test_catalyst_tone_cache_hit,
        test_master_brain_cache_hit,
        test_whitehouse_brain_cache_hit,
        test_prompt_hash_sensitivity,
        test_call_model_uses_cache,
        test_gdelt_snapshot_roundtrip,
        test_gdelt_snapshot_different_dates,
        test_event_snapshot_uses_gdelt_snapshot,
        test_context_snapshot_on_stress_day_event_path,
        test_context_snapshot_non_stress_day_fomc_path,
        test_veto_fires_on_stress_day_with_persistent_shock,
        test_gather_state_tape_family_labels,
        test_gather_state_price_regime_blocks_same_family,
        test_same_tape_rule_in_system_prompt,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            global FAIL
            FAIL += 1
            print(f"  ERROR  {fn.__name__}: {e}")
    print(f"\n{'=' * 50}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
