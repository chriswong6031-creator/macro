"""Live Entry Radar PR-4 (W4) — the bounded C3 minute reader.

WHAT THIS SUITE IS FOR
----------------------
``vendor_minutes`` is the ONLY place in ``engine/entry_radar/`` where a network
fetch is even expressible, and it sits directly upstream of a detector that mints
candidates.  Both facts make it dangerous in ways the math modules are not: a
reader that mis-computes a window turns one pass into a bulk crawl, a cache that
serves a partial session turns an incomplete 4H bar into a confirmed one, and a
"just this once" import into ``four_hour`` would put a socket behind CI.  The
properties below are those failure modes, each stated as something a machine can
refuse:

  C3R-1   one name, one session — the request path and params are EXACT, the
          tape carries that session's minutes and nothing else, and the symbol
          translation is the estate's dash → the vendor's dot
  C3R-2   ``assert_window`` REFUSES a window no episode could justify; a lawful
          one passes (the bulk-crawl bound is a bound, not a decoration)
  C3R-3   a COMPLETED session is fetched once and served from the state dir
          forever after — including its TIMEZONE, which is the half of a cache
          round-trip that fails silently
  C3R-4   PIT-W4-7: a bucket that has not ended is ``confirmed=False`` and a
          partial session is NEVER written to the cache
  C3R-5   PIT-W4-8: an early close clips the grid to the ACTUAL session, and a
          normal session's clipping is the 390-minute RTH day's own shape
  C3R-6   BOTH CLOCKS on a C3 event: the signal is knowable at its BUCKET
          BOUNDARY, the pass happened whenever the lane looked, and the two are
          not the same instant
  C3R-7   no W3 math module imports this one — the network stays outside the
          engine, asserted at AST level so an aliased or function-local import
          cannot slip past
  C3R-8   importing this module opens no client: the vendor stack is resolved
          LAZILY inside ``default_transport``
  C3R-9   pacing happens on EVERY call — empties and exceptions included —
          because the vendor counts requests, not successes

WHY EACH GUARD CARRIES A MUTATION CONTROL.  A test that only restates today's
behaviour proves the code does what it does.  So C3R-2 also proves a lawful
window is accepted, C3R-4 also proves the same buckets come back CONFIRMED under
the replay contract (``now=None``) — which is what makes the ``confirmed`` flag,
rather than a coincidence of the fixture, the thing doing the refusing — C3R-5
states the normal-session shape explicitly instead of asserting a bare "not
clipped", C3R-7 plants each import shape it claims to catch, and C3R-8 asserts
the lazy import IS there rather than merely that a network module is absent.

THE TRANSPORT IS ALWAYS INJECTED.  Every reader in this file is handed a callable
over deterministic synthetic rows; nothing here opens a socket, reads ``data/``
or touches ``site/``.  The minute generator is a fixed sawtooth (no randomness),
which is enough to make 4H buckets that differ from each other — the only
property the grid tests need — and enough, over a warm-up window, to produce a
real histogram turn for C3R-6.
"""
from __future__ import annotations

import ast
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh
from engine.entry_radar import live_eval as le
from engine.entry_radar import live_ledger as ll
from engine.entry_radar import vendor_minutes as vm
from engine.session_digest import is_early_close, session_window_et
from tests.test_entry_radar_w4_pack import (
    AS_OF,
    NEXT_SESSION,
    build,
    frame_from_closes,
)

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / "engine" / "entry_radar"

#: The W3 math modules.  Named explicitly rather than globbed so the guard below
#: cannot go vacuous by matching nothing.
W3_MATH_MODULES = ("challengers.py", "four_hour.py", "indicator_core.py",
                   "readings.py", "detectors.py")

#: Module paths that would put a socket behind ``import vendor_minutes``.
NETWORK_ROOTS = ("requests", "httpx", "urllib", "urllib3", "socket", "boto3",
                 "aiohttp", "http")

#: A real US early close (half day, 13:00 ET).  VERIFIED against the calendar
#: helper in the test rather than trusted from a comment.
EARLY_CLOSE = date(2026, 11, 27)


# ---------------------------------------------------------------------------
# synthetic minute rows + a recording transport
# ---------------------------------------------------------------------------

def rows_for(session: date, base: float = 90.0) -> list[dict]:
    """One session of 5-minute vendor aggregate rows, deterministically.

    A sawtooth rather than a flat line: buckets that all carry the same close
    make a 4H series with no variation, and a grid test that passes on a
    constant series would pass on a broken one too.
    """
    open_dt, close_dt = session_window_et(session)
    out: list[dict] = []
    cursor, i = open_dt, 0
    while cursor < close_dt:
        price = base * (1.0 + 0.004 * ((i % 23) - 11))
        out.append({"t": cursor.timestamp() * 1000.0, "o": price, "h": price * 1.001,
                    "l": price * 0.999, "c": price, "v": 100.0})
        cursor += timedelta(minutes=5)
        i += 1
    return out


class Recorder:
    """A transport that records every (path, params) it was asked for."""

    def __init__(self, rows=rows_for) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._rows = rows

    @property
    def paths(self) -> list[str]:
        return [path for path, _params in self.calls]

    def __call__(self, path: str, params) -> list[dict]:
        self.calls.append((path, dict(params)))
        return self._rows(date.fromisoformat(path.split("/")[-2]))


def reader_for(recorder: Recorder, state_dir: Path | None = None) -> vm.VendorMinuteReader:
    return vm.VendorMinuteReader(transport=recorder, state_dir=state_dir,
                                 sleep_seconds=0.0)


def cache_body(state_dir: Path, ticker: str) -> dict:
    path = state_dir / "c3_buckets" / f"{ticker.upper()}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# C3R-1 — one name, one session, an exact request
# ---------------------------------------------------------------------------

def test_C3R1_the_reader_returns_one_sessions_tape_on_the_adjusted_basis(tmp_path):
    """The ``IntradayReader`` contract: one call, one session, one basis.

    ``adjusted`` is load-bearing rather than cosmetic — the pack substrate is an
    ADJUSTED daily frame, and a raw intraday tape beside it is the spliced basis
    W3-1 refuses before the engine is ever reached.
    """
    recorder = Recorder()
    tape = reader_for(recorder, tmp_path)("WASH", NEXT_SESSION)
    assert isinstance(tape, ch.SessionTape)
    assert tape.price_basis == ch.BASIS_ADJUSTED
    assert tape.session == NEXT_SESSION
    assert {bar.start.date() for bar in tape.minutes} == {NEXT_SESSION}


def test_C3R1_the_request_path_and_params_are_exact(tmp_path):
    """Re-typed from the vendor contract, not read back off the module.

    Two independent copies is the point: a drift in either one reds this test,
    which an ``assert AGGS_PARAMS == AGGS_PARAMS`` cannot.
    """
    recorder = Recorder()
    reader_for(recorder, tmp_path)("WASH", NEXT_SESSION)
    assert len(recorder.calls) == 1
    path, params = recorder.calls[0]
    assert path == (f"/v2/aggs/ticker/WASH/range/1/minute/"
                    f"{NEXT_SESSION.isoformat()}/{NEXT_SESSION.isoformat()}")
    assert params == {"adjusted": "true", "sort": "asc", "limit": 50000}


def test_C3R1_the_symbol_translation_is_the_estates_dash_to_the_vendors_dot():
    assert vm.polygon_symbol("BRK-B") == "BRK.B"
    assert vm.polygon_symbol("WASH") == "WASH"


def test_C3R1_the_request_carries_the_TRANSLATED_symbol(tmp_path):
    """CONTROL for the line above: the translation is actually applied."""
    recorder = Recorder()
    reader_for(recorder, tmp_path)("BRK-B", NEXT_SESSION)
    assert "/ticker/BRK.B/" in recorder.paths[0]


def test_C3R1_an_empty_vendor_response_is_an_EMPTY_TAPE_not_a_raise(tmp_path):
    """Halted, unlisted and no-print names all produce the same honest answer.

    An empty tape yields buckets with ``close=None``, which ``run_c3`` discloses
    as ``confirmed_empty`` — a stated gap rather than a fabricated bar.
    """
    reader = vm.VendorMinuteReader(transport=lambda path, params: [],
                                   state_dir=tmp_path, sleep_seconds=0.0)
    tape = reader("GHOST", NEXT_SESSION)
    assert tape.minutes == ()
    assert reader.empty == 1
    assert reader.errors == 0


def test_C3R1_the_warmup_window_covers_the_INDICATORS_own_warm_up(tmp_path):
    """``C3_WARMUP_SESSIONS`` is derived, and this is where it is pinned.

    ``live_eval`` names this file as the mechanical pin so the indicator cannot
    outgrow the constant silently.  The bar count is MEASURED via
    ``first_lawful_turn_index`` rather than asserted from a comment: an RTH day
    yields two buckets, so the window must be at least half the first lawful
    turn index, and the shipped value must keep margin over that.
    """
    from lib.nyse_calendar import session_n_back, sessions_between

    recorder = Recorder()
    reader = reader_for(recorder, tmp_path)
    start = session_n_back(NEXT_SESSION, le.C3_WARMUP_SESSIONS)
    confirmed: list[fh.FourHourBucket] = []
    for day in sessions_between(start, NEXT_SESSION):
        confirmed.extend(b for b in reader.buckets("WARM", day)
                         if b.confirmed and b.close is not None)
    index = fh.first_lawful_turn_index(fh.confirmed_four_hour_series(confirmed))
    assert index is not None, "the warm-up window never reaches an evaluable turn"
    assert le.C3_WARMUP_SESSIONS * 2 > index, (
        f"the 4H turn is first evaluable at bucket {index}; "
        f"{le.C3_WARMUP_SESSIONS} sessions buy only {le.C3_WARMUP_SESSIONS * 2}")


# ---------------------------------------------------------------------------
# C3R-2 — the bulk-crawl refusal
# ---------------------------------------------------------------------------

def test_C3R2_a_window_no_episode_could_justify_is_REFUSED(tmp_path):
    """A window bug must be an exception, never a year of minutes per name."""
    reader = reader_for(Recorder(), tmp_path)
    with pytest.raises(vm.VendorMinutesError, match="episode-windowed"):
        reader.assert_window(date(2024, 1, 2), NEXT_SESSION)


def test_C3R2_CONTROL_a_lawful_episode_window_is_accepted(tmp_path):
    """The bound is a bound, not a blanket refusal.

    A window the size of the C3 warm-up — the one the evaluator actually asks
    for every pass — must pass, or the guard would dark C3 entirely.
    """
    from lib.nyse_calendar import session_n_back, sessions_between

    reader = reader_for(Recorder(), tmp_path)
    start = session_n_back(NEXT_SESSION, le.C3_WARMUP_SESSIONS)
    span = len(sessions_between(start, NEXT_SESSION))
    assert span <= vm.MAX_WINDOW_SESSIONS, span
    reader.assert_window(start, NEXT_SESSION)  # must not raise


def test_C3R2_the_refusal_boundary_sits_where_the_constant_says(tmp_path):
    """CONTROL on the bound itself: a reader with a tighter bound refuses more.

    Injecting the limit proves the comparison reads ``max_window_sessions``
    rather than a hard-coded figure that happens to agree with it today.
    """
    tight = vm.VendorMinuteReader(transport=Recorder(), state_dir=tmp_path,
                                  sleep_seconds=0.0, max_window_sessions=3)
    tight.assert_window(NEXT_SESSION, NEXT_SESSION)
    with pytest.raises(vm.VendorMinutesError):
        tight.assert_window(date(2026, 8, 3), NEXT_SESSION)


# ---------------------------------------------------------------------------
# C3R-3 — the completed-session cache, INCLUDING its timezone
# ---------------------------------------------------------------------------

def test_C3R3_a_completed_session_is_fetched_once_and_cached_on_disk(tmp_path):
    recorder = Recorder()
    reader = reader_for(recorder, tmp_path)
    buckets = reader.buckets("WASH", AS_OF)
    assert buckets and all(b.confirmed for b in buckets)
    assert len(recorder.calls) == 1
    body = cache_body(tmp_path, "WASH")
    assert body.get("schema") == "entry_radar.c3_buckets/v1"
    assert AS_OF.isoformat() in (body.get("sessions") or {})


def test_C3R3_a_SECOND_reader_over_the_same_state_dir_makes_no_request(tmp_path):
    """The cache is on DISK, not in an instance.  A fresh pass must inherit it."""
    recorder = Recorder()
    fresh = reader_for(recorder, tmp_path).buckets("WASH", AS_OF)
    calls_after_warm = len(recorder.calls)

    second = reader_for(recorder, tmp_path)
    cached = second.buckets("WASH", AS_OF)
    assert len(recorder.calls) == calls_after_warm, "the cache was not consulted"
    assert second.cache_hits == 1
    assert second.fetched_n == 0
    assert list(cached) == list(fresh)


def test_C3R3_the_cached_buckets_round_trip_ELEMENT_WISE_including_tzinfo(tmp_path):
    """The half of a cache round-trip that fails silently.

    ``FourHourBucket.to_dict`` serialises through ``utc_iso``, so a naive
    round-trip hands back UTC-aware datetimes while the fresh path carries the
    EASTERN ones ``session_window_et`` produced.  Same instants, so ``==`` on the
    datetimes is TRUE and the defect is invisible to an equality assert — but
    ``confirmed_four_hour_series`` builds a ``pd.DatetimeIndex`` over them and
    refuses a list of mixed offsets outright.  So the tzinfo is asserted
    explicitly, field by field, rather than left to dataclass equality.
    """
    recorder = Recorder()
    fresh = reader_for(recorder, tmp_path).buckets("WASH", AS_OF)
    cached = reader_for(recorder, tmp_path).buckets("WASH", AS_OF)
    assert len(fresh) == len(cached) >= 2
    for before, after in zip(fresh, cached):
        assert before == after
        assert before.start.tzinfo == after.start.tzinfo
        assert before.effective_end.tzinfo == after.effective_end.tzinfo
        assert before.effective_end.utcoffset() == after.effective_end.utcoffset()
        assert before.effective_minutes == after.effective_minutes
        assert before.clipped == after.clipped
        assert before.confirmed is after.confirmed


def test_C3R3_a_pass_mixing_one_CACHED_session_with_FRESH_ones_completes(tmp_path):
    """The integration half of the tz property, end to end through ``run_pass``.

    The unit assert above pins the shape; this one pins the CONSEQUENCE.  A
    mixed-offset bucket list only ever occurs for names whose episode window
    straddles the cache, so the defect would surface as an exception on some
    names on some passes — the worst possible shape for a bug, and precisely the
    shape a unit test alone can be talked past.
    """
    pack = late_wash_pack()
    recorder = Recorder()
    warm = reader_for(recorder, tmp_path)
    warm.buckets("LATEWASH", AS_OF)                    # exactly ONE session cached
    assert AS_OF.isoformat() in (cache_body(tmp_path, "LATEWASH").get("sessions") or {})

    reader = reader_for(recorder, tmp_path)
    result = run_live_pass(pack, tmp_path, reader=reader)   # must not raise
    assert result.health["inputs"]["c3_reader"]["cache_hits"] >= 1
    assert result.health["inputs"]["c3_reader"]["errors"] == 0
    assert result.names[0].lanes.get("c3"), "C3 produced no readings at all"


# ---------------------------------------------------------------------------
# C3R-4 — PIT-W4-7: an incomplete bucket is refused, and never cached
# ---------------------------------------------------------------------------

def test_C3R4_a_bucket_that_has_not_ended_is_not_confirmed(tmp_path):
    """Mid-session, both of the day's buckets are still running."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)
    buckets = reader_for(Recorder(), tmp_path).buckets("WASH", NEXT_SESSION, now=now)
    assert buckets, "the fixture produced no buckets at all"
    assert [b.confirmed for b in buckets] == [False] * len(buckets)
    assert all(b.effective_end > now for b in buckets)


def test_C3R4_a_partial_session_is_NEVER_written_to_the_cache(tmp_path):
    """A cached partial session would serve the very read PIT-W4-7 forbids."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)
    reader_for(Recorder(), tmp_path).buckets("WASH", NEXT_SESSION, now=now)
    sessions = (cache_body(tmp_path, "WASH").get("sessions") or {})
    assert NEXT_SESSION.isoformat() not in sessions, sessions


def test_C3R4_MUTATION_CONTROL_the_same_buckets_come_back_CONFIRMED_on_replay(tmp_path):
    """``now=None`` is the replay contract — the session is fully elapsed.

    This is what makes the test above load-bearing.  Without it "not confirmed"
    could be an artefact of a fixture that produced no minutes; with it, the
    SAME buckets over the SAME rows flip to confirmed purely because the
    observation instant moved, which proves the ``confirmed`` flag is the thing
    doing the refusing.
    """
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)
    recorder = Recorder()
    reader = reader_for(recorder, tmp_path)
    live = reader.buckets("WASH", NEXT_SESSION, now=now)
    replay = reader.buckets("WASH", NEXT_SESSION, now=None)

    assert [b.confirmed for b in replay] == [True] * len(replay)
    assert len(replay) == len(live)
    for running, elapsed in zip(live, replay):
        assert running.start == elapsed.start
        assert running.effective_end == elapsed.effective_end
        assert running.close == elapsed.close
        assert running.confirmed is False and elapsed.confirmed is True


# ---------------------------------------------------------------------------
# C3R-5 — PIT-W4-8: the grid clips to the ACTUAL session
# ---------------------------------------------------------------------------

def test_C3R5_the_early_close_date_really_is_an_early_close():
    """Verified against the calendar helper, never trusted from a comment."""
    assert is_early_close(EARLY_CLOSE) is True
    open_dt, close_dt = session_window_et(EARLY_CLOSE)
    assert close_dt.hour == 13 and close_dt.minute == 0
    assert int((close_dt - open_dt).total_seconds() // 60) == 210


def test_C3R5_an_early_close_clips_the_grid_to_the_real_bell(tmp_path):
    """A 210-minute half day is ONE clipped bucket, ending at the actual close.

    A grid that ran to a fictitious 16:00 would hand C3 a bucket whose close was
    never printed, and confirm it four hours after the exchange had gone home.
    """
    buckets = reader_for(Recorder(), tmp_path).buckets("EARLY", EARLY_CLOSE)
    assert len(buckets) == 1
    final = buckets[-1]
    assert final.effective_minutes < fh.FOUR_HOUR_MINUTES
    assert final.effective_minutes == 210
    assert final.clipped is True
    assert final.effective_end == session_window_et(EARLY_CLOSE)[1]
    assert final.close is not None


def test_C3R5_CONTROL_a_normal_session_has_the_390_minute_RTH_shape(tmp_path):
    """The expected shape, STATED — not a bare ``not clipped``.

    A 390-minute day is 240 + 150, so the second bucket is legitimately clipped.
    Asserting "nothing is clipped" here would be false, and asserting only the
    first bucket would hide a grid that lost the afternoon entirely.
    """
    buckets = reader_for(Recorder(), tmp_path).buckets("NORMAL", NEXT_SESSION)
    assert [b.effective_minutes for b in buckets] == [240, 150]
    assert [b.clipped for b in buckets] == [False, True]
    assert buckets[0].start == session_window_et(NEXT_SESSION)[0]
    assert buckets[-1].effective_end == session_window_et(NEXT_SESSION)[1]


# ---------------------------------------------------------------------------
# C3R-6 — BOTH CLOCKS on a C3 event
# ---------------------------------------------------------------------------

def late_wash_closes() -> list[float]:
    """A long rise, then a slide only in the final sessions — a LATE washout.

    Deliberately not ``washout_closes``: that shape's daily K dips under 20 at
    the very start of the C3 window, so ``run_c3`` arms immediately and §10
    expires the arm 15 sessions later — long before the 4H turn is evaluable at
    all.  Here K stays above 20 until the last handful of sessions, so the arm
    lands AFTER the warm-up and the first post-arm turn can actually promote.

    The ripple is fast (period 3) on purpose: a long, slow wobble drives StochRSI
    to its 14-bar floor every cycle, which is how the earlier construction armed
    at the wrong end of the window.
    """
    def fast_ripple(i: int, amp: float = 0.02, period: float = 3.0) -> float:
        return 1.0 + amp * math.sin(2.0 * math.pi * i / period)

    prefix = [(100.0 + 0.5 * i) * fast_ripple(i) for i in range(180)]
    return prefix + [prefix[-1] * (0.97 ** k) for k in range(1, 7)]


def late_wash_pack():
    return build({"LATEWASH": frame_from_closes(late_wash_closes())},
                 tickers=["LATEWASH"])


def run_live_pass(pack, state_dir: Path, *, reader, spool=None, ledger=None):
    """One in-window pass over a one-name pack, with the C3 reader wired in."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)
    ts = now - timedelta(minutes=2)
    row = pack.by_ticker()["LATEWASH"]
    quotes = {"asof": ts.isoformat(), "delayed_min": 15,
              "quotes": {"LATEWASH": {"price": float(row.as_of_close) * 0.97,
                                      "ts": ts.timestamp() * 1000.0,
                                      "source": "polygon", "basis": "trade",
                                      "prevClose": row.as_of_close}}}
    return le.run_pass(now=now, pack=pack, quotes=quotes,
                       ledger=ledger or ll.LiveEpisodeLedger(state_dir),
                       state_dir=state_dir, spool=spool,
                       unspooled_ok=spool is None, intraday_reader=reader, env={})


def utc_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def c3_fire(tmp_path_factory):
    """One real end-to-end C3 candidate, with its spool object on disk."""
    state_dir = tmp_path_factory.mktemp("c3fire")
    pack = late_wash_pack()
    spool = ll.EventSpool(local_dir=state_dir / "spool")
    reader = reader_for(Recorder(), state_dir)
    result = run_live_pass(pack, state_dir, reader=reader, spool=spool)
    events = [e for e in result.delta.events
              if str(e.get("detector_id")) == fh.C3_DETECTOR_ID]
    assert events, "the fixture failed to stage a C3 candidate end to end"
    spooled = sorted((state_dir / "spool").rglob("*.json"))
    assert len(spooled) == 1, spooled
    return {"result": result, "event": events[0], "reader": reader,
            "spooled": json.loads(spooled[0].read_text(encoding="utf-8")),
            "state_dir": state_dir}


def test_C3R6_the_event_is_knowable_at_its_BUCKET_BOUNDARY(c3_fire):
    """A 4H bar is knowable at its close, not when the lane happened to look."""
    event = c3_fire["event"]
    context = dict(event.get("context") or {})
    session = date.fromisoformat(str(context["market_session"]))
    index = int(context["bucket_index"])
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)

    bucket = c3_fire["reader"].buckets("LATEWASH", session, now=now)[index]
    assert bucket.confirmed is True
    assert event["signal_known_ts"] == ch.utc_iso(bucket.effective_end)
    assert event["signal_ts"] == ch.utc_iso(bucket.effective_end)


def test_C3R6_the_spooled_object_is_stamped_with_the_PASS_instant(c3_fire):
    open_dt, _close = session_window_et(NEXT_SESSION)
    now = (open_dt + timedelta(minutes=32)).astimezone(timezone.utc)
    assert c3_fire["spooled"]["pass_ts"] == utc_stamp(now)
    assert c3_fire["result"].payload["asof"] == utc_stamp(now)


def test_C3R6_the_two_clocks_are_DIFFERENT_and_the_signal_is_the_earlier(c3_fire):
    """The whole point: one instant is the market's, the other is the lane's.

    Collapsing them would make a signal look as if it had been knowable only
    when the evaluator got around to reading it — which is the same class of
    error as reading a bar before it closed, pointing the other way.
    """
    signal = datetime.fromisoformat(
        str(c3_fire["event"]["signal_known_ts"]).replace("Z", "+00:00"))
    pass_ts = datetime.fromisoformat(
        str(c3_fire["spooled"]["pass_ts"]).replace("Z", "+00:00"))
    assert signal != pass_ts
    assert signal < pass_ts
    assert signal.date() < pass_ts.date(), "the fixture no longer spans two sessions"


def test_C3R6_the_spooled_event_carries_the_same_knowability(c3_fire):
    """CONTROL: the clock that reaches the spool is the BUCKET's, not the pass's."""
    spooled = [e for e in c3_fire["spooled"]["events"]
               if str(e.get("detector_id")) == fh.C3_DETECTOR_ID]
    assert len(spooled) == 1
    assert spooled[0]["signal_known_ts"] == c3_fire["event"]["signal_known_ts"]
    assert spooled[0]["signal_known_ts"] != c3_fire["spooled"]["pass_ts"]


# ---------------------------------------------------------------------------
# C3R-7 — the import guard: the network stays outside the engine
# ---------------------------------------------------------------------------

def _imports_in(text: str, *, name: str = "<probe>") -> set[str]:
    """Every module path a source imports, AST-level (aliases and locals too)."""
    tree = ast.parse(text, filename=name)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                found.add(module)
            for alias in node.names:
                found.add(f"{module}.{alias.name}" if module else alias.name)
    return found


def _reader_imports(names: set[str]) -> list[str]:
    return sorted(n for n in names
                  if n == "vendor_minutes" or n.endswith(".vendor_minutes")
                  or n.split(".")[-1] == "VendorMinuteReader")


def test_C3R7_the_guard_sources_all_exist():
    """A file-list guard that matches nothing passes for the wrong reason."""
    missing = [n for n in W3_MATH_MODULES if not (RADAR_DIR / n).is_file()]
    assert missing == [], missing


@pytest.mark.parametrize("module", W3_MATH_MODULES)
def test_C3R7_no_W3_math_module_imports_the_vendor_reader(module):
    """The ``IntradayReader`` protocol states what the engine needs; this proves
    the engine never reaches for the thing that supplies it."""
    offenders = _reader_imports(_imports_in(
        (RADAR_DIR / module).read_text(encoding="utf-8"), name=module))
    assert offenders == [], f"{module} imports the vendor reader: {offenders}"


@pytest.mark.parametrize("source,expected", [
    ("import engine.entry_radar.vendor_minutes", "engine.entry_radar.vendor_minutes"),
    ("from engine.entry_radar import vendor_minutes", "engine.entry_radar.vendor_minutes"),
    ("from engine.entry_radar import vendor_minutes as vm",
     "engine.entry_radar.vendor_minutes"),
    ("def f():\n    import engine.entry_radar.vendor_minutes as v\n",
     "engine.entry_radar.vendor_minutes"),
    ("from engine.entry_radar.vendor_minutes import VendorMinuteReader",
     "engine.entry_radar.vendor_minutes"),
])
def test_C3R7_CONTROL_the_scanner_catches_every_planted_import_shape(source, expected):
    """A scanner that never fires proves nothing.

    Aliased and function-local forms are included because those are exactly the
    shapes a line-based grep can be talked past.
    """
    assert expected in _reader_imports(_imports_in(source)), f"scanner missed {source!r}"


# ---------------------------------------------------------------------------
# C3R-8 — importing this module opens no client
# ---------------------------------------------------------------------------

def _module_level_imports(path: Path) -> set[str]:
    """Only the TOP-LEVEL imports.  A function-local one is the lazy shape."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
    return found


def test_C3R8_the_module_pulls_no_network_client_at_import_time():
    """Import-time cost is import-time RISK.

    A network client resolved at module level would sit behind every ``engine``
    import in CI — including the ones that have nothing to do with C3.
    """
    top = _module_level_imports(RADAR_DIR / "vendor_minutes.py")
    offenders = sorted(n for n in top if n.split(".")[0] in NETWORK_ROOTS)
    assert offenders == [], f"vendor_minutes imports {offenders} at module level"


def test_C3R8_CONTROL_default_transport_DOES_resolve_the_vendor_client():
    """The property is LAZINESS, not absence.

    Without this control the test above would pass just as happily on a module
    that had lost its vendor client altogether — which would be a lane that can
    never fetch, dressed as a clean import graph.
    """
    tree = ast.parse((RADAR_DIR / "vendor_minutes.py").read_text(encoding="utf-8"))
    functions = [n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "default_transport"]
    assert len(functions) == 1
    inner = _imports_in(ast.unparse(functions[0]))
    assert "collectors.polygon_options" in inner, sorted(inner)
    assert "collectors.polygon_options" not in _module_level_imports(
        RADAR_DIR / "vendor_minutes.py")


# ---------------------------------------------------------------------------
# C3R-9 — pacing and the counters
# ---------------------------------------------------------------------------

class Naps:
    """Records every sleep the reader asked for, and takes none of them."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.seconds.append(float(seconds))


def test_C3R9_every_call_is_PACED_including_the_empty_and_the_failed(monkeypatch,
                                                                    tmp_path):
    """The vendor counts REQUESTS, not successes.

    A reader that paced only its successes would burst on exactly the pathology
    that produces the most calls — a name the vendor keeps erroring on.
    """
    naps = Naps()
    monkeypatch.setattr(vm.time, "sleep", naps)
    script = [rows_for(AS_OF), [], "boom"]

    def flaky(path, params):
        item = script.pop(0)
        if item == "boom":
            raise RuntimeError("vendor 500")
        return item

    reader = vm.VendorMinuteReader(transport=flaky, state_dir=None,
                                   sleep_seconds=0.06)
    reader("PACE", AS_OF)                       # a normal response
    reader("PACE", NEXT_SESSION)                # an EMPTY response
    with pytest.raises(RuntimeError, match="vendor 500"):
        reader("PACE", EARLY_CLOSE)             # a RAISING transport

    assert naps.seconds == [0.06, 0.06, 0.06]


def test_C3R9_an_empty_response_is_counted_as_empty_and_is_not_an_error(tmp_path):
    reader = vm.VendorMinuteReader(transport=lambda path, params: [],
                                   state_dir=tmp_path, sleep_seconds=0.0)
    reader("GHOST", AS_OF)
    stats = reader.stats().to_dict()
    assert stats["empty"] == 1
    assert stats["errors"] == 0
    assert stats["fetched_n"] == 1


def test_C3R9_a_raising_transport_is_counted_and_PROPAGATES(tmp_path):
    """The reader counts and re-raises; deciding what a dark C3 means is the
    evaluator's job, and is asserted there rather than here."""
    def boom(path, params):
        raise RuntimeError("vendor 500")

    reader = vm.VendorMinuteReader(transport=boom, state_dir=tmp_path,
                                   sleep_seconds=0.0)
    with pytest.raises(RuntimeError, match="vendor 500"):
        reader("BOOM", AS_OF)
    stats = reader.stats().to_dict()
    assert stats["errors"] == 1
    assert stats["fetched_n"] == 0, "a failed call must not count as a fetch"


def test_C3R9_CONTROL_a_reader_paced_at_zero_sleeps_not_at_all(monkeypatch, tmp_path):
    """The pacing is read from ``sleep_seconds``, not hard-coded beside it."""
    naps = Naps()
    monkeypatch.setattr(vm.time, "sleep", naps)
    vm.VendorMinuteReader(transport=Recorder(), state_dir=tmp_path,
                          sleep_seconds=0.0)("PACE", AS_OF)
    assert naps.seconds == []


# ---------------------------------------------------------------------------
# W4R — round-1 adversarial review regressions (C3 lane half)
# ---------------------------------------------------------------------------

class FlakyRecorder(Recorder):
    """A transport that raises on named sessions and serves the rest.

    A transient 502 is exactly the shape the finding was about: the pass used to
    ``continue`` past it, and ``run_c3`` then rebuilt the whole completed-4H
    series over the survivors.
    """

    def __init__(self, fail_on: set[date]) -> None:
        super().__init__()
        self.fail_on = set(fail_on)

    def __call__(self, path: str, params):
        session = date.fromisoformat(path.split("/")[-2])
        if session in self.fail_on:
            raise RuntimeError(f"vendor 502 for {session}")
        return super().__call__(path, params)


def _c3_window(pack, ledger=None) -> list[date]:
    from lib.nyse_calendar import sessions_between
    start = ll.session_at_offset(NEXT_SESSION, -le.C3_WARMUP_SESSIONS)
    return list(sessions_between(start, NEXT_SESSION))


def test_W4R_C1_a_missing_session_REFUSES_C3_rather_than_running_on_a_gapped_series(
        tmp_path):
    """``four_hour_turn`` reads POSITIONAL neighbours of the completed-4H series.

    So a session dropped by a transport fault does not merely thin the series:
    ``rsi_macd_hist`` is recomputed over a SHORTER series, every histogram point
    moves, and prev2/prev/now can straddle a calendar gap.  Measured before the
    fix (20-session warm-up, 3 injected errors): a ``C3Run`` with 36 readings was
    produced with no gap disclosure anywhere — ``completed_4h_gaps`` cannot see
    it, because it counts buckets that were FETCHED and empty and a session never
    fetched contributes no bucket at all.
    """
    pack = late_wash_pack()
    window = _c3_window(pack)
    broken = {window[len(window) // 2], window[len(window) // 2 + 1]}
    reader = reader_for(FlakyRecorder(broken), tmp_path)
    result = run_live_pass(pack, tmp_path, reader=reader)

    name = result.names[0]
    assert "c3_incomplete_window" in name.reasons
    assert name.state == "evaluated", "a C3 fetch fault must dark the LANE, not the name"
    assert name.lanes.get("c3") is None, "C3 ran on a gapped series"
    block = name.lanes["c3_incomplete"]
    assert block["availability"] == "unavailable"
    assert set(block["missing_sessions"]) == {d.isoformat() for d in broken}
    assert result.health["inputs"]["c3_reader"]["incomplete_n"] == 1
    assert "c3_incomplete_window:1" in result.health["reasons"]
    assert result.health["dark"]["c3_incomplete_window"] == 1


def test_W4R_C1_CONTROL_an_unbroken_window_still_runs_C3(tmp_path):
    """Without this the refusal above could be a fixture that never ran C3."""
    pack = late_wash_pack()
    result = run_live_pass(pack, tmp_path, reader=reader_for(Recorder(), tmp_path))
    name = result.names[0]
    assert "c3_incomplete_window" not in name.reasons
    assert name.lanes.get("c3"), "the control produced no C3 readings at all"
    assert result.health["inputs"]["c3_reader"]["incomplete_n"] == 0


def test_W4R_C1b_an_AGGREGATION_fault_still_reaches_c3_reader_errors(tmp_path,
                                                                     monkeypatch):
    """``VendorMinuteReader.errors`` increments ONLY on a transport raise.

    A raise from ``four_hour_buckets``/``_bucket_from_dict`` — including the
    mixed-timezone case that function's own docstring warns about — never touches
    it, and the pass used to OVERWRITE its own honest count with the reader's.
    Measured: 3 sessions errored, ``stats`` came back ``errors: 0``, so the
    ``c3_reader_errors`` health reason could not fire and the state stayed
    ``live``.
    """
    pack = late_wash_pack()
    window = _c3_window(pack)
    doomed = {window[len(window) // 2]}
    real = vm.VendorMinuteReader.buckets

    def exploding(self, ticker, session, *, now=None, vintage=None):
        if session in doomed:
            raise ValueError("aggregation fault: mixed tz in the bucket list")
        return real(self, ticker, session, now=now, vintage=vintage)

    monkeypatch.setattr(vm.VendorMinuteReader, "buckets", exploding)
    reader = reader_for(Recorder(), tmp_path)
    result = run_live_pass(pack, tmp_path, reader=reader)

    stats = result.health["inputs"]["c3_reader"]
    assert reader.stats().errors == 0, "the fixture raised inside the transport"
    assert stats["errors"] == 1, "the pass-local count was overwritten again"
    assert stats["reader_errors"] == 0
    assert "c3_reader_errors:1" in result.health["reasons"]
    assert result.health["state"] == "degraded"


def test_W4R_C1b_the_reader_counters_ride_a_NAMESPACE_of_their_own(tmp_path):
    pack = late_wash_pack()
    reader = reader_for(Recorder(), tmp_path)
    stats = run_live_pass(pack, tmp_path, reader=reader).health["inputs"]["c3_reader"]
    for key in ("fetched_n", "cache_hits", "errors", "empty"):
        assert f"reader_{key}" in stats, key
    assert stats["reader_fetched_n"] == reader.stats().fetched_n
    for key in sorted(le.PASS_OWNED_C3_STATS):
        assert key in stats


# --- H4: the bucket cache carries its adjustment vintage --------------------

def _vintage(pack, ticker: str, session: date) -> dict:
    daily = le.pack_daily_history(pack, ticker)
    return {"pack_as_of": pack.as_of,
            "substrate_fingerprint": le.substrate_fingerprint(daily, session)}


def test_W4R_H4_a_moved_adjustment_basis_DROPS_the_whole_ticker_cache(tmp_path):
    """Adjusted minute aggregates are NOT immutable.

    A split or a large cash dividend retroactively rescales the vendor's entire
    adjusted history, and the cache key was ``(TICKER, session)`` alone — no
    ``as_of``, no ``pack_hash``, no adjustment epoch.  ``run_c3`` would then
    receive pre-adjustment cached closes beside post-adjustment fresh ones across
    the split boundary: a fabricated move in the 4H histogram, which fabricates a
    turn.  W3-1, reintroduced in the one lane where no basis audit runs.
    """
    pack = late_wash_pack()
    stamp = _vintage(pack, "LATEWASH", AS_OF)
    assert stamp["substrate_fingerprint"], "the fixture has no fingerprint to move"

    recorder = Recorder()
    warm = reader_for(recorder, tmp_path)
    warm.buckets("LATEWASH", AS_OF, vintage=stamp)
    warmed = len(recorder.calls)
    assert AS_OF.isoformat() in (cache_body(tmp_path, "LATEWASH").get("sessions") or {})

    rescaled = dict(stamp, substrate_fingerprint="a-post-split-fingerprint")
    after = reader_for(recorder, tmp_path)
    after.buckets("LATEWASH", AS_OF, vintage=rescaled)
    assert len(recorder.calls) == warmed + 1, "the stale-basis cache was served"
    assert after.cache_hits == 0 and after.fetched_n == 1


def test_W4R_H4_the_invalidation_is_the_WHOLE_ticker_not_the_moved_row(tmp_path):
    """"Drop that row" is the variant the ruling rejected, and it is worse than
    no cache at all.

    The damage a corporate action does is the SEAM: pre-adjustment closes spliced
    to post-adjustment ones inside one 4H series fabricate a move, which
    fabricates a turn.  Invalidating only the session whose fingerprint moved
    leaves every OTHER cached session on the old basis — which is exactly the
    spliced series.  Warming a single session cannot tell the two apart, so this
    warms several and requires all of them gone.
    """
    pack = late_wash_pack()
    sessions = [s for s in (ll.session_at_offset(AS_OF, -n) for n in (2, 1, 0))
                if s is not None]
    assert len(sessions) == 3, "the fixture needs a multi-session window"

    recorder = Recorder()
    warm = reader_for(recorder, tmp_path)
    for session in sessions:
        warm.buckets("LATEWASH", session, vintage=_vintage(pack, "LATEWASH", session))
    cached = set((cache_body(tmp_path, "LATEWASH").get("sessions") or {}))
    assert len(cached) == 3, f"only {len(cached)} session(s) cached; nothing to drop"

    # ONE session's basis moves — a split makes the whole history disagree, but
    # the caller notices it at whichever session it asks about first.
    moved = sessions[-1]
    after = reader_for(recorder, tmp_path)
    after.buckets("LATEWASH", moved,
                  vintage=dict(_vintage(pack, "LATEWASH", moved),
                               substrate_fingerprint="a-post-split-fingerprint"))
    left = set((cache_body(tmp_path, "LATEWASH").get("sessions") or {}))
    assert left <= {moved.isoformat()}, (
        f"sessions on the OLD basis survived the rescale: {sorted(left)} — the "
        "next window splices them to fresh post-adjustment closes")


def test_W4R_H4_CONTROL_the_SAME_fingerprint_still_serves_the_cache(tmp_path):
    """The invalidation must be about the BASIS, not about caching at all — a
    guard that drops every row is the same as having no cache."""
    pack = late_wash_pack()
    stamp = _vintage(pack, "LATEWASH", AS_OF)
    recorder = Recorder()
    reader_for(recorder, tmp_path).buckets("LATEWASH", AS_OF, vintage=stamp)
    warmed = len(recorder.calls)

    second = reader_for(recorder, tmp_path)
    second.buckets("LATEWASH", AS_OF, vintage=dict(stamp, pack_as_of="2099-01-01"))
    assert len(recorder.calls) == warmed, "a nightly pack bump threw the cache away"
    assert second.cache_hits == 1 and second.fetched_n == 0


def test_W4R_H4_the_stored_row_records_the_basis_it_was_written_on(tmp_path):
    pack = late_wash_pack()
    stamp = _vintage(pack, "LATEWASH", AS_OF)
    reader_for(Recorder(), tmp_path).buckets("LATEWASH", AS_OF, vintage=stamp)
    row = cache_body(tmp_path, "LATEWASH")["sessions"][AS_OF.isoformat()]
    assert row["vintage"] == stamp
    assert row["buckets"] and all(b["confirmed"] for b in row["buckets"])


def test_W4R_H4_the_fingerprint_moves_with_the_ADJUSTED_CLOSE_and_nothing_else():
    """A fingerprint that moved on every nightly close would invalidate the cache
    daily; one that moved on nothing would never invalidate it."""
    import pandas as pd

    from engine.entry_radar import challengers as ch2

    pack = late_wash_pack()
    daily = le.pack_daily_history(pack, "LATEWASH")
    base = le.substrate_fingerprint(daily, AS_OF)
    assert base is not None

    frame = daily.frame.copy()
    frame.loc[frame.index == pd.Timestamp(AS_OF), "close"] *= 0.5   # a 2:1 split
    split = ch2.DailyHistory(frame=frame, price_basis=daily.price_basis,
                             vintage=daily.vintage)
    assert le.substrate_fingerprint(split, AS_OF) != base

    missing = ll.session_at_offset(AS_OF, -5000)
    assert le.substrate_fingerprint(daily, missing) is None, \
        "a session outside the substrate must be UNCHECKABLE, never a false match"
