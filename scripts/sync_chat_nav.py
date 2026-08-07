#!/usr/bin/env python3
"""Static guard: templates/chat.html's header must equal the canonical partial.

WHY THIS EXISTS (follow-up to #4228, measured 2026-08-01):

templates/chat.html is a PLAIN-COPY page — scripts/check_template_site_sync.py
requires it to byte-match site/chat.html, so a Jinja ``{% include %}`` cannot run
there and #4228's sweep (113 of 114 product templates → ``_site_nav.html.j2``)
had to skip it. Its header was therefore still the hand-copied block someone
pasted in when the page was built, frozen at that date. By 2026-08-01 it had
drifted badly enough to be a navigation bug, not a cosmetic one:

  * 12 current pages were MISSING from the menu entirely (confluence_screener,
    euro_area, fundamental_forensics, government_revenue, india, japan,
    neural_web, research_vault, sector_cycles_china, south_korea, stage_analysis,
    united_kingdom);
  * 17 REMOVED pages were still advertised (anticipation, btc_strategy,
    committee, congress_trades, crossasset, demand, factors, impulse, ipo,
    macro_signals, measurement, signal_lab, tech_lab, transmission, vector,
    vector_allocation, whitehouse) — dead links in a shipped menu;
  * it linked a bespoke ``chat_nav.css`` instead of ``navigation-refresh.css``,
    the stylesheet CLAUDE.md's Navigation source-of-truth law puts in charge of
    nav appearance, because its markup was the SUPERSEDED mega structure
    (.nav-mega-grid/.nav-mega-col) that the current partial no longer emits.

Hand-copying is what produced all three. So the block is no longer hand-copied:
this script RENDERS ``_site_nav.html.j2`` and splices the result into the page,
and CI runs the same render and refuses a page that disagrees with it. A future
edit to the partial that forgets chat.html now fails a check instead of shipping
a menu that silently lies about which pages exist.

BOUNDARY — the splice is keyed on the structural ``<nav class="site-nav"> …
</nav>`` element, NOT on sentinel comments. A comment marker is deletable, and a
guard whose marker went missing reads as green forever (tests/
test_renamed_sentinel* documents that shape). A missing/duplicated wrapper is a
hard error here, never a skip.

STAMPS — ``scripts/optimize_assets.py`` decorates the shipped bytes after this
runs: ``?v=<8hex>`` on local assets and ``defer`` on scripts. Those are the
optimizer's to own and they change whenever an asset's content changes, so the
comparison normalizes exactly those two decorations and nothing else. Anything
else that differs is real drift and fails.

...and ``--fix`` CARRIES THEM ACROSS (#4774, measured 2026-08-06). Normalizing a
decoration away for the comparison does not make it disposable on the write path:
``--fix`` used to splice in the RAW ``render_canonical()`` block, which wears
neither, so healing a one-link nav drift ALSO stripped 5 ``?v=`` stamps and 4
``defer`` attributes from the header of both copies of the pair — including
``live.js`` and ``live_config.js``, which ``app/deploy/Caddyfile``'s
``@public_versioned`` matcher only serves ``immutable, max-age=1y`` WHILE the ref
carries a ``?v=`` (dropping them to a 300s revalidate-per-navigation, the exact
cost ui.asset_stamp exists to remove), and demoting four ``defer`` scripts to
render-blocking on first paint. Both copies were rewritten identically, so
``check_template_site_sync`` saw no divergence and nothing else caught it; #4774
noticed only because it read the diff, and hand-applied the edit instead.

So the splice now re-runs ``lib.pages.optimize_assets_text`` over the new block
with the OLD block's per-asset stamps as its hash source — the decorations land
in the optimizer's own shape, keyed by the asset each one names, and a link the
partial added or removed still lands. It is fail-closed: a decoration that the
new block's own assets should have kept but did not is a hard refusal to write,
not a silent loss. The sibling guard refuses ``--fix`` outright in its analogous
case, but there the fix DIRECTION is wrong (site/ is the fresher side and cannot
be regenerated); here the direction is right and only the decorations are
collateral, and refusing would make this script's own printed remedy a dead end —
returning chat.html's header to the hand-editing it exists to abolish.

Usage:
    python -m scripts.sync_chat_nav              # report + exit 1 on drift
    python -m scripts.sync_chat_nav --fix        # re-splice from the partial
    python -m scripts.sync_chat_nav --selftest   # gate fires on synthetic drift
Exit codes: 0 = in sync / fixed / selftest passed · 1 = drift found / selftest
failed / the page's <nav class="site-nav"> boundary could not be located.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CANONICAL = "_site_nav.html.j2"
PAGE = "chat.html"

# The one <nav class="site-nav"> element on the page, non-greedy to its </nav>.
_NAV_RE = re.compile(r'<nav class="site-nav">.*?</nav>', re.DOTALL)

# Exactly what scripts/optimize_assets.py adds, and nothing else:
#   lib.pages.optimize_assets_text -> ?v=<8 hex> on local .js/.css refs
#   lib.pages.optimize_assets_text -> defer on non-async, non-module scripts
_STAMP_RE = re.compile(r"\?v=[0-9a-f]{8}")
_DEFER_RE = re.compile(r"(<script\b[^>]*?)\s+defer(\s*/?>)", re.IGNORECASE)

# The same two decorations, read back keyed by the ASSET each one names, so a
# re-splice can carry them onto the new block instead of dropping them.
_STAMPED_REF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"?#]+)\?v=([0-9a-f]{8})"', re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
_ASSET_REF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"', re.IGNORECASE)
_DEFER_ATTR_RE = re.compile(r"\bdefer\b", re.IGNORECASE)


def render_canonical(templates: Path) -> str:
    """The canonical header, rendered exactly as the site builders render it.

    Matches scripts/build_site.py: ``autoescape=True`` (which is why the search
    placeholder ships ``&amp;``), and a bilingual ``t()`` that emits the same
    ``.l-en``/``.l-zh`` span pair ``_navlinks.html.j2``'s own macro does — the
    partial's wrapper reads ``t`` from the page context, so supplying the
    English-only stub used by unit tests here would ship a page with no Chinese.
    """
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup, escape

    def t(en: str, zh: str = "") -> Markup:
        return Markup(
            f'<span class="l-en">{escape(en)}</span>'
            f'<span class="l-zh">{escape(zh or en)}</span>'
        )

    env = Environment(loader=FileSystemLoader(str(templates)), autoescape=True)
    return env.get_template(CANONICAL).render(t=t).strip()


def normalize(block: str) -> str:
    """`block` with the optimizer's stamps/defer removed, for comparison only."""
    block = _STAMP_RE.sub("", block)
    block = _DEFER_RE.sub(r"\1\2", block)
    return block.strip()


def asset_refs(block: str) -> set[str]:
    """Every href/src in `block`, stripped of any query/fragment."""
    return {ref.split("?", 1)[0].split("#", 1)[0] for ref in _ASSET_REF_RE.findall(block)}


def decorations(block: str) -> tuple[dict[str, str], set[str]]:
    """The optimizer's decorations on `block`, keyed by the asset each one names.

    Returns ``({asset: 8-hex stamp}, {asset of every deferred <script>})``. Keyed
    by asset and not by line so the carry survives the very edits this script
    exists to make — the partial reordering its header, or a menu link landing
    above the script block, must not cost live.js its stamp.
    """
    stamps = {url: h for url, h in _STAMPED_REF_RE.findall(block)}
    deferred = set()
    for attrs in _SCRIPT_TAG_RE.findall(block):
        ref = _ASSET_REF_RE.search(attrs)
        if ref and _DEFER_ATTR_RE.search(attrs):
            deferred.add(ref.group(1).split("?", 1)[0].split("#", 1)[0])
    return stamps, deferred


def redecorate(canonical: str, current: str) -> str:
    """`canonical` wearing the decorations the optimizer had put on `current`.

    Runs the optimizer's own rewrite (``lib.pages.optimize_assets_text``) rather
    than patching attributes here, so the result is shaped exactly like the bytes
    a render would emit — same stamp placement, same ``defer`` rule (and so the
    same exemptions for ``async``/``type=module``/``data-sync``/the data-base
    shim, none of which this script may quietly override).

    The hash source is the CURRENT block: this is a markup re-splice, not a
    re-hash, and the assets themselves did not change. An asset the partial has
    newly added has no prior stamp and gets none — it ships bare until the next
    optimizer pass, which the caller reports rather than hides.
    """
    from lib.pages import optimize_assets_text

    stamps, _ = decorations(current)
    return optimize_assets_text(canonical, stamps.get)


def lost_decorations(current: str, spliced: str) -> list[str]:
    """Decorations `spliced` DROPPED for an asset it still references.

    An asset the partial removed takes its stamp with it and is not a loss; the
    fail-closed condition is a ref that survived the splice and came out barer
    than it went in.
    """
    before_stamps, before_defer = decorations(current)
    after_stamps, after_defer = decorations(spliced)
    survivors = asset_refs(spliced)
    lost = [
        f'{url}: lost ?v={h} (now {"?v=" + after_stamps[url] if url in after_stamps else "bare"})'
        for url, h in sorted(before_stamps.items())
        if url in survivors and after_stamps.get(url) != h
    ]
    lost += [
        f"{url}: lost defer (script is render-blocking again)"
        for url in sorted(before_defer)
        if url in survivors and url not in after_defer
    ]
    return lost


def extract_nav(text: str, label: str) -> str:
    """The page's single header element, or SystemExit with a real diagnosis."""
    found = _NAV_RE.findall(text)
    if len(found) != 1:
        print(
            f"::error title=chat-nav-sync boundary lost::{label} has {len(found)} "
            f'<nav class="site-nav">…</nav> elements, expected exactly 1. This '
            f"guard splices on that element; it cannot run against a page whose "
            f"header wrapper was renamed, removed or duplicated. Restore the "
            f"wrapper (or update {Path(__file__).name} deliberately) — do not "
            f"leave this unresolved, it is the page's whole navigation."
        )
        raise SystemExit(1)
    return found[0]


def check(root: Path, fix: bool = False) -> bool:
    """True when the page's header matches the partial (after fixing, if asked)."""
    templates, site = root / "templates", root / "site"
    tpl_path, site_path = templates / PAGE, site / PAGE
    canonical = render_canonical(templates)
    page_text = tpl_path.read_text(encoding="utf-8")
    current = extract_nav(page_text, f"templates/{PAGE}")

    if normalize(current) == normalize(canonical):
        print(f"chat nav sync OK (templates/{PAGE} header == {CANONICAL})")
        return True

    if not fix:
        print(
            f"::error title=chat-nav-sync drift::templates/{PAGE}'s header no "
            f"longer matches {CANONICAL}. The header is GENERATED — do not hand-"
            f"edit it; edit {CANONICAL} / _navlinks.html.j2 and re-run: "
            f"python -m scripts.sync_chat_nav --fix"
        )
        return False

    # Splice, preserving everything outside the wrapper byte-for-byte — and
    # everything the optimizer had already put INSIDE it (see the STAMPS note).
    spliced = redecorate(canonical, current)

    lost = lost_decorations(current, spliced)
    if lost:
        print(
            f"::error title=chat-nav-sync decorations lost::re-splicing "
            f"templates/{PAGE}'s header would drop optimizer decorations that its "
            f"own assets still need: {'; '.join(lost)}. Refusing to write — a "
            f"stripped ?v= drops the asset out of the Caddyfile's "
            f"`immutable, max-age=1y` tier and a stripped defer puts the script "
            f"back on the first-paint path. Apply the header edit by hand, "
            f"preserving these, or fix redecorate()."
        )
        raise SystemExit(1)

    # The write must stay a fixed point for the CHECK above: re-decorating may add
    # ONLY stamps and defer, the two things normalize() forgives. Anything else it
    # introduced would make --fix write a page the very next run calls drifted.
    if normalize(spliced) != normalize(canonical):
        print(
            f"::error title=chat-nav-sync redecoration changed the markup::"
            f"re-applying the optimizer's decorations to {PAGE}'s new header "
            f"changed it by more than ?v= stamps and defer, so --fix would write "
            f"a page that immediately reports drift. Refusing to write."
        )
        raise SystemExit(1)

    bare = sorted(
        url for url in asset_refs(spliced) - set(decorations(spliced)[0])
        if url.lower().endswith((".js", ".css")) and not url.startswith(
            ("http://", "https://", "//", "data:"))
    )
    if bare:
        print(
            f"::warning title=chat-nav-sync unstamped asset::{PAGE}'s header "
            f"references {len(bare)} local asset(s) the old header did not, so "
            f"they have no stamp to carry and ship bare until the next optimizer "
            f"pass: {bare}. Run `python -m scripts.optimize_assets` (or let the "
            f"next render) before relying on their cache headers.",
            flush=True,
        )

    updated = page_text.replace(current, spliced, 1)

    # These writes are raw write_text, not lib.pages.write_page, and are listed in
    # tests/test_site_shim._ALLOW for it. That is deliberate and it is the same
    # call scripts/optimize_assets.py makes on this exact pair: write_page INJECTS
    # the data-base shim, which would (a) write generated markup into a SOURCE file
    # and (b) make templates/chat.html differ from site/chat.html, breaking the
    # byte-match law that makes this a plain-copy page at all.
    #
    # An allowlist entry is a hole unless something still checks the thing it
    # excuses, so check it here: the splice replaces only the <nav> element, so the
    # shim (which lives in <head>) must survive untouched. If it ever does not,
    # this refuses to write rather than shipping a page whose per-ticker fetches
    # silently miss the R2 reroute.
    from lib.pages import DBASE_MARKER

    if page_text.count(DBASE_MARKER) != updated.count(DBASE_MARKER):
        print(
            f"::error title=chat-nav-sync shim lost::splicing the header changed the "
            f"number of {DBASE_MARKER!r} shim tags in {PAGE} "
            f"({page_text.count(DBASE_MARKER)} -> {updated.count(DBASE_MARKER)}). "
            f"Refusing to write. The header splice must not touch <head>."
        )
        raise SystemExit(1)

    tpl_path.write_text(updated, encoding="utf-8")
    print(f"FIXED: templates/{PAGE} header re-rendered from {CANONICAL}")
    # Mirror to the site copy so the pair stays byte-identical (the sync law).
    # check_template_site_sync --fix would also do it; doing it here keeps this
    # script a fixed point on its own.
    if site_path.is_file():
        site_path.write_text(updated, encoding="utf-8")
        print(f"FIXED: site/{PAGE} mirrored from templates/{PAGE}")
    return True


def selftest() -> int:
    """Guard the guard: a hand-edited header must go red, and --fix must heal it."""
    import hashlib
    import shutil
    import tempfile

    root = Path(__file__).resolve().parent.parent
    tmp = Path(tempfile.mkdtemp(prefix="sync_chat_nav_selftest_"))
    try:
        shutil.copytree(root / "templates", tmp / "templates")
        (tmp / "site").mkdir()
        shutil.copy2(root / "site" / PAGE, tmp / "site" / PAGE)

        if not check(tmp, fix=True):
            print("selftest FAIL: --fix could not bring the fixture into sync")
            return 1
        if not check(tmp):
            print("selftest FAIL: a freshly fixed page still reports drift "
                  "(the check is not a fixed point)")
            return 1

        # The exact 2026-08-01 shape: a link the partial does not carry.
        page = tmp / "templates" / PAGE
        text = page.read_text(encoding="utf-8")
        page.write_text(
            text.replace('<div class="nav-links">',
                         '<div class="nav-links">\n    <a href="whitehouse.html">X</a>', 1),
            encoding="utf-8",
        )
        if check(tmp):
            print("selftest FAIL: a hand-added menu link did NOT trip the gate")
            return 1

        # Stamps/defer are the optimizer's, not drift — normalizing them must not
        # blind the gate to the line above, which is why this is asserted after it.
        if not check(tmp, fix=True):
            print("selftest FAIL: --fix could not heal the drifted page")
            return 1
        healed = page.read_text(encoding="utf-8")
        if "whitehouse.html" in extract_nav(healed, "fixture"):
            print("selftest FAIL: --fix left the hand-added link in the header")
            return 1
        if (tmp / "site" / PAGE).read_text(encoding="utf-8") != healed:
            print("selftest FAIL: --fix did not mirror the site copy")
            return 1

        # Set the stamp rather than prepending one: --fix now carries stamps across,
        # so a bare `.replace()` here would build `…css?v=deadbeef?v=<carried>` and
        # pass on a malformed URL that normalize() happens to erase twice.
        page.write_text(
            re.sub(r"navigation-refresh\.css(\?v=[0-9a-f]{8})?",
                   "navigation-refresh.css?v=deadbeef", healed, count=1),
            encoding="utf-8",
        )
        if not check(tmp):
            print("selftest FAIL: an optimizer ?v= stamp was reported as drift")
            return 1

        # --- --fix must CARRY those decorations, not just tolerate them ------
        # #4774. The assertion above is about the COMPARATOR, and it is exactly
        # what made the write path look safe: --fix spliced in the raw canonical
        # block, which wears no decorations at all, so healing a one-link drift
        # took 5 ?v= stamps and 4 defers off BOTH copies of the pair — silently,
        # because it rewrote them identically and left nothing to diverge.
        # Decorate the fixture with the optimizer itself (deterministic per-asset
        # hashes, so this can never end up asserting over an empty set), re-drift
        # it, and require every decoration back on the far side.
        from lib.pages import optimize_assets_text

        decorated = optimize_assets_text(
            page.read_text(encoding="utf-8"),
            lambda url: hashlib.sha256(url.encode()).hexdigest()[:8],
        )
        page.write_text(decorated, encoding="utf-8")
        want_stamps, want_defer = decorations(extract_nav(decorated, "fixture"))
        if not want_stamps or not want_defer:
            print(f"selftest FAIL: the fixture header carries {len(want_stamps)} stamp(s) "
                  f"and {len(want_defer)} defer(s) — this assertion would be vacuous")
            return 1

        page.write_text(
            decorated.replace('<div class="nav-links">',
                              '<div class="nav-links">\n    <a href="whitehouse.html">X</a>', 1),
            encoding="utf-8",
        )
        if not check(tmp, fix=True):
            print("selftest FAIL: --fix could not heal the decorated page")
            return 1
        healed = page.read_text(encoding="utf-8")
        nav = extract_nav(healed, "fixture")
        got_stamps, got_defer = decorations(nav)
        if "whitehouse.html" in nav:
            print("selftest FAIL: --fix left the hand-added link in the decorated header")
            return 1
        dropped = [f"{u}?v={h} -> {got_stamps.get(u, 'bare')}"
                   for u, h in sorted(want_stamps.items()) if got_stamps.get(u) != h]
        if dropped:
            print(f"selftest FAIL: --fix did not carry the optimizer's ?v= stamps across "
                  f"the re-splice: {dropped}. Those assets fall out of the Caddyfile's "
                  f"`immutable, max-age=1y` tier the moment the stamp goes (#4774).")
            return 1
        undeferred = sorted(want_defer - got_defer)
        if undeferred:
            print(f"selftest FAIL: --fix stripped defer from {undeferred} — those scripts "
                  f"go back onto the first-paint path (#4774)")
            return 1
        if (tmp / "site" / PAGE).read_text(encoding="utf-8") != healed:
            print("selftest FAIL: --fix did not mirror the decorated site copy")
            return 1
        if not check(tmp):
            print("selftest FAIL: the re-decorated page reports drift — --fix is not a "
                  "fixed point once it carries decorations")
            return 1

        print(f"selftest PASS: drift detected, --fix heals both copies, the optimizer's "
              f"stamps are not mistaken for drift, and --fix carries all "
              f"{len(want_stamps)} stamp(s) + {len(want_defer)} defer(s) across the splice")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    root = Path(__file__).resolve().parent.parent
    return 0 if check(root, fix="--fix" in argv) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
