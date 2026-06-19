"""Theme → Binding Catalyst Binder — SCORECARD DIM 5 · DISPLAY-ONLY · LEAF.

directional:false — this module computes a DESCRIPTIVE, display-only proxy for the
presence of a binding fundamental catalyst per thematic basket. It does NOT score
expected forward returns, does NOT feed the conviction/recommendation engine, and
NOTHING in the scoring path imports it.

WHAT A "BINDING CATALYST" IS (and why we can only approximate it):
  In the doctrine, Dim-5 asks: has a KEY member (the basket leader by 60-day
  relative-strength) recently printed — or does it have imminent — a binding
  fundamental event: an earnings beat + guidance raise, a capex/contract
  announcement, or a product ramp. A true classifier for "beat+guide-up vs
  beat-guide-flat vs miss", a capex announcement, or a signed contract REQUIRES
  richer per-event structured data that is not currently available in the nightly
  store. The module docstring says so explicitly (see `confidence` field below).

WHAT WE SURFACE INSTEAD (best available proxies):
  1. has_recent_print — the leader reported an EPS beat (positive surprise_pct) in
     the last RECENT_WINDOW_DAYS calendar days, drawn from
     data/earnings/earnings.parquet:surprises_json (the same source the stock page
     reads). "Beat" = surprise_pct > 0; "strong beat" = surprise_pct >= STRONG_BEAT_PCT.
  2. nearest_earnings_date — the leader's next scheduled earnings date from the same
     parquet (next_date column). Imminent = within IMMINENT_DAYS calendar days.
  3. has_stockbrief_catalyst — if a precomputed AI brief exists for the leader in
     site/stockbrief/<leader>.json, we surface its catalysts[] list (LLM-extracted
     from public news + context) as a supplementary text signal. NOT scored — text
     context only. The brief may be absent (not all tickers have a precomputed brief).
  4. confidence is always "proxy" — never "confirmed". A "proxy" read means the
     system inferred the catalyst from available structured data, not from a
     validated beat+guide-up / capex / contract event parser.

LEADER SELECTION: the basket member with the highest 60-day relative-strength vs
the benchmark (SPY). Mirrors the RS logic in engine.group_flow (_setup gives the
closes + bench; we compute RS ourselves so this module has no external dep on the
scoring path). Falls back to the first active member if fewer than RS_MIN_HISTORY
trading days of history are available for all members.

DATA ACCESS: mirrors engine.theme_scoring and engine.catalyst_stock:
  - membership from data/baskets/membership.json (group_flow._setup's 'mem' key)
  - closes + bench from group_flow._setup() (same plane the theme_scoring engine uses)
  - earnings from data/earnings/earnings.parquet (same source as the stock page)
  - stockbriefs from site/stockbrief/<ticker>.json (same output as catalyst_stock)
  - config.ROOT / config.data_dir() / config.load()['storage']['site_dir'] — mirrors
    catalyst_stock.assemble_context()

PUBLIC API:
  theme_catalyst(region='us') -> dict[str, CatalystRecord]
  where CatalystRecord = {
      theme_id: str,
      leader: str,                 # basket leader ticker by RS
      leader_rs_60d: float|None,   # 60-day rel-strength vs bench (decimal)
      has_recent_print: bool,      # leader beat EPS within RECENT_WINDOW_DAYS
      recent_print_date: str|None, # ISO date of the latest beat (reported field)
      recent_print_surprise_pct: float|None,
      strong_beat: bool,           # surprise_pct >= STRONG_BEAT_PCT
      has_imminent_earnings: bool, # next earnings within IMMINENT_DAYS
      imminent_earnings_date: str|None,
      days_to_earnings: int|None,
      has_binding_catalyst: bool,  # True if has_recent_print OR has_imminent_earnings
      kind: str,                   # "recent_beat" | "imminent_earnings" | "both" | "none"
      brief_catalysts: list[str],  # from precomputed AI brief (display text only)
      confidence: "proxy",         # ALWAYS "proxy" — see docstring
      note: str,                   # human-readable caveat
  }

NEVER RAISES — missing/short data returns a NEUTRAL/empty-but-typed record.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypedDict

import pandas as pd

from engine import group_flow
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
RS_WINDOW_D: int = 60          # trading-day RS window for leader detection
RS_MIN_HISTORY: int = 30       # minimum trading days to compute RS; else first member
RECENT_WINDOW_DAYS: int = 45   # calendar days: a "recent" print
IMMINENT_DAYS: int = 21        # calendar days: an "imminent" earnings event
STRONG_BEAT_PCT: float = 5.0   # surprise_pct >= this = "strong beat"

_PROXY_NOTE = (
    "PROXY ONLY — a true beat+guide-up / capex / contract classifier requires "
    "richer per-event data not available in the nightly store. "
    "has_recent_print = EPS beat in last 45 days; has_imminent_earnings = next "
    "earnings within 21 days. Inspect the earnings details and AI brief catalysts "
    "for context. Never a scored forward-return signal."
)


# ---------------------------------------------------------------------------
# typed record
# ---------------------------------------------------------------------------
class CatalystRecord(TypedDict, total=False):
    theme_id: str
    leader: str | None
    leader_rs_60d: float | None
    has_recent_print: bool
    recent_print_date: str | None
    recent_print_surprise_pct: float | None
    strong_beat: bool
    has_imminent_earnings: bool
    imminent_earnings_date: str | None
    days_to_earnings: int | None
    has_binding_catalyst: bool
    kind: str
    brief_catalysts: list
    confidence: str
    note: str


def _neutral(theme_id: str) -> CatalystRecord:
    """Empty-but-typed neutral record — returned on any data shortfall."""
    return CatalystRecord(
        theme_id=theme_id,
        leader=None,
        leader_rs_60d=None,
        has_recent_print=False,
        recent_print_date=None,
        recent_print_surprise_pct=None,
        strong_beat=False,
        has_imminent_earnings=False,
        imminent_earnings_date=None,
        days_to_earnings=None,
        has_binding_catalyst=False,
        kind="none",
        brief_catalysts=[],
        confidence="proxy",
        note=_PROXY_NOTE,
    )


# ---------------------------------------------------------------------------
# earnings parquet loader (mirrors catalyst_stock._edgar_context pattern)
# ---------------------------------------------------------------------------
def _load_earnings_parquet(root: Path) -> pd.DataFrame | None:
    """Load data/earnings/earnings.parquet. Returns None on failure (never raises)."""
    p = root / "data" / "earnings" / "earnings.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("earnings.parquet load failed: %s", e)
        return None


def _parse_reported_date(s: str) -> date | None:
    """Parse 'm/d/yyyy' or 'yyyy-mm-dd' -> date. Returns None on failure."""
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _earnings_record(edf: pd.DataFrame, ticker: str, today: date) -> dict:
    """Extract the catalyst-relevant fields for one ticker from the earnings parquet.
    Returns a dict with keys: next_date, surprises, has_recent_print,
    recent_print_date, recent_print_surprise_pct, strong_beat,
    has_imminent_earnings, imminent_earnings_date, days_to_earnings.
    Never raises."""
    out = {
        "next_date": None, "surprises": [],
        "has_recent_print": False, "recent_print_date": None,
        "recent_print_surprise_pct": None, "strong_beat": False,
        "has_imminent_earnings": False, "imminent_earnings_date": None,
        "days_to_earnings": None,
    }
    if edf is None or ticker not in edf.index:
        return out
    try:
        row = edf.loc[ticker]
        if hasattr(row, "iloc") and getattr(row, "ndim", 1) > 1:
            row = row.iloc[0]

        # next earnings date
        nd_raw = row.get("next_date")
        if nd_raw and str(nd_raw).strip() not in ("", "nan", "None"):
            nd_raw = str(nd_raw).strip()
            if nd_raw and nd_raw != "nan":
                nd = _parse_reported_date(nd_raw)
                if nd is not None:
                    out["next_date"] = nd.isoformat()
                    delta = (nd - today).days
                    out["days_to_earnings"] = delta
                    if 0 <= delta <= IMMINENT_DAYS:
                        out["has_imminent_earnings"] = True
                        out["imminent_earnings_date"] = nd.isoformat()

        # recent beat
        surp_raw = row.get("surprises_json") or "[]"
        try:
            surprises = json.loads(surp_raw) if isinstance(surp_raw, str) else []
        except Exception:  # noqa: BLE001
            surprises = []
        out["surprises"] = surprises
        # surprises are most-recent-first in the stored parquet
        cutoff = today - timedelta(days=RECENT_WINDOW_DAYS)
        for s in surprises:
            rep = _parse_reported_date(str(s.get("reported") or ""))
            if rep is None:
                continue
            if rep >= cutoff:
                sp = s.get("surprise_pct")
                if sp is not None and float(sp) > 0:
                    out["has_recent_print"] = True
                    out["recent_print_date"] = rep.isoformat()
                    out["recent_print_surprise_pct"] = round(float(sp), 2)
                    out["strong_beat"] = float(sp) >= STRONG_BEAT_PCT
                    break   # most recent qualifying beat is enough
    except Exception as e:  # noqa: BLE001
        log.debug("earnings_record(%s) failed: %s", ticker, e)
    return out


# ---------------------------------------------------------------------------
# stockbrief loader (mirrors catalyst_stock.assemble_context pattern)
# ---------------------------------------------------------------------------
def _load_brief_catalysts(root: Path, site_dir: str, ticker: str) -> list[str]:
    """Load precomputed AI brief catalysts[] for a ticker. Returns [] if absent."""
    safe = ticker.replace("=", "_").replace("^", "_")
    p = root / site_dir / "stockbrief" / f"{safe}.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
        cats = d.get("catalysts") or []
        if isinstance(cats, list):
            return [str(c).strip() for c in cats if c and str(c).strip()][:5]
        return []
    except Exception as e:  # noqa: BLE001
        log.debug("brief_catalysts(%s) failed: %s", ticker, e)
        return []


# ---------------------------------------------------------------------------
# RS leader detection (mirrors group_flow._setup data plane)
# ---------------------------------------------------------------------------
def _basket_leader(members: list[dict], closes: pd.DataFrame,
                   bench: pd.Series, today_i: int) -> tuple[str | None, float | None]:
    """Return (leader_ticker, rs_60d) for the basket.
    RS = basket-member 60-day return minus bench 60-day return.
    Falls back to first active member (rs=None) on insufficient history.
    Never raises."""
    active = [m["ticker"] for m in members
              if m["ticker"] in closes.columns and not m.get("removed")]
    if not active:
        return None, None
    window_i = max(0, today_i - RS_WINDOW_D)
    best_ticker, best_rs = None, None
    for t in active:
        col = closes[t]
        try:
            v0 = col.iloc[window_i]
            v1 = col.iloc[today_i]
            b0 = bench.iloc[window_i]
            b1 = bench.iloc[today_i]
            if pd.isna(v0) or pd.isna(v1) or pd.isna(b0) or pd.isna(b1):
                continue
            if v0 == 0 or b0 == 0:
                continue
            n_valid = col.iloc[window_i: today_i + 1].notna().sum()
            if n_valid < RS_MIN_HISTORY:
                continue
            rs = float(v1 / v0 - 1) - float(b1 / b0 - 1)
            if best_rs is None or rs > best_rs:
                best_ticker, best_rs = t, rs
        except Exception:  # noqa: BLE001
            continue
    if best_ticker is None:
        # fallback: first active member, no RS
        return active[0], None
    return best_ticker, round(best_rs, 4)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def theme_catalyst(region: str = "us") -> dict[str, CatalystRecord]:
    """Return a binding-catalyst proxy record for every basket in the given region.

    Maps theme_id -> CatalystRecord (see module docstring for the full field spec).
    Returns {} (empty dict, not None) on catastrophic failures so callers can safely
    iterate without guards.

    directional:false — display context only, never a scored forward-return signal.
    """
    if region != "us":
        # Other regions do not yet have an earnings parquet or the same group_flow
        # setup. Return empty rather than fabricating records for unsupported regions.
        log.debug("theme_catalyst: region '%s' not yet supported — returning {}", region)
        return {}

    today = date.today()
    root = config.ROOT
    try:
        cfg_storage = config.load().get("storage", {})
    except Exception:  # noqa: BLE001
        cfg_storage = {}
    site_dir = cfg_storage.get("site_dir", "site")

    # load earnings parquet once (shared across all baskets)
    edf = _load_earnings_parquet(root)

    # load closes + bench from the same data plane theme_scoring uses
    try:
        s = group_flow._setup()
    except Exception as e:  # noqa: BLE001
        log.warning("theme_catalyst: group_flow._setup() failed (%s)", e)
        return {}
    if s is None:
        return {}

    closes = s["closes"]
    bench = s["bench"]
    idx = s["idx"]
    mem = s.get("mem") or {}
    bdict = mem.get("baskets") or {}
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]

    today_i = len(idx) - 1
    result: dict[str, CatalystRecord] = {}

    for bid, b in items:
        members = b.get("members") or []
        if not members:
            result[bid] = _neutral(bid)
            continue

        # find leader
        leader, leader_rs = _basket_leader(members, closes, bench, today_i)
        rec = _neutral(bid)
        rec["theme_id"] = bid
        rec["leader"] = leader
        rec["leader_rs_60d"] = leader_rs

        if leader is None:
            result[bid] = rec
            continue

        # earnings-based catalyst proxy
        er = _earnings_record(edf, leader, today)
        rec["has_recent_print"] = er["has_recent_print"]
        rec["recent_print_date"] = er["recent_print_date"]
        rec["recent_print_surprise_pct"] = er["recent_print_surprise_pct"]
        rec["strong_beat"] = er["strong_beat"]
        rec["has_imminent_earnings"] = er["has_imminent_earnings"]
        rec["imminent_earnings_date"] = er["imminent_earnings_date"]
        rec["days_to_earnings"] = er["days_to_earnings"]

        # derive has_binding_catalyst and kind
        rp = er["has_recent_print"]
        ie = er["has_imminent_earnings"]
        rec["has_binding_catalyst"] = rp or ie
        if rp and ie:
            rec["kind"] = "both"
        elif rp:
            rec["kind"] = "recent_beat"
        elif ie:
            rec["kind"] = "imminent_earnings"
        else:
            rec["kind"] = "none"

        # supplementary: AI brief catalysts (display text only)
        rec["brief_catalysts"] = _load_brief_catalysts(root, site_dir, leader)

        result[bid] = rec

    return result
