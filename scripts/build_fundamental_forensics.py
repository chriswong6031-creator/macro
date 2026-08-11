"""Build the display-only Filing Forensics workbench state and page.

This is deliberately a projection builder, not the canonical SEC lineage engine.
It reads the repository's already-normalized quarterly/annual EDGAR panels and
turns five transparent accounting checks into a compact browser artifact.  The
canonical accession-aware, acceptance-time replay engine lives in
``engine.fundamental_forensics`` and can replace this projection without changing
the UI contract once its scheduled raw store is available.

No finding produced here is a fraud claim, a company score, or trading authority.
The page is additive and fail-soft: a missing input leaves the last rendered page
untouched when called from the main site build.

The assembled state is written atomically to a gitignored local path.  Production
publishes that validated gzip to the existing private Research Vault object store;
the public repository and Pages mirror receive only the data-free shell/assets.

Usage::

    python -m scripts.build_fundamental_forensics
    python -m scripts.build_fundamental_forensics --publish-private
    python -m scripts.build_fundamental_forensics --publish-only
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from engine.fundamental_forensics.private_state import (
    LOCAL_STATE_RELATIVE,
    STATE_SCHEMA,
    decode_state_blob,
    publish_state_blob,
)  # noqa: E402
from engine.fundamental_forensics.disclosure_projection import (
    DisclosureProjectionError,
    read_disclosure_projection_directory,
)  # noqa: E402

log = logging.getLogger("build_fundamental_forensics")

SCHEMA = STATE_SCHEMA

# The counts-only public projection: aggregate totals the anonymous gate may
# print, carried in a committed file because the private state is gitignored.
PUBLIC_SUMMARY_RELATIVE = Path("data/fundamental_forensics/public_summary.json")
PUBLIC_SUMMARY_SCHEMA = "fundamental_forensics.public_summary/v1"
# How long a committed projection may keep being published. daily.yml's run_py
# prints an ::error annotation for a failed builder but does NOT exit non-zero,
# so a broken forensics build leaves the nightly green while build_site keeps
# re-rendering this page from the last good file — the counts would freeze and
# stay published forever. The stamp bounds that: a projection nobody has
# refreshed in a month stops being printed instead of quietly going stale.
PUBLIC_SUMMARY_MAX_AGE_DAYS = 30
QUARTERLY_METRICS = (
    "revenue",
    "gross_profit",
    "receivables",
    "inventory",
    "cfo",
    "capex",
    "op_income",
    "ni",
    "contract_liabilities",
)

DETECTORS = (
    {
        "id": "margin_compression_despite_revenue_growth",
        "topic": "margin",
        "title_en": "Margin compression",
        "title_zh": "利润率承压",
        "description_en": "Revenue grew while gross margin moved lower year over year.",
        "description_zh": "收入同比增长，但毛利率下降。",
        "threshold_en": "Revenue growth ≥ 3%; current gross margin < prior-year quarter",
        "threshold_zh": "收入增长 ≥ 3%；本季毛利率低于去年同期",
    },
    {
        "id": "receivables_stretch",
        "topic": "working_capital",
        "title_en": "Receivables outran revenue",
        "title_zh": "应收账款跑赢收入",
        "description_en": "Receivables grew materially faster than reported revenue.",
        "description_zh": "应收账款增长明显快于报告收入。",
        "threshold_en": "Receivables growth > revenue growth + 10 percentage points",
        "threshold_zh": "应收账款增速 > 收入增速 + 10 个百分点",
    },
    {
        "id": "inventory_build",
        "topic": "working_capital",
        "title_en": "Inventory outran revenue",
        "title_zh": "库存跑赢收入",
        "description_en": "Inventory accumulated materially faster than reported revenue.",
        "description_zh": "库存累积明显快于报告收入。",
        "threshold_en": "Inventory growth > revenue growth + 15 percentage points",
        "threshold_zh": "库存增速 > 收入增速 + 15 个百分点",
    },
    {
        "id": "capital_intensity_rising",
        "topic": "capital_intensity",
        "title_en": "Capital intensity rose",
        "title_zh": "资本强度上升",
        "description_en": "Capital spending grew faster than revenue and operating income.",
        "description_zh": "资本开支增速快于收入及经营利润。",
        "threshold_en": "Capex growth > revenue and operating-income growth by 10 percentage points",
        "threshold_zh": "资本开支增速比收入及经营利润增速高 10 个百分点",
    },
    {
        "id": "accruals_trending_up",
        "topic": "cash_conversion",
        "title_en": "Accrual burden rose",
        "title_zh": "应计负担上升",
        "description_en": "Three-year accrual intensity moved materially higher.",
        "description_zh": "三年应计强度明显上升。",
        "threshold_en": "Latest minus oldest (net income − CFO) / assets ≥ 3 percentage points",
        "threshold_zh": "最新与最早的（净利润 − 经营现金流）/ 资产差值 ≥ 3 个百分点",
    },
)

# The state transport remains intentionally compact even when the raw archive
# cache grows.  The disclosure projection module bounds each company record;
# this second guard prevents a one-off bulk import from crowding out the
# existing broad-universe workbench state.  Omitted records remain available in
# the private projection directory and are reported explicitly in coverage.
# Real two-track Inline XBRL comparisons can legitimately reach ~550 KiB even
# after the redline/receipt caps are applied (AAPL's annual + quarterly pair is
# a measured example). Keep a firm per-company ceiling, but do not silently
# discard the very evidence-heavy issuers this feature exists to investigate.
MAX_DISCLOSURE_PROJECTION_BYTES = 768 * 1024
MAX_DISCLOSURE_STATE_BYTES = 12 * 1024 * 1024


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _ratio(num: Any, den: Any) -> float | None:
    n, d = _finite(num), _finite(den)
    if n is None or d is None or d <= 0:
        return None
    return n / d


def _growth(current: Any, prior: Any) -> float | None:
    c, p = _finite(current), _finite(prior)
    if c is None or p is None or p <= 0:
        return None
    return c / p - 1.0


def _json_number(value: Any) -> float | None:
    val = _finite(value)
    return round(val, 8) if val is not None else None


def _period_label(row: pd.Series) -> str:
    fy = int(row["fiscal_year"])
    fq = int(row["fiscal_quarter"])
    return f"FY{fy} Q{fq}"


def _source_links(cik: int | None, filed: str | None) -> list[dict[str, Any]]:
    if cik is None:
        return []
    cik10 = f"{int(cik):010d}"
    return [
        {
            "label_en": "SEC filing history",
            "label_zh": "SEC 披露历史",
            "date": filed,
            "url": f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}&owner=exclude&action=getcompany",
            "basis": "filing_index",
        },
        {
            "label_en": "SEC Company Facts JSON",
            "label_zh": "SEC 公司事实 JSON",
            "date": filed,
            "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
            "basis": "companyfacts_source",
        },
    ]


def _value(
    key: str,
    label_en: str,
    label_zh: str,
    current: Any,
    prior: Any,
    delta: Any,
    fmt: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label_en": label_en,
        "label_zh": label_zh,
        "current": _json_number(current),
        "prior": _json_number(prior),
        "delta": _json_number(delta),
        "format": fmt,
    }


def _finding(
    detector: str,
    priority: str,
    current: pd.Series,
    prior: pd.Series,
    *,
    title_en: str,
    title_zh: str,
    summary_en: str,
    summary_zh: str,
    formula_en: str,
    formula_zh: str,
    threshold_en: str,
    threshold_zh: str,
    values: list[dict[str, Any]],
    cik: int | None,
    limitations_en: Iterable[str] = (),
    limitations_zh: Iterable[str] = (),
) -> dict[str, Any]:
    current_label = _period_label(current)
    prior_label = _period_label(prior)
    return {
        "id": f"{detector}:{current_label.replace(' ', '-').lower()}",
        "detector": detector,
        "priority": priority,
        "topic": next(d["topic"] for d in DETECTORS if d["id"] == detector),
        "title_en": title_en,
        "title_zh": title_zh,
        "summary_en": summary_en,
        "summary_zh": summary_zh,
        "period_current": current_label,
        "period_prior": prior_label,
        "formula_en": formula_en,
        "formula_zh": formula_zh,
        "threshold_en": threshold_en,
        "threshold_zh": threshold_zh,
        "values": values,
        "evidence": _source_links(cik, str(current.get("filed") or "")),
        "limitations_en": list(limitations_en),
        "limitations_zh": list(limitations_zh),
        "display_only": True,
        "authority": "review_priority_only",
    }


def detect_quarterly(current: pd.Series, prior: pd.Series, cik: int | None) -> list[dict[str, Any]]:
    """Return transparent triggered checks for matched fiscal quarters."""
    out: list[dict[str, Any]] = []
    rev_g = _growth(current.get("revenue"), prior.get("revenue"))
    gm_cur = _ratio(current.get("gross_profit"), current.get("revenue"))
    gm_prev = _ratio(prior.get("gross_profit"), prior.get("revenue"))
    # A computable revenue GROWTH is not the same as a usable revenue BASE.
    # _growth only requires the PRIOR denominator to be positive, so a filer
    # whose revenue collapses to 0 (or is reported negative) still yields
    # rev_g = -1.0 or lower. The working-capital spreads below then degenerate:
    # `ar_g > rev_g + 0.10` becomes `ar_g > -0.90`, which almost any receivables
    # series clears — a near-certain FALSE FIRE driven entirely by the revenue
    # collapse rather than by any receivables behaviour. Both sibling
    # implementations already refuse here (engine/moat_falsifiers.py returns
    # None; engine/fundamental_forensics/detectors.py returns NOT_EVALUABLE with
    # "positive_revenue_and_nonzero_prior_balance_required"), so this gate makes
    # the workbench agree with them instead of publishing the artefact.
    # The margin check needs no such gate: _ratio already requires d > 0.
    rev_cur = _finite(current.get("revenue"))
    rev_cur_positive = rev_cur is not None and rev_cur > 0

    if rev_g is not None and rev_g >= 0.03 and gm_cur is not None and gm_prev is not None and gm_cur < gm_prev:
        compression = gm_prev - gm_cur
        priority = "high" if compression >= 0.03 else "watch"
        out.append(_finding(
            "margin_compression_despite_revenue_growth", priority, current, prior,
            title_en="Revenue grew. Gross margin did not.",
            title_zh="收入增长，毛利率却下降。",
            summary_en=f"Revenue rose {rev_g:.1%} year over year while gross margin fell {compression:.1%}.",
            summary_zh=f"收入同比增长 {rev_g:.1%}，毛利率下降 {compression:.1%}。",
            formula_en="Gross margin = gross profit / revenue; compare the same fiscal quarter year over year.",
            formula_zh="毛利率 = 毛利润 / 收入；对比去年同期季度。",
            threshold_en="Revenue growth ≥ 3% and current gross margin < prior-year quarter.",
            threshold_zh="收入增长 ≥ 3%，且本季毛利率低于去年同期。",
            values=[
                _value("revenue_growth", "Revenue growth", "收入增长", rev_g, None, None, "percent"),
                _value("gross_margin", "Gross margin", "毛利率", gm_cur, gm_prev, gm_cur - gm_prev, "percent"),
            ], cik=cik,
            limitations_en=("A lower margin can reflect mix, acquisitions, pass-through costs, or deliberate investment.",),
            limitations_zh=("毛利率下降也可能源于产品组合、并购、成本转嫁或主动投资。",),
        ))

    ar_g = _growth(current.get("receivables"), prior.get("receivables"))
    if rev_g is not None and rev_cur_positive and ar_g is not None and ar_g > rev_g + 0.10:
        gap = ar_g - rev_g
        out.append(_finding(
            "receivables_stretch", "high" if gap >= 0.25 else "watch", current, prior,
            title_en="Receivables are outrunning sales.",
            title_zh="应收账款跑赢销售。",
            summary_en=f"Receivables grew {gap:.1%} faster than revenue year over year.",
            summary_zh=f"应收账款增速比收入快 {gap:.1%}。",
            formula_en="Receivables growth minus revenue growth.",
            formula_zh="应收账款增速减去收入增速。",
            threshold_en="Spread > 10 percentage points.",
            threshold_zh="差值 > 10 个百分点。",
            values=[
                _value("receivables_growth", "Receivables growth", "应收账款增长", ar_g, None, None, "percent"),
                _value("revenue_growth", "Revenue growth", "收入增长", rev_g, None, None, "percent"),
                _value("growth_gap", "Growth gap", "增速差", gap, None, None, "percent"),
            ], cik=cik,
            limitations_en=("Seasonality, billing cadence, acquisitions, and customer mix can create a benign gap.",),
            limitations_zh=("季节性、开票节奏、并购及客户结构可能造成良性差异。",),
        ))

    inv_g = _growth(current.get("inventory"), prior.get("inventory"))
    if rev_g is not None and rev_cur_positive and inv_g is not None and inv_g > rev_g + 0.15:
        gap = inv_g - rev_g
        out.append(_finding(
            "inventory_build", "high" if gap >= 0.30 else "watch", current, prior,
            title_en="Inventory is building faster than sales.",
            title_zh="库存增长快于销售。",
            summary_en=f"Inventory grew {gap:.1%} faster than revenue year over year.",
            summary_zh=f"库存增速比收入快 {gap:.1%}。",
            formula_en="Inventory growth minus revenue growth.",
            formula_zh="库存增速减去收入增速。",
            threshold_en="Spread > 15 percentage points.",
            threshold_zh="差值 > 15 个百分点。",
            values=[
                _value("inventory_growth", "Inventory growth", "库存增长", inv_g, None, None, "percent"),
                _value("revenue_growth", "Revenue growth", "收入增长", rev_g, None, None, "percent"),
                _value("growth_gap", "Growth gap", "增速差", gap, None, None, "percent"),
            ], cik=cik,
            limitations_en=("A planned product ramp, supply protection, acquisitions, or commodity inflation can explain the build.",),
            limitations_zh=("产品爬坡、供应保障、并购或大宗商品通胀可能解释库存增加。",),
        ))

    capex_g = _growth(current.get("capex"), prior.get("capex"))
    op_g = _growth(current.get("op_income"), prior.get("op_income"))
    op_cur = _finite(current.get("op_income"))
    # Current capex must be POSITIVE — the detector is about rising capital
    # SPENDING, and a non-positive current capex is net disposal proceeds (or a
    # quarter with none reported), which is the opposite direction. _growth only
    # constrains the PRIOR, so without this gate a zero/negative current capex
    # yields a well-formed capex_g <= -1.0 that can never clear rev_g + 0.10 —
    # so the pair reports "clear" forever AND is counted as covered, a permanent
    # verdict drawn from evidence that cannot support one. Both siblings already
    # refuse here (engine/moat_falsifiers.py skips on current capex <= 0; the
    # registry kernel returns not_evaluable with
    # "nonzero_revenue_and_positive_capex_required").
    capex_cur = _finite(current.get("capex"))
    capex_cur_positive = capex_cur is not None and capex_cur > 0
    capex_triggered = False
    capex_gap = None
    if capex_g is not None and rev_g is not None and capex_cur_positive and capex_g > rev_g + 0.10:
        if op_cur is not None and op_cur <= 0:
            capex_triggered, capex_gap = True, capex_g - rev_g
        elif op_g is not None and capex_g > op_g + 0.10:
            capex_triggered, capex_gap = True, min(capex_g - rev_g, capex_g - op_g)
    if capex_triggered and capex_gap is not None:
        out.append(_finding(
            "capital_intensity_rising", "high" if capex_gap >= 0.25 else "watch", current, prior,
            title_en="Capital spending accelerated ahead of output.",
            title_zh="资本开支增速领先产出。",
            summary_en=f"Capex growth exceeded operating growth by at least {capex_gap:.1%}.",
            summary_zh=f"资本开支增速至少比经营增长快 {capex_gap:.1%}。",
            formula_en="Capex growth compared with revenue and operating-income growth.",
            formula_zh="比较资本开支、收入及经营利润增速。",
            threshold_en="Capex growth exceeds both comparators by > 10 percentage points; revenue-only when operating income is non-positive.",
            threshold_zh="资本开支增速比两项指标均高 > 10 个百分点；经营利润非正时仅比较收入。",
            values=[
                _value("capex_growth", "Capex growth", "资本开支增长", capex_g, None, None, "percent"),
                _value("revenue_growth", "Revenue growth", "收入增长", rev_g, None, None, "percent"),
                _value("operating_income_growth", "Operating income growth", "经营利润增长", op_g, None, None, "percent"),
            ], cik=cik,
            limitations_en=("Growth investment can be economically attractive; this check identifies a review question, not a negative verdict.",),
            limitations_zh=("增长性投资可能具有经济价值；本检查仅提出复核问题，不构成负面结论。",),
        ))
    return out


def _accrual_inputs(annual: pd.DataFrame) -> tuple[list[int], list[float]] | None:
    """Return the exact three-year detector inputs, or None when not evaluable."""
    if annual.empty:
        return None
    rows = annual.sort_values(["fy", "period_end"], na_position="first").tail(3)
    if len(rows) != 3:
        return None
    fys = [int(v) for v in rows["fy"]]
    if fys[1] - fys[0] != 1 or fys[2] - fys[1] != 1:
        return None
    vals: list[float] = []
    for _, row in rows.iterrows():
        ni, cfo, assets = (_finite(row.get(k)) for k in ("ni", "cfo", "assets"))
        if ni is None or cfo is None or assets is None or assets <= 0:
            return None
        vals.append((ni - cfo) / assets)
    return fys, vals


def detector_evaluability(
    current: pd.Series,
    prior: pd.Series,
    annual: pd.DataFrame,
) -> dict[str, bool]:
    """Apply the same denominator/period gates as each detector.

    A finite value is not automatically an evaluable input: growth requires a
    positive prior denominator, capital intensity changes branch when operating
    income is non-positive, and accruals require three consecutive fiscal years.
    Keeping this map beside the detector math prevents false "covered" labels.
    """
    rev_g = _growth(current.get("revenue"), prior.get("revenue"))
    gm_cur = _ratio(current.get("gross_profit"), current.get("revenue"))
    gm_prev = _ratio(prior.get("gross_profit"), prior.get("revenue"))
    ar_g = _growth(current.get("receivables"), prior.get("receivables"))
    inv_g = _growth(current.get("inventory"), prior.get("inventory"))
    capex_g = _growth(current.get("capex"), prior.get("capex"))
    op_cur = _finite(current.get("op_income"))
    op_g = _growth(current.get("op_income"), prior.get("op_income"))
    # Mirrors the gate added to detect_quarterly: a non-positive CURRENT revenue
    # makes the working-capital spread an artefact of the revenue collapse, so
    # the pair is not evaluable rather than "covered but clear".
    rev_cur = _finite(current.get("revenue"))
    rev_cur_positive = rev_cur is not None and rev_cur > 0
    # Mirrors detect_quarterly: a non-positive CURRENT capex is disposal
    # proceeds, not capital spending, so the pair is not evaluable rather than
    # "covered and clear".
    capex_cur = _finite(current.get("capex"))
    capex_cur_positive = capex_cur is not None and capex_cur > 0
    capex_evaluable = (
        capex_g is not None
        and rev_g is not None
        and capex_cur_positive
        and op_cur is not None
        and (op_cur <= 0 or op_g is not None)
    )
    return {
        "margin_compression_despite_revenue_growth": rev_g is not None and gm_cur is not None and gm_prev is not None,
        "receivables_stretch": rev_g is not None and ar_g is not None and rev_cur_positive,
        "inventory_build": rev_g is not None and inv_g is not None and rev_cur_positive,
        "capital_intensity_rising": capex_evaluable,
        "accruals_trending_up": _accrual_inputs(annual) is not None,
    }


def detect_accruals(annual: pd.DataFrame, current_q: pd.Series, prior_q: pd.Series, cik: int | None) -> dict[str, Any] | None:
    """Three-period annual accrual trend using the repository's locked 3pp rule."""
    inputs = _accrual_inputs(annual)
    if inputs is None:
        return None
    fys, vals = inputs
    delta = vals[-1] - vals[0]
    if delta < 0.03 or vals[-1] <= vals[0]:
        return None
    return _finding(
        "accruals_trending_up", "high" if delta >= 0.05 else "watch", current_q, prior_q,
        title_en="Earnings moved further ahead of cash.",
        title_zh="利润进一步领先现金流。",
        summary_en=f"Accrual intensity rose {delta:.1%} across FY{fys[0]}–FY{fys[-1]}.",
        summary_zh=f"FY{fys[0]}–FY{fys[-1]} 应计强度上升 {delta:.1%}。",
        formula_en="Accrual intensity = (net income − operating cash flow) / assets.",
        formula_zh="应计强度 =（净利润 − 经营现金流）/ 资产。",
        threshold_en="Latest minus oldest ≥ 3 percentage points across three consecutive fiscal years.",
        threshold_zh="连续三个财年中，最新值减最早值 ≥ 3 个百分点。",
        values=[
            _value("accrual_oldest", f"FY{fys[0]} accrual intensity", f"FY{fys[0]} 应计强度", vals[0], None, None, "percent"),
            _value("accrual_middle", f"FY{fys[1]} accrual intensity", f"FY{fys[1]} 应计强度", vals[1], None, None, "percent"),
            _value("accrual_latest", f"FY{fys[2]} accrual intensity", f"FY{fys[2]} 应计强度", vals[2], vals[0], delta, "percent"),
        ], cik=cik,
        limitations_en=("Working-capital timing and business-model differences can move accrual ratios without implying misstatement.",),
        limitations_zh=("营运资金时点及商业模式差异可能影响应计比率，并不意味着错报。",),
    )


def _metadata(root: Path) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    names: dict[str, str] = {}
    sectors: dict[str, str] = {}
    membership = root / "data" / "universe" / "membership.parquet"
    if membership.exists():
        m = pd.read_parquet(membership)
        if "active" in m.columns:
            m = m[m["active"].fillna(False)]
        for row in m.drop_duplicates("ticker", keep="last").to_dict("records"):
            ticker = str(row.get("ticker") or "").upper()
            if ticker:
                names[ticker] = str(row.get("name") or ticker)
                sectors[ticker] = str(row.get("sector") or "Unclassified")
    sector_path = root / "data" / "breadth" / "ticker_sectors.parquet"
    if sector_path.exists():
        for row in pd.read_parquet(sector_path).to_dict("records"):
            ticker = str(row.get("ticker") or "").upper()
            if ticker and row.get("sector"):
                sectors[ticker] = str(row["sector"])
    ciks: dict[str, int] = {}
    fundamentals = root / "data" / "edgar" / "fundamentals.parquet"
    if fundamentals.exists():
        f = pd.read_parquet(fundamentals, columns=["cik"])
        for ticker, row in f.iterrows():
            cik = _finite(row.get("cik"))
            if cik is not None:
                ciks[str(ticker).upper()] = int(cik)
    return names, sectors, ciks


def _clean_period(row: pd.Series) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "fiscal_year": int(row["fiscal_year"]),
        "fiscal_quarter": int(row["fiscal_quarter"]),
        "period_end": str(row.get("period_end") or ""),
        "filed": str(row.get("filed") or ""),
    }
    for metric in QUARTERLY_METRICS:
        doc[metric] = _json_number(row.get(metric))
    return doc


def _source_generated_at(quarterly: pd.DataFrame, annual: pd.DataFrame, as_of: str | None) -> str:
    """Return a stable source-snapshot clock instead of a wall-clock build time."""
    candidates: list[pd.Timestamp] = []
    for frame in (quarterly, annual):
        if frame.empty or "as_of" not in frame.columns:
            continue
        parsed = pd.to_datetime(frame["as_of"], errors="coerce", utc=True).dropna()
        if not parsed.empty:
            candidates.append(parsed.max())
    if candidates:
        return max(candidates).floor("s").isoformat()
    if as_of:
        return f"{as_of}T23:59:59+00:00"
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _state_disclosure_projection(projection: dict[str, Any]) -> dict[str, Any]:
    """Return the browser-safe private slice of one verified projection.

    The on-disk projection is already bounded and source-receipt rich.  Keep
    the explicit source/clock fields in state, but drop the duplicate issuer
    identity because it is carried by the company object that owns this slice.
    """
    return {
        "schema": projection["schema"],
        "projection_id": projection["projection_id"],
        "clocks": dict(projection["clocks"]),
        "source": dict(projection["source"]),
        "coverage": dict(projection["coverage"]),
        "tracks": list(projection["tracks"]),
        "limitations": list(projection["limitations"]),
        "display_only": True,
        "authority": "review_priority_only",
    }


def _load_disclosure_projections(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load optional, prebuilt accession-level comparisons without blocking v1.

    Heavy SEC retrieval/comparison is deliberately elsewhere.  A bad optional
    private projection is ignored fail-soft here; it cannot turn a successful
    base workbench build into an invented disclosure result.
    """
    try:
        return read_disclosure_projection_directory(root), []
    except DisclosureProjectionError as exc:
        log.warning("ignored invalid disclosure projection directory: %s", exc)
        return {}, [type(exc).__name__]


def _disclosure_budgeted(
    projections: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Select canonical projection records that fit the compact state budget."""
    selected: dict[str, dict[str, Any]] = {}
    total = 0
    too_large = 0
    deferred = 0
    for ticker, projection in sorted(projections.items()):
        encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_DISCLOSURE_PROJECTION_BYTES:
            too_large += 1
            continue
        if total + len(encoded) > MAX_DISCLOSURE_STATE_BYTES:
            deferred += 1
            continue
        selected[ticker] = projection
        total += len(encoded)
    return selected, {
        "loaded": len(projections),
        "selected": len(selected),
        "too_large": too_large,
        "deferred_for_state_budget": deferred,
        "embedded_bytes": total,
    }


def compose_state(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    q_path = root / "data" / "edgar" / "statements_quarterly.parquet"
    a_path = root / "data" / "edgar" / "statements.parquet"
    if not q_path.exists():
        raise FileNotFoundError(q_path)
    quarterly = pd.read_parquet(q_path)
    annual = pd.read_parquet(a_path) if a_path.exists() else pd.DataFrame()
    names, sectors, ciks = _metadata(root)
    disclosure_projections, disclosure_load_issues = _load_disclosure_projections(root)
    disclosure_projections, disclosure_budget = _disclosure_budgeted(disclosure_projections)

    for col in ("fiscal_year", "fiscal_quarter"):
        quarterly[col] = pd.to_numeric(quarterly[col], errors="coerce")
    quarterly = quarterly.dropna(subset=["ticker", "fiscal_year", "fiscal_quarter", "period_end"])
    quarterly["ticker"] = quarterly["ticker"].astype(str).str.upper()
    quarterly["filed"] = quarterly["filed"].fillna("").astype(str)
    quarterly = quarterly.sort_values(["ticker", "fiscal_year", "fiscal_quarter", "filed", "period_end"])
    quarterly = quarterly.drop_duplicates(["ticker", "fiscal_year", "fiscal_quarter"], keep="last")
    if not annual.empty:
        annual["ticker"] = annual["ticker"].astype(str).str.upper()

    companies: dict[str, dict[str, Any]] = {}
    ranked: list[dict[str, Any]] = []
    coverage_by_detector = {d["id"]: {"evaluated": 0, "triggered": 0} for d in DETECTORS}
    all_latest_filed: list[str] = []
    disclosure_attached = 0
    disclosure_tracks_ready = 0
    disclosure_tracks_not_evaluable = 0

    for ticker, rows in quarterly.groupby("ticker", sort=True):
        rows = rows.sort_values(["period_end", "filed"])
        current = rows.iloc[-1]
        same_q = rows[
            (rows["fiscal_quarter"] == current["fiscal_quarter"])
            & (rows["fiscal_year"] == current["fiscal_year"] - 1)
        ]
        if same_q.empty:
            continue
        prior = same_q.iloc[-1]
        cik = ciks.get(ticker)
        findings = detect_quarterly(current, prior, cik)
        annual_rows = annual[annual["ticker"] == ticker] if not annual.empty else pd.DataFrame()
        accrual = detect_accruals(annual_rows, current, prior, cik)
        if accrual:
            findings.append(accrual)

        # Coverage is an evidence-availability measure, never a company score.
        available = sum(
            _finite(current.get(metric)) is not None and _finite(prior.get(metric)) is not None
            for metric in QUARTERLY_METRICS
        )
        metrics_pct = available / len(QUARTERLY_METRICS)
        latest_filed = str(current.get("filed") or "")
        if latest_filed:
            all_latest_filed.append(latest_filed)

        evaluability = detector_evaluability(current, prior, annual_rows)
        evaluable_count = sum(evaluability.values())
        for detector in DETECTORS:
            det_id = detector["id"]
            if evaluability[det_id]:
                coverage_by_detector[det_id]["evaluated"] += 1
            if any(f["detector"] == det_id for f in findings):
                coverage_by_detector[det_id]["triggered"] += 1

        findings.sort(key=lambda f: (0 if f["priority"] == "high" else 1, f["detector"]))
        if any(f["priority"] == "high" for f in findings):
            action = {"key": "high", "en": "Changes need attention", "zh": "有变化需要关注"}
        elif findings:
            action = {"key": "watch", "en": "Changes to keep an eye on", "zh": "有变化值得持续观察"}
        elif evaluable_count < len(DETECTORS):
            action = {
                "key": "limited",
                "en": "Some checks could not run",
                "zh": "部分检查无法运行",
            }
        else:
            action = {
                "key": "covered",
                "en": "No unusual change in covered checks",
                "zh": "已覆盖检查暂无异常变化",
            }

        recent = rows.tail(8).iloc[::-1]
        company = {
            "symbol": ticker,
            "name": names.get(ticker, ticker),
            "sector": sectors.get(ticker, "Unclassified"),
            "cik": cik,
            "latest_period": _period_label(current),
            "latest_filed": latest_filed,
            "action": action,
            "coverage": {
                "periods": int(len(recent)),
                "metrics_pct": round(metrics_pct, 4),
                "detectors_evaluable": evaluable_count,
                "detectors_total": len(DETECTORS),
                "basis": "normalized_quarterly_projection",
            },
            "findings": findings,
            "periods": [_clean_period(row) for _, row in recent.iterrows()],
        }
        disclosure = disclosure_projections.get(ticker)
        if disclosure is not None:
            company["disclosures"] = _state_disclosure_projection(disclosure)
            disclosure_attached += 1
            disclosure_tracks_ready += int(disclosure["coverage"].get("tracks_ready") or 0)
            disclosure_tracks_not_evaluable += int(disclosure["coverage"].get("tracks_not_evaluable") or 0)
        companies[ticker] = company
        for finding in findings:
            ranked.append({
                "symbol": ticker,
                "finding_id": finding["id"],
                "priority": finding["priority"],
                "topic": finding["topic"],
                "latest_filed": latest_filed,
            })

    ranked.sort(key=lambda row: (
        0 if row["priority"] == "high" else 1,
        -(int(row["latest_filed"].replace("-", "")[:8]) if row["latest_filed"][:10].replace("-", "").isdigit() else 0),
        row["symbol"], row["finding_id"],
    ))
    high_n = sum(1 for row in ranked if row["priority"] == "high")
    as_of = max(all_latest_filed) if all_latest_filed else None
    generated = generated_at or _source_generated_at(quarterly, annual, as_of)
    # A stable, evidence-rich launch symbol makes the workbench reproducible while
    # the ranked feed remains fully live.  Fall back deterministically when SMCI
    # leaves the universe or has no current review item.
    default_symbol = (
        "SMCI"
        if companies.get("SMCI", {}).get("findings")
        else (ranked[0]["symbol"] if ranked else next(iter(companies), "AAPL"))
    )

    return {
        "schema": SCHEMA,
        "generated_at": generated,
        "as_of": as_of,
        "source": {
            "label": "SEC Company Facts normalized broad-universe projection",
            "basis": "repository quarterly and annual EDGAR panels",
            "limitations_en": [
                "This broad-universe statements projection preserves filing dates but is not accession-coherent; optional disclosure records below have their own accession and source-receipt lineage.",
                "Quarterly flow fields can be derived from year-to-date facts, and different metrics can come from independently selected standard concepts.",
                "Open the SEC source endpoints before relying on a finding; company-specific taxonomy and corporate actions can require review.",
                "Findings are deterministic review prompts, not misconduct claims, ratings, or trading signals.",
            ],
            "limitations_zh": [
                "广覆盖报表投影保留披露日期，但并非 accession 一致；下方可选披露记录拥有各自的 accession 与来源回执谱系。",
                "季度流量字段可能由年初至今数据推导，不同指标也可能来自独立选择的标准概念。",
                "依赖任何发现前请打开 SEC 来源端点；公司自定义分类及公司行动可能需要人工复核。",
                "发现是确定性的复核提示，不是欺诈指控、评级或交易信号。",
            ],
            "companyfacts_url_pattern": "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
            "accession_disclosure_projection": {
                "available": bool(disclosure_projections),
                "basis": "prebuilt checksum-bound primary-document comparisons; never fetched during render",
                "knowledge_clock": "source_event_acceptance_time",
            },
        },
        "summary": {
            "companies": len(companies),
            "findings": len(ranked),
            "high": high_n,
            "watch": len(ranked) - high_n,
            "latest_filing": as_of,
            "detector_coverage": coverage_by_detector,
            "disclosure_coverage": {
                **disclosure_budget,
                "attached_to_companies": disclosure_attached,
                "unmatched_company_projections": max(0, disclosure_budget["selected"] - disclosure_attached),
                "tracks_ready": disclosure_tracks_ready,
                "tracks_not_evaluable": disclosure_tracks_not_evaluable,
                "load_issues": disclosure_load_issues,
            },
        },
        "detectors": list(DETECTORS),
        "default_symbol": default_symbol,
        "ranked_findings": ranked,
        "companies": companies,
    }


def render(root: Path, state: dict[str, Any]) -> Path:
    """Atomically render the public shell/assets, then commit private state last."""
    summary = state.get("summary") or {}
    _write_public_summary(root, summary, generated_at=state.get("generated_at"))
    page = render_shell(root, state_summary=summary)
    _write_state_atomic(root / LOCAL_STATE_RELATIVE, state)
    return page


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(destination)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def _write_state_atomic(path: Path, state: dict[str, Any]) -> Path:
    """Write one deterministic, validated gzip without exposing partial bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(path)
    encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with temp.open("wb") as raw_fh:
            # Suppress the temp filename in the gzip header; mtime=0 alone is
            # insufficient because the PID-bearing atomic temp path would make
            # byte-identical state hash differently on every build process.
            with gzip.GzipFile(filename="", fileobj=raw_fh, mode="wb", compresslevel=9, mtime=0) as zipped:
                zipped.write(encoded.encode("utf-8"))
            raw_fh.flush()
            os.fsync(raw_fh.fileno())
        decode_state_blob(temp.read_bytes())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def public_summary_projection(summary: dict[str, Any]) -> dict[str, int]:
    """Project the private summary down to the two counts the gate may publish.

    Aggregate COUNTS are free by the same house rule the tier preview states:
    a count names nobody, while the member rows are the product. This builds the
    projection field by field on purpose — never by spreading `summary` — so a
    later key added to compose_state() (a symbol, a top-finding, a per-company
    breakdown) cannot reach a public byte by default.
    """
    return {
        "companies": int(summary.get("companies") or 0),
        "findings": int(summary.get("findings") or 0),
    }


def _write_public_summary(root: Path, summary: dict[str, Any], *, generated_at: str | None = None) -> Path:
    """Persist the counts-only projection so BOTH render paths read one number.

    The private state is gitignored, and build_site.py re-renders this shell
    through render_from_state() moments after the nightly forensics build (see
    daily.yml — forensics, then build_site) and again on every render.yml lane
    that never composes state at all. A count passed only in-process would be
    overwritten by that second render within seconds and would never exist on a
    render-lane rebuild. This file is committed by the nightly's broad
    `git add data/`, so the shell prints the same counts on every path.
    """
    path = root / PUBLIC_SUMMARY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = generated_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "schema": PUBLIC_SUMMARY_SCHEMA,
        "generated_at": stamped,
        **public_summary_projection(summary),
    }
    temp = _temp_sibling(path)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def read_public_summary(root: Path, *, now: datetime | None = None) -> dict[str, int]:
    """Read the committed counts, or {} when absent/unreadable/malformed/stale.

    Absence is a normal state, not an error: a fresh clone, a CI checkout and
    the very first build all lack the file, and the page must simply omit the
    fact rather than print a zero or a stale literal. A projection older than
    PUBLIC_SUMMARY_MAX_AGE_DAYS is treated the same way as an absent one — see
    that constant for why an unrefreshed file can otherwise outlive its build.
    """
    try:
        raw = json.loads((root / PUBLIC_SUMMARY_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("schema") != PUBLIC_SUMMARY_SCHEMA:
        return {}
    try:
        stamped = datetime.fromisoformat(str(raw["generated_at"]))
    except (KeyError, TypeError, ValueError):
        return {}
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    age = (now or datetime.now(timezone.utc)) - stamped
    if age.days > PUBLIC_SUMMARY_MAX_AGE_DAYS:
        return {}
    try:
        return public_summary_projection(raw)
    except (TypeError, ValueError):
        return {}


def render_shell(root: Path, state_summary: dict[str, Any] | None = None) -> Path:
    """Render only the public workbench shell, versioned assets, and free counts.

    `state_summary` carries no rows — only the aggregate counts projected by
    public_summary_projection(). When the caller supplies none (build_site's
    compatibility hook), the committed projection is read from disk so every
    render path agrees.
    """
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    counts = public_summary_projection(state_summary) if state_summary else read_public_summary(root)
    html = env.get_template("fundamental_forensics.html.j2").render(
        generated_utc="private-state-runtime",
        state_summary=counts,
        active_section="research",
        active_page="fundamental_forensics",
    )
    page = site / "fundamental_forensics.html"
    page_temp = _temp_sibling(page)
    try:
        write_page(page_temp, html)
        os.replace(page_temp, page)
    finally:
        page_temp.unlink(missing_ok=True)
    for name in ("fundamental_forensics.css", "fundamental_forensics.js"):
        _atomic_copy(root / "templates" / name, site / name)
    return page


def render_from_state(root: Path) -> Path:
    """Compatibility hook for build_site: render only the public shell/assets."""
    return render_shell(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=config.ROOT)
    parser.add_argument("--generated-at", default=None, help="Injected clock for deterministic builds/tests")
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument(
        "--publish-private",
        action="store_true",
        help="Build locally, then publish and byte-verify the private R2 object",
    )
    publish_group.add_argument(
        "--publish-only",
        action="store_true",
        help="Publish the already-built local private state without recomputing",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        state_path = root / LOCAL_STATE_RELATIVE
        if args.publish_only:
            if not publish_state_blob(state_path):
                raise RuntimeError("private state publish or read-back verification failed")
            log.info("published and verified %s", state_path)
            return 0
        state = compose_state(root, generated_at=args.generated_at)
        page = render(root, state)
        log.info("wrote %s (%d companies, %d findings)", page, state["summary"]["companies"], state["summary"]["findings"])
        if args.publish_private and not publish_state_blob(state_path):
            raise RuntimeError("private state publish or read-back verification failed")
        return 0
    except Exception as exc:  # noqa: BLE001 - additive page must not break the main build
        log.exception("fundamental forensics build skipped: %s", exc)
        print(f"::warning title=fundamental_forensics::build skipped ({type(exc).__name__}: {exc})", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
