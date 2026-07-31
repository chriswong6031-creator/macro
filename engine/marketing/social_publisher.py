"""engine.marketing.social_publisher — Backend-agnostic social publisher (W1).

The missing publish half of the D02 desk network: takes text (and optional
media/link) and pushes it to a social channel through a pluggable backend.
The only backend implemented today is Buffer's GraphQL API (personal access
token). The publisher itself knows nothing about the outbox ledger — the runner
(scripts/marketing_publisher.py) owns queue state; this module owns "send one
post, return a receipt".

DARK BY DEFAULT. Nothing here fires a network call unless a caller invokes
publish()/list_channels() with a real token AND a real transport. Every network
byte flows through BufferPublisher._transport(), which tests monkeypatch so the
whole module is exercised with ZERO live traffic.

Fail-soft contract (mirrors engine/marketing/outbox.py):
  * Public methods NEVER raise. Any network/GraphQL/parse error becomes a
    Receipt(ok=False, error=...) (publish) or [] (list_channels) with a
    log.warning. A crashing backend must never crash the runner mid-post.
  * All file/config derivation uses _repo_root() from __file__, never cwd.

Buffer GraphQL contract (confirmed 2026-07-22 from developers.buffer.com):
  endpoint   POST https://api.buffer.com                     [guides/your-first-post]
  auth       Authorization: Bearer <token>                   [api-standards / your-first-post]
  channels   query { channels(input:{organizationId}) { id name service } }
             org id via  query { account { organizations { id name } } }
  create     mutation { createPost(input: CreatePostInput) { ...union } }
             CreatePostInput = { text, channelId, schedulingType, mode,
                                 dueAt?, assets? }
             assets (CURRENT format, changed 2026-05-25) is an ordered list of
               { image: { url } }  or  { video: { url, metadata:{thumbnailOffset} } }
               — Buffer hosts NO uploads; each url must be publicly reachable.
             response is a UNION resolved with inline fragments:
               ... on PostActionSuccess { post { id text dueAt } }
               ... on MutationError    { message }
  delete     mutation { deletePost(input: DeletePostInput!): DeletePostPayload! }
             DeletePostInput = { id: PostId! }
             DeletePostPayload is a union of DeletePostSuccess { id } and
             VoidMutationError. Per the error-handling guide the API never
             returns VoidMutationError by name — the documented pattern is to
             select the `... on MutationError { message }` CATCH-ALL (which
             VoidMutationError satisfies) so a later-added error member still
             delivers its message without a query change. Same shape as create.
  The endpoint + query/mutation strings live in the module constants below so
  they are trivial to update as the beta evolves.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Buffer API constants — the ONE place to edit as the GraphQL beta changes.
# ─────────────────────────────────────────────────────────────────────────────

BUFFER_GRAPHQL_ENDPOINT = "https://api.buffer.com"
BUFFER_TOKEN_ENV = "BUFFER_TOKEN"


class BufferRateLimited(RuntimeError):
    """Buffer answered 429 — we are out of quota, not offline.

    RuntimeError on purpose: every existing caller catches broadly and turns a
    transport failure into a fail-soft "did not send", and that must not change.
    What changes is that the reason is now nameable, because the two failures
    need opposite responses — a rate limit is self-inflicted (the publisher and
    the metrics poller share one token and one 24h allowance) and is fixed by
    spacing our own calls out, while an outage is Buffer's and is fixed by
    waiting.
    """

    def __init__(self, message: str, *, retry_after: str = "") -> None:
        super().__init__(message)
        self.retry_after = retry_after
_HTTP_TIMEOUT_S = 15
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # a hostile/broken response must not OOM

# List connected channels for an organization.
_CHANNELS_QUERY = """
query GetChannels($input: ChannelsInput!) {
  channels(input: $input) {
    id
    name
    service
  }
}
""".strip()

# Resolve the organization id (channels() requires it).
_ORGANIZATIONS_QUERY = """
query GetOrganizations {
  account {
    organizations {
      id
      name
    }
  }
}
""".strip()

# Create a post. dueAt + mode:customScheduled schedule at a specific time;
# omitting dueAt with mode:addToQueue lets Buffer slot it into the queue.
# The response is a union — request both members via inline fragments.
_CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post {
        id
        text
        dueAt
      }
    }
    ... on MutationError {
      message
    }
  }
}
""".strip()

# Delete (cancel) ONE post by id. For a post that has not gone out yet — a
# customScheduled item still sitting in Buffer's queue — this is a CANCEL: it
# never reaches the network. For one Buffer has already sent, deleting removes
# Buffer's record; whether the live post survives on X is Buffer's business and
# NOT something this module may assume either way. That asymmetry is exactly why
# the recall runner (scripts/marketing_recall.py) refuses to call this on an item
# whose booked send time has passed — see its `_is_still_pending`.
#
# Contract confirmed 2026-07-28 against developers.buffer.com's reference +
# error-handling guides (direct fetch is Cloudflare-gated; read via the search
# index, corroborated across four independent queries):
#   deletePost(input: DeletePostInput!): DeletePostPayload!
#   DeletePostInput  = { id: PostId! }
#   DeletePostPayload = DeletePostSuccess { id } | VoidMutationError
# `... on MutationError { message }` is the documented catch-all — see the
# module docstring. If the beta renames this, THIS constant is the one edit.
_DELETE_POST_MUTATION = """
mutation DeletePost($input: DeletePostInput!) {
  deletePost(input: $input) {
    __typename
    ... on DeletePostSuccess {
      id
    }
    ... on MutationError {
      message
    }
  }
}
""".strip()

# Read back one post's analytics + its public permalink. The `post(input:{id})`
# query returns the x.com permalink (externalLink) — which createPost's payload
# does NOT expose — plus a normalized metrics list (impressions/reactions/…,
# refreshed ~daily by Buffer). metricsUpdatedAt is the last-refresh timestamp;
# a freshly-posted item may have an empty metrics list until Buffer's first pull.
# (Confirmed 2026-07-23 from developers.buffer.com analytics guide.)
_POST_METRICS_QUERY = """
query PostMetrics($input: PostInput!) {
  post(input: $input) {
    id
    externalLink
    metricsUpdatedAt
    metrics {
      type
      name
      value
      unit
    }
  }
}
""".strip()

# X (Twitter) counts every URL as a fixed-length t.co link regardless of the
# real URL length. 23 is the long-standing t.co reserved length.
_URL_WEIGHT = 23
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MAX_TWEET_LEN = 280


# ─────────────────────────────────────────────────────────────────────────────
# Receipt
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Receipt:
    """The outcome of one publish attempt.

    ok          True only when the backend confirmed the post was created.
    external_id backend post id (Buffer post.id) — None on failure.
    external_url permalink to the live post, when the backend gives one.
                (Buffer's createPost payload does NOT currently return a post
                 URL — TODO below — so this stays None for the Buffer backend.)
    error       human-readable failure string — None on success.
    backend     backend name, e.g. "buffer".
    at          iso8601 UTC timestamp of the attempt.
    """
    ok: bool
    external_id: str | None
    external_url: str | None
    error: str | None
    backend: str
    at: str


@dataclass
class DeleteResult:
    """The outcome of one delete/cancel attempt (BufferPublisher.delete_post).

    ok          True ONLY when the backend confirmed the post was deleted. Every
                other outcome — GraphQL error, "not found", transport failure,
                an unreadable payload — is False. This flag is load-bearing: the
                recall runner transitions an item out of `posted` if and only if
                ok is True, so anything short of a confirmed delete must leave
                the item exactly where it was. FAIL CLOSED, always.
    external_id the backend post id that was deleted — None on failure.
    error       human-readable failure string — None on success.
    backend     backend name, e.g. "buffer".
    at          iso8601 UTC timestamp of the attempt.
    """
    ok: bool
    external_id: str | None
    error: str | None
    backend: str
    at: str


@dataclass
class MetricsResult:
    """The outcome of one post-analytics read (BufferPublisher.fetch_post_metrics).

    ok            True only when the backend returned a post object for the id.
    external_url  the post's public permalink (Buffer `externalLink`) — the
                  x.com URL createPost never returns — or None.
    metrics       normalized name→value map (impressions/likes/reposts/comments/
                  clicks/engagement_rate when present). EMPTY {} is an honest
                  outcome: Buffer had not yet refreshed analytics for the post.
    raw           the untouched Buffer metrics list ([{type,name,value,unit}]),
                  preserved so no signal is lost to the normalization.
    metrics_updated_at  Buffer's last-refresh timestamp (metricsUpdatedAt), or None.
    error         human-readable failure string — None on success.
    backend       backend name, e.g. "buffer".
    at            iso8601 UTC timestamp of the read attempt.
    """
    ok: bool
    external_url: str | None
    metrics: dict[str, Any]
    raw: list[dict]
    metrics_updated_at: str | None
    error: str | None
    backend: str
    at: str


# Buffer's normalized metric `type`/`name` tokens → our stable console keys.
# Buffer labels vary by service; match on lowercased type first, then name.
# Anything unmapped still survives in MetricsResult.raw (nothing is dropped).
_METRIC_KEY_ALIASES: dict[str, str] = {
    "impressions": "impressions",
    "impression": "impressions",
    "reach": "impressions",
    "likes": "likes",
    "like": "likes",
    "favorites": "likes",
    "reactions": "likes",
    "reaction": "likes",
    "reposts": "reposts",
    "repost": "reposts",
    "retweets": "reposts",
    "retweet": "reposts",
    "shares": "reposts",
    "share": "reposts",
    "comments": "comments",
    "comment": "comments",
    "replies": "comments",
    "reply": "comments",
    "clicks": "clicks",
    "click": "clicks",
    "urlclicks": "clicks",
    "engagementrate": "engagement_rate",
    "engagement_rate": "engagement_rate",
}


def _normalize_metrics(raw: list[dict]) -> dict[str, Any]:
    """Map Buffer's [{type,name,value,unit}] list to stable console keys.

    Pure. Matches on the lowercased `type` then `name` against
    _METRIC_KEY_ALIASES. Unmapped entries are simply not surfaced under a
    console key (they remain in the caller's `raw`). Non-numeric values are
    skipped. Later duplicates win (Buffer never sends dupes, but be total).
    """
    out: dict[str, Any] = {}
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        token = str(m.get("type") or "").strip().lower().replace(" ", "")
        key = _METRIC_KEY_ALIASES.get(token)
        if key is None:
            name_tok = str(m.get("name") or "").strip().lower().replace(" ", "")
            key = _METRIC_KEY_ALIASES.get(name_tok)
        if key is None:
            continue
        val = m.get("value")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        out[key] = val
    return out


def _iso_now(now: datetime | None = None) -> str:
    ts = now if now is not None else datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


# Buffer rejects a customScheduled post whose dueAt is not in the future
# ("Invalid post input: dueAt must be in the future"). The publisher only ever
# posts DUE items, whose scheduled_at (their ladder slot) is in the PAST by post
# time — so a naive dueAt=scheduled_at fails EVERY post (the real reason the
# account had never published). Bump any past/near-now slot to a small margin
# ahead of now, which Buffer accepts and publishes promptly; the margin also
# absorbs runner↔Buffer clock skew.
_MIN_DUE_LEAD = timedelta(minutes=3)


def _effective_due_at(scheduled_at: str | None, now: datetime | None = None,
                      *, immediate: bool = False) -> str | None:
    """Resolve the dueAt to send Buffer, or None to fall back to addToQueue.

    - blank/unparseable scheduled_at → None (Buffer slots it into the queue);
    - a scheduled_at at/before now + lead → now + lead (post ~now, in the future);
    - a genuinely future scheduled_at → itself (honour the schedule).

    ``immediate=True`` is the SHARE-NOW contract (cadence masterplan F3): a
    breaking / immediate item must never fall through to ``addToQueue``, which
    parks it in *Buffer's own* queue and posts it at whatever slot that queue
    next offers — arbitrary latency on the one class of post whose whole value
    is being fast. With the flag set, a missing or unreadable schedule resolves
    to ``now + lead`` (customScheduled) instead of None.
    """
    s = (scheduled_at or "").strip()
    floor = (now if now is not None else datetime.now(timezone.utc)) + _MIN_DUE_LEAD
    _share_now = floor.strftime("%Y-%m-%dT%H:%M:%SZ") if immediate else None
    if not s:
        return _share_now
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return _share_now
    return (floor if dt < floor else dt).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level copy helpers (pure, no I/O)
# ─────────────────────────────────────────────────────────────────────────────

def tweet_length(text: str, link: str | None = None) -> int:
    """Approximate X's character count for `text` (+ an optional appended link).

    X counts ANY URL as a fixed 23 chars regardless of its real length (t.co
    wrapping). This replaces each URL in the body with a 23-char stand-in and
    adds 23 (plus a separating space) for a non-empty `link` appended to the
    post. Deliberately approximate — it is a guard rail for the 280 cap, not a
    byte-exact reimplementation of X's grapheme counter.
    """
    body = text or ""
    # Weight URLs inside the body as fixed-length.
    weighted_body = _URL_RE.sub("X" * _URL_WEIGHT, body)
    total = len(weighted_body)
    if link and link.strip():
        # A link appended to the post: its own 23 chars, plus one space to
        # separate it from the body when the body is non-empty.
        total += _URL_WEIGHT + (1 if weighted_body else 0)
    return total


def validate_postable(text: str, link: str | None, links_allowed: bool) -> list[str]:
    """Return a list of problem strings for a would-be post; [] means postable.

    Checks (all reported, not just the first):
      * empty/whitespace text                → "empty_text"
      * over the 280-char X cap              → "over_280:<n>"
      * a link present while links are off    → "link_not_allowed"
    """
    problems: list[str] = []

    if not text or not text.strip():
        problems.append("empty_text")

    n = tweet_length(text or "", link)
    if n > _MAX_TWEET_LEN:
        problems.append(f"over_280:{n}")

    if link and link.strip() and not links_allowed:
        problems.append("link_not_allowed")

    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Publisher protocol
# ─────────────────────────────────────────────────────────────────────────────

class SocialPublisher(Protocol):
    """Backend-agnostic publisher surface the runner depends on."""

    backend: str

    def publish(
        self,
        *,
        text: str,
        channel_id: str,
        media_paths: list[str] | None = None,
        link: str | None = None,
        scheduled_at: str | None = None,
        now: datetime | None = None,
        immediate: bool = False,
    ) -> Receipt:
        ...

    def delete_post(self, post_id: str, *, now: datetime | None = None) -> DeleteResult:
        ...

    def list_channels(self) -> list[dict]:
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Repo root (never cwd)
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Derive repo root the same way the other marketing modules do."""
    return Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Buffer backend
# ─────────────────────────────────────────────────────────────────────────────

class BufferPublisher:
    """Publish to a social channel via Buffer's GraphQL API.

    Auth: a personal access token, read from env BUFFER_TOKEN by default (a
    token may also be injected for tests). The token rides in the
    ``Authorization: Bearer <token>`` header.

    All HTTP is isolated in _transport(); tests monkeypatch that single method,
    so no test ever opens a socket. Every public method is fail-soft.
    """

    backend = "buffer"

    def __init__(
        self,
        *,
        token: str | None = None,
        organization_id: str | None = None,
        endpoint: str = BUFFER_GRAPHQL_ENDPOINT,
    ) -> None:
        self.token = (token if token is not None else os.environ.get(BUFFER_TOKEN_ENV, "")).strip()
        self.organization_id = (organization_id or "").strip() or None
        self.endpoint = endpoint

    # -- transport ------------------------------------------------------------

    def _transport(self, payload: dict) -> dict:
        """Send ONE GraphQL request and return the decoded JSON response.

        This is the ONLY method that touches the network. Tests monkeypatch it.
        `payload` is the GraphQL POST body ({"query": ..., "variables": {...}}).
        Returns the parsed JSON dict. Raises on transport/HTTP/decoding failure;
        the public callers convert those into fail-soft results.
        """
        if not self.token:
            raise RuntimeError("BUFFER_TOKEN is empty — cannot authenticate")

        body = json.dumps(payload).encode("utf-8")
        req = Request(  # noqa: S310 — fixed https Buffer endpoint
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
                raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # A 429 IS NOT A NETWORK BLIP, AND IT USED TO LOOK LIKE ONE.
            #
            # Buffer authenticates as ONE personal token, and BOTH the publisher
            # (`publish`) and the engagement poller (`fetch_post_metrics`) go
            # through this method with it. They share one 24h quota: a metrics
            # sweep over a few hundred posted items can spend the allowance the
            # publisher needs to post at all, and the publisher's failure then
            # arrives as a generic transport error that the public callers turn
            # into a fail-soft "did not send".
            #
            # Fail-soft is right — a rate limit must never crash a sweep — but
            # INDISTINGUISHABLE is not. "Buffer refused us because we are out of
            # quota" and "Buffer is down" call for opposite responses, and the
            # first is self-inflicted and fixable by spacing the poller out.
            #
            # BufferRateLimited subclasses RuntimeError, so every existing
            # `except Exception` caller keeps its current fail-soft behaviour
            # unchanged; the difference is that the reason is now on the record.
            if getattr(exc, "code", None) == 429:
                retry_after = ""
                try:
                    retry_after = str(exc.headers.get("Retry-After") or "")
                except Exception:  # noqa: BLE001
                    retry_after = ""
                print("::warning title=marketing-buffer-rate-limited::"
                      "Buffer returned 429 — the publisher and the engagement "
                      "poller share ONE token and ONE 24h quota, so this is most "
                      "likely our own polling spending the posting allowance"
                      + (f" (Retry-After: {retry_after})" if retry_after else ""),
                      flush=True)
                raise BufferRateLimited(
                    "Buffer rate limit (429)"
                    + (f"; retry after {retry_after}" if retry_after else ""),
                    retry_after=retry_after) from exc
            raise
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError("Buffer response exceeded size cap")
        return json.loads(raw.decode("utf-8"))

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _graphql_errors(resp: dict) -> str | None:
        """Return a joined GraphQL top-level error string, or None."""
        errs = resp.get("errors")
        if errs:
            msgs = [str(e.get("message") or e) for e in errs if isinstance(e, dict)] or [str(errs)]
            return "; ".join(msgs)
        return None

    @staticmethod
    def _build_assets(media_paths: list[str] | None) -> list[dict]:
        """Map media paths to Buffer `assets` entries (CURRENT 2026-05-25 shape).

        Buffer hosts NO uploads: each asset must carry a PUBLICLY reachable URL.
        Only entries that already look like http(s) URLs become assets; a local
        filesystem path (e.g. the outbox's data/marketing/outbox/media/*.svg)
        cannot be attached as-is and is skipped with a warning.

        TODO(W1+): to attach the outbox's locally-rendered chart media, first
        publish each SVG/PNG to a public host (R2 bucket) and pass the resulting
        URL here. (SVG is also not renderable on X — a PNG rasterization step is
        needed before this is useful.) Text-first posts need no assets.
        """
        assets: list[dict] = []
        for p in media_paths or []:
            s = str(p).strip()
            if not s:
                continue
            if s.lower().startswith(("http://", "https://")):
                assets.append({"image": {"url": s}})
            else:
                log.warning(
                    "BufferPublisher: skipping non-public media path %r — Buffer "
                    "needs a hosted URL (no upload endpoint)", s)
        return assets

    def _resolve_org_id(self) -> str | None:
        """Return the organization id, resolving + caching it if not set."""
        if self.organization_id:
            return self.organization_id
        resp = self._transport({"query": _ORGANIZATIONS_QUERY})
        err = self._graphql_errors(resp)
        if err:
            raise RuntimeError(f"GraphQL error resolving organization: {err}")
        orgs = (((resp.get("data") or {}).get("account") or {}).get("organizations")) or []
        if not orgs:
            raise RuntimeError("no organizations returned for this token")
        org_id = str(orgs[0].get("id") or "").strip()
        if not org_id:
            raise RuntimeError("organization id missing in response")
        self.organization_id = org_id
        return org_id

    # -- public API -----------------------------------------------------------

    def list_channels(self) -> list[dict]:
        """Return connected channels as [{id, service, name}].

        Fail-soft: returns [] on any error (with a log.warning). Use this to
        discover the X channel id once a real token exists.
        """
        try:
            org_id = self._resolve_org_id()
            resp = self._transport({
                "query": _CHANNELS_QUERY,
                "variables": {"input": {"organizationId": org_id}},
            })
            err = self._graphql_errors(resp)
            if err:
                log.warning("BufferPublisher.list_channels: GraphQL error: %s", err)
                return []
            raw = ((resp.get("data") or {}).get("channels")) or []
            out: list[dict] = []
            for ch in raw:
                if not isinstance(ch, dict):
                    continue
                out.append({
                    "id": str(ch.get("id") or ""),
                    "service": str(ch.get("service") or ""),
                    "name": str(ch.get("name") or ""),
                })
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("BufferPublisher.list_channels failed: %s", exc)
            return []

    def delete_post(self, post_id: str, *, now: datetime | None = None) -> DeleteResult:
        """Delete (cancel) one Buffer post by id.

        THE HOLE THIS CLOSES. `publish.max_forward_book_min` lets one sweep hand
        Buffer several posts as customScheduled sends up to an hour out. Those
        live in BUFFER's queue, not ours — so `MARKETING_PUBLISH_ENABLED=0`, which
        only stops the runner from creating NEW posts, does not stop them. On
        2026-07-28 a 16:25:46Z sweep booked five posts through 17:27Z, the
        operator disarmed at 16:26:47Z on quality defects, and all five still
        fired; the only recall available was deleting them by hand in Buffer's
        UI. This is the missing half of the kill switch.

        Uses the SAME transport/auth/timeout plumbing as publish(), so tests
        exercise it with zero live traffic.

        Fail-soft AND fail-closed: returns DeleteResult(ok=False, error=...) on
        any transport/GraphQL/parse failure and never raises. `ok` is True only
        on a confirmed DeletePostSuccess — a missing/ambiguous payload is a
        failure, because the caller uses this flag to decide whether a post may
        be marked recalled, and guessing there would resurrect a live post as
        "never sent".
        """
        at = _iso_now(now)
        pid = str(post_id or "").strip()
        if not pid:
            return DeleteResult(False, None, "empty_post_id", self.backend, at)
        try:
            resp = self._transport({
                "query": _DELETE_POST_MUTATION,
                "variables": {"input": {"id": pid}},
            })
            err = self._graphql_errors(resp)
            if err:
                log.warning("BufferPublisher.delete_post(%s): GraphQL error: %s", pid, err)
                return DeleteResult(False, None, f"graphql_error: {err}", self.backend, at)

            result = ((resp.get("data") or {}).get("deletePost")) or {}
            typename = result.get("__typename")

            # Union: DeletePostSuccess carries the deleted id; any error member
            # carries a message (the `... on MutationError` catch-all). Mirror
            # publish()'s __typename-absent fallback so a beta that stops
            # returning __typename still resolves an error message correctly.
            if typename not in (None, "DeletePostSuccess") or (
                    typename is None and result.get("message")):
                msg = result.get("message") or f"unknown error ({typename})"
                log.warning("BufferPublisher.delete_post(%s) refused: %s", pid, msg)
                return DeleteResult(False, None, f"buffer_error: {msg}", self.backend, at)

            deleted_id = str(result.get("id") or "").strip()
            if not deleted_id:
                # No confirmed id back = no confirmed delete. Do NOT assume the
                # post is gone (see the fail-closed note in the docstring).
                log.warning("BufferPublisher.delete_post(%s): no id in payload — "
                            "treating as NOT deleted", pid)
                return DeleteResult(
                    False, None,
                    f"buffer_no_deleted_id: {json.dumps(result)[:300]}",
                    self.backend, at)
            return DeleteResult(True, deleted_id, None, self.backend, at)

        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("BufferPublisher.delete_post(%s): http %s", pid, exc.code)
            return DeleteResult(False, None, f"http_error {exc.code}: {detail}",
                                self.backend, at)
        except URLError as exc:
            log.warning("BufferPublisher.delete_post(%s): network error: %s", pid, exc.reason)
            return DeleteResult(False, None, f"network_error: {exc.reason}", self.backend, at)
        except Exception as exc:  # noqa: BLE001
            log.warning("BufferPublisher.delete_post(%s) failed: %s", pid, exc)
            return DeleteResult(False, None, f"error: {exc}", self.backend, at)

    def fetch_post_metrics(self, post_id: str, *, now: datetime | None = None) -> MetricsResult:
        """Read one post's analytics + public permalink by Buffer post id.

        Uses the SAME transport/auth/timeout plumbing as publish() — the
        `post(input:{id})` query returns the x.com permalink (externalLink,
        absent from createPost) and a normalized metrics list Buffer refreshes
        ~daily. An empty metrics list is HONEST, not an error: a freshly-posted
        item has no analytics until Buffer's first pull.

        Fail-soft: returns MetricsResult(ok=False, error=...) on any
        transport/GraphQL/parse failure (never raises). An empty/missing
        post object (deleted or not-yet-indexed) is ok=False with a clear error.
        """
        at = _iso_now(now)
        pid = str(post_id or "").strip()
        if not pid:
            return MetricsResult(False, None, {}, [], None, "empty_post_id", self.backend, at)
        try:
            resp = self._transport({
                "query": _POST_METRICS_QUERY,
                "variables": {"input": {"id": pid}},
            })
            err = self._graphql_errors(resp)
            if err:
                return MetricsResult(False, None, {}, [], None,
                                     f"graphql_error: {err}", self.backend, at)
            post = ((resp.get("data") or {}).get("post")) or {}
            if not isinstance(post, dict) or not post:
                return MetricsResult(False, None, {}, [], None,
                                     "no_post_returned", self.backend, at)
            raw = post.get("metrics")
            raw_list = [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []
            ext = post.get("externalLink")
            ext_url = str(ext).strip() if ext else None
            updated = post.get("metricsUpdatedAt")
            updated_s = str(updated).strip() if updated else None
            return MetricsResult(
                True, ext_url or None, _normalize_metrics(raw_list), raw_list,
                updated_s or None, None, self.backend, at)
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            return MetricsResult(False, None, {}, [], None,
                                 f"http_error {exc.code}: {detail}", self.backend, at)
        except URLError as exc:
            return MetricsResult(False, None, {}, [], None,
                                 f"network_error: {exc.reason}", self.backend, at)
        except Exception as exc:  # noqa: BLE001
            return MetricsResult(False, None, {}, [], None,
                                 f"error: {exc}", self.backend, at)

    def publish(
        self,
        *,
        text: str,
        channel_id: str,
        media_paths: list[str] | None = None,
        link: str | None = None,
        scheduled_at: str | None = None,
        now: datetime | None = None,
        immediate: bool = False,
    ) -> Receipt:
        """Create (optionally schedule) one post on `channel_id`.

        `link`, when given, is appended to the post body (Buffer has no separate
        link field on CreatePostInput — the URL lives in the text). `media_paths`
        with public URLs become `assets`. `scheduled_at` (iso8601) schedules the
        post; omitting it adds to the account's queue — UNLESS `immediate` is
        set, in which case a missing/unreadable schedule still posts share-now
        (customScheduled at now + lead) rather than parking in Buffer's queue.

        NEVER raises: any failure returns Receipt(ok=False, error=...).
        """
        at = _iso_now(now)
        try:
            post_text = text or ""
            if link and link.strip():
                post_text = f"{post_text} {link.strip()}".strip()

            create_input: dict[str, Any] = {
                "text": post_text,
                "channelId": channel_id,
                "schedulingType": "automatic",
            }
            eff_due = _effective_due_at(scheduled_at, now, immediate=immediate)
            if eff_due:
                create_input["mode"] = "customScheduled"
                create_input["dueAt"] = eff_due
            else:
                create_input["mode"] = "addToQueue"

            assets = self._build_assets(media_paths)
            if assets:
                create_input["assets"] = assets

            resp = self._transport({
                "query": _CREATE_POST_MUTATION,
                "variables": {"input": create_input},
            })

            top_err = self._graphql_errors(resp)
            if top_err:
                return Receipt(False, None, None, f"graphql_error: {top_err}", self.backend, at)

            result = ((resp.get("data") or {}).get("createPost")) or {}
            typename = result.get("__typename")

            # Union: PostActionSuccess carries the post; MutationError carries a
            # message. Fall back on __typename absence to whatever fields exist.
            if typename == "MutationError" or (typename is None and result.get("message")):
                return Receipt(
                    False, None, None,
                    f"buffer_error: {result.get('message') or 'unknown error'}",
                    self.backend, at)

            post = result.get("post") or {}
            post_id = str(post.get("id") or "").strip()
            if not post_id:
                return Receipt(
                    False, None, None,
                    f"buffer_no_post_id: {json.dumps(result)[:300]}",
                    self.backend, at)

            # TODO(buffer): createPost's PostActionSuccess.post does not expose a
            # public permalink in the documented schema — leave external_url None
            # until the beta adds one (then request it in _CREATE_POST_MUTATION).
            return Receipt(True, post_id, None, None, self.backend, at)

        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            return Receipt(False, None, None, f"http_error {exc.code}: {detail}", self.backend, at)
        except URLError as exc:
            return Receipt(False, None, None, f"network_error: {exc.reason}", self.backend, at)
        except Exception as exc:  # noqa: BLE001
            return Receipt(False, None, None, f"error: {exc}", self.backend, at)
