"""RED→GREEN tests for MOR-1 route-semantic evidence (issue #6782)."""

from __future__ import annotations

import copy
import hashlib
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
    "tool": {"version": "1.0.0"},
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


def _ok_journeys() -> dict:
    return {
        "change": {"ok": True},
        "clear": {"ok": True},
        "reload": {"ok": True},
        "back_forward": {"ok": True},
        "share": {"ok": True},
    }


def _binding() -> dict:
    return {
        "source_commit": "b" * 40,
        "source_tree": "c" * 40,
        "source_commit_verified": True,
        "worktree_head_matches_source": True,
        "site_reference_sha256": "d" * 64,
        "serve_root": "http://127.0.0.1:9",
        "capture_tool_version": "1.3.0",
        "capture_tool_module_sha256": "e" * 64,
    }


def _route_state_for(case: dict, *, locale: str = "en") -> dict:
    expect = case["expect"]
    count = max(expect.get("min_visible_results") or 0, 2)
    selected = expect.get("selected_id")
    ids = [selected] if selected else [f"entry-{i}" for i in range(count)]
    if expect.get("query_q"):
        ids = ["curve-a", "curve-b"][:count]
    focused = selected
    return {
        "requested_url": f"http://127.0.0.1:9/{case['route']}",
        "final_url": f"http://127.0.0.1:9/{case['route']}",
        "hash": expect.get("hash", ""),
        "query_q": expect.get("query_q"),
        "rf_q_value": expect.get("query_q") or "",
        "miss_visible": bool(expect.get("miss_visible")),
        "selected_id": selected,
        "visible_result_count": count,
        "visible_entry_ids": ids,
        "count_label_visible": True,
        "count_label_text": f"{count} of 34 entries" if locale == "en" else f"显示 {count} 条",
        "count_label_values": [str(count)],
        "focused_element_id": focused,
        "focused_visible": bool(expect.get("require_focus")),
        "target_below_fixed_ui": True if expect.get("require_focus") else None,
        "journeys": _ok_journeys(),
    }


def _rest_states_for(route_state: dict, *, sha: str = "a" * 64) -> list[dict]:
    states = []
    for viewport in ("desktop", "mobile"):
        for locale in ("en", "zh"):
            for theme in ("dark", "light"):
                rs = dict(route_state)
                # Locale-appropriate count label text.
                count = rs.get("visible_result_count") or 0
                if locale == "zh":
                    rs["count_label_text"] = f"显示 {count} 条"
                else:
                    rs["count_label_text"] = f"{count} of 34 entries"
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
                        "route_state": rs,
                    }
                )
    return states


def _green_manifest() -> dict:
    pages = []
    for i, case in enumerate(ROUTE_CASES):
        sha = f"{i:064x}"
        pages.append(
            {
                "page_id": case["page_id"],
                "route": case["route"],
                "console_errors": [],
                "failed_responses": [],
                "route_journeys": _ok_journeys(),
                "states": _rest_states_for(_route_state_for(case), sha=sha),
            }
        )
    return {
        "schema": "mastermind.p0_evidence.v2",
        "tool": {"version": "1.3.0", "module_ref": "scripts/capture_page_evidence.py"},
        "candidate_binding": _binding(),
        "target": {
            "resolved_sha_or_none": "b" * 40,
            "resolved_sha_source": "verified worktree HEAD",
        },
        "pages": pages,
        "excluded": [],
    }


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
    errors = validate_manifest_route_matrix(manifest)
    assert any("reused across distinct routes" in e for e in errors)


def test_query_route_without_query_state_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["query_q"] = None
        state["route_state"]["visible_result_count"] = 0
        state["route_state"]["visible_entry_ids"] = []
    errors = validate_manifest_route_matrix(manifest)
    assert any("query_q" in e or "visible_result_count" in e for e in errors)


def test_unknown_anchor_without_miss_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_visible"] = False
    errors = validate_manifest_route_matrix(manifest)
    assert any("miss_visible" in e for e in errors)


def test_vix_without_focus_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#vix")
    for state in page["states"]:
        state["route_state"]["focused_visible"] = False
        state["route_state"]["target_below_fixed_ui"] = False
    errors = validate_manifest_route_matrix(manifest)
    assert any("focused_visible" in e or "target_below_fixed_ui" in e for e in errors)


def test_duplicate_page_id_is_red():
    manifest = _green_manifest()
    clone = copy.deepcopy(manifest["pages"][0])
    clone["route"] = "reference.html#dup"
    manifest["pages"].append(clone)
    errors = validate_manifest_route_matrix(manifest)
    assert any("duplicate page_id" in e for e in errors)


def test_missing_journeys_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        page.pop("route_journeys", None)
    errors = validate_manifest_route_matrix(manifest)
    assert any("route_journeys" in e for e in errors)


def test_missing_candidate_binding_is_red():
    manifest = _green_manifest()
    manifest.pop("candidate_binding")
    errors = validate_manifest_route_matrix(manifest)
    assert any("candidate_binding" in e for e in errors)


def test_png_byte_mutate_is_red(tmp_path: Path):
    manifest = _green_manifest()
    # Write PNGs that do not match declared digests/bytes/dims.
    for page in manifest["pages"]:
        for state in page["states"]:
            path = tmp_path / state["file"]
            path.write_bytes(b"not-a-png-but-bytes")
    errors = validate_manifest_route_matrix(manifest, evidence_dir=tmp_path)
    assert any("PNG" in e or "hash" in e or "bytes" in e or "dimensions" in e for e in errors)


def test_unexpected_extra_png_is_red(tmp_path: Path):
    manifest = _green_manifest()
    # Minimal valid 1x1 PNG
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"\x00\xff\x00\x00"
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    # Write declared files with matching meta, plus an orphan extra.
    digest = hashlib.sha256(png).hexdigest()
    for page in manifest["pages"]:
        for state in page["states"]:
            state["sha256"] = digest
            state["bytes"] = len(png)
            state["width"] = 1
            state["height"] = 1
            (tmp_path / state["file"]).write_bytes(png)
    (tmp_path / "orphan_extra.png").write_bytes(png)
    errors = validate_manifest_route_matrix(manifest, evidence_dir=tmp_path)
    assert any("unexpected PNG extras" in e for e in errors)


def test_old_tool_version_is_red():
    manifest = _green_manifest()
    manifest["tool"]["version"] = "1.2.0"
    errors = validate_manifest_route_matrix(manifest)
    assert any("tool version" in e for e in errors)


def test_green_matrix_passes():
    assert validate_manifest_route_matrix(_green_manifest()) == []


def test_mor1_capture_rows_cover_four_cases():
    rows = mor1_capture_rows()
    assert [r["capture_route"] for r in rows] == [c["route"] for c in ROUTE_CASES]
    assert len(rows) == 4


def test_template_writes_query_to_url_and_focuses_valid_anchor():
    text = (REPO / "templates" / "reference.html.j2").read_text(encoding="utf-8")
    assert "READ, never written" not in text
    assert "function syncQueryToUrl" in text
    assert "popstate" in text
    assert "searchParams.set(\"q\"" in text or "searchParams.set('q'" in text
    assert "focusEl.focus" in text or ".focus(" in text
    assert "scrollIntoView" in text  # retained, but not alone


def test_direct_checker_bootstrap_importable():
    # scripts/check_market_reference_route_evidence.py must be runnable without
    # an external PYTHONPATH when executed as a file.
    src = (REPO / "scripts" / "check_market_reference_route_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "sys.path.insert" in src
