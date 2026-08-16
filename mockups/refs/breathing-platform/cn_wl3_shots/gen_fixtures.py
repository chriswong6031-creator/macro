#!/usr/bin/env python3
"""CN-W-L3 / CN-PR-3 — synthetic `cn_prophet_live.states/v1` payloads for the browser proof.

    python3 mockups/refs/breathing-platform/cn_wl3_shots/gen_fixtures.py

Writes five fixtures into ``fixtures/`` beside this file. They are NEVER written into
``site/live/`` — the shipped site tree must stay exactly what the last asia bake produced,
because that frozen N−1 board is half of what the proof is proving.

The tickers are the FIRST TEN CARDS of the real rendered ``site/china_stocks.html`` entry
grid, in DOM order, so one screenshot carries the whole chip vocabulary at once — including
the two states (``dormant``/``unknown``) that deliberately paint NOTHING. A chip is news,
not a status light; a board where 90 of 107 cards wear a pill has taught the reader to stop
seeing pills, so the proof has to show the silence as well as the chips.

Schema: research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md §6.
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "fixtures"

#: The rendered board's own session — the client's feed floor reads this off the page.
PAGE_SESSION = "2026-08-14"
#: The synthetic runtime session: N, one ahead of the frozen render. The upgrade path.
SESSION_N = "2026-08-15"
#: N−2. Every gate passes for it when the clock is set to that day EXCEPT the feed floor,
#: which is what makes the refusal crop a proof of the floor and not of the calendar.
SESSION_N2 = "2026-08-13"

UNIVERSE_N, ARMED_N, OBSERVABLE_N = 1450, 141, 128


def _utc(session: str, cst_hhmm: str) -> str:
    """An Asia/Shanghai wall time as the UTC stamp the producer would write (CST = UTC+8,
    no DST ever, which is why this is arithmetic and not a timezone database lookup)."""
    h, m = (int(x) for x in cst_hhmm.split(":"))
    y, mo, d = (int(x) for x in session.split("-"))
    h -= 8
    if h < 0:
        h += 24
        d -= 1
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{m:02d}:00Z"


def _name(state, status="trading", since=None, session=SESSION_N, px=12.34, prev=12.10):
    """One `names[ticker]` entry. Only the fields this client actually reads are varied;
    the rest are present so the fixture is a real §6 payload and not a client-shaped stub."""
    return {
        "state": state,
        "since_ts": _utc(session, since) if since else None,
        "market_status": status,
        "price": None if status in ("unavailable", "suspended_suspected") else px,
        "quote_ts": None if status in ("unavailable", "suspended_suspected") else _utc(session, "14:12"),
        "quote_age_sec": None if status in ("unavailable", "suspended_suspected") else 902,
        "price_basis": None if status in ("unavailable", "suspended_suspected") else "minute",
        "prev_close_feed": prev,
        "as_of_close_pack": PAGE_SESSION,
        "trigger_px": round(prev * 1.02, 2),
        "fade_px": round(prev * 0.97, 2),
        "band_lo_px": round(prev * 0.99, 2),
        "band_hi_px": round(prev * 1.06, 2),
        "frozen": {"score": 78.4, "rank": 3, "lane": "featured"},
        "dark_reason": None,
    }


#: First ten cards of the real entry grid, in DOM order, each given a different kind so a
#: single crop is a full specimen sheet of the chip vocabulary. (ticker, state, status,
#: since) — the last two rows paint NOTHING, and their presence in the payload is the
#: point: the client is handed a state for them and still leaves the card exactly as the
#: nightly built it.
CARD_SPEC = [
    ("600879.SS", "forming", "trading",             "13:42"),
    ("002466.SZ", "near",    "trading",             "14:05"),
    ("002709.SZ", "at_risk", "trading",             "13:11"),
    ("002460.SZ", "forming", "limit_up_locked",     "10:31"),
    ("002050.SZ", "faded",   "trading",             "10:58"),
    ("600118.SS", "at_risk", "limit_down_locked",   "09:41"),
    ("001301.SZ", "near",    "suspended_suspected", "09:30"),
    ("002048.SZ", "forming", "unavailable",         "11:02"),
    ("603920.SS", "dormant", "trading",             None),
    ("002756.SZ", "unknown", "trading",             None),
]


def _names(session: str) -> dict:
    """The per-name block, stamped in the session it belongs to. `since_ts` must carry the
    payload's OWN session date: the client shows the clock time only when `since` falls on
    that session, so a prior-session carry-over can never print a wrong-day time."""
    return {tk: _name(state, status=status, since=since, session=session)
            for tk, state, status, since in CARD_SPEC}


def _base(session: str, phase: str, built_cst: str, revision: str) -> dict:
    return {
        "schema": "cn_prophet_live.states/v1",
        "session": session,
        "built_at": _utc(session, built_cst),
        "market_phase": phase,
        "pack_as_of": PAGE_SESSION,
        "revision": revision,
        "close_pending": False,
        "quote_source": "yahoo_spark",
        "delay_floor_min": 15,
        "coverage": {
            "universe_n": UNIVERSE_N, "armed_n": ARMED_N,
            "observable_n": OBSERVABLE_N,
            "coverage_pct": round(OBSERVABLE_N / ARMED_N * 100, 1),
        },
        "repaint_disclosure": {"t2_repaint_pct": 15.1},
        "names": _names(session),
        "close_board": None,
        "liveness": {
            "expected_session": session,
            "market_phase": phase,
            "source": "yahoo_spark",
            "source_asof": _utc(session, built_cst),
            "quote_age_sec_p50": 902,
            "universe_n": UNIVERSE_N, "observable_n": OBSERVABLE_N,
            "candidate_n": ARMED_N, "coverage_pct": round(OBSERVABLE_N / ARMED_N * 100, 1),
            "evaluation_started_at": _utc(session, built_cst),
            "artifact_written_at": _utc(session, built_cst),
            "close_observed_at": None, "first_close_board_at": None,
            "provisional_revision": revision, "canonical_revision": None,
            "confirmation_status": None, "failure_stage": None, "failure_reason": None,
        },
        "prev_states": None,
        "dark": None,
    }


def build() -> dict[str, dict]:
    out: dict[str, dict] = {}

    # (a)(b)(e) intraday, mid-afternoon — the full chip vocabulary.
    out["intraday_afternoon"] = _base(SESSION_N, "afternoon", "14:12", "intraday_provisional")

    # (f) lunch. States FREEZE (§2): the same reads, stamped 11:32, and the strip — not 107
    # pills — is what says the market is shut. The ribbon's fill stops dead at the gap.
    brk = _base(SESSION_N, "session_break", "11:32", "intraday_provisional")
    for tk, st in brk["names"].items():
        if st["quote_ts"]:
            st["quote_ts"] = _utc(SESSION_N, "11:29")
    out["session_break"] = brk

    # (c)(d) the close board, complete.
    cl = _base(SESSION_N, "post_close", "15:06", "close_provisional")
    cl["close_board"] = {
        "close_n": ARMED_N, "observable_n": ARMED_N, "close_coverage_pct": 100.0,
        "first_close_board_at": _utc(SESSION_N, "15:04"),
        "close_observed_at": _utc(SESSION_N, "15:01"),
    }
    cl["liveness"]["first_close_board_at"] = _utc(SESSION_N, "15:04")
    cl["liveness"]["close_observed_at"] = _utc(SESSION_N, "15:01")
    out["close_board"] = cl

    # The honest pending case: past 15:05 CST with the close still arriving. §5 keeps
    # intraday semantics below the floor — a close is never manufactured.
    pd = _base(SESSION_N, "post_close", "15:07", "intraday_provisional")
    pd["close_pending"] = True
    pd["close_board"] = {"close_n": 62, "observable_n": 62, "close_coverage_pct": 44.0,
                         "first_close_board_at": None, "close_observed_at": None}
    out["close_pending"] = pd

    # (g) the refusal. Session N−2 against a page rendered at N−1.
    st = _base(SESSION_N2, "afternoon", "13:58", "intraday_provisional")
    out["stale_prior_session"] = st

    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in build().items():
        p = OUT / f"{name}.json"
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {p.relative_to(HERE.parents[3])}")
