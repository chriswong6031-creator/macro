"""G-D — the plan-book board read: join semantics, honest absence, coverage telemetry.

The gate this pins (MP-1 spawn gate G-D): every plan row must end in a state a surface
can render without inventing anything — a canonical actionability read, or a disclosed
absence with a machine-readable cause. The failure mode these tests exist to make
impossible is the quiet one: a join that silently reaches 45 of 179 rows and reads, on
screen, exactly like a board with nothing to say.
"""

import json

import pytest

from engine import prophet_board_read as pbr


# ── fixtures ──────────────────────────────────────────────────────────────────
def plan(pid="P1", asset="AAA", closed=False, **kw):
    return {"id": pid, "asset": asset, "closed": closed, **kw}


def library(tmp_path, records):
    """A LibraryIndex over a real temp tree — the reader is exercised, not stubbed."""
    root = tmp_path / "stockdata"
    root.mkdir(exist_ok=True)
    for ticker, rec in records.items():
        (root / f"{pbr.safe_ticker(ticker)}.json").write_text(json.dumps(rec))
    return pbr.LibraryIndex(root)


def rec(status=None, *, name="Alpha Co", sector="Tech", spark="<svg/>",
        null_reason=None, asof="2026-08-13"):
    out = {"name": name, "sector": sector, "spark_svg": spark, "asof": asof}
    if status is not None:
        out["entry_signal"] = {"status": status}
    if null_reason is not None:
        out["entry_signal_null_reason"] = null_reason
    return {k: v for k, v in out.items() if v is not None}


def standouts(**buckets):
    return {"as_of": "2026-08-12", **buckets}


def field(block, name):
    return block["fields"][name]


# ── 1. the actionability axis comes from the entry/actionability authority ────
class TestActionabilityAuthority:
    def test_status_is_the_entry_signal_status(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now")})
        block = pbr.build_board_read(plan(), library=lib)
        assert field(block, "status") == {
            "value": "buy_now", "state": pbr.AVAILABLE,
            "reason": None, "source": pbr.SRC_LIBRARY,
        }

    def test_recommended_action_is_never_substituted(self, tmp_path):
        """The management engine is trade-management-only; its action carries
        display/narrative authority, not order authority (operator ruling 2026-08-13).
        A plan loudly carrying one, with no axis, is still BLOCKED_DATA."""
        lib = library(tmp_path, {"AAA": rec(None, null_reason="no_cycle_ladder")})
        block = pbr.build_board_read(
            plan(recommended_action="hold",
                 state={"recommended_action": "hold"}),
            library=lib)
        got = field(block, "status")
        assert got["state"] == pbr.BLOCKED_DATA
        assert got["value"] is None
        assert "hold" not in json.dumps(got)

    def test_unknown_row_never_becomes_wait(self, tmp_path):
        """Coverage is an outcome, not a target. Mapping an unobtainable axis to a
        cautious-looking verb would originate a signal the engine never stated."""
        lib = pbr.LibraryIndex(tmp_path / "absent")
        for p in (plan(), plan(asset="ZZZ"), plan(asset="")):
            got = field(pbr.build_board_read(p, library=lib), "status")
            assert got["value"] is None
            assert got["state"] == pbr.BLOCKED_DATA

    def test_frozen_admission_stamp_is_not_read_and_not_written(self, tmp_path):
        """`entry_status` is the §6.2 A1 admission stamp — frozen, null before the era,
        read as provenance by us_candidate_lanes / prophet_arena. The live read must
        neither consume it nor overwrite it."""
        lib = library(tmp_path, {"AAA": rec("buy_soon")})
        row = plan(entry_status="bounce_wait")
        pbr.attach([row], library=lib)
        assert row["entry_status"] == "bounce_wait"          # untouched
        assert field(row[pbr.BLOCK_KEY], "status")["value"] == "buy_soon"

    def test_axis_absent_everywhere_is_blocked_not_absent_key(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec(None)})
        got = field(pbr.build_board_read(plan(), library=lib), "status")
        assert got["state"] == pbr.BLOCKED_DATA
        assert got["reason"] == pbr.R_GAUGE_UNDISCLOSED


# ── 2. every row ends in exactly one of three honest states ──────────────────
class TestThreeHonestStates:
    def test_closed_plan_is_not_applicable_not_blocked(self, tmp_path):
        """A resolved plan has no live stance. Reporting that as missing data would
        make a complete answer look like a gap."""
        lib = library(tmp_path, {"AAA": rec("buy_now")})
        got = field(pbr.build_board_read(plan(closed=True), library=lib), "status")
        assert got["state"] == pbr.NOT_APPLICABLE
        assert got["reason"] == pbr.R_PLAN_CLOSED
        assert got["value"] is None

    def test_whole_source_outage_is_distinguishable_from_ticker_misses(self, tmp_path):
        """179 rows blocked because the tree is gone must not read as 179 individually
        unlucky tickers — the causes route to different fixes."""
        absent = pbr.LibraryIndex(tmp_path / "nope")
        assert field(pbr.build_board_read(plan(), library=absent), "status")["reason"] \
            == pbr.R_SOURCE_UNAVAILABLE
        present = library(tmp_path, {"BBB": rec("hold")})
        assert field(pbr.build_board_read(plan(), library=present), "status")["reason"] \
            == pbr.R_TICKER_ABSENT

    def test_gauge_null_reuses_the_gauges_own_vocabulary(self, tmp_path):
        """engine.entry_signal.null_reason already names these causes. One cause, one
        name — a second vocabulary is a second story about the same fact."""
        for reason in ("no_cycle_ladder", "short_history", "not_assessed",
                       "gauge_error:ValueError"):
            lib = library(tmp_path, {"AAA": rec(None, null_reason=reason)})
            got = field(pbr.build_board_read(plan(), library=lib), "status")
            assert got["state"] == pbr.BLOCKED_DATA
            assert got["reason"] == f"{pbr.R_GAUGE_NULL_PREFIX}{reason}"

    @pytest.mark.parametrize("name", pbr.FIELDS)
    def test_every_field_terminates_in_a_known_state_with_a_cause(self, tmp_path, name):
        lib = library(tmp_path, {"AAA": rec("buy_now")})
        rows = [plan(), plan("P2", "ZZZ"), plan("P3", closed=True), plan("P4", "")]
        pbr.attach(rows, library=lib, standouts=standouts(
            buy=[{"ticker": "AAA", "lane": "bottoming"}]))
        for row in rows:
            got = field(row[pbr.BLOCK_KEY], name)
            assert got["state"] in pbr.STATES
            if got["state"] == pbr.AVAILABLE:
                assert got["value"] is not None and got["reason"] is None
                assert got["source"] in (pbr.SRC_LIBRARY, pbr.SRC_STANDOUTS)
            else:
                assert got["value"] is None
                assert (got["reason"] in pbr.REASONS
                        or got["reason"].startswith(pbr.R_GAUGE_NULL_PREFIX)), got


# ── 3. lane is a board-membership label, never derived ───────────────────────
class TestLaneIsNotDerived:
    def test_off_board_lane_is_not_applicable(self, tmp_path):
        """`build_stock_library._lane_for` is TOTAL — it returns 'bottoming' for input
        it does not recognise. Running it off-board would give 100% lane coverage made
        entirely of fabricated setup archetypes."""
        lib = library(tmp_path, {"AAA": rec("buy_now")})
        got = field(pbr.build_board_read(plan(), library=lib, board_rows={}), "lane")
        assert got["state"] == pbr.NOT_APPLICABLE
        assert got["reason"] == pbr.R_NOT_ON_BOARD

    def test_lane_bearing_bucket_supplies_it(self, tmp_path):
        rows = [plan()]
        pbr.attach(rows, library=library(tmp_path, {}),
                   standouts=standouts(buy=[{"ticker": "AAA", "lane": "continuation"}]))
        assert field(rows[0][pbr.BLOCK_KEY], "lane") == {
            "value": "continuation", "state": pbr.AVAILABLE,
            "reason": None, "source": pbr.SRC_STANDOUTS,
        }

    def test_laggards_carry_no_lane_and_say_so_distinctly(self, tmp_path):
        rows = [plan()]
        pbr.attach(rows, library=library(tmp_path, {}),
                   standouts=standouts(laggards=[{"ticker": "AAA", "name": "Alpha"}]))
        got = field(rows[0][pbr.BLOCK_KEY], "lane")
        assert got["state"] == pbr.NOT_APPLICABLE
        assert got["reason"] == pbr.R_BUCKET_NO_LANE   # NOT not_on_board — it IS on board

    def test_lane_never_falls_back_to_the_library(self, tmp_path):
        """A library record carrying a stray `lane` must not be promoted into a board
        label; the field means board membership, not any lane-shaped string."""
        lib = library(tmp_path, {"AAA": dict(rec("buy_now"), lane="bottoming")})
        got = field(pbr.build_board_read(plan(), library=lib, board_rows={}), "lane")
        assert got["state"] == pbr.NOT_APPLICABLE


# ── 4. plan identity survives a ticker-keyed join ────────────────────────────
class TestEpisodeIdentity:
    def test_ticker_enrichment_fans_out_without_collapsing_episodes(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now")})
        rows = [plan("P1"), plan("P2"), plan("P3", closed=True)]
        pbr.attach(rows, library=lib)
        assert len({id(r[pbr.BLOCK_KEY]) for r in rows}) == 3   # three distinct blocks
        assert [field(r[pbr.BLOCK_KEY], "name")["value"] for r in rows] == ["Alpha Co"] * 3
        # …and applicability is still decided PER PLAN, not per ticker.
        states = [field(r[pbr.BLOCK_KEY], "status")["state"] for r in rows]
        assert states == [pbr.AVAILABLE, pbr.AVAILABLE, pbr.NOT_APPLICABLE]

    def test_scope_is_declared_on_the_row(self, tmp_path):
        block = pbr.build_board_read(plan(), library=library(tmp_path, {"AAA": rec("hold")}))
        assert block["scope"] == "ticker"      # so a surface cannot present it per-episode
        assert block["ticker"] == "AAA"


# ── 5. coverage telemetry — the regression tripwire ──────────────────────────
class TestCoverageTelemetry:
    def test_states_partition_the_rows_for_every_field(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now"), "BBB": rec(None, null_reason="short_history")})
        rows = [plan("P1", "AAA"), plan("P2", "BBB"), plan("P3", "CCC"),
                plan("P4", "AAA", closed=True)]
        pbr.attach(rows, library=lib, standouts=standouts(buy=[{"ticker": "AAA", "lane": "bottoming"}]))
        cov = pbr.coverage(rows, library=lib)
        assert cov["rows"] == 4
        for name in pbr.FIELDS:
            counts = {k: v for k, v in cov["by_field"][name].items()
                      if k not in ("reasons", "sources")}
            assert sum(counts.values()) == 4, (name, counts)
            assert set(counts) <= set(pbr.STATES), (name, counts)

    def test_a_179_to_45_regression_is_visible_as_a_number(self, tmp_path):
        """The whole point of the block. A source outage must move a published count,
        not just quietly empty the board."""
        rows = [plan(f"P{i}", f"T{i}") for i in range(20)]
        healthy = library(tmp_path, {f"T{i}": rec("buy_now") for i in range(20)})
        pbr.attach(rows, library=healthy)
        assert pbr.coverage(rows, library=healthy)["by_field"]["status"][pbr.AVAILABLE] == 20

        outage = pbr.LibraryIndex(tmp_path / "gone")
        pbr.attach(rows, library=outage)
        cov = pbr.coverage(rows, library=outage)
        assert cov["by_field"]["status"][pbr.AVAILABLE] == 0
        assert cov["source_available"] is False
        assert cov["by_field"]["status"]["reasons"] == {pbr.R_SOURCE_UNAVAILABLE: 20}
        assert cov["blocked_data_rows"] == 20

    def test_unmapped_status_word_surfaces_instead_of_being_relabelled(self, tmp_path):
        """If the engine's twelve-value domain grows a thirteenth word, the Board's
        stance projection cannot place it. Publish it verbatim and COUNT it — never
        drop it, never map it to something renderable."""
        lib = library(tmp_path, {"AAA": rec("teleporting")})
        rows = [plan()]
        pbr.attach(rows, library=lib)
        cov = pbr.coverage(rows, library=lib)
        assert field(rows[0][pbr.BLOCK_KEY], "status")["value"] == "teleporting"
        assert cov["status_unmapped"] == {"teleporting": 1}

    def test_known_statuses_do_not_trip_the_unmapped_counter(self, tmp_path):
        lib = library(tmp_path, {t: rec(t) for t in pbr.KNOWN_STATUSES})
        rows = [plan(f"P{i}", t) for i, t in enumerate(sorted(pbr.KNOWN_STATUSES))]
        pbr.attach(rows, library=lib)
        assert pbr.coverage(rows, library=lib)["status_unmapped"] == {}

    def test_unreadable_record_is_a_disclosed_null_and_a_named_read_error(self, tmp_path):
        root = tmp_path / "stockdata"
        root.mkdir()
        (root / "AAA.json").write_text("{not json")
        lib = pbr.LibraryIndex(root)
        rows = [plan()]
        pbr.attach(rows, library=lib)
        cov = pbr.coverage(rows, library=lib)
        assert field(rows[0][pbr.BLOCK_KEY], "status")["state"] == pbr.BLOCKED_DATA
        assert "AAA" in cov["read_errors"]


# ── 6. lineage is declared, and vintage cannot be overclaimed ────────────────
class TestLineage:
    def test_every_governed_field_has_a_declared_source(self, tmp_path):
        lin = pbr.lineage(library=library(tmp_path, {}), standouts=standouts())
        declared = {f for src in lin["sources"] for f in src["fields"]}
        assert set(pbr.FIELDS) <= declared
        assert lin["join_key"] == "ticker"
        assert set(lin["states"]) == set(pbr.STATES)

    def test_lineage_names_the_authority_and_disclaims_the_substitute(self, tmp_path):
        lin = pbr.lineage(library=library(tmp_path, {}), standouts=standouts())
        assert "entry_signal.status" in lin["authority"]["status"]
        assert "recommended_action" in lin["authority"]["status"]
        assert "admission stamp" in lin["note"]

    def test_vintage_is_read_back_from_the_records_not_asserted(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now", asof="2026-08-13"),
                                 "BBB": rec("hold", asof="2026-08-13")})
        pbr.attach([plan("P1", "AAA"), plan("P2", "BBB")], library=lib)
        assert lib.as_of() == "2026-08-13"

    def test_disagreeing_record_vintages_refuse_to_name_one(self, tmp_path):
        """A mixed-vintage tree must not publish whichever date it happened to see
        first — an unknown as-of is the honest answer and the caller can disclose it."""
        lib = library(tmp_path, {"AAA": rec("buy_now", asof="2026-08-13"),
                                 "BBB": rec("hold", asof="2026-07-01")})
        pbr.attach([plan("P1", "AAA"), plan("P2", "BBB")], library=lib)
        assert lib.as_of() is None


# ── 7. the spark sibling ─────────────────────────────────────────────────────
class TestSparkArtifact:
    def test_reference_resolves_into_the_banked_artifact(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now", spark="<svg id=a/>")})
        rows = [plan("P1"), plan("P2")]           # two episodes, one ticker
        sparks = pbr.attach(rows, library=lib)
        art = pbr.sparks_artifact(sparks, library=lib)
        for row in rows:
            got = field(row[pbr.BLOCK_KEY], "spark")
            assert got["state"] == pbr.AVAILABLE
            assert got["value"] == f"{pbr.SPARKS_FILENAME}#AAA"
            assert art["sparks"][got["value"].split("#", 1)[1]] == "<svg id=a/>"
        assert art["n"] == 1                      # ticker-keyed: banked once, not twice

    def test_available_is_never_claimed_without_a_banked_body(self, tmp_path):
        lib = library(tmp_path, {"AAA": rec("buy_now", spark=None)})
        rows = [plan()]
        sparks = pbr.attach(rows, library=lib)
        assert field(rows[0][pbr.BLOCK_KEY], "spark")["state"] == pbr.BLOCKED_DATA
        assert sparks == {}


# ── 7b. the sibling lands beside the index that references it ────────────────
def test_sparks_artifact_follows_index_path_not_site_prophet(tmp_path, monkeypatch):
    """The `spark` value is a reference RELATIVE TO index.json, so the artifact must
    land beside whichever index the run writes.

    Regression: the first cut wrote to `SITE_PROPHET / SPARKS_FILENAME`, and
    test_prophet_bridge.py::test_end_to_end_smoke redirects INDEX_PATH to tmp_path while
    leaving SITE_PROPHET alone — so the write escaped into the real `site/prophet/`
    (and, in a sparse agent worktree, into an omitted tree). Same module-constant trap
    that file already documents twice for write_showcase.
    """
    from scripts import build_prophet as bp

    src = (__import__("pathlib").Path(bp.__file__)).read_text()
    marker = f"prophet_board_read.SPARKS_FILENAME"
    write_line = next(ln for ln in src.splitlines()
                      if marker in ln and "_write_json" in ln)
    assert "INDEX_PATH.parent" in write_line, write_line
    assert "SITE_PROPHET" not in write_line, write_line


# ── 8. the join key itself ───────────────────────────────────────────────────
class TestJoinKey:
    def test_safe_ticker_mirrors_the_producers_filename_mapping(self):
        # scripts/build_stock_library.py: safe = ticker.replace("=","_").replace("^","_")
        assert pbr.safe_ticker("BRK=B") == "BRK_B"
        assert pbr.safe_ticker("^GSPC") == "_GSPC"
        assert pbr.safe_ticker("AAPL") == "AAPL"

    def test_bucket_precedence_is_the_boards_own(self, tmp_path):
        idx = pbr.standouts_index(standouts(
            buy=[{"ticker": "AAA", "lane": "bottoming"}],
            watch=[{"ticker": "AAA", "lane": "watch"}]))
        assert idx["AAA"]["lane"] == "bottoming"
        assert idx["AAA"]["_bucket"] == "buy"


# ── 9. producer contract — the fields the join depends on must keep shipping ──
def test_producer_stamps_the_enrichment_onto_every_universe_record():
    """`build_stock_library` writes disp_map's spark and the gauge's disclosed null onto
    the per-name record, in the same loop iteration that appends it to `to_write`.

    That co-location is the whole basis for claiming spark coverage EQUALS library-record
    coverage rather than merely tracking it — a `continue` slipped between the stamp and
    the write would silently split the two populations again, which is exactly the shape
    of the bug this gate exists to close."""
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent
           / "scripts" / "build_stock_library.py").read_text().splitlines()
    spark = next(i for i, line in enumerate(src) if 'rec["spark_svg"] = _spark' in line)
    null = next(i for i, line in enumerate(src) if 'rec["entry_signal_null_reason"] = entry_sig_null' in line)
    write = next(i for i, line in enumerate(src) if "to_write.append((safe, rec))" in line)
    assert spark < write and null < write
    between = src[spark:write]
    assert not [ln for ln in between
                if ln.strip().startswith(("continue", "break", "return"))], between


def test_producer_does_not_stamp_price_into_the_board_read_lane():
    """The quote half is not this lane's. `last_price` is already on the plan row and the
    live quote is the page's `data-sym` path — so disp_map's `price`/`off_high` must not
    ride along (a top-level `price` would also shadow `tech.price` for every stockdata
    reader)."""
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent
           / "scripts" / "build_stock_library.py").read_text()
    assert 'rec["price"]' not in src
    assert 'rec.update({k: v for k, v in (disp_map.' not in src
    assert "price" not in pbr.FIELDS and "change" not in pbr.FIELDS
