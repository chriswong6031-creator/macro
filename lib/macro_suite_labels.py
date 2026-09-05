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
