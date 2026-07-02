"""Tests for engine/communique_diff.py — the Communiqué Diff engine (W4 B1, spec D9).

Covers:
  * phrase matching including VARIANT forms (适度宽松 ~ 适度宽松的货币政策)
  * APPEARED / DROPPED logic against a trailing window
  * COLD-START behavior (no prior window → no appeared/dropped, organ flagged)
  * LEAD_SHIFT on People's Daily front-page lead-domain change
  * salience-only qledger claim registration (direction=0, horizon 21, macro
    scope vs 510300.SS) + idempotency
  * qbus emit rows shape

All PURE / on fixtures; qledger writes are redirected to tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import communique_diff as cd  # noqa: E402
from engine import qledger  # noqa: E402


def _book():
    return cd.load_phrase_book()


def _row(organ, title, body, crawled, url="u", rank=-1):
    return {"organ": organ, "title": title, "body": body, "url": url,
            "_crawled_at": crawled, "seendate": crawled[:10], "layout_rank": rank}


# --------------------------------------------------------------------------- #
# phrase book + matching
# --------------------------------------------------------------------------- #
def test_phrase_book_loads_canonical_formulas():
    book = _book()
    zh = {r["zh"] for r in book}
    # the spec's named canonical formulas must all be present
    for formula in ("适度宽松", "房住不炒", "新质生产力", "反内卷",
                    "稳中求进", "超常规逆周期调节"):
        assert formula in zh, f"{formula} missing from phrase book"
    assert len(book) >= 40   # ~44-formula seed


def test_variant_form_maps_to_canonical():
    book = _book()
    # the variant 适度宽松的货币政策 must register as the CANONICAL 适度宽松
    hits = cd.phrases_in_text("央行实施适度宽松的货币政策", book)
    assert "适度宽松" in hits
    # a full property variant maps to 房住不炒
    hits2 = cd.phrases_in_text("坚持房子是用来住的不是用来炒的", book)
    assert "房住不炒" in hits2


def test_empty_text_matches_nothing():
    assert cd.phrases_in_text("", _book()) == set()
    assert cd.phrases_in_text("no chinese policy formula here", _book()) == set()


def test_phrase_meta_carries_polarity_and_review_status():
    meta = cd.phrase_meta(_book())
    assert meta["适度宽松"]["domain"] == "monetary"
    assert meta["适度宽松"]["polarity"] == 1
    # polarity is human-review PROVISIONAL until reviewed (spec §5)
    assert meta["房住不炒"]["review_status"] == "PROVISIONAL"


# --------------------------------------------------------------------------- #
# appeared / dropped
# --------------------------------------------------------------------------- #
def test_appeared_and_dropped_against_window():
    book = _book()
    today = [_row("pboc", "适度宽松", "实施适度宽松的货币政策", "2026-07-02T01:00:00")]
    prior = [_row("pboc", "稳健", "稳健的货币政策 房住不炒", "2026-06-20T01:00:00")]
    res = cd.compute_events(today + prior, "2026-07-02", book=book, window_days=30)
    kinds = {(e["kind"], e["phrase"]) for e in res["events"]}
    assert ("APPEARED", "适度宽松") in kinds        # newly present vs window
    assert ("DROPPED", "房住不炒") in kinds          # in window, absent today
    assert ("DROPPED", "稳健的货币政策") in kinds
    assert res["cold_start_organs"] == []


def test_appeared_event_carries_evidence_and_meta():
    book = _book()
    today = [_row("ndrc", "新质生产力", "发展新质生产力",
                  "2026-07-02T01:00:00", url="http://ndrc/x")]
    prior = [_row("ndrc", "旧文", "供给侧结构性改革", "2026-06-20T01:00:00")]
    res = cd.compute_events(today + prior, "2026-07-02", book=book)
    appeared = [e for e in res["events"] if e["kind"] == "APPEARED"]
    e = next(x for x in appeared if x["phrase"] == "新质生产力")
    assert e["organ"] == "ndrc"
    assert e["domain"] == "industrial"
    assert e["evidence_url"] == "http://ndrc/x"
    assert e["review_status"] == "PROVISIONAL"
    assert e["event_id"].startswith("cd_")


# --------------------------------------------------------------------------- #
# cold start
# --------------------------------------------------------------------------- #
def test_cold_start_emits_no_appear_drop_and_flags_organ():
    book = _book()
    # only a today document, NO prior window → cannot tell appeared from always-present
    today = [_row("pboc", "适度宽松", "实施适度宽松的货币政策", "2026-07-02T01:00:00")]
    res = cd.compute_events(today, "2026-07-02", book=book)
    assert res["counts"]["n_appeared"] == 0
    assert res["counts"]["n_dropped"] == 0
    assert "pboc" in res["cold_start_organs"]


def test_window_excludes_out_of_range_prior():
    book = _book()
    today = [_row("csrc", "反内卷", "综合整治内卷式竞争", "2026-07-02T01:00:00")]
    # prior doc is OUTSIDE the 30-day window → treated as no prior → cold start
    prior_old = [_row("csrc", "旧", "反内卷", "2026-01-01T01:00:00")]
    res = cd.compute_events(today + prior_old, "2026-07-02", book=book, window_days=30)
    assert "csrc" in res["cold_start_organs"]
    assert res["counts"]["n_appeared"] == 0


# --------------------------------------------------------------------------- #
# lead shift (People's Daily front-page prominence)
# --------------------------------------------------------------------------- #
def test_lead_shift_on_front_page_domain_change():
    book = _book()
    # prior day lead = tech (新质生产力 / 科技自立自强); today lead = property
    prior = [_row("peoples_daily", "科技自立自强 新质生产力", "", "2026-07-01T01:00:00",
                  url="a", rank=0)]
    today = [_row("peoples_daily", "房住不炒 保交楼", "", "2026-07-02T01:00:00",
                  url="b", rank=0)]
    res = cd.compute_events(prior + today, "2026-07-02", book=book)
    shifts = [e for e in res["events"] if e["kind"] == "LEAD_SHIFT"]
    assert len(shifts) == 1
    assert shifts[0]["from_domain"] in ("tech", "industrial")
    assert shifts[0]["to_domain"] == "property"


def test_no_lead_shift_when_domain_unchanged():
    book = _book()
    prior = [_row("peoples_daily", "适度宽松", "", "2026-07-01T01:00:00", url="a", rank=0)]
    today = [_row("peoples_daily", "降准降息", "", "2026-07-02T01:00:00", url="b", rank=0)]
    res = cd.compute_events(prior + today, "2026-07-02", book=book)
    # both lead items are monetary → no shift
    assert res["counts"]["n_lead_shift"] == 0


def test_lead_domain_reads_top_of_page():
    book = _book()
    rows = [_row("peoples_daily", "房住不炒", "", "2026-07-02T01:00:00", rank=0),
            _row("peoples_daily", "适度宽松", "", "2026-07-02T01:00:00", rank=1)]
    # rank 0 (front-page lead) is property, so that wins over the rank-1 monetary
    assert cd.lead_domain(rows, book) == "property"


# --------------------------------------------------------------------------- #
# qledger claim registration (salience-only) + qbus emit
# --------------------------------------------------------------------------- #
def test_register_claims_are_salience_only_macro(tmp_path):
    book = _book()
    today = [_row("pboc", "适度宽松", "实施适度宽松的货币政策", "2026-07-02T01:00:00")]
    prior = [_row("pboc", "稳健", "稳健的货币政策", "2026-06-20T01:00:00")]
    res = cd.compute_events(today + prior, "2026-07-02", book=book)
    n = cd.register_claims(res, root=tmp_path)
    assert n == res["counts"]["n_events"] > 0
    claims = qledger.load_claims(tmp_path)
    c = claims[0]
    assert c["desk"] == cd.DESK
    assert c["direction"] == 0                    # salience-only (polarity PROVISIONAL)
    assert c["horizon_d"] == cd.HORIZON_D == 21
    assert c["claim_family"] == cd.CLAIM_FAMILY
    assert c["scope"]["type"] == "macro"
    assert c["scope"]["key"] == "510300.SS"       # machine-checkable observable (D4)
    assert c["bench"] == "510300.SS"
    assert c["status"] == "open"                  # a valid macro claim, not rejected
    assert c["event_kind"] in ("APPEARED", "DROPPED")


def test_register_claims_idempotent(tmp_path):
    book = _book()
    today = [_row("ndrc", "反内卷", "综合整治内卷式竞争", "2026-07-02T01:00:00")]
    prior = [_row("ndrc", "旧", "供给侧结构性改革", "2026-06-20T01:00:00")]
    res = cd.compute_events(today + prior, "2026-07-02", book=book)
    cd.register_claims(res, root=tmp_path)
    n1 = len(qledger.load_claims(tmp_path))
    cd.register_claims(res, root=tmp_path)         # re-run
    n2 = len(qledger.load_claims(tmp_path))
    assert n1 == n2 and n1 > 0                      # dedupe by claim_id


def test_qbus_rows_shape():
    book = _book()
    today = [_row("pboc", "适度宽松", "实施适度宽松的货币政策", "2026-07-02T01:00:00")]
    prior = [_row("pboc", "稳健", "稳健的货币政策", "2026-06-20T01:00:00")]
    res = cd.compute_events(today + prior, "2026-07-02", book=book)
    rows = cd._to_qbus_rows(res, "2026-07-02T02:00:00")
    assert rows
    r = rows[0]
    assert r["desk"] == cd.DESK
    assert r["lang"] == "zh"
    assert r["source_tier"] == 1
    assert r["themes"] == ["policy"]
    assert r["timestamp_quality"] == "CRAWL_BOUNDED"


def test_no_events_when_corpus_empty():
    res = cd.compute_events([], "2026-07-02", book=_book())
    assert res["counts"]["n_events"] == 0
    assert res["events"] == []
