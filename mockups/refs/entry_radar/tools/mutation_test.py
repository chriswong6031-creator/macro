#!/usr/bin/env python3
"""Mutation battery for the W8 Radar RIG.

Each mutation is applied to a temp copy of the reference tree. verify.py must
FAIL, and the named check must be among the failures. A check that cannot
detect its mutation is not evidence.

Usage: python3 tools/mutation_test.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools" / "verify.py"

# (id, file, find, replace, must_fail_check_prefix)
MUTATIONS = [
    ("M1-flatten-experts", "radar-data.js",
     'G0: { id: "G0_GREY_DOT@1"',
     'entry_signal: { id: "GENERIC_ENTRY"',
     "R3h"),
    ("M2-c4-fires", "radar-data.js",
     'C4: { id: "C4_MTF_TURN@1", lane: null, firing: false, role: "stratification_only" }',
     'C4: { id: "C4_MTF_TURN@1", lane: "c4", firing: true, role: "firing_detector" }',
     "R4"),
    ("M3-provisional-as-confirmed", "radar-data.js",
     "5m ago · 1D LIVE · provisional",
     "5m ago · Daily confirmed",
     "R5"),
    ("M4-stale-as-live", "radar.css",
     ".pvcard.er-stale,\n.pvcard.er-unav,\n.pvcard.er-degraded,\n.pvcard.er-raw {",
     ".pvcard.er-UNREACHABLE {",
     "R6"),
    ("M5-unav-as-false", "radar-data.js",
     "UNAVAILABLE · condition is null, not a non-fire",
     "NO FIRE · condition is false",
     "R7"),
    ("M6-drop-false-starts", "radar.js",
     "r.false_starts",
     "r.false_startz",
     "R8d"),
    ("M7-collapse-multi", "radar-data.js",
     '  multi:        ["multi_g0","multi_c1","multi_c2"],',
     '  multi:        ["multi_g0"],',
     "R3"),
    ("M8-fake-priority", "radar-data.js",
     'research_priority: { state: "ACCRUING", value: null, until: "W6" }',
     'research_priority: { state: "READY", value: 91, until: "now" }',
     "R9"),
    ("M9-drop-zh", "radar.css",
     'html[data-lang="zh"] .l-en { display: none; }',
     'html[data-lang="zh"] .l-en { display: inline; }',
     "R10"),
    ("M10-become-production", "index.html",
     'data-reference-banner="1"',
     'data-live-app="1"',
     "R1"),
    ("M11-own-it", "radar.js",
     "not_prophet",
     "Own-It",
     "R11"),
    ("M12-390-overflow", "radar.css",
     "  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;\n}",
     "  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;\n  overflow-x: hidden;\n}",
     "R13b"),
    ("M13-cand-as-buy", "radar.css",
     ".er-cand   { --pvh: var(--er-life); --pvh-ink: var(--ink-life); }",
     ".er-cand   { --pvh: var(--pv-buy);  --pvh-ink: var(--pv-buy); }",
     "R12g"),
    ("M22-cand-as-ok", "radar.css",
     ".er-cand   { --pvh: var(--er-life); --pvh-ink: var(--ink-life); }",
     ".er-cand   { --pvh: var(--ok);      --pvh-ink: var(--ink-ok); }",
     "R12h"),
    ("M14-quiet-force-zero", "radar.js",
     "  const probeSet = META.probe_set;",
     '  const probeSet = state === "quiet" ? 0 : META.probe_set;',
     "R16"),
    ("M15-drop-sort", "radar.js",
     "  rows.sort((a, b) => {",
     "  void ((a, b) => {",
     "R17"),
    ("M16-best-count", "radar.js",
     '      ? `<b class="fig" data-best-unranked="1">—</b>`',
     '      ? `<b class="fig">${n}</b>`',
     "R18"),
    ("M17-featured-fixture", "radar.js",
     '    if (inLane(r, "best")) out.push("pv-featured");',
     "    if (r.featured) out.push(\"pv-featured\");",
     "R19"),
    ("M18-stale-no-spark", "radar-data.js",
     "    stale: true,\n    spark: [74.2, 75.1, 76.0, 76.8, 77.1, 76.9, 77.2, 77.4, 77.40],",
     "    stale: true,",
     "R20"),
    ("M19-dead-hash", "radar.js",
     '          <span class="pv-idw">',
     '          <a class="pv-open" href="#${esc(r.ticker)}"><span class="pv-idw">',
     "R21"),
    ("M20-w9-launder", "W9_IMPLEMENTATION_HANDOFF.md",
     "## NOT §14 COMPLETE — BLOCKED_DATA / ACCRUING",
     "## CAN COPY — card anatomy is §14 complete\n\nCard anatomy: lifecycle + expert identity + optional C2 variant + quote + ACCRUING Priority + why line + freshness footer",
     "R22"),
    ("M21-card-accruing", "radar.js",
     '            <span class="pv-prin pv-prin--na" data-priority="accruing">—</span>',
     '            <span class="pv-prin pv-prin--na" data-priority="accruing">${t(C.pri_accruing)}</span>',
     "R23"),
    ("M24-c2-overlay", "radar.js",
     '        <span class="er-xchip" data-expert="${esc(r.expert)}">\n          <span class="pv-axis">${t(C.expert_axis)}</span> ${esc(r.expert)}\n        </span>\n      </div>',
     '        <span class="er-xchip" data-expert="${esc(r.expert)}">\n          <span class="pv-axis">${t(C.expert_axis)}</span> ${esc(r.expert)}\n        </span>\n        ${v ? `<span class="pv-mk-i" data-c2-variant="${esc(r.c2_variant)}">${esc(t(v))}</span>` : ""}\n      </div>',
     "R25c"),
    ("M25-overlay-nowrap", "radar.css",
     ".pv-ov.pv-ovl { flex-wrap: wrap; row-gap: 3px; max-width: calc(100% - 122px); }",
     ".pv-ov.pv-ovl { flex-wrap: nowrap; max-width: calc(100% - 96px); }",
     "R25e"),
    ("M26-title-zh", "radar.js",
     '          <span class="pv-pri" tabindex="0"',
     '          <span class="pv-pri" title="${esc(t(C.pri_tip))}" tabindex="0"',
     "R26"),
    ("M27-unav-no-path", "radar.js",
     '      else if (r && r.unavailable) msg = both("Path unavailable", "路径不可用");',
     "",
     "R27"),
    ("M28-prov-filled", "radar.css",
     '.pvcard[data-bar="provisional_1d_live"] .pv-chip.er-lifechip {',
     ".pvcard[data-bar=\"never-provisional\"] .pv-chip.er-lifechip {",
     "R28"),
]


def run_verify(tree: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(tree / "tools" / "verify.py")],
        cwd=str(tree),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    # Positive control: the real tree must pass static checks.
    rc, out = run_verify(ROOT)
    if rc != 0:
        print("CONTROL FAIL — verify.py is already red on the unmutated tree:")
        print(out)
        return 2
    print("CONTROL  verify.py green on the unmutated tree")

    caught = 0
    missed = []
    for mid, rel, find, repl, prefix in MUTATIONS:
        tmp = Path(tempfile.mkdtemp(prefix="radar-w8-mut-"))
        try:
            shutil.copytree(ROOT, tmp / "entry_radar", ignore=shutil.ignore_patterns("crops", "__pycache__"))
            tree = tmp / "entry_radar"
            target = tree / rel
            text = target.read_text(encoding="utf-8")
            if find not in text:
                missed.append((mid, f"needle not found in {rel}"))
                print(f"MISS     {mid}  needle not found")
                continue
            target.write_text(text.replace(find, repl, 1), encoding="utf-8")
            rc, out = run_verify(tree)
            hit = rc != 0 and any(
                line.startswith("  FAIL") and prefix in line
                for line in out.splitlines()
            )
            if hit:
                caught += 1
                print(f"CAUGHT   {mid}  by {prefix}*")
            else:
                missed.append((mid, f"rc={rc}; prefix {prefix} not in FAIL lines"))
                print(f"MISS     {mid}  rc={rc}")
                for line in out.splitlines():
                    if "FAIL" in line:
                        print("         ", line)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{caught}/{len(MUTATIONS)} mutations caught")
    if missed:
        print("UNCAUGHT:")
        for mid, why in missed:
            print(f"  {mid}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
