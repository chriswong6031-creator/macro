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

Both modes also re-derive the CAPABILITY side-car (W3A §9.3) — never a node column,
because node rows are write-once and a capability written onto one would be a ratchet
that outlived every later substrate improvement — and both pass through the source-family
SHRINK WALL: a build that would close more than a quarter of a family's live memberships
refuses unless ``--allow-source-shrink <family>`` says the restructure is real. That wall
sits on the write path rather than the refresh path on purpose: a hand-edited input never
goes near a refresh run, and in an append-only store its closures are permanent.

Non-fatal by construction: this is a display-tier product data plane (all six synapse
authority booleans false). A failure here degrades context, never a decision, so the
nightly step must not take the collect lane down with it.

Run: python -m scripts.build_theme_graph [--backfill] [--force-backfill]
     [--allow-source-shrink FAMILY]
"""
from __future__ import annotations

import argparse
import json
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


def _capability_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = str(r.get("capability"))
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def _identity_resolution_state_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = str(r.get("resolution_state"))
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def run(*, backfill: bool, force_backfill: bool,
        allow_source_shrink: tuple[str, ...] = ()) -> int:
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

    # SECOND WALL (§2). The refresh contract's interlocks guard the path a refresh takes;
    # this one guards the path every WRITE takes, so a hand-edited or truncated input
    # that never went through a refresh still cannot mass-close a source family. Refusing
    # here is cheap; un-closing 2,000 permanent rows in an append-only store is not.
    refusals = materialize.source_shrink_refusals(edges, stored, allow=allow_source_shrink)
    if refusals:
        for r in refusals:
            log.error("theme graph shrink wall: %s", r)
        print("::warning title=theme graph source shrink refused::" + "; ".join(refusals),
              flush=True)
        return 1

    log.info("theme graph computed: %d nodes, %d edges (%d to append), %d evidence rows, "
             "%d capability rows %s, %d identity resolution rows %s; era=%s lane=%r",
             len(view.nodes), len(view.edges), len(edges), len(view.evidence),
             len(view.capability), _capability_counts(view.capability),
             len(view.identity_resolution),
             _identity_resolution_state_counts(view.identity_resolution), era, lane)
    for family, report in sorted(view.local_plane.items()):
        log.info("  local plane %s: %s", family, json.dumps(report, ensure_ascii=False,
                                                            sort_keys=True)[:600])
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
    # Re-derived every run, never carried forward: a node whose price coverage improved
    # is re-classified UP tonight, which is the whole reason capability is a side-car and
    # not a write-once node column.
    added_cap = store.write_capability(view.capability, lane=lane, allow_backfill=allow)
    # V4-D2A: same re-derivation discipline — a node NOT_IN_MASTER tonight may resolve
    # tomorrow as the Data OS master's coverage grows.
    added_idres = store.write_identity_resolution(view.identity_resolution, lane=lane,
                                                   allow_backfill=allow)

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
            "capability": int(len(store.read_capability())),
            "identity_resolution": int(len(store.read_identity_resolution())),
        },
        "rows_appended": {"nodes": added_nodes, "edges": added_edges,
                          "evidence": added_ev, "capability": added_cap,
                          "identity_resolution": added_idres},
        "identity_resolution_state_counts":
            _identity_resolution_state_counts(view.identity_resolution),
        "per_suite": view.per_suite,
        "skipped_suites": view.skipped_suites,
        "ths_unmapped_concept_count": view.ths_unmapped_concept_count,
        "unknown_ths_codes": view.unknown_ths_codes,
        # The local plane's own report: the vintage ladder it read, and the company-mint
        # resolution table printed rather than estimated (§9.13).
        "local_plane": view.local_plane,
        "unknown_ths_concepts": view.unknown_ths_concepts,
        "capability_counts": _capability_counts(view.capability),
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
    ap.add_argument("--allow-source-shrink", action="append", default=[],
                    metavar="FAMILY",
                    help="permit this source family's live memberships to shrink past "
                         "the wall (repeatable). For a REAL vendor restructure — the "
                         "flag exists so the decision has a name attached")
    a = ap.parse_args(argv)
    try:
        return run(backfill=a.backfill, force_backfill=a.force_backfill,
                   allow_source_shrink=tuple(a.allow_source_shrink))
    except Exception:  # noqa: BLE001 — display-tier plane; never break the collect lane
        log.exception("theme graph build failed")
        print("::warning title=theme graph build failed::"
              "scripts.build_theme_graph raised; the graph plane is stale for this run. "
              "Display-tier only — no decision path depends on it — but a repeat means "
              "the membership/crosswalk inputs moved under it.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
