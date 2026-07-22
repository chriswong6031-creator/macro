"""scripts/ingest_research.py — Research Vault hourly ingestion CLI (RV W1).

Builds the object store (R2 private bucket, or a local dir), runs the ingestion
pass (engine.research_vault.ingest.run), then publishes catalog.json + corpus.sqlite
to the store and prints a summary. Also snapshots catalog.json to the repo at
``data/research_vault/catalog.json`` so the nightly render can SSR-bake without R2.

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
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("ingest_research")

# Repo snapshot the nightly render SSR-bakes from (masterplan §4).
_REPO_CATALOG = Path(__file__).resolve().parent.parent / "data" / "research_vault" / "catalog.json"


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

        print(f"ingest_research: ok — ingested={summary['ingested']} "
              f"skipped={summary['skipped']} failed={summary['failed']} "
              f"needs_metadata={summary['needs_metadata']} "
              f"corpus_published={summary.get('corpus_published')} snapshot={_REPO_CATALOG}")
        return 0
    except Exception as exc:  # noqa: BLE001 — never-raise: keep the hourly job alive
        log.warning("ingest_research: run failed: %s", exc)
        print(f"ingest_research: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
