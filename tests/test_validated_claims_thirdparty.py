"""BC-2: quoted third-party research is a structural non-claim — and nothing more.

The research vault mirrors syndicated institutional notes verbatim on the nightly render
path, so 'validated' arrives in its ordinary English sense ("the June CPI print validated
two likely sources of ongoing disinflation") with no artifact to cite. Before #3768 that
reddened check_validated_claims on main and blocked every open PR from ci-pack-0 until
someone hand-wrote an allowlist entry — an entry the allowlist's own purpose calls "a claim
of record", which a third-party quote is not ours to make.

scripts/check_validated_claims.py now masks the third-party TEXT SINKS of the three
syndicated render targets. These tests exist to pin that the exemption is a SINK exemption,
not a path exemption: for every shape where a quote passes, the same page carrying OUR OWN
affirmative claim must still fail. If someone widens the skip to "site/research/ is exempt",
the paired platform-authored case here goes green and this file fails.

Covers the four ways the skip could be wrong:
  1. too narrow — a real sink left unmapped (the recurrence returns)
  2. too wide  — our own copy on the same page silently exempted
  3. forgeable — the exemption obtainable without the builder's attestation
  4. leaky     — a malformed page exempting everything after its last opener
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_validated_claims import (  # noqa: E402
    _ATTEST,
    _EARNINGS_ARTICLE_ATTEST,
    _EARNINGS_INDEX_ATTEST,
    _EARNINGS_WEEKLY_ATTEST,
    _NEWS_ATTEST,
    _THIRD_PARTY_PAGES,
    TOKEN,
    _earnings_article,
    _earnings_index,
    _earnings_weekly,
    _load_allowlist,
    _news_page,
    _page,
    _third_party_specs,
    scan_text,
)

# A report page, the crawl hub, and the vault page — the three syndicated render targets.
REPORT = "site/research/us-daily-oil-and-inflation-3da181.html"
HUB = "site/research/index.html"
VAULT = "site/research_vault.html"

# Ordinary-English 'validated' in third-party economics prose: the sentence from the real
# note (site/research/us-daily-what-the-rebound-in-oil-prices-…-3da181.html:290) that reddened
# main on 2026-07-26. Note it is affirmative and un-hedged — the negation guards do NOT save
# it; only the third-party skip does.
QUOTED = ("we estimate that the Dallas Fed's trimmed mean PCE increased only 0.14% "
          "month-over-month in June—and validated two likely sources of ongoing disinflation")
# A Macro Dashboard claim: exactly what BC-2 exists to stop shipping unbacked.
OURS = "This rank is validated as a real cross-sectional alpha."
OURS_ZH = "该信号是已验证的方向性优势。"


@pytest.fixture(scope="module")
def allow():
    return _load_allowlist()


def _fire(rel: str, text: str, allow) -> bool:
    """Does the gate flag an unearned claim in `text` when scanned as `rel`?"""
    found, _ = scan_text(rel, text, allow)
    return bool(found)


# ── 1. the recurrence is closed: every third-party sink on every render target ──────────

@pytest.mark.parametrize("sink,page", [
    ("verbatim excerpt", _page(body=QUOTED)),
    ("report title", _page(title="Q2 Results Validated Our Thesis")),
    ("teaser + meta description", _page(teaser=QUOTED)),
    ("related report title", _page(related="Q2 Results Validated Our Thesis")),
])
def test_quoted_third_party_passes(sink, page, allow):
    """A syndicated note using 'validated' in its ordinary sense must not red the build."""
    assert not _fire(REPORT, page, allow), f"third-party {sink} wrongly flagged as a claim"


def test_crawl_hub_titles_pass(allow):
    hub = ('<p class="rx-sub">Every desk report in the vault — buy-side and sell-side.</p>\n'
           '<li><a href="x.html"><span class="ti">Q2 Results Validated Our Thesis</span></a></li>')
    assert not _fire(HUB, hub, allow)


def test_vault_baked_catalog_passes(allow):
    vault = ('<script id="rv-catalog" type="application/json">'
             '{"items":[{"title":"Q2 Results Validated Our Thesis",'
             '"summary_points":["The print validated the disinflation channel."]}]}</script>')
    assert not _fire(VAULT, vault, allow)


# ── 2. NOT a path exemption: our own copy on the same page still fails ──────────────────

@pytest.mark.parametrize("where,page", [
    ("paywall copy (.rr-gate)", _page(platform=OURS)),
    ("paywall copy, zh", _page(platform_zh=OURS_ZH)),
    ("platform claim beside a quoted one", _page(body=QUOTED, platform=OURS)),
])
def test_platform_claim_on_the_same_page_still_fails(where, page, allow):
    """The load-bearing test: same file, same page shape — our claim is still gated."""
    assert _fire(REPORT, page, allow), f"platform claim in {where} escaped the gate"


def test_platform_claim_on_the_crawl_hub_still_fails(allow):
    hub = ('<p class="rx-sub">Every desk report in the vault — buy-side and sell-side.</p>\n'
           f"<p>{OURS}</p>")
    assert _fire(HUB, hub, allow)


def test_platform_claim_on_the_vault_page_still_fails(allow):
    vault = ('<script id="rv-catalog" type="application/json">{"items":[]}</script>\n'
             f"<p>{OURS}</p>")
    assert _fire(VAULT, vault, allow)


def test_templates_are_never_exempt(allow):
    """templates/ is the safety invariant: every platform string on these pages is authored
    there, and the gate scans it with NO skip. The rendered-copy exemption is only sound
    because of this — so pin it."""
    assert _fire("templates/research_report.html.j2", _page(body=QUOTED, platform=OURS), allow)
    assert not _third_party_specs("templates/research_report.html.j2", _page())


def test_our_own_site_js_is_never_exempt(allow):
    assert _fire("site/research_vault.js", f"const s = '{OURS}';", allow)


def test_other_surfaces_unaffected(allow):
    """The same page bytes outside the three render targets get nothing."""
    assert _fire("site/leader_radar.html", _page(body=QUOTED), allow)
    assert not _third_party_specs("site/leader_radar.html", _page(body=QUOTED))


# ── 3. not forgeable: the builder's attestation is required ─────────────────────────────

def test_attestation_is_required(allow):
    """Living under site/research/ earns nothing — a hand-dropped page there is scanned in
    full. Guards against evading BC-2 by filename."""
    forged = _page(body=QUOTED, attest="Mastermind publishes research")
    assert _fire(REPORT, forged, allow)
    assert not _third_party_specs(REPORT, forged)
    assert _third_party_specs(REPORT, _page(body=QUOTED))   # …and the real one does qualify


def test_index_html_is_not_a_report_page(allow):
    """index.html is the crawl hub, a different template: it must not pick up the report
    page's regions even though it shares the directory."""
    assert not _third_party_specs(HUB, f'<div class="rr-x-body">{OURS}</div>')


# ── 4. fails closed on a malformed page ─────────────────────────────────────────────────

def test_unclosed_region_masks_nothing(allow):
    """An opener with no closer must be DISCARDED, not run to EOF — otherwise one broken
    tag would exempt the whole tail of the page."""
    broken = _page(body=QUOTED, platform=OURS).replace("</section>", "<!-- gone -->")
    assert _fire(REPORT, broken, allow)
    found, _ = scan_text(REPORT, broken, allow)
    # both the quote AND our claim are scanned — nothing was masked
    assert len(found) >= 2, f"expected the whole page scanned, got {found}"


def test_masking_cannot_forge_or_erase_a_claim(allow):
    """Splicing a line around an excised span must fail CLOSED: it may never create a
    negation that hides an adjacent claim of ours."""
    # 'no' ends the platform text; the quote is cut out between it and our token
    spliced = _page().replace(
        "<h1>Oil Prices and Upcoming Inflation Prints</h1>",
        f"<span>there is no</span><h1>{QUOTED}</h1><span>{OURS}</span>")
    assert _fire(REPORT, spliced, allow)


# ── the gate as CI runs it ──────────────────────────────────────────────────────────────

def test_selftest_still_fires_on_every_synthetic_claim():
    """--selftest is the EN+zh tripwire; the exemption must not blunt it."""
    r = subprocess.run([sys.executable, "-m", "scripts.check_validated_claims", "--selftest"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, f"selftest failed:\n{r.stdout}\n{r.stderr}"
    # match the STATUS TOKEN, not the word: several case names contain "STILL FAILS"
    assert "[FAIL]" not in r.stdout, r.stdout
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("[PASS]")]
    assert len(lines) >= 25, f"selftest lost cases — only {len(lines)} ran"


def test_real_tree_is_green_without_a_per_quote_allowlist_entry():
    """The structural skip — not an allowlist entry — is what holds the tree green."""
    entries = json.loads((ROOT / "data/regime/validated_claims_allowlist.json")
                         .read_text(encoding="utf-8"))["allow"]
    assert not any("disinflation" in e.get("match", "") for e in entries), (
        "the #3767 per-quote entry is back; quoted third-party text is handled structurally "
        "(see the allowlist's notes field)")
    assert not any("validated technology" in e.get("match", "") for e in entries), (
        "a per-quote earnings-wire entry is back; quoted call excerpts are handled "
        "structurally (see _THIRD_PARTY_PAGES entries 5–7). A per-quote row cannot "
        "hold: the wire regenerates nightly.")
    r = subprocess.run([sys.executable, "-m", "scripts.check_validated_claims"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


# ── the skip must be LOAD-BEARING, not merely harmless ─────────────────────────────────
#
# A skip that masks nothing is worse than one that fails: the gate reports safety it is not
# providing. Until 2026-08-07 that was pinned by naming the note that reddened main on
# 2026-07-26 (site/research/us-daily-what-the-rebound-in-oil-prices-…-3da181.html) and
# asserting its quote was masked. The page is still rendered and still mapped, but the quote
# is gone and NOTHING about the gate changed: the hourly ingest's excerpt snapshot
# (data/research_vault/excerpts.json) dropped from 912 entries to 2 at 2026-08-07T05:39Z, so
# the re-render that followed emitted no <div class="rr-x-body"> on ~905 report pages — the
# sink that quote lived in. The assertion did exactly its job: it refused to report "covered"
# for a page that had gone green because its text rotated away.
#
# The property is now pinned on both sides so neither half can go quiet:
#   * on IN-REPO fixture bytes, which cannot rotate — always runs;
#   * on the live tree, following _THIRD_PARTY_PAGES (the gate's own map) instead of a
#     filename, so a newly mapped render target is swept the day it is added.
# Both use the same control: strip the attestation — the only thing that earns the skip —
# and the very same bytes must fire. That is strictly stronger than counting the mask,
# because it proves WHAT greened the page rather than that something was excised.

def _live_candidates() -> list[Path]:
    """Every live file the third-party map can cover: the vault's report pages, their crawl
    hub, the vault app page, the China news tape, and the earnings-wire family.

    Earnings call-record articles are sampled, not walked in full: ~3k of them would
    re-read the same tree the full-gate test already scanned, and the existence
    check only needs one match per path_re. The WAVE article that reddened main
    is the load-bearing sample; index pages and weekly briefs are small enough
    to include whole.
    """
    return [p for p in (*sorted(ROOT.glob("site/research/*.html")),
                        ROOT / "site/research_vault.html",
                        ROOT / "site/china_news.html",
                        ROOT / "site/stocks/earnings/index.html",
                        *sorted(ROOT.glob("site/stocks/earnings/page-*.html")),
                        ROOT / "site/stocks/earnings/wave-2025q4-call-record.html",
                        *sorted(ROOT.glob("site/stocks/earnings/weekly/*.html")))
            if p.is_file()]


def _live_syndicated_renders() -> list[tuple[str, str]]:
    """(rel, bytes) for the live renders that carry the token at all. Prefiltered on TOKEN —
    the gate's own definition — so 900+ pages are read but only the few that say the word
    are scanned."""
    out = []
    for p in _live_candidates():
        text = p.read_text(encoding="utf-8")
        if TOKEN.search(html.unescape(text)):
            out.append((p.relative_to(ROOT).as_posix(), text))
    return out


def _unattested(rel: str, text: str) -> str:
    """`text` with its render's attestation literal removed, so it earns no exemption."""
    attest = next(a for path_re, a, _ in _THIRD_PARTY_PAGES if path_re.match(rel))
    return text.replace(attest, "Mastermind publishes research")


def test_the_skip_is_what_greens_a_quoted_page(allow):
    """Anti-vacuity on bytes that cannot rotate out: the quote is masked (counted), and
    without the attestation the identical page fires."""
    page = _page(body=QUOTED)
    found, stats = scan_text(REPORT, page, allow)
    assert not found
    assert stats["third_party"] >= 1, "the quote was not masked — something else greened it"

    bare = _unattested(REPORT, page)
    assert not _third_party_specs(REPORT, bare), "the exemption survived losing its literal"
    fired, st = scan_text(REPORT, bare, allow)
    assert fired, "the skip is not what greens the page — the unattested copy scans clean too"
    assert st["third_party"] == 0


def test_the_live_syndicated_renders_are_covered_by_the_skip(allow):
    """The same property against what actually ships. Every live render the map covers is
    green; wherever the mask carried a claim, removing the exemption fires it.

    Content-conditioned by nature — the vault mirrors third-party prose that rotates nightly,
    so on a day when no live note uses the word affirmatively in a mapped sink there is
    nothing to observe. That state skips rather than reddening main on innocent copy (which
    is the recurrence BC-2 exists to prevent); the fixture test above still pins the
    mechanism unconditionally.
    """
    masked: list[tuple[str, int]] = []
    load_bearing: list[tuple[str, int]] = []
    for rel, text in _live_syndicated_renders():
        found, stats = scan_text(rel, text, allow)
        assert not found, f"{rel}: syndicated render reports an unearned claim: {found}"
        if not stats["third_party"]:
            continue                    # token is in OUR chrome here, not in a mapped sink
        masked.append((rel, stats["third_party"]))
        bare = _unattested(rel, text)
        assert not _third_party_specs(rel, bare), f"{rel}: the exemption survived its literal"
        fired, st = scan_text(rel, bare, allow)
        assert st["third_party"] == 0, f"{rel}: masked with no exemption"
        if fired:                       # a hedged/negated quote is masked but never fired
            load_bearing.append((rel, stats["third_party"]))
    if not load_bearing:
        pytest.skip("no live syndicated render currently masks an affirmative 'validated' "
                    f"(masked-but-hedged: {masked}) — third-party prose rotates nightly")


def test_every_mapped_render_target_exists_in_the_live_tree():
    """The live sweep walks a candidate list, not the whole site. If a render target is
    mapped that the list cannot reach, the sweep silently stops covering it — fail here."""
    cands = [p.relative_to(ROOT).as_posix() for p in _live_candidates()]
    for path_re, _attest, _regions in _THIRD_PARTY_PAGES:
        assert any(path_re.match(c) for c in cands), (
            f"no live file matches mapped render {path_re.pattern!r} — "
            "_live_candidates() no longer reaches it")


def test_attestation_literals_still_exist_in_the_templates():
    """The skip keys off literals the builders emit. If a template edit drops one, the gate
    silently stops exempting that render and main goes red — catch it here instead."""
    report_j2 = (ROOT / "templates/research_report.html.j2").read_text(encoding="utf-8")
    assert _ATTEST in report_j2, f"research_report.html.j2 no longer emits {_ATTEST!r}"
    hub_j2 = (ROOT / "templates/research_index.html.j2").read_text(encoding="utf-8")
    assert "Every desk report in the vault" in hub_j2
    vault_j2 = (ROOT / "templates/research_vault.html.j2").read_text(encoding="utf-8")
    assert '<script id="rv-catalog"' in vault_j2
    news_j2 = (ROOT / "templates/china_news.html.j2").read_text(encoding="utf-8")
    assert _NEWS_ATTEST in news_j2, f"china_news.html.j2 no longer emits {_NEWS_ATTEST!r}"
    article_j2 = (ROOT / "templates/earnings_wire/earnings_wire_article.html.j2").read_text(
        encoding="utf-8")
    assert _EARNINGS_ARTICLE_ATTEST in article_j2, (
        f"earnings_wire_article.html.j2 no longer emits {_EARNINGS_ARTICLE_ATTEST!r}")
    index_j2 = (ROOT / "templates/earnings_wire/earnings_wire_index.html.j2").read_text(
        encoding="utf-8")
    assert _EARNINGS_INDEX_ATTEST in index_j2, (
        f"earnings_wire_index.html.j2 no longer emits {_EARNINGS_INDEX_ATTEST!r}")
    weekly_j2 = (ROOT / "templates/earnings_wire/earnings_weekly.html.j2").read_text(
        encoding="utf-8")
    assert _EARNINGS_WEEKLY_ATTEST in weekly_j2, (
        f"earnings_weekly.html.j2 no longer emits {_EARNINGS_WEEKLY_ATTEST!r}")


# ── the China news tape — same sink exemption, a feed that rotates every night ──────────
#
# 2026-08-07: a Sina wire headline ("Strong momentum in innovative drugs continues to be
# validated." / 创新药高景气持续验证) reddened main on site/china_news.html through TWO sinks
# at once — the .tp-title element text and the item's data-search attribute. It is an
# external publisher's sentence about a drug sector, not a Macro Dashboard claim, and it has
# no artifact to cite because it is not ours to back.
#
# An allowlist entry could not have held it: the tape is regenerated nightly from ingested
# headlines (engine/china_news.py -> templates/china_news.html.j2, rendered at
# scripts/build_china.py:1555), so the next headline carrying the word reds main again. Same
# reasoning, same remedy, same safety invariant as the research vault above: mask the SINKS
# the wire fields reach, never the page.
#
# EVERY fixture here is _news_page() — in-repo bytes that cannot rotate. Pinning against the
# live tape would repeat the exact 2026-08-07 vacuity documented above: the assertion goes
# green the night the headline changes, and reports coverage it is no longer providing. The
# live tape IS still swept, by _live_syndicated_renders() (site/china_news.html is now in
# _live_candidates), which follows _THIRD_PARTY_PAGES rather than a headline.

CN = "site/china_news.html"
# The live EN headline, verbatim. Its zh half (创新药高景气持续验证) carries NO BC-2 token —
# 持续验证 is not one of TOKEN's four forms — so both live findings came from the English, and
# a zh fixture built on it would pass for having nothing to match. WIRE_ZH is therefore a zh
# wire sentence that DOES carry one (已经验证, matched through 经验证).
WIRE = ("Power of earnings: CXO giant jumps 20% in a single week! Strong momentum in "
        "innovative drugs continues to be validated.")
WIRE_ZH = "创新药的高景气度已经验证。"
WIRE_SEARCH = WIRE.lower() + " " + WIRE_ZH        # the attribute is built |lower


def test_the_live_wire_zh_half_carries_no_token():
    """Pins the premise of the note above — if 持续验证 ever becomes a TOKEN form, the zh
    fixtures here must switch back to the live string."""
    assert not TOKEN.search("业绩的力量，CXO巨头单周暴涨20%！创新药高景气持续验证")
    assert TOKEN.search(WIRE) and TOKEN.search(WIRE_ZH)


@pytest.mark.parametrize("sink,page", [
    ("headline (.tp-title)", _news_page(title=WIRE)),
    ("headline, zh (.tp-title)", _news_page(title_zh=WIRE_ZH)),
    ("search index (data-search attribute)", _news_page(search=WIRE_SEARCH)),
    ("summary (.tp-sum)", _news_page(summary=WIRE)),
    ("summary, zh (.tp-sum)", _news_page(summary_zh=WIRE_ZH)),
    ("headline + search index at once, as it actually shipped",
     _news_page(title=WIRE, search=WIRE.lower())),
])
def test_wire_headline_sinks_pass(sink, page, allow):
    """A wire headline using 'validated' in its ordinary sense must not red the build."""
    assert not _fire(CN, page, allow), f"third-party news {sink} wrongly flagged as a claim"


# NOT a page exemption: everything on the tape that is OURS is still gated — including the
# copy that shares the very same <a class="tp-item"> wrapper. That wrapper is deliberately
# NOT the masked region: our theme chip, importance label and channel chips live inside it.

@pytest.mark.parametrize("where,page", [
    ("theme chip (.cn-tag), inside the item", _news_page(title=WIRE, theme=OURS)),
    ("importance label (.cn-imp), inside the item", _news_page(title=WIRE, imp=OURS)),
    ("channel chip (.cn-cchip), inside the item", _news_page(title=WIRE, chip=OURS)),
    ("hero lead (.cn-lead), above the feed", _news_page(title=WIRE, hero=OURS)),
    ("hero lead, zh", _news_page(title=WIRE, hero_zh=OURS_ZH)),
    ("disclaimer (.cn-disc), below the feed", _news_page(title=WIRE, disc=OURS)),
    ("disclaimer, zh", _news_page(title=WIRE, disc=OURS_ZH)),
])
def test_our_copy_on_the_news_tape_still_fails(where, page, allow):
    """The load-bearing half: same file, same item, our claim is still gated."""
    assert _fire(CN, page, allow), f"platform claim in {where} escaped the gate"


@pytest.mark.parametrize("sink,page", [
    ("headline (.tp-title)", _news_page(title=WIRE, title_zh=WIRE_ZH)),
    ("search index (data-search attribute)", _news_page(search=WIRE_SEARCH)),
    ("summary (.tp-sum)", _news_page(summary=WIRE, summary_zh=WIRE_ZH)),
])
def test_the_news_skip_is_what_greens_the_tape(sink, page, allow):
    """Anti-vacuity, per sink, on bytes that cannot rotate: BOTH tokens in the sink are
    masked (counted), and the identical page without the feed attestation fires. That is
    strictly stronger than counting the mask — it proves WHAT greened the page."""
    found, stats = scan_text(CN, page, allow)
    assert not found
    assert stats["third_party"] >= 2, (
        f"{sink}: expected the EN and zh tokens masked, got {stats['third_party']} — "
        "something other than the skip greened this page")

    bare = page.replace(_NEWS_ATTEST, '<div class="tp-feed">')
    assert not _third_party_specs(CN, bare), "the exemption survived losing its literal"
    fired, st = scan_text(CN, bare, allow)
    assert fired, f"{sink}: the skip is not what greens it — the unattested copy scans clean"
    assert st["third_party"] == 0


def test_the_news_template_is_never_exempt(allow):
    """Same safety invariant as the research vault: every platform string on this page is
    authored in templates/china_news.html.j2, which the gate scans with NO skip."""
    assert _fire("templates/china_news.html.j2", _news_page(title=WIRE, hero=OURS), allow)
    assert not _third_party_specs("templates/china_news.html.j2", _news_page())


def test_the_news_shape_earns_nothing_on_another_page(allow):
    """The exemption is bound to site/china_news.html. The identical markup elsewhere — a
    sibling news surface, a hand-dropped page — is scanned in full."""
    for rel in ("site/news.html", "site/china.html", "site/china_news_backup.html"):
        assert _fire(rel, _news_page(title=WIRE), allow), f"{rel} picked up the tape exemption"
        assert not _third_party_specs(rel, _news_page(title=WIRE))


def test_news_sink_literals_still_exist_in_the_template():
    """The three regions key off markup the template emits. If a class is renamed the gate
    silently stops exempting that sink and the next wire headline reds main — catch it
    here, where the fix is one line, instead of on somebody else's PR."""
    j2 = (ROOT / "templates/china_news.html.j2").read_text(encoding="utf-8")
    assert '<h2 class="tp-title">' in j2
    assert '<p class="tp-sum">' in j2
    assert any(ln.lstrip().startswith('data-search="') for ln in j2.splitlines()), (
        "china_news.html.j2 no longer emits data-search as the first token on its own line — "
        "the whole-line region in _THIRD_PARTY_PAGES no longer matches it")


def test_the_masked_search_attribute_carries_no_platform_copy_of_its_own():
    """The one place the tape's sink exemption is coarser than an element span.

    data-search is masked WHOLE-LINE (an attribute value cannot be span-delimited safely —
    china_news renders with autoescape=False, so a quote inside a headline would truncate a
    span mid-value). Its value is nearly all wire text, but the template also folds in the
    channel/theme display labels (templates/china_news.html.j2:319, `chsearch`). Those are
    OURS, they live in engine dicts that scan_python_copy does not reach (they are not
    display-copy FIELDS), and only the first four of five are re-emitted unmasked in the
    .cn-cchip chips — so the fifth would have no other gated sink. Pin them directly."""
    from engine.china_news import CHANNEL_LABEL, THEME_LABEL  # noqa: PLC0415

    for name, lex in (("CHANNEL_LABEL", CHANNEL_LABEL), ("THEME_LABEL", THEME_LABEL)):
        for slug, pair in lex.items():
            for word in pair:
                assert not TOKEN.search(word), (
                    f"engine.china_news.{name}[{slug!r}] = {word!r} carries the BC-2 token, "
                    "and it rides into the masked data-search attribute — either reword it "
                    "or narrow the data-search region before shipping this label")


# ── the earnings-wire family — same sink exemption, a feed that rotates every night ──
#
# 2026-08-15: an Eco Wave Power executive's sentence ("the combination of validated
# technology, growing global project pipeline…") reddened main on TWO renders at once
# — the call-record article and its directory-card preview. It is the speaker's own
# words inside a <blockquote>, not a Macro Dashboard claim, and it has no artifact
# to cite because it is not ours to back.
#
# An allowlist entry could not have held it: the wire regenerates nightly from
# ingested transcripts (scripts/build_earnings_public_wire.py), so the next call
# carrying the word reds main again. Same reasoning, same remedy, same safety
# invariant as the China news tape above: mask the SINK the quote field reaches,
# never the page. PR #5683 planted a per-quote row as a same-day heal; that row
# is the thing this section exists to make unnecessary.
#
# EVERY fixture here is _earnings_*() — in-repo bytes that cannot rotate. The live
# WAVE pages ARE still swept, by _live_syndicated_renders() (page-34 + the WAVE
# article + weekly briefs are now in _live_candidates).

EW_ARTICLE = "site/stocks/earnings/wave-2025q4-call-record.html"
EW_INDEX = "site/stocks/earnings/page-34.html"
EW_WEEKLY = "site/stocks/earnings/weekly/2026-03-16.html"
# The live EN sentence, verbatim. The wire has no zh half of the quote — transcripts
# are English — so there is no WIRE_ZH twin.
CALL = ("Overall, we believe that the combination of validated technology, "
        "growing global project pipeline, improving cost discipline, and increasing "
        "global demand for clean energy driven by AI positions Eco Wave Power well "
        "for the next phase of growth.")


@pytest.mark.parametrize("sink,rel,page", [
    ("article excerpt (_facts.html.j2)", EW_ARTICLE, _earnings_article(quote=CALL)),
    ("index card preview (earnings_wire_index.html.j2)", EW_INDEX, _earnings_index(quote=CALL)),
    ("weekly notable-record card (earnings_weekly.html.j2)",
     EW_WEEKLY, _earnings_weekly(quote=CALL)),
])
def test_earnings_quote_sinks_pass(sink, rel, page, allow):
    """A call excerpt using 'validated' in its ordinary sense must not red the build."""
    assert not _fire(rel, page, allow), f"third-party earnings {sink} wrongly flagged as a claim"


# NOT a page exemption: everything on the card that is OURS is still gated — including
# the copy that shares the very same <article> wrapper. That wrapper is deliberately
# NOT the masked region: our tags, attribution and receipt rows live inside it.

@pytest.mark.parametrize("where,rel,page", [
    ("category tag (.ew-tags), inside the article card",
     EW_ARTICLE, _earnings_article(quote=CALL, tag=OURS)),
    ("attribution (.ewa-attribution), inside the article card",
     EW_ARTICLE, _earnings_article(quote=CALL, attribution=OURS)),
    ("receipt row, below the excerpts",
     EW_ARTICLE, _earnings_article(quote=CALL, receipt=OURS)),
    ("category tag (.ew-tags), inside the index card",
     EW_INDEX, _earnings_index(quote=CALL, tag=OURS)),
    ("card-foot attribution, inside the index card",
     EW_INDEX, _earnings_index(quote=CALL, attribution=OURS)),
    ("category tag (.ew-tags), inside the weekly card",
     EW_WEEKLY, _earnings_weekly(quote=CALL, tag=OURS)),
    ("record-foot attribution, inside the weekly card",
     EW_WEEKLY, _earnings_weekly(quote=CALL, attribution=OURS)),
    ("category tag, zh, inside the article card",
     EW_ARTICLE, _earnings_article(quote=CALL, tag=OURS_ZH)),
])
def test_our_copy_on_the_earnings_wire_still_fails(where, rel, page, allow):
    """The load-bearing half: same file, same card, our claim is still gated."""
    assert _fire(rel, page, allow), f"platform claim in {where} escaped the gate"


@pytest.mark.parametrize("sink,rel,page,attest", [
    ("article excerpt", EW_ARTICLE, _earnings_article(quote=CALL), _EARNINGS_ARTICLE_ATTEST),
    ("index card preview", EW_INDEX, _earnings_index(quote=CALL), _EARNINGS_INDEX_ATTEST),
    ("weekly notable-record card", EW_WEEKLY, _earnings_weekly(quote=CALL),
     _EARNINGS_WEEKLY_ATTEST),
])
def test_the_earnings_skip_is_what_greens_the_page(sink, rel, page, attest, allow):
    """Anti-vacuity, per render, on bytes that cannot rotate: the quote is masked
    (counted), and the identical page without that render's attestation fires. That
    is strictly stronger than counting the mask — it proves WHAT greened the page."""
    found, stats = scan_text(rel, page, allow)
    assert not found
    assert stats["third_party"] >= 1, (
        f"{sink}: expected the quote masked, got {stats['third_party']} — "
        "something other than the skip greened this page")

    bare = page.replace(attest, "Mastermind publishes research")
    assert not _third_party_specs(rel, bare), "the exemption survived losing its literal"
    fired, st = scan_text(rel, bare, allow)
    assert fired, f"{sink}: the skip is not what greens it — the unattested copy scans clean"
    assert st["third_party"] == 0


def test_the_earnings_templates_are_never_exempt(allow):
    """Same safety invariant as the research vault: every platform string on these
    pages is authored in templates/earnings_wire/, which the gate scans with NO skip."""
    assert _fire("templates/earnings_wire/earnings_wire_article.html.j2",
                 _earnings_article(quote=CALL, tag=OURS), allow)
    assert not _third_party_specs("templates/earnings_wire/earnings_wire_article.html.j2",
                                  _earnings_article())
    assert _fire("templates/earnings_wire/earnings_wire_index.html.j2",
                 _earnings_index(quote=CALL, tag=OURS), allow)
    assert _fire("templates/earnings_wire/earnings_weekly.html.j2",
                 _earnings_weekly(quote=CALL, tag=OURS), allow)


def test_the_earnings_shape_earns_nothing_on_another_page(allow):
    """The exemption is bound to the three render-target paths. The identical markup
    elsewhere — a sibling stocks page, a hand-dropped article — is scanned in full."""
    page = _earnings_article(quote=CALL)
    for rel in ("site/stocks/WAVE.html",
                "site/stocks/earnings/wave-2025q4.html",
                "site/earnings/wave-2025q4-call-record.html"):
        assert _fire(rel, page, allow), f"{rel} picked up the earnings-wire exemption"
        assert not _third_party_specs(rel, page)


def test_earnings_index_path_is_not_an_article(allow):
    """index.html / page-N.html are the directory, a different template: they must not
    pick up the article attestation even though they share the directory."""
    # Article attestation + article regions, but an index path — no match.
    forged = _earnings_article(quote=CALL)
    assert not _third_party_specs(EW_INDEX, forged)
    assert _fire(EW_INDEX, forged, allow)


def test_earnings_sink_literal_still_exists_in_the_templates():
    """The one region keys off markup all three templates emit. If the tag is renamed
    the gate silently stops exempting the quote and the next call reds main — catch
    it here, where the fix is one line, instead of on somebody else's PR."""
    for rel in ("templates/earnings_wire/_facts.html.j2",
                "templates/earnings_wire/earnings_weekly.html.j2",
                "templates/earnings_wire/earnings_wire_index.html.j2"):
        j2 = (ROOT / rel).read_text(encoding="utf-8")
        assert '<blockquote lang="en">' in j2, (
            f"{rel} no longer emits <blockquote lang=\"en\"> — "
            "the earnings-wire region in _THIRD_PARTY_PAGES no longer matches it")
