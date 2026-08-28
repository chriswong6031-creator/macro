"""Two localization repairs at their canonical source (Wave-C bug packet):

1. The shared five-market single-stock analyzer (templates/stockview.js, fed by
   engine/cycles.py + engine/stock_view.py) must carry real display twins on the
   engine/view contract instead of passing the English value as both languages.
2. The China dashboard's turnover percentile (templates/china.html.j2) must stop
   emitting a nested twin-inside-a-twin with the Chinese ordinal marker in the
   wrong position, and engine/i18n.py's t() must make that nesting structurally
   impossible going forward.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

from engine import i18n
from engine import cycles
from engine import stock_score as ss
from engine import stock_view as sv

REPO_ROOT = Path(__file__).resolve().parents[1]


# ===========================================================================
# Part B — engine/i18n.py: t_pctile() helper + t() nesting guard
# ===========================================================================
_PCTILE_CASES = [
    (1, "st"), (2, "nd"), (3, "rd"), (4, "th"),
    (11, "th"), (12, "th"), (13, "th"),
    (21, "st"), (96, "th"), (100, "th"),
]


@pytest.mark.parametrize("n,suffix", _PCTILE_CASES)
def test_t_pctile_english_ordinal_is_correct(n, suffix):
    s = str(i18n.t_pctile(n))
    assert f"{n}{suffix} percentile" in s, s


@pytest.mark.parametrize("n,suffix", _PCTILE_CASES)
def test_t_pctile_chinese_ordinal_marker_precedes_number(n, suffix):
    s = str(i18n.t_pctile(n))
    zh = re.search(r'<span class="l-zh">(.*?)</span>', s, re.S)
    assert zh, s
    # house form: 第N百分位 — the ordinal marker 第 comes FIRST, then the number,
    # then the percentile word 百分位 (never "N第百分位" / "N百分位" without 第).
    assert zh.group(1) == f"第{n}百分位", zh.group(1)
    assert zh.group(1).index("第") < zh.group(1).index(str(n))


@pytest.mark.parametrize("n,suffix", _PCTILE_CASES)
def test_t_pctile_emits_exactly_one_twin_no_nesting(n, suffix):
    """Proves t_pctile() never nests: exactly one l-en span and one l-zh span."""
    s = str(i18n.t_pctile(n))
    assert s.count('class="l-en"') == 1, s
    assert s.count('class="l-zh"') == 1, s


def test_t_rejects_a_nested_twin_argument():
    """The structural guard: engine/i18n.py t() must refuse an argument that is
    itself already dual-language span markup — the exact shape china.html.j2:2582
    used to build (`t(pctile ~ t('th percentile', 'th百分位'), ...)`)."""
    inner = str(i18n.t("th percentile", "th百分位"))
    with pytest.raises(ValueError, match="nested"):
        i18n.t("82" + inner)
    with pytest.raises(ValueError, match="nested"):
        i18n.t("82nd percentile", inner)


def test_t_plain_calls_are_unaffected_by_the_guard():
    """The guard must not false-positive on ordinary, non-nested calls."""
    s = str(i18n.t("Uptrend", "上涨趋势"))
    assert "Uptrend" in s and "上涨趋势" in s


# ===========================================================================
# Part B — china.html.j2 turnover row: render the REAL source (extracted from
# the live file, not a hand-copied duplicate, so this cannot silently drift)
# and assert the nesting is gone.
# ===========================================================================
def _render_turnover_snippet(pctile: int) -> str:
    text = (REPO_ROOT / "templates" / "china.html.j2").read_text(encoding="utf-8")
    macro_match = re.search(r"\{% macro t\(en, zh=''\) -%\}.*?\{%- endmacro %\}", text, re.S)
    assert macro_match, "china.html.j2's local t() macro definition not found — template drifted"
    line_match = re.search(r"^.*Turnover heat.*$", text, re.M)
    assert line_match, "china.html.j2 turnover-heat row not found — template drifted"
    tmpl_src = macro_match.group(0) + "\n" + line_match.group(0)
    env = jinja2.Environment(autoescape=False)
    env.globals.update(t_pctile=i18n.t_pctile)
    tmpl = env.from_string(tmpl_src)
    return tmpl.render(I={"turnover": {"pctile": pctile}})


def _spans_are_not_nested(html: str) -> bool:
    """No l-en/l-zh span's own content contains another l-en/l-zh span open tag."""
    for m in re.finditer(r'<span class="l-(?:en|zh)">(.*?)</span>', html, re.S):
        if 'class="l-en"' in m.group(1) or 'class="l-zh"' in m.group(1):
            return False
    return True


@pytest.mark.parametrize("pctile", [1, 2, 3, 11, 21, 82, 96, 100])
def test_china_turnover_row_has_no_nested_twin(pctile):
    html = _render_turnover_snippet(pctile)
    assert _spans_are_not_nested(html), html
    # the old defect nested a full inner twin's markup inside the outer twin's
    # own EN leg — that inner l-en/l-zh class markup must never appear literal
    # inside the rendered en/zh CONTENT (as opposed to as one of the row's own
    # top-level spans, which _spans_are_not_nested already isolates).
    assert html.count('class="l-en"') == html.count('class="l-zh"'), html


def test_china_turnover_row_chinese_word_order_and_only_one_language_pair():
    html = _render_turnover_snippet(82)
    zh_spans = re.findall(r'<span class="l-zh">(.*?)</span>', html, re.S)
    assert "第82百分位" in zh_spans, zh_spans        # the percentile leg specifically
    # exactly one <l-en, l-zh> pair for the percentile phrase itself (plus the
    # separate "Turnover heat" label pair and the froth/elevated qualifier pair
    # — three independent twins total on this row, none nested in another).
    assert html.count('class="l-en"') == html.count('class="l-zh"')
    assert html.count('class="l-en"') == 3, html


def test_china_turnover_row_old_defect_pattern_is_gone():
    """Pin against literal regression to the old composition."""
    html = _render_turnover_snippet(82)
    assert "th百分位" not in html          # old hard-coded English-only suffix leaking into zh
    assert "82第百分位" not in html         # old wrong CN word order (number before marker)


# ===========================================================================
# Part A — engine/cycles.py: ladder_state() must propagate label_zh
# ===========================================================================
def test_ladder_state_emits_label_zh_matching_state_display():
    """Point 1: STATE_DISPLAY already carries label_zh for all 9 states —
    ladder_state() must not drop it on the floor."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(3)
    n = 520
    t_arr = np.arange(n)
    period = 40
    phase = (t_arr % period) / period
    cyc_shape = np.where(phase < 0.5, phase / 0.5, (1 - phase) / 0.5)
    price = 100 * np.exp(0.0004 * t_arr) * (1 + 0.06 * cyc_shape) + rng.normal(0, 0.15, n)
    c = pd.Series(price, index=pd.bdate_range("2020-01-01", periods=n))

    st = cycles.ladder_state(cycles.cycle_state(c), cycles.mtf_snapshot(c))
    assert "label_zh" in st
    assert st["label_zh"] == cycles.STATE_DISPLAY[st["state"]]["label_zh"]


def test_state_display_zh_differs_from_english_for_every_state():
    """Guard against the same-string anti-pattern at the source enum."""
    for state, disp in cycles.STATE_DISPLAY.items():
        assert disp.get("label_zh"), f"{state} has no label_zh"
        assert disp["label_zh"] != disp["label"], f"{state}: zh == en"


# ===========================================================================
# Part A — engine/stock_score.py: bucket_display() human twin for the size enum
# ===========================================================================
def test_bucket_display_covers_every_closed_enum_value():
    for bucket in ("avoid", "quarter", "half", "three-quarter", "full"):
        en, zh = ss.bucket_display(bucket)
        assert en and zh
        assert en != bucket, f"{bucket}: English leaked the raw slug"
        assert "_" not in en, f"{bucket}: not a human label: {en!r}"
        assert en[0].isupper(), f"{bucket}: not sentence/title-cased: {en!r}"
        assert en != zh, f"{bucket}: zh == en (same-string anti-pattern)"


def test_bucket_display_unknown_slug_degrades_to_prettified_english_never_blank():
    en, zh = ss.bucket_display("brand-new-bucket")
    assert en == "Brand New Bucket"
    assert zh == en          # documented fallback: unknown degrades to prettified EN, not blank
    assert en and zh


def test_bucket_display_missing_bucket_is_none_not_blank_string():
    """A missing/absent size block must stay absent (existing 'omit, never blank'
    contract), not degrade to an empty-string label."""
    assert ss.bucket_display(None) == (None, None)
    assert ss.bucket_display("") == (None, None)


# ===========================================================================
# Part A — engine/stock_view.py: build_view() contract — both timing paths +
# the bucket twin, across every market fixture that is cheap to build.
# ===========================================================================
def _rec(market, **over):
    base = {"ticker": "T", "name": "Test", "alpha": 1.4,
            "ladder": {"state": "RALLY ON", "label": "UPTREND", "label_zh": "上涨趋势",
                       "entry": {"tag": "HOLD", "urgency": "hold"}},
            "tech": {"above200": True, "pct_vs_200dma": 8.0, "rsi14": 55.0}}
    base.update(over)
    return base


def _profiled(market, **over):
    rec = _rec(market, **over)
    rec["conviction"] = ss.conviction_profile(rec, market)
    return rec


@pytest.mark.parametrize("market", ss.MARKETS)  # US, CN, HK, CA, INTL — all cheap via
                                                  # the real conviction engine, no I/O.
def test_build_view_emits_state_label_zh_and_bucket_twins_per_market(market):
    """Point 2 + 3: every supported market's view contract carries the analyzer
    display twins the shared stockview.js renderer needs. All 5 markets are cheap
    to fixture through ss.conviction_profile (pure function, no data dependency),
    so no market is skipped/faked here."""
    rec = _profiled(market)
    d = sv.build_view(rec, market)["decision"]
    t = d["timing"]
    assert t.get("state_label_zh"), f"{market}: no state_label_zh"
    assert t["state_label_zh"] == "上涨趋势"
    assert t["state_label_zh"] != t["state_label"]

    size = d.get("size") or {}
    if size.get("bucket") is not None:      # bucket present whenever conviction sized the name
        assert size.get("bucket_label"), f"{market}: no bucket_label"
        assert size.get("bucket_label_zh"), f"{market}: no bucket_label_zh"
        assert size["bucket_label_zh"] != size["bucket_label"]
        assert size["bucket_label"] != size["bucket"], "raw slug leaked as the English label"


def test_build_view_state_label_zh_covers_the_no_conviction_fallback_path():
    """Point 2's SECOND timing block (:918-928 in the spec, the close-only /
    no-conviction fallback) must carry the same twin — this is the path that
    silently kept the bug if only the main branch were fixed."""
    rec = {"ladder": {"state": "FRESH BUY", "label": "Buy zone", "label_zh": "买入区",
                      "summary_line": "Confirmed cycle low",
                      "entry": {"tag": "BUY NOW", "tag_zh": "立即买入", "urgency": "now"}}}
    v = sv.build_view(rec, "INTL")
    assert v["decision"]["action"] is None          # confirms we're on the fallback branch
    t = v["decision"]["timing"]
    assert t["state_label_zh"] == "买入区"
    assert t["state_label_zh"] != t["state_label"]


def test_build_view_state_label_zh_degrades_to_english_when_state_unmapped():
    """An unmapped/absent state must degrade to today's English-only behaviour,
    never to a blank field (spec point 2's explicit fallback contract)."""
    rec = _rec("US", ladder={"state": "SOME_UNMAPPED_STATE", "label": "Weird State",
                              "entry": {"tag": "HOLD", "urgency": "hold"}})
    rec["conviction"] = ss.conviction_profile(rec, "US")
    t = sv.build_view(rec, "US")["decision"]["timing"]
    assert t["state_label_zh"] == "Weird State"     # falls back to the English label, not blank


@pytest.mark.parametrize("state", list(cycles.LADDER))
def test_every_ladder_state_view_twin_is_not_the_same_string_anti_pattern(state):
    """Guard test: for every closed ladder-state enum value, the view's Chinese
    field must not merely equal its English twin (the defect this packet fixes
    was exactly `B(t.state_label, t.state_label)` in stockview.js)."""
    disp = cycles.STATE_DISPLAY[state]
    rec = _rec("US", ladder={"state": state, "label": disp["label"],
                             "label_zh": disp["label_zh"],
                             "entry": {"tag": "HOLD", "urgency": "hold"}})
    rec["conviction"] = ss.conviction_profile(rec, "US")
    t = sv.build_view(rec, "US")["decision"]["timing"]
    assert t["state_label_zh"] != t["state_label"], state


# NOTE: no dedicated per-market fixture is added for HK/CA/INTL beyond the
# parametrized test above — ss.conviction_profile is a pure function over a
# plain dict for every market (no network/data-file dependency), so a
# per-market fixture is cheap everywhere and none needed to be skipped.
