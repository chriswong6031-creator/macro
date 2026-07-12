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

import json
import logging
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
                  p: dict = PARAMS, phase_in: str | None = None) -> dict | None:
    """All three signatures at the last common bar, or None."""
    idx = close_out.dropna().index.intersection(close_in.dropna().index)
    if len(idx) == 0:
        return None
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
    """Trading sessions from a to b inclusive-of-b (0 if a==b), on the pair calendar."""
    try:
        return max(0, dates.index(b) - dates.index(a))
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
                receipts = evaluate_pair(close_out, close_in, p)
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


def run_nightly(sectors: dict, data_dir, p: dict = PARAMS,
                generated_utc: str | None = None) -> dict:
    """Load state (cold-start: replay the trailing window) → step every pair → persist
    state + append the ledger → return the display payload for
    site/marketdata/rotation_events.json."""
    d = data_dir / "rotation_events"
    d.mkdir(parents=True, exist_ok=True)
    state_p, ledger_p = d / "state.json", d / "events.jsonl"
    replay_created: list = []
    replay_closed: list = []
    if state_p.exists():
        try:
            state = json.loads(state_p.read_text())
        except Exception:  # noqa: BLE001 — unreadable → fresh (lockouts reset, disclosed)
            log.warning("rotation_events: state.json unreadable — cold-starting")
            state, replay_created, replay_closed = coldstart_replay(sectors, p)
    else:
        state, replay_created, replay_closed = coldstart_replay(sectors, p)
    new_state, active, created, closed = step_pairs(sectors, state, p)

    now = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
        for c in closed:
            fh.write(json.dumps({"ts": now, "event": "closed", **c},
                                ensure_ascii=False) + "\n")
    state_p.write_text(json.dumps(new_state, ensure_ascii=False, indent=1))

    as_of = max((e["asof"] for e in active), default=None)
    if as_of is None:
        as_of = max((s["etf_close"].index[-1].date().isoformat()
                     for s in sectors.values()), default=None)
    order = {"major": 0, "notable": 1, "standard": 2}
    active.sort(key=lambda e: (order.get(e["severity"], 3), -e["day_n"]))
    return {
        "schema": SCHEMA, "ok": True, "as_of": as_of, "generated_utc": now,
        "authority": {"tier": "display", "may_rank": False, "may_gate": False,
                      "may_size": False, "may_escalate": False},
        "params": p,
        "n_pairs_scanned": sum(max(0, len(s["legs"]) * (len(s["legs"]) - 1))
                               for s in sectors.values()),
        "active": active,
        "created_tonight": created,
        "closed_tonight": closed,
        "coldstart": bool(replay_created or replay_closed),
    }
