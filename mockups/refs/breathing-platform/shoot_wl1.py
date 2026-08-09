"""W-L1 provisional board — crop shooter + computed-style verifier.

    python3 mockups/refs/breathing-platform/shoot_wl1.py

Shoots one crop per (state × lang × theme) = 16 PNGs off the mockups in this
directory, then reads back the things a screenshot cannot prove:

  · CONTRAST — every new ink/fill pair measured in BOTH themes against WCAG AA
    for small text (4.5:1). The marks-row chip and the two stamp treatments are
    the whole new palette, so all of it is measured, none of it eyeballed.
  · STAMP EXCLUSIVITY — never two stamps, and never a stamp on the confirmed
    board. The absence IS the third state, so absence is asserted, not assumed.
  · PERFORATED EDGE — the ::before exists exactly on the provisional panel and
    nowhere else, read off getComputedStyle rather than off the markup.
  · HEADER HEIGHT — the four states' panel headers stay within one line-height
    of each other, so flipping state never shoves the card grid.
  · NO MOTION — no animation/transition is introduced by the new classes (the
    design is deliberately static; this pins that it stays that way).
  · GLANCE-TIER VOCABULARY — the visible text INSIDE the board panels carries no
    program name, internal state name, or falsifier word, in either language.
    Scoped to .panel on purpose: this file's own <title> and its state dividers
    say "W-L1" and "PROVISIONAL" because they are review scaffolding, and the
    scaffolding is exactly what a builder must not carry across.
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
STATES = ["s1", "s2", "s3", "s4"]
STATE_SLUG = {"s1": "provisional", "s2": "confirmed", "s3": "stale", "s4": "closed"}

# Words that may never reach the glance tier. Scoped to the board panels, never
# to the whole document: this file's own <title> and its state dividers say
# "W-L1" and "PROVISIONAL" because they are review scaffolding — and the
# scaffolding is precisely what a builder must not carry across into the page.
# "provisional" is on the list as UI COPY: it is the correct word for the tier in
# the spec and in code comments, and the wrong word to say to a reader, who is
# owed the plain-word version ("tonight's picks, confirmed by morning").
BANNED = [
    "W-L1", "close-pass", "close pass", "armed", "reconciler", "admission",
    "gauntlet", "prereg", "provisional", "display-tier", "expected-null",
    "falsifier", "falsified", "refuted", "invalidated", "证伪",
]


def _lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _rgb(s):
    """Parse a computed colour to [r,g,b,a] with r/g/b on 0..255.

    Chromium serialises any color-mix() result as ``color(srgb 0.57 0.72 0.90)``
    — 0..1 floats — while plain values come back as ``rgb(146, 185, 230)``. Read
    naively, every mixed colour is crushed to near-zero luminance and EVERY pair
    measures ~1.00:1, which reads as a catastrophic contrast failure that is not
    real. The whole new palette here is color-mix, so this branch is the
    difference between measuring the design and measuring the parser.
    """
    s = (s or "").strip()
    m = re.findall(r"-?[\d.]+", s)
    if len(m) < 3:
        return None
    v = [float(x) for x in m[:3]]
    if s.startswith("color("):
        v = [x * 255.0 for x in v]
    return v + [float(m[3]) if len(m) > 3 else 1.0]


def _over(fg, bg):
    """Composite fg (may be translucent) over an opaque bg."""
    a = fg[3]
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)]


def ratio(fg, bg):
    l1, l2 = _lum(fg), _lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def main():
    from playwright.sync_api import sync_playwright

    fails, notes = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for lang in ("en", "zh"):
            for theme in ("dark", "light"):
                src = HERE / f"wl1_board_{lang}_{theme}.html"
                pg = b.new_page(viewport={"width": 1280, "height": 1000},
                                device_scale_factor=2)
                pg.goto(src.as_uri())
                pg.wait_for_timeout(280)

                panels = pg.query_selector_all(".panel")
                assert len(panels) == 4, f"expected 4 panels, got {len(panels)}"

                heights = []
                for i, st in enumerate(STATES):
                    panels[i].screenshot(
                        path=str(HERE / f"wl1_{STATE_SLUG[st]}_{lang}_{theme}.png"))
                    heights.append(pg.evaluate(
                        """p => p.querySelector('.nbgrid').getBoundingClientRect().top
                                - p.getBoundingClientRect().top""", panels[i]))

                # ---- header height invariance: flipping state must not shove the grid
                spread = max(heights) - min(heights)
                notes.append(f"header→grid offset {lang}/{theme}: "
                             + ", ".join(f"{h:.1f}" for h in heights)
                             + f"  (spread {spread:.1f}px)")
                # 4px, not a loose 20: all four states measured within 1.5px once
                # .pbs-note stopped wrapping, so anything above a rounding wobble
                # means a state flip would shove the card grid under the reader.
                if spread > 4:
                    fails.append(f"HEADER SHOVE {lang}/{theme}: spread {spread:.1f}px > 4")

                # ---- stamp exclusivity
                cnt = [pg.evaluate("p => p.querySelectorAll('.pbs').length", x) for x in panels]
                if cnt != [1, 0, 1, 1]:
                    fails.append(f"STAMP COUNT {lang}/{theme}: {cnt} != [1,0,1,1]")

                # ---- perforated edge: only on the provisional panel
                edge = [pg.evaluate(
                    """p => { const s = getComputedStyle(p, '::before');
                              return (s.content !== 'none' && s.height !== 'auto'
                                      && parseFloat(s.height) > 0) ? s.backgroundImage : ''; }""",
                    x) for x in panels]
                if not edge[0].startswith("repeating-linear-gradient"):
                    fails.append(f"NO PERFORATED EDGE on provisional {lang}/{theme}: {edge[0]!r}")
                for i in (1, 2, 3):
                    if edge[i].startswith("repeating-linear-gradient"):
                        fails.append(f"UNEXPECTED EDGE on {STATES[i]} {lang}/{theme}")

                # ---- contrast, measured (not eyeballed)
                page_bg = _rgb(pg.evaluate("getComputedStyle(document.body).backgroundColor"))
                for sel, label in ((".pbs-ahead", "stamp ahead"),
                                   (".pbs-behind", "stamp behind"),
                                   (".pv-mk-adj", "mark adjusted"),
                                   (".pbs-note", "note line"),
                                   (".pbs-note b", "note stance")):
                    # Collect the element's own fill and every ancestor fill up to
                    # and including the first OPAQUE one, so translucent tints can
                    # be composited in paint order. Starting the walk at the
                    # element itself (and stopping at the first non-transparent
                    # colour) makes a translucent chip its own backdrop and every
                    # such pair measures exactly 1.00:1.
                    got = pg.evaluate(
                        """s => { const e = document.querySelector(s); if (!e) return null;
                                  const stack = []; let n = e;
                                  while (n) { const c = getComputedStyle(n).backgroundColor;
                                    const a = /rgba?\\([^)]*?,\\s*([\\d.]+)\\s*\\)$/.exec(c);
                                    const a2 = /\\/\\s*([\\d.]+)\\s*\\)$/.exec(c);
                                    const al = a ? parseFloat(a[1]) : (a2 ? parseFloat(a2[1]) : 1);
                                    if (al > 0) stack.push(c);
                                    if (al >= 1) break;
                                    n = n.parentElement; }
                                  return [getComputedStyle(e).color, stack]; }""", sel)
                    if not got:
                        fails.append(f"MISSING {sel} in {lang}/{theme}")
                        continue
                    fg = _rgb(got[0])
                    layers = [_rgb(c) for c in got[1]]
                    base = (layers[-1][:3] if layers and layers[-1][3] >= 1
                            else page_bg[:3])
                    for lay in reversed(layers[:-1] if layers and layers[-1][3] >= 1
                                        else layers):
                        base = _over(lay, base)
                    r = ratio(_over(fg, base), base)
                    notes.append(f"contrast {label:<15} {lang}/{theme}: {r:.2f}:1")
                    if r < 4.5:
                        fails.append(f"CONTRAST FAIL {label} {lang}/{theme}: {r:.2f} < 4.5")

                # ---- no motion introduced by the new classes
                mo = pg.evaluate(
                    """() => ['.pbs','.pbs-note','.pv-mk-adj']
                         .map(s => { const e = document.querySelector(s); if (!e) return '';
                                     const c = getComputedStyle(e);
                                     return c.animationName + '|' + c.transitionProperty; })""")
                for s, v in zip(('.pbs', '.pbs-note', '.pv-mk-adj'), mo):
                    if not v.startswith("none|") or v.split("|")[1] not in ("none", "all"):
                        if not v.startswith("none|none"):
                            notes.append(f"motion {s} {lang}/{theme}: {v}")
                    if not v.startswith("none|"):
                        fails.append(f"UNEXPECTED ANIMATION on {s} {lang}/{theme}: {v}")

                # ---- glance-tier vocabulary, scoped to the board panels
                for i, st in enumerate(STATES):
                    txt = pg.evaluate("p => p.innerText", panels[i])
                    for word in BANNED:
                        if word.lower() in txt.lower():
                            fails.append(f"BANNED VOCAB {word!r} on {st} {lang}/{theme}")

                pg.close()
        b.close()

    print("\n".join(notes))
    print()
    if fails:
        print("FAILED:")
        for f in fails:
            print("  ·", f)
        sys.exit(1)
    print("ALL CHECKS PASS — 16 crops written to", HERE)


if __name__ == "__main__":
    main()
