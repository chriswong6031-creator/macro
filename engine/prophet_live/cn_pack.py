"""engine.prophet_live.cn_pack — the mainland arming pass (CN-PR-1, spec §4).

WHAT IT DOES. For every tradable A-share in the nightly board's own pool it re-runs
the SAME close-only admission gate (:func:`engine.signal_gate.gate`) with candidate
provisional closes APPENDED as the next mainland session's bar, and records the price
interval over which the gate holds. The next session's 5-minute lane then only has to
compare a delayed live price to those two numbers — it never re-derives a signal.
The pack is an OPTIMIZATION; the gate is the truth.

THE PROBE MACHINERY IS THE US ONE, DRIVEN — NOT FORKED. :mod:`engine.prophet_live.armed_pack`
owns the append semantics, the structure grid, the bisection, the edge checks and the
fail-closed verification, all of it re-measured and re-argued at length in that module's
docstring. This module supplies the four things that are genuinely CN:

  1. THE CALENDAR. The appended bar must land on the next MAINLAND session. That is
     the additive ``calendar=`` parameter threaded through ``armed_pack`` in this same
     PR; ``calendar=None`` remains NYSE, so no US caller moved. A hand-rolled business
     day would put the bar on a Golden Week holiday and re-phase every 2D/3D bucket
     ``engine.session_anchor`` assigns.
  2. THE PROBE SPAN. Per-class DAILY LIMIT (±10% main board, ±20% STAR/ChiNext), not
     the US 15%. Exact, not tighter and not wider than what tomorrow's tape can
     lawfully print: probing to +15% on a main-board name spends a third of the grid
     on prices that cannot exist, and probing only to +15% on a ChiNext name leaves
     the top quarter of its lawful range unswept (spec §2/§4).
  3. THE T2 EVENT LATCH, MANDATORY. Every gate call passes
     ``event_latch=EventLatch("CN").load()`` with ``record=False``. The repaint class
     this closes is measured: the incomplete trailing 3D bucket's known-date advances
     every session, so a T2 conjunction UN-FIRES on a bar that already printed and the
     name leaves every lane at once (300363.SZ: 2026-08-05 rank 1 → 08-06 absent →
     +20.02% on 08-07). Latch discipline lives ENTIRELY in the arm — the evaluator
     never calls ``gate()`` — so a pack armed without it would poison a whole session
     with no way to notice. ``record=False`` is equally load-bearing: this lane is not
     the asia collection lane and a fired event may never be un-fired, so it READS the
     latch and writes nothing to it.
  4. THE FROZEN CROSS-SECTIONAL CONTEXT. Tonight's score/rank/lane ride the pack per
     name, PROJECTED and never recomputed (spec §4). The close board restates the
     nightly's own order from ``frozen.board_order``; it does not re-rank. That is what
     keeps §11's "no new scoring authority" true of this whole program.

LANE LAW. This module writes NOTHING under ``data/`` and commits nothing. It publishes
one R2 key (:data:`engine.prophet_live.cn_states.CN_PACK_KEY`) and, with ``--out``, one
local copy for the reconciler. The nightly ``asia-close`` remains the sole writer of
every ledger and the only thing that confirms. Kill switch
``CN_PROPHET_LIVE_NO_PUBLISH=1`` refuses the publish.

ONE PRICE BASIS (W-L0 gate 3, spec §3). Every edge in this pack is a price on a
SPLIT+DIVIDEND ADJUSTED series and the pack says so per name. Measured, not assumed:
both CN close sources pull ``auto_adjust=True`` — ``data/china_stocks``
(``collectors/china_stock_prices.py``, ``overwrite_overlap=True`` re-owns the refresh
window) and the ``data/china_search`` cache (``collectors/china_universe.py``, the
``yf.download(..., auto_adjust=True)`` call and its seam-free merge). That is a
STRONGER position than the US pack, whose breadth-cache names accrue raw closes between
rebuilds and have to be stamped as exceptions. ``data/china_stocks_raw``
(``auto_adjust=False``) is NOT read by this lane.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from engine.prophet_live import armed_pack as AP
from engine.prophet_live import cn_clock
from engine.prophet_live.cn_states import CN_PACK_KEY  # noqa: F401  (re-exported)
from engine.prophet_live.interval import ADJUSTED, DEFAULT_PACK_ADJUSTMENT

log = logging.getLogger(__name__)

SCHEMA = "cn_prophet_live.armed/v1"

#: Config block. Falls through to ``prophet_live`` for anything it does not set, so
#: the grid/bisection resolution has ONE definition estate-wide.
CFG_BLOCK = "cn_prophet_live"

#: CN overrides on :data:`engine.prophet_live.armed_pack._DEFAULTS`. Only what
#: genuinely differs is listed — everything absent is the US number on purpose.
_CN_DEFAULTS: dict[str, Any] = {
    # Ceiling on names given a full grid, and the wall clock for the WHOLE pass. The
    # step runs inside asia-close at `timeout-minutes: 12` and is `continue-on-error`
    # (advisory lane — its failure never reds settlement; its ABSENCE is what the
    # evaluator's `stale_pack` honesty catches). Measured on this store 2026-08-15:
    # 1,711 non-ETF names, ~312 ms per gate call, so the centre census alone is ~535
    # CPU-seconds and the budget is what makes the step fit at all.
    "max_probe": 180,
    "max_seconds": 420,
    # A mainland name can be SUSPENDED for weeks and come back — that is an ordinary
    # A-share event, not a dead series — so the staleness cut is the US 3 sessions and
    # a lagging name ships its centre state unprobed and MARKED, never silently
    # relabelled dormant.
    "max_lag_sessions": 3,
}

#: The nightly board's lanes, in the order the close board restates them (spec §5).
#: The artifact's array names, not display labels: ``buy`` is the featured lane.
BOARD_LANES: tuple[str, ...] = ("buy", "more_actionable", "forming")

#: Where the scored board artifact lands. Read-only, and read ONCE at arm time — the
#: evaluator never opens it (CXI-R23: chat/runtime context reads product artifacts,
#: and the runtime lane reads only the pack).
STANDOUTS_REL = Path("site") / "factordata" / "china_standouts.json"


def cn_pack_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve the CN arming config: ``cn_prophet_live`` over ``prophet_live`` over code."""
    out = AP.pack_cfg(cfg)
    out.update(_CN_DEFAULTS)
    try:
        block = (cfg or {}).get(CFG_BLOCK) or {}
        for k in list(out):
            if k in block:
                out[k] = type(out[k])(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_pack: bad %s config (%s) — using defaults", CFG_BLOCK, exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Universe
# ─────────────────────────────────────────────────────────────────────────────

#: Sector labels the nightly board excludes from the per-name pool. The same two
#: strings ``build_china_library.main`` filters on when it builds
#: ``_stock_universe_tickers`` — context ETFs and indices stay in the library for its
#: pages but are never scored, and this lane must arm exactly what the board scores.
NON_STOCK_SECTORS: frozenset[str] = frozenset({"Sector ETF", "Index"})


def universe_rows(limit: int | None = None) -> list[tuple[str, pd.Series, str, str]]:
    """``[(ticker, close, name, sector), ...]`` — the nightly board's own pool.

    ONE UNIVERSE DEFINITION. This calls ``scripts.build_china_library.universe()`` and
    applies the SAME two screens the nightly applies, in the same order: drop
    ``Sector ETF``/``Index``, then the tradability predicate (ST fail-closed, market-cap
    floor, ADV floor). A second loader here would be a second definition of who is in
    the universe, which is how two surfaces start disagreeing about board membership.

    The tradability predicate and its input maps are IMPORTED from the nightly builder
    (``tradability_ok`` / ``identity_screen_maps``), which this PR lifted to module
    level for the purpose — the logic is unchanged and ``main()`` now calls the same
    functions, so there is exactly one copy of the screen.
    """
    from scripts.build_china_library import (  # noqa: PLC0415
        identity_screen_maps, tradability_ok, universe,
    )
    uni = universe()
    rows = [(t, c, n, s) for (t, c, _h, n, s) in uni if s not in NON_STOCK_SECTORS]
    mktcap_by, name_zh_by, _name_en_by, st_flag_by = identity_screen_maps()
    liq_by: dict[str, dict] = {}
    try:
        from engine import china_liquidity  # noqa: PLC0415
        liq_by = china_liquidity.liquidity_map([t for (t, *_r) in rows])
    except Exception as exc:  # noqa: BLE001 — additive screen, never fatal
        log.warning("cn_pack: china liquidity map unavailable (%s) — ADV leg inert", exc)
    counters: dict[str, int] = {}
    kept = [r for r in rows
            if tradability_ok(r[0], st_flag_by=st_flag_by, name_zh_by=name_zh_by,
                              mktcap_by=mktcap_by, liq_by=liq_by, counters=counters)]
    print(f"cn-prophet pack: universe {len(uni)} -> {len(rows)} stocks -> {len(kept)} "
          f"tradable (screen_drop={dict(sorted(counters.items()))})", flush=True)
    return kept[: int(limit)] if limit else kept


def price_adjustment(tickers: Sequence[str]) -> dict[str, str]:
    """``{ticker: basis}`` for the CN universe — the twin of the US
    ``build_stock_library.universe_price_adjustment``, which the CN library had none of.

    EVERY name is :data:`engine.prophet_live.interval.ADJUSTED`, and that is a MEASURED
    claim about two collectors, not a default: ``data/china_stocks`` and the
    ``data/china_search`` cache both pull ``auto_adjust=True`` (module docstring). The
    map is still built per name rather than stated once, because the consumer contract
    is per name and the day a third CN source appears on a different basis, this
    function is the ONE place that has to learn about it.
    """
    return {str(t): ADJUSTED for t in tickers}


# ─────────────────────────────────────────────────────────────────────────────
# Frozen cross-sectional context (spec §4)
# ─────────────────────────────────────────────────────────────────────────────

def _first_present(row: dict[str, Any], *paths: tuple[str, ...]) -> tuple[Any, str | None]:
    """First non-None value along ``paths``, plus the dotted key it came from."""
    for path in paths:
        cur: Any = row
        for part in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(part)
        if cur is not None:
            return cur, ".".join(path)
    return None, None


def frozen_context(standouts: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """``{ticker: {score, rank, lane, board_order, score_source, rank_source}}``.

    PROJECTED, NEVER RECOMPUTED. These are tonight's numbers riding along so the
    surface and the close board can show a scored row without a single re-derivation —
    §11's "no new scoring authority" made structural rather than promised.

    ``board_order`` is the nightly's OWN ordering across :data:`BOARD_LANES`, captured
    here once. The close board sorts on it and therefore RESTATES a board instead of
    re-ranking one; without it, "ordered membership" would have to be reconstructed at
    close time from numbers, which is a ranking, which is authority this lane does not
    have.

    SELF-DESCRIBING ON PURPOSE. The board artifact's rows carry no top-level ``score``
    or ``rank`` key today — the readable numbers live at ``conviction.score`` and
    ``conviction.rank_pctile`` — so the extractor tries the documented names FIRST and
    records which one actually answered under ``score_source``/``rank_source``. A
    consumer therefore never has to guess whether a null means "no score" or "the key
    moved", and the day ``prophet_score`` lands, nothing here changes.
    """
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(standouts, dict):
        return out
    order = 0
    for lane_key in BOARD_LANES:
        rows = standouts.get(lane_key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            tkr = str(row.get("ticker") or "").strip().upper()
            if not tkr or tkr in out:
                continue
            score, score_src = _first_present(
                row, ("prophet_score",), ("score",), ("conviction", "score"))
            rank, rank_src = _first_present(
                row, ("prophet_rank",), ("rank",), ("conviction", "rank_pctile"))
            out[tkr] = {
                "score": score, "rank": rank,
                "lane": str(row.get("lane") or lane_key),
                "board_order": order,
                "score_source": score_src, "rank_source": rank_src,
            }
            order += 1
    return out


def load_standouts(root: Path) -> dict[str, Any] | None:
    """The scored board artifact, or None. Absence is a DEGRADATION, never a failure.

    A pack with no frozen context still arms every level correctly — the surface just
    shows no score chip and the close board has no nightly lanes to restate, which the
    payload discloses through ``meta.frozen_n``. Refusing to arm because a display
    field is missing would trade a real capability for a cosmetic one.
    """
    p = root / STANDOUTS_REL
    try:
        if not p.is_file():
            print("::warning title=cn-prophet-pack::no china_standouts.json at "
                  f"{p} — arming with NO frozen score/lane context "
                  "(levels are unaffected; the close board will have no nightly lanes)",
                  flush=True)
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-pack::china_standouts.json unreadable ({exc})"
              " — arming with no frozen context", flush=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Probe span — the CN difference that actually changes numbers
# ─────────────────────────────────────────────────────────────────────────────

def name_cfg(cfg: dict[str, Any], ticker: str) -> dict[str, Any]:
    """``cfg`` with ``band_pct`` set to THIS name's lawful daily limit (spec §4).

    Reuses ``armed_pack``'s span/grid arithmetic wholesale by handing it the right
    band, rather than reimplementing a CN span. A ticker outside the modelled classes
    (nothing in today's universe, but the map is deliberately narrow) falls back to
    the main-board ±10%, which is the tighter of the two and therefore the direction
    that under-claims rather than over-claims.
    """
    band = cn_clock.limit_pct_for(ticker)
    return {**cfg, "band_pct": float(band if band else cn_clock.MAIN_BOARD_LIMIT_PCT)}


def gate_factory(latch: Any) -> Callable[[str, Any], dict]:
    """A ``gate_fn`` that carries the MANDATORY CN T2 event latch on every call.

    Module-level rather than a lambda because the driver fans this across a process
    pool and a lambda does not pickle; the pool's initializer builds the latch once per
    worker and hands it here.
    """
    from engine import signal_gate  # noqa: PLC0415

    def _gate(ticker: str, close: Any) -> dict:
        return signal_gate.gate(ticker, close, event_latch=latch)

    return _gate


def load_latch():
    """The CN T2 latch, loaded READ-ONLY.

    ``record=False`` is not a default to be tidied away: the recording path is gated to
    the asia collection lane precisely because a fired event may never be un-fired, and
    a pack lane that latched a conjunction computed on its own probe series would write
    fiction into a store the nightly board reads.
    """
    from engine import confluence_latch  # noqa: PLC0415
    return confluence_latch.EventLatch("CN", record=False).load()


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def as_of_date(closes) -> str | None:
    """Store tip — the MAX last-bar date across the universe. See ``armed_pack``."""
    return AP.as_of_date(closes)


def assemble(names: dict[str, dict[str, Any]], *, as_of: str, cfg: dict[str, Any],
             universe_n: int, wanted_n: int, gate_calls: int, build_seconds: float,
             skipped: dict[str, int], edges_checked: int = 0,
             probe_seconds: dict[str, float] | None = None,
             frozen: dict[str, dict[str, Any]] | None = None,
             adjustment: dict[str, str] | None = None,
             now: datetime | None = None) -> dict[str, Any]:
    """The published ``cn_prophet_live.armed/v1`` payload.

    Deliberately NOT ``armed_pack.assemble``: that function stamps the US schema and a
    single ``band_pct`` for the whole pack, and on this lane the band is PER NAME (the
    daily limit class). Every counting helper it owns is reused rather than recounted.
    """
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    frozen = frozen or {}
    states: dict[str, int] = {}
    limit_classes: dict[str, int] = {}
    for tkr, e in names.items():
        states[e.get("state", "dormant")] = states.get(e.get("state", "dormant"), 0) + 1
        # THE BAND IS PART OF THE CONTRACT, so it rides on the row: the evaluator's
        # `in_probed_band` reads band_lo/hi, but a reviewer asking "was this ChiNext
        # name swept to +20%" needs the class, not two prices to divide.
        lp = cn_clock.limit_pct_for(tkr)
        if lp is not None:
            e["limit_pct"] = lp
            key = f"{lp:g}%"
            limit_classes[key] = limit_classes.get(key, 0) + 1
        fz = frozen.get(tkr)
        if fz:
            e["frozen"] = fz
    adj_counts = AP._stamp_price_adjustment(names, adjustment)  # noqa: SLF001
    probed_n = sum(1 for e in names.values() if e.get("probed"))
    armed_n = sum(1 for e in names.values() if AP._is_armed(e))  # noqa: SLF001
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "market": "CN",
        "price_adjustment": DEFAULT_PACK_ADJUSTMENT,
        "built_at": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        # NOT a single band_pct: the span is the name's own daily limit. The header
        # states the CLASSES so a consumer sizing the pack does not have to.
        "band_policy": "per_name_daily_limit",
        "limit_classes": dict(sorted(limit_classes.items())),
        "grid_points": int(cfg["grid_points"]),
        "bisect_iters": int(cfg["bisect_iters"]),
        "names": names,
        "meta": {
            "universe_n": int(universe_n),
            "probed_n": int(probed_n),
            "armed_n": int(armed_n),
            "by_class": AP.class_counts(names, probe_seconds),
            "board_probe_share": float(cfg.get("board_probe_share", 0.4)),
            "wanted_probe_n": int(wanted_n),
            "gate_calls": int(gate_calls),
            "edges_checked": int(edges_checked),
            "build_seconds": round(float(build_seconds), 1),
            "states": states,
            "unrounded_edges": sum(1 for e in names.values() if e.get("unrounded_edge")),
            "probe_center_flips": sum(
                1 for e in names.values()
                if e.get("probe_center_buyable") is not None
                and bool(e["probe_center_buyable"]) != bool(e.get("center_buyable"))),
            "probe_scope": "two_sided_for_buyable__up_only_for_rest",
            "probe_order": "buyable__eligible__bars_to_cross__hist_d2__ticker",
            "probe_span_policy": "per_name_daily_limit_band",
            # Whatever the budget cut, BY NAME COUNT and by reason. Never silently
            # relabelled dormant — an unprobed entry ships its honest centre state with
            # no threshold and the evaluator leaves it out of coverage.
            "skipped": {k: int(v) for k, v in sorted(skipped.items()) if v},
            "price_adjustment_counts": adj_counts,
            # How many names carry tonight's score/lane. A pack whose board artifact
            # was missing arms every level correctly and says so here.
            "frozen_n": sum(1 for e in names.values() if e.get("frozen")),
            "t2_event_latch": "CN/read_only",
            "calendar": "lib.cn_calendar",
        },
    }


def build_pack(entries: Sequence[tuple[str, Any]], *, cfg: dict[str, Any] | None = None,
               now: datetime | None = None,
               gate_fn: Callable[[str, Any], dict] | None = None,
               frozen: dict[str, dict[str, Any]] | None = None,
               adjustment: dict[str, str] | None = None) -> dict[str, Any]:
    """Serial reference build over ``[(ticker, close_series), ...]`` — what tests drive.

    The driver fans the same computation across a process pool with a wall-clock
    deadline; ``max_seconds`` is NOT enforced here, because the deadline belongs to the
    pool driver that can cancel outstanding work.
    """
    from lib import cn_calendar  # noqa: PLC0415
    c = cn_pack_cfg({CFG_BLOCK: cfg} if cfg is not None else None)
    t0 = time.time()
    cleaned: list[tuple[str, pd.Series]] = []
    skipped: dict[str, int] = {}
    for tkr, close in entries:
        s = AP.clean_closes(close)
        if s is None or len(s) < 2:
            skipped["no_series"] = skipped.get("no_series", 0) + 1
            continue
        cleaned.append((tkr, s))

    tip = AP.as_of_date(s for _, s in cleaned)
    max_lag = int(c["max_lag_sessions"])
    recs: dict[str, dict[str, Any]] = {}
    series: dict[str, pd.Series] = {}
    gate_calls = 0
    for tkr, s in cleaned:
        lag = AP.session_lag(str(pd.Timestamp(s.index[-1]).date()), tip, cn_calendar)
        if lag > max_lag:
            recs[tkr] = AP.stale_record(tkr, s, lag)
            skipped["stale_series"] = skipped.get("stale_series", 0) + 1
            continue
        r = AP.centre_record(tkr, s, cfg=name_cfg(c, tkr), gate_fn=gate_fn)
        gate_calls += r["gate_calls"]
        if r.get("skip"):
            skipped[r["skip"]] = skipped.get(r["skip"], 0) + 1
        recs[tkr] = r
        series[tkr] = s

    wanted = sum(1 for r in recs.values() if r.get("wants_probe"))
    probes: dict[str, dict[str, Any]] = {}
    probe_seconds: dict[str, float] = {}
    split = AP.split_probes(recs, c, skipped)
    for cls in AP.CLASSES:
        t_cls = time.time()
        for tkr in split[cls]:
            p = AP.probe_name(tkr, series[tkr], recs[tkr], cfg=name_cfg(c, tkr),
                              gate_fn=gate_fn, calendar=cn_calendar)
            gate_calls += p["gate_calls"]
            probes[tkr] = p
            if p.get("irregular"):
                skipped["irregular"] = skipped.get("irregular", 0) + 1
        probe_seconds[cls] = time.time() - t_cls

    names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
    edges = 0
    bad: list[str] = []
    for tkr, entry in names.items():
        checks = AP.edge_checks(entry, probes.get(tkr))
        if not checks:
            continue
        lines, n = AP.verify_edges(tkr, series[tkr], checks, gate_fn=gate_fn,
                                   calendar=cn_calendar)
        bad.extend(lines)
        edges += n
        gate_calls += n
    if bad:
        skipped["edge_mismatch"] = len(bad)

    pack = assemble(names, as_of=tip or "", cfg=c, universe_n=len(entries),
                    wanted_n=wanted, gate_calls=gate_calls, edges_checked=edges,
                    probe_seconds=probe_seconds, frozen=frozen, adjustment=adjustment,
                    build_seconds=time.time() - t0, skipped=skipped, now=now)
    pack["meta"]["edge_mismatches"] = bad
    return pack


def probe_span_for(ticker: str, as_of_close: float,
                   center_buyable: bool) -> tuple[float, float]:
    """The (lo, hi) span this name's probe sweeps. Exposed for tests and receipts."""
    band = cn_clock.limit_pct_for(ticker) or cn_clock.MAIN_BOARD_LIMIT_PCT
    return AP.probe_span(float(as_of_close), bool(center_buyable), float(band))


def sanity(payload: dict[str, Any]) -> list[str]:
    """Structural complaints about an assembled pack. Empty = nothing obviously wrong.

    NOT the parity gate — :func:`engine.prophet_live.armed_pack.verify_edges` is, and it
    is the one that can actually fail. This catches the shape errors that would make
    the evaluator dark a whole board for a reason nobody could read.
    """
    out: list[str] = []
    if payload.get("schema") != SCHEMA:
        out.append(f"schema is {payload.get('schema')!r}, expected {SCHEMA!r}")
    if not payload.get("as_of"):
        out.append("no as_of — the close store produced no dated bar")
    names = payload.get("names")
    if not isinstance(names, dict) or not names:
        out.append("no names")
        return out
    for tkr, e in names.items():
        if not e.get("probed"):
            continue
        lo, hi = e.get("band_lo_px"), e.get("band_hi_px")
        if hi is None:
            out.append(f"{tkr}: probed but publishes no band_hi_px")
        if lo is not None and hi is not None and float(lo) > float(hi):
            out.append(f"{tkr}: band_lo_px {lo} > band_hi_px {hi}")
        ac = e.get("as_of_close")
        if ac is None or not math.isfinite(float(ac)) or float(ac) <= 0:
            out.append(f"{tkr}: unusable as_of_close {ac!r}")
    return out
