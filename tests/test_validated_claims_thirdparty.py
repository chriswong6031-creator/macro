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
    _THIRD_PARTY_PAGES,
    TOKEN,
    _load_allowlist,
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
    hub, and the vault app page."""
    return [p for p in (*sorted(ROOT.glob("site/research/*.html")),
                        ROOT / "site/research_vault.html") if p.is_file()]


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
