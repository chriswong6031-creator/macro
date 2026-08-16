"""CN breathing-platform rescue classifier (CN-PR-4, spec §8).

Read-only diagnosis. Maps a miss to its stage and names the lever. Alert-only
in v1: asia-close already self-retries, and the no-blind-dispatch invariants
forbid this script from firing a bake. The VPS 10-minute heartbeat covers the
evaluator process via the health clause; this classifier answers *which* stage
is dark so an operator does not guess.

Stages, upstream first:

    pack_missing      arm step / build_cn_live_pack
    evaluator_dead    no artifact tick (or the tick is older than the cadence)
    quotes_stale      artifact ticking, quote_age flat
    publish_failed    R2 fresh, served stale or vice versa
    route_broken      served fresh, reader 4xx/5xx
    client_stale      route fresh, page shows N−1
    settlement_late   asia-close no success by 12:00 UTC
    ok                nothing to rescue (including quiet phases)

Lunch, pre-open, holidays and weekends expect quiet — those phases cannot
produce evaluator_dead or quotes_stale. A missing pack is still a miss: the
asia-close arm is what should have written it the night before.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

STAGES: tuple[str, ...] = (
    "pack_missing",
    "evaluator_dead",
    "quotes_stale",
    "publish_failed",
    "route_broken",
    "client_stale",
    "settlement_late",
    "ok",
)

QUIET_PHASES = frozenset({
    "holiday", "weekend", "pre_open", "session_break", "closed",
})

#: 5-minute timer plus slack: two missed ticks is dead, one is absorbed.
EVALUATOR_TICK_DEAD_SEC = 20 * 60
#: Quote age that means the plane is frozen while the evaluator is still
#: rewriting the shell. The feed's declared delay is 15 minutes; 30 minutes
#: of p50 age is a flat tape, not a delayed-but-alive one.
QUOTE_STALE_SEC = 30 * 60
SETTLEMENT_DEADLINE_UTC = "12:00"

LEVERS = {
    "pack_missing": "asia-close arm step / scripts/build_cn_live_pack.py",
    "evaluator_dead": "macro-live-cnprophet.timer / scripts/cn_live_evaluator.py",
    "quotes_stale": "VPS quotes plane / fetch_quotes",
    "publish_failed": "atomic served write / R2 PUT of cn_prophet_live.json",
    "route_broken": "Caddy /live/ allowlist or auth gate",
    "client_stale": "cache-bust / china_stocks feed floor",
    "settlement_late": "asia-close.yml / reconcile_cn_live --asia",
    "ok": None,
}


def _utc(now: datetime | None) -> datetime:
    t = now or datetime.now(timezone.utc)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _verdict(stage: str, *, detail: str | None = None) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    out: dict[str, Any] = {
        "schema": "cn_live_rescue.classify/v1",
        "stage": stage,
        "lever": LEVERS[stage],
        "alert_only": True,
    }
    if detail:
        out["detail"] = detail
    return out


def _present(block: object) -> bool:
    return isinstance(block, dict) and bool(block.get("present"))


def classify(obs: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Map a bag of observations to one stage. Missing keys mean unmeasured.

    Expected keys (all optional)::

        market_phase: str
        pack:        {present: bool}
        artifact:    {present, tick_age_sec, quote_age_sec_p50, session, built_at}
        r2_states:   {present, built_at}
        served:      {present, built_at}
        route:       {status: int}
        client:      {page_session: str}
        asia_close:  {success: bool}
    """
    ts = _utc(now)
    phase = str(obs.get("market_phase") or "")
    quiet = phase in QUIET_PHASES

    pack = obs.get("pack") if isinstance(obs.get("pack"), dict) else {}
    if pack and not _present(pack):
        return _verdict("pack_missing", detail="armed pack is not on R2")

    art = obs.get("artifact") if isinstance(obs.get("artifact"), dict) else {}
    if art and not _present(art):
        if quiet:
            return _verdict("ok", detail=f"{phase or 'quiet'} phase, no artifact expected")
        return _verdict("evaluator_dead", detail="no served CN artifact")

    if art and not quiet:
        try:
            tick_age = float(art["tick_age_sec"]) if art.get("tick_age_sec") is not None else None
        except (TypeError, ValueError):
            tick_age = None
        if tick_age is not None and tick_age > EVALUATOR_TICK_DEAD_SEC:
            return _verdict(
                "evaluator_dead",
                detail=f"last tick {tick_age:.0f}s ago (dead after {EVALUATOR_TICK_DEAD_SEC}s)",
            )
        try:
            qage = (
                float(art["quote_age_sec_p50"])
                if art.get("quote_age_sec_p50") is not None else None
            )
        except (TypeError, ValueError):
            qage = None
        if qage is not None and qage > QUOTE_STALE_SEC:
            return _verdict(
                "quotes_stale",
                detail=f"quote_age p50 {qage:.0f}s (flat after {QUOTE_STALE_SEC}s)",
            )

    r2 = obs.get("r2_states") if isinstance(obs.get("r2_states"), dict) else {}
    served = obs.get("served") if isinstance(obs.get("served"), dict) else {}
    if _present(r2) and _present(served):
        r2_at, served_at = r2.get("built_at"), served.get("built_at")
        if r2_at and served_at and r2_at != served_at:
            return _verdict(
                "publish_failed",
                detail=f"R2 built_at={r2_at} served built_at={served_at}",
            )
        if r2.get("present") and not served.get("present"):
            return _verdict("publish_failed", detail="R2 has the artifact, served does not")
        if served.get("present") and not r2.get("present"):
            return _verdict("publish_failed", detail="served has the artifact, R2 does not")

    route = obs.get("route") if isinstance(obs.get("route"), dict) else {}
    try:
        status = int(route["status"]) if route.get("status") is not None else None
    except (TypeError, ValueError):
        status = None
    if status is not None and status >= 400:
        return _verdict("route_broken", detail=f"reader HTTP {status}")

    client = obs.get("client") if isinstance(obs.get("client"), dict) else {}
    page_session = client.get("page_session")
    art_session = art.get("session") if art else None
    if (
        isinstance(page_session, str) and page_session
        and isinstance(art_session, str) and art_session
        and page_session < art_session
    ):
        return _verdict(
            "client_stale",
            detail=f"page session {page_session} < artifact {art_session}",
        )

    asia = obs.get("asia_close") if isinstance(obs.get("asia_close"), dict) else {}
    if ts.strftime("%H:%M") >= SETTLEMENT_DEADLINE_UTC and asia and not asia.get("success"):
        return _verdict(
            "settlement_late",
            detail=f"no asia-close success by {SETTLEMENT_DEADLINE_UTC} UTC",
        )

    return _verdict("ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--classify", action="store_true",
                        help="read a JSON observation bag and print one verdict")
    parser.add_argument("--input", default="-",
                        help="path to the observation JSON, or - for stdin")
    args = parser.parse_args(argv)
    if not args.classify:
        parser.error("v1 is classify-only; pass --classify")
    if args.input == "-":
        raw = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as fh:
            raw = fh.read()
    try:
        obs = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"cn_live_rescue: invalid JSON ({exc})", file=sys.stderr)
        return 2
    if not isinstance(obs, dict):
        print("cn_live_rescue: observation bag must be an object", file=sys.stderr)
        return 2
    print(json.dumps(classify(obs), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
