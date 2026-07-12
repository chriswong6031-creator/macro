"""Treasury Watch — deterministic detector of market-critical Treasury cash-flow moves.

The White House desk (scripts/build_whitehouse.py) watches *policy announcements*; this
module watches the Treasury's *plumbing*: the Treasury General Account (TGA) at the Fed.
When Treasury spends from the TGA the cash lands in private bank deposits and reserve
balances — a mechanical liquidity injection; when it rebuilds the TGA it drains reserves.
Around quarter-ends this move is large enough (hundreds of $bn) to backstop or amplify a
tape, so it belongs in the same alert surface as executive policy.

Two public functions, both degrade-never-raise (missing/short/unreadable inputs → an empty
list or a schema-shaped payload full of nulls + a gaps[] note, never an exception):

* ``detect_events(root=None, …)`` → 0-or-1 White-House-feed-item-shaped dict(s) describing
  the current TGA episode, ready to flow through the IDENTICAL sentinel pipeline
  (processed.json guid dedupe → Opus brain → ledger → banner).  The item ``body`` is a
  deterministic data narrative giving the brain everything it needs to judge the move IN
  CONTEXT (the day-by-day TGA path, net-liquidity backdrop, RRP buffer, reserve scarcity,
  regime) — the brain adds the market read, never the numbers.

* ``snapshot(root=None, …)`` → the ``treasury_watch.v1`` payload (events=[]) that the panel
  on whitehouse.html and the bot-side reader (brain/treasury_context.py) both consume.

ID-STABILITY INVARIANT (why the hourly sentinel never double-fires an episode): an episode's
id is anchored to the date of the trailing-window TGA *extremum* (the quarter-end peak for a
release, the trough for a rebuild), NOT to the latest date.  As a drawdown deepens day by day
the anchor date — and therefore the id — stays fixed (``tw-2026-06-30-tga-release``), so the
processed.json guid dedupe marks it seen once and the brain evaluates it once.

ACCEPTANCE EPISODE (reproducible from the repo's committed data/treasury/tga.parquet): the
Jun-30 2026 quarter-end release — TGA 919.1bn (06-30) → 744.6bn (07-09), magnitude ≈ −174.5bn,
id ``tw-2026-06-30-tga-release``, quarter_end_adjacent True.

DISPLAY-ONLY: nothing here feeds a score or an allocation.  All $bn values are USD billions
(the TGA parquet stores $ millions → divide by 1000).
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

log = logging.getLogger("treasury_watch")

SCHEMA = "treasury_watch.v1"

_DTS_URL = ("https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/"
            "operating-cash-balance")
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _cfg() -> dict[str, Any]:
    """Thresholds from config.yml ``treasury_watch:`` (defaults when the section is absent)."""
    try:
        c = config.load().get("treasury_watch", {}) or {}
    except Exception:  # noqa: BLE001 — degrade-never-raise
        c = {}
    return {
        "min_episode_bn": float(c.get("min_episode_bn", 100.0)),
        "min_1d_bn": float(c.get("min_1d_bn", 60.0)),
        "lookback_extremum_bd": int(c.get("lookback_extremum_bd", 15)),
        "spark_days": int(c.get("spark_days", 60)),
    }


# --------------------------------------------------------------------------- #
# input readers (all fail-soft; every one has an injectable test seam)
# --------------------------------------------------------------------------- #
def _root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    try:
        return Path(config.ROOT)
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parent.parent


def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else None
    except Exception as e:  # noqa: BLE001
        log.debug("treasury_watch: read %s failed (%s)", p, e)
        return None


def _load_tga_bn(_tga: Any = None) -> pd.Series | None:
    """Return the daily TGA level as a float Series in $ **billions**, DatetimeIndex sorted.

    Accepts an injected DataFrame with a ``tga_mn`` column (the real parquet shape), an
    injected Series already in $bn, or reads data/treasury/tga.parquet.  None when
    unavailable/empty.
    """
    try:
        obj: Any
        if _tga is not None:
            obj = _tga
        else:
            obj = store.read("treasury", "tga")
        if obj is None:
            return None
        if isinstance(obj, pd.DataFrame):
            if "tga_mn" in obj.columns:
                s = pd.to_numeric(obj["tga_mn"], errors="coerce") / 1000.0
            else:  # single-column frame already in bn
                s = pd.to_numeric(obj.iloc[:, 0], errors="coerce")
        elif isinstance(obj, pd.Series):
            s = pd.to_numeric(obj, errors="coerce")  # assumed already in bn
        else:
            return None
        s.index = pd.to_datetime(s.index)
        s = s.dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        return s if not s.empty else None
    except Exception as e:  # noqa: BLE001
        log.debug("treasury_watch: TGA load failed (%s)", e)
        return None


def _load_plumbing(root: Path, _plumbing: Any = None) -> dict[str, Any]:
    if isinstance(_plumbing, dict):
        return _plumbing
    for rel in ("data/neuralweb/liquidity_plumbing.json",
                "site/neuralwebdata/liquidity_plumbing.json"):
        d = _read_json(root / rel)
        if d:
            return d
    return {}


def _load_regime(root: Path, _regime: Any = None) -> dict[str, Any]:
    if isinstance(_regime, dict):
        return _regime
    return _read_json(root / "data" / "regime" / "latest.json") or {}


def _load_netliq_df(root: Path, _netliq: Any = None) -> pd.DataFrame | None:
    if isinstance(_netliq, pd.DataFrame):
        return _netliq
    try:
        p = root / "data" / "macro" / "fed_net_liquidity.parquet"
        if not p.exists():
            return None
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("treasury_watch: netliq parquet load failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _f(x: Any, nd: int = 3) -> float | None:
    try:
        if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
            return None
        return round(float(x), nd)
    except Exception:  # noqa: BLE001
        return None


def _dstr(d: Any) -> str | None:
    try:
        return pd.Timestamp(d).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _pretty(d: Any) -> str:
    """'2026-06-30' → 'Jun 30'."""
    try:
        ts = pd.Timestamp(d)
        return f"{_MON[ts.month - 1]} {ts.day}"
    except Exception:  # noqa: BLE001
        return str(d)


def _busdays_between(a: date, b: date) -> int:
    """Absolute business-day distance between two dates (holidays ignored — adjacency only)."""
    try:
        return int(abs(np.busday_count(min(a, b), max(a, b))))
    except Exception:  # noqa: BLE001
        return abs((a - b).days)


def _quarter_end_adjacent(anchor: date, within_bd: int = 3) -> tuple[bool, str | None]:
    """(True, 'YYYY-MM-DD') when ``anchor`` is within ``within_bd`` business days of any
    calendar quarter-end (Mar 31 / Jun 30 / Sep 30 / Dec 31); else (False, None)."""
    best: tuple[int, date] | None = None
    for y in (anchor.year - 1, anchor.year, anchor.year + 1):
        for m, d in _QUARTER_ENDS:
            try:
                qe = date(y, m, d)
            except ValueError:
                continue
            dist = _busdays_between(anchor, qe)
            if best is None or dist < best[0]:
                best = (dist, qe)
    if best is not None and best[0] <= within_bd:
        return True, best[1].isoformat()
    return False, None


def _recent_quarter_end_anchor(series: pd.Series, max_age_days: int = 45) -> tuple[Any, float] | None:
    """The observation at/just-before the most recent calendar quarter-end, when that
    quarter-end is within ``max_age_days`` of the latest observation.  Returns
    (anchor_timestamp, level_bn) or None.  This is the canonical anchor for a
    post-quarter-end TGA release — Treasury builds cash INTO the quarter-end reporting
    date then spends it down, so the quarter-end level is the local high markets watch."""
    try:
        latest_d = pd.Timestamp(series.index[-1]).date()
        cand: date | None = None
        for y in (latest_d.year, latest_d.year - 1):
            for m, d in _QUARTER_ENDS:
                qe = date(y, m, d)
                if qe <= latest_d and (cand is None or qe > cand):
                    cand = qe
        if cand is None or (latest_d - cand).days > max_age_days:
            return None
        at_or_before = series[series.index <= pd.Timestamp(cand)]
        if at_or_before.empty:
            return None
        return at_or_before.index[-1], float(at_or_before.iloc[-1])
    except Exception:  # noqa: BLE001
        return None


def _episode(series: pd.Series, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Detect the dominant current TGA episode.

    Anchor selection (in priority order):
      1. QUARTER-END RELEASE (canonical): if a calendar quarter-end sits within range and
         the drawdown from its level clears the episode threshold, anchor there. This is
         preferred even over a larger raw drawdown from an earlier intra-quarter tax-date
         peak — the post-quarter-end spend-down is the nameable, market-watched event, and
         a quarter-end anchor is far more id-stable across daily runs than a sliding extremum.
      2. Raw trailing-window extremum (peak→latest release / trough→latest build).
      3. Single-day |ΔTGA| trigger (anchored on the prior day).

    Returns {kind, anchor(date), anchor_str, magnitude_bn, chg_1d_bn, days, direction,
    quarter_end_adjacent, quarter_end_date, source} or None when nothing clears threshold.
    """
    n = len(series)
    if n < 2:
        return None
    latest = float(series.iloc[-1])
    prev = float(series.iloc[-2])
    chg_1d = latest - prev
    lookback = cfg["lookback_extremum_bd"]
    window = series.iloc[-lookback:] if lookback and n > lookback else series
    min_ep = cfg["min_episode_bn"]
    min_1d = cfg["min_1d_bn"]

    cands: list[tuple[str, Any, float, str]] = []

    # (1) quarter-end release — the preferred, canonical anchor
    qe_anchor = _recent_quarter_end_anchor(series)
    if qe_anchor is not None:
        qe_ts, qe_level = qe_anchor
        qe_mag = latest - qe_level
        if qe_mag <= -min_ep:
            cands.append(("tga_release", qe_ts, qe_mag, "quarter_end"))

    # (2) raw trailing-window extremum
    peak_date = window.idxmax()
    trough_date = window.idxmin()
    release_mag = latest - float(window.max())   # <= 0 (drawdown from the peak)
    build_mag = latest - float(window.min())     # >= 0 (rebuild from the trough)
    if release_mag <= -min_ep:
        cands.append(("tga_release", peak_date, release_mag, "extremum"))
    if build_mag >= min_ep:
        cands.append(("tga_build", trough_date, build_mag, "extremum"))

    # (3) single-day triggers (only when no multi-day episode of the same sign fired) —
    # anchor on the prior day so the id is distinct from a multi-day episode.
    if not any(k == "tga_release" for k, _, _, _ in cands) and chg_1d <= -min_1d:
        cands.append(("tga_release", series.index[-2], chg_1d, "single_day"))
    if not any(k == "tga_build" for k, _, _, _ in cands) and chg_1d >= min_1d:
        cands.append(("tga_build", series.index[-2], chg_1d, "single_day"))
    if not cands:
        return None

    # a quarter-end release wins outright; otherwise the largest-magnitude candidate.
    qe_cands = [c for c in cands if c[3] == "quarter_end"]
    kind, anchor_ts, mag, source = (max(qe_cands, key=lambda c: abs(c[2])) if qe_cands
                                    else max(cands, key=lambda c: abs(c[2])))
    anchor_d = pd.Timestamp(anchor_ts).date()
    latest_d = pd.Timestamp(series.index[-1]).date()
    # business days elapsed from anchor to latest (# observations in the span − 1)
    try:
        days = int(len(series.loc[pd.Timestamp(anchor_ts):series.index[-1]]) - 1)
    except Exception:  # noqa: BLE001
        days = max(0, _busdays_between(anchor_d, latest_d))
    if source == "quarter_end":
        qe_adj, qe_date = True, anchor_d.isoformat()
    else:
        qe_adj, qe_date = _quarter_end_adjacent(anchor_d)
    return {
        "kind": kind,
        "anchor": anchor_d,
        "anchor_str": anchor_d.isoformat(),
        "magnitude_bn": round(mag, 3),
        "chg_1d_bn": round(chg_1d, 3),
        "days": days,
        "direction": "drawdown" if kind == "tga_release" else "build",
        "quarter_end_adjacent": qe_adj,
        "quarter_end_date": qe_date,
        "source": source,
    }


def _impulse_summary(ep: dict[str, Any]) -> tuple[str, str]:
    """Deterministic EN/zh one-liner for the episode (numbers-only, no market claim)."""
    mag = abs(ep["magnitude_bn"])
    days = ep["days"]
    since = _pretty(ep["anchor_str"])
    qe = ep["quarter_end_adjacent"]
    if ep["kind"] == "tga_release":
        en = (f"TGA drawdown of ${mag:.1f}bn over {days} business day(s) since "
              f"{since}{' (quarter-end)' if qe else ''} — cash released into bank reserves.")
        zh = (f"自{since}{'（季末）' if qe else ''}以来，TGA在{days}个交易日内减少约{mag * 10:.0f}亿美元"
              f"——现金释放至银行准备金。")
    else:
        en = (f"TGA rebuild of ${mag:.1f}bn over {days} business day(s) since "
              f"{since} — cash drained from bank reserves.")
        zh = (f"自{since}以来，TGA在{days}个交易日内回补约{mag * 10:.0f}亿美元"
              f"——现金从银行准备金抽离。")
    return en, zh


def _spark_points(pairs: list[list[Any]], w: int = 560, h: int = 64, pad: int = 4) -> str:
    """SVG polyline points over a wxh viewBox; y inverted (higher level → higher on screen).
    Empty string for <2 points; all-equal values render as a flat mid-line (no div-by-zero)."""
    vals = [v for _, v in pairs if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    inner = h - 2 * pad
    pts: list[str] = []
    m = len(pairs)
    for i, (_, v) in enumerate(pairs):
        if v is None:
            continue
        x = (w * i / (m - 1)) if m > 1 else 0.0
        y = pad + inner * (1.0 - (v - lo) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


# --------------------------------------------------------------------------- #
# public: snapshot
# --------------------------------------------------------------------------- #
def snapshot(root: str | Path | None = None, _tga: Any = None, _netliq: Any = None,
             _plumbing: Any = None, _regime: Any = None) -> dict[str, Any]:
    """Assemble the ``treasury_watch.v1`` payload (events=[]).  Never raises."""
    r = _root(root)
    cfg = _cfg()
    gaps: list[str] = []

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": None,
        "is_context_only": True,
        "tga": None,
        "net_liquidity": None,
        "plumbing": None,
        "tga_impulse": None,
        "market_context": None,
        "events": [],
        "gaps": gaps,
    }

    # —— TGA block ——
    tga = _load_tga_bn(_tga)
    if tga is None or tga.empty:
        gaps.append("TGA series unavailable (data/treasury/tga.parquet) — TGA block null")
    else:
        latest_d = _dstr(tga.index[-1])
        payload["as_of"] = latest_d
        level = float(tga.iloc[-1])
        n = len(tga)

        def _chg(back: int) -> float | None:
            if n > back:
                return round(level - float(tga.iloc[-(back + 1)]), 3)
            return None

        # quarter-end reference (most recent calendar quarter-end ≤ as_of, within 45 days)
        qe_block = None
        try:
            latest_date = pd.Timestamp(tga.index[-1]).date()
            cand: date | None = None
            for m_, d_ in _QUARTER_ENDS:
                qe = date(latest_date.year, m_, d_)
                if qe <= latest_date and (cand is None or qe > cand):
                    cand = qe
            if cand is None:  # only Q4 of the prior year qualifies early in Q1
                cand = date(latest_date.year - 1, 12, 31)
            if (latest_date - cand).days <= 45:
                at_or_before = tga[tga.index <= pd.Timestamp(cand)]
                if not at_or_before.empty:
                    qe_level = float(at_or_before.iloc[-1])
                    qe_block = {
                        "date": cand.isoformat(),
                        "level_bn": round(qe_level, 3),
                        "chg_since_bn": round(level - qe_level, 3),
                    }
        except Exception as e:  # noqa: BLE001
            log.debug("treasury_watch: quarter-end ref failed (%s)", e)

        spark_pairs = [[_dstr(d), round(float(v), 3)]
                       for d, v in tga.iloc[-cfg["spark_days"]:].items()]
        payload["tga"] = {
            "level_bn": round(level, 3),
            "asof": latest_d,
            "chg_1d_bn": _chg(1),
            "chg_5d_bn": _chg(5),
            "chg_20d_bn": _chg(20),
            "quarter_end": qe_block,
            "spark_60d": spark_pairs,
            "spark_points": _spark_points(spark_pairs),
        }
        if qe_block is None:
            gaps.append("no calendar quarter-end within 45d of as_of — tga.quarter_end null")

        # —— self-computed impulse (the plumbing artifact has no tga_impulse block) ——
        ep = _episode(tga, cfg)
        if ep is not None:
            en, zh = _impulse_summary(ep)
            payload["tga_impulse"] = {
                "active": True,
                "direction": ep["direction"],
                "magnitude_bn": ep["magnitude_bn"],
                "days": ep["days"],
                "since": ep["anchor_str"],
                "quarter_end_adjacent": ep["quarter_end_adjacent"],
                "summary_en": en,
                "summary_zh": zh,
            }

    # —— net-liquidity + plumbing blocks (prefer the canonical plumbing artifact) ——
    plumb = _load_plumbing(r, _plumbing)
    regime = _load_regime(r, _regime)
    q = plumb.get("quantity") if isinstance(plumb.get("quantity"), dict) else {}
    fed = plumb.get("fed") if isinstance(plumb.get("fed"), dict) else {}
    rrp = plumb.get("rrp") if isinstance(plumb.get("rrp"), dict) else {}
    funding = plumb.get("funding") if isinstance(plumb.get("funding"), dict) else {}
    headline = plumb.get("headline") if isinstance(plumb.get("headline"), dict) else {}
    overlay = regime.get("liquidity_overlay") or q.get("overlay")

    if q or fed or rrp:
        payload["net_liquidity"] = {
            "netliq_bn": _f(q.get("netliq_bn")),
            "chg_20d_bn": _f(q.get("netliq_chg_20d_bn")),
            "chg_65d_bn": _f(q.get("netliq_chg_65d_bn")),
            "pctile_expanding": _f(q.get("netliq_pctile_expanding"), 4),
            "overlay": overlay,
            "walcl_bn": _f(fed.get("assets_bn")),
            "rrp_bn": _f(rrp.get("rrp_bn")),
        }
    else:
        # fall back to the netliq parquet's latest row
        ndf = _load_netliq_df(r, _netliq)
        if ndf is not None and not ndf.empty:
            row = ndf.iloc[-1]
            payload["net_liquidity"] = {
                "netliq_bn": _f(row.get("netliq_bn")),
                "chg_20d_bn": None,
                "chg_65d_bn": None,
                "pctile_expanding": _f(row.get("netliq_pctile_expanding"), 4),
                "overlay": overlay,
                "walcl_bn": _f(row.get("walcl_bn")),
                "rrp_bn": _f(row.get("rrp_bn")),
            }
            gaps.append("liquidity_plumbing.json absent — net_liquidity from parquet, "
                        "20d/65d deltas null")
        else:
            gaps.append("net-liquidity unavailable (no liquidity_plumbing.json, no "
                        "fed_net_liquidity.parquet) — net_liquidity block null")

    if headline or rrp or funding:
        payload["plumbing"] = {
            "headline_state": headline.get("state"),
            "headline_summary_en": headline.get("summary"),
            "headline_summary_zh": None,  # the plumbing artifact carries EN prose only
            "rrp_buffer_state": rrp.get("buffer_state"),
            "reserve_scarcity_state": funding.get("reserve_scarcity_state"),
        }
    else:
        gaps.append("liquidity_plumbing.json absent — plumbing block null")

    # —— market/regime context ——
    if regime:
        payload["market_context"] = {
            "regime_quad": regime.get("quad"),
            "quad_name": regime.get("quad_name"),
            "liquidity_overlay": regime.get("liquidity_overlay"),
            "regime_asof": regime.get("asof") or regime.get("date"),
        }
    else:
        gaps.append("data/regime/latest.json unavailable — market_context null")

    return payload


# --------------------------------------------------------------------------- #
# public: detect_events
# --------------------------------------------------------------------------- #
def detect_events(root: str | Path | None = None, _tga: Any = None, _plumbing: Any = None,
                  _regime: Any = None, now: datetime | None = None) -> list[dict[str, Any]]:
    """Return 0-or-1 White-House-feed-item-shaped dict(s) for the current TGA episode.

    Shape matches engine.whitehouse_feed items so it flows through the sentinel pipeline
    unchanged: {id, guid, title, url, published, excerpt, body, section, categories}.
    """
    try:
        cfg = _cfg()
        tga = _load_tga_bn(_tga)
        if tga is None or len(tga) < 2:
            return []
        ep = _episode(tga, cfg)
        if ep is None:
            return []

        r = _root(root)
        plumb = _load_plumbing(r, _plumbing)
        regime = _load_regime(r, _regime)

        latest_d = pd.Timestamp(tga.index[-1]).date()
        latest_level = float(tga.iloc[-1])
        mag = ep["magnitude_bn"]
        kind = ep["kind"]
        anchor = ep["anchor_str"]
        qe = ep["quarter_end_adjacent"]

        ev_id = f"tw-{anchor}-{'tga-release' if kind == 'tga_release' else 'tga-build'}"

        if kind == "tga_release":
            title = (f"Treasury released ~${abs(mag):.0f}bn of TGA cash into the banking "
                     f"system since {_pretty(anchor)}"
                     f"{' (quarter-end)' if qe else ''}")
        else:
            title = (f"Treasury rebuilt the TGA by ~${abs(mag):.0f}bn since {_pretty(anchor)}, "
                     f"draining bank reserves"
                     f"{' (quarter-end)' if qe else ''}")

        # deterministic day-by-day path from anchor → latest
        try:
            path = tga.loc[pd.Timestamp(anchor):tga.index[-1]]
        except Exception:  # noqa: BLE001
            path = tga.iloc[-min(len(tga), ep["days"] + 1):]
        path_lines = [f"  {_dstr(d)}: ${float(v):.1f}bn" for d, v in path.items()]

        q = plumb.get("quantity") if isinstance(plumb.get("quantity"), dict) else {}
        rrp = plumb.get("rrp") if isinstance(plumb.get("rrp"), dict) else {}
        fed = plumb.get("fed") if isinstance(plumb.get("fed"), dict) else {}
        funding = plumb.get("funding") if isinstance(plumb.get("funding"), dict) else {}
        headline = plumb.get("headline") if isinstance(plumb.get("headline"), dict) else {}

        ctx: list[str] = []
        if q.get("netliq_bn") is not None:
            ctx.append(f"Net liquidity (WALCL − TGA − RRP): ${float(q['netliq_bn']):.0f}bn"
                       + (f", Δ20d {float(q['netliq_chg_20d_bn']):+.0f}bn"
                          if q.get("netliq_chg_20d_bn") is not None else "")
                       + (f", {float(q['netliq_pctile_expanding']) * 100:.0f}th pctile of the "
                          "expanding history" if q.get("netliq_pctile_expanding") is not None
                          else "")
                       + ".")
        if fed.get("assets_bn") is not None:
            ctx.append(f"Fed balance sheet (WALCL): ${float(fed['assets_bn']):.0f}bn.")
        if rrp.get("rrp_bn") is not None:
            ctx.append(f"Overnight RRP: ${float(rrp['rrp_bn']):.1f}bn"
                       + (f" (buffer {rrp['buffer_state']})" if rrp.get("buffer_state") else "")
                       + ". A drawdown into an EXHAUSTED RRP buffer lands directly in reserves "
                         "— the highest-impact case; an ample RRP absorbs part of the swing.")
        if funding.get("reserve_scarcity_state"):
            ctx.append(f"Reserve scarcity: {funding['reserve_scarcity_state']}.")
        if headline.get("state"):
            ctx.append(f"Liquidity-plumbing state: {headline['state']}.")
        if regime.get("quad_name") or regime.get("liquidity_overlay"):
            ctx.append(f"Macro regime: {regime.get('quad_name') or regime.get('quad') or '?'}"
                       f" (Fed liquidity overlay: {regime.get('liquidity_overlay') or '?'}).")

        mechanism = ("When the TGA falls, that cash lands in private bank deposits and reserve "
                     "balances — a mechanical liquidity injection; its market impact is strongest "
                     "when the RRP buffer is exhausted, because the reserves add flows straight "
                     "into the banking system rather than draining the RRP first."
                     if kind == "tga_release" else
                     "When the TGA rebuilds, Treasury is pulling cash out of private bank deposits "
                     "and reserve balances — a mechanical liquidity drain that tightens financial "
                     "conditions at the margin, most acutely when the RRP buffer is already thin.")

        body = "\n".join([
            title + ".",
            "",
            f"TGA path ({'peak' if kind == 'tga_release' else 'trough'} {_pretty(anchor)} "
            f"→ {_pretty(latest_d.isoformat())}):",
            *path_lines,
            "",
            f"Episode magnitude: {mag:+.1f}bn over {ep['days']} business day(s)"
            + (" — anchored on a calendar quarter-end." if qe else ".")
            + f" Latest TGA level: ${latest_level:.1f}bn.",
            "",
            "Context at the time of this move:",
            *[f"- {c}" for c in ctx],
            "",
            mechanism,
        ])
        excerpt = body.replace("\n", " ").strip()[:300]

        published = f"{latest_d.isoformat()}T20:00:00+00:00"

        return [{
            "id": ev_id,
            "guid": ev_id,
            "title": title,
            "url": _DTS_URL,
            "published": published,
            "excerpt": excerpt,
            "body": body,
            "section": "treasury",
            "categories": ["treasury", "liquidity", "tga"],
        }]
    except Exception as e:  # noqa: BLE001 — degrade-never-raise
        log.warning("treasury_watch.detect_events failed (%s)", e)
        return []
