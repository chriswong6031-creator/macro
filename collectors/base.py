"""Adapter layer. Every external source implements Adapter; the runner wraps
fetch() with retry/backoff and a circuit breaker so one broken scraper can
never kill the run — it logs the gap, marks the source stale, and moves on.
"""
from __future__ import annotations

import logging
import re
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd
import requests

from lib import config, store

log = logging.getLogger(__name__)

CIRCUIT_BREAKER_FAILS = 3  # consecutive run failures -> mark dead, skip

# Preventive hardening: redact secrets from retried-request log lines AND from
# FetchResult.error (which is serialized into the TRACKED data/run_status.json —
# see run_adapter below). `requests`' default HTTPError/ConnectionError text
# embeds the FULL request URL — query string and all — via `raise_for_status()`
# and friends, so a bare `str(exc)` interpolation carries any credential value
# straight into a log line or a committed file, even one that otherwise takes
# care to log a query-stripped URL separately.
#
# Widened per the AD-1C0 adversarial review (2026-08-19) — the enumerated leak
# shapes a single "name=value" regex missed: a quoted JSON body value
# ("apiKey":"…"), an `Authorization: Bearer …` header repr, a URL-encoded
# assignment (name%3Dvalue), a bare "name value" mention with no `=` at all, and
# a vendor secret embedded as a URL PATH SEGMENT with no adjacent keyword at all
# (Stripe-style sk_live_…/pk_test_… prefixes). Several passes, most specific
# first; each is independently idempotent so their order does not matter for
# correctness, only for keeping the output readable.
_CRED_PARAM_NAMES = r'(?:api[_-]?key|apikey|access[_-]?key|token|secret|password|key)'

# "apiKey": "value" (JSON body, any of the credential names, case-insensitive).
_CRED_JSON_RE = re.compile(rf'(?i)("(?:{_CRED_PARAM_NAMES})"\s*:\s*)"[^"]*"')
# Authorization: Bearer <token>
_BEARER_RE = re.compile(r'(?i)\b(Bearer\s+)\S+')
# name=value / name%3Dvalue (url-encoded '=') — query string or bare mention.
# Deliberately NO leading \b: a url-encoded '?' (%3F) immediately preceding the
# param name (e.g. "...%3FapiKey%3D...") glues the trailing 'F' of %3F straight
# onto 'apiKey' with no word-boundary between them, and that exact shape is how
# a URL-encoded assignment actually renders once its '?' is also encoded.
_CRED_ASSIGN_RE = re.compile(
    rf'(?i)({_CRED_PARAM_NAMES}\s*(?:=|%3[dD])\s*)[^\s&"\'%)}}]+')
# name value (space-separated free-text mention) — bare "key" excluded here,
# too generic a word to redact on adjacency alone outside an assignment shape.
_CRED_SPACED_RE = re.compile(
    r'(?i)\b((?:api[_-]?key|apikey|access[_-]?key|token|secret|password)\s+)'
    r'[^\s&"\')}]+')
# Common vendor secret-token prefixes that leak with NO adjacent keyword at all
# (e.g. a URL path segment like /api/v1/sk_live_XXXX/chain).
_TOKEN_PREFIX_RE = re.compile(r'(?i)\b(?:sk|pk)_[A-Za-z0-9_]{4,}')
# Whatever is left of a URL query string after the above — final catch-all.
_QUERY_TAIL_RE = re.compile(r'\?[^\s"\')]+')


def redact_secrets(text: str) -> str:
    """Strip secrets from an arbitrary string (an exception's str(), a formatted
    traceback, ...). safe_exc_text() is the exception-typed convenience wrapper;
    this is the reusable text-level primitive (M5: also applied to FetchResult.
    error and its traceback, which land in the TRACKED data/run_status.json)."""
    text = _CRED_JSON_RE.sub(lambda m: f'{m.group(1)}"REDACTED"', text)
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)}REDACTED", text)
    text = _CRED_ASSIGN_RE.sub(lambda m: f"{m.group(1)}REDACTED", text)
    text = _CRED_SPACED_RE.sub(lambda m: f"{m.group(1)}REDACTED", text)
    text = _TOKEN_PREFIX_RE.sub("REDACTED", text)
    text = _QUERY_TAIL_RE.sub("?REDACTED", text)
    return text


def safe_exc_text(exc: BaseException) -> str:
    """Render `exc` for logging (or for a tracked-file field) with secrets
    stripped — never surface a raw exception that may have travelled through a
    keyed vendor URL, header, or JSON body."""
    return redact_secrets(str(exc))

# An open breaker is HALF-OPEN, not permanently dead: after this long it lets ONE
# probe through. A success closes it; a failure re-opens it for another window.
# Without this an open breaker NEVER retries — the daily/weekly collect never pass
# --full-history (the only flag that bypassed it), so a single transient trip
# became a permanent SILENT death (a healthy source stuck "dead" for weeks).
CIRCUIT_HALF_OPEN_AFTER_H = 20.0   # ~one probe per daily run


@dataclass
class FetchResult:
    source: str
    status: str            # ok | stale | failed | dead | skipped | blocked
    rows: int = 0
    last_date: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    probed_at: str | None = None   # set when this run was a half-open breaker probe


@dataclass(frozen=True)
class ColumnContract:
    """What a single stored COLUMN owes, so a dead column cannot hide inside a
    live frame.

    ``detect_stale_series`` is frame-grain: it asks when the frame last had ANY
    observation.  A multi-column series therefore stays "fresh" forever as long
    as one column keeps ticking — which is exactly how china_connect/northbound
    hid the death of ``net``/``buy``/``sell`` for ~2 years behind a still-live
    ``turnover``.  A column contract makes each column answer for itself.

    Exactly one mode must be set:

    ``max_dark_days``
        The column is LIVE and owed on a cadence.  Warn when its last non-null
        observation is older than this many days (set it to a few cadences so
        holidays and a late post do not cry wolf).
    ``retired``
        ISO date on which upstream disclosure ENDED.  The column is EXPECTED to
        be all-null afterwards, so that steady state is SILENT — a retired
        column must never warn nightly forever.  The only event worth surfacing
        is the opposite one: a non-null value after the retirement date, meaning
        upstream may have resumed and a human should adjudicate un-retiring it.

    ``note`` is appended to the annotation, so the alarm text says what to do
    rather than only what broke.
    """

    max_dark_days: int | None = None
    retired: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if (self.max_dark_days is None) == (self.retired is None):
            raise ValueError(
                "ColumnContract needs exactly one of max_dark_days= (live column) "
                f"or retired= (upstream disclosure ended); got max_dark_days="
                f"{self.max_dark_days!r}, retired={self.retired!r}"
            )


class Adapter:
    """Subclass per source. fetch() returns the canonical DataFrame(s) and is
    allowed to raise — the runner handles failure."""

    name: str = "base"
    group: str = "misc"
    stale_after_days: int = 5   # weekly/lagged sources override (COT: 12, H4.1: 10)
    expected_failure: str | None = None  # set to a reason string when a source is
    # known-broken (e.g. bot-blocked); failures then report status 'blocked'
    overwrite_overlap: bool = False  # True for dividend/split-ADJUSTED series (yfinance
    # auto_adjust=True): the fresh pull fully overwrites its own date span so a re-adjusted
    # history leaves no combine_first basis seam. See lib.store.upsert / masterplan §W6-CN.

    # Opt-in per-COLUMN freshness contracts: {series_name: {column: ColumnContract}}.
    # Empty = no column-grain checking (every existing adapter is unaffected). See
    # ColumnContract and detect_dark_columns for why frame-grain staleness is not enough.
    column_contracts: dict[str, dict[str, ColumnContract]] = {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Return {series_name: DataFrame indexed by date}. Raise on failure."""
        raise NotImplementedError

    def validate(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Basic sanity: datetime index, numeric columns, no all-NaN."""
        if df is None or df.empty:
            raise ValueError(f"{self.name}/{name}: empty frame")
        df = df.copy()
        df.index = pd.to_datetime(df.index).normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.dropna(how="all")
        if df.empty:
            raise ValueError(f"{self.name}/{name}: all-NaN after cleaning")
        return df

    def last_good_date(self) -> date | None:
        dates = [d for d in (store.last_date(self.group, n) for n in self.stored_series()) if d]
        return max(dates) if dates else None

    def stored_series(self) -> list[str]:
        d = config.data_dir() / self.group
        if not d.exists():
            return []
        return [p.stem for p in d.glob("*.parquet")]

    def fetch_result_status(self, frames: dict[str, pd.DataFrame]) -> str | None:
        """Optionally expose a deliberate non-failure operational outcome.

        Most adapters let the runner derive ``ok``/``stale`` from their series.
        A bounded evidence lane can instead return ``blocked`` for an explicit
        operator dependency without throwing and poisoning its circuit breaker.
        """
        return None

    # -- shared HTTP helpers ---------------------------------------------------
    def http_get(self, url: str, retries: int = 3, backoff_base: float = 3.0,
                 timeout: int = 60, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent",
                           config.load()["sponsors"]["user_agent"])
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                r = requests.get(url, timeout=timeout, headers=headers, **kwargs)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001 — retried, then surfaced by runner
                last_exc = e
                wait = backoff_base * (2 ** attempt)
                log.warning("%s GET %s attempt %d/%d failed (%s); retry in %.0fs",
                            self.name, url.split("?")[0], attempt + 1, retries,
                            safe_exc_text(e), wait)
                if attempt < retries - 1:
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]


def is_connection_error(exc: Exception) -> bool:
    """True when *exc* means the HOST is unreachable (timeout / refused / DNS), as
    opposed to a data-level problem (404, empty series). Lets a multi-series
    collector fail fast on a dead endpoint instead of retrying EVERY series through
    its full timeout+backoff — a single FRED-frontend outage once turned the
    intl_macro plane into a ~56-minute no-op (34 series x 3 retries x 30s)."""
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):   # covers Connect/ReadTimeout
        return True
    s = str(exc).lower()
    return ("timed out" in s or "max retries" in s
            or "failed to establish a new connection" in s
            or "connection aborted" in s or "connection refused" in s)


def detect_stale_series(
    group: str,
    frames: dict[str, pd.DataFrame],
    cadence_days: int,
    *,
    multiplier: float = 3.0,
) -> list[dict]:
    """Frozen-tail detector: after a SUCCESSFUL 200-OK fetch, compare each series'
    stored last-observation date against the expected cadence.

    A series is "frozen" when its last observation is older than
    ``cadence_days * multiplier`` days — i.e. multiple release cycles have passed
    without any new data. This catches discontinued upstream series that return
    200-OK with stale history (the failure mode that silently killed JP/KR CPI,
    EZ unemployment, and the intl M2 group: FRED kept serving historical data with
    a frozen tail, so is_connection_error and the adapter-level stale check both
    missed it).

    Returns a list of ``{group, series, last_obs, cadence_days, age_days}`` dicts
    for every frozen tail detected; empty list if all series are live.  Non-fatal
    by design — the caller writes these to run_status["stale_series"] for the
    health surface.
    """
    today = datetime.now(timezone.utc).date()
    threshold = int(cadence_days * multiplier)
    stale: list[dict] = []
    for name, df in frames.items():
        try:
            df_clean = df.dropna(how="all")
            if df_clean.empty:
                continue
            last_obs: date = pd.Timestamp(df_clean.index.max()).date()
            age = (today - last_obs).days
            if age > threshold:
                log.warning(
                    "stale_series detected: %s/%s last_obs=%s age=%dd (threshold=%dd, "
                    "cadence=%dd×%.1f)",
                    group, name, last_obs, age, threshold, cadence_days, multiplier,
                )
                stale.append({
                    "group": group,
                    "series": name,
                    "last_obs": str(last_obs),
                    "cadence_days": cadence_days,
                    "age_days": age,
                })
        except Exception:  # noqa: BLE001 — staleness check must never crash the run
            pass
    return stale


def _write_stale_series(new_entries: list[dict]) -> None:
    """Merge new stale-series entries into run_status["stale_series"], keyed by
    group+series so repeated runs deduplicate and update the last_obs timestamp."""
    if not new_entries:
        return
    status = store.read_status()
    existing: list[dict] = status.get("stale_series", [])
    by_key = {(e["group"], e["series"]): e for e in existing}
    for entry in new_entries:
        by_key[(entry["group"], entry["series"])] = {
            **entry, "detected_at": datetime.now(timezone.utc).isoformat()
        }
    status["stale_series"] = list(by_key.values())
    store.write_status(status)


def detect_dark_columns(
    group: str,
    series: str,
    df: pd.DataFrame,
    contracts: dict[str, ColumnContract],
    today: date,
) -> list[dict]:
    """Column-grain contract check: which contracted COLUMNS have gone dark, and
    which RETIRED ones have come back to life?

    ``detect_stale_series`` cannot see either event.  It is frame-grain, so one
    live column keeps the whole frame "fresh": china_connect/northbound reported
    healthy every night for ~2 years while ``net``/``buy``/``sell`` were null,
    because ``turnover`` was still ticking daily in the same frame.

    PURE by construction — ``today`` is injected, never read from the wall clock,
    so the caller owns the clock and tests can pin it.  Pass the MERGED store
    frame, not the fetch window: the incremental fetch is a short recent slice
    and cannot answer "when did this column last have a value".

    Returns one dict per finding (empty list when everything is on contract):

    ``{"kind": "dark", group, series, column, last_obs, age_days, max_dark_days, note}``
        A live column is past its horizon.  ``last_obs``/``age_days`` are BOTH
        ``None`` when the column is missing from the frame or has no non-null
        value at all — an unbounded age, deliberately not a magic number that a
        consumer could average or sort as if it were a real age.
    ``{"kind": "resurrected", group, series, column, retired, last_obs, note}``
        A retired column has a non-null value AFTER its retirement date.

    A retired column that is simply all-null after retirement produces NOTHING —
    that is the expected steady state, and an alarm that fires every night for a
    permanent, known condition is an alarm nobody reads.

    Per-column try/except (mirroring detect_stale_series): a weird dtype or a
    non-datetime index can never crash the run.  This is an alarm, not a gate.
    """
    found: list[dict] = []
    for column, contract in (contracts or {}).items():
        try:
            if contract.retired:
                cutoff = pd.Timestamp(contract.retired)
                if column not in df.columns:
                    continue        # retired AND gone from the frame: expected
                after = df.loc[df.index > cutoff, column].dropna()
                if after.empty:
                    continue        # expected steady state — stay silent
                found.append({
                    "kind": "resurrected",
                    "group": group,
                    "series": series,
                    "column": column,
                    "retired": contract.retired,
                    "last_obs": str(pd.Timestamp(after.index.max()).date()),
                    "note": contract.note,
                })
                continue
            if contract.max_dark_days is None:
                continue            # neither mode set — nothing to check
            last_valid = df[column].last_valid_index() if column in df.columns else None
            if last_valid is None:
                # missing column or all-NaN: dark with an unbounded age
                last_obs, age = None, None
            else:
                last_obs_date = pd.Timestamp(last_valid).date()
                age = (today - last_obs_date).days
                if age <= contract.max_dark_days:
                    continue        # on contract
                last_obs = str(last_obs_date)
            log.warning(
                "dark_column detected: %s/%s.%s last_obs=%s age=%s (max_dark_days=%d)",
                group, series, column, last_obs, age, contract.max_dark_days,
            )
            found.append({
                "kind": "dark",
                "group": group,
                "series": series,
                "column": column,
                "last_obs": last_obs,
                "age_days": age,
                "max_dark_days": contract.max_dark_days,
                "note": contract.note,
            })
        except Exception:  # noqa: BLE001 — a column alarm must never crash the run
            log.warning("column contract check failed for %s/%s.%s",
                        group, series, column, exc_info=True)
    return found


def dark_column_annotation(entry: dict) -> str:
    """Render one detect_dark_columns entry as a SINGLE GitHub Actions annotation
    line.

    The caller MUST emit this with a bare ``print(..., flush=True)``.  Routing it
    through a logger prefixes the line ("WARNING ::warning …"), GitHub only parses
    a workflow command when ``::`` sits at column 0, and the alarm silently
    disappears — the failure mode guarded by tests/test_gh_annotation_line_start.py.
    """
    where = f"{entry['group']}/{entry['series']}.{entry['column']}"
    pointer = entry.get("module") or f"collectors/{entry['group']}.py"
    note = " ".join(str(entry.get("note") or "").split())
    tail = f" {note} — see {pointer}" if note else f" — see {pointer}"
    if entry.get("kind") == "resurrected":
        return (
            f"::notice title=retired-column-alive::{where} is RETIRED (upstream "
            f"disclosure ended {entry.get('retired')}) but a non-null value landed "
            f"{entry.get('last_obs')} — upstream may have resumed; a human should "
            f"adjudicate un-retiring the column.{tail}"
        )
    if entry.get("last_obs") is None:
        aged = ("NO non-null value anywhere in the stored series (column missing "
                "or entirely null)")
    else:
        aged = (f"last value {entry.get('last_obs')} is {entry.get('age_days')}d old")
    return (
        f"::warning title=dark-column::{where} has gone dark: {aged}, past its "
        f"{entry.get('max_dark_days')}d contract — the frame itself still looks fresh "
        f"via its other columns, so the frame-grain staleness check cannot see this.{tail}"
    )


def _dark_column_note(entry: dict) -> str:
    """Short human line for FetchResult.notes (the collect summary table)."""
    where = f"{entry['series']}.{entry['column']}"
    if entry.get("kind") == "resurrected":
        return (f"retired column alive: {where} value on {entry.get('last_obs')} "
                f"(retired {entry.get('retired')})")
    return (f"dark column: {where} last={entry.get('last_obs')} "
            f"age={entry.get('age_days')}d (contract {entry.get('max_dark_days')}d)")


def _write_dark_columns(new_entries: list[dict]) -> None:
    """Merge dark-column entries into run_status["dark_columns"], keyed by
    group+series+column so repeated runs deduplicate and refresh detected_at.

    Deliberately NOT run_status["stale_series"]: that key has its own (frame-grain)
    shape and unknown consumers, so column entries go in their own bucket rather
    than smuggling a different schema into an existing contract.
    """
    if not new_entries:
        return
    status = store.read_status()
    existing: list[dict] = status.get("dark_columns", [])
    by_key = {(e.get("group"), e.get("series"), e.get("column")): e for e in existing}
    for entry in new_entries:
        by_key[(entry["group"], entry["series"], entry["column"])] = {
            **entry, "detected_at": datetime.now(timezone.utc).isoformat()
        }
    status["dark_columns"] = list(by_key.values())
    store.write_status(status)


def _contract_entries(adapter: Adapter, series: str, merged: pd.DataFrame,
                      today: date) -> list[dict]:
    """Run the column contracts an adapter declares for one series, if any.

    Fully exception-isolated: the contract pass is an ALARM bolted onto a fetch
    that already succeeded, so nothing in it may turn an 'ok' adapter into a
    'failed' one.
    """
    try:
        contracts = (getattr(adapter, "column_contracts", None) or {}).get(series)
        if not contracts:
            return []
        entries = detect_dark_columns(adapter.group, series, merged, contracts, today)
        module = f"{type(adapter).__module__.replace('.', '/')}.py"
        for entry in entries:
            entry.setdefault("module", module)
        return entries
    except Exception:  # noqa: BLE001 — never fail an adapter over its own alarm
        log.warning("column contract pass failed for %s/%s", adapter.group, series,
                    exc_info=True)
        return []


def _emit_dark_columns(entries: list[dict]) -> list[str]:
    """Print one line-start annotation per entry, persist them, return short notes."""
    notes: list[str] = []
    if not entries:
        return notes
    try:
        for entry in entries:
            notes.append(_dark_column_note(entry))
            # BARE print, never log.*: a logger's prefixing format pushes '::' off
            # column 0 and GitHub drops the annotation entirely (see
            # tests/test_gh_annotation_line_start.py). flush is load-bearing —
            # stdout is block-buffered when piped in CI.
            print(dark_column_annotation(entry), flush=True)
    except Exception:  # noqa: BLE001
        log.warning("dark-column annotation failed", exc_info=True)
    try:
        _write_dark_columns(entries)
    except Exception:  # noqa: BLE001
        log.warning("dark-column run_status write failed", exc_info=True)
    return notes


def _breaker_state() -> dict:
    return store.read_status().get("circuit_breaker", {})


def _probe_state() -> dict:
    return store.read_status().get("circuit_breaker_probe", {})


def _probe_due(last_probe: str | None,
               cooldown_h: float = CIRCUIT_HALF_OPEN_AFTER_H) -> bool:
    """True when an open breaker has waited long enough for its next half-open probe."""
    if not last_probe:
        return True
    try:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(last_probe)).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return True
    return age_h >= cooldown_h


def run_adapter(adapter: Adapter, full_history: bool = False,
                stale_after_days: int | None = None) -> FetchResult:
    """Execute one adapter with circuit breaker + graceful degradation."""
    if stale_after_days is None:
        stale_after_days = adapter.stale_after_days
    breaker = _breaker_state()
    fails = breaker.get(adapter.name, 0)
    half_open = False
    if fails >= CIRCUIT_BREAKER_FAILS and not full_history:
        if not _probe_due(_probe_state().get(adapter.name)):
            return FetchResult(adapter.name, "dead",
                               error=f"circuit open ({fails} consecutive failures)")
        half_open = True   # cooldown elapsed -> let ONE probe through to test recovery
        log.info("adapter %s breaker half-open: probing after %d fails", adapter.name, fails)

    try:
        frames = adapter.fetch(full_history=full_history)
        rows, last = 0, None
        today = datetime.now(timezone.utc).date()
        dark_found: list[dict] = []
        for series_name, df in frames.items():
            df = adapter.validate(series_name, df)
            merged = store.upsert(adapter.group, series_name, df,
                                  outlier_col=df.columns[0] if len(df.columns) == 1 else None,
                                  normalize_index=getattr(adapter, "normalize_index", True),
                                  overwrite_overlap=getattr(adapter, "overwrite_overlap", False))
            rows += len(df)
            last = max(filter(None, [last, merged.index.max()]))
            # Column-grain contract check on the MERGED frame (store ground truth —
            # the fetch window is a short recent slice and cannot say when a column
            # last had a value). Opt-in: adapters declaring no contracts are untouched.
            dark_found.extend(_contract_entries(adapter, series_name, merged, today))
        status = "ok"
        if last is not None:
            age = (datetime.now(timezone.utc).date() - last.date()).days
            if age > stale_after_days:
                status = "stale"
        # fetch_result_status is an OPTIONAL adapter protocol (2 of ~228 define it) —
        # a missing attribute must never fail an otherwise-successful fetch.
        declared = getattr(adapter, "fetch_result_status", None)
        declared_status = declared(frames) if callable(declared) else None
        if declared_status is not None:
            if declared_status not in {"ok", "stale", "blocked"}:
                raise ValueError(f"{adapter.name}: unsupported declared fetch status {declared_status!r}")
            status = declared_status
        # Frozen-tail detector: a 200-OK fetch whose last observation never advances
        # (series discontinued upstream) is invisible to is_connection_error. Compare
        # each fetched series' last observation against cadence. Non-fatal; writes
        # named stale_series entries to run_status.json for the health surface.
        stale_found = detect_stale_series(
            adapter.group, frames, cadence_days=stale_after_days)
        if stale_found:
            _write_stale_series(stale_found)
            notes = [f"frozen tail: {e['series']} last={e['last_obs']} age={e['age_days']}d"
                     for e in stale_found]
        else:
            notes = []
        # Column-grain alarms: bare-print annotations + run_status["dark_columns"].
        notes += _emit_dark_columns(dark_found)
        res = FetchResult(adapter.name, status, rows=rows,
                          last_date=str(last.date()) if last is not None else None,
                          notes=notes)
    except Exception as e:  # noqa: BLE001 — degrade, never crash the run
        # expected_failure is likewise optional — the handler itself must be
        # attribute-safe or one duck-typing gap crashes the whole collect pass.
        expected = getattr(adapter, "expected_failure", None)
        if expected:
            log.info("adapter %s blocked (known): %s", adapter.name, safe_exc_text(e))
            res = FetchResult(adapter.name, "blocked", error=expected)
        else:
            # M5 (AD-1C0 review): FetchResult.error lands in the TRACKED
            # data/run_status.json via collect.py's asdict(r) — a raw credential
            # in a vendor URL/header/JSON body must never reach a committed file,
            # not just a log line. Both the logged traceback AND the persisted
            # `error` field are sanitized.
            tb = redact_secrets(traceback.format_exc(limit=3))
            log.error("adapter %s failed: %s\n%s", adapter.name, safe_exc_text(e), tb)
            res = FetchResult(adapter.name, "failed",
                              error=f"{type(e).__name__}: {safe_exc_text(e)}")
    if half_open:
        res.probed_at = datetime.now(timezone.utc).isoformat()
    return res


def update_breaker(results: list[FetchResult],
                   probe_state: dict | None = None) -> tuple[dict, dict]:
    """Recompute (circuit_breaker, circuit_breaker_probe) after a collect pass.

    A 'failed' increments the breaker; a reachable, definitive outcome
    ('ok'/'stale'/'blocked') closes it. 'blocked' clears too — it is an
    expected_failure (a known limitation, not a transient outage), so it must not
    leave the source wedged 'dead'. The probe map records when a half-open probe was
    last attempted so an open breaker re-probes at most once per cooldown.
    """
    breaker = _breaker_state()
    probe = dict(_probe_state() if probe_state is None else probe_state)
    for r in results:
        if r.status == "failed":
            breaker[r.source] = breaker.get(r.source, 0) + 1
        elif r.status in ("ok", "stale", "blocked"):
            breaker[r.source] = 0
        # half-open bookkeeping: a recovered/blocked source forgets its probe clock;
        # a still-failing probe stamps the time so it waits a full cooldown again.
        if r.status in ("ok", "stale", "blocked"):
            probe.pop(r.source, None)
        elif r.probed_at:
            probe[r.source] = r.probed_at
    return breaker, probe
