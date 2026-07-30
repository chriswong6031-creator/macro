"""engine/positioning_persistence.py — OIP E3: positioning persistence reads.

Lights the four positioning-persistence reads the gex_state payload was missing
(research/options_estate/OIP_MASTERPLAN.md §6 E3), all DISPLAY-TIER, all derived
from stores that already exist:

  (a) oi_delta_clusters   — matched-contract day-over-day open-interest change from
      data/polygon_gex/chains/{date}.parquet (per-strike snapshots, 2026-06-15->).
      This is the SANCTIONED reliable read (§0.8): a signing-free count of contracts
      added or closed. Build/unwind FACTS only — no direction claim, no fused score,
      and deliberately no sector-level aggregation (that lens is a standing kill).
  (b) wall_persistence    — how long the heaviest-open-interest strike either side of
      the price has held, over a bounded window of stored snapshots.
  (d) net_gex_pctile      — where today's net dealer gamma sits inside the name's OWN
      accrued daily record (the board payload's history[]).
      deep_history        — descriptive window/spread of the multi-year index rebuild
      (data/index_gex_history), for the four index ETFs it covers.

WHY OPEN INTEREST AND NOT DOLLAR GAMMA (documented deviation — OURS)
--------------------------------------------------------------------
The masterplan sketches (b) as "sessions-at-level count for current call/put walls
from payload history[]". That is not computable: the payload's history[] rows carry
only {date, net_gex_bn, regime, iv30}, and the store behind them (data/cboe/gex_<KEY>)
has no wall columns at all — no wall level was ever persisted, so there is no wall
history of ANY vintage to count. The two buildable alternatives were:

  * recompute the payload's dollar-gamma wall per session from the polygon chain
    snapshots (measured: 19.1 s / 340 MB peak for a 10-session window, 11.3 s for 6) —
    rejected: it costs ~80x more than the read below, it imports the assumption-signed
    dealer sign into a NEW field, and its "today" wall comes from a DIFFERENT chain
    source (Polygon) than the payload's wall (Cboe), so annotating one with the other
    is the mixed-source class §0.11 forbids;
  * count persistence of the OPEN-INTEREST wall — the heaviest call-side open interest
    above the price and the heaviest put-side below it — from the same snapshots
    (measured: 0.15 s for a 6-session window). Signing-free, internally consistent
    (one source on both sides), and the same reliable instrument (a) is built on.

The second is what ships. It is NOT relabelled as the payload's `call_wall` /
`put_wall`: the block carries its own level plus `matches_board_wall`, so a consumer
can see when the gamma wall and the open-interest wall coincide and when they do not.

SESSION + VINTAGE INTEGRITY (§0.11 — the classes that have bitten this repo)
---------------------------------------------------------------------------
  * Weekend/holiday rows are REAL in both stores. data/polygon_gex/chains holds 11
    non-session files out of 39 (Saturdays, Sundays, and Juneteenth 2026-06-19);
    data/cboe/gex_SPY.parquet holds 13 non-session rows out of 36. Every dated read
    here session-filters through lib.nyse_calendar.is_session FIRST.
  * The filename date is NOT the open-interest vintage. Consecutive snapshots can
    carry byte-identical open interest (measured: 2026-07-25/26/27 are all the same
    reading, and 7 of 10 names repeat between 2026-06-15 and 2026-06-16). A delta
    across two identical vintages is not "no change" — it is an unmeasurable window,
    so `same_vintage` is stamped, the lists come back empty, and the note says so.
    This is the mixed-asof class: the guard is per NAME, because one root can repeat
    while the rest of the file advances.
  * TWO SNAPSHOTS BEING SELF-CONSISTENT DOES NOT MAKE THEM CURRENT OR ADJACENT. Every
    block therefore stamps `sessions_apart` (1 = consecutive; more means the pair
    straddles a collector gap and the "day-over-day" framing would be a lie) and
    `sessions_behind` + `stale` for the newest snapshot against the latest close. Both
    are said in plain words. Without them a collector dead for weeks reads as today.
  * THE SNAPSHOT'S PRICE IS NOT THE BOARD'S PRICE. `dist_pct` and the above/below-price
    wall split are measured against the SNAPSHOT source's own underlying price — one
    source on both sides of every derived number — while the payload's top-level `spot`
    comes from the Cboe chain. They really diverge. Measured 2026-07-29 over the 302 roots
    that actually EMIT a payload (the population the artifact has, not the 358 roots that
    merely share both prices — thin-chain names like LII are dropped by compute_gex_state
    before any of this is reached): median 0.582%, 129 past 1%, 97 past 2%, 40 past 5%,
    worst 18.6% (UCTT 77.50 snapshot vs 95.25 board). So both blocks emit
    `snapshot_spot`, and the payload layer adds a plain-word note when the gap exceeds
    SPOT_DIVERGENCE_PCT or when any emitted row's above/below reading flips between the
    two prices; a reader must never have to discover that `dist_pct`'s sign disagrees
    with (K - payload.spot).
  * Open interest is a COUNT of contracts (integral, >= 0). `_normalise_chain` refuses
    a frame whose oi column looks normalised/fractional rather than a count, so a
    vendor or fixture shape change cannot silently rescale the delta. It also drops
    rows with a null-shaped or duplicated `strike_ticker` before the merge, because the
    inner join would otherwise pair every such row on one side with every one on the
    other — an m*n cartesian product of invented contracts. Measured 0 nulls and 0
    duplicates across all 28 session snapshots today: a fence, not a live fix.
  * `oi_delta_pct` is a PERCENT (1000 -> 1500 is 50.0, never 0.5) — the x100 class.

STANDING-KILL COMPLIANCE (checked against research/DO_NOT_REBUILD.md)
---------------------------------------------------------------------
The registry carries "DOI (options delta-OI family) | DEAD | Options->NW
entry-intelligence W-E1 gauntlet". That kill is a PROMOTION verdict: the ΔOI family
does not earn rank / size / gate authority. It is not a build gate — the house rule is
that context and detection infrastructure ships display-tier freely and a null never
blocks accrual (CLAUDE.md §Epistemics). Everything here is display-tier and descriptive:
no score, no ranking, no gating, no direction language beyond the build/unwind facts, and
no sector-level ΔOI aggregation (the specific construction the W-E1 census closed).
The OIP masterplan §8 lists matched-contract day-over-day ΔOI among the estate's two
RELIABLE instruments precisely because it is signing-free — that is the read below.

EPISTEMIC LAWS (binding)
------------------------
  * authority_tier stays 'display'; nothing here ranks, sizes, or gates.
  * No "validated" wording. No falsifier/refutation language.
  * Every user-facing string is a plain-word EN/ZH pair (note_en / note_zh); internal
    enums stay in machine-named fields, never inside the notes.
  * Nulls, vintages and young windows are PRINTED, never hidden.
  * Reads only. This module writes nothing to data/ — it is safe in the intraday
    closing-bell lane as well as the nightly one (§0.9).
"""
from __future__ import annotations

import datetime as _dt
import glob
import logging
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from lib import nyse_calendar

log = logging.getLogger(__name__)

# ── tunables (OURS) ──────────────────────────────────────────────────────────
# Snapshots read for the wall-persistence window. Bounded on purpose: the whole
# accrued history is never scanned (§0.10). 6 sessions is ~1.2 weeks of tape —
# long enough to separate "this level has been here all week" from "new today",
# short enough that the read costs ~0.15 s for the full 370-name store.
# NOTE ON THE READ BUDGET: the CLUSTER derivation reads exactly 2 chain days; the WALL
# pass reads this many (each released as soon as its levels are extracted). "Reads 2
# chain days" is a statement about the clusters only — do not quote it for the module.
WALL_WINDOW_SESSIONS = 6
# Top-N strikes per side in each cluster list. Keeps the per-name payload bounded.
CLUSTER_TOP_N = 4
# A stored daily record shorter than this is flagged low_confidence for percentiles.
PCTILE_LOW_CONFIDENCE_SESSIONS = 60
# The index rebuild is a weekly job; more than a week and a half of sessions behind
# is worth saying out loud (calmly — see note_en/note_zh, never an alarm).
DEEP_HISTORY_STALE_SESSIONS = 7
# The chain store is a DAILY collect step, so it is behind as soon as it misses a day.
# 2 gives one session of slack for a run that lands before the settle buffer.
CHAIN_STALE_SESSIONS = 2
# Above this, the snapshot source's underlying price is far enough from the board's own
# that a reader comparing dist_pct to payload.spot would be misled — so say it.
SPOT_DIVERGENCE_PCT = 2.0
# Index roots the multi-year rebuild covers (scripts/build_index_gex_history.py).
DEEP_HISTORY_ROOTS = frozenset({"SPY", "QQQ", "IWM", "DIA"})
_DEEP_HISTORY_GROUP = "index_gex_history"

# Chain columns the reads need. Pruned hard — the daily file is ~4.6 MB on disk.
CHAIN_COLS = ["underlying", "strike_ticker", "K", "is_call", "oi", "spot"]

# First stored per-strike snapshot (data/polygon_gex/chains). Used for the young-window
# disclosure when the resolved history really does start at the beginning of the store.
_STORE_EPOCH_NOTE_EN = "Per-strike chain snapshots begin {start}, so this record is still short."
_STORE_EPOCH_NOTE_ZH = "逐行权价期权链快照自 {start} 起累积，记录仍然很短。"

# Copy for a genuine READ/BUILD FAILURE — deliberately different from "not stored". The
# store may be intact and simply unreadable this run; claiming nothing is stored would
# point a reader at the wrong problem. engine/gex_state.py keeps a byte-identical pair for
# the one path that cannot reach this module (its own import failing); a test pins them
# equal so the two copies cannot drift.
OI_DELTA_UNAVAILABLE_EN = (
    "Open-interest change could not be read for this name, so no build or unwind "
    "strikes are shown."
)
OI_DELTA_UNAVAILABLE_ZH = "本标的未平仓量变化暂时无法读取，因此不显示新增或平仓行权价。"


# ── small helpers ────────────────────────────────────────────────────────────

def _f(x: Any, n: int = 2) -> float | None:
    """Round to n dp, or None for NaN/inf/non-numeric — JSON-safe (allow_nan=False)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def _i(x: Any) -> int | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return int(round(v)) if np.isfinite(v) else None


def _as_date(x: Any) -> _dt.date | None:
    """Coerce a string/date/Timestamp to a plain date, or None."""
    if x is None:
        return None
    if isinstance(x, _dt.date) and not isinstance(x, _dt.datetime):
        return x
    try:
        return pd.Timestamp(x).date()
    except (ValueError, TypeError):
        return None


# ── injectable readers (default = disk; tests pass fakes) ────────────────────

def _chains_dir() -> Path:
    from lib import config  # noqa: PLC0415 — keeps this module importable bare
    return config.data_dir() / "polygon_gex" / "chains"


def default_chain_dates() -> list[_dt.date]:
    """Sorted SESSION-only chain snapshot dates (from the filenames).

    Non-session files are real in this store (weekend runs re-fetch the Friday
    reading, and 2026-06-19 Juneteenth has a file) — dropping them here is the
    #3721 weekend-row guard applied at the earliest possible seam.
    """
    out: list[_dt.date] = []
    for f in glob.glob(str(_chains_dir() / "*.parquet")):
        d = _as_date(Path(f).stem)
        if d is not None and nyse_calendar.is_session(d):
            out.append(d)
    return sorted(out)


def default_read_chain(d: _dt.date) -> pd.DataFrame | None:
    p = _chains_dir() / f"{d.isoformat()}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p, columns=CHAIN_COLS)
    except Exception as e:  # noqa: BLE001 — a corrupt snapshot must not break the pass
        log.warning("positioning_persistence: chain %s unreadable: %s", d, e)
        return None


# ── ingestion guard (§0.11 unit seam) ────────────────────────────────────────

class ChainShapeError(ValueError):
    """The chain frame does not carry open interest as a count of contracts."""


def _normalise_chain(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a chain frame to the canonical shape and REFUSE a rescaled oi column.

    Accepts both the production dtypes (underlying=category, oi/K/spot=float32,
    is_call=bool) and plain fixture dtypes (object/int64/float64, is_call as
    bool / 0-1 / "C"/"P"). Raises ChainShapeError when `oi` looks like a
    fraction or share rather than a contract count — the shape that would let a
    vendor change silently rescale every delta downstream.
    """
    missing = [c for c in CHAIN_COLS if c not in df.columns]
    if missing:
        raise ChainShapeError(f"chain frame missing columns: {missing}")

    # `underlying` stays CATEGORICAL (it is in production and ~450 rows share each of
    # 370 values): materialising 165k Python strings per snapshot cost ~130 MB of the
    # measured peak for nothing. float32 is kept for the numerics — every value in this
    # store is exactly representable (open interest tops out ~3e5, strikes are .0/.5/
    # .25) — and only the per-underlying SUMS widen to float64 below.
    out = pd.DataFrame({
        "underlying": (df["underlying"] if isinstance(df["underlying"].dtype,
                                                      pd.CategoricalDtype)
                       else df["underlying"].astype("category")),
        "strike_ticker": df["strike_ticker"].astype(str),
        "K": pd.to_numeric(df["K"], errors="coerce", downcast="float"),
        "oi": pd.to_numeric(df["oi"], errors="coerce", downcast="float"),
        "spot": pd.to_numeric(df["spot"], errors="coerce", downcast="float"),
    })

    ic = df["is_call"]
    if ic.dtype == bool:
        out["is_call"] = ic.to_numpy(bool)
    elif pd.api.types.is_numeric_dtype(ic):
        out["is_call"] = pd.to_numeric(ic, errors="coerce").fillna(0).astype(int).astype(bool)
    else:
        s = ic.astype(str).str.strip().str.upper()
        out["is_call"] = s.isin({"C", "CALL", "TRUE", "1"}).to_numpy(bool)

    out = out.dropna(subset=["K", "oi", "spot"])

    # JOIN-KEY INVARIANT (must hold before the inner merge in matched_oi_delta).
    # strike_ticker is the OCC contract id and is the SOLE join key. A null-shaped or
    # duplicated key is not a harmless bad row: pandas' inner merge pairs every left
    # occurrence with every right occurrence, so m nulls on one side x n on the other is
    # an m*n CARTESIAN product of invented contract pairs feeding the OI sums. Drop them
    # here and report the count — silently tolerating them is the fabrication path.
    # Measured 2026-07-29 across all 28 session snapshots: 0 nulls, 0 duplicates. This is
    # a FENCE against a vendor/fixture shape change, not a fix for a live defect.
    before = len(out)
    bad_key = out["strike_ticker"].isna() | out["strike_ticker"].isin(
        {"", "nan", "NaN", "None", "<NA>"})
    out = out[~bad_key]
    out = out[~out["strike_ticker"].duplicated(keep=False)]
    dropped = before - len(out)
    out.attrs["dropped_bad_join_keys"] = int(dropped)

    oi = out["oi"]
    if len(oi):
        if (oi < 0).any():
            raise ChainShapeError("chain frame carries negative open interest")
        positive = oi[oi > 0]
        # A count column has integral values >= 1. An all-below-1 positive column is a
        # share/fraction; a non-integral one has been scaled. Either would make
        # oi_delta a fabricated number, so refuse rather than publish it.
        if len(positive) and float(positive.max()) < 1.0:
            raise ChainShapeError(
                "open interest looks normalised (every positive value < 1) — expected a "
                "count of contracts, not a share")
        if len(positive) and not bool(np.isclose(positive % 1.0, 0.0).all()):
            raise ChainShapeError(
                "open interest is not integral — expected a count of contracts")
    return out


# ── vintage fingerprints (mixed-asof guard) ──────────────────────────────────

def vintage_fingerprints(df: pd.DataFrame) -> pd.DataFrame:
    """Per-underlying content fingerprint of one chain snapshot.

    The filename date is a RUN stamp, not the open-interest vintage: a weekend or
    early-morning run re-fetches the previous reading unchanged. Two snapshots that
    agree on (contract count, total open interest, underlying price) for a name are
    the same reading for that name, whatever their filenames say.
    """
    # WIDEN BEFORE SUMMING (vectorised, not per-group): a float32 accumulator over a
    # liquid root's ~6k contracts of up to 3e5 open interest each reaches ~1e8, well past
    # float32's 2^24 exact-integer range — and a fingerprint that rounds is a fingerprint
    # that falsely MATCHES, which would suppress a real delta as "same vintage".
    tmp = pd.DataFrame({"underlying": df["underlying"],
                        "oi": df["oi"].astype("float64"),
                        "spot": df["spot"].astype("float64")})
    g = tmp.groupby("underlying", observed=True).agg(
        contracts=("oi", "size"), oi_total=("oi", "sum"), spot=("spot", "first"))
    g.index = g.index.astype(str)
    return g


def same_vintage_mask(prior_fp: pd.DataFrame, latest_fp: pd.DataFrame) -> "pd.Series":
    """Boolean Series indexed by underlying — True when the two snapshots agree."""
    j = prior_fp.join(latest_fp, how="inner", lsuffix="_a", rsuffix="_b")
    if j.empty:
        return pd.Series(dtype=bool)
    # EXACT equality, not np.isclose. Both sides are float64 sums of integral contract
    # counts, so they are exact — while isclose's default rtol=1e-5 on a liquid root's
    # ~1e8 total is a ~1,000-contract tolerance, i.e. it would call a genuine
    # thousand-contract day "the same vintage" and suppress a real delta.
    return ((j["contracts_a"] == j["contracts_b"])
            & (j["oi_total_a"] == j["oi_total_b"])
            & (j["spot_a"] == j["spot_b"]))


# ── (a) matched-contract open-interest delta ─────────────────────────────────

def matched_oi_delta(prior: pd.DataFrame, latest: pd.DataFrame) -> pd.DataFrame:
    """Per (underlying, strike, right) open-interest change on MATCHED contracts.

    Matched on `strike_ticker` (the OCC contract id, unique within a snapshot), so a
    contract that only exists on one side never contributes a phantom delta. Strike
    and price are taken from the LATEST side only — never mixed across snapshots.

    Returns columns: underlying, K, right, oi_prior, oi_now, oi_delta, oi_delta_pct,
    dist_pct, spot, contracts.
    """
    empty = pd.DataFrame(columns=["underlying", "K", "right", "oi_prior", "oi_now",
                                  "oi_delta", "oi_delta_pct", "dist_pct", "spot",
                                  "contracts"])
    if prior.empty or latest.empty:
        return empty
    # strike_ticker is the OCC contract id and is unique WITHIN a snapshot, so it alone
    # is the join key — and the prior side contributes ONLY its open interest. Every
    # other field (strike, right, price, root) comes from the latest snapshot, which is
    # what makes the row mixed-vintage-proof by construction rather than by convention.
    m = latest[["underlying", "strike_ticker", "K", "is_call", "oi", "spot"]].merge(
        prior[["strike_ticker", "oi"]].rename(columns={"oi": "oi_a"}),
        on="strike_ticker", how="inner")
    if m.empty:
        return empty
    # Widen the two open-interest columns BEFORE the group sums (see vintage_fingerprints
    # for why float32 accumulators are not safe at this scale). Vectorised cast, not a
    # per-group lambda — the lambda form measured 2.6x slower on the real store.
    m["oi"] = m["oi"].astype("float64")
    m["oi_a"] = m["oi_a"].astype("float64")
    g = m.groupby(["underlying", "K", "is_call"], observed=True).agg(
        oi_prior=("oi_a", "sum"), oi_now=("oi", "sum"),
        spot=("spot", "first"), contracts=("strike_ticker", "size"),
    ).reset_index()
    g["underlying"] = g["underlying"].astype(str)
    g["right"] = np.where(g["is_call"].to_numpy(bool), "call", "put")
    g["oi_delta"] = g["oi_now"] - g["oi_prior"]
    # PERCENT of the prior reading (x100 class): 1000 -> 1500 is 50.0, not 0.5.
    prior_oi = g["oi_prior"].to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(prior_oi > 0, g["oi_delta"].to_numpy(float) / prior_oi * 100.0, np.nan)
    g["oi_delta_pct"] = pct
    spot = g["spot"].to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        g["dist_pct"] = np.where(spot > 0, (g["K"].to_numpy(float) - spot) / spot * 100.0, np.nan)
    return g.drop(columns=["is_call"])


def _cluster_row(r: Any) -> dict:
    return {
        "K": _f(r.K, 4),
        "right": str(r.right),
        "oi_prior": _i(r.oi_prior),
        "oi_now": _i(r.oi_now),
        "oi_delta": _i(r.oi_delta),
        "oi_delta_pct": _f(r.oi_delta_pct, 1),
        "dist_pct": _f(r.dist_pct, 1),
        "contracts": _i(r.contracts),
    }


def clusters_for_underlying(delta: pd.DataFrame, top_n: int = CLUSTER_TOP_N) -> dict:
    """Top build / top unwind strikes for ONE underlying's delta frame."""
    if delta.empty:
        return {"new_oi": [], "exit_oi": []}
    builds = delta[delta["oi_delta"] > 0].nlargest(top_n, "oi_delta")
    unwinds = delta[delta["oi_delta"] < 0].nsmallest(top_n, "oi_delta")
    return {
        "new_oi": [_cluster_row(r) for r in builds.itertuples()],
        "exit_oi": [_cluster_row(r) for r in unwinds.itertuples()],
    }


# ── (b) open-interest wall persistence ───────────────────────────────────────

def oi_walls(df: pd.DataFrame) -> pd.DataFrame:
    """Per-underlying heaviest call open interest ABOVE the price and heaviest put
    open interest BELOW it, aggregated across expiries at each strike.

    Signing-free: this is a count of contracts at a level, not a dealer-gamma sign.
    Returns columns: underlying, call_K, call_oi, put_K, put_oi, spot.
    """
    if df.empty:
        return pd.DataFrame(columns=["underlying", "call_K", "call_oi",
                                     "put_K", "put_oi", "spot"])
    d = df[df["oi"] > 0]
    if d.empty:
        return pd.DataFrame(columns=["underlying", "call_K", "call_oi",
                                     "put_K", "put_oi", "spot"])
    g = d.groupby(["underlying", "K", "is_call"], observed=True).agg(
        oi=("oi", "sum"), spot=("spot", "first")).reset_index()
    up = g[(g["K"] > g["spot"]) & g["is_call"]]
    dn = g[(g["K"] < g["spot"]) & ~g["is_call"]]
    parts = []
    if not up.empty:
        c = up.loc[up.groupby("underlying", observed=True)["oi"].idxmax()]
        parts.append(c[["underlying", "K", "oi", "spot"]]
                     .rename(columns={"K": "call_K", "oi": "call_oi"})
                     .set_index("underlying"))
    if not dn.empty:
        p = dn.loc[dn.groupby("underlying", observed=True)["oi"].idxmax()]
        parts.append(p[["underlying", "K", "oi"]]
                     .rename(columns={"K": "put_K", "oi": "put_oi"})
                     .set_index("underlying"))
    if not parts:
        return pd.DataFrame(columns=["underlying", "call_K", "call_oi",
                                     "put_K", "put_oi", "spot"])
    out = parts[0]
    for extra in parts[1:]:
        out = out.join(extra, how="outer")
    return out.reset_index()


def sessions_at_level(levels: list[float | None]) -> int:
    """How many snapshots, counting back from the newest, share the newest level.

    `levels` is oldest-first. Returns 0 when the newest level is unknown.
    """
    if not levels:
        return 0
    newest = levels[-1]
    if newest is None:
        return 0
    n = 0
    for v in reversed(levels):
        if v is not None and np.isclose(float(v), float(newest)):
            n += 1
        else:
            break
    return n


# ── (d) own-history percentile ───────────────────────────────────────────────

def net_gex_percentile(history: list[dict] | None, today_net_gex_bn: float | None) -> dict | None:
    """Where today's net dealer gamma sits inside the name's OWN stored daily record.

    `history` is the board payload's history[] (rows of {date, net_gex_bn, ...}).
    SESSION-FILTERED first: the store behind it carries weekend/holiday rows that
    repeat the previous close (13 of 36 rows for SPY as of 2026-07-29), and an
    unfiltered percentile double-counts them (#3721 class).

    Follows the house iv_rank idiom exactly (strictly-below share, n_days,
    low_confidence) so the two percentiles read the same way. Returns None when
    fewer than 5 session rows carry a value.
    """
    if today_net_gex_bn is None or not history:
        return None
    xs: list[float] = []
    dates: list[_dt.date] = []
    for h in history or []:
        v = h.get("net_gex_bn")
        d = _as_date(h.get("date"))
        if v is None or d is None or not nyse_calendar.is_session(d):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(fv):
            continue
        xs.append(fv)
        dates.append(d)
    if len(xs) < 5:
        return None
    try:
        today = float(today_net_gex_bn)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(today):
        return None
    pct = int(round(100.0 * sum(1 for v in xs if v < today) / len(xs)))
    start, end = min(dates).isoformat(), max(dates).isoformat()
    low_conf = len(xs) < PCTILE_LOW_CONFIDENCE_SESSIONS
    tail_en = (" The record is short, so read it as a rough placement."
               if low_conf else "")
    tail_zh = "记录较短，只能作为粗略定位。" if low_conf else ""
    # "sits above 0% of" is not a sentence a reader can use, and "above 100%" is worse.
    # The ends of the range get their own plain wording.
    span = f"{len(xs)} trading days, {start} to {end}"
    span_zh = f"{len(xs)} 个交易日，{start} 至 {end}"
    if pct <= 0:
        head_en = ("Today's net dealer gamma is at or below every one of this name's own "
                   f"stored daily readings ({span}).")
        head_zh = (f"今日净做市商 Gamma 不高于该标的自身任何一天的记录（{span_zh}）。")
    elif pct >= 100:
        head_en = ("Today's net dealer gamma is above every one of this name's own stored "
                   f"daily readings ({span}).")
        head_zh = (f"今日净做市商 Gamma 高于该标的自身每一天的记录（{span_zh}）。")
    else:
        head_en = (f"Today's net dealer gamma sits above {pct}% of this name's own stored "
                   f"daily readings ({span}).")
        head_zh = (f"今日净做市商 Gamma 高于该标的自身 {pct}% 的每日记录（{span_zh}）。")
    return {
        "pctile": pct,
        "n_sessions": len(xs),
        "low_confidence": low_conf,
        "window_start": start,
        "window_end": end,
        "note_en": head_en + tail_en,
        "note_zh": head_zh + tail_zh,
    }


def deep_history_context(root: str, reader: Callable[[str, str], Any] | None = None,
                         now: _dt.datetime | None = None) -> dict | None:
    """Descriptive window + spread of the multi-year index rebuild for `root`.

    DELIBERATELY NOT a percentile of today's value. The rebuild is a ThetaData
    reconstruction; today's payload value comes from the Cboe delayed chain. Placing
    one inside the other is the cross-source comparison engine/market_gamma refuses
    for exactly this reason (its SCALE NOTE), so this block reports the window and
    the spread and says plainly that today's reading is not placed inside it.

    Measured on the ACTUAL pair (reconstruction vs data/cboe/gex_<ROOT>, 12 shared dates,
    2026-07-29): SPY raw corr 0.9329 / same-spot 0.9956 n=8 / mean abs diff 2.0585 $bn;
    QQQ 0.7618 / 0.9933 n=7 / 1.2896; IWM 0.4850 / 0.9655 n=8 / 0.3366; DIA has no cboe
    store to compare against. Comparable context, not one distribution.

    Staleness is disclosed calmly in plain words — never as an alarm (§0.7).
    """
    root = str(root or "").upper()
    if root not in DEEP_HISTORY_ROOTS:
        return None
    if reader is None:
        from lib import store  # noqa: PLC0415
        reader = store.read
    try:
        hist = reader(_DEEP_HISTORY_GROUP, root)
    except Exception as e:  # noqa: BLE001 — context is a nicety, never fatal
        log.debug("positioning_persistence: deep history %s unreadable: %s", root, e)
        return None
    if hist is None or not len(hist) or "net_gex_bn" not in hist.columns:
        return None
    # SESSION-FILTER FIRST, then quantile. The rebuild really does carry non-session rows
    # (measured: one 2019-02-02 Saturday row in each of SPY/QQQ/IWM/DIA), and computing
    # n_sessions and the spread over the unfiltered series contradicted this function's
    # own contract — the numeric effect is small (SPY median -0.204 -> -0.200) but a
    # denominator that says "sessions" must count sessions.
    idx = pd.to_datetime(hist.index, errors="coerce")
    keep = [bool(pd.notna(d) and nyse_calendar.is_session(d.date())) for d in idx]
    if not any(keep):
        return None
    sub = hist.loc[keep]
    ng = pd.to_numeric(sub["net_gex_bn"], errors="coerce").dropna()
    if not len(ng):
        return None
    dates = [d.date() for d in pd.to_datetime(sub.index, errors="coerce") if pd.notna(d)]
    if not dates:
        return None
    start, end = min(dates), max(dates)
    behind = nyse_calendar.sessions_behind(end, now)
    stale = behind > DEEP_HISTORY_STALE_SESSIONS
    lag_en = (f" — {behind} trading sessions behind the latest close" if stale
              else " and is current")
    lag_zh = (f" — 比最近收盘落后 {behind} 个交易日" if stale else "，数据为最新")
    return {
        "root": root,
        "n_sessions": int(len(ng)),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "sessions_behind": int(behind),
        "stale": bool(stale),
        "net_gex_bn_min": _f(ng.min()),
        "net_gex_bn_p10": _f(ng.quantile(0.10)),
        "net_gex_bn_median": _f(ng.median()),
        "net_gex_bn_p90": _f(ng.quantile(0.90)),
        "net_gex_bn_max": _f(ng.max()),
        "note_en": (
            f"The multi-year rebuild for {root} covers {start.isoformat()} through "
            f"{end.isoformat()}{lag_en}. Today's reading comes from a different chain "
            "source, so it is not placed inside that window."),
        "note_zh": (
            f"{root} 的多年重建数据覆盖 {start.isoformat()} 至 {end.isoformat()}"
            f"{lag_zh}。今日读数来自另一个期权链来源，因此不放入该区间做百分位比较。"),
    }


# ── plain-word notes ─────────────────────────────────────────────────────────

def _young_window_note(store_start: _dt.date | None) -> tuple[str, str]:
    """(EN, ZH) young-window tails. EN sentences are space-joined; ZH is not —
    Simplified Chinese runs sentences together after the full-width stop."""
    if store_start is None:
        return "", ""
    s = store_start.isoformat()
    return (" " + _STORE_EPOCH_NOTE_EN.format(start=s),
            _STORE_EPOCH_NOTE_ZH.format(start=s))


def _gap_note(sessions_apart: int | None) -> tuple[str, str]:
    """(EN, ZH) tail when the two snapshots are NOT one session apart.

    Without this, a pair straddling a collector outage emits full "day-over-day" lists
    with nothing saying the two readings are weeks apart. Silent on the normal
    consecutive-session case so the copy stays short when there is nothing to say.
    """
    if sessions_apart is None or sessions_apart <= 1:
        return "", ""
    return (f" The two snapshots are {sessions_apart} trading sessions apart, not "
            "consecutive, so the change covers that whole stretch.",
            f"两次快照相隔 {sessions_apart} 个交易日，并不相邻，"
            "因此变化涵盖这整段时间。")


def _behind_note(sessions_behind: int | None, stale: bool) -> tuple[str, str]:
    """(EN, ZH) tail when the newest stored snapshot is behind the latest close.

    Calm, never an alarm (§0.7): a window statement. Silent when current, so a healthy
    collector adds no noise.
    """
    if not stale or sessions_behind is None or sessions_behind <= 0:
        return "", ""
    return (f" The newest stored snapshot is {sessions_behind} trading sessions behind "
            "the latest close.",
            f"最新的已存储快照比最近收盘落后 {sessions_behind} 个交易日。")


def rows_cross_the_board_price(rows: list[dict] | None, snapshot_spot: float | None,
                              board_spot: float | None) -> bool:
    """True when any emitted row reads ABOVE one price and NOT-ABOVE the other.

    This is the adjudicated DIRECTION condition, written as the exact sign comparison a
    reader performs rather than a range test: sign(K - snapshot_spot) != sign(K -
    board_spot), ties counted as not-above on both sides so the boundary K == spot is
    handled the same way `dist_pct` handles it (0 is not positive).

    Why it exists alongside the percentage threshold: measured 2026-07-29 across the whole
    board, 99 of 2,259 emitted cluster rows have an above/below reading that flips between
    the two prices, and the >2% distance threshold alone caught only 77 of them — the rest
    are strikes wedged between two prices that agree closely. (A further 5 rows LOOK
    flipped if you compare the ROUNDED `dist_pct` to the board price, but there the two
    prices are identical and `dist_pct` merely rounds to 0.0 — nothing to disclose.) A sign flip breaks the
    reader's mental model at ANY magnitude, so it triggers the note on its own. (A first
    pass used a strict `lo < K < hi` range test and left 4 rows uncovered, exactly the
    K-equals-one-of-the-prices boundary; the sign comparison has no such gap.)
    """
    if not rows:
        return False
    try:
        s, b = float(snapshot_spot), float(board_spot)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if not (np.isfinite(s) and np.isfinite(b)):
        return False
    for r in rows:
        k = r.get("K")
        if k is None:
            continue
        try:
            kf = float(k)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(kf):
            continue
        if (kf > s) != (kf > b):
            return True
    return False


def spot_divergence_note(snapshot_spot: float | None,
                         board_spot: float | None,
                         force: bool = False) -> tuple[str, str] | None:
    """(EN, ZH) disclosure when the snapshot source's price differs from the board's.

    The strike distances and the above/below-price split in these blocks are computed
    against the SNAPSHOT's own underlying price — single-source internal consistency is
    the whole point, and mixing the board's Cboe price into a Polygon-derived row would
    be the mixed-source class. But the payload's own top-level `spot` is the Cboe one,
    and the two really do diverge: over the 302 roots that emit a payload (2026-07-29),
    median 0.582%, 97 past 2%, worst 18.6% (UCTT 77.50 vs 95.25). A reader comparing
    `dist_pct` against the payload's `spot` finds the sign contradicted on 99 of 2,259
    emitted cluster rows. So say it, above a 2% threshold.

    `force` fires the note below the threshold — used when a row actually straddles the
    two prices (see rows_cross_the_board_price), which is the case a reader misreads.

    Returns None when there is nothing to disclose (either price missing, or agreement
    inside the threshold with no straddling row).
    """
    try:
        s, b = float(snapshot_spot), float(board_spot)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(s) and np.isfinite(b)) or b <= 0:
        return None
    pct = abs(s - b) / b * 100.0
    if pct <= SPOT_DIVERGENCE_PCT and not force:
        return None
    # Name which condition triggered, so a reader knows whether the concern is DISTANCE
    # (the prices are materially apart) or DIRECTION (a listed strike falls between them,
    # so above/below reads the opposite way against the board's price). Direction is the
    # one that actually breaks a mental model, so it gets the explicit sentence.
    flip_en = (" Some strikes below sit between the two prices, so above-or-below reads "
               "the other way round against this board's price."
               if force and pct <= SPOT_DIVERGENCE_PCT else "")
    flip_zh = ("下方部分行权价正好落在两个价格之间，"
               "因此以本板块价格衡量时，高于/低于的方向会相反。"
               if force and pct <= SPOT_DIVERGENCE_PCT else "")
    return (
        f"Strike distances here are measured against the snapshot source's price of "
        f"{_level_text(s)}, which differs from this board's price by {pct:.1f}%."
        + flip_en,
        f"此处的行权价距离以快照来源的价格 {_level_text(s)} 为基准，"
        f"与本板块价格相差 {pct:.1f}%。" + flip_zh,
    )


def _cluster_notes(state: str, prior: _dt.date | None, latest: _dt.date | None,
                   store_start: _dt.date | None, sessions_apart: int | None = None,
                   sessions_behind: int | None = None,
                   stale: bool = False) -> tuple[str, str]:
    """Plain-word EN/ZH pair for one of the five cluster states."""
    young_en, young_zh = _young_window_note(store_start)
    gap_en, gap_zh = _gap_note(sessions_apart)
    beh_en, beh_zh = _behind_note(sessions_behind, stale)
    tail_en, tail_zh = gap_en + beh_en + young_en, gap_zh + beh_zh + young_zh
    if state == "lit":
        return (
            f"Contract-by-contract open-interest change between the {prior} and {latest} "
            "chain snapshots. Counts of contracts added or closed at each strike — not a "
            "direction call." + tail_en,
            f"{prior} 与 {latest} 两次期权链快照之间逐张合约的未平仓量变化，"
            "显示各行权价新增或平掉的合约数量，不代表方向判断。" + tail_zh,
        )
    if state == "same_vintage":
        return (
            f"The {prior} and {latest} chain snapshots report identical open interest for "
            "this name, so no change can be measured yet." + tail_en,
            f"本标的在 {prior} 与 {latest} 两次期权链快照中的未平仓量完全相同，"
            "因此暂时测不出变化。" + tail_zh,
        )
    if state == "no_matched_contracts":
        # A root present in BOTH snapshots whose listed contracts do not overlap at all.
        # Reachable on the real store (2026-07-02 -> 2026-07-07: CRWD, 1 of 350 shared
        # roots). Falling through to the "absent" copy claimed no snapshots were stored
        # while the two snapshot dates sat non-null right beside it in the same block.
        return (
            f"Chain snapshots exist for this name on both {prior} and {latest}, but no "
            "single contract appears in both — the listed contracts turned over, so no "
            "open-interest change can be measured across them." + tail_en,
            f"本标的在 {prior} 与 {latest} 两次快照中都有期权链数据，"
            "但没有任何一张合约同时出现在两次快照中——挂牌合约已完全更替，"
            "因此无法测量两者之间的未平仓量变化。" + tail_zh,
        )
    if state == "one_snapshot":
        return (
            "Only one stored chain snapshot covers this name so far, so a day-over-day "
            "open-interest change cannot be measured yet." + tail_en,
            "目前只有一次期权链快照覆盖本标的，因此还无法测量隔日未平仓量变化。" + tail_zh,
        )
    if state == "one_of_pair":
        # In exactly ONE of the two compared snapshots, but present in older ones too —
        # so "only one snapshot covers this name" would be false. Say which is true.
        return (
            "Only one of the two most recent stored chain snapshots lists this name, so a "
            "change across the compared pair cannot be measured for it." + tail_en,
            "最近两次期权链快照中只有一次包含本标的，"
            "因此无法测量该对比区间内的未平仓量变化。" + tail_zh,
        )
    if state == "outside_pair":
        return (
            "Neither of the two most recent stored chain snapshots lists this name, "
            "though earlier snapshots do, so no current open-interest change is "
            "available for it." + tail_en,
            "最近两次期权链快照都不包含本标的（较早的快照有），"
            "因此目前无法提供其未平仓量变化。" + tail_zh,
        )
    if state == "failure":
        # A genuine read/build failure. Distinct from "not stored": the store may be
        # perfectly fine and simply unreadable this run, and saying "no snapshots are
        # stored" would send a reader looking for the wrong problem.
        return (OI_DELTA_UNAVAILABLE_EN, OI_DELTA_UNAVAILABLE_ZH)
    return (
        "No per-strike chain snapshots are stored for this name, so open-interest change "
        "is not available.",
        "本标的没有逐行权价期权链快照，因此无法提供未平仓量变化。",
    )


def _level_text(level: float | None) -> str:
    """Strike as a reader would write it: 800, not 800.0; 137.5 stays 137.5."""
    v = _f(level, 4)
    if v is None:
        return "—"
    return str(int(v)) if float(v).is_integer() else str(v)


# Basis of the wall comparison, stated once per block (B1c). The two walls are
# DIFFERENT constructions from DIFFERENT sources, so a False match is definitional, not
# a fault — measured 2026-07-29, False is the majority on both sides.
_WALL_BASIS_EN = (
    "This level is the heaviest open interest in the snapshot source's full contract "
    "list. The board's own call and put walls are dollar-gamma levels taken from a "
    "narrower window of a different chain source, so the two often land on different "
    "strikes.")
_WALL_BASIS_ZH = (
    "此水平取自快照来源完整合约列表中未平仓量最重的行权价。"
    "本板块自身的看涨/看跌墙是另一个期权链来源、在更窄区间内计算的美元 Gamma 水平，"
    "因此两者经常落在不同的行权价上。")


def _wall_notes(side_en: str, side_zh: str, level: float | None, held: int,
                covered: int, store_start: _dt.date | None,
                sessions_behind: int | None = None,
                stale: bool = False) -> tuple[str, str]:
    """(EN, ZH) for one wall side.

    Deliberately does NOT repeat the store-epoch sentence the cluster note carries:
    "N of M stored chain snapshots" plus the block's own window_start / window_end
    already state the window, and repeating the epoch three times per payload was
    ~250 wasted bytes x 622 files a night for no added honesty. It DOES carry the
    behind-the-close tail, because a reader of this block alone would otherwise read a
    stalled collector's last window as current.
    """
    if level is None or held <= 0:
        return (
            f"No {side_en} open-interest level is stored for this name yet.",
            f"本标的暂无{side_zh}未平仓量水平记录。",
        )
    lvl = _level_text(level)
    if held >= covered:
        head_en = (f"The heaviest {side_en} open interest has sat at {lvl} in every one of "
                   f"the {covered} stored chain snapshots, so it may have held longer than "
                   "the window kept.")
        head_zh = (f"{side_zh}未平仓量最重的行权价，在已存储的 {covered} 次期权链快照中"
                   f"每一次都落在 {lvl}，实际持续时间可能长于已保存的窗口。")
    else:
        head_en = (f"The heaviest {side_en} open interest has sat at {lvl} for the last "
                   f"{held} of {covered} stored chain snapshots.")
        head_zh = (f"{side_zh}未平仓量最重的行权价，在已存储的 {covered} 次期权链快照中，"
                   f"最近 {held} 次落在 {lvl}。")
    beh_en, beh_zh = _behind_note(sessions_behind, stale)
    return (
        head_en + " Open-interest size is a count of contracts, not a dealer position."
        + beh_en,
        head_zh + "未平仓量是合约数量，不是做市商持仓。" + beh_zh,
    )


# ── process-level derived store (built once, thread-safe) ────────────────────

class PositioningStore:
    """Derived, per-underlying positioning-persistence reads for one process.

    Built ONCE from a bounded set of chain snapshots, then held as small dicts.
    build_gex_board fans ~691 names across a ThreadPoolExecutor, so construction is
    guarded by a lock and every accessor is read-only afterwards.

    MEMORY, stated both ways because only one of them is the number that matters to the
    render box (measured 2026-07-29, 6-snapshot window, full 370-name store):
      * the DERIVED store is genuinely tiny — 0.73 MB pickled, ~5 MB of live Python
        objects after a gc.collect();
      * but the process RSS high-water rises ~+230-300 MB during the build and does NOT
        come back down (381 MB still resident after gc). pandas/pyarrow return freed
        arenas to their own allocator, not to the OS. So "the frames are dropped" is true
        about object lifetime and false about resident footprint — for the rest of the
        board run this module costs a few hundred MB of RSS, not a few hundred KB.
    WALL_WINDOW_SESSIONS is the lever: window 2 measured +171 MB, 6 +237 MB, 10 +243 MB.
    """

    def __init__(self, clusters: dict[str, dict], walls: dict[str, dict],
                 meta: dict, coverage: dict[str, tuple[int, int]] | None = None) -> None:
        self._clusters = clusters
        self._walls = walls
        self.meta = meta
        # {ROOT: (snapshots_of_the_compared_PAIR_listing_it, window_snapshots_listing_it)}
        # PER-ROOT coverage, because the store-wide counts cannot describe an individual
        # name. Without it every root outside the pair's INTERSECTION fell to the
        # store-wide fallback and claimed "no per-strike chain snapshots are stored for
        # this name" while a wall block derived from those very snapshots sat beside it.
        # Measured on the real store: 25 of 375 roots on the 2026-07-02 -> 07-07 pair, and
        # 346 of 356 on the 2026-06-18 -> 06-22 universe-expansion pair.
        self._coverage = coverage or {}

    def coverage(self, root: str) -> tuple[int, int]:
        """(pair_snapshots, window_snapshots) that list `root`."""
        return self._coverage.get(str(root or "").upper(), (0, 0))

    # -- accessors ---------------------------------------------------------
    def clusters(self, root: str) -> dict:
        key = str(root or "").upper()
        hit = self._clusters.get(key)
        if hit is not None:
            return dict(hit)
        state = self._fallback_state(key)
        en, zh = _cluster_notes(state, self.meta.get("prior_snapshot"),
                                self.meta.get("latest_snapshot"),
                                self.meta.get("store_start"),
                                self.meta.get("sessions_apart"),
                                self.meta.get("sessions_behind"),
                                bool(self.meta.get("stale")))
        # prior/latest_snapshot are NULL here on purpose. These fields describe the pair
        # THIS root's delta was computed from, and for a root the store does not cover
        # there is no such pair. Stamping the store-wide dates next to copy that says
        # "no snapshots are stored for this name" is the same self-contradiction the
        # no_matched_contracts state exists to fix — the window lives in meta.
        return {
            "new_oi": [], "exit_oi": [],
            "prior_snapshot": None,
            "latest_snapshot": None,
            "sessions_apart": None,
            "sessions_behind": self.meta.get("sessions_behind"),
            "stale": bool(self.meta.get("stale")),
            "matched_contracts": 0,
            "same_vintage": False,
            "snapshot_spot": None,
            "note_en": en, "note_zh": zh,
        }

    def _fallback_state(self, key: str) -> str:
        """Which honest-absence state applies to a root with no cluster entry.

        Driven by PER-ROOT coverage, not by the store-wide snapshot count:
          failure       — the build itself failed; the store may be fine and unreadable
          one_snapshot  — exactly one stored snapshot lists this name (literally true)
          one_of_pair   — in one of the two compared snapshots, and in older ones too
          outside_pair  — in neither compared snapshot, though earlier ones list it
          absent        — no stored snapshot lists it at all
        """
        if self.meta.get("degraded"):
            return "failure"
        pair, window = self.coverage(key)
        # No PAIR exists yet (empty store, or a single stored snapshot), so the
        # pair-relative wordings would be nonsense — only "one" or "none" apply.
        if int(self.meta.get("snapshots_compared") or 0) < 2:
            return "one_snapshot" if window >= 1 else "absent"
        if pair == 1:
            # "only one snapshot covers this name" is literally true only when no older
            # snapshot lists it either; otherwise say which pair side is missing.
            return "one_snapshot" if window <= 1 else "one_of_pair"
        if pair == 0:
            return "outside_pair" if window >= 1 else "absent"
        return "absent"

    def wall_persistence(self, root: str) -> dict | None:
        key = str(root or "").upper()
        hit = self._walls.get(key)
        return dict(hit) if hit is not None else None


def _iso(d: Any) -> str | None:
    dd = _as_date(d)
    return dd.isoformat() if dd is not None else None


_LOCK = threading.Lock()
_CACHE: PositioningStore | None = None


def reset_cache() -> None:
    """Drop the process cache (tests, and any caller that swaps the readers)."""
    global _CACHE
    with _LOCK:
        _CACHE = None


def load(chain_dates: Callable[[], list[_dt.date]] | None = None,
         read_chain: Callable[[_dt.date], pd.DataFrame | None] | None = None,
         window_sessions: int = WALL_WINDOW_SESSIONS,
         top_n: int = CLUSTER_TOP_N,
         use_cache: bool = True,
         now: _dt.datetime | None = None) -> PositioningStore:
    """Build (or return the cached) PositioningStore.

    Degrades honestly at every step: no chains dir, one snapshot only, a corrupt
    file, or a name absent from the store all yield empty lists plus a plain-word
    note — never an exception into the caller and never a fabricated zero.

    FAILURE IS MEMOISED TOO. gex_state calls this three times per root from three
    separate try/excepts, so at board scale (~555 emitted payloads) an exception out of
    _build used to mean ~1,665 full rebuilds — roughly +33 min on the render band, from
    a path that only ever produces the empty degraded answer. A raise now caches a
    DEGRADED store (whose copy says the change could not be READ, not that nothing is
    stored) and every later call returns it instantly. Exactly one ::warning per process.

    `now` is the clock seam for the staleness disclosure — injectable so a test can pin a
    date instead of skipping itself once the fixture dates age past the threshold.
    """
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE
    with _LOCK:
        if use_cache and _CACHE is not None:
            return _CACHE
        try:
            built = _build(chain_dates or default_chain_dates,
                           read_chain or default_read_chain,
                           window_sessions, top_n, now)
        except Exception as e:  # noqa: BLE001 — degrade once, never per-root
            print(f"::warning title=positioning-persistence-degraded::chain positioning "
                  f"reads unavailable this run ({type(e).__name__}: {e}) — open-interest "
                  f"clusters and wall persistence ship empty with a note", flush=True)
            log.warning("positioning_persistence: build failed, serving degraded store "
                        "for the rest of this process: %s", e, exc_info=True)
            built = _degraded_store(f"{type(e).__name__}: {e}", window_sessions)
        if use_cache:
            _CACHE = built
        return built


def _degraded_store(reason: str, window_sessions: int) -> PositioningStore:
    """An empty store whose copy says the change could not be READ.

    Deliberately NOT the "no snapshots are stored for this name" copy: the store may be
    perfectly intact and simply unreadable this run, and the two point an operator at
    different problems. `degraded: True` in meta routes every root to the failure state.
    """
    return PositioningStore({}, {}, {
        "source": "polygon_gex/chains",
        "store_start": None,
        "sessions_available": 0,
        "window_sessions": int(window_sessions),
        "sessions_covered": 0,
        "prior_snapshot": None,
        "latest_snapshot": None,
        "snapshots_compared": 0,
        "sessions_apart": None,
        "sessions_behind": None,
        "stale": False,
        "roots_with_clusters": 0,
        "roots_with_walls": 0,
        "dropped_bad_join_keys": 0,
        "degraded": True,
        "degraded_reason": reason,
    })


def _build(chain_dates: Callable[[], list[_dt.date]],
           read_chain: Callable[[_dt.date], pd.DataFrame | None],
           window_sessions: int, top_n: int,
           now: _dt.datetime | None = None) -> PositioningStore:
    try:
        dates = [d for d in (chain_dates() or []) if nyse_calendar.is_session(d)]
    except Exception as e:  # noqa: BLE001
        log.warning("positioning_persistence: chain date listing failed: %s", e)
        dates = []
    dates = sorted(dates)
    store_start = dates[0] if dates else None
    window = dates[-max(2, int(window_sessions)):] if dates else []

    # Per-date open-interest wall LEVELS (a few tuples per root), plus the two NEWEST
    # whole frames — all the delta needs. Every older frame is released as soon as its
    # walls are extracted, which bounds how many are LIVE at once; it does not shrink the
    # process RSS afterwards (see PositioningStore's MEMORY note — the allocator keeps
    # ~230-300 MB for the rest of the run). WALL_WINDOW_SESSIONS is the lever.
    wall_rows: dict[str, dict[_dt.date, tuple]] = {}
    kept: list[_dt.date] = []
    recent: list[tuple[_dt.date, pd.DataFrame]] = []
    dropped_keys = 0
    for d in window:
        raw = read_chain(d)
        if raw is None or raw.empty:
            continue
        try:
            norm = _normalise_chain(raw)
        except ChainShapeError as e:
            # A rescaled/odd snapshot is DROPPED with a loud line, never averaged in.
            print(f"::warning title=oi-chain-shape::{d.isoformat()} chain snapshot "
                  f"refused: {e}", flush=True)
            continue
        finally:
            del raw           # release the vendor-shaped frame before the wall pass
        if norm.empty:
            continue
        bad = int(norm.attrs.get("dropped_bad_join_keys", 0) or 0)
        if bad:
            dropped_keys += bad
            print(f"::warning title=oi-chain-join-keys::{d.isoformat()} chain snapshot "
                  f"dropped {bad} row(s) with a missing or duplicated contract id before "
                  f"the open-interest match", flush=True)
        kept.append(d)
        for r in oi_walls(norm).itertuples():
            wall_rows.setdefault(str(r.underlying), {})[d] = (
                _f(getattr(r, "call_K", None), 4),
                _f(getattr(r, "put_K", None), 4),
                _f(getattr(r, "spot", None)),
            )
        recent.append((d, norm))
        if len(recent) > 2:
            recent.pop(0)   # drops the last reference to an out-of-pair frame
        # NOT projected down further: the older half of the pair contributes only its
        # open interest to matched_oi_delta, but vintage_fingerprints ALSO needs its
        # underlying and spot, so the droppable columns are just K + is_call (~1 MB).
        del norm
    # ── freshness of the store itself (M1) ────────────────────────────────
    # The chain store is a DAILY collect step. A dead collector leaves a perfectly
    # self-consistent pair whose newest side is weeks old, and nothing in the block said
    # so — the same shape that let index_gex_history read as current for 18 sessions.
    latest_kept = kept[-1] if kept else None
    behind: int | None = None
    if latest_kept is not None:
        try:
            behind = int(nyse_calendar.sessions_behind(latest_kept, now))
        except Exception:  # noqa: BLE001 — a calendar hiccup must not drop the block
            behind = None
    stale = behind is not None and behind >= CHAIN_STALE_SESSIONS

    meta: dict[str, Any] = {
        "source": "polygon_gex/chains",
        "store_start": store_start,
        "sessions_available": len(dates),
        "window_sessions": int(window_sessions),
        "sessions_covered": len(kept),
        "prior_snapshot": None,
        "latest_snapshot": None,
        "snapshots_compared": len(kept),
        "sessions_apart": None,
        "sessions_behind": behind,
        "stale": bool(stale),
        "dropped_bad_join_keys": dropped_keys,
        "degraded": False,
    }

    # ── per-root coverage (drives the honest-absence state) ───────────────
    # window count first; the pair count is filled in below once the pair is known.
    window_cov: dict[str, int] = {r.upper(): len(by_date)
                                  for r, by_date in wall_rows.items()}
    pair_cov: dict[str, int] = {}

    # ── (a) clusters from the two newest SESSION snapshots ────────────────
    clusters: dict[str, dict] = {}
    if len(recent) >= 2:
        (prior_d, prior), (latest_d, latest) = recent[0], recent[1]
        meta["prior_snapshot"], meta["latest_snapshot"] = prior_d, latest_d
        meta["snapshots_compared"] = 2
        # How far apart the two readings actually are. 1 = consecutive sessions (the
        # normal case, disclosed silently); more means the pair straddles a gap and the
        # "day-over-day" framing would otherwise be a lie.
        apart = max(0, len(nyse_calendar.sessions_between(prior_d, latest_d)) - 1) or None
        meta["sessions_apart"] = apart
        prior_fp = vintage_fingerprints(prior)
        latest_fp = vintage_fingerprints(latest)
        same = same_vintage_mask(prior_fp, latest_fp)
        # The snapshot's OWN underlying price per root — the price dist_pct and the
        # above/below-price wall split are actually measured against. It was computed and
        # thrown away before; a reader had no way to know which price the row used.
        snap_spot = {str(k): _f(v) for k, v in latest_fp["spot"].items()}
        # PAIR coverage: how many of the two compared snapshots list each root. 2 =
        # comparable (the loop below handles it); 1 = only one side lists it, so there is
        # nothing to compare FOR THAT NAME even though the store holds both snapshots.
        prior_roots = {str(u).upper() for u in prior_fp.index}
        latest_roots = {str(u).upper() for u in latest_fp.index}
        for r in prior_roots | latest_roots:
            pair_cov[r] = int(r in prior_roots) + int(r in latest_roots)
        delta = matched_oi_delta(prior, latest)
        by_root = {str(u): g for u, g in delta.groupby("underlying", observed=True)} \
            if not delta.empty else {}
        roots = set(by_root) | {str(u) for u in same.index}
        common = set(same.index.astype(str))

        def _stamp(root: str) -> dict:
            return {
                "prior_snapshot": prior_d.isoformat(),
                "latest_snapshot": latest_d.isoformat(),
                "sessions_apart": apart,
                "sessions_behind": behind,
                "stale": bool(stale),
                "snapshot_spot": snap_spot.get(root),
            }

        for root in roots:
            if bool(same.get(root, False)):
                en, zh = _cluster_notes("same_vintage", prior_d, latest_d, store_start,
                                        apart, behind, stale)
                clusters[root.upper()] = {
                    "new_oi": [], "exit_oi": [], **_stamp(root),
                    "matched_contracts": 0, "same_vintage": True,
                    "note_en": en, "note_zh": zh,
                }
                continue
            g = by_root.get(root)
            if g is None or g.empty:
                # Present in BOTH snapshots (so it IS in the fingerprint intersection)
                # yet sharing no contract id — the listed universe turned over. This used
                # to fall through to the store-level "no snapshots are stored for this
                # name" copy while the two snapshot dates sat non-null beside it.
                # Reachable on the real store: 2026-07-02 -> 2026-07-07, CRWD (1 of 350).
                if root in common:
                    en, zh = _cluster_notes("no_matched_contracts", prior_d, latest_d,
                                            store_start, apart, behind, stale)
                    clusters[root.upper()] = {
                        "new_oi": [], "exit_oi": [], **_stamp(root),
                        "matched_contracts": 0, "same_vintage": False,
                        "note_en": en, "note_zh": zh,
                    }
                continue
            body = clusters_for_underlying(g, top_n)
            en, zh = _cluster_notes("lit", prior_d, latest_d, store_start,
                                    apart, behind, stale)
            clusters[root.upper()] = {
                **body, **_stamp(root),
                "matched_contracts": int(g["contracts"].sum()),
                "same_vintage": False,
                "note_en": en, "note_zh": zh,
            }
    elif len(kept) == 1:
        meta["latest_snapshot"] = kept[-1]

    # ── (b) wall persistence over the stored window ──────────────────────
    # Series are aligned to `kept` and padded with None for a snapshot that did not
    # cover the name, so a root that entered the universe mid-window cannot borrow
    # another root's session count.
    walls: dict[str, dict] = {}
    if kept:
        covered = len(kept)
        for root, by_date in wall_rows.items():
            calls = [by_date.get(d, (None, None, None))[0] for d in kept]
            puts = [by_date.get(d, (None, None, None))[1] for d in kept]
            c_held = sessions_at_level(calls)
            p_held = sessions_at_level(puts)
            c_lvl, p_lvl = calls[-1], puts[-1]
            c_en, c_zh = _wall_notes("call-side", "看涨", c_lvl, c_held, covered,
                                     store_start, behind, stale)
            p_en, p_zh = _wall_notes("put-side", "看跌", p_lvl, p_held, covered,
                                     store_start, behind, stale)
            walls[root.upper()] = {
                "window_sessions": int(window_sessions),
                "sessions_covered": covered,
                "window_start": kept[0].isoformat(),
                "window_end": kept[-1].isoformat(),
                "sessions_behind": behind,
                "stale": bool(stale),
                # The price the above/below-price split was actually taken against — the
                # snapshot source's own, not the board's. Newest snapshot that covered
                # this root.
                "snapshot_spot": next(
                    (by_date[d][2] for d in reversed(kept) if d in by_date), None),
                "basis_en": _WALL_BASIS_EN,
                "basis_zh": _WALL_BASIS_ZH,
                "call_side": {"level": c_lvl, "sessions_at_level": c_held,
                              "note_en": c_en, "note_zh": c_zh},
                "put_side": {"level": p_lvl, "sessions_at_level": p_held,
                             "note_en": p_en, "note_zh": p_zh},
            }

    coverage = {r: (pair_cov.get(r, 0), window_cov.get(r, 0))
                for r in set(pair_cov) | set(window_cov)}
    meta["roots_with_clusters"] = len(clusters)
    meta["roots_with_walls"] = len(walls)
    meta["roots_in_window"] = len(coverage)
    meta["roots_outside_pair"] = sum(1 for p, _w in coverage.values() if p < 2)
    meta["store_start"] = store_start
    log.info("positioning_persistence: %d session snapshots (%s..%s, %s apart, %s behind), "
             "clusters for %d roots, wall window %d snapshots for %d roots, "
             "%d bad join keys dropped",
             len(dates), meta["prior_snapshot"], meta["latest_snapshot"],
             meta["sessions_apart"], behind, len(clusters), len(kept), len(walls),
             dropped_keys)
    return PositioningStore(clusters, walls, meta, coverage)
