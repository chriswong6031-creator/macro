"""Run-adapter wrapper for the gated Tushare plane (china_tushare).

Root cause this fixes (masterplan §W6-CN / CHINA_ENGINE_REASSESSMENT): the
tushare_* collectors are standalone modules with ``refresh()`` entry points that
were NEVER registered in scripts/collect.py's adapter registry — the asia shard
is a china*/hk* PREFIX match, so nothing in CI ever invoked them and the plane
froze at the last token-bearing dev commit (2026-06-21). This adapter's name
starts with ``china`` so the asia lane picks it up automatically, and running
through ``run_adapter`` gives the plane run_status/circuit-breaker health for
free (which engine/tushare_freshness.py's consume-time badge reads).

Each sub-module writes its own ``data/tushare/*.parquet`` directly inside
``refresh()``; the frame returned here is a small per-module heartbeat row so
the runner has something dated to health-check. One sub-module failing must not
kill the rest (per-module try/except); the adapter raises only when the token
is present and EVERY module failed (a real API outage the breaker should see).
Token absent → ``expected_failure`` is set so the runner reports 'blocked',
never a breaker-counted failure.

HEARTBEAT LIVENESS (2026-08-05). The heartbeat is stamped ``utcnow()``, so it is
fresh whether or not anything was collected, and the runner's freshness machinery
reads only the frames an adapter RETURNS — never the ``data/tushare/*.parquet``
the sub-modules write. That makes this plane's real stores invisible to
``stale_after_days`` and to ``detect_stale_series`` alike. From 2026-07-27 the
token was set, every ``refresh()`` returned 0 (``tushare_client.query`` degrades
to None on a denied/expired plan), and the adapter reported 'ok' for ten
consecutive nights while every store sat frozen at the 07-24 close.
``fetch_result_status`` below closes that hole by deriving status from the
heartbeat's VALUES, which are the only liveness signal it actually carries.
"""
from __future__ import annotations

import importlib
import logging

import pandas as pd

from collectors import tushare_client
from collectors.base import Adapter

log = logging.getLogger(__name__)

# Daily-cadence order first; heavier/backfill-style modules last so a timeout
# still lands the highest-value planes.
_MODULES = (
    "tushare_valuation",   # real mktcaps (feeds the ==30亿 sentinel fix)
    "tushare_moneyflow",   # sector moneyflow (china_radar)
    "tushare_margin",      # per-name margin (crowding froth, normalized by circ_mv)
    "tushare_chips",       # chip distribution
    "tushare_broker",      # broker seats
    "tushare_forecast",    # earnings guidance
    "tushare_history",     # grid backfill (bounded by _GRID_DAYS)
)


class ChinaTushareAdapter(Adapter):
    name = "china_tushare"
    group = "china_tushare"          # heartbeat store; sub-modules own data/tushare/*
    stale_after_days = 4             # daily plane, weekend/holiday tolerant

    def __init__(self) -> None:
        if not tushare_client.enabled():
            # runner reports 'blocked' (known-gated), never a breaker failure
            self.expected_failure = "TUSHARE_TOKEN absent — gated plane skipped"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not tushare_client.enabled():
            raise RuntimeError("TUSHARE_TOKEN absent — gated tushare plane skipped")
        rows: dict[str, float] = {}
        errors: list[str] = []
        for mod_name in _MODULES:
            try:
                mod = importlib.import_module(f"collectors.{mod_name}")
                rows[mod_name] = float(mod.refresh())
            except Exception as e:  # noqa: BLE001 — one plane down must not kill the rest
                rows[mod_name] = -1.0
                errors.append(f"{mod_name}: {e}")
                log.warning("china_tushare sub-module %s failed: %s", mod_name, e)
        if errors and len(errors) == len(_MODULES):
            raise RuntimeError(f"all tushare sub-modules failed: {'; '.join(errors[:3])}")
        if not any(v > 0 for v in rows.values()):
            # THE SILENT FAILURE. `refresh()` returns 0 — never raises — when
            # tushare_client.query() degrades to None, which it does for an
            # expired membership, exhausted 积分, or a denied endpoint just as
            # readily as for a genuinely empty response. Every module returning
            # 0 means the gate was OPEN (a closed gate raises above, before this
            # line) and the API still handed back nothing across seven distinct
            # endpoints — an outage, not a quiet day. A snapshot module re-fetches
            # its whole cross-section every run and reports thousands of rows even
            # on a weekend, so an all-zero pass is anomalous by construction.
            #
            # This ran unnoticed 2026-07-27 → 08-05: data/tushare/*.parquet froze
            # at the 07-24 close, taking the A-share legs of site/flowdata/desk.json
            # (and chips/margin/valuation/moneyflow/forecast/broker) dark for 10
            # nights with nothing red anywhere.
            print("::warning title=china-tushare-zero-collection::TUSHARE_TOKEN is set but "
                  f"all {len(_MODULES)} tushare modules collected 0 rows — the API returned "
                  "nothing across every endpoint (expired membership, exhausted 积分, or a "
                  "denied plan). data/tushare/*.parquet is FROZEN this run; every CN surface "
                  "fed by it (flow velocity, chips, margin, valuation, moneyflow) silently "
                  "serves its last vintage.", flush=True)
            log.warning("china_tushare: gate open but every module collected 0 rows")
        hb = pd.DataFrame([rows], index=[pd.Timestamp.utcnow().normalize().tz_localize(None)])
        return {"run_log": hb}

    def fetch_result_status(self, frames: dict[str, pd.DataFrame]) -> str | None:
        """Report 'stale' for a run that collected nothing.

        The heartbeat above is stamped ``utcnow()``, so it is fresh BY
        CONSTRUCTION: run_adapter's ``age > stale_after_days`` check and
        detect_stale_series both read this adapter's only series and both see
        today's date, every night, whether or not a single row was collected.
        Every freshness guard in the collector framework is therefore
        structurally blind to this plane — which is why a 10-night outage
        reported 'ok' 10 times.

        The row VALUES are the only honest liveness signal the heartbeat
        carries, so status is derived from them. 'stale' and not a raise:
        update_breaker treats it as a definitive outcome that CLEARS the
        breaker, which is right — the adapter did its job, the upstream had
        nothing to give, and wedging the circuit would suppress the recovery
        probe that ends the outage.
        """
        hb = frames.get("run_log")
        if hb is None or hb.empty:
            return None
        counts = [v for v in hb.iloc[-1].tolist()
                  if isinstance(v, (int, float)) and not pd.isna(v)]
        if counts and not any(v > 0 for v in counts):
            return "stale"
        return None
