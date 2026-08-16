"""engine.prophet_live.cn_pack — the CN armed pack (CN-PR-1, spec §4).

ONE ENGINE. This module does not invent a second probe: it threads the mainland
calendar and the per-class daily-limit band through
:mod:`engine.prophet_live.armed_pack` and stamps the frozen nightly-board context
the close board will later restate. The US pack stays the NYSE path
(``calendar=None``).

LANE LAW (inherited, unchanged):
  * The nightly asia-close lane is the sole writer of ``data/cn_prophet_live/``.
  * Nothing here confirms. The pack is tonight's CONTRACT, not a verdict.
  * T2 latch is mandatory pack-side (300363.SZ). The evaluator never calls gate().
  * Probe APPENDS the next mainland session bar (W-L0 #4982).
  * Probe span is the ticker's daily-limit band, not the US 15%.

NO CN-LIMIT-ALPHA IMPORTS. Displayed score authority traces to
``engine.china_board_rank`` v3 + ``engine.signal_gate`` only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from engine.prophet_live import armed_pack as AP
from engine.prophet_live import cn_clock
from engine.prophet_live.interval import ADJUSTED, DEFAULT_PACK_ADJUSTMENT

log = logging.getLogger(__name__)

SCHEMA = "cn_prophet_live.armed/v1"
MARKET = "CN"

#: Frozen nightly legs the pack projects (spec §4). Live-derived fields are the
#: evaluator's: state, market_status, price. Never recompute these at 5-min.
FROZEN_LEG_KEYS: tuple[str, ...] = (
    "score", "rank", "lane", "rev_z", "reversal_member",
    "theme_timing", "relay", "liquidity", "microstructure",
)
LIVE_DERIVED_KEYS: tuple[str, ...] = ("state", "market_status", "price")

_ETF_OR_INDEX = frozenset({"Sector ETF", "Index"})


def pack_cfg(cfg: dict | None) -> dict[str, Any]:
    """US pack defaults, with the CN band defaulted per-name (not 15%)."""
    out = AP.pack_cfg(cfg)
    block = ((cfg or {}).get("cn_prophet_live") or {}) if isinstance(cfg, dict) else {}
    if isinstance(block, dict):
        for k, dv in list(out.items()):
            if k in block:
                try:
                    out[k] = type(dv)(block[k])
                except (TypeError, ValueError):
                    continue
    return out


def band_pct_for(ticker: Any) -> float:
    """Per-class daily-limit band (spec §2/§4). Main-board 10, STAR/ChiNext 20."""
    pct = cn_clock.limit_pct_for(ticker)
    return float(pct) if pct is not None else cn_clock.MAIN_BOARD_LIMIT_PCT


def is_cn_stock(ticker: Any, sector: Any = "") -> bool:
    """True for a mainland A-share the nightly board would score.

    Sector ETF / Index rows ride ``universe()`` for the library but are not
    Prophet names. ``.BJ`` is not in this lane's universe (spec §2).
    """
    try:
        t = str(ticker or "").strip().upper()
    except Exception:  # noqa: BLE001
        return False
    if not (t.endswith(".SS") or t.endswith(".SZ")):
        return False
    if str(sector or "") in _ETF_OR_INDEX:
        return False
    return True


def make_cn_gate(latch: Any | None = None) -> Callable[[str, Any], dict]:
    """``signal_gate.gate`` with the CN T2 latch loaded (record=False on this path).

    The pack-side latch is READ-ONLY here: writes stay on the asia collection
    lane. A missing store degrades to an empty latch (EventLatch.load never
    raises) — that is today's behaviour, not a new one.
    """
    from engine import signal_gate  # noqa: PLC0415

    if latch is None:
        from engine.confluence_latch import EventLatch  # noqa: PLC0415
        latch = EventLatch("CN", record=False).load()

    def _gate(ticker: str, close: Any) -> dict:
        return signal_gate.gate(ticker, close, event_latch=latch)

    return _gate


def centre_record(ticker: str, close: Any, *, cfg: dict[str, Any],
                  gate_fn: Callable[[str, Any], dict] | None = None,
                  center_verdict: dict | None = None) -> dict[str, Any]:
    """US centre census with this name's daily-limit band and the CN calendar."""
    from lib import cn_calendar  # noqa: PLC0415

    local = dict(cfg)
    local["band_pct"] = band_pct_for(ticker)
    rec = AP.centre_record(ticker, close, cfg=local, gate_fn=gate_fn,
                           center_verdict=center_verdict)
    rec["band_pct"] = local["band_pct"]
    rec["calendar"] = cn_calendar
    return rec


def probe_name(ticker: str, close: Any, rec: dict[str, Any], *,
               cfg: dict[str, Any],
               gate_fn: Callable[[str, Any], dict] | None = None) -> dict[str, Any]:
    from lib import cn_calendar  # noqa: PLC0415

    local = dict(cfg)
    local["band_pct"] = rec.get("band_pct") or band_pct_for(ticker)
    return AP.probe_name(ticker, close, rec, cfg=local, gate_fn=gate_fn,
                         calendar=cn_calendar)


def verify_edges(ticker: str, close: Any, checks: list,
                 gate_fn: Callable[[str, Any], dict] | None = None) -> tuple[list[str], int]:
    from lib import cn_calendar  # noqa: PLC0415
    return AP.verify_edges(ticker, close, checks, gate_fn=gate_fn, calendar=cn_calendar)


def attach_frozen(entry: dict[str, Any], frozen: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project the nightly board's frozen legs onto one pack entry (spec §4)."""
    src = dict(frozen or {})
    if not src:
        entry["repaint_disclosure"] = {"frozen_as_of": [], "live_derived": list(LIVE_DERIVED_KEYS)}
        return entry
    blob = {
        "score": src.get("prophet_score", src.get("score")),
        "rank": src.get("prophet_rank", src.get("rank")),
        "lane": src.get("lane"),
        "rev_z": src.get("rev_z"),
        "reversal_member": src.get("reversal_member"),
        "theme_timing": src.get("theme_timing"),
        "relay": src.get("relay"),
        "liquidity": src.get("liquidity"),
        "microstructure": src.get("microstructure"),
    }
    entry["frozen"] = {k: v for k, v in blob.items() if v is not None}
    entry["repaint_disclosure"] = {
        "frozen_as_of": list(FROZEN_LEG_KEYS),
        "live_derived": list(LIVE_DERIVED_KEYS),
    }
    return entry


def assemble(names: dict[str, dict[str, Any]], *, as_of: str, cfg: dict[str, Any],
             universe_n: int, wanted_n: int, gate_calls: int,
             build_seconds: float, skipped: dict[str, int],
             edges_checked: int = 0,
             probe_seconds: dict[str, float] | None = None,
             price_adjustment: dict[str, str] | None = None,
             frozen: Mapping[str, Mapping[str, Any]] | None = None,
             now: datetime | None = None) -> dict[str, Any]:
    """US assemble, then restamp the CN schema and attach frozen context."""
    for tkr, entry in names.items():
        attach_frozen(entry, (frozen or {}).get(tkr))
        entry.setdefault("band_pct", band_pct_for(tkr))
        entry.setdefault("price_adjustment",
                         (price_adjustment or {}).get(tkr) or DEFAULT_PACK_ADJUSTMENT)
    payload = AP.assemble(
        names, as_of=as_of, cfg=cfg, universe_n=universe_n, wanted_n=wanted_n,
        gate_calls=gate_calls, build_seconds=build_seconds, skipped=skipped,
        edges_checked=edges_checked, probe_seconds=probe_seconds,
        price_adjustment=price_adjustment, now=now,
    )
    payload["schema"] = SCHEMA
    payload["market"] = MARKET
    payload["price_adjustment"] = ADJUSTED
    payload["meta"]["band_rule"] = "per_class_daily_limit"
    payload["meta"]["calendar"] = "cn"
    payload["meta"]["t2_latch"] = "CN"
    return payload


def filter_universe(rows: Iterable[tuple]) -> list[tuple]:
    """Drop Sector ETF / Index / non-.SS/.SZ rows from ``universe()``."""
    out: list[tuple] = []
    for row in rows:
        if not row:
            continue
        tkr = row[0]
        sector = row[4] if len(row) > 4 else ""
        if is_cn_stock(tkr, sector):
            out.append(row)
    return out
