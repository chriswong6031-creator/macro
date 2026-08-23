#!/usr/bin/env python3
"""R3B1-14 — unique-kill mutation suite for the bidirectional inventory.

"Mutation suite removes each independently and must get a unique red. A
guard true before the feature is not a guard." (COMMISSION.md R3B1-14)

For each pinned hero capability this script:
  1. copies the BUILT candidate (never the real proposal file) into a temp
     directory;
  2. confirms `inventory_check.py` is GREEN against the pristine copy
     (baseline proof the guard can pass);
  3. applies ONE targeted byte-level mutation that removes/blanks that one
     capability from the copy — the same shape of silent omission DAC-101
     through DAC-106 actually shipped;
  4. re-runs `inventory_check.py` against the mutated copy and records which
     checks now FAIL;
  5. asserts every mutation's failing-check set is non-empty and that no two
     mutations produce the same failing-check set (a pairwise distinctness
     check across ALL {mutation: failing_set} pairs).

Also runs a destination-family mutation ("strip all basket/* hrefs") to
prove direction 2 (candidate -> allowed) catches an invented/blanked
destination family, not just direction 1.

Usage:
    <playwright-python> mutation_suite.py [--out MUTATION_RESULTS.md]
Exit 0 iff every mutation gets a unique, non-empty red and the pristine
baseline is green.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
INVENTORY_CHECK = BUILD_DIR / "inventory_check.py"
CANDIDATE = BUILD_DIR.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

FAIL_LINE_RE = re.compile(r"^\[FAIL\] (.+?) — ")


def mutate_sizing_directive(html: str) -> str:
    target = 'function sizingHTML(){'
    assert html.count(target) == 1, f"expected exactly 1 occurrence, got {html.count(target)}"
    return html.replace(target, 'function sizingHTML(){return "";', 1)


def mutate_caveat_clause_a(html: str) -> str:
    en = "'Shape read only — not a forecast.\\n'"
    zh = "'仅为形态读数，非预测。\\n'"
    assert html.count(en) == 1 and html.count(zh) == 1
    html = html.replace(en, "''", 1)
    html = html.replace(zh, "''", 1)
    return html


def mutate_caveat_clause_b(html: str) -> str:
    en1 = "skips the most recent '"
    en2 = "'~3 weeks by construction; suggested weights unchanged.'"
    zh = "设计上跳过最近约3周数据；"
    assert html.count(en1) == 1 and html.count(en2) == 1 and html.count(zh) == 1
    html = html.replace(en1, "'", 1)
    html = html.replace(en2, "'suggested weights unchanged.'", 1)
    html = html.replace(zh, "", 1)
    return html


def mutate_migration_note(html: str) -> str:
    target = "var migration = mg.note_en"
    assert html.count(target) == 1
    return html.replace(target, "var migration = false", 1)


def mutate_allocation_destination(html: str) -> str:
    target = "var play = withPlaybook"
    assert html.count(target) == 1
    return html.replace(target, "var play = false", 1)


def mutate_hero_enrichment_outgoing(html: str) -> str:
    target = "var outX = metaFor(tl.id, 'out');"
    assert html.count(target) == 1
    return html.replace(target, "var outX = null;", 1)


def mutate_hero_enrichment_incoming(html: str) -> str:
    target = "var inX = metaFor((takers[0] || {}).id, 'in');"
    assert html.count(target) == 1
    return html.replace(target, "var inX = null;", 1)


def mutate_hero_enrichment_counts(html: str) -> str:
    target = "function paintCounts(){"
    assert html.count(target) == 1
    return html.replace(target, "function paintCounts(){return;", 1)


def mutate_sp_coverage_sentence(html: str) -> str:
    target = "if(cov.n_gateable != null){"
    assert html.count(target) == 1
    return html.replace(target, "if(false){", 1)


def mutate_conviction_picks_label(html: str) -> str:
    target = "L('Conviction', '综合把握')"
    assert html.count(target) == 2, f"expected exactly 2 occurrences, got {html.count(target)}"
    return html.replace(target, "L('', '')", 1)  # first occurrence only — the header, marker 13


def mutate_destination_family_basket(html: str) -> str:
    assert "basket/" in html
    return html.replace("basket/", "zz-not-a-basket/")


MUTATIONS = [
    ("sizing_directive", mutate_sizing_directive),
    ("method_caveat_clause_a", mutate_caveat_clause_a),
    ("method_caveat_clause_b", mutate_caveat_clause_b),
    ("migration_note", mutate_migration_note),
    ("allocation_destination", mutate_allocation_destination),
    ("hero_enrichment_outgoing", mutate_hero_enrichment_outgoing),
    ("hero_enrichment_incoming", mutate_hero_enrichment_incoming),
    ("hero_enrichment_counts", mutate_hero_enrichment_counts),
    ("sp_coverage_sentence", mutate_sp_coverage_sentence),
    ("conviction_picks_label", mutate_conviction_picks_label),
    ("destination_family_basket", mutate_destination_family_basket),
]


def run_inventory_check(candidate_path: Path) -> tuple[int, str, set[str]]:
    r = subprocess.run(
        [sys.executable, str(INVENTORY_CHECK),
         "--candidate", str(candidate_path), "--no-write-expected"],
        cwd=str(BUILD_DIR), capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    failing = set()
    for line in out.splitlines():
        m = FAIL_LINE_RE.match(line)
        if m:
            failing.add(m.group(1))
    return r.returncode, out, failing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BUILD_DIR / "MUTATION_RESULTS.md"))
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    pristine_html = CANDIDATE.read_text(encoding="utf-8")

    all_ok = True
    rows: list[dict] = []
    failing_sets: dict[str, frozenset[str]] = {}

    with tempfile.TemporaryDirectory(prefix="r3b1_mutation_") as tmp:
        tmp_path = Path(tmp)
        pristine_copy = tmp_path / "pristine.html"
        pristine_copy.write_text(pristine_html, encoding="utf-8")

        print("=== baseline: pristine copy must be fully GREEN ===")
        rc0, out0, failing0 = run_inventory_check(pristine_copy)
        baseline_ok = (rc0 == 0 and not failing0)
        print(f"[{'PASS' if baseline_ok else 'FAIL'}] baseline pristine copy green "
              f"— rc={rc0} failing={sorted(failing0)}")
        if not baseline_ok:
            all_ok = False

        for capability, mutate_fn in MUTATIONS:
            mutated_html = mutate_fn(pristine_html)
            assert mutated_html != pristine_html, f"{capability}: mutation was a no-op"
            mutated_path = tmp_path / f"mutated_{capability}.html"
            mutated_path.write_text(mutated_html, encoding="utf-8")

            print(f"\n=== mutation: {capability} ===")
            rc, out, failing = run_inventory_check(mutated_path)
            unique_red = bool(failing)
            ok = unique_red
            if not ok:
                all_ok = False
            print(f"[{'PASS' if ok else 'FAIL'}] {capability} produced a red "
                  f"— failing={sorted(failing)}")

            failing_sets[capability] = frozenset(failing)
            rows.append({
                "capability": capability,
                "baseline_green": baseline_ok,
                "failing": sorted(failing),
                "rc": rc,
                "got_red": unique_red,
            })

    # pairwise distinctness across ALL mutations (including empty sets, which
    # would collide with each other and must never happen)
    print("\n=== pairwise distinctness ===")
    caps = [c for c, _ in MUTATIONS]
    collisions = []
    for i in range(len(caps)):
        for j in range(i + 1, len(caps)):
            a, b = caps[i], caps[j]
            if failing_sets[a] == failing_sets[b]:
                collisions.append((a, b, sorted(failing_sets[a])))
    distinct_ok = not collisions
    if not distinct_ok:
        all_ok = False
    print(f"[{'PASS' if distinct_ok else 'FAIL'}] all {len(caps)} mutations produced "
          f"pairwise-distinct failing-check sets"
          + (f" — collisions: {collisions}" if collisions else ""))

    write_report(Path(args.out), baseline_ok, rows, distinct_ok, collisions)
    print(f"\nMUTATION_RESULTS.md -> {args.out}")

    n_pass = sum(1 for row in rows if row["got_red"]) + (1 if baseline_ok else 0) + (1 if distinct_ok else 0)
    n_total = len(rows) + 2
    print(f"\n{n_pass}/{n_total} mutation-suite checks passed.")
    return 0 if all_ok else 1


def write_report(out_path: Path, baseline_ok: bool, rows: list[dict],
                  distinct_ok: bool, collisions: list) -> None:
    lines = []
    lines.append("# R3B1-14 — mutation suite results\n")
    lines.append(
        "Candidate: `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`. "
        "Every mutation below is applied to an in-memory COPY of the built "
        "candidate inside a throwaway temp directory; the real proposal file "
        "is never touched.\n"
    )
    lines.append(f"**Pristine baseline green:** {'YES' if baseline_ok else 'NO — SEE ABOVE'}\n")
    lines.append("## Per-mutation results\n")
    lines.append("| capability | got a red | failing checks |")
    lines.append("|---|---|---|")
    for row in rows:
        failing = "<br>".join(row["failing"]) if row["failing"] else "(none — BUG)"
        lines.append(f"| `{row['capability']}` | {'yes' if row['got_red'] else '**NO**'} | {failing} |")
    lines.append("")
    lines.append("## Pairwise distinctness\n")
    if distinct_ok:
        lines.append("All mutations produced pairwise-distinct failing-check sets — "
                      "no two capabilities collapse to the same red.\n")
    else:
        lines.append("**COLLISIONS FOUND:**\n")
        for a, b, shared in collisions:
            lines.append(f"- `{a}` and `{b}` both produced: {shared}\n")
    lines.append(
        "## Method\n\n"
        "Each mutation targets the exact JS source construct Lane A/B restored "
        "for that capability (a return-early guard, a ternary condition forced "
        "false, or a literal string fragment blanked) — the built candidate "
        "embeds the view partials' JS source verbatim, so the mutation operates "
        "on the same bytes the browser executes, not on the fixture or the "
        "producer contract. `destination_family_basket` instead does a global "
        "byte substitution of the literal `basket/` prefix, proving direction 2 "
        "(candidate -> allowed) catches a stripped destination family, not only "
        "direction 1's hero-copy pins."
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
