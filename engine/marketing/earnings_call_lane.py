"""Deterministic Chronicle earnings-call derivative for the X outbox.

NOT WIRED TO ANYTHING TODAY (stated plainly, 2026-08-06). Nothing in
``engine/``, ``scripts/``, ``app/`` or ``.github/`` calls :func:`enqueue_event`
or :func:`run_ledger`; the only callers are under ``tests/``, and the two
mentions elsewhere are inert (a comment in ``config/marketing.yml`` and an
artifact row in ``config/synapse.yml``). Read that before spending review budget
here, and before treating a green test in this module as evidence about the live
timeline: three rounds of card-gate review hardened this lane, and
``tests/test_marketing_card_earns_pixels.py::test_dispatch_does_not_blanket_drop_every_card``
— the suite's only demonstration that a real emission can still KEEP its card —
proves it through this lane and not through the press wire. Wiring it or
deleting it is an open operator decision, not a builder's call; until one is
made, the module is kept correct rather than left to rot, because a dormant lane
that is wrong is worse than one that is right.

This is a projection, not another research engine.  Its only input is the
committed :mod:`engine.chronicle.earnings_calls` ``earnings.call_event.v1``
ledger.  The qualitative model has already done its work upstream; this module
only selects cited facts, applies the existing marketing gates, renders the
existing card family, and enters the canonical outbox.

Public contract:

``compose_event``
    Pure, deterministic native-post copy.  It never calls a model and always
    labels the output as research context rather than trading advice.

``build_outbox_item``
    Builds ``marketing.outbox/v1`` through ``outbox.make_item`` and stamps the
    existing Gift-Grip-Proof verdict.  Provenance carries the committed event
    id, transcript revision hash, source URL, and source-record id.

``enqueue_event``
    Reuses wire routing, the cross-account story lock, copy validation,
    preflight/durable outbox dedupe, card publishing, and the value gate.  A
    rerun of the same event revision is refused *before* rendering.  A newer
    revision of an already-emitted company-period is returned as an explicit
    ``correction_required`` receipt; it is never appended as an unlabeled
    second post.

``run_ledger``
    Reads only the committed ledger.  By default it admits calls from the last
    two calendar days and at most eight rows, preventing a first deployment
    from turning a historical transcript backfill into an X flood.

The one-owner identity is exactly
``earnings-call:<ticker>:<quarter>:<year>``.  X/Buffer has no self-reply
threading seam today, so the native post stays link-free and the transcript
citation plus optional article URL remain in provenance for a future reply
actuator.  We do not pretend a reply was scheduled when the publisher cannot
send one.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from engine.chronicle.earnings_calls import (
    call_event_available_as_of,
    load_call_events,
    sanitize_untrusted_prose,
    validate_call_event,
)


LANE = "earnings_call"
PROVENANCE = "earnings_call_lane"
EVENT_CLASS = "earnings"
PRIORITY = 1
DEFAULT_MAX_CALL_AGE_DAYS = 2
DEFAULT_MAX_EVENTS = 8

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", re.I)
_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?")
_SAFE_TONE_RE = re.compile(r"^[a-z][a-z -]{0,31}$")
_ADVICE_RE = re.compile(
    r"\b(?:buy|sell|overweight|underweight|price target|target price|"
    r"entry (?:point|level)|exit (?:point|level)|go (?:long|short)|"
    r"stay (?:long|short)|trade setup|position sizing|call options?|"
    r"put options?)\b",
    re.I,
)
_TRAILING_PUNCT = ".!?;:,"
_DISCLAIMER = "Research context only, not a trading recommendation."


def _utc(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clean(value: object, max_chars: int = 400) -> str:
    text = _URL_RE.sub("", str(value or ""))
    text = text.replace("\u2014", "-").replace("\u2013", "-").replace("\u2015", "-")
    return _WS_RE.sub(" ", text).strip()[:max_chars].strip()


def _http_url(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _short_clause(value: object, max_chars: int) -> str:
    """A qualitative clause with no advice language or ungrounded numerics.

    Summaries and highlights are model-produced upstream.  A number appearing
    in that prose is therefore not its own receipt and cannot become grounded
    merely because we copied it into ``numbers_whitelist``.  The call-event
    contract currently has no structured numeric-fact collection, so numeric
    model clauses are omitted in full.  Period numerics are supplied separately
    by :func:`_structured_numbers` from the event's quarter/year fields.
    """

    text = sanitize_untrusted_prose(
        _clean(value, max_chars=max_chars * 2), max_len=max_chars * 2,
    ).strip(_TRAILING_PUNCT + " ")
    if not text or _ADVICE_RE.search(text) or _NUMBER_RE.search(text):
        return ""
    if len(text) > max_chars:
        cut = text[: max_chars + 1].rsplit(" ", 1)[0].strip(_TRAILING_PUNCT + " ")
        text = cut
    return f"{text}." if text else ""


def _safe_tone(value: object) -> str:
    tone = _clean(value, 32).lower().strip(_TRAILING_PUNCT + " ")
    if not _SAFE_TONE_RE.fullmatch(tone):
        return "mixed"
    try:
        from engine.marketing.copywriter import banned_language

        if banned_language(tone):
            return "mixed"
    except Exception:
        return "mixed"
    return tone


def _structured_numbers(event: Mapping[str, Any]) -> list[str]:
    """Numbers independently grounded by structured company-period fields."""

    quarter = str(event.get("quarter") or "").upper().strip()
    match = re.fullmatch(r"Q([1-4])", quarter)
    try:
        year = str(int(event.get("year")))
    except (TypeError, ValueError):
        year = ""
    return list(dict.fromkeys([
        *(match.groups() if match else ()),
        *([year] if year else []),
    ]))


def _valid_event(event: Mapping[str, Any]) -> None:
    if event.get("is_context_only") is not True:
        # This is the publication authority boundary, not an incidental schema
        # detail, so name it even when other fields are malformed too.
        raise ValueError("earnings-call X derivatives must be context-only")
    problems = validate_call_event(dict(event))
    if problems:
        raise ValueError("invalid earnings.call_event.v1: " + "; ".join(problems))


def story_identity(event: Mapping[str, Any]) -> str:
    """Return the single fleet-wide identity for this company-period call."""

    ticker = str(event.get("ticker") or "").upper().strip()
    quarter = str(event.get("quarter") or "").upper().strip()
    try:
        year = int(event.get("year"))
    except (TypeError, ValueError) as exc:
        raise ValueError("earnings-call event year is invalid") from exc
    if not ticker or not re.fullmatch(r"Q[1-4]", quarter):
        raise ValueError("earnings-call event ticker/quarter is invalid")
    return f"earnings-call:{ticker}:{quarter}:{year}"


def _candidate_bodies(event: Mapping[str, Any]) -> list[str]:
    positives = event.get("positive_highlights") or []
    negatives = event.get("negative_highlights") or []
    def first_safe(items: Iterable[object]) -> str:
        for item in items:
            clause = _short_clause(item, 82)
            if clause:
                return clause
        return ""

    pos = first_safe(positives)
    neg = first_safe(negatives)
    summary = _short_clause(event.get("summary"), 145)

    candidates: list[str] = []
    if pos and neg:
        candidates.append(f"Strong point: {pos} Risk noted: {neg} {_DISCLAIMER}")
    if summary:
        candidates.append(f"{summary} {_DISCLAIMER}")
    if pos:
        candidates.append(f"Strong point: {pos} {_DISCLAIMER}")
    if neg:
        candidates.append(f"Risk noted: {neg} {_DISCLAIMER}")
    candidates.append(
        "Management's remarks are saved as research context only, not a trading "
        "recommendation."
    )
    return list(dict.fromkeys(candidates))


def compose_event(
    event: Mapping[str, Any],
    *,
    account: str = "flagship",
    as_of: str | None = None,
) -> dict[str, Any]:
    """Compose deterministic, validated X copy for one committed call event."""

    _valid_event(event)
    ticker = str(event["ticker"]).upper()
    quarter = str(event["quarter"]).upper()
    year = int(event["year"])
    tone = _safe_tone(event.get("tone_word"))
    headline = f"${ticker} {quarter} FY{year} call: {tone} tone."
    as_of = as_of or str(event["call_date"])

    from engine.marketing.copywriter import validate_copy

    last_violations: list[str] = []
    numbers = _structured_numbers(event)
    for body in _candidate_bodies(event):
        ctx = {
            "ticker": ticker,
            "cashtag": f"${ticker}",
            "type": "earnings",
            "account": str(account),
            "as_of": as_of,
            "numbers_whitelist": numbers,
            "emoji_budget": 0,
            "voice": "dry, receipts-forward",
            "persona_name": "The Scorekeeper",
        }
        violations = validate_copy(headline, body, ctx)
        if not violations and not _ADVICE_RE.search(f"{headline} {body}".replace(_DISCLAIMER, "")):
            return {
                "headline": headline,
                "body": body,
                "text": f"{headline}\n\n{body}",
                "numbers_whitelist": numbers,
                "story_key": story_identity(event),
            }
        last_violations = violations
    raise ValueError("earnings-call copy failed validation: " + "; ".join(last_violations))


def _provenance(
    event: Mapping[str, Any],
    composed: Mapping[str, Any],
    *,
    article_url: str = "",
) -> dict[str, Any]:
    source_url = _http_url(event.get("source_url"))
    if not source_url:
        raise ValueError("earnings-call source_url is not public HTTP(S)")
    article = _http_url(article_url)
    return {
        "lane": LANE,
        "event_id": str(event["id"]),
        "story_key": str(composed["story_key"]),
        "revision_sha256": str(event["source_sha256"]),
        "source_sha256": str(event["source_sha256"]),
        "source_url": source_url,
        "source_record_id": str(event["source_record_id"]),
        "citation_url": article or source_url,
        "article_url": article or None,
        "ticker": str(event["ticker"]).upper(),
        "quarter": str(event["quarter"]).upper(),
        "year": int(event["year"]),
        "call_date": str(event["call_date"]),
        "source_updated_at": str(event["source_updated_at"]),
        "context_only": True,
        "is_context_only": True,
        "numbers_whitelist": list(composed.get("numbers_whitelist") or []),
    }


def build_outbox_item(
    event: Mapping[str, Any],
    *,
    account: str,
    now: datetime,
    media: list[dict[str, Any]],
    cfg: dict | None = None,
    article_url: str = "",
    card_withheld: bool = False,
) -> dict[str, Any]:
    """Build one canonical outbox row and apply the shared value gate.

    ``card_withheld`` says the card was drawn and deliberately not printed
    because it restated the post. It is the ONLY way past the hosted-card
    requirement below, and it is not a way past a failed upload — see
    press_lane._emit_outbox_item for why the two must never read alike.
    """

    from engine.marketing import outbox

    now = _utc(now)
    if not card_withheld and (
        not media or not any(_http_url(entry.get("media_url")) for entry in media)
    ):
        raise ValueError("earnings-call ticker posts require a hosted card")
    composed = compose_event(event, account=account, as_of=now.date().isoformat())
    source = _provenance(event, composed, article_url=article_url)
    if card_withheld:
        source["card_withheld_for_value"] = True
    would_abstain = outbox.stamp_value_gate(
        source,
        headline=str(composed["headline"]),
        body=str(composed["body"]),
        kind="earnings",
        has_media=bool(media),
        media_withheld=bool(card_withheld),
        numbers_whitelist=composed["numbers_whitelist"],
        citation=source["citation_url"],
        cfg=cfg,
    )
    gate_enforced = outbox._value_gate_enforced(cfg, "earnings")
    if isinstance(source.get("value_gate"), dict):
        # stamp_value_gate's legacy metadata call has no kind argument.  The
        # decision here does, so record the answer this lane actually applied.
        source["value_gate"]["enforced"] = gate_enforced
    if would_abstain and gate_enforced:
        reasons = ",".join((source.get("value_gate") or {}).get("reasons") or [])
        raise ValueError(f"value_gate_abstain:{reasons}")

    item = outbox.make_item(
        account=account,
        kind="earnings",
        text=str(composed["text"]),
        as_of=now.date().isoformat(),
        media=media,
        scheduled_at="immediate",
        priority=PRIORITY,
        provenance=PROVENANCE,
        source=source,
        now=now,
    )
    item["immediate"] = True
    item["headline"] = composed["headline"]
    item["body"] = composed["body"]
    problems = outbox.validate_item(item)
    if problems:
        raise ValueError("invalid marketing.outbox/v1: " + "; ".join(problems))
    return item


def _same_revision_already_emitted(event: Mapping[str, Any], items: Iterable[dict]) -> bool:
    event_id = str(event.get("id") or "")
    revision = str(event.get("source_sha256") or "")
    for item in items:
        source = item.get("source") if isinstance(item, dict) else None
        if not isinstance(source, dict) or source.get("lane") != LANE:
            continue
        if str(source.get("event_id") or "") != event_id:
            continue
        if str(source.get("revision_sha256") or "") == revision:
            return True
    return False


def _prior_revision_emission(
    event: Mapping[str, Any], items: Iterable[dict],
) -> dict[str, Any] | None:
    """Return a prior emission of this story with a different revision.

    There is a canonical rewrite seam, but it cannot safely serve as a general
    correction actuator here: its status fold sees only the tracked outbox, not
    daemon-spooled items, and identical replacement copy is deliberately a
    no-op (which would retain stale revision provenance).  Until the outbox owns
    an atomic correction API across both stores, fail closed and name the prior
    item instead of risking two live versions.
    """

    event_id = str(event.get("id") or "")
    source_record_id = str(event.get("source_record_id") or "")
    revision = str(event.get("source_sha256") or "")
    story_key = story_identity(event)
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if not isinstance(source, dict) or source.get("lane") != LANE:
            continue
        same_story = any((
            event_id and str(source.get("event_id") or "") == event_id,
            source_record_id
            and str(source.get("source_record_id") or "") == source_record_id,
            str(source.get("story_key") or "") == story_key,
        ))
        if not same_story:
            continue
        prior_revision = str(
            source.get("revision_sha256") or source.get("source_sha256") or ""
        )
        if prior_revision != revision:
            return item
    return None


def _media_for_event(
    event: Mapping[str, Any],
    composed: Mapping[str, Any],
    *,
    root: Path,
    now: datetime,
    cfg: dict | None,
) -> tuple[list[dict[str, Any]], str]:
    """Render through the existing card family and require a hosted image.

    Returns ``([], reason)`` on refusal. ``reason`` distinguishes three things:
    ``media_unhosted`` (the upload failed, or the renderer fell through its
    fail-soft — transient, the post cannot ship) from
    ``card_withheld_for_value`` (the card was drawn and is a restatement — the
    post ships text-only). The caller must not treat them alike.

    RENDER FIRST, THEN JUDGE (2026-08-06 review, M4/M12). The gate used to run
    BEFORE the render, on `_short_clause(summary, 190)` — 190 characters scored
    against a box whose measured capacity is chart_render.card_summary_budget_chars()
    == 129. So the body veto was computed over a tail the card does not print: a
    summary whose drawn head restates the post while its undrawn tail is
    additive attached a restating card, which is the defect the gate exists for.
    It also falsified the premise the publisher's exemption rests on
    (scripts/marketing_publisher._card_withheld_for_value: "nothing sets this
    flag except a gate that has SEEN a rendered card"). Both are now true: the
    render happens first, and the gate scores `fit["headline_drawn"]` /
    `fit["summary_drawn"]` — the same two fields press_lane scores.
    """

    from engine.marketing.breaking_summary import card_earns_attachment
    from engine.marketing.chart_render import chart_cta_enabled, render_breaking_card
    from engine.marketing.media_publish import publish_card

    ticker = str(event["ticker"]).upper()
    card_id = (
        f"earnings-call-{ticker.lower()}-{str(event['quarter']).lower()}-"
        f"{int(event['year'])}-{str(event['source_sha256'])[:12]}"
    )
    card_headline = str(composed["headline"])
    card_summary = _short_clause(event.get("summary"), 190) or None
    fit: dict = {}
    svg = render_breaking_card(
        headline=card_headline,
        source_name="Earnings call transcript",
        # A COMPANY'S OWN TRANSCRIPT IS A PRIMARY SOURCE, not a relay. It sat on
        # `aggregator` — the most cautious tier, which is the right default for
        # an UNKNOWN provenance and the wrong grade for an artefact the issuer
        # published itself.
        source_tier="official",
        published_at=str(event.get("scored_at") or event["call_date"]),
        tickers=None,
        suppress_cta=False,
        summary=card_summary,
        event_class=None,
        eyebrow="EARNINGS CALL",
        logo_root=root,
        cta=chart_cta_enabled(cfg),
        fit=fit,
    )
    if "headline_drawn" not in fit:
        # The renderer's outer fail-soft returned a blank fallback and populated
        # no fit report. There is nothing to judge and nothing worth printing —
        # same reading as press_lane's, and an earnings post names a ticker, so
        # it does not ship bare.
        print("::warning title=earnings-call-card-render-degraded::"
              f"{ticker} {event['quarter']} FY{event['year']}: the renderer "
              "returned a card with no fit report (fail-soft fallback)",
              flush=True)
        return [], "media_unhosted"
    # THE CARD-VALUE LAW IS NOT PRESS-LANE-LOCAL (2026-08-06). This lane drew a
    # `breaking`-family card whose hero is `composed["headline"]` — the post's
    # own first line, verbatim — and never consulted the gate, so the exact
    # defect the gate was built for (one fact, two surfaces, the tweet in poster
    # type) kept shipping from here while press_lane was fixed. Every lane that
    # draws this card asks the same question, with the same post text it is
    # about to publish, over WHAT THE CARD DREW. Pinned structurally by
    # tests/test_marketing_card_earns_pixels.py::test_every_card_drawing_lane_consults_the_gate.
    attach, why = card_earns_attachment(
        str(composed["text"]),
        str(fit.get("headline_drawn") or card_headline),
        str(fit.get("summary_drawn") or ""),
        [],
    )
    if not attach:
        print("::notice title=earnings-call-card-dropped::"
              f"{ticker} {event['quarter']} FY{event['year']}: {why}; "
              "posting text-only", flush=True)
        return [], "card_withheld_for_value"
    published = publish_card(
        svg,
        chart_id=card_id,
        as_of=now.date().isoformat(),
        root=root,
    ) or {}
    media_url = _http_url(published.get("media_url"))
    if not media_url:
        return [], "media_unhosted"
    entry: dict[str, Any] = {
        "kind": "chart_svg",
        "path": str(published.get("svg_path") or (
            f"data/marketing/outbox/media/{now.date().isoformat()}/{card_id}.svg"
        )),
        "chart_id": card_id,
        "media_url": media_url,
        "ticker": ticker,
    }
    for key in ("media_png_path", "media_render"):
        if published.get(key):
            entry[key] = published[key]
    return [entry], ""


def enqueue_event(
    event: Mapping[str, Any],
    *,
    root: Path | str,
    now: datetime | None = None,
    cfg: dict | None = None,
    article_url: str = "",
    dry_run: bool = False,
    spool: bool = False,
) -> dict[str, Any]:
    """Build and optionally enqueue one committed call-event derivative."""

    from engine.marketing import outbox, story_lock, wire_routing

    repo = Path(root)
    now_utc = _utc(now)
    try:
        _valid_event(event)
        if not call_event_available_as_of(event, now_utc):
            raise ValueError("earnings-call evidence is not available as of enqueue time")
        account = wire_routing.route(EVENT_CLASS, cfg=cfg, root=repo)
        composed = compose_event(event, account=account, as_of=now_utc.date().isoformat())
    except Exception as exc:
        return {"status": "invalid", "reason": str(exc), "item": None}

    existing = outbox.read_items_all(repo)
    if _same_revision_already_emitted(event, existing):
        return {"status": "duplicate", "reason": "event_revision", "item": None}

    prior = _prior_revision_emission(event, existing)
    if prior is not None:
        source = prior.get("source") if isinstance(prior.get("source"), dict) else {}
        prior_id = str(prior.get("id") or "")
        prior_status = str(
            outbox.current_statuses(repo).get(prior_id)
            or prior.get("status")
            or "unknown"
        )
        return {
            "status": "correction_required",
            "reason": "prior_revision_requires_explicit_supersede",
            "prior_item_id": prior_id,
            "prior_revision_sha256": str(
                source.get("revision_sha256") or source.get("source_sha256") or ""
            ),
            "prior_status": prior_status,
            "item": None,
        }

    verdict = story_lock.check(
        account,
        str(composed["story_key"]),
        existing,
        now=now_utc,
        cfg=cfg,
    )
    if not verdict.allowed:
        return {
            "status": "story_locked",
            "reason": verdict.reason,
            "owner": verdict.owner,
            "item": None,
        }

    preflight = outbox.preflight_enqueue(
        account=account,
        kind="earnings",
        text=str(composed["text"]),
        as_of=now_utc.date().isoformat(),
        root=repo,
        cfg=cfg,
    )
    if preflight != "ok":
        return {"status": preflight, "reason": "outbox_preflight", "item": None}

    card_withheld = False
    if dry_run:
        media = [{
            "kind": "chart_svg",
            "path": "dry-run/earnings-call.svg",
            "chart_id": "dry-run-earnings-call",
            "media_url": "https://example.invalid/dry-run.png",
            "ticker": str(event["ticker"]).upper(),
        }]
    else:
        media, media_reason = _media_for_event(
            event, composed, root=repo, now=now_utc, cfg=cfg,
        )
        if not media and media_reason == "card_withheld_for_value":
            # TEXT-ONLY, NOT NO POST. A card refused for restating the copy is
            # the card law working; killing the post here would answer a
            # doubled-card complaint with silence.
            card_withheld = True
        elif not media:
            return {"status": "media_unhosted", "reason": media_reason, "item": None}

    try:
        item = build_outbox_item(
            event,
            account=account,
            now=now_utc,
            media=media,
            cfg=cfg,
            article_url=article_url,
            card_withheld=card_withheld,
        )
    except Exception as exc:
        return {"status": "refused", "reason": str(exc), "item": None}

    if dry_run:
        return {"status": "dry_run", "reason": "", "item": item}

    status = outbox.enqueue(item, repo, cfg=cfg, spool=spool)
    return {
        "status": status,
        "reason": "" if status == "queued" else "outbox_enqueue",
        "item": item if status == "queued" else None,
    }


def run_ledger(
    *,
    root: Path | str,
    now: datetime | None = None,
    cfg: dict | None = None,
    article_urls: Mapping[str, str] | None = None,
    dry_run: bool = False,
    spool: bool = False,
    max_call_age_days: int = DEFAULT_MAX_CALL_AGE_DAYS,
    max_events: int = DEFAULT_MAX_EVENTS,
) -> dict[str, Any]:
    """Project a bounded recent slice of the committed call-event ledger."""

    repo = Path(root)
    now_utc = _utc(now)
    rows, gap = load_call_events(repo)
    if gap:
        # A publication consumer must never continue from the valid-looking
        # prefix of a duplicate/corrupt ledger.  Empty/absent ledgers also
        # produce no work through the same fail-closed response.
        return {
            "input_rows": len(rows),
            "eligible_rows": 0,
            "stale_rows": 0,
            "capped_rows": 0,
            "gap": gap,
            "integrity_blocked": True,
            "results": [],
            "queued": 0,
            "dry_run": 0,
            "duplicates": 0,
            "corrections_required": 0,
        }
    floor = now_utc.date() - timedelta(days=max(0, int(max_call_age_days)))
    eligible: list[dict] = []
    stale = 0
    for row in rows:
        try:
            call_day = date.fromisoformat(str(row.get("call_date") or "")[:10])
        except ValueError:
            stale += 1
            continue
        if (
            call_day < floor
            or call_day > now_utc.date()
            or not call_event_available_as_of(row, now_utc)
        ):
            stale += 1
            continue
        eligible.append(row)

    eligible.sort(key=lambda row: (
        str(row.get("call_date") or ""),
        str(row.get("scored_at") or ""),
        str(row.get("id") or ""),
    ))
    recent_rows = len(eligible)
    cap = max(0, int(max_events))
    if cap:
        eligible = eligible[-cap:]
    else:
        eligible = []

    results: list[dict[str, Any]] = []
    urls = article_urls or {}
    for row in eligible:
        result = enqueue_event(
            row,
            root=repo,
            now=now_utc,
            cfg=cfg,
            article_url=str(urls.get(str(row.get("id") or "")) or ""),
            dry_run=dry_run,
            spool=spool,
        )
        results.append({"event_id": row.get("id"), **result})

    return {
        "input_rows": len(rows),
        "eligible_rows": len(eligible),
        "stale_rows": stale,
        "capped_rows": max(0, recent_rows - len(eligible)),
        "gap": gap,
        "integrity_blocked": False,
        "results": results,
        "queued": sum(result.get("status") == "queued" for result in results),
        "dry_run": sum(result.get("status") == "dry_run" for result in results),
        "duplicates": sum(result.get("status") == "duplicate" for result in results),
        "corrections_required": sum(
            result.get("status") == "correction_required" for result in results
        ),
    }


__all__ = [
    "DEFAULT_MAX_CALL_AGE_DAYS",
    "DEFAULT_MAX_EVENTS",
    "build_outbox_item",
    "compose_event",
    "enqueue_event",
    "run_ledger",
    "story_identity",
]
