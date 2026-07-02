"""Physical bottleneck nowcast — T1 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md).

THE IDEA. The June-2024 13D HBM call was a SUPPLY-constraint call with zero revision
numbers: "HBM chips are sold out for the next two years… manufacturers are investing to
increase capacity," supply ~100% concentrated, the market focused elsewhere. That is the
genuinely LEADING signal — it precedes the estimate revisions by quarters. This engine
generalizes it: per theme/industry, is the supply side physically full?

Eight physical legs, each free:
  leg1 capacity full    : cap-U high (z of CAPUTLG{naics}S)                [FRED]
  leg2 inventory drained: inventories/sales falling (-z of MNFCTRIRSA)     [FRED]
  leg3 backlog building  : unfilled-orders/shipments rising                 [FRED]
  leg4 pricing power     : industry PPI YoY accelerating                   [FRED]
  leg6 language          : EDGAR "sold out / capacity constrained / on
                           allocation" mention ACCEL for the theme's filers [EDGAR FTS]
  leg7 member inventory  : per-member XBRL inventory-days YoY trend        [EDGAR XBRL]
  leg8 member backlog    : per-member XBRL RPO YoY growth                  [EDGAR XBRL]
  (margin trend feeds pricing_power axis in foresight_score.py, not a band leg)

Weights 0.25 (leg6) and provisional XBRL-leg weights are PROVISIONAL — shadow-
calibration pending (§3.2 of the upgrade spec). The live cutoff and z-threshold are
also PROVISIONAL until the PIT backtest (Wave 3a) produces empirically-earned values.
Shadow variants are logged to data/foresight/shadow_bands_log.jsonl from day one
(see _shadow_log_cutoffs; band-level rows — the STAGE-level shadow ledger is
engine/foresight_shadow.py's shadow_log.jsonl; the two schemas never share a file
per the W3b review).

W5a FINGERPRINT INTEGRATION (backtest-redirected Q2):
The NAICS legs (legs 1-4) use 3 shared industry codes for 7 themes — MU/WDC and
AMAT/LRCX get the SAME cap-U read despite being different businesses. Legs 7-8 are
per-theme by construction: they read each theme's OWN members' filed numbers. The 11
previously unmapped themes now get a real numeric path when ≥3 members report.

ANTI-LAUNDERING: legs 7-8 are numeric (XBRL-filed numbers) and participate in the
numeric_composite / numeric_band like legs 1-4 — they are not language and do not
trigger the text-only cap. The anti-laundering discriminator (text cannot tip numeric)
is unaffected: language_z_gated is still excluded from numeric_avail.

The HBM template fires when legs 1-4 fire TOGETHER (demand outrunning supply). leg6
can additionally lift a theme to TIGHT (text)/TIGHTENING (text) for unmapped themes.
DISPLAY-ONLY; returns None/partial cleanly until collectors run.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine import theme_fingerprint as fp
from lib import config, store

log = logging.getLogger(__name__)

MIN_OBS = 24               # need >=24 monthly points before a z-score is trustworthy
Z_WIN = 120               # trailing months for the z baseline (10y); None = full history

# Per-theme NAICS map — only themes with a clean free capacity/PPI series. Others are
# left UNMAPPED (honest: no per-industry physical series exists for them on free data).
THEME_MAP = {
    "memory_storage":          {"cap_u": "CAPUTLG3344S", "ppi": "PCU334413334413", "naics": "3344"},
    "ai_semiconductors":       {"cap_u": "CAPUTLG3344S", "ppi": "PCU334413334413", "naics": "3344"},
    "semicap_equipment":       {"cap_u": "CAPUTLG3344S", "ppi": "PCU334413334413", "naics": "3344"},
    "data_center_power":       {"cap_u": "CAPUTLG334S", "naics": "334"},
    "grid_electrification":    {"cap_u": "CAPUTLG334S", "naics": "334"},
    "copper_steel_electrify":  {"cap_u": "CAPUTLG331S", "ppi": "PCU331110331110", "naics": "331"},
    "rare_earth_critical_min": {"cap_u": "CAPUTLG331S", "ppi": "PCU331110331110", "naics": "331"},
}

# economy-wide legs shared by every theme (no per-NAICS free series for these)
INV_SALES = "MNFCTRIRSA"
UNFILLED, SHIPMENTS = "AMTMUO", "AMTMVS"
DELIVERY = ["DTCISA156MSFRBPHI", "DTMUAMFRBDAL"]    # regional-Fed delivery-time diffusion
PRICES_RECV = "PFGIUAMFRBDAL"

# Numeric legs (legs 1-4): weights rebalanced to 0.65 total to accommodate leg6_language
# at 0.20 PROVISIONAL and legs 7-8 at 0.075 each PROVISIONAL (total 0.15).
# Original ratios for legs 1-4: 0.28:0.22:0.25:0.25, now scaled to 0.65 total:
# 0.28*0.65/1.0≈0.182, 0.22*0.65/1.0≈0.143, 0.25*0.65/1.0≈0.1625 each.
# Rounded to sum exactly to 1.0:
#   leg1 0.182 + leg2 0.143 + leg3 0.163 + leg4 0.162 = 0.65
#   leg6 0.20 + leg7 0.075 + leg8 0.075 = 0.35
#   total = 1.00
#
# ALL WEIGHTS PROVISIONAL — shadow-calibration pending (§3.2 of the upgrade spec).
# Once the PIT backtest runs and forward grading has ≥30d of flags per leg, the
# calibration loop will promote/adjust these values. Until then each leg carries a
# 'provisional' tag in the output and none is used alone to assert conviction.
#
# Shadow-grid registration: leg7 + leg8 are candidates for the §3.2 loop.
# They participate in numeric_composite / numeric_band (XBRL filed numbers, not text).
WEIGHTS = {
    "leg1_capacity":   0.182,   # PROVISIONAL
    "leg2_inventory":  0.143,   # PROVISIONAL
    "leg3_backlog":    0.163,   # PROVISIONAL
    "leg4_pricing":    0.162,   # PROVISIONAL
    "leg6_language":   0.20,    # PROVISIONAL (down from 0.25 to accommodate legs 7-8)
    "leg7_member_inventory": 0.075,  # PROVISIONAL — W5a XBRL fingerprint
    "leg8_member_backlog":   0.075,  # PROVISIONAL — W5a XBRL fingerprint
}

# Shadow z-cutoff candidates for the language leg (§3.2 shadow-threshold ledger).
# These are logged nightly but DO NOT affect the live band — the live cutoff is LANG_Z_LIVE.
LANG_Z_LIVE = 0.5        # PROVISIONAL live cutoff; anything > 0 = net acceleration
LANG_Z_SHADOW_CUTOFFS = [1.0, 1.5, 2.0]

# Minimum distinct affirmative filers required for a text-only band to count.
# With polarity=null (fallback b), all non-negated hits count; ≥2 distinct tickers required.
LANG_MIN_FILERS = 2


def _series(sid: str) -> pd.Series | None:
    df = store.read("fred", sid)
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].dropna()
    return s if len(s) else None


def _z(s: pd.Series | None) -> float | None:
    """Latest value z-scored against its trailing-Z_WIN history. None if too short/flat."""
    if s is None or len(s) < MIN_OBS:
        return None
    base = s.iloc[-Z_WIN:] if Z_WIN else s
    mu, sd = float(base.mean()), float(base.std(ddof=0))
    if sd == 0 or np.isnan(sd):
        return None
    return round((float(s.iloc[-1]) - mu) / sd, 2)


def _yoy(s: pd.Series | None) -> pd.Series | None:
    if s is None or len(s) < 13:
        return None
    return s.pct_change(12).dropna() * 100.0


def _latest(s: pd.Series | None) -> float | None:
    if s is None or not len(s):
        return None
    return round(float(s.iloc[-1]), 2)


def _delivery_diffusion() -> float | None:
    """Mean of the regional-Fed current-delivery-time diffusion series (>0 = lengthening)."""
    vals = [_latest(_series(sid)) for sid in DELIVERY]
    vals = [v for v in vals if v is not None]
    return round(float(np.mean(vals)), 2) if vals else None


def _backlog_ratio() -> pd.Series | None:
    unf, shp = _series(UNFILLED), _series(SHIPMENTS)
    if unf is None or shp is None:
        return None
    df = pd.concat([unf, shp], axis=1).dropna()
    if df.empty:
        return None
    return (df.iloc[:, 0] / df.iloc[:, 1]).dropna()


def _language_accel(tickers: list[str], parquet_path: Path | None = None) -> tuple[float | None, int, int]:
    """EDGAR bottleneck-phrase mention acceleration for the theme's filers (last 120d vs
    prior 120d).

    With polarity=null (fallback b, no snippet available), 'affirmative' count = all hits
    where polarity is not 'negated'. Distinct-filer gate is applied at the call site.

    Returns (accel_ratio, recent_hits, n_distinct_filers). None if the collector hasn't run.
    """
    if parquet_path is None:
        parquet_path = config.data_dir() / "edgar" / "bottleneck_hits.parquet"
    if not parquet_path.exists():
        return None, 0, 0
    try:
        df = pd.read_parquet(parquet_path)
    except Exception:  # noqa: BLE001
        return None, 0, 0
    if df.empty or "ticker" not in df.columns or "file_date" not in df.columns:
        return None, 0, 0
    df = df[df["ticker"].isin(tickers)].copy()
    if df.empty:
        return 0.0, 0, 0

    # Filter out negated hits when polarity column is available and populated
    if "polarity" in df.columns:
        df = df[df["polarity"] != "negated"]

    df["file_date"] = pd.to_datetime(df["file_date"])
    end = df["file_date"].max()
    recent = df[df["file_date"] > end - pd.Timedelta(days=120)]
    prior = df[(df["file_date"] <= end - pd.Timedelta(days=120)) &
               (df["file_date"] > end - pd.Timedelta(days=240))]
    nr, npq = len(recent), len(prior)
    accel = round((nr - npq) / max(npq, 1), 2)
    n_distinct = recent["ticker"].nunique() if len(recent) else 0
    return accel, nr, n_distinct


def _language_z(accel: float | None) -> float | None:
    """Convert language accel ratio to a z-like score for weighting.
    PROVISIONAL: simple clip-and-scale pending PIT backtest calibration (Wave 3a)."""
    if accel is None:
        return None
    # Treat accel > 0 as positive, clip to [-2, 2] for the weighted-sum
    return round(float(np.clip(accel, -2.0, 2.0)), 2)


def _is_fingerprint_only(numeric_avail: dict) -> bool:
    """Return True when the only numeric legs available are XBRL fingerprint legs.

    fingerprint-only = numeric_avail is a non-empty subset of {leg7_member_inventory,
    leg8_member_backlog} (no FRED legs 1-4 present). This is always the case for unmapped
    themes — they have no FRED NAICS series at all. For mapped themes it would only trigger
    if ALL of legs 1-4 are absent but a fingerprint exists (an edge case).
    """
    if not numeric_avail:
        return False
    _FINGERPRINT_LEGS = {"leg7_member_inventory", "leg8_member_backlog"}
    return set(numeric_avail.keys()) <= _FINGERPRINT_LEGS


def _band(composite: float | None, n_legs: int, regime: bool,
          lang_accel: float | None = None, n_filers: int = 0,
          text_only: bool = False, fingerprint_only: bool = False) -> str:
    """Return a band string.

    text_only=True: only the language leg contributed (no numeric FRED legs). In this
    case the band is capped at 'TIGHT (text)' / 'TIGHTENING (text)' / None.

    fingerprint_only=True: only XBRL fingerprint legs (leg7/leg8) contributed — annual
    cadence, not real-time FRED. Tightening-direction bands get a '(fingerprint)' suffix
    to mark them as annual-only and prevent conflation with FRED-backed reads.
    LOOSE and NEUTRAL stay plain (only tightening-direction overclaims).
    """
    if text_only:
        if composite is None:
            return "AWAITING_DATA"
        if composite > LANG_Z_LIVE and n_filers >= LANG_MIN_FILERS:
            return "TIGHT (text)"
        if composite > 0 and n_filers >= LANG_MIN_FILERS:
            return "TIGHTENING (text)"
        return "NEUTRAL"

    if composite is None:
        return "AWAITING_DATA"
    if regime and composite > 1.5:
        band = "SOLD_OUT"
    elif composite > 0.75:
        band = "TIGHT"
    elif composite > 0.25:
        band = "TIGHTENING"
    elif composite < -0.25:
        band = "LOOSE"
    else:
        band = "NEUTRAL"

    if fingerprint_only:
        # Annual XBRL: emit fingerprint-variant for tightening-direction bands only.
        # No SOLD_OUT on annual-only data (annual cadence can't confirm sold-out state).
        if band == "TIGHT":
            return "TIGHT (fingerprint)"
        if band == "TIGHTENING":
            return "TIGHTENING (fingerprint)"
        if band == "SOLD_OUT":
            return "TIGHT (fingerprint)"  # no SOLD_OUT on annual-only data
        # LOOSE and NEUTRAL stay plain

    return band


def _shadow_log_cutoffs(theme_key: str, asof: str | None, lang_accel: float | None,
                        n_filers: int) -> None:
    """Log shadow z-cutoff variants for the language leg per §3.2.

    For each cutoff in LANG_Z_SHADOW_CUTOFFS, compute what the text band WOULD be and
    append to data/foresight/shadow_bands_log.jsonl (append-only, deduped by theme+asof+cutoff).
    Non-fatal — the live band is unaffected.
    """
    if lang_accel is None or asof is None:
        return
    try:
        p = config.data_dir() / "foresight" / "shadow_bands_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        seen: set[tuple] = set()
        if p.exists():
            for line in p.read_text().splitlines():
                try:
                    e = json.loads(line)
                    seen.add((e.get("theme"), e.get("asof"), e.get("cutoff")))
                except Exception:  # noqa: BLE001
                    continue
        ts = datetime.now(timezone.utc).isoformat()
        lines = []
        for cutoff in LANG_Z_SHADOW_CUTOFFS:
            if (theme_key, asof, cutoff) in seen:
                continue
            if lang_accel > cutoff and n_filers >= LANG_MIN_FILERS:
                would_be = "TIGHT (text)"
            elif lang_accel > 0 and lang_accel <= cutoff and n_filers >= LANG_MIN_FILERS:
                would_be = "TIGHTENING (text)"
            else:
                would_be = "NEUTRAL"
            lines.append(json.dumps({
                "theme": theme_key, "asof": asof, "ts": ts,
                "cutoff": cutoff, "would_be_band": would_be,
                "lang_accel": lang_accel, "n_filers": n_filers,
            }, separators=(",", ":")))
        if lines:
            with p.open("a") as fh:
                fh.write("\n".join(lines) + "\n")
    except Exception as e:  # noqa: BLE001
        log.debug("shadow_log write failed (non-fatal): %s", e)


def _theme_bottleneck(theme_key: str, name: str, tickers: list[str], shared: dict,
                      asof: str | None = None,
                      data_dir=None) -> dict | None:
    """Compute per-theme bottleneck read including W5a XBRL fingerprint legs.

    data_dir: optional override for the fingerprint engine's parquet path
    (test fixtures pass tmp_path here; production passes None → config.data_dir()).
    """
    spec = THEME_MAP.get(theme_key)
    lang_accel, lang_hits, n_filers = _language_accel(tickers)
    lang_z = _language_z(lang_accel)

    # W5a: compute per-theme XBRL fingerprint legs (cache-read only, no network)
    _fp_data_dir = data_dir if data_dir is not None else config.data_dir()
    fingerprint = None
    leg7_inv = None
    leg8_rpo = None
    try:
        fingerprint = fp.compute_theme_fingerprint(theme_key, tickers, _fp_data_dir)
        if fingerprint is not None:
            leg7_inv = fingerprint.get("leg7_member_inventory")
            leg8_rpo = fingerprint.get("leg8_member_backlog")
    except Exception as e:  # noqa: BLE001 — fingerprint failure never blocks the rest
        log.debug("theme_fingerprint[%s] failed (non-fatal): %s", theme_key, e)

    if spec is None:
        # Unmapped theme: W5a extends this path — fingerprint legs (legs 7-8) provide a
        # real numeric path when ≥MIN_MEMBERS members report, making text_only=False.
        # Previously this path was language-only (text_only=True always).
        _shadow_log_cutoffs(theme_key, asof, lang_accel, n_filers)
        leg6_out = {
            "value": lang_z, "accel": lang_accel, "hits": lang_hits,
            "n_filers": n_filers, "provisional": True,
        }

        # Build leg dict: fingerprint legs count as numeric; language is text-gated
        lang_z_gated_u = lang_z if (lang_z is not None and n_filers >= LANG_MIN_FILERS) else None
        unmapped_legs: dict[str, float | None] = {"leg6_language": lang_z_gated_u}
        if leg7_inv is not None:
            unmapped_legs["leg7_member_inventory"] = leg7_inv
        if leg8_rpo is not None:
            unmapped_legs["leg8_member_backlog"] = leg8_rpo

        # Numeric legs for unmapped themes = only the fingerprint legs (no FRED NAICS here)
        unmapped_numeric: dict[str, float] = {
            k: v for k, v in unmapped_legs.items()
            if k in ("leg7_member_inventory", "leg8_member_backlog") and v is not None
        }

        if not unmapped_legs or all(v is None for v in unmapped_legs.values()):
            # No data at all for this theme
            if fingerprint is None and lang_accel is None:
                return None
        if lang_accel is None and not unmapped_numeric:
            return None

        # text_only=False when fingerprint legs are live (they are numeric, not text)
        has_numeric_fingerprint = bool(unmapped_numeric)
        text_only_unmapped = not has_numeric_fingerprint

        if unmapped_numeric:
            # Numeric fingerprint legs available → compute numeric_composite
            nwsum = sum(WEIGHTS[k] for k in unmapped_numeric if k in WEIGHTS)
            if nwsum > 0:
                unmapped_numeric_composite = round(
                    sum(WEIGHTS[k] * v for k, v in unmapped_numeric.items()
                        if k in WEIGHTS) / nwsum, 2)
            else:
                unmapped_numeric_composite = None
            unmapped_numeric_band = (
                _band(unmapped_numeric_composite, len(unmapped_numeric), False)
                if unmapped_numeric_composite is not None else None
            )
        else:
            unmapped_numeric_composite = None
            unmapped_numeric_band = None

        # Combined composite (numeric + language if available)
        avail_u = {k: v for k, v in unmapped_legs.items() if v is not None}
        if avail_u:
            wsum = sum(WEIGHTS[k] for k in avail_u if k in WEIGHTS)
            if wsum > 0:
                combined_composite = round(
                    sum(WEIGHTS[k] * v for k, v in avail_u.items()
                        if k in WEIGHTS) / wsum, 2)
                n_u = len(avail_u)
            else:
                combined_composite = None
                n_u = 0
        else:
            combined_composite = None
            n_u = 0

        # Fingerprint numeric_band still makes a theme Tier P under #996's corrected gate
        # — intentional (filed physical ≥ watch shelf); the cap+variant carries the honesty.
        # For unmapped themes, _is_fingerprint_only is always True when has_numeric_fingerprint
        # (they have no FRED legs at all — only legs 7-8 can be in unmapped_numeric).
        fingerprint_only_flag = _is_fingerprint_only(unmapped_numeric) if has_numeric_fingerprint else False

        if text_only_unmapped:
            # Language-only: cap at TIGHT (text) — original behaviour
            text_composite = lang_z
            band = _band(text_composite, 0, False,
                         lang_accel=lang_accel, n_filers=n_filers, text_only=True)
            tightness_out = None
        else:
            # Has numeric fingerprint legs: use fingerprint-variant band (not plain TIGHT)
            band = _band(combined_composite, n_u, False,
                         lang_accel=lang_accel, n_filers=n_filers,
                         text_only=False, fingerprint_only=fingerprint_only_flag)
            tightness_out = combined_composite
            # Anti-laundering: if numeric-only is not TIGHT, language can't make it TIGHT.
            # Check both plain and fingerprint-variant TIGHT bands.
            if band in ("TIGHT (fingerprint)", "TIGHT", "SOLD_OUT") and (
                    unmapped_numeric_composite is None
                    or unmapped_numeric_composite <= 0.75):
                band = "TIGHT (text)"
                text_only_unmapped = True
                fingerprint_only_flag = False
                tightness_out = None

        # Recompute unmapped_numeric_band with fingerprint variant
        if unmapped_numeric and unmapped_numeric_composite is not None and fingerprint_only_flag:
            unmapped_numeric_band = _band(
                unmapped_numeric_composite, len(unmapped_numeric), False,
                fingerprint_only=True
            )

        n_unmapped_legs = sum(1 for v in unmapped_legs.values() if v is not None)
        result = {
            "name": name,
            "naics": None,
            "band": band,
            "tightness": tightness_out,
            "regime": False,
            "n_legs": n_unmapped_legs,
            "legs": unmapped_legs,
            "cap_u_latest": None,
            "ppi_yoy_latest": None,
            "language_accel": lang_accel,
            "language_hits": lang_hits,
            "language_n_filers": n_filers,
            "leg6_detail": leg6_out,
            "numeric_composite": unmapped_numeric_composite,
            "numeric_band": unmapped_numeric_band,
            "weights": {k: WEIGHTS[k] for k in unmapped_legs if k in WEIGHTS},
            "text_only": text_only_unmapped,
            "fingerprint": fingerprint,
        }
        if fingerprint_only_flag:
            result["fingerprint_only"] = True
            result["basis"] = "annual"
        return result

    # --- MAPPED THEME (NAICS legs 1-4 available) ---

    cap_u = _series(spec["cap_u"])
    leg1 = _z(cap_u)                                     # capacity full
    leg2 = shared["leg2"]                                # inventory drained (economy-wide)
    leg3 = shared["leg3"]                                # backlog building (economy-wide)
    ppi = _series(spec["ppi"]) if spec.get("ppi") else None
    leg4 = _z(_yoy(ppi))                                 # pricing power (industry PPI yoy)

    # leg6 enters the COMPOSITE only past the ≥2-distinct-filers gate — a single filing
    # must never move the weighted read (the spec's "filers gate carries the noise
    # burden" applies to the composite path, not just the band relabel)
    lang_z_gated = lang_z if (lang_z is not None and n_filers >= LANG_MIN_FILERS) else None

    # W5a: fingerprint legs 7-8 are numeric (XBRL filed) → include in numeric_avail
    legs = {
        "leg1_capacity":  leg1,
        "leg2_inventory": leg2,
        "leg3_backlog":   leg3,
        "leg4_pricing":   leg4,
        "leg6_language":  lang_z_gated,
    }
    if leg7_inv is not None:
        legs["leg7_member_inventory"] = leg7_inv
    if leg8_rpo is not None:
        legs["leg8_member_backlog"] = leg8_rpo

    avail = {k: v for k, v in legs.items() if v is not None}
    # Numeric avail: all legs except language (language is text, not physical XBRL/FRED)
    # Fingerprint legs 7-8 ARE numeric — they are filed XBRL numbers, not language.
    numeric_avail = {k: v for k, v in avail.items() if k != "leg6_language"}

    if not avail:
        composite, n = None, 0
        regime = False
    else:
        # Re-normalize weights over available legs
        wsum = sum(WEIGHTS[k] for k in avail if k in WEIGHTS)
        composite = round(sum(WEIGHTS[k] * v for k, v in avail.items()
                              if k in WEIGHTS) / wsum, 2) if wsum else None
        n = len(avail)
        # regime requires ALL four numeric FRED legs positive and non-null
        # (fingerprint legs 7-8 do NOT gate the HBM regime — they are supplemental)
        numeric_legs = {k: legs[k] for k in ("leg1_capacity", "leg2_inventory",
                                              "leg3_backlog", "leg4_pricing")}
        regime = all((numeric_legs[k] or 0) > 0 for k in numeric_legs) \
            and None not in numeric_legs.values()

    # NUMERIC-ONLY composite — the sole discriminator for a plain (physically-confirmed)
    # TIGHT/SOLD_OUT. Without it, leg6 tipping the combined composite over 0.75 LAUNDERS
    # a text signal into a numeric band: text_only=False, TEXT_ONLY_CAP bypassed,
    # physical_confirmed=True, hot tone, mislabeled ledger row (review finding:
    # grid_electrification numeric 0.66 → combined 1.07 → shipped plain TIGHT @ 79.4).
    # W5a: legs 7-8 ARE numeric so they participate in numeric_composite.
    if numeric_avail:
        nwsum = sum(WEIGHTS[k] for k in numeric_avail if k in WEIGHTS)
        numeric_composite = round(
            sum(WEIGHTS[k] * v for k, v in numeric_avail.items()
                if k in WEIGHTS) / nwsum, 2) if nwsum else None
    else:
        numeric_composite = None

    # the band the NUMERIC legs alone would produce — surfaced so the shadow-threshold
    # machinery (engine/foresight_shadow.py) can re-derive candidate bands faithfully
    # (W3b review B3: an approximation that lost the numeric base band biased the
    # lang_z calibration toward text-bands)
    # For mapped themes: fingerprint_only is True only when ALL FRED legs 1-4 are absent
    # (all None in numeric_avail) but a fingerprint exists — a mapped-theme edge case.
    mapped_fingerprint_only = _is_fingerprint_only(numeric_avail)
    numeric_band = (_band(numeric_composite, len(numeric_avail), regime,
                          fingerprint_only=mapped_fingerprint_only)
                    if numeric_avail else None)

    # Determine if we have only the language leg (no numeric FRED or XBRL legs at all)
    text_only = not numeric_avail and lang_z is not None

    band = _band(composite, n, regime,
                 lang_accel=lang_accel, n_filers=n_filers, text_only=text_only,
                 fingerprint_only=mapped_fingerprint_only)

    if not text_only and numeric_avail and composite is not None:
        thresh = 1.5 if band in ("SOLD_OUT", "TIGHT (fingerprint)") else 0.75
        if band in ("TIGHT", "SOLD_OUT", "TIGHT (fingerprint)") and not (
                numeric_composite is not None and numeric_composite > thresh):
            # The combined composite cleared the threshold ONLY because of the text leg —
            # the numeric legs alone do not confirm. Demote to the text variant so the
            # cap binds, the tone stays warn, and the ledger row is honestly labeled.
            band = "TIGHT (text)"
            text_only = True
            mapped_fingerprint_only = False
        elif (lang_z_gated is not None and lang_z_gated > LANG_Z_LIVE
                and band not in ("TIGHT", "SOLD_OUT", "TIGHT (text)", "TIGHT (fingerprint)")):
            # Language alone clears TIGHT while numeric legs sit below it — text-only read
            band = "TIGHT (text)"
            text_only = True
            mapped_fingerprint_only = False

    # Shadow log for all themes with a language read
    _shadow_log_cutoffs(theme_key, asof, lang_accel, n_filers)

    leg6_out = {
        "value": lang_z, "accel": lang_accel, "hits": lang_hits,
        "n_filers": n_filers, "provisional": True,
    }

    result = {
        "name": name,
        "naics": spec["naics"],
        "band": band,
        "tightness": composite,
        "regime": regime,
        "n_legs": n,
        "legs": legs,
        "cap_u_latest": _latest(cap_u),
        "ppi_yoy_latest": _latest(_yoy(ppi)),
        "language_accel": lang_accel,
        "language_hits": lang_hits,
        "language_n_filers": n_filers,
        "leg6_detail": leg6_out,
        "numeric_composite": numeric_composite,
        "numeric_band": numeric_band,
        "weights": {k: WEIGHTS[k] for k in legs if k in WEIGHTS},
        "text_only": text_only,
        "fingerprint": fingerprint,
    }
    if mapped_fingerprint_only:
        result["fingerprint_only"] = True
        result["basis"] = "annual"
    return result


def compute_bottleneck(write_ledger: bool = True, data_dir=None) -> dict | None:
    """Per-theme physical-tightness read over ALL themes (mapped + unmapped via text-only
    path). DISPLAY-ONLY.

    data_dir: optional override (used by tests; production passes None → config.data_dir()).

    Returns None when no bottleneck data is available at all."""
    # Reset fingerprint module-level caches so each compute_bottleneck call starts fresh
    # (mirrors foresight_score.py's reset_caches pattern; prevents stale test fixtures
    # bleeding into subsequent calls)
    fp.reset_caches()

    # economy-wide shared legs computed once
    leg2 = _z(_series(INV_SALES))
    if leg2 is not None:
        leg2 = -leg2                                     # falling inv/sales = tight = positive leg
    leg3 = _z(_backlog_ratio())
    shared = {"leg2": leg2, "leg3": leg3,
              "delivery_diffusion": _delivery_diffusion(),
              "prices_received": _latest(_series(PRICES_RECV))}

    # Determine asof from the freshest cap-U series (used for shadow log + ledger)
    asof_dates = []
    for sid in {THEME_MAP[k]["cap_u"] for k in THEME_MAP}:
        s = _series(sid)
        if s is not None:
            asof_dates.append(s.index.max())
    asof = str(pd.to_datetime(max(asof_dates)).date()) if asof_dates else None

    themes = (config.load() or {}).get("themes") or {}
    out: dict[str, dict] = {}
    for key, spec in themes.items():
        try:
            r = _theme_bottleneck(
                key, spec.get("name", key), spec.get("tickers") or [], shared,
                asof=asof, data_dir=data_dir,
            )
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("bottleneck[%s] failed: %s", key, e)
            r = None
        if r is not None:
            out[key] = r

    # nothing cached at all -> the collector hasn't run; signal awaiting-data, don't crash
    if not out or all(t["tightness"] is None and t.get("band") in (None, "AWAITING_DATA")
                      and (t.get("language_accel") is None) for t in out.values()):
        if not out:
            return None

    payload = {
        "asof": asof,
        "n_themes": len(out),
        "themes": out,
        "macro_context": {
            "inv_sales_z": (-leg2 if leg2 is not None else None),
            "backlog_z": leg3,
            "delivery_diffusion": shared["delivery_diffusion"],
            "prices_received": shared["prices_received"],
        },
        "note": ("display-only; T1 leading leg of the foresight cascade. All weights "
                 "PROVISIONAL (shadow-calibration pending). W5a: legs 7-8 add per-theme "
                 "XBRL member-level fingerprints (inventory-days + RPO). Watchlist-builder / "
                 "thesis-confirmer, NOT an entry-timer — defer the buy to the dislocation overlay."),
        "fingerprint_coverage": {
            k: (v.get("fingerprint") or {}).get("n_legs_live", 0)
            for k, v in out.items()
            if v.get("fingerprint") is not None
        },
    }

    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("bottleneck ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per (theme, asof) where the band is
    TIGHT/SOLD_OUT or a text-only band. Graded forward against subsequent PPI acceleration
    + basket return."""
    d = config.data_dir() / "bottleneck"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    loggable_bands = {
        "TIGHT", "SOLD_OUT", "TIGHT (text)", "TIGHTENING (text)",
        "TIGHT (fingerprint)", "TIGHTENING (fingerprint)",
    }
    lines = []
    for key, t in payload["themes"].items():
        if t["band"] not in loggable_bands or (key, asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": key, "asof": asof, "ts": ts, "band": t["band"],
            "tightness": t["tightness"], "regime": t["regime"], "legs": t["legs"],
            "text_only": t.get("text_only", False),
            "fingerprint_only": t.get("fingerprint_only", False),
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
