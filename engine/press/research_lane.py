"""engine.press.research_lane — the Mastermind Research X surface.  SHIPS DARK.

W2R's distribution half (XG-W8; masterplan D14 §6, X Growth charter §1).  A
triaged research report becomes two X output shapes:

    x_post      short-form, VALUE-COMPLETE.  The claim and its receipt are IN
                THE POST; the link rides in a reply (masterplan §6: "each piece
                becomes a value-complete post, with the link in a reply or
                card — link-bearing posts tend to see softer organic reach").
    x_article   X-native long-form.  Title, standfirst, one section per
                extracted point, standing footer.

FOUR LOCKS KEEP THIS DARK, and they are independent on purpose — the operator
should have to do FOUR deliberate things, not one:

  1. THE X ACCOUNT DOES NOT EXIST.  There is no @handle for Mastermind Research
     (X Growth charter §1: "*(not created yet)*", operator lever §7.1).
  2. NO BUFFER CHANNEL.  `publish.channels` carries no `mastermind_research`
     entry, so even an enqueued item has no posting address.
  3. desk_network SAYS NO, TWICE.  `enabled: false` (the account model's intent
     key) AND `disabled: true` (the legacy per-account kill switch some older
     call sites still read directly).  Both, for exactly the reason
     mastermind_news carries both: the publish-time lanes once filtered on
     `disabled` ALONE, which made a dark property postable.
  4. THIS MODULE REFUSES TO ENQUEUE.  `build_items` resolves liveness through
     engine.marketing.accounts (the ONE liveness model) and returns
     `state="dark"` with an empty item list unless the account is enabled.  A
     caller cannot opt out: `enqueue=True` on a dark account is a no-op that
     says so.

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


def compose_post(item: dict, *, cfg: dict | None = None) -> dict:
    """Short-form, value-complete X post for one vault report.

    Shape: who published it, then the sharpest extracted point, in our own
    extraction's words.  NO LINK IN THE BODY — the link is returned separately
    and belongs in a reply (masterplan §6).
    """
    limit = int(_get(cfg, "short_max_chars"))
    institution = _clean(item.get("institution")) or "An institution"
    points = [_clean(p) for p in (item.get("summary_points") or [])]
    points = [p for p in points if p]
    if not points:
        return {"headline": "", "body": "", "reason": "no summary_points"}

    # The vault writes "**Label**: claim" points; the claim is the post, the
    # label is a filing tag and reads as machine output in a timeline.
    lead = points[0]
    if ":" in lead[:60]:
        lead = lead.split(":", 1)[1].strip() or lead

    headline = f"{institution}, in our read:"
    body = _truncate_sentences(lead, max(0, limit - len(headline) - 2))
    if not body:
        return {"headline": "", "body": "", "reason": "lead point does not fit a post"}
    return {"headline": headline, "body": body, "reason": ""}


def _quoted_title(item: dict, institution: str, limit: int) -> str:
    """`<Institution> on "<report title>": our read`, cut at a word boundary."""
    raw = _clean(item.get("title")) or "the latest note"
    # Straight quotes only: the vault's titles already carry curly apostrophes,
    # and mixing quote styles in one line reads as a paste.
    raw = raw.replace('"', "'").strip()
    prefix, suffix = f'{institution} on "', '": our read'
    room = max(12, limit - len(prefix) - len(suffix))
    if len(raw) > room:
        cut = raw[:room].rsplit(" ", 1)[0].rstrip(",;:")
        raw = cut or raw[:room]
    return f"{prefix}{raw}{suffix}"


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
            if violations:
                skipped.append({"id": rid, "format": fmt,
                                "reason": f"banned_language: {violations[0]}"})
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
                    source={
                        "lane": "research_triage",
                        "format": fmt,
                        "report_id": rid,
                        "institution": str(report.get("institution") or ""),
                        # The link belongs in a REPLY, never in the post body —
                        # the native-first rule (masterplan §6). It is carried
                        # as data so the publisher can place it correctly.
                        "reply_link": link,
                        "triage_rank": triage.get("rank"),
                        "triage_tier": triage.get("tier"),
                        "w_score": triage.get("w_score"),
                        "scoring_version": triage.get("scoring_version"),
                    },
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
                    log.warning("research_lane: enqueue refused %s (%s): %s",
                                rid, fmt, exc)

    return {"state": "ready", "reason": "", "account": account, "items": items,
            "enqueued": enqueued, "skipped": skipped}


__all__ = [
    "ACCOUNT", "KIND", "FORMAT_POST", "FORMAT_ARTICLE",
    "account_state", "compose_post", "compose_article", "report_link",
    "build_items",
]
