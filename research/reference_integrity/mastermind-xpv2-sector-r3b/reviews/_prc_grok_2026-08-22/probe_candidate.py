#!/usr/bin/env python3
"""Independent product-regression probe of the frozen R3B Sector Central candidate.

Does not import the author's verify_reference.py. Serves the candidate over HTTP
and drives Playwright against real hash routing, access states, and the six
customer workflows.
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[5]
CANDIDATE = ROOT / (
    "mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/"
    "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
)
OUT = Path(__file__).resolve().parent
SHOTS = OUT / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

CANONICAL = ["overview", "map", "moving", "money", "explore", "confluence"]
LEGACY = {
    "actnow-section": "overview",
    "regime": "overview",
    "grader": "overview",
    "si-map": "map",
    "rotmap-section": "map",
    "sc-cyclemap": "map",
    "board": "map",
    "si-movement": "moving",
    "rc-events-mount": "moving",
    "rotation-app": "moving",
    "si-money": "money",
    "internals-section": "money",
    "scc-leadership": "money",
    "explore-section": "explore",
    "table-section": "explore",
    "chart-section": "explore",
    "forming-narratives": "explore",
    "tm-mount": "explore",
    "confluence": "confluence",
    "sc-app": "confluence",
    "sc-top": "confluence",
}


def start_server(directory: Path) -> tuple[socketserver.TCPServer, str]:
    os.chdir(directory)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    httpd.allow_reuse_address = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    return httpd, f"http://127.0.0.1:{port}/{CANDIDATE.name}"


def js_eval(page, script: str, *args):
    return page.evaluate(script, *args)


def dump_view(page) -> dict:
    return js_eval(
        page,
        """() => {
          const views = [...document.querySelectorAll('section.si-view')].map(s => {
            const cs = getComputedStyle(s);
            const r = s.getBoundingClientRect();
            return {
              view: s.getAttribute('data-view'),
              on: s.classList.contains('on'),
              display: cs.display,
              visibility: cs.visibility,
              w: Math.round(r.width),
              h: Math.round(r.height),
              top: Math.round(r.top)
            };
          });
          const sticky = document.querySelector('.si-topbar, .si-side, header, .r3-sticky');
          const bar = document.querySelector('.si-topbar');
          const rail = document.querySelector('nav.si-side');
          const offset = getComputedStyle(document.documentElement)
            .getPropertyValue('--ref-sticky-offset').trim();
          const text = (el) => (el ? el.innerText.replace(/\\s+/g,' ').trim().slice(0, 4000) : '');
          const on = views.find(v => v.on);
          const onEl = document.querySelector('section.si-view.on');
          const navs = [...document.querySelectorAll('a[data-ref-nav], a[href]')].slice(0, 400)
            .map(a => ({
              href: a.getAttribute('href'),
              ref: a.hasAttribute('data-ref-nav'),
              text: (a.innerText||'').replace(/\\s+/g,' ').trim().slice(0,80),
              inOn: !!(onEl && onEl.contains(a)),
              display: getComputedStyle(a).display
            }));
          return {
            hash: location.hash,
            title: document.title,
            lang: document.documentElement.getAttribute('data-lang') || document.documentElement.lang,
            views,
            onView: on ? on.view : null,
            stickyOffset: offset,
            topbarH: bar ? Math.round(bar.getBoundingClientRect().height) : null,
            railH: rail ? Math.round(rail.getBoundingClientRect().height) : null,
            railLabel: rail ? rail.getAttribute('aria-label') : null,
            access: (window.REF && REF.accessState) || null,
            log: (window.REF && REF.log) ? REF.log.slice(-40) : [],
            registryKeys: (window.REF && REF.registry) ? Object.keys(REF.registry) : [],
            fragmentKeys: (window.REF && REF.fragments) ? Object.keys(REF.fragments) : [],
            visibleText: text(onEl),
            bodyTextHead: text(document.body).slice(0, 1500)
          };
        }""",
    )


def measure_target(page, target_id: str) -> dict:
    return js_eval(
        page,
        """(id) => {
          const el = document.getElementById(id);
          if (!el) return {id, present: false};
          const r = el.getBoundingClientRect();
          const bar = document.querySelector('.si-topbar');
          const rail = document.querySelector('nav.si-side');
          const stickyH = (bar ? bar.getBoundingClientRect().height : 0)
            + ((rail && getComputedStyle(rail).position === 'sticky')
                ? rail.getBoundingClientRect().height : 0);
          const cs = getComputedStyle(el);
          return {
            id,
            present: true,
            top: Math.round(r.top),
            height: Math.round(r.height),
            scrollY: Math.round(window.scrollY),
            stickyH: Math.round(stickyH),
            occluded: r.top < stickyH - 2 && r.bottom > 0,
            scrollMarginTop: cs.scrollMarginTop,
            inView: r.top >= -2 && r.top < window.innerHeight
          };
        }""",
        target_id,
    )


def main() -> None:
    assert CANDIDATE.is_file(), CANDIDATE
    httpd, url = start_server(CANDIDATE.parent)
    report: dict = {
        "candidate": str(CANDIDATE),
        "url": url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "canonical": [],
        "legacy": [],
        "special": {},
        "access": {},
        "tasks": {},
        "destinations": {},
        "console": [],
        "pageerrors": [],
    }
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda m: report["console"].append(
                {"type": m.type, "text": m.text[:400]}
            ))
            page.on("pageerror", lambda e: report["pageerrors"].append(str(e)[:400]))

            # --- canonical hashes ---
            for view in CANONICAL:
                page.goto(f"{url}#{view}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(700)
                d = dump_view(page)
                d["target"] = measure_target(page, view) if page.evaluate(
                    "(id) => !!document.getElementById(id)", view
                ) else None
                page.screenshot(path=str(SHOTS / f"canonical-{view}-1440.png"), full_page=False)
                report["canonical"].append(
                    {
                        "hash": f"#{view}",
                        "onView": d["onView"],
                        "views": d["views"],
                        "stickyOffset": d["stickyOffset"],
                        "topbarH": d["topbarH"],
                        "visible_head": d["visibleText"][:800],
                        "access": d["access"],
                    }
                )

            # --- empty + unknown ---
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(500)
            empty = dump_view(page)
            report["special"]["empty"] = {
                "hash": empty["hash"],
                "onView": empty["onView"],
            }
            page.goto(f"{url}#not-a-real-view", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(400)
            unk = dump_view(page)
            report["special"]["unknown"] = {"hash": unk["hash"], "onView": unk["onView"]}

            # --- legacy anchors ---
            for anc, expected in LEGACY.items():
                page.goto(f"{url}#{anc}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(500)
                d = dump_view(page)
                tgt = measure_target(page, anc)
                report["legacy"].append(
                    {
                        "hash": f"#{anc}",
                        "expected": expected,
                        "onView": d["onView"],
                        "ok_view": d["onView"] == expected,
                        "target": tgt,
                    }
                )

            # --- theme / read ---
            theme_id = page.evaluate(
                """() => {
                  const raw = (window.REF && REF.registry && REF.registry['basketdata/baskets.json']);
                  if (!raw) return null;
                  const j = JSON.parse(raw);
                  const t = ((j.theme_intel||{}).themes||[]).find(x => x && x.id);
                  return t ? t.id : null;
                }"""
            )
            report["special"]["theme_id"] = theme_id
            if theme_id:
                page.goto(f"{url}#theme-{theme_id}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(400)
                th = dump_view(page)
                report["special"]["theme"] = {
                    "hash": th["hash"],
                    "onView": th["onView"],
                    "log": th["log"],
                }
            page.goto(f"{url}#theme-not-a-real-theme", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(300)
            thb = dump_view(page)
            report["special"]["theme_unknown"] = {
                "hash": thb["hash"],
                "onView": thb["onView"],
                "log": thb["log"][-8:],
            }

            read_id = page.evaluate(
                """() => {
                  const raw = REF.registry && REF.registry['basketdata/action_board.json'];
                  if (!raw) return null;
                  const j = JSON.parse(raw.replace(/:(\\s*)NaN\\b/g,':$1null'));
                  const rows = j.buy_now || j.action_board || [];
                  const list = Array.isArray(rows) ? rows : (j.buy_now || []);
                  const row = (j.buy_now || j.lanes || [])[0];
                  // production uses data-mlc-bid; try several shapes
                  if (Array.isArray(j.buy_now) && j.buy_now[0]) {
                    return j.buy_now[0].id || j.buy_now[0].bid || j.buy_now[0].theme_id || null;
                  }
                  return null;
                }"""
            )
            report["special"]["read_id_guess"] = read_id
            if read_id:
                page.goto(f"{url}#read-{read_id}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(700)
                rd = dump_view(page)
                expanded = page.evaluate(
                    """(id) => {
                      const row = document.querySelector(`#actnow .rvx-trow[data-mlc-bid="${id}"]`)
                        || document.querySelector(`[data-mlc-bid="${id}"]`);
                      return row ? {present:true, cls:row.className, text:row.innerText.slice(0,200)} : {present:false};
                    }""",
                    read_id,
                )
                report["special"]["read"] = {
                    "hash": rd["hash"],
                    "onView": rd["onView"],
                    "row": expanded,
                }

            # --- access states ---
            page.goto(f"{url}#overview", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(600)

            def access_snapshot(label: str) -> dict:
                return page.evaluate(
                    """(label) => {
                      const lanes = [...document.querySelectorAll('[data-ab-lane], .r3-lane, .act-col, [id^="ab-"]')];
                      const more = [...document.querySelectorAll('.pg-more, a[href="plans.html"]')]
                        .map(el => ({text: el.innerText.replace(/\\s+/g,' ').trim().slice(0,160),
                                     href: el.getAttribute('href')}));
                      const rows = [...document.querySelectorAll('#actnow a, #actnow .rvx-trow, #actnow [data-name], #ov-act a[data-ref-nav]')]
                        .map(el => ({
                          text: (el.innerText||'').replace(/\\s+/g,' ').trim().slice(0,80),
                          href: el.getAttribute('href')
                        }));
                      const counts = [...document.querySelectorAll('.acth-count, .r3-ledge-count, [data-count]')]
                        .map(el => el.innerText.replace(/\\s+/g,' ').trim());
                      const gatedElse = [...document.querySelectorAll('section.si-view')]
                        .filter(s => s.getAttribute('data-view') !== 'overview')
                        .map(s => ({
                          view: s.getAttribute('data-view'),
                          hasPlans: !!s.querySelector('a[href="plans.html"]'),
                          hasSignIn: /sign in/i.test(s.innerText),
                          hasLock: /locked|upgrade|subscribe/i.test(s.innerText)
                        }));
                      return {
                        label,
                        access: REF.accessState,
                        more,
                        rowCount: rows.length,
                        rows: rows.slice(0, 20),
                        counts,
                        gatedElse,
                        actnowText: (document.querySelector('#actnow')||{innerText:''}).innerText.replace(/\\s+/g,' ').trim().slice(0,1500)
                      };
                    }""",
                    label,
                )

            report["access"]["gated"] = access_snapshot("gated")
            page.screenshot(path=str(SHOTS / "access-gated-overview.png"))
            page.evaluate("() => REF.setAccessState('hydrated')")
            page.wait_for_timeout(400)
            report["access"]["hydrated"] = access_snapshot("hydrated")
            page.screenshot(path=str(SHOTS / "access-hydrated-overview.png"))
            page.evaluate("() => REF.setAccessState('ungated')")
            page.wait_for_timeout(400)
            report["access"]["ungated"] = access_snapshot("ungated")
            page.screenshot(path=str(SHOTS / "access-ungated-overview.png"))
            page.evaluate("() => REF.setAccessState('gated')")

            # fetch-fail boot
            page.goto(f"{url}?reffail=1#overview", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(700)
            fail = dump_view(page)
            report["access"]["reffail"] = {
                "onView": fail["onView"],
                "visible_head": fail["visibleText"][:1000],
                "log": fail["log"][-20:],
                "hasFailCopy": "Data failed to load" in fail["visibleText"],
            }
            page.screenshot(path=str(SHOTS / "access-reffail-overview.png"))

            # --- six tasks ---
            page.goto(f"{url}#overview", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(700)
            report["tasks"]["overview"] = page.evaluate(
                """() => {
                  const watch = document.getElementById('ov-watch') || document.querySelector('.r3-watch');
                  const grader = document.getElementById('grader');
                  const lanes = [...document.querySelectorAll('.r3-ledge, [data-ab-lane], .act-col')].map(el => ({
                    id: el.id,
                    lane: el.getAttribute('data-ab-lane'),
                    text: el.innerText.replace(/\\s+/g,' ').trim().slice(0,220)
                  }));
                  const timing = (watch && /timing_state|signal\\b/i.test(watch.innerText));
                  const hrefs = [...document.querySelectorAll('#actnow a, .r3-watch a')].map(a => a.getAttribute('href'));
                  return {
                    watchPresent: !!watch,
                    watchText: watch ? watch.innerText.replace(/\\s+/g,' ').trim().slice(0,600) : null,
                    watchRendersTiming: timing,
                    graderPresent: !!grader,
                    graderText: grader ? grader.innerText.replace(/\\s+/g,' ').trim().slice(0,500) : null,
                    lanes,
                    hrefs: hrefs.slice(0, 30),
                    drill: (document.querySelector('a[href="#confluence"]')||{}).innerText || null
                  };
                }"""
            )

            page.goto(f"{url}#map", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(900)
            report["tasks"]["map"] = page.evaluate(
                """() => {
                  const svg = document.querySelector('#rvx-rmap svg, #rvx-rmap canvas, #sc-chart svg, #sc-chart canvas');
                  const board = document.getElementById('rvx-board') || document.querySelector('#board');
                  const table = document.querySelector('#rvx-board table, #map-access table, table');
                  const reco = [...document.querySelectorAll('#board .reco, .r3-reco, [data-reco]')]
                    .slice(0,8).map(el => el.innerText.replace(/\\s+/g,' ').trim());
                  const disclaimer = /Only the lanes above carry a gated/i.test(document.body.innerText);
                  const hrefs = [...document.querySelectorAll('section.si-view.on a')].map(a => ({
                    href: a.getAttribute('href'), ref: a.hasAttribute('data-ref-nav'),
                    text: a.innerText.replace(/\\s+/g,' ').trim().slice(0,60)
                  }));
                  return {
                    svgPresent: !!svg,
                    boardPresent: !!board,
                    boardText: board ? board.innerText.replace(/\\s+/g,' ').trim().slice(0,700) : null,
                    tablePresent: !!table,
                    reco,
                    disclaimer,
                    hrefs: hrefs.slice(0, 25),
                    scChart: !!document.getElementById('sc-chart')
                  };
                }"""
            )
            page.screenshot(path=str(SHOTS / "task-map.png"))

            page.goto(f"{url}#moving", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1000)
            report["tasks"]["moving"] = page.evaluate(
                """() => {
                  const ev = document.getElementById('rc-events-mount');
                  const rot = document.getElementById('rotation-app');
                  const desk = document.getElementById('desk-watch-mount');
                  const hrefs = [...document.querySelectorAll('section.si-view.on a')].map(a => ({
                    href: a.getAttribute('href'), ref: a.hasAttribute('data-ref-nav'),
                    text: a.innerText.replace(/\\s+/g,' ').trim().slice(0,60)
                  }));
                  const fetches = (REF.log||[]).filter(x => x.type==='fetch').map(x => x.path+':'+x.result);
                  return {
                    eventsText: ev ? ev.innerText.replace(/\\s+/g,' ').trim().slice(0,700) : null,
                    rotationText: rot ? rot.innerText.replace(/\\s+/g,' ').trim().slice(0,700) : null,
                    deskText: desk ? desk.innerText.replace(/\\s+/g,' ').trim().slice(0,700) : null,
                    hrefs: hrefs.slice(0, 25),
                    fetches: fetches.slice(0, 30)
                  };
                }"""
            )
            page.screenshot(path=str(SHOTS / "task-moving.png"))

            page.goto(f"{url}#money", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1000)
            report["tasks"]["money"] = page.evaluate(
                """() => {
                  const heat = document.getElementById('heatmap-scorecard');
                  const flows = document.getElementById('sc-flows');
                  const lead = document.getElementById('scc-leadership');
                  const read = document.getElementById('si-read-money');
                  const hrefs = [...document.querySelectorAll('section.si-view.on a')].map(a => ({
                    href: a.getAttribute('href'), ref: a.hasAttribute('data-ref-nav'),
                    text: a.innerText.replace(/\\s+/g,' ').trim().slice(0,60)
                  }));
                  return {
                    readText: read ? read.innerText.replace(/\\s+/g,' ').trim().slice(0,400) : null,
                    heatText: heat ? heat.innerText.replace(/\\s+/g,' ').trim().slice(0,700) : null,
                    heatHasSvg: !!(heat && heat.querySelector('svg, canvas')),
                    flowsText: flows ? flows.innerText.replace(/\\s+/g,' ').trim().slice(0,500) : null,
                    leadText: lead ? lead.innerText.replace(/\\s+/g,' ').trim().slice(0,500) : null,
                    bodyHead: document.querySelector('section.si-view.on').innerText.replace(/\\s+/g,' ').trim().slice(0,1200),
                    hrefs: hrefs.slice(0, 25)
                  };
                }"""
            )
            page.screenshot(path=str(SHOTS / "task-money.png"))

            page.goto(f"{url}#explore", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1200)
            report["tasks"]["explore_before"] = page.evaluate(
                """() => {
                  const table = document.getElementById('btable');
                  const tm = document.getElementById('tm-mount');
                  const fn = document.getElementById('forming-narratives');
                  const show = document.getElementById('btbl-showall');
                  const chart = document.getElementById('chart-section');
                  return {
                    tableRows: table ? table.querySelectorAll('tr').length : 0,
                    tableHead: table ? table.innerText.replace(/\\s+/g,' ').trim().slice(0,800) : null,
                    showAll: show ? show.innerText.trim() : null,
                    tmText: tm ? tm.innerText.replace(/\\s+/g,' ').trim().slice(0,600) : null,
                    fnText: fn ? fn.innerText.replace(/\\s+/g,' ').trim().slice(0,800) : null,
                    hasModelAnalysis: /model analysis/i.test(document.body.innerText),
                    hasWatchingFor: /Watching for:/i.test(document.body.innerText),
                    hasKill: /Kill criterion/i.test(document.body.innerText),
                    chartText: chart ? chart.innerText.replace(/\\s+/g,' ').trim().slice(0,400) : null,
                    searchBox: !!document.querySelector('section.si-view.on input[type="search"], section.si-view.on input[type="text"]')
                  };
                }"""
            )
            # Show all
            show = page.query_selector("#btbl-showall")
            if show:
                show.click()
                page.wait_for_timeout(400)
            report["tasks"]["explore_showall"] = page.evaluate(
                """() => ({
                  tableRows: document.querySelectorAll('#btable tr').length,
                  showAll: (document.getElementById('btbl-showall')||{}).innerText || null
                })"""
            )
            # Time machine open
            tm_summary = page.query_selector("#tm-mount summary, #tm-mount button, #tm-mount .tm-open")
            if tm_summary:
                tm_summary.click()
                page.wait_for_timeout(800)
            report["tasks"]["explore_tm_open"] = page.evaluate(
                """() => ({
                  tmText: (document.getElementById('tm-mount')||{}).innerText.replace(/\\s+/g,' ').trim().slice(0,800),
                  fetches: (REF.log||[]).filter(x => /tm_|oracledata|episode|chunk/.test(x.path||'')).slice(-20)
                })"""
            )
            page.screenshot(path=str(SHOTS / "task-explore.png"))

            page.goto(f"{url}#confluence", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1200)
            report["tasks"]["confluence"] = page.evaluate(
                """() => {
                  const tabs = [...document.querySelectorAll('[role="tab"], .sc-tab, .r3-uni, button, a')]
                    .filter(el => /S&P|Nasdaq|Russell|Basket/i.test(el.innerText))
                    .slice(0, 12)
                    .map(el => ({text: el.innerText.replace(/\\s+/g,' ').trim().slice(0,40),
                                 pressed: el.getAttribute('aria-selected') || el.getAttribute('aria-pressed') || el.className.slice(0,80)}));
                  const hrefs = [...document.querySelectorAll('section.si-view.on a')].map(a => ({
                    href: a.getAttribute('href'), ref: a.hasAttribute('data-ref-nav'),
                    text: a.innerText.replace(/\\s+/g,' ').trim().slice(0,60)
                  }));
                  const search = document.querySelector('section.si-view.on input');
                  return {
                    bodyHead: document.querySelector('section.si-view.on').innerText.replace(/\\s+/g,' ').trim().slice(0,1500),
                    tabs,
                    hrefs: hrefs.slice(0, 40),
                    hasSearch: !!search,
                    searchPlaceholder: search ? search.getAttribute('placeholder') : null,
                    tableRows: document.querySelectorAll('section.si-view.on table tr, section.si-view.on .sc-row').length
                  };
                }"""
            )
            # try universe clicks
            universes = []
            for label in ["Nasdaq", "Russell", "Baskets", "S&P"]:
                loc = page.locator("section.si-view.on").get_by_text(label, exact=False).first
                try:
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=2000)
                        page.wait_for_timeout(500)
                        universes.append(
                            page.evaluate(
                                """(label) => ({
                                  label,
                                  head: document.querySelector('section.si-view.on').innerText.replace(/\\s+/g,' ').trim().slice(0,400),
                                  hrefSample: [...document.querySelectorAll('section.si-view.on a[data-ref-nav]')].slice(0,5).map(a => a.getAttribute('href'))
                                })""",
                                label,
                            )
                        )
                except Exception as exc:
                    universes.append({"label": label, "error": str(exc)[:200]})
            report["tasks"]["confluence_universes"] = universes
            # zero-search
            search = page.query_selector("section.si-view.on input")
            if search:
                search.fill("zzzz-no-such-group")
                page.wait_for_timeout(300)
                report["tasks"]["confluence_zero_search"] = page.evaluate(
                    """() => ({
                      head: document.querySelector('section.si-view.on').innerText.replace(/\\s+/g,' ').trim().slice(0,500),
                      hasNoResults: /no results|nothing found|0\\//i.test(document.querySelector('section.si-view.on').innerText)
                    })"""
                )
            page.screenshot(path=str(SHOTS / "task-confluence.png"))

            # mobile sticky
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"{url}#actnow-section", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(700)
            report["special"]["mobile_actnow"] = {
                "target": measure_target(page, "actnow-section"),
                "onView": dump_view(page)["onView"],
            }
            page.screenshot(path=str(SHOTS / "mobile-actnow-390.png"))
            page.goto(f"{url}#grader", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(700)
            report["special"]["mobile_grader"] = measure_target(page, "grader")
            page.screenshot(path=str(SHOTS / "mobile-grader-390.png"))

            # destination inventory after JS
            page.set_viewport_size({"width": 1440, "height": 900})
            dests = {}
            for view in CANONICAL:
                page.goto(f"{url}#{view}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(800)
                dests[view] = page.evaluate(
                    """() => [...document.querySelectorAll('section.si-view.on a[href]')].map(a => ({
                      href: a.getAttribute('href'),
                      ref: a.hasAttribute('data-ref-nav'),
                      text: (a.innerText||'').replace(/\\s+/g,' ').trim().slice(0,70)
                    }))"""
                )
            report["destinations"] = dests

            browser.close()
    finally:
        httpd.shutdown()

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (OUT / "probe_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", OUT / "probe_report.json")
    print("canonical", [(x["hash"], x["onView"]) for x in report["canonical"]])
    print("legacy fails", [x["hash"] for x in report["legacy"] if not x["ok_view"]])
    print("pageerrors", len(report["pageerrors"]), report["pageerrors"][:5])


if __name__ == "__main__":
    main()
