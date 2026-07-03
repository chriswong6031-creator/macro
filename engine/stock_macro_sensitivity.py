"""Per-stock MACRO SENSITIVITY — the single-name rate / inflation read (display-only).

A fast-follow to the Rate & Inflation Transmission foundation
(engine/rate_inflation_transmission.py + data/transmission/*.json). The transmission
layer answers the *cross-asset* question — how the rate/inflation state propagates into
each asset CLASS. This leaf brings that read down to the SINGLE STOCK the user is looking
at, surfacing a "Macro sensitivity" chip on stock.html.

WHAT IT IS — four honest, never-scored reads assembled from data we already ship:

  1. rate-beta tier   the name's OWN orthogonal rate beta (engine.factor_exposure's TLT
                      factor — the marginal duration beyond market/growth/size), carried
                      with its standard error as a HIGH / MEDIUM / LOW precision tier. The
                      SE is reconstructed in closed form from the exposure export
                      (idio_vol, n, the rate factor's annual vol) — no new regression:
                         SE(beta) = idio_vol / (factor_vol_rates * sqrt(n))
                      Every surface carries the MANDATORY caveat that single-name secondary
                      betas are noisy (the exposure Phase-0 measured persist≈0.36) — trust
                      the portfolio aggregate, not any one stock's rate beta.

  2. duration bucket  long / neutral / short. ANCHORED on the name's SECTOR-ETF orthogonal
                      rate beta (the sector aggregate the foundation says to trust — XLRE /
                      XLU / XLB / XLV / XLP read long, XLE / XLF short, tech / disc /
                      industrials neutral because their rate risk runs through their market
                      / growth beta, not a distinct duration leg). The name's own beta only
                      *refines* the anchor (and flags a divergence when it is itself
                      well-estimated), never overrides it. Falls back to engine.conditions
                      sector_macro_beta when the sector ETF is unavailable.

  3. regime read      headwind / tailwind. Combines the duration bucket with the LIVE
                      transmission state (data/transmission/latest.json — rates regime,
                      direction, the real-rate chain's activation): a long-duration name into
                      a restrictive, rising-real-rate regime → rate headwind; a short-duration
                      / rate-beneficiary into the same regime → tailwind. Omitted when the
                      transmission snapshot is absent (the chip degrades to duration + tier).

  4. inflation label  hedge / negative / neutral. A STRUCTURAL classification from the
                      stock's archetype (engine.stock_fundamentals) + sector: energy /
                      materials / deep-value tilt = inflation hedge (grounded by the sector
                      ETF's oil-factor beta where it is informative); long-duration growth =
                      negative inflation beta. Softer-caveated than the rate read because the
                      measured forward-return IC of a sticky-inflation gap is negative for
                      almost every sector (higher-for-longer de-rates everything) and so is
                      not a clean per-sector hedge discriminator.

DISCIPLINE — display / LLM-context ONLY, NEVER scored. Nothing here touches
stock_score conviction, cycles.py buy-setups, or any ladder. Additive, graceful: a missing
input degrades the relevant read to None and the chip simply shows less. Bilingual
throughout. Scoped to US single stocks (a resolvable GICS sector) for the MVP.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass

from lib import config

log = logging.getLogger(__name__)

# Sector name (as the stock library carries it on each record) -> SPDR sector ETF, all
# present in data/yahoo and in the factor_betas export. The ETF's orthogonal rate beta is
# the robust per-sector duration anchor. The library mixes two naming schemes — full GICS
# names (from the breadth universe) and SPDR short names (from the sector-ETF holdings) —
# so both are mapped.
GICS_ETF = {
    # full GICS names (breadth universe)
    "Energy": "XLE", "Information Technology": "XLK", "Financials": "XLF",
    "Health Care": "XLV", "Industrials": "XLI", "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP", "Utilities": "XLU", "Materials": "XLB",
    "Real Estate": "XLRE", "Communication Services": "XLC",
    # SPDR short-name aliases (sector-ETF holdings)
    "Technology": "XLK", "Communications": "XLC",
}
_GICS_ETF_LC = {k.lower(): v for k, v in GICS_ETF.items()}

# duration thresholds on the orthogonal rate (TLT) beta. + beta = bond-like / long
# duration (hurt by rising yields); - beta = rate-beneficiary / short duration. The
# dead-band keeps near-zero (market-channel-only) names neutral; the min-t gate keeps a
# direction only when the beta is estimated above noise.
DUR_BETA = 0.10
MIN_T = 1.5
# per-NAME precision tiers from the t-stat (in-sample precision; the OOS-noise concern is
# carried separately by the mandatory caveat).
TIER_HIGH_T = 2.5
TIER_MED_T = 1.5
# the sector ETF's oil-factor beta above which we treat the sector as a real-asset /
# inflation-shock beneficiary (energy reads ~0.25; everything else ~0).
OIL_HEDGE_BETA = 0.10

# archetypes (engine.stock_fundamentals.ARCHETYPES keys) that lean value / real-asset.
_VALUE_ARCH = {"deep_value"}
# ...and the long-duration-growth archetypes that carry a negative inflation beta.
# secular_growth and broken_growth are added here: both are CAGR-driven growth buckets
# introduced in v2; under v1 those names were mostly quality_compounder or
# high_beta_momentum, so extending _GROWTH_ARCH preserves inflation_label semantics
# for reclassified names without changing the read for non-growth bucket members.
_GROWTH_ARCH = {"high_beta_momentum", "speculative_unprofitable", "quality_compounder",
                "secular_growth", "broken_growth"}
# sectors whose duration is dominated by long-duration GROWTH (their rate risk runs
# through the market/growth factor, so the orthogonal sector beta reads ~neutral) — used
# only for the inflation classification, where the growth tilt is the relevant axis.
_GROWTH_SECTORS = {"Information Technology", "Communication Services", "Consumer Discretionary",
                   "Technology", "Communications"}
_REAL_ASSET_SECTORS = {"Energy", "Materials"}

# the mandatory single-name caveat — verbatim on every chip.
CAVEAT = {
    "en": "Single-name secondary betas are noisy — trust the portfolio aggregate, not "
          "any one stock's rate beta (measured out-of-sample persistence ≈ 0.36).",
    "zh": "单一个股的次级beta噪声很大——应相信组合层面的汇总，而非任何单只股票的利率beta"
          "（实测样本外持续性约0.36）。",
}


# --------------------------------------------------------------------------- #
# context loader (file I/O kept here so assess() stays a pure transform)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Context:
    """Everything assess() needs, loaded once per build."""
    betas: dict                     # factor_betas["betas"]: ticker -> beta record
    factor_vol_rates: float | None  # annualized vol of the orthogonal rate factor
    rate_persist: float | None      # the rate factor's OOS persistence (Phase-0)
    rate_state: dict | None         # transmission latest.state.rates (regime/direction/…)
    infl_state: dict | None         # transmission latest.state.inflation
    real_rate_active: bool          # the real-rate transmission chain is live
    calibrated: bool                # the transmission layer is calibrated & current


def load_context(site_dir=None, data_dir=None) -> Context:
    """Read the factor-beta export + the live transmission snapshot. Graceful: any
    missing/garbled file degrades the corresponding read, never raises."""
    site = site_dir or (config.ROOT / config.load()["storage"]["site_dir"])
    data = data_dir or config.data_dir()

    betas: dict = {}
    fvol = None
    persist = None
    fp = site / "factor_betas.json"
    if fp.exists():
        try:
            exp = json.loads(fp.read_text()) or {}
            betas = exp.get("betas", {}) or {}
            fvol = (exp.get("factor_vol_ann") or {}).get("rates")
            for f in exp.get("factors", []):
                if f.get("key") == "rates":
                    persist = f.get("persist")
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("factor_betas.json unreadable (%s)", e)

    rate_state = infl_state = None
    real_rate_active = False
    calibrated = False
    tp = data / "transmission" / "latest.json"
    if tp.exists():
        try:
            tj = json.loads(tp.read_text()) or {}
            state = tj.get("state") or {}
            rate_state = state.get("rates")
            infl_state = state.get("inflation")
            calibrated = bool(tj.get("calibrated"))
            for ch in tj.get("chains", []):
                if ch.get("id") == "real_rate":
                    real_rate_active = bool(ch.get("active"))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("transmission latest.json unreadable (%s)", e)

    return Context(betas=betas, factor_vol_rates=fvol, rate_persist=persist,
                   rate_state=rate_state, infl_state=infl_state,
                   real_rate_active=real_rate_active, calibrated=calibrated)


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def beta_se(rec: dict, factor_vol_rates: float | None) -> float | None:
    """Closed-form OLS standard error of the orthogonal rate beta, reconstructed from the
    exposure export. The factors are mutually orthogonal so the slope decouples to
    cov/var and SE(b) = s_resid / sqrt(n·var(g)); both the residual and factor vols are
    annualized in the export so the annualization cancels."""
    if not rec or not factor_vol_rates:
        return None
    idio = rec.get("idio_vol")
    n = rec.get("n")
    if idio is None or n is None or rec.get("rates") is None or n <= 0:
        return None
    try:
        return idio / (factor_vol_rates * math.sqrt(n))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _tstat(beta: float | None, se: float | None) -> float | None:
    if beta is None or not se:
        return None
    return abs(beta) / se


def rate_beta_tier(t: float | None) -> str:
    """Per-name precision tier from the t-stat. HIGH/MEDIUM = the beta is estimated above
    noise this window; LOW = within noise (or no SE). Always paired with CAVEAT."""
    if t is None:
        return "low"
    if t >= TIER_HIGH_T:
        return "high"
    if t >= TIER_MED_T:
        return "medium"
    return "low"


def _bucket_from_beta(beta: float | None, t: float | None) -> str:
    """long / neutral / short from a signed rate beta, gated by precision & a dead-band."""
    if beta is None or t is None or t < MIN_T or abs(beta) < DUR_BETA:
        return "neutral"
    return "long" if beta > 0 else "short"


def duration_bucket(name_beta, name_t, sector_beta, sector_t,
                    sector_macro_beta_val=None) -> dict:
    """Duration bucket: SECTOR-ETF beta is the robust anchor; the name's own beta only
    refines it (and flags a divergence when the name is itself well-estimated). Falls back
    to the name's own beta, then to sector_macro_beta, then neutral."""
    sec_bucket = _bucket_from_beta(sector_beta, sector_t)
    name_bucket = _bucket_from_beta(name_beta, name_t)
    name_tier = rate_beta_tier(name_t)
    diverges = False
    src = "sector"

    if sector_beta is not None and sec_bucket != "neutral":
        bucket = sec_bucket
        # a HIGH-precision name beta that points the OPPOSITE way is worth flagging
        if name_tier == "high" and name_bucket != "neutral" and name_bucket != sec_bucket:
            diverges = True
    elif sector_beta is not None and sec_bucket == "neutral":
        # sector is duration-neutral; let a HIGH-precision name beta speak for itself
        if name_tier == "high" and name_bucket != "neutral":
            bucket, src = name_bucket, "name"
        else:
            bucket = "neutral"
    elif name_bucket != "neutral" and name_tier in ("high", "medium"):
        bucket, src = name_bucket, "name"            # no sector ETF — use the name
    elif sector_macro_beta_val is not None and abs(sector_macro_beta_val) >= 0.35:
        bucket, src = ("long" if sector_macro_beta_val > 0 else "short"), "macro_beta"
    else:
        bucket, src = "neutral", "fallback"
    return {"bucket": bucket, "src": src, "diverges": diverges}


def regime_read(bucket: str, rate_state: dict | None, real_rate_active: bool) -> str | None:
    """headwind / tailwind / neutral for THIS name into the live rate regime. None when
    there is no live transmission state to read against. A head/tailwind is asserted only
    when rates are actually moving (a direction AND the real-rate transmission chain live);
    a dormant rate channel leaves even a long/short-duration name rate-neutral."""
    if not rate_state:
        return None
    direction = rate_state.get("direction")          # rising / falling / stable
    if bucket == "neutral" or direction not in ("rising", "falling") or not real_rate_active:
        return "neutral"
    rising = direction == "rising"
    if bucket == "long":
        return "headwind" if rising else "tailwind"
    return "tailwind" if rising else "headwind"      # short-duration is the mirror


def inflation_label(archetype_key, sector, sector_oil_beta=None) -> str:
    """hedge / negative / neutral — a STRUCTURAL inflation-beta classification."""
    if sector in _REAL_ASSET_SECTORS or archetype_key in _VALUE_ARCH \
            or (sector_oil_beta is not None and sector_oil_beta >= OIL_HEDGE_BETA):
        return "hedge"
    if sector in _GROWTH_SECTORS and archetype_key in _GROWTH_ARCH:
        return "negative"
    return "neutral"


# --------------------------------------------------------------------------- #
# bilingual label tables
# --------------------------------------------------------------------------- #
TIER_LABEL = {"high": ("High", "高"), "medium": ("Medium", "中"), "low": ("Low / noisy", "低／噪声")}
DUR_LABEL = {
    "long": ("Long-duration", "长久期"),
    "short": ("Short-duration", "短久期"),
    "neutral": ("Duration-neutral", "久期中性"),
}
REGIME_LABEL = {
    "headwind": ("rate headwind", "利率逆风"),
    "tailwind": ("rate tailwind", "利率顺风"),
    "neutral": ("rate-neutral", "利率中性"),
}
INFL_LABEL = {
    "hedge": ("Inflation hedge", "通胀对冲"),
    "negative": ("Negative inflation beta", "负通胀beta"),
    "neutral": ("Inflation-neutral", "通胀中性"),
}
_RATE_REGIME_ZH = {"restrictive": "偏紧", "accommodative": "宽松", "neutral": "中性"}
_RATE_DIR_ZH = {"rising": "上行", "falling": "下行", "stable": "平稳"}


def _bil(en, zh):
    return {"en": en, "zh": zh}


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def assess(ticker: str, sector: str | None, archetype_key: str | None, ctx: Context,
           sector_macro_beta_val: float | None = None) -> dict | None:
    """Assemble the per-stock Macro-sensitivity payload, or None if out of scope / no data.

    Scoped to US single stocks with a resolvable GICS sector and a rate beta in the
    factor-exposure export. Every text field is bilingual {en, zh}; nothing here is scored.
    """
    if not sector:
        return None
    etf = GICS_ETF.get(sector) or _GICS_ETF_LC.get(str(sector).strip().lower())
    if not etf:                                        # ETFs / commodities / crypto: out of scope
        return None
    name = ctx.betas.get(ticker)
    if not name or name.get("rates") is None:          # not in the exposure universe
        return None

    name_beta = float(name["rates"])
    name_se = beta_se(name, ctx.factor_vol_rates)
    name_t = _tstat(name_beta, name_se)
    tier = rate_beta_tier(name_t)

    sec = ctx.betas.get(etf) or {}
    sector_beta = sec.get("rates")
    sector_beta = float(sector_beta) if sector_beta is not None else None
    sector_t = _tstat(sector_beta, beta_se(sec, ctx.factor_vol_rates))
    sector_oil = sec.get("oil")

    dur = duration_bucket(name_beta, name_t, sector_beta, sector_t, sector_macro_beta_val)
    bucket = dur["bucket"]
    regime = regime_read(bucket, ctx.rate_state, ctx.real_rate_active)
    infl = inflation_label(archetype_key, sector, sector_oil)

    # ---- headline (duration + regime) ------------------------------------- #
    dur_en, dur_zh = DUR_LABEL[bucket]
    rs = ctx.rate_state or {}
    regime_word = rs.get("regime")
    direction = rs.get("direction")
    if regime is None:
        head_en = f"{dur_en} name (live rate regime unavailable)."
        head_zh = f"{dur_zh}标的（实时利率环境暂不可用）。"
    else:
        reg_en, reg_zh = REGIME_LABEL[regime]
        env_en = (f"a {regime_word}, {direction}-real-rate regime"
                  if regime_word and direction else "the current rate regime")
        env_zh = (f"{_RATE_REGIME_ZH.get(regime_word, regime_word)}、实际利率{_RATE_DIR_ZH.get(direction, direction)}的环境"
                  if regime_word and direction else "当前利率环境")
        arrow_en = " → " if regime != "neutral" else " — "
        if regime == "neutral" and bucket == "neutral":
            head_en = "Rate risk runs through its market / growth beta, not a distinct duration leg."
            head_zh = "其利率风险通过市场／成长beta体现，并无独立的久期暴露。"
        else:
            head_en = f"{dur_en} name into {env_en}{arrow_en}{reg_en}."
            head_zh = f"{dur_zh}标的进入{env_zh}{('→' if regime != 'neutral' else '——')}{reg_zh}。"

    # ---- detail (single-name beta + sector anchor + inflation) ------------ #
    beta_txt = f"{name_beta:+.2f}" + (f" ± {name_se:.2f}" if name_se is not None else "")
    tier_en, tier_zh = TIER_LABEL[tier]
    infl_en, infl_zh = INFL_LABEL[infl]
    sec_part_en = ""
    sec_part_zh = ""
    if sector_beta is not None:
        anchor_en = DUR_LABEL[_bucket_from_beta(sector_beta, sector_t)][0].lower()
        sec_part_en = f" Sector anchor ({etf}) reads {anchor_en} ({sector_beta:+.2f})."
        anchor_zh = DUR_LABEL[_bucket_from_beta(sector_beta, sector_t)][1]
        sec_part_zh = f" 板块锚（{etf}）为{anchor_zh}（{sector_beta:+.2f}）。"
    div_en = " The name's own beta diverges from its sector." if dur["diverges"] else ""
    div_zh = " 该股自身beta与其板块相悖。" if dur["diverges"] else ""
    detail_en = (f"Own orthogonal rate (TLT) beta {beta_txt} — {tier_en.lower()} precision."
                 f"{sec_part_en}{div_en} {infl_en}.")
    detail_zh = (f"自身正交利率（TLT）beta {beta_txt}——精度{tier_zh}。"
                 f"{sec_part_zh}{div_zh} {infl_zh}。")

    out = {
        "ticker": ticker,
        "rate_beta": round(name_beta, 3),
        "rate_beta_se": round(name_se, 3) if name_se is not None else None,
        "t_stat": round(name_t, 2) if name_t is not None else None,
        "tier": tier,
        "tier_label": _bil(tier_en, tier_zh),
        "duration": bucket,
        "duration_label": _bil(dur_en, dur_zh),
        "duration_src": dur["src"],
        "name_diverges": dur["diverges"],
        "sector_etf": etf,
        "sector_beta": round(sector_beta, 3) if sector_beta is not None else None,
        "regime": regime,
        "regime_label": _bil(*REGIME_LABEL[regime]) if regime else None,
        "inflation": infl,
        "inflation_label": _bil(infl_en, infl_zh),
        "headline": _bil(head_en, head_zh),
        "detail": _bil(detail_en, detail_zh),
        "caveat": dict(CAVEAT),
        "rate_state": ({"regime": regime_word, "direction": direction,
                        "real_10y": rs.get("real_10y")} if ctx.rate_state else None),
        "infl_state": ({"regime": (ctx.infl_state or {}).get("regime"),
                        "direction": (ctx.infl_state or {}).get("direction")}
                       if ctx.infl_state else None),
        "calibrated": ctx.calibrated,
        "persist": ctx.rate_persist,
    }
    return out
