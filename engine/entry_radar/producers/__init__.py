"""engine/entry_radar/producers — one adapter per nomination producer.

Every adapter reads ONE artifact, decides its availability, and emits
`mastermind.entry_probe_nomination.v1` records.  None of them computes an
indicator, ranks anything, or combines sources — see ``base.py`` for the shared
contract and ``nomination_bus.py`` for what happens after the door.

REGISTRY (Track C receipt → adapter):

  Track C #22  ``site/factordata/us_standouts.json``      boards.read_us_standouts
  Track C #22  ``site/factordata/setups.json``            boards.read_setups
  Track C #23  ``site/stockdata/<T>.json``                boards.read_stock_library  (features only)
  Track C #25  ``site/basketdata/pulse.json``             baskets.read_group_pulse   (membership_expansion)
  Track C #27  ``site/basketdata/linked_outsiders.json``  baskets.read_linked_outsiders
  Track C #13  ``site/live/flow_pulse.json``              live_flow.read_flow_pulse
  Track C #21  ``data/ipo/calendar.parquet``              ipo.read_ipo_calendar
  Track C §2   ``data/breadth/constituents.parquet`` +…   constituents.read_universe_sources
  Track C §2   Supabase watchlists/portfolio_positions    universe.SupabaseWatchlistAdapter
  Track C #28  ``engine/marketing/hot_tape.py`` (no artifact)  spool.tap_hot_tape_events

DELIBERATELY NOT ADAPTED IN PR-1, each for a stated reason:

  * ``capital_structure`` — API-gated, not artifact-based (Track C #29); needs an
    authenticated integration, structurally unlike every row here.
  * ``state_of_themes`` / ``radar`` / ``foresight`` — theme-scored, with NO
    single-name producer at their headline level (Track C §3).  Any nomination
    from them would have to come through a separate artifact, and a basket-level
    fact must never launder into a single-name one (§6).
  * The options family — four builds with overlapping but non-identical
    universes and no unified per-symbol store (Track C §3); picking one
    arbitrarily would misreport coverage.
  * 13F / FINRA / insider families — quarterly-to-weekly cadence with a ~45d
    filing lag; they belong to a later PR's slower lane, not to a 5-minute bus.
"""
from __future__ import annotations

from engine.entry_radar.producers.base import (
    AdapterResult,
    build_read,
    grade_staleness,
    read_json,
    stale_after,
    unavailable,
)
from engine.entry_radar.producers.baskets import (
    LINKED_OUTSIDERS_SOURCE_ID,
    PULSE_SOURCE_ID,
    read_group_pulse,
    read_linked_outsiders,
)
from engine.entry_radar.producers.boards import (
    SETUPS_SOURCE_ID,
    STANDOUTS_SOURCE_ID,
    STOCK_LIBRARY_SOURCE_ID,
    read_setups,
    read_stock_library,
    read_us_standouts,
)
from engine.entry_radar.producers.constituents import (
    DEFAULT_SOURCES,
    MEMBERSHIP_KEYS,
    memberships_from,
    names_from,
    read_universe_sources,
    sectors_from,
)
from engine.entry_radar.producers.ipo import IPO_SOURCE_ID, read_ipo_calendar
from engine.entry_radar.producers.live_flow import FLOW_PULSE_SOURCE_ID, read_flow_pulse

__all__ = [
    "AdapterResult",
    "DEFAULT_SOURCES",
    "FLOW_PULSE_SOURCE_ID",
    "IPO_SOURCE_ID",
    "LINKED_OUTSIDERS_SOURCE_ID",
    "MEMBERSHIP_KEYS",
    "PULSE_SOURCE_ID",
    "SETUPS_SOURCE_ID",
    "STANDOUTS_SOURCE_ID",
    "STOCK_LIBRARY_SOURCE_ID",
    "build_read",
    "grade_staleness",
    "memberships_from",
    "names_from",
    "read_flow_pulse",
    "read_group_pulse",
    "read_ipo_calendar",
    "read_json",
    "read_linked_outsiders",
    "read_setups",
    "read_stock_library",
    "read_universe_sources",
    "read_us_standouts",
    "sectors_from",
    "stale_after",
    "unavailable",
]
