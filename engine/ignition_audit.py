"""Sector-ignition forward ledger — per-market snapshot + deterministic grading.

The sibling of engine/risk_radar_intl_audit.py, for the sector-ignition strip
(engine/sector_ignition.py). Ledger-advancing renders APPEND one row per basket to
data/ignition_log/<market>_ignition.jsonl (idempotent by (as-of, basket); every writer
self-gates on ledger_lane_armed(), so off-lane renders are read-only). Once an entry's
horizon matures it is GRADED against the basket's OWN realized forward excess return vs the
market benchmark: 4-week (h20) and 8-week (h40) basket-minus-benchmark return from the as-of
close. An "igniting"/"running" call is a true-positive when its forward excess is positive.

DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED — the strip never scores off these grades until
the log matures (first single 4w grade ~Aug 2026). Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

HORIZONS = {"h20": 20, "h40": 40}          # 4-week / 8-week business-day forward windows
ALERT_STATES = ("igniting", "running")     # the loud tiers — the ones a scoreboard grades

# ── Pre-registered US-arm grading policy (census PR #4564 charter §4, 2026-08-05) ──
#
# GEOPOLITICAL_EVENT_SECTORS — the canonical single-sector event-bid instruments
# (oil/energy, defense, safe-haven gold). Per the 2026-07-23 suspension ruling
# (research/DO_NOT_REBUILD.md "Ignition Radar user-facing surfaces" row +
# POSTMORTEM_20260723_MAG7_FORCED_CALL_BY_FABLE.md §2): a geopolitical
# single-sector bid is NOT ignition. Items in this set are excluded from
# narrow-channel ranking, logging, and alert TP-rate denominators UNLESS the
# broad channel is in a confirmed "ignited" state (a broad ignition is by
# definition not single-sector). Excluded items are always DISCLOSED — the radar
# payload carries them under narrow.event_excluded and the scorecard prints the
# excluded count — never silently dropped. The set is deliberately minimal;
# extending it is a registry adjudication, not a code edit.
GEOPOLITICAL_EVENT_SECTORS = frozenset({
    "XLE",               # SPDR Energy — the 2026-07-23 war-bid instrument itself
    "energy_complex",    # US Energy Complex basket
    "us_sector_energy",  # Energy (Equal-Weight) sector basket
    "defense",           # Defense & Aerospace basket
    "gold_miners",       # safe-haven gold basket
})

# NARROW_TP_HORIZON — the narrow arm's success criterion, PRE-REGISTERED before
# any narrow grade matured (first h40 maturity ≈ 2026-09-04 for the 2026-07-10
# session row; registered 2026-08-05). An alert-state ("igniting"/"running")
# narrow item is a TRUE POSITIVE iff its basket-minus-SPY excess at the fixed
# h40 horizon (8 weeks — the long end of the same h20/h40 ruler as HK/CA) is
# > 0; false positive otherwise. h20 excess is printed as a secondary
# descriptive stat, never the criterion. Non-alert items grade quiet_up /
# quiet_flat on the same fixed horizon. Items whose basket level cannot be
# loaded at grade time grade "ungradeable" — counted and printed by
# us_scorecard, excluded from rate denominators (excluded counts are always
# shown next to the rate, never silently dropped).
NARROW_TP_HORIZON = "h40"


def event_sector_excluded(item_id: str | None, broad_state: str | None) -> bool:
    """True when item_id is a geopolitical event sector NOT covered by a broad ignition.

    The suspension's exclusion (geopolitical single-sector bids ≠ ignition) applies
    whenever the broad channel is anything short of "ignited" — an event-sector theme
    may rank/grade as ignition only inside a confirmed broad ignition."""
    return (item_id in GEOPOLITICAL_EVENT_SECTORS) and (broad_state != "ignited")


def ledger_lane_armed() -> bool:
    """True only on a ledger-advancing collect lane (COLLECT_LANE=nightly, legacy
    alias US_LANE). House law: nightly is the SOLE advancer of data/ forward
    ledgers. The ignition call sites also run on closing-bell (whose contract,
    closing-bell.yml, is that every ledger writer self-gates on COLLECT_LANE) and
    the engine-render/render re-render lanes; there the strip still renders and
    snapshot_and_grade degrades to a pure scorecard read, but log/grade must not
    advance — appends are idempotent-by-(asof, basket) with FIRST-WRITER-WINS, so
    a mid-session off-lane append would permanently displace the nightly row.
    The HK arm's advancing lane is asia-close (the Asia chain's nightly, commits
    data/), which arms this gate inline on its build_baskets_hk invocation only
    (guarded by tests/test_ignition_lane_gate.py). Sibling gate:
    engine/intl_run._ledger_lane_armed (#2684)."""
    import os
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def _path(market: str, root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "ignition_log" / f"{market}_ignition.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _write(p: Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n")


def _entries_from_snapshot(ign: dict, market: str) -> list[dict]:
    if not ign or not ign.get("as_of") or not ign.get("items"):
        return []
    asof = str(ign["as_of"])
    out = []
    for it in ign["items"]:
        if it.get("ignition_score") is None:
            continue
        out.append({
            "asof": asof,
            "market": market,
            "basket": it.get("id"),
            "name": it.get("name"),
            "ignition_score": it.get("ignition_score"),
            "state": it.get("state"),
            "alert": it.get("state") in ALERT_STATES,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graded": None,
        })
    return out


def log_snapshot(ign: dict, market: str, root=None) -> int:
    """Append today's ignition strip to the market's forward log (idempotent by (asof, basket)).
    Ledger-advancing lanes only (ledger_lane_armed): off-lane calls no-op, returning 0."""
    try:
        if not ledger_lane_armed():
            log.debug("ignition_audit log(%s) skipped: lane not armed", market)
            return 0
        entries = _entries_from_snapshot(ign, market)
        if not entries:
            return 0
        p = _path(market, root)
        rows = _read(p)
        seen = {(r.get("asof"), r.get("basket")) for r in rows}
        added = [e for e in entries if (e["asof"], e["basket"]) not in seen]
        if not added:
            return 0
        rows.extend(added)
        _write(p, rows)
        return len(added)
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit log(%s) failed: %s", market, e)
        return 0


def _grade_entry(entry: dict, basket_lvl: pd.Series, bench_lvl: pd.Series) -> dict | None:
    """Realized forward basket-minus-benchmark excess per horizon from the as-of date.
    None until the longest horizon has matured."""
    asof = pd.Timestamp(entry["asof"])

    def _base_loc(px: pd.Series):
        loc = px.index.searchsorted(asof, side="right")
        return loc

    bl, bnl = basket_lvl.dropna(), bench_lvl.dropna()
    if bl.empty or bnl.empty:
        return None
    loc_b, loc_n = _base_loc(bl), _base_loc(bnl)
    maxH = max(HORIZONS.values())
    if loc_b + maxH > len(bl) or loc_n + maxH > len(bnl):
        return None
    base_b = float(bl.iloc[max(0, loc_b - 1)])
    base_n = float(bnl.iloc[max(0, loc_n - 1)])
    if base_b <= 0 or base_n <= 0:
        return None
    excess, win = {}, {}
    for hk, hd in HORIZONS.items():
        fb = float(bl.iloc[min(loc_b + hd - 1, len(bl) - 1)])
        fn = float(bnl.iloc[min(loc_n + hd - 1, len(bnl) - 1)])
        ex = (fb / base_b - 1.0) - (fn / base_n - 1.0)
        excess[hk] = round(ex, 4)
        win[hk] = bool(ex > 0)
    st = entry.get("state")
    any_pos = any(excess[hk] > 0 for hk in HORIZONS)
    if st in ALERT_STATES:
        outcome = "true_positive" if any_pos else "false_positive"
    else:
        outcome = "quiet_up" if any_pos else "quiet_flat"
    return {"excess": excess, "beat_bench": win, "outcome": outcome,
            "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def grade_log(market: str, level_of, bench_series, root=None) -> int:
    """Grade every matured, ungraded entry against realized basket + benchmark paths.

    level_of      callable(basket_id) -> that basket's level Series (or None)
    bench_series  the benchmark level Series

    Ledger-advancing lanes only (ledger_lane_armed): grades are keep-first-permanent,
    so an off-lane grade computed from a mid-session store would stick — no-op, 0.
    """
    try:
        if not ledger_lane_armed():
            log.debug("ignition_audit grade(%s) skipped: lane not armed", market)
            return 0
        p = _path(market, root)
        rows = _read(p)
        if not rows or bench_series is None:
            return 0
        bench = pd.Series(bench_series).dropna()
        if bench.empty:
            return 0
        cache: dict[str, pd.Series | None] = {}
        n = 0
        for r in rows:
            if r.get("graded"):
                continue
            bid = r.get("basket")
            if bid not in cache:
                try:
                    cache[bid] = level_of(bid)
                except Exception:  # noqa: BLE001
                    cache[bid] = None
            lvl = cache[bid]
            if lvl is None or getattr(lvl, "empty", True):
                continue
            g = _grade_entry(r, pd.Series(lvl), bench)
            if g is not None:
                r["graded"] = g
                n += 1
        if n:
            _write(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit grade(%s) failed: %s", market, e)
        return 0


def scorecard(market: str, root=None) -> dict:
    """Rolling realized-accuracy scorecard from the graded log. Never raises."""
    try:
        rows = [r for r in _read(_path(market, root)) if r.get("graded")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return {"market": market, "n_graded": 0,
                "note": "scoreboard accruing — first read ~Aug 2026 (4w grades mature ~+20 sessions)"}
    n = len(rows)
    alerts = [r for r in rows if r.get("alert")]
    tp = [r for r in alerts if r["graded"]["outcome"] == "true_positive"]
    by_state: dict[str, dict] = {}
    for r in rows:
        d = by_state.setdefault(r.get("state"), {"n": 0, "beat": 0})
        d["n"] += 1
        d["beat"] += int(bool((r["graded"].get("beat_bench") or {}).get("h20")))
    by_state = {k: {"n": v["n"], "beat_rate_4w": round(v["beat"] / v["n"], 3)}
                for k, v in by_state.items()}
    return {
        "market": market,
        "n_graded": n,
        "n_alerts": len(alerts),
        "alert_precision_4w": round(len(tp) / len(alerts), 3) if alerts else None,
        "by_state": by_state,
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]],
    }


def snapshot_and_grade(ign: dict, market: str, level_of, bench_series, root=None) -> dict:
    """Log today's ignition strip, grade matured entries, return the scorecard.

    Off-lane (ledger_lane_armed() False) the log/grade legs no-op and this is a
    pure scorecard read — the scoreboard display stays populated on the
    closing-bell / engine-render / render lanes without advancing the ledger."""
    n_logged = log_snapshot(ign, market, root=root)
    grade_log(market, level_of, bench_series, root=root)
    sc = scorecard(market, root=root)
    sc["n_logged_today"] = n_logged
    return sc


# ---------------------------------------------------------------------------
# US ARM — broad + narrow Ignition Radar forward log
# ---------------------------------------------------------------------------

_US_MARKET = "us"
_US_HORIZONS_BROAD = {"h21": 21, "h63": 63, "h126": 126}   # IGN-R5: SPY absolute return
_US_HORIZONS_NARROW = {"h20": 20, "h40": 40}                # basket-minus-SPY excess, same as HK/CA


def _us_path(root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "ignition_log" / "us_ignition.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _us_read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _us_write(p: Path, rows: list[dict]) -> None:
    p.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n"
    )


def log_us_snapshot(ig: dict, root=None) -> int:
    """Append today's US Ignition Radar snapshot to us_ignition.jsonl.

    One line per underlying US TRADING SESSION (census PR #4564 charter §4): the
    idempotency key is the session — ig["data_session"], the SPY tape date stamped
    by ignition_radar.snapshot() — falling back to the calendar as_of for payloads
    that predate the stamp. Weekend nightly re-runs carry Friday's data_session and
    therefore no-op; a session-less payload with a weekend as_of is refused outright
    (a Saturday/Sunday calendar date never opens a US session — the pre-fix log
    accrued 6 duplicate weekend re-logs this way, quarantined 2026-08-05 into
    us_ignition_quarantine.jsonl). First-writer-wins per session. Ledger-advancing
    lanes only (ledger_lane_armed): off-lane calls no-op, returning 0.

    Returns the number of rows added (0 = already logged / refused).
    """
    try:
        if not ledger_lane_armed():
            log.debug("ignition_audit log_us_snapshot skipped: lane not armed")
            return 0
        if not ig or not ig.get("as_of"):
            return 0
        asof = str(ig["as_of"])
        session = ig.get("data_session") or None
        if session is None:
            # Legacy payload without a tape stamp: calendar-keyed, but a weekend
            # calendar date is definitionally a re-log of Friday's tape — refuse.
            try:
                if pd.Timestamp(asof).dayofweek >= 5:
                    log.debug(
                        "ignition_audit log_us_snapshot skipped: weekend as_of %s "
                        "without data_session", asof,
                    )
                    return 0
            except Exception:  # noqa: BLE001
                pass
        key = str(session or asof)
        p = _us_path(root)
        rows = _us_read(p)
        seen = {str(r.get("session") or r.get("asof")) for r in rows}
        if key in seen:
            return 0
        chips = ig.get("chips") or []
        narrow = ig.get("narrow") or {}
        entry = {
            "asof": asof,
            "session": session,
            "market": _US_MARKET,
            "broad_state": ig.get("state"),
            "k_count": ig.get("k_count"),
            "chips_lit": [c["key"] for c in chips if c.get("lit")],
            "chips_fresh": [c["key"] for c in chips if c.get("fresh")],
            "regime_fragile": (ig.get("regime") or {}).get("fragile", False),
            "regime_label": (ig.get("regime") or {}).get("label_en"),
            "top_narrow": [
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "ignition_score": it.get("ignition_score"),
                    "state": it.get("state"),
                }
                for it in (narrow.get("items") or [])[:5]
            ],
            # audit trail: which items the event-sector exclusion removed from
            # ranking today (ids only) — lets the record show the exclusion
            # operated, so it can itself be audited later.
            "event_excluded": [
                e.get("id") for e in (narrow.get("event_excluded") or []) if e.get("id")
            ],
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "graded_broad": None,
            "graded_narrow": None,
        }
        rows.append(entry)
        _us_write(p, rows)
        return 1
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit log_us_snapshot failed: %s", e)
        return 0


def _grade_us_broad(entry: dict, spy_series) -> dict | None:
    """Grade broad state against SPY forward absolute return + MAE.

    Primary horizons: h21 and h63 (gating horizon — both required to produce a grade).
    h126 is filled independently on a later pass once it matures; existing h21/h63 grades
    are NEVER overwritten (idempotent per-horizon storage).

    Pre-declared per IGN-R5: broad-state grades on SPY absolute return.
    The forward-return base date is the row's underlying SESSION
    (entry["session"]) when stamped, else the calendar as_of (weekend as_of
    dates already resolve to the prior Friday close via searchsorted).
    Returns None when the primary gate horizon h63 has not matured.
    """
    base_date = pd.Timestamp(entry.get("session") or entry["asof"])
    spy = pd.Series(spy_series).dropna()
    spy.index = pd.to_datetime(spy.index)
    loc = spy.index.searchsorted(base_date, side="right")
    # Primary gate: h63 must be mature
    primary_h = _US_HORIZONS_BROAD["h63"]
    if loc + primary_h > len(spy):
        return None
    base = float(spy.iloc[max(0, loc - 1)])
    if base <= 0:
        return None

    # Retrieve any already-stored horizon results so we never overwrite them
    existing = entry.get("graded_broad") or {}
    existing_returns = dict(existing.get("returns") or {})
    existing_mae = dict(existing.get("mae") or {})

    returns = dict(existing_returns)
    mae = dict(existing_mae)

    for hk, hd in _US_HORIZONS_BROAD.items():
        if returns.get(hk) is not None:
            continue  # already graded with a real value — skip (idempotency)
        if loc + hd > len(spy):
            # h126 not matured yet — store as null
            returns[hk] = None
            mae[hk] = None
            continue
        fwd_slice = spy.iloc[loc: loc + hd]
        fwd_val = float(spy.iloc[min(loc + hd - 1, len(spy) - 1)])
        ret = fwd_val / base - 1.0
        returns[hk] = round(ret, 4)
        if not fwd_slice.empty:
            mae[hk] = round(float((fwd_slice.min() / base) - 1.0), 4)
        else:
            mae[hk] = None

    # A "true positive" broad call = subsequent SPY > 0 at h21
    tp = bool((returns.get("h21") or 0) > 0)

    # Preserve the original graded_at timestamp when re-filling h126
    graded_at = existing.get("graded_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "returns": returns,
        "mae": mae,
        "broad_tp": tp,
        "note": (
            "accruing — display-only until >=30 grades + operator ruling. "
            "Graded on SPY absolute return (IGN-R5). h126 filled when mature."
        ),
        "graded_at": graded_at,
    }


def _grade_us_narrow(entry: dict, spy_series) -> dict | None:
    """Grade top narrow items on basket-minus-SPY excess at the fixed h20/h40 horizons.

    PRE-REGISTERED success criterion (2026-08-05, census PR #4564 charter §4 —
    defined before any narrow grade matured; fire conditions untouched):

      * alert-state item (state_at_log in ALERT_STATES): outcome "true_positive"
        iff excess at NARROW_TP_HORIZON (h40) > 0, else "false_positive".
      * non-alert item: "quiet_up" / "quiet_flat" by the same fixed-horizon sign.
      * basket level unavailable or too short at grade time → outcome
        "ungradeable" (no excess fields). Grades are keep-first-permanent, so a
        late-arriving basket history does NOT re-open the item; us_scorecard
        prints the ungradeable count next to every rate.
      * geopolitical event sectors (GEOPOLITICAL_EVENT_SECTORS) logged outside a
        broad "ignited" state carry event_excluded=true — graded for the record
        but excluded from alert TP denominators (suspension 2026-07-23:
        geopolitical single-sector bids ≠ ignition).

    The forward-return base date is the row's underlying SESSION
    (entry["session"], stamped by the session-keyed logger or the 2026-08-05
    heal) when present, else the calendar as_of — whose weekend dates already
    resolve to the prior Friday close via searchsorted. Returns None until h40
    has matured on the SPY path.
    """
    base_date = pd.Timestamp(entry.get("session") or entry["asof"])
    spy = pd.Series(spy_series).dropna()
    spy.index = pd.to_datetime(spy.index)
    loc_spy = spy.index.searchsorted(base_date, side="right")
    max_h = max(_US_HORIZONS_NARROW.values())
    if loc_spy + max_h > len(spy):
        return None
    base_spy = float(spy.iloc[max(0, loc_spy - 1)])
    if base_spy <= 0:
        return None
    # compute spy forward returns as the bench
    spy_rets = {}
    for hk, hd in _US_HORIZONS_NARROW.items():
        fv = float(spy.iloc[min(loc_spy + hd - 1, len(spy) - 1)])
        spy_rets[hk] = fv / base_spy - 1.0
    broad_state = entry.get("broad_state")
    graded_items = []
    for it in entry.get("top_narrow") or []:
        basket_id = it.get("id")
        # try to load basket level from ohlcv / closes
        basket_lvl = None
        try:
            from lib import config as _cfg
            from engine.ignition_radar import _load_etf_series
            # try as ETF first (sector items), then basket
            p_ohlcv = _cfg.data_dir() / "baskets" / "ohlcv" / f"{basket_id}.parquet"
            if p_ohlcv.exists():
                import pandas as _pd
                df = _pd.read_parquet(p_ohlcv)
                if "close" in df.columns:
                    basket_lvl = df["close"].dropna().sort_index().astype(float)
                    basket_lvl.index = _pd.to_datetime(basket_lvl.index)
            elif basket_id and len(basket_id) <= 5:
                basket_lvl = _load_etf_series(basket_id)
        except Exception:  # noqa: BLE001
            pass
        item_grade: dict = {"id": basket_id, "state_at_log": it.get("state")}
        if event_sector_excluded(basket_id, broad_state):
            item_grade["event_excluded"] = True
        if basket_lvl is not None and not basket_lvl.empty:
            loc_b = basket_lvl.index.searchsorted(base_date, side="right")
            if loc_b + max_h <= len(basket_lvl):
                base_b = float(basket_lvl.iloc[max(0, loc_b - 1)])
                if base_b > 0:
                    for hk, hd in _US_HORIZONS_NARROW.items():
                        fv_b = float(basket_lvl.iloc[min(loc_b + hd - 1, len(basket_lvl) - 1)])
                        b_ret = fv_b / base_b - 1.0
                        item_grade[f"excess_{hk}"] = round(b_ret - spy_rets[hk], 4)
        ex_tp = item_grade.get(f"excess_{NARROW_TP_HORIZON}")
        if ex_tp is None:
            item_grade["outcome"] = "ungradeable"
        elif it.get("state") in ALERT_STATES:
            item_grade["outcome"] = "true_positive" if ex_tp > 0 else "false_positive"
        else:
            item_grade["outcome"] = "quiet_up" if ex_tp > 0 else "quiet_flat"
        graded_items.append(item_grade)
    return {
        "items": graded_items,
        "note": (
            "accruing — basket-minus-SPY excess, same ruler as HK/CA (IGN-R5 narrow "
            f"track). Pre-registered criterion: alert TP iff excess_{NARROW_TP_HORIZON} "
            "> 0 (census #4564 §4, 2026-08-05); event sectors excluded from alert "
            "denominators outside broad ignition."
        ),
        "graded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def grade_us_log(spy_series, root=None) -> int:
    """Grade every matured, ungraded US entry against realized SPY path.

    spy_series: SPY close Series.
    Returns number of entries newly graded.

    Ledger-advancing lanes only (ledger_lane_armed): grades are keep-first-permanent,
    so an off-lane grade computed from a mid-session store would stick — no-op, 0.
    """
    try:
        if not ledger_lane_armed():
            log.debug("ignition_audit grade_us_log skipped: lane not armed")
            return 0
        p = _us_path(root)
        rows = _us_read(p)
        if not rows or spy_series is None:
            return 0
        spy = pd.Series(spy_series).dropna()
        spy.index = pd.to_datetime(spy.index)
        n = 0  # counts rows where at least one arm was newly graded
        for r in rows:
            # needs_broad: either no grade yet, OR h126 is null and we can now fill it
            existing_broad = r.get("graded_broad")
            h126_null = (
                existing_broad is not None
                and (existing_broad.get("returns") or {}).get("h126") is None
            )
            needs_broad = not existing_broad or h126_null
            needs_narrow = not r.get("graded_narrow")
            if not (needs_broad or needs_narrow):
                continue
            row_changed = False
            if needs_broad:
                g = _grade_us_broad(r, spy)
                if g is not None:
                    r["graded_broad"] = g
                    row_changed = True
            if needs_narrow:
                g = _grade_us_narrow(r, spy)
                if g is not None:
                    r["graded_narrow"] = g
                    row_changed = True
            if row_changed:
                n += 1
        if n:
            _us_write(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("ignition_audit grade_us_log failed: %s", e)
        return 0


def _us_meta(root=None) -> dict:
    """Read us_ignition_meta.json (known gaps + quarantine provenance). Never raises."""
    try:
        base = config.data_dir() if root is None else (Path(root) / "data")
        p = base / "ignition_log" / "us_ignition_meta.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def us_scorecard(root=None) -> dict:
    """Rolling realized-accuracy scorecard for the US broad/narrow arms.

    Narrow rates follow the pre-registered criterion (NARROW_TP_HORIZON): the
    alert TP rate's denominator is gradeable, non-event-excluded alert items —
    with the event-excluded and ungradeable counts PRINTED beside it, never
    silently dropped. Known log gaps + quarantine counts from us_ignition_meta.json
    are attached so the record discloses its own holes."""
    try:
        rows = [r for r in _us_read(_us_path(root)) if r.get("graded_broad") or r.get("graded_narrow")]
    except Exception:  # noqa: BLE001
        rows = []
    n = len(rows)
    note = "accruing — display-only until >=30 grades + operator ruling"
    meta = _us_meta(root)
    meta_block = None
    if meta:
        gaps = []
        for g in meta.get("known_gaps") or []:
            gaps.extend(g.get("missing_sessions") or [])
        meta_block = {
            "known_missing_sessions": gaps,
            "n_quarantined": (meta.get("quarantine") or {}).get("n_rows"),
        }
    if not rows:
        out = {"market": _US_MARKET, "n_graded": 0, "note": note}
        if meta_block:
            out["log_meta"] = meta_block
        return out
    broad_graded = [r for r in rows if r.get("graded_broad")]
    tp_broad = [r for r in broad_graded if (r["graded_broad"] or {}).get("broad_tp")]

    # narrow arm — item-level aggregation under the pre-registered criterion
    narrow_items: list[dict] = []
    for r in rows:
        gn = r.get("graded_narrow")
        if gn:
            narrow_items.extend(gn.get("items") or [])
    excluded = [i for i in narrow_items if i.get("event_excluded")]
    ungradeable = [
        i for i in narrow_items
        if not i.get("event_excluded") and i.get("outcome") == "ungradeable"
    ]
    gradeable = [
        i for i in narrow_items
        if not i.get("event_excluded") and i.get("outcome") not in (None, "ungradeable")
    ]
    alerts = [i for i in gradeable if i.get("state_at_log") in ALERT_STATES]
    tp_narrow = [i for i in alerts if i.get("outcome") == "true_positive"]
    narrow_block = {
        "criterion": (
            f"alert TP iff basket-minus-SPY excess {NARROW_TP_HORIZON} > 0 "
            "(pre-registered 2026-08-05, census #4564 §4)"
        ),
        "n_items_graded": len(narrow_items),
        "n_alerts_gradeable": len(alerts),
        f"alert_tp_rate_{NARROW_TP_HORIZON}": (
            round(len(tp_narrow) / len(alerts), 3) if alerts else None
        ),
        "n_event_excluded": len(excluded),
        "n_ungradeable": len(ungradeable),
    }

    out = {
        "market": _US_MARKET,
        "n_graded": n,
        "n_broad_graded": len(broad_graded),
        "broad_tp_rate": round(len(tp_broad) / len(broad_graded), 3) if broad_graded else None,
        "narrow": narrow_block,
        "asof_range": [rows[0]["asof"], rows[-1]["asof"]] if rows else None,
        "note": note,
    }
    if meta_block:
        out["log_meta"] = meta_block
    return out


def us_snapshot_and_grade(ig: dict, spy_series, root=None) -> dict:
    """Log today's US ignition snapshot, grade matured entries, return scorecard.

    ig          output of engine.ignition_radar.snapshot()
    spy_series  SPY close Series (load once in caller and reuse)

    Off-lane (ledger_lane_armed() False) the log/grade legs no-op and this is a
    pure scorecard read — closing-bell/engine-render still get the display payload."""
    log_us_snapshot(ig, root=root)
    grade_us_log(spy_series, root=root)
    sc = us_scorecard(root=root)
    sc["note"] = (
        "accruing — display-only until >=30 broad-state grades + operator ruling. "
        "Broad graded on SPY absolute return + MAE at h21/h63 (h126 printed). "
        "Narrow graded on basket-minus-SPY excess at h20/h40 (same ruler as HK/CA, "
        f"IGN-R5); pre-registered narrow criterion: alert TP iff excess_{NARROW_TP_HORIZON} "
        "> 0, event sectors excluded from alert denominators outside broad ignition "
        "(census #4564 §4, 2026-08-05)."
    )
    return sc
