"""Coverage-gap diagnostic over the theme graph — mechanical, LLM-free (W3A §4, §9.9).

THE QUESTION IT ASKS. Given a set of instruments somebody cares about, which of them does
the concept vocabulary fail to explain? The motivating exemplar is the lithium one: three
names move together, each of them HAS local-theme memberships, and yet no single concept
contains more than one of them — a coverage gap that a per-name "is it in any theme?"
check cannot see, because every name individually looks covered.

So case A is a CO-OCCURRENCE report, not a zero-membership report:

  * pairwise shared-concept counts across the supplied ids;
  * the ids that share NO concept with any other supplied id — the gap signal;
  * ids with zero live memberships at all, reported as a sub-case (they are a different
    failure: no vocabulary rather than no SHARED vocabulary).

Case D is a BREADTH signal: ids whose only memberships are concepts above a reporting
floor. A 200-member concept explains "this is a US equity" more than it explains why
these three names moved. The floor is a REPORT PARAMETER — printed with the breadth
distribution beside it, never a truth claim about where "too broad" begins.

Cases B and C (theme_discovery clusters, co-movement) are documented in the plan and
deferred to W3B, where those inputs have state.

READ-ONLY over the store. The optional ``--propose`` writes probation rows, which are
suggestions in a queue nothing reads without a curated ratification — never edges.

Run: python -m scripts.theme_coverage_gaps --ids-file ids.txt [--out report.json]
                                          [--breadth-floor N] [--propose]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import probation, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("theme_coverage_gaps")

#: Default breadth REPORTING floor. Not a truth claim, not a threshold anything is
#: measured against: a visibility cutoff so a report is readable, printed beside the
#: actual breadth distribution so a reader can see where it sits.
DEFAULT_BREADTH_FLOOR = 25


def _is_null(v: object) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "None")


def _live(row: dict) -> bool:
    return _is_null(row.get("valid_to"))


def read_ids(source: str | None) -> list[str]:
    """Ids from a file, or stdin when the path is '-' or absent."""
    if source and source != "-":
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    out, seen = [], set()
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def resolve_ids(ids: list[str], nodes) -> tuple[dict[str, str], dict[str, str]]:
    """``({supplied: node_id}, {supplied: why_not})``.

    A bare symbol is resolved against the store's company nodes. An AMBIGUOUS symbol —
    the same string listed in two markets — is reported unresolved rather than guessed:
    picking a market for the caller is how a US answer quietly gets computed from a CN
    listing.
    """
    known = {str(n) for n in nodes.get("node_id", [])}
    by_symbol: dict[str, list[str]] = {}
    for nid in known:
        parts = nid.split(":")
        if len(parts) >= 3 and parts[0] == "co":
            by_symbol.setdefault(parts[2].split("#")[0].upper(), []).append(nid)
    resolved, unresolved = {}, {}
    for item in ids:
        if item in known:
            resolved[item] = item
            continue
        hits = by_symbol.get(item.upper(), [])
        if len(hits) == 1:
            resolved[item] = hits[0]
        elif len(hits) > 1:
            unresolved[item] = f"ambiguous across markets: {sorted(hits)}"
        else:
            unresolved[item] = "no company node with this id or symbol"
    return resolved, unresolved


def membership_index(edges: list[dict]) -> tuple[dict[str, set[str]], dict[str, int]]:
    """``({company_node: {local_theme}}, {local_theme: live_member_count})``.

    Both membership paths are folded in: the direct company→local_theme claim, and the
    two-hop company→basket→local_theme join the CN plane uses. The breadth count is the
    concept's TOTAL live membership, not just the supplied ids' share of it.
    """
    basket_ltheme: dict[str, set[str]] = {}
    for e in edges:
        if (e.get("type") == "EXPRESSES" and _live(e)
                and str(e.get("src", "")).startswith("basket:")
                and str(e.get("dst", "")).startswith("ltheme:")):
            basket_ltheme.setdefault(str(e["src"]), set()).add(str(e["dst"]))

    per_company: dict[str, set[str]] = {}
    for e in edges:
        if e.get("type") != "MEMBER_OF" or not _live(e):
            continue
        src, dst = str(e.get("src", "")), str(e.get("dst", ""))
        if not src.startswith("co:"):
            continue
        if dst.startswith("ltheme:"):
            per_company.setdefault(src, set()).add(dst)
        elif dst.startswith("basket:"):
            for lt in basket_ltheme.get(dst, ()):
                per_company.setdefault(src, set()).add(lt)

    breadth: dict[str, int] = {}
    for company, themes in per_company.items():
        for lt in themes:
            breadth[lt] = breadth.get(lt, 0) + 1
    return per_company, breadth


def analyse(ids: list[str], nodes, edges: list[dict], *,
            breadth_floor: int = DEFAULT_BREADTH_FLOOR) -> dict:
    resolved, unresolved = resolve_ids(ids, nodes)
    per_company, breadth = membership_index(edges)
    memberships = {sup: per_company.get(node, set()) for sup, node in resolved.items()}

    pairs = []
    supplied = sorted(memberships)
    for i, a in enumerate(supplied):
        for b in supplied[i + 1:]:
            shared = memberships[a] & memberships[b]
            if shared:
                pairs.append({"a": a, "b": b, "shared": len(shared),
                              "concepts": sorted(shared)})
    pairs.sort(key=lambda p: (-p["shared"], p["a"], p["b"]))

    has_partner = {name for p in pairs for name in (p["a"], p["b"])}
    zero_membership = sorted(s for s in supplied if not memberships[s])
    isolated = sorted(s for s in supplied if s not in has_partner and memberships[s])
    broad_only = sorted(
        s for s in supplied
        if memberships[s] and all(breadth.get(lt, 0) >= breadth_floor
                                  for lt in memberships[s]))

    sizes = sorted(breadth.values())
    distribution = {
        "concepts_with_live_members": len(sizes),
        "median_members": (sizes[len(sizes) // 2] if sizes else 0),
        "p90_members": (sizes[int(len(sizes) * 0.9)] if sizes else 0),
        "max_members": (sizes[-1] if sizes else 0),
    }
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "rule": "coverage_gaps.v1 (mechanical, LLM-free; case A co-occurrence + case D "
                "breadth signal). Cases B/C need theme_discovery clusters and co-movement "
                "state — deferred to W3B, where those inputs exist.",
        "supplied": len(ids),
        "resolved": len(resolved),
        "unresolved": unresolved,
        "case_a_cooccurrence": {
            "pairs_sharing_a_concept": pairs[:200],
            "isolated_ids": isolated,
            "isolated_note": "these ids HAVE memberships, but share no concept with any "
                             "other supplied id — the gap the per-name check cannot see",
            "zero_membership_ids": zero_membership,
            "zero_membership_note": "a different failure from isolation: no vocabulary at "
                                    "all, rather than no shared vocabulary",
        },
        "case_d_breadth": {
            "reporting_floor_members": breadth_floor,
            "floor_note": "a REPORT PARAMETER, not a truth claim about where 'too broad' "
                          "begins; the distribution below is what it should be read "
                          "against",
            "breadth_distribution": distribution,
            "broad_only_ids": broad_only,
        },
        "membership_detail": {s: sorted(m) for s, m in sorted(memberships.items())},
    }


def proposals_from(report: dict) -> list[dict]:
    """Probation rows for the isolated ids. Suggestions in a queue, never edges."""
    isolated = report["case_a_cooccurrence"]["isolated_ids"]
    if len(isolated) < 2:
        return []
    return [probation.make_proposal(
        kind="new_theme",
        subject={"instrument_ids": sorted(isolated)},
        evidence={"rule": report["rule"],
                  "breadth_floor": report["case_d_breadth"]["reporting_floor_members"],
                  "supplied": report["supplied"], "resolved": report["resolved"]},
        proposed_by="coverage_gap",
        note="ids that co-occur in the caller's question but share no concept — a "
             "candidate vocabulary gap, NOT a theme. Ratification is a curated act.")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids-file", default="-",
                    help="file of instrument node ids or symbols, one per line ('-' = stdin)")
    ap.add_argument("--out", help="write the report JSON here (default: stdout)")
    ap.add_argument("--breadth-floor", type=int, default=DEFAULT_BREADTH_FLOOR,
                    help=f"case-D reporting floor in live members (default "
                         f"{DEFAULT_BREADTH_FLOOR}); printed in the report")
    ap.add_argument("--propose", action="store_true",
                    help="append probation proposals for isolated ids (never edges)")
    a = ap.parse_args(argv)

    ids = read_ids(a.ids_file)
    if not ids:
        print("::notice title=theme coverage gaps::no instrument ids supplied — nothing "
              "to diagnose", flush=True)
        return 0
    nodes = store.read_nodes()
    edges = store.read_edges(latest_belief=True).to_dict("records")
    if not len(nodes) or not edges:
        print("::notice title=theme coverage gaps::theme graph store is empty — run "
              "scripts.build_theme_graph first; an empty store is INDETERMINATE, not a "
              "coverage answer", flush=True)
        return 0

    report = analyse(ids, nodes, edges, breadth_floor=a.breadth_floor)
    if a.propose:
        rows = proposals_from(report)
        added, skipped = probation.append_proposals(rows, store.probation_path())
        report["probation"] = {"written": added, "already_present": skipped}
        log.info("probation: %d proposal(s) appended, %d already present", added, skipped)

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        log.info("wrote %s", a.out)
    else:
        print(text)
    log.info("coverage gaps: %d/%d ids resolved; %d isolated, %d with zero membership, "
             "%d broad-only (floor %d)", report["resolved"], report["supplied"],
             len(report["case_a_cooccurrence"]["isolated_ids"]),
             len(report["case_a_cooccurrence"]["zero_membership_ids"]),
             len(report["case_d_breadth"]["broad_only_ids"]), a.breadth_floor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
