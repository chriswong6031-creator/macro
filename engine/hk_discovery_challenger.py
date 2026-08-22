"""HK Lane-B discovery challenger — ``hk_discovery_v1`` (WS:PROPHET-HK-CA-REVAMP).

research/PROPHET_SHADOW_CONTRACT_V1.md §3 is the binding storage/isolation
contract; this module is the FIRST real registrant against the market-scoped
registry engine/board_shadow.py ships empty. It answers one question only:
"was this opportunity visible to the research system before it won?" — it is
NOT a ranking model, picks no winner, and computes no outcome.

MARKET-FREE BY CONSTRUCTION (K-D6): this module never takes, infers, or reads
a market. There is no market parameter anywhere in its public surface, no
environment-variable read, and no other-market token. Market ownership lives
ONLY at the registration call site (``scripts/build_hk_library.py``, which
binds this module's :data:`DEFINITION` to the literal HK market when calling
``engine.board_shadow.register_challenger``). A future second-market
registrant is a SEPARATE module registered separately — never a branch added
here.

PUBLICATION-INDEPENDENT (K-D2 / K-D9): :func:`build_candidates` consumes an
explicit ``evidence`` bundle assembled by the caller from pre-cut structures
the nightly build already computes — never board rank, never the composite
selection score's order, never which names the display board flagged for
extra attention, and never the published board artifact itself. Any of
those fields riding along in the evidence bundle (a caller's fixture is free
to include them) are simply not read by anything below — this module's
source names none of them, checked by a repo-wide source fence
(tests/test_hk_discovery_challenger.py K-D2).

ORIGIN PREDICATES (fixed canonical order — the "+"-joined
``candidate_origin`` token on every candidate row lists whichever of these
fired, always in this order):

  a. washout_reclaim   — the 2W washout/reclaim state map (``_tf_state`` on a
                         2W-FRI resample of the close panel; the SAME
                         pre-cut structure scripts/build_hk_library.py
                         already computes at ~L1328-1336, keyed by
                         ``stoch_cross_up``).
  b. leadership        — engine.hk_leadership.compute()'s own per-member
                         ``above_rising_ma10`` read, gated on the organ's own
                         ``leaders_participating`` state (the fixed mega-cap
                         cohort's population limitation is honest — this
                         module never extends the cohort).
  c. ripening          — membership in the UNCAPPED population underlying
                         engine.hk_board_rank.build_ripening_rows (the
                         caller calls that exact function a second time with
                         an expanded cap so the classifier logic is never
                         duplicated here).
  d. aged_turn         — engine.hk_board_rank.ran_admits(), called directly:
                         the UNCAPPED admission predicate underlying
                         build_ran_rows (the anchor/close-series machinery
                         build_ran_rows also does is a DISPLAY concern —
                         "can this row show an age" — not an admission
                         concern, so calling the predicate directly reaches
                         the true uncapped population).
  e. blocked_signal    — engine.hk_board_rank.veto_admits(), called
                         directly: the UNCAPPED admission predicate
                         underlying build_vetoed_rows, carrying the
                         deterministic veto reason as a sub-token, e.g.
                         ``blocked_signal(counter_trend_no_200_reclaim_hold)``.
                         Bounded by the SAME staleness measure
                         build_vetoed_rows applies (VETOED_MAX_SESSIONS, via
                         the shared engine.hk_board_rank.veto_sessions_since()
                         helper — build commission R2/F2): a veto older than
                         that bound does not fire here either. Unknown age
                         (no marker date and no fresh_bars) still fires —
                         only a KNOWN-stale veto is excluded, never an
                         unknown one.
  f. hk_native_onset   — engine.hk_southbound_stocks.signal()'s own
                         ``label == "accumulating"`` read, sub-token
                         ``hk_native_onset(southbound)``.
  g. ah_dislocation    — engine.hk_stock_signals.ah_value_signal()'s own
                         ``cheap`` read, for names WITH a resolvable A/H
                         twin only (a name absent from that map fires
                         nothing and receives no fabricated zero — K-D3).

CAP LAW: (c)/(d)/(e) reach the UNCAPPED population — either by calling the
production predicate directly (no cap parameter exists on ``ran_admits``/
``veto_admits`` at all) or by calling the production builder a second time
with an expanded ``cap=``/``ready_cap=`` (ripening), never by re-implementing
any of that logic here.

AVAILABILITY: an INDEPENDENT read (never fed by, and never feeding, the
origin predicates above) over the frozen enum {ENTRY_OPEN, WAIT_PULLBACK,
WAIT_CONFLUENCE, RAN_DONT_CHASE, RIGHTS_BLOCKED, UNAVAILABLE_DATA}, via the
fixed, fail-closed precedence ladder in :func:`_availability`.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

#: The registered challenger definition — bound to the HK market ONLY at the
#: registration call site (scripts/build_hk_library.py). This module never
#: reads or decides market membership itself.
DEFINITION = "hk_discovery_v1"

# ---------------------------------------------------------------------------
# Pinned per-origin state tokens (frozen; a module edit elsewhere may add
# tokens, but these are the ones this challenger reads directly).
#
# Origin (a) washout_reclaim has NO constant here (build commission R9/F12):
# this module reads the ALREADY-RESOLVED per-ticker boolean from
# evidence["washout_2w"] (see :func:`_fires_washout_reclaim`) — the raw
# ``stoch_cross_up`` key on the 2W ``_tf_state`` map is read and resolved to
# that boolean by scripts/build_hk_library.py (~L1328-1336, the module
# docstring's origin (a) note above), never by this module. A
# WASHOUT_RECLAIM_FLAG_KEY constant here previously claimed this module read
# that raw key directly — it never did, and was dead code.
# ---------------------------------------------------------------------------
# Origin (b): the one organ-level state this challenger treats as "leadership
# fired" — the mega-cap cohort's own thrust label.
LEADERSHIP_FIRE_STATE = "leaders_participating"

# Origin (f): the southbound per-name label this challenger treats as onset.
SOUTHBOUND_ONSET_LABEL = "accumulating"

# ---------------------------------------------------------------------------
# Availability enum (frozen)
# ---------------------------------------------------------------------------
ENTRY_OPEN = "ENTRY_OPEN"
WAIT_PULLBACK = "WAIT_PULLBACK"
WAIT_CONFLUENCE = "WAIT_CONFLUENCE"
RAN_DONT_CHASE = "RAN_DONT_CHASE"
RIGHTS_BLOCKED = "RIGHTS_BLOCKED"
UNAVAILABLE_DATA = "UNAVAILABLE_DATA"

_ORIGIN_ORDER = (
    "washout_reclaim", "leadership", "ripening", "aged_turn",
    "blocked_signal", "hk_native_onset", "ah_dislocation",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: Any) -> str:
    """Deterministic lower_snake_case token for a raw reason string."""
    cleaned = _SLUG_RE.sub("_", str(text or "").strip().lower()).strip("_")
    return cleaned or "unknown"


# ---------------------------------------------------------------------------
# Origin predicates — each reads ONLY its own evidence key(s), never the
# incumbent board's rank/order/flag fields.
# ---------------------------------------------------------------------------
def _fires_washout_reclaim(ticker: str, evidence: Mapping[str, Any]) -> bool:
    washout_2w = evidence.get("washout_2w") or {}
    return bool(washout_2w.get(ticker))


def _fires_leadership(ticker: str, evidence: Mapping[str, Any]) -> bool:
    leadership = evidence.get("leadership") or {}
    if leadership.get("state") != LEADERSHIP_FIRE_STATE:
        return False
    for member in leadership.get("members") or ():
        if str(member.get("ticker")) == ticker:
            return bool(member.get("above_rising_ma10"))
    return False


def _fires_ripening(ticker: str, evidence: Mapping[str, Any]) -> bool:
    return ticker in (evidence.get("ripening_tickers") or ())


def _fires_aged_turn(ticker: str, evidence: Mapping[str, Any]) -> bool:
    from engine import hk_board_rank  # local import — see module docstring

    verdict = (evidence.get("sig_verdict") or {}).get(ticker)
    if verdict is None:
        return False
    row = {"dir": (evidence.get("dir_by_ticker") or {}).get(ticker)}
    return hk_board_rank.ran_admits(
        verdict, row,
        require_above200=bool(evidence.get("ran_require_above200", True)),
    )


def _fires_blocked_signal(ticker: str, evidence: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Build commission R2 (F2): applies the SAME staleness bound the display
    builder does (``engine.hk_board_rank.build_vetoed_rows``,
    ``VETOED_MAX_SESSIONS``) via the shared ``veto_sessions_since()`` helper —
    never a second, independently maintained copy of that computation. A veto
    whose age is KNOWN and exceeds the bound does not fire; an UNKNOWN age
    (no marker date and no fresh_bars) still fires, matching the display
    lane's own conditional (``sessions is not None and sessions > bound``)."""
    from engine import hk_board_rank  # local import — see module docstring

    verdict = (evidence.get("sig_verdict") or {}).get(ticker)
    if verdict is None:
        return False, None
    row = {"dir": (evidence.get("dir_by_ticker") or {}).get(ticker)}
    if not hk_board_rank.veto_admits(verdict, row):
        return False, None
    sessions = hk_board_rank.veto_sessions_since(verdict, ticker)
    if sessions is not None and sessions > hk_board_rank.VETOED_MAX_SESSIONS:
        return False, None
    reason = ((verdict or {}).get("last") or {}).get("reason")
    return True, _slug(reason)


def _fires_hk_native_onset(ticker: str, evidence: Mapping[str, Any]) -> bool:
    southbound = evidence.get("southbound") or {}
    entry = southbound.get(ticker) or {}
    return entry.get("label") == SOUTHBOUND_ONSET_LABEL


def _fires_ah_dislocation(ticker: str, evidence: Mapping[str, Any]) -> bool:
    ah_value = evidence.get("ah_value") or {}
    entry = ah_value.get(ticker)
    if entry is None:
        return False               # no resolvable twin — never a fabricated zero (K-D3)
    return bool(entry.get("cheap"))


def _candidate_universe(evidence: Mapping[str, Any]) -> list[str]:
    """Every ticker any origin evidence map even MENTIONS — a name with zero
    firing origins never becomes a row (checked in :func:`build_candidates`),
    so scanning a superset here costs nothing but a dict lookup per name.

    DETERMINISM (build commission R5/F5): the output order follows first-seen
    insertion order across the evidence maps scanned below. Every one of
    those is a ``dict`` (whose iteration order is insertion-stable) EXCEPT
    ``ripening_tickers``, which the caller must supply as a SORTED sequence,
    never a raw ``set`` — Python's set iteration order is not stable across
    process runs (hash randomisation), so a raw set here would make row
    order silently depend on the interpreter's hash seed. Asserted below
    rather than merely documented, so a caller regression fails loudly."""
    ripening = evidence.get("ripening_tickers") or ()
    assert not isinstance(ripening, (set, frozenset)), (
        "evidence['ripening_tickers'] must be a sorted list/tuple, never a "
        "raw set — set iteration order is not stable across process runs "
        "(R5/F5); sort it at the bundle-assembly call site before handing "
        "it to build_candidates()"
    )

    seen: dict[str, None] = {}

    def _add(keys) -> None:
        for key in keys:
            if key is None:
                continue
            text = str(key)
            if text and text not in seen:
                seen[text] = None

    _add((evidence.get("washout_2w") or {}).keys())
    _add(str(m.get("ticker")) for m in (evidence.get("leadership") or {}).get("members") or ()
         if m.get("ticker"))
    _add(ripening)
    _add((evidence.get("sig_verdict") or {}).keys())
    _add((evidence.get("southbound") or {}).keys())
    _add((evidence.get("ah_value") or {}).keys())
    return list(seen.keys())


# ---------------------------------------------------------------------------
# Availability — independent of the origin predicates above (frozen ladder)
# ---------------------------------------------------------------------------
def _availability(ticker: str, evidence: Mapping[str, Any]) -> tuple[str, str]:
    """Build commission R4 (F4): ``knife_available``/``extension_available``
    close the missing-vs-False collapse the same way ``plc_available``
    already does — a name that would otherwise reach ``ENTRY_OPEN`` while the
    knife or extension READ never ran this pass gets ``UNAVAILABLE_DATA``
    instead of a silent pass-through. Per-name absence WITHIN an available
    map (the ordinary case — a name simply is not knife-risk / not extended)
    stays a genuine ``False`` and is unaffected; only the WHOLE-map-absent
    case (mirrors ``plc_available``'s own shape) is caught here. Both flags
    default to available (``True``) when the caller's evidence bundle omits
    them at all, matching every fixture/test that never set them."""
    sig_verdict = evidence.get("sig_verdict") or {}
    verdict = sig_verdict.get(ticker)
    if verdict is None:
        return UNAVAILABLE_DATA, "missing_inputs(gate_verdict)"

    plc_map = evidence.get("plc_map") or {}
    if plc_map.get(ticker):
        return RIGHTS_BLOCKED, "placement_flags"

    knife_map = evidence.get("knife_risk") or {}
    if bool(knife_map.get(ticker)):
        return WAIT_PULLBACK, "knife_read"

    extended_map = evidence.get("extended") or {}
    if bool(extended_map.get(ticker)):
        return RAN_DONT_CHASE, "extension_read"

    eligible = bool((verdict or {}).get("eligible"))
    if not eligible:
        return WAIT_CONFLUENCE, "hk_signal_gate"

    plc_available = bool(evidence.get("plc_available", True))
    if not plc_available:
        return UNAVAILABLE_DATA, "placement_gate_unavailable"

    knife_available = bool(evidence.get("knife_available", True))
    if not knife_available:
        return UNAVAILABLE_DATA, "knife_read_unavailable"

    extension_available = bool(evidence.get("extension_available", True))
    if not extension_available:
        return UNAVAILABLE_DATA, "extension_read_unavailable"

    return ENTRY_OPEN, "hk_signal_gate"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_candidates(evidence: Mapping[str, Any] | None, asof: str) -> list[dict]:
    """Pure candidate builder — no market, no env read, no published-artifact
    read. One raw row per name with ≥1 firing origin; a name with zero firing
    origins is not a candidate and gets no row."""
    evidence = evidence or {}
    rows: list[dict] = []
    for raw_ticker in _candidate_universe(evidence):
        origins: list[str] = []
        if _fires_washout_reclaim(raw_ticker, evidence):
            origins.append("washout_reclaim")
        if _fires_leadership(raw_ticker, evidence):
            origins.append("leadership")
        if _fires_ripening(raw_ticker, evidence):
            origins.append("ripening")
        if _fires_aged_turn(raw_ticker, evidence):
            origins.append("aged_turn")
        fired_blocked, reason_slug = _fires_blocked_signal(raw_ticker, evidence)
        if fired_blocked:
            origins.append(f"blocked_signal({reason_slug})")
        if _fires_hk_native_onset(raw_ticker, evidence):
            origins.append("hk_native_onset(southbound)")
        if _fires_ah_dislocation(raw_ticker, evidence):
            origins.append("ah_dislocation")
        if not origins:
            continue

        status, source = _availability(raw_ticker, evidence)
        rows.append({
            "session_date": str(asof),
            "security_ref_raw": raw_ticker,
            "candidate_origin": "+".join(origins),
            "availability_status": status,
            "availability_source": source,
        })
    return rows
