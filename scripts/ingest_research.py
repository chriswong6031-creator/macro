"""scripts/ingest_research.py — Research Vault hourly ingestion CLI (RV W1).

Builds the object store (R2 private bucket, or a local dir), runs the ingestion
pass (engine.research_vault.ingest.run), then publishes catalog.json + corpus.sqlite
to the store and prints a summary. Also snapshots to the repo, so the nightly
render can SSR-bake without R2:

  * ``data/research_vault/catalog.json``  — the public catalog;
  * ``data/research_vault/excerpts.json`` — the public first-pages excerpts
    (engine.research_vault.excerpt) that the per-report SEO pages publish
    outside the paywall. Derived from the corpus body text HERE because the
    corpus lives only in R2 and the render path must never reach for it.

Usage:
    python -m scripts.ingest_research                 # R2 (R2_RESEARCH_BUCKET + creds)
    RESEARCH_LOCAL_STORE=/tmp/rv python -m scripts.ingest_research --local /tmp/rv
    python -m scripts.ingest_research --dry-run       # ingest, but publish nothing

Never-raise: exits 0 with a warning on error so the hourly workflow keeps going.
Store precedence: --local > RESEARCH_LOCAL_STORE > R2_RESEARCH_BUCKET; no store → no-op.
Mirrors the brevity of scripts/build_marketing.py.
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

log = logging.getLogger("ingest_research")

# Repo snapshots the nightly render SSR-bakes from (masterplan §4).
_REPO_CATALOG = Path(__file__).resolve().parent.parent / "data" / "research_vault" / "catalog.json"
_REPO_EXCERPTS = Path(__file__).resolve().parent.parent / "data" / "research_vault" / "excerpts.json"


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s",
                        stream=sys.stderr)
    ap = argparse.ArgumentParser(description="Research Vault ingestion (RV W1)")
    ap.add_argument("--local", metavar="DIR",
                    help="use a local filesystem store rooted at DIR (no R2)")
    ap.add_argument("--dry-run", action="store_true",
                    help="run ingest but do NOT publish corpus/catalog back to R2")
    ap.add_argument("--corpus", metavar="PATH",
                    help="corpus.sqlite path (default: a temp file)")
    a = ap.parse_args()

    try:
        from engine.research_vault import ingest as ingest_mod
        from engine.research_vault import r2_store

        store = r2_store.build_store(local_dir=a.local)
        if store is None:
            print("ingest_research: no store (set RESEARCH_LOCAL_STORE, --local, "
                  "or R2_RESEARCH_BUCKET + R2 creds) — nothing to do", file=sys.stderr)
            return 0

        corpus_path = Path(a.corpus) if a.corpus else \
            Path(tempfile.gettempdir()) / "research_vault_corpus.sqlite"

        summary = ingest_mod.run(store, corpus_path, dry_run=a.dry_run)

        catalog_bytes = summary.get("catalog_bytes") or b""

        if a.dry_run:
            print(f"ingest_research: DRY-RUN — ingested={summary['ingested']} "
                  f"skipped={summary['skipped']} failed={summary['failed']} "
                  f"needs_metadata={summary['needs_metadata']} "
                  f"titles_repaired={summary.get('titles_repaired', 0)} "
                  f"(corpus={corpus_path}; nothing published)")
            return 0

        # Catalog + corpus were already published to the store by run(); snapshot
        # catalog.json to the repo for the nightly SSR bake.
        if catalog_bytes:
            try:
                _REPO_CATALOG.parent.mkdir(parents=True, exist_ok=True)
                _REPO_CATALOG.write_bytes(catalog_bytes)
            except Exception as exc:  # noqa: BLE001
                log.warning("ingest_research: repo snapshot write failed: %s", exc)

        # Public first-pages excerpts, snapshotted beside the catalog so the
        # nightly render stays R2-free (the corpus body text lives only in R2).
        # Own never-raise guard: an excerpt is never worth failing the hourly job,
        # and a failure here simply leaves yesterday's committed snapshot in place.
        n_excerpts = 0
        try:
            if corpus_path.is_file() and catalog_bytes:
                from engine.research_vault import excerpt as excerpt_mod

                items = (json.loads(catalog_bytes.decode("utf-8")) or {}).get("items") or []
                ids = {it["id"] for it in items if isinstance(it, dict) and it.get("id")}
                # READ-ONLY: this connection must never mutate the corpus that was
                # just published to R2.
                conn = sqlite3.connect(f"file:{corpus_path}?mode=ro", uri=True)
                try:
                    excerpts = excerpt_mod.snapshot(conn, ids)
                finally:
                    conn.close()
                if excerpt_mod.write_repo_snapshot(excerpts, _REPO_EXCERPTS):
                    n_excerpts = len(excerpts)
        except Exception as exc:  # noqa: BLE001 — keep the hourly job alive
            log.warning("ingest_research: excerpt snapshot failed: %s", exc)

        print(f"ingest_research: ok — ingested={summary['ingested']} "
              f"skipped={summary['skipped']} failed={summary['failed']} "
              f"needs_metadata={summary['needs_metadata']} "
              f"titles_repaired={summary.get('titles_repaired', 0)} "
              f"(from_pdf={summary.get('titles_recovered', 0)}, "
              f"filename_only={summary.get('titles_unresolved', 0)}) "
              f"corpus_published={summary.get('corpus_published')} "
              f"excerpts={n_excerpts} snapshot={_REPO_CATALOG}")
        return 0
    except Exception as exc:  # noqa: BLE001 — never-raise: keep the hourly job alive
        log.warning("ingest_research: run failed: %s", exc)
        print(f"ingest_research: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
