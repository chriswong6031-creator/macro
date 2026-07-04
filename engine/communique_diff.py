"""Communiqué Diff — discrete, dated, backtestable events from official policy language.

LEAF · SALIENCE-ONLY · DETERMINISTIC · NO NETWORK · NO CLOCK IN LIB LOGIC. This is
the ONE China path to standalone validation (spec D9 / §2.2 / Appendix P4): rather
than a bag-of-words tone (which misses the actual signal — CN-QUAL-6), it detects
verbatim canonical-formula shifts across a running window of official documents.

The signal is in ordering, elevation, and FORMULA presence/absence. Three event
types per new document (against that organ's trailing N-window):

  APPEARED   — a phrase from the phrase book is present in this document but ABSENT
               from the organ's trailing window (first reappearance of 适度宽松).
  DROPPED    — a phrase present in the organ's prior comparable document/window is
               absent now (房住不炒 dropped from the readout).
  LEAD_SHIFT — the People's Daily front-page LEAD ITEM's dominant policy domain
               shifted vs the prior day (layout order = editorial prominence, D9).

Each event is emitted TWICE:
  1. into qbus as a discrete item (theme=policy, entities where mappable), so it
     joins the unified store + fattens the Missing-Tape baseline; AND
  2. as a SALIENCE-ONLY qledger claim (desk=communique_diff, direction=0,
     horizon 21, claim_family=communique_diff) — the forward log starts accruing
     TODAY. direction=0 because polarity is human-review-PROVISIONAL (§5): UNSIGNED
     events are safe immediately; a signed phrase-return map is deferred (D9).

COLD-START (documented rule): with no trailing window for an organ (fresh deploy,
first crawl of an organ), we CANNOT distinguish "appeared" from "always present".
So on cold start we emit NOTHING for APPEARED/DROPPED for that organ and record a
`cold_start` marker; the window has to accrue at least one prior comparable
document before appear/drop fire. LEAD_SHIFT needs two consecutive People's Daily
days. This avoids a first-run flood of false "appeared" events.

Phrase matching handles VARIANT forms: 适度宽松 matches 适度宽松的货币政策 (the
canonical zh OR any listed variant counts as the same formula). Matching is on the
raw document text (title + body), substring — Chinese has no word breaks so
substring is the correct primitive.

Nothing here is ever a scoring input beyond the salience lane; direction is 0.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "communique_diff.v1"
CLAIM_FAMILY = "communique_diff"
DESK = "communique_diff"
HORIZON_D = 21   # spec D9: horizon 21

_PHRASE_BOOK_REL = ("data", "china_official", "phrase_book.yml")


# --------------------------------------------------------------------------- #
# phrase book — load + index (canonical zh OR variant → phrase record)
# --------------------------------------------------------------------------- #
def _phrase_book_path(root: Path | str | None = None) -> Path:
    from lib import config
    base = Path(root) if root else config.ROOT
    return base.joinpath(*_PHRASE_BOOK_REL)


def load_phrase_book(root: Path | str | None = None) -> list[dict]:
    """The phrase records from data/china_official/phrase_book.yml. Each record:
    {zh, gloss, domain, polarity, review_status, variants?}. Returns [] if the file
    is missing/unparseable. Never raises."""
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return []
    p = _phrase_book_path(root)
    if not p.exists():
        return []
    try:
        blob = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("communique_diff: phrase_book load failed (%s)", e)
        return []
    phrases = blob.get("phrases") if isinstance(blob, dict) else None
    return [p for p in (phrases or []) if isinstance(p, dict) and p.get("zh")]


def _surface_forms(rec: dict) -> list[str]:
    """All surface strings that count as this phrase (canonical + variants). PURE."""
    forms = [str(rec.get("zh") or "")]
    for v in (rec.get("variants") or []):
        if v:
            forms.append(str(v))
    return [f for f in forms if f]


def phrases_in_text(text: str, book: list[dict]) -> set[str]:
    """The set of canonical phrase `zh` keys whose canonical form OR any variant
    appears (substring) in `text`. Variant match maps back to the canonical zh so
    适度宽松的货币政策 registers as 适度宽松. PURE. Never raises."""
    blob = text or ""
    if not blob:
        return set()
    hits: set[str] = set()
    for rec in book:
        zh = str(rec.get("zh") or "")
        if not zh:
            continue
        for form in _surface_forms(rec):
            if form and form in blob:
                hits.add(zh)
                break
    return hits


def phrase_meta(book: list[dict]) -> dict[str, dict]:
    """Index canonical zh → {gloss, domain, polarity, review_status}. PURE."""
    out: dict[str, dict] = {}
    for rec in book:
        zh = str(rec.get("zh") or "")
        if zh:
            out[zh] = {
                "gloss": rec.get("gloss", ""),
                "domain": rec.get("domain", ""),
                "polarity": rec.get("polarity", 0),
                "review_status": rec.get("review_status", "PROVISIONAL"),
            }
    return out


# --------------------------------------------------------------------------- #
# document access — a "document" is one corpus row (title + body). The trailing
# window is prior documents from the SAME organ (comparable-document diff).
# --------------------------------------------------------------------------- #
def _doc_text(row: dict) -> str:
    return f"{row.get('title', '')} {row.get('body', '')}"


def _crawl_day(row: dict) -> str:
    return (str(row.get("_crawled_at") or "")[:10]
            or str(row.get("seendate") or "")[:10])


def _window_phrases(prior_rows: list[dict], book: list[dict]) -> set[str]:
    """Union of phrases present across all prior documents in the window. PURE."""
    acc: set[str] = set()
    for r in prior_rows:
        acc |= phrases_in_text(_doc_text(r), book)
    return acc


# --------------------------------------------------------------------------- #
# event id — stable, content-defined
# --------------------------------------------------------------------------- #
def _event_id(kind: str, organ: str, asof: str, key: str) -> str:
    basis = f"{kind}|{organ}|{asof}|{key}"
    return "cd_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:13]


# --------------------------------------------------------------------------- #
# core diff — appeared / dropped per organ, lead-shift for People's Daily
# --------------------------------------------------------------------------- #
def diff_organ(organ: str, today_rows: list[dict], prior_rows: list[dict],
               book: list[dict], asof: str) -> tuple[list[dict], bool]:
    """Diff one organ's TODAY documents against its PRIOR-window documents.

    Returns (events, cold_start). cold_start=True when there is no prior window
    for this organ — in which case NO appeared/dropped events are emitted (see the
    cold-start rule): we cannot tell "appeared" from "always present" yet.

    Event dicts (kind ∈ {APPEARED, DROPPED}):
      {event_id, kind, organ, phrase, gloss, domain, polarity, review_status,
       asof, evidence_url, evidence_title}
    PURE. Never raises."""
    events: list[dict] = []
    if not today_rows:
        return events, False

    today_phrases = _window_phrases(today_rows, book)
    meta = phrase_meta(book)

    if not prior_rows:
        # COLD START: no comparable prior document for this organ.
        return events, True

    prior_phrases = _window_phrases(prior_rows, book)

    # a representative today-document per phrase for the evidence link
    def _evidence(ph: str) -> dict:
        for r in today_rows:
            if ph in phrases_in_text(_doc_text(r), book):
                return {"url": r.get("url", ""), "title": r.get("title", "")}
        return {"url": "", "title": ""}

    appeared = sorted(today_phrases - prior_phrases)
    dropped = sorted(prior_phrases - today_phrases)

    for ph in appeared:
        ev = _evidence(ph)
        m = meta.get(ph, {})
        events.append({
            "event_id": _event_id("APPEARED", organ, asof, ph),
            "kind": "APPEARED", "organ": organ, "phrase": ph,
            "gloss": m.get("gloss", ""), "domain": m.get("domain", ""),
            "polarity": m.get("polarity", 0),
            "review_status": m.get("review_status", "PROVISIONAL"),
            "asof": asof, "evidence_url": ev["url"], "evidence_title": ev["title"],
        })
    for ph in dropped:
        m = meta.get(ph, {})
        # dropped evidence is the prior document that carried it
        ev = {"url": "", "title": ""}
        for r in prior_rows:
            if ph in phrases_in_text(_doc_text(r), book):
                ev = {"url": r.get("url", ""), "title": r.get("title", "")}
                break
        events.append({
            "event_id": _event_id("DROPPED", organ, asof, ph),
            "kind": "DROPPED", "organ": organ, "phrase": ph,
            "gloss": m.get("gloss", ""), "domain": m.get("domain", ""),
            "polarity": m.get("polarity", 0),
            "review_status": m.get("review_status", "PROVISIONAL"),
            "asof": asof, "evidence_url": ev["url"], "evidence_title": ev["title"],
        })
    return events, False


def lead_domain(layout_rows: list[dict], book: list[dict]) -> str | None:
    """The dominant policy DOMAIN of the People's Daily front-page LEAD ITEM(s).

    Reads the lowest-layout_rank documents (the front-page lead) and returns the
    domain of the first phrase-book phrase they carry (order = prominence, D9).
    Returns None when the lead carries no known formula. PURE."""
    rows = [r for r in layout_rows if int(r.get("layout_rank", -1)) >= 0]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: int(r.get("layout_rank", 0)))
    meta = phrase_meta(book)
    # scan from the top of the page; first known-phrase domain wins
    for r in rows:
        for ph in phrases_in_text(_doc_text(r), book):
            dom = meta.get(ph, {}).get("domain")
            if dom:
                return dom
    return None


def diff_lead_shift(today_layout: list[dict], prior_layout: list[dict],
                    book: list[dict], organ: str, asof: str) -> list[dict]:
    """LEAD_SHIFT event when the People's Daily front-page lead DOMAIN changed vs
    the prior comparable day. Needs both days to resolve a lead domain; otherwise
    emits nothing (cold-start for the layout leg). PURE. Never raises."""
    today_dom = lead_domain(today_layout, book)
    prior_dom = lead_domain(prior_layout, book)
    if today_dom is None or prior_dom is None or today_dom == prior_dom:
        return []
    return [{
        "event_id": _event_id("LEAD_SHIFT", organ, asof, f"{prior_dom}->{today_dom}"),
        "kind": "LEAD_SHIFT", "organ": organ, "phrase": "",
        "from_domain": prior_dom, "to_domain": today_dom,
        "domain": today_dom, "polarity": 0, "review_status": "PROVISIONAL",
        "asof": asof, "evidence_url": "", "evidence_title": "",
    }]


# --------------------------------------------------------------------------- #
# orchestration over the corpus — split today vs trailing window per organ
# --------------------------------------------------------------------------- #
def _split_today_prior(rows: list[dict], asof_day: str,
                       window_days: int) -> tuple[list[dict], list[dict]]:
    """Partition an organ's rows into (today == asof_day crawl) vs (prior window,
    the `window_days` crawl-days BEFORE asof). PURE."""
    today: list[dict] = []
    prior: list[dict] = []
    try:
        lo = (date.fromisoformat(asof_day) -
              timedelta(days=window_days)).isoformat()
    except (ValueError, TypeError):
        lo = ""
    for r in rows:
        d = _crawl_day(r)
        if d == asof_day:
            today.append(r)
        elif lo and lo <= d < asof_day:
            prior.append(r)
    return today, prior


def compute_events(corpus_rows: list[dict], asof: str,
                   book: list[dict] | None = None,
                   window_days: int = 30) -> dict:
    """The full diff pass over a corpus (list of corpus-row dicts) for one asof
    day. Groups by organ, splits today vs trailing window, runs appeared/dropped +
    lead-shift, and returns:

      {asof, events: [...], cold_start_organs: [...], counts: {...}}

    PURE (asof passed; no clock, no network). Never raises. This is what the
    build script calls and what the tests exercise directly on fixtures."""
    book = book if book is not None else load_phrase_book()
    asof_day = str(asof)[:10]

    by_organ: dict[str, list[dict]] = {}
    for r in corpus_rows or []:
        by_organ.setdefault(str(r.get("organ") or ""), []).append(r)

    events: list[dict] = []
    cold: list[str] = []

    for organ, rows in by_organ.items():
        if not organ:
            continue
        today_rows, prior_rows = _split_today_prior(rows, asof_day, window_days)
        if not today_rows:
            continue
        # appeared / dropped
        evs, cold_start = diff_organ(organ, today_rows, prior_rows, book, asof_day)
        events.extend(evs)
        if cold_start:
            cold.append(organ)
        # lead-shift only for the layout organ (People's Daily); compare today's
        # lead vs the most recent prior crawl day's lead.
        if any(int(r.get("layout_rank", -1)) >= 0 for r in today_rows):
            prior_days = sorted({_crawl_day(r) for r in prior_rows
                                 if _crawl_day(r) < asof_day}, reverse=True)
            prior_layout: list[dict] = []
            if prior_days:
                pd_day = prior_days[0]
                prior_layout = [r for r in prior_rows if _crawl_day(r) == pd_day]
            events.extend(
                diff_lead_shift(today_rows, prior_layout, book, organ, asof_day))

    counts = {
        "n_events": len(events),
        "n_appeared": sum(1 for e in events if e["kind"] == "APPEARED"),
        "n_dropped": sum(1 for e in events if e["kind"] == "DROPPED"),
        "n_lead_shift": sum(1 for e in events if e["kind"] == "LEAD_SHIFT"),
        "n_cold_start_organs": len(cold),
    }
    return {"schema": SCHEMA, "asof": asof_day, "events": events,
            "cold_start_organs": sorted(cold), "counts": counts}


# --------------------------------------------------------------------------- #
# entity mapping (best-effort; events are typically macro/policy, no ticker)
# --------------------------------------------------------------------------- #
def _entities_for(event: dict) -> list[str]:
    """Map an event's evidence text → A-share tickers where the entity resolver
    finds any (usually none for policy formulas — that is fine, the claim is macro/
    salience). Never raises."""
    try:
        from engine import entity_resolver
        text = " ".join([str(event.get("evidence_title") or ""),
                         str(event.get("phrase") or "")])
        return [h["ticker"] for h in entity_resolver.resolve_cn(text)][:5]
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------- #
# emit — qbus item rows + salience-only qledger claims
# --------------------------------------------------------------------------- #
def _event_title(e: dict) -> str:
    if e["kind"] == "LEAD_SHIFT":
        return (f"[人民日报头版] 领衔议题 {e.get('from_domain')} → "
                f"{e.get('to_domain')}")
    verb = "重现" if e["kind"] == "APPEARED" else "淡出"
    return f"[{e.get('organ')}] {e.get('phrase')} {verb} ({e.get('gloss')})"


def _to_qbus_rows(result: dict, crawled_at: str) -> list[dict]:
    rows: list[dict] = []
    for e in result.get("events", []):
        rows.append({
            "desk": DESK,
            "source": "communique_diff",
            "source_tier": 1,
            "lang": "zh",
            "url": e.get("evidence_url", ""),
            "title": _event_title(e),
            "body_sha256": "",
            "seendate": result.get("asof", ""),
            "_crawled_at": crawled_at,
            "timestamp_quality": "CRAWL_BOUNDED",
            "entities": _entities_for(e),
            "themes": ["policy"],
            "importance_raw": 0.0,
        })
    return rows


def emit_to_qbus(result: dict, crawled_at: str) -> int:
    """Emit diff events into qbus (theme=policy). Returns count; 0 on failure."""
    rows = _to_qbus_rows(result, crawled_at)
    if not rows:
        return 0
    try:
        from engine import qbus
        qbus.append_items(rows, assign_keys=True)
        return len(rows)
    except Exception as e:  # noqa: BLE001
        log.warning("communique_diff: qbus emit failed (%s)", e)
        return 0


def register_claims(result: dict, root: Path | str | None = None) -> int:
    """Register each diff event as a SALIENCE-ONLY qledger claim (direction=0,
    horizon 21, claim_family=communique_diff). The forward log starts accruing
    today. Returns the number of claims registered; 0 on failure.

    scope: entity when the event mapped to a ticker, else macro (a policy formula
    with no ticker proxy grades as a macro claim against a named observable — here
    the CSI-300 ETF 510300.SS, the China event-move benchmark [P1], so the claim is
    machine-checkable per D4). direction=0 keeps it salience-only regardless of the
    phrase's PROVISIONAL polarity."""
    try:
        from engine import qledger
    except Exception as e:  # noqa: BLE001
        log.warning("communique_diff: qledger import failed (%s)", e)
        return 0

    # W0 Stage B-e: build the claim list first, then ONE register_batch() call —
    # register() re-reads the whole claims file per call (O(file)); this loop was
    # the ledger's highest-volume writer. Per-claim error isolation is preserved
    # (make_claim failures skip the event; batch slots that error are counted out).
    pending: list[dict] = []
    for e in result.get("events", []):
        asof = e.get("asof") or result.get("asof")
        ents = _entities_for(e)
        try:
            if ents:
                for tk in ents:
                    pending.append(qledger.make_claim(
                        desk=DESK, asof=asof, scope_type="entity", scope_key=tk,
                        direction=0, horizon_d=HORIZON_D,
                        timestamp_quality="CRAWL_BOUNDED",
                        claim_family=CLAIM_FAMILY,
                        extra={"event_id": e.get("event_id"),
                               "event_kind": e.get("kind"),
                               "phrase": e.get("phrase"),
                               "organ": e.get("organ"),
                               "polarity": e.get("polarity"),
                               "review_status": e.get("review_status"),
                               "salt": e.get("event_id")},
                    ))
            else:
                # macro claim vs the CSI-300 ETF (machine-checkable observable, D4)
                pending.append(qledger.make_claim(
                    desk=DESK, asof=asof, scope_type="macro",
                    scope_key="510300.SS", direction=0, horizon_d=HORIZON_D,
                    timestamp_quality="CRAWL_BOUNDED",
                    bench="510300.SS", claim_family=CLAIM_FAMILY,
                    extra={"event_id": e.get("event_id"),
                           "event_kind": e.get("kind"),
                           "phrase": e.get("phrase"),
                           "organ": e.get("organ"),
                           "polarity": e.get("polarity"),
                           "review_status": e.get("review_status"),
                           "salt": e.get("event_id")},
                ))
        except Exception as ex:  # noqa: BLE001 — one bad event never sinks the batch
            log.debug("communique_diff: claim build failed for %s (%s)",
                      e.get("event_id"), ex)
    if not pending:
        return 0
    results = qledger.register_batch(pending, root=root)
    n = sum(1 for r in results if r.get("status") != "error")
    return n


# --------------------------------------------------------------------------- #
# public: the live diff run (fetch already done by the collector; we read corpus)
# --------------------------------------------------------------------------- #
def run(asof: date | str | None = None, root: Path | str | None = None,
        window_days: int | None = None) -> dict | None:
    """Read the accrued official corpus, compute diff events for `asof`, emit to
    qbus, and register salience-only qledger claims. Returns the result dict (with
    counts) or None if the corpus is empty. Never raises into the build.

    `asof` defaults to today (the ONE clock read, at the ingest boundary, matching
    the qual-suite convention that library logic stays clock-free but the public
    entry may stamp now)."""
    try:
        from collectors import china_official_corpora as coc
    except Exception as e:  # noqa: BLE001
        log.warning("communique_diff.run: corpus reader import failed (%s)", e)
        return None

    from lib import config
    cfg = (config.load().get("communique_diff", {}) or {})
    win = int(window_days if window_days is not None
              else cfg.get("window_days", 30))

    corpus = coc.read_corpus(days=cfg.get("corpus_read_days"))
    if corpus is None or len(corpus) == 0:
        log.info("communique_diff.run: no corpus accrued yet — nothing to diff")
        return None

    asof_day = (asof.isoformat() if isinstance(asof, date)
                else str(asof)[:10] if asof else date.today().isoformat())
    crawled_at = datetime.now(timezone.utc).isoformat()

    rows = corpus.to_dict("records")
    book = load_phrase_book(root)
    result = compute_events(rows, asof_day, book=book, window_days=win)

    n_bus = emit_to_qbus(result, crawled_at)
    n_claims = register_claims(result, root=root)
    result["n_qbus"] = n_bus
    result["n_claims"] = n_claims
    result["is_context_only"] = True
    log.info("communique_diff.run: %s events (%s appeared / %s dropped / "
             "%s lead-shift) — %d→qbus, %d→qledger, cold_start=%s",
             result["counts"]["n_events"], result["counts"]["n_appeared"],
             result["counts"]["n_dropped"], result["counts"]["n_lead_shift"],
             n_bus, n_claims, result["cold_start_organs"])
    return result
