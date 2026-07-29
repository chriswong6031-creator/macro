"""engine.marketing.reply_drafter — per-persona reply drafting (XG-W4).

The reply formula (constitution §9.3): **one gift, one grip, one doorway**.

  * **gift** — a missing fact, mechanism, chart, reframe, or condition. Ours
    comes from the own-feed fact builders, so every number in it is already on
    the whitelist. The drafter never invents a figure.
  * **grip** — tension, surprise, or compression. Family-specific.
  * **doorway** — a natural surface for response. It need not be a question;
    constant questions become formulaic, which is its own tell.

**Families, not paraphrases.** Constitution §9.4 asks for strategically
different DESIGNS, and is explicit that three paraphrases of one thought is the
failure mode. ``FAMILIES`` is therefore a register of reasoning MOVES — the
missing-variable move and the second-order move reach different conclusions from
the same fact, which is what makes an alternate draft worth having. Rotation is
least-recently-used per account, so one successful family cannot take over
(§13.7 anti-sameness).

**Voice is borrowed, never forked.** The banned-vocab guard and the expression
dial belong to ``copywriter``/``expression_dial``; this module calls them with
``kind="reply"`` (dial 2 for employees, 1 for flagship, charter §2 amendment 3)
and owns no word list of its own.

**The LLM phrases, it never drafts.** ``draft_reply`` composes deterministically
and then hands the PRIMARY draft to ``reply_voice.voice_or_fallback`` (E4;
``research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md``), which re-phrases it in the
register the reply corpus says earns a reply. That pass is two-key armed, never
raises, and returns THIS draft on any gate hit — so the deterministic path below
is the product, and the model is an upgrade on top of it. Alternates are never
voiced: they exist to differ in reasoning MOVE, not in wording.

**Charts are EOD-only.** ``chart_render`` reads nightly parquet, so a reply that
attaches one must carry an as-of stamp; presenting yesterday's bar as live is
the failure the charter names by hand. ``attach_chart`` stamps every reference,
and the composer prints the stamp in the copy when a chart rides along.

Public API:
    FAMILIES: dict[str, dict]
    family_ids() -> list[str]
    rotate_family(recent, *, allowed=None) -> str
    compose(family, gift, ctx) -> str
    draft_reply(*, account, target, facts, ...) -> dict
    attach_chart(as_of, chart_id, *, root=None) -> dict | None
    prerender_artillery(tickers, as_of, *, root=None, ...) -> list[dict]
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The reply-family register (constitution §9.4). Each entry is a distinct
#: reasoning move, with the author-response trigger it serves (§9.5) recorded so
#: a later re-weighting can argue from design intent, not vibes.
FAMILIES: dict[str, dict[str, Any]] = {
    "missing_variable": {
        "label": "missing variable",
        "move": "name the variable the thread has not priced",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "second_order": {
        "label": "second-order implication",
        "move": "grant the claim, derive what it forces next",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "respectful_disagreement": {
        "label": "respectful disagreement",
        "move": "grant the observation, dispute the mechanism",
        "trigger": "respectfully challenges the mechanism",
        "dial_floor": 1,
    },
    "compression": {
        "label": "compression",
        "move": "compress the whole thread into one line plus the number",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "conditional_prediction": {
        "label": "conditional prediction",
        "move": "state a falsifiable if/then with a level",
        "trigger": "offers a falsifiable condition",
        "dial_floor": 1,
    },
    "human_reaction": {
        "label": "human reaction + analysis",
        "move": "a plain reaction, then one useful sentence",
        "trigger": "gives credit before adding a complication",
        "dial_floor": 2,
    },
    "reframe": {
        "label": "reframe",
        "move": "change what the move is about",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "cross_market_lead": {
        "label": "cross-market lead",
        "move": "point at the market that moved first",
        "trigger": "connects their topic to an adjacent market",
        "dial_floor": 1,
    },
    "correction": {
        "label": "correction without humiliation",
        "move": "fix the fact, never name the person",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "micro_framework": {
        "label": "micro-framework",
        "move": "a two-part lens the reader can carry",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "author_question": {
        "label": "author-specific question",
        "move": "one precise question inside their expertise",
        "trigger": "asks a precise question inside their expertise",
        "dial_floor": 1,
    },
    "original_chart": {
        "label": "original chart",
        "move": "lead with the chart nobody else in the thread has",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
        "needs_chart": True,
    },
    "acknowledgment_plus_one": {
        "label": "acknowledgment with one useful addition",
        "move": "agree in four words, then add exactly one thing",
        "trigger": "gives credit before adding a complication",
        "dial_floor": 1,
    },
    "callback": {
        "label": "callback",
        "move": "connect to a prior public position of ours",
        "trigger": "extends their idea",
        "dial_floor": 1,
        "needs_callback": True,
    },
}


def family_ids() -> list[str]:
    return list(FAMILIES.keys())


def rotate_family(recent: list[str] | tuple[str, ...] | None, *,
                  allowed: list[str] | None = None) -> str:
    """Least-recently-used family (§13.7: one family may not take over).

    ``recent`` is oldest-first. Families never used rank ahead of any family
    that has been; among used ones, the longest-ago wins.
    """
    pool = [f for f in (allowed or family_ids()) if f in FAMILIES]
    if not pool:
        pool = family_ids()
    recent_list = [str(f) for f in (recent or [])]
    def _key(fam: str) -> tuple[int, int]:
        try:
            return (1, recent_list.index(fam))
        except ValueError:
            return (0, pool.index(fam))
    return sorted(pool, key=_key)[0]


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _subject_of(ctx: dict) -> str:
    """A short noun phrase to hang the grip on."""
    subj = str(ctx.get("subject") or "").strip()
    if subj:
        return subj
    ticker = str(ctx.get("ticker") or "").strip()
    if ticker:
        return ticker.lstrip("$")
    return "the move"


def _lead_of(ctx: dict) -> str:
    """The mechanism this family points at (never a new number)."""
    return str(ctx.get("mechanism") or "credit").strip()


def _clean(text: str) -> str:
    """Strip the dash tells the shared guard bans, and collapse whitespace.

    Em/en dashes are a documented LLM tell and a hard ban in
    ``copywriter.banned_language``. Rewriting them here (rather than letting the
    guard reject) keeps the drafter honest without giving it a second word list.
    """
    text = text.replace("—", ", ").replace("–", "-").replace("―", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def compose(family: str, gift: str, ctx: dict | None = None) -> str:
    """Build one draft from a family + a gift sentence.

    The gift is used VERBATIM: it came from an own-feed fact builder, so its
    numbers are already whitelisted. Grip and doorway introduce no figures,
    which is what keeps ``fact_discipline`` satisfiable by construction.
    """
    ctx = dict(ctx or {})
    gift = _clean(gift)
    subject = _subject_of(ctx)
    lead = _lead_of(ctx)
    stamp = str(ctx.get("as_of_stamp") or "").strip()

    if family == "missing_variable":
        body = f"{gift}\n\nThe price move is the reaction. {lead.capitalize()} is the test."
    elif family == "second_order":
        body = (f"{gift}\n\nIf that holds, the pressure shows up in {lead} before it "
                f"shows up in {subject}.")
    elif family == "respectful_disagreement":
        body = (f"Observation holds. The mechanism is where I'd push back.\n\n{gift}\n\n"
                f"That reads like {lead}, not {subject}.")
    elif family == "compression":
        body = f"Short version: {gift}"
    elif family == "conditional_prediction":
        body = (f"{gift}\n\nIf {lead} keeps going the same direction while {subject} "
                f"stays put, the two are arguing and one of them is wrong.")
    elif family == "human_reaction":
        body = f"okay, this one is actually interesting.\n\n{gift}\n\nThat is the part I'd watch."
    elif family == "reframe":
        body = f"{gift}\n\nWorth reading this as a {lead} story rather than a {subject} story."
    elif family == "cross_market_lead":
        body = f"{gift}\n\n{lead.capitalize()} moved first. {subject.capitalize()} is catching up."
    elif family == "correction":
        body = f"One thing worth fixing in the thread: {gift}"
    elif family == "micro_framework":
        body = (f"Two questions settle this.\n\n1. What is {lead} doing.\n"
                f"2. Whether {subject} agrees.\n\n{gift}")
    elif family == "author_question":
        body = (f"{gift}\n\nDoes your read on {subject} survive if {lead} keeps "
                f"moving against it?")
    elif family == "original_chart":
        body = f"Charted it.\n\n{gift}"
    elif family == "acknowledgment_plus_one":
        body = f"Agreed, with one addition.\n\n{gift}"
    elif family == "callback":
        prior = str(ctx.get("callback") or "").strip()
        body = (f"{gift}\n\nSame condition we flagged before: {prior}" if prior
                else f"{gift}\n\nSame condition we flagged before.")
    else:
        body = gift

    if stamp:
        body = f"{body}\n\n({stamp})"
    return _clean(body)


# ---------------------------------------------------------------------------
# Chart attachment (reply artillery)
# ---------------------------------------------------------------------------
def attach_chart(as_of: str, chart_id: str, *, root: Path | str | None = None) -> dict | None:
    """Reference an ALREADY-RENDERED chart by path. Never renders here.

    Returns the queue item's ``chart`` block (``local_path`` + ``public_url``,
    charter §5) with an as-of stamp, or None when no such chart exists. Charts
    are EOD-only, so the stamp is mandatory: a nightly bar presented as live is
    the exact misrepresentation the charter calls out.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
    rel = Path("data") / "marketing" / "outbox" / "media" / str(as_of) / f"{chart_id}.png"
    local = base / rel
    if not local.exists():
        return None
    public_url = None
    try:
        from engine.marketing import media_publish as _mp  # noqa: PLC0415

        public_url = _mp.public_url_for_key(_mp.chart_key(as_of, chart_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: cannot build public url for %r: %s", chart_id, exc)
    return {
        "local_path": str(rel),
        "public_url": public_url,
        "chart_id": chart_id,
        "as_of": as_of,
        "as_of_stamp": f"chart as of {as_of} close",
    }


def prerender_artillery(
    tickers: list[str],
    as_of: str,
    *,
    root: Path | str | None = None,
    closes_for: Any = None,
    limit: int = 12,
) -> list[dict]:
    """Pre-render charts for the day's trending tickers.

    Deliberately minimal: this is a small scheduled sweep that REUSES the
    existing render machinery (``chart_render`` + ``media_publish``) so a reply
    can attach a chart nobody else in the thread has. It renders nothing new
    conceptually and owns no chart style.

    ``closes_for(ticker) -> (dates, o, h, l, c, v) | None`` is injected so this
    function needs no data-layer import and stays testable in a stdlib lane.
    Imports of the render stack are lazy and are allowed to RAISE: a sweep that
    silently renders nothing is indistinguishable from a sweep that ran.
    """
    if not tickers:
        return []
    if closes_for is None:
        raise ValueError(
            "prerender_artillery needs a closes_for(ticker) callable — a sweep "
            "that silently renders nothing is indistinguishable from one that ran"
        )
    from engine.marketing import chart_render as _cr  # noqa: PLC0415
    from engine.marketing import media_publish as _mp  # noqa: PLC0415

    out: list[dict] = []
    for ticker in list(tickers)[:limit]:
        series = closes_for(ticker)
        if not series:
            continue
        # The documented contract is a (dates, o, h, l, c, v) tuple; a mapping
        # of the same fields is accepted too. Anything else is a caller bug and
        # says so, rather than rendering zero charts in silence.
        if isinstance(series, dict):
            kwargs = dict(series)
        elif isinstance(series, (tuple, list)) and len(series) == 6:
            dates, o, h, low, close, vol = series
            kwargs = {"dates": dates, "o": o, "h": h, "l": low, "c": close, "v": vol}
        else:
            raise TypeError(
                f"closes_for({ticker!r}) returned {type(series).__name__}; expected a "
                "(dates, o, h, l, c, v) tuple or an equivalent mapping"
            )
        try:
            svg = _cr.render_chart_v2(ticker=ticker, **kwargs)
            if not svg:
                continue
            chart_id = f"reply-{str(ticker).lstrip('$').lower()}"
            published = _mp.publish_card(svg, chart_id=chart_id, as_of=as_of, root=root)
            out.append({
                "ticker": ticker,
                "chart_id": chart_id,
                "local_path": published.get("media_png_path") or published.get("svg_path"),
                "public_url": published.get("media_url"),
                "as_of_stamp": f"chart as of {as_of} close",
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_drafter: artillery render failed for %s: %s", ticker, exc)
    return out


# ---------------------------------------------------------------------------
# The drafter
# ---------------------------------------------------------------------------
def _pick_gift(facts: dict) -> tuple[str, list[str]]:
    """Highest-salience own-feed fact, plus the whitelist it licenses."""
    rows = [f for f in (facts or {}).get("facts") or [] if isinstance(f, dict) and f.get("text")]
    rows.sort(key=lambda f: -float(f.get("salience") or 0.0))
    whitelist = [str(n) for n in (facts or {}).get("numbers_whitelist") or []]
    return (str(rows[0]["text"]) if rows else ""), whitelist


def draft_reply(
    *,
    account: str,
    target: dict,
    facts: dict,
    family: str | None = None,
    recent_families: list[str] | None = None,
    chart: dict | None = None,
    callback: str | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
    n_alts: int = 2,
) -> dict[str, Any]:
    """Draft one reply plus genuinely different alternates.

    Returns {draft, alt_drafts, family, alt_families, numbers_whitelist,
             components, dial_violations}.

    The alternates come from DIFFERENT families, not from re-wording the
    primary: §9.4's whole point is that a second draft is worth having only when
    it reasons differently. An empty gift returns an empty draft rather than
    padding — Law 1 (value before activity) means abstention is a legal answer.
    """
    gift, whitelist = _pick_gift(facts)
    if not gift.strip():
        return {
            "draft": "", "alt_drafts": [], "family": None, "alt_families": [],
            "numbers_whitelist": whitelist, "components": {"abstained": "no own-feed fact"},
            "dial_violations": [],
        }

    allowed = [f for f, spec in FAMILIES.items()
               if not (spec.get("needs_chart") and not chart)
               and not (spec.get("needs_callback") and not callback)]
    primary = family if family in FAMILIES else rotate_family(recent_families, allowed=allowed)

    ctx = {
        "subject": target.get("subject") or target.get("ticker"),
        "ticker": target.get("ticker"),
        "mechanism": target.get("mechanism"),
        "as_of_stamp": (chart or {}).get("as_of_stamp"),
        "callback": callback,
    }

    order = [primary] + [f for f in rotate_order(allowed, primary) if f != primary]
    drafts: list[tuple[str, str]] = []
    for fam in order[: 1 + max(0, int(n_alts))]:
        drafts.append((fam, compose(fam, gift, ctx)))

    # Voice pass: the SHARED dial, kind="reply". apply_pass is deterministic
    # clean-up only (off-signature emoji, exclamation downgrade); everything
    # else the dial dislikes is reported, never silently rewritten.
    polished: list[tuple[str, str]] = []
    for fam, text in drafts:
        try:
            from engine.marketing import expression_dial as _dial  # noqa: PLC0415

            _, body = _dial.apply_pass("", text, account=account, kind="reply", root=root)
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_drafter: dial pass unavailable for %r: %s", account, exc)
            body = text
        polished.append((fam, _clean(body)))

    # E4 phrasing pass — OPTIONAL, and DOWNSTREAM of everything above. The
    # deterministic draft is the argument and the fallback, so this line can
    # only change words, never whether a reply exists.
    voice = _voice_pass(
        polished[0][1], family=polished[0][0], account=account, target=target,
        whitelist=whitelist, cfg=cfg, root=root,
    )
    polished[0] = (polished[0][0], voice["text"])

    # The dial's own findings on the SHIPPING primary text, reported not
    # swallowed: the critics re-run this independently, but a drafter that
    # returns an empty violation list it never populated is a permanent
    # all-clear to any caller that trusts the field. Graded AFTER the voice
    # pass, because grading the pre-voice text would describe copy that is not
    # the copy being returned.
    dial_violations: list[str] = []
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        dial_violations = list(_dial.violations(
            "", polished[0][1], account=account, kind="reply", root=root,
            include_house_bans=False,
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: dial grading unavailable for %r: %s", account, exc)

    return {
        "draft": polished[0][1],
        "alt_drafts": [t for _, t in polished[1:]],
        "family": polished[0][0],
        "alt_families": [f for f, _ in polished[1:]],
        "numbers_whitelist": whitelist,
        "components": {
            "gift": gift,
            "family_move": FAMILIES[polished[0][0]]["move"],
            "trigger": FAMILIES[polished[0][0]]["trigger"],
            "chart": bool(chart),
            "voice_mode": voice["mode"],
        },
        "dial_violations": dial_violations,
        "voice": voice,
    }


def _voice_pass(
    draft: str,
    *,
    family: str,
    account: str,
    target: dict,
    whitelist: list[str],
    cfg: dict | None,
    root: Path | str | None,
) -> dict[str, Any]:
    """The E4 LLM phrasing hook. Returns {text, mode, provider, violations}.

    ``reply_voice.voice_or_fallback`` is two-key armed (config
    ``reply_desk.voice.enabled`` + ``MARKETING_LLM_ENABLED``), never raises, and
    hands back THIS draft on any gate hit, provider failure or disarmed key. The
    try/except here is therefore about the IMPORT — if the module is absent or
    broken, the deterministic draft is still what ships, and the alternates are
    never voiced at all (they exist to differ in reasoning MOVE, and one call
    per drafted reply is what keeps the runaway guard meaningful).

    The output is re-``_clean``ed: no dash tell may leave this module, whoever
    wrote the sentence.
    """
    fallback = {"text": draft, "mode": "off", "provider": None, "violations": []}
    try:
        from engine.marketing import reply_voice as _voice  # noqa: PLC0415

        out = _voice.voice_or_fallback(
            draft,
            family=family,
            account=account,
            parent_text=str((target or {}).get("text") or ""),
            parent_author=str((target or {}).get("author") or ""),
            numbers_whitelist=list(whitelist or []),
            family_spec=FAMILIES.get(family),
            cfg=cfg,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001 — a drafted reply must still exist
        log.warning("reply_drafter: voice pass unavailable for %r: %s", account, exc)
        return fallback
    text = _clean(str(out.get("text") or "")) or draft
    return {
        "text": text,
        "mode": str(out.get("mode") or "off"),
        "provider": out.get("provider"),
        "violations": list(out.get("violations") or []),
    }


def rotate_order(allowed: list[str], primary: str) -> list[str]:
    """Deterministic alternate ordering: the families furthest from the primary
    in the register, so alternates differ in MOVE, not in wording."""
    pool = [f for f in allowed if f != primary]
    if not pool:
        return []
    try:
        idx = allowed.index(primary)
    except ValueError:
        idx = 0
    return pool[idx:] + pool[:idx]


__all__ = [
    "FAMILIES", "family_ids", "rotate_family", "rotate_order", "compose",
    "draft_reply", "attach_chart", "prerender_artillery",
]
