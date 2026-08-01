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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page
from engine.fundamental_forensics.private_state import (
    LOCAL_STATE_RELATIVE,
    STATE_SCHEMA,
    decode_state_blob,
    publish_state_blob,
)

log = logging.getLogger("build_fundamental_forensics")

SCHEMA = STATE_SCHEMA
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
            "label_zh": "SEC 申报历史",
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
    if rev_g is not None and ar_g is not None and ar_g > rev_g + 0.10:
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
    if rev_g is not None and inv_g is not None and inv_g > rev_g + 0.15:
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
    capex_triggered = False
    capex_gap = None
    if capex_g is not None and rev_g is not None and capex_g > rev_g + 0.10:
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
    capex_evaluable = (
        capex_g is not None
        and rev_g is not None
        and op_cur is not None
        and (op_cur <= 0 or op_g is not None)
    )
    return {
        "margin_compression_despite_revenue_growth": rev_g is not None and gm_cur is not None and gm_prev is not None,
        "receivables_stretch": rev_g is not None and ar_g is not None,
        "inventory_build": rev_g is not None and inv_g is not None,
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


def compose_state(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    q_path = root / "data" / "edgar" / "statements_quarterly.parquet"
    a_path = root / "data" / "edgar" / "statements.parquet"
    if not q_path.exists():
        raise FileNotFoundError(q_path)
    quarterly = pd.read_parquet(q_path)
    annual = pd.read_parquet(a_path) if a_path.exists() else pd.DataFrame()
    names, sectors, ciks = _metadata(root)

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
            action = {"key": "high", "en": "Review before adding risk", "zh": "加仓前复核"}
        elif findings:
            action = {"key": "watch", "en": "Watch the next filing", "zh": "关注下一份财报"}
        elif evaluable_count < len(DETECTORS):
            action = {
                "key": "limited",
                "en": "Coverage limited — do not infer clean",
                "zh": "覆盖有限 — 不可推断为无异常",
            }
        else:
            action = {
                "key": "covered",
                "en": "No review prompt in covered checks",
                "zh": "已覆盖检查暂无复核提示",
            }

        recent = rows.tail(8).iloc[::-1]
        companies[ticker] = {
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
                "This broad-universe projection preserves filing dates but is not accession-coherent and does not expose revision lineage.",
                "Quarterly flow fields can be derived from year-to-date facts, and different metrics can come from independently selected standard concepts.",
                "Open the SEC source endpoints before relying on a finding; company-specific taxonomy and corporate actions can require review.",
                "Findings are deterministic review prompts, not misconduct claims, ratings, or trading signals.",
            ],
            "limitations_zh": [
                "广覆盖投影保留申报日期，但并非 accession 一致，也不展示修订谱系。",
                "季度流量字段可能由年初至今数据推导，不同指标也可能来自独立选择的标准概念。",
                "依赖任何发现前请打开 SEC 来源端点；公司自定义分类及公司行动可能需要人工复核。",
                "发现是确定性的复核提示，不是欺诈指控、评级或交易信号。",
            ],
            "companyfacts_url_pattern": "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
        },
        "summary": {
            "companies": len(companies),
            "findings": len(ranked),
            "high": high_n,
            "watch": len(ranked) - high_n,
            "latest_filing": as_of,
            "detector_coverage": coverage_by_detector,
        },
        "detectors": list(DETECTORS),
        "default_symbol": default_symbol,
        "ranked_findings": ranked,
        "companies": companies,
    }


def render(root: Path, state: dict[str, Any]) -> Path:
    """Atomically render the public shell/assets, then commit private state last."""
    page = render_shell(root)
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


def render_shell(root: Path) -> Path:
    """Render only the data-free public workbench shell and versioned assets."""
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    html = env.get_template("fundamental_forensics.html.j2").render(
        generated_utc="private-state-runtime",
        state_summary={},
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
