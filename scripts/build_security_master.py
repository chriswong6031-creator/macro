#!/usr/bin/env python3
"""Materialize the security master + the time-scoped vendor alias table (Data OS DOS-1.1).

WHAT THIS PRODUCES, AND WHY IT IS TWO FILES
-------------------------------------------
``data/reference/security_master.parquet``  one row per SECURITY — the stored,
authoritative ``security_id``.  ``lib/dataos/identity.py`` is the ALLOCATOR (a pure
derivation, no counter, no hash); this artifact is the AUTHORITY (the value that was
minted and stored).  ``research/MASTERMIND_SECURITY_MASTER_SPEC.md`` §4 states the
rule this script implements as code: **mint once and store** — a later correction to
inception facts appends an ALIAS, it never re-mints a stable id, because two ids for
one thing is the exact defect the spine exists to end.

``data/reference/vendor_aliases.parquet``  one row per
``(vendor, vendor_symbol, security_id, valid_from, valid_to)``, half-open in time:
``valid_from`` INCLUSIVE, ``valid_to`` EXCLUSIVE (spec §6;
``lib/dataos/identity.py::AliasRow``).  An inclusive end would make the changeover day
ambiguous, and 2026-01-14 is exactly the day the MMC/MRSH answer has to be
unambiguous.

``data/reference/_receipt.json``  ``code_version`` (git sha), per-input sha256, row
counts, ``generated_at``, and the coverage numbers.  Coverage is a REPORTED NUMBER,
never an asserted completeness: DOS-1.1's acceptance bullet is "N of M members
resolved, K unresolved, listed by name".

THE TWO RENAMES THIS EXISTS TO ANSWER
-------------------------------------
**MMC -> MRSH, 2026-01-14.**  Marsh McLennan changed its NYSE symbol; same listing,
same CUSIP (``lib/ticker_aliases.py`` module docstring).  Yahoo migrated the whole
history onto MRSH while ``scripts/fetch_basket_ohlcv`` carried only the FI->FISV
entry, so ``data/baskets/ohlcv/MMC.parquet`` came to never exist and the ``insurance``
basket rendered 18/19 members and ``us_sector_financials`` 75/76 for SEVEN MONTHS.
Nothing went red; the site simply drew one fewer line.  A timeless two-entry dict can
say "MMC means MRSH" but cannot say "MMC MEANT MMC before 2026-01-14", so a backfill
through it silently re-labels the past.  Both symbols resolve here to ONE id,
``SEC:US-XNYS-MMC``, and the table answers DIFFERENTLY either side of the boundary.

**SATS -> ECHO, 2026-06-24.**  EchoStar.  ``engine/ledger_identity.py`` module
docstring measures the live defect: ``data/signal_archive/track_record.parquet``
carries SATS 128 rows and ECHO 128 rows with IDENTICAL ``(date, type)`` key sets and
all 39 identity/entry columns byte-identical — one physical fire logged twice — so
every hit-rate, forward-return and drawdown statistic over that ledger DOUBLE-WEIGHTS
one name.  A table that knew MMC and not SATS would have reproduced the exact
fragmentation being fixed, so SATS is not optional here.

WHAT THIS SCRIPT DOES NOT DO
----------------------------
* It does not become an authority.  Nothing reads these artifacts yet except
  ``tests/test_dataos_security_master.py``; DOS-1.2 declares the seams, and the master
  becomes authority only at spec §11.4.  Display-tier accrual needs no gauntlet.
* It does not invent an inception DATE.  Spec §4: there is **no in-repo US listing-date
  source**, and back-dating one from a store's earliest bar would be a fabricated fact
  (``lib/symbol_directory_receipts.py`` forbids that class of synthesis outright).
  ``effective_at`` is therefore the earliest DATED OBSERVATION in this repo's committed
  seeds that the security existed — see :func:`_effective_at`.  It is NOT a listing date
  and must never be read as one.
* It does not resolve a venue by guessing.  ``KNOWN_MICS`` in
  ``lib/dataos/identity.py`` is closed on purpose; a symbol whose venue has no MIC
  there is reported UNRESOLVED by name rather than minted onto a guessed venue.
  Getting a MIC wrong mints a different, stable, wrong id — spec §5: "the one mistake
  this scheme cannot self-heal".
* It creates no new store, no control plane and no second identity reader
  (gate G4).  ``lib/dataos/identity.VendorAliasTable`` is the only reader, and this
  builder round-trips every alias row through it before writing, so an ambiguous table
  fails HERE rather than in a consumer.

Usage::

    python3 scripts/build_security_master.py              # build + write
    python3 scripts/build_security_master.py --report     # build + write + full census
    python3 scripts/build_security_master.py --dry-run    # build, print, write NOTHING
    python3 scripts/build_security_master.py --out DIR    # default: data/reference
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config, ticker_aliases  # noqa: E402
from lib.dataos.identity import (  # noqa: E402
    XASE,
    XNAS,
    XNYS,
    AliasRow,
    IdentityError,
    ListingKey,
    VendorAliasTable,
    issuer_id,
    security_id,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
# Resolved against THIS FILE, never the cwd: the nightly, the CI packs and a
# developer shell all run from different directories (same reasoning as
# lib/dataos/registry.REGISTRY_PATH).
DEFAULT_OUT = ROOT / "data" / "reference"
MASTER_NAME = "security_master.parquet"
ALIASES_NAME = "vendor_aliases.parquet"
RECEIPT_NAME = "_receipt.json"

CONSTITUENTS = ROOT / "data" / "breadth" / "constituents.parquet"
MEMBERSHIP = ROOT / "data" / "baskets" / "membership.json"
DELISTED_LEDGER = ROOT / "config" / "delisted_symbols.yml"
CONFIG_YML = ROOT / "config.yml"
TICKER_ALIASES_PY = ROOT / "lib" / "ticker_aliases.py"
SYMBOL_DIR_SNAPSHOTS = ROOT / "data" / "symbol_directory" / "snapshots"

#: The exact column order written to each artifact.  These are the ``schema:`` keys of
#: ``reference.security_master`` / ``reference.vendor_aliases`` in
#: ``config/dataset_registry.yml``, in declaration order, and
#: ``tests/test_dataos_security_master.py`` pins the equality both ways — the registry
#: is the contract, not a description of whatever this script happened to emit.
MASTER_COLUMNS = (
    "security_id",
    "issuer_id",
    "listing_key",
    "country",
    "mic",
    "inception_code",
    "effective_at",
    "ingested_at",
)
ALIAS_COLUMNS = (
    "vendor",
    "vendor_symbol",
    "security_id",
    "valid_from",
    "valid_to",
    "ingested_at",
)

#: Non-string column kinds, from the same ``schema:`` blocks.  Rows are carried in
#: memory as ISO STRINGS and cast only at write, so a re-read of a committed artifact
#: compares byte-for-byte against a freshly derived row instead of "Timestamp vs str".
#: That equality is what makes the builder idempotent rather than merely deterministic.
MASTER_DTYPES = {"effective_at": "datetime", "ingested_at": "datetime"}
ALIAS_DTYPES = {"valid_from": "date", "valid_to": "date", "ingested_at": "datetime"}

# ── Vendors (symbol SPACES) ───────────────────────────────────────────────────
# A "vendor" here is a symbol space, which is why one of the three is this repo.
# Spec §6's column note lists `yahoo` … `nasdaq_symdir` … `exchange` as vendors; the
# repo's own stable key is the space every site surface, page slug and ledger row is
# written in, so it needs a name in the same table or the translation has no LHS.
VENDOR_YAHOO = "yahoo"          # the symbol REQUESTED from Yahoo (lib.ticker_aliases.fetch_symbol)
VENDOR_MEMBERSHIP = "membership"  # this repo's stable join key (universe seeds + breadth.ticker_fixups)
VENDOR_LEDGER = "ledger"        # the per-ticker signal-archive key space (quality.ticker_key_migrations)

# ── Venue authority ───────────────────────────────────────────────────────────
#: otherlisted.txt single-character exchange codes, per the legend the collector that
#: fetches the file records at ``collectors/symbol_directory.py:184-185``:
#: "A=NYSE MKT (AMEX), N=NYSE, P=NYSE Arca, Z=BATS, V=Investors Exchange".
#: Only the three that have a MIC in ``lib/dataos/identity.KNOWN_MICS`` are mapped.
#: Arca / BATS / IEX are deliberately ABSENT rather than approximated: a name listed
#: there is reported unresolved by name, because widening the closed MIC list is a
#: decision a human makes once, in a diff — not something a seed loader guesses.
EXCHANGE_MIC = {
    "NASDAQ": XNAS,
    "N": XNYS,
    "A": XASE,
}

#: `exchange:` values used by the exit ledger (`config/delisted_symbols.yml`), which
#: spells venues out because it is hand-written from SEC filings.  The exit ledger is
#: consulted FIRST for a delisted name: the symbol directory is a CURRENT listing set
#: (`scripts/check_symbol_rename_drift.py:36-42`), so it structurally cannot carry a
#: security whose tape has ended.
DELISTED_EXCHANGE_MIC = {
    "NYSE": XNYS,
    "NYSE AMERICAN": XASE,
    "NASDAQ": XNAS,
}

DEFAULT_COUNTRY = "US"


# ── The curated rename events ─────────────────────────────────────────────────
@dataclass(frozen=True)
class RenameEvent:
    """One DATED symbol change inside one symbol space.

    The repo's machine-readable maps (`lib.ticker_aliases.YAHOO_FETCH_ALIASES`,
    `breadth.ticker_fixups`, `quality.ticker_key_migrations`) are all TIMELESS — they
    carry the pair but not the day.  The days live in prose beside them, so they are
    lifted here with a `file:LINE`-grade citation each.  This is the ONLY authored data
    in this builder; everything else is derived from a committed seed.
    """

    old: str
    new: str
    on: date
    vendors: tuple[str, ...]
    evidence: str


RENAME_EVENTS: tuple[RenameEvent, ...] = (
    RenameEvent(
        old="MMC",
        new="MRSH",
        on=date(2026, 1, 14),
        # Yahoo LED this rename — it migrated the whole history onto MRSH, which is why
        # lib/ticker_aliases fetches under MRSH and the membership's MMC started 404-ing.
        # The membership space did NOT move: breadth.ticker_fixups pins MRSH back to MMC
        # ("MMC stays the stored key — 13 open qledger claims and the baskets membership
        # are keyed on it", config.yml), so no `membership` row is dated here.
        vendors=(VENDOR_YAHOO,),
        evidence=(
            "lib/ticker_aliases.py module docstring (MMC->MRSH 2026-01-14, symbol change "
            "only: same listing, same CUSIP; Yahoo serves the NEW symbol); "
            "config.yml breadth.ticker_fixups MRSH->MMC"
        ),
    ),
    RenameEvent(
        old="SATS",
        new="ECHO",
        on=date(2026, 6, 24),
        # Both the vendor space and the repo's LEDGER key space moved on this one:
        # data/stocks/SATS.parquet no longer exists, data/stocks/ECHO.parquet holds the
        # full spliced history, and quality.ticker_key_migrations ratifies SATS->ECHO as
        # the key the stack now stores.  That double move is what produced the
        # double-logged ledger this table exists to make visible.
        vendors=(VENDOR_YAHOO, VENDOR_LEDGER),
        evidence=(
            "engine/ledger_identity.py module docstring (EchoStar renamed SATS->ECHO "
            "effective 2026-06-24; SATS 128 rows and ECHO 128 rows with identical "
            "(date,type) key sets and 39 byte-identical identity columns); "
            "config.yml quality.ticker_key_migrations SATS: ECHO"
        ),
    ),
)

#: Renames the repo records WITHOUT a citable date.  Fiserv renamed FISV->FI in 2023
#: and the vendor LAGS it: Yahoo still serves the series under FISV
#: (`lib/ticker_aliases.YAHOO_FETCH_ALIASES["FI"] == "FISV"`), and so does the exchange
#: symbol directory (the 2026-08-10 snapshot carries FISV, "Fiserv, Inc. - Common
#: Stock", and carries no FI at all).  There is therefore NO vendor-side changeover day
#: to scope, and no in-repo source for the 2023 date, so both rows stay OPEN-BOUNDED.
#: An open bound is the ABSENCE of a claim about the boundary; inventing 2023-07-01 to
#: make the table look complete would be exactly the fabricated fact §4 forbids.
UNDATED_RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "FISV",
        "FI",
        "lib/ticker_aliases.py YAHOO_FETCH_ALIASES FI->FISV (vendor LAGS the rename); "
        "config.yml breadth.ticker_fixups FISV->FI; no in-repo date for the 2023 change",
    ),
)


# ── Small helpers ─────────────────────────────────────────────────────────────
def unmodelled_renames(fixups: dict[str, str], migrations: dict[str, str]) -> list[str]:
    """Rename pairs the repo's own maps carry that this builder does not model.

    The failure mode this closes is the one the whole task exists to end: a rename gets
    added to ``breadth.ticker_fixups`` or ``quality.ticker_key_migrations`` — both
    TIMELESS, both one line — and the time-scoped table silently keeps answering with
    the old pairing, because nothing asks it to notice.  A loud line beats a silent gap;
    the reader still has to supply the DATE and the evidence by hand, which is the
    curation step (``detectors propose, curation ratifies``) and not something a seed
    loader may guess.
    """
    modelled = {frozenset((e.old, e.new)) for e in RENAME_EVENTS}
    modelled |= {frozenset((old, new)) for old, new, _ in UNDATED_RENAMES}
    missing: list[str] = []
    for label, mapping in (("breadth.ticker_fixups", fixups),
                           ("quality.ticker_key_migrations", migrations)):
        for left, right in mapping.items():
            if frozenset((left, right)) not in modelled:
                missing.append(
                    f"{label} carries {left}->{right}, which scripts/build_security_master.py "
                    "does not model — add a RenameEvent (with its date and evidence) or an "
                    "UNDATED_RENAMES row, or the alias table answers the old pairing forever"
                )
    return missing


def _sha256(path: Path) -> str | None:
    """sha256 of a file, or None when it is absent (a missing seed is REPORTED)."""
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str | None:
    """HEAD sha, or None outside a git checkout.  Receipt provenance only.

    A run clock never enters an IDENTITY here (``DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY``)
    — ``code_version`` and ``generated_at`` live in the receipt, and the parquet bodies
    are byte-stable across re-runs on unchanged seeds.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return None
    sha = (out.stdout or "").strip()
    return sha or None


def _as_iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _class_notation_variants(symbol: str) -> tuple[str, ...]:
    """``BRK-B`` -> ``('BRK-B', 'BRK.B')``.

    Spec §6 names this seam explicitly: "``BRK-B``/``BRK.B`` become ``class_notation``".
    The two spellings are one security on one venue; only the vendor differs on the
    separator, so the directory lookup tries both before a name is called unresolved.
    """
    out = [symbol]
    if "-" in symbol:
        out.append(symbol.replace("-", "."))
    if "." in symbol:
        out.append(symbol.replace(".", "-"))
    seen: list[str] = []
    for item in out:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


# ── Seed loading ──────────────────────────────────────────────────────────────
def load_universe() -> dict[str, dict]:
    """``{membership key: {'sources': [...], 'first_seen': date|None}}``.

    The membership key is the repo's STABLE join key by charter — ``lib/ticker_aliases``
    says it outright: "Site copy, page slugs and ledger keys keep the membership
    ticker; this only ever decides what string goes to the vendor."
    """
    import pandas as pd  # local: keeps the module importable without pandas

    universe: dict[str, dict] = {}

    def note(ticker: str, source: str, seen: date | None) -> None:
        row = universe.setdefault(ticker, {"sources": [], "first_seen": None})
        if source not in row["sources"]:
            row["sources"].append(source)
        if seen is not None and (row["first_seen"] is None or seen < row["first_seen"]):
            row["first_seen"] = seen

    if CONSTITUENTS.exists():
        frame = pd.read_parquet(CONSTITUENTS)
        for ticker in frame.index.astype(str):
            note(ticker.strip().upper(), "breadth.constituents", None)

    if MEMBERSHIP.exists():
        payload = json.loads(MEMBERSHIP.read_text())
        for basket_id, basket in (payload.get("baskets") or {}).items():
            for member in basket.get("members") or []:
                ticker = str(member.get("ticker") or "").strip().upper()
                if not ticker:
                    continue
                added = member.get("added")
                seen: date | None = None
                if added:
                    try:
                        seen = date.fromisoformat(str(added))
                    except ValueError:
                        seen = None
                note(ticker, f"baskets.membership:{basket_id}", seen)

    return universe


def load_delisted() -> dict[str, dict]:
    """``{ticker: row}`` from the exit ledger, via its own reader (never re-parsed here)."""
    from lib import delisted_symbols

    delisted_symbols.ledger.cache_clear()
    return dict(delisted_symbols.ledger())


def load_directory() -> tuple[dict[str, str], str | None, Path | None]:
    """``({symbol: exchange code}, snapshot date, path)`` from the NEWEST snapshot.

    Newest by FILENAME stem, never by mtime: file mtimes in this repo are
    observer-stamped (a status sweep or a reflog expiry restamps whole trees), so an
    mtime-ordered "latest" is not a fact about the data.
    """
    import pandas as pd

    if not SYMBOL_DIR_SNAPSHOTS.is_dir():
        return {}, None, None
    files = sorted(p for p in SYMBOL_DIR_SNAPSHOTS.glob("*.parquet"))
    if not files:
        return {}, None, None
    newest = files[-1]
    frame = pd.read_parquet(newest)
    mapping = {
        str(sym).strip().upper(): str(exch).strip().upper()
        for sym, exch in zip(frame["symbol"], frame["exchange"])
    }
    return mapping, newest.stem, newest


def load_config_maps() -> tuple[dict[str, str], dict[str, str]]:
    """``(breadth.ticker_fixups, quality.ticker_key_migrations)`` — both TIMELESS maps."""
    raw = config.load()
    fixups = dict((raw.get("breadth") or {}).get("ticker_fixups") or {})
    migrations = dict((raw.get("quality") or {}).get("ticker_key_migrations") or {})
    return (
        {str(k).strip().upper(): str(v).strip().upper() for k, v in fixups.items()},
        {str(k).strip().upper(): str(v).strip().upper() for k, v in migrations.items()},
    )


# ── Resolution ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Resolution:
    """One membership key resolved (or not) to a venue and an inception code."""

    key: str
    listing_key: ListingKey | None
    inception_code: str | None
    exchange_symbol: str | None
    venue_source: str | None
    effective_at: date | None
    reason: str | None = None


def _inception_code(key: str, directory_symbol: str | None) -> str:
    """The code the listing carried at INCEPTION — never today's symbol.

    Walks the rename chains BACKWARDS to their ROOT: a dated event (MMC->MRSH,
    SATS->ECHO) or an undated one (FISV->FI) whose NEW side is this key means the OLD
    side is the earlier code this repo can evidence.

    The membership key can sit on EITHER side of a chain, and that asymmetry is the
    whole MMC case: the repo's key is the OLD symbol (``MMC``, pinned by
    ``breadth.ticker_fixups``) while the venue's current spelling is the NEW one
    (``MRSH``).  Reaching for the directory spelling there would mint
    ``SEC:US-XNYS-MRSH`` — a stable id built on today's symbol, which is exactly the
    defect §D2 forbids.  So a key that appears anywhere in a chain resolves through the
    chain; only a key no rename mentions falls back to the exchange spelling
    (``BRK.B``, not the vendor's ``BRK-B``), because the venue is the authority on its
    own code.
    """
    backwards: dict[str, str] = {}
    forwards: dict[str, str] = {}
    for event in RENAME_EVENTS:
        backwards[event.new] = event.old
        forwards[event.old] = event.new
    for old, new, _ in UNDATED_RENAMES:
        backwards[new] = old
        forwards[old] = new

    if key not in backwards and key not in forwards:
        return (directory_symbol or key).upper()

    seen = {key}
    current = key
    while current in backwards:
        nxt = backwards[current]
        if nxt in seen:  # a cycle is a config defect, never a loop here
            break
        seen.add(nxt)
        current = nxt
    return current


def _effective_at(universe_row: dict | None, delisted_row: dict | None,
                  snapshot_date: str | None) -> date | None:
    """The earliest DATED OBSERVATION in the committed seeds that this security existed.

    NOT an inception/listing date.  Spec §4 is explicit that no in-repo US listing-date
    source exists and that back-dating one from a store's earliest bar is fabrication,
    so this column carries the weaker, TRUE fact instead: the oldest day a committed
    seed in this repo says the name was there.  Candidates, earliest wins:

      * a basket member's ``added`` date (``data/baskets/membership.json``);
      * the exit ledger's ``last_session`` — the security demonstrably traded that day;
      * the symbol-directory snapshot date — a dated observation of a CURRENT listing.
    """
    candidates: list[date] = []
    if universe_row and universe_row.get("first_seen"):
        candidates.append(universe_row["first_seen"])
    if delisted_row and delisted_row.get("last_session"):
        try:
            candidates.append(date.fromisoformat(str(delisted_row["last_session"])))
        except ValueError:
            pass
    if snapshot_date:
        try:
            candidates.append(date.fromisoformat(snapshot_date))
        except ValueError:
            pass
    return min(candidates) if candidates else None


def resolve_universe(
    universe: dict[str, dict],
    delisted: dict[str, dict],
    directory: dict[str, str],
    snapshot_date: str | None,
) -> list[Resolution]:
    """Resolve every seed key to a venue + inception code, or say why it could not be.

    Venue precedence, and the reason for it:
      1. the EXIT LEDGER, for a delisted name — the symbol directory is a *current*
         listing set and structurally cannot carry a finished tape;
      2. the SYMBOL DIRECTORY, under the vendor symbol this repo actually fetches
         (``lib.ticker_aliases.fetch_symbol``) and under both class-notation spellings;
      3. UNRESOLVED, named in the report.
    """
    keys = sorted(set(universe) | set(delisted))
    out: list[Resolution] = []
    for key in keys:
        delisted_row = delisted.get(key)
        universe_row = universe.get(key)
        effective = _effective_at(universe_row, delisted_row, snapshot_date)

        mic: str | None = None
        venue_source: str | None = None
        directory_symbol: str | None = None
        reason: str | None = None

        if delisted_row:
            exchange = str(delisted_row.get("exchange") or "").strip().upper()
            mic = DELISTED_EXCHANGE_MIC.get(exchange)
            venue_source = f"config/delisted_symbols.yml:{key}.exchange={exchange or '<none>'}"
            if mic is None:
                reason = (
                    f"exit-ledger exchange {exchange or '<none>'!r} has no MIC in "
                    "lib/dataos/identity.KNOWN_MICS"
                )

        if mic is None and reason is None:
            fetch_symbol = ticker_aliases.fetch_symbol(key)
            for candidate in (
                *_class_notation_variants(fetch_symbol),
                *_class_notation_variants(key),
            ):
                exchange = directory.get(candidate)
                if exchange is None:
                    continue
                directory_symbol = candidate
                mic = EXCHANGE_MIC.get(exchange)
                venue_source = (
                    f"data/symbol_directory/snapshots/{snapshot_date}.parquet:"
                    f"{candidate}.exchange={exchange}"
                )
                if mic is None:
                    reason = (
                        f"listed on exchange code {exchange!r} "
                        "(collectors/symbol_directory.py:184-185: P=NYSE Arca, Z=BATS, "
                        "V=Investors Exchange) which has no MIC in "
                        "lib/dataos/identity.KNOWN_MICS"
                    )
                break
            else:
                reason = (
                    "absent from the newest symbol-directory snapshot under "
                    f"{fetch_symbol!r} or {key!r} (and from the exit ledger) — venue unknown"
                )

        if mic is None:
            out.append(Resolution(key, None, None, None, venue_source, effective, reason))
            continue

        code = _inception_code(key, directory_symbol)
        try:
            listing_key = ListingKey(DEFAULT_COUNTRY, mic, code)
        except IdentityError as exc:
            out.append(
                Resolution(key, None, None, directory_symbol, venue_source, effective, str(exc))
            )
            continue
        out.append(
            Resolution(key, listing_key, code, directory_symbol, venue_source, effective, None)
        )
    return out


# ── Alias construction ────────────────────────────────────────────────────────
def build_alias_rows(resolutions: list[Resolution], ids: dict[str, str]) -> list[AliasRow]:
    """Every ``(vendor, vendor_symbol, security_id, valid_from, valid_to)`` this seed set supports.

    Per resolved security, per vendor space, either ONE open-bounded row (the space
    never moved, or the day it moved is not citable) or a DATED PAIR straddling a
    rename.  The pair is what makes the table answer differently either side of the
    boundary, which is the whole deliverable.
    """
    dated: dict[tuple[str, str], RenameEvent] = {}
    for event in RENAME_EVENTS:
        for vendor in event.vendors:
            dated[(vendor, event.old)] = event
            dated[(vendor, event.new)] = event

    rows: list[AliasRow] = []
    for res in resolutions:
        if res.listing_key is None:
            continue
        sec = ids[res.key]

        spaces = {
            VENDOR_MEMBERSHIP: res.key,
            VENDOR_YAHOO: ticker_aliases.fetch_symbol(res.key),
        }
        # The ledger space only gets a row where its own ratified map has something to
        # say; inventing a `ledger` row for every name would claim a key space this
        # builder has not read.  quality.ticker_key_migrations is that map.
        for event in RENAME_EVENTS:
            if VENDOR_LEDGER in event.vendors and res.key in (event.old, event.new):
                spaces[VENDOR_LEDGER] = res.key

        for vendor, symbol in spaces.items():
            event = dated.get((vendor, symbol))
            if event is None:
                rows.append(AliasRow(vendor, symbol, sec, None, None))
                continue
            # valid_from INCLUSIVE / valid_to EXCLUSIVE: on the boundary day itself the
            # NEW symbol is the answer and the OLD one is already out of scope.
            rows.append(AliasRow(vendor, event.old, sec, None, event.on))
            rows.append(AliasRow(vendor, event.new, sec, event.on, None))

    # Dedup on the full grain — a security reached through two spaces that happen to
    # agree must not produce two identical rows (which would also read as an overlap).
    unique: dict[tuple, AliasRow] = {}
    for row in rows:
        unique[(row.vendor, row.vendor_symbol, row.security_id, row.valid_from, row.valid_to)] = row
    return [unique[k] for k in sorted(unique, key=lambda k: (k[0], k[1], k[2], str(k[3]), str(k[4])))]


# ── Mint-once-and-store ───────────────────────────────────────────────────────
def _read_existing(path: Path, columns: tuple[str, ...],
                   dtypes: dict[str, str]) -> list[dict]:
    """Committed rows as plain dicts of ISO strings / None.  The stored value is the AUTHORITY."""
    import pandas as pd

    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise SystemExit(
            f"{path} is missing declared column(s) {missing} — refusing to append to an "
            "artifact whose schema does not match config/dataset_registry.yml"
        )
    rows: list[dict] = []
    for record in frame[list(columns)].to_dict("records"):
        row: dict = {}
        for column in columns:
            value = record[column]
            kind = dtypes.get(column)
            if kind == "date":
                row[column] = _normalize_bound(value)
            elif kind == "datetime":
                row[column] = _normalize_datetime(value)
            else:
                row[column] = None if value is None else str(value)
        rows.append(row)
    return rows


def _iso_now() -> str:
    """UTC, second precision, NAIVE.

    CI runs UTC and a local-time stamp is a different fact, so the instant is UTC.  The
    offset is dropped because the registry declares ``datetime64[ns]`` with
    ``timezone: UTC`` — carrying "+00:00" in the in-memory string and losing it in the
    parquet would make a re-read differ from the row that wrote it, which is exactly the
    difference that would make an idempotent re-run look like a change.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()


def mint_master_rows(resolutions: list[Resolution], existing: list[dict],
                     now: str) -> tuple[list[dict], dict[str, str], list[str]]:
    """``(master rows, {membership key: security_id}, notes)`` — existing ids never move.

    The join back into a committed master is by ``listing_key``: the master's grain is
    the security, and it deliberately carries no membership-key column (that belongs to
    the alias table).  A stored row therefore wins on EVERY column, including a
    ``security_id`` that no longer matches what the derivation would produce today —
    that is precisely "mint once and store", and re-deriving it would be a re-mint.

    A correction that changes the INCEPTION CODE cannot be detected here (it changes the
    listing key, so it reads as a new security).  Per §D2 that correction is expressed
    by APPENDING an alias, never by rewriting a master row — and this builder never
    deletes a row it did not re-derive, so nothing is silently dropped either.
    """
    by_listing_key = {str(row["listing_key"]): dict(row) for row in existing}
    out: dict[str, dict] = {k: dict(v) for k, v in by_listing_key.items()}
    ids: dict[str, str] = {}
    notes: list[str] = []

    minted_by: dict[str, str] = {}
    for res in resolutions:
        if res.listing_key is None:
            continue
        rendered = res.listing_key.render()
        stored = by_listing_key.get(rendered)
        if stored is not None:
            ids[res.key] = str(stored["security_id"])
        else:
            sec = security_id(res.listing_key)
            if rendered in minted_by and minted_by[rendered] != res.key:
                notes.append(
                    f"collision: {minted_by[rendered]!r} and {res.key!r} both mint "
                    f"{sec} — spec §5 resolves a genuine ticker REUSE with an explicit "
                    "'.2' disambiguator, which is an operator ratification, not a guess"
                )
                ids[res.key] = sec
                continue
            minted_by[rendered] = res.key
            out[rendered] = {
                "security_id": sec,
                "issuer_id": issuer_id(res.listing_key),
                "listing_key": rendered,
                "country": res.listing_key.country,
                "mic": res.listing_key.mic,
                "inception_code": res.inception_code,
                # midnight UTC: the registry declares datetime64[ns] and the evidence is
                # day-grained, so the time-of-day is a padding artefact, never a claim.
                "effective_at": (
                    None if res.effective_at is None
                    else f"{res.effective_at.isoformat()}T00:00:00"
                ),
                "ingested_at": now,
            }
            ids[res.key] = sec

    rows = [out[k] for k in sorted(out)]
    return rows, ids, notes


def merge_alias_rows(fresh: list[AliasRow], existing: list[dict], now: str) -> list[dict]:
    """Append-only on the declared grain; a committed row keeps its ``ingested_at``."""
    merged: dict[tuple, dict] = {}
    for row in existing:
        key = (
            str(row["vendor"]),
            str(row["vendor_symbol"]),
            str(row["security_id"]),
            _normalize_bound(row["valid_from"]),
            _normalize_bound(row["valid_to"]),
        )
        merged[key] = {
            "vendor": key[0],
            "vendor_symbol": key[1],
            "security_id": key[2],
            "valid_from": key[3],
            "valid_to": key[4],
            "ingested_at": str(row["ingested_at"]),
        }
    for row in fresh:
        key = (row.vendor, row.vendor_symbol, row.security_id,
               _as_iso(row.valid_from), _as_iso(row.valid_to))
        if key in merged:
            continue
        merged[key] = {
            "vendor": key[0],
            "vendor_symbol": key[1],
            "security_id": key[2],
            "valid_from": key[3],
            "valid_to": key[4],
            "ingested_at": now,
        }
    return [merged[k] for k in sorted(merged, key=lambda k: (k[0], k[1], k[2], str(k[3]), str(k[4])))]


def _normalize_bound(value) -> str | None:
    """A stored date bound as an ISO date string, or None.

    ``NaT``/``NaN``/``''`` all mean OPEN BOUND, and every one of them is a shape pandas
    can hand back for a parquet null depending on the column's inferred dtype — so all
    three collapse here rather than in each caller.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text or text.lower() in {"nat", "nan", "none", "<na>"}:
        return None
    return text[:10]


def _normalize_datetime(value) -> str | None:
    """A stored timestamp as a naive-UTC ISO string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
        return stamp.replace(microsecond=0).isoformat()
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00"
    text = str(value).strip()
    if not text or text.lower() in {"nat", "nan", "none", "<na>"}:
        return None
    return text.replace(" ", "T")[:19]


# ── Writing ───────────────────────────────────────────────────────────────────
def _write_parquet(rows: list[dict], columns: tuple[str, ...], path: Path,
                   dtypes: dict[str, str]) -> None:
    """Write the declared columns in the declared order, with the declared dtypes."""
    import pandas as pd

    data: dict[str, object] = {}
    for column in columns:
        values = [row.get(column) for row in rows]
        kind = dtypes.get(column)
        if kind == "datetime":
            data[column] = pd.to_datetime(pd.Series(values, dtype="object"), errors="coerce")
        elif kind == "date":
            data[column] = pd.Series(
                [None if v is None else date.fromisoformat(str(v)[:10]) for v in values],
                dtype="object",
            )
        else:
            data[column] = pd.Series(
                [None if v is None else str(v) for v in values], dtype="object"
            )
    frame = pd.DataFrame(data, columns=list(columns))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def build(out_dir: Path, dry_run: bool = False) -> dict:
    """Do the whole build and return the receipt payload (written unless ``dry_run``)."""
    universe = load_universe()
    delisted = load_delisted()
    directory, snapshot_date, snapshot_path = load_directory()
    fixups, migrations = load_config_maps()

    resolutions = resolve_universe(universe, delisted, directory, snapshot_date)
    resolved = [r for r in resolutions if r.listing_key is not None]
    unresolved = [r for r in resolutions if r.listing_key is None]

    now = _iso_now()
    master_path = out_dir / MASTER_NAME
    aliases_path = out_dir / ALIASES_NAME

    seed_notes = unmodelled_renames(fixups, migrations)

    master_rows, ids, notes = mint_master_rows(
        resolutions, _read_existing(master_path, MASTER_COLUMNS, MASTER_DTYPES), now
    )
    fresh_aliases = build_alias_rows(resolutions, ids)
    alias_rows = merge_alias_rows(
        fresh_aliases, _read_existing(aliases_path, ALIAS_COLUMNS, ALIAS_DTYPES), now
    )

    # THE ONLY READER, used as the validator: an ambiguous table must fail HERE, at
    # write time, not in whatever consumer first asks it a question.
    table = VendorAliasTable.from_records(alias_rows)

    receipt = {
        "dataset_ids": ["reference.security_master", "reference.vendor_aliases"],
        "producer": "scripts/build_security_master.py",
        "code_version": _git_sha(),
        "generated_at": now,
        "inputs": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (
                CONSTITUENTS, MEMBERSHIP, DELISTED_LEDGER, CONFIG_YML, TICKER_ALIASES_PY,
                *( [snapshot_path] if snapshot_path is not None else [] ),
            )
        },
        "symbol_directory_snapshot": snapshot_date,
        "row_counts": {
            "security_master": len(master_rows),
            "vendor_aliases": len(alias_rows),
            "vendor_alias_rows_readable": len(table.rows),
        },
        "coverage": {
            "total": len(resolutions),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "unresolved_names": [r.key for r in unresolved],
        },
        "seed_counts": {
            "universe_keys": len(universe),
            "delisted_keys": len(delisted),
            "directory_symbols": len(directory),
            "ticker_fixups": len(fixups),
            "ticker_key_migrations": len(migrations),
        },
        "rename_events": [
            {"old": e.old, "new": e.new, "on": e.on.isoformat(),
             "vendors": list(e.vendors), "evidence": e.evidence}
            for e in RENAME_EVENTS
        ],
        "undated_renames": [
            {"old": old, "new": new, "evidence": why} for old, new, why in UNDATED_RENAMES
        ],
        "notes": seed_notes + notes,
        "authority": "display_only — DOS-1.1 materializes the spine; nothing reads it as authority yet",
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_parquet(master_rows, MASTER_COLUMNS, master_path, MASTER_DTYPES)
        _write_parquet(alias_rows, ALIAS_COLUMNS, aliases_path, ALIAS_DTYPES)
        (out_dir / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    receipt["_resolutions"] = resolutions  # in-process only; never serialized
    return receipt


# ── Reporting ─────────────────────────────────────────────────────────────────
def coverage_line(receipt: dict) -> str:
    """``N/M resolved, K unresolved`` — the number DOS-1.1 asks to be REPORTED."""
    cov = receipt["coverage"]
    return f"{cov['resolved']}/{cov['total']} resolved, {cov['unresolved']} unresolved"


def _report(receipt: dict, verbose: bool) -> None:
    resolutions = receipt.get("_resolutions") or []
    print(coverage_line(receipt))
    unresolved = [r for r in resolutions if r.listing_key is None]
    for res in unresolved:
        print(f"  UNRESOLVED {res.key}: {res.reason}")
    if unresolved:
        # Bare print at column 0, never through a logger: a prefixing formatter emits
        # "WARNING ::warning …" and GitHub silently drops it
        # (tests/test_gh_annotation_line_start.py).
        print(
            f"::warning title=security-master-coverage::{coverage_line(receipt)} — "
            f"unresolved: {', '.join(r.key for r in unresolved)}",
            flush=True,
        )
    for note in receipt.get("notes") or []:
        print(f"::warning title=security-master-note::{note}", flush=True)

    if not verbose:
        return
    print(f"  security_master rows: {receipt['row_counts']['security_master']}")
    print(f"  vendor_aliases rows:  {receipt['row_counts']['vendor_aliases']}")
    print(f"  symbol directory:     {receipt['symbol_directory_snapshot']}")
    for event in receipt["rename_events"]:
        print(
            f"  dated rename {event['old']}->{event['new']} on {event['on']} "
            f"in {','.join(event['vendors'])}"
        )
    for undated in receipt["undated_renames"]:
        print(f"  undated rename {undated['old']}->{undated['new']} (open-bounded rows)")
    for name, digest in sorted(receipt["inputs"].items()):
        print(f"  input {name} sha256={digest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="output directory (default: data/reference)")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and report, write nothing")
    parser.add_argument("--report", action="store_true",
                        help="full census: row counts, rename events, input hashes")
    args = parser.parse_args(argv)

    receipt = build(Path(args.out), dry_run=args.dry_run)
    _report(receipt, verbose=args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
