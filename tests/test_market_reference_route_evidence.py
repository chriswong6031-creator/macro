"""RED→GREEN tests for MOR-1 route-semantic evidence (issue #6782)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.market_reference_route_evidence import (
    ROUTE_CASES,
    assert_historical_overclaim_is_red,
    mor1_capture_rows,
    validate_manifest_route_matrix,
)

REPO = Path(__file__).resolve().parents[1]

# Immutable snapshot of the #6771 false-complete pattern (8 default cells +
# three excluded required routes). Kept inline so the committed estate can be
# repaired without erasing the discriminating RED proof.
HISTORICAL_OVERCLAIM = {
    "schema": "mastermind.p0_evidence.v2",
    "pages": [
        {
            "page_id": "reference.html",
            "route": "reference.html",
            "states": [
                {
                    "viewport": vp,
                    "locale": loc,
                    "theme": th,
                    "access": "anonymous",
                    "force_state": None,
                    "captured": True,
                    "file": "deadbeef.png",
                    "sha256": "aa" * 32,
                    "bytes": 1,
                    "width": 1,
                    "height": 1,
                    "applied_theme": th,
                    "applied_locale": loc,
                }
                for vp in ("desktop", "mobile")
                for loc in ("en", "zh")
                for th in ("dark", "light")
            ],
        }
    ],
    "excluded": [
        {"route": "reference.html#vix", "reason": "historical omission"},
        {"route": "reference.html#not-a-real-entry", "reason": "historical omission"},
        {"route": "reference.html?q=curve", "reason": "historical omission"},
    ],
}


def _rest_states_for(route_state: dict, *, sha: str = "a" * 64) -> list[dict]:
    states = []
    for viewport in ("desktop", "mobile"):
        for locale in ("en", "zh"):
            for theme in ("dark", "light"):
                states.append(
                    {
                        "viewport": viewport,
                        "locale": locale,
                        "theme": theme,
                        "access": "anonymous",
                        "force_state": None,
                        "captured": True,
                        "file": f"{sha[:16]}.png",
                        "sha256": sha,
                        "bytes": 10,
                        "width": 10,
                        "height": 10,
                        "applied_theme": theme,
                        "applied_locale": locale,
                        "route_state": dict(route_state),
                    }
                )
    return states


def _green_manifest() -> dict:
    pages = []
    for i, case in enumerate(ROUTE_CASES):
        expect = case["expect"]
        rs = {
            "requested_url": f"http://127.0.0.1:9/{case['route']}",
            "final_url": f"http://127.0.0.1:9/{case['route']}",
            "hash": expect.get("hash", ""),
            "query_q": expect.get("query_q"),
            "miss_visible": bool(expect.get("miss_visible")),
            "selected_id": expect.get("selected_id"),
            "visible_result_count": max(expect.get("min_visible_results") or 0, 2),
            "rf_q_value": expect.get("query_q") or "",
        }
        # Unique digest per route case.
        sha = f"{i:064x}"
        pages.append(
            {
                "page_id": case["page_id"],
                "route": case["route"],
                "states": _rest_states_for(rs, sha=sha),
            }
        )
    return {"schema": "mastermind.p0_evidence.v2", "pages": pages, "excluded": []}


def test_historical_committed_manifest_is_red_overclaim():
    assert_historical_overclaim_is_red(HISTORICAL_OVERCLAIM)


def test_missing_route_case_is_red():
    manifest = _green_manifest()
    manifest["pages"] = [p for p in manifest["pages"] if p["route"] != "reference.html#vix"]
    errors = validate_manifest_route_matrix(manifest)
    assert any("valid_anchor" in e or "reference.html#vix" in e for e in errors)


def test_relabel_default_digest_as_vix_is_red():
    manifest = _green_manifest()
    default = next(p for p in manifest["pages"] if p["route"] == "reference.html")
    vix = next(p for p in manifest["pages"] if p["route"] == "reference.html#vix")
    stolen = default["states"][0]["sha256"]
    for state in vix["states"]:
        state["sha256"] = stolen
        # Keep vix route_state so the only mutant is cross-route digest reuse.
    errors = validate_manifest_route_matrix(manifest)
    assert any("reused across distinct routes" in e for e in errors)


def test_query_route_without_query_state_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["query_q"] = None
        state["route_state"]["visible_result_count"] = 0
    errors = validate_manifest_route_matrix(manifest)
    assert any("query_q" in e or "visible_result_count" in e for e in errors)


def test_unknown_anchor_without_miss_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_visible"] = False
    errors = validate_manifest_route_matrix(manifest)
    assert any("miss_visible" in e for e in errors)


def test_green_matrix_passes():
    assert validate_manifest_route_matrix(_green_manifest()) == []


def test_mor1_capture_rows_cover_four_cases():
    rows = mor1_capture_rows()
    assert [r["capture_route"] for r in rows] == [c["route"] for c in ROUTE_CASES]
    assert len(rows) == 4


def test_template_writes_query_to_url():
    text = (REPO / "templates" / "reference.html.j2").read_text(encoding="utf-8")
    assert "READ, never written" not in text
    assert "function syncQueryToUrl" in text
    assert "popstate" in text
    assert "searchParams.set(\"q\"" in text or "searchParams.set('q'" in text
