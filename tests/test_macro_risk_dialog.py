"""Structural freeze for the US Macro #dlg-risk Risk Radar modal.

Presentation-only: these tests encode the Sol design freeze (verdict → why →
watch → context) without snapshotting the full page. They import the dashboard
render helpers rather than cloning the view-model factory.
"""
from __future__ import annotations

import re

from tests.test_dashboard_template_render import _base_vm, _env

SCARES = (
    ("global", "Global breadth breakdown", "全球广度破位", 51.5),
    ("bubble", "Trend extension watch", "趋势延伸观察", 48.0),
    ("credit", "Credit stress", "信用压力", 34.0),
    ("growth", "Growth scare / defensive rotation", "增长恐慌/防御轮动", 33.6),
    ("rates", "Rates / inflation shock", "利率/通胀冲击", 25.9),
    ("internals", "Breadth internals", "内部广度", 20.9),
    ("vol", "Volatility event", "波动率事件", 1.2),
)

THEMES = (
    ("ai-software", "AI Software", "AI 软件", 4, 9),
    ("ai-agents", "AI Agents", "AI 智能体", 6, 1),
    ("other-software", "Other Software", "其他软件", 8, 6),
    ("semicap-equipment", "Semicap Equipment", "半导体设备", 11, -2),
    ("ai-hardware", "AI Hardware", "AI 硬件", 14, -4),
    ("cyber", "Cybersecurity", "网络安全", 16, 2),
    ("cloud", "Cloud Infra", "云基础设施", 19, 0),
)


def _scares():
    rows = []
    for key, en, zh, score in SCARES:
        rows.append(
            {
                "scare": key,
                "label_en": en,
                "label_zh": zh,
                "score": score,
                "band": "calm",
                "firing_legs": (
                    [
                        {
                            "leg": "growth_cyc_def",
                            "pctile": 0.72,
                            "confirmed": True,
                        }
                    ]
                    if key == "growth"
                    else []
                ),
            }
        )
    return rows


def _radar(**overrides):
    rd = {
        "state": "calm",
        "state_zh": "平静",
        "top_score": 34,
        "label_en": "Growth scare / defensive rotation",
        "label_zh": "增长恐慌/防御轮动",
        "do_en": "Normal exposure.",
        "do_zh": "正常仓位。",
        "dd5": 0.02,
        "dd10": 0.06,
        "dd21": 0.13,
        "dd_lift": 0.73,
        "dd_base": {"h5": 0.036, "h10": 0.086, "h21": 0.178},
        "is_loud": False,
        "binding": False,
        "authority": {
            "note_en": "Advisory — sizes risk; does not override the measured tape.",
            "note_zh": "提示性信号——仅调整仓位，不覆盖实测盘面。",
        },
        "cycle": {
            "show": True,
            "label_en": "Midterm year",
            "label_zh": "中期选举年",
            "in_drawdown_window": True,
            "sector_bias": {
                "favor": [{"ticker": "XLU"}],
                "avoid": [{"ticker": "XLY"}],
            },
            "stat_en": "Weaker stretch.",
            "stat_zh": "偏弱时段。",
            "slice_en": "Calendar only.",
            "slice_zh": "仅日历。",
        },
        "contagion": {
            "level": "low",
            "line_en": "No tracked market in risk-off.",
            "line_zh": "追踪市场均无避险警报。",
            "top_exporters": [],
        },
        "cross_asset": {
            "verdict": "converging",
            "absorption_pctile": 0.61,
        },
        "track": {
            "windows": {"y1": {"alerts": {"hit_rate": 0.4, "tp": 8, "n": 20}}}
        },
    }
    rd.update(overrides)
    return rd


def _vm(**updates):
    vm = _base_vm()
    latest = dict(vm["latest"])
    latest["date"] = "2026-08-28"
    latest["fed_stance"] = {"stance": "hawkish"}
    latest["risk_radar"] = {"scares": _scares()}
    vm["latest"] = latest
    vm["market_state"] = {
        "radar": _radar(),
        "components": [],
        "color": "green",
        "score": 62,
        "label_en": "Risk-on",
        "label_zh": "偏好",
        "asof": "2026-08-28",
        "headline_en": "Markets lean risk-on.",
        "headline_zh": "市场偏向风险偏好。",
        "overrides": [],
        "flip_en": None,
        "flip_zh": None,
        "mtf": None,
    }
    vm["sector_heat"] = {
        "as_of": "2026-08-28",
        "rotation": [
            {
                "id": slug,
                "short_name": en,
                "short_name_zh": zh,
                "rank": rank,
                "rank_delta_5d": delta,
                "heat": "heating" if delta > 0 else ("cooling" if delta < 0 else "flat"),
            }
            for slug, en, zh, rank, delta in THEMES
        ],
    }
    vm["leadership_crack"] = {
        "state": "BROKEN",
        "asof": "2026-08-21",
        "med_dd": -0.28,
        "high_window_sessions": 63,
        "share10": 0.7,
        "share30": 0.4,
        "n_total": 10,
        "index_dd": -0.08,
        "worst_members": [
            {"ticker": "NVDA", "dd": -0.32},
            {"ticker": "AVGO", "dd": -0.29},
            {"ticker": "TSM", "dd": -0.27},
            {"ticker": "ASML", "dd": -0.26},
            {"ticker": "AMD", "dd": -0.24},
            {"ticker": "AMAT", "dd": -0.22},
        ],
        "state_since": "2026-06-26",
        "z_vel": -0.4,
        "carnage_share_ema": 0.31,
    }
    vm["fear_euphoria"] = {"fe_score": 98, "band": "Euphoria"}
    vm["fear_greed"] = {
        "dial": 51,
        "label_en": "Neutral",
        "n_legs_qualifying": 6,
        "young_tiles": [],
    }
    vm["froth_fragility"] = {
        "score": 44,
        "band": "watch",
        "band_zh": "关注",
        "provisional": True,
        "quadrant_en": "Heat is concentrated, not broad.",
        "quadrant_zh": "热度集中，并非全面亢奋。",
        "face_a": {"score": 70},
        "face_b": {"score": 22},
    }
    vm.update(updates)
    return vm


def _render(vm=None, mode="macro") -> str:
    return _env().get_template("dashboard.html.j2").render(**(vm or _vm()), mode=mode)


def _dlg(html: str) -> str:
    start = html.index('id="dlg-risk"')
    rest = html[start:]
    nxt = rest.find('id="dlg-policy"')
    return rest if nxt < 0 else rest[:nxt]


def _default_visible(dlg: str) -> str:
    """Strip collapsed <details> bodies, keeping each <summary>."""

    def _keep_summary(match: re.Match[str]) -> str:
        block = match.group(0)
        summary = re.search(r"<summary\b[^>]*>.*?</summary>", block, re.S)
        return summary.group(0) if summary else ""

    prev = None
    out = dlg
    while prev != out:
        prev = out
        out = re.sub(r"<details\b[^>]*>.*?</details>", _keep_summary, out, flags=re.S)
    return out


def _idx(haystack: str, needle: str) -> int:
    pos = haystack.find(needle)
    assert pos >= 0, f"missing {needle!r}"
    return pos


def test_modal_chrome_and_dialog_contract():
    dlg = _dlg(_render())
    assert 'id="dlg-risk"' in dlg
    assert 'role="dialog"' in dlg
    assert 'aria-modal="true"' in dlg
    assert "Risk Radar" in dlg
    assert "风险雷达" in dlg
    assert 'title="' not in dlg


def test_one_brief_no_driver_banner():
    html = _render()
    dlg = _dlg(html)
    assert dlg.count('class="riskdlg-brief"') == 1 or dlg.count("riskdlg-brief") >= 1
    assert 'class="riskdlg-brief"' in dlg
    vis = _default_visible(dlg)
    assert "mx5-dlg-driver-hd" not in vis
    assert vis.count("34/100") == 1 or vis.count(">34<") + vis.count("34/100") == 1
    assert vis.count("Normal exposure.") == 1


def test_section_order_and_seven_scares():
    dlg = _dlg(_render())
    order = [
        'class="riskdlg-brief"',
        'class="riskdlg-drivers"',
        'class="riskdlg-ladder"',
        'class="riskdlg-sentiment"',
        'class="riskdlg-leadership"',
        'class="riskdlg-method"',
    ]
    positions = [_idx(dlg, name) for name in order]
    assert positions == sorted(positions)
    for _key, en, zh, score in SCARES:
        assert en in dlg
        assert zh in dlg
        assert str(score) in dlg
    assert dlg.count('class="riskdlg-scare"') == 7


def test_drivers_omit_track_record_and_what_to_do():
    vis = _default_visible(_dlg(_render()))
    drivers = vis.split('class="riskdlg-drivers"', 1)[1].split('class="riskdlg-ladder"', 1)[0]
    assert "Track record" not in drivers
    assert "历史记录" not in drivers
    assert "What to do" not in drivers
    assert "应对" not in drivers
    assert "Leading" in drivers
    assert "Calendar" in drivers
    assert "Overseas" in drivers
    assert "Correlation" in drivers
    method = _dlg(_render())
    assert "Track record" in method.split('class="riskdlg-method"', 1)[1]


def test_no_duplicate_overseas_l1_after_leadership():
    dlg = _dlg(_render())
    after = dlg.split('class="riskdlg-leadership"', 1)[1]
    assert "mx5-dlg-eyebrow" not in after.split('class="riskdlg-method"', 1)[0] or (
        "Overseas" not in after.split('class="riskdlg-method"', 1)[0]
        and "海外" not in after.split('class="riskdlg-method"', 1)[0]
    )
    vis = _default_visible(dlg)
    after_vis = vis.split('class="riskdlg-leadership"', 1)[1]
    assert "rkc-ov-grid" not in after_vis


def test_froth_is_advanced_disclosure():
    dlg = _dlg(_render())
    vis = _default_visible(dlg)
    assert 'id="froth-fragility"' not in vis
    assert 'id="froth-fragility"' in dlg
    assert "Advanced sentiment context" in dlg
    assert "进阶情绪背景" in dlg
    assert "provisional" in dlg
    assert "暂定" in dlg
    assert "display context" in dlg.lower() or "展示背景" in dlg


def test_leadership_three_at_rest_seven_accessible():
    dlg = _dlg(_render())
    vis = _default_visible(dlg)
    rest = re.findall(r'class="riskdlg-theme[^"]*"', vis)
    assert sum(1 for c in rest if "riskdlg-theme-more" not in c) == 3
    assert dlg.count('class="riskdlg-theme') >= 7
    assert "View all 7 themes" in dlg
    assert "查看全部 7 个主题" in dlg
    vis_lead = vis.split('class="riskdlg-leadership"', 1)[1]
    assert "rkc-ldr-bars" not in vis_lead
    assert "Residual hardware damage" in dlg or "残余" in dlg
    assert "not today's leader roster" in dlg or "不是当下龙头" in dlg
    assert "rkc-ldr-bars" in dlg


def test_missing_radar_does_not_coerce_calm_or_zero():
    vm = _vm()
    vm["market_state"] = {
        "radar": {},
        "components": [],
        "color": "green",
        "score": 55,
        "label_en": "Risk-on",
        "label_zh": "偏好",
        "asof": "2026-08-28",
        "headline_en": "Markets lean risk-on.",
        "headline_zh": "市场偏向风险偏好。",
        "overrides": [],
        "flip_en": None,
        "flip_zh": None,
        "mtf": None,
    }
    vm["latest"]["risk_radar"] = None
    html = _render(vm)
    dlg = _dlg(html)
    vis = _default_visible(dlg)
    assert "No active risk readings" in vis or "暂无活跃风险读数" in vis
    assert "0/100" not in vis
    assert ">0<" not in vis.split('class="riskdlg-brief"', 1)[-1][:800]


def test_method_and_scare_classes_are_exclusive():
    dlg = _dlg(_render())
    assert re.findall(r'\bclass="riskdlg-method"', dlg)
    assert not re.search(r'class="[^"]*\briskdlg-method\s', dlg)
    assert dlg.count('class="riskdlg-scare"') == 7
    assert not re.search(r'class="[^"]*\briskdlg-scare\s', dlg)
    assert "Fear ↔ Euphoria: regime synthesis" in dlg
    assert "恐惧 ↔ 欣喜：周期综合" in dlg
    assert "sizing, not selection" in dlg
    assert "而非选股" in dlg


def test_missing_horizon_omits_zero_coerce():
    vm = _vm()
    radar = dict(vm["market_state"]["radar"])
    radar["dd5"] = None
    vm["market_state"] = dict(vm["market_state"], radar=radar)
    dlg = _default_visible(_dlg(_render(vm)))
    odds = dlg.split("riskdlg-odds", 1)[1][:1200]
    assert "5d" not in odds or "5日" not in odds or "0%" not in odds.split("5d", 1)[-1][:40]
    assert "10d" in odds
    assert "21d" in odds
    assert "6%" in odds
    assert "13%" in odds
