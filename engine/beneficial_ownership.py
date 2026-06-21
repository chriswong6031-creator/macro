"""Beneficial-ownership regime (Schedule 13D/13G) — a per-ticker CONTEXT read built
on the events the special-situations desk already ingests, with the custodian/index
AGGREGATION GUARD the JPM/SBSW case study demands.

The literature (Brav-Jiang-Partnoy-Thomas 2008) is blunt: an **activist 13D** carries
a real, non-reversing stake signal (~+6-8%), while a **passive 13G** — and especially
a 13G from a custodian/index complex (Vanguard/BlackRock/State Street/JPMorgan…) that
certifies "ordinary course of business, no control intent" — is mostly client/index/
custody aggregation, NOT conviction. The 13G→13D *flip* is the highest-signal
escalation. So we grade:
  * activist 13D (non-custodian filer)        -> HIGH signal
  * 13G→13D flip                              -> HIGH signal
  * passive 13G (unknown / non-giant filer)   -> LOW signal
  * 13G from a custodian/index giant          -> NOISE (explicitly flagged)

Filer identity comes from a lightweight SGML-header enrichment
(collectors/beneficial_ownership.py); the engine degrades gracefully to a
form-type-only read (13D vs 13G + flip) when that enrichment is absent.
DISPLAY-ONLY CONTEXT — never a scored alpha (the case study: "very few events,
not statistically validated").
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_13D = {"SC 13D", "SC 13D/A"}
_13G = {"SC 13G", "SC 13G/A"}

# Custodian / index / broker-dealer complexes whose 13G is aggregation, not
# conviction (matched as a substring on the normalized filer name).
_PASSIVE_GIANTS = (
    "VANGUARD", "BLACKROCK", "STATE STREET", "SSGA", "JPMORGAN", "JP MORGAN",
    "MORGAN STANLEY", "GOLDMAN SACHS", "BANK OF AMERICA", "WELLINGTON",
    "FMR LLC", "FIDELITY", "GEODE", "NORTHERN TRUST", "CHARLES SCHWAB",
    "BNY MELLON", "BANK OF NEW YORK", "UBS", "DEUTSCHE BANK", "CITIGROUP",
    "CITADEL", "CAPITAL RESEARCH", "CAPITAL GROUP", "T. ROWE PRICE",
    "T ROWE PRICE", "INVESCO", "DIMENSIONAL", "NORGES", "AMERIPRISE",
    "ALLIANCEBERNSTEIN", "FRANKLIN RESOURCES", "NUVEEN", "TIAA",
)


def classify_filer_type(name: str | None) -> str:
    """'passive_giant' for custodian/index/broker complexes (13G = aggregation),
    else 'other' (could be an activist or a concentrated fund). PURE."""
    if not name:
        return "unknown"
    n = str(name).upper()
    return "passive_giant" if any(g in n for g in _PASSIVE_GIANTS) else "other"


def _is_13d(form: str) -> bool:
    return str(form).strip().upper() in _13D


def _is_13g(form: str) -> bool:
    return str(form).strip().upper() in _13G


def regime_for(rows: pd.DataFrame) -> dict | None:
    """One ticker's beneficial-ownership regime from its 13D/13G event rows
    (columns: form_type, date_filed, optional filer / filer_type). PURE.

    state ∈ {activist, flip, passive, custodial, none}; `signal` grades it
    high/low/noise per the activist-vs-aggregation doctrine."""
    if rows is None or rows.empty:
        return None
    df = rows.copy()
    df["_d"] = pd.to_datetime(df["date_filed"], errors="coerce")
    df = df.dropna(subset=["_d"]).sort_values("_d")
    is_d = df["form_type"].map(_is_13d)
    is_g = df["form_type"].map(_is_13g)
    if not (is_d.any() or is_g.any()):
        return None
    ftype = (df["filer_type"] if "filer_type" in df.columns
             else df.get("filer", pd.Series([None] * len(df))).map(classify_filer_type))
    df = df.assign(_isd=is_d.values, _isg=is_g.values, _ftype=list(ftype))

    # 13G→13D flip: a passive 13G strictly before an activist 13D by the SAME filer
    # (subject-level when the filer is unknown) — the highest-signal escalation.
    flip = False
    if is_d.any() and is_g.any():
        d_df, g_df = df[df["_isd"]], df[df["_isg"]]
        if "filer" in df.columns and d_df["filer"].notna().any():
            for f in set(d_df["filer"].dropna()):
                gd = g_df[g_df["filer"] == f]["_d"]
                dd = d_df[d_df["filer"] == f]["_d"]
                if len(gd) and len(dd) and gd.min() < dd.max():
                    flip = True
                    break
        elif len(g_df) and len(d_df) and g_df["_d"].min() < d_df["_d"].max():
            flip = True                       # filer unknown -> subject-level sequence

    last = df.iloc[-1]
    n_13d = int(is_d.sum())
    n_13g = int(is_g.sum())
    # is there an activist (non-custodian) 13D?
    activist_13d = df[(df["_isd"]) & (df["_ftype"] != "passive_giant")]
    custodial_only = (n_13d == 0 and n_13g > 0 and
                      (df[df["_isg"]]["_ftype"] == "passive_giant").all())

    if not activist_13d.empty:
        state, signal = ("flip", "high") if flip else ("activist", "high")
    elif flip:
        state, signal = "flip", "high"
    elif custodial_only:
        state, signal = "custodial", "noise"
    elif n_13g > 0:
        state, signal = "passive", "low"
    else:                                     # only custodian 13D (rare) — treat as low
        state, signal = "passive", "low"

    return {
        "state": state,
        "signal": signal,
        "n_13d": n_13d,
        "n_13g": n_13g,
        "is_flip": bool(flip),
        "latest_form": str(last["form_type"]),
        "latest_date": str(last["_d"].date()),
        "latest_filer": (str(last.get("filer")) if last.get("filer") is not None
                         and str(last.get("filer")) != "nan" else None),
        "latest_filer_type": str(last["_ftype"]),
    }


def regime_map(events: pd.DataFrame) -> dict[str, dict]:
    """{ticker: regime_for(...)} over a 13D/13G event frame (must carry a `ticker`
    column). Empty dict on no input. PURE."""
    if events is None or events.empty or "ticker" not in events.columns:
        return {}
    ev = events[events["form_type"].map(lambda f: _is_13d(f) or _is_13g(f))]
    ev = ev[ev["ticker"].notna()]
    out: dict[str, dict] = {}
    for tk, rows in ev.groupby("ticker"):
        r = regime_for(rows)
        if r is not None:
            out[str(tk)] = r
    return out


# --------------------------------------------------------------------------- #
# Disk read: join the special-sits 13D/G events with the filer enrichment cache.
# --------------------------------------------------------------------------- #
def _load_events_with_tickers() -> pd.DataFrame | None:
    p = config.data_dir() / "special_situations" / "events.parquet"
    if not p.exists():
        return None
    try:
        ev = pd.read_parquet(p, columns=["form_type", "cik", "date_filed", "accession"])
    except Exception:  # noqa: BLE001
        return None
    ev = ev[ev["form_type"].map(lambda f: _is_13d(f) or _is_13g(f))].copy()
    if ev.empty:
        return None
    try:
        from engine.special_situations import _universe_caps
        cik_ticker, _ = _universe_caps()
    except Exception:  # noqa: BLE001
        cik_ticker = {}
    ev["ticker"] = ev["cik"].apply(
        lambda c: cik_ticker.get(int(c)) if str(c).isdigit() else None)
    return ev


def _load_enrichment() -> pd.DataFrame | None:
    p = config.data_dir() / "beneficial_ownership" / "filings.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        return df if not df.empty else None
    except Exception:  # noqa: BLE001
        return None


def load_regime() -> dict[str, dict]:
    """Per-ticker beneficial-ownership regime from disk. PRIMARY source is the
    dedicated 13D/G sweep (collectors/beneficial_ownership.py — ticker + filer +
    filer_type in one); falls back to the special-situations 13D/G events (joined
    to the enrichment cache for filer) if the sweep cache isn't built yet."""
    enr = _load_enrichment()
    if enr is not None and "ticker" in enr.columns:
        ev = enr[enr["ticker"].notna()]
        if not ev.empty:
            return regime_map(ev)
    ev = _load_events_with_tickers()
    if ev is None or ev.empty:
        return {}
    if enr is not None and "accession" in enr.columns:
        keep = [c for c in ("accession", "filer", "filer_type") if c in enr.columns]
        ev = ev.merge(enr[keep].drop_duplicates("accession"), on="accession", how="left")
    return regime_map(ev)
