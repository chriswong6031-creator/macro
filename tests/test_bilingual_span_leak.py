"""Guard: the English half of a bilingual span pair must not also print the Chinese.

The site shows one language at a time by CSS — `html[data-lang]` hides `.l-zh` or
`.l-en` — so a pair only works when each span holds ONE language. macro.html's
Release Radar built its chips as

    +'<span class="l-en">benchmark-only 仅基准</span>'
    +'<span class="l-zh">仅基准</span>'

and the EN reader got "benchmark-only 仅基准": the l-zh span was correctly hidden,
and the translation rode along inside the l-en span where no language toggle can
reach it (operator report 2026-08-02; "awaiting data 待数据" on the no-data card was
the same construction).

The signature is deliberately allowlist-free, because a banned-word list would be a
pin on one postmortem rather than a check on the defect. What is wrong is not "CJK
appears in an l-en span" — `同花顺 Theme Baskets` and the china_mechanics glossary
(`涨停 Limit-Up`) are proper nouns and deliberate, and an allowlist would have to
grow every time one is added. What is wrong is the EN span ENDING with exactly what
its own l-zh sibling says: that is the translation duplicated into the copy that
hides it. A glossary term whose two spans are IDENTICAL is a different, legitimate
construction (both languages show the same term) and stays legal.

Runs over templates/ and the committed site/ pages both — the leak reaches a reader
through the render, and a template-only check would pass while the shipped page was
still wrong for a whole nightly cycle.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# CJK ideographs + CJK punctuation + fullwidth forms
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")
# an l-en span immediately followed by its l-zh sibling, tolerating the JS
# string-concatenation idiom ("...</span>' +'<span class=...") between them
PAIR = re.compile(
    r'class="l-en">([^<]*)</span>[\s\'"+]*<span class="l-zh">([^<]*)</span>'
)


def _leaks(text: str) -> list[tuple[str, str]]:
    out = []
    for en, zh in PAIR.findall(text):
        en, zh = en.strip(), zh.strip()
        if not zh or not CJK.search(en):
            continue
        # identical pair = deliberate (a glossary term shown the same in both);
        # EN strictly longer but ending in the ZH body = the translation leaked in
        if en != zh and en.endswith(zh):
            out.append((en, zh))
    return out


def _sources() -> list[Path]:
    return (sorted(ROOT.joinpath("templates").rglob("*.j2"))
            + sorted(ROOT.joinpath("templates").glob("*.js"))
            + sorted(ROOT.joinpath("site").glob("*.html")))


def test_detector_fires_on_the_shipped_defect() -> None:
    """Mutation check — the signature must actually catch the reported markup."""
    shipped = (
        """<div class="rr-chips-row">"""
        """<span class="rr-bmo-tag">"""
        """<span class="l-en">benchmark-only 仅基准</span>"""
        """<span class="l-zh">仅基准</span></span></div>"""
    )
    assert _leaks(shipped) == [("benchmark-only 仅基准", "仅基准")]
    # and the JS-concatenated form the template actually writes
    js = ("""+'<span class="l-en">awaiting data 待数据</span>'"""
          """+'<span class="l-zh">待数据</span>'""")
    assert _leaks(js) == [("awaiting data 待数据", "待数据")]


def test_identical_glossary_pairs_stay_legal() -> None:
    """china_mechanics shows 涨停 Limit-Up in BOTH languages on purpose."""
    assert _leaks('<span class="l-en">涨停 Limit-Up</span>'
                  '<span class="l-zh">涨停 Limit-Up</span>') == []


def test_proper_nouns_in_english_copy_stay_legal() -> None:
    """A Chinese vendor/index name inside English prose is not a leak."""
    assert _leaks('<span class="l-en">同花顺 Theme Baskets</span>'
                  '<span class="l-zh">同花顺主题篮子</span>') == []


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_english_span_repeats_its_chinese_sibling(path: Path) -> None:
    leaks = _leaks(path.read_text(encoding="utf-8", errors="ignore"))
    assert not leaks, "\n".join(
        f"{path.relative_to(ROOT)}: l-en {en!r} ends with its own l-zh {zh!r}"
        f" — drop {zh!r} from the English span" for en, zh in leaks
    )
