"""ETF holdings tracker for the active/thematic watchlist.

Daily snapshot per fund under data/holdings/<TICKER>/<YYYY-MM-DD>.parquet.
The engine diffs consecutive snapshots with flow normalization:

    expected_shares(t) = shares(t-1) * SO(t)/SO(t-1)
    active_decision(t) = actual_shares(t) - expected_shares(t)

which isolates manager decisions from creation/redemption pass-through.
N-PORT (EDGAR, ~60d lag) is a quarterly validation check only, never a live
signal. Per-sponsor fragility is documented in LIMITATIONS.md.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Non-equity holding lines that must NEVER be treated as a stock position: cash,
# FX/currency, money-market, equivalents, derivatives (incl. index-futures
# overlays), receivables/payables. Their "shares" are a dollar/units BALANCE or a
# contract count, not an ownership stake, so a flow-normalized share-diff over
# them is meaningless — it explodes into absurd % (the radar's
# "CHATS Cash&Other −15,116,065%" / "BETZ Euro −338,977%" bug). This predicate is
# shared by the diff engine (active_changes_dir) AND the collector
# (collectors.etf_holdings._normalize), because already-stored snapshots are
# never re-cleaned — the diff layer can't trust the snapshot was filtered at write.
# Real foreign-listed EQUITIES (e.g. "000720 KS", "1211 HK", "8001 JP") are kept —
# INCLUDING the ones whose ticker is currency-SHAPED ("EUR AU" = European Lithium
# on the ASX, "COP" = ConocoPhillips). The ticker alone never decides those; the
# name column does. See the _CURRENCY_NAME_RE block below.
# --------------------------------------------------------------------------- #
_CURRENCY_CODES = {
    "USD", "USDOLLAR", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "HKD", "CNY",
    "CNH", "KRW", "TWD", "SGD", "INR", "BRL", "MXN", "ZAR", "SEK", "NOK", "DKK",
    "NZD", "ILS", "PLN", "THB", "IDR", "MYR", "PHP", "TRY", "CLP", "COP", "PEN",
}
# Sentinels that are non-equity on the TICKER ALONE: an empty/placeholder cell can
# never name an issuer, so no corroboration is possible or needed. Kept separate
# from _CURRENCY_CODES because a currency code CAN also be a real issuer's ticker
# (see _CURRENCY_NAME_RE below); a blank cell cannot.
_SENTINEL_TICKERS = {
    "", "-", "--", "—", "NAN", "NONE", "NULL", "<NA>", "N/A", "CASH",
}
# "NA" is ambiguous, not an unconditional sentinel: it is both the legacy
# missing-value literal AND a live listing (Nano Labs Ltd on Nasdaq, National
# Bank of Canada on TSX) — an unconditional match here silently dropped both
# real names' holdings rows. Name-corroborated like the currency-code branch
# below, never decided on the ticker alone. See PR #5936 / collectors/symbol_directory.py
# for the sibling defect this mirrors on the identity-roster side.
_AMBIGUOUS_SENTINEL_TICKERS = {"NA"}
_NON_EQUITY_TICKERS = _CURRENCY_CODES | _SENTINEL_TICKERS | _AMBIGUOUS_SENTINEL_TICKERS  # kept: legacy importers
# High-precision name patterns — kept tight to avoid flagging real issuers
# (e.g. "FutureFuel", "Cash America" are NOT matched: we anchor on cash-sleeve /
# currency / instrument phrasing, not bare substrings).
_NON_EQUITY_NAME_RE = re.compile(
    r"^\s*cash\b|cash\s*[&/+]|cash\s+and\b|cash\s+equiv|&\s*equivalent|"
    r"money\s*market|u\.?\s*s\.?\s*dollar\b|\bcurrency\b|cash\s*&\s*other|"
    r"\brepo\b|receivable|payable|net\s+other\s+asset|other\s+net\s+asset|"
    r"\bfx\s+forward|forward\s+contract|\bswap\b",
    re.IGNORECASE,
)
# An ISO-4217 code in the ticker is EVIDENCE of a currency line, never a verdict:
# real issuers carry currency-shaped tickers. Measured over all 55,612 rows of
# data/etf_holdings + data/holdings (2026-08-12), the bare-code and leading-code
# branches were dropping SIX REAL ISSUERS, 130 rows:
#   COP ConocoPhillips (SPY, RSP) · PEN Penumbra Inc. (MDY) · CNH Industrial NV
#   (MDY) · "EUR AU" European Lithium (LIT, 42 rows) · "INR AU" ioneer (LIT, 42)
#   · "PEN AU" Peninsula Energy (URA, 42).
# The last three are the sharper half: the `head in _CURRENCY_CODES` rule was
# written for INSTRUMENT suffixes ("USD CASH", "EUR FWD") but a Bloomberg foreign
# listing has the identical shape — "<CODE> <EXCHANGE>" — so an ASX lithium and
# uranium miner read as an FX line in the two funds built to hold exactly those.
# This is the failure direction the futures predicate (§6c m17) also refuses: a
# wrongly-dropped equity leaves NO trace in any output, and here not even in the
# store, because collectors.etf_holdings._normalize applies this predicate at
# WRITE time — the row is erased at ingest, not merely hidden at read.
#
# The discriminator is the name column, and on the live corpus it is clean: every
# genuine FX/cash line is named for the CURRENCY ("EURO", "SOUTH KOREA WON",
# "NEW TAIWAN DOLLAR", "DANISH KRONE"), every equity for its ISSUER. So a
# currency-coded ticker is non-equity only when the name corroborates it, or when
# the name is blank and nothing CAN corroborate it (R1's lesson, masterplan §6b:
# sponsors do file cash sleeves with an empty name column).
# CONSERVATISM. _CURRENCY_NAME_RE is anchored end-to-end, not a substring search,
# and is consulted ONLY for a ticker already matching a currency code. Both guards
# are load-bearing: "Dollar General", "Dollar Tree" and "The RealReal" carry
# currency WORDS, and a substring rule would drop all three the day one of them
# is filed under a currency-shaped ticker. Verified over the full corpus: 130 rows
# change verdict, all six issuers above, and ZERO rows newly dropped.
_CURRENCY_NAME_RE = re.compile(
    r"^[a-z.\s]{0,24}?(?:dollar|euro|pound|yen|yuan|renminbi|won|franc|krone|"
    r"krona|peso|rupee|rupiah|ringgit|baht|shekel|zloty|lira|rand|koruna|"
    r"forint|dirham|riyal|dinar|dong|sol|real)s?$",
    re.IGNORECASE,
)
# The second corroborating form: a cash/treasury token ANYWHERE in the name
# ("Euro Cash", "USD Cash Account", "JPY spot"). Deliberately a loose substring
# search where _CURRENCY_NAME_RE is anchored, because it is reachable ONLY after
# the ticker already matched a currency code — the two guards compose, and
# neither is safe alone. "Cash America International" (ticker CSH) never reaches
# here; if it ever traded under a currency-shaped ticker this rule would drop it,
# which is the residual risk accepted for catching the sponsor forms below.
_CURRENCY_CONTEXT_RE = re.compile(
    r"\b(?:cash|balance|deposit|account|spot|fx|forward|fwd|currency|"
    r"money\s*market|treasur\w+)\b",
    re.IGNORECASE,
)
# "<CCY> CASH" / "<CCY> FWD" — a currency code followed by an INSTRUMENT token is
# non-equity whatever the name says. A currency code followed by an EXCHANGE code
# ("EUR AU") is a real foreign listing. Enumerating the instrument tokens is what
# separates the two; the old rule could not tell them apart.
_CURRENCY_INSTRUMENT_RE = re.compile(
    r"^[A-Z]{3}[\s_-]+(?:CASH|FWD|FORWARD|SPOT|FX|CURRENCY|CCY|MM)\b")
# Sponsor cash-sleeve lines whose CASH MARKER IS THE TICKER and whose name column
# is empty/NaN, so neither the ticker set nor the name patterns above can see them.
# VanEck's form is "-USD CASH-" / "-EUR CASH-" / "-CZK CASH-": a LEADING HYPHEN
# (which no real equity ticker carries — the sponsor uses it precisely to mark a
# non-security line), an ISO-4217-shaped 3-letter code, and a CASH token. Matching
# on that STRUCTURE rather than on membership of _CURRENCY_CODES is deliberate:
# the live feeds carry CZK/TWD/IDR cash sleeves that the currency set does not
# list, and widening that set would also start flagging bare 3-letter tickers.
# Missing this form was the R1 defect (masterplan §6b): the cash line's share
# BALANCE (SMH: 28.5M "shares", ~10% of the fund's total share count, against
# $0.03B of value) sat inside the SUM-ratio denominator `active_changes_dir`
# uses, so a fund whose true scale was 1.0242 measured 0.9743 and EVERY
# constituent published a phantom +5.12% active change.
_CASH_SLEEVE_TICKER_RE = re.compile(r"^-\s*[A-Z]{3}[\s_-]*CASH\b[\s-]*$")
# Index-FUTURES overlay lines (masterplan §6c). A fund equitizes its uninvested
# cash with index futures so the sleeve tracks the benchmark, and the sponsor
# files that overlay as a HOLDING beside the equities. Its "shares" are a
# CONTRACT COUNT, so nothing the share-diff engine computes about it carries the
# meaning it carries for a stock — and the contract ROLLS every quarter, which
# is the same defect class R1 fixed for cash, arriving on the lifecycle path
# instead of the denominator. Measured on the live feeds 2026-08-12:
#   * BOTZ filed "NQM6 Index / NASDAQ 100 E-MINI JUN26" through 2026-06-15 and
#     "NQU6 Index / … SEP26" from 2026-06-16. The engine reads that rollover as
#     a full EXIT of a 0.43%-weight position PLUS a brand-new 0.44% one — the
#     two strongest signals the board publishes, both above min_position_pct,
#     manufactured quarterly out of a roll that moved no money. BOTZ and BUG are
#     in the shipped universe today, so this is a live defect, not a latent one.
#   * Between rolls the count still moves (BOTZ 28 -> 25 contracts on
#     2026-06-26), publishing as a -10.7% "manager trim" of a futures overlay.
#   * QQQ files the overlay as an offsetting PAIR, "NQM6" and "NQM6_", the second
#     carrying NEGATIVE shares (-900) and a negative weight; XOP's "IXPM6 / XAE
#     ENERGY JUN26" legs are negative-weight too. RSP's "LWEM6" is 1,220
#     contracts worth $208.7M — 0.226% of the fund, above min_position_pct.
#
# CONSERVATISM. The equity side is the binding constraint, not the futures side.
# "FutureFuel Corp" and "Option Care Health Inc" are real live holdings, so the
# name rule never keys on a bare "future"/"option" substring, and never on the
# singular "future" alone (Future plc is a listed issuer). It keys on the plural,
# on "index future(s)", on "future(s) contract", on the E-MINI product name, and
# on a contract-month token ("JUN26") — the forms the live files actually use.
# The ticker rule keys ONLY on the Bloomberg " Index" suffix, which no listed
# equity carries; it exists because R1's lesson was that a sponsor can put the
# marker in the ticker and leave the name column empty.
# DELIBERATELY REFUSED: a bare CME root+month+year ticker shape
# (^[A-Z]{2,4}[FGHJKMNQUVXZ]\d$, which would match NQM6/LWEM6/IXPM6 directly).
# It is indistinguishable from Latin-American local tickers — CMIG4 (Cemig) and
# BRKM5 (Braskem) are letters + a CME month code + a digit — and silently
# dropping a real equity is a far worse failure than keeping a futures line,
# because a dropped name leaves no trace in any output. Every futures row in the
# live corpus is already caught by name, so the shape rule buys nothing. Both
# rules were swept over all 55,612 rows of data/etf_holdings + data/holdings:
# 7 distinct hits, all genuine futures, zero real issuers flagged.
_FUTURES_NAME_RE = re.compile(
    r"\bfutures\b|\bindex\s+futures?\b|\bfutures?\s+contract|\be[\s-]?mini\b|"
    r"\bfut\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{2}\b",
    re.IGNORECASE,
)
_FUTURES_TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}\s+INDEX$")
# The SECOND form of the same defect: a government money-market SWEEP sleeve, or a
# T-bill held to park cash. Neither is caught above — the ticker is a real symbol
# (FGXXX, AGPXX, a CUSIP) and the name says neither "cash" nor "money market" — yet
# the row is a DOLLAR BALANCE, not a position: measured on the live feed, these
# lines carry shares EXACTLY equal to market_value (METV FGXXX 1,722,754.52 /
# 1,722,754.52; BLOK AGPXX 17,685,543.99 / 17,685,543.99), i.e. a $1-NAV fund. In
# METV that balance is 18.9% of the fund's TOTAL share count at 0.81% of its
# weight, and it sits inside the SUM-ratio denominator `active_changes_dir` uses,
# so the fund's measured scale was 1.4164 against a true 1.1688 and EVERY
# constituent published a phantom +21.18% active change (bar: 5%). Measured across
# the board: 14 rows in 14 funds change verdict, 13 funds' published scale moves,
# 6 of them at or over that 5% bar (table in research/ETF_DATA_SOURCES.md § W3).
#
# Anchored on the two vehicle families the live feeds actually carry plus the
# Treasury instrument names — NEVER on bare tokens. "BILL Holdings" (XSW/FINX/MDY),
# "Liquidity Services" (EBIZ) and "Treasury Wine Estates" are real issuers a loose
# `bill|liquidity|treasury` would silently delete. The `&amp;` alternative is
# load-bearing: the HTML-sourced Invesco rows arrive still escaped.
_CASH_EQUIV_NAME_RE = re.compile(
    r"government\s+obligations?\s+fund|"
    r"government\s+(?:&amp;|&|and)\s+agency\s+(?:portfolio|fund)|"
    r"\btreasury\s+(?:bill|note|bond)s?\b|\bt-bills?\b",
    re.IGNORECASE,
)
# Secondary, structural belt for a sweep vehicle we have not seen yet: Nasdaq's
# 5th-letter "X" marks a mutual fund, so a 5-letter all-alpha ticker ending in X
# is never a listed operating company. Required to co-occur with a cash-vehicle
# NAME token so that neither half can fire alone.
_MMF_TICKER_RE = re.compile(r"^[A-Z]{4}X$")
_MMF_NAME_TOKEN_RE = re.compile(
    r"\b(?:fund|portfolio|obligations?|treasury|government|govt|liquidity|reserves?)\b",
    re.IGNORECASE,
)
# Swap lines whose NAME cannot give them away. Roundhill files the same total-
# return swap two ways depending on the date: "21873S108 TRS 090827 GS" named
# "COREWEAVE, INC.-SWAP-GOLD-L" (the name patterns above catch it) and, on other
# dates, "21873S108 SWP" with the name column simply REPEATING the ticker — no
# issuer, no "swap". Measured on NCLD: the second form survived as a 16.38% and a
# 20.38% phantom equity constituent whose "shares" are swap units.
# The marker must be a TOKEN beside another token, never the whole ticker: TRS is
# TriMas Corp and SWP is a live symbol elsewhere, so a bare 3-letter ticker stays.
_DERIVATIVE_TOKENS = {"SWP", "SWAP", "TRS"}


def is_non_equity_holding(ticker, name: str = "") -> bool:
    """True if a holdings row is cash / FX / money-market / a derivative / an
    index-futures overlay / receivable — anything whose share count is a balance
    or a contract count, not an equity position. Used to weed the radar's
    erroneous near-zero-base blow-ups and phantom lifecycle rows.

    A currency-shaped TICKER is evidence, not a verdict: it decides the row only
    when the NAME corroborates it (or is blank, so nothing can). See the comment
    block above for the six real issuers the unqualified rule was erasing.
    """
    tk = str(ticker).strip().upper()
    nm = str(name).strip()
    # A blank-ish NAME carries no evidence either way. "nan"/"none"/"<na>" are what
    # str() leaves of a pandas missing value; the rest are literal missing-value
    # cells that now REACH us, because the parse sites pass keep_default_na=False
    # so a real 'NA' ticker survives — the name column stopped being pre-blanked
    # for us, so blank it here instead.
    if nm.lower() in ("nan", "none", "<na>", "n/a", "na", "null", "-", "--", "—"):
        nm = ""
    if tk in _SENTINEL_TICKERS:
        return True
    if tk in _AMBIGUOUS_SENTINEL_TICKERS:
        # "NA" — name-corroborated like the currency-code branch below, so
        # Nano Labs Ltd / National Bank of Canada survive as equities.
        if not nm:                                  # nothing can contradict it
            return True
        if _CURRENCY_NAME_RE.match(nm) or _CURRENCY_CONTEXT_RE.search(nm):
            return True
        # Deliberately NO `return False` here: fall through to the shared name
        # rules below (_NON_EQUITY_NAME_RE / _FUTURES_NAME_RE / _CASH_EQUIV_NAME_RE)
        # so ticker "NA" on a futures leg ("NASDAQ 100 E-MINI JUN26") or a cash
        # sleeve ("… GOVERNMENT OBLIGATIONS FUND") is still caught. An early
        # return would hand those back as equities — the one thing moving "NA"
        # out of the unconditional set must not cost us.
    if _CURRENCY_INSTRUMENT_RE.match(tk):           # e.g. "USD CASH", "EUR FWD"
        return True
    # Currency-shaped ticker is evidence, not a verdict. A name that
    # does not corroborate (COP, PEN, CNH, "EUR AU") is an equity.
    head = tk.split()[0] if tk.split() else ""
    if tk in _CURRENCY_CODES or head in _CURRENCY_CODES:
        if not nm:                                  # nothing can contradict it
            return True
        if (_CURRENCY_NAME_RE.match(nm)             # "EURO", "DANISH KRONE"
                or _CURRENCY_CONTEXT_RE.search(nm)  # "Euro Cash", "JPY spot"
                or _NON_EQUITY_NAME_RE.search(nm)):
            return True
        return False
    if _CASH_SLEEVE_TICKER_RE.match(tk):            # e.g. "-USD CASH-" (name NaN)
        return True
    if _FUTURES_TICKER_RE.match(tk):                # e.g. "NQU6 Index" (Bloomberg)
        return True
    parts = tk.split()
    if len(parts) > 1 and _DERIVATIVE_TOKENS & set(parts):   # e.g. "21873S108 SWP"
        return True
    if not nm:
        return False
    if _NON_EQUITY_NAME_RE.search(nm):
        return True
    if _FUTURES_NAME_RE.search(nm):                 # e.g. "… E-MINI SEP26"
        return True
    if _CASH_EQUIV_NAME_RE.search(nm):              # e.g. FGXXX / AGPXX / a T-bill
        return True
    return bool(_MMF_TICKER_RE.match(tk) and _MMF_NAME_TOKEN_RE.search(nm))


def drop_non_equity(df: pd.DataFrame) -> pd.DataFrame:
    """Filter cash/FX/derivative rows from a holdings snapshot. Resolves the name
    column across sponsors (etf_holdings: 'name'; ARK csv: 'company').

    PUBLIC because stored snapshots deliberately RETAIN these rows — the store is
    the raw sponsor filing, and every reader must weed it for itself. Readers that
    only ever look a ticker UP (`weights.get(t)` keyed by an independent equity
    universe) are inert against cash keys today, but the inertness is an accident
    of which strings sponsors happen to use: `CASH` is both a sentinel here and a
    live published ticker (Pathward Financial), so a sponsor filing its sleeve
    under that string would hand a real stock a cash weight. Call this instead of
    relying on the accident. Never resolve the name column by hand at a call site
    — that is what silently diverges when a new sponsor arrives.
    """
    if df is None or df.empty or "ticker" not in df.columns:
        return df
    ncol = next((c for c in df.columns if c.lower() in ("name", "company")), None)
    names = df[ncol].astype(str) if ncol else pd.Series("", index=df.index)
    keep = [not is_non_equity_holding(t, n)
            for t, n in zip(df["ticker"].astype(str), names)]
    return df[pd.Series(keep, index=df.index)]


_drop_non_equity = drop_non_equity          # legacy in-module alias


class HoldingsAdapter(Adapter):
    name = "holdings"
    group = "holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["holdings"]
        self.dir = config.ROOT / config.load()["storage"]["holdings_dir"]

    # holdings snapshots are written directly (one file per fund per day),
    # so fetch() returns {} and reports via raising on total failure.
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        results, errors = {}, []
        for ticker, spec in self.cfg["watchlist"].items():
            try:
                snap = self._fetch_fund(ticker, spec)
                if snap is not None and not snap.empty:
                    self._write_snapshot(ticker, snap)
                    results[ticker] = len(snap)
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{ticker}: {e}")
                log.warning("holdings %s failed: %s", ticker, e)
        if not results:
            raise RuntimeError(f"all watchlist funds failed: {errors}")
        # return a tiny summary series so the runner records freshness
        s = pd.DataFrame({"funds_ok": [len(results)]},
                         index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _write_snapshot(self, ticker: str, snap: pd.DataFrame) -> None:
        d = self.dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        snap_date = snap["as_of"].iloc[0] if "as_of" in snap.columns else str(date.today())
        snap.to_parquet(d / f"{snap_date}.parquet")

    def _fetch_fund(self, ticker: str, spec: dict) -> pd.DataFrame | None:
        sponsor = spec["sponsor"]
        fn = getattr(self, f"_fetch_{sponsor}", None)
        if fn is None:
            raise ValueError(f"no adapter for sponsor '{sponsor}'")
        return fn(ticker, spec)

    # --- sponsor adapters -------------------------------------------------------
    def _fetch_ark(self, ticker: str, spec: dict) -> pd.DataFrame:
        r = self.http_get(spec["url"], retries=self.cfg["retries"])
        # keep_default_na=False: 'NA' is a live listing (Nano Labs; National Bank of
        # Canada on TSX). na_values=[""] keeps blank -> NaN so dropna/to_numeric are unchanged.
        df = pd.read_csv(io.StringIO(r.text), keep_default_na=False, na_values=[""])
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.dropna(subset=["ticker"]) if "ticker" in df.columns else df
        keep = [c for c in ["date", "fund", "company", "ticker", "cusip",
                            "shares", "market_value_($)", "market_value",
                            "weight_(%)", "weight"] if c in df.columns]
        df = df[keep].rename(columns={"market_value_($)": "market_value",
                                      "weight_(%)": "weight"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(pd.to_datetime(df["date"].iloc[0]).date()) \
            if "date" in df.columns else str(date.today())
        return df

    def _fetch_coinshares(self, ticker: str, spec: dict) -> pd.DataFrame:
        # URL resolved by recon (see config holdings.watchlist.WGMI.url).
        url = spec.get("url", "")
        if not url:
            raise RuntimeError("WGMI holdings URL not configured yet")
        r = self.http_get(url, retries=self.cfg["retries"])
        df = pd.read_csv(io.StringIO(r.text), keep_default_na=False, na_values=[""])
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        share_col = next((c for c in df.columns if "share" in c or "quantity" in c), None)
        tick_col = next((c for c in df.columns if "ticker" in c or "symbol" in c), None)
        if not share_col or not tick_col:
            raise ValueError(f"unrecognized WGMI csv columns: {list(df.columns)}")
        df = df.rename(columns={share_col: "shares", tick_col: "ticker"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(date.today())
        return df.dropna(subset=["shares"])


def _weight_map(df: pd.DataFrame) -> pd.Series:
    """ticker -> weight_pct from a holdings snapshot (the weight column name varies
    by sponsor: weight_pct / weight / weight_(%) …). Used to recover the PRIOR
    weight of a fully-exited position, which is absent from the latest snapshot."""
    if df is None or df.empty or "ticker" not in df.columns:
        return pd.Series(dtype=float)
    wcol = next((c for c in df.columns if "weight" in c.lower()), None)
    if wcol is None:
        return pd.Series(dtype=float)
    w = pd.to_numeric(df[wcol].astype(str).str.replace(r"[,%$]", "", regex=True),
                      errors="coerce")
    return pd.Series(w.values, index=df["ticker"].astype(str)).groupby(level=0).last()


def active_changes_dir(d, window_d: int, *, min_base_frac: float = 1e-6,
                       include_lifecycle: bool = False) -> pd.DataFrame | None:
    """Flow-normalized share decisions from per-day snapshots in directory `d`.

    Isolates the manager's (or index's) actual share decisions from mechanical
    creation/redemption pass-through: expected_shares(t) = shares(t-1)·SO(t)/SO(t-1),
    where the fund SO ratio is proxied by the total share growth of positions
    common to both snapshots. Sponsor-agnostic, so any collector that writes
    snapshots with a `ticker`+`shares` schema (holdings/, etf_holdings/) reuses it.

    Two data-hygiene guards make the %-change trustworthy (every consumer — the
    radar, the dashboard panel, alerts — flows through here):
      1. cash/FX/derivative rows are dropped (is_non_equity_holding);
      2. a position whose expected base is a negligible fraction of the fund
         (< min_base_frac) is dropped, so a near-zero denominator can never
         explode the ratio (also kills placeholder contra-lines).

    `include_lifecycle` adds two RADAR-only row kinds whose % change is undefined
    (so they'd be noise in the plain alert path, which stays on continuing
    positions): brand-NEW positions (is_new) and full EXITS (is_exit, with the
    prior weight carried so conviction can be scored on it).
    """
    from pathlib import Path
    d = Path(d)
    if not d.exists():
        return None
    snaps = sorted(d.glob("*.parquet"))[-(window_d + 1):]
    if len(snaps) < 2:
        return None
    first_df = _drop_non_equity(pd.read_parquet(snaps[0]))
    last_df = _drop_non_equity(pd.read_parquet(snaps[-1]))
    first = first_df.set_index("ticker")["shares"]
    last = last_df.set_index("ticker")["shares"]
    # collapse any duplicate tickers, drop non-numeric residue
    first = pd.to_numeric(first, errors="coerce").groupby(level=0).sum()
    last = pd.to_numeric(last, errors="coerce").groupby(level=0).sum()
    common = first.index.intersection(last.index)
    if common.empty or first[common].sum() == 0:
        return None
    so_ratio = last[common].sum() / first[common].sum()
    expected = first * so_ratio
    diff = (last.reindex(expected.index) - expected).dropna()
    # align pct to diff's index — otherwise dividing by the full `expected` index
    # re-introduces fully-exited tickers as NaN rows (handled explicitly below).
    pct = 100 * diff / expected.reindex(diff.index).replace(0, pd.NA)
    out = pd.DataFrame({"active_share_chg": diff, "active_chg_pct": pct})
    # denominator guard: drop positions whose expected base is a negligible
    # share of the fund — their % is meaningless and prone to blow-ups.
    exp_pos = expected[expected > 0]
    if not exp_pos.empty:
        frac = expected.reindex(out.index).fillna(0.0) / exp_pos.sum()
        out = out[frac >= min_base_frac]
    out["is_new"], out["is_exit"], out["prior_weight_pct"] = False, False, float("nan")
    if include_lifecycle:
        # Brand-NEW positions — held now, absent a window ago. A manager INITIATING
        # a stake is the strongest "high interest" signal, but its % change is
        # undefined (no prior base), so is_new=True and downstream ranks it on the
        # full CURRENT weight (frac=1) instead of a meaningless ratio.
        new_last = last.reindex(last.index.difference(first.index)).dropna()
        new_last = new_last[new_last > 0]
        if len(new_last):
            out = pd.concat([out, pd.DataFrame({
                "active_share_chg": new_last, "active_chg_pct": float("nan"),
                "is_new": True, "is_exit": False, "prior_weight_pct": float("nan")})])
        # Full EXITS — held a window ago, gone now (manager fully sold out): the
        # strongest NEGATIVE signal. The position is absent from the latest snapshot
        # so we carry its PRIOR weight for conviction scoring (= −full weight).
        exit_first = first.reindex(first.index.difference(last.index)).dropna()
        exit_first = exit_first[exit_first > 0]
        if len(exit_first):
            pw = _weight_map(first_df).reindex(exit_first.index)
            out = pd.concat([out, pd.DataFrame({
                "active_share_chg": -exit_first, "active_chg_pct": -100.0,
                "is_new": False, "is_exit": True, "prior_weight_pct": pw},
                index=exit_first.index)])
    out["window_start"], out["window_end"] = snaps[0].stem, snaps[-1].stem
    return out.sort_values("active_chg_pct")


def active_changes(ticker: str, window_d: int | None = None) -> pd.DataFrame | None:
    """Flow-normalized manager decisions over the last N snapshots (ARK watchlist)."""
    cfg = config.load()["holdings"]
    window_d = window_d or cfg["active_change_window_d"]
    d = config.ROOT / config.load()["storage"]["holdings_dir"] / ticker
    return active_changes_dir(d, window_d)
