"""Build the China Mechanics cockpit page (W8 — china_mechanics.html).

Reads the spine artifacts from site/chinastatedata/ and the data lobes from
data/china_*/  to assemble a control-room cockpit — participation trends,
limit mechanics, cycle memory, policy tape, cross-market — then renders
templates/china_mechanics.html.j2.

Authority: context_only (CN-SYS-R1).  No fused scores (CN-SYS-R13).
LLMs never feed the page (CN-SYS-R14).

Usage: python -m scripts.build_china_mechanics
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_china_mechanics")

_ROOT = Path(__file__).resolve().parent.parent
_SITE = _ROOT / "site"
_CHINASTATE = _SITE / "chinastatedata"
_OUT_DIR = _SITE / "chinamechanicsdata"
_TMPL = "china_mechanics.html.j2"

ASSETS = ("theme.css", "theme.js", "chart_i18n.js", "charts.js", "tablesort.js")

# ── phase catalog ───────────────────────────────────────────────────────────────
# Single source of truth for the cycle-wheel, the phase legend, and the glossary
# "cycle phase meanings".  Ordered CLOCKWISE around the natural market cycle
# (recovery → bull → top → bear → back).  Colors are the canonical phase colors
# used across the china pages.  meaning_* are plain-English (average-user) readings.
# Descriptive only — this catalog never scores, ranks or originates state
# (CN-SYS-R1/R13/R14).
PHASE_CATALOG = [
    {"key": "REPAIR", "color": "#7aa7e0", "name_en": "Repair", "name_zh": "修复期",
     "meaning_en": "Quiet base-building — turnover stable-low, no breadth extremes either way.",
     "meaning_zh": "筑底修复 — 成交平稳偏低，涨跌停均不极端。"},
    {"key": "POLICY_PUT", "color": "#5b9bf0", "name_en": "Policy Put", "name_zh": "政策托底",
     "meaning_en": "Selling looks exhausted and a policy floor arrives — early-cycle, driven by policy not broad money.",
     "meaning_zh": "抛压趋于枯竭、政策底部显现 — 周期早段，由政策而非广义流动性驱动。"},
    {"key": "LIQUIDITY_IGNITION", "color": "#45b873", "name_en": "Liquidity Ignition", "name_zh": "流动性点火",
     "meaning_en": "Money floods in — turnover explodes and limit-ups spike as the first move ignites.",
     "meaning_zh": "资金涌入 — 成交激增、涨停井喷，首波行情点火。"},
    {"key": "BROADENING", "color": "#3da564", "name_en": "Broadening", "name_zh": "全面扩散",
     "meaning_en": "A healthy, broad advance — participation widens across sectors.",
     "meaning_zh": "健康的全面上行 — 板块参与度普遍扩散。"},
    {"key": "THEME_LEADERSHIP", "color": "#e08b45", "name_en": "Theme Leadership", "name_zh": "题材领涨",
     "meaning_en": "A narrow, selective rally — a handful of hot themes lead while breadth thins.",
     "meaning_zh": "窄幅、结构性行情 — 少数热门题材领涨，宽度收窄。"},
    {"key": "EUPHORIA", "color": "#e06464", "name_en": "Euphoria", "name_zh": "亢奋期",
     "meaning_en": "Late-bull frenzy — speculation peaks and lianban chains run hot.",
     "meaning_zh": "牛市末期亢奋 — 投机达到顶点，连板火爆。"},
    {"key": "DISTRIBUTION", "color": "#e07070", "name_en": "Distribution", "name_zh": "派发期",
     "meaning_en": "Smart money sells into strength — the tape stays up while quality quietly leaves.",
     "meaning_zh": "主力借强势派发 — 指数仍高，优质筹码悄然离场。"},
    {"key": "DELEVERAGING", "color": "#c04040", "name_en": "Deleveraging", "name_zh": "去杠杆",
     "meaning_en": "Margin unwinds — leverage comes off and the first air-pockets appear.",
     "meaning_zh": "融资盘平仓 — 杠杆退潮，开始出现急跌。"},
    {"key": "CAPITULATION", "color": "#8b93a1", "name_en": "Capitulation", "name_zh": "恐慌宣泄",
     "meaning_en": "Panic cascade — limit-downs surge and margin calls force selling.",
     "meaning_zh": "恐慌宣泄 — 跌停激增，强制平仓引发连锁抛售。"},
    {"key": "GRINDING_BEAR", "color": "#a07070", "name_en": "Grinding Bear", "name_zh": "阴跌熊市",
     "meaning_en": "Slow attrition — low turnover and relief rallies that keep failing.",
     "meaning_zh": "缓慢阴跌 — 成交低迷，反弹屡屡失败。"},
]
PHASE_ORDER = [p["key"] for p in PHASE_CATALOG]
PHASE_BY_KEY = {p["key"]: p for p in PHASE_CATALOG}


def _phase_meta(key: str | None) -> dict:
    """Catalog entry for a phase key (empty-ish dict if unknown)."""
    return PHASE_BY_KEY.get(key or "", {})


# ── helpers ────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("JSON unreadable (%s): %s", path, e)
    return None


def _clean_float(v: object) -> float | None:
    """Return None for nan/inf, else float."""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _series_to_chart(series: pd.Series, n: int = 120) -> list[dict]:
    """Last n rows of a float series -> [{d: date_str, v: float|null}]."""
    tail = series.dropna().tail(n)
    out = []
    for idx, val in tail.items():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({"d": d, "v": _clean_float(val)})
    return out


def _series_with_nulls(series: pd.Series, n: int = 120) -> list[dict]:
    """Last n rows including nulls."""
    tail = series.tail(n)
    out = []
    for idx, val in tail.items():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        out.append({"d": d, "v": _clean_float(val)})
    return out


# ── panel (a): participation ───────────────────────────────────────────────────

def _participation_panel() -> dict:
    """Build the participation panel payload."""
    try:
        tape = pd.read_parquet(_ROOT / "data" / "china_participation" / "tape.parquet")
        tape.index = pd.to_datetime(tape.index)
        tail = tape.tail(120)
        participation_json = _read_json(_CHINASTATE / "participation.json")
        return {
            "turnover_z20": _series_with_nulls(tail["turnover_z20"]),
            "margin_balance": _series_to_chart(tail["margin_balance"]),
            "margin_chg_5d": _series_with_nulls(tail["margin_chg_5d"]),
            "southbound_z": _series_with_nulls(tail["southbound_z"]),
            "qvix": _series_to_chart(tail["qvix"]),
            "latest": participation_json,
            "as_of": str(tape.index[-1].date()) if len(tape) > 0 else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("participation panel failed (%s); degrading", e)
        return {"latest": _read_json(_CHINASTATE / "participation.json")}


# ── panel (b): limit mechanics ─────────────────────────────────────────────────

def _limit_panel() -> dict:
    """Build the limit mechanics panel payload."""
    try:
        tape = pd.read_parquet(_ROOT / "data" / "china_microstructure" / "limit_tape.parquet")
        # tape uses a 'date' column (not the index); coerce
        if "date" in tape.columns:
            tape["date"] = pd.to_datetime(tape["date"])
            tape = tape.set_index("date").sort_index()
        tail = tape.tail(120)
        events_raw = pd.read_parquet(_ROOT / "data" / "china_microstructure" / "limit_events.parquet")
        events_raw["date"] = pd.to_datetime(events_raw["date"])
        events_raw = events_raw.sort_values("date")

        # latest session events table
        latest_date = events_raw["date"].max()
        latest_events = events_raw[events_raw["date"] == latest_date].to_dict("records")
        # limit up/down breadth series
        lup_series = _series_with_nulls(tail["limit_up_breadth_pct"])
        ldn_series = _series_with_nulls(tail["limit_down_breadth_pct"])
        # failed seal ratio = failed_up_seal_count / limit_up_count (avoid div0)
        fsr = (tail["failed_up_seal_count"] / tail["limit_up_count"].clip(lower=1)).where(
            tail["limit_up_count"] > 0
        )
        fsr_series = _series_with_nulls(fsr)
        lianban_series = _series_with_nulls(tail["lianban_2plus"])

        micro_json = _read_json(_CHINASTATE / "microstructure.json")
        latest_agg = dict((micro_json or {}).get("latest_aggregate") or {})
        # count fields arrive as floats (9.0, 1585.0); display them as integers
        for _k in ("limit_up_count", "limit_down_count", "sealed_up_close",
                   "failed_up_seal_count", "lianban_2plus", "lianban_max",
                   "universe_n", "st_excluded_counts"):
            _v = latest_agg.get(_k)
            if isinstance(_v, (int, float)) and not (isinstance(_v, float) and math.isnan(_v)):
                latest_agg[_k] = int(round(_v))

        # clean events for display (stringify dates)
        clean_events = []
        for ev in latest_events[:20]:
            clean_events.append({
                "ticker": ev.get("ticker", ""),
                "board": ev.get("board", ""),
                "event": ev.get("event", ""),
                "lianban_count": int(ev.get("lianban_count", 0) or 0),
                "close_off_limit_pct": _clean_float(ev.get("close_off_limit_pct")),
            })

        return {
            "lup_series": lup_series,
            "ldn_series": ldn_series,
            "fsr_series": fsr_series,
            "lianban_series": lianban_series,
            "latest_events": clean_events,
            "latest_date": str(latest_date.date()) if pd.notna(latest_date) else None,
            "latest_agg": latest_agg,
            "as_of": str(tape.index[-1].date()) if len(tape) > 0 else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("limit panel failed (%s); degrading", e)
        micro_json = _read_json(_CHINASTATE / "microstructure.json")
        return {"latest_agg": (micro_json or {}).get("latest_aggregate") or {}}


# ── panel (c): phase memory ────────────────────────────────────────────────────

def _phase_panel() -> dict:
    """Build the phase memory panel payload (90-session strip + falsifier ledger + ERA analogs)."""
    cp = _read_json(_CHINASTATE / "cycle_phase.json")
    phase_strip: list[dict] = []
    ledger_held = 0
    ledger_fired = 0
    days_in_phase: int | None = None
    phase_started: str | None = None
    prev_phase: str | None = None

    try:
        tape_path = _ROOT / "data" / "china_cycle_phase" / "phase_tape.parquet"
        if tape_path.exists():
            tape = pd.read_parquet(tape_path)
            tape.index = pd.to_datetime(tape.index)
            tape = tape.sort_index()
            tail = tape.tail(90)
            for idx, row in tail.iterrows():
                phase_strip.append({
                    "d": idx.strftime("%Y-%m-%d"),
                    "phase": str(row.get("phase", "")),
                    "confidence": _clean_float(row.get("confidence")),
                })
            # days_in_phase / phase_started / prev_phase from the FULL tape (not
            # just the 90-session window) so a long-held phase is measured honestly.
            if "phase" in tape.columns and len(tape) > 0:
                phases_full = [str(p) for p in tape["phase"].tolist()]
                dates_full = list(tape.index)
                cur = phases_full[-1]
                run = 0
                for i in range(len(phases_full) - 1, -1, -1):
                    if phases_full[i] == cur:
                        run += 1
                    else:
                        prev_phase = phases_full[i]
                        break
                days_in_phase = run
                start_idx = len(phases_full) - run
                if 0 <= start_idx < len(dates_full):
                    d0 = dates_full[start_idx]
                    phase_started = d0.strftime("%Y-%m-%d") if hasattr(d0, "strftime") else str(d0)

        ledger_path = _ROOT / "data" / "china_cycle_phase" / "falsifier_ledger.parquet"
        if ledger_path.exists():
            ledger = pd.read_parquet(ledger_path)
            ledger_held = int((ledger["outcome"] == "held").sum()) if "outcome" in ledger.columns else 0
            ledger_fired = int((ledger["outcome"] == "fired").sum()) if "outcome" in ledger.columns else 0
    except Exception as e:  # noqa: BLE001
        log.warning("phase tape/ledger read failed (%s); degrading", e)

    # if tape empty, use snapshot from cycle_phase.json
    if not phase_strip and cp:
        phase_strip = [{"d": cp.get("asof", ""), "phase": cp.get("phase", ""), "confidence": cp.get("confidence")}]

    era_table = (cp or {}).get("era_table", [])
    ledger_summary = (cp or {}).get("ledger_summary") or {"held": ledger_held, "fired": ledger_fired, "total_graded": ledger_held + ledger_fired}

    # current-phase enrichment: where we are on the wheel + what usually comes next
    cur_key = (cp or {}).get("phase")
    cur_meta = _phase_meta(cur_key)
    next_key = None
    if cur_key in PHASE_ORDER:
        next_key = PHASE_ORDER[(PHASE_ORDER.index(cur_key) + 1) % len(PHASE_ORDER)]
    next_meta = _phase_meta(next_key)

    return {
        "current": cp,
        "phase_strip": phase_strip,
        "era_table": era_table,
        "ledger_summary": ledger_summary,
        "catalog": PHASE_CATALOG,
        "days_in_phase": days_in_phase,
        "phase_started": phase_started,
        "prev_phase": prev_phase,
        "prev_phase_name": _phase_meta(prev_phase),
        "current_meta": cur_meta,
        "next_phase": next_key,
        "next_meta": next_meta,
    }


# ── panel (d): policy tape ─────────────────────────────────────────────────────

def _policy_panel() -> dict:
    """Build the policy tape panel payload."""
    pt = _read_json(_CHINASTATE / "policy_transmission.json") or {}
    return {
        "policy_impulse": pt.get("policy_impulse"),
        "transmission_channel": pt.get("transmission_channel", []),
        "recent_events": pt.get("recent_events", []),
        "staleness": pt.get("staleness", {}).get("per_source_days", {}),
        "asof": pt.get("asof"),
    }


# ── panel (e): cross-market ────────────────────────────────────────────────────

def _cross_market_panel() -> dict:
    """Build the cross-market panel from market_state.json external block."""
    ms = _read_json(_CHINASTATE / "market_state.json") or {}
    ext = ms.get("external") or {}
    return {
        "yield_curve": ext.get("yield_curve") or {},
        "cgb_curve": ext.get("cgb_curve") or {},
        "usdcnh": ext.get("usdcnh") or {},
        "dxy": ext.get("dxy"),
        "as_of": ms.get("as_of"),
        "data_gaps": ms.get("data_gaps", []),
    }


# ── deterministic plain-English state reading ───────────────────────────────────
# Composes a bilingual, average-user paragraph purely from the finite-vocab enums
# already on the page (phase, participation regime / who_controls / risk, policy
# impulse) plus a couple of numeric context reads.  DETERMINISTIC — no model, no
# LLM ever touches this page (CN-SYS-R14).  It DESCRIBES market structure; it never
# advises, scores, ranks or originates state (CN-SYS-R1).

_WHO_EN = {"institutional": "institutions", "offshore": "offshore money (HK southbound)",
           "retail": "retail traders", "margin": "leveraged (margin) money"}
_WHO_ZH = {"institutional": "机构", "offshore": "外资（港股通南向）",
           "retail": "散户", "margin": "融资盘"}
_IMPULSE_EN = {"easing": "broad easing", "targeted_support": "targeted support",
               "market_rescue": "market rescue", "neutral": "neutral", "tightening": "tightening"}
_IMPULSE_ZH = {"easing": "全面宽松", "targeted_support": "定向支持",
               "market_rescue": "救市", "neutral": "中性", "tightening": "收紧"}
_RISK_EN = {"frothy": "frothy", "fire_sale": "fire-sale", "normal": "near-normal"}
_RISK_ZH = {"frothy": "泡沫化", "fire_sale": "恐慌抛售", "normal": "接近正常"}


def _compose_state_reading(participation: dict, phase: dict, policy: dict) -> dict:
    """Return {'en': str, 'zh': str} — a plain-English state paragraph."""
    lpl = (participation or {}).get("latest") or {}
    cur_meta = (phase or {}).get("current_meta") or {}
    days = (phase or {}).get("days_in_phase")

    en: list[str] = []
    zh: list[str] = []

    # 1) phase sentence
    pname_en = cur_meta.get("name_en")
    pname_zh = cur_meta.get("name_zh")
    if pname_en:
        held_en = f" for the past {days} sessions" if days else ""
        held_zh = f"已持续 {days} 个交易日" if days else ""
        m_en = cur_meta.get("meaning_en", "")
        m_en = (m_en[:1].lower() + m_en[1:]) if m_en else m_en  # reads mid-sentence after em-dash
        en.append(f"The A-share market is in <b>{pname_en}</b>{held_en} — {m_en}")
        zh.append(f"A股市场目前处于<b>{pname_zh}</b>阶段（{held_zh}）— "
                  f"{cur_meta.get('meaning_zh','')}")
    else:
        en.append("A-share market structure snapshot.")
        zh.append("A股市场结构快照。")

    # 2) participation sentence
    who = lpl.get("who_controls")
    tz20 = _clean_float(lpl.get("turnover_z20"))
    tz60 = _clean_float(lpl.get("turnover_z60"))
    sbz = _clean_float(lpl.get("southbound_z"))
    turnover_ref = tz20 if tz20 is not None else tz60
    p_en = "Participation is led by " + (_WHO_EN.get(who, "no single group") if who else "no single group")
    p_zh = "参与方面，" + (_WHO_ZH.get(who, "无单一主导方") if who else "无单一主导方") + "主导"
    bits_en, bits_zh = [], []
    if sbz is not None and sbz >= 1.0:
        bits_en.append(f"offshore (southbound) flow is unusually active at z=+{sbz:.1f}")
        bits_zh.append(f"南向资金异常活跃（z=+{sbz:.1f}）")
    elif sbz is not None and sbz <= -1.0:
        bits_en.append(f"offshore (southbound) flow is draining at z={sbz:.1f}")
        bits_zh.append(f"南向资金流出（z={sbz:.1f}）")
    if turnover_ref is not None:
        if turnover_ref <= -0.5:
            bits_en.append("domestic turnover is below its recent average")
            bits_zh.append("境内成交低于近期均值")
        elif turnover_ref >= 0.5:
            bits_en.append("domestic turnover is running hot")
            bits_zh.append("境内成交明显放量")
    if bits_en:
        p_en += " — " + ", but ".join(bits_en) if len(bits_en) == 2 else " — " + bits_en[0]
        p_zh += " — " + "，但".join(bits_zh) if len(bits_zh) == 2 else " — " + bits_zh[0]
    en.append(p_en + ".")
    zh.append(p_zh + "。")

    # 3) fear / risk sentence
    qvix = _clean_float(lpl.get("qvix"))
    risk = lpl.get("risk")
    if qvix is not None:
        band_en = "elevated" if qvix >= 25 else ("subdued" if qvix < 16 else "near-normal")
        band_zh = "偏高" if qvix >= 25 else ("低迷" if qvix < 16 else "接近正常")
        risk_en = _RISK_EN.get(risk, risk)
        risk_zh = _RISK_ZH.get(risk, risk)
        # avoid the redundant "near-normal … near-normal" when band == risk read
        rext_en = f", and the broader risk read is {risk_en}" if risk and risk_en != band_en else ""
        rext_zh = f"，整体风险环境为{risk_zh}" if risk and risk_zh != band_zh else ""
        en.append(f"Fear (QVIX {qvix:.1f}) is {band_en}{rext_en}.")
        zh.append(f"恐慌指标（QVIX {qvix:.1f}）{band_zh}{rext_zh}。")

    # 4) policy sentence
    impulse = (policy or {}).get("policy_impulse")
    if impulse:
        en.append(f"Policy impulse is <b>{_IMPULSE_EN.get(impulse, impulse.replace('_',' '))}</b>.")
        zh.append(f"政策冲量为<b>{_IMPULSE_ZH.get(impulse, impulse)}</b>。")

    return {"en": " ".join(en), "zh": "".join(zh)}


# ── payload builder ────────────────────────────────────────────────────────────

def build_payload() -> dict:
    """Assemble all panel payloads into a single VM dict."""
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ms = _read_json(_CHINASTATE / "market_state.json") or {}
    participation = _participation_panel()
    limits = _limit_panel()
    phase = _phase_panel()
    policy = _policy_panel()
    cross_market = _cross_market_panel()
    state_reading = _compose_state_reading(participation, phase, policy)
    return {
        "built": built,
        "as_of": ms.get("as_of", ""),
        "authority": "context_only",
        "state_reading": state_reading,
        "phase_catalog": PHASE_CATALOG,
        "participation": participation,
        "limits": limits,
        "phase": phase,
        "policy": policy,
        "cross_market": cross_market,
        "data_gaps": ms.get("data_gaps", []),
    }


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)

        payload = build_payload()

        # write the JSON payload (committed artifact)
        payload_path = _OUT_DIR / "mechanics.json"
        payload_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("wrote %s", payload_path)

        # render the template
        env = Environment(
            loader=FileSystemLoader(str(_ROOT / "templates")), autoescape=False
        )
        from engine import i18n  # noqa: E402
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        tmpl = env.get_template(_TMPL)
        html = tmpl.render(**payload)
        write_page(_SITE / "china_mechanics.html", html)
        log.info(
            "wrote site/china_mechanics.html (%d KB)", len(html) // 1024
        )

        # copy assets
        for a in ASSETS:
            src = _ROOT / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, _SITE)

    except Exception as e:  # noqa: BLE001
        log.error("build_china_mechanics failed (%s); skipping", e)
        return 0  # non-fatal per CN-SYS-R11
    return 0


if __name__ == "__main__":
    sys.exit(main())
