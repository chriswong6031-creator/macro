#!/usr/bin/env python3
"""Gate + nightly counter for the two stretch/extension oracles.

Contract: docs/site_semantics/stretch_oracles.md

The site renders TWO independent answers to "has this name already run" next to each
other in the per-ticker drawer:

  O1  ladder.alignment.overextended          — a 4-leg entry-timing brake (3 oscillator
                                               legs + 1 distance leg), oscillator-DOMINANT
  O2  entry_signal.status == "extended"      — a relabel of ladder.entry.urgency=="caution"

They disagree on ~38% of names. That divergence is LEGITIMATE (a measurement vs a bucket
label), so this script does not try to make them equal. What it enforces is that the
divergence stays *disclosed*: every flagged name must carry the leg that actually fired,
so no consumer has to guess a cause — the failure mode that produced a "Stretched" chip
above a sentence reading "about 9% BELOW its 200-day line".

HARD invariants (exit 1):
  I1  overextended=True  =>  overextended_legs is a non-empty list
  I2  overextended=False =>  overextended_legs is empty
  I3  overextended_basis == overextension_basis(overextended_legs)
  I4  basis=="oscillator" (no distance leg) => NOT (ext_pct_used >= stretch threshold);
      a row that saw a qualifying distance but did not fire the distance leg means the
      producer and the disclosure were computed from different inputs.

MONITORED counters (annotation only, never fatal):
  * the O1 x O2 confusion matrix, with the store's VINTAGE — so a divergence number can
    never again be quoted from a six-week-old local build (see the contract doc: the
    widely-quoted 37.3% came from a store baked 11 days before the two fixes that were
    supposed to have moved it).
  * D2 exposure — rows a distance-narrating renderer would mis-attribute.

Exit 0 clean · 1 contract violation · 2 nothing to check.

Usage:
    python3 scripts/check_stretch_oracle_contract.py [STORE_DIR] [--strict] [--quiet]
    # default STORE_DIR: site/stockdata
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.cycles import (  # noqa: E402
    _EG_STRETCH_BLOCK,
    OVEREXTENSION_LEG_STRETCH,
    OVEREXTENSION_OSCILLATOR_LEGS,
    overextension_basis,
)

DEFAULT_STORE = ROOT / "site" / "stockdata"
_LEG_VOCAB = set(OVEREXTENSION_OSCILLATOR_LEGS) | {OVEREXTENSION_LEG_STRETCH}


def _rows(store: Path):
    """Yield (ticker, alignment, entry_signal, tech, asof) for each ticker JSON."""
    for path in sorted(store.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            j = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(j, dict) or "ticker" not in j:
            continue
        yield (
            j.get("ticker"),
            ((j.get("ladder") or {}).get("alignment") or {}),
            (j.get("entry_signal") or {}),
            (j.get("tech") or {}),
            j.get("asof"),
        )


def check(store: Path, strict: bool = False) -> tuple[int, list[str], dict]:
    """Returns (exit_code, violations, stats)."""
    viol: list[str] = []
    n = n_contract = 0
    cm: Counter = Counter()
    basis_dist: Counter = Counter()
    vintages: Counter = Counter()
    d2_exposure = 0

    for ticker, al, es, tech, asof in _rows(store):
        if not al:
            continue
        n += 1
        vintages[asof] += 1
        over = al.get("overextended")
        status = es.get("status")
        if over is not None and status is not None:
            cm[(over is True, status == "extended")] += 1

        if "overextended_legs" not in al:
            continue                       # pre-contract row; counted below, not judged
        n_contract += 1

        legs = al.get("overextended_legs")
        basis = al.get("overextended_basis")
        ext_used = al.get("ext_pct_used")
        basis_dist[basis] += 1

        if not isinstance(legs, list):
            viol.append(f"{ticker}: overextended_legs is {type(legs).__name__}, expected list")
            continue
        unknown = [x for x in legs if x not in _LEG_VOCAB]
        if unknown:
            viol.append(f"{ticker}: unknown leg name(s) {unknown}")

        # I1 / I2 — the brake and its disclosed cause are one evaluation
        if over is True and not legs:
            viol.append(f"{ticker}: overextended=True but no leg disclosed (I1)")
        if over is not True and legs:
            viol.append(f"{ticker}: overextended={over!r} but legs={legs} disclosed (I2)")

        # I3 — basis is derived, not independently asserted
        want = overextension_basis(legs)
        if basis != want:
            viol.append(f"{ticker}: overextended_basis={basis!r} but legs {legs} imply {want!r} (I3)")

        # I4 — a qualifying distance must have fired the distance leg
        if (basis == "oscillator" and isinstance(ext_used, (int, float))
                and ext_used >= _EG_STRETCH_BLOCK):
            viol.append(
                f"{ticker}: basis='oscillator' but ext_pct_used={ext_used} "
                f">= {_EG_STRETCH_BLOCK} — distance leg should have fired (I4)")

        # monitored: rows a distance-narrating renderer would mis-attribute
        pv = tech.get("pct_vs_200dma")
        if basis == "oscillator" and isinstance(pv, (int, float)):
            d2_exposure += 1

    stats = {
        "n": n,
        "n_contract": n_contract,
        "cm": cm,
        "basis": basis_dist,
        "vintages": vintages,
        "d2_exposure": d2_exposure,
    }
    if n == 0:
        return 2, viol, stats
    if viol:
        return 1, viol, stats
    if n_contract == 0 and strict:
        return 1, [f"no row carries overextended_legs — store is pre-contract ({n} rows)"], stats
    return 0, viol, stats


def _annotate(stats: dict, strict: bool) -> None:
    """Nightly counters. GitHub annotations must START the line and be flushed —
    a logger prefix makes them invisible (house law, tests/test_gh_annotation_line_start.py)."""
    cm = stats["cm"]
    both = sum(cm.values())
    dis = cm[(True, False)] + cm[(False, True)]
    vint = stats["vintages"].most_common(1)
    vintage = vint[0][0] if vint else "unknown"
    pct = (100.0 * dis / both) if both else 0.0
    print(
        f"::notice title=stretch-oracle-divergence::store_vintage={vintage} "
        f"names={stats['n']} both_oracles={both} disagree={dis} ({pct:.1f}%) "
        f"o1_only={cm[(True, False)]} o2_only={cm[(False, True)]} "
        f"agree_flagged={cm[(True, True)]} contract_rows={stats['n_contract']}",
        flush=True,
    )
    if stats["n_contract"]:
        b = stats["basis"]
        print(
            f"::notice title=stretch-oracle-basis::oscillator={b.get('oscillator', 0)} "
            f"stretch={b.get('stretch', 0)} both={b.get('both', 0)} "
            f"not_flagged={b.get(None, 0)} d2_exposure={stats['d2_exposure']}",
            flush=True,
        )
    elif not strict:
        print(
            f"::warning title=stretch-oracle-precontract::store at vintage {vintage} carries "
            f"no overextended_legs on any of {stats['n']} rows — rebuild before quoting a "
            f"divergence number (docs/site_semantics/stretch_oracles.md)",
            flush=True,
        )


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    strict = "--strict" in argv
    quiet = "--quiet" in argv
    store = Path(args[0]) if args else DEFAULT_STORE

    if not store.is_dir():
        print(f"stretch-oracle contract: no store at {store} — nothing to check")
        return 2

    code, viol, stats = check(store, strict=strict)
    if not quiet:
        _annotate(stats, strict)

    if code == 2:
        print(f"stretch-oracle contract: {store} holds no ticker records — nothing to check")
        return 2
    if viol:
        print(f"\nstretch-oracle CONTRACT VIOLATIONS ({len(viol)}):", flush=True)
        for v in viol[:40]:
            print(f"  - {v}")
        if len(viol) > 40:
            print(f"  ... and {len(viol) - 40} more")
        print("\nContract: docs/site_semantics/stretch_oracles.md", flush=True)
        print("::error title=stretch-oracle-contract::"
              f"{len(viol)} row(s) violate the stretch-oracle disclosure contract", flush=True)
        return 1
    print(f"stretch-oracle contract OK — {stats['n_contract']}/{stats['n']} rows carry "
          f"a disclosed basis, 0 violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
