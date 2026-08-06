"""Macro Thesis Ledger — a point-in-time register of operator macro conviction,
graded at fixed horizons to build a track record OF SYNTHESIS.

TIER: ops/journal.  **ZERO AUTHORITY.**
    This module never scores, ranks, gates, sizes, vetoes, or tilts ANY product
    surface.  Nothing here is read by a signal engine, a board builder, a ranker,
    an allocator, or a render lane.  It is a track record *of* judgment, never a
    signal *into* the system.  A thesis recorded here carries exactly as much
    authority as a diary entry: none.  If a future wave wants any of this to
    inform a shipped number, that is a PROMOTION and it goes through the normal
    pre-registration + gauntlet gate (CLAUDE.md §Epistemics) — not through an
    import of this module.

GRAIN (why this is not a duplicate of anything already built):
    Trade Memory (`admin/trade_memory.py`, `engine/neuralweb/trade_memory.py`) is
    PER-TRADE, per-ticker, private, Supabase-backed: "I bought JNJ, here is how it
    went".  The Long-Hold departments are per-stock.  The "Thesis lobe" killed by
    the NW next-lobes adjudication (#1666/#1669/#1671) and re-affirmed by
    `research/PROPHET_TRADE_MEMORY_MASTERPLAN_2026-07-28.md` was explicitly "a
    duplicate PER-STOCK thesis store".

    This ledger is none of those.  Its unit is one MULTIVARIABLE MACRO THESIS —
    several planes (rates / fx / commodities / policy events / CN sector cycle /
    flow / narrative) combined into one directional call spanning SEVERAL
    instruments at once.  A macro synthesis is not a stock thesis, and it has
    never had a home: it was made in chat, in the operator's head, and it was
    never gradeable afterwards.  That is the gap this closes.

STORE:
    ``data/macro_thesis/ledger.jsonl`` — append-only, one JSON object per line.
    ``thesis_id`` = ``<title-slug>-<registered_at>``.  KEEP-FIRST: registering an
    id that already exists is a no-op that reports the incumbent.  Rows are NEVER
    edited in place; a revision is a NEW row whose ``amended_from`` names the row
    it supersedes.  The file is committed to git on purpose — a conviction
    register whose history can be quietly rewritten records nothing.

    This is NOT a nightly-advanced forward ledger, so `engine.ledger_lane` does
    not apply: rows are written only by an explicit operator/admin registration,
    and :func:`grade` is a PURE READ that computes grades on the fly and writes
    nothing.  There is no lane that can silently advance this file.

FORWARD / RETRO FIREWALL (hard, enforced by raise):
    ``entry_class="forward"`` rows were registered BEFORE the outcome was known.
    ``entry_class="retro"`` rows are historical episodes written up AFTER the fact
    for training/calibration; they REQUIRE ``event_period``, a mandatory
    ``hindsight_risk`` disclosure, and ``sources``.

    Retro rows are curated *because* they are legible in hindsight, so their hit
    rate is meaningless as a track record and pooling them with forward rows would
    manufacture a flattering, entirely fake number.  :func:`grade` therefore
    returns them in SEPARATE top-level sections and :func:`summarize` RAISES
    :class:`MacroThesisFirewallError` on a mixed batch.  The firewall is a raise,
    not a convention, because a convention is what gets forgotten at 2am.

GRADING:
    Entry anchor = the first close ON OR AFTER ``registered_at`` (for retro rows,
    on or after ``event_period.from``).  Returns are measured at H=21 and H=63
    SESSIONS from that anchor, plus an always-available mark-to-latest interim.
    EXCESS is computed against each instrument's named benchmark over the SAME
    CALENDAR WINDOW (both legs snapped by date, so a CN instrument vs a US
    benchmark stays honest across mismatched trading calendars).  A benchmark of
    ``"absolute"`` means the raw return is the number and excess is null by design.
    Thesis-level rollup = MEDIAN across that thesis's instruments.

    NOTE — this anchor convention DIFFERS from `engine.grading.forward_metrics`,
    which is the validated NEXT-BAR fill used for SIGNAL grading (entry = the bar
    strictly AFTER the signal bar, and its date snap looks BACKWARD to the last bar
    on-or-before).  That convention exists to keep a *signal* free of look-ahead.
    This ledger is not a signal: a thesis is written by a human at a moment, and
    the honest anchor is the first price they could actually have transacted at on
    or after that moment — never a print from BEFORE they wrote it, which is what a
    backward snap would hand them on a weekend registration.  The two conventions
    coincide on a weekday registration and must not be conflated: numbers from this
    module are journal numbers and are never gauntlet-grade signal evidence.

    A series that resolves nowhere is a DISCLOSED NULL (``resolution: "unresolved"``
    with a reason), never a crash and never a silent zero.

NEURAL WEB HOOK (documentation only — no brain code ships in this module):
    Each leg may carry a ``state_ref``: {artifact, key, observed} naming the
    in-house artifact + key path that HELD that state at registration, together
    with the literal value read at that moment.  That triple is what makes this
    ledger a future TRAINING TARGET rather than prose:

      1. RECONSTRUCT — the state_refs pin the machine-visible frame at time T.
         Replaying those artifacts at T gives the brain the same inputs the
         operator had, with no leakage from after T.
      2. PREDICT — the brain, given only that frame, proposes its own direction,
         horizon, and instrument set.
      3. SCORE — the brain's proposal is scored twice: against the REGISTERED
         thesis (did it reach the same synthesis a human did?) and against the
         GRADED OUTCOME (was the synthesis right?).  Those are different
         questions and both are informative — agreeing with a human who was
         wrong is not success.
      4. CALIBRATE — legs marked ``leg_kind="judgment"`` with a null state_ref are
         precisely the planes the machine CANNOT yet see.  The running count of
         judgment-vs-calibrated legs is therefore a standing work-list of which
         planes to wire next, ranked by how often operator conviction leans on
         something no artifact records.

    Until such a wave is pre-registered and gauntleted, the brain's role here is
    strictly de-escalation and read-back; per constitution A7 an LLM never
    originates a signal, a score, or an escalation from this ledger.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

import pandas as pd

# `lib.config` / `lib.store` are imported INSIDE the three functions that use them
# (_ledger_path, _close_series, _basket_members), never at module level. The admin
# panel import-caches this module, so a module-level import would pull lib/config.py
# and lib/store.py into the admin LOAD-TIME closure — and
# tests/test_deploy_update_self_heal.py then demands both be added to the admin
# restart regex in app/deploy/update.sh, which directly contradicts
# test_non_admin_path_does_not_trigger_admin_restart[lib/config.py]. Deferring keeps
# the admin restart surface to this file alone and satisfies both guards. Neither name
# is referenced at module level, so nothing else changes.

# ── contract ──────────────────────────────────────────────────────────────────

LEDGER_DIR = "macro_thesis"
LEDGER_FILE = "ledger.jsonl"
SCHEMA = "macro_thesis.v1"

DEFAULT_HORIZONS: tuple[int, ...] = (21, 63)

PLANES = frozenset({
    "rates", "fx", "commodities", "policy_event",
    "cn_sector_cycle", "flow", "narrative", "other",
})
DIRECTIONS = frozenset({"long", "short", "rotate"})
AUTHORS = frozenset({"operator", "brain", "retro-curator"})
LEG_KINDS = frozenset({"calibrated", "judgment"})
ENTRY_CLASSES = frozenset({"forward", "retro"})

STATUS_ACCRUING = "accruing"
STATUS_INTERIM = "interim"
STATUS_GRADED_21 = "graded_21"
STATUS_GRADED_63 = "graded_63"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SERIES_RE = re.compile(r"^[A-Za-z0-9._^=-]{1,32}$")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")

# Ticker-suffix → store groups, most specific first.  Mirrors the proven
# `(china_stocks, china)` fallback in engine/china_standout_track.py — names live
# in the per-name OHLC group, ETFs/indices in the curated group.
_GROUPS_CN = ("china_stocks", "china")
_GROUPS_HK = ("hk_stocks", "hk")
_GROUPS_US = ("yahoo", "stocks")
_GROUPS_ALL = _GROUPS_CN + _GROUPS_HK + _GROUPS_US

_BASKET_MEMBERSHIP = ("baskets_china", "membership.json")


class MacroThesisFirewallError(ValueError):
    """Raised when forward and retro records would be pooled into one statistic.

    Deliberately its own type: a bare ValueError would be swallowed by any test
    that merely asserts "something went wrong", and this failure has to name
    itself so the guard pins the defect rather than the wording.
    """


# ── ledger I/O ────────────────────────────────────────────────────────────────

def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config, store  # deferred: see the note at the import block
    root = data_root if data_root is not None else config.data_dir()
    p = root / LEDGER_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict[str, Any]]:
    """Every row in registration order.  Unparseable lines are skipped, not fatal."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def slugify(text: str) -> str:
    slug = _SLUG_STRIP_RE.sub("-", str(text).strip().lower()).strip("-")
    return slug[:60] or "thesis"


def thesis_id(title: str, registered_at: str) -> str:
    """``<title-slug>-<registered_at>`` — stable, human-readable, collision-loud."""
    return f"{slugify(title)}-{registered_at}"


# ── validation ────────────────────────────────────────────────────────────────

def _text(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return text


def _date(value: Any, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not _DATE_RE.fullmatch(text):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        pd.Timestamp(text)
    except ValueError as exc:
        raise ValueError(f"{field} is not a real date") from exc
    return text


def _one_of(value: Any, field: str, allowed: frozenset[str], default: str | None = None) -> str:
    text = str(value or default or "").strip().lower()
    if text not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return text


def _normalize_state_ref(raw: Any, index: int) -> dict[str, Any] | None:
    """A leg's machine-readable pointer, or None for a pure-judgment leg.

    ``observed`` is the literal value the artifact held at registration.  Storing
    it is the whole point: without it the row says only "look at this key", and
    the key will have moved on by the time anyone grades the thesis.
    """
    if raw in (None, "", {}):
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"legs[{index}].state_ref must be an object or null")
    artifact = _text(raw.get("artifact"), f"legs[{index}].state_ref.artifact", 240, required=True)
    key = _text(raw.get("key"), f"legs[{index}].state_ref.key", 240, required=True)
    ref: dict[str, Any] = {"artifact": artifact, "key": key}
    if "observed" in raw:
        ref["observed"] = raw.get("observed")
    return ref


def _normalize_leg(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"legs[{index}] must be an object")
    plane = _one_of(raw.get("plane"), f"legs[{index}].plane", PLANES, "other")
    claim = _text(raw.get("claim"), f"legs[{index}].claim", 2000, required=True)
    state_ref = _normalize_state_ref(raw.get("state_ref"), index)
    leg_kind = _one_of(
        raw.get("leg_kind"), f"legs[{index}].leg_kind", LEG_KINDS,
        "calibrated" if state_ref else "judgment",
    )
    # A calibrated leg with no pointer is the exact shape that lets an unwired
    # plane masquerade as a measured one.  Refuse it.
    if leg_kind == "calibrated" and state_ref is None:
        raise ValueError(
            f"legs[{index}]: leg_kind='calibrated' requires a state_ref "
            "(artifact + key); use leg_kind='judgment' for an unwired plane"
        )
    return {"plane": plane, "claim": claim, "state_ref": state_ref, "leg_kind": leg_kind}


def _normalize_instrument(raw: Any, index: int) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"instruments[{index}] must be an object")
    series = _text(raw.get("series"), f"instruments[{index}].series", 32, required=True)
    if not _SERIES_RE.fullmatch(series):
        raise ValueError(
            f"instruments[{index}].series must be a ticker or basket id "
            "(letters, digits, dot, dash, underscore, caret)"
        )
    benchmark = _text(raw.get("benchmark"), f"instruments[{index}].benchmark", 32) or "absolute"
    if benchmark != "absolute" and not _SERIES_RE.fullmatch(benchmark):
        raise ValueError(f"instruments[{index}].benchmark must be a ticker or 'absolute'")
    return {"series": series, "benchmark": benchmark}


def _normalize_event_period(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("retro entries require event_period {from, to}")
    start = _date(raw.get("from"), "event_period.from", required=True)
    end = _date(raw.get("to"), "event_period.to", required=True)
    if end < start:
        raise ValueError("event_period.to cannot be before event_period.from")
    return {"from": start, "to": end}


def normalize_thesis(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize one thesis.  Raises ValueError with a plain reason.

    Hand-rolled rather than jsonschema-driven on purpose: the cross-field rules
    that actually matter here (retro ⇒ hindsight_risk, calibrated ⇒ state_ref)
    are conditionals a flat schema states poorly, and the error text is what an
    operator reads in the admin form.
    """
    if not isinstance(payload, dict):
        raise ValueError("thesis must be an object")

    title = _text(payload.get("title"), "title", 200, required=True)
    registered_at = _date(payload.get("registered_at"), "registered_at", required=True)
    author = _one_of(payload.get("author"), "author", AUTHORS, "operator")
    direction = _one_of(payload.get("direction"), "direction", DIRECTIONS, "long")
    entry_class = _one_of(payload.get("entry_class"), "entry_class", ENTRY_CLASSES, "forward")

    # ABSENT means "use the default"; an explicitly EMPTY list is an error rather
    # than a silent substitution — quietly swapping in a default horizon would
    # overwrite stated operator intent in a register whose whole job is to
    # preserve it.
    horizons_raw = payload.get("horizon_sessions")
    if horizons_raw is None:
        horizons_raw = list(DEFAULT_HORIZONS)
    if not isinstance(horizons_raw, (list, tuple)) or not horizons_raw:
        raise ValueError("horizon_sessions must be a non-empty list of integers")
    horizons: list[int] = []
    for h in horizons_raw:
        if isinstance(h, bool) or not isinstance(h, int):
            raise ValueError("horizon_sessions must be integers")
        if not 1 <= h <= 504:
            raise ValueError("horizon_sessions must be between 1 and 504 sessions")
        horizons.append(h)
    horizons = sorted(set(horizons))

    conviction = payload.get("conviction", 3)
    if isinstance(conviction, bool) or not isinstance(conviction, int):
        raise ValueError("conviction must be an integer 1-5")
    if not 1 <= conviction <= 5:
        raise ValueError("conviction must be between 1 and 5")

    legs_raw = payload.get("legs") or []
    if not isinstance(legs_raw, (list, tuple)) or not legs_raw:
        raise ValueError("legs must be a non-empty list")
    legs = [_normalize_leg(leg, i) for i, leg in enumerate(legs_raw)]

    instruments_raw = payload.get("instruments") or []
    if not isinstance(instruments_raw, (list, tuple)) or not instruments_raw:
        raise ValueError("instruments must be a non-empty list")
    instruments = [_normalize_instrument(x, i) for i, x in enumerate(instruments_raw)]

    thesis: dict[str, Any] = {
        "schema": SCHEMA,
        "thesis_id": thesis_id(title, registered_at),
        "registered_at": registered_at,
        "author": author,
        "title": title,
        "direction": direction,
        "horizon_sessions": horizons,
        "conviction": conviction,
        "legs": legs,
        "instruments": instruments,
        "confirm_watch": _text(payload.get("confirm_watch"), "confirm_watch", 2000),
        "risk_watch": _text(payload.get("risk_watch"), "risk_watch", 2000),
        "entry_class": entry_class,
        "amended_from": _text(payload.get("amended_from"), "amended_from", 200) or None,
    }

    if entry_class == "retro":
        thesis["event_period"] = _normalize_event_period(payload.get("event_period"))
        # Mandatory and non-empty: a retro row without an honest statement of what
        # hindsight bought it is indistinguishable from a forward call.
        thesis["hindsight_risk"] = _text(
            payload.get("hindsight_risk"), "hindsight_risk", 4000, required=True,
        )
        sources = payload.get("sources") or []
        if not isinstance(sources, (list, tuple)) or not sources:
            raise ValueError("retro entries require a non-empty sources list")
        thesis["sources"] = [_text(s, "sources[]", 500, required=True) for s in sources]
    else:
        for forbidden in ("event_period", "hindsight_risk", "sources"):
            if payload.get(forbidden):
                raise ValueError(f"{forbidden} is only valid on a retro entry")

    return thesis


# ── registration ──────────────────────────────────────────────────────────────

def register(payload: dict[str, Any], data_root: Path | None = None) -> dict[str, Any]:
    """Validate and append one thesis.  KEEP-FIRST on ``thesis_id``.

    Re-registering an existing id does NOT overwrite: the incumbent row is the
    record and the caller is told so.  Correcting a thesis means registering a
    new one with ``amended_from`` set — the original stays readable forever,
    because a conviction register that can be edited after the fact records
    nothing worth grading.
    """
    thesis = normalize_thesis(payload)
    tid = thesis["thesis_id"]

    existing = {row.get("thesis_id") for row in load_ledger(data_root)}
    if tid in existing:
        return {"ok": False, "error": f"thesis_id already registered: {tid}", "thesis_id": tid,
                "kept": "first"}

    if thesis.get("amended_from") and thesis["amended_from"] not in existing:
        raise ValueError(f"amended_from names an unknown thesis_id: {thesis['amended_from']}")

    path = _ledger_path(data_root)
    line = json.dumps(thesis, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return {"ok": True, "thesis_id": tid, "thesis": thesis}


# ── series resolution ─────────────────────────────────────────────────────────

def _groups_for(series: str) -> tuple[str, ...]:
    upper = series.upper()
    if upper.endswith((".SS", ".SZ", ".BJ")):
        return _GROUPS_CN
    if upper.endswith(".HK"):
        return _GROUPS_HK
    return _GROUPS_US + _GROUPS_CN + _GROUPS_HK


def _close_series(ticker: str) -> pd.Series | None:
    from lib import config, store  # deferred: see the note at the import block
    for group in _groups_for(ticker):
        df = store.read(group, ticker)
        if df is not None and "close" in df.columns:
            s = pd.to_numeric(df["close"], errors="coerce").dropna()
            s = s[s > 0]
            if not s.empty:
                return s
    return None


def _basket_members(basket_id: str, data_root: Path | None = None) -> list[str]:
    """Member tickers for a curated CN basket, or [] when unknown.

    Basket ids carry a ``b-`` prefix in cross-namespace id-spaces (cycle rows,
    URLs) but are stored BARE in membership.json — accept either spelling.
    """
    from lib import config, store  # deferred: see the note at the import block
    root = data_root if data_root is not None else config.data_dir()
    path = root / _BASKET_MEMBERSHIP[0] / _BASKET_MEMBERSHIP[1]
    if not path.exists():
        return []
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    baskets = blob.get("baskets")
    if not isinstance(baskets, dict):
        return []
    bare = basket_id.removeprefix("b-")
    entry = baskets.get(bare) or baskets.get(basket_id)
    if not isinstance(entry, dict):
        return []
    members = entry.get("members")
    if not isinstance(members, list):
        return []
    return [
        str(m.get("ticker")).strip()
        for m in members
        if isinstance(m, dict) and m.get("ticker") and not m.get("removed")
    ]


def resolve_frame(
    series: str, data_root: Path | None = None,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Resolve a ticker OR curated basket id to an aligned close frame.

    Returns ``(frame, meta)``.  A single ticker yields a one-column frame; a
    basket yields one column per member, inner-joined onto the dates every member
    trades.  Every downstream return is then the mean of per-column ratios, which
    for one column is the plain return and for N columns is the equal-weighted
    return with weights equal AT THE ANCHOR — the honest reading of "equal-weight
    member mean" for a thesis registered at a moment.

    ``frame`` is None when nothing resolves; ``meta['reason']`` says why.  A
    series that resolves nowhere is a disclosed null, never a crash.
    """
    members = _basket_members(series, data_root)
    if members:
        cols: dict[str, pd.Series] = {}
        missing: list[str] = []
        for ticker in members:
            s = _close_series(ticker)
            if s is None:
                missing.append(ticker)
            else:
                cols[ticker] = s
        if not cols:
            return None, {"resolution": "unresolved", "kind": "basket",
                          "reason": f"no member of {series} resolved in any store",
                          "members": members, "missing": missing}
        frame = pd.concat(cols, axis=1, join="inner").dropna(how="any")
        if frame.empty:
            return None, {"resolution": "unresolved", "kind": "basket",
                          "reason": f"members of {series} share no common trading dates",
                          "members": members, "missing": missing}
        return frame, {"resolution": "basket_equal_weight", "kind": "basket",
                       "members": sorted(cols), "missing": missing}

    s = _close_series(series)
    if s is None:
        return None, {"resolution": "unresolved", "kind": "series",
                      "reason": f"{series} not found in any price store and is not a known basket"}
    return s.to_frame(series), {"resolution": "series", "kind": "series"}


# ── window math ───────────────────────────────────────────────────────────────

def anchor_position(index: pd.Index, date: str) -> int | None:
    """Position of the FIRST bar ON OR AFTER ``date``; None when the date is
    beyond the end of the series.

    ``side="left"`` is load-bearing — it is what makes this "on or after".  A
    backward snap would anchor a weekend registration at a price printed BEFORE
    the thesis was written.
    """
    if len(index) == 0:
        return None
    pos = int(index.searchsorted(pd.Timestamp(date), side="left"))
    return pos if pos < len(index) else None


def _ratio_mean(frame: pd.DataFrame, start: int, end: int) -> float | None:
    base = frame.iloc[start]
    tip = frame.iloc[end]
    nan = float("nan")
    ratios = (tip / base).replace([float("inf"), float("-inf")], nan).dropna()
    if ratios.empty:
        return None
    return float(ratios.mean() - 1.0)


def last_position_on_or_before(index: pd.Index, date: str) -> int | None:
    """Position of the LAST bar on or before ``date``; None when it predates history.

    The mirror of :func:`anchor_position`, used to CLOSE a window rather than open
    one — a retro episode's interim must stop inside its event period, not run on
    to today.
    """
    if len(index) == 0:
        return None
    pos = int(index.searchsorted(pd.Timestamp(date), side="right")) - 1
    return pos if pos >= 0 else None


def _return_between_dates(frame: pd.DataFrame, start_date, end_date) -> float | None:
    """Return between two CALENDAR dates, each snapped to the first bar on/after.

    Used for the benchmark leg so a CN instrument measured against a US benchmark
    compares the same wall-clock window rather than the same bar count.
    """
    a = anchor_position(frame.index, str(pd.Timestamp(start_date).date()))
    b = anchor_position(frame.index, str(pd.Timestamp(end_date).date()))
    if a is None or b is None or b <= a:
        return None
    return _ratio_mean(frame, a, b)


def _status_for(elapsed: int, horizons: tuple[int, ...] | list[int]) -> str:
    hs = sorted(horizons)
    long_h = hs[-1]
    short_h = hs[0]
    if elapsed <= 0:
        return STATUS_ACCRUING
    if elapsed >= long_h:
        return STATUS_GRADED_63 if long_h == 63 else f"graded_{long_h}"
    if elapsed >= short_h:
        return STATUS_GRADED_21 if short_h == 21 else f"graded_{short_h}"
    return STATUS_INTERIM


# ── grading ───────────────────────────────────────────────────────────────────

def grade_instrument(
    instrument: dict[str, str],
    anchor_date: str,
    horizons: tuple[int, ...] | list[int],
    data_root: Path | None = None,
    interim_cutoff: str | None = None,
) -> dict[str, Any]:
    """Grade one instrument from ``anchor_date``.  Never raises on bad data.

    ``interim_cutoff`` closes the mark-to-latest window at a date instead of at
    the last available bar.  Retro rows pass their ``event_period.to``: marking a
    bounded historical episode all the way to today measures holding it forever
    afterwards, not the episode, and that number lands on the card as if it were
    the result (the 2024 gold seed read +117% to today vs +28% over its actual
    window).  Fixed horizons are unaffected — H21/H63 are defined from the anchor.
    """
    series = instrument["series"]
    benchmark = instrument.get("benchmark") or "absolute"
    out: dict[str, Any] = {
        "series": series,
        "benchmark": benchmark,
        "resolution": "unresolved",
        "anchor_date": None,
        "anchor_price": None,
        "sessions_elapsed": 0,
        "status": STATUS_ACCRUING,
        "returns": {},
        "excess": {},
        "interim": None,
        "interim_excess": None,
        "interim_date": None,
    }

    frame, meta = resolve_frame(series, data_root)
    out.update({k: v for k, v in meta.items() if k != "reason"})
    if frame is None:
        out["resolution"] = "unresolved"
        out["reason"] = meta.get("reason", "unresolved")
        return out

    a = anchor_position(frame.index, anchor_date)
    if a is None:
        out["resolution"] = "unresolved"
        out["reason"] = (
            f"{series} has no close on or after {anchor_date} "
            f"(last bar {frame.index[-1].date()})"
        )
        return out

    out["anchor_date"] = str(frame.index[a].date())
    # A basket has no single anchor price — the mean of member closes is an
    # arbitrary number, so report None rather than something that reads like a
    # quote.  Returns are always ratio-based and never use this field.
    out["anchor_price"] = (
        round(float(frame.iloc[a].iloc[0]), 6) if frame.shape[1] == 1 else None
    )
    elapsed = len(frame) - 1 - a
    out["sessions_elapsed"] = int(elapsed)
    out["status"] = _status_for(elapsed, horizons)

    bench_frame = None
    if benchmark != "absolute":
        bench_frame, bench_meta = resolve_frame(benchmark, data_root)
        if bench_frame is None:
            out["benchmark_reason"] = bench_meta.get("reason", "unresolved")

    for h in sorted(horizons):
        key = str(h)
        end = a + h
        if end >= len(frame):
            out["returns"][key] = None
            out["excess"][key] = None
            continue
        ret = _ratio_mean(frame, a, end)
        out["returns"][key] = None if ret is None else round(ret, 6)
        if bench_frame is None or ret is None:
            out["excess"][key] = None
            continue
        bench_ret = _return_between_dates(bench_frame, frame.index[a], frame.index[end])
        out["excess"][key] = None if bench_ret is None else round(ret - bench_ret, 6)

    # mark-to-latest interim — available once at least one session has elapsed
    last = len(frame) - 1
    if interim_cutoff:
        capped = last_position_on_or_before(frame.index, interim_cutoff)
        # capped is None only when the cutoff predates the whole series, i.e. the
        # event window closed before this instrument has any data.  Falling back
        # to the uncapped last bar there would print a mark-to-TODAY number on a
        # bounded card — the exact defect the cap exists to prevent — so collapse
        # the window to nothing and report no interim instead.
        last = min(last, capped) if capped is not None else a
        out["interim_basis"] = f"capped at {interim_cutoff} (event period close)"
    if last > a:
        interim = _ratio_mean(frame, a, last)
        out["interim"] = None if interim is None else round(interim, 6)
        out["interim_date"] = str(frame.index[last].date())
        if bench_frame is not None and interim is not None:
            bench_interim = _return_between_dates(bench_frame, frame.index[a], frame.index[last])
            out["interim_excess"] = (
                None if bench_interim is None else round(interim - bench_interim, 6)
            )
    return out


def _median_or_none(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(float(statistics.median(clean)), 6)


def grade_thesis(thesis: dict[str, Any], data_root: Path | None = None) -> dict[str, Any]:
    """Grade one thesis: per-instrument grades + a MEDIAN rollup across them."""
    horizons = thesis.get("horizon_sessions") or list(DEFAULT_HORIZONS)
    entry_class = thesis.get("entry_class", "forward")
    interim_cutoff = None
    if entry_class == "retro":
        period = thesis.get("event_period") or {}
        anchor_date = period.get("from") or thesis["registered_at"]
        # A retro episode is BOUNDED: its interim stops at the event close, so the
        # card reports the episode rather than the years since.
        interim_cutoff = period.get("to")
    else:
        anchor_date = thesis["registered_at"]

    instruments = [
        grade_instrument(inst, anchor_date, horizons, data_root,
                         interim_cutoff=interim_cutoff)
        for inst in thesis.get("instruments", [])
    ]
    resolved = [i for i in instruments if i["resolution"] != "unresolved"]

    rollup_returns = {
        str(h): _median_or_none([i["returns"].get(str(h)) for i in resolved])
        for h in sorted(horizons)
    }
    rollup_excess = {
        str(h): _median_or_none([i["excess"].get(str(h)) for i in resolved])
        for h in sorted(horizons)
    }

    if resolved:
        status = _status_for(min(i["sessions_elapsed"] for i in resolved), horizons)
    else:
        status = STATUS_ACCRUING

    legs = thesis.get("legs", [])
    return {
        "thesis_id": thesis.get("thesis_id"),
        "title": thesis.get("title"),
        "registered_at": thesis.get("registered_at"),
        "author": thesis.get("author"),
        "direction": thesis.get("direction"),
        "conviction": thesis.get("conviction"),
        "entry_class": entry_class,
        "anchor_date": anchor_date,
        "horizon_sessions": sorted(horizons),
        "status": status,
        "instruments": instruments,
        "unresolved_n": len(instruments) - len(resolved),
        "rollup": {
            "method": "median across instruments",
            "returns": rollup_returns,
            "excess": rollup_excess,
            "interim": _median_or_none([i["interim"] for i in resolved]),
            "interim_excess": _median_or_none([i["interim_excess"] for i in resolved]),
        },
        "legs_total": len(legs),
        "legs_calibrated": sum(1 for leg in legs if leg.get("leg_kind") == "calibrated"),
        "legs_judgment": sum(1 for leg in legs if leg.get("leg_kind") == "judgment"),
        "legs": legs,
        "confirm_watch": thesis.get("confirm_watch"),
        "risk_watch": thesis.get("risk_watch"),
        "event_period": thesis.get("event_period"),
        "hindsight_risk": thesis.get("hindsight_risk"),
        "sources": thesis.get("sources"),
        "amended_from": thesis.get("amended_from"),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate ONE entry_class.  Raises on a mixed batch — see the firewall note.

    Forward rows are a track record; retro rows are curated hindsight.  One
    number spanning both is not a weaker statistic, it is a false one, so this
    refuses rather than warns.
    """
    classes = {r.get("entry_class") for r in records}
    if len(classes) > 1:
        raise MacroThesisFirewallError(
            "refusing to pool forward and retro theses in one statistic "
            f"(got {sorted(str(c) for c in classes)}); grade them separately — "
            "retro rows are selected in hindsight and their rate is not a track record"
        )
    entry_class = next(iter(classes)) if classes else None

    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    def _median_over(getter) -> float | None:
        return _median_or_none([getter(r) for r in records])

    horizons = sorted({h for r in records for h in r.get("horizon_sessions", [])})
    return {
        "entry_class": entry_class,
        "n": len(records),
        "by_status": by_status,
        "median_return": {
            str(h): _median_over(lambda r, h=h: r["rollup"]["returns"].get(str(h)))
            for h in horizons
        },
        "median_excess": {
            str(h): _median_over(lambda r, h=h: r["rollup"]["excess"].get(str(h)))
            for h in horizons
        },
        "median_interim": _median_over(lambda r: r["rollup"]["interim"]),
        "legs_calibrated": sum(r.get("legs_calibrated", 0) for r in records),
        "legs_judgment": sum(r.get("legs_judgment", 0) for r in records),
        "unresolved_instruments": sum(r.get("unresolved_n", 0) for r in records),
    }


def grade(data_root: Path | None = None) -> dict[str, Any]:
    """Grade the whole ledger, forward and retro STRICTLY SEPARATED.

    There is no top-level pooled statistic and there must never be one: the two
    sections are different epistemic objects.  See the firewall note in the
    module docstring.
    """
    rows = load_ledger(data_root)
    graded = [grade_thesis(row, data_root) for row in rows]
    graded.sort(key=lambda r: (r.get("registered_at") or "", r.get("thesis_id") or ""), reverse=True)

    forward = [r for r in graded if r["entry_class"] == "forward"]
    retro = [r for r in graded if r["entry_class"] == "retro"]
    return {
        "schema": SCHEMA,
        "authority": "none — ops/journal tier; never scores, ranks, gates or sizes any surface",
        "forward": {
            "label": "FORWARD REGISTER (track record)",
            "theses": forward,
            "summary": summarize(forward),
        },
        "retro": {
            "label": "RETRO LIBRARY (training/calibration — hindsight-disclosed, never pooled)",
            "theses": retro,
            "summary": summarize(retro),
        },
    }
