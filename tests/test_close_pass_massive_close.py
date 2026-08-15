"""tests/test_close_pass_massive_close.py — same-day close truth (breathing PR-A).

WHAT IS ACTUALLY AT RISK HERE, and therefore what this file pins.

The evening pass used to skip every name whose store bar was not today's — 1,508
of 1,763 on Friday 2026-08-14, 86% of the universe. Filling those from the vendor
is a coverage win and a TRUTH RISK in the same edit: a close spliced onto a
history it does not belong to is a fabricated gap the gate will happily score, and
it fails SILENTLY, because a wrong price looks exactly like a right one.

Three properties are the difference between the two outcomes, and each has its own
section below:

  SESSION      a vendor row must PROVE it belongs to the session before it is
               used. Grouped daily carries the session in its URL; the snapshot
               does not, and a snapshot read at 16:01 ET on a Monday still hands
               out Friday's `day` bar. That row is refused.
  BASIS        a store history is re-based retrospectively at each ex-date, so
               today's raw close IS today's adjusted close for any name with no
               same-session corporate action — and is off BY THE SPLIT FACTOR for
               any name with one. Those names are darked, never spliced.
  FAIL-CLOSED  the corp-action read is the guard, so an incomplete one is GUARD
               DOWN and stops every append that pass. "We did not get to look" is
               not evidence that nobody split.

CHAOS (commission §12) lives in the last section: a synthetic 10:1 split whose
splice flips the REAL gate's verdict, proved in both directions — the guard darks
it, and a deliberately-broken guard shows the verdict it would have flipped.

SPARSE-TREE SAFE. Nothing here reads `data/`: the universe, the price store and
the vendor are all stubbed at their own seams. The parity battery
(`scripts/measure_massive_close_parity.py`) is the piece that needs the real
store, and it is a script rather than a test for exactly that reason.
"""
from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_stock_library as BSL  # noqa: E402
import scripts.close_pass_publish as P  # noqa: E402
from engine import signal_gate  # noqa: E402
from engine.close_pass import massive_close as MC  # noqa: E402
from engine.prophet_live import interval  # noqa: E402

SESSION = "2026-08-14"          # a Friday, and the measured defect's own session
NEXT_SESSION = "2026-08-17"     # the Monday a stale Friday snapshot lands on
PRIOR = "2026-08-13"

ADJ = interval.ADJUSTED


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — a price store, a universe and a vendor, all stubbed at their seam
# ─────────────────────────────────────────────────────────────────────────────
def series(seed: int = 4, *, periods: int = 420, end: str = PRIOR,
           name: str = "X") -> pd.Series:
    """A plausible daily close history ENDING at ``end`` (never at SESSION).

    Deterministic: PCG64's stream is a stability guarantee, so the same seed is
    the same series on every machine and every numpy. Seed 4 is not arbitrary —
    see `test_a_split_day_splice_would_flip_the_real_gates_verdict`.
    """
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=periods)
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0009, 0.013, len(idx))))
    return pd.Series(px, index=idx, name=name)


def universe(spec: dict[str, pd.Series]):
    """The 5-tuple shape ``build_stock_library.universe()`` returns."""
    return [(t, s, None, f"{t} Corp", "Technology") for t, s in spec.items()]


@pytest.fixture
def store(monkeypatch):
    """Drive the real ``collect()`` over a stubbed universe and a stubbed vendor.

    Every seam is patched where the LANE reaches it, so the function under test
    is the one the workflow calls rather than a re-implementation of it.
    """
    from lib import delisted_symbols

    class Store:
        session = SESSION

        def run(self, spec: dict[str, pd.Series], *, closes=None,
                source=MC.SOURCE_GROUPED, finalized=True, reason=None,
                corp=(), complete=True, corp_reason=None,
                session: str = SESSION) -> dict:
            monkeypatch.setattr(BSL, "universe", lambda: universe(spec))
            monkeypatch.setattr(BSL, "universe_price_adjustment",
                                lambda: {t: ADJ for t in spec})
            monkeypatch.setattr(delisted_symbols, "is_delisted", lambda t: False)
            vendor = dict(closes or {})
            monkeypatch.setattr(P.MC, "fetch_session_closes",
                                lambda s, wanted, **kw: MC.SessionCloses(
                                    session=s, closes=vendor,
                                    source=source if vendor else None,
                                    observed_at="2026-08-14T20:26:00Z",
                                    finalized=finalized,
                                    vendor_rows=12_424, wanted_n=len(list(wanted)),
                                    matched_n=len(vendor), reason=reason))
            monkeypatch.setattr(P.MC, "corp_action_tickers",
                                lambda s, **kw: MC.CorpActions(
                                    session=s, tickers=frozenset(corp),
                                    splits_n=len(corp), dividends_n=0,
                                    complete=complete, reason=corp_reason))
            return P.collect(session)

    return Store()


def grouped(rows: dict[str, float]) -> dict:
    return {"status": "OK",
            "results": [{"T": t, "c": c, "v": 1} for t, c in rows.items()]}


def snapshot(rows: dict[str, tuple[float, int]]) -> dict:
    """``{ticker: (day close, updated ns)}`` → a full-market snapshot body."""
    return {"status": "OK",
            "tickers": [{"ticker": t, "day": {"c": c}, "updated": ns,
                         "lastTrade": {"p": c * 1.5, "t": ns}}
                        for t, (c, ns) in rows.items()]}


#: 2026-08-14T20:00:00.000Z = 16:00:00 ET — the measured freeze stamp of AAPL's
#: Friday day-bar, read on the Saturday. Every snapshot fixture derives from it.
FRIDAY_CLOSE_NS = 1_786_752_000_000_000_000
ONE_DAY_NS = 86_400 * 1_000_000_000


# ─────────────────────────────────────────────────────────────────────────────
# SESSION — a vendor row proves which day it is, or it is not used
# ─────────────────────────────────────────────────────────────────────────────
def test_the_measured_freeze_stamp_resolves_to_the_session_it_closed():
    """The anchor every snapshot check rests on, taken from the live API rather
    than computed: AAPL's Friday `updated` stamp is exactly 16:00:00 ET, so a day
    bar's own stamp names its session and the evening's after-hours prints did not
    move it."""
    assert MC.et_session_of(FRIDAY_CLOSE_NS) == SESSION
    # ...and the ET conversion is real, not a UTC-date coincidence: 20:00Z is the
    # same DAY in UTC and in ET here, but 23:30Z on the same date is not.
    assert MC.et_session_of(FRIDAY_CLOSE_NS + 3.5 * 3600 * 10**9) == "2026-08-14"
    assert MC.et_session_of(FRIDAY_CLOSE_NS + 5 * 3600 * 10**9) == "2026-08-15"


def test_a_snapshot_row_from_another_session_is_refused():
    """THE stale-bar defect, in the shape it really arrives in: a Monday 16:01 ET
    read, before the day's grouped aggregate exists, where a thin name has not
    printed a Monday bar and still carries FRIDAY's `day` object. Splicing that
    would put a three-day-old close under today's date — the mixed-vintage board
    the `no_todays_bar` skip exists to prevent, only silent."""
    monday_ns = FRIDAY_CLOSE_NS + 3 * ONE_DAY_NS
    body = snapshot({"FRESH": (50.0, monday_ns), "STALE": (11.0, FRIDAY_CLOSE_NS)})
    out = MC.fetch_session_closes(
        NEXT_SESSION, ["FRESH", "STALE"],
        fetch=lambda url, params=None: (None if "grouped" in url else body))
    assert dict(out.closes) == {"FRESH": 50.0}
    assert out.source == MC.SOURCE_SNAPSHOT and out.finalized is False
    # The same body, read for the session it DOES belong to, yields the other name
    # — so this is a session check and not a filter that drops odd rows.
    friday = MC.fetch_session_closes(
        SESSION, ["FRESH", "STALE"],
        fetch=lambda url, params=None: (None if "grouped" in url else body))
    assert dict(friday.closes) == {"STALE": 11.0}


def test_a_row_with_no_readable_stamp_is_refused_rather_than_assumed():
    """Fail closed on the check itself. A missing, mistyped or MILLIsecond
    `updated` cannot say which session the bar belongs to, and a bar that cannot
    prove its session is not a bar this lane will splice."""
    body = {"status": "OK", "tickers": [
        {"ticker": "NOSTAMP", "day": {"c": 1.0}},
        {"ticker": "MILLIS", "day": {"c": 2.0}, "updated": FRIDAY_CLOSE_NS // 10**6},
        {"ticker": "JUNK", "day": {"c": 3.0}, "updated": "yesterday"},
        {"ticker": "GOOD", "day": {"c": 4.0}, "updated": FRIDAY_CLOSE_NS}]}
    out = MC.fetch_session_closes(
        SESSION, ["NOSTAMP", "MILLIS", "JUNK", "GOOD"],
        fetch=lambda url, params=None: (None if "grouped" in url else body))
    assert dict(out.closes) == {"GOOD": 4.0}
    for bad in (None, True, "", "2026-08-14", 12345, 10**24):
        assert MC.et_session_of(bad) is None, bad


def test_a_last_trade_is_never_read_as_a_close():
    """`lastTrade` is the last print of ANY session including after-hours, so on
    a news evening it is a different number from the close every other surface in
    this estate quotes. The fixture makes them differ by 50% on purpose; the day
    bar is what comes back."""
    body = snapshot({"AAA": (100.0, FRIDAY_CLOSE_NS)})
    assert body["tickers"][0]["lastTrade"]["p"] == 150.0
    out = MC.fetch_session_closes(
        SESSION, ["AAA"],
        fetch=lambda url, params=None: (None if "grouped" in url else body))
    assert dict(out.closes) == {"AAA": 100.0}
    # A row with NO day bar yields nothing at all rather than falling through to
    # the trade rung.
    only_trade = {"status": "OK", "tickers": [
        {"ticker": "AAA", "updated": FRIDAY_CLOSE_NS, "lastTrade": {"p": 150.0}}]}
    empty = MC.fetch_session_closes(
        SESSION, ["AAA"],
        fetch=lambda url, params=None: (None if "grouped" in url else only_trade))
    assert not empty.closes and empty.ok is False


def test_grouped_is_preferred_and_the_snapshot_is_only_the_early_minutes_fallback():
    """Order is the contract: grouped daily is the session's FINALIZED aggregate
    and is asked first; the snapshot is reached only when grouped came back empty
    or unavailable, which is the state of the world for the minutes right after
    the close."""
    seen: list[str] = []

    def fetch(url, params=None):
        seen.append(url)
        return grouped({"AAA": 10.0}) if "grouped" in url else snapshot(
            {"AAA": (99.0, FRIDAY_CLOSE_NS)})

    out = MC.fetch_session_closes(SESSION, ["AAA"], fetch=fetch)
    assert dict(out.closes) == {"AAA": 10.0}
    assert out.source == MC.SOURCE_GROUPED and out.finalized is True
    assert len(seen) == 1 and "grouped" in seen[0]          # snapshot never asked
    # `adjusted=false` is not optional — an adjusted grouped bar would be a
    # different number on any name with history behind an ex-date.
    got: dict = {}
    MC.fetch_session_closes(SESSION, ["AAA"],
                            fetch=lambda url, params=None: got.update(params or {}))
    assert got.get("adjusted") == "false"

    seen.clear()
    empty = MC.fetch_session_closes(
        SESSION, ["AAA"],
        fetch=lambda url, params=None: ({"status": "OK", "results": []}
                                        if "grouped" in url
                                        else snapshot({"AAA": (99.0,
                                                               FRIDAY_CLOSE_NS)})))
    assert dict(empty.closes) == {"AAA": 99.0}
    assert empty.source == MC.SOURCE_SNAPSHOT and empty.finalized is False
    assert len(seen) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Identity — one company, two spellings
# ─────────────────────────────────────────────────────────────────────────────
def test_the_vendors_dot_and_the_universes_hyphen_are_one_company():
    """`build_stock_library` normalises every holdings name through
    `.replace(".", "-")`, so BRK.B on the tape is BRK-B on the board. Without the
    fold a 12,424-row market read matches the universe minus its class shares —
    a coverage hole that looks like thin vendor coverage and is not."""
    assert MC.universe_ticker("BRK.B") == "BRK-B"
    assert MC.universe_ticker(" BRK.B ") == "BRK-B"
    assert MC.universe_ticker("AAPL") == "AAPL"
    out = MC.fetch_session_closes(
        SESSION, ["BRK-B", "AAPL"],
        fetch=lambda url, params=None: grouped({"BRK.B": 504.03, "AAPL": 305.93}))
    assert dict(out.closes) == {"BRK-B": 504.03, "AAPL": 305.93}


def test_the_vendors_lowercase_letter_is_a_different_security(monkeypatch):
    """MEASURED 2026-08-15, and this code got it wrong first.

    The vendor's ticker space is case-SENSITIVE — a lowercase letter marks a
    different security on the same root. Grouped daily for 2026-08-13 carried
    `TPC` (Tutor Perini, common, 94.67) beside `TpC` (16.98), and `BCPC`
    (Balchem, common, 177.14) beside `BCpC` (Brunswick 6.375% Notes due 2049,
    23.9999). Upper-casing the vendor side collapses each pair and the LAST row
    in the payload wins: the parity battery caught TPC coming back at 16.98, a
    5.6x mis-price, while Balchem survived on payload ORDER alone.

    Both orderings are asserted, because "right in the test, wrong in production"
    is exactly the failure the ordering produced.
    """
    for order in (["TPC", "TpC"], ["TpC", "TPC"]):
        body = grouped({t: (94.67 if t == "TPC" else 16.98) for t in order})
        out = MC.fetch_session_closes(SESSION, ["TPC"],
                                      fetch=lambda url, params=None: body)
        assert dict(out.closes) == {"TPC": 94.67}, order
    for order in (["BCPC", "BCpC"], ["BCpC", "BCPC"]):
        body = grouped({t: (177.14 if t == "BCPC" else 23.9999) for t in order})
        out = MC.fetch_session_closes(SESSION, ["BCPC"],
                                      fetch=lambda url, params=None: body)
        assert dict(out.closes) == {"BCPC": 177.14}, order
    # A name the vendor ONLY spells in mixed case is simply not filled — a
    # coverage miss, which is the safe direction. It is never filled from the
    # upper-cased sibling.
    lone = MC.fetch_session_closes(
        SESSION, ["TPC"], fetch=lambda url, params=None: grouped({"TpC": 16.98}))
    assert lone.closes == {} and lone.ok is False


def test_the_corp_action_guard_darks_both_spellings_because_it_fails_closed():
    """The deliberate asymmetry with the matcher above. A mis-identified PRICE is
    a wrong number on a board, so matching is case-exact; a missed DARK splices a
    split-day price onto a pre-split history, so the guard takes both spellings.
    Over-darking costs one name's coverage for one night. Measured 2026-08-13 and
    2026-08-14: zero corp-action rows were mixed-case and upper-cased into the
    real universe, so today it costs nothing at all."""
    out = MC.corp_action_tickers(
        SESSION,
        fetch=lambda url, params=None: (
            {"status": "OK", "results": [{"ticker": "TpC"}]}
            if url == MC.SPLITS_PATH else {"status": "OK", "results": []}))
    assert {"TpC", "TPC"} <= out.tickers and out.complete is True


def test_an_exact_vendor_match_wins_over_a_folded_one():
    """The fold is lossy — `BRK.B` and a genuine `BRK-B` collapse onto one key —
    so the unambiguous match is taken first and the fold only FILLS what is still
    missing. Without the two passes the winner is whichever row the vendor
    happened to list last: an order-dependent mis-price on a class share."""
    body = grouped({"BRK-B": 504.03, "BRK.B": 999.99})
    assert dict(MC.fetch_session_closes(
        SESSION, ["BRK-B"], fetch=lambda url, params=None: body).closes) == {
        "BRK-B": 504.03}
    # ...and the reverse listing order gives the same answer, which is the point.
    body["results"].reverse()
    assert dict(MC.fetch_session_closes(
        SESSION, ["BRK-B"], fetch=lambda url, params=None: body).closes) == {
        "BRK-B": 504.03}


def test_a_zero_or_unusable_close_is_not_a_price():
    """A vendor zero is a row that did not trade, not a $0.00 stock. NaN, inf,
    negatives, booleans and strings are the other shapes of "no number", and each
    would reach a card as a price if it were merely truthy."""
    body = grouped({"AAA": 0.0, "BBB": float("nan"), "CCC": float("inf"),
                    "DDD": -5.0, "EEE": None, "FFF": "12.5", "GGG": 7.5})
    body["results"].append({"T": "HHH"})                    # no `c` key at all
    out = MC.fetch_session_closes(
        SESSION, ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
        fetch=lambda url, params=None: body)
    # "12.5" IS a number the vendor spelled as a string — float() is the honest
    # read of it. Everything that is not a positive finite number is refused.
    assert dict(out.closes) == {"FFF": 12.5, "GGG": 7.5}
    assert out.vendor_rows == 8 and out.matched_n == 2 and out.wanted_n == 8


# ─────────────────────────────────────────────────────────────────────────────
# The contract — never raises, bounded, keyless-safe
# ─────────────────────────────────────────────────────────────────────────────
def test_no_key_degrades_cleanly_and_names_the_env_var_never_a_value(monkeypatch):
    """A lane that has to publish inside 30 minutes cannot be taken down by a
    missing secret. The degrade names the ENV VAR so an operator can act on the
    run log — and the value never appears anywhere, which is the property that
    survives someone pasting a reason into an issue."""
    for name in MC.KEY_ENVS:
        monkeypatch.delenv(name, raising=False)
    assert MC.api_key() is None
    out = MC.fetch_session_closes(SESSION, ["AAA"])
    assert out.ok is False and out.closes == {} and out.source is None
    assert "MASSIVE_API_KEY" in (out.reason or "")
    guard = MC.corp_action_tickers(SESSION)
    assert guard.complete is False and "MASSIVE_API_KEY" in (guard.reason or "")

    monkeypatch.setenv("MASSIVE_API_KEY", "s3cr3t-not-a-real-key")
    assert MC.api_key() == "s3cr3t-not-a-real-key"
    boom = MC.fetch_session_closes(
        SESSION, ["AAA"], fetch=lambda url, params=None: 1 / 0)
    assert boom.ok is False and "s3cr3t" not in (boom.reason or "")


@pytest.mark.parametrize("payload", [
    None, {}, {"status": "NOT_AUTHORIZED"}, {"results": None}, {"results": "x"},
    [1, 2, 3], "nope", {"results": [None, 7, {"T": None}]},
])
def test_the_public_functions_never_raise_whatever_comes_back(payload):
    """The whole degrade contract in one sweep. Every one of these is a shape a
    vendor has actually returned somewhere in this estate; none of them may reach
    the lane as an exception, because the lane's answer to an exception is no
    board at all."""
    out = MC.fetch_session_closes(SESSION, ["AAA"],
                                  fetch=lambda url, params=None: payload)
    assert isinstance(out, MC.SessionCloses) and out.ok is False
    assert out.reason and out.basis == MC.BASIS
    guard = MC.corp_action_tickers(SESSION, fetch=lambda url, params=None: payload)
    assert isinstance(guard, MC.CorpActions) and guard.complete is False


def test_a_raising_fetch_is_an_absent_answer_not_an_exception():
    def boom(url, params=None):
        raise TimeoutError("read timed out")

    out = MC.fetch_session_closes(SESSION, ["AAA"], fetch=boom)
    assert out.ok is False and "TimeoutError" in (out.reason or "")
    guard = MC.corp_action_tickers(SESSION, fetch=boom)
    assert guard.complete is False and guard.tickers == frozenset()


def test_the_retry_budget_is_bounded_and_a_4xx_is_never_retried(monkeypatch):
    """Bounded by count, and asymmetric by design: a 5xx or a transport error may
    be transient, a 403/404 is an ANSWER. Re-asking an answer is the retry storm
    the cap exists to prevent, and this lane shares one vendor quota with the
    nightly."""
    import types
    calls: list[float | None] = []

    class Resp:
        def __init__(self, status): self.status_code = status
        def json(self): return {"status": "OK", "results": []}

    class FakeSession:
        def __init__(self, statuses):
            self.headers: dict = {}
            self._statuses = list(statuses)

        def get(self, url, params=None, timeout=None):
            calls.append(timeout)
            status = self._statuses.pop(0)
            if status == "boom":
                raise OSError("connection reset")
            return Resp(status)

    def over(statuses):
        """The REAL `_default_fetch`, running over a fake `requests`."""
        calls.clear()
        monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
            Session=lambda: FakeSession(statuses)))
        return MC._default_fetch("k")

    assert over([500, 500, 500])("/v3/x", None) is None
    assert len(calls) == MC.ATTEMPTS == 3
    assert all(t == MC.TIMEOUT_S for t in calls)

    assert over([403, 403, 403])("/v3/x", None) is None
    assert len(calls) == 1, "a 4xx is an answer — it must not be re-asked"

    assert over(["boom", 200])("/v3/x", None) == {"status": "OK", "results": []}
    assert len(calls) == 2                                # retried once, then won


def test_the_key_rides_a_header_and_never_a_query_string(monkeypatch):
    """The one property that keeps a secret out of a URL, an exception message
    and a proxy log alike. Asserted on the session the module actually builds."""
    import types
    captured: dict = {}

    class FakeSession:
        headers: dict = {}
        def get(self, url, params=None, timeout=None):
            captured["url"], captured["params"] = url, params
            raise OSError("stop here")

    fake = FakeSession()
    monkeypatch.setitem(sys.modules, "requests",
                        types.SimpleNamespace(Session=lambda: fake))
    MC._default_fetch("sup3r-secret")(MC.SNAPSHOT_PATH, {"adjusted": "false"})
    assert fake.headers["Authorization"] == "Bearer sup3r-secret"
    assert "sup3r-secret" not in captured["url"]
    assert "sup3r-secret" not in str(captured["params"])
    assert captured["url"].startswith("https://")


def test_a_next_url_is_followed_verbatim_without_the_original_query():
    """A cursor already carries the query it was minted from. Re-sending the
    original params alongside it is how a paginator silently restarts at page
    one and loops until the cap."""
    pages = {
        MC.SPLITS_PATH: {"status": "OK", "results": [{"ticker": "AAA"}],
                         "next_url": "https://api.polygon.io/v3/reference/splits?cursor=2"},
        "https://api.polygon.io/v3/reference/splits?cursor=2":
            {"status": "OK", "results": [{"ticker": "BBB"}]},
        MC.DIVIDENDS_PATH: {"status": "OK", "results": [{"ticker": "CCC"}]},
    }
    seen: list[tuple] = []

    def fetch(url, params=None):
        seen.append((url, params))
        return pages.get(url, {"status": "OK", "results": []})

    out = MC.corp_action_tickers(SESSION, fetch=fetch)
    assert out.tickers == frozenset({"AAA", "BBB", "CCC"})
    assert out.complete is True and out.splits_n == 2 and out.dividends_n == 1
    cursor = [p for u, p in seen if "cursor=2" in u]
    assert cursor == [None], "the cursor page must not re-send the first query"


def test_a_capped_or_refused_corp_action_walk_is_incomplete_never_empty():
    """The fail-closed half. An under-reported action set is WORSE than none: it
    reads as "no name had an action today" on exactly the names that had one. So
    a page cap, a failed page and a 200-with-NOT_AUTHORIZED all report
    `complete=False` rather than a short list."""
    endless = {"status": "OK", "results": [{"ticker": "AAA"}],
               "next_url": "https://api.polygon.io/v3/reference/splits?cursor=x"}
    capped = MC.corp_action_tickers(SESSION, fetch=lambda url, params=None: endless)
    assert capped.complete is False and "AAA" in capped.tickers

    refused = MC.corp_action_tickers(
        SESSION, fetch=lambda url, params=None: {"status": "NOT_AUTHORIZED"})
    assert refused.complete is False and refused.tickers == frozenset()

    # A genuinely quiet day IS complete with zero rows — an empty list is not one
    # of the ways to be incomplete, or the guard would never let anything through.
    quiet = MC.corp_action_tickers(
        SESSION, fetch=lambda url, params=None: {"status": "OK", "results": []})
    assert quiet.complete is True and quiet.tickers == frozenset()


def test_a_split_and_an_ex_dividend_both_dark_the_name():
    """Both re-base the history, so both break "today's raw close is today's
    adjusted close". Measured 2026-08-14: 3 splits (IDTIF 200:1, HAO 20:1, BYND
    1:30 reverse) and 450 ex-dividends. The vendor's dotted spelling is folded
    here too — a darked BRK.B that reached the caller as `BRK.B` would never match
    the `BRK-B` it was meant to protect."""
    def fetch(url, params=None):
        if url == MC.SPLITS_PATH:
            assert params["execution_date"] == SESSION
            return {"status": "OK", "results": [{"ticker": "BYND"},
                                                {"ticker": "BRK.B"}]}
        assert params["ex_dividend_date"] == SESSION
        return {"status": "OK", "results": [{"ticker": "KO"}]}

    out = MC.corp_action_tickers(SESSION, fetch=fetch)
    assert out.tickers == frozenset({"BYND", "BRK-B", "KO"})
    assert out.splits_n == 2 and out.dividends_n == 1 and out.complete is True


def test_the_basis_names_the_adjustment_and_the_session_rung():
    """W-L0 gate 3 — name the adjustment at every seam. `raw_rth_close` is
    narrower than the estate's UNADJUSTED family because it also says WHICH print:
    the regular-hours close, never an after-hours one. The family is imported, not
    restated — three names for one fact is how two surfaces end up disagreeing
    about what "adjusted" meant."""
    assert MC.BASIS == "raw_rth_close"
    assert MC.BASIS_FAMILY == interval.UNADJUSTED == "unadjusted_vendor_print"
    assert MC.SessionCloses(session=SESSION).basis == MC.BASIS


def test_the_module_imports_with_no_pandas_and_no_requests(monkeypatch):
    """It is imported by `close_pass_publish`, which has a `--help` path, and by
    the mirror, which installs neither. Heavy imports are function-scoped so the
    module itself costs nothing to load."""
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name.split(".")[0] in ("pandas", "numpy", "requests", "boto3"):
            raise ModuleNotFoundError(f"blocked: {name}")
        return real(name, *a, **k)

    spec = importlib.util.spec_from_file_location(
        "massive_close_bare", ROOT / "engine" / "close_pass" / "massive_close.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "massive_close_bare", module)
    monkeypatch.setattr(builtins, "__import__", blocked)
    spec.loader.exec_module(module)                    # raises if anything heavy
    monkeypatch.setattr(builtins, "__import__", real)
    assert module.BASIS == MC.BASIS


# ─────────────────────────────────────────────────────────────────────────────
# The lane — what `collect()` does with all of the above
# ─────────────────────────────────────────────────────────────────────────────
def test_a_name_with_no_store_bar_is_filled_and_the_board_says_where_from(store):
    """The coverage defect, closed. AAA's store ends yesterday — the state 86% of
    the universe was in on 2026-08-14 — and the vendor's close carries it into the
    evaluated set instead of into `no_todays_bar`."""
    out = store.run({"AAA": series(name="AAA"), "BBB": series(5, name="BBB")},
                    closes={"AAA": 111.0, "BBB": 222.0})
    assert set(out["verdicts"]) == {"AAA", "BBB"}
    assert out["skipped"].get("no_todays_bar") is None
    assert out["price_through"] == {"AAA": SESSION, "BBB": SESSION}

    meta = out["close_meta"]
    assert meta["close_source"] == {"store": 0, "massive": 2}
    assert meta["close_basis"] == MC.BASIS and meta["close_finalized"] is True
    assert meta["close_fill_source"] == MC.SOURCE_GROUPED
    assert "close_degraded" not in meta
    # The DISPLAY price of a filled name is the price it was filled with — the
    # card and the gate must not disagree about what today's close was.
    admitted = [t for t, v in out["verdicts"].items() if signal_gate.is_buyable(v)]
    for ticker in admitted:
        assert out["display_by"][ticker]["price"] == pytest.approx(
            {"AAA": 111.0, "BBB": 222.0}[ticker])


def test_the_stores_own_today_bar_wins_over_the_vendor(store):
    """Basis consistency, not favouritism. A store bar and the history behind it
    come from ONE vendor on ONE convention; replacing it with another vendor's
    print to gain nothing would introduce a seam where there is currently none."""
    fresh = series(name="AAA")
    fresh = pd.concat([fresh, pd.Series([777.0], index=[pd.Timestamp(SESSION)])])
    out = store.run({"AAA": fresh}, closes={"AAA": 111.0})
    assert out["close_meta"]["close_source"] == {"store": 1, "massive": 0}
    assert out["price_through"]["AAA"] == SESSION
    if signal_gate.is_buyable(out["verdicts"]["AAA"]):
        assert out["display_by"]["AAA"]["price"] == pytest.approx(777.0)
    # `close_finalized` is a claim about the WHOLE board, so a board with no fill
    # at all is final on the store's own settled bars.
    assert out["close_meta"]["close_finalized"] is True


def test_a_corp_action_name_is_darked_never_spliced(store):
    """The basis law's exception, counted rather than hidden. BYND split 30:1 on
    2026-08-14; its raw close that day is off its own pre-split history by the
    factor itself, and the nightly settles it hours later."""
    out = store.run({"BYND": series(name="BYND"), "AAA": series(5, name="AAA")},
                    closes={"BYND": 1.5, "AAA": 222.0}, corp=["BYND"])
    assert "BYND" not in out["verdicts"] and "AAA" in out["verdicts"]
    assert out["skipped"]["corp_action_today"] == 1
    assert out["skipped"].get("no_todays_bar") is None
    assert out["close_meta"]["close_source"] == {"store": 0, "massive": 1}


def test_the_darked_counter_counts_refusals_not_names_nobody_priced(store):
    """`corp_action_today` means "the guard darked N names". A name with a corp
    action AND no vendor close was never spliceable in the first place, so it is
    an ordinary `no_todays_bar` — counting it twice would inflate the guard's
    apparent bite and hide the coverage hole underneath it."""
    out = store.run({"BYND": series(name="BYND")}, closes={}, corp=["BYND"],
                    reason="grouped and snapshot both returned no rows")
    assert out["skipped"] == {"no_todays_bar": 1}
    assert "corp_action_today" not in out["skipped"]


@pytest.mark.parametrize("complete,reason", [
    (False, "a corp-action page failed or the page cap was hit"),
    (False, None),
])
def test_a_guard_that_is_down_stops_every_append_that_pass(store, complete, reason):
    """FAIL CLOSED, and for the WHOLE pass rather than per name. An incomplete
    corp-action read cannot tell "nobody split today" from "we did not get to
    look", and splicing on the second would put a split-day price on a pre-split
    history. The board degrades to store-only and says so."""
    out = store.run({"AAA": series(name="AAA"), "BBB": series(5, name="BBB")},
                    closes={"AAA": 111.0, "BBB": 222.0},
                    complete=complete, corp_reason=reason)
    assert out["verdicts"] == {}
    assert out["skipped"]["no_todays_bar"] == 2
    assert out["close_meta"]["close_source"] == {"store": 0, "massive": 0}
    assert out["close_meta"]["close_degraded"]


def test_a_provider_timeout_leaves_a_store_only_board_and_a_warning(store, capsys):
    """The lane still publishes. What it must not do is publish quietly: an
    operator reading the run log learns the board's coverage is whatever the store
    had, and the annotation starts the line so GitHub actually shows it."""
    out = store.run({"AAA": series(name="AAA")}, closes={},
                    reason="fetch failed (TimeoutError)")
    assert out["verdicts"] == {} and out["skipped"]["no_todays_bar"] == 1
    assert out["close_meta"]["close_degraded"] == "fetch failed (TimeoutError)"
    assert out["close_meta"]["close_source"] == {"store": 0, "massive": 0}
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=close-pass::")
    assert "TimeoutError" in warn[0]


@pytest.mark.parametrize("covered,total", [(90, 100), (50, 100), (0, 100)])
def test_partial_vendor_coverage_degrades_with_honest_counts(store, covered, total):
    """10% / 50% / 100% coverage loss. The failure direction is always the same:
    names without a close leave the evaluated set and are COUNTED, so the board
    is smaller and says so. Nothing is ever carried forward at yesterday's price
    to make the count look better."""
    spec = {f"T{i:03d}": series(i, name=f"T{i:03d}") for i in range(total)}
    closes = {t: 100.0 + i for i, t in enumerate(sorted(spec)) if i < covered}
    out = store.run(spec, closes=closes,
                    reason=None if covered else "vendor returned no rows")
    assert len(out["verdicts"]) == covered
    assert out["skipped"].get("no_todays_bar", 0) == total - covered
    assert out["close_meta"]["close_source"] == {"store": 0, "massive": covered}
    assert out["universe_n"] == total


def test_a_snapshot_fill_is_published_as_not_final(store):
    """The early-minutes case reaches the payload as what it is. A snapshot read
    at 16:01 ET is the best answer available AT THAT MOMENT and may still be
    revised; a consumer that cannot tell it from a settled aggregate would grade
    a revision as a disagreement."""
    out = store.run({"AAA": series(name="AAA")}, closes={"AAA": 111.0},
                    source=MC.SOURCE_SNAPSHOT, finalized=False)
    assert out["close_meta"]["close_finalized"] is False
    assert out["close_meta"]["close_fill_source"] == MC.SOURCE_SNAPSHOT


def test_the_fill_is_process_local_and_never_reaches_the_store(store, tmp_path):
    """G0.2. The append builds a NEW series; the frame the universe handed over is
    the store's own object and comes back unchanged, so a second reader in the
    same process sees the store rather than this pass's opinion of it."""
    original = series(name="AAA")
    before = (len(original), float(original.iloc[-1]), original.index[-1])
    out = store.run({"AAA": original}, closes={"AAA": 111.0})
    assert (len(original), float(original.iloc[-1]), original.index[-1]) == before
    assert out["price_through"]["AAA"] == SESSION
    assert not (tmp_path / "data").exists()


def test_a_store_newer_than_the_session_is_never_back_filled(store):
    """Only ever forward. A replay of an OLD session against a current store must
    not append a row BEHIND the tip — that builds a non-monotone index the gate
    reads positionally, which is a wrong answer rather than a missing one."""
    ahead = series(name="AAA", end="2026-08-20")
    out = store.run({"AAA": ahead}, closes={"AAA": 111.0})
    assert out["verdicts"] == {} and out["skipped"]["no_todays_bar"] == 1
    assert out["close_meta"]["close_source"] == {"store": 0, "massive": 0}


def test_the_appended_bar_lands_on_the_session_date_and_keeps_the_index_type():
    """The splice itself, at the seam. A naive stamp concatenated onto a tz-aware
    index yields an object-dtype index, and every downstream `.date()` then works
    on the wrong type instead of raising where it can be seen."""
    for tz in (None, "America/New_York"):
        base = series(name="AAA")
        if tz:
            base.index = base.index.tz_localize(tz)
        out = P._with_session_close(base, SESSION, 123.25)
        assert isinstance(out.index, pd.DatetimeIndex)
        assert (getattr(out.index, "tz", None) is None) == (tz is None)
        assert out.index[-1].date().isoformat() == SESSION
        assert float(out.iloc[-1]) == 123.25
        assert len(out) == len(base) + 1
        assert out.index.is_monotonic_increasing


# ─────────────────────────────────────────────────────────────────────────────
# CHAOS (commission §12) — the split-day mutation, proved in both directions
# ─────────────────────────────────────────────────────────────────────────────
def test_a_split_day_splice_would_flip_the_real_gates_verdict(store):
    """THE mutation test, and the reason the corp-action guard is not decoration.

    Half one: the un-split close on this history is ADMITTED by the real
    `signal_gate` — a T1 verdict. Half two: the same history with a 10:1 split-day
    close spliced onto it is NOT admitted. So a splice through the guard does not
    merely add noise, it CHANGES WHO IS ON THE BOARD.

    Seed 4 was found by scanning seeds for exactly this pair (buyable un-split,
    not buyable at ×10). If a gate re-tune ever breaks it, re-scan rather than
    weaken the assertion — a mutation test that cannot fail proves nothing.
    """
    base = series(name="SPLIT")
    clean = P._with_session_close(base, SESSION, float(base.iloc[-1]) * 1.005)
    split = P._with_session_close(base, SESSION, float(base.iloc[-1]) * 10.0)

    clean_v = signal_gate.gate("SPLIT", clean)
    split_v = signal_gate.gate("SPLIT", split)
    assert signal_gate.is_buyable(clean_v) is True, "fixture no longer admits"
    assert signal_gate.is_buyable(split_v) is False
    assert clean_v.get("tier_cascade") != split_v.get("tier_cascade")

    # ── the guard, on the real lane ──────────────────────────────────────────
    guarded = store.run({"SPLIT": base}, closes={"SPLIT": float(base.iloc[-1]) * 10.0},
                        corp=["SPLIT"])
    assert "SPLIT" not in guarded["verdicts"]
    assert guarded["skipped"]["corp_action_today"] == 1

    # ── the same pass with the guard DELIBERATELY BROKEN ─────────────────────
    # This is the half that proves the guard is load-bearing: told the day was
    # quiet, the lane splices, the gate scores the fabricated 10× gap, and the
    # name lands on the board with a verdict built from a price that never
    # happened. The guard is the only thing standing between those two runs.
    unguarded = store.run({"SPLIT": base},
                          closes={"SPLIT": float(base.iloc[-1]) * 10.0}, corp=[])
    assert "SPLIT" in unguarded["verdicts"]
    assert unguarded["verdicts"]["SPLIT"] == split_v != clean_v
    assert unguarded["skipped"].get("corp_action_today") is None


def test_a_reverse_split_is_darked_on_the_same_rule(store):
    """BYND's 2026-08-14 action was a 1:30 REVERSE split — the price goes UP by
    the factor, not down. Direction is irrelevant to the rule: the history is
    re-based either way, so the name is darked either way."""
    base = series(name="BYND")
    out = store.run({"BYND": base}, closes={"BYND": float(base.iloc[-1]) * 30.0},
                    corp=["BYND"])
    assert "BYND" not in out["verdicts"]
    assert out["skipped"]["corp_action_today"] == 1
