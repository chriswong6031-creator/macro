"""Coverage census v0 (registration §8 / masterplan §8.2) — estimability first.

The census exists because of G-6: *estimability precedes design*. Before anything
downstream conditions on a cell, the census says how many episodes that cell has,
how many are censored, and — the column that actually decides whether a later
estimate means anything — **how many distinct calendar clusters** it spans. A cell
with 40 episodes that all live in March 2020 has an honest N of one market event,
not forty. `DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` died of coverage, not of
signal, and this artifact is the instrument that would have said so up front.

Cluster rule (frozen v0)
------------------------
Anchor dates are pooled **across names**, mapped to positions on the universe
session calendar, and split into single-linkage connected components wherever
consecutive anchors sit more than 126 sessions apart. Cluster ids are global, so
"how many distinct clusters" is comparable across cells. The P90-episode-duration
linkage refinement is a *named PR-3 candidate*, not something silently swapped in.

Scope
-----
Universe **minus the blind arm**. The blind arm is excluded entirely from any
published census until PR-3, and the excluded-name count is stated in the header —
the exclusion is disclosed, not invisible. Pilot rows carry full detail.

Fires-per-name-year and attribution-rate columns are PR-2/PR-3 additions. No expert
data exists in W1 by law, so those columns are absent rather than empty.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CLUSTER_LINKAGE_SESSIONS = 126
TOP_CLUSTERS = 3


def session_calendar(dates: Iterable[pd.Timestamp]) -> pd.DatetimeIndex:
    """The universe session calendar — the union of every observed session date."""
    idx = pd.DatetimeIndex(sorted({pd.Timestamp(d).normalize() for d in dates if pd.notna(d)}))
    return idx


def assign_calendar_clusters(
    anchors: Sequence[pd.Timestamp],
    calendar: pd.DatetimeIndex,
    linkage_sessions: int = CLUSTER_LINKAGE_SESSIONS,
) -> tuple[dict[pd.Timestamp, int], pd.DataFrame]:
    """Pooled single-linkage clustering of anchor dates on the session calendar.

    Returns ``(anchor_date -> cluster_id)`` and a per-cluster summary. Working in
    *session* space rather than calendar days is deliberate: a 126-day gap spanning
    a market holiday stretch is not the same distance as 126 trading sessions, and
    the episode durations this linkage is meant to approximate are counted in
    sessions everywhere else in the program.
    """
    uniq = sorted({pd.Timestamp(a).normalize() for a in anchors if pd.notna(a)})
    if not uniq or len(calendar) == 0:
        return {}, pd.DataFrame(columns=["cluster_id", "start", "end", "n_anchor_dates"])

    pos_of = {d: i for i, d in enumerate(calendar)}
    positions = []
    for d in uniq:
        if d in pos_of:
            positions.append((pos_of[d], d))
        else:  # a date off the union calendar cannot happen, but never guess one
            j = int(calendar.searchsorted(d))
            positions.append((min(j, len(calendar) - 1), d))
    positions.sort()

    mapping: dict[pd.Timestamp, int] = {}
    rows: list[dict[str, Any]] = []
    cid = 0
    start_date = positions[0][1]
    prev_date = positions[0][1]
    prev_pos = positions[0][0]
    count = 0
    for pos, d in positions:
        if pos - prev_pos > linkage_sessions:
            rows.append(
                {"cluster_id": cid, "start": start_date, "end": prev_date, "n_anchor_dates": count}
            )
            cid += 1
            start_date = d
            count = 0
        mapping[d] = cid
        prev_pos = pos
        prev_date = d
        count += 1
    rows.append({"cluster_id": cid, "start": start_date, "end": prev_date, "n_anchor_dates": count})
    return mapping, pd.DataFrame(rows)


def build_census(
    catalogs: pd.DataFrame,
    *,
    calendar: pd.DatetimeIndex,
    linkage_sessions: int = CLUSTER_LINKAGE_SESSIONS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[pd.Timestamp, int]]:
    """Per (ticker x episode_type x tier) coverage rows plus the cluster table.

    Censored episodes have no anchor by construction, so they count toward
    ``n_episodes`` and ``n_censored`` and contribute nothing to the cluster columns.
    The censored share is therefore printable beside every cluster count instead of
    being silently folded into it.
    """
    cols = [
        "symbol", "price_plane_id", "episode_type", "tier", "n_episodes", "n_censored",
        "censored_share", "first_anchor", "last_anchor", "n_calendar_clusters",
        "top3_cluster_share", "n_calendar_clusters_typetier",
        "top3_cluster_share_typetier", "median_depth_pct", "median_duration_sessions",
    ]
    if catalogs is None or catalogs.empty:
        return pd.DataFrame(columns=cols), pd.DataFrame(), {}

    anchors = catalogs.loc[catalogs["anchor_date"].notna(), "anchor_date"]
    mapping, cluster_table = assign_calendar_clusters(list(anchors), calendar, linkage_sessions)

    # Diagnostic clustering, NAMED not swapped. The frozen v0 rule pools anchors across
    # every name AND every episode type; at universe scale that pool covers essentially
    # every session, so single linkage returns one component and the column carries no
    # information. The object masterplan §8.1 actually describes ("post-2010 tier-1
    # episodes concentrate in a single-digit number of market clusters") is the anchor
    # pool of ONE (type, tier) stratum. Both are reported: the frozen one because it is
    # frozen, the stratified one because it is the one that can answer the question.
    typetier_maps: dict[tuple[str, int], dict[pd.Timestamp, int]] = {}
    typetier_tables: list[pd.DataFrame] = []
    for (etype, tier), g in catalogs.groupby(["episode_type", "tier"], dropna=False):
        a = g.loc[g["anchor_date"].notna(), "anchor_date"]
        m, t = assign_calendar_clusters(list(a), calendar, linkage_sessions)
        typetier_maps[(str(etype), int(tier))] = m
        if not t.empty:
            t = t.copy()
            t.insert(0, "episode_type", str(etype))
            t.insert(1, "tier", int(tier))
            typetier_tables.append(t)
    typetier_table = (
        pd.concat(typetier_tables, ignore_index=True) if typetier_tables else pd.DataFrame()
    )

    rows: list[dict[str, Any]] = []
    grouped = catalogs.groupby(["symbol", "price_plane_id", "episode_type", "tier"], dropna=False)
    for (sym, plane, etype, tier), g in grouped:
        anch = g.loc[g["anchor_date"].notna(), "anchor_date"]
        ids = [mapping.get(pd.Timestamp(a).normalize()) for a in anch]
        ids = [i for i in ids if i is not None]
        if ids:
            counts = pd.Series(ids).value_counts()
            top3 = float(counts.iloc[:TOP_CLUSTERS].sum()) / float(len(ids))
            n_clusters = int(counts.size)
        else:
            top3, n_clusters = float("nan"), 0
        tt_map = typetier_maps.get((str(etype), int(tier)), {})
        tt_ids = [tt_map.get(pd.Timestamp(a).normalize()) for a in anch]
        tt_ids = [i for i in tt_ids if i is not None]
        if tt_ids:
            tc = pd.Series(tt_ids).value_counts()
            tt_top3 = float(tc.iloc[:TOP_CLUSTERS].sum()) / float(len(tt_ids))
            tt_n = int(tc.size)
        else:
            tt_top3, tt_n = float("nan"), 0
        n = int(len(g))
        n_cens = int(g["censored"].sum())
        rows.append(
            {
                "symbol": sym,
                "price_plane_id": plane,
                "episode_type": etype,
                "tier": int(tier),
                "n_episodes": n,
                "n_censored": n_cens,
                "censored_share": float(n_cens) / float(n) if n else float("nan"),
                "first_anchor": pd.Timestamp(anch.min()) if len(anch) else pd.NaT,
                "last_anchor": pd.Timestamp(anch.max()) if len(anch) else pd.NaT,
                "n_calendar_clusters": n_clusters,
                "top3_cluster_share": top3,
                "n_calendar_clusters_typetier": tt_n,
                "top3_cluster_share_typetier": tt_top3,
                "median_depth_pct": float(pd.to_numeric(g["depth_pct"], errors="coerce").median()),
                "median_duration_sessions": float(
                    pd.to_numeric(g["duration_sessions"], errors="coerce").median()
                ),
            }
        )
    census = pd.DataFrame(rows, columns=cols).sort_values(
        ["episode_type", "tier", "symbol"]
    ).reset_index(drop=True)
    if not typetier_table.empty:
        cluster_table = cluster_table.assign(scope="frozen_v0_pooled_all_anchors")
        cluster_table = pd.concat(
            [cluster_table, typetier_table.assign(scope="diagnostic_by_type_and_tier")],
            ignore_index=True,
        )
    return census, cluster_table, mapping


def feature_availability_by_plane(
    coverage: pd.DataFrame, planes: pd.Series, feature_names: Sequence[str]
) -> pd.DataFrame:
    """Share of names on each plane for which each feature has a value.

    This is the cross-tab the plane law demands (masterplan §4 law vi): if a family
    is available on one plane and not another, the census shows it *before* any
    neighborhood is computed, so nobody discovers later that their clusters were
    data planes wearing a behavioral costume.
    """
    if coverage is None or coverage.empty:
        return pd.DataFrame(columns=["price_plane_id", "feature", "n_names", "available_share"])
    planes = planes.reindex(coverage.index)
    rows: list[dict[str, Any]] = []
    for plane, g in coverage.groupby(planes):
        for f in feature_names:
            if f not in g.columns:
                continue
            rows.append(
                {
                    "price_plane_id": str(plane),
                    "feature": f,
                    "n_names": int(len(g)),
                    "available_share": float(g[f].astype(bool).mean()),
                }
            )
    return pd.DataFrame(rows)


def render_markdown(
    census: pd.DataFrame,
    cluster_table: pd.DataFrame,
    availability: pd.DataFrame,
    *,
    header: dict[str, Any],
) -> str:
    """The operator-facing census document."""
    lines: list[str] = []
    lines.append("# Identity Atlas v0 — coverage census (W1 / PR-1)")
    lines.append("")
    lines.append(
        "Descriptive coverage only. Zero authority: nothing here ranks, sizes, gates, "
        "originates a signal, or escalates. No expert data exists in W1 by law "
        "(masterplan §16.9), so fires-per-name-year and attribution-rate columns are "
        "absent rather than empty — they are PR-2/PR-3 additions."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- **asof**: {header.get('asof')}")
    lines.append(f"- **Universe (evaluated)**: {header.get('universe_n')} names")
    lines.append(
        f"- **Excluded as blind evaluation arm**: {header.get('blind_excluded_n')} names — "
        "the blind arm is excluded entirely from this census until PR-3; its members "
        "appear nowhere below, not even as counts by stratum."
    )
    lines.append(
        f"- **Excluded by ticker-identity hygiene**: {header.get('hygiene_excluded_n')} names "
        f"({header.get('hygiene_excluded_list')})"
    )
    lines.append(f"- **Census population**: {header.get('census_n')} names")
    lines.append(
        "- **Survivor-only cohort**: the allowed price planes retain no ceased tapes; no "
        "dead name could be included (registration §2). Every cohort-level statement "
        "below is therefore a statement about survivors, and cannot name who is missing."
    )
    lines.append(f"- **Episodes catalogued**: {header.get('n_episodes')}")
    lines.append(
        f"- **Censored share**: {header.get('censored_share')} — censored episodes are "
        "kept, never dropped (a decline that never prints a durable low is exactly the "
        "case that would otherwise turn recall into a survivorship filter)."
    )
    lines.append(f"- **Constants**: {header.get('constants_hash')}")
    lines.append(f"- **fingerprint_spec_hash**: {header.get('fingerprint_spec_hash')}")
    lines.append("")
    lines.append(
        "Cluster rule (frozen v0): anchor dates pooled across names, single-linkage "
        f"components at a {CLUSTER_LINKAGE_SESSIONS}-session gap, global cluster ids. "
        "The P90-episode-duration linkage refinement is a named PR-3 candidate."
    )
    lines.append("")

    lines.append("## Episodes by type and tier")
    lines.append("")
    if census.empty:
        lines.append("_no episodes catalogued_")
    else:
        agg = census.groupby(["episode_type", "tier"]).agg(
            n_names=("symbol", "nunique"),
            n_episodes=("n_episodes", "sum"),
            n_censored=("n_censored", "sum"),
        ).reset_index()
        lines.append("| episode_type | tier | names | episodes | censored | censored share |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for r in agg.itertuples(index=False):
            share = (r.n_censored / r.n_episodes) if r.n_episodes else float("nan")
            lines.append(
                f"| {r.episode_type} | {r.tier} | {r.n_names} | {r.n_episodes} | "
                f"{r.n_censored} | {share:.3f} |"
            )
    lines.append("")

    lines.append("## Calendar clusters — frozen v0 rule (all anchors pooled)")
    lines.append("")
    frozen = (
        cluster_table[cluster_table.get("scope", "frozen_v0_pooled_all_anchors")
                      == "frozen_v0_pooled_all_anchors"]
        if not cluster_table.empty else cluster_table
    )
    if frozen.empty:
        lines.append("_no anchored episodes_")
    else:
        lines.append(f"Total distinct clusters: **{len(frozen)}**")
        lines.append("")
        if len(frozen) <= 1:
            lines.append(
                "**This column carries no information at universe scale, and that is a "
                "result about the rule, not about the market.** The frozen v0 rule pools "
                "anchor dates across every name AND every episode type; with thousands of "
                "names catalogued, the pooled anchors cover essentially every session, so "
                "no 126-session gap ever occurs and single linkage returns one component. "
                "The rule is applied as frozen and reported as frozen. The stratified view "
                "below is a NAMED diagnostic, not a substitution — swapping the rule "
                "silently is precisely what the registration forbids."
            )
            lines.append("")
        lines.append("| cluster_id | start | end | anchor dates |")
        lines.append("|---:|---|---|---:|")
        for r in frozen.itertuples(index=False):
            lines.append(
                f"| {r.cluster_id} | {pd.Timestamp(r.start).date()} | "
                f"{pd.Timestamp(r.end).date()} | {r.n_anchor_dates} |"
            )
    lines.append("")

    lines.append("## Calendar clusters — diagnostic, stratified by (type, tier)")
    lines.append("")
    lines.append(
        "Anchors pooled within one (episode_type, tier) stratum, same 126-session single "
        "linkage. This is the object masterplan §8.1 describes when it says post-2010 "
        "tier-1 episodes concentrate in a single-digit number of market clusters, and it "
        "is the count to read when judging whether a cell's episodes are one market event "
        "wearing many tickers."
    )
    lines.append("")
    diag = (
        cluster_table[cluster_table.get("scope") == "diagnostic_by_type_and_tier"]
        if "scope" in getattr(cluster_table, "columns", []) else pd.DataFrame()
    )
    if diag.empty:
        lines.append("_not computed_")
    else:
        lines.append("| episode_type | tier | clusters | first | last |")
        lines.append("|---|---:|---:|---|---|")
        for (etype, tier), g in diag.groupby(["episode_type", "tier"]):
            lines.append(
                f"| {etype} | {tier} | {len(g)} | {pd.Timestamp(g['start'].min()).date()} | "
                f"{pd.Timestamp(g['end'].max()).date()} |"
            )
    lines.append("")

    lines.append("## Distinct-cluster distribution per cell")
    lines.append("")
    if not census.empty:
        lines.append(
            "| episode_type | tier | cells | median clusters/cell (diagnostic) | "
            "cells with <=1 cluster |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for (etype, tier), g in census.groupby(["episode_type", "tier"]):
            single = int((g["n_calendar_clusters_typetier"] <= 1).sum())
            lines.append(
                f"| {etype} | {tier} | {len(g)} | "
                f"{float(g['n_calendar_clusters_typetier'].median()):.1f} | {single} |"
            )
        lines.append("")
        lines.append(
            "A cell whose episodes sit in one cluster has an honest N of one market "
            "event regardless of its raw episode count."
        )
    lines.append("")

    lines.append("## Feature availability by price plane")
    lines.append("")
    if availability.empty:
        lines.append("_no coverage data_")
    else:
        piv = availability.pivot_table(
            index="feature", columns="price_plane_id", values="available_share"
        )
        planes = list(piv.columns)
        lines.append("| feature | " + " | ".join(planes) + " |")
        lines.append("|---|" + "---:|" * len(planes))
        for feat, row in piv.iterrows():
            cells = " | ".join(
                "n/a" if pd.isna(row[p]) else f"{row[p]:.3f}" for p in planes
            )
            lines.append(f"| {feat} | {cells} |")
        lines.append("")
        lines.append(
            "The gap family sits in the diagnostic block precisely because its "
            "availability is plane-conditional: the open-less curated plane cannot "
            "carry it, so under the plane-availability law it is excluded from the "
            "metric block universe-wide rather than masked per name."
        )
    lines.append("")
    return "\n".join(lines) + "\n"
