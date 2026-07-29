"""scripts/marketing_press_wire.py — the */5 Actions press wire (masterplan §10 E7).

WHAT THIS CLOSES. The press/Trump wire has never once reached X. The VPS daemon
(``scripts/marketing_fastlane_daemon.py``) emits press items with ``spool=True``,
which routes them to the GITIGNORED ``data/marketing/outbox/items-host.jsonl``;
the Actions publisher checks out main and folds the git-TRACKED ``items.jsonl``
and nothing else, so it has never seen a press emission. ``outbox._host_items_path``
says so in its own docstring ("The split-brain is unchanged"). On top of that the
daemon's systemd unit ships disabled and was never armed, so even the spool is
empty. Two independent reasons the lane is dark.

THE FIX IS THE HOT-TAPE PATTERN (#3941, ``scripts/hot_tape_radar.py``): run the
tick in GitHub Actions, emit through the CANONICAL outbox path (``spool=False``
→ tracked ``items.jsonl``), commit the state back with ``merge=union``, push,
and only THEN dispatch ``marketing-publish.yml -f post_now_item=<ids>``.

    python -m scripts.marketing_press_wire [--dry-run]

WHAT THIS LANE MAY WRITE (ledger law). Only ``data/marketing/outbox/*`` (through
``press_lane`` → ``outbox.enqueue``, plus the card SVG) and its own three state
files under ``data/marketing/press_wire/``. NEVER a forward ledger, never
anything the nightly owns. This loop runs 288 times a day.

STATE IS THE WHOLE DESIGN PROBLEM. On the VPS the press lane persists cursors,
conditional-GET ETags, the twitterapi.io spend counter, the flagship top-K
counter and the seen-ledger under the gitignored ``data/marketing/press/``. In
Actions every run is a FRESH CHECKOUT, so any state left there evaporates — and
an evaporating spend counter means the $75/mo twitterapi.io cap is not enforced
at all, because every run starts the month at $0.00. This lane therefore keeps
its state in COMMITTED files:

  data/marketing/press_wire/cursors.json    single-writer, last-wins whole-file
  data/marketing/press_wire/spend.jsonl     append-only DELTAS, merge=union
  data/marketing/press_wire/seen_ring.jsonl append-only keys,   merge=union

The split is deliberate. A push race that loses the cursors write costs one
re-poll (the seen ring still dedupes the result). A push race that lost a SPEND
row would under-count money and a lost SEEN row would re-post a story that
already went out — so those two are append-only with union merge, where the
merge driver cannot drop a side.

ONE LANE AT A TIME. The VPS daemon may still be armed some day (it reaches ≤90s
latency, which Actions' 5-minute cron floor cannot). The two must never poll the
same handles against the same cap from two different state stores, so this lane
stands down entirely when the repo variable ``PRESS_WIRE_DAEMON_ACTIVE`` is
true. The daemon's own paths and behaviour are untouched by this file — every
Actions adaptation below is a CONFIG TRANSFORM handed to the existing engine
functions, not an edit to them.

FAIL TOWARD "NO POST". Every step is never-raise and degrades to booking
nothing; the process exits 0 unless an invariant is genuinely broken.

Import discipline: pandas is NEVER imported on this path. ``breaking_relevance``
widens its ticker universe from ``data/earnings/earnings.parquet`` when pandas
AND that file are present and falls back to its static universe otherwise — the
workflow's sparse cone deliberately omits the parquet, so the fallback is the
only path here.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

log = logging.getLogger("marketing_press_wire")

# ─────────────────────────────────────────────────────────────────────────────
# Paths + knobs
# ─────────────────────────────────────────────────────────────────────────────

#: The committed state dir. TRACKED on purpose — see the module docstring.
STATE_SUBDIR = "data/marketing/press_wire"
CURSORS_REL = f"{STATE_SUBDIR}/cursors.json"
SPEND_REL = f"{STATE_SUBDIR}/spend.jsonl"
SEEN_REL = f"{STATE_SUBDIR}/seen_ring.jsonl"

#: Where ``breaking_feed`` keeps its own poller state. GITIGNORED and empty in a
#: fresh Actions checkout, so this lane hydrates it from cursors.json before the
#: poll and harvests it back after (zero changes to breaking_feed.py).
BREAKING_SUBDIR = "data/marketing/breaking"

#: Seen-ring capacity. Parity with the daemon's ``_PRESS_SEEN_CAP`` (8000), with
#: an age bound on top: a key past the horizon can no longer be re-emitted by
#: anything upstream (the mirrors' archives roll, the RSS feeds roll) and keeping
#: it forever would grow a file this lane commits 288 times a day.
SEEN_KEEP = 8000
#: 21 days (M9), and the SAME horizon the daemon copy keeps
#: (``_PRESS_SEEN_RETENTION_DAYS``) — two lanes writing one dedupe memory must
#: agree about how long it remembers. Seven days was too short to be a horizon:
#: mirror archives and RSS backfills re-deliver items older than a week, and a
#: key that ages out is not "stale", it is ELIGIBLE AGAIN — re-summarized on a
#: billed call and posted a second time as new.
SEEN_MAX_AGE_H = 504.0          # 21 days

#: Spend ledger retention. Only the CURRENT month is ever read; older rows are
#: audit trail. Six months keeps the file a few hundred rows.
SPEND_KEEP_MONTHS = 6

#: Carryover horizon for the publisher dispatch (mirrors hot_tape_radar's).
CARRYOVER_MAX_AGE_MIN = 45.0

#: twitterapi.io ``/twitter/user/last_tweets`` returns one page per request and
#: the page is what gets billed at $0.15/1k tweets. The documented default page
#: is 20 tweets, so a handle poll costs ~$0.003 — twenty times the $0.00015
#: minimum charge. Budgeting off the minimum charge (as the "it's only 15 hundredths
#: of a cent" reading does) under-states this lane's cost by 20x, which is exactly
#: how a $75 cap gets blown in week one. Every projection below uses the PAGE.
DEFAULT_TWEETS_PER_REQUEST = 20

#: Fallbacks when config/press_sources.yml carries no ``actions_wire`` block.
#: Tracks the config's own value (the reserve invariant in
#: tests/test_marketing_press_wire.py::TestSpendCapReserve) so an absent block
#: cannot silently RAISE the cap.
DEFAULT_ACTIONS_CAP_USD = 50.0
DEFAULT_TIER_INTERVALS_S = {"fast": 1140, "mid": 6900, "slow": 42600}
#: cursors.json ceiling. The optional scoring-brain sub-stores (story spine,
#: signal corpus, source authority) are the only things here that can grow, and
#: this file is rewritten WHOLE 288 times a day — a 500 KB blob at that cadence
#: is ~144 MB/day of poorly-deltable git objects. Over the ceiling they are
#: dropped with a start-of-line warning; the correctness keys never are.
DEFAULT_CURSORS_MAX_BYTES = 256 * 1024

#: State keys that are pure scoring ENRICHMENT. With ``breaking.scoring.rank_ordering``
#: dark (its default) these change no gate — they feed `_components` provenance
#: and the ordering that ships off. Persisting them is opt-in for that reason.
#: `intel_claims` (Intelligence Desk V2 story-identity registry) joins the list
#: because THIS lane discards `run_press_tick`'s intelligence packets — only the
#: VPS daemon advances the desk — so persisting desk identity state here would
#: spend tracked-file bytes on something no reader ever consumes.
SCORING_KEYS = ("story_spine", "signal_corpus", "source_authority",
                "intel_claims")

#: Env names.
ENV_DAEMON_ACTIVE = "PRESS_WIRE_DAEMON_ACTIVE"
ENV_OUTBOX_ENABLED = "MARKETING_OUTBOX_ENABLED"


def _repo_root() -> Path:
    return Path(_CODE_ROOT)


def _env_flag(name: str) -> bool:
    """True when env `name` is one of 1/true/yes (case-insensitive)."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def daemon_active() -> bool:
    """True when the VPS daemon owns this lane and Actions must stand down.

    Wired to the repo variable PRESS_WIRE_DAEMON_ACTIVE. Two pollers against one
    twitterapi.io cap from two different spend stores would each believe they had
    the whole budget.
    """
    return _env_flag(ENV_DAEMON_ACTIVE)


def push_access_ok(root: Path | str, *, timeout_s: float = 45.0) -> tuple[bool, str]:
    """Can this run push its state back? Probed BEFORE a single billed request.

    THE STATE WRITE IS THE BUDGET. cursors.json carries ``last_poll``, which is
    what ``press_providers.TwitterApiIoProvider.fetch`` throttles each handle
    against; spend.jsonl carries the deltas ``fold_spend`` sums into the cap
    guard's seed. A run whose push never lands loses BOTH at once — so the next
    */5 tick re-polls all 18 handles (no ``last_poll``) AND reads $0.00 spent (no
    deltas), and the cap can never fire. A persistent push failure therefore does
    not cost "one re-poll": it converts the $46.6/mo plan into ~$466/mo of real
    money on the shared $75 account, green-looping every five minutes.

    So the billed tier is FAIL-CLOSED on remote write. A cheap
    ``git push --dry-run`` (no objects transferred, one ref negotiation) answers
    "would a push be accepted right now" before any money is spent. Free work —
    the RSS wire, the mirrors, composing, and the state files themselves — still
    runs: it costs nothing and a landing push makes it all count.

    THE PROBE REF IS A THROWAWAY, NOT ``main``. ``--dry-run`` transfers nothing
    and creates nothing, but pushing HEAD at ``main`` would also fail whenever
    main merely advanced since the checkout — a non-fast-forward the commit
    step's rebase loop resolves in seconds. That is not a push OUTAGE and must
    not stand the lane down. Probing a ref that cannot exist yet asks the one
    question that matters: does this remote accept a write from this token.

    Returns (ok, detail). NEVER raises: git missing, no remote, or a hung probe
    all read as "cannot push", which is the conservative direction.
    """
    import subprocess  # noqa: PLC0415

    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "push", "--dry-run", "--porcelain", "origin",
             "HEAD:refs/heads/press-wire-push-probe"],
            cwd=str(root), capture_output=True, text=True, timeout=timeout_s,
        )
    except FileNotFoundError:
        return False, "git executable not found"
    except subprocess.TimeoutExpired:
        return False, f"probe timed out after {timeout_s:.0f}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode == 0:
        return True, "ok"
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, (detail[-1][:200] if detail else f"git exit {proc.returncode}")


# ─────────────────────────────────────────────────────────────────────────────
# Config surface (config/press_sources.yml `actions_wire`)
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    """Parse a YAML file; {} on any failure (fail-soft, like the daemon's)."""
    try:
        import yaml  # noqa: PLC0415

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("press_wire: config load failed (%s): %s", path.name, exc)
        return {}


def actions_cfg(press_cfg: dict) -> dict:
    """The `actions_wire` block, or {} when the config predates it."""
    block = (press_cfg or {}).get("actions_wire")
    return block if isinstance(block, dict) else {}


def poll_tier_intervals(press_cfg: dict) -> dict[str, int]:
    """Per-tier minimum seconds between polls of ONE handle, in Actions mode.

    THE CADENCE IS AN INTERVAL, NOT A RUN COUNTER. The obvious implementation —
    "fast every run, mid every 3rd run, slow hourly" by arithmetic on the run
    index — needs a run counter that survives a fresh checkout, and it skips a
    whole cycle whenever GitHub's scheduler fires late or drops a tick (it
    routinely does both). The provider ALREADY throttles per handle against a
    persisted ``last_poll`` wall clock (``TwitterApiIoProvider.fetch``), and that
    clock now persists in cursors.json — so the Actions cadence is expressed by
    OVERRIDING ``x_follow.poll_tiers`` with these intervals and letting the
    provider's own tested gate enforce them. Cron drift becomes a few seconds of
    jitter instead of a dropped cycle, and press_providers.py needs no edit.

    Intervals are picked a little under their round number (19m, 85m, 11h50m) so
    a handle due "every 20 minutes" is not pushed to 25 by a run that fires 40
    seconds early.
    """
    raw = actions_cfg(press_cfg).get("poll_tiers")
    out = dict(DEFAULT_TIER_INTERVALS_S)
    if isinstance(raw, dict):
        for tier, seconds in raw.items():
            try:
                out[str(tier)] = int(seconds)
            except (TypeError, ValueError):
                continue
    return out


def handles_by_tier(press_cfg: dict) -> dict[str, int]:
    """Count of pollable handles per tier — the projection's other input.

    Mirrors ``TwitterApiIoProvider.__init__``'s admission rules (satire hard-block
    and the PCF exclusion) so the projected spend counts the handles that will
    actually be polled, not the ones merely listed.
    """
    x_follow = (press_cfg or {}).get("x_follow") or {}
    satire = {str(h).lower() for h in ((press_cfg or {}).get("satire_blocklist") or [])}
    exclude_pcf = bool(x_follow.get("exclude_pcf_labeled", True))
    counts: dict[str, int] = {}
    for handle in x_follow.get("handles") or []:
        if not isinstance(handle, dict) or not handle.get("handle"):
            continue
        if str(handle["handle"]).lower() in satire:
            continue
        if exclude_pcf and handle.get("pcf_labeled"):
            continue
        tier = str(handle.get("tier", "mid"))
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def projected_monthly_usd(press_cfg: dict) -> dict[str, Any]:
    """Projected twitterapi.io spend for THIS lane, from config alone.

    THE MATH (printed every tick, asserted by tests/test_marketing_press_wire.py
    so a config edit that blows the budget turns the suite red rather than the
    invoice):

        requests/day per tier = handles(tier) * 86400 / interval_s(tier)
        $/request             = max($0.00015, tweets_per_request/1000 * $0.15)
        $/month               = sum(requests/day) * $/request * 30.44

    With the shipped register (5 fast / 10 mid / 3 slow) and the shipped
    intervals (19 min / 115 min / 11h50m) at a 20-tweet page:

        fast  5 * 86400/1140  =  379/day
        mid  10 * 86400/6900  =  125/day
        slow  3 * 86400/42600 =    6/day
        total                 =  510/day * $0.003 = $1.53/day = ~$46.6/mo

    …against the ~$55/mo left after the reply desk's $15 sub-budget is carved out
    of the $75 estate cap. It fits with ~15% head-room, and
    ``actions_wire.monthly_usd_cap`` is the hard stop above it: the provider
    refuses to spend past the cap even if this projection is wrong. Note the
    direction — a cap BELOW the projection is not caution, it is a silent outage
    from whatever day the month runs out.

    WHY THE FAST TIER IS 19 MINUTES AND NOT 5. Polling all 18 handles on every
    */5 run is 5,184 requests/day = ~$466/mo, six times the whole estate cap. The
    sub-5-minute path is carried by the FREE tiers instead: the wire RSS lane and
    the trumpstruth mirror poll every run at zero marginal cost, and those are the
    lanes a Trump post actually breaks on. twitterapi.io is corroboration breadth
    and the handles no RSS feed covers — worth $50/mo, not worth $466.
    """
    intervals = poll_tier_intervals(press_cfg)
    counts = handles_by_tier(press_cfg)
    x_follow = (press_cfg or {}).get("x_follow") or {}
    price_per_1k = float(x_follow.get("price_per_1k_tweets_usd", 0.15))
    min_charge = float(x_follow.get("min_charge_per_request_usd", 0.00015))
    per_request_tweets = int(
        actions_cfg(press_cfg).get("tweets_per_request", DEFAULT_TWEETS_PER_REQUEST)
    )
    usd_per_request = max(min_charge, per_request_tweets / 1000.0 * price_per_1k)

    by_tier: dict[str, float] = {}
    requests_per_day = 0.0
    for tier, n_handles in sorted(counts.items()):
        interval = max(1, int(intervals.get(tier, DEFAULT_TIER_INTERVALS_S.get(tier, 3600))))
        per_day = n_handles * 86400.0 / interval
        by_tier[tier] = round(per_day, 1)
        requests_per_day += per_day

    usd_per_day = requests_per_day * usd_per_request
    return {
        "handles": counts,
        "intervals_s": {t: intervals.get(t) for t in sorted(counts)},
        "requests_per_day": round(requests_per_day, 1),
        "requests_per_day_by_tier": by_tier,
        "usd_per_request": round(usd_per_request, 6),
        "usd_per_day": round(usd_per_day, 4),
        # 30.44 = mean days/month. Using 30 would under-state by half a percent
        # in the direction that matters least, but this is a budget, so be exact.
        "usd_per_month": round(usd_per_day * 30.44, 2),
    }


def actions_monthly_cap(press_cfg: dict) -> float:
    """This lane's monthly twitterapi.io sub-cap, in USD.

    Clamped to the estate-wide ``spend.twitterapiio_monthly_cap_usd`` so a typo in
    the sub-block can only ever LOWER the ceiling, never raise it above the one
    real account limit.
    """
    hard = float(((press_cfg or {}).get("spend") or {})
                 .get("twitterapiio_monthly_cap_usd", 75.0))
    try:
        sub = float(actions_cfg(press_cfg).get("monthly_usd_cap", DEFAULT_ACTIONS_CAP_USD))
    except (TypeError, ValueError):
        sub = DEFAULT_ACTIONS_CAP_USD
    return min(sub, hard)


def actions_press_cfg(press_cfg: dict) -> dict:
    """press_sources.yml as the ACTIONS lane sees it.

    THE WHOLE "Actions-mode adaptation" IS THIS FUNCTION. Rather than teach
    press_providers.py about a second deployment (a mode flag on a billed lane is
    a place for the two modes to drift apart, and the daemon's behaviour has to
    stay byte-identical), the two differences are expressed as a config transform
    on the dict handed to ``press_providers.poll_all``:

      1. ``x_follow.poll_tiers``  -> the Actions cadence (see poll_tier_intervals)
      2. ``spend.twitterapiio_monthly_cap_usd`` -> this lane's SUB-cap, so the
         provider's existing cap guard stops the Actions lane at $45 and leaves
         head-room under the $75 account cap for the reply desk and for the
         daemon if it is ever armed.

    Deep-copied: the caller's dict is also handed to ``run_press_tick`` for the
    wire/voice/format blocks and must not see the overrides.
    """
    out = copy.deepcopy(press_cfg or {})
    out.setdefault("x_follow", {})["poll_tiers"] = poll_tier_intervals(press_cfg)
    out.setdefault("spend", {})["twitterapiio_monthly_cap_usd"] = actions_monthly_cap(press_cfg)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Committed state: cursors.json (whole-file, last-wins)
# ─────────────────────────────────────────────────────────────────────────────

CURSORS_SCHEMA = "press_wire.cursors/v1"


def load_cursors(root: Path | str) -> dict:
    """Load the committed press state, or {} when this is a cold start.

    The returned dict is the SAME SHAPE the daemon keeps in its gitignored
    state.json (``providers`` nested, everything else at top level), so the two
    deployments' state files stay interchangeable.
    """
    path = Path(root) / CURSORS_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        # A corrupt state file must not wedge the lane forever; it costs one
        # re-poll and a prime, both of which are safe.
        print(f"::warning title=press-wire-state::cursors.json unreadable ({exc}) "
              "— starting from empty state", flush=True)
        return {}
    return data if isinstance(data, dict) else {}


def save_cursors(root: Path | str, state: dict, *, now: datetime,
                 press_cfg: dict | None = None) -> None:
    """Atomically write cursors.json, dropping enrichment state over the ceiling."""
    cfg = actions_cfg(press_cfg or {})
    persist_scoring = bool(cfg.get("persist_scoring", False))
    try:
        max_bytes = int(cfg.get("cursors_max_bytes", DEFAULT_CURSORS_MAX_BYTES))
    except (TypeError, ValueError):
        max_bytes = DEFAULT_CURSORS_MAX_BYTES

    payload = {k: v for k, v in state.items() if not str(k).startswith("_")}
    payload["schema"] = CURSORS_SCHEMA
    payload["updated_at"] = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not persist_scoring:
        for key in SCORING_KEYS:
            payload.pop(key, None)

    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if len(body.encode("utf-8")) > max_bytes and any(k in payload for k in SCORING_KEYS):
        for key in SCORING_KEYS:
            payload.pop(key, None)
        body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        print(f"::warning title=press-wire-state-ceiling::cursors.json exceeded "
              f"{max_bytes}B with the scoring stores — dropped them for this write "
              "(rank_ordering is dark, so no gate changes)", flush=True)

    path = Path(root) / CURSORS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# Committed state: spend.jsonl (append-only DELTAS, merge=union)
# ─────────────────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    """Every parseable object in a JSONL file. A bad line is skipped, not fatal."""
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError as exc:
        print(f"::warning title=press-wire-state::could not read {path.name}: {exc}",
              flush=True)
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def month_key(now: datetime) -> str:
    """The month bucket the provider's spend counter uses (UTC, %Y-%m)."""
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def fold_spend(root: Path | str, month: str) -> dict[str, float]:
    """Month-to-date twitterapi.io spend, summed from the committed deltas.

    Rows are DELTAS, not running totals, precisely so union merge is correct: two
    runs that both appended in the same push race keep both rows and the sum is
    right. A running total would have one row silently win and the loser's spend
    would vanish — under-counting money is the one direction a cap must never
    fail in.
    """
    total = {"requests": 0.0, "tweets": 0.0, "usd": 0.0}
    for row in _read_jsonl(Path(root) / SPEND_REL):
        if str(row.get("month", "")) != month:
            continue
        for field in total:
            try:
                total[field] += float(row.get(field, 0) or 0)
            except (TypeError, ValueError):
                continue
    return total


def append_spend(root: Path | str, delta: dict[str, float], *, month: str,
                 now: datetime) -> bool:
    """Append this tick's spend delta. Returns True when a row was written."""
    if not any(float(delta.get(f, 0) or 0) > 0 for f in ("requests", "tweets", "usd")):
        return False
    row = {
        "at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "month": month,
        "lane": "actions",
        "requests": int(delta.get("requests", 0) or 0),
        "tweets": int(delta.get("tweets", 0) or 0),
        "usd": round(float(delta.get("usd", 0.0) or 0.0), 6),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
    }
    _append_jsonl(Path(root) / SPEND_REL, [row])
    return True


def roll_spend(root: Path | str, *, now: datetime, keep_months: int = SPEND_KEEP_MONTHS) -> int:
    """Drop spend rows older than `keep_months`. Returns the number dropped.

    Only the current month is ever READ; the rest is audit trail with a horizon.
    A rewrite of a union-merged file is only safe because it exclusively REMOVES
    rows that no reader consults — a concurrent run's re-added old row is inert.
    """
    path = Path(root) / SPEND_REL
    rows = _read_jsonl(path)
    if not rows:
        return 0
    cutoff = (now.astimezone(timezone.utc) - timedelta(days=31 * keep_months))
    cutoff_month = cutoff.strftime("%Y-%m")
    keep = [r for r in rows if str(r.get("month", "")) >= cutoff_month]
    dropped = len(rows) - len(keep)
    if dropped <= 0:
        return 0
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in keep:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)
    return dropped


# ─────────────────────────────────────────────────────────────────────────────
# Committed state: seen_ring.jsonl (append-only, merge=union)
# ─────────────────────────────────────────────────────────────────────────────

#: Two key spaces share one ring. `press` = the press lane's MIRROR-COLLAPSED
#: emission keys (what stops a story re-posting). `wire` = breaking_feed's own
#: feed-item ids, hydrated into its gitignored seen.json before the poll.
SEEN_SPACE_PRESS = "press"
SEEN_SPACE_WIRE = "wire"


def load_seen(root: Path | str, space: str, *, now: datetime) -> dict[str, str]:
    """{key -> first_seen_iso} for one key space, age-filtered."""
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=SEEN_MAX_AGE_H)
    out: dict[str, str] = {}
    for row in _read_jsonl(Path(root) / SEEN_REL):
        if str(row.get("t", SEEN_SPACE_PRESS)) != space:
            continue
        key = str(row.get("k", ""))
        if not key:
            continue
        at = str(row.get("at", ""))
        parsed = _parse_iso(at)
        if parsed is not None and parsed < cutoff:
            continue
        # First sighting wins: the ring records when we FIRST saw a key, and a
        # union merge can legitimately deliver the same key twice.
        if key not in out or at < out[key]:
            out[key] = at
    return out


def append_seen(root: Path | str, keys: dict[str, list[str]], *, now: datetime) -> int:
    """Append new keys per space. `keys` is {space: [key, ...]}. Returns rows written."""
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {"k": key, "t": space, "at": stamp}
        for space, key_list in sorted(keys.items())
        for key in sorted(set(key_list))
        if key
    ]
    _append_jsonl(Path(root) / SEEN_REL, rows)
    return len(rows)


def roll_seen(root: Path | str, *, now: datetime, keep: int = SEEN_KEEP) -> int:
    """Trim the ring to `keep` newest rows per space, then by age. Returns rows dropped.

    Same safety argument as roll_spend: this only REMOVES rows past the dedupe
    horizon, and a concurrent run's union-merged re-add of an old key merely
    suppresses a story that is already stale. The failure direction is "posts
    nothing", never "posts twice".
    """
    path = Path(root) / SEEN_REL
    rows = _read_jsonl(path)
    if not rows:
        return 0
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=SEEN_MAX_AGE_H)
    fresh = []
    for row in rows:
        parsed = _parse_iso(str(row.get("at", "")))
        if parsed is not None and parsed < cutoff:
            continue
        fresh.append(row)
    by_space: dict[str, list[dict]] = {}
    for row in fresh:
        by_space.setdefault(str(row.get("t", SEEN_SPACE_PRESS)), []).append(row)
    kept: list[dict] = []
    for space_rows in by_space.values():
        space_rows.sort(key=lambda r: str(r.get("at", "")))
        kept.extend(space_rows[-keep:])
    kept.sort(key=lambda r: str(r.get("at", "")))
    dropped = len(rows) - len(kept)
    if dropped <= 0:
        return 0
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)
    return dropped


def _parse_iso(raw: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# breaking_feed hydration (its state dir is gitignored + empty in Actions)
# ─────────────────────────────────────────────────────────────────────────────

def hydrate_breaking(root: Path | str, cursors: dict, seen_wire: dict[str, str]) -> None:
    """Write breaking_feed's state.json + seen.json from the committed state.

    Zero changes to breaking_feed.py: it reads two files in a gitignored dir and
    this puts them there before ``poll_all`` runs.

    THE SEEN LEDGER IS NOT OPTIONAL HERE, and not only for dedupe. Without it
    every RSS feed's whole page reads as NEW on every one of the 288 daily runs.
    The press lane's own dedupe would still stop them EMITTING — but only after
    they had passed through ``SignalCorpus.observe`` and ``StorySpine.assign``,
    so the same headline would register 288 arrivals a day and the burst detector
    would score a quiet feed as a breaking story. The dedupe is what keeps the
    scoring brain's statistics honest, not just the queue clean.
    """
    d = Path(root) / BREAKING_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    wire_state = cursors.get("wire")
    (d / "state.json").write_text(
        json.dumps(wire_state if isinstance(wire_state, dict) else {}, indent=2),
        encoding="utf-8",
    )
    (d / "seen.json").write_text(json.dumps(seen_wire, indent=2), encoding="utf-8")


def harvest_breaking(root: Path | str, cursors: dict) -> dict[str, str]:
    """Read breaking_feed's post-poll state back; returns its seen ledger.

    The ETag/backoff state goes into ``cursors["wire"]`` (whole-file, last-wins —
    losing it costs one unconditional re-fetch). The seen ids are returned so the
    caller can append only the NEW ones to the union-merged ring.
    """
    d = Path(root) / BREAKING_SUBDIR
    try:
        raw_state = json.loads((d / "state.json").read_text(encoding="utf-8"))
        if isinstance(raw_state, dict):
            cursors["wire"] = raw_state
    except Exception:  # noqa: BLE001
        pass
    try:
        raw_seen = json.loads((d / "seen.json").read_text(encoding="utf-8"))
        if isinstance(raw_seen, dict):
            return {str(k): str(v) for k, v in raw_seen.items()}
    except Exception:  # noqa: BLE001
        pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Publisher dispatch
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_ids(root: Path | str, booked: list[str], *, now: datetime) -> list[str]:
    """The ids this pass hands marketing-publish, oldest first.

    Same reasoning as ``hot_tape_radar.dispatch_ids``: the dispatch is ONE
    fire-and-forget API call made only when this pass booked something, so an
    item whose own dispatch lost a push race would otherwise wait for the next
    scheduled sweep — the ">= 20 min" latency this lane exists to beat. Every
    still-queued press item inside the carryover horizon rides along free.

    Unlike hot tape this needs no separate fired-ledger: a press emission is
    identifiable from the queue itself (``source.lane == "press"``), so the
    carryover is folded out of the outbox rather than a fourth state file.
    """
    from engine.marketing import outbox as OB  # noqa: PLC0415

    booked_set = set(booked)
    try:
        state = OB.fold_state(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("press_wire: outbox fold failed, dispatching booked only: %s", exc)
        return list(booked)

    statuses = state.get("status") or {}
    items = state.get("items") or {}
    pending: list[tuple[str, str]] = []
    stale: list[str] = []
    for item_id, item in items.items():
        if item_id in booked_set:
            continue
        if str((item.get("source") or {}).get("lane", "")) != "press":
            continue
        if statuses.get(item_id) not in ("queued", "approved"):
            continue
        created = _parse_iso(item.get("created_at") or item.get("created"))
        age = (now - created).total_seconds() / 60.0 if created is not None else None
        if age is None or age > CARRYOVER_MAX_AGE_MIN:
            stale.append(item_id)
            continue
        pending.append((str(item.get("created_at") or item.get("created") or ""), item_id))

    if stale:
        print("::warning title=press-wire-unposted::"
              f"{len(stale)} press item(s) booked over {CARRYOVER_MAX_AGE_MIN:.0f}m ago "
              f"are still unposted: {','.join(sorted(set(stale))[:20])} - the scheduled "
              "publish sweep owns them", flush=True)

    out: list[str] = []
    seen: set[str] = set()
    for _, item_id in sorted(pending):
        if item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    for item_id in booked:      # this pass's own, newest, last
        if item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    return out


def floor_diagnostic(press_cfg: dict, skipped: list[dict], emitted: list[dict]) -> str | None:
    """One line naming the salience floor when it is what blocked the whole tick.

    WHAT THIS REPORTS. ``wire.flagship_salience_floor`` is checked BEFORE account
    routing (press_lane step 5 precedes step 5b), so an item under it emits to NO
    account — not the flagship, not the wire desk. It survives only on the
    news.html rail, whose floor is 40. When a tick emits nothing and the floor is
    the reason, that is worth one line in the run log.

    EVERY NUMBER IN THE MESSAGE IS COMPUTED, none is asserted. The first cut of
    this function narrated the calibration as it stood that morning ("the
    mirror/x_relay tiers earn no tier bonus", "policy bases at 45") and the E7
    calibration landed on the same branch hours later: `mirror` (+12) and
    `x_relay` (+8) joined ``_TIER_BONUS`` and policy went 45 -> 50. The prose
    stayed. A diagnostic that recites remembered constants is a diagnostic that
    lies the moment somebody fixes the thing it describes, so the message now
    reads the taxonomy and the tier table at call time.

    Returns None unless the floor was the binding constraint on THIS tick AND the
    best score this lane's own tiers can reach without keyword/ticker help is
    still under it — so the line fires only when it is true and disarms itself
    once the calibration moves, rather than shouting on all 288 daily runs.
    """
    if emitted:
        return None
    blocked = [s for s in (skipped or []) if s.get("reason") == "below_flagship_floor"]
    if not blocked:
        return None
    floor = float(((press_cfg or {}).get("wire") or {}).get("flagship_salience_floor", 70.0))
    try:
        from engine.marketing.breaking_relevance import (  # noqa: PLC0415
            _CLASS_TAXONOMY, _TIER_BONUS,
        )

        max_base = max(float(row[1]) for row in _CLASS_TAXONOMY)
        # The tiers THIS lane's items actually carry. An RSS "official" bonus is
        # irrelevant to a diagnosis about press items.
        press_bonus = max(float(_TIER_BONUS.get(t, 0.0))
                          for t in ("mirror", "x_relay"))
    except Exception:  # noqa: BLE001
        return None                      # internals moved — say nothing rather than lie
    if max_base + press_bonus >= floor:
        return None            # reachable without keyword/ticker help; nothing to say
    best = max((float(s.get("salience") or 0.0) for s in blocked), default=0.0)
    return (f"::notice title=press-wire-floor::{len(blocked)} item(s) blocked by "
            f"wire.flagship_salience_floor={floor:g}; best was {best:g}. The highest "
            f"event-class base is {max_base:g} and the best press tier bonus is "
            f"+{press_bonus:g}, so a press item clears this floor only on "
            f"keyword/ticker strength")


def _write_github_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("press_wire: GITHUB_OUTPUT write failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# One tick
# ─────────────────────────────────────────────────────────────────────────────

def run(root: Path | str, *, now: datetime | None = None, dry_run: bool = False) -> int:
    """One Actions press-wire pass. Never raises; 0 unless genuinely broken."""
    root = Path(root)
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    if daemon_active():
        # The VPS daemon owns the lane. Standing down BEFORE any poll is the
        # whole point: two pollers, two spend stores, one cap.
        print(f"::notice title=press-wire-standdown::{ENV_DAEMON_ACTIVE} is set - "
              "the VPS daemon owns this lane, Actions polls nothing", flush=True)
        return 0

    marketing_cfg = load_yaml(root / "config" / "marketing.yml")
    press_cfg = load_yaml(root / "config" / "press_sources.yml")
    if not press_cfg:
        print("::warning title=press-wire::config/press_sources.yml missing or empty "
              "- standing down", flush=True)
        return 0

    projection = projected_monthly_usd(press_cfg)
    cap = actions_monthly_cap(press_cfg)
    month = month_key(ts)
    spent = fold_spend(root, month)
    print(f"press-wire projection {projection['requests_per_day']} req/day "
          f"@ ${projection['usd_per_request']}/req = ${projection['usd_per_month']}/mo "
          f"| cap ${cap:.2f} | {month} spent ${spent['usd']:.4f} "
          f"({int(spent['requests'])} req, {int(spent['tweets'])} tweets)", flush=True)
    if projection["usd_per_month"] > cap:
        # Not fatal — the provider's cap guard is the hard stop — but a config
        # that is designed to overrun should say so on every run until it is fixed.
        print(f"::warning title=press-wire-budget::projected ${projection['usd_per_month']}/mo "
              f"exceeds the lane cap ${cap:.2f}; the provider will hard-stop mid-month",
              flush=True)

    # COLD START. Parity with the daemon (m2): with neither state file present the
    # first batch is a full history snapshot (mirror archives, twitterapi.io
    # last_tweets with no cursor), not real-time news. PRIME — seed the cursors and
    # the seen ring, emit nothing — rather than flood the queue with a week of news.
    cursors_path = root / CURSORS_REL
    seen_path = root / SEEN_REL
    cold_start = not cursors_path.exists() and not seen_path.exists()

    cursors = load_cursors(root)
    seen_press = load_seen(root, SEEN_SPACE_PRESS, now=ts)
    seen_wire = load_seen(root, SEEN_SPACE_WIRE, now=ts)

    # Emission gate. MARKETING_OUTBOX_ENABLED is the QUEUE switch (the same one
    # engine/neuralweb/marketing_governor.py reads); MARKETING_PUBLISH_ENABLED —
    # deliberately NOT read here — is the SEND switch and belongs to
    # marketing-publish.yml. This lane only ever fills the queue, so with the send
    # switch off the operator can watch exactly what it WOULD have posted.
    emit_allowed = _env_flag(ENV_OUTBOX_ENABLED) and not dry_run
    effective_dry = not emit_allowed

    # BILLED-LANE PREFLIGHT, before any money moves. A run that cannot push its
    # state back loses BOTH the per-handle `last_poll` throttle and the spend
    # deltas, and those two together ARE the budget — see push_access_ok. A real
    # dry run already skips the billed lane, and with no API key on the host the
    # provider skips itself, so the probe is only worth its ~1s when this run
    # could actually spend.
    _key_env = str(((press_cfg.get("x_follow") or {}).get("key_env"))
                   or "TWITTERAPI_IO_KEY")
    billed_offline = effective_dry
    if not effective_dry and os.environ.get(_key_env, "").strip():
        _push_ok, _push_why = push_access_ok(root)
        if not _push_ok:
            billed_offline = True
            print(
                "::warning title=press-wire-push-preflight::remote write is "
                f"unavailable ({_push_why}) — the BILLED twitterapi.io tier stands "
                "down for this run. Its state (last_poll + spend deltas) could not "
                "be committed, and a lane that re-polls all handles with a $0.00 "
                "spend counter every 5 minutes is ~$466/mo against a $75 account. "
                "Free wire RSS + mirrors continue.",
                flush=True,
            )

    # 1. Wire RSS (FREE, every run). Hydrate breaking_feed's gitignored state dir
    #    from the committed ring first so its dedupe works in a fresh checkout.
    hydrate_breaking(root, cursors, seen_wire)
    wire_items: list = []
    try:
        from engine.marketing import breaking_feed  # noqa: PLC0415

        wire_items = breaking_feed.poll_all(root, marketing_cfg.get("breaking", {}))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=press-wire-rss::wire poll failed (continuing): {exc}",
              flush=True)
    seen_wire_after = harvest_breaking(root, cursors)

    # 2. Press providers (trumpstruth + CNN mirrors FREE; twitterapi.io BILLED).
    #    offline=billed_offline keeps the billed lane off the network in a dry run
    #    (whose spend is never persisted — M2) and on a run that failed the push
    #    preflight (whose spend + throttle would be lost — see above). Free
    #    providers ignore the flag and still poll in both cases.
    provider_state = cursors.setdefault("providers", {})
    tw_state = provider_state.setdefault("twitterapiio", {})
    # Seed the provider's month counter from the COMMITTED ledger. Without this
    # every fresh checkout starts the month at $0.00 and the cap never fires.
    tw_state.setdefault("spend", {})[month] = {
        "requests": int(spent["requests"]),
        "tweets": int(spent["tweets"]),
        "usd": float(spent["usd"]),
    }
    press_items: list = []
    try:
        from engine.marketing import press_providers  # noqa: PLC0415

        press_items = press_providers.poll_all(
            root, actions_press_cfg(press_cfg), provider_state,
            offline=billed_offline, now=ts,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=press-wire-providers::provider poll failed "
              f"(continuing): {exc}", flush=True)

    post = tw_state.get("spend", {}).get(month, {})
    delta = {
        "requests": float(post.get("requests", 0)) - spent["requests"],
        "tweets": float(post.get("tweets", 0)) - spent["tweets"],
        "usd": float(post.get("usd", 0.0)) - spent["usd"],
    }

    all_items = list(wire_items) + list(press_items)
    print(f"press-wire poll wire={len(wire_items)} providers={len(press_items)} "
          f"total={len(all_items)} emit_allowed={int(emit_allowed)} "
          f"cold_start={int(cold_start)} spend_delta=${delta['usd']:.5f}", flush=True)

    # 3. The tick itself. spool=False is the entire point of this program: the
    #    emission lands in the git-TRACKED items.jsonl the Actions publisher folds,
    #    not the gitignored items-host.jsonl the daemon writes and nothing reads.
    result: dict = {}
    try:
        from engine.marketing.press_lane import run_press_tick  # noqa: PLC0415

        result = run_press_tick(
            all_items,
            root=root,
            now=ts,
            cfg=marketing_cfg,
            press_cfg=press_cfg,
            state=cursors,
            seen_ids=set(seen_press.keys()),
            dry_run=effective_dry,
            prime=cold_start,
            spool=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=press-wire-tick::press tick failed: "
              f"{type(exc).__name__}: {exc}", flush=True)
        result = {}

    emitted = result.get("emitted") or []
    booked = [str(item.get("id")) for item in emitted if item.get("id")]
    print(f"press-wire tick emitted={len(emitted)} digest={len(result.get('digest') or [])} "
          f"skipped={len(result.get('skipped') or [])} "
          f"blocked={len(result.get('blocked') or [])} rail={len(result.get('rail') or [])}",
          flush=True)
    for item in emitted:
        print(f"press-wire BOOK {item.get('id')} account={item.get('account')} "
              f"{str(item.get('headline', ''))[:90]}", flush=True)

    diagnostic = floor_diagnostic(press_cfg, result.get("skipped") or [], emitted)
    if diagnostic:
        print(diagnostic, flush=True)

    if dry_run:
        # Non-consuming by construction: no spend row, no cursor write, no seen
        # append. The next live run sees exactly what this run saw.
        print("press-wire dry-run: no state written", flush=True)
        return 0

    # 4. Persist. Spend and seen FIRST — they are the two ledgers whose loss is
    #    expensive (money under-counted, a story re-posted); cursors last.
    if append_spend(root, delta, month=month, now=ts):
        roll_spend(root, now=ts)

    # THE SEEN RING ADVANCES ON EVERY REAL RUN, armed or not (M8 — the same fix
    # the daemon copy carries). This was gated on `emit_allowed`, i.e. on
    # MARKETING_OUTBOX_ENABLED, which is DARK by default: a disarmed run still
    # polls, still scores and still pays the summarizer for every item, so the
    # gate meant the lane re-did that work on the same items every five minutes
    # and never remembered any of it. The switch decides whether we PUBLISH; it
    # says nothing about whether we already looked. `--dry-run` returned above,
    # so it stays non-consuming.
    new_press = [k for k in (result.get("_seen") or []) if k not in seen_press]
    new_wire = [k for k in seen_wire_after if k not in seen_wire]
    written = append_seen(
        root, {SEEN_SPACE_PRESS: new_press, SEEN_SPACE_WIRE: new_wire}, now=ts
    )
    if written:
        roll_seen(root, now=ts)

    save_cursors(root, cursors, now=ts, press_cfg=press_cfg)

    # 5. Dispatch. The workflow makes the API call AFTER the push lands, so an id
    #    named here is guaranteed to exist in the publisher's checkout.
    ids = dispatch_ids(root, booked, now=ts)
    if ids:
        joined = ",".join(ids)
        print(f"press-wire DISPATCH ids={joined}", flush=True)
        _write_github_output("post_now_ids", joined)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Actions press wire — poll the press tiers and book breaking posts.")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="poll the free tiers, score and compose; write NOTHING "
                             "(the billed twitterapi.io lane is skipped entirely)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s",
                        stream=sys.stdout)
    return run(_repo_root(), dry_run=bool(args.dry_run))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
