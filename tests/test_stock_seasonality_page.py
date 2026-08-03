"""Calendar Clock page guards — research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md.

The page's whole claim is that it tells the truth about a weak result, so these
pin the honesty surface (plain-word Tier 1, EN/ZH parity, no invented state) as
hard as they pin the render.
"""
from __future__ import annotations

import json
import math
import re
import sys
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import build_stock_seasonality_page as bss  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "seasonality" / "SPY.entity.json"
MU_FIXTURE = ROOT / "tests" / "fixtures" / "seasonality" / "MU.entity.json"
CJK = re.compile(r"[㐀-鿿＀-￯　-〿]")

# Spec §3 — banned from Tier 1 ON THIS PAGE, on top of the doctrine's Law-2 list.
# Every one has a sanctioned Tier-2 home, so the scan runs over ALWAYS-VISIBLE
# markup only (help tips and the embedded payload are stripped first).
BANNED = [
    "p-value", "maxT", "familywise", "FDR", "q≤", "t-stat", "bootstrap",
    "null distribution", "multiplicity", "in-sample", "OOS", "significance",
    "证伪", "falsifier", "refuted", "giveback", "dead-cat",
]
# Word-boundary forms: bare tokens that would false-positive as substrings.
BANNED_WORDS = [
    r"\bn=", r"\bBY\b", r"\bdetrend\b", r"\bdetrends\b", r"\bdetrending\b",
    r"\bfade[sd]?\b", r"\bbounce[sd]?\b",
]


@pytest.fixture(scope="module")
def entity() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def html() -> str:
    """Render the page the way the builder does — not the committed output, so a
    template edit that breaks the render fails here and not only in the lane."""
    return bss.render(ROOT)


def _strip_balanced(markup: str, opener: str) -> str:
    """Remove `opener` and everything up to its MATCHING </span>.

    A non-greedy regex stops at the first close tag, which leaves the deepest
    rows of a nested tip on screen — the exact way a copy guard passes while the
    banned words are still visible. Count the nesting instead.
    """
    while (i := markup.find(opener)) != -1:
        depth, j = 0, i
        while j < len(markup):
            if markup.startswith("<span", j):
                depth += 1
                j += 5
            elif markup.startswith("</span>", j):
                depth -= 1
                j += 7
                if depth == 0:
                    break
            else:
                j += 1
        markup = markup[:i] + " " + markup[j:]
    return markup


def visible(markup: str) -> str:
    """Always-visible markup: Tier-2 tips, scripts, the embedded payload, SVG
    <title> tooltips and [hidden] elements are all removed first."""
    out = re.sub(r"<script\b[^>]*>.*?</script>", " ", markup, flags=re.S | re.I)
    out = _strip_balanced(out, '<span class="sx-tip">')
    out = re.sub(r"<title>.*?</title>", " ", out, flags=re.S)
    out = re.sub(r"<[a-z]+\b[^>]*\shidden(\s|>)[^>]*>.*?</[a-z]+>", " ", out, flags=re.S | re.I)
    return out


# ── the render ──────────────────────────────────────────────────────────────
def test_page_builds_and_carries_its_furniture(html):
    assert html.lstrip().startswith("<!DOCTYPE html>")
    for probe in ('id="sxf"', 'id="sx-fan"', 'id="sx-verdict"', 'id="sx-chips"',
                  'id="sx-track"', 'id="sx-tbody"', 'sx-honesty',
                  'stock_seasonality.css', 'stock_seasonality.js'):
        assert probe in html, probe


def test_shared_nav_family_is_reused_not_forked(html):
    """CLAUDE.md §Navigation: exactly two header families. This page uses the
    authenticated one via _site_nav -> _navlinks; it must not hand-roll a third."""
    assert html.count('<nav class="site-nav">') == 1
    assert '<div class="nav-links">' in html
    assert "navigation-refresh.css" in html


def test_nav_entry_exists_once_in_find_the_edge():
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text()
    assert nav.count("stock_seasonality.html") == 1
    entry = nav[nav.index("stock_seasonality.html"):]
    assert "Stock Seasonality" in entry[:900] and "个股季节性" in entry[:900]
    assert "Which calendar windows actually repeat" in entry[:900]
    # It belongs to the Find the Edge section, beside the other edge-finding pages.
    section = nav[nav.index("Find the Edge"):nav.index("Capital & Regimes")]
    assert "stock_seasonality.html" in section


def test_existing_factor_seasonality_page_is_untouched():
    """A different page with a different job (Ken French factor climate)."""
    other = (ROOT / "templates" / "seasonality.html.j2").read_text()
    assert "stock_seasonality" not in other


# ── the signature: one strand per complete year, one fan thread per year ────
def test_one_strand_and_one_fan_thread_per_complete_year(html, entity):
    n = entity["coverage"]["n_years_complete"]
    assert n == len(entity["years"])
    assert html.count('class="sxf-strand"') == n
    assert html.count('class="f up"') + html.count('class="f dn"') == n
    # the end-dot column IS the sample — one circle per year, and no separate dot row
    assert html.count('class="e up"') + html.count('class="e dn"') == n
    assert "sx-dots" not in html and "sxf-lit" not in html


def test_year_field_has_no_in_gate_lighting_state(html):
    """Spec §13: rendered, in-gate lighting is illegible at the year's y-scale.
    The layer AND its dim/undim state machine are gone."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert "sxf-lit" not in css
    assert 'data-gate="on"' not in css and 'data-gate' not in html


def test_strand_downsample_cap(html):
    """<=183 points per strand (every second calendar day) — spec §4."""
    for d in re.findall(r'class="sxf-strand" d="([^"]+)"', html):
        assert d.count(",") <= bss.MAX_POINTS


# ── bilingual contract ──────────────────────────────────────────────────────
def test_en_zh_pair_parity(html):
    assert html.count('class="l-en"') == html.count('class="l-zh"')
    assert html.count('class="l-en"') > 60


def test_no_translated_text_in_attributes(html):
    """CI-guarded house law, restated at spec §0.6 for title= AND aria-label."""
    for attr in ("title", "aria-label", "alt"):
        for value in re.findall(rf'\b{attr}="([^"]*)"', html):
            assert not CJK.search(value), f"{attr}= carries translated text: {value!r}"


def test_svg_carries_no_translated_text(html):
    """Bilingual labels are HTML overlays; the SVG holds month initials only."""
    for block in re.findall(r"<svg\b.*?</svg>", html, flags=re.S):
        assert not CJK.search(block), "SVG carries translated text"


def test_zh_copy_is_not_english_dropped_into_chinese(html):
    """Every ZH span must actually be Chinese — a raw EN state name in the zh
    lane is the defect the doctrine's builder checklist §5 names."""
    bad = []
    for body in re.findall(r'<span class="l-zh">(.*?)</span>', html, flags=re.S):
        text = re.sub(r"<[^>]+>", "", body).strip()
        if not text or CJK.search(text):
            continue
        # figures, tickers and the month/weekday initials are legitimately latin
        if re.fullmatch(r"[-+0-9.,%<>→·|:()\s/A-Z]{0,24}", text):
            continue
        bad.append(text)
    assert not bad, f"zh spans with no Chinese: {bad[:5]}"


# ── doctrine: plain words on the glance tier ────────────────────────────────
def test_banned_tier1_vocabulary_absent_from_visible_markup(html):
    text = visible(html)
    for term in BANNED:
        assert term not in text, f"banned Tier-1 term visible: {term}"
    for pattern in BANNED_WORDS:
        assert not re.search(pattern, text), f"banned Tier-1 term visible: {pattern}"


def test_detrended_control_label_survives_the_bare_verb_ban(html):
    """The ban is on `detrend` as a bare verb; the control label is spec-sanctioned
    (§5), so the guard above must not have been satisfied by deleting the control."""
    assert "Detrended" in html and "去趋势" in html


def test_validated_is_absent(html):
    assert "validated" not in html.lower()


def test_no_score_no_rank_anywhere(html):
    """Spec §0.5 — no score, no rank, no cross-name ordering on this page.

    The honesty strip DOES say "we don't rank symbols against each other yet",
    so this checks the absence of ranking as a FEATURE, not of the word: no rank
    tokens, no score readout, and the years in chronological order only —
    sorting by return is the flattering-presentation trap (spec §5)."""
    # tags out and entities decoded first: a hex colour inside an SVG attribute is
    # not a rank badge, and a bare &#39; is not "#39"
    text = unescape(re.sub(r"<[^>]+>", " ", visible(html))).lower()
    assert not re.search(r"#\d+\b", text), "rank badge in copy"
    for term in ("score:", "rank #", "top 10", "ranked list", "vs peers"):
        assert term not in text, term
    assert "don’t rank symbols" in text or "don't rank symbols" in text
    years = [int(y) for y in re.findall(r'<td class="y">(\d{4})</td>', html)]
    assert years and years == sorted(years), "years table must stay chronological"


def test_falsifier_language_never_reaches_the_user(html):
    """Standing operator ruling: verdicts live on the Calibration Lab, never here."""
    for term in ("falsifier", "refuted", "证伪", "thesis refuted"):
        assert term not in html


# ── paired assets + serving boundary ───────────────────────────────────────
@pytest.mark.parametrize("name", ["stock_seasonality.css", "stock_seasonality.js"])
def test_template_and_site_asset_bytes_match(name):
    tpl = (ROOT / "templates" / name).read_bytes()
    site = (ROOT / "site" / name).read_bytes()
    assert tpl == site, f"{name} diverged — run python -m scripts.check_template_site_sync --fix"


def test_page_and_assets_are_declared_public():
    """Default-DENY serving: an un-allowlisted page ships dark (302/401)."""
    import yaml
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    for path in ("/stock_seasonality.html", "/stock_seasonality.css", "/stock_seasonality.js"):
        assert path in policy["public"]["exact"], path
        assert (ROOT / "site" / path.lstrip("/")).is_file(), path
    for matcher in ("reg_asset", "reg_asset_err", "reg_html", "gate_html",
                    "reg_html_err", "gate_html_err"):
        body = re.search(rf"@{matcher}\s*\{{(.*?)^\s*\}}", caddy, flags=re.S | re.M).group(1)
        assert "/stock_seasonality.html" in body, matcher


def test_builder_is_registered_in_every_render_lane():
    dag = (ROOT / "config" / "dag.yml").read_text()
    assert dag.count("scripts.build_stock_seasonality_page") == dag.count("- scripts.build_seasonality\n")
    for wf in ("render.yml", "engine-render.yml", "daily.yml"):
        text = (ROOT / ".github" / "workflows" / wf).read_text()
        assert "scripts.build_stock_seasonality_page" in text, wf
        # A slug absent from ORDER never has its log replayed and never raises its
        # rc!=0 ::error — the 2026-07-25 transmission_chains silent-failure defect.
        order = re.search(r'ORDER="([^"]*)"', text).group(1).split()
        assert "stock_seasonality_page" in order, f"{wf}: slug missing from ORDER"
        # and it must not collide with the artifact producer's own brun slug
        assert text.count("brun stock_seasonality_page ") == 1, wf


# ── the statistics the client is allowed to reproduce (spec §9) ────────────
def test_window_convention_is_doy_minus_one(entity):
    """The off-by-one is silent and plausible-looking: on SPY's registered window
    the WRONG convention returns |t| 5.60 against a shipped 7.25 — both look like
    real numbers, and nothing else in the page would have flagged it."""
    cums = [y["cum"] for y in entity["years"]]
    a, b = entity["default_window"]["start_doy"], entity["default_window"]["end_doy"]
    right = bss.window_stats(cums, a, b)["abs_t"]
    wrong_r = [(row[b] - row[a]) * 1e-5 for row in cums]
    n = len(wrong_r)
    m = sum(wrong_r) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in wrong_r) / (n - 1))
    wrong = abs(m) / (sd / math.sqrt(n))
    assert right == pytest.approx(entity["default_window"]["abs_t"], rel=1e-3)
    assert abs(wrong - right) > 1.0, "the two conventions must be distinguishable"


def test_window_stats_match_a_hand_computation(entity):
    cums = [y["cum"] for y in entity["years"]]
    a, b = entity["default_window"]["start_doy"], entity["default_window"]["end_doy"]
    st = bss.window_stats(cums, a, b)
    r = [(row[b - 1] - row[a - 1]) * 1e-5 for row in cums]
    n = len(r)
    mean = sum(r) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in r) / (n - 1))
    assert st["n"] == n
    assert st["mean"] == pytest.approx(mean)
    assert st["abs_t"] == pytest.approx(abs(mean) / (sd / math.sqrt(n)))


def test_shipped_abs_t_is_reproducible_from_the_shipped_arrays(entity):
    """The contract's core promise: every number on the page is either shipped or
    derivable from years[].cum by the one formula. If this drifts, the page is
    showing the user a statistic they cannot check."""
    dw = entity["default_window"]
    st = bss.window_stats([y["cum"] for y in entity["years"]], dw["start_doy"], dw["end_doy"])
    assert st["abs_t"] == pytest.approx(dw["abs_t"], rel=1e-3)


def test_four_state_chip_logic():
    n95 = {"max_abs_t_quantiles": {"0.95": 3.0}}
    assert bss.derive_state(25, 4.0, n95, 4.0, n95, True) == "own"
    assert bss.derive_state(25, 4.0, n95, 1.0, n95, True) == "market"
    assert bss.derive_state(25, 4.0, n95, None, None, False) == "market"  # benchmark
    # a residual panel EXISTS but carries no null for this year count: "we cannot
    # say", never "the market's" — that would be a claim the data does not support
    assert bss.derive_state(25, 4.0, n95, 4.0, None, True) == "nonull"
    assert bss.derive_state(25, 1.0, n95, 9.0, n95, True) == "fails"
    assert bss.derive_state(5, 9.0, n95, 9.0, n95, True) == "thin"
    assert bss.derive_state(25, 9.0, None, None, None, False) == "nonull"


def test_fails_is_never_painted_as_bearish(html, entity):
    """Spec §3: a failed test is not a bearish signal — painting chip 4 --down
    would be a lie. Assert the class map, not just today's state."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    tpl = (ROOT / "templates" / "stock_seasonality.html.j2").read_text()
    assert "'fails':'sx-chip-muted'" in tpl
    assert "sx-chip-down" not in css and "sx-chip-down" not in tpl


def test_exceedance_reads_the_producers_101_rung_ladder(entity):
    """The ladder is the producer's empirical CDF; the 3-quantile grid is the §9
    floor. Prefer the ladder, and never interpolate a rung into existence."""
    nul = entity["family"]["null"]
    grid = bss._grid(nul)
    assert len(grid) == 101
    assert [t for _, t in grid] == nul["max_abs_t_quantile_ladder"]
    shipped = entity["default_window"]["null_max_exceedance_pct"]
    got = bss.exceedance(entity["default_window"]["abs_t"], nul)
    assert abs(got["pct"] - shipped) <= 1, (got, shipped)
    # with no ladder it falls back to the three §9 quantiles
    assert len(bss._grid({"max_abs_t_quantiles": {"0.90": 1, "0.95": 2, "0.99": 3}})) == 3


def test_exceedance_never_prints_zero_percent():
    """With B=2,000 the honest floor is 'under 1%'."""
    grid = {"max_abs_t_quantiles": {"0.10": 1.0, "0.50": 2.0, "0.90": 3.0,
                                    "0.95": 3.5, "0.99": 4.0}}
    assert bss.exceedance(9.9, grid) == {"form": "lt", "pct": 1, "cdf": 0.99}
    assert bss.exceedance(0.1, grid)["form"] == "gt"          # below the grid: a bound
    mid = bss.exceedance(2.5, grid)
    assert mid["form"] == "exact" and 1 <= mid["pct"] <= 99
    assert bss.from_pct(0.3)["form"] == "lt"
    assert bss.from_pct(1.65) == {"form": "exact", "pct": 2, "cdf": pytest.approx(0.9835)}


def test_client_is_never_handed_a_null_it_did_not_ship(entity):
    """exceedance() interpolates the SHIPPED quantile grid and nothing else."""
    assert bss.exceedance(3.0, None) == {"form": "none"}
    assert bss.exceedance(3.0, {"max_abs_t_quantiles": {}}) == {"form": "none"}
    assert bss.chance_track(3.0, {"max_abs_t_quantiles": {"0.95": 3.0}}) is None
    assert bss.exceedance(3.0, {"max_abs_t_quantile_ladder": []}) == {"form": "none"}


def test_lookback_without_a_matching_null_gets_no_verdict(entity):
    """family.null.n_years is the producer's statement of what the null was run
    on. A 10-year |t| against a 25-year null is exactly the quiet dishonesty this
    page exists to avoid: a shorter lookback gets its OWN null from
    family.null_by_lookback, and a lookback with neither gets no verdict."""
    fam = entity["family"]
    assert bss.null_for(fam, 25, entity["coverage"]) is fam["null"]
    assert bss.null_for(fam, 10, entity["coverage"]) is fam["null_by_lookback"]["10"]
    assert bss.null_for(fam, 10, entity["coverage"])["n_years"] == 10
    assert bss.null_for(fam, 20, entity["coverage"]) is None
    faked = {"null": dict(fam["null"]), "null_by_lookback": {"10": {"B": 1}}}
    assert bss.null_for(faked, 10, entity["coverage"]) == {"B": 1}


def test_missing_null_degrades_to_the_pinned_copy(entity):
    stripped = json.loads(json.dumps(entity))
    stripped["family"].pop("null", None)
    stripped["family"].pop("null_by_lookback", None)
    stripped["default_window"].pop("state", None)
    view = bss.build_view(stripped, None, True)
    assert view["state"] == "nonull"
    assert view["track"] is None


def test_thin_history_says_so(entity):
    thin = json.loads(json.dumps(entity))
    thin["years"] = thin["years"][-4:]
    thin["coverage"]["n_years_complete"] = 4
    thin["default_window"].pop("state", None)
    assert bss.build_view(thin, None, True)["state"] == "thin"


# ── the artifact contract ──────────────────────────────────────────────────
def test_fixture_is_the_producers_real_artifact(entity):
    """SPY.entity.json is vendored verbatim from the producer lane, so these
    assertions are about the SHIPPED contract, not a re-implementation of it."""
    cal = entity["calendar"]
    assert cal["cum_encoding"] == "int_1e-5_log_return"
    assert cal["cum_scale"] == 1e-05
    assert "cum index = doy - 1" in cal["window_convention"]
    assert entity["family"]["null"]["n_years"] == entity["coverage"]["n_years_complete"]
    assert len(entity["family"]["null"]["max_abs_t_quantile_ladder"]) == 101
    assert entity["default_window"]["neutral_basis"] == "self_benchmark"
    assert entity["neutral"] == {}


def test_fixture_conforms_to_the_entity_contract(entity):
    assert entity["schema"] == "biopharma_seasonality.entity.v1"
    for key in ("symbol", "name", "asof", "price_source", "coverage", "calendar",
                "years", "aggregate", "views", "family", "default_window", "neutral"):
        assert key in entity, key
    assert entity["calendar"]["n_slots"] == bss.SLOTS
    assert len(entity["calendar"]["labels"]) == bss.SLOTS
    for y in entity["years"]:
        assert len(y["cum"]) == bss.SLOTS, "365 values, index = doy - 1"
        assert y["cum"][0] == 0
        assert all(isinstance(v, int) for v in y["cum"]), "cum is 1e-5 integer units"
    assert entity["default_window"]["source"] == "symbol_best"
    for key in ("abs_t", "null_max_exceedance_pct", "state", "raw_clears",
                "neutral_clears", "stability", "neutral_basis"):
        assert key in entity["default_window"], key
    assert entity["default_window"]["state"] in ("own", "market", "fails", "thin")


def test_window_grid_never_wraps_the_year(entity):
    fam = entity["family"]
    assert fam["n_candidates"] == sum(bss.SLOTS - h for h in fam["horizons_days"])
    dw = entity["default_window"]
    assert 1 <= dw["start_doy"] < dw["end_doy"] <= bss.SLOTS


def test_both_fixtures_between_them_exercise_the_chip(entity):
    """SPY is the benchmark, so its residual is empty by construction -> `market`.
    MU carries calendar structure of its own after the market leg -> `own`."""
    mu = json.loads(MU_FIXTURE.read_text())
    assert entity["default_window"]["state"] == "market"
    assert entity["neutral"] == {}
    assert mu["default_window"]["state"] == "own"
    assert mu["neutral"]["market"]["years"]
    assert mu["neutral"]["market"]["family"]["null"]["max_abs_t_quantiles"]["0.95"]


def test_stability_sentence_is_rendered_only_when_shipped(html, entity):
    assert 'id="sx-stab"' in html
    survives = entity["default_window"]["stability"]["survives"]
    # §17: "a recurring date, not a season" was nonsense for a 60-day window; the
    # clause is horizon-agnostic now.
    assert "recurring date, not a season" not in html
    assert ("the effect depends on these exact dates" in html) is not survives
    without = json.loads(json.dumps(entity))
    without["default_window"].pop("stability")
    assert bss.build_view(without, None, True)["stability"] is None


# ── honesty strip ──────────────────────────────────────────────────────────
def test_honesty_strip_states_every_required_disclosure(html):
    text = visible(html)
    assert "One complete year is one piece of evidence" in text
    assert "Split- and dividend-adjusted closing prices" in text
    assert "don’t rank symbols against each other yet" in text or \
           "don't rank symbols against each other yet" in text
    assert "marked exploratory" in text
    assert "about 1 in 20" in text            # across-symbol multiplicity, plain words
    assert "seasonalitydata/methodology.json" in html


def test_exploratory_badge_exists_and_starts_hidden(html):
    assert 'id="sx-expl"' in html
    badge = html[html.index('id="sx-expl"'):]
    assert badge[:40].strip().startswith('id="sx-expl" hidden') or " hidden" in badge[:60]
    assert "Your window · exploratory" in html and "自选窗口 · 探索性" in html


def test_client_fetches_entities_through_data_base():
    """Heavy per-symbol panels are R2-served; only index.json is same-origin."""
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    assert 'window.DATA_BASE || ""' in js
    assert 'seasonalitydata/entities/' in js
    # DATA_BASE is an ORIGIN with no trailing slash, so a bare concatenation builds
    # "https://pub-….r2.devseasonalitydata/…" and every symbol switch dies on a
    # malformed host. Observed in the browser before this guard existed; site/odds.js
    # is the house precedent this program adopts (spec §14).
    join = js[js.index("function entityUrl"):]
    join = join[:join.index("}")]
    assert 'slice(-1) !== "/"' in join, "DATA_BASE join must normalize the trailing slash"
    assert 'fetch("seasonalitydata/index.json"' in js
    # a failed switch keeps the loaded symbol on screen and says what happened
    assert 'note("sx-err", true)' in js


def test_reduced_motion_parks_every_animated_element():
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    block = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    assert "animation: none !important" in block and "transition: none !important" in block
    for cls in ("sxf-strand", "sxf-band", "sxf-median", "sxf-gate", "sxf-handle", "sx-chip"):
        assert cls in block, cls


def test_gate_handles_are_keyboard_operable(html):
    for hid, label in (("sxf-h1", "Window start"), ("sxf-h2", "Window end")):
        block = html[html.index(f'id="{hid}"'):][:400]
        assert 'role="slider"' in block and 'tabindex="0"' in block
        assert f'aria-label="{label}"' in block
        assert "aria-valuenow=" in block and "aria-valuetext=" in block
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert ".sxf-handle:focus-visible .grip { outline: 2px solid var(--sx-ink)" in css


def test_mobile_touch_targets_are_resized_in_user_units(html):
    """preserveAspectRatio="none" squashes the desktop 30x40 hit rect to about
    10x28 CSS px at 375px, so the mobile block must restate it in viewBox units.
    Measured in the browser at 375px: 46.1 x 50.3 CSS px, non-overlapping."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    block = css[css.index("@media (max-width: 720px)"):]
    block = block[:block.index("@media (max-width: 420px)")]
    assert ".sxf-handle .hit { y: 294px; height: 72px; }" in block
    h1 = re.search(r"#sxf-h1 \.hit \{ x: (-?\d+)px; width: (\d+)px; \}", block)
    h2 = re.search(r"#sxf-h2 \.hit \{ x: (-?\d+)px; width: (\d+)px; \}", block)
    assert h1 and h2
    # asymmetric and non-overlapping at the 5-day minimum window (~12.2 user units)
    h1_right = int(h1.group(1)) + int(h1.group(2))
    assert h1_right - int(h2.group(1)) < 12, "hit rects overlap at the minimum window"
    assert "touch-action: none" in css and "touch-action: pan-y" in css


def test_symbol_picker_is_a_real_combobox(html):
    block = html[html.index('id="sx-search"'):][:400]
    assert 'role="combobox"' in block and 'aria-expanded="false"' in block
    assert 'aria-controls="sx-results"' in block
    assert 'role="listbox"' in html
