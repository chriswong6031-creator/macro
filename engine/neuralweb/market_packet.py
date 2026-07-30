"""engine.neuralweb.market_packet — Live Market State Packet for the brain's grounding turn.

WHAT THIS IS
------------
A compact, freshness-stamped, cross-asset snapshot of the dashboard's OWN state,
assembled from artifacts that are already on disk and prepended to the user's
turn so the model answers from real numbers rather than memory.  It replaces the
thin nightly prose of ``brain_gateway._grounding_digest`` (whose master_brief /
world_state extraction is ported here verbatim, caps included) with a structured
packet that says WHEN each number was true.

PROVENANCE DISCIPLINE (the load-bearing rule)
---------------------------------------------
This module AGGREGATES.  It ORIGINATES nothing.

* Every number it prints was computed by an existing engine or builder and is
  read back off disk unchanged — the only arithmetic here is presentational
  (normalizing a yield-index print to percent whichever units the feed used —
  see _yield_pct_pair, units are feed-dependent — a change in basis points, a
  mean of index change percents) plus a handful of THRESHOLD comparisons over
  those same numbers.  No new signal, no fused score, no probability, no ranking, no
  forecast.  The deterministic FLAGS are shape observations ("these two things
  moved together, here are the exact numbers") — they are display tier, they
  never gate anything, and each one carries the figures that fired it so the
  reader can check the claim.
* No network.  No writes.  No clock in any payload: ``datetime`` is used only to
  compare an artifact's own as-of stamp against now for staleness and event age,
  never hashed, stored, or rendered as a fact.
* Honesty is the product.  Every rendered section starts with its own as-of
  stamp, and the header states whether the tape is live, delayed, or last
  session's close.  A block whose source is missing or corrupt is silently
  OMITTED (with an internal note in ``packet["gaps"]``) — never rendered with a
  borrowed or implied stamp, never back-filled from a neighbour.
* The EVENTS wire carries headlines, timestamps and salience ONLY.  House kill
  TI-R5 forbids authored effect chains / beneficiary lists in brain feeds, so no
  effect, beneficiary, or "what it means" field is read or rendered here even
  when the source item happens to carry one.
* No numeric confidence ever reaches the prompt: an engine's QUALITATIVE word
  ("medium") is passed through, a float is dropped, because a decimal next to the
  word "confidence" reads to a model as a calibrated probability and none of
  these reads are that.

SOURCES (each block independent, each fail-soft)
-----------------------------------------------
Live dir (see ``_live_dir`` — env override, then the VPS public live dir, then
the repo's ``site/live``): quotes.json, breadth.json, market_drivers.json,
shock_state.json, risk_state.json, wires.json, basket_pulse.json.
Repo: site/master_brief.json (else data/regime/master_brief.json),
data/neuralweb/world_state.json, data/rates_command/latest.json,
site/vol/regime.json, data/crossasset/latest.json, and a final wires fallback at
data/marketing/press/wires.json.

DESIGN
------
Pure module: stdlib only, no gateway imports, no side effects.  ``build_packet``
and ``digest`` never raise.  ``digest`` caches on the (path, mtime) tuple of every
source plus the budget, with a 60 s ceiling — the same mtime-cache idiom as
``engine.neuralweb.doctrine`` and ``brain_gateway._load_brain_config``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

PACKET_VERSION = 1
DEFAULT_CHAR_BUDGET = 4200

# ---------------------------------------------------------------------------
# Live-dir resolution ladder
# ---------------------------------------------------------------------------
# On the production VPS the live JSONs are NOT under the repo checkout: the press
# / quote daemons publish them into a served public dir. Same ladder as
# scripts.notify_turn_events (_SITE_LIVE) and marketing_fastlane_daemon's wires
# sink, so the brain reads the SAME bytes the site serves.
_LIVE_DIR_ENV = "MACRO_LIVE_DIR"
_VPS_LIVE_DIR = Path("/var/lib/macro-live/public/live")


def _live_dir(root: Path) -> Path:
    """Resolve the live-artifact directory. Never raises.

    (a) ``$MACRO_LIVE_DIR`` when set (unconditional — an explicit operator
        override, matching scripts.notify_turn_events), else
    (b) the VPS public live dir when it EXISTS, else
    (c) ``root/site/live`` (repo checkout / dev / tests).
    """
    try:
        env = os.environ.get(_LIVE_DIR_ENV)
        if env and env.strip():
            return Path(env.strip())
        if _VPS_LIVE_DIR.is_dir():
            return _VPS_LIVE_DIR
    except Exception:  # noqa: BLE001
        pass
    return root / "site" / "live"


# ---------------------------------------------------------------------------
# Tape universe + labels
# ---------------------------------------------------------------------------

_INDEX_SYMS: tuple[tuple[str, str], ...] = (
    ("^GSPC", "SPX"), ("^IXIC", "NDX"), ("^DJI", "DJI"), ("^RUT", "RUT"),
)
# ETF stand-ins, honestly labeled: the same-origin display snapshot carries
# SPY/QQQ rather than ^GSPC/^IXIC. An ETF is not the index, so it renders under
# its OWN name, and only when its index's row is absent.
_INDEX_ETF_FALLBACK: tuple[tuple[str, tuple[str, str]], ...] = (
    ("^GSPC", ("SPY", "SPY")), ("^IXIC", ("QQQ", "QQQ")),
)
_FUTURES_SYMS: tuple[tuple[str, str], ...] = (
    ("ES=F", "ES"), ("NQ=F", "NQ"), ("YM=F", "YM"), ("RTY=F", "RTY"),
)
_VIX_SYM = "^VIX"
_COMMODITY_SYMS: tuple[tuple[str, str], ...] = (
    ("CL=F", "WTI"), ("BZ=F", "Brent"), ("GC=F", "Gold"),
    ("HG=F", "Copper"), ("SI=F", "Silver"),
)
_DOLLAR_SYM = "DX-Y.NYB"
_CRYPTO_SYMS: tuple[tuple[str, str], ...] = (("BTC-USD", "BTC"), ("ETH-USD", "ETH"))

# Yield-index UNITS ARE FEED-DEPENDENT (W1 diagnosis, 2026-07-29): the spark
# path behind site/live/quotes.json delivers the yield percent DIRECTLY (^TNX
# price 4.622 == 4.622% — probed live from the VPS), while the /ws/tape relay
# streams the CBOE ×10 index convention (42.5 == 4.25%). Mirror the browser's
# scale detection (templates/live.js tnxPct(), in production since 2026-07-24):
# a row with either value above _YIELD_X10_THRESHOLD is ×10 units, normalize
# both ÷10 (pair-level — see _yield_pct_pair). No US tenor has yielded >15%
# since 1985, and a ×10 print of even a 2% yield is 20 — the bands can't
# overlap in any plausible regime. level_pct = normalized price;
# change_bp = (normalized price - normalized prevClose) * 100.
_YIELD_SYMS: tuple[tuple[str, str], ...] = (
    ("^IRX", "3M"), ("^FVX", "5Y"), ("^TNX", "10Y"), ("^TYX", "30Y"),
)
_YIELD_X10_THRESHOLD = 15.0
_BP_PER_PCT = 100.0
_FRONT_TENORS = ("3M", "5Y")     # first present wins
_LONG_TENORS = ("30Y", "10Y")    # first present wins

# Sanity gate — a junk index print (a stale 0, a 10x glitch, a 200bp "move")
# must never reach the prompt as a curve fact.
TENOR_MIN_PCT = 0.0        # exclusive
TENOR_MAX_PCT = 20.0       # exclusive
TENOR_MAX_ABS_BP = 60.0    # inclusive

# ---------------------------------------------------------------------------
# Flag thresholds (module constants so the arithmetic is auditable in one place)
# ---------------------------------------------------------------------------

CURVE_STEEPEN_BP = 3.0     # (long - front) above this = steepening
CURVE_FLATTEN_BP = -3.0    # (long - front) below this = flattening
CURVE_BEAR_BP = 2.0        # the leg that rose enough to make it a BEAR move
CURVE_BULL_BP = -2.0       # the leg that fell enough to make it a BULL move

INDEX_MEAN_DOWN_PCT = -0.8     # mean index change% below this = stocks down
LONG_BOND_UP_BP = 4.0          # long tenor above this = long bonds down
DOLLAR_GOLD_UP_PCT = 0.5       # both above this = dollar+gold up together
OIL_SHOCK_ABS_PCT = 4.0        # |WTI change%| above this = oil shock day
VIX_SPIKE_PCT = 15.0           # VIX change% above this = vol spike

QUOTES_DELAYED_MIN = 25.0      # max used delayMin above this = delayed basis
QUOTES_STALE_MIN = 45.0        # quotes older than this in an OPEN session = STALE
EVENTS_MAX_AGE_H = 12.0        # a wire item older than this is not "live"
EVENTS_MAX_ITEMS = 3
EVENTS_TEXT_CHARS = 90

LEADERS_PER_SIDE = 3           # strongest N and weakest N groups
LEADERS_MAX_ABS_PCT = 40.0     # |EW day move| above this = junk print, dropped

_CURVE_GLOSS: dict[str, str] = {
    "bear_steepener": "bear steepener (long end selling off while the front end holds)",
    "bull_steepener": "bull steepener (front end rallying faster than the long end)",
    "bear_flattener": "bear flattener (front end selling off faster than the long end)",
    "bull_flattener": "bull flattener (long end rallying while the front end holds)",
}

# Cross-asset trend slugs -> plain words. A canonical bilingual map lives in
# engine.cross_asset_trend._NAME_LABEL, but importing it would drag lib.config /
# store into a module that must stay stdlib-pure, so the plain-word forms are
# restated here; an unknown slug degrades to underscores-as-spaces.
_CROSSASSET_LABELS: dict[str, str] = {
    "equity_us": "US equity",
    "equity_sm": "small caps",
    "equity_intl": "international equity",
    "equity_em": "EM equity",
    "credit_hy": "high yield",
    "gold": "gold",
    "silver": "silver",
    "copper": "copper",
    "oil": "crude oil",
    "dollar": "dollar",
    "bond_10y": "10Y Treasuries",
    "duration": "long Treasuries",
    "crypto": "bitcoin",
}

# Basket/sector slugs -> plain words for the LEADERS line. Same reason as
# _CROSSASSET_LABELS above: the canonical names live in the baskets-membership
# registry (and its site-sector-pulse mirror), but opening a SECOND artifact
# to label a line the first one already fully populates would triple this block's
# read cost, and importing the basket registry would drag lib.config into a module
# that must stay stdlib-pure. Compacted from the canonical `name` field, so an
# equal-weight GICS sector reads as "<sector> sector" and never collides with the
# thematic basket next to it ("energy sector" vs "energy complex"). An unlisted
# slug degrades to underscores-as-spaces rather than dropping the group.
_BASKET_LABELS: dict[str, str] = {
    # US GICS sectors, equal-weight
    "us_sector_tech": "tech sector",
    "us_sector_financials": "financials sector",
    "us_sector_health": "health care sector",
    "us_sector_discretionary": "discretionary sector",
    "us_sector_comm": "communications sector",
    "us_sector_industrials": "industrials sector",
    "us_sector_staples": "staples sector",
    "us_sector_energy": "energy sector",
    "us_sector_utilities": "utilities sector",
    "us_sector_realestate": "real estate sector",
    "us_sector_materials": "materials sector",
    # Thematic baskets
    "mag7": "mega-cap tech",
    "ai_infra": "AI infrastructure",
    "ai_software": "AI software",
    "ai_agents": "AI agents",
    "ai_neoclouds": "AI neoclouds",
    "ai_semiconductors": "AI semiconductors",
    "semicap_equipment": "semiconductor equipment",
    "memory_storage": "memory & storage",
    "non_ai_software": "non-AI software",
    "non_ai_tech": "non-AI tech & hardware",
    "cybersecurity": "cybersecurity",
    "quantum_computing": "quantum computing",
    "robotics_automation": "robotics & automation",
    "space_economy": "space economy",
    "defense": "defense & aerospace",
    "reshoring": "reshoring & industrial capex",
    "industrial_distribution": "industrial distribution",
    "power_grid": "power & grid buildout",
    "data_center_power": "data-center power",
    "nuclear_power": "nuclear & SMR power",
    "uranium_miners": "uranium & nuclear fuel",
    "critical_minerals": "critical minerals & rare earths",
    "energy_complex": "energy complex",
    "housing": "housing chain",
    "travel": "travel & experiences",
    "retail": "retail",
    "defensives": "defensives",
    "regional_banks": "regional banks",
    "payments_fintech": "payments & fintech",
    "insurance": "insurance & brokers",
    "managed_care": "managed care & insurers",
    "big_pharma": "big pharma",
    "obesity_glp1": "GLP-1 & obesity",
    "crypto": "crypto & digital assets",
    "crypto_rails": "crypto rails",
}

# The pulse's OWN graded-mode field (TS-R1 honest-delay law in
# scripts/build_basket_pulse.py) as a plain phrase. 'live' adds nothing the
# section stamp does not already say; an unknown mode renders NOTHING rather than
# leaking a raw slug into the prompt.
_LEADERS_MODE_NOTE: dict[str, str] = {
    "live": "",
    "delayed": "delayed quotes",
    "last_rth": "last full session",
    "eod": "last close",
}

_BASIS_LIVE = "live"
_BASIS_DELAYED = "≈15-min delayed"
_BASIS_CLOSED = "last session's tape (market closed)"
_BASIS_NO_TAPE = "nightly desk state, no live tape"

_STALE_PREFIX = "STALE — treat as last known, not current: "

_HEADER = (
    "[CURRENT DASHBOARD STATE — {basis}; stamps per section. Ground your answer in "
    "this, but NEVER name files or fields — give the plain read. Numbers here are "
    "the desk's own reads.]"
)

# Section render order == budget priority. Dropping runs from the BOTTOM up;
# HEADER and TAPE are never dropped when present. SHOCK is not in the
# commissioned list — an ACTIVE shock de-escalation window is rare and material,
# so it sits with the flags it qualifies rather than at the droppable tail.
_SECTION_ORDER: tuple[str, ...] = (
    "HEADER", "TAPE", "CURVE", "FLAGS", "SHOCK", "EVENTS", "DRIVERS",
    "RATES", "VOL", "BREADTH", "LEADERS", "CROSSASSET", "DESK", "WATCH",
)
_NEVER_DROP: frozenset[str] = frozenset({"HEADER", "TAPE"})


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

_MINUS = "−"   # U+2212 MINUS SIGN — the house glyph for a negative print
_SEP = " · "   # " · "


def _f(v: object) -> float | None:
    """float(v) for a real number only. bool, None, str, NaN, inf -> None."""
    if v is None or isinstance(v, bool):
        return None
    if not isinstance(v, (int, float)):
        return None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _trim(s: str) -> str:
    """Drop trailing zeros from a FIXED-POINT string only. Guard: a bare rstrip
    would turn the integer '30' into '3'."""
    return s.rstrip("0").rstrip(".") if "." in s else s


def _num(v: object, nd: int = 2) -> str | None:
    """Unsigned number, nd decimals, trailing zeros dropped. 18.21 -> '18.21'."""
    f = _f(v)
    if f is None:
        return None
    s = _trim(f"{round(f, nd):.{nd}f}")
    return "0" if s in ("", "-0", "-") else s


def _signed(v: object, nd: int = 1, unit: str = "") -> str | None:
    """Signed number with the house minus glyph, trailing zeros dropped.

    +1.7% / -1.7% (U+2212) / 0% when the value rounds away at this precision —
    an unsigned zero is the honest print for 'moved less than we show'.
    """
    f = _f(v)
    if f is None:
        return None
    r = round(f, nd)
    body = _trim(f"{abs(r):.{nd}f}")
    if body in ("", "0"):
        return "0" + unit
    return ("+" if r > 0 else _MINUS) + body + unit


def _parse_ts(raw: object) -> datetime | None:
    """Parse the as-of shapes these artifacts use, tz-aware UTC. Never raises.

    '2026-07-27T22:32:09.883727+00:00' | '2026-07-27T21:19:20Z' |
    '2026-07-27 22:31:49 UTC' | '2026-07-28'
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith(" UTC"):
        s = s[:-4].strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stamp(raw: object) -> str:
    """Short UTC stamp for a section header. A timestamp -> '07-27 22:32Z';
    a date-only as-of keeps its full 'YYYY-MM-DD' (a nightly date without a year
    is ambiguous). Unparseable -> the raw string, trimmed."""
    dt = _parse_ts(raw)
    if dt is None:
        return str(raw).strip()[:24] if raw else ""
    if isinstance(raw, str) and len(raw.strip()) <= 10:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%m-%d %H:%MZ")


def _read_json(path: Path, gaps: list[str], tag: str) -> object | None:
    """Read + parse one artifact. Missing or corrupt -> None + an internal gap
    note. Never raises, never warns at INFO+ (this runs on every brain turn)."""
    try:
        if not path.exists():
            gaps.append(f"{tag}: absent")
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"{tag}: unreadable ({type(exc).__name__})")
        log.debug("market_packet: %s unreadable (%s)", path, exc)
        return None


def _clip(v: object, cap: int) -> str:
    """Trim one free-text field to its cap, as the nightly digest does today."""
    return str(v).strip()[:cap]


def _flatten_item(x: object, cap: int) -> str:
    """One watch/conflict/forward item -> plain text under `cap`.

    forward_watch rows are DICTS ({date, label, kind, note}); a raw dict repr
    would leak field names into the prompt and burn the budget, so the known
    keys are joined in reading order and anything else degrades to its string
    values.
    """
    if isinstance(x, dict):
        head = " ".join(
            str(x[k]).strip() for k in ("date", "label") if str(x.get(k, "")).strip()
        )
        note = str(x.get("note", "")).strip()
        if head and note:
            return f"{head} — {note}"[:cap]
        if head or note:
            return (head or note)[:cap]
        vals = [str(v).strip() for v in x.values() if isinstance(v, str) and v.strip()]
        return " — ".join(vals)[:cap] if vals else ""
    return _clip(x, cap)


def _humanize(slug: object) -> str:
    return str(slug).replace("_", " ").strip()


# ---------------------------------------------------------------------------
# Curve shape — pure function over two change-in-bp legs
# ---------------------------------------------------------------------------

def curve_shape(front_bp: float | None, long_bp: float | None) -> str | None:
    """Name the curve move from the front and long change-in-bp legs.

    Steepening when (long - front) > CURVE_STEEPEN_BP, flattening when it is
    below CURVE_FLATTEN_BP; the bear/bull prefix says WHICH leg drove it (a rise
    of more than CURVE_BEAR_BP = bear, a fall of more than |CURVE_BULL_BP| =
    bull). A move with no qualifying driver leg is not named at all — the flag
    exists only in its four fully-specified forms. When both prefixes qualify the
    bear test wins (source order), which is the conventional read: a leg selling
    off names the move.
    """
    if front_bp is None or long_bp is None:
        return None
    spread = long_bp - front_bp
    if spread > CURVE_STEEPEN_BP:
        if long_bp > CURVE_BEAR_BP:
            return "bear_steepener"
        if front_bp < CURVE_BULL_BP:
            return "bull_steepener"
        return None
    if spread < CURVE_FLATTEN_BP:
        if front_bp > CURVE_BEAR_BP:
            return "bear_flattener"
        if long_bp < CURVE_BULL_BP:
            return "bull_flattener"
        return None
    return None


# ---------------------------------------------------------------------------
# Block builders — one per source, each fail-soft in isolation
# ---------------------------------------------------------------------------

def _tape_block(quotes: dict, gaps: list[str]) -> dict | None:
    """Present-only cross-asset rows + the max measured delay of the rows used."""
    qs = quotes.get("quotes")
    if not isinstance(qs, dict) or not qs:
        gaps.append("tape: no quotes")
        return None

    delays: list[float] = []

    def row(sym: str, label: str) -> dict | None:
        q = qs.get(sym)
        if not isinstance(q, dict):
            return None
        chg = _f(q.get("changePct"))
        px = _f(q.get("price"))
        if chg is None and px is None:
            return None
        d = _f(q.get("delayMin"))
        if d is not None:
            delays.append(d)
        return {"sym": sym, "label": label, "change_pct": chg, "price": px,
                "basis": q.get("basis")}

    def group(pairs: tuple[tuple[str, str], ...]) -> list[dict]:
        return [r for r in (row(s, lab) for s, lab in pairs) if r]

    indices = group(_INDEX_SYMS)
    _present = {r["sym"] for r in indices}
    for _idx_sym, (_etf_sym, _etf_label) in _INDEX_ETF_FALLBACK:
        if _idx_sym not in _present:
            _r = row(_etf_sym, _etf_label)
            if _r:
                indices.append(_r)

    block: dict = {
        "indices": indices,
        "futures": group(_FUTURES_SYMS),
        "vix": row(_VIX_SYM, "VIX"),
        "commodities": group(_COMMODITY_SYMS),
        "dollar": row(_DOLLAR_SYM, "DXY"),
        "crypto": group(_CRYPTO_SYMS),
    }
    if not any(block.get(k) for k in block):
        gaps.append("tape: no tracked symbols present")
        return None
    block["max_delay_min"] = max(delays) if delays else None
    block["asof"] = quotes.get("asof")
    return block


def _yield_pct_pair(px: float, prev: float | None) -> tuple[float, float | None]:
    """Normalize a yield-index price/prevClose PAIR to percent, whichever units
    the feed used (feed-dependent — see _YIELD_SYMS comment): 4.622 -> 4.622%,
    46.22 -> 4.622%. Detection is PAIR-LEVEL — either value above the threshold
    marks the whole row ×10 — because per-value detection fabricates a giant
    Δbp when a ×10 low-yield print straddles 15 (px 14.5 / prev 15.5 is a real
    -10bp move at 1.45%, not -1320bp). Same >15 threshold the browser has used
    since 2026-07-24 (live.js tnxPct)."""
    x10 = px > _YIELD_X10_THRESHOLD or (
        prev is not None and prev > _YIELD_X10_THRESHOLD)
    scale = 10.0 if x10 else 1.0
    return px / scale, (prev / scale if prev is not None else None)


def _curve_block(quotes: dict, gaps: list[str]) -> dict | None:
    """Yahoo yield indexes -> tenor level_pct / change_bp, each sanity-gated."""
    qs = quotes.get("quotes")
    if not isinstance(qs, dict) or not qs:
        return None
    tenors: dict[str, dict] = {}
    for sym, tenor in _YIELD_SYMS:
        q = qs.get(sym)
        if not isinstance(q, dict):
            continue
        px = _f(q.get("price"))
        if px is None:
            continue
        level, prev = _yield_pct_pair(px, _f(q.get("prevClose")))
        chg_bp = (level - prev) * _BP_PER_PCT if prev is not None else None
        if not (TENOR_MIN_PCT < level < TENOR_MAX_PCT):
            gaps.append(f"curve: {tenor} level {level:.3f}% outside sanity band — dropped")
            continue
        if chg_bp is not None and abs(chg_bp) > TENOR_MAX_ABS_BP:
            gaps.append(f"curve: {tenor} move {chg_bp:.1f}bp outside sanity band — dropped")
            continue
        tenors[tenor] = {"level_pct": level, "change_bp": chg_bp}
    if not tenors:
        return None

    def pick(order: tuple[str, ...]) -> str | None:
        for t in order:
            if tenors.get(t, {}).get("change_bp") is not None:
                return t
        return None

    return {"tenors": tenors, "asof": quotes.get("asof"),
            "front_tenor": pick(_FRONT_TENORS), "long_tenor": pick(_LONG_TENORS)}


def _flags_block(tape: dict | None, curve: dict | None) -> list[dict]:
    """Deterministic shape flags. Each carries the exact numbers that fired it.
    Only FIRED flags are emitted."""
    flags: list[dict] = []
    tenors = (curve or {}).get("tenors") or {}
    front_t = (curve or {}).get("front_tenor")
    long_t = (curve or {}).get("long_tenor")
    front_bp = tenors.get(front_t, {}).get("change_bp") if front_t else None
    long_bp = tenors.get(long_t, {}).get("change_bp") if long_t else None

    name = curve_shape(front_bp, long_bp)
    if name:
        flags.append({
            "name": name, "front_tenor": front_t, "front_bp": front_bp,
            "long_tenor": long_t, "long_bp": long_bp,
            "spread_bp": (long_bp or 0.0) - (front_bp or 0.0),
        })

    idx = [r["change_pct"] for r in (tape or {}).get("indices", [])
           if r.get("change_pct") is not None]
    if idx and long_bp is not None:
        mean_pct = sum(idx) / len(idx)
        if mean_pct < INDEX_MEAN_DOWN_PCT and long_bp > LONG_BOND_UP_BP:
            flags.append({"name": "stocks_and_long_bonds_both_down",
                          "index_mean_pct": mean_pct, "n_indices": len(idx),
                          "long_tenor": long_t, "long_bp": long_bp})

    def chg(group: str, sym: str) -> float | None:
        for r in (tape or {}).get(group, []):
            if r.get("sym") == sym:
                return r.get("change_pct")
        return None

    dxy = ((tape or {}).get("dollar") or {}).get("change_pct")
    gold = chg("commodities", "GC=F")
    if dxy is not None and gold is not None \
            and dxy > DOLLAR_GOLD_UP_PCT and gold > DOLLAR_GOLD_UP_PCT:
        flags.append({"name": "dollar_and_gold_both_up",
                      "dxy_pct": dxy, "gold_pct": gold})

    wti = chg("commodities", "CL=F")
    if wti is not None and abs(wti) > OIL_SHOCK_ABS_PCT:
        flags.append({"name": "oil_shock_day", "wti_pct": wti,
                      "direction": "up" if wti > 0 else "down"})

    vix = (tape or {}).get("vix") or {}
    vix_pct = vix.get("change_pct")
    if vix_pct is not None and vix_pct > VIX_SPIKE_PCT:
        flags.append({"name": "vix_spike", "vix_pct": vix_pct,
                      "vix_level": vix.get("price")})
    return flags


def _breadth_block(raw: object, gaps: list[str]) -> dict | None:
    if not isinstance(raw, dict):
        return None
    tiers_raw = raw.get("tiers")
    if not isinstance(tiers_raw, list) or not tiers_raw:
        gaps.append("breadth: no tiers")
        return None
    tiers: list[dict] = []
    for t in tiers_raw:
        if not isinstance(t, dict):
            continue
        row = {"key": str(t.get("key") or ""), "univ": str(t.get("univ") or ""),
               "adv": _f(t.get("adv")), "dec": _f(t.get("dec")),
               "adv_pct": _f(t.get("adv_pct"))}
        if row["key"] == "large":
            row["nh"] = _f(t.get("nh"))
            row["nl"] = _f(t.get("nl"))
        if row["adv_pct"] is not None:
            tiers.append(row)
    if not tiers:
        gaps.append("breadth: no usable tier")
        return None
    return {"tiers": tiers, "session": str(raw.get("session") or ""),
            "delay_min": _f(raw.get("delay_min")), "asof": raw.get("asof")}


def _leaders_block(raw: object, gaps: list[str]) -> dict | None:
    """Today's strongest / weakest groups off the intraday basket pulse.

    SOURCE CHOICE — the intraday basket pulse (basket_pulse.v1, ~14 KB), the
    smallest artifact on disk that actually answers "what is leading". The four
    alternatives were rejected on grain or weight:

    * site-sector-pulse (47 KB) carries the same 46 groups but NO 1-day move — its
      numbers are a composite score, a cross-sectional rank and a 5-day relative,
      none of which is "today".
    * site-flow-leaders (68 KB) and site-leader-radar (326 KB) are TICKER grain,
      not group grain.
    * site-us-standouts is 1.8 MB and its ``leaders`` key is also per-ticker.
    * The nightly baskets snapshot (14 KB) is group grain but, like sector-pulse,
      carries score/rank/label only — no day move.

    The pulse also happens to be the one candidate that is BOTH git-tracked under
    the repo's live dir (so a dev checkout resolves it) and published into the VPS
    public live dir by scripts/vps_live_orchestrator's snapshot lane (so production
    resolves it) — it rides the module's existing ``_live_dir`` ladder with no new
    path convention, and check_vps_live_health holds it to a 15-minute freshness
    bound on weekdays. It is NOT in config/synapse.yml: the whole live plane is
    unregistered there, so declaring it is a governance decision, not this block's.

    WHAT IS AND IS NOT COMPUTED HERE. ``live_ew_chg_pct`` is the builder's own
    equal-weight member day move; this function only SELECTS from it (the same
    idiom as ``_events_block`` sorting the wire by the wire's own salience) and
    THRESHOLD-gates a junk print. The sort key is the printed move rather than the
    artifact's ``tape_rank`` because rank ships null on the eod fallback path,
    and because sorting on the number we print keeps the order and the figures
    from ever disagreeing. A group whose member coverage fell under the builder's
    floor already arrives as an honest null and is skipped, never imputed.

    Zero is neither half: a group has to be strictly above 0 to read as leading
    and strictly below to read as lagging, so an all-green tape renders the up
    half alone rather than promoting three flat groups to "down".
    """
    if not isinstance(raw, dict):
        return None
    rows_raw = raw.get("baskets")
    if not isinstance(rows_raw, list) or not rows_raw:
        gaps.append("leaders: no baskets")
        return None
    rows: list[dict] = []
    for b in rows_raw:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        chg = _f(b.get("live_ew_chg_pct"))
        if not bid or chg is None:
            continue
        if abs(chg) > LEADERS_MAX_ABS_PCT:
            gaps.append(f"leaders: {bid} move {chg:.1f}% outside sanity band — dropped")
            continue
        rows.append({"id": bid, "label": _BASKET_LABELS.get(bid, _humanize(bid)),
                     "change_pct": chg})
    if not rows:
        gaps.append("leaders: no group with a usable move")
        return None

    up = sorted((r for r in rows if r["change_pct"] > 0),
                key=lambda r: -r["change_pct"])[:LEADERS_PER_SIDE]
    down = sorted((r for r in rows if r["change_pct"] < 0),
                  key=lambda r: r["change_pct"])[:LEADERS_PER_SIDE]
    if not up and not down:
        gaps.append("leaders: every group flat")
        return None

    mode = str(raw.get("mode") or "").strip()
    return {"up": up, "down": down, "mode": mode,
            "mode_note": _LEADERS_MODE_NOTE.get(mode, ""),
            # as_of_quotes is the tape the moves were measured on; as_of_utc is
            # the build. The quote stamp is the one that says when the numbers
            # were true, so it leads.
            "asof": raw.get("as_of_quotes") or raw.get("as_of_utc")}


def _drivers_block(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("primary_label") or "").strip()
    direction = str(raw.get("direction") or "").strip()
    if not label and not direction:
        return None
    # A QUALITATIVE confidence word only. A float here would print as
    # "confidence: 0.75" and read as a calibrated probability, which it is not.
    conf_raw = raw.get("confidence")
    conf = str(conf_raw).strip() if isinstance(conf_raw, str) else ""
    if conf and _f_from_text(conf) is not None:
        conf = ""
    return {"primary_label": label, "primary_label_zh": str(raw.get("primary_label_zh") or ""),
            "direction": direction, "direction_zh": str(raw.get("direction_zh") or ""),
            "confidence": conf, "confidence_zh": str(raw.get("confidence_zh") or ""),
            "verdict": str(raw.get("verdict") or "").strip(),
            "verdict_zh": str(raw.get("verdict_zh") or ""),
            "window_d": _f(raw.get("window_d")), "asof": raw.get("asof")}


def _f_from_text(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _shock_block(raw: object) -> dict | None:
    """Only an ACTIVE de-escalation window is a fact about right now."""
    if not isinstance(raw, dict) or not raw.get("active"):
        return None
    return {"note": str(raw.get("note") or "").strip(),
            "since": str(raw.get("since") or "").strip(),
            "expires": str(raw.get("expires") or "").strip()}


def _rates_block(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    board = raw.get("board") if isinstance(raw.get("board"), dict) else {}
    rp = board.get("rate_path_row") if isinstance(board.get("rate_path_row"), dict) else {}
    infl = board.get("inflation_row") if isinstance(board.get("inflation_row"), dict) else {}
    risk = board.get("risk_row") if isinstance(board.get("risk_row"), dict) else {}
    path = rp.get("implied_path") if isinstance(rp.get("implied_path"), dict) else {}

    # Top-level curve_regime_key is the commissioned field but ships null in the
    # current vintage; the populated copy lives on the risk row, and a
    # pre-humanized label is the last resort.
    curve_key = raw.get("curve_regime_key") or risk.get("curve_regime_key")
    curve = _humanize(curve_key) if curve_key else str(
        risk.get("curve_regime_label_en") or "").strip().lower()

    block = {
        "asof": rp.get("asof") or raw.get("asof"),
        "policy_rate": _f(rp.get("policy_rate")),
        "implied_m3": _f(path.get("m3")),
        "curve_regime": curve or "",
        # Desk-canonical zh curve label (熊市变陡 family) — rendered on zh turns so
        # the model reuses the desk's own translation instead of inventing one.
        "curve_regime_zh": str(risk.get("curve_regime_label_zh") or "").strip(),
        "breakeven_10y": _f(infl.get("breakeven_10y")),
        "term_premium_dir": str(risk.get("term_premium_dir") or "").strip(),
    }
    if not any(v not in (None, "") for k, v in block.items() if k != "asof"):
        return None
    return block


def _vol_block(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    snap = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else None
    if not snap:
        return None
    block = {"asof": snap.get("asof") or raw.get("asof"),
             "regime": str(snap.get("regime") or "").strip(),
             "vix": _f(snap.get("vix")),
             "ts_slope_state": str(snap.get("ts_slope_state") or "").strip(),
             "move": _f(snap.get("move"))}
    if not any(v not in (None, "") for k, v in block.items() if k != "asof"):
        return None
    return block


def _crossasset_block(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    fav_raw = raw.get("favored")
    favored = [str(x) for x in fav_raw[:3]] if isinstance(fav_raw, list) else []
    block = {"asof": raw.get("asof") or raw.get("date"),
             "regime": str(raw.get("regime") or "").strip(),
             "favored": favored,
             "correlation": str(raw.get("correlation") or "").strip()}
    if not block["regime"] and not favored and not block["correlation"]:
        return None
    return block


def _desk_block(root: Path, gaps: list[str]) -> tuple[dict | None, dict | None]:
    """master_brief (site copy first, then the data/regime copy) + the world_state
    regime label. Same keys, same order and same truncation caps as the nightly
    digest this replaces."""
    mb: dict | None = None
    for p in (root / "site" / "master_brief.json",
              root / "data" / "regime" / "master_brief.json"):
        raw = _read_json(p, [], "master_brief")
        if isinstance(raw, dict):
            mb = raw
            break
    desk: dict | None = None
    watch: dict | None = None
    if mb is not None:
        asof = mb.get("state_asof") or mb.get("generated_at") or ""
        reads: list[tuple[str, str]] = []
        for key, label in (("regime_read", "Regime"), ("summary", "Read"),
                           ("rotation_check", "Rotation"), ("forward_read", "Forward")):
            v = mb.get(key)
            if isinstance(v, str) and v.strip():
                reads.append((label, _clip(v, 380)))
        conflicts = mb.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            joined = "; ".join(_flatten_item(x, 110) for x in conflicts[:4])
            if joined.strip("; "):
                reads.append(("Conflicts", joined))
        if reads:
            desk = {"asof": asof, "reads": reads}
        w_lines: list[tuple[str, str]] = []
        for key, label in (("watch_items", "Watch"), ("forward_watch", "Ahead")):
            v = mb.get(key)
            if isinstance(v, list) and v:
                joined = "; ".join(_flatten_item(x, 110) for x in v[:4])
                if joined.strip("; "):
                    w_lines.append((label, joined))
        if w_lines:
            watch = {"asof": asof, "lines": w_lines}
    else:
        gaps.append("master_brief: absent")

    ws = _read_json(root / "data" / "neuralweb" / "world_state.json", gaps, "world_state")
    if isinstance(ws, dict):
        reg = ws.get("regime")
        lab = None
        ws_asof = ""
        if isinstance(reg, dict):
            # quad_name first: the original chain's `label` is the raw code "Q1",
            # which is meaningless to a reader and a banned slug on any surface.
            lab = (reg.get("quad_name") or reg.get("label") or reg.get("state")
                   or reg.get("verdict") or reg.get("headline"))
            ws_asof = str(reg.get("asof") or ws.get("asof") or "").strip()
        elif isinstance(reg, str) and reg.strip():
            lab = reg.strip()
            ws_asof = str(ws.get("asof") or "").strip()
        if lab:
            entry = ("Cross-asset regime", _clip(lab, 160))
            if desk is None:
                # No master_brief: this block stands on the world_state's OWN
                # as-of, never on a blank stamp.
                desk = {"asof": ws_asof, "reads": [entry]}
            else:
                desk["reads"].append(entry)
    return desk, watch


def _events_block(raw: object, now: datetime, gaps: list[str]) -> dict | None:
    """Live news wire, headline + stamp + salience ONLY (TI-R5: no authored
    effect or beneficiary field is read here). Top N fresh items by salience
    then recency."""
    if not isinstance(raw, dict):
        return None
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        gaps.append("events: empty wire")
        return None
    rows: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("en") or "").strip()
        ts = _parse_ts(it.get("ts"))
        if not text or ts is None:
            continue
        age_h = (now - ts).total_seconds() / 3600.0
        if age_h > EVENTS_MAX_AGE_H or age_h < -1.0:
            continue
        sal = _f(it.get("salience"))
        rows.append({"id": str(it.get("id") or ""), "ts": ts,
                     "hhmm": ts.strftime("%H:%M"),
                     "en": text, "zh": str(it.get("zh") or ""),
                     "salience": sal if sal is not None else 0.0,
                     "corroboration": it.get("corroboration")
                     or it.get("corroboration_class"),
                     "source_name": str(it.get("source_name") or ""),
                     "class": str(it.get("class") or "")})
    if not rows:
        gaps.append("events: no item inside the freshness window")
        return None
    rows.sort(key=lambda r: (-r["salience"], -r["ts"].timestamp()))
    return {"items": rows[:EVENTS_MAX_ITEMS]}


# ---------------------------------------------------------------------------
# build_packet
# ---------------------------------------------------------------------------

def build_packet(root: Path) -> dict:
    """Assemble the packet from whatever is on disk. Never raises.

    Every block is independent: a missing or corrupt source removes THAT block
    and records a note in ``packet["gaps"]``; it never degrades a neighbour and
    never leaves a block rendered under a borrowed stamp.
    """
    packet: dict = {"version": PACKET_VERSION, "gaps": []}
    gaps: list[str] = packet["gaps"]
    try:
        live = _live_dir(root)
        now = datetime.now(timezone.utc)

        quotes = _read_json(live / "quotes.json", gaps, "quotes")
        tape = curve = None
        if isinstance(quotes, dict):
            try:
                tape = _tape_block(quotes, gaps)
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"tape: build failed ({type(exc).__name__})")
            try:
                curve = _curve_block(quotes, gaps)
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"curve: build failed ({type(exc).__name__})")

        risk = _read_json(live / "risk_state.json", gaps, "risk_state")
        session_open: bool | None = None
        risk_stale = False
        if isinstance(risk, dict):
            sess = risk.get("session") if isinstance(risk.get("session"), dict) else {}
            if isinstance(sess.get("open"), bool):
                session_open = sess["open"]
            risk_stale = bool(risk.get("stale"))
            packet["session"] = {
                "open": session_open,
                "local_time": str(sess.get("local_time") or "").strip(),
                "stale": risk_stale,
                "stale_reason": str(risk.get("stale_reason") or "").strip(),
            }

        # ---- staleness law -------------------------------------------------
        if tape is None:
            packet["basis"] = _BASIS_NO_TAPE
        elif risk_stale or session_open is False:
            packet["basis"] = _BASIS_CLOSED
        else:
            md = tape.get("max_delay_min")
            packet["basis"] = (_BASIS_DELAYED if md is not None and md > QUOTES_DELAYED_MIN
                               else _BASIS_LIVE)
        packet["stale_warn"] = False
        if tape is not None and packet["basis"] != _BASIS_CLOSED:
            qdt = _parse_ts(tape.get("asof"))
            if qdt is not None and (now - qdt).total_seconds() / 60.0 > QUOTES_STALE_MIN:
                packet["stale_warn"] = True

        if tape:
            packet["tape"] = tape
        if curve:
            packet["curve"] = curve
        try:
            flags = _flags_block(tape, curve)
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"flags: build failed ({type(exc).__name__})")
            flags = []
        if flags:
            packet["flags"] = flags

        for key, path, builder in (
            ("breadth", live / "breadth.json", lambda r: _breadth_block(r, gaps)),
            ("leaders", live / "basket_pulse.json", lambda r: _leaders_block(r, gaps)),
            ("drivers", live / "market_drivers.json", _drivers_block),
            ("shock", live / "shock_state.json", _shock_block),
            ("rates", root / "data" / "rates_command" / "latest.json", _rates_block),
            ("vol", root / "site" / "vol" / "regime.json", _vol_block),
            ("crossasset", root / "data" / "crossasset" / "latest.json", _crossasset_block),
        ):
            try:
                block = builder(_read_json(path, gaps, key))
                if block:
                    packet[key] = block
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"{key}: build failed ({type(exc).__name__})")

        # Wire rail: live dir first, then the repo dev/test sink.
        try:
            wires = None
            for p in (live / "wires.json",
                      root / "data" / "marketing" / "press" / "wires.json"):
                wires = _read_json(p, [], "wires")
                if isinstance(wires, dict):
                    break
            if isinstance(wires, dict):
                block = _events_block(wires, now, gaps)
                if block:
                    packet["events"] = block
            else:
                gaps.append("wires: absent")
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"events: build failed ({type(exc).__name__})")

        try:
            desk, watch = _desk_block(root, gaps)
            if desk:
                packet["desk"] = desk
            if watch:
                packet["watch"] = watch
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"desk: build failed ({type(exc).__name__})")
    except Exception as exc:  # noqa: BLE001
        log.debug("market_packet: build_packet failed (%s)", exc)
        gaps.append(f"packet: build failed ({type(exc).__name__})")
    return packet


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _row_text(r: dict) -> str:
    """'SPX −1.7%' — change only; a level instrument also shows its level."""
    chg = _signed(r.get("change_pct"), 1, "%")
    if r.get("sym") == _VIX_SYM:
        lvl = _num(r.get("price"), 1)
        if lvl and chg:
            return f"{r['label']} {lvl} ({chg})"
        if lvl:
            return f"{r['label']} {lvl}"
    if chg is None:
        lvl = _num(r.get("price"), 2)
        return f"{r['label']} {lvl}" if lvl else ""
    return f"{r['label']} {chg}"


def _render_tape(p: dict) -> str:
    tape = p["tape"]
    groups: list[str] = []
    for key in ("indices", "futures"):
        rows = [t for t in (_row_text(r) for r in tape.get(key, [])) if t]
        if rows:
            groups.append(_SEP.join(rows))
    if tape.get("vix"):
        t = _row_text(tape["vix"])
        if t:
            groups.append(t)
    rows = [t for t in (_row_text(r) for r in tape.get("commodities", [])) if t]
    if rows:
        groups.append(_SEP.join(rows))
    if tape.get("dollar"):
        t = _row_text(tape["dollar"])
        if t:
            groups.append(t)
    rows = [t for t in (_row_text(r) for r in tape.get("crypto", [])) if t]
    if rows:
        groups.append(_SEP.join(rows))
    if not groups:
        return ""
    prefix = _STALE_PREFIX if p.get("stale_warn") else ""
    return (f"{prefix}TAPE ({_stamp(tape.get('asof'))}, {p.get('basis', '')}): "
            + " | ".join(groups))


def _render_curve(p: dict) -> str:
    curve = p["curve"]
    tenors = curve.get("tenors") or {}
    bp_parts: list[str] = []
    lvl_parts: list[str] = []
    for _sym, tenor in _YIELD_SYMS:
        t = tenors.get(tenor)
        if not t:
            continue
        bp = _signed(t.get("change_bp"), 1)
        if bp is not None:
            bp_parts.append(f"{tenor} {bp}")
        lvl = _num(t.get("level_pct"), 3)
        if lvl:
            lvl_parts.append(f"{tenor} {lvl}%")
    # A tenor with no prior close has no move to report — never let a LEVEL ride
    # under a "Δbp" header. With no move anywhere, the levels are the honest line.
    if bp_parts:
        parts, unit = bp_parts, "Δbp"
    elif lvl_parts:
        parts, unit = lvl_parts, "level"
    else:
        return ""
    line = f"CURVE ({_stamp(curve.get('asof'))}, {unit}): " + _SEP.join(parts)
    for f in p.get("flags", []):
        if f["name"] in _CURVE_GLOSS:
            line += " → " + _CURVE_GLOSS[f["name"]]
            break
    return line


def _flag_text(f: dict) -> str:
    name = f["name"]
    if name == "stocks_and_long_bonds_both_down":
        return (f"stocks and long bonds down together (indices "
                f"{_signed(f.get('index_mean_pct'), 1, '%')} avg, "
                f"{f.get('long_tenor')} {_signed(f.get('long_bp'), 1, 'bp')})")
    if name == "dollar_and_gold_both_up":
        return (f"dollar and gold both up (DXY {_signed(f.get('dxy_pct'), 1, '%')}, "
                f"Gold {_signed(f.get('gold_pct'), 1, '%')})")
    if name == "oil_shock_day":
        return f"oil shock day (WTI {_signed(f.get('wti_pct'), 1, '%')})"
    if name == "vix_spike":
        lvl = _num(f.get("vix_level"), 1)
        tail = f", now {lvl}" if lvl else ""
        return f"volatility spike (VIX {_signed(f.get('vix_pct'), 1, '%')}{tail})"
    return ""


def _render_flags(p: dict) -> str:
    # curve_shape already reads on the CURVE line — never print a flag twice.
    texts = [t for t in (_flag_text(f) for f in p.get("flags", [])
                         if f["name"] not in _CURVE_GLOSS) if t]
    if not texts:
        return ""
    stamp = _stamp((p.get("tape") or {}).get("asof"))
    head = f"FLAGS ({stamp}): " if stamp else "FLAGS: "
    return head + _SEP.join(texts)


def _render_shock(p: dict) -> str:
    s = p["shock"]
    window = " → ".join(x for x in (s.get("since"), s.get("expires")) if x)
    note = s.get("note") or "shock de-escalation window active"
    return f"SHOCK WINDOW ({window or 'active'}): {_clip(note, 200)}"


def _zh(p: dict) -> bool:
    """True when this render pass targets Chinese. The flag is stamped onto a
    SHALLOW COPY by render_digest (never the caller's dict); zh rendering is
    deliberately narrow — only fields whose Chinese the DESK already computed
    (drivers labels, wire item zh, the curve-regime label) switch, so the model
    reuses canonical desk vocabulary instead of re-translating. Everything else
    stays English and the LANGUAGE directive handles it."""
    return p.get("_render_lang") == "zh"


def _render_events(p: dict) -> str:
    items = p["events"].get("items") or []
    zh = _zh(p)
    parts: list[str] = []
    for it in items:
        text = (it.get("zh") or it["en"]) if zh else it["en"]
        if len(text) > EVENTS_TEXT_CHARS:
            text = text[:EVENTS_TEXT_CHARS - 1].rstrip() + "…"
        parts.append(f"{it['hhmm']} UTC {text}")
    return "EVENTS (live wire): " + _SEP.join(parts) if parts else ""


def _render_drivers(p: dict) -> str:
    d = p["drivers"]
    zh = _zh(p)
    label = (d.get("primary_label_zh") or d.get("primary_label")) if zh else d.get("primary_label")
    direction = (d.get("direction_zh") or d.get("direction")) if zh else d.get("direction")
    conf = (d.get("confidence_zh") or d.get("confidence")) if zh else d.get("confidence")
    verdict = (d.get("verdict_zh") or d.get("verdict")) if zh else d.get("verdict")
    body = " — ".join(x for x in (label, direction) if x)
    tail: list[str] = []
    if conf:
        tail.append(f"置信度: {conf}" if zh else f"desk confidence: {conf}")
    if verdict:
        tail.append(f"归因: {verdict}" if zh else f"attribution: {verdict}")
    stamp = _stamp(d.get("asof"))
    win = _num(d.get("window_d"), 0)
    head = f"DRIVERS ({stamp}{f', {win}d window' if win else ''}): "
    return head + body + (f" ({'; '.join(tail)})" if tail else "")


def _render_rates(p: dict) -> str:
    r = p["rates"]
    parts: list[str] = []
    pol = _num(r.get("policy_rate"), 2)
    if pol:
        parts.append(f"policy {pol}%")
    m3 = _num(r.get("implied_m3"), 2)
    if m3:
        parts.append(f"implied path m3 {m3}%")
    if r.get("curve_regime"):
        curve = (r.get("curve_regime_zh") or r["curve_regime"]) if _zh(p) else r["curve_regime"]
        parts.append(f"curve: {curve}")
    be = _num(r.get("breakeven_10y"), 2)
    if be:
        parts.append(f"10Y breakeven {be}%")
    if r.get("term_premium_dir"):
        parts.append(f"term premium {r['term_premium_dir']}")
    if not parts:
        return ""
    return f"RATES DESK ({_stamp(r.get('asof'))}): " + _SEP.join(parts)


def _render_vol(p: dict) -> str:
    v = p["vol"]
    parts: list[str] = []
    vix = _num(v.get("vix"), 2)
    if vix:
        parts.append(f"VIX {vix}")
    if v.get("ts_slope_state"):
        parts.append(f"futures {v['ts_slope_state']}")
    mv = _num(v.get("move"), 1)
    if mv:
        parts.append(f"MOVE {mv}")
    head = f"VOL ({_stamp(v.get('asof'))}): "
    if v.get("regime") and parts:
        return head + f"{v['regime']} — " + ", ".join(parts)
    if v.get("regime"):
        return head + v["regime"]
    return head + ", ".join(parts) if parts else ""


def _render_breadth(p: dict) -> str:
    b = p["breadth"]
    tiers = b.get("tiers") or []
    parts: list[str] = []
    nh_nl = ""
    for t in tiers:
        name = t.get("univ") or _humanize(t.get("key"))
        pct = _num(t.get("adv_pct"), 0)
        if pct is None:
            continue
        if t.get("key") == "large":
            adv, dec = _num(t.get("adv"), 0), _num(t.get("dec"), 0)
            detail = f" ({adv} adv / {dec} dec)" if adv and dec else ""
            parts.append(f"{name} {pct}% advancing{detail}")
            nh, nl = _num(t.get("nh"), 0), _num(t.get("nl"), 0)
            if nh is not None and nl is not None:
                nh_nl = f"{nh} new highs / {nl} new lows"
        else:
            parts.append(f"{name} {pct}%")
    if nh_nl:
        parts.append(nh_nl)
    if not parts:
        return ""
    stamp = _stamp(b.get("asof"))
    sess = b.get("session")
    head = f"BREADTH ({', '.join(x for x in (stamp, sess) if x)}): "
    return head + _SEP.join(parts)


def _render_leaders(p: dict) -> str:
    """'LEADERS (07-27 19:38Z, last full session): up — … | down — …'

    Either half may be absent (an all-green or all-red tape); with both absent the
    section renders "" rather than a promise it cannot keep. The head mirrors
    BREADTH's stamp+qualifier join, and falls back to the bare 'LEADERS: ' form
    that FLAGS / DESK READ use when the source carries no as-of at all.
    """
    ld = p["leaders"]

    def half(rows: list[dict]) -> str:
        parts: list[str] = []
        for r in rows:
            pct = _signed(r.get("change_pct"), 1, "%")
            if pct:
                parts.append(f"{r['label']} {pct}")
        return _SEP.join(parts)

    halves = [f"{word} — {body}" for word, body in
              (("up", half(ld.get("up") or [])), ("down", half(ld.get("down") or [])))
              if body]
    if not halves:
        return ""
    bits = ", ".join(x for x in (_stamp(ld.get("asof")), ld.get("mode_note") or "") if x)
    head = f"LEADERS ({bits}): " if bits else "LEADERS: "
    return head + " | ".join(halves)


def _render_crossasset(p: dict) -> str:
    c = p["crossasset"]
    parts: list[str] = []
    if c.get("regime"):
        parts.append(c["regime"])
    fav = [_CROSSASSET_LABELS.get(s, _humanize(s)) for s in c.get("favored", [])]
    if fav:
        parts.append("favored: " + ", ".join(fav))
    if c.get("correlation"):
        parts.append(f"correlation {c['correlation']}")
    if not parts:
        return ""
    return f"CROSS-ASSET ({_stamp(c.get('asof'))}): " + _SEP.join(parts)


def _render_desk(p: dict) -> str:
    d = p["desk"]
    stamp = _stamp(d.get("asof"))
    lines = [f"DESK READ ({stamp})" if stamp else "DESK READ"]
    lines += [f"{label}: {text}" for label, text in d.get("reads", [])]
    return "\n".join(lines) if len(lines) > 1 else ""


def _render_watch(p: dict) -> str:
    w = p["watch"]
    lines = w.get("lines") or []
    if not lines:
        return ""
    stamp = _stamp(w.get("asof"))
    head = f"WATCH ({stamp}): " if stamp else "WATCH: "
    out = [head + (lines[0][1] if lines[0][0] == "Watch"
                   else f"{lines[0][0]}: {lines[0][1]}")]
    out += [f"{label}: {text}" for label, text in lines[1:]]
    return "\n".join(out)


_RENDERERS: dict[str, object] = {
    "TAPE": ("tape", _render_tape),
    "CURVE": ("curve", _render_curve),
    "FLAGS": ("flags", _render_flags),
    "SHOCK": ("shock", _render_shock),
    "EVENTS": ("events", _render_events),
    "DRIVERS": ("drivers", _render_drivers),
    "RATES": ("rates", _render_rates),
    "VOL": ("vol", _render_vol),
    "BREADTH": ("breadth", _render_breadth),
    "LEADERS": ("leaders", _render_leaders),
    "CROSSASSET": ("crossasset", _render_crossasset),
    "DESK": ("desk", _render_desk),
    "WATCH": ("watch", _render_watch),
}


def render_digest(packet: dict, char_budget: int = DEFAULT_CHAR_BUDGET,
                  lang: str = "en") -> str:
    """Compact plain text for prompt injection. "" when the packet has no content.

    Sections render in _SECTION_ORDER; when the text exceeds ``char_budget``
    whole sections are dropped from the BOTTOM of that order up. HEADER and TAPE
    are never dropped, and a header with nothing under it renders as "" rather
    than an empty promise.

    ``lang='zh'`` switches ONLY the desk-precomputed Chinese fields (see _zh);
    the flag rides a shallow copy so a caller-held packet is never mutated.
    """
    if not isinstance(packet, dict):
        return ""
    if lang == "zh":
        packet = dict(packet)
        packet["_render_lang"] = "zh"
    sections: list[tuple[str, str]] = []
    try:
        for name in _SECTION_ORDER:
            if name == "HEADER":
                continue
            key, fn = _RENDERERS[name]
            if not packet.get(key):
                continue
            try:
                text = fn(packet)
            except Exception as exc:  # noqa: BLE001
                log.debug("market_packet: %s render failed (%s)", name, exc)
                continue
            if text and text.strip():
                sections.append((name, text))
    except Exception as exc:  # noqa: BLE001
        log.debug("market_packet: render_digest failed (%s)", exc)
        return ""
    if not sections:
        return ""

    header = _HEADER.format(basis=packet.get("basis") or _BASIS_NO_TAPE)
    kept = [("HEADER", header)] + sections
    try:
        budget = int(char_budget)
    except (TypeError, ValueError):
        budget = DEFAULT_CHAR_BUDGET

    def total(rows: list[tuple[str, str]]) -> int:
        return len("\n".join(t for _n, t in rows))

    while total(kept) > budget:
        idx = next((i for i in range(len(kept) - 1, -1, -1)
                    if kept[i][0] not in _NEVER_DROP), None)
        if idx is None:
            break
        kept.pop(idx)
    if len(kept) <= 1:
        return ""
    return "\n".join(t for _n, t in kept)


# ---------------------------------------------------------------------------
# digest() — build + render behind an mtime cache with a 60 s ceiling
# ---------------------------------------------------------------------------

_CACHE_TTL_S = 60.0
_CACHE: dict[tuple, tuple[str, float]] = {}
_CACHE_LOCK = threading.Lock()

# Relative to the LIVE dir.
_LIVE_SOURCES: tuple[str, ...] = (
    "quotes.json", "breadth.json", "market_drivers.json",
    "shock_state.json", "risk_state.json", "wires.json", "basket_pulse.json",
)
# Relative to root.
_ROOT_SOURCES: tuple[str, ...] = (
    "site/master_brief.json", "data/regime/master_brief.json",
    "data/neuralweb/world_state.json", "data/rates_command/latest.json",
    "site/vol/regime.json", "data/crossasset/latest.json",
    "data/marketing/press/wires.json",
)


def _clock() -> float:
    """Monotonic seconds. Indirected so a test can age the cache."""
    return time.monotonic()


def _cache_key(root: Path, char_budget: int, lang: str = "en") -> tuple:
    """(root, budget) plus the (path, mtime) pair of every source. A source that
    APPEARS or vanishes changes the key as surely as an edited one, because a
    missing file is keyed as None rather than skipped."""
    pairs: list[tuple[str, float | None]] = []
    try:
        live = _live_dir(root)
        paths = [live / n for n in _LIVE_SOURCES] + [root / n for n in _ROOT_SOURCES]
        for p in paths:
            try:
                pairs.append((str(p), p.stat().st_mtime))
            except OSError:
                pairs.append((str(p), None))
    except Exception:  # noqa: BLE001
        pass
    return (str(root), int(char_budget), str(lang), tuple(pairs))


def digest(root: Path, char_budget: int = DEFAULT_CHAR_BUDGET,
           lang: str = "en") -> str:
    """build_packet + render_digest behind a cache. Never raises.

    Cached on the source mtimes and the budget, with a 60 s ceiling so a clock-
    dependent line (staleness, event age) can never be served indefinitely even
    when nothing on disk moved.
    """
    try:
        key = _cache_key(root, char_budget, lang)
        now = _clock()
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit is not None and (now - hit[1]) < _CACHE_TTL_S:
                return hit[0]
        text = render_digest(build_packet(root), char_budget, lang=lang)
        with _CACHE_LOCK:
            if len(_CACHE) > 64:      # unbounded roots would leak; cheap to rebuild
                _CACHE.clear()
            _CACHE[key] = (text, _clock())
        return text
    except Exception as exc:  # noqa: BLE001
        log.debug("market_packet: digest failed (%s)", exc)
        return ""
