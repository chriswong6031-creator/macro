"""Build the Research Reports section -> site/reports.html + one page per report.

A small, registry-driven blog/article system for in-depth market reports. Each entry
in REPORTS points at a Jinja article template (extending article_base.html.j2) plus the
metadata used to render the row-based index (reports.html.j2).

Fully static and additive — depends on no live JSON, so it can never break the daily
build. Bilingual (EN/中文) via the same l-en/l-zh spans as the rest of the site.

------------------------------------------------------------------------------
ADD A NEW REPORT (3 steps):
  1. Copy the starter:  templates/_report_TEMPLATE.html.j2
                  ->    templates/report_<slug>.html.j2   (it has inline docs)
  2. Fill its art_kicker / art_toc / art_body blocks (bilingual via t()).
  3. Append one dict to REPORTS below with a matching slug + template. See the
     EXAMPLE entry (commented out) for every field. Date drives index sorting.
Then:  python -m scripts.build_reports   (or let daily.yml run it).

Tag chip colours are defined in report_base.html.j2 (.chip.tag-<key>); reuse an
existing key (macro / fed / rates / equities / crypto / event) or add a CSS rule.
------------------------------------------------------------------------------

Usage: python -m scripts.build_reports
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_reports")

_MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MON_FULL = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]


def _tag(key: str, en: str, zh: str) -> dict:
    return {"key": key, "en": en, "zh": zh}


# ---------------------------------------------------------------------------
# Report registry — newest entries can go anywhere; the index sorts by date.
# ---------------------------------------------------------------------------
REPORTS: list[dict] = [
    {
        "slug": "report_relapse_jul8",
        "template": "report_relapse_jul8.html.j2",
        "date": "2026-07-08",
        "read_min": 18,
        "title_en": "The Relapse",
        "title_zh": "复燃",
        "dek_en": "A tactical companion to The Second Act. The Iran war restarted six weeks early, "
                  "the disinflation glide path took a torpedo, and Hong Kong ripped 3% into a "
                  "global risk-off tape — none of it breaks the 18-month map; it bends the "
                  "schedule. We re-mark our own odds in public, then convert the week's tape into "
                  "a ranked seven-idea buy list with entry timing, sizing, and the exact tripwire "
                  "that proves each wrong: energy that now pays carry, the China platform leg with "
                  "the 1260H caveat, Act II power into weakness, the first Mag-7 trough tranche, "
                  "gold, Bitcoin, and copper — while memory-chip strength stays something you sell.",
        "dek_zh": "《第二幕》的战术姊妹篇。伊朗战争提前六周复燃、反通胀滑翔路径中了一枚鱼雷，而恒指却顶着"
                  "全球避险盘面大涨 3%——这一切都没有推翻 18 个月的路线图，只是弯曲了时间表。本文先公开"
                  "重估我们自己的概率，再把本周盘面转译为一张排序的七点买入清单，附入场时点、仓位与每个"
                  "观点被证伪的确切绊线：现在开始付息的能源、附 1260H 警示的中国平台、趁弱建仓的第二幕"
                  "电力、Mag-7 第一批低谷仓、黄金、比特币与铜——而存储芯片的强势，仍然只能用来卖出。",
        "tags": [
            _tag("equities", "Equities", "股票"),
            _tag("energy", "Energy", "能源"),
            _tag("china", "China", "中国"),
            _tag("macro", "Macro", "宏观"),
            _tag("crypto", "Crypto", "加密"),
        ],
    },
    {
        "slug": "report_second_act",
        "template": "report_second_act.html.j2",
        "date": "2026-07-02",
        "read_min": 45,
        "title_en": "The Second Act",
        "title_zh": "第二幕",
        "dek_en": "The AI boom isn't ending — it's changing hands. Chips and memory had their "
                  "run; the money now flows to power, cooling, optical networking, robots, and "
                  "the payment rails underneath. A month-by-month map from July 2026 to December "
                  "2027: what to own, when to buy it, what the Mag 7 are really worth at their "
                  "cash-flow low, and exactly what would prove us wrong. The best buying window "
                  "on the map: October 2026.",
        "dek_zh": "AI 热潮没有结束 —— 而是在换手。芯片与存储已经跑完了自己的一程；资金正流向电力、散热、"
                  "光模块、机器人，以及底层的支付轨道。这是一份 2026年7月 → 2027年12月 的逐月路线图："
                  "该持有什么、何时买入、七巨头在现金流低谷处的真实价值，以及什么情况会证明我们错了。"
                  "全图最佳买入窗口：2026年10月。",
        "tags": [
            _tag("ai", "AI", "AI"),
            _tag("macro", "Macro", "宏观"),
            _tag("equities", "Equities", "股票"),
            _tag("crypto", "Crypto", "加密"),
            _tag("china", "China", "中国"),
        ],
    },
    {
        "slug": "report_ai_master_plan",
        "template": "report_ai_master_plan.html.j2",
        "date": "2026-07-01",
        "read_min": 30,
        "title_en": "The AI Master Plan",
        "title_zh": "AI 总体规划",
        "dek_en": "Strip the White House AI Action Plan to its mechanisms and it stops being "
                  "industrial policy and becomes the refinancing of the United States — a "
                  "physical-stock strategy that is bubble-dependent by design. A full decode of "
                  "the five levers, why the state went long its own bubble, and where the losses "
                  "are pre-routed — with a predictive pathway that maps how the market is "
                  "front-running the administration’s schedule: distribution now, a midterm-year "
                  "low, and the blow-off deferred to 2027.",
        "dek_zh": "剥开白宫《AI 行动计划》看机制，它就不再是产业政策，而是美国的再融资工程 —— 一套在设计上依赖"
                  "泡沫的“物理存量”战略。全面解码五个杠杆、国家为何做多自己的泡沫、损失被预先路由到何处 —— "
                  "并附一条预测路径，剖析市场如何抢跑政府的时间表：当下派发、中期选举年的低点，以及被推迟"
                  "至 2027 年的“blow-off 冲顶”。",
        "tags": [
            _tag("ai", "AI", "AI"),
            _tag("macro", "Macro", "宏观"),
            _tag("fed", "Fed", "美联储"),
            _tag("china", "China", "中国"),
            _tag("credit", "Credit", "信用"),
        ],
    },
    {
        "slug": "report_bessent_jun24",
        "template": "report_bessent_jun24.html.j2",
        "date": "2026-06-24",
        "read_min": 12,
        "title_en": "The Bessent Bridge",
        "title_zh": "贝森特之桥",
        "dek_en": "One week after the Warsh Shock, the hawkish reset has done the Fed's "
                  "tightening for it — gold under $4,000, the dollar at a 13-month high, and "
                  "the AI-and-semis leadership that led all year finally cracked. Then the "
                  "Treasury Secretary said the quiet part out loud: you can have a strong "
                  "dollar while the Fed cuts. A decode of the staged sequence — setup, not "
                  "destination — and where the debasement trade bottoms.",
        "dek_zh": "沃什冲击一周后，鹰派重置已替美联储完成了紧缩 —— 黄金跌破4000美元、美元创13个月新高、"
                  "今年全程领涨的AI与半导体板块终于裂开。随后，财长道出了潜台词：美联储降息时也能维持"
                  "强势美元。解码这套分阶段的序列 —— 是铺垫，而非终点 —— 以及去货币化交易将在何处筑底。",
        "tags": [
            _tag("fed", "Fed", "美联储"),
            _tag("rates", "Rates", "利率"),
            _tag("crypto", "Crypto", "加密"),
            _tag("macro", "Macro", "宏观"),
        ],
    },
    {
        "slug": "report_warsh_fomc",
        "template": "report_warsh_fomc.html.j2",
        "date": "2026-06-17",
        "read_min": 9,
        "title_en": "The Warsh Shock",
        "title_zh": "沃什冲击",
        "dek_en": "Kevin Warsh's first FOMC as Fed Chair — the hawkish dot-plot turn, the "
                  "press conference that removed forward guidance, the cross-asset reaction, "
                  "and what it means for markets next.",
        "dek_zh": "凯文·沃什出任美联储主席后的首次 FOMC —— 鹰派点阵图的转向、取消前瞻指引的发布会、"
                  "跨资产反应，以及对后市的意义。",
        "tags": [
            _tag("fed", "Fed", "美联储"),
            _tag("rates", "Rates", "利率"),
            _tag("equities", "Equities", "股票"),
            _tag("macro", "Macro", "宏观"),
        ],
    },
    # ----------------------------------------------------------------------
    # EXAMPLE — copy this block, uncomment, and edit to publish a new report.
    # The `template` file must exist (copy templates/_report_TEMPLATE.html.j2).
    # ----------------------------------------------------------------------
    # {
    #     "slug": "report_my_topic",                 # -> site/report_my_topic.html
    #     "template": "report_my_topic.html.j2",     # copied from _report_TEMPLATE
    #     "date": "2026-07-01",                       # YYYY-MM-DD; drives sort + date badge
    #     "read_min": 6,                              # estimated minutes
    #     "title_en": "Headline Here",
    #     "title_zh": "标题",
    #     "dek_en": "One-sentence standfirst shown on the index row and article hero.",
    #     "dek_zh": "用于索引行与文章页眉的一句话导语。",
    #     "tags": [                                    # reuse keys for chip colours
    #         _tag("macro", "Macro", "宏观"),
    #         _tag("rates", "Rates", "利率"),
    #     ],
    # },
]


def _enrich(r: dict) -> dict:
    dt = datetime.strptime(r["date"], "%Y-%m-%d")
    out = dict(r)
    out["mon"] = _MON[dt.month - 1]
    out["day"] = str(dt.day)
    out["year"] = str(dt.year)
    out["date_display"] = f"{_MON_FULL[dt.month - 1]} {dt.day}, {dt.year}"
    return out


def _all_tags(reports: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in reports:
        for tg in r["tags"]:
            seen.setdefault(tg["key"], tg)
    return list(seen.values())


def main() -> int:
    site = config.ROOT / "site"
    site.mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)

    reports = [_enrich(r) for r in REPORTS]
    # newest first for the index + prev/next chaining
    reports.sort(key=lambda r: r["date"], reverse=True)
    all_tags = _all_tags(reports)

    # ---- index ----
    idx = env.get_template("reports.html.j2").render(
        reports=reports, all_tags=all_tags, active_section="research", active_page="reports",
    )
    write_page(site / "reports.html", idx)
    log.info("wrote %s/reports.html (%d reports, %d KB)", site, len(reports), len(idx) // 1024)

    # ---- one page per report ----
    for i, r in enumerate(reports):
        prev_r = reports[i - 1] if i > 0 else None           # newer
        next_r = reports[i + 1] if i + 1 < len(reports) else None  # older
        html = env.get_template(r["template"]).render(
            report=r, reports=reports, prev_report=prev_r, next_report=next_r,
            active_section="research", active_page="reports",
        )
        write_page(site / f"{r['slug']}.html", html)
        log.info("wrote %s/%s.html (%d KB)", site, r["slug"], len(html) // 1024)

    return 0


if __name__ == "__main__":
    sys.exit(main())
