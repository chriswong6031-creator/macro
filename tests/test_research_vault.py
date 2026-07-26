"""Tests for the Research Vault ingestion spine (RV W1).

Covers:
  - sidecar normalization + id derivation + EVERY fallback (missing/blank/bad-JSON);
  - catalog upsert ordering (newest-first) + institutions rollup + idempotent replace;
  - corpus FTS5 build + a body-only search (proves BODY is searchable) + facet filter;
  - ingest end-to-end via the LOCAL store with tiny fixture PDFs — idempotency
    (second run ingests 0), receipt written, needs_metadata path, top-picks prefix;
  - the PUBLIC first-pages excerpt (engine/research_vault/excerpt.py): page-window
    + sparse-cover behaviour, email/URL cleaning, the char cap, and the repo
    snapshot's refuse-empty + deterministic (churn-free) serialization.

No R2 needed: the LocalStore backend + a monkeypatched pdftotext extractor keep the
whole suite offline. stdlib + pytest only.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from engine.research_vault import catalog as catalog_mod
from engine.research_vault import corpus as corpus_mod
from engine.research_vault import excerpt as excerpt_mod
from engine.research_vault import ingest as ingest_mod
from engine.research_vault import sidecar as sidecar_mod
from engine.research_vault import title as title_mod
from engine.research_vault.r2_store import LocalStore, build_store


# ===========================================================================
# sidecar: id derivation
# ===========================================================================

def test_derive_id_basic():
    got = sidecar_mod.derive_id(
        "Bernstein", "2026-07-21T14:00:00Z",
        "Data Center Pipeline Probabilities — Separating credible developers")
    assert got.startswith("bernstein-2026-07-21-")
    # title slug truncated to <=40 chars
    ttl = got[len("bernstein-2026-07-21-"):]
    assert len(ttl) <= 40
    assert got == got.lower()
    assert " " not in got


def test_derive_id_accents_folded():
    got = sidecar_mod.derive_id("Société Générale", "2026-01-02", "Café Résumé")
    assert got == "societe-generale-2026-01-02-cafe-resume"


def test_derive_id_missing_parts_degrade():
    assert sidecar_mod.derive_id("", "", "") == "unknown-undated-untitled"
    assert sidecar_mod.derive_id("GS", "not-a-date", "T").startswith("gs-undated-")


def test_slug_empty_and_punctuation():
    assert sidecar_mod.slug("") == ""
    assert sidecar_mod.slug("!!!") == ""
    assert sidecar_mod.slug("Hello, World!") == "hello-world"


# ===========================================================================
# sidecar: normalization + fallbacks
# ===========================================================================

def test_normalize_full_valid_sidecar():
    sc = {
        "schema": "research_vault.sidecar.v1",
        "id": "bernstein-2026-07-21-dc-pipeline",
        "title": "DC Pipeline",
        "institution": "Bernstein",
        "side": "sell",
        "published_at": "2026-07-21T14:00:00Z",
        "summary_points": ["a", "b", "c"],
        "tags": ["ai", "datacenters"],
        "tickers": ["eqix", "dlr"],
        "top_pick": True,
        "pages": 12,
        "language": "en",
        "source_filename": "bernstein_dc_pipeline.pdf",
        "unknown_field": "ignored",
    }
    item = sidecar_mod.normalize(sc)
    assert item["id"] == "bernstein-2026-07-21-dc-pipeline"
    assert item["title"] == "DC Pipeline"
    assert item["institution"] == "Bernstein"
    assert item["side"] == "sell"
    assert item["tickers"] == ["EQIX", "DLR"]  # upper-cased
    assert item["top_pick"] is True
    assert item["pages"] == 12
    assert item["needs_metadata"] is False
    assert "unknown_field" not in item  # unknown fields not carried on public item


def test_normalize_missing_title_falls_back_to_pdf_then_filename():
    # No sidecar title → PDF-embedded title.
    item = sidecar_mod.normalize(
        {"institution": "GS", "published_at": "2026-07-01"},
        fallback_title_pdf="Embedded Title", fallback_title_filename="the_file")
    assert item["title"] == "Embedded Title"
    assert item["needs_metadata"] is True  # fell back → flagged

    # No sidecar title, no embedded title → filename.
    item2 = sidecar_mod.normalize(
        {"institution": "GS", "published_at": "2026-07-01"},
        fallback_title_filename="the_file")
    assert item2["title"] == "the_file"
    assert item2["needs_metadata"] is True


def test_normalize_recovers_truncated_title_from_pdf():
    # MarketDesk dropped the Reuters ".US)" suffix → unbalanced "(". A fuller,
    # balanced PDF /Title is preferred (and the recovery is transparent — the
    # sidecar DID supply a title, so needs_metadata is NOT raised).
    item = sidecar_mod.normalize(
        {"title": "Alcon Inc. (ALCC", "institution": "GS", "published_at": "2026-07-01"},
        fallback_title_pdf="Alcon Inc. (ALCC.US) - Q2 Results")
    assert item["title"] == "Alcon Inc. (ALCC.US) - Q2 Results"
    assert item["needs_metadata"] is False


def test_normalize_repairs_truncated_title_when_pdf_not_better():
    # PDF title absent, itself truncated, or shorter → no fuller name to recover,
    # so the dangling "(" is CLOSED rather than published unbalanced. The exchange
    # suffix stays unknown — we never invent ".PA".
    base = {"title": "Carrefour (CARR", "institution": "GS"}
    assert sidecar_mod.normalize(base)["title"] == "Carrefour (CARR)"                       # no pdf
    assert sidecar_mod.normalize(base, fallback_title_pdf="Carrefour (CAR")["title"] == "Carrefour (CARR)"  # pdf also truncated
    assert sidecar_mod.normalize(base, fallback_title_pdf="Carr")["title"] == "Carrefour (CARR)"            # pdf shorter


def test_normalize_strips_download_dedupe_suffix():
    # "Carrefour (CARR(1)" = a truncated parenthetical PLUS the save-as dedupe
    # marker the desk's second download added. Both go.
    item = sidecar_mod.normalize({"title": "Carrefour (CARR(1)", "institution": "GS"})
    assert item["title"] == "Carrefour (CARR)"
    # ... and on an otherwise-clean title too.
    assert sidecar_mod.normalize(
        {"title": "China 2026 Outlook (1)", "institution": "GS"})["title"] == "China 2026 Outlook"


# ===========================================================================
# sidecar: clean_title (the public-surface title repair)
# ===========================================================================

@pytest.mark.parametrize("raw,want", [
    # the five production defects (data/research_vault/catalog.json, 2026-07-26)
    ("Carrefour (CARR", "Carrefour (CARR)"),
    ("SAP (SAPG", "SAP (SAPG)"),
    ("Alcon Inc. (ALCC", "Alcon Inc. (ALCC)"),
    ("Carrefour (CARR(1)", "Carrefour (CARR)"),
    ("Repsol (REP", "Repsol (REP)"),
    # dedupe marker on a balanced title
    ("South Africa SARB Keeps Policy Rate on Hold(1)", "South Africa SARB Keeps Policy Rate on Hold"),
    ("Report (final)(1)", "Report (final)"),
    # a fragment with nothing in it is dropped, not closed with "()"
    ("Morning Briefing (", "Morning Briefing"),
    # unmatched closer is stripped
    ("Morning Briefing)", "Morning Briefing"),
    # nested truncation still balances
    ("A (B (C", "A (B (C))"),
    # already-good titles are untouched
    ("JPM US Market Intel | Morning Briefing", "JPM US Market Intel | Morning Briefing"),
    ("Allianz SE (ALVG.DE) announced acquisition", "Allianz SE (ALVG.DE) announced acquisition"),
    # a 4-digit year parenthetical is NOT a dedupe marker
    ("Global Outlook (2027)", "Global Outlook (2027)"),
    # whitespace collapse + empties
    ("  spaced   out  ", "spaced out"),
    ("(", ""),
    ("", ""),
])
def test_clean_title_cases(raw, want):
    assert sidecar_mod.clean_title(raw) == want


def test_clean_title_is_idempotent():
    for raw in ("Carrefour (CARR(1)", "Alcon Inc. (ALCC", "A (B (C", "Morning Briefing ("):
        once = sidecar_mod.clean_title(raw)
        assert sidecar_mod.clean_title(once) == once


def test_clean_title_never_raises_on_junk():
    for junk in (None, 123, ["x"], {"a": 1}):
        assert isinstance(sidecar_mod.clean_title(junk), str)


def test_clean_title_is_slug_stable_for_paren_repair():
    """The repair must never move an already-indexed /research/ URL.

    Closing a dangling "(" only adds punctuation, and the slug strips
    non-alphanumerics — so the published page keeps its exact filename.
    """
    for raw in ("Alcon Inc. (ALCC", "SAP (SAPG", "Repsol (REP"):
        assert sidecar_mod.slug(sidecar_mod.clean_title(raw)) == sidecar_mod.slug(raw)


def test_normalize_good_title_never_touched_by_pdf():
    # A balanced sidecar title is never replaced, even if a PDF title exists.
    item = sidecar_mod.normalize(
        {"title": "Datacenter demand inflecting", "institution": "GS"},
        fallback_title_pdf="Microsoft Word - template.docx")
    assert item["title"] == "Datacenter demand inflecting"


def test_normalize_missing_title_all_the_way_to_placeholder():
    item = sidecar_mod.normalize({"institution": "GS"})
    assert item["title"] == "Untitled research"
    assert item["needs_metadata"] is True


def test_normalize_missing_institution_flags_needs_metadata():
    item = sidecar_mod.normalize({"title": "T", "published_at": "2026-07-01"})
    assert item["institution"] == "Unknown"
    assert item["needs_metadata"] is True


def test_normalize_blank_institution_uses_caller_fallback():
    item = sidecar_mod.normalize(
        {"title": "T", "institution": "   "},
        fallback_institution="Morgan Stanley")
    assert item["institution"] == "Morgan Stanley"


def test_normalize_missing_published_at_uses_upload_time_fallback():
    item = sidecar_mod.normalize(
        {"title": "T", "institution": "GS"},
        fallback_published_at="2026-07-22T09:00:00Z")
    assert item["published_at"] == "2026-07-22T09:00:00Z"


def test_normalize_invalid_side_defaults_sell():
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "side": "wat"})["side"] == "sell"
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "side": "buy"})["side"] == "buy"
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "side": "independent"})["side"] == "independent"


def test_normalize_missing_summary_is_empty_list():
    item = sidecar_mod.normalize({"title": "T", "institution": "GS"})
    assert item["summary_points"] == []


def test_normalize_summary_clamped_to_eight():
    pts = [f"p{i}" for i in range(20)]
    item = sidecar_mod.normalize({"title": "T", "institution": "GS", "summary_points": pts})
    assert len(item["summary_points"]) == 8


def test_normalize_id_derived_when_absent():
    item = sidecar_mod.normalize(
        {"title": "My Report", "institution": "Bernstein", "published_at": "2026-07-21"})
    assert item["id"] == "bernstein-2026-07-21-my-report"


def test_normalize_explicit_id_is_slugged():
    # A provided id is always slugged for url-safety (underscores/spaces → '-').
    item = sidecar_mod.normalize(
        {"id": "Bernstein DC_Report!", "title": "T", "institution": "GS"})
    assert item["id"] == "bernstein-dc-report"


def test_normalize_pages_type_safety():
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "pages": "12"})["pages"] == 12
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "pages": "x"})["pages"] is None
    assert sidecar_mod.normalize({"title": "T", "institution": "GS", "pages": True})["pages"] is None


def test_parse_json_bad_json_flags_and_falls_back():
    sc, bad = sidecar_mod.parse_json(b"{ not valid json ]")
    assert bad is True
    assert sc == {}
    item = sidecar_mod.normalize(sc, bad_json=bad,
                                 fallback_title_filename="orphan",
                                 fallback_institution="",
                                 fallback_published_at="2026-07-22T00:00:00Z")
    assert item["needs_metadata"] is True
    assert item["title"] == "orphan"
    assert item["institution"] == "Unknown"


def test_parse_json_absent_is_not_an_error():
    sc, bad = sidecar_mod.parse_json(None)
    assert bad is False and sc == {}
    sc2, bad2 = sidecar_mod.parse_json(b"")
    assert bad2 is False and sc2 == {}


def test_parse_json_non_dict_is_bad():
    sc, bad = sidecar_mod.parse_json(b"[1, 2, 3]")
    assert bad is True and sc == {}


def test_from_bytes_end_to_end_bad_json():
    item = sidecar_mod.from_bytes(
        b"{bad",
        fallback_title_filename="f", fallback_published_at="2026-07-22T00:00:00Z")
    assert item["needs_metadata"] is True
    assert item["title"] == "f"


# ===========================================================================
# catalog: ordering + rollup + idempotency
# ===========================================================================

def _item(id_, inst, date, top=False):
    return sidecar_mod.normalize(
        {"id": id_, "title": id_, "institution": inst, "published_at": date,
         "top_pick": top})


def test_catalog_upsert_orders_newest_first():
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item("a", "GS", "2026-07-01"))
    catalog_mod.upsert_item(cat, _item("b", "GS", "2026-07-20"))
    catalog_mod.upsert_item(cat, _item("c", "GS", "2026-07-10"))
    order = [it["id"] for it in cat["items"]]
    assert order == ["b", "c", "a"]  # newest-first
    assert cat["count"] == 3


def test_catalog_institutions_rollup_sorted_unique():
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item("a", "Goldman Sachs", "2026-07-01"))
    catalog_mod.upsert_item(cat, _item("b", "Bernstein", "2026-07-02"))
    catalog_mod.upsert_item(cat, _item("c", "Bernstein", "2026-07-03"))
    assert cat["institutions"] == ["Bernstein", "Goldman Sachs"]


def test_catalog_upsert_is_idempotent_by_id():
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item("dup", "GS", "2026-07-01"))
    catalog_mod.upsert_item(cat, _item("dup", "GS", "2026-07-05"))  # same id, newer date
    assert cat["count"] == 1
    assert cat["items"][0]["published_at"] == "2026-07-05"


def test_catalog_item_has_no_body_field():
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item("a", "GS", "2026-07-01"))
    assert "body" not in cat["items"][0]


def test_catalog_load_write_roundtrip_local_store(tmp_path):
    store = LocalStore(tmp_path / "store")
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item("a", "GS", "2026-07-01", top=True))
    data = catalog_mod.write(store, cat)
    assert store.exists(catalog_mod.CATALOG_KEY)
    reloaded = catalog_mod.load(store)
    assert reloaded["count"] == 1
    assert reloaded["items"][0]["top_pick"] is True
    assert reloaded["schema"] == "research_vault.catalog.v1"
    assert reloaded["generated_at"]  # stamped
    # bytes are valid JSON with trailing newline
    assert data.endswith(b"\n")
    json.loads(data)


def test_catalog_load_corrupt_degrades_to_empty(tmp_path):
    store = LocalStore(tmp_path / "store")
    store.put_bytes(catalog_mod.CATALOG_KEY, b"{ corrupt", "application/json")
    cat = catalog_mod.load(store)
    assert cat == catalog_mod.empty()


def test_catalog_upsert_cleans_the_title():
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, dict(_item("a", "GS", "2026-07-01"), title="Alcon Inc. (ALCC"))
    assert cat["items"][0]["title"] == "Alcon Inc. (ALCC)"


def test_catalog_load_heals_already_published_titles(tmp_path):
    """The heal that reaches docs ingest can no longer touch.

    Ingest is receipt-idempotent, so a report already in the vault NEVER
    re-normalizes — every doc ingested before the sidecar fix would keep its
    truncated title forever. Repairing on load means the next hourly run
    republishes them fixed, with no receipt surgery and no re-download.
    """
    store = LocalStore(tmp_path / "store")
    store.put_bytes(catalog_mod.CATALOG_KEY, json.dumps({
        "schema": "research_vault.catalog.v1", "generated_at": "", "count": 3,
        "institutions": ["Goldman Sachs"],
        "items": [
            {"id": "md-1", "title": "Alcon Inc. (ALCC", "institution": "Goldman Sachs"},
            {"id": "md-2", "title": "Carrefour (CARR(1)", "institution": "Goldman Sachs"},
            {"id": "md-3", "title": "Fine As-Is (FOO.PA)", "institution": "Goldman Sachs"},
        ],
    }).encode("utf-8"), "application/json")

    cat = catalog_mod.load(store)
    titles = {it["id"]: it["title"] for it in cat["items"]}
    assert titles["md-1"] == "Alcon Inc. (ALCC)"
    assert titles["md-2"] == "Carrefour (CARR)"
    assert titles["md-3"] == "Fine As-Is (FOO.PA)"      # untouched
    assert [it["id"] for it in cat["items"]] == ["md-1", "md-2", "md-3"]  # ids never move

    # Idempotent: writing the healed catalog back and reloading changes nothing.
    catalog_mod.write(store, cat)
    assert {it["id"]: it["title"] for it in catalog_mod.load(store)["items"]} == titles


def test_catalog_load_heal_survives_malformed_rows(tmp_path):
    store = LocalStore(tmp_path / "store")
    store.put_bytes(catalog_mod.CATALOG_KEY, json.dumps({
        "schema": "research_vault.catalog.v1", "items": [
            "not-a-dict", {"id": "md-1"}, {"id": "md-2", "title": None},
            {"id": "md-3", "title": "SAP (SAPG"},
        ],
    }).encode("utf-8"), "application/json")
    cat = catalog_mod.load(store)
    assert cat["items"][-1]["title"] == "SAP (SAPG)"


# ===========================================================================
# corpus: FTS build + body-only search + facet filter
# ===========================================================================

def test_corpus_body_is_searchable(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    item = sidecar_mod.normalize(
        {"id": "doc1", "title": "Quiet Title", "institution": "Bernstein",
         "published_at": "2026-07-21", "summary_points": ["short summary"]})
    body = "The nameplate pipeline includes substantial hyperscaler capacity in Texas."
    corpus_mod.upsert(conn, item, body)

    # A term that appears ONLY in the body (not title/summary) must match.
    hits = corpus_mod.search(conn, "hyperscaler")
    assert len(hits) == 1
    assert hits[0]["id"] == "doc1"
    assert hits[0]["title"] == "Quiet Title"

    # A word absent everywhere returns nothing.
    assert corpus_mod.search(conn, "zzznotpresent") == []
    conn.close()


def test_corpus_facet_filter_by_institution(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    common_body = "capacity capacity capacity pipeline"
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "b1", "title": "T1", "institution": "Bernstein", "published_at": "2026-07-01"}),
        common_body)
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "g1", "title": "T2", "institution": "Goldman Sachs", "published_at": "2026-07-02"}),
        common_body)

    all_hits = corpus_mod.search(conn, "capacity")
    assert {h["id"] for h in all_hits} == {"b1", "g1"}

    only_b = corpus_mod.search(conn, "capacity", institution="Bernstein")
    assert [h["id"] for h in only_b] == ["b1"]
    conn.close()


def test_corpus_facet_date_range(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    for i, d in enumerate(["2026-06-01", "2026-07-15", "2026-08-20"]):
        corpus_mod.upsert(conn, sidecar_mod.normalize(
            {"id": f"d{i}", "title": "x", "institution": "GS", "published_at": d}),
            "alpha beta gamma")
    mid = corpus_mod.search(conn, "beta", date_from="2026-07-01", date_to="2026-07-31")
    assert [h["id"] for h in mid] == ["d1"]
    conn.close()


def test_corpus_title_weight_beats_body(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    # "datacenter" in the TITLE of one, only in the BODY of the other. (ids are
    # slugged for url-safety, so "title_hit" normalizes to "title-hit".)
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "title-hit", "title": "Datacenter Report", "institution": "GS",
         "published_at": "2026-07-01"}), "generic body about markets")
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "body-hit", "title": "Markets Weekly", "institution": "GS",
         "published_at": "2026-07-02"}), "a datacenter is mentioned once here")
    hits = corpus_mod.search(conn, "datacenter")
    assert hits[0]["id"] == "title-hit"  # title weight 4 > body weight 1
    conn.close()


def test_corpus_sanitizer_strips_operators(tmp_path):
    # Malicious/operator-laden input must not raise, just degrade.
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "d", "title": "safe", "institution": "GS", "published_at": "2026-07-01"}),
        "the quick brown fox")
    # These would be FTS5 syntax errors if not sanitized.
    for bad in ['fox NOT quick', 'fox OR OR', '"unterminated', 'fox AND (quick', '*(']:
        got = corpus_mod.search(conn, bad)
        assert isinstance(got, list)  # never raises
    # A plain matching token still works after sanitization.
    assert len(corpus_mod.search(conn, "fox")) == 1
    conn.close()


def test_corpus_empty_query_returns_empty(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "d", "title": "x", "institution": "GS", "published_at": "2026-07-01"}), "body")
    assert corpus_mod.search(conn, "") == []
    assert corpus_mod.search(conn, "   ") == []
    conn.close()


def test_corpus_upsert_replaces_not_duplicates(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    item = sidecar_mod.normalize(
        {"id": "d", "title": "x", "institution": "GS", "published_at": "2026-07-01"})
    corpus_mod.upsert(conn, item, "first body has apples")
    corpus_mod.upsert(conn, item, "second body has oranges")
    # Old body term gone; only one row.
    assert corpus_mod.search(conn, "apples") == []
    assert len(corpus_mod.search(conn, "oranges")) == 1
    n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert n == 1
    conn.close()


# ===========================================================================
# ingest: end-to-end via the LOCAL store
# ===========================================================================

# A minimal valid single-page PDF (enough for a store round-trip; body text comes
# from the monkeypatched extractor so we don't depend on poppler in CI).
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)


@pytest.fixture
def canned_pdftotext(monkeypatch):
    """Make extract_pdf_text return a body keyed off the PDF bytes (no poppler)."""
    def _fake(pdf_bytes: bytes):
        # Distinct body per fixture so body-search assertions are meaningful.
        if b"ALPHA" in pdf_bytes:
            return "hyperscaler capacity dominates the credible pipeline in Texas"
        return "generic research body text"
    monkeypatch.setattr(ingest_mod, "extract_pdf_text", _fake)
    return _fake


def _seed_pdf(store, pdf_key, sidecar_obj, marker=b""):
    store.put_bytes(pdf_key, _MINIMAL_PDF + marker, "application/pdf")
    if sidecar_obj is not None:
        raw = (json.dumps(sidecar_obj) if isinstance(sidecar_obj, dict) else sidecar_obj)
        store.put_bytes(pdf_key[:-4] + ".json",
                        raw.encode() if isinstance(raw, str) else raw, "application/json")


def test_already_processed_skips_on_pdf_key_not_filename(tmp_path):
    """The processed-skip set is the source ``pdf_key`` recorded in each receipt
    body — NOT the receipt filename, since a receipt is named by the derived id
    which can differ from the source PDF's filename. Non-json / broken receipts
    are ignored, never raising. (Bodies are fetched concurrently for scale.)"""
    store = LocalStore(tmp_path / "store")
    store.put_bytes(
        "research_inbox/_processed/bernstein-2026-07-21-x.json",
        json.dumps({"id": "bernstein-2026-07-21-x",
                    "pdf_key": "research_inbox/rep1.pdf"}).encode("utf-8"))
    store.put_bytes(
        "research_inbox/_processed/gs-2026-07-20-y.json",
        json.dumps({"id": "gs-2026-07-20-y",
                    "pdf_key": "research_inbox/rep2.pdf"}).encode("utf-8"))
    store.put_bytes("research_inbox/_processed/README.txt", b"ignore me")
    store.put_bytes("research_inbox/_processed/broken.json", b"{ not json ]")

    done = ingest_mod._already_processed_pdf_keys(store)
    assert done == {"research_inbox/rep1.pdf", "research_inbox/rep2.pdf"}


def test_ingest_end_to_end_and_idempotent(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"

    _seed_pdf(store, "research_inbox/rep1.pdf", {
        "schema": "research_vault.sidecar.v1",
        "title": "DC Pipeline", "institution": "Bernstein",
        "published_at": "2026-07-21T14:00:00Z",
        "summary_points": ["Only 33% credible"], "top_pick": True,
    }, marker=b"ALPHA")
    _seed_pdf(store, "research_inbox/rep2.pdf", {
        "schema": "research_vault.sidecar.v1",
        "title": "Markets Weekly", "institution": "Goldman Sachs",
        "published_at": "2026-07-20T09:00:00Z", "summary_points": ["watch rates"],
    })

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 2
    assert summary["failed"] == 0
    assert summary["skipped"] == 0

    # Catalog published + newest-first + top_pick preserved.
    cat = catalog_mod.load(store)
    assert cat["count"] == 2
    assert cat["items"][0]["id"].startswith("bernstein-2026-07-21")  # newest
    assert cat["institutions"] == ["Bernstein", "Goldman Sachs"]
    top_ids = [it["id"] for it in cat["items"] if it["top_pick"]]
    assert len(top_ids) == 1

    # PDFs promoted into the vault (private).
    bern_id = cat["items"][0]["id"]
    assert store.exists(f"research_vault/{bern_id}.pdf")

    # Receipts written for both.
    receipts = store.list_prefix("research_inbox/_processed/")
    assert len(receipts) == 2

    # Body text is searchable via the corpus that ingest built.
    conn = corpus_mod.open_db(corpus_path)
    hits = corpus_mod.search(conn, "hyperscaler")
    assert len(hits) == 1 and hits[0]["id"] == bern_id
    conn.close()

    # IDEMPOTENCY: a second pass ingests 0 and skips both.
    summary2 = ingest_mod.run(store, corpus_path)
    assert summary2["ingested"] == 0
    assert summary2["skipped"] == 2
    # Catalog unchanged in count.
    assert catalog_mod.load(store)["count"] == 2


def test_ingest_bad_sidecar_needs_metadata_but_not_dropped(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # Corrupt JSON sidecar → must still ingest, flagged needs_metadata.
    _seed_pdf(store, "research_inbox/orphan.pdf", "{ this is not : valid json ]")

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 1
    assert summary["needs_metadata"] == 1

    cat = catalog_mod.load(store)
    assert cat["count"] == 1
    row = cat["items"][0]
    assert row["needs_metadata"] is True
    assert row["institution"] == "Unknown"
    # Title fell back to the filename stem.
    assert "orphan" in row["title"].lower()


def test_ingest_missing_sidecar_uses_upload_time(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # No sidecar at all.
    store.put_bytes("research_inbox/nosidecar.pdf", _MINIMAL_PDF, "application/pdf")

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 1
    cat = catalog_mod.load(store)
    row = cat["items"][0]
    assert row["needs_metadata"] is True     # no institution
    assert row["institution"] == "Unknown"
    assert row["published_at"]               # filled from upload time (mtime)


def test_ingest_top_picks_prefix_sets_top_pick(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # Sidecar does NOT set top_pick, but the file is under top_picks/.
    _seed_pdf(store, "research_inbox/top_picks/hot.pdf", {
        "title": "Hot Take", "institution": "Bernstein",
        "published_at": "2026-07-21", "top_pick": False,
    })
    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 1
    cat = catalog_mod.load(store)
    assert cat["items"][0]["top_pick"] is True   # prefix wins


def test_ingest_no_store_is_noop():
    summary = ingest_mod.run(None, "/tmp/whatever.sqlite")
    assert summary == {"ingested": 0, "skipped": 0, "failed": 0,
                       "needs_metadata": 0, "catalog_bytes": b""}


def test_ingest_one_bad_pdf_does_not_abort_batch(tmp_path, canned_pdftotext, monkeypatch):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/good.pdf", {
        "title": "Good", "institution": "GS", "published_at": "2026-07-20"})
    _seed_pdf(store, "research_inbox/boom.pdf", {
        "title": "Boom", "institution": "GS", "published_at": "2026-07-21"})

    # Make corpus.upsert raise ONLY for the "Boom" doc to prove per-item isolation.
    real_upsert = corpus_mod.upsert

    def _flaky(conn, item, body):
        if item.get("title") == "Boom":
            raise RuntimeError("simulated corpus failure")
        return real_upsert(conn, item, body)

    monkeypatch.setattr(ingest_mod.corpus_mod, "upsert", _flaky)

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 1   # good one succeeds
    assert summary["failed"] == 1     # boom isolated, batch survived
    cat = catalog_mod.load(store)
    assert [it["title"] for it in cat["items"]] == ["Good"]


def test_ingest_corpus_persists_across_runs_via_store(tmp_path, canned_pdftotext):
    """History must survive an hourly run on a FRESH runner (empty local /tmp).

    Regression for the silent-data-loss bug: the corpus is restored from the store
    before each run, so a run that only ADDS this hour's docs still republishes a
    corpus holding ALL prior docs. Without the restore, run 2 (different local
    corpus path == fresh runner) would publish a corpus with ONLY rep2 and drop
    rep1 from search entirely.
    """
    store = LocalStore(tmp_path / "store")
    corpus_a = tmp_path / "run1" / "corpus.sqlite"
    corpus_b = tmp_path / "run2" / "corpus.sqlite"  # different path → fresh runner

    _seed_pdf(store, "research_inbox/rep1.pdf", {
        "title": "DC Pipeline", "institution": "Bernstein",
        "published_at": "2026-07-21T14:00:00Z"}, marker=b"ALPHA")
    s1 = ingest_mod.run(store, corpus_a)
    assert s1["ingested"] == 1
    assert store.exists(ingest_mod.CORPUS_KEY)      # corpus published to the store

    _seed_pdf(store, "research_inbox/rep2.pdf", {
        "title": "Markets Weekly", "institution": "Goldman Sachs",
        "published_at": "2026-07-22T09:00:00Z"})
    s2 = ingest_mod.run(store, corpus_b)
    assert s2["ingested"] == 1 and s2["skipped"] == 1

    # The republished corpus holds BOTH docs; rep1's BODY is still searchable.
    conn = corpus_mod.open_db(corpus_b)
    assert corpus_mod.institutions(conn) == ["Bernstein", "Goldman Sachs"]
    assert len(corpus_mod.search(conn, "hyperscaler")) == 1   # rep1 body preserved
    conn.close()


def test_ingest_checkpoint_survives_mid_run_kill(tmp_path, canned_pdftotext, monkeypatch):
    """A run killed mid-backfill must not orphan receipted docs (backfill hardening).

    Receipts are written per item; without mid-run checkpoints, a killed run
    leaves receipted docs that every later run skips but that never reached the
    published catalog/corpus. With checkpoint_every=1 we kill the run at the
    SECOND corpus checkpoint and prove (a) the store already holds the first
    doc, and (b) a plain re-run converges to all three.
    """
    store = LocalStore(tmp_path / "store")
    for i, d in enumerate(["2026-07-01", "2026-07-02", "2026-07-03"]):
        _seed_pdf(store, f"research_inbox/p{i}.pdf", {
            "title": f"Paper {i}", "institution": "GS", "published_at": d})

    real_publish = ingest_mod.publish_corpus
    calls = {"n": 0}

    def _killing_publish(store_, corpus_path_):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("simulated GHA kill")  # BaseException: not swallowed
        return real_publish(store_, corpus_path_)

    monkeypatch.setattr(ingest_mod, "publish_corpus", _killing_publish)
    with pytest.raises(KeyboardInterrupt):
        ingest_mod.run(store, tmp_path / "run1" / "c.sqlite", checkpoint_every=1)

    # Checkpoint #1 landed: store catalog+corpus hold doc 1, and ONLY doc 1 is
    # receipted (receipts flush strictly AFTER their batch's publish — the
    # invariant is receipted => present in a published catalog+corpus).
    assert catalog_mod.load(store)["count"] >= 1
    assert store.exists(ingest_mod.CORPUS_KEY)
    receipts = store.list_prefix("research_inbox/_processed/")
    assert len(receipts) == 1

    # Recovery: a plain re-run (fresh runner path) re-ingests the unreceipted
    # docs and converges — catalog AND searchable corpus both reach all 3.
    monkeypatch.setattr(ingest_mod, "publish_corpus", real_publish)
    s2 = ingest_mod.run(store, tmp_path / "run2" / "c.sqlite", checkpoint_every=1)
    assert s2["ingested"] == 2 and s2["skipped"] == 1
    assert catalog_mod.load(store)["count"] == 3
    pulled = tmp_path / "pulled.sqlite"
    pulled.write_bytes(store.get_bytes(ingest_mod.CORPUS_KEY))
    conn = corpus_mod.open_db(pulled)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    conn.close()
    assert len(store.list_prefix("research_inbox/_processed/")) == 3


def test_corpus_body_capped(tmp_path):
    """Body text is capped per doc so a backfilled corpus stays transferable."""
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    body = ("EARLYTOKEN " * 3) + ("x" * corpus_mod.BODY_MAX_CHARS) + " LATETOKEN"
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": "cap", "title": "t", "institution": "GS",
         "published_at": "2026-07-01"}), body)
    stored = conn.execute("SELECT length(body) FROM documents").fetchone()[0]
    assert stored <= corpus_mod.BODY_MAX_CHARS
    assert len(corpus_mod.search(conn, "EARLYTOKEN")) == 1   # inside cap: searchable
    assert corpus_mod.search(conn, "LATETOKEN") == []        # beyond cap: dropped
    conn.close()


def test_ingest_dry_run_mutates_nothing(tmp_path, canned_pdftotext):
    """--dry-run reports what it WOULD do but writes nothing to the store."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/rep1.pdf", {
        "title": "DC Pipeline", "institution": "Bernstein",
        "published_at": "2026-07-21T14:00:00Z"}, marker=b"ALPHA")

    summary = ingest_mod.run(store, corpus_path, dry_run=True)
    assert summary["ingested"] == 1        # reports what it would ingest
    assert summary["catalog_bytes"]        # serialized for inspection

    # Nothing written to the store: no catalog, no corpus, no receipts, no PDF.
    assert not store.exists(catalog_mod.CATALOG_KEY)
    assert not store.exists(ingest_mod.CORPUS_KEY)
    assert store.list_prefix("research_inbox/_processed/") == []
    assert store.list_prefix("research_vault/") == []

    # A real run right after still ingests it (dry-run left no receipt).
    assert ingest_mod.run(store, corpus_path)["ingested"] == 1


# ===========================================================================
# excerpt: the PUBLIC first-pages lead-in (SEO exact-quote play)
# ===========================================================================

# pdftotext writes \f between pages, so these fixtures are shaped like real
# extractor output: form-feed page breaks, blank-line paragraph groups.
_XP1 = ("Alphapageone opens the report with a thesis paragraph long enough to read as "
        "prose rather than page furniture, which is what the cleaner is deciding.\n\n"
        "A second paragraph on the same page carries that thesis forward with plenty of "
        "characters to clear the paragraph floor.")
_XP2 = ("Bravopagetwo continues onto the next page with another substantial block of "
        "argument, keeping the first two pages comfortably above the sparse floor.")
_XP3 = "Charliepagethree sits past the two-page window and must never be published."


def test_excerpt_derive_stops_at_the_page_window():
    paras = excerpt_mod.derive("\f".join([_XP1, _XP2, _XP3]))
    joined = " ".join(paras)
    assert "Alphapageone" in joined and "Bravopagetwo" in joined
    # Rich first pages: no reason to widen the window, so page 3 stays private.
    assert sum(len(p) for p in paras) >= excerpt_mod.SPARSE_MIN_CHARS
    assert "Charliepagethree" not in joined


def test_excerpt_derive_strips_emails_urls_and_phones():
    body = ("Contact research@example-bank.com for distribution, see "
            "https://example-bank.com/disclosures and www.example-bank.com/terms for "
            "the standard disclaimers that accompany every published report.\n\n"
            "Analyst contacts: ben.x@example-bank.com +1 212 555 0100 and "
            "(212) 555-0199, on guidance of $780-790mn for the coming year.\n\n"
            "We hold our 2025-2026 estimates unchanged as of 2026-07-25, with the "
            "risk to that call skewed to the upside on the back of the capex guide.")
    joined = " ".join(excerpt_mod.derive(body))
    assert "Contact for distribution" in joined     # text kept, contact/link removed
    assert "@" not in joined
    assert "http" not in joined and "www." not in joined
    # Stripping the email but leaving the desk line would still publish the phone.
    assert "555" not in joined and "212" not in joined
    # ...while a short prose figure stays: the length floor is what separates them.
    assert "$780-790mn" in joined
    # Dates share the phone SHAPE, so the digit floor — not the length floor — is
    # what saves them: 8 digits each, and bank prose is full of both.
    assert "our 2025-2026 estimates" in joined
    assert "as of 2026-07-25" in joined


def test_excerpt_derive_caps_chars_at_a_word_boundary():
    body = ("hyperscaler capacity " * 60).strip()   # one long single paragraph
    paras = excerpt_mod.derive(body, max_chars=120)
    assert len(paras) == 1
    text = paras[0]
    assert text.endswith("…")                       # visibly stops mid-report
    assert len(text) <= 121                         # cap + the ellipsis
    kept = text[:-1]
    assert body.startswith(kept) and not kept.endswith(" ")   # whole-word prefix

    # The default dial bounds a full-length body too.
    big = excerpt_mod.derive("alpha beta gamma delta " * 500)
    assert sum(len(p) for p in big) <= excerpt_mod.EXCERPT_MAX_CHARS + 1


def test_excerpt_derive_empty_input_is_empty_list():
    assert excerpt_mod.derive(None) == []
    assert excerpt_mod.derive("") == []
    assert excerpt_mod.derive("   \n\n \f \t ") == []   # scanned PDF: no text layer


def test_excerpt_sparse_cover_pages_extend_the_window():
    """Bank cover pages are often text-sparse — widen rather than publish nothing."""
    cover = "MORGAN STANLEY"                                  # under the para floor
    page2 = "Global Macro Strategy — July 2026 edition"       # kept, still sparse
    page3 = ("Deltapagethree carries the actual opening argument and runs well past "
             "the sparse floor, so the widened window stops right here. " * 4)
    page4 = "Echopagefour must stay out of the published excerpt entirely."
    joined = " ".join(excerpt_mod.derive("\f".join([cover, page2, page3, page4])))
    assert "Deltapagethree" in joined      # widened past the 2-page default…
    assert "Echopagefour" not in joined    # …but only as far as it had to


def test_excerpt_window_never_exceeds_four_pages():
    thin = [f"Page {i} carries one short line only, nowhere near the sparse floor."
            for i in range(1, 5)]
    thin.append("Foxtrotpagefive is past the four-page ceiling and must never publish.")
    joined = " ".join(excerpt_mod.derive("\f".join(thin)))
    assert "Page 1 carries" in joined and "Page 4 carries" in joined
    assert "Foxtrotpagefive" not in joined


def _x_doc(conn, doc_id, body):
    corpus_mod.upsert(conn, sidecar_mod.normalize(
        {"id": doc_id, "title": "T", "institution": "GS", "published_at": "2026-07-01"}),
        body)


def test_excerpt_snapshot_is_restricted_to_catalog_ids():
    conn = corpus_mod.open_db(":memory:")
    prose = ("Alphabody opens the sampled report with a paragraph long enough to "
             "survive the paragraph floor and land in the published excerpt.")
    _x_doc(conn, "z-doc", prose)
    _x_doc(conn, "a-doc", prose)
    _x_doc(conn, "m-doc", prose)      # in the corpus but NOT in the catalog
    _x_doc(conn, "s-doc", "")         # scanned PDF: derives to [] → omitted

    out = excerpt_mod.snapshot(conn, {"z-doc", "a-doc", "s-doc"})
    assert list(out) == ["a-doc", "z-doc"]        # sorted → deterministic diffs
    assert out["a-doc"][0].startswith("Alphabody")
    assert excerpt_mod.snapshot(conn, set()) == {}
    conn.close()


def test_excerpt_write_repo_snapshot_refuses_empty(tmp_path):
    """An empty derivation must never clobber a good committed snapshot."""
    p = tmp_path / "excerpts.json"
    assert excerpt_mod.write_repo_snapshot({}, p) is False
    assert not p.exists()


def test_excerpt_write_repo_snapshot_is_deterministic(tmp_path):
    """Timestamp-free + sorted: an unchanged hour produces no git diff, no churn."""
    p = tmp_path / "sub" / "excerpts.json"        # parent is created on demand
    data = {"b-doc": ["second doc"], "a-doc": ["first doc", "第二段"]}
    assert excerpt_mod.write_repo_snapshot(data, p) is True
    first = p.read_bytes()

    reordered = dict(reversed(list(data.items())))
    assert excerpt_mod.write_repo_snapshot(reordered, p) is True
    assert p.read_bytes() == first

    payload = json.loads(first.decode("utf-8"))
    assert payload["schema"] == 1
    assert payload["excerpts"]["a-doc"] == ["first doc", "第二段"]
    assert "第二段".encode("utf-8") in first        # ensure_ascii=False


# ===========================================================================
# r2_store factory + local backend
# ===========================================================================

def test_build_store_local_arg(tmp_path):
    store = build_store(local_dir=tmp_path / "s")
    assert isinstance(store, LocalStore)
    assert store.available is True


def test_build_store_env_local(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_LOCAL_STORE", str(tmp_path / "envstore"))
    store = build_store()
    assert isinstance(store, LocalStore)


def test_build_store_none_without_creds(monkeypatch):
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    monkeypatch.delenv("R2_RESEARCH_BUCKET", raising=False)
    assert build_store() is None


def test_local_store_rejects_traversal(tmp_path):
    store = LocalStore(tmp_path / "s")
    with pytest.raises(ValueError):
        store._p("../escape.txt")


def test_local_store_get_missing_is_none(tmp_path):
    store = LocalStore(tmp_path / "s")
    assert store.get_bytes("nope.txt") is None
    assert store.exists("nope.txt") is False
    assert store.upload_time("nope.txt") is None


def test_local_store_list_prefix(tmp_path):
    store = LocalStore(tmp_path / "s")
    store.put_bytes("research_inbox/a.pdf", b"x")
    store.put_bytes("research_inbox/_processed/a.json", b"{}")
    store.put_bytes("research_vault/a.pdf", b"y")
    inbox = store.list_prefix("research_inbox/")
    assert "research_inbox/a.pdf" in inbox
    assert "research_inbox/_processed/a.json" in inbox
    assert "research_vault/a.pdf" not in inbox


def test_r2_client_prefers_research_account_creds(monkeypatch):
    """R2_RESEARCH_* (a separate Cloudflare account) is preferred over the shared
    R2_* creds, and each falls back to R2_* when unset. Skipped where boto3 is
    absent (the minimal CI lane); client construction is offline (creds aren't
    validated until a call), so we can assert the resolved endpoint."""
    import pytest as _pytest
    _pytest.importorskip("boto3")
    from engine.research_vault import r2_store as rs
    monkeypatch.setenv("R2_ENDPOINT", "https://shared.example.com")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "shared-ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "shared-sk")
    monkeypatch.setenv("R2_RESEARCH_ENDPOINT", "https://research.example.com")
    monkeypatch.setenv("R2_RESEARCH_ACCESS_KEY_ID", "research-ak")
    monkeypatch.setenv("R2_RESEARCH_SECRET_ACCESS_KEY", "research-sk")
    assert rs._r2_client().meta.endpoint_url == "https://research.example.com"
    for _k in ("R2_RESEARCH_ENDPOINT", "R2_RESEARCH_ACCESS_KEY_ID", "R2_RESEARCH_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(_k, raising=False)
    assert rs._r2_client().meta.endpoint_url == "https://shared.example.com"


# ===========================================================================
# title: filename-derived titles (detection, cleaning, first-page recovery)
# ===========================================================================

@pytest.mark.parametrize("bad", [
    "2026 07 24 Rearming Britain's Supply Side en",   # ISO date stamp + language
    "26 07 24 Focus Europe ECB Reaction",             # 2-digit date stamp
    "260723 ECB slightly hawkish hold",               # compact date stamp
    "Daily Asia en 1663849 1",                        # language + document id
    "JPM International Ma 2026 07 24 5381087",        # trailing id run
    "China 2026 Outlook Exploring New Growth (1)",    # re-download marker
    "Consensus(1)",                                   # …with no space
])
def test_title_detects_filename_furniture(bad):
    assert title_mod.looks_filename_derived(bad) is True


@pytest.mark.parametrize("good", [
    "US Econ Notes July 24",                          # trailing day number
    "European Equities Week Ahead Jul 27 Jul 31",     # two of them
    "Recap 7 24 26",                                  # a date IS the title here
    "invesco low cost ai strategy july 2026",         # trailing year
    "China 2026 Outlook Exploring New Growth Engines",  # interior year
    "Fed Chatterbox July Edition",
    "Alcon Inc. (ALCC.US)",
    "China Property HK",                              # "hk"/"it"/"no" are words,
    "Semis and IT",                                   # …not language suffixes
    "",
])
def test_title_leaves_real_titles_alone(good):
    assert title_mod.looks_filename_derived(good) is False
    assert title_mod.resolve(good) == (good, "sidecar")


def test_title_clean_strips_only_the_furniture():
    assert title_mod.clean("2026 07 24 Rearming Britain's Supply Side en") == \
        "Rearming Britain's Supply Side"
    assert title_mod.clean("Daily US en 1663880 1") == "Daily US"   # keeps "US"
    assert title_mod.clean("US Econ Notes July 24") == "US Econ Notes July 24"


def test_title_recovered_from_the_reports_own_first_page():
    """The headline the PDF prints wins over the prettified filename."""
    body = ("Europe Watch - Quick Insights 24 Jul 2026\n"
            "PMI: FALL SEVEN TIMES, GET UP EIGHT\n"
            "Davide Oneglia\n\n"
            "July flash Euro Area PMIs surprised to the upside across sectors.\f"
            "page two: pmi fall seven times get up eight decoy\n")
    got, src = title_mod.resolve("2026 07 24 Pmi Fall Seven Times Get Up Eight en", body)
    assert got == "PMI: FALL SEVEN TIMES, GET UP EIGHT"   # punctuation + casing restored
    assert src == "pdf"


def test_title_recovery_drops_the_byline_printed_after_the_headline():
    body = "REARMING BRITAIN'S SUPPLY SIDE Alexandros Xenofontos\n"
    got, src = title_mod.resolve("2026 07 24 Rearming Britain's Supply Side en", body)
    assert got == "REARMING BRITAIN'S SUPPLY SIDE"
    assert src == "pdf"


def test_title_recovery_closes_a_bracket_the_anchor_cut():
    body = "Transformational Innovation Opportunities (TRIO) — 2026 update\n"
    got, src = title_mod.resolve("Transformational Innovation Opportunities (TRIO) en 1662393 1", body)
    assert got == "Transformational Innovation Opportunities (TRIO)"
    assert src == "pdf"


def test_title_recovery_is_anchored_never_generative():
    """A first page full of other headlines can never rename the report."""
    body = ("GLOBAL MARKETS DAILY\nA COMPLETELY DIFFERENT HEADLINE\n"
            "Some prose that mentions daily asia in passing.\n")
    got, src = title_mod.resolve("Daily Asia Weekly Wrap en 1663849 1", body)
    assert got == "Daily Asia Weekly Wrap"     # cleaned only — nothing invented
    assert src == "filename"


def test_title_recovery_needs_a_real_anchor():
    # A 1-2 word title anchors nothing: cleaned, never "recovered".
    got, src = title_mod.resolve("Platinum en 1663759 1", "CIO View: Platinum\n")
    assert (got, src) == ("Platinum", "filename")


def test_title_resolve_is_idempotent():
    body = "PMI: FALL SEVEN TIMES, GET UP EIGHT Davide Oneglia\n"
    once, _ = title_mod.resolve("2026 07 24 Pmi Fall Seven Times Get Up Eight en", body)
    assert title_mod.resolve(once, body) == (once, "sidecar")   # second pass is a no-op


def test_title_never_empties_a_title():
    got, _src = title_mod.resolve("en 1663849 1", "")
    assert got.strip()


# ===========================================================================
# ingest: title repair at ingest time + over the EXISTING catalog
# ===========================================================================

def test_ingest_recovers_a_filename_title_from_the_pdf(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "store")
    monkeypatch.setattr(
        ingest_mod, "extract_pdf_text",
        lambda b: "PMI: FALL SEVEN TIMES, GET UP EIGHT Davide Oneglia\n")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "2026 07 24 Pmi Fall Seven Times Get Up Eight en",
        "institution": "TS Lombard", "published_at": "2026-07-24T14:48:53Z",
    })
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["ingested"] == 1
    assert summary["titles_recovered"] == 1
    row = catalog_mod.load(store)["items"][0]
    assert row["title"] == "PMI: FALL SEVEN TIMES, GET UP EIGHT"
    assert row["needs_metadata"] is False       # the sidecar DID carry a title


def test_repair_titles_heals_documents_already_in_the_catalog(tmp_path, canned_pdftotext):
    """The receipted-doc path: ingest never re-reads those PDFs, so the repair pass
    over the loaded catalog is the only thing that can reach them."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "id": "marketdesk-abc-3a8606", "title": "Rates Weekly Outlook en 1663849 1",
        "institution": "UBS", "published_at": "2026-07-24T10:00:00Z",
    })
    ingest_mod.run(store, corpus_path)

    # Simulate the pre-fix state: put the filename title back into both stores.
    cat = catalog_mod.load(store)
    cat["items"][0]["title"] = "Rates Weekly Outlook en 1663849 1"
    catalog_mod.write(store, cat)
    conn = corpus_mod.open_db(corpus_path)
    conn.execute("UPDATE documents SET title=?, body=? WHERE doc_id=?",
                 ("Rates Weekly Outlook en 1663849 1",
                  "RATES WEEKLY OUTLOOK: THE LONG END WINS\nMark Haefele\n",
                  "marketdesk-abc-3a8606"))
    conn.commit(); conn.close()
    # The store copy is the source of truth — run() restores it over the local
    # file, so the edit has to be published to survive into the repair pass.
    ingest_mod.publish_corpus(store, corpus_path)

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 0 and summary["skipped"] == 1   # nothing re-ingested
    assert summary["titles_repaired"] == 1
    # Casing restored from the PDF; the ": THE LONG END WINS" the filename never
    # carried is left off — past the anchor, a subtitle and a byline are the same
    # shape, and a title is not the place to guess.
    assert catalog_mod.load(store)["items"][0]["title"] == "RATES WEEKLY OUTLOOK"

    # The corpus title is repaired too (title is the heaviest FTS column).
    conn = corpus_mod.open_db(corpus_path)
    hits = corpus_mod.search(conn, "Rates Weekly Outlook")
    assert hits and hits[0]["id"] == "marketdesk-abc-3a8606"
    assert hits[0]["title"] == "RATES WEEKLY OUTLOOK"
    conn.close()

    # And a third run is a clean no-op — the repair does not flap.
    assert ingest_mod.run(store, corpus_path)["titles_repaired"] == 0


def test_repair_titles_survives_a_missing_corpus_row(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Good Title", "institution": "UBS", "published_at": "2026-07-24",
    })
    ingest_mod.run(store, corpus_path)
    cat = catalog_mod.load(store)
    # A catalog row with no corpus body at all (id never ingested here).
    cat["items"].append({"id": "ghost-1", "title": "Swiss economy en 1663943 1",
                         "institution": "UBS", "published_at": "2026-07-01"})
    catalog_mod.write(store, cat)

    summary = ingest_mod.run(store, corpus_path)
    assert summary["titles_repaired"] == 1
    titles = {it["title"] for it in catalog_mod.load(store)["items"]}
    assert "Swiss economy" in titles            # cleaned without a body, never dropped
