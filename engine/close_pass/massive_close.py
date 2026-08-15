"""engine.close_pass.massive_close — same-day close truth for the evening pass.

THE DEFECT THIS CLOSES, MEASURED. The Friday 2026-08-14 close pass published
``22 admitted of 253 evaluated (universe 1763); skipped {'no_todays_bar': 1508}``
— 86% of the universe carried no today-bar at pass time, so the evening board was
a read of ~14% of the market rather than of the market. The lane's own prefetch
(``scripts.check_price_store_freshness --heal``) is KEYLESS and refreshes the
index group; the deep per-name stores are the nightly's job and at 16:25 ET they
still end at yesterday. Skipping those names was the RIGHT call on the data the
pass had — a mixed-vintage board is the defect W-L0 gate 3 exists to stop — so
this module changes the DATA, never the rule.

WHAT IT FETCHES, AND WHY IN THAT ORDER
  1. grouped daily ``/v2/aggs/grouped/locale/us/market/stocks/{session}``
     with ``adjusted=false`` — ONE request for the WHOLE market (12,424 tickers
     measured for 2026-08-14) carrying the session's finalized daily bar. The
     preferred source, and the only one stamped ``finalized``.
  2. full-market snapshot ``/v2/snapshot/locale/us/markets/stocks/tickers`` — the
     fallback for the minutes after the close, before the day's grouped aggregate
     exists. Its ``day`` object holds the session's completed bar and freezes AT
     the regular-hours close: measured 2026-08-15, AAPL ``updated`` =
     1786752000000000000 ns = 2026-08-14T20:00:00.000Z = 16:00:00 ET and
     ``day.c`` = 305.93, equal to the grouped close TO THE CENT — the evening's
     after-hours prints did not move it. It is NOT ``finalized``: a snapshot read
     at 16:01 ET can still be revised.

``lastTrade`` IS NEVER A CLOSE HERE. It is the last print of ANY session
including after-hours, so on a news evening it is a different number from the
close every other surface in this estate quotes. ``day.c`` or nothing.

THE SNAPSHOT'S SESSION IS VERIFIED, NOT ASSUMED — the load-bearing half. A
snapshot read at 16:01 ET on a MONDAY still carries FRIDAY's ``day`` object for
any name that has not printed a Monday bar, and splicing that onto a Monday board
would carry a three-day-old close under today's date: the same mixed-vintage
defect the ``no_todays_bar`` skip exists to prevent, only silent. So every row's
ET session date is derived from its OWN ``updated`` stamp and a row whose session
is not the expected one is EXCLUDED. Grouped daily needs no such check — its
session is in the URL.

PRICE BASIS (W-L0 gate 3 — name the adjustment at every seam). Both endpoints are
read unadjusted (``adjusted=false`` on grouped; a snapshot ``day`` bar is a raw
vendor print by construction) and both are the REGULAR-HOURS close. That pair is
narrower than :data:`engine.prophet_live.interval.UNADJUSTED` — it also names the
session rung — so it carries its own constant, :data:`BASIS`, and declares the
family it belongs to in :data:`BASIS_FAMILY` rather than minting a rival
vocabulary.

CORPORATE ACTIONS ARE A GUARD, NOT A FEATURE. :func:`corp_action_tickers` names
the tickers whose split or ex-dividend date IS the session, because those are
exactly the names on which "today's raw close equals today's adjusted close" stops
being true. It reports ``complete`` and the caller is required to treat
incomplete as GUARD DOWN — see ``scripts.close_pass_publish.collect``.

TWO RECORDS GOVERN THE VENDOR CONTRACT, both in the knowledge plane rather than
only here: ``DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE`` (which RUNG to read, and why
the snapshot needs a session check) and ``DSC:MASSIVE-TICKER-CASE-IS-IDENTITY``
(WHICH SECURITY a row belongs to — see :func:`universe_ticker`). A splice needs
both answered; either one alone gets a plausible wrong number.

NO ``data/`` PATH, NO GIT, NO RAISE. Every public function returns an explicit
result object and degrades rather than throwing: this feeds a lane whose whole
purpose is to land inside a 30-minute window, so a vendor hiccup must cost
coverage and never the pass. Heavy imports are function-scoped and there is no
pandas anywhere in here — the module has to import on a ``--help`` path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from engine.prophet_live.interval import UNADJUSTED

#: Massive is the Polygon rebrand; the REST base is unchanged and is already
#: declared once in ``config.yml`` (``polygon.base_url``). Read from there at call
#: time, with this as the fallback, so there is one base URL in the estate.
DEFAULT_BASE_URL = "https://api.polygon.io"
#: The key env this lane's workflow step sets. ``POLYGON_API_KEY`` is accepted as
#: a fallback because it is the SAME account and the same key in this estate
#: (``scripts.build_polygon_universe`` already reads the pair) — it makes a local
#: parity run work off the host ``.env`` without a second secret. It cannot mask a
#: missing CI secret: close-pass.yml passes neither name unless it is set.
KEY_ENVS = ("MASSIVE_API_KEY", "POLYGON_API_KEY")

#: The price basis of every number this module returns. Narrower than the family
#: below on purpose: it names BOTH the adjustment (raw) and the session rung (the
#: regular-hours close, never an after-hours print).
BASIS = "raw_rth_close"
#: The estate-wide family :data:`BASIS` belongs to, imported rather than restated
#: — three names for one fact is how two surfaces end up disagreeing about what
#: "adjusted" meant (``engine.prophet_live.interval``'s own words).
BASIS_FAMILY = UNADJUSTED

SOURCE_GROUPED = "massive_grouped"
SOURCE_SNAPSHOT = "massive_snapshot"

GROUPED_PATH = "/v2/aggs/grouped/locale/us/market/stocks/{session}"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
SPLITS_PATH = "/v3/reference/splits"
DIVIDENDS_PATH = "/v3/reference/dividends"

#: Vendor page size. Measured 2026-08-15: 450 dividend rows for 2026-08-14 came
#: back in ONE page at this limit with no ``next_url``, and 3 split rows. The
#: pagination loop below is therefore expected to be a no-op — it exists for the
#: heavy ex-date (the quarterly cluster), not for the ordinary day.
PAGE_LIMIT = 1000
#: A HARD page cap, and hitting it sets ``complete = False`` rather than silently
#: returning a short list. An under-reported corp-action set is worse than none:
#: it reads as "no action today" on exactly the names that had one.
MAX_PAGES = 8

#: Bounded, and deliberately not generous. The pass has ~30 minutes of an 18:30 ET
#: SLA and one grouped request returns the whole market — a fetch that needs more
#: than this is a fetch that has already failed.
TIMEOUT_S = 30.0
#: One try plus two retries, on transport error and 5xx only. Never on a 4xx: a
#: 403/404 is an answer, and re-asking it is the retry storm this cap exists to
#: prevent.
ATTEMPTS = 3

_ET = ZoneInfo("America/New_York")
_UA = "macro-dashboard close-pass/massive_close"

#: Sanity band for a nanosecond epoch stamp (2001-09-09 .. 2096-10-02). A vendor
#: field that silently arrives in MILLIseconds would otherwise resolve to 1970 and
#: be refused as "wrong session" for the right reason by accident; this refuses it
#: for the right reason on purpose, and a stamp we cannot read is a row we do not
#: trust.
_NS_MIN = 1_000_000_000_000_000_000
_NS_MAX = 4_000_000_000_000_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Results — explicit objects, because a caller that has to guess degrades wrong
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SessionCloses:
    """One session's closes, keyed by UNIVERSE-form ticker, plus its provenance.

    ``finalized`` is the difference that matters downstream: a grouped daily bar
    is the session's settled aggregate, while a snapshot read minutes after the
    close is the best answer available AT THAT MOMENT and may still be revised.
    Both are usable; only one of them is final, and the payload says which.
    """

    session: str
    closes: Mapping[str, float] = field(default_factory=dict)
    source: str | None = None
    basis: str = BASIS
    observed_at: str = ""
    finalized: bool = False
    #: Vendor rows the endpoint returned, before any filtering — the denominator
    #: that turns "we matched 1,700" into a statement about coverage.
    vendor_rows: int = 0
    wanted_n: int = 0
    matched_n: int = 0
    #: Why there are no closes. None when there are.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.closes)


@dataclass(frozen=True)
class CorpActions:
    """Tickers whose split or ex-dividend date IS ``session``.

    ``complete`` is the caller's licence to splice AT ALL. False means the guard
    is DOWN — a page cap was hit or a fetch failed — and a caller that splices
    anyway is asserting "no name had an action today" on evidence it does not
    have. Fail closed: no appends that pass, disclosed.
    """

    session: str
    tickers: frozenset[str] = frozenset()
    splits_n: int = 0
    dividends_n: int = 0
    complete: bool = False
    reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Small pure helpers
# ─────────────────────────────────────────────────────────────────────────────
def universe_ticker(vendor: str) -> str:
    """Vendor ticker → universe form. Folds the DOT convention and NOTHING else.

    The vendor writes class shares with a DOT (``BRK.B``); this repo's universe
    writes them with a HYPHEN, because ``build_stock_library`` normalises every
    holdings name through ``.replace(".", "-")``. Two spellings of one company is
    how a 12,424-row market read matches 1,600 names instead of 1,700.

    CASE IS IDENTITY, NOT FORMATTING — measured 2026-08-15, and this function
    used to get it wrong. The vendor's ticker space is case-SENSITIVE: a
    lowercase letter marks a different security on the same root. Grouped daily
    for 2026-08-13 carried BOTH ``TPC`` (Tutor Perini, common, c=94.67) and
    ``TpC`` (c=16.98), and BOTH ``BCPC`` (Balchem, common, c=177.14) and ``BCpC``
    (Brunswick 6.375% Notes due 2049, c=23.9999). Upper-casing the vendor side
    collapses each pair onto one universe name and the LAST row in the payload
    wins — so TPC came back at 16.98 (a 5.6× mis-price, caught by the parity
    battery) while Balchem survived on payload order alone. 389 of 12,500 rows
    that day were mixed-case; exactly 2 collided with this universe, and one of
    the two was already wrong. A price that is wrong by luck of ordering is the
    worst kind: it is right in the test and wrong in production, or the reverse,
    with nothing in the code to say which.
    """
    return str(vendor or "").strip().replace(".", "-")


def _finite_positive(value: Any) -> float | None:
    """A usable close, or None. Rejects bools, NaN, inf, 0, negatives, garbage.

    ``0`` is a REFUSAL, not a price: the vendor returns a zero close for a row
    that did not trade, and a $0.00 board card is worse than an absent one.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")) or out <= 0:
        return None
    return out


def et_session_of(ns_stamp: Any) -> str | None:
    """A nanosecond epoch stamp → its ET calendar date, or None if unreadable.

    This is the whole snapshot session check. A stamp outside the sanity band is
    None rather than an epoch-1970 date, so the caller refuses the row instead of
    comparing a garbage date against the session and getting the right answer for
    the wrong reason.
    """
    if isinstance(ns_stamp, bool) or ns_stamp is None:
        return None
    try:
        ns = int(ns_stamp)
    except (TypeError, ValueError):
        return None
    if not (_NS_MIN <= ns <= _NS_MAX):
        return None
    stamp = datetime.fromtimestamp(ns // 1_000_000_000, tz=timezone.utc)
    return stamp.astimezone(_ET).date().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


def _base_url() -> str:
    try:
        from lib import config  # noqa: PLC0415 — config read belongs to the call
        cfg = (config.load() or {}).get("polygon") or {}
        return str(cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    except Exception:  # noqa: BLE001 — a missing config is not a reason to fail
        return DEFAULT_BASE_URL


def api_key() -> str | None:
    """The key, read AT CALL TIME. Never logged, never returned in a reason.

    Call time rather than import time so a test can set the env after import and
    so a workflow step's ``env:`` block is what decides, not the process that
    imported the module.
    """
    for name in KEY_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The network seam — ONE function, injectable, never raising
# ─────────────────────────────────────────────────────────────────────────────
def _default_fetch(key: str) -> Callable[[str, Mapping[str, Any] | None], Any]:
    """Build the real fetcher. ``fetch(path_or_url, params) -> payload | None``.

    None means "no answer" — transport error, 5xx after the retry budget, or a
    body that would not parse. A caller cannot tell those apart and must not: all
    three mean the same thing to a lane that has to publish either way.

    THE KEY RIDES A HEADER, never a query string, so no URL this module builds —
    and no exception text requests embeds a URL into — can carry the secret.
    """
    import requests  # noqa: PLC0415 — light, but still not an import-time cost

    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": _UA,
                            "Authorization": f"Bearer {key}"})
    base = _base_url()

    def fetch(path_or_url: str, params: Mapping[str, Any] | None = None) -> Any:
        url = (path_or_url if path_or_url.startswith("http")
               else base + path_or_url)
        for attempt in range(ATTEMPTS):
            try:
                resp = session.get(url, params=dict(params or {}) or None,
                                   timeout=TIMEOUT_S)
            except Exception:  # noqa: BLE001 — transport; retry, then give up
                if attempt + 1 < ATTEMPTS:
                    continue
                return None
            status = int(getattr(resp, "status_code", 0) or 0)
            # 4xx is an ANSWER (403 not entitled, 404 no such day). Re-asking it
            # is the retry storm the budget exists to prevent.
            if 500 <= status < 600 and attempt + 1 < ATTEMPTS:
                continue
            if status >= 400:
                return None
            try:
                return resp.json()
            except Exception:  # noqa: BLE001
                return None
        return None

    return fetch


def _refused(payload: Any) -> bool:
    """True when the vendor said NO in the BODY of a 200.

    Polygon answers some paths with ``{"status": "NOT_AUTHORIZED"}`` and an HTTP
    200, so refusal is honoured here rather than trusted to the status code
    alone. Load-bearing for the corp-action guard: a refusal that parsed as "no
    rows" would read as "no name had an action today" and open the splice on
    exactly the names it exists to close.
    """
    return (isinstance(payload, Mapping)
            and str(payload.get("status") or "").upper() in ("NOT_AUTHORIZED",
                                                             "ERROR"))


def _rows(payload: Any) -> list[dict]:
    """The result rows of any of these endpoints, or [] — never a raise."""
    if not isinstance(payload, Mapping) or _refused(payload):
        return []
    for key in ("results", "tickers"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, Mapping)]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Closes
# ─────────────────────────────────────────────────────────────────────────────
def _match(rows: Iterable[Mapping[str, Any]], wanted: set[str],
           ticker_key: str, close_of: Callable[[Mapping[str, Any]], float | None],
           ) -> tuple[dict[str, float], int]:
    """Vendor rows → ``{universe ticker: close}``, EXACT matches winning.

    Two passes on purpose. ``universe_ticker`` folds ``.`` to ``-``, and the
    vendor's own tape carries hyphenated symbols too, so a single translated pass
    lets ``BRK.B`` overwrite a genuine ``BRK-B`` row (or the reverse, depending on
    iteration order) — a silent, order-dependent mis-price on a class share. An
    exact vendor==universe match is unambiguous, so it is taken first and the
    translated pass only FILLS names still missing.

    Comparison is CASE-EXACT on both sides. See ``universe_ticker``: the vendor
    uses case to distinguish securities (``TpC`` is not ``TPC``), so normalising
    it away is not tidying, it is a mis-identification.
    """
    exact: dict[str, float] = {}
    translated: dict[str, float] = {}
    seen = 0
    for row in rows:
        seen += 1
        raw = str(row.get(ticker_key) or "").strip()
        if not raw:
            continue
        folded = universe_ticker(raw)
        hit_exact = raw in wanted
        hit_folded = folded != raw and folded in wanted
        if not (hit_exact or hit_folded):
            continue
        # ONCE per row, never once per spelling: `close_of` counts its own
        # refusals (the snapshot's stale-session tally), and calling it twice for
        # one row would report a market twice as stale as it is.
        close = close_of(row)
        if close is None:
            continue
        if hit_exact:
            exact[raw] = close
        if hit_folded and folded not in translated:
            translated[folded] = close
    out = dict(translated)
    out.update(exact)              # exact wins wherever both exist
    return out, seen


def _grouped_close(row: Mapping[str, Any]) -> float | None:
    return _finite_positive(row.get("c"))


def fetch_session_closes(session: str, wanted: Iterable[str], *,
                         fetch: Callable[..., Any] | None = None) -> SessionCloses:
    """``session`` + the tickers we care about → that session's closes.

    Grouped daily first (finalized, one request, whole market); the full-market
    snapshot ONLY if grouped came back empty or unavailable, which is the state
    of the world for the first minutes after the close.

    ``fetch`` is injectable and resolves at CALL time — a default bound at def
    time would make the network boundary unpatchable and every test would
    silently exercise the real API. Never raises; an unusable world comes back as
    an empty result carrying its ``reason``.
    """
    # Stripped, never re-cased. Normalising OUR side would be symmetric with
    # normalising the vendor's, and the vendor's case carries identity — a
    # universe name folded up to meet a vendor row is the same mis-match from
    # the other direction.
    wanted_set = {str(t).strip() for t in wanted if str(t).strip()}
    stamp = _now_iso()

    def degraded(reason: str, **over: Any) -> SessionCloses:
        return SessionCloses(session=session, observed_at=stamp,
                             wanted_n=len(wanted_set), reason=reason, **over)

    if not wanted_set:
        return degraded("no tickers requested")

    if fetch is None:
        key = api_key()
        if not key:
            # The lane must still publish. Naming the ENV VAR (never a value) is
            # what turns this into an operator-actionable line in the run log.
            return degraded(f"no API key ({'/'.join(KEY_ENVS)} unset)")
        try:
            fetch = _default_fetch(key)
        except Exception as exc:  # noqa: BLE001 — e.g. requests absent
            return degraded(f"http client unavailable ({type(exc).__name__})")

    try:
        payload = fetch(GROUPED_PATH.format(session=session),
                        {"adjusted": "false", "include_otc": "false"})
        rows = _rows(payload)
        if rows:
            closes, seen = _match(rows, wanted_set, "T", _grouped_close)
            if closes:
                return SessionCloses(
                    session=session, closes=closes, source=SOURCE_GROUPED,
                    observed_at=stamp, finalized=True, vendor_rows=seen,
                    wanted_n=len(wanted_set), matched_n=len(closes))

        # ── snapshot fallback ────────────────────────────────────────────────
        # Reached in the minutes after the close, before the day's grouped
        # aggregate exists. Every row must PROVE it belongs to this session.
        payload = fetch(SNAPSHOT_PATH, None)
        snap = _rows(payload)
        if not snap:
            return degraded("grouped and snapshot both returned no rows")

        stale = 0

        def snapshot_close(row: Mapping[str, Any]) -> float | None:
            nonlocal stale
            # `lastTrade` is deliberately unreachable from here: it is the last
            # print of ANY session, so on a news evening it is a different number
            # from the close the rest of the estate quotes.
            if et_session_of(row.get("updated")) != session:
                stale += 1
                return None
            return _finite_positive((row.get("day") or {}).get("c"))

        closes, seen = _match(snap, wanted_set, "ticker", snapshot_close)
        if not closes:
            return degraded(
                f"snapshot carried no {session} row for any wanted ticker "
                f"({stale} row(s) belonged to another session)")
        return SessionCloses(
            session=session, closes=closes, source=SOURCE_SNAPSHOT,
            observed_at=stamp, finalized=False, vendor_rows=seen,
            wanted_n=len(wanted_set), matched_n=len(closes))
    except Exception as exc:  # noqa: BLE001 — the contract is "never raises"
        return degraded(f"fetch failed ({type(exc).__name__})")


# ─────────────────────────────────────────────────────────────────────────────
# Corporate actions — the splice guard
# ─────────────────────────────────────────────────────────────────────────────
def _paged(fetch: Callable[..., Any], path: str,
           params: Mapping[str, Any]) -> tuple[list[dict], bool]:
    """Walk ``next_url`` up to :data:`MAX_PAGES`. ``(rows, complete)``.

    ``complete`` is False when a page failed OR the cap was hit with a
    ``next_url`` still outstanding — the two ways this can under-report, both of
    which must reach the caller as "guard down" rather than as a short list.
    """
    rows: list[dict] = []
    url: str | None = path
    query: Mapping[str, Any] | None = params
    for _ in range(MAX_PAGES):
        payload = fetch(url, query)
        # THREE ways to be incomplete, and an empty list is NOT one of them: a
        # quiet day genuinely has no split. What is not allowed is inferring
        # "quiet day" from a refusal (200 + NOT_AUTHORIZED) or from a body with
        # no `results` list at all — both of which parse to zero rows and would
        # read as "no name had an action today".
        if not isinstance(payload, Mapping) or _refused(payload):
            return rows, False
        results = payload.get("results")
        if not isinstance(results, list):
            return rows, False
        page = _rows(payload)
        # A row we could not READ is a row we could not rule out. If the page
        # carried entries this parser dropped, the vendor is speaking a shape we
        # do not understand and "no action on that name" is a guess.
        if len(page) != len(results):
            return rows + page, False
        rows.extend(page)
        nxt = payload.get("next_url")
        if not nxt:
            return rows, True
        # A `next_url` already carries the cursor; re-sending the original query
        # alongside it is how a paginator silently restarts at page one.
        url, query = str(nxt), None
    return rows, False


def corp_action_tickers(session: str, *,
                        fetch: Callable[..., Any] | None = None) -> CorpActions:
    """Tickers with a split executing, or an ex-dividend date, ON ``session``.

    These are exactly the names for which "today's raw close equals today's
    adjusted close" is FALSE, so they are the names a raw close may not be
    spliced onto an adjusted history. Measured 2026-08-14: 3 splits (IDTIF 200:1,
    HAO 20:1, BYND 1:30 reverse) and 450 ex-dividends.

    Never raises. ``complete=False`` is a GUARD-DOWN report and the caller is
    required to stop splicing entirely on it — see the ruling in
    ``scripts.close_pass_publish.collect``.
    """
    if fetch is None:
        key = api_key()
        if not key:
            return CorpActions(session=session,
                               reason=f"no API key ({'/'.join(KEY_ENVS)} unset)")
        try:
            fetch = _default_fetch(key)
        except Exception as exc:  # noqa: BLE001
            return CorpActions(session=session,
                               reason=f"http client unavailable ({type(exc).__name__})")

    try:
        splits, ok_s = _paged(fetch, SPLITS_PATH,
                              {"execution_date": session, "limit": PAGE_LIMIT})
        divs, ok_d = _paged(fetch, DIVIDENDS_PATH,
                            {"ex_dividend_date": session, "limit": PAGE_LIMIT})
    except Exception as exc:  # noqa: BLE001 — the contract is "never raises"
        return CorpActions(session=session,
                           reason=f"fetch failed ({type(exc).__name__})")

    # THE GUARD'S ASYMMETRY, stated where it is taken. The closes matcher is
    # case-EXACT because a mis-identified price is a wrong number on a board; the
    # guard adds the upper-cased spelling TOO, because its failure directions are
    # not symmetric — over-darking costs one name's coverage for one night, while
    # under-darking splices a split-day price onto a pre-split history. Measured
    # 2026-08-13 and 2026-08-14: ZERO corp-action rows were mixed-case and
    # upper-cased into this universe, so the extra spelling costs nothing today
    # and buys the closed direction if the vendor's convention ever moves.
    names: set[str] = set()
    for row in list(splits) + list(divs):
        ticker = universe_ticker(row.get("ticker") or "")
        if ticker:
            names.add(ticker)
            names.add(ticker.upper())
    complete = bool(ok_s and ok_d)
    return CorpActions(
        session=session, tickers=frozenset(names), splits_n=len(splits),
        dividends_n=len(divs), complete=complete,
        reason=None if complete else "a corp-action page failed or the page cap "
                                     "was hit — treat as guard down")
