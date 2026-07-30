"""scripts/marketing_publisher.py — D02 W1 live social publisher.

The missing publish half of the desk network: takes APPROVED, DUE items from
the outbox and posts them through a backend (Buffer today). Off the render
path; operator-run or nightly-cron; DARK BY DEFAULT.

Usage:
    # dry-run (default): print exactly what WOULD post, zero network calls
    python -m scripts.marketing_publisher
    python -m scripts.marketing_publisher --account flagship

    # discover Buffer channel ids (needs BUFFER_TOKEN in env)
    BUFFER_TOKEN=... python -m scripts.marketing_publisher --list-channels

    # LIVE post — requires BOTH flags together:
    MARKETING_PUBLISH_ENABLED=1 BUFFER_TOKEN=... \
        python -m scripts.marketing_publisher --live --account flagship

Guards (ALL must pass or the runner no-ops with a clear log line):
  * kill-switch  sentinel.publish_enabled() is true AND --live was passed
  * per-account daily cap  outbox.effective_cap(cfg), counted ledger-based via
                           outbox.posted_today_by_account (folded status
                           posted/posting whose last transition landed today —
                           nightly items post the day AFTER their as_of)
  * per-item     social_publisher.validate_postable() (280 cap, link policy,
                 empty text)

No-double-post guarantee:
  * validate fail          → item transitioned to `quarantined` (reason), never posted
  * before the network call → `approved → posting` (durable in-flight marker)
  * publish success         → `posting → posted`, Receipt recorded in the ledger
  * publish failure         → `posting → failed`, error recorded
  * item already `posting` at startup → REPORTED and LEFT AS-IS, never reposted
    (a crash mid-post must not double-post on the next run)

Backend + per-account channel id come from config/marketing.yml `publish:`; the
Buffer token from env BUFFER_TOKEN. Structured logging throughout.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Top-level ON PURPOSE (stdlib-only module): the post-time language gate must
# fail LOUDLY at import if copywriter breaks — a lazy import inside main()
# wrapped in try/except would silently disarm the gate (the swallowed-import
# failure mode). Path bootstrap first so `python scripts/marketing_publisher.py`
# from any cwd resolves `engine.` the same as `python -m scripts...` does.
_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:
    sys.path.insert(0, _CODE_ROOT)
from engine.marketing.copywriter import banned_language as _banned_language  # noqa: E402
from engine.marketing.copywriter import headline_fragments as _headline_fragments  # noqa: E402

log = logging.getLogger("marketing_publisher")


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrapping helpers
# ─────────────────────────────────────────────────────────────────────────────

def _code_root() -> Path:
    """Directory containing engine/ — always where this script lives (../)."""
    return Path(__file__).resolve().parent.parent


def _data_root(root_arg: str | None) -> Path:
    return Path(root_arg) if root_arg is not None else _code_root()


def _ensure_importable() -> None:
    cr = _code_root()
    if str(cr) not in sys.path:
        sys.path.insert(0, str(cr))


def _load_marketing_cfg(root: Path) -> dict:
    """Load config/marketing.yml fail-soft; {} on any error."""
    try:
        import yaml  # noqa: PLC0415
        cfg_path = root / "config" / "marketing.yml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load marketing.yml: %s", exc)
    return {}


def _publish_cfg(cfg: dict) -> dict:
    return (cfg.get("publish") or {}) if isinstance(cfg, dict) else {}


def _channel_id_for(pub_cfg: dict, account: str) -> str:
    return str((pub_cfg.get("channels") or {}).get(account, "") or "").strip()


def _dark_account_ids(cfg: dict, root) -> "frozenset[str] | None":
    """Ids of desk_network accounts that are NOT effective-enabled, or None when
    liveness is UNKNOWN (the accounts model could not be consulted).

    The accounts model is the single reader of that question — config intent
    (``enabled``, legacy ``disabled: true``) plus the operator override file
    data/marketing/account_overrides.json — and sentinel.gate_plan resolves the
    plan-path version of this list with the identical predicate. Both paths call
    effective_accounts and test ``not enabled`` so the nightly plan and a
    dispatch can never disagree about which desk is armed.

    FAIL DIRECTION, deliberately the OPPOSITE of wire_routing._enabled_accounts.
    That module treats unknown liveness as route-to-default because it HAS a safe
    fallback account to route to; the publisher has no safe fallback for "may
    this desk post at all", and failing closed would park every live desk on a
    transient helper error — a seven-desk outage to protect one dark one, which
    is the worse failure. Unknown therefore stands the gate down INERT for the
    run (items flow exactly as they did before this gate existed) and says so in
    the Actions summary. None and the empty set are still DIFFERENT answers and
    callers must not conflate them: empty means "asked, a real roster came back,
    nothing on it is dark".

    TWO shapes are unknown, not one, and the second is the silent-disarm the
    first review caught: an EMPTY roster. effective_accounts reads
    ``cfg.desk_network.accounts``, and every way that key can go missing —
    _load_marketing_cfg failing soft to {}, a mis-indented block, a renamed key,
    a checkout with no config — returns [] rather than raising. Read as "nothing
    is dark" that silently disarms the gate on the exact configs least likely to
    be correct (probe: channels bound, no desk_network → a dark item posts, rc 0,
    no annotation). A publisher with no roster does not KNOW which desks are
    armed, so it says so and goes inert loudly instead of quietly.
    """
    try:
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        accounts = effective_accounts(cfg, root)
        if not accounts:
            log.warning("dark-desk park: desk_network resolved ZERO accounts — "
                        "liveness UNKNOWN (no roster to check against), the gate "
                        "stands down INERT for this run")
            return None
        # Empty ids dropped: an id-less desk_network entry resolves to "" and
        # would park every item whose account field is missing or blank.
        dark = {str(a.get("id") or "").strip()
                for a in accounts if not a.get("enabled")}
        dark.discard("")
        return frozenset(dark)
    except Exception as exc:  # noqa: BLE001
        log.warning("dark-desk park: accounts model unavailable (%s) — the gate "
                    "stands down INERT for this run", exc)
        return None


#: Accounts already annotated in THIS process. The park fires once per item and
#: the publisher runs on a */5 cron, so an unarmed desk with a queue behind it
#: would otherwise bury the Actions summary the annotation exists to surface.
#: Keyed by account, not by item: the operator's action is the same one
#: desk_network flip however many items are behind it.
_WARNED_DARK_PARK: set[str] = set()

#: Ledger note for BOTH park sites. Starts with the reason class sentinel's
#: _ALWAYS_ENFORCED already names, so a parked item greps the same as a
#: plan-gate quarantine and no operator exception can revive it.
_DARK_PARK_NOTE = (
    "account_disabled: desk not enabled in desk_network — dispatch-time park "
    "(arming = enable the desk; parked items stay parked)"
)


def reset_dark_park_warnings() -> None:
    """Clear the once-per-process dark-park warning set (tests)."""
    _WARNED_DARK_PARK.clear()


def _warn_dark_park(acct: str) -> None:
    """Print the dark-desk park annotation at most once per account per process."""
    if acct in _WARNED_DARK_PARK:
        return
    _WARNED_DARK_PARK.add(acct)
    # Start-of-line annotation (house law): a logger prefix makes GitHub drop it
    # silently, and a dispatch aimed at a dark property is exactly what the
    # operator must see in the Actions summary.
    print(
        f"::warning title=publisher-dark-desk::item(s) for {acct!r} parked — the "
        "desk is not enabled in desk_network (reason account_disabled). Enabling "
        "the desk (one desk_network flip, or an account_overrides.json entry) "
        "arms dispatch; parked items stay parked — wire copy is perishable and "
        "fresh items flow once armed.",
        flush=True,
    )


# Kinds whose producers compose item text as headline + "\n\n" + body
# (outbox.compose_text): the content-plan desks (signal/chart/education/
# macro/receipt/watchlist/event/mover/theme_list) and the earnings fastlane.
# wire/breaking are EXCLUDED on purpose — a press/wire summary is ONE text
# block with no headline, and validate_copy 4f skips headline="" callers for
# the same reason. A kind not listed here is simply not screened: post-time
# quarantine is terminal, so unknown shapes fail SAFE (unscreened), never
# fail dead.
_HEADLINE_KINDS = frozenset({
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "mover", "theme_list", "earnings",
})


def _queued_headline(kind: str | None, text: str) -> str | None:
    """The headline of a queued item, or None when the shape is ambiguous.

    Outbox items carry ONE string (`text`); the headline exists only as the
    first block of the headline-bearing kinds' composition. Recover it ONLY
    when unambiguous: the kind is a headline-bearing kind, the text has the
    two-block shape, the first block is a single non-empty line, and a
    non-empty body follows. Anything else returns None and is left to the
    generation-time bar — a terminal gate must never guess.
    """
    if kind not in _HEADLINE_KINDS:
        return None
    head, sep, rest = text.partition("\n\n")
    if not sep or not rest.strip():
        return None
    head = head.strip()
    if not head or "\n" in head:
        return None
    return head


_PUBLICATIONS_REL = Path("data/marketing/publications.jsonl")


def _publication_row(it: dict, text: str, receipt, *, published_at: str) -> dict:
    """A PublicationReceipt-shaped row (contracts/marketing_publication_receipt.v1)
    for one live X post — the Channels page reads publications.jsonl, and until now
    posted receipts landed ONLY in the outbox status ledger, so that page stayed dead.

    Required schema fields (publication_id, asset_id, channel, account, published_at,
    campaign_id) are always populated; the rest carry honest live-post defaults.
    """
    iid = str(it.get("id", ""))
    external_id = getattr(receipt, "external_id", None)
    external_url = getattr(receipt, "external_url", None)
    return {
        "publication_id": f"pub-{iid}" if iid else f"pub-{external_id or 'unknown'}",
        "asset_id": iid,
        "channel": "x",
        "account": it.get("account", ""),
        "remote_id": external_id,
        "published_at": published_at,
        "effective_copy_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "policy_version": str(it.get("policy_version") or "v1"),
        "audience": "public",
        "destination": "x_timeline",
        # Items don't carry a campaign_id today; fall back to provenance so the
        # required field is never empty. A later PR threads real campaign ids.
        "campaign_id": str(it.get("campaign_id") or it.get("provenance") or "publisher_live"),
        "experiment_cell": it.get("experiment_cell"),
        "correction_state": "clean",
        "takedown_method": "unpublish_via_adapter",
        "mode": "live",
        "external_url": external_url,
    }


def _record_persona_post(
    root: Path | str | None,
    item: dict,
    account: str,
    text: str,
    now: datetime,
) -> None:
    """Record a SHIPPED post into persona memory (XG-W3, charter §4).

    Called from the one posting-success branch, which both the ladder and the
    immediate/fastlane lanes flow through — so a post shipped by either lane
    spends the same quirk budget.

    DIAL-GOVERNED ACCOUNTS ONLY. The store exists to arm the XG-W1 per-quirk
    frequency caps, and those live in a persona's `voice_codex`. An account with
    no codex has no caps to enforce, so recording its posts would grow a tracked
    ledger nothing ever reads.

    FAIL-SOFT, DELIBERATELY. The post has already gone out by the time we get
    here; raising would turn a successful publish into a failed run and could
    re-drive the item. A lost counter costs one unit of cap precision, which is
    strictly cheaper than a double-post.
    """
    try:
        from engine.marketing import expression_dial as _ed  # noqa: PLC0415

        if _ed.codex_for(account) is None:
            return
        from engine.marketing import persona_memory as _pm  # noqa: PLC0415

        _pm.record_post(
            account,
            text,
            now=now,
            as_of=str(item.get("as_of") or ""),
            franchise=str((item.get("source") or {}).get("franchise") or ""),
            kind=str(item.get("kind") or ""),
            item_id=str(item.get("id") or ""),
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("persona_memory: could not record post for %s (%s) — "
                    "frequency caps lose one unit of history", account, exc)


def _append_publication(root: Path | str | None, row: dict) -> None:
    """Append a publication receipt to publications.jsonl. Fail-soft — a ledger
    write must never turn a successful post into a crash."""
    from engine.marketing.ledgers import append_jsonl  # noqa: PLC0415
    try:
        append_jsonl(Path(_data_root(root)) / _PUBLICATIONS_REL, row)
    except Exception as exc:  # noqa: BLE001
        log.warning("publisher: publications.jsonl append failed for %s: %s",
                    row.get("asset_id", "?"), exc)


def _links_allowed_for(pub_cfg: dict, account: str) -> bool:
    v = (pub_cfg.get("links_allowed") or {}).get(account, False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _media_enabled_cfg(pub_cfg: dict) -> bool:
    """publish.media_enabled — the top-level chart-image attach gate (default OFF)."""
    v = pub_cfg.get("media_enabled", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


def _media_paths_for(it: dict, pub_cfg: dict, sidecar: dict | None = None) -> list[str]:
    """Public media URLs to attach to a post (PNG on X; Buffer needs a hosted URL).

    Prefers the chart's public https media_url (stamped at plan-build time when
    publish.media_enabled AND R2 creds existed). The local .svg/.png `path` is a
    repo file Buffer cannot fetch — _build_assets() skips non-http paths anyway —
    so we never pass it. Returns [] (text-only) when the gate is off or no post
    carries a public URL: the graceful, always-correct fallback.

    `sidecar` is the media-backfill map (scripts/marketing_media_backfill.py),
    consulted ONLY for an entry the plan build left unstamped. That stamp happens
    once, inside the nightly, and only if R2 creds were live in that process —
    so without this fallback a single R2 hiccup makes a whole day's posts
    text-only forever, with the charts rendered and committed but unreachable.
    An item that already carries its own media_url never looks here.
    """
    if not _media_enabled_cfg(pub_cfg):
        return []
    urls: list[str] = []
    for m in it.get("media") or []:
        if not isinstance(m, dict):
            continue
        u = str(m.get("media_url") or "").strip()
        if not u and sidecar:
            key = f"{str(it.get('as_of') or '').strip()}/{str(m.get('chart_id') or '').strip()}"
            u = str(sidecar.get(key) or "").strip()
        if u.lower().startswith(("http://", "https://")):
            urls.append(u)
    return urls


# Kinds whose post is ABOUT a specific name. The operator's standing rule is
# that these always carry their chart ("we should always have illustrations for
# charting tickers ... we're doing entry timing so charting should be used").
# Every other member of outbox.KINDS — macro, education, event, theme_list,
# wire, breaking, earnings, mover — is a method, breadth or news post that
# legitimately goes out as text and must keep flowing.
_CHART_BEARING_KINDS: frozenset[str] = frozenset({
    "signal", "chart", "watchlist", "receipt",
})

# A ticker post whose chart never resolves may not defer forever. Past this age
# the publisher gives up and QUARANTINES it instead of shipping it bare: an
# entry-timing read this stale is not worth posting even if the picture finally
# lands, and posting it text-only is exactly the violation this gate exists to
# prevent. Set to match the no-channel expiry below (deliberately a separate
# number: one is an upload race, the other a misconfiguration).
_MEDIA_DEFER_MAX_AGE_DAYS = 3

_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}\b")


def _item_age_days(it: dict, now: datetime) -> int:
    """Whole days since the item's as_of (else created_at) stamp.

    Unparseable → 0, i.e. "brand new, don't expire": a malformed stamp must
    never be the reason a post is dropped.
    """
    stamp = str(it.get("as_of") or it.get("created_at") or "")[:10]
    try:
        return (now.date() - date.fromisoformat(stamp)).days
    except (ValueError, TypeError):
        return 0


def _item_ticker(it: dict) -> str:
    """The name this post is about, or "" for a method/macro/breadth post.

    Emitted items carry NO top-level `ticker`: the outbox writes it to
    `source.ticker` (every signal/chart/watchlist row has one) and mirrors it
    onto each `media[]` entry. Top-level `ticker`/`cashtag` are still read first
    so an emitter that later promotes the field is picked up for free.

    The copy's own cashtag is the last resort. By the time we look there `kind`
    has already narrowed us to the chart-bearing four, so a `$SPY` mentioned in
    passing by a macro or education post can never reach this line.
    """
    src = it.get("source") if isinstance(it.get("source"), dict) else {}
    for v in (it.get("ticker"), it.get("cashtag"),
              src.get("ticker"), src.get("cashtag")):
        if isinstance(v, str) and v.strip():
            return v.strip().lstrip("$")
    for m in it.get("media") or []:
        if isinstance(m, dict) and str(m.get("ticker") or "").strip():
            return str(m["ticker"]).strip().lstrip("$")
    hit = _CASHTAG_RE.search(str(it.get("text") or ""))
    return hit.group(0).lstrip("$") if hit else ""


def _missing_required_media(it: dict, pub_cfg: dict, media_paths: list[str]) -> bool:
    """True when this is a ticker post that HAS a chart and cannot reach it.

    The gap: media_url is stamped once, inside the nightly's content_studio, and
    only if R2 creds were live in that process. Any publish sweep that fires
    between a failed upload and scripts/marketing_media_backfill.py resolves
    nothing and ships the read BARE to all seven desks — a silent violation of
    the illustrate-every-ticker rule, and a live race rather than a rare one.

    All four conditions are load-bearing:
      * media_enabled ON — with the global gate off NOTHING resolves a URL, so
        deferring on that would wedge the entire ticker queue instead of one item;
      * no resolved URL — neither the plan-build stamp nor the backfill sidecar;
      * chart-bearing kind — a macro/education/breadth post has no chart to miss;
      * a non-empty media[] — the chart was BUILT, so the URL is recoverable and
        deferring is honest. An item that never had a media entry is a different
        gap (nothing was rendered) and is out of scope here.
    """
    if not _media_enabled_cfg(pub_cfg) or media_paths:
        return False
    if str(it.get("kind") or "").strip().lower() not in _CHART_BEARING_KINDS:
        return False
    if not any(isinstance(m, dict) for m in (it.get("media") or [])):
        return False
    return bool(_item_ticker(it))


def _chart_ids_for(it: dict) -> str:
    """The item's chart ids, for the operator log line — so a deferral names
    exactly which chart failed to upload rather than just the item id."""
    ids = [str(m.get("chart_id") or "").strip()
           for m in (it.get("media") or []) if isinstance(m, dict)]
    return ",".join(i for i in ids if i) or "?"


def _auto_approve_cfg(pub_cfg: dict) -> bool:
    """publish.auto_approve, parsed strictly (a quoted "false" must not enable)."""
    v = pub_cfg.get("auto_approve", False)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


#: publish.auto_approve_scope values. "kinds" is the W1 default.
_AUTO_APPROVE_SCOPES: frozenset[str] = frozenset({"kinds", "all"})


def _auto_approve_scope_cfg(pub_cfg: dict) -> str:
    """publish.auto_approve_scope → "kinds" (default) | "all".

    WHAT THIS NARROWS (masterplan §7, operator directive 2026-07-29). Until now
    `publish.auto_approve: true` meant EVERY kind: the nightly's own persona
    posts cleared themselves and went to X with no human in the loop. On
    2026-07-29 that auto-approved 61 posts the operator then aborted reviewing in
    disgust — one lever, no way to keep the descriptive publish-time tape posts
    automatic while the diary-register posts wait for a decision.

    "kinds" splits the lever: the global flag still turns the pass ON, but only
    `publish.auto_approve_kinds` items from the publish-time lane may clear it
    (mover/theme_list today; breaking and the wire lanes keep their own
    immediate paths). Planned kinds — signal, chart, education, macro, receipt,
    watchlist, event — wait for an operator decision, which is where the
    approve-ladder gets its label stream from (masterplan §7).

    "all" restores the pre-W1 behaviour exactly, and is the ONE config line the
    operator flips to get full autonomy back.

    Parsed strictly and fail-CLOSED: an unknown value falls back to "kinds" with
    a warning, because the failure mode of a typo here is publishing unreviewed
    copy. The scope governs `--auto-approve` too — the flag's help calls itself
    equivalent to the config key, and two lanes with different scopes would be a
    trap rather than a convenience.
    """
    raw = pub_cfg.get("auto_approve_scope", "kinds")
    v = str(raw).strip().lower() if raw is not None else "kinds"
    if v not in _AUTO_APPROVE_SCOPES:
        log.warning("publish.auto_approve_scope: unknown value %r — using 'kinds' "
                    "(valid: %s)", raw, ", ".join(sorted(_AUTO_APPROVE_SCOPES)))
        return "kinds"
    return v


def _auto_approve_kinds_cfg(pub_cfg: dict) -> frozenset[str]:
    """publish.auto_approve_kinds → the set of kinds that may auto-approve even
    while publish.require_approval is true, but ONLY for publish-time-lane items
    (provenance publisher_live_movers — enforced in _auto_approve_pass).

    Parsed STRICTLY: each entry must be a lowercase string that is a member of
    outbox.KINDS; junk (non-strings, unknown kinds) is ignored with a warning so
    a typo can never silently widen the auto-approve surface. Absent/empty → the
    empty set (no scoped exception; fully manual).
    """
    raw = pub_cfg.get("auto_approve_kinds")
    if not raw or not isinstance(raw, (list, tuple)):
        return frozenset()
    try:
        from engine.marketing.outbox import KINDS  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        KINDS = frozenset()  # type: ignore[assignment]
    out: set[str] = set()
    for v in raw:
        if not isinstance(v, str):
            log.warning("publish.auto_approve_kinds: ignoring non-string entry %r", v)
            continue
        k = v.strip().lower()
        if KINDS and k not in KINDS:
            log.warning("publish.auto_approve_kinds: ignoring unknown kind %r", v)
            continue
        out.add(k)
    return frozenset(out)


def _at_cap(count: int, cap: int) -> bool:
    """True when ``count`` has reached a REAL per-account daily cap. A negative
    cap is the UNLIMITED sentinel (config ``max_posts_per_account_per_day: -1``,
    surfaced by ``outbox.effective_cap`` as ``-1``): it means NO limit, so this
    is always False. Every daily-cap gate routes through here so the -1 trap
    (``0 >= -1`` → skip everything) can never re-appear at one site and not
    another — the cap is a FUNCTIONAL gate on posting, not just a display value.
    """
    return cap >= 0 and count >= cap


def _floor_minutes_cfg(pub_cfg: dict) -> int:
    """publish.min_minutes_between_any_posts — the GLOBAL post-time anti-spam
    floor: no two posts go out within N minutes of each other, across ALL
    accounts (distinct from the sentinel's per-account *plan-time* cadence
    min_minutes_between_posts). 0 / absent / non-positive / unparseable → 0 =
    disabled (fully backward-compatible)."""
    raw = pub_cfg.get("min_minutes_between_any_posts", 0)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def _jitter_max_cfg(pub_cfg: dict) -> int:
    """publish.post_jitter_max_min — the widest send-time offset, in minutes, a
    LADDER item may be booked past the sweep minute.

    Fixed cron-sweep minutes are a temporal-regularity bot signature (the June
    2026 purge detection class): an account whose posts land on the same minute
    every day looks scheduled, because it is. 0 / absent / negative / unparseable
    → 0 = disabled, which reproduces the exact pre-jitter booking behaviour.
    """
    raw = pub_cfg.get("post_jitter_max_min", 0)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def _forward_book_horizon_cfg(pub_cfg: dict) -> int:
    """publish.max_forward_book_min — how far AHEAD of now one sweep may book a
    ladder item that is inside the global spacing floor. 0 / absent → 0, which
    reproduces the pre-2026-07-28 behaviour exactly (the item defers to the next
    sweep instead of being booked).

    WHY THIS EXISTS. The floor guarantees "no two posts closer than
    min_minutes_between_any_posts". The original enforcement deferred any item
    inside the floor to the next cron sweep, which silently made the SWEEP the
    unit of throughput: 30 sweeps/day → at most 30 posts/day network-wide, no
    matter how many the desks generated or what the per-account caps allowed.
    With the desks generating ~59/day that quietly strands more than half the
    queue every day, and it degrades further whenever a sweep is dropped.

    Booking forward enforces the SAME spacing without that coupling: the item is
    handed to Buffer as a customScheduled post at (floor + spacing), so the send
    times are identical to what the defer path would eventually have produced —
    they are simply reserved now instead of re-derived one sweep at a time.

    The horizon is the safety bound, and it is a TAPE-FRESHNESS bound, not a
    performance knob: every item is verified against live quotes at BOOK time
    (live_verify), so booking N minutes ahead ships a read that is up to N
    minutes stale. Keep it near the live gate's own max_quote_age_min rather
    than raising it to drain the queue faster — a whole day booked at 09:00 is
    a whole day of reads written against the 09:00 tape.
    """
    raw = pub_cfg.get("max_forward_book_min", 0)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def _post_jitter_minutes(item_id: str, jitter_max: int) -> int:
    """The send-time offset for one item, in [0, jitter_max].

    DERIVED FROM THE ITEM ID, never from a clock or an RNG: a dry-run, the admin
    preview and the live run must all book the same minute, and no test may need
    a frozen clock to assert on it. crc32 is used as a cheap stable hash — it is
    not a checksum here, and it must never be swapped for hash() (PYTHONHASHSEED
    randomises str hashing per process).
    """
    if jitter_max <= 0 or not item_id:
        return 0
    return zlib.crc32(item_id.encode("utf-8")) % (jitter_max + 1)


def _last_global_post_at(root) -> "datetime | None":
    """The most recent 'posted' transition time across ALL accounts (the floor is
    account-agnostic), or None if nothing has ever posted. Seeds the floor across
    cron runs. Fail-soft: malformed rows / timestamps are skipped, never raises.

    Prefers the receipt's ``booked_at`` — the wall-clock the post was actually
    BOOKED for — over the row's ``at``, which is only when the ledger row was
    written. With send-time jitter the two diverge by up to
    publish.post_jitter_max_min minutes, and seeding the floor from the write
    time would let the next run book inside the previous post's floor window.
    Rows with no booked_at (everything written before jitter shipped) fall back
    to ``at``, where the two were equal anyway.
    """
    from engine.marketing.outbox import read_ledger  # noqa: PLC0415
    latest: "datetime | None" = None
    for row in read_ledger(root):
        if row.get("to") != "posted":
            continue
        receipt = row.get("receipt")
        booked = (str(receipt.get("booked_at") or "").strip()
                  if isinstance(receipt, dict) else "")
        raw = booked or str(row.get("at") or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if latest is None or dt > latest:
            latest = dt
    return latest


def _within_floor(last_post_at: "datetime | None", now: datetime, floor_min: int) -> bool:
    """True when posting *now* would violate the global min-spacing floor — the
    last post was less than floor_min minutes ago. No prior post or a non-positive
    floor → never blocks. Callers advance ``last_post_at`` in memory after each
    post so a single run emits at most one item per window."""
    if last_post_at is None or floor_min <= 0:
        return False
    return (now - last_post_at) < timedelta(minutes=floor_min)


def _select_approved_due(state: dict, statuses: dict, items_by_id: dict,
                         account: str | None, now: datetime,
                         only_ids: "frozenset[str] | None" = None) -> list[dict]:
    """The APPROVED + DUE candidate set (+ optional account filter), sorted the
    canonical way: priority, then schedule, then id. Refactored out of main() so
    it can run twice (once to feed generate_slot_items a preliminary list, once
    after the auto-approve pass) without duplicating the selection logic.

    ``only_ids`` is the operator "post now" override: the set collapses to those
    ids and the DUE check is dropped (posting now is the entire point — an item
    still sitting on a later ladder slot must be eligible). Every SAFETY gate in
    the caller — validation, tape gate, cap, channel, floor — still runs.
    """
    out: list[dict] = []
    for iid, s in statuses.items():
        if s != "approved" or iid not in items_by_id:
            continue
        it = items_by_id[iid]
        if only_ids is not None:
            if iid not in only_ids:
                continue
            out.append(it)
            continue
        if account is not None and it.get("account") != account:
            continue
        if not _is_due(it.get("scheduled_at"), now):
            continue
        out.append(it)
    out.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")))
    return out


def _auto_approve_pass(
    outbox, state: dict, pub_cfg: dict, *, cap: int, now: datetime, live: bool,
    account: str | None, posted_today: dict, validate_postable, root,
    allowed_kinds: "frozenset[str] | None" = None,
    only_ids: "frozenset[str] | None" = None,
    cap_for=None,
    halted: "set[str] | frozenset[str] | None" = None,
    dark_accounts: "frozenset[str] | None" = None,
    announce: bool = True,
    parked_out: "list[str] | None" = None,
) -> list[str]:
    """Auto-advance queued → approved for items passing ALL publish gates.

    Gates (an item must clear every one to be auto-approved):
      * the account is NOT halted (XG-W6 health monitor / network tripwire).
        Auto-approving for a halted desk would build a pile of approved items
        the post loop then refuses one by one — noise that hides the halt.
      * the account is LIVE: an account that is not effective-enabled in
        desk_network (``dark_accounts``) is QUARANTINED here, not skipped. The
        halt above skips on purpose — a halt is temporary and the item is fine —
        but a dark desk is a durable ARMING state and its wire copy is
        perishable, so quarantine is the honest terminal park rather than a pile
        that would fire stale the day someone flips the switch. The reason class
        is ``account_disabled``, which sentinel holds in _ALWAYS_ENFORCED: no
        operator exception overrides it, and neither does an operator --post-now
        (see ``only_ids`` below). The remedy is the desk_network flip.
      * NOT held (a queued item whose latest operator decision is 'hold' stays put)
      * kind scope: when ``allowed_kinds`` is not None (global publish.auto_approve
        is OFF but publish.auto_approve_kinds is set), an item is a candidate ONLY
        if its kind is in allowed_kinds AND it was generated by the publish-time
        lane (provenance publisher_live_movers). When allowed_kinds is None
        (global auto_approve ON), the scope is unrestricted — every kind, exactly
        as before.
      * validate_postable() clean (280 cap, link policy, non-empty text)
      * a channel id is configured for its account
      * the account is under the per-account daily cap, counting BOTH items
        already posted today AND items this pass has already approved this run
        (so auto-approve never over-fills the queue past the cap)

    DRY-RUN safety: when ``live`` is False this makes NO ledger writes — it only
    logs and returns the ids it WOULD approve. The queued→approved transition is
    applied via outbox.transition() ONLY when ``live`` is True.

    ``announce`` False silences the dark-desk annotation for the writeless admin
    preview (same reason resolve_ramp takes announce=False there). It is not
    cosmetic: the annotation is once-per-account-per-PROCESS, so a preview that
    printed it would also CONSUME it and the real dispatch behind it would park
    silently. A preview is not a dispatch and must leave that budget alone — and
    for the same reason a DRY-RUN never annotates either, whatever ``announce``
    says. ``parked_out`` is the matching sink — the caller that cannot read the
    log (the preview builds a dict; main() folds the count into its summary) gets
    the parked ids appended to it.

    ``only_ids`` is the operator "post now" override: the pass considers ONLY
    those ids and drops the kind scope (the operator's click IS the approval for
    any kind). It does NOT relax a hold, nor any of the gates above — an item
    that fails validation, has no channel, is at cap, or is addressed to a dark
    desk still will not post.

    Returns the list of item ids that were (or, in dry-run, would be) approved,
    in the deterministic order they were considered.
    """
    items_by_id = state["items"]
    statuses = state["status"]
    held = state.get("held") or set()

    # Running per-account budget: seed from what is already posted today, then
    # also charge each already-approved+due item so auto-approve tops up TO the
    # cap, not beyond it (approved-but-not-yet-posted still consumes a slot).
    budget: dict[str, int] = dict(posted_today)
    for iid, s in statuses.items():
        if s == "approved" and iid in items_by_id:
            it = items_by_id[iid]
            if account is not None and it.get("account") != account:
                continue
            if _is_due(it.get("scheduled_at"), now):
                acct = it.get("account", "")
                budget[acct] = budget.get(acct, 0) + 1

    # Kind-scope predicate. allowed_kinds None → unrestricted (global auto_approve
    # ON, legacy behavior). allowed_kinds set → ONLY publish-time-lane items of a
    # listed kind may auto-approve (the scoped exception to require_approval).
    _scoped = allowed_kinds is not None and only_ids is None
    _AUTO_LANE = "publisher_live_movers"

    def _kind_ok(it: dict) -> bool:
        if not _scoped:
            return True
        return (it.get("kind") in allowed_kinds
                and it.get("provenance") == _AUTO_LANE)

    # Deterministic consideration order: priority, then schedule, then id.
    candidates = [
        items_by_id[iid] for iid, s in statuses.items()
        if s == "queued" and iid in items_by_id and iid not in held
        and (only_ids is None or iid in only_ids)
        and (only_ids is not None
             or account is None or items_by_id[iid].get("account") == account)
        and _kind_ok(items_by_id[iid])
    ]
    candidates.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")))

    approved: list[str] = []
    for it in candidates:
        iid = it["id"]
        acct = it.get("account", "")
        text = it.get("text", "") or ""
        link = it.get("link")
        links_allowed = _links_allowed_for(pub_cfg, acct)

        if halted and acct in halted:
            log.info("auto-approve SKIP %s (%s): account HALTED", iid, acct)
            continue

        # Dark desk: routing is pure — an emitter addresses a desk by what the
        # item IS, never by whether that desk is armed — so liveness binds HERE,
        # ahead of every other gate. A dark property costs nothing, reaches
        # nothing, and no operator post_now overrides account_disabled.
        if dark_accounts and acct in dark_accounts:
            log.warning("auto-approve PARK %s (%s): account dark (desk_network)",
                        iid, acct)
            if live:
                outbox.transition(iid, "quarantined", actor="publisher",
                                  root=root, note=_DARK_PARK_NOTE)
            if parked_out is not None:
                parked_out.append(iid)
            # Annotation only when something actually happened: a dry-run wrote
            # no ledger row, so "item(s) parked" would be a claim about a park
            # that did not occur — and it would spend the once-per-process budget
            # the next live run needs. The log lines above still say it.
            if announce and live:
                _warn_dark_park(acct)
            continue

        problems = validate_postable(text, link, links_allowed)
        if problems:
            log.info("auto-approve SKIP %s (%s): fails validation %s", iid, acct, problems)
            continue
        if not _channel_id_for(pub_cfg, acct):
            log.info("auto-approve SKIP %s (%s): no channel id configured", iid, acct)
            continue
        # Breaking/immediate items are cap-EXEMPT (operator 2026-07-27: breaking
        # has no volume limits). An item is immediate when it is an operator
        # "post now" (only_ids) or carries no ladder slot (_is_immediate).
        _immediate = (only_ids is not None and iid in only_ids) \
            or _is_immediate(it.get("scheduled_at"))
        _acct_cap = cap_for(acct) if cap_for is not None else cap
        if not _immediate and _at_cap(budget.get(acct, 0), _acct_cap):
            log.info("auto-approve SKIP %s (%s): account at daily cap (%d/day)",
                     iid, acct, _acct_cap)
            continue

        if live:
            _note = ("auto-approved (kind-scoped publish-time lane)" if _scoped
                     else "auto-approved (all gates passed)")
            if not outbox.transition(iid, "approved", actor="publisher-autoapprove",
                                     root=root, note=_note):
                log.warning("auto-approve %s: transition failed — leaving queued", iid)
                continue
            log.info("auto-approve APPROVED %s (%s)", iid, acct)
        else:
            log.info("WOULD AUTO-APPROVE %s (%s) chars=%d", iid, acct, len(text))
        budget[acct] = budget.get(acct, 0) + 1
        approved.append(iid)

    return approved


def _is_due(scheduled_at: str | None, now: datetime) -> bool:
    """True if the item is due to post now.

    "immediate" (or empty/missing) is always due. Otherwise parse the ISO
    timestamp and compare; an unparseable value is treated as NOT due (fail
    closed — never post something on a schedule we cannot read).
    """
    s = (scheduled_at or "").strip()
    if not s or s == "immediate":
        return True
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= now
    except (ValueError, TypeError):
        log.warning("unparseable scheduled_at %r — treating as NOT due", scheduled_at)
        return False


def _make_publisher(backend: str, *, token: str, cfg: dict):
    """Instantiate the configured backend publisher. Returns None if unsupported."""
    from engine.marketing.social_publisher import BufferPublisher  # noqa: PLC0415
    if backend == "buffer":
        return BufferPublisher(token=token)
    log.error("unsupported publish backend %r", backend)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marketing live social publisher (D02 W1 — dark by default)"
    )
    parser.add_argument("--live", action="store_true",
                        help="Actually post (requires MARKETING_PUBLISH_ENABLED=1 too). "
                             "Without this flag the runner is a dry-run.")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-advance queued→approved for items that pass ALL gates "
                             "(validate_postable clean, under the daily cap, channel id set) "
                             "before selecting approved items. OFF by default; also enabled by "
                             "config publish.auto_approve. HONORS publish.auto_approve_scope: "
                             "under the default 'kinds' only publish.auto_approve_kinds items "
                             "from the publish-time lane clear, and planned nightly kinds wait "
                             "for an operator decision; 'all' is the unrestricted blanket. "
                             "In DRY-RUN this only REPORTS what it "
                             "would approve — it never mutates the ledger.")
    parser.add_argument("--account", default=None,
                        help="Only process this account id (default: all accounts)")
    parser.add_argument("--list-channels", action="store_true",
                        help="Print the backend's connected channels and exit "
                             "(for channel-id discovery; needs BUFFER_TOKEN)")
    parser.add_argument("--root", default=None,
                        help="Repo root directory (default: derived from script location)")
    parser.add_argument("--now", default=None,
                        help="Override 'now' as ISO8601 (testing/determinism)")
    parser.add_argument("--post-now", default=None, metavar="ID[,ID…]",
                        help="BREAKING DISPATCH: restrict this run to these outbox item "
                             "ids, approve them regardless of the auto-approve config, "
                             "and send them immediately. SKIPS ONLY PACING: the ladder "
                             "slot, the per-account daily cap, the cadence resolver, the "
                             "global min-spacing floor and the send-time jitter. Every "
                             "SAFETY gate still runs — validation, banned language, the "
                             "chart-required law, repeat/near-dup, the live tape gate, "
                             "channel, account halts and the global kill switch. It "
                             "cannot arm the publisher: without --live and "
                             "MARKETING_PUBLISH_ENABLED this is still a dry run.")
    args = parser.parse_args(argv)

    # Operator/breaking override: a non-empty set switches the run into
    # "post these, now" mode. Blank entries are dropped so `--post-now ""` (a
    # workflow input that was left empty) is simply a normal sweep.
    post_now: frozenset[str] = frozenset(
        p.strip() for p in str(args.post_now or "").split(",") if p.strip()
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _ensure_importable()
    root = _data_root(args.root)
    cfg = _load_marketing_cfg(root)
    pub_cfg = _publish_cfg(cfg)
    backend = str(pub_cfg.get("backend") or "buffer").strip()
    token = os.environ.get("BUFFER_TOKEN", "").strip()

    now = _parse_now(args.now)

    # ── --list-channels convenience path (gated on a token) ─────────────────
    if args.list_channels:
        return _run_list_channels(backend, token=token, cfg=cfg)

    from engine.marketing import outbox as _outbox  # noqa: PLC0415
    try:
        from engine.marketing.sentinel import publish_enabled as _publish_enabled  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        def _publish_enabled() -> bool:  # conservative: switch off
            return False

    from engine.marketing.social_publisher import validate_postable  # noqa: PLC0415

    kill_on = _publish_enabled()
    live = bool(args.live) and kill_on
    cap = _outbox.effective_cap(cfg)

    # ── Per-account daily cap, narrowed by the D08 age ramp ──────────────────
    # `cap` above is the BASE ceiling (-1/unlimited live), which made every
    # post-time cap check vacuously false: an approved backlog could drain at ~one
    # per sweep, ~30/day, past a week-1 account's 2. The plan gate cannot catch
    # those — they already cleared it, on an earlier day or via the operator.
    # The reference date here is the RUNTIME POSTING date, not the plan's as_of:
    # an account can cross a tier boundary between plan build and post time, and
    # each seam applies the stricter answer for its own moment.
    _post_date = now.strftime("%Y-%m-%d")
    try:
        from engine.marketing.sentinel import resolve_ramp as _resolve_ramp  # noqa: PLC0415
        _ramp = _resolve_ramp(cfg, _post_date, root=root)
    except Exception as _ramp_exc:  # noqa: BLE001 — never break a run on a cap lookup
        log.warning("ramp unavailable (%s) — falling back to the base cap", _ramp_exc)
        _ramp = None

    def _cap_for(account: str) -> int:
        return _outbox.effective_cap_for(cfg, account, _post_date,
                                         root=root, ramp=_ramp)

    state = _outbox.fold_state(root)
    items_by_id = state["items"]
    statuses = state["status"]

    # ── Startup safety: report items stuck in `posting`, NEVER repost them ───
    stuck_posting = [
        i for i, s in statuses.items()
        if s == "posting" and i in items_by_id
        and (args.account is None or items_by_id[i].get("account") == args.account)
    ]
    for iid in stuck_posting:
        log.warning(
            "item %s is stuck in 'posting' (in-flight from a prior run) — "
            "reporting, NOT reposting (no-double-post)", iid)

    # ── Per-account cap accounting: ledger-based posts-today ─────────────────
    # NOT as_of-based: nightly items post the day AFTER their as_of, so as_of
    # counting misses them — see outbox.posted_today_by_account.
    today = now.strftime("%Y-%m-%d")
    posted_today: dict[str, int] = _outbox.posted_today_by_account(state, today)

    # ── Publish-time mover/theme generation (honest live tape posts) ─────────
    # mover/theme_list posts are generated NIGHTLY but never emitted (a "+7%
    # today" claim is stale next morning). Generate them HERE from the freshest
    # tape in this checkout, enqueue via outbox, and let the tape gate re-verify
    # them below. Runs BEFORE the auto-approve pass so the scoped lane can pick
    # them up this same run. Fully fail-soft: any error leaves the legacy flow
    # untouched. The preliminary approved_due list feeds the module's per-account
    # spacing law (one post per account per slot run).
    pt_generated = pt_dropped = 0
    try:
        from engine.marketing import publish_time_content as _pt  # noqa: PLC0415
        _prelim_due = _select_approved_due(state, statuses, items_by_id,
                                           args.account, now)
        _pt_report = _pt.generate_slot_items(
            root, cfg=cfg, now=now, state=state, approved_due=_prelim_due,
            posted_counts=posted_today, cap=cap, live=live,
            account_filter=args.account,
        )
        pt_generated = len(_pt_report.get("generated") or [])
        pt_dropped = len(_pt_report.get("dropped") or [])
        log.info(
            "publish-time generation | enabled=%s slot=%s quotes=%s "
            "generated=%d would_generate=%d dropped=%d",
            _pt_report.get("enabled"), _pt_report.get("slot") or "-",
            _pt_report.get("quote_source"), pt_generated,
            len(_pt_report.get("would_generate") or []), pt_dropped,
        )
        for _d in (_pt_report.get("dropped") or []):
            log.info("  pt drop: %s — %s", _d.get("reason"), _d.get("detail"))
        for _w in (_pt_report.get("would_generate") or []):
            log.info("  WOULD GENERATE | account=%s kind=%s %s | %s",
                     _w.get("account"), _w.get("kind"), _w.get("ticker") or "",
                     _w.get("text", ""))
        if live and pt_generated:
            # Re-fold so the auto-approve pass + candidate set see the new items.
            state = _outbox.fold_state(root)
            items_by_id = state["items"]
            statuses = state["status"]
    except Exception as _pt_exc:  # noqa: BLE001
        log.warning("publish-time generation unavailable (%s) — legacy flow unaffected",
                    _pt_exc)

    # ── Publish-time DAILY READ (kind=event, "My read on today's move") ──────
    # DARK by default (publish.publish_time_read.enabled false → the generator
    # returns a disabled report and writes nothing). When armed it generates the
    # read from the FRESH daily brief on the after-close ladder slot, once/day,
    # provenance publisher_live_movers so the scoped auto-approve (publish.
    # auto_approve_kinds must include `event`) can pick it up this run. Sibling
    # try so it is independently fail-soft: any error leaves the legacy flow
    # untouched. Runs BEFORE the auto-approve pass, like the mover lane above.
    try:
        from engine.marketing import publish_time_content as _pt  # noqa: PLC0415
        _read_report = _pt.generate_read_item(
            root, cfg=cfg, now=now, state=state, live=live,
            account_filter=args.account,
        )
        _read_generated = len(_read_report.get("generated") or [])
        log.info(
            "publish-time read | enabled=%s slot=%s generated=%d would_generate=%d "
            "dropped=%d",
            _read_report.get("enabled"), _read_report.get("slot") or "-",
            _read_generated, len(_read_report.get("would_generate") or []),
            len(_read_report.get("dropped") or []),
        )
        for _d in (_read_report.get("dropped") or []):
            log.info("  read drop: %s — %s", _d.get("reason"), _d.get("detail"))
        for _w in (_read_report.get("would_generate") or []):
            log.info("  READ WOULD GENERATE | account=%s kind=%s | %s",
                     _w.get("account"), _w.get("kind"), _w.get("text", ""))
        if live and _read_generated:
            # Re-fold so the auto-approve pass + candidate set see the new items.
            state = _outbox.fold_state(root)
            items_by_id = state["items"]
            statuses = state["status"]
    except Exception as _read_exc:  # noqa: BLE001
        log.warning("publish-time read unavailable (%s) — legacy flow unaffected",
                    _read_exc)

    # ── OPTIONAL auto-approve: queued → approved for items that pass ALL gates ─
    # Gated OFF by default; enabled by publish.auto_approve OR --auto-approve.
    # This is the operator's path to full automation — leave it off during the
    # aged-account warm-up. In DRY-RUN it only REPORTS what it would approve and
    # NEVER mutates the ledger (the transitions happen only when `live`).
    #
    # SCOPED exception (publish.auto_approve_kinds): when the global flag is OFF
    # but a kind list is configured, the pass still runs — restricted to
    # publish-time-lane items of those kinds (the descriptive tape posts above).
    # Operator-authored / nightly items of any kind still require approval.
    #
    # --post-now (breaking dispatch) FORCES the pass on, scoped to the requested
    # ids: the operator clicking "Post now" IS the approval, so the run must not
    # depend on publish.auto_approve being on — but only for those ids, and only
    # through the same gates.
    # ── PER-ACCOUNT HALT (XG-W6) ─────────────────────────────────────────────
    # The post half of the health monitor's guarantee: a tripped account halts
    # THAT ACCOUNT ONLY (charter §5 — "a failure must be able to halt one
    # account without halting seven"). The registry is read ONCE per run and the
    # table threaded through both the auto-approve pass and the post loop; a
    # per-item read would re-parse the file once per post. Fail-soft by design:
    # an unreadable registry yields {} and announces itself loudly rather than
    # silencing all seven desks, which is the fleet-wide outage the per-account
    # design exists to prevent.
    try:
        from engine.marketing import health_monitor as _health  # noqa: PLC0415

        _halts = _health.load_halts(root)
    except Exception as _hm_exc:  # noqa: BLE001
        log.warning("health monitor unavailable (%s) — no halts enforced", _hm_exc)
        _health, _halts = None, {}
    if _halts:
        log.warning("halted account(s): %s — their posts are blocked; every other "
                    "desk posts normally", sorted(_halts))
    skipped_halt = 0

    # ── DARK DESK PARK (desk_network liveness) ───────────────────────────────
    # The dispatch-time half of the accounts model. Emitters route by what an
    # item IS and never consult liveness — wire_routing states the law outright
    # ("LIVENESS IS NOT ROUTING") — so a wired-but-dark desk whose Buffer channel
    # id already sits in publish.channels was one immediate dispatch away from
    # posting live. Sentinel's plan gate resolves the same disabled-account list
    # (reason account_disabled) but only ever sees the NIGHTLY plan; the
    # breaking/immediate rail is enqueued straight to the outbox and dispatched
    # with --post-now, so it passes no plan gate at all. Read ONCE per run, same
    # idiom as the halt registry, threaded through the auto-approve pass and the
    # post loop. None = liveness unknown = gate INERT (see _dark_account_ids for
    # why unknown must not fail closed here).
    _dark = _dark_account_ids(cfg, root)
    if _dark is None:
        print("::warning title=publisher-dark-desk::accounts model unavailable — "
              "dark-desk park INERT this run (see the log line above for the "
              "error); desk liveness is NOT enforced at dispatch.", flush=True)
    elif _dark:
        log.info("dark desk(s) not enabled in desk_network: %s — any dispatch "
                 "addressed to them parks", sorted(_dark))
    # Parked ids, by gate. Both feed the parked_dark summary count; together they
    # are also what decides the exit code of a post-now dispatch (see the ruling
    # at the end of this function) — a count alone cannot answer "was EVERY
    # requested id parked", which is the difference between an expected park and
    # a real failure.
    _parked_auto: list[str] = []
    _parked_post: list[str] = []

    auto_approve_on = bool(args.auto_approve) or _auto_approve_cfg(pub_cfg)
    allowed_kinds = _auto_approve_kinds_cfg(pub_cfg)
    # W1: the global flag is no longer a blanket. Under the default
    # auto_approve_scope "kinds" it turns the pass ON but the kind scope still
    # binds, so nightly planned-kind posts wait for an operator decision;
    # "all" restores the pre-W1 blanket (see _auto_approve_scope_cfg).
    auto_approve_scope = _auto_approve_scope_cfg(pub_cfg)
    auto_approve_unscoped = auto_approve_on and auto_approve_scope == "all"
    scoped_on = (not auto_approve_unscoped) and bool(allowed_kinds)
    auto_approved: list[str] = []
    if post_now:
        missing = sorted(i for i in post_now if i not in items_by_id)
        if missing:
            log.error("--post-now: unknown item id(s) %s — not in the outbox on this "
                      "checkout (was the item committed to main?)", ", ".join(missing))
        auto_approved = _auto_approve_pass(
            _outbox, state, pub_cfg, cap=cap, now=now, live=live,
            account=args.account, posted_today=posted_today,
            validate_postable=validate_postable, root=root,
            only_ids=post_now, cap_for=_cap_for, halted=set(_halts),
            dark_accounts=_dark, parked_out=_parked_auto,
        )
    elif auto_approve_on or scoped_on:
        # allowed_kinds param: None ONLY when the operator asked for the
        # unrestricted blanket (auto_approve on AND scope "all"); otherwise the
        # configured kind set binds, whether the pass was turned on by the global
        # flag or by the scoped exception alone.
        _kinds_param = None if auto_approve_unscoped else allowed_kinds
        auto_approved = _auto_approve_pass(
            _outbox, state, pub_cfg, cap=cap, now=now, live=live,
            account=args.account, posted_today=posted_today,
            validate_postable=validate_postable, root=root,
            allowed_kinds=_kinds_param, cap_for=_cap_for, halted=set(_halts),
            dark_accounts=_dark, parked_out=_parked_auto,
        )
    if live and auto_approved:
        # Re-fold so the candidate set below sees the freshly-approved items.
        state = _outbox.fold_state(root)
        items_by_id = state["items"]
        statuses = state["status"]

    # ── Candidate set: APPROVED + DUE (+ optional account filter) ────────────
    # With --post-now the set collapses to the requested ids and the DUE check
    # is dropped (see _select_approved_due).
    approved_due = _select_approved_due(state, statuses, items_by_id,
                                        args.account, now,
                                        only_ids=(post_now or None))

    mode = "LIVE" if live else "DRY-RUN"
    log.info(
        "%s | backend=%s cap=%d/day kill_switch=%s --live=%s auto_approve=%s%s | "
        "approved+due=%d stuck_posting=%d auto_approved=%d "
        "pt_generated=%d pt_dropped=%d",
        mode, backend, cap, "ON" if kill_on else "off", bool(args.live),
        ("post-now" if post_now
         else "on(all)" if auto_approve_unscoped
         else "on(kinds)" if auto_approve_on
         else ("scoped" if scoped_on else "off")),
        (f" post_now={','.join(sorted(post_now))}" if post_now else ""),
        len(approved_due), len(stuck_posting), len(auto_approved),
        pt_generated, pt_dropped,
    )
    if bool(args.live) and not kill_on:
        log.warning("--live passed but MARKETING_PUBLISH_ENABLED is not set — "
                    "refusing to post; running as DRY-RUN")

    # ── Lazily build the publisher only when we actually post ────────────────
    publisher = None
    if live:
        publisher = _make_publisher(backend, token=token, cfg=cfg)
        if publisher is None:
            log.error("no usable backend — aborting live run")
            return 2
        if not token:
            log.error("BUFFER_TOKEN empty — refusing live run")
            return 2

    posted = failed = quarantined = skipped_cap = skipped_channel = would_post = 0
    tape_quarantined = tape_skipped = skipped_floor = deferred_immediate = 0
    forward_booked = deferred_no_media = 0

    # ── Global min-spacing floor (publish.min_minutes_between_any_posts) ──────
    # Post-time anti-spam guard: at most one post per floor-minute window across
    # ALL accounts, so an accumulated backlog (or a breaking item) can never
    # burst out at once. Seeded from the last posted row in the ledger so it
    # holds across cron runs, then advanced in-memory after each post so ONE run
    # emits at most one item per window (the rest defer to the next slot). 0 =
    # disabled. This is the Phase-2 floor from the cadence masterplan.
    #
    # IMMEDIATE items are floor-EXEMPT (operator 2026-07-27: breaking has no
    # limits). They post at ``now`` unconditionally — never floor-booked, never
    # deferred, never dropped. A posted immediate item STILL advances the
    # in-memory floor, so the next ladder post budges by the 10-min spacing. A
    # ladder item still defers when inside the floor, unchanged.
    floor_min = _floor_minutes_cfg(pub_cfg)
    last_post_at = _last_global_post_at(root) if floor_min else None

    # ── Media backfill sidecar (fail-soft) ───────────────────────────────────
    # Public chart URLs recovered by scripts/marketing_media_backfill.py for
    # items whose plan build could not reach R2. Loaded ONCE per run; an empty
    # map (no sidecar, unreadable file) reproduces the pre-sidecar behaviour
    # exactly, so a broken ledger costs an image and never a post.
    _media_sidecar: dict = {}
    try:
        from scripts.marketing_media_backfill import load_sidecar as _load_sidecar  # noqa: PLC0415
        _media_sidecar = _load_sidecar(root)
        if _media_sidecar:
            log.info("media backfill sidecar: %d recovered chart URLs", len(_media_sidecar))
    except Exception as _sc_exc:  # noqa: BLE001
        log.warning("media backfill sidecar unavailable (%s) — items keep their own "
                    "media_url only", _sc_exc)

    # ── Forward-booking horizon (publish.max_forward_book_min) ───────────────
    # Decouples network throughput from the cron grid: an item inside the floor
    # is booked at the moment the floor clears (Buffer customScheduled) instead
    # of deferring a whole sweep. Spacing is unchanged; only the reservation
    # moves earlier. 0 = off = the pre-2026-07-28 defer path. See
    # _forward_book_horizon_cfg for why the bound is about tape freshness.
    forward_horizon_min = _forward_book_horizon_cfg(pub_cfg)

    # ── Send-time jitter (publish.post_jitter_max_min) ───────────────────────
    # A ladder item books at (floor-cleared time + a per-item offset) instead of
    # the exact sweep minute, so the account's send times stop landing on the
    # cron's clock. The offset is ADDED on top of the floor-cleared time, so
    # ordering is preserved and the spacing floor is never shortened: the floor
    # then advances to the BOOKED time (not "now"), which is also what the
    # receipt's booked_at carries so the next cron run seeds from it. Immediate /
    # breaking items are never jittered.
    jitter_max = _jitter_max_cfg(pub_cfg)

    # ── Live tape gate context: load once per run (fail-soft) ────────────────
    # The plan was written off yesterday's EOD; the tape has been open for
    # hours by the AM/PM/EOD slots. Every item re-verifies against the freshest
    # repo-local quotes before it may post (engine/marketing/live_verify.py).
    try:
        from engine.marketing import live_verify as _live_verify  # noqa: PLC0415
        _tape = _live_verify.load_live_quotes(root)
        _earn_set = _live_verify.load_earnings_guard_set(root, now=now)
        log.info("live tape gate: %d quotes (%s), %d tickers on earnings guard",
                 len(_tape.get("quotes") or {}), _tape.get("source"), len(_earn_set))
    except Exception as _lv_exc:  # noqa: BLE001
        log.warning("live tape gate unavailable (%s) — signals will be held", _lv_exc)
        _live_verify = None  # type: ignore[assignment]
        _tape = {"quotes": {}, "asof": None, "source": "none"}
        _earn_set = frozenset()

    # ── Post-time repeat gate (the second half of the enqueue text guard) ────
    # The enqueue-time guard stops identical copy ENTERING the queue, but an
    # item enqueued before that guard shipped sits approved under a fresh id
    # and fires a night later (the 2026-07-26/27 byte-identical "My read on
    # today's move" pair). Text that already went out this window never goes
    # out again — checked here, at the last gate before the network.
    # UPGRADED 2026-07-27 to NEAR-dup: a lightly-reworded repeat (token Jaccard
    # ≥ 0.7 vs a same-account posted text) is quarantined too — "deeply reworded"
    # is the bar. Strictly per-account (cross-account near-dup is sentinel's
    # plan-time job). This gate applies to immediate/breaking items as well —
    # dedup is a safety gate the operator explicitly kept.
    _ref_day = now.strftime("%Y-%m-%d")
    posted_text_keys = _outbox.recent_posted_text_keys(state, _ref_day)
    posted_texts_by_account = _outbox.recent_posted_texts(state, _ref_day)

    # ── Post-time frame / filler / substance gates (ported from #3928) ───────
    # THE DEFECT CLASS. On 2026-07-28 the founder desk shipped "$TEL close to
    # going", "$CBOE close to going" and "$FDS close to going" in one day, two of
    # them sharing a byte-identical tail. Every dedup gate above compares raw
    # TOKENS, the tickers and prices differ, so three renders of one template
    # score 0.3-0.4 and all three went out. Blanking tickers and numbers leaves
    # the frame, and a repeated frame on one account in one day is the templated-
    # content fingerprint accounts get purged for.
    #
    # SAME-DAY, PER-ACCOUNT, LANE-BLIND. The nightly plan, the wire lanes, the
    # press bridge, publish-time movers and an operator "post now" all land in one
    # desk's day and never share a plan, so the copywriter's plan-side batch-stem
    # validators cannot see the pair. This loop is the only place that can.
    #
    # Fully fail-soft: a broken sentinel must never wedge the queue, so any
    # failure here leaves the pre-port behaviour intact.
    _sentinel_gates = None
    _frames_by_account: dict[str, list[tuple[str, frozenset]]] = {}
    _filler_today: dict[str, int] = {}
    _frame_threshold = 0.0
    _max_filler: int | None = None
    _substance_armed = False
    try:
        from engine.marketing import sentinel as _sentinel_gates  # noqa: PLC0415
        _frame_threshold = _sentinel_gates.frame_similarity_threshold(cfg)
        _max_filler = _sentinel_gates.max_filler_per_account_per_day(cfg)
        _substance_armed = _sentinel_gates.require_ticker_and_number(cfg)
        for _acct, _rows in _outbox.posted_today_rows_by_account(state, today).items():
            _frames_by_account[_acct] = [
                (_rid, _sentinel_gates.skeleton_tokens(_rtext))
                for _rid, _rtext, _rkind in _rows]
            _filler_today[_acct] = sum(
                1 for _rid, _rtext, _rkind in _rows
                if _sentinel_gates.is_filler_kind(_rkind))
        log.info("post-time gates | frame>=%.2f filler<=%s substance_floor=%s",
                 _frame_threshold,
                 "unlimited" if _max_filler is None else _max_filler,
                 "ARMED" if _substance_armed else "shadow")
    except Exception as _pg_exc:  # noqa: BLE001
        log.warning("post-time frame/filler gates unavailable (%s) — the near-dup "
                    "and cap gates still run", _pg_exc)
        _sentinel_gates = None
    quarantined_frame = 0
    skipped_filler = 0
    quarantined_substance = 0
    shadow_substance = 0

    # ── Cross-account near-dup bar (XG-W2) ───────────────────────────────────
    # The gate above is strictly per-account. With seven live accounts the
    # failure that matters is TWO of ours posting near-identical text — the
    # text-similarity clustering signal, not a style problem. Sentinel applies
    # this bar across accounts inside ONE nightly plan; here it covers the queue,
    # which spans nights and carries the fast lanes that never enter a plan.
    # Threshold from sentinel.near_dup_jaccard (stricter than the same-account
    # 0.7 on purpose — see outbox.cross_account_threshold).
    _xa_threshold = _outbox.cross_account_threshold(cfg)

    # ── Per-account cadence resolver (XG-W2) ─────────────────────────────────
    # config/marketing.yml keeps sentinel.max_posts_per_account_per_day: -1 as
    # the GLOBAL backstop the operator chose on 2026-07-24. The per-account law
    # is now each persona spec's own cadence block, read by
    # engine/marketing/cadence_resolver.py. The two compose: an item posts only
    # when BOTH allow it. Fail-soft — a broken resolver must never wedge the
    # queue, so any failure here leaves the pre-XG-W2 behaviour intact.
    _cadence = None
    _cadence_profiles: dict = {}
    _cadence_history: dict = {}
    _cadence_exempt_immediate = True
    try:
        from engine.marketing import cadence_resolver as _cadence  # noqa: PLC0415
        # Specs come from the SAME root the run's marketing.yml came from — a
        # run's cadence law and its posting config must not come from two trees.
        # A root with no persona-spec directory yields no profiles and the
        # resolver abstains, which is the honest behaviour for a checkout that
        # carries none. (This module never reads a spec itself; the resolver is
        # the one adjudicated reader — see the fence in test_marketing_personas.)
        _cadence_profiles = _cadence.load_profiles(root=root)
        _cadence_history = _cadence.posting_history(state)
        _cadence_knobs = _cadence.resolver_config(cfg)
        _cadence_exempt_immediate = bool(
            (cfg.get("cadence_resolver") or {}).get("exempt_immediate", True))
        log.info("cadence resolver | enabled=%s profiles=%d exempt_immediate=%s",
                 _cadence_knobs["enabled"], len(_cadence_profiles),
                 _cadence_exempt_immediate)
    except Exception as _cr_exc:  # noqa: BLE001
        log.warning("cadence resolver unavailable (%s) — sentinel cap only", _cr_exc)
        _cadence = None
    skipped_cadence = 0
    shadow_cadence = 0
    deferred_xa = 0

    # ── Hot-tape orphan-brief gate context (fail-soft) ───────────────────────
    # The publisher half of the two-step recall cascade (#3983 closed the radar
    # half). A context brief rides only while the alert it explains is still
    # "posted", and the radar re-checks that at its own dispatch — but that
    # sweep runs only when the radar runs. An operator recall after the last
    # radar pass of the day (end of ET window, weekend, workflow disabled)
    # leaves the booked brief on its scheduled_at, and THIS sweep would send
    # it. Re-checked here, at the last gate before the network, against the
    # outbox ledger itself. Fail-soft in the publisher's usual shape: if this
    # context cannot be built the gate stands down and the send path is
    # unchanged — a broken check must never wedge the queue, and "unresolved"
    # must mean "the ledger answered: no such alert", never "the check broke".
    # This module is in the Hot Tape program's READ-ONLY safety stack (gate
    # 0.5, class TestSafetyStack in the radar's suite), so the reach is ONE
    # sanctioned symbol, recorded by name in that test's allowance. It earns
    # the allowance the same way the copywriter's does: the gate can only
    # REFUSE a brief, and there is no argument to it that lets a post through
    # that would otherwise be refused.
    _ht_orphan_status = None
    _ht_lane = ""
    _ht_alert_ids: dict[str, str] = {}
    try:
        from engine.marketing.hot_tape import LANE, BRIEF_TRIGGER, orphaned_brief_status  # noqa: PLC0415
        _ht_lane = LANE
        for _hid, _hit in (state.get("items") or {}).items():
            _hsrc = _hit.get("source")
            if not isinstance(_hsrc, dict) or _hsrc.get("lane") != _ht_lane:
                continue
            if str(_hsrc.get("trigger") or "") == BRIEF_TRIGGER:
                continue
            _hk = str(_hsrc.get("story_key") or "")
            # Prefer a posted duplicate: the question is "is the post this
            # brief explains live", so any posted holder of the key answers it.
            if _hk and (_hk not in _ht_alert_ids
                        or statuses.get(_ht_alert_ids[_hk]) != "posted"):
                _ht_alert_ids[_hk] = str(_hid)
        _ht_orphan_status = orphaned_brief_status
    except Exception as _ht_exc:  # noqa: BLE001
        log.warning("hot-tape orphan gate unavailable (%s) — briefs post "
                    "ungated this run", _ht_exc)
        _ht_orphan_status = None

    for it in approved_due:
        iid = it["id"]
        account = it.get("account", "")
        text = it.get("text", "") or ""

        # -- halt gate: BEFORE validation, the cap, and the channel lookup ----
        # A halted desk must cost nothing and touch nothing, so this is the
        # first thing the loop asks. It is deliberately not a quarantine: the
        # item is fine, the desk is halted, and quarantining would bury a good
        # post under a reason that has nothing to do with it.
        if _health is not None and _health.is_halted(account, halts=_halts):
            log.warning("item %s (%s) SKIPPED — account HALTED (%s)", iid, account,
                        (_halts.get(account) or {}).get("reason"))
            skipped_halt += 1
            continue

        # -- dark-desk park: directly behind the halt, ahead of validation ----
        # The auto-approve pass parks queued items, but an item can be APPROVED
        # already — an operator approval, or a run from before the desk went dark
        # — and this is the last gate that sees it. Quarantine, not skip: unlike
        # a halt, an unarmed desk is not a state that lifts on its own, and
        # leaving perishable copy approved would fire it stale on arming day.
        if _dark and account in _dark:
            log.warning("item %s (%s) QUARANTINED — account dark (desk_network "
                        "disabled)", iid, account)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher",
                                   root=root, note=_DARK_PARK_NOTE)
                # Dry-run parks nothing, so it announces nothing (and does not
                # spend the next live run's annotation budget).
                _warn_dark_park(account)
            _parked_post.append(iid)
            continue

        # -- hot-tape orphan gate: a brief never outlives its alert -----------
        # The second half of a two-step publish must not ship if the first
        # half is gone: a context brief whose parent alert is recalled,
        # quarantined, or absent from this ledger would explain a post nobody
        # can see. Same predicate as the radar's dispatch re-check
        # (orphaned_brief_status), stricter policy on "unresolved": here the
        # map comes from the outbox ledger itself, so a parent it cannot name
        # is positive evidence, not a fold hiccup (see the predicate's
        # docstring). Runs for post_now/immediate items too — an operator
        # click buys timing, never a waiver on a safety gate (#3983).
        if _ht_orphan_status is not None:
            try:
                _bsrc = it.get("source")
                _orphan = None
                if isinstance(_bsrc, dict) and _bsrc.get("lane") == _ht_lane:
                    _orphan = _ht_orphan_status(
                        _bsrc.get("story_key"), _bsrc.get("trigger"),
                        _ht_alert_ids, statuses)
                if _orphan is not None:
                    reason = f"orphaned context brief: alert is {_orphan}"
                    print(f"::warning title=hot-tape-orphan-brief::context brief "
                          f"{iid} is not published: the alert it explains is "
                          f"{_orphan}, not posted - a brief is the second half "
                          "of a two-step publish and never ships alone",
                          flush=True)
                    log.warning("item %s (%s) QUARANTINED as an orphaned context "
                                "brief (alert is %s)", iid, account, _orphan)
                    if live:
                        _outbox.transition(iid, "quarantined", actor="publisher",
                                           root=root, note=reason)
                    quarantined += 1
                    continue
            except Exception as _ob_exc:  # noqa: BLE001
                log.warning("hot-tape orphan gate failed for %s (%s) — item "
                            "proceeds", iid, _ob_exc)

        links_allowed = _links_allowed_for(pub_cfg, account)
        # Items carry no separate link field today; the link (if any) is inline
        # in the post text. Pass link=None so validate_postable checks the body
        # length and the account's link policy is still available for the future.
        link = it.get("link")

        # Breaking/immediate items (a fastlane earnings post, an operator "post
        # now" click, a publish-time mover) have NO volume limits (operator
        # 2026-07-27): they are exempt from the daily cap and the global floor and
        # post at ``now``. Every SAFETY gate below (validate, repeat/near-dup,
        # tape gate, channel, kill-switch) still runs. Computed up front so the
        # cap gate can see it.
        is_immediate = _is_immediate(it.get("scheduled_at")) or iid in post_now

        # -- validate → quarantine on failure --------------------------------
        problems = validate_postable(text, link, links_allowed)
        if problems:
            reason = "unpostable: " + ", ".join(problems)
            log.warning("item %s (%s) failed validation: %s", iid, account, problems)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            quarantined += 1
            continue

        # -- repeat gate: identical copy never posts twice in the window -----
        if _outbox.text_key(account, text) in posted_text_keys:
            reason = (f"repeat: identical to a post from the last "
                      f"{_outbox._TEXT_DEDUP_WINDOW_DAYS} days")
            log.warning("item %s (%s) QUARANTINED as a repeat", iid, account)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            quarantined += 1
            continue

        # -- near-dup gate: a lightly-reworded repeat also never posts --------
        # Per-account token Jaccard ≥ 0.7 vs any same-account posted text in the
        # window → quarantine; "deeply reworded" (< 0.7) passes.
        _near_hit = None
        for _pid, _ptext, _pas_of in posted_texts_by_account.get(account, ()):
            _score = _outbox.token_jaccard(text, _ptext)
            if _score >= _outbox._NEAR_DUP_JACCARD:
                _near_hit = (_pid, _pas_of, _score)
                break
        if _near_hit is not None:
            _pid, _pas_of, _score = _near_hit
            reason = (f"repeat: near-identical (jaccard={_score:.2f}) to {_pid} "
                      f"posted {_pas_of or 'recently'}; deep rewording required")
            log.warning("item %s (%s) QUARANTINED as a near-duplicate of %s "
                        "(jaccard=%.2f)", iid, account, _pid, _score)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            quarantined += 1
            continue

        # -- cross-account near-dup radar: two of OUR accounts never post ----
        # near-identical text. Same Jaccard machinery, wider corpus, stricter
        # bar. This is the fleet-linkage defense, not a style rule, so it binds
        # on breaking items too — a coordinated-looking pair is worse when it is
        # fast.
        _xa_hit = None
        for _other_acct, _rows in posted_texts_by_account.items():
            if _other_acct == account:
                continue
            for _pid, _ptext, _pas_of in _rows:
                _score = _outbox.token_jaccard(text, _ptext)
                if _score >= _xa_threshold:
                    _xa_hit = (_other_acct, _pid, _pas_of, _score)
                    break
            if _xa_hit is not None:
                break
        if _xa_hit is not None:
            _oacct, _pid, _pas_of, _score = _xa_hit
            # DEFER, DO NOT QUARANTINE. Quarantine is TERMINAL, and the item
            # that loses this race is decided by hash-ordered iteration — an
            # arbitrary one of the two desks would be permanently killed for a
            # collision that is a property of the PAIR, not a defect in either
            # post. The same-account gates above quarantine correctly (a repeat
            # of your own copy is defective on its own terms); this one is a
            # scheduling conflict, so the item stays `approved` and retries on a
            # later sweep, by which time the counterpart has aged out of the
            # window or an editor has reworded it. The counterpart id is logged
            # so the deferral is diagnosable rather than mysterious.
            log.warning(
                "item %s (%s) DEFERRED — cross-account near-duplicate of %s (%s, "
                "jaccard=%.2f, posted %s); stays approved and retries next sweep",
                iid, account, _pid, _oacct, _score, _pas_of or "recently")
            deferred_xa += 1
            continue

        # -- template-frame gate: one template wearing two tickers ------------
        # The defect the two near-dup gates above structurally cannot see (they
        # compare raw tokens; the tickers and prices differ). BINDS IMMEDIATES,
        # matching every similarity gate above it — a coordinated-looking set of
        # renders is worse when it is fast — and it QUARANTINES rather than
        # defers, because unlike the cross-account collision this is a defect in
        # the item on its own terms: your desk already published this frame today.
        if _sentinel_gates is not None:
            _frame_hit = _sentinel_gates.frame_repeat_of(
                _sentinel_gates.skeleton_tokens(text),
                _frames_by_account.get(account, ()),
                threshold=_frame_threshold)
            if _frame_hit is not None:
                _fid, _fscore = _frame_hit
                reason = (f"frame repeat (skeleton jaccard={_fscore:.2f}) of {_fid} "
                          f"posted today; same template, different ticker")
                log.warning("item %s (%s) QUARANTINED as a template-frame repeat "
                            "of %s (skeleton jaccard=%.2f)", iid, account, _fid, _fscore)
                if live:
                    _outbox.transition(iid, "quarantined", actor="publisher",
                                       root=root, note=reason)
                quarantined += 1
                quarantined_frame += 1
                continue

        # -- language gate: the queue is not a bypass around the copy bar ----
        # Generation-time validators cannot reach copy already sitting in the
        # queue: the 2026-07-27 $AVGO "POC held" post was enqueued by an older
        # weekend_levels before the study-name bans existed and fired days
        # later. Same bar, last gate — text validate_copy would reject for
        # its LANGUAGE never posts, whatever lane or vintage queued it.
        lang = _banned_language(text)
        if lang:
            reason = "reads too technical / banned language: " + ", ".join(lang[:4])
            log.warning("item %s (%s) QUARANTINED by language gate: %s",
                        iid, account, reason)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            quarantined += 1
            continue

        # -- headline-shape gate: fragment headlines are vintage-proof too ---
        # validate_copy 4f (#3907) rejects fragment headlines ("Circling",
        # "is close", "Radar check on") at GENERATION time, but the queue is
        # a bypass around any generation-time law — the same $AVGO lesson the
        # language gate above exists for. Screen the queued headline here so
        # a queue-vintage fragment never posts. Fires only when the headline
        # is UNAMBIGUOUS (see _queued_headline): quarantine is terminal, so
        # ambiguity means skip, never guess.
        _qh = _queued_headline(it.get("kind"), text)
        if _qh is not None:
            _frags = _headline_fragments(_qh)
            if _frags:
                reason = "fragment headline (queue vintage): " + "; ".join(_frags[:2])
                log.warning("item %s (%s) QUARANTINED by headline-shape gate: %s",
                            iid, account, reason)
                if live:
                    _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
                quarantined += 1
                continue

        # -- substance floor: name a cashtag, state a quantity ----------------
        # THE BAR (operator 2026-07-28): "a post must name a ticker, state a dated
        # fact with its numbers, and then say something that FOLLOWS from that
        # fact." Clauses one and two, at the last gate, over every lane and
        # vintage — the same reasoning as the language gate above.
        #
        # LANDS DARK. Arming it drops macro/event/education and the ticker-free
        # watchlist slot outright: none of them can name a cashtag. That is a
        # product ruling about whether those lanes exist, not a bug fix, so the
        # verdict is computed in full every sweep and only COUNTED until
        # sentinel.require_ticker_and_number flips true (the shape
        # cadence_resolver.enabled uses). Replies are exempt — a reply is a
        # conversation, and a ticker requirement there is a category error.
        if _sentinel_gates is not None and not _sentinel_gates.is_reply_item(it):
            _gap = _sentinel_gates.substance_gap(text, ticker=_item_ticker(it))
            if _gap is not None and _substance_armed:
                reason = f"no substance: post states no {_gap}"
                log.warning("item %s (%s) QUARANTINED by the substance floor: "
                            "no %s", iid, account, _gap)
                if live:
                    _outbox.transition(iid, "quarantined", actor="publisher",
                                       root=root, note=reason)
                quarantined += 1
                quarantined_substance += 1
                continue
            if _gap is not None:
                log.info("item %s (%s, %s) substance floor SHADOW — would refuse: "
                         "no %s", iid, account, it.get("kind"), _gap)
                shadow_substance += 1

        # -- live tape gate: never post yesterday's read against today's tape --
        if _live_verify is not None:
            verdict = _live_verify.verify_item(
                it, live=_tape, earnings=_earn_set, now=now, cfg=cfg)
        else:
            # Gate module broken: hold signals (fail closed), pass the rest.
            verdict = ({"action": "skip", "reasons": ["live gate unavailable"]}
                       if it.get("kind") == "signal"
                       else {"action": "post", "reasons": []})
        if verdict["action"] == "quarantine":
            reason = "tape gate: " + "; ".join(verdict["reasons"])
            log.warning("item %s (%s) QUARANTINED by tape gate: %s", iid, account, reason)
            if live:
                _outbox.transition(iid, "quarantined", actor="publisher", root=root, note=reason)
            tape_quarantined += 1
            continue
        if verdict["action"] == "skip":
            log.info("item %s (%s) held by tape gate: %s", iid, account,
                     "; ".join(verdict["reasons"]))
            tape_skipped += 1
            continue

        # -- per-account daily cap (immediate/breaking is EXEMPT) ------------
        _acct_cap = _cap_for(account)
        if not is_immediate and _at_cap(posted_today.get(account, 0), _acct_cap):
            log.info("item %s (%s) skipped — account at daily cap (%d/day, "
                     "ramp-narrowed from base %d)", iid, account, _acct_cap, cap)
            skipped_cap += 1
            continue

        # -- filler cap: the no-ticker kinds are seasoning, not a meal --------
        # Kelly's ENTIRE 2026-07-28 output was four macro/education posts, each a
        # different way to say "I post my results", so after the operator's review
        # she shipped nothing. One a day per desk.
        #
        # A VOLUME cap, so IMMEDIATE/breaking is exempt — the same standing ruling
        # ("breaking has no limits", operator 2026-07-27) that exempts them from
        # the daily cap above and the cadence resolver below. A breaking `event`
        # post is the exact case that ruling protects. It SKIPS rather than
        # quarantines: the item is fine, the day is full, and it can post tomorrow.
        #
        # content_studio.apply_reuse_budget trims the emitted plan to this same key
        # (one reader, two seams), so this fires on what the plan could not see:
        # queue vintage, the wire lanes, the press bridge, operator injections.
        if (_sentinel_gates is not None and not is_immediate
                and _max_filler is not None
                and _sentinel_gates.is_filler_kind(it.get("kind"))
                and _filler_today.get(account, 0) >= _max_filler):
            log.info("item %s (%s, %s) skipped — account at its daily filler cap "
                     "(%d/day of macro/event/education)", iid, account,
                     it.get("kind"), _max_filler)
            skipped_filler += 1
            continue

        # -- per-account cadence resolver (XG-W2) ----------------------------
        # The persona spec's own posts_per_day / min_spacing_min / session
        # window, read from its persona spec by the resolver (this module never
        # touches the spec layer itself). The sentinel -1 above is the
        # global backstop; THIS is the per-account law. An account with no spec
        # abstains (reason no_profile) and is governed exactly as before.
        #
        # IMMEDIATE items are exempt by default, honouring the standing operator
        # ruling of 2026-07-27 ("breaking has no limits") that already exempts
        # them from the daily cap and the global floor. It is a config key
        # (cadence_resolver.exempt_immediate), not a buried constant, because a
        # wire-cadence property may well want its breaking flow bounded too.
        #
        # TODO(xg-w2-review): immediate items bypass the resolver but their
        # posted receipts still count in posting_history — a breaking storm
        # silently exhausts the ladder's daily budget for the rest of the local
        # day with no log naming the cause; split the history count or log the
        # attribution when this first bites.
        if _cadence is not None and not (is_immediate and _cadence_exempt_immediate):
            try:
                _decision = _cadence.resolve(
                    account, str(it.get("kind") or ""),
                    now=now,
                    profile=_cadence_profiles.get(account),
                    history=_cadence_history.get(account, []),
                    cfg=cfg,
                    seed=iid,
                )
            except Exception as _cd_exc:  # noqa: BLE001
                log.warning("cadence resolve failed for %s (%s) — allowing",
                            iid, _cd_exc)
                _decision = None
            if _decision is not None and not _decision.allow:
                log.info("item %s (%s) held by the cadence resolver: %s | %s",
                         iid, account, _decision.reason, _decision.detail)
                skipped_cadence += 1
                continue
            # SHADOW MODE (cadence_resolver.enabled: false — the land-dark
            # default). The verdict was computed in full and is NOT binding;
            # log what arming WOULD have refused, because reading one cycle of
            # this is the precondition for the arming decision. Counted
            # separately so a shadow run's summary never reads as enforcement.
            if _decision is not None and _decision.detail.get("would_refuse"):
                log.info("item %s (%s) cadence SHADOW — would refuse: %s | %s",
                         iid, account, _decision.detail["would_refuse"],
                         _decision.detail)
                shadow_cadence += 1

        # -- channel id must exist -------------------------------------------
        channel_id = _channel_id_for(pub_cfg, account)
        if not channel_id:
            log.warning("item %s (%s) has no configured channel id in "
                        "publish.channels.%s — cannot post", iid, account, account)
            skipped_channel += 1
            # Approved items on a channel-less account otherwise rot 'approved'
            # forever (re-skipped every run, never expiring). After 3 days,
            # quarantine so the queue drains honestly. Only in --live (dry-run
            # never mutates the ledger).
            if live and _item_age_days(it, now) > 3:
                _outbox.transition(iid, "quarantined", actor="publisher",
                                   root=root, note="expired_no_channel")
            continue

        # -- a ticker post must carry its chart -------------------------------
        # Public chart-image URLs (PNG on X) from the plan-build stamp or, when
        # that R2 upload failed, the backfill sidecar. Resolved HERE — ahead of
        # the floor gate — so an item held for a missing chart never consumes
        # the spacing window or a forward-book slot, the same reason the tape,
        # cap and channel gates run first.
        media_paths = _media_paths_for(it, pub_cfg, _media_sidecar)
        # `post_now` BUYS A SLOT, NOT A WAIVER (#3960 minor). This used to read
        # `iid not in post_now and _missing_required_media(...)`, on the reasoning
        # that an operator click is explicit intent that outranks the hold. It is
        # explicit intent about the TIMING; it is not consent to break the
        # standing chart law (#3921, "every ticker post carries a chart"), and a
        # bare ticker post is exactly what that law forbids. The operator clicking
        # "post now" cannot see that the chart's R2 URL never resolved, so the
        # waiver silently converted a charted entry-timing read into a naked call
        # — the one failure mode the gate exists for. A deferred item is not
        # refused, it retries the moment the media backfill lands.
        if _missing_required_media(it, pub_cfg, media_paths):
            _charts = _chart_ids_for(it)
            _age_days = _item_age_days(it, now)
            if _age_days > _MEDIA_DEFER_MAX_AGE_DAYS:
                # Bounded escape: the chart is not coming. Quarantine rather
                # than post bare — see _MEDIA_DEFER_MAX_AGE_DAYS. Annotation is
                # a BARE print (a logger prefix would make GitHub drop it).
                print(f"::warning title=marketing-chart-missing::item {iid} "
                      f"({account}/{it.get('kind')}, ${_item_ticker(it)}) "
                      f"quarantined after {_age_days}d — chart {_charts} never "
                      f"got a public URL; run scripts/marketing_media_backfill.py",
                      flush=True)
                log.warning("item %s (%s, %s) quarantined — chart %s still has no "
                            "public URL after %dd", iid, account, it.get("kind"),
                            _charts, _age_days)
                if live:
                    _outbox.transition(iid, "quarantined", actor="publisher",
                                       root=root, note="expired_no_media")
                quarantined += 1
            else:
                log.info("item %s (%s, %s) deferred — chart %s has no public URL "
                         "yet (age %dd); stays approved and retries once the "
                         "media backfill lands", iid, account, it.get("kind"),
                         _charts, _age_days)
                deferred_no_media += 1
            continue

        # -- global min-spacing floor: at most one post per window (any acct) --
        # Checked AFTER the tape/cap/channel gates so a held item never consumes
        # the window. A blocked LADDER item stays approved and retries the next
        # slot. A BREAKING/immediate item is floor-EXEMPT (operator 2026-07-27):
        # it posts at NOW unconditionally — never floor-booked, never deferred,
        # never dropped. It STILL advances the in-memory floor so the next ladder
        # post budges by the spacing (and a burst of immediates all fire at now).
        # The earliest wall-clock this item may go out without breaking the
        # floor. `now` once the floor is clear; otherwise the moment it clears.
        floor_clear_at = now
        if not is_immediate and _within_floor(last_post_at, now, floor_min):
            floor_clear_at = last_post_at + timedelta(minutes=floor_min)
            _ahead = int((floor_clear_at - now).total_seconds() // 60)
            # Forward-booking (publish.max_forward_book_min) hands the item to
            # Buffer scheduled at floor_clear_at instead of dropping it back in
            # the queue for the next sweep. Same spacing, same send time — the
            # slot is just reserved now. Bounded by the horizon so a booked read
            # is never verified against a tape much older than it claims.
            if forward_horizon_min <= 0 or _ahead > forward_horizon_min:
                _ago = int((now - last_post_at).total_seconds() // 60)
                log.info("item %s (%s) deferred — a post went out %dm ago (< %dm "
                         "global floor); retries next slot", iid, account, _ago, floor_min)
                skipped_floor += 1
                continue
            log.info("item %s (%s) forward-booked +%dm (global floor %dm, horizon %dm)",
                     iid, account, _ahead, floor_min, forward_horizon_min)
            forward_booked += 1

        # The wall-clock this post is booked for. An immediate item books at NOW.
        # A ladder item books at floor_clear_at + its deterministic jitter offset;
        # with the floor clear and jitter off (0) that is NOW, and
        # send_scheduled_at stays the item's own ladder slot exactly as before.
        # Also the value the in-memory floor advances to after a post — the floor
        # must count from the time a post actually goes out, not from the sweep
        # that queued it.
        jitter_minutes = 0 if is_immediate else _post_jitter_minutes(iid, jitter_max)
        booked_at = floor_clear_at + timedelta(minutes=jitter_minutes)
        if is_immediate or jitter_max > 0 or booked_at > now:
            send_scheduled_at = booked_at.strftime(_TS_FMT)
        else:
            send_scheduled_at = it.get("scheduled_at")
        floor_advance = booked_at

        # -- DRY-RUN: print, never touch the network or the ledger -----------
        if not live:
            log.info(
                "WOULD POST | account=%s channel=%s chars=%d media=%d sched=%s "
                "send_at=%s%s\n    %s",
                account, channel_id, len(text), len(media_paths),
                it.get("scheduled_at"), send_scheduled_at,
                " (immediate)" if is_immediate else "",
                text.replace("\n", " ")[:200],
            )
            would_post += 1
            last_post_at = floor_advance   # mirror live pacing in the projection
            # Mirror the cadence resolver's accounting too, so a dry-run
            # projection shows the same per-account bound the live run enforces
            # (otherwise a whole day's backlog "would post" in one sweep).
            _cadence_history.setdefault(account, []).append(
                (floor_advance, str(it.get("kind") or "")))
            continue

        # -- LIVE: approved → posting BEFORE the network call ----------------
        if not _outbox.transition(iid, "posting", actor="publisher", root=root,
                                  note="in-flight (pre-publish)"):
            log.error("item %s: could not mark posting — skipping (not posting)", iid)
            continue

        receipt = publisher.publish(
            text=text,
            channel_id=channel_id,
            media_paths=media_paths or None,
            link=link,
            scheduled_at=send_scheduled_at,
            now=now,
            # SHARE-NOW: never let a breaking item fall through to Buffer's own
            # queue (addToQueue) — it must be customScheduled at a concrete time.
            immediate=is_immediate,
        )

        if receipt.ok:
            _outbox.transition(
                iid, "posted", actor="publisher", root=root,
                note="published",
                receipt={
                    "backend": receipt.backend,
                    "external_id": receipt.external_id,
                    "external_url": receipt.external_url,
                    "at": receipt.at,
                    # The wall-clock this post was BOOKED for (== `at` when
                    # jitter is off). _last_global_post_at seeds the next cron
                    # run's spacing floor from this, so a jittered post can never
                    # be followed inside its own floor window.
                    "booked_at": floor_advance.strftime(_TS_FMT),
                },
            )
            # ALSO record a publication receipt so the Channels page (reads
            # publications.jsonl via engine.marketing.state) surfaces the post —
            # the outbox status ledger alone never reached that reader.
            _append_publication(
                root,
                _publication_row(
                    it, text, receipt,
                    published_at=(receipt.at or now.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ),
            )
            posted_today[account] = posted_today.get(account, 0) + 1
            # Feed the cadence resolver so ONE run cannot burst past an
            # account's posts_per_day / min_spacing (the folded state was read
            # before the loop and does not see posts made inside it).
            _cadence_history.setdefault(account, []).append(
                (floor_advance, str(it.get("kind") or "")))
            posted += 1
            # Feed the repeat gate so two identical items due in ONE run can't
            # both go out (the enqueue guard should prevent that pair existing,
            # but the last gate assumes nothing upstream).
            posted_text_keys.add(_outbox.text_key(account, text))
            # Same reason for the ported gates: the folded state was read before
            # the loop, so without these two lines the frame gate and the filler
            # cap would both be blind to what THIS run already sent — and one run
            # is exactly how the three "$X close to going" renders shipped.
            if _sentinel_gates is not None:
                _frames_by_account.setdefault(account, []).append(
                    (iid, _sentinel_gates.skeleton_tokens(text)))
                if _sentinel_gates.is_filler_kind(it.get("kind")):
                    _filler_today[account] = _filler_today.get(account, 0) + 1
            # Advance the global floor to the time this post was BOOKED for —
            # NOW for an immediate item, NOW + jitter for a ladder item — so the
            # next post budges from when this one actually goes out.
            last_post_at = floor_advance
            # PERSONA MEMORY (XG-W3). Record the emitted text so the codex
            # frequency caps (max_per_day / max_per_7d / max_share_7d) can see
            # it TOMORROW. Without this call the caps evaluate against an empty
            # `recent` and `expression_dial.frequency_violations` returns [] —
            # i.e. a signature opener capped at "≤1/day and ≤30% over 7 days"
            # would be enforced only within a single nightly batch, and an
            # account could open with the same line every day forever.
            #
            # THIS IS THE ONLY PLACE A POST IS KNOWN TO HAVE ACTUALLY SHIPPED.
            # Recording at enqueue would charge the budget for items that are
            # never approved or that expire in the queue.
            #
            # Host-spool write (gitignored); the nightly consolidator is the
            # sole advancer of the tracked ledger. Fail-soft: a memory write
            # must never turn a SUCCESSFUL post into an error path.
            _record_persona_post(root, it, account, text, now)
            log.info("item %s POSTED via %s id=%s%s", iid, receipt.backend,
                     receipt.external_id,
                     (f" (scheduled {send_scheduled_at})" if booked_at > now else ""))
        else:
            _outbox.transition(iid, "failed", actor="publisher", root=root,
                               note=receipt.error or "publish failed",
                               receipt={"backend": receipt.backend, "error": receipt.error,
                                        "at": receipt.at})
            failed += 1
            log.warning("item %s FAILED: %s", iid, receipt.error)

    # ── Summary + activity row ──────────────────────────────────────────────
    # A held post is invisible unless we say so. marketing-media-backfill is a
    # workflow_dispatch lane — nothing schedules it — so the recovery this hold
    # waits on only happens if a human starts it. Warn on the FIRST sweep that
    # holds anything, not at quarantine time three days later.
    if deferred_no_media:
        print(f"::warning title=marketing-charts-missing::{deferred_no_media} ticker "
              f"post(s) held: chart built but no public URL. Recover with the "
              f"marketing-media-backfill workflow (gh workflow run "
              f"marketing-media-backfill.yml) — held items quarantine after "
              f"{_MEDIA_DEFER_MAX_AGE_DAYS}d.", flush=True)

    # Both gates park, so both count. The auto-approve pass takes the queued
    # items (a breaking dispatch's usual shape) and the post loop takes the
    # already-approved ones; reporting only the second read parked_dark=0 on the
    # very scenario this gate was built for.
    parked_dark = len(_parked_auto) + len(_parked_post)

    if skipped_halt:
        # Bare print at line start — a logger prefixes the annotation and GitHub
        # silently drops it (house law).
        print(
            f"::warning title=publisher-account-halted::{skipped_halt} post(s) held "
            f"back — account(s) {sorted(_halts)} are HALTED (health monitor / network "
            "tripwire). Every other desk posted normally. Clear the halt in the admin "
            "health panel once the cause is understood.",
            flush=True,
        )
    # The filler cap firing means the plan side did NOT trim what it should have
    # (content_studio.apply_reuse_budget reads the same key), or a lane the plan
    # never saw filled the day. Either way it is a fact about the pipeline, not a
    # routine skip, so it is loud. Bare print at line start — a logger prefixes
    # the annotation and GitHub silently drops it (house law).
    if skipped_filler:
        print(
            f"::warning title=publisher-filler-cap::{skipped_filler} no-ticker post(s) "
            f"(macro/event/education) held — desk already at its daily filler cap. "
            f"content_studio.apply_reuse_budget trims the nightly plan to the same "
            f"sentinel.max_filler_per_account_per_day, so a hit here means a lane "
            f"outside the plan filled the day, or the plan-side trim did not run.",
            flush=True,
        )
    if quarantined_frame:
        print(
            f"::warning title=publisher-frame-repeat::{quarantined_frame} post(s) "
            f"quarantined as template-frame repeats — one desk published the same "
            f"skeleton (tickers and numbers blanked) twice in one day at jaccard "
            f">= {_frame_threshold:.2f}. Check the producing lane's copy variety.",
            flush=True,
        )
    if shadow_substance:
        print(
            f"::notice title=publisher-substance-shadow::{shadow_substance} post(s) "
            f"state no cashtag or no number. The substance floor is DARK "
            f"(sentinel.require_ticker_and_number: false) so all of them posted; "
            f"arming it would have dropped every one.",
            flush=True,
        )
    log.info(
        "%s complete | posted=%d failed=%d quarantined=%d would_post=%d "
        "tape_quarantined=%d tape_skipped=%d skipped_floor=%d "
        "forward_booked=%d deferred_immediate=%d deferred_no_media=%d "
        "skipped_cap=%d skipped_cadence=%d cadence_shadow=%d deferred_xa=%d "
        "quarantined_frame=%d skipped_filler=%d quarantined_substance=%d "
        "substance_shadow=%d "
        "skipped_no_channel=%d skipped_halt=%d parked_dark=%d "
        "stuck_posting=%d auto_approved=%d",
        mode, posted, failed, quarantined, would_post,
        tape_quarantined, tape_skipped, skipped_floor,
        forward_booked, deferred_immediate, deferred_no_media,
        skipped_cap, skipped_cadence, shadow_cadence, deferred_xa,
        quarantined_frame, skipped_filler, quarantined_substance, shadow_substance,
        skipped_channel,
        skipped_halt, parked_dark,
        len(stuck_posting),
        len(auto_approved),
    )
    try:
        _outbox._append_activity(root, {
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lane": "publisher_live" if live else "publisher_dry_run",
            "backend": backend,
            "cap": cap,
            "posted": posted,
            "failed": failed,
            "quarantined": quarantined,
            "would_post": would_post,
            "tape_quarantined": tape_quarantined,
            "tape_skipped": tape_skipped,
            "skipped_floor": skipped_floor,
            "forward_booked": forward_booked,
            "deferred_immediate": deferred_immediate,
            "deferred_no_media": deferred_no_media,
            "skipped_cap": skipped_cap,
            "skipped_cadence": skipped_cadence,
            "cadence_shadow": shadow_cadence,
            "deferred_cross_account": deferred_xa,
            "quarantined_frame": quarantined_frame,
            "skipped_filler": skipped_filler,
            "quarantined_substance": quarantined_substance,
            "substance_shadow": shadow_substance,
            "skipped_no_channel": skipped_channel,
            "skipped_halt": skipped_halt,
            "halted_accounts": sorted(_halts),
            "parked_dark": parked_dark,
            "dark_accounts": (None if _dark is None else sorted(_dark)),
            "stuck_posting": len(stuck_posting),
            "auto_approved": len(auto_approved),
            "pt_generated": pt_generated,
            "pt_dropped": pt_dropped,
            "account": args.account or "all",
            **({"post_now": sorted(post_now)} if post_now else {}),
        })
    except Exception:  # noqa: BLE001
        pass

    # A breaking dispatch that posted nothing exits non-zero so the operator who
    # clicked "Post now" sees a RED run instead of a silent no-op. Dry-run (the
    # kill-switch is off) is exempt — nothing was ever going to post.
    #
    # EXCEPT a pure dark-desk park (ruling 2026-07-29). Every sub-85 radar event
    # dispatches to a desk that is dark until XG-W2 arms it, so a red here is not
    # an incident report — it is a scheduled one, several times a day, and a
    # recurring expected red teaches the operator to stop reading reds. The park
    # already leaves two durable receipts (the ::warning in the summary and an
    # account_disabled row in the ledger), which is what a red was for. Narrow on
    # purpose: EVERY requested id must have been parked. A validation quarantine,
    # an unknown id, or any mix of park and failure stays red, because those are
    # the ones a human has to look at. An id that is not in this checkout's
    # outbox can never be parked, so it can never be covered here — a dispatch
    # naming a phantom id is a fault of its own and keeps its red.
    if post_now and live and not posted:
        _parked = set(_parked_auto) | set(_parked_post)
        if post_now <= _parked:
            log.info("--post-now: nothing posted — all %d requested item(s) "
                     "parked on dark desk(s) (account_disabled); the ::warning "
                     "and the quarantine rows are the receipts. Not a failure: "
                     "arming the desk in desk_network is what releases this lane.",
                     len(post_now))
            return 0
        log.error("--post-now: nothing was posted for %s — see the gate lines above",
                  ", ".join(sorted(post_now)))
        return 3

    return 0


def _parse_now(now_arg: str | None) -> datetime:
    if not now_arg:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(now_arg.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        log.warning("bad --now %r — using current time", now_arg)
        return datetime.now(timezone.utc)


def _is_immediate(scheduled_at: str | None) -> bool:
    s = (scheduled_at or "").strip()
    return not s or s == "immediate"


def dry_run_report(root=None, *, account: str | None = None,
                   now: datetime | None = None) -> dict:
    """Compute the DRY-RUN "would post" report as structured data — no side effects.

    This is the in-process entrypoint the admin "Run dry-run" button calls. It
    reuses the exact selection logic main() runs in dry-run, but returns a dict
    instead of logging and NEVER touches the network OR the ledger (no
    transition(), no _append_activity()). Fail-soft: any error becomes
    {"ok": False, "error": ...}.

    Returns {ok, mode:"dry_run", backend, cap, kill_switch, account,
             counts:{approved_due, would_post, quarantine, skipped_cap,
                     skipped_no_channel, stuck_posting, would_auto_approve,
                     would_park_dark},
             would_post:[{id,account,channel,chars,media,scheduled_at,preview}],
             quarantine:[{id,account,reasons}],
             would_auto_approve:[{id,account,chars}],
             would_park_dark:[{id,account}],
             stuck_posting:[ids], auto_approve:bool}.
    """
    try:
        _ensure_importable()
        r = _data_root(root)
        cfg = _load_marketing_cfg(r)
        pub_cfg = _publish_cfg(cfg)
        backend = str(pub_cfg.get("backend") or "buffer").strip()
        now = now or datetime.now(timezone.utc)

        from engine.marketing import outbox as _outbox  # noqa: PLC0415
        from engine.marketing.social_publisher import validate_postable  # noqa: PLC0415
        try:
            from engine.marketing.sentinel import publish_enabled as _pe  # noqa: PLC0415
            kill_on = _pe()
        except Exception:  # noqa: BLE001
            kill_on = False

        cap = _outbox.effective_cap(cfg)
        # Mirror main(): the cap that governs an account is the base ceiling
        # narrowed by its D08 ramp tier, resolved against the RUNTIME posting
        # date. announce=False — the admin preview must not spam the Actions
        # summary with config warnings the nightly gate already raised.
        _post_date = now.strftime("%Y-%m-%d")
        try:
            from engine.marketing.sentinel import resolve_ramp as _resolve_ramp  # noqa: PLC0415
            _ramp = _resolve_ramp(cfg, _post_date, root=r, announce=False)
        except Exception:  # noqa: BLE001
            _ramp = None

        def _cap_for(acct_id: str) -> int:
            return _outbox.effective_cap_for(cfg, acct_id, _post_date,
                                             root=r, ramp=_ramp)

        state = _outbox.fold_state(r)
        items_by_id = state["items"]
        statuses = state["status"]

        # The halt gate main() applies at post time. The admin preview MUST
        # apply it too: a halted desk showing up under "would post" tells the
        # operator the exact opposite of the truth, and the preview's whole job
        # is to say what a live run would do.
        try:
            from engine.marketing import health_monitor as _health  # noqa: PLC0415

            _halts = _health.load_halts(r)
        except Exception:  # noqa: BLE001
            _halts = {}

        # Same argument for desk liveness, and the failure is worse: a dark desk
        # under "would post" promises the operator a post the live run parks, and
        # promising a post on an UNARMED property is the exact confusion the park
        # exists to end. Resolved once, like the halts, and reported explicitly
        # (would_park_dark) rather than by silent omission.
        _dark = _dark_account_ids(cfg, r)
        would_park_dark: list[dict] = []

        def _acct_ok(it: dict) -> bool:
            return account is None or it.get("account") == account

        stuck = [i for i, s in statuses.items()
                 if s == "posting" and i in items_by_id and _acct_ok(items_by_id[i])]

        today = now.strftime("%Y-%m-%d")
        posted_today: dict[str, int] = _outbox.posted_today_by_account(state, today)

        # Auto-approve preview (always dry here → never mutates). Honors both the
        # global flag AND the scoped publish.auto_approve_kinds exception, so the
        # admin dry-run mirrors what a live run would auto-approve.
        auto_on = _auto_approve_cfg(pub_cfg)
        allowed_kinds = _auto_approve_kinds_cfg(pub_cfg)
        # Same scope resolution as main() — the admin preview must mirror what a
        # live run would do, or the operator reviews a queue the runner will not
        # produce (the whole point of a dry-run report).
        auto_unscoped = auto_on and _auto_approve_scope_cfg(pub_cfg) == "all"
        scoped_on = (not auto_unscoped) and bool(allowed_kinds)
        would_auto: list[dict] = []
        if auto_on or scoped_on:
            # announce=False: a preview must not spend the once-per-process
            # annotation budget the real dispatch behind it needs. parked_out is
            # how this writeless caller learns what the gate took out.
            _parked_ids: list[str] = []
            ids = _auto_approve_pass(
                _outbox, state, pub_cfg, cap=cap, now=now, live=False,
                account=account, posted_today=posted_today,
                validate_postable=validate_postable, root=r,
                allowed_kinds=(None if auto_unscoped else allowed_kinds),
                cap_for=_cap_for, halted=set(_halts), dark_accounts=_dark,
                announce=False, parked_out=_parked_ids,
            )
            for iid in _parked_ids:
                would_park_dark.append(
                    {"id": iid, "account": items_by_id.get(iid, {}).get("account", "")})
            for iid in ids:
                it = items_by_id.get(iid, {})
                would_auto.append({"id": iid, "account": it.get("account", ""),
                                   "chars": len(it.get("text", "") or "")})

        # APPROVED + DUE candidates, classified as main() would in dry-run.
        approved_due = sorted(
            (items_by_id[iid] for iid, s in statuses.items()
             if s == "approved" and iid in items_by_id and _acct_ok(items_by_id[iid])
             and _is_due(items_by_id[iid].get("scheduled_at"), now)),
            key=lambda i: (i.get("priority", 5), i.get("scheduled_at", ""), i.get("id", "")),
        )

        would_post: list[dict] = []
        quarantine: list[dict] = []
        skipped_cap = skipped_channel = skipped_floor = deferred_immediate = 0
        skipped_halt = 0
        budget = dict(posted_today)
        floor_min = _floor_minutes_cfg(pub_cfg)
        jitter_max = _jitter_max_cfg(pub_cfg)
        last_post_at = _last_global_post_at(r) if floor_min else None
        for it in approved_due:
            iid = it["id"]
            acct = it.get("account", "")
            text = it.get("text", "") or ""
            link = it.get("link")
            # Halt first, then the dark-desk park, exactly as main() orders them.
            if acct in _halts:
                skipped_halt += 1
                continue
            if _dark and acct in _dark:
                would_park_dark.append({"id": iid, "account": acct})
                continue
            problems = validate_postable(text, link, _links_allowed_for(pub_cfg, acct))
            if problems:
                quarantine.append({"id": iid, "account": acct, "reasons": problems})
                continue
            # Mirror main() exactly: an immediate item is cap-EXEMPT and floor-
            # EXEMPT — it projects as posting NOW; a ladder item skips at cap and
            # defers inside the floor.
            is_immediate = _is_immediate(it.get("scheduled_at"))
            if not is_immediate and _at_cap(budget.get(acct, 0), _cap_for(acct)):
                skipped_cap += 1
                continue
            channel_id = _channel_id_for(pub_cfg, acct)
            if not channel_id:
                skipped_channel += 1
                continue
            if not is_immediate and _within_floor(last_post_at, now, floor_min):
                skipped_floor += 1
                continue
            media = [m.get("path") for m in (it.get("media") or []) if m.get("path")]
            # Mirror main()'s booking exactly, jitter included: the offset is
            # derived from the item id, so this preview names the SAME minute the
            # live run will book (jitter_max 0 → booked_at == now, unchanged).
            jitter_minutes = 0 if is_immediate else _post_jitter_minutes(iid, jitter_max)
            booked_at = now + timedelta(minutes=jitter_minutes)
            would_post.append({
                "id": iid, "account": acct, "channel": channel_id,
                "chars": len(text), "media": len(media),
                "scheduled_at": it.get("scheduled_at"),
                "send_at": booked_at.strftime(_TS_FMT),
                "immediate": bool(is_immediate),
                "preview": text.replace("\n", " ")[:200],
            })
            budget[acct] = budget.get(acct, 0) + 1
            # advance the floor so the preview mirrors live pacing — from the
            # BOOKED time, as main() does
            last_post_at = booked_at

        return {
            "ok": True,
            "mode": "dry_run",
            "backend": backend,
            "cap": cap,
            "kill_switch": bool(kill_on),
            "account": account or "all",
            "auto_approve": bool(auto_on),
            "counts": {
                "approved_due": len(approved_due),
                "would_post": len(would_post),
                "quarantine": len(quarantine),
                "skipped_cap": skipped_cap,
                "skipped_no_channel": skipped_channel,
                "skipped_floor": skipped_floor,
                "deferred_immediate": deferred_immediate,
                "skipped_halt": skipped_halt,
                "stuck_posting": len(stuck),
                "would_auto_approve": len(would_auto),
                "would_park_dark": len(would_park_dark),
            },
            "would_post": would_post,
            "quarantine": quarantine,
            "would_auto_approve": would_auto,
            "would_park_dark": would_park_dark,
            "stuck_posting": stuck,
            "halted_accounts": sorted(_halts),
            # None = liveness UNKNOWN (gate inert), [] = asked, nothing dark.
            "dark_accounts": (None if _dark is None else sorted(_dark)),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("dry_run_report failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _run_list_channels(backend: str, *, token: str, cfg: dict) -> int:
    """--list-channels path: gated on a token; prints {id, service, name}."""
    if not token:
        log.error("--list-channels needs BUFFER_TOKEN in the environment "
                  "(none set) — nothing to query")
        return 2
    publisher = _make_publisher(backend, token=token, cfg=cfg)
    if publisher is None:
        return 2
    channels = publisher.list_channels()
    if not channels:
        log.info("no channels returned (empty token scope, or a query error — "
                 "see warnings above)")
        return 0
    print(f"Connected {backend} channels:")
    for ch in channels:
        print(f"  {ch.get('service',''):<12} {ch.get('id',''):<28} {ch.get('name','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
