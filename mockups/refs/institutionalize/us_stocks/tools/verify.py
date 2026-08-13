#!/usr/bin/env python3
"""Reconciliation harness for the Prophet Board mockup (MP-1 gate G-C evidence).

Checks the acceptance properties that are mechanically checkable, against the
RENDERED page rather than against the source — so it fails if the markup drifts
from the payload:

  A. two-total law      six live cells == lifecycle_live_total == open_count;
                        all seven == lifecycle_grand_total == active_count
  B. chip-count law     for every ladder filter, rendered cards + quoted "+N"
                        == that cell's count, exactly, with no remainder;
                        table view renders the cell in full
  C. resolved is out    no resolved card in the unfiltered grid; the headline
                        equals the live total, not the grand total
  D. stage retirement   no user-facing "stage"/"阶段", no "#stage=" anywhere
  E. rail retirement    no four-dot rail; at most one lane mark per card;
                        no "recovery" chip
  F. one-referent law   no lifecycle cell word (EN or ZH) inside Candidates
  G. no direction ink   no lifecycle mark resolves to an --up/--down colour,
                        in either language
  H. 390w               no horizontal page scroll, seven cells in a 4+3 wrap
  I. anonymous          exactly one card's data in the DOM, zero locked rows

Usage: python3 tools/verify.py [base_url]
Exit 0 = every check passed.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8791"
CELLS = ["watch", "ready", "entered", "delivering", "overtime", "invalidated", "resolved"]
LIVE = CELLS[:6]

# the ruled lexicon — both languages, for the one-referent sweep
WORDS_EN = ["Watch", "Ready", "Entered", "Delivering", "Overtime", "Invalidated", "Resolved"]
WORDS_ZH = ["观察", "就绪", "入场", "达标", "超时", "失效", "已结"]

fails, checks = [], []


def ok(name, cond, detail=""):
    checks.append((bool(cond), name, detail))
    if not cond:
        fails.append(f"{name} — {detail}")


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()

        def page_at(q, w=1440, h=900):
            pg = br.new_page(viewport={"width": w, "height": h})
            pg.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            pg.wait_for_timeout(150)
            return pg

        # ── A. two-total law ────────────────────────────────────────────────
        pg = page_at("theme=dark&lang=en&state=paid")
        B = pg.evaluate("() => window.BOARD")
        painted = pg.evaluate(
            "() => Object.fromEntries([...document.querySelectorAll('.mx-cell')]"
            ".map(c => [c.dataset.life, c.querySelector('.mx-cell-n').textContent.trim()]))")
        headline = int(pg.inner_text(".ladder-n").strip())

        live_sum = sum(B["counts"][k] for k in LIVE)
        ok("A1 six live cells == lifecycle_live_total",
           live_sum == B["live_total"], f"{live_sum} vs {B['live_total']}")
        ok("A2 lifecycle_live_total == open_count",
           B["live_total"] == B["open_count"], f"{B['live_total']} vs {B['open_count']}")
        ok("A3 all seven == grand_total == active_count",
           live_sum + B["counts"]["resolved"] == B["grand_total"] == B["active_count"],
           f"{live_sum + B['counts']['resolved']} / {B['grand_total']} / {B['active_count']}")
        ok("A4 headline == live total (not grand)",
           headline == B["live_total"], f"headline {headline} vs {B['live_total']}")
        for k in CELLS:
            exp = "—" if (k == "watch" and not B["watch_key_present"]) else str(B["counts"][k])
            ok(f"A5 painted cell {k} == payload", painted.get(k) == exp,
               f"painted {painted.get(k)!r} vs {exp!r}")
        ok("A6 watch key absent renders a dash, never 0",
           painted.get("watch") == "—" if not B["watch_key_present"] else True,
           f"painted {painted.get('watch')!r}")

        # ── C. resolved is outside the default grid ────────────────────────
        res_default = pg.evaluate(
            "() => [...document.querySelectorAll('.pvcard')].filter(c=>c.dataset.life==='resolved').length")
        ok("C1 no resolved card in the unfiltered grid", res_default == 0, str(res_default))
        pg.close()

        # ── B. chip-count law, every cell, grid AND table ──────────────────
        for k in CELLS:
            pg = page_at(f"theme=dark&lang=en&state=paid&life={k}")
            n = B["counts"][k]
            got = pg.evaluate("""() => {
                const cards = document.querySelectorAll('.pvcard').length;
                const m = document.querySelector('.pv-more');
                const more = m ? parseInt((m.textContent.match(/\\d+/)||[0])[0],10) : 0;
                return {cards, more};
            }""")
            if n == 0:
                ok(f"B-grid {k} (0) shows a stated empty state, not a hole",
                   pg.query_selector(".mx-empty") is not None, "no .mx-empty")
            else:
                ok(f"B-grid {k}: cards + '+N' == cell count",
                   got["cards"] + got["more"] == n,
                   f"{got['cards']}+{got['more']} vs {n}")
            pg.close()

            pg = page_at(f"theme=dark&lang=en&state=paid&life={k}&view=table")
            rows = pg.evaluate("() => document.querySelectorAll('.st-table tbody tr').length")
            ok(f"B-table {k}: rendered rows == cell count, no remainder",
               rows == n, f"{rows} vs {n}")
            pg.close()

        # ── D/E/F. vocabulary + rail sweeps, both languages ────────────────
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=paid")
            txt = pg.evaluate("() => document.getElementById('board').innerText")
            html = pg.evaluate("() => document.getElementById('board').innerHTML")

            # Anti-vacuity: every absence check below passes trivially if the text
            # it reads is empty. Pin that the sweep is actually looking at a
            # rendered board, and that innerText really is language-filtered —
            # otherwise D/E/F are receipts that cannot fail.
            other = "观察" if lang == "en" else "Watch"
            ok(f"D0[{lang}] sweep reads a populated board",
               len(txt) > 2000 and "Prophet" in txt, f"len={len(txt)}")
            ok(f"D0b[{lang}] innerText is language-filtered (no {other!r})",
               other not in txt, f"found the other language's word {other!r}")

            ok(f"D1[{lang}] no user-facing 'stage'",
               "stage" not in txt.lower(), "found 'stage' in rendered text")
            ok(f"D2[{lang}] no user-facing '阶段'", "阶段" not in txt, "found 阶段")
            ok(f"D3[{lang}] no '#stage=' anywhere", "#stage=" not in html, "found #stage=")
            ok(f"D4[{lang}] fragment vocabulary is #life=",
               "#life=" in html or "data-life" in html, "no #life=/data-life")

            ok(f"E1[{lang}] no four-dot rail",
               pg.query_selector(".pv-stp") is None and pg.query_selector(".pv-dot") is None,
               "rail classes present")
            ok(f"E2[{lang}] at most one lane mark per card",
               pg.evaluate("() => [...document.querySelectorAll('.pvcard')]"
                           ".every(c => c.querySelectorAll('.pv-mark').length <= 1)"),
               "a card carries >1 .pv-mark")
            ok(f"E3[{lang}] no recovery chip",
               "recovery" not in txt.lower() and "复苏" not in txt, "found a recovery chip")

            # F. one-referent-per-page: no cell word inside the Candidates section
            cand = pg.evaluate("() => document.getElementById('candidates').innerText")
            words = WORDS_ZH if lang == "zh" else WORDS_EN
            hits = [w for w in words if w in cand]
            # anti-vacuity: the section must actually carry its shelf vocabulary,
            # otherwise "no cell word here" is true because there is no text here
            shelf = "筛出" if lang == "zh" else "screened"
            ok(f"F0[{lang}] Candidates section is populated",
               len(cand) > 200 and shelf in cand, f"len={len(cand)}")
            ok(f"F1[{lang}] no lifecycle cell word inside Candidates",
               not hits, f"found {hits}")

            # G. no direction ink on any lifecycle mark
            inks = pg.evaluate("""() => {
              const up = getComputedStyle(document.documentElement).getPropertyValue('--up').trim();
              const dn = getComputedStyle(document.documentElement).getPropertyValue('--down').trim();
              const hex = h => { h=h.replace('#',''); return 'rgb(' + [0,2,4].map(i=>parseInt(h.substr(i,2),16)).join(', ') + ')'; };
              const bad = [hex(up), hex(dn)];
              return [...document.querySelectorAll('.mx-cap, .mx-mark')].filter(e => {
                const g = getComputedStyle(e), b = getComputedStyle(e, '::before');
                return bad.some(c => (g.color+b.backgroundColor+b.backgroundImage+b.borderTopColor).includes(c));
              }).length;
            }""")
            ok(f"G1[{lang}] no lifecycle mark uses a direction ink", inks == 0, f"{inks} marks")
            pg.close()

        # ── H. 390w ────────────────────────────────────────────────────────
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=paid", 390, 844)
            m = pg.evaluate("""() => {
              const de = document.documentElement;
              const cells = [...document.querySelectorAll('.mx-cell')];
              const tops = [...new Set(cells.map(c => Math.round(c.getBoundingClientRect().top)))];
              const perRow = tops.map(t => cells.filter(c => Math.round(c.getBoundingClientRect().top) === t).length);
              return {sw: de.scrollWidth, cw: de.clientWidth, cells: cells.length, perRow};
            }""")
            ok(f"H1[{lang}] no horizontal page scroll at 390w",
               m["sw"] <= m["cw"], f"scrollWidth {m['sw']} > clientWidth {m['cw']}")
            ok(f"H2[{lang}] seven cells visible at 390w", m["cells"] == 7, str(m["cells"]))
            ok(f"H3[{lang}] ladder wraps 4+3 at 390w",
               m["perRow"] == [4, 3], str(m["perRow"]))
            pg.close()

        # ── I. anonymous: no leaked rows ───────────────────────────────────
        pg = page_at("theme=dark&lang=en&state=anon")
        leak = pg.evaluate("""() => {
          const html = document.getElementById('board').innerHTML;
          const shown = new Set([...document.querySelectorAll('.pvcard')].map(c=>c.dataset.ticker));
          const candTk = new Set((window.BOARD.cand_rows||[]).slice(0,6).map(r=>r.tk));
          const leaked = [...new Set(window.BOARD.rows.map(r=>r.tk))]
            .filter(tk => !shown.has(tk) && !candTk.has(tk))
            .filter(tk => new RegExp('\\\\b'+tk+'\\\\b').test(html));
          return {shown:[...shown], leaked,
                  ghostText:[...document.querySelectorAll('.pv-ghost')].map(g=>g.textContent.trim()).join('')};
        }""")
        ok("I1 anonymous renders exactly one card's data", len(leak["shown"]) == 1, str(leak["shown"]))
        ok("I2 zero withheld setup rows in the DOM", not leak["leaked"], str(leak["leaked"][:6]))
        ok("I3 locked placeholders carry no content", leak["ghostText"] == "", "ghosts have text")
        pg.close()

        br.close()

    width = max(len(n) for _, n, _ in checks)
    for good, name, detail in checks:
        print(f"{'PASS' if good else 'FAIL'}  {name.ljust(width)}  {detail if not good else ''}".rstrip())
    print(f"\n{sum(1 for g,_,_ in checks if g)}/{len(checks)} checks passed")
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
