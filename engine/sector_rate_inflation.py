"""Per-sector RATE & INFLATION sensitivity overlay — a display-only sector chip.

A LEAF on top of the rate/inflation TRANSMISSION foundation
(engine/rate_inflation_transmission.py + data/transmission/calibration.json). It
takes that module's MEASURED driver→asset forward-IC matrix, splits the live read-
drivers into a RATE channel (discount-rate speed + curve + policy pricing) and an
INFLATION channel (breakeven change + core-PCE gap + re-acceleration + the
expectations wedge), and for each sector SPDR reports the live headwind / tailwind
each channel is exerting RIGHT NOW — the same measured ``IC × current driver-
activation`` product the foundation's ``transmission_read`` uses, restricted to one
channel's drivers — plus how strongly that channel is measured to move the sector.

WHY: today the sector heat score is dampened only by the fixed cyclical/defensive
``config.confluence.sector_macro_beta`` table, which cannot tell a rate-sensitive
long-duration sector (XLK) from a sector whose forward returns the data says barely
respond to the rate channel at all. This overlay adds that missing per-sector,
per-channel rate/inflation read — as CONTEXT beside the heat, never inside it.

DISCIPLINE — display / LLM-context ONLY, NEVER scored. The sector HEAT score
(``engine.technicals._score_components``) is byte-identical with or without this
overlay; this module is imported only by the playbook's per-sector enrichment and
the sector page, never by any scoring path. The foundation's scored-leg gate found
NO rate/inflation leg robust enough to TIME returns (the strongest — real-rate speed
— is regime-dependent and fails purged-CV; see
reports/rate-inflation-transmission-calibration.md). This overlay inherits that
verdict: it enlarges the facts a sector read can cite, it does not move the heat.
Every coefficient is the split-half forward IC the calibrator measured, carried with
its verdict (CONFIRMED / DIRECTIONAL) so the reader sees how much to trust each link.
CONTEXT / UNMEASURED cells and cells weaker than ``min_ic`` are dropped, so a sector
whose rate link is only regime-dependent (e.g. the bond-proxy XLU/XLRE on a forward-
IC basis) honestly reads "no robust measured link" rather than asserting the textbook
sensitivity. Bilingual throughout. Additive, never fatal.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from engine.rate_inflation_transmission import (
    DRIVERS_META,
    _last,
    _z,
    build_drivers,
    load_calibration,
)

log = logging.getLogger(__name__)

# The two channels — exactly the foundation's READ_DRIVERS split in two (the raw
# LEVEL drivers stay excluded for co-trend, as in rate_inflation_transmission).
RATE_DRIVERS = ["real10y_chg63", "nom10y_chg63", "curve_tp_adj", "policy_gap"]
INFL_DRIVERS = ["be10y_chg63", "corepce_gap", "infl_accel", "exp_wedge"]

# The economically-clean SIGN anchor per channel (textbook-interpretable) used only
# to word the static "sensitivity character"; the live net still aggregates ALL of a
# channel's drivers. Rate sign = the discount-rate SPEED (rising real/nominal yields,
# then cut/hike pricing); inflation sign = the sticky-inflation gap, then re-
# acceleration, then breakeven change. The curve / expectations-wedge legs are kept
# OUT of the sign anchor because their direction is ambiguous (a steeper curve can be
# bull or bear; the wedge's measured effect inverts the textbook hedge).
RATE_SIGN_ORDER = ["real10y_chg63", "nom10y_chg63", "policy_gap"]
INFL_SIGN_ORDER = ["corepce_gap", "infl_accel", "be10y_chg63"]

# Sector SPDRs the overlay annotates. The calibration matrix covers 8 of these; the
# other three (XLC / XLI / XLY) have no measured cells and degrade to "not measured".
SECTOR_TICKERS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
                  "XLP", "XLRE", "XLU", "XLV", "XLY"]

_SKIP = ("CONTEXT", "UNMEASURED")  # verdicts not robust enough to aggregate / count

_VERDICT_ZH = {"CONFIRMED": "已确认", "DIRECTIONAL": "方向性",
               "CONTEXT": "依赖状态", "INVERTED": "反向", "UNMEASURED": "未测得"}
_CHAN_ZH = {"headwind": "逆风", "tailwind": "顺风", "neutral": "中性"}
_STRENGTH_ZH = {"strong": "强", "moderate": "中等", "weak": "弱"}


def _bil(en: str, zh: str) -> dict:
    return {"en": en, "zh": zh}


def _driver_label(drv: str) -> dict:
    en, zh, _kind = DRIVERS_META.get(drv, (drv, drv, ""))
    return _bil(en, zh)


def _channel(mat: dict, act: dict, tkr: str, drivers: list[str],
             sign_order: list[str], *, min_ic: float, z_cap: float,
             cut: float, ic_strong: float) -> dict:
    """Aggregate one channel's MEASURED cells × current activation into a live
    headwind/tailwind for ``tkr``. Mirrors rate_inflation_transmission.transmission_
    read's per-cell math, restricted to ``drivers``. Returns the live net, verdict,
    measured strength, character sign, and the top contributing drivers."""
    net = 0.0
    max_ic = 0.0
    parts: list[dict] = []
    for drv in drivers:
        cell = mat.get(drv, {}).get("assets", {}).get(tkr)
        if not cell:
            continue
        ic = cell.get("ic")
        verdict = cell.get("verdict")
        az = act.get(drv)
        if ic is None or az is None or abs(ic) < min_ic or verdict in _SKIP:
            continue
        azc = max(-z_cap, min(z_cap, az))
        contrib = ic * (azc / z_cap)               # in [-|ic|, |ic|]
        net += contrib
        max_ic = max(max_ic, abs(ic))
        parts.append({"driver": drv, "label": _driver_label(drv),
                      "ic": round(ic, 3), "verdict": verdict,
                      "verdict_zh": _VERDICT_ZH.get(verdict, verdict),
                      "activation_z": round(az, 2),
                      "contribution": round(contrib, 3)})
    parts.sort(key=lambda p: -abs(p["contribution"]))

    # static character sign: first robustly-measured cell in textbook priority order
    sign = 0
    for drv in sign_order:
        cell = mat.get(drv, {}).get("assets", {}).get(tkr)
        if (cell and cell.get("ic") is not None and abs(cell["ic"]) >= min_ic
                and cell.get("verdict") not in _SKIP):
            sign = 1 if cell["ic"] > 0 else -1
            break

    measured = bool(parts)
    verdict = "headwind" if net < -cut else "tailwind" if net > cut else "neutral"
    strength = ("strong" if max_ic >= ic_strong
                else "moderate" if max_ic >= min_ic else "weak")
    return {"net": round(net, 3), "verdict": verdict, "strength": strength,
            "max_ic": round(max_ic, 3) if max_ic else None, "sign": sign,
            "measured": measured, "drivers": parts[:2]}


# kind-specific wording for the static character (when the channel is measured but
# currently quiet, the chip still conveys the sector's sensitivity rather than going
# blank). sign: +1 = the sector's forward return rises with the channel, -1 = falls.
_CHAR = {
    "rate": {1: _bil("rate-helped", "受益于利率"), -1: _bil("rate-sensitive", "利率敏感")},
    "inflation": {1: _bil("inflation-helped", "受益于通胀"),
                  -1: _bil("inflation-pressured", "受通胀压制")},
}
_NAME = {"rate": _bil("Rate", "利率"), "inflation": _bil("Inflation", "通胀")}
_ARROW = {"headwind": "▼", "tailwind": "▲", "neutral": "·"}
_TONE = {"headwind": "neg", "tailwind": "pos", "neutral": "muted"}


def _decorate(ch: dict, kind: str, covered: bool) -> dict:
    """Attach ready bilingual chip text + tooltip so the templates stay trivial."""
    name = _NAME[kind]
    if not ch["measured"]:
        ch["show"] = False
        ch["tone"] = "muted"
        ch["arrow"] = "·"
        if not covered:
            ch["chip"] = _bil(f"{name['en']}: not measured", f"{name['zh']}：未测得")
            ch["tip"] = _bil(
                f"No measured {kind} transmission cell for this sector — it is not in "
                f"the calibrated matrix. Display-only.",
                f"该板块没有可测得的{name['zh']}传导系数（不在已校准矩阵中）。仅供展示。")
        else:
            ch["chip"] = _bil(f"{name['en']}: regime-dependent",
                              f"{name['zh']}：依赖状态")
            ch["tip"] = _bil(
                f"This sector's {kind} link is only regime-dependent (CONTEXT) over the "
                f"split-half forward-IC test — no robust measured headwind/tailwind. "
                f"Display-only, never scored.",
                f"在分半前瞻IC检验中，该板块的{name['zh']}关联仅依赖市场状态（CONTEXT）—— "
                f"无稳健可测的逆风/顺风。仅供展示，从不计分。")
        return ch

    ch["show"] = True
    ch["tone"] = _TONE[ch["verdict"]]
    ch["arrow"] = _ARROW[ch["verdict"]]
    char = _CHAR[kind].get(ch["sign"]) or _bil(f"{kind}-linked", f"{name['zh']}相关")
    if ch["verdict"] == "neutral":
        # measured link exists but currently quiet → lead with the character word
        ch["chip"] = _bil(char["en"][:1].upper() + char["en"][1:], char["zh"])
    else:
        word = "headwind" if ch["verdict"] == "headwind" else "tailwind"
        word_zh = _CHAN_ZH[ch["verdict"]]
        ch["chip"] = _bil(f"{name['en']} {word}", f"{name['zh']}{word_zh}")

    top = ch["drivers"][0] if ch["drivers"] else None
    if top:
        ch["tip"] = _bil(
            f"{name['en']} channel: measured {ch['verdict']} right now "
            f"(net {ch['net']:+.2f}; {ch['strength']} measured sensitivity, "
            f"{char['en']}). Dominant driver: {top['label']['en']}, forward IC "
            f"{top['ic']:+.2f} ({top['verdict']}), currently {top['activation_z']:+.1f}σ. "
            f"Display-only — never scored.",
            f"{name['zh']}通道：当前实测为{_CHAN_ZH[ch['verdict']]}"
            f"（净值 {ch['net']:+.2f}；{char['zh']}，可测敏感度{_STRENGTH_ZH.get(ch['strength'], ch['strength'])}）。"
            f"主导驱动：{top['label']['zh']}，前瞻IC {top['ic']:+.2f}"
            f"（{top['verdict_zh']}），当前 {top['activation_z']:+.1f}σ。仅供展示，从不计分。")
    else:
        ch["tip"] = _bil(f"{name['en']} channel: {ch['verdict']}. Display-only.",
                         f"{name['zh']}通道：{_CHAN_ZH[ch['verdict']]}。仅供展示。")
    return ch


def _summary(rate: dict, infl: dict, covered: bool) -> dict:
    """One-line bilingual read combining both channels, for the detail page."""
    def phrase(ch: dict, label_en: str, label_zh: str) -> tuple[str, str]:
        if not ch["measured"]:
            return (f"no robust {label_en} link", f"无稳健{label_zh}关联")
        if ch["verdict"] == "neutral":
            return (f"a measured but quiet {label_en} link",
                    f"可测但平静的{label_zh}关联")
        return (f"a measured {label_en} {ch['verdict']}",
                f"实测{label_zh}{_CHAN_ZH[ch['verdict']]}")
    re, rz = phrase(rate, "rate", "利率")
    ie, iz = phrase(infl, "inflation", "通胀")
    return _bil(
        f"This sector currently shows {re} and {ie}. These are measured forward-IC "
        f"coefficients shown as context — display-only, never folded into the heat "
        f"score (the scored-leg gate found no robust rate/inflation timing leg).",
        f"该板块当前呈现{rz}与{iz}。这些是作为背景展示的实测前瞻IC系数 —— "
        f"仅供展示，绝不计入热度分数（可计分腿检验未发现稳健的利率/通胀择时腿）。")


def sector_channels(f: pd.DataFrame, cal: dict | None = None,
                    cfg: dict | None = None) -> dict:
    """{sector_ticker -> {covered, rate, inflation, summary}} display-only read.

    ``rate`` / ``inflation`` each carry: net (live contribution), verdict
    (headwind/tailwind/neutral), strength (strong/moderate/weak measured link),
    measured (bool), the top contributing drivers, and ready bilingual chip/tip
    text. Returns ``{}`` if the transmission layer is disabled or the calibration is
    missing — additive, never fatal."""
    cfg = cfg if cfg is not None else (config.load().get("transmission") or {})
    if not cfg.get("enabled", True):
        return {}
    cal = cal if cal is not None else load_calibration()
    if not cal or "transmission_matrix" not in cal:
        return {}
    mat = cal["transmission_matrix"]
    z_cap = cfg.get("z_cap", 2.5)
    min_ic = cfg.get("min_ic", 0.04)
    cut = cfg.get("effect_cut", 0.06)
    ic_strong = float((cal.get("meta") or {}).get("ic_strong", 0.10))

    drivers = build_drivers(f)
    act = {k: _last(_z(drivers[k])) for k in drivers.columns if drivers[k].notna().any()}

    out: dict = {}
    all_drv = RATE_DRIVERS + INFL_DRIVERS
    for tkr in SECTOR_TICKERS:
        covered = any(tkr in mat.get(d, {}).get("assets", {}) for d in all_drv)
        rate = _channel(mat, act, tkr, RATE_DRIVERS, RATE_SIGN_ORDER,
                        min_ic=min_ic, z_cap=z_cap, cut=cut, ic_strong=ic_strong)
        infl = _channel(mat, act, tkr, INFL_DRIVERS, INFL_SIGN_ORDER,
                        min_ic=min_ic, z_cap=z_cap, cut=cut, ic_strong=ic_strong)
        out[tkr] = {"ticker": tkr, "covered": covered,
                    "rate": _decorate(rate, "rate", covered),
                    "inflation": _decorate(infl, "inflation", covered),
                    "summary": _summary(rate, infl, covered),
                    "any_shown": rate["measured"] or infl["measured"]}
    return out
