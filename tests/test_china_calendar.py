"""china_calendar — schema pin, source-class law, feed-beats-rule, degrade paths.

The calendar is an AGGREGATOR: it must not re-encode a release rule that
engine.china_event_calendar / engine.hk_event_calendar already own, and it must never
become rankable (RIC-R3). Both are pinned here, not just asserted in prose.

No network, no clock: every assertion runs against an injected `asof` and either the
committed stores or a synthetic parquet in tmp_path.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from engine import china_calendar as cal

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ASOF = date(2026, 7, 27)

_ENTRY_KEYS = {"date", "window_end", "etype", "label_en", "label_zh", "region",
               "impact", "source_class", "source", "approx"}
_PAYLOAD_KEYS = {"schema", "asof", "generated_at_utc", "horizon_days", "entries",
                 "data_gaps", "authority"}


@pytest.fixture(scope="module")
def payload(tmp_path_factory) -> dict:
    """The rule/static skeleton, assembled against EMPTY stores ON PURPOSE.

    Reading the LIVE data/china_omo + data/china_earnings stores here would make every
    schema assertion below a function of last night's collector run: the nightly
    advances those parquets, so a suite that passes today fails the week the PBoC
    announces an operation of a shape nobody anticipated — a failure that says nothing
    about the code under test. The feed leg has its own tests, each with a synthetic
    store it fully controls.
    """
    empty = tmp_path_factory.mktemp("china_calendar_no_stores")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cal, "omo_store_path", lambda: empty / "operations.parquet")
        mp.setattr(cal, "earnings_store_path", lambda: empty / "calendar.parquet")
        return cal.assemble_calendar(asof=_ASOF, horizon_days=45)


# --------------------------------------------------------------------------- #
# schema pin
# --------------------------------------------------------------------------- #
def test_payload_schema_and_authority_stamp(payload):
    assert set(payload) == _PAYLOAD_KEYS
    assert payload["schema"] == "china_calendar.v1"
    assert payload["asof"] == "2026-07-27" and payload["horizon_days"] == 45
    assert payload["generated_at_utc"].startswith("20")
    assert isinstance(payload["data_gaps"], list)
    # RIC-R3: the artifact declares itself unrankable on its face.
    assert payload["authority"] == {"tier": "context_only", "may_rank": False}


def test_every_entry_matches_the_v1_row_shape(payload):
    entries = payload["entries"]
    assert entries, "the aggregate calendar must never be empty with both engines live"
    for e in entries:
        assert set(e) == _ENTRY_KEYS, f"row shape drift: {sorted(set(e) ^ _ENTRY_KEYS)}"
        assert date.fromisoformat(e["date"])                       # ISO or raises
        if e["window_end"] is not None:
            assert date.fromisoformat(e["window_end"]) >= date.fromisoformat(e["date"])
        assert e["region"] in {"cn", "hk"}
        assert e["impact"] in {"high", "medium", "low"}
        assert e["source_class"] in {"rule", "feed", "static"}
        assert isinstance(e["approx"], bool)
        assert e["etype"] and e["source"]
        # bilingual law: a zh label that fell back to the EN string is a leak, and an
        # empty one is worse. Both sides must be non-empty AND actually different.
        assert e["label_en"].strip(), f"{e['etype']} has an empty EN label"
        assert e["label_zh"].strip(), f"{e['etype']} has an empty ZH label"
        assert e["label_zh"] != e["label_en"], f"{e['etype']} zh label leaks the EN text"


def test_entries_are_sorted_and_deduped(payload):
    sort_keys = [(e["date"], e["region"], e["etype"]) for e in payload["entries"]]
    assert sort_keys == sorted(sort_keys)
    # Uniqueness is on the FOUR-key (review F5): the label is part of the identity
    # because one feed etype legitimately carries several rows on one date (different
    # tenor/size). Two rows that agree on all four are the same row twice.
    keys = [(e["date"], e["region"], e["etype"], e["label_zh"])
            for e in payload["entries"]]
    assert len(keys) == len(set(keys)), "duplicate (date, region, etype, label_zh) rows"


def test_hk_engine_cn_reexports_are_not_shipped_twice(payload):
    """hk_macro_events re-exports the CN high-impact prints with a CN_ prefix; the
    aggregator drops them because the CN leg already emitted the same rows."""
    assert not [e for e in payload["entries"] if e["etype"].startswith("CN_")]
    cn_pmi = [e for e in payload["entries"] if e["etype"] == "PMI"]
    assert cn_pmi and all(e["region"] == "cn" for e in cn_pmi)


def test_both_engines_are_represented(payload):
    sources = {e["source"] for e in payload["entries"]}
    assert "engine.china_event_calendar" in sources
    assert "engine.hk_event_calendar" in sources


# --------------------------------------------------------------------------- #
# design law: aggregate, never re-encode
# --------------------------------------------------------------------------- #
def test_module_imports_the_rule_engines_instead_of_re_encoding_them():
    src = (_REPO_ROOT / "engine" / "china_calendar.py").read_text(encoding="utf-8")
    assert "from engine.china_event_calendar import china_macro_events" in src
    assert "from engine.hk_event_calendar import hk_macro_events" in src
    # a second CY release table here would silently diverge from the engines' own
    for banned in ("_SCHED_2026", "_HK_SCHED_2026", "last_day_of_month",
                   "nth_business_day"):
        assert banned not in src, f"{banned} re-encodes a rule the engines already own"


_RISK_STATE_GLOBS = ("risk_radar*.py", "risk_state*.py", "risk_sizing*.py",
                     "risk_brain*.py", "china_market_state*.py", "market_state*.py",
                     "*_gate*.py", "china_axes.py", "china_regime*.py",
                     "china_playbook.py", "china_radar*.py", "hk_axes.py",
                     "hk_regime*.py", "hk_playbook.py", "regime*.py",
                     "*_score.py", "*_scorer.py", "setup_tier.py",
                     "confluence_tiers.py")

_CAL_IMPORT_FORMS = ("from engine.china_calendar", "import engine.china_calendar",
                     "from engine import china_calendar",
                     'import_module("engine.china_calendar")',
                     "import_module('engine.china_calendar')")


def test_ric_r3_no_risk_or_state_module_imports_the_calendar():
    """RIC-R3, the OTHER direction: nothing that ranks, gates or sizes may READ this.

    The forward test below proves the calendar does not reach into the scored core.
    That is only half the rule — a calendar-gated risk leg is built by the risk module
    importing the calendar, which the forward test cannot see at all. This scan is the
    reverse direction, and it is deliberately cheap: file names in the risk/state
    family, four import spellings, no AST.
    """
    scanned: list[Path] = []
    offenders: list[str] = []
    for folder in ("engine", "scripts"):
        for pattern in _RISK_STATE_GLOBS:
            for path in sorted((_REPO_ROOT / folder).glob(pattern)):
                if path in scanned:
                    continue
                scanned.append(path)
                code = "\n".join(
                    ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if not ln.lstrip().startswith("#"))
                if any(form in code for form in _CAL_IMPORT_FORMS):
                    offenders.append(str(path.relative_to(_REPO_ROOT)))
    # a guard that scans nothing passes forever — pin the floor (count-guard law)
    assert len(scanned) >= 40, f"the risk/state scan went vacuous: {len(scanned)} files"
    assert any(p.name == "risk_radar.py" for p in scanned)
    assert any(p.name == "china_market_state.py" for p in scanned)
    assert not offenders, (
        "RIC-R3: these risk/state modules import engine.china_calendar — a calendar "
        f"row may never gate, size or dampen a channel: {offenders}")


def test_ric_r3_no_risk_or_state_channel_writers():
    """RIC-R3: a calendar row may never gate/size a risk or state channel. Neither the
    engine nor its builder may reach into those modules at all."""
    forbidden = ("risk_radar", "china_market_state", "china_axes", "china_regime",
                 "china_playbook", "hk_axes", "hk_regime", "hk_playbook",
                 "china_intel_bus", "china_policy_transmission")
    for rel in ("engine/china_calendar.py", "scripts/build_china_calendar.py"):
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        for name in forbidden:
            assert f"import {name}" not in code and f"from engine.{name}" not in code, \
                f"{rel} reaches into {name} — RIC-R3 forbids a calendar-gated channel"


# --------------------------------------------------------------------------- #
# static political rhythm (CNH-R12)
# --------------------------------------------------------------------------- #
def test_two_sessions_lands_in_a_february_horizon():
    p = cal.assemble_calendar(asof=date(2026, 2, 20), horizon_days=45)
    ts = [e for e in p["entries"] if e["etype"] == "two_sessions"]
    assert len(ts) == 1
    assert ts[0]["date"] == "2026-03-03" and ts[0]["window_end"] == "2026-03-12"
    assert ts[0]["source_class"] == "static" and ts[0]["approx"] is True
    assert ts[0]["region"] == "cn" and ts[0]["impact"] == "high"
    assert "两会" in ts[0]["label_zh"]


def test_politburo_july_window_is_live_on_a_july_asof():
    p = cal.assemble_calendar(asof=date(2026, 7, 1), horizon_days=45)
    pb = [e for e in p["entries"] if e["etype"] == "politburo_econ"]
    assert any(e["date"] == "2026-07-20" and e["window_end"] == "2026-07-31" for e in pb)
    assert all(e["approx"] is True and e["source_class"] == "static" for e in pb)


def test_window_already_open_is_still_shown():
    """A window we are INSIDE is the most decision-relevant row — start < asof must
    not filter it out."""
    p = cal.assemble_calendar(asof=date(2026, 7, 27), horizon_days=10)
    pb = [e for e in p["entries"] if e["etype"] == "politburo_econ"]
    assert [e["date"] for e in pb] == ["2026-07-20"]


def test_horizon_past_the_tabled_years_prints_a_gap():
    p = cal.assemble_calendar(asof=date(2027, 12, 20), horizon_days=45)
    assert any("political-window table covers" in g for g in p["data_gaps"])


def test_cewc_window_is_tabled_for_both_years():
    for year in (2026, 2027):
        p = cal.assemble_calendar(asof=date(year, 12, 1), horizon_days=30)
        cewc = [e for e in p["entries"] if e["etype"] == "cewc"]
        assert [e["date"] for e in cewc] == [f"{year}-12-10"]


# --------------------------------------------------------------------------- #
# feed leg — announced PBoC operations
# --------------------------------------------------------------------------- #
_OMO_COLUMNS = ["announce_date", "op_date", "bulletin_no", "column", "kind",
                "tenor_label", "tenor_days", "rate_pct", "amount_bn", "bid_bn",
                "awarded_bn", "maturity_date", "title", "url", "provenance",
                "first_seen", "fetched_at"]


def _omo_store(tmp_path: Path, rows: list[dict]) -> Path:
    import pandas as pd
    p = tmp_path / "operations.parquet"
    pd.DataFrame(rows).reindex(columns=_OMO_COLUMNS).to_parquet(p, index=False)
    return p


def _mlf_row(op_date: str = "2026-08-14") -> dict:
    return {"announce_date": "2026-08-13", "op_date": op_date, "bulletin_no": "",
            "column": "mlf", "kind": "mlf_tender", "tenor_label": "1年期",
            "tenor_days": 365, "rate_pct": float("nan"), "amount_bn": 5000.0,
            "maturity_date": "2027-08-14", "title": "中期借贷便利（MLF）开展情况",
            "url": "https://www.pbc.gov.cn/mlf/jul.html", "provenance": "pboc_bulletin"}


def test_feed_rows_carry_bilingual_amount_and_tenor(tmp_path, monkeypatch):
    store = _omo_store(tmp_path, [
        _mlf_row(),
        {"announce_date": "2026-07-24", "op_date": "2026-07-29", "bulletin_no": "2026-5",
         "column": "announcement", "kind": "reverse_repo_preannounce",
         "tenor_label": "隔夜", "tenor_days": 1, "rate_pct": float("nan"),
         "amount_bn": 6000.0, "maturity_date": None, "title": "公开市场业务公告[2026]第5号",
         "url": "https://www.pbc.gov.cn/ann/5.html", "provenance": "pboc_bulletin"},
        {"announce_date": "2026-07-14", "op_date": "2026-08-15", "bulletin_no": "",
         "column": "outright", "kind": "outright_repo_tender", "tenor_label": "6个月",
         "tenor_days": 184, "rate_pct": float("nan"), "amount_bn": 14000.0,
         "maturity_date": "2027-02-15", "title": "买断式逆回购", "url": "https://x/o.html",
         "provenance": "pboc_bulletin"},
        # a RESULT bulletin (kind=reverse_repo) is history, not a forward event
        {"announce_date": "2026-07-27", "op_date": "2026-07-27", "bulletin_no": "2026-143",
         "column": "trade", "kind": "reverse_repo", "tenor_label": "7天", "tenor_days": 7,
         "rate_pct": 1.40, "amount_bn": 3255.0, "url": "https://x/143.html",
         "provenance": "pboc_bulletin"},
    ])
    monkeypatch.setattr(cal, "omo_store_path", lambda: store)
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    feed = {e["etype"]: e for e in p["entries"] if e["source_class"] == "feed"}

    mlf = feed["omo_mlf_tender"]
    # A MATURITY IS NOT A WINDOW (review F15): a 1-year tender is a one-day event whose
    # money returns in a year. window_end=2027-08-14 painted a 365-day band across the
    # calendar; the maturity now reads as the fact it is, in the labels.
    assert mlf["date"] == "2026-08-14" and mlf["window_end"] is None
    assert "matures 2027-08-14" in mlf["label_en"]
    assert "到期 2027-08-14" in mlf["label_zh"]
    assert mlf["source"] == "china_omo.operations" and mlf["approx"] is False
    assert "1年期" in mlf["label_zh"] and "5,000亿元" in mlf["label_zh"]
    assert "RMB 500bn" in mlf["label_en"] and "MLF" in mlf["label_en"]
    assert mlf["impact"] == "high" and mlf["region"] == "cn"

    ann = feed["omo_reverse_repo_preannounce"]
    assert ann["date"] == "2026-07-29" and ann["window_end"] is None
    assert "隔夜" in ann["label_zh"] and "6,000亿元" in ann["label_zh"]
    # 量价分离: no rate was published, so no rate appears in either label
    assert "%" not in ann["label_en"] and "利率" not in ann["label_zh"]

    out = feed["omo_outright_repo_tender"]
    assert out["date"] == "2026-08-15" and "RMB 1,400bn" in out["label_en"]
    assert out["window_end"] is None and "matures 2027-02-15" in out["label_en"]

    # a settled result bulletin is NOT a forward calendar row
    assert "omo_reverse_repo" not in feed


def test_feed_mlf_suppresses_the_rule_row(tmp_path, monkeypatch):
    """Announced beats guessed — the ~15th arithmetic MLF row must disappear when the
    PBoC has published the tender, and the payload must say why.

    The "before" leg runs against an EMPTY store (review F7): read from the live
    data/china_omo tape it was a dated time bomb — the nightly appends real tenders, so
    the day the PBoC announced an August MLF this assertion would fail while nothing in
    the code had changed. An empty store is the only baseline that means "no feed row".
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(cal, "omo_store_path", lambda: empty / "operations.parquet")
    before = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert [e["date"] for e in before["entries"] if e["etype"] == "MLF"] == ["2026-08-17"]

    monkeypatch.setattr(cal, "omo_store_path", lambda: _omo_store(tmp_path, [_mlf_row()]))
    after = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert not [e for e in after["entries"] if e["etype"] == "MLF"]
    assert [e["date"] for e in after["entries"] if e["etype"] == "omo_mlf_tender"] \
        == ["2026-08-14"]
    assert any("MLF rule row 2026-08-17 suppressed" in g for g in after["data_gaps"])


def test_mlf_suppression_is_scoped_to_the_matching_operation(tmp_path, monkeypatch):
    """The suppression is a SAME-MONTH test, not a blanket kill of the MLF rule: a
    September tender takes out September's guessed row and leaves August's."""
    monkeypatch.setattr(cal, "omo_store_path",
                        lambda: _omo_store(tmp_path, [_mlf_row("2026-09-05")]))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=60)
    ruled = [e["date"] for e in p["entries"] if e["etype"] == "MLF"]
    assert ruled == ["2026-08-17"]                      # Aug survives (nothing announced)
    assert any("MLF rule row 2026-09-15 suppressed" in g for g in p["data_gaps"])
    assert not any("2026-08-17 suppressed" in g for g in p["data_gaps"])


def test_a_late_month_tender_still_suppresses_the_mid_month_guess(tmp_path, monkeypatch):
    """REVIEW F4 — the old +/-10-day window failed on the CADENCE THAT ACTUALLY RUNS.

    MLF is monthly: one tender per calendar month. The engine guesses the 15th; the
    observed 2026 tenders have landed on the 24th-26th. A 26th-vs-15th pair is 11 days
    apart, i.e. just outside the old +/-10d test, so the reader was shown the ANNOUNCED
    tender and a phantom rule row for the very same monthly operation.
    """
    feed_day = date(2026, 9, 26)
    rule_day = date(2026, 9, 15)
    assert abs((feed_day - rule_day).days) > 10, "the old window would have kept both"

    monkeypatch.setattr(cal, "omo_store_path",
                        lambda: _omo_store(tmp_path, [_mlf_row(feed_day.isoformat())]))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=75)
    september = [e for e in p["entries"]
                 if e["date"].startswith("2026-09") and "MLF" in e["etype"].upper()]
    assert [(e["date"], e["source_class"]) for e in september] == [("2026-09-26", "feed")]
    assert any("MLF rule row 2026-09-15 suppressed" in g for g in p["data_gaps"])
    # August, which nothing announced, keeps its honest guess
    assert [e["date"] for e in p["entries"] if e["etype"] == "MLF"] == ["2026-08-17"]


def test_same_day_multi_tenor_feed_rows_both_survive_dedup(tmp_path, monkeypatch):
    """REVIEW F5 — two operations announced for the SAME DAY are two rows.

    The PBoC routinely pre-announces different tenors/sizes for one date, and both
    carried etype 'omo_reverse_repo_preannounce'. On the old (date, etype, region) key
    the second collapsed into the first: the larger operation deleted outright, with
    nothing in data_gaps to say a row had been dropped.
    """
    monkeypatch.setattr(cal, "omo_store_path", lambda: _omo_store(tmp_path, [
        {"announce_date": "2026-07-27", "op_date": "2026-08-03", "bulletin_no": "2026-6",
         "column": "announcement", "kind": "reverse_repo_preannounce",
         "tenor_label": "隔夜", "tenor_days": 1, "rate_pct": float("nan"),
         "amount_bn": 3000.0, "title": "公开市场业务公告［2026］第6号",
         "url": "https://www.pbc.gov.cn/ann/6.html", "provenance": "pboc_bulletin"},
        {"announce_date": "2026-07-27", "op_date": "2026-08-03", "bulletin_no": "2026-6",
         "column": "announcement", "kind": "reverse_repo_preannounce",
         "tenor_label": "14天", "tenor_days": 14, "rate_pct": float("nan"),
         "amount_bn": 8000.0, "title": "公开市场业务公告［2026］第6号",
         "url": "https://www.pbc.gov.cn/ann/6.html", "provenance": "pboc_bulletin"},
    ]))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    same_day = [e for e in p["entries"]
                if e["etype"] == "omo_reverse_repo_preannounce" and e["date"] == "2026-08-03"]
    assert len(same_day) == 2, "a same-day multi-tenor announcement lost a leg"
    # both the tenor and the size survive — the old key kept whichever arrived first
    assert sorted(e["label_zh"] for e in same_day) == sorted([
        "央行逆回购操作（预告）：隔夜，3,000亿元",
        "央行逆回购操作（预告）：14天，8,000亿元"])
    # and the 3-key the review flagged really would have collapsed them
    assert len({(e["date"], e["etype"], e["region"]) for e in same_day}) == 1


def test_rule_and_static_rows_still_collapse_on_the_four_key(tmp_path, monkeypatch):
    """The F5 key extension must not un-dedup the rows dedup exists for: a rule row the
    feed already announces, and the HK engine's CN re-exports."""
    monkeypatch.setattr(cal, "omo_store_path", lambda: _omo_store(tmp_path, [_mlf_row()]))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    keys = [(e["date"], e["region"], e["etype"], e["source_class"])
            for e in p["entries"] if e["source_class"] in ("rule", "static")]
    assert len(keys) == len(set(keys)), "rule/static rows duplicated"
    assert not [e for e in p["entries"] if e["etype"].startswith("CN_")]


def test_out_of_horizon_and_past_operations_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "omo_store_path", lambda: _omo_store(tmp_path, [
        _mlf_row("2026-07-15"),     # before asof
        _mlf_row("2027-01-15"),     # past the horizon
    ]))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert not [e for e in p["entries"] if e["source_class"] == "feed"
                and e["etype"].startswith("omo_")]
    assert any("no announced operation inside the horizon" in g for g in p["data_gaps"])


def test_amount_labels_keep_the_native_unit_and_convert_honestly():
    assert cal._amount_labels(3255) == ("RMB 325.5bn", "3,255亿元")
    assert cal._amount_labels(5000) == ("RMB 500bn", "5,000亿元")
    assert cal._amount_labels(float("nan")) == ("", "")
    assert cal._amount_labels(None) == ("", "") and cal._amount_labels("") == ("", "")
    assert cal._rate_labels(1.4) == ("at 1.40%", "利率1.40%")
    assert cal._rate_labels(float("nan")) == ("", "")


# --------------------------------------------------------------------------- #
# feed leg — A-share reporting season
# --------------------------------------------------------------------------- #
def _earnings_store(tmp_path: Path, rows: list[dict]) -> Path:
    import pandas as pd
    p = tmp_path / "calendar.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def test_earnings_window_needs_a_dense_month(tmp_path, monkeypatch):
    rows = [{"ticker": f"{i:06d}.SZ", "next_date": "2026-08-20", "last_date": "",
             "period": "20260630", "asof": "2026-07-27"} for i in range(60)]
    rows += [{"ticker": f"9{i:05d}.SS", "next_date": "2026-09-04", "last_date": "",
              "period": "20260630", "asof": "2026-07-27"} for i in range(10)]
    rows[0]["next_date"] = "2026-08-01"      # window start
    rows[59]["next_date"] = "2026-08-31"     # window end
    monkeypatch.setattr(cal, "earnings_store_path", lambda: _earnings_store(tmp_path, rows))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    seasons = [e for e in p["entries"] if e["etype"] == "earnings_season"]
    # August = 60/70 (86%) clears the gate; September = 10/70 (14%) does not
    assert len(seasons) == 1
    s = seasons[0]
    assert s["date"] == "2026-08-01" and s["window_end"] == "2026-08-31"
    assert s["source_class"] == "feed" and s["source"] == "china_earnings.calendar"
    assert s["impact"] == "high" and s["region"] == "cn" and s["approx"] is False
    assert "86%" in s["label_en"] and "86%" in s["label_zh"]
    assert "interim results" in s["label_en"] and "中报" in s["label_zh"]


def test_mid_season_share_is_the_months_fact_not_a_horizon_slice(tmp_path, monkeypatch):
    """REVIEW F6 — the label states a MONTH fact, so the arithmetic must be the month's.

    99 of 100 covered names report in August. Clipping the numerator to [asof, end]
    made the same August read 99% on the 1st and 70% on the 25th — a number the label
    presents as "% of the covered board reports in 2026-08" — and DEMOTED impact from
    high to medium as the clipped share fell through 50%, i.e. the season looked calmer
    the deeper into it we got.
    """
    rows = [{"ticker": f"{i:06d}.SZ", "next_date": f"2026-08-{1 + i % 20:02d}",
             "last_date": "", "period": "20260630", "asof": "2026-08-25"}
            for i in range(29)]                                   # 8-01..8-20, all PAST asof
    rows += [{"ticker": f"1{i:05d}.SZ", "next_date": f"2026-08-{26 + i % 6:02d}",
              "last_date": "", "period": "20260630", "asof": "2026-08-25"}
             for i in range(70)]                                  # 8-26..8-31, still ahead
    rows += [{"ticker": "600000.SS", "next_date": "2026-09-10", "last_date": "",
              "period": "20260630", "asof": "2026-08-25"}]
    monkeypatch.setattr(cal, "earnings_store_path", lambda: _earnings_store(tmp_path, rows))
    p = cal.assemble_calendar(asof=date(2026, 8, 25), horizon_days=45)
    seasons = [e for e in p["entries"] if e["etype"] == "earnings_season"]
    assert len(seasons) == 1
    s = seasons[0]
    assert "99%" in s["label_en"] and "99%" in s["label_zh"]     # the month's own fact
    assert "70%" not in s["label_en"]                            # not the horizon slice
    assert s["impact"] == "high"                                 # no mid-season demotion
    # the window is the month's; the entry date is clamped forward to today
    assert s["date"] == "2026-08-25" and s["window_end"] == "2026-08-31"


def test_a_finished_season_is_not_a_forward_row(tmp_path, monkeypatch):
    """The horizon still decides WHETHER a window ships: a month whose last report is
    behind us is history, not a forward calendar row."""
    rows = [{"ticker": f"{i:06d}.SZ", "next_date": "2026-08-05", "last_date": "",
             "period": "20260630", "asof": "2026-08-25"} for i in range(80)]
    monkeypatch.setattr(cal, "earnings_store_path", lambda: _earnings_store(tmp_path, rows))
    p = cal.assemble_calendar(asof=date(2026, 8, 25), horizon_days=45)
    assert not [e for e in p["entries"] if e["etype"] == "earnings_season"]


def test_sparse_calendar_reports_the_density_gap(tmp_path, monkeypatch):
    rows = [{"ticker": f"{i:06d}.SZ", "next_date": "2026-08-20" if i < 5 else "2027-04-01",
             "last_date": "", "period": "20260630", "asof": "2026-07-27"}
            for i in range(100)]
    monkeypatch.setattr(cal, "earnings_store_path", lambda: _earnings_store(tmp_path, rows))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert not [e for e in p["entries"] if e["etype"] == "earnings_season"]
    assert any("20% reporting-density gate" in g for g in p["data_gaps"])


# --------------------------------------------------------------------------- #
# degrade paths — a missing or corrupt store is a gap, never an exception
# --------------------------------------------------------------------------- #
def test_absent_stores_degrade_to_named_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "omo_store_path", lambda: tmp_path / "nope.parquet")
    monkeypatch.setattr(cal, "earnings_store_path", lambda: tmp_path / "nope2.parquet")
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert p["entries"], "the rule/static legs must survive a missing store"
    assert any("china_omo store unavailable" in g for g in p["data_gaps"])
    assert any("china_earnings store unavailable" in g for g in p["data_gaps"])
    assert not [e for e in p["entries"] if e["source_class"] == "feed"]


def test_unreadable_stores_degrade_to_named_gaps(tmp_path, monkeypatch):
    bad_omo = tmp_path / "operations.parquet"
    bad_omo.write_bytes(b"PAR1 not actually a parquet file")
    bad_earn = tmp_path / "calendar.parquet"
    bad_earn.write_bytes(b"PAR1 garbage")
    monkeypatch.setattr(cal, "omo_store_path", lambda: bad_omo)
    monkeypatch.setattr(cal, "earnings_store_path", lambda: bad_earn)
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert any("UNREADABLE" in g for g in p["data_gaps"])
    assert len([g for g in p["data_gaps"] if "UNREADABLE" in g]) == 2
    assert p["entries"]


def test_schema_drift_in_the_omo_store_degrades(tmp_path, monkeypatch):
    import pandas as pd
    p = tmp_path / "operations.parquet"
    pd.DataFrame([{"unexpected": 1}]).to_parquet(p, index=False)
    monkeypatch.setattr(cal, "omo_store_path", lambda: p)
    out = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert any("schema drift" in g for g in out["data_gaps"])


def test_dead_engine_degrades_to_a_gap(monkeypatch):
    import engine.china_event_calendar as cec
    monkeypatch.setattr(cec, "china_macro_events",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    p = cal.assemble_calendar(asof=_ASOF, horizon_days=45)
    assert any("engine.china_event_calendar unavailable" in g for g in p["data_gaps"])
    assert p["entries"], "the HK leg must still ship when the CN engine dies"


# --------------------------------------------------------------------------- #
# builder
# --------------------------------------------------------------------------- #
def test_builder_writes_atomically_and_exits_zero(tmp_path, monkeypatch, capsys):
    from scripts import build_china_calendar as b
    out = tmp_path / "chinastatedata" / "calendar.json"
    monkeypatch.setattr(b, "OUT_PATH", out)
    rc = b.main(["--asof", "2026-07-27", "--horizon-days", "45", "--check"])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == _PAYLOAD_KEYS and payload["asof"] == "2026-07-27"
    assert payload["authority"]["may_rank"] is False
    # tmp sibling cleaned up by os.replace — a *.tmp left behind means a non-atomic write
    assert not list(out.parent.glob("*.tmp"))
    printed = capsys.readouterr().out
    assert "china_calendar.v1" in printed and "entries=" in printed


def test_builder_rejects_a_bad_asof(tmp_path, monkeypatch):
    from scripts import build_china_calendar as b
    monkeypatch.setattr(b, "OUT_PATH", tmp_path / "calendar.json")
    assert b.main(["--asof", "27-07-2026"]) == 2
    assert not (tmp_path / "calendar.json").exists()


def test_builder_survives_a_total_assembly_failure(tmp_path, monkeypatch):
    """Exit 0 on degrade: an empty calendar with an honest gap beats a red asia lane."""
    from scripts import build_china_calendar as b
    out = tmp_path / "calendar.json"
    monkeypatch.setattr(b, "OUT_PATH", out)
    monkeypatch.setattr(cal, "resolve_asof",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert b.main([]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["entries"] == [] and payload["data_gaps"]
    assert payload["authority"] == {"tier": "context_only", "may_rank": False}
