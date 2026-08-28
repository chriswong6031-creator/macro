#!/usr/bin/env python3
"""R3B1-14 — bidirectional capability inventory for the R3B.1 candidate.

Commissioned to close DAC-108: `capability_crosscheck.md` rows #24 and #86
were marked VERIFIED by *enumerating what the candidate renders and stopping*
— a method that cannot detect an omission by construction, and is exactly how
DAC-101/102/103/104/106 (the dropped sizing directive, methodology caveat,
migration note, allocation destination, and hero enrichment) passed unnoticed
through that same row #24/#86 in the R3B pack.

This script replaces that method with two independent directions, run against
the RENDERED DOM of the built candidate (never against the candidate's own
markup as the source of truth for what "should" be there):

  Direction 1  expected production inventory -> candidate inventory
    EXPECTED_INVENTORY is hand-authored from PRODUCER bytes (the R3A fixture
    JSON, read fresh at every run) and the R3A capability ledger/routing
    contract — never from the candidate. Every numeric pin (the 81% sizing
    figure, the hero 20d/5d relative-performance percentages, the 49/15
    theme/category counts, the 65/113/48 S&P coverage numbers) is re-derived
    from the fixture bytes each run, not hardcoded, so a fixture update that
    changes these numbers changes the proof's expectation too — see
    `build_expected_inventory()`. Every entry is sourced in
    `INVENTORY_SOURCES.md`.

  Direction 2  candidate inventory -> allowed production/projection inventory
    Every `data-path="…"` data-registry block in the built candidate must
    trace to an R3A fixture receipt or an R3B.1 fixture_supplement receipt;
    every unresolved (`recorded-not-executed`) runtime fetch must be one of
    the two documented, out-of-lane exceptions (Time Machine chunk fetches,
    README_BUILD.md; the R3A premium-data access gate); and every
    `[data-ref-nav]` href must match one of the R3A routing contract's
    per-view working-destination families. Anything unmatched is a red
    naming the offending path/href — a capability the candidate invented
    that no producer or contract authorizes.

Usage:
    <playwright-python> inventory_check.py [--candidate PATH] [--json OUT]
Exit 0 iff every check in both directions passes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD_DIR = Path(__file__).resolve().parent
R3B1_DIR = BUILD_DIR.parent
REPO_ROOT = BUILD_DIR.parents[4]

R3A_DIR = REPO_ROOT / "research/reference_integrity/mastermind-xpv2-sector-r3"
FIXTURE_DIR = R3A_DIR / "fixture"
RECEIPTS_PATH = FIXTURE_DIR / "receipts.json"
RECEIPTS_SUPPLEMENT_PATH = BUILD_DIR / "fixture_supplement" / "receipts_supplement.json"

DEFAULT_CANDIDATE = R3B1_DIR / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
EXPECTED_JSON_PATH = BUILD_DIR / "expected_inventory.json"

VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
CONFLUENCE_TABS = ["subsectors", "nasdaq", "russell", "baskets"]

# ── Direction 2 — allowed destination families ──────────────────────────────
# Sourced from research/.../mastermind-xpv2-sector-r3/routing_contract.md §7
# ("Working-destination inventory per view") and capability_crosscheck.md row
# #86, plus the Money view's producer-bound external terminal URL (see
# INVENTORY_SOURCES.md for the full citation of each).
DESTINATION_FAMILIES = [
    {"id": "basket_family", "pattern": r"^basket/",
     "source": "routing_contract.md §7 Overview/Map/Explore: basket/<id>.html"},
    {"id": "subsector_family", "pattern": r"^subsector",
     "source": "routing_contract.md §7 Confluence detailHref: subsector/, subsector_nasdaq/, subsector_russell/, subsector/b-*"},
    {"id": "stock_family", "pattern": r"^stock\.html#",
     "source": "routing_contract.md §7 Confluence stockHref(tk): stock.html#<TICKER>"},
    {"id": "rotation_family", "pattern": r"^rotation/",
     "source": "capability_crosscheck.md row #86 Moving view: rotation/*"},
    {"id": "sector_cycles_family", "pattern": r"^sector_cycles\.html",
     "source": "capability_crosscheck.md row #86 Map view: sector_cycles.html / sector_cycles.html#*"},
    {"id": "plans_family", "pattern": r"^plans\.html",
     "source": "routing_contract.md §7 Overview gated tease: plans.html"},
    {"id": "allocation_family", "pattern": r"^allocation\.html",
     "source": "R3A capability ledger #86 Overview hero destination: allocation.html (DAC-104 restoration, R3B1-04)"},
    {"id": "terminal_cross_repo_family", "pattern": r"^https://app\.mastermind-x\.com/terminal\?symbol=",
     "source": "build/fixture_supplement/marketdata/sp500_heatmap.json stock_url field; money.html STOCK_URL mirrors production heatmap.js:826 (data.stock_url fallback)",
     "producer_note": "the fixture's own stock_url is the external terminal URL, not the 'stock.html#' fallback; both are genuine per production's own field"},
]

# ── Direction 2 — allowed unresolved (recorded-not-executed) fetch paths ────
ALLOWED_UNRESOLVED_FETCHES = {
    "basketdata/pulse.json": "Explore Time Machine mount — R3C-only condition (COMMISSION.md "
                              "'Time Machine live oracledata episode/chunk fetch'); README_BUILD.md "
                              "'Time Machine — recorded-not-executed ruling'",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def rel_txt(v: float) -> str:
    """Mirror overview.html's relTxt(v): `(p>=0?'+':'')+p.toFixed(1)+'%'`."""
    p = v * 100
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.1f}%"


# ── Direction 1 — EXPECTED_INVENTORY, derived from producer bytes ──────────
def build_expected_inventory() -> tuple[list[dict], dict]:
    """Hand-authored expected inventory. Selectors/views/static UI copy are
    literal (this reference's own presentation code, e.g. 'Open the
    playbook', 'How this works'); every NUMBER and every producer-authored
    sentence is read from the R3A/R3B.1 fixture bytes right here, at run
    time — never hardcoded — so the proof re-derives from producer bytes on
    every invocation, per the frozen spec.
    """
    baskets = load_json(FIXTURE_DIR / "basketdata" / "baskets.json")
    handoff = load_json(FIXTURE_DIR / "basketdata" / "si_handoff.json")
    coverage_sp = load_json(FIXTURE_DIR / "marketdata" / "subsector_confluence.json")["coverage"]

    ti = baskets["theme_intel"]
    regime_sizing = ti["regime_sizing"]
    pct = round(regime_sizing["gross_scalar"] * 100)

    themes_by_id = {t["id"]: t for t in ti.get("themes", []) if "id" in t}
    tc = handoff["theme_context"]
    leadership = tc["leadership"]
    trailing = leadership.get("trailing_leader") or {}
    strength = leadership.get("strength") or []
    taker = strength[0] if strength else None

    def meta_for(theme_id, side):
        t = themes_by_id.get(theme_id) if theme_id else None
        if not t:
            return None
        perf = t.get("perf") or {}
        r20 = (perf.get("20d") or {}).get("rel")
        parts_en, parts_zh = [], []
        if r20 is not None:
            parts_en.append(f"{rel_txt(r20)} 20d")
            parts_zh.append(f"{rel_txt(r20)} 20日")
        if side == "out":
            r5 = (perf.get("5d") or {}).get("rel")
            if r5 is not None and r5 < 0:
                parts_en.append(f"{rel_txt(r5)} 5d")
                parts_zh.append(f"{rel_txt(r5)} 5日")
        else:
            delta = t.get("pulse_rank_delta_5d")
            if delta is not None and delta > 0:
                parts_en.append("climbing fast")
                parts_zh.append("快速上行")
        if not parts_en:
            return None
        return {"en": " · ".join(parts_en), "zh": " · ".join(parts_zh)}

    out_meta = meta_for(trailing.get("id"), "out")
    in_meta = meta_for(taker.get("id") if taker else None, "in")

    n_themes = len(baskets.get("baskets", []))
    n_categories = len(baskets.get("categories", []))

    migration = tc.get("migration") or {}
    note_en = migration.get("note_en") or ""
    note_zh = migration.get("note_zh") or note_en

    entries: list[dict] = []

    entries.append({
        "id": "sizing_pct", "capability": "sizing_directive",
        "view": "overview", "selector": '[data-r3b1="01"]', "check": "text",
        "must_contain_en": [f"positions sized to {pct}%"],
        "must_contain_zh": [f"仓位缩至 {pct}%"],
        "source": "basketdata/baskets.json theme_intel.regime_sizing.gross_scalar "
                   f"= {regime_sizing['gross_scalar']} (round(*100)={pct}); production "
                   "sector_central.html.j2:2886-2919 renderRegimeSizing()",
    })
    entries.append({
        "id": "caveat_not_forecast", "capability": "method_caveat_clause_a",
        "view": "overview", "selector": '[data-r3b1="02"] [data-tip-en]', "check": "attr",
        "attrs": ["data-tip-en", "data-tip-zh"],
        "must_contain_en": ["not a forecast"], "must_contain_zh": ["非预测"],
        "source": "production sector_central.html.j2:2153, quoted DAC-102 "
                   "'Shape read only — not a forecast.'",
    })
    entries.append({
        "id": "caveat_construction_lag", "capability": "method_caveat_clause_b",
        "view": "overview", "selector": '[data-r3b1="02"] [data-tip-en]', "check": "attr",
        "attrs": ["data-tip-en", "data-tip-zh"],
        "must_contain_en": ["~3 weeks by construction"], "must_contain_zh": ["约3周"],
        "source": "production sector_central.html.j2:2153, quoted DAC-102 "
                   "'skips the most recent ~3 weeks by construction'",
    })
    entries.append({
        "id": "migration_note", "capability": "migration_note",
        "view": "overview", "selector": '[data-r3b1="03"]', "check": "text",
        "must_contain_en": [note_en], "must_contain_zh": [note_zh],
        "source": "basketdata/si_handoff.json theme_context.migration.note_en/note_zh; "
                   "production sector_central.html.j2:2130 (DAC-103)",
    })
    entries.append({
        "id": "allocation_href", "capability": "allocation_destination",
        "view": "overview", "selector": '[data-r3b1="04"]', "check": "href",
        "equals": "allocation.html",
        "source": "R3A capability_disposition_ledger.md #86 'per-view working-destination "
                   "inventory', Overview 'Hero leadership context' row; production "
                   "sector_central.html.j2:2163 (DAC-104)",
    })
    entries.append({
        "id": "allocation_text", "capability": "allocation_destination",
        "view": "overview", "selector": '[data-r3b1="04"]', "check": "text",
        "must_contain_en": ["Open the playbook"], "must_contain_zh": ["打开操盘手册"],
        "source": "same as allocation_href",
    })
    if out_meta:
        entries.append({
            "id": "hero_enrichment_outgoing", "capability": "hero_enrichment_outgoing",
            "view": "overview", "selector": '[data-r3b1="05a"]', "check": "text",
            "must_contain_en": [out_meta["en"]], "must_contain_zh": [out_meta["zh"]],
            "source": f"basketdata/baskets.json theme_intel.themes[id={trailing.get('id')!r}]"
                      ".perf['20d'].rel / .perf['5d'].rel (relTxt); "
                      "basketdata/si_handoff.json theme_context.leadership.trailing_leader; "
                      "production sector_central.html.j2:2928-2933 (DAC-106)",
        })
    if in_meta:
        entries.append({
            "id": "hero_enrichment_incoming", "capability": "hero_enrichment_incoming",
            "view": "overview", "selector": '[data-r3b1="05b"]', "check": "text",
            "must_contain_en": [in_meta["en"]], "must_contain_zh": [in_meta["zh"]],
            "source": f"basketdata/baskets.json theme_intel.themes[id={(taker or {}).get('id')!r}]"
                      ".perf['20d'].rel / .pulse_rank_delta_5d; "
                      "basketdata/si_handoff.json theme_context.leadership.strength[0]; "
                      "production sector_central.html.j2:2928-2933 (DAC-106)",
        })
    entries.append({
        "id": "hero_counts_themes", "capability": "hero_enrichment_counts",
        "view": "overview", "selector": '[data-r3b1="05c"]', "check": "text",
        "must_contain_en": [f"{n_themes} themes"], "must_contain_zh": [f"{n_themes} 个主题"],
        "source": f"basketdata/baskets.json baskets[].length={n_themes} (production "
                  ":2926 mirror; DAC-106)",
    })
    entries.append({
        "id": "hero_counts_categories", "capability": "hero_enrichment_counts",
        "view": "overview", "selector": '[data-r3b1="05c"]', "check": "text",
        "must_contain_en": [f"{n_categories} categories"], "must_contain_zh": [f"{n_categories} 个分类"],
        "source": f"basketdata/baskets.json categories[].length={n_categories} (production "
                  ":2926 mirror; DAC-106)",
    })
    entries.append({
        "id": "sp_coverage_gateable", "capability": "sp_coverage_sentence",
        "view": "confluence", "tab": "subsectors", "selector": '[data-r3b1="07"]', "check": "text",
        "must_contain_en": [str(coverage_sp["n_gateable"])], "must_contain_zh": [str(coverage_sp["n_gateable"])],
        "source": f"marketdata/subsector_confluence.json coverage.n_gateable={coverage_sp['n_gateable']}",
    })
    entries.append({
        "id": "sp_coverage_total", "capability": "sp_coverage_sentence",
        "view": "confluence", "tab": "subsectors", "selector": '[data-r3b1="07"]', "check": "text",
        "must_contain_en": [str(coverage_sp["n_subsectors"])], "must_contain_zh": [str(coverage_sp["n_subsectors"])],
        "source": f"marketdata/subsector_confluence.json coverage.n_subsectors={coverage_sp['n_subsectors']}",
    })
    entries.append({
        "id": "sp_coverage_thin", "capability": "sp_coverage_sentence",
        "view": "confluence", "tab": "subsectors", "selector": '[data-r3b1="07"]', "check": "text",
        "must_contain_en": [str(coverage_sp["n_thin"])], "must_contain_zh": [str(coverage_sp["n_thin"])],
        "source": f"marketdata/subsector_confluence.json coverage.n_thin={coverage_sp['n_thin']}",
    })
    entries.append({
        "id": "sp_coverage_phrase", "capability": "sp_coverage_sentence",
        "view": "confluence", "tab": "subsectors", "selector": '[data-r3b1="07"]', "check": "text",
        "must_contain_en": ["have enough live data"], "must_contain_zh": ["实时数据"],
        "source": "views/confluence.html paintFoot() honest-wording literal (R3B1-07, DAC-105 "
                  "wording condition); static UI copy, not a producer-derived number",
    })
    entries.append({
        "id": "conviction_label", "capability": "conviction_picks_label",
        "view": "confluence", "tab": "subsectors", "selector": '[data-r3b1="13"]', "check": "text_ci",
        "must_contain_en": ["conviction"], "must_contain_zh": ["综合把握"],
        "source": "ORCHESTRATOR_ADJUDICATIONS_R3B1.md R3B1-13 ruling (producer-named "
                  "'Conviction' combined_score column, not an invented label)",
    })

    meta = {
        "destination_families": DESTINATION_FAMILIES,
        "allowed_unresolved_fetches": ALLOWED_UNRESOLVED_FETCHES,
        "derived_values": {
            "sizing_pct": pct,
            "trailing_leader_id": trailing.get("id"),
            "taker_id": (taker or {}).get("id"),
            "n_themes": n_themes,
            "n_categories": n_categories,
            "coverage": coverage_sp,
            "migration_note_en": note_en,
            "migration_note_zh": note_zh,
        },
    }
    return entries, meta


# ── Playwright harness ───────────────────────────────────────────────────────
class Harness:
    def __init__(self, page):
        self.page = page
        self._visited_views: set[str] = set()   # for the full destination-family traversal
        self._current_view: str | None = None
        self._current_tab: str | None = None
        self.all_data_ref_nav_hrefs: set[str] = set()

    def goto_view(self, view: str) -> None:
        self.page.evaluate(
            "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
            "if(b)b.click();else location.hash='#'+v;}",
            view,
        )
        self.page.wait_for_timeout(300)
        self._visited_views.add(view)
        self._current_view = view
        self._current_tab = None
        self._collect_hrefs()

    def goto_confluence_tab(self, tab: str) -> None:
        if self._current_view != "confluence":
            self.goto_view("confluence")
        self.page.evaluate(
            "(t)=>{var b=document.getElementById('cf-uni-'+t); if(b) b.click();}", tab
        )
        self.page.wait_for_timeout(300)
        self._current_tab = tab
        self._collect_hrefs()

    def _collect_hrefs(self) -> None:
        hrefs = self.page.evaluate(
            "()=>Array.from(document.querySelectorAll('[data-ref-nav]'))"
            ".map(a=>a.getAttribute('href'))"
        )
        for h in hrefs:
            if h:
                self.all_data_ref_nav_hrefs.add(h)

    def full_traverse(self) -> None:
        for v in VIEWS:
            self.goto_view(v)
            if v == "confluence":
                for t in CONFLUENCE_TABS:
                    self.goto_confluence_tab(t)

    def ensure(self, view: str | None, tab: str | None) -> None:
        """Navigate to EXACTLY the (view, tab) an entry needs, every time —
        re-checking a marker after a later mutation's traversal moved the
        confluence tab away must not silently read a stale/absent DOM."""
        if view and self._current_view != view:
            self.goto_view(view)
        if tab and self._current_tab != tab:
            self.goto_confluence_tab(tab)

    def text_content(self, selector: str) -> str | None:
        return self.page.evaluate(
            "(s)=>{var e=document.querySelector(s); return e? e.textContent : null;}",
            selector,
        )

    def get_attr(self, selector: str, attr: str) -> str | None:
        return self.page.evaluate(
            "(a)=>{var e=document.querySelector(a[0]); "
            "return e? e.getAttribute(a[1]) : null;}",
            [selector, attr],
        )

    def ref_log(self) -> list[dict]:
        return self.page.evaluate("()=>REF.log || []")


# ── Direction 1 runner ──────────────────────────────────────────────────────
def run_direction1(h: Harness, entries: list[dict]) -> tuple[bool, list[str]]:
    all_ok = True
    failing: list[str] = []
    for e in entries:
        h.ensure(e.get("view"), e.get("tab"))
        ok = True
        detail = ""
        if e["check"] == "href":
            got = h.get_attr(e["selector"], "href")
            ok = got == e["equals"]
            detail = f"selector={e['selector']} href={got!r} expected={e['equals']!r}"
        elif e["check"] == "attr":
            hay_parts = [h.get_attr(e["selector"], a) or "" for a in e["attrs"]]
            hay = " \x1f ".join(hay_parts)
            missing_en = [s for s in e.get("must_contain_en", []) if s not in hay]
            missing_zh = [s for s in e.get("must_contain_zh", []) if s not in hay]
            ok = not missing_en and not missing_zh
            detail = (f"selector={e['selector']} attrs={e['attrs']} "
                      f"missing_en={missing_en} missing_zh={missing_zh}")
        elif e["check"] in ("text", "text_ci"):
            hay = h.text_content(e["selector"]) or ""
            if e["check"] == "text_ci":
                hay_cmp = hay.lower()
                en_needed = [s.lower() for s in e.get("must_contain_en", [])]
                zh_needed = [s.lower() for s in e.get("must_contain_zh", [])]
            else:
                hay_cmp = hay
                en_needed = e.get("must_contain_en", [])
                zh_needed = e.get("must_contain_zh", [])
            missing_en = [s for s in en_needed if s not in hay_cmp]
            missing_zh = [s for s in zh_needed if s not in hay_cmp]
            ok = not missing_en and not missing_zh
            detail = (f"selector={e['selector']} missing_en={missing_en} "
                      f"missing_zh={missing_zh} got={hay[:120]!r}")
        else:
            ok = False
            detail = f"unknown check kind {e['check']!r}"

        if not ok:
            all_ok = False
            failing.append(e["id"])
        check(f"D1 [{e['capability']}] {e['id']}", ok, detail)
    return all_ok, failing


# ── Direction 2 runner ───────────────────────────────────────────────────────
def run_direction2(h: Harness, html_text: str, receipts_paths: set[str],
                    supplement_paths: set[str]) -> tuple[bool, list[str]]:
    all_ok = True
    failing: list[str] = []

    allowed_data_paths = receipts_paths | supplement_paths
    found_data_paths = set(re.findall(r'data-path="([^"]+)"', html_text))
    extra_data_paths = sorted(found_data_paths - allowed_data_paths)
    ok = not extra_data_paths
    check("D2 [data_registry] every data-path traces to an R3A/R3B.1 receipt", ok,
          f"{len(found_data_paths)} data-path blocks found, "
          f"{len(extra_data_paths)} unmatched: {extra_data_paths}" if extra_data_paths
          else f"{len(found_data_paths)} data-path blocks, all traced")
    if not ok:
        all_ok = False
        failing.append("data_registry:extra_data_path")

    log = h.ref_log()
    unresolved = sorted({e["path"] for e in log
                          if e.get("type") == "fetch" and e.get("result") == "recorded-not-executed"})
    unauthorized = [p for p in unresolved if p not in ALLOWED_UNRESOLVED_FETCHES]
    ok = not unauthorized
    check("D2 [fetch_destinations] every unresolved fetch is a documented exception", ok,
          f"unresolved={unresolved} unauthorized={unauthorized}")
    if not ok:
        all_ok = False
        failing.append("fetch_destinations:unauthorized")

    for fam in DESTINATION_FAMILIES:
        matches = [href for href in h.all_data_ref_nav_hrefs if re.match(fam["pattern"], href)]
        ok = len(matches) >= 1
        check(f"D2 [destination_family] {fam['id']} has >=1 real href", ok,
              f"pattern={fam['pattern']!r} matches={len(matches)} sample={matches[:2]}")
        if not ok:
            all_ok = False
            failing.append(f"family:{fam['id']}")

    unmatched_hrefs = sorted({
        href for href in h.all_data_ref_nav_hrefs
        if not any(re.match(fam["pattern"], href) for fam in DESTINATION_FAMILIES)
    })
    ok = not unmatched_hrefs
    check("D2 [destination_family] every data-ref-nav href matches an allowed family", ok,
          f"total={len(h.all_data_ref_nav_hrefs)} unmatched={len(unmatched_hrefs)} "
          f"sample={unmatched_hrefs[:10]}")
    if not ok:
        all_ok = False
        failing.append("family:unmatched_href")

    return all_ok, failing


def print_summary() -> int:
    n_pass = sum(1 for _n, ok, _d in results if ok)
    n_total = len(results)
    print(f"\n{n_pass}/{n_total} inventory checks passed.")
    return 0 if n_pass == n_total else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--json", default=str(EXPECTED_JSON_PATH))
    ap.add_argument("--no-write-expected", action="store_true",
                     help="don't overwrite expected_inventory.json (used by the mutation "
                          "suite so a mutated-copy run never touches the real artifact)")
    args = ap.parse_args()

    candidate_path = Path(args.candidate)
    if not candidate_path.exists():
        print(f"missing candidate: {candidate_path}", file=sys.stderr)
        return 2

    entries, meta = build_expected_inventory()

    if not args.no_write_expected:
        out = {"entries": entries, **meta}
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    receipts = load_json(RECEIPTS_PATH)
    receipts_paths = {e["path"] for e in receipts["entries"]
                       if e["path"] != "correction/UNREPRESENTED.md"}
    supplement = load_json(RECEIPTS_SUPPLEMENT_PATH)
    supplement_paths = {e["path"] for e in supplement["entries"]
                         if e["path"] != "sector_cycles_data.js"}

    html_text = candidate_path.read_text(encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.goto(candidate_path.as_uri(), wait_until="load")
        page.wait_for_timeout(1000)
        h = Harness(page)
        h.full_traverse()

        run_direction1(h, entries)
        run_direction2(h, html_text, receipts_paths, supplement_paths)

        ctx.close()
        browser.close()

    return print_summary()


if __name__ == "__main__":
    raise SystemExit(main())
