"""engine/rotation_events.py — first-class ROTATION events (Rotation Command W1, RC-R1).

The 2026-06-25 miss (research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md §0): the stack caught
the rotate-OUT of memory everywhere and had no object to express the rotate-IN to the Mag-7
generals, so the handoff surfaced only as adjacent minor alerts while every stance said
avoid. A ROTATION event pairs the two sides explicitly. It fires for an ordered leg pair
(A → B, same registered sector) when, at the evaluated bar, ALL THREE hold:

  (a) leg A shows a BLOWOFF-CRASH signature — a z-scored runup into a recent local high,
      then a hard drawdown off it (the MU/WDC June shape);
  (b) leg B shows a TURN signature — a fresh long-lookback low, a minimum rise off it, and
      a short-horizon reclaim (or a Trough-family phase, when the caller supplies one);
  (c) the B/A pair ratio CONFIRMS — its 10-session change is positive after a recent
      negative stretch (inflection), or the ratio prints a 20-session high.

The three-way AND is what suppresses the naive mid-June misfire: while memory was still
blowing off, (a) had not completed and (c) pointed the other way.

DISPLAY/CONTEXT TIER (promotion-gate law): events carry no authority — no rank, no gate,
no size, no stance words beyond the event chip itself. Deterministic price arithmetic
only; no LLM anywhere. The ledger (data/rotation_events/events.jsonl, append-only) accrues
from day 1 and is EXPECTED-NULL until the RC-R9 pre-registered studies mature; the
2026-06-25 memory→mag7 episode is case zero and earns no retro credit.

Lifecycle: an event stays ACTIVE until the ratio slope goes negative for RATIO_EXIT_RUN
consecutive sessions, the conditions lapse for LAPSE_RUN consecutive sessions, or TTL
sessions elapse — whichever first. A closed pair is locked out for LOCKOUT sessions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

SCHEMA = "rotation_events.v1"

# Detector parameters — one dict so the RC-R8 replay and any RC-R9 prereg tune ONE place
# (and so the payload can disclose exactly what fired the receipts).
PARAMS = {
    "runup_min": 0.15,        # (a) minimum blowoff runup into the peak
    "runup_z_min": 2.0,       # (a) 20d-return z-score at the peak vs its own trailing year
    "runup_strong": 0.30,     # (a) absolute runup that qualifies even when the z fails —
                              #     a year-long melt-up inflates its own trailing ret20
                              #     distribution (memory June 2026: +47%/20s scored z=1.6)
    "crash_min": 0.10,        # (a) minimum drawdown off the peak
    "peak_within": 25,        # (a) peak must sit inside this many trailing sessions
    "runup_window": 25,       # (a) runup measured from the low of this window before the peak
    "z_obs_min": 150,         # (a) minimum 20d-return observations to trust the z-score
    "low_lookback": 40,       # (b) the turn low must be a low of this many sessions
    "low_within": 15,         # (b) ...printed inside this many trailing sessions
    "min_off_low": 0.03,      # (b) minimum rise off the low
    "reclaim_len": 5,         # (b) close above the max of the prior N closes
    "reclaim_recent": 5,      # (b) ...at least once in the last N sessions
    "slope_len": 10,          # (c) ratio change horizon
    "flip_within": 7,         # (c) slope must have been negative inside this window
    "ratio_high_len": 20,     # (c) alternative: ratio prints an N-session high
    "start_backscan": 12,     # earliest-continuous-true search depth for `started`
    "coldstart_backscan": 15,  # first-ever run replays this many sessions of lifecycle
    "ttl_sessions": 20,       # lifecycle: hard time-to-live
    "lapse_run": 5,           # lifecycle: close after N consecutive non-firing sessions
    "ratio_exit_run": 3,      # lifecycle: close after N consecutive negative-slope sessions
    "lockout_sessions": 10,   # closed pair can't re-fire for N sessions
    "sev_crash_bump": 0.18,   # severity bump: out-leg crash at least this deep...
    "sev_offlow_bump": 0.08,  #   ...and in-leg at least this far off its low
}


# ------------------------------------------------------------------ signatures ----

def blowoff_crash(close: pd.Series, p: dict = PARAMS) -> dict | None:
    """(a) Leg-A signature: z-scored runup into a recent local high, then a hard drawdown.
    None when it doesn't hold — including when history is too thin for an honest z-score."""
    s = close.dropna()
    if len(s) < p["peak_within"] + p["runup_window"] + 40:
        return None
    tail = s.iloc[-p["peak_within"]:]
    peak_date = tail.idxmax()
    peak = float(tail.loc[peak_date])
    if peak_date == s.index[-1]:
        return None                                   # still making highs — no crash yet
    ppos = int(s.index.get_loc(peak_date))
    base = float(s.iloc[max(0, ppos - p["runup_window"]):ppos + 1].min())
    if base <= 0:
        return None
    runup = peak / base - 1.0
    ret20 = s.pct_change(20)
    hist = ret20.iloc[:ppos + 1].dropna().iloc[-252:]
    if len(hist) < p["z_obs_min"]:
        return None                                   # thin history → no claim
    sd = float(hist.std())
    if not sd or not np.isfinite(sd):
        return None
    runup_z = (float(ret20.iloc[ppos]) - float(hist.mean())) / sd
    drawdown = 1.0 - float(s.iloc[-1]) / peak
    abnormal = runup_z >= p["runup_z_min"] or runup >= p["runup_strong"]
    if runup >= p["runup_min"] and abnormal and drawdown >= p["crash_min"]:
        return {"peak_date": str(peak_date.date()), "runup_pct": round(runup, 4),
                "runup_z": round(runup_z, 2), "drawdown_pct": round(drawdown, 4),
                "qualified_by": "z" if runup_z >= p["runup_z_min"] else "abs_runup"}
    return None


def turn_up(close: pd.Series, p: dict = PARAMS, phase: str | None = None) -> dict | None:
    """(b) Leg-B signature: fresh long-lookback low + minimum rise off it + short reclaim
    (or a Trough-family phase from the caller — the cycle engine's read, when supplied)."""
    s = close.dropna()
    if len(s) < p["low_lookback"] + 5:
        return None
    win = s.iloc[-p["low_lookback"]:]
    low_date = win.idxmin()
    low = float(win.loc[low_date])
    lpos_from_end = len(win) - 1 - int(win.index.get_loc(low_date))
    if lpos_from_end > p["low_within"] or low <= 0:
        return None
    off_low = float(s.iloc[-1]) / low - 1.0
    if off_low < p["min_off_low"]:
        return None
    rec = s > s.shift(1).rolling(p["reclaim_len"]).max()
    reclaimed = bool(rec.iloc[-p["reclaim_recent"]:].any())
    phase_turn = phase in ("Trough", "Recovery")
    if not (reclaimed or phase_turn):
        return None
    return {"low_date": str(low_date.date()), "off_low_pct": round(off_low, 4),
            "reclaimed": reclaimed, **({"phase": phase} if phase else {})}


def pair_confirm(close_in: pd.Series, close_out: pd.Series, p: dict = PARAMS) -> dict | None:
    """(c) The B/A ratio confirms: positive 10-session change after a recent negative
    stretch (inflection), or a fresh 20-session ratio high."""
    ratio = (close_in / close_out).dropna()
    if len(ratio) < p["ratio_high_len"] + p["slope_len"] + 5:
        return None
    sl = ratio.pct_change(p["slope_len"])
    cur = float(sl.iloc[-1])
    if not np.isfinite(cur):
        return None
    inflected = cur > 0 and float(sl.iloc[-p["flip_within"]:].min()) < 0
    ratio_high = float(ratio.iloc[-1]) >= float(ratio.iloc[-p["ratio_high_len"]:].max())
    if not (inflected or ratio_high):
        return None
    return {"ratio_chg_10s": round(cur, 4), "inflected": bool(inflected),
            "ratio_20s_high": bool(ratio_high)}


def evaluate_pair(close_out: pd.Series, close_in: pd.Series,
                  p: dict = PARAMS, phase_in: str | None = None,
                  _blowoff_cache: dict | None = None) -> dict | None:
    """All three signatures at the last common bar, or None. `_blowoff_cache` (optional,
    keyed on the out-leg object + evaluation date) lets step_pairs/the RC-R8 replay skip
    recomputing one out-leg's blowoff for each of its N peer in-legs — pure memo, no
    behavior change."""
    idx = close_out.dropna().index.intersection(close_in.dropna().index)
    if len(idx) == 0:
        return None
    if _blowoff_cache is not None:
        key = (id(close_out), idx[-1])
        if key not in _blowoff_cache:
            _blowoff_cache[key] = blowoff_crash(close_out.loc[:idx[-1]], p)
        a = _blowoff_cache[key]
    else:
        a = blowoff_crash(close_out.loc[:idx[-1]], p)
    if a is None:
        return None
    b = turn_up(close_in.loc[:idx[-1]], p, phase=phase_in)
    if b is None:
        return None
    c = pair_confirm(close_in.loc[:idx[-1]], close_out.loc[:idx[-1]], p)
    if c is None:
        return None
    return {"blowoff": a, "turn": b, "ratio": c, "asof": str(idx[-1].date())}


def find_start(close_out: pd.Series, close_in: pd.Series,
               p: dict = PARAMS, phase_in: str | None = None) -> str:
    """Earliest session (within start_backscan) from which evaluate_pair has been TRUE
    continuously through the last bar — the honest `started` date for day-N counting."""
    idx = close_out.dropna().index.intersection(close_in.dropna().index)
    started = idx[-1]
    for k in range(2, min(p["start_backscan"], len(idx) - 1) + 1):
        d = idx[-k]
        if evaluate_pair(close_out.loc[:d], close_in.loc[:d], p, phase_in) is None:
            break
        started = d
    return str(started.date())


# ------------------------------------------------------------------ lifecycle ----

def _sessions_between(dates: list[str], a: str, b: str) -> int:
    """Trading sessions from a to b inclusive-of-b (0 if a==b), on the pair calendar.
    If `a` predates the calendar (e.g. scrolled out of a WINDOWED series in the RC-R8
    replay), it was LONG ago — return a large count, never 0: a 0 here once made a
    closed pair's re-fire lockout permanent."""
    try:
        ia = dates.index(a)
    except ValueError:
        return 10**6 if (dates and a < dates[0]) else 0
    try:
        return max(0, dates.index(b) - ia)
    except ValueError:
        return 0


def severity(out_cfg: dict, in_cfg: dict, receipts: dict, p: dict = PARAMS) -> str:
    """Hand-declared leg tiers (see config/sector_legs.json notes.tiers) + move size.
    {standard, notable, major} — major only when a cap-share-dominant leg is involved
    or the move sizes clear the bump bars on both sides."""
    tiers = {out_cfg.get("tier"), in_cfg.get("tier")}
    lvl = 2 if tiers == {"primary"} else (1 if "primary" in tiers else 0)
    if (receipts["blowoff"]["drawdown_pct"] >= p["sev_crash_bump"]
            and receipts["turn"]["off_low_pct"] >= p["sev_offlow_bump"]):
        lvl = min(2, lvl + 1)
    return ("standard", "notable", "major")[lvl]


def _copy(sec: dict, out_cfg: dict, in_cfg: dict, receipts: dict, day_n: int) -> tuple[str, str]:
    dd = receipts["blowoff"]["drawdown_pct"]
    off = receipts["turn"]["off_low_pct"]
    low_d = receipts["turn"]["low_date"]
    en = (f"Rotation — out of {out_cfg['name_en']}, into {in_cfg['name_en']} "
          f"(day {day_n}): {out_cfg['name_en']} −{dd:.0%} off its blowoff high while "
          f"{in_cfg['name_en']} is +{off:.1%} off its {low_d} low and the "
          f"{in_cfg['name_en']}/{out_cfg['name_en']} ratio is turning up.")
    zh = (f"轮动 — 资金自{out_cfg['name_zh']}转向{in_cfg['name_zh']}（第{day_n}天）："
          f"{out_cfg['name_zh']}较冲顶高点回落{dd:.0%}，{in_cfg['name_zh']}自{low_d}低点"
          f"回升{off:.1%}，两者比值拐头向上。")
    return en, zh


def step_pairs(sectors: dict, state: dict, p: dict = PARAMS) -> tuple[dict, list, list, list]:
    """One nightly step over every registered ordered pair.

    sectors: sector_legs.sector_closes() output. state: the persisted lifecycle dict
    {"active": {pair_id: {...}}, "closed": {pair_id: last_close_asof}}. Pure — no I/O.
    Returns (new_state, active_events, created, closed)."""
    active_prev = dict(state.get("active") or {})
    closed_prev = dict(state.get("closed") or {})
    active_out: dict = {}
    events_active: list = []
    created: list = []
    closed: list = []
    blowoff_cache: dict = {}          # one out-leg's blowoff shared across its N in-legs

    for skey, sec in sectors.items():
        cfg = sec["cfg"]
        legs_cfg = {l["key"]: l for l in cfg.get("legs", [])}
        legs = sec["legs"]
        for out_key, close_out in legs.items():
            for in_key, close_in in legs.items():
                if in_key == out_key:
                    continue
                pair_id = f"{skey}:{out_key}->{in_key}"
                idx = close_out.dropna().index.intersection(close_in.dropna().index)
                if len(idx) < 60:
                    continue
                dates = [str(d.date()) for d in idx]
                asof = dates[-1]
                receipts = evaluate_pair(close_out, close_in, p,
                                         _blowoff_cache=blowoff_cache)
                prev = active_prev.get(pair_id)

                # ratio-slope exit counter (runs whether or not the pair fired tonight)
                sl = (close_in / close_out).dropna().pct_change(p["slope_len"])
                neg_run = 0
                for v in reversed(sl.to_numpy()):
                    if np.isfinite(v) and v < 0:
                        neg_run += 1
                    else:
                        break

                if prev is None and receipts is not None:
                    last_closed = closed_prev.get(pair_id)
                    if last_closed and _sessions_between(dates, last_closed, asof) <= p["lockout_sessions"]:
                        continue                       # lockout — no re-fire churn
                    started = find_start(close_out, close_in, p)
                    ev = {"pair_id": pair_id, "sector": skey,
                          "from_leg": out_key, "to_leg": in_key,
                          "started": started, "lapse_count": 0}
                    active_out[pair_id] = ev
                    created.append(pair_id)
                    prev = ev
                elif prev is not None:
                    prev = dict(prev)
                    prev["lapse_count"] = 0 if receipts is not None else prev.get("lapse_count", 0) + 1
                    active_out[pair_id] = prev

                if prev is None:
                    continue

                day_n = _sessions_between(dates, prev["started"], asof) + 1
                reason = None
                if neg_run >= p["ratio_exit_run"]:
                    reason = "ratio_slope_flipped"
                elif prev["lapse_count"] >= p["lapse_run"]:
                    reason = "conditions_lapsed"
                elif day_n > p["ttl_sessions"]:
                    reason = "ttl"
                if reason:
                    active_out.pop(pair_id, None)
                    closed_prev[pair_id] = asof
                    closed.append({"pair_id": pair_id, "sector": skey, "from_leg": out_key,
                                   "to_leg": in_key, "started": prev["started"],
                                   "closed_asof": asof, "reason": reason, "day_n": day_n})
                    continue

                # event row for the display payload (receipts may be tonight's or, during a
                # short lapse, absent — the chip persists, the receipts say last-confirmed)
                out_cfg, in_cfg = legs_cfg[out_key], legs_cfg[in_key]
                rc = receipts or prev.get("last_receipts")
                if receipts is not None:
                    active_out[pair_id]["last_receipts"] = receipts
                if rc is None:
                    continue
                sev = severity(out_cfg, in_cfg, rc, p)
                en, zh = _copy(cfg, out_cfg, in_cfg, rc, day_n)
                events_active.append({
                    "id": pair_id, "sector": skey,
                    "sector_name_en": cfg["name_en"], "sector_name_zh": cfg["name_zh"],
                    "from_leg": {"key": out_key, "name_en": out_cfg["name_en"],
                                 "name_zh": out_cfg["name_zh"], "tier": out_cfg.get("tier")},
                    "to_leg": {"key": in_key, "name_en": in_cfg["name_en"],
                               "name_zh": in_cfg["name_zh"], "tier": in_cfg.get("tier")},
                    "started": prev["started"], "day_n": day_n, "asof": asof,
                    "severity": sev, "receipts": rc,
                    "confirmed_tonight": receipts is not None,
                    "copy_en": en, "copy_zh": zh,
                })

    new_state = {"active": active_out, "closed": closed_prev}
    return new_state, events_active, created, closed


_CROSS_EVENT_TYPES = frozenset({"into_strength", "cross_handoff", "correlation_break"})


def to_alerts(payload: dict) -> list[dict]:
    """RC-R5: one alert per event CREATED tonight, in the rotation-alerts schema
    (engine.subsector_rotation_alerts / engine.alert_triage pick it up with zero new
    plumbing). Rotation events get their own type + honest severity mapping instead of
    drowning among per-node minor flow alerts (the 06-30 Social-Media alert was correct
    and invisible). Active-but-not-new events do NOT re-alert.

    v1 branch: events from step_pairs carry from_leg/to_leg/sector_name_en/sector_name_zh.
    v2 cross branch: events from step_cross_pairs carry donor/receiver/from_sector/to_sector
      and event_type in {into_strength, cross_handoff, correlation_break}.
    """
    out = []
    created = set(payload.get("created_tonight") or [])
    ts = payload.get("generated_utc") or payload.get("as_of") or ""
    for ev in payload.get("active", []):
        if ev["id"] not in created:
            continue
        sev = "high" if ev["severity"] == "major" else "minor"
        bucket = (ev.get("asof") or payload.get("as_of") or "")[:10]
        event_type = ev.get("event_type", "handoff")

        if event_type in _CROSS_EVENT_TYPES:
            # v2 cross event: donor/receiver dicts carry label_en/label_zh
            donor = ev.get("donor") or {}
            receiver = ev.get("receiver") or {}
            donor_en = donor.get("name_en") or donor.get("key") or ev.get("from_sector", "")
            donor_zh = donor.get("name_zh") or donor_en
            recv_en = receiver.get("name_en") or receiver.get("key") or ev.get("to_sector", "")
            recv_zh = receiver.get("name_zh") or recv_en
            sector_en = ev.get("from_sector") or ev.get("to_sector") or ""
            sector_zh = sector_en
            type_label_en = {
                "into_strength": "Cross-sector strength rotation",
                "cross_handoff": "Cross-sector handoff",
                "correlation_break": "Correlation break",
            }.get(event_type, "Cross-sector rotation event")
            type_label_zh = {
                "into_strength": "跨板块强势轮动",
                "cross_handoff": "跨板块交棒",
                "correlation_break": "相关性断裂",
            }.get(event_type, "跨板块轮动事件")
            hl = f"⟲ {type_label_en} — {donor_en} → {recv_en}"
            if sector_en:
                hl += f" ({sector_en})"
            hl_zh = f"⟲ {type_label_zh} — {donor_zh} → {recv_zh}"
            if sector_zh:
                hl_zh += f"（{sector_zh}）"
            det = (f"{type_label_en}: {donor_en} → {recv_en}. "
                   "Display-tier context (Rotation Command v2) — ledgered, expected-NULL; not a buy list.")
            det_zh = (f"{type_label_zh}：{donor_zh} → {recv_zh}。"
                      "展示层上下文（Rotation Command v2）——已入账、预期无效应声明；非买入清单。")
        else:
            # v1 intra-sector event: from_leg/to_leg/sector_name_en/sector_name_zh
            hl = (f"⟲ Rotation event — {ev['from_leg']['name_en']} → {ev['to_leg']['name_en']} "
                  f"({ev['sector_name_en']})")
            hl_zh = (f"⟲ 轮动事件 — {ev['from_leg']['name_zh']} → {ev['to_leg']['name_zh']}"
                     f"（{ev['sector_name_zh']}）")
            det = ev["copy_en"] + " Display-tier context (Rotation Command W1) — ledgered, expected-NULL; not a buy list."
            det_zh = ev["copy_zh"] + " 展示层上下文（Rotation Command W1）——已入账、预期无效应声明；非买入清单。"

        out.append({"id": f"rotation:us:rotation_event:{ev['id']}:{bucket}",
                    "ts": ts, "source": "rotation", "asset": ev["id"],
                    "type": "rotation_event", "severity": sev,
                    "headline": hl, "detail": det,
                    "headline_zh": hl_zh, "detail_zh": det_zh,
                    "context": {"severity": ev["severity"], "day_n": ev["day_n"],
                                "started": ev["started"], "receipts": ev.get("receipts"),
                                "event_type": event_type},
                    "anchor": "#rc-events"})
    return out


# ------------------------------------------------------------------ nightly I/O ----

def _truncate_sectors(sectors: dict, cut: pd.Timestamp) -> dict:
    return {k: {"cfg": s["cfg"], "etf_close": s["etf_close"].loc[:cut],
                "legs": {lk: ls.loc[:cut] for lk, ls in s["legs"].items()},
                "leg_meta": s.get("leg_meta", {})}
            for k, s in sectors.items()}


def coldstart_replay(sectors: dict, p: dict = PARAMS) -> tuple[dict, list, list]:
    """First-ever run: replay the lifecycle over the trailing coldstart_backscan sessions
    so a mid-episode deploy doesn't miss events whose CREATION window (the ratio
    inflection) already passed — the exact rule, just stepped from N sessions back.
    Deterministic; ledger rows from the replay are stamped tonight and flagged
    `replayed`, so this earns no retro credit (masterplan RC-R15: case zero grades
    prospectively). Returns (state, created_rows, closed_rows)."""
    cal = sorted({d for s in sectors.values()
                  for d in s["etf_close"].dropna().index[-p["coldstart_backscan"]:]})
    state: dict = {}
    created_rows: list = []
    closed_rows: list = []
    for cut in cal[:-1]:
        state, act, created, closed = step_pairs(_truncate_sectors(sectors, cut), state, p)
        for pid in created:
            ev = next((e for e in act if e["id"] == pid), None)
            if ev:
                created_rows.append({**ev, "replayed": True})
        closed_rows += [{**c, "replayed": True} for c in closed]
    return state, created_rows, closed_rows


# ======================================================================
# Rotation Events v2 — cross-sector families and extended lifecycle
# All functions below are ADDITIVE; v1 functions above are untouched.
# NOTE: run_nightly is defined once below (v2, at ~line 1062) and handles both
# the v1-only path (universe=None) and the v2 path.  There is NO second
# definition here — the dead v1 stub was removed (R-B1 consolidation).
# ======================================================================

# ------------------------------------------------------------------ lane gate ----

def _ledger_lane_armed() -> bool:
    """Return True only when COLLECT_LANE==nightly (case-insensitive).
    Off-lane: payload + state snapshot render; no events.jsonl append."""
    return (os.environ.get("COLLECT_LANE", "") or "").lower() == "nightly"


# ------------------------------------------------------------------ family C — donor_state ----

def donor_state(close: pd.Series, bench: pd.Series, p: dict = PARAMS) -> str | None:
    """Family C: donor leg signature — blowoff or contagion_bleed, or None.

    blowoff        : blowoff_crash(close) fires (reused verbatim from v1)
    contagion_bleed: close <= min(last bleed_low_lookback) * bleed_low_tol
                     AND SPY-relative 20d return (rs20) <= bleed_rs20_max
                     AND NOT blowoff

    FINDING 8 fix: rs20 is SPY-relative (not absolute), so a donor falling merely
    with the broad market (rs20≈0) does NOT qualify as contagion_bleed.
    """
    from engine.rotation_universe import PARAMS_V2
    lookback = PARAMS_V2["bleed_low_lookback"]
    tol = PARAMS_V2["bleed_low_tol"]
    rs20_max = PARAMS_V2["bleed_rs20_max"]

    s = close.dropna()
    if len(s) < lookback + 5:
        return None

    # blowoff check first (reused verbatim)
    if blowoff_crash(s, p) is not None:
        return "blowoff"

    # contagion_bleed
    win_min = float(s.iloc[-lookback:].min())
    at_low = float(s.iloc[-1]) <= win_min * tol

    if not at_low:
        return None

    # SPY-relative 20d return
    b = bench.reindex(s.index).ffill()
    if len(b.dropna()) < 22:
        return None
    rs20 = float(s.pct_change(20).iloc[-1]) - float(b.pct_change(20).iloc[-1])
    if not np.isfinite(rs20):
        return None

    if rs20 <= rs20_max:
        return "contagion_bleed"
    return None


# ------------------------------------------------------------------ family B — into_strength ----

def into_strength(
    receiver: pd.Series,
    donor: pd.Series,
    bench: pd.Series,
    breadth_recv: float | None,
    breadth_donor: float | None,
    breadth_recv_series: pd.Series | None = None,
) -> dict | None:
    """Family B: receiver is already leading the tape (XLV blind-spot fix).

    Fires when ALL hold:
      off_low  : receiver >= min(last bleed_low_lookback) * (1 + into_off_low_min)
      leading  : rs20(receiver) >= into_rel_lead (SPY-relative, FINDING 7)
      ratio    : ratio 20d change >= into_ratio_chg_min  OR  ratio at 20d high
      breadth  : breadth_recv >= into_breadth_min AND rising AND > breadth_donor

    FINDING 4 fix: ratio 20d high check is the OR-branch; the primary branch is the
    20d ratio change. Both are computed and disclosed in the receipt.
    """
    from engine.rotation_universe import PARAMS_V2
    low_lb = PARAMS_V2["bleed_low_lookback"]
    off_low_min = PARAMS_V2["into_off_low_min"]
    rel_lead = PARAMS_V2["into_rel_lead"]
    ratio_chg_min = PARAMS_V2["into_ratio_chg_min"]
    brd_min = PARAMS_V2["into_breadth_min"]
    brd_rise_len = PARAMS_V2["into_breadth_rise_len"]

    sr = receiver.dropna()
    sd = donor.dropna()
    b = bench.dropna()

    if len(sr) < low_lb + 5 or len(sd) < low_lb + 5:
        return None

    # off_low gate
    win_min_recv = float(sr.iloc[-low_lb:].min())
    if win_min_recv <= 0:
        return None
    off_low = float(sr.iloc[-1]) / win_min_recv - 1.0
    if off_low < off_low_min:
        return None

    # receiver must NOT be at a 40d low (it's leading, not bottoming)
    # (the off_low > 8% gate already ensures this)

    # SPY-relative 20d return for receiver
    b_r = b.reindex(sr.index).ffill()
    if len(b_r.dropna()) < 22:
        return None
    rs20_recv = float(sr.pct_change(20).iloc[-1]) - float(b_r.pct_change(20).iloc[-1])
    if not np.isfinite(rs20_recv) or rs20_recv < rel_lead:
        return None

    # ratio gate (FINDING 4: primary is 20d change, OR branch is 20d high)
    idx = sr.index.intersection(sd.index)
    if len(idx) < 22:
        return None
    ratio = (sr.reindex(idx) / sd.reindex(idx)).dropna()
    if len(ratio) < 22:
        return None
    ratio_cur = float(ratio.iloc[-1])
    ratio_20d_ago = float(ratio.iloc[-21])
    if ratio_20d_ago <= 0:
        return None
    ratio_chg_20s = ratio_cur / ratio_20d_ago - 1.0
    ratio_20s_high = bool(ratio_cur >= float(ratio.iloc[-20:].max()))
    ratio_ok = (ratio_chg_20s >= ratio_chg_min) or ratio_20s_high
    if not ratio_ok:
        return None

    # breadth gate
    if breadth_recv is None or breadth_recv < brd_min:
        return None
    if breadth_donor is not None and breadth_recv <= breadth_donor:
        return None

    # breadth rising over brd_rise_len sessions
    brd_rising = False
    if breadth_recv_series is not None and len(breadth_recv_series.dropna()) >= brd_rise_len + 1:
        tail = breadth_recv_series.dropna().iloc[-(brd_rise_len + 1):]
        brd_rising = bool(float(tail.iloc[-1]) > float(tail.iloc[0]))
    if not brd_rising:
        return None

    return {
        "off_low_pct": round(off_low, 4),
        "rs20": round(rs20_recv, 4),
        "ratio_chg_20s": round(ratio_chg_20s, 4),
        "ratio_20s_high": ratio_20s_high,
        "breadth_above50": round(breadth_recv * 100, 2) if breadth_recv is not None else None,
        "breadth_rising": brd_rising,
        "breadth_above_donor": bool(breadth_donor is None or breadth_recv > breadth_donor),
    }


# ------------------------------------------------------------------ cross-pair evaluator ----

def evaluate_cross(
    donor_close: pd.Series,
    receiver_close: pd.Series,
    bench: pd.Series,
    breadth_recv: float | None = None,
    breadth_donor: float | None = None,
    breadth_recv_series: pd.Series | None = None,
    p: dict = PARAMS,
) -> dict | None:
    """Evaluate a cross-sector pair using v2 families B+C+pair_confirm.

    event_type is derived from which family branch fires:
      "into_strength"  — if receiver leads (B branch via into_strength)
      "cross_handoff"  — if donor shows blowoff AND receiver shows turn_up (classic)
      None             — if no event

    donor_signature: "blowoff" | "contagion_bleed" | None

    Returns a receipts dict (analogous to evaluate_pair for intra-sector) or None.
    """
    # align to common index
    idx = (donor_close.dropna().index
           .intersection(receiver_close.dropna().index)
           .intersection(bench.dropna().index))
    if len(idx) < 60:
        return None
    d_cl = donor_close.loc[:idx[-1]]
    r_cl = receiver_close.loc[:idx[-1]]
    b_cl = bench.loc[:idx[-1]]

    # Family C: donor state
    d_state = donor_state(d_cl, b_cl, p)
    if d_state is None:
        return None     # no cross event without a donor signature

    # Family B: into_strength (primary branch for 07-17 case)
    into = into_strength(r_cl, d_cl, b_cl,
                         breadth_recv, breadth_donor, breadth_recv_series)
    if into is not None:
        # pair_confirm as a corroborating receipt (not a gate here — B already fires)
        pc = pair_confirm(r_cl, d_cl, p)
        asof = str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1])
        return {
            "event_type": "into_strength",
            "donor_signature": d_state,
            "donor": {
                "state": d_state,
                "rs20": None,   # populated by caller with SPY-rel 20d
                "at_40d_low": True,
                "asof": asof,
            },
            "receiver": into,
            "ratio": pc,
            "blowoff": None,
            "turn": None,
            "asof": asof,
        }

    # Classic blowoff + turn_up branch (cross_handoff)
    if d_state == "blowoff":
        b_rec = turn_up(r_cl, p)
        if b_rec is not None:
            c_rec = pair_confirm(r_cl, d_cl, p)
            if c_rec is not None:
                a_rec = blowoff_crash(d_cl, p)
                asof = str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1])
                return {
                    "event_type": "cross_handoff",
                    "donor_signature": "blowoff",
                    "donor": {"state": "blowoff", "asof": asof},
                    "receiver": b_rec,
                    "ratio": c_rec,
                    "blowoff": a_rec,
                    "turn": b_rec,
                    "asof": asof,
                }

    return None


# ------------------------------------------------------------------ cross-pair lifecycle ----

def _cross_find_start(
    dates: list[str],
    asof: str,
    start_backscan: int,
) -> str:
    """Find-start analogue for cross pairs (R-m1).

    Backtracks from asof up to start_backscan sessions to find the earliest
    session in the current continuous run.  Mirrors find_start (:178) for
    intra-sector pairs.  Returns the earliest date within start_backscan of
    asof that is part of a continuous sequence ending at asof.
    """
    if asof not in dates:
        return asof
    idx = dates.index(asof)
    earliest = idx
    max_back = max(0, idx - start_backscan)
    for i in range(idx - 1, max_back - 1, -1):
        earliest = i
    return dates[max(0, earliest)]


def step_cross_pairs(
    universe: dict,
    closes: dict[str, pd.Series],
    bench: pd.Series,
    state: dict,
    breadth_by_sector: dict | None = None,
    breadth_series_by_sector: dict | None = None,
    p2: dict | None = None,
) -> tuple[dict, list, list, list]:
    """One nightly step over all registered cross-sector pairs.

    R-B2 FIX: Candidates accrue confirm_streak in a SEPARATE ``candidates`` dict
    and are EXCLUDED from active_out (and from the payload active[] list, and from
    any ledger write) until confirm_streak reaches confirm_days.  On the night
    confirm_streak reaches confirm_days, the event is set announced=True, emitted
    in ``created`` (ledger row + alert fire, exactly once), and from then on it is
    a normal active event.

    State layout (stored in cross_state.json):
      {
        "active":     {pair_id: event_dict},        # confirmed & announced events
        "candidates": {pair_id: candidate_dict},    # pre-confirmation; never in active
        "closed":     {pair_id: last_close_asof},
      }

    Mirrors step_pairs (lines 235-335) lifecycle verbatim: creation via
    find_start analogue (R-m1), lockout, lapse_count, neg_run, ttl.
    """
    from engine.rotation_universe import PARAMS_V2
    p = p2 or PARAMS_V2

    series_index = {s["key"]: s for s in universe.get("series", [])}
    active_prev = dict(state.get("active") or {})
    candidates_prev = dict(state.get("candidates") or {})
    closed_prev = dict(state.get("closed") or {})
    active_out: dict = {}
    candidates_out: dict = {}
    events_active: list = []
    created: list = []
    closed: list = []
    bbd = breadth_by_sector or {}
    bbs = breadth_series_by_sector or {}

    confirm_days = p.get("confirm_days", PARAMS_V2["confirm_days"])
    start_backscan = p.get("start_backscan", PARAMS.get("start_backscan", 12))

    for pair_cfg in universe.get("pairs", []):
        pair_id = pair_cfg["id"]
        donor_key = pair_cfg["donor"]
        recv_key = pair_cfg["receiver"]
        tier = pair_cfg.get("tier", "secondary")

        d_cl = closes.get(donor_key)
        r_cl = closes.get(recv_key)
        if d_cl is None or r_cl is None:
            continue

        # receiver/donor breadth from spec sector mapping
        d_spec = series_index.get(donor_key, {})
        r_spec = series_index.get(recv_key, {})
        d_sector = d_spec.get("sector", donor_key)
        r_sector = r_spec.get("sector", recv_key)

        breadth_recv = bbd.get(r_sector)
        breadth_donor = bbd.get(d_sector)
        breadth_recv_series = bbs.get(r_sector)

        idx = d_cl.dropna().index.intersection(r_cl.dropna().index)
        if len(idx) < 60:
            continue
        dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in idx]
        asof = dates[-1]

        receipts = evaluate_cross(d_cl, r_cl, bench,
                                  breadth_recv, breadth_donor, breadth_recv_series)

        # ratio-slope neg_run (same as step_pairs)
        sl = (r_cl / d_cl).dropna().pct_change(p.get("slope_len", PARAMS["slope_len"]))
        neg_run_cur = 0
        for v in reversed(sl.to_numpy()):
            if np.isfinite(v) and v < 0:
                neg_run_cur += 1
            else:
                break

        lapse_run = p.get("lapse_run", PARAMS["lapse_run"])
        ttl = p.get("ttl_sessions", PARAMS["ttl_sessions"])
        lockout = p.get("lockout_sessions", PARAMS_V2["lockout_sessions"])
        ratio_exit_run = p.get("ratio_exit_run", PARAMS["ratio_exit_run"])

        # ----------------------------------------------------------------
        # CANDIDATE PHASE (pre-confirmation, excluded from active_out)
        # ----------------------------------------------------------------
        active_ev = active_prev.get(pair_id)
        cand_ev = candidates_prev.get(pair_id)

        if active_ev is None and cand_ev is None and receipts is not None:
            # Night 1: first fire — enter candidate state (NOT active_out yet)
            last_closed = closed_prev.get(pair_id)
            if last_closed and _sessions_between(dates, last_closed, asof) <= lockout:
                continue
            # R-m1: backdate started to earliest continuous session within start_backscan
            started = _cross_find_start(dates, asof, start_backscan)
            candidates_out[pair_id] = {
                "pair_id": pair_id,
                "donor": donor_key,
                "receiver": recv_key,
                "tier": tier,
                "started": started,
                "lapse_count": 0,
                "confirm_streak": 1,
                "last_receipts": receipts,
            }
            # Do NOT add to active_out or events_active yet — not confirmed
            continue

        if active_ev is None and cand_ev is not None:
            # Still in candidate phase: update streak
            cand_ev = dict(cand_ev)
            fired = receipts is not None
            if fired:
                cand_ev["confirm_streak"] = cand_ev.get("confirm_streak", 0) + 1
                cand_ev["lapse_count"] = 0
                cand_ev["last_receipts"] = receipts
            else:
                cand_ev["confirm_streak"] = 0   # reset — must be consecutive
                cand_ev["lapse_count"] = cand_ev.get("lapse_count", 0) + 1

            if cand_ev["confirm_streak"] >= confirm_days:
                # CONFIRMED tonight — promote from candidate to active, emit created
                # R-B2: this is the ONLY night created fires for this pair
                started = cand_ev["started"]
                active_out[pair_id] = {
                    "pair_id": pair_id,
                    "donor": donor_key,
                    "receiver": recv_key,
                    "tier": tier,
                    "started": started,
                    "lapse_count": 0,
                    "neg_run": neg_run_cur,
                    "confirm_streak": cand_ev["confirm_streak"],
                    "announced": True,
                    "last_receipts": cand_ev["last_receipts"],
                }
                created.append(pair_id)
                # Fall through to the emission block below (no continue here)
            elif cand_ev.get("lapse_count", 0) >= lapse_run:
                # Candidate lapsed without confirming — discard silently
                continue
            else:
                # Still pending confirmation
                candidates_out[pair_id] = cand_ev
                continue

        # ----------------------------------------------------------------
        # ACTIVE PHASE (already confirmed and announced)
        # ----------------------------------------------------------------
        if active_ev is not None:
            active_ev = dict(active_ev)
            fired = receipts is not None
            active_ev["lapse_count"] = 0 if fired else active_ev.get("lapse_count", 0) + 1
            if fired:
                active_ev["confirm_streak"] = active_ev.get("confirm_streak", 0) + 1
                active_ev["last_receipts"] = receipts
            else:
                active_ev["confirm_streak"] = 0
            # R-M1: persist live neg_run onto the event dict before _health
            active_ev["neg_run"] = neg_run_cur

            day_n = _sessions_between(dates, active_ev["started"], asof) + 1
            reason = None
            if neg_run_cur >= ratio_exit_run:
                reason = "ratio_slope_flipped"
            elif active_ev["lapse_count"] >= lapse_run:
                reason = "conditions_lapsed"
            elif day_n > ttl:
                reason = "ttl"
            if reason:
                closed_prev[pair_id] = asof
                closed.append({
                    "pair_id": pair_id, "donor": donor_key, "receiver": recv_key,
                    "tier": tier, "started": active_ev["started"],
                    "closed_asof": asof, "reason": reason, "day_n": day_n,
                })
                continue

            active_out[pair_id] = active_ev

            rc = receipts or active_ev.get("last_receipts")
            if rc is None:
                continue

            d_label = series_index.get(donor_key, {})
            r_label = series_index.get(recv_key, {})

            # severity: primary pairs get notable floor; secondary standard
            sev_lvl = 1 if tier == "primary" else 0
            sev = ("standard", "notable", "major")[sev_lvl]
            event_type = rc.get("event_type", "into_strength")

            ev_out = {
                "id": pair_id,
                "event_type": event_type,
                "from_sector": d_label.get("sector", donor_key),
                "to_sector": r_label.get("sector", recv_key),
                "donor": {"key": donor_key, "name_en": d_label.get("label_en", donor_key),
                          "name_zh": d_label.get("label_zh", donor_key), "tier": tier},
                "receiver": {"key": recv_key, "name_en": r_label.get("label_en", recv_key),
                             "name_zh": r_label.get("label_zh", recv_key)},
                "donor_signature": rc.get("donor_signature"),
                "started": active_ev["started"],
                "day_n": day_n,
                "asof": asof,
                "severity": sev,
                "severity_effective": sev,     # populated by _health + decay_severity
                "receipts": rc,
                "confirmed_tonight": receipts is not None,
                # carry neg_run for _health
                "lapse_count": active_ev["lapse_count"],
                "neg_run": neg_run_cur,
            }
            events_active.append(ev_out)
            continue

        # pair_id was just promoted from candidate → active this night
        # (active_ev was None above, active_out[pair_id] set during candidate promotion)
        if pair_id in active_out and pair_id not in active_prev:
            promoted = active_out[pair_id]
            day_n = _sessions_between(dates, promoted["started"], asof) + 1
            rc = receipts or promoted.get("last_receipts")
            if rc is None:
                continue
            d_label = series_index.get(donor_key, {})
            r_label = series_index.get(recv_key, {})
            sev_lvl = 1 if tier == "primary" else 0
            sev = ("standard", "notable", "major")[sev_lvl]
            event_type = rc.get("event_type", "into_strength")
            events_active.append({
                "id": pair_id,
                "event_type": event_type,
                "from_sector": d_label.get("sector", donor_key),
                "to_sector": r_label.get("sector", recv_key),
                "donor": {"key": donor_key, "name_en": d_label.get("label_en", donor_key),
                          "name_zh": d_label.get("label_zh", donor_key), "tier": tier},
                "receiver": {"key": recv_key, "name_en": r_label.get("label_en", recv_key),
                             "name_zh": r_label.get("label_zh", recv_key)},
                "donor_signature": rc.get("donor_signature"),
                "started": promoted["started"],
                "day_n": day_n,
                "asof": asof,
                "severity": sev,
                "severity_effective": sev,
                "receipts": rc,
                "confirmed_tonight": True,
                "lapse_count": 0,
                "neg_run": neg_run_cur,
            })

    new_state = {"active": active_out, "candidates": candidates_out, "closed": closed_prev}
    return new_state, events_active, created, closed


# ------------------------------------------------------------------ family E — health ----

def _health(ev: dict, p: dict | None = None) -> dict:
    """Compute the health sub-object for an active event.

    Inputs come from the event's lifecycle state (lapse_count, neg_run) and
    ev["day_n"] / ev["started"].

    STRICT weakening rule (FINDING 6):
      weakening = lapse_count >= lapse_warn  OR  neg_run >= neg_warn
                  OR  ratio_neg_run >= ratio_exit_run
    At lapse_count=1 the event stays "active" (verified on 07-17 ai_semis->mag7).
    closing_soon = sessions_to_close <= 2
    """
    from engine.rotation_universe import PARAMS_V2
    p = p or PARAMS_V2
    lapse_warn = p.get("lapse_warn", 2)
    neg_warn = p.get("neg_warn", 2)
    ratio_exit_run = p.get("ratio_exit_run", 3)
    ttl = p.get("ttl_sessions", 20)
    lapse_run = p.get("lapse_run", 5)

    lapse_count = int(ev.get("lapse_count", 0))
    neg_run = int(ev.get("neg_run", 0))
    day_n = int(ev.get("day_n", 1))
    sessions_since_confirm = int(ev.get("lapse_count", 0))  # same as lapse when no re-confirm
    sessions_since_confirm_val = lapse_count   # how long since last confirmed session

    sessions_to_close = min(
        ttl - day_n,
        lapse_run - lapse_count,
        ratio_exit_run - neg_run,
    )

    weakening = (lapse_count >= lapse_warn
                 or neg_run >= neg_warn
                 or neg_run >= ratio_exit_run)
    closing_soon = 0 < sessions_to_close <= 2

    if weakening:
        state = "weakening"
    elif closing_soon:
        state = "closing_soon"
    else:
        state = "active"

    return {
        "state": state,
        "lapse_count": lapse_count,
        "neg_run": neg_run,
        "sessions_since_confirm": sessions_since_confirm_val,
        "sessions_to_close": max(0, sessions_to_close),
    }


def decay_severity(sev: str, health: dict) -> str:
    """Effective severity after health-based decay.

    STRICT: demote once if weakening; standard if closing_soon.
    Base severity is preserved on the event as "severity"; this returns "severity_effective".
    """
    order = ["standard", "notable", "major"]
    idx = order.index(sev) if sev in order else 0
    state = health.get("state", "active")
    if state == "closing_soon":
        return "standard"
    if state == "weakening":
        return order[max(0, idx - 1)]
    return sev


# ------------------------------------------------------------------ closed_recent ----

def closed_recent(ledger_path, n_sessions: int = 5) -> list:
    """Rolling N-session closure log: read the tail of events.jsonl and return the
    most recent 'closed' rows. Used for the #rc-closures strip (dead-end #6).
    """
    import pathlib
    p = pathlib.Path(ledger_path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    # scan from the end, collect closed rows
    rows = []
    seen_dates: set = set()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if row.get("event") == "closed":
            d = (row.get("closed_asof") or row.get("asof") or "")[:10]
            rows.append(row)
            seen_dates.add(d)
            if len(seen_dates) >= n_sessions:
                break
    return list(reversed(rows))


# ------------------------------------------------------------------ emit_v2 ----

def emit_v2(
    base_payload: dict,
    cross_events: list,
    cross_created: list,
    contagion_rows: list | None = None,
    velocity_board_data: dict | None = None,
    closed_recent_rows: list | None = None,
    n_cross_pairs_scanned: int = 0,
) -> dict:
    """Assemble the v2 payload: additive over the v1 base_payload.

    All NEW fields: event_type, to_sector, from_sector, donor_signature,
    severity_effective, health, flow_receipts per event; top-level
    n_cross_pairs_scanned, contagion, velocity_board, closed_recent.

    v1 intra-sector events are back-filled with event_type="handoff",
    to_sector=sector, from_sector=sector so all events carry the new keys.

    SCHEMA stays "rotation_events.v1" (additive; no SCHEMA bump).
    """
    # back-fill v1 events with new keys (additive)
    active = base_payload.get("active", [])
    for ev in active:
        if "event_type" not in ev:
            ev["event_type"] = "handoff"
        if "to_sector" not in ev:
            ev["to_sector"] = ev.get("sector")
        if "from_sector" not in ev:
            ev["from_sector"] = ev.get("sector")
        if "donor_signature" not in ev:
            ev["donor_signature"] = None
        if "severity_effective" not in ev:
            ev["severity_effective"] = ev.get("severity", "standard")
        if "health" not in ev:
            ev["health"] = {
                "state": "active", "lapse_count": ev.get("lapse_count", 0),
                "neg_run": 0, "sessions_since_confirm": 0, "sessions_to_close": 0,
            }
        if "flow_receipts" not in ev:
            ev["flow_receipts"] = None

    # enrich cross-pair events with health + effective severity
    for ev in cross_events:
        h = _health(ev)
        ev["health"] = h
        ev["severity_effective"] = decay_severity(ev.get("severity", "standard"), h)

    # merge all active events
    all_active = active + cross_events
    all_created = list(base_payload.get("created_tonight", [])) + cross_created

    # sort severity-first
    order = {"major": 0, "notable": 1, "standard": 2}
    all_active.sort(key=lambda e: (
        order.get(e.get("severity", "standard"), 3), -int(e.get("day_n", 1))
    ))

    out = dict(base_payload)
    out["active"] = all_active
    out["created_tonight"] = list(dict.fromkeys(all_created))
    out["n_cross_pairs_scanned"] = n_cross_pairs_scanned
    out["contagion"] = contagion_rows or []
    out["velocity_board"] = velocity_board_data
    out["closed_recent"] = closed_recent_rows or []
    return out


# ------------------------------------------------------------------ extended run_nightly ----

def run_nightly(sectors: dict, data_dir, p: dict = PARAMS,
                generated_utc: str | None = None,
                data_subdir: str = "rotation_events",
                universe: dict | None = None,
                breadth_by_sector: dict | None = None,
                breadth_series_by_sector: dict | None = None,
                closes: dict | None = None) -> dict:
    """Load state → step every pair → persist state + lane-gated ledger → return payload.

    V1 path (universe=None): identical to the original; China/HK callers are completely
    unaffected. Cross-universe machinery only activates when universe is passed.

    V2 path (universe dict provided): additionally runs step_cross_pairs, corr_break
    detection, velocity_board assembly, and emits the v2 payload (additive over v1).

    Lane-gate: events.jsonl append only when _ledger_lane_armed() (COLLECT_LANE==nightly).
    Coldstart replay rows → coldstart_seed.jsonl (never events.jsonl), with fingerprint
    dedup so a second cold run produces identical line counts.

    ``data_subdir`` controls the directory under ``data_dir`` (default "rotation_events").
    """
    d = data_dir / data_subdir
    d.mkdir(parents=True, exist_ok=True)
    state_p, ledger_p = d / "state.json", d / "events.jsonl"
    seed_p = d / "coldstart_seed.jsonl"

    replay_created: list = []
    replay_closed: list = []
    if state_p.exists():
        try:
            state = json.loads(state_p.read_text())
        except Exception:  # noqa: BLE001
            log.warning("rotation_events: state.json unreadable — cold-starting")
            state, replay_created, replay_closed = coldstart_replay(sectors, p)
    else:
        state, replay_created, replay_closed = coldstart_replay(sectors, p)
    new_state, active, created, closed_list = step_pairs(sectors, state, p)

    now = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- lane-gated ledger append (v1 rows) ----
    armed = _ledger_lane_armed()
    if armed:
        with ledger_p.open("a") as fh:
            for row in replay_created:
                fh.write(json.dumps({"ts": now, "event": "created", **row},
                                    ensure_ascii=False) + "\n")
            for row in replay_closed:
                fh.write(json.dumps({"ts": now, "event": "closed", **row},
                                    ensure_ascii=False) + "\n")
            for pid in created:
                ev = next(e for e in active if e["id"] == pid)
                fh.write(json.dumps({"ts": now, "event": "created", **ev},
                                    ensure_ascii=False) + "\n")
            for c in closed_list:
                fh.write(json.dumps({"ts": now, "event": "closed", **c},
                                    ensure_ascii=False) + "\n")
    else:
        # off-lane: coldstart replay rows go to coldstart_seed.jsonl with fingerprint dedup
        if replay_created or replay_closed:
            _append_coldstart_seed(seed_p, replay_created, replay_closed, now, p)

    state_p.write_text(json.dumps(new_state, ensure_ascii=False, indent=1))

    as_of = max((e["asof"] for e in active), default=None)
    if as_of is None:
        as_of = max((s["etf_close"].index[-1].date().isoformat()
                     for s in sectors.values()), default=None)
    order = {"major": 0, "notable": 1, "standard": 2}
    active.sort(key=lambda e: (order.get(e["severity"], 3), -e["day_n"]))

    base = {
        "schema": SCHEMA, "ok": True, "as_of": as_of, "generated_utc": now,
        "authority": {"tier": "display", "may_rank": False, "may_gate": False,
                      "may_size": False, "may_escalate": False},
        "params": p,
        "n_pairs_scanned": sum(max(0, len(s["legs"]) * (len(s["legs"]) - 1))
                               for s in sectors.values()),
        "active": active,
        "created_tonight": list(dict.fromkeys(
            created + [r["id"] for r in replay_created
                       if r["id"] in new_state["active"]])),
        "closed_tonight": closed_list,
        "coldstart": bool(replay_created or replay_closed),
    }

    # ---- v2 cross-universe path ----
    if universe is None:
        return base

    # need closes dict for the cross-pair step
    if closes is None:
        log.warning("rotation_events.run_nightly: universe passed but no closes dict — "
                    "skipping cross-pair step")
        return base

    from engine.rotation_universe import PARAMS_V2
    # load bench close
    bench_key = universe.get("bench", {}).get("key", "spy")
    bench_close = closes.get(bench_key)
    if bench_close is None:
        log.warning("rotation_events.run_nightly: bench series %s not in closes — "
                    "skipping cross-pair step", bench_key)
        return base

    # cross-pair state
    cross_state_p = d / "cross_state.json"
    cross_state: dict = {}
    if cross_state_p.exists():
        try:
            cross_state = json.loads(cross_state_p.read_text())
        except Exception:  # noqa: BLE001
            cross_state = {}

    new_cross_state, cross_events, cross_created, cross_closed = step_cross_pairs(
        universe, closes, bench_close, cross_state,
        breadth_by_sector=breadth_by_sector,
        breadth_series_by_sector=breadth_series_by_sector,
        p2=PARAMS_V2,
    )

    if armed:
        with ledger_p.open("a") as fh:
            for pid in cross_created:
                ev = next((e for e in cross_events if e["id"] == pid), None)
                if ev:
                    fh.write(json.dumps({"ts": now, "event": "created", **ev},
                                        ensure_ascii=False) + "\n")
            for c in cross_closed:
                fh.write(json.dumps({"ts": now, "event": "closed", **c},
                                    ensure_ascii=False) + "\n")

    cross_state_p.write_text(json.dumps(new_cross_state, ensure_ascii=False, indent=1))

    # contagion detection
    from engine.rotation_corr import corr_break, attribute_break
    contagion_rows: list = []
    for cp in universe.get("contagion_pairs", []):
        a_cl = closes.get(cp["a"])
        b_cl = closes.get(cp["b"])
        if a_cl is None or b_cl is None:
            continue
        cb = corr_break(a_cl, b_cl, bench_close, PARAMS_V2)
        if cb is not None:
            # attribution for the complex
            complex_key = cp.get("complex")
            attr = None
            if complex_key:
                cx_cfg = next((c for c in universe.get("complexes", [])
                               if c["key"] == complex_key), None)
                if cx_cfg:
                    attr = attribute_break(cx_cfg, closes, bench_close, PARAMS_V2)
            contagion_rows.append({
                "id": cp["id"],
                "a": cp["a"],
                "b": cp["b"],
                "complex": complex_key,
                "root_cause": attr,
                **cb,
            })

    # velocity board
    from engine.rotation_velocity import velocity_board as _vb
    from engine.rotation_flows import flow_receipt_for_series
    series_index = {s["key"]: s for s in universe.get("series", [])}
    flow_receipts = {}
    for key in universe.get("velocity_series", []):
        spec = series_index.get(key)
        if spec:
            flow_receipts[key] = flow_receipt_for_series(spec, data_dir)

    vboard = _vb(universe, closes, flow_receipts, bench_key)

    # closed_recent strip
    cr_rows = closed_recent(ledger_p, n_sessions=5) if ledger_p.exists() else []

    n_cross = len(universe.get("pairs", []))
    payload = emit_v2(base, cross_events, cross_created,
                      contagion_rows=contagion_rows,
                      velocity_board_data=vboard,
                      closed_recent_rows=cr_rows,
                      n_cross_pairs_scanned=n_cross)
    return payload


# ------------------------------------------------------------------ coldstart seed helpers ----

def _coldstart_fingerprint(sectors: dict, p: dict) -> str:
    """SHA1 fingerprint for coldstart dedup: based on the pair calendar tail
    + coldstart_backscan value. Identical inputs → identical fingerprint → skip replay."""
    backscan = p.get("coldstart_backscan", PARAMS["coldstart_backscan"])
    cal_tail = sorted({
        str(d.date()) if hasattr(d, "date") else str(d)
        for s in sectors.values()
        for d in s["etf_close"].dropna().index[-backscan:]
    })
    payload_str = json.dumps({"cal_tail": cal_tail, "backscan": backscan}, sort_keys=True)
    return hashlib.sha1(payload_str.encode()).hexdigest()


def _append_coldstart_seed(
    seed_path,
    replay_created: list,
    replay_closed: list,
    now: str,
    p: dict,
) -> None:
    """Append coldstart replay rows to coldstart_seed.jsonl (not events.jsonl).
    Skips if the fingerprint matches existing tail (idempotency — double-run safe).
    """
    import pathlib
    sp = pathlib.Path(seed_path)

    # read existing fingerprints from seed tail to check dedup
    existing_fps: set = set()
    if sp.exists():
        try:
            for line in sp.read_text(encoding="utf-8").strip().splitlines()[-200:]:
                try:
                    row = json.loads(line)
                    fp = row.get("_fingerprint")
                    if fp:
                        existing_fps.add(fp)
                except Exception:  # noqa: BLE001
                    pass
        except OSError:
            pass

    # we can't compute fingerprint without sectors here — use a hash of the rows themselves
    row_hash = hashlib.sha1(
        json.dumps([r.get("id") or r.get("pair_id") for r in replay_created + replay_closed],
                   sort_keys=True).encode()
    ).hexdigest()

    if row_hash in existing_fps:
        return   # already written — idempotent

    with sp.open("a") as fh:
        for row in replay_created:
            fh.write(json.dumps({"ts": now, "event": "created", "coldstart": True,
                                  "_fingerprint": row_hash, **row},
                                ensure_ascii=False) + "\n")
        for row in replay_closed:
            fh.write(json.dumps({"ts": now, "event": "closed", "coldstart": True,
                                  "_fingerprint": row_hash, **row},
                                ensure_ascii=False) + "\n")
