"""Contract tests for the Macro -> Terminal opportunity receipt projection."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_opportunity_timeline import (  # noqa: E402
    SCHEMA,
    SOURCE_SPECS,
    build_timeline,
    main,
    merge_checkpoint,
    normalize_ticker,
)


EVENT_KEYS = {
    "id", "market", "system", "definition", "authority", "surfaced_at", "entry_date",
    "entry_basis", "entry_price", "rank", "tier", "state", "maturity",
    "latest_price", "return_pct", "excess_pct", "sessions", "source_artifact",
    "source_as_of", "priced_through",
}


def _ledger(market: str, rows: list[dict], *, definition: str | None = None,
            as_of: str = "2026-08-10", priced_through: str | None = None,
            prior: dict | None = None, extras: list[dict] | None = None) -> dict:
    meta = {}
    if definition:
        meta["board_definition"] = definition
    if priced_through:
        meta["priced_through"] = priced_through
    doc = {
        "schema": "track_ledger/v1",
        "market": market,
        "as_of": as_of,
        "state": "accruing",
        "summary": {},
        "rows": rows,
        "meta": meta,
    }
    if prior is not None:
        doc["prior_record"] = prior
    if extras is not None:
        doc["extra_records"] = extras
    return doc


def _row(ticker: str, surfaced: str, **overrides) -> dict:
    row = {
        "t": ticker,
        "d": surfaced,
        "e": 10.0,
        "l": 11.0,
        "p": 10.0,
        "x": 8.0,
        "dy": 4,
        "st": "early",
        "m": False,
        "rk": 7,
        "tr": "T2",
    }
    row.update(overrides)
    return row


def _sources() -> list[tuple[dict[str, str], dict]]:
    specs = {spec["artifact"]: spec for spec in SOURCE_SPECS}
    prior = {
        "board_definition": "cn_standout_v1",
        "rows": [_row("601212.SH", "2026-07-23", e=4.73, l=5.44, p=15.0,
                      x=14.84, dy=10, st="beat", m=True, rk=28, tr="T1",
                      eb="t1_open")],
    }
    # Reversal is repeated here on purpose.  The dedicated reversal ledger must
    # win the stable-key collision below.
    reversal_copy = {
        "board_definition": "cn_reversal_watch_v1",
        "rows": [_row("002716.SZ", "2026-08-05", e=8.0, p=-1.0, eb="t1_open")],
    }
    cn_track = _ledger(
        "CN",
        [_row("600000.SS", "2026-08-07", eb="t1_hl2")],
        definition="cn_prophet_v3",
        as_of="2026-08-07",
        prior=prior,
        extras=[reversal_copy],
    )
    cn_reversal = _ledger(
        "CN",
        [_row("002716.SZ", "2026-08-05", e=9.0, l=9.4, p=4.4,
              rk=19, tr=None, eb="t1_open")],
        definition="cn_reversal_watch_v1",
        as_of="2026-08-07",
        # This duplicate prior record must not produce a second event.
        prior=copy.deepcopy(prior),
    )
    us = _ledger(
        "US",
        [_row("NEM", "2026-07-24", e=93.47, l=112.98, p=20.9, x=None,
              dy=9, st="onboard", rk=15, tr=None, bd="confluence")],
        as_of="2026-08-07",
        priced_through="2026-08-07",
    )
    hk = _ledger(
        "HK",
        [_row("09988.HK", "2026-07-13", e=None, l=None, p=None, x=None,
              dy=None, rk=9, tr=None)],
        as_of="2026-08-10",
    )
    return [
        (specs["factordata/us_track_ledger.json"], us),
        (specs["factordata/cn_track_ledger.json"], cn_track),
        (specs["factordata/cn_reversal_ledger.json"], cn_reversal),
        (specs["factordata/hk_track_ledger.json"], hk),
    ]


def test_flattens_all_eras_dedupes_and_preserves_candidate_authority():
    payload = build_timeline(_sources())

    assert set(payload) == {"schema", "as_of", "priced_through", "symbols"}
    assert payload["schema"] == SCHEMA
    assert payload["as_of"] == "2026-08-10"
    assert payload["priced_through"] == {"CN": None, "HK": None, "US": "2026-08-07"}
    assert set(payload["symbols"]) == {"NEM", "600000.SS", "601212.SS", "002716.SZ", "9988.HK"}

    nem = payload["symbols"]["NEM"]["events"][0]
    assert set(nem) == EVENT_KEYS
    assert nem["system"] == "prophet_board"
    assert nem["market"] == "US"
    assert nem["definition"] == "confluence"
    assert nem["authority"] == "candidate"
    assert nem["entry_date"] is None  # surfaced bar is not fabricated as the T+1 fill date
    assert nem["entry_basis"] == "next_session_close"
    assert nem["entry_price"] == 93.47
    assert nem["source_artifact"] == "site/factordata/us_track_ledger.json"

    legacy = payload["symbols"]["601212.SS"]["events"][0]
    assert legacy["definition"] == "cn_standout_v1"
    assert legacy["authority"] == "candidate"
    assert legacy["maturity"] == "matured"
    assert legacy["entry_basis"] == "t1_open"

    reversal = payload["symbols"]["002716.SZ"]["events"]
    assert len(reversal) == 1
    assert reversal[0]["system"] == "reversal_watch"
    assert reversal[0]["authority"] == "watch"
    assert reversal[0]["entry_price"] == 9.0
    assert reversal[0]["source_artifact"].endswith("cn_reversal_ledger.json")

    hk = payload["symbols"]["9988.HK"]["events"][0]
    assert hk["authority"] == "candidate"
    assert hk["entry_price"] is None
    assert all(event["authority"] in {"candidate", "watch"}
               for block in payload["symbols"].values() for event in block["events"])


def test_identity_is_stable_when_marks_change_and_reads_future_entry_date():
    first_sources = _sources()
    first = build_timeline(first_sources)["symbols"]["NEM"]["events"][0]

    second_sources = copy.deepcopy(first_sources)
    row = second_sources[0][1]["rows"][0]
    row.update({"l": 130.0, "p": 39.1, "dy": 10, "ed": "2026-07-27"})
    second = build_timeline(second_sources)["symbols"]["NEM"]["events"][0]

    assert first["id"] == second["id"]
    assert second["latest_price"] == 130.0
    assert second["entry_date"] == "2026-07-27"


def test_checkpoint_retains_rows_that_fall_out_of_capped_source_and_current_marks_win():
    first = build_timeline(_sources())
    old = copy.deepcopy(first["symbols"]["NEM"]["events"][0])
    old["surfaced_at"] = "2025-01-02"
    old["id"] = "opp_" + hashlib.sha256(
        "\x1f".join(("US", old["system"], old["definition"], "NEM", old["surfaced_at"])).encode()
    ).hexdigest()[:20]
    first["symbols"]["NEM"]["events"].append(old)

    second_sources = copy.deepcopy(_sources())
    second_sources[0][1]["rows"][0].update({"l": 130.0, "p": 39.1})
    current = build_timeline(second_sources)
    merged = merge_checkpoint(current, first)
    events = merged["symbols"]["NEM"]["events"]

    assert len(events) == 2
    assert {event["surfaced_at"] for event in events} == {"2025-01-02", "2026-07-24"}
    refreshed = next(event for event in events if event["surfaced_at"] == "2026-07-24")
    assert refreshed["latest_price"] == 130.0
    assert refreshed["return_pct"] == 39.1


def test_checkpoint_migrates_the_initial_marketless_v1_without_repainting_identity():
    current = build_timeline(_sources())
    prior = copy.deepcopy(current)
    for block in prior["symbols"].values():
        for event in block["events"]:
            event.pop("market")

    merged = merge_checkpoint(current, prior)
    assert merged == current


def test_legacy_definition_is_replaced_by_authoritative_admission_without_duplication():
    prior = build_timeline(_sources())
    old = prior["symbols"]["NEM"]["events"][0]
    old_definition = old["definition"]
    assert old_definition == "confluence"  # fixture carries a current per-row bd
    old["definition"] = "legacy"
    old["id"] = "opp_" + hashlib.sha256(
        "\x1f".join(("US", old["system"], "legacy", "NEM", old["surfaced_at"])).encode()
    ).hexdigest()[:20]
    old["latest_price"] = 115.0
    old["return_pct"] = 23.0
    old["source_as_of"] = "2026-08-10"
    old["priced_through"] = "2026-08-10"

    current = build_timeline(_sources())
    current_event = current["symbols"]["NEM"]["events"][0]
    current_event["source_as_of"] = "2026-08-07"
    current_event["priced_through"] = "2026-08-07"
    merged = merge_checkpoint(current, prior)
    events = merged["symbols"]["NEM"]["events"]

    assert len(events) == 1
    assert events[0]["definition"] == "confluence"
    assert events[0]["id"] == current_event["id"]
    # Identity migrates, but a stale reconstruction cannot roll the receipt's marks back.
    assert events[0]["latest_price"] == 115.0
    assert events[0]["return_pct"] == 23.0
    assert events[0]["priced_through"] == "2026-08-10"


def test_stale_current_same_id_cannot_overwrite_a_fresher_checkpoint_mark():
    prior = build_timeline(_sources())
    old = prior["symbols"]["NEM"]["events"][0]
    old.update({
        "latest_price": 115.0, "return_pct": 23.0,
        "source_as_of": "2026-08-10", "priced_through": "2026-08-10",
    })
    prior["as_of"] = "2026-08-10"
    prior["priced_through"]["US"] = "2026-08-10"

    current = build_timeline(_sources())
    incoming = current["symbols"]["NEM"]["events"][0]
    incoming.update({
        "latest_price": 105.0, "return_pct": 12.0,
        "source_as_of": "2026-08-07", "priced_through": "2026-08-07",
    })
    merged = merge_checkpoint(current, prior)
    event = merged["symbols"]["NEM"]["events"][0]

    assert merged["as_of"] == "2026-08-10"
    assert merged["priced_through"]["US"] == "2026-08-10"
    assert event["latest_price"] == 115.0
    assert event["return_pct"] == 23.0
    assert event["source_as_of"] == "2026-08-10"
    assert event["priced_through"] == "2026-08-10"


def test_bad_checkpoint_id_is_fail_closed(tmp_path):
    site = tmp_path / "site"
    for spec, doc in _sources():
        path = site / spec["artifact"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")
    out = site / "factordata" / "opportunity_timeline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    last_good = build_timeline(_sources())
    last_good["symbols"]["NEM"]["events"][0]["id"] = "tampered"
    out.write_text(json.dumps(last_good), encoding="utf-8")
    before = out.read_bytes()

    assert main(["--site", str(site)]) == 1
    assert out.read_bytes() == before


def test_ticker_normalization_is_conservative():
    assert normalize_ticker("601212.sh", "CN") == "601212.SS"
    assert normalize_ticker("000001.XSHE", "CN") == "000001.SZ"
    assert normalize_ticker("09988.hk", "HK") == "9988.HK"
    assert normalize_ticker("brk.b", "US") == "BRK.B"
    assert normalize_ticker("601212", "CN") is None
    assert normalize_ticker("9988", "HK") is None
    assert normalize_ticker("N/A", "US") is None


def test_cli_is_atomic_and_leaves_last_good_when_a_required_source_is_missing(tmp_path):
    site = tmp_path / "site"
    out = site / "factordata" / "opportunity_timeline.json"
    out.parent.mkdir(parents=True)
    out.write_text('{"last_good":true}\n', encoding="utf-8")

    assert main(["--site", str(site)]) == 1
    assert json.loads(out.read_text()) == {"last_good": True}


def test_cli_writes_strict_deterministic_json(tmp_path):
    site = tmp_path / "site"
    for spec, doc in _sources():
        path = site / spec["artifact"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")

    assert main(["--site", str(site)]) == 0
    out = site / "factordata" / "opportunity_timeline.json"
    first = out.read_bytes()
    assert json.loads(first)["schema"] == SCHEMA
    assert main(["--site", str(site)]) == 0
    assert out.read_bytes() == first
