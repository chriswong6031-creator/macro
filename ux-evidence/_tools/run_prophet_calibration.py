#!/usr/bin/env python3
"""Calibration run: Prophet board + stock detail. Read-only browser evidence."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cdp_collect import CDP, EXTRACT_JS, annotate, connect, dump_json  # noqa: E402

ROOT = Path("/Users/chriswong/Documents/Cluade/macro-main/ux-evidence")
BOARD = ROOT / "pages" / "us-stocks-prophet-board"
DETAIL = ROOT / "pages" / "stock-detail"
SHOTS_B = BOARD / "screenshots"
SHOTS_D = DETAIL / "screenshots"
RUNTIME = []


def note(msg):
    print(msg, flush=True)
    RUNTIME.append({"t": datetime.now(timezone.utc).isoformat(), "msg": msg})


def wait_ready(cdp, extra=2.0):
    time.sleep(extra)
    try:
        cdp.ev("document.readyState")
    except Exception as e:
        note(f"ready check: {e}")


def scroll_to(cdp, selector):
    cdp.ev(
        f"""(() => {{
      const el = document.querySelector({selector!r});
      if (el) el.scrollIntoView({{block:'start', behavior:'instant'}});
      return !!(el);
    }})()"""
    )
    time.sleep(0.5)


def capture_view(cdp, dest_dir: Path, prefix: str, w, h, mobile=False, full=False, extra_name=""):
    dest_dir.mkdir(parents=True, exist_ok=True)
    cdp.viewport(w, h, mobile=mobile)
    wait_ready(cdp, 0.7)
    name = f"{prefix}_{w}x{h}{extra_name}{'_full' if full else ''}.png"
    path = dest_dir / name
    cdp.screenshot(path, full=full)
    note(f"shot {path.name} {path.stat().st_size}")
    return path


def frames(cdp, dest_dir: Path, prefix: str, action_js: str):
    dest_dir.mkdir(parents=True, exist_ok=True)
    before = dest_dir / f"{prefix}_00_before.png"
    cdp.screenshot(before)
    cdp.ev(action_js)
    time.sleep(0.05)
    start = dest_dir / f"{prefix}_01_start.png"
    try:
        cdp.screenshot(start)
    except Exception as e:
        note(f"frame start fail {e}")
        start = None
    time.sleep(0.12)
    mid = dest_dir / f"{prefix}_02_mid.png"
    try:
        cdp.screenshot(mid)
    except Exception as e:
        note(f"frame mid fail {e}")
        mid = None
    time.sleep(0.5)
    settled = dest_dir / f"{prefix}_03_settled.png"
    cdp.screenshot(settled)
    return {
        "before": str(before),
        "start": str(start) if start else None,
        "mid": str(mid) if mid else None,
        "settled": str(settled),
    }


def ax_tree(cdp):
    try:
        return cdp.call("Accessibility.getFullAXTree", timeout=20)
    except Exception as e:
        note(f"AX tree failed: {e}")
        return {"error": str(e)}


def console_errors(cdp):
    out = []
    for ev in cdp.events:
        m = ev.get("method")
        p = ev.get("params") or {}
        if m in ("Runtime.exceptionThrown", "Log.entryAdded"):
            out.append({"method": m, "params": p})
        if m == "Network.loadingFailed":
            out.append({"method": m, "url": p.get("errorText"), "type": p.get("type")})
        if m == "Runtime.consoleAPICalled" and p.get("type") in ("error", "warning"):
            out.append({"method": m, "type": p.get("type"), "args": p.get("args")})
    return out[-80:]


def main():
    ts = datetime.now(timezone.utc).isoformat()
    cdp = CDP(connect())
    cdp.enable()
    note("CDP enabled")

    # -------- BOARD --------
    url = "https://www.mastermind-x.com/us_stocks.html"
    cdp.navigate(url, wait=5)
    note(f"navigated {cdp.ev('location.href')}")
    scroll_to(cdp, "#us-standouts")
    cdp.viewport(1440, 1000)
    wait_ready(cdp, 1.5)

    extract = cdp.ev(EXTRACT_JS)
    dump_json(BOARD / "extract-default-1440.json", extract)
    dump_json(BOARD / "element-manifest.json", extract.get("elements") or [])
    (BOARD / "visible-text.txt").write_text(extract.get("visible_text") or "", encoding="utf-8")
    dump_json(BOARD / "layout-style.json", {
        "styles": extract.get("styles"),
        "token_proliferation": extract.get("token_proliferation"),
        "viewport": extract.get("viewport"),
    })
    dump_json(BOARD / "accessibility-tree.json", ax_tree(cdp))

    # default viewports
    p1440 = capture_view(cdp, SHOTS_B, "board_default", 1440, 1000)
    annotate(p1440, SHOTS_B / "board_default_1440x1000_annotated.png", extract.get("elements") or [])
    capture_view(cdp, SHOTS_B, "board_default", 1440, 1000, full=True)
    capture_view(cdp, SHOTS_B, "board_default", 1280, 900)
    capture_view(cdp, SHOTS_B, "board_default", 1024, 800)
    capture_view(cdp, SHOTS_B, "board_default", 768, 900, mobile=True)
    p390 = capture_view(cdp, SHOTS_B, "board_default", 390, 844, mobile=True)
    annotate(p390, SHOTS_B / "board_default_390x844_annotated.png", extract.get("elements") or [])
    capture_view(cdp, SHOTS_B, "board_default", 390, 844, mobile=True, full=True)

    # reset desktop
    cdp.viewport(1440, 1000)
    scroll_to(cdp, "#us-standouts")

    interactions = []

    # hover first featured card
    hover_js = r"""
    (() => {
      const el = document.querySelector('a.pvcard.pv-featured') || document.querySelector('a.pvcard');
      if (!el) return {ok:false};
      el.scrollIntoView({block:'center', behavior:'instant'});
      el.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));
      el.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true}));
      const r = el.getBoundingClientRect();
      return {ok:true, ticker: el.dataset.ticker, box:{x:r.x,y:r.y,w:r.width,h:r.height}, href: el.getAttribute('href')};
    })()
    """
    hover = cdp.ev(hover_js)
    time.sleep(0.35)
    capture_view(cdp, SHOTS_B, "board_card_hover", 1440, 1000, extra_name="")
    interactions.append({
        "id": "I001", "control": "first featured prophet card", "type": "hover",
        "action": "mouseenter/mouseover", "result": hover, "url_change": None
    })
    # unhover
    cdp.ev("document.querySelector('a.pvcard') && document.querySelector('a.pvcard').dispatchEvent(new MouseEvent('mouseleave',{bubbles:true}))")

    # help tooltip
    tip = cdp.ev(r"""
    (() => {
      const h = document.querySelector('#us-standouts .help');
      if (!h) return {ok:false};
      h.scrollIntoView({block:'center', behavior:'instant'});
      h.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true}));
      h.dispatchEvent(new FocusEvent('focusin', {bubbles:true}));
      return {ok:true, text: (h.innerText||'').slice(0,400)};
    })()
    """)
    time.sleep(0.3)
    capture_view(cdp, SHOTS_B, "board_help_tooltip", 1440, 1000)
    interactions.append({"id": "I002", "control": "board help ?", "type": "hover/focus", "result": tip})

    # table view
    table_frames = frames(
        cdp,
        SHOTS_B / "motion_table_toggle",
        "table",
        "document.getElementById('us-st-btn-table') && document.getElementById('us-st-btn-table').click()",
    )
    after_table = cdp.ev(r"""
    (() => ({
      grid_sel: document.getElementById('us-st-btn-grid')?.getAttribute('aria-selected'),
      table_sel: document.getElementById('us-st-btn-table')?.getAttribute('aria-selected'),
      table_visible: !!(document.querySelector('#us-standouts table, #us-st-table, .st-table')),
      href: location.href
    }))()
    """)
    capture_view(cdp, SHOTS_B, "board_table_view", 1440, 1000)
    interactions.append({
        "id": "I003", "control": "Table view toggle", "type": "button",
        "action": "click #us-st-btn-table", "result": after_table,
        "motion_frames": table_frames, "url_change": after_table.get("href")
    })

    # back to grid
    cdp.ev("document.getElementById('us-st-btn-grid') && document.getElementById('us-st-btn-grid').click()")
    time.sleep(0.4)

    # track record dialog
    trd_frames = frames(
        cdp,
        SHOTS_B / "motion_track_record",
        "trd",
        "document.getElementById('trd-btn') && document.getElementById('trd-btn').click()",
    )
    trd_state = cdp.ev(r"""
    (() => {
      const dlg = document.getElementById('trd-dlg');
      const btn = document.getElementById('trd-btn');
      const cs = dlg ? getComputedStyle(dlg) : null;
      return {
        expanded: btn?.getAttribute('aria-expanded'),
        dlg_display: cs && cs.display,
        dlg_visibility: cs && cs.visibility,
        dlg_text: (dlg?.innerText || '').slice(0, 1500)
      };
    })()
    """)
    capture_view(cdp, SHOTS_B, "board_track_record_open", 1440, 1000)
    interactions.append({
        "id": "I004", "control": "Track record", "type": "dialog",
        "action": "click #trd-btn", "result": trd_state, "motion_frames": trd_frames
    })
    # close dialog
    cdp.ev(r"""
    (() => {
      const c = document.querySelector('[data-trd-close]');
      if (c) c.click();
      else document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
    })()
    """)
    time.sleep(0.4)

    # lifecycle / stage filters if present
    filter_info = cdp.ev(r"""
    (() => {
      const nodes = [...document.querySelectorAll('#us-standouts [data-stage], .pb-stage, .stage-filter, [data-filter], .pv-stage-filter, button')];
      const interesting = nodes.filter(n => /stage|live|ready|wait|buy|filter|featured|bottom/i.test((n.innerText||'')+(n.className||'')+(n.id||''))).slice(0, 25);
      return interesting.map(n => ({
        tag: n.tagName, id: n.id, text: (n.innerText||'').replace(/\s+/g,' ').trim().slice(0,80),
        className: String(n.className).slice(0,80)
      }));
    })()
    """)
    dump_json(BOARD / "candidate-filters.json", filter_info)

    # try clicking a stage/filter-looking control that isn't the table toggle
    clicked_filter = cdp.ev(r"""
    (() => {
      const btns = [...document.querySelectorAll('#us-standouts button, #us-standouts [role="tab"]')];
      const skip = new Set(['us-st-btn-grid','us-st-btn-table','trd-btn']);
      const cand = btns.find(b => b.id && !skip.has(b.id) && b.offsetParent);
      const cand2 = cand || btns.find(b => /featured|live|ready|wait|buy|all|new/i.test(b.innerText||'') && !skip.has(b.id));
      if (!cand2) return {ok:false, reason:'no filter button'};
      const before = document.querySelectorAll('a.pvcard').length;
      cand2.click();
      return {ok:true, id: cand2.id, text: (cand2.innerText||'').trim().slice(0,80), cards_before: before, cards_after: document.querySelectorAll('a.pvcard').length};
    })()
    """)
    time.sleep(0.5)
    if clicked_filter and clicked_filter.get("ok"):
        capture_view(cdp, SHOTS_B, "board_filter_applied", 1440, 1000)
        interactions.append({"id": "I005", "control": clicked_filter.get("id"), "type": "filter/button", "result": clicked_filter})
        # try restore by clicking again or 'all'
        cdp.ev("document.getElementById('us-st-btn-grid') && document.getElementById('us-st-btn-grid').click()")

    # language toggle if present
    lang_toggle = cdp.ev(r"""
    (() => {
      const el = document.querySelector('[data-lang-toggle], #lang, button.lang, .lang-toggle, [aria-label*="language" i], [aria-label*="中文"]');
      const all = [...document.querySelectorAll('button, a')].filter(n => /^(EN|ZH|中文|English)$/i.test((n.innerText||'').trim()) || /lang/i.test(n.id+n.className));
      return {
        dedicated: el && {id: el.id, text: (el.innerText||'').slice(0,40)},
        candidates: all.slice(0,8).map(n => ({id:n.id, text:(n.innerText||'').trim().slice(0,20), cls:String(n.className).slice(0,40)}))
      };
    })()
    """)
    dump_json(BOARD / "lang-theme-controls.json", lang_toggle)

    # theme
    theme_now = cdp.ev("document.documentElement.getAttribute('data-theme')")
    # safely toggle theme via attribute only (local, reversible)
    cdp.ev("document.documentElement.setAttribute('data-theme','light')")
    time.sleep(0.5)
    capture_view(cdp, SHOTS_B, "board_theme_light", 1440, 1000)
    cdp.ev("document.documentElement.setAttribute('data-lang','zh')")
    time.sleep(0.4)
    capture_view(cdp, SHOTS_B, "board_theme_light_zh", 1440, 1000)
    # restore
    cdp.ev(f"document.documentElement.setAttribute('data-theme', {theme_now!r} || 'dark')")
    cdp.ev("document.documentElement.setAttribute('data-lang','en')")
    time.sleep(0.3)

    # scroll inspection
    cdp.viewport(1440, 1000)
    scroll_to(cdp, "#us-standouts")
    capture_view(cdp, SHOTS_B, "board_scroll_top_of_board", 1440, 1000)
    cdp.ev("window.scrollBy(0, 700)")
    time.sleep(0.4)
    capture_view(cdp, SHOTS_B, "board_scroll_mid", 1440, 1000)
    sticky = cdp.ev(r"""
    (() => {
      const all = [...document.querySelectorAll('header, nav, .topbar, .sticky, [style*="sticky"], [style*="fixed"]')];
      return all.slice(0,20).map(el => {
        const cs = getComputedStyle(el);
        return {tag: el.tagName, id: el.id, cls: String(el.className).slice(0,60), position: cs.position, top: cs.top};
      });
    })()
    """)
    dump_json(BOARD / "scroll-sticky.json", sticky)

    # pick first card ticker for detail
    first_card = (extract.get("cards") or [{}])[0]
    ticker = first_card.get("ticker") or "ONTO"
    detail_href = first_card.get("href") or f"stock.html#{ticker}"
    note(f"detail target {ticker} {detail_href}")

    dump_json(BOARD / "interaction-manifest.json", interactions)
    dump_json(BOARD / "state-manifest.json", {
        "observed_states": [
            "DEFAULT_GRID",
            "CARD_HOVER",
            "HELP_TOOLTIP",
            "TABLE_VIEW",
            "TRACK_RECORD_DIALOG",
            "THEME_LIGHT",
            "LANG_ZH_ON_LIGHT",
            "SCROLLED",
            "FILTER_APPLIED" if clicked_filter and clicked_filter.get("ok") else "FILTER_NOT_FOUND",
        ],
        "transitions": [
            "DEFAULT_GRID -> CARD_HOVER",
            "DEFAULT_GRID -> TABLE_VIEW -> DEFAULT_GRID",
            "DEFAULT_GRID -> TRACK_RECORD_DIALOG -> DEFAULT_GRID",
            "DEFAULT_GRID -> THEME_LIGHT -> LANG_ZH_ON_LIGHT -> DEFAULT_GRID",
        ],
        "source_states_not_triggered": [
            "ahead / tonight's picks badge (hidden unless board state)",
            "behind / last confirmed badge",
            "closed market badge",
            "empty board",
            "paid/locked board if signed out still shows cards (anonymous populated observed)",
            "prophet-live panel (#prophet-live starts hidden)",
        ],
    })

    meta_board = {
        "route": "/us_stocks.html",
        "query": None,
        "hash": None,
        "page_title_visible": "Prophet Stock Signals",
        "browser_title": extract.get("title"),
        "navigation_location": "United States → Stock Dashboard",
        "auth_subscription_state": extract.get("auth_hint"),
        "viewport_primary": "1440x1000",
        "timestamp": ts,
        "application_commit_local": "36e8f7dc8b28",
        "application_commit_origin_main": "3c6f4ffa3a9a",
        "feature_flags": None,
        "data_context": {
            "market": "US",
            "board_asof_visible": "see visible-text / pbs-note",
            "card_count": extract.get("counts", {}).get("pvcards"),
            "first_ticker": ticker,
        },
        "major_sections": [
            "site shell / market nav",
            "optional #prophet-live forming-today panel (hidden by default)",
            "#us-standouts Prophet Stock Signals board",
            "grid/table toggle",
            "overnight confirmation note",
            "card grid (.pvcard)",
            "track record control + dialog",
            "footer note on Priority/Featured",
        ],
        "major_components": [
            "templates/_prophet_card.html.j2 (.pvcard)",
            "templates us stocks board (generated site/us_stocks.html)",
            "track record dialog #trd-dlg",
            "USStockTable view toggle",
        ],
        "apparent_user_objective": "Scan tonight/overnight US Prophet setups, compare readiness, open a name into the stock analyzer.",
        "outbound_routes": sorted({c.get("href") for c in extract.get("cards") or [] if c.get("href")}),
        "lang": extract.get("lang"),
        "theme": extract.get("theme"),
        "counts": extract.get("counts"),
    }
    dump_json(BOARD / "00-meta.json", meta_board)

    # -------- DETAIL --------
    detail_url = "https://www.mastermind-x.com/" + detail_href.lstrip("/")
    cdp.navigate(detail_url, wait=6)
    note(f"detail href {cdp.ev('location.href')} title {cdp.ev('document.title')}")
    cdp.viewport(1440, 1000)
    wait_ready(cdp, 2.0)

    detail_extract = cdp.ev(r"""
    (() => {
      const vis = (el) => {
        if (!el) return false;
        const cs = getComputedStyle(el);
        if (cs.display==='none'||cs.visibility==='hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width>1 && r.height>1;
      };
      const txt = (el) => (el.innerText||'').replace(/\s+/g,' ').trim();
      const box = (el) => { const r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; };
      const els = [];
      const push = (id, el, extra={}) => { if (!el) return; els.push({id, visible_label: txt(el).slice(0,240), role: el.getAttribute('role')||el.tagName.toLowerCase(), selector: el.id?('#'+el.id):el.tagName.toLowerCase(), tag: el.tagName.toLowerCase(), bounding_box: box(el), visible: vis(el), ...extra}); };
      push('E001', document.querySelector('h1, .tk, .ticker, .name-line'));
      [...document.querySelectorAll('h1,h2,h3')].slice(0,20).forEach((el,i)=>push('D'+String(i+1).padStart(3,'0'), el, {section:'headings'}));
      [...document.querySelectorAll('button, [role="tab"], .tab, nav a')].slice(0,40).forEach((el,i)=>push('I'+String(i+1).padStart(3,'0'), el, {section:'controls'}));
      const charts = [...document.querySelectorAll('svg, canvas, .chart')].slice(0,12);
      return {
        href: location.href, title: document.title,
        lang: document.documentElement.getAttribute('data-lang'),
        theme: document.documentElement.getAttribute('data-theme'),
        headings: [...document.querySelectorAll('h1,h2,h3')].map(h => ({t:h.tagName, text: txt(h).slice(0,160)})),
        buttons: [...document.querySelectorAll('button')].filter(vis).slice(0,40).map(b => ({id:b.id, text:txt(b).slice(0,80)})),
        tabs: [...document.querySelectorAll('[role="tab"], .tab, .tabs button')].map(t => txt(t).slice(0,80)),
        links: [...document.querySelectorAll('a[href]')].slice(0,40).map(a => ({href:a.getAttribute('href'), text:txt(a).slice(0,80)})),
        chart_count: charts.length,
        visible_text: document.body.innerText,
        elements: els,
        lock: !!(document.querySelector('.lock-cta, .mx-tier, .gate, .paywall')),
        viewport: {w:innerWidth,h:innerHeight,scrollH:document.documentElement.scrollHeight}
      };
    })()
    """)
    dump_json(DETAIL / "extract-default-1440.json", detail_extract)
    dump_json(DETAIL / "element-manifest.json", detail_extract.get("elements") or [])
    (DETAIL / "visible-text.txt").write_text(detail_extract.get("visible_text") or "", encoding="utf-8")
    dump_json(DETAIL / "accessibility-tree.json", ax_tree(cdp))

    d1440 = capture_view(cdp, SHOTS_D, "detail_default", 1440, 1000)
    annotate(d1440, SHOTS_D / "detail_default_1440x1000_annotated.png", detail_extract.get("elements") or [])
    capture_view(cdp, SHOTS_D, "detail_default", 1440, 1000, full=True)
    capture_view(cdp, SHOTS_D, "detail_default", 1280, 900)
    capture_view(cdp, SHOTS_D, "detail_default", 1024, 800)
    capture_view(cdp, SHOTS_D, "detail_default", 768, 900, mobile=True)
    d390 = capture_view(cdp, SHOTS_D, "detail_default", 390, 844, mobile=True)
    annotate(d390, SHOTS_D / "detail_default_390x844_annotated.png", detail_extract.get("elements") or [])
    capture_view(cdp, SHOTS_D, "detail_default", 390, 844, mobile=True, full=True)

    cdp.viewport(1440, 1000)
    # click first tab-like control if any
    detail_interactions = []
    tab_click = cdp.ev(r"""
    (() => {
      const tabs = [...document.querySelectorAll('[role="tab"], .tabs button, .tab')];
      if (!tabs[1]) return {ok:false, count: tabs.length, labels: tabs.map(t => (t.innerText||'').trim().slice(0,40))};
      const first = tabs[0] && (tabs[0].innerText||'').trim();
      tabs[1].click();
      return {ok:true, from: first, to: (tabs[1].innerText||'').trim(), count: tabs.length};
    })()
    """)
    time.sleep(0.6)
    if tab_click and tab_click.get("ok"):
        capture_view(cdp, SHOTS_D, "detail_tab_b", 1440, 1000)
        detail_interactions.append({"id": "DI001", "control": "second tab", "result": tab_click})

    # lock/cta if present
    lock = cdp.ev(r"""
    (() => {
      const el = document.querySelector('.lock-cta, .mx-tier-primary, .gate, .paywall');
      return el ? {present:true, text:(el.innerText||'').slice(0,200), cls:el.className} : {present:false};
    })()
    """)
    if lock and lock.get("present"):
        capture_view(cdp, SHOTS_D, "detail_locked_or_cta", 1440, 1000)
    detail_interactions.append({"id": "DI002", "control": "lock/cta presence", "result": lock})

    # chart hover
    chart_hover = cdp.ev(r"""
    (() => {
      const svg = document.querySelector('svg');
      if (!svg) return {ok:false};
      const r = svg.getBoundingClientRect();
      svg.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, clientX: r.x+r.width*0.7, clientY: r.y+r.height*0.4}));
      return {ok:true, w:r.width, h:r.height};
    })()
    """)
    time.sleep(0.3)
    capture_view(cdp, SHOTS_D, "detail_chart_hover", 1440, 1000)
    detail_interactions.append({"id": "DI003", "control": "first svg mousemove", "result": chart_hover})

    dump_json(DETAIL / "interaction-manifest.json", detail_interactions)
    dump_json(DETAIL / "state-manifest.json", {
        "observed_states": ["DEFAULT", "TAB_B" if tab_click and tab_click.get("ok") else "NO_SECOND_TAB", "CHART_HOVER"],
        "transitions": ["DEFAULT -> TAB_B"] if tab_click and tab_click.get("ok") else [],
        "ticker": ticker,
        "url": detail_extract.get("href"),
        "lock": lock,
    })
    dump_json(DETAIL / "00-meta.json", {
        "route": "/stock.html",
        "hash": f"#{ticker}",
        "page_title_visible": (detail_extract.get("headings") or [{}])[0],
        "browser_title": detail_extract.get("title"),
        "navigation_location": "reached from Prophet card href",
        "viewport_primary": "1440x1000",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_context": {"ticker": ticker, "href": detail_href},
        "auth_subscription_state": lock,
        "outbound_routes": [x.get("href") for x in (detail_extract.get("links") or [])][:40],
        "headings": detail_extract.get("headings"),
        "tabs": detail_extract.get("tabs"),
        "chart_count": detail_extract.get("chart_count"),
    })

    dump_json(ROOT / "pages" / "_runtime-events.json", console_errors(cdp))
    dump_json(BOARD / "_run-log.json", RUNTIME)
    note("done")
    cdp.close()


if __name__ == "__main__":
    main()
