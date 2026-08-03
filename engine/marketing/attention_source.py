"""engine.marketing.attention_source — read-only candidate pools for post selection.

Supply side of the TrendSpider hardening program (masterplan §3 PR-B). This
module ONLY reads collected artifacts and ranks them with deterministic
arithmetic; it selects nothing, posts nothing, and writes nothing. The selector
that consumes these pools is PR-C's business.

A7 / display-tier law. Every row here is *display tier*: an ordering over data
somebody else collected, with the concrete driver spelled out in ``why``. No
model, LLM or otherwise, originates a rank, a score or a signal in this file —
the arithmetic is a sort key and the provenance is the receipt.

Public API (all fail-soft — no public function raises):

    top_by_dollar_volume(root, n=...)  -> list[dict]   hot_tape_pack adv_rank
    top_by_options_volume(root, n=...) -> list[dict]   options_flow contract volume
    retail_attention(root, n=...)      -> list[dict]   WSB mentions ∪ wiki attention z
    earnings_this_week(root, n=...)    -> list[dict]   earnings.parquet next_date ≤ 5 sessions
    stage2_leaders(root, n=...)        -> list[dict]   stage backfill, USA stage 2 by SATA
    stage_transitions(root, n=...)     -> list[dict]   stage_flag changed vs prior snapshot

    supply_config(root)                       -> dict
    pool_cap(root, pool)                      -> int
    long_tail_quota(root)                     -> dict
    max_chart_posts_per_ticker_day(root)      -> int
    max_stale_sessions(root, pool=None)       -> int
    pack_min_adv_dollars(root)                -> float

Every row is ``{ticker, rank, why, asof, source}``:

* ``rank``   1-based position **within this pool**, not the source's own rank
             (the source's rank, when it has one, is spelled out in ``why``).
* ``why``    a plain sentence naming the concrete driver and its number.
* ``asof``   the session **that row's own source** dates itself to.
* ``source`` the artifact the row came from.

FRESHNESS BEATS COVERAGE (masterplan §3 PR-B.2). A pool whose source is older
than ``max_stale_sessions`` trading sessions returns ``[]`` and prints ONE
GitHub annotation. A stale pool must never masquerade as a fresh one: an
attention rank computed off a two-week-old snapshot is a *lie about today*,
and the selector downstream has no way to tell the difference once the rows
are in its hands.

The gate is applied **per row** wherever the artifact dates itself per row —
``data/options_flow`` carries 369 names at 2026-07-31 and a dozen 2 sessions
behind it, and ``data/earnings/earnings.parquet`` mixes two ``as_of`` sweeps in
one file. Dropping the whole pool because one straggler is stale would throw
away 369 honest rows to punish 12; dating all 383 by the freshest stamp would
be the mixed-asof failure ``movers_source`` already documents at length. So
each row carries its own session and is dropped on its own session, and the
POOL only collapses to ``[]`` (with the annotation) when nothing fresh is left.

SPLIT-ADJUSTMENT LAW. ``data/massive_stock_day`` is not split-adjusted, so
fields derived from it may rank VOLUME but may never state a price fact. This
module reads ``adv20_dollars``/``adv_rank`` from the hot-tape pack (volume) and
never its price fields.

GitHub annotations are bare ``print`` at line start with ``flush=True`` — never
through a logger, which would prefix the line and make the annotation invisible
to Actions (CLAUDE.md five-strike law, ``tests/test_gh_annotation_line_start.py``).
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, Path]

# ─────────────────────────────────────────────────────────────────────────────
# Artifact locations
# ─────────────────────────────────────────────────────────────────────────────

PACK_REL = "data/marketing/hot_tape_pack.json"
OPTIONS_FLOW_REL = "data/options_flow"
WSB_REL = "data/quiver/wallstreetbets.parquet"
WIKI_ATTENTION_REL = "site/factordata/attention.json"
EARNINGS_REL = "data/earnings/earnings.parquet"
STAGE_REL = "data/stage_analysis/backfill/equitydesk_overview.parquet"

#: Sessions a source may lag before its pool is refused. Overridable per repo in
#: ``config/marketing.yml`` under ``supply.freshness.max_stale_sessions``.
DEFAULT_MAX_STALE_SESSIONS = 3

#: Earnings inside this many forward sessions count as "this week".
EARNINGS_FORWARD_SESSIONS = 5

#: Defaults for the ``supply:`` config block. PR-C's selector consumes these;
#: nothing in PR-B wires them to a consumer, on purpose — one owner, one block.
_SUPPLY_DEFAULTS: dict[str, Any] = {
    "pool_caps": {
        "dollar_volume": 120,
        "options_volume": 80,
        "retail_attention": 80,
        "earnings_this_week": 60,
        "stage2_leaders": 60,
        "stage_transitions": 40,
    },
    "long_tail_quota": {
        "min_fresh_per_day": 3,
        "not_posted_within_days": 30,
    },
    "per_ticker_day": {
        "max_chart_posts": 3,
    },
    "freshness": {
        "max_stale_sessions": DEFAULT_MAX_STALE_SESSIONS,
        # Per-pool override, EMPTY on purpose: out of the box every pool is
        # judged by the one number above, exactly as specified. The lever
        # exists because two of these sources do not refresh daily — the
        # earnings calendar sweeps sporadically (two `as_of` stamps in the
        # shipped file) and the stage backfill is a weekly artifact — so a
        # 3-session budget refuses them most of the time. Raising a pool's
        # budget here is an operator decision with a receipt; quietly widening
        # the gate in code, or letting a caller ignore an empty pool, is not.
        "per_pool": {},
    },
    "tiers": {
        # Key name is `pack_min_adv_dollars`, NOT the pack's module name: the
        # config file that carries it is held read-only to the Hot Tape program
        # by tests/test_marketing_hot_tape_radar.py::TestSafetyStack, whose
        # config invariant is absolute (no sanctioned-token exception). Naming
        # the artifact is fine HERE — this file is not on that list.
        "pack_min_adv_dollars": 25_000_000,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Annotations + small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _warn(title: str, msg: str) -> None:
    """Emit ONE GitHub annotation, bare print, line start, flushed.

    Never a logger: every builder in this repo logs through a prefixing
    formatter, so ``log.warning("::warning ...")`` emits ``WARNING ::warning``
    and Actions silently drops it. ``flush`` is load-bearing because stdout is
    block-buffered when the step is piped.
    """
    print(f"::warning title={title}::{msg}", flush=True)


def _iso_date(value: object) -> date | None:
    """Parse the leading ``YYYY-MM-DD`` of *value*; None when unparseable."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        y, m, d = (int(x) for x in str(value)[:10].split("-"))
        return date(y, m, d)
    except Exception:  # noqa: BLE001
        return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def sessions_since(earlier: object, later: object) -> int | None:
    """Mon–Fri sessions in ``(earlier, later]`` — how stale *earlier* is.

    Same shape as ``content_studio.trading_days_since`` and deliberately not an
    import of it: that module is the selection engine PR-C rewrites, and a
    read-only supply module must not drag it in.

    No market-holiday calendar is consulted, and here that omission is the SAFE
    direction: counting a holiday as a session makes a source look *older* than
    it is, so the freshness gate trips sooner rather than later. Returns None
    when either side is unparseable (callers fail closed on None), and 0 when
    *later* is not after *earlier* — a source stamped in the future is not fresh
    evidence of anything, but it is also not stale, so it passes the gate and
    its own row-level stamp keeps the receipt honest.
    """
    d0, d1 = _iso_date(earlier), _iso_date(later)
    if d0 is None or d1 is None:
        return None
    if d1 <= d0:
        return 0
    if (d1 - d0).days > 400:
        return 9999
    n = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _is_stale(asof: object, ref: date, budget: int) -> bool:
    """True when *asof* lags *ref* by more than *budget* sessions (or is unreadable)."""
    n = sessions_since(asof, ref)
    if n is None:
        return True
    return n > budget


def _finite(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _human_dollars(v: float) -> str:
    """$4.2B / $317M / $25.0M — a dollar figure a caption could survive."""
    a = abs(v)
    if a >= 1e12:
        return f"${v / 1e12:.1f}T"
    if a >= 1e9:
        return f"${v / 1e9:.1f}B"
    if a >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


def _rows(items: list[dict], n: int) -> list[dict]:
    """Stamp 1-based pool rank onto the first *n* already-sorted rows."""
    out: list[dict] = []
    for i, it in enumerate(items[: max(0, int(n))], start=1):
        it["rank"] = i
        out.append(it)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Config accessors (config/marketing.yml → supply:)
# ─────────────────────────────────────────────────────────────────────────────

def _deep_fill(base: dict, defaults: dict) -> dict:
    """Return *defaults* overlaid by *base*, one level of nesting deep."""
    out: dict[str, Any] = {}
    for k, dv in defaults.items():
        bv = base.get(k) if isinstance(base, dict) else None
        if isinstance(dv, dict):
            out[k] = {**dv, **(bv if isinstance(bv, dict) else {})}
        else:
            out[k] = bv if bv is not None else dv
    for k, bv in (base or {}).items():
        if k not in out:
            out[k] = bv
    return out


def supply_config(root: PathLike | None) -> dict:
    """The ``supply:`` block of config/marketing.yml, defaults filled in.

    ONE owner for the diversity knobs (masterplan §3 PR-B.4). PR-B defines and
    reads the block; PR-C's selector is what will act on it. Fail-soft: an
    absent or malformed config yields the built-in defaults, never an exception.
    """
    raw: dict = {}
    try:
        import yaml  # type: ignore[import-untyped]
        path = Path(str(root or ".")) / "config" / "marketing.yml"
        if path.exists():
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(cfg, dict) and isinstance(cfg.get("supply"), dict):
                raw = cfg["supply"]
    except Exception:  # noqa: BLE001
        raw = {}
    return _deep_fill(raw, _SUPPLY_DEFAULTS)


def pool_cap(root: PathLike | None, pool: str) -> int:
    """Candidate cap for *pool* (``dollar_volume``, ``options_volume``, …)."""
    caps = supply_config(root).get("pool_caps") or {}
    v = caps.get(pool)
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return int(_SUPPLY_DEFAULTS["pool_caps"].get(pool, 50))


def long_tail_quota(root: PathLike | None) -> dict:
    """``{min_fresh_per_day, not_posted_within_days}`` — §0 gate 6's long tail."""
    q = supply_config(root).get("long_tail_quota") or {}
    out = dict(_SUPPLY_DEFAULTS["long_tail_quota"])
    for k in out:
        try:
            out[k] = int(q[k])
        except (KeyError, TypeError, ValueError):
            pass
    return out


def max_chart_posts_per_ticker_day(root: PathLike | None) -> int:
    """Chart posts one ticker may carry in one day (§0 gate 6 cap)."""
    blk = supply_config(root).get("per_ticker_day") or {}
    try:
        return max(1, int(blk["max_chart_posts"]))
    except (KeyError, TypeError, ValueError):
        return int(_SUPPLY_DEFAULTS["per_ticker_day"]["max_chart_posts"])


def max_stale_sessions(root: PathLike | None, pool: str | None = None) -> int:
    """Sessions a source may lag before its pool is refused.

    *pool* consults ``supply.freshness.per_pool`` first and falls back to the
    single ``max_stale_sessions`` number, which is what every pool uses unless
    an operator has deliberately given one its own budget.
    """
    blk = supply_config(root).get("freshness") or {}
    if pool:
        per_pool = blk.get("per_pool")
        if isinstance(per_pool, dict) and pool in per_pool:
            try:
                return max(0, int(per_pool[pool]))
            except (TypeError, ValueError):
                pass
    try:
        return max(0, int(blk["max_stale_sessions"]))
    except (KeyError, TypeError, ValueError):
        return DEFAULT_MAX_STALE_SESSIONS


def pack_min_adv_dollars(root: PathLike | None) -> float:
    """ADV floor a hot-tape-pack name must clear to enter the tier universe."""
    blk = supply_config(root).get("tiers") or {}
    v = _finite(blk.get("pack_min_adv_dollars"))
    if v is None or v < 0:
        return float(_SUPPLY_DEFAULTS["tiers"]["pack_min_adv_dollars"])
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Shared reads
# ─────────────────────────────────────────────────────────────────────────────

def load_hot_tape_pack(root: PathLike | None) -> dict | None:
    """Read ``data/marketing/hot_tape_pack.json``; None when absent/malformed."""
    try:
        path = Path(str(root or ".")) / PACK_REL
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("tickers"), dict):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pool 1 — dollar volume (hot-tape pack adv_rank)
# ─────────────────────────────────────────────────────────────────────────────

def top_by_dollar_volume(
    root: PathLike | None,
    n: int = 120,
    *,
    as_of: object = None,
) -> list[dict]:
    """Most-traded names by 20-day average dollar volume.

    ``adv_rank`` is the pack's own dense rank over ``adv20_dollars`` — a VOLUME
    field, which is the only thing the unadjusted store underneath it is allowed
    to decide (module docstring, split-adjustment law).
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "dollar_volume")
    pack = load_hot_tape_pack(root)
    if pack is None:
        _warn("marketing-supply-dollar-volume",
              f"hot_tape_pack absent at {PACK_REL} — dollar-volume pool empty")
        return []
    trade_date = str(pack.get("trade_date") or "")[:10]
    if _is_stale(trade_date, ref, budget):
        _warn("marketing-supply-dollar-volume",
              f"hot_tape_pack trade_date {trade_date or '?'} is more than {budget} "
              f"sessions behind {ref.isoformat()} — dollar-volume pool empty")
        return []

    items: list[dict] = []
    for ticker, rec in (pack.get("tickers") or {}).items():
        if not isinstance(rec, dict):
            continue
        rank = rec.get("adv_rank")
        adv = _finite(rec.get("adv20_dollars"))
        if rank is None or adv is None:
            continue
        try:
            rank_i = int(rank)
        except (TypeError, ValueError):
            continue
        items.append({
            "ticker": str(ticker).upper(),
            "_sort": (rank_i, str(ticker).upper()),
            "why": f"dollar-volume rank #{rank_i} ({_human_dollars(adv)} a day)",
            "asof": str(rec.get("last_date") or trade_date)[:10],
            "source": "hot_tape_pack",
        })
    items.sort(key=lambda r: r["_sort"])
    for it in items:
        it.pop("_sort", None)
    return _rows(items, n)


# ─────────────────────────────────────────────────────────────────────────────
# Pool 2 — options volume (data/options_flow/summary_<TICKER>.parquet)
# ─────────────────────────────────────────────────────────────────────────────

def top_by_options_volume(
    root: PathLike | None,
    n: int = 80,
    *,
    as_of: object = None,
) -> list[dict]:
    """Busiest options tape by latest-session contract volume.

    Each ``summary_<TICKER>.parquet`` is a daily aggregate indexed by date; the
    last row is that name's most recent session, and that name's session is what
    dates its row — the files do not advance in lockstep.
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "options_volume")
    base = Path(str(root or ".")) / OPTIONS_FLOW_REL
    if not base.is_dir():
        _warn("marketing-supply-options-volume",
              f"{OPTIONS_FLOW_REL} absent — options-volume pool empty")
        return []
    try:
        import pandas as pd  # noqa: F401
    except Exception:  # noqa: BLE001
        _warn("marketing-supply-options-volume",
              "pandas unavailable — options-volume pool empty")
        return []

    files = sorted(base.glob("summary_*.parquet"))
    items: list[dict] = []
    n_stale = 0
    freshest: str = ""
    for path in files:
        ticker = path.stem[len("summary_"):].upper()
        if not ticker:
            continue
        try:
            df = pd.read_parquet(path, columns=["volume", "premium_mn", "pc_ratio"])
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        try:
            row_asof = str(df.index[-1])[:10]
            last = df.iloc[-1]
            volume = _finite(last.get("volume"))
            premium = _finite(last.get("premium_mn"))
            pc = _finite(last.get("pc_ratio"))
        except Exception:  # noqa: BLE001
            continue
        if volume is None or volume <= 0:
            continue
        if row_asof > freshest:
            freshest = row_asof
        if _is_stale(row_asof, ref, budget):
            n_stale += 1
            continue
        why = f"options volume {volume:,.0f} contracts"
        if premium is not None:
            why += f", {_human_dollars(premium * 1e6)} premium"
        if pc is not None:
            why += f", put/call {pc:.2f}"
        items.append({
            "ticker": ticker,
            "_sort": (-volume, ticker),
            "why": why,
            "asof": row_asof,
            "source": "options_flow",
        })

    if not items:
        _warn("marketing-supply-options-volume",
              f"every options_flow summary is more than {budget} sessions behind "
              f"{ref.isoformat()} (freshest {freshest or 'none'}, {n_stale} stale, "
              f"{len(files)} files) — options-volume pool empty")
        return []
    items.sort(key=lambda r: r["_sort"])
    for it in items:
        it.pop("_sort", None)
    return _rows(items, n)


# ─────────────────────────────────────────────────────────────────────────────
# Pool 3 — retail attention (WSB mentions ∪ Wikipedia attention z)
# ─────────────────────────────────────────────────────────────────────────────

def _wsb_leg(root: PathLike | None, ref: date, budget: int) -> tuple[dict[str, dict], str]:
    """``{ticker: {count, rank, sentiment}}`` for the latest collected WSB day."""
    path = Path(str(root or ".")) / WSB_REL
    if not path.exists():
        return {}, ""
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return {}, ""
    if df is None or df.empty or "Ticker" not in df.columns or "Count" not in df.columns:
        return {}, ""
    try:
        col = "_collected" if "_collected" in df.columns else None
        if col is None:
            return {}, ""
        latest = str(max(str(x)[:10] for x in df[col].dropna()))
        day = df[df[col].astype(str).str[:10] == latest]
    except Exception:  # noqa: BLE001
        return {}, ""
    if _is_stale(latest, ref, budget):
        return {}, latest

    counts: dict[str, float] = {}
    sents: dict[str, float] = {}
    try:
        for _, row in day.iterrows():
            t = str(row.get("Ticker") or "").upper()
            c = _finite(row.get("Count"))
            if not t or c is None or c <= 0:
                continue
            counts[t] = counts.get(t, 0.0) + c
            s = _finite(row.get("Sentiment"))
            if s is not None:
                sents[t] = s
    except Exception:  # noqa: BLE001
        return {}, latest
    if not counts:
        return {}, latest

    order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out: dict[str, dict] = {}
    for i, (t, c) in enumerate(order, start=1):
        out[t] = {"count": c, "rank": i, "sentiment": sents.get(t)}
    return out, latest


def _wiki_leg(root: PathLike | None, ref: date, budget: int) -> tuple[dict[str, dict], str]:
    """``{ticker: {z, views, asof}}`` from site/factordata/attention.json."""
    path = Path(str(root or ".")) / WIKI_ATTENTION_REL
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}, ""
    if not isinstance(data, dict):
        return {}, ""

    out: dict[str, dict] = {}
    newest = ""
    for ticker, rec in data.items():
        if not isinstance(rec, dict):
            continue
        z = _finite(rec.get("z"))
        if z is None:
            continue
        asof = str(rec.get("asof") or "")[:10]
        if asof > newest:
            newest = asof
        if _is_stale(asof, ref, budget):
            continue
        out[str(ticker).upper()] = {"z": z, "views": _finite(rec.get("views")), "asof": asof}
    return out, newest


def retail_attention(
    root: PathLike | None,
    n: int = 80,
    *,
    as_of: object = None,
) -> list[dict]:
    """Names retail is actually looking at — WSB mentions ∪ Wikipedia attention.

    Blend: each leg is max-normalized to ``[0, 1]`` over the day's own
    population (a WSB count against the day's top count; a wiki z against the
    day's top positive z, negatives clamped to 0), and the score is the mean of
    the two legs with a missing leg counting 0. That deliberately rewards a name
    both legs see over a name only one leg sees, and it needs no cross-source
    unit conversion — the two sources measure different things and only their
    *position within their own population* is comparable.

    ``why`` names the leg that actually drove the row, never the blend: "WSB #3
    by mentions (207)" is a fact a reader can check, "attention score 0.71" is
    an artifact of this function.
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "retail_attention")
    wsb, wsb_asof = _wsb_leg(root, ref, budget)
    wiki, wiki_asof = _wiki_leg(root, ref, budget)

    if not wsb and not wiki:
        _warn("marketing-supply-retail-attention",
              f"no fresh retail-attention leg within {budget} sessions of "
              f"{ref.isoformat()} (wsb {wsb_asof or 'absent'}, "
              f"wiki {wiki_asof or 'absent'}) — retail-attention pool empty")
        return []

    max_count = max((v["count"] for v in wsb.values()), default=0.0)
    max_z = max((v["z"] for v in wiki.values() if v["z"] > 0), default=0.0)

    items: list[dict] = []
    for ticker in sorted(set(wsb) | set(wiki)):
        w = wsb.get(ticker)
        k = wiki.get(ticker)
        wsb_norm = (w["count"] / max_count) if (w and max_count > 0) else 0.0
        wiki_norm = (max(0.0, k["z"]) / max_z) if (k and max_z > 0) else 0.0
        score = (wsb_norm + wiki_norm) / 2.0
        if score <= 0:
            continue
        if wsb_norm >= wiki_norm and w is not None:
            why = f"WSB #{w['rank']} by mentions ({int(w['count'])} today)"
            asof, source = wsb_asof, "quiver_wsb"
        elif k is not None:
            why = f"search attention z {k['z']:.1f}"
            if k.get("views") is not None:
                why += f" ({int(k['views'])} page views)"
            asof, source = k["asof"] or wiki_asof, "wiki_attention"
        else:  # pragma: no cover — unreachable while score > 0
            continue
        items.append({
            "ticker": ticker,
            "_sort": (-score, ticker),
            "why": why,
            "asof": asof,
            "source": source,
        })

    items.sort(key=lambda r: r["_sort"])
    for it in items:
        it.pop("_sort", None)
    return _rows(items, n)


# ─────────────────────────────────────────────────────────────────────────────
# Pool 4 — earnings this week
# ─────────────────────────────────────────────────────────────────────────────

_EARNINGS_TIME_WORDS = {
    "time-pre-market": "before the open",
    "time-after-hours": "after the close",
    "time-not-supplied": "time not set",
}


def earnings_this_week(
    root: PathLike | None,
    n: int = 60,
    *,
    as_of: object = None,
) -> list[dict]:
    """Names reporting inside the next ``EARNINGS_FORWARD_SESSIONS`` sessions.

    The calendar file mixes sweeps — rows carry their own ``as_of`` and a stale
    row is dropped on its own stamp, not on the file's freshest one.
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "earnings_this_week")
    path = Path(str(root or ".")) / EARNINGS_REL
    if not path.exists():
        _warn("marketing-supply-earnings",
              f"{EARNINGS_REL} absent — earnings pool empty")
        return []
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        _warn("marketing-supply-earnings",
              f"{EARNINGS_REL} unreadable — earnings pool empty")
        return []
    if df is None or df.empty or "next_date" not in df.columns:
        _warn("marketing-supply-earnings",
              f"{EARNINGS_REL} carries no next_date column — earnings pool empty")
        return []

    has_asof = "as_of" in df.columns
    has_time = "next_time" in df.columns
    items: list[dict] = []
    n_stale = 0
    freshest = ""
    for ticker, row in df.iterrows():
        t = str(ticker).upper()
        nd = _iso_date(row.get("next_date"))
        if not t or nd is None:
            continue
        row_asof = str(row.get("as_of") or "")[:10] if has_asof else ""
        if row_asof:
            if row_asof > freshest:
                freshest = row_asof
            if _is_stale(row_asof, ref, budget):
                n_stale += 1
                continue
        sessions = sessions_since(ref, nd)
        if sessions is None or sessions > EARNINGS_FORWARD_SESSIONS:
            continue
        if nd < ref:
            continue
        when = _EARNINGS_TIME_WORDS.get(str(row.get("next_time") or ""), "") if has_time else ""
        why = f"reports {nd.isoformat()}"
        why += f" ({when})" if when else ""
        why += f", {sessions} session{'' if sessions == 1 else 's'} away" if sessions else ", today"
        items.append({
            "ticker": t,
            "_sort": (sessions, t),
            "why": why,
            "asof": row_asof or ref.isoformat(),
            "source": "earnings_calendar",
        })

    if not items:
        _warn("marketing-supply-earnings",
              f"no earnings row inside {EARNINGS_FORWARD_SESSIONS} sessions of "
              f"{ref.isoformat()} survived the {budget}-session freshness gate "
              f"(freshest sweep {freshest or 'unstamped'}, {n_stale} stale) — "
              "earnings pool empty")
        return []
    items.sort(key=lambda r: r["_sort"])
    for it in items:
        it.pop("_sort", None)
    return _rows(items, n)


# ─────────────────────────────────────────────────────────────────────────────
# Pools 5 + 6 — Weinstein stage reads
# ─────────────────────────────────────────────────────────────────────────────

_STAGE_COLS = [
    "ticker", "region", "stage_flag", "stage_detailed",
    "sata_score", "weeks_in_stage", "as_of_date",
]


def _read_stage(root: PathLike | None):
    """The stage backfill frame, or None. Same read ``radar_internal._feed_stage`` does."""
    path = Path(str(root or ".")) / STAGE_REL
    if not path.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(path, columns=_STAGE_COLS)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    return df


def stage2_leaders(
    root: PathLike | None,
    n: int = 60,
    *,
    as_of: object = None,
) -> list[dict]:
    """US names in Weinstein stage 2, strongest SATA score first.

    Same parquet, region filter and ordering ``radar_internal._feed_stage`` uses
    — plus the freshness gate that read does not have. The backfill is a WEEKLY
    artifact refreshed on its own cadence, so a run that finds it more than
    ``max_stale_sessions`` behind will legitimately return ``[]``; that is the
    gate working, not a bug, and the annotation says which snapshot it saw.
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "stage2_leaders")
    df = _read_stage(root)
    if df is None:
        _warn("marketing-supply-stage2",
              f"{STAGE_REL} absent or unreadable — stage-2 pool empty")
        return []
    try:
        snapshots = sorted({str(x)[:10] for x in df["as_of_date"].dropna()})
    except Exception:  # noqa: BLE001
        snapshots = []
    latest = snapshots[-1] if snapshots else ""
    if _is_stale(latest, ref, budget):
        _warn("marketing-supply-stage2",
              f"stage backfill snapshot {latest or 'unstamped'} is more than {budget} "
              f"sessions behind {ref.isoformat()} — stage-2 pool empty")
        return []

    try:
        sel = df[(df["region"] == "USA") & (df["stage_flag"] == 2)].copy()
        sel = sel[sel["as_of_date"].astype(str).str[:10] == latest]
        sel = sel.sort_values(["sata_score", "ticker"], ascending=[False, True])
    except Exception:  # noqa: BLE001
        return []

    items: list[dict] = []
    for _, row in sel.iterrows():
        t = str(row.get("ticker") or "").upper()
        if not t:
            continue
        items.append({
            "ticker": t,
            "why": (f"stage {row.get('stage_detailed')}, SATA {row.get('sata_score')}, "
                    f"{row.get('weeks_in_stage')}w in stage"),
            "asof": latest,
            "source": "stage_analysis",
        })
    return _rows(items, n)


def stage_transitions(
    root: PathLike | None,
    n: int = 40,
    *,
    as_of: object = None,
) -> list[dict]:
    """Names whose stage_flag changed between the two newest snapshots.

    STRUCTURAL LIMIT, stated rather than hidden: the shipped backfill parquet
    carries exactly ONE ``as_of_date`` (2026-07-17 as of this build), so there
    is no prior snapshot to diff and this pool is empty for a reason that has
    nothing to do with staleness. The diff is implemented anyway — it is the
    cheap half — and it starts producing rows the day the backfill retains two
    snapshots. Until then the pool says so in an annotation instead of quietly
    returning ``[]`` and letting a caller read that as "no transitions today".
    """
    ref = _iso_date(as_of) or _today()
    budget = max_stale_sessions(root, "stage_transitions")
    df = _read_stage(root)
    if df is None:
        _warn("marketing-supply-stage-transitions",
              f"{STAGE_REL} absent or unreadable — stage-transition pool empty")
        return []
    try:
        snapshots = sorted({str(x)[:10] for x in df["as_of_date"].dropna()})
    except Exception:  # noqa: BLE001
        snapshots = []
    if len(snapshots) < 2:
        _warn("marketing-supply-stage-transitions",
              f"{STAGE_REL} retains {len(snapshots)} snapshot(s) "
              f"({snapshots[-1] if snapshots else 'none'}) — a stage transition needs two, "
              "so the pool is structurally empty, not quiet")
        return []
    latest, prior = snapshots[-1], snapshots[-2]
    if _is_stale(latest, ref, budget):
        _warn("marketing-supply-stage-transitions",
              f"stage backfill snapshot {latest} is more than {budget} sessions behind "
              f"{ref.isoformat()} — stage-transition pool empty")
        return []

    try:
        usa = df[df["region"] == "USA"].copy()
        asof_s = usa["as_of_date"].astype(str).str[:10]
        cur = usa[asof_s == latest]
        old = usa[asof_s == prior]
        prev_flag = {str(r.get("ticker") or "").upper(): r.get("stage_flag")
                     for _, r in old.iterrows()}
        cur = cur.sort_values(["sata_score", "ticker"], ascending=[False, True])
    except Exception:  # noqa: BLE001
        return []

    items: list[dict] = []
    for _, row in cur.iterrows():
        t = str(row.get("ticker") or "").upper()
        if not t or t not in prev_flag:
            continue
        was, now = prev_flag[t], row.get("stage_flag")
        if was is None or now is None or str(was) == str(now):
            continue
        items.append({
            "ticker": t,
            "why": (f"stage {was} to {now} since {prior}, "
                    f"SATA {row.get('sata_score')}, now {row.get('stage_detailed')}"),
            "asof": latest,
            "source": "stage_analysis",
        })
    return _rows(items, n)
