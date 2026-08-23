#!/usr/bin/env python3
"""Unique-red proof for the R3B.2 freeze-critical semantic guards.

Each mutation is applied to a throwaway candidate copy. The real proposal is
never modified. The suite first proves both audits green on a pristine copy,
then requires every independent omission to produce a non-empty and pairwise-
distinct set of stable failing check ids.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


BUILD = Path(__file__).resolve().parent
DEFAULT_CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
FIG_AUDIT = BUILD / "fig_naming_audit.py"
CLOSURE_AUDIT = BUILD / "closure_audit.py"


def replace_exact(html: str, old: str, new: str, expected: int = 1) -> str:
    count = html.count(old)
    assert count == expected, f"expected {expected} occurrence(s) of {old!r}, got {count}"
    return html.replace(old, new, 1)


def mutate_fig_kind(kind: str) -> Callable[[str], str]:
    def mutate(html: str) -> str:
        return replace_exact(html, f'data-fig-kind="{kind}"', f'data-fig-kind="removed-{kind}"')
    return mutate


def mutate_strength_header(html: str) -> str:
    old = 'data-r3b1="11" data-r3b2="01">\' + L(\'Strength\', \'强度\')'
    new = 'data-r3b1="11" data-r3b2="01">\' + L(\'Score\', \'评分\')'
    return replace_exact(html, old, new)


def mutate_low_confidence(html: str) -> str:
    return replace_exact(html, "L('Low confidence', '低置信度')", "L('Thin data', '数据稀疏')")


def mutate_shared_receipt(html: str) -> str:
    old = "+ ' aria-controls=\"r3-receipt\"'"
    return replace_exact(html, old, "+ ''")


def mutate_context_qualification(html: str) -> str:
    old = "if(!t || t.is_context_only!==true) return '';"
    return replace_exact(html, old, "return '';")


MUTATIONS: list[tuple[str, str, Callable[[str], str]]] = [
    ("b2_05_strength", "fig", mutate_fig_kind("strength")),
    ("b2_05_delta", "fig", mutate_fig_kind("delta")),
    ("b2_05_entry", "fig", mutate_fig_kind("entry")),
    ("b2_05_conviction", "fig", mutate_fig_kind("conviction")),
    ("b2_01_strength_term", "closure", mutate_strength_header),
    ("b2_12_authority_term", "closure", mutate_low_confidence),
    ("b2_13_shared_receipt", "closure", mutate_shared_receipt),
    ("b2_15_context_scope", "closure", mutate_context_qualification),
]


def run_audit(kind: str, candidate: Path, json_path: Path) -> tuple[int, set[str], str]:
    script = FIG_AUDIT if kind == "fig" else CLOSURE_AUDIT
    cmd = [sys.executable, str(script), "--candidate", str(candidate), "--json", str(json_path)]
    # One discriminating mobile/EN cell is sufficient for a mutation kill. The
    # committed binding artifact still runs the full 1440/390/320 x EN/ZH sweep.
    if kind == "fig":
        cmd += ["--widths", "390", "--langs", "en"]
    run = subprocess.run(cmd, cwd=str(BUILD), capture_output=True, text=True)
    failed: set[str] = set()
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        failed = set(payload.get("failed_check_ids") or [])
    return run.returncode, failed, (run.stdout or "") + (run.stderr or "")


def write_reports(md_path: Path, json_path: Path, payload: dict) -> None:
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# R3B.2 closure mutation results",
        "",
        "Every mutation was applied to a throwaway copy of the assembled candidate; the real proposal file was never modified.",
        "",
        f"**Pristine figure guard green:** {'YES' if payload['baseline']['fig'] else 'NO'}  ",
        f"**Pristine closure guard green:** {'YES' if payload['baseline']['closure'] else 'NO'}  ",
        f"**Pairwise-distinct reds:** {'YES' if payload['pairwise_distinct'] else 'NO'}",
        "",
        "| mutation | guard | got red | failing check ids |",
        "|---|---|---:|---|",
    ]
    for row in payload["mutations"]:
        ids = "<br>".join(f"`{x}`" for x in row["failed_check_ids"]) or "(none)"
        lines.append(f"| `{row['name']}` | {row['guard']} | {'yes' if row['got_red'] else '**NO**'} | {ids} |")
    lines += ["", "## Distinctness", ""]
    if payload["pairwise_distinct"]:
        lines.append("All eight independently removed semantics produced non-empty, pairwise-distinct failing-check sets.")
    else:
        lines.append(f"Collisions: `{payload['collisions']}`")
    lines += [
        "",
        "The four B2-05 mutations cover the two independently named Overview measurements and the Entry tier and Conviction figure classes. The remaining mutations cover the one-path/one-term law, the distinct authority terms, the shared receipt target, and the producer-derived context qualification.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--out", default=str(BUILD / "CLOSURE_MUTATION_RESULTS.md"))
    ap.add_argument("--json", default=str(BUILD / "closure_mutation_results.json"))
    args = ap.parse_args()
    candidate = Path(args.candidate).resolve()
    if not candidate.exists():
        print(f"missing candidate: {candidate}", file=sys.stderr)
        return 2
    pristine = candidate.read_text(encoding="utf-8")

    baseline: dict[str, bool] = {}
    rows: list[dict] = []
    failing_sets: dict[str, frozenset[str]] = {}
    all_ok = True
    with tempfile.TemporaryDirectory(prefix="r3b2_closure_mutation_") as td:
        tmp = Path(td)
        pristine_copy = tmp / "pristine.html"
        pristine_copy.write_text(pristine, encoding="utf-8")
        for guard in ("fig", "closure"):
            rc, failed, out = run_audit(guard, pristine_copy, tmp / f"baseline_{guard}.json")
            baseline[guard] = rc == 0 and not failed
            print(f"[{'PASS' if baseline[guard] else 'FAIL'}] pristine {guard} guard green — failed={sorted(failed)}")
            if not baseline[guard]:
                print(out[-4000:])
                all_ok = False

        for name, guard, mutation in MUTATIONS:
            mutated = mutation(pristine)
            assert mutated != pristine, f"{name}: mutation was a no-op"
            path = tmp / f"{name}.html"
            path.write_text(mutated, encoding="utf-8")
            rc, failed, out = run_audit(guard, path, tmp / f"{name}.json")
            got_red = rc != 0 and bool(failed)
            failing_sets[name] = frozenset(failed)
            rows.append({"name": name, "guard": guard, "returncode": rc,
                         "got_red": got_red, "failed_check_ids": sorted(failed)})
            print(f"[{'PASS' if got_red else 'FAIL'}] {name} unique-red candidate — failed={sorted(failed)}")
            if not got_red:
                print(out[-4000:])
                all_ok = False

    collisions: list[dict] = []
    names = [name for name, _guard, _fn in MUTATIONS]
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            if failing_sets[left] == failing_sets[right]:
                collisions.append({"left": left, "right": right,
                                   "failed_check_ids": sorted(failing_sets[left])})
    pairwise = not collisions
    all_ok = all_ok and pairwise
    print(f"[{'PASS' if pairwise else 'FAIL'}] pairwise distinctness — collisions={collisions}")

    payload = {
        "schema": "mastermind.xpv2.sector_r3b2.closure_mutation_results.v1",
        "candidate": candidate.name,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "baseline": baseline,
        "mutations": rows,
        "pairwise_distinct": pairwise,
        "collisions": collisions,
        "pass": all_ok,
    }
    write_reports(Path(args.out), Path(args.json), payload)
    print(f"{sum(1 for r in rows if r['got_red'])}/{len(rows)} mutations produced a red; pairwise_distinct={pairwise}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
