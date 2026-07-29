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
  * Open interest is a COUNT of contracts (integral, >= 0). `_normalise_chain` refuses
    a frame whose oi column looks normalised/fractional rather than a count, so a
    vendor or fixture shape change cannot silently rescale the delta.
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
WALL_WINDOW_SESSIONS = 6
# Top-N strikes per side in each cluster list. Keeps the per-name payload bounded.
CLUSTER_TOP_N = 4
# A stored daily record shorter than this is flagged low_confidence for percentiles.
PCTILE_LOW_CONFIDENCE_SESSIONS = 60
# The index rebuild is a weekly job; more than a week and a half of sessions behind
# is worth saying out loud (calmly — see note_en/note_zh, never an alarm).
DEEP_HISTORY_STALE_SESSIONS = 7
# Index roots the multi-year rebuild covers (scripts/build_index_gex_history.py).
DEEP_HISTORY_ROOTS = frozenset({"SPY", "QQQ", "IWM", "DIA"})
_DEEP_HISTORY_GROUP = "index_gex_history"

# Chain columns the reads need. Pruned hard — the daily file is ~4.6 MB on disk.
CHAIN_COLS = ["underlying", "strike_ticker", "K", "is_call", "oi", "spot"]

# First stored per-strike snapshot (data/polygon_gex/chains). Used for the young-window
# disclosure when the resolved history really does start at the beginning of the store.
_STORE_EPOCH_NOTE_EN = "Per-strike chain snapshots begin {start}, so this record is still short."
_STORE_EPOCH_NOTE_ZH = "逐行权价期权链快照自 {start} 起累积，记录仍然很短。"


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
    return ((j["contracts_a"] == j["contracts_b"])
            & np.isclose(j["oi_total_a"], j["oi_total_b"])
            & np.isclose(j["spot_a"], j["spot_b"]))


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
    return {
        "pctile": pct,
        "n_sessions": len(xs),
        "low_confidence": low_conf,
        "window_start": start,
        "window_end": end,
        "note_en": (
            f"Today's net dealer gamma sits above {pct}% of this name's own stored "
            f"daily readings ({len(xs)} trading days, {start} to {end})." + tail_en),
        "note_zh": (
            f"今日净做市商 Gamma 高于该标的自身 {pct}% 的每日记录"
            f"（{len(xs)} 个交易日，{start} 至 {end}）。" + tail_zh),
    }


def deep_history_context(root: str, reader: Callable[[str, str], Any] | None = None,
                         now: _dt.datetime | None = None) -> dict | None:
    """Descriptive window + spread of the multi-year index rebuild for `root`.

    DELIBERATELY NOT a percentile of today's value. The rebuild is a ThetaData
    reconstruction; today's payload value comes from the Cboe delayed chain. Placing
    one inside the other is the cross-source comparison engine/market_gamma refuses
    for exactly this reason (its SCALE NOTE), so this block reports the window and
    the spread and says plainly that today's reading is not placed inside it.

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
    ng = pd.to_numeric(hist["net_gex_bn"], errors="coerce").dropna()
    if not len(ng):
        return None
    idx = pd.to_datetime(hist.index, errors="coerce")
    dates = [d.date() for d in idx if pd.notna(d) and nyse_calendar.is_session(d.date())]
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


def _cluster_notes(state: str, prior: _dt.date | None, latest: _dt.date | None,
                   store_start: _dt.date | None) -> tuple[str, str]:
    """Plain-word EN/ZH pair for one of the four cluster states."""
    young_en, young_zh = _young_window_note(store_start)
    if state == "lit":
        return (
            f"Contract-by-contract open-interest change between the {prior} and {latest} "
            "chain snapshots. Counts of contracts added or closed at each strike — not a "
            "direction call." + young_en,
            f"{prior} 与 {latest} 两次期权链快照之间逐张合约的未平仓量变化，"
            "显示各行权价新增或平掉的合约数量，不代表方向判断。" + young_zh,
        )
    if state == "same_vintage":
        return (
            f"The {prior} and {latest} chain snapshots report identical open interest for "
            "this name, so no change can be measured yet." + young_en,
            f"本标的在 {prior} 与 {latest} 两次期权链快照中的未平仓量完全相同，"
            "因此暂时测不出变化。" + young_zh,
        )
    if state == "one_snapshot":
        return (
            "Only one stored chain snapshot covers this name so far, so a day-over-day "
            "open-interest change cannot be measured yet." + young_en,
            "目前只有一次期权链快照覆盖本标的，因此还无法测量隔日未平仓量变化。" + young_zh,
        )
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


def _wall_notes(side_en: str, side_zh: str, level: float | None, held: int,
                covered: int, store_start: _dt.date | None) -> tuple[str, str]:
    """(EN, ZH) for one wall side.

    Deliberately does NOT repeat the store-epoch sentence the cluster note carries:
    "N of M stored chain snapshots" plus the block's own window_start / window_end
    already state the window, and repeating the epoch three times per payload was
    ~250 wasted bytes x 622 files a night for no added honesty.
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
    return (
        head_en + " Open-interest size is a count of contracts, not a dealer position.",
        head_zh + "未平仓量是合约数量，不是做市商持仓。",
    )


# ── process-level derived store (built once, thread-safe) ────────────────────

class PositioningStore:
    """Derived, per-underlying positioning-persistence reads for one process.

    Built ONCE from a bounded set of chain snapshots and then held as small dicts —
    the frames are dropped, so steady-state memory is a few hundred kilobytes.
    build_gex_board fans ~691 names across a ThreadPoolExecutor, so construction is
    guarded by a lock and every accessor is read-only afterwards.
    """

    def __init__(self, clusters: dict[str, dict], walls: dict[str, dict],
                 meta: dict) -> None:
        self._clusters = clusters
        self._walls = walls
        self.meta = meta

    # -- accessors ---------------------------------------------------------
    def clusters(self, root: str) -> dict:
        key = str(root or "").upper()
        hit = self._clusters.get(key)
        if hit is not None:
            return dict(hit)
        state = "one_snapshot" if self.meta.get("snapshots_compared") == 1 else "absent"
        en, zh = _cluster_notes(state, self.meta.get("prior_snapshot"),
                                self.meta.get("latest_snapshot"),
                                self.meta.get("store_start"))
        return {
            "new_oi": [], "exit_oi": [],
            "prior_snapshot": _iso(self.meta.get("prior_snapshot")),
            "latest_snapshot": _iso(self.meta.get("latest_snapshot")),
            "matched_contracts": 0,
            "same_vintage": False,
            "note_en": en, "note_zh": zh,
        }

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
         use_cache: bool = True) -> PositioningStore:
    """Build (or return the cached) PositioningStore.

    Degrades honestly at every step: no chains dir, one snapshot only, a corrupt
    file, or a name absent from the store all yield empty lists plus a plain-word
    note — never an exception into the caller and never a fabricated zero.
    """
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE
    with _LOCK:
        if use_cache and _CACHE is not None:
            return _CACHE
        built = _build(chain_dates or default_chain_dates,
                       read_chain or default_read_chain,
                       window_sessions, top_n)
        if use_cache:
            _CACHE = built
        return built


def _build(chain_dates: Callable[[], list[_dt.date]],
           read_chain: Callable[[_dt.date], pd.DataFrame | None],
           window_sessions: int, top_n: int) -> PositioningStore:
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
    # walls are extracted: keeping the whole window resident measured ~180 MB against
    # ~60 MB for the rolling pair, and the derived output is a few hundred kilobytes
    # either way. WALL_WINDOW_SESSIONS is the lever if the peak ever needs to come down.
    wall_rows: dict[str, dict[_dt.date, tuple]] = {}
    kept: list[_dt.date] = []
    recent: list[tuple[_dt.date, pd.DataFrame]] = []
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
    meta: dict[str, Any] = {
        "source": "polygon_gex/chains",
        "store_start": store_start,
        "sessions_available": len(dates),
        "window_sessions": int(window_sessions),
        "sessions_covered": len(kept),
        "prior_snapshot": None,
        "latest_snapshot": None,
        "snapshots_compared": len(kept),
    }

    # ── (a) clusters from the two newest SESSION snapshots ────────────────
    clusters: dict[str, dict] = {}
    if len(recent) >= 2:
        (prior_d, prior), (latest_d, latest) = recent[0], recent[1]
        meta["prior_snapshot"], meta["latest_snapshot"] = prior_d, latest_d
        meta["snapshots_compared"] = 2
        same = same_vintage_mask(vintage_fingerprints(prior), vintage_fingerprints(latest))
        delta = matched_oi_delta(prior, latest)
        by_root = {str(u): g for u, g in delta.groupby("underlying", observed=True)} \
            if not delta.empty else {}
        roots = set(by_root) | {str(u) for u in same.index}
        for root in roots:
            is_same = bool(same.get(root, False))
            if is_same:
                en, zh = _cluster_notes("same_vintage", prior_d, latest_d, store_start)
                clusters[root.upper()] = {
                    "new_oi": [], "exit_oi": [],
                    "prior_snapshot": prior_d.isoformat(),
                    "latest_snapshot": latest_d.isoformat(),
                    "matched_contracts": 0,
                    "same_vintage": True,
                    "note_en": en, "note_zh": zh,
                }
                continue
            g = by_root.get(root)
            if g is None or g.empty:
                continue
            body = clusters_for_underlying(g, top_n)
            en, zh = _cluster_notes("lit", prior_d, latest_d, store_start)
            clusters[root.upper()] = {
                **body,
                "prior_snapshot": prior_d.isoformat(),
                "latest_snapshot": latest_d.isoformat(),
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
            c_en, c_zh = _wall_notes("call-side", "看涨", c_lvl, c_held, covered, store_start)
            p_en, p_zh = _wall_notes("put-side", "看跌", p_lvl, p_held, covered, store_start)
            walls[root.upper()] = {
                "window_sessions": int(window_sessions),
                "sessions_covered": covered,
                "window_start": kept[0].isoformat(),
                "window_end": kept[-1].isoformat(),
                "call_side": {"level": c_lvl, "sessions_at_level": c_held,
                              "note_en": c_en, "note_zh": c_zh},
                "put_side": {"level": p_lvl, "sessions_at_level": p_held,
                             "note_en": p_en, "note_zh": p_zh},
            }

    meta["roots_with_clusters"] = len(clusters)
    meta["roots_with_walls"] = len(walls)
    meta["store_start"] = store_start
    log.info("positioning_persistence: %d session snapshots (%s..%s), clusters for %d "
             "roots, wall window %d snapshots for %d roots",
             len(dates), meta["prior_snapshot"], meta["latest_snapshot"],
             len(clusters), len(kept), len(walls))
    return PositioningStore(clusters, walls, meta)
