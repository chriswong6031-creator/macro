"""Render the finite BioCatalyst D0a reference board to deterministic PNGs.

This is intentionally a reference renderer, not product UI and not a browser test.
It produces the committed source-of-truth PNG corpus from synthetic data only, using
SVG plus the macOS-native ``sips`` rasterizer so the repository does not acquire a
design-tool or competitor-asset dependency. Production D0b must replace the draft
capture receipt with browser screenshots against the same finite manifest.

Usage:
    python3 mockups/refs/biocatalyst/d0a/render_reference.py
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]

VIEWPORTS = {
    "desktop": (1440, 900),
    "tablet": (820, 1180),
    "mobile": (390, 844),
}

# Each of the 24 required viewport × theme × language × motion combinations is
# deliberately assigned one primary state. Together they cover the reference pack's
# full state vocabulary without pretending that every screen is a live product page.
CELLS = (
    ("desktop", "dark", "en", "standard", "catalyst_radar"),
    ("desktop", "dark", "en", "reduced", "change_tape_correction"),
    ("desktop", "dark", "zh", "standard", "explorer_dense"),
    ("desktop", "dark", "zh", "reduced", "asset_ambiguous_identity"),
    ("desktop", "light", "en", "standard", "trial_peer_matrix"),
    ("desktop", "light", "en", "reduced", "company_partial"),
    ("desktop", "light", "zh", "standard", "regulatory_mixed_sources"),
    ("desktop", "light", "zh", "reduced", "evidence_thread_expanded"),
    ("tablet", "dark", "en", "standard", "catalyst_radar"),
    ("tablet", "dark", "en", "reduced", "explorer_dense"),
    ("tablet", "dark", "zh", "standard", "change_tape_correction"),
    ("tablet", "dark", "zh", "reduced", "historical_mode"),
    ("tablet", "light", "en", "standard", "company_partial"),
    ("tablet", "light", "en", "reduced", "trial_peer_matrix"),
    ("tablet", "light", "zh", "standard", "asset_ambiguous_identity"),
    ("tablet", "light", "zh", "reduced", "regulatory_mixed_sources"),
    ("mobile", "dark", "en", "standard", "explorer_dense"),
    ("mobile", "dark", "en", "reduced", "locked"),
    ("mobile", "dark", "zh", "standard", "asset_ambiguous_identity"),
    ("mobile", "dark", "zh", "reduced", "empty"),
    ("mobile", "light", "en", "standard", "evidence_thread_expanded"),
    ("mobile", "light", "en", "reduced", "source_outage"),
    ("mobile", "light", "zh", "standard", "change_tape_correction"),
    ("mobile", "light", "zh", "reduced", "historical_mode"),
)

COPY = {
    "en": {
        "nav": ("Radar", "Explorer", "Dossiers", "Change Tape", "Workbench", "Alerts", "Data / API"),
        "tag": "FACTS FIRST · RESEARCH CONTEXT",
        "status": "Registry fact · As known 16:00 UTC · Partial",
        "source": "ClinicalTrials.gov · Evidence thread",
        "authority": "Research context — no trade call",
        "tray": "Research tray · 03 pinned questions",
        "inspect": "Inspect evidence",
    },
    "zh": {
        "nav": ("催化雷达", "探索", "档案", "变更记录", "研究台", "提醒", "数据 / API"),
        "tag": "事实优先 · 研究背景",
        "status": "登记事实 · 截至 16:00 UTC · 部分覆盖",
        "source": "ClinicalTrials.gov · 证据线索",
        "authority": "研究背景 — 不构成交易建议",
        "tray": "研究托盘 · 已固定 03 个问题",
        "inspect": "查看证据",
    },
}

STATE_COPY = {
    "catalyst_radar": ("Catalyst Radar", "Source-reported dates and fresh record changes", "Next 30 days · 08 source-backed records"),
    "explorer_dense": ("Explorer", "108 records · long filters preserved", "Recruiting · Phase 2 · Oncology · Updated ≤ 30d"),
    "trial_peer_matrix": ("Trial Protocol Peer Matrix", "Explicit cohort · fields remain source-labelled", "Phase · enrollment · endpoints · sites"),
    "company_partial": ("Company dossier", "Financing context unavailable — no PIT adapter", "Company identity · source-backed facts only"),
    "asset_ambiguous_identity": ("Asset × indication", "Relationship needs review — two candidates remain separate", "No issuer or ticker inference"),
    "regulatory_mixed_sources": ("Regulatory dossier", "Regulator-native and company-reported claims remain distinct", "Application history · source class visible"),
    "change_tape_correction": ("Change Tape", "Earlier registry record corrected", "Before / after · source path · correction lineage"),
    "evidence_thread_expanded": ("Evidence Thread", "One claim, its context, and its exact source locator", "Source excerpt · record version · known-at"),
    "historical_mode": ("Historical view", "As known 12 Jun 2026 · current updates paused", "Point-in-time context"),
    "source_outage": ("Source temporarily unavailable", "Last good record is 6h old; live freshness is unknown", "ClinicalTrials.gov status · inspect health"),
    "locked": ("This view needs access", "No denied values are shown", "Access boundary · no layout shift"),
    "empty": ("No matching records", "Your filters returned no source-backed result", "Phase 2 · Rare disease · Updated ≤ 7d"),
}

STATE_COPY_ZH = {
    "catalyst_radar": ("催化雷达", "来源披露的日期与最新记录变更", "未来30天 · 08条来源事实"),
    "explorer_dense": ("探索", "108条记录 · 长筛选条件已保留", "招募中 · 2期 · 肿瘤 · 30天内更新"),
    "trial_peer_matrix": ("试验方案对比", "明确队列 · 字段始终标注来源", "阶段 · 入组 · 终点 · 站点"),
    "company_partial": ("公司档案", "融资背景不可用 — 尚未接入 PIT 适配器", "公司身份 · 仅来源事实"),
    "asset_ambiguous_identity": ("资产 × 适应症", "关系需要复核 — 两个候选保持独立", "不推断发行人或代码"),
    "regulatory_mixed_sources": ("监管档案", "监管原始事实与公司披露保持区分", "申请历史 · 来源类别可见"),
    "change_tape_correction": ("变更记录", "早期登记记录已更正", "前后对比 · 来源路径 · 更正链"),
    "evidence_thread_expanded": ("证据线索", "一个结论、上下文与精确来源定位", "来源摘录 · 记录版本 · 已知时间"),
    "historical_mode": ("历史视图", "截至 2026年6月12日 · 当前更新暂停", "时点背景"),
    "source_outage": ("来源暂不可用", "最近有效记录为6小时前；实时新鲜度未知", "ClinicalTrials.gov 状态 · 查看健康度"),
    "locked": ("此视图需要访问权限", "不显示被拒绝的数据", "访问边界 · 布局不跳动"),
    "empty": ("没有匹配记录", "当前筛选没有来源支持的结果", "2期 · 罕见病 · 7天内更新"),
}


def _colors(theme: str) -> dict[str, str]:
    if theme == "light":
        return {
            "bg": "#f4f1e9", "panel": "#fbfaf5", "panel2": "#ebe8df", "ink": "#18222d",
            "muted": "#65717d", "line": "#d3d0c7", "mint": "#167b65", "violet": "#6744a4",
            "amber": "#a86110", "red": "#a33a3a", "glow": "#bfe7dc",
        }
    return {
        "bg": "#0c1015", "panel": "#111821", "panel2": "#17212c", "ink": "#edf0e7",
        "muted": "#99a7b4", "line": "#283644", "mint": "#54d7b7", "violet": "#ad8cff",
        "amber": "#f1ae54", "red": "#fb7a7a", "glow": "#153d38",
    }


def _t(value: str, x: float, y: float, size: float, fill: str, *, weight: int = 400, anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, PingFang SC, sans-serif" '
        f'font-size="{size:.1f}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def _pill(value: str, x: float, y: float, width: float, color: str, text: str) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="22" rx="11" fill="{color}" opacity="0.18"/>'
        + _t(value, x + 10, y + 15, 10, text, weight=650)
    )


def _bars(x: float, y: float, width: float, color: str, *, count: int = 12) -> str:
    parts = []
    gap = width / count
    for index in range(count):
        height = 16 + ((index * 23) % 47)
        parts.append(
            f'<rect x="{x + index * gap:.1f}" y="{y + 68 - height:.1f}" width="{max(3, gap - 5):.1f}" height="{height:.1f}" rx="2" fill="{color}" opacity="{0.25 + index / (count * 2):.2f}"/>'
        )
    return "".join(parts)


def _main_module(state: str, lang: str, x: float, y: float, w: float, h: float, c: dict[str, str]) -> str:
    title, subtitle, detail = (STATE_COPY_ZH if lang == "zh" else STATE_COPY)[state]
    status_color = c["mint"]
    if state in {"source_outage", "locked", "empty"}:
        status_color = c["amber"] if state == "source_outage" else c["muted"]
    if state in {"asset_ambiguous_identity", "change_tape_correction"}:
        status_color = c["violet"] if state == "asset_ambiguous_identity" else c["amber"]
    label = "STATE / " + state.replace("_", " ").upper()
    state_label = "状态 / " + state.replace("_", " ").upper() if lang == "zh" else label
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{c["panel"]}" stroke="{c["line"]}"/>',
        _t(state_label, x + 26, y + 23, 9, status_color, weight=720),
        _t(title, x + 26, y + 53, min(27, w / 18), c["ink"], weight=680),
        _t(subtitle, x + 26, y + 77, min(14, w / 32), c["muted"]),
        _pill(detail, x + 26, y + 91, min(w - 52, max(130, len(detail) * 5.4)), status_color, c["ink"]),
        f'<line x1="{x + 26}" y1="{y + 129}" x2="{x + w - 26}" y2="{y + 129}" stroke="{c["line"]}"/>',
    ]
    # The envelope is intentionally dense. It prevents a glamorous module title
    # from hiding the things an operator actually needs to qualify a value.
    envelope_y = y + 149
    envelope_labels = (
        ("Fact class", "Registry fact"), ("As known", "16:00 UTC"),
        ("Precision", "Month / exact"), ("Coverage", "Partial"),
    ) if lang == "en" else (
        ("事实类别", "登记事实"), ("已知时间", "16:00 UTC"),
        ("精度", "月份 / 精确"), ("覆盖", "部分"),
    )
    columns = 4 if w > 600 else 2
    card_w = (w - 52 - (columns - 1) * 8) / columns
    for index, (key, value) in enumerate(envelope_labels):
        row, col = divmod(index, columns)
        card_x = x + 26 + col * (card_w + 8)
        card_y = envelope_y + row * 43
        parts.extend((
            f'<rect x="{card_x:.1f}" y="{card_y:.1f}" width="{card_w:.1f}" height="35" rx="7" fill="{c["panel2"]}"/>',
            _t(key, card_x + 10, card_y + 13, 9, c["muted"], weight=600),
            _t(value, card_x + 10, card_y + 27, 10, status_color if key in {"Coverage", "覆盖"} else c["ink"], weight=650),
        ))
    body_y = envelope_y + (82 if columns == 2 else 54)
    if state == "trial_peer_matrix":
        headers = ("Trial", "Phase", "Enrollment", "Primary endpoint") if lang == "en" else ("试验", "阶段", "入组", "主要终点")
        col = (w - 52) / 4
        for i, header in enumerate(headers):
            parts.append(_t(header, x + 26 + i * col, body_y, 11, c["muted"], weight=650))
        peer_rows = (
            ("NCT00000001", "Phase 2", "184 est.", "Week 24 response"),
            ("NCT00000002", "Phase 2", "216 est.", "Month 6 function"),
            ("NCT00000003", "Phase 1/2", "72 actual", "Dose-limiting safety"),
            ("NCT00000004", "Phase 3", "540 est.", "Time to event"),
        )
        for row, values in enumerate(peer_rows):
            ry = body_y + 20 + row * 38
            parts.append(f'<rect x="{x + 26}" y="{ry}" width="{w - 52}" height="29" rx="6" fill="{c["panel2"]}"/>')
            for i, value in enumerate(values):
                parts.append(_t(value, x + 34 + i * col, ry + 19, 10, c["ink"] if i == 0 else c["muted"], weight=550 if i == 0 else 400))
    elif state in {"explorer_dense", "catalyst_radar", "change_tape_correction"}:
        if state == "explorer_dense":
            records = (
                ("NCT00000001 · AUR-101", "Recruiting · Phase 2 · 184 planned", "Primary completion: Aug 2026"),
                ("NCT00000002 · SYN-44", "Active, not recruiting · Phase 2", "Record change: endpoints updated"),
                ("NCT00000003 · NWK-9", "Recruiting · Phase 1/2 · 72 actual", "Last verified: 2h ago"),
                ("NCT00000004 · OBI-7", "Completed · Phase 3 · 540 planned", "Completion date: reported month"),
            )
        elif state == "catalyst_radar":
            records = (
                ("Aug 09 · exact date", "Registry field update · source fact", "NCT00000001 · status changed"),
                ("Aug 2026 · reported month", "Primary completion constraint", "NCT00000002 · precision preserved"),
                ("Q3 2026 · reported quarter", "Company-reported milestone", "Source class remains company-reported"),
                ("No disclosed date", "Missing constraint", "No timing prediction shown"),
            )
        else:
            records = (
                ("Primary endpoint", "Before: Week 12 response", "After: Week 24 response · version 8 → 9"),
                ("Enrollment", "Before: 160 estimated", "After: 184 estimated · source path shown"),
                ("Record correction", "Earlier value retained", "Correction linked; no materiality label"),
                ("Site listing", "Before: 14 locations", "After: 18 locations · no activation claim"),
            )
        for row, (headline, qualifier, receipt) in enumerate(records):
            ry = body_y + row * 55
            accent = status_color if row in {0, 2} else c["line"]
            parts.extend((
                f'<rect x="{x + 26}" y="{ry}" width="{w - 52}" height="43" rx="8" fill="{c["panel2"]}"/>',
                f'<rect x="{x + 26}" y="{ry}" width="3" height="43" rx="1.5" fill="{accent}"/>',
                _t(headline if lang == "en" else headline.replace("Before", "前").replace("After", "后"), x + 42, ry + 16, 11, c["ink"], weight=640),
                _t(qualifier if lang == "en" else qualifier.replace("source", "来源").replace("Record", "记录"), x + 42, ry + 31, 9.5, c["muted"]),
                _t(("Evidence" if lang == "en" else "证据"), x + w - 43, ry + 16, 9, c["mint"], weight=650, anchor="end"),
                _t(("Inspect" if lang == "en" else "查看"), x + w - 43, ry + 32, 9, c["ink"], weight=650, anchor="end"),
            ))
    elif state in {"locked", "empty", "source_outage"}:
        icon = "×" if state == "empty" else ("⌁" if state == "source_outage" else "⊘")
        parts.extend((
            _t(icon, x + w / 2, body_y + 68, 52, status_color, weight=300, anchor="middle"),
            _t(("Inspect source health" if state == "source_outage" and lang == "en" else "查看来源健康度" if state == "source_outage" else "Clear one filter" if state == "empty" and lang == "en" else "清除一个筛选" if state == "empty" else "View access options" if lang == "en" else "查看访问选项"), x + w / 2, body_y + 108, 12, c["ink"], weight=650, anchor="middle"),
            _t(("Last good value is visibly qualified; stale data is never fresh." if lang == "en" else "最近有效值已明确标识；过期数据不会伪装成最新。"), x + w / 2, body_y + 136, 10, c["muted"], anchor="middle"),
        ))
    else:
        left_w = (w - 60) * 0.56
        right_w = (w - 60) - left_w
        parts.extend((
            f'<rect x="{x + 26}" y="{body_y}" width="{left_w}" height="76" rx="10" fill="{c["panel2"]}"/>',
            _t(("Reported value" if lang == "en" else "披露数值"), x + 42, body_y + 25, 11, c["muted"], weight=650),
            _t(("Partial / requires review" if lang == "en" else "部分覆盖 / 需要复核"), x + 42, body_y + 53, 20, status_color, weight=650),
            f'<rect x="{x + 34 + left_w}" y="{body_y}" width="{right_w}" height="76" rx="10" fill="{c["panel2"]}"/>',
            _t(("What is missing" if lang == "en" else "缺少内容"), x + 50 + left_w, body_y + 25, 11, c["muted"], weight=650),
            _t(("PIT identity / rights" if lang == "en" else "PIT 身份 / 权利"), x + 50 + left_w, body_y + 53, 14, c["amber"], weight=650),
            _bars(x + 26, body_y + 100, w - 52, status_color),
            f'<rect x="{x + 26}" y="{body_y + 184}" width="{w - 52}" height="54" rx="9" fill="{c["panel2"]}"/>',
            _t(("Evidence thread has 3 source facts · 1 unresolved edge · open exact locators" if lang == "en" else "证据线索含3条来源事实 · 1条未解决关系 · 可打开精确定位"), x + 42, body_y + 206, 10, c["ink"], weight=600),
            _t(("Pin question to Research Tray  →" if lang == "en" else "将问题固定到研究托盘  →"), x + 42, body_y + 226, 10, c["mint"], weight=650),
        ))
    # A real workbench closes the loop: provenance is inspectable and the next
    # research action is explicit. This shared lower rail removes the old generic
    # dead canvas while keeping the visual hierarchy calm.
    lower_y = max(body_y + 238, y + h - 202)
    lower_h = y + h - 20 - lower_y
    if w > 560:
        left_w = (w - 60) * 0.58
        right_x = x + 34 + left_w
        right_w = (w - 60) - left_w
        parts.extend((
            f'<rect x="{x + 26}" y="{lower_y}" width="{left_w}" height="{lower_h}" rx="10" fill="{c["panel2"]}"/>',
            _t(("Source timeline" if lang == "en" else "来源时间线"), x + 42, lower_y + 23, 10, c["muted"], weight=650),
            _t(("Known-at order keeps the earlier record visible" if lang == "en" else "已知时间顺序保留早期记录"), x + 42, lower_y + 42, 10, c["ink"], weight=600),
            _bars(x + 42, lower_y + 50, left_w - 32, status_color, count=8),
            _t("v7", x + 42, lower_y + lower_h - 14, 9, c["muted"]),
            _t("v8", x + left_w / 2, lower_y + lower_h - 14, 9, c["muted"], anchor="middle"),
            _t(("v9 · current" if lang == "en" else "v9 · 当前"), x + left_w + 18, lower_y + lower_h - 14, 9, c["mint"], weight=650, anchor="end"),
            f'<rect x="{right_x}" y="{lower_y}" width="{right_w}" height="{lower_h}" rx="10" fill="{c["panel2"]}"/>',
            _t(("Research next" if lang == "en" else "下一步研究"), right_x + 16, lower_y + 23, 10, c["muted"], weight=650),
            _t(("Compare the source record" if lang == "en" else "比较来源记录"), right_x + 16, lower_y + 47, 11, c["ink"], weight=650),
            _t(("Pin a question · open exact evidence" if lang == "en" else "固定问题 · 打开精确证据"), right_x + 16, lower_y + 69, 9.5, c["mint"], weight=650),
            _t(("No ranking or trade instruction" if lang == "en" else "无排名或交易指令"), right_x + 16, lower_y + lower_h - 15, 9, c["muted"]),
        ))
    else:
        parts.extend((
            f'<rect x="{x + 26}" y="{lower_y}" width="{w - 52}" height="{lower_h}" rx="10" fill="{c["panel2"]}"/>',
            _t(("Research next" if lang == "en" else "下一步研究"), x + 42, lower_y + 24, 10, c["muted"], weight=650),
            _t(("Compare source record · pin question" if lang == "en" else "比较来源记录 · 固定问题"), x + 42, lower_y + 48, 11, c["ink"], weight=650),
            _t(("Known-at order · exact evidence · no trade call" if lang == "en" else "已知时间顺序 · 精确证据 · 非交易建议"), x + 42, lower_y + 70, 9, c["mint"], weight=650),
        ))
    return "".join(parts)


def _svg(viewport: str, theme: str, lang: str, motion: str, state: str) -> str:
    width, height = VIEWPORTS[viewport]
    c = _colors(theme)
    copy = COPY[lang]
    rail_w = 190 if viewport == "desktop" else (132 if viewport == "tablet" else 0)
    right_w = 294 if viewport == "desktop" else (0 if viewport == "mobile" else 0)
    gap = 18
    main_x = rail_w + gap
    main_w = width - main_x - right_w - (gap if right_w else gap)
    head_h = 102 if viewport == "mobile" else 88
    content_y = head_h + 18
    content_h = height - content_y - 70
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{c["bg"]}"/>',
        f'<rect x="0" y="0" width="{width}" height="{head_h}" fill="{c["panel"]}"/>',
        f'<line x1="0" y1="{head_h}" x2="{width}" y2="{head_h}" stroke="{c["line"]}"/>',
        _t("BIOCATALYST", 22, 33, 17, c["ink"], weight=750),
        _t(copy["tag"], 22, 54, 9, c["mint"], weight=700),
        _t(("Reduced motion" if motion == "reduced" and lang == "en" else "减少动态" if motion == "reduced" else "Standard motion" if lang == "en" else "标准动态"), width - 18, 32, 10, c["muted"], weight=600, anchor="end"),
    ]
    if viewport == "mobile":
        mobile_status = "Registry fact · 16:00 · Partial" if lang == "en" else "登记事实 · 16:00 · 部分覆盖"
        parts.append(_pill(mobile_status, 16, 68, width - 32, c["mint"], c["ink"]))
    else:
        parts.append(_pill(copy["status"], width - 226, 44, 208, c["mint"], c["ink"]))
    if rail_w:
        parts.append(f'<rect x="0" y="{head_h}" width="{rail_w}" height="{height - head_h}" fill="{c["panel"]}"/>')
        for index, item in enumerate(copy["nav"]):
            y = 123 + index * 43
            active = (index == 0 and state == "catalyst_radar") or (index == 1 and state == "explorer_dense") or (index == 2 and state in {"company_partial", "asset_ambiguous_identity", "regulatory_mixed_sources"}) or (index == 3 and state == "change_tape_correction") or (index == 4 and state == "trial_peer_matrix")
            if active:
                parts.append(f'<rect x="12" y="{y - 19}" width="{rail_w - 24}" height="31" rx="8" fill="{c["glow"]}"/>')
            label = item
            parts.append(_t(label, 26, y, 12 if viewport == "desktop" else 10, c["ink"] if active else c["muted"], weight=650 if active else 500))
    if viewport == "mobile":
        parts.extend((
            f'<rect x="16" y="{content_y}" width="{width - 32}" height="34" rx="10" fill="{c["panel2"]}"/>',
            _t(("Explorer  ›  synthetic cohort" if lang == "en" else "探索  ›  合成队列"), 30, content_y + 22, 11, c["ink"], weight=600),
        ))
        content_y += 49
        content_h -= 49
    parts.append(_main_module(state, lang, main_x, content_y, main_w, content_h, c))
    if right_w:
        rx = width - right_w - gap
        parts.extend((
            f'<rect x="{rx}" y="{content_y}" width="{right_w}" height="{content_h}" rx="18" fill="{c["panel"]}" stroke="{c["line"]}"/>',
            _t(copy["source"], rx + 20, content_y + 33, 12, c["ink"], weight=650),
            _t(("Evidence envelope" if lang == "en" else "证据包络"), rx + 20, content_y + 56, 11, c["mint"], weight=650),
            f'<line x1="{rx + 20}" y1="{content_y + 72}" x2="{rx + right_w - 20}" y2="{content_y + 72}" stroke="{c["line"]}"/>',
            _t(("Exact source locator" if lang == "en" else "精确来源定位"), rx + 20, content_y + 104, 10, c["muted"]),
            _t("/protocolSection/statusModule", rx + 20, content_y + 126, 10, c["ink"], weight=600),
            f'<rect x="{rx + 20}" y="{content_y + 148}" width="{right_w - 40}" height="82" rx="9" fill="{c["panel2"]}"/>',
            _t(("Record excerpt" if lang == "en" else "记录摘录"), rx + 32, content_y + 169, 9, c["muted"], weight=650),
            _t(("Overall status: Recruiting" if lang == "en" else "总体状态：招募中"), rx + 32, content_y + 191, 11, c["ink"], weight=650),
            _t(("Version 9 · submitted 15:42 UTC" if lang == "en" else "版本9 · 15:42 UTC 提交"), rx + 32, content_y + 213, 9, c["muted"]),
            _t(("Completeness" if lang == "en" else "完整性"), rx + 20, content_y + 267, 10, c["muted"]),
            _pill(("Partial" if lang == "en" else "部分"), rx + 20, content_y + 281, 90, c["amber"], c["ink"]),
            _t(("1 unresolved relationship" if lang == "en" else "1条未解决关系"), rx + 20, content_y + 331, 10, c["violet"], weight=650),
            f'<line x1="{rx + 20}" y1="{content_y + 350}" x2="{rx + right_w - 20}" y2="{content_y + 350}" stroke="{c["line"]}"/>',
            _t(("Open source record  →" if lang == "en" else "打开来源记录  →"), rx + 20, content_y + 380, 10, c["mint"], weight=650),
        ))
    # Footer doubles as the intentionally bounded timestamp mask location: stable in refs,
    # but masked in browser captures because production timestamps are live.
    parts.extend((
        f'<rect x="0" y="{height - 52}" width="{width}" height="52" fill="{c["panel"]}"/>',
        f'<line x1="0" y1="{height - 52}" x2="{width}" y2="{height - 52}" stroke="{c["line"]}"/>',
        _t(copy["tray"], 20, height - 29, 11, c["ink"], weight=650),
        _t(("NCT00000001" if lang == "en" else "NCT00000001"), 20, height - 13, 9, c["mint"], weight=650),
        _t(("Question: what changed?" if lang == "en" else "问题：发生了什么变化？"), 95, height - 13, 9, c["muted"]),
        _t(copy["authority"], width - 18, height - 22, 10, c["muted"], anchor="end"),
        "</svg>",
    ))
    return "".join(parts)


def _destination(viewport: str, theme: str, lang: str, motion: str) -> Path:
    return HERE / f"d0a_{viewport}_{theme}_{lang}_{motion}.png"


def render() -> None:
    if sys.platform != "darwin":
        raise SystemExit("D0a references are committed from the macOS-native sips renderer")
    for viewport, theme, lang, motion, state in CELLS:
        svg_path = HERE / f"d0a_{viewport}_{theme}_{lang}_{motion}.svg"
        png_path = _destination(viewport, theme, lang, motion)
        svg_path.write_text(_svg(viewport, theme, lang, motion, state), encoding="utf-8")
        subprocess.run(
            ["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        svg_path.unlink()
        print(png_path.relative_to(ROOT))


if __name__ == "__main__":
    render()
