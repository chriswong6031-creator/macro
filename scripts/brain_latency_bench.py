#!/usr/bin/env python3
"""Measure Mastermind brain latency end-to-end against a running gateway.

WHY THIS EXISTS
    "Mastermind feels slow" was an argument until the competitive teardown measured it:
    headers in 0.5-0.8s, then 48-73 seconds of blocking tool rounds before the first
    answer byte, against a competitor's 2.14s on a one-line price question
    (research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md
    §6.3 and §6.7). This script is how that measurement is re-run — same prompts, same
    surface, one table.

WHAT IT MEASURES (per probe, client-side, wall clock from the request going out)
    headers_ms       response headers back (the network + auth + quota preamble)
    first_status_ms  first `status` SSE event (the widget's first sign of life)
    ttfv_ms          first `delta` event — time to first VISIBLE answer byte
    done_ms          the `done` event
    n_deltas         how many delta events carried the answer
    n_tool_events    tool rounds the turn spent
    route            'instant' | 'deep', read from done.usage.latency.route

    A server without the W5 latency work simply has no route/latency keys; those
    columns print "-" and every timing above still works.

NO LEDGER WRITES. This is a probe, not a pipeline: results go to stdout, and to a
JSONL file only when --out names one. Nothing under data/ is ever touched (house law:
nightly is the sole advancer of forward ledgers).

USAGE
    python3 scripts/brain_latency_bench.py --cookie "$MM_AID" --label cold
    python3 scripts/brain_latency_bench.py --bearer "$SUPABASE_ACCESS_TOKEN" --runs 3 --label warm
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# The docket's benchmark prompts
# ---------------------------------------------------------------------------
# Reproduced from
# research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md §6.3
# ("Prompt class" / "Prompt" columns), which is also the set the live A/B in §6.7 sent.
# Keep the wording stable — the recorded 27.33s / 9.81s / 2.14s competitor numbers and
# the 56.68s / 52.12s Mastermind numbers are only comparable against these asks.
#
# The fourth entry is NOT from the docket. The docket's "simple current fact" prompt
# carries three extra instructions (one sentence, source, exact as-of), and the W5
# instant router deliberately refuses anything that elaborate — it is biased hard
# towards falling through to the deep loop. This bare form is the shape the instant
# lane actually claims, so the table can show both sides of the same question.
DOCKET_PROMPTS: tuple[tuple[str, str], ...] = (
    ("broad",
     "Give me situational awareness of the market right now: the regime, which themes "
     "are working, breadth, rates and liquidity, the catalysts ahead and the main "
     "risks. Cite your sources and timestamp every read."),
    ("native",
     "For AAPL give me relative strength over 1 month, 3 months and 12 months, its "
     "industry rank, its Stage, the next earnings date and the latest reported EPS "
     "growth. Give the as-of for each field and cite the source."),
    ("simple",
     "What is AAPL's current price? One sentence, with the source and the exact as-of."),
    ("instant",
     "What's AAPL trading at?"),
)

_COLUMNS = ("probe", "run", "headers_ms", "first_status_ms", "ttfv_ms", "done_ms",
            "n_deltas", "n_tool_events", "route")


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------

class SSEParser:
    """Incremental ``text/event-stream`` parser: feed one decoded line, get 0+ events.

    Only the pieces this endpoint uses are implemented: ``data:`` fields (joined with
    newlines across a multi-line event), a blank line as the dispatch boundary, and
    ``:`` comment lines — which matter, because the brain's run pump injects
    ``: keepalive`` comments through the dead air of a blocking tool turn and a parser
    that mistook one for an event would report a phantom first byte.

    A ``data:`` payload that is not JSON is dropped rather than raised on: this is a
    measuring instrument, and it must survive a degraded server well enough to report
    what it saw.
    """

    def __init__(self) -> None:
        self._data: list[str] = []

    def feed(self, line: str) -> list[dict]:
        line = line.rstrip("\n").rstrip("\r")
        if line.startswith(":"):
            return []                      # comment / keepalive
        if line == "":
            return self._dispatch()
        field, _, value = line.partition(":")
        if field == "data":
            self._data.append(value[1:] if value.startswith(" ") else value)
        return []                          # event:/id:/retry: are not used here

    def close(self) -> list[dict]:
        """Flush an event left pending by a stream that ended without a blank line."""
        return self._dispatch()

    def _dispatch(self) -> list[dict]:
        if not self._data:
            return []
        payload = "\n".join(self._data)
        self._data = []
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return []
        return [obj] if isinstance(obj, dict) else []


def read_events(lines: Iterable[str], clock=time.monotonic) -> list[tuple[dict, float]]:
    """Parse a whole SSE line stream into (event, arrival_clock) pairs."""
    parser = SSEParser()
    out: list[tuple[dict, float]] = []
    for line in lines:
        for ev in parser.feed(line):
            out.append((ev, clock()))
    for ev in parser.close():
        out.append((ev, clock()))
    return out


def summarize(events: list[tuple[dict, float]], t0: float, headers_ms: int | None) -> dict:
    """Fold parsed events into one probe row. Missing keys stay None → printed as '-'."""
    row: dict[str, Any] = {
        "headers_ms": headers_ms,
        "first_status_ms": None,
        "ttfv_ms": None,
        "done_ms": None,
        "n_deltas": 0,
        "n_tool_events": 0,
        "route": None,
        "server_latency": None,
        "answer_chars": 0,
        "degraded": None,
        "error": None,
    }
    for ev, at in events:
        kind = ev.get("type")
        ms = int((at - t0) * 1000)
        if kind == "status" and row["first_status_ms"] is None:
            row["first_status_ms"] = ms
        elif kind == "tool":
            row["n_tool_events"] += 1
        elif kind == "delta":
            if row["ttfv_ms"] is None:
                row["ttfv_ms"] = ms
            row["n_deltas"] += 1
            row["answer_chars"] += len(str(ev.get("text") or ""))
        elif kind == "done":
            row["done_ms"] = ms
            row["degraded"] = bool(ev.get("degraded"))
            latency = (ev.get("usage") or {}).get("latency")
            if isinstance(latency, dict):
                row["server_latency"] = latency
                row["route"] = latency.get("route") or row["route"]
            if not row["route"] and ev.get("route"):
                row["route"] = ev.get("route")
    return row


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

def probe(base_url: str, message: str, *, cookie: str = "", bearer: str = "",
          lane: str = "fast", page: str = "", symbol: str = "",
          timeout: float = 180.0) -> dict:
    """Send ONE prompt to POST /api/brain/stream and return its measured row."""
    url = base_url.rstrip("/") + "/api/brain/stream"
    body: dict[str, Any] = {"message": message, "lane": lane}
    context: dict[str, str] = {}
    if page:
        context["page"] = page
    if symbol:
        context["symbol"] = symbol
    if context:
        body["context"] = context

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream",
               "User-Agent": "brain-latency-bench/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if cookie:
        headers["Cookie"] = f"mm_aid={cookie}"

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    t0 = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — operator-supplied URL
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        hint = ""
        if exc.code in (401, 403):
            hint = " — pass --cookie (mm_aid) or --bearer; an unauthenticated probe is unmeterable"
        elif exc.code == 402:
            hint = " — quota exhausted for this principal"
        elif exc.code == 429:
            hint = " — burst throttle; slow the run down"
        return {"error": f"HTTP {exc.code}{hint}: {detail}".strip(),
                "headers_ms": int((time.monotonic() - t0) * 1000)}
    except urllib.error.URLError as exc:
        return {"error": f"cannot reach {url}: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"cannot reach {url}: {type(exc).__name__}: {exc}"}

    headers_ms = int((time.monotonic() - t0) * 1000)
    try:
        with resp:
            events = read_events((raw.decode("utf-8", "replace") for raw in resp))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"stream broke after headers: {type(exc).__name__}: {exc}",
                "headers_ms": headers_ms}
    return summarize(events, t0, headers_ms)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def print_table(rows: list[dict]) -> None:
    """Fixed-width table on stdout. Rows carrying an `error` print it under the row."""
    printable = [[_cell(r.get(c)) for c in _COLUMNS] for r in rows]
    widths = [max(len(_COLUMNS[i]), *(len(r[i]) for r in printable)) if printable
              else len(_COLUMNS[i]) for i in range(len(_COLUMNS))]
    header = "  ".join(h.ljust(widths[i]) for i, h in enumerate(_COLUMNS))
    print(header)
    print("  ".join("-" * w for w in widths))
    for row, cells in zip(rows, printable):
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)))
        if row.get("error"):
            print(f"    ! {row['error']}")


def print_medians(rows: list[dict]) -> None:
    """Per-probe medians — the number to quote when --runs > 1."""
    by_probe: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("error"):
            continue
        by_probe.setdefault(str(row.get("probe")), []).append(row)
    if not any(len(v) > 1 for v in by_probe.values()):
        return
    print("\nmedians")
    for name, group in by_probe.items():
        parts = []
        for key in ("headers_ms", "ttfv_ms", "done_ms"):
            vals = [r[key] for r in group if isinstance(r.get(key), int)]
            parts.append(f"{key}={int(statistics.median(vals))}" if vals else f"{key}=-")
        print(f"  {name}: " + "  ".join(parts) + f"  (n={len(group)})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brain_latency_bench",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", default="http://127.0.0.1:8000",
                   help="gateway origin (default: %(default)s)")
    p.add_argument("--cookie", default="",
                   help="mm_aid cookie value, sent as `Cookie: mm_aid=<value>`. The brain "
                        "routes authenticate as a verified user (--bearer) or, when guest "
                        "access is enabled, as a guest keyed on this cookie. WITHOUT either, "
                        "the request is refused 401: an anonymous probe has no principal to "
                        "meter, and an unmeterable turn is not the turn users get.")
    p.add_argument("--bearer", default="",
                   help="Supabase access token for a SIGNED-IN probe (the docket's §6.7 A/B "
                        "was authenticated). Wins over --cookie when both are given.")
    p.add_argument("--runs", type=int, default=1, help="repeats per prompt (default: 1)")
    p.add_argument("--label", default="cold", choices=("cold", "warm"),
                   help="tag for the run, recorded in --out rows (default: %(default)s). "
                        "'cold' = first probe after a restart (empty digest/packet caches); "
                        "'warm' = caches primed by a prior run.")
    p.add_argument("--lane", default="fast", choices=("fast", "pro"),
                   help="brain lane (default: %(default)s)")
    p.add_argument("--page", default="",
                   help="context.page to send, e.g. 'terminal' (default: none)")
    p.add_argument("--symbol", default="",
                   help="context.symbol chip to send (default: none)")
    p.add_argument("--only", default="", metavar="LABEL",
                   help="run a single probe by label: " + ", ".join(n for n, _ in DOCKET_PROMPTS))
    p.add_argument("--timeout", type=float, default=180.0,
                   help="per-probe socket timeout in seconds (default: %(default)s)")
    p.add_argument("--out", default="",
                   help="append one JSON object per probe to this path (JSONL). Ad-hoc only "
                        "— never point it into data/.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompts = [(n, t) for n, t in DOCKET_PROMPTS if not args.only or n == args.only]
    if not prompts:
        print(f"no probe named {args.only!r}; known: "
              + ", ".join(n for n, _ in DOCKET_PROMPTS), file=sys.stderr)
        return 2
    if not (args.cookie or args.bearer):
        print("note: no --cookie / --bearer given; expect HTTP 401 unless guest access "
              "is enabled and the server does not require the mm_aid cookie.",
              file=sys.stderr)

    rows: list[dict] = []
    for run in range(1, max(1, args.runs) + 1):
        for name, text in prompts:
            row = probe(args.base_url, text, cookie=args.cookie, bearer=args.bearer,
                        lane=args.lane, page=args.page, symbol=args.symbol,
                        timeout=args.timeout)
            row.update({"probe": name, "run": run, "label": args.label,
                        "lane": args.lane, "base_url": args.base_url,
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            rows.append(row)

    print_table(rows)
    print_medians(rows)

    if args.out:
        try:
            with open(args.out, "a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
        except OSError as exc:
            print(f"could not write {args.out}: {exc}", file=sys.stderr)
            return 1
    return 1 if all(r.get("error") for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
