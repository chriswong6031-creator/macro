"""engine.press.research_lane — the Mastermind Research X surface.  SHIPS DARK.

W2R's distribution half (XG-W8; masterplan D14 §6, X Growth charter §1).  A
triaged research report becomes two X output shapes:

    x_post      short-form, VALUE-COMPLETE.  The claim and its receipt are IN
                THE POST; the link rides in a reply (masterplan §6: "each piece
                becomes a value-complete post, with the link in a reply or
                card — link-bearing posts tend to see softer organic reach").
    x_article   X-native long-form.  Title, standfirst, one section per
                extracted point, standing footer.

WHAT KEEPS THIS DARK — stated precisely, because "four independent locks" was
the first draft's phrasing and it overstated the independence:

TWO EXTERNAL FACTS (not code, and not ours to enforce):
  A. THE X ACCOUNT DOES NOT EXIST.  There is no @handle for Mastermind Research
     (X Growth charter §1: "*(not created yet)*", operator lever §7.1).
  B. NO BUFFER CHANNEL.  `publish.channels` carries no `mastermind_research`
     entry, so even an enqueued item has no posting address.

TWO CODE LOCKS, and they are NOT independent of each other:
  1. desk_network SAYS NO, TWICE.  `enabled: false` (the account model's intent
     key) AND `disabled: true` (the legacy per-account kill switch some older
     call sites still read directly).  Both, for exactly the reason
     mastermind_news carries both: the publish-time lanes once filtered on
     `disabled` ALONE, which made a dark property postable.
  2. THIS MODULE REFUSES TO ENQUEUE.  `build_items` returns `state="dark"` with
     an empty item list unless the account is enabled.  `enqueue=True` on a dark
     account is a no-op that says so.

     BOTH READ THE SAME RESOLVER.  Lock 2 asks engine.marketing.accounts, which
     is where lock 1's config keys are interpreted — so they are one mechanism
     read twice, not two mechanisms.  In particular
     `data/marketing/account_overrides.json` sets `enabled` AFTER config, so a
     single override entry `{"mastermind_research": {"enabled": true}}` flips
     BOTH at once.  That file is the documented operator lever and it is the
     right design; it is named here so nobody reads "two locks" as "two things
     an operator must edit".  With A and B still true an override cannot
     actually post anything — but it WOULD start building and queueing items for
     an account with no channel, so an override on this id is worth seeing in
     ops.

NO HAND-ROLLED WRITER.  Items are built with `outbox.make_item` and checked with
`outbox.validate_item` — the canonical path, which is what carries the id-dedup,
exact-text dedup and near-duplicate guards.  XG-W2 spent a whole wave deleting
the two raw-file writers that bypassed it; this lane does not add a third.

NO NEW OUTBOX KIND.  Both shapes are `kind="education"` — the analyst/explainer
register the mastermind_research persona already tilts toward, and expression
dial level 1 ("analysis"), which is what a research property posts.  The house
rule is explicit (tests/test_marketing_desk_feeds.py: "NO NEW KINDS. A franchise
maps onto a kind the outbox already admits"), and a new kind would need an
expression-dial level, a tilt entry on every account and a sentinel cap review
before it could carry a single post.  `source.format` distinguishes the two
shapes for any consumer that cares.

NO LLM.  Every character of copy here is composed deterministically from the
vault's own `summary_points` — our analyst extraction, already fact-anchored.
Nothing is originated, so there is nothing for the fact-anchor law to catch.
The shared copywriter banned-vocabulary guard (charter §2 amendment 12: "one
vocab guard, every drafter") screens the result anyway, because a lane that
trusts its own inputs is how the $AVGO post reached the queue.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable

log = logging.getLogger(__name__)

#: The persona/account this lane speaks as.  There is no other.
ACCOUNT = "mastermind_research"

#: The outbox kind both shapes use.  See the module docstring: no new kinds.
KIND = "education"

#: `source.format` values.  A consumer that only wants the short-form filters
#: on this rather than on text length.
FORMAT_POST = "x_post"
FORMAT_ARTICLE = "x_article"

_DEFAULTS: dict[str, Any] = {
    # X's own limit is 280; the house copy law is 275 (config/marketing.yml
    # copywriter.copy_laws). Composed text is TRUNCATED AT A SENTENCE BOUNDARY,
    # never mid-word, because a clipped receipt is a wrong receipt.
    "short_max_chars": 275,
    # Points carried into the long-form shape.
    "article_max_points": 6,
    "article_title_max_chars": 110,
    # Standing disclosure. Same sentence as the press footer
    # (config/press.yml validators.footer_required_text), in X-LEGAL
    # PUNCTUATION: the site footer uses an em dash, and the house copy law bans
    # em/en dashes in X copy outright (config/marketing.yml copywriter.copy_laws
    # — "use a period, a comma, or a new sentence"). Carrying the site string
    # verbatim made the shared banned-vocabulary guard reject EVERY article
    # shape, which is the guard working and the string being wrong.
    "footer": "Educational content, not investment advice. Markets involve risk.",
}

_WS_RE = re.compile(r"\s+")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

# Em dash, en dash, horizontal bar. The vault's analyst summaries are written
# for the SITE, where these are normal typography; on X they are a banned tell.
_DASH_RE = re.compile(r"\s*[—–―]\s*")
_COMMA_RUN_RE = re.compile(r",\s*(?=[,.;:])")
_PUNCT_COMMA_RE = re.compile(r"([.;:!?])\s*,\s*")

# THE ONLY PREFIX compose_post MAY STRIP, and it is anchored to the markdown the
# vault actually writes: `**Filing Label**: the claim`.
#
# THE DEFECT THIS REPLACES: the first version split the CLEANED point on its
# first bare colon inside the leading 60 characters. Every colon in financial
# prose is a candidate — the reviewer reproduced "At 10:30 GMT the print showed
# a 0.3 percent rise." becoming "30 GMT the print showed a 0.3 percent rise."
# (a FABRICATED number, in a post whose whole job is carrying a receipt) and
# "Three risks: rates, oil, the labour print." losing its subject. Anchoring on
# the bold markers means the strip only fires where the source really did put a
# filing label in front of the sentence, and it runs on the RAW point because
# `_strip_md` erases exactly the evidence the anchor needs.
_BOLD_LABEL_RE = re.compile(r"^\s*\*\*(?P<label>[^*\n]{1,60}?)\*\*\s*[:：]\s*")


def _get(cfg: dict | None, key: str) -> Any:
    if isinstance(cfg, dict) and key in cfg and cfg[key] is not None:
        return cfg[key]
    return _DEFAULTS[key]


def _clean(text: object) -> str:
    """Plain text for X: markdown bold stripped, dashes normalised, ws collapsed.

    THE DASH SUBSTITUTION IS THE ONLY EDIT THIS MODULE MAKES TO SOURCE WORDS, and
    it is a typography fix, not a content one: the copy law's own prescribed
    remedy for a dash is "a period, a comma, or a new sentence". The vault's
    analyst summaries are written for the site, where an em dash is normal, so
    without this every second report would be skipped for punctuation the house
    itself wrote. Everything the guard catches for CONTENT reasons (banned
    vocabulary, study names, the cheese list) still skips the shape — this
    normaliser cannot rescue those and deliberately does not try.
    """
    from engine.press.desk_planner import _strip_md  # noqa: PLC0415

    out = _strip_md(str(text or ""))
    out = _DASH_RE.sub(", ", out)
    out = _PUNCT_COMMA_RE.sub(r"\1 ", out)   # ". , " -> ". "
    out = _COMMA_RUN_RE.sub("", out)         # ", ." -> "."
    return _WS_RE.sub(" ", out).strip().strip(",").strip()


def _truncate_sentences(text: str, limit: int) -> str:
    """Longest whole-sentence prefix that fits.  Never cuts mid-word.

    A receipt cut in half is not a shorter receipt, it is a different number, so
    there is no character-level fallback here: if not even the first sentence
    fits, the caller gets "" and drops the shape.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    out = ""
    for sentence in _SENTENCE_END_RE.split(text):
        candidate = (out + " " + sentence).strip() if out else sentence.strip()
        if len(candidate) > limit:
            break
        out = candidate
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Liveness — one model, imported, never re-derived
# ─────────────────────────────────────────────────────────────────────────────


def account_state(cfg: dict | None, root=None, *, account: str = ACCOUNT) -> dict:
    """Is this account allowed to generate/post?  {"enabled", "status", "reason"}.

    Delegates to engine.marketing.accounts — the single place that answers
    "which desk accounts actually exist tonight?".  A second liveness rule here
    is how a dark account goes live by accident.

    FAILS CLOSED.  An unreadable config, a missing account entry, or an
    exception all resolve to disabled: the account that does not exist yet must
    never be the one a degraded read decides to arm.
    """
    try:
        from engine.marketing import accounts as _accounts  # noqa: PLC0415

        rows = _accounts.effective_accounts(cfg, root)
        row = next((a for a in rows if str(a.get("id")) == account), None)
        if row is None:
            return {"enabled": False, "status": "planned",
                    "reason": f"{account} has no desk_network entry"}
        channels = ((cfg or {}).get("publish") or {}).get("channels") or {}
        status = _accounts.account_status(row, channels)
        return {"enabled": bool(row.get("enabled")), "status": status,
                "reason": "" if row.get("enabled") else
                          f"{account} is not enabled in desk_network"}
    except Exception as exc:  # noqa: BLE001 — fail CLOSED, always
        log.warning("research_lane: liveness unreadable (%s) — treating %s as dark",
                    exc, account)
        return {"enabled": False, "status": "planned",
                "reason": f"liveness unreadable ({type(exc).__name__})"}


# ─────────────────────────────────────────────────────────────────────────────
# Copy composition (deterministic; zero LLM)
# ─────────────────────────────────────────────────────────────────────────────


def strip_filing_label(raw_point: object) -> str:
    """Drop a leading `**Label**:` filing tag from a RAW summary point.

    Runs on the raw markdown, never on cleaned text: the bold markers ARE the
    anchor, and `_strip_md` erases them.  Anything that is not a bold-label
    prefix — a clock time, a list-introducing colon, a ratio, a ticker
    annotation — is returned untouched.
    """
    raw = str(raw_point or "")
    match = _BOLD_LABEL_RE.match(raw)
    if not match:
        return raw
    remainder = raw[match.end():].strip()
    # A label with nothing after it is the whole point; keep the point.
    return remainder or raw


def compose_post(item: dict, *, cfg: dict | None = None) -> dict:
    """Short-form, value-complete X post for one vault report.

    Shape: who published it, then the sharpest extracted point, in our own
    extraction's words.  NO LINK IN THE BODY — the link is returned separately
    and belongs in a reply (masterplan §6).

    Walks the points in order and takes the first one that FITS whole sentences
    inside the character budget.  A long lead point used to kill the post
    outright; the second point is a worse lead than the first and a much better
    one than nothing.

    TWO STAGES USED TO DISAGREE ABOUT "USABLE" (2026-07-30).  Selection asked
    only "does it FIT" (character budget); admission — value_gate's `gift` leg,
    armed the same day — asks "is there a POST here at all" (a word floor).  A
    report whose first fitting point was four words therefore produced a draft
    that the gate then abstained on, and the post was lost even when point two
    was a full paragraph.  Neither stage was wrong on its own; they were reading
    different definitions, and the lane paid for it in silence.

    So selection now applies the gate's own floor as a PREFERENCE: walk for the
    first point that both fits and clears it.  The floor is imported, never
    re-declared, so raising it in one place moves both stages together.  If no
    point clears it we still return the first that fits, unchanged — that keeps
    this function from growing a second, quieter drop of its own, and leaves the
    refusal where it belongs, with the gate that announces it.
    """
    # Lazy, like every other engine.marketing import in this file: the thin CI
    # lane's minimal env is the contract that keeps these modules importable
    # without pandas, and a top-level import here would be the thing that breaks it.
    from engine.marketing.value_gate import MIN_BODY_WORDS  # noqa: PLC0415

    limit = int(_get(cfg, "short_max_chars"))
    institution = _clean(item.get("institution")) or "An institution"
    raw_points = [p for p in (item.get("summary_points") or []) if str(p or "").strip()]
    if not raw_points:
        return {"headline": "", "body": "", "reason": "no summary_points"}

    headline = f"{institution}, in our read:"
    room = max(0, limit - len(headline) - 2)
    fits: list[tuple[int, str]] = []
    for index, raw in enumerate(raw_points):
        candidate = _clean(strip_filing_label(raw))
        body = _truncate_sentences(candidate, room)
        if not body:
            continue
        fits.append((index, body))
        if len(body.split()) >= MIN_BODY_WORDS:
            return {"headline": headline, "body": body, "reason": "",
                    "point_index": index}
    if fits:
        index, body = fits[0]
        return {"headline": headline, "body": body, "reason": "",
                "point_index": index}
    return {"headline": "", "body": "",
            "reason": "no summary point fits a post at the character budget"}


def _topic_hint(item: dict) -> str:
    """A short subject for the UNQUOTED title form, taken from our own filing.

    Prefers the first summary point's bold label — that label is OUR analyst's
    filing tag, not the source's prose, so using it outside quotation marks
    claims nothing about the institution's words.
    """
    for raw in (item.get("summary_points") or []):
        match = _BOLD_LABEL_RE.match(str(raw or ""))
        if match:
            label = _clean(match.group("label"))
            if label:
                return label[0].lower() + label[1:] if len(label) > 1 else label.lower()
    return ""


def _quoted_title(item: dict, institution: str, limit: int) -> str:
    """The article's own headline.  A QUOTED span is VERBATIM or there is none.

    THE DEFECT THIS REPLACES (AM-R4, fabricated quotation): the first version
    put `_clean`ed text inside quotation marks — em dashes swapped for commas,
    double quotes swapped for single, and a silent mid-title truncation with no
    ellipsis — and attributed the result to the institution.  Every one of those
    is an edit; presenting an edited string as the source's own title is
    manufacturing a quote, which is precisely the line AM-R4 draws.

    The rule now:

      1. Try the VERBATIM title.  No dash normalisation, no quote swapping, no
         silent cut.  It may be shortened only at a WORD BOUNDARY and only with
         a visible ellipsis, which is the ordinary journalistic mark for "this
         is where the quotation stops".
      2. That candidate must fit the budget AND clear the shared vocabulary
         guard.  A source title carrying an em dash cannot be quoted on X at
         all, because normalising it would falsify it.
      3. Otherwise DROP THE QUOTATION MARKS and say something true in our own
         words: `<Institution>'s latest note on <topic>`, where <topic> is OUR
         filing label, not their prose.

    So the quoted span is always a verbatim prefix of the source title (modulo a
    trailing ellipsis), and when it cannot be, nothing is in quotes.
    """
    from engine.marketing.copywriter import banned_language  # noqa: PLC0415

    raw = str(item.get("title") or "").strip()
    prefix, suffix = f'{institution} on "', '": our read'
    room = limit - len(prefix) - len(suffix)

    if raw and room >= 20:
        quoted = raw
        if len(quoted) > room:
            cut = raw[: room - 1].rsplit(" ", 1)[0].rstrip(" ,;:.")
            quoted = f"{cut}…" if cut else ""
        if quoted:
            candidate = f"{prefix}{quoted}{suffix}"
            if len(candidate) <= limit and not banned_language(candidate):
                return candidate

    # Unquoted fallback — our words about their note, claiming no quotation.
    topic = _topic_hint(item)
    tail = f" on {topic}" if topic else ""
    unquoted = f"{institution}'s latest research note{tail}"
    if len(unquoted) > limit:
        unquoted = f"{institution}'s latest research note"
    return unquoted


def compose_article(item: dict, *, cfg: dict | None = None) -> dict:
    """X-native long-form Article shape for one vault report.

    A STRUCTURE, not prose.  Every line traces to a `summary_points` entry, so
    the fact-anchor law holds by construction — this lane originates nothing and
    therefore cannot originate a number.  When the press desk's article for the
    same report exists, the Article body is the piece; until then this is the
    outline the desk publishes from.
    """
    max_points = int(_get(cfg, "article_max_points"))
    title_limit = int(_get(cfg, "article_title_max_chars"))
    footer = str(_get(cfg, "footer"))
    institution = _clean(item.get("institution")) or "An institution"
    points = [_clean(p) for p in (item.get("summary_points") or [])][:max_points]
    points = [p for p in points if p]
    if not points:
        return {"headline": "", "body": "", "reason": "no summary_points"}

    # THE SOURCE TITLE IS QUOTED AND ATTRIBUTED, never presented as our own line.
    # AM-R4 rev 3 is "cover any story you like, never lift another outlet's
    # prose", and a headline is prose — but naming a report by its title, in
    # quotation marks, next to who wrote it, is how every desk on earth refers to
    # a research note. The distinction is presentation, so it is enforced here in
    # the construction rather than left to a reviewer's eye.
    title = _quoted_title(item, institution, title_limit)

    lines = [f"What {institution} put in front of clients, and what we make of it."]
    lines.append("")
    for point in points:
        lines.append(f"- {point}")
    lines.append("")
    lines.append(footer)
    return {"headline": title, "body": "\n".join(lines), "reason": ""}


def report_link(item: dict, all_items: list[dict] | None = None) -> str:
    """Our PUBLIC coverage page for the report ("" when there is no slug).

    The vault landing page, not the source document: we never republish source
    material.  This is what goes in the REPLY, never in the post body.
    """
    from engine.press.desk_planner import _SITE_BASE, vault_slug  # noqa: PLC0415

    slug = vault_slug(item, list(all_items or [item]))
    return f"{_SITE_BASE}/research/{slug}.html" if slug else ""


# ─────────────────────────────────────────────────────────────────────────────
# Item construction — the canonical outbox path, and nothing else
# ─────────────────────────────────────────────────────────────────────────────


def build_items(pieces: Iterable[dict], *, cfg: dict | None = None,
                lane_cfg: dict | None = None, root=None,
                as_of: str | date | None = None, now: datetime | None = None,
                account: str = ACCOUNT, enqueue: bool = False,
                catalog_items: list[dict] | None = None) -> dict:
    """Build (and optionally enqueue) the X shapes for triaged reports.

    `pieces` is an iterable of ``{"report": <vault item>, "triage": <row>}``.
    `cfg` is the MARKETING config (config/marketing.yml) — this is a marketing
    surface, so liveness and the outbox contract come from there.

    Returns::

        {"state": "dark" | "ready", "reason": str, "account": str,
         "items": [...], "enqueued": n, "skipped": [{"id", "reason"}]}

    THE DARK BRANCH IS FIRST AND UNCONDITIONAL.  On a dark account this returns
    before a single item is built, so there is no code path where a hostile
    `enqueue=True` reaches the queue.
    """
    state = account_state(cfg, root, account=account)
    if not state.get("enabled"):
        # NOT an error and NOT a warning: this is the designed state until the
        # operator creates the account (X Growth charter §7 lever 1).
        log.info("research_lane: %s is dark (%s) — no items built",
                 account, state.get("reason"))
        return {"state": "dark", "reason": str(state.get("reason") or ""),
                "account": account, "items": [], "enqueued": 0, "skipped": []}

    from engine.marketing import expression_dial as _dial  # noqa: PLC0415
    from engine.marketing import outbox as _ob  # noqa: PLC0415
    from engine.marketing.copywriter import banned_language  # noqa: PLC0415

    ts = now or datetime.now(tz=timezone.utc)
    day = str(as_of) if as_of else ts.astimezone(timezone.utc).strftime("%Y-%m-%d")

    items: list[dict] = []
    skipped: list[dict] = []
    enqueued = 0

    for piece in pieces:
        report = (piece or {}).get("report") or {}
        triage = (piece or {}).get("triage") or {}
        rid = str(report.get("id") or "")
        link = report_link(report, catalog_items)

        for fmt, composer in ((FORMAT_POST, compose_post),
                              (FORMAT_ARTICLE, compose_article)):
            draft = composer(report, cfg=lane_cfg)
            if not draft["headline"] or not draft["body"]:
                skipped.append({"id": rid, "format": fmt,
                                "reason": draft.get("reason") or "empty draft"})
                continue

            text = _ob.compose_text(draft["headline"], draft["body"])
            # ONE VOCAB GUARD, EVERY DRAFTER (charter §2 amendment 12). The copy
            # is deterministic and sourced from our own extraction, which is
            # exactly the confidence that put a banned study name in the queue
            # in July — so it is screened like every other lane's.
            violations = banned_language(text)
            # THE EXPRESSION DIAL IS LAW ON EVERY COPY PATH (XG-W1 / charter §2
            # amendment 3), not only on the ones with a codex today. `violations`
            # returns [] for an account with no `voice_codex.dial_profile`, which
            # mastermind_research does not yet carry — so this call is inert
            # RIGHT NOW and becomes the gate the moment the codex is filled in.
            # A lane wired to the dial only after it goes live is a lane that
            # ships its first week unpoliced.
            violations += _dial.violations(
                draft["headline"], draft["body"],
                account=account, kind=KIND, root=root, as_of=day,
                # banned_language already ran on this exact text, one line up —
                # one guard, two callers, reported once (the copywriter idiom).
                include_house_bans=False,
            )
            if violations:
                skipped.append({"id": rid, "format": fmt,
                                "reason": f"copy_guard: {violations[0]}"})
                continue

            source = {
                "lane": "research_triage",
                "format": fmt,
                "report_id": rid,
                "institution": str(report.get("institution") or ""),
                # The link belongs in a REPLY, never in the post body — the
                # native-first rule (masterplan §6). It is carried as data so
                # the publisher can place it correctly.
                "reply_link": link,
                "triage_rank": triage.get("rank"),
                "triage_tier": triage.get("tier"),
                "w_score": triage.get("w_score"),
                "scoring_version": triage.get("scoring_version"),
            }
            # GIFT-GRIP-PROOF VERDICT ON EVERY EMISSION (charter §0 XG-W3).
            # RECORD-ONLY here, exactly as press_lane runs it: the verdict is
            # stamped onto `source` and an abstention is announced, but only
            # `value_gate.enforce` turns it into a refusal. `source_headline` is
            # the SOURCE REPORT's title, so the informational-surplus test has
            # the right thing to compare our line against.
            would_block = _ob.stamp_value_gate(
                source,
                headline=draft["headline"],
                body=draft["body"],
                kind=KIND,
                has_media=False,
                source_headline=str(report.get("title") or ""),
                citation=link,
                cfg=cfg,
            )
            if would_block:
                verdict = source.get("value_gate") or {}
                # SAY WHICH IT IS. This line read "would abstain … enforce=True"
                # in both modes, so once the gate was armed the log described a
                # dropped post in the conditional voice — the operator reads a
                # rehearsal and the lane is actually losing output. Shadow mode
                # keeps "would abstain"; an armed refusal says so, at ::warning,
                # because a post that does not ship is not a notice.
                enforced = _ob._value_gate_enforced(cfg)
                why = ",".join(verdict.get("reasons") or [])
                if enforced:
                    print("::warning title=research-lane-value-gate::"
                          f"{rid}/{fmt}: ABSTAINED, not posted ({why})", flush=True)
                else:
                    print("::notice title=research-lane-value-gate::"
                          f"{rid}/{fmt}: would abstain ({why}) — "
                          "shadow mode, post ships", flush=True)
                if enforced:
                    skipped.append({"id": rid, "format": fmt,
                                    "reason": "value_gate: "
                                              + ",".join(verdict.get("reasons") or [])})
                    continue

            try:
                item = _ob.make_item(
                    account=account,
                    kind=KIND,
                    text=text,
                    as_of=day,
                    # "immediate" is the outbox's NO-ADVISORY-TIME sentinel, not
                    # a share-now instruction (see _scheduled_at_for_slot): a
                    # research post is scheduled by the cadence resolver, not by
                    # this lane, and any other string is not a legal value.
                    scheduled_at="immediate",
                    provenance="press_research_lane",
                    source=source,
                    now=ts,
                )
            except ValueError as exc:
                skipped.append({"id": rid, "format": fmt, "reason": f"make_item: {exc}"})
                continue

            errors = _ob.validate_item(item)
            if errors:
                skipped.append({"id": rid, "format": fmt,
                                "reason": f"validate_item: {errors[0]}"})
                continue
            items.append(item)

            if enqueue:
                try:
                    # enqueue returns a STATUS STRING, never a boolean:
                    # "queued" | "duplicate" | "cross_account_duplicate" |
                    # "cap_exceeded" | "invalid:<msg>". Every one of those is
                    # truthy, so counting on truthiness would report a
                    # cap-refused item as enqueued.
                    result = _ob.enqueue(item, root, cfg=cfg)
                    if result == "queued":
                        enqueued += 1
                    else:
                        skipped.append({"id": rid, "format": fmt,
                                        "reason": f"outbox: {result}"})
                except Exception as exc:  # noqa: BLE001
                    # A raising enqueue is still an item that did NOT reach the
                    # queue. Leaving it out of `skipped` made built - enqueued
                    # unaccountable, which is the one arithmetic a caller uses
                    # this return value for.
                    log.warning("research_lane: enqueue refused %s (%s): %s",
                                rid, fmt, exc)
                    skipped.append({"id": rid, "format": fmt,
                                    "reason": f"outbox raised: {type(exc).__name__}"})

    return {"state": "ready", "reason": "", "account": account, "items": items,
            "enqueued": enqueued, "skipped": skipped}


__all__ = [
    "ACCOUNT", "KIND", "FORMAT_POST", "FORMAT_ARTICLE",
    "account_state", "compose_post", "compose_article", "report_link",
    "build_items",
]
