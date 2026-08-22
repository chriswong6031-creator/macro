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

    # ── (j)/(k) committed browser-gate artifacts (not rerun here) ────────
    check_committed_zoom_sweep()
    check_committed_contrast_audit()

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
