"""Reviewed bilingual display labels for the Macro & Monetary suite (F01).

The ``mastermind.macro_workspace_snapshot.v1`` contract is built out of CLOSED
machine vocabularies — freshness states, null reasons, presence states, evidence
classes, comparability verdicts, direction semantics, units. Those tokens are
producer identifiers. None of them may reach a user's screen raw
(``CURRENT``, ``WARMUP``, ``higher_tighter``, ``USD_bn`` are not English, and
they are certainly not Chinese).

This module is the ONE place that maps each closed vocabulary to a reviewed
``{"en", "zh"}`` pair, so every page in the twelve-workspace suite renders the
same word for the same state. It is pure presentation: it never decides a
state, never transforms a value, and never invents a label for a token it does
not know — an unrecognised token degrades to a readable de-slugged form and is
reported by :func:`unknown_tokens` so a contract extension cannot ship a raw
slug to production unnoticed.

Bilingual law (house rule): a label is a PAIR. Exactly one language is visible
at a time via the site's ``.l-en`` / ``.l-zh`` toggle; a page never shows both.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

# Tokens seen by this process that had no reviewed label. Tests assert this is
# empty for the shipped artifact; the page renders a de-slugged fallback either
# way, so a new owner token degrades honestly instead of blanking the cell.
_UNKNOWN: set[str] = set()

EM_DASH = "—"


def _pair(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


# --- section 7.6 freshness vocabulary ---------------------------------------
FRESHNESS: dict[str, dict[str, str]] = {
    "CURRENT": _pair("Current", "当前有效"),
    "LATE_WITHIN_TOLERANCE": _pair("Late, within tolerance", "延迟但在容忍范围内"),
    "STALE_SOURCE": _pair("Stale source", "数据源已过期"),
    "NOT_YET_RELEASED": _pair("Not yet released", "尚未发布"),
    "SOURCE_FAILED": _pair("Source failed", "数据源获取失败"),
    "RIGHTS_BLOCKED": _pair("Rights blocked", "授权受限"),
    "NOT_COVERED": _pair("Not covered", "未覆盖"),
    "HISTORICAL_AS_KNOWN": _pair("Historical, as known then", "历史（按当时已知）"),
    "SIMULATED": _pair("Simulated", "模拟"),
}

# Tone drives colour only. "Missing" is never drawn as calm or as zero.
FRESHNESS_TONE: dict[str, str] = {
    "CURRENT": "ok",
    "LATE_WITHIN_TOLERANCE": "warn",
    "STALE_SOURCE": "warn",
    "NOT_YET_RELEASED": "neutral",
    "SOURCE_FAILED": "bad",
    "RIGHTS_BLOCKED": "bad",
    "NOT_COVERED": "neutral",
    "HISTORICAL_AS_KNOWN": "neutral",
    "SIMULATED": "warn",
}

# --- section 7.7 null vocabulary --------------------------------------------
NULL_REASON: dict[str, dict[str, str]] = {
    "UNKNOWN": _pair("Unknown", "未知"),
    "NOT_APPLICABLE": _pair("Not applicable", "不适用"),
    "NOT_YET_RELEASED": _pair("Not yet released", "尚未发布"),
    "SOURCE_FAILED": _pair("Source failed", "数据源获取失败"),
    "RIGHTS_BLOCKED": _pair("Rights blocked", "授权受限"),
    "INSUFFICIENT_HISTORY": _pair("Insufficient history", "历史数据不足"),
    "WARMUP": _pair("Warm-up: first accepted print", "预热期：首个已接受读数"),
    "REVISION_PENDING_REBUILD": _pair("Revision pending rebuild", "修订待重建"),
    "DISAGREEMENT": _pair("Sources disagree", "数据源存在分歧"),
    "COMPUTATION_REFUSED": _pair("Computation refused", "拒绝计算"),
    "OUT_OF_REGION": _pair("Outside this region", "超出该地区范围"),
    "NOT_COVERED": _pair("Not covered", "未覆盖"),
}

PRESENCE: dict[str, dict[str, str]] = {
    "PRESENT": _pair("Present", "已具备"),
    "PARTIAL": _pair("Partial", "部分具备"),
    "ABSENT": _pair("Absent", "缺失"),
    "DISAGREEMENT": _pair("Disagreement", "存在分歧"),
}

PRESENCE_TONE: dict[str, str] = {
    "PRESENT": "ok",
    "PARTIAL": "warn",
    "ABSENT": "neutral",
    "DISAGREEMENT": "bad",
}

# --- section 8.1 evidence classes -------------------------------------------
EVIDENCE_CLASS: dict[str, dict[str, str]] = {
    "DESCRIPTIVE": _pair("Descriptive", "描述性"),
    "HISTORICAL_ASSOCIATION": _pair("Historical association", "历史关联"),
    "MECHANISM_SUPPORTED": _pair("Mechanism-supported", "机制支持"),
    "MODEL_HYPOTHESIS": _pair("Model hypothesis", "模型假设"),
}

# What each class is allowed to claim — rendered next to the badge so an
# "association" is never read as proof of causality.
EVIDENCE_CLAIM: dict[str, dict[str, str]] = {
    "DESCRIPTIVE": _pair("States what the accepted data shows.",
                         "陈述已接受数据所显示的事实。"),
    "HISTORICAL_ASSOCIATION": _pair(
        "An association in a named sample. Not evidence of causality.",
        "特定样本中的统计关联，并非因果证据。"),
    "MECHANISM_SUPPORTED": _pair(
        "A governed transmission channel plus current supporting observations.",
        "受管控的传导渠道，并有当前观察佐证。"),
    "MODEL_HYPOTHESIS": _pair(
        "Research-surface hypothesis. Carries no authority on this page.",
        "研究层面的假设，在本页不具备任何权威性。"),
}

CONFIDENCE_BAND: dict[str, dict[str, str]] = {
    "LOW": _pair("Low", "低"),
    "MEDIUM": _pair("Medium", "中"),
    "HIGH": _pair("High", "高"),
}

CONFIDENCE_DIMENSION: dict[str, dict[str, str]] = {
    "data_coverage": _pair("Data coverage", "数据覆盖"),
    "source_health": _pair("Source health", "数据源健康度"),
    "revision_risk": _pair("Revision risk", "修订风险"),
    "method_stability": _pair("Method stability", "方法稳定性"),
    "evidence_breadth": _pair("Evidence breadth", "证据广度"),
    "contradiction_state": _pair("Contradiction", "矛盾状态"),
}

# --- section 7.8 change comparability ---------------------------------------
COMPARABILITY: dict[str, dict[str, str]] = {
    "COMPARABLE": _pair("Comparable with the prior accepted print",
                        "与上一已接受读数可比"),
    "NO_PRIOR": _pair("No comparable prior print", "没有可比的历史读数"),
    "METHOD_CHANGED": _pair("Method version changed — shown as a method change, not a delta",
                            "方法版本已变更 — 按方法变更呈现，而非数值变化"),
    "DEFINITION_INCOMPARABLE": _pair("Definitions are not comparable — numeric comparison refused",
                                     "定义不可比 — 拒绝进行数值比较"),
}

CORRECTION_STATE: dict[str, dict[str, str]] = {
    "none": _pair("No correction recorded", "无更正记录"),
    "corrected": _pair("Corrected", "已更正"),
    "superseded": _pair("Superseded", "已被取代"),
    "unknown": _pair("Correction state unknown", "更正状态未知"),
}

RIGHTS_STATE: dict[str, dict[str, str]] = {
    "OPEN": _pair("Open", "公开"),
    "RIGHTS_BLOCKED": _pair("Rights blocked", "授权受限"),
    "UNKNOWN": _pair("Unknown", "未知"),
}

# --- section 7.5 clock law ---------------------------------------------------
# Order matters: this is the order the evidence drawer lists them in.
CLOCKS: tuple[tuple[str, dict[str, str], dict[str, str]], ...] = (
    ("reference_period", _pair("Reference period", "参考期"),
     _pair("The period the economic value describes.", "该经济数值所描述的期间。")),
    ("observed_at", _pair("Observed", "观察时间"),
     _pair("Native economic or market observation time.", "原生经济或市场观察时间。")),
    ("released_at", _pair("Released", "发布时间"),
     _pair("Provider publication time.", "数据提供方的发布时间。")),
    ("available_at", _pair("First knowable", "首次可知"),
     _pair("Earliest time this value was lawfully knowable to us.",
           "本系统可合法获知该数值的最早时间。")),
    ("collected_at", _pair("Collected", "采集时间"),
     _pair("When Mastermind received it.", "Mastermind 接收到该数据的时间。")),
    ("revised_at", _pair("Revised", "修订时间"),
     _pair("Provider correction or revision time.", "数据提供方的更正或修订时间。")),
    ("calculation_as_of", _pair("Calculation as-of", "计算截止"),
     _pair("Cut-off used for the derived result.", "推导结果所使用的数据截止点。")),
)

# built_at / rendered_at are listed apart because they NEVER establish economic
# freshness (section 7.5, final sentence).
NON_ECONOMIC_CLOCKS: tuple[tuple[str, dict[str, str], dict[str, str]], ...] = (
    ("built_at", _pair("Artifact built", "产物生成"),
     _pair("Producer generation time. Not an economic clock.",
           "生产端生成时间，并非经济时钟。")),
    ("page_built_at", _pair("Page built", "页面生成"),
     _pair("Static page render time. Not an economic clock.",
           "静态页面渲染时间，并非经济时钟。")),
)

# --- direction semantics (owner slugs -> a reader-facing sentence) -----------
DIRECTION: dict[str, dict[str, str]] = {
    "higher_tighter": _pair("Higher = tighter funding", "数值越高＝融资越紧"),
    "higher_stronger": _pair("Higher = stronger support", "数值越高＝支持越强"),
    "higher_more_cushion": _pair("Higher = more cushion", "数值越高＝缓冲越厚"),
    "higher_more_stress": _pair("Higher = more stress", "数值越高＝压力越大"),
    "higher_wider_spread": _pair("Higher = wider spread", "数值越高＝利差越阔"),
    "higher_weaker": _pair("Higher = weaker", "数值越高＝越疲弱"),
    "lower_tighter": _pair("Lower = tighter", "数值越低＝越紧"),
}

# --- units -------------------------------------------------------------------
UNIT: dict[str, dict[str, str]] = {
    "score": _pair("score (0-100)", "评分（0–100）"),
    "USD_bn": _pair("USD bn", "十亿美元"),
    "pct": _pair("%", "%"),
    "percent": _pair("%", "%"),
    "bp": _pair("bp", "基点"),
    "stddev": _pair("std dev", "标准差"),
    "percentile": _pair("percentile (0-1)", "分位（0–1）"),
    "z_score": _pair("z-score", "z 值"),
    "categorical": _pair("category", "类别"),
    "index": _pair("index", "指数"),
    "count": _pair("count", "数量"),
    "ratio": _pair("ratio", "比率"),
}

# --- basis -------------------------------------------------------------------
BASIS: dict[str, dict[str, str]] = {
    "level": _pair("Level", "水平值"),
    "composite_prior_only": _pair("Composite, prior-only inputs", "复合指标（仅使用先验输入）"),
    "roc_over_owner_window": _pair("Rate of change over the owner window", "所有者窗口内的变化率"),
}

# --- owner categorical readings ---------------------------------------------
OWNER_VALUE: dict[str, dict[str, str]] = {
    "contracting": _pair("Contracting", "收缩"),
    "expanding": _pair("Expanding", "扩张"),
    "benign_expansion": _pair("Benign expansion", "良性扩张"),
    "stressed_expansion": _pair("Stressed expansion", "承压扩张"),
    "neutral": _pair("Neutral", "中性"),
    "stable": _pair("Stable", "平稳"),
    "deteriorating": _pair("Deteriorating", "恶化"),
    "improving": _pair("Improving", "改善"),
    # The liquidity_regime producer's quality scale is HYPHENATED, so the
    # underscored keys above never match it. `neutral-hollow` is the value the
    # shipped artifact carries today, and without a reviewed entry it deslugs to
    # a raw token on the page -- the exact leak this table exists to prevent, and
    # the failure `test_the_shipped_artifact_needs_no_unreviewed_label` reports.
    # "Hollow" is the producer's own word for support whose LEVEL reads neutral
    # while its COMPOSITION is mechanical or exhausted; the reviewed copy says
    # that in plain words rather than shipping the jargon.
    "neutral-hollow": _pair("Neutral level, weak composition", "中性水平，结构偏弱"),
}

# --- metric identities -------------------------------------------------------
# The reference product leaks raw provider series ids (ECIWAG, DRTSCILM) into
# its chart legends. Ours resolves every published metric_id to a reviewed
# public name instead; an id with no entry falls back to :func:`deslug` and is
# reported by :func:`unknown_tokens`.
METRIC: dict[str, dict[str, str]] = {
    "funding_pressure": _pair("Funding pressure", "融资压力"),
    "balance_sheet_support": _pair("Balance-sheet support", "资产负债表支持"),
    "net_liquidity_roc_bn": _pair("Net-liquidity rate of change", "净流动性变化率"),
    "rrp_buffer_bn": _pair("Overnight reverse-repo buffer", "隔夜逆回购缓冲"),
    "nfci": _pair("Chicago Fed financial conditions", "芝加哥联储金融状况指数"),
    "ofr_fsi": _pair("OFR financial stress", "OFR 金融压力指数"),
    "hy_oas_pct": _pair("High-yield credit spread", "高收益信用利差"),
    "rates_scare_score": _pair("Rates scare score", "利率恐慌评分"),
}

# --- implication horizons ----------------------------------------------------
HORIZON: dict[str, dict[str, str]] = {
    "current": _pair("Current reading", "当前读数"),
    "days": _pair("Days", "数日"),
    "weeks": _pair("Weeks", "数周"),
    "months": _pair("Months", "数月"),
    "quarters": _pair("Quarters", "数个季度"),
    "cycle": _pair("Cycle", "整个周期"),
}

# --- supported regions -------------------------------------------------------
# The artifact's display_name is English by contract; the reader gets a
# reviewed pair, with the artifact's own name as the fallback.
REGION: dict[str, dict[str, str]] = {
    "US": _pair("United States", "美国"),
    "EU": _pair("Euro area", "欧元区"),
    "JP": _pair("Japan", "日本"),
    "CN": _pair("China", "中国"),
    "GB": _pair("United Kingdom", "英国"),
}

# --- transmission channels ---------------------------------------------------
CHANNEL: dict[str, dict[str, str]] = {
    "funding": _pair("Funding", "融资"),
    "reserves": _pair("Bank reserves", "银行准备金"),
    "credit": _pair("Credit", "信贷"),
    "rates": _pair("Rates", "利率"),
    "duration": _pair("Duration", "久期"),
    "equities": _pair("Equities", "股票"),
    "dollar": _pair("US dollar", "美元"),
    "volatility": _pair("Volatility", "波动率"),
    "lending": _pair("Bank lending", "银行信贷投放"),
}

# --- alert condition kinds (declared, not offered) ---------------------------
ALERT_KIND: dict[str, dict[str, str]] = {
    "state_transition": _pair("Named state transition", "状态切换"),
    "boundary_approach": _pair("Axis boundary approach", "接近坐标轴分界"),
    "component_shock": _pair("Component shock", "分项冲击"),
    "source_stale_or_failed": _pair("Source stale or failed", "数据源过期或失败"),
    "source_revision": _pair("Material source revision", "数据源重大修订"),
    "release_approaching": _pair("Scheduled release approaching", "临近既定发布"),
    "contradiction_change": _pair("Contradiction appears or resolves", "矛盾出现或消解"),
}

# --- F01 Macro Command P2: The Read + the state strip -----------------------
# Design pin `macro_command_P2_design_pin.md` §1/§6. `headline.state_id` is a
# QUADRANT LETTER (A-D, `lib.macro_suite_view._QUADRANT_GRID`) whose meaning is
# entirely local to its own workspace — `B` is "Accelerating momentum, broad
# strength" for `growth_real_economy` and "Tight conditions / Tightening
# impulse" for `financial_conditions`. STATE_WORD / PREDICATE_FORM / STATE_TONE
# are therefore keyed `workspace_id -> state_id -> value` (pin D-1), never on
# a flat state_id and never on freshness. The three tables carry an IDENTICAL
# `(workspace_id, state_id)` key set — a mismatch is a build defect
# (tests/test_macro_command_read_strip.py).
#
# `monetary_policy` and `rates_curves` publish no axes and so never produce a
# `state_id` (§1) — they carry no rows here by design, not by omission; their
# chips render null via the CHIP_NULL_NOTE cause table below.

CHIP_LABEL: dict[str, dict[str, str]] = {
    # F-8: the chip label IS the Read topic word, for all seven market chips —
    # one reviewed pair used in both registers. `coverage` has no Read
    # counterpart and keeps its own label.
    "money": _pair("Money", "资金"),
    # D-3: "Policy rates", not "Central banks" — the source workspace is
    # `monetary_policy`, mapped to the `policy` section; "central banks" names
    # `liquidity_central_banks`, which lives under `money`.
    "policy": _pair("Policy rates", "政策利率"),
    "rates": _pair("Rates", "利率"),
    "inflation": _pair("Inflation", "通胀"),
    "growth": _pair("Growth", "增长"),
    "jobs": _pair("Jobs", "就业"),
    # D-10: "Borrowing", not "Borrowing costs" — measured truncation at 1008px
    # content width; the section itself keeps the longer name.
    "credit": _pair("Borrowing", "融资"),
    "coverage": _pair("Data coverage", "数据覆盖"),
}

STATE_WORD: dict[str, dict[str, dict[str, str]]] = {
    "liquidity_regime": {
        "A": _pair("Ample", "充裕"),
        "B": _pair("Tight but backed", "偏紧但有支撑"),
        "C": _pair("Easy but thin", "宽松但偏薄"),
        "D": _pair("Tight and thin", "偏紧且偏薄"),
    },
    "inflation_system": {
        "A": _pair("Cooling, still sticky", "降温但仍顽固"),
        "B": _pair("Rising and broad", "上升且广泛"),
        "C": _pair("Cooling", "全面降温"),
        "D": _pair("Rising, but narrow", "上升但面窄"),
    },
    "growth_real_economy": {
        "A": _pair("Strong but slowing", "强劲但放缓"),
        "B": _pair("Picking up", "正在加快"),
        "C": _pair("Weak and slowing", "疲弱且放缓"),
        "D": _pair("Weak but improving", "疲弱但改善"),
    },
    "labor_markets": {
        "A": _pair("Tight but cooling", "偏紧但降温"),
        "B": _pair("Hiring, still tight", "招聘强仍偏紧"),
        "C": _pair("Cooling and loose", "降温且宽松"),
        "D": _pair("Hiring into slack", "宽松中招聘"),
    },
    "financial_conditions": {
        "A": _pair("Easy but tightening", "宽松但转紧"),
        "B": _pair("Tight and tightening", "偏紧且续紧"),
        "C": _pair("Easy and easing", "宽松且续松"),
        "D": _pair("Tight but easing", "偏紧但转松"),
    },
}

PREDICATE_FORM: dict[str, dict[str, dict[str, str]]] = {
    "liquidity_regime": {
        "A": _pair("is ample and well supported", "既充裕又有支撑"),
        "B": _pair("is tight but still backed", "偏紧，但仍有支撑"),
        "C": _pair("is easy to get but thinly supported", "容易取得，但支撑偏薄"),
        "D": _pair("is tight and poorly supported", "既偏紧，支撑也不足"),
    },
    "inflation_system": {
        "A": _pair("is cooling but still sticky underneath", "正在降温，但底层仍顽固"),
        "B": _pair("is rising and broadening", "正在上升，并向各处扩散"),
        "C": _pair("is cooling across the board", "已全面降温"),
        "D": _pair("is picking up in a few places only", "有所回升，但只集中在少数项目"),
    },
    "growth_real_economy": {
        "A": _pair("is strong but slowing", "依然强劲，但正在放缓"),
        "B": _pair("is picking up across the board", "正在加快，面也广"),
        "C": _pair("is weak and still slowing", "疲弱，且仍在放缓"),
        "D": _pair("is weak but improving", "仍然疲弱，但正在改善"),
    },
    "labor_markets": {
        "A": _pair("are still tight but cooling", "仍然偏紧，但正在降温"),
        "B": _pair("are still hard to fill", "仍然一岗难求"),
        "C": _pair("are cooling and easier to fill", "正在降温，招人变得更容易"),
        "D": _pair("are picking up with room to grow", "招聘在回升，且仍有余量"),
    },
    "financial_conditions": {
        "A": _pair("is still cheap but getting less so", "仍然便宜，但正在变贵"),
        "B": _pair("is expensive and getting harder", "成本偏高，而且越来越难"),
        "C": _pair("is cheap and getting cheaper", "便宜，而且还在变便宜"),
        "D": _pair("is expensive but easing", "成本仍高，但正在放松"),
    },
}

# Tone judged INSIDE the chip's own subject only (pin §6.4) — a tight labour
# market is `ok` because hiring is strong FOR JOBS; whether that is
# inflationary is a different workspace's question. Null chip -> `neutral`,
# always (D1 / §3.4): freshness never contributes a tone anywhere.
STATE_TONE: dict[str, dict[str, str]] = {
    "liquidity_regime": {"A": "ok", "B": "warn", "C": "warn", "D": "bad"},
    "inflation_system": {"A": "warn", "B": "bad", "C": "ok", "D": "warn"},
    "growth_real_economy": {"A": "warn", "B": "ok", "C": "bad", "D": "warn"},
    "labor_markets": {"A": "warn", "B": "ok", "C": "bad", "D": "ok"},
    "financial_conditions": {"A": "warn", "B": "bad", "C": "ok", "D": "warn"},
}

# Plain-word siblings of FRESHNESS (`.mc-chip-fresh`, pin §6.6). FRESHNESS's
# own strings are producer-shaped internal names ("Stale source", "Source
# failed") banned from the glance tier by doctrine Law 2 / charter §7.x. This
# table sets no tone, ever — freshness never contributes a tone (D1). CURRENT
# has no row: the caller omits `.mc-chip-fresh` entirely when freshness is
# CURRENT.
FRESHNESS_NOTE: dict[str, dict[str, str]] = {
    "LATE_WITHIN_TOLERANCE": _pair("arriving late", "延迟送达"),
    "STALE_SOURCE": _pair("not updated today", "今日未更新"),
    "NOT_YET_RELEASED": _pair("not published yet", "尚未发布"),
    "SOURCE_FAILED": _pair("didn't arrive today", "今日未送达"),
    "RIGHTS_BLOCKED": _pair("not licensed here", "此处无授权"),
    "NOT_COVERED": _pair("not covered", "未覆盖"),
    "HISTORICAL_AS_KNOWN": _pair("as known at the time", "按当时已知"),
    "SIMULATED": _pair("simulated", "模拟数据"),
}

# The always-rendered chip note (`role="note"` + `aria-describedby`, pin §6.7).
# Budget: <= 24 EN words / <= 42 ZH characters.
CHIP_MEANING: dict[str, dict[str, str]] = {
    "money": _pair(
        "How easily money is moving through the system, and whether central-bank support is behind it.",
        "资金在体系中流动的难易程度，以及背后是否有央行支持。"),
    "policy": _pair(
        "Where official interest rates sit, and where the market expects them to go next.",
        "官方利率目前的水平，以及市场预期其下一步走向。"),
    "rates": _pair(
        "What it costs to borrow for a few months, against what it costs for a few years.",
        "借款数月与借款数年之间的成本差异。"),
    "inflation": _pair(
        "How fast prices are rising, and whether the rise is broad or confined to a few things.",
        "物价上涨的速度，以及涨势是广泛的还是仅限于少数项目。"),
    "growth": _pair(
        "Whether the economy is speeding up or slowing down, and how widely.",
        "经济是在加速还是放缓，以及影响面有多广。"),
    "jobs": _pair(
        "How hard it is for companies to hire, and how easily people find work.",
        "企业招人的难度，以及求职者找工作的难易程度。"),
    "credit": _pair(
        "How expensive, and how hard, it is for companies to borrow right now.",
        "企业当下借钱的成本高低与难易程度。"),
    "coverage": _pair(
        "How many sections have a reading dated today. This one is about our data, not the market.",
        "有多少板块已具备今日读数。此项说明的是我们的数据，而非市场。"),
}

# Null-chip notes, replacing CHIP_MEANING when the chip is null (pin §6.8).
# Selection order lives in `lib.macro_suite_view._chip_null_cause` — the
# first matching cause wins.
CHIP_NULL_NOTE: dict[str, dict[str, str]] = {
    "no_state": _pair(
        "This section publishes its own numbers rather than a one-word read. Open it to see them.",
        "本板块发布的是具体数据，而非一句话读数。点击查看。"),
    "late": _pair(
        "Today's reading hasn't arrived. We show nothing rather than yesterday's number dressed as today's.",
        "今日读数尚未送达。我们宁可不显示，也不会把昨天的数字当作今天的。"),
    "not_released": _pair(
        "The source hasn't published yet. It appears here the first time it does.",
        "数据源尚未发布。首次发布后即会出现在此处。"),
    "no_snapshot": _pair(
        "We show this once this section publishes a dated reading. It refreshes with the nightly update.",
        "该板块首次发布带日期的读数后即会显示，随每晚更新刷新。"),
    "rights": _pair(
        "We're not licensed to show this reading here.",
        "我们在此处没有显示该读数的授权。"),
    "plan": _pair(
        "This section is part of a higher plan.",
        "本板块属于更高级别方案。"),
}

# Chip 8 (`coverage`) value word (pin §6.5) — digit-free, per §3.0 bullet 1.
COVERAGE_WORD: dict[str, dict[str, str]] = {
    "complete": _pair("All sections current", "各板块均最新"),
    "partial": _pair("Some sections behind", "部分板块滞后"),
}

# The Read's inter-clause punctuation, assigned by POSITION, never stored in
# copy (pin §4.3): index < n-2 -> "mid", index == n-2 -> "penultimate", last
# -> "last". ZH never carries a coordinating word (native-shaped, not
# calqued) — every ZH value is "；" or "。".
READ_PUNCT: dict[str, dict[str, str]] = {
    "mid": _pair(", ", "；"),
    "penultimate": _pair(", and ", "；"),
    "last": _pair(".", "。"),
}


def date_display_pair(iso_date: str) -> dict[str, str] | None:
    """Bilingual display for an ISO ``YYYY-MM-DD`` (or longer timestamp,
    truncated to its date) — ``"4 Sep 2026"`` / ``"2026年9月4日"``. Never a
    raw ISO string in visible text (G2b); returns ``None`` for anything that
    does not parse rather than fabricating a date."""
    if not isinstance(iso_date, str) or len(iso_date) < 10:
        return None
    from datetime import date as _date  # noqa: PLC0415 — stdlib, avoids a
    # module-level import purely for one formatter used by one packet.
    try:
        d = _date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    month_en = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[d.month - 1]
    return _pair(f"{d.day} {month_en} {d.year}", f"{d.year}年{d.month}月{d.day}日")


_VOCABULARIES: dict[str, dict[str, dict[str, str]]] = {
    "freshness": FRESHNESS,
    "null_reason": NULL_REASON,
    "presence": PRESENCE,
    "evidence_class": EVIDENCE_CLASS,
    "evidence_claim": EVIDENCE_CLAIM,
    "confidence_band": CONFIDENCE_BAND,
    "confidence_dimension": CONFIDENCE_DIMENSION,
    "comparability": COMPARABILITY,
    "correction_state": CORRECTION_STATE,
    "rights_state": RIGHTS_STATE,
    "direction": DIRECTION,
    "unit": UNIT,
    "basis": BASIS,
    "owner_value": OWNER_VALUE,
    "metric": METRIC,
    "horizon": HORIZON,
    "region": REGION,
    "channel": CHANNEL,
    "alert_kind": ALERT_KIND,
}


def deslug(token: str) -> str:
    """Readable fallback for a token with no reviewed label.

    Never returns the raw slug shape: underscores become spaces and the result
    is sentence-cased, so an unmapped ``rate_pressure`` reads ``Rate pressure``
    and an unmapped enum ``SOME_FUTURE_STATE`` reads ``Some future state``
    rather than shouting a producer identifier at the reader.
    """
    text = str(token).replace("_", " ").replace("-", " ").strip().lower()
    return text[:1].upper() + text[1:] if text else ""


def label(vocabulary: str, token: Any) -> dict[str, str] | None:
    """Reviewed ``{"en", "zh"}`` for ``token`` in ``vocabulary``.

    ``None`` in, ``None`` out — a caller must render its own typed absence
    rather than a fabricated label. An unknown token yields a de-slugged pair
    and is recorded in :func:`unknown_tokens`.
    """
    if token is None:
        return None
    table = _VOCABULARIES.get(vocabulary)
    if table is None:
        raise KeyError(f"unknown label vocabulary: {vocabulary!r}")
    found = table.get(str(token))
    if found is not None:
        return dict(found)
    _UNKNOWN.add(f"{vocabulary}:{token}")
    readable = deslug(token)
    return _pair(readable, readable)


def tone(vocabulary: str, token: Any, default: str = "neutral") -> str:
    if token is None:
        return default
    if vocabulary == "freshness":
        return FRESHNESS_TONE.get(str(token), default)
    if vocabulary == "presence":
        return PRESENCE_TONE.get(str(token), default)
    return default


def unknown_tokens() -> tuple[str, ...]:
    """Tokens this process had no reviewed label for, as ``vocabulary:token``."""
    return tuple(sorted(_UNKNOWN))


def reset_unknown_tokens() -> None:
    _UNKNOWN.clear()


def record_unknown(token: str) -> None:
    """Register a token this process had no reviewed label for, outside the
    ``label()`` lookup path — used by a caller (Macro Command's chip/Read
    builder) that resolves its own workspace-scoped tables rather than a flat
    :data:`_VOCABULARIES` entry, but still owes the same
    :func:`unknown_tokens` accounting (frozen spec §3.3 step 3)."""
    _UNKNOWN.add(token)


def known(vocabulary: str) -> tuple[str, ...]:
    return tuple(sorted(_VOCABULARIES[vocabulary]))


# --- value formatting --------------------------------------------------------

def fmt_number(value: Any) -> str | None:
    """Format a numeric cell WITHOUT changing its basis or unit.

    Returns ``None`` for a missing value so the caller renders a typed absence.
    No scaling, no percent conversion, no rounding to a friendlier story: a
    percentile of ``0.046`` prints as ``0.046`` beside a ``percentile (0-1)``
    unit, never as a silently multiplied ``4.6%``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, (int, float)):
        return None
    magnitude = abs(float(value))
    if magnitude >= 1000:
        return f"{value:,.1f}"
    if magnitude >= 1:
        return f"{value:,.2f}"
    if magnitude == 0:
        return "0"
    return f"{value:.4g}"


def fmt_signed(value: Any) -> str | None:
    text = fmt_number(value)
    if text is None:
        return None
    try:
        return f"+{text}" if float(value) > 0 else text
    except (TypeError, ValueError):
        return text


def fmt_ratio_pct(value: Any) -> str | None:
    """A 0-1 coverage RATIO rendered as a percentage — the one conversion that
    is unambiguous, and only ever applied to a field the contract types as a
    ratio (``availability.coverage_ratio``)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return f"{float(value) * 100:.0f}%"


def value_pair(value: Any) -> dict[str, str] | None:
    """Bilingual rendering of a metric/driver value.

    Numbers are language-neutral and cross over unchanged; a categorical owner
    reading gets its reviewed pair.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return _pair("Yes", "是") if value else _pair("No", "否")
    if isinstance(value, str):
        return label("owner_value", value)
    text = fmt_number(value)
    return None if text is None else _pair(text, text)


def date_or_none(value: Any) -> str | None:
    """Pass a clock string through, or ``None``. Never substitutes 'today'."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def collect_unknown(*tokens: Iterable[Any]) -> tuple[str, ...]:  # pragma: no cover
    return unknown_tokens()


def is_bilingual(node: Any) -> bool:
    return isinstance(node, Mapping) and "en" in node
