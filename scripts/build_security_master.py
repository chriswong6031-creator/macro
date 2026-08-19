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
unambiguous.  It carries FIVE vendor spaces in TWO FAMILIES — three that answer "what
was it called THEN" and two that answer "what do I call it TODAY, for a bar of any
date".  Confusing those two is the seven-month MMC outage in a new costume, so the
families have different names and a test pins them apart; see the vendor block below.

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
    parse_listing_key,
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
ISSUER_MASTER_NAME = "issuer_master.parquet"
ISSUER_MIGRATIONS_NAME = "issuer_migrations.parquet"

CONSTITUENTS = ROOT / "data" / "breadth" / "constituents.parquet"
MEMBERSHIP = ROOT / "data" / "baskets" / "membership.json"
DELISTED_LEDGER = ROOT / "config" / "delisted_symbols.yml"
CONFIG_YML = ROOT / "config.yml"
TICKER_ALIASES_PY = ROOT / "lib" / "ticker_aliases.py"
SYMBOL_DIR_SNAPSHOTS = ROOT / "data" / "symbol_directory" / "snapshots"
#: Weekly SEC registrant map (V4-D2B1 §1) — read-only, collector-owned
#: (``data/symbol_directory/**`` is never written by this script).
CIK_MAP_DIR = ROOT / "data" / "symbol_directory" / "cik_map"
#: Operator-ratified CIKs allowed to form a NEW multi-member issuer group (V4-D2B1
#: FIX 5 / M3) — see :func:`_load_issuer_group_allowlist`.
ISSUER_GROUP_ALLOWLIST_PATH = ROOT / "config" / "issuer_group_allowlist.yml"

#: The exact column order written to each artifact.  These are the ``schema:`` keys of
#: ``reference.security_master`` / ``reference.vendor_aliases`` in
#: ``config/dataset_registry.yml``, in declaration order, and
#: ``tests/test_dataos_security_master.py`` pins the equality both ways — the registry
#: is the contract, not a description of whatever this script happened to emit.
#:
#: The issuer axis (``issuer_state``/``issuer_cik``/``issuer_evidence_snapshot``) is
#: V4-D2B1: it sits next to ``issuer_id`` because the four columns together are one
#: semantic unit (the value, its evidentiary status, the evidence CIK, and the
#: snapshot it was observed in).
MASTER_COLUMNS = (
    "security_id",
    "issuer_id",
    "issuer_state",
    "issuer_cik",
    "issuer_evidence_snapshot",
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
#: ``reference.issuer_master`` — one row per distinct non-null issuer_id (spec §3).
ISSUER_MASTER_COLUMNS = (
    "issuer_id",
    "cik",
    "legal_name",
    "n_securities",
    "evidence_source",
    "evidence_snapshot",
    "status",
    "era",
)
#: ``reference.issuer_migrations`` — append-only, one row per security whose issuer_id
#: VALUE changed in an era (spec §3).
ISSUER_MIGRATIONS_COLUMNS = (
    "security_id",
    "listing_key",
    "old_issuer_id",
    "new_issuer_id",
    "reason",
    "evidence_cik",
    "evidence_snapshot",
    "migrated_at",
)

#: Non-string column kinds, from the same ``schema:`` blocks.  Rows are carried in
#: memory as ISO STRINGS and cast only at write, so a re-read of a committed artifact
#: compares byte-for-byte against a freshly derived row instead of "Timestamp vs str".
#: That equality is what makes the builder idempotent rather than merely deterministic.
MASTER_DTYPES = {"effective_at": "datetime", "ingested_at": "datetime",
                 "issuer_evidence_snapshot": "date"}
ALIAS_DTYPES = {"valid_from": "date", "valid_to": "date", "ingested_at": "datetime"}
ISSUER_MASTER_DTYPES = {"evidence_snapshot": "date", "n_securities": "int"}
ISSUER_MIGRATIONS_DTYPES = {"evidence_snapshot": "date", "migrated_at": "datetime"}

#: Columns a PRE-D2B1 committed ``security_master.parquet`` will not carry yet.
#: ``_read_existing`` fills these with ``None`` instead of refusing, which is what
#: makes ``issuer_state is None`` the "not yet migrated by this era" marker the D2B1
#: era stage (:func:`apply_issuer_correction`) reads (spec §4 "era-inside-the-builder
#: idempotent migration").
ISSUER_AXIS_COLUMNS = frozenset({"issuer_state", "issuer_cik", "issuer_evidence_snapshot"})

#: The one authorized issuer-identity correction era (spec §4).
ERA_ISSUER_CORRECTION = "issuer_semantic_correction_v1"

# ── Vendors (symbol SPACES) — TWO CLOCKS, never one ───────────────────────────
# A "vendor" here is a symbol space, which is why several of them are this repo.
# Spec §6's column note lists `yahoo` … `nasdaq_symdir` … `exchange` as vendors; the
# repo's own stable key is the space every site surface, page slug and ledger row is
# written in, so it needs a name in the same table or the translation has no LHS.
#
# THE DISTINCTION THIS TABLE MUST NOT COLLAPSE (adversarial review, 2026-08-13).  A
# rename gives a security two names, and there are two DIFFERENT questions about them:
#
#   HISTORICAL NAMING — "what did this space call the security ON 2020-01-02?"  Answered
#     by a DATED pair straddling the changeover.  This is the question a backfill of a
#     dated archive asks, and the one a timeless dict cannot answer at all.
#   CURRENT CATALOG — "what string do I use TODAY to fetch or store this security's
#     series, for data of ANY date?"  Answered by ONE OPEN-BOUNDED row at today's
#     symbol, because the vendor and the store both migrated the WHOLE history onto the
#     new name — Yahoo serves Marsh's entire tape under MRSH and `data/stocks/ECHO.parquet`
#     holds EchoStar's spliced history back to 2008.
#
# Reading the historical answer as if it were the current one is the seven-month MMC
# outage in a new costume: a §11.4 backfill that requested "MMC" for 2020 because the
# table said Yahoo called it MMC then would get "possibly delisted, no price data found".
# So the two families are SEPARATE VENDOR SPACES with names that say which clock they
# run on, and `tests/test_dataos_security_master.py` pins them apart.

# ── historical-naming spaces (dated across a rename) ──
VENDOR_YAHOO = "yahoo"            # what Yahoo CALLED the security on a given day
VENDOR_MEMBERSHIP = "membership"  # what THIS REPO keyed it on that day (universe seeds)
VENDOR_LEDGER = "ledger"          # the per-ticker signal-archive key space on that day

# ── current-catalog spaces (one open-bounded row at today's symbol) ──
#: The string to REQUEST from Yahoo today, for a bar of ANY date.  Reproduces
#: `lib.ticker_aliases.fetch_symbol` exactly — the row family that lets this dataset
#: claim `supersedes: lib/ticker_aliases.py` without lying.
VENDOR_YAHOO_FETCH = "yahoo_fetch"
#: The key this repo's per-ticker stores and ledger rows carry today, for data of ANY
#: date — `lib.ticker_aliases.store_key`'s side of the same seam.  `data/stocks/`,
#: `data/baskets/ohlcv/` and `data/signal_archive/` rows written after a rename are all
#: keyed here, which is why a dedup over the archive has to ask THIS space, not `ledger`.
VENDOR_STORE = "store"

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
        # The vendor space AND both of this repo's own key spaces moved on this one:
        # data/stocks/SATS.parquet no longer exists, data/stocks/ECHO.parquet holds the
        # full spliced history, and quality.ticker_key_migrations ratifies SATS->ECHO as
        # the key the stack now stores.  That double move is what produced the
        # double-logged ledger this table exists to make visible.
        #
        # `membership` is DATED here and open at MMC above, and the asymmetry is the
        # fact, not an inconsistency: `breadth.ticker_fixups` pins MRSH back to MMC (the
        # repo key deliberately did NOT move), while `quality.ticker_key_migrations`
        # ratifies SATS->ECHO (it DID).  Leaving membership open at today's ECHO would
        # re-label EchoStar's whole repo-side past — the exact timeless-map defect the
        # time-scoping exists to end, shipped inside the artifact that ends it.
        vendors=(VENDOR_YAHOO, VENDOR_LEDGER, VENDOR_MEMBERSHIP),
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

#: Identity cases whose current symbol is verified but whose historical alias cannot be
#: represented by the builder's symbol-pair-only ``RenameEvent`` yet.  Fail closed:
#: minting an open-bounded row would answer a known prior issuer as the current one.
#:
#: ``B`` is not a plain ``GOLD -> B`` rename.  Barrick changed NYSE GOLD to B on
#: 2025-05-09, while Gold.com (formerly NASDAQ AMRK) reused NYSE GOLD on 2025-12-02.
#: A global GOLD/B pair would therefore collapse Barrick and Gold.com into one security.
#: Moreover, Barnes Group was the prior NYSE B holder until its 2025-01-27 delisting, so
#: an open historical B alias is independently false.  The full repair needs one
#: identity-scoped continuation plus one ratified reuse break; until that registered DOS
#: amendment exists, B remains named in coverage as unresolved and mints no row.
DEFERRED_IDENTITY_KEYS: dict[str, dict[str, str]] = {
    "B": {
        "reason": (
            "verified identity-scoped event required: NYSE B belonged to Barnes Group "
            "through 2025-01-27; Barrick Mining changed NYSE GOLD->B effective "
            "2025-05-09; Gold.com then reused NYSE GOLD effective 2025-12-02. A bare "
            "RenameEvent would collapse different issuers, so B is fail-closed pending "
            "a registered identity-scoped continuation+reuse amendment"
        ),
        "evidence": (
            "SEC Barnes Group 2025-01-27 8-K/Form 25; Barrick Mining 2025-05-07 "
            "Form 6-K Exhibit 99.2; Gold.com 2025-11-12 AMRK->NYSE GOLD transfer "
            "announcement; config/theme_graph_identity_breaks.yml GOLD"
        ),
    },
}

#: Already-materialized exception that this narrow roster repair only discloses.  The
#: committed GOLD alias predates the ratified break and is open-bounded across it.  The
#: append-only alias builder cannot close that row without producing an overlap, so the
#: same future identity-scoped DOS amendment must supersede it atomically.  Keeping this
#: in the receipt prevents a consumer from mistaking current coverage for temporal
#: authority in the interim.
DISCLOSED_IDENTITY_EXCEPTIONS: dict[str, dict[str, str]] = {
    "GOLD": {
        "reason": (
            "existing historical alias is not issuer-safe across 2025-12-02: the "
            "open GOLD row predates the ratified Gold.com reuse break and must not be "
            "treated as Barrick/miner history; replacement requires the same registered "
            "identity-scoped continuation+reuse amendment"
        ),
        "evidence": (
            "config/theme_graph_identity_breaks.yml GOLD; config.yml "
            "quality.reused_ticker_acks.GOLD"
        ),
    },
}


# ── Small helpers ─────────────────────────────────────────────────────────────
def unmodelled_renames(fixups: dict[str, str], migrations: dict[str, str]) -> list[str]:
    """Rename pairs the repo's own maps carry that this builder does not model.

    The failure mode this closes is the one the whole task exists to end: a rename gets
    added to ``breadth.ticker_fixups`` or ``quality.ticker_key_migrations`` — both
    TIMELESS, both one line — and the time-scoped table silently keeps answering with
    the old pairing, because nothing asks it to notice.  The reader still has to supply
    the DATE and the evidence by hand, which is the curation step (``detectors propose,
    curation ratifies``) and not something a seed loader may guess.

    A returned line is a FAILURE, not a hint: :func:`main` exits non-zero while this is
    non-empty, and both maps live in root ``config.yml``, which ``house-law-registry``
    declares in its manifest scope so a one-line rename PR actually reaches this check.
    Both halves are load-bearing — an advisory detector nothing can reach is two ways of
    being decoration.
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


def _relpath(path: Path) -> str:
    """``path`` relative to :data:`ROOT` as a string, or the absolute path unchanged
    when it is not under ROOT at all (a test monkeypatching e.g. ``CIK_MAP_DIR`` at a
    ``tmp_path`` outside the checkout) — same guard as :func:`run_nightly_refresh`'s
    ``missing`` list, so a receipt key never raises on a path outside the repo."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


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


def load_cik_map() -> tuple[dict[str, tuple[str, str]], str | None, Path | None, frozenset[str]]:
    """``({current symbol: (zero-padded 10-digit CIK, SEC registrant title)}, snapshot
    date, path, ambiguous_tickers)`` from the NEWEST weekly
    ``data/symbol_directory/cik_map/*.parquet`` (V4-D2B1 §1).  Newest by FILENAME
    stem, never by mtime — same reasoning as :func:`load_directory`: this repo's
    file mtimes are observer-stamped.

    Ticker is a unique key on the MEASURED source (2026-08-18: 10,398 rows, 7,998
    CIKs, zero ticker->multi-CIK), but V4-D2B1 FIX 7 (m1) stops trusting that as an
    invariant: a ticker seen with MORE THAN ONE DISTINCT CIK in the same snapshot is
    REMOVED from ``mapping`` entirely (never a silent first-wins pick) and named in
    ``ambiguous_tickers`` instead, so a security whose evidence join hits it can be
    typed ``AMBIGUOUS`` — reserved, fail-closed, spec §3 — rather than silently
    resolving (or missing evidence) on whichever row happened to be read first.
    """
    import pandas as pd

    if not CIK_MAP_DIR.is_dir():
        return {}, None, None, frozenset()
    files = sorted(p for p in CIK_MAP_DIR.glob("*.parquet"))
    if not files:
        return {}, None, None, frozenset()
    newest = files[-1]
    frame = pd.read_parquet(newest)
    mapping: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for ticker, cik, title in zip(frame["ticker"], frame["cik"], frame["title"]):
        t = str(ticker).strip().upper()
        c = f"{int(cik):010d}"
        if t in ambiguous:
            continue
        existing = mapping.get(t)
        if existing is None:
            mapping[t] = (c, str(title))
        elif existing[0] != c:
            # A SECOND, DIFFERENT CIK for a ticker already seen — the ticker is
            # ambiguous on this snapshot; remove it rather than keep the first CIK.
            ambiguous.add(t)
            del mapping[t]
    return mapping, newest.stem, newest, frozenset(ambiguous)


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


def _current_symbol(inception_code: str) -> str:
    """Inception code -> this repo's own CURRENT symbol for the listing (V4-D2B1 §1
    evidence join law), walking the SAME rename records :func:`_inception_code` walks
    BACKWARD (``RENAME_EVENTS`` + ``UNDATED_RENAMES``) but FORWARDS to the chain's tip.

    This is deliberately this repo's OWN rename record, not "whatever Yahoo currently
    serves" — the two disagree for exactly the case the FI/FISV row exists to carry:
    Yahoo still serves the pre-rename ``FISV`` (the vendor lags), but this repo's own
    ``UNDATED_RENAMES`` records the venue-current name as ``FI``, and ``FI`` is the
    join key spec §1 asks for (the SEC registrant map is an independent, current
    observation of the same real-world fact — it does not follow Yahoo's lag).  For
    MMC/SATS, where the vendor LED the rename, this walk and Yahoo's current symbol
    agree (``MMC``->``MRSH``, ``SATS``->``ECHO``) because both ``RENAME_EVENTS`` rows
    were sourced from the same real-world change.

    A name no chain mentions returns itself unchanged — the venue is the authority on
    its own current spelling when this repo has recorded no rename for it.
    """
    forwards: dict[str, str] = {}
    for event in RENAME_EVENTS:
        forwards[event.old] = event.new
    for old, new, _ in UNDATED_RENAMES:
        forwards[old] = new

    seen = {inception_code}
    current = inception_code
    while current in forwards:
        nxt = forwards[current]
        if nxt in seen:  # a cycle is a config defect, never a loop here
            break
        seen.add(nxt)
        current = nxt
    return current


def _evidence_join_key(inception_code: str) -> str:
    """The CIK-map join key for one master row (V4-D2B1 §1): the security's current
    symbol (:func:`_current_symbol`), dot->dash normalized — the CIK map spells class
    suffixes with a dash (``BRK-B``) while the master spells them with a dot
    (``BRK.B``).  NEVER joins a historical/dated alias symbol against the CURRENT
    observation CIK map — that would be the two-clock violation spec §1 names (a
    reused ticker binding the wrong registrant); this function only ever answers
    "what is this security called today".
    """
    return _current_symbol(inception_code).replace(".", "-")


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

        deferred = DEFERRED_IDENTITY_KEYS.get(key)
        if deferred is not None:
            out.append(
                Resolution(
                    key,
                    None,
                    None,
                    None,
                    "operator-ratified fail-closed identity exception",
                    effective,
                    deferred["reason"],
                )
            )
            continue

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

    TWO FAMILIES, per the clock each answers (see the vendor block at the top):

    * HISTORICAL-NAMING spaces (``yahoo``, ``membership``, ``ledger``) get either ONE
      open-bounded row (the space never moved, or the day it moved is not citable) or a
      DATED PAIR straddling the rename.  The pair is what makes the table answer
      differently either side of the boundary, which is the whole deliverable.
    * CURRENT-CATALOG spaces (``yahoo_fetch``, ``store``) get exactly ONE OPEN-BOUNDED
      row at today's symbol, for every security, always.  A vendor that migrated the
      whole history onto the new name has no boundary to scope, and one row per security
      is also what ``VendorAliasTable`` requires: the constructor refuses two rows that
      overlap on ``(vendor, security_id)``, so a "current catalog" carrying both names
      open-bounded is not a thing this reader will accept — correctly, because "what do
      I call it today" has exactly one answer.
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

        historical = {
            VENDOR_MEMBERSHIP: res.key,
            VENDOR_YAHOO: ticker_aliases.fetch_symbol(res.key),
        }
        # The ledger space only gets a row where its own ratified map has something to
        # say; inventing a `ledger` row for every name would claim a key space this
        # builder has not read.  quality.ticker_key_migrations is that map.
        for event in RENAME_EVENTS:
            if VENDOR_LEDGER in event.vendors and res.key in (event.old, event.new):
                historical[VENDOR_LEDGER] = res.key

        # `res.key` IS the current store key: the universe seeds carry today's key
        # (ECHO, not SATS) and `breadth.ticker_fixups` pins a vendor-led rename back to
        # it (MRSH -> MMC), which is why data/baskets/ohlcv/MMC.parquet is the file that
        # exists while Yahoo is fetched under MRSH.
        current = {
            VENDOR_YAHOO_FETCH: ticker_aliases.fetch_symbol(res.key),
            VENDOR_STORE: res.key,
        }

        for vendor, symbol in historical.items():
            event = dated.get((vendor, symbol))
            if event is None:
                rows.append(AliasRow(vendor, symbol, sec, None, None))
                continue
            # valid_from INCLUSIVE / valid_to EXCLUSIVE: on the boundary day itself the
            # NEW symbol is the answer and the OLD one is already out of scope.
            rows.append(AliasRow(vendor, event.old, sec, None, event.on))
            rows.append(AliasRow(vendor, event.new, sec, event.on, None))

        for vendor, symbol in current.items():
            rows.append(AliasRow(vendor, symbol, sec, None, None))

    # Dedup on the full grain — a security reached through two spaces that happen to
    # agree must not produce two identical rows (which would also read as an overlap).
    unique: dict[tuple, AliasRow] = {}
    for row in rows:
        unique[(row.vendor, row.vendor_symbol, row.security_id, row.valid_from, row.valid_to)] = row
    return [unique[k] for k in sorted(unique, key=lambda k: (k[0], k[1], k[2], str(k[3]), str(k[4])))]


# ── Mint-once-and-store ───────────────────────────────────────────────────────
def _read_existing(path: Path, columns: tuple[str, ...],
                   dtypes: dict[str, str],
                   allow_missing: frozenset[str] = frozenset()) -> list[dict]:
    """Committed rows as plain dicts of ISO strings / None.  The stored value is the AUTHORITY.

    ``allow_missing`` names declared columns a COMMITTED file is allowed to lack —
    filled with ``None`` rather than raising.  This is the era-migration seam
    (V4-D2B1 §4): a pre-D2B1 ``security_master.parquet`` has no issuer-axis columns
    at all, and reading it should mean "not yet migrated by this era"
    (``issuer_state is None``), not a schema-mismatch refusal.  Every OTHER declared
    column absent from a committed file is still a hard failure — this does not widen
    the refusal to genuine schema drift.
    """
    import pandas as pd

    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    missing = [c for c in columns if c not in frame.columns]
    hard_missing = [c for c in missing if c not in allow_missing]
    if hard_missing:
        raise SystemExit(
            f"{path} is missing declared column(s) {hard_missing} — refusing to append to an "
            "artifact whose schema does not match config/dataset_registry.yml"
        )
    present = [c for c in columns if c not in missing]
    rows: list[dict] = []
    for record in frame[present].to_dict("records"):
        row: dict = {}
        for column in columns:
            if column in missing:
                row[column] = None
                continue
            value = record[column]
            kind = dtypes.get(column)
            if kind == "date":
                row[column] = _normalize_bound(value)
            elif kind == "datetime":
                row[column] = _normalize_datetime(value)
            else:
                # A nullable STRING column (e.g. issuer_id/issuer_cik) round-trips a
                # missing cell as a bare `value is None` check would miss: measured on
                # this stack (pandas 3.0.3), pd.read_parquet(...).to_dict("records")
                # hands back a genuine `float('nan')` for a null cell in a column that
                # also carries real strings, not `None` and not `pd.NA`. `is None`
                # alone let that NaN fall through to `str(value)` == the LITERAL
                # STRING "nan", silently corrupting every null issuer_id/issuer_cik on
                # the very next read. `pd.isna` catches None/NaN/NaT uniformly.
                row[column] = None if (value is None or pd.isna(value)) else str(value)
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

    ``issuer_id`` is deliberately NOT minted here (V4-D2B1 §2/§3): a brand-new row
    starts with ``issuer_id=None`` and no issuer axis — the abolished per-listing
    mint fallback.  :func:`apply_issuer_correction`, run once over the FULL returned
    row set, is the only place an issuer_id is ever assigned or repointed.  Every row
    read from ``existing`` is tagged ``_existed_before`` (an in-memory marker only —
    never a declared column, never written to parquet) so the era stage can tell a
    genuine issuer_id VALUE CHANGE (migration-worthy) from a brand-new mint's first
    assignment (not a migration: there was no prior stored value to migrate from).
    """
    by_listing_key = {str(row["listing_key"]): dict(row) for row in existing}
    out: dict[str, dict] = {}
    for k, v in by_listing_key.items():
        row = dict(v)
        row["_existed_before"] = True
        out[k] = row
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
                "issuer_id": None,
                "issuer_state": None,
                "issuer_cik": None,
                "issuer_evidence_snapshot": None,
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


# ── Issuer axis (V4-D2B1) — the one authorized correction era ─────────────────
def _exception_by_inception_code() -> dict[str, dict]:
    """``{inception code -> exception info}`` for both fail-closed families.

    Keyed the way a master row's own ``inception_code`` spells them: neither ``B``
    nor ``GOLD`` is inside any rename chain (:data:`RENAME_EVENTS` /
    :data:`UNDATED_RENAMES`), so their inception_code IS their own bare name.
    """
    out: dict[str, dict] = {}
    for key, info in DEFERRED_IDENTITY_KEYS.items():
        out[key.upper()] = {"status": "deferred_no_mint", **info}
    for key, info in DISCLOSED_IDENTITY_EXCEPTIONS.items():
        out[key.upper()] = {"status": "disclosed_existing_alias", **info}
    return out


def _pick_canonical_member(members: list[dict]) -> dict:
    """Canonical member of a CIK group — spec §2 tie-break, rules 1-4.

    Rules 1 (earliest ``list_date``) and 2 (venue in the issuer's country of
    incorporation) have NO in-repo data source: this repo carries no per-security
    listing-date or country-of-incorporation table, so per spec ("skip when
    unsourced, never guess") they can never fire here and are not attempted — only
    rules 3 (lowest MIC) and 4 (the D2B1 extension: lowest full listing key) are ever
    operative.  Rule 4 is what discriminates GOOG from GOOGL (same venue, same
    country): ``US-XNAS-GOOG`` < ``US-XNAS-GOOGL`` lexicographically.
    """
    if len(members) == 1:
        return members[0]
    lowest_mic = min(m["mic"] for m in members)
    candidates = [m for m in members if m["mic"] == lowest_mic]
    return min(candidates, key=lambda m: m["listing_key"])


def _load_issuer_group_allowlist(path: Path = ISSUER_GROUP_ALLOWLIST_PATH) -> frozenset[str]:
    """CIKs ratified to form a NEW multi-member issuer group (V4-D2B1 FIX 5 / M3).

    A shared SEC registrant CIK is NECESSARY evidence for grouping (spec §1) but not
    SUFFICIENT on its own to form a group for the FIRST time: the registrant may be a
    sponsor/trust rather than the fund for an ETP, so blind CIK-grouping risks
    collapsing unrelated products under one issuer.  :data:`ISSUER_GROUP_ALLOWLIST_PATH`
    is the operator ratification — only a CIK listed there may form a brand-new
    multi-member group in :func:`apply_issuer_correction`.  Adoption of an ALREADY
    established group (mint-once, spec §2) is unaffected: the review happened when
    that group first formed.  Missing/empty file -> no CIK is pre-ratified (fail
    closed, matching every other identity-authority default in this module).
    """
    if not path.exists():
        return frozenset()
    import yaml  # local: this module stays importable without a yaml dependency otherwise

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(
        str(g["cik"]).strip() for g in (payload.get("groups") or []) if g.get("cik")
    )


def apply_issuer_correction(
    rows: list[dict], cik_map: dict[str, tuple[str, str]], snapshot_date: str | None,
    now: str, allowlist: frozenset[str] | None = None,
    ambiguous_tickers: frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict]]:
    """The one authorized issuer-identity correction era (spec §4), run over the FULL
    accumulated master row set (existing + freshly minted this run) EVERY build.

    IDEMPOTENT BY CONSTRUCTION — mint-once for the issuer axis, the same law as
    ``security_id`` itself, EXTENDED (V4-D2B1 FIX 1 / B1) to also RE-EXAMINE a row
    whose ``issuer_state`` is already ``NO_ISSUER_EVIDENCE``: without this, a row
    stamped unevidenced on one run could never self-heal when a LATER weekly CIK map
    finally covers its ticker — the contract's own promised self-heal (spec §11 "FI/
    FISV ... self-heals on a later map") was unreachable.  ``RESOLVED``,
    ``DEFERRED_IDENTITY_EXCEPTION`` and ``EVIDENCE_CONFLICT`` rows stay mint-once —
    never revisited: a later run whose seeds are unchanged sees the SAME pending set
    (only the unstamped + NO_ISSUER_EVIDENCE rows) and, if none of them can change
    outcome, returns byte-stable rows.  A CIK group that later grows to include an
    already-RESOLVED member ADOPTS that member's existing ``issuer_id`` rather than
    re-running the tie-break ("the id is never re-derived because membership grew",
    spec §2).

    Per-row outcome (spec §3 state semantics, FIX 1 evidence-hit split):
      * inception_code names a fail-closed identity exception (``B``/``GOLD`` today)
        -> ``DEFERRED_IDENTITY_EXCEPTION``, excluded from grouping entirely, issuer_id
        UNCHANGED (the legacy value, if any, is retained — never cleared).
      * the evidence join (:func:`_evidence_join_key`) misses the CIK map -> state
        stays/becomes ``NO_ISSUER_EVIDENCE``, issuer_id UNCHANGED (legacy value
        retained for a pre-era row; stays ``None`` for a brand-new row — never a fresh
        per-listing mint, the abolished fallback).  Byte-stable when nothing changed.
      * the join hits and the row's OWN committed issuer_id (if any) agrees with, or
        is silent on (null), the CIK group's canonical id -> ``RESOLVED``, issuer_id
        set to the group's canonical id (adopted from an existing evidenced group, or
        freshly tie-broken — gated by the allowlist below when the group is BRAND NEW
        and has more than one member).  For the vast majority of rows the group has
        exactly one member, so the canonical id IS the row's own pre-existing value —
        no visible change, only the evidentiary status becomes explicit (spec §2).
      * the join hits but DISAGREES with a row's own already-committed non-null
        issuer_id (a re-examined ``NO_ISSUER_EVIDENCE`` row whose legacy value points
        at a different group than the fresh evidence would) -> ``EVIDENCE_CONFLICT``,
        issuer_id left UNCHANGED — recorded, never executed (frozen contract §2: a
        committed assignment never rewrites; only a future authorized era executes).
      * the join would form a BRAND-NEW multi-member group (no member already carries
        a committed canonical id for this CIK) whose CIK is NOT in
        :func:`_load_issuer_group_allowlist` (V4-D2B1 FIX 5 / M3: a shared CIK is
        necessary but not sufficient evidence — an SEC registrant may be a
        sponsor/trust for an ETP) -> every would-be member ``EVIDENCE_CONFLICT``
        instead of a group, issuer_id UNCHANGED, and a bare ``::warning`` names the
        CIK and members.  Adoption of an ALREADY-established group and every
        single-member group are UNGATED — the review already happened, or there was
        never a grouping decision to make.

    Returns ``(rows, migration_rows)``.  ``rows`` is the SAME objects, mutated in
    place (every element is also referenced by the caller's ``out`` dict).
    ``migration_rows`` covers ONLY securities that EXISTED before this run
    (``_existed_before``) whose issuer_id VALUE changed — a brand-new mint's first
    assignment is not a migration, because there was no prior stored value to migrate
    from (spec §3: "one row per security whose issuer_id VALUE changed in the era").
    """
    existed_before = {r["listing_key"] for r in rows if r.get("_existed_before")}
    exceptions = _exception_by_inception_code()
    allowed_ciks = allowlist if allowlist is not None else _load_issuer_group_allowlist()

    # FIX 1 (B1) + N1: re-examine unstamped rows, rows already NO_ISSUER_EVIDENCE,
    # and rows typed AMBIGUOUS — AMBIGUOUS is a pure source-snapshot artifact with no
    # committed assignment at stake, so a clean later map must be allowed to settle it
    # (RESOLVED/DEFERRED/EVIDENCE_CONFLICT stay mint-once).  Captured BEFORE either
    # loop below mutates issuer_state, so a row's PRIOR state is still readable here.
    _REOPENABLE = (None, "", "NO_ISSUER_EVIDENCE", "AMBIGUOUS")
    pending = [r for r in rows if r.get("issuer_state") in _REOPENABLE]
    if not pending:
        return rows, []
    reexamined_ids = {
        r["security_id"]
        for r in pending
        if r.get("issuer_state") in ("NO_ISSUER_EVIDENCE", "AMBIGUOUS")
    }

    # Adoption index: a CIK already carrying a RESOLVED canonical id (from an earlier
    # era run, or from a different pending group processed earlier in THIS loop —
    # groups are keyed by CIK so this only matters across runs, not within one).
    cik_to_existing_issuer: dict[str, str] = {}
    for r in rows:
        if r.get("issuer_state") == "RESOLVED" and r.get("issuer_cik"):
            cik_to_existing_issuer.setdefault(r["issuer_cik"], r["issuer_id"])

    groups: dict[str, list[dict]] = {}
    for r in pending:
        code = str(r["inception_code"]).upper()
        exc = exceptions.get(code)
        if exc is not None:
            r["issuer_state"] = "DEFERRED_IDENTITY_EXCEPTION"
            r["issuer_cik"] = None
            r["issuer_evidence_snapshot"] = None
            continue
        join_key = _evidence_join_key(code)
        if join_key in ambiguous_tickers:
            # FIX 7 (m1): the ticker maps to MORE THAN ONE distinct CIK on the
            # source snapshot — load_cik_map() already removed it from cik_map, so
            # this must be checked explicitly rather than read as a plain miss
            # (NO_ISSUER_EVIDENCE would silently misreport "no evidence" for a
            # ticker that has TOO MUCH, conflicting evidence).
            r["issuer_state"] = "AMBIGUOUS"
            r["issuer_cik"] = None
            r["issuer_evidence_snapshot"] = None
            continue
        evidence = cik_map.get(join_key)
        if evidence is None:
            r["issuer_state"] = "NO_ISSUER_EVIDENCE"
            r["issuer_cik"] = None
            r["issuer_evidence_snapshot"] = None
            continue
        cik, _title = evidence
        groups.setdefault(cik, []).append(r)

    migrations: list[dict] = []
    for cik, members in sorted(groups.items()):
        existing_issuer = cik_to_existing_issuer.get(cik)
        is_new_multi_member_group = existing_issuer is None and len(members) > 1
        if is_new_multi_member_group and cik not in allowed_ciks:
            # FIX 5 (M3, latent): refuse to form the group — record, never execute.
            member_ids = sorted(r["security_id"] for r in members)
            print(
                f"::warning title=security-master-issuer-allowlist::CIK {cik} would "
                f"form a new {len(members)}-member issuer group "
                f"({', '.join(member_ids)}) not in config/issuer_group_allowlist.yml "
                "— refusing to group; recording EVIDENCE_CONFLICT for review",
                flush=True,
            )
            for r in members:
                r["issuer_state"] = "EVIDENCE_CONFLICT"
                r["issuer_cik"] = cik
                r["issuer_evidence_snapshot"] = snapshot_date
                # issuer_id UNCHANGED — recorded, never executed (frozen contract §2).
            continue
        canonical_issuer_id = existing_issuer or issuer_id(
            parse_listing_key(_pick_canonical_member(members)["listing_key"])
        )
        for r in members:
            old_issuer = r["issuer_id"]
            if (r["security_id"] in reexamined_ids and old_issuer is not None
                    and old_issuer != canonical_issuer_id):
                # FIX 1(b): a re-examined row's own committed value disagrees with
                # where fresh evidence would group it — recorded, never executed.
                r["issuer_state"] = "EVIDENCE_CONFLICT"
                r["issuer_cik"] = cik
                r["issuer_evidence_snapshot"] = snapshot_date
                continue
            r["issuer_state"] = "RESOLVED"
            r["issuer_cik"] = cik
            r["issuer_evidence_snapshot"] = snapshot_date
            r["issuer_id"] = canonical_issuer_id
            if r["listing_key"] in existed_before and old_issuer != canonical_issuer_id:
                migrations.append({
                    "security_id": r["security_id"],
                    "listing_key": r["listing_key"],
                    "old_issuer_id": old_issuer,
                    "new_issuer_id": canonical_issuer_id,
                    "reason": ERA_ISSUER_CORRECTION,
                    "evidence_cik": cik,
                    "evidence_snapshot": snapshot_date,
                    "migrated_at": now,
                })

    return rows, sorted(migrations, key=lambda m: m["security_id"])


def _merge_issuer_migrations(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Append-only on ``(security_id, old_issuer_id, new_issuer_id, reason)`` — the
    same shape as :func:`merge_alias_rows`.  Mint-once means a security migrates at
    most once per reason in practice; the dedup is defensive, not load-bearing."""
    merged: dict[tuple, dict] = {}
    for row in existing:
        key = (str(row["security_id"]), str(row["old_issuer_id"]), str(row["new_issuer_id"]),
               str(row["reason"]))
        merged[key] = dict(row)
    for row in fresh:
        key = (row["security_id"], row["old_issuer_id"], row["new_issuer_id"], row["reason"])
        if key in merged:
            continue
        merged[key] = row
    return [merged[k] for k in sorted(merged, key=lambda k: (k[0], k[3]))]


def _build_issuer_master_rows(master_rows: list[dict],
                              cik_to_title: dict[str, str]) -> list[dict]:
    """``reference.issuer_master`` — one row per distinct non-null ``issuer_id`` in the
    master (spec §3 minimal cut).  NOT a second identity system: minted only via
    ``lib.dataos.identity.issuer_id`` (inside :func:`apply_issuer_correction`),
    pointed into by ``security_master.issuer_id`` — this is a CENSUS over that column,
    never an independent allocator.
    """
    groups: dict[str, list[dict]] = {}
    for r in master_rows:
        iid = r.get("issuer_id")
        if iid:
            groups.setdefault(iid, []).append(r)

    out: list[dict] = []
    for issuer, members in groups.items():
        resolved = [m for m in members if m.get("issuer_state") == "RESOLVED"]
        if resolved:
            cik = resolved[0].get("issuer_cik")
            out.append({
                "issuer_id": issuer,
                "cik": cik,
                "legal_name": cik_to_title.get(cik) if cik else None,
                "n_securities": len(members),
                "evidence_source": "sec_company_tickers",
                "evidence_snapshot": resolved[0].get("issuer_evidence_snapshot"),
                "status": "active",
                "era": ERA_ISSUER_CORRECTION,
            })
        else:
            out.append({
                "issuer_id": issuer,
                "cik": None,
                "legal_name": None,
                "n_securities": len(members),
                "evidence_source": "legacy_mint",
                "evidence_snapshot": None,
                "status": "active",
                "era": "legacy",
            })
    return sorted(out, key=lambda r: r["issuer_id"])


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
        elif kind == "int":
            data[column] = pd.Series(
                [None if v is None else int(v) for v in values], dtype="Int64"
            )
        else:
            # Same NaN-is-not-None trap as _read_existing: a caller that assigns
            # `frame.loc[..., col] = None` onto a pandas "str"-dtype column can hand
            # this a `float('nan')`, not a Python `None` — `v is None` alone would
            # stringify it into the LITERAL STRING "nan" and corrupt the column.
            data[column] = pd.Series(
                [None if (v is None or pd.isna(v)) else str(v) for v in values],
                dtype="object",
            )
    frame = pd.DataFrame(data, columns=list(columns))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _issuer_state_counts(master_rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in master_rows:
        state = r.get("issuer_state") or "UNMIGRATED"
        counts[state] = counts.get(state, 0) + 1
    return counts


def _multi_security_issuer_groups(master_rows: list[dict]) -> list[dict]:
    """Every issuer_id carried by >1 security — the multi-security group census
    (spec §6): machine-visible confirmation of what the era actually grouped."""
    groups: dict[str, list[str]] = {}
    for r in master_rows:
        iid = r.get("issuer_id")
        if iid:
            groups.setdefault(iid, []).append(r["security_id"])
    return [
        {"issuer_id": iid, "security_ids": sorted(secs)}
        for iid, secs in sorted(groups.items())
        if len(secs) > 1
    ]


def build(out_dir: Path, dry_run: bool = False, allow_missing_evidence: bool = False) -> dict:
    """Do the whole build and return the receipt payload (written unless ``dry_run``).

    ``allow_missing_evidence`` (V4-D2B1 FIX 2 / B2 manual-path hardening): a missing or
    empty ``CIK_MAP_DIR`` — no weekly evidence snapshot has ever landed — refuses with
    :class:`IdentityError` UNLESS this is set.  Without this guard, a manual run on a
    bare checkout (no ``data/symbol_directory/cik_map/`` at all) would silently mint
    EVERY row ``NO_ISSUER_EVIDENCE``, which is exactly the false-freshness escape §7
    law (a) already closes for the nightly seam — the CLI path needed the same fence,
    because a human blind to the missing rail could commit that output as if it were a
    normal build.  Passing this flag is an explicit, printed (see :func:`main`)
    admission that no CIK evidence exists yet — the correct state on a genuinely bare
    checkout before the first weekly map lands.
    """
    universe = load_universe()
    delisted = load_delisted()
    directory, snapshot_date, snapshot_path = load_directory()
    fixups, migrations = load_config_maps()
    cik_map, cik_snapshot_date, cik_map_path, ambiguous_tickers = load_cik_map()
    if cik_map_path is None and not allow_missing_evidence:
        raise IdentityError(
            "data/symbol_directory/cik_map has no snapshot — refusing to mint issuer "
            "evidence blind (every row would silently become NO_ISSUER_EVIDENCE). "
            "Pass allow_missing_evidence=True (CLI: --allow-missing-evidence) to build "
            "anyway, e.g. on a bare checkout before the first weekly CIK map lands."
        )

    resolutions = resolve_universe(universe, delisted, directory, snapshot_date)
    resolved = [r for r in resolutions if r.listing_key is not None]
    unresolved = [r for r in resolutions if r.listing_key is None]

    now = _iso_now()
    master_path = out_dir / MASTER_NAME
    aliases_path = out_dir / ALIASES_NAME
    issuer_master_path = out_dir / ISSUER_MASTER_NAME
    issuer_migrations_path = out_dir / ISSUER_MIGRATIONS_NAME

    seed_notes = unmodelled_renames(fixups, migrations)

    master_rows, ids, notes = mint_master_rows(
        resolutions,
        _read_existing(master_path, MASTER_COLUMNS, MASTER_DTYPES,
                       allow_missing=ISSUER_AXIS_COLUMNS),
        now,
    )
    master_rows, fresh_issuer_migrations = apply_issuer_correction(
        master_rows, cik_map, cik_snapshot_date, now, ambiguous_tickers=ambiguous_tickers
    )

    fresh_aliases = build_alias_rows(resolutions, ids)
    alias_rows = merge_alias_rows(
        fresh_aliases, _read_existing(aliases_path, ALIAS_COLUMNS, ALIAS_DTYPES), now
    )

    issuer_migration_rows = _merge_issuer_migrations(
        _read_existing(issuer_migrations_path, ISSUER_MIGRATIONS_COLUMNS,
                       ISSUER_MIGRATIONS_DTYPES),
        fresh_issuer_migrations,
    )
    cik_to_title = {cik: title for cik, title in cik_map.values()}
    issuer_master_rows = _build_issuer_master_rows(master_rows, cik_to_title)

    # THE ONLY READER, used as the validator: an ambiguous table must fail HERE, at
    # write time, not in whatever consumer first asks it a question.
    table = VendorAliasTable.from_records(alias_rows)

    receipt = {
        "dataset_ids": [
            "reference.security_master", "reference.vendor_aliases",
            "reference.issuer_master", "reference.issuer_migrations",
        ],
        "producer": "scripts/build_security_master.py",
        "code_version": _git_sha(),
        "generated_at": now,
        # V4-D2B1 FIX 2 (B2 n2): every identity rail is ALWAYS named here, even when
        # absent (value null) — a dropped key silently reads as "not an input", which
        # is exactly the shape that let the listing-snapshots rail go uncovered by the
        # nightly preflight (only the 5 seed files + the CIK rail were named/checked).
        # Keyed on the RAIL'S OWN DIRECTORY (stable across which file is newest), not
        # the newest file's path, so the key never depends on which snapshot exists.
        "inputs": {
            **{
                str(path.relative_to(ROOT)): _sha256(path)
                for path in (CONSTITUENTS, MEMBERSHIP, DELISTED_LEDGER, CONFIG_YML,
                            TICKER_ALIASES_PY)
            },
            _relpath(SYMBOL_DIR_SNAPSHOTS): (
                _sha256(snapshot_path) if snapshot_path is not None else None
            ),
            _relpath(CIK_MAP_DIR): (
                _sha256(cik_map_path) if cik_map_path is not None else None
            ),
        },
        "symbol_directory_snapshot": snapshot_date,
        "cik_map_snapshot": cik_snapshot_date,
        "row_counts": {
            "security_master": len(master_rows),
            "vendor_aliases": len(alias_rows),
            "vendor_alias_rows_readable": len(table.rows),
            "issuer_master": len(issuer_master_rows),
            "issuer_migrations": len(issuer_migration_rows),
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
        "identity_exceptions": [
            {
                "key": key,
                "status": "deferred_no_mint",
                **DEFERRED_IDENTITY_KEYS[key],
            }
            for key in sorted(DEFERRED_IDENTITY_KEYS)
        ] + [
            {
                "key": key,
                "status": "disclosed_existing_alias",
                **DISCLOSED_IDENTITY_EXCEPTIONS[key],
            }
            for key in sorted(DISCLOSED_IDENTITY_EXCEPTIONS)
        ],
        "notes": seed_notes + notes,
        # V4-D2B1 §12: authority is semantically DECOMPOSED — identity is canonical
        # for CURRENT exact issuer/security/listing identity (Sol's D2A ruling); the
        # spine never gates/ranks/trades on its own account. `consumers` names every
        # real reader so the next session does not have to re-discover D2A by grep.
        "authority": {
            "identity_authority": "canonical_exact_identity",
            "signal_authority": "none",
            "ranking_authority": "none",
            "trade_authority": "none",
            "consumers": ["gmi.identity_resolution/v1"],
        },
        "issuer": {
            "era": ERA_ISSUER_CORRECTION,
            "state_counts": _issuer_state_counts(master_rows),
            "multi_security_groups": _multi_security_issuer_groups(master_rows),
            "migrations_this_run": len(fresh_issuer_migrations),
            # V4-D2B1 FIX 9 (n3): the ALL-TIME count, alongside the per-run count —
            # "migrations_this_run: 0" alone reads as "no migrations ever happened",
            # which is false on every run after the era's first.
            "era_migrations_total": len(issuer_migration_rows),
            "evidence_snapshot": cik_snapshot_date,
        },
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_parquet(master_rows, MASTER_COLUMNS, master_path, MASTER_DTYPES)
        _write_parquet(alias_rows, ALIAS_COLUMNS, aliases_path, ALIAS_DTYPES)
        _write_parquet(issuer_master_rows, ISSUER_MASTER_COLUMNS, issuer_master_path,
                       ISSUER_MASTER_DTYPES)
        _write_parquet(issuer_migration_rows, ISSUER_MIGRATIONS_COLUMNS,
                       issuer_migrations_path, ISSUER_MIGRATIONS_DTYPES)
        (out_dir / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    receipt["_resolutions"] = resolutions  # in-process only; never serialized
    return receipt


# ── Nightly fail-closed refresh seam (V4-D2B1 §7) ──────────────────────────────
#: The artifacts a nightly refresh compares byte-for-byte to decide "did anything
#: actually change" (RECEIPT_NAME is handled separately — see :func:`run_nightly_refresh`).
_NIGHTLY_ARTIFACT_NAMES = (MASTER_NAME, ALIASES_NAME, ISSUER_MASTER_NAME, ISSUER_MIGRATIONS_NAME)


def _read_bytes_if_exists(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _identity_rail_unreadable(directory: Path) -> bool:
    """True iff ``directory`` cannot supply a readable newest-snapshot parquet.

    Shared preflight test for BOTH silently-degrading identity rails
    (:data:`CIK_MAP_DIR`, :data:`SYMBOL_DIR_SNAPSHOTS`) — see :func:`run_nightly_refresh`.
    """
    if not directory.is_dir():
        return True
    files = sorted(p for p in directory.glob("*.parquet"))
    if not files:
        return True
    try:
        import pandas as pd
        pd.read_parquet(files[-1])
    except Exception:  # noqa: BLE001 — an unreadable snapshot refuses, never half-runs
        return True
    return False


def _restore_artifacts(out_dir: Path, before: dict[str, bytes | None],
                       before_receipt: bytes | None) -> None:
    for name, content in before.items():
        path = out_dir / name
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.write_bytes(content)
    receipt_path = out_dir / RECEIPT_NAME
    if before_receipt is None:
        if receipt_path.exists():
            receipt_path.unlink()
    else:
        receipt_path.write_bytes(before_receipt)


def run_nightly_refresh(out_dir: Path) -> int:
    """The ``daily.yml`` collect-job seam (spec §7).  Fail-closed refresh laws:

      (a) a missing/unreadable identity input -> REFUSE, keep last-good artifacts,
          ``::warning``, exit 0, ``generated_at`` NOT re-stamped;
      (b) inputs unchanged since the last generation -> byte-stable no-op,
          ``generated_at`` NOT re-stamped;
      (c) inputs advanced -> regenerate, stamp, receipt pins the exact snapshot ids
          consumed.

    A source failure can never produce a falsely fresh identity generation (§23.24):
    the real (writing) build always runs first into ``out_dir``, and its output is
    then compared byte-for-byte against what was there before — if nothing besides
    the receipt's own wall-clock stamp changed, or if the run surfaced a config
    defect (an unmodelled rename / listing-key collision, the two things
    ``receipt['notes']`` ever carries), every artifact including the receipt is
    restored to its prior bytes.  Non-fatal throughout: this function always returns
    0 — a nightly step must never fail the collect job over an identity refresh.

    Law (a) covers THREE distinct identity inputs, all refused pre-flight (never left
    to ``build()``): the ``required`` seed/config files above, the ``CIK_MAP_DIR``
    evidence rail (escape #11), and the ``SYMBOL_DIR_SNAPSHOTS`` listing rail (V4-D2B1
    FIX 2 / B2/n2).  ``load_cik_map()``/``load_directory()`` both silently degrade to
    an empty mapping when their directory is missing/empty/unreadable (correct for the
    one-shot ``build()``/``main()`` CLI path, where "no evidence yet" is a valid state
    to mint from — hardened for THAT path too, see ``allow_missing_evidence`` on
    :func:`build`), which would otherwise let the nightly regenerate a falsely fresh
    artifact: an empty CIK map mints every row ``NO_ISSUER_EVIDENCE``, and an empty
    listing-snapshots dir starves ``resolve_universe`` of any venue evidence at all,
    collapsing coverage toward zero while still returning a clean receipt with no
    ``notes`` and a success ``::notice`` — the false-freshness escape this law exists
    to close, on either rail.
    """
    required = (CONSTITUENTS, MEMBERSHIP, DELISTED_LEDGER, CONFIG_YML, TICKER_ALIASES_PY)
    missing = [
        str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
        for p in required if not p.exists()
    ]
    if missing:
        print(
            f"::warning title=security-master-nightly::missing identity input(s) "
            f"{missing} — refusing, keeping last-good artifacts, generated_at not "
            "re-stamped", flush=True,
        )
        return 0

    # V4-D2B1 FIX 2 (B2/n2): the listing-snapshots rail was not covered by the
    # cik_map fence commit ed49d19083d0 landed — an empty/missing snapshots dir made
    # load_directory() silently return ({}, None, None), so a nightly run over it
    # would resolve almost nothing (coverage collapses toward zero) yet still stamp a
    # fresh generation and a success ::notice. Same law as the cik_map rail below.
    if _identity_rail_unreadable(SYMBOL_DIR_SNAPSHOTS):
        print(
            "::warning title=security-master-nightly::identity input missing: "
            "symbol_directory snapshots — refusing to regenerate; last-good "
            "artifacts retained", flush=True,
        )
        return 0

    # V4-D2B1 escape #11: load_cik_map() silently degrades to an empty mapping when
    # CIK_MAP_DIR is missing/empty/unreadable (the manual `build()` path treats that
    # as "no CIK evidence yet", not a failure — every row just mints NO_ISSUER_EVIDENCE
    # and the run still returns a clean receipt with no `notes`). Nightly is the ONLY
    # lane this widens into an escape: the same silent degrade there was a fail-CLOSED
    # violation of law (a) — a missing evidence rail must refuse, never regenerate a
    # falsely-fresh artifact where every issuer axis value quietly goes NO_ISSUER_EVIDENCE.
    if _identity_rail_unreadable(CIK_MAP_DIR):
        print(
            "::warning title=security-master-nightly::identity input missing: "
            "cik_map — refusing to regenerate; last-good artifacts retained",
            flush=True,
        )
        return 0

    before = {name: _read_bytes_if_exists(out_dir / name) for name in _NIGHTLY_ARTIFACT_NAMES}
    before_receipt = _read_bytes_if_exists(out_dir / RECEIPT_NAME)

    try:
        receipt = build(out_dir, dry_run=False)
    except Exception as exc:  # noqa: BLE001 — any read/parse failure refuses, never half-writes
        # FIX 4 (M2): a mid-build failure can leave PARTIAL writes on disk (build()
        # writes master -> aliases -> issuer_master -> issuer_migrations -> receipt in
        # sequence, and any of those can raise) — restore ALL artifacts to last-good
        # rather than leaving a torn mix of new-and-old bytes.
        _restore_artifacts(out_dir, before, before_receipt)
        print(
            f"::warning title=security-master-nightly::build failed reading identity "
            f"inputs ({exc}) — keeping last-good artifacts, generated_at not "
            "re-stamped", flush=True,
        )
        return 0

    if receipt.get("notes"):
        _restore_artifacts(out_dir, before, before_receipt)
        print(
            f"::warning title=security-master-nightly::{'; '.join(receipt['notes'])} — "
            "unmodelled rename or listing-key collision; keeping last-good artifacts, "
            "generated_at not re-stamped", flush=True,
        )
        return 0

    after = {name: _read_bytes_if_exists(out_dir / name) for name in _NIGHTLY_ARTIFACT_NAMES}
    if after == before:
        if before_receipt is not None:
            (out_dir / RECEIPT_NAME).write_bytes(before_receipt)
        print(
            "::notice title=security-master-nightly::inputs unchanged since the last "
            "generation — byte-stable no-op, generated_at not re-stamped", flush=True,
        )
        return 0

    print(
        f"::notice title=security-master-nightly::identity inputs advanced — "
        f"regenerated ({coverage_line(receipt)})", flush=True,
    )
    return 0


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
    parser.add_argument(
        "--nightly", action="store_true",
        help=(
            "daily.yml collect-job seam (spec §7): fail-closed refresh — refuses "
            "non-fatally on a missing/unreadable identity input, is a byte-stable "
            "no-op when nothing advanced, and only re-stamps generated_at when "
            "inputs genuinely changed. Always exits 0. Ignores --dry-run/--report."
        ),
    )
    parser.add_argument(
        "--allow-missing-evidence", action="store_true",
        help=(
            "V4-D2B1 FIX 2 (B2 manual-path hardening): opt out of the refusal that "
            "otherwise raises when data/symbol_directory/cik_map has no snapshot — "
            "build anyway, minting every row NO_ISSUER_EVIDENCE. Prints a warning. "
            "Ignored under --nightly (the nightly seam has its own, always-refusing "
            "preflight and never reaches this flag)."
        ),
    )
    args = parser.parse_args(argv)

    if args.nightly:
        return run_nightly_refresh(Path(args.out))

    if args.allow_missing_evidence:
        print(
            "::warning title=security-master-manual::--allow-missing-evidence set — "
            "building without CIK issuer evidence; every row will mint "
            "NO_ISSUER_EVIDENCE", flush=True,
        )
    receipt = build(Path(args.out), dry_run=args.dry_run,
                    allow_missing_evidence=args.allow_missing_evidence)
    _report(receipt, verbose=args.report)
    # A NOTE IS A FAILURE, not a warning (adversarial review, 2026-08-13).  `notes`
    # carries exactly two things, and neither may pass: a rename the repo's own maps
    # record that this builder does not model (the alias table would answer the OLD
    # pairing forever — the seven-month MMC loss, one layer up), and a listing-key
    # COLLISION, which spec §5 says takes an operator-ratified `.2` disambiguator and
    # never a guess.  Emitting a `::warning` and exiting 0 makes the detector advisory,
    # and an advisory detector on a silent-loss defect is decoration.  Coverage is NOT
    # in this set on purpose: DOS-1.1 asks for it to be REPORTED, not asserted complete.
    if receipt.get("notes"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
