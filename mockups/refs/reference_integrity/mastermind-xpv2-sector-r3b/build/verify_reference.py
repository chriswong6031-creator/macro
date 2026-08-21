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

Exits 0 iff every check passes; prints a PASS/FAIL line per check.
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

    return print_summary()


def print_summary() -> int:
    n_pass = sum(1 for _n, ok, _d in results if ok)
    n_total = len(results)
    print(f"\n{n_pass}/{n_total} checks passed.")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
