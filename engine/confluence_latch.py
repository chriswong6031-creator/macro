"""PIT latch for confluence events — a fired event may never be un-fired.

THE DEFECT THIS CLOSES.  ``confluence_tiers._to_daily`` stamps each timeframe bucket's value
onto the daily bar equal to that bucket's known-date (``_tf_bars`` returns ``known`` = the
bucket's LAST session).  The trailing bucket is INCOMPLETE, so its known-date advances every
session while the bucket stays open:

    3D bucket 2026-08-04 -> known 2026-08-05   (run of 08-05)  bar 08-05 carries recent3=True
    3D bucket 2026-08-04 -> known 2026-08-06   (run of 08-06)  bar 08-05 ffills 08-03 -> False

The 2D cross event stays pinned to its own CLOSED bucket, but its 3D partner leg walks off the
bar underneath it, so the T2 conjunction at ``confluence_tiers`` un-fires on a bar that ALREADY
PRINTED.  The last surviving event then falls back many ticks, blows the ``FRESH_TICKS`` window,
and the name leaves every board lane at once with no departure notice.

Measured: 300363.SZ 博腾股份 was the #1 name on the 2026-08-05 CN Prophet board (prophet 90.32,
featured, T2, ticks 0) and absent from all seven lanes on 08-06; it closed +20.02% — the ChiNext
limit — on 08-07.  Its per-bucket state never changed (``xup=True, recent3=True`` on that bucket
in BOTH runs); only the daily annotation moved.  Census on the post-#4732 engine: 86 erasure
events across 78 names in 12 sessions, so the absolute-session anchor repair did NOT close this
— it fixed bin PHASE (history-depth dependence), not bucket COMPLETION.

WHY A LATCH AND NOT A RECOMPUTE.  With provisional buckets you cannot have both no-lookahead and
no-repaint by recomputation alone: reading the containing bucket's FINAL value for a past bar is
lookahead, and re-deriving it from the moving known-date is the repaint.  The only construction
that is both is to write each bar's verdict ONCE — at the moment that bar was the as-of bar, from
data <= that bar — and never revise it.  That is this store.

SEMANTICS.
  * keep-FIRST on ``(ticker, date)`` — the first observation of a bar as the as-of bar wins,
    matching the published board and every other PIT store in this repo.
  * the LAST bar of a series is always the freshly computed value (it IS today's verdict, and
    it is what gets recorded).
  * bars before the store's birth fall back to the computed value — forward-only from store
    birth, the standard convention here.  A missing latch is therefore a no-op, never an error.

ZERO CHANGE BY DEFAULT.  ``confluence_tiers.cascade`` and ``signal_gate.gate`` take the latch as
an OPTIONAL argument defaulting to None; with None they are byte-identical to before, so US, HK
and CA are untouched by this module existing.
"""
from __future__ import annotations

import logging
import threading

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_STORE = "confluence_latch"
_COLS = ("ticker", "date", "fired")
_LOCK = threading.Lock()


def _path(market: str):
    return config.data_dir() / _STORE / f"{market.lower()}_t2.parquet"


class EventLatch:
    """Loaded-once view over one market's latch, with an in-memory pending buffer.

    Read path is a dict lookup keyed ``(ticker, 'YYYY-MM-DD')``; the writer batches new
    observations and :meth:`flush` merges them keep-first.  Never raises: a store that cannot
    be read degrades to an empty latch, which reproduces today's behaviour exactly.
    """

    def __init__(self, market: str = "CN", *, record: bool = False):
        self.market = market
        self.record = bool(record)
        self._seen: dict[tuple[str, str], bool] = {}
        self._pending: list[dict] = []
        self._loaded = False

    # ---- read -------------------------------------------------------------------------
    def load(self) -> "EventLatch":
        if self._loaded:
            return self
        self._loaded = True
        p = _path(self.market)
        if not p.exists():
            log.info("confluence_latch[%s]: no store yet — forward-only from this run",
                     self.market)
            return self
        try:
            df = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001 — a bad store must never break admission
            log.warning("confluence_latch[%s]: unreadable (%s) — treating as empty",
                        self.market, exc)
            return self
        for t, d, f in zip(df["ticker"].astype(str), df["date"].astype(str), df["fired"]):
            self._seen[(t, d)] = bool(f)
        log.info("confluence_latch[%s]: %d latched bars", self.market, len(self._seen))
        return self

    def stabilize(self, ticker: str, t2_buy: pd.Series) -> pd.Series:
        """Return ``t2_buy`` with every already-observed bar restored to its latched verdict.

        The LAST bar is left as computed — that is today's verdict, and it is what gets
        recorded.  Bars with no latch entry are left as computed (pre-birth fallback), so the
        first run over a long history changes nothing and simply begins accruing.
        """
        if t2_buy is None or len(t2_buy) == 0:
            return t2_buy
        try:
            out = t2_buy
            if self._seen:
                vals = out.to_numpy().copy()
                idx = out.index
                # every bar except the last may be restored from the latch
                for i in range(len(idx) - 1):
                    hit = self._seen.get((ticker, str(idx[i].date())))
                    if hit is not None:
                        vals[i] = hit
                out = pd.Series(vals, index=idx)
            if self.record:
                last = out.index[-1]
                self._pending.append({"ticker": str(ticker),
                                      "date": str(last.date()),
                                      "fired": bool(out.iloc[-1])})
            return out
        except Exception as exc:  # noqa: BLE001 — never break the board on a latch fault
            log.debug("confluence_latch[%s]: stabilize failed for %s (%s)",
                      self.market, ticker, exc)
            return t2_buy

    # ---- write ------------------------------------------------------------------------
    def flush(self) -> int:
        """Merge the pending observations keep-first.  Returns total rows after the merge."""
        if not self.record or not self._pending:
            return len(self._seen)
        p = _path(self.market)
        try:
            with _LOCK:
                p.parent.mkdir(parents=True, exist_ok=True)
                new = pd.DataFrame(self._pending, columns=list(_COLS))
                if p.exists():
                    try:
                        prior = pd.read_parquet(p)
                    except Exception:
                        prior = pd.DataFrame(columns=list(_COLS))
                    combined = pd.concat([prior, new], ignore_index=True)
                else:
                    combined = new
                combined["ticker"] = combined["ticker"].astype(str)
                combined["date"] = combined["date"].astype(str)
                combined["fired"] = combined["fired"].astype(bool)
                combined = combined.drop_duplicates(subset=["ticker", "date"], keep="first")
                combined.to_parquet(p, index=False)
            self._pending.clear()
            log.info("confluence_latch[%s]: %d rows after merge", self.market, len(combined))
            return len(combined)
        except Exception as exc:  # noqa: BLE001
            log.warning("confluence_latch[%s]: flush failed (%s)", self.market, exc)
            return len(self._seen)
