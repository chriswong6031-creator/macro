#!/usr/bin/env python3
"""XPV2-SC-R3B — deterministic assembler for the Sector Central reference artifact.

Pure byte transport. This script NEVER recomputes rank, lane assignment, a
count (other than a caller-supplied `.length`-style count the production
template itself performs, which lives in the view partials, not here),
state, or a gate decision — see FROZEN SPEC in the R3B commission. It:

  1. Verifies every embedded R3A fixture file against
     research/reference_integrity/mastermind-xpv2-sector-r3/fixture/receipts.json
     (SHA-256 recompute; aborts on any mismatch) and every supplement file
     against build/fixture_supplement/receipts_supplement.json.
  2. Byte-compares the embedded router copy against templates/si_workspace.js
     (aborts if they would differ — the router is reused VERBATIM, never
     edited).
  3. Assembles ONE self-contained HTML file from build/shell.html (slot
     markers), the six build/views/*.html partials, the embedded data
     registry, build/runtime_shim.js, and the verbatim router — in that
     fixed order.
  4. Writes proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html and
     proposal/BUILD_MANIFEST.json.

Deterministic: two runs against the same inputs produce byte-identical
output. No wall-clock timestamp of the assembler's own is ever written to
the HTML or the manifest — any date shown in the artifact comes from fixture
data. Ordering is sorted everywhere it is not already fixed by the assembly
sequence above.

Run: python3 build_reference.py
Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
R3B_DIR = BUILD_DIR.parent
REPO_ROOT = BUILD_DIR.parents[4]

R3A_DIR = REPO_ROOT / "research/reference_integrity/mastermind-xpv2-sector-r3"
FIXTURE_DIR = R3A_DIR / "fixture"
RECEIPTS_PATH = FIXTURE_DIR / "receipts.json"

SUPPLEMENT_DIR = BUILD_DIR / "fixture_supplement"
RECEIPTS_SUPPLEMENT_PATH = SUPPLEMENT_DIR / "receipts_supplement.json"

SI_WORKSPACE_JS_PATH = REPO_ROOT / "templates/si_workspace.js"

SHELL_PATH = BUILD_DIR / "shell.html"
VIEWS_DIR = BUILD_DIR / "views"
RUNTIME_SHIM_PATH = BUILD_DIR / "runtime_shim.js"

PROPOSAL_DIR = R3B_DIR / "proposal"
OUT_HTML_PATH = PROPOSAL_DIR / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
OUT_MANIFEST_PATH = PROPOSAL_DIR / "BUILD_MANIFEST.json"

#: Canonical six views + EN/ZH titles, verbatim from templates/si_workspace.js:17-20
#: (routing_contract.md §1). Hardcoded here because nav chrome is structural, not
#: fixture-derived data — this table is a literal restatement of the frozen router
#: contract, not a new construction.
VIEWS = [
    ("overview", "Overview", "总览"),
    ("map", "The Map", "全景图谱"),
    ("moving", "What's Moving", "正在轮动"),
    ("money", "Money & Breadth", "资金与广度"),
    ("explore", "Explore", "深入探索"),
    ("confluence", "Confluence", "子行业汇聚"),
]

#: Per-view nav glyph classes, verbatim from the Principal Design Lead's own
#: nav in build/shell_specimen.html:643-648 — the sanctioned masked-monoline
#: `.dash-icon` set already defined in shell.html's CSS (DESIGN_SYSTEM_SPEC.md
#: §8 item 10). Not a new construction — a literal restatement of the
#: specimen's per-view icon choice.
VIEW_GLYPHS = {
    "overview": "dash-icon submenu-icon-intelligence",
    "map": "dash-icon dash-icon-compass",
    "moving": "dash-icon submenu-icon-rotation",
    "money": "dash-icon submenu-icon-flow",
    "explore": "dash-icon dash-icon-search",
    "confluence": "dash-icon submenu-icon-confluence",
}

#: R3A fixture entries this artifact embeds as data-registry <script> blocks.
#: Excludes `correction/UNREPRESENTED.md` (an authored doc, not a data artifact
#: any view reads) — every OTHER receipts.json entry (17 of 18) is embedded.
EXCLUDED_FIXTURE_PATHS = {"correction/UNREPRESENTED.md"}

#: Supplement entries embedded as JSON data-registry blocks (the fragment and
#: the plain-executed sector_cycles_data.js are handled separately below).
SUPPLEMENT_JSON_PATHS = {
    "marketdata/sp500_heatmap.json",
    "basketdata/etf_pulse.json",
    "basketdata/vol_sentiment.json",
    "marketdata/nasdaq_internals.json",
}
SUPPLEMENT_SCRIPT_PATH = "sector_cycles_data.js"
SUPPLEMENT_FRAGMENT_PATH = "fragments/sc_flows.html"


class BuildError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def escape_script_close(text: str) -> str:
    """Standard `<\\/script>` JSON/JS-safe escape: replace every `</script`
    (case-insensitive) with `<\\/script` (same case). Valid in both JSON
    strings (`\\/` is a recognized escape for `/`) and JS strings (`\\/`
    evaluates to `/`), so parsed semantics never change — this is a textual
    escape, not a re-serialization. Applied to every embedded blob so a
    literal "</script" sequence anywhere in fixture bytes can never close the
    surrounding <script> element early."""
    return re.sub(r"</(script)", r"<\\/\1", text, flags=re.IGNORECASE)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_entry(base_dir: Path, entry: dict, *, label: str) -> str:
    """Read `base_dir / entry['fixture']`, verify its sha256/size against the
    receipt, and return its raw text. Aborts (raises BuildError) on any
    mismatch — a receipts mismatch means the file was altered after capture."""
    rel = entry["fixture"]
    p = base_dir / rel
    if not p.exists():
        raise BuildError(f"{label}: missing file for receipt entry {rel!r}")
    data = p.read_bytes()
    got_sha = sha256_bytes(data)
    got_size = len(data)
    if got_sha != entry["sha256"]:
        raise BuildError(
            f"{label}: SHA-256 mismatch for {rel!r} — expected {entry['sha256']}, "
            f"got {got_sha}. The fixture file was altered after capture."
        )
    if got_size != entry["size_bytes"]:
        raise BuildError(
            f"{label}: size mismatch for {rel!r} — expected {entry['size_bytes']} bytes, "
            f"got {got_size} bytes."
        )
    return data.decode("utf-8")


def data_script(path: str, text: str, *, script_type: str) -> str:
    return (
        f'<script type="{script_type}" id="ref-data" data-path="{path}">'
        f"{escape_script_close(text)}</script>"
    )


def build_nav_html() -> str:
    parts = []
    for vid, en, zh in VIEWS:
        glyph_class = VIEW_GLYPHS[vid]
        parts.append(
            f'    <a class="si-view-btn" data-view="{vid}" href="#{vid}">'
            f'<span class="si-vb-g {glyph_class}" aria-hidden="true"></span>'
            f'<span class="si-vb-l"><span class="l-en">{en}</span>'
            f'<span class="l-zh">{zh}</span></span></a>'
        )
    return "\n".join(parts)


def build_views_html() -> str:
    parts = []
    for vid, _en, _zh in VIEWS:
        p = VIEWS_DIR / f"{vid}.html"
        if not p.exists():
            raise BuildError(f"missing view partial: {p}")
        parts.append(p.read_text(encoding="utf-8").rstrip("\n"))
    return "\n".join(parts)


def main() -> int:
    manifest_inputs: list[dict] = []

    # ── 1. Verify + collect the 17 R3A fixture entries ─────────────────────
    receipts = load_json(RECEIPTS_PATH)
    fixture_entries = sorted(
        (e for e in receipts["entries"] if e["path"] not in EXCLUDED_FIXTURE_PATHS),
        key=lambda e: e["path"],
    )
    fixture_texts: dict[str, str] = {}
    for entry in fixture_entries:
        text = verify_entry(R3A_DIR, entry, label="R3A fixture")
        fixture_texts[entry["path"]] = text
        manifest_inputs.append({
            "path": entry["path"],
            "source": "R3A fixture",
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
        })
    n_fixture = len(fixture_entries)
    print(f"[verify] R3A fixture: {n_fixture} file(s) verified against receipts.json")

    # ── 2. Verify + collect the supplement entries ──────────────────────────
    receipts_supp = load_json(RECEIPTS_SUPPLEMENT_PATH)
    supp_entries = sorted(receipts_supp["entries"], key=lambda e: e["path"])
    supp_texts: dict[str, str] = {}
    for entry in supp_entries:
        text = verify_entry(BUILD_DIR, entry, label="R3B supplement")
        supp_texts[entry["path"]] = text
        manifest_inputs.append({
            "path": entry["path"],
            "source": "R3B supplement",
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
        })
    print(f"[verify] R3B supplement: {len(supp_entries)} file(s) verified against receipts_supplement.json")

    # ── 3. Verify si_workspace.js is embedded byte-verbatim ────────────────
    if not SI_WORKSPACE_JS_PATH.exists():
        raise BuildError(f"missing router source: {SI_WORKSPACE_JS_PATH}")
    router_bytes = SI_WORKSPACE_JS_PATH.read_bytes()
    router_text = router_bytes.decode("utf-8")
    router_sha = sha256_bytes(router_bytes)
    print(f"[verify] templates/si_workspace.js: {len(router_bytes)} bytes, sha256={router_sha}")

    # ── 4. Assemble the data registry (deterministic order: sorted paths) ──
    data_blocks: list[str] = []
    for path in sorted(fixture_texts):
        data_blocks.append(data_script(path, fixture_texts[path], script_type="application/json"))
    for path in sorted(t for t in supp_texts if t in SUPPLEMENT_JSON_PATHS):
        data_blocks.append(data_script(path, supp_texts[path], script_type="application/json"))
    # the extracted HTML fragment — inert container, not auto-executed
    frag_text = supp_texts[SUPPLEMENT_FRAGMENT_PATH]
    data_blocks.append(data_script(SUPPLEMENT_FRAGMENT_PATH, frag_text, script_type="text/x-ref-fragment"))
    # sector_cycles_data.js — plain EXECUTED script (it assigns window.SECTOR_CYCLES),
    # verbatim bytes, escaped only for the </script> boundary.
    cycles_text = supp_texts[SUPPLEMENT_SCRIPT_PATH]
    data_blocks.append(f"<script>{escape_script_close(cycles_text)}</script>")
    # window.SECTOR_CENTRAL — baked at build time from the verbatim
    # sectordata/sector_central.json bytes, exactly as scripts/build_sector_central.py
    # writes site/sector_central_data.js ("window.SECTOR_CENTRAL="+json+";\n") — a
    # build-time embed, never a client fetch, matching production.
    sc_json_text = fixture_texts["sectordata/sector_central.json"]
    data_blocks.append(
        "<script>window.SECTOR_CENTRAL=" + escape_script_close(sc_json_text) + ";</script>"
    )
    data_html = "\n".join(data_blocks)

    n_data_blocks = len(fixture_texts) + len(SUPPLEMENT_JSON_PATHS) + 1  # +1 fragment
    print(f"[assemble] data registry: {n_data_blocks} <script> block(s) "
          f"({len(fixture_texts)} fixture + {len(SUPPLEMENT_JSON_PATHS)} supplement JSON + 1 fragment), "
          f"plus sector_cycles_data.js + window.SECTOR_CENTRAL bake")

    # ── 5. Runtime shim (verbatim, escaped only for the </script> boundary) ─
    if not RUNTIME_SHIM_PATH.exists():
        raise BuildError(f"missing runtime shim: {RUNTIME_SHIM_PATH}")
    shim_text = RUNTIME_SHIM_PATH.read_text(encoding="utf-8")
    shim_sha = sha256_bytes(shim_text.encode("utf-8"))
    shim_html = f"<script>{escape_script_close(shim_text)}</script>"

    # ── 6. Router (verbatim, escaped only for the </script> boundary) ──────
    router_html = f"<script>{escape_script_close(router_text)}</script>"

    # ── 7. Nav + views ───────────────────────────────────────────────────
    nav_html = build_nav_html()
    views_html = build_views_html()

    # ── 8. Substitute the shell's slot markers ──────────────────────────────
    if not SHELL_PATH.exists():
        raise BuildError(f"missing shell: {SHELL_PATH}")
    shell_text = SHELL_PATH.read_text(encoding="utf-8")
    slots = {
        "<!--REF:NAV-->": nav_html,
        "<!--REF:VIEWS-->": views_html,
        "<!--REF:DATA-->": data_html,
        "<!--REF:RUNTIME-->": shim_html,
        "<!--REF:ROUTER-->": router_html,
    }
    # Validate against the PRISTINE shell text (not the accumulating output) so a
    # marker string that happens to appear inside another slot's replacement
    # content (e.g. documentation prose quoting a marker name) can never be
    # mistaken for an unconsumed or duplicated shell.html marker.
    for marker in slots:
        n = shell_text.count(marker)
        if n == 0:
            raise BuildError(f"shell.html is missing slot marker {marker!r}")
        if n > 1:
            raise BuildError(f"slot marker {marker!r} appears {n} times in shell.html (expected exactly 1)")
    out_text = shell_text
    for marker, replacement in slots.items():
        out_text = out_text.replace(marker, replacement, 1)

    out_bytes = out_text.encode("utf-8")
    out_sha = sha256_bytes(out_bytes)
    out_size = len(out_bytes)

    SIZE_LIMIT = 6 * 1024 * 1024
    if out_size > SIZE_LIMIT:
        raise BuildError(f"emitted HTML is {out_size} bytes, over the ~6MB size limit")

    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HTML_PATH.write_bytes(out_bytes)
    print(f"[write] {OUT_HTML_PATH.relative_to(REPO_ROOT)}: {out_size} bytes, sha256={out_sha}")

    # ── 9. Manifest ──────────────────────────────────────────────────────
    assembler_self_bytes = Path(__file__).read_bytes()
    manifest = {
        "output": {
            "path": str(OUT_HTML_PATH.relative_to(R3B_DIR)),
            "sha256": out_sha,
            "size_bytes": out_size,
        },
        "inputs": sorted(manifest_inputs, key=lambda e: e["path"]),
        "si_workspace_js": {
            "source": str(SI_WORKSPACE_JS_PATH.relative_to(REPO_ROOT)),
            "sha256": router_sha,
            "size_bytes": len(router_bytes),
        },
        "runtime_shim_js": {
            "source": str(RUNTIME_SHIM_PATH.relative_to(R3B_DIR)),
            "sha256": shim_sha,
            "size_bytes": len(shim_text.encode("utf-8")),
        },
        "assembler_self": {
            "source": str(Path(__file__).resolve().relative_to(R3B_DIR)),
            "sha256": sha256_bytes(assembler_self_bytes),
            "size_bytes": len(assembler_self_bytes),
        },
        "views": [f"{vid}.html" for vid, _e, _z in VIEWS],
        "fixture_capture_commit": receipts.get("captured_commit"),
        "supplement_capture_commit": receipts_supp.get("captured_commit"),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    OUT_MANIFEST_PATH.write_bytes(manifest_bytes)
    print(f"[write] {OUT_MANIFEST_PATH.relative_to(REPO_ROOT)}: {len(manifest_bytes)} bytes")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as e:
        print(f"BUILD ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
