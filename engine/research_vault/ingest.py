"""research_vault.ingest — the hourly, idempotent ingestion pipeline (§7).

For each new PDF in ``research_inbox/`` (one whose receipt
``research_inbox/_processed/<id>.json`` is absent):

  1. fetch pdf + sidecar (store GET, private bucket),
  2. normalize the sidecar to the v1 contract (fallbacks; never drop),
  3. extract body text via ``pdftotext -layout`` (30s timeout; graceful empty),
  4. promote the PDF → ``research_vault/<id>.pdf``,
  5. upsert the catalog row + FTS corpus row (title/summary/body/institution/date),
  6. write the receipt ``research_inbox/_processed/<id>.json``.

Every per-item step is wrapped so ONE bad document can never abort the batch
(never-raise-per-item); the whole run is idempotent (a re-run ingests 0). A
``top_pick`` is honored from the sidecar ``top_pick:true`` OR the
``research_inbox/top_picks/`` prefix. Returns a summary dict.

The pdftotext extractor is copied verbatim from ``collectors/hk_cbbc_sld.py``
(tmpfile, -layout, 30s timeout, UTF-8, graceful None).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from engine.research_vault import catalog as catalog_mod
from engine.research_vault import corpus as corpus_mod
from engine.research_vault import sidecar as sidecar_mod

log = logging.getLogger("research_vault.ingest")

INBOX_PREFIX = "research_inbox/"
TOP_PICKS_PREFIX = "research_inbox/top_picks/"
PROCESSED_PREFIX = "research_inbox/_processed/"
VAULT_PREFIX = "research_vault/"
CORPUS_KEY = "research_vault/corpus.sqlite"


# ---------------------------------------------------------------------------
# PDF text extraction (copied idiom: collectors/hk_cbbc_sld.extract_pdf_text)
# ---------------------------------------------------------------------------

def _pdftotext_available() -> bool:
    return shutil.which("pdftotext") is not None


def extract_pdf_text(pdf_bytes: bytes) -> str | None:
    """Extract text from PDF bytes using ``pdftotext -layout``.

    Returns the text, or None on failure (pdftotext missing / crash / timeout).
    Never raises. Copied from collectors/hk_cbbc_sld.py:184-217.
    """
    if not _pdftotext_available():
        log.warning("research_vault: pdftotext not found — body text unavailable")
        return None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(pdf_bytes)
            result = subprocess.run(
                ["pdftotext", "-layout", tmp_path, "-"],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                log.warning("research_vault: pdftotext returned %d: %s",
                            result.returncode, result.stderr[:200])
                return None
            return result.stdout.decode("utf-8", errors="replace")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except subprocess.TimeoutExpired:
        log.warning("research_vault: pdftotext timed out")
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("research_vault: pdftotext exception: %s", e)
        return None


def _embedded_title(pdf_bytes: bytes) -> str:
    """Best-effort PDF-embedded /Title (Info dict). '' when unavailable.

    Uses a light regex over the raw bytes — no pypdf dependency in W1
    (watermarking/pypdf is W2). Never raises.
    """
    try:
        import re
        m = re.search(rb"/Title\s*\(([^)]{1,200})\)", pdf_bytes)
        if m:
            return m.group(1).decode("latin-1", errors="replace").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


# ---------------------------------------------------------------------------
# inbox listing
# ---------------------------------------------------------------------------

def _list_inbox_pdfs(store) -> list[str]:
    """PDF keys directly under research_inbox/ (incl. the top_picks/ subfolder),
    excluding the _processed/ receipt area."""
    keys = store.list_prefix(INBOX_PREFIX)
    out = []
    for k in keys:
        if not k.lower().endswith(".pdf"):
            continue
        if k.startswith(PROCESSED_PREFIX):
            continue
        out.append(k)
    return sorted(out)


def _sidecar_key(pdf_key: str) -> str:
    """The <id>.json sidecar beside a <id>.pdf."""
    return pdf_key[:-4] + ".json" if pdf_key.lower().endswith(".pdf") else pdf_key + ".json"


def _receipt_key(item_id: str) -> str:
    return f"{PROCESSED_PREFIX}{item_id}.json"


def _pdf_stem_filename(pdf_key: str) -> str:
    """The bare filename (no dir, no .pdf) — the last-ditch title fallback."""
    return Path(pdf_key).stem


def _already_processed_pdf_keys(store) -> set[str]:
    """PDF source keys recorded in any receipt (idempotency across id changes).

    A receipt records the source ``pdf_key`` it consumed; we skip re-ingesting
    the same source object even if the derived id later shifts.
    """
    done: set[str] = set()
    for rk in store.list_prefix(PROCESSED_PREFIX):
        if not rk.endswith(".json"):
            continue
        raw = store.get_bytes(rk)
        if not raw:
            continue
        try:
            rec = json.loads(raw)
            src = rec.get("pdf_key")
            if src:
                done.add(src)
        except Exception:  # noqa: BLE001 — unreadable receipt: fall through
            continue
    return done


# ---------------------------------------------------------------------------
# per-item ingest (never raises to the caller)
# ---------------------------------------------------------------------------

def _ingest_one(store, conn, pdf_key: str, now: datetime, dry_run: bool = False) -> dict:
    """Ingest a single PDF. Returns a per-item result dict.

    ``status`` ∈ ingested | failed. On any exception the item is marked failed
    (logged) and the batch continues.
    """
    result = {"pdf_key": pdf_key, "status": "failed", "id": None, "needs_metadata": False}
    try:
        pdf_bytes = store.get_bytes(pdf_key)
        if not pdf_bytes:
            log.warning("research_vault: pdf missing/empty %s — skip", pdf_key)
            return result

        sidecar_raw = store.get_bytes(_sidecar_key(pdf_key))

        # Fallbacks the caller can recover before normalization.
        upload_time = store.upload_time(pdf_key) or now.astimezone(timezone.utc).isoformat()
        item = sidecar_mod.from_bytes(
            sidecar_raw,
            fallback_title_pdf=_embedded_title(pdf_bytes),
            fallback_title_filename=_pdf_stem_filename(pdf_key),
            fallback_published_at=upload_time,
            fallback_source_filename=_pdf_stem_filename(pdf_key) + ".pdf",
        )

        # top_pick from the sidecar OR the top_picks/ prefix (§5).
        if pdf_key.startswith(TOP_PICKS_PREFIX):
            item["top_pick"] = True

        item_id = item["id"]
        result["id"] = item_id
        result["needs_metadata"] = bool(item.get("needs_metadata"))

        body_text = extract_pdf_text(pdf_bytes) or ""

        # Promote the canonical PDF into the vault (private). Skipped on dry-run.
        if not dry_run:
            store.put_bytes(f"{VAULT_PREFIX}{item_id}.pdf", pdf_bytes, "application/pdf")

        # Upsert corpus (title/summary/body/institution/date).
        corpus_mod.upsert(conn, item, body_text)

        result["item"] = item
        result["status"] = "ingested"
        return result
    except Exception as e:  # noqa: BLE001 — one bad doc must not kill the batch
        log.warning("research_vault: ingest failed for %s: %s", pdf_key, e)
        return result


# ---------------------------------------------------------------------------
# corpus restore (the store copy is the source of truth)
# ---------------------------------------------------------------------------

def _restore_corpus(store, corpus_path: str | Path) -> str:
    """Restore the canonical ``corpus.sqlite`` from the store to ``corpus_path``.

    Returns:
      - ``"fresh"``    — no store copy yet (first run); any stale local file is
                          cleared so we never publish leftover local state.
      - ``"restored"`` — the store copy was written locally.
      - ``"error"``    — a store copy EXISTS but could not be written locally; the
                          caller MUST NOT publish, to avoid clobbering it.

    Why this exists: the run skips already-processed PDFs (idempotency), so it only
    upserts the NEW documents. The store copy is therefore the source of truth and
    must be restored before we open the DB — otherwise an hourly run on a runner
    with an empty ``/tmp`` would publish a corpus holding ONLY that hour's items
    and silently drop all search history (the catalog, loaded from the store each
    run, would then reference documents the corpus can no longer find).
    """
    p = Path(corpus_path)
    _sidecars = (f"{p}-wal", f"{p}-shm", f"{p}-journal")
    data = store.get_bytes(CORPUS_KEY)
    if not data:
        for cand in (str(p), *_sidecars):
            try:
                Path(cand).unlink()
            except OSError:
                pass
        return "fresh"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        for s in _sidecars:
            try:
                Path(s).unlink()
            except OSError:
                pass
        tmp = p.with_suffix(p.suffix + ".restore.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        return "restored"
    except Exception as e:  # noqa: BLE001 — protect the published corpus
        log.error("research_vault: corpus restore failed (%s)", e)
        return "error"


# ---------------------------------------------------------------------------
# batch run
# ---------------------------------------------------------------------------

def run(store, corpus_path: str | Path, now: datetime | None = None,
        dry_run: bool = False) -> dict:
    """Run one ingestion pass. Idempotent + never-raise-per-item.

    Restores the canonical corpus from the store (source of truth), lists new
    inbox PDFs (receipt absent), ingests each, upserts the catalog + corpus,
    writes receipts, and persists the catalog + corpus back to the store.

    Returns a summary dict::

        {ingested, skipped, failed, needs_metadata, catalog_bytes[, corpus_published][, error]}

    ``catalog_bytes`` is the serialized catalog.json (so the CLI can snapshot it to
    the repo). ``dry_run=True`` runs the full pipeline but mutates NOTHING in the
    store: no PDF promotion, no receipts, no catalog write, no corpus publish —
    the counts still report what a real run WOULD do.
    """
    now = now or datetime.now(timezone.utc)
    summary = {"ingested": 0, "skipped": 0, "failed": 0, "needs_metadata": 0,
               "catalog_bytes": b""}

    if store is None:
        log.info("research_vault: no store available — nothing to ingest")
        return summary

    # Restore the published corpus before we upsert onto it (see _restore_corpus).
    restore = _restore_corpus(store, corpus_path)
    if restore == "error":
        # A store copy exists but could not be restored — refuse to proceed so we
        # never overwrite the good published corpus with a truncated rebuild. No
        # receipts are written, so the next run retries the whole batch cleanly.
        log.error("::error::research_vault: corpus restore FAILED with an existing "
                  "store copy — skipping this run to protect the published corpus")
        summary["error"] = "corpus_restore_failed"
        return summary

    conn = corpus_mod.open_db(corpus_path)
    try:
        cat = catalog_mod.load(store)
        done_pdf_keys = _already_processed_pdf_keys(store)

        for pdf_key in _list_inbox_pdfs(store):
            if pdf_key in done_pdf_keys:
                summary["skipped"] += 1
                continue

            res = _ingest_one(store, conn, pdf_key, now, dry_run=dry_run)
            if res["status"] != "ingested":
                summary["failed"] += 1
                continue

            item = res["item"]
            item_id = item["id"]
            catalog_mod.upsert_item(cat, item)

            # Receipt marks the source consumed (idempotency). Real runs only.
            if not dry_run:
                receipt = {
                    "id": item_id,
                    "pdf_key": pdf_key,
                    "vault_key": f"{VAULT_PREFIX}{item_id}.pdf",
                    "processed_at": now.astimezone(timezone.utc).isoformat(),
                    "needs_metadata": bool(item.get("needs_metadata")),
                    "institution": item.get("institution"),
                    "top_pick": bool(item.get("top_pick")),
                }
                store.put_bytes(
                    _receipt_key(item_id),
                    (json.dumps(receipt, ensure_ascii=False) + "\n").encode("utf-8"),
                    "application/json",
                )
            done_pdf_keys.add(pdf_key)

            summary["ingested"] += 1
            if item.get("needs_metadata"):
                summary["needs_metadata"] += 1

        # Catalog: serialize always (for the repo snapshot); write to the store
        # only on a real run.
        if dry_run:
            summary["catalog_bytes"] = catalog_mod.serialize(cat, now=now)
        else:
            summary["catalog_bytes"] = catalog_mod.write(store, cat, now=now)
    finally:
        conn.close()

    # Publish the now-complete single-file corpus back to the store (real runs
    # only), after the connection is closed so there is no open journal.
    if not dry_run:
        summary["corpus_published"] = publish_corpus(store, corpus_path)

    return summary


def publish_corpus(store, corpus_path: str | Path) -> bool:
    """Publish corpus.sqlite bytes to the store at research_vault/corpus.sqlite."""
    p = Path(corpus_path)
    if not p.is_file():
        log.warning("research_vault: corpus missing at %s — not published", p)
        return False
    try:
        data = p.read_bytes()
    except Exception as e:  # noqa: BLE001
        log.warning("research_vault: corpus read failed: %s", e)
        return False
    return store.put_bytes(f"{VAULT_PREFIX}corpus.sqlite", data,
                           "application/x-sqlite3")
