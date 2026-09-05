#!/usr/bin/env python3
"""scripts/activation_funnel_report.py — the CA1A machine consumer.

Reconstructs the early-funnel sequence

    visit -> intelligence.viewed -> personal.act -> watchlist.saved

from existing `analytics_events` rows and emits one bounded, DETERMINISTIC report:
per-stage session counts, adjacent conversion ratios, explicit cutoffs, the filter
version, and the largest observed leak as a templated sentence. Same rows in, same
bytes out — there is no model, no wall clock, and no network unless --from-supabase
is explicitly requested.

Input modes
-----------
  --input rows.json          a JSON array of analytics_events rows (fixtures, exports)
  --from-supabase            PostgREST read of analytics_events using SUPABASE_URL +
                             SUPABASE_SERVICE_ROLE_KEY from the environment (canary use)

Both modes REQUIRE explicit --since/--until ISO-8601 UTC cutoffs: a report that
defaults its own window can never be reproduced (point-in-time contract, PROJECT_SOL
return §6.6). Rows are admitted by INGESTION time (`created_at`); the report also
states the max observed occurrence time so late-data effects are visible.

Null contract: a stage whose denominator is zero or unknown reports its ratio as null
("missing is not zero"), and the largest-leak sentence names only stages that HAVE a
denominator.

Filter contract (versioned; the version string is part of the output):
  commercial_activation_filter.v1 =
    * drop rows whose `ua` contains (case-insensitive) any of
      bot | crawl | spider | slurp | headless | monitor | probe
      — SUBSTRING match, deliberately: real crawler UAs are compounds ("Googlebot",
      "bingbot", "AhrefsBot") that a word-boundary match silently admits
    * drop rows with a non-null user_id belonging to --internal-user (repeatable)
    * drop rows whose visitor_id is in --internal-visitor (repeatable)
Unknown identity is NOT dropped — exclusion needs a reason, absence of one keeps the row.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FILTER_VERSION = "commercial_activation_filter.v1"
SCHEMA_VERSION = "growth_events.v1"
REPORT_VERSION = "activation_funnel_report.v1"

_BOT_UA = re.compile(r"(?i)(bot|crawl|spider|slurp|headless|monitor|probe)")

# Ordered funnel stages: (stage key, predicate over one row).
def _is_visit(row: dict) -> bool:
    return True  # any admitted row marks its session as a visit

def _is_value(row: dict) -> bool:
    return row.get("type") == "intelligence.viewed"

def _is_act(row: dict) -> bool:
    return row.get("type") == "personal.act"

def _is_save(row: dict) -> bool:
    if row.get("type") != "watchlist.saved":
        return False
    meta = row.get("meta") or {}
    try:
        return int(meta.get("symbol_count", 0)) >= 3
    except (TypeError, ValueError):
        return False

_STAGES = [
    ("visit", _is_visit),
    ("intelligence_viewed", _is_value),
    ("personal_act", _is_act),
    ("watchlist_saved", _is_save),
]


def _parse_iso(value: str, flag: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{flag}: not ISO-8601: {value!r} ({exc})")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_ts(row: dict, field: str) -> datetime | None:
    raw = row.get(field)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _admit(rows: list[dict], since: datetime, until: datetime,
           internal_users: set[str], internal_visitors: set[str]) -> tuple[list[dict], dict]:
    admitted, dropped = [], {"bot_ua": 0, "internal_user": 0, "internal_visitor": 0,
                             "outside_window": 0, "no_created_at": 0}
    for row in rows:
        created = _row_ts(row, "created_at")
        if created is None:
            dropped["no_created_at"] += 1
            continue
        if not (since <= created <= until):
            dropped["outside_window"] += 1
            continue
        ua = row.get("ua") or ""
        if _BOT_UA.search(ua):
            dropped["bot_ua"] += 1
            continue
        uid = row.get("user_id")
        if uid and uid in internal_users:
            dropped["internal_user"] += 1
            continue
        if (row.get("visitor_id") or "") in internal_visitors:
            dropped["internal_visitor"] += 1
            continue
        admitted.append(row)
    return admitted, dropped


def _sessions_per_stage(rows: list[dict]) -> dict[str, set]:
    per: dict[str, set] = {stage: set() for stage, _ in _STAGES}
    for row in rows:
        sid = row.get("session_id") or ""
        if not sid:
            continue
        for stage, pred in _STAGES:
            if pred(row):
                per[stage].add(sid)
    return per


def _ratio(numer: int, denom: int | None):
    if not denom:  # 0 or None: missing is not zero — the ratio is unknowable
        return None
    return round(numer / denom, 4)


def _largest_leak(counts: dict[str, int]) -> str:
    worst = None  # (drop, idx, from_stage, to_stage, n_from, n_to)
    for i in range(len(_STAGES) - 1):
        a, b = _STAGES[i][0], _STAGES[i + 1][0]
        n_from, n_to = counts[a], counts[b]
        if n_from <= 0:
            continue  # no denominator, no leak claim
        drop = n_from - n_to
        if worst is None or drop > worst[0]:  # strict >: earlier stage wins ties
            worst = (drop, i, a, b, n_from, n_to)
    if worst is None:
        return "No leak measurable: no stage has a non-zero denominator."
    drop, _i, a, b, n_from, n_to = worst
    pct = round(n_to / n_from * 100, 1)
    return (f"Largest leak: {a} -> {b}: {n_from} -> {n_to} sessions "
            f"({pct}% continue, {drop} lost).")


def build_report(rows: list[dict], since: datetime, until: datetime,
                 internal_users: set[str], internal_visitors: set[str]) -> dict:
    admitted, dropped = _admit(rows, since, until, internal_users, internal_visitors)
    per = _sessions_per_stage(admitted)
    counts = {stage: len(per[stage]) for stage, _ in _STAGES}
    occurred = [ts for r in admitted if (ts := _row_ts(r, "client_ts"))]
    return {
        "report": REPORT_VERSION,
        "schema": SCHEMA_VERSION,
        "filter_version": FILTER_VERSION,
        "ingestion_cutoff": {"since": since.isoformat(), "until": until.isoformat()},
        "occurrence_observed_max": max(occurred).isoformat() if occurred else None,
        "rows_admitted": len(admitted),
        "rows_dropped": dropped,
        "stage_sessions": counts,
        "conversion": {
            "intelligence_viewed_over_visit": _ratio(counts["intelligence_viewed"], counts["visit"]),
            "personal_act_over_intelligence_viewed": _ratio(counts["personal_act"], counts["intelligence_viewed"]),
            "watchlist_saved_over_personal_act": _ratio(counts["watchlist_saved"], counts["personal_act"]),
        },
        "largest_leak": _largest_leak(counts),
    }


def _fetch_supabase(since: datetime, until: datetime) -> list[dict]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise SystemExit("--from-supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    out: list[dict] = []
    page, step = 0, 1000
    while True:
        params = urllib.parse.urlencode({
            "select": "id,type,site,path,ticker,session_id,visitor_id,user_id,ua,client_ts,created_at,meta",
            "created_at": f"gte.{since.isoformat()}",
            "order": "created_at.asc",
            "limit": str(step),
            "offset": str(page * step),
        })
        # PostgREST supports one filter per key via urlencode; the upper bound rides a
        # second created_at constraint using the and= syntax to stay exact.
        url = (f"{base}/rest/v1/analytics_events?{params}"
               f"&and=(created_at.lte.{urllib.parse.quote(until.isoformat())})")
        req = urllib.request.Request(url, headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read())
        out.extend(batch)
        if len(batch) < step:
            return out
        page += 1


def _to_markdown(rep: dict) -> str:
    lines = [
        f"# Activation funnel report ({rep['report']})",
        "",
        f"- Ingestion window: `{rep['ingestion_cutoff']['since']}` -> `{rep['ingestion_cutoff']['until']}`",
        f"- Filter: `{rep['filter_version']}` | Schema: `{rep['schema']}`",
        f"- Rows admitted: {rep['rows_admitted']} | dropped: {json.dumps(rep['rows_dropped'])}",
        "",
        "| stage | sessions |",
        "|---|---|",
    ]
    for stage, _ in _STAGES:
        lines.append(f"| {stage} | {rep['stage_sessions'][stage]} |")
    lines += ["", "| transition | ratio |", "|---|---|"]
    for key, val in rep["conversion"].items():
        lines.append(f"| {key} | {'null' if val is None else val} |")
    lines += ["", rep["largest_leak"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="JSON array of analytics_events rows")
    src.add_argument("--from-supabase", action="store_true")
    ap.add_argument("--since", required=True, help="ingestion cutoff start, ISO-8601 UTC")
    ap.add_argument("--until", required=True, help="ingestion cutoff end, ISO-8601 UTC")
    ap.add_argument("--internal-user", action="append", default=[])
    ap.add_argument("--internal-visitor", action="append", default=[])
    ap.add_argument("--out", help="write JSON here (default stdout)")
    ap.add_argument("--markdown", help="also write a Markdown rendering here")
    args = ap.parse_args(argv)

    since = _parse_iso(args.since, "--since")
    until = _parse_iso(args.until, "--until")
    if until < since:
        raise SystemExit("--until precedes --since")

    if args.input:
        rows = json.loads(open(args.input, encoding="utf-8").read())
        if not isinstance(rows, list):
            raise SystemExit("--input must be a JSON array of rows")
    else:
        rows = _fetch_supabase(since, until)

    rep = build_report(rows, since, until,
                       set(args.internal_user), set(args.internal_visitor))
    blob = json.dumps(rep, indent=2, sort_keys=True)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(blob + "\n")
    else:
        print(blob)
    if args.markdown:
        open(args.markdown, "w", encoding="utf-8").write(_to_markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
