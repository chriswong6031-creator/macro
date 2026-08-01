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
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _probe_rung_available() -> bool:
    """True when at least one of probe.py's PDF-parsing rungs can run here.

    Page-count assertions need pypdf OR poppler; with neither, ``probe`` correctly
    reports None and those tests would be asserting the absence of a dependency
    rather than the behaviour of the code.
    """
    if shutil.which("pdfinfo"):
        return True
    try:
        import pypdf  # noqa: F401, PLC0415
        return True
    except Exception:  # noqa: BLE001
        return False


# A REAL PDF, used wherever a test asserts a MEASURED page count.
#
# Why not the hand-rolled ``_MINIMAL_PDF`` below: it has no xref table, so pypdf
# refuses it outright and only poppler is lenient enough to report its one page.
# Asserting a measured page count against that fixture silently makes the test
# poppler-only — green on the self-hosted Mac, red on the ubuntu CI lane that
# installs pypdf and no system packages. A real PDF is read by BOTH rungs.
_REAL_PDF = Path(__file__).resolve().parent / "fixtures" / "hk_cbbc" / "sample_sld_index.pdf"
_REAL_PDF_PAGES = 16
_HAVE_PDFINFO = shutil.which("pdfinfo") is not None

_needs_measured = pytest.mark.skipif(
    not (_REAL_PDF.is_file() and _probe_rung_available()),
    reason="needs the real PDF fixture plus pypdf or poppler to measure page counts")

# The poppler rung specifically — the one production runs, since the hourly ingest
# lane installs only boto3+pyyaml. Skips where poppler is absent (ubuntu CI).
_needs_pdfinfo = pytest.mark.skipif(
    not (_REAL_PDF.is_file() and _HAVE_PDFINFO),
    reason="poppler pdfinfo or the real PDF fixture is absent")


def _have_pypdf() -> bool:
    try:
        import pypdf  # noqa: F401, PLC0415
        return True
    except Exception:  # noqa: BLE001
        return False


# Cross-checking one rung against the other is only meaningful when BOTH exist —
# neither the ubuntu CI lane (no poppler) nor the hourly ingest lane (no pypdf) has
# both, so this skips in each of them and runs in a full local/dev environment.
_needs_both_rungs = pytest.mark.skipif(
    not (_REAL_PDF.is_file() and _HAVE_PDFINFO and _have_pypdf()),
    reason="needs BOTH pypdf and poppler pdfinfo to cross-check them")

from engine.research_vault import catalog as catalog_mod
from engine.research_vault import corpus as corpus_mod
from engine.research_vault import excerpt as excerpt_mod
from engine.research_vault import ingest as ingest_mod
from engine.research_vault import probe as probe_mod
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


def test_normalize_missing_published_at_honors_explicit_fallback():
    # normalize() keeps a generic published_at fallback param, but the research-vault
    # ingest caller deliberately never feeds it our clock (see the ingest test
    # test_ingest_missing_sidecar_leaves_date_blank_never_our_time). An EXPLICIT
    # known-good date passed by a caller is still honored.
    item = sidecar_mod.normalize(
        {"title": "T", "institution": "GS"},
        fallback_published_at="2026-07-22T09:00:00Z")
    assert item["published_at"] == "2026-07-22T09:00:00Z"


def test_normalize_missing_published_at_and_no_fallback_stays_blank():
    # No sidecar date + no fallback → blank, never fabricated. A blank date sorts
    # LAST in the catalog, so an undated paper can never masquerade as the newest.
    item = sidecar_mod.normalize({"title": "T", "institution": "GS"})
    assert item["published_at"] == ""


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


def test_public_summary_describes_the_full_catalog_not_a_preview_slice():
    cat = {
        "items": [
            {"id": "a1", "institution": "Desk A", "published_at": "2026-07-31T10:00:00Z",
             "tags": ["AI"], "top_pick": True},
            {"id": "a2", "institution": "Desk A", "published_at": "2026-07-25T10:00:00Z",
             "tags": ["Macro", "AI"], "top_pick": False},
            {"id": "b", "institution": "Desk B", "published_at": "2026-07-24T10:00:00Z",
             "tags": ["AI"], "top_pick": False},
            {"id": "c", "institution": "Desk C", "published_at": "2026-07-23T10:00:00Z",
             "tags": ["Old theme"], "top_pick": False},
        ]
    }

    summary = catalog_mod.public_summary(
        cat, now=datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    )

    assert summary == {
        "total": 4,
        "new_this_week": 3,
        "desks_this_week": 2,
        "highlighted": 1,
        "most_covered_theme": "AI",
        "institutions": [
            {"name": "Desk A", "count": 2},
            {"name": "Desk B", "count": 1},
            {"name": "Desk C", "count": 1},
        ],
    }


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


def _seed_pdf(store, pdf_key, sidecar_obj, marker=b"", pdf_bytes=None):
    """Seed a PDF + its sidecar into the store.

    ``pdf_bytes`` overrides the hand-rolled minimal fixture — pass the real PDF
    when the test asserts a MEASURED page count (see _REAL_PDF above).
    """
    store.put_bytes(pdf_key, pdf_bytes or (_MINIMAL_PDF + marker), "application/pdf")
    if sidecar_obj is not None:
        raw = (json.dumps(sidecar_obj) if isinstance(sidecar_obj, dict) else sidecar_obj)
        store.put_bytes(pdf_key[:-4] + ".json",
                        raw.encode() if isinstance(raw, str) else raw, "application/json")


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


def test_ingest_missing_sidecar_leaves_date_blank_never_our_time(tmp_path, canned_pdftotext):
    # A paper with NO sidecar (hence no MarketDesk publish date) must NOT be stamped
    # with our R2-upload / ingest time — that would post a stale backfill as brand-new
    # at the TOP of "latest". It ingests with a BLANK published_at (which sorts it to
    # the BOTTOM, below every dated paper) and is flagged needs_metadata.
    #
    # Regression guard: LocalStore.upload_time() returns a real mtime for the seeded
    # file, so if the ingest ever re-adds `fallback_published_at=upload_time` the
    # blank assertion below fails.
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"

    # A genuinely-dated paper, to prove the undated one sorts BELOW it (never above).
    _seed_pdf(store, "research_inbox/dated.pdf", {
        "title": "Real Dated Report", "institution": "Goldman Sachs",
        "published_at": "2026-07-20T09:00:00Z",
    })
    # No sidecar at all → no publish date recoverable.
    store.put_bytes("research_inbox/nosidecar.pdf", _MINIMAL_PDF, "application/pdf")

    summary = ingest_mod.run(store, corpus_path)
    assert summary["ingested"] == 2
    assert summary["needs_metadata"] == 1

    cat = catalog_mod.load(store)
    undated = [it for it in cat["items"] if it["institution"] == "Unknown"]
    assert len(undated) == 1
    assert undated[0]["published_at"] == ""      # NOT stamped with our upload/ingest clock
    assert undated[0]["needs_metadata"] is True
    # Sorts LAST — below the dated report, never at the top of "latest".
    assert cat["items"][0]["published_at"] == "2026-07-20T09:00:00Z"
    assert cat["items"][-1]["institution"] == "Unknown"


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
                       "needs_metadata": 0, "duplicate_bytes": 0,
                       "no_text_layer": 0, "text_unavailable": 0,
                       "catalog_bytes": b""}


def test_ingest_one_bad_pdf_does_not_abort_batch(tmp_path, canned_pdftotext, monkeypatch):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/good.pdf", {
        "title": "Good", "institution": "GS", "published_at": "2026-07-20"})
    _seed_pdf(store, "research_inbox/boom.pdf", {
        "title": "Boom", "institution": "GS", "published_at": "2026-07-21"})

    # Make corpus.upsert raise ONLY for the "Boom" doc to prove per-item isolation.
    real_upsert = corpus_mod.upsert

    def _flaky(conn, item, body, **kw):
        if item.get("title") == "Boom":
            raise RuntimeError("simulated corpus failure")
        return real_upsert(conn, item, body, **kw)

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
    # An all-lowercase multi-word title is a de-slugified stem with no other
    # tell — no date stamp, no language token, no id run. Ground truth for this
    # one: its own committed excerpt opens "An alternative model: China's
    # low-cost AI strategy", so the catalog row really is the filename.
    "invesco an alternative model chinas low cost ai strategy july 2026",
    "oils next move hinges on three variables",
])
def test_title_detects_filename_furniture(bad):
    assert title_mod.looks_filename_derived(bad) is True


@pytest.mark.parametrize("stem,want", [
    ("oils next move hinges on three variables", "Oils next move hinges on three variables"),
    ("invesco an alternative model chinas low cost ai strategy july 2026",
     "Invesco an alternative model chinas low cost AI strategy july 2026"),
])
def test_title_recases_an_all_lowercase_stem(stem, want):
    """Sentence-case + acronyms, so no <h1> ships starting lowercase."""
    assert title_mod.clean(stem) == want
    assert title_mod.clean(want) == want                      # idempotent


@pytest.mark.parametrize("good", [
    "US Econ Notes July 24",
    "iPhone demand tracker",                                  # lowercase FIRST letter is fine…
    "Semis and IT",                                           # …when something else is capitalised
    "on hold",                                                # under 3 words: never re-cased
])
def test_title_recase_never_touches_a_real_title(good):
    assert title_mod.clean(good) == good


@pytest.mark.parametrize("good", [
    "US Econ Notes July 24",                          # trailing day number
    "European Equities Week Ahead Jul 27 Jul 31",     # two of them
    "Recap 7 24 26",                                  # a date IS the title here
    "Invesco low cost AI strategy july 2026",         # trailing year
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


# ===========================================================================
# sidecar refresh: the upstream desk writes summary_points ASYNCHRONOUSLY
# ===========================================================================

def _dt(iso: str) -> datetime:
    """Pin the run clock — the refresh lookback window is measured against it."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def test_late_sidecar_summary_reaches_an_already_published_row(tmp_path, canned_pdftotext):
    """The defect this pass exists for: we routinely read the sidecar between the
    upstream's identity write and its summary write, and receipt-idempotency then
    froze the half-written copy forever ("Summary pending" on the public site)."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"

    # Phase 1 of the upstream write: identity present, summary not yet generated.
    _seed_pdf(store, "research_inbox/late.pdf", {
        "id": "marketdesk-late-000001", "title": "G10 FX Daily",
        "institution": "Scotiabank", "side": "sell",
        "published_at": "2026-07-28T00:47:05Z",
    })
    ingest_mod.run(store, corpus_path)
    row = catalog_mod.load(store)["items"][0]
    assert row["summary_points"] == []          # renders "Summary pending"

    # Phase 2: the desk's summarizer finishes and rewrites the SAME sidecar key.
    store.put_bytes("research_inbox/late.json", json.dumps({
        "id": "marketdesk-late-000001", "title": "G10 FX Daily",
        "institution": "Scotiabank", "side": "sell",
        "published_at": "2026-07-28T00:47:05Z",
        "summary_points": ["CAD firms into the BoC", "Front-end spreads compress"],
        "tags": ["fx"], "tickers": ["fxc"], "desk": "FX Strategy",
    }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T05:00:00Z"))
    assert summary["ingested"] == 0 and summary["skipped"] == 1   # nothing re-ingested
    assert summary["summaries_recovered"] == 1
    assert summary["sidecars_refreshed"] == 1

    row = catalog_mod.load(store)["items"][0]
    assert row["summary_points"] == ["CAD firms into the BoC",
                                     "Front-end spreads compress"]
    assert row["tags"] == ["fx"] and row["tickers"] == ["FXC"]    # coerced, upper-cased
    assert row["desk"] == "FX Strategy"

    # The corpus summary column is updated too, so FTS ranks on the new bullets
    # (weight 3) — the UPDATE trigger has to have re-synced the postings.
    conn = corpus_mod.open_db(corpus_path)
    hits = corpus_mod.search(conn, "front-end spreads compress")
    assert hits and hits[0]["id"] == "marketdesk-late-000001"
    conn.close()

    # Idempotent: a filled row leaves the candidate set, so the pass does not flap.
    again = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T06:00:00Z"))
    assert again["summaries_recovered"] == 0 and again["sidecars_refreshed"] == 0


def test_sidecar_refresh_never_overwrites_identity_when_it_fills_a_gap(tmp_path, canned_pdftotext):
    """Fill-only. A row that IS a candidate still only gains its missing fields —
    a repaired title must never regress to the raw sidecar string, and identity
    (institution/side/published_at) must never move under a published row."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/keep.pdf", {
        "id": "marketdesk-keep-000002", "title": "Rates Weekly Outlook en 1663849 1",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
    })
    ingest_mod.run(store, corpus_path)
    kept_title = catalog_mod.load(store)["items"][0]["title"]   # already title-repaired

    # Phase 2 arrives, but with DIFFERENT values for every field we already hold.
    store.put_bytes("research_inbox/keep.json", json.dumps({
        "id": "marketdesk-keep-000002", "title": "Rates Weekly Outlook en 1663849 1",
        "institution": "Nobody Bank", "side": "buy",
        "published_at": "1999-01-01T00:00:00Z",
        "summary_points": ["The genuine gap"], "tags": ["rates"], "pages": 9999,
    }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    row = catalog_mod.load(store)["items"][0]
    assert summary["summaries_recovered"] == 1
    assert row["summary_points"] == ["The genuine gap"]   # the gap filled
    assert row["tags"] == ["rates"]                       # filled opportunistically
    assert row["title"] == kept_title                     # repair NOT regressed
    assert row["institution"] == "UBS"                    # identity untouched
    assert row["published_at"] == "2026-07-28T09:00:00Z"
    assert row["side"] == "sell"
    assert row["pages"] != 9999                           # MEASURED (§5b) outranks


def test_a_row_with_bullets_is_never_re_fetched(tmp_path, canned_pdftotext):
    """Candidacy keys on summary_points ALONE. desk/tags/tickers have no producer
    and are empty on every document, so gating on all four would re-GET every
    in-window row every hour forever — the opposite of a self-quiescing pass."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # Bullets present; desk/tags/tickers absent — the shape of a real vault row.
    _seed_pdf(store, "research_inbox/done.pdf", {
        "id": "marketdesk-done-000008", "title": "Already Summarized",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
        "summary_points": ["Arrived with the PDF"],
    })
    ingest_mod.run(store, corpus_path)

    # A rewritten sidecar must not even be FETCHED, three runs running.
    store.put_bytes("research_inbox/done.json", json.dumps({
        "id": "marketdesk-done-000008", "title": "Already Summarized",
        "institution": "UBS", "published_at": "2026-07-28T09:00:00Z",
        "summary_points": ["Arrived with the PDF"], "tags": ["x"], "desk": "y",
    }).encode(), "application/json")
    for hour in (10, 11, 12):
        s = ingest_mod.run(store, corpus_path, now=_dt(f"2026-07-28T{hour}:00:00Z"))
        assert s["sidecars_checked"] == 0, f"re-fetched at hour {hour}"
    assert catalog_mod.load(store)["items"][0]["summary_points"] == ["Arrived with the PDF"]


def test_a_duplicate_re_drop_cannot_blank_a_recovered_summary(tmp_path, canned_pdftotext):
    """The refresh runs AFTER the ingest loop for this reason: upsert_item does a
    whole-ROW replace, so the same report re-dropped under a second filename with
    the SAME explicit sidecar id would otherwise overwrite a just-recovered
    summary with that second sidecar's still-empty one — shipping "Summary
    pending" while the run reported summaries_recovered=1, and flapping hourly."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/v1.pdf", {
        "id": "marketdesk-dup-000009", "title": "Re-dropped Report",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
    })
    ingest_mod.run(store, corpus_path)

    # v1's summarizer finishes...
    store.put_bytes("research_inbox/v1.json", json.dumps({
        "id": "marketdesk-dup-000009", "title": "Re-dropped Report",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
        "summary_points": ["Recovered from v1"],
    }).encode(), "application/json")
    # ...and in the SAME hour the desk re-drops the identical report under a new
    # filename, whose sidecar is back in the half-written phase-1 state.
    _seed_pdf(store, "research_inbox/v2.pdf", {
        "id": "marketdesk-dup-000009", "title": "Re-dropped Report",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
    })

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    row = catalog_mod.load(store)["items"][0]
    assert summary["ingested"] == 1                      # v2 really was ingested
    # The reported count and the shipped row must agree — that is the whole point.
    assert row["summary_points"] == ["Recovered from v1"]
    assert summary["summaries_recovered"] == 1
    conn = corpus_mod.open_db(corpus_path)
    stored = conn.execute("SELECT summary FROM documents WHERE doc_id=?",
                          ("marketdesk-dup-000009",)).fetchone()[0]
    assert stored == "Recovered from v1"                 # and search agrees
    conn.close()


def test_sidecar_refresh_survives_a_catalog_row_with_an_unhashable_id(tmp_path, canned_pdftotext):
    """The catalog is JSON reloaded from the store. An unhashable id must not raise
    out of the pass — that would abort the WHOLE hourly run before anything
    ingested, surfacing only as a logger line with no GitHub annotation."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/ok.pdf", {
        "id": "marketdesk-ok-000010", "title": "Fine Row",
        "institution": "UBS", "side": "sell", "published_at": "2026-07-28T09:00:00Z",
    })
    ingest_mod.run(store, corpus_path)
    cat = catalog_mod.load(store)
    cat["items"].append({"id": ["not", "hashable"], "title": "Broken",
                         "published_at": "2026-07-28T09:00:00Z"})
    catalog_mod.write(store, cat)
    store.put_bytes("research_inbox/ok.json", json.dumps({
        "id": "marketdesk-ok-000010", "title": "Fine Row", "institution": "UBS",
        "published_at": "2026-07-28T09:00:00Z", "summary_points": ["Still healed"],
    }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["summaries_recovered"] == 1           # the good row still healed
    rows = {str(it["id"]): it for it in catalog_mod.load(store)["items"]}
    assert rows["marketdesk-ok-000010"]["summary_points"] == ["Still healed"]


def test_a_non_iso_published_at_stays_in_refresh_scope(tmp_path, canned_pdftotext):
    """A bare [:10] slice on "07/28/2026" sorts BELOW any 2026-… cutoff, which
    would silently exclude the row from every future refresh. An unusable date is
    the same half-written state this pass exists for — it must stay IN scope."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/us.pdf", {
        "id": "marketdesk-us-000011", "title": "US Format Date",
        "institution": "UBS", "side": "sell", "published_at": "07/28/2026",
    })
    ingest_mod.run(store, corpus_path)
    store.put_bytes("research_inbox/us.json", json.dumps({
        "id": "marketdesk-us-000011", "title": "US Format Date", "institution": "UBS",
        "published_at": "07/28/2026", "summary_points": ["Reachable anyway"],
    }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["summaries_recovered"] == 1
    assert catalog_mod.load(store)["items"][0]["summary_points"] == ["Reachable anyway"]


def test_sidecar_refresh_skips_documents_past_the_lookback_window(tmp_path, canned_pdftotext):
    """A sidecar still empty after two weeks was never summarized upstream, not
    raced — polling it hourly forever would grow per-run GETs without bound."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # Two documents, identical except for age — so the window, and nothing else,
    # is what separates them. Without both, "checked == 0" would also pass against
    # a refresh pass that never ran at all.
    _seed_pdf(store, "research_inbox/old.pdf", {
        "id": "marketdesk-old-000003", "title": "Ancient Note",
        "institution": "UBS", "published_at": "2026-01-05T09:00:00Z",
    })
    _seed_pdf(store, "research_inbox/new.pdf", {
        "id": "marketdesk-new-000006", "title": "Fresh Note",
        "institution": "UBS", "published_at": "2026-07-27T09:00:00Z",
    }, marker=b"ALPHA")
    ingest_mod.run(store, corpus_path)
    for key, doc_id, pub in (("old", "marketdesk-old-000003", "2026-01-05T09:00:00Z"),
                             ("new", "marketdesk-new-000006", "2026-07-27T09:00:00Z")):
        store.put_bytes(f"research_inbox/{key}.json", json.dumps({
            "id": doc_id, "title": "Note", "institution": "UBS",
            "published_at": pub, "summary_points": ["Arrived late"],
        }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["sidecars_checked"] == 1          # the fresh one only
    assert summary["summaries_recovered"] == 1
    rows = {it["id"]: it for it in catalog_mod.load(store)["items"]}
    assert rows["marketdesk-new-000006"]["summary_points"] == ["Arrived late"]
    assert rows["marketdesk-old-000003"]["summary_points"] == []   # aged out


def test_sidecar_refresh_survives_a_sidecar_that_went_bad(tmp_path, canned_pdftotext):
    """One unreadable sidecar must not stop the pass — or the run."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/bad.pdf", {
        "id": "marketdesk-bad-000004", "title": "Bad Sidecar Later",
        "institution": "UBS", "published_at": "2026-07-28T09:00:00Z",
    })
    _seed_pdf(store, "research_inbox/good.pdf", {
        "id": "marketdesk-good-000005", "title": "Good Sidecar Later",
        "institution": "UBS", "published_at": "2026-07-28T09:30:00Z",
    })
    ingest_mod.run(store, corpus_path)
    store.put_bytes("research_inbox/bad.json", b"{not json at all", "application/json")
    store.put_bytes("research_inbox/good.json", json.dumps({
        "id": "marketdesk-good-000005", "title": "Good Sidecar Later",
        "institution": "UBS", "published_at": "2026-07-28T09:30:00Z",
        "summary_points": ["It arrived"],
    }).encode(), "application/json")

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["summaries_recovered"] == 1       # the good one still healed
    rows = {it["id"]: it for it in catalog_mod.load(store)["items"]}
    assert rows["marketdesk-good-000005"]["summary_points"] == ["It arrived"]
    assert rows["marketdesk-bad-000004"]["summary_points"] == []


def test_sidecar_refresh_cap_is_announced_not_silent(tmp_path, canned_pdftotext, monkeypatch, capsys):
    """A bound that truncates coverage must SAY so — a silent cap reads downstream
    as 'every incomplete row was re-checked', which is the opposite of the truth."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    for i in range(3):
        _seed_pdf(store, f"research_inbox/c{i}.pdf", {
            "id": f"marketdesk-cap-00000{i}", "title": f"Capped {i}",
            "institution": "UBS", "published_at": f"2026-07-2{i+5}T09:00:00Z",
        }, marker=f"cap{i}".encode())
    ingest_mod.run(store, corpus_path)
    for i in range(3):
        store.put_bytes(f"research_inbox/c{i}.json", json.dumps({
            "id": f"marketdesk-cap-00000{i}", "title": f"Capped {i}",
            "institution": "UBS", "published_at": f"2026-07-2{i+5}T09:00:00Z",
            "summary_points": [f"bullet {i}"],
        }).encode(), "application/json")

    monkeypatch.setattr(ingest_mod, "REFRESH_MAX", 2)
    capsys.readouterr()
    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    out = capsys.readouterr().out

    assert summary["sidecars_capped"] == 1
    assert summary["sidecars_checked"] == 2          # the cap bounds the FETCH path
    # GitHub only parses a workflow command when "::" STARTS the line.
    assert any(ln.startswith("::warning") and "capped at 2" in ln
               for ln in out.splitlines())
    # Newest-first, so the row dropped is the OLDEST — least likely to be mid-summary.
    rows = {it["id"]: it for it in catalog_mod.load(store)["items"]}
    assert rows["marketdesk-cap-000000"]["summary_points"] == []
    assert rows["marketdesk-cap-000002"]["summary_points"] == ["bullet 2"]


def test_the_cap_keeps_undated_rows_the_ones_it_exists_for(tmp_path, canned_pdftotext, monkeypatch):
    """_reindex sorts blank published_at LAST, but those are exactly the
    half-written rows the refresh exists for — a naive head-slice would discard
    the highest-priority candidates first."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    seeds = [("d0", "2026-07-26T09:00:00Z"), ("d1", "2026-07-27T09:00:00Z"), ("un", "")]
    for n, pub in seeds:
        _seed_pdf(store, f"research_inbox/{n}.pdf", {
            "id": f"marketdesk-{n}-x", "title": f"Row {n}",
            "institution": "UBS", "published_at": pub,
        }, marker=n.encode())
    ingest_mod.run(store, corpus_path)
    for n, pub in seeds:
        store.put_bytes(f"research_inbox/{n}.json", json.dumps({
            "id": f"marketdesk-{n}-x", "title": f"Row {n}", "institution": "UBS",
            "published_at": pub, "summary_points": [f"{n} bullet"],
        }).encode(), "application/json")

    monkeypatch.setattr(ingest_mod, "REFRESH_MAX", 1)
    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["sidecars_capped"] == 2
    rows = {it["id"]: it for it in catalog_mod.load(store)["items"]}
    assert rows["marketdesk-un-x"]["summary_points"] == ["un bullet"]   # kept


def test_corpus_summary_resync_heals_a_failed_corpus_publish(tmp_path, canned_pdftotext):
    """run() writes the catalog BEFORE publishing the corpus, so a failed publish
    strands bullets in the catalog with a blank corpus summary — and that row is
    no longer a refresh candidate, so search would rank it on stale text forever."""
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    # Every refresh field filled, so the row is NOT a refresh candidate — the
    # resync is then the only path that can reach it.
    _seed_pdf(store, "research_inbox/skew.pdf", {
        "id": "marketdesk-skew-000007", "title": "Skewed Row",
        "institution": "UBS", "published_at": "2026-07-28T09:00:00Z",
        "summary_points": ["Only in the catalog"],
        "tags": ["macro"], "tickers": ["SPY"], "desk": "Rates",
    })
    ingest_mod.run(store, corpus_path)

    # Reproduce the skew: catalog keeps the bullets, the corpus summary is blank.
    conn = corpus_mod.open_db(corpus_path)
    conn.execute("UPDATE documents SET summary='' WHERE doc_id=?",
                 ("marketdesk-skew-000007",))
    conn.commit(); conn.close()
    ingest_mod.publish_corpus(store, corpus_path)   # the store copy is the truth
    assert catalog_mod.load(store)["items"][0]["summary_points"] == ["Only in the catalog"]

    summary = ingest_mod.run(store, corpus_path, now=_dt("2026-07-28T10:00:00Z"))
    assert summary["sidecars_checked"] == 0         # not a refresh candidate — no GET
    # Pin the key the ::warning reads. Five dead-annotation regressions shipped
    # here (#3487/#3515/#3562/#3563/#3570) because nothing asserted the counter.
    assert summary["summaries_resynced"] == 1
    conn = corpus_mod.open_db(corpus_path)
    stored = conn.execute("SELECT summary FROM documents WHERE doc_id=?",
                          ("marketdesk-skew-000007",)).fetchone()[0]
    assert stored == "Only in the catalog"
    hits = corpus_mod.search(conn, "Only in the catalog")
    assert hits and hits[0]["id"] == "marketdesk-skew-000007"
    conn.close()


def test_corpus_summary_text_is_the_single_definition(tmp_path):
    """upsert() and the refresh pass BOTH write the summary column; a second join
    in either place would give the same bullets two different searchable forms."""
    item = {"id": "x", "summary_points": ["one", "two"]}
    assert corpus_mod.summary_text(item) == "one • two"
    assert corpus_mod.summary_text({"id": "x"}) == ""
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    corpus_mod.upsert(conn, item, "body")
    stored = conn.execute("SELECT summary FROM documents WHERE doc_id='x'").fetchone()[0]
    assert stored == corpus_mod.summary_text(item)
    conn.close()


# ===========================================================================
# probe: deterministic facts measured from the bytes (RV W1-A)
# ===========================================================================

def test_probe_hash_and_size_always_present():
    facts = probe_mod.probe(_MINIMAL_PDF)
    assert len(facts["content_sha256"]) == 64
    assert facts["byte_size"] == len(_MINIMAL_PDF)


def test_probe_hash_is_stable_and_content_addressed():
    a = probe_mod.probe(_MINIMAL_PDF)["content_sha256"]
    b = probe_mod.probe(_MINIMAL_PDF)["content_sha256"]
    c = probe_mod.probe(_MINIMAL_PDF + b"x")["content_sha256"]
    assert a == b and a != c


@_needs_measured
def test_probe_reads_the_page_count():
    assert probe_mod.probe(_REAL_PDF.read_bytes())["pages"] == _REAL_PDF_PAGES


def test_probe_garbage_bytes_degrade_to_unknown_not_zero():
    """A page count we could not measure must be None — never 0.

    A zero would read downstream as "a zero-page document", which is a claim we
    have not earned; None is the honest "not measured".
    """
    facts = probe_mod.probe(b"this is definitely not a pdf")
    assert facts["pages"] is None
    assert facts["content_sha256"]            # still hashed
    assert facts["pdf_producer"] == ""


def test_probe_empty_bytes_is_all_unknown():
    facts = probe_mod.probe(b"")
    assert facts["pages"] is None
    assert facts["content_sha256"] == ""
    assert facts["byte_size"] == 0


@pytest.mark.parametrize("raw,want", [
    ("D:20260721185916+08'00'", "2026-07-21T18:59:16+08:00"),
    ("D:20260721185916Z",       "2026-07-21T18:59:16+00:00"),
    ("D:20260721185916",        "2026-07-21T18:59:16"),
    ("D:2026",                  "2026-01-01T00:00:00"),
    ("2026-07-21T18:59:16+08",  "2026-07-21T18:59:16+08:00"),
    ("",                        ""),
    ("not a date",              ""),
    ("D:garbage",               ""),
])
def test_pdf_date_to_iso(raw, want):
    assert probe_mod._pdf_date_to_iso(raw) == want


def test_text_facts_distinguishes_unavailable_from_absent():
    """The four text-layer states must stay distinct.

    ``extract_pdf_text() or ""`` collapses a BROKEN HOST (None) into an
    image-only DOCUMENT (""). One is fixed by installing poppler, the other by
    getting a better PDF — reporting them as the same thing hides the former.
    """
    assert probe_mod.text_facts(None)["text_layer"] == "unavailable"
    assert probe_mod.text_facts(None)["char_count"] is None
    assert probe_mod.text_facts("")["text_layer"] == "none"
    assert probe_mod.text_facts("")["char_count"] == 0


def test_text_facts_density_is_per_page_when_pages_known():
    body = "x" * 1000
    # 1000 chars over 1 page is a real text layer; over 20 pages it is not.
    assert probe_mod.text_facts(body, 1)["text_layer"] == "full"
    assert probe_mod.text_facts(body, 20)["text_layer"] == "thin"


def test_text_facts_falls_back_to_absolute_floor_without_pages():
    assert probe_mod.text_facts("x" * 100, None)["text_layer"] == "thin"
    assert probe_mod.text_facts("x" * 5000, None)["text_layer"] == "full"


def test_text_facts_counts_words():
    f = probe_mod.text_facts("alpha beta  gamma\ndelta")
    assert f["word_count"] == 4
    assert f["char_count"] == len("alpha beta  gamma\ndelta")


def test_first_page_splits_on_form_feed_and_caps():
    body = "cover page text\fpage two\fpage three"
    assert probe_mod.first_page(body) == "cover page text"
    assert probe_mod.first_page(body, limit=5) == "cover"
    assert probe_mod.first_page("") == ""
    assert probe_mod.first_page(None) == ""


def test_first_page_of_single_page_body_is_the_whole_body():
    assert probe_mod.first_page("no form feeds here") == "no form feeds here"


# ===========================================================================
# corpus: v1 -> v2 migration (the restored-from-R2 path)
# ===========================================================================

# The FROZEN v1 schema, written out longhand on purpose: this is the shape of the
# corpus.sqlite already published to R2, which _restore_corpus pulls down at the
# start of every run. Deriving it from the current module would make the test
# tautological — it must keep describing HISTORY, not today's code.
_V1_DDL = """
CREATE TABLE documents (
    rowid          INTEGER PRIMARY KEY,
    doc_id         TEXT UNIQUE NOT NULL,
    title          TEXT,
    summary        TEXT,
    institution    TEXT,
    side           TEXT,
    published_at   TEXT,
    published_date TEXT,
    body           TEXT
);
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, summary, body, institution, content=''
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO meta(key,value) VALUES('schema_version','1');
"""


def _write_v1_corpus(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_V1_DDL)
    conn.commit()
    conn.close()


def test_v1_corpus_migrates_and_still_ingests(tmp_path):
    """A v1 corpus restored from R2 must accept a v2 upsert.

    Regression for the failure mode this migration exists to prevent: with the new
    columns declared ONLY in the CREATE TABLE, ``CREATE TABLE IF NOT EXISTS`` would
    no-op against the restored v1 file, every INSERT naming a v2 column would raise
    OperationalError inside _ingest_one's catch-all, and the run would report every
    single document as "failed" with no other symptom.
    """
    p = tmp_path / "corpus.sqlite"
    _write_v1_corpus(p)

    conn = corpus_mod.open_db(p)
    cols = corpus_mod._existing_columns(conn)
    for name, _decl in corpus_mod._V2_COLUMNS:
        assert name in cols, f"{name} missing after migration"

    corpus_mod.upsert(conn, {"id": "d1", "title": "Rates", "institution": "GS",
                             "published_at": "2026-07-21", "pages": 12},
                      "body text about rates",
                      facts={"content_sha256": "abc", "pages": 12,
                             "char_count": 21, "text_layer": "full"})
    row = conn.execute("SELECT pages, content_sha256, text_layer FROM documents "
                       "WHERE doc_id='d1'").fetchone()
    assert (row[0], row[1], row[2]) == (12, "abc", "full")
    conn.close()


def test_v1_migration_preserves_existing_rows_and_search(tmp_path):
    """Migrating must not lose the archive or break the FTS postings."""
    p = tmp_path / "corpus.sqlite"
    _write_v1_corpus(p)
    conn = sqlite3.connect(str(p))
    conn.execute("INSERT INTO documents(doc_id,title,summary,institution,side,"
                 "published_at,published_date,body) VALUES(?,?,?,?,?,?,?,?)",
                 ("old-1", "Legacy Report", "s", "UBS", "sell",
                  "2026-01-02", "2026-01-02", "hyperscaler capacity"))
    conn.execute("INSERT INTO documents_fts(rowid,title,summary,body,institution) "
                 "VALUES((SELECT rowid FROM documents WHERE doc_id='old-1'),"
                 "'Legacy Report','s','hyperscaler capacity','UBS')")
    conn.commit()
    conn.close()

    conn = corpus_mod.open_db(p)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    hits = corpus_mod.search(conn, "hyperscaler")
    assert [h["id"] for h in hits] == ["old-1"]
    # The pre-existing row's new columns are NULL — honest "never measured".
    assert conn.execute("SELECT pages FROM documents WHERE doc_id='old-1'"
                        ).fetchone()[0] is None
    conn.close()


def test_migration_is_idempotent(tmp_path):
    p = tmp_path / "corpus.sqlite"
    _write_v1_corpus(p)
    conn = corpus_mod.open_db(p)
    assert corpus_mod._migrate(conn) == []      # second pass adds nothing
    conn.close()
    conn = corpus_mod.open_db(p)                # reopen: still nothing to do
    assert corpus_mod._migrate(conn) == []
    conn.close()


def test_fresh_and_migrated_corpora_have_identical_columns(tmp_path):
    """One declaration site, two entry paths — they must converge exactly."""
    fresh = corpus_mod.open_db(tmp_path / "fresh.sqlite")
    fresh_cols = corpus_mod._existing_columns(fresh)
    fresh.close()

    old = tmp_path / "old.sqlite"
    _write_v1_corpus(old)
    migrated = corpus_mod.open_db(old)
    migrated_cols = corpus_mod._existing_columns(migrated)
    migrated.close()

    assert fresh_cols == migrated_cols


def test_open_db_stamps_schema_version_2(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    got = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
    assert got == "2"
    conn.close()


def test_first_page_text_is_deliberately_not_a_column(tmp_path):
    """Page 1 lives inside ``body`` (tail-truncated), so a column would duplicate it."""
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    assert "first_page_text" not in corpus_mod._existing_columns(conn)
    conn.close()


def test_measured_facts_are_not_in_the_fts_index(tmp_path):
    """The v2 columns are metadata; indexing them would reweight every BM25 score."""
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    corpus_mod.upsert(conn, {"id": "d1", "title": "T", "institution": "GS",
                             "published_at": "2026-07-21"}, "body",
                      facts={"pdf_producer": "Acrobat Distiller", "pages": 3})
    # The producer string is stored but must not be searchable.
    assert corpus_mod.search(conn, "Distiller") == []
    row = conn.execute("SELECT pdf_producer FROM documents WHERE doc_id='d1'").fetchone()
    assert row[0] == "Acrobat Distiller"
    conn.close()


def test_upsert_without_facts_leaves_measured_columns_null(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    corpus_mod.upsert(conn, {"id": "d1", "title": "T", "institution": "GS",
                             "published_at": "2026-07-21"}, "body")
    row = conn.execute("SELECT pages, content_sha256 FROM documents "
                       "WHERE doc_id='d1'").fetchone()
    assert row[0] is None and row[1] is None
    conn.close()


def test_sha_index_maps_hash_to_doc_id(tmp_path):
    conn = corpus_mod.open_db(tmp_path / "c.sqlite")
    corpus_mod.upsert(conn, {"id": "d1", "title": "A", "institution": "GS",
                             "published_at": "2026-07-21"}, "b",
                      facts={"content_sha256": "hash-a"})
    corpus_mod.upsert(conn, {"id": "d2", "title": "B", "institution": "GS",
                             "published_at": "2026-07-22"}, "b",
                      facts={"content_sha256": ""})     # unhashed rows excluded
    assert corpus_mod.sha_index(conn) == {"hash-a": "d1"}
    conn.close()


def test_sha_index_is_empty_on_a_pre_v2_corpus(tmp_path):
    p = tmp_path / "corpus.sqlite"
    _write_v1_corpus(p)
    conn = sqlite3.connect(str(p))
    assert corpus_mod.sha_index(conn) == {}      # no column, no crash
    conn.close()


# ===========================================================================
# catalog: per-field coverage (the anti-vacuous-green tripwire)
# ===========================================================================

def _cat(items):
    return {"schema": "research_vault.catalog.v1", "count": len(items),
            "institutions": [], "items": items}


def test_coverage_counts_populated_fields():
    cov = catalog_mod.coverage(_cat([
        {"id": "a", "pages": 12, "tags": ["ai"], "desk": "", "tickers": [],
         "summary_points": ["x"]},
        {"id": "b", "pages": None, "tags": [], "desk": "Rates", "tickers": [],
         "summary_points": []},
    ]))
    assert cov["pages"] == {"filled": 1, "total": 2, "pct": 50.0}
    assert cov["desk"]["filled"] == 1
    assert cov["tickers"]["filled"] == 0
    assert cov["summary_points"]["filled"] == 1


def test_coverage_flags_a_field_no_producer_ever_fills():
    """The exact state that hid behind a green needs_metadata for 60 documents."""
    cov = catalog_mod.coverage(_cat([
        {"id": str(i), "pages": None, "tags": [], "tickers": [], "desk": "",
         "summary_points": ["ok"]} for i in range(60)
    ]))
    _lines, dead = catalog_mod.coverage_lines(cov)
    assert set(dead) == {"pages", "tags", "tickers", "desk"}
    assert "summary_points" not in dead


def test_coverage_of_an_empty_catalog_is_zero_not_an_error():
    cov = catalog_mod.coverage(_cat([]))
    assert cov["pages"] == {"filled": 0, "total": 0, "pct": 0.0}
    _lines, dead = catalog_mod.coverage_lines(cov)
    assert dead == []          # nothing to fill yet is not a dead field


def test_coverage_excludes_defaulted_and_boolean_fields():
    """``language`` defaults to "en" and the booleans mean something when False.

    Counting either would report health the pipeline has not demonstrated.
    """
    assert "language" not in catalog_mod._COVERAGE_FIELDS
    assert "top_pick" not in catalog_mod._COVERAGE_FIELDS
    assert "needs_metadata" not in catalog_mod._COVERAGE_FIELDS


def test_coverage_ignores_non_dict_items():
    cov = catalog_mod.coverage({"items": [{"id": "a", "pages": 3}, "junk", None]})
    assert cov["pages"]["total"] == 1


def test_catalog_item_carries_language():
    cat = catalog_mod.upsert_item(catalog_mod.empty(), {
        "id": "d1", "title": "T", "institution": "GS", "side": "sell",
        "published_at": "2026-07-21", "language": "zh",
    })
    assert cat["items"][0]["language"] == "zh"


def test_builder_mirrors_the_catalog_item_fields():
    """The SSR bake projects its own copy of the field list — they must match."""
    import importlib

    builder = importlib.import_module("scripts.build_research_vault")
    assert builder._ITEM_FIELDS == catalog_mod._ITEM_FIELDS


# ===========================================================================
# ingest: measured facts win over sidecar claims; duplicates reported
# ===========================================================================

@_needs_measured
def test_ingest_measures_pages_and_overrides_the_sidecar_claim(tmp_path, canned_pdftotext):
    """``pages`` was null on every document ever ingested because the ingester only
    ever read the sidecar's value. A local measurement beats an upstream promise."""
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Rates Outlook", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z", "pages": 999,   # a false claim
    }, pdf_bytes=_REAL_PDF.read_bytes())
    ingest_mod.run(store, tmp_path / "corpus.sqlite")
    item = catalog_mod.load(store)["items"][0]
    assert item["pages"] == _REAL_PDF_PAGES     # what the PDF actually contains


def test_ingest_keeps_the_sidecar_pages_when_measurement_fails(tmp_path, canned_pdftotext,
                                                              monkeypatch):
    """An unmeasurable PDF must not blank a value the sidecar did supply."""
    monkeypatch.setattr(probe_mod, "probe", lambda b: {
        "content_sha256": "x" * 64, "byte_size": len(b), "pages": None,
        "encrypted": None, "pdf_creator": "", "pdf_producer": "",
        "pdf_created_at": "", "pdf_modified_at": "",
    })
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Rates Outlook", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z", "pages": 42,
    })
    ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert catalog_mod.load(store)["items"][0]["pages"] == 42


@_needs_measured
def test_ingest_records_measured_facts_in_the_corpus(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    corpus_path = tmp_path / "corpus.sqlite"
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Rates Outlook", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z"}, pdf_bytes=_REAL_PDF.read_bytes())
    ingest_mod.run(store, corpus_path)

    conn = sqlite3.connect(str(corpus_path))
    row = conn.execute("SELECT content_sha256, byte_size, pages, char_count, "
                       "text_layer FROM documents").fetchone()
    conn.close()
    assert len(row[0]) == 64          # hashed
    assert row[1] > 0                 # sized
    assert row[2] == _REAL_PDF_PAGES  # measured page count
    assert row[3] > 0                 # body chars counted
    assert row[4] in ("full", "thin")


def test_ingest_reports_duplicate_bytes_without_skipping_them(tmp_path, canned_pdftotext):
    """The same PDF under two source keys is two objects to the receipt ledger.

    We surface it, but must NOT skip on a hash match: identical bytes legitimately
    re-arrive with a CORRECTED sidecar, and skipping would freeze the original bad
    metadata in place forever (receipts make re-ingestion the only repair path).
    """
    store = LocalStore(tmp_path / "store")
    for key, title in (("research_inbox/a.pdf", "First Drop"),
                       ("research_inbox/b.pdf", "Second Drop")):
        _seed_pdf(store, key, {"title": title, "institution": "GS",
                               "published_at": "2026-07-21T10:00:00Z"})

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["ingested"] == 2            # both kept
    assert summary["duplicate_bytes"] == 1     # and the collision is reported
    assert catalog_mod.load(store)["count"] == 2


def test_ingest_counts_a_missing_text_layer(tmp_path, monkeypatch):
    """An image-only PDF is invisible to body search and nothing else says so."""
    monkeypatch.setattr(ingest_mod, "extract_pdf_text", lambda b: "")
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/scan.pdf", {
        "title": "Scanned Deck", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z"})

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["ingested"] == 1            # still ingested, never dropped
    assert summary["no_text_layer"] == 1


def test_ingest_separates_a_broken_extractor_from_an_empty_pdf(tmp_path, monkeypatch):
    """pdftotext missing is a HOST fault and must not be filed as a document one."""
    monkeypatch.setattr(ingest_mod, "extract_pdf_text", lambda b: None)
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Report", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z"})

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["text_unavailable"] == 1
    assert summary["no_text_layer"] == 0


@_needs_measured
def test_ingest_receipt_carries_the_measured_evidence(tmp_path, canned_pdftotext):
    """Receipts are the only per-document record never regenerated from scratch."""
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Rates Outlook", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z"}, pdf_bytes=_REAL_PDF.read_bytes())
    ingest_mod.run(store, tmp_path / "corpus.sqlite")

    keys = [k for k in store.list_prefix("research_inbox/_processed/")
            if k.endswith(".json")]
    receipt = json.loads(store.get_bytes(keys[0]))
    assert len(receipt["content_sha256"]) == 64
    assert receipt["pages"] == _REAL_PDF_PAGES
    assert receipt["byte_size"] > 0
    assert receipt["text_layer"] in ("full", "thin")


@_needs_measured
def test_ingest_summary_reports_coverage(tmp_path, canned_pdftotext):
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/rep.pdf", {
        "title": "Rates Outlook", "institution": "GS",
        "published_at": "2026-07-21T10:00:00Z", "tags": ["rates"]},
        pdf_bytes=_REAL_PDF.read_bytes())
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    cov = summary["coverage"]
    assert cov["pages"]["filled"] == 1         # measured, so no longer dead
    assert cov["tags"]["filled"] == 1
    assert cov["tickers"]["filled"] == 0


# The hourly ingest lane installs only boto3+pyyaml, so pypdf (a SOFT dep declared
# for the download watermark) is ABSENT there and production actually runs on the
# poppler `pdfinfo` rung. These two tests cover that path against a real PDF.
@_needs_pdfinfo
def test_probe_pdfinfo_rung_reads_a_real_pdf(monkeypatch):
    """With pypdf unavailable — the hourly lane's real configuration."""
    monkeypatch.setattr(probe_mod, "_probe_pypdf", lambda b: {})
    facts = probe_mod.probe(_REAL_PDF.read_bytes())
    assert facts["pages"] and facts["pages"] > 1
    assert facts["pdf_producer"]                       # Info dict recovered
    assert facts["pdf_created_at"].startswith("20")    # ISO, not the locale form
    assert facts["encrypted"] is False


@_needs_both_rungs
def test_probe_rungs_agree_on_the_page_count():
    """pypdf and pdfinfo must not disagree about something this basic."""
    data = _REAL_PDF.read_bytes()
    assert probe_mod._probe_pypdf(data).get("pages") == \
        probe_mod._probe_pdfinfo(data).get("pages")
