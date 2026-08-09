"""Hermetic adversarial tests for the W0b focused vendor-snapshot quote lane."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import threading
import time

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine import chain_snapshot_completion as completion
from engine import options_focused_quote as focused
from engine import options_structure_intraday as w0a
from scripts import build_options_focused_quote as builder


SESSION = "2026-08-07"
BUCKET = "15:45"
AVAILABLE = "2026-08-07T20:00:00.000000Z"
T0 = datetime(2026, 8, 7, 20, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=1)
PROFILE_A = "convex_otm_30_180_v1"
PROFILE_B = "prophet_delta60_monthly_v1"
SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "contracts/options/options.focused_quote_attempt.v1.schema.json"
    ).read_text()
)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def _schema_errors(record: dict) -> list[str]:
    return [error.message for error in VALIDATOR.iter_errors(record)]


def _contract_id(root: str, expiration: str, right: str, strike: str) -> str:
    raw = f"{root}|{expiration}|{right}|{strike}".encode("ascii")
    return "contract:uchain:" + sha256(raw).hexdigest()


def _packet(
    root: str,
    rows: list[tuple[str, str, str, tuple[str, ...]]],
) -> tuple[dict, dict[tuple[str, str], str]]:
    """Build the exact W0a identity surface W0b consumes.

    rows: (expiration, right, strike_canonical, profile_ids)
    """
    contracts: list[dict] = []
    profiles: dict[str, dict] = {}
    identities: dict[tuple[str, str], str] = {}
    for expiration, right, strike, profile_ids in rows:
        contract_id = _contract_id(root, expiration, right, strike)
        strike_value = float(Decimal(strike))
        occ = w0a.construct_occ_symbol(
            root, date.fromisoformat(expiration), right, Decimal(strike)
        )
        contracts.append({
            "contract_id": contract_id,
            "contract": {
                "root": root,
                "expiration": expiration,
                "right": right,
                "strike": strike_value,
                "strike_canonical": strike,
                "occ_symbol": occ,
            },
            "dte_calendar_days": (
                date.fromisoformat(expiration) - date.fromisoformat(SESSION)
            ).days,
            "moneyness": {
                "underlying_price": max(strike_value * 0.9, 1.0),
                "otm_pct": 10.0,
                "state": "otm",
            },
            "quote": {
                "snapshot_ts": "2026-08-07T19:59:00.000000Z",
                "age_minutes": 1.0,
                "bid": 1.25,
                "ask": 1.35,
                "mid": 1.30,
                "spread_abs": 0.10,
                "spread_pct": 7.6923076923,
                "browser_eligible": True,
                "ineligible_reasons": [],
                "bid_size": None,
                "ask_size": None,
                "depth_available": False,
                "capacity_assessed": False,
            },
            "greeks": {
                "delta": 0.5,
                "theta": -0.1,
                "vega": 0.2,
                "rho": 0.01,
                "epsilon": -0.01,
                "lambda": 4.0,
                "gamma": 0.02,
                "vanna": 0.01,
                "charm": -0.01,
                "vomma": 0.03,
                "veta": -0.02,
            },
            "implied_vol": 0.25,
            "iv_error": None,
            "volume": {
                "value": 10,
                "available": True,
                "source_note": "chain_snapshot",
            },
            "open_interest": {
                "value": 250,
                "snapshot_ts": "2026-08-06T20:00:00.000000Z",
                "vintage_session": "2026-08-06",
                "timing": "prior_session_eod_positions",
                "vintage_derivation": "previous_real_nyse_session",
            },
            "profile_matches": list(profile_ids),
            "profile_evaluations": {
                PROFILE_A: {
                    "matched": PROFILE_A in profile_ids,
                    "passed_filters": [],
                    "failed_filters": [],
                }
            },
            "authority": w0a.authority_block(),
        })
        for profile in profile_ids:
            profiles.setdefault(profile, {"eligible_contract_ids": []})[
                "eligible_contract_ids"
            ].append(contract_id)
            identities[(profile, strike)] = contract_id
    prophet_eligible = profiles.get(PROFILE_B, {}).get("eligible_contract_ids", [])
    convex_eligible = profiles.get(PROFILE_A, {}).get("eligible_contract_ids", [])
    governed_profiles = {
        PROFILE_B: {
            "profile_id": PROFILE_B,
            "profile_kind": "legacy_display_resolver",
            "definition": {
                "law_source": "engine.prophet_bridge.resolve_option",
                "right": "direction-derived call or put",
                "target_expiry": "nearest listed expiry around D+60",
                "primary": "minimum absolute delta distance",
                "fallback": "deterministic closest OTM",
                "legacy_fallback_disclosure": "source-order fallback is not reused",
                "primary_tie_semantics": "first source row, matching pandas Series.idxmin",
                "browser_gate_semantics": "browser eligible quote required",
                "quote_browser_eligible_required": True,
            },
            "within_profile_order": [],
            "eligible_contract_ids": prophet_eligible,
            "selection": (
                {
                    "contract_id": prophet_eligible[0],
                    "mode": "primary_delta60",
                    "target_delta": 0.6,
                }
                if prophet_eligible
                else None
            ),
            "authority": w0a.authority_block(),
            "status": "selected" if prophet_eligible else "context_required",
            "abstention_reason": None,
            "request": None,
        },
        PROFILE_A: {
            "profile_id": PROFILE_A,
            "profile_kind": "research_filter",
            "status": "eligible" if convex_eligible else "abstain",
            "abstention_reason": None if convex_eligible else "NO_ELIGIBLE_CONTRACT",
            "definition": {
                "dte_calendar_days": {"minimum": 30, "maximum": 180},
                "otm_pct": {"minimum": 5.0, "maximum": 20.0},
                "absolute_delta": {"minimum": 0.10, "maximum": 0.45},
                "spread_pct_maximum": 15.0,
                "prior_session_open_interest_minimum": 100,
                "quote_browser_eligible_required": True,
                "research_only_not_reconstructed_competitor_rule": True,
                "ranking_inputs": [],
            },
            "within_profile_order": [
                "contract_id ASC",
                "expiration ASC",
                "strike ASC",
            ],
            "evaluated_contract_count": len(contracts),
            "filter_pass_counts": {
                "browser_quote_fresh_valid": len(contracts),
                "dte_30_180": len(contracts),
                "otm_5_20_pct": len(contracts),
                "absolute_delta_0_10_0_45": len(contracts),
                "spread_pct_lte_15": len(contracts),
                "prior_session_oi_gte_100": len(contracts),
            },
            "eligible_contract_ids": convex_eligible,
            "authority": w0a.authority_block(),
        },
    }
    payload = {
        "schema": w0a.SCHEMA,
        "packet_id": None,
        "root": root,
        "session": {
            "date": SESSION,
            "open_at": "2026-08-07T13:30:00.000000Z",
            "close_at": "2026-08-07T20:00:00.000000Z",
            "early_close": False,
            "snapshot_bucket": BUCKET,
            "bucket_at": "2026-08-07T19:45:00.000000Z",
            "cadence_minutes": 15,
        },
        "clocks": {
            "vendor_snapshot_ts_min": "2026-08-07T19:59:00.000000Z",
            "vendor_snapshot_ts_max": "2026-08-07T19:59:00.000000Z",
            "vendor_naive_clock_interpretation": "America/New_York",
            "builder_observed_at": "2026-08-07T19:59:30.000000Z",
            "available_at": AVAILABLE,
            "browser_freshness_limit_minutes": 20,
        },
        "source_receipt": {
            "source_family": "chain_snapshot",
            "private_raw_parquet_published": False,
            "chain": {
                "logical_key": f"chain_snapshots/{root}/{SESSION}.parquet",
                "bucket_sha256": "1" * 64,
                "bucket_row_count": len(contracts),
            },
            "prior_session_open_interest": {
                "logical_key": f"chain_snapshots/{root}/{SESSION}_oi.parquet",
                "projection_sha256": "2" * 64,
                "row_count": len(contracts),
                "usable_row_count": len(contracts),
                "expired_excluded_row_count": 0,
                "vintage_session": "2026-08-06",
                "vintage_derivation": "previous_real_nyse_session",
            },
        },
        "coverage": {
            "complete_root_bucket": True,
            "source_contract_count": len(contracts),
            "browser_eligible_contract_count": len(contracts),
            "projected_contract_count": len(contracts),
            "quote_rejection_counts": {},
        },
        "profiles": governed_profiles,
        "contracts": contracts,
        "limitations": {
            "bid_ask_depth": "unavailable",
            "capacity_assessed": False,
            "underlying_selection": "not_in_scope",
            "execution_quote_polling": "not_in_scope",
            "issuance": "not_authorized",
        },
        "authority": w0a.authority_block(),
    }
    unsigned = dict(payload)
    unsigned.pop("packet_id")
    payload["packet_id"] = (
        "packet:uchain:" + sha256(w0a.canonical_json_bytes(unsigned)).hexdigest()
    )
    return payload, identities


def _completion_ledger(
    packets: list[dict],
    *,
    availability_at: str = AVAILABLE,
) -> bytes:
    roots = tuple(packet["root"] for packet in packets)
    results: list[dict] = []
    for ordinal, packet in enumerate(packets, start=1):
        chain = packet["source_receipt"]["chain"]
        oi = packet["source_receipt"]["prior_session_open_interest"]
        bucket_rows = chain["bucket_row_count"]
        oi_rows = max(oi["row_count"], 1)
        results.append({
            "root": packet["root"],
            "rows": bucket_rows,
            "total_rows": bucket_rows,
            "oi_rows": oi_rows,
            "oi_total_rows": oi_rows,
            "error": None,
            "completion_errors": [],
            "bucket_rows": bucket_rows,
            "bucket_content_sha256": f"{ordinal + 2:x}" * 64,
            "parquet_sha256": f"{ordinal + 4:x}" * 64,
            "oi_parquet_sha256": f"{ordinal + 6:x}" * 64,
            "first_vendor_min_at": packet["clocks"]["vendor_snapshot_ts_min"],
            "first_vendor_max_at": packet["clocks"]["vendor_snapshot_ts_max"],
            "first_prebucket_rows": 0,
            "first_at_or_after_bucket_rows": bucket_rows,
            "second_clock_matched_rows": bucket_rows,
            "second_clock_unmatched_rows": 0,
            "quarantined": [],
            "oi_quarantined": [],
        })
    completion_summary = completion.build_completion_summary(roots, results)
    intent = completion._with_receipt_id({
        "schema": completion.SCHEMA_ID,
        "kind": "intent",
        "bucket_id": completion.bucket_id(SESSION, BUCKET),
        "session_date": SESSION,
        "bucket": BUCKET,
        "cadence_min": 15,
        "roots": list(roots),
        "preexisting_target_roots": [],
        "intent_at": "2026-08-07T19:46:00.000000Z",
    })
    decision = completion._with_receipt_id({
        "schema": completion.SCHEMA_ID,
        "kind": "decision",
        "bucket_id": intent["bucket_id"],
        "session_date": SESSION,
        "bucket": BUCKET,
        "intent_receipt_id": intent["receipt_id"],
        "intent_sha256": sha256(completion.canonical_bytes(intent)).hexdigest(),
        "decision_at": "2026-08-07T19:59:30.000000Z",
        "completion": completion_summary,
    })
    availability = completion._with_receipt_id({
        "schema": completion.SCHEMA_ID,
        "kind": "availability",
        "bucket_id": intent["bucket_id"],
        "session_date": SESSION,
        "bucket": BUCKET,
        "intent_receipt_id": intent["receipt_id"],
        "decision_receipt_id": decision["receipt_id"],
        "decision_at": decision["decision_at"],
        "availability_at": availability_at,
    })
    body = b"".join(
        completion.canonical_bytes(record) + b"\n"
        for record in (intent, decision, availability)
    )
    states = completion.decode_ledger(body, Path(f"{SESSION}.jsonl"))
    assert len(states) == 1 and states[0].status == "complete"
    return body


def _bundle(
    specs: dict[str, list[tuple[str, str, str, tuple[str, ...]]]] | None = None,
) -> dict:
    specs = specs or {
        "SPY": [("2026-09-18", "C", "100", (PROFILE_A, PROFILE_B))],
        "QQQ": [("2026-10-16", "P", "500.125", (PROFILE_A,))],
    }
    packets: list[dict] = []
    objects: dict[str, bytes] = {}
    receipts: dict[str, dict] = {}
    identities: dict[tuple[str, str, str], str] = {}
    for root, rows in specs.items():
        packet, packet_ids = _packet(root, rows)
        body = w0a.canonical_json_bytes(packet)
        key = w0a.packet_key(root, SESSION, BUCKET)
        receipt = w0a.object_receipt(key, body, packet)
        packets.append(packet)
        objects[key] = body
        receipts[root] = receipt
        for (profile, strike), contract_id in packet_ids.items():
            identities[(root, profile, strike)] = contract_id
    index = w0a.build_index(packets, receipts)
    return {
        "index": index,
        "index_bytes": w0a.canonical_json_bytes(index),
        "completion_ledger_bytes": _completion_ledger(packets),
        "packets": packets,
        "objects": objects,
        "identities": identities,
    }


def _rewrite_packet(bundle: dict, root: str, mutation) -> dict:
    rewritten = deepcopy(bundle)
    packets: list[dict] = []
    receipts: dict[str, dict] = {}
    objects: dict[str, bytes] = {}
    for index_row in bundle["index"]["roots"]:
        key = index_row["object"]["key"]
        packet = json.loads(bundle["objects"][key])
        if packet["root"] == root:
            mutation(packet)
            unsigned = dict(packet)
            unsigned.pop("packet_id")
            packet["packet_id"] = (
                "packet:uchain:"
                + sha256(w0a.canonical_json_bytes(unsigned)).hexdigest()
            )
        body = w0a.canonical_json_bytes(packet)
        packets.append(packet)
        objects[key] = body
        receipts[packet["root"]] = w0a.object_receipt(key, body, packet)
    index = w0a.build_index(packets, receipts)
    rewritten["index"] = index
    rewritten["index_bytes"] = w0a.canonical_json_bytes(index)
    rewritten["objects"] = objects
    rewritten["packets"] = packets
    return rewritten


def _inputs(bundle: dict, rows: list[tuple[str, str, str]] | None = None) -> list[dict]:
    rows = rows or [("SPY", PROFILE_A, "100"), ("QQQ", PROFILE_A, "500.125")]
    return [
        {
            "root": root,
            "profile_id": profile,
            "contract_id": bundle["identities"][(root, profile, strike)],
        }
        for root, profile, strike in rows
    ]


def _loader(bundle: dict):
    return lambda key: bundle["objects"][key]


def _plan(bundle: dict, inputs: list[dict] | None = None) -> dict:
    return focused.prepare_attempt(
        inputs or _inputs(bundle),
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
    )


def _frames(decision: dict, *, snapshot="2026-08-07T15:59:00") -> dict[str, pd.DataFrame]:
    grouped: dict[str, list[dict]] = {
        root: [] for root in decision["preflight"]["unique_roots"]
    }
    seen: set[tuple[str, str, str, int]] = set()
    for contract in decision["requested_contracts"]:
        key = (
            contract["root"], contract["expiration"], contract["right"],
            contract["strike_millis"],
        )
        if key in seen:
            continue
        seen.add(key)
        grouped[contract["root"]].append({
            "root": contract["root"],
            "expiration": pd.Timestamp(contract["expiration"]),
            "strike": contract["strike_millis"] / 1000,
            "right": contract["right"],
            "snapshot_ts": pd.Timestamp(snapshot),
            "bid": 1.25,
            "ask": 1.35,
            "delta": 0.5,
            "underlying_price": 100.0,
        })
    return {root: pd.DataFrame(rows) for root, rows in grouped.items()}


class Clock:
    def __init__(self, *values: datetime):
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        if not self.values:
            raise AssertionError("clock exhausted")
        return self.values.pop(0)


class S3Error(RuntimeError):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class FakeR2:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.puts: list[dict] = []
        self.corrupt_reads: set[str] = set()
        self.length_delta: dict[str, int] = {}
        self.content_types: dict[str, str] = {}
        self.cache_controls: dict[str, str] = {}

    def seed(self, key: str, body: bytes, metadata: dict[str, str] | None = None):
        self.objects[key] = (body, metadata or {"sha256": sha256(body).hexdigest()})

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise S3Error("NoSuchKey", 404)
        body, metadata = self.objects[Key]
        returned = body + b"x" if Key in self.corrupt_reads else body
        return {
            "Body": io.BytesIO(returned),
            "ContentLength": len(returned) + self.length_delta.get(Key, 0),
            "Metadata": dict(metadata),
            "ContentType": self.content_types.get(Key, "application/json"),
            "CacheControl": self.cache_controls.get(Key, "private, no-store"),
        }

    def put_object(self, **kwargs):
        self.puts.append(dict(kwargs))
        key = kwargs["Key"]
        if key in self.objects:
            raise S3Error("PreconditionFailed", 412)
        self.objects[key] = (bytes(kwargs["Body"]), dict(kwargs["Metadata"]))
        return {}


def _seed_record(client: FakeR2, record: dict) -> None:
    key = record["publication"][f"{record['record_type']}_key"]
    body = focused.canonical_json_bytes(record)
    client.seed(key, body, {
        "sha256": sha256(body).hexdigest(),
        "schema": record["schema"],
        "record-type": record["record_type"],
        "attempt-id": record["attempt_id"],
        "visibility": "private",
        "immutable": "true",
    })


def test_schema_is_valid_and_discriminates_decision_and_receipt() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    bundle = _bundle()
    decision = focused.build_decision(_plan(bundle), decided_at=T0)
    receipt = focused.build_source_receipt(decision, _frames(decision), verified_at=T1)
    assert _schema_errors(decision) == []
    assert _schema_errors(receipt) == []
    assert decision["record_type"] == "decision"
    assert receipt["record_type"] == "receipt"
    assert not VALIDATOR.is_valid({**decision, "record_type": "receipt"})


def test_exact_bytes_are_deterministic_and_all_authority_is_false() -> None:
    bundle = _bundle()
    first_plan = _plan(bundle)
    second_plan = _plan(bundle)
    first_decision = focused.build_decision(first_plan, decided_at=T0)
    second_decision = focused.build_decision(second_plan, decided_at=T0)
    first_receipt = focused.build_source_receipt(
        first_decision, _frames(first_decision), verified_at=T1
    )
    second_receipt = focused.build_source_receipt(
        second_decision, _frames(second_decision), verified_at=T1
    )
    assert focused.canonical_json_bytes(first_decision) == focused.canonical_json_bytes(second_decision)
    assert focused.canonical_json_bytes(first_receipt) == focused.canonical_json_bytes(second_receipt)
    assert not any(first_decision["authority"].values())
    assert not any(first_receipt["authority"].values())
    assert first_receipt["quote_semantics"] == focused.quote_semantics()
    assert all(value is False for key, value in first_receipt["quote_semantics"].items() if key not in {"endpoint", "label"})


@pytest.mark.parametrize("count", [0, 13])
def test_inputs_are_bounded_without_truncation(count: int) -> None:
    bundle = _bundle()
    row = _inputs(bundle)[:1][0]
    with pytest.raises(focused.FocusedQuoteError, match="1..12"):
        focused.normalize_inputs([dict(row, contract_id=f"contract:uchain:{i:064x}") for i in range(count)])


@pytest.mark.parametrize(
    "raw",
    [
        {"root": "SPY", "profile_id": PROFILE_A},
        {"root": "SPY", "profile_id": PROFILE_A, "contract_id": "contract:uchain:" + "a" * 64, "rank": 1},
    ],
)
def test_input_keys_are_exact(raw: dict) -> None:
    with pytest.raises(focused.FocusedQuoteError, match="exactly"):
        focused.normalize_inputs([raw])


def test_duplicate_explicit_input_is_rejected_not_deduplicated() -> None:
    bundle = _bundle()
    row = _inputs(bundle)[:1][0]
    with pytest.raises(focused.FocusedQuoteError, match="duplicate"):
        focused.normalize_inputs([row, row])


def test_input_order_and_first_root_order_are_preserved_exactly() -> None:
    bundle = _bundle()
    inputs = _inputs(bundle, [
        ("QQQ", PROFILE_A, "500.125"),
        ("SPY", PROFILE_B, "100"),
        ("SPY", PROFILE_A, "100"),
    ])
    plan = _plan(bundle, inputs)
    assert [row["ordinal"] for row in plan["inputs"]] == [1, 2, 3]
    assert [row["root"] for row in plan["inputs"]] == ["QQQ", "SPY", "SPY"]
    assert plan["preflight"]["unique_roots"] == ["QQQ", "SPY"]
    assert [row["root"] for row in plan["w0a"]["packets"]] == ["QQQ", "SPY"]
    assert [row["root"] for row in plan["requested_contracts"]] == ["QQQ", "SPY", "SPY"]


def test_exact_w0a_index_and_every_indexed_packet_are_attested_once() -> None:
    bundle = _bundle()
    plan = _plan(bundle)
    index = plan["w0a"]["index"]
    assert index == {
        "key": focused.W0A_INDEX_KEY,
        "sha256": sha256(bundle["index_bytes"]).hexdigest(),
        "bytes": len(bundle["index_bytes"]),
        "index_id": bundle["index"]["index_id"],
        "epoch": f"{SESSION}/{BUCKET}",
    }
    assert len(plan["w0a"]["packets"]) == 2
    for receipt in plan["w0a"]["packets"]:
        body = bundle["objects"][receipt["key"]]
        assert receipt["sha256"] == sha256(body).hexdigest()
        assert receipt["bytes"] == len(body)
        assert receipt["epoch"] == index["epoch"]


def test_exact_producer_complete_state_is_attested_in_semantic_attempt() -> None:
    bundle = _bundle()
    plan = _plan(bundle)
    state = completion.decode_ledger(
        bundle["completion_ledger_bytes"], Path(f"{SESSION}.jsonl")
    )[0]
    records = (state.intent, state.decision, state.availability)
    assert all(record is not None for record in records)
    record_bodies = [completion.canonical_bytes(record) for record in records]
    state_body = b"".join(body + b"\n" for body in record_bodies)
    attestation = plan["w0a"]["completion"]
    assert attestation["ledger_key"] == (
        f"chain_snapshots/_bucket_receipts/{SESSION}.jsonl"
    )
    assert attestation["state"] == "complete"
    assert attestation["state_sha256"] == sha256(state_body).hexdigest()
    assert attestation["state_bytes"] == len(state_body)
    assert attestation["bucket_id"] == state.intent["bucket_id"]
    assert attestation["root_count"] == bundle["index"]["root_count"]
    assert set(attestation["roots"]) == {
        row["root"] for row in bundle["index"]["roots"]
    }
    assert attestation["intent"] == {
        "receipt_id": state.intent["receipt_id"],
        "sha256": sha256(record_bodies[0]).hexdigest(),
        "intent_at": state.intent["intent_at"],
    }
    assert attestation["decision"]["receipt_id"] == state.decision["receipt_id"]
    assert attestation["decision"]["sha256"] == sha256(record_bodies[1]).hexdigest()
    assert attestation["availability"] == {
        "receipt_id": state.availability["receipt_id"],
        "sha256": sha256(record_bodies[2]).hexdigest(),
        "availability_at": state.availability["availability_at"],
    }


def test_preparation_loads_every_index_packet_before_focused_poll() -> None:
    bundle = _bundle()
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    loads: list[str] = []

    def loader(key: str) -> bytes:
        loads.append(key)
        return bundle["objects"][key]

    plan = focused.prepare_attempt(
        inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=loader,
    )
    assert loads == [row["object"]["key"] for row in bundle["index"]["roots"]]
    assert plan["preflight"]["unique_roots"] == ["SPY"]


def test_direct_preparation_has_no_completion_ledger_bypass() -> None:
    bundle = _bundle()
    with pytest.raises(TypeError, match="completion_ledger_bytes"):
        focused.prepare_attempt(
            _inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            packet_loader=_loader(bundle),
        )


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ("torn", "completion ledger is invalid"),
        ("decision_only", "lacks one exact producer-complete"),
        ("root_set", "index roots do not exactly match"),
        ("row_count", "bucket row count mismatch"),
        ("vendor_clock", "first-vendor clock mismatch"),
        ("availability", "predates producer availability"),
    ],
)
def test_completion_ledger_mismatch_fails_before_state_or_provider(
    tmp_path: Path,
    kind: str,
    match: str,
) -> None:
    bundle = _bundle()
    ledger = bundle["completion_ledger_bytes"]
    if kind == "torn":
        ledger = ledger[:-1]
    elif kind == "decision_only":
        ledger = b"\n".join(ledger.splitlines()[:2]) + b"\n"
    elif kind == "root_set":
        ledger = _completion_ledger(bundle["packets"][:1])
    elif kind == "row_count":
        completion_packets = deepcopy(bundle["packets"])
        completion_packets[0]["source_receipt"]["chain"]["bucket_row_count"] += 1
        ledger = _completion_ledger(completion_packets)
    elif kind == "vendor_clock":
        completion_packets = deepcopy(bundle["packets"])
        completion_packets[0]["clocks"]["vendor_snapshot_ts_min"] = (
            "2026-08-07T19:58:00.000000Z"
        )
        completion_packets[0]["clocks"]["vendor_snapshot_ts_max"] = (
            "2026-08-07T19:58:00.000000Z"
        )
        ledger = _completion_ledger(completion_packets)
    else:
        ledger = _completion_ledger(
            bundle["packets"],
            availability_at="2026-08-07T20:00:00.000001Z",
        )
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    state_root = tmp_path / "state"
    with pytest.raises(focused.W0AAttestationError, match=match):
        builder.run_attempt(
            inputs=_inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=ledger,
            packet_loader=_loader(bundle),
            state_root=state_root,
            snapshot_greeks=provider,
            clock=Clock(T0, T1),
        )
    assert calls == 0
    assert not state_root.exists()


def test_private_immutable_attempt_keys_have_no_current_or_discovery_pointer() -> None:
    plan = _plan(_bundle())
    publication = plan["publication"]
    assert publication["visibility"] == "private"
    assert publication["immutable_only"] is True
    assert publication["current_pointer"] is False
    assert publication["discovery_pointer"] is False
    assert "/attempts/" in publication["decision_key"]
    assert publication["decision_key"].endswith("/decision.json")
    assert publication["receipt_key"].endswith("/receipt.json")


def test_noncanonical_index_bytes_fail_before_decision() -> None:
    bundle = _bundle()
    with pytest.raises(focused.W0AAttestationError, match="not canonical"):
        focused.prepare_attempt(
            _inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"] + b" ",
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
        )


def test_index_schema_and_identity_fail_closed() -> None:
    bundle = _bundle()
    for field, value, match in [
        ("schema", "wrong/v1", "schema"),
        ("index_id", "index:uchain:" + "0" * 64, "index_id"),
        ("epoch", "2026-08-07/15:44", "epoch"),
    ]:
        payload = deepcopy(bundle["index"])
        payload[field] = value
        if field == "epoch":
            unsigned = dict(payload)
            unsigned.pop("index_id")
            payload["index_id"] = (
                "index:uchain:" + sha256(w0a.canonical_json_bytes(unsigned)).hexdigest()
            )
        with pytest.raises(focused.W0AAttestationError, match=match):
            focused.prepare_attempt(
                _inputs(bundle),
                index_key=focused.W0A_INDEX_KEY,
                index_bytes=w0a.canonical_json_bytes(payload),
                completion_ledger_bytes=bundle["completion_ledger_bytes"],
                packet_loader=_loader(bundle),
            )


def test_packet_digest_and_byte_count_fail_closed_before_decision() -> None:
    bundle = _bundle()
    key = next(iter(bundle["objects"]))
    damaged = dict(bundle["objects"])
    damaged[key] = damaged[key] + b"x"
    with pytest.raises(focused.W0AAttestationError, match="byte count"):
        focused.prepare_attempt(
            _inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=lambda object_key: damaged[object_key],
        )


@pytest.mark.parametrize("field", ["eligible_contract_ids", "profile_matches"])
def test_w0a_identity_arrays_reject_unhashable_or_malformed_members(field: str) -> None:
    bundle = _bundle()

    def corrupt(packet: dict) -> None:
        if field == "eligible_contract_ids":
            packet["profiles"][PROFILE_A][field] = [[
                bundle["identities"][("SPY", PROFILE_A, "100")]
            ]]
        else:
            packet["contracts"][0][field] = [[PROFILE_A]]

    damaged = _rewrite_packet(bundle, "SPY", corrupt)
    with pytest.raises(focused.W0AAttestationError, match="schema validation"):
        _plan(damaged)


def test_w0a_authority_requires_the_exact_six_false_keys() -> None:
    bundle = _bundle()
    bad_index = deepcopy(bundle["index"])
    bad_index["authority"] = {"rank_authority": False}
    unsigned_index = dict(bad_index)
    unsigned_index.pop("index_id")
    bad_index["index_id"] = (
        "index:uchain:"
        + sha256(w0a.canonical_json_bytes(unsigned_index)).hexdigest()
    )
    with pytest.raises(focused.W0AAttestationError, match="schema validation"):
        focused.prepare_attempt(
            _inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=w0a.canonical_json_bytes(bad_index),
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
        )

    def corrupt_packet(packet: dict) -> None:
        packet["authority"] = {
            **w0a.authority_block(),
            "neural_web_authority": False,
        }

    damaged = _rewrite_packet(bundle, "SPY", corrupt_packet)
    with pytest.raises(focused.W0AAttestationError, match="schema validation"):
        _plan(damaged)


def test_standalone_w0a_index_schema_accepts_build_index_output() -> None:
    schema = focused.strict_json_object(focused.W0A_INDEX_SCHEMA_PATH.read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(_bundle()["index"])) == []


def test_reidentified_schema_invalid_w0a_index_and_packet_fail_before_plan() -> None:
    bundle = _bundle()
    bad_index = deepcopy(bundle["index"])
    bad_index["unexpected_discovery_alias"] = "current.json"
    unsigned_index = dict(bad_index)
    unsigned_index.pop("index_id")
    bad_index["index_id"] = (
        "index:uchain:"
        + sha256(w0a.canonical_json_bytes(unsigned_index)).hexdigest()
    )
    loads = 0

    def forbidden_loader(key: str) -> bytes:
        nonlocal loads
        loads += 1
        return bundle["objects"][key]

    with pytest.raises(focused.W0AAttestationError, match="index schema validation"):
        focused.prepare_attempt(
            _inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=w0a.canonical_json_bytes(bad_index),
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=forbidden_loader,
        )
    assert loads == 0

    damaged = _rewrite_packet(
        bundle,
        "SPY",
        lambda packet: packet.pop("source_receipt"),
    )
    packet_key = next(
        key for key in damaged["objects"] if "/SPY/" in key
    )
    packet = json.loads(damaged["objects"][packet_key])
    packet_schema = focused.strict_json_object(
        focused.W0A_PACKET_SCHEMA_PATH.read_bytes()
    )
    assert not Draft202012Validator(
        packet_schema, format_checker=FormatChecker()
    ).is_valid(packet)
    with pytest.raises(focused.W0AAttestationError, match="packet SPY schema validation"):
        _plan(damaged)


@pytest.mark.parametrize(
    "kind,path_attribute",
    [
        ("index", "W0A_INDEX_SCHEMA_PATH"),
        ("packet", "W0A_PACKET_SCHEMA_PATH"),
    ],
)
def test_w0a_schema_unavailability_fails_before_a_decision(
    kind: str,
    path_attribute: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    focused._W0A_VALIDATORS.clear()
    monkeypatch.setattr(focused, path_attribute, tmp_path / f"missing-{kind}.json")
    try:
        with pytest.raises(focused.W0AAttestationError, match="schema unavailable"):
            _plan(bundle)
    finally:
        focused._W0A_VALIDATORS.clear()


def test_unknown_profile_or_noneligible_contract_fails_closed() -> None:
    bundle = _bundle()
    input_row = _inputs(bundle)[:1][0]
    with pytest.raises(focused.W0AAttestationError, match="profile"):
        _plan(bundle, [{**input_row, "profile_id": "unknown_profile_v1"}])
    with pytest.raises(focused.W0AAttestationError, match="not explicitly eligible"):
        _plan(bundle, [{**input_row, "contract_id": "contract:uchain:" + "f" * 64}])


def test_non_millistrike_preflight_abstains_without_provider_call(tmp_path: Path) -> None:
    bundle = _bundle({
        "SPY": [("2026-09-18", "C", "100.0005", (PROFILE_A,))],
    })
    calls: list[tuple] = []
    receipt = builder.run_attempt(
        inputs=_inputs(bundle, [("SPY", PROFILE_A, "100.0005")]),
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=lambda *args, **kwargs: calls.append((args, kwargs)),
        clock=Clock(T0, T0),
    )
    assert calls == []
    assert receipt["status"] == "abstain"
    assert receipt["abstention_reason"] == "NON_MILLISTRIKE_CONTRACT"
    assert receipt["quotes"] == []


def test_occ_roundtrip_failure_preflight_abstains_without_provider_call(tmp_path: Path) -> None:
    bundle = _bundle({
        "BRK.B": [("2026-09-18", "C", "100", (PROFILE_A,))],
    })
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    receipt = builder.run_attempt(
        inputs=_inputs(bundle, [("BRK.B", PROFILE_A, "100")]),
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0, T0),
    )
    assert calls == 0
    assert receipt["abstention_reason"] == "OCC_ROUNDTRIP_FAILED"


def test_one_existing_first_order_full_chain_call_per_root_and_local_grouping(tmp_path: Path) -> None:
    bundle = _bundle()
    inputs = _inputs(bundle, [
        ("QQQ", PROFILE_A, "500.125"),
        ("SPY", PROFILE_B, "100"),
        ("SPY", PROFILE_A, "100"),
    ])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frames = _frames(decision)
    calls: list[tuple[str, str]] = []

    def provider(root: str, *, order: str):
        calls.append((root, order))
        return frames[root]

    receipt = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0, T1),
    )
    assert calls == [("QQQ", "first"), ("SPY", "first")]
    assert receipt["status"] == "complete"
    assert [row["ordinal"] for row in receipt["quotes"]] == [1, 2, 3]
    assert [row["root"] for row in receipt["quotes"]] == ["QQQ", "SPY", "SPY"]


def test_vendor_snapshot_label_never_claims_execution_provenance(tmp_path: Path) -> None:
    bundle = _bundle()
    decision = focused.build_decision(_plan(bundle), decided_at=T0)
    frames = _frames(decision)
    for frame in frames.values():
        frame["bid_size"] = 999
        frame["ask_size"] = 888
        frame["bid_exchange"] = "X"
        frame["ask_exchange"] = "Y"
        frame["bid_condition"] = "A"
        frame["ask_condition"] = "B"
    receipt = focused.build_source_receipt(decision, frames, verified_at=T1)
    encoded = focused.canonical_json_bytes(receipt)
    assert receipt["quote_semantics"]["label"] == "vendor_snapshot_bid_ask"
    assert b"bid_size" not in encoded
    assert b"ask_size" not in encoded
    assert b"exchange" not in encoded
    assert b'"bid_condition"' not in encoded
    assert b'"ask_condition"' not in encoded
    assert b"trade_quote" in encoded  # the explicit false anti-splice claim
    assert receipt["quote_semantics"]["trade_quote_spliced"] is False


@pytest.mark.parametrize(
    "kind",
    [
        "none",
        "empty",
        "missing_columns",
        "duplicate_columns",
        "non_scalar_identity",
        "non_scalar_quote",
        "missing_row",
        "duplicate",
        "duplicate_mixed",
        "crossed",
        "future",
    ],
)
def test_empty_malformed_or_ambiguous_source_is_one_honest_abstention(kind: str) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])), decided_at=T0
    )
    frame = _frames(decision)["SPY"]
    if kind == "none":
        value: object = None
    elif kind == "empty":
        value = frame.iloc[0:0]
    elif kind == "missing_columns":
        value = frame.drop(columns=["bid"])
    elif kind == "duplicate_columns":
        value = pd.concat([frame, frame[["root"]]], axis=1)
    elif kind == "non_scalar_identity":
        value = frame.astype({"right": "object"})
        value.at[0, "right"] = ["C"]
    elif kind == "non_scalar_quote":
        value = frame.astype({"bid": "object"})
        value.at[0, "bid"] = [1.25]
    elif kind == "missing_row":
        value = frame.assign(strike=101.0)
    elif kind == "duplicate":
        value = pd.concat([frame, frame.assign(ask=1.36)], ignore_index=True)
    elif kind == "duplicate_mixed":
        value = pd.concat([frame, frame.assign(bid=2.0, ask=1.0)], ignore_index=True)
    elif kind == "crossed":
        value = frame.assign(bid=2.0, ask=1.0)
    else:
        value = frame.assign(snapshot_ts=pd.Timestamp("2026-08-07T16:01:00"))
    receipt = focused.build_source_receipt(decision, {"SPY": value}, verified_at=T0)
    assert receipt["status"] == "abstain"
    assert receipt["abstention_reason"] == "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW"
    assert receipt["quotes"] == []
    assert "trade" not in receipt["abstention_reason"].lower()


def test_freshness_is_computed_at_verified_availability_exactly() -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])), decided_at=T0
    )
    receipt = focused.build_source_receipt(
        decision, _frames(decision, snapshot="2026-08-07T15:59:30.123456"),
        verified_at=T0,
    )
    freshness = receipt["quotes"][0]["vendor_snapshot"]["freshness"]
    assert freshness["verified_available_at"] == focused._iso_utc(T0)
    assert freshness["age_microseconds"] == 29_876_544
    assert freshness["basis"] == "verified_available_at_minus_vendor_snapshot_ts"


def test_structurally_valid_prior_close_can_be_complete_without_freshness_claim() -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])),
        decided_at=T0,
    )
    receipt = focused.build_source_receipt(
        decision,
        _frames(decision, snapshot="2026-08-06T15:59:00"),
        verified_at=T0,
    )
    assert receipt["status"] == "complete"
    assert receipt["quote_semantics"]["current"] is False
    assert receipt["quote_semantics"]["live"] is False
    assert (
        receipt["quotes"][0]["vendor_snapshot"]["freshness"]["age_microseconds"]
        == 86_460_000_000
    )


def test_verified_availability_clock_is_captured_after_row_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])),
        decided_at=T0,
    )
    events: list[str] = []
    original = focused._source_snapshot_clock

    def observed_snapshot(value):
        events.append("row-normalized")
        return original(value)

    def verified_clock() -> datetime:
        events.append("availability-verified")
        return T1

    monkeypatch.setattr(focused, "_source_snapshot_clock", observed_snapshot)
    receipt = focused.build_source_receipt(
        decision,
        _frames(decision),
        verified_at=verified_clock,
    )
    assert events == ["row-normalized", "availability-verified"]
    assert receipt["verified_available_at"] == focused._iso_utc(T1)


def test_provider_exception_becomes_abstention_and_never_repolls(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    calls = 0

    def uncertain(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("synthetic provider uncertainty")

    first = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=uncertain,
        clock=Clock(T0, T1),
    )
    second = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=uncertain,
        clock=Clock(T1),
    )
    assert calls == 1
    assert first == second
    assert first["abstention_reason"] == "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW"


def test_one_root_failure_does_not_skip_or_substitute_another_explicit_root(tmp_path: Path) -> None:
    bundle = _bundle()
    inputs = _inputs(bundle)
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frames = _frames(decision)
    calls: list[tuple[str, str]] = []

    def provider(root: str, *, order: str):
        calls.append((root, order))
        if root == "SPY":
            raise TimeoutError("synthetic first-root uncertainty")
        return frames[root]

    receipt = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0, T1),
    )
    assert calls == [("SPY", "first"), ("QQQ", "first")]
    assert receipt["status"] == "abstain"
    assert receipt["abstention_reason"] == "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW"
    assert receipt["quotes"] == []


def test_existing_decision_never_repolls_and_recovers_only_at_300_seconds(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    plan = _plan(bundle, inputs)
    decision = focused.build_decision(plan, decided_at=T0)
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    builder._write_immutable(
        attempt_dir / "decision.json", focused.canonical_json_bytes(decision)
    )
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.AttemptPendingError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0 + timedelta(seconds=299, microseconds=999999)),
        )
    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0 + timedelta(seconds=300)),
    )
    assert calls == 0
    assert recovered["abstention_reason"] == "RECOVERY_DEADLINE_EXCEEDED"
    assert recovered["recovery"]["recovered_without_repoll"] is True


def test_recovery_clock_before_durable_decision_is_rejected(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    builder._write_immutable(attempt_dir / "decision.json", focused.canonical_json_bytes(decision))
    with pytest.raises(focused.FocusedQuoteClockError, match="precedes"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not poll"),
            clock=Clock(T0 - timedelta(seconds=1)),
        )


def test_naive_decision_clock_fails_before_provider_call(tmp_path: Path) -> None:
    bundle = _bundle()
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(focused.FocusedQuoteClockError, match="timezone-aware"):
        builder.run_attempt(
            inputs=_inputs(bundle),
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(datetime(2026, 8, 7, 20, 0)),
        )
    assert calls == 0


def test_post_provider_clock_failure_never_authorizes_a_repoll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frame = _frames(decision)["SPY"]
    calls = 0

    def provider(root, *, order):
        nonlocal calls
        calls += 1
        return frame

    with pytest.raises(focused.FocusedQuoteClockError, match="timezone-aware"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0, datetime(2026, 8, 7, 20, 1)),
        )
    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0 + timedelta(seconds=300)),
    )
    assert calls == 1
    assert recovered["abstention_reason"] == "RECOVERY_DEADLINE_EXCEEDED"


def test_per_attempt_flock_serializes_hostile_concurrency_to_one_poll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frame = _frames(decision)["SPY"]
    count_lock = threading.Lock()
    calls = 0

    def provider(root, *, order):
        nonlocal calls
        with count_lock:
            calls += 1
        time.sleep(0.15)
        return frame

    def invoke():
        return builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=lambda: T0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert calls == 1
    assert results[0] == results[1]
    assert results[0]["status"] == "complete"


def test_attempt_directory_symlink_cannot_escape_state_root(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    digest = decision["attempt_id"].rsplit(":", 1)[1]
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    state_root.mkdir(mode=0o700)
    outside.mkdir()
    (state_root / digest).symlink_to(outside, target_is_directory=True)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.FocusedQuoteRuntimeError, match="symlink or special"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=state_root,
            snapshot_greeks=provider,
            clock=Clock(T0, T1),
        )
    assert calls == 0
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("artifact_name", ["decision.json", "receipt.json"])
def test_local_artifact_symlink_is_never_adopted(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    digest = decision["attempt_id"].rsplit(":", 1)[1]
    attempt_dir = tmp_path / digest
    attempt_dir.mkdir(mode=0o700)
    if artifact_name == "receipt.json":
        builder._write_immutable(
            attempt_dir / "decision.json",
            focused.canonical_json_bytes(decision),
        )
    outside = tmp_path / f"outside-{artifact_name}"
    outside.write_bytes(
        focused.canonical_json_bytes(decision)
        if artifact_name == "decision.json"
        else b"not an adoptable receipt\n"
    )
    (attempt_dir / artifact_name).symlink_to(outside)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.FocusedQuoteRuntimeError, match="symlink, special file, or hard link"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0, T1),
        )
    assert calls == 0


def test_special_and_hardlinked_local_state_fail_closed_before_poll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    digest = decision["attempt_id"].rsplit(":", 1)[1]

    special_root = tmp_path / "special"
    special_root.mkdir(mode=0o700)
    (special_root / digest).write_bytes(b"not a directory")
    with pytest.raises(builder.FocusedQuoteRuntimeError, match="symlink or special"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=special_root,
            snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not poll"),
            clock=Clock(T0, T1),
        )

    linked_root = tmp_path / "linked"
    linked_attempt = linked_root / digest
    linked_root.mkdir(mode=0o700)
    linked_attempt.mkdir(mode=0o700)
    outside = tmp_path / "outside-decision.json"
    outside.write_bytes(focused.canonical_json_bytes(decision))
    os.link(outside, linked_attempt / "decision.json")
    with pytest.raises(builder.FocusedQuoteRuntimeError, match="hard link"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=linked_root,
            snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not poll"),
            clock=Clock(T0, T1),
        )


def test_lock_symlink_is_rejected_before_decision_or_poll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    digest = decision["attempt_id"].rsplit(":", 1)[1]
    attempt_dir = tmp_path / digest
    attempt_dir.mkdir(mode=0o700)
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"outside")
    (attempt_dir / ".attempt.lock").symlink_to(outside)

    with pytest.raises(builder.FocusedQuoteRuntimeError, match="confined per-attempt state"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not poll"),
            clock=Clock(T0, T1),
        )
    assert not (attempt_dir / "decision.json").exists()


def test_replacing_lock_inode_cannot_create_a_second_provider_holder(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    digest = decision["attempt_id"].rsplit(":", 1)[1]
    frame = _frames(decision)["SPY"]
    provider_started = threading.Event()
    release_provider = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def provider(root: str, *, order: str):
        nonlocal calls
        with calls_lock:
            calls += 1
        provider_started.set()
        assert release_provider.wait(5), "test did not release provider"
        return frame

    def invoke(clock: Clock) -> Exception | dict:
        try:
            return builder.run_attempt(
                inputs=inputs,
                index_key=focused.W0A_INDEX_KEY,
                index_bytes=bundle["index_bytes"],
                completion_ledger_bytes=bundle["completion_ledger_bytes"],
                packet_loader=_loader(bundle),
                state_root=tmp_path,
                snapshot_greeks=provider,
                clock=clock,
            )
        except Exception as exc:  # noqa: BLE001 - the exact fail-closed outcomes are asserted
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(invoke, Clock(T0, T1))
        assert provider_started.wait(5), "first holder did not reach provider"
        lock_path = tmp_path / digest / ".attempt.lock"
        original_inode = lock_path.stat().st_ino
        lock_path.unlink()
        lock_path.write_bytes(b"hostile replacement")
        lock_path.chmod(0o600)
        assert lock_path.stat().st_ino != original_inode
        second_future = pool.submit(invoke, Clock(T0 + timedelta(seconds=1)))
        time.sleep(0.1)
        assert not second_future.done(), "replacement lock admitted a parallel holder"
        release_provider.set()
        first = first_future.result(timeout=5)
        second = second_future.result(timeout=5)

    assert isinstance(first, builder.FocusedQuoteRuntimeError)
    assert "per-attempt lock" in str(first)
    assert isinstance(second, builder.AttemptPendingError)
    assert calls == 1
    assert not (tmp_path / digest / "receipt.json").exists()


def test_private_r2_decision_cas_prevents_repoll_after_state_root_replacement(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frame = _frames(decision)["SPY"]
    state_root = tmp_path / "state"
    replaced_root = tmp_path / "state-replaced"
    client = FakeR2()
    provider_started = threading.Event()
    release_provider = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def provider(root: str, *, order: str):
        nonlocal calls
        with calls_lock:
            calls += 1
        provider_started.set()
        assert release_provider.wait(5), "test did not release provider"
        return frame

    def invoke(clock: Clock) -> Exception | dict:
        try:
            return builder.run_attempt(
                inputs=inputs,
                index_key=focused.W0A_INDEX_KEY,
                index_bytes=bundle["index_bytes"],
                completion_ledger_bytes=bundle["completion_ledger_bytes"],
                packet_loader=_loader(bundle),
                state_root=state_root,
                snapshot_greeks=provider,
                clock=clock,
                r2_client=client,
                r2_bucket="private-test",
            )
        except Exception as exc:  # noqa: BLE001 - exact fail-closed outcomes are asserted
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(invoke, Clock(T0, T1))
        assert provider_started.wait(5), "first holder did not reach provider"
        state_root.rename(replaced_root)
        state_root.mkdir(mode=0o700)
        second_future = pool.submit(invoke, Clock(T0 + timedelta(seconds=1)))
        try:
            second = second_future.result(timeout=2)
        finally:
            release_provider.set()
        first = first_future.result(timeout=5)

    assert isinstance(first, builder.FocusedQuoteRuntimeError)
    assert "state root inode changed" in str(first)
    assert isinstance(second, builder.AttemptPendingError)
    assert calls == 1
    assert decision["publication"]["decision_key"] in client.objects
    assert decision["publication"]["receipt_key"] not in client.objects

    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=state_root,
        snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not repoll"),
        clock=Clock(T0 + timedelta(seconds=300)),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert recovered["abstention_reason"] == "RECOVERY_DEADLINE_EXCEEDED"
    assert calls == 1


def test_remote_decision_and_receipt_are_create_only_private_and_verified(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    frame = _frames(decision)["SPY"]
    client = FakeR2()
    receipt = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=lambda root, *, order: frame,
        clock=Clock(T0, T1),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert receipt["status"] == "complete"
    assert [put["Key"] for put in client.puts] == [
        decision["publication"]["decision_key"],
        decision["publication"]["receipt_key"],
    ]
    assert all(put["IfNoneMatch"] == "*" for put in client.puts)
    assert all(put["CacheControl"] == "private, no-store" for put in client.puts)
    assert all(put["Metadata"]["sha256"] == sha256(put["Body"]).hexdigest() for put in client.puts)
    assert all(put["Metadata"]["visibility"] == "private" for put in client.puts)
    assert all(put["Metadata"]["immutable"] == "true" for put in client.puts)


def test_remote_decision_collision_fails_before_provider_call(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    different = b"different\n"
    client.seed(decision["publication"]["decision_key"], different, {
        "sha256": sha256(different).hexdigest(),
        "schema": focused.SCHEMA,
        "record-type": "decision",
        "attempt-id": decision["attempt_id"],
        "visibility": "private",
        "immutable": "true",
    })
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.RemoteImmutableCollisionError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0),
            r2_client=client,
            r2_bucket="private-test",
        )
    assert calls == 0


def test_remote_decision_verification_uncertainty_fails_before_provider_call(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    client.corrupt_reads.add(decision["publication"]["decision_key"])
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.RemotePublicationUncertainError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0),
            r2_client=client,
            r2_bucket="private-test",
        )
    assert calls == 0


def test_globally_preexisting_decision_without_receipt_never_polls(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    _seed_record(client, decision)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.AttemptPendingError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0, T0 + timedelta(seconds=1)),
            r2_client=client,
            r2_bucket="private-test",
        )
    assert calls == 0


def test_globally_preexisting_decision_clock_is_adopted_before_local_creation(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    remote_decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    _seed_record(client, remote_decision)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.AttemptPendingError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0 + timedelta(seconds=1)),
            r2_client=client,
            r2_bucket="private-test",
        )
    attempt_dir = tmp_path / remote_decision["attempt_id"].rsplit(":", 1)[1]
    assert (attempt_dir / "decision.json").read_bytes() == focused.canonical_json_bytes(
        remote_decision
    )
    assert calls == 0


def test_interleaved_cas_loser_adopts_winner_and_retry_never_polls(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    winner = focused.build_decision(_plan(bundle, inputs), decided_at=T0)

    class LosingCAS(FakeR2):
        def put_object(self, **kwargs):
            self.puts.append(dict(kwargs))
            _seed_record(self, winner)
            raise S3Error("PreconditionFailed", 412)

    client = LosingCAS()
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.AttemptPendingError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(
                T0 + timedelta(seconds=1),
                T0 + timedelta(seconds=2),
            ),
            r2_client=client,
            r2_bucket="private-test",
        )
    attempt_dir = tmp_path / winner["attempt_id"].rsplit(":", 1)[1]
    assert (attempt_dir / "decision.json").read_bytes() == focused.canonical_json_bytes(
        winner
    )

    winner_receipt = focused.build_source_receipt(
        winner, _frames(winner), verified_at=T1
    )
    _seed_record(client, winner_receipt)
    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert recovered == winner_receipt
    assert calls == 0


def test_globally_preexisting_receipt_is_recovered_without_poll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    receipt = focused.build_source_receipt(
        decision, _frames(decision), verified_at=T1
    )
    client = FakeR2()
    _seed_record(client, decision)
    _seed_record(client, receipt)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert calls == 0
    assert recovered == receipt
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    assert (attempt_dir / "receipt.json").read_bytes() == focused.canonical_json_bytes(receipt)


def test_local_decision_retry_adopts_globally_preexisting_receipt_without_poll(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    receipt = focused.build_source_receipt(
        decision, _frames(decision), verified_at=T1
    )
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    builder._write_immutable(
        attempt_dir / "decision.json", focused.canonical_json_bytes(decision)
    )
    client = FakeR2()
    _seed_record(client, decision)
    _seed_record(client, receipt)
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    recovered = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T1),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert recovered == receipt
    assert calls == 0


def test_remote_metadata_mismatch_fails_before_provider_call(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    _seed_record(client, decision)
    body, metadata = client.objects[decision["publication"]["decision_key"]]
    client.objects[decision["publication"]["decision_key"]] = (
        body,
        {**metadata, "record-type": "receipt"},
    )
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.RemoteImmutableCollisionError, match="metadata/body"):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0),
            r2_client=client,
            r2_bucket="private-test",
        )
    assert calls == 0


@pytest.mark.parametrize("fault", ["metadata_extra", "content_type", "cache_control"])
def test_remote_privacy_headers_and_metadata_are_exact_before_provider(
    fault: str,
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    _seed_record(client, decision)
    key = decision["publication"]["decision_key"]
    if fault == "metadata_extra":
        body, metadata = client.objects[key]
        client.objects[key] = (body, {**metadata, "unexpected": "value"})
    elif fault == "content_type":
        client.content_types[key] = "text/plain"
    else:
        client.cache_controls[key] = "public, max-age=60"
    calls = 0

    def provider(*args, **kwargs):
        nonlocal calls
        calls += 1

    with pytest.raises(builder.RemotePublicationUncertainError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0),
            r2_client=client,
            r2_bucket="private-test",
        )
    assert calls == 0


def test_oversized_remote_body_is_rejected_before_stream_read() -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])),
        decided_at=T0,
    )
    body = focused.canonical_json_bytes(decision)

    class NeverRead:
        def __init__(self):
            self.read_calls = 0
            self.closed = False

        def read(self, size=-1):
            self.read_calls += 1
            raise AssertionError("oversized body must not be read")

        def close(self):
            self.closed = True

    stream = NeverRead()

    class OversizedClient:
        def get_object(self, *, Bucket, Key):
            return {
                "Body": stream,
                "ContentLength": builder.MAX_REMOTE_OBJECT_BYTES + 1,
                "ContentType": "application/json",
                "CacheControl": "private, no-store",
                "Metadata": {
                    "sha256": sha256(body).hexdigest(),
                    "schema": focused.SCHEMA,
                    "record-type": "decision",
                    "attempt-id": decision["attempt_id"],
                    "visibility": "private",
                    "immutable": "true",
                },
            }

    with pytest.raises(builder.RemotePublicationUncertainError, match="length is unsafe"):
        builder._remote_object(
            OversizedClient(),
            "private-test",
            decision["publication"]["decision_key"],
        )
    assert stream.read_calls == 0
    assert stream.closed is True


def test_generic_r2_environment_cannot_enable_private_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dedicated = (
        "OPTIONS_FOCUSED_QUOTE_R2_ENDPOINT",
        "OPTIONS_FOCUSED_QUOTE_R2_ACCESS_KEY_ID",
        "OPTIONS_FOCUSED_QUOTE_R2_SECRET_ACCESS_KEY",
        "OPTIONS_FOCUSED_QUOTE_R2_BUCKET",
    )
    for name in dedicated:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_ENDPOINT", "https://shared-public.invalid")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "shared-access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "shared-secret")
    monkeypatch.setenv("R2_BUCKET", "shared-public-bucket")
    assert builder._private_r2_config() is None

    monkeypatch.setenv("OPTIONS_FOCUSED_QUOTE_R2_BUCKET", "private-only")
    with pytest.raises(builder.FocusedQuoteRuntimeError, match="incomplete"):
        builder._private_r2_config()


@pytest.mark.parametrize(
    ("extra_args", "expected_error"),
    [
        ([], "--execute-provider-poll acknowledgement is required"),
        (
            ["--execute-provider-poll", "--publish"],
            "OPTIONS_FOCUSED_QUOTE_R2_* private settings are required",
        ),
    ],
)
def test_cli_cannot_poll_or_write_a_decision_without_explicit_private_r2_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
    expected_error: str,
) -> None:
    for name in (
        "OPTIONS_FOCUSED_QUOTE_R2_ENDPOINT",
        "OPTIONS_FOCUSED_QUOTE_R2_ACCESS_KEY_ID",
        "OPTIONS_FOCUSED_QUOTE_R2_SECRET_ACCESS_KEY",
        "OPTIONS_FOCUSED_QUOTE_R2_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        builder,
        "run_attempt",
        lambda **kwargs: pytest.fail("CLI gate must stop before run_attempt"),
    )
    state_root = tmp_path / "state"
    result = builder.main([
        "--inputs", str(tmp_path / "not-read-inputs.json"),
        "--w0a-index", str(tmp_path / "not-read-index.json"),
        "--w0a-completion-ledger", str(tmp_path / "not-read-completion.jsonl"),
        "--w0a-object-root", str(tmp_path / "not-read-objects"),
        "--state-root", str(state_root),
        *extra_args,
    ])
    assert result == 2
    assert expected_error in capsys.readouterr().err
    assert not state_root.exists()


def test_recovery_receipt_cas_loser_adopts_winner_and_retry_is_stable(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    winner = focused.build_recovery_receipt(
        decision, verified_at=T0 + timedelta(seconds=300)
    )

    class LosingReceiptCAS(FakeR2):
        def put_object(self, **kwargs):
            if kwargs["Key"] == decision["publication"]["receipt_key"]:
                self.puts.append(dict(kwargs))
                _seed_record(self, winner)
                raise S3Error("PreconditionFailed", 412)
            return super().put_object(**kwargs)

    client = LosingReceiptCAS()
    _seed_record(client, decision)
    provider = lambda *args, **kwargs: pytest.fail("recovery must not poll")
    adopted = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0 + timedelta(seconds=301)),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert adopted == winner
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    assert (attempt_dir / "receipt.json").read_bytes() == focused.canonical_json_bytes(
        winner
    )
    retried = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert retried == winner


def test_preexisting_divergent_local_receipt_cannot_preempt_remote_winner(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    winner = focused.build_recovery_receipt(
        decision, verified_at=T0 + timedelta(seconds=300)
    )
    loser = focused.build_recovery_receipt(
        decision, verified_at=T0 + timedelta(seconds=301)
    )
    attempt_dir = tmp_path / decision["attempt_id"].rsplit(":", 1)[1]
    builder._write_immutable(
        attempt_dir / "decision.json", focused.canonical_json_bytes(decision)
    )
    builder._write_immutable(
        attempt_dir / "receipt.json", focused.canonical_json_bytes(loser)
    )
    client = FakeR2()
    _seed_record(client, decision)
    _seed_record(client, winner)
    adopted = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not poll"),
        clock=Clock(),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert adopted == winner
    assert (attempt_dir / "receipt.json").read_bytes() == focused.canonical_json_bytes(
        loser
    )


def test_deadline_receipt_can_win_against_long_source_completion_without_repoll(
    tmp_path: Path,
) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    recovery = focused.build_recovery_receipt(
        decision, verified_at=T0 + timedelta(seconds=300)
    )
    frame = _frames(decision)["SPY"]
    client = FakeR2()
    calls = 0

    def long_provider(root: str, *, order: str):
        nonlocal calls
        calls += 1
        _seed_record(client, recovery)
        return frame

    adopted = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=long_provider,
        clock=Clock(T0, T0 + timedelta(seconds=301)),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert calls == 1
    assert adopted == recovery
    assert adopted["abstention_reason"] == "RECOVERY_DEADLINE_EXCEEDED"
    retried = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=lambda *args, **kwargs: pytest.fail("must not repoll"),
        clock=Clock(),
        r2_client=client,
        r2_bucket="private-test",
    )
    assert retried == recovery
    assert calls == 1


def test_remote_receipt_collision_never_causes_a_second_poll(tmp_path: Path) -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    inputs = _inputs(bundle, [("SPY", PROFILE_A, "100")])
    decision = focused.build_decision(_plan(bundle, inputs), decided_at=T0)
    client = FakeR2()
    different = b"different\n"
    client.seed(decision["publication"]["receipt_key"], different, {
        "sha256": sha256(different).hexdigest(),
        "schema": focused.SCHEMA,
        "record-type": "receipt",
        "attempt-id": decision["attempt_id"],
        "visibility": "private",
        "immutable": "true",
    })
    frame = _frames(decision)["SPY"]
    calls = 0

    def provider(root, *, order):
        nonlocal calls
        calls += 1
        return frame

    with pytest.raises(builder.RemoteImmutableCollisionError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T0, T1),
            r2_client=client,
            r2_bucket="private-test",
        )
    with pytest.raises(builder.AttemptPendingError):
        builder.run_attempt(
            inputs=inputs,
            index_key=focused.W0A_INDEX_KEY,
            index_bytes=bundle["index_bytes"],
            completion_ledger_bytes=bundle["completion_ledger_bytes"],
            packet_loader=_loader(bundle),
            state_root=tmp_path,
            snapshot_greeks=provider,
            clock=Clock(T1),
        )
    local = builder.run_attempt(
        inputs=inputs,
        index_key=focused.W0A_INDEX_KEY,
        index_bytes=bundle["index_bytes"],
        completion_ledger_bytes=bundle["completion_ledger_bytes"],
        packet_loader=_loader(bundle),
        state_root=tmp_path,
        snapshot_greeks=provider,
        clock=Clock(T0 + timedelta(seconds=300)),
    )
    assert calls == 1
    assert local["abstention_reason"] == "RECOVERY_DEADLINE_EXCEEDED"


def test_schema_and_digest_mutations_are_rejected() -> None:
    bundle = _bundle()
    decision = focused.build_decision(_plan(bundle), decided_at=T0)
    bad_schema = deepcopy(decision)
    bad_schema["authority"]["trade_authority"] = True
    assert _schema_errors(bad_schema)
    with pytest.raises(focused.FocusedQuoteError, match="decision_id"):
        focused.validate_decision({**decision, "decided_at": focused._iso_utc(T1)})


def test_reidentified_receipt_cannot_contradict_source_call_evidence() -> None:
    bundle = _bundle({"SPY": [("2026-09-18", "C", "100", (PROFILE_A,))]})
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100")])),
        decided_at=T0,
    )
    receipt = focused.build_source_receipt(
        decision, _frames(decision), verified_at=T1
    )
    bad_complete = deepcopy(receipt)
    bad_complete["source_calls"][0].update({
        "returned_row_count": 0,
        "source_shape_valid": False,
        "requested_match_row_count": 0,
        "structurally_accepted_requested_row_count": 0,
        "malformed_requested_row_count": 0,
    })
    bad_complete["receipt_id"] = focused._identity_digest(
        "receipt:focused_quote:", bad_complete, "receipt_id"
    )
    assert _schema_errors(bad_complete) == []
    with pytest.raises(focused.FocusedQuoteError, match="complete source-call evidence"):
        focused.validate_receipt(bad_complete, decision)

    bad_abstention = deepcopy(receipt)
    bad_abstention["status"] = "abstain"
    bad_abstention["abstention_reason"] = "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW"
    bad_abstention["quotes"] = []
    bad_abstention["receipt_id"] = focused._identity_digest(
        "receipt:focused_quote:", bad_abstention, "receipt_id"
    )
    assert _schema_errors(bad_abstention) == []
    with pytest.raises(focused.FocusedQuoteError, match="contradicts complete"):
        focused.validate_receipt(bad_abstention, decision)


def test_reidentified_source_receipt_cannot_bypass_preflight_abstention() -> None:
    bundle = _bundle({
        "SPY": [("2026-09-18", "C", "100.0005", (PROFILE_A,))],
    })
    decision = focused.build_decision(
        _plan(bundle, _inputs(bundle, [("SPY", PROFILE_A, "100.0005")])),
        decided_at=T0,
    )
    receipt = focused.build_preflight_receipt(decision, verified_at=T0)
    hostile = deepcopy(receipt)
    hostile["abstention_reason"] = "NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW"
    hostile["source_calls"] = [{
        "root": "SPY",
        "endpoint": focused.SOURCE_ENDPOINT,
        "call_count": 1,
        "returned_row_count": 0,
        "source_shape_valid": True,
        "requested_match_row_count": 0,
        "structurally_accepted_requested_row_count": 0,
        "malformed_requested_row_count": 0,
    }]
    hostile["receipt_id"] = focused._identity_digest(
        "receipt:focused_quote:", hostile, "receipt_id"
    )
    assert _schema_errors(hostile) == []
    with pytest.raises(
        focused.FocusedQuoteError,
        match="preflight abstention cannot carry provider",
    ):
        focused.validate_receipt(hostile, decision)


def test_collector_truth_constants_match_the_engine_without_new_endpoint() -> None:
    from collectors import thetadata

    assert thetadata.SNAPSHOT_FIRST_ORDER_ENDPOINT == focused.SOURCE_ENDPOINT
    assert thetadata.SNAPSHOT_FIRST_ORDER_QUOTE_LABEL == focused.SOURCE_QUOTE_LABEL
    assert thetadata.SNAPSHOT_FIRST_ORDER_IS_NBBO is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_IS_LIVE is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_IS_CURRENT is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_IS_EXECUTABLE is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_HAS_SIZES is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_HAS_VENUES is False
    assert thetadata.SNAPSHOT_FIRST_ORDER_HAS_CONDITIONS is False


def test_external_cwd_import_does_not_depend_on_repository_cwd() -> None:
    assert builder.REPO_ROOT == Path(__file__).resolve().parents[1]
