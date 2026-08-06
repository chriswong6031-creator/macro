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
kill the rest (per-module try/except); the adapter raises when the token is
present and EVERY module failed (a real API outage the breaker should see), or
when the vendor REJECTED the token and nothing landed rows (see fetch()).
Token absent → ``expected_failure`` is set so the runner reports 'blocked',
never a breaker-counted failure. Token present but rejected is NOT expected —
it is an outage, and ``expected_failure`` stays unset so the breaker counts it.
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
        # AUTH REJECTION — the failure mode that hid for 10 days. When the vendor rejects the
        # token (code 40101), query() returns None for EVERY endpoint, so no sub-module raises:
        # each one simply returns 0 rows, the heartbeat frame below is written with 0.0 (not the
        # -1.0 an exception would have left), the adapter reports status=ok, and run_status, the
        # circuit breaker and every freshness guard see a healthy plane. That is exactly how
        # data/tushare/*.parquet sat frozen at 2026-07-24 from 2026-07-27 to 2026-08-06 with the
        # nightly reporting success. A rejected credential is an OUTAGE, so raise it: no heartbeat
        # row is written for the night, which is the honest signal the freshness guards can see,
        # and the breaker counts it. Recovery self-clears (the latch resets on any code==0).
        auth = tushare_client.last_auth_error()
        if auth and not any(v > 0 for v in rows.values()):
            code, msg = auth.get("code"), auth.get("msg")
            detail = (f"tushare code={code} {msg} — TUSHARE_TOKEN secret is SET but the vendor "
                      "rejects it (dark since 2026-07-27); regenerate the token in the "
                      "tushare.pro account page and update the GitHub secret TUSHARE_TOKEN")
            # BARE print at line start — GitHub only parses '::' at column 0, and every logger
            # here prefixes the line (tests/test_gh_annotation_line_start.py).
            print(f"::error title=tushare-auth-rejected::{detail}", flush=True)
            raise RuntimeError(detail)
        if errors and len(errors) == len(_MODULES):
            raise RuntimeError(f"all tushare sub-modules failed: {'; '.join(errors[:3])}")
        if auth:
            # PARTIAL: some module still landed rows (a per-endpoint entitlement quirk, or a
            # token that healed mid-loop). Do not fail the night over a plane that is producing.
            log.warning("china_tushare: vendor auth rejection on %s (code=%s %s) but %d module(s) "
                        "still returned rows — not raising; check TUSHARE_TOKEN",
                        auth.get("api_name"), auth.get("code"), auth.get("msg"),
                        sum(1 for v in rows.values() if v > 0))
        hb = pd.DataFrame([rows], index=[pd.Timestamp.utcnow().normalize().tz_localize(None)])
        return {"run_log": hb}
