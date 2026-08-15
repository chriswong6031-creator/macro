"""Operator proof: today's China board under the v3 ORDER and the v4 ORDER, side by side.

WHAT THIS IS
    A receipt, not a study.  It answers one question — "what actually changes on the
    board?" — so the operator can look at the resulting names immediately instead of
    waiting for a forward record.  It makes NO promotion claim, computes NO forward
    outcome, and reads NO research artifact.

HOW IT STAYS FAITHFUL
    v4 changed the board's ORDER and nothing else: every admission gate (signal
    freshness, prime entry window, confirmed-late, relay-late, fillability, liquidity
    floor, extension, non-entry stage) is v3's, unchanged.  Every one of those gates is
    ORDER-INDEPENDENT — a name either clears it or does not, regardless of who is ranked
    above it.  Only two lane reasons depend on order: ``featured_cap`` and ``sector_cap``.

    So this script does not re-derive a single gate.  It reads the PUBLISHED board
    (``site/factordata/china_standouts.json``), takes each row's live lane and
    lane_reasons as ground truth, and re-runs ONLY the capped allocation in v4 order:

        featured-clear  :=  currently featured
                        OR  currently more_actionable for cap reasons alone

    Those rows are re-allocated against the same FEATURED_CAP / SECTOR_CAP in v4 order.
    Any row whose demotion reason was a real gate stays demoted, in both boards.

    That makes the diff below exactly attributable to the ordering change — nothing in
    it can come from a re-derived gate, because no gate was re-derived.

USAGE
    python3 -m scripts.cn_prophet_v4_proof [--top 30] [--out research/cn_prophet_v4]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import china_board_rank as R  # noqa: E402
from engine import china_intel_interest as CII  # noqa: E402

log = logging.getLogger("cn_prophet_v4_proof")

BOARD_JSON = "site/factordata/china_standouts.json"
LANES = ("buy", "more_actionable", "late_or_unfillable", "forming")
#: The only two lane reasons that depend on ranking order.
CAP_REASONS = frozenset({"featured_cap", "sector_cap"})


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_board() -> dict:
    path = _root() / BOARD_JSON
    if not path.exists():
        raise SystemExit(f"board artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(board: dict) -> list[dict]:
    """Every eligible row across the four lossless lanes, lane stamped."""
    out: list[dict] = []
    for key in LANES:
        for row in board.get(key) or []:
            if not isinstance(row, dict) or not row.get("ticker"):
                continue
            row = dict(row)
            row["_lane"] = "featured" if key == "buy" else key
            out.append(row)
    return out


def _prophet_score(row: dict) -> float:
    score = (row.get("prophet") or {}).get("score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _is_featured_clear(row: dict) -> bool:
    """True when v3 admitted the row to the shelf, or excluded it ONLY for a cap.

    A row demoted for any real gate is not cap-limited and can never be rescued by
    re-ordering — it stays demoted under both boards.
    """
    if row["_lane"] == "featured":
        return True
    if row["_lane"] != "more_actionable":
        return False
    reasons = set(row.get("lane_reasons") or [])
    return bool(reasons) and reasons <= CAP_REASONS


def _allocate(clear_rows: list[dict], featured_cap: int, sector_cap: int) -> list[str]:
    """Re-run the capped shelf allocation over pre-ordered rows.  Returns tickers."""
    featured: list[str] = []
    per_sector: dict[str, int] = defaultdict(int)
    for row in clear_rows:
        if len(featured) >= featured_cap:
            continue
        sector = str(row.get("sector") or "—")
        if per_sector[sector] >= sector_cap:
            continue
        per_sector[sector] += 1
        featured.append(str(row["ticker"]))
    return featured


def build_proof(top: int = 30) -> dict[str, Any]:
    board = _load_board()
    rows = _rows(board)
    if not rows:
        raise SystemExit("board artifact carries no eligible rows")

    interest = CII.build_interest_map(str(r["ticker"]) for r in rows)
    coverage = CII.coverage(interest)

    for row in rows:
        record = interest.get(str(row["ticker"]).upper().strip()) or {}
        row["_intel"] = record
        row["_intel_score"] = record.get("score")
        row["_intel_basis"] = record.get("basis", R.INTEL_BASIS_FALLBACK)
        row["_prophet_score"] = _prophet_score(row)
        # Same key the engine orders by, fed from the published row.
        row["_v4_key"] = R.intel_order_key({
            "ticker": row["ticker"],
            "prophet_score": row["_prophet_score"],
            "intel_interest_score": row["_intel_score"],
            "intel_interest_basis": row["_intel_basis"],
        })

    v3_order = sorted(rows, key=lambda r: (-r["_prophet_score"], str(r["ticker"])))
    v4_order = sorted(rows, key=lambda r: r["_v4_key"])
    v3_rank = {str(r["ticker"]): i for i, r in enumerate(v3_order, start=1)}
    v4_rank = {str(r["ticker"]): i for i, r in enumerate(v4_order, start=1)}

    featured_cap = int(board.get("lane_counts", {}).get("featured_cap")
                       or R.FEATURED_CAP)
    sector_cap = int(R.SECTOR_CAP)
    clear = [r for r in rows if _is_featured_clear(r)]
    v3_featured = _allocate(sorted(clear, key=lambda r: (-r["_prophet_score"],
                                                        str(r["ticker"]))),
                            featured_cap, sector_cap)
    v4_featured = _allocate(sorted(clear, key=lambda r: r["_v4_key"]),
                            featured_cap, sector_cap)

    # Sanity: the reconstruction must reproduce the live shelf exactly, or the
    # comparison below is measuring the reconstruction rather than the change.
    live_featured = [str(r["ticker"]) for r in rows if r["_lane"] == "featured"]
    reconstruction_ok = set(v3_featured) == set(live_featured)

    by_ticker = {str(r["ticker"]): r for r in rows}

    def row_view(ticker: str) -> dict:
        row = by_ticker[ticker]
        record = row["_intel"]
        return {
            "ticker": ticker,
            "name": row.get("name"),
            "sector": row.get("sector"),
            "lane": row["_lane"],
            "lane_reasons": list(row.get("lane_reasons") or []),
            "entry_status": (row.get("entry_signal") or {}).get("status"),
            "stage": row.get("stage"),
            "v3_rank": v3_rank[ticker],
            "v4_rank": v4_rank[ticker],
            "rank_move": v3_rank[ticker] - v4_rank[ticker],
            "prophet_score_v3": round(row["_prophet_score"], 2),
            "intel_interest_score": row["_intel_score"],
            "intel_interest_basis": row["_intel_basis"],
            "intel_drivers": list(record.get("drivers") or []),
            "intel_signal_core": record.get("signal_core"),
            "intel_edge_remaining": record.get("edge_remaining"),
            "intel_leading_gap": record.get("gap"),
            "intel_unavailable_reason": record.get("unavailable_reason"),
        }

    return {
        "generated_from": BOARD_JSON,
        "board_asof": board.get("as_of"),
        "live_definition": R.BOARD_DEFINITION,
        "shadow_definition": R.V3_SHADOW_DEFINITION,
        "ordering": R.INTEL_INTEREST_ORDER,
        "n_rows": len(rows),
        "featured_cap": featured_cap,
        "sector_cap": sector_cap,
        "reconstruction_matches_live_shelf": reconstruction_ok,
        "intel_coverage": coverage,
        "excludes": list(CII.BOARD_DERIVED_TERMS_EXCLUDED),
        "top_v4": [row_view(str(r["ticker"])) for r in v4_order[:top]],
        "top_v3": [row_view(str(r["ticker"])) for r in v3_order[:top]],
        "featured_v3": v3_featured,
        "featured_v4": v4_featured,
        "featured_added_by_v4": [row_view(t) for t in v4_featured
                                 if t not in set(v3_featured)],
        "featured_dropped_by_v4": [row_view(t) for t in v3_featured
                                   if t not in set(v4_featured)],
        "biggest_promotions": [row_view(str(r["ticker"])) for r in
                               sorted(rows, key=lambda r: v4_rank[str(r["ticker"])]
                                      - v3_rank[str(r["ticker"])])[:10]],
        "biggest_demotions": [row_view(str(r["ticker"])) for r in
                              sorted(rows, key=lambda r: v3_rank[str(r["ticker"])]
                                     - v4_rank[str(r["ticker"])])[:10]],
    }


def _fmt_table(views: list[dict], limit: int) -> list[str]:
    lines = [
        "| # | ticker | sector | lane | entry | v3 rank | v4 rank | move | v3 score | intel | basis | top intelligence drivers |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for i, v in enumerate(views[:limit], start=1):
        intel = "—" if v["intel_interest_score"] is None else f"{v['intel_interest_score']:.2f}"
        move = v["rank_move"]
        move_s = f"+{move}" if move > 0 else str(move)
        drivers = "; ".join(v["intel_drivers"]) or "—"
        lines.append(
            f"| {i} | `{v['ticker']}` | {v['sector'] or '—'} | {v['lane']} | "
            f"{v['entry_status'] or '—'} | {v['v3_rank']} | {v['v4_rank']} | {move_s} | "
            f"{v['prophet_score_v3']:.2f} | {intel} | {v['intel_interest_basis']} | {drivers} |"
        )
    return lines


def render_markdown(proof: dict, top: int) -> str:
    cov = proof["intel_coverage"]
    out: list[str] = []
    out.append(f"# CN Prophet v4 vs v3 — board ordering proof ({proof['board_asof']})")
    out.append("")
    out.append(
        "Generated by `scripts/cn_prophet_v4_proof.py` from the published board "
        f"(`{proof['generated_from']}`). **This is a receipt, not a study**: no forward "
        "outcome is computed, no promotion is claimed, and the v4 ordering has no "
        "accrued record. It exists so the resulting names can be looked at now."
    )
    out.append("")
    out.append("## What changed")
    out.append("")
    out.append(
        f"- Live definition: `{proof['live_definition']}` — rank by "
        f"`{proof['ordering']}`, gate by the unchanged v3 entry machinery."
    )
    out.append(f"- Displaced v3 ordering shadow: `{proof['shadow_definition']}`.")
    out.append(
        "- The v3 **score** is untouched: no intelligence term enters `prophet_score`."
    )
    out.append(
        f"- Board-independent by construction — excluded: "
        f"{', '.join('`' + t + '`' for t in proof['excludes'])}."
    )
    out.append("")
    out.append("## Intelligence coverage")
    out.append("")
    out.append(
        f"- **{cov['n_measured']} / {cov['n_rows']} rows measured "
        f"({cov['measured_rate_pct']}%)**; {cov['n_fallback_v3']} fell back to v3 priority."
    )
    if cov.get("fallback_reasons"):
        out.append(f"- Fallback reasons: `{json.dumps(cov['fallback_reasons'])}`.")
    out.append(
        f"- Measured score range: {cov['score_min']} … {cov['score_max']} "
        f"(median {cov['score_median']})."
    )
    out.append(
        f"- Shelf reconstruction reproduces the live featured set exactly: "
        f"**{proof['reconstruction_matches_live_shelf']}** — so every difference below "
        "is attributable to the ordering change alone."
    )
    out.append("")
    out.append(f"## Top {top} — V4 order (live)")
    out.append("")
    out.extend(_fmt_table(proof["top_v4"], top))
    out.append("")
    out.append(f"## Top {top} — V3 order (displaced, now shadow)")
    out.append("")
    out.extend(_fmt_table(proof["top_v3"], top))
    out.append("")
    out.append("## Featured shelf movement")
    out.append("")
    out.append(
        f"- v3 shelf: {len(proof['featured_v3'])} names · v4 shelf: "
        f"{len(proof['featured_v4'])} names "
        f"(cap {proof['featured_cap']}, sector cap {proof['sector_cap']})."
    )
    out.append("")
    out.append("**Newly featured under v4**")
    out.append("")
    if proof["featured_added_by_v4"]:
        out.extend(_fmt_table(proof["featured_added_by_v4"], 50))
    else:
        out.append("_none — the shelf composition is unchanged._")
    out.append("")
    out.append("**Dropped from featured under v4**")
    out.append("")
    if proof["featured_dropped_by_v4"]:
        out.extend(_fmt_table(proof["featured_dropped_by_v4"], 50))
    else:
        out.append("_none._")
    out.append("")
    out.append("## Biggest rank moves")
    out.append("")
    out.append("**Promoted by intelligence interest**")
    out.append("")
    out.extend(_fmt_table(proof["biggest_promotions"], 10))
    out.append("")
    out.append("**Demoted by intelligence interest**")
    out.append("")
    out.extend(_fmt_table(proof["biggest_demotions"], 10))
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--out", default="research/cn_prophet_v4")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    proof = build_proof(top=args.top)

    out_dir = _root() / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(proof.get("board_asof") or "unknown")[:10]
    json_path = out_dir / f"v4_vs_v3_board_proof_{stamp}.json"
    md_path = out_dir / f"V4_VS_V3_BOARD_PROOF_{stamp}.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    md_path.write_text(render_markdown(proof, args.top), encoding="utf-8")
    print(f"wrote {md_path.relative_to(_root())}")
    print(f"wrote {json_path.relative_to(_root())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
