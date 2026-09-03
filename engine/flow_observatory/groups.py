"""engine.flow_observatory.groups — official/curated lenses, coverage, concentration
and contribution (Flow Observatory V2 W4, ``research/flow_observatory/W4_SPEC.md``).

Pure assembly on top of the SAME kinetics primitives ``engine.flow_velocity`` already
exposes (``kinetics``/``rate_read``/``spark``/``series_tail``/``WK``) — "same math as
the theme rollup ... no second velocity engine" (spec §2A). This module owns three
things neither the theme rollup nor ``engine.flow_observatory.contract`` owned before
W4:

  coverage      n_members / n_covered / coverage_pct per group, and the floor below
                which a group renders ``insufficient coverage`` instead of a partial
                statistic (spec §3 — ``COVERAGE_FLOOR_PCT``, calibrated below).
  overlap       curated themes may share members; ``overlap_count`` (theme-level) and
                the per-member "in N themes" chip data (spec §3).
  concentration top-1/top-3 gross-flow share, the without-top1 sensitivity direction,
                and the per-member contributions that reconcile to the group's own
                relative value within 1e-6 (spec §4).
  aggregate_lens
                the OFFICIAL (Shenwan L1, non-overlapping) sector lens itself — built
                from the SW constituent membership store
                (``data/china_sectors/membership.parquet``, ``collectors.china_sectors
                .collect_sw_membership``) joined onto the SAME per-ticker kinetics map
                (``kmap``) the theme rollup already computed, so a name's velocity is
                identical wherever it appears (matches the existing "the datasets
                breathe together" invariant — engine.flow_velocity's own docstring).

COVERAGE_FLOOR_PCT calibration receipt (spec §3, real data, 2026-09-03): all 22 curated
baskets_china themes sit at 100% coverage today (every basket member is present AND
scored in the flow kinetics map) — any floor at or below 100% keeps every one of them
eligible. The SW L1 official-sector distribution is the real "degenerate tail" the
floor exists to catch: measured against the same kmap (31 groups), coverage ranges
5.1%-90.5% with a natural break at 57.6% -> 62.1% (only Banks 90.5%, Non-bank
Financials 77.2%, and Nonferrous Metals 62.1% clear a 60% floor; the other 28 groups
legitimately have too little of their true membership inside the ~1,800-name Tushare
moneyflow panel to publish a non-survivor-biased read). The starting hypothesis (60%)
sits inside that natural gap and is kept as-is — moving it lower would let in several
sectors where 4 in 5 constituents are silently absent from the read, which is exactly
the "survivor-biased read" gate #0.2 exists to forbid.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── calibrated constants (spec §3/§4 — see module docstring for the receipt) ──────
COVERAGE_FLOOR_PCT = 60.0
CONCENTRATION_CHIP_PCT = 40.0          # spec §4: chip fires when top1_share > 40%
MIN_COLS_FOR_KINETICS = 3              # same computability floor the theme rollup used

INSUFFICIENT_COVERAGE_EN = "insufficient coverage"
INSUFFICIENT_COVERAGE_ZH = "覆盖不足"
CONCENTRATED_CHIP_EN = "concentrated"
CONCENTRATED_CHIP_ZH = "集中度高"

_DIR_WORDS: dict[str, tuple[str, str]] = {
    "same": ("same direction", "方向不变"),
    "flip": ("flips", "方向反转"),
    "unknown": ("unclear", "不明确"),
}


# ── coverage (spec §3) ─────────────────────────────────────────────────────────────
def coverage_stats(n_members: int, n_covered: int) -> dict[str, Any]:
    """``{n_members, n_covered, coverage_pct}`` — every group statistic's own
    denominator (§0.2 gate). ``coverage_pct`` is ``None`` only when the group has no
    known membership at all (n_members == 0), never silently treated as 0%."""
    pct = round(100.0 * n_covered / n_members, 1) if n_members else None
    return {"n_members": n_members, "n_covered": n_covered, "coverage_pct": pct}


def excluded_members(members: list[str], wide_columns, kmap: dict[str, Any],
                      name_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Members NOT present+scored in the kinetics map, with a reason — the drilldown's
    "excluded/missing" list (spec §3/§6 test 7): ``unscored`` when the ticker has flow
    data but too short/thin a history to score, ``missing`` when it has no flow data at
    all. Never silent — every excluded name is named."""
    name_map = name_map or {}
    wide_set = set(wide_columns)
    out = []
    for t in members:
        if t in kmap:
            continue
        reason = "unscored" if t in wide_set else "missing"
        out.append({"ticker": t, "name": name_map.get(t), "reason": reason})
    return out


# ── overlap (spec §3) ────────────────────────────────────────────────────────────────
def compute_overlap_counts(membership_by_group: dict[str, list[str]]) -> dict[str, int]:
    """ticker -> count of OTHER groups (excluding the ticker's own group) it also
    belongs to. 0 = unique to one group; used for both the theme-level
    ``overlap_count`` and the member "in N themes" chip."""
    c: Counter = Counter()
    for members in membership_by_group.values():
        for t in set(members):
            c[t] += 1
    return {t: (n - 1) for t, n in c.items()}


def theme_overlap_count(members: list[str], overlap_by_ticker: dict[str, int]) -> int:
    """Count of THIS group's members that are shared with >=1 OTHER group."""
    return sum(1 for t in members if overlap_by_ticker.get(t, 0) >= 1)


# ── concentration + contribution (spec §4) ─────────────────────────────────────────
def member_contributions(covered: list[str], kmap: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-member signed demeaned-rate contribution = ``member_rel / n`` where ``n`` is
    the count of members that actually carry a scored ``rate_rel`` (spec §4). Dividing
    by exactly that count — not a separately-measured "n_covered" — is what makes the
    reconciliation law (Σcontributions == the group's own rel value) hold by
    CONSTRUCTION, not by coincidence: the group's rel value here IS defined as the mean
    of these same per-member values (see :func:`concentration_from_contributions`)."""
    vals = [(t, (kmap.get(t) or {}).get("rate_rel")) for t in covered]
    vals = [(t, v) for t, v in vals if v is not None]
    n = len(vals)
    if not n:
        return []
    return [{"ticker": t, "name": (kmap.get(t) or {}).get("name"), "rate_rel": v,
             "contribution": v / n} for t, v in vals]


def concentration_from_contributions(contrib: list[dict[str, Any]]) -> dict[str, Any]:
    """top1_share/top3_share (of GROSS |contribution|), without_top1_direction
    (same/flip/unknown), and the ranked top-3 positive/negative contributor lists
    (spec §4). ``group_rel`` = Σcontributions, i.e. the mean member rate_rel — the
    reconciliation law's target, exact to float precision by construction."""
    if not contrib:
        return {"top1_share": None, "top3_share": None, "without_top1_direction": "unknown",
                "top3_pos": [], "top3_neg": [], "gross": None, "group_rel": None, "top1": None}
    ranked = sorted(contrib, key=lambda c: -abs(c["contribution"]))
    gross = sum(abs(c["contribution"]) for c in ranked)
    group_rel = sum(c["contribution"] for c in ranked)
    top1 = ranked[0]
    top1_share = round(100.0 * abs(top1["contribution"]) / gross, 1) if gross else None
    top3_share = round(100.0 * sum(abs(c["contribution"]) for c in ranked[:3]) / gross, 1) if gross else None

    n = len(contrib)
    without_dir = "unknown"
    if n >= 2:
        without_top1_rel = (n * (group_rel - top1["contribution"])) / (n - 1)
        s_full = (group_rel > 0) - (group_rel < 0)
        s_wo = (without_top1_rel > 0) - (without_top1_rel < 0)
        if s_full != 0 and s_wo != 0:
            without_dir = "same" if s_full == s_wo else "flip"

    pos_ranked = sorted((c for c in contrib if c["contribution"] > 0), key=lambda c: -c["contribution"])
    neg_ranked = sorted((c for c in contrib if c["contribution"] < 0), key=lambda c: c["contribution"])
    return {
        "top1_share": top1_share, "top3_share": top3_share,
        "without_top1_direction": without_dir,
        "top3_pos": pos_ranked[:3], "top3_neg": neg_ranked[:3],
        "top1": top1, "gross": round(gross, 4) if gross else None,
        "group_rel": round(group_rel, 4),
    }


def drilldown_line(conc: dict[str, Any] | None) -> tuple[str, str] | None:
    """The pinned drilldown line (spec §4): EN "top name = {p}% of gross flow ·
    without it: {same direction/flips}" / ZH "最大贡献个股占总流量{p}% ·
    剔除后：{方向不变/方向反转}". ``None`` when there is nothing to show."""
    if not conc or conc.get("top1_share") is None:
        return None
    p = conc["top1_share"]
    dir_en, dir_zh = _DIR_WORDS.get(conc.get("without_top1_direction") or "unknown", _DIR_WORDS["unknown"])
    en = f"top name = {p:.0f}% of gross flow · without it: {dir_en}"
    zh = f"最大贡献个股占总流量{p:.0f}% · 剔除后：{dir_zh}"
    return en, zh


# ── official-sector membership resolution (spec §2A) ───────────────────────────────
def resolve_active_membership(membership_df: pd.DataFrame | None,
                               as_of: str | None = None) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """The ACTIVE (l1_code -> [tickers]) view of the interval store at ``as_of``
    (default: the OPEN/current rows, ``end_date`` null). A ticker active in more than
    one ``l1_code`` at once is a source contradiction (a name belongs to exactly one
    Shenwan L1 industry) — spec §2A/§6 test 1: it is EXCLUDED from every such l1_code
    (never assigned, never silently double-counted) and returned in ``excluded`` with
    reason ``duplicate_membership``."""
    if membership_df is None or membership_df.empty:
        return {}, []
    df = membership_df.copy()
    if as_of is None:
        active = df[df["end_date"].isna()]
    else:
        start_ok = df["start_date"].fillna("") <= as_of
        end_ok = df["end_date"].isna() | (df["end_date"] > as_of)
        active = df[start_ok & end_ok]
    if active.empty:
        return {}, []
    counts = active.groupby("ticker")["l1_code"].nunique()
    dupe_tickers = set(counts[counts > 1].index)
    by_code: dict[str, list[str]] = {}
    for _, r in active.iterrows():
        t, code = r["ticker"], r["l1_code"]
        if t in dupe_tickers:
            continue
        by_code.setdefault(code, []).append(t)
    excluded = [{"ticker": t, "reason": "duplicate_membership"} for t in sorted(dupe_tickers)]
    return by_code, excluded


# ── official-sector lens assembly (spec §2A) ────────────────────────────────────────
def aggregate_lens(wide: pd.DataFrame | None, kmap: dict[str, Any],
                    membership_df: pd.DataFrame | None, *,
                    l1_names: dict[str, tuple[str, str]] | None = None,
                    seed_date: str | None = None, as_of: str | None = None,
                    cfg: dict | None = None,
                    coverage_floor: float = COVERAGE_FLOOR_PCT) -> dict[str, Any]:
    """The official (Shenwan L1) sector lens: same per-group equal-weight-mean
    kinetics as the curated-theme rollup, reusing ``engine.flow_velocity``'s shared
    primitives, over CURRENT constituent membership only (spec §2A — never a
    historical replay before ``seed_date``).

    Returns ``{"available": False, "reason": ...}`` when there is no membership data
    at all, or when ``as_of`` predates the store's own accrual origin (spec §2A "No
    historical replay ... before real accrued membership covers the window", tested
    §6 test 3). Otherwise ``{"available": True, "rows": [...], "membership_as_of":
    ..., "seed_date": ..., "n": ...}`` — each row carries the SAME abs-computable
    fields the theme rollup emits (vel/accel/rate_*/state/spark/members) plus
    ``group_kind: "official_sector"``, ``overlap_allowed: False``,
    ``membership_as_of``, coverage, and concentration. A row whose coverage sits
    below ``coverage_floor`` (or that has too few members present to compute at all)
    still renders — never dropped — with every numeric field null and
    ``coverage_state: "insufficient_coverage"`` (spec §3/§0.2: never a
    survivor-biased read).
    """
    from engine.flow_velocity import WK as _wk_cfg
    from engine.flow_velocity import kinetics as _kin
    from engine.flow_velocity import rate_read as _rr
    from engine.flow_velocity import series_tail as _st
    from engine.flow_velocity import spark as _sp

    cfg = cfg or _wk_cfg
    if membership_df is None or membership_df.empty:
        return {"available": False, "reason": "no_membership_data"}

    if seed_date is None:
        # `collected_at` — the date OUR pipeline first observed a row — not
        # `start_date` (SW's own reported inclusion date, which predates this
        # collector by years for most names). Using `start_date` here would let a
        # request for pre-accrual official-sector history through even though this
        # store has zero real observations before its own first collection run.
        if "collected_at" in membership_df.columns:
            stamps = pd.to_datetime(membership_df["collected_at"], errors="coerce").dropna()
        else:
            stamps = pd.to_datetime(membership_df["start_date"], errors="coerce").dropna()
        seed_date = str(stamps.min().date()) if len(stamps) else None
    if as_of is not None and seed_date is not None and as_of < seed_date:
        return {"available": False, "reason": "before_seed_date",
                "seed_date": seed_date, "requested": as_of}

    by_code, dup_excluded = resolve_active_membership(membership_df, as_of=as_of)
    l1_names = l1_names or {}
    wide_cols = set(wide.columns) if wide is not None else set()
    dup_by_ticker: dict[str, list[dict]] = {}
    for e in dup_excluded:
        dup_by_ticker.setdefault(e["ticker"], []).append(e)

    rows: list[dict[str, Any]] = []
    for code in sorted(by_code):
        members = sorted(set(by_code[code]))
        n_members = len(members)
        if n_members == 0:
            continue
        cols = [t for t in members if t in wide_cols]
        covered = [t for t in cols if t in kmap]
        cov = coverage_stats(n_members, len(covered))
        excluded = excluded_members(members, wide_cols, kmap)
        for t in members:
            excluded.extend(dup_by_ticker.get(t, []))

        # l1_names[code] = (name_en, name_zh) — a bare (code, code) fallback would
        # silently ship an unlabeled ID rather than a name, in EITHER language.
        name_en, name_zh = l1_names.get(code, (code, code))
        row: dict[str, Any] = {
            "id": code, "name": name_en, "name_zh": name_zh,
            "group_kind": "official_sector", "overlap_allowed": False,
            "membership_as_of": as_of or "current",
            "n_members": cov["n_members"], "n_covered": cov["n_covered"],
            "coverage_pct": cov["coverage_pct"], "excluded": excluded,
        }

        sufficient = (cov["coverage_pct"] is not None and cov["coverage_pct"] >= coverage_floor
                      and len(cols) >= MIN_COLS_FOR_KINETICS)
        kin = None
        if sufficient:
            sect_flow = wide[cols].mean(axis=1)
            kin = _kin(sect_flow, cfg)
            if not kin or kin.get("vel_primary") is None:
                sufficient = False
        if sufficient and kin:
            rr = _rr(sect_flow, cfg)
            contrib = member_contributions(covered, kmap)
            conc = concentration_from_contributions(contrib)
            row.update(vel=kin["vel_primary"], accel=kin["accel"], **rr,
                       state=kin["state"], state_zh=kin["state_zh"],
                       spark=_sp(_st(sect_flow.cumsum(), 130)),
                       concentration=conc, coverage_state="ok",
                       members=sorted((kmap[t] for t in covered),
                                      key=lambda r: -abs(r.get("vel") or 0))[:8])
        else:
            row.update(vel=None, accel=None, rate_now=None, rate_4wk=None, rate_norm=None,
                       rate_rel=None, state=INSUFFICIENT_COVERAGE_EN, state_zh=INSUFFICIENT_COVERAGE_ZH,
                       spark=None, concentration=None, members=[],
                       coverage_state="insufficient_coverage")
        rows.append(row)

    return {"available": True, "rows": rows, "membership_as_of": as_of or "current",
            "seed_date": seed_date, "n": len(rows)}
