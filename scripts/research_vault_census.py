"""scripts/research_vault_census.py — READ-ONLY id-set census of the live vault.

The correction audit for Research Vault Wave 4. Builds the four id sets the wave's
invariants are stated over and reports every mismatch between them:

    CATALOG_IDS    ids the public catalog admits      (research_vault/catalog.json)
    VAULT_PDF_IDS  promoted canonical PDFs            (research_vault/<id>.pdf)
    CORPUS_IDS     searchable rows                    (research_vault/corpus.sqlite)
    RECEIPTED_IDS  documents marked processed         (research_inbox/_processed/)

Each mismatch direction means something different, and the point of the census is
to CLASSIFY them, never to force the sets equal:

  catalog − pdf     user-visible DEAD reports. A reader can open these and get a
                    404. Repair from source, or withdraw from availability.
  receipt − catalog STRANDED already-processed reports. A receipt makes a document
                    unre-ingestable, so these can only come back by deliberate
                    recovery. Distinguish historical failed publishes from
                    intentional deletions and superseded duplicates before acting.
  corpus − catalog  publication-AHEAD rows. Legitimate for the moments between the
                    corpus put and the catalog put (the corpus publishes first by
                    design); a persistent one is a failed catalog publish. These
                    must not be user-visible, which the serving-tier catalog
                    membership filter now enforces for every tier.
  catalog − corpus  browsable but NOT searchable. Repair the corpus row.

Also records both ``generated_at`` values — R2's and the committed repo mirror's.
The mirror may LAG; it must never be independently NEWER, because that would mean
it advanced past a canonical publish that failed (Wave 4 freeze §B).

STRICTLY READ-ONLY: this script never puts, deletes, or mutates a single object,
in the store or in the repo. Recovery is an operator action taken against its
output, never something a census performs.

Usage:
    python -m scripts.research_vault_census                     # live R2
    python -m scripts.research_vault_census --local /tmp/rv     # a local store
    python -m scripts.research_vault_census --json out.json     # machine-readable

Exit 0 when the census completed (mismatches are REPORTED, not failures — an
unexplained mismatch is for a human to adjudicate). Exit 1 only when the census
could not be taken at all: no store, or an unreadable catalog.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("research_vault_census")

_REPO_MIRROR = Path(__file__).resolve().parent.parent / "data" / "research_vault" / "catalog.json"

# How many example ids to print per mismatch bucket. The full sets go to --json.
_SAMPLE = 12


def _catalog_ids(store) -> tuple[set[str], dict]:
    """Admitted ids + catalog metadata. Raises CatalogUnavailable if unreadable."""
    from engine.research_vault import catalog as catalog_mod

    # check_items=False: the census must be able to REPORT on a catalog carrying a
    # malformed row, not refuse to run because of one. A row without a usable id
    # is counted separately below rather than silently dropped.
    cat = catalog_mod.read_strict(store, check_future_clock=False, check_items=False)
    ids: set[str] = set()
    unusable = 0
    for item in cat.get("items") or []:
        doc_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(doc_id, str) and doc_id.strip():
            ids.add(doc_id)
        else:
            unusable += 1
    meta = {
        "generated_at": cat.get("generated_at"),
        "declared_count": cat.get("count"),
        "item_rows": len(cat.get("items") or []),
        "unusable_id_rows": unusable,
    }
    return ids, meta


def _vault_pdf_ids(store) -> set[str]:
    from engine.research_vault import ingest as ingest_mod

    out = set()
    for key in store.list_prefix(ingest_mod.VAULT_PREFIX):
        if key.lower().endswith(".pdf"):
            out.add(Path(key).stem)
    return out


def _receipted(store) -> tuple[set[str], dict[str, str]]:
    """Receipted ids + the ``{doc_id: source pdf_key}`` map recovery needs.

    The source mapping is the ONLY route from a published row back to the inbox
    object it came from, so it is what makes a stranded row deterministically
    recoverable rather than a guess.
    """
    from engine.research_vault import ingest as ingest_mod

    ids: set[str] = set()
    sources: dict[str, str] = {}
    for key in store.list_prefix(ingest_mod.PROCESSED_PREFIX):
        if not key.endswith(".json"):
            continue
        doc_id = Path(key).stem
        ids.add(doc_id)
        raw = store.get_bytes(key)
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:  # noqa: BLE001 — an unreadable receipt still counts as one
            continue
        if isinstance(rec, dict) and rec.get("pdf_key"):
            sources[doc_id] = str(rec["pdf_key"])
    return ids, sources


def _corpus_ids(store) -> tuple[set[str], int]:
    """Searchable ids from the published corpus, read from a temp copy."""
    from engine.research_vault import ingest as ingest_mod

    data = store.get_bytes(ingest_mod.CORPUS_KEY)
    if not data:
        return set(), 0
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "corpus.sqlite"
        path.write_bytes(data)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = [r[0] for r in conn.execute("SELECT doc_id FROM documents")]
        finally:
            conn.close()
    return {r for r in rows if r}, len(rows)


def _mirror_meta() -> dict:
    if not _REPO_MIRROR.is_file():
        return {"present": False}
    try:
        obj = json.loads(_REPO_MIRROR.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"present": True, "error": str(exc)}
    items = obj.get("items") or []
    return {
        "present": True,
        "generated_at": obj.get("generated_at"),
        "declared_count": obj.get("count"),
        "item_rows": len(items),
        "ids": {it.get("id") for it in items if isinstance(it, dict) and it.get("id")},
    }


def _sample(ids: set[str]) -> list[str]:
    return sorted(ids)[:_SAMPLE]


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description="Research Vault id-set census (read-only)")
    ap.add_argument("--local", metavar="DIR", help="census a local store instead of R2")
    ap.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    a = ap.parse_args()

    from engine.research_vault import catalog as catalog_mod
    from engine.research_vault import r2_store

    store = r2_store.build_store(local_dir=a.local)
    if store is None:
        print("::error title=research_vault_census::no store configured "
              "(RESEARCH_LOCAL_STORE / --local / R2_RESEARCH_BUCKET + creds)",
              flush=True)
        return 1

    try:
        catalog_ids, catalog_meta = _catalog_ids(store)
    except catalog_mod.CatalogUnavailable as exc:
        print(f"::error title=research_vault_census::authoritative catalog is "
              f"UNAVAILABLE ({exc.reason}: {exc.detail}) — the census cannot be "
              f"taken against it. This is itself the Defect 2 condition; recover "
              f"the catalog before auditing.", flush=True)
        return 1

    pdf_ids = _vault_pdf_ids(store)
    receipt_ids, receipt_sources = _receipted(store)
    corpus_ids, corpus_rows = _corpus_ids(store)
    mirror = _mirror_meta()

    catalog_minus_pdf = catalog_ids - pdf_ids
    receipt_minus_catalog = receipt_ids - catalog_ids
    corpus_minus_catalog = corpus_ids - catalog_ids
    catalog_minus_corpus = catalog_ids - corpus_ids
    pdf_minus_catalog = pdf_ids - catalog_ids

    report = {
        "schema": "research_vault.census.v1",
        "catalog": {**catalog_meta, "id_count": len(catalog_ids)},
        "vault_pdfs": len(pdf_ids),
        "corpus": {"id_count": len(corpus_ids), "rows": corpus_rows},
        "receipts": len(receipt_ids),
        "repo_mirror": {k: v for k, v in mirror.items() if k != "ids"},
        "mismatches": {
            "catalog_minus_pdf": sorted(catalog_minus_pdf),
            "receipt_minus_catalog": sorted(receipt_minus_catalog),
            "corpus_minus_catalog": sorted(corpus_minus_catalog),
            "catalog_minus_corpus": sorted(catalog_minus_corpus),
            "pdf_minus_catalog": sorted(pdf_minus_catalog),
        },
        # The source mapping for exactly the rows an operator may need to recover.
        "recovery_sources": {
            doc_id: receipt_sources.get(doc_id, "")
            for doc_id in sorted(receipt_minus_catalog)
        },
    }
    if mirror.get("present") and mirror.get("ids") is not None:
        report["repo_mirror"]["id_count"] = len(mirror["ids"])
        report["repo_mirror"]["mirror_minus_catalog"] = sorted(mirror["ids"] - catalog_ids)
        report["repo_mirror"]["catalog_minus_mirror"] = sorted(catalog_ids - mirror["ids"])

    print("=" * 72)
    print("RESEARCH VAULT ID-SET CENSUS (read-only)")
    print("=" * 72)
    print(f"  catalog generated_at : {catalog_meta['generated_at']}")
    print(f"  catalog ids          : {len(catalog_ids)} "
          f"(declared count={catalog_meta['declared_count']}, "
          f"rows={catalog_meta['item_rows']}, "
          f"unusable-id rows={catalog_meta['unusable_id_rows']})")
    print(f"  promoted vault PDFs  : {len(pdf_ids)}")
    print(f"  corpus ids           : {len(corpus_ids)} (rows={corpus_rows})")
    print(f"  receipts             : {len(receipt_ids)}")
    print(f"  repo mirror          : generated_at={mirror.get('generated_at')} "
          f"count={mirror.get('declared_count')}")
    print("-" * 72)
    for label, ids, meaning in (
        ("catalog − pdf   ", catalog_minus_pdf,
         "USER-VISIBLE DEAD REPORTS (open -> 404)"),
        ("receipt − catalog", receipt_minus_catalog,
         "stranded processed reports (unre-ingestable without recovery)"),
        ("corpus − catalog ", corpus_minus_catalog,
         "publication-ahead rows (must not be user-visible)"),
        ("catalog − corpus ", catalog_minus_corpus,
         "browsable but NOT searchable"),
        ("pdf − catalog    ", pdf_minus_catalog,
         "promoted objects the catalog does not admit"),
    ):
        print(f"  {label}: {len(ids):5d}   {meaning}")
        if ids:
            print(f"      e.g. {', '.join(_sample(ids))}"
                  f"{' …' if len(ids) > _SAMPLE else ''}")
    print("=" * 72)

    # The one direction that is a HARD invariant violation rather than a finding:
    # the repo mirror must never be independently newer than the R2 catalog.
    try:
        if mirror.get("generated_at") and catalog_meta.get("generated_at"):
            mirror_at = catalog_mod.parse_generated_at(mirror["generated_at"])
            r2_at = catalog_mod.parse_generated_at(catalog_meta["generated_at"])
            if mirror_at > r2_at:
                print(f"::error title=research_vault_census::repo mirror "
                      f"({mirror_at.isoformat()}) is NEWER than the canonical R2 "
                      f"catalog ({r2_at.isoformat()}) — the mirror advanced past a "
                      f"publish that did not land (Wave 4 freeze §B)", flush=True)
            else:
                lag = (r2_at - mirror_at).total_seconds()
                print(f"  repo mirror lag: {lag:.0f}s behind R2 (lagging is correct; "
                      f"independently newer is not)")
    except catalog_mod.CatalogUnavailable as exc:
        print(f"::warning title=research_vault_census::could not compare mirror and "
              f"R2 clocks ({exc.reason})", flush=True)

    if catalog_minus_pdf:
        print(f"::error title=research_vault_census::{len(catalog_minus_pdf)} "
              f"catalog-admitted report(s) have NO canonical PDF — a reader can "
              f"open these and receive a 404", flush=True)
    if corpus_minus_catalog:
        print(f"::warning title=research_vault_census::{len(corpus_minus_catalog)} "
              f"corpus row(s) are not admitted by the catalog (publication-ahead or "
              f"a failed catalog publish); the serving tier hides them", flush=True)
    if catalog_minus_corpus:
        print(f"::warning title=research_vault_census::{len(catalog_minus_corpus)} "
              f"catalog report(s) are browsable but NOT searchable", flush=True)
    if receipt_minus_catalog:
        print(f"::warning title=research_vault_census::{len(receipt_minus_catalog)} "
              f"receipted report(s) are absent from the catalog — classify before "
              f"acting (failed publish vs intentional deletion vs superseded)",
              flush=True)

    if a.json:
        out = Path(a.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"census JSON written to {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
