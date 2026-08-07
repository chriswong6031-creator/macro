"""W1A/W1C — the point-in-time universe read adapter, with honest unavailable states.

The seasonality panel folds ~25 complete years onto a calendar clock.  The only
dated identity substrate this repo owns is
``data/symbol_directory/snapshots/YYYY-MM-DD.parquet``, whose earliest snapshot
is weeks old, not decades.  ``config/sector_intelligence_ownership.yml``
registers that store as ``private_point_in_time_snapshots`` under
``registrations.security_identity_and_corporate_actions`` with four declared
limitations, and registers
``biocatalyst_security_identity_pit_adapter.v1`` as
``unavailable_bootstrap_roster_only`` (``module: null``, ``callable: null``)
behind the blocker :data:`UNRESOLVED_BLOCKER`.  ``collectors.symbol_directory``
is scoped ``us_exchange_roster_not_complete_security_master`` — a bootstrap
roster, explicitly NOT an acceptable point-in-time implementation and NOT an
acceptable fallback.

So this adapter answers four questions, and for most of the panel's history the
answer is *unavailable*.  Surfacing that is the deliverable:

==============================================  ==========================================
question                                        answer
==============================================  ==========================================
identity, earliest <= asof <= latest + carry    RESOLVED from the snapshot at-or-before it
identity as of a date < earliest snapshot       UNAVAILABLE — never today's roster
identity past latest + carry window             UNAVAILABLE — never a carried-forward roster
corporate actions as of any date                UNAVAILABLE — always, naming the blocker
point-in-time price adjustment                  UNAVAILABLE — ``current_vendor_vintage``
==============================================  ==========================================

where *carry* is :data:`MAX_FORWARD_CARRY_DAYS`.

Six properties are structural rather than commented-on:

* **No look-ahead.**  A read picks the snapshot with the GREATEST date <= the
  requested ``asof``.  A later snapshot is never consulted, so a name that only
  exists in the future cannot appear in the past.
* **No backward leak.**  When no snapshot precedes ``asof`` the read is
  unavailable with ``security=None``.  There is no branch that substitutes the
  current roster, and no branch that returns a bare ticker.
* **No unbounded FORWARD leak.**  The mirror of the backward rule, and just as
  load-bearing: past the last snapshot the roster is not evidence about the
  future either.  Beyond :data:`MAX_FORWARD_CARRY_DAYS` the read goes
  unavailable rather than serving today's roster for any date to the end of
  time, and every available read carries ``snapshot_age_days`` so a caller can
  see how stale the answer it did get is.
* **No silently resolved ticker collision.**  This plane's declared linkage is
  :data:`IDENTITY_LINKAGE` — ticker only, no stable security id.  When one
  snapshot carries two rows for a ticker (the committed store does: an upstream
  ``NA``/``nan`` NA-coercion artifact collides with the real ``NAN``), there is
  nothing in the schema that can pick the right one, so the read is
  ``ambiguous_ticker_multiple_rows_no_stable_security_id`` rather than
  ``.iloc[0]``.
* **No invented limitations.**  ``limitations`` are read verbatim from the
  ownership registry and the ``coverage_class`` is the registry's own first
  declared limitation, not a constant restated here.  A missing registry entry
  FAILS CLOSED — the adapter goes unavailable rather than inventing a coverage
  claim it is not registered for.
* **No wall clock.**  ``asof`` is always an explicit, required argument.  This
  module reads no clock, so a read is reproducible from its arguments alone.

A snapshot is only accepted as :data:`SNAPSHOT_SCHEMA` when it carries every
column in :data:`SNAPSHOT_REQUIRED_COLUMNS`.  A thinner file is unavailable, not
a stamped read with quiet zeroes: the writer builds its column order by
*presence*, so a partial snapshot is producible by construction, and
``excluded_preferred: 0`` from "the column is gone" is indistinguishable from
"there were none" — the same quiet-gap-vs-quiet-zero failure
:func:`corporate_actions_asof` refuses to commit.

The roster carries no permanent security or issuer identifier and no sector
column, so ticker renames, dual-class linkage, and sector-as-of are all
unavailable *from this artifact* — reported as ``None`` fields on the identity
payload, never guessed.  That "cannot answer" is scoped to the registered
artifact, not to the repo: the same collector also writes
``data/symbol_directory/cik_map/`` (a SEC CIK per ticker, which WOULD link a
dual-class pair), but that file is outside this adapter's registered writer
artifact and is deliberately not read here — the coverage report says so by
name rather than letting the null read wider than it is.

``engine.seasonality.foundation`` already discloses
``price_adjustment_is_point_in_time: False`` and
``universe_is_survivorship_biased: True``; this module does not repair either,
it only gives callers a typed way to ask and be told no.

Imports of pandas and PyYAML are deliberately deferred into the functions that
need them, so ``import engine.seasonality`` stays importable on a thin CI runner
with no scientific stack — the same contract the package ``__init__`` keeps for
``panel``/``calendar``/``scanner``.

Pure reads over the committed store — no network, and nothing here writes.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

# --- registered facts -------------------------------------------------------

#: The blocker key registered against ``biocatalyst_security_identity_pit_adapter.v1``.
UNRESOLVED_BLOCKER = "complete_point_in_time_security_and_corporate_actions_contract"

#: The registration this adapter reads under, and the state that registration is
#: in.  Carried on EVERY read (not only the coverage report) so a disclosure
#: surface rendering one ``UniverseRead`` still sees that the underlying
#: registration is a bootstrap roster.
ADAPTER_REGISTRATION = "biocatalyst_security_identity_pit_adapter.v1"
ADAPTER_IMPLEMENTATION_STATE = "unavailable_bootstrap_roster_only"

#: Store layout.  ``SNAPSHOT_SUBPATH`` is the default; the effective path honours
#: ``storage.data_dir`` from ``<root>/config.yml`` — the same key the registered
#: writer resolves through ``lib.config.data_dir()`` — so reader and writer
#: cannot desynchronise if that key is ever changed.
DATA_DIR_DEFAULT = "data"
DATA_DIR_CONFIG_SUBPATH = Path("config.yml")
SNAPSHOT_STORE_RELPATH = Path("symbol_directory") / "snapshots"
SNAPSHOT_SUBPATH = Path(DATA_DIR_DEFAULT) / SNAPSHOT_STORE_RELPATH
CIK_MAP_RELPATH = Path("symbol_directory") / "cik_map"

REGISTRY_SUBPATH = Path("config") / "sector_intelligence_ownership.yml"
REGISTRY_SECTION = "registrations"
REGISTRY_KEY = "security_identity_and_corporate_actions"

COVERAGE_SCHEMA = "seasonality.pit_universe_coverage.v1"
SNAPSHOT_SCHEMA = "symbol_directory_snapshot.v1"

#: A file is only accepted as :data:`SNAPSHOT_SCHEMA` when it carries all of
#: these.  ``symbol_directory_snapshot.v1`` has no declared schema document
#: anywhere in the repo, so this list IS the contract this reader asserts.
SNAPSHOT_REQUIRED_COLUMNS = (
    "symbol",
    "security_name",
    "exchange",
    "etf",
    "test_issue",
    "is_preferred",
    "source",
)

#: The snapshot filename is stamped by the collector from the UTC clock at
#: collection time, so it is a UTC COLLECTION date, not an exchange session
#: date (``collectors/symbol_directory.py``).  Content predates its stamp; a caller
#: reasoning on a US trading calendar can be off by up to one day, and this
#: string is on every payload so that is never silently assumed away.
SNAPSHOT_DATE_BASIS = "utc_collection_date_not_exchange_session_date"

#: How far past the LAST snapshot a read may reach before it stops being a
#: point-in-time answer and becomes a stale roster wearing a future date.  A
#: week absorbs a collector outage over a holiday weekend; beyond it the plane
#: has no evidence at all and says so.
MAX_FORWARD_CARRY_DAYS = 7

#: Coverage class when the registry entry is absent — the fail-closed state.
COVERAGE_CLASS_UNREGISTERED = "unregistered_no_ownership_entry"
#: The coverage class the COMMITTED registry currently yields.  Not a source of
#: truth: :func:`_coverage` reads the class from the registry's own first
#: declared limitation, so this constant tracks the registry rather than the
#: registry being asserted to match this constant.
COVERAGE_CLASS_ROSTER = "us_exchange_roster_only"

# --- unavailable reasons ----------------------------------------------------

REASON_NO_SNAPSHOT = "no_snapshot_at_or_before_asof"
REASON_ASOF_BEYOND_STORE = "asof_beyond_latest_snapshot_max_forward_carry"
REASON_SYMBOL_ABSENT = "symbol_absent_from_snapshot"
REASON_SYMBOL_AMBIGUOUS = "ambiguous_ticker_multiple_rows_no_stable_security_id"
REASON_CORPORATE_ACTIONS = "corporate_action_history_unavailable"
REASON_REGISTRY_MISSING = "ownership_registry_entry_missing"
REASON_REGISTRY_UNREADABLE = "ownership_registry_present_but_unreadable"
REASON_REGISTRY_NO_LIMITATIONS = "ownership_registry_entry_declares_no_limitations"
REASON_SNAPSHOT_UNREADABLE = "snapshot_unreadable_or_unrecognised_schema"

# --- declared identity/eligibility rules ------------------------------------

#: Membership is filtered by DECLARED structural rules over the snapshot's own
#: columns.  There is no ticker blacklist here and there must never be one: a
#: hand-maintained exclusion list is a survivorship decision made after the fact.
#: The ETF rule is stated in the same declared-and-UNAPPLIED form as the
#: liquidity rule: the roster is 44% ETFs and the read must not let a caller
#: mistake "roster membership" for "common equity".
MEMBERSHIP_RULES = (
    "test_issue_rows_excluded",
    "preferred_lines_excluded",
    "etf_lines_kept_and_flagged_not_excluded",
    "duplicate_ticker_rows_collapsed_and_counted",
    "no_ticker_blacklist",
    "liquidity_screen_requires_price_or_volume_absent_from_this_schema",
)

#: The roster has no price or volume column, so a dormant shell cannot be
#: screened out on liquidity here.  It stays in membership and the read says so.
LIQUIDITY_SCREEN_STATE = "unavailable_no_price_or_volume_in_snapshot_schema"

#: ETFs are IN the returned membership.  Excluding them would be a universe
#: decision this adapter is not registered to make; leaving them in silently
#: would be a wrong universe.  So they are kept, counted, and listed.
ETF_SCREEN_STATE = "declared_unapplied_etf_rows_kept_and_listed"

IDENTITY_LINKAGE = "ticker_only_no_stable_security_id"
SECTOR_AVAILABILITY = "not_in_roster_schema"

_SNAPSHOT_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.parquet$")


# --- the read ---------------------------------------------------------------


@dataclass(frozen=True)
class UniverseRead:
    """One point-in-time answer — ALWAYS returned, available or not.

    Never ``None``, never ``{}``, never a bare ticker.  ``security`` carries the
    payload only when ``available`` is true; otherwise ``unavailable_reason`` is
    populated and, where a registered contract is what is missing, ``blocker``
    names it.  ``snapshot_age_days`` is ``asof - snapshot_date`` — the staleness
    of whatever answer was given — and ``detail`` carries machine-readable
    context for an unavailable that has some (a ticker collision's row count,
    say), never a partial answer.
    """

    available: bool
    asof: date
    snapshot_date: date | None
    security: dict | None
    unavailable_reason: str | None
    blocker: str | None
    coverage_class: str
    limitations: tuple[str, ...] = field(default=())
    snapshot_age_days: int | None = None
    detail: dict | None = None
    adapter_implementation_state: str = ADAPTER_IMPLEMENTATION_STATE

    def __post_init__(self) -> None:
        if self.available and self.security is None:
            raise ValueError("an available read must carry a security payload")
        if self.available and self.snapshot_date is None:
            raise ValueError("an available read must name the snapshot it came from")
        if not self.available and self.security is not None:
            raise ValueError("an unavailable read must not carry a security payload")
        if not self.available and not self.unavailable_reason:
            raise ValueError("an unavailable read must state a reason")
        if self.snapshot_age_days is not None and self.snapshot_date is None:
            raise ValueError("staleness without a snapshot is not a measurable age")

    def as_dict(self) -> dict:
        """A JSON-safe view for disclosure surfaces."""
        return {
            "available": self.available,
            "asof": self.asof.isoformat(),
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "snapshot_age_days": self.snapshot_age_days,
            "snapshot_date_basis": SNAPSHOT_DATE_BASIS,
            "security": self.security,
            "unavailable_reason": self.unavailable_reason,
            "detail": self.detail,
            "blocker": self.blocker,
            "coverage_class": self.coverage_class,
            "limitations": list(self.limitations),
            "adapter_registration": ADAPTER_REGISTRATION,
            "adapter_implementation_state": self.adapter_implementation_state,
        }


# --- registry (read only, fail closed) --------------------------------------


def _registry_entry(root: Path) -> tuple[str, dict | None]:
    """``(status, entry)`` with ``status`` in ``ok`` / ``missing`` / ``unreadable``.

    The two failures are told apart because they have different remedies and a
    read that reports "entry missing" for a YAML syntax error sends the reader
    to the wrong file.  READ ONLY — nothing in this module writes the registry.
    """
    path = Path(root) / REGISTRY_SUBPATH
    if not path.is_file():
        return "missing", None
    try:
        import yaml  # deferred: keeps ``import engine.seasonality`` stdlib-thin
    except ImportError:  # pragma: no cover - PyYAML is present in every CI job here
        return "unreadable", None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable", None
    if not isinstance(loaded, dict):
        return "unreadable", None
    section = loaded.get(REGISTRY_SECTION)
    if not isinstance(section, dict):
        return "missing", None
    entry = section.get(REGISTRY_KEY)
    if not isinstance(entry, dict):
        return "missing", None
    return "ok", entry


def _coverage(root: Path) -> tuple[str, tuple[str, ...], bool, str | None]:
    """``(coverage_class, limitations, registered, unavailable_reason)``.

    ``limitations`` are verbatim, and ``coverage_class`` is the registry's own
    FIRST declared limitation rather than a constant restated here — a registry
    edit moves the class with it, so the class cannot drift into a coverage
    claim the registry never made.
    """
    status, entry = _registry_entry(root)
    if status == "unreadable":
        return COVERAGE_CLASS_UNREGISTERED, (), False, REASON_REGISTRY_UNREADABLE
    if entry is None:
        return COVERAGE_CLASS_UNREGISTERED, (), False, REASON_REGISTRY_MISSING
    raw = entry.get("limitations")
    limitations = tuple(str(item) for item in raw) if isinstance(raw, (list, tuple)) else ()
    if not limitations:
        # Registered but claiming no limitations is not a coverage upgrade this
        # adapter is allowed to grant itself.
        return COVERAGE_CLASS_UNREGISTERED, (), False, REASON_REGISTRY_NO_LIMITATIONS
    return limitations[0], limitations, True, None


# --- snapshot store ---------------------------------------------------------


@lru_cache(maxsize=8)
def _configured_data_dir(config_text: str, mtime_ns: int, size: int) -> str:
    """``storage.data_dir`` from a repo ``config.yml``, or the default."""
    try:
        import yaml  # deferred, same bargain as the registry read
    except ImportError:  # pragma: no cover - PyYAML is present in every CI job here
        return DATA_DIR_DEFAULT
    try:
        loaded = yaml.safe_load(Path(config_text).read_text(encoding="utf-8"))
    except Exception:
        return DATA_DIR_DEFAULT
    if not isinstance(loaded, dict):
        return DATA_DIR_DEFAULT
    storage = loaded.get("storage")
    value = storage.get("data_dir") if isinstance(storage, dict) else None
    return str(value) if isinstance(value, str) and value.strip() else DATA_DIR_DEFAULT


def _data_dir(root: Path) -> Path:
    config_path = Path(root) / DATA_DIR_CONFIG_SUBPATH
    try:
        stat = config_path.stat()
    except OSError:
        return Path(root) / DATA_DIR_DEFAULT
    name = _configured_data_dir(str(config_path), stat.st_mtime_ns, stat.st_size)
    configured = Path(name)
    return configured if configured.is_absolute() else Path(root) / configured


def snapshot_store(root: Path) -> Path:
    """Where this reader looks, honouring the writer's own ``storage.data_dir``."""
    return _data_dir(root) / SNAPSHOT_STORE_RELPATH


def snapshot_dates(root: Path) -> list[date]:
    """Every dated snapshot in the store, ascending.

    Filenames that are not ``YYYY-MM-DD.parquet`` are ignored rather than
    guessed at.
    """
    store = snapshot_store(root)
    if not store.is_dir():
        return []
    out: list[date] = []
    for entry in store.iterdir():
        match = _SNAPSHOT_NAME.match(entry.name)
        if not match:
            continue
        try:
            out.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
    return sorted(out)


def earliest_snapshot(root: Path) -> date | None:
    """The first date this plane can answer identity for, or ``None``."""
    dates = snapshot_dates(root)
    return dates[0] if dates else None


def latest_snapshot(root: Path) -> date | None:
    """The last date this plane has evidence for, or ``None``."""
    dates = snapshot_dates(root)
    return dates[-1] if dates else None


def _snapshot_at_or_before(root: Path, asof: date) -> date | None:
    """The GREATEST snapshot date <= ``asof``, within the forward carry window.

    A later snapshot is never returned — that is the look-ahead guard.  Reaching
    more than :data:`MAX_FORWARD_CARRY_DAYS` past the LAST snapshot returns
    ``None`` too: extrapolating today's roster to an arbitrary future date is
    the forward mirror of the backward leak this module exists to prevent.

    The bound deliberately applies only past the END of the store, not to every
    gap inside it.  Inside the store a gap is bracketed by evidence on both
    sides and the staleness is disclosed as ``snapshot_age_days``; past the end
    there is no bracketing evidence and there never will be for that ``asof``,
    so the answer is not stale — it is unknown.
    """
    dates = snapshot_dates(root)
    index = bisect_right(dates, asof)
    if not index:
        return None
    chosen = dates[index - 1]
    if chosen == dates[-1] and (asof - chosen).days > MAX_FORWARD_CARRY_DAYS:
        return None
    return chosen


@lru_cache(maxsize=16)
def _load_frame(path_text: str, mtime_ns: int, size: int):
    """Read one snapshot parquet.  Keyed by mtime+size so it cannot go stale.

    Projected to :data:`SNAPSHOT_REQUIRED_COLUMNS`: it is the columns this
    adapter reads, and a file that cannot serve them is not this schema.
    """
    import pandas as pd  # deferred: parquet is the only reason pandas is needed

    return pd.read_parquet(path_text, columns=list(SNAPSHOT_REQUIRED_COLUMNS))


def _read_snapshot(root: Path, snapshot: date):
    """The snapshot frame, or ``None`` when it is unreadable or off-schema.

    Fail-closed on purpose: a corrupt file, an unreadable one, and one missing a
    declared column all become an UNAVAILABLE read rather than a stamped payload
    with quiet nulls in it.
    """
    path = snapshot_store(root) / f"{snapshot.isoformat()}.parquet"
    try:
        stat = path.stat()
        frame = _load_frame(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception:
        return None
    columns = getattr(frame, "columns", None)
    if columns is None:
        return None
    if any(column not in columns for column in SNAPSHOT_REQUIRED_COLUMNS):
        return None
    return frame


def _flag(row, column: str) -> bool | None:
    if column not in row:
        return None
    value = row[column]
    try:
        if value is None or value != value:  # NaN
            return None
    except TypeError:  # pragma: no cover - non-comparable cell
        return None
    return bool(value)


def _text(row, column: str) -> str | None:
    if column not in row:
        return None
    value = row[column]
    try:
        if value is None or value != value:  # NaN
            return None
    except TypeError:  # pragma: no cover - non-comparable cell
        return None
    return str(value)


def _coerce_asof(asof) -> date:
    if isinstance(asof, datetime):
        return asof.date()
    if isinstance(asof, date):
        return asof
    raise TypeError(f"asof must be a date, got {type(asof).__name__}")


def _no_snapshot_reason(root: Path, asof: date) -> str:
    """Which side of the store ``asof`` fell off — before it, or past its end."""
    last = latest_snapshot(root)
    if last is not None and asof > last:
        return REASON_ASOF_BEYOND_STORE
    return REASON_NO_SNAPSHOT


def _unavailable(
    asof: date,
    reason: str,
    *,
    coverage_class: str,
    limitations: tuple[str, ...],
    snapshot_date: date | None = None,
    blocker: str | None = None,
    detail: dict | None = None,
) -> UniverseRead:
    return UniverseRead(
        available=False,
        asof=asof,
        snapshot_date=snapshot_date,
        security=None,
        unavailable_reason=reason,
        blocker=blocker,
        coverage_class=coverage_class,
        limitations=limitations,
        snapshot_age_days=(asof - snapshot_date).days if snapshot_date else None,
        detail=detail,
    )


# --- the four questions -----------------------------------------------------


def resolve_security_asof(symbol: str, asof: date, *, root: Path) -> UniverseRead:
    """Identity for ``symbol`` as it was KNOWN on ``asof``.

    Resolved from the snapshot with the greatest date <= ``asof``.  Before the
    earliest snapshot there is no answer and none is invented: the read comes
    back ``available=False`` with ``security=None``.  More than
    :data:`MAX_FORWARD_CARRY_DAYS` past the last snapshot there is no answer
    either.  A symbol missing from the chosen snapshot is
    ``symbol_absent_from_snapshot`` — not a guess, and never a look-up in the
    current roster.  A symbol matching TWO rows is ambiguous, not the first row:
    with no stable security id there is nothing that can choose between them.
    """
    asof = _coerce_asof(asof)
    coverage_class, limitations, registered, registry_reason = _coverage(root)
    if not registered:
        return _unavailable(
            asof,
            registry_reason or REASON_REGISTRY_MISSING,
            coverage_class=coverage_class,
            limitations=limitations,
            blocker=UNRESOLVED_BLOCKER,
        )

    snapshot = _snapshot_at_or_before(root, asof)
    if snapshot is None:
        return _unavailable(
            asof,
            _no_snapshot_reason(root, asof),
            coverage_class=coverage_class,
            limitations=limitations,
        )

    frame = _read_snapshot(root, snapshot)
    if frame is None:
        return _unavailable(
            asof,
            REASON_SNAPSHOT_UNREADABLE,
            coverage_class=coverage_class,
            limitations=limitations,
            snapshot_date=snapshot,
        )

    wanted = str(symbol).strip().upper()
    matches = frame[frame["symbol"].astype(str).str.strip().str.upper() == wanted]
    if matches.empty:
        return _unavailable(
            asof,
            REASON_SYMBOL_ABSENT,
            coverage_class=coverage_class,
            limitations=limitations,
            snapshot_date=snapshot,
        )
    if len(matches) > 1:
        return _unavailable(
            asof,
            REASON_SYMBOL_AMBIGUOUS,
            coverage_class=coverage_class,
            limitations=limitations,
            snapshot_date=snapshot,
            blocker=UNRESOLVED_BLOCKER,
            detail={
                "queried_symbol": wanted,
                "n_matching_rows": int(len(matches)),
                "matching_symbols": sorted({str(v) for v in matches["symbol"].astype(str)}),
                "matching_exchanges": sorted({str(v) for v in matches["exchange"].astype(str)}),
                "identity_linkage": IDENTITY_LINKAGE,
            },
        )

    row = matches.iloc[0]
    return UniverseRead(
        available=True,
        asof=asof,
        snapshot_date=snapshot,
        snapshot_age_days=(asof - snapshot).days,
        security={
            "symbol": _text(row, "symbol") or wanted,
            "security_name": _text(row, "security_name"),
            "exchange": _text(row, "exchange"),
            "source": _text(row, "source"),
            "is_etf": _flag(row, "etf"),
            "is_test_issue": _flag(row, "test_issue"),
            "is_preferred": _flag(row, "is_preferred"),
            # Absent BY SCHEMA, so reported as absent rather than guessed.  A
            # rename or a dual-class pair cannot be linked without these.
            "security_id": None,
            "issuer_id": None,
            "sector": None,
            "identity_linkage": IDENTITY_LINKAGE,
            "sector_availability": SECTOR_AVAILABILITY,
            "snapshot_schema": SNAPSHOT_SCHEMA,
            "snapshot_date_basis": SNAPSHOT_DATE_BASIS,
            "as_known_on": snapshot.isoformat(),
        },
        unavailable_reason=None,
        blocker=None,
        coverage_class=coverage_class,
        limitations=limitations,
    )


def corporate_actions_asof(symbol: str, asof: date, *, root: Path) -> UniverseRead:
    """Corporate actions known on ``asof`` — UNAVAILABLE, always.

    The registry declares ``incomplete_corporate_action_history`` and holds
    ``biocatalyst_security_identity_pit_adapter.v1`` behind
    :data:`UNRESOLVED_BLOCKER`.  There is deliberately no branch in this
    function that can return an action: a partial action history is worse than
    none, because a caller cannot tell a quiet gap from a quiet zero.
    """
    asof = _coerce_asof(asof)
    coverage_class, limitations, _registered, _reason = _coverage(root)
    return _unavailable(
        asof,
        REASON_CORPORATE_ACTIONS,
        coverage_class=coverage_class,
        limitations=limitations,
        blocker=UNRESOLVED_BLOCKER,
    )


def price_adjustment_vintage() -> dict:
    """The vintage of the panel's only price source — not point in time.

    ``data/yahoo/*.parquet`` is the vendor's CURRENT adjustment re-applied to
    all history, so it cannot answer any "as adjusted on date D" question.
    ``engine.seasonality.foundation`` discloses the same fact to readers; this
    is the machine-readable twin, and it is a constant because there is no
    replay proof that would let it be anything else.
    """
    return {
        "point_in_time": False,
        "vintage": "current_vendor_vintage",
        "note": (
            "Split- and dividend-adjusted closes are the vendor's CURRENT vintage re-applied "
            "to all history. No frozen as-of-date adjustment exists, so a split or special "
            "dividend that happened after a study window has already been folded backwards "
            "into that window's prices."
        ),
        "source": "data/yahoo/*.parquet",
        "disclosed_by": "engine.seasonality.foundation.build_methodology_manifest",
        "blocker": UNRESOLVED_BLOCKER,
    }


def membership_asof(asof: date, *, root: Path) -> UniverseRead:
    """The roster membership as it was KNOWN on ``asof``.

    Structural, declared filters only (:data:`MEMBERSHIP_RULES`) over the
    snapshot's own columns.  A name that was listed then and is delisted or
    acquired now is still a member of the historical read — that is the point.
    A dormant shell stays in too: the roster carries no price or volume, so the
    liquidity rule is declared and reported UNAPPLIED rather than replaced with
    a hand-maintained ticker blacklist.

    ETFs stay in as well, and this is NOT a roster of common equity: 44% of the
    committed store is an ETF line.  They are counted (``n_etf_symbols``) and
    listed (``etf_symbols``) so a caller can subtract them without re-reading
    the parquet, and ``screens_applied`` states which declared rules actually
    ran.  Counts reconcile exactly:
    ``n_rows_in_snapshot - excluded_test_issue - excluded_preferred -
    excluded_duplicate_symbol_rows == n_symbols``.
    """
    asof = _coerce_asof(asof)
    coverage_class, limitations, registered, registry_reason = _coverage(root)
    if not registered:
        return _unavailable(
            asof,
            registry_reason or REASON_REGISTRY_MISSING,
            coverage_class=coverage_class,
            limitations=limitations,
            blocker=UNRESOLVED_BLOCKER,
        )

    snapshot = _snapshot_at_or_before(root, asof)
    if snapshot is None:
        return _unavailable(
            asof,
            _no_snapshot_reason(root, asof),
            coverage_class=coverage_class,
            limitations=limitations,
        )

    frame = _read_snapshot(root, snapshot)
    if frame is None:
        return _unavailable(
            asof,
            REASON_SNAPSHOT_UNREADABLE,
            coverage_class=coverage_class,
            limitations=limitations,
            snapshot_date=snapshot,
        )

    # Every column below is guaranteed present by the schema gate in
    # ``_read_snapshot``, so a reported 0 always means "none", never "unknown".
    n_rows = int(len(frame))
    keep = frame
    mask = keep["test_issue"].fillna(False).astype(bool)
    excluded_test = int(mask.sum())
    keep = keep[~mask]
    mask = keep["is_preferred"].fillna(False).astype(bool)
    excluded_preferred = int(mask.sum())
    keep = keep[~mask]

    normalised = keep["symbol"].astype(str).str.strip().str.upper()
    symbols = tuple(sorted(set(normalised)))
    etf_mask = keep["etf"].fillna(False).astype(bool)
    etf_symbols = tuple(sorted(set(normalised[etf_mask])))
    excluded_duplicate = int(len(keep) - len(symbols))
    return UniverseRead(
        available=True,
        asof=asof,
        snapshot_date=snapshot,
        snapshot_age_days=(asof - snapshot).days,
        security={
            "kind": "membership_asof",
            "symbols": symbols,
            "n_symbols": len(symbols),
            "n_rows_in_snapshot": n_rows,
            "excluded_test_issue": excluded_test,
            "excluded_preferred": excluded_preferred,
            "excluded_duplicate_symbol_rows": excluded_duplicate,
            "etf_symbols": etf_symbols,
            "n_etf_symbols": len(etf_symbols),
            "etf_screen": ETF_SCREEN_STATE,
            "etf_screen_applied": False,
            "rules": MEMBERSHIP_RULES,
            "screens_applied": {
                "test_issue_rows_excluded": True,
                "preferred_lines_excluded": True,
                "etf_lines_excluded": False,
                "liquidity_screen_applied": False,
            },
            "liquidity_screen": LIQUIDITY_SCREEN_STATE,
            "liquidity_screen_applied": False,
            "sector_availability": SECTOR_AVAILABILITY,
            "identity_linkage": IDENTITY_LINKAGE,
            "snapshot_schema": SNAPSHOT_SCHEMA,
            "snapshot_date_basis": SNAPSHOT_DATE_BASIS,
            "as_known_on": snapshot.isoformat(),
        },
        unavailable_reason=None,
        blocker=None,
        coverage_class=coverage_class,
        limitations=limitations,
    )


def coverage_report(root: Path) -> dict:
    """What this plane can and cannot answer, with counts.

    Written to be pasted into a disclosure surface unedited: the ``cannot``
    list is longer than the ``can`` list, and that is the accurate shape.  The
    ``cannot`` list is scoped to the REGISTERED artifact — see
    ``planes_not_read_by_this_adapter``, which names the adjacent CIK map so the
    null is not read as "the repo cannot do this".
    """
    coverage_class, limitations, registered, _reason = _coverage(root)
    dates = snapshot_dates(root)
    first = dates[0] if dates else None
    last = dates[-1] if dates else None
    return {
        "schema": COVERAGE_SCHEMA,
        "registered": registered,
        "coverage_class": coverage_class,
        "limitations": list(limitations),
        "blocker": UNRESOLVED_BLOCKER,
        "adapter_registration": ADAPTER_REGISTRATION,
        "adapter_implementation_state": ADAPTER_IMPLEMENTATION_STATE,
        "snapshot_root": str(snapshot_store(root)),
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "snapshot_required_columns": list(SNAPSHOT_REQUIRED_COLUMNS),
        "snapshot_date_basis": SNAPSHOT_DATE_BASIS,
        "max_forward_carry_days": MAX_FORWARD_CARRY_DAYS,
        "n_snapshots": len(dates),
        "earliest_snapshot": first.isoformat() if first else None,
        "latest_snapshot": last.isoformat() if last else None,
        "snapshot_span_days": (last - first).days if first and last else None,
        "can_answer": [
            "security_identity_asof_between_earliest_snapshot_and_latest_plus_max_forward_carry",
            "roster_membership_asof_between_earliest_snapshot_and_latest_plus_max_forward_carry",
        ],
        "cannot_answer": [
            "security_identity_before_earliest_snapshot",
            "security_identity_beyond_latest_snapshot_max_forward_carry",
            "corporate_actions_asof_any_date",
            "point_in_time_price_adjustment",
            "stable_security_or_issuer_identifier",
            "ticker_rename_linkage",
            "dual_class_issuer_linkage",
            "ambiguous_ticker_with_two_rows_in_one_snapshot",
            "sector_classification_asof",
            "common_equity_only_universe_etfs_are_not_screened_out",
            "non_us_listings_and_private_companies",
        ],
        "cannot_answer_scope": (
            "Scoped to this adapter's REGISTERED artifact "
            "(data/symbol_directory/snapshots/), not to the repo as a whole."
        ),
        "planes_not_read_by_this_adapter": [
            {
                "path": str(_data_dir(root) / CIK_MAP_RELPATH),
                "carries": "sec_cik_issuer_identifier_per_ticker",
                "written_by": "collectors.symbol_directory",
                "why_not_read": (
                    "Outside the registered writer artifact for "
                    "registrations.security_identity_and_corporate_actions, which names "
                    "snapshots/ only. A CIK is a permanent issuer id and WOULD link a "
                    "dual-class pair or a rename, so the unavailables above are limited to "
                    "this artifact rather than claimed for the repo."
                ),
            }
        ],
        "coverage_gap_note": (
            "The seasonality panel spans up to 25 complete years; this plane's snapshots span "
            "days to weeks. For nearly all historical work every question above is answered "
            "unavailable, and that is the correct answer rather than a degraded one."
        ),
        "price_adjustment": price_adjustment_vintage(),
    }


__all__ = [
    "ADAPTER_IMPLEMENTATION_STATE",
    "ADAPTER_REGISTRATION",
    "COVERAGE_CLASS_ROSTER",
    "COVERAGE_CLASS_UNREGISTERED",
    "COVERAGE_SCHEMA",
    "ETF_SCREEN_STATE",
    "LIQUIDITY_SCREEN_STATE",
    "MAX_FORWARD_CARRY_DAYS",
    "MEMBERSHIP_RULES",
    "REASON_ASOF_BEYOND_STORE",
    "REASON_CORPORATE_ACTIONS",
    "REASON_NO_SNAPSHOT",
    "REASON_REGISTRY_MISSING",
    "REASON_REGISTRY_NO_LIMITATIONS",
    "REASON_REGISTRY_UNREADABLE",
    "REASON_SNAPSHOT_UNREADABLE",
    "REASON_SYMBOL_ABSENT",
    "REASON_SYMBOL_AMBIGUOUS",
    "SNAPSHOT_DATE_BASIS",
    "SNAPSHOT_REQUIRED_COLUMNS",
    "SNAPSHOT_SUBPATH",
    "UNRESOLVED_BLOCKER",
    "UniverseRead",
    "corporate_actions_asof",
    "coverage_report",
    "earliest_snapshot",
    "latest_snapshot",
    "membership_asof",
    "price_adjustment_vintage",
    "resolve_security_asof",
    "snapshot_dates",
    "snapshot_store",
]
