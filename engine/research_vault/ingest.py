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

Receipted PDFs are never re-ingested, so three passes over the ALREADY-published
catalog/corpus are the only way a later correction ever reaches them:
:func:`_repair_titles` re-derives filename-shaped titles,
:func:`_refresh_sidecars` re-reads the sidecar of any row still missing
``summary_points``/``tags``/``tickers``/``desk`` — the upstream desk writes those
asynchronously, well after the PDF itself lands — and
:func:`_reextract_bodies` re-runs ``pdftotext`` over the vault PDF of any row whose
body never extracted because the HOST was broken at ingest time.

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
from datetime import datetime, timedelta, timezone
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


def _processed_index(store) -> tuple[set[str], dict[str, str]]:
    """Read every receipt once → ``(done_pdf_keys, {doc_id: pdf_key})``.

    ``done_pdf_keys`` drives idempotency: a receipt records the source ``pdf_key``
    it consumed, so we skip re-ingesting that object even if the derived id later
    shifts.

    The ``{doc_id: pdf_key}`` map is the ONLY way back from a published catalog
    row to the inbox object it came from — the public catalog carries no source
    key — and it is what lets :func:`_refresh_sidecars` re-read a sidecar for a
    document that is already receipted. It costs nothing extra: this pass was
    already reading every receipt.
    """
    done: set[str] = set()
    by_id: dict[str, str] = {}
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
                doc_id = rec.get("id")
                if doc_id:
                    by_id[doc_id] = src
        except Exception:  # noqa: BLE001 — unreadable receipt: fall through
            continue
    return done, by_id


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
# sidecar refresh over the EXISTING catalog (the upstream is TWO-PHASE)
# ---------------------------------------------------------------------------

# The enrichment fields a later sidecar write can still supply. Deliberately NOT
# here: identity (id/title/institution/side/published_at), because a row's title
# has by now been through title.resolve + _repair_titles and must never regress
# to the raw sidecar string; and `pages`/`language`, because §5b makes the
# MEASURED page count authoritative over the sidecar's claim.
_REFRESH_FIELDS = ("summary_points", "tags", "tickers", "desk")

# CANDIDACY keys on summary_points ALONE — not on all of _REFRESH_FIELDS.
# `desk`/`tags`/`tickers` are empty on EVERY document in the vault because no
# producer writes them (catalog.coverage exists to report exactly that), so an
# all-fields gate is never satisfied and every in-window row would be re-fetched
# every hour forever — the opposite of the self-quiescing pass this claims to be,
# at ~236 wasted GETs/hour. summary_points is the one field with a real producer
# and therefore the only honest liveness signal. The other three are still FILLED
# opportunistically whenever a fetch happens; they just cannot keep a row alive.
_REFRESH_TRIGGER = "summary_points"

# Only re-check documents published inside this window. A sidecar still empty
# after two weeks is a document the upstream never summarized, not one we raced;
# polling it hourly forever would grow the per-run GET count without bound as the
# vault does. The cap is the second bound, for a large backfill of empty rows.
REFRESH_LOOKBACK_DAYS = 14
REFRESH_MAX = 500


def _resync_corpus_summaries(cat: dict, conn) -> int:
    """Copy catalog ``summary_points`` onto any corpus row whose summary is blank.

    Closes a skew the refresh pass would otherwise make PERMANENT. ``run()``
    writes the catalog BEFORE it publishes the corpus, so a failed corpus publish
    leaves the store holding a catalog row with bullets and a corpus row without
    them. That row is then no longer a refresh candidate (its ``summary_points``
    is non-empty), so search would rank it on stale text forever.

    Purely local — one query plus an UPDATE per skewed row, no store reads. Runs
    every pass because it is the cheap direction: normally it finds nothing.
    Never raises; returns the number of rows resynced.
    """
    try:
        blank = {r[0] for r in conn.execute(
            "SELECT doc_id FROM documents WHERE summary IS NULL OR summary=''"
        ).fetchall()}
    except Exception as e:  # noqa: BLE001 — a resync is never worth failing the job
        log.warning("research_vault: corpus summary resync query failed: %s", e)
        return 0
    if not blank:
        return 0
    n = 0
    for item in cat.get("items") or []:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("id") or ""
        if doc_id not in blank or not item.get("summary_points"):
            continue
        try:
            conn.execute("UPDATE documents SET summary=? WHERE doc_id=?",
                         (corpus_mod.summary_text(item), doc_id))
            n += 1
        except Exception as e:  # noqa: BLE001 — one bad row never stops the pass
            log.warning("research_vault: corpus summary resync failed for %s: %s",
                        doc_id, e)
    if n:
        log.info("research_vault: resynced %d corpus summary(ies) from the catalog", n)
    return n


def _refresh_sidecars(store, cat: dict, conn, id_to_pdf_key: dict[str, str],
                      now: datetime) -> dict:
    """Fold late-arriving sidecar metadata into rows that are already published.

    WHY this exists: the upstream desk writes a sidecar in TWO phases — identity
    (title/institution/side/published_at) when the PDF lands, then
    ``summary_points`` once its summarizer finishes. Our hourly cron frequently
    reads the object in between. Because ingest is receipt-idempotent the sidecar
    was then never re-read, so whichever phase we happened to catch was frozen
    forever: replaying the catalog's own git history over 74 hourly snapshots
    showed 63 of 236 rows stuck on ``summary_points: []`` (the public
    "Summary pending") and ZERO rows that ever transitioned ``[] -> filled``.

    Fill-only, never overwrite: a field we already have is left exactly as it is,
    so this pass can only add information. That is what makes it safe to re-run
    hourly, and idempotent — a row whose ``summary_points`` arrive drops out of
    the candidate set (see _REFRESH_TRIGGER for why candidacy keys on that one
    field and not on all of _REFRESH_FIELDS).

    Returns ``{checked, refreshed, summaries, capped, resynced}``; never raises —
    a late summary is never worth failing the hourly job.
    """
    out = {"checked": 0, "refreshed": 0, "summaries": 0, "capped": 0, "resynced": 0}
    cutoff = (now - timedelta(days=REFRESH_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    candidates = []
    for item in cat.get("items") or []:
        # str() every value read out of the catalog before using it: this is JSON
        # reloaded from the store, so a non-string is possible, and an unhashable
        # id (`"id": ["x"]`) would raise straight out of the pass — which, running
        # inside run()'s try, would abort the WHOLE hourly job before any document
        # ingested, and surface only as a logger line with no GitHub annotation.
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("id") or "")
        if not doc_id or doc_id not in id_to_pdf_key:
            continue
        if item.get(_REFRESH_TRIGGER):
            continue
        # An unparseable or absent published_at is kept IN scope: it means the
        # sidecar had no usable date either, which is the same half-written state
        # this pass exists to heal. Anchored parse, not a bare slice — a non-ISO
        # date like "07/28/2026" slices to "07/28/2026"[:10], which sorts BELOW
        # any "2026-…" cutoff and would silently exclude the row forever.
        pub = sidecar_mod.date_part(str(item.get("published_at") or ""))
        if pub and pub < cutoff:
            continue
        candidates.append(item)

    # Prioritize the rows a cap must NOT drop. Items are stored newest-first, but
    # _reindex sorts blank published_at LAST — and those are precisely the
    # half-written rows this pass exists for, so a naive head-slice would discard
    # the highest-priority candidates first. Undated ahead of dated, newest first
    # within each (the sort is stable, so the catalog order is preserved).
    candidates.sort(key=lambda it: bool(
        sidecar_mod.date_part(str(it.get("published_at") or ""))))

    if len(candidates) > REFRESH_MAX:
        out["capped"] = len(candidates) - REFRESH_MAX
        candidates = candidates[:REFRESH_MAX]
        print(f"::warning title=research_vault::sidecar refresh capped at "
              f"{REFRESH_MAX} — {out['capped']} older incomplete row(s) not "
              f"re-checked this run", flush=True)

    touched = False
    for item in candidates:
        doc_id = item["id"]
        try:
            raw = store.get_bytes(_sidecar_key(id_to_pdf_key[doc_id]))
            if not raw:
                continue
            out["checked"] += 1
            sc, bad_json = sidecar_mod.parse_json(raw)
            if bad_json or not sc:
                continue
            # Normalize for the COERCION only (bullet clamp, ticker upper-casing,
            # non-string drops) — every field outside _REFRESH_FIELDS, including
            # the fallback title/institution this call invents, is discarded.
            fresh = sidecar_mod.normalize(sc)
            changed = [f for f in _REFRESH_FIELDS
                       if not item.get(f) and fresh.get(f)]
            if not changed:
                continue
            for f in changed:
                item[f] = fresh[f]
            out["refreshed"] += 1
            touched = True
            log.info("research_vault: refreshed %s from its sidecar (%s)",
                     doc_id, ", ".join(changed))

            if "summary_points" in changed:
                out["summaries"] += 1
                # summary is an FTS column (weight 3) — the UPDATE trigger keeps
                # the postings in sync, so search sees the new bullets too.
                try:
                    conn.execute("UPDATE documents SET summary=? WHERE doc_id=?",
                                 (corpus_mod.summary_text(item), doc_id))
                except Exception as e:  # noqa: BLE001 — catalog is the public surface
                    log.warning("research_vault: corpus summary update failed for "
                                "%s: %s", doc_id, e)
        except Exception as e:  # noqa: BLE001 — one bad row never stops the pass
            log.warning("research_vault: sidecar refresh failed for %s: %s", doc_id, e)

    out["resynced"] = _resync_corpus_summaries(cat, conn)
    touched = touched or bool(out["resynced"])
    if touched:
        conn.commit()
    return out


# ---------------------------------------------------------------------------
# body re-extraction over the EXISTING corpus (a HOST fault froze these rows)
# ---------------------------------------------------------------------------

# Per-run bound on the re-extraction pass. Each candidate costs one R2 GET of a
# multi-MB PDF plus a pdftotext subprocess, and the hourly job has a 15-minute
# timeout it shares with the ingest itself — so a 127-row backlog drains over
# three runs rather than risking the batch. Small on purpose: the pass is
# self-quiescing (a healed row stops being a candidate), so a backlog only ever
# shrinks.
REEXTRACT_MAX = 50


def _reextract_bodies(store, conn, cap: int = REEXTRACT_MAX) -> dict:
    """Re-extract the body of published rows whose text never made it in.

    WHY this exists — the THIRD published-row repair, sibling to
    :func:`_repair_titles` and :func:`_refresh_sidecars`: receipts freeze an
    ingest-time MISTAKE as permanently as they freeze an ingest-time success. On
    2026-07-30 the ``macstudio-light`` runner label moved to a Mac without poppler,
    so ``shutil.which("pdftotext")`` failed in every hourly run for two days; each
    document ingested in that window was published with ``body=''`` and the honest
    ``text_layer='unavailable'`` stamp, was receipted, and could never re-ingest.
    127 rows were still bodyless when the host was healed — invisible to body
    search, and served to the Mastermind full-report reader as excerpt-only.
    ``unavailable`` is exactly the state that says "we know nothing about this
    document because OUR tool was broken", so it is the state a repair pass can
    act on without touching a single document-level fact.

    Candidacy is read from the CORPUS, not the catalog: ``text_layer`` is a
    server-side measured column (§5b keeps it out of the public catalog), so the
    corpus row is the only place the fault is recorded. ``text_layer IS NULL``
    rows join the queue behind them — they predate the probe entirely and carry no
    measured facts at all — but they are ordered LAST because, unlike the
    ``unavailable`` rows, they are not user-visibly broken.

    Load-bearing rules:

    - **Fill-only for ``body``.** A row that already holds text keeps it
      byte-for-byte; only an empty/NULL body is written. A NULL-``text_layer`` row
      is usually a fine pre-v2 row that simply was never measured, and re-extraction
      must not be allowed to shorten (or otherwise rewrite) text already published.
    - **Facts are ALWAYS stamped** (every measured value, not just the body). Even
      a scan-only PDF gets its measured columns, which re-classifies it to
      ``text_layer='none'`` — the honest "this document has no text" state — and
      drops it out of candidacy forever. That is the quiescence mechanism, and it
      is what lets a consumer tell "no text exists" apart from "text unreachable
      right now". A fact that came back UNKNOWN (None/'') is the one thing not
      written: on an already-published row that would delete a value rather than
      correct one.
    - **A missing vault PDF leaves the row COMPLETELY untouched.** Absence of the
      object is not evidence about the document, so stamping "none" over it would
      manufacture a fact out of a storage gap.
    - **A still-dead tool aborts the WHOLE pass at the first candidate.** If
      ``extract_pdf_text`` returns None the host is broken again; every further
      GET would burn bandwidth to learn the same thing, and no row may be stamped
      from an extraction that never ran.
    - **A plain UPDATE, never delete+insert.** The ``rv_docs_au`` trigger keeps the
      FTS postings in sync, so the re-extracted body becomes searchable in place.

    Returns ``{checked, bodies, facts_only, pdf_missing, remaining,
    aborted_tool_unavailable}``; ``remaining`` is the candidate count beyond the
    cap (0 = the backlog is drained). Never raises — a repair is never worth
    failing the hourly job — and never-raise-per-item, so one unreadable PDF
    cannot stop the pass.
    """
    out = {"checked": 0, "bodies": 0, "facts_only": 0, "pdf_missing": 0,
           "remaining": 0, "aborted_tool_unavailable": False}

    have = corpus_mod._existing_columns(conn)
    if "text_layer" not in have:
        # Pre-v2 corpus whose migration did not land: there is no fault column to
        # read, so there is nothing this pass can honestly select on.
        return out

    try:
        rows = conn.execute(
            "SELECT doc_id, body, text_layer FROM documents "
            "WHERE text_layer = 'unavailable' OR text_layer IS NULL "
            # 'unavailable' first (user-visibly broken), NULL after (never
            # measured); newest published_at first inside each group.
            "ORDER BY (text_layer IS NULL) ASC, published_at DESC"
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — an unreadable corpus is not fatal here
        log.warning("research_vault: body re-extraction query failed: %s", e)
        return out

    if not rows:
        return out
    if len(rows) > cap:
        out["remaining"] = len(rows) - cap
        rows = rows[:cap]

    # The columns we may stamp — intersected with the columns the database
    # ACTUALLY has, exactly like `upsert`, so a corpus whose migration partially
    # failed still repairs what it can instead of raising per row.
    fact_cols = [name for name, _decl in corpus_mod._V2_COLUMNS if name in have]

    touched = False
    for row in rows:
        doc_id = row["doc_id"]
        try:
            pdf_bytes = store.get_bytes(f"{VAULT_PREFIX}{doc_id}.pdf")
            if not pdf_bytes:
                out["pdf_missing"] += 1
                log.warning("research_vault: %s has no vault PDF — body left as-is",
                            doc_id)
                continue

            raw_text = extract_pdf_text(pdf_bytes)
            if raw_text is None:
                # HOST fault, again. Stop before we touch anything: no row may be
                # re-stamped from an extraction that did not run.
                out["aborted_tool_unavailable"] = True
                log.warning("research_vault: pdftotext still unavailable — body "
                            "re-extraction aborted (0 rows changed this run)")
                break

            out["checked"] += 1

            facts = probe_mod.probe(pdf_bytes)
            facts.update(probe_mod.text_facts(raw_text, facts.get("pages")))

            sets: list[str] = []
            params: list = []
            stored_body = row["body"] or ""
            new_body = (raw_text or "")[:corpus_mod.BODY_MAX_CHARS]
            filled = not stored_body and bool(new_body)
            if filled:
                sets.append("body=?")
                params.append(new_body)
            for name in fact_cols:
                # A null is not a measurement, and this row is ALREADY published:
                # stamping None/'' over a value it already carries would delete a
                # fact rather than correct one (the host that lost pdftotext could
                # equally lose pdfinfo, nulling every `pages` it touched). Same
                # asymmetry _ingest_one applies when it falls back to the sidecar's
                # page claim. `char_count=0`/`text_layer='none'` are MEASUREMENTS
                # and pass this gate — only unknowns are dropped.
                if name in facts and facts[name] not in (None, ""):
                    sets.append(f"{name}=?")
                    params.append(facts[name])
            if not sets:
                continue
            params.append(doc_id)
            conn.execute(f"UPDATE documents SET {','.join(sets)} WHERE doc_id=?",
                         params)
            touched = True
            if filled:
                out["bodies"] += 1
                log.info("research_vault: re-extracted %s chars of body for %s "
                         "(text_layer %s -> %s)", len(new_body), doc_id,
                         row["text_layer"], facts.get("text_layer"))
            else:
                out["facts_only"] += 1
        except Exception as e:  # noqa: BLE001 — one bad row never stops the pass
            log.warning("research_vault: body re-extraction failed for %s: %s",
                        doc_id, e)

    if touched:
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
         sidecars_checked, sidecars_refreshed, summaries_recovered, sidecars_capped,
         summaries_resynced,
         bodies_reextracted, reextract_facts_only, reextract_checked,
         reextract_pdf_missing, reextract_remaining[, reextract_aborted],
         coverage, catalog_bytes[, corpus_published][, error]}

    ``coverage`` is the per-field fill rate over the final catalog
    (:func:`catalog.coverage`) — the signal that ``needs_metadata`` cannot give,
    since it never inspects desk/tags/tickers/pages.

    ``catalog_bytes`` is the serialized catalog.json (so the CLI can snapshot it to
    the repo). ``dry_run=True`` runs the full pipeline but mutates NOTHING in the
    store: no PDF promotion, no receipts, no catalog write, no corpus publish —
    the counts still report what a real run WOULD do. The one pass a dry run does
    not perform at all is :func:`_reextract_bodies`: it is pure mutation of rows
    that are ALREADY published, so there is no "would do" for it to report.
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

        done_pdf_keys, id_to_pdf_key = _processed_index(store)

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

        # Re-read the sidecars of rows still missing summary_points. The upstream
        # fills them asynchronously, so the copy we read at first sight is routinely
        # the half-written one (see _refresh_sidecars).
        #
        # AFTER the ingest loop, not before: upsert_item does a whole-ROW replace,
        # so a report re-dropped under a second filename with the SAME explicit
        # sidecar id would overwrite a just-recovered summary with that second
        # sidecar's still-empty one — shipping "Summary pending" while the run
        # reported summaries_recovered=1, and flapping every hour. Running last
        # means the refresh sees the post-ingest row and heals it from the sidecar
        # the receipt actually points at.
        ref = _refresh_sidecars(store, cat, conn, id_to_pdf_key, now)
        summary["sidecars_checked"] = ref["checked"]
        summary["sidecars_refreshed"] = ref["refreshed"]
        summary["summaries_recovered"] = ref["summaries"]
        summary["sidecars_capped"] = ref["capped"]
        summary["summaries_resynced"] = ref["resynced"]

        # Re-extract the bodies of rows that were published while the HOST was
        # broken (see _reextract_bodies). Pure mutation of already-published rows,
        # so a dry run — which publishes nothing — must not perform it at all;
        # reporting a heal that was never written would be simply false.
        if not dry_run:
            rex = _reextract_bodies(store, conn)
            summary["bodies_reextracted"] = rex["bodies"]
            summary["reextract_facts_only"] = rex["facts_only"]
            summary["reextract_checked"] = rex["checked"]
            summary["reextract_pdf_missing"] = rex["pdf_missing"]
            summary["reextract_remaining"] = rex["remaining"]
            if rex["aborted_tool_unavailable"]:
                summary["reextract_aborted"] = True

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
