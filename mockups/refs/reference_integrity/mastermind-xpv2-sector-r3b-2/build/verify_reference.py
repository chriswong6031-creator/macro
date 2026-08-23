#!/usr/bin/env python3
"""XPV2-SC-R3B — standalone verification for the assembled reference artifact.

Not a pytest file (deliberately NOT named test_*, per the commission's
OUT-OF-SCOPE instruction — this harness's checks must not couple into the
repo's tests/ CI packs). Run directly:

    python3 verify_reference.py

Checks:
  (a) rebuild determinism — two independent builds are byte-identical.
  (b) every receipts.json + receipts_supplement.json hash verifies against
      the files build_reference.py actually read (recomputed here too, not
      just trusted from the build's own log).
  (c) the emitted HTML contains one data block per required production-relative
      path, and zero `href="#"` occurrences.
  (d) the embedded si_workspace.js bytes equal templates/si_workspace.js bytes
      (modulo only the documented </script>-boundary escape).
  (e) output size is under the ~6MB limit.
  (f) R3B1-14 bidirectional capability inventory, both directions
      (inventory_check.py) — expected production inventory -> candidate, and
      candidate -> allowed production/projection inventory.
  (g) R3B1-14 unique-kill mutation suite (mutation_suite.py) — every pinned
      hero capability's removal produces a unique, non-empty red.
  (h) duplicate-ID / ARIA-reference audit (aria_id_audit.py).
  (i) EN/ZH document-language probe (lang_probe.py).
  (j) severe-zoom clipping matrix — asserts the committed
      lane_crops_b/zoom_sweep.json artifact exists and reports 0 failing
      cells (from committed artifact; NOT rerun here — browser-based gate).
  (k) contrast matrix — asserts the committed lane_crops_b/CONTRAST_TABLE.md
      + lane_crops_b/contrast_audit.json artifacts exist and report 0 AA
      failures (from committed artifact; NOT rerun here — browser-based gate).
  NOTE — heatmap colour-field axis (Sol FINAL CONTINUATION HANDOFF S4): the ~440
      shadowed .hm-t glyphs over the data-driven colour field are UNMEASURED by the
      flat-surface contrast method. This verifier REPORTS that axis and never
      converts UNMEASURED into PASS or FAIL; final legibility review is a
      human/appropriate-method task carried to R3C/design-system.

Checks (f)-(i) shell out to Playwright-based sibling scripts in this
directory and therefore need a Playwright-enabled Python interpreter to run
this file at all (the checks above, (a)-(e), are pure stdlib and do not).

Exits 0 iff every check passes; prints a PASS/FAIL line per check, and a
final quotable summary block.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
R3B_DIR = BUILD_DIR.parent
REPO_ROOT = BUILD_DIR.parents[4]

R3A_DIR = REPO_ROOT / "research/reference_integrity/mastermind-xpv2-sector-r3"
RECEIPTS_PATH = R3A_DIR / "fixture" / "receipts.json"
RECEIPTS_SUPPLEMENT_PATH = BUILD_DIR / "fixture_supplement" / "receipts_supplement.json"
SI_WORKSPACE_JS_PATH = REPO_ROOT / "templates/si_workspace.js"

PROPOSAL_DIR = R3B_DIR / "proposal"
OUT_HTML_PATH = PROPOSAL_DIR / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
OUT_MANIFEST_PATH = PROPOSAL_DIR / "BUILD_MANIFEST.json"

BUILD_SCRIPT = BUILD_DIR / "build_reference.py"
INVENTORY_CHECK_SCRIPT = BUILD_DIR / "inventory_check.py"
MUTATION_SUITE_SCRIPT = BUILD_DIR / "mutation_suite.py"
ARIA_ID_AUDIT_SCRIPT = BUILD_DIR / "aria_id_audit.py"
LANG_PROBE_SCRIPT = BUILD_DIR / "lang_probe.py"

LANE_CROPS_B = BUILD_DIR / "lane_crops_b"
ZOOM_SWEEP_JSON = LANE_CROPS_B / "zoom_sweep.json"
CONTRAST_TABLE_MD = LANE_CROPS_B / "CONTRAST_TABLE.md"
CONTRAST_AUDIT_JSON = LANE_CROPS_B / "contrast_audit.json"
FIG_NAMING_JSON = BUILD_DIR / "fig_naming_audit.json"
TREEMAP_LABELS_JSON = BUILD_DIR / "treemap_labels_audit.json"
MOBILE_GEOMETRY_JSON = BUILD_DIR / "mobile_geometry_audit.json"
CLOSURE_AUDIT_JSON = BUILD_DIR / "closure_audit.json"
CLOSURE_MUTATION_JSON = BUILD_DIR / "closure_mutation_results.json"
STATE_SMOKE_JSON = BUILD_DIR / "state_smoke.json"

SIZE_LIMIT = 6 * 1024 * 1024

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_build(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        cwd=str(cwd), capture_output=True, text=True,
    )


def main() -> int:
    if not OUT_HTML_PATH.exists():
        print("Output does not exist yet — running build_reference.py once first.")
        r = run_build(BUILD_DIR)
        if r.returncode != 0:
            check("initial build succeeds", False, r.stderr.strip())
            print_summary()
            return 1

    html_bytes = OUT_HTML_PATH.read_bytes()

    # ── (a) rebuild determinism ──────────────────────────────────────────
    before_sha = sha256_bytes(html_bytes)
    r1 = run_build(BUILD_DIR)
    after1_bytes = OUT_HTML_PATH.read_bytes()
    after1_sha = sha256_bytes(after1_bytes)
    r2 = run_build(BUILD_DIR)
    after2_bytes = OUT_HTML_PATH.read_bytes()
    after2_sha = sha256_bytes(after2_bytes)
    det_ok = (r1.returncode == 0 and r2.returncode == 0
              and after1_sha == after2_sha == before_sha)
    check("(a) rebuild determinism (2 rebuilds byte-identical)", det_ok,
          f"before={before_sha[:12]} run1={after1_sha[:12]} run2={after2_sha[:12]}")
    html_bytes = after2_bytes  # use the freshest build for the remaining checks

    # ── (b) receipts hashes verify ───────────────────────────────────────
    receipts = json.loads(RECEIPTS_PATH.read_text(encoding="utf-8"))
    fixture_ok = True
    n_fixture_checked = 0
    for entry in receipts["entries"]:
        p = R3A_DIR / entry["fixture"]
        if not p.exists():
            fixture_ok = False
            print(f"       missing fixture file: {entry['fixture']}")
            continue
        got = sha256_file(p)
        n_fixture_checked += 1
        if got != entry["sha256"]:
            fixture_ok = False
            print(f"       MISMATCH {entry['fixture']}: expected {entry['sha256']}, got {got}")
    check("(b1) R3A fixture receipts verify", fixture_ok, f"{n_fixture_checked} entries checked")

    receipts_supp = json.loads(RECEIPTS_SUPPLEMENT_PATH.read_text(encoding="utf-8"))
    supp_ok = True
    n_supp_checked = 0
    for entry in receipts_supp["entries"]:
        p = BUILD_DIR / entry["fixture"]
        if not p.exists():
            supp_ok = False
            print(f"       missing supplement file: {entry['fixture']}")
            continue
        got = sha256_file(p)
        n_supp_checked += 1
        if got != entry["sha256"]:
            supp_ok = False
            print(f"       MISMATCH {entry['fixture']}: expected {entry['sha256']}, got {got}")
    check("(b2) R3B supplement receipts verify", supp_ok, f"{n_supp_checked} entries checked")

    # ── (c) required data blocks present + zero href="#" ────────────────
    html_text = html_bytes.decode("utf-8")
    # sector_cycles_data.js is deliberately NOT a data-path block — spec calls
    # for it to embed as a plain EXECUTED <script> (it assigns
    # window.SECTOR_CYCLES), same as the window.SECTOR_CENTRAL bake. Both are
    # checked separately below instead of via the data-path marker.
    required_paths = sorted(
        [e["path"] for e in receipts["entries"] if e["path"] != "correction/UNREPRESENTED.md"]
        + [e["path"] for e in receipts_supp["entries"]
           if e["path"] not in ("fragments/sc_flows.html", "sector_cycles_data.js")]
    )
    missing = []
    for path in required_paths:
        marker = f'data-path="{path}"'
        if marker not in html_text:
            missing.append(path)
    check("(c1) one data block per required production-relative path", not missing,
          f"{len(required_paths)} required, missing: {missing}" if missing else f"{len(required_paths)} present")

    check("(c1b) sc_flows.html fragment block present",
          'data-path="fragments/sc_flows.html"' in html_text and
          'type="text/x-ref-fragment"' in html_text)
    check("(c1c) sector_cycles_data.js embedded as plain executed script",
          "window.SECTOR_CYCLES=" in html_text)
    check("(c1d) window.SECTOR_CENTRAL baked from fixture bytes",
          "window.SECTOR_CENTRAL=" in html_text)

    href_hash_count = len(re.findall(r'href="#"', html_text))
    check("(c2) zero href=\"#\" placeholders", href_hash_count == 0, f"found {href_hash_count}")

    # ── (d) si_workspace.js embedded byte-verbatim (modulo </script> escape) ─
    router_text = SI_WORKSPACE_JS_PATH.read_text(encoding="utf-8")
    router_escaped = re.sub(r"</(script)", r"<\\/\1", router_text, flags=re.IGNORECASE)
    router_sha = sha256_bytes(router_text.encode("utf-8"))
    manifest = json.loads(OUT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_router_sha = manifest.get("si_workspace_js", {}).get("sha256")
    router_present = router_escaped in html_text
    check("(d) si_workspace.js embedded verbatim", router_present and manifest_router_sha == router_sha,
          f"manifest sha256={manifest_router_sha}, recomputed={router_sha}, substring present={router_present}")

    # ── (e) size under limit ─────────────────────────────────────────────
    size = len(html_bytes)
    check("(e) output size under limit", size <= SIZE_LIMIT,
          f"{size} bytes ({size/1024/1024:.2f} MiB) vs {SIZE_LIMIT} byte limit")

    # ── (f) R3B1-14 bidirectional capability inventory ──────────────────
    run_inventory_and_mutation_checks()

    # ── (h) duplicate-ID / ARIA-reference audit ──────────────────────────
    run_sibling_script_check(
        "(h) duplicate-ID / ARIA-reference audit (aria_id_audit.py)",
        [sys.executable, str(ARIA_ID_AUDIT_SCRIPT)],
    )

    # ── (i) EN/ZH document-language probe ────────────────────────────────
    run_sibling_script_check(
        "(i) EN/ZH document-language probe (lang_probe.py)",
        [sys.executable, str(LANG_PROBE_SCRIPT)],
    )

    # ── (j)/(k)/(l) committed browser-gate artifacts (not rerun here) ────
    check_committed_zoom_sweep()
    check_committed_contrast_audit()
    report_heatmap_unmeasured_axis()

    # ── (m)/(n)/(o) Lane B responsive/a11y geometry artifacts ────────────
    check_committed_fig_naming_audit()
    check_committed_treemap_labels_audit()
    check_committed_mobile_geometry_audit()
    check_committed_closure_audit()
    check_committed_closure_mutations()
    check_committed_state_smoke()

    return print_summary()


def run_sibling_script_check(name: str, cmd: list[str]) -> None:
    r = subprocess.run(cmd, cwd=str(BUILD_DIR), capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    tail_lines = [ln for ln in out.strip().splitlines() if ln.strip()][-3:]
    detail = " | ".join(tail_lines) if tail_lines else f"rc={r.returncode}, no output"
    check(name, r.returncode == 0, detail)


def run_inventory_and_mutation_checks() -> None:
    if not INVENTORY_CHECK_SCRIPT.exists() or not MUTATION_SUITE_SCRIPT.exists():
        check("(f) R3B1-14 bidirectional capability inventory (both directions)", False,
              "inventory_check.py or mutation_suite.py missing")
        check("(g) R3B1-14 unique-kill mutation suite", False, "prerequisite script missing")
        return

    r = subprocess.run(
        [sys.executable, str(INVENTORY_CHECK_SCRIPT)],
        cwd=str(BUILD_DIR), capture_output=True, text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    n_pass_d1 = out.count("[PASS] D1")
    n_fail_d1 = out.count("[FAIL] D1")
    n_pass_d2 = out.count("[PASS] D2")
    n_fail_d2 = out.count("[FAIL] D2")
    summary_line = next((ln for ln in reversed(out.strip().splitlines())
                          if "inventory checks passed" in ln), out.strip().splitlines()[-1] if out.strip() else "")
    check("(f) R3B1-14 bidirectional capability inventory (both directions)",
          r.returncode == 0,
          f"direction1(expected->candidate) {n_pass_d1} pass / {n_fail_d1} fail; "
          f"direction2(candidate->allowed) {n_pass_d2} pass / {n_fail_d2} fail; {summary_line.strip()}")

    r2 = subprocess.run(
        [sys.executable, str(MUTATION_SUITE_SCRIPT)],
        cwd=str(BUILD_DIR), capture_output=True, text=True,
    )
    out2 = (r2.stdout or "") + (r2.stderr or "")
    summary_line2 = next((ln for ln in reversed(out2.strip().splitlines())
                           if "mutation-suite checks passed" in ln), out2.strip().splitlines()[-1] if out2.strip() else "")
    n_got_red = out2.count("produced a red")
    check("(g) R3B1-14 unique-kill mutation suite (every capability's removal is a unique red)",
          r2.returncode == 0,
          f"{n_got_red} mutation lines evaluated; {summary_line2.strip()}")


def check_committed_zoom_sweep() -> None:
    if not ZOOM_SWEEP_JSON.exists():
        check("(j) severe zoom matrix (from committed artifact)", False,
              f"missing {ZOOM_SWEEP_JSON}")
        return
    cells = json.loads(ZOOM_SWEEP_JSON.read_text(encoding="utf-8"))
    failing = [c for c in cells if not c.get("pass", False)]
    check("(j) severe zoom matrix (from committed artifact)", not failing,
          f"{len(cells)} cells swept, {len(failing)} failing "
          f"(lane_crops_b/zoom_sweep.json, reproduce with `<playwright-python> zoom_sweep.py`)")


def check_committed_contrast_audit() -> None:
    if not CONTRAST_TABLE_MD.exists() or not CONTRAST_AUDIT_JSON.exists():
        check("(k) contrast matrix (from committed artifact)", False,
              f"missing {CONTRAST_TABLE_MD} or {CONTRAST_AUDIT_JSON}")
        return
    table_text = CONTRAST_TABLE_MD.read_text(encoding="utf-8")
    m = re.search(r"\|\s*AA failures\s*\|\s*\*\*(\d+)\*\*\s*\|", table_text)
    table_aa_failures = int(m.group(1)) if m else None

    audit = json.loads(CONTRAST_AUDIT_JSON.read_text(encoding="utf-8"))
    cells = audit.get("cells", [])
    scored = [c for c in cells if c.get("scope") == "reference_authored"]
    json_fails = [c for c in scored if not c.get("pass") and not c.get("suspect_parse")]

    ok = (m is not None and table_aa_failures == 0 and len(json_fails) == 0
          and table_aa_failures == len(json_fails))
    check("(k) contrast matrix (from committed artifact)", ok,
          f"CONTRAST_TABLE.md declares AA failures={table_aa_failures}; "
          f"contrast_audit.json recomputes {len(json_fails)} failing of "
          f"{len(scored)} reference-authored cells "
          f"(reproduce with `<playwright-python> contrast_audit.py`)")


def report_heatmap_unmeasured_axis() -> None:
    """Sol FINAL CONTINUATION HANDOFF S4 (old B2-03 RECLASSIFIED): the candidate-owned
    .hm-t colour-field text (~440 shadowed glyphs over a data-driven colour field) is
    UNMEASURED by the flat-surface contrast method. Report the axis honestly; NEVER
    convert UNMEASURED into PASS (and never into FAIL without a valid method). Final
    legibility review = human/appropriate-method, carried to R3C/design-system."""
    print("NOTE  heatmap colour-field axis: UNMEASURED by flat-surface method "
          "(~440 shadowed .hm-t glyphs) — reported, not scored; never PASS "
          "(Sol handoff S4; final review carried to R3C/design-system)")


def _load_audit(path: Path, name: str) -> dict | None:
    """Shared loader for the committed browser-gate artifacts. A missing or
    self-declared-error artifact is a FAILING check, never a skipped one."""
    if not path.exists():
        check(name, False, f"missing {path}")
        return None
    audit = json.loads(path.read_text(encoding="utf-8"))
    if audit.get("error"):
        check(name, False, f"audit reported an error: {audit['error']}")
        return None
    if not audit.get("cells"):
        check(name, False, "audit recorded zero cells (empty sweep)")
        return None
    return audit


def check_committed_fig_naming_audit() -> None:
    """(m) B2-05 — every `.r3-fig` names its own figure at every width.

    Consumes the committed `fig_naming_audit.json`. The gate is the artifact's
    own per-cell failure list PLUS the census assertions re-derived here, so a
    future edit that quietly drops figures out of the sweep cannot pass by
    reporting "0 failures" over an empty population."""
    name = "(m) B2-05 .r3-fig visible/AT naming by breakpoint (from committed artifact)"
    audit = _load_audit(FIG_NAMING_JSON, name)
    if audit is None:
        return
    cells = audit["cells"]
    expected = audit.get("expected_census_per_cell", 0)
    census_bad = [c for c in cells if c["census"] != expected or c["census"] == 0]
    unnamed = sum(len(c["unnamed"]) for c in cells)
    naked = sum(len(c["naked_visible"]) for c in cells)
    doubled = sum(len(c["double_labelled"]) for c in cells)
    proofs = [p for c in cells for p in c["proofs"]]
    proofs_failed = [p for p in proofs if not p["pass"]]
    failing = [c for c in cells if c["failures"]]
    hash_bound = audit.get("candidate_sha256") == sha256_file(OUT_HTML_PATH)
    ok = (bool(cells) and expected > 0 and not census_bad and not unnamed
          and not naked and not doubled and bool(proofs) and not proofs_failed
          and not failing and audit.get("pass") is True and hash_bound)
    check(name, ok,
          f"{len(cells)} cells (1440/390/320 x EN/ZH, six views each), "
          f"census {expected}/cell, {unnamed} valued figure(s) with no accessible name, "
          f"{naked} painted figure(s) with no visible name at "
          f"<={audit.get('mobile_breakpoint_px')}px, {doubled} double-labelled above the "
          f"breakpoint, commissioned visible-label proofs "
          f"{len(proofs) - len(proofs_failed)}/{len(proofs)} passing, "
          f"{len(failing)} failing cell(s), candidate hash bound={hash_bound} "
          f"(reproduce with `<playwright-python> fig_naming_audit.py`)")


def check_committed_treemap_labels_audit() -> None:
    """(n) B2-06 — painted-label collision for the candidate-owned treemap
    (old B2-07 withdrawn per Sol handoff S4; interactive census reported, and the
    natively-true zero-interactive invariant still gates). Consumes
    `treemap_labels_audit.json`."""
    name = "(n) B2-06 treemap painted-label collision (+ reported interactive census) (from committed artifact)"
    audit = _load_audit(TREEMAP_LABELS_JSON, name)
    if audit is None:
        return
    cells = audit["cells"]
    zero_census = [c for c in cells
                   if not c.get("tiles") or not c.get("painted_labels")
                   or not c.get("sector_names")]
    overlaps = sum(len(c["overlaps"]) for c in cells)
    interactive = sum(c.get("interactive_in_map") or 0 for c in cells)
    subfloor = sum(len(c.get("sub_floor_interactive") or []) for c in cells)
    failing = [c for c in cells if c["failures"]]
    ok = (bool(cells) and not zero_census and not overlaps and not interactive
          and not subfloor and not failing and audit.get("pass") is True)
    check(name, ok,
          f"{len(cells)} cells (320/390/820 x EN/ZH x dark/light), "
          f"{sum(c['tiles'] or 0 for c in cells)} tiles and "
          f"{sum(c['painted_labels'] or 0 for c in cells)} painted labels measured, "
          f"{overlaps} cross-owner label overlap(s), {interactive} interactive element(s) "
          f"inside the treemap, {subfloor} under the "
          f"{audit.get('touch_floor_px')}px target floor, "
          f"{len(zero_census)} cell(s) with an empty census, {len(failing)} failing cell(s) "
          f"(reproduce with `<playwright-python> treemap_labels_audit.py`)")


def check_committed_mobile_geometry_audit() -> None:
    """(o) B2-10 + B2-11 (+ MAC1-002, PRC1R-001) — the mobile geometry relations.
    Consumes `mobile_geometry_audit.json`."""
    name = "(o) B2-10/B2-11 mobile ramp + headline-receipt flow geometry (from committed artifact)"
    audit = _load_audit(MOBILE_GEOMETRY_JSON, name)
    if audit is None:
        return
    cells = audit["cells"]
    # B2-10 must be discriminating in BOTH directions: at least one cell where
    # the ledge is a five-track row and the ramp IS painted, and at least one
    # where it stacks and the ramp is NOT.
    ramp_on = [c for c in cells if c["ramp"].get("tracks") == 5 and c["ramp"].get("ramp_painted")]
    ramp_off = [c for c in cells if c["ramp"].get("tracks", 5) < 5 and not c["ramp"].get("ramp_painted")]
    receipt_ok = [c for c in cells
                  if (c["receipt"].get("on_last_line") or c["receipt"].get("after_last_line"))
                  and c["receipt"].get("inside_content_box")
                  and c["receipt"].get("inside_viewport")]
    btn_census = sum(c.get("textbtn_census") or 0 for c in cells)
    under_floor = sum(len(c.get("textbtn_under_floor") or []) for c in cells)
    zh_shou_qi = audit.get("zh_shou_qi_controls_measured", 0)
    aria_ok = [c for c in cells if c["aria"].get("aria_controls") == "r3-receipt"
               and c["aria"].get("panel_present")]
    failing = [c for c in cells if c["failures"]]
    ok = (bool(cells) and bool(ramp_on) and bool(ramp_off)
          and len(receipt_ok) == len(cells) and btn_census > 0 and not under_floor
          and zh_shou_qi > 0 and len(aria_ok) == len(cells)
          and not failing and audit.get("pass") is True)
    check(name, ok,
          f"{len(cells)} cells (1440/390/320 at 100% + 390/320 at 200% zoom, x EN/ZH); "
          f"B2-10 ramp painted in {len(ramp_on)} five-track cell(s) and suppressed in "
          f"{len(ramp_off)} stacked cell(s); B2-11 receipt flows with the final wrapped line in "
          f"{len(receipt_ok)}/{len(cells)}; MAC1-002 {btn_census} .r3-textbtn measured "
          f"({zh_shou_qi} ZH 收起), {under_floor} under the {audit.get('target_floor_px')}px floor; "
          f"PRC1R-001 aria-controls resolved in {len(aria_ok)}/{len(cells)}; "
          f"{len(failing)} failing cell(s) "
          f"(reproduce with `<playwright-python> mobile_geometry_audit.py`)")


def check_committed_closure_audit() -> None:
    """(p) Rendered customer terms, producer-derived qualification scope and
    shared receipt wiring for the final continuation."""
    name = "(p) B2-01/B2-12/B2-13/B2-15 rendered closure semantics (from committed artifact)"
    audit = _load_audit(CLOSURE_AUDIT_JSON, name)
    if audit is None:
        return
    cells = audit["cells"]
    checks = [c for cell in cells for c in cell.get("checks", [])]
    failing = [c for c in checks if not c.get("pass")]
    expected_ids = {
        "b2_01.overview_header", "b2_01.overview_inline_census", "b2_01.map_header",
        "b2_01.map_detail", "b2_01.map_tooltip", "b2_01.one_path_one_term",
        "b2_12.coverage_fact", "b2_12.low_confidence_census",
        "b2_12.low_confidence_term", "b2_12.distinct_authority_terms",
        "b2_13.shared_target", "b2_13.overview_control", "b2_13.moving_controls",
        "b2_13.exact_shared_control_census", "b2_15.producer_scope",
        "b2_15.qualification_present", "b2_15.localized_clauses",
        "b2_15.qualification_excludes_21d", "b2_15.explicit_21d_line",
        "b2_15.visual_separation",
    }
    by_lang = {cell.get("lang"): {c.get("id") for c in cell.get("checks", [])} for cell in cells}
    complete = set(by_lang) == {"en", "zh"} and all(ids == expected_ids for ids in by_lang.values())
    hash_bound = audit.get("candidate_sha256") == sha256_file(OUT_HTML_PATH)
    ok = (complete and not failing and audit.get("failed_check_ids") == []
          and audit.get("pass") is True and hash_bound)
    check(name, ok,
          f"{len(checks)-len(failing)}/{len(checks)} checks pass across EN/ZH; "
          f"complete id census={complete}; candidate hash bound={hash_bound} "
          f"(reproduce with `<playwright-python> closure_audit.py`)")


def check_committed_closure_mutations() -> None:
    """(q) Every final-continuation guard is discriminating, not pre-true."""
    name = "(q) R3B.2 closure unique-red mutation proof (from committed artifact)"
    if not CLOSURE_MUTATION_JSON.exists():
        check(name, False, f"missing {CLOSURE_MUTATION_JSON}")
        return
    audit = json.loads(CLOSURE_MUTATION_JSON.read_text(encoding="utf-8"))
    rows = audit.get("mutations") or []
    nonempty = [r for r in rows if r.get("got_red") and r.get("failed_check_ids")]
    failing_sets = [frozenset(r.get("failed_check_ids") or []) for r in rows]
    hash_bound = audit.get("candidate_sha256") == sha256_file(OUT_HTML_PATH)
    baseline = audit.get("baseline") or {}
    ok = (len(rows) == 8 and len(nonempty) == 8 and len(set(failing_sets)) == 8
          and baseline == {"fig": True, "closure": True}
          and audit.get("pairwise_distinct") is True and not audit.get("collisions")
          and audit.get("pass") is True and hash_bound)
    check(name, ok,
          f"{len(nonempty)}/{len(rows)} mutations produced non-empty reds; "
          f"distinct sets={len(set(failing_sets))}; baselines={baseline}; "
          f"candidate hash bound={hash_bound} "
          f"(reproduce with `<playwright-python> closure_mutation_suite.py`)")


def check_committed_state_smoke() -> None:
    """(r) Hash routing, access-state arithmetic and active-universe isolation."""
    name = "(r) canonical/legacy hash + access + four-universe state smoke (from committed artifact)"
    if not STATE_SMOKE_JSON.exists():
        check(name, False, f"missing {STATE_SMOKE_JSON}")
        return
    audit = json.loads(STATE_SMOKE_JSON.read_text(encoding="utf-8"))
    hashes = audit.get("hashes") or {}
    universes = audit.get("confluence_universes") or []
    hash_bound = audit.get("candidate_sha256") == sha256_file(OUT_HTML_PATH)
    ok = (audit.get("pass") is True and audit.get("failed_check_ids") == []
          and hashes.get("canonical_pass") == 6 and hashes.get("legacy_view_pass") == 21
          and hashes.get("legacy_target_present") == 20
          and (audit.get("access") or {}).get("pass") is True
          and len(universes) == 4 and all(u.get("pass") for u in universes)
          and audit.get("href_hash_count") == 0 and hash_bound)
    check(name, ok,
          f"canonical={hashes.get('canonical_pass')}/6, legacy views={hashes.get('legacy_view_pass')}/21, "
          f"legacy targets={hashes.get('legacy_target_present')}/21 (#sc-top documented absent), "
          f"access pass={(audit.get('access') or {}).get('pass')}, "
          f"universes={sum(1 for u in universes if u.get('pass'))}/{len(universes)}, "
          f"href=# count={audit.get('href_hash_count')}, candidate hash bound={hash_bound} "
          f"(reproduce with `<playwright-python> state_smoke.py`)")


def print_summary() -> int:
    n_pass = sum(1 for _n, ok, _d in results if ok)
    n_total = len(results)
    all_green = n_pass == n_total
    print(f"\n{n_pass}/{n_total} checks passed.")

    print("\n" + "=" * 78)
    print("R3B1-14 VERIFICATION SUMMARY — quotable")
    print("=" * 78)
    for i, (name, ok, _detail) in enumerate(results, 1):
        print(f"{i:2}. [{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 78)
    print(f"RESULT: {'ALL GREEN' if all_green else 'RED'} — {n_pass}/{n_total} checks passed "
          f"(candidate {OUT_HTML_PATH.name})")
    print("=" * 78)

    return 0 if all_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
