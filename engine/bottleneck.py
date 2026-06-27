"""Physical bottleneck nowcast — T1 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md).

THE IDEA. The June-2024 13D HBM call was a SUPPLY-constraint call with zero revision
numbers: "HBM chips are sold out for the next two years… manufacturers are investing to
increase capacity," supply ~100% concentrated, the market focused elsewhere. That is the
genuinely LEADING signal — it precedes the estimate revisions by quarters. This engine
generalizes it: per theme/industry, is the supply side physically full?

Five physical legs, each a free FRED series (config fred.series.bottleneck), z-scored vs
its own history so "high vs normal" is explicit:
  leg1 capacity full   : cap-U high (z of CAPUTLG{naics}S)
  leg2 inventory drained: inventories/sales falling (-z of MNFCTRIRSA)
  leg3 backlog building : unfilled-orders/shipments rising (z of AMTMUO/AMTMVS) + delivery-time diffusion
  leg4 pricing power    : industry PPI YoY accelerating (z of PPI yoy) + prices-received diffusion
  leg6 language         : EDGAR "sold out / capacity constrained / on allocation" mention ACCEL for the theme's filers
The HBM template fires when legs 1-4 fire TOGETHER (demand outrunning supply). Concentration
(leg6 names) confirms durability; the underpricing/entry edge is deferred to the dislocation
overlay — this engine is a WATCHLIST-BUILDER / THESIS-CONFIRMER, NOT an entry-timer (13D was
right and ~9 months early). DISPLAY-ONLY; returns None/partial cleanly until collectors run.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

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

WEIGHTS = {"leg1_capacity": 0.28, "leg2_inventory": 0.22, "leg3_backlog": 0.25,
           "leg4_pricing": 0.25}


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


def _band(composite: float | None, n_legs: int, regime: bool) -> str:
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


def _language_accel(tickers: list[str]) -> tuple[float | None, int]:
    """EDGAR bottleneck-phrase mention acceleration for the theme's filers (last 120d vs
    prior 120d). Returns (accel_ratio, recent_hits). None if the collector hasn't run."""
    p = config.data_dir() / "edgar" / "bottleneck_hits.parquet"
    if not p.exists():
        return None, 0
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None, 0
    if df.empty or "ticker" not in df.columns or "file_date" not in df.columns:
        return None, 0
    df = df[df["ticker"].isin(tickers)].copy()
    if df.empty:
        return 0.0, 0
    df["file_date"] = pd.to_datetime(df["file_date"])
    end = df["file_date"].max()
    recent = df[df["file_date"] > end - pd.Timedelta(days=120)]
    prior = df[(df["file_date"] <= end - pd.Timedelta(days=120)) &
               (df["file_date"] > end - pd.Timedelta(days=240))]
    nr, npq = len(recent), len(prior)
    accel = round((nr - npq) / max(npq, 1), 2)
    return accel, nr


def _theme_bottleneck(theme_key: str, name: str, tickers: list[str], shared: dict) -> dict | None:
    spec = THEME_MAP.get(theme_key)
    if spec is None:
        return None
    cap_u = _series(spec["cap_u"])
    leg1 = _z(cap_u)                                     # capacity full
    leg2 = shared["leg2"]                                # inventory drained (economy-wide)
    leg3 = shared["leg3"]                                # backlog building (economy-wide)
    ppi = _series(spec["ppi"]) if spec.get("ppi") else None
    leg4 = _z(_yoy(ppi))                                 # pricing power (industry PPI yoy)
    lang_accel, lang_hits = _language_accel(tickers)

    legs = {"leg1_capacity": leg1, "leg2_inventory": leg2,
            "leg3_backlog": leg3, "leg4_pricing": leg4}
    avail = {k: v for k, v in legs.items() if v is not None}
    if not avail:
        composite, n = None, 0
        regime = False
    else:
        # re-normalize weights over available legs
        wsum = sum(WEIGHTS[k] for k in avail)
        composite = round(sum(WEIGHTS[k] * v for k, v in avail.items()) / wsum, 2)
        n = len(avail)
        regime = all((legs[k] or 0) > 0 for k in legs) and None not in legs.values()

    return {
        "name": name,
        "naics": spec["naics"],
        "band": _band(composite, n, regime),
        "tightness": composite,
        "regime": regime,
        "n_legs": n,
        "legs": legs,
        "cap_u_latest": _latest(cap_u),
        "ppi_yoy_latest": _latest(_yoy(ppi)),
        "language_accel": lang_accel,
        "language_hits": lang_hits,
        "weights": {k: WEIGHTS[k] for k in legs},
    }


def compute_bottleneck(write_ledger: bool = True) -> dict | None:
    """Per-theme physical-tightness read over the mapped themes. DISPLAY-ONLY.

    Returns None when no bottleneck FRED series are cached yet (collector hasn't run)."""
    # economy-wide shared legs computed once
    leg2 = _z(_series(INV_SALES))
    if leg2 is not None:
        leg2 = -leg2                                     # falling inv/sales = tight = positive leg
    leg3 = _z(_backlog_ratio())
    shared = {"leg2": leg2, "leg3": leg3,
              "delivery_diffusion": _delivery_diffusion(),
              "prices_received": _latest(_series(PRICES_RECV))}

    themes = (config.load() or {}).get("themes") or {}
    out: dict[str, dict] = {}
    for key, spec in themes.items():
        if key not in THEME_MAP:
            continue
        try:
            r = _theme_bottleneck(key, spec.get("name", key), spec.get("tickers") or [], shared)
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("bottleneck[%s] failed: %s", key, e)
            r = None
        if r is not None:
            out[key] = r

    # nothing cached at all -> the collector hasn't run; signal awaiting-data, don't crash
    if not out or all(t["tightness"] is None for t in out.values()):
        if not out:
            return None
    payload = {
        "asof": None,
        "n_themes": len(out),
        "themes": out,
        "macro_context": {
            "inv_sales_z": (-leg2 if leg2 is not None else None),
            "backlog_z": leg3,
            "delivery_diffusion": shared["delivery_diffusion"],
            "prices_received": shared["prices_received"],
        },
        "note": ("display-only; T1 leading leg of the foresight cascade. Watchlist-builder / "
                 "thesis-confirmer, NOT an entry-timer — defer the buy to the dislocation overlay."),
    }
    # stamp asof from the freshest cap-U series we touched
    dates = []
    for sid in {THEME_MAP[k]["cap_u"] for k in out}:
        s = _series(sid)
        if s is not None:
            dates.append(s.index.max())
    if dates:
        payload["asof"] = str(pd.to_datetime(max(dates)).date())

    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("bottleneck ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per (theme, asof) where the band is
    TIGHT/SOLD_OUT. Graded forward against subsequent PPI acceleration + basket return."""
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
    lines = []
    for key, t in payload["themes"].items():
        if t["band"] not in ("TIGHT", "SOLD_OUT") or (key, asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": key, "asof": asof, "ts": ts, "band": t["band"],
            "tightness": t["tightness"], "regime": t["regime"], "legs": t["legs"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
