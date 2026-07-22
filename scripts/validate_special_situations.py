"""Pre-registered event-study gauntlet for the `special_situation` convergence channel.

The `special_situation` alt-data channel (engine/altdata_models.py, CHANNEL_WEIGHTS)
carries a 0.40 AUTHORITY-tier weight — 2x the 0.20 context floor — yet, unlike its
sibling `activist_13d` (gauntleted in #3216 via validate_activist_ownership.py), it had
NO measured edge behind that weight. This script supplies the missing promotion gate,
exactly as validate_activist_ownership.py did for the 13D leg: measure the forward
abnormal return AFTER the event fires and let the number decide the weight.

WHAT the channel actually fires on (engine/altdata.py:special_situations_signal +
_SPECIAL_SIT_ACTIONABLE): a HARD, DATED, NON-activist corporate deal-event on a US name —
Acquisitions, M&A / Divestitures, Tender/Issuer Tenders, Going-Private, Spin-Offs,
Strategic Reviews, Deal Terminations, Restructuring & Busted M&A, Liquidations, Insolvency,
Delistings — at non-low confidence. So the gauntlet measures EXACTLY that set: the desk's
own dated EDGAR detections (engine.special_situations.build_situations, status 'ok'),
first actionable event per US ticker (the initiation), non-activist.

METHOD — a synthesis of the two house templates:
  * From validate_activist_ownership.py: leak-free entry (first close STRICTLY AFTER the
    EDGAR filing date — EDGAR's daily index posts ~22:00 ET so a same-day close is a
    4-6h look-ahead), SPY-relative forward abnormal returns at 5/10/21/63 trading days,
    an n-floor, and a "scored only if right-signed + significant + beats a control" verdict.
  * From engine/signal_governor.py (the intel-hub V3 daily-HAC governor): because the
    special-situations pipeline is only ~6 months old (events.parquet starts 2026-02),
    a MONTHLY-clustered HAC (the activist script's choice for its 2-year 13D panel) would
    have ~6 monthly obs — below the newey_west n>=8 floor, an auto-null by underpower, not
    a fair test. Instead we cluster in CALENDAR TIME by DAY (a daily equal-weight portfolio
    of every event entering that day) and take a Newey-West HAC t with lag = horizon, gated
    by the same `n_days >= max(6, horizon)` validity bar the governor uses so we never act
    on a degenerate (lag >= n_days) long-run variance.

CONTROL (mirrors the activist gate's passive-13G leg): a pre-event PLACEBO — the same
tickers entered one quarter (63 bdays) BEFORE the filing. It measures each name's NORMAL
SPY-relative drift absent the event; the event must beat it. This catches the trap that
many special-situation names (distressed delistings, busted deals) are already drifting —
an "edge" that is just the stock's own trend, not the event, fails here.

VERDICT: scored iff SOME horizon is valid (n_events >= floor AND n_days >= needed),
right-signed (mean_abn > 0 and HAC-t > 0), significant (|HAC-t| >= 2.0), AND beats the
placebo. lead_horizon = the qualifying horizon with the largest |HAC-t|. Per the standing
epistemics law (LLMs may only DE-escalate calibrated keys, never originate escalations):
scored -> KEEP 0.40 (now gauntlet-confirmed, not raised); null/negative -> DE-escalate to
the 0.20 context tier, exactly as activist_13d was in #3216. Any RAISE above 0.40 is an
operator decision, never this script's.

Outputs: data/special_situations/validation_gate.json  (schema special_situation.gate.v1)
         reports/special-situation-validation.md
Offline + idempotent: reads on-disk EDGAR detections + the US close caches only (no network);
85%+ of first-event tickers are already priced by the breadth/bt caches.

Run: python -m scripts.validate_special_situations
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import special_situations as sse          # noqa: E402  the desk's dated detections
from engine import validation as V                     # noqa: E402  newey_west_tstat (HAC)
from engine.altdata import _SPECIAL_SIT_ACTIONABLE     # noqa: E402  the exact channel admission set
from scripts.backtest_special_situations import _us_closes, _spy  # noqa: E402  reuse price panel
from lib import config                                 # noqa: E402

log = logging.getLogger("validate_special_situation")

_HORIZONS = [5, 10, 21, 63]
_MIN_EVENTS = 40            # power floor for a "proven" verdict (matches the activist gate)
_T_BAR = 2.0               # |Newey-West HAC t| bar (matches signal_governor.T_SIG)
_MIN_HAC_DAYS = 6          # floor on distinct entry-days for a valid HAC (signal_governor.MIN_HAC_DAYS)
_PLACEBO_LAG = 63          # pre-event baseline entry: one quarter (bdays) before the filing


def _needed_days(h: int) -> int:
    """Daily calendar-time HAC uses lag = horizon; a HAC t with lag >= n_days is DEGENERATE
    (the long-run variance is unestimable) so require n_days >= max(6, horizon). Mirrors
    engine.signal_governor._needed_days."""
    return max(_MIN_HAC_DAYS, h)


def _us(t) -> str | None:
    """US common-stock ticker (drops foreign dotted codes and placeholders)."""
    t = str(t or "").strip().upper()
    if not t or "." in t or t.lower() == "none":
        return None
    return t.split(".")[0] or None


def event_panel() -> pd.DataFrame:
    """First actionable NON-activist deal-event per US ticker — the exact set the
    `special_situation` channel converges on. Columns: tk, d (filing date), category."""
    df = sse.build_situations()
    if df.empty:
        return pd.DataFrame()
    ok = df[df.status == "ok"].copy() if "status" in df.columns else df.copy()
    ok["tk"] = ok["ticker"].map(_us)
    ok["d"] = pd.to_datetime(ok.get("date_filed"), errors="coerce")
    # the channel drops low-confidence rows (special_situations_signal); mirror that so the
    # gauntlet measures precisely the admitted set. `confidence` is the field the JSON carries.
    conf = ok["confidence"].astype(str).str.lower() if "confidence" in ok.columns else pd.Series("", index=ok.index)
    keep = (
        ok["tk"].notna()
        & ok["d"].notna()
        & ok["category"].isin(_SPECIAL_SIT_ACTIONABLE)   # actionable set already excludes 'Activist Campaigns'
        & (conf != "low")
    )
    sub = ok[keep].sort_values("d")
    first = sub.groupby("tk", as_index=False).first()     # initiation event per ticker
    return first[["tk", "d", "category"]].reset_index(drop=True)


def _fwd_abn(closes: pd.DataFrame, spy: pd.Series, tk: str, d: pd.Timestamp, h: int):
    """SPY-relative forward return over h trading days, entry = first close STRICTLY AFTER
    `d` (leak-free: excludes the filing-day close). Returns (entry_day, abn) or None."""
    if tk not in closes.columns or spy is None:
        return None
    s = closes[tk].dropna()
    after = s.index[s.index > d]
    if len(after) <= h:
        return None
    e0 = after[0]
    loc = s.index.get_loc(e0)
    if loc + h >= len(s):
        return None
    e1 = s.index[loc + h]
    try:
        r = s.loc[e1] / s.loc[e0] - 1.0
        sp0, sp1 = spy.asof(e0), spy.asof(e1)
        sp = sp1 / sp0 - 1.0
    except Exception:  # noqa: BLE001
        return None
    if not np.isfinite(r) or not np.isfinite(sp):
        return None
    return e0, float(r - sp)


def _study(events: pd.DataFrame, closes: pd.DataFrame, spy: pd.Series, shift_bdays: int = 0) -> dict:
    """Per-horizon daily-calendar-time abnormal-return study. shift_bdays > 0 walks the entry
    back that many business days for the pre-event placebo baseline."""
    out: dict = {}
    for h in _HORIZONS:
        recs = []
        for ev in events.itertuples(index=False):
            d = ev.d - pd.tseries.offsets.BDay(shift_bdays) if shift_bdays else ev.d
            a = _fwd_abn(closes, spy, ev.tk, d, h)
            if a is not None:
                recs.append(a)
        if len(recs) < 10:
            out[h] = {"n": len(recs)}
            continue
        edf = pd.DataFrame(recs, columns=["e0", "abn"])
        edf["day"] = edf["e0"].dt.normalize()
        # calendar-time portfolio: each entry-day = one obs (mean abn of names entering that day).
        # This defeats the cross-sectional correlation of names sharing a filing day; the
        # Newey-West lag=h then corrects the serial correlation of overlapping h-day windows.
        daily = edf.groupby("day")["abn"].mean().sort_index()
        nw = V.newey_west_tstat(daily.values, lags=h)
        rec = {
            "n": int(len(edf)),
            "n_days": int(len(daily)),
            "mean_abn": round(float(edf["abn"].mean()), 4),
            "median_abn": round(float(edf["abn"].median()), 4),
            "hit_rate": round(float((edf["abn"] > 0).mean()), 3),
            "valid_hac": bool(len(daily) >= _needed_days(h)),
        }
        # newey_west_tstat returns mean/t/p = None when <8 daily obs — OMIT (don't float(None));
        # consumers .get('hac_t', 0) then fail closed (not scored).
        for k_out, k_nw, nd in (("daily_mean", "mean", 4), ("hac_t", "t", 2), ("p", "p", 4)):
            v = nw.get(k_nw)
            if v is not None:
                rec[k_out] = round(float(v), nd)
        out[h] = rec
    return out


def _verdict(ev: dict, pl: dict) -> tuple[bool, int | None]:
    """scored iff some horizon is valid (n_events>=floor AND n_days>=needed), right-signed
    (mean_abn>0, HAC-t>0), significant (|HAC-t|>=2.0) AND beats the placebo (measured, so a
    sparse placebo can't be trivially 'beaten'). lead = qualifying horizon with largest |t|."""
    best_h, scored = None, False
    for h in _HORIZONS:
        a, p = ev.get(h, {}), pl.get(h, {})
        beats = p.get("n", 0) >= _MIN_EVENTS and a.get("mean_abn", 0) > p.get("mean_abn", 0)
        if (a.get("valid_hac") and a.get("n", 0) >= _MIN_EVENTS
                and a.get("mean_abn", 0) > 0
                and abs(a.get("hac_t", 0)) >= _T_BAR and a.get("hac_t", 0) > 0
                and beats):
            scored = True
            if best_h is None or abs(a.get("hac_t", 0)) > abs(ev[best_h].get("hac_t", 0)):
                best_h = h
    return scored, best_h


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("building the special-situations event panel (dated EDGAR detections)…")
    panel = event_panel()
    if panel.empty:
        log.error("no actionable special-situation events found — aborting")
        return
    closes = _us_closes()
    spy = _spy(closes)
    if closes.empty or spy is None:
        log.error("no US price panel / SPY on disk — cannot run the study")
        return
    priceable = panel[panel["tk"].isin(closes.columns)]
    log.info("panel: %d first-event US tickers (%d priceable) · %s → %s",
             len(panel), len(priceable), panel["d"].min().date(), panel["d"].max().date())

    ev = _study(panel, closes, spy, shift_bdays=0)
    pl = _study(panel, closes, spy, shift_bdays=_PLACEBO_LAG)
    scored, best_h = _verdict(ev, pl)

    gate = {
        "schema": "special_situation.gate.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "channel": "special_situation",
        "event_class": "non-activist actionable US deal-events (first per ticker)",
        "categories": sorted(_SPECIAL_SIT_ACTIONABLE),
        "panel_start": str(panel["d"].min().date()),
        "panel_end": str(panel["d"].max().date()),
        "n_events": int(len(panel)),
        "n_priceable": int(len(priceable)),
        "method": ("daily calendar-time portfolio · SPY-relative · leak-free entry (first close "
                   "strictly after the EDGAR filing date) · Newey-West HAC lag=horizon · "
                   "validity bar n_days>=max(6,horizon)"),
        "scored": bool(scored),
        "lead_horizon": best_h,
        "weight": 1.0 if scored else 0.0,
        "current_channel_weight": 0.40,
        "channel_weight_recommendation": (
            "KEEP 0.40 (gauntlet-confirmed authority; a raise is an operator decision, not this gate)"
            if scored else
            "DE-ESCALATE to 0.20 (context tier) — mirror activist_13d in #3216"),
        "event": ev,
        "placebo_pre_event": pl,
        "min_events": _MIN_EVENTS,
        "t_bar": _T_BAR,
        "note": ("post-filing special-situation drift is right-signed, significant and beats the "
                 "pre-event placebo → SCORED authority channel"
                 if scored else
                 "post-filing special-situation drift is NOT robustly positive/significant vs the "
                 "pre-event placebo on the covered panel → context-tier confirmer ('measuring')"),
    }
    gp = config.data_dir() / "special_situations" / "validation_gate.json"
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps(gate, indent=2))
    log.info("GATE scored=%s lead_horizon=%s -> %s", scored, best_h, gp)

    # human report
    rp = Path(__file__).resolve().parent.parent / "reports"
    rp.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Special-situation (deal-event) convergence channel — event study", "",
        f"_Generated {gate['generated_at']}. Event class: {gate['event_class']}._", "",
        f"- Events: **{len(panel)}** first-per-ticker actionable US deal-events "
        f"({len(priceable)} priceable) · {gate['panel_start']} → {gate['panel_end']}",
        f"- Method: {gate['method']}",
        f"- **Verdict: {'SCORED authority channel' if scored else 'context-tier confirmer (measuring)'}**"
        + (f" · peak horizon {best_h}d" if best_h else ""),
        f"- **Weight ruling: {gate['channel_weight_recommendation']}**", "",
        "## Post-filing SPY-relative abnormal returns (vs pre-event placebo)", "",
        "_Entry is STRICTLY AFTER the filing date, so the announcement pop is already gone — this is "
        "post-filing DRIFT, not the event jump. The placebo enters the same names one quarter earlier "
        "to net out each name's normal drift._", "",
        "| Horizon | n | n_days | mean_abn | median | hit | HAC-t | p | valid | placebo mean | placebo HAC-t |",
        "|--:|--:|--:|--:|--:|--:|--:|--:|:--:|--:|--:|",
    ]
    for h in _HORIZONS:
        a, p = ev.get(h, {}), pl.get(h, {})
        lines.append(
            f"| {h}d | {a.get('n','—')} | {a.get('n_days','—')} | {a.get('mean_abn','—')} | "
            f"{a.get('median_abn','—')} | {a.get('hit_rate','—')} | {a.get('hac_t','—')} | "
            f"{a.get('p','—')} | {'✓' if a.get('valid_hac') else '—'} | "
            f"{p.get('mean_abn','—')} | {p.get('hac_t','—')} |")
    lines += ["", f"_{gate['note']}._", "",
              "_Caveat: the special-situations pipeline is ~6 months old, so even a SCORED reading is "
              "provisional and rests on a daily-HAC (not the activist gate's 2-year monthly cluster). "
              "Re-run as the panel deepens._", ""]
    (rp / "special-situation-validation.md").write_text("\n".join(lines))
    log.info("report -> %s", rp / "special-situation-validation.md")


if __name__ == "__main__":
    main()
