"""Hermetic tests for engine/qledger_desk_adapter.py — the T9 wave-1 translator
that mirrors POOL_DESKS thesis rows into the Universal Scoreboard.

FIXTURE-ONLY BY LAW. Nothing here reads or asserts over data/qledger/claims.jsonl
or any desk's committed theses.jsonl: those are nightly-appended stores whose
contents change every night, and a test that pins their content is a scheduled
red. Every claim in this file is registered against a tmp_path root.

What is pinned:
  * DIRECTION IS ENGINE-DERIVED (R4) — the sign is read off the predicate the
    desks' OWN `_derive_check`/`_thesis_for` functions emit, and those functions
    are called here rather than re-implemented, so a change to a desk's lean→op
    mapping breaks this suite instead of silently re-labelling the corpus.
  * A DECLARED NO-CALL IS SKIPPED, never filed as direction=0. direction==0 means
    SALIENCE (hit is null by construction) and 71% of the corpus already is;
    mapping 247 neutral stock_desk leans onto it would grow that share with rows
    the desk itself declared unscoreable.
  * horizon_d IS THE ROW'S OWN RULER (R2) — never substituted for a shorter one.
  * bench IS READ, never defaulted — a non-SPY-benched desk must not silently
    become an SPY claim.
  * IDEMPOTENCE — an explicit salt (the thesis id) means a re-run registers zero
    new rows, and two same-day rows on one ticker never collide into one.
  * The claims validate under qledger's own `_validate_claim`.
"""
from __future__ import annotations

import json

import pytest

from engine import demand_ledger, qledger as q, qledger_desk_adapter as qa
from engine import stock_desk, thematic_desk


# --------------------------------------------------------------------------- #
# fixtures — synthetic rows in each desk's committed schema
# --------------------------------------------------------------------------- #
def _demand_row(**over) -> dict:
    """A demand_chain row, built by the ENGINE's own `_thesis_for` so the lean →
    op/threshold mapping under test is the shipped one."""
    read = {"leading": True, "divergence": "ahead_of_consensus", "chain_key": "own_rpo",
            "fy_latest": 2025, "horizon_d": 126, "trend": "accelerating",
            "yoy_pct": 26.5, "tier": "bookings"}
    read.update(over.pop("read", {}))
    row = demand_ledger._thesis_for("NOW", read, "2026-08-09", 124.88, 773.26)
    row.update(over)
    return row


def _stock_row(lean: str, horizon: int = 20, ticker: str = "CASY") -> dict:
    check = stock_desk._derive_check(ticker, lean, horizon, {})
    entry = ({ticker: 850.849976, "SPY": 740.960022}
             if check.get("kind") == "rel_return" else {})
    return {"id": f"2026-08-10-{ticker}-20260811041812-6", "state_asof": "2026-08-10",
            "ticker": ticker, "lean": lean, "conviction": "low", "horizon_d": horizon,
            "falsifier": {"text": "…", "check": check},
            "check_by": "2026-09-07", "entry_levels": entry,
            "status": "open", "outcome": None}


_THEME_RANKS = [{"id": "us_semis", "name": "Semiconductors", "etf_proxy": "SMH"},
                {"id": "ca_telecom", "name": "Telecom", "etf_proxy": "XCD.TO"},
                {"id": "us_vibes", "name": "Vibes", "etf_proxy": None}]


def _thematic_row(lean: str, subject: str = "Semiconductors", region: str = "us",
                  horizon: int = 20) -> dict:
    check = thematic_desk._derive_check(subject, lean, horizon, region, _THEME_RANKS, {})
    entry = {}
    if check.get("kind") == "theme_rel_return":
        entry = {check["subject_ticker"]: 300.0, check["vs"]: 740.96}
    return {"id": f"{region}-2026-08-07-20260810024400-2", "market": region,
            "subject": subject, "lean": lean, "conviction": "low",
            "horizon_d": horizon, "state_asof": "2026-08-07",
            "falsifier": {"text": "…", "check": check},
            "check_by": "2026-09-18", "entry_levels": entry}


# --------------------------------------------------------------------------- #
# R4 — the direction is the ENGINE's, never the adapter's
# --------------------------------------------------------------------------- #
class TestDirectionIsEngineDerived:
    def test_demand_chain_both_divergences(self):
        long_row = _demand_row()
        short_row = _demand_row(read={"divergence": "consensus_at_risk"})
        assert long_row["lean"] == "outperform"
        assert short_row["lean"] == "underperform"
        assert qa.direction_from_check(long_row["falsifier"]["check"]) == 1
        assert qa.direction_from_check(short_row["falsifier"]["check"]) == -1

    @pytest.mark.parametrize("lean,expected", [
        ("constructive", 1), ("cautious", -1), ("avoid", -1), ("neutral", None)])
    def test_stock_desk_leans(self, lean, expected):
        check = stock_desk._derive_check("CASY", lean, 20, {})
        assert qa.direction_from_check(check) == expected

    @pytest.mark.parametrize("lean,expected", [
        ("overweight", 1), ("underweight", -1), ("avoid", -1)])
    def test_thematic_desk_leans(self, lean, expected):
        check = thematic_desk._derive_check("Semiconductors", lean, 20, "us",
                                            _THEME_RANKS, {})
        assert qa.direction_from_check(check) == expected

    def test_theme_without_scalar_proxy_is_soft(self):
        check = thematic_desk._derive_check("Vibes", "overweight", 20, "us",
                                            _THEME_RANKS, {})
        assert check["kind"] == "soft"
        assert qa.direction_from_check(check) is None

    def test_unknown_kind_and_disagreeing_predicate_are_not_directional(self):
        # a `level` predicate (ai_desk's fade-fear leg) has no subject-vs-bench home
        assert qa.direction_from_check({"kind": "level", "op": "<", "threshold": -0.05}) is None
        # op and threshold must AGREE — a mismatched pair is not a predicate any of
        # these engines emits, so the adapter refuses to guess a sign for it.
        assert qa.direction_from_check(
            {"kind": "rel_return", "op": "<", "threshold": 0.05}) is None
        assert qa.direction_from_check(
            {"kind": "rel_return", "op": ">", "threshold": -0.05}) is None
        assert qa.direction_from_check(None) is None


class TestNoCallIsSkippedNotSalience:
    def test_neutral_stock_lean_produces_no_claim(self):
        row = _stock_row("neutral")
        assert row["falsifier"]["check"]["kind"] == "soft"
        assert qa.claim_from_thesis(row, desk="stock_desk", claim_family="stock_desk",
                                    timestamp_quality="CRAWL_BOUNDED") is None

    def test_batch_never_emits_direction_zero(self):
        rows = [_stock_row(l, ticker=t) for l, t in
                (("constructive", "A"), ("neutral", "B"), ("cautious", "C"),
                 ("avoid", "D"), ("neutral", "E"))]
        claims, stats = qa.claims_from_theses(
            rows, desk="stock_desk", claim_family="stock_desk",
            timestamp_quality="CRAWL_BOUNDED")
        assert stats["n_rows"] == 5
        assert stats["n_claims"] == 3
        assert stats["n_skipped_no_call"] == 2
        assert all(c["direction"] in (-1, 1) for c in claims)
        assert not any(c["direction"] == 0 for c in claims)


# --------------------------------------------------------------------------- #
# R2 / bench / PIT — every field is lifted, none is substituted
# --------------------------------------------------------------------------- #
class TestFieldsAreLiftedNotInvented:
    def test_demand_chain_claim_shape(self):
        row = _demand_row()
        c = qa.claim_from_thesis(row, desk="demand_chain", claim_family="demand_chain",
                                 timestamp_quality="DISCLOSURE_DATE")
        assert c["horizon_d"] == 126 == row["horizon_d"]      # the declared ruler
        assert c["scope"] == {"type": "entity", "key": "NOW"}
        assert c["bench"] == "SPY"
        assert c["control"] is None                           # no sector on this desk
        assert c["entry_levels"] == {"subject": 124.88, "bench": 773.26}
        assert c["check_by"] == row["check_by"] == "2027-02-01"
        assert c["falsifier"] is row["falsifier"]
        assert c["timestamp_quality"] == "DISCLOSURE_DATE"
        assert c["salt"] == row["id"]
        assert c["source_id"] == row["id"]
        ok, why = q._validate_claim(c)
        assert ok, why

    @pytest.mark.parametrize("horizon", [10, 15, 20, 21, 25, 30, 60])
    def test_horizon_is_never_substituted(self, horizon):
        c = qa.claim_from_thesis(_stock_row("constructive", horizon=horizon),
                                 desk="stock_desk", claim_family="stock_desk",
                                 timestamp_quality="CRAWL_BOUNDED")
        assert c["horizon_d"] == horizon

    def test_bench_is_read_from_the_predicate_not_defaulted(self):
        row = _thematic_row("avoid", subject="Telecom", region="canada")
        assert row["falsifier"]["check"]["vs"] == "XIC.TO"
        c = qa.claim_from_thesis(row, desk="thematic_desk",
                                 claim_family="thematic_desk_ca",
                                 timestamp_quality="CRAWL_BOUNDED")
        assert c["bench"] == "XIC.TO"
        assert c["bench"] != q.default_bench_for("entity", "XCD.TO")

    def test_thematic_scope_key_is_the_proxy_not_the_theme_label(self):
        row = _thematic_row("overweight")
        c = qa.claim_from_thesis(row, desk="thematic_desk",
                                 claim_family="thematic_desk_us",
                                 timestamp_quality="CRAWL_BOUNDED")
        assert c["scope"] == {"type": "entity", "key": "SMH"}   # priceable
        assert c["scope"]["key"] != row["subject"]
        assert c["control"] is None       # no matched control for a theme proxy

    def test_stock_desk_control_is_the_sector_etf(self):
        c = qa.claim_from_thesis(_stock_row("constructive", ticker="NVDA"),
                                 desk="stock_desk", claim_family="stock_desk",
                                 timestamp_quality="CRAWL_BOUNDED",
                                 sector_of={"NVDA": "Information Technology"}.get)
        assert c["control"] == "XLK"
        assert c["control"] != c["scope"]["key"]   # never degenerate

    def test_row_without_a_stable_id_is_skipped(self):
        row = _stock_row("constructive")
        row["id"] = ""
        assert qa.claim_from_thesis(row, desk="stock_desk", claim_family="stock_desk",
                                    timestamp_quality="CRAWL_BOUNDED") is None


# --------------------------------------------------------------------------- #
# registration — idempotent, batched, marked
# --------------------------------------------------------------------------- #
def _stored(root):
    return q.load_claims(root)


class TestRegistration:
    def test_re_running_registers_nothing_new(self, tmp_path):
        rows = [_stock_row("constructive", ticker="A"), _stock_row("avoid", ticker="B")]
        first = qa.register_theses(rows, desk="stock_desk", claim_family="stock_desk",
                                   timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        n1 = len(_stored(tmp_path))
        second = qa.register_theses(rows, desk="stock_desk", claim_family="stock_desk",
                                    timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        n2 = len(_stored(tmp_path))
        assert first["n_claims"] == second["n_claims"] == 2
        assert n1 == 2
        assert n2 == n1, "re-running the adapter duplicated claims"

    def test_two_same_day_rows_on_one_ticker_stay_distinct(self, tmp_path):
        a = _stock_row("constructive", ticker="WT")
        b = _stock_row("constructive", ticker="WT")
        b["id"] = a["id"] + "-2"
        qa.register_theses([a, b], desk="stock_desk", claim_family="stock_desk",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        ids = {c["claim_id"] for c in _stored(tmp_path)}
        assert len(ids) == 2, "an unsalted claim_id collapsed two leans into one"

    def test_duplicate_ids_in_one_ledger_keep_first(self, tmp_path):
        """stock_desk's pre-run_token ledger carries one id under CONTRADICTORY
        leans; first-wins, and the second never silently overwrites."""
        a = _stock_row("constructive", ticker="WT")
        b = _stock_row("cautious", ticker="WT")
        b["id"] = a["id"]
        qa.register_theses([a, b], desk="stock_desk", claim_family="stock_desk",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        claims = _stored(tmp_path)
        assert len(claims) == 1
        assert claims[0]["direction"] == 1

    def test_backfilled_rows_are_marked(self, tmp_path):
        fresh = _stock_row("constructive", ticker="A")
        old = _stock_row("avoid", ticker="B")
        qa.register_theses([fresh, old], desk="stock_desk", claim_family="stock_desk",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path,
                           forward_ids={fresh["id"]})
        by_key = {c["scope"]["key"]: c for c in _stored(tmp_path)}
        assert by_key["A"].get("backfilled") is None
        assert by_key["B"]["backfilled"] is True

    def test_all_registered_claims_validate(self, tmp_path):
        rows = ([_demand_row()]
                + [_stock_row(l, ticker=t) for l, t in
                   (("constructive", "A"), ("cautious", "B"))]
                + [_thematic_row("overweight"), _thematic_row("avoid", subject="Vibes")])
        for row, desk, tq in ((rows[0], "demand_chain", "DISCLOSURE_DATE"),
                              (rows[1], "stock_desk", "CRAWL_BOUNDED"),
                              (rows[2], "stock_desk", "CRAWL_BOUNDED"),
                              (rows[3], "thematic_desk", "CRAWL_BOUNDED"),
                              (rows[4], "thematic_desk", "CRAWL_BOUNDED")):
            qa.register_theses([row], desk=desk, claim_family=desk,
                               timestamp_quality=tq, root=tmp_path,
                               warn_when_empty=False)
        claims = _stored(tmp_path)
        assert claims, "no claims registered"
        assert all(c["status"] == "open" for c in claims), \
            [c.get("reject_reason") for c in claims if c["status"] != "open"]
        # the soft "Vibes" row must not have produced a claim
        assert len(claims) == 4

    def test_dark_desk_emits_a_line_start_annotation(self, tmp_path, capsys):
        qa.register_theses([_stock_row("neutral")], desk="stock_desk",
                           claim_family="stock_desk",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if "stock_desk-no-claims" in ln]
        assert lines, out
        # GitHub drops an annotation that does not START the line (a logger would
        # prefix it with the level) — pin the position, not the wording.
        assert lines[0].startswith("::warning "), lines[0]

    def test_registration_never_raises_on_garbage(self, tmp_path):
        stats = qa.register_theses([None, 7, {}, {"falsifier": "not a dict"}],
                                   desk="stock_desk", claim_family="stock_desk",
                                   timestamp_quality="CRAWL_BOUNDED", root=tmp_path,
                                   warn_when_empty=False)
        assert stats["n_claims"] == 0
        assert not _stored(tmp_path)


class TestRegisterLedger:
    def test_filter_and_forward_ids(self, tmp_path):
        us_new = _thematic_row("overweight")
        us_old = _thematic_row("avoid", subject="Semiconductors")
        us_old["id"] = "us-2026-07-01-abc-1"
        ca = _thematic_row("avoid", subject="Telecom", region="canada")
        lp = tmp_path / "theses.jsonl"
        lp.write_text("\n".join(json.dumps(r) for r in (us_new, us_old, ca)) + "\n")

        qa.register_ledger(lp, desk="thematic_desk", claim_family="thematic_desk_us",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path,
                           forward_ids={us_new["id"]},
                           row_filter=lambda r: r.get("market") == "us")
        claims = _stored(tmp_path)
        assert len(claims) == 2, "the canada leg (unpriceable bench) must not register"
        assert {c["bench"] for c in claims} == {"SPY"}
        marked = {c["source_id"]: c.get("backfilled") for c in claims}
        assert marked[us_new["id"]] is None
        assert marked[us_old["id"]] is True

    def test_include_backfill_false_registers_only_this_run(self, tmp_path):
        new = _stock_row("constructive", ticker="A")
        old = _stock_row("cautious", ticker="B")
        old["id"] = "2026-06-18-WT-3"
        lp = tmp_path / "theses.jsonl"
        lp.write_text("\n".join(json.dumps(r) for r in (new, old)) + "\n")
        qa.register_ledger(lp, desk="stock_desk", claim_family="stock_desk",
                           timestamp_quality="CRAWL_BOUNDED", root=tmp_path,
                           forward_ids={new["id"]}, include_backfill=False)
        claims = _stored(tmp_path)
        assert [c["source_id"] for c in claims] == [new["id"]]

    def test_missing_ledger_is_not_an_error(self, tmp_path):
        stats = qa.register_ledger(tmp_path / "nope.jsonl", desk="stock_desk",
                                   claim_family="stock_desk",
                                   timestamp_quality="CRAWL_BOUNDED", root=tmp_path)
        assert stats["n_claims"] == 0
        assert not _stored(tmp_path)


# --------------------------------------------------------------------------- #
# desk wiring — the call sites the nightly path depends on
# --------------------------------------------------------------------------- #
class TestDeskWiring:
    def test_stock_desk_append_returns_the_rows_it_wrote(self, tmp_path, monkeypatch):
        """run() registers claims for exactly the rows that survived the
        id-immutability gate, so _append_ledger must hand them back."""
        monkeypatch.setattr(stock_desk, "_entry_levels", lambda check, asof: {})
        notes = [{"id": "2026-08-10-AAA-tok-1", "ticker": "AAA", "lean": "constructive",
                  "conviction": "low", "horizon_d": 20,
                  "falsifier": {"check": stock_desk._derive_check("AAA", "constructive", 20, {})},
                  "check_by": "2026-09-07", "engine_verdict": None}]
        written = stock_desk._append_ledger(notes, "2026-08-10", tmp_path)
        assert [r["id"] for r in written] == ["2026-08-10-AAA-tok-1"]
        again = stock_desk._append_ledger(notes, "2026-08-10", tmp_path)
        assert again == [], "a re-append must register no second claim"

    def test_demand_ledger_registration_is_lane_gated(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        demand_ledger._register_claims([_demand_row()], set(), tmp_path)
        assert not _stored(tmp_path), "a discarded lane must not write claims"
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        demand_ledger._register_claims([_demand_row()], set(), tmp_path)
        assert len(_stored(tmp_path)) == 1

    def test_thematic_registration_is_lane_gated_and_us_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ca = _thematic_row("avoid", subject="Telecom", region="canada")
        lp = tmp_path / "theses.jsonl"
        lp.write_text(json.dumps(ca) + "\n")
        thematic_desk._register_claims(lp, [ca], tmp_path)
        assert not _stored(tmp_path), "the canada leg must never register"
        us = _thematic_row("overweight")
        lp.write_text("\n".join(json.dumps(r) for r in (ca, us)) + "\n")
        thematic_desk._register_claims(lp, [us], tmp_path)
        claims = _stored(tmp_path)
        assert len(claims) == 1
        assert claims[0]["scope"]["key"] == "SMH"


class TestGradabilityIsHonestlyReported:
    """R2 / DNR:KILL-OFFHORIZON-VERDICTS. `in_scope_horizons` returns the
    GRADE_HORIZONS (5,21,63) at or below horizon_d and falls back to the claim's
    own ruler only when horizon_d < 5 — so a claim is read at its DECLARED ruler
    only when horizon_d is exactly 5, 21 or 63. Wave 1's dominant horizons are
    20 (stock/thematic) and 126 (demand_chain), neither of which is in that set.
    This is a SUBSTRATE property, deliberately left unchanged by this wave; it is
    pinned here so the limitation cannot be forgotten or discovered at maturity.
    """

    def test_declared_ruler_is_not_in_scope_for_wave1_horizons(self):
        assert q.in_scope_horizons(20) == [5]
        assert 20 not in q.in_scope_horizons(20)
        assert q.in_scope_horizons(126) == [5, 21, 63]
        assert 126 not in q.in_scope_horizons(126)
        # the three horizons that DO grade at their own ruler
        for h in q.GRADE_HORIZONS:
            assert h in q.in_scope_horizons(h)
