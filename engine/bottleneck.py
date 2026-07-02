"""Physical bottleneck nowcast — T1 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md).

THE IDEA. The June-2024 13D HBM call was a SUPPLY-constraint call with zero revision
numbers: "HBM chips are sold out for the next two years… manufacturers are investing to
increase capacity," supply ~100% concentrated, the market focused elsewhere. That is the
genuinely LEADING signal — it precedes the estimate revisions by quarters. This engine
generalizes it: per theme/industry, is the supply side physically full?

Six physical legs, each free:
  leg1 capacity full    : cap-U high (z of CAPUTLG{naics}S)                [FRED]
  leg2 inventory drained: inventories/sales falling (-z of MNFCTRIRSA)     [FRED]
  leg3 backlog building  : unfilled-orders/shipments rising                 [FRED]
  leg4 pricing power     : industry PPI YoY accelerating                   [FRED]
  leg6 language          : EDGAR "sold out / capacity constrained / on
                           allocation" mention ACCEL for the theme's filers [EDGAR FTS]

Weight 0.25 is PROVISIONAL — shadow-calibration pending (§3.2 of the upgrade spec).
The live cutoff and z-threshold are also PROVISIONAL until the PIT backtest (Wave 3a)
produces empirically-earned values. Shadow variants are logged to
data/foresight/shadow_log.jsonl from day one (see _shadow_log_cutoffs).

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

# Numeric legs (legs 1-4): weights rebalanced to 0.75 total to accommodate leg6_language
# at 0.25.  Original ratios: 0.28:0.22:0.25:0.25 → scaled to 0.75 → 0.21:0.165:0.1875:0.1875
# Rounded to sum exactly to 0.75:
WEIGHTS = {
    "leg1_capacity":  0.21,
    "leg2_inventory": 0.165,
    "leg3_backlog":   0.1875,
    "leg4_pricing":   0.1875,
    # PROVISIONAL weight — shadow-calibration pending (Wave 3a).
    # Once the PIT backtest runs and forward grading has ≥30d of text-band flags,
    # the calibration loop (§3.2) will promote/adjust this value. Until then it
    # carries a 'provisional' tag in the output and is NOT used alone to assert conviction.
    "leg6_language":  0.25,    # PROVISIONAL
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


def _band(composite: float | None, n_legs: int, regime: bool,
          lang_accel: float | None = None, n_filers: int = 0,
          text_only: bool = False) -> str:
    """Return a band string.

    text_only=True: only the language leg contributed (no numeric FRED legs). In this
    case the band is capped at 'TIGHT (text)' / 'TIGHTENING (text)' / None.
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
        return "SOLD_OUT"
    if composite > 0.75:
        return "TIGHT"
    if composite > 0.25:
        return "TIGHTENING"
    if composite < -0.25:
        return "LOOSE"
    return "NEUTRAL"


def _shadow_log_cutoffs(theme_key: str, asof: str | None, lang_accel: float | None,
                        n_filers: int) -> None:
    """Log shadow z-cutoff variants for the language leg per §3.2.

    For each cutoff in LANG_Z_SHADOW_CUTOFFS, compute what the text band WOULD be and
    append to data/foresight/shadow_log.jsonl (append-only, deduped by theme+asof+cutoff).
    Non-fatal — the live band is unaffected.
    """
    if lang_accel is None or asof is None:
        return
    try:
        p = config.data_dir() / "foresight" / "shadow_log.jsonl"
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
                      asof: str | None = None) -> dict | None:
    spec = THEME_MAP.get(theme_key)
    lang_accel, lang_hits, n_filers = _language_accel(tickers)
    lang_z = _language_z(lang_accel)

    if spec is None:
        # Unmapped theme: language-only pass — band capped at TIGHT (text) / TIGHTENING (text)
        if lang_accel is None:
            return None   # no data at all for this theme
        text_composite = lang_z
        band = _band(text_composite, 0, False,
                     lang_accel=lang_accel, n_filers=n_filers, text_only=True)
        # Log shadow cutoffs even for unmapped themes
        _shadow_log_cutoffs(theme_key, asof, lang_accel, n_filers)
        leg6_out = {
            "value": lang_z, "accel": lang_accel, "hits": lang_hits,
            "n_filers": n_filers, "provisional": True,
        }
        return {
            "name": name,
            "naics": None,
            "band": band,
            "tightness": None,
            "regime": False,
            "n_legs": 1 if lang_z is not None else 0,
            "legs": {"leg6_language": lang_z},
            "cap_u_latest": None,
            "ppi_yoy_latest": None,
            "language_accel": lang_accel,
            "language_hits": lang_hits,
            "language_n_filers": n_filers,
            "leg6_detail": leg6_out,
            "weights": {"leg6_language": WEIGHTS["leg6_language"]},
            "text_only": True,
        }

    cap_u = _series(spec["cap_u"])
    leg1 = _z(cap_u)                                     # capacity full
    leg2 = shared["leg2"]                                # inventory drained (economy-wide)
    leg3 = shared["leg3"]                                # backlog building (economy-wide)
    ppi = _series(spec["ppi"]) if spec.get("ppi") else None
    leg4 = _z(_yoy(ppi))                                 # pricing power (industry PPI yoy)

    legs = {
        "leg1_capacity":  leg1,
        "leg2_inventory": leg2,
        "leg3_backlog":   leg3,
        "leg4_pricing":   leg4,
        "leg6_language":  lang_z,
    }
    avail = {k: v for k, v in legs.items() if v is not None}
    numeric_avail = {k: v for k, v in avail.items() if k != "leg6_language"}

    if not avail:
        composite, n = None, 0
        regime = False
    else:
        # Re-normalize weights over available legs
        wsum = sum(WEIGHTS[k] for k in avail)
        composite = round(sum(WEIGHTS[k] * v for k, v in avail.items()) / wsum, 2)
        n = len(avail)
        # regime requires ALL four numeric legs positive and non-null
        numeric_legs = {k: legs[k] for k in ("leg1_capacity", "leg2_inventory",
                                              "leg3_backlog", "leg4_pricing")}
        regime = all((numeric_legs[k] or 0) > 0 for k in numeric_legs) \
            and None not in numeric_legs.values()

    # Determine if we have only the language leg (no numeric FRED legs at all)
    text_only = not numeric_avail and lang_z is not None

    band = _band(composite, n, regime,
                 lang_accel=lang_accel, n_filers=n_filers, text_only=text_only)

    # Text-band variant: when language alone clears TIGHT but numeric legs do NOT
    if not text_only and numeric_avail and composite is not None:
        # Check whether language alone would push into TIGHT (text) territory
        if (lang_z is not None and lang_z > LANG_Z_LIVE and n_filers >= LANG_MIN_FILERS
                and band not in ("TIGHT", "SOLD_OUT", "TIGHT (text)")):
            # Numeric legs are not yet at TIGHT/SOLD_OUT — language creates a text-only read
            band = "TIGHT (text)"
            text_only = True

    # Shadow log for all themes with a language read
    _shadow_log_cutoffs(theme_key, asof, lang_accel, n_filers)

    leg6_out = {
        "value": lang_z, "accel": lang_accel, "hits": lang_hits,
        "n_filers": n_filers, "provisional": True,
    }

    return {
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
        "weights": {k: WEIGHTS[k] for k in legs},
        "text_only": text_only,
    }


def compute_bottleneck(write_ledger: bool = True) -> dict | None:
    """Per-theme physical-tightness read over ALL themes (mapped + unmapped via text-only
    path). DISPLAY-ONLY.

    Returns None when no bottleneck data is available at all."""
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
                key, spec.get("name", key), spec.get("tickers") or [], shared, asof=asof
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
        "note": ("display-only; T1 leading leg of the foresight cascade. leg6_language "
                 "weight PROVISIONAL (shadow-calibration pending). Watchlist-builder / "
                 "thesis-confirmer, NOT an entry-timer — defer the buy to the dislocation overlay."),
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
    loggable_bands = {"TIGHT", "SOLD_OUT", "TIGHT (text)", "TIGHTENING (text)"}
    lines = []
    for key, t in payload["themes"].items():
        if t["band"] not in loggable_bands or (key, asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": key, "asof": asof, "ts": ts, "band": t["band"],
            "tightness": t["tightness"], "regime": t["regime"], "legs": t["legs"],
            "text_only": t.get("text_only", False),
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
