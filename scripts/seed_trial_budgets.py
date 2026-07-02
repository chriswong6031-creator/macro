#!/usr/bin/env python3
"""One-time retrospective seeding of the Trial Ledger for grandfathered harnesses (W1d).

Audit #21: the ledger had 20 entries and ZERO declared budgets across ~25+ harnesses, so
multiple-testing deflation was near-inert. Counting the TRUE budget across 404 engine files
exactly is intractable (every parameter tried in development is a trial); the honest move is a
documented UPPER-BOUND estimate marked ``basis: estimated`` — "a documented upper-bound guess
beats zero". This script writes one such estimate per grandfathered harness so its DSR/kill/FDR
deflation reflects a real search space instead of nothing.

Estimation rule (deliberately conservative — over-counting is the safe direction, de Prado):
  * ``in-code``  — the largest ``n_trials=<literal>`` or ``len(<grid>)`` the harness itself uses
    (its own honest itemized count), read statically.
  * ``research`` — a ×RESEARCH_MULT bump for the specs tried during development that never made
    it into the final grid (thresholds, windows, and variants iterated on before the harness
    was frozen). Floored at MIN_BUDGET so a 1-config harness still carries a non-trivial count.

The result is idempotent (log_declared_budget dedups on family+n+reason); re-running does not
inflate N. Families are named ``<harness_stem>`` so ``walk_forward._ledger_n_trials`` and any
``deflated_sharpe(family=...)`` migration can find them.

Run:  python3 scripts/seed_trial_budgets.py            # write the estimates
      python3 scripts/seed_trial_budgets.py --dry-run  # print what it WOULD write
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402

# import the frozen grandfathered set so this seeder and the CI lint agree on scope.
try:
    from scripts.check_trial_registration import LEGACY_UNREGISTERED  # noqa: E402
except ImportError:  # scripts/ is not always a package on the path
    sys.path.insert(0, str(_ROOT / "scripts"))
    from check_trial_registration import LEGACY_UNREGISTERED  # noqa: E402

RESEARCH_MULT = 3          # dev-time specs tried per shipped config (conservative upper bound)
MIN_BUDGET = 8             # a harness that deflates a Sharpe searched at LEAST this much


def _in_code_trials(path: Path) -> int:
    """Largest static multiple-testing count the harness itself uses: a literal
    ``n_trials=<int>`` or a ``len(<grid>)`` where the grid literal is countable."""
    txt = path.read_text(encoding="utf-8")
    best = 1
    # literal n_trials=<int>
    for m in re.finditer(r"n_trials\s*=\s*(\d+)", txt):
        best = max(best, int(m.group(1)))
    # a grid list/tuple literal assigned to a *grid*/*GRID*/*variants* name — count its elements
    try:
        tree = ast.parse(txt, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    nm = getattr(tgt, "id", "") or ""
                    if re.search(r"grid|variant|spec|combo|config", nm, re.I):
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            best = max(best, len(node.value.elts))
    except SyntaxError:
        pass
    return best


def estimate(path: Path) -> tuple[int, str]:
    ic = _in_code_trials(path)
    budget = max(MIN_BUDGET, ic * RESEARCH_MULT)
    reason = (f"in-code n_trials≈{ic} ×{RESEARCH_MULT} research specs "
              f"(floor {MIN_BUDGET}); retrospective upper bound")
    return budget, reason


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dry = "--dry-run" in argv
    led = None if dry else TrialLedger()
    n_written = 0
    for rel in sorted(LEGACY_UNREGISTERED):
        p = _ROOT / rel
        if not p.exists():
            print(f"  SKIP (missing): {rel}", file=sys.stderr)
            continue
        family = p.stem
        budget, reason = estimate(p)
        note = f"[estimated] {reason}"
        if dry:
            print(f"  {family:38s} budget={budget:4d}  {reason}")
        else:
            wrote = led.log_declared_budget(budget, family=family, reason=note)
            n_written += int(wrote)
            print(f"  {family:38s} budget={budget:4d}  {'(new)' if wrote else '(dup)'}")
    if dry:
        print(f"\nDRY RUN — {len(LEGACY_UNREGISTERED)} families would be seeded.")
    else:
        print(f"\nSeeded {n_written} NEW declared budgets ({len(LEGACY_UNREGISTERED)} families total, "
              f"basis=estimated) into {TrialLedger().path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
