"""Election-cycle context layer — a HONEST, evidence-gated calendar MODULATOR for the Risk
Radar. NOT an alert originator.

WHY THIS IS A MODULATOR, NEVER A LEG
------------------------------------
The owner proposed fusing the four-year presidential cycle with Brent Johnson's Dollar
Milkshake thesis: tighten in the midterm year, drain global dollar liquidity, crush
EM/HK/China/high-beta, then launch into the pre-election year. We BACKTESTED it on our own
data (SPY 1993+, the 11 SPDR sectors, DXY 1971+, SHCOMP/HSI/FXI/TSX, USD/CNH) before
wiring anything in. The verdict was sobering and is the reason this file is a *modulator*:

  • US midterm drawdowns ARE deeper on average — Apr-Oct max DD -14.6% vs -10.2% (n=8,
    Cohen d=-0.53) — but it is SUGGESTIVE-NOT-SIGNIFICANT (one-sided Mann-Whitney p~0.088;
    honest independent-episode count 5/8 vs 12/25, Fisher p=0.38). The worst year on record
    (2008, -47%) is NON-midterm: the tail does not live in midterms.
  • The Dollar-Milkshake DIRECTION is REFUTED in history: DXY Jun->Dec is -3.42% in midterm
    years vs -0.36% otherwise. The firm-dollar bucket is the ELECTION year (Y4, +2.09%). The
    dollar is, on average, WEAKER in a midterm H2 — the opposite of the thesis. (This cycle's
    firm dollar is the Iran-shock / Warsh-hawkish *idiosyncrasy* of 2026, which the radar's
    DXY/rate/CNH legs already measure directly — not a midterm-calendar effect.)
  • "EM/HK/China bears cluster in US midterms" FAILS a permutation test in all four markets
    (worst-year clustering p=0.24-0.79, none beats 25% chance). SHCOMP and FXI are actually
    MILDER in midterms; HSI's edge is one 1998 outlier; the only real hit is TSX (Canada).
    => the international radar must NOT encode a midterm EM-drawdown prior; it already has the
    validated dollar/rate/US-CN-diff/CNH/breadth legs that capture the real mechanism.
  • Sector seasonality ("XLV strongest / real estate worst") is directionally real for XLV
    (midterm Jul-Dec +7.2%, 83% win, n=6 — NOT the claimed 100%/+8%/5yr) but is MOSTLY
    ordinary defensive-H2 seasonality (XLV is +4.2% in non-midterm H2 too). Real estate's
    "0% over 5 midterms" is impossible: XLRE was born 2015-10 (only 2018 & 2022 exist, n=2).

So the ONLY genuinely non-collinear, directionally-consistent edge is narrow: in a midterm
Apr-Oct window WHILE THE TAPE IS STILL RISK-ON (SPY above its 200dMA), >=5% pullbacks have
arrived at ~1.25x the base rate (32.5% vs 26.0%) — i.e. the calendar flags risk *before
price reveals it*. That, and only that, is the sensitivity nudge below. Everything else is
display + a small sizing prior.

WHAT THIS FILE DOES (all at the modulator/display tier — the evidence gate is untouched):
  context()    — where we are in the 4-yr cycle + the Hirsch midterm-drawdown window, with the
                 MEASURED odds (not assumed) printed so the chip can never imply false certainty.
  modulation() — the Risk-Radar nudge: lowers ONLY the early (watch/caution) bands, and ONLY in
                 the risk-ON midterm window (the 1.25x cut); plus a small gross (sizing) trim
                 across the window. It can NEVER manufacture a loud (elevated+) banner — that
                 still requires the broad tape to break (the radar's #1 validated FP lever).
  sector_bias()— display-only defensive-rotation tilt for a midterm H2, labelled as mostly
                 generic seasonality.

All functions are pure (date in -> dict out) and never raise. Sources: this repo's backtest
(workflow midterm-milkshake-backtest); Hirsch / Stock Trader's Almanac for the window timing.
"""
from __future__ import annotations

import datetime as _dt

# ---- the four-year cadence -------------------------------------------------
# Y%4: 1 = Year1 (post-election), 2 = Year2 (MIDTERM), 3 = Year3 (pre-election), 0 = Year4
# (election). Anchors: 2025=Y1 (Trump inaug Jan 2025), 2026=midterm, 2022=midterm, 2024=Y4.
TERM_LABEL = {
    1: ("Post-election year", "选举次年"),
    2: ("Midterm year", "中期选举年"),
    3: ("Pre-election year", "大选前一年"),
    4: ("Election year", "大选年"),
}

# Hirsch midterm drawdown window (Stock Trader's Almanac): declines historically begin
# ~late Apr and bottom by ~mid-Aug..mid-Oct, then spring-board into the pre-election year.
_WIN_START = (4, 1)     # Apr 1
_WIN_END = (10, 31)     # Oct 31
_TROUGH_START = (8, 1)  # Aug
_TROUGH_END = (10, 31)  # Oct  — the historical bottoming zone

# ---- the ONE measured edge that survived the backtest ----------------------
# Midterm Apr-Oct window AND SPY risk-ON -> >=5% pullback at 32.5% vs 26.0% base = ~1.25x.
# Translate that into a SMALL early-tier band nudge. Lowering the watch/caution thresholds a
# few points makes the QUIET tiers fire earlier; the loud (elevated/risk-off) bands are left
# untouched, so the calendar can never originate a loud banner.
_BAND_NUDGE = 4.0       # points to subtract from the watch + caution thresholds, risk-ON slice only
# Small sizing prior across the whole midterm Apr-Oct window (DD ~1.4x deeper on average). The
# engine's own philosophy: de-risk = SIZING, not selection. Floored by the radar's gross floor.
_GROSS_MULT = 0.97

# ---- honest stat strings (baked from the backtest so the chip can't overclaim) -------------
# Voice: Lens content law (memory hover-popup-doctrine, 2026-07-19) — these strings land in
# hover explainers, so they must read as plain words. The machine receipt (n=8, p≈0.088,
# d=-0.53, the DXY numbers) stays in THIS FILE's docstring and in the tip's receipt line —
# never in body copy.
_STAT_EN = ("Midterm-year drops between April and October have run deeper than usual — though "
            "the pattern is loose, and the worst crashes on record came in other years.")
_STAT_ZH = ("中期选举年 4–10 月的回撤历来比平常更深——但规律并不严格，史上最深的下跌都发生在其他年份。")
_SLICE_EN = ("The one measured edge: while the market still looks healthy (S&P above its "
             "200-day average), pullbacks have come about 1.25× as often in this window — an "
             "early heads-up for position size, never a trigger.")
_SLICE_ZH = ("唯一可量化的优势：当大盘仍健康（标普高于 200 日均线）时，该窗口出现回撤的频率约为平常的 "
             "1.25 倍——仅作提前提醒、用于仓位，绝非买卖触发。")
_CAVEAT_EN = ("Calendar context only — it gently adjusts position size and alert sensitivity, "
              "and can never raise an alarm by itself. And ignore the folk story that the "
              "dollar firms up in midterm second halves: history shows the opposite, so trust "
              "the measured dollar and rate gauges, not the year.")
_CAVEAT_ZH = ("仅为日历背景——只轻微调整仓位与预警灵敏度，绝不单独拉响警报。至于「中期下半年美元走强」"
              "的坊间说法：历史恰好相反，请相信实测的美元与利率指标，而非年份本身。")

# ---- sector rotation (display-only) ----------------------------------------
# Midterm Jul-Dec, full-history (n=6) sectors: defensives held / improved, cyclicals faded.
# Mostly ordinary defensive-H2 seasonality, so this is a cosmetic tilt, never a signal.
_FAVOR = (("XLV", "Health Care", "医疗保健"), ("XLP", "Staples", "必需消费"), ("XLU", "Utilities", "公用事业"))
_AVOID = (("XLE", "Energy", "能源"), ("XLY", "Discretionary", "可选消费"))
_SECTOR_EN = ("In past midterm second halves, defensives (health care, staples, utilities) "
              "held up while energy and discretionary lagged — mostly ordinary second-half "
              "seasonality, not a midterm effect.")
_SECTOR_ZH = ("历次中期选举年下半年，防御板块（医疗、必需消费、公用事业）相对抗跌，能源与可选消费走弱——"
              "多为普通的下半年季节性，并非中期专属效应。")


# ---- helpers ---------------------------------------------------------------
def _as_date(asof) -> _dt.date:
    if asof is None:
        return _dt.date.today()
    if isinstance(asof, _dt.date) and not isinstance(asof, _dt.datetime):
        return asof
    if isinstance(asof, _dt.datetime):
        return asof.date()
    # str / pandas.Timestamp / numpy datetime — parse leniently without importing pandas
    s = str(asof)[:10]
    return _dt.date.fromisoformat(s)


def year_in_term(year: int) -> int:
    """1=post-election, 2=midterm, 3=pre-election, 4=election."""
    return 4 if (year % 4 == 0) else (year % 4)


def _in_span(d: _dt.date, start: tuple, end: tuple) -> bool:
    return (d.month, d.day) >= start and (d.month, d.day) <= end


# ---- public API ------------------------------------------------------------
def context(asof=None) -> dict:
    """Where we are in the 4-year cycle + the Hirsch midterm-drawdown window, with MEASURED
    odds. Pure; never raises. `show` is True only when the chip has something worth saying
    (a midterm year — the only bucket with even a suggestive edge)."""
    try:
        d = _as_date(asof)
    except Exception:
        d = _dt.date.today()
    y = d.year
    yt = year_in_term(y)
    is_mid = yt == 2
    in_window = is_mid and _in_span(d, _WIN_START, _WIN_END)
    in_h2 = is_mid and _in_span(d, (7, 1), (12, 31))
    in_trough = is_mid and _in_span(d, _TROUGH_START, _TROUGH_END)
    le, lz = TERM_LABEL[yt]
    out = {
        "schema": "election_cycle.v1",
        "asof": d.isoformat(),
        "year": y,
        "year_in_term": yt,
        "label_en": le,
        "label_zh": lz,
        "is_midterm": bool(is_mid),
        "in_drawdown_window": bool(in_window),
        "in_h2": bool(in_h2),
        "in_trough_window": bool(in_trough),
        # the Hirsch projection — a tendency, not a forecast
        "trough_window_en": f"historically bottoms ~Aug–Oct {y}" if is_mid else None,
        "trough_window_zh": f"历史上约在 {y} 年 8–10 月见底" if is_mid else None,
        "stat_en": _STAT_EN, "stat_zh": _STAT_ZH,
        "slice_en": _SLICE_EN, "slice_zh": _SLICE_ZH,
        "caveat_en": _CAVEAT_EN, "caveat_zh": _CAVEAT_ZH,
        "show": bool(is_mid),
    }
    out["sector_bias"] = sector_bias(d)
    return out


def modulation(asof=None, spy_risk_on=None) -> dict:
    """The Risk-Radar modulation. Returns:
      band_delta — points to LOWER the watch + caution thresholds (early tiers only). Non-zero
                   ONLY in a midterm Apr-Oct window AND spy_risk_on (the measured non-collinear
                   1.25x cut). It can NEVER touch the elevated/risk-off bands, so the calendar
                   cannot originate a loud banner.
      gross_mult — small sizing trim (<=1.0) applied across the whole midterm Apr-Oct window
                   (a position-sizing prior; the deeper-drawdown season). 1.0 otherwise.
      active     — whether anything is being modulated.
    Pure; never raises."""
    try:
        d = _as_date(asof)
    except Exception:
        d = _dt.date.today()
    in_window = (year_in_term(d.year) == 2) and _in_span(d, _WIN_START, _WIN_END)
    # band nudge ONLY in the risk-ON slice (when risk-OFF, midterm is near-collinear with price
    # already weak — adding sensitivity there would just double-count the radar's own read).
    risk_on = bool(spy_risk_on) if spy_risk_on is not None else False
    band_delta = _BAND_NUDGE if (in_window and risk_on) else 0.0
    gross_mult = _GROSS_MULT if in_window else 1.0
    reason_en = reason_zh = None
    if in_window:
        if band_delta > 0:
            reason_en = ("Midterm risk-on window — early-tier sensitivity raised (~1.25× base) "
                         "and gross trimmed; loud banner still requires the broad tape to break.")
            reason_zh = "中期选举「风险开」窗口——提高早期预警灵敏度（约 1.25 倍）并小幅降仓；响亮警报仍需大盘破位。"
        else:
            reason_en = "Midterm drawdown window — gross trimmed as a sizing prior (deeper-drawdown season)."
            reason_zh = "中期回撤窗口——按季节性偏深回撤的先验小幅降仓。"
    return {
        "band_delta": float(band_delta),
        "gross_mult": float(gross_mult),
        "active": bool(in_window),
        "risk_on_slice": bool(band_delta > 0),
        "reason_en": reason_en,
        "reason_zh": reason_zh,
    }


def sector_bias(asof=None) -> dict | None:
    """Display-only defensive-rotation tilt for a midterm H2 (Jul-Dec). None otherwise.
    Labelled as mostly generic seasonality so it can't be mistaken for a signal."""
    try:
        d = _as_date(asof)
    except Exception:
        d = _dt.date.today()
    if not ((year_in_term(d.year) == 2) and _in_span(d, (7, 1), (12, 31))):
        return None
    return {
        "favor": [{"ticker": t, "en": e, "zh": z} for t, e, z in _FAVOR],
        "avoid": [{"ticker": t, "en": e, "zh": z} for t, e, z in _AVOID],
        "note_en": _SECTOR_EN, "note_zh": _SECTOR_ZH,
        "display_only": True,
    }
