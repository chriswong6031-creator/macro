"""Shared merge for the US breadth wide close caches — freshest column wins.

WHY THIS EXISTS (2026-08-06, generalising
research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md §4 chip (3)).

``data/{breadth,smallcap_breadth,midcap_breadth,russell_breadth}/_closes_cache.parquet``
are UNION-FOREVER archives by design (survivorship-honest; #4643 R4 — never prune).
A name that LEAVES an index keeps its column in that tier's cache, frozen on its exit
date, while the tier it JOINED carries a live column for the same ticker.

Every consumer merged the tiers with the same idiom — concat in a fixed tier order,
then ``~columns.duplicated()`` / ``setdefault`` — which keeps the FIRST occurrence.
For an index migrant that is the DEAD column, and the LIVE one, sitting in the very
same concat, is discarded. Measured on the 2026-07-31 caches:

  * order (breadth, smallcap, midcap)  -> 6 dead-picked: CAG CPB POOL SANM SMTC VIAV
  * order (breadth, midcap, smallcap)  -> 7 dead-picked: BLKB CAG CNXC COTY CPB GT POOL

This is NOT the generic staleness case (a genuinely dead feed, which is what #4643's
scan demotion handles). It is a merge defect: the panel already contains the right
answer and the reader throws it away. Downstream receipts at that vintage —
``engine.equity_factors._closes("broad")`` feeds site/factordata/factors.json,
site/factordata/alpha.json AND scripts/grade_us_board.py's price panel, so VIAV
ranked sector-leader #9/221 on a column that had stopped 23 days earlier while its
live column stood 9.2% lower.

CONTRACT — the naive repair (take the freshest column whole) trades one defect for
another: a migrant's NEW tier column starts on the migration date, so it carries only
26-51 observations against the dead column's 300-770, and every window factor that
needs history (vol / beta at min_price_history_d=150) goes NaN. Measured: all 9
rescued names would have lost their vol and beta legs, and VIAV's composite with them.

So the join is MEASUREMENT-GATED rather than assumed. Two tiers can carry the same
ticker on different adjustment bases (measured: CPB's two columns differ by a constant
1.69%, a dividend-adjustment gap), and stitching across that would manufacture exactly
the #2120 intra-series seam the adjudication forbids (R4/§4). But agreement is a thing
we can TEST, not guess: where the two columns are bit-identical on their overlapping
sessions they are the same series observed by two collector lanes, and combining them
is a gap-fill, not a basis mix. At the 2026-07-31 vintage 8 of the 9 overlaps are
identical to 0.000e+00 and stitch; CPB alone fails the test and falls back to the whole
live column, seam-free, accepting the shorter history rather than inventing a rebase.

Column COVERAGE is invariant: the merged panel carries the same ticker set as the
keep-first merge it replaces, so no admission lane loses its price source
(tests/test_us_board_ledger_continuity.py Section 1).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Agreement bar for stitching a migrant's two tier columns into one series. Deliberately
# at float-noise level, NOT a tolerance band: anything a real adjustment difference would
# produce (CPB's 1.69%) must fail, and only lanes writing the identical series pass.
_STITCH_MAX_REL_DIFF = 1e-6
# Minimum overlapping sessions before the agreement test carries any evidence — one or
# two coincidentally-equal closes are not proof that two series share a basis.
_STITCH_MIN_OVERLAP = 5

# The canonical US tiers, in the historical naming-priority order. Callers pass
# their own order; a ticker's NAME/sector metadata still follows tier priority,
# only the PRICE column now follows freshness.
US_TIERS = ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")


def _last_valid(panel: pd.DataFrame) -> pd.Series:
    """ticker -> last non-NaN index label (NaT when the column is empty)."""
    if panel.empty:
        return pd.Series(dtype="datetime64[ns]")
    return panel.apply(lambda s: s.last_valid_index())


def _stitch_ok(dead: pd.Series, live: pd.Series) -> tuple[bool, int, float]:
    """Are these two columns the SAME series seen by two collector lanes?

    True only when they overlap on at least ``_STITCH_MIN_OVERLAP`` sessions AND agree
    to within float noise there. That is the whole seam argument: columns equal on every
    shared session cannot introduce a discontinuity when combined, whereas a genuine
    adjustment-basis difference (CPB's constant 1.69%) fails and is never spliced.

    Returns (ok, n_overlap, max_rel_diff)."""
    both = pd.concat([dead.rename("d"), live.rename("l")], axis=1).dropna()
    if len(both) < _STITCH_MIN_OVERLAP:
        return False, len(both), float("nan")
    rel = ((both["d"] / both["l"]) - 1.0).abs().max()
    if not pd.notna(rel):
        return False, len(both), float("nan")
    return bool(rel <= _STITCH_MAX_REL_DIFF), len(both), float(rel)


def choose_column(caches: dict, ticker: str, order) -> tuple[pd.Series | None, str | None]:
    """Freshest column for ONE ticker across already-loaded per-tier frames, with the
    same measurement-gated history stitch as :func:`merge_close_caches`.

    For callers that keep a {tier: DataFrame} dict rather than a merged panel
    (scripts/build_chart_data.py). ``order`` breaks freshness ties, preserving each
    caller's existing tier priority for every non-migrant ticker.

    Returns ``(series, source_tier)``, or ``(None, None)`` when no tier carries the
    ticker with any data.
    """
    have = [(g, caches[g][ticker]) for g in order
            if g in caches and caches[g] is not None and ticker in caches[g].columns]
    have = [(g, s) for g, s in have if s.notna().any()]
    if not have:
        return None, None
    best_g, best_s = have[0]
    for g, s in have[1:]:
        if s.last_valid_index() > best_s.last_valid_index():
            best_g, best_s = g, s
    for g, s in have:
        if g == best_g or s.notna().sum() <= best_s.notna().sum():
            continue
        ok, _n, _rel = _stitch_ok(s, best_s)
        if ok:
            best_s = best_s.combine_first(s)
            break
    return best_s, best_g


def merge_close_caches(
    groups,
    kind: str = "_closes_cache",
    data_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Merge the per-tier wide caches into one panel, FRESHEST column per ticker.

    ``groups`` is the tier order (used only to break freshness TIES, so behaviour is
    unchanged for every ticker that is not an index migrant). ``kind`` selects the
    cache file stem (``_closes_cache`` / ``_volume_cache`` / ``_high_cache`` / …).

    A missing or unreadable tier is skipped with a log line — never fatal, so one
    corrupt restored cache cannot blank a page (CSP-R1).

    Returns ``(panel, meta)``. ``meta`` carries:
      ``tip``      -- panel-wide max index (pd.Timestamp) or None,
      ``behind``   -- {ticker: calendar days its chosen column lags ``tip``},
      ``source``   -- {ticker: tier the chosen column came from},
      ``rescued``  -- {ticker: (dead_tier, dead_days, live_tier)} for every ticker
                      where freshness overrode tier order — i.e. the columns this
                      merge saved from the keep-first defect. Never silent: the
                      caller discloses the count.
      ``stitched`` -- {ticker: (donor_tier, n_overlap, max_rel_diff)} for tickers whose
                      pre-migration history was restored from another tier AFTER that
                      tier's column was proven bit-identical on the overlap. A ticker
                      absent here kept a single intact column.
    """
    if data_dir is None:
        from lib import config
        data_dir = config.data_dir()

    frames: dict[str, pd.DataFrame] = {}
    for grp in groups:
        p = Path(data_dir) / grp / f"{kind}.parquet"
        if not p.exists():
            continue
        try:
            d = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001 — a corrupt cache must never kill a page
            log.warning("closes_panel: %s/%s unreadable (%s) — tier skipped", grp, kind, e)
            continue
        if d.empty:
            continue
        d = d.loc[:, ~d.columns.duplicated()]
        d.index = pd.to_datetime(d.index)
        frames[grp] = d.sort_index()

    if not frames:
        return pd.DataFrame(), {"tip": None, "behind": {}, "source": {}, "rescued": {}}

    lasts = {g: _last_valid(d) for g, d in frames.items()}
    tip = max(d.index.max() for d in frames.values())
    index = pd.to_datetime(sorted({i for d in frames.values() for i in d.index}))

    # Choose a source tier per ticker: freshest last-valid bar wins; ties (including
    # two all-empty columns) fall back to the caller's tier order, so this is a strict
    # refinement of the previous keep-first behaviour.
    chosen: dict[str, str] = {}
    for grp in groups:
        d = frames.get(grp)
        if d is None:
            continue
        for tk in d.columns:
            cur = chosen.get(tk)
            if cur is None:
                chosen[tk] = grp
                continue
            a, b = lasts[cur].get(tk), lasts[grp].get(tk)
            # NaT sorts last: a column with any data beats an all-empty one.
            a_ok, b_ok = pd.notna(a), pd.notna(b)
            if (b_ok and not a_ok) or (a_ok and b_ok and b > a):
                chosen[tk] = grp

    rescued: dict[str, tuple] = {}
    stitched: dict[str, tuple] = {}
    cols: dict[str, pd.Series] = {}
    for tk, grp in chosen.items():
        live = frames[grp][tk].reindex(index)
        # Any OTHER tier carrying this ticker with a staler tip is a candidate donor of
        # pre-migration history. Longest first: one donor is enough in practice, and a
        # deterministic order keeps the merge reproducible.
        donors = [g for g in groups
                  if g != grp and g in frames and tk in frames[g].columns]
        donors.sort(key=lambda g: -int(frames[g][tk].notna().sum()))
        for dg in donors:
            dead = frames[dg][tk].reindex(index)
            if dead.notna().sum() <= live.notna().sum():
                continue                      # donor adds no history worth testing
            ok, n_overlap, rel = _stitch_ok(dead, live)
            if not ok:
                continue      # too little overlap, or a different adjustment basis
            # Same series, two lanes: live wins wherever it exists, the donor only fills
            # sessions the live column never covered. No seam — the columns are equal on
            # every session they share.
            live = live.combine_first(dead)
            stitched[tk] = (dg, n_overlap, rel)
            break
        cols[tk] = live
        # Record the migrants whose price tip the old keep-first merge would have taken
        # from a dead column (i.e. tier order disagreed with freshness).
        first_by_order = next((g for g in groups
                               if g in frames and tk in frames[g].columns), None)
        if first_by_order is not None and first_by_order != grp:
            prev = lasts[first_by_order].get(tk)
            rescued[tk] = (first_by_order,
                           int((tip - prev).days) if pd.notna(prev) else None, grp)

    out = pd.DataFrame(cols, index=index).sort_index()

    behind: dict[str, int] = {}
    for tk in chosen:
        lv = out[tk].last_valid_index()
        behind[tk] = int((tip - lv).days) if pd.notna(lv) else -1  # -1 = never populated
    return out, {"tip": tip, "behind": behind, "source": chosen,
                 "rescued": rescued, "stitched": stitched}


_DISCLOSED: set = set()


def disclose_merge(meta: dict, label: str) -> None:
    """Line-start ``::warning`` disclosure of what the merge had to rescue.

    Bare print, never the logger: every builder here logs with a prefixing format,
    so ``log.warning("::warning ...")`` emits ``WARNING ::warning ...`` and GitHub
    silently drops it (repo annotation law, tests/test_gh_annotation_line_start.py).

    Deduplicated per (label, rescued set) for the life of the process: `_closes()` is
    called by equity_factors, residual_alpha and the board grader within one build, and
    three identical annotations read as three separate incidents.
    """
    rescued = meta.get("rescued") or {}
    if not rescued:
        return
    key = (label, tuple(sorted(rescued)))
    if key in _DISCLOSED:
        return
    _DISCLOSED.add(key)
    names = ", ".join(f"{t}({d[0]}->{d[2]})" for t, d in sorted(rescued.items())[:12])
    more = "" if len(rescued) <= 12 else f" (+{len(rescued) - 12} more)"
    print(f"::warning title={label} stale-tier column overridden::{len(rescued)} ticker(s) "
          f"carried a FROZEN column in an earlier tier and a live one in a later tier — "
          f"index migrants whose old tier's column stopped on index exit; the live "
          f"column now wins: {names}{more}", flush=True)
