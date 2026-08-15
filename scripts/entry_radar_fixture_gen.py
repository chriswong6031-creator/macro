#!/usr/bin/env python3
"""scripts/entry_radar_fixture_gen.py — generate the W3 (PR-3) challenger fixtures.

WHY A GENERATOR AND NOT A HAND-TYPED TAPE
------------------------------------------
The W3 PIT battery needs a minute tape whose *oscillator morphology* is exact: an
arm below 20, a trough that never prints zero, a failed micro-turn, a later C2a
cross that fires **above** 20, and a raw one-minute low materially below every
5-minute sampled point.  Hand-typing prices to hit those StochRSI levels is not
possible; this script INVERTS the indicator instead.  Canonical StochRSI %K is
monotone non-decreasing in the current close (the §7.1 threshold-inversion
property), so a bisection on price hits a target ``rawk`` exactly, and the whole
morphology is CONSTRUCTED rather than hoped for.

The generated fixture is committed.  This script exists as the provenance receipt
for it: what the numbers are, and how they came to be.  It is never run in CI and
nothing in the test suite imports it.

WHAT IS SYNTHETIC, AND WHY THAT IS LAWFUL
------------------------------------------
Every price here is synthetic and the manifest says so in machine-readable form.
Contract §5's replay law forbids EOD-faked intraday HISTORY used as evidence; it
does not forbid a constructed tape used to prove a boundary.  A synthetic tape is
in fact the only way to test the boundaries that matter — a real session rarely
contains a flash low three ATR below the sampled path on exactly the bar needed.
No claim about any real security is made or implied, and the ticker is a reserved
nonsense symbol.

USAGE
    python3 scripts/entry_radar_fixture_gen.py            # write the fixtures
    python3 scripts/entry_radar_fixture_gen.py --check    # regenerate + diff only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, and at position 0 on purpose.  `python scripts/<name>.py` puts
# scripts/ (not the repo root) first, so repo imports would otherwise resolve from
# whatever ambient sys.path entries the host carries — the defect
# tests/test_check_script_import_pinning.py exists to prevent.
sys.path.insert(0, str(ROOT))

from engine import canon  # noqa: E402
from engine import session_anchor  # noqa: E402
from engine.session_digest import is_early_close, session_window_et  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "entry_radar"
MAIN_FIXTURE = FIXTURE_DIR / "w3_c1c2_path.json"
EARLY_FIXTURE = FIXTURE_DIR / "w3_early_close_tape.json"
MANIFEST = FIXTURE_DIR / "w3_provenance.json"

SCHEMA = "radar.w3.fixture/v1"
TICKER = "ZZWO"
PRICE_BASIS = "adjusted"
INTERVAL_MINUTES = 5

#: Pre-tape warm-up: a wobbling uptrend.  The wobble is load-bearing — a monotone
#: series has zero down-moves, so Wilder RSI's denominator is zero and every
#: oscillator downstream is NaN.
WARMUP_BARS = 100
WARMUP_DRIFT = 0.0025
WARMUP_WOBBLE = (0.010, 2.3, 0.005, 6.1, 0.7)

#: rawk targets for the three confirmed sessions immediately before the tape.
#: These fix the two-bar rawk memory %D reads, which is what decides the C2a
#: threshold inside each tape session.
PRE_TAPE_RAWK = (90.0, 40.0, 10.0)

#: Per-session rawk waypoints, interpolated across the session's 5-minute grid.
#: Chosen so the resulting %K path is: 35 -> arm below 20 -> 5 -> failed
#: micro-turn -> 4 (never <= 2) -> recovery through 14 -> C2a cross above 20.
SESSION_RAWK_PLAN: dict[str, tuple[float, ...]] = {
    "A": (55.0, 46.0, 36.0, 27.0, 20.0, 14.0, 9.0, 6.0, 3.0, 1.0),
    "B": (25.0, 12.0, 5.0, 9.0, 12.0, 4.0, 2.0, 8.0, 25.0, 66.0),
    "C": (5.0, 18.0, 30.0, 45.0, 55.0, 62.0, 70.0, 76.0, 80.0, 84.0),
}

#: The flash low, in PRICE UNITS below the sampled path, planted on one minute of
#: session A.  PIT-6's whole point: a raw one-minute low that the 5-minute sampled
#: path never saw, on a session where the sampled path produces no c2f fire at all.
FLASH_LOW_SESSION = "A"
FLASH_LOW_INTERVAL = 58
FLASH_LOW_MINUTE = 2
FLASH_LOW_DROP = 3.0

#: Extended-hours prints attached to every tape session.  They exist so PIT-11 can
#: MUTATE them: a guard that filters a bar family the fixture never contains is a
#: guard nobody has tested.
PREMARKET_MINUTES = 20
POSTMARKET_MINUTES = 20

#: Daily OHLC synthesis for the pre-tape bars: a plausible range around the close.
#: Tape sessions get their real high/low FROM the minute tape instead.
DAILY_RANGE_PCT = 0.004


# ---------------------------------------------------------------------------
# indicator inversion
# ---------------------------------------------------------------------------

def _rawk_k_d(history: list[float], price: float) -> tuple[float, float, float]:
    series = pd.Series(history + [float(price)], dtype=float)
    rsi = canon.rsi(series, canon.RSI_LEN)
    low = rsi.rolling(canon.STOCH_LEN).min()
    high = rsi.rolling(canon.STOCH_LEN).max()
    rawk = (rsi - low) / (high - low).replace(0, np.nan) * 100
    k, d = canon.stoch_rsi_kd(series)
    return float(rawk.iloc[-1]), float(k.iloc[-1]), float(d.iloc[-1])


def solve_price_for_rawk(history: list[float], target: float, *,
                         iterations: int = 44) -> float:
    """Bisect today's close until ``rawk`` hits ``target``.

    Monotone by the §7.1 property (RSI rises with the live close; ``rawk``
    saturates rather than reversing), so bisection is exact up to the saturation
    plateaus — and a target inside the reachable band never lands on one.
    """
    low, high = min(history) * 0.05, max(history) * 20.0
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        if _rawk_k_d(history, mid)[0] < target:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def interpolate(waypoints: tuple[float, ...], n: int) -> list[float]:
    """Piecewise-linear expansion of the waypoints onto ``n`` observation slots."""
    xs = np.linspace(0.0, 1.0, len(waypoints))
    return list(np.interp(np.linspace(0.0, 1.0, n), xs, np.asarray(waypoints)))


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

def warmup_closes() -> list[float]:
    t = np.arange(WARMUP_BARS, dtype=float)
    a1, p1, a2, p2, phase = WARMUP_WOBBLE
    wobble = a1 * np.sin(t / p1) + a2 * np.sin(t / p2 + phase)
    return list(100.0 * np.exp(WARMUP_DRIFT * t) * (1.0 + wobble))


def sessions_for(count: int, *, end: str) -> list[date]:
    reference = session_anchor.reference_sessions("US")
    cut = reference[reference <= pd.Timestamp(end)]
    return [ts.date() for ts in cut[-count:]]


def interval_ends(session: date) -> list[datetime]:
    open_dt, close_dt = session_window_et(session)
    out: list[datetime] = []
    cursor = open_dt
    while cursor < close_dt:
        out.append(min(cursor + timedelta(minutes=INTERVAL_MINUTES), close_dt))
        cursor = out[-1]
    return out


def minute_rows(session: date, sampled: list[float], previous_close: float, *,
                flash: tuple[int, int, float] | None) -> list[list]:
    """Expand the sampled path into a full minute tape.

    Every interval's LAST minute closes exactly on the sampled value — that is
    what makes the fixture's sampled path a fact rather than an approximation —
    and the intervening minutes interpolate from the previous sampled value.
    """
    open_dt, close_dt = session_window_et(session)
    rows: list[list] = []
    prior = float(previous_close)
    cursor = open_dt
    for index, target in enumerate(sampled):
        end = min(cursor + timedelta(minutes=INTERVAL_MINUTES), close_dt)
        span = int((end - cursor).total_seconds() // 60)
        for step in range(span):
            frac = (step + 1) / span
            close = prior + (target - prior) * frac
            open_px = prior if step == 0 else rows[-1][4]
            high = max(open_px, close) * (1.0 + 0.0006)
            low = min(open_px, close) * (1.0 - 0.0006)
            if flash is not None and index == flash[0] and step == flash[1]:
                low = min(low, close - flash[2])
            rows.append([(cursor + timedelta(minutes=step)).isoformat(),
                         round(open_px, 4), round(high, 4), round(low, 4),
                         round(close, 4), 1000.0 + 10 * step])
        prior = target
        cursor = end
    return rows


def extended_hours_rows(session: date, first_close: float,
                        last_close: float) -> list[list]:
    """Premarket and postmarket prints — deliberately far from the RTH path.

    Far on purpose: a session filter that silently admitted them would move every
    downstream value by a visible amount, so PIT-11 fails loudly rather than by a
    rounding digit.
    """
    open_dt, close_dt = session_window_et(session)
    rows: list[list] = []
    for i in range(PREMARKET_MINUTES, 0, -1):
        px = round(first_close * 1.08, 4)
        start = open_dt - timedelta(minutes=i)
        rows.append([start.isoformat(), px, round(px * 1.001, 4),
                     round(px * 0.999, 4), px, 500.0])
    for i in range(POSTMARKET_MINUTES):
        px = round(last_close * 0.90, 4)
        start = close_dt + timedelta(minutes=i)
        rows.append([start.isoformat(), px, round(px * 1.001, 4),
                     round(px * 0.999, 4), px, 500.0])
    return rows


def build() -> tuple[dict, dict]:
    history = warmup_closes()
    for target in PRE_TAPE_RAWK:
        history.append(solve_price_for_rawk(history, target))

    tape_sessions = sessions_for(len(SESSION_RAWK_PLAN) + 1, end="2026-06-26")
    pre_session = tape_sessions[0]
    tape_sessions = tape_sessions[1:]
    daily_sessions = sessions_for(len(history) + len(SESSION_RAWK_PLAN),
                                  end=tape_sessions[-1].isoformat())

    tapes: list[dict] = []
    measured: dict[str, list[dict]] = {}
    for name, session in zip(SESSION_RAWK_PLAN, tape_sessions):
        slots = len(interval_ends(session))
        plan = interpolate(SESSION_RAWK_PLAN[name], slots)
        sampled: list[float] = []
        readings: list[dict] = []
        for target in plan:
            price = round(solve_price_for_rawk(history, target), 4)
            rawk, k, d = _rawk_k_d(history, price)
            sampled.append(price)
            readings.append({"rawk": round(rawk, 3), "k": round(k, 4),
                             "d": round(d, 4), "close": price})
        flash = ((FLASH_LOW_INTERVAL, FLASH_LOW_MINUTE, FLASH_LOW_DROP)
                 if name == FLASH_LOW_SESSION else None)
        rows = minute_rows(session, sampled, history[-1], flash=flash)
        rows += extended_hours_rows(session, sampled[0], sampled[-1])
        rows.sort(key=lambda r: r[0])
        tapes.append({"label": name, "session": session.isoformat(),
                      "price_basis": PRICE_BASIS,
                      "columns": ["start", "open", "high", "low", "close", "volume"],
                      "rows": rows})
        measured[name] = readings
        history.append(sampled[-1])

    daily_rows: list[list] = []
    tape_by_session = {t["session"]: t for t in tapes}
    for session, close in zip(daily_sessions, history):
        key = session.isoformat()
        tape = tape_by_session.get(key)
        if tape is not None:
            rth = [r for r in tape["rows"]
                   if session_window_et(session)[0]
                   <= datetime.fromisoformat(r[0])
                   < session_window_et(session)[1]]
            open_px = rth[0][1]
            high = max(r[2] for r in rth)
            low = min(r[3] for r in rth)
        else:
            open_px = round(close * (1.0 - DAILY_RANGE_PCT / 2), 4)
            high = round(close * (1.0 + DAILY_RANGE_PCT), 4)
            low = round(close * (1.0 - DAILY_RANGE_PCT), 4)
        daily_rows.append([key, round(open_px, 4), round(high, 4), round(low, 4),
                           round(close, 4)])

    fixture = {
        "schema": SCHEMA,
        "ticker": TICKER,
        "price_basis": PRICE_BASIS,
        "interval_minutes": INTERVAL_MINUTES,
        "pre_tape_session": pre_session.isoformat(),
        "tape_sessions": [t["session"] for t in tapes],
        "daily": {"columns": ["session", "open", "high", "low", "close"],
                  "rows": daily_rows},
        "tapes": tapes,
        "measured": {name: rows for name, rows in measured.items()},
        "flash_low": {"session": tape_by_session[tapes[0]["session"]]["session"]
                      if FLASH_LOW_SESSION == "A" else None,
                      "interval": FLASH_LOW_INTERVAL, "minute": FLASH_LOW_MINUTE,
                      "drop": FLASH_LOW_DROP},
    }

    early_session = next(d for d in reversed(sessions_for(400, end="2026-06-26"))
                         if is_early_close(d))
    early_open, early_close_dt = session_window_et(early_session)
    slots = len(interval_ends(early_session))
    base = float(daily_rows[-1][4])
    ramp = [round(base * (1.0 + 0.0004 * i), 4) for i in range(slots)]
    early = {
        "schema": SCHEMA,
        "ticker": TICKER,
        "price_basis": PRICE_BASIS,
        "session": early_session.isoformat(),
        "session_open_et": early_open.isoformat(),
        "session_close_et": early_close_dt.isoformat(),
        "columns": ["start", "open", "high", "low", "close", "volume"],
        "rows": minute_rows(early_session, ramp, base, flash=None),
    }
    return fixture, early


def manifest(fixture: dict, early: dict) -> dict:
    return {
        "schema": "radar.w3.fixture_manifest/v1",
        "generated_by": "scripts/entry_radar_fixture_gen.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {
            MAIN_FIXTURE.name: {
                "kind": "synthetic",
                "source": ("constructed by bisecting canonical StochRSI rawk targets; "
                           "no market data of any kind was read"),
                "vintage": "n/a — no vendor input",
                "ticker": fixture["ticker"],
                "price_basis": fixture["price_basis"],
                "sessions": fixture["tape_sessions"],
                "daily_bars": len(fixture["daily"]["rows"]),
                "minute_rows": sum(len(t["rows"]) for t in fixture["tapes"]),
                "why_synthetic": ("the PIT battery needs an exact oscillator morphology "
                                  "(arm below 20, trough above 2, failed micro-turn, C2a "
                                  "cross above 20, a flash low the sampled path never "
                                  "saw); a real session supplies those only by accident"),
            },
            EARLY_FIXTURE.name: {
                "kind": "synthetic",
                "source": ("a monotone intraday ramp on a REAL NYSE early-close session "
                           "date, so the 13:00 clip is exercised against the real "
                           "calendar"),
                "vintage": "n/a — no vendor input",
                "session": early["session"],
                "minute_rows": len(early["rows"]),
            },
        },
        "calendar": "lib.nyse_calendar via engine.session_anchor / engine.session_digest",
        "regenerate": "python3 scripts/entry_radar_fixture_gen.py",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="regenerate and report a diff without writing")
    args = parser.parse_args()

    fixture, early = build()
    payloads = {MAIN_FIXTURE: fixture, EARLY_FIXTURE: early,
                MANIFEST: manifest(fixture, early)}
    changed = []
    for path, payload in payloads.items():
        text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        changed.append(path.name)
        if not args.check:
            path.write_text(text, encoding="utf-8")
    print(f"entry-radar W3 fixtures: {'changed' if changed else 'unchanged'} {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
