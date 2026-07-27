"""research_vault.ingest — the hourly, idempotent ingestion pipeline (§7).

For each new PDF in ``research_inbox/`` (one whose receipt
``research_inbox/_processed/<id>.json`` is absent):

  1. fetch pdf + sidecar (store GET, private bucket),
  2. normalize the sidecar to the v1 contract (fallbacks; never drop),
  3. extract body text via ``pdftotext -layout`` (30s timeout; graceful empty),
  4. measure the deterministic facts (probe.py: pages, content hash, text-layer
     density, PDF provenance) — these OVERRIDE sidecar claims for the same field,
  5. recover the real title when the sidecar gave us the PDF's FILENAME (title.py),
  6. promote the PDF → ``research_vault/<id>.pdf``,
  7. upsert the catalog row + FTS corpus row (title/summary/body/institution/date),
  8. write the receipt ``research_inbox/_processed/<id>.json``.

Each run also re-derives filename-shaped titles for documents ALREADY in the
catalog (:func:`_repair_titles`) — receipted PDFs are never re-ingested, so that
pass is the only way an ingest-side title fix ever reaches them.

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
from engine.research_vault import probe as probe_mod
from engine.research_vault import sidecar as sidecar_mod
from engine.research_vault import title as title_mod

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

def _ingest_one(store, conn, pdf_key: str, dry_run: bool = False) -> dict:
    """Ingest a single PDF. Returns a per-item result dict.

    ``status`` ∈ ingested | failed. On any exception the item is marked failed
    (logged) and the batch continues.
    """
    result = {"pdf_key": pdf_key, "status": "failed", "id": None, "needs_metadata": False,
              "title_source": "sidecar", "facts": {}}
    try:
        pdf_bytes = store.get_bytes(pdf_key)
        if not pdf_bytes:
            log.warning("research_vault: pdf missing/empty %s — skip", pdf_key)
            return result

        sidecar_raw = store.get_bytes(_sidecar_key(pdf_key))

        # Fallbacks the caller can recover before normalization. We deliberately
        # pass NO published_at fallback: published_at is MarketDesk's own publish
        # timestamp (carried by the sidecar). If it is ever missing, the paper must
        # sort to the BOTTOM of the vault (a blank date sorts last) — it must NEVER
        # be stamped with our R2-upload / ingest time, which would masquerade a
        # stale backfill as brand-new at the TOP of "latest".
        item = sidecar_mod.from_bytes(
            sidecar_raw,
            fallback_title_pdf=_embedded_title(pdf_bytes),
            fallback_title_filename=_pdf_stem_filename(pdf_key),
            fallback_source_filename=_pdf_stem_filename(pdf_key) + ".pdf",
        )

        # top_pick from the sidecar OR the top_picks/ prefix (§5).
        if pdf_key.startswith(TOP_PICKS_PREFIX):
            item["top_pick"] = True

        item_id = item["id"]
        result["id"] = item_id
        result["needs_metadata"] = bool(item.get("needs_metadata"))
        if not item.get("published_at"):
            log.warning("research_vault: %s has no MarketDesk publish date; it will "
                        "sort to the bottom of the vault (never stamped with our "
                        "ingest time)", item_id)

        # Keep the RAW extractor result: None means pdftotext is missing/crashed
        # (a host fault) while "" means the PDF genuinely has no text layer (a
        # document fault). probe.text_facts keeps them apart; every consumer below
        # wants the "" form.
        raw_text = extract_pdf_text(pdf_bytes)
        body_text = raw_text or ""

        # Facts MEASURED from the bytes — page count, content hash, text-layer
        # density, PDF provenance. These override sidecar CLAIMS for the same field
        # (pages), because a local measurement beats an upstream promise.
        facts = probe_mod.probe(pdf_bytes)
        facts.update(probe_mod.text_facts(raw_text, facts.get("pages")))
        if facts.get("pages"):
            item["pages"] = facts["pages"]
        else:
            facts["pages"] = item.get("pages")
        facts["language"] = item.get("language") or ""
        result["facts"] = facts

        if facts.get("text_layer") in ("none", "thin"):
            # Body search is blind (or nearly) to this document and nothing else in
            # the pipeline would ever say so — the row still ingests and still ranks
            # on title/summary.
            log.warning("research_vault: %s has a %s text layer (%s chars / %s pages)"
                        " — body search will not find it",
                        item_id, facts["text_layer"], facts.get("char_count"),
                        facts.get("pages"))

        # A sidecar title that is really the PDF's FILENAME is a valid field, so the
        # normalize ladder never sees it as missing — it has to be caught by shape
        # and looked up in the report's own first page (engine/research_vault/title.py).
        # The id is NOT re-derived: it already keys the receipt and vault object.
        new_title, src = title_mod.resolve(item["title"], body_text)
        if src != "sidecar":
            log.info("research_vault: title (%s) %r -> %r", src, item["title"], new_title)
            item["title"] = new_title
        result["title_source"] = src

        # Promote the canonical PDF into the vault (private). Skipped on dry-run.
        if not dry_run:
            store.put_bytes(f"{VAULT_PREFIX}{item_id}.pdf", pdf_bytes, "application/pdf")

        # Upsert corpus (title/summary/body/institution/date + measured facts).
        corpus_mod.upsert(conn, item, body_text, facts=facts)

        result["item"] = item
        result["status"] = "ingested"
        return result
    except Exception as e:  # noqa: BLE001 — one bad doc must not kill the batch
        log.warning("research_vault: ingest failed for %s: %s", pdf_key, e)
        return result


# ---------------------------------------------------------------------------
# title repair over the EXISTING catalog
# ---------------------------------------------------------------------------

def _repair_titles(cat: dict, conn) -> dict:
    """Re-derive filename-shaped titles for documents already in the catalog.

    Ingest skips every PDF that has a receipt, so a fix to the ingest-time title
    ladder alone would never reach a document that was already ingested — and the
    catalog in the store is the copy the render bakes from. This pass closes that
    gap: each run re-examines the catalog it just loaded, repairs any title that
    still carries filename furniture using the body text the corpus already holds
    (restored from the store above — no PDF re-fetch), and updates the corpus row
    so search ranks the real title too (title is the heaviest FTS column).

    Idempotent: a repaired title no longer looks filename-derived, so the next run
    passes over it. Returns ``{repaired, recovered, unresolved: [(id, title), …]}``;
    never raises — a title is never worth failing the hourly job.
    """
    out = {"repaired": 0, "recovered": 0, "unresolved": []}
    for item in cat.get("items") or []:
        try:
            old = (item.get("title") or "").strip()
            doc_id = item.get("id") or ""
            if not old or not doc_id or not title_mod.looks_filename_derived(old):
                continue
            body = ""
            try:
                row = conn.execute("SELECT body FROM documents WHERE doc_id=?",
                                   (doc_id,)).fetchone()
                if row is not None:
                    body = row[0] or ""
            except Exception as e:  # noqa: BLE001 — no body: clean-only repair
                log.warning("research_vault: corpus body lookup failed for %s: %s", doc_id, e)
            new, src = title_mod.resolve(old, body)
            if src == "filename":
                out["unresolved"].append((doc_id, new))
            if new == old:
                continue
            item["title"] = new
            out["repaired"] += 1
            out["recovered"] += int(src == "pdf")
            log.info("research_vault: repaired title (%s) %r -> %r", src, old, new)
            try:
                conn.execute("UPDATE documents SET title=? WHERE doc_id=?", (new, doc_id))
            except Exception as e:  # noqa: BLE001 — catalog is the public surface
                log.warning("research_vault: corpus title update failed for %s: %s", doc_id, e)
        except Exception as e:  # noqa: BLE001 — one bad row never stops the pass
            log.warning("research_vault: title repair failed for %s: %s", item.get("id"), e)
    if out["repaired"]:
        conn.commit()
    return out


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

# Publish catalog+corpus every N ingested docs so a killed run (e.g. the GHA
# 15-min timeout mid-backfill) loses at most the last partial batch — receipts
# are written per item, so WITHOUT checkpoints the receipted-but-unpublished
# items would be skipped by every later run yet never appear in catalog/corpus.
CHECKPOINT_EVERY = 100


def run(store, corpus_path: str | Path, now: datetime | None = None,
        dry_run: bool = False, checkpoint_every: int = CHECKPOINT_EVERY) -> dict:
    """Run one ingestion pass. Idempotent + never-raise-per-item.

    Restores the canonical corpus from the store (source of truth), lists new
    inbox PDFs (receipt absent), ingests each, upserts the catalog + corpus,
    writes receipts, and persists the catalog + corpus back to the store.

    Returns a summary dict::

        {ingested, skipped, failed, needs_metadata, duplicate_bytes, no_text_layer,
         text_unavailable, titles_repaired, titles_recovered, titles_unresolved,
         coverage, catalog_bytes[, corpus_published][, error]}

    ``coverage`` is the per-field fill rate over the final catalog
    (:func:`catalog.coverage`) — the signal that ``needs_metadata`` cannot give,
    since it never inspects desk/tags/tickers/pages.

    ``catalog_bytes`` is the serialized catalog.json (so the CLI can snapshot it to
    the repo). ``dry_run=True`` runs the full pipeline but mutates NOTHING in the
    store: no PDF promotion, no receipts, no catalog write, no corpus publish —
    the counts still report what a real run WOULD do.
    """
    now = now or datetime.now(timezone.utc)
    summary = {"ingested": 0, "skipped": 0, "failed": 0, "needs_metadata": 0,
               "duplicate_bytes": 0, "no_text_layer": 0, "text_unavailable": 0,
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
        # Bare print, NOT log.error: GitHub only parses a workflow command when
        # "::" STARTS the line, and every entry point that runs this module
        # (build_research_vault, ingest_research) logs with a "%(levelname)s "
        # prefix, which silently drops the annotation.
        print("::error::research_vault: corpus restore FAILED with an existing "
              "store copy — skipping this run to protect the published corpus",
              flush=True)
        summary["error"] = "corpus_restore_failed"
        return summary

    conn = corpus_mod.open_db(corpus_path)
    pending_receipts: list = []  # (key, body) — flushed only after a publish
    try:
        cat = catalog_mod.load(store)

        # Heal filename-shaped titles already in the catalog (receipted docs are
        # never re-ingested, so this is the only path that reaches them).
        rep = _repair_titles(cat, conn)
        summary["titles_repaired"] = rep["repaired"]
        summary["titles_recovered"] = rep["recovered"]
        summary["titles_unresolved"] = len(rep["unresolved"])

        done_pdf_keys = _already_processed_pdf_keys(store)

        # {content_sha256: doc_id} for everything already indexed. Idempotency keys
        # on the SOURCE KEY, so the same report re-dropped under a different
        # filename is a genuinely new object and gets its own row. The hash makes
        # that visible.
        seen_sha = corpus_mod.sha_index(conn)

        for pdf_key in _list_inbox_pdfs(store):
            if pdf_key in done_pdf_keys:
                summary["skipped"] += 1
                continue

            res = _ingest_one(store, conn, pdf_key, dry_run=dry_run)
            if res["status"] != "ingested":
                summary["failed"] += 1
                continue

            item = res["item"]
            item_id = item["id"]

            facts = res.get("facts") or {}
            layer = facts.get("text_layer")
            if layer in ("none", "thin"):
                summary["no_text_layer"] += 1
            elif layer == "unavailable":
                summary["text_unavailable"] += 1

            # REPORT byte-identical duplicates; never skip on one. The same bytes
            # legitimately re-arrive with a corrected sidecar, and skipping would
            # freeze the original bad metadata in place forever (receipts already
            # make re-ingestion the only repair path).
            sha = facts.get("content_sha256") or ""
            if sha:
                prior = seen_sha.get(sha)
                if prior and prior != item_id:
                    summary["duplicate_bytes"] += 1
                    log.warning("research_vault: %s is byte-identical to %s "
                                "(same PDF, different source key) — ingesting both",
                                item_id, prior)
                seen_sha.setdefault(sha, item_id)
            if res.get("title_source") == "pdf":
                summary["titles_recovered"] += 1
            elif res.get("title_source") == "filename":
                rep["unresolved"].append((item_id, item["title"]))
                summary["titles_unresolved"] += 1
            catalog_mod.upsert_item(cat, item)

            # Receipt is only ACCUMULATED here — it is flushed to the store AFTER
            # its batch's catalog+corpus publish succeeds (checkpoint or final).
            # INVARIANT: a receipted doc is always present in a published
            # catalog+corpus. A kill between publishes loses only unflushed
            # receipts, so those docs simply re-ingest next run (every step is
            # idempotent: same vault key, catalog upsert by id, corpus
            # delete-then-insert).
            if not dry_run:
                receipt = {
                    "id": item_id,
                    "pdf_key": pdf_key,
                    "vault_key": f"{VAULT_PREFIX}{item_id}.pdf",
                    "processed_at": now.astimezone(timezone.utc).isoformat(),
                    "needs_metadata": bool(item.get("needs_metadata")),
                    "title_source": res.get("title_source"),
                    "institution": item.get("institution"),
                    "top_pick": bool(item.get("top_pick")),
                    # Measured evidence, carried on the receipt so it survives a
                    # corpus rebuild — the receipts are the only per-document record
                    # that is never regenerated from scratch.
                    "content_sha256": facts.get("content_sha256") or "",
                    "byte_size": facts.get("byte_size"),
                    "pages": facts.get("pages"),
                    "text_layer": facts.get("text_layer"),
                }
                pending_receipts.append((
                    _receipt_key(item_id),
                    (json.dumps(receipt, ensure_ascii=False) + "\n").encode("utf-8"),
                ))
            done_pdf_keys.add(pdf_key)

            summary["ingested"] += 1
            if item.get("needs_metadata"):
                summary["needs_metadata"] += 1

            # Mid-run checkpoint (real runs only): publish catalog + corpus, then
            # flush this batch's receipts. Publish failure keeps the receipts
            # pending (the docs retry at the next checkpoint / next run).
            if (not dry_run and checkpoint_every > 0
                    and summary["ingested"] % checkpoint_every == 0):
                catalog_mod.write(store, cat, now=now)
                conn.commit()
                if publish_corpus(store, corpus_path):
                    _flush_receipts(store, pending_receipts)
                log.info("research_vault: checkpoint at %d ingested",
                         summary["ingested"])

        # Per-field fill rate over the FINAL catalog — reported whether or not this
        # run ingested anything, because a dead contract field is a standing state,
        # not an event.
        summary["coverage"] = catalog_mod.coverage(cat)

        # Catalog: serialize always (for the repo snapshot); write to the store
        # only on a real run.
        if dry_run:
            summary["catalog_bytes"] = catalog_mod.serialize(cat, now=now)
        else:
            summary["catalog_bytes"] = catalog_mod.write(store, cat, now=now)
            conn.commit()

        # Flag rather than silently ship: these reports are published under a
        # cleaned-up FILENAME because their headline could not be found on page 1
        # — the desk sidecar needs a real title (or the PDF has no text layer).
        # Printed bare: a "::warning" behind logging's prefixed format never
        # parses as a GitHub annotation.
        if rep["unresolved"]:
            names = ", ".join(f"{i} ({t})" for i, t in rep["unresolved"][:8])
            more = "" if len(rep["unresolved"]) <= 8 else f" +{len(rep['unresolved']) - 8} more"
            print(f"::warning title=research_vault::{len(rep['unresolved'])} report(s) "
                  f"titled from their filename — no headline found on page 1: "
                  f"{names}{more}")
    finally:
        conn.close()

    # Final publish (real runs only), after the connection is closed. Receipts
    # for the last partial batch flush only on success — on failure they stay
    # unwritten and the batch re-ingests cleanly next run.
    if not dry_run:
        summary["corpus_published"] = publish_corpus(store, corpus_path)
        if summary["corpus_published"]:
            _flush_receipts(store, pending_receipts)
        if pending_receipts:
            print(f"::error::research_vault: {len(pending_receipts)} receipts unflushed "
                  f"(corpus publish failed) — the docs will re-ingest next run",
                  flush=True)
            summary["receipts_unflushed"] = len(pending_receipts)

    return summary


def _flush_receipts(store, pending: list) -> None:
    """Write+drain accumulated receipts (called only after a successful publish)."""
    while pending:
        key, body = pending[0]
        store.put_bytes(key, body, "application/json")
        pending.pop(0)


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
