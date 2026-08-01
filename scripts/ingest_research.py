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


def _report_measured(summary: dict, dry_run: bool = False) -> None:
    """Print the per-field fill rate + the engine-measured tripwires.

    Annotations use a BARE print starting at column 0: GitHub only parses a
    workflow command when ``::`` starts the line, and this CLI's logging format
    prefixes ``%(levelname)s``, which would silently swallow it.

    Every condition here is a WARNING or a NOTICE, never a failure — the hourly
    job's contract is that a bad document never blocks the batch, and the same
    holds for a document we merely learned something unflattering about. (The one
    fail-CLOSED gate in this lane is upstream of the CLI: the workflow refuses to
    ingest at all on a host with no ``pdftotext``, because ingesting bodyless
    writes receipts that freeze the damage — see research-ingest.yml.)

    The re-extraction lines below describe rows that were CHANGED, so like the
    sidecar lines they may claim nothing under --dry-run, which publishes nothing.
    """
    try:
        from engine.research_vault import catalog as catalog_mod

        cov = summary.get("coverage") or {}
        if cov:
            lines, dead = catalog_mod.coverage_lines(cov)
            print("ingest_research: catalog field coverage")
            for ln in lines:
                print(ln)
            for field in dead:
                # A schema field that no producer ever fills. Loud on purpose: this
                # is the state that sat unnoticed across every document in the vault
                # while needs_metadata reported a clean bill of health.
                print(f"::warning::research_vault: catalog field '{field}' is empty on "
                      f"ALL {cov[field]['total']} items — no producer fills it",
                      flush=True)

        # Both of these describe rows that were CHANGED, so neither may claim
        # anything under --dry-run, which publishes nothing: "folded into
        # already-published rows" would be simply false.
        if summary.get("summaries_recovered") and not dry_run:
            # A NOTICE, not a warning: this is the repair working. It is worth
            # surfacing because the number is also the count of rows that shipped
            # "Summary pending" to the public site until this run healed them.
            print(f"::notice title=research_vault::{summary['summaries_recovered']} "
                  f"late sidecar summary(ies) folded into already-published rows "
                  f"({summary.get('sidecars_checked', 0)} sidecar(s) re-checked)",
                  flush=True)

        if summary.get("summaries_resynced") and not dry_run:
            # Rows whose bullets reached the catalog but not the corpus — the
            # skew a failed corpus publish leaves behind. Non-zero means a PRIOR
            # run's publish failed, so it is worth seeing even though it healed.
            print(f"::warning title=research_vault::"
                  f"{summary['summaries_resynced']} corpus summary(ies) were out of "
                  f"sync with the catalog and have been resynced — a previous "
                  f"corpus publish did not land", flush=True)

        if summary.get("bodies_reextracted") and not dry_run:
            # A NOTICE, not a warning: this is the repair working. The number is
            # also the count of rows that were invisible to body search — and
            # served to the full-report reader as excerpt-only — until this run
            # healed them (see ingest._reextract_bodies).
            print(f"::notice title=research_vault::{summary['bodies_reextracted']} "
                  f"empty body(ies) re-extracted into already-published rows "
                  f"({summary.get('reextract_checked', 0)} re-checked)", flush=True)

        if summary.get("reextract_remaining") and not dry_run:
            # Mirrors the sidecar-cap precedent: a bound that truncates coverage
            # must SAY so, or the notice above reads as "the backlog is drained".
            print(f"::warning title=research_vault::body re-extraction capped — "
                  f"{summary['reextract_remaining']} candidate row(s) not "
                  f"re-checked this run", flush=True)

        if summary.get("reextract_aborted") and not dry_run:
            # The 2026-07-30 fault itself, still live: the pass refuses to stamp
            # anything from an extraction that never ran, so the backlog stands
            # until poppler is back on this host.
            print("::warning title=research_vault::body re-extraction could not "
                  "run — pdftotext is still unavailable on this host, so the "
                  "bodyless rows stay bodyless (install poppler)", flush=True)

        if summary.get("no_text_layer"):
            print(f"::warning::research_vault: {summary['no_text_layer']} document(s) "
                  f"ingested with no/thin text layer — body search cannot find them",
                  flush=True)
        if summary.get("text_unavailable"):
            print(f"::warning::research_vault: pdftotext unavailable for "
                  f"{summary['text_unavailable']} document(s) — HOST fault, not a "
                  f"document property (install poppler)", flush=True)
        if summary.get("duplicate_bytes"):
            print(f"::warning::research_vault: {summary['duplicate_bytes']} "
                  f"byte-identical duplicate(s) ingested under a second id", flush=True)
    except Exception as exc:  # noqa: BLE001 — reporting must never fail the job
        log.warning("ingest_research: coverage report failed: %s", exc)


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
                  f"summaries_recovered={summary.get('summaries_recovered', 0)} "
                  f"(corpus={corpus_path}; nothing published)")
            _report_measured(summary, dry_run=True)
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
              f"summaries_recovered={summary.get('summaries_recovered', 0)} "
              f"(checked={summary.get('sidecars_checked', 0)}, "
              f"resynced={summary.get('summaries_resynced', 0)}) "
              f"bodies_reextracted={summary.get('bodies_reextracted', 0)} "
              f"(checked={summary.get('reextract_checked', 0)}, "
              f"remaining={summary.get('reextract_remaining', 0)}) "
              f"corpus_published={summary.get('corpus_published')} "
              f"excerpts={n_excerpts} snapshot={_REPO_CATALOG}")
        _report_measured(summary)
        return 0
    except Exception as exc:  # noqa: BLE001 — never-raise: keep the hourly job alive
        log.warning("ingest_research: run failed: %s", exc)
        print(f"ingest_research: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
