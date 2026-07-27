"""engine.press.properties — W1.5 per-publication static property renderer.

Builds ONE publication's whole static property from two inputs and nothing
else: the append-only press ledger (data/press/published.jsonl) and the .md
archive those rows point at.  Front page, article pages, RSS, sitemap, robots,
JSON-LD and the stamped stylesheet.

NO LLM.  NO NETWORK.  NO WALL CLOCK.

THE CLOCK LAW (pinned by tests/test_press_properties.py, which greps this file):
nothing here may read the current time.  Every timestamp on every page comes
from a ledger row's `ts` or a .md file's frontmatter, so two runs over the same
inputs produce byte-identical trees — which is the only reason
`scripts/build_press_properties.py --check` can exist at all.  A single
wall-clock read (a "generated at" stamp, an RSS lastBuildDate taken from the
current instant) would make that check red on every run and it would be turned
off within a week.  RFC-822 pubDates are DERIVED from the stored ISO instants,
never from the clock.

PRE-CUTOVER SHAPE.  This renderer works today, at `cutover: false`, and what it
produces then is deliberately partial: every ledger row still points at the
flagship /blog/ estate, so those articles appear on the property's front page
and in its RSS feed as CROSS-DOMAIN links, with no local article file and no
sitemap entry.  A row is NATIVE only when its url starts with the publication's
own base_url, which is exactly what routed emit writes after cutover.  Nothing
here needs a migration to cross that line: the ledger row carries its own URL,
so old rows keep pointing where they were actually published.

WHAT IS NOT DONE HERE, on purpose: nothing is PRUNED.  The ledger is
append-only, so a file in the tree with no row behind it means somebody hand
edited the tree; `--check` reports it as drift rather than silently deleting
the evidence.
"""
from __future__ import annotations

import email.utils
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

log = logging.getLogger(__name__)

# Where a pre-cutover row was published when it carries no explicit url.  This
# is the flagship /blog/ estate and it is NOT read from config on purpose: it
# describes rows that were written before the url field existed, so it is a
# statement about HISTORY, and history does not move when config does.
_FLAGSHIP_BASE = "https://www.mastermind-x.com"

_FEED_MAX_ITEMS = 20
_WORDS_PER_MINUTE = 200

# Publication key -> template/asset prefix.  Adding a publication with a
# property tree means adding its four templates and its stylesheet; an
# unmapped key raises rather than guessing a filename that does not exist.
_TEMPLATE_PREFIX: dict[str, str] = {
    "mastermind_news": "news",
    "mastermind_research": "research",
}

_TAG_RE = re.compile(r"<[^>]+>")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# A slug becomes a FILE PATH (articles/<slug>.html) and a URL. Anything outside
# this alphabet is either a path escape or a link that will not resolve, and the
# estate frontmatter contract already forbids it — this is the second lock,
# checked on the way OUT of the ledger rather than on the way in.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _annotate(level: str, title: str, message: str) -> None:
    """GitHub annotation.  Bare print, line-start, flushed — a logger would
    prefix the line and GitHub would silently drop it (house law)."""
    print(f"::{level} title={title}::{message}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────────────────────────────────────


def _env(root: Path | str | None = None):
    """The property template environment.

    StrictUndefined is the whole point: these templates are written against a
    fixed context contract, and a renamed context key must blow up at build
    time rather than ship a page with a silently blank masthead.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: PLC0415

    return Environment(
        loader=FileSystemLoader(str(templates_dir(root))),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def repo_root(root: Path | str | None = None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent


def templates_dir(root: Path | str | None = None) -> Path:
    return repo_root(root) / "templates" / "press"


# ─────────────────────────────────────────────────────────────────────────────
# Config projection
# ─────────────────────────────────────────────────────────────────────────────


def template_prefix(pub_key: str) -> str:
    try:
        return _TEMPLATE_PREFIX[str(pub_key)]
    except KeyError:
        raise ValueError(
            f"publication {pub_key!r} has no template set — add it to "
            f"engine/press/properties._TEMPLATE_PREFIX and ship "
            f"templates/press/<prefix>_{{front,article,about,404}}.html.j2 "
            f"plus templates/press/press_<prefix>.css"
        ) from None


def publication_context(cfg: dict, pub_key: str) -> dict:
    """The `pub` dict every template receives.

    Every key is always present — StrictUndefined turns a missing one into a
    render failure, and a masthead is not the place to discover that.
    """
    pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}
    pub = pubs.get(pub_key) or {}
    if not isinstance(pub, dict):
        pub = {}
    return {
        "key": str(pub_key),
        "label": str(pub.get("label") or pub_key),
        "domain": str(pub.get("domain") or ""),
        "base_url": str(pub.get("base_url") or "").rstrip("/"),
        "tagline": str(pub.get("tagline") or ""),
    }


def property_tree_path(root: Path | str | None, cfg: dict, pub_key: str) -> Path:
    pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}
    rel = ((pubs.get(pub_key) or {}) if isinstance(pubs.get(pub_key), dict) else {}).get("property_tree")
    if not rel:
        raise ValueError(f"publication {pub_key!r} carries no property_tree")
    return repo_root(root) / str(rel)


def publications_with_trees(cfg: dict) -> list[str]:
    """Every publication key that owns a property tree, in config order."""
    pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}
    return [k for k, v in pubs.items() if isinstance(v, dict) and v.get("property_tree")]


def _footer_text(cfg: dict) -> str:
    validators = (cfg.get("validators") or {}) if isinstance(cfg, dict) else {}
    return str(validators.get("footer_required_text") or "")


# ─────────────────────────────────────────────────────────────────────────────
# Time formatting — every value here is DERIVED from stored data
# ─────────────────────────────────────────────────────────────────────────────


def _parse_instant(raw: Any) -> datetime | None:
    """Parse a ledger `ts` or a frontmatter date into an aware UTC instant."""
    s = str(raw or "").strip()
    if not s:
        return None
    iso = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def display_date(dt: datetime | None) -> str:
    """"Jul 27, 2026".

    Built from an explicit month table rather than strftime("%b"): %b is
    LOCALE-DEPENDENT, so a runner with a non-English locale would render a
    different byte string for the same input and turn `--check` red for a
    reason nobody would find.
    """
    if dt is None:
        return ""
    return f"{_MONTHS[dt.month - 1]} {dt.day}, {dt.year}"


def _rfc822(dt: datetime) -> str:
    """RFC-822 pubDate, derived from a stored instant (never from the clock)."""
    return email.utils.format_datetime(dt, usegmt=True)


# ─────────────────────────────────────────────────────────────────────────────
# The .md archive
# ─────────────────────────────────────────────────────────────────────────────


def _parse_md(path: Path) -> tuple[dict, str]:
    """Split frontmatter + HTML body fragment from a .md file.

    Mirrors scripts.build_free_content._parse_md deliberately rather than
    importing it: that module pulls the whole estate builder (jinja2 templates,
    lib.pages, lib.seo, config.yml) for fifteen lines of string splitting.
    tests/test_press_properties.py pins the two against each other so the
    mirror cannot drift into a second, different contract.
    """
    import yaml  # noqa: PLC0415

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path}: must start with '---' frontmatter fence")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError(f"{path}: frontmatter closing '---' not found")
    fm = yaml.safe_load(text[3:end].strip()) or {}
    return (fm if isinstance(fm, dict) else {}), text[end + 4:].strip()


def _md_search_paths(root: Path, cfg: dict, pub_key: str, slug: str) -> list[Path]:
    """Where this publication's .md for `slug` could live, in priority order.

    The publication's own content_dir first (post-cutover pieces), then the
    flagship estate (every pre-cutover piece).  Both are searched regardless of
    the cutover flag: a ledger spans the flip, so a renderer that only looked
    at one side would drop half the archive on the day the switch moved.
    """
    out: list[Path] = []
    pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}
    pub = pubs.get(pub_key)
    content_dir = (pub or {}).get("content_dir") if isinstance(pub, dict) else None
    if content_dir:
        out.append(root / str(content_dir) / f"{slug}.md")
    estate = ((cfg.get("paths") or {}).get("content_dir") or "content/seo/blog")
    out.append(root / str(estate) / f"{slug}.md")
    return out


def reading_minutes(body_html: str) -> int:
    """Whole minutes at 200 wpm, floored at 1 — a zero-minute read is a bug."""
    words = len(_TAG_RE.sub(" ", body_html or "").split())
    return max(1, round(words / _WORDS_PER_MINUTE))


def _chrome_pattern(css_class: str, *, leading: bool) -> re.Pattern:
    cls = re.escape(str(css_class))
    para = rf'<p[^>]*\bclass="[^"]*\b{cls}\b[^"]*"[^>]*>.*?</p>'
    return re.compile(rf"\A\s*{para}\s*" if leading else rf"\s*{para}\s*\Z",
                      re.DOTALL | re.IGNORECASE)


def strip_estate_chrome(body_html: str, cfg: dict) -> str:
    """Drop the in-body byline and disclosure footer for a PROPERTY page.

    THE DOUBLE-CHROME PROBLEM.  engine/press/validators.py REQUIRES every press
    .md to open with a `press-byline` paragraph and close with a `press-footer`
    paragraph carrying the standing disclosure verbatim — and that requirement
    stays, because the .md is the archive of record AND the source the
    free-content estate renders /blog/ pages from, where the body carries its
    own provenance.

    A property page is different: its template renders the byline in the
    article header and the disclosure in the site footer.  Pasting the body in
    unmodified prints both TWICE — a duplicated byline under the one the
    template just drew, and the disclosure once in the article and once in the
    footer.  So the chrome is stripped HERE, at property render, and nowhere
    else: the .md on disk is untouched, the validator contract is untouched,
    and the estate render is untouched.

    Tolerant of surrounding whitespace and a no-op when either paragraph is
    absent — a hand-written .md that never had them renders unchanged.
    """
    validators = (cfg.get("validators") or {}) if isinstance(cfg, dict) else {}
    body = body_html or ""
    byline_class = str(validators.get("byline_class") or "press-byline")
    footer_class = str(validators.get("footer_class") or "press-footer")
    body = _chrome_pattern(byline_class, leading=True).sub("", body, count=1)
    body = _chrome_pattern(footer_class, leading=False).sub("", body, count=1)
    return body.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Ledger -> articles
# ─────────────────────────────────────────────────────────────────────────────


def _read_ledger(root: Path, cfg: dict) -> list[dict]:
    rel = ((cfg.get("paths") or {}).get("ledger") or "data/press/published.jsonl")
    path = root / str(rel)
    if not path.exists():
        return []
    import json  # noqa: PLC0415

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _desk_labels(cfg: dict, desk: str, pub: dict) -> tuple[str, str]:
    """(desk_label, byline) for a ledger row's desk."""
    desks = (cfg.get("desks") or {}) if isinstance(cfg, dict) else {}
    d = desks.get(desk) if isinstance(desks.get(desk), dict) else {}
    label = str((d or {}).get("label") or "")
    if not label:
        # Derived, not invented: "research_desk" -> "Research Desk". An operator
        # who wants different wording adds `label:` to the desk in config.
        label = str(desk or "").replace("_", " ").strip().title() or pub["label"]
    byline = str((d or {}).get("byline") or "") or pub["label"]
    return label, byline


def _corrections(fm: dict) -> list[dict]:
    """Frontmatter corrections -> {date_display, text}.  Empty is the norm."""
    out: list[dict] = []
    for item in (fm.get("corrections") or []):
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            when = _parse_instant(item.get("date"))
        else:
            text, when = str(item).strip(), None
        if text:
            out.append({"date_display": display_date(when), "text": text})
    return out


def iter_publication_articles(root: Path | str, cfg: dict, pub_key: str, *,
                              extra_rows: list[dict] | None = None) -> list[dict]:
    """Every article this publication has published, NEWEST FIRST.

    The LEDGER is the source of truth for what exists, in what order, and at
    what URL; the .md archive supplies title, dek, body and byline.  A row whose
    .md is gone is SKIPPED with a loud annotation — rendering a page whose body
    we cannot read would put an empty article on a public front page, and
    dropping it silently would hide the archive loss that caused it.

    `extra_rows` are ledger rows not yet appended to disk (the emit path renders
    the piece it is publishing in the same pass that writes it).  They sort
    after the on-disk rows at equal timestamps, which is their true order.
    """
    root = Path(root)
    pub = publication_context(cfg, pub_key)
    base_url = pub["base_url"]
    rows = _read_ledger(root, cfg) + list(extra_rows or [])

    ordered: list[tuple[datetime, int, dict]] = []
    for idx, row in enumerate(rows):
        if str(row.get("publication") or "") != str(pub_key):
            continue
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        if not _SLUG_RE.match(slug):
            # A slug is joined onto the tree root to make a file path. A row
            # carrying "../../.." would write outside the property entirely, so
            # this refuses BEFORE any path is built rather than sanitising a
            # value we do not have to accept at all.
            _annotate("warning", "press_property_bad_slug",
                      f"press property {pub_key}: ledger row "
                      f"{row.get('id') or slug!r} carries slug {slug!r}, which is not "
                      f"lowercase-alphanumeric-hyphen — skipped, nothing written for it")
            continue

        md_path = next((p for p in _md_search_paths(root, cfg, pub_key, slug) if p.exists()),
                       None)
        if md_path is None:
            _annotate("warning", "press_property_orphan_row",
                      f"press property {pub_key}: ledger row {row.get('id') or slug!r} "
                      f"has no .md archive for slug {slug!r} — skipped. The row stays in "
                      f"the ledger (append-only); restore the .md to publish the page.")
            continue
        try:
            fm, body_html = _parse_md(md_path)
        except ValueError as exc:
            _annotate("warning", "press_property_orphan_row",
                      f"press property {pub_key}: unreadable archive {md_path} ({exc}) "
                      f"— slug {slug!r} skipped")
            continue

        published = _parse_instant(row.get("ts")) or _parse_instant(fm.get("published"))
        if published is None:
            _annotate("warning", "press_property_orphan_row",
                      f"press property {pub_key}: slug {slug!r} carries no readable "
                      f"publication date (ledger ts nor frontmatter `published`) — skipped")
            continue
        updated = _parse_instant(fm.get("updated"))
        show_updated = bool(updated and updated.date() != published.date())

        # The row's own url wins. `urls[0]` is deliberately NOT consulted as a
        # second source: for every row ever written it is byte-identical to the
        # derivation below, and two spellings of one fact is how they diverge.
        url = str(row.get("url") or "").strip() or f"{_FLAGSHIP_BASE}/blog/{slug}.html"
        desk_label, byline = _desk_labels(cfg, str(row.get("desk") or ""), pub)

        # NATIVE means "this property hosts the file at exactly this URL", and
        # that is a claim about a path, not a domain. A row on our own domain at
        # some OTHER path (an older layout, a hand-edited row) would otherwise
        # make us write articles/<slug>.html and then link somewhere else — a
        # sitemap entry for a URL we do not serve and an orphan file we do.
        # Demote it to a listing-only row and say so.
        native = bool(base_url) and url.startswith(base_url + "/")
        if native and url != f"{base_url}/articles/{slug}.html":
            _annotate("warning", "press_property_url_mismatch",
                      f"press property {pub_key}: row {row.get('id') or slug!r} claims "
                      f"{url} on this domain, but this property serves slug {slug!r} at "
                      f"{base_url}/articles/{slug}.html — listed on the front page and "
                      f"in the feed only; no local file, no sitemap entry")
            native = False

        ordered.append((published, idx, {
            "slug": slug,
            "title": str(fm.get("title") or row.get("title") or slug),
            "dek": str(fm.get("description") or ""),
            "body_html": strip_estate_chrome(body_html, cfg),
            "byline": byline,
            "desk_label": desk_label,
            "url": url,
            "native": native,
            "published_iso": _iso_z(published),
            "published_display": display_date(published),
            "updated_iso": _iso_z(updated) if show_updated else "",
            "updated_display": display_date(updated) if show_updated else "",
            "reading_minutes": reading_minutes(body_html),
            "corrections": _corrections(fm),
            "publication": str(pub_key),
        }))

    ordered.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [a for _, _, a in ordered]


# ─────────────────────────────────────────────────────────────────────────────
# JSON-LD
# ─────────────────────────────────────────────────────────────────────────────


def jsonld_for(pub: dict, article: dict) -> str:
    """Serialized schema.org JSON-LD for one article page.

    EVERY field is a fact we hold.  No fabricated author persons, no invented
    ratings, no wordCount we did not measure, no image we do not ship — a
    structured-data block is a machine-readable claim, and inventing one is
    inventing it in the most quotable form there is.  `author` is the
    ORGANISATION (the desk), because these pieces are desk copy: naming a
    person would be a fabricated person.
    """
    import json  # noqa: PLC0415

    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "NewsArticle" if pub["key"] == "mastermind_news" else "Article",
        "headline": article["title"],
        "description": article["dek"],
        "datePublished": article["published_iso"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": article["url"]},
        "url": article["url"],
        "author": {"@type": "Organization",
                   "name": article.get("byline") or pub["label"]},
        "publisher": {"@type": "Organization", "name": "Mastermind",
                      "url": _FLAGSHIP_BASE},
        "isAccessibleForFree": True,
    }
    if article.get("updated_iso"):
        data["dateModified"] = article["updated_iso"]
    return _script_safe_json(json.dumps(data, ensure_ascii=False, indent=2,
                                        sort_keys=False))


def _script_safe_json(payload: str) -> str:
    """Escape the three characters that can break OUT of a <script> element.

    A JSON-LD block is injected raw into `<script type="application/ld+json">`,
    and HTML parsing beats JSON parsing: a title containing `</script>` ends the
    element early, and everything after it is parsed as MARKUP. That is script
    injection through a headline — and the headline comes from a .md file, which
    an LLM wrote. Autoescaping is not the answer either: it would turn every
    quote into `&#34;` and the block would parse as nothing at all.

    `\\u003c` / `\\u003e` / `\\u0026` are ordinary JSON string escapes, so the
    PARSED object is byte-identical to the unescaped one — only the wire form
    changes.

    ORDER IS PROVABLY IRRELEVANT, which is worth stating because the obvious
    worry is that one pass corrupts another's output. It cannot: every
    replacement emits `\\u00XX`, and none of `\\`, `u`, `0`, `2`, `3`, `6`, `c`,
    `e` is one of the three TRIGGER characters `&`, `<`, `>`. The inputs and the
    outputs are disjoint alphabets, so no pass can re-match what an earlier pass
    wrote and all six orderings produce the same string. (`&` runs first here
    only because that is the order a reader expects; the test pins the
    equivalence rather than the order, so a future reshuffle cannot silently
    matter.)
    """
    return (payload.replace("&", "\\u0026")
                   .replace("<", "\\u003c")
                   .replace(">", "\\u003e"))


# ─────────────────────────────────────────────────────────────────────────────
# Feed / sitemap / robots
# ─────────────────────────────────────────────────────────────────────────────


def _cdata(text: str) -> str:
    """CDATA wrap, closing any embedded ]]> (the estate builder's idiom)."""
    return "<![CDATA[" + str(text).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def feed_xml(pub: dict, articles: list[dict]) -> str:
    """RSS 2.0.  Valid with ZERO items — an empty feed is a real state.

    lastBuildDate is the newest ITEM's pubDate, and it is OMITTED entirely when
    there are no items.  Both halves matter: taking it from the clock would make
    the file change on every build, and emitting an empty element would make it
    a lie about a build that produced nothing.
    """
    base = pub["base_url"]
    items = articles[:_FEED_MAX_ITEMS]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{_cdata(pub['label'])}</title>",
        f"    <link>{_xml_escape(base + '/')}</link>",
        f"    <description>{_cdata(pub['tagline'])}</description>",
        "    <language>en</language>",
        f'    <atom:link href="{_xml_escape(base + "/feed.xml")}" rel="self" '
        'type="application/rss+xml"/>',
    ]
    if items:
        newest = _parse_instant(items[0]["published_iso"])
        if newest is not None:
            lines.append(f"    <lastBuildDate>{_rfc822(newest)}</lastBuildDate>")
    for a in items:
        when = _parse_instant(a["published_iso"])
        lines.extend([
            "    <item>",
            f"      <title>{_cdata(a['title'])}</title>",
            f"      <link>{_xml_escape(a['url'])}</link>",
            f"      <description>{_cdata(a['dek'])}</description>",
        ])
        if when is not None:
            lines.append(f"      <pubDate>{_rfc822(when)}</pubDate>")
        lines.extend([
            f'      <guid isPermaLink="true">{_xml_escape(a["url"])}</guid>',
            "    </item>",
        ])
    lines.extend(["  </channel>", "</rss>", ""])
    return "\n".join(lines)


def sitemap_xml(pub: dict, articles: list[dict]) -> str:
    """SAME-DOMAIN urls only.

    A cross-domain row (every pre-cutover piece) belongs on the front page and
    in the feed — it is genuinely one of this desk's articles — but listing
    another host's URL in this host's sitemap is a claim we do not get to make,
    and search engines treat it as one.
    """
    base = pub["base_url"]
    natives = [a for a in articles if a.get("native")]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    front = ["  <url>", f"    <loc>{_xml_escape(base + '/')}</loc>"]
    if natives:
        newest = _parse_instant(natives[0]["published_iso"])
        if newest is not None:
            front.append(f"    <lastmod>{newest.date().isoformat()}</lastmod>")
    front.append("  </url>")
    lines.extend(front)
    lines.extend(["  <url>", f"    <loc>{_xml_escape(base + '/about.html')}</loc>", "  </url>"])
    for a in natives:
        when = _parse_instant(a["published_iso"])
        lines.append("  <url>")
        lines.append(f"    <loc>{_xml_escape(a['url'])}</loc>")
        if when is not None:
            lines.append(f"    <lastmod>{when.date().isoformat()}</lastmod>")
        lines.append("  </url>")
    lines.extend(["</urlset>", ""])
    return "\n".join(lines)


def robots_txt(pub: dict) -> str:
    return ("User-agent: *\n"
            "Allow: /\n"
            f"Sitemap: {pub['base_url']}/sitemap.xml\n")


# ─────────────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────────────


def _markup(text: str):
    """Mark a value as already-safe HTML for an autoescaping template.

    Two values in the article context are HTML/JSON payloads, not text: the
    body fragment and the pre-serialized JSON-LD.  Autoescape would turn both
    into visible source — an article body rendered as literal `<p>` tags, and a
    structured-data block whose every quote is `&#34;` and which therefore
    parses as nothing.  Wrapping them here means the template renders correctly
    whether or not it remembers `| safe`, which is the right default for a
    context contract handed to a template author working in another lane.
    """
    from markupsafe import Markup  # noqa: PLC0415

    return Markup(text)


def _write(tree: Path, rel: str, payload: bytes, written: list[str]) -> None:
    dst = tree / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(payload)
    written.append(rel)


def css_stamp(payload: bytes) -> str:
    """Cache-buster for the property stylesheet.

    sha1 truncated to 10 hex chars — a content address, not a security
    primitive: it exists so a changed stylesheet gets a new URL.
    """
    return hashlib.sha1(payload).hexdigest()[:10]  # noqa: S324


def render_property(root: Path | str, cfg: dict, pub_key: str, *,
                    dest: Path | str | None = None,
                    extra_rows: list[dict] | None = None) -> list[str]:
    """Write one publication's whole property tree.  Returns written relpaths.

    `dest` overrides the output root (used by `--check`, which renders to a temp
    dir and byte-compares); the DATA still comes from `root` either way.
    """
    root = Path(root)
    pub = publication_context(cfg, pub_key)
    if not pub["base_url"]:
        raise ValueError(f"publication {pub_key!r} carries no base_url — every URL on the "
                         "property is built from it")
    prefix = template_prefix(pub_key)
    tree = Path(dest) if dest is not None else property_tree_path(root, cfg, pub_key)
    env = _env(root)
    articles = iter_publication_articles(root, cfg, pub_key, extra_rows=extra_rows)
    written: list[str] = []

    # Stylesheet first: css_href carries its content stamp, so the pages cannot
    # be rendered until the bytes that produce the stamp are known.
    css_name = f"press_{prefix}.css"
    css_bytes = (templates_dir(root) / css_name).read_bytes()
    css_href = f"/assets/{css_name}?v={css_stamp(css_bytes)}"
    _write(tree, f"assets/{css_name}", css_bytes, written)
    fonts = templates_dir(root) / "fonts"
    if fonts.is_dir():
        for font in sorted(fonts.glob("*.woff2")):
            _write(tree, f"assets/fonts/{font.name}", font.read_bytes(), written)

    base_ctx = {"pub": pub, "css_href": css_href, "footer_text": _footer_text(cfg)}
    nav = {"feed_href": "/feed.xml", "about_href": "/about.html"}

    def _page(rel: str, template: str, **ctx: Any) -> None:
        html = env.get_template(template).render(**base_ctx, **ctx)
        _write(tree, rel, html.encode("utf-8"), written)

    _page("index.html", f"{prefix}_front.html.j2", articles=articles, **nav)
    _page("about.html", f"{prefix}_about.html.j2", flagship_url=_FLAGSHIP_BASE)
    _page("404.html", f"{prefix}_404.html.j2")
    for article in articles:
        if not article["native"]:
            continue          # cross-domain: listed here, hosted elsewhere
        renderable = dict(article, body_html=_markup(article["body_html"]))
        _page(f"articles/{article['slug']}.html", f"{prefix}_article.html.j2",
              a=renderable, jsonld=_markup(jsonld_for(pub, article)), **nav)

    _write(tree, "feed.xml", feed_xml(pub, articles).encode("utf-8"), written)
    _write(tree, "sitemap.xml", sitemap_xml(pub, articles).encode("utf-8"), written)
    _write(tree, "robots.txt", robots_txt(pub).encode("utf-8"), written)
    return sorted(written)
