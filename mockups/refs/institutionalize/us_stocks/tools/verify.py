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
import re
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
        pg = page_at("theme=dark&lang=en&state=today")
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
            pg = page_at(f"theme=dark&lang=en&state=today&life={k}")
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

            pg = page_at(f"theme=dark&lang=en&state=today&life={k}&view=table")
            rows = pg.evaluate("() => document.querySelectorAll('.st-table tbody tr').length")
            ok(f"B-table {k}: rendered rows == cell count, no remainder",
               rows == n, f"{rows} vs {n}")
            pg.close()

        # ── D/E/F. vocabulary + rail sweeps, both languages ────────────────
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=today")
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
            if lang == "zh":
                # A latin word wedged into a Chinese sentence is the tell of
                # English-shaped copy (shipped once as "是production迁移前的…").
                # Product nouns and tickers are legitimate; lowercase prose is not.
                bad = re.findall(r"[\u4e00-\u9fff][a-z]{4,}|[a-z]{4,}[\u4e00-\u9fff]", txt)
                ok("D5[zh] no latin prose word wedged inside Chinese copy",
                   not bad, f"found {sorted(set(bad))[:5]}")
            ok(f"D3[{lang}] no '#stage=' anywhere", "#stage=" not in html, "found #stage=")
            ok(f"D4[{lang}] fragment vocabulary is #life=",
               "#life=" in html or "data-life" in html, "no #life=/data-life")

            ok(f"E1[{lang}] no four-dot rail",
               pg.query_selector(".pv-stp") is None and pg.query_selector(".pv-dot") is None,
               "rail classes present")
            lanes = pg.evaluate("() => [...document.querySelectorAll('.pvcard')]"
                                ".map(c => c.querySelectorAll('.pv-mk-lane').length)")
            ok(f"E2a[{lang}] the lane mark selector actually matches something",
               sum(lanes) > 0, "no .pv-mk-lane on any card — check is vacuous")
            ok(f"E2b[{lang}] at most one lane mark per card",
               all(n <= 1 for n in lanes), f"max {max(lanes) if lanes else 0}")
            ok(f"E3[{lang}] no recovery chip",
               "recovery" not in txt.lower() and "复苏" not in txt, "found a recovery chip")

            # ── the revised card contract (G-C amalgamation) ─────────────────
            cardm = pg.evaluate("""() => {
              const cards = [...document.querySelectorAll('.pvcard')];
              return {
                n: cards.length,
                charts: cards.filter(c => c.querySelector('.pv-chart svg')).length,
                fallbacks: cards.filter(c => c.querySelector('.pv-nochart')).length,
                stance: cards.filter(c => c.querySelector('.pv-chip')).length,
                quote: cards.filter(c => c.querySelector('.pv-px')).length,
                chg: cards.filter(c => c.querySelector('.pv-chg')).length,
                pri: cards.filter(c => c.querySelector('.pv-prin')).length,
                life: cards.filter(c => c.querySelector('.pv-life-w')).length,
                zone: cards.filter(c => c.querySelector('.pv-zn')).length,
                maxMarks: Math.max(...cards.map(c => c.querySelectorAll('.pv-mk-i').length)),
                text: cards.map(c => c.innerText).join(' '),
                full: cards.filter(c => !c.classList.contains('pvcard--compact')),
                nFull: cards.filter(c => !c.classList.contains('pvcard--compact')).length,
                fullPri: cards.filter(c => !c.classList.contains('pvcard--compact')
                                        && c.querySelector('.pv-prin')).length,
                nCompact: cards.filter(c => c.classList.contains('pvcard--compact')).length,
                compactIdentified: cards.filter(c => c.classList.contains('pvcard--compact')
                                        && c.querySelector('.pv-tk') && c.querySelector('.pv-life-w')).length
              };
            }""")
            # AMENDED at R4. The original asserted EVERY card carries a priority
            # number. That was true only because GRID_CAP=40 hid the null-priority
            # tail: PRC-306 makes all 159 live rows reachable, and 65 of them have
            # no chart, no quote, no stance and no priority. VTC-308 rules that
            # such rows take the COMPACT form rather than a full card repeating
            # "PRIORITY —", so the priority slot is deliberately absent there.
            # The guard keeps its force by splitting on the form instead of being
            # relaxed: a full-form card must still carry all three, and a compact
            # card must still identify itself (ticker + lifecycle) rather than
            # being a shape with nothing in it.
            ok(f"K1[{lang}] every FULL-form card carries priority, lifecycle and a zone footer",
               cardm["fullPri"] == cardm["nFull"] and cardm["life"] == cardm["n"]
               and cardm["zone"] == cardm["n"],
               f"fullPri {cardm['fullPri']}/{cardm['nFull']} · "
               f"life {cardm['life']} zone {cardm['zone']} of {cardm['n']}")
            ok(f"K1b[{lang}] every COMPACT card still names itself and its lifecycle",
               cardm["compactIdentified"] == cardm["nCompact"],
               f"{cardm['compactIdentified']}/{cardm['nCompact']} identified")
            ok(f"K2[{lang}] both enriched and fallback cards are on screen",
               cardm["charts"] > 0 and cardm["fallbacks"] > 0,
               f"charts {cardm['charts']} fallbacks {cardm['fallbacks']}")
            ok(f"K3[{lang}] a quote always carries its change read",
               cardm["chg"] == cardm["quote"], f"quote {cardm['quote']} chg {cardm['chg']}")
            ok(f"K4[{lang}] marks stay restrained (<= 3 per card)",
               cardm["maxMarks"] <= 3, f"max {cardm['maxMarks']}")
            # handoff §6: plan-clock telemetry and paragraph copy are OFF the card
            ok(f"K5[{lang}] no plan-clock telemetry on the card",
               not re.search(r"day \d+ of \d+|past its \d+-day|第 \d+ 天", cardm["text"]),
               "found day-of-horizon copy")
            ok(f"K6[{lang}] no execution-command copy on the card",
               not re.search(r"No entry above|Buy exactly|Must exit|不要在.*之上买入", cardm["text"]),
               "found an execution instruction")
            ok(f"K7[{lang}] no Entry/T1/Void geometry row on the card",
               not re.search(r"\bT1\b|\bVoid\b|失效价|目标一", cardm["text"]),
               "found the three-number footer")

            # ── stance ruling (operator 2026-08-13) ──────────────────────────
            st = pg.evaluate("""() => {
              const cards = [...document.querySelectorAll('.pvcard')];
              const chip = c => (c.querySelector('.pv-chip') || {}).textContent || '';
              return {
                n: cards.length,
                noread: cards.filter(c => c.querySelector('.pv-chip--noread')).length,
                hued:   cards.filter(c => c.className.match(/pv-(buy|near|wait|hold|avoid)\\b/)).length,
                // a BLOCKED_DATA card must never also carry a stance hue class
                leaked: cards.filter(c => c.querySelector('.pv-chip--noread') &&
                                          c.className.match(/pv-(buy|near|wait|hold|avoid)\\b/)).length,
                chips: [...new Set(cards.map(chip).filter(Boolean))]
              };
            }""")
            ok(f"L1[{lang}] BLOCKED_DATA rows render a disclosed no-read chip",
               st["noread"] > 0, "no .pv-chip--noread rendered — check is vacuous")
            ok(f"L2[{lang}] a no-read card never also carries a stance hue",
               st["leaked"] == 0, f"{st['leaked']} cards carry both")
            ok(f"L3[{lang}] no sixth TRIM verb on the Board",
               not re.search(r"TRIM|减仓", " ".join(st["chips"])), f"chips {st['chips']}")
            ok(f"L4[{lang}] the internal token never reaches the user",
               "blocked_data" not in txt.lower() and "BLOCKED_DATA" not in html,
               "found the internal token in user-facing text")
            pg.close()

        # ── the stance projection is factored from the ENGINE's buckets ──────
        # (source-level: a display mapping that drifts from its producer becomes an
        #  independent unowned semantic — exactly what the ruling forbids)
        # tools/verify.py -> us_stocks -> institutionalize -> refs -> mockups -> repo root
        import pathlib as _pl
        eng = (_pl.Path(__file__).resolve().parents[5] / "engine" / "us_board_rank.py")
        gen = (_pl.Path(__file__).resolve().parent / "gen_fixture.py")
        # FAIL CLOSED. A missing source must not silently skip this block — an
        # absent check reads as a passing check, which is how M1-M4 sat dark.
        ok("M0 the engine + generator sources are readable",
           eng.exists() and gen.exists(), f"engine={eng.exists()} gen={gen.exists()} ({eng})")
        if eng.exists() and gen.exists():
            esrc, gsrc = eng.read_text(), gen.read_text()

            def _bucket(name):
                m = re.search(name + r"\s*=\s*frozenset\(\(([^)]*)\)\)", esrc)
                return {x.strip().strip("\"'") for x in m.group(1).split(",") if x.strip()} if m else set()

            mapping = {}
            mm = re.search(r"STANCE_BY_STATUS\s*=\s*\{(.*?)\}", gsrc, re.S)
            for k, v in re.findall(r'"([a-z_]+)"\s*:\s*"([a-z_]+)"', mm.group(1) if mm else ""):
                mapping[k] = v
            exp = {"_LIVE_STATUSES": {"buy", "near"}, "_SETTING_UP_STATUSES": {"wait"},
                   "_RAN_STATUSES": {"hold"}, "_BLOCKED_STATUSES": {"avoid"}}
            for bname, verbs in exp.items():
                vals = _bucket(bname)
                ok(f"M1 {bname} is fully mapped by the stance projection",
                   vals and all(s in mapping for s in vals),
                   f"unmapped: {sorted(s for s in vals if s not in mapping)}")
                ok(f"M2 {bname} projects only to {sorted(verbs)}",
                   {mapping.get(s) for s in vals} <= verbs,
                   f"got {sorted({mapping.get(s) for s in vals})}")
            # Target the code path, not the prose: the file documents the
            # prohibition in a comment, so a bare substring match self-trips.
            # Strip comments and docstrings, then look for an actual field read.
            code = re.sub(r"#.*", "", gsrc)
            code = re.sub(r'"""(?:.|\n)*?"""', "", code)
            reads = re.findall(r'(?:get\(\s*["\']recommended_action["\']|\.recommended_action|'
                               r'\[\s*["\']recommended_action["\']\s*\])', code)
            ok("M3 the projection never reads the management engine's recommended_action",
               not reads, f"{len(reads)} live read(s) of recommended_action in gen_fixture.py")
            ok("M4 no sixth verb in the projection",
               set(mapping.values()) <= {"buy", "near", "wait", "hold", "avoid"},
               f"verbs {sorted(set(mapping.values()))}")

        # ── G. lifecycle ink + the stance token family, BOTH languages ───────
        # (G3/G4 are zh-only, so this loop must cover zh or they never run)
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=paid")

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

            # G2/G3: the stance family must EXIST (an undefined --pv-* silently
            # falls back and paints the wrong stance colour), and under zh it must
            # flip with the direction convention exactly as theme.css does.
            tok = pg.evaluate("""() => {
              const g = getComputedStyle(document.documentElement);
              const v = k => g.getPropertyValue(k).trim();
              return {buy: v('--pv-buy'), near: v('--pv-near'), wait: v('--pv-wait'),
                      hold: v('--pv-hold'), avoid: v('--pv-avoid'),
                      up: v('--up'), down: v('--down'),
                      chip: (() => { const c = document.querySelector('.pv-buy .pv-chip');
                                     return c ? getComputedStyle(c).backgroundColor : ''; })()};
            }""")
            ok(f"G2[{lang}] the --pv-* stance family is defined",
               all(tok[k] for k in ("buy", "near", "wait", "hold", "avoid")),
               f"undefined: {[k for k in ('buy','near','wait','hold','avoid') if not tok[k]]}")
            if lang == "zh":
                # The zh FLIP is asserted by G4 below, on the RENDERED chip: the raw
                # custom-property value has already substituted var(--up), so there is
                # no textual derivation left to test here.
                # The chip may compute to rgb(), rgba() or color(srgb ...) depending
                # on whether color-mix was involved. Assert the SEMANTIC fact — a zh
                # Buy chip is RED (red channel dominates) — not a literal string.
                _n = [float(x) for x in re.findall(r"[0-9.]+", tok["chip"] or "")][:3]
                if _n and max(_n) <= 1.0:
                    _n = [v * 255 for v in _n]
                ok("G4[zh] a rendered Buy chip is painted red (the zh up-ink)",
                   len(_n) == 3 and _n[0] > _n[1] + 40 and _n[0] > _n[2] + 40,
                   f"chip {tok['chip']!r} -> rgb{tuple(round(v) for v in _n)}")
            pg.close()

        # ── R3. the RIG R2 revise mandate (A-E + the G-D display defect) ────
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=paid")

            # C: ONE universe. `paid` and `today` must render the same population
            # — a view-specific exemption IS the count-law contradiction.
            here = pg.evaluate("() => [...document.querySelectorAll('.pvcard')].map(c=>c.dataset.id)")
            pg2 = page_at(f"theme=dark&lang={lang}&state=today")
            there = pg2.evaluate("() => [...document.querySelectorAll('.pvcard')].map(c=>c.dataset.id)")
            pg2.close()
            ok(f"R-C1[{lang}] paid and today render one identical population",
               here == there and len(here) > 0, f"{len(here)} vs {len(there)}")
            recon = pg.evaluate("""() => {
              const m = document.querySelector('.pv-more');
              const more = m ? parseInt((m.textContent.match(/\\d+/)||[0])[0],10) : 0;
              return {cards: document.querySelectorAll('.pvcard').length, more,
                      head: parseInt(document.querySelector('.ladder-n').textContent.trim(),10),
                      total: (document.querySelector('.mx-sec-total')||{}).textContent||''};
            }""")
            ok(f"R-C2[{lang}] rendered + '+N' == the live headline",
               recon["cards"] + recon["more"] == recon["head"],
               f"{recon['cards']}+{recon['more']} vs {recon['head']}")
            ok(f"R-C3[{lang}] the section total states the canonical population",
               str(recon["head"]) in recon["total"], f"total={recon['total']!r}")

            # A: the risk ledger is CARRIED and REACHABLE
            cau = pg.evaluate("""() => {
              const pills = [...document.querySelectorAll('.pv-cau')];
              return {n: pills.length,
                      withRows: pills.filter(p => p.querySelectorAll('.pv-cau-row').length > 0).length,
                      focusable: pills.filter(p => p.hasAttribute('tabindex')).length,
                      counted: pills.filter(p => /\\d/.test((p.querySelector('.pv-cau-btn')||{}).textContent||'')).length};
            }""")
            ok(f"R-A1[{lang}] the caution carrier exists on the board",
               cau["n"] > 0, "no .pv-cau rendered — capability absent again")
            ok(f"R-A2[{lang}] every caution pill carries its sentences",
               cau["withRows"] == cau["n"], f"{cau['withRows']} of {cau['n']}")
            ok(f"R-A3[{lang}] every caution pill is keyboard-reachable and counted",
               cau["focusable"] == cau["n"] and cau["counted"] == cau["n"],
               f"focusable {cau['focusable']} counted {cau['counted']} of {cau['n']}")

            # B: zone geography must not read as an instruction on a non-actionable card
            zone = pg.evaluate("""() => {
              const bad = [], seen = {};
              document.querySelectorAll('.pvcard').forEach(c => {
                const m = c.className.match(/pv-(buy|near|wait|hold|avoid|noread)\\b/);
                const st = m ? m[1] : 'none';
                const active = !!c.querySelector('.pv-znr');
                seen[st] = seen[st] || {active:0, quiet:0};
                active ? seen[st].active++ : seen[st].quiet++;
                if (active && ['wait','hold','avoid','noread'].includes(st)) bad.push(c.dataset.ticker);
              });
              return {bad, seen};
            }""")
            ok(f"R-B1[{lang}] no non-actionable card renders the active buy-zone treatment",
               not zone["bad"], f"{zone['bad'][:5]}")
            ok(f"R-B2[{lang}] the active treatment is actually used somewhere",
               (zone["seen"].get("buy", {}).get("active", 0)
                + zone["seen"].get("near", {}).get("active", 0)) > 0,
               f"{zone['seen']}")

            # D: no producer-less market assertions; Groups bound with lineage
            surf = pg.evaluate("() => document.getElementById('board').innerText")
            claims = [w for w in ("Risk-on", "Broadening", "Act on the best few",
                                  "偏好风险", "扩散中", "择优出手") if w in surf]
            ok(f"R-D1[{lang}] no authored regime/posture claim on the board",
               not claims, f"found {claims}")
            grp = pg.evaluate("""() => ({
              n: document.querySelectorAll('.grp').length,
              lineage: document.getElementById('groups').innerText
            })""")
            ok(f"R-D2[{lang}] Groups is bound to the theme producer",
               grp["n"] > 0, "no .grp rendered")
            ok(f"R-D3[{lang}] Groups states its lineage (as-of)",
               ("as of" in grp["lineage"] or "数据日期" in grp["lineage"]), "no as-of stamp")

            # E: Featured is an aura pinned to --pv-buy, not a bare ring
            feat = pg.evaluate("""() => {
              const c = document.querySelector('.pvcard.pv-featured');
              if (!c) return null;
              const g = getComputedStyle(c);
              // count SHADOW LAYERS, not rgba() tokens: modern colours serialise
              // as color(srgb ...) and an rgba-only match under-counts to 1.
              const layers = (g.boxShadow.match(/\\d+px/g)||[]).length ? g.boxShadow.split(/,(?![^(]*\\))/).length : 0;
              return {shadow: g.boxShadow, layers: layers,
                      inset: g.boxShadow.includes('inset'), bg: g.backgroundColor,
                      rail: !!getComputedStyle(c, '::before').content};
            }""")
            ok(f"R-E1[{lang}] Featured renders the ratified aura, not a bare ring",
               feat and feat["layers"] >= 3 and not feat["inset"],
               f"{(feat or {}).get('layers')} layers inset={(feat or {}).get('inset')}")

            # E: stance ink must be distinguishable from the direction ink
            inks = pg.evaluate("""() => {
              const g = getComputedStyle(document.documentElement);
              const norm = v => { const n=(v.match(/[0-9.]+/g)||[]).slice(0,3).map(Number);
                                  return n.length===3 ? (Math.max(...n)<=1 ? n.map(x=>Math.round(x*255)) : n.map(Math.round)) : null; };
              const probe = k => { const d=document.createElement('div'); d.style.color='var('+k+')';
                                   document.body.appendChild(d); const c=getComputedStyle(d).color;
                                   d.remove(); return norm(c); };
              return {buy: probe('--pv-buy'), up: probe('--up'),
                      avoid: probe('--pv-avoid'), down: probe('--down')};
            }""")
            def dist(a, b):
                return a and b and sum(abs(x - y) for x, y in zip(a, b)) >= 24
            ok(f"R-E2[{lang}] the Buy stance ink differs from the direction up-ink",
               dist(inks["buy"], inks["up"]), f"buy={inks['buy']} up={inks['up']}")
            ok(f"R-E3[{lang}] the Avoid stance ink differs from the direction down-ink",
               dist(inks["avoid"], inks["down"]), f"avoid={inks['avoid']} down={inks['down']}")
            pg.close()

        # E: 390w must expose a real opportunity card above the first fold
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=paid", 390, 844)
            m = pg.evaluate("""() => {
              const F = 844;
              // AMENDED at R4. `bottom <= F` is TRUE for a display:none card,
              // whose rect is all zeros — so once PRC-306 put the whole partition
              // in the DOM with the overflow hidden, this counted 120 "whole cards
              // above the fold" at 390w instead of 1. It still passed, which is
              // worse than failing: the guard stopped measuring anything while
              // still reporting green. A card counts only if it is laid out, has
              // real height, and actually ends above the fold.
              const cs = [...document.querySelectorAll('.pvcard')]
                .filter(c => c.offsetParent !== null);
              const full = cs.filter(c => {
                const r = c.getBoundingClientRect();
                return r.height > 40 && r.top >= 0 && r.bottom <= F;
              }).length;
              const de = document.documentElement;
              const cells = [...document.querySelectorAll('.mx-cell')];
              const tops = [...new Set(cells.map(c => Math.round(c.getBoundingClientRect().top)))];
              return {full, cells: cells.length,
                      perRow: tops.map(t => cells.filter(c => Math.round(c.getBoundingClientRect().top)===t).length),
                      sw: de.scrollWidth, cw: de.clientWidth};
            }""")
            ok(f"R-E4[{lang}] 390w shows >=1 whole opportunity card above the fold",
               m["full"] >= 1, f"{m['full']} cards")
            ok(f"R-E5[{lang}] the count ladder is not broken to achieve it",
               m["cells"] == 7 and m["perRow"] == [4, 3], f"{m['cells']} cells {m['perRow']}")
            ok(f"R-E6[{lang}] still no horizontal page scroll at 390w",
               m["sw"] <= m["cw"], f"{m['sw']} > {m['cw']}")
            pg.close()

        # G-D display defect: the duplicated `enriched` declaration is gone
        import pathlib as _pl2
        _bj = (_pl2.Path(__file__).resolve().parents[1] / "board.js").read_text()
        ok("R-GD1 no duplicate `enriched` declaration in board.js",
           _bj.count("var enriched") == 0, f"{_bj.count('var enriched')} declarations remain")
        # Scope to ONE function body — `var h` legitimately recurs across functions;
        # what must never recur is a declaration inside a single scope, which is how
        # `enriched` came to hold two different formulas in the same function.
        #
        # AMENDED at R4. This used to slice `setups()` as "everything up to
        # `function candidates()`", which is only equivalent to one function body
        # while nothing sits between the two. R4 added smCount()/showMore() there
        # (PRC-306), so the slice swallowed a second function and reported its
        # `var h` as a duplicate of setups()'s — a FALSE POSITIVE that would have
        # been "fixed" by renaming an innocent variable. It was also the mirror
        # failure: reorder the file and a genuine duplicate escapes the slice.
        # Now brace-matched, so the scope is the actual function body.
        def _body(src, sig):
            i = src.index(sig)
            b = src.index("{", i)
            depth, j = 0, b
            while j < len(src):
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return src[b:j + 1]
                j += 1
            raise AssertionError(f"unbalanced braces scanning {sig}")

        _fn = _body(_bj, "function setups()")
        # a nested function is its own scope; strip them so only setups()'s own
        # declarations are compared
        _own = re.sub(r"function\s*\([^)]*\)\s*\{", "{", _fn)
        _depth0, _out, _d = 0, [], 0
        for _ch in _own:
            if _ch == "{":
                _d += 1
            if _d <= 1:
                _out.append(_ch)
            if _ch == "}":
                _d -= 1
        _top = "".join(_out)
        _dupes = [n for n in set(re.findall(r"\bvar ([A-Za-z_$][\w$]*)\s*=", _top))
                  if len(re.findall(r"\bvar " + re.escape(n) + r"\s*=", _top)) > 1]
        ok("R-GD2 no variable is declared twice inside setups()",
           not _dupes, f"duplicated: {sorted(_dupes)[:6]}")

        # ── N8: board-level facts are invariant across lenses ───────────────
        # "What changed today" is a fact about the plan book, so it may not move
        # with whatever subset a view happens to render.
        import re as _re
        seen = {}
        for st in ("paid", "today", "fallback"):
            pg = page_at(f"theme=dark&lang=en&state={st}")
            el = pg.query_selector(".chg-strip")
            if el:
                m = _re.search(r"(\d+)", el.inner_text())
                seen[st] = int(m.group(1)) if m else None
            pg.close()
        ok("N8 'what changed today' is identical across every lens",
           len(set(v for v in seen.values() if v is not None)) == 1, str(seen))

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
