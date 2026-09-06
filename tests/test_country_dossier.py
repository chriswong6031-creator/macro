"""Country policy dossier leaf — schema, typed nulls, fail-closed contract."""

from __future__ import annotations

import ast
import copy
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from engine.country_dossier import (
    SCHEMA,
    STANCE_KEYS,
    build_dossier_block,
    dossier_path,
)
from engine.international_macro_dashboard import (
    REGIONS,
    build_country_view,
    validate_view,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "engine" / "country_dossier.py"
TODAY = date(2026, 9, 6)


def _minimal_ok_yaml(**overrides) -> dict:
    base = {
        "dossier": "xx",
        "schema": SCHEMA,
        "rev": 1,
        "region": "XX",
        "tier": "context_only",
        "reviewed_at": "2026-09-01",
        "review_interval_days": 180,
        "rights": "public",
        "stance": {
            "key": "on_hold",
            "claim": "INFERENCE",
            "known_at": "2026-07-31",
            "evidence": {
                "source_url": "https://example.com/policy",
                "publisher": {"en": "Example Bank", "zh": "示例银行"},
                "document": {"en": "Policy statement", "zh": "政策声明"},
                "version": "2026-07-31",
            },
        },
        "seats": [
            {
                "key": "central_bank",
                "role": {"en": "Governor", "zh": "行长"},
                "institution": {"en": "Example Bank", "zh": "示例银行"},
                "holder": {"en": "A Person", "zh": "某人"},
                "since": "2023-04-10",
                "note": {
                    "en": "Sets the policy rate for the economy.",
                    "zh": "决定政策利率。",
                },
                "claim": "FACT",
                "known_at": "2026-09-01",
                "jurisdiction": "settled",
                "rights": "public",
                "evidence": {
                    "source_url": "https://example.com/board",
                    "publisher": {"en": "Example Bank", "zh": "示例银行"},
                    "document": {"en": "Board members", "zh": "委员会名单"},
                    "version": "2026-09-01",
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _write_yaml(tmp_path: Path, cc: str, data: dict | str | bytes) -> Path:
    d = tmp_path.joinpath("knowledge", "policy_geo", "country_dossier")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{cc.lower()}.yaml"
    if isinstance(data, bytes):
        path.write_bytes(data)
    elif isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _jp_record() -> dict:
    spec = REGIONS["JP"]
    return {
        "cc": "JP",
        "name": "Japan",
        "name_zh": "日本",
        "flag": "🇯🇵",
        "date": "2026-07-30",
        "quad": "Q2",
        "quad_name": "Reflation",
        "growth_score": 0.4,
        "inflation_score": 0.25,
        "confidence": 0.55,
        "liquidity": "neutral",
        "recession_score": 20.0,
        "recession_band": "low",
        "data_limited": False,
        "macro": {
            "cpi_yoy": 2.4,
            "gdp_yoy": 1.8,
            "unemployment": 4.1,
            "yield_10y": 3.2,
            "policy_rate": 2.5,
            "curve": 0.7,
            "fx": 100.25,
            "fx_strength_3m": -1.2,
            "drawdown": -5.0,
            "realvol": 18.0,
        },
        "macro_asof": {
            "cpi_yoy": "2026-06",
            "gdp": "2026-04",
            "unemployment": "2026-06",
            "yield_10y": "2026-07",
        },
        "equity": {"drawdown_risk": 32.0},
        "risk_radar": {
            "state": "caution",
            "top_score": 62,
            "dominant_label_en": "Rate shock",
            "dominant_label_zh": "利率冲击",
            "drawdown_prob": {
                "h21": 0.21,
                "measure": ">=5% pullback within 21 business days",
            },
            "scares": [],
        },
        "scope_zh_hint": spec.scope_zh[:2],
    }


def test_real_jp_dossier_is_ok() -> None:
    block = build_dossier_block("JP", today=TODAY)
    assert block["state"] in {"ok", "stale"}
    assert block["schema"] == SCHEMA
    assert 1 <= len(block["seats"]) <= 4
    assert block["stance"]["key"] in STANCE_KEYS
    for seat in block["seats"]:
        assert seat.get("known_at")
        assert seat.get("claim") in {"FACT", "INFERENCE"}
        ev = seat.get("evidence") or {}
        assert str(ev.get("source_url", "")).startswith("https://")


def test_missing_file_is_a_typed_null_not_a_raise(tmp_path: Path) -> None:
    block = build_dossier_block("ZZ", today=TODAY, root=tmp_path)
    assert block["state"] == "no_coverage"
    assert block["stance"] is None
    assert block["seats"] == []
    assert block["reason"] == "file_absent"


def test_malformed_schema_fails_closed(tmp_path: Path) -> None:
    cases = [
        (
            "missing_source_url",
            lambda d: d["seats"][0]["evidence"].pop("source_url"),
        ),
        ("bad_claim", lambda d: d["stance"].__setitem__("claim", "GUESS")),
        (
            "future_known_at",
            lambda d: d["stance"].__setitem__("known_at", "2099-01-01"),
        ),
        (
            "duplicate_seat",
            lambda d: d["seats"].append(copy.deepcopy(d["seats"][0])),
        ),
        (
            "five_seats",
            lambda d: d.update(
                {
                    "seats": [
                        {**copy.deepcopy(d["seats"][0]), "key": k}
                        for k in (
                            "head_of_government",
                            "central_bank",
                            "finance",
                            "legislature",
                            "central_bank",
                        )
                    ]
                }
            ),
        ),
        ("wrong_schema", lambda d: d.__setitem__("schema", "other.v1")),
        ("bad_tier", lambda d: d.__setitem__("tier", "authority")),
    ]
    for name, mut in cases:
        data = _minimal_ok_yaml()
        # five_seats needs unique keys but >4 — rebuild carefully
        if name == "five_seats":
            seat0 = copy.deepcopy(data["seats"][0])
            data["seats"] = []
            for i, k in enumerate(
                (
                    "head_of_government",
                    "central_bank",
                    "finance",
                    "legislature",
                )
            ):
                s = copy.deepcopy(seat0)
                s["key"] = k
                data["seats"].append(s)
            extra = copy.deepcopy(seat0)
            extra["key"] = "central_bank"  # will also fail duplicate if 5th with dup — use 5 unique by adding a clone with same after pad
            # Spec: 5 seats → invalid. Force length 5 with a duplicate key intentionally:
            data["seats"].append(extra)
        else:
            mut(data)
        _write_yaml(tmp_path, "XX", data)
        block = build_dossier_block("XX", today=TODAY, root=tmp_path)
        assert block["state"] == "invalid", name
        assert block.get("reason"), name

    _write_yaml(tmp_path, "YY", "{ this is: [not: valid")
    bad = build_dossier_block("YY", today=TODAY, root=tmp_path)
    assert bad["state"] == "invalid"
    assert bad.get("reason")

    view = build_country_view(_jp_record(), today=TODAY)
    view["dossier"] = bad
    # A context-only dossier (never feeds a score/regime/rank/trade call) must not
    # hard-fail the country build on a curator typo — it degrades to a typed null
    # with the original reason preserved instead of raising.
    validate_view(view)
    assert view["dossier"]["state"] == "no_coverage"
    assert view["dossier"]["reason"] == bad["reason"]


def test_stale_is_a_state_not_an_error(tmp_path: Path) -> None:
    data = _minimal_ok_yaml(reviewed_at=(TODAY - timedelta(days=200)).isoformat())
    _write_yaml(tmp_path, "XX", data)
    block = build_dossier_block("XX", today=TODAY, root=tmp_path)
    assert block["state"] == "stale"
    assert block["stance"] is not None
    assert block["seats"]


def test_rights_suppressed_drops_detail(tmp_path: Path) -> None:
    data = _minimal_ok_yaml(rights="suppressed")
    _write_yaml(tmp_path, "XX", data)
    block = build_dossier_block("XX", today=TODAY, root=tmp_path)
    assert block["state"] == "rights_suppressed"
    assert "holder" not in str(block)

    data2 = _minimal_ok_yaml()
    data2["dossier"] = "xz"
    data2["region"] = "XZ"
    data2["seats"][0]["rights"] = "suppressed"
    data2["seats"][0]["evidence"] = {
        "source_url": "https://example.com/board",
        "publisher": {"en": "Example Bank", "zh": "示例银行"},
        "document": None,
        "version": None,
    }
    _write_yaml(tmp_path, "XZ", data2)
    block2 = build_dossier_block("XZ", today=TODAY, root=tmp_path)
    assert block2["state"] in {"ok", "stale"}
    seat = block2["seats"][0]
    assert seat["state"] == "rights_suppressed"
    assert "holder" not in seat
    assert "note" not in seat


def test_ambiguous_jurisdiction_drops_the_holder(tmp_path: Path) -> None:
    data = _minimal_ok_yaml()
    data["seats"][0]["jurisdiction"] = "ambiguous"
    _write_yaml(tmp_path, "XX", data)
    block = build_dossier_block("XX", today=TODAY, root=tmp_path)
    seat = block["seats"][0]
    assert seat["state"] == "ambiguous_jurisdiction"
    assert "holder" not in seat
    assert seat["role"]["en"]
    assert seat["institution"]["en"]


def test_human_dates_are_formatted_by_the_producer() -> None:
    block = build_dossier_block("JP", today=TODAY)
    assert block["reviewed_at_human_en"]
    assert not re.fullmatch(r"\d{4}-\d{2}-\d{2}", block["reviewed_at_human_en"])
    assert "年" in block["reviewed_at_human_zh"]
    assert block["stance"]["known_at_human_en"]
    assert not re.fullmatch(r"\d{4}-\d{2}-\d{2}", block["stance"]["known_at_human_en"])
    for seat in block["seats"]:
        assert seat["known_at_human_en"]
        assert "年" in seat["known_at_human_zh"]
        if seat.get("since"):
            assert seat["since_human_en"]
            assert not re.fullmatch(r"\d{4}-\d{2}-\d{2}", seat["since_human_en"])


def test_producer_never_raises(tmp_path: Path) -> None:
    hostile = [
        "",
        "[]",
        "42",
        "null",
        b"\x00\x01\xff",
        "seats: null\ndossier: xx\n",
        yaml.safe_dump({**_minimal_ok_yaml(), "reviewed_at": 20260901}),
        yaml.safe_dump({**_minimal_ok_yaml(), "stance": None}),
        yaml.safe_dump({**_minimal_ok_yaml(), "seats": None}),
        "{: broken",
    ]
    for i, payload in enumerate(hostile):
        _write_yaml(tmp_path, f"h{i}", payload)
        block = build_dossier_block(f"H{i}", today=TODAY, root=tmp_path)
        assert isinstance(block, dict)
        assert "state" in block


def test_leaf_imports() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_roots = {"engine", "collectors", "pandas", "numpy", "scripts"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in forbidden_roots, alias.name
                assert "score" not in alias.name
                assert "regime" not in alias.name
                assert "market_state" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".", 1)[0]
            assert root not in forbidden_roots, mod
            assert "score" not in mod
            assert "regime" not in mod
            assert "market_state" not in mod


def test_no_llm_and_no_network() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    for token in ("requests", "urllib", "httpx", "openai", "anthropic", "socket"):
        assert token not in src


def test_dossier_path_joins_region_stem() -> None:
    assert dossier_path("JP").name == "jp.yaml"
