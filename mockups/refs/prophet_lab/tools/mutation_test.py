#!/usr/bin/env python3
"""Do the D-LAB-R5 guards actually BITE?

Usage:  python3 tools/mutation_test.py [base_url]

`verify.py` asserting a law holds is a different claim from `verify.py` being
able to SEE the law broken. The R4 cycle found two inherited checks that had
silently stopped measuring anything while still reporting green — a DOM count
that counted hidden nodes, and a geometry probe on a `display:none` element
whose rect is all zeros. Its README names that trap as the first thing the
next cycle should re-check. This is that re-check.

Each mutation below breaks exactly one law in the artifact, runs verify.py, and
requires the intended check to FAIL. Three properties are enforced:

  * a mutation whose pattern does not match is an ERROR, not a skip — a
    silently no-op mutation makes a decorative guard look green;
  * a mutation the harness SURVIVES is reported as a hole;
  * two mutations may not share a sole catcher, so no guard is decorative.

The files are restored whatever happens, including on Ctrl-C.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8794/prophet_lab"
PY = sys.executable

JS = LAB / "lab.js"
CSS = LAB / "lab.css"

# (id, file, pattern, replacement, the check id that must catch it)
MUTATIONS = [
    ("M1  paint a seed with the live-sighting treatment", JS,
     r'<span class="lab-cls lab-cls--seed"',
     '<span class="lab-cls lab-cls--live"',
     "D6c"),
    ("M2  let a seed carry a measured lead", JS,
     r'if \(r\.cls === "live_forward" && r\.lead != null\) \{',
     'if (r.lead != null || r.cls === "seed") {',
     "D6"),
    ("M3  make the seed spine solid", CSS,
     r'\.lab-row--seed \.lab-when \{ border-right-style: dashed;',
     '.lab-row--seed .lab-when { border-right-style: solid;',
     "D6e"),
    ("M4  print the raw expert slug at the glance tier", JS,
     r't\(e\.en, e\.zh\) \+ "</span>";',
     't(e.exp, e.exp) + "</span>";',
     "D7"),
    # the page-wide substring test survives this: the board SELECTORS also
    # carry detector ids. Only a per-row check can see it, which is the point.
    ("M5  drop the per-reading Tier-2 identity receipt", JS,
     r'e\.det \+ \(e\.det\.indexOf\("C2_"\) === 0 \? " / " \+ e\.exp : ""\),\n'
     r'        e\.det \+ \(e\.det\.indexOf\("C2_"\) === 0 \? " / " \+ e\.exp : ""\)\)',
     '"", "")',
     "D7c"),
    ("M6  merge the experts into one chip", JS,
     r'r\.ex\.forEach\(function \(e\) \{',
     'r.ex.slice(0, 1).forEach(function (e) {',
     "D8"),
    ("M7  leave the plan-book ladder standing under a LAB label", JS,
     r'\["ladder-block"\]\.forEach',
     '[].forEach',
     "D4b"),
    ("M8  restore LIVE from a snapshot instead of re-deriving it", JS,
     r'sc\.src = "\.\./institutionalize/us_stocks/board\.js\?repaint=" \+ \(\+\+C\.repaints\);',
     'sc.src = "../institutionalize/us_stocks/board.js?repaint=" + C.repaints;',
     "D15d"),
    ("M9  mount the mode control as its own row, moving the board down", JS,
     r'stamp\.insertAdjacentHTML\("beforeend",',
     'document.querySelector(".bh").insertAdjacentHTML("beforeend",',
     "D2"),
    ("M10 show the operator affordance without entitlement", JS,
     r'var operator = qs\.get\("op"\) !== "0" && qs\.get\("state"\) !== "anon";',
     'var operator = true;',
     "D3"),
    # the silent fallback: the label still says LAB, the content is the live
    # board. This is the single failure LAB-0 §6.5 names by name.
    ("M11 fall back to LIVE content when the Lab feed is down", JS,
     r'if \(setups\) setups\.innerHTML = plane\(\);',
     'if (setups && C.feed !== "down") setups.innerHTML = plane();',
     "D14b"),
    ("M12 sort the stream oldest-first", JS,
     r'return out;   /\* already newest-first',
     'return out.slice().reverse();   /* already newest-first',
     "D10"),
    ("M13 blank the lead slot on seeds instead of stating why", JS,
     r'    return \'<span class="lab-lead lab-lead--none"\' \+ tip\(\n'
     r'      "Lead cannot be measured", "无法测量提前量",',
     '    return ""; var _mut = tip(\n      "Lead cannot be measured", "无法测量提前量",',
     "D6g"),
]


def run_verify():
    """Returns (failed_check_ids, stdout, stderr).

    A CRASHED harness is not a pass. If verify.py exits non-zero without
    printing a FAILED block — because a mutation produced a page it could not
    even drive — the mutation must be reported as un-measured rather than
    silently counted as survived, which would read as "the guard is fine".
    """
    r = subprocess.run([PY, str(HERE / "verify.py"), BASE],
                       capture_output=True, text=True)
    failed = set()
    tail = r.stdout.split("FAILED:")
    if len(tail) > 1:
        for line in tail[1].strip().splitlines():
            line = line.strip()
            if line.startswith("D"):
                failed.add(line.split()[0].split("[")[0])
    if r.returncode != 0 and not failed:
        return {"__CRASH__"}, r.stdout, r.stderr
    return failed, r.stdout, r.stderr


def main():
    originals = {p: p.read_text(encoding="utf-8") for p in (JS, CSS)}
    caught, survived, killers = [], [], {}
    try:
        base_failed, out, err = run_verify()
        if base_failed:
            raise SystemExit(
                "::error title=mutation::the UNMUTATED artifact already fails "
                f"{sorted(base_failed)} — fix that before measuring guards\n{err[-800:]}")
        print(f"baseline: clean ({out.strip().splitlines()[-1]})\n")

        for name, path, pat, rep, want in MUTATIONS:
            src = originals[path]
            new, n = re.subn(pat, rep, src, count=1)
            if n != 1:
                # a mutation that does not apply proves nothing and would make
                # a decorative guard look green. Loud failure, never a skip.
                raise SystemExit(
                    f"::error title=mutation::{name}: pattern did not match "
                    f"{path.name} — the mutation is stale, rewrite it")
            path.write_text(new, encoding="utf-8")
            failed, _, _ = run_verify()
            path.write_text(src, encoding="utf-8")

            if "__CRASH__" in failed:
                raise SystemExit(
                    f"::error title=mutation::{name}: verify.py could not drive the "
                    "mutated page at all, so nothing was measured. Rewrite the "
                    "mutation to break ONE law, not the artifact.")
            if want in failed:
                caught.append((name, want, sorted(failed)))
                killers[name] = set(failed)
                print(f"CAUGHT   {name}\n         by {sorted(failed)}")
            else:
                survived.append((name, want, sorted(failed)))
                print(f"SURVIVED {name}\n         expected {want}, harness saw {sorted(failed)}")
    finally:
        for p, s in originals.items():
            p.write_text(s, encoding="utf-8")

    # no two mutations may share a SOLE catcher — otherwise one guard is doing
    # all the work and the others are decoration
    shared = []
    singles = {n: next(iter(k)) for n, k in killers.items() if len(k) == 1}
    seen: dict[str, str] = {}
    for n, k in singles.items():
        if k in seen:
            shared.append((seen[k], n, k))
        seen[k] = n

    print(f"\n{len(caught)}/{len(MUTATIONS)} caught")
    if shared:
        print("SHARED SOLE CATCHER (a guard here is decorative):")
        for a, bb, k in shared:
            print(f"  {a} and {bb} are both caught only by {k}")
    if survived:
        print("HOLES:")
        for n, w, f in survived:
            print(f"  {n}: expected {w}, saw {f}")
    return 1 if (survived or shared) else 0


if __name__ == "__main__":
    sys.exit(main())
