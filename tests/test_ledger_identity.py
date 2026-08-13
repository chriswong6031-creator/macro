"""engine/ledger_identity — one ledger key per company, not per ticker STRING.

THE SIGNATURE UNDER TEST (measured 2026-08-12, data/signal_archive/track_record.parquet):
EchoStar renamed SATS->ECHO on 2026-06-24 and the ledger ended up holding 128 SATS rows
and 128 ECHO rows whose ``(date, type)`` key sets are IDENTICAL — same
2008-11-25 -> 2026-04-23 span, zero keys unique to either side, all 39 identity/entry
columns byte-identical. One physical fire logged twice, so every per-row statistic
weights that company DOUBLE.

Fixtures are synthetic. The live-ledger checks at the bottom read the committed parquet
and SKIP when it is absent (agent worktrees are sparse — a missing input proves nothing
and must not read as a pass).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import ledger_identity as LI
from engine import track_record as TR

_ROOT = Path(__file__).resolve().parents[1]
LIVE_LEDGER = _ROOT / "data" / "signal_archive" / "track_record.parquet"


@pytest.fixture(scope="module")
def live() -> pd.DataFrame:
    """The committed ledger's key columns (read once — the file is ~10 MB)."""
    return pd.read_parquet(LIVE_LEDGER, columns=list(LI.KEY_COLS))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(rows: list[dict]) -> pd.DataFrame:
    """A minimal ledger frame: the real key columns plus a couple of value columns."""
    return pd.DataFrame(rows, columns=["ticker", "date", "type", "entry_price",
                                       "fwd_ret_60", "last_backfill_asof"])


def _pair_rows(old: str, new: str, n: int, *, start_day: int = 1) -> list[dict]:
    """`n` fires logged identically under BOTH tickers — the duplicate signature."""
    rows = []
    for i in range(n):
        d = f"2020-01-{start_day + i:02d}"
        for t in (old, new):
            rows.append({"ticker": t, "date": d, "type": "buy", "entry_price": 10.0 + i,
                         "fwd_ret_60": 0.05, "last_backfill_asof": "2026-06-29"})
    return rows


# ---------------------------------------------------------------------------
# 1. The map
# ---------------------------------------------------------------------------

class TestLoadMigrations:
    def test_reads_and_uppercases(self):
        m = LI.load_migrations({"ticker_key_migrations": {"sats": "echo"}})
        assert m == {"SATS": "ECHO"}

    def test_resolves_chains_transitively(self):
        """A name renamed twice must land on ONE key, or the ledger splits three ways."""
        m = LI.load_migrations({"ticker_key_migrations": {"A": "B", "B": "C"}})
        assert m == {"A": "C", "B": "C"}
        assert LI.current_key("A", m) == "C"

    def test_cycle_is_dropped_not_looped(self):
        m = LI.load_migrations({"ticker_key_migrations": {"A": "B", "B": "A"}})
        assert m == {}

    def test_degenerate_rows_dropped(self):
        m = LI.load_migrations({"ticker_key_migrations": {"A": "A", "": "B", "C": ""}})
        assert m == {}

    def test_absent_key_yields_empty_map(self):
        assert LI.load_migrations({}) == {}

    def test_current_key_is_identity_when_unmapped(self):
        assert LI.current_key("AAPL", {"SATS": "ECHO"}) == "AAPL"


# ---------------------------------------------------------------------------
# 2. The detector — THE test that must fail on the duplicate signature
# ---------------------------------------------------------------------------

class TestDeclaredDuplicates:
    def test_identical_keysets_under_a_ratified_pair_are_found(self):
        """SATS/ECHO in miniature: two strings, one entity, identical key sets."""
        df = _ledger(_pair_rows("SATS", "ECHO", 6))
        found = LI.find_declared_duplicates(df, {"SATS": "ECHO"})

        assert len(found) == 1, "the duplicate identity must be reported"
        f = found[0]
        assert (f["superseded"], f["current"]) == ("SATS", "ECHO")
        assert f["superseded_rows"] == 6
        assert f["current_rows"] == 6
        assert f["shared_keys"] == 6
        assert f["superseded_only_keys"] == 0
        assert f["current_only_keys"] == 0

    def test_silent_when_the_superseded_key_carries_nothing(self):
        """After a migration the old key is empty — that is the CLEAN state, not a finding."""
        df = _ledger([{"ticker": "ECHO", "date": "2020-01-01", "type": "buy",
                       "entry_price": 1.0, "fwd_ret_60": None, "last_backfill_asof": None}])
        assert LI.find_declared_duplicates(df, {"SATS": "ECHO"}) == []

    def test_orphaned_superseded_rows_are_reported_even_with_no_overlap(self):
        """Rows stranded under a dead key still need migrating — they are just re-keyed."""
        df = _ledger([
            {"ticker": "SATS", "date": "2020-01-01", "type": "buy", "entry_price": 1.0,
             "fwd_ret_60": None, "last_backfill_asof": None},
            {"ticker": "ECHO", "date": "2021-01-01", "type": "buy", "entry_price": 2.0,
             "fwd_ret_60": None, "last_backfill_asof": None},
        ])
        f = LI.find_declared_duplicates(df, {"SATS": "ECHO"})[0]
        assert f["shared_keys"] == 0
        assert f["superseded_only_keys"] == 1


class TestUndeclaredDuplicates:
    """The scan that would have caught EchoStar WITHOUT knowing the rename."""

    def test_identical_keysets_under_two_unrelated_strings_are_candidates(self):
        df = _ledger(_pair_rows("SATS", "ECHO", 8))
        cand = LI.find_undeclared_duplicates(df, migrations={})
        assert len(cand) == 1
        assert cand[0]["tickers"] == ["ECHO", "SATS"]
        assert cand[0]["n_keys"] == 8

    def test_a_ratified_pair_is_not_a_candidate(self):
        """Once ratified it belongs to the declared list, with a remedy attached."""
        df = _ledger(_pair_rows("SATS", "ECHO", 8))
        assert LI.find_undeclared_duplicates(df, {"SATS": "ECHO"}) == []

    def test_dual_class_overlap_does_not_trip(self):
        """GOOG/GOOGL shape: heavy overlap, genuinely two instruments.

        Measured on the live ledger at Jaccard 0.769. Exact set EQUALITY is the whole
        point of the signature — an overlap threshold would sweep these in and the
        detector would start proposing that two real securities are one company.
        """
        rows = []
        for i in range(20):
            d = f"2020-02-{i + 1:02d}"
            rows.append({"ticker": "GOOG", "date": d, "type": "buy", "entry_price": 1.0,
                         "fwd_ret_60": None, "last_backfill_asof": None})
            rows.append({"ticker": "GOOGL", "date": d, "type": "buy", "entry_price": 1.0,
                         "fwd_ret_60": None, "last_backfill_asof": None})
        # GOOGL fires five more times; GOOG does not. Key sets now differ.
        for i in range(5):
            rows.append({"ticker": "GOOGL", "date": f"2020-03-{i + 1:02d}", "type": "buy",
                         "entry_price": 1.0, "fwd_ret_60": None, "last_backfill_asof": None})
        assert LI.find_undeclared_duplicates(_ledger(rows), {}) == []

    def test_a_handful_of_coincident_fires_does_not_trip(self):
        """AMCX/SSP shape: two unrelated names that fired once on the same date."""
        df = _ledger([
            {"ticker": "AMCX", "date": "2020-01-01", "type": "buy", "entry_price": 1.0,
             "fwd_ret_60": None, "last_backfill_asof": None},
            {"ticker": "SSP", "date": "2020-01-01", "type": "buy", "entry_price": 2.0,
             "fwd_ret_60": None, "last_backfill_asof": None},
        ])
        assert LI.find_undeclared_duplicates(df, {}) == []

    def test_min_keys_floor_is_the_only_thing_separating_them(self):
        """Pin the floor's job: below it coincidence, at/above it an identity claim."""
        n = LI.MIN_IDENTICAL_KEYS
        assert LI.find_undeclared_duplicates(_ledger(_pair_rows("A", "B", n - 1)), {}) == []
        assert len(LI.find_undeclared_duplicates(_ledger(_pair_rows("A", "B", n)), {})) == 1


# ---------------------------------------------------------------------------
# 3. The losslessness receipt — the ratification evidence
# ---------------------------------------------------------------------------

class TestMigrationReceipt:
    def test_identical_copies_are_lossless(self):
        r = LI.migration_receipt(_ledger(_pair_rows("SATS", "ECHO", 4)), "SATS", "ECHO")
        assert r["lossless"] is True
        assert r["cells_lost"] == []
        assert r["identity_conflicts"] == []
        assert r["keys_without_counterpart"] == []

    def test_a_cell_only_the_superseded_copy_holds_vetoes_the_merge(self):
        rows = _pair_rows("SATS", "ECHO", 3)
        for r in rows:                                  # ECHO never matured this one
            if r["ticker"] == "ECHO" and r["date"] == "2020-01-02":
                r["fwd_ret_60"] = None
        r = LI.migration_receipt(_ledger(rows), "SATS", "ECHO")
        assert r["lossless"] is False
        assert [c["column"] for c in r["cells_lost"]] == ["fwd_ret_60"]

    def test_disagreeing_measurements_veto_the_merge(self):
        rows = _pair_rows("SATS", "ECHO", 3)
        for r in rows:
            if r["ticker"] == "ECHO" and r["date"] == "2020-01-03":
                r["entry_price"] = 999.0
        r = LI.migration_receipt(_ledger(rows), "SATS", "ECHO")
        assert r["lossless"] is False
        assert [c["column"] for c in r["identity_conflicts"]] == ["entry_price"]

    def test_provenance_divergence_is_reported_but_never_a_veto(self):
        """The live SATS/ECHO case: three `last_backfill_asof` stamps disagree because
        the copies stopped being touched by the same run — bookkeeping, not measurement."""
        rows = _pair_rows("SATS", "ECHO", 3)
        for r in rows:
            if r["ticker"] == "ECHO":
                r["last_backfill_asof"] = "2026-07-15"
        r = LI.migration_receipt(_ledger(rows), "SATS", "ECHO")
        assert r["lossless"] is True, "a provenance stamp must not block a key migration"
        assert r["identity_conflicts"] == []
        assert {c["column"] for c in r["provenance_divergences"]} == {"last_backfill_asof"}
        assert len(r["provenance_divergences"]) == 3

    def test_provenance_carve_out_stays_narrow(self):
        """The way this protection rots is by widening the tuple. Pin it."""
        assert LI.PROVENANCE_COLS == ("first_seen_asof", "last_backfill_asof")

    def test_a_key_with_no_counterpart_is_re_keyed_not_lost(self):
        df = _ledger([
            {"ticker": "SATS", "date": "2020-05-05", "type": "buy", "entry_price": 7.0,
             "fwd_ret_60": 0.1, "last_backfill_asof": None},
        ])
        r = LI.migration_receipt(df, "SATS", "ECHO")
        assert r["keys_without_counterpart"] == [["2020-05-05", "buy"]]
        assert r["lossless"] is False   # something must move; a silent drop is not allowed


# ---------------------------------------------------------------------------
# 4. The gated repair
# ---------------------------------------------------------------------------

class TestMigrateFrame:
    def test_merge_drops_the_duplicate_and_keeps_the_current_key(self):
        from scripts.migrate_track_record_keys import migrate, plan

        df = _ledger(_pair_rows("SATS", "ECHO", 5))
        p = plan(df, {"SATS": "ECHO"})
        out = migrate(df, {"SATS": "ECHO"})

        assert len(out) == 5 == p["ledger_rows_after"]
        assert set(out["ticker"]) == {"ECHO"}
        assert p["rows_merged"] == 5 and p["rows_rekeyed"] == 0 and p["clean"] is True

    def test_the_surviving_row_is_the_copy_that_can_still_mature(self):
        """ECHO's row wins, not SATS's — SATS's price store is gone, so its copy is frozen."""
        rows = _pair_rows("SATS", "ECHO", 2)
        for r in rows:
            r["last_backfill_asof"] = "2026-07-15" if r["ticker"] == "ECHO" else "2026-06-29"
        from scripts.migrate_track_record_keys import migrate
        out = migrate(_ledger(rows), {"SATS": "ECHO"})
        assert set(out["last_backfill_asof"]) == {"2026-07-15"}

    def test_orphan_rows_are_carried_across_under_the_new_key(self):
        from scripts.migrate_track_record_keys import migrate
        df = _ledger([
            {"ticker": "SATS", "date": "2019-01-01", "type": "buy", "entry_price": 3.0,
             "fwd_ret_60": 0.2, "last_backfill_asof": None},
            {"ticker": "ECHO", "date": "2021-01-01", "type": "buy", "entry_price": 4.0,
             "fwd_ret_60": 0.3, "last_backfill_asof": None},
        ])
        out = migrate(df, {"SATS": "ECHO"})
        assert len(out) == 2
        assert set(out["ticker"]) == {"ECHO"}
        assert sorted(out["date"]) == ["2019-01-01", "2021-01-01"]

    def test_unrelated_tickers_are_untouched(self):
        from scripts.migrate_track_record_keys import migrate
        df = _ledger(_pair_rows("SATS", "ECHO", 3) + [
            {"ticker": "AAPL", "date": "2020-01-01", "type": "buy", "entry_price": 1.0,
             "fwd_ret_60": None, "last_backfill_asof": None}])
        out = migrate(df, {"SATS": "ECHO"})
        assert sorted(set(out["ticker"])) == ["AAPL", "ECHO"]
        assert len(out) == 4


# ---------------------------------------------------------------------------
# 5. The ingest guard — the ledger must stop ACCRUING the duplicate
# ---------------------------------------------------------------------------

def _mini_close(n: int = 400) -> pd.Series:
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n))),
                     index=idx, name="close")


def _rename_fixture(tmp_path: Path) -> tuple[Path, Path, Path, list[dict]]:
    """Both strings present with IDENTICAL markers and BOTH priceable — the exact
    2026-06-29 state, where the old store had not yet rotted away."""
    stocks_dir = tmp_path / "stocks"; stocks_dir.mkdir()
    signals_dir = tmp_path / "signals"; signals_dir.mkdir()
    arch = tmp_path / "track_record.parquet"
    close = _mini_close()
    markers = [{"date": "2021-01-04", "type": "buy", "quality": "take"},
               {"date": "2021-03-01", "type": "sell"}]
    for t in ("SATS", "ECHO"):
        pd.DataFrame({"close": close, "high": close * 1.01,
                      "low": close * 0.99}).to_parquet(stocks_dir / f"{t}.parquet")
        (signals_dir / f"{t}.json").write_text(json.dumps({
            "ticker": t, "asof": "2021-06-01", "tf": "3D", "state": "long-bias",
            "above200": True, "weekly_bull": True, "markers": markers,
        }))
    return signals_dir, stocks_dir, arch, markers


def test_without_the_map_both_strings_log_the_same_fires(tmp_path, monkeypatch):
    """THE CONTROL. Proves the fixture is capable of producing the duplicate, so the
    guard test below cannot pass for the wrong reason (a fixture that never logs SATS
    would look identical to a guard that works).

    The map is forced EMPTY here — the real config.yml now ships the SATS->ECHO row, so
    without this the control would be guarded too and would prove nothing.
    """
    monkeypatch.setattr(TR.ledger_identity, "load_migrations", lambda *a, **k: {})
    signals_dir, stocks_dir, arch, markers = _rename_fixture(tmp_path)
    TR.update_track_record(signals_dir=signals_dir, stocks_dir=stocks_dir,
                           out_path=arch, asof="2021-06-01")
    df = pd.read_parquet(arch)
    sats = df[df.ticker == "SATS"]
    echo = df[df.ticker == "ECHO"]
    assert len(sats) == len(echo) == len(markers)
    # ...and it is the signature: identical key sets under two strings.
    assert (set(zip(sats["date"], sats["type"]))
            == set(zip(echo["date"], echo["type"])))


def test_the_map_stops_the_superseded_key_from_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(TR.ledger_identity, "load_migrations",
                        lambda *a, **k: {"SATS": "ECHO"})
    signals_dir, stocks_dir, arch, markers = _rename_fixture(tmp_path)
    summary = TR.update_track_record(signals_dir=signals_dir, stocks_dir=stocks_dir,
                                     out_path=arch, asof="2021-06-01")
    df = pd.read_parquet(arch)

    assert df[df.ticker == "SATS"].empty, "a superseded key must never be logged"
    assert len(df[df.ticker == "ECHO"]) == len(markers), "the current key still logs"
    # The counter proves the GUARD refused it, rather than the row vanishing for some
    # other reason — and keeps the refusal countable rather than a silent `continue`.
    assert summary["skipped_superseded_key"] == len(markers)
    assert summary["migration_skips"] == {"SATS": len(markers)}


def test_near_misses_are_re_keyed_rather_than_dropped(tmp_path, monkeypatch):
    """`near` carries ONE live observation per row, not a re-dated history — so the
    honest repair is to file it under the current key, not to discard it."""
    monkeypatch.setattr(TR.ledger_identity, "load_migrations",
                        lambda *a, **k: {"SATS": "ECHO"})
    signals_dir, stocks_dir, arch, _ = _rename_fixture(tmp_path)
    reason = sorted(TR.grading.REJECTION_TAXONOMY)[0]
    out = TR.log_near_misses(
        [{"ticker": "SATS", "date": "2021-02-01", "primary_rejection_reason": reason}],
        out_path=arch, stocks_dir=stocks_dir, data_dir=tmp_path,
        stockdata_dir=tmp_path / "stockdata",
    )
    assert out["n_key_migrated"] == 1
    df = pd.read_parquet(arch)
    assert df[df.ticker == "SATS"].empty
    assert len(df[(df.ticker == "ECHO") & (df.type == TR.NEAR_MISS_TYPE)]) == 1


# ---------------------------------------------------------------------------
# 6. The live committed ledger
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not LIVE_LEDGER.exists(),
                    reason="data/ not checked out (sparse worktree) — a missing input "
                           "proves nothing and must not read as a pass")
class TestLiveLedger:
    def test_the_config_map_is_actually_wired(self):
        """Registering a map is not the same as reading one: pin the config->code join."""
        m = LI.load_migrations()
        assert m.get("SATS") == "ECHO", (
            "quality.ticker_key_migrations must declare the ratified SATS->ECHO rename"
        )
        assert "SATS" in LI.superseded_keys(m)

    def test_no_undeclared_duplicate_identity(self, live):
        """THE FORWARD GATE. A new rename that double-logs a company reds here on the
        first night, instead of six weeks later during an unrelated investigation."""
        cand = LI.find_undeclared_duplicates(live, LI.load_migrations())
        assert cand == [], (
            "ticker(s) share an IDENTICAL (date, type) key set with no ratified identity "
            f"linking them: {cand}. Either they are one company under a rename — resolve "
            "the identity (NASDAQ directory + EDGAR CIK + OpenFIGI) and add the row to "
            "config.yml quality.ticker_key_migrations — or explain why two distinct "
            "securities fire on exactly the same dates."
        )

    def test_any_declared_duplicate_is_still_safely_migratable(self, live):
        """The committed ledger keeps its SATS/ECHO double count until an operator runs
        `python scripts/migrate_track_record_keys.py --apply` (the parquet is append-only
        by charter, so the repair is a ratified act, not a nightly one). What must hold
        meanwhile is that the repair stays SAFE — nothing may drift into a state where
        merging the keys would lose or contradict a measurement.
        """
        full = pd.read_parquet(LIVE_LEDGER)
        for f in LI.find_declared_duplicates(full, LI.load_migrations()):
            r = LI.migration_receipt(full, f["superseded"], f["current"])
            assert r["lossless"], (
                f"{f['superseded']}->{f['current']} is no longer a clean key migration: "
                f"{len(r['cells_lost'])} cell(s) only the superseded copy holds, "
                f"{len(r['identity_conflicts'])} disagreeing cell(s), "
                f"{len(r['keys_without_counterpart'])} orphan key(s). "
                "Re-examine the identity before rewriting an append-only ledger."
            )
