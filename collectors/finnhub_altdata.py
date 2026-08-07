"""Finnhub alt-data trio — analyst recommendation trends, insider sentiment (MSPR), and
earnings surprises. Uses the FINNHUB key the repo ALREADY has (free tier, 60 req/min).

Three per-ticker endpoints, queried over a capped narrative-basket watchlist:
  * /stock/recommendation-trends — strongBuy/buy/hold/sell/strongSell per month  -> analyst tilt
  * /stock/insider-sentiment     — monthly MSPR (net insider sentiment, pre-aggregated)
  * /stock/earnings              — last quarters' actual/estimate/surprisePercent

These feed the per-ticker convergence kernel as the analyst_upgrade_cluster / insider_mspr /
earnings_beat channels — cross-checks that complement (never replace) the Quiver/SEC insider
feeds. Three append-only key-deduped tables under data/finnhub/. GATED: no FINNHUB key ->
'blocked', non-fatal.

AUTH/PLAN GATES ARE NAMED, NOT COUNTED (2026-08-05)
--------------------------------------------------
This collector failed every night with ``no rows from 120 tickers (errors=120)`` and
nobody could act on it, because that sentence does not distinguish a rejected key from
an endpoint that moved to a paid tier — and both look identical to a transient outage.
``data/finnhub/recommendation.parquet`` has therefore NEVER existed, and seven
consumers (build_leader_radar, altdata, stock_fundamentals, eightk_magnitude,
moat_falsifiers, neuralweb.theme_asymmetry, 2 synapse artifacts) have been reading a
missing store and failing open to null the whole time.

Two fixes, mirroring the pattern already proven in collectors/finnhub_transcripts.py:

1. **Classify and stop.** A 401/403 (or a 200 carrying an ``error`` payload) is an
   auth/plan gate, not an outage: it is reported by NAME through ``expected_failure``
   (status 'blocked' — a known limitation that does NOT wedge the circuit breaker) with
   a ``::warning`` annotation so it is visible in the Actions summary, and the sweep
   stops on the first one instead of spending 120 tickers x 3 endpoints x 2 retries
   x backoff proving the same wall (the failing run burned 106s doing exactly that).
   401 => rotate the key; 403 => the endpoint left the free tier. The next nightly run
   now says which.

2. **Per-endpoint isolation.** The three calls used to share one try-block, so a gate on
   the SECOND endpoint silently cost the third for every ticker. They are independent
   now: whichever endpoints the plan still serves keep flowing.

Anything that is not an auth/plan gate (network, 5xx, unparseable) still raises and is
still reported 'failed' — a genuinely broken source must not be laundered into 'blocked'.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

BASE = "https://finnhub.io/api/v1"
MAX_TICKERS = 120          # 3 calls each -> ~360 calls; ~6 min at the 60/min free cap
PACE_S = 0.9               # stay under 60 req/min
RATE_LIMIT_GIVEUP = 5      # consecutive 429s on one endpoint -> stop asking, by name

# HTTP codes that mean "this key/plan may not have this endpoint" — never a retry.
_GATE_STATUS = {401: "key rejected (401) — rotate FINNHUB_API_KEY",
                403: "plan-gated (403) — endpoint not on the current Finnhub tier"}
_GATE_WORDS = ("permission", "plan", "access", "unauthorized", "forbidden",
               "premium", "subscribe")


def _key() -> str | None:
    return config.secret("FINNHUB_API_KEY") or config.secret("FINNHUB_KEY")


def _is_rate_limited(exc: Exception) -> bool:
    """True for an HTTP 429. Same structured-then-anchored-regex shape as
    gate_reason_from_exc, so a ticker or timestamp containing '429' cannot match."""
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        m = re.search(r"(?<!\d)429(?!\d)", str(exc))
        code = 429 if m else None
    return code == 429


def gate_reason_from_exc(exc: Exception) -> str | None:
    """Auth/plan-gate reason for *exc*, or None if it is some other failure.

    Prefers the structured ``exc.response.status_code`` (base.http_get re-raises the
    ``requests.HTTPError`` from ``raise_for_status``, which carries the response), and
    falls back to matching a bare 401/403 token in the message. The fallback is
    deliberately anchored so a ticker or timestamp containing "403" cannot match.
    """
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        m = re.search(r"(?<!\d)(401|403)(?!\d)", str(exc))
        code = int(m.group(1)) if m else None
    return _GATE_STATUS.get(code)


def gate_reason_from_payload(data) -> str | None:
    """Finnhub also answers HTTP 200 with ``{"error": "..."}``. Treat the entitlement
    wordings as a gate; anything else is just an empty read."""
    if not isinstance(data, dict):
        return None
    err = data.get("error")
    if not err:
        return None
    low = str(err).lower()
    if any(w in low for w in _GATE_WORDS):
        return f"plan/permission error payload — {str(err)[:120]}"
    return None


class FinnhubAltdataAdapter(Adapter):
    name = "finnhub_altdata"
    group = "finnhub"
    stale_after_days = 5

    def __init__(self) -> None:
        self.api_key = _key()
        self._gate: str | None = None   # set on a whole-key/plan gate; stops the sweep
        if not self.api_key:
            self.expected_failure = "FINNHUB_API_KEY/FINNHUB_KEY not set"

    def _get(self, path: str, params: dict) -> list | dict | None:
        params = {**params, "token": self.api_key}
        r = self.http_get(f"{BASE}{path}", params=params, retries=2, timeout=30)
        return r.json()

    def _merge(self, dataset: str, new: pd.DataFrame, keys: list[str]) -> int:
        if new.empty:
            return 0
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / self.group / f"{dataset}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        k = [c for c in keys if c in combined.columns]
        combined = combined.drop_duplicates(subset=k or None, keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        return len(new)

    def _call(self, endpoint: str, path: str, params: dict):
        """One endpoint call. Returns (payload, gate_reason). Raises on a real failure.

        `gate_reason` non-None means auth/plan — the caller must stop the whole sweep,
        not retry it. A gate is recorded once per endpoint so the reason names the
        endpoint that is actually gated, which is what tells 401 (key) from 403 (tier).
        """
        if self._gate:
            return None, self._gate
        try:
            data = self._get(path, params)
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            reason = gate_reason_from_exc(e)
            if reason:
                return None, f"{endpoint}: {reason}"
            raise
        reason = gate_reason_from_payload(data)
        if reason:
            return None, f"{endpoint}: {reason}"
        return data, None

    def _trip_gate(self, reason: str, watch_n: int) -> None:
        """Name the gate: expected_failure -> status 'blocked', plus a visible annotation.

        The annotation is a bare print (NOT log.warning): every logger here prefixes the
        level, and GitHub only parses `::warning` at the START of a line.
        """
        self._gate = reason
        self.expected_failure = f"finnhub_altdata {reason}"
        print(f"::warning title=finnhub-altdata-gated::{reason} — sweep stopped after "
              f"the first gate (watchlist {watch_n}); recommendation/insider/earnings "
              f"channels stay dark until this is resolved", flush=True)
        log.warning("finnhub_altdata gated: %s", reason)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("FINNHUB key not set")
        watch = basket_members(cap=MAX_TICKERS)
        if not watch:
            raise ValueError("finnhub_altdata: empty watchlist")
        end = datetime.now(timezone.utc).date()
        since = (end - timedelta(days=120)).isoformat()
        rec_rows, mspr_rows, earn_rows = [], [], []
        errors = 0
        # Per-endpoint gates: one paid endpoint must not cost the endpoints after it.
        dead: set[str] = set()
        # Rate-limited endpoints, kept SEPARATE from `dead` on purpose (see below).
        throttled: set[str] = set()
        rl_streak: dict[str, int] = {}

        for tk in watch:
            if self._gate:
                break
            for endpoint, path, params in (
                ("recommendation-trends", "/stock/recommendation-trends", {"symbol": tk}),
                ("insider-sentiment", "/stock/insider-sentiment",
                 {"symbol": tk, "from": since, "to": end.isoformat()}),
                ("earnings", "/stock/earnings", {"symbol": tk, "limit": 4}),
            ):
                if endpoint in dead or endpoint in throttled:
                    continue
                try:
                    data, gate = self._call(endpoint, path, params)
                except Exception as e:  # noqa: BLE001
                    if is_connection_error(e):
                        raise
                    errors += 1
                    log.debug("finnhub_altdata %s %s: %s", tk, endpoint, e)
                    # RATE-LIMIT BACKSTOP (2026-08-06). Errors used to `continue` past
                    # the pace sleep below (see the finally), so the first burst of
                    # failures removed the only rate limiting this sweep had and the
                    # run hammered the API into a self-sustaining 429 wall — the
                    # 2026-08-05 nightly burned 116s to reach "no rows from 120
                    # tickers (errors=120)". Pacing is now unconditional, and once an
                    # endpoint answers 429 this many times in a row there is nothing
                    # left to learn by asking 300 more times: stop it by NAME.
                    # NOT added to `dead` — `dead` means auth/plan, which reports
                    # 'blocked' (a known limitation). A throttle is transient and must
                    # stay a real failure, or a rate-limited night launders itself into
                    # an expected one.
                    if _is_rate_limited(e):
                        rl_streak[endpoint] = rl_streak.get(endpoint, 0) + 1
                        if rl_streak[endpoint] >= RATE_LIMIT_GIVEUP:
                            throttled.add(endpoint)
                            log.warning("finnhub_altdata: %s rate-limited %dx in a row "
                                        "— stopping that endpoint for this run",
                                        endpoint, rl_streak[endpoint])
                    else:
                        rl_streak[endpoint] = 0
                    continue
                finally:
                    # Pace EVERY attempted call, not just the ones that worked.
                    time.sleep(PACE_S)
                rl_streak[endpoint] = 0
                if gate:
                    dead.add(endpoint)
                    # every endpoint gated => the key/plan itself is the problem
                    if len(dead) == 3:
                        self._trip_gate(gate, len(watch))
                    else:
                        log.warning("finnhub_altdata: %s gated (%s) — other channels continue",
                                    endpoint, gate)
                    continue
                if endpoint == "recommendation-trends":
                    rt = data or []
                    if isinstance(rt, list) and rt:
                        r0 = rt[0]  # most recent period
                        rec_rows.append({"ticker": tk, "period": r0.get("period"),
                                         "strongBuy": r0.get("strongBuy"), "buy": r0.get("buy"),
                                         "hold": r0.get("hold"), "sell": r0.get("sell"),
                                         "strongSell": r0.get("strongSell"),
                                         "prev_buy": (rt[1].get("strongBuy", 0) + rt[1].get("buy", 0)) if len(rt) > 1 else None})
                elif endpoint == "insider-sentiment":
                    for d in (data or {}).get("data", [])[-3:]:
                        mspr_rows.append({"ticker": tk, "year": d.get("year"), "month": d.get("month"),
                                          "mspr": d.get("mspr"), "change": d.get("change")})
                else:
                    ea = data or []
                    for d in (ea if isinstance(ea, list) else [])[:2]:
                        earn_rows.append({"ticker": tk, "period": d.get("period"), "actual": d.get("actual"),
                                          "estimate": d.get("estimate"), "surprisePercent": d.get("surprisePercent")})

        n = (self._merge("recommendation", pd.DataFrame(rec_rows), ["ticker", "period"])
             + self._merge("insider_sentiment", pd.DataFrame(mspr_rows), ["ticker", "year", "month"])
             + self._merge("earnings", pd.DataFrame(earn_rows), ["ticker", "period"]))
        if n == 0:
            if self._gate:
                # expected_failure is set -> the runner reports 'blocked', with the reason
                raise RuntimeError(f"finnhub_altdata: {self._gate}")
            gated = f"; gated endpoints: {sorted(dead)}" if dead else ""
            # Name the throttle in the sentence the operator actually reads
            # (run_status.json sources.finnhub_altdata.error). "no rows from 120
            # tickers (errors=120)" is the message that made this un-actionable for
            # 17 nights: it cannot tell a rejected key from a rate limit from an
            # outage. 429 is transient and needs a different response than a gate.
            rl = (f"; RATE-LIMITED endpoints (stopped after {RATE_LIMIT_GIVEUP} "
                  f"consecutive HTTP 429): {sorted(throttled)}") if throttled else ""
            raise RuntimeError(
                f"finnhub_altdata: no rows from {len(watch)} tickers "
                f"(errors={errors}{gated}{rl}) — not an auth/plan gate, so this is a "
                f"real failure")
        if dead:
            print(f"::warning title=finnhub-altdata-partial::endpoints gated: "
                  f"{sorted(dead)} — those channels stay dark, the rest ingested "
                  f"{n} rows", flush=True)
        log.info("finnhub_altdata: %d watch, +%d rows (rec=%d mspr=%d earn=%d), %d errors",
                 len(watch), n, len(rec_rows), len(mspr_rows), len(earn_rows), errors)
        ingest = pd.DataFrame({"new_rows": [n], "watch": [len(watch)],
                               "gated_endpoints": [",".join(sorted(dead))]},
                              index=[pd.Timestamp(end)])
        return {"finnhub_altdata__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinnhubAltdataAdapter().fetch()
