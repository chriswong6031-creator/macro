"""FOMC statement-diff card — the surface the analysis actually ships on.

WHY THE ANALYSIS IS ON A PICTURE. X gives a post 280 characters, and a 2-4
paragraph read of what the Committee changed is several thousand. The post body
therefore carries a hook and the card carries the argument, which is the same
division the earnings and breaking cards in this family already use. There are no
threads in v1: a thread is a different product with its own failure modes (a
dropped reply orphans the analysis) and the card is legible, quotable and one
fetch.

VISUAL FAMILY, NOT A LOOKALIKE. Every piece of chrome here is IMPORTED from
engine/marketing/chart_render.py — the favicon logomark, the brand bar, the
measured text width estimator, the wrapper, the escaper, the family palette. The
2026-07-26 incident in this repo was two lanes rendering their own lookalike cards
that drifted apart; the standing rule since is one seam, one renderer. What this
module owns is the LAYOUT of an FOMC diff, not a second visual language. The
candlestick machinery in that module is deliberately not touched.

CANVAS. 1080x1350 — the family's declared 4:5 tall variant, taken because a
statement diff plus three paragraphs of analysis genuinely warrants the extra
room. Every measurement is authored in 1080-space and scaled, so an off-size
caller degrades in proportion. Rastered at the family's scale=2 the body type
lands at ~62px on a 2160px-wide PNG, comfortably above what a phone timeline
needs and above the family's own 26px-in-1080-space legibility floor.

FAIL-SOFT. Returns a minimal valid SVG on any internal error, never raises. A
render that degrades costs the desk its analysis surface; a render that throws
would take down a wire tick.
"""
from __future__ import annotations

import logging
import zlib

log = logging.getLogger(__name__)

# ── Family chrome (see the module docstring: imported, never re-authored) ─────
from engine.marketing.chart_render import (  # noqa: E402
    _bc_text_w,
    _bc_wrap_w,
    _brand_bar,
    _BREAK_AMBER,
    _BREAK_BODY,
    _BREAK_DOWN,
    _BREAK_GREY,
    _BREAK_RULE,
    _BREAK_UP,
    _favicon_logomark,
    _xesc,
)

#: Authoring canvas. 1080 wide is the family master; 1350 is its declared 4:5
#: tall variant.
CARD_W = 1080
CARD_H = 1350

#: Card background — the family's dark navy base.
_BG = "#0E1420"
_MAST_BG = "#0A1020"

#: Hard floor on body type, in 1080-space. The family's own floor is 26 and this
#: card holds a higher one because reading it IS the product.
#:
#: The number that matters is the RASTERED one. media_publish rasters this family
#: at scale=2, so a 1080-wide card becomes a 2160px PNG and 28 here draws at 56px
#: there — twice the 28px-on-a-2000px-card legibility floor this lane was built
#: to. The ladder in `_render` starts at 35 (70px rastered) and stops here.
_BODY_MIN = 28.0

#: Highlight lines the "what changed" block may draw, total.
MAX_HIGHLIGHT_LINES = 6

#: Lines one added/removed SENTENCE row may take. Two clipped a real dissent
#: sentence mid-word ("who preferred t...") on the first render probe; three
#: holds the sentences this corpus actually produces.
_SENTENCE_ROW_LINES = 3


def _house_dash(text: str) -> str:
    """Normalise the Fed's typesetting to the house dash law.

    The statement pages carry a SPACED EN DASH in the vote line ("by a 9 – 3
    vote"). House law (docs/DESIGN_DOCTRINE.md, CI-guarded for post copy by
    copywriter.banned_language) forbids em dashes and spaced en dashes on our own
    surfaces, and the card is one of our surfaces. A hyphen carries the identical
    meaning for a vote count, so the substance of the quote is untouched and the
    card stops shipping a dash the rest of the house is not allowed to use.
    """
    out = str(text or "")
    for dash in ("—", "–", "‒", "‑", "‐"):
        out = out.replace(f" {dash} ", "-").replace(dash, "-")
    return out


def _fallback_svg(width: int, height: int, note: str = "") -> str:
    """Minimal valid card. Returned on any internal failure."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>'
        f'<text x="{width / 2:.0f}" y="{height / 2:.0f}" fill="{_BREAK_GREY}" '
        f'font-size="34" font-family="sans-serif" text-anchor="middle">'
        f'FOMC statement{(" " + _xesc(note)) if note else ""}</text></svg>'
    )


def _fmt_date(date_str: str) -> str:
    """2026-07-29 -> JULY 29, 2026. Falls back to the raw string."""
    months = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
              "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")
    try:
        y, m, d = str(date_str).strip()[:10].split("-")
        return f"{months[int(m) - 1]} {int(d)}, {int(y)}"
    except (TypeError, ValueError, IndexError):
        return str(date_str or "").upper()


def _vote_caption(facts: dict) -> str:
    """"VOTE 9-3" / "VOTE 12-0 UNANIMOUS" / "" when there is no vote line."""
    vote = (facts or {}).get("vote")
    if not isinstance(vote, dict):
        return ""
    try:
        votes_for, against = int(vote["for"]), int(vote["against"])
    except (KeyError, TypeError, ValueError):
        return ""
    caption = f"VOTE {votes_for}-{against}"
    return f"{caption} UNANIMOUS" if against == 0 else caption


def _text(
    x: float, y: float, content: str, size: float, fill: str, *,
    weight: int = 400, anchor: str = "start", track: float = 0.0,
    family: str = "sans-serif",
) -> str:
    """One escaped <text> node."""
    extra = f' letter-spacing="{track:.1f}"' if track else ""
    anch = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size:.1f}" '
        f'font-weight="{weight}" font-family="{family}"{anch}{extra}>'
        f'{_xesc(content)}</text>'
    )


def _struck(
    x: float, y: float, content: str, size: float, fill: str, *, weight: int = 700
) -> tuple[str, float]:
    """Red-tinted STRUCK phrase. Returns (svg, advance_width).

    The rule is DRAWN rather than declared with `text-decoration`: the raster
    goes through headless Chrome, but the same SVG is also served to the admin
    preview and saved as an artifact, and a drawn line renders identically
    everywhere. Its width comes from the family's own measured estimator, which
    over-predicts on purpose, so the rule can only ever be a hair long.
    """
    width = _bc_text_w(content, size, bold=weight >= 600)
    svg = _text(x, y, content, size, fill, weight=weight)
    svg += (
        f'<rect x="{x:.1f}" y="{y - size * 0.30:.1f}" width="{width:.1f}" '
        f'height="{max(2.0, size * 0.075):.1f}" fill="{fill}" opacity="0.85"/>'
    )
    return svg, width


def _plan_highlights(
    rows: list[dict], *, line_size: float, text_w: float
) -> tuple[list[dict], int]:
    """Decide what the "what changed" block draws, and how many LINES it costs.

    Runs BEFORE any vertical space is committed so the analysis can be given
    everything this block does not need (see the space-accounting note in
    :func:`_render`). Returns (plan, total_lines) with total_lines never above
    MAX_HIGHLIGHT_LINES; a row that will not fit in what remains is dropped
    whole rather than half-drawn.
    """
    plan: list[dict] = []
    used = 0
    arrow = "  →  "
    for row in rows:
        left = MAX_HIGHLIGHT_LINES - used
        if left <= 0:
            break
        kind = str(row.get("kind") or "")
        removed = _house_dash(str(row.get("removed_text") or "").strip())
        added = _house_dash(str(row.get("added_text") or "").strip())

        if kind == "changed" and removed and added:
            fits_one = (
                _bc_text_w(removed, line_size) + _bc_text_w(arrow, line_size)
                + _bc_text_w(added, line_size)
            ) <= text_w
            if fits_one:
                plan.append({"op": "inline", "removed": removed, "added": added})
                used += 1
                continue
            if left < 2:
                continue
            plan.append({
                "op": "stacked",
                "removed": _bc_wrap_w(removed, line_size, text_w, 1)[0][0],
                "added": _bc_wrap_w(added, line_size, text_w, 1)[0][0],
            })
            used += 2
            continue

        is_add = kind == "added" or (added and not removed)
        body = added if is_add else removed
        if not body:
            continue
        take = min(_SENTENCE_ROW_LINES, left)
        wrapped, _over = _bc_wrap_w(body, line_size, text_w, take, bold=False)
        wrapped = [ln for ln in wrapped if ln]
        if not wrapped:
            continue
        plan.append({"op": "block", "lines": wrapped, "add": is_add})
        used += len(wrapped)
    return plan, used


def render_fomc_card(
    *,
    date_str: str,
    decision_line: str | None,
    analysis_paragraphs: list[str],
    highlights: list[dict],
    facts: dict | None = None,
    unchanged_count: int | None = None,
    prior_date: str | None = None,
    width: int = CARD_W,
    height: int = CARD_H,
    fit: dict | None = None,
) -> str:
    """Render the statement-diff card SVG. Never raises.

    Args:
        date_str: decision date, YYYY-MM-DD.
        decision_line: the plain-word decision sentence
            (engine.marketing.fomc_diff.decision_line). None draws the eyebrow
            block without a hero, which is the honest look for a statement whose
            decision sentence we could not positively extract.
        analysis_paragraphs: the model's 2-4 short paragraphs. THE ARGUMENT.
        highlights: fomc_diff.highlights() rows, best first. Drawn against a
            LINE budget (MAX_HIGHLIGHT_LINES), not a row count, because one added
            sentence legitimately costs two lines and six of those would not fit.
        facts: fomc_diff.extract_facts() output, read for the vote chip only.
        unchanged_count: sentences carried over verbatim; drawn as the quiet
            counterweight to the highlights ("6 sentences unchanged" is the
            context that makes three changes meaningful).
        prior_date: the meeting being diffed against, for the section subtitle.
        fit: optional caller-owned out-param, populated with what was actually
            DRAWN (body size, paragraphs drawn/dropped, highlight lines). Left
            untouched on the fail-soft path, so a caller reading a missing key
            knows the render degraded.

    Returns:
        Self-contained SVG. No <script>. Every caller string escaped.
        Deterministic for a given input (no clock, no randomness).
    """
    try:
        return _render(
            date_str=date_str, decision_line=decision_line,
            analysis_paragraphs=analysis_paragraphs, highlights=highlights,
            facts=facts or {}, unchanged_count=unchanged_count,
            prior_date=prior_date, width=int(width), height=int(height), fit=fit,
        )
    except Exception as exc:  # noqa: BLE001 — a card may degrade, never raise
        log.warning("render_fomc_card: fell through to the fallback (%s: %s)",
                    type(exc).__name__, exc)
        print(f"::warning title=fomc-card-render-degraded::{date_str}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return _fallback_svg(int(width), int(height), str(date_str or ""))


def _render(
    *,
    date_str: str,
    decision_line: str | None,
    analysis_paragraphs: list[str],
    highlights: list[dict],
    facts: dict,
    unchanged_count: int | None,
    prior_date: str | None,
    width: int,
    height: int,
    fit: dict | None,
) -> str:
    k = width / float(CARD_W)

    def u(v: float) -> float:
        """A 1080-space measurement in this card's units."""
        return v * k

    uid = str(zlib.crc32(f"fomc{date_str}".encode("utf-8")) & 0xFFFFFFFF)
    pad = u(72)
    col_w = width - pad * 2
    parts: list[str] = []
    defs: list[str] = []

    # ── Masthead ─────────────────────────────────────────────────────────────
    mast_h = min(u(112), height * 0.11)
    rule_h = max(3.0, u(7))
    logo_tile = mast_h * 0.535
    logo_cx = pad + logo_tile / 2
    logo_cy = mast_h / 2
    logo_defs, logo_group = _favicon_logomark(logo_cx, logo_cy, size=logo_tile, uid=uid)
    defs.append(logo_defs)
    wordmark = mast_h * 0.30
    parts.append(f'<rect x="0" y="0" width="{width}" height="{mast_h:.1f}" '
                 f'fill="{_MAST_BG}" opacity="0.92"/>')
    parts.append(logo_group)
    parts.append(_text(logo_cx + logo_tile / 2 + u(16), logo_cy + wordmark * 0.36,
                       "MASTERMIND", wordmark, "#ffffff", weight=900,
                       track=wordmark * 0.07))
    desk_size = mast_h * 0.19
    parts.append(_text(width - pad, logo_cy + desk_size * 0.36, "FOMC DESK",
                       desk_size, _BREAK_GREY, anchor="end", track=u(4)))
    parts.append(f'<rect x="0" y="{mast_h:.1f}" width="{width}" '
                 f'height="{rule_h:.1f}" fill="{_BREAK_AMBER}"/>')

    # ── Footer (no CTA: this card informs, it does not pitch) ─────────────────
    band_h = int(min(u(84), height * 0.085))
    bar_defs, footer = _brand_bar(
        width, height, uid,
        tagline=None,
        copyright_text="© 2026 Mastermind · Federal Reserve statement",
        show_button=False, band_h=band_h,
    )
    defs.append(bar_defs)

    y = mast_h + rule_h + u(48)

    # ── Eyebrow: desk label + the meeting date ───────────────────────────────
    eb_size = u(30)
    mark = u(24)
    parts.append(f'<rect x="{pad:.1f}" y="{y - mark * 0.86:.1f}" '
                 f'width="{mark:.1f}" height="{mark:.1f}" rx="{u(4):.1f}" '
                 f'fill="{_BREAK_AMBER}"/>')
    eyebrow = "FOMC STATEMENT"
    parts.append(_text(pad + mark + u(16), y, eyebrow, eb_size, _BREAK_AMBER,
                       weight=900, track=u(6)))
    eb_w = _bc_text_w(eyebrow, eb_size) * 1.07 + u(6) * len(eyebrow)
    kx = pad + mark + u(16) + eb_w + u(26)
    parts.append(f'<circle cx="{kx:.1f}" cy="{y - eb_size * 0.32:.1f}" '
                 f'r="{u(4):.1f}" fill="{_BREAK_GREY}"/>')
    parts.append(_text(kx + u(18), y, _fmt_date(date_str), u(25), _BREAK_GREY,
                       weight=700, track=u(4)))
    y += u(30)

    # ── Hero: what the Committee did ─────────────────────────────────────────
    hero_lines: list[str] = []
    if decision_line:
        for size in (u(52), u(47), u(42)):
            lines, over = _bc_wrap_w(str(decision_line), size, col_w, 3)
            if not over:
                hero_size, hero_lines = size, lines
                break
        else:
            hero_size, hero_lines = u(42), _bc_wrap_w(
                str(decision_line), u(42), col_w, 3)[0]
        for line in hero_lines:
            y += hero_size * 1.06
            parts.append(_text(pad, y, line, hero_size, "#ffffff", weight=900))
        y += u(26)

    # ── Vote chip ────────────────────────────────────────────────────────────
    vote = _vote_caption(facts)
    if vote:
        chip_size = u(27)
        chip_h = u(58)
        chip_pad = u(26)
        chip_w = chip_pad * 2 + _bc_text_w(vote, chip_size) + u(4) * len(vote)
        dissent = facts.get("dissenters") if isinstance(facts, dict) else None
        accent = _BREAK_AMBER if (dissent or not facts.get("unanimous")) else _BREAK_GREY
        parts.append(
            f'<rect x="{pad:.1f}" y="{y:.1f}" width="{chip_w:.1f}" '
            f'height="{chip_h:.1f}" rx="{chip_h / 2:.1f}" fill="none" '
            f'stroke="{accent}" stroke-width="{max(2.0, u(3)):.1f}"/>'
        )
        parts.append(_text(pad + chip_pad, y + chip_h * 0.66, vote, chip_size,
                           accent, weight=900, track=u(4)))
        # Dissent names ride beside the chip, plain-word, never a slug.
        if isinstance(dissent, list) and dissent:
            surnames = [str(n).split()[-1] for n in dissent if str(n).strip()]
            pref = str(facts.get("dissent_preference") or "").strip()
            size_txt = str(facts.get("dissent_size") or "").strip()
            tail = ", ".join(surnames)
            if pref and size_txt:
                tail = f"{tail} wanted to {pref} by {size_txt} point"
            elif pref:
                tail = f"{tail} wanted to {pref}"
            d_size = u(26)
            d_lines, _over = _bc_wrap_w(
                tail, d_size, col_w - chip_w - u(24), 2, bold=False)
            dy = y + chip_h * 0.44
            for line in d_lines:
                parts.append(_text(pad + chip_w + u(24), dy, line, d_size,
                                   _BREAK_GREY, weight=600))
                dy += d_size * 1.24
        y += chip_h + u(34)

    # ── Space accounting ─────────────────────────────────────────────────────
    footer_top = height - band_h - u(30)
    available = footer_top - y

    # THE "WHAT CHANGED" BLOCK IS SIZED BY ITS CONTENT, NOT BY A FRACTION.
    #
    # The first version reserved a flat 44% of the free height for it. Measured on
    # the real July-2026 diff that block needed four lines and took twenty-two
    # lines' worth of room: the card shipped a visible void under the analysis AND
    # dropped the analysis's third paragraph for want of space that was sitting
    # empty six inches below it. Planning the highlights first costs one measuring
    # pass and hands every unused line back to the argument, which is the thing
    # the reader came for.
    line_size = u(30)
    line_step = line_size * 1.44
    gutter = u(26)
    text_x = pad + gutter
    text_w = col_w - gutter
    plan, plan_lines = _plan_highlights(
        highlights or [], line_size=line_size, text_w=text_w)
    # rule -> label -> first line -> ... -> bottom padding
    changed_budget = (u(38) + u(34) + plan_lines * line_step + u(20)
                      if plan else u(0))
    analysis_budget = max(u(0), available - changed_budget - u(28))

    # ── Analysis (the argument) ──────────────────────────────────────────────
    paragraphs = [str(p).strip() for p in (analysis_paragraphs or []) if str(p).strip()]
    body_size = _BODY_MIN * k
    drawn_lines: list[list[str]] = []
    for size in (u(35), u(33), u(31), u(30), _BODY_MIN * k):
        lines_per: list[list[str]] = []
        total = 0.0
        fits = True
        for para in paragraphs:
            lines, over = _bc_wrap_w(para, size, col_w, 8, bold=False)
            if over:
                fits = False
            lines_per.append(lines)
            total += len(lines) * size * 1.42 + size * 0.66
        if fits and total <= analysis_budget:
            body_size, drawn_lines = size, lines_per
            break
        body_size, drawn_lines = size, lines_per
    # Draw as many whole paragraphs as the box holds. A paragraph is never
    # HALF-drawn: a truncated argument reads as a rendering bug, and the writer
    # is asked for 2-4 short paragraphs precisely so this is rare.
    paras_drawn = 0
    py = y
    for lines in drawn_lines:
        block_h = len(lines) * body_size * 1.42 + body_size * 0.66
        if py - y + block_h > analysis_budget and paras_drawn > 0:
            break
        for line in lines:
            py += body_size * 1.42
            parts.append(_text(pad, py, line, body_size, _BREAK_BODY, weight=400))
        py += body_size * 0.66
        paras_drawn += 1

    # ── What changed (bottom-anchored, drawn from the plan above) ────────────
    lines_drawn = 0
    if plan:
        cy = footer_top - changed_budget
        parts.append(f'<rect x="{pad:.1f}" y="{cy:.1f}" width="{col_w:.1f}" '
                     f'height="{max(2.0, u(2)):.1f}" fill="{_BREAK_RULE}"/>')
        cy += u(38)
        label_size = u(26)
        parts.append(_text(pad, cy, "WHAT CHANGED", label_size, _BREAK_AMBER,
                           weight=900, track=u(5)))
        sub_bits: list[str] = []
        if prior_date:
            sub_bits.append(f"vs {_fmt_date(prior_date).title()}")
        if isinstance(unchanged_count, int) and unchanged_count > 0:
            sub_bits.append(f"{unchanged_count} sentences unchanged")
        if sub_bits:
            parts.append(_text(width - pad, cy, " · ".join(sub_bits), u(24),
                               _BREAK_GREY, weight=600, anchor="end"))
        cy += u(34)

        arrow = "  →  "
        for step in plan:
            op = step["op"]
            if op == "inline":
                cy += line_step
                parts.append(_text(pad, cy, "~", line_size, _BREAK_GREY, weight=700))
                svg, adv = _struck(text_x, cy, step["removed"], line_size, _BREAK_DOWN)
                parts.append(svg)
                ax = text_x + adv
                parts.append(_text(ax, cy, arrow, line_size, _BREAK_GREY))
                parts.append(_text(ax + _bc_text_w(arrow, line_size), cy,
                                   step["added"], line_size, _BREAK_UP, weight=700))
                lines_drawn += 1
            elif op == "stacked":
                cy += line_step
                parts.append(_text(pad, cy, "~", line_size, _BREAK_GREY, weight=700))
                svg, _adv = _struck(text_x, cy, step["removed"], line_size,
                                    _BREAK_DOWN)
                parts.append(svg)
                cy += line_step
                parts.append(_text(text_x, cy, step["added"], line_size, _BREAK_UP,
                                   weight=700))
                lines_drawn += 2
            else:  # block — a whole sentence appeared or disappeared
                colour = _BREAK_UP if step["add"] else _BREAK_DOWN
                for i, line in enumerate(step["lines"]):
                    cy += line_step
                    if i == 0:
                        parts.append(_text(pad, cy, "+" if step["add"] else "-",
                                           line_size, colour, weight=900))
                    parts.append(_text(text_x, cy, line, line_size, colour,
                                       weight=600))
                    lines_drawn += 1

    parts.append(footer)

    if fit is not None and isinstance(fit, dict):
        fit["body_size"] = round(body_size / k, 1)
        fit["paragraphs_supplied"] = len(paragraphs)
        fit["paragraphs_drawn"] = paras_drawn
        fit["highlight_lines_drawn"] = lines_drawn
        fit["highlights_supplied"] = len(highlights or [])
        fit["highlight_rows_drawn"] = len(plan)

    defs_svg = "".join(d for d in defs if d)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'<defs>{defs_svg}</defs>'
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>'
        f'{"".join(parts)}'
        f'</svg>'
    )
