"""Materialize the GMI theme graph — nodes, edges, evidence (masterplan §4.1, W1b).

TWO MODES.

``--backfill`` (one-shot, era=reconstruction)
    Builds the whole graph from the live membership documents, the crosswalk and the
    THS concept map, and stamps every row ``era="reconstruction"`` with ``belief_time``
    = the run's own date. It refuses to run over a populated edge store unless
    ``--force-backfill`` is passed: a second reconstruction would append a whole
    duplicate history under a new belief_time and make the store's own diff meaningless.

default (nightly, era=observed)
    Recomputes tonight's view, diffs it against the stored latest-belief view, and
    appends ONLY what changed. Lane-gated: ledger writes require ``COLLECT_LANE=nightly``
    (fail-closed, defaultless). Off-lane the whole computation still runs and its
    summary is logged — a render lane computes and discards, exactly like every other
    ledger here.

Non-fatal by construction: this is a display-tier product data plane (all six synapse
authority booleans false). A failure here degrades context, never a decision, so the
nightly step must not take the collect lane down with it.

Run: python -m scripts.build_theme_graph [--backfill] [--force-backfill]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import materialize, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_theme_graph")


def _newest_raw_snapshot() -> tuple[str, dict] | None:
    """The newest RAW 同花顺 dump, classified by the seeder's own discriminator.

    The snapshots directory is mixed-shape (raw vendor dumps and byte-copies of
    membership.json share it), so the shape question has exactly one owner:
    ``scripts.seed_china_ths_baskets.classify_snapshot_shape``. Importing it beats
    re-deriving the rule here — two copies of a shape rule is how the two halves drift
    apart and the graph starts "corroborating" a membership against itself.
    """
    try:
        from scripts import seed_china_ths_baskets as seed  # noqa: PLC0415
        raws = seed.raw_snapshots()
    except Exception as exc:  # noqa: BLE001 — corroboration is additive, never fatal
        log.warning("no raw THS snapshot available (%s) — THS memberships will carry "
                    "their membership-document receipt only", exc)
        return None
    if not raws:
        log.info("no raw THS snapshot on disk — THS memberships carry their "
                 "membership-document receipt only")
        return None
    return raws[-1]


def run(*, backfill: bool, force_backfill: bool) -> int:
    lane = store.collect_lane()
    era = "reconstruction" if backfill else "observed"
    stored = store.read_edges(latest_belief=True)

    if backfill and not stored.empty and not force_backfill:
        log.error("edges.parquet already holds %d edges — refusing a second backfill. "
                  "A repeat reconstruction appends a duplicate history under a new "
                  "belief_time and the store can no longer say what changed. Pass "
                  "--force-backfill only if that is genuinely what you want.", len(stored))
        return 1

    view = materialize.build(era=era, raw_snapshot=_newest_raw_snapshot())
    edges = view.edges if backfill else materialize.changed_edges(view.edges, stored)

    log.info("theme graph computed: %d nodes, %d edges (%d to append), %d evidence rows; "
             "era=%s lane=%r", len(view.nodes), len(view.edges), len(edges),
             len(view.evidence), era, lane)
    for suite, why in sorted(view.skipped_suites.items()):
        log.info("  suite %s skipped: %s", suite, why)
    if view.unknown_ths_codes:
        # Weekly THS concept drift. Reported, never fatal — a renamed board is not a
        # broken build, and a build that died on one would take the whole plane down
        # every time 同花顺 reorganised its taxonomy.
        log.info("  %d crosswalk THS code(s) not in the current concept map: %s",
                 len(view.unknown_ths_codes), ", ".join(view.unknown_ths_codes))

    allow = bool(backfill)
    added_nodes = store.write_nodes(view.nodes, lane=lane, allow_backfill=allow)
    added_ev = store.write_evidence(view.evidence, lane=lane, allow_backfill=allow)
    added_edges = store.write_edges(edges, lane=lane, allow_backfill=allow)

    meta = {
        "computed_at": materialize.utc_now_stamp(),
        "engine_version": store.ENGINE_VERSION,
        "mode": "backfill" if backfill else "nightly",
        "era": era,
        "belief_time": materialize.utc_today(),
        "lane": lane,
        "counts": {
            "nodes": int(len(store.read_nodes())),
            "edges": int(len(store.read_edges(latest_belief=False))),
            "edges_latest_belief": int(len(store.read_edges())),
            "evidence": int(len(store.read_evidence())),
        },
        "rows_appended": {"nodes": added_nodes, "edges": added_edges,
                          "evidence": added_ev},
        "per_suite": view.per_suite,
        "skipped_suites": view.skipped_suites,
        "ths_unmapped_concept_count": view.ths_unmapped_concept_count,
        "unknown_ths_codes": view.unknown_ths_codes,
    }
    if store.write_meta(meta, lane=lane, allow_backfill=allow):
        log.info("wrote %s — appended %d nodes / %d edges / %d evidence rows",
                 store.meta_path(), added_nodes, added_edges, added_ev)
    else:
        log.info("off-lane: computed %d nodes / %d edges / %d evidence rows and wrote "
                 "nothing (COLLECT_LANE=%r)", len(view.nodes), len(edges),
                 len(view.evidence), lane)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backfill", action="store_true",
                    help="one-shot era=reconstruction build of the whole graph")
    ap.add_argument("--force-backfill", action="store_true",
                    help="allow --backfill over a populated edge store (rarely right)")
    a = ap.parse_args(argv)
    try:
        return run(backfill=a.backfill, force_backfill=a.force_backfill)
    except Exception:  # noqa: BLE001 — display-tier plane; never break the collect lane
        log.exception("theme graph build failed")
        print("::warning title=theme graph build failed::"
              "scripts.build_theme_graph raised; the graph plane is stale for this run. "
              "Display-tier only — no decision path depends on it — but a repeat means "
              "the membership/crosswalk inputs moved under it.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
