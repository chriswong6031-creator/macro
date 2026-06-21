"""Event-study validation for the activist-ownership (Schedule 13D) leg.

The research blueprint (research/INTELLIGENCE_HUB_V2_RESEARCH.md §4.1) is blunt:
13D is "the largest event AR in the set" BUT the Feb-2024 SEC rule shrank the
filing window 10→5 days, so every pre-2024 abnormal-return estimate is from a
different regime and overstates capturable drift. **Re-event-study post-2024.**

This script does exactly that, honestly:
  1. Backfill SCHEDULE 13D/13G filings from the EDGAR quarterly full-index
     (2024Q1 → current), CIK→ticker via the SEC master. Streamed + cached.
  2. Fetch daily closes for the target panel + SPY (yfinance — the local price
     parquets cover NONE of these small/mid-cap activist targets).
  3. Measure POST-FILING SPY-relative abnormal returns (entry = first close
     strictly after the filing date, so it's leak-free) at 5/10/21/63 trading
     days, for activist 13D INITIATIONS vs a passive-13G control.
  4. Month-clustered t-stat (13D events cluster in calendar time → returns are
     cross-correlated; a naive across-event t over-states significance).
  5. Emit a GATE: scored only if 13D drift is right-signed, significant, n≥floor,
     AND exceeds the 13G control. Else display-only / "measuring".

Outputs: data/beneficial_ownership/validation_gate.json
         reports/activist-ownership-validation.md
Idempotent: per-quarter parses + the price panel are cached under
data/beneficial_ownership/_backfill/.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.beneficial_ownership import _cik_ticker  # noqa: E402
from engine import validation as V  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("validate_activist")

_UA = "Macro Dashboard research longr2512@gmail.com"
_FULLIDX = "https://www.sec.gov/Archives/edgar/full-index/{yr}/QTR{q}/form.idx"
# the amended-13D regime (5-day window) became effective 2024-02-05; study post that.
_RULE_DATE = pd.Timestamp("2024-02-05")
_HORIZONS = [5, 10, 21, 63]
_MIN_EVENTS = 40           # power floor for a "proven" verdict
_T_BAR = 2.0               # |HAC-t| bar


def _bdir() -> Path:
    p = config.data_dir() / "beneficial_ownership" / "_backfill"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _quarters(start_yr=2024, start_q=1) -> list[tuple[int, int]]:
    today = datetime.now(timezone.utc).date()
    out = []
    yr, q = start_yr, start_q
    while (yr, q) <= (today.year, (today.month - 1) // 3 + 1):
        out.append((yr, q))
        q += 1
        if q > 4:
            q, yr = 1, yr + 1
    return out


# EDGAR transitioned the full-index form-type label mid-2024: early quarters use
# the short "SC 13D"; late-2024+ spell out "SCHEDULE 13D". Match BOTH, normalize
# to the canonical short form the engine reads.
_FORM_CANON = {
    "SC 13D": "SC 13D", "SC 13D/A": "SC 13D/A", "SC 13G": "SC 13G", "SC 13G/A": "SC 13G/A",
    "SCHEDULE 13D": "SC 13D", "SCHEDULE 13D/A": "SC 13D/A",
    "SCHEDULE 13G": "SC 13G", "SCHEDULE 13G/A": "SC 13G/A",
}


def _fetch_index(url: str) -> str | None:
    """Full GET with retries + a sanity check that the body is a real form.idx
    (rapid 50MB hits get throttled to a tiny HTML page → must not be cached)."""
    import time
    import requests
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=180)
            if r.status_code == 200 and len(r.text) > 1_000_000 and "Form Type" in r.text[:600]:
                return r.text
            log.warning("index …%s bad response (HTTP %d, %d bytes) — retry %d",
                        url[-22:], r.status_code, len(r.text), attempt + 1)
        except Exception as e:  # noqa: BLE001
            log.warning("index …%s fetch error: %s — retry %d", url[-22:], e, attempt + 1)
        time.sleep(3.0 * (attempt + 1))
    return None


def backfill_filings() -> pd.DataFrame:
    """SC/SCHEDULE 13D/13G rows across quarters, CIK→ticker resolved, cached per
    quarter (only on success, so a throttled quarter re-fetches next run)."""
    import re
    import time
    cik_tk = _cik_ticker()
    frames = []
    for yr, q in _quarters():
        cache = _bdir() / f"{yr}Q{q}.parquet"
        if cache.exists():
            frames.append(pd.read_parquet(cache))
            continue
        text = _fetch_index(_FULLIDX.format(yr=yr, q=q))
        if text is None:
            log.warning("full-index %dQ%d unavailable — skipping (no cache)", yr, q)
            continue
        rows = []
        for raw in text.splitlines():
            if "13D" not in raw and "13G" not in raw:
                continue
            parts = re.split(r"\s{2,}", raw.strip())
            if len(parts) < 5:
                continue
            form = _FORM_CANON.get(parts[0].strip())
            if form is None:
                continue
            d = parts[-2].strip()
            # quarterly index dates are dashed (YYYY-MM-DD); daily is YYYYMMDD.
            date_filed = d if "-" in d else f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            cik = parts[-3].strip()
            rows.append({
                "accession": Path(parts[-1].strip()).stem,
                "form_type": form,
                "company": " ".join(parts[1:-3]).strip(),
                "cik": cik,
                "date_filed": date_filed,
                "ticker": cik_tk.get(int(cik)) if cik.isdigit() else None,
            })
        df = pd.DataFrame(rows)
        if df.empty:
            log.warning("full-index %dQ%d parsed 0 rows — skipping (no cache)", yr, q)
            continue
        df.to_parquet(cache)
        log.info("backfilled %dQ%d: %d 13D/G rows (%d ticker-resolved)",
                 yr, q, len(df), int(df["ticker"].notna().sum()))
        frames.append(df)
        time.sleep(1.5)                       # be polite between 50MB pulls
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not out.empty:
        out = out.drop_duplicates("accession")
        out["d"] = pd.to_datetime(out["date_filed"], errors="coerce")
        out = out.dropna(subset=["d", "ticker"])
        out = out[out["d"] >= _RULE_DATE]
    return out


def _initiations(df: pd.DataFrame, form: str) -> pd.DataFrame:
    """First filing of `form` per ticker (the initiation event)."""
    sub = df[df["form_type"] == form].sort_values("d")
    return sub.groupby("ticker", as_index=False).first()


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    """Daily closes for the panel + SPY, cached. Batched yfinance."""
    cache = _bdir() / "prices.parquet"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    need = sorted(set(tickers + ["SPY"]) - set(have.columns))
    if not need:
        return have
    import yfinance as yf
    got = {}
    B = 150
    for i in range(0, len(need), B):
        chunk = need[i:i + B]
        try:
            raw = yf.download(chunk, start="2024-01-01", interval="1d",
                              progress=False, threads=False, auto_adjust=True)
        except Exception as e:  # noqa: BLE001
            log.warning("yf batch %d failed: %s", i, e)
            continue
        if raw is None or raw.empty:
            continue
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) and "Close" in raw.columns.get_level_values(0) else raw
        if isinstance(close, pd.Series):
            close = close.to_frame(chunk[0])
        for c in close.columns:
            s = close[c].dropna()
            if len(s) > 20:
                got[c] = s
        log.info("fetched prices batch %d/%d (+%d cols)", i // B + 1,
                 (len(need) + B - 1) // B, len(close.columns))
    if got:
        new = pd.DataFrame(got)
        have = new if have.empty else have.join(new, how="outer")
        have.to_parquet(cache)
    return have


def _fwd_abn(prices: pd.DataFrame, ticker: str, d: pd.Timestamp, h: int) -> float | None:
    """SPY-relative forward return over h trading days, entry = first close
    STRICTLY AFTER the filing date (leak-free)."""
    if ticker not in prices.columns or "SPY" not in prices.columns:
        return None
    s = prices[ticker].dropna()
    spy = prices["SPY"].dropna()
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
        sp = spy.asof(e1) / spy.asof(e0) - 1.0
    except Exception:  # noqa: BLE001
        return None
    if not np.isfinite(r) or not np.isfinite(sp):
        return None
    return float(r - sp)


def _study(events: pd.DataFrame, prices: pd.DataFrame, label: str) -> dict:
    """Per-horizon month-clustered mean abnormal return + HAC-t."""
    out = {}
    for h in _HORIZONS:
        recs = []
        for ev in events.itertuples(index=False):
            a = _fwd_abn(prices, ev.ticker, ev.d, h)
            if a is not None:
                recs.append((ev.d, a))
        if len(recs) < 10:
            out[h] = {"n": len(recs)}
            continue
        edf = pd.DataFrame(recs, columns=["d", "abn"])
        edf["mo"] = edf["d"].dt.to_period("M").astype(str)
        # month-clustered series (each month = one obs) defeats event-time correlation
        monthly = edf.groupby("mo")["abn"].mean()
        nw = V.newey_west_tstat(monthly.values, lags=min(4, max(1, len(monthly) // 4)))
        out[h] = {
            "n": int(len(edf)),
            "n_months": int(len(monthly)),
            "mean_abn": round(float(edf["abn"].mean()), 4),
            "median_abn": round(float(edf["abn"].median()), 4),
            "hit_rate": round(float((edf["abn"] > 0).mean()), 3),
            "monthly_mean": round(float(nw.get("mean", float("nan"))), 4),
            "hac_t": round(float(nw.get("t", float("nan"))), 2),
            "p": round(float(nw.get("p", float("nan"))), 4),
        }
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("backfilling 13D/13G filings (post-2024 regime)…")
    df = backfill_filings()
    if df.empty:
        log.error("no filings backfilled — aborting")
        return
    d13 = _initiations(df, "SC 13D")
    g13 = _initiations(df, "SC 13G")
    log.info("initiations: %d activist-13D · %d passive-13G (post %s)",
             len(d13), len(g13), _RULE_DATE.date())

    # fetch prices for the union of targets (+SPY). cap the 13G control for cost.
    g13_ctrl = g13.sample(min(len(g13), 600), random_state=7) if len(g13) > 600 else g13
    panel = sorted(set(d13["ticker"]) | set(g13_ctrl["ticker"]))
    log.info("fetching prices for %d distinct targets…", len(panel))
    prices = fetch_prices(panel)
    log.info("price panel: %d columns, %d rows", prices.shape[1], prices.shape[0])

    act = _study(d13, prices, "activist_13d")
    pas = _study(g13_ctrl, prices, "passive_13g")

    # verdict: best horizon for 13D where right-signed + significant + n≥floor + beats control
    best_h, scored = None, False
    for h in _HORIZONS:
        a = act.get(h, {})
        p = pas.get(h, {})
        # "beats control" only counts when the control is itself measurable — else a sparse
        # control horizon defaults to mean 0 and the comparison is trivially (and falsely) met.
        beats_control = p.get("n", 0) >= _MIN_EVENTS and a.get("mean_abn", 0) > p.get("mean_abn", 0)
        if (a.get("n", 0) >= _MIN_EVENTS and a.get("mean_abn", 0) > 0
                and abs(a.get("hac_t", 0)) >= _T_BAR and a.get("hac_t", 0) > 0
                and beats_control):
            scored = True
            if best_h is None or abs(a.get("hac_t", 0)) > abs(act[best_h].get("hac_t", 0)):
                best_h = h
    gate = {
        "schema": "activist_ownership.gate.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "rule_date": str(_RULE_DATE.date()),
        "n_activist_13d": int(len(d13)),
        "n_passive_13g_ctrl": int(len(g13_ctrl)),
        "scored": bool(scored),
        "lead_horizon": best_h,
        "weight": 1.0 if scored else 0.0,
        "activist_13d": act,
        "passive_13g": pas,
        "min_events": _MIN_EVENTS,
        "t_bar": _T_BAR,
        "note": ("activist-13D post-filing drift is right-signed, significant and beats "
                 "the passive-13G control → SCORED leading leg"
                 if scored else
                 "post-2024 activist-13D drift NOT robustly significant on the covered "
                 "panel → display-only confirmer ('measuring')"),
    }
    gp = config.data_dir() / "beneficial_ownership" / "validation_gate.json"
    gp.write_text(json.dumps(gate, indent=2))
    log.info("GATE scored=%s lead_horizon=%s -> %s", scored, best_h, gp)

    # human report
    rp = Path(__file__).resolve().parent.parent / "reports"
    rp.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Activist-ownership (Schedule 13D) event study — post-2024 regime", "",
        f"_Generated {gate['generated_at']}. Rule date {gate['rule_date']} "
        f"(Feb-2024 5-day-window regime)._", "",
        f"- Activist 13D initiations: **{len(d13)}** · Passive 13G control: **{len(g13_ctrl)}**",
        f"- Price coverage: {prices.shape[1]-1} of {len(panel)} targets (yfinance)",
        f"- **Verdict: {'SCORED leading leg' if scored else 'display-only confirmer (measuring)'}**"
        + (f" · peak horizon {best_h}d" if best_h else ""), "",
        "## Post-filing SPY-relative abnormal returns", "",
        "_The 13D **median** matters more than the mean: a few takeout/squeeze winners can drag "
        "the mean far positive while the typical name is flat-to-down (watch the 63d row)._", "",
        "| Horizon | 13D n | 13D mean | 13D median | 13D hit | 13D HAC-t | 13G mean | 13G HAC-t |",
        "|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for h in _HORIZONS:
        a, p = act.get(h, {}), pas.get(h, {})
        lines.append(
            f"| {h}d | {a.get('n','—')} | {a.get('mean_abn','—')} | {a.get('median_abn','—')} | "
            f"{a.get('hit_rate','—')} | {a.get('hac_t','—')} | "
            f"{p.get('mean_abn','—')} | {p.get('hac_t','—')} |")
    lines += ["", f"_{gate['note']}._", ""]
    (rp / "activist-ownership-validation.md").write_text("\n".join(lines))
    log.info("report -> %s", rp / "activist-ownership-validation.md")


if __name__ == "__main__":
    main()
