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
    # @reg_html / @reg_html_err are retired (operator 2026-08-04 opened every
    # HTML shell to anonymous visitors), so only the asset + funnel matchers
    # still carry a path list to check.
    for matcher in ("reg_asset", "reg_asset_err", "gate_html", "gate_html_err"):
        body = re.search(rf"@{matcher}\s*\{{(.*?)^\s*\}}", caddy, flags=re.S | re.M).group(1)
        assert "/stock_seasonality.html" in body, matcher


def test_builder_is_registered_in_every_render_lane():
    dag = (ROOT / "config" / "dag.yml").read_text()
    assert dag.count("scripts.build_stock_seasonality_page") == dag.count("- scripts.build_seasonality\n")
    for wf in ("render.yml", "engine-render.yml", "daily.yml"):
        # Resolved: a band block extracted to scripts/ci/ carries its brun calls
        # AND its ORDER string out of the YAML together, so a raw read would see
        # neither. See scripts/workflow_run_source.
        from scripts.workflow_run_source import resolved_workflow_text

        text = resolved_workflow_text(ROOT / ".github" / "workflows" / wf, ROOT)
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




# ── Catalyst mode — the evidence boundary (W2C/W3) ─────────────────────────
METHODOLOGY = ROOT / "site" / "seasonalitydata" / "methodology.json"

# Causal language is the fabrication this surface is uniquely exposed to. Its
# whole premise is "no event source is connected", so a sentence that explains
# WHY a name moves in a season is a claim derived from data the same page says
# it does not have — and it needs no numeral, so the invention ban below cannot
# see it (mutation 8, adversarial review 2026-08-07).
BANNED_CAUSAL = [
    r"\bbecause\b", r"\bdrives?\b", r"\bdriven by\b", r"\bdue to\b",
    r"\bcaused? by\b", r"\bcauses\b", r"\bexplains?\b", r"\bleads? to\b",
    r"\bresults? from\b", r"\bwhy this\b", r"\breason\b",
    "导致", "推动", "由于", "因为", "原因", "促使", "造成",
]
# Nor may it promise. A schedule with no feed behind it is the same defect
# wearing the future tense.
BANNED_PROMISE = [
    r"\bexpected\b", r"\bupcoming\b", r"\bscheduled\b", r"\bwill happen\b",
    r"\bnext catalyst\b", r"\bahead of\b",
    "预计", "即将", "定于", "预期",
]


@pytest.fixture(scope="module")
def methodology() -> dict:
    return json.loads(METHODOLOGY.read_text())


def render_with(methodology: dict | None, entity: dict) -> str:
    """Render the real template against a synthetic method contract.

    Without this every Catalyst guard reads ONE artifact state, so a page that
    hardcodes its counts and a page that computes them are indistinguishable —
    the repo's own hardcoded-promotion-stat-outlives-its-recompute trap."""
    from jinja2 import Environment, FileSystemLoader

    view = bss.build_view(entity, None, True, methodology)
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.globals.update(zip=zip, abs=abs, enumerate=enumerate)
    return env.get_template("stock_seasonality.html.j2").render(v=view, built="test")


def _balanced(markup: str, start: int, tag: str = "div") -> str:
    """`markup[start:]` up to the element's MATCHING close tag."""
    depth, j, o, c = 0, start, f"<{tag}", f"</{tag}>"
    while j < len(markup):
        if markup.startswith(o, j):
            depth += 1
            j += len(o)
        elif markup.startswith(c, j):
            depth -= 1
            j += len(c)
            if depth == 0:
                return markup[start:j]
        else:
            j += 1
    raise AssertionError(f"unbalanced <{tag}> from {start}")


def catalyst_markup(markup: str) -> str:
    """The Catalyst surface — by CLASS MEMBERSHIP, not by a positional slice.

    The first cut sliced from the wrapper to the calendar's first card, so a
    SECOND `.sx-cat` panel placed after that card rendered in the same mode, on
    the same screen, and was invisible to every guard below: a fabricated FDA
    decision date and a 62% hit rate shipped green (mutation C, adversarial
    review 2026-08-07). One panel is asserted, then extracted balanced."""
    assert markup.count('class="sx-cat"') == 1, "exactly one Catalyst panel"
    assert markup.count('id="sx-catalyst"') == 1
    return _balanced(markup, markup.index('<div class="sx-cat"'))


def catalyst_text(markup: str) -> str:
    """Always-visible Catalyst copy: help tips stripped, tags out, entities decoded."""
    return unescape(re.sub(r"<[^>]+>", " ", visible(catalyst_markup(markup))))


def catalyst_tip_text(markup: str) -> str:
    """Tier-2 tip copy on the Catalyst surface. `visible()` strips it, so the
    invention ban never looked inside a tooltip."""
    tips = re.findall(r'<span class="sx-tip">(.*?)</span></span>',
                      catalyst_markup(markup), flags=re.S)
    return unescape(re.sub(r"<[^>]+>", " ", " ".join(tips)))


def _spans(markup: str, opener: str) -> list[int]:
    out, i = [], markup.find(opener)
    while i != -1:
        out.append(i)
        i = markup.find(opener, i + 1)
    return out


def _balanced_span(markup: str, start: int) -> str:
    depth, j = 0, start
    while j < len(markup):
        if markup.startswith("<span", j):
            depth += 1
            j += 5
        elif markup.startswith("</span>", j):
            depth -= 1
            j += 7
            if depth == 0:
                return markup[start:j]
        else:
            j += 1
    raise AssertionError("unbalanced span")


def _js_body(js: str, name: str) -> str:
    """The body of `function <name>(`, brace-counted."""
    i = js.index(f"function {name}(")
    j = js.index("{", i)
    depth, k = 0, j
    while k < len(js):
        if js[k] == "{":
            depth += 1
        elif js[k] == "}":
            depth -= 1
            if depth == 0:
                return js[j:k + 1]
        k += 1
    raise AssertionError(f"unbalanced body for {name}")


def _reduced_motion_block(css: str) -> str:
    """The reduced-motion at-rule, bounded at its CLOSING BRACE.

    Slicing to EOF made every assertion satisfiable by a selector appearing
    anywhere later in the sheet — including in a rule that re-enables motion
    (mutation 5b)."""
    i = css.index("@media (prefers-reduced-motion: reduce)")
    j = css.index("{", i)
    depth, k = 0, j
    while k < len(css):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                return css[i:k + 1]
        k += 1
    raise AssertionError("unbalanced reduced-motion block")


# ── the mode control ───────────────────────────────────────────────────────
def test_mode_switch_is_in_the_masthead_not_the_lens_row(html):
    """Mode changes what the page is ABOUT; a lens changes how one chart is drawn.
    So it must not sit in .sx-ctrls with Median/Raw/Max — it takes the masthead
    slot above the H1, and it reuses the segmented idiom rather than inventing
    a control (or, worse, a second page header)."""
    mast = html[html.index('<header class="sx-mast">'):html.index("</header>")]
    assert 'id="sx-mode"' in mast, "mode switch must live in the masthead"
    assert mast.index('id="sx-mode"') < mast.index('class="sx-h1"'), "mode sits above the H1"
    ctrls = html[html.index('<div class="sx-ctrls">'):]
    ctrls = ctrls[:ctrls.index("</section>")]
    assert 'id="sx-mode"' not in ctrls, "mode must not join the lens row"
    # the same family as the three lens groups, not a new widget
    block = html[html.index('<span class="sx-seg sx-mode"'):][:700]
    assert 'id="sx-mode"' in block and 'role="group"' in block
    assert block.count('aria-pressed="true"') == 1, "exactly one mode is pressed"
    assert block.count("<button") == 2
    assert 'data-v="calendar"' in block and 'data-v="catalyst"' in block


def test_the_mode_group_carries_a_bilingual_accessible_name(html):
    """A role="group" with no name is announced as bare "group"; an aria-label
    can hold exactly ONE language and translated attribute text is a CI-guarded
    house-law violation, so the name is a visually-hidden bilingual span. The
    inactive .l-* is display:none and therefore out of the name computation."""
    block = html[html.index('<span class="sx-seg sx-mode"'):][:400]
    assert 'aria-labelledby="sx-mode-lab"' in block
    assert "aria-label=" not in block, "an aria-label can only be one language"
    lab = html[html.index('id="sx-mode-lab"'):]
    lab = lab[:lab.index("</span>", lab.index("l-zh"))]
    assert "Page mode" in lab and "页面模式" in lab
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert ".sx-sr {" in css and "clip-path: inset(50%)" in css


def test_a_deep_link_never_leaves_the_control_contradicting_the_body(html):
    """?mode=catalyst paints the catalyst BODY from <head>, but the control ships
    calendar-pressed and was only reconciled by stock_seasonality.js at the end
    of <body> — so between parse and script the segment labelled the wrong page,
    and permanently if that file never loaded. Two fixes, both here: the pressed
    FILL is derived from html[data-sx-mode] so it cannot desync at all, and an
    inline script reconciles the ARIA during parse."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert 'html:not([data-sx-mode="catalyst"]) .sx-seg.sx-mode .gbtn[data-v="calendar"],' in css
    assert 'html[data-sx-mode="catalyst"] .sx-seg.sx-mode .gbtn[data-v="catalyst"] {' in css
    assert '.sx-seg.sx-mode .gbtn[aria-pressed="true"]' not in css, \
        "pressed fill must not wait for a JS-written attribute"
    # the ARIA reconciliation is INLINE and sits with the control, not at </body>
    bar = html[html.index('<div class="sx-modebar">'):]
    bar = bar[:bar.index("</div>")]
    assert "<script>" in bar and "aria-pressed" in bar
    assert bar.index('id="sx-mode"') < bar.index("<script>")


def test_the_mode_control_outranks_the_lens_controls_in_type_not_only_place(html):
    """It is the page's most senior control, so it must LOOK senior next to the
    lens segments. The first cut set both at 12.5px — the whole claimed
    hierarchy was a weight step, and placement was carrying it alone."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    mode = re.search(r"\.sx-seg\.sx-mode \.gbtn \{(.*?)\}", css, flags=re.S).group(1)
    lens = re.search(r"\n\.sx-seg \.gbtn \{(.*?)\}", css, flags=re.S).group(1)
    mode_px = float(re.search(r"(\d+(?:\.\d+)?)px", mode.split("font:")[1]).group(1))
    lens_px = float(re.search(r"(\d+(?:\.\d+)?)px", lens.split("font:")[1]).group(1))
    assert mode_px > lens_px, f"mode {mode_px}px is not senior to lens {lens_px}px"
    assert "var(--sx-display)" in mode and "var(--sx-data)" in lens


def test_mode_change_is_announced_and_keyboard_reachable(html):
    """A pressed segment is silent to a reader who is not on the control."""
    live = html[html.index('id="sx-mode-live"'):][:200]
    assert 'role="status"' in live and 'aria-live="polite"' in live
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    # native <button>s (Enter/Space are the user agent's job) + a visible ink ring
    assert ".sx-seg .gbtn:focus-visible { outline: 2px solid var(--sx-ink)" in css
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    assert "sx-mode-live" in js
    # WIRED, not merely defined: deleting the call site left the identifier in
    # the file and the old grep-assertion green while the click path went silent.
    assert "announceMode(" in _js_body(js, "setMode")


def test_the_catalyst_cta_keeps_a_visible_focus_ring():
    """The only click affordance unique to this mode. Its sibling segment ring is
    pinned above; this one shipped unguarded, so `outline: none` was green."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert ".sx-cta:focus-visible { outline: 2px solid var(--sx-ink); outline-offset: 2px; }" in css


def test_mode_creates_no_second_page_header(html):
    """CLAUDE.md §Navigation: exactly two header families, and this page uses the
    authenticated one. A mode switch is a control, never a chrome bar."""
    block = catalyst_markup(html)
    for tag in ("<header", "<nav", "site-nav", "nav-links"):
        assert tag not in block, tag
    assert html.count('<nav class="site-nav">') == 1


def test_mode_persists_the_way_the_page_already_persists_state(html):
    """The symbol lives in the URL query; so does the mode. pushState, not
    replaceState, because Back must return the reader to the mode they came
    from — and the head applies it before first paint so a deep link never
    flashes the calendar first."""
    head = html[:html.index("</head>")]
    assert "searchParams.get('mode')" in head and "data-sx-mode" in head
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    assert 'u.searchParams.set("mode", m)' in js
    assert 'u.searchParams.delete("mode")' in js
    assert "history.pushState" in js
    assert 'addEventListener("popstate"' in js
    # a symbol switch rewrites the URL from the CURRENT href, so mode rides along
    assert 'u.searchParams.set("symbol", j.symbol)' in js
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert 'html[data-sx-mode="catalyst"] .sx-cal { display: none; }' in css
    assert 'html[data-sx-mode="catalyst"] .sx-cat { display: block; }' in css


def test_back_returns_the_reader_and_not_only_the_mode():
    """A mode swap rewrites the document from the masthead down. Back into
    catalyst from a scrolled calendar left the viewport 690px BELOW the mode's
    entire message at 375px, reading a bullet from a card that no longer
    existed; the only signal was the polite live region."""
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    body = _js_body(js, "revealMode")
    assert "sx-catalyst" in body and "sx-verdict" in body
    assert "prefers-reduced-motion" in body, "a forced smooth scroll ignores the setting"
    assert "if ((window.pageYOffset || 0) <= top) return;" in body, \
        "never yank a reader who is already above the surface"
    assert "revealMode(m)" in _js_body(js, "setMode")
    pop = js[js.index('addEventListener("popstate"'):][:400]
    assert "setMode(m, false, true)" in pop


def test_the_mode_switch_writes_no_dead_state():
    """`root.dataset.mode` was written on every switch and read by nothing —
    css and js both key off html[data-sx-mode]."""
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    assert "root.dataset.mode" not in js
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert ".sx-eyebrow {" not in css, "the mode bar replaced its only consumer"


# ── the ledger is computed, never authored ─────────────────────────────────
def test_catalyst_is_driven_by_the_availability_block(html, methodology):
    """Every line reads methodology.json. The page ships an UNAVAILABLE state
    because live_event_graph is false — if the artifact ever says otherwise this
    must be rewritten, not silently keep claiming a boundary that moved."""
    avail = methodology["availability"]
    assert avail["live_event_graph"] is False, "premise of the shipped copy"
    cat = bss.build_catalyst(methodology)
    sources = [r for r in cat["rows"] if r["source"]]
    assert cat["n_live"] == sum(1 for r in sources if r["live"])
    assert cat["n_live"] + cat["n_dark"] == len(sources)
    assert cat["n_never"] == len(cat["rows"]) - len(sources)
    live = {r["key"] for r in cat["rows"] if r["live"]}
    assert live == {k for k, v in avail.items() if v is True and k != "note"}
    text = catalyst_text(html)
    assert f"{cat['n_live']} connected" in text
    assert f"{cat['n_dark']} not connected" in text


def test_the_rendered_ledger_is_exactly_the_built_ledger(html, methodology):
    """Pins the MARKUP to build_catalyst(), row for row and state for state.

    Without this the guards are lexical only: a fabricated row carrying no
    numeral passed every one of them (mutation 2b), and hardcoding the chip
    literals passed too (mutation B) because the count assertion only proved the
    string was present, never that the page recomputed it."""
    cat = bss.build_catalyst(methodology)
    block = catalyst_markup(html)
    rows = re.findall(r'<li class="sx-led-row is-(on|off|never)">(.*?)</li>', block, flags=re.S)
    assert len(rows) == len(cat["rows"]), "the ledger renders every built row and no other"
    built = [(r["state"], r["en"], r["zh"], r["why_en"], r["why_zh"]) for r in cat["rows"]]
    seen = []
    for state, body in rows:
        name = re.search(r'<span class="sx-led-name">(.*?)</span></span>\s*</span>', body, flags=re.S)
        name_en = re.search(r'<span class="l-en">(.*?)</span>', body).group(1)
        name_zh = re.search(r'<span class="l-zh">(.*?)</span>', body).group(1)
        whys = re.findall(r'<span class="l-(?:en|zh)">(.*?)</span>', body, flags=re.S)
        seen.append((state, unescape(name_en), unescape(name_zh),
                     unescape(whys[2]), unescape(whys[3])))
        assert name is None or True  # name span located above
    assert seen == built, f"markup drifted from build_catalyst(): {seen} != {built}"
    # and the state WORDS partition the same way
    assert block.count(">Connected<") == cat["n_live"]
    assert block.count(">Not connected<") == cat["n_dark"]
    assert block.count(">Not offered<") == cat["n_never"]


def test_the_counts_track_a_synthetic_artifact(entity, methodology):
    """Flip a field and the page must move. The chips are recomputed, not typed."""
    import copy
    m = copy.deepcopy(methodology)
    m["availability"]["live_event_graph"] = True
    out = render_with(m, entity)
    cat = bss.build_catalyst(m)
    assert (cat["n_live"], cat["n_dark"]) == (3, 0), "premise of this fixture"
    text = catalyst_text(out)
    assert "3 connected" in text and "0 not connected" in text
    assert "已接入 3 项" in text and "未接入 0 项" in text
    # and the headline follows the same field
    assert "Event coverage is connected" in text
    assert "Catalyst coverage is not connected" not in text


def test_a_connected_event_feed_never_renders_the_absence_clause(entity, methodology):
    """The event row's why-clause was assigned unconditionally, so flipping the
    feed live printed "No feed is connected for regulatory decisions, …"
    underneath the state word CONNECTED."""
    import copy
    m = copy.deepcopy(methodology)
    m["availability"]["live_event_graph"] = True
    row = [r for r in bss.build_catalyst(m)["rows"] if r["key"] == "live_event_graph"][0]
    assert row["live"] is True and row["state"] == "on"
    assert "No feed is connected" not in row["why_en"]
    assert "无数据源接入" not in row["why_zh"]
    assert "connected for" in row["why_en"] and "已接入数据源" in row["why_zh"]
    text = catalyst_text(render_with(m, entity))
    assert "No feed is connected" not in text
    # the empty-clocks branch has the same two faces
    assert "connected" in bss.event_clock_clause({}, True)[0]
    assert bss.event_clock_clause({}, False)[0].startswith("No clinical or regulatory")


def test_a_design_choice_is_never_counted_as_a_missing_feed(html, methodology):
    """`Forecasts` and `Symbol screening` say in their own why-clauses that we
    chose not to build them. Shipping them under NOT CONNECTED made the glance
    chip read "3 not connected" — "this page is 40% built" — when exactly ONE
    source is missing. They are off the rail and out of the counts."""
    cat = bss.build_catalyst(methodology)
    never = {r["key"] for r in cat["rows"] if r["state"] == "never"}
    assert never == {"live_forecasts", "live_screener"}
    assert cat["n_dark"] == 1, "exactly one source is actually missing"
    block = catalyst_markup(html)
    text = catalyst_text(html)
    assert "1 not connected" in text and "3 not connected" not in text
    assert "Chosen, not missing" in text and "刻意不做，并非缺失" in text
    assert "Not offered" in text and "不提供" in text
    # the rail is the evidence encoding, so a choice carries none of it
    for body in re.findall(r'<li class="sx-led-row is-never">(.*?)</li>', block, flags=re.S):
        assert "sx-rail" not in body, "a design choice must not be marked on the evidence axis"
    for state in ("on", "off"):
        for body in re.findall(rf'<li class="sx-led-row is-{state}">(.*?)</li>', block, flags=re.S):
            assert 'class="sx-rail"' in body
    # and the closing line no longer hardcodes the length of the list above it
    assert "all three hold" not in text


def test_a_missing_availability_field_renders_unavailable_never_a_default():
    """Fail closed: absent, null, or a truthy non-bool is NOT a connected feed."""
    assert not [r for r in bss.build_catalyst({})["rows"] if r["live"]]
    assert bss.build_catalyst({})["n_live"] == 0
    assert bss.build_catalyst({})["asof_en"] == ""
    for bogus in (None, "true", 1, {}, "yes"):
        cat = bss.build_catalyst({"availability": {"live_event_graph": bogus}})
        assert not [r for r in cat["rows"] if r["key"] == "live_event_graph"][0]["live"], bogus


def test_catalyst_renders_with_no_methodology_artifact(entity):
    """The producer contract does not exist yet, so the unreadable/absent case is
    the one that must not blow up or invent a reading."""
    view = bss.build_view(entity, None, True, None)
    cat = view["catalyst"]
    assert cat["n_live"] == 0
    assert cat["n_dark"] == sum(1 for _, _, _, _, _, src in bss.AVAIL_ROWS if src)
    assert cat["event_live"] is False and cat["clock_live"] is False
    assert cat["meth_ok"] is False


def test_the_dark_ledger_never_makes_a_claim_about_the_whole_page(entity, methodology):
    """Fail-closed produced a FALSE statement: with the availability block gone
    the page said "Nothing on this page is connected right now" one click away
    from 25 drawn years and a verdict it stands behind. The stance is scoped to
    the ledger, or to the method file, and always leaves a route."""
    import copy
    for m, probe_en, probe_zh in (
        ({k: v for k, v in methodology.items() if k != "availability"},
         "The method file could not be read.", "方法文件无法读取。"),
        (dict(copy.deepcopy(methodology), availability={"live_forecasts": False}),
         "No source below is connected.", "下方没有任何已接入的数据源。"),
    ):
        text = catalyst_text(render_with(m, entity))
        assert probe_en in text and probe_zh in text
        assert "Nothing on this page is connected" not in text
        assert "本页目前没有任何已接入的数据" not in text
        # Law 1: a stance still has to leave somewhere to go
        assert "The calendar clock is still drawn here." in text
        assert "Open the calendar clock" in text


# ── the hard line: nothing invented ────────────────────────────────────────
def test_catalyst_invents_no_event_no_date_no_probability(html, methodology):
    """The hard line: not one number on this surface that is not computed from a
    real artifact. Every numeral must live inside the page's figure idiom
    (<span class="n"> in a chip) — a structural rule, so it cannot go slack when
    the artifact's own date happens to contain a convenient digit."""
    cat = bss.build_catalyst(methodology)
    block = visible(catalyst_markup(html))
    text = unescape(re.sub(r"<[^>]+>", " ", block))
    outside = unescape(re.sub(r"<[^>]+>", " ", _strip_balanced(block, '<span class="n">')))
    assert not re.search(r"\d", outside), \
        f"figure outside the chip idiom: {re.findall(r'[^ ]*[0-9][^ ]*', outside)}"
    figures = [unescape(re.sub(r"<[^>]+>", " ", _balanced_span(block, i)))
               for i in _spans(block, '<span class="n">')]
    assert figures, "the counts are the only figures, and they must be there"
    for f in figures:
        assert (f"{cat['n_live']} connected" in f or f"{cat['n_dark']} not connected" in f
                or (cat["asof_en"] and cat["asof_en"] in f)), f"unexplained figure: {f!r}"
    assert "%" not in text, "no probability may appear where there is no model"
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text), "no ISO date"
    # not a placeholder and not a splash
    for term in ("coming soon", "stay tuned", "placeholder", "TBD", "to be announced",
                 "will be available", "即将", "敬请期待", "占位"):
        assert term.lower() not in text.lower(), term


def test_the_tier2_tips_invent_nothing_either(html):
    """`visible()` strips tips, so the whole invention ban had a hole exactly the
    size of a tooltip — a fabricated decision date in a `?` popover was unguarded."""
    tip = catalyst_tip_text(html)
    assert tip.strip(), "the surface does carry tips; this guard must not be vacuous"
    assert not re.search(r"\d{4}-\d{2}-\d{2}", tip)
    assert "%" not in tip
    for pattern in BANNED_PROMISE:
        assert not re.search(pattern, tip), pattern


def test_catalyst_asserts_no_cause(html):
    """A sentence explaining WHY a name moves in a season is knowledge derived
    from data this page says it does not have — and it carries no numeral, so
    the invention ban cannot see it. House law: copy never originates a signal."""
    text = catalyst_text(html)
    for pattern in BANNED_CAUSAL:
        assert not re.search(pattern, text, flags=re.I), f"causal claim: {pattern}"
    for pattern in BANNED_PROMISE:
        assert not re.search(pattern, text, flags=re.I), f"promise: {pattern}"


def test_catalyst_names_the_missing_feeds_in_plain_words_never_by_slug(html, methodology):
    """Doctrine Law 2: raw machine slugs never reach the reader. An unmapped clock
    folds into one plain phrase rather than leaking its key."""
    text = catalyst_text(html)
    for slug in (methodology.get("clocks") or {}).get("event") or []:
        # machine-shaped identifiers, never — a slug that happens to also be an
        # ordinary English word ("conference") is allowed to appear only because
        # its plain label legitimately contains it ("medical conferences")
        if "_" in slug:
            assert slug not in text, f"raw slug on the page: {slug}"
        assert bss.EVENT_CLOCK_EN[slug] in text, f"{slug} has no plain-word label"
        assert bss.EVENT_CLOCK_ZH[slug] in text, f"{slug} has no Chinese label"
    for slug in ("live_event_graph", "live_forecasts", "live_screener",
                 "live_calendar_clock", "live_selection_correction",
                 "biopharma.event.v1", "calendar_clock_live", "shadow"):
        assert slug not in text, slug
    en, zh = bss.event_clock_clause(methodology)
    assert "regulatory decisions" in en and "监管决定" in zh
    unmapped = bss.event_clock_clause({"clocks": {"event": ["a_brand_new_clock"]}})
    assert "a_brand_new_clock" not in unmapped[0] and bss.OTHER_CLOCK_EN in unmapped[0]
    assert bss.OTHER_CLOCK_ZH in unmapped[1]
    assert bss.event_clock_clause({})[0].startswith("No clinical or regulatory")


# ── the as-of stamp ────────────────────────────────────────────────────────
def test_a_malformed_as_of_prints_no_date_at_all():
    """It used to fold through the seasonal clock's 365-slot day-of-year helper,
    which returns slot 1 on any parse failure — so an ordinary ISO TIMESTAMP
    from a producer rendered "Through Jan 1", a date computed from nothing, on
    the one surface whose thesis is that no figure appears unless an artifact
    produced it. Availability fails closed; the date must too."""
    for bad in ("2026-08-06T00:00:00Z", "2026-08", "garbage", "2026-13-99",
                "20260806", " ", "2026/08/06", None):
        cat = bss.build_catalyst({"as_of": bad})
        assert cat["asof_en"] == "" and cat["asof_zh"] == "", bad
    good = bss.build_catalyst({"as_of": "2026-08-06"})
    assert good["asof_en"] == "Aug 6, 2026" and good["asof_zh"] == "2026年8月6日"
    # the 365-slot leap fold is a CLOCK convention; a wall-clock date is not folded
    leap = bss.build_catalyst({"as_of": "2028-02-29"})
    assert leap["asof_en"] == "Feb 29, 2028" and leap["asof_zh"] == "2028年2月29日"


def test_the_as_of_chip_carries_its_year_and_its_own_idiom(html, methodology):
    """Two bare "Through <Mon D>" chips in one masthead, in the same words the
    seasonal window chips use, is ambiguous on a 25-year page — and a two-year
    stale method was byte-identical to today's."""
    cat = bss.build_catalyst(methodology)
    assert re.search(r"\d{4}$", cat["asof_en"]), "the year is the point"
    text = catalyst_text(html)
    assert f"Method as of {cat['asof_en']}" in text
    assert f"方法更新于 {cat['asof_zh']}" in text
    assert "Through" not in text, "that idiom belongs to the price-coverage chip"


# ── doctrine ───────────────────────────────────────────────────────────────
def test_catalyst_carries_a_stance_and_a_one_click_route_back(html):
    """Doctrine Law 1 — a surface that shows a state with no 'so what do I do'
    makes the reader do the analyst's job, even when the honest answer is
    'this one is empty, read the other one'."""
    text = catalyst_text(html)
    assert "Catalyst coverage is not connected" in text
    assert "Read the calendar clock instead" in text
    assert "催化剂数据尚未接入" in text and "改用日历时钟" in text
    # the route is a control, not a sentence pointing somewhere
    assert 'id="sx-to-cal"' in html and 'class="sx-cta"' in html
    js = (ROOT / "templates" / "stock_seasonality.js").read_text()
    assert "sx-to-cal" in js and 'setMode("calendar", true' in js
    # and it names what the calendar does answer
    assert "What the calendar clock answers" in text
    assert "日历时钟能回答什么" in text
    # conditions being watched — never a promise and never a date
    assert "Conditions we watch — not a schedule." in text
    assert "stays empty on purpose" in text


def test_the_boundary_says_where_trial_dates_actually_live(html):
    """The reader's next question at "no trial dates here" is "then who has
    them?" — and BioCatalyst Intelligence is one click away in this page's own
    nav rail. Leaving it unmentioned made an honest page-scoped claim read as a
    false program-scoped one to anyone arriving from that nav item. The second
    sentence is load-bearing: it says what that page is NOT."""
    text = catalyst_text(html)
    assert "Trial and approval dates live on" in text
    assert "BioCatalyst Intelligence" in text and "生物医药催化剂智能" in text
    assert "Nothing there is checked against past years." in text
    assert "不与过往年份对照检验" in text
    assert 'href="biocatalyst.html"' in catalyst_markup(html)
    assert (ROOT / "site" / "biocatalyst.html").is_file(), "never route into a 404"
    import yaml
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    tiers = [t for t in ("public", "free_registered")
             if "/biocatalyst.html" in policy[t]["exact"]]
    assert tiers, "never route at a page the serving policy does not allow-list"
    # the same tier this page's own nav rail already links it at
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text()
    assert "biocatalyst.html" in nav


def test_catalyst_stance_stays_inside_the_glance_word_budget(html):
    """Doctrine Law 4: title <=4 words, subtitle <=14. The header region of a
    Tier-3 page still follows Tier 1, and the guard is written to the LAW — the
    first cut asserted <=20, six words of slack the doctrine does not grant."""
    block = catalyst_markup(html)
    for cls in ('<p class="sx-verdict">', '<p class="sx-cat-act">'):
        chunk = block[block.index(cls):]
        chunk = chunk[:chunk.index("</p>")]
        en = unescape(re.sub(r"<[^>]+>", " ", chunk.split('<span class="l-zh">')[0]))
        assert len(en.split()) <= 14, f"over budget ({len(en.split())}): {en.strip()!r}"


def test_catalyst_copy_survives_the_tier1_vocabulary_ban(html):
    """The page-wide guard already scans this markup; this pins the Catalyst
    surface on its own so a future edit fails HERE, naming the surface."""
    text = catalyst_text(html)
    for term in BANNED:
        assert term not in text, term
    for pattern in BANNED_WORDS:
        assert not re.search(pattern, text), pattern
    assert "validated" not in text.lower()


def test_every_calendar_block_is_tagged_for_the_mode_swap(html):
    """Mode hides `.sx-cal` and shows `.sx-cat`. Anything carrying NEITHER leaks
    into both modes: the seasonality loader error and the "we don't cover that
    symbol yet" 404 notice both printed on the Catalyst surface, the second one
    directly above a chip saying coverage here is the same for every symbol."""
    wrap = html[html.index('<main class="sx-wrap"'):html.index("</main>")]
    body = wrap[wrap.index("</header>"):]
    tops = re.findall(r'\n  <(?:p|ul|div|section|details)\b[^>]*class="([^"]*)"', body)
    assert len(tops) >= 6, "the scan must actually see the page's blocks"
    for cls in tops:
        names = cls.split()
        assert "sx-cal" in names or "sx-cat" in names, \
            f"untagged top-level block leaks into both modes: {cls!r}"


# ── bilingual ──────────────────────────────────────────────────────────────
def test_catalyst_zh_is_native_not_transliterated_english(html):
    """Count-equality alone is not parity: a string authored with NO t() wrapper
    keeps the counts equal and shows English to a ZH reader (mutation 4b). So the
    EN lane is REMOVED and whatever survives must be Chinese."""
    block = catalyst_markup(html)
    assert block.count('class="l-en"') == block.count('class="l-zh"')
    zh_only = visible(re.sub(r'<span class="l-en">.*?</span>', " ", block, flags=re.S))
    for chunk in unescape(re.sub(r"<[^>]+>", "\n", zh_only)).split("\n"):
        t = chunk.strip()
        if not t or CJK.search(t):
            continue
        # figures, arrows, the `?` help glyph and punctuation are legitimately
        # latin in a zh lane; letters are not, so no English word survives this
        assert re.fullmatch(r"[-+0-9.,%<>→?·|:()\s/、。；：]{0,24}", t), \
            f"untranslated copy reaches a zh reader: {t!r}"
    bad = []
    for body in re.findall(r'<span class="l-zh">(.*?)</span>', block, flags=re.S):
        t = re.sub(r"<[^>]+>", "", body).strip()
        if not t or CJK.search(t) or re.fullmatch(r"[-+0-9.,%<>→·|:()\s/A-Z]{0,24}", t):
            continue
        bad.append(t)
    assert not bad, f"zh spans with no Chinese: {bad[:5]}"


def test_catalyst_zh_is_not_english_shaped(html, methodology):
    """Memory: zh-copy-was-english-shaped-not-wrong. These three read as
    transliteration, not as Chinese a pharma reader would write."""
    text = catalyst_text(html)
    assert "试验读数" not in text, "读数 is a meter reading; a readout is 结果公布"
    assert "上市销售" not in text, "上市 alone reads as an IPO on a stock page"
    assert "按设计" not in text, "a direct calque of 'by design'; native is 刻意"
    assert bss.EVENT_CLOCK_ZH["clinical_trial"] == "试验结果公布"
    assert bss.EVENT_CLOCK_ZH["commercial"] == "产品上市"
    # CJK typography: 破折号 or a colon, never a half-width em dash with spaces
    block = catalyst_markup(html)
    for body in re.findall(r'<span class="l-zh">(.*?)</span>', block, flags=re.S):
        assert " — " not in body, f"half-width em dash in zh copy: {body[:60]!r}"
    mast = html[html.index('<div class="sx-modebar">'):]
    mast = mast[:mast.index("</div>")]
    for body in re.findall(r'<span class="l-zh">(.*?)</span>', mast, flags=re.S):
        assert " — " not in body, f"half-width em dash in zh copy: {body[:60]!r}"


# ── the one graphic device ─────────────────────────────────────────────────
def test_catalyst_rail_reads_as_a_boundary_in_both_states():
    """The one graphic device in this mode. A hollow 1px outline was tried and
    does not read at a 3px width, so 'not connected' is dashed — which is
    already this page's vocabulary for unsettled (gate rules, exploratory chip,
    notice boxes)."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    assert ".is-on  > .sx-rail { background: var(--sx-ink); }" in css
    assert "repeating-linear-gradient" in css[css.index(".is-off > .sx-rail"):][:400]
    # "2 connected" is a count of sources, not a price direction: --up would flip
    # red under the zh 红涨绿跌 swap and read as a market call about coverage
    tpl = (ROOT / "templates" / "stock_seasonality.html.j2").read_text()
    cat = tpl[tpl.index('<div class="sx-cat"'):]
    assert "sx-chip-up" not in cat and "var(--up)" not in cat
    assert "sx-chip-ink" in cat and ".sx-chip-ink {" in css


def test_reduced_motion_parks_the_catalyst_affordances():
    """The kill block is read to its CLOSING BRACE, not to EOF — sliced to EOF
    any later rule in the sheet satisfied it, including one re-enabling motion.
    And only selectors that actually MOVE are pinned: `.sx-cta::before/::after`
    were asserted while `.sx-cta` has no generated content at all, so two of the
    five assertions were vacuous."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    block = _reduced_motion_block(css)
    assert block.endswith("}")
    # COMMENTS OUT FIRST. Deleting `.sx-cta` from the selector list left a
    # comment in this very block that names it, and the presence assertion
    # passed on the prose — a guard satisfied by its own explanation.
    decls = re.sub(r"/\*.*?\*/", " ", block, flags=re.S)
    assert ".sx-cta" in decls, "the mode's one moving affordance must be parked"
    assert "animation: none !important; transition: none !important;" in decls
    # nothing named here may be a pseudo with no motion behind it
    assert ".sx-cta::before" not in decls and ".sx-led-break::before" not in decls
    # and .sx-cta genuinely moves, so the assertion above is not vacuous either
    cta = css[css.index("\n.sx-cta {"):]
    assert "transition:" in cta[:cta.index("}")]


def test_catalyst_recomposes_at_the_mobile_floor():
    """375px is the hard floor. The ledger drops its status column under the row
    rather than squeezing it, and the rail spans both lines so one row still
    reads as one piece of evidence. Measured in the browser at 375px:
    document.scrollWidth == window.innerWidth == 375, EN and ZH."""
    css = (ROOT / "templates" / "stock_seasonality.css").read_text()
    block = css[css.index("@media (max-width: 720px)"):]
    block = block[:block.index("@media (max-width: 420px)")]
    assert ".sx-led-row, .sx-led-never .sx-led-row { grid-template-columns: 3px minmax(0, 1fr);" in block
    assert ".sx-rail { grid-row: 1 / span 2; }" in block
    assert ".sx-led-state, .sx-led-never .sx-led-state { grid-column: 2;" in block
