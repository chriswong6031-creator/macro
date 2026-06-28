"""Activist filer track-record (P3.2 — display/context only).

The EDGAR daily index lists a Schedule 13D under the SUBJECT company (the target), so the
target ticker resolves cleanly — but the activist's identity (the reporting person) lives
only in the filing's cover page. This module (a) extracts that reporting person from the
cached 13D text, and (b) builds a per-filer forward-return track-record (filing-date entry
on the target) so the desk can tell a marquee activist's 13D from a no-name filer's.

Honest by construction: a per-filer prior needs a sample. Below `min_filings` priced
campaigns a filer is "descriptive" (shown, never trusted as a number); the whole leaf is
SCORED=False context. Nothing here sizes anything.
"""
from __future__ import annotations

import re

import pandas as pd

ACTIVIST_CATEGORY = "Activist Campaigns"
MIN_FILINGS = 4               # priced campaigns needed before a filer prior is "tracked"
DEFAULT_HORIZON = 60          # trading days forward from the filing date

# the Schedule 13D/G cover page: "1 NAME OF REPORTING PERSON  <name>  2 CHECK ..."
_RP_RE = re.compile(
    r"NAMES?\s+OF\s+REPORTING\s+PERSON[S]?"
    r"(?:\s+I\.?R\.?S\.?\s+IDENTIFICATION\s+NOS?\.?(?:\s+OF\s+ABOVE\s+PERSONS?)?)?"
    r"(?:\s*\(\s*ENTITIES\s+ONLY\s*\))?"
    r"[\s:.-]+(?P<name>[A-Za-z0-9][\w .,&'/\-]{2,70}?)"
    r"\s+(?:2\b|CHECK\b|I\.?R\.?S\.?\b|S\.?S\.?\s+OR\b|\(\s*[ab]\s*\))",
    re.I | re.S)

# noise sometimes captured between the label and the name
_RP_STRIP = re.compile(r"^(?:I\.?R\.?S\.?.*?PERSONS?|\(?\s*entities?\s+only\s*\)?)\s*", re.I)


def extract_reporting_person(text: str | None) -> str | None:
    """Best-effort pull of the reporting person (activist) from a 13D/G cover page.
    Returns a cleaned name, or None if not confidently found."""
    if not text:
        return None
    t = " ".join(str(text).split())
    m = _RP_RE.search(t)
    if not m:
        return None
    name = _RP_STRIP.sub("", m.group("name")).strip()
    name = re.sub(r"^[,\-\s]+|[,\-\s]+$", "", name)        # trim stray punctuation, keep 'L.P.'
    # reject obvious non-names (all digits, too short, leftover labels)
    if len(name) < 3 or name.isdigit() or re.fullmatch(r"[\d.\- ]+", name):
        return None
    return name


def norm_filer(name: object) -> str | None:
    """Normalize a filer name for grouping: collapse whitespace, upper-case, drop a trailing
    legal suffix so 'Elliott Investment Management LP' and '... L.P.' group together."""
    if not name or (isinstance(name, float) and pd.isna(name)):
        return None
    s = re.sub(r"\s+", " ", str(name)).strip().upper().rstrip(" .,")
    s = re.sub(r"\b(L\.?P\.?|LLC|L\.?L\.?C\.?|INC\.?|LTD\.?|LIMITED|CORP\.?|CO\.?|"
               r"PARTNERS?|MANAGEMENT|CAPITAL|ADVISORS?|GROUP|FUND[S]?|HOLDINGS?)\b\.?", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .,&-")
    return s or None


def filer_of(row) -> str | None:
    """The activist's name for a row: the LLM-extracted name wins, else the regex one."""
    for col in ("llm_filer", "filer"):
        v = row.get(col) if hasattr(row, "get") else None
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip():
            return str(v).strip()
    return None


def _fwd(series: pd.Series, when, h: int) -> float | None:
    s = series.dropna()
    if s.empty or not when or (isinstance(when, float) and pd.isna(when)):
        return None
    try:
        d = pd.Timestamp(when)
    except Exception:  # noqa: BLE001
        return None
    pos = int(s.index.searchsorted(d))
    if pos >= len(s) or pos + h >= len(s):
        return None
    p0, p1 = s.iloc[pos], s.iloc[pos + h]
    return float(p1 / p0 - 1.0) if (p0 and p1 and p0 > 0) else None


def filer_track_record(df: pd.DataFrame, closes: pd.DataFrame,
                       horizon: int = DEFAULT_HORIZON, min_filings: int = MIN_FILINGS) -> dict:
    """Per-filer forward-return prior from our own 13D history (filing-date entry on the
    target). Returns {by_filer: {NAME: {n, n_priced, med_fwd_pct, win_pct, status, display}}}.
    Filers below `min_filings` priced campaigns are status='descriptive'. Pure / leak-free
    (entry strictly at the filing date)."""
    out: dict[str, dict] = {}
    if df is None or df.empty:
        return {"by_filer": out, "horizon": horizon, "min_filings": min_filings}
    act = df[(df.get("category") == ACTIVIST_CATEGORY) & (df.get("status") == "ok")] \
        if "category" in df.columns else df.iloc[0:0]
    have_prices = closes is not None and not closes.empty
    agg: dict[str, dict] = {}
    for _, r in act.iterrows():
        name = filer_of(r)
        key = norm_filer(name)
        if not key:
            continue
        a = agg.setdefault(key, {"display": str(name).strip(), "n": 0, "rets": []})
        a["n"] += 1
        tkr = str(r.get("ticker") or "").upper().split(".")[0]
        if have_prices and tkr and tkr in closes.columns:
            fr = _fwd(closes[tkr], r.get("date_filed"), horizon)
            if fr is not None:
                a["rets"].append(fr)
    for key, a in agg.items():
        rets = pd.Series(a["rets"], dtype=float)
        n_priced = int(len(rets))
        out[key] = {
            "display": a["display"], "n": int(a["n"]), "n_priced": n_priced,
            "med_fwd_pct": round(float(rets.median()) * 100, 1) if n_priced else None,
            "win_pct": round(float((rets > 0).mean()) * 100, 0) if n_priced else None,
            "status": "tracked" if n_priced >= min_filings else "descriptive",
        }
    return {"by_filer": out, "horizon": horizon, "min_filings": min_filings}
