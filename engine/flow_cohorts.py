"""engine/flow_cohorts.py — Cohort-level options-flow aggregation.

Aggregates per-day options flow summary files (data/options_flow/summary_<T>.parquet)
for four thematic cohorts: Mag 7, Memory/Storage, AI Chips, AI Software.

The 06-26 lesson: generals (call-bid) and memory (put-hedge) were invisible when buried
inside a single GICS bucket.  These four cohorts cross GICS lines; surfacing them
separately makes that divergence visible.

Outputs
-------
data/options_flow/cohorts_<key>.parquet — append/idempotent accrual (one row per cohort per
                                     day; COLLECT_LANE=nightly-gated, HOUSE-U5) plus a
                                     bounded backfill of sessions the single-asof upsert
                                     stranded (same gate; see _heal_sessions)
site/flowdata/cohorts.json         — latest-day snapshot + 10-session sparkline arrays
                                     (10 sessions that carry a READING — a null row never
                                     eats a slot)

Design principles (carry-through from flow_desk)
-------------------------------------------------
- DIRECTION (net_premium_mn) is SOFT — always labelled ~ / direction approx.
- NO composite score, NO rank ordering by net premium.
- Cohort order is fixed (COHORTS list order), not ordered by net.
- Percentile context vs own trailing history where >= 20 obs; raw-fallback flag otherwise.
- n_members_covered / n_members honesty count always emitted.
- Display-tier only.  Never feeds any scored or arithmetic weight path.

Run: python -m engine.flow_cohorts  (standalone smoke-test)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config, store
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

# ── Cohort definitions ─────────────────────────────────────────────────────────
# Display names EN + ZH; members sourced from data/baskets/membership.json at
# build time so they track any future membership edits automatically.

COHORTS: list[dict[str, Any]] = [
    {"key": "mag7",            "name_en": "Mag 7",    "name_zh": "七巨头",
     "basket_key": "mag7"},
    {"key": "memory_storage",  "name_en": "Memory",   "name_zh": "存储",
     "basket_key": "memory_storage"},
    {"key": "ai_semiconductors", "name_en": "AI chips", "name_zh": "AI芯片",
     "basket_key": "ai_semiconductors"},
    {"key": "ai_software",     "name_en": "Software",  "name_zh": "软件",
     "basket_key": "ai_software"},
]

# Minimum observations for percentile context; below this → raw fallback
MIN_PCT_HISTORY = 20

# Number of sessions for sparkline arrays
SPARKLINE_SESSIONS = 10

# How far back the backfill pass re-checks for sessions that have per-ticker
# summary coverage but no usable ledger row.  ~20 trading sessions — enough to
# reach MIN_PCT_HISTORY and twice the sparkline window, short enough that the
# pass can never walk deep history.
BACKFILL_LOOKBACK_DAYS = 30

# Parquet store location
COHORTS_STORE_GROUP = "options_flow"
COHORTS_STORE_NAME = "cohorts"

# Ledger row shape — the columns accrued to cohorts_<key>.parquet, in order.
LEDGER_COLUMNS = [
    "gross_premium_mn", "net_premium_mn", "pc_ratio",
    "zerodte_share", "net_doi", "n_members", "n_members_covered",
]


# ── Membership loading ─────────────────────────────────────────────────────────

def _load_cohort_members(data_dir: Path) -> dict[str, list[str]]:
    """Return {cohort_key: [ticker, ...]} from data/baskets/membership.json."""
    p = data_dir / "baskets" / "membership.json"
    if not p.exists():
        log.warning("flow_cohorts: membership.json absent — using empty cohort members")
        return {c["key"]: [] for c in COHORTS}
    mb = json.loads(p.read_text())
    baskets = mb.get("baskets", {})
    result: dict[str, list[str]] = {}
    for cohort in COHORTS:
        basket_key = cohort["basket_key"]
        basket = baskets.get(basket_key, {})
        members = [m["ticker"] for m in basket.get("members", [])
                   if m.get("removed") is None]
        result[cohort["key"]] = members
    return result


# ── Per-ticker summary loading ──────────────────────────────────────────────────

def _load_ticker_summary(
    data_dir: Path,
    ticker: str,
    cache: dict[str, pd.DataFrame | None] | None = None,
) -> pd.DataFrame | None:
    """Load data/options_flow/summary_<TICKER>.parquet (1 row/day history).

    ``cache`` memoises the frame (including the absent/unreadable → None case)
    for the life of one build_cohorts() call.  Without it the backfill pass
    below re-reads all 40 member parquets once per candidate date: measured on
    this checkout, a 30-day pass costs 2.84 s uncached vs 0.20 s cached, and
    render budget is law.
    """
    if cache is not None and ticker in cache:
        return cache[ticker]
    p = data_dir / "options_flow" / f"summary_{ticker}.parquet"
    df: pd.DataFrame | None = None
    if p.exists():
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
        except Exception as e:  # noqa: BLE001
            log.debug("flow_cohorts: summary %s read error: %s", ticker, e)
            df = None
    if cache is not None:
        cache[ticker] = df
    return df


# ── Aggregation ────────────────────────────────────────────────────────────────

def _volume_weighted_pc_ratio(
    df_map: dict[str, pd.DataFrame], asof: date
) -> float | None:
    """Volume-weighted P/C ratio across covered tickers for a given day."""
    total_vol = 0.0
    weighted_pc = 0.0
    for _ticker, df in df_map.items():
        ts = pd.Timestamp(asof)
        if ts not in df.index:
            continue
        row = df.loc[ts]
        vol = float(row.get("volume", 0) or 0)
        pc = float(row.get("pc_ratio") if not pd.isna(row.get("pc_ratio", float("nan"))) else float("nan"))
        if vol > 0 and not np.isnan(pc):
            total_vol += vol
            weighted_pc += vol * pc
    if total_vol < 1:
        return None
    return round(weighted_pc / total_vol, 3)


def _aggregate_day(
    data_dir: Path,
    cohort_key: str,
    members: list[str],
    asof: date,
    cache: dict[str, pd.DataFrame | None] | None = None,
) -> dict[str, Any]:
    """Aggregate options-flow metrics for one cohort on one date.

    Returns a dict with all aggregate columns + honesty counts.
    Values are None when no data is available.
    """
    gross_pm = 0.0
    net_pm = 0.0
    zerodte_w: list[tuple[float, float]] = []  # (gross_weight, zerodte_share)
    vol_total = 0.0
    vol_pc_weighted = 0.0
    net_doi_sum: float | None = None
    n_covered = 0

    ts = pd.Timestamp(asof)

    for ticker in members:
        df = _load_ticker_summary(data_dir, ticker, cache)
        if df is None or ts not in df.index:
            continue
        row = df.loc[ts]
        n_covered += 1

        # Gross premium
        gross = float(row.get("premium_mn") if not pd.isna(row.get("premium_mn", float("nan"))) else 0)
        gross_pm += gross

        # Net premium (SOFT)
        net = float(row.get("net_premium_mn") if not pd.isna(row.get("net_premium_mn", float("nan"))) else 0)
        net_pm += net

        # Volume-weighted P/C ratio
        vol = float(row.get("volume") if not pd.isna(row.get("volume", float("nan"))) else 0)
        pc = row.get("pc_ratio")
        if vol > 0 and pc is not None and not pd.isna(pc):
            vol_total += vol
            vol_pc_weighted += vol * float(pc)

        # Zerodte share (weight by gross premium)
        z_share = row.get("zerodte_share")
        if gross > 0 and z_share is not None and not pd.isna(z_share):
            zerodte_w.append((gross, float(z_share)))

        # Net DOI — sum if available
        net_doi = row.get("net_doi")
        if net_doi is not None and not pd.isna(net_doi):
            if net_doi_sum is None:
                net_doi_sum = 0.0
            net_doi_sum += float(net_doi)

    if n_covered == 0:
        return {
            "key": cohort_key,
            "asof": str(asof),
            "gross_premium_mn": None,
            "net_premium_mn": None,
            "pc_ratio": None,
            "zerodte_share": None,
            "net_doi": None,
            "n_members": len(members),
            "n_members_covered": 0,
        }

    # Compute weighted averages
    pc_ratio = round(vol_pc_weighted / vol_total, 3) if vol_total > 0 else None
    zerodte_total_w = sum(w for w, _ in zerodte_w)
    zerodte_share = (
        round(sum(w * z for w, z in zerodte_w) / zerodte_total_w, 3)
        if zerodte_total_w > 0 else None
    )

    return {
        "key": cohort_key,
        "asof": str(asof),
        "gross_premium_mn": round(gross_pm, 1) if n_covered > 0 else None,
        "net_premium_mn": round(net_pm, 1) if n_covered > 0 else None,  # soft
        "pc_ratio": pc_ratio,
        "zerodte_share": zerodte_share,
        "net_doi": round(net_doi_sum, 0) if net_doi_sum is not None else None,
        "n_members": len(members),
        "n_members_covered": n_covered,
    }


# ── Bounded backfill ───────────────────────────────────────────────────────────

def _heal_sessions(
    data_dir: Path,
    cohort_key: str,
    members: list[str],
    asof: date,
    cache: dict[str, pd.DataFrame | None],
) -> tuple[list[str], int]:
    """Re-aggregate in-window sessions that have per-ticker summary coverage but
    no usable ledger row.  Returns (healed ISO dates, in-window dates skipped
    for zero coverage).

    Two row shapes are healed, and they are one defect seen from two sides:

    - an ALL-NULL row, written by an off-nightly run whose requested asof had no
      per-ticker coverage *at the time*.  #4007 gated new ones; the rows already
      written stayed, and nothing revisited them — because a later nightly only
      ever upserts its own asof.  Five of the nine such rows in the committed
      store (07-13/14/16/17/20) sit at dates the summary store covers in FULL
      today: the reading was recoverable all along, so purging those rows would
      have thrown away five real sessions.
    - NO row at all, for the same reason from the other direction: a session the
      nightly never ran at (07-01/02/06/09/10 pre-FL-B) never got a row, and the
      single-asof upsert has no path back to it.

    Deliberately consistent with the main path on coverage: any date with
    n_members_covered > 0 is written, exactly as the nightly would have written
    it at the time.  A date with ZERO coverage carries no information and is
    never written — that is the row shape this whole repair exists to stop.

    Caller must already be in the nightly lane; this UPSERTS a forward ledger.
    Values come from the summary store as it stands TODAY, so a healed row
    carries the current vintage of the per-ticker summaries rather than the
    vintage of the original session — acceptable at display tier (this artifact
    feeds no scored or arithmetic path), and stated in the JSON's own
    magnitude/direction notes.
    """
    if not members:
        return [], 0

    lo = pd.Timestamp(asof) - pd.Timedelta(days=BACKFILL_LOOKBACK_DAYS)
    hi = pd.Timestamp(asof)  # exclusive — asof itself is owned by the main path

    hist = store.read(COHORTS_STORE_GROUP, f"{COHORTS_STORE_NAME}_{cohort_key}")
    usable: set[pd.Timestamp] = set()
    if hist is not None and not hist.empty and "gross_premium_mn" in hist.columns:
        usable = set(pd.to_datetime(hist.index[hist["gross_premium_mn"].notna()]).normalize())

    # Candidate sessions = every date the members' summary store covers in-window.
    covered: set[pd.Timestamp] = set()
    for ticker in members:
        df = _load_ticker_summary(data_dir, ticker, cache)
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index).normalize()
        covered |= set(idx[(idx >= lo) & (idx < hi)])

    todo = sorted(covered - usable)
    if not todo:
        return [], 0

    rows: list[dict[str, Any]] = []
    stamps: list[pd.Timestamp] = []
    skipped = 0
    for ts in todo:
        row = _aggregate_day(data_dir, cohort_key, members, ts.date(), cache)
        if row.get("n_members_covered", 0) < 1 or row.get("gross_premium_mn") is None:
            skipped += 1
            continue
        rows.append(row)
        stamps.append(ts)

    if not rows:
        return [], skipped

    # One upsert per cohort, not one per date — the store rewrites the whole file.
    sdf = pd.DataFrame({k: [r.get(k) for r in rows] for k in LEDGER_COLUMNS}, index=stamps)
    store.upsert(COHORTS_STORE_GROUP, f"{COHORTS_STORE_NAME}_{cohort_key}", sdf, outlier_col=None)
    return [str(ts.date()) for ts in stamps], skipped


# ── Percentile context ─────────────────────────────────────────────────────────

def _percentile_vs_history(
    series: pd.Series, value: float, min_obs: int = MIN_PCT_HISTORY
) -> float | None:
    """Compute percentile of value vs series history. Returns 0-100 or None."""
    clean = series.dropna()
    if len(clean) < min_obs:
        return None
    pct = float((clean < value).sum()) / len(clean) * 100
    return round(pct, 1)


# ── Tone chip ─────────────────────────────────────────────────────────────────

def _pc_tone(pc_ratio: float | None) -> str:
    """Return plain-word P/C tone label (solid, not direction-signed net)."""
    if pc_ratio is None:
        return "balanced"
    if pc_ratio < 0.7:
        return "call-tilted"
    if pc_ratio > 1.3:
        return "put-tilted"
    return "balanced"


def _net_soft_tone(net_pm: float | None) -> str:
    """Soft net-premium direction chip (direction approx only)."""
    if net_pm is None:
        return "neutral~"
    if net_pm > 30:
        return "pos~"
    if net_pm < -30:
        return "neg~"
    return "neutral~"


# ── Main build entry points ───────────────────────────────────────────────────

def build_cohorts(
    data_dir: Path,
    asof: date | None = None,
    site_flowdata_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Build cohort-level flow aggregates for a single date.

    Parameters
    ----------
    data_dir:         path to data/ directory (config.data_dir())
    asof:             date to aggregate; defaults to today
    site_flowdata_dir: where to write cohorts.json (site/flowdata/); None → skip JSON

    Returns a list of cohort dicts (one per cohort), with percentile context,
    tone chips, sparkline arrays, and honesty counts.  Also:
    - appends one row per cohort to data/options_flow/cohorts_<key>.parquet
      (idempotent; COLLECT_LANE=nightly-gated, HOUSE-U5)
    - re-aggregates in-window sessions that have per-ticker summary coverage but
      no usable ledger row (same gate; bounded to BACKFILL_LOOKBACK_DAYS — see
      _heal_sessions for why a single-asof upsert alone strands sessions)
    - writes site/flowdata/cohorts.json if site_flowdata_dir is given

    The returned rows and the JSON are produced in EVERY lane — only the parquet
    accrual is gated.  Percentile context and sparklines are read back from the
    store, so off-nightly they reflect the committed vintage (see the gate
    comment below).
    """
    if asof is None:
        asof = date.today()

    members_map = _load_cohort_members(data_dir)
    cohort_rows: list[dict[str, Any]] = []
    # Per-call summary-frame cache — shared by the asof aggregation and the
    # backfill pass so the whole build reads each member parquet at most once.
    summary_cache: dict[str, pd.DataFrame | None] = {}

    # HOUSE-U5: the accrual UPSERTS committed data/options_flow/ parquets, so only
    # the nightly collector may advance them — express/intraday lanes bake site/
    # from the committed vintage and must leave data/ untouched.  The headline
    # figures below are recomputed live in every lane; only the percentile and
    # sparkline context, read back from the store, stays at the committed vintage.
    #
    # This gate is not merely hygiene — it closes a measured corruption.  An
    # off-nightly run whose asof has no per-ticker summary coverage aggregates to
    # n_members_covered=0 / all-None, and the ungated upsert wrote THAT row into
    # the forward ledger: measured 2026-07-29 on this checkout (tide asof 07-28,
    # summary parquets ending 07-27) an express run appended a NaN row at 07-28 to
    # all four cohorts_<key>.parquet and the sparkline tail came back [4893.9,
    # None].  Gated, the ledger stays at 07-27 and the sparkline reads [4877.0,
    # 4893.9].  Nightly is the sole advancer of forward ledgers (house law).
    persist = nightly_advance_enabled()
    if not persist:
        log.info("flow_cohorts: COLLECT_LANE!=nightly — cohort accrual upserts skipped "
                 "(cohorts_<key>.parquet stay at committed vintage; display reads "
                 "committed history)")

    for cohort in COHORTS:
        ckey = cohort["key"]
        members = members_map.get(ckey, [])
        row = _aggregate_day(data_dir, ckey, members, asof, summary_cache)
        cohort_rows.append(row)

        # Accrue to parquet store (idempotent via upsert) — nightly lane only.
        if persist:
            try:
                sdf = pd.DataFrame(
                    {k: [row.get(k)] for k in LEDGER_COLUMNS},
                    index=[pd.Timestamp(asof)],
                )
                store.upsert(COHORTS_STORE_GROUP, f"{COHORTS_STORE_NAME}_{ckey}", sdf, outlier_col=None)
            except Exception as e:  # noqa: BLE001
                log.warning("flow_cohorts: accrual %s failed: %s", ckey, e)

    # Bounded backfill — nightly lane only, and only AFTER the asof row is in
    # place so the pass never competes with the main upsert for the same date.
    # Without this there is no path back to a session the nightly never ran at,
    # nor to a null row an off-nightly run left behind (see _heal_sessions).
    if persist:
        for cohort in COHORTS:
            ckey = cohort["key"]
            try:
                healed, skipped = _heal_sessions(
                    data_dir, ckey, members_map.get(ckey, []), asof, summary_cache
                )
            except Exception as e:  # noqa: BLE001 — a repair must never kill the build
                log.warning("flow_cohorts: backfill %s failed: %s", ckey, e)
                continue
            if healed or skipped:
                log.info(
                    "flow_cohorts: backfill %s — healed %d session(s) %s; "
                    "%d in-window date(s) skipped (zero member coverage — no row written)",
                    ckey, len(healed), healed, skipped,
                )

    # Enrich with percentile context + sparklines
    enriched: list[dict[str, Any]] = []
    for cohort, row in zip(COHORTS, cohort_rows):
        ckey = cohort["key"]
        enriched_row = dict(row)
        enriched_row["name_en"] = cohort["name_en"]
        enriched_row["name_zh"] = cohort["name_zh"]

        # Load trailing history for percentile context
        hist_df = store.read(COHORTS_STORE_GROUP, f"{COHORTS_STORE_NAME}_{ckey}")

        # Gross premium percentile
        gross_pct = None
        raw_fallback = True
        spark_gross: list[float | None] = []
        spark_net: list[float | None] = []

        if hist_df is not None and not hist_df.empty and "gross_premium_mn" in hist_df.columns:
            hist_gross = hist_df["gross_premium_mn"].dropna()
            obs = len(hist_gross)
            raw_fallback = obs < MIN_PCT_HISTORY
            if not raw_fallback and row.get("gross_premium_mn") is not None:
                gross_pct = _percentile_vs_history(hist_gross, row["gross_premium_mn"])

            # Sparkline: the last SPARKLINE_SESSIONS sessions that carry a READING,
            # not the last SPARKLINE_SESSIONS rows.  A null row consumes a slot
            # under a plain .tail(): measured on the committed 2026-07-28 vintage,
            # mag7 spark_gross came back
            #   [5777.8, null, null, null, null, null, null, 4877.0, 4893.9, 4012.3]
            # — 4 real points in 10 slots, because nine all-null rows an off-nightly
            # run had left in the ledger (#4007 gated new ones, nothing cleaned the
            # old) sat inside the window.  The percentile path was already immune via
            # its own .dropna(); this makes the sparkline immune the same way, so any
            # future null row costs the strip nothing whatever the store holds.
            #
            # Selection is on gross_premium_mn (the sparkline's own series) and BOTH
            # arrays are then read off the same frame — spark_gross and spark_net must
            # stay positionally aligned to one set of sessions, so a session whose
            # net signing failed keeps its null in spark_net rather than shifting the
            # series by one slot.
            recent = hist_df[hist_df["gross_premium_mn"].notna()].tail(SPARKLINE_SESSIONS)
            spark_gross = [
                (float(v) if not pd.isna(v) else None)
                for v in recent.get("gross_premium_mn", pd.Series(dtype=float))
            ]
            if "net_premium_mn" in recent.columns:
                spark_net = [
                    (float(v) if not pd.isna(v) else None)
                    for v in recent["net_premium_mn"]
                ]

        enriched_row["gross_pct"] = gross_pct
        enriched_row["raw_fallback"] = raw_fallback
        enriched_row["spark_gross"] = spark_gross
        enriched_row["spark_net"] = spark_net

        # P/C tone (solid read — magnitude)
        enriched_row["pc_tone"] = _pc_tone(row.get("pc_ratio"))
        # Net soft tone (direction approx)
        enriched_row["net_tone"] = _net_soft_tone(row.get("net_premium_mn"))

        # Coverage label
        n_m = row.get("n_members", 0)
        n_c = row.get("n_members_covered", 0)
        enriched_row["coverage_label"] = f"{n_c} of {n_m} members covered"

        enriched.append(enriched_row)

    # Write JSON snapshot
    if site_flowdata_dir is not None:
        _write_json(enriched, asof, site_flowdata_dir)

    return enriched


def _write_json(
    enriched: list[dict[str, Any]],
    asof: date,
    site_flowdata_dir: Path,
) -> None:
    """Write site/flowdata/cohorts.json (latest snapshot + sparkline arrays)."""
    site_flowdata_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "flow_cohorts.v1",
        "built": str(date.today()),
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "asof": str(asof),
        "direction_reliable": False,
        "magnitude_reliable": True,
        "direction_note": (
            "net premium direction is SOFT — approximate (minute tick-rule signing); "
            "P/C ratio from volume-weighted aggregate is a solid magnitude read"
        ),
        "cohorts": enriched,
    }
    out = site_flowdata_dir / "cohorts.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), default=_json_default))
    log.info("flow_cohorts: wrote %s (%d bytes)", out, out.stat().st_size)


def _json_default(obj: Any) -> Any:  # noqa: ANN401
    """JSON serializer fallback for non-standard types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (date, datetime)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Standalone smoke-test ──────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    data_dir = config.data_dir()
    cfg = config.load()
    site_dir = config.ROOT / cfg["storage"]["site_dir"]
    site_flowdata_dir = site_dir / "flowdata"

    rows = build_cohorts(data_dir, site_flowdata_dir=site_flowdata_dir)
    for r in rows:
        log.info(
            "cohort=%s gross=$%sM net=$%sM~ pc=%s 0DTE=%s%% covered=%d/%d pct=%s",
            r["key"], r.get("gross_premium_mn"), r.get("net_premium_mn"),
            r.get("pc_ratio"), round((r.get("zerodte_share") or 0) * 100),
            r.get("n_members_covered", 0), r.get("n_members", 0),
            r.get("gross_pct"),
        )
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
