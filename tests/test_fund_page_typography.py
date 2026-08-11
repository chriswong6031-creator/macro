"""Regression guards for the fund pages' SM4-R3 typography treatment.

`templates/fund_dossier.html.j2` (every ``site/fund_<slug>.html``) and
`templates/fund_index.html.j2` were written to mirror the Ownership
Intelligence Desk, but the SM4-R3 fix that retired the desk's local ``--numf``
mono token was never ported to them — so word-bearing badges ("RELIABILITY
IMPROVING", "QUALITY_GROWTH") kept rendering in a monospace face while the desk
itself rendered them in Inter, and the two surfaces read as two products.

House law (memory ``mono-numerals-are-for-figures-never-words``): the terminal
mono face is for pure numeric FIGURES only. Anything containing a word inherits
the site's ``--font-ui`` (Inter, with ``-apple-system``/San Francisco in the
fallback chain); genuinely numeric spans get ``font-family:inherit`` plus
``font-variant-numeric:tabular-nums`` (Inter's own tabular figures). The ONLY
survivor of a real mono face is ``.spark`` — sparkline bars built from Unicode
block glyphs (▁▂▃▄▅▆▇█), which need fixed-width cells to align.

Pure source reads: no Jinja render, no network, no ``site/`` dependency, so
this can never be skipped out (the dossier tests in
``tests/test_smart_money_v3.py`` §4 are all jinja2-gated) and never trips the
sparse-worktree ``site/`` failure mode.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# (template, page-scope class) — the scope class carries the retired token.
FUND_TEMPLATES = (
    ("fund_dossier.html.j2", "fd"),
    ("fund_index.html.j2", "fx"),
)


def _src(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name,scope", FUND_TEMPLATES)
def test_fund_templates_never_reintroduce_the_numf_mono_token(name, scope):
    """``--numf`` is retired: no declaration, no ``var()`` read, no mention."""
    src = _src(name)

    assert "--numf" not in src, (
        f"templates/{name} reintroduced the retired --numf mono token. "
        "Word-bearing badges must inherit Inter (--font-ui); numeric spans use "
        "font-family:inherit + font-variant-numeric:tabular-nums; only .spark "
        "takes a real mono face, via var(--mono). See SM4-R3 in "
        "research/SMART_MONEY_V2_MASTERPLAN_BY_FABLE.md."
    )
    # Belt-and-braces: the old hardcoded stack must not come back inline either,
    # under --numf or any other name. The sanctioned --mono token names "SF Mono"
    # as a FALLBACK, so match the retired stack's distinctive leading face.
    assert '"SF Mono",ui-monospace' not in src, (
        f'templates/{name} reintroduced the pre-SM4-R3 mono stack '
        f'(\'"SF Mono",ui-monospace,...\'). Source mono from '
        f"var(--font-mono) via the page's --mono token instead."
    )


@pytest.mark.parametrize("name,scope", FUND_TEMPLATES)
def test_fund_numeric_spans_inherit_inter_with_tabular_figures(name, scope):
    """``.num`` is the numeric-figure span: Inter's tabular figures, not mono.

    Pins the SM4-R3 SHAPE, not merely the absence of a string — a heal that
    deleted ``--numf`` but swapped in some other mono face would pass a bare
    absence check.
    """
    src = _src(name)

    assert f".{scope} .num {{ font-family:inherit; font-variant-numeric:tabular-nums; }}" in src, (
        f"templates/{name}: .{scope} .num must inherit the UI font and use "
        "Inter's tabular figures (font-family:inherit + "
        "font-variant-numeric:tabular-nums)."
    )


def test_dossier_sparklines_keep_a_real_mono_face():
    """``.spark`` is the ONE sanctioned mono consumer — block glyphs must align.

    Only the dossier has sparklines; ``fund_index.html.j2`` has no ``.spark``,
    which is why it carries no ``--mono`` token at all.
    """
    dossier = _src("fund_dossier.html.j2")
    index = _src("fund_index.html.j2")

    assert '.fd { --mono:var(--font-mono,ui-monospace,"SF Mono",monospace);' in dossier, (
        "templates/fund_dossier.html.j2 must define --mono from the shared "
        "--font-mono token (mirrors .sm in templates/smart_money.html.j2)."
    )
    assert ".spark { font-family:var(--mono);" in dossier, (
        "templates/fund_dossier.html.j2: .spark draws Unicode block bars and "
        "needs fixed-width glyphs — it must source var(--mono)."
    )
    assert ".spark" not in index, (
        "templates/fund_index.html.j2 gained a .spark rule; it now needs its "
        "own --mono token (see the .fd definition in fund_dossier.html.j2)."
    )
