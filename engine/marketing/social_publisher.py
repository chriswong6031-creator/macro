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
  The endpoint + query/mutation strings live in the module constants below so
  they are trivial to update as the beta evolves.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _iso_now(now: datetime | None = None) -> str:
    ts = now if now is not None else datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    ) -> Receipt:
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
        with urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
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

    def publish(
        self,
        *,
        text: str,
        channel_id: str,
        media_paths: list[str] | None = None,
        link: str | None = None,
        scheduled_at: str | None = None,
        now: datetime | None = None,
    ) -> Receipt:
        """Create (optionally schedule) one post on `channel_id`.

        `link`, when given, is appended to the post body (Buffer has no separate
        link field on CreatePostInput — the URL lives in the text). `media_paths`
        with public URLs become `assets`. `scheduled_at` (iso8601) schedules the
        post; omitting it adds to the account's queue.

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
            if scheduled_at and scheduled_at.strip():
                create_input["mode"] = "customScheduled"
                create_input["dueAt"] = scheduled_at.strip()
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
