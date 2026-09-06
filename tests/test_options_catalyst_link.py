"""Tests for engine.options_catalyst_link — F03 catalyst-linkage read-model.

Synthetic live_flow event fixtures only. No data/ I/O. No network. No clock.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
from datetime import date

import pytest

from engine.options_catalyst_link import (
    AMBIGUOUS_MULTIPLE,
    BINDING_STATES,
    BOUND,
    EXPIRY_MISMATCH,
    IDENTITY_UNRESOLVED,
    STALE_CATALYST,
    UNBOUND_NO_CATALYST,
    CalendarContext,
    CatalystCandidate,
    ContractKeyError,
    bind_event,
    bind_events,
    write_links,
)
from engine.stock_identity.authority import authority_block, is_zero_authority

EXPECTED_KEYS = frozenset(
    {
        "schema",
        "spec_version",
        "session_date",
        "asof",
        "event_id",
        "contract",
        "binding_state",
        "identity",
        "catalyst",
        "catalyst_state",
        "catalyst_reason",
        "candidates",
        "expiry",
        "evidence",
        "source_rights",
        "authority",
        "is_context_only",
    }
)

ASOF = date(2026, 9, 4)
# 2026-10-16 is a third Friday (monthly OPEX)
EXP_OK = "2026-10-16"
KNOWN = frozenset({"AAPL", "SPY", "QQQ"})


def _event(**overrides):
    """Synthetic live_flow event dict using the emitted field names."""
    base = {
        "id": "a1b2c3d4e5f60718",
        "ts": "2026-09-04T14:30:00-04:00",
        "observed_at": "2026-09-04T14:30:05-04:00",
        "root": "AAPL",
        "group": "tech",
        "group_zh": "科技",
        "right": "C",
        "exp": EXP_OK,
        "strike": 240.0,
        "dte": 42,
        "dte_bucket": "30_60",
        "mny_bucket": "atm",
        "side": "ask",
        "n_prints": 3,
        "size": 150,
        "avg_price": 2.5,
        "premium": 37500.0,
        "premium_z": 2.1,
        "baseline_source": "session",
        "selection_rule": "floor",
        "selection_floor_usd": 25000.0,
        "selection_root_class": "single_name",
        "vol_gt_oi": False,
        "vol_gt_oi_ratio": None,
        "oi_vintage": None,
        "repeated": False,
        "zerodte": False,
        "signing_source": "tape",
        "swept": False,
        "microstructure": {"spread_bps": 10},
    }
    base.update(overrides)
    return base


def _empty_calendar(macros=()):
    return CalendarContext(
        is_third_friday=None,
        is_quad_witching=None,
        macro_catalysts=tuple(macros),
    )


def _earnings(d: date, *, stale=False, source="earnings_blackout.assess", label="Q4 results"):
    return CatalystCandidate(
        kind="earnings",
        date=d,
        source=source,
        stale=stale,
        as_of_age_td=2 if stale is False else None,
        label=label,
    )


# ── 1. positive bind ──────────────────────────────────────────────────────────


def test_positive_bind_single_in_window_catalyst():
    cat = _earnings(date(2026, 10, 30))
    # Wait — 2026-10-30 is AFTER exp 2026-10-16, so that would be after expiry.
    # Need catalyst BETWEEN asof and exp.
    cat = _earnings(date(2026, 10, 10), label="Q3 results")
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [cat]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert link.binding_state == BOUND
    assert rec["binding_state"] == BOUND
    assert rec["catalyst"]["date"] == "2026-10-10"
    assert rec["catalyst"]["days_expiry_minus_catalyst"] == (
        date(2026, 10, 16) - date(2026, 10, 10)
    ).days
    assert len(rec["evidence"]) == 3
    assert [e["leg"] for e in rec["evidence"]] == ["event", "catalyst", "expiry"]


# ── 2. ambiguous — never nearest ──────────────────────────────────────────────


def test_ambiguous_multiple_is_typed_not_nearest():
    near = _earnings(date(2026, 9, 15), label="near")
    far = _earnings(date(2026, 10, 8), label="far", source="earnings_blackout.assess:b")
    # Different kinds so dedupe by (kind, date) keeps both; same kind different dates.
    near = CatalystCandidate(
        kind="earnings", date=date(2026, 9, 15), source="a", stale=False, label="near"
    )
    far = CatalystCandidate(
        kind="cpi", date=date(2026, 10, 8), source="b", stale=False, label="far"
    )
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [near, far]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == AMBIGUOUS_MULTIPLE
    assert rec["catalyst"] is None
    assert len(rec["candidates"]) == 2
    dates = {c["date"] for c in rec["candidates"]}
    assert dates == {"2026-09-15", "2026-10-08"}
    # Explicitly: did NOT pick the nearer date
    assert rec["catalyst"] is None


# ── 3. stale True ─────────────────────────────────────────────────────────────


def test_stale_catalyst_is_typed():
    cat = _earnings(date(2026, 10, 10), stale=True)
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [cat]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == STALE_CATALYST
    assert len(rec["candidates"]) == 1
    assert rec["candidates"][0]["stale"] is True


# ── 4. stale None is never fresh ──────────────────────────────────────────────


def test_stale_none_is_not_read_as_fresh():
    cat = CatalystCandidate(
        kind="earnings",
        date=date(2026, 10, 10),
        source="earnings_blackout.assess",
        stale=None,
        as_of_age_td=None,
        label="unchecked",
    )
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [cat]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == STALE_CATALYST
    assert rec["candidates"][0]["stale"] is None
    assert rec["candidates"][0]["stale_reason"] == "never_checked"


# ── 5. identity unresolved — expiry still runs ────────────────────────────────


def test_identity_unresolved_is_typed():
    link = bind_event(
        _event(root="ZZZZ"),
        asof=ASOF,
        catalysts={},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == IDENTITY_UNRESOLVED
    assert rec["identity"]["resolved_symbol"] is None
    assert rec["identity"]["state"] == IDENTITY_UNRESOLVED
    assert rec["catalyst_state"] == "NOT_ATTEMPTED"
    # Expiry leg still populated
    assert rec["expiry"]["state"] == "OK"
    assert rec["expiry"]["is_third_friday"] is True
    assert isinstance(rec["expiry"]["dte_calendar_days"], int)


# ── 6. expiry mismatch does not blank the event ───────────────────────────────


def test_expiry_mismatch_does_not_blank_the_event():
    link = bind_event(
        _event(exp="not-a-date"),
        asof=ASOF,
        catalysts={"AAPL": [_earnings(date(2026, 9, 20))]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == EXPIRY_MISMATCH
    assert rec["expiry"]["state"] == EXPIRY_MISMATCH
    assert rec["expiry"]["is_third_friday"] is None  # not False
    assert rec["expiry"]["is_quad_witching"] is None
    assert rec["event_id"] == "a1b2c3d4e5f60718"
    assert rec["contract"]["root"] == "AAPL"
    assert rec["identity"]["state"] == "RESOLVED"


# ── 7. catalyst after expiry ──────────────────────────────────────────────────


def test_catalyst_after_expiry_is_typed_expiry_mismatch():
    cat = _earnings(date(2026, 11, 15))  # after exp 2026-10-16
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [cat]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == EXPIRY_MISMATCH
    assert rec["expiry"]["state"] == EXPIRY_MISMATCH
    assert rec["expiry"]["reason"] == "catalyst_after_expiry"
    assert rec["catalyst_reason"] == "all_candidates_after_expiry"
    assert rec["catalyst_state"] == UNBOUND_NO_CATALYST


# ── 8. no catalyst — never invented ───────────────────────────────────────────


def test_no_catalyst_is_unbound_never_invented():
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["binding_state"] == UNBOUND_NO_CATALYST
    assert rec["catalyst"] is None
    assert rec["candidates"] == []
    blob = json.dumps(rec, sort_keys=True)
    # No invented catalyst date field sneaking in
    assert '"catalyst": null' in blob or rec["catalyst"] is None
    for key, val in rec.items():
        if key == "asof" or key == "session_date":
            continue
        if key == "contract":
            continue
        if key == "expiry":
            continue
        if isinstance(val, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
            pytest.fail(f"invented date at top-level key {key}: {val}")


# ── 9. contract key miss raises ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"strike": None},
        {"root": ""},
        {"right": "X"},
        {"id": None},
    ],
)
def test_contract_key_miss_raises(overrides, tmp_path):
    ev = _event(**overrides)
    # Drop key entirely for strike when None
    if "strike" in overrides and overrides["strike"] is None:
        ev.pop("strike", None)
    if "id" in overrides and overrides["id"] is None:
        ev.pop("id", None)
    with pytest.raises(ContractKeyError):
        bind_event(
            ev,
            asof=ASOF,
            catalysts={},
            calendar=_empty_calendar(),
            known_symbols=KNOWN,
        )
    # Nothing written
    out = tmp_path / "x.jsonl"
    assert not out.exists()


# ── 10. determinism ───────────────────────────────────────────────────────────


def test_determinism_byte_identical():
    cats = [
        CatalystCandidate(
            kind="cpi", date=date(2026, 10, 8), source="b", stale=False
        ),
        CatalystCandidate(
            kind="earnings", date=date(2026, 9, 15), source="a", stale=False
        ),
    ]
    events = [
        _event(id="id00000000000001", root="AAPL"),
        _event(id="id00000000000002", root="SPY", selection_root_class="etf_anchor"),
    ]
    kwargs = dict(
        asof=ASOF,
        catalysts={"AAPL": cats, "SPY": []},
        calendar=_empty_calendar(
            macros=(
                CatalystCandidate(
                    kind="fomc", date=date(2026, 9, 20), source="event_calendar:static", stale=False
                ),
            )
        ),
        known_symbols=KNOWN,
    )
    # Shuffle input order of catalyst list between calls — bind sorts internally
    a = bind_events(events, **kwargs)
    b = bind_events(events, **kwargs)
    for la, lb in zip(a, b):
        assert json.dumps(la.record, sort_keys=True) == json.dumps(
            lb.record, sort_keys=True
        )
        assert [c["date"] for c in la.record["candidates"]] == [
            c["date"] for c in lb.record["candidates"]
        ]
        assert [e["ref_id"] for e in la.record["evidence"]] == [
            e["ref_id"] for e in lb.record["evidence"]
        ]


# ── 11. nulls printed ─────────────────────────────────────────────────────────


def test_nulls_are_printed_not_absent():
    fixtures = {
        BOUND: (
            _event(),
            {"AAPL": [_earnings(date(2026, 10, 10))]},
            _empty_calendar(),
            KNOWN,
        ),
        AMBIGUOUS_MULTIPLE: (
            _event(),
            {
                "AAPL": [
                    CatalystCandidate(
                        kind="earnings", date=date(2026, 9, 15), source="a", stale=False
                    ),
                    CatalystCandidate(
                        kind="cpi", date=date(2026, 10, 8), source="b", stale=False
                    ),
                ]
            },
            _empty_calendar(),
            KNOWN,
        ),
        STALE_CATALYST: (
            _event(),
            {"AAPL": [_earnings(date(2026, 10, 10), stale=True)]},
            _empty_calendar(),
            KNOWN,
        ),
        UNBOUND_NO_CATALYST: (
            _event(),
            {},
            _empty_calendar(),
            KNOWN,
        ),
        IDENTITY_UNRESOLVED: (
            _event(root="NOPE"),
            {},
            _empty_calendar(),
            KNOWN,
        ),
        EXPIRY_MISMATCH: (
            _event(exp="bogus"),
            {"AAPL": [_earnings(date(2026, 9, 20))]},
            _empty_calendar(),
            KNOWN,
        ),
    }
    assert set(fixtures) == set(BINDING_STATES)
    for state, (ev, cats, cal, known) in fixtures.items():
        link = bind_event(ev, asof=ASOF, catalysts=cats, calendar=cal, known_symbols=known)
        rec = link.record
        assert set(rec) == EXPECTED_KEYS, state
        assert rec["binding_state"] == state
        # Unknowns are None, never absent
        assert "catalyst_reason" in rec
        assert "catalyst" in rec
        assert rec["identity"]["state"] is not None
        assert rec["expiry"]["state"] is not None


# ── 12. zero authority ────────────────────────────────────────────────────────


def test_zero_authority():
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [_earnings(date(2026, 10, 10))]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    rec = link.record
    assert rec["authority"] == authority_block()
    assert all(v is False for v in rec["authority"].values())
    assert rec["source_rights"] == "research_expression_only"
    assert rec["is_context_only"] is True
    assert is_zero_authority(rec) is True


# ── 13. no scoring / prophet import ───────────────────────────────────────────


def test_no_scoring_or_prophet_import():
    src_path = pathlib.Path("engine/options_catalyst_link.py")
    src = src_path.read_text(encoding="utf-8")
    assert (
        re.search(
            r"^(from|import) +(engine\.(prophet|conditions|regime|run|inputs|"
            r"equity_alloc|calibrate|scoring)|scripts|lib\.prophet)",
            src,
            re.M,
        )
        is None
    )

    forbidden_prefixes = (
        "engine.prophet",
        "engine.conditions",
        "engine.regime",
        "engine.run",
        "engine.inputs",
        "engine.equity_alloc",
        "engine.calibrate",
        "engine.live_flow",
        "scripts",
        "pandas",
        "requests",
        "urllib",
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                for prefix in forbidden_prefixes:
                    assert not (
                        name == prefix or name.startswith(prefix + ".")
                    ), f"forbidden import {name}"
                assert not name.startswith("engine.") or name in (
                    "engine.event_calendar",
                    "engine.stock_identity.authority",
                ) or name.startswith("engine.stock_identity")
                if name.startswith("engine.") and "signal" in name:
                    pytest.fail(f"forbidden signal import {name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prefix in forbidden_prefixes:
                assert not (
                    mod == prefix or mod.startswith(prefix + ".")
                ), f"forbidden from-import {mod}"
            if mod.startswith("engine.") and mod.endswith("_signals"):
                pytest.fail(f"forbidden signals import {mod}")
            assert mod in (
                "engine.event_calendar",
                "engine.stock_identity.authority",
                "__future__",
            ) or mod.split(".")[0] in (
                "dataclasses",
                "datetime",
                "json",
                "typing",
                "os",
            ) or mod == "engine.stock_identity.authority"


# ── 14. write_links path discipline ───────────────────────────────────────────


def test_write_links_only_touches_given_path(tmp_path):
    data_sentinel = pathlib.Path("data/options/catalyst_links")
    pre_existed = data_sentinel.exists()
    link = bind_event(
        _event(),
        asof=ASOF,
        catalysts={"AAPL": [_earnings(date(2026, 10, 10))]},
        calendar=_empty_calendar(),
        known_symbols=KNOWN,
    )
    out = tmp_path / "x.jsonl"
    n = write_links(out, [link, link])
    assert n == 2
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert obj["schema"] == "options.catalyst_link/v1"
    if not pre_existed:
        assert not data_sentinel.exists()
