"""Contract tests for scripts/build_am_edition.py (packet A-MO-W2-3).

All tests drive build_payload() against tmp_path fixture trees with a frozen
`now` — none touch the network, none require the real data/ or site/ trees,
so this file is safe in a sparse worktree and needs no needs_full_checkout
marker.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.build_am_edition import (
    STATES,
    CLASSIFICATIONS,
    build_payload,
)

FORBIDDEN_KEYS = {
    "score", "rank", "signal", "gate", "size", "sizing", "ENTRY_OPEN",
    "prophet", "conviction", "buy", "sell", "target",
}


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _fresh_tree(tmp_path: Path, *, tape_asof: str, session_date: str) -> tuple[Path, Path]:
    site = tmp_path / "site"
    data = tmp_path / "data"
    _write(site / "live" / "quotes.json", {
        "ts": 1, "asof": tape_asof, "source": "yahoo",
        "quotes": {
            "SPY": {"price": 740.0, "prevClose": 739.0, "changePct": 0.14, "basis": "regular"},
        },
        "meta": {},
    })
    _write(data / "market_state" / "latest.json", {
        "asof": session_date, "label_en": "Risk-on", "label_zh": "风险偏好",
        "posture_en": "Constructive", "posture_zh": "积极", "headline_en": "x", "headline_zh": "x",
    })
    _write(data / "regime" / "latest.json", {
        "asof": session_date, "quad_name": "Reflation", "label": "Reflation",
    })
    _write(data / "neuralweb" / "market_plane.json", {
        "asof": session_date, "verdict": "confirming", "contradiction_count": 0,
        "stale": False, "gaps": [],
    })
    _write(data / "release_forecast" / "latest.json", {
        "asof": f"{session_date}T10:00:00Z",
        "upcoming": [{"date": f"{session_date}T13:30:00Z", "name": "CPI"}],
    })
    _write(site / "master_brief.json", {
        "generated_at": f"{session_date}T10:00:00Z", "state_asof": session_date, "lens": "macro",
    })
    return site, data


def _empty_tree(tmp_path: Path) -> tuple[Path, Path]:
    site = tmp_path / "site"
    data = tmp_path / "data"
    site.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    return site, data


def test_generated_at_may_not_launder_a_stale_source(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)  # Tuesday, after open
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-05T10:00:00Z", session_date="2026-09-08")
    payload = build_payload(site, data, now=now)
    tape = next(b for b in payload["blocks"] if b["key"] == "tape_since_prior_close")
    assert tape["state"] != "CURRENT"
    assert tape["age_minutes"] > tape["max_age_minutes"]
    for b in payload["blocks"]:
        if b["state"] == "CURRENT" and b["key"] != "session_clock":
            assert 0 <= b["age_minutes"] <= b["max_age_minutes"]

    # Future-stamped source (negative age) must never be CURRENT.
    site2, data2 = _fresh_tree(tmp_path, tape_asof="2026-09-09T10:00:00Z", session_date="2026-09-08")
    payload2 = build_payload(site2, data2, now=now)
    tape2 = next(b for b in payload2["blocks"] if b["key"] == "tape_since_prior_close")
    assert tape2["state"] != "CURRENT"


def test_every_block_carries_its_own_source_clock(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    payload = build_payload(site, data, now=now)
    gen_at = payload["generated_at"]
    for b in payload["blocks"]:
        if b["state"] in ("CURRENT", "STALE_WITH_LAST_KNOWN"):
            assert b["source_as_of"] is not None
            if b["key"] != "session_clock":
                # session_clock is a self-computed calendar fact: its "source"
                # IS the current instant, so equality is not laundering.
                assert b["source_as_of"] != gen_at
        else:
            assert b["source_as_of"] is None


def test_state_vocabulary_is_exactly_the_five(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    payload = build_payload(site, data, now=now)
    for b in payload["blocks"]:
        assert b["state"] in STATES
    raw = json.dumps(payload)
    for s in ("CURRENT", "STALE_WITH_LAST_KNOWN", "UNAVAILABLE", "NOT_COVERED", "NOT_YET_OPEN"):
        assert s in STATES  # sanity: vocabulary itself is exactly 5 members
    assert len(STATES) == 5


def test_missing_source_prints_a_null_it_does_not_drop_the_block(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _empty_tree(tmp_path)
    payload = build_payload(site, data, now=now)
    keys = {b["key"] for b in payload["blocks"]}
    expected = {
        "session_clock", "tape_since_prior_close", "market_state", "regime",
        "cross_asset_plane", "todays_calendar", "prior_close_brief_ref",
    }
    assert keys == expected
    observed_null = 0
    for b in payload["blocks"]:
        if b["key"] == "session_clock":
            continue
        assert b["state"] in ("UNAVAILABLE", "NOT_COVERED")
        assert b["state_reason_en"]
        assert b["state_reason_zh"]
        observed_null += 1
    assert payload["null_count"] == observed_null


def test_feasibility_is_computed_not_assumed(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)

    site_a, data_a = _fresh_tree(tmp_path / "a", tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    payload_a = build_payload(site_a, data_a, now=now)
    assert payload_a["morning_source_feasibility"] == "AVAILABLE"

    site_b, data_b = _fresh_tree(tmp_path / "b", tape_asof="2026-07-27T22:32:09Z", session_date="2026-09-08")
    payload_b = build_payload(site_b, data_b, now=now)
    assert payload_b["morning_source_feasibility"] == "DEGRADED"
    assert "site/live/quotes.json" in payload_b["morning_source_feasibility_cause"]
    for b in payload_b["blocks"]:
        for row in b.get("rows") or []:
            if isinstance(row, dict) and "last" in row:
                assert b["state"] != "CURRENT"

    site_c, data_c = _empty_tree(tmp_path / "c")
    payload_c = build_payload(site_c, data_c, now=now)
    assert payload_c["morning_source_feasibility"] == "BLOCKED"
    assert "site/live/quotes.json" in payload_c["morning_source_feasibility_cause"]


def test_no_authority_fields_are_emitted(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    payload = build_payload(site, data, now=now)
    raw = json.dumps(payload)

    def _walk_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from _walk_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from _walk_keys(item)

    keys = set(_walk_keys(payload))
    assert not (keys & FORBIDDEN_KEYS), keys & FORBIDDEN_KEYS
    assert payload["authority"] == "display_only"
    assert payload["display_only"] is True


def test_every_field_is_classified(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    payload = build_payload(site, data, now=now)
    for b in payload["blocks"]:
        assert b["classification"] in CLASSIFICATIONS


def test_weekend_and_before_open_states(tmp_path):
    saturday = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)  # Saturday
    site, data = _fresh_tree(tmp_path / "sat", tape_asof="2026-09-04T20:00:00Z", session_date="2026-09-05")
    payload = build_payload(site, data, now=saturday)
    assert payload["session_state"] == "NOT_YET_OPEN"
    tape = next(b for b in payload["blocks"] if b["key"] == "tape_since_prior_close")
    assert tape["state"] != "CURRENT"

    weekday_before_open = datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc)  # Tuesday 11:00 UTC
    site2, data2 = _fresh_tree(tmp_path / "wk", tape_asof="2026-09-08T10:59:00Z", session_date="2026-09-08")
    payload2 = build_payload(site2, data2, now=weekday_before_open)
    assert payload2["session_state"] == "NOT_YET_OPEN"
    tape2 = next(b for b in payload2["blocks"] if b["key"] == "tape_since_prior_close")
    assert tape2["state"] != "CURRENT"


def test_output_is_deterministic(tmp_path):
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    site, data = _fresh_tree(tmp_path, tape_asof="2026-09-08T13:00:00Z", session_date="2026-09-08")
    p1 = build_payload(site, data, now=now)
    p2 = build_payload(site, data, now=now)
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_producer_never_breaks_the_render(tmp_path):
    from scripts import build_am_edition as mod

    site = tmp_path / "site"
    data = tmp_path / "data"
    site.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    # Poisoned 0-byte source.
    (site / "live").mkdir(parents=True, exist_ok=True)
    (site / "live" / "quotes.json").write_bytes(b"")

    class _FakeCfg(dict):
        pass

    orig_load = mod.config.load
    orig_root = mod.config.ROOT
    try:
        mod.config.load = lambda: {"storage": {"site_dir": str(site)}}
        mod.config.ROOT = str(tmp_path)
        rc = mod.main()
        assert rc == 0
        out = site / "am_edition.json"
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["schema"] == "am_edition.v1"
    finally:
        mod.config.load = orig_load
        mod.config.ROOT = orig_root
