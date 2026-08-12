"""Wiring tests for the HK + Canada Risk Radar dialogs (W2 of
research/RISK_RADAR_COUNTRY_PORT_MASTERPLAN.md).

`tests/test_risk_radar_dlg_partial.py` pins the shared PARTIAL's contract (absent-safety,
copy law, shell derivation). This file pins the two country BUILDERS that feed it:

  1. `_radar_dlg_vm` never raises — not on an empty view-model, not on a view-model whose
     stores returned partial/None rows. Every section is its own try/except, so a store
     that failed drops ONE payload, and the macro then renders nothing for it. A build
     that dies here takes the whole page down, which is the failure mode the try/except
     ladder exists to prevent.
  2. The ctx it emits is *shaped* the way the partial's contract says (tone vocabulary,
     bilingual twins on every user-visible string, no bar on a row with no honest scale).
  3. The copy law: no falsifier vocabulary, no "validated" (CI-guarded elsewhere too),
     no glance-tier jargon, and a zh twin for every en string.
  4. Canada's small-card severity pill is DERIVED from the radar state, not the literal
     "HIGH" it shipped with until 2026-08-11 — a caution read wearing a risk-off face.

Fast by construction: `_radar_dlg_vm` is a pure function of the view-model dict, so
nothing here touches a store, a network, or a full page build.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]

# Shape mirrors engine/market_state.py `_radar_to_rd` — which always emits every key.
_RD = {
    "state": "caution", "top_score": 61, "label_en": "USD / HKD funding",
    "label_zh": "美元／港元资金", "state_zh": "警戒",
    "do_en": "A risk is building — stay normal, just watch it.",
    "do_zh": "风险在积累 — 保持正常，留意即可。", "gross": 0.97,
    "dd5": 0.08, "dd10": 0.17, "dd21": 0.31, "dd_lift": 1.0,
    "dd_base": {"h5": 0.077, "h10": 0.174, "h21": 0.309},
    "is_loud": True, "forward_log": None, "cycle": None, "counterread": None,
    "amp": 0, "amp_flags_en": [], "amp_flags_zh": [], "recovery": None,
    "scares": [{"label_en": "USD / HKD funding", "label_zh": "美元／港元资金",
                "score": 61.0, "band": "caution",
                "firing_legs": [{"leg": "usd_strength", "pctile": 0.81}]}],
    "contagion": {"level": "low", "line_en": "Pressure from abroad: low",
                  "line_zh": "海外传导压力：低",
                  "top_exporters": [{"market": "kr", "name_en": "South Korea",
                                     "name_zh": "韩国", "dd21": 0.1488}]},
    "track": {"windows": {"y1": {"alerts": {"n": 0, "tp": 0, "hit_rate": None}}}},
    "fx_context": {"cnh_basis_bps": -34.0, "cnh_basis_state": "normal",
                   "usd_dir": "strengthening", "as_of": "2026-08-10", "stale": False},
}

# A view-model with every HK store readable.
_VM_HK = {
    "market_state": {"radar": _RD},
    "index_health": [{"ticker": "^HSI", "dist200": 6.4},
                     {"ticker": "^HSCE", "dist200": -2.8}],
    "event_strip": [{"date": "2026-08-12", "name_en": "US CPI", "name_zh": "美国 CPI",
                     "importance": "high"},
                    {"date": "2026-08-14", "name_en": "HK GDP", "name_zh": "香港 GDP",
                     "importance": "high"}],
    "funding": {"peg": {"level": 7.8459, "state": "weak-side (outflow)"},
                "hibor_on": 2.19, "hibor_on_chg20": -0.31, "asof": "2026-08-05"},
    "vhsi": {"level": 18.75, "pctile": 36, "chg20": -3.64},
    "internals": {"southbound": {"net": 20.2, "cum_20d": 242.0, "pos_days_20": 8}},
    "cbbc_map": {"bellwethers": [{"ticker": "^HSI", "bull_bear_ratio": 0.9,
                                  "leverage_state": "balanced"}]},
    "setups": {"leaders": [{"ticker": "2359.HK", "name": "WuXi AppTec",
                            "name_zh": "药明康德"},
                           {"ticker": "2269.HK", "name": "WuXi Biologics",
                            "name_zh": "药明生物"}],
               "leadership": {"state": "quiet", "cohesion_now": 0.2,
                              "broad_breadth_pct": 65.4}},
}

# A view-model with every Canada store readable.
_VM_CA = {
    "market_state": {"radar": _RD},
    "benchmark": {"name": "S&P/TSX Composite", "dist200": 9.9, "price": 36458.33},
    "overlay": {"terms_of_trade": "improving", "factors": [
        {"key": "oil", "label": "WTI crude oil", "risk": "neutral", "level": 82.08},
        {"key": "gold", "label": "Gold", "risk": "on", "level": 4459.3},
        {"key": "copper_gold", "label": "Copper / Gold", "risk": "off", "level": 0.0015},
    ]},
    "pair": {"usdcad": {"level": 1.3951, "chg_20d_pct": -1.05},
             "copper_gold": {"level": 0.0015, "chg_20d_pct": -0.34}},
    "breadth": {"pct_above_200": 71.0, "pct_above_50": 63.6, "state": "broad"},
}
_LATEST_HK = {"date": "2026-08-11"}
_LATEST_CA = {"date": "2026-08-10", "liquidity_overlay": "neutral"}


def _vm_fns():
    from scripts.build_canada import _radar_dlg_vm as ca_vm
    from scripts.build_hk import _radar_dlg_vm as hk_vm
    return {"hk": (hk_vm, _VM_HK, _LATEST_HK), "ca": (ca_vm, _VM_CA, _LATEST_CA)}


def _strings(obj):
    """Every string the ctx would put in front of a user, flattened."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("leg", "level", "tone"):     # raw codes, never rendered as-is
                continue
            out += _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _strings(v)
    elif isinstance(obj, str):
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# 1. Absent-safety — the whole reason each payload has its own try/except
# ---------------------------------------------------------------------------
class TestAbsentSafe:
    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    @pytest.mark.parametrize("vm,latest", [
        ({}, {}),
        ({"market_state": None}, {"date": None}),
        ({"market_state": {"radar": {}}}, {"date": "2026-08-11"}),
        # the Undefined-vs-None trap: keys PRESENT but None, and rows missing fields
        ({"market_state": {"radar": {"scares": [{}], "contagion": {}, "track": {}}},
          "index_health": [{"ticker": "^HSI"}], "benchmark": {}, "funding": {"peg": None},
          "vhsi": {}, "internals": {"southbound": {}}, "cbbc_map": {"bellwethers": []},
          "setups": {}, "overlay": {"factors": [{}]}, "pair": {}, "breadth": {},
          "event_strip": [{}]}, {"date": "2026-08-11"}),
    ], ids=["empty", "none-state", "empty-radar", "sparse"])
    def test_never_raises(self, mkt, vm, latest):
        fn = _vm_fns()[mkt][0]
        ctx = fn(dict(vm), dict(latest))
        assert isinstance(ctx, dict)

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_a_dead_store_drops_only_its_own_payload(self, mkt):
        """A store that raises on read must not take its neighbours with it."""
        fn, vm, latest = _vm_fns()[mkt]

        class Boom(dict):
            def get(self, *a, **k):
                raise RuntimeError("store exploded")

        broken = dict(vm)
        broken["funding" if mkt == "hk" else "overlay"] = Boom()
        ctx = fn(broken, latest)
        # the tiles, which read a DIFFERENT store, still came through
        assert ctx.get("overseas"), "a dead store took an unrelated payload with it"
        assert ctx.get("asof") == latest["date"]


# ---------------------------------------------------------------------------
# 2. Shape — the ctx contract the partial documents
# ---------------------------------------------------------------------------
class TestCtxShape:
    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_tone_vocabulary_is_closed(self, mkt):
        """tone drives --rrd-c off the zh-flipping token family; an unknown tone
        silently paints muted, which reads as 'nothing to see here'."""
        fn, vm, latest = _vm_fns()[mkt]
        ctx = fn(vm, latest)
        allowed = {"down", "warn", "up", "muted"}
        seen = []
        for section in ("policy_chips", "factors"):
            for row in ctx.get(section) or []:
                seen.append(row.get("tone"))
        for k in ("leading", "overseas"):
            if isinstance(ctx.get(k), dict) and ctx[k].get("tone"):
                seen.append(ctx[k]["tone"])
        assert seen, "no toned rows produced at all"
        assert set(seen) <= allowed, set(seen) - allowed

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_every_en_string_has_a_zh_twin(self, mkt):
        fn, vm, latest = _vm_fns()[mkt]
        ctx = fn(vm, latest)

        def walk(node, path=""):
            if isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
                return
            if not isinstance(node, dict):
                return
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    walk(v, f"{path}.{k}")
                elif k.endswith("_en") and v:
                    twin = k[:-3] + "_zh"
                    assert node.get(twin), f"{path}.{k} has no {twin}"
                    assert re.search(r"[一-鿿]", str(node[twin])), \
                        f"{path}.{twin} carries no Chinese — transliterated English"

        walk(ctx)

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_bar_only_where_an_honest_0_100_scale_exists(self, mkt):
        """`pct` draws a magnitude bar. A price, a count or a ratio has no ceiling to
        draw against — inventing one is the vetoed fake-magnitude-bar idiom."""
        fn, vm, latest = _vm_fns()[mkt]
        for row in fn(vm, latest).get("factors") or []:
            pct = row.get("pct")
            if pct is None:
                continue
            assert 0 <= pct <= 100, f"{row.get('label_en')} bar is off-scale: {pct}"

    def test_hk_payloads_present_when_every_store_reads(self):
        ctx = _vm_fns()["hk"][0](_VM_HK, _LATEST_HK)
        assert ctx["leading"]["stretch_pct"] == 6.4
        assert ctx["leading"]["leg"] == "usd_strength"
        assert ctx["overseas"]["level"] == "low"
        assert ctx["track"] == {"n": 0, "tp": 0, "hit_rate": None}
        assert len(ctx["calendar"]) == 2
        labels = [c["label_en"] for c in ctx["policy_chips"]]
        assert labels == ["Peg distance", "Borrowing cost"]
        assert "联汇偏离" in [c["label_zh"] for c in ctx["policy_chips"]]
        rows = {f["label_en"]: f for f in ctx["factors"]}
        assert set(rows) == {"Fear gauge", "Southbound flow", "Leverage bets"}
        assert rows["Southbound flow"]["value"] == "+¥242亿"   # already in 亿, not re-scaled
        assert rows["Leverage bets"]["pct"] is None            # a ratio has no 0-100 scale
        assert ctx["factors_note_en"] and ctx["factors_note_zh"]
        assert [r["ticker"] for r in ctx["leaders"]["rows"]] == ["2359.HK", "2269.HK"]
        assert ctx["fx"]["usd_dir"] == "strengthening"

    def test_ca_payloads_present_when_every_store_reads(self):
        ctx = _vm_fns()["ca"][0](_VM_CA, _LATEST_CA)
        assert ctx["leading"]["stretch_pct"] == 9.9
        assert "calendar" not in ctx, "Canada has no calendar engine — omit, don't fake"
        labels = [c["label_en"] for c in ctx["policy_chips"]]
        assert labels == ["Policy stance", "Canadian dollar"]
        rows = {f["label_en"]: f for f in ctx["factors"]}
        assert set(rows) == {"Oil (WTI)", "Gold", "Copper vs gold", "Participation"}
        assert rows["Participation"]["pct"] == 71      # a share IS an honest 0-100 scale
        assert rows["Oil (WTI)"]["pct"] is None        # a price is not
        assert rows["Copper vs gold"]["value"] == "-0.3%"
        assert "tailwind" in ctx["factors_note_en"]    # terms_of_trade == improving
        assert "顺风" in ctx["factors_note_zh"]

    def test_ca_leaders_is_an_honest_absence_not_an_empty_table(self):
        ctx = _vm_fns()["ca"][0](_VM_CA, _LATEST_CA)
        assert not ctx["leaders"].get("rows")
        assert ctx["leaders"]["absent_en"].startswith("Leader coverage building")
        assert "数据积累中" in ctx["leaders"]["absent_zh"]

    def test_ca_fx_drops_the_offshore_yuan_block(self):
        """attach_fx_context also carries China's CNH basis. Passed through verbatim it
        would print a 'Yuan pressure' row on a Canadian page — from the dialog's own FX
        section AND from the embedded .rrx card, which reads cnh_basis_state directly.
        Defence at both ends: the radar dict is scoped right after the attach, and the
        ctx projection carries only the dollar."""
        from scripts.build_canada import _ca_scope_fx_context
        ctx = _vm_fns()["ca"][0](_VM_CA, _LATEST_CA)
        assert ctx["fx"]["usd_dir"] == "strengthening"
        assert "cnh_basis_state" not in ctx["fx"]
        assert "cnh_basis_bps" not in ctx["fx"]

        radar = {"fx_context": {"cnh_basis_bps": -34.0, "cnh_basis_state": "normal",
                                "usd_dir": "weakening", "as_of": "2026-08-10",
                                "stale": True, "built_date": "2026-08-10"}}
        _ca_scope_fx_context(radar)
        assert radar["fx_context"] == {"usd_dir": "weakening", "as_of": "2026-08-10",
                                       "stale": True, "built_date": "2026-08-10"}
        # absent-safe: no radar, no fx_context, a non-dict — all no-ops, never raise
        for bad in (None, {}, {"fx_context": None}, {"fx_context": "nope"}):
            _ca_scope_fx_context(bad)

    @pytest.mark.parametrize("mkt,dist,bench", [("hk", -0.2, "Hang Seng"),
                                                ("ca", 0.3, "The TSX")])
    def test_a_sub_half_percent_stretch_prints_words_not_a_zero(self, mkt, dist, bench):
        """"0% below its 200-day average" is a number that says nothing (Law 3)."""
        fn, vm, latest = _vm_fns()[mkt]
        vm = dict(vm)
        if mkt == "hk":
            vm["index_health"] = [{"ticker": "^HSI", "dist200": dist}]
        else:
            vm["benchmark"] = {"dist200": dist}
        lead = fn(vm, latest)["leading"]
        assert lead["stretch_pct"] is None
        assert "200-day average" in lead["bench_en"] and bench in lead["bench_en"]
        assert "200日均线" in lead["bench_zh"]


# ---------------------------------------------------------------------------
# 3. Copy law (DESIGN_DOCTRINE §5 / CLAUDE.md epistemics)
# ---------------------------------------------------------------------------
class TestCopyLaw:
    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    @pytest.mark.parametrize("banned", [
        # falsifier vocabulary is never front-facing (operator 2026-07-27, #3821)
        "falsifier", "refuted", "证伪",
        # CI-guarded overclaim
        "validated", "已验证", "经验证",
        # internal vocabulary banned at the glance tier (DESIGN_DOCTRINE Law 2)
        "display-tier", "gauntlet", "prereg", "z-score", "percentile", "K-of-N",
        "risk-off", "leverage_state", "terms_of_trade", "pctile",
    ])
    def test_banned_vocabulary_absent(self, mkt, banned):
        fn, vm, latest = _vm_fns()[mkt]
        blob = " ".join(_strings(fn(vm, latest))).lower()
        assert banned.lower() not in blob, banned

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_the_profile_caveat_is_rewritten_not_passed_through(self, mkt):
        """engine/risk_radar_intl.py's caveats are written for the engine's own audience
        ('the external legs', 'least US-coupled of the three', and — for China — the
        CI-forbidden word 'validated'). The dialog footnote must carry the plain-word
        rewrite, never the raw string."""
        from engine import risk_radar_intl as rri
        prof = rri.HK_PROFILE if mkt == "hk" else rri.CA_PROFILE
        fn, vm, latest = _vm_fns()[mkt]
        ctx = fn(vm, latest)
        assert ctx["caveat_en"] and ctx["caveat_zh"]
        assert ctx["caveat_en"] != prof.caveat_en
        for jargon in ("US-coupling", "external legs", "emerging-only", "recent era"):
            assert jargon.lower() not in ctx["caveat_en"].lower(), jargon

    def test_hk_says_out_loud_that_it_has_no_breadth_history(self):
        """HK_PROFILE.breadth_group is None — the leg that does most of the work on the
        other two reads cannot be measured here. Plain-word disclosure IS the compliant
        form of 'nulls printed' (DESIGN_DOCTRINE Law 5)."""
        from engine import risk_radar_intl as rri
        assert rri.HK_PROFILE.breadth_group is None, "premise changed — revisit this copy"
        ctx = _vm_fns()["hk"][0](_VM_HK, _LATEST_HK)
        note = ctx["factors_note_en"].lower()
        assert "breadth" in note or "broadly" in note
        assert "广度" in ctx["factors_note_zh"]

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_no_markup_or_quotes_that_would_break_a_data_tip_attribute(self, mkt):
        """Tips are emitted into data-tip-en/zh attributes — a raw double quote or a tag
        would break out of the attribute (and title= is CI-banned for translated text)."""
        fn, vm, latest = _vm_fns()[mkt]
        for s in _strings(fn(vm, latest)):
            assert '"' not in s, s
            assert "<" not in s and ">" not in s, s


# ---------------------------------------------------------------------------
# 4. Render — the ctx each builder emits, through the real partial
# ---------------------------------------------------------------------------
class TestRendersThroughThePartial:
    @staticmethod
    def _render(mkt, ctx):
        env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
        tpl = env.from_string(
            '{% import "_risk_radar_dlg.html.j2" as rrd %}'
            "{{ rrd.risk_radar_dlg(mkt, rd, rd.scares, ctx) }}"
        )
        # Canada's radar carries a yuan-free fx_context in production — the builder
        # strips it right after the attach (`_ca_scope_fx_context`), so the embedded
        # .rrx card cannot emit a "Yuan pressure" row on a Canadian page.
        rd = dict(_RD)
        if mkt == "ca":
            rd = dict(_RD)
            from scripts.build_canada import _ca_scope_fx_context
            rd["fx_context"] = dict(_RD["fx_context"])
            _ca_scope_fx_context(rd)
        return tpl.render(mkt=mkt, rd=rd, ctx=ctx)

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_one_asof_and_one_footer(self, mkt):
        fn, vm, latest = _vm_fns()[mkt]
        html = self._render(mkt, fn(vm, latest))
        assert html.count('class="rrd-foot"') == 1
        assert html.count(f"As of {latest['date']}") == 1
        assert html.count(f"数据截至 {latest['date']}") == 1

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_shell_is_the_page_dialog_the_entry_points_already_open(self, mkt):
        fn, vm, latest = _vm_fns()[mkt]
        html = self._render(mkt, fn(vm, latest))
        px = {"hk": "hkx", "ca": "cax"}[mkt]
        assert f'id="{px}-dlg-risk"' in html
        assert f'class="{px}-dlg"' in html
        assert f"{px}CloseDlg()" in html

    @pytest.mark.parametrize("mkt", ["hk", "ca"])
    def test_no_translated_text_in_title_attributes(self, mkt):
        fn, vm, latest = _vm_fns()[mkt]
        assert "title=" not in self._render(mkt, fn(vm, latest))

    def test_ca_renders_no_calendar_and_no_yuan_row(self):
        ctx = _vm_fns()["ca"][0](_VM_CA, _LATEST_CA)
        html = self._render("ca", ctx)
        assert "Calendar" not in html and "日历" not in html
        assert "Currency backdrop" in html          # the dollar row still renders
        assert "Leader coverage building" in html   # the honest absence, not a table
        # The dialog's OWN currency section carries the dollar and nothing else. (The
        # embedded .rrx card emits a yuan row of its own regardless of payload; the
        # partial hides every .rrx-fxc inside .rrd, and the builder has already stripped
        # the CNH numbers, so nothing Chinese is visible or quantified here.)
        fx = html[html.index("Currency backdrop"):]
        fx = fx[:fx.index("rrd-foot")]
        assert "Yuan pressure" not in fx and "人民币压力" not in fx
        assert "bp<" not in fx
        assert "rrd-fxrow" in fx and "A headwind for this market" in fx
        assert ".rrx-fxc" in (ROOT / "templates" / "_risk_radar_dlg.css.j2").read_text(
            encoding="utf-8"), "the .rrx duplicate-row suppression was removed"

    def test_hk_renders_its_tiles_chips_and_rows(self):
        ctx = _vm_fns()["hk"][0](_VM_HK, _LATEST_HK)
        html = self._render("hk", ctx)
        for token in ("Leading", "Overseas", "Track record", "Calendar",
                      "Peg distance", "联汇偏离", "Fear gauge", "Southbound flow",
                      "Leverage bets", "The local backdrop", "Leaders"):
            assert token in html, token


# ---------------------------------------------------------------------------
# 5. Canada's small-card severity pill — derived, not a literal
# ---------------------------------------------------------------------------
_CAX = (ROOT / "templates" / "canada.html.j2").read_text(encoding="utf-8")


def _sev_ladder() -> str:
    """The five {% set _rr_sev_* %} lines from the Canada pullback card, verbatim."""
    start = _CAX.index("{% set _rr_sev_col")
    end = _CAX.index("%}", _CAX.index("{% set _rr_sev_zh", start)) + 2
    return _CAX[start:end]


class TestCanadaSeverityPill:
    @pytest.mark.parametrize("state,en,zh,col", [
        ("caution",  "CAUTION",  "谨慎", "var(--warn)"),
        ("elevated", "ELEVATED", "偏高", "var(--down)"),
        ("risk-off", "HIGH",     "高",   "var(--down)"),
    ])
    def test_pill_word_and_colour_follow_the_radar_state(self, state, en, zh, col):
        """The card is shown for all three states; until 2026-08-11 it shouted a
        hardcoded red HIGH for every one of them, so a caution read wore a risk-off
        face. Same three-tier ladder china.html.j2 already moved to."""
        env = Environment(autoescape=False)
        out = env.from_string(
            _sev_ladder() + "{{ _rr_sev_en }}|{{ _rr_sev_zh }}|{{ _rr_sev_col }}"
        ).render(_risk_state=state).strip()
        assert out == f"{en}|{zh}|{col}"

    def test_no_hardcoded_severity_literal_survives_in_the_card(self):
        card = _CAX[_CAX.index("{% set _rr_sev_col"):_CAX.index("{% else %}",
                                                                _CAX.index("{% set _rr_sev_col"))]
        assert "t('HIGH','高')" not in card, "the hardcoded pill is back"
        assert "{{ t(_rr_sev_en, _rr_sev_zh) }}" in card

    def test_severity_colour_rides_only_the_zh_flipping_token_family(self):
        """Risk colour must come from --down/--warn/--up (theme.css swaps them under zh,
        Asia convention), never a literal hex the flip cannot reach."""
        ladder = _sev_ladder()
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", ladder), "literal hex in the pill ladder"
        assert not re.search(r"rgba?\(", ladder), "literal rgb() in the pill ladder"
        for tok in ("var(--warn)", "var(--down)"):
            assert tok in ladder


# ---------------------------------------------------------------------------
# 6. Both pages import the partial and open it at the id their JS already knows
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page,px", [("hk.html.j2", "hkx"), ("canada.html.j2", "cax")])
def test_page_wires_the_shared_partial_at_the_existing_dialog_id(page, px):
    src = (ROOT / "templates" / page).read_text(encoding="utf-8")
    assert '{% import "_risk_radar_dlg.html.j2" as rrd %}' in src
    assert "rrd.risk_radar_dlg(" in src
    # the bespoke body is gone — one dialog per id, or the page ships two of them
    assert src.count(f'id="{px}-dlg-risk"') == 0, "a second hand-rolled body survived"
    # the JS the entry points call is untouched
    assert f"window.{px}OpenDlg={px}OpenDlg" in src
    assert f"{px}OpenDlg('{px}-dlg-risk')" in src


# ---------------------------------------------------------------------------
# 7. China's two conditions gauges — LABEL <-> SOURCE, pinned so it cannot swap
#
# The old bespoke `#cnx-dlg-risk` had them crossed: "Deep-drawdown gauge" over
# `conditions.recession` (the macro SLOWDOWN gauge) and "Slowdown gauge" over
# `conditions.drawdown` (the A-share DEEP-DRAWDOWN risk gauge). It went unnoticed for
# months because both of its charts read `…​.chart_html`, a key scripts/build_china.py
# never writes (it writes `recession_html` / `drawdown_html` ON `conditions`), so the
# charts were dead markup. Porting the dialog made the crossed labels visible.
# ---------------------------------------------------------------------------
_CN_COND = {
    "recession": {"score": 51.0, "label": "high"},
    "drawdown_risk": {"score": 22.0, "band": "low"},
    "recession_html": "<svg data-src=RECESSION></svg>",
    "drawdown_html": "<svg data-src=DRAWDOWN></svg>",
}


def _cn_gauges():
    from scripts.build_china import _radar_dlg_vm as cn_vm
    ctx = cn_vm({"market_state": {"radar": _RD}},
                {"date": "2026-08-11", "conditions": dict(_CN_COND)})
    return {g["label_en"]: g for g in (ctx.get("gauges") or [])}


def test_china_gauge_labels_match_the_series_they_draw():
    g = _cn_gauges()
    assert set(g) == {"Slowdown gauge", "Deep-drawdown gauge"}
    # the macro slowdown legs (credit impulse / PPI / PMI / M1-M2 / property / GDP)
    assert g["Slowdown gauge"]["chart_html"] == _CN_COND["recession_html"]
    assert g["Slowdown gauge"]["score"] == 51
    assert g["Slowdown gauge"]["label_zh"] == "放缓仪表"
    # the A-share stress rank (slowdown + margin froth + flat CGB + QVIX + turnover)
    assert g["Deep-drawdown gauge"]["chart_html"] == _CN_COND["drawdown_html"]
    assert g["Deep-drawdown gauge"]["score"] == 22
    assert g["Deep-drawdown gauge"]["label_zh"] == "深跌仪表"


def test_china_gauge_premise_still_holds_in_the_engine():
    """If the engine ever renames or repurposes these keys, this reds BEFORE the labels
    silently start describing the wrong series again."""
    from engine import china_conditions as cc
    assert "slowdown / recession gauge" in cc.china_recession.__doc__
    assert "drawdown-risk gauge" in cc.china_drawdown.__doc__
    src = (ROOT / "scripts" / "build_china.py").read_text(encoding="utf-8")
    # the chart the builder stamps as the slowdown chart is the recession series
    assert 'cond["recession_html"] = _ilx(ch.get("recession")' in src
    assert 'aria_en="Slowdown gauge chart"' in src
    assert 'cond["drawdown_html"] = _ilx(ch.get("drawdown")' in src
    assert 'aria_en="Drawdown gauge chart"' in src


def test_china_gauge_read_words_come_from_the_engine_band_not_a_local_threshold():
    """The first port re-banded the slowdown score at 60/40, cut points the gauge's own
    history-anchored bands (_REC_BANDS = 26/45) contradict — a 51 read 'elevated' on one
    scale and 'high' on the other."""
    from engine import china_conditions as cc
    assert cc._REC_BANDS == (26.0, 45.0)
    src = (ROOT / "scripts" / "build_china.py").read_text(encoding="utf-8")
    block = src[src.index("# ── Gauges:"):src.index("# ── Leaders:")]
    assert '(60, "high"' not in block and '(40, "elevated"' not in block
    assert 'rec.get("label")' in block and 'dd.get("band")' in block


def test_china_says_the_local_rows_are_not_inputs_to_the_score():
    """CN_PROFILE's caveat ends 'the internal froth legs are excluded (they mean-revert)':
    margin, options fear, limit-up and southbound are NOT radar legs. The plain-word
    rewrite dropped that, so the section read as a causal breakdown of the headline."""
    from scripts.build_china import _radar_dlg_vm as cn_vm
    ctx = cn_vm({"market_state": {"radar": _RD}}, {"date": "2026-08-11"})
    assert "context" in ctx["factors_note_en"].lower()
    assert "背景" in ctx["factors_note_zh"]
    for banned in ("validated", "已验证", "falsifier", "证伪", "refuted"):
        assert banned.lower() not in (ctx["factors_note_en"] + ctx["factors_note_zh"]).lower()


# ---------------------------------------------------------------------------
# 8. ONE as-of per dialog — a lagging FX feed is disclosed in the merged footer,
#    never as a second timestamp inside the currency block.
# ---------------------------------------------------------------------------
def test_a_lagging_fx_feed_adds_no_second_asof_stamp():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    tpl = env.from_string('{% import "_risk_radar_dlg.html.j2" as rrd %}'
                          "{{ rrd.risk_radar_dlg('cn', rd, none, ctx) }}")
    ctx = {"asof": "2026-08-11",
           "fx": {"usd_dir": "strengthening", "stale": True, "built_date": "2026-08-08"}}
    html = tpl.render(rd=_RD, ctx=ctx)
    assert "Currency data as of" not in html and "汇率数据截至" not in html
    # twice = once in the l-en span, once in the l-zh twin — one visible per language
    assert html.count("2026-08-08") == 2
    assert "As of 2026-08-11, currency readings from 2026-08-08." in html
    assert "数据截至 2026-08-11，汇率读数为 2026-08-08。" in html
    assert html.count('class="rrd-fnote"') == 0
    # same date on both -> no clause at all, not the stamp printed twice
    ctx["fx"]["built_date"] = "2026-08-11"
    same = tpl.render(rd=_RD, ctx=ctx)
    assert "currency readings from" not in same
    assert same.count("As of 2026-08-11") == 1


# ---------------------------------------------------------------------------
# 9. China's ctx under the same copy law HK and Canada are held to (W1 shipped the
#    CN builder with no test of its own — only the partial and the two W2 builders
#    were covered).
# ---------------------------------------------------------------------------
_VM_CN = {
    "market_state": {"radar": dict(_RD, label_en="Breadth breakdown (all-boats)", scares=[
        {"label_en": "Breadth breakdown (all-boats)", "label_zh": "广度普跌（普跌）",
         "score": 61.0, "band": "caution",
         "firing_legs": [{"leg": "cn_breadth", "pctile": 0.8}]}])},
    "index_health": [{"ticker": "000001.SS", "dist200": 7.1}],
    "internals": {"pboc": {"bias": "easing", "rrr_big": 8.5},
                  "margin": {"pctile": 62},
                  "southbound": {"cum_20d": 24200.0, "pos_days_20": 13}},
    "cn_market_state_json": {"external": {"usdcnh": {"quote": 7.21, "chg_pct": 0.12}}},
    "cn_participation_json": {"margin_to_mcap": 2.44, "qvix": 18.2, "qvix_z": 0.6,
                              "date": "2026-08-08"},
    "cn_microstructure_json": {"latest_aggregate": {"limit_up_count": 58,
                                                    "sealed_up_close": 31,
                                                    "lianban_2plus": 9}},
    "event_strip": [{"date": "2026-08-15", "name_en": "LPR fix", "name_zh": "LPR 报价"}],
    "top_setups": [{"ticker": "600118.SS", "name": "China Satellite", "name_zh": "中国卫星"}],
}
_LATEST_CN = {"date": "2026-08-11", "conditions": dict(_CN_COND)}


def _cn_ctx():
    from scripts.build_china import _radar_dlg_vm as cn_vm
    return cn_vm(dict(_VM_CN), dict(_LATEST_CN))


@pytest.mark.parametrize("banned", [
    "falsifier", "refuted", "证伪", "validated", "已验证",
    "display-tier", "display-only", "gauntlet", "prereg", "z-score", "percentile",
    "K-of-N", "risk-off", "pctile", "qvix_z", "latest_aggregate", "lianban",
])
def test_cn_banned_vocabulary_absent(banned):
    assert banned.lower() not in " ".join(_strings(_cn_ctx())).lower(), banned


def test_cn_strings_are_attribute_safe_and_have_zh_twins():
    ctx = _cn_ctx()
    # gauges[].chart_html is pre-rendered SVG passed through |safe — markup by design
    ctx_no_svg = {k: v for k, v in ctx.items() if k != "gauges"}
    for s in _strings(ctx_no_svg) + _strings(
            [{k: v for k, v in g.items() if k != "chart_html"} for g in ctx["gauges"]]):
        assert '"' not in s and "<" not in s and ">" not in s, s

    def walk(node, path=""):
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                walk(v, f"{path}.{k}")
            elif k.endswith("_en") and v and k != "chart_html":
                twin = k[:-3] + "_zh"
                assert node.get(twin), f"{path}.{k} has no {twin}"
                assert re.search(r"[一-鿿]", str(node[twin])), f"{path}.{twin} is not Chinese"

    walk({k: v for k, v in ctx.items() if k != "gauges"})
    for g in ctx["gauges"]:
        assert re.search(r"[一-鿿]", g["label_zh"])
        if g["read_en"]:
            assert re.search(r"[一-鿿]", g["read_zh"])


def test_cn_tone_vocabulary_is_closed():
    ctx = _cn_ctx()
    allowed = {"down", "warn", "up", "muted"}
    seen = [r.get("tone") for sec in ("policy_chips", "factors", "gauges")
            for r in (ctx.get(sec) or [])]
    assert seen and set(seen) <= allowed, set(seen) - allowed
