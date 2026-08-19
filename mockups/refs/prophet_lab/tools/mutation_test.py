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
    # aimed at the class census (D6h) rather than the chip: with the per-row
    # seed chip gone, the way a seed can wear the live treatment is to be
    # LABELLED live, and that also silently empties every seed-scoped check —
    # the vacuity hole this mutation found.
    ("M1  label every row a live sighting", JS,
     r'\(seed \? "lab-row--seed" : "lab-row--live"\)',
     '("lab-row--live")',
     "D6h"),
    ("M2  let a seed carry a measured lead", JS,
     r'var measurable = r\.cls === "live_forward" && r\.lead != null;',
     'var measurable = r.lead != null || r.cls === "seed";',
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
    # R5.1: the R5 mutation attacked the OVER-REACH (a ladder left standing).
    # The law inverted, so the mutation inverts with it: the defect to catch is
    # now the mode DELETING a plan-book section, which is what VTL-401 found.
    ("M7  make LAB delete a plan-book section again (the VTL-401 defect)", JS,
     r'    var setups = document\.getElementById\("setups"\);\n    if \(setups\) setups\.innerHTML = plane\(\);',
     '    var _c = document.getElementById("candidates"); if (_c) _c.style.display = "none";\n'
     '    var setups = document.getElementById("setups");\n    if (setups) setups.innerHTML = plane();',
     "D4d"),
    ("M18 make the class divider non-sticky", CSS,
     r'  position: sticky; top: var\(--lab-mark-top, 0px\); z-index: 4;\n'
     r'  background: var\(--panel\);',
     '  position: static; z-index: 4;\n  background: var(--panel);',
     "D6c"),
    # R5.2 / PR51-1 — THE DEFECT THAT ACTUALLY SHIPPED, as a mutation. M18
    # attacks the declaration; this attacks the layout the declaration lives in,
    # which is how the capability was inert for a whole cycle while M18 passed.
    # It is caught ONLY by the behavioural check, which is the point.
    ("M22 clip the stream with overflow, re-inerting the pin (PR51-1)", CSS,
     r'\.lab-stream \{\n  margin: 0; padding: 0; list-style: none;\n'
     r'  background: var\(--panel\); border: 1px solid var\(--line\);\n'
     r'  border-radius: 14px;\n  box-shadow: var\(--card-shadow\);\n\}',
     '.lab-stream {\n  margin: 0; padding: 0; list-style: none;\n'
     '  background: var(--panel); border: 1px solid var(--line);\n'
     '  border-radius: 14px; overflow: hidden;\n  box-shadow: var(--card-shadow);\n}',
     "D6c3"),
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
     r'    return \'<span class="lab-lead lab-lead--none lab-lead--dash" aria-label="\' \+\n'
     r'      esc\(lang\(\) === "zh" \? "无法测量提前量" : "Lead not measurable"\) \+ \'"\' \+ tip\(',
     '    return ""; var _mut = ("" +\n      esc("") + "") + tip(',
     "D6g"),

    # ══ R5.1 mutations — one per revision requirement ═══════════════════════
    ("M14 print a literal 0 from a feed that is not answering (VTL-402)", JS,
     r'var n = unk \? "&mdash;" : \(C\.feed === "empty" \? "0" : String\(b\.rows\.length\)\);',
     'var n = (C.feed === "down" || C.feed === "empty") ? "0" : String(b.rows.length);',
     "D18"),
    ("M15 route an adverse lead back through the favourable branch (VTL-403)", JS,
     r'    if \(measurable && r\.lead > 0\) \{\n      var d = r\.lead;',
     '    if (measurable && r.lead !== 0) {\n      var d = Math.abs(r.lead);',
     "D19"),
    ("M16 re-amplify the favourable lead chip (VTL-403)", CSS,
     r'\.lab-lead--measured \{\n  color: color-mix\(in srgb, var\(--text\) 88%, var\(--muted\)\);\n'
     r'  background: transparent;\n  border: 1px solid var\(--line\);\n\}',
     '.lab-lead--measured {\n  color: var(--lab-ink);\n'
     '  background: var(--lab-wash);\n  border: 1px solid var(--lab-rule);\n}\n'
     '.lab-lead--adverse { color: var(--muted); }',
     "D19c"),
    # C1 — the one the R5 verdict asked for by name. It restores a CACHED DOM
    # on the way back to LIVE while leaving the repaint counter untouched, so
    # D15d still passes and only the sentinel check can see it. That is the
    # point: it proves the counter was never evidence.
    ("M17 cache the board on LAB entry and restore it on LIVE (C1)", JS,
     [r'    var setups = document\.getElementById\("setups"\);\n    if \(setups\) setups\.innerHTML = plane\(\);',
      r'    var sc = document\.createElement\("script"\);'],
     ['    var _b0 = document.getElementById("board");\n'
      '    if (_b0 && !window.__labSnap) window.__labSnap = _b0.innerHTML;\n'
      '    var setups = document.getElementById("setups");\n'
      '    if (setups) setups.innerHTML = plane();',
      '    if (window.__labSnap) {\n'
      '      C.repaints++;\n'
      '      document.getElementById("board").innerHTML = window.__labSnap;\n'
      '      window.__labSnap = null; mountModebar(); syncSeg(); harnessStamp(); return;\n'
      '    }\n    var sc = document.createElement("script");'],
     "D22"),
    ("M19 put the six boards back behind an unaffordanced scroller (VTL-411)", CSS,
     r'\.lab-sel-wrap \{ margin: 14px 0 0; \}\n'
     r'\.lab-sel \{ display: flex; flex-wrap: wrap; gap: 7px; row-gap: 7px; padding-bottom: 3px; \}',
     '.lab-sel-wrap { margin: 14px 0 0; overflow-x: auto; }\n'
     '.lab-sel { display: flex; flex-wrap: nowrap; gap: 7px; row-gap: 7px; padding-bottom: 3px; }',
     "D20"),

    # ══ R5.2 mutations — PR51-3: D4b and D4c were unattacked ════════════════
    # VTL-401 was the R5 verdict's first major, and R5.1 shipped six checks for
    # it with a mutation aimed at exactly one (M7 → D4d). D4b and D4c were
    # therefore asserted, never proven to bite — the same "a guard that has
    # stopped measuring still reports green" trap the harness exists for.
    ("M20 make LAB hide the ladder again (VTL-401)", JS,
     r'    var setups = document\.getElementById\("setups"\);\n    if \(setups\) setups\.innerHTML = plane\(\);',
     '    var _l = document.querySelector(".ladder-block"); if (_l) _l.style.display = "none";\n'
     '    var setups = document.getElementById("setups");\n    if (setups) setups.innerHTML = plane();',
     "D4b"),
    ("M21 make LAB hide the page header again (VTL-401)", JS,
     r'    var setups = document\.getElementById\("setups"\);\n    if \(setups\) setups\.innerHTML = plane\(\);',
     '    var _p = document.querySelector(".bh-purpose"); if (_p) _p.style.display = "none";\n'
     '    var setups = document.getElementById("setups");\n    if (setups) setups.innerHTML = plane();',
     "D4c"),

    # ── R5.2 / R52-D1 · R52-D2 ──────────────────────────────────────────────
    # The constant VTL-408 removed as a chip and R5.1 kept printing as a rail.
    ("M23 repeat the class assertion on all 23 rails again (R52-D1)", JS,
     r'      h \+= \'<span class="lab-tl">\' \+ t\("signal date", "信号日期"\) \+ "</span>";',
     '      h += \'<span class="lab-tl">\' + t("signal date<br>not a sighting", '
     '"信号日期<br>非观测记录") + "</span>";',
     "D6i2"),
    # `top: 0` is right only on a route with no page header. This is the defect
    # in the shape a follower surface would actually ship it: still sticky,
    # still pinning, just pinning underneath the site nav where nobody sees it.
    # R5.3: the expected catcher moves from D6c4 to D6c4b. D6c4 used to be one
    # check conflating "the chrome is pinned" with "the pin clears it"; PR52-1
    # split it, and this mutation attacks the second half — the chrome still
    # pins, the divider just ignores it. Measured: M25 -> ['D6c4b'] alone,
    # M27 -> ['D6c4', 'D6c4b'], so the split is load-bearing in both directions.
    ("M25 hardcode the pin to top:0, ignoring the page header (R52-D1)", CSS,
     r'  position: sticky; top: var\(--lab-mark-top, 0px\); z-index: 4;',
     '  position: sticky; top: 0; z-index: 4;',
     "D6c4b"),
    ("M24 stop landing the region on flip (R52-D2)", JS,
     r'  function landRegion\(\) \{\n    var band = ',
     '  function landRegion() {\n    if (true) return;\n    var band = ',
     "D24"),
    ("M26 keep the landing but never undo it (R52-D2)", JS,
     r'      if \(C\.preLabScrollY != null\) \{\n        var y = C\.preLabScrollY;',
     '      if (false) {\n        var y = C.preLabScrollY;',
     "D24c"),

    # ══ R5.3 mutations — one per blocking ruling ════════════════════════════
    # PR52-1. THE DEFECT THAT SHIPPED, as a mutation. M25 attacks the pin's
    # declaration; this takes the CHROME's travel away, which is what made the
    # seam imaginary for a whole cycle while M25 kept passing. The R5.2 version
    # of D6c4 read the bar's HEIGHT and could not tell the difference, so this
    # mutation is also the receipt that the rewritten check now can.
    ("M27 re-inert the chrome seam by giving the harness no travel (PR52-1)", CSS,
     r'#harness \{ display: contents; \}',
     '#harness { display: block; }',
     "D6c4"),
    # VTL52-601. The line goes back to bare integers with no subject and no
    # unit — the R5.2 wording, verbatim, which is what created the collision.
    ("M28 strip the subject and unit off the lead aggregate (VTL52-601)", JS,
     r'    var aggEn = "we were earlier on <b>" \+ early \+ "</b> &middot; same day on <b>" \+ sameDay \+\n'
     r'                "</b> &middot; Prophet earlier on <b>" \+ late \+ "</b>";',
     '    var aggEn = "<b>" + early + "</b> earlier &middot; <b>" + sameDay +\n'
     '                "</b> same day &middot; <b>" + late + "</b> later";',
     "D26"),
    # VTL52-602. The constant returns to the seed lead slot, 23 times, below a
    # divider that states it once. D6g and D6i still pass — they did at R5.2 —
    # so only the widened D6i4 can see it.
    ("M29 print the class consequence on all 23 seed rows again (VTL52-602)", JS,
     r'\'><span aria-hidden="true">&mdash;</span></span>\';',
     '">" + t("Lead not measurable", "无法测量提前量") + "</span>";',
     "D6i4"),
    # PR52-4 / VTL52-604. The touch path goes away and the <=560 landings become
    # unreachable again by the only gesture a phone reader has.
    ("M30 take the LENS tap path away again (PR52-4)", JS,
     r'    if \(el === lensHeld && labLensIsOpen\(\)\) \{ labLensClose\(\); return; \}\n'
     r'    labLensClose\(\);\n    labLensOpen\(el\);',
     '    return;',
     "D28"),
    # PR52-3. Focus is dropped on the way back to LIVE, as it was at R5.2.
    ("M31 drop focus to <body> on LAB->LIVE again (PR52-3)", JS,
     r'      if \(refocus\) \{\n'
     r'        var back = document\.querySelector\(\'\.lab-seg button\[aria-checked="true"\]\'\);\n'
     r'        if \(back\) back\.focus\(\{ preventScroll: true \}\);\n      \}',
     '      if (false) { /* focus dropped */ }',
     "D25"),
    # VTL52-603. The caveat demotes off the glance tier again while all six
    # integers stay — the R5.2 rule, restored.
    ("M32 demote the overlap caveat off the 390 glance tier again (VTL52-603)", CSS,
     r'  \.lab-overlap \{ margin-top: 6px; \}',
     '  .lab-overlap { display: none; }',
     "D27"),
    # PR52-2. The landing forgets the sticky chrome, which is what put the
    # reader's own control behind the header at chrome=1.
    # VTL52-607. The five statements run together with whitespace again.
    ("M34 run the meta statements together with no separator (VTL52-607)", CSS,
     r'  content: ""; position: absolute; left: 0; top: 50%;\n'
     r'  transform: translateY\(-50%\);\n'
     r'  width: 1px; height: 11px; background: var\(--line\);',
     '  content: none;',
     "D29"),
    ("M33 land the region without the sticky-chrome offset (PR52-2)", JS,
     r'    window\.scrollTo\(\{ top: Math\.max\(0, Math\.round\(bandTop\) - off\), behavior: "auto" \}\);',
     '    window.scrollTo({ top: Math.round(bandTop), behavior: "auto" });',
     "D24b"),
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
            # a mutation may need to change more than one site (C1's snapshot
            # restore touches both the LAB entry and the LIVE return); pattern
            # and replacement may therefore be parallel lists.
            pats = pat if isinstance(pat, list) else [pat]
            reps = rep if isinstance(rep, list) else [rep]
            new = src
            for p_, r_ in zip(pats, reps):
                new, n = re.subn(p_, r_, new, count=1)
                if n != 1:
                    # a mutation that does not apply proves nothing and would
                    # make a decorative guard look green. Loud, never a skip.
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
