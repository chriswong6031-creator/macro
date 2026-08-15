"""One-shot member-overlap statistics: curated baskets × Finviz subthemes (W3A §4, §9.8).

WHAT IT DOES: computes, for every (curated basket, source subtheme) pair, how much their
LIVE membership overlaps — |A∩B|, Jaccard, and containment in BOTH directions, because a
12-name basket sitting inside a 60-name subtheme and a 60-name subtheme sitting inside a
12-name basket are completely different relationships and one number hides that.

WHAT IT REFUSES: minting anything. G0.13 forbids promoting a string match or an overlap
statistic into an edge, so pairs above the reporting floor land in the probation queue as
``kind=mapping`` proposals with their statistics attached, and a human ratifies specific
pairs later — or does not.

THE NULL BASELINE (§9.8) is the part that makes the floor honest. A containment floor of
0.5 sounds strict until you ask how often a RANDOM basket of the same size clears it, and
the answer depends entirely on the size distribution: small baskets clear high
containments by accident all the time. So every run shuffles the member→basket assignment
k times, preserving each basket's size, recomputes the yield, and prints it beside the
observed yield.

  A note on what is shuffled. Permuting basket ids while their member sets ride along is
  a DEGENERATE null — the pair statistics are numerically identical, so it would report a
  100% false-positive rate by construction and prove nothing. The null that answers the
  question permutes the MEMBERS between baskets (basket labels shuffled across member
  slots), which keeps the size distribution and destroys the real grouping. That is the
  reading implemented here.

Run: python -m scripts.propose_basket_ltheme_relations [--suite baskets]
        [--containment-floor 0.5] [--shuffles 20] [--seed 20260814] [--write]
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import probation, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("propose_basket_ltheme_relations")

#: A REPORTING floor — a visibility cutoff labelled as such, printed with its own null
#: yield beside it. Not a significance threshold and not a promotion rule.
DEFAULT_CONTAINMENT_FLOOR = 0.5
DEFAULT_SHUFFLES = 20
DEFAULT_SEED = 20260814


def _is_null(v: object) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "None")


def _live(row: dict) -> bool:
    return _is_null(row.get("valid_to"))


def membership_sets(edges: list[dict], *, suite: str) -> tuple[dict[str, set[str]],
                                                               dict[str, set[str]]]:
    """``({basket_id: {company}}, {ltheme_id: {company}})`` over LIVE memberships."""
    baskets: dict[str, set[str]] = {}
    lthemes: dict[str, set[str]] = {}
    prefix = f"basket:{suite}:"
    for e in edges:
        if e.get("type") != "MEMBER_OF" or not _live(e):
            continue
        src, dst = str(e.get("src", "")), str(e.get("dst", ""))
        if not src.startswith("co:"):
            continue
        if dst.startswith(prefix):
            baskets.setdefault(dst, set()).add(src)
        elif dst.startswith("ltheme:"):
            lthemes.setdefault(dst, set()).add(src)
    return baskets, lthemes


def pair_stats(a: set[str], b: set[str]) -> dict[str, float]:
    inter = len(a & b)
    union = len(a | b)
    return {
        "overlap": inter,
        "basket_size": len(a),
        "subtheme_size": len(b),
        "jaccard": round(inter / union, 4) if union else 0.0,
        "containment_of_basket": round(inter / len(a), 4) if a else 0.0,
        "containment_of_subtheme": round(inter / len(b), 4) if b else 0.0,
    }


def clearing_pairs(baskets: dict[str, set[str]], lthemes: dict[str, set[str]],
                   floor: float) -> list[dict]:
    out = []
    for bid, members in baskets.items():
        if not members:
            continue
        for lt, lt_members in lthemes.items():
            if not (members & lt_members):
                continue
            stats = pair_stats(members, lt_members)
            if max(stats["containment_of_basket"],
                   stats["containment_of_subtheme"]) >= floor:
                out.append({"basket": bid, "local_theme": lt, **stats})
    out.sort(key=lambda r: (-max(r["containment_of_basket"], r["containment_of_subtheme"]),
                            -r["overlap"], r["basket"], r["local_theme"]))
    return out


def shuffled_yield(baskets: dict[str, set[str]], lthemes: dict[str, set[str]],
                   floor: float, *, shuffles: int, seed: int) -> dict:
    """How many pairs the floor yields when the member→basket grouping is destroyed."""
    universe = sorted({m for members in baskets.values() for m in members})
    sizes = [(bid, len(members)) for bid, members in sorted(baskets.items())]
    rng = random.Random(seed)
    yields: list[int] = []
    for _ in range(max(0, shuffles)):
        pool = list(universe)
        rng.shuffle(pool)
        fake: dict[str, set[str]] = {}
        cursor = 0
        for bid, size in sizes:
            take = pool[cursor:cursor + size]
            cursor += size
            if len(take) < size:            # universe smaller than the sum of sizes:
                take += rng.sample(universe, size - len(take))  # sample with repeats
            fake[bid] = set(take)
        yields.append(len(clearing_pairs(fake, lthemes, floor)))
    yields.sort()
    if not yields:
        return {"shuffles": 0}
    return {
        "shuffles": len(yields),
        "seed": seed,
        "mean": round(sum(yields) / len(yields), 2),
        "median": yields[len(yields) // 2],
        "max": yields[-1],
        "p95": yields[min(len(yields) - 1, int(len(yields) * 0.95))],
        "what_was_shuffled": "members reassigned between baskets, each basket's SIZE "
                             "preserved; permuting basket ids alone is degenerate — the "
                             "pair statistics would be identical",
    }


def build_report(edges: list[dict], *, suite: str, floor: float, shuffles: int,
                 seed: int) -> dict:
    baskets, lthemes = membership_sets(edges, suite=suite)
    observed = clearing_pairs(baskets, lthemes, floor)
    null = shuffled_yield(baskets, lthemes, floor, shuffles=shuffles, seed=seed)
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "suite": suite,
        "baskets": len(baskets),
        "local_themes": len(lthemes),
        "containment_floor": floor,
        "floor_note": "REPORTING floor (a visibility cutoff), not a significance "
                      "threshold and not a promotion rule — read it against the null "
                      "yield below",
        "observed_pairs": len(observed),
        "null_baseline": null,
        "pairs": observed,
        "edges_minted": 0,
        "edges_minted_note": "zero, by law: G0.13 forbids promoting an overlap statistic "
                             "into an edge. These are proposals for a curated act.",
    }


def proposals_from(report: dict) -> list[dict]:
    return [
        probation.make_proposal(
            kind="mapping",
            subject={"basket": row["basket"], "local_theme": row["local_theme"]},
            evidence={k: row[k] for k in
                      ("overlap", "basket_size", "subtheme_size", "jaccard",
                       "containment_of_basket", "containment_of_subtheme")}
            | {"containment_floor": report["containment_floor"],
               "null_baseline": report["null_baseline"]},
            proposed_by="overlap_stats",
            note="member-overlap statistic only. Overlap is not expression: two sets can "
                 "share names because both hold the same mega-caps.")
        for row in report["pairs"]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", default="baskets", help="curated basket suite (default: baskets)")
    ap.add_argument("--containment-floor", type=float, default=DEFAULT_CONTAINMENT_FLOOR)
    ap.add_argument("--shuffles", type=int, default=DEFAULT_SHUFFLES,
                    help=f"null-baseline shuffles (default {DEFAULT_SHUFFLES})")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", help="write the report JSON here (default: stdout)")
    ap.add_argument("--write", action="store_true",
                    help="append the proposals to the probation queue (never edges)")
    a = ap.parse_args(argv)

    edges = store.read_edges(latest_belief=True).to_dict("records")
    if not edges:
        print("::notice title=basket/subtheme overlap::theme graph store is empty — run "
              "scripts.build_theme_graph first", flush=True)
        return 0
    report = build_report(edges, suite=a.suite, floor=a.containment_floor,
                          shuffles=a.shuffles, seed=a.seed)
    if not report["local_themes"]:
        print("::notice title=basket/subtheme overlap::no local_theme memberships in the "
              "store — the local plane has not been materialised yet", flush=True)
        return 0

    if a.write:
        added, skipped = probation.append_proposals(proposals_from(report),
                                                    store.probation_path())
        report["probation"] = {"written": added, "already_present": skipped}
        log.info("probation: %d proposal(s) appended, %d already present", added, skipped)

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        log.info("wrote %s", a.out)
    else:
        print(text)
    log.info("overlap: %d basket(s) × %d local theme(s); %d pair(s) clear containment "
             ">= %.2f; null yield mean %s over %s shuffles",
             report["baskets"], report["local_themes"], report["observed_pairs"],
             a.containment_floor, report["null_baseline"].get("mean"),
             report["null_baseline"].get("shuffles"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
