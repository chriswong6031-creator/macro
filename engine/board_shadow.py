"""HK + Canada Prophet Shadow Substrate — frozen contract V1 (zero-authority).

research/PROPHET_SHADOW_CONTRACT_V1.md is the binding spec. Frozen after an Opus
adversarial pre-implementation review (2026-08-21); every clause below traces to
a named finding (F1-F18) from that review. This module is STORAGE + ISOLATION
only — no ranking model, no discovery-alpha wave, no winner. The challenger
registry is EMPTY at merge (contract §4); registering a challenger is a later,
separately reviewed change, and needs zero schema migration and zero
production-builder surgery.

Two market-parameterized stores (parquet, git-tracked, append-only, keep-first):

    Lane A (same-population rank pairs):
        data/prophet_shadow/{hk,ca}_rank_pairs.parquet
        key: (date, ticker, challenger_definition)
    Lane B (discovery observations):
        data/prophet_shadow/{hk,ca}_discovery.parquet
        key: (session_date, security_ref, challenger_definition)

Authority law (contract §2/§5): NOTHING in production reads either store. No
rank, gate, plan, publication, Featured, Brain, or entry effect. Enforced
statically repo-wide by K6 (tests/test_board_shadow.py) — the string
'prophet_shadow' may not appear outside this module and its own tests.

Outcome law: neither lane stores an outcome column, ever, and this module
NEVER reads price history or computes a return (F7/F13). The CALL surface is
narrowly pinned to exactly two read points, both structured PIT stores, never
market data: :func:`_read_incumbent_positions` (the board_ledger board_pos
read-back, contract §2) and :func:`_read_own_store` (this module's own Lane
A/B parquet, for keep-first merge and prospectivity lookups — the same thing
board_ledger._merge_and_write does against its own store). K3's AST guard
(tests/test_board_shadow.py) walks this module's source EXCLUDING those two
function bodies and hard-fails on any Name/Attribute resolving to a grading
surface, a market-close reader, or a bare pandas/store parquet read anywhere
else.

Lane gates mirror board_ledger.append_board exactly (contract §4): HK writes
only under engine.ledger_lane.asia_advance_enabled() (CN_LANE=asia), CA only
under nightly_advance_enabled() (COLLECT_LANE=nightly); an import failure is
treated as off-lane (fail-closed). The single public entry point,
:func:`write_shadow`, is fail-soft by contract — it never raises into a build —
and is called exactly once per market, downstream of that market's published
artifact (contract §4; the ordering differs by market and is the CALLER's
responsibility, not this module's).
"""
from __future__ import annotations

import copy
import datetime as _dt
import fnmatch
import logging
import math
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from engine import board_ledger
from lib import config

log = logging.getLogger(__name__)

MARKETS = ("HK", "CA")
STORE_DIR = "prophet_shadow"

# Bind the EXACT function object board_ledger uses to normalise a stamped
# board_definition cell (contract §2, F6 — "two normalizers feeding one
# exact-equality comparison must be one object"). This is an IMPORT, never a
# re-implementation; a test pins `_definition_or_none is board_ledger._definition_or_none`.
_definition_or_none = board_ledger._definition_or_none

# ---------------------------------------------------------------------------
# Schema law (contract §1, F4) — pinned column allowlists. No column reaches
# disk that is not in one of these two lists (denylist outranks both — see
# _DENY_PATTERNS below).
# ---------------------------------------------------------------------------
_SCHEMA_A = (
    "date", "market", "ticker",
    "incumbent_definition", "incumbent_rank", "incumbent_lane",
    "challenger_definition", "challenger_rank", "challenger_rank_domain",
    "challenger_score_raw", "challenger_score_conservative",
    "challenger_coverage", "population_n", "challenger_offlist_n",
    "stamped_at",
)
_LANE_A_KEY = ("date", "ticker", "challenger_definition")

#: Lane B evidence families are REGISTERED, not free-form (contract §1): a
#: family contributes exactly ``<family>_status`` + ``<family>_value``, and
#: registering one is a reviewed code change to this tuple (which regenerates
#: _schema_b()). EMPTY at merge — no family exists yet.
FAMILY_REGISTRY: tuple[str, ...] = ()

_FIXED_SCHEMA_B_HEAD = (
    "session_date", "market",
    "security_ref", "security_ref_raw", "ref_collision_n",
    "challenger_definition", "candidate_origin",
    "first_seen_at",
)
_FIXED_SCHEMA_B_TAIL = (
    "availability_status", "availability_source",
    "visible_to_user", "published_authority",
    "stamped_at",
)
#: `security_ref_raw` joins the key (review finding M4): without it, two
#: DISTINCT raw refs that collided into one `security_ref` this session (K9)
#: survive the FIRST write (no prior store to merge against, so
#: `_merge_write_lane_b` skips drop_duplicates entirely) but are silently
#: collapsed to ONE row the moment a SECOND write_shadow call merges against
#: that prior store — `drop_duplicates` on (session_date, security_ref,
#: challenger_definition) alone sees two rows with identical values on all
#: three and keeps only the first. Contract §1 states the key without this
#: column; this is a deliberate, reviewed widening, not a silent
#: reinterpretation — see the build packet's DEVIATIONS.
_LANE_B_KEY = ("session_date", "security_ref", "security_ref_raw", "challenger_definition")


def _family_columns(registry: tuple[str, ...] = FAMILY_REGISTRY) -> tuple[str, ...]:
    cols: list[str] = []
    for fam in registry:
        cols.append(f"{fam}_status")
        cols.append(f"{fam}_value")
    return tuple(cols)


def schema_b(registry: tuple[str, ...] = FAMILY_REGISTRY) -> tuple[str, ...]:
    """The full Lane B column allowlist: fixed columns + registered families."""
    return (*_FIXED_SCHEMA_B_HEAD, *_family_columns(registry), *_FIXED_SCHEMA_B_TAIL)


#: Hard-fail DENYLIST of outcome/authority column families (contract §1).
#: Outranks the allowlist — a column matching one of these patterns is dropped
#: even if it happens to also appear in _SCHEMA_A/schema_b() (defense in
#: depth; by construction neither allowlist contains a match today).
#: `visible_to_user` / `published_authority` are the two pinned literal-False
#: columns of contract §3 and are exempt from the visible*/published* pattern
#: by EXACT NAME only — nothing else matching those two patterns is exempt.
_DENY_PATTERNS = (
    "fwd_*", "*_ret", "excess*", "mfe*", "terminal_state*", "hit_*",
    "pnl*", "rank_ic*", "size*", "weight*", "gate*", "plan*", "featured*",
    "visible*", "published*",
)
_DENY_EXACT_EXEMPT = frozenset({"visible_to_user", "published_authority"})


def _is_denylisted(column: str) -> bool:
    if column in _DENY_EXACT_EXEMPT:
        return False
    return any(fnmatch.fnmatchcase(column, pattern) for pattern in _DENY_PATTERNS)


def classify_column(column: str, schema: tuple[str, ...]) -> str:
    """Return 'allowed' / 'denied' / 'unclassified' for one column name."""
    if _is_denylisted(column):
        return "denied"
    if column in schema:
        return "allowed"
    return "unclassified"


# IMPORT-TIME ASSERTION (review finding M3): the denylist must never silently
# swallow a schema member via `_apply_write_seam`'s `effective_schema` filter
# — this fails LOUD at import time the moment a future schema edit adds a
# column that also matches a deny pattern, rather than discovering it as a
# missing column on disk months later.
_schema_a_denylisted = [c for c in _SCHEMA_A if _is_denylisted(c)]
assert not _schema_a_denylisted, (
    f"_SCHEMA_A contains denylisted column(s): {_schema_a_denylisted} — "
    "rename the column or narrow the deny pattern before it ships"
)
_schema_b_denylisted = [c for c in schema_b() if _is_denylisted(c)]
assert not _schema_b_denylisted, (
    f"schema_b() contains denylisted column(s): {_schema_b_denylisted} — "
    "rename the column or narrow the deny pattern before it ships"
)


def _apply_write_seam(frame: pd.DataFrame, schema: tuple[str, ...], lane_name: str) -> pd.DataFrame:
    """The write seam (contract §1, K11): reindex to the schema AFTER
    stripping the denylist FROM the schema itself — the denylist outranks the
    allowlist even for a column that is (or somehow becomes) a member of
    ``schema`` (review finding M3: the previous shape only ever checked
    denylist membership for columns NOT already in ``schema``, so a
    denylisted name that was also a schema member would survive
    ``reindex(columns=schema)`` untouched — dormant today only because no
    current schema member happens to match a deny pattern, which is exactly
    what :data:`_SCHEMA_A`/:func:`schema_b`'s own assert below exists to keep
    true). Denylisted columns and unclassified columns are DISTINCT failure
    classes and get their own line-start ``::warning`` (bare print,
    flush=True — CLAUDE.md annotation law; never through a logger)."""
    effective_schema = [c for c in schema if not _is_denylisted(c)]
    present = set(frame.columns)
    denied = sorted(c for c in present if _is_denylisted(c))
    unclassified = sorted(c for c in present if c not in schema and c not in denied)
    if denied:
        print(
            f"::warning title=board-shadow-denylist-column::{lane_name}: dropped "
            f"outcome/authority column(s) {', '.join(denied)} — denylist outranks "
            "the allowlist and this write never persisted them",
            flush=True,
        )
    if unclassified:
        print(
            f"::warning title=board-shadow-unclassified-column::{lane_name}: dropped "
            f"unclassified column(s) {', '.join(unclassified)} — register a family "
            "or extend the schema allowlist in engine/board_shadow.py",
            flush=True,
        )
    return frame.reindex(columns=effective_schema)


# ---------------------------------------------------------------------------
# canonical_ref() — the ONE importable identity canonicalizer (contract §3, F11)
# ---------------------------------------------------------------------------
def canonical_ref(raw: Any) -> str | None:
    """Canonicalise a raw discovery security reference.

    Today's rule is EXACT identity over board_ledger's verbatim ``str(ticker)``
    — no ``.strip()``, no case-folding, no punctuation normalisation. A
    strip-or-fold canonicalizer would mint a SECOND identity truth diverging
    from what board_ledger actually stores (F11's own concern, m3 review
    correction 2026-08-21: the draft version's bare ``.strip()`` was exactly
    that second truth, however minimal). Every Lane B writer MUST call this
    exact function; a future semantic canonicalizer replaces only this body,
    never a second copy. Collision machinery (ref_collision_n, K9) is
    therefore DORMANT in production until that future canonicalizer folds two
    distinct raw forms together — correct substrate behaviour, not a gap:
    tests exercise the collision path by monkeypatching this function to a
    strip-variant, never by relying on today's identity rule to collide.
    """
    if raw is None:
        return None
    text = str(raw)
    return text or None


# ---------------------------------------------------------------------------
# Store paths + the two pinned, sanctioned read points (K3 CALL surface)
# ---------------------------------------------------------------------------
def _store_dir() -> Path:
    return config.data_dir() / STORE_DIR


def _lane_a_path(market: str) -> Path:
    return _store_dir() / f"{market.lower()}_rank_pairs.parquet"


def _lane_b_path(market: str) -> Path:
    return _store_dir() / f"{market.lower()}_discovery.parquet"


def _read_board_parquet(market: str, columns: list[str]) -> pd.DataFrame | None:
    """THE sanctioned board-parquet read point (contract §2, F5).

    The ONE place in this module permitted to touch ``pandas.read_parquet``
    against ``data/board_ledger/<m>_board.parquet`` — every read of that store
    (the live board_pos read-back in :func:`_read_incumbent_positions` AND the
    cross-store validator's board_definition check) goes through this single
    function. K3's AST guard excludes this function's body (and
    :func:`_read_own_store`, the module's own Lane A/B read point) by name and
    hard-fails on the same reference anywhere else in the module.
    """
    path = board_ledger._store_path(market)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path, columns=columns)
    except Exception as exc:  # noqa: BLE001 — read-only probe, degrade never raise
        log.warning("board_shadow(%s): board_ledger read failed (%s)", market, exc)
        return None


def _read_incumbent_positions(market: str, date: str) -> dict[str, int]:
    """Read ``board_pos`` back from board_ledger for the exact (date, ticker)
    pairs AFTER board_ledger.append_board has already returned for this build
    pass — never re-derived by enumerating the calls list a second time
    (board_pos is minted inside append_board after a ticker-less row skip, so
    an independent enumerate silently records a phantom board order, F5)."""
    frame = _read_board_parquet(market, ["date", "ticker", "board_pos"])
    if frame is None:
        return {}
    sub = frame[frame["date"].astype(str) == str(date)]
    out: dict[str, int] = {}
    for ticker, pos in zip(sub["ticker"], sub["board_pos"]):
        if pd.notna(pos):
            out[str(ticker)] = int(pos)
    return out


def _read_own_store(path: Path, columns: list[str] | None = None) -> pd.DataFrame | None:
    """Read THIS module's own Lane A/B parquet (never price/outcome data).

    The second sanctioned read point (K3): used for keep-first merge writes
    and Lane B's first_seen_at / store-max-session-date lookups — exactly the
    role board_ledger._merge_and_write's own ``pd.read_parquet`` plays against
    board_ledger's store. Reading one's own accreting store is not a private
    grader; it never touches price history, forward metrics, or terminal
    state.
    """
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path, columns=columns)
    except Exception as exc:  # noqa: BLE001
        log.warning("board_shadow: own-store read failed for %s (%s)", path, exc)
        return None


# ---------------------------------------------------------------------------
# Small coercion helpers (self-contained; this module never imports grading)
# ---------------------------------------------------------------------------
def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _coerce_object_cols(frame: pd.DataFrame, cols: tuple[str, ...]) -> pd.DataFrame:
    """Force nullable-string columns to object dtype (NaN -> None) so a later
    cell write never hits pandas 3.x's float-dtype string-write TypeError
    (the same failure mode board_ledger._coerce_object_cols exists for)."""
    for col in cols:
        if col in frame.columns and frame[col].dtype != object:
            coerced = frame[col].astype(object)
            frame[col] = coerced.where(pd.notna(coerced), None)
    return frame


# ---------------------------------------------------------------------------
# Challenger registry (contract §4, market-scoped per the 2026-08-21 post-merge
# Sol review correction — see the contract's dated correction section) — EMPTY
# at merge.
# ---------------------------------------------------------------------------
#: {(market, challenger_definition): {"rank_fn": callable | None, "discovery_fn": callable | None}}
#: rank_fn(calls: list[dict]) -> {ticker: {"score_raw": float|None, "score_conservative": float|None}}
#: discovery_fn(asof: str) -> list[dict]  (raw Lane B candidate rows)
#: Keyed by (market, challenger_definition), NOT by challenger_definition alone
#: — the original merged shape keyed on definition only, so the FIRST real
#: registrant would have executed in BOTH the HK and CA lanes regardless of
#: which market it was meant for (the defect this correction repairs; zero
#: production registrants existed at the time, so no backward compatibility
#: with the unscoped key is owed). Registering a challenger needs ZERO schema
#: migration and ZERO production-builder surgery — it is purely an entry in
#: this dict.
CHALLENGER_REGISTRY: dict[tuple[str, str], dict[str, Callable | None]] = {}


def register_challenger(
    market: str,
    definition: str,
    *,
    rank_fn: Callable[[list[dict]], dict] | None = None,
    discovery_fn: Callable[[str], list[dict]] | None = None,
) -> None:
    """Register a challenger, bound EXPLICITLY to one market.

    ``market`` is a required first positional argument — there is no
    market-less registration shape. The registry key is ``(market,
    definition)``, so the same ``challenger_definition`` string may be
    registered independently for HK and for CA without collision, and
    :func:`write_shadow` only ever iterates the registrations keyed to the
    market it was called for (:func:`_registrations_for`).

    Market binding is EXPLICIT and decided by the CALLER at registration
    time — challenger functions (``rank_fn``/``discovery_fn``) must NEVER
    decide market membership themselves by inspecting tickers, board
    definitions, environment variables, or any other incidental state. The
    ``market`` argument here is the only lawful place that decision is made;
    a challenger that branches on market internally defeats the isolation
    this registry exists to provide.

    Raises ``ValueError`` immediately (fail-loud at registration time) if
    ``market`` does not normalize (``str(market).upper()``) into
    :data:`MARKETS`. This can never reach a production build today — the
    production registry is empty — but a future registrant must not
    silently no-op into the wrong lane instead of failing loudly at the
    call site that got it wrong.

    Out of scope for this wave to call in production (no challenger model
    ships here); tests use this to exercise the writer.
    """
    normalized_market = str(market).upper()
    if normalized_market not in MARKETS:
        raise ValueError(
            f"register_challenger: market {market!r} not in {MARKETS}"
        )
    key = (normalized_market, str(definition))
    if key in CHALLENGER_REGISTRY:
        # D9 (nit, last-wins is intentional): an overwrite is silent by
        # design elsewhere in this module, but a silent overwrite of an
        # existing registration is exactly the kind of thing a later
        # registrant would want to know happened — name the key so the
        # overwrite is visible in logs, never hidden.
        log.warning(
            "board_shadow: register_challenger overwriting existing registration "
            "for %r (last registration wins)", key,
        )
    CHALLENGER_REGISTRY[key] = {
        "rank_fn": rank_fn, "discovery_fn": discovery_fn,
    }


def _registrations_for(market: str) -> list[tuple[str, dict[str, Callable | None]]]:
    """The market-selection seam (contract correction 2026-08-21): every
    ``(challenger_definition, spec)`` pair registered for EXACTLY this
    market, sorted by definition. This is the ONE place :func:`write_shadow`
    learns which registrations apply to its own call — an HK write must
    never see a CA-only registration and vice versa.

    This function is the SOLE authority on market scoping: it hands back the
    spec dict directly rather than a bare list of names, so nothing
    downstream re-derives market membership via a second, independently
    protected lookup (a name-only return would need
    ``CHALLENGER_REGISTRY[(market, definition)]`` at the call site, which
    would silently double as a second market check via KeyError — muddying
    exactly which seam is responsible for isolation). K19 proves this seam
    is load-bearing, not decorative: with this function monkeypatched to
    ignore market scoping entirely (return every registered
    ``(definition, spec)`` pair regardless of market), the K15/K16-style
    isolation kills above are shown to FAIL — the foreign challenger's
    function actually executes, not merely errors out safely.

    D6 (malformed-key hardening): every registration reaches this module
    ONLY through :func:`register_challenger`, which always mints a
    well-formed ``(MARKET, str)`` tuple key — but ``CHALLENGER_REGISTRY`` is
    a plain module-level dict, not an encapsulated type, so nothing stops a
    test (or a future caller) from poking a malformed key directly into it
    (e.g. a bare string). Unpacking such a key via ``for (mkt, d), spec in
    CHALLENGER_REGISTRY.items()`` raises, and — because this function is
    called from :func:`write_shadow`'s OUTER try (before the per-registration
    guard added for D7) — that raise used to flip the ENTIRE pass to
    ``registry_state=error`` for BOTH markets over one bad key belonging to
    neither. A malformed key here is skipped with a named warning instead;
    only well-formed keys participate in market selection."""
    pairs: list[tuple[str, dict[str, Callable | None]]] = []
    for key, spec in CHALLENGER_REGISTRY.items():
        if not (
            isinstance(key, tuple) and len(key) == 2
            and isinstance(key[0], str) and isinstance(key[1], str)
        ):
            log.warning(
                "board_shadow: malformed CHALLENGER_REGISTRY key %r skipped "
                "(not a (market, definition) str-tuple)", key,
            )
            continue
        mkt, definition = key
        if mkt == market:
            pairs.append((definition, spec))
    return sorted(pairs, key=lambda pair: pair[0])


# ---------------------------------------------------------------------------
# Lane A — same-population rank challenger (contract §2)
# ---------------------------------------------------------------------------
def _dense_rank_desc(scores: dict[str, float]) -> dict[str, int]:
    """Dense rank (1 = best) over exactly the given scores (contract §2 F9:
    'challenger_rank_domain=minted_population' — dense rank over the minted
    population is the only lawful shape; ties share a rank and the next rank
    increments by 1, never skips)."""
    if not scores:
        return {}
    uniq_desc = sorted(set(scores.values()), reverse=True)
    rank_of = {value: i + 1 for i, value in enumerate(uniq_desc)}
    return {ticker: rank_of[value] for ticker, value in scores.items()}


def _write_lane_a(
    market: str,
    asof: str,
    calls: list[dict],
    definition: str,
    rank_fn: Callable[[list[dict]], dict],
    incumbent_positions: dict[str, int],
    failures: list[dict[str, str]] | None = None,
) -> int:
    """Mint Lane A rows ONLY from ``calls`` (contract §2 population law,
    attack class 2): the writer takes the exact calls list as its sole
    population input and cannot re-originate. A name the challenger did not
    score gets a row with null challenger fields (missing != zero); a name
    the challenger emitted that is NOT in the incumbent population is
    filtered out and counted in challenger_offlist_n, never silently
    dropped-and-forgotten.

    ``failures`` (hk-discovery wave, additive): when supplied, a ``rank_fn``
    exception is ALSO appended to it as ``{"definition": ..., "error": ...}``
    — the receipt's failure-threading, never a change to this function's own
    fail-soft contract (it still returns a valid int either way)."""
    tickers: list[str] = []
    call_by_ticker: dict[str, dict] = {}
    for call in calls:
        ticker = call.get("ticker")
        if not ticker:
            continue
        ticker = str(ticker)
        if ticker not in call_by_ticker:
            tickers.append(ticker)
            call_by_ticker[ticker] = call
    population_n = len(tickers)
    if population_n == 0:
        return 0

    try:
        raw_scores = dict(rank_fn(copy.deepcopy(calls)) or {})
    except Exception as exc:  # noqa: BLE001 — a challenger must never break the build
        log.warning("board_shadow(%s): challenger %s rank_fn failed (%s)", market, definition, exc)
        if failures is not None:
            failures.append({"definition": definition, "error": str(exc)})
        raw_scores = {}

    offlist = sorted({str(t) for t in raw_scores} - set(call_by_ticker))
    scoped = {str(t): (v or {}) for t, v in raw_scores.items() if str(t) in call_by_ticker}
    finite_scores = {
        t: score for t in scoped
        if (score := _finite(scoped[t].get("score_raw"))) is not None
    }
    dense = _dense_rank_desc(finite_scores)
    stamped_at = _now_iso()
    coverage = round(len(dense) / population_n, 6) if population_n else None

    rows = []
    for ticker in tickers:
        call = call_by_ticker[ticker]
        sv = scoped.get(ticker) or {}
        rows.append({
            "date": str(asof), "market": market, "ticker": ticker,
            "incumbent_definition": _definition_or_none(call.get("board_definition")),
            "incumbent_rank": incumbent_positions.get(ticker),
            "incumbent_lane": "watch" if str(call.get("group") or "") == "watch" else "buy",
            "challenger_definition": definition,
            "challenger_rank": dense.get(ticker),
            "challenger_rank_domain": "minted_population",
            "challenger_score_raw": _finite(sv.get("score_raw")),
            "challenger_score_conservative": _finite(sv.get("score_conservative")),
            "challenger_coverage": coverage,
            "population_n": population_n,
            "challenger_offlist_n": len(offlist),
            "stamped_at": stamped_at,
        })
    if offlist:
        print(
            f"::warning title=board-shadow-offlist::{market}/{definition}: "
            f"{len(offlist)} challenger name(s) off the incumbent population "
            f"(Lane B territory, never Lane A): {', '.join(offlist)}",
            flush=True,
        )
    return _merge_write_lane_a(market, pd.DataFrame(rows))


def _merge_write_lane_a(market: str, new_frame: pd.DataFrame) -> int:
    new_frame = _apply_write_seam(new_frame, _SCHEMA_A, "lane_a")
    path = _lane_a_path(market)
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = _read_own_store(path)
    if prior is not None:
        cols = list(dict.fromkeys([*_SCHEMA_A, *prior.columns]))
        combined = pd.concat(
            [prior.reindex(columns=cols), new_frame.reindex(columns=cols)],
            ignore_index=True,
        )
        combined = combined.drop_duplicates(subset=list(_LANE_A_KEY), keep="first")
    else:
        combined = new_frame
    combined = _coerce_object_cols(combined, ("incumbent_definition", "incumbent_lane",
                                              "challenger_definition", "challenger_rank_domain"))
    if "date" in combined.columns:
        combined = combined.sort_values("date", kind="stable").reset_index(drop=True)
    combined.to_parquet(path, index=False)
    return int(len(new_frame))


# ---------------------------------------------------------------------------
# Lane B — population-changing discovery challenger (contract §3)
# ---------------------------------------------------------------------------
SETTLE_WINDOW_DAYS = 3  # weekend-safe buffer, mirrors china_prophet_shadow's settled-session fence


def _settle_violation(session_date: str, stamp_date: str) -> bool:
    """Wall-clock fence (K8b, F10): stamped_at's date may not exceed
    session_date by more than the market's settle window. An unparseable date
    on either side refuses (fail-closed)."""
    try:
        sd = _dt.date.fromisoformat(str(session_date)[:10])
        td = _dt.date.fromisoformat(str(stamp_date)[:10])
    except Exception:  # noqa: BLE001
        return True
    return (td - sd).days > SETTLE_WINDOW_DAYS


def _discovery_store_max_session(market: str) -> str | None:
    frame = _read_own_store(_lane_b_path(market), columns=["session_date"])
    if frame is None or frame.empty:
        return None
    dates = frame["session_date"].dropna().astype(str)
    return str(dates.max()) if len(dates) else None


def _discovery_first_seen_lookup(market: str, definition: str) -> dict[str, str]:
    """{security_ref: earliest first_seen_at already on disk} for this
    challenger — the min-carry lookup K14's forward-clock law depends on."""
    frame = _read_own_store(
        _lane_b_path(market),
        columns=["security_ref", "challenger_definition", "first_seen_at"],
    )
    if frame is None or frame.empty:
        return {}
    sub = frame[frame["challenger_definition"].astype(str) == str(definition)]
    if sub.empty:
        return {}
    out: dict[str, str] = {}
    for ref, group in sub.groupby("security_ref"):
        values = [str(v) for v in group["first_seen_at"].dropna()]
        if values:
            out[str(ref)] = min(values)
    return out


def _write_lane_b(market: str, asof: str, definition: str,
                   discovery_fn: Callable[[str], list[dict]],
                   failures: list[dict[str, str]] | None = None) -> int:
    """``failures`` (hk-discovery wave, additive): see :func:`_write_lane_a`'s
    matching note — a ``discovery_fn`` exception is ALSO appended to it,
    never a change to this function's own fail-soft contract."""
    try:
        raw_rows = list(discovery_fn(str(asof)) or [])
    except Exception as exc:  # noqa: BLE001 — a challenger must never break the build
        log.warning("board_shadow(%s): challenger %s discovery_fn failed (%s)", market, definition, exc)
        if failures is not None:
            failures.append({"definition": definition, "error": str(exc)})
        return 0
    if not raw_rows:
        return 0

    store_max = _discovery_store_max_session(market)
    stamped_at = _now_iso()
    stamp_date = stamped_at[:10]

    accepted: list[dict] = []
    n_asof = n_wallclock = n_behind_head = 0
    for raw in raw_rows:
        session_date = str(raw.get("session_date") or asof)
        if session_date != str(asof):
            n_asof += 1
            continue
        if _settle_violation(session_date, stamp_date):
            n_wallclock += 1
            continue
        if store_max is not None and session_date < store_max:
            n_behind_head += 1
            continue
        accepted.append(raw)
    if n_asof or n_wallclock or n_behind_head:
        print(
            f"::warning title=board-shadow-discovery-refused::{market}/{definition}: "
            f"refused rows — asof_mismatch={n_asof} wallclock_fence={n_wallclock} "
            f"behind_head={n_behind_head}",
            flush=True,
        )
    if not accepted:
        return 0

    by_ref: dict[str, list[dict]] = {}
    for raw in accepted:
        ref = canonical_ref(raw.get("security_ref_raw"))
        if not ref:
            continue
        # NOTE: `_raw` is the EXACT string as received — never stripped/
        # normalised. K9's collision counter must see " AAA" and "AAA " as
        # two DISTINCT raw refs even though canonical_ref() folds them
        # together; stripping here would silently make every whitespace-only
        # collision invisible.
        by_ref.setdefault(ref, []).append({
            **raw,
            "_raw": str(raw.get("security_ref_raw"))
                    if raw.get("security_ref_raw") is not None else "",
        })

    existing_first_seen = _discovery_first_seen_lookup(market, definition)
    rows = []
    for ref, group in by_ref.items():
        distinct_raw = sorted({g["_raw"] for g in group})
        collision_n = len(distinct_raw)
        if collision_n > 1:
            print(
                f"::warning title=board-shadow-ref-collision::{market}/{definition}/{ref}: "
                f"{collision_n} distinct raw ref(s) canonicalised together this session "
                f"— counted, never silently collapsed: {', '.join(distinct_raw)}",
                flush=True,
            )
        prior_min = existing_first_seen.get(ref)
        # TRUE min(), not "prior_min if it exists" (n2, review round 2
        # clock-skew correction): ISO-8601 UTC strings from _now_iso() sort
        # lexicographically in chronological order, so a plain string min()
        # is correct without parsing. The earlier shape silently assumed
        # prior_min always precedes today's stamped_at — true in the ordinary
        # forward-flowing case, but a genuine min() is what "never advances,
        # only carries the earliest" actually means under clock skew across
        # machines/runners.
        first_seen_at = min(prior_min, stamped_at) if prior_min else stamped_at
        for g in group:
            row = {
                "session_date": str(asof), "market": market,
                "security_ref": ref, "security_ref_raw": g["_raw"],
                "ref_collision_n": collision_n,
                "challenger_definition": definition,
                "candidate_origin": g.get("candidate_origin"),
                "first_seen_at": first_seen_at,
                "availability_status": g.get("availability_status"),
                "availability_source": g.get("availability_source"),
                "visible_to_user": False,
                "published_authority": False,
                "stamped_at": stamped_at,
            }
            for fam in FAMILY_REGISTRY:
                row[f"{fam}_status"] = g.get(f"{fam}_status")
                row[f"{fam}_value"] = g.get(f"{fam}_value")
            rows.append(row)
    if not rows:
        return 0
    return _merge_write_lane_b(market, pd.DataFrame(rows))


def _merge_write_lane_b(market: str, new_frame: pd.DataFrame) -> int:
    schema = schema_b()
    new_frame = _apply_write_seam(new_frame, schema, "lane_b")
    path = _lane_b_path(market)
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = _read_own_store(path)
    if prior is not None:
        cols = list(dict.fromkeys([*schema, *prior.columns]))
        combined = pd.concat(
            [prior.reindex(columns=cols), new_frame.reindex(columns=cols)],
            ignore_index=True,
        )
        # Append-only, keep-FIRST (contract §3): no updates, no deletes, no
        # forward-clock resets. A later session re-observing the same key is a
        # NEW row (different session_date is part of the key); a rerun of the
        # SAME session collapses to the first-written row.
        combined = combined.drop_duplicates(subset=list(_LANE_B_KEY), keep="first")
    else:
        combined = new_frame
    combined = _coerce_object_cols(
        combined,
        ("security_ref", "security_ref_raw", "challenger_definition", "candidate_origin",
         "availability_status", "availability_source", *_family_columns()),
    )
    if "session_date" in combined.columns:
        combined = combined.sort_values("session_date", kind="stable").reset_index(drop=True)
    combined.to_parquet(path, index=False)
    return int(len(new_frame))


# ---------------------------------------------------------------------------
# Public entry point — contract §4 wiring
# ---------------------------------------------------------------------------
#: D2(a) reentrancy guard: a plain module-level flag, not a lock (this module
#: is single-threaded per build pass). Refuses a reentrant write_shadow call
#: fail-soft rather than let a challenger call back into write_shadow for the
#: OTHER market mid-pass (probe-G1 shape) execute that other market's own
#: registrations from inside the call it was never meant to trigger.
_WRITE_SHADOW_ACTIVE = False


def _discovery_receipt_path(market: str) -> Path:
    """hk-discovery wave (contract §4's deferred surface-freshness wiring):
    the per-market freshness receipt, basename ``<market.lower()>_discovery_
    receipt.json`` (write-surface fence: the basename starts with the
    market's own lowercase prefix, exactly like the Lane A/B store files)."""
    return _store_dir() / f"{market.lower()}_discovery_receipt.json"


def _write_discovery_receipt(
    market: str,
    asof: str,
    registry_state: str,
    written: int,
    market_registrations: list[tuple[str, dict[str, Callable | None]]],
    challenger_failures: list[dict[str, str]],
) -> None:
    """Best-effort freshness receipt — additive, never raises. Written ONLY
    when :func:`_registrations_for` was non-empty for this market (callers
    check that before calling this), on BOTH the ``wrote_n_rows`` and
    ``error`` registry-state paths, so scripts/check_surface_freshness.py can
    tell 'absent, not yet wired' apart from 'wired and healthy' apart from
    'wired and broken'. A receipt-write failure logs a line-start
    ``::warning`` (bare print, flush=True — CLAUDE.md annotation law) and
    never breaks write_shadow's own fail-soft contract."""
    try:
        import json as _json

        payload = {
            "market": market,
            "as_of": asof,
            "registry_state": registry_state,
            "written": int(written),
            "definitions": sorted(definition for definition, _spec in market_registrations),
            "challenger_failures": list(challenger_failures),
            "stamped_at": _now_iso(),
        }
        path = _discovery_receipt_path(market)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(payload, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 — additive; never break write_shadow
        print(
            f"::warning title=board-shadow-receipt-failed::{market}: discovery "
            f"receipt write failed ({exc}) — the surface-freshness vocabulary "
            "sees no update this pass",
            flush=True,
        )


def write_shadow(calls: list[dict], market: str, asof: str | None = None) -> dict:
    """The ONE fail-soft call per market (contract §4). Never raises into a
    build. Deep-copies ``calls`` on entry (F1 defense-in-depth) so nothing
    this module or a registered challenger does can alias or mutate the
    caller's population list — the same object (or anything reachable from
    it) that may still be live on the caller's side feeding the published
    artifact.

    Lane-gated exactly like board_ledger.append_board: HK only under
    asia_advance_enabled(), CA only under nightly_advance_enabled(); an
    import failure is off-lane, fail-closed.

    The registry-state ladder is FOUR mutually distinguishable POST-GATE
    states (F16 + the 2026-08-21 market-scope correction) — reached only
    once the market/asof/lane pre-gate checks above have already passed (the
    pre-gate states ``unsupported_market`` / ``no_asof`` / ``off_lane``, and
    the even-earlier reentrancy state below, are unchanged and are not part
    of this four-way ladder): an on-lane pass against a globally EMPTY
    registry logs ``registry_state=no_challenger_registered`` (an empty
    store must be distinguishable from a broken writer); a registry that
    holds registrations but NONE for this call's market logs
    ``registry_state=no_challenger_for_market`` (a foreign-market
    registration must never be silently treated as this market's own — the
    defect this correction repairs); a market with registrations logs
    ``registry_state=wrote_n_rows n=<n>`` (n=0 is a lawful successful
    zero-row challenger pass, e.g. every registered rank_fn/discovery_fn
    yielding nothing this session); and a SUBSTRATE-level exception path
    (e.g. :func:`_read_incumbent_positions` itself exploding, never a single
    challenger raising — see the per-registration guard below) logs
    ``registry_state=error``.

    D2(a) reentrancy: a call arriving while another write_shadow call is
    already active anywhere on the call stack (for EITHER market — the guard
    is not market-scoped, because the isolation it repairs is against
    cross-market re-entry specifically) is refused fail-soft with
    ``registry_state=reentrant_refused`` before any other check runs. This
    closes the shape a TRUSTED-but-reviewed registered challenger could
    otherwise take: calling ``write_shadow`` for the other market from
    inside its own ``rank_fn``/``discovery_fn`` mid-pass. See the contract's
    trust-boundary note (§4) — the registry is not a defense against a
    hostile registered challenger, only against mis-laning a well-behaved
    one; this guard closes the one concrete reentrant shape identified, not
    every conceivable hostile action a reviewed challenger could take.

    D7 semantics: one registered challenger raising (inside its own
    ``rank_fn``/``discovery_fn`` call, or inside that registration's own lane
    write) is caught by a PER-REGISTRATION try/except and logged as
    ``challenger_failed definition=<d>`` — it does NOT flip the whole pass to
    ``error``; the remaining registrations still run, and the pass concludes
    ``wrote_n_rows n=<n>`` reflecting the TRUE accumulated count from every
    registration that did succeed. ``error`` is reserved for a failure below
    that per-registration boundary (the substrate read, or anything else in
    this function's own control flow) — the outer except is a backstop, not
    the normal path for a misbehaving challenger.
    """
    global _WRITE_SHADOW_ACTIVE
    if _WRITE_SHADOW_ACTIVE:
        log.warning(
            "board_shadow(%s): reentrant write_shadow call refused — a "
            "challenger called write_shadow again while a pass was already "
            "in progress", market,
        )
        return {"written": 0, "registry_state": "reentrant_refused"}

    _WRITE_SHADOW_ACTIVE = True
    try:
        market = str(market or "").upper()
        if market not in MARKETS:
            log.info("board_shadow: unsupported market %r — no-op", market)
            return {"written": 0, "registry_state": "unsupported_market"}
        if not asof:
            log.info("board_shadow(%s): no asof — no-op", market)
            return {"written": 0, "registry_state": "no_asof"}

        try:
            from engine.ledger_lane import asia_advance_enabled, nightly_advance_enabled  # noqa: PLC0415
            if market == "HK" and not asia_advance_enabled():
                log.info("board_shadow(HK): off-lane (CN_LANE != asia) — skip write")
                return {"written": 0, "registry_state": "off_lane"}
            if market == "CA" and not nightly_advance_enabled():
                log.info("board_shadow(CA): off-lane (COLLECT_LANE != nightly) — skip write")
                return {"written": 0, "registry_state": "off_lane"}
        except Exception as exc:  # noqa: BLE001 — fail-closed, matching board_ledger
            log.warning("board_shadow(%s): ledger_lane import failed (%s) — off-lane", market, exc)
            return {"written": 0, "registry_state": "off_lane"}

        # F1: deep-copy the population input on entry. Nothing below this
        # line ever touches the caller's original `calls` object again.
        calls_copy = copy.deepcopy(list(calls or []))
        total = 0

        try:
            if not CHALLENGER_REGISTRY:
                log.info("board_shadow(%s): registry_state=no_challenger_registered", market)
                return {"written": 0, "registry_state": "no_challenger_registered"}

            market_registrations = _registrations_for(market)
            if not market_registrations:
                log.info("board_shadow(%s): registry_state=no_challenger_for_market", market)
                return {"written": 0, "registry_state": "no_challenger_for_market"}

            # hk-discovery wave: threaded into the receipt below (both the
            # success and error paths) without changing D7 semantics — a
            # per-registration failure is still caught here and the pass
            # still concludes wrote_n_rows n=<true total>; the receipt
            # simply also NAMES the failures.
            challenger_failures: list[dict[str, str]] = []
            incumbent_positions = _read_incumbent_positions(market, str(asof))
            for definition, spec in market_registrations:
                rank_fn = spec.get("rank_fn")
                discovery_fn = spec.get("discovery_fn")
                try:
                    if rank_fn is not None:
                        total += _write_lane_a(
                            market, str(asof), calls_copy, definition, rank_fn, incumbent_positions,
                            failures=challenger_failures,
                        )
                    if discovery_fn is not None:
                        total += _write_lane_b(
                            market, str(asof), definition, discovery_fn,
                            failures=challenger_failures,
                        )
                except Exception as exc:  # noqa: BLE001 — D7: one registration's
                    # failure must never mute the rest of the pass, and must
                    # never be reported as the whole pass erroring.
                    log.warning(
                        "board_shadow(%s): challenger_failed definition=%s (%s)",
                        market, definition, exc,
                    )
                    challenger_failures.append({"definition": definition, "error": str(exc)})
                    continue
            state = f"wrote_n_rows n={total}"
            log.info("board_shadow(%s): registry_state=%s", market, state)
            _write_discovery_receipt(
                market, str(asof), state, total, market_registrations, challenger_failures,
            )
            return {"written": total, "registry_state": state}
        except Exception as exc:  # noqa: BLE001 — fail-soft backstop: a
            # SUBSTRATE-level failure (never a single challenger raising —
            # that is caught above) still must never break the build. Return
            # the true accumulated `total` written so far, not a hardcoded 0.
            log.warning(
                "board_shadow(%s): write_shadow failed (%s) — registry_state=error",
                market, exc,
            )
            try:
                # Receipt owed on the error path too (contract), but ONLY
                # when this market actually had a registration — a
                # substrate failure before that point (e.g. the
                # CHALLENGER_REGISTRY/market pre-gates above) must not mint
                # a receipt for a market with nothing registered.
                _error_registrations = _registrations_for(market)
                if _error_registrations:
                    _write_discovery_receipt(
                        market, str(asof), "error", total, _error_registrations,
                        challenger_failures if "challenger_failures" in locals() else [],
                    )
            except Exception:  # noqa: BLE001 — receipt is best-effort even here
                pass
            return {"written": total, "registry_state": "error"}
    finally:
        _WRITE_SHADOW_ACTIVE = False


# ---------------------------------------------------------------------------
# Cross-store validator (contract §6, F15) — the compensating invariant for
# choosing a separately-keyed Lane A over the paired-row DEC's default shape.
# ---------------------------------------------------------------------------
def validate_lane_a_against_board_ledger(market: str) -> list[str]:
    """Every Lane-A (date, ticker) must exist in board_ledger with matching
    board_pos and board_definition. Returns a list of human-readable
    violation strings (empty = clean)."""
    market = market.upper()
    lane_a = _read_own_store(_lane_a_path(market))
    if lane_a is None or lane_a.empty:
        return []
    board = _read_board_parquet(market, ["date", "ticker", "board_pos", "board_definition"])
    if board is None:
        return [f"{market}: board_ledger store absent but Lane A has {len(lane_a)} row(s)"]
    board_idx = {
        (str(r.date), str(r.ticker)): (r.board_pos, _definition_or_none(r.board_definition))
        for r in board.itertuples()
    }
    violations: list[str] = []
    for row in lane_a.itertuples():
        key = (str(row.date), str(row.ticker))
        if key not in board_idx:
            violations.append(f"{market}: Lane A {key} has no board_ledger row")
            continue
        board_pos, board_def = board_idx[key]
        if row.incumbent_rank is not None and board_pos is not None and int(row.incumbent_rank) != int(board_pos):
            violations.append(
                f"{market}: Lane A {key} incumbent_rank={row.incumbent_rank} != "
                f"board_ledger board_pos={board_pos}"
            )
        if _definition_or_none(row.incumbent_definition) != board_def:
            violations.append(
                f"{market}: Lane A {key} incumbent_definition={row.incumbent_definition!r} != "
                f"board_ledger board_definition={board_def!r}"
            )
    return violations


def validate_population_identities(market: str) -> list[str]:
    """K10 (F8): population_n must equal the row count for that
    (date, market, challenger_definition) key, and challenger_coverage must
    reproduce from the stored columns — the incumbent minted population is
    the ONLY lawful denominator."""
    market = market.upper()
    lane_a = _read_own_store(_lane_a_path(market))
    if lane_a is None or lane_a.empty:
        return []
    violations: list[str] = []
    for (date, definition), group in lane_a.groupby(["date", "challenger_definition"]):
        n = len(group)
        pop_values = set(group["population_n"].dropna().astype(int))
        if pop_values and pop_values != {n}:
            violations.append(
                f"{market}: population_n {sorted(pop_values)} != row count {n} "
                f"for (date={date}, challenger_definition={definition})"
            )
        scored = int(group["challenger_rank"].notna().sum())
        for _, row in group.iterrows():
            if row.get("population_n") in (None, 0) or pd.isna(row.get("population_n")):
                continue
            expected = round(scored / int(row["population_n"]), 6)
            actual = row.get("challenger_coverage")
            if actual is not None and not pd.isna(actual) and round(float(actual), 6) != expected:
                violations.append(
                    f"{market}: challenger_coverage={actual} != {expected} "
                    f"(scored={scored}, population_n={row['population_n']}) "
                    f"for (date={date}, challenger_definition={definition})"
                )
    return violations
