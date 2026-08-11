"""engine.price_pressure.context — per-event point-in-time facts.

Everything here is computable from data that EXISTED at the close of t0.  A
field that needs t0+1 to compute belongs in the grading block, not here, and
``tests/test_price_pressure.py`` poisons the fixture's t0+1 bars to prove the
identity block does not move.

Two house laws shape this module:

**No day taxonomy in the ledger** (DNR:KILL-PARALLEL-SHOCK-CLASSIFIER).  The
ledger stores day CHARACTER as numbers only — ``panel_shock_count``,
``panel_share_z2``, ``spy_ret_z`` — and never a categorical label.  The live
artifact banner may borrow ``market_drivers`` vocabulary for the CURRENT day
(fail-open), because that organ's graded history is 17 rows and cannot label a
five-year backfill.

**Filing families are coverage-gated** (masterplan §6, review BLOCKER 2).  EDGAR
tracks 1,314 tickers; ~54% of this panel is outside it.  "No filing on record"
and "we do not track filings for this name" are DIFFERENT statements, so an
uncovered name gets its own family and never lands in ``no-filing``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure.panel import BASE_WIN, news_flags, sector_ex_self_peer

log = logging.getLogger("price_pressure.context")

#: The four filing families (§6).  ``filing-coverage-unknown`` is NOT a null —
#: it is the honest name for "EDGAR does not track this ticker".
FAMILIES: tuple[str, ...] = (
    "earnings-filing", "other-filing", "no-filing", "filing-coverage-unknown",
)

#: Plain-word display strings for the family chips (§9).  The uncovered one is
#: the review's exact required wording.
FAMILY_LABELS: dict[str, str] = {
    "earnings-filing": "earnings filing",
    "other-filing": "other filing",
    "no-filing": "no filing on record",
    "filing-coverage-unknown": "filings not tracked for this name",
}

#: Minimum priced co-members before a thematic basket residual is computed.
BASKET_MIN_PEERS = 3

#: Trailing window for the VIX percentile (LSR convention: 252 sessions).
VIX_WINDOW = 252


# ---------------------------------------------------------------------------
# filing families
# ---------------------------------------------------------------------------

def attach_filings(ev: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """EDGAR 8-K firewall flags via LSR ``news_flags`` (imported, not copied).

    Adds ``earn8k``/``mat8k``/``news``/``cov_earn8k`` and renames the coverage
    bit to the ledger's ``edgar_covered``.
    """
    ev = news_flags(ev, Path(data_dir))
    ev["edgar_covered"] = ev["cov_earn8k"].astype(bool)
    return ev


def family_of(earn8k: bool, mat8k: bool, edgar_covered: bool) -> str:
    """The coverage-gated filing family for one event row.

    An uncovered ticker can never be ``no-filing``: we did not look, so we do
    not know.  Earnings outranks material when both fired in the ±1d window.
    """
    if not edgar_covered:
        return "filing-coverage-unknown"
    if earn8k:
        return "earnings-filing"
    if mat8k:
        return "other-filing"
    return "no-filing"


def attach_families(ev: pd.DataFrame) -> pd.DataFrame:
    ev["family"] = [
        family_of(bool(e), bool(m), bool(c))
        for e, m, c in zip(ev["earn8k"], ev["mat8k"], ev["edgar_covered"])
    ]
    return ev


# ---------------------------------------------------------------------------
# numeric day facts (never a label)
# ---------------------------------------------------------------------------

def spy_return_z(data_dir: Path, sessions: pd.DatetimeIndex,
                 base_win: int = BASE_WIN) -> pd.Series:
    """SPY's same-day return as a z against its OWN trailing σ (shifted).

    A number, not a verdict: it says how large the index move was in its own
    recent terms and lets a reader see "everything fell today" without the lobe
    inventing a name for the day.  Missing store -> an all-null series.
    """
    idx = pd.DatetimeIndex(sessions)
    path = Path(data_dir) / "yahoo" / "SPY.parquet"
    if not path.exists():
        return pd.Series(np.nan, index=idx, name="spy_ret_z", dtype="float64")
    try:
        df = pd.read_parquet(path)
        col = "close" if "close" in df.columns else df.columns[0]
        px = pd.to_numeric(df[col], errors="coerce").dropna()
        px.index = pd.DatetimeIndex(px.index).normalize()
        px = px[~px.index.duplicated(keep="last")].sort_index()
        r = px.pct_change()
        z = r / r.rolling(base_win, min_periods=40).std().shift(1)
        return z.reindex(idx.normalize()).set_axis(idx).astype("float64").rename("spy_ret_z")
    except Exception as exc:  # noqa: BLE001 — a torn benchmark is a gap, not a crash
        log.debug("price_pressure: SPY z unavailable (%s)", exc)
        return pd.Series(np.nan, index=idx, name="spy_ret_z", dtype="float64")


def vix_store_path(data_dir: Path) -> Path:
    """The ONE VIXCLS artifact this lobe reads — named once, so the §10.1
    completion receipt can hash exactly the bytes the stamp transform saw."""
    return Path(data_dir) / "fred" / "VIXCLS.parquet"


def clean_vix_closes(df: pd.DataFrame) -> pd.Series:
    """The store frame reduced to the series the §3 transform actually ranks.

    dropna -> normalize -> ``duplicated(keep="last")`` -> sort.  Split out of
    ``vix_percentile`` so the stamp-completion pass (``completion.py``) ranks
    the SAME construction rather than a re-typed lookalike: a second copy of
    these four steps is how a completed stamp quietly stops matching the
    harvest-night stamp it is standing in for.
    """
    col = "vix_close" if "vix_close" in df.columns else df.columns[0]
    v = pd.to_numeric(df[col], errors="coerce").dropna()
    v.index = pd.DatetimeIndex(v.index).normalize()
    return v[~v.index.duplicated(keep="last")].sort_index()


def vix_percentile_of(closes: pd.Series, window: int = VIX_WINDOW) -> pd.Series:
    """Trailing-``window``-observation percentile rank, inclusive of the row's
    own close — the §3 transform, on an already-cleaned series."""
    return closes.rolling(window, min_periods=60).rank(pct=True)


def vix_close_series(data_dir: Path) -> pd.Series:
    """Cleaned VIXCLS closes off the store, or an empty series.  Never raises."""
    path = vix_store_path(data_dir)
    if not path.exists():
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([]), name="vix_close")
    try:
        return clean_vix_closes(pd.read_parquet(path))
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: VIX store unreadable (%s)", exc)
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([]), name="vix_close")


def vix_percentile(data_dir: Path, sessions: pd.DatetimeIndex,
                   window: int = VIX_WINDOW) -> pd.Series:
    """VIX level as a trailing-252-session percentile (FRED VIXCLS, LSR source)."""
    idx = pd.DatetimeIndex(sessions)
    try:
        v = vix_close_series(data_dir)
        if v.empty:
            return pd.Series(np.nan, index=idx, name="vix_pctile", dtype="float64")
        pct = vix_percentile_of(v, window)
        return pct.reindex(idx.normalize()).set_axis(idx).astype("float64").rename("vix_pctile")
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: VIX percentile unavailable (%s)", exc)
        return pd.Series(np.nan, index=idx, name="vix_pctile", dtype="float64")


# ---------------------------------------------------------------------------
# level facts off the panel
# ---------------------------------------------------------------------------

def position_frames(panel: dict[str, pd.DataFrame], window: int = 252) -> dict[str, pd.DataFrame]:
    """``pos52`` (house convention, 0-100 within the 52w range) + 52w-low distance."""
    close = panel["close"]
    hi = close.rolling(window, min_periods=100).max()
    lo = close.rolling(window, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    return {
        "pos52": (100.0 * (close - lo) / span),
        "dist_52w_low": (close / lo.replace(0, np.nan) - 1.0),
    }


def revisions_covered_set(data_dir: Path) -> set[str]:
    """Tickers with any analyst-revisions history — the §8 accrual clock, visible
    from day one so the coverage question is answerable later without a re-run."""
    path = Path(data_dir) / "revisions" / "history.parquet"
    if not path.exists():
        return set()
    try:
        return set(pd.read_parquet(path, columns=["ticker"])["ticker"].astype(str).unique())
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: revisions coverage unavailable (%s)", exc)
        return set()


# ---------------------------------------------------------------------------
# thematic baskets — a DISPLAY-HONESTY axis, never the fence
# ---------------------------------------------------------------------------

def load_basket_membership(data_dir: Path) -> dict[str, list[dict]]:
    """``{basket_id: [{ticker, added, removed}, …]}`` from data/baskets/membership.json.

    Dated membership is respected point-in-time: a member added in 2025 is not a
    peer for a 2023 shock.
    """
    path = Path(data_dir) / "baskets" / "membership.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) or {}
        out: dict[str, list[dict]] = {}
        for bid, entry in (raw.get("baskets") or {}).items():
            members = []
            for m in (entry or {}).get("members") or []:
                t = str(m.get("ticker") or "").strip().upper()
                if t:
                    members.append({"ticker": t, "added": m.get("added"),
                                    "removed": m.get("removed")})
            if members:
                out[str(bid)] = members
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: basket membership unavailable (%s)", exc)
        return {}


def basket_labels(data_dir: Path) -> dict[str, dict[str, str]]:
    """``{basket_id: {"en": name, "zh": name_zh}}`` for display chips.

    Display COPY lives here rather than in the ledger: a ledger row stores the
    basket id (a fact), and the surface resolves the bilingual name at build
    time, so renaming a basket never rewrites history.
    """
    path = Path(data_dir) / "baskets" / "membership.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) or {}
        out: dict[str, dict[str, str]] = {}
        for bid, entry in (raw.get("baskets") or {}).items():
            en = str((entry or {}).get("name") or "").strip()
            zh = str((entry or {}).get("name_zh") or "").strip()
            if en or zh:
                out[str(bid)] = {"en": en or None, "zh": zh or None}
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: basket labels unavailable (%s)", exc)
        return {}


def basket_residual_frames(ret: pd.DataFrame, membership: dict[str, list[dict]],
                           *, min_peers: int = BASKET_MIN_PEERS,
                           ) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    """Per-basket ex-self peer return, respecting dated membership.

    Reuses the imported LSR ``sector_ex_self_peer`` on a membership-masked slice
    (one pseudo-sector per basket), then removes the helper's whole-universe
    fallback so a thin basket reads NULL instead of borrowing the market.  The
    result is a CONTEXT axis: the shock fence itself stays sector-basis
    LSR-pure (masterplan §12).

    Returns ``({basket_id: exself_frame}, chosen_basket_size)`` where the second
    value maps basket_id -> ever-member count, used for the most-specific pick.
    """
    frames: dict[str, pd.DataFrame] = {}
    sizes: dict[str, int] = {}
    cols = set(ret.columns)
    for bid, members in membership.items():
        names = sorted({m["ticker"] for m in members} & cols)
        if len(names) < min_peers + 1:
            continue
        active = pd.DataFrame(True, index=ret.index, columns=names)
        for m in members:
            t = m["ticker"]
            if t not in active.columns:
                continue
            if m.get("added"):
                active.loc[active.index < pd.Timestamp(m["added"]), t] = False
            if m.get("removed"):
                active.loc[active.index > pd.Timestamp(m["removed"]), t] = False
        sub = ret[names].where(active)
        exself = sector_ex_self_peer(sub, pd.Series(bid, index=names), min_peers=min_peers)
        n = sub.notna().sum(axis=1).to_numpy()
        exself = exself.where(np.repeat((n >= min_peers)[:, None], len(names), axis=1))
        frames[bid] = exself
        sizes[bid] = len(names)
    return frames, pd.Series(sizes, dtype="int64")


def attach_basket_context(ev: pd.DataFrame, ret: pd.DataFrame,
                          membership: dict[str, list[dict]],
                          precomputed: tuple[dict[str, pd.DataFrame], pd.Series] | None = None,
                          ) -> pd.DataFrame:
    """Stamp each event with its most-specific thematic basket and that residual.

    Most specific = fewest ever-members with a value on the day, ties broken
    alphabetically — deterministic, and it prefers ``silver_miners`` (10 names)
    over ``us_sector_materials`` (80), which is the whole point: CDE's GICS
    sector is chemicals-and-steel, so a Materials "peers implied" line would be
    economically false while the silver basket carries the honest framing (§6).
    """
    ev["basket"] = pd.Series([None] * len(ev), index=ev.index, dtype="object")
    ev["basket_ret"] = np.nan
    ev["basket_resid"] = np.nan
    if ev.empty or (not membership and precomputed is None):
        return ev
    frames, sizes = precomputed if precomputed is not None else \
        basket_residual_frames(ret, membership)
    if not frames:
        return ev
    order = [b for b in sizes.sort_values(kind="stable").index if b in frames]
    order.sort(key=lambda b: (int(sizes[b]), b))
    per_ticker: dict[str, list[str]] = {}
    for bid in order:
        for t in frames[bid].columns:
            per_ticker.setdefault(t, []).append(bid)

    basket, bret = [], []
    for t, dt in zip(ev["ticker"], ev["date"]):
        pick, val = None, np.nan
        for bid in per_ticker.get(t, ()):
            fr = frames[bid]
            if dt in fr.index:
                v = fr.at[dt, t]
                if pd.notna(v):
                    pick, val = bid, float(v)
                    break
        basket.append(pick)
        bret.append(val)
    ev["basket"] = pd.Series(basket, index=ev.index, dtype="object")
    ev["basket_ret"] = pd.Series(bret, index=ev.index, dtype="float64")
    ev["basket_resid"] = ev["ret"].astype("float64") - ev["basket_ret"]
    return ev


# ---------------------------------------------------------------------------
# live day-character banner (artifact only, current day, fail-open)
# ---------------------------------------------------------------------------

def day_character(root: Path, gaps: list[str], *,
                  allow_snapshot: bool = True) -> dict | None:
    """``market_drivers`` vocabulary for TODAY's banner — never for the ledger.

    Reads the persisted nightly read first (``data/regime/latest.json``), then
    falls back to a lazy ``engine.market_drivers.snapshot()``.  Both arms are
    fail-open: a missing organ appends a gap note and the banner is dropped, it
    never blocks the artifact.

    ``allow_snapshot=False`` skips the live recompute — the snapshot resolves its
    own inputs through ``lib.config`` and would reach outside a caller-supplied
    ``root``, which a hermetic test must not do.
    """
    root = Path(root)
    try:
        p = root / "data" / "regime" / "latest.json"
        if p.exists():
            md = (json.loads(p.read_text(encoding="utf-8")) or {}).get("market_drivers")
            if isinstance(md, dict) and md.get("verdict"):
                return {"verdict": str(md.get("verdict")),
                        "primary_label": str(md.get("primary_label") or "").strip() or None,
                        "asof": str(md.get("asof") or "").strip() or None,
                        "source": "data/regime/latest.json#market_drivers"}
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"day_character: regime read failed ({type(exc).__name__})")
    if not allow_snapshot:
        gaps.append("day_character: persisted market_drivers read absent")
        return None
    try:
        from engine import market_drivers  # lazy: heavy leaf, optional at import time

        snap = market_drivers.snapshot()
        if isinstance(snap, dict) and snap.get("verdict") not in (None, "unknown"):
            return {"verdict": str(snap.get("verdict")),
                    "primary_label": str(snap.get("primary_label") or "").strip() or None,
                    "asof": str(snap.get("asof") or "").strip() or None,
                    "source": "engine.market_drivers.snapshot()"}
        gaps.append("day_character: market_drivers verdict unavailable")
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"day_character: market_drivers unavailable ({type(exc).__name__})")
    return None
