"""engine.neuralweb.confluence — Confluence Graph v1 (Neural Web W4).

PURPOSE
-------
build_graph(root) constructs the confluence graph over the signal bus:

  Nodes:
    engine    — one per engine family in spine_index (us_board, altdata, radar, etc.)
    sector    — oracle_state.json complexes[] + 11 GICS sector ids
    regime    — 4 regime quads + __all__
    thesis    — active theses from data/radar/theses.jsonl
    episode   — oracle_state.json active_episodes[] (summarised, capped 50 most recent)

  Edges:
    feeds       — structural data-flow from config/synapse.yml producer→artifact→consumer
    stable      — Oracle edge_stability where stable==True (READ-ONLY): graph_s Tier-S
                  all stable pairs + graph_m Tier-M capped to complex-level
    leads       — Oracle graph_m.json leadlag records (include honest nulls)
    contradicts — from detect_contradictions() output
    confirms    — co-firing lift from spine_index (same symbol+as_of+direction+horizon
                  across different engines; MIN_N=10; below floor → edge with n + lift=null)

HARD LAW — encoded in every docstring and in the artifact output:
    Confluence NEVER gates, NEVER ranks, NEVER raises a priority.  Every edge carries
    display_only=True.  No cross-engine hard gate without its own pre-registered gauntlet
    (the China falsification precedent).  Edge promotion beyond display requires its own
    registered gauntlet result committed to config/qual_ladder.yml.

SCHEMA
------
data/neuralweb/confluence_graph.json — artifact_id 'confluence-graph'
{
  "schema":         "neuralweb.confluence_graph.v1",
  "artifact_id":    "confluence-graph",
  "asof":           <str>,
  "tier":           "display",
  "is_context_only": true,
  "display_only":   true,
  "hard_law":       "confluence never gates never ranks ...",
  "nodes":          [{"id", "type", "label", "meta"}],
  "edges":          [{"src", "dst", "edge_type", "n", "stable", "display_only",
                      "regime", "note"}],
  "contradiction_summary": {"n": int, "by_severity": {...}, "top_pair_ids": [...]},
  "gaps":           [str],
  "produced_by":    "engine/neuralweb/confluence.py",
  "produced_at":    <utc str>
}

FAIL-OPEN CONTRACT
------------------
Every source is read fail-open.  Absent Oracle graph files → omit stable/leads edges
and note in gaps.  Absent oracle_state.json → omit sector/episode nodes.  The graph
is always returned (possibly sparse with many gaps).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb.contradictions import detect_contradictions

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA = "neuralweb.confluence_graph.v1"
_HARD_LAW = (
    "HARD LAW: confluence never gates, never ranks, never raises a priority.  "
    "All edges are display_only=True.  Cross-engine hard gates require their own "
    "pre-registered gauntlet (China falsification precedent).  Edge promotion beyond "
    "display requires a registered gauntlet result in config/qual_ladder.yml."
)

_GICS_11 = [
    ("xlk", "Technology"),
    ("xlc", "Communication Services"),
    ("xly", "Consumer Discretionary"),
    ("xlp", "Consumer Staples"),
    ("xlv", "Health Care"),
    ("xlf", "Financials"),
    ("xli", "Industrials"),
    ("xlb", "Materials"),
    ("xle", "Energy"),
    ("xlre", "Real Estate"),
    ("xlu", "Utilities"),
]

_REGIME_QUADS = ["Q1", "Q2", "Q3", "Q4"]

_MIN_N_COFIRING = 10  # minimum n for co-firing lift edge


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence: unreadable %s — %s", p, exc)
        return None


def _node(nid: str, ntype: str, label: str, meta: dict | None = None) -> dict:
    return {"id": nid, "type": ntype, "label": label, "meta": meta or {}}


# ---------------------------------------------------------------------------
# R-ORTH PR-4: independence block reader
# ---------------------------------------------------------------------------

def _read_independence_block(repo: Path, gaps: list[str]) -> dict:
    """Read the lobes block from data/neuralweb/covariance_spine.json fail-open.

    Returns a top-level "independence" dict for embedding in confluence_graph.json.
    If the file is absent or the lobes block is null, returns a null-valued dict
    and appends a gap note; never raises.

    Fields:
      effective_independent_lobes  — participation-ratio estimate (float | null)
      n_lobes_measurable           — engines with >= 30 active weeks (int | null)
      n_lobes_total                — total engines in spine_index (int | null)
      pctile_vs_null               — lobes pctile vs. 200 circular-shift draws (float | null)
      same_bet_warning             — warning object or null
      dominant_overlap_cluster     — largest cluster engine list or null
      descriptive_not_gauntleted   — always True (F-ORTH-1 house law)
      display_only                 — always True
      source                       — "data/neuralweb/covariance_spine.json"
    """
    _null = {
        "effective_independent_lobes": None,
        "n_lobes_measurable": None,
        "n_lobes_total": None,
        "pctile_vs_null": None,
        "same_bet_warning": None,
        "dominant_overlap_cluster": None,
        "descriptive_not_gauntleted": True,
        "display_only": True,
        "source": "data/neuralweb/covariance_spine.json",
    }

    spine_path = repo / "data" / "neuralweb" / "covariance_spine.json"
    if not spine_path.exists():
        gaps.append(
            "independence: data/neuralweb/covariance_spine.json absent — "
            "independence block null; run scripts/build_covariance_spine.py"
        )
        return _null

    raw = _read_json(spine_path)
    if raw is None:
        gaps.append("independence: covariance_spine.json unreadable — independence block null")
        return _null

    lobes = (raw.get("blocks") or {}).get("lobes")
    if lobes is None:
        gaps.append(
            "independence: covariance_spine.json has no lobes block — "
            "spine_index.parquet may be absent or too sparse"
        )
        return _null

    # Extract pctile from nested null_reference
    null_ref = lobes.get("null_reference") or {}
    pctile = null_ref.get("pctile_vs_null")

    # dominant_overlap_cluster: largest cluster by engine list length
    clusters = lobes.get("clusters") or []
    dominant: list | None = None
    if clusters:
        largest = max(clusters, key=lambda c: len(c.get("engines") or []))
        dominant = largest.get("engines") or None

    sbw = lobes.get("same_bet_warning")
    # Only propagate the warning object when active; pass null otherwise
    same_bet = sbw if (sbw and sbw.get("active")) else None

    return {
        "effective_independent_lobes": lobes.get("effective_independent_lobes"),
        "n_lobes_measurable": lobes.get("n_lobes_measurable"),
        "n_lobes_total": lobes.get("n_lobes_total"),
        "pctile_vs_null": pctile,
        "same_bet_warning": same_bet,
        "dominant_overlap_cluster": dominant,
        "descriptive_not_gauntleted": True,
        "display_only": True,
        "source": "data/neuralweb/covariance_spine.json",
    }



def _edge(
    src: str,
    dst: str,
    edge_type: str,
    *,
    n: int | None = None,
    stable: bool | None = None,
    regime: str | None = None,
    note: str = "",
) -> dict:
    return {
        "src": src,
        "dst": dst,
        "edge_type": edge_type,
        "n": n,
        "stable": stable,
        "display_only": True,
        "regime": regime,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

def _build_engine_nodes(spine_df: Any, gaps: list[str]) -> list[dict]:
    """One engine node per unique engine family in spine_index."""
    nodes: list[dict] = []
    if spine_df is None:
        gaps.append("engine nodes: spine_index.parquet absent — engine nodes empty")
        return nodes
    try:
        for eng in sorted(spine_df["engine"].unique().tolist()):
            n_rows = int((spine_df["engine"] == eng).sum())
            nodes.append(_node(
                nid=f"engine:{eng}",
                ntype="engine",
                label=eng,
                meta={"n_spine_rows": n_rows},
            ))
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence: engine nodes failed — %s", exc)
        gaps.append(f"engine nodes: {exc}")
    return nodes


def _build_sector_nodes(oracle_state: dict | None, gaps: list[str]) -> list[dict]:
    """Sector nodes from oracle_state complexes + 11 GICS sectors."""
    nodes: list[dict] = []
    # 8 oracle complexes
    if oracle_state is not None:
        for cx in (oracle_state.get("complexes") or []):
            cid = cx.get("id") or ""
            if not cid:
                continue
            nodes.append(_node(
                nid=f"complex:{cid}",
                ntype="sector",
                label=cx.get("name") or cid,
                meta={
                    "subtype": "oracle_complex",
                    "direction": cx.get("direction"),
                    "tier": cx.get("tier"),
                    "state": cx.get("state"),
                },
            ))
    else:
        gaps.append(
            "sector nodes (oracle complexes): oracle_state.json absent — "
            "8 oracle complex nodes omitted; oracle_state is gitignored/Mac-local"
        )

    # 11 GICS sectors (always)
    for sid, slabel in _GICS_11:
        nodes.append(_node(
            nid=f"sector:{sid}",
            ntype="sector",
            label=slabel,
            meta={"subtype": "gics_sector", "ticker": sid.upper()},
        ))
    return nodes


def _build_regime_nodes() -> list[dict]:
    """4 regime quad nodes + __all__."""
    quad_labels = {
        "Q1": "Goldilocks (Q1)",
        "Q2": "Reflation (Q2)",
        "Q3": "Stagflation (Q3)",
        "Q4": "Growth-scare/Deflation (Q4)",
    }
    nodes = [
        _node(nid="regime:__all__", ntype="regime", label="All Regimes",
              meta={"subtype": "marginal"})
    ]
    for qid, qlabel in quad_labels.items():
        nodes.append(_node(
            nid=f"regime:{qid}",
            ntype="regime",
            label=qlabel,
            meta={"subtype": "quad"},
        ))
    return nodes


def _build_thesis_nodes(theses_jsonl: Path, gaps: list[str]) -> list[dict]:
    """Active thesis nodes from data/radar/theses.jsonl."""
    nodes: list[dict] = []
    if not theses_jsonl.exists():
        gaps.append("thesis nodes: data/radar/theses.jsonl absent")
        return nodes
    try:
        seen: set[str] = set()
        for line in theses_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            tid = t.get("id") or t.get("thesis_id") or ""
            if not tid or tid in seen:
                continue
            seen.add(tid)
            # Only include active theses (no exhausted_at or exhausted_at is null)
            if t.get("exhausted_at"):
                continue
            nodes.append(_node(
                nid=f"thesis:{tid}",
                ntype="thesis",
                label=t.get("label_en") or t.get("title") or tid,
                meta={
                    "direction": t.get("direction"),
                    "onset_date": t.get("onset_date") or t.get("as_of"),
                },
            ))
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence: thesis nodes failed — %s", exc)
        gaps.append(f"thesis nodes: {exc}")
    return nodes


def _build_episode_nodes(
    oracle_state: dict | None, gaps: list[str], cap: int = 50
) -> list[dict]:
    """Episode nodes from oracle_state active_episodes, capped at 50 most recent.

    Summary only: node+direction.  No full episode data on the node.
    """
    nodes: list[dict] = []
    if oracle_state is None:
        return nodes  # gap already noted in sector nodes
    episodes: list[dict] = oracle_state.get("active_episodes") or []
    # Sort by onset_date descending to get most recent
    def _key(e: dict) -> str:
        return str(e.get("onset_date") or e.get("confirmed_date") or "")
    sorted_eps = sorted(episodes, key=_key, reverse=True)[:cap]
    for ep in sorted_eps:
        node_val = ep.get("node") or ""
        direction = ep.get("direction") or ""
        onset = ep.get("onset_date") or ep.get("confirmed_date") or ""
        eid = f"{node_val}:{direction}:{onset}"
        nodes.append(_node(
            nid=f"episode:{eid}",
            ntype="episode",
            label=f"{node_val} {direction}",
            meta={
                "node": node_val,
                "direction": direction,
                "onset_date": onset,
                "tier": ep.get("tier"),
                "two_sided": ep.get("two_sided"),
            },
        ))
    if len(episodes) > cap:
        gaps.append(
            f"episode nodes: {len(episodes)} active episodes, capped at {cap} "
            f"most recent (omitted {len(episodes)-cap})"
        )
    return nodes


# ---------------------------------------------------------------------------
# Edge builders
# ---------------------------------------------------------------------------

def _build_feeds_edges(registry: dict, gaps: list[str]) -> list[dict]:
    """Structural feeds edges from config/synapse.yml.

    Each artifact contributes edges: producer_module → artifact_path → consumer_module.
    These are structural wiring facts, not learned relationships.
    """
    edges: list[dict] = []
    artifacts = registry.get("artifacts") or {}
    for aid, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        producer = (entry.get("producer") or "").split(":")[0].strip()
        path = entry.get("path") or ""
        consumers = entry.get("consumers") or []
        if not producer or not path:
            continue
        # producer → artifact
        edges.append(_edge(
            src=f"module:{producer}",
            dst=f"artifact:{aid}",
            edge_type="feeds",
            note=f"structural: {producer} writes {path}",
        ))
        # artifact → consumer
        for consumer in consumers:
            if isinstance(consumer, str) and consumer:
                consumer_mod = consumer.split(":")[0].strip()
                edges.append(_edge(
                    src=f"artifact:{aid}",
                    dst=f"module:{consumer_mod}",
                    edge_type="feeds",
                    note=f"structural: {path} consumed by {consumer_mod}",
                ))
    return edges


def _build_stable_edges(
    graph_s: dict | None,
    graph_m: dict | None,
    gaps: list[str],
) -> list[dict]:
    """Oracle edge_stability where stable==True (READ-ONLY).

    graph_m: cap to complex-level pairs only (NOT 18,745 member pairs).
    graph_s: all 20 stable sector ETF pairs.
    """
    edges: list[dict] = []

    def _process_stab(graph: dict | None, tier_label: str, cap_complex: bool) -> None:
        if graph is None:
            return
        stab = graph.get("edge_stability") or []
        # If cap_complex, use complex_edges as the source; otherwise use edge_stability
        if cap_complex:
            stab = graph.get("complex_edges") or stab[:0]  # only complex-level
        count = 0
        for s in stab:
            if not isinstance(s, dict):
                continue
            if not s.get("stable"):
                continue
            node_a = str(s.get("node_a") or s.get("sector_a") or "")
            node_b = str(s.get("node_b") or s.get("sector_b") or "")
            if not node_a or not node_b:
                continue
            mean_corr = s.get("mean_corr")
            note_str = (
                f"oracle_stability tier={tier_label} mean_corr={mean_corr} "
                f"n_windows={s.get('n_windows')} sign_consistency={s.get('sign_consistency')}"
            )
            edges.append(_edge(
                src=f"sector:{node_a}",
                dst=f"sector:{node_b}",
                edge_type="stable",
                stable=True,
                note=note_str,
            ))
            count += 1
        if count:
            log.debug("confluence: %d stable edges from %s", count, tier_label)

    _process_stab(graph_s, "Tier-S", cap_complex=False)
    _process_stab(graph_m, "Tier-M", cap_complex=True)  # complex-level only

    if graph_s is None:
        gaps.append(
            "stable edges (Tier-S): data/oracle/graph_s.json absent — "
            "gitignored/Mac-local on this run"
        )
    if graph_m is None:
        gaps.append(
            "stable edges (Tier-M): data/oracle/graph_m.json absent — "
            "gitignored/Mac-local on this run"
        )
    return edges


def _build_leads_edges(
    graph_m: dict | None,
    gaps: list[str],
) -> list[dict]:
    """Oracle leadlag records from graph_m (includes honest nulls for n_is_leader=0)."""
    edges: list[dict] = []
    if graph_m is None:
        return edges  # gap already noted in stable edges

    leadlag = graph_m.get("leadlag") or []
    n_is_leader = graph_m.get("n_is_leader", 0)
    asof = graph_m.get("asof", "unknown")

    for ll in leadlag:
        if not isinstance(ll, dict):
            continue
        node_a = str(ll.get("node_a") or "")
        node_b = str(ll.get("node_b") or "")
        if not node_a or not node_b:
            continue
        is_leader = ll.get("is_leader")  # True/False/None
        best_lag = ll.get("best_lag")
        best_corr = ll.get("best_corr")
        edges.append(_edge(
            src=f"sector:{node_a}",
            dst=f"sector:{node_b}",
            edge_type="leads",
            note=(
                f"oracle_leadlag asof={asof} is_leader={is_leader} "
                f"best_lag={best_lag} best_corr={best_corr} "
                f"(n_is_leader={n_is_leader}: no complex dominantly leads another "
                f"at current panel depth — honest null)"
            ),
        ))

    if not leadlag:
        gaps.append(
            f"leads edges: graph_m.json has 0 leadlag records "
            f"(n_is_leader={n_is_leader} — honest null; panel depth insufficient)"
        )
    return edges


def _build_contradicts_edges(
    records: list[dict],
    gaps: list[str],
) -> list[dict]:
    """Contradiction edges from detect_contradictions() output."""
    edges: list[dict] = []
    for rec in records:
        pair_id = rec.get("pair_id") or "unknown"
        a = rec.get("a") or {}
        b = rec.get("b") or {}
        edges.append(_edge(
            src=a.get("artifact", "unknown"),
            dst=b.get("artifact", "unknown"),
            edge_type="contradicts",
            note=(
                f"pair_id={pair_id} kind={rec.get('kind')} "
                f"severity={rec.get('severity')} "
                f"a={a.get('reading','?')[:60]} b={b.get('reading','?')[:60]}"
            ),
        ))
    return edges


def _build_confirms_edges(
    spine_df: Any,
    gaps: list[str],
) -> list[dict]:
    """Co-firing lift edges from spine_index.

    Same (symbol, as_of, direction, horizon) across different engine values.
    MIN_N_COFIRING=10 floor: below floor → edge with n printed and lift=null.
    """
    edges: list[dict] = []
    if spine_df is None:
        gaps.append("confirms edges: spine_index.parquet absent")
        return edges

    try:
        import pandas as pd  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        graded = spine_df[
            spine_df["outcome_excess"].notna() &
            (spine_df["direction"] != 0)
        ].copy()

        if len(graded) == 0:
            gaps.append("confirms edges: no graded rows in spine_index")
            return edges

        engines = sorted(graded["engine"].unique().tolist())

        # For each engine pair, compute co-firing lift
        for i, e1 in enumerate(engines):
            for e2 in engines[i + 1:]:
                d1 = graded[graded["engine"] == e1][
                    ["symbol", "as_of", "direction", "horizon", "outcome_excess"]
                ].rename(columns={"outcome_excess": "oe1"})
                d2 = graded[graded["engine"] == e2][
                    ["symbol", "as_of", "direction", "horizon", "outcome_excess"]
                ].rename(columns={"outcome_excess": "oe2"})

                merged = d1.merge(d2, on=["symbol", "as_of", "direction", "horizon"])
                n_cofiring = len(merged)

                if n_cofiring == 0:
                    continue

                # Compute lift: mean(outcome_excess | both) - mean(outcome_excess | either)
                if n_cofiring >= _MIN_N_COFIRING:
                    # Mean excess when both fire (average of both engines' excess at same event)
                    mean_both = float(
                        (merged["oe1"] + merged["oe2"]).mean() / 2
                    )
                    # Mean excess in the individual sets
                    mean_e1 = float(graded[graded["engine"] == e1]["outcome_excess"].mean())
                    mean_e2 = float(graded[graded["engine"] == e2]["outcome_excess"].mean())
                    mean_either = (mean_e1 + mean_e2) / 2
                    lift = round(mean_both - mean_either, 5)
                    lift_val: float | None = lift
                    note_str = (
                        f"co-firing lift={lift:.4f} n={n_cofiring} "
                        f"(pre-gauntlet estimate; display-only)"
                    )
                else:
                    lift_val = None
                    note_str = (
                        f"n={n_cofiring} < MIN_N={_MIN_N_COFIRING} — lift=null "
                        f"(insufficient sample; display-only)"
                    )

                edges.append({
                    "src": f"engine:{e1}",
                    "dst": f"engine:{e2}",
                    "edge_type": "confirms",
                    "n": n_cofiring,
                    "lift": lift_val,
                    "stable": None,
                    "display_only": True,
                    "regime": None,
                    "note": note_str,
                })

    except Exception as exc:  # noqa: BLE001
        log.warning("confluence: confirms edges failed — %s", exc)
        gaps.append(f"confirms edges: {exc}")
    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _build_options_edges(
    repo: Path,
    gaps: list[str],
) -> list[dict]:
    """Options→NW W-B (RO-6): display-only aggregate edges between the options
    entry state and current US-board lanes.  Four adopted edges; the AMPLIFIES
    verb was REJECTED (unsanctioned) and the oracle_rotation edge is DEFERRED
    to Oracle-program review.  All counts are computed from the latest
    display-tier state table + latest board as_of; every edge display_only=True.
    """
    edges: list[dict] = []
    state_path = repo / "data" / "options_entry" / "state.parquet"
    ledger_path = repo / "data" / "us_board_ledger" / "retro_grades.parquet"

    state = None
    board = None
    try:
        import pandas as pd  # noqa: PLC0415
        if state_path.exists():
            state = pd.read_parquet(state_path)
        else:
            gaps.append("options_edges: state.parquet absent — options edges omitted")
        if ledger_path.exists():
            board = pd.read_parquet(ledger_path)
        else:
            gaps.append("options_edges: retro_grades.parquet absent — options edges omitted")
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"options_edges: read failed ({exc}) — options edges omitted")
        return edges
    if state is None or board is None or state.empty or board.empty:
        return edges

    try:
        latest = board["as_of"].max()
        cur = board[board["as_of"] == latest]
        buy_names = set(cur.loc[cur["lane"] == "buy", "ticker"].dropna())
        watch_names = set(cur.loc[cur["lane"] == "watch", "ticker"].dropna())
        st = state.set_index("ticker")

        def _count(names: set, cond) -> tuple[int, list[str]]:
            hits = []
            for t in names:
                if t not in st.index:
                    continue
                try:
                    if cond(st.loc[t]):
                        hits.append(t)
                except Exception:  # noqa: BLE001 — nulls
                    continue
            return len(hits), sorted(hits)[:8]

        # Edge 1 (adopted): bottom candidates CONTRADICTED_BY rising skew
        n1, ex1 = _count(buy_names, lambda r: r.get("skew_5d_chg") is not None
                         and float(r["skew_5d_chg"]) > 0)
        edges.append(_edge(
            src="options.skew_rising", dst="us_board.buy_lane",
            edge_type="contradicts", n=n1,
            note=(f"buy-lane names with 5d-rising OTM-put skew (as_of {latest}); "
                  f"e.g. {', '.join(ex1) or 'none'}. Display-only de-escalation context; "
                  "W-E1 prior: bullish skew-decel UNSUPPORTED on sector history."),
        ))
        # Edge 2 (adopted): bottom candidates CONFIRMED_BY skew deceleration
        thr = None
        try:
            skews = state["skew"].dropna().astype(float)
            thr = float(skews.quantile(2.0 / 3.0)) if len(skews) >= 30 else None
        except Exception:  # noqa: BLE001
            thr = None
        if thr is not None:
            n2, ex2 = _count(buy_names, lambda r: r.get("skew") is not None
                             and r.get("skew_5d_chg") is not None
                             and float(r["skew"]) >= thr and float(r["skew_5d_chg"]) < 0)
            edges.append(_edge(
                src="options.skew_decel", dst="us_board.buy_lane",
                edge_type="confirms", n=n2,
                note=(f"buy-lane names with top-tercile skew now falling (as_of {latest}); "
                      f"e.g. {', '.join(ex2) or 'none'}. Display-only; S-SKEW_DECEL gate "
                      "building_history, W-E1 sector-history prior is SKEPTICAL."),
            ))
        # Edge 3 (adopted): watch lane CONFIRMED_BY positive ivspread + call DOI
        n3, ex3 = _count(watch_names, lambda r: r.get("ivspread_rel") is not None
                         and r.get("net_doi") is not None
                         and float(r["ivspread_rel"]) > 0 and float(r["net_doi"]) > 0)
        edges.append(_edge(
            src="options.ivspread_positive_call_doi", dst="us_board.watch_lane",
            edge_type="confirms", n=n3,
            note=(f"watch-lane names with CW ivspread>0 and net ΔOI>0 (as_of {latest}); "
                  f"e.g. {', '.join(ex3) or 'none'}. Display-only; S-IVSPREAD-F gate "
                  "building_history; W-E1: CWIV Era3 5d IC survives on sector history."),
        ))
        # Edge 4 (adopted): extension signal CONFIRMED_BY skew_rising / call-wall pin.
        # No extension detector is wired on the board ledger yet — counts pending,
        # edge declared with n=None (honest; no fabricated membership).
        edges.append(_edge(
            src="options.skew_rising_or_call_wall_pin", dst="us_board.extended_names",
            edge_type="confirms", n=None,
            note=("extension detector not wired on the board ledger — counts pending; "
                  "display-only declaration per RO-6. Pin context available per-name via "
                  "options_entry state (pin_risk, wall distances)."),
        ))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"options_edges: build failed ({exc}) — partial/no options edges")

    return edges


def build_graph(
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict:
    """Build the confluence graph and return it as a dict.

    Parameters
    ----------
    root:
        Repo root override.
    now:
        UTC datetime for produced_at.  Defaults to now.

    Returns
    -------
    dict
        The confluence graph payload.  Always returns a dict (never raises).
        Partial reads produce a partial graph with gaps noted.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    repo = _repo_root(root)
    data_dir = repo / "data"
    site_dir = repo / "site"

    gaps: list[str] = []

    # ── Load spine_index ──────────────────────────────────────────────────────
    spine_df = None
    spine_path = data_dir / "neuralweb" / "spine_index.parquet"
    if spine_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            spine_df = pd.read_parquet(spine_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("confluence: spine_index read failed — %s", exc)
            gaps.append(f"spine_index.parquet: {exc}")
    else:
        gaps.append("spine_index.parquet: absent")

    # ── Load oracle_state ─────────────────────────────────────────────────────
    oracle_path = site_dir / "basketdata" / "oracle_state.json"
    oracle_state = _read_json(oracle_path)
    if oracle_state is None:
        gaps.append(
            "site/basketdata/oracle_state.json: absent — "
            "oracle complex + episode nodes omitted; gitignored/Mac-local"
        )

    # ── Load oracle graph files (READ-ONLY) ──────────────────────────────────
    graph_s: dict | None = None
    gs_path = data_dir / "oracle" / "graph_s.json"
    if gs_path.exists():
        graph_s = _read_json(gs_path)  # type: ignore[assignment]

    graph_m: dict | None = None
    gm_path = data_dir / "oracle" / "graph_m.json"
    if gm_path.exists():
        graph_m = _read_json(gm_path)  # type: ignore[assignment]

    # ── Load synapse registry for feeds edges ────────────────────────────────
    registry: dict = {}
    synapse_path = repo / "config" / "synapse.yml"
    if synapse_path.exists():
        try:
            import yaml  # noqa: PLC0415
            with open(synapse_path, encoding="utf-8") as fh:
                registry = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("confluence: synapse.yml read failed — %s", exc)
            gaps.append(f"config/synapse.yml: {exc}")
    else:
        gaps.append("config/synapse.yml: absent — feeds edges empty")

    # ── Build nodes ───────────────────────────────────────────────────────────
    nodes: list[dict] = []
    nodes.extend(_build_engine_nodes(spine_df, gaps))
    nodes.extend(_build_sector_nodes(oracle_state, gaps))
    nodes.extend(_build_regime_nodes())
    nodes.extend(_build_thesis_nodes(data_dir / "radar" / "theses.jsonl", gaps))
    nodes.extend(_build_episode_nodes(oracle_state, gaps))

    # ── Detect contradictions ─────────────────────────────────────────────────
    contra_records, contra_gaps = detect_contradictions(root=repo)
    gaps.extend(contra_gaps)

    # ── Build edges ───────────────────────────────────────────────────────────
    edges: list[dict] = []
    edges.extend(_build_feeds_edges(registry, gaps))
    edges.extend(_build_stable_edges(graph_s, graph_m, gaps))
    edges.extend(_build_leads_edges(graph_m, gaps))
    edges.extend(_build_contradicts_edges(contra_records, gaps))
    edges.extend(_build_confirms_edges(spine_df, gaps))
    edges.extend(_build_options_edges(repo, gaps))   # Options→NW W-B (RO-6)

    # ── Contradiction summary ─────────────────────────────────────────────────
    by_severity: dict[str, int] = {}
    for rec in contra_records:
        sev = rec.get("severity") or "unknown"
        by_severity[sev] = by_severity.get(sev, 0) + 1

    top_pair_ids = [rec.get("pair_id") for rec in contra_records[:5]]

    # ── Determine asof ───────────────────────────────────────────────────────
    asof: str = now.strftime("%Y-%m-%d")
    try:
        if oracle_state:
            asof = oracle_state.get("asof") or asof
    except Exception:  # noqa: BLE001
        pass

    # ── R-ORTH PR-4: independence block (additive, fail-open) ─────────────────
    independence = _read_independence_block(repo, gaps)

    # ── Assemble payload ──────────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "artifact_id": "confluence-graph",
        "asof": asof,
        "tier": "display",
        "is_context_only": True,
        "display_only": True,
        "hard_law": _HARD_LAW,
        "nodes": nodes,
        "edges": edges,
        "contradiction_summary": {
            "n": len(contra_records),
            "by_severity": by_severity,
            "top_pair_ids": top_pair_ids,
        },
        "contradiction_records": contra_records,
        "independence": independence,
        "gaps": gaps,
        "produced_by": "engine/neuralweb/confluence.py",
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return payload


def build_and_write(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_path: Path | str | None = None,
) -> dict:
    """Build the confluence graph, write to data/neuralweb/confluence_graph.json.

    Stamps the payload with the five envelope keys (schema_version, produced_by,
    produced_at, inputs_hash, tier) using stamp_if_changed so the artifact stays
    byte-identical when data is unchanged — prevents daily churn on unchanged graphs.

    Returns the stamped payload dict.  Never raises; write failures propagate as OSError.
    """
    repo = _repo_root(root)
    if out_path is None:
        dest = repo / "data" / "neuralweb" / "confluence_graph.json"
    else:
        dest = Path(out_path)

    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = build_graph(root=repo, now=now)

    # Read existing on-disk artifact for stamp_if_changed byte-identity path.
    prev_payload: dict | None = None
    if dest.exists():
        try:
            prev_payload = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev_payload = None

    # Stamp with envelope (sibling keys — NOT a nested wrapper).
    try:
        from engine.neuralweb.envelope import stamp_if_changed  # noqa: PLC0415
        payload = stamp_if_changed(
            payload,
            prev_payload,
            artifact_id="confluence-graph",
            now=now,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("confluence.build_and_write: envelope stamp failed: %s", e)

    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return payload
