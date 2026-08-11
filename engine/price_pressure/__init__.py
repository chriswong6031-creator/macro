"""engine.price_pressure — Dislocation & Recovery lobe (DRL), wave 1.

    tier            : display
    authority       : context_only
    owner_program   : price-pressure

Detect when a single US name's price has been pushed materially away from what
its sector peers justify (a residual shock), record everything knowable about
that moment POINT-IN-TIME, and track how the residual resolves.  Program home:
``research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md`` (v2, red-team
adjudication folded in at §12).

**Not a buy-signal engine.**  The 1-5d shock-reversal classifier is CLOSED at
OHLCV grade (DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER, LSR-P0 2026-08-05):
no-news down-shocks *continue*, and the real unconditional bounce breaks even at
14.2bp/leg.  This lobe ships the measured truth as display-tier context; nothing
here ranks, sizes, gates, originates a signal, or escalates one.  Any future
promotion walks the masterplan §7 gauntlet on the FORWARD ledger only.

Module map (see masterplan §4):

    panel.py      the single import seam onto the LSR-P0 machinery — the panel
                  build, residual construction, event harvest and EDGAR firewall
                  are IMPORTED, never re-derived (masterplan §0/§4).
    detect.py     residual derivation + shock harvest on top of that seam, the
                  t+60 ledger tail read off LSR's own cumulative frame, and the
                  peer-basis disclosure mask (§4.1: ≥65% of the panel
                  residualizes against the market, not sector peers).
    context.py    per-event PIT facts: coverage-gated filing families, NUMERIC
                  day facts only (no day taxonomy in the ledger —
                  DNR:KILL-PARALLEL-SHOCK-CLASSIFIER), thematic-basket ex-self
                  residual, pos52, VIX percentile.
    ledger.py     the point-in-time event ledger (§5): schema, episodes, era
                  rules, fixed-window grading, display states (§5.1), catch-up.
    completion.py the ONE sanctioned identity-block write: the §10.1 VIXCLS
                  stamp-completion pass, against append-only receipts
                  (``research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md``).
    base_rates.py the frozen family x horizon base-rate tables (§6).
    artifact.py   the display snapshot ``data/price_pressure/latest.json``.
    backfill.py   the one-shot historical seed (era="backfill"), run locally.

No LLM anywhere in this package (constitution A7).  Every field is engine
computed.  Submodules are imported lazily by ``__getattr__`` so that a reader
that only wants a constant does not drag pandas in.
"""
from __future__ import annotations

from typing import Any

ENGINE_VERSION = "price_pressure.v1"
SCHEMA_LATEST = "price_pressure.v1"

#: Ledger grading horizons — the five LSR-native ones plus the §5 t+60 tail.
#: t+60 is graded identically but is BEYOND THE MEASURED RECORD (LSR-P0 measured
#: 1..21); the schema and every published table label it as such.
LEDGER_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 21, 60)

#: The primary terminal window (§5.1).  21d, not 60d: it is inside the measured
#: record and aligned with DNR:LAW-REVERSION-RULER's ~20-25d time-exit ruler.
TERMINAL_PRIMARY = 21
#: The secondary ledger tail, graded identically, labeled beyond-the-record.
TERMINAL_SECONDARY = 60
#: Headline horizons for the published base-rate tables (§6).
HEADLINE_HORIZONS: tuple[int, ...] = (5, 21)

# ── §5.1 display-state taxonomy — EXHAUSTIVE on the running retrace fraction ──
# No σ-band dead zone: every observed close falls in exactly one bucket.  These
# are DISPLAY thresholds, not tuned alpha — they slice the same frozen
# distributions §6 publishes, and moving them re-cuts the published tables.
SLIDE_FRAC = -0.15       # frac ≤ −0.15 → still making residual lows
RETRACE_PARTIAL = 0.33   # RETRACING floor / PARTIAL floor
RETRACE_FULL = 0.80      # RECOVERED floor
FULL_RETRACE = 1.00      # observational only — days_to_first_100pct_retrace

#: Denominator guard for the retrace fraction (§5): |log1p(resid_t0)| below this
#: makes the ratio meaningless, so the fraction is NULL rather than explosive.
LOG_DENOM_FLOOR = 0.02

#: A same-side shock landing within this many SESSIONS of the newest shock in an
#: open episode joins that episode (§5).  Per-horizon honest-N uses `first_in_h`.
EPISODE_JOIN_SESSIONS = 5

#: Bars that stop more than this many sessions before the store's newest session
#: mean the name is gone, not that the window is young: the row grades
#: DELISTED_OR_HALTED and stays INSIDE the terminal denominator (§5 honesty
#: invariants — resolution-conditioned denominators delete losers).
DEAD_TAPE_SESSIONS = 10

#: Ordering law (§9, review finding 11): every list this lobe emits — artifact
#: events, market-packet lines, report rows — is most-recent-first then ticker
#: alphabetical.  Ordering by |z| or |resid| would be the ranking authority the
#: artifact explicitly denies.
ORDER_BY: tuple[str, ...] = ("date desc", "ticker asc")

#: Cap per side on the artifact's tracked-event list (§9).
TOP_EVENTS_PER_SIDE = 12

_LAZY = {
    "artifact": "engine.price_pressure.artifact",
    "backfill": "engine.price_pressure.backfill",
    "base_rates": "engine.price_pressure.base_rates",
    "completion": "engine.price_pressure.completion",
    "context": "engine.price_pressure.context",
    "detect": "engine.price_pressure.detect",
    "ledger": "engine.price_pressure.ledger",
    "panel": "engine.price_pressure.panel",
}


def __getattr__(name: str) -> Any:
    """Lazy submodule access — ``engine.price_pressure.ledger`` on first touch."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return importlib.import_module(target)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
