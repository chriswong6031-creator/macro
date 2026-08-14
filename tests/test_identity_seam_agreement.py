"""DOS-1.2 — the identity seam gate.

`config/identity_seams.yml` declares every surface in this repository that answers
"which security is this?", classified ADOPT / ALIAS-INTO-MASTER / KNOWINGLY-DIFFERENT /
RETIRE against the DOS-1.1 master.

WHY THIS EXISTS.  `lib/ticker_aliases.py`'s docstring records the realized cost of an
ungoverned seam: MMC->MRSH lived in ``scripts/fetch_basket_extras`` but not in its sibling
``scripts/fetch_basket_ohlcv``, so ``data/baskets/ohlcv/MMC.parquet`` never existed and for
seven months the ``insurance`` basket rendered 18/19 members and ``us_sector_financials``
75/76.  **Nothing went red.**  This file is the thing that goes red.

THE GATE IS ONLY WORTH ITS RUNTIME IF IT CAN FAIL.  Three properties are engineered in on
purpose, because the cheap version of this test passes forever:

  1. Each ADOPT surface is read through ITS OWN reader — ``engine.ledger_identity.current_key``
     for the ledger space, the committed parquet through ``lib.dataos.identity.VendorAliasTable``
     for the master, the spine's own literal for CN.  Nothing is compared to a value the
     registry itself supplies, because a comparison of a thing to itself cannot fail.
  2. Every agreement assertion is guarded by a NON-EMPTINESS assertion that prints its N.
     An agreement gate over zero securities is green forever and means nothing.
  3. The declared divergences are pinned as DIVERGENT.  A silent "fix" that makes two
     knowingly-different surfaces agree is itself a failure here, because it would mean a
     product decision was taken by a cleanup (precedent: DNR:HOLD-FF-DETECTOR-PERIOD-BASIS).

DISCOVERY BOUND, STATED HONESTLY.  ``test_no_unlisted_identity_surface`` pins the declared
set and rescans the known candidate shapes.  It CANNOT detect an identity map expressed in a
form it has never seen.  A green run means "no known-shaped surface is unlisted", NOT "no
other identity surface exists".  Do not upgrade that claim.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
pd = pytest.importorskip("pandas")

from lib.dataos import identity as ident  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
_SEAMS = _REPO / "config" / "identity_seams.yml"
_MASTER = _REPO / "data" / "reference" / "security_master.parquet"
_ALIASES = _REPO / "data" / "reference" / "vendor_aliases.parquet"

_CLASSES = {"ADOPT", "ALIAS-INTO-MASTER", "KNOWINGLY-DIFFERENT", "RETIRE"}


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def seams() -> dict:
    return yaml.safe_load(_SEAMS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alias_table():
    """The master's alias space, read from the COMMITTED artifact through the canonical
    reader — never reconstructed from the registry."""
    frame = pd.read_parquet(_ALIASES)
    records = []
    for row in frame.to_dict("records"):
        records.append(
            {
                "vendor": row["vendor"],
                "vendor_symbol": row["vendor_symbol"],
                "security_id": row["security_id"],
                "valid_from": _as_date(row.get("valid_from")),
                "valid_to": _as_date(row.get("valid_to")),
            }
        )
    return ident.VendorAliasTable.from_records(records)


def _as_date(value):
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    if not text or text.lower() in {"none", "nat", "nan"}:
        return None
    return date.fromisoformat(text[:10])


# --------------------------------------------------------------------------- registry schema
class TestRegistryIsWellFormed:
    def test_every_row_declares_a_class_from_the_closed_vocabulary(self, seams):
        for row in seams["surfaces"]:
            assert row.get("class") in _CLASSES, f"{row.get('path')}: bad class {row.get('class')!r}"

    def test_no_duplicate_surface_keys(self, seams):
        keys = [(r["path"], r.get("key"), r.get("symbol")) for r in seams["surfaces"]]
        assert len(keys) == len(set(keys)), f"duplicate rows: {keys}"

    def test_every_declared_path_exists_on_disk(self, seams):
        rows = list(seams["surfaces"]) + list(seams.get("excluded") or [])
        for row in rows:
            for key in ("path", "also"):
                rel = row.get(key)
                if rel:
                    assert (_REPO / rel).exists(), f"{rel} declared but absent"

    def test_knowingly_different_rows_carry_a_reason(self, seams):
        """The escape-hatch guard. KNOWINGLY-DIFFERENT is the class that will be abused to
        park unfixed drift; an empty reason makes that abuse invisible."""
        for row in seams["surfaces"]:
            if row["class"] == "KNOWINGLY-DIFFERENT":
                reason = (row.get("reason") or "").strip()
                assert len(reason) > 40, f"{row['path']}: KNOWINGLY-DIFFERENT needs a substantive reason"

    def test_retire_rows_carry_a_successor_and_a_migration(self, seams):
        for row in seams["surfaces"]:
            if row["class"] == "RETIRE":
                assert (row.get("superseded_by") or "").strip(), f"{row['path']}: RETIRE needs superseded_by"
                assert (row.get("migration") or "").strip(), f"{row['path']}: RETIRE needs migration"

    def test_alias_rows_name_where_their_content_goes(self, seams):
        for row in seams["surfaces"]:
            if row["class"] == "ALIAS-INTO-MASTER":
                assert (row.get("migrates_to") or "").strip(), f"{row['path']}: needs migrates_to"

    def test_adopt_rows_say_how_the_gate_reads_them(self, seams):
        for row in seams["surfaces"]:
            if row["class"] == "ADOPT":
                assert (row.get("checked_by") or "").strip(), f"{row['path']}: ADOPT needs checked_by"

    def test_excluded_rows_carry_a_reason(self, seams):
        for row in seams.get("excluded") or []:
            assert len((row.get("reason") or "").strip()) > 40, f"{row['path']}: exclusion needs a reason"


# --------------------------------------------------------------------------- the agreement gate
class TestAdoptSurfacesAgree:
    """The deliverable. Two ADOPT surfaces that disagree about a security FAIL here."""

    def test_there_are_at_least_two_adopt_surfaces_to_compare(self, seams):
        """Vacuity guard #1: one ADOPT surface has no pair, so the gate below would be
        decorative."""
        adopt = [r["path"] for r in seams["surfaces"] if r["class"] == "ADOPT"]
        assert len(adopt) >= 2, f"agreement gate needs >=2 ADOPT surfaces, got {adopt}"

    def test_ledger_identity_and_the_master_agree_on_every_renamed_key(self, alias_table):
        """ADOPT x ADOPT: `engine.ledger_identity` vs the master, read INDEPENDENTLY.

        `current_key` answers from config.yml quality.ticker_key_migrations; the master
        answers from the committed vendor_aliases parquet. They must name the same current
        symbol for the same security, or the ledger is writing rows under a key the master
        does not believe in — which is precisely the SATS/ECHO double-count DOS-1.1 fixed.
        """
        from lib import config as _config
        from engine import ledger_identity as _ledger

        migrations = ((_config.load().get("quality") or {}).get("ticker_key_migrations") or {})
        assert migrations, "vacuity guard #2: no migrations to compare — gate would be empty"

        compared = 0
        for old_symbol, expected_current in migrations.items():
            # Surface A — the ledger module's own reader.
            ledger_answer = _ledger.current_key(old_symbol, migrations)

            # Surface B — the master, independently. Resolve the OLD symbol before the
            # boundary to get the security, then ask what that security is called today.
            security = alias_table.resolve("ledger", old_symbol, on=date(1990, 1, 1))
            if security is None:
                continue
            master_answer = alias_table.vendor_symbol_for("ledger", security, on=date.today())

            assert ledger_answer == master_answer, (
                f"ADOPT surfaces disagree for {old_symbol!r} (security {security}): "
                f"engine/ledger_identity.py says {ledger_answer!r}, "
                f"the master says {master_answer!r}"
            )
            assert ledger_answer == expected_current
            compared += 1

        assert compared > 0, "vacuity guard #3: zero securities actually compared"
        print(f"::notice title=identity-seam-agreement::ledger vs master compared {compared} security(s)", flush=True)

    def test_the_cn_spine_and_the_master_build_the_same_listing_key(self):
        """ADOPT x ADOPT: the CN spine vs the master, each through ITS OWN reader.

        CORRECTED after CEO review 2026-08-13. The first version of this test hardcoded
        ``spine_answer = f"CN-{mic}-{code}"`` — a literal typed into the test, not the ADOPT
        surface's own answer — so it compared the master to the test author's belief about
        the spine and could not detect the spine changing. That is exactly the vacuity this
        module's own docstring forbids. It now calls
        ``collectors.china_tushare_spine.canonical_identity`` for real.

        SEAM NOTE (declared in config/identity_seams.yml): the spine's field is *named*
        ``security_id`` but its value is the Data OS **listing_id** — bare
        ``CN-XSHG-600519``, no ``SEC:`` prefix. It is NOT Data OS ``security_id()``. The
        production field is deliberately NOT renamed by DOS-1.2; the seam is only declared.
        """
        spine = pytest.importorskip("collectors.china_tushare_spine")

        cases = [
            ("600519.SH", "CN-XSHG-600519"),   # Shanghai main board
            ("000001.SZ", "CN-XSHE-000001"),   # Shenzhen main board
            ("920163.BJ", "CN-XBSE-920163"),   # Beijing, canonical 920xxx
            ("688981.SH", "CN-XSHG-688981"),   # STAR
            ("300750.SZ", "CN-XSHE-300750"),   # ChiNext
        ]
        assert cases, "vacuity guard: no CN cases to compare"

        for ts_code, expected_listing in cases:
            spine_identity = spine.canonical_identity(ts_code)          # surface A, own reader
            listing_key = ident.parse_listing_key(spine_identity.security_id)
            master_listing = ident.listing_id(listing_key)              # surface B, own reader

            assert spine_identity.security_id == master_listing, (
                f"CN identity forked for {ts_code}: spine yields "
                f"{spine_identity.security_id!r}, the master renders {master_listing!r}"
            )
            assert master_listing == expected_listing, (
                f"{ts_code}: expected listing key {expected_listing!r}, got {master_listing!r}"
            )
            # The seam itself: spine.security_id is a LISTING id, not a Data OS security id.
            assert not spine_identity.security_id.startswith("SEC:")
            assert ident.security_id(listing_key) == f"SEC:{master_listing}"

        print(
            f"::notice title=identity-seam-agreement::cn spine vs master compared {len(cases)} listing(s)",
            flush=True,
        )

    def test_the_master_resolves_both_sides_of_every_recorded_rename(self, alias_table):
        """The MMC and SATS pins, asserted through the master's own reader."""
        checks = [
            ("yahoo", "MMC", date(2026, 1, 13), "MRSH", date(2026, 1, 15)),
            ("ledger", "SATS", date(2026, 6, 23), "ECHO", date(2026, 6, 25)),
        ]
        for vendor, before_sym, before_on, after_sym, after_on in checks:
            before = alias_table.resolve(vendor, before_sym, on=before_on)
            after = alias_table.resolve(vendor, after_sym, on=after_on)
            if before is None and after is None:
                pytest.fail(f"{vendor}: neither {before_sym} nor {after_sym} resolves — alias space is empty")
            assert before == after, (
                f"{vendor}: {before_sym}@{before_on} -> {before} but {after_sym}@{after_on} -> {after}; "
                "a rename must not split one security into two identities"
            )


# --------------------------------------------------------------------------- divergences stay declared
class TestDeclaredDivergencesRemainDeclared:
    """A KNOWINGLY-DIFFERENT surface that quietly adopts the master's convention means a
    product decision was made by a cleanup. That is a failure, not an improvement."""

    def test_the_declared_divergence_ids_are_present(self, seams):
        ids = {d["id"] for d in seams["declared_divergences"]}
        required = {
            "collision-suffix-conventions",
            "share-class-collapse",
            "cn-beijing-range-split",
            "legacy-beijing-alias",
        }
        assert required <= ids, f"missing declared divergences: {required - ids}"

    def test_share_class_equiv_still_collapses_goog_onto_googl(self):
        """If this ever stops being true, the 13F consensus lane changed meaning."""
        rows = yaml.safe_load((_REPO / "config" / "share_class_equiv.yml").read_text(encoding="utf-8"))
        pairs = rows if isinstance(rows, list) else rows.get("pairs") or rows.get("equivalences") or []
        collapsed = {(r.get("ticker"), r.get("canonical")) for r in pairs if isinstance(r, dict)}
        assert collapsed, "share_class_equiv.yml parsed empty — the divergence check is vacuous"
        assert any(t == "GOOG" for t, _ in collapsed), (
            "GOOG no longer collapses in share_class_equiv.yml — if intentional, update "
            "identity_seams.yml declared_divergences in the same commit"
        )

    def test_the_master_still_treats_goog_and_googl_as_distinct(self):
        """CORRECTED after CEO review 2026-08-13.

        The first version wrapped these assertions in ``if {"GOOG","GOOGL"} <= codes:`` — so
        DELETING one side of the divergence made the guard GREEN. A divergence guard that
        passes when half the divergence disappears protects nothing. Both sides must exist
        AND must be two distinct securities, unconditionally.
        """
        frame = pd.read_parquet(_MASTER)
        codes = set(frame["inception_code"].astype(str))

        missing = {"GOOG", "GOOGL"} - codes
        assert not missing, (
            f"{sorted(missing)} absent from the committed security master — the declared "
            "GOOG/GOOGL divergence cannot be protected if a side is missing. If a share class "
            "genuinely delisted, update identity_seams.yml declared_divergences in the same commit."
        )

        rows = frame[frame["inception_code"].isin(["GOOG", "GOOGL"])]
        distinct = rows["security_id"].nunique()
        assert distinct == 2, (
            f"master yields {distinct} security_id(s) for GOOG+GOOGL, expected 2 — collapsing "
            "share classes is config/share_class_equiv.yml's job for 13F consensus, never the "
            f"master's. Rows: {rows[['inception_code', 'security_id']].to_dict('records')}"
        )

    def test_the_theme_graph_uses_its_own_collision_suffix(self, seams):
        row = next(r for r in seams["surfaces"] if r["path"] == "config/theme_graph_identity_breaks.yml")
        assert "#" in row["id_convention"], "theme graph suffix convention no longer declared"
        assert row["class"] == "KNOWINGLY-DIFFERENT"


# --------------------------------------------------------------------------- completeness
class TestRegistryIsComplete:
    """Discovery bound: this pins the declared set and rescans KNOWN candidate shapes. It
    cannot find an identity map in a shape it has never seen. Green means 'no known-shaped
    surface is unlisted', not 'no other surface exists'."""

    #: Every path the DOS-1.2 census examined. A new entry here without a registry row fails.
    _CANDIDATES = (
        "lib/ticker_aliases.py",
        "lib/delisted_symbols.py",
        "lib/symbol_directory_receipts.py",
        "engine/entity_resolver.py",
        "engine/name_resolver.py",
        "engine/ledger_identity.py",
        "collectors/edgar_deadnames.py",
        "config/theme_graph_identity_breaks.yml",
        "config/biocatalyst_sponsor_ticker_map.yml",
        "config/us_search_aliases_zh.json",
        "config/share_class_equiv.yml",
        "collectors/china_universe.py",
        "collectors/china_ths_concepts.py",
        "collectors/china_analyst.py",
        "collectors/china_tushare_spine.py",
        "lib/dataos/identity.py",
        "config.yml",
    )

    def test_every_examined_surface_is_classified_or_explicitly_excluded(self, seams):
        declared = {r["path"] for r in seams["surfaces"]}
        declared |= {r.get("also") for r in seams["surfaces"] if r.get("also")}
        excluded = {r["path"] for r in seams.get("excluded") or []}
        for path in self._CANDIDATES:
            assert path in declared or path in excluded, (
                f"{path} is an examined identity surface but is neither classified nor excluded "
                "in config/identity_seams.yml"
            )

    def test_the_candidate_list_matches_what_is_on_disk(self):
        for path in self._CANDIDATES:
            assert (_REPO / path).exists(), f"candidate {path} vanished — update the census"

    def test_master_lifecycle_gap_is_recorded_honestly(self, seams):
        """The master has no lifecycle column; two feeders are scoped against that gap. If a
        lifecycle column is ever added, this flag must move in the same commit."""
        frame = pd.read_parquet(_MASTER)
        has_lifecycle = any(
            k in c.lower() for c in frame.columns for k in ("delist", "active", "status", "lifecycle")
        )
        assert bool(seams["master"]["models_lifecycle"]) == has_lifecycle, (
            "identity_seams.yml master.models_lifecycle disagrees with the committed master's columns: "
            f"{list(frame.columns)}"
        )
