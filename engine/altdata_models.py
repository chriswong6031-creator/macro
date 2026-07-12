"""Alt-data MODELS — the deeper signal layer + the single weighted-convergence kernel.

`engine.altdata` owns the original cross-sectional signals (congress / contracts /
lobbying / insiders / 13F / Trump). This module:

  1. turns the Quiver feeds that were COLLECTED-BUT-UNUSED into real signals —
     app-store demand momentum, patent-grant clusters, pending-bill catalysts,
     congressional position SIZE, corporate-jet proximity, exec-comp alignment,
     retail attention — so the $750/yr suite is used to its full extent, and
  2. defines the ONE weighted-convergence kernel (`channel_records`) that both the
     cross-sectional display (`altdata.convergence`) and the per-ticker substrate
     (`altdata_signals.build`) call, replacing the two slightly-divergent count-only
     implementations with a single weighted one.

A channel's WEIGHT is its prior signal quality (an insider cluster outranks a WSB
mention). `weighted_score` = sum of distinct-channel weights; `count` = #channels.
Pure reads + pandas; no network, no LLM; every reader degrades to empty on a bad/missing
table so the builder never crashes.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_MISSING = {"", "nan", "none", "nat", "null", "<na>"}


# --------------------------------------------------------------------------- coercion
def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _MISSING else s


def _f(v) -> float:
    s = _s(v)
    if s is None:
        return float("nan")
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))


def _read(dataset: str) -> pd.DataFrame | None:
    p = config.data_dir() / "quiver" / f"{dataset}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata_models: cannot read %s: %s", dataset, e)
        return None


# =========================================================================== #
# CHANNEL WEIGHTS — the single source of truth for convergence quality.
# Upgraded variants (…_cluster / …_accel / smart_money_…) outrank their base
# channel and REPLACE it for a ticker, so a strong read scores higher than a weak
# one of the same kind without double-counting.
# =========================================================================== #
CHANNEL_WEIGHTS: dict[str, float] = {
    "insider_cluster":    1.00,   # >=3 open-market insider buyers — the strongest tell
    "gov_contract_accel": 0.90,   # federal $ accelerating >=2x off a real base
    "gov_grant_accel":    0.85,   # federal GRANT $ (CHIPS/DOE/IRA) accelerating off a real base
    "smart_money_13f":    0.85,   # a tracked marquee fund initiated/added
    "fda_approval":       0.80,   # new drug/biologic approval (ORIG/AP) — a hard dated catalyst
    "congress_cluster":   0.80,   # >=3 members net-buying the same name
    "fda_label_expansion": 0.70,  # sNDA EFFICACY supplement — widens the addressable market
    "unusual_options":    0.65,   # options-flow surge (vol/OI spiking off baseline) — positioning
    "insider_buy":        0.60,   # single open-market insider buy
    "insider_mspr":       0.55,   # Finnhub insider sentiment (MSPR) strongly positive — cross-check
    "material_8k":        0.55,   # cluster of material 8-K filings (filing-time corporate activity)
    "activist_13d":       0.55,   # Special-Situations handshake (P3.3): a high-conf 13D activist campaign
    "darkpool_accum":     0.55,   # off-exchange accumulation (z-scored)
    "special_situation":  0.40,   # Special-Situations handshake (P3.3): a high-conf live deal/event on the name
    "lobbying_spike":     0.50,   # lobbying spend spiking off a real base
    "trump":              0.50,   # Donald-Trump trade / branded affiliation
    "affiliation":        0.50,   # influence-graph edge (actor -> this name)
    "gov_grant":          0.50,   # federal grant/loan present (CHIPS/DOE/IRA), not accelerating
    "gov_contract":       0.45,   # federal contracts present (not accelerating)
    "congress_buy":       0.45,   # single member net-buying
    "13f_add":            0.40,   # institutional 13F add (non-marquee)
    "patent_cluster":     0.40,   # patent-grant cluster (innovation cadence)
    "app_demand":         0.40,   # app-store rating + review momentum
    "analyst_upgrade_cluster": 0.35,  # Finnhub: bullish analyst consensus rising (lagging, noisy)
    "clinical_phase3_start": 0.35,  # new Phase-3 trial registration (biotech pipeline advancing)
    "hf_model_momentum":  0.35,   # Hugging Face model-download velocity (AI adoption proxy)
    "github_momentum":    0.30,   # GitHub star velocity (developer-mindshare proxy)
    "earnings_beat":      0.30,   # Finnhub earnings surprise — single beat is weak context
    "lobbying":           0.30,   # lobbying present (no spike)
    "bill_catalyst":      0.30,   # pending legislation tied to the name's sector
    "cnbc_pick":          0.25,   # CNBC desk pick
    "news_sentiment":     0.20,   # Polygon editorial-news bullish lean — abundant but noisy
    "retail_buzz":        0.15,   # WSB / retail attention — context, lowest weight
}

# Marquee 13F filers whose ADDS carry signal (case-insensitive substring on Fund).
# Removed defunct funds to prevent false-trigger on 0.85-weight smart_money_13f channel:
#   melvin — Melvin Capital closed May 2022 (unwound after GameStop short-squeeze losses)
SMART_MONEY = (
    "berkshire", "scion", "pershing square", "bridgewater", "renaissance",
    "citadel", "tiger global", "coatue", "appaloosa", "icahn", "third point",
    "baupost", "lone pine", "viking global", "soros", "greenlight", "duquesne",
    "elliott", "starboard", "trian", "altimeter", "whale rock",
)

_GOV_FLOOR = 5_000_000.0      # absolute $ floor below which "acceleration" is noise
_GRANT_FLOOR = 5_000_000.0    # absolute $ floor for a federal grant/loan to register
_LOBBY_FLOOR = 100_000.0      # absolute $ floor for a lobbying "spike"


# =========================================================================== #
# NEW SIGNALS — the previously-unused Quiver feeds, now real signals
# =========================================================================== #
def app_ratings_momentum(top: int = 15) -> list[dict]:
    """App-store demand proxy: review-weighted rating + total review base per ticker,
    plus review VELOCITY when >=2 snapshots exist. The freshest, highest-volume Quiver
    feed — a near-real-time read on consumer demand for app-driven names."""
    df = _read("appratings")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "app": df.get("App", pd.Series(dtype=object)).map(_s),
        "rating": df.get("Rating", pd.Series(dtype=object)).map(_f),
        "count": df.get("Count", pd.Series(dtype=object)).map(_f),
        "time": df.get("Time", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & (d["count"].fillna(0) > 0) & (d["rating"].fillna(0) > 0)]
    if d.empty:
        return []
    # velocity: total reviews at the latest snapshot minus the prior snapshot
    times = sorted(t for t in d["time"].dropna().unique())
    latest, prior = (times[-1] if times else None), (times[-2] if len(times) >= 2 else None)
    cur = d[d["time"] == latest] if latest else d
    rows = []
    for tk, g in cur.groupby("ticker"):
        reviews = float(g["count"].sum())
        rating = float((g["rating"] * g["count"]).sum() / reviews) if reviews else None
        vel = None
        if prior is not None:
            pr = d[(d["time"] == prior) & (d["ticker"] == tk)]["count"].sum()
            # Relative velocity (delta / prior_count) avoids mega-platform bias.
            # Floor of 1000 prior reviews prevents tiny-denominator blowups.
            if pr >= 1000:
                vel = round(float((reviews - pr) / pr), 4)
        top_app = g.sort_values("count", ascending=False).iloc[0]["app"]
        rows.append({
            "ticker": tk, "rating": round(rating, 2) if rating is not None else None,
            "reviews": int(reviews), "apps": int(len(g)), "top_app": top_app,
            "review_velocity": vel,
            "lean": ("strong" if rating and rating >= 4.3 and reviews >= 1000
                     else "soft" if rating and rating < 3.5 else "neutral"),
        })
    rows.sort(key=lambda r: (r["rating"] or 0) * (r["reviews"] ** 0.5), reverse=True)
    return rows[:top]


def patent_velocity(window_days: int = 120, top: int = 15) -> list[dict]:
    """Patent-grant cadence per ticker: a cluster of recent grants = an innovation/IP
    push the price often hasn't discounted. Counts grants in-window + IPC-class breadth."""
    df = _read("patents")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "ipc": df.get("IPC", pd.Series(dtype=object)).map(_s),
        "title": df.get("Title", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna()]
    if d.empty:
        return []
    if d["date"].notna().any():
        d = d[d["date"] >= _now() - pd.Timedelta(days=window_days)]
    rows = []
    for tk, g in d.groupby("ticker"):
        ipc_classes = {(c or "")[:4] for c in g["ipc"].dropna()}
        rows.append({
            "ticker": tk, "patents": int(len(g)),
            "ipc_classes": int(len([c for c in ipc_classes if c])),
            "sample_title": (g["title"].dropna().iloc[0] if g["title"].notna().any() else None),
        })
    rows.sort(key=lambda r: (r["patents"], r["ipc_classes"]), reverse=True)
    return rows[:top]


# bill summary -> sector keyword map (deterministic; the Haiku tagger refines in the brain)
_BILL_SECTORS: list[tuple[str, tuple[str, ...]]] = [
    ("Defense", ("defense", "national security", "armed forces", "military", "missile", "weapon")),
    ("Semiconductors", ("semiconductor", "chips act", "chip ", "fabrication", "foundry")),
    ("Energy", ("energy", "oil", "natural gas", "pipeline", "nuclear", "renewable", "solar", "drilling")),
    ("Healthcare", ("medicare", "medicaid", "health care", "healthcare", "drug pricing", "pharmaceutical", "fda")),
    ("Financials", ("banking", "financial services", "securities", "credit", "insurance", "basel")),
    ("Crypto", ("digital asset", "cryptocurrency", "stablecoin", "bitcoin", "blockchain")),
    ("Technology / AI", ("artificial intelligence", " ai ", "data center", "broadband", "spectrum", "privacy")),
    ("Aerospace", ("aviation", "aerospace", "faa", "space", "satellite")),
    ("Homeland / Immigration", ("homeland security", "immigration", "border", "customs")),
    ("Infrastructure", ("infrastructure", "highway", "transportation", "transit", "water system")),
    ("Trade", ("tariff", "trade", "export", "import", "sanction")),
]


def bill_catalysts(top: int = 18) -> list[dict]:
    """Pending-legislation catalysts mapped to a SECTOR (the brain maps sector->names).
    Most-recently-acted first. The qualitative policy channel the structured feeds miss."""
    df = _read("bills")
    if df is None or df.empty:
        return []
    df = df.assign(_d=_dt(df.get("lastActionDate"))).sort_values("_d", ascending=False, na_position="last")
    out = []
    for _, r in df.head(60).iterrows():
        title = _s(r.get("title")) or ""
        summary = re.sub(r"<[^>]+>", " ", str(r.get("summary") or "")).strip()
        blob = (title + " " + summary).lower()
        sector = next((name for name, kws in _BILL_SECTORS if any(k in blob for k in kws)), None)
        if not sector:
            continue
        out.append({
            "title": title[:140], "sector": sector,
            "chamber": _s(r.get("currentChamber")),
            "bill": f"{_s(r.get('billType')) or ''}{_s(r.get('number')) or ''}".strip(),
            "last_action": _s(r.get("lastAction")),
            "last_action_date": _s(r.get("lastActionDate")),
            "url": _s(r.get("url")),
            "summary": summary[:300],
        })
        if len(out) >= top:
            break
    return out


def congress_holdings(top: int = 200) -> dict[str, dict]:
    """Aggregate congressional POSITION SIZE per ticker (parses the Holdings JSON blob).
    Returns {ticker: {position_usd, holders}} — SIZE context that complements the trade
    FLOW from political_netflow (a $40k sale matters more against a $5M position)."""
    df = _read("congressholdings")
    if df is None or df.empty:
        return {}
    agg: dict[str, dict] = {}
    for _, r in df.iterrows():
        raw = _s(r.get("Holdings"))
        if not raw:
            continue
        try:
            holdings = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(holdings, dict):
            continue
        for tk, val in holdings.items():
            tk = _s(tk)
            v = _f(val)
            if not tk or pd.isna(v):
                continue
            slot = agg.setdefault(tk, {"position_usd": 0.0, "holders": 0})
            slot["position_usd"] += abs(v)
            slot["holders"] += 1
    for slot in agg.values():
        slot["position_usd"] = round(slot["position_usd"], 0)
    return dict(sorted(agg.items(), key=lambda kv: kv[1]["position_usd"], reverse=True)[:top])


def flights_proximity(top: int = 12) -> list[dict]:
    """Corporate-jet activity per ticker — a classic (sparse, often stale) M&A / deal
    proximity tell. Display-only; flagged stale when the feed lags."""
    df = _read("flights")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "dep": df.get("DepartureCity", pd.Series(dtype=object)).map(_s),
        "arr": df.get("ArrivalCity", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna()]
    if d.empty:
        return []
    stale = bool(d["date"].notna().any() and (_now() - d["date"].max()).days > 45)
    rows = []
    for tk, g in d.groupby("ticker"):
        g2 = g[g["dep"].notna() & g["arr"].notna()]
        route = (f"{g2.iloc[0]['dep']} → {g2.iloc[0]['arr']}" if len(g2) else None)
        last = g["date"].max()
        rows.append({
            "ticker": tk, "flights": int(len(g)),
            "last_date": last.date().isoformat() if pd.notna(last) else None,
            "sample_route": route, "stale": stale,
        })
    rows.sort(key=lambda r: r["flights"], reverse=True)
    return rows[:top]


def exec_comp(top: int = 20) -> list[dict]:
    """Top-paid executive per watch ticker (alignment context). Watchlist-limited."""
    df = _read("execcomp")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("ticker", pd.Series(dtype=object)).map(_s),
        "name": df.get("name", pd.Series(dtype=object)).map(_s),
        "role": df.get("role", pd.Series(dtype=object)).map(_s),
        "year": df.get("year", pd.Series(dtype=object)).map(_f),
        "total": df.get("total_comp", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna() & d["total"].notna()]
    if d.empty:
        return []
    rows = []
    for tk, g in d.groupby("ticker"):
        r = g.sort_values("total", ascending=False).iloc[0]
        rows.append({
            "ticker": tk, "top_exec": r["name"], "role": r["role"],
            "total_comp": round(float(r["total"]), 0),
            "year": int(r["year"]) if pd.notna(r["year"]) else None,
        })
    rows.sort(key=lambda r: r["total_comp"], reverse=True)
    return rows[:top]


def retail_attention(wsb: list[dict] | None, top: int = 15) -> list[dict]:
    """Retail attention context — WSB mentions + sentiment (the live retail feed). Twitter
    follower growth is effectively dead, so WSB carries it. Lowest-weight channel."""
    out = []
    for r in (wsb or [])[:top]:
        m = r.get("mentions")
        if not r.get("ticker") or not m:
            continue
        out.append({"ticker": r["ticker"], "mentions": m, "sentiment": r.get("sentiment"),
                    "hot": bool(m and m >= 50)})
    return out


# =========================================================================== #
# THE WEIGHTED-CONVERGENCE KERNEL — single source for display + by_ticker
# =========================================================================== #
_DPI_Z_MIN_DATES = 20   # minimum distinct dates required for z-score path

def _dpi_z_lookup() -> dict[str, dict]:
    """Per-ticker DPI z-score vs the ticker's own off-exchange history, so 'accumulation'
    means LOW-for-this-name, not a fixed cut.

    Returns {ticker: {"z": float, "basis": "z_score"|"threshold"}} so callers can
    distinguish statistically-grounded z from fixed-threshold fallbacks.

    Requires >=20 distinct dates for the z-path (ddof=1); otherwise records
    basis='threshold' so the display layer can disclose the fallback used.
    """
    df = _read("offexchange")
    if df is None or df.empty or "DPI" not in df.columns:
        return {}
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "dpi": df.get("DPI", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna() & d["dpi"].notna()]
    if d.empty:
        return {}
    out: dict[str, dict] = {}
    for tk, g in d.groupby("ticker"):
        n_dates = g["date"].nunique()
        g = g.sort_values("date")
        latest = float(g["dpi"].iloc[-1])
        if n_dates >= _DPI_Z_MIN_DATES:
            hist = g["dpi"]
            mu, sd = float(hist.mean()), float(hist.std(ddof=1))
            if sd and sd > 1e-9:
                out[tk] = {"z": round((latest - mu) / sd, 2), "basis": "z_score"}
        else:
            # Insufficient history for robust z — fall back to fixed threshold;
            # basis='threshold' is exposed in the payload so the display can disclose it.
            out[tk] = {"z": None, "basis": "threshold"}
    return out


def channel_records(signals: dict, affiliations: dict | None = None) -> dict[str, dict]:
    """THE kernel: invert the cross-sectional signal lists into one weighted record per
    ticker. Returns {ticker: {channels, channel_detail, weighted_score, count, ...metrics}}.

    `affiliations`: optional {ticker: detail} from the influence graph — adds an
    'affiliation' channel so a graph edge (actor -> name) converges with the hard feeds.
    """
    by: dict[str, dict] = {}
    dpi_z = _dpi_z_lookup()

    def rec(tk):
        tk = _s(tk)
        if not tk:
            return None
        return by.setdefault(tk, {"ticker": tk, "channels": {}, "metrics": {}})

    def add(tk, channel, detail, drops=()):
        r = rec(tk)
        if r is None:
            return
        # Upgrade channels (drops non-empty) always displace their base targets exactly once.
        # Base channels (drops empty) are first-seen only — a second base firing from a
        # different source does not overwrite the first (preserves PIT semantics and prevents
        # a later base call from undoing an upgrade that already displaced it).
        if drops or channel not in r["channels"]:
            for d in drops:                  # displace base only when upgrade is accepted
                r["channels"].pop(d, None)
            r["channels"][channel] = detail

    # --- congress: cluster (>=3 members) outranks a single buyer ---
    for r in signals.get("political", {}).get("buys", []):
        members = int(r.get("members") or 0)
        if r.get("net", 0) <= 0:
            continue
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(congress_net=r.get("net"), congress_members=members)
        if members >= 3:
            add(r["ticker"], "congress_cluster", f"{members} members net +{r['net']}", drops=("congress_buy",))
        else:
            add(r["ticker"], "congress_buy", f"{members} member(s) net +{r['net']}")

    # --- gov contracts: real acceleration off a real base outranks mere presence ---
    for r in signals.get("gov_contracts", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(gov_contract_usd_30d=r.get("total_usd"), gov_contract_accel=r.get("accel_x"))
        ax, tot = r.get("accel_x"), r.get("total_usd") or 0
        if ax is not None and ax >= 2.0 and tot >= _GOV_FLOOR:
            add(r["ticker"], "gov_contract_accel", f"${tot:,.0f}, {ax:.1f}x accel", drops=("gov_contract",))
        else:
            add(r["ticker"], "gov_contract", f"${tot:,.0f} awarded")

    # --- federal GRANTS/LOANS: CHIPS/DOE/IRA money the contracts feed can't see ---
    for r in signals.get("gov_grants", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(gov_grant_usd=r.get("total_usd"), gov_grant_accel=r.get("accel_x"))
        ax, tot = r.get("accel_x"), r.get("total_usd") or 0
        if ax is not None and ax >= 2.0 and tot >= _GRANT_FLOOR:
            add(r["ticker"], "gov_grant_accel", f"${tot:,.0f}, {ax:.1f}x grant accel", drops=("gov_grant",))
        elif tot >= _GRANT_FLOOR:
            add(r["ticker"], "gov_grant", f"${tot:,.0f} federal grant/loan")

    # --- lobbying: spike off a real base outranks presence ---
    for r in signals.get("lobbying", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["lobbying_usd"] = r.get("spend_usd")
        sx, sp = r.get("spike_x"), r.get("spend_usd") or 0
        if sx is not None and sx >= 2.0 and sp >= _LOBBY_FLOOR:
            add(r["ticker"], "lobbying_spike", f"${sp:,.0f}, {sx:.1f}x spike", drops=("lobbying",))
        elif sp >= _LOBBY_FLOOR:
            add(r["ticker"], "lobbying", f"${sp:,.0f} lobbied")

    # --- insiders: cluster (>=3 buyers) outranks a single buy ---
    for r in signals.get("insiders", {}).get("buys", []):
        if (r.get("net_usd") or 0) <= 0:
            continue
        buyers = int(r.get("buyers") or 0)
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(insider_net_usd=r.get("net_usd"), insider_buyers=buyers)
        if buyers >= 3:
            add(r["ticker"], "insider_cluster", f"{buyers} insiders, ${r['net_usd']:,.0f} net", drops=("insider_buy",))
        else:
            add(r["ticker"], "insider_buy", f"${r['net_usd']:,.0f} net insider buy")

    # --- off-exchange: z-scored when history exists, else fixed accumulation lean ---
    for r in signals.get("offexchange", []):
        tk = r.get("ticker")
        entry = dpi_z.get(tk)   # {"z": float|None, "basis": "z_score"|"threshold"} or None
        z = entry["z"] if entry else None
        basis = entry["basis"] if entry else None
        m = rec(tk)
        if m is not None:
            m["metrics"]["dpi"] = r.get("dpi")
            if z is not None:
                m["metrics"]["dpi_z"] = z
            if basis:
                m["metrics"]["dpi_basis"] = basis
        accum = (z is not None and z <= -1.0) or (z is None and r.get("lean") == "accumulation")
        if accum:
            if m is not None:
                m["metrics"]["dpi_lean"] = "accumulation"
            add(tk, "darkpool_accum", (f"DPI z {z}" if z is not None else f"DPI {r.get('dpi')}"))

    # --- 13F: marquee funds outrank generic adds ---
    for r in signals.get("inst_13f", {}).get("adds", [])[:25]:
        fund = (r.get("fund") or "").lower()
        if any(s in fund for s in SMART_MONEY):
            add(r["ticker"], "smart_money_13f", f"{r.get('fund')} +${r.get('chg_usd', 0):,.0f}", drops=("13f_add",))
        else:
            add(r["ticker"], "13f_add", f"{r.get('fund')} +${r.get('chg_usd', 0):,.0f}")

    # --- openFDA drug catalysts: new approval / label expansion (healthcare blind spot) ---
    for r in signals.get("fda", []):
        kind = r.get("kind")
        if kind == "approval":
            add(r["ticker"], "fda_approval", r.get("drug") or "new FDA approval")
        elif kind == "label_expansion":
            add(r["ticker"], "fda_label_expansion", r.get("drug") or "FDA label expansion")

    # --- SEC 8-K material-event cluster (filing-time corporate activity) ---
    for r in signals.get("material_8k", []):
        n = int(r.get("count") or 0)
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["material_8k_30d"] = n
        if n >= 2:
            add(r["ticker"], "material_8k", f"{n} material 8-Ks (items {r.get('items', '')})")

    # --- CNBC desk picks ---
    for r in signals.get("cnbc", []):
        if (r.get("Direction") or "").lower() in ("buy", "final trade"):
            add(r.get("Ticker"), "cnbc_pick", r.get("Traders"))

    # --- Trump trade / branded affiliation (one channel for the whole round-trip) ---
    for r in signals.get("trump", []):
        from engine import altdata_picks
        if r.get("side") and not altdata_picks.is_passive(r.get("company"), r.get("ticker")):
            m = rec(r["ticker"])
            if m is not None:
                m["metrics"]["trump_side"] = r.get("side")
            add(r["ticker"], "trump", r.get("company"))

    # --- new feeds: app demand, patents, retail buzz ---
    for r in signals.get("app_ratings", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(app_rating=r.get("rating"), app_reviews=r.get("reviews"))
        if r.get("lean") == "strong":
            add(r["ticker"], "app_demand", f"{r.get('rating')}★ × {r.get('reviews'):,} reviews")
    for r in signals.get("patents", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["patents"] = r.get("patents")
        if int(r.get("patents") or 0) >= 3:
            add(r["ticker"], "patent_cluster", f"{r['patents']} grants, {r.get('ipc_classes')} IPC classes")
    for r in signals.get("retail", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["wsb_mentions"] = r.get("mentions")
        if r.get("hot"):
            add(r["ticker"], "retail_buzz", f"{r.get('mentions')} WSB mentions")
    for r in signals.get("hf", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["hf_downloads_30d"] = r.get("downloads_30d")
        if r.get("hot"):
            add(r["ticker"], "hf_model_momentum", f"+{r.get('wow_pct')}% model downloads")

    # --- deferred sources: options flow, analyst/insider/earnings (Finnhub), news, clinical, github ---
    for r in signals.get("unusual_options", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(opt_vol_oi=r.get("vol_oi"), opt_put_call=r.get("put_call"))
        if r.get("hot"):
            add(r["ticker"], "unusual_options", f"{r.get('mult')}× vol/OI, {r.get('lean')}")
    for r in signals.get("analyst", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["analyst_bull_ratio"] = r.get("bull_ratio")
        if r.get("hot"):
            # Detail describes the REVISION DELTA (the actual trigger), not the consensus level.
            # bull_ratio is carried in metrics as display context only (analyst_trends docstring).
            delta = r.get("revision_delta")
            delta_str = f"+{delta}" if delta is not None and delta > 0 else (str(delta) if delta is not None else "rising")
            add(r["ticker"], "analyst_upgrade_cluster", f"net upgrades {delta_str} revision delta")
    for r in signals.get("insider_mspr", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["insider_mspr"] = r.get("mspr")
        if r.get("hot"):
            add(r["ticker"], "insider_mspr", f"MSPR {r.get('mspr')}", drops=("insider_buy",))
    for r in signals.get("earnings", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["earnings_surprise_pct"] = r.get("surprise_pct")
        if r.get("hot"):
            add(r["ticker"], "earnings_beat", f"+{r.get('surprise_pct')}% surprise")
    for r in signals.get("news_sentiment", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["news_bull_ratio"] = r.get("bull_ratio")
        if r.get("hot"):
            add(r["ticker"], "news_sentiment", f"{r.get('bull_ratio')} bullish news ({r.get('articles')} art)")
    for r in signals.get("clinical", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"].update(clinical_phase3_starts=r.get("phase3_starts"), clinical_halts=r.get("halts"))
        if r.get("hot"):
            add(r["ticker"], "clinical_phase3_start",
                f"{r.get('phase3_starts')} new Phase-3" + (f", {r['halts']} halt(s)" if r.get("halts") else ""))
    for r in signals.get("github", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["github_stars"] = r.get("stars")
        if r.get("hot"):
            add(r["ticker"], "github_momentum", f"+{r.get('wow_pct')}% stars")

    # --- congressional position SIZE context (size, not a vote) ---
    for tk, slot in (signals.get("congress_holdings") or {}).items():
        m = rec(tk)
        if m is not None:
            m["metrics"]["congress_position_usd"] = slot.get("position_usd")

    # --- corporate donors: recorded as size, NOT a channel (too broad to vote) ---
    for r in signals.get("corporate_donors", []):
        m = rec(r["ticker"])
        if m is not None:
            m["metrics"]["donor_usd"] = r.get("total_usd")

    # --- special-situations cross-emit (P3.3 handshake): the event desk lights a channel ---
    # so a confirmed corporate event converges with the hard alt-data feeds on the same name.
    for r in signals.get("special_situations", []):
        if r.get("activist"):
            who = r.get("filer")
            add(r["ticker"], "activist_13d", "13D activist campaign" + (f" — {who}" if who else ""))
        else:
            add(r["ticker"], "special_situation", r.get("detail") or "live special situation")

    # --- influence-graph affiliations (actor -> name) ---
    for tk, detail in (affiliations or {}).items():
        add(tk, "affiliation", detail)

    # finalize: weighted score + count
    out = {}
    for tk, r in by.items():
        chans = dict(r["channels"])
        weighted = round(sum(CHANNEL_WEIGHTS.get(c, 0.2) for c in chans), 2)
        out[tk] = {
            "ticker": tk,
            "channels": sorted(chans.keys()),
            "channel_detail": chans,
            "weighted_score": weighted,
            "count": len(chans),
            **r["metrics"],
        }
    return out
