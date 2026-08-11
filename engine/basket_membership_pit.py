"""Point-in-time (PIT) membership history for the two CN basket suites.

WHY THIS EXISTS
---------------
``research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`` §2.12 names
this the **weakest joint** of the whole relay program: the THS concept-board
membership used by the 12-month ignition/chase study was a single 2026-07-08
snapshot applied BACKWARD over the entire window, and the two PIT snapshots that
do exist differ by 7.7% of member-slots across 8 days.  Any theme/relay
construction measured on back-applied membership is look-ahead-contaminated, so
§5 W-C charters this store as the prerequisite for ANY future relay-construction
promotion.  It ships display/infrastructure tier and grades nothing.

WHAT IT IS
----------
An append-only parquet per suite — ``data/<suite>/membership_history.parquet`` —
with one row per ``(snapshot_date, basket_id, ticker)``, keep-FIRST on that key
so a re-run on the same day can never duplicate or rewrite a stamped day.  The
curated suite (``baskets_china``) is snapshotted the same way as the machine
suite (``baskets_china_ths``): same columns, same semantics, so a consumer needs
one reader, not two.

CONTENT DEDUP (why every calendar day is not a row set)
------------------------------------------------------
A full THS snapshot is ~3,500 member rows.  Stamping one every night would add
~1.3M rows/year that say nothing — membership moves on the vendor's schedule,
not the trading calendar.  So a snapshot_date is stamped only when the
membership set DIFFERS from the newest one already stored (``members_sha`` over
the normalized ``(basket_id, ticker, added, removed)`` tuples, so a cosmetic
re-serialization of membership.json is not mistaken for a membership change).
This is the same content-dedup the sibling JSON side-car in
``scripts/build_baskets_china_ths.py`` already uses, and it leaves the PIT read
identical: **the membership in force at date D is the newest snapshot ≤ D.**

LANE DISCIPLINE
---------------
House law (CLAUDE.md): nightly/asia is the sole advancer of ledgers; render
lanes discard ``data/`` writes.  Every writer here goes through ``_lane_ok``,
which is FAIL-CLOSED and PER-SUITE: each suite names the ONE collection lane
allowed to advance it (``SUITE_LANE``) and everything else — a foreign lane, an
unrecognised lane, an unknown suite, or no lane at all — is refused before any
write.  It does NOT mirror ``engine.china_standout_track.append_board``'s
permissive ``lane is not None`` form; see ``_lane_ok`` for why keep-FIRST makes
that default unsafe here.

THREE SUITES, TWO LANES (GMI W1a)
---------------------------------
The two CN suites are advanced by the asia collection lane (asia-close.yml,
``CN_LANE=asia``).  The US suite ``baskets`` — the 49 hand-curated US thematic
baskets in ``data/baskets/membership.json`` — is advanced by the US nightly
(daily.yml, ``COLLECT_LANE=nightly``), which is the only lane that collects and
commits US ``data/``.  The gate is per-suite precisely because "asia" is the
wrong answer for a US store and "nightly" is the wrong answer for a CN one: a
single global lane name would have to be permissive enough to admit both, and
this store cannot afford a permissive gate (keep-FIRST, below).  US rows carry
the same COLUMNS; ``name_zh`` is simply empty for them — one reader, not two.

TWO SIDE-CAR SHAPES (and why the store says which one it used)
--------------------------------------------------------------
The dated JSON side-cars are not uniform.  ``2026-06-30.json`` predates the
byte-copy the seeder writes today: it is the RAW vendor concept dump keyed by
the Chinese board name, ~9,069 member-slots.  ``2026-07-08.json`` is a
membership.json copy — the SEEDED, capped subset the engine actually tracks,
~3,532 slots.  Both are true about their own population; they are not the same
population.  Differencing naively across that boundary reports ~61% "drift",
which is mostly the seeding cap.  So every row records ``source_shape`` and
``members_asof`` returns it with an explicit note when the resolved snapshot's
shape is not the store's newest.  The alternative — dropping the older file —
would delete half of the only real PIT evidence the program has.

THE READER'S CONTRACT (the load-bearing half)
---------------------------------------------
``members_asof`` ALWAYS reports which basis it answered on.  When the history
predates the requested date — the store's birth is forward-only, so every date
before its first snapshot is uncovered — it falls back to the CURRENT
membership.json and stamps ``pit=False``.  A consumer that silently treats a
fallback answer as point-in-time is exactly the look-ahead bug this store was
built to end, so the flag is not optional metadata: it is the answer.  The same
goes for ``source_shape``: a caveat that does not travel with the answer is a
caveat nobody reads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SUITE_THS = "baskets_china_ths"
SUITE_CURATED = "baskets_china"
SUITE_US = "baskets"

#: The CN pair.  Kept as ``SUITES`` because it is the default of ``append_all``
#: and the set every existing caller and test means by "both suites".
SUITES: tuple[str, ...] = (SUITE_THS, SUITE_CURATED)
#: The US suite, advanced by a DIFFERENT lane — hence its own tuple.
SUITES_US: tuple[str, ...] = (SUITE_US,)
ALL_SUITES: tuple[str, ...] = (*SUITES, *SUITES_US)

#: The ONE collection lane permitted to advance each suite's PIT store.
#: Fail-closed by construction: a suite absent from this map has NO lane that
#: may write it, so a typo'd or newly-added suite refuses until it is declared.
SUITE_LANE: dict[str, str] = {
    SUITE_THS: "asia",       # asia-close.yml band A, CN_LANE=asia
    SUITE_CURATED: "asia",   # ditto
    SUITE_US: "nightly",     # daily.yml engine job, COLLECT_LANE=nightly
}

MEMBERSHIP_FILE = "membership.json"
HISTORY_FILE = "membership_history.parquet"
SNAPSHOT_DIR = "snapshots"

#: Mutable cadence stamp inside each suite's snapshot dir — deliberately NOT part
#: of the append-only history.  See ``write_cadence_stamp``.  The leading
#: underscore keeps it out of the ``????-??-??.json`` dated-side-car namespace.
CADENCE_FILE = "_cadence.json"

#: Parquet column order.  ``added``/``removed`` are the source's own PIT dates and
#: are carried through so a reader can resolve membership BETWEEN two snapshots.
COLUMNS: tuple[str, ...] = (
    "snapshot_date", "suite", "basket_id", "ticker",
    "added", "removed", "name_zh", "members_sha", "source_shape",
)

#: Which document shape a row was read from — the honest bound on how PIT it is.
#: ``membership`` = a membership.json (baskets + per-member added/removed dates).
#: ``ths_concept_dump`` = the raw vendor concept dump the earliest side-car uses:
#: members are point-in-time, but the concept -> basket_id mapping is today's.
SHAPE_MEMBERSHIP = "membership"
SHAPE_CONCEPT_DUMP = "ths_concept_dump"

#: Keep-first key (masterplan §5 W-C: "append-only store, keep-first per date").
KEY: tuple[str, ...] = ("snapshot_date", "basket_id", "ticker")

_BASIS_PIT = "pit_snapshot"
_BASIS_CURRENT = "current_membership"
_BASIS_UNKNOWN = "unknown_basket"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def membership_path(suite: str) -> Path:
    """Live membership document for ``suite``."""
    return config.data_dir() / suite / MEMBERSHIP_FILE


def history_path(suite: str) -> Path:
    """Append-only PIT history parquet for ``suite``."""
    return config.data_dir() / suite / HISTORY_FILE


def snapshot_dir(suite: str) -> Path:
    """Dated JSON side-car directory for ``suite``."""
    return config.data_dir() / suite / SNAPSHOT_DIR


def cadence_path(suite: str) -> Path:
    """The suite's mutable cadence stamp (see ``write_cadence_stamp``)."""
    return snapshot_dir(suite) / CADENCE_FILE


def dated_snapshots(suite: str) -> list[Path]:
    """The suite's dated side-cars, oldest→newest.

    The ONE place the dated-side-car namespace is defined.  ``????-??-??.json``
    excludes the ``_cadence.json`` stamp and any other underscore-prefixed
    working file — an important exclusion rather than a cosmetic one, because
    ``_`` sorts AFTER every digit in ASCII, so a plain ``*.json`` glob taking a
    max/last would resolve the stamp as the NEWEST snapshot.
    """
    d = snapshot_dir(suite)
    try:
        return sorted(p for p in d.glob("????-??-??.json")) if d.is_dir() else []
    except Exception as exc:  # noqa: BLE001
        log.warning("basket_membership_pit: snapshot scan failed for %s (%s)", suite, exc)
        return []


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _text(v: object) -> str | None:
    """Trimmed string, or None for null/blank/NaN. Never raises.

    A parquet round-trip turns a missing ``removed`` date into NaN, not None, and
    ``str(nan)`` is the truthy string "nan" — so the NaN check has to come first
    or every never-removed member reads as removed on a date called "nan".
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("none", "nan", "nat", "null"):
        return None
    return s


def _baskets(doc: object) -> dict:
    """The ``baskets`` mapping of a membership document, or {}."""
    if not isinstance(doc, dict):
        return {}
    b = doc.get("baskets")
    return b if isinstance(b, dict) else {}


#: One normalized member slot: (basket_id, ticker, added, removed, name_zh).
_Member = tuple[str, str, str, str, str]


def _members_from_membership(doc: object) -> list[_Member]:
    """Member slots from a membership.json-shaped document."""
    out: list[_Member] = []
    for basket_id, basket in _baskets(doc).items():
        if not isinstance(basket, dict):
            continue
        for m in basket.get("members") or []:
            if not isinstance(m, dict):
                continue
            ticker = _text(m.get("ticker")) or _text(m.get("code"))
            if not ticker:
                continue
            out.append((str(basket_id), ticker,
                        _text(m.get("added")) or "", _text(m.get("removed")) or "",
                        _text(m.get("name_zh")) or ""))
    return out


def _concept_index(suite: str) -> dict[str, str]:
    """``ths_concept`` (raw 同花顺 board name) -> basket_id, from live membership."""
    out: dict[str, str] = {}
    for basket_id, basket in _baskets(_read_json(membership_path(suite))).items():
        if not isinstance(basket, dict):
            continue
        concept = _text(basket.get("ths_concept"))
        if concept:
            out[concept] = str(basket_id)
    return out


def _members_from_concept_dump(doc: object, concept_to_basket: dict[str, str]) -> list[_Member]:
    """Member slots from the RAW THS concept dump shape ``{concept: [{ticker,name}]}``.

    The earliest side-car (2026-06-30) predates the membership.json byte-copy the
    seeder writes today, so it is keyed by the vendor's Chinese concept name.  It
    is also HALF of the program's only real PIT evidence — the pair whose 7.7%
    member-slot drift is §2.12's receipt — so it is read rather than skipped.

    HONEST BOUND, recorded in the ``source_shape`` column: the MEMBERS are
    point-in-time, but the concept -> basket_id mapping is today's, so which
    concepts we track is a current-basis choice.  A concept we do not track today
    contributes nothing; the caller logs how many were dropped.
    """
    out: list[_Member] = []
    if not isinstance(doc, dict):
        return out
    for concept, members in doc.items():
        basket_id = concept_to_basket.get(str(concept).strip())
        if not basket_id or not isinstance(members, list):
            continue
        for m in members:
            if not isinstance(m, dict):
                continue
            ticker = _text(m.get("ticker")) or _text(m.get("code"))
            if not ticker:
                continue
            # No added/removed in this shape — absent, not "unknown-as-a-date".
            out.append((basket_id, ticker, "", "", _text(m.get("name")) or ""))
    return out


def _sha_of(members: list[_Member]) -> str:
    """sha256 over the SORTED (basket_id, ticker, added, removed) slots.

    The dedup basis.  Sorting + normalizing is what makes the hash describe the
    MEMBERSHIP rather than the file's byte layout: a re-ordered or re-indented
    membership.json hashes identically and is correctly not stamped as a new
    snapshot.  ``name_zh`` is excluded — a vendor renaming a company is not a
    membership change.
    """
    payload = json.dumps(sorted({m[:4] for m in members}), ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def members_sha(doc: object) -> str:
    """sha256 of a membership.json-shaped document's member set."""
    return _sha_of(_members_from_membership(doc))


def _rows_from_members(members: list[_Member], snapshot_date: str, suite: str,
                       source_shape: str) -> list[dict]:
    """Flatten normalized member slots into PIT rows for one snapshot_date."""
    sha = _sha_of(members)
    return [{
        "snapshot_date": str(snapshot_date),
        "suite": suite,
        "basket_id": basket_id,
        "ticker": ticker,
        "added": added or None,
        "removed": removed or None,
        "name_zh": name_zh or None,
        "members_sha": sha,
        "source_shape": source_shape,
    } for basket_id, ticker, added, removed, name_zh in members]


def _rows_from_doc(doc: object, snapshot_date: str, suite: str) -> list[dict]:
    """Flatten a membership.json-shaped document into PIT rows."""
    return _rows_from_members(_members_from_membership(doc), snapshot_date, suite,
                              SHAPE_MEMBERSHIP)


def _read_json(path: Path) -> object | None:
    """Parse a JSON file, or None. Never raises."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad file degrades to "no snapshot"
        log.warning("basket_membership_pit: unreadable %s (%s)", path, exc)
        return None


def read_history(suite: str) -> pd.DataFrame:
    """The PIT history frame for ``suite`` (empty frame when absent/unreadable)."""
    p = history_path(suite)
    try:
        if not p.exists():
            return pd.DataFrame(columns=list(COLUMNS))
        df = pd.read_parquet(p)
        for col in COLUMNS:                       # schema union with older writes
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("basket_membership_pit: history read failed for %s (%s)", suite, exc)
        return pd.DataFrame(columns=list(COLUMNS))


def _latest_sha(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """(snapshot_date, members_sha) of the NEWEST stored snapshot, or (None, None)."""
    if df.empty or "snapshot_date" not in df.columns:
        return None, None
    dates = df["snapshot_date"].astype(str)
    newest = dates.max()
    row = df[dates == newest]
    if row.empty:
        return None, None
    return str(newest), _text(row.iloc[0].get("members_sha"))


# ---------------------------------------------------------------------------
# Cadence stamp (mutable, deliberately outside the append-only history)
# ---------------------------------------------------------------------------

def write_cadence_stamp(suite: str, *, writer: str, membership_sha: str | None,
                        now: str | None = None) -> Path | None:
    """Rewrite ``<suite>/snapshots/_cadence.json`` — "this writer ran, and here is what it saw".

    WHY A SEPARATE STAMP.  Both snapshot writers are content-deduped: when
    membership has not changed they write nothing and log a dedup skip.  That is
    correct for the history and catastrophic for monitoring, because a writer that
    is deduping and a writer that has been UNWIRED FOR A MONTH leave the identical
    trace on disk — nothing.  That is precisely how the THS side-car store sat at
    two snapshots while its nightly step ran green ~35 nights in a row: the step
    hashed today's membership.json against the last side-car, matched, and skipped,
    every night, because nothing upstream was refreshing membership.json at all.

    So liveness gets its own artifact.  It is MUTABLE (rewritten every run) and
    therefore explicitly NOT part of the append-only history: it records the last
    time the writer ran, never what membership was on some past date.  It lives
    inside the snapshots dir so a reader needs one path, and is named with a
    leading ``_`` so it can never collide with — or be globbed as — a dated
    side-car (``dated_snapshots`` is the one enumerator, and it is date-shaped).

    ``membership_sha`` is the writer's own dedup basis (sha256 of the membership
    document it just hashed), so a stale ``last_snapshot_date`` next to a moving
    ``membership_sha`` says "membership is churning but nothing is being stamped",
    which is a different fault from "nothing is running".  Never raises.
    """
    try:
        p = cadence_path(suite)
        p.parent.mkdir(parents=True, exist_ok=True)
        dated = dated_snapshots(suite)
        payload = {
            "schema": "basket_membership_cadence.v1",
            "suite": suite,
            "writer": writer,
            "checked_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "membership_sha": membership_sha,
            "last_snapshot_date": dated[-1].stem if dated else None,
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except Exception as exc:  # noqa: BLE001 — a liveness stamp never breaks a build
        log.warning("basket_membership_pit: cadence stamp failed for %s (%s)", suite, exc)
        return None


def read_cadence(suite: str) -> dict | None:
    """The suite's cadence stamp, or None when absent/unreadable."""
    blob = _read_json(cadence_path(suite))
    return blob if isinstance(blob, dict) else None


# ---------------------------------------------------------------------------
# Writers (one collection lane per suite)
# ---------------------------------------------------------------------------

def _lane_ok(lane: str | None, what: str, *, suite: str) -> bool:
    """The per-suite collection-lane gate for every writer here — FAIL-CLOSED.

    ``lane == SUITE_LANE[suite]`` writes.  EVERYTHING else refuses: a FOREIGN lane
    (the US nightly reaching for a CN suite, or asia reaching for the US one), an
    unrecognised lane, a suite with no declared lane, and — the case that matters —
    no lane at all.  This deliberately does NOT mirror
    ``china_standout_track.append_board``'s permissive ``lane is not None`` form.
    append_board can afford that default because a board row is re-derivable and a
    second lane rewriting it changes nothing.  This store cannot: it is append-only
    and keep-FIRST on ``(snapshot_date, basket_id, ticker)`` (masterplan §5 W-C), and
    it is content-deduped, so the FIRST lane to stamp a date owns that snapshot
    FOREVER — a later lane's view of the same day is silently discarded, and the
    published PIT answer for every date from then on is whatever the first writer saw.

    Which is why the permissive form was not merely loose but dead: the one production
    caller resolved its lane as ``os.environ.get("CN_LANE", "asia")``, so every context
    that leaves ``CN_LANE`` unset — a hand-run, a future render-lane adopter — arrived
    here as the asia lane itself and the gate never fired.

    The lane NAMES come from what the workflows already pass, and each resolver is
    itself defaultless: ``.github/workflows/asia-close.yml`` (band A) sets
    ``CN_LANE: asia``, read by ``scripts.build_baskets_china_ths._membership_pit_lane``;
    ``.github/workflows/daily.yml`` (engine job) sets ``COLLECT_LANE: nightly``, read by
    ``scripts.build_baskets._membership_pit_lane``.  Every other context resolves None
    and lands on the refusal below.
    """
    want = SUITE_LANE.get(suite)
    if want is not None and lane == want:
        return True
    log.info("basket_membership_pit: %s REFUSED (lane=%r, suite %s is advanced only by "
             "lane %r) — one collection lane per suite is the sole advancer of the PIT "
             "store", what, lane, suite, want)
    return False


def _append_rows(suite: str, rows: list[dict]) -> int:
    """Append rows keep-FIRST on KEY. Returns rows ADDED (0 on no-op/failure)."""
    if not rows:
        return 0
    try:
        new = pd.DataFrame(rows, columns=list(COLUMNS))
        p = history_path(suite)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = read_history(suite)
            before = len(prior)
            cols = list(dict.fromkeys([*COLUMNS, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=cols), new.reindex(columns=cols)],
                ignore_index=True,
            ).drop_duplicates(subset=list(KEY), keep="first")
        else:
            before = 0
            combined = new
        combined = combined.sort_values(list(KEY), kind="stable").reset_index(drop=True)
        combined.to_parquet(p, index=False)
        return int(len(combined) - before)
    except Exception as exc:  # noqa: BLE001 — a PIT store never breaks a build
        log.warning("basket_membership_pit: append failed for %s (%s)", suite, exc)
        return 0


def append_snapshot(suite: str, *, asof: str | None = None,
                    lane: str | None = None) -> dict:
    """Stamp today's membership of ``suite`` into the PIT history.

    Content-deduped: a snapshot_date is stamped only when the membership set
    differs from the newest one stored.  Keep-first on
    ``(snapshot_date, basket_id, ticker)`` makes a same-day re-run a no-op even
    when the content check is bypassed.  Never raises.
    """
    result = {"suite": suite, "written": False, "rows_added": 0,
              "snapshot_date": None, "reason": None}
    if not _lane_ok(lane, f"{suite} snapshot", suite=suite):
        result["reason"] = f"lane={lane}"
        return result
    doc = _read_json(membership_path(suite))
    if not _baskets(doc):
        result["reason"] = "membership.json missing or empty"
        log.warning("basket_membership_pit: %s — %s", suite, result["reason"])
        return result

    date = _text(asof) or pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    result["snapshot_date"] = date
    prior = read_history(suite)
    if not prior.empty and (prior["snapshot_date"].astype(str) == date).any():
        result["reason"] = "date already stamped"
        return result
    last_date, last_sha = _latest_sha(prior)
    sha = members_sha(doc)
    if last_sha is not None and last_sha == sha:
        result["reason"] = f"membership unchanged since {last_date}"
        log.info("basket_membership_pit: %s — %s (dedup skip)", suite, result["reason"])
        return result

    added = _append_rows(suite, _rows_from_doc(doc, date, suite))
    result["written"] = added > 0
    result["rows_added"] = added
    log.info("basket_membership_pit: %s stamped %s (+%d rows)", suite, date, added)
    return result


def backfill_from_json_snapshots(suite: str, *, lane: str | None = None) -> dict:
    """Seed the history from the dated JSON side-cars already on disk.

    ``data/baskets_china_ths/snapshots/YYYY-MM-DD.json`` predates this store and
    holds the only two real PIT snapshots the program has (the 2026-06-30 /
    2026-07-08 pair whose 7.7% member-slot drift is §2.12's evidence).  Reading
    them in costs one pass and is what lets the store answer PIT questions from
    its first night instead of from its birth date.  Keep-first, so this is
    idempotent and can never overwrite a stamped day.
    """
    result = {"suite": suite, "dates": [], "rows_added": 0,
              "unparsed": [], "reason": None}
    if not _lane_ok(lane, f"{suite} backfill", suite=suite):
        result["reason"] = f"lane={lane}"
        return result
    files = dated_snapshots(suite)
    if not files:
        result["reason"] = "no dated JSON snapshots"
        return result
    have = set(read_history(suite)["snapshot_date"].astype(str))
    concepts = _concept_index(suite)
    rows: list[dict] = []
    for f in files:
        if f.stem in have:
            continue
        doc = _read_json(f)
        members = _members_from_membership(doc)
        shape = SHAPE_MEMBERSHIP
        if not members:
            # Older side-cars are the raw vendor concept dump, not a
            # membership.json copy. Read them rather than dropping half the
            # evidence pair — see _members_from_concept_dump for the bound.
            members = _members_from_concept_dump(doc, concepts)
            shape = SHAPE_CONCEPT_DUMP
        if not members:
            # A dated file we could not read is a HOLE in the record. It must
            # never vanish silently — a store that quietly covers less than it
            # appears to is worse than one that covers nothing.
            result["unparsed"].append(f.name)
            log.warning("basket_membership_pit: %s snapshot %s matched no known "
                        "shape — NOT backfilled", suite, f.name)
            continue
        rows.extend(_rows_from_members(members, f.stem, suite, shape))
        result["dates"].append(f.stem)
    if not rows:
        result["reason"] = "already covered" if not result["unparsed"] else "no readable snapshot"
        return result
    result["rows_added"] = _append_rows(suite, rows)
    log.info("basket_membership_pit: %s backfilled %s (+%d rows%s)",
             suite, ",".join(result["dates"]), result["rows_added"],
             f", {len(result['unparsed'])} unparsed" if result["unparsed"] else "")
    return result


def append_all(*, asof: str | None = None, lane: str | None = None,
               suites: tuple[str, ...] = SUITES) -> dict:
    """Backfill + stamp each suite in ``suites``. The single nightly entry point.

    ``lane`` is threaded straight through to both writers and is FAIL-CLOSED there
    (see ``_lane_ok``): omit it and nothing is written, in any suite.

    ``suites`` defaults to the CN pair — the asia lane's call, unchanged.  The US
    nightly passes ``SUITES_US``.  It is a parameter rather than a global sweep
    because the lane gate is per-suite: a single call naming one lane can only
    ever advance the suites that lane owns, so sweeping all three from either
    nightly would log two guaranteed refusals every run and train the reader to
    ignore the refusal line that matters.
    """
    out: dict = {}
    for suite in suites:
        try:
            backfill = backfill_from_json_snapshots(suite, lane=lane)
            snap = append_snapshot(suite, asof=asof, lane=lane)
            out[suite] = {"backfill": backfill, "snapshot": snap}
        except Exception as exc:  # noqa: BLE001 — one suite never breaks the other
            log.warning("basket_membership_pit: %s failed (%s)", suite, exc)
            out[suite] = {"error": f"{type(exc).__name__}"}
    return out


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

def _active_at(row: pd.Series, date: str) -> bool:
    """Was this member row in force on ``date``?

    Uses the source's OWN ``added``/``removed`` dates, which is what makes a
    read BETWEEN two snapshots correct rather than merely nearest-neighbour.
    A blank/absent date is treated as "no constraint" — never as an exclusion.
    """
    added = _text(row.get("added"))
    removed = _text(row.get("removed"))
    if added and added > date:
        return False
    return not (removed and removed <= date)


def members_asof(basket_id: str, date: str, *, suite: str = SUITE_THS) -> dict:
    """Members of ``basket_id`` in force on ``date`` — WITH its membership basis.

    Returns ``{basket_id, suite, asof, members, pit, basis, snapshot_date,
    source_shape, note}``.

    ``pit`` is the contract.  ``True`` means the answer came from a stored
    snapshot dated ≤ ``date`` (point-in-time, safe to measure on).  ``False``
    means the store does not cover ``date`` — the history is forward-only from
    its birth — and the answer is the CURRENT membership applied backward, which
    is exactly the look-ahead basis §2.12 flagged.  A caller that measures on a
    ``pit=False`` answer is contaminating its own study; the flag exists so that
    is a decision, never an accident.

    ``source_shape`` is the SECOND basis, and it matters for the same reason.
    The earliest side-car is the raw vendor concept dump (every name on the
    board); every later one is the seeded membership (the capped subset the
    engine actually tracks).  Both are true about their own population, but they
    are not the same population, so differencing across the boundary measures
    the seeding cap as well as real membership churn.  ``note`` says so
    explicitly whenever the resolved snapshot's shape is not the store's newest.
    Never raises.
    """
    date = str(date)
    out = {"basket_id": str(basket_id), "suite": suite, "asof": date,
           "members": [], "pit": False, "basis": _BASIS_CURRENT,
           "snapshot_date": None, "source_shape": None, "note": ""}
    try:
        df = read_history(suite)
        covered = df[df["snapshot_date"].astype(str) <= date] if not df.empty else df
        if not covered.empty:
            snap = str(covered["snapshot_date"].astype(str).max())
            rows = covered[
                (covered["snapshot_date"].astype(str) == snap)
                & (covered["basket_id"].astype(str) == str(basket_id))
            ]
            out.update(snapshot_date=snap, basis=_BASIS_PIT, pit=True)
            if rows.empty:
                # The snapshot is real and does NOT contain this basket. Say which
                # of the two very different things that means.
                if str(basket_id) in _baskets(_read_json(membership_path(suite))):
                    out["note"] = f"basket not present in the {snap} snapshot"
                else:
                    out.update(pit=False, basis=_BASIS_UNKNOWN,
                               note=f"unknown basket_id for suite {suite}")
                return out
            shape = _text(rows.iloc[0].get("source_shape")) or SHAPE_MEMBERSHIP
            out["source_shape"] = shape
            newest = _text(
                df.sort_values("snapshot_date").iloc[-1].get("source_shape")
            ) or SHAPE_MEMBERSHIP
            if shape != newest:
                out["note"] = (
                    f"snapshot {snap} is the {shape} population, the store's newest "
                    f"is {newest} — differencing across that boundary also measures "
                    "the seeding cap, not membership churn alone"
                )
            out["members"] = sorted({
                str(r["ticker"]) for _i, r in rows.iterrows() if _active_at(r, date)
            })
            return out

        # ---- uncovered: fall back to CURRENT membership, flagged ----
        doc = _read_json(membership_path(suite))
        basket = _baskets(doc).get(str(basket_id))
        first = str(df["snapshot_date"].astype(str).min()) if not df.empty else None
        if not isinstance(basket, dict):
            out.update(basis=_BASIS_UNKNOWN,
                       note=f"unknown basket_id for suite {suite}")
            return out
        out["members"] = sorted({
            t for t in (
                _text(m.get("ticker")) or _text(m.get("code"))
                for m in (basket.get("members") or []) if isinstance(m, dict)
            ) if t
        })
        out["note"] = (
            f"PIT history starts {first}; {date} predates coverage — current "
            "membership applied backward (look-ahead basis)"
            if first else
            "no PIT history yet — current membership applied backward "
            "(look-ahead basis)"
        )
        return out
    except Exception as exc:  # noqa: BLE001 — a reader never raises into a build
        log.warning("basket_membership_pit: members_asof failed (%s)", exc)
        out["note"] = f"read failed ({type(exc).__name__})"
        return out


def coverage(suite: str = SUITE_THS) -> dict:
    """Compact store description: {suite, snapshots, first, last, rows}."""
    df = read_history(suite)
    if df.empty:
        return {"suite": suite, "snapshots": 0, "first": None, "last": None, "rows": 0}
    dates = sorted(set(df["snapshot_date"].astype(str)))
    return {"suite": suite, "snapshots": len(dates), "first": dates[0],
            "last": dates[-1], "rows": len(df)}
