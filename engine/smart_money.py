"""Smart-money (13F) engine — diff curated super-investor quarters into
new/add/trim/exit, resolve CUSIP->ticker against our universe, and emit a
per-ticker "who holds this" context slice for the stock pages (plus a consensus
"most-held" overlap and per-fund summaries for a future board).

Reads the snapshots collectors/edgar_13f.py writes under data/smart_money/<slug>/.
Pure where it matters: parse/resolve/diff take in-memory inputs so tests need no
network and no parquet. CONTEXT only — never imported by any scoring path.
"""
from __future__ import annotations

import logging
import pathlib
from datetime import datetime, timezone

import pandas as pd
import yaml

from collectors import edgar
from lib import config

log = logging.getLogger(__name__)

NOTE = ("13F-HR holdings: quarterly, ~45-day lag, long-only US equity stakes "
        ">= $100M. No shorts, options detail, or non-US positions. CUSIPs are "
        "name-matched to tickers, so some lines are hidden. Context on who holds "
        "a name, not a buy list or a real-time signal.")

# extra tokens stripped beyond edgar._SUFFIX so class/share descriptors and
# connective words on 13F issuer names collapse onto our universe company names.
_EXTRA_DROP = {"CL", "SER", "SERIES", "ADR", "ADS", "SPON", "SPONSORED", "REIT",
               "SHS", "SH", "ORD", "VTG", "VOTING", "COMMON", "CMN", "NEW",
               "PAR", "REDH", "DEL", "MD", "RG", "REG", "OF", "AND", "THE",
               "FOR", "TO",
               # domicile / market tags 13F appends that our names omit
               "SWITZ", "IRE", "IRELAND", "BERMUDA", "BMU", "CAYMAN", "NETH",
               "LUX", "JERSEY", "UK", "USA"}
# 13F abbreviations -> the canonical token our universe names use (canonical may
# itself be an edgar suffix that then drops out, e.g. GRP->GROUP->dropped).
_SYN = {"FINL": "FINANCIAL", "FIN": "FINANCIAL", "GRP": "GROUP", "HLDGS": "HOLDINGS",
        "HLDG": "HOLDINGS", "INTL": "INTERNATIONAL", "TECH": "TECHNOLOGY",
        "TECHS": "TECHNOLOGY", "SYS": "SYSTEMS", "MGMT": "MANAGEMENT",
        "COS": "COMPANIES", "SVCS": "SERVICES", "SVC": "SERVICES",
        "COMMUN": "COMMUNICATIONS", "COMM": "COMMUNICATIONS",
        "PHARM": "PHARMACEUTICALS", "PHARMA": "PHARMACEUTICALS",
        "PETE": "PETROLEUM", "PAC": "PACIFIC", "NATL": "NATIONAL",
        "AMER": "AMERICAN", "INDS": "INDUSTRIES", "MTRS": "MOTORS",
        "ELEC": "ELECTRIC", "ENRGY": "ENERGY", "RES": "RESOURCES",
        "PPTYS": "PROPERTIES", "PWR": "POWER", "LABS": "LABORATORIES"}
# tokens dropped after canonicalization (edgar suffixes + our extras)
_DROP = edgar._SUFFIX | _EXTRA_DROP

# share-count change beyond +/- this fraction => ADD / TRIM (else HOLD)
_MOVE_FRAC = 0.10

# --------------------------------------------------------------------------- #
# Share-class equivalence — loaded once, applied everywhere                     #
# --------------------------------------------------------------------------- #

def _load_equiv_table() -> dict[str, str]:
    """Load config/share_class_equiv.yml, returning {non-canonical: canonical} map.
    Silent-degrades to empty dict if the file is absent."""
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        p = root / "config" / "share_class_equiv.yml"
        if not p.exists():
            return {}
        with open(p) as fh:
            data = yaml.safe_load(fh) or {}
        equiv: dict[str, str] = {}
        for entry in data.get("equivalences", []):
            t = str(entry.get("ticker", "")).strip().upper()
            c = str(entry.get("canonical", "")).strip().upper()
            if t and c and t != c:
                equiv[t] = c
        return equiv
    except Exception:  # noqa: BLE001
        log.debug("share_class_equiv.yml load failed — issuer dedup via CUSIP only")
        return {}


_EQUIV: dict[str, str] = {}  # populated lazily on first call to issuer_key


def _get_equiv() -> dict[str, str]:
    global _EQUIV
    if not _EQUIV:
        _EQUIV = _load_equiv_table()
    return _EQUIV


def issuer_key(ticker: str | None, cusip: str | None) -> str:
    """Canonical share-class key for deduplication across 13F holders counts.

    Collapses via the share_class_equiv.yml table first (e.g. GOOG -> GOOGL,
    BRK.B -> BRK.A). Falls back to the 6-char CUSIP stem when two tickers share it
    (same issuer, different series). Returns the canonical ticker or CUSIP stem as a
    non-empty string suitable as a grouping key.

    PURE (uses module-level cached table). Holder counts that call this must NEVER
    double-count share classes — this is the contract tested in the BRK.A+BRK.B
    fixture test in tests/test_smart_money.py.
    """
    eq = _get_equiv()
    t = str(ticker or "").strip().upper()
    if eq and t in eq:
        t = eq[t]
    c = str(cusip or "").strip().upper()
    stem = c[:6] if len(c) >= 6 else ""
    return t if t and t not in ("", "NAN", "NONE") else (stem or "UNKNOWN")

# >= this many tracked funds currently holding a name flags it a cross-fund "VIP"
# (broad super-investor consensus). Display context — never a scoring leg.
_VIP_MIN = 5


def overlap_stats(holders: list[dict]) -> dict:
    """Cross-fund VIP / ownership-concentration read for one name from its tracked
    holders (the by_ticker entries). PURE. CONTEXT only.

    * ``vip`` — number of tracked funds CURRENTLY holding it (exits excluded); a
      higher count = broader super-investor consensus.
    * ``ownership_hhi`` — Herfindahl of the holders' dollar values (Σ wᵢ², wᵢ =
      fundᵢ's share of the tracked dollars in this name). ~1/vip = evenly held;
      near 1 = one whale dominates (a "consensus" of one, not a crowd).
    * ``max_book_pct`` / ``avg_book_pct`` — the highest- and average-conviction
      holder's weight (the stock's % of that fund's reported book).
    """
    cur = [e for e in holders if e.get("action") != "exit"]
    vip = len(cur)
    if not vip:
        return {"vip": 0}
    vals = [float(e.get("value_usd") or 0.0) for e in cur]
    tot = sum(vals)
    hhi = round(sum((v / tot) ** 2 for v in vals), 3) if tot > 0 else None
    books = [float(e["pct_portfolio"]) for e in cur if e.get("pct_portfolio") is not None]
    return {
        "vip": vip,
        "is_vip": vip >= _VIP_MIN,
        "ownership_hhi": hhi,
        "max_book_pct": round(max(books), 2) if books else None,
        "avg_book_pct": round(sum(books) / len(books), 2) if books else None,
    }


def _norm(name: str) -> str:
    """Normalize an issuer/company name for cross-source matching: strip
    possessive apostrophes (Moody's -> MOODYS, matching 13F's MOODYS), run the
    shared edgar normalizer, map common 13F abbreviations to canonical tokens,
    and drop suffix/connective words. Maximizes 13F<->universe name overlap."""
    s = str(name or "").replace("'", "").replace("’", "")
    base = edgar._norm_name(s)
    toks = [_SYN.get(t, t) for t in base.split()]
    return " ".join(t for t in toks if t and t not in _DROP)


def name_ticker_map(membership: pd.DataFrame | None = None) -> dict[str, str]:
    """normalized issuer name -> ticker, from the S&P 1500 membership table.
    First active ticker wins on a normalized-name collision (e.g. GOOGL before
    GOOG); pass `membership` to unit test without disk."""
    if membership is None:
        p = config.data_dir() / "universe" / "membership.parquet"
        if not p.exists():
            return {}
        membership = pd.read_parquet(p)
    out: dict[str, str] = {}
    df = membership
    if "active" in df.columns:
        df = df[df["active"].astype(bool)]
    for _, row in df.iterrows():
        nm = _norm(row.get("name", ""))
        if nm:
            out.setdefault(nm, str(row["ticker"]))
    return out


def cusip_ticker_seed() -> dict[str, str]:
    """Exact CUSIP -> ticker pairs harvested from the ARK holdings snapshots we
    already store (the only repo source carrying both). Small (~60) but precise;
    used as the high-confidence first pass before name matching."""
    import glob
    out: dict[str, str] = {}
    for f in glob.glob(str(config.data_dir() / "holdings" / "*" / "*.parquet")):
        try:
            d = pd.read_parquet(f, columns=["cusip", "ticker"])
        except Exception:  # noqa: BLE001 — not every snapshot carries cusip
            continue
        for c, t in zip(d["cusip"].astype(str), d["ticker"].astype(str)):
            c = c.strip().upper()
            if c and t and t.lower() != "nan":
                out.setdefault(c, t)
    return out


def full_cusip_map() -> tuple[dict[str, str], dict]:
    """The full CUSIP→ticker resolver for 13F lines: the precise ARK seed FIRST,
    then the free OpenFIGI master (collectors/openfigi.py) layered underneath to
    unhide foreign/ADR/renamed/non-index lines the seed + name-match miss. Seed
    wins on conflict (hand-verified).

    Returns (cusip_map, coverage_meta) where coverage_meta = {
        'openfigi_entries': int,   # 0 = OpenFIGI cache empty → WARNING logged
        'ark_seed_entries': int,
    }.
    Callers that only need the map can do `cusip_map, _ = full_cusip_map()` or
    for backward compat pass the result's first element.
    """
    try:
        from collectors.openfigi import load_cusip_ticker
        figi = load_cusip_ticker()
    except Exception:  # noqa: BLE001 — never break resolution over an optional cache
        figi = {}

    if len(figi) == 0:
        log.warning("full_cusip_map: OpenFIGI cache contributed 0 entries — "
                    "resolution falls back to ARK seed + name matching only; "
                    "run collectors/openfigi.py to refresh the cache")

    seed = cusip_ticker_seed()
    combined = {**figi, **seed}  # seed overrides OpenFIGI on conflict
    meta = {"openfigi_entries": len(figi), "ark_seed_entries": len(seed)}
    return combined, meta


# --------------------------------------------------------------------------- #
# New SM2 pure helpers                                                          #
# --------------------------------------------------------------------------- #

def position_rank_and_tilt(snap: pd.DataFrame) -> pd.DataFrame:
    """Attach within-fund position rank and tilt to a resolved snapshot.

    rank     : 1 = largest position by value_usd; PURE, row-level.
    tilt_pp  : pct_portfolio − mean(pct_portfolio) for the fund's resolved rows.
               Positive = overweight vs average fund allocation; PURE.

    Returns a copy of the frame with added columns [rank, tilt_pp].
    Rows lacking value_usd or pct_portfolio get rank=None and tilt_pp=None.
    """
    out = snap.copy()
    if "value_usd" not in out.columns:
        out["rank"] = None
        out["tilt_pp"] = None
        return out
    out = out.sort_values("value_usd", ascending=False).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    if "pct_portfolio" in out.columns:
        mean_pct = out["pct_portfolio"].mean()
        out["tilt_pp"] = (out["pct_portfolio"] - mean_pct).round(3)
    else:
        out["tilt_pp"] = None
    return out


def window_dressing_flag(fund_snaps: list[tuple[str, str, pd.DataFrame]],
                         ticker: str) -> str:
    """Window-dressing persistence flag for a ticker in a fund's history.

    'persisted'   : appeared in the LATEST quarter AND at least one prior quarter.
    'one_quarter' : appeared in exactly one quarter that is NOT the latest.
    'pending'     : appeared only in the latest quarter (persistence unknown yet).

    'pending' is the correct label for any new position in the latest quarter since
    we cannot yet determine whether it will persist. PURE.
    """
    if not fund_snaps:
        return "pending"
    tickers_by_q: list[set] = []
    for _, _, snap in fund_snaps:
        eq = snap[snap.get("sh_type", pd.Series(["SH"] * len(snap))) == "SH"]
        if "ticker" in eq.columns:
            tickers_by_q.append(set(eq["ticker"].dropna().astype(str)))
        else:
            tickers_by_q.append(set())
    if not tickers_by_q:
        return "pending"
    latest_has = ticker in tickers_by_q[-1]
    prior_count = sum(1 for s in tickers_by_q[:-1] if ticker in s)
    if latest_has:
        return "persisted" if prior_count >= 1 else "pending"
    return "one_quarter" if prior_count == 1 else "persisted" if prior_count > 1 else "pending"


def amendment_delta(slug: str) -> list[dict]:
    """Position deltas between the original 13F-HR and any amendments (13F-HR/A).

    Amendments are stored under data/smart_money/<slug>/amendments/<period_end>__<filing_date>.parquet
    (same schema as the originals, may not exist — handled gracefully).

    Returns a list of delta records [{ticker, cusip, issuer, pct_change_shares,
    orig_filing_date, amendment_filing_date, period_end}] for changes >±20% in shares.
    Empty list when no amendments directory exists or no material changes found.
    """
    d = config.data_dir() / "smart_money" / slug / "amendments"
    if not d.exists():
        return []
    # Load originals index: period_end -> (filing_date, DataFrame)
    orig_dir = config.data_dir() / "smart_money" / slug
    originals: dict[str, tuple[str, pd.DataFrame]] = {}
    for p in sorted(orig_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
            pe = p.stem
            fd = _snapshot_filing_date(df)
            originals[pe] = (fd, df)
        except Exception:  # noqa: BLE001
            continue

    results: list[dict] = []
    for ap in sorted(d.glob("*.parquet")):
        # Filename: <period_end>__<filing_date>.parquet
        stem = ap.stem
        parts = stem.split("__", 1)
        if len(parts) != 2:
            continue
        period_end, amend_filing_date = parts[0], parts[1]
        if period_end not in originals:
            continue
        orig_fd, orig_df = originals[period_end]
        try:
            amend_df = pd.read_parquet(ap)
        except Exception:  # noqa: BLE001
            continue
        # Compare shares by cusip
        def _to_shares(df: pd.DataFrame) -> dict[str, tuple]:
            eq = df[df.get("sh_type", pd.Series(["SH"] * len(df))) == "SH"]
            g = eq.groupby("cusip", as_index=False).agg(
                issuer=("issuer", "first"), shares=("shares", "sum"))
            return {row["cusip"]: (row["issuer"], float(row["shares"]))
                    for row in g.to_dict("records")}
        orig_sh = _to_shares(orig_df)
        amend_sh = _to_shares(amend_df)
        all_cusips = set(orig_sh) | set(amend_sh)
        for cusip in all_cusips:
            o_issuer, o_shares = orig_sh.get(cusip, ("", 0.0))
            a_issuer, a_shares = amend_sh.get(cusip, ("", 0.0))
            if o_shares == 0 and a_shares == 0:
                continue
            if o_shares == 0:
                pct_change = None  # new position in amendment
            elif a_shares == 0:
                pct_change = -100.0
            else:
                pct_change = round((a_shares - o_shares) / o_shares * 100.0, 1)
            if pct_change is None or abs(pct_change) > 20.0:
                results.append({
                    "cusip": cusip, "issuer": a_issuer or o_issuer,
                    "pct_change_shares": pct_change,
                    "orig_filing_date": orig_fd,
                    "amendment_filing_date": amend_filing_date,
                    "period_end": period_end,
                })
    return results


def resolve_tickers(df: pd.DataFrame, name_map: dict[str, str],
                    cusip_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Add a `ticker` column (or None). PURE — takes the maps as args. CUSIP 8/9-char
    exact match first (precise), then normalized issuer-name match (broad)."""
    cusip_map = cusip_map or {}
    out = df.copy()

    def _one(cusip: str, issuer: str) -> str | None:
        c = str(cusip).strip().upper()
        if c in cusip_map:
            return cusip_map[c]
        if len(c) >= 8 and c[:8] in {k[:8] for k in cusip_map}:  # 8-char issuer stem
            for k, v in cusip_map.items():
                if k[:8] == c[:8]:
                    return v
        return name_map.get(_norm(issuer))

    out["ticker"] = [_one(c, i) for c, i in zip(out.get("cusip", ""), out.get("issuer", ""))]
    return out


def diff_snapshots(prev: pd.DataFrame | None, latest: pd.DataFrame,
                   move_frac: float = _MOVE_FRAC) -> pd.DataFrame:
    """Classify each position in `latest` (and full exits from `prev`) as
    new/add/trim/hold/exit by share count. PURE. Snapshots use the
    collectors/edgar_13f.py schema (cusip, shares, value_usd, sh_type, issuer …).
    pct_portfolio = value share of the latest equity book."""
    eq = latest[latest.get("sh_type", "SH") == "SH"].copy()
    if eq.empty:
        return eq.assign(action=[], pct_portfolio=[], prior_shares=[], shares_change_pct=[])
    eq = (eq.groupby("cusip", as_index=False)
            .agg(issuer=("issuer", "first"), shares=("shares", "sum"),
                 value_usd=("value_usd", "sum")))
    total = eq["value_usd"].sum() or 1.0
    eq["pct_portfolio"] = 100.0 * eq["value_usd"] / total

    prior_sh: dict[str, float] = {}
    if prev is not None and not prev.empty:
        pe = prev[prev.get("sh_type", "SH") == "SH"]
        prior_sh = pe.groupby("cusip")["shares"].sum().to_dict()

    actions, prior_col, chg = [], [], []
    for c, sh in zip(eq["cusip"], eq["shares"]):
        ps = prior_sh.get(c)
        prior_col.append(ps)
        if ps is None or ps == 0:
            actions.append("new"); chg.append(None)
        else:
            pct = (sh - ps) / ps
            chg.append(round(100.0 * pct, 1))
            actions.append("add" if pct > move_frac else "trim" if pct < -move_frac else "hold")
    eq["action"] = actions
    eq["prior_shares"] = prior_col
    eq["shares_change_pct"] = chg

    # full exits: in prev, gone from latest
    if prior_sh:
        gone = set(prior_sh) - set(eq["cusip"])
        if gone:
            pe = prev[prev["cusip"].isin(gone) & (prev.get("sh_type", "SH") == "SH")]
            ex = (pe.groupby("cusip", as_index=False)
                    .agg(issuer=("issuer", "first"), shares=("shares", "sum"),
                         value_usd=("value_usd", "sum")))
            ex["pct_portfolio"] = 0.0
            ex["action"] = "exit"
            ex["prior_shares"] = ex["shares"]
            ex["shares"] = 0.0
            ex["shares_change_pct"] = -100.0
            eq = pd.concat([eq, ex], ignore_index=True)
    return eq


# fraction value-change that, absent a holder-count move, still reads as a trend
_TREND_VAL_FRAC = 15.0


def accumulation_trend(series: list[dict]) -> dict | None:
    """Multi-quarter "Historical institutional increase/decrease" read for ONE name.
    PURE. `series` = per-quarter aggregates ascending by period, each
    {period, n_funds, value_usd, filing_date?} (n_funds = tracked funds holding it
    that quarter; `filing_date` = when that quarter's data became PUBLIC).

    Direction is driven by the holder-count change across the window (broadening
    vs narrowing super-investor ownership), with aggregate $ value as the
    tiebreaker when the holder count is flat. Leading quarters before the name was
    ever held are trimmed, but a trailing exit-to-zero is KEPT (it IS the signal).
    <2 quarters of history -> None (no trend yet).

    LOOK-AHEAD: `to_period`/`from_period` are QUARTER-END dates (NOT observable
    until the 13F is filed ~45 days later). The trade-correct as-of is `available_on`
    (= the latest holder's filing_date for the most-recent quarter). Any scorer MUST
    join on `available_on`, never `to_period` — see `as_of_for_scoring`."""
    start = next((i for i, p in enumerate(series)
                  if p.get("n_funds") or p.get("value_usd")), None)
    if start is None:
        return None
    pts = series[start:]
    if len(pts) < 2:
        return None
    first, last = pts[0], pts[-1]
    h0, h1 = int(first.get("n_funds") or 0), int(last.get("n_funds") or 0)
    v0 = float(first.get("value_usd") or 0.0)
    v1 = float(last.get("value_usd") or 0.0)
    h_delta = h1 - h0
    v_pct = round((v1 - v0) / v0 * 100, 1) if v0 > 0 else None
    if h_delta > 0 or (h_delta == 0 and v_pct is not None and v_pct > _TREND_VAL_FRAC):
        direction = "accumulating"
    elif h_delta < 0 or (h_delta == 0 and v_pct is not None and v_pct < -_TREND_VAL_FRAC):
        direction = "distributing"
    else:
        direction = "stable"
    return {
        "direction": direction,
        "n_quarters": len(pts),
        "holders_first": h0,
        "holders_last": h1,
        "holders_delta": h_delta,
        "value_change_pct": v_pct,
        "from_period": str(first.get("period") or ""),
        "to_period": str(last.get("period") or ""),
        # filing dates = the only look-ahead-free timestamps (see docstring)
        "available_on": str(last.get("filing_date") or ""),
        "available_on_first": str(first.get("filing_date") or ""),
        "holders_series": [int(p.get("n_funds") or 0) for p in pts],
    }


def as_of_for_scoring(trend: dict | None) -> str | None:
    """The ONLY look-ahead-free as-of date for joining an accumulation trend to
    forward returns: the most-recent quarter's PUBLIC filing date, never the
    quarter-end. Returns None if no filing date is known (then the trend must not
    be scored). This is the contract every scorer must honor (guard-tested)."""
    if not trend:
        return None
    return trend.get("available_on") or None


def enrich_since_filing(by_ticker: dict[str, dict]) -> None:
    """Attach realized price-move-since-filing context to each ticker in `by_ticker`
    (mutates in-place). For every ticker whose `trend.available_on` is a valid date,
    we compute the stock's % return and SPY-excess return from that public filing date
    to the latest available close. Result is stored as `since_filing` on the ticker
    record — a DESCRIPTIVE realized fact, NEVER a score, prediction, or signal input.

    LOOK-AHEAD-FREE: anchor is always `trend.available_on` (the date the 13F became
    public, ~45 days after period_end). Missing/unparseable date or missing price file
    → field is OMITTED for that ticker (best-effort, never crashes the build).

    Uses the same ClosePanel (yahoo ∪ breadth caches) as engine.manager_trades so
    the price-load logic is identical and not duplicated."""
    try:
        from engine.manager_trades import ClosePanel
        panel = ClosePanel()
    except Exception:  # noqa: BLE001 — price panel unavailable; degrade silently
        log.debug("enrich_since_filing: ClosePanel unavailable — skipping price enrichment")
        return

    import pandas as pd

    for ticker, rec in by_ticker.items():
        try:
            trend = rec.get("trend") or {}
            ao = trend.get("available_on") or ""
            if not ao or ao == "nan" or ao == "None":
                continue
            # Validate the date is parseable
            try:
                ao_ts = pd.Timestamp(ao)
            except Exception:
                continue

            s = panel.get(ticker)
            if s is None or len(s) == 0:
                continue
            spy = panel.spy
            if spy is None or len(spy) == 0:
                continue

            after = s.index[s.index >= ao_ts]
            if len(after) == 0:
                continue
            entry_date = after[0]
            p0 = float(s.loc[entry_date])
            p1 = float(s.iloc[-1])
            if p0 <= 0:
                continue

            # SPY over the same calendar window
            spy_after = spy.index[spy.index >= ao_ts]
            if len(spy_after) == 0:
                continue
            b0 = float(spy.loc[spy_after[0]])
            b1_idx = spy.index[spy.index <= s.index[-1]]
            if len(b1_idx) == 0:
                continue
            b1 = float(spy.loc[b1_idx[-1]])
            if b0 <= 0:
                continue

            ret_pct = round((p1 / p0 - 1.0) * 100.0, 1)
            spy_pct = round((b1 / b0 - 1.0) * 100.0, 1)
            ex_spy_pct = round(ret_pct - spy_pct, 1)
            # trading days in the window (inclusive of entry session)
            days = int(len(s.index[(s.index >= entry_date) & (s.index <= s.index[-1])]))

            rec["since_filing"] = {
                "available_on": ao,
                "ret_pct": ret_pct,
                "ex_spy_pct": ex_spy_pct,
                "days": days,
                "thru": str(s.index[-1].date()),
            }
        except Exception:  # noqa: BLE001 — per-ticker failure must not interrupt the loop
            log.debug("enrich_since_filing: skipped %s", ticker, exc_info=True)


# --------------------------------------------------------------------------- #
# Orchestration (reads disk; the heavy lifting above is pure/tested).
# --------------------------------------------------------------------------- #
def _read_two(slug: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    d = config.data_dir() / "smart_money" / slug
    if not d.exists():
        return None, None
    snaps = sorted(d.glob("*.parquet"))
    if not snaps:
        return None, None
    latest = pd.read_parquet(snaps[-1])
    prev = pd.read_parquet(snaps[-2]) if len(snaps) >= 2 else None
    return prev, latest


def _snapshot_filing_date(df: pd.DataFrame) -> str:
    """The public filing date stamped on a snapshot (collectors/edgar_13f.py writes
    it per row). Empty string if absent (legacy snapshots) — callers degrade to a
    look-ahead-free None as-of rather than guessing."""
    if "filing_date" in df.columns and len(df):
        v = df["filing_date"].iloc[0]
        return str(v) if v is not None and str(v) != "nan" else ""
    return ""


def _read_all(slug: str) -> list[tuple[str, str, pd.DataFrame]]:
    """Every retained snapshot for a fund, (period_end, filing_date, frame) ascending
    by period. `filing_date` is when that quarter became PUBLIC (look-ahead-free)."""
    d = config.data_dir() / "smart_money" / slug
    if not d.exists():
        return []
    out: list[tuple[str, str, pd.DataFrame]] = []
    for p in sorted(d.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            continue
        if not df.empty:
            out.append((p.stem, _snapshot_filing_date(df), df))
    return out


def _accumulation(funds: dict, name_map: dict[str, str],
                  cusip_map: dict[str, str]) -> dict[str, dict]:
    """{ticker: accumulation_trend(...)} across ALL retained quarters of every
    tracked fund — the multi-quarter "who's been building vs trimming this name"
    rollup. Reads disk; the per-name math is the pure accumulation_trend above.

    Per (ticker, quarter) we keep the LATEST contributing fund's filing_date as the
    quarter's `available_on` — the conservative date by which that quarter's holder
    set was fully public — so the trend carries a look-ahead-free as-of."""
    # ticker -> period -> [holder_count, total_value, max_filing_date]
    agg: dict[str, dict[str, list]] = {}
    periods: set[str] = set()
    for slug in funds:
        for period_end, filing_date, snap in _read_all(slug):
            eq = snap[snap.get("sh_type", "SH") == "SH"]
            if eq.empty:
                continue
            g = (eq.groupby("cusip", as_index=False)
                   .agg(issuer=("issuer", "first"), value_usd=("value_usd", "sum")))
            res = resolve_tickers(g, name_map, cusip_map)
            res = res[res["ticker"].notna()]
            if res.empty:
                continue
            periods.add(period_end)
            # one fund counted once per ticker (collapse dual-class lots)
            per = res.groupby("ticker", as_index=False).agg(value_usd=("value_usd", "sum"))
            for r in per.itertuples(index=False):
                slot = agg.setdefault(r.ticker, {}).setdefault(period_end, [0, 0.0, ""])
                slot[0] += 1
                slot[1] += float(r.value_usd)
                if filing_date > slot[2]:        # latest filer = fully-public date
                    slot[2] = filing_date
    ordered = sorted(periods)
    out: dict[str, dict] = {}
    for tk, pmap in agg.items():
        series = [{"period": p, "n_funds": pmap.get(p, [0, 0.0, ""])[0],
                   "value_usd": pmap.get(p, [0, 0.0, ""])[1],
                   "filing_date": pmap.get(p, [0, 0.0, ""])[2]} for p in ordered]
        tr = accumulation_trend(series)
        if tr is not None:
            out[tk] = tr
    return out


def _safe_manager_quality(cfg: dict | None) -> dict:
    """Backtested per-fund grades, or {} if prices/snapshots are unavailable.
    Lazy import breaks the smart_money<->manager_quality cycle; quality is optional
    CONTEXT so any failure must degrade silently, never break the panel."""
    try:
        from engine.manager_quality import compute_manager_quality
        return compute_manager_quality(cfg)
    except Exception:  # noqa: BLE001
        log.debug("manager_quality unavailable", exc_info=True)
        return {}


def compute_smart_money(cfg: dict | None = None) -> dict | None:
    cfg = cfg if cfg is not None else (config.load().get("smart_money", {}) or {})
    funds = cfg.get("funds", {}) or {}
    if not funds:
        return None
    name_map = name_ticker_map()
    cusip_map, _figi_meta = full_cusip_map()      # ARK seed + free OpenFIGI master
    top_n = int(cfg.get("panel_top_n", 12))

    by_ticker: dict[str, dict] = {}
    fund_rows: list[dict] = []
    overlap: dict[str, dict] = {}
    as_of_dates: list[str] = []

    for slug, spec in funds.items():
        prev, latest = _read_two(slug)
        if latest is None or latest.empty:
            continue
        period_end = str(latest["period_end"].iloc[0]) if "period_end" in latest else ""
        as_of_dates.append(period_end)
        diff = diff_snapshots(prev, latest)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        resolved = diff[diff["ticker"].notna()]
        if not resolved.empty:
            # collapse dual-class / multi-lot lines mapping to the same ticker
            # (e.g. a fund holding BRK-A + BRK-B) so a fund is counted once per name:
            # sum the weight/value, take the largest lot's action.
            resolved = (resolved.sort_values("value_usd", ascending=False)
                        .groupby("ticker", as_index=False)
                        .agg(action=("action", "first"),
                             pct_portfolio=("pct_portfolio", "sum"),
                             value_usd=("value_usd", "sum"),
                             shares_change_pct=("shares_change_pct", "first")))
        # per-fund coverage: resolved / total positions
        n_resolved_count = int(len(resolved)) if not resolved.empty else 0
        n_positions_count = int(len(diff))
        coverage_pct = (round(100.0 * n_resolved_count / n_positions_count, 1)
                        if n_positions_count else None)
        fund_rows.append({
            "slug": slug, "name": spec.get("name", slug), "period_end": period_end,
            "n_positions": n_positions_count, "n_resolved": n_resolved_count,
            "resolution_coverage_pct": coverage_pct,
            "top": [{"ticker": t, "pct": round(float(p), 2)}
                    for t, p in resolved.sort_values("pct_portfolio", ascending=False)
                    .head(5)[["ticker", "pct_portfolio"]].itertuples(index=False)],
        })
        # Attach position rank + within-fund tilt to the resolved frame before iterating
        if not resolved.empty:
            resolved = position_rank_and_tilt(resolved)
        for r in resolved.itertuples(index=False):
            t = r.ticker
            entry = {
                "fund": slug.upper(), "fund_name": spec.get("name", slug),
                "action": r.action, "pct_portfolio": round(float(r.pct_portfolio), 2),
                "value_usd": float(r.value_usd), "period_end": period_end,
                "shares_change_pct": (None if r.shares_change_pct is None
                                      or pd.isna(r.shares_change_pct)
                                      else float(r.shares_change_pct)),
                "position_rank": (int(r.rank) if hasattr(r, "rank")
                                  and r.rank is not None else None),
                "tilt_pp": (round(float(r.tilt_pp), 3) if hasattr(r, "tilt_pp")
                            and r.tilt_pp is not None else None),
            }
            by_ticker.setdefault(t, {"holders": []})["holders"].append(entry)
            ov = overlap.setdefault(t, {"ticker": t, "n_funds": 0, "funds": [],
                                        "total_value": 0.0})
            ov["n_funds"] += 1
            ov["funds"].append(slug.upper())
            ov["total_value"] += float(r.value_usd)

    if not by_ticker:
        return None

    # multi-quarter "Historical institutional increase/decrease" trend per name
    trends = _accumulation(funds, name_map, cusip_map)
    # backtested per-fund predictiveness — quality-weights the panel (descriptive
    # CONTEXT, never a scored alpha; see engine/manager_quality.py)
    mq = _safe_manager_quality(cfg)

    _BUY = {"new": 0, "add": 1, "hold": 2, "trim": 3, "exit": 4}
    for t, rec in by_ticker.items():
        h = rec["holders"]
        h.sort(key=lambda e: (_BUY.get(e["action"], 9), -e["pct_portfolio"]))
        rec.update(overlap_stats(h))            # vip / hhi / book conviction (full list)
        rec["holders"] = h[:top_n]
        rec["n_holders"] = len(h)
        rec["n_buying"] = sum(1 for e in h if e["action"] in ("new", "add"))
        rec["n_selling"] = sum(1 for e in h if e["action"] in ("trim", "exit"))
        rec["as_of"] = max((e["period_end"] for e in h), default="")
        if t in trends:
            rec["trend"] = trends[t]
        # tag each holder with its fund's backtested grade + flag clustering by
        # GRADED-skilled funds — the "not all managers are equal" lesson.
        for e in h:
            g = (mq.get(str(e["fund"]).lower()) or {}).get("grade")
            if g and g != "n/a":
                e["fund_grade"] = g
        graded = [e["fund_grade"] for e in h if e.get("fund_grade")]
        if graded:
            rec["quality_cluster"] = {
                "n_quality_buyers": sum(1 for e in h if e.get("fund_grade") in ("A", "B")
                                        and e["action"] in ("new", "add")),
                "best_grade": min(graded),       # 'A' < 'B' < 'C' < 'D'
                "graded_holders": len(graded),
            }

    # enrich the per-fund board with each fund's quality grade
    for fr in fund_rows:
        q = mq.get(fr["slug"]) or {}
        if q.get("grade") and q["grade"] != "n/a":
            fr["quality_grade"] = q["grade"]
            fr["quality_z"] = q.get("quality_z")

    most_held = sorted(overlap.values(), key=lambda r: (-r["n_funds"], -r["total_value"]))[:40]
    for m in most_held:
        m["total_value"] = round(m["total_value"], 0)

    return {
        "as_of": max(as_of_dates) if as_of_dates else "",
        "built": datetime.now(timezone.utc).isoformat(),
        "note": NOTE,
        "n_funds": len(fund_rows),
        "n_names": len(by_ticker),
        "funds": sorted(fund_rows, key=lambda r: r["name"]),
        "most_held": most_held,
        "manager_quality": mq,
        "by_ticker": by_ticker,
        # OpenFIGI resolution metadata (n_resolved/n_positions per fund above;
        # openfigi_entries=0 triggers a WARNING in full_cusip_map already)
        "cusip_resolution": _figi_meta,
    }
