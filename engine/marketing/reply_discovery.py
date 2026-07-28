"""engine.marketing.reply_discovery — reply-target discovery (XG-W4).

A SEPARATE twitterapi.io provider. It deliberately does not extend
``press_providers.TwitterApiIoProvider``, because that class is shaped for the
Trump wire and is wrong for a reply desk in three load-bearing ways (charter §5,
verified in-tree 2026-07-28):

  1. ``_request`` hardcodes ``includeReplies=false``. A reply desk needs the
     replies — that is where the conversations are.
  2. ``_count_tweets`` only recognises the ``tweets`` response key, so a
     mentions or thread-replies payload bills as zero and the spend counter
     silently under-reads.
  3. It owns the wire's cursor namespace and the wire's spend counter. Sharing
     either means reply polling can starve the Trump wire, which the charter
     forbids outright.

**The shared-bucket posture.** twitterapi.io is one account, one $75/mo bucket.
This lane carves a sub-budget out of it (``reply_discovery.monthly_usd_cap``,
default $15) and enforces it INDEPENDENTLY, with a deliberate asymmetry:

  * Reply spend increments only the reply counter, never the wire's. The wire's
    own cap check therefore cannot see reply spend at all — it is structurally
    impossible for reply polling to stop the wire. That is the guarantee the
    charter asks for and it holds unconditionally.
  * Reply polling additionally stops when the COMBINED spend it can observe
    reaches the global cap. Reply yields to the wire; the wire never yields to
    reply. When the wire's spend is not observable the sub-cap alone binds,
    which is still safe in the protected direction.

State (cursors + spend) lives under the HOST state dir, never the repo: the M1
is the nightly render host and the house law is "pollers make zero repo writes".

Public API:
    load_register(root=None) -> dict                # config/reply_targets.yml
    validate_register(reg) -> list[str]             # [] means valid
    register_for_account(reg, account) -> list[dict]
    count_items(response) -> int                    # endpoint-shape aware
    ReplyDiscoveryProvider(cfg, *, sub_cap_usd, global_cap_usd, ...)
        .fetch(*, session_state, offline=False, wire_spend_usd=None) -> list[dict]
        .poll_outcomes(*, session_state, status_ids, offline=False) -> list[dict]
    run_tick(provider, *, root=None, offline=False) -> dict   # load, poll, SAVE
    load_state(root=None) / save_state(state, root=None)
    build_provider(press_cfg, marketing_cfg=None, *, root=None)
        -> ReplyDiscoveryProvider | None
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from engine.marketing.reply_queue import state_dir

log = logging.getLogger(__name__)

_TIMEOUT_S = 12
_MAX_BYTES = 2_000_000
_DEFAULT_UA = "MastermindX-ReplyDesk/1.0 (+https://mastermind-x.com)"

# twitterapi.io pricing, same rate card as the wire lane (press_providers).
# Duplicated as a named constant rather than imported so a wire-lane refactor
# cannot silently re-price this lane's budget without a test noticing.
_PRICE_PER_1K = 0.15
_MIN_CHARGE = 0.00015

#: Sub-budget default. Small on purpose — this lane is additive to a bucket the
#: wire already depends on, and the charter's rule is that the wire wins.
DEFAULT_SUB_CAP_USD = 15.0
DEFAULT_GLOBAL_CAP_USD = 75.0

#: Cursor namespace. NOT "twitterapiio" — that key is the wire's.
STATE_NS = "reply_discovery"

TIERS: frozenset[str] = frozenset({"relationship", "conversion", "breakout"})

_REGISTER_REL = Path("config") / "reply_targets.yml"


# ---------------------------------------------------------------------------
# Author register (config/reply_targets.yml)
# ---------------------------------------------------------------------------
def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def load_register(root: Path | str | None = None) -> dict:
    """Load the per-persona author register. Returns {} when absent."""
    path = _repo_root(root) / _REGISTER_REL
    if not path.exists():
        log.warning("reply_discovery: no author register at %s", path)
        return {}
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_discovery: cannot parse %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def validate_register(reg: dict) -> list[str]:
    """Return a list of schema errors; [] means valid.

    The register is operator-curated. Validation is the deliverable, not the
    handle list: a malformed entry must fail loudly at load rather than quietly
    poll the wrong account or bill an unknown tier.
    """
    errors: list[str] = []
    if not isinstance(reg, dict):
        return ["register must be a mapping"]

    accounts = reg.get("accounts")
    if not isinstance(accounts, dict):
        return ["register must carry an 'accounts' mapping"]

    seen_global: dict[str, str] = {}
    for account, block in accounts.items():
        if not isinstance(block, dict):
            errors.append(f"accounts.{account}: must be a mapping")
            continue
        beats = block.get("beats")
        if beats is not None and not isinstance(beats, list):
            errors.append(f"accounts.{account}.beats: must be a list")
        authors = block.get("authors") or []
        if not isinstance(authors, list):
            errors.append(f"accounts.{account}.authors: must be a list")
            continue
        seen_local: set[str] = set()
        for i, entry in enumerate(authors):
            where = f"accounts.{account}.authors[{i}]"
            if not isinstance(entry, dict):
                errors.append(f"{where}: must be a mapping")
                continue
            handle = str(entry.get("handle") or "").strip()
            if not handle:
                errors.append(f"{where}: 'handle' must be non-empty")
                continue
            if handle.startswith("@"):
                errors.append(f"{where}: 'handle' must not include a leading '@' (got {handle!r})")
            key = handle.lower().lstrip("@")
            if key in seen_local:
                errors.append(f"{where}: duplicate handle {handle!r} for {account}")
            seen_local.add(key)
            tier = str(entry.get("tier") or "").strip()
            if tier not in TIERS:
                errors.append(f"{where}: tier {tier!r} not in {sorted(TIERS)}")
            entry_beats = entry.get("beats")
            if entry_beats is not None and not isinstance(entry_beats, list):
                errors.append(f"{where}: 'beats' must be a list")
            # One conversation, one owner starts at the register: the same author
            # curated onto two desks guarantees a same-thread collision later.
            if key in seen_global and seen_global[key] != account:
                errors.append(
                    f"{where}: handle {handle!r} is already registered to "
                    f"{seen_global[key]!r} — one author, one desk"
                )
            seen_global.setdefault(key, account)
    return errors


def register_for_account(reg: dict, account: str) -> list[dict]:
    """Curated author entries for one desk, normalised."""
    block = ((reg or {}).get("accounts") or {}).get(account) or {}
    beats = [str(b).lower() for b in (block.get("beats") or [])]
    out: list[dict] = []
    for entry in block.get("authors") or []:
        if not isinstance(entry, dict):
            continue
        handle = str(entry.get("handle") or "").strip().lstrip("@")
        if not handle or entry.get("enabled") is False:
            continue
        out.append({
            "handle": handle,
            "tier": str(entry.get("tier") or "conversion"),
            "beats": [str(b).lower() for b in (entry.get("beats") or beats)],
            "notes": entry.get("notes"),
            "account": account,
        })
    return out


# ---------------------------------------------------------------------------
# Endpoint-shape-aware cost counter
# ---------------------------------------------------------------------------
#: Every response key twitterapi.io uses for a list of tweet-like objects. The
#: wire lane's counter knows only "tweets", so a mentions or thread-replies
#: payload bills as ZERO there — an under-read that would let this lane spend
#: past its budget while the counter reported nothing.
_ITEM_KEYS: tuple[str, ...] = ("tweets", "replies", "mentions", "results", "data", "items")


def count_items(response: str | dict | None) -> int:
    """Count tweet-like objects in ANY twitterapi.io response shape.

    Handles: {tweets:[...]}, {replies:[...]}, {mentions:[...]}, {results:[...]},
    {data:[...]}, {data:{tweets:[...]}}, and a bare top-level list.
    """
    try:
        data = response if isinstance(response, (dict, list)) else json.loads(response or "{}")
    except Exception:  # noqa: BLE001
        return 0
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    for key in _ITEM_KEYS:
        val = data.get(key)
        if isinstance(val, list):
            return len(val)
        if isinstance(val, dict):
            for nested in _ITEM_KEYS:
                inner = val.get(nested)
                if isinstance(inner, list):
                    return len(inner)
    return 0


def extract_items(response: dict | None) -> list[dict]:
    """Pull the tweet-like objects out of any supported response shape."""
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if not isinstance(response, dict):
        return []
    for key in _ITEM_KEYS:
        val = response.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
        if isinstance(val, dict):
            for nested in _ITEM_KEYS:
                inner = val.get(nested)
                if isinstance(inner, list):
                    return [r for r in inner if isinstance(r, dict)]
    return []


# ---------------------------------------------------------------------------
# Host state (cursors + spend) — zero repo writes
# ---------------------------------------------------------------------------
def _state_path(root: Path | str | None = None) -> Path:
    return state_dir(root) / "discovery" / "state.json"


def load_state(root: Path | str | None = None) -> dict:
    path = _state_path(root)
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_discovery: cannot read %s: %s", path, exc)
        return {}


def save_state(state: dict, root: Path | str | None = None) -> bool:
    """Atomic write (tmp + replace). Host state only — never git-tracked."""
    path = _state_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_discovery: cannot write %s: %s", path, exc)
        return False


def _as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------
class ReplyDiscoveryProvider:
    """twitterapi.io reads for the reply desk. Read-only, allowlist-only."""

    source_tier = "x_reply"
    billed = True  # dry-run/offline must skip every fetch this class makes

    def __init__(
        self,
        cfg: dict,
        *,
        sub_cap_usd: float = DEFAULT_SUB_CAP_USD,
        global_cap_usd: float = DEFAULT_GLOBAL_CAP_USD,
        register: dict | None = None,
        our_accounts: dict[str, str] | None = None,
        satire_blocklist: list[str] | None = None,
    ) -> None:
        cfg = cfg or {}
        self.cfg = cfg
        self.base_url = str(cfg.get("base_url", "https://api.twitterapi.io"))
        self.auth_header = str(cfg.get("auth_header", "X-API-Key"))
        self.key_env = str(cfg.get("key_env", "TWITTERAPI_IO_KEY"))
        self.user_agent = str(cfg.get("user_agent", _DEFAULT_UA))
        endpoints = cfg.get("endpoints") or {}
        self.ep_author_posts = str(endpoints.get("author_posts", "/twitter/user/last_tweets"))
        self.ep_mentions = str(endpoints.get("mentions", "/twitter/user/mentions"))
        self.ep_post_replies = str(endpoints.get("post_replies", "/twitter/tweet/replies"))
        # Which tiers are worth paying for replies on. Relationship targets are
        # where a conversation actually starts, so their threads are read in
        # full; breakout targets are read top-level only (cheaper, and a giant
        # thread's replies are clutter we would not enter anyway).
        self.include_replies_tiers = {
            str(t).strip().lower()
            for t in (cfg.get("include_replies_for_tiers") or ["relationship"])
        }
        self.max_requests_per_tick = int(cfg.get("max_requests_per_tick", 12))
        self.sub_cap_usd = float(sub_cap_usd)
        self.global_cap_usd = float(global_cap_usd)
        self.register = register or {}
        #: {account_id: handle} for our own accounts, for mentions polling.
        self.our_accounts = dict(our_accounts or {})
        self.satire = {str(h).lower().lstrip("@") for h in (satire_blocklist or [])}

        if self.sub_cap_usd > self.global_cap_usd:
            print(
                f"::warning title=reply-discovery-subcap::reply_discovery.monthly_usd_cap "
                f"${self.sub_cap_usd:.2f} exceeds the shared twitterapi.io cap "
                f"${self.global_cap_usd:.2f} — clamped to the shared cap",
                flush=True,
            )
            self.sub_cap_usd = self.global_cap_usd

    # -- budget ------------------------------------------------------------
    @staticmethod
    def _month_key(now: datetime | None = None) -> str:
        return (now or datetime.now(tz=timezone.utc)).strftime("%Y-%m")

    def budget_state(self, session_state: dict, *, now: datetime | None = None) -> dict:
        """This lane's own spend bucket for the current month."""
        ns = session_state.setdefault(STATE_NS, {})
        spend = ns.setdefault("spend", {})
        return spend.setdefault(self._month_key(now), {"requests": 0, "items": 0, "usd": 0.0})

    @staticmethod
    def wire_spend(session_state: dict, *, now: datetime | None = None) -> float:
        """Read the WIRE lane's spend for this month out of shared session state.

        The two lanes share one twitterapi.io account, and when both run off the
        same daemon state their counters sit side by side. Reading the wire's
        number here is what makes the shared-bucket stop live rather than
        theoretical — an earlier version took it as a parameter no caller passed,
        so the combined ceiling was $75 + $15 = $90 against a $75 bucket.

        This lane only READS that counter; it never writes it. The wire's own
        cap check therefore still cannot see reply spend, which is what keeps
        reply polling structurally unable to starve the wire.
        """
        month = (now or datetime.now(tz=timezone.utc)).strftime("%Y-%m")
        spend = ((session_state or {}).get("twitterapiio") or {}).get("spend") or {}
        try:
            return float((spend.get(month) or {}).get("usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def budget_check(self, month_spend: dict, *, wire_spend_usd: float | None = None) -> tuple[bool, str]:
        """May this lane make one more billed request?

        Two independent stops. The sub-cap is the lane's own ceiling. The
        shared-bucket stop makes this lane yield to the wire — never the
        reverse, which is why the wire's counter is read but never written.

        ``wire_spend_usd`` of None means "not observable", which falls back to
        the sub-cap alone. That is still safe in the protected direction.
        """
        usd = float(month_spend.get("usd", 0.0) or 0.0)
        if usd >= self.sub_cap_usd:
            return False, "reply_sub_cap"
        if wire_spend_usd is not None:
            if usd + float(wire_spend_usd) >= self.global_cap_usd:
                return False, "shared_bucket_cap"
        return True, ""

    def _bill(self, month_spend: dict, n_items: int) -> float:
        cost = max(_MIN_CHARGE, n_items / 1000.0 * _PRICE_PER_1K)
        month_spend["requests"] = int(month_spend.get("requests", 0)) + 1
        month_spend["items"] = int(month_spend.get("items", 0)) + n_items
        month_spend["usd"] = round(float(month_spend.get("usd", 0.0)) + cost, 6)
        return cost

    @staticmethod
    def _announce_stop(reason: str, month_spend: dict, cap: float) -> None:
        title = "reply-discovery-subcap" if reason == "reply_sub_cap" else "reply-discovery-bucket"
        print(
            f"::warning title={title}::reply discovery stopped ({reason}): "
            f"month spend ${float(month_spend.get('usd', 0.0)):.4f} against cap ${cap:.2f} "
            f"— the Trump wire lane is unaffected",
            flush=True,
        )

    # -- cursors -----------------------------------------------------------
    @staticmethod
    def _cursors(session_state: dict) -> dict:
        """Cursor namespace, distinct from the wire's ``twitterapiio`` key."""
        return session_state.setdefault(STATE_NS, {}).setdefault("cursors", {})

    # -- transport ---------------------------------------------------------
    def _request(self, api_key: str, endpoint: str, params: dict) -> dict | None:
        """One GET against twitterapi.io. Returns parsed JSON or None.

        Unlike the wire lane's ``_request``, ``includeReplies`` is a caller
        decision, not a constant.
        """
        url = f"{self.base_url}{endpoint}?{urlencode(params)}"
        try:
            req = Request(url, headers={  # noqa: S310
                "User-Agent": self.user_agent,
                self.auth_header: api_key,
                "Accept": "application/json",
            })
            with urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310
                raw = resp.read(_MAX_BYTES + 1)
            return json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            print(f"[reply_discovery] request error ({endpoint}): {exc}", file=sys.stderr)
            return None

    # -- normalisation -----------------------------------------------------
    @staticmethod
    def _norm_tweet(raw: dict, *, kind: str, author_tier: str, beats: list[str],
                    account: str | None, our_handle: str | None = None) -> dict | None:
        sid = str(raw.get("id") or raw.get("id_str") or "").strip()
        if not sid:
            return None
        author = raw.get("author") or raw.get("user") or {}
        handle = str(
            (author.get("userName") or author.get("screen_name") or author.get("username") or "")
        ).strip().lstrip("@")
        text = str(raw.get("text") or raw.get("full_text") or "")
        in_reply_to = str(
            raw.get("inReplyToId") or raw.get("in_reply_to_status_id_str") or ""
        ).strip()
        conv = str(raw.get("conversationId") or raw.get("conversation_id") or "").strip()
        return {
            "kind": kind,
            "status_id": sid,
            "thread_root_id": conv or in_reply_to or sid,
            "in_reply_to_id": in_reply_to or None,
            "url": str(raw.get("url") or (f"https://x.com/{handle}/status/{sid}" if handle else "")),
            "author": handle,
            "author_tier": author_tier,
            "beats": list(beats),
            "text": text,
            "created_at": raw.get("createdAt") or raw.get("created_at"),
            "reply_count": _as_int(raw.get("replyCount") or raw.get("reply_count")) or 0,
            "like_count": _as_int(raw.get("likeCount") or raw.get("like_count")) or 0,
            "retweet_count": _as_int(raw.get("retweetCount") or raw.get("retweet_count")) or 0,
            "view_count": _as_int(raw.get("viewCount") or raw.get("view_count")) or 0,
            "account": account,
            "is_reply_to_us": bool(our_handle) and kind in {"mention", "our_post_reply"},
            "our_handle": our_handle,
        }

    def _harvest(self, response: dict | None, *, kind: str, author_tier: str,
                 beats: list[str], account: str | None, since_id: str | None,
                 our_handle: str | None = None) -> tuple[list[dict], str | None]:
        """Normalise + apply the client-side since-id gate.

        twitterapi.io has no native since-id param on these endpoints, so the
        cursor is enforced here: keep ids strictly newer than the cursor and
        advance it to the newest id seen.
        """
        out: list[dict] = []
        since_int = _as_int(since_id)
        max_int = since_int
        for raw in extract_items(response):
            norm = self._norm_tweet(raw, kind=kind, author_tier=author_tier, beats=beats,
                                    account=account, our_handle=our_handle)
            if norm is None:
                continue
            if norm["author"].lower() in self.satire:
                continue
            tid = _as_int(norm["status_id"])
            if since_int is not None and tid is not None and tid <= since_int:
                continue
            if tid is not None and (max_int is None or tid > max_int):
                max_int = tid
            out.append(norm)
        new_since = str(max_int) if max_int is not None else since_id
        return out, new_since

    # -- the poll ----------------------------------------------------------
    def fetch(
        self,
        *,
        session_state: dict,
        offline: bool = False,
        wire_spend_usd: float | None = None,
        accounts: list[str] | None = None,
        now: datetime | None = None,
    ) -> list[dict]:
        """Poll monitored authors + our own mentions. Returns reply targets.

        ``offline`` makes zero network calls and zero spend (dry-run law for
        billed providers). ``wire_spend_usd`` lets the caller hand this lane the
        wire's observed spend so it can yield inside the shared bucket.
        """
        if offline:
            return []

        api_key = os.environ.get(self.key_env, "").strip()
        if not api_key:
            log.warning("reply_discovery: %s unset — skipping (no spend)", self.key_env)
            return []

        month_spend = self.budget_state(session_state, now=now)
        cursors = self._cursors(session_state)
        # Observe the wire's spend from shared state unless the caller overrode
        # it, so the shared-bucket stop binds without every caller remembering.
        if wire_spend_usd is None:
            wire_spend_usd = self.wire_spend(session_state, now=now)

        ok, reason = self.budget_check(month_spend, wire_spend_usd=wire_spend_usd)
        if not ok:
            cap = self.sub_cap_usd if reason == "reply_sub_cap" else self.global_cap_usd
            self._announce_stop(reason, month_spend, cap)
            return []

        targets: list[dict] = []
        requests_made = 0
        if accounts is not None:
            want_accounts = list(accounts)
        else:
            want_accounts = sorted(
                set((self.register.get("accounts") or {}).keys()) | set(self.our_accounts.keys())
            )
            # ROTATE. A fixed alphabetical order plus a per-tick request cap
            # starves the tail of the list forever — with 6 desks and a cap of
            # 12, `meagan` and `sophia` were never polled on any tick. The
            # rotation cursor lives in the same state blob as the spend counters.
            ns = session_state.setdefault(STATE_NS, {})
            start = int(ns.get("rotation", 0) or 0)
            if want_accounts:
                start %= len(want_accounts)
                want_accounts = want_accounts[start:] + want_accounts[:start]
                ns["rotation"] = (start + 1) % len(want_accounts)

        truncated = False
        for account in want_accounts:
            if truncated:
                break
            # (a) curated authors from the register
            for entry in register_for_account(self.register, account):
                if requests_made >= self.max_requests_per_tick:
                    truncated = True
                    break
                ok, reason = self.budget_check(month_spend, wire_spend_usd=wire_spend_usd)
                if not ok:
                    cap = self.sub_cap_usd if reason == "reply_sub_cap" else self.global_cap_usd
                    self._announce_stop(reason, month_spend, cap)
                    return targets

                handle = entry["handle"]
                tier = entry["tier"]
                include_replies = tier.lower() in self.include_replies_tiers
                ckey = f"author:{handle}"
                params = {
                    "userName": handle,
                    "includeReplies": "true" if include_replies else "false",
                }
                resp = self._request(api_key, self.ep_author_posts, params)
                requests_made += 1
                self._bill(month_spend, count_items(resp))
                got, new_since = self._harvest(
                    resp, kind="author_post", author_tier=tier, beats=entry["beats"],
                    account=account, since_id=cursors.get(ckey),
                )
                cursors[ckey] = new_since or cursors.get(ckey) or ""
                targets.extend(got)

            # (b) mentions of / replies to our own account — the M2 lane's
            #     lowest-risk surface, and inbound is always worth reading.
            our_handle = self.our_accounts.get(account)
            if our_handle and not truncated:
                if requests_made >= self.max_requests_per_tick:
                    truncated = True
                    break
                ok, reason = self.budget_check(month_spend, wire_spend_usd=wire_spend_usd)
                if not ok:
                    cap = self.sub_cap_usd if reason == "reply_sub_cap" else self.global_cap_usd
                    self._announce_stop(reason, month_spend, cap)
                    return targets
                ckey = f"mentions:{our_handle}"
                resp = self._request(api_key, self.ep_mentions, {"userName": our_handle})
                requests_made += 1
                self._bill(month_spend, count_items(resp))
                got, new_since = self._harvest(
                    resp, kind="mention", author_tier="inbound", beats=[],
                    account=account, since_id=cursors.get(ckey), our_handle=our_handle,
                )
                cursors[ckey] = new_since or cursors.get(ckey) or ""
                targets.extend(got)

        if truncated:
            print(
                f"::warning title=reply-discovery-tick-cap::hit max_requests_per_tick "
                f"({self.max_requests_per_tick}) before covering every desk — the "
                f"rotation cursor resumes at the next desk, but a persistently "
                f"truncated tick means some desks are polled rarely",
                flush=True,
            )
        return targets

    def poll_outcomes(
        self,
        *,
        session_state: dict,
        status_ids: list[str],
        offline: bool = False,
        wire_spend_usd: float | None = None,
        now: datetime | None = None,
    ) -> list[dict]:
        """Telemetry stub — did the parent author answer our reply?

        Reads the replies under each of our sent status ids. This wave records
        only what the endpoint directly observes (``author_replied``, ``likes``);
        the parent-adjusted labels that turn these into a learning signal are
        XG-W6's, and land on top of ``reply_queue.record_outcome`` without
        touching this method's shape.
        """
        if offline or not status_ids:
            return []
        api_key = os.environ.get(self.key_env, "").strip()
        if not api_key:
            return []
        month_spend = self.budget_state(session_state, now=now)
        out: list[dict] = []
        for sid in status_ids[: self.max_requests_per_tick]:
            ok, reason = self.budget_check(month_spend, wire_spend_usd=wire_spend_usd)
            if not ok:
                cap = self.sub_cap_usd if reason == "reply_sub_cap" else self.global_cap_usd
                self._announce_stop(reason, month_spend, cap)
                break
            resp = self._request(api_key, self.ep_post_replies, {"tweetId": str(sid)})
            self._bill(month_spend, count_items(resp))
            items = extract_items(resp)
            out.append({
                "status_id": str(sid),
                "replies": len(items),
                "raw": items,
            })
        return out


# ---------------------------------------------------------------------------
# Construction from config
# ---------------------------------------------------------------------------
def run_tick(
    provider: ReplyDiscoveryProvider,
    *,
    root: Path | str | None = None,
    offline: bool = False,
    accounts: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load host state, poll once, persist. THE entry point for a scheduled tick.

    Persistence is the whole point. Without it the monthly spend counter resets
    to zero on every process, which makes the sub-cap vacuous, and the since-id
    cursors reset too, so every author's full timeline is re-read and re-billed
    every tick. Both failures are silent and both cost money, which is why the
    load/save pair lives inside the tick rather than in a caller's good
    intentions.

    Returns {targets, spend, requests, persisted}.
    """
    state = load_state(root)
    targets = provider.fetch(session_state=state, offline=offline,
                             accounts=accounts, now=now)
    persisted = False if offline else save_state(state, root)
    month = (now or datetime.now(tz=timezone.utc)).strftime("%Y-%m")
    spend = ((state.get(STATE_NS) or {}).get("spend") or {}).get(month) or {}
    return {
        "targets": targets,
        "count": len(targets),
        "spend": spend,
        "wire_spend": provider.wire_spend(state, now=now),
        "persisted": persisted,
    }


def build_provider(
    press_cfg: dict | None,
    marketing_cfg: dict | None = None,
    *,
    root: Path | str | None = None,
) -> ReplyDiscoveryProvider | None:
    """Build the provider from config, or None when the lane is off.

    The sub-cap lives beside the wire's cap in ``config/press_sources.yml`` so
    the shared-bucket relationship is visible in one file.
    """
    press_cfg = press_cfg or {}
    rd_cfg = press_cfg.get("reply_discovery") or {}
    if not rd_cfg or rd_cfg.get("enabled") is False:
        return None

    global_cap = float((press_cfg.get("spend") or {}).get("twitterapiio_monthly_cap_usd",
                                                          DEFAULT_GLOBAL_CAP_USD))
    sub_cap = float(rd_cfg.get("monthly_usd_cap", DEFAULT_SUB_CAP_USD))

    register = load_register(root)
    errors = validate_register(register) if register else []
    if errors:
        for err in errors[:10]:
            print(f"::warning title=reply-register-invalid::{err}", flush=True)
        return None

    our_accounts: dict[str, str] = {}
    for acct in ((marketing_cfg or {}).get("desk_network") or {}).get("accounts") or []:
        if not isinstance(acct, dict) or not acct.get("enabled"):
            continue
        handle = str(acct.get("handle") or "").strip().lstrip("@")
        if handle:
            our_accounts[str(acct.get("id"))] = handle

    return ReplyDiscoveryProvider(
        rd_cfg,
        sub_cap_usd=sub_cap,
        global_cap_usd=global_cap,
        register=register,
        our_accounts=our_accounts,
        satire_blocklist=press_cfg.get("satire_blocklist") or [],
    )


__all__ = [
    "ReplyDiscoveryProvider", "build_provider", "run_tick",
    "count_items", "extract_items",
    "load_register", "validate_register", "register_for_account",
    "load_state", "save_state", "STATE_NS", "TIERS",
    "DEFAULT_SUB_CAP_USD", "DEFAULT_GLOBAL_CAP_USD",
]
