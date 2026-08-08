"""Group Pulse (GR0) — basket-level PARTICIPATION / DIRECTION / ARC read plane.

AUTHORITY
=========
    tier            : display
    authority       : context_only
    may_rank        : False        may_gate    : False
    may_size        : False        may_escalate: False

This organ prints WHAT A BASKET IS DOING RIGHT NOW — how many of its members are
actually moving, whether they are moving the same way, and where the group sits in
a washout->advance arc.  It is CONTEXT, never authority: nothing here gates an
entry, ranks a basket against another, sizes a position, or escalates an alert, and
the payload deliberately contains NO fused score / rank / heat number of any kind
(program law R-TIL-3; pinned by tests/test_group_pulse_tripwire.py, which fails on
any key matching score|rank|heat anywhere in the artifact).

It is an ASSEMBLER over organs that already exist, not a new scorer (R-TIL-9):

    engine.group_flow._mean_pairwise_corr   cohesion (mean pairwise correlation)
    engine.group_flow.sign_agreement        directional consensus (added there, GR0)
    engine.group_flow._causal_z             trailing z-score convention
    engine.coiled.washout_ctx_detail        per-member capitulation + trough DATE
                                            (added there additively, GR0)
    engine.weinstein_stage.classify         per-member stage 1/2/3/4
    engine.baskets  / engine.us_basket_turn dated-membership + EW-level conventions

DATA PLANE
==========
    data/baskets/membership.json        the basket registry; a member is LIVE at
                                        `as_of` when added <= as_of < removed
    data/baskets/ohlcv/<T>.parquet      member close AND volume.  This is the only
                                        store carrying VOLUME for the whole basket
                                        universe (the breadth close caches are
                                        close-only), so the activity volume leg
                                        requires it.
    data/yahoo/SPY.parquet              the benchmark (via lib.store.read("yahoo",
                                        "SPY")["close"]) — the same SPY series
                                        engine/baskets.py and engine/group_flow.py
                                        benchmark against, so "SPY-adjusted" means
                                        the same thing on every basket surface.

OUTPUTS
=======
    site/basketdata/pulse.json          {basket_id: group_pulse.v1}, one object per
                                        US basket.  Written in ANY lane (it is a
                                        display snapshot).
    data/group_pulse/episodes.parquet   append-only participation-episode ledger,
                                        advanced ONLY by the nightly lane
                                        (engine.ledger_lane.nightly_advance_enabled;
                                        house law — nightly is the sole advancer of
                                        forward ledgers, intraday lanes discard).

DEFINITIONS (deterministic; every threshold is a module constant below)
======================================================================
MEMBER ACTIVITY (per member, per session).  A member is ACTIVE on a session when
EITHER leg fires:

    return leg  |SPY-adjusted daily return| z-score >= ACTIVITY_Z_MIN (1.5) against
                that member's OWN trailing ACTIVITY_LOOKBACK_D (63) sessions.  The
                z-score is `engine.group_flow._causal_z` applied to the ABSOLUTE
                SPY-adjusted return — i.e. "is today's move unusually LARGE for this
                name", direction-free by construction (direction is the `direction`
                block's job, not participation's).  The 63-session window ENDS at
                the session being scored (inclusive), matching `_causal_z`; it is
                causal — no bar after t enters t's score.
    volume leg  volume >= ACTIVITY_VOL_MULT (1.5) x that member's own trailing
                63-session MEDIAN volume.

    A member with no usable volume history is scored on the RETURN LEG ONLY and is
    counted under `participation.activity_basis.ret_only`; a member with both legs
    available is counted under `ret_and_volume`.  Those two counts partition the
    ACTIVE members and therefore sum to `activity_n`.

COVERAGE.  A live member is COVERED at `as_of` when its activity read exists there
(a readable tape whose 63-session return-leg z-score is non-null on that session).
A live member with no tape, or with a tape that stops before `as_of`, is live but
NOT covered, and the hole is printed in `coverage_warnings` — never filled in.

DENOMINATORS (why the shares do not all divide by the same n).  Each cross-sectional
stat divides by the set that could actually answer it, and each carries its own n so
the divide is reconstructible:

    activity_share          activity_n / n_covered
    trend_share_50d/200d    over covered members that HAVE that MA (a 40-session
                            IPO has no 200d MA; it is not a member below its MA)
    agreement_pct           over ACTIVE members (|net sign| / n_active), 0.0 when
                            n_active == 0, in which case `sign` is "mixed"
    cohesion                mean pairwise correlation of COVERED members' returns
                            over group_flow's `corr_window_d` (default 40 sessions)
    median_move_spy_adj,
    strongest / weakest     over COVERED members.  All three are on the SPY-ADJUSTED
                            basis — the whole `direction` block is one basis, so a
                            surface can label it "vs SPY" once and be right.
    washed_out_share        washed_out_n / (covered members with a NON-NULL washout
                            read).  `washout_ctx` needs 308 sessions, so a young
                            member is unknown, not un-washed-out.
    reclaimed_20d_share     over the WASHED-OUT members (denominator washed_out_n)
    stage2_share/stage4_share  over covered members with a non-null stage read

ARC LADDER (first match wins; the coverage floors are checked FIRST):

    floors : n_covered >= ARC_MIN_COVERED (5) AND
             n_covered / n_members >= ARC_MIN_COVERED_FRACTION (0.6)
             else state = "insufficient_coverage"
    1 washout_in_progress               washed_out_share >= 0.5 AND
                                        capitulation_median_age_d <= 5
    2 washout_complete_awaiting_reclaim washed_out_share >= 0.5 AND age > 5 AND
                                        reclaimed_20d_share < 0.5
    3 turning                           washed_out_share >= 0.5 AND
                                        reclaimed_20d_share >= 0.5
    4 advancing                         stage2_share >= 0.5 AND trend_share_50d >= 0.6
    5 distributing                      stage4_share >= 0.4 AND trend_share_50d < 0.5
    6 quiet                             otherwise

`capitulation_median_age_d` is the MEDIAN number of TRADING SESSIONS since the
capitulation trough across the washed-out members (the contract key name is frozen;
the unit is sessions, not calendar days).

`arc.null_disclosure` is the literal string "oracle_p8": sector-grain washout->turn
printed NULL as a STANDALONE signal (Oracle P8), and consumers must render the
standing disclosure beside any arc state.  This plane is a different construction —
basket grain, display tier, no entry trigger — and retains the washout read as
CONTEXT/confluence input, which a standalone null never forbids.

EPISODES.  A basket-day is ACTIVE when activity_share >= EPISODE_ENTER_SHARE (0.5)
AND activity_n >= EPISODE_MIN_ACTIVE (3).  Once an episode is open the bar drops to
EPISODE_EXIT_SHARE (0.35) — hysteresis, so a single soft session does not chop an
episode in two.  Active days separated by <= EPISODE_MAX_GAP (2) inactive sessions
belong to the SAME episode; EPISODE_CLOSE_AFTER (3) consecutive inactive sessions
closes it at its last active session.  `persistence_share` = members active in EVERY
active session / members active in at least one.

    The open episode's row is PROVISIONAL and is recomputed on every advance.  A row
    with closed=True is IMMUTABLE — later advances read it back and re-emit it
    verbatim, never recompute it (provisional-bucket law; pinned by
    tests/test_group_pulse_episodes.py::test_closed_rows_are_immutable).

STAGE SOURCE (disclosed choice).  Stages come from `engine.weinstein_stage.classify`
run live over the member tape (~19s for the ~706-name basket universe, measured on
the render host).  The committed board `site/stagedata/stage_board_weekly.json`
carries the same field for 699/708 members and would cost ~0.5s, but it is written
by `build_stage_analysis`, which runs AFTER `build_baskets` in the nightly ORDER
(.github/workflows/daily.yml) — reading it would make every stage share one session
stale and would couple this organ to a build ordering it does not control.  The
live path was chosen for freshness and independence; it fits the budget.

DEGRADATION.  Every input is optional.  A missing benchmark, a missing tape, a short
history, an unreadable ledger — each degrades the affected field to null and appends
a `coverage_warnings` code.  Nothing here fabricates a value and nothing here raises
into the nightly.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from engine.coiled import washout_ctx_detail
from engine.group_flow import _causal_z, _cfg as _flow_cfg, _mean_pairwise_corr, sign_agreement
from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

log = logging.getLogger(__name__)

SCHEMA = "group_pulse.v1"

#: Authority block (invariant — matches the module docstring and the synapse tier).
AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "authority": "context_only",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

#: Standing expected-NULL disclosure key carried on every arc block.  Consumers
#: render the standing sector-grain washout->turn null beside the state.
ARC_NULL_DISCLOSURE = "oracle_p8"

# ── member ACTIVITY ──────────────────────────────────────────────────────────
ACTIVITY_LOOKBACK_D: int = 63       # own trailing window for both legs
ACTIVITY_Z_MIN: float = 1.5         # |spy-adj ret| z-score bar (return leg)
ACTIVITY_VOL_MULT: float = 1.5      # x own trailing-63d median volume (volume leg)

# ── trend / reclaim moving averages (engine.group_flow breadth convention:
#    rolling(N, min_periods=N//2).mean(), share of members with close > MA) ────
TREND_MA_FAST: int = 50
TREND_MA_SLOW: int = 200
RECLAIM_MA: int = 20

# ── direction ────────────────────────────────────────────────────────────────
#: |net sign| / n_active at or above this prints an "up"/"down" label; below it the
#: cross-section is called "mixed".  0.5 == a 75/25 split.  A LABEL, not a gate.
SIGN_AGREEMENT_MIN: float = 0.5

# ── arc ladder ───────────────────────────────────────────────────────────────
ARC_MIN_COVERED: int = 5
ARC_MIN_COVERED_FRACTION: float = 0.6
ARC_WASHOUT_SHARE_MIN: float = 0.5
ARC_CAPIT_FRESH_SESSIONS: int = 5
ARC_RECLAIM_SHARE_MIN: float = 0.5
ARC_STAGE2_SHARE_MIN: float = 0.5
ARC_TREND50_ADVANCING_MIN: float = 0.6
ARC_STAGE4_SHARE_MIN: float = 0.4
ARC_TREND50_DISTRIBUTING_MAX: float = 0.5

# ── episodes ─────────────────────────────────────────────────────────────────
EPISODE_ENTER_SHARE: float = 0.5
EPISODE_EXIT_SHARE: float = 0.35    # hysteresis: sustains an OPEN episode only
EPISODE_MIN_ACTIVE: int = 3         # activity_n floor for an active basket-day
EPISODE_MAX_GAP: int = 2            # inactive sessions an episode may bridge
EPISODE_CLOSE_AFTER: int = 3        # consecutive inactive sessions that close it
EPISODE_STATE_DELTA: float = 0.10   # activity_share move that reads strengthening/cooling

#: Basket-id prefixes owned by the non-US planes (engine/us_basket_turn._NON_US_PREFIXES).
NON_US_PREFIXES: tuple[str, ...] = ("cn_", "hk_", "ca_")

#: Member price store — the ONE rung carrying volume for the whole basket universe.
MEMBER_STORE_REL: tuple[str, ...] = ("baskets", "ohlcv")

_LEDGER_REL: tuple[str, ...] = ("group_pulse", "episodes.parquet")
_SITE_REL: tuple[str, ...] = ("basketdata", "pulse.json")

#: Frozen ledger column order (also the parquet column order).
EPISODE_COLUMNS: tuple[str, ...] = (
    "basket_id", "episode_id", "start_date", "end_date", "sessions_active",
    "sessions_span", "members_ever_active", "members_persisted",
    "persistence_share", "closed", "advanced_at",
)

_ARC_STATES: frozenset[str] = frozenset({
    "washout_in_progress", "washout_complete_awaiting_reclaim", "turning",
    "advancing", "distributing", "quiet", "insufficient_coverage",
})
_SIGN_STATES: frozenset[str] = frozenset({"up", "down", "mixed"})
_STATE_CHANGES: frozenset[str] = frozenset({"strengthening", "steady", "cooling", "quiet"})


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _r(x: Any, nd: int = 4) -> float | None:
    """Round to `nd` places, mapping NaN/inf/None to None (JSON-safe)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _iso(d: Any) -> str | None:
    if d is None:
        return None
    try:
        ts = pd.Timestamp(d)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def _share(num: int, den: int) -> float | None:
    return None if den <= 0 else float(num) / float(den)


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

def load_membership(data_root: Path) -> dict[str, dict]:
    """US baskets from data/baskets/membership.json (non-US prefixes filtered out).

    A membership failure yields a ZERO-basket artifact, which is a louder failure
    than any per-basket hole — so it is a bare-print GitHub annotation, not a log
    record (this module runs inside an Actions step via scripts/build_baskets.py,
    and GitHub only parses a `::` that STARTS the line).
    """
    mp = data_root / "baskets" / "membership.json"
    if not mp.exists():
        print(f"::warning title=group-pulse::membership.json not found at {mp} "
              f"— 0 baskets in pulse.json for this run", flush=True)
        return {}
    try:
        raw = json.loads(mp.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"::warning title=group-pulse::membership.json unreadable ({e}) "
              f"— 0 baskets in pulse.json for this run", flush=True)
        return {}
    baskets = raw.get("baskets") or {}
    if isinstance(baskets, list):
        baskets = {b["id"]: b for b in baskets if b.get("id")}
    return {bid: b for bid, b in sorted(baskets.items())
            if not any(str(bid).startswith(p) for p in NON_US_PREFIXES)}


def basket_tickers(baskets: dict[str, dict]) -> list[str]:
    """Every ticker referenced by any basket, deterministically ordered."""
    return sorted({str(m["ticker"]) for b in baskets.values()
                   for m in (b.get("members") or []) if m.get("ticker")})


def load_member_tape(tickers: Sequence[str],
                     data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """(closes, volumes, missing) from data/baskets/ohlcv/<T>.parquet.

    Both frames share one column set and one union DatetimeIndex.  A ticker with no
    file, an unreadable file, or no usable `close` is returned in `missing` and is
    absent from both frames — never a fabricated column.
    """
    cl: dict[str, pd.Series] = {}
    vo: dict[str, pd.Series] = {}
    missing: list[str] = []
    base = data_root.joinpath(*MEMBER_STORE_REL)
    for t in tickers:
        p = base / f"{t}.parquet"
        if not p.exists():
            missing.append(t)
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns or df.empty:
                missing.append(t)
                continue
            df.index = pd.DatetimeIndex(pd.to_datetime(df.index))
            df = df[~df.index.duplicated(keep="last")].sort_index()
            c = df["close"].astype("float64")
            if c.dropna().empty:
                missing.append(t)
                continue
            cl[t] = c
            if "volume" in df.columns:
                v = df["volume"].astype("float64")
                # a zero/negative print is a data hole, not a quiet tape
                vo[t] = v.where(v > 0)
        except Exception as e:  # noqa: BLE001 — one bad file is never fatal
            log.debug("group_pulse: member tape %s unreadable: %s", t, e)
            missing.append(t)
    if not cl:
        return pd.DataFrame(), pd.DataFrame(), missing
    closes = pd.concat(cl, axis=1).sort_index()
    volumes = pd.concat(vo, axis=1).sort_index() if vo else pd.DataFrame(index=closes.index)
    volumes = volumes.reindex(index=closes.index, columns=closes.columns)
    return closes, volumes, missing


def load_benchmark(data_root: Path) -> pd.Series | None:
    """SPY close — the same benchmark engine/baskets.py and engine/group_flow.py use."""
    try:
        from lib import store
        df = store.read("yahoo", "SPY")
        if df is not None and "close" in df.columns:
            s = df["close"].astype("float64").dropna()
            if not s.empty:
                return s
    except Exception as e:  # noqa: BLE001
        log.debug("group_pulse: store.read SPY failed: %s", e)
    p = data_root / "yahoo" / "SPY.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if "close" in df.columns:
                df.index = pd.DatetimeIndex(pd.to_datetime(df.index))
                s = df["close"].astype("float64").dropna().sort_index()
                if not s.empty:
                    return s
        except Exception as e:  # noqa: BLE001
            log.debug("group_pulse: SPY parquet unreadable: %s", e)
    return None


# ---------------------------------------------------------------------------
# member panel — every per-member leg, computed ONCE for the whole universe
# ---------------------------------------------------------------------------

def build_member_panel(closes: pd.DataFrame,
                       volumes: pd.DataFrame | None,
                       bench_close: pd.Series | None) -> dict[str, Any]:
    """Vectorise every per-member leg once across the FULL close matrix.

    Cost discipline: each leg is one frame-wide rolling op, so adding a basket costs
    a boolean sum, not a member re-read.  Returns a dict of aligned frames:

        closes, spy_adj, activity_z, vol_ratio, covered, active, vol_leg,
        above_ma20 / above_ma50 / above_ma200 (+ their `has_ma*` availability masks)
    """
    idx = closes.index
    rets = closes.pct_change(fill_method=None)
    if bench_close is not None and not bench_close.empty:
        bench_ret = bench_close.reindex(idx).ffill().pct_change(fill_method=None)
        spy_adj = rets.sub(bench_ret, axis=0)
    else:                                   # benchmark hole: fall back to RAW returns
        spy_adj = rets

    activity_z = _causal_z(spy_adj.abs(), ACTIVITY_LOOKBACK_D)

    if volumes is not None and not volumes.empty:
        vol_med = volumes.rolling(ACTIVITY_LOOKBACK_D,
                                  min_periods=ACTIVITY_LOOKBACK_D).median()
        vol_ratio = volumes / vol_med.replace(0.0, np.nan)
    else:
        vol_ratio = pd.DataFrame(np.nan, index=idx, columns=closes.columns)

    covered = activity_z.notna()
    vol_leg = vol_ratio.notna()
    active = covered & ((activity_z >= ACTIVITY_Z_MIN) | (vol_ratio >= ACTIVITY_VOL_MULT))

    out: dict[str, Any] = {
        "closes": closes, "rets": rets, "spy_adj": spy_adj,
        "activity_z": activity_z, "vol_ratio": vol_ratio, "covered": covered,
        "active": active, "vol_leg": vol_leg, "index": idx,
    }
    for key, win in (("ma20", RECLAIM_MA), ("ma50", TREND_MA_FAST), ("ma200", TREND_MA_SLOW)):
        ma = closes.rolling(win, min_periods=max(1, win // 2)).mean()
        out[f"has_{key}"] = ma.notna() & closes.notna()
        out[f"above_{key}"] = closes > ma
    return out


def member_washouts(closes: pd.DataFrame) -> dict[str, dict | None]:
    """Per-member capitulation read via engine.coiled.washout_ctx_detail.

    The detail form is what buys the ARC block its age leg: the bool alone cannot
    tell "capitulated 3 sessions ago" from "capitulated 60 sessions ago".
    """
    return {t: washout_ctx_detail(closes[t].dropna()) for t in closes.columns}


def member_stages(closes: pd.DataFrame,
                  volumes: pd.DataFrame | None,
                  bench_close: pd.Series | None) -> dict[str, int | None]:
    """Per-member Weinstein stage via engine.weinstein_stage.classify (see the
    module docstring's STAGE SOURCE note for why this is computed, not read)."""
    try:
        from engine import weinstein_stage
    except Exception as e:  # noqa: BLE001 — stage shares degrade to null
        log.warning("group_pulse: weinstein_stage unavailable: %s", e)
        return {}
    if bench_close is None or bench_close.empty:
        return {}
    out: dict[str, int | None] = {}
    for t in closes.columns:
        try:
            c = closes[t].dropna()
            v = None
            if volumes is not None and t in volumes.columns:
                v = volumes[t].dropna()
                if v.empty:
                    v = None
            res = weinstein_stage.classify(c, v, bench_close)
            st = res.get("stage") if isinstance(res, dict) else None
            out[t] = int(st) if st in (1, 2, 3, 4) else None
        except Exception as e:  # noqa: BLE001 — one bad name never sinks the sweep
            log.debug("group_pulse: stage for %s failed: %s", t, e)
            out[t] = None
    return out


# ---------------------------------------------------------------------------
# membership masks + the per-basket daily participation series
# ---------------------------------------------------------------------------

def live_members(basket: dict, as_of: pd.Timestamp) -> list[str]:
    """Members live at `as_of` — added <= as_of < removed."""
    out: list[str] = []
    for m in (basket.get("members") or []):
        t = m.get("ticker")
        if not t:
            continue
        added = m.get("added")
        if added and pd.Timestamp(added) > as_of:
            continue
        removed = m.get("removed")
        if removed and pd.Timestamp(removed) <= as_of:
            continue
        out.append(str(t))
    return sorted(set(out))


def membership_mask(basket: dict, idx: pd.DatetimeIndex,
                    columns: Sequence[str]) -> pd.DataFrame:
    """Dated-membership boolean frame (idx x columns) — added <= d < removed.

    Same [added, removed) convention as engine/baskets._ew_level and
    engine/us_basket_turn.ew_level_from_closes, so a member enters and leaves this
    plane on exactly the sessions it enters and leaves the basket's level.
    """
    cols = [c for c in columns]
    mask = pd.DataFrame(False, index=idx, columns=cols)
    present = set(cols)
    arr = idx.to_numpy()
    for m in (basket.get("members") or []):
        t = m.get("ticker")
        if not t or t not in present:
            continue
        a = np.ones(len(idx), dtype=bool)
        if m.get("added"):
            a &= arr >= np.datetime64(pd.Timestamp(m["added"]).to_datetime64())
        if m.get("removed"):
            a &= arr < np.datetime64(pd.Timestamp(m["removed"]).to_datetime64())
        mask[t] = mask[t].to_numpy() | a
    return mask


def basket_daily_participation(mask: pd.DataFrame, panel: dict) -> pd.DataFrame:
    """Per-session n_members / n_covered / activity_n / activity_share for one basket.

    This is the episode machine's ONLY input, and it is a pure frame op over the
    shared panel — one basket costs three boolean sums, not a member re-read.
    """
    cols = list(mask.columns)
    covered = panel["covered"].reindex(columns=cols, fill_value=False) & mask
    active = panel["active"].reindex(columns=cols, fill_value=False) & mask
    n_members = mask.sum(axis=1).astype("int64")
    n_covered = covered.sum(axis=1).astype("int64")
    activity_n = active.sum(axis=1).astype("int64")
    share = np.where(n_covered.to_numpy() > 0,
                     activity_n.to_numpy() / np.maximum(n_covered.to_numpy(), 1),
                     0.0)
    return pd.DataFrame({
        "n_members": n_members,
        "n_covered": n_covered,
        "activity_n": activity_n,
        "activity_share": pd.Series(share, index=mask.index, dtype="float64"),
    })


# ---------------------------------------------------------------------------
# episode state machine (pure — the unit-test seam)
# ---------------------------------------------------------------------------

def episodes_from_series(basket_id: str,
                         dates: Sequence[Any],
                         activity_share: Sequence[float],
                         activity_n: Sequence[int],
                         active_members: Sequence[Iterable[str]] | None = None,
                         ) -> list[dict]:
    """Run the participation-episode machine over one basket's daily series.

    PURE: no IO, no clock, no ledger.  Same inputs -> same output, which is what
    makes the append-only ledger's closed rows re-derivable and therefore checkable.

        enter   activity_share >= EPISODE_ENTER_SHARE  AND activity_n >= EPISODE_MIN_ACTIVE
        sustain activity_share >= EPISODE_EXIT_SHARE   AND activity_n >= EPISODE_MIN_ACTIVE
                (hysteresis — a soft session inside an episode is still an active
                session of it, and does not restart the count)
        join    active days <= EPISODE_MAX_GAP inactive sessions apart are ONE episode
        close   EPISODE_CLOSE_AFTER consecutive inactive sessions close it AT ITS LAST
                ACTIVE SESSION (the trailing quiet days belong to no episode)

    `active_members[i]` is the set of member tickers active on session i; when given,
    persistence is computed (members active in EVERY active session / members active
    in at least one).  Without it those fields are 0 / None.

    The trailing episode is returned with closed=False when the series ends inside
    it (or inside its <3-session grace) — that row is PROVISIONAL by construction.
    """
    n = len(dates)
    if not (n == len(activity_share) == len(activity_n)):
        raise ValueError("group_pulse.episodes_from_series: ragged inputs")

    episodes: list[dict] = []
    open_ep: dict | None = None
    gap = 0

    def _finish(ep: dict, closed: bool) -> dict:
        ever = ep["ever"]
        persisted = ep["persisted"]
        n_ever = len(ever)
        n_pers = len(persisted) if ep["sessions_active"] else 0
        return {
            "basket_id": basket_id,
            "episode_id": f"{basket_id}:{_iso(ep['start'])}",
            "start_date": _iso(ep["start"]),
            "end_date": _iso(ep["end"]),
            "sessions_active": int(ep["sessions_active"]),
            "sessions_span": int(ep["end_pos"] - ep["start_pos"] + 1),
            "members_ever_active": int(n_ever),
            "members_persisted": int(n_pers),
            "persistence_share": (round(n_pers / n_ever, 4) if n_ever else None),
            "closed": bool(closed),
        }

    for i in range(n):
        share = float(activity_share[i]) if activity_share[i] is not None else 0.0
        cnt = int(activity_n[i]) if activity_n[i] is not None else 0
        members = set(active_members[i]) if active_members is not None else set()

        bar = EPISODE_EXIT_SHARE if open_ep is not None else EPISODE_ENTER_SHARE
        day_active = (share >= bar) and (cnt >= EPISODE_MIN_ACTIVE)

        if day_active:
            if open_ep is None:
                open_ep = {"start": dates[i], "start_pos": i, "end": dates[i],
                           "end_pos": i, "sessions_active": 0,
                           "ever": set(), "persisted": None}
            open_ep["end"] = dates[i]
            open_ep["end_pos"] = i
            open_ep["sessions_active"] += 1
            open_ep["ever"] |= members
            open_ep["persisted"] = (set(members) if open_ep["persisted"] is None
                                    else open_ep["persisted"] & members)
            gap = 0
        elif open_ep is not None:
            gap += 1
            if gap >= EPISODE_CLOSE_AFTER:
                open_ep["persisted"] = open_ep["persisted"] or set()
                episodes.append(_finish(open_ep, closed=True))
                open_ep, gap = None, 0

    if open_ep is not None:
        open_ep["persisted"] = open_ep["persisted"] or set()
        episodes.append(_finish(open_ep, closed=False))
    return episodes


def episode_state_change(daily: pd.DataFrame, active_now: bool) -> str:
    """`episode.state_change` for the latest session (first match wins).

        strengthening  activity_share rose >= EPISODE_STATE_DELTA vs the prior
                       session AND the basket is in an open episode today
        cooling        fell >= EPISODE_STATE_DELTA AND (in an episode today, or
                       sitting inside the exit hysteresis band [0.35, 0.5))
        steady         in an episode today, neither of the above
        quiet          otherwise
    """
    if daily.empty:
        return "quiet"
    share = float(daily["activity_share"].iloc[-1])
    prev = float(daily["activity_share"].iloc[-2]) if len(daily) >= 2 else share
    delta = share - prev
    in_hysteresis = EPISODE_EXIT_SHARE <= share < EPISODE_ENTER_SHARE
    if active_now and delta >= EPISODE_STATE_DELTA:
        return "strengthening"
    if delta <= -EPISODE_STATE_DELTA and (active_now or in_hysteresis):
        return "cooling"
    if active_now:
        return "steady"
    return "quiet"


# ---------------------------------------------------------------------------
# the group_pulse.v1 object
# ---------------------------------------------------------------------------

def _participation(panel: dict, as_of: pd.Timestamp,
                   members: list[str]) -> tuple[dict, dict]:
    """participation block + the intermediate sets the other blocks reuse."""
    covered = [t for t in members if bool(panel["covered"].at[as_of, t])]
    active = [t for t in covered if bool(panel["active"].at[as_of, t])]
    with_vol = [t for t in active if bool(panel["vol_leg"].at[as_of, t])]

    def _trend(key: str) -> tuple[float | None, int]:
        has = [t for t in covered if bool(panel[f"has_{key}"].at[as_of, t])]
        if not has:
            return None, 0
        above = sum(1 for t in has if bool(panel[f"above_{key}"].at[as_of, t]))
        return _share(above, len(has)), len(has)

    trend50, _n50 = _trend("ma50")
    trend200, _n200 = _trend("ma200")
    block = {
        "activity_share": _r(_share(len(active), len(covered)), 4),
        "activity_n": len(active),
        "trend_share_50d": _r(trend50, 4),
        "trend_share_200d": _r(trend200, 4),
        "activity_basis": {"ret_only": len(active) - len(with_vol),
                           "ret_and_volume": len(with_vol)},
    }
    return block, {"covered": covered, "active": active}


def _direction(sets: dict, panel: dict, as_of: pd.Timestamp) -> dict:
    covered, active = sets["covered"], sets["active"]
    row = panel["spy_adj"].loc[as_of]

    agree = sign_agreement(row.reindex(active)) if active else sign_agreement(pd.Series(dtype="float64"))
    pct = float(agree["agreement_pct"])
    if agree["n"] == 0 or pct < SIGN_AGREEMENT_MIN or agree["net"] == 0:
        sign = "mixed"
    else:
        sign = "up" if agree["net"] > 0 else "down"

    cov_rets = row.reindex(covered).dropna()
    median_move = float(cov_rets.median()) if not cov_rets.empty else None

    # COHESION is the one RAW-return leg in this block, deliberately: it is
    # engine.group_flow's cohesion, same function and same input basis, so
    # flow.json and pulse.json can never print two different "cohesion" numbers
    # for the same basket. Everything else here is SPY-adjusted.
    cfg = _flow_cfg()
    cw = int(cfg.get("corr_window_d", 40))
    pos = panel["index"].get_loc(as_of)
    win = panel["rets"].iloc[max(0, pos - cw + 1): pos + 1]
    cohesion = _mean_pairwise_corr(win.reindex(columns=covered)) if covered else None

    leader = None
    if active:
        zrow = panel["activity_z"].loc[as_of].reindex(active).dropna()
        if not zrow.empty:
            leader = {"ticker": str(zrow.idxmax()), "kind": "activity"}

    strongest = weakest = None
    if not cov_rets.empty:
        strongest = {"ticker": str(cov_rets.idxmax()), "ret": _r(cov_rets.max(), 4)}
        weakest = {"ticker": str(cov_rets.idxmin()), "ret": _r(cov_rets.min(), 4)}

    return {
        "agreement_pct": _r(pct, 4),
        "sign": sign,
        "median_move_spy_adj": _r(median_move, 5),
        "cohesion": _r(cohesion, 4),
        "leader": leader,
        "strongest": strongest,
        "weakest": weakest,
    }


def _arc(sets: dict, panel: dict, as_of: pd.Timestamp, washouts: dict,
         stages: dict, n_members: int, trend50: float | None,
         dd_pctile: float | None) -> dict:
    covered = sets["covered"]
    n_covered = len(covered)

    readable = [t for t in covered if washouts.get(t) is not None]
    washed = [t for t in readable if washouts[t]["washed_out"]]
    washed_share = _share(len(washed), len(readable))

    ages = [washouts[t]["sessions_since_trough"] for t in washed]
    median_age = int(np.median(ages)) if ages else None

    reclaimed = None
    if washed:
        have20 = [t for t in washed if bool(panel["has_ma20"].at[as_of, t])]
        if have20:
            up20 = sum(1 for t in have20 if bool(panel["above_ma20"].at[as_of, t]))
            reclaimed = _share(up20, len(have20))

    staged = [stages.get(t) for t in covered if stages.get(t) in (1, 2, 3, 4)]
    stage2 = _share(sum(1 for s in staged if s == 2), len(staged)) if staged else None
    stage4 = _share(sum(1 for s in staged if s == 4), len(staged)) if staged else None

    state = _arc_state(n_covered, n_members, washed_share, median_age, reclaimed,
                       stage2, stage4, trend50)
    return {
        "state": state,
        "washed_out_share": _r(washed_share, 4),
        "washed_out_n": len(washed),
        "reclaimed_20d_share": _r(reclaimed, 4),
        "capitulation_median_age_d": median_age,
        "stage2_share": _r(stage2, 4),
        "stage4_share": _r(stage4, 4),
        "drawdown_pctile_own_history": _r(dd_pctile, 4),
        "null_disclosure": ARC_NULL_DISCLOSURE,
    }


def _arc_state(n_covered: int, n_members: int, washed_share: float | None,
               median_age: int | None, reclaimed: float | None,
               stage2: float | None, stage4: float | None,
               trend50: float | None) -> str:
    """The ARC ladder — floors first, then first match wins (see module docstring)."""
    if n_covered < ARC_MIN_COVERED:
        return "insufficient_coverage"
    if n_members <= 0 or (n_covered / n_members) < ARC_MIN_COVERED_FRACTION:
        return "insufficient_coverage"
    washed_ok = washed_share is not None and washed_share >= ARC_WASHOUT_SHARE_MIN
    if washed_ok and median_age is not None and median_age <= ARC_CAPIT_FRESH_SESSIONS:
        return "washout_in_progress"
    if (washed_ok and median_age is not None and median_age > ARC_CAPIT_FRESH_SESSIONS
            and (reclaimed is None or reclaimed < ARC_RECLAIM_SHARE_MIN)):
        return "washout_complete_awaiting_reclaim"
    if washed_ok and reclaimed is not None and reclaimed >= ARC_RECLAIM_SHARE_MIN:
        return "turning"
    if (stage2 is not None and stage2 >= ARC_STAGE2_SHARE_MIN
            and trend50 is not None and trend50 >= ARC_TREND50_ADVANCING_MIN):
        return "advancing"
    if (stage4 is not None and stage4 >= ARC_STAGE4_SHARE_MIN
            and trend50 is not None and trend50 < ARC_TREND50_DISTRIBUTING_MAX):
        return "distributing"
    return "quiet"


def equal_weight_drawdown_pctile(mask: pd.DataFrame, panel: dict) -> float | None:
    """Where the basket's CURRENT equal-weight drawdown sits in its OWN history.

    0.91 reads "deeper than 91% of this basket's own sessions" — the percentile is
    over DEPTH, so a fresh high is ~0.0 and the worst session on record is 1.0.  The
    EW level follows engine/baskets._ew_level (mean of active members' daily returns,
    cumulated, dated membership); the comparison universe is that basket only, never
    a cross-basket pool (this plane never ranks one basket against another).
    """
    cols = list(mask.columns)
    if not cols:
        return None
    rets = panel["closes"][cols].pct_change(fill_method=None)
    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return None
    lvl = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    if len(lvl) < 2:
        return None
    dd = (lvl / lvl.cummax() - 1.0).to_numpy()
    now = dd[-1]
    if not np.isfinite(now):
        return None
    return float(np.mean(dd >= now))


def basket_frames(basket: dict, panel: dict, as_of: pd.Timestamp) -> dict:
    """Per-basket derived frames, built ONCE and shared by the pulse object and the
    episode ledger (the two used to build them independently, which doubled the
    per-basket cost for byte-identical inputs).

    `members_by_day` is materialised only for CANDIDATE active sessions — a day that
    cannot clear the episode machine's lowest bar is never consulted for persistence,
    so building its member set is pure waste at ~3.2k sessions x ~49 baskets.
    """
    cols = list(panel["closes"].columns)
    members = live_members(basket, as_of)
    present = [t for t in members if t in cols]
    mask = membership_mask(basket, panel["index"], present)
    daily = basket_daily_participation(mask, panel)

    act = panel["active"].reindex(columns=present, fill_value=False) & mask
    shares = daily["activity_share"].to_numpy()
    counts = daily["activity_n"].to_numpy()
    candidate = (shares >= EPISODE_EXIT_SHARE) & (counts >= EPISODE_MIN_ACTIVE)
    arr = act.to_numpy()
    acols = np.asarray(act.columns, dtype=object)
    members_by_day = [set(acols[arr[i]]) if candidate[i] else set()
                      for i in range(len(daily))]
    return {"members": members, "present": present, "mask": mask, "daily": daily,
            "members_by_day": members_by_day}


def basket_pulse(basket_id: str, basket: dict, panel: dict, as_of: pd.Timestamp,
                 washouts: dict, stages: dict, generated_at: str,
                 frames: dict, episodes: list[dict],
                 stage_source_ok: bool = True,
                 bench_ok: bool = True) -> dict | None:
    """One `group_pulse.v1` object.  Returns None when the basket has no live member."""
    members, present = frames["members"], frames["present"]
    mask, daily = frames["mask"], frames["daily"]
    n_members = len(members)
    if n_members == 0:
        return None

    part, sets = _participation(panel, as_of, present)
    direction = _direction(sets, panel, as_of)
    dd_pctile = equal_weight_drawdown_pctile(mask, panel)
    arc = _arc(sets, panel, as_of, washouts, stages, n_members,
               part["trend_share_50d"], dd_pctile)

    open_ep = episodes[-1] if episodes and not episodes[-1]["closed"] else None
    # active_now is the STRICT reading: today is an ACTIVE SESSION of the open
    # episode.  An episode inside its <=2-session grace stays open (current_start
    # keeps printing) while active_now goes false — "the episode has not closed,
    # but the basket is not participating today" is a real state, not a contradiction.
    active_now = bool(open_ep is not None and open_ep["end_date"] == _iso(as_of))
    episode = {
        "active_now": active_now,
        "current_start": open_ep["start_date"] if open_ep else None,
        "sessions_active": int(open_ep["sessions_active"]) if open_ep else 0,
        "state_change": episode_state_change(daily, active_now),
    }

    cols = list(panel["closes"].columns)
    warnings: list[str] = []
    n_covered = len(sets["covered"])
    no_tape = [t for t in members if t not in cols]
    if no_tape:
        warnings.append(f"members_without_tape:{len(no_tape)}")
    thin = n_members - n_covered - len(no_tape)
    if thin > 0:
        warnings.append(f"members_without_activity_read:{thin}")
    if arc["state"] == "insufficient_coverage":
        warnings.append("below_coverage_floor")
    if not stage_source_ok or arc["stage2_share"] is None:
        warnings.append("stage_read_unavailable")
    if not bench_ok:
        warnings.append("benchmark_unavailable_returns_unadjusted")
    if direction["cohesion"] is None:
        warnings.append("cohesion_unavailable")

    return {
        "schema": SCHEMA,
        "authority": AUTHORITY["authority"],
        "generated_at": generated_at,
        "basket_id": basket_id,
        "as_of": _iso(as_of),
        "n_members": n_members,
        "n_covered": n_covered,
        "participation": part,
        "direction": direction,
        "arc": arc,
        "episode": episode,
        "coverage_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# contract validator (the golden/mutant test seam)
# ---------------------------------------------------------------------------

_TOP_KEYS = {
    "schema": str, "authority": str, "generated_at": str, "basket_id": str,
    "as_of": str, "n_members": int, "n_covered": int, "participation": dict,
    "direction": dict, "arc": dict, "episode": dict, "coverage_warnings": list,
}
_PART_KEYS = {"activity_share", "activity_n", "trend_share_50d",
              "trend_share_200d", "activity_basis"}
_BASIS_KEYS = {"ret_only", "ret_and_volume"}
_DIR_KEYS = {"agreement_pct", "sign", "median_move_spy_adj", "cohesion",
             "leader", "strongest", "weakest"}
_ARC_KEYS = {"state", "washed_out_share", "washed_out_n", "reclaimed_20d_share",
             "capitulation_median_age_d", "stage2_share", "stage4_share",
             "drawdown_pctile_own_history", "null_disclosure"}
_EPI_KEYS = {"active_now", "current_start", "sessions_active", "state_change"}

#: Every cross-sectional SHARE and the count that is its numerator/denominator.
#: "every cross-sectional stat carries n's" is a contract clause, so it is checked,
#: not merely documented.
_SHARE_N_PAIRS = (("participation", "activity_share", "activity_n"),
                  ("arc", "washed_out_share", "washed_out_n"))


def _block(errs: list[str], obj: dict, name: str, allowed: set) -> dict:
    b = obj.get(name)
    if not isinstance(b, dict):
        errs.append(f"{name}: missing or not an object")
        return {}
    unknown = set(b) - allowed
    if unknown:
        errs.append(f"{name}: unknown key(s) {sorted(unknown)}")
    missing = allowed - set(b)
    if missing:
        errs.append(f"{name}: missing key(s) {sorted(missing)}")
    return b


def validate_pulse(obj: Any) -> list[str]:
    """Return the list of contract violations for ONE group_pulse.v1 object.

    Empty list == valid.  Unknown keys ARE violations (a frozen contract that
    tolerates extras is not frozen), and so is a share that arrives without its n.
    """
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["not an object"]
    unknown = set(obj) - set(_TOP_KEYS)
    if unknown:
        errs.append(f"top-level: unknown key(s) {sorted(unknown)}")
    for k, typ in _TOP_KEYS.items():
        if k not in obj:
            errs.append(f"top-level: missing key '{k}'")
        elif typ is int and isinstance(obj[k], bool):
            errs.append(f"top-level: '{k}' must be {typ.__name__}")
        elif not isinstance(obj[k], typ):
            errs.append(f"top-level: '{k}' must be {typ.__name__}")
    if obj.get("schema") != SCHEMA:
        errs.append(f"schema must be '{SCHEMA}'")
    if obj.get("authority") != "context_only":
        errs.append("authority must be 'context_only'")

    part = _block(errs, obj, "participation", _PART_KEYS)
    basis = part.get("activity_basis")
    if isinstance(basis, dict):
        if set(basis) != _BASIS_KEYS:
            errs.append(f"participation.activity_basis: keys must be {sorted(_BASIS_KEYS)}")
        elif isinstance(part.get("activity_n"), int):
            if sum(int(v) for v in basis.values()) != int(part["activity_n"]):
                errs.append("participation.activity_basis must partition activity_n")
    elif "activity_basis" in part:
        errs.append("participation.activity_basis: not an object")

    direction = _block(errs, obj, "direction", _DIR_KEYS)
    if direction.get("sign") not in _SIGN_STATES:
        errs.append(f"direction.sign must be one of {sorted(_SIGN_STATES)}")
    for k in ("leader", "strongest", "weakest"):
        v = direction.get(k)
        if v is not None and not (isinstance(v, dict) and v.get("ticker")):
            errs.append(f"direction.{k} must be null or carry a ticker")

    arc = _block(errs, obj, "arc", _ARC_KEYS)
    if arc.get("state") not in _ARC_STATES:
        errs.append(f"arc.state must be one of {sorted(_ARC_STATES)}")
    if arc.get("null_disclosure") != ARC_NULL_DISCLOSURE:
        errs.append(f"arc.null_disclosure must be '{ARC_NULL_DISCLOSURE}'")

    epi = _block(errs, obj, "episode", _EPI_KEYS)
    if epi.get("state_change") not in _STATE_CHANGES:
        errs.append(f"episode.state_change must be one of {sorted(_STATE_CHANGES)}")
    if not isinstance(epi.get("active_now"), bool):
        errs.append("episode.active_now must be a bool")

    for block_name, share_key, n_key in _SHARE_N_PAIRS:
        b = obj.get(block_name)
        if isinstance(b, dict) and b.get(share_key) is not None and not isinstance(
                b.get(n_key), int):
            errs.append(f"{block_name}.{share_key} present without {n_key}")

    for k in ("n_members", "n_covered"):
        v = obj.get(k)
        if isinstance(v, int) and v < 0:
            errs.append(f"top-level: '{k}' must be non-negative")
    if isinstance(obj.get("n_members"), int) and isinstance(obj.get("n_covered"), int):
        if obj["n_covered"] > obj["n_members"]:
            errs.append("n_covered cannot exceed n_members")
    if not all(isinstance(w, str) for w in (obj.get("coverage_warnings") or [])):
        errs.append("coverage_warnings must be a list of strings")
    return errs


def validate_payload(payload: Any) -> list[str]:
    """Violations across the whole {basket_id: group_pulse.v1} artifact."""
    if not isinstance(payload, dict):
        return ["payload: not an object"]
    errs: list[str] = []
    for bid, obj in payload.items():
        for e in validate_pulse(obj):
            errs.append(f"{bid}: {e}")
        if isinstance(obj, dict) and obj.get("basket_id") != bid:
            errs.append(f"{bid}: basket_id does not match its key")
    return errs


# ---------------------------------------------------------------------------
# episode ledger — append-only, nightly-only, closed rows IMMUTABLE
# ---------------------------------------------------------------------------

def ledger_path(data_root: Path) -> Path:
    return data_root.joinpath(*_LEDGER_REL)


def _empty_ledger() -> pd.DataFrame:
    return pd.DataFrame({
        "basket_id": pd.Series(dtype="string"),
        "episode_id": pd.Series(dtype="string"),
        "start_date": pd.Series(dtype="string"),
        "end_date": pd.Series(dtype="string"),
        "sessions_active": pd.Series(dtype="int64"),
        "sessions_span": pd.Series(dtype="int64"),
        "members_ever_active": pd.Series(dtype="int64"),
        "members_persisted": pd.Series(dtype="int64"),
        "persistence_share": pd.Series(dtype="float64"),
        "closed": pd.Series(dtype="bool"),
        "advanced_at": pd.Series(dtype="string"),
    })


def read_ledger(data_root: Path) -> pd.DataFrame:
    """The episode ledger, or an empty typed frame when absent/unreadable."""
    p = ledger_path(data_root)
    if not p.exists():
        return _empty_ledger()
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — an unreadable ledger degrades, never crashes
        print(f"::warning title=group-pulse::episode ledger unreadable ({e}) "
              f"— this advance starts from an EMPTY ledger; prior closed rows are not "
              f"in the artifact for this run", flush=True)
        return _empty_ledger()
    for c in EPISODE_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    return _typed(df[list(EPISODE_COLUMNS)])


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ("basket_id", "episode_id", "start_date", "end_date", "advanced_at"):
        out[c] = out[c].astype("string")
    for c in ("sessions_active", "sessions_span", "members_ever_active",
              "members_persisted"):
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype("int64")
    out["persistence_share"] = pd.to_numeric(out["persistence_share"], errors="coerce"
                                             ).astype("float64")
    out["closed"] = out["closed"].astype("boolean").fillna(False).astype("bool")
    return out[list(EPISODE_COLUMNS)]


def merge_episodes(stored: pd.DataFrame, computed: dict[str, list[dict]],
                   advanced_at: str) -> pd.DataFrame:
    """Fold freshly-computed episodes into the stored ledger.

    THE IMMUTABILITY RULE, in one place: a stored row with closed=True is re-emitted
    VERBATIM and its recomputed twin is discarded.  Only NEW closed episodes and the
    single PROVISIONAL (open) row per basket are written from this run.  That is why
    advancing twice over the same inputs cannot rewrite history — not because the
    recompute happens to agree, but because the stored row is never asked.
    """
    stored = _typed(stored) if len(stored) else _empty_ledger()
    frozen = stored[stored["closed"]].copy()
    frozen_ids = set(frozen["episode_id"].dropna().astype(str))

    fresh: list[dict] = []
    for bid in sorted(computed):
        for ep in computed[bid]:
            if ep["episode_id"] in frozen_ids:
                continue                     # already frozen — never rewritten
            fresh.append({**ep, "advanced_at": advanced_at})

    frames = [f for f in (frozen, pd.DataFrame(fresh)) if len(f)]
    if not frames:
        return _empty_ledger()
    out = pd.concat(frames, ignore_index=True)
    out = _typed(out)
    # Deterministic order: basket, then episode start.  A stable order keeps the
    # parquet byte-comparable across advances that changed nothing.
    out = out.sort_values(["basket_id", "start_date", "episode_id"],
                          kind="stable").reset_index(drop=True)
    return out


def advance_episode_ledger(computed: dict[str, list[dict]], data_root: Path,
                           require_nightly_lane: bool = True,
                           advanced_at: str | None = None) -> dict:
    """Append this run's episodes to data/group_pulse/episodes.parquet.

    Gated on `engine.ledger_lane.nightly_advance_enabled()` — house law: nightly is
    the sole advancer of forward ledgers, and an intraday lane computes and DISCARDS.
    `require_nightly_lane=False` is the test/backfill seam only.
    """
    if require_nightly_lane and not _ledger_advance_enabled():
        log.info("group_pulse: episode ledger advance skipped (COLLECT_LANE != nightly)")
        return {"written": False, "reason": "off_nightly_lane", "rows": 0}
    stamp = advanced_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = read_ledger(data_root)
    merged = merge_episodes(stored, computed, stamp)
    p = ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(p, index=False)
    return {"written": True, "rows": int(len(merged)),
            "closed": int(merged["closed"].sum()),
            "open": int((~merged["closed"]).sum()), "path": str(p)}


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

def compute(data_root: Path | None = None) -> dict[str, Any]:
    """Build the whole {basket_id: group_pulse.v1} payload plus the episode map.

    Returns ``{"payload": {...}, "episodes": {basket_id: [episode, ...]},
    "as_of": "YYYY-MM-DD", "elapsed_s": float, "n_baskets": int}``.  Never raises:
    a total data failure returns an EMPTY payload with the hole annotated.
    """
    t0 = time.time()
    if data_root is None:
        from lib import config
        data_root = config.data_dir()
    data_root = Path(data_root)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    baskets = load_membership(data_root)
    if not baskets:
        return {"payload": {}, "episodes": {}, "as_of": None,
                "elapsed_s": round(time.time() - t0, 2), "n_baskets": 0}

    tickers = basket_tickers(baskets)
    closes, volumes, missing = load_member_tape(tickers, data_root)
    if closes.empty:
        print("::warning title=group-pulse::no member tape readable under "
              f"{data_root.joinpath(*MEMBER_STORE_REL)} — pulse.json is EMPTY this run",
              flush=True)
        return {"payload": {}, "episodes": {}, "as_of": None,
                "elapsed_s": round(time.time() - t0, 2), "n_baskets": 0}
    if missing:
        log.info("group_pulse: %d/%d member tickers have no readable tape",
                 len(missing), len(tickers))

    bench = load_benchmark(data_root)
    bench_ok = bench is not None and not bench.empty
    if not bench_ok:
        print("::warning title=group-pulse::SPY benchmark unavailable — activity and "
              "direction fall back to RAW returns for this run (disclosed per basket "
              "as coverage_warnings.benchmark_unavailable_returns_unadjusted)",
              flush=True)

    panel = build_member_panel(closes, volumes, bench)
    as_of = panel["index"].max()
    washouts = member_washouts(closes)
    stages = member_stages(closes, volumes, bench)
    stage_ok = bool(stages) and any(v is not None for v in stages.values())

    payload: dict[str, dict] = {}
    episodes: dict[str, list[dict]] = {}
    for bid, b in baskets.items():
        try:
            frames = basket_frames(b, panel, as_of)
            eps = episodes_from_series(
                bid, list(frames["daily"].index),
                frames["daily"]["activity_share"].tolist(),
                frames["daily"]["activity_n"].tolist(),
                frames["members_by_day"])
            obj = basket_pulse(bid, b, panel, as_of, washouts, stages, generated_at,
                               frames, eps, stage_source_ok=stage_ok,
                               bench_ok=bench_ok)
        except Exception as e:  # noqa: BLE001 — one bad basket never sinks the sweep
            print(f"::warning title=group-pulse::basket {bid} failed ({e}) — it is "
                  f"ABSENT from pulse.json this run", flush=True)
            log.debug("group_pulse: basket %s failed", bid, exc_info=True)
            continue
        if obj is None:
            continue
        payload[bid] = obj
        episodes[bid] = eps

    return {"payload": payload, "episodes": episodes, "as_of": _iso(as_of),
            "elapsed_s": round(time.time() - t0, 2), "n_baskets": len(payload)}


def write_site_artifact(payload: dict, site_root: Path | None = None) -> Path:
    """Write site/basketdata/pulse.json.  Returns the written path."""
    if site_root is None:
        from lib import config
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out = Path(site_root).joinpath(*_SITE_REL)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=False, default=str)
    out.write_text(body + "\n", encoding="utf-8")
    log.info("group_pulse: wrote %s (%d baskets, %dKB)", out, len(payload),
             len(body.encode()) // 1024)
    return out


def run(data_root: Path | None = None, site_root: Path | None = None,
        require_nightly_lane: bool = True) -> dict:
    """Nightly entry point: compute -> write pulse.json -> advance the ledger.

    The ARTIFACT is written in any lane (a display snapshot); only the LEDGER append
    is nightly-gated.  Returns a small summary dict for the caller's log line.
    """
    res = compute(data_root)
    path = write_site_artifact(res["payload"], site_root)
    if data_root is None:
        from lib import config
        data_root = config.data_dir()
    ledger = advance_episode_ledger(res["episodes"], Path(data_root),
                                    require_nightly_lane=require_nightly_lane)
    return {"as_of": res["as_of"], "n_baskets": res["n_baskets"],
            "elapsed_s": res["elapsed_s"], "artifact": str(path), "ledger": ledger}
