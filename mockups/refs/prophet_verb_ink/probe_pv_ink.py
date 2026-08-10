"""Prophet-card verb INK probe — every verb, both themes, both languages.

    python3 mockups/refs/prophet_verb_ink/probe_pv_ink.py
    python3 mockups/refs/prophet_verb_ink/probe_pv_ink.py --near-mix 56%   # sweep a candidate
    python3 mockups/refs/prophet_verb_ink/probe_pv_ink.py --shoot          # + swatch PNGs

Why this exists as its own harness rather than a crop off a board: the defect it
was built for is a TOKEN defect, and no shipped board carries all five verbs at
once (the us_stocks board renders buy/near/wait and no hold/avoid). Measuring the
token plane directly is the only way to see all 5 × 2 themes × 2 languages, and
it is the plane the fix edits.

It is NOT a mockup. Both stylesheets are the shipping ones, unmodified:

  · ``templates/theme.css`` is inlined verbatim — that is where every ``--pv-*``
    hue, every ``--ink-pv-*`` mix and the ``html[data-lang="zh"]`` 红涨绿跌 swap
    live, and the inks resolve at ``html`` scope, so the probe sets the same two
    attributes production sets (``data-theme`` / ``data-lang``).
  · the card CSS is the real ``pv_css()`` macro from
    ``templates/_prophet_card.html.j2``, RENDERED through Jinja rather than
    regex-scraped, so the jinja comments inside the ``<style>`` block resolve the
    way the page resolves them and the rules measured are byte-identical to the
    rules shipped.

Every rule that prints a verb hue AS TEXT is measured — the set was taken by
grepping ``var(--pvh-ink)`` rather than by picking the obvious two, because a
consumer nobody measured is exactly how the defect this was built for survived:

  · ``.pv-chip``  — 10px/800 uppercase, on ``color-mix(--pvh 13%, --panel)``.
    ``.pv-buy`` inverts this (solid ink fill, ``--panel`` text) and is measured
    in its inverted form, because that is the pair a reader actually sees.
  · ``.pv-edn``   — 14px/800 tabular Edge number, on the card's ``--panel2``.
  · ``.pv-znl``   — 9.5px/800 zone label, on the ``.pv-zn`` footer's own
    ``color-mix(--panel 55%, --bg)`` — a THIRD surface, neither panel nor panel2.
  · ``.pv-trg``   — 10px/800 target pill, on a 9% tint (thinner than the chip's
    13%, so it is a strictly harder surface and cannot be inferred from it).

All are SMALL text under WCAG (9.5–14px bold is nowhere near the 18.66px-bold
large-text threshold), so the floor is 4.5:1, not 3.0:1.

``cn_limit_picks.html.j2`` also reads ``--pvh-ink`` but rebinds it to
``--prov-ink``/``--ink-warn``, so it never resolves a ``--ink-pv-*`` token and is
out of this probe's scope.

Compositing is done by walking each node's ancestors and layering every
non-transparent background, because ``getComputedStyle`` reports a translucent
background as authored, not as painted — measuring text against ``rgba(...)``
directly is measuring the authored value and not the pixel.

``_rgb``/``_over``/``ratio`` are imported from the breathing-platform shooter
rather than retyped. Its ``color(srgb …)`` branch is load-bearing: Chromium
serialises every ``color-mix()`` result as 0..1 floats, and this palette is
almost entirely ``color-mix``, so a naive parse crushes every mixed colour to
near-zero luminance and reports a uniform ~1.00:1 — a catastrophic-looking
failure that is purely a parser artifact.

Exit code is non-zero when any measured pair lands under AA, so this doubles as
a pre-push gate.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mockups" / "refs" / "breathing-platform"))

from shoot_wl1 import _over, _rgb, ratio  # noqa: E402 — reused, not retyped

#: WCAG 2.1 AA for small text. Both consumers are small text (see module docstring).
AA_SMALL = 4.5

#: Verb order = the card's own severity ladder, not alphabetical.
VERBS = ("buy", "near", "wait", "hold", "avoid")

def _chip_text() -> dict:
    """{verb: (en, zh)} read from the template's own _VEN/_VZH maps.

    Parsed rather than copied: a hand-typed copy of this had 'near' as 接近 when
    production ships 临近, so the crops carried a word the product never prints.
    """
    src = (ROOT / "templates" / "_prophet_card.html.j2").read_text(encoding="utf-8")
    out = {}
    for name in ("_VEN", "_VZH"):
        m = re.search(rf"set {name} = \{{(.*?)\}}", src, re.S)
        assert m, f"{name} not found in _prophet_card.html.j2 — re-point the probe"
        pairs = dict(re.findall(r"'([a-z]+)'\s*:\s*'([^']+)'", m.group(1)))
        for verb, label in pairs.items():
            out.setdefault(verb, []).append(label)
    missing = [v for v in VERBS if len(out.get(v, [])) != 2]
    assert not missing, f"verb label maps incomplete for {missing}"
    return {v: tuple(out[v]) for v in VERBS}


#: Rendered into the chip so the crops read as the real thing in both languages.
CHIP_TEXT = _chip_text()

COMBOS = (("en", "light"), ("zh", "light"), ("en", "dark"), ("zh", "dark"))


def _card_css() -> str:
    """Render the shipping ``pv_css()`` macro through Jinja."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    mod = env.get_template("_prophet_card.html.j2").make_module({"t": lambda *a, **k: ""})
    return str(mod.pv_css())  # type: ignore[attr-defined]


def _page(theme: str, lang: str, near_mix: str | None) -> str:
    theme_css = (ROOT / "templates" / "theme.css").read_text(encoding="utf-8")
    override = ""
    if near_mix:
        # Same selector the fix edits, appended last so it wins the tie at equal specificity.
        override = (
            '<style>html[data-theme="light"][data-lang="zh"]{'
            f"--ink-pv-near: color-mix(in srgb, var(--pv-near) {near_mix}, var(--text));"
            "}</style>"
        )
    idx = 0 if lang == "en" else 1
    cards = "\n".join(
        f'''<a class="pvcard pv-{v}" data-verb="{v}">
              <div class="pv-ov pv-ovl"><span class="pv-chip">{CHIP_TEXT[v][idx]}</span></div>
              <div class="pv-nochart"></div>
              <div class="pv-bd">
                <div class="pv-hd">
                  <span class="pv-idw"><span class="pv-tk">ABCD</span></span>
                  <span class="pv-edge"><span class="pv-edl">Edge</span><span class="pv-edn">+4.2</span></span>
                </div>
                <div class="pv-mk"><span class="pv-trg">T 152.40</span></div>
              </div>
              <div class="pv-zn">
                <span class="pv-znl">ZONE</span><span class="pv-znr">148.2–151.6</span>
              </div>
            </a>'''
        for v in VERBS
    )
    return f"""<!doctype html>
<html lang="{lang}" data-theme="{theme}" data-lang="{lang}">
<head><meta charset="utf-8"><title>pv ink probe {lang}/{theme}</title>
<style>{theme_css}</style>
{_CARD_CSS}
{override}
<style>
  body{{background:var(--bg);margin:0;padding:18px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
  .pvgrid{{display:grid;grid-template-columns:repeat(5,246px);gap:12px}}
  .l-en{{display:{'inline' if lang == 'en' else 'none'}}}
  .l-zh{{display:{'none' if lang == 'en' else 'inline'}}}
</style>
</head>
<body><div class="pvgrid">{cards}</div></body></html>"""


#: Walks up from a node layering every painted background, then measures.
_PROBE_JS = """
() => {
  const bgOf = (el) => {
    // Layer ancestor backgrounds bottom-up until an opaque one is reached.
    const stack = [];
    for (let n = el; n; n = n.parentElement) {
      const bg = getComputedStyle(n).backgroundColor;
      stack.push(bg);
      if (!/rgba\\(.*,\\s*0\\)/.test(bg) && !bg.includes('transparent')) {
        const m = bg.match(/[\\d.]+/g);
        if (!m || m.length < 4 || parseFloat(m[3]) >= 1) break;
      }
    }
    return stack;
  };
  const out = [];
  for (const card of document.querySelectorAll('.pvcard')) {
    const verb = card.dataset.verb;
    for (const sel of ['.pv-chip', '.pv-edn', '.pv-znl', '.pv-trg']) {
      const el = card.querySelector(sel);
      if (!el) continue;
      out.push({verb, sel, fg: getComputedStyle(el).color, bgs: bgOf(el)});
    }
  }
  return out;
};
"""


def measure(near_mix: str | None = None, shoot: str | None = None):
    from playwright.sync_api import sync_playwright

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for lang, theme in COMBOS:
            page = browser.new_page(viewport={"width": 1340, "height": 260},
                                    device_scale_factor=2)
            page.set_content(_page(theme, lang, near_mix), wait_until="load")
            page.wait_for_timeout(140)
            if shoot:
                # Named for the MIX actually rendered, never "before"/"after" —
                # a shot whose filename asserts a state it cannot prove is how a
                # proof crop ends up showing the wrong side of the fix.
                page.locator(".pvgrid").screenshot(
                    path=str(HERE / f"pv_verbs_{lang}_{theme}_{shoot}.png"))
            for r in page.evaluate(_PROBE_JS):
                bg = None
                for layer in reversed(r["bgs"]):        # bottom-up
                    c = _rgb(layer)
                    if c is None or c[3] == 0:
                        continue
                    bg = c[:3] if bg is None else _over(c, bg)
                if bg is None:
                    bg = [255, 255, 255] if theme == "light" else [0, 0, 0]
                fg = _rgb(r["fg"])
                rows.append({
                    "lang": lang, "theme": theme, "verb": r["verb"],
                    "sel": r["sel"].lstrip("."),
                    "ratio": ratio(_over(fg, bg), bg),
                })
            page.close()
        browser.close()
    return rows


def report(rows) -> int:
    fails = [r for r in rows if r["ratio"] < AA_SMALL]
    width = max(len(v) for v in VERBS)
    for sel in ("pv-chip", "pv-edn", "pv-znl", "pv-trg"):
        print(f"\n  {sel}  (WCAG AA small text = {AA_SMALL}:1)")
        header = "  " + " " * (width + 2) + "".join(f"{l}/{t:<7}" for l, t in COMBOS)
        print(header)
        for verb in VERBS:
            cells = ""
            for lang, theme in COMBOS:
                hit = [r for r in rows
                       if r["verb"] == verb and r["sel"] == sel
                       and r["lang"] == lang and r["theme"] == theme]
                if not hit:
                    cells += f"{'—':<10}"
                    continue
                v = hit[0]["ratio"]
                cells += f"{v:>5.2f}{'  FAIL' if v < AA_SMALL else '      '}"
            print(f"  {verb:<{width + 2}}{cells}")
    print()
    if fails:
        for f in sorted(fails, key=lambda r: r["ratio"]):
            print(f"::error title=pv-ink-contrast::{f['lang']}/{f['theme']} "
                  f"{f['verb']} .{f['sel']} = {f['ratio']:.2f}:1 (< {AA_SMALL})", flush=True)
        print(f"\n  {len(fails)} pair(s) under AA.")
        return 1
    print(f"  all {len(rows)} pairs clear AA "
          f"(worst {min(r['ratio'] for r in rows):.2f}:1).")
    return 0


_CARD_CSS = ""


def main() -> int:
    global _CARD_CSS
    ap = argparse.ArgumentParser()
    ap.add_argument("--near-mix", default=None,
                    help="override --ink-pv-near's mix under light+zh, e.g. 56%%")
    ap.add_argument("--shoot", metavar="LABEL", default=None,
                    help="also write swatch PNGs tagged with this label; name it for "
                         "the TOKEN and MIX actually rendered (e.g. near70, avoid88)")
    args = ap.parse_args()
    _CARD_CSS = _card_css()
    label = f"--ink-pv-near @ {args.near_mix} (light+zh)" if args.near_mix else "as shipped"
    print(f"\n  prophet verb inks — {label}")
    return report(measure(args.near_mix, args.shoot))


if __name__ == "__main__":
    raise SystemExit(main())
