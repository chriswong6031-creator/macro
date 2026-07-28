"""engine.marketing.story_spine — L0 identity + incremental story clustering (XG-W5).

MARKETING-INTERNAL, DISPLAY-TIER. Nothing here is a market signal and nothing it
produces is ever user-facing: a story id, a source count and a tier mix are triage
metadata for the wire desk. NO LLM anywhere (docket law + DO_NOT_REBUILD: the
model never decides what is the same story, and never originates a score).

The layer, top to bottom (masterplan §3 "L0 — identity & story spine"):

    URL normalize -> exact identity key -> MinHash-LSH near-dup -> optional
    semantic pass -> incremental cluster assignment

A STORY record carries: cluster id, first_seen, source count, tier mix, observed
engagement — exactly the four the masterplan pins.

OPTIONAL DEPENDENCIES DEGRADE; THEY NEVER CRASH THE DAEMON. The VPS press daemon
runs this on every tick, so a missing wheel or a missing model artifact must be a
downgrade notice, never a traceback and never a blocked emission:

    datasketch absent   -> near-dup pass DISABLED. Identity collapses to the
                           exact key only (truth_status_id / normalized URL /
                           normalized-headline hash), which is what the lane did
                           before this module existed.
    model2vec absent,
    or no local model   -> semantic pass DISABLED.

Each downgrade prints ONE start-of-line notice per process (house law: bare
``print("::notice ...", flush=True)``, never through a logger) and is also
readable programmatically via ``StorySpine.downgrades``.

NO RUNTIME MODEL DOWNLOAD, ON ANY PATH. ``load_encoder`` only ever loads from a
LOCAL directory named in config; it never passes a hub id and never reaches the
network. Fetching the Model2Vec artifact is an explicit operator/R2 step
(docs/scoring_brain.md §3); an absent artifact means "pass disabled", full stop.

STATE. The spine is a pure function of the mutable dict handed to it, which the
press daemon owns and persists to data/marketing/press/state.json — GITIGNORED
host state, never a repo write (house law: pollers make zero git writes, and the
nightly stays the sole advancer of tracked ledgers).

Public API:
    normalize_url(url) -> str
    normalize_text(text) -> str
    shingles(text, k=3) -> set[str]
    content_key(item) -> str
    load_encoder(cfg) -> callable | None
    StorySpine(state, *, cfg=None, encoder=None)
        .assign(item, *, now) -> dict     the story record view for this item
        .prune(now) -> int
        .downgrades -> list[str]
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit

_STATE_VERSION = 1

# ─────────────────────────────────────────────────────────────────────────────
# Defaults — EVERY ONE IS A CONFIG KEY (charter §8: thresholds are hypotheses,
# never constants). These are the fallbacks a config-less checkout uses.
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "minhash_num_perm": 96,
    "near_dup_threshold": 0.62,
    "shingle_k": 3,
    "semantic_threshold": 0.86,
    "story_ttl_h": 72,
    "max_stories": 1500,
    "max_members_per_story": 40,
    "max_text_chars": 600,
}

# Query parameters that carry no story identity. Stripping them is what makes
# two syndicated copies of one wire story land on the same normalized URL.
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_", "at_", "ns_", "cmpid_")
_TRACKING_KEYS: frozenset[str] = frozenset({
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "dclid", "twclid",
    "mc_cid", "mc_eid", "igshid", "ref", "ref_src", "ref_url", "referrer",
    "src", "source", "cmp", "cmpid", "icid", "ito", "smid", "partner",
    "yptr", "guccounter", "guce_referrer", "guce_referrer_sig",
    "__twitter_impression", "sh", "share", "spm", "xtor", "cid", "ncid",
})
# Twitter/X strips story identity through `s` and `t`; elsewhere those letters
# can be meaningful (e.g. `?s=AAPL`), so they are host-scoped.
_X_HOSTS: frozenset[str] = frozenset({"twitter.com", "x.com", "mobile.twitter.com"})
_X_TRACKING_KEYS: frozenset[str] = frozenset({"s", "t"})

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_AMP_SUFFIX_RE = re.compile(r"/(amp|amp\.html|amp/?)$")

# Emitted once per process, per notice slug.
_NOTICED: set[str] = set()


def _notice(slug: str, message: str) -> str:
    """Print a start-of-line downgrade notice ONCE per process; return it.

    House law (CLAUDE.md): GitHub annotations must START the line and go through
    a bare ``print(..., flush=True)``. Every builder here logs with a prefixing
    formatter, so a logger call would emit ``INFO ::notice ...`` and GitHub would
    silently drop it — the call would review as an alarm and produce nothing.
    """
    text = f"::notice title={slug}::{message}"
    if slug not in _NOTICED:
        _NOTICED.add(slug)
        print(text, flush=True)
    return text


def _cfg(cfg: dict | None, key: str) -> Any:
    if isinstance(cfg, dict) and key in cfg:
        return cfg[key]
    return _DEFAULTS[key]


# ─────────────────────────────────────────────────────────────────────────────
# Normalization (pure)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_url(url: object) -> str:
    """Canonical, identity-bearing form of a URL. "" when there is nothing left.

    Scheme is DROPPED (http/https are one story), `www.` and default ports are
    stripped, the fragment is dropped, tracking parameters are removed, the
    remaining query is sorted, an AMP suffix is folded, and a trailing slash is
    trimmed. The result is a bare ``host/path?query`` string.
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""

    path = parts.path or ""
    path = _AMP_SUFFIX_RE.sub("", path)
    if len(path) > 1:
        path = path.rstrip("/")

    drop_st = host in _X_HOSTS
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        low = key.lower()
        if low in _TRACKING_KEYS:
            continue
        if drop_st and low in _X_TRACKING_KEYS:
            continue
        if any(low.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        kept.append((low, value))
    query = urlencode(sorted(kept))

    out = f"{host}{path}"
    if query:
        out = f"{out}?{query}"
    return out


def normalize_text(text: object) -> str:
    """Lowercased, punctuation-free, whitespace-collapsed form of a string."""
    s = str(text or "").lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def shingles(text: object, k: int = 3) -> set[str]:
    """Word k-shingles of `text` (the MinHash input set)."""
    tokens = normalize_text(text).split()
    if not tokens:
        return set()
    if len(tokens) <= k:
        return {" ".join(tokens)}
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def content_key(item: dict) -> str:
    """The EXACT identity key for a feed item.

    Precedence mirrors the lane's own mirror-collapse rule (press_lane._emission_key):
    a Truth status id is the same post however many mirrors carried it; then the
    normalized URL; then a normalized-headline hash for items with neither
    (twitterapi.io relays whose URL is per-tweet).
    """
    tsid = str(item.get("truth_status_id", "") or "").strip()
    if tsid:
        return f"truth:{tsid}"
    url = normalize_url(item.get("url"))
    if url:
        return f"url:{url}"
    head = normalize_text(item.get("headline"))
    if head:
        return "head:" + hashlib.sha1(head.encode("utf-8")).hexdigest()[:20]
    return "id:" + str(item.get("id", ""))


def _item_text(item: dict, max_chars: int) -> str:
    head = str(item.get("headline", "") or "")
    body = str(item.get("body_snippet", "") or "")
    return f"{head} {body}"[:max_chars]


def _source_key(item: dict) -> str:
    """Identity used to count INDEPENDENT sources — same rule as press_lane."""
    return str(item.get("x_handle") or item.get("source") or "")


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _parse_iso(value: object) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Optional near-dup backend (datasketch)
# ─────────────────────────────────────────────────────────────────────────────

class _MinHashBackend:
    """MinHash-LSH over story signatures. Inert (``available=False``) without datasketch.

    Two datasketch facts this class exists to absorb:

    * **Permutation scheme.** datasketch 2.0 refuses to rebuild a MinHash from
      raw ``hashvalues`` unless the caller names the scheme those values came
      from, and it refuses to compare two MinHashes built under different
      schemes. Signatures are therefore persisted WITH their scheme, and a
      signature written under a different scheme is treated as absent rather
      than silently mis-compared. (1.x has no ``scheme`` kwarg at all, so the
      rebuild falls back for it.)
    * **Band-parameter feasibility.** ``MinHashLSH`` raises for threshold /
      num_perm pairs it cannot band (e.g. 0.99 at 96 permutations). That must be
      a DOWNGRADE, not a crash inside the press tick — a config value nobody can
      satisfy should cost the near-dup pass, not the wire.
    """

    def __init__(self, *, num_perm: int, threshold: float) -> None:
        self.num_perm = int(num_perm)
        self.threshold = float(threshold)
        self.available = False
        self.downgrade = ""
        self.scheme = ""
        self._lsh = None
        self._minhash_cls = None
        self._np = None
        try:  # noqa: PLC0415 — optional dependency probe, deliberately lazy
            from datasketch import MinHash, MinHashLSH
            import numpy as np
        except Exception as exc:  # noqa: BLE001
            self.downgrade = _notice(
                "story-spine-no-datasketch",
                "datasketch unavailable "
                f"({type(exc).__name__}) — near-dup pass disabled; story identity "
                "falls back to exact/normalized-URL keys only",
            )
            return
        try:
            probe = MinHash(num_perm=self.num_perm)
            self.scheme = str(getattr(probe, "scheme", "") or "")
            self._lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        except Exception as exc:  # noqa: BLE001
            self.downgrade = _notice(
                "story-spine-lsh-unbuildable",
                f"MinHashLSH(threshold={self.threshold}, num_perm={self.num_perm}) "
                f"rejected ({type(exc).__name__}: {exc}) — near-dup pass disabled; "
                "pick a feasible near_dup_threshold/minhash_num_perm pair",
            )
            return
        self._minhash_cls = MinHash
        self._np = np
        self.available = True

    # -- signature helpers ----------------------------------------------------

    def signature(self, text: str, k: int) -> list[int] | None:
        """Persistable MinHash signature for `text`, or None when unavailable."""
        if not self.available:
            return None
        grams = shingles(text, k)
        if not grams:
            return None
        mh = self._minhash_cls(num_perm=self.num_perm)
        for gram in grams:
            mh.update(gram.encode("utf-8"))
        return [int(v) for v in mh.hashvalues]

    def _rehydrate(self, values: Iterable[int]):
        arr = self._np.array(list(values), dtype=self._np.uint64)
        if self.scheme:
            try:
                return self._minhash_cls(num_perm=self.num_perm, hashvalues=arr,
                                         scheme=self.scheme)
            except TypeError:
                pass  # datasketch < 2.0 — no scheme kwarg, values are comparable
        return self._minhash_cls(num_perm=self.num_perm, hashvalues=arr)

    def index(self, story_id: str, values: Iterable[int]) -> None:
        if not self.available:
            return
        try:
            mh = self._rehydrate(values)
            if story_id in self._lsh:
                self._lsh.remove(story_id)
            self._lsh.insert(story_id, mh)
        except Exception as exc:  # noqa: BLE001
            _notice("story-spine-lsh-index",
                    f"LSH index rejected {story_id}: {type(exc).__name__}")

    def drop(self, story_id: str) -> None:
        if not self.available:
            return
        try:
            if story_id in self._lsh:
                self._lsh.remove(story_id)
        except Exception:  # noqa: BLE001
            pass

    def query(self, values: Iterable[int]) -> list[str]:
        if not self.available:
            return []
        try:
            return [str(k) for k in self._lsh.query(self._rehydrate(values))]
        except Exception:  # noqa: BLE001
            return []

    def jaccard(self, a: Iterable[int], b: Iterable[int]) -> float:
        if not self.available:
            return 0.0
        try:
            return float(self._rehydrate(a).jaccard(self._rehydrate(b)))
        except Exception:  # noqa: BLE001
            return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Optional semantic backend (Model2Vec static embeddings)
# ─────────────────────────────────────────────────────────────────────────────

def load_encoder(cfg: dict | None, *, root: Path | str | None = None) -> Callable[[list[str]], list[list[float]]] | None:
    """Return a text->vectors callable, or None when the semantic pass is off.

    THE PASS IS OFF BY DEFAULT and can only turn on when BOTH hold:
      1. ``cfg["enabled"]`` is true, and
      2. ``cfg["model_path"]`` names a directory that EXISTS on this host.

    There is no hub id, no fallback name and no download — an absent artifact is
    "pass disabled". The artifact is placed by an explicit operator/R2 step
    (docs/scoring_brain.md §3), never by a render/nightly/daemon path.
    """
    cfg = cfg or {}
    if not bool(cfg.get("enabled", False)):
        return None
    raw_path = str(cfg.get("model_path", "") or "").strip()
    if not raw_path:
        _notice("story-spine-no-model-path",
                "semantic pass enabled but no model_path configured — pass disabled")
        return None
    path = Path(raw_path)
    if not path.is_absolute() and root is not None:
        path = Path(root) / path
    if not path.exists():
        _notice("story-spine-no-model-artifact",
                f"Model2Vec artifact absent at {path} — semantic pass disabled "
                "(fetch is an operator/R2 step; never a runtime download)")
        return None
    try:  # noqa: PLC0415 — optional dependency probe, deliberately lazy
        from model2vec import StaticModel
    except Exception as exc:  # noqa: BLE001
        _notice("story-spine-no-model2vec",
                f"model2vec unavailable ({type(exc).__name__}) — semantic pass disabled")
        return None
    try:
        model = StaticModel.from_pretrained(str(path))
    except Exception as exc:  # noqa: BLE001
        _notice("story-spine-model-load-failed",
                f"Model2Vec load failed ({type(exc).__name__}) — semantic pass disabled")
        return None

    def _encode(texts: list[str]) -> list[list[float]]:
        vectors = model.encode(texts)
        return [[float(x) for x in row] for row in vectors]

    return _encode


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two plain float lists (no numpy required)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


# ─────────────────────────────────────────────────────────────────────────────
# The spine
# ─────────────────────────────────────────────────────────────────────────────

class StorySpine:
    """Incremental story clustering over a mutable, JSON-persistable state dict.

    The clustering rule is greedy single-link nearest-neighbour against the live
    story set: an item joins the most similar story above threshold, else it
    opens one. That IS incremental DBSCAN at ``min_samples=1`` — the batch
    HDBSCAN the masterplan sketches needs the whole corpus in memory at once,
    which a 120-second VPS tick does not have and does not need.
    """

    def __init__(self, state: dict | None, *, cfg: dict | None = None,
                 encoder: Callable[[list[str]], list[list[float]]] | None = None) -> None:
        self.cfg = cfg or {}
        self.state = state if isinstance(state, dict) else {}
        self.state.setdefault("version", _STATE_VERSION)
        self.stories: dict[str, dict] = self.state.setdefault("stories", {})
        self.keys: dict[str, str] = self.state.setdefault("keys", {})

        self.num_perm = int(_cfg(self.cfg, "minhash_num_perm"))
        self.near_dup_threshold = float(_cfg(self.cfg, "near_dup_threshold"))
        self.shingle_k = int(_cfg(self.cfg, "shingle_k"))
        self.semantic_threshold = float(_cfg(self.cfg, "semantic_threshold"))
        self.ttl_h = float(_cfg(self.cfg, "story_ttl_h"))
        self.max_stories = int(_cfg(self.cfg, "max_stories"))
        self.max_members = int(_cfg(self.cfg, "max_members_per_story"))
        self.max_text_chars = int(_cfg(self.cfg, "max_text_chars"))

        self.encoder = encoder
        self.downgrades: list[str] = []

        self._backend = _MinHashBackend(num_perm=self.num_perm,
                                        threshold=self.near_dup_threshold)
        if self._backend.downgrade:
            self.downgrades.append(self._backend.downgrade)
        if self.encoder is None:
            self.downgrades.append(
                "semantic pass disabled (no encoder — see load_encoder)"
            )

        # Rebuild the LSH index from persisted signatures. O(live stories) per
        # construction; the story set is TTL-pruned and hard-capped so this stays
        # a few thousand cheap band hashes, not a growing cost.
        if self._backend.available:
            for sid, rec in self.stories.items():
                if self._comparable(rec):
                    self._backend.index(sid, rec["signature"])

    def _comparable(self, rec: dict) -> bool:
        """True when a persisted signature can be compared to a fresh one.

        A signature written under a different permutation scheme (an upgraded
        datasketch, a changed num_perm) is NOT comparable. Treating it as absent
        loses one story's near-dup coverage until its TTL rolls; treating it as
        comparable would produce a silently wrong similarity.
        """
        sig = rec.get("signature")
        if not sig or len(sig) != self._backend.num_perm:
            return False
        return str(rec.get("signature_scheme", "")) == self._backend.scheme

    # -- properties -----------------------------------------------------------

    @property
    def near_dup_enabled(self) -> bool:
        return self._backend.available

    @property
    def semantic_enabled(self) -> bool:
        return self.encoder is not None

    # -- assignment -----------------------------------------------------------

    def assign(self, item: dict, *, now: datetime) -> dict:
        """Assign `item` to a story, creating one when nothing matches.

        Returns a READ-ONLY VIEW of the story record (a fresh dict) carrying the
        four pinned fields plus the derived counts the L1 features consume.
        Never raises: every optional path is guarded, because this runs inside
        the live wire tick and a clustering failure must not stop an emission.
        """
        try:
            return self._assign(item, now=now)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=story-spine-assign-failed::"
                  f"{item.get('id', '')}: {type(exc).__name__}: {exc}", flush=True)
            return {
                "story_id": "",
                "match": "error",
                "first_seen": _iso(now),
                "source_count": 1,
                "sources_15m": 1,
                "sources_60m": 1,
                "tier_mix": {},
                "observed_engagement": {},
                "member_count": 1,
                "is_new": True,
            }

    def _assign(self, item: dict, *, now: datetime) -> dict:
        key = content_key(item)
        text = _item_text(item, self.max_text_chars)
        signature = self._backend.signature(text, self.shingle_k)
        vector = self._encode_one(text)

        match = "exact"
        sid = self.keys.get(key)
        if sid is not None and sid not in self.stories:
            sid = None
        if sid is None:
            sid, match = self._nearest(signature, vector)
        if sid is None:
            sid = self._new_story_id(key, now)
            match = "new"
            self.stories[sid] = {
                "story_id": sid,
                "first_seen": _iso(now),
                "last_seen": _iso(now),
                "headline": str(item.get("headline", "") or "")[:200],
                "sources": {},
                "tier_mix": {},
                "members": [],
                "observed_engagement": {"likes": 0, "retweets": 0, "replies": 0,
                                        "views": 0, "samples": 0},
            }
            if signature:
                self.stories[sid]["signature"] = signature
                self.stories[sid]["signature_scheme"] = self._backend.scheme
                self._backend.index(sid, signature)
            if vector:
                self.stories[sid]["vector"] = vector

        rec = self.stories[sid]
        self.keys[key] = sid
        self._absorb(rec, item, now=now)
        view = self.view(sid, now=now)
        view["match"] = match
        view["is_new"] = match == "new"
        return view

    def _new_story_id(self, key: str, now: datetime) -> str:
        raw = f"{key}|{_iso(now)}"
        return "st-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _encode_one(self, text: str) -> list[float]:
        if self.encoder is None or not text.strip():
            return []
        try:
            vectors = self.encoder([text])
        except Exception as exc:  # noqa: BLE001
            _notice("story-spine-encode-failed",
                    f"semantic encode failed ({type(exc).__name__}) — pass disabled for this tick")
            return []
        if not vectors:
            return []
        return [float(x) for x in vectors[0]]

    def _nearest(self, signature: list[int] | None,
                 vector: list[float]) -> tuple[str | None, str]:
        """Best story above threshold: MinHash first, then the semantic pass."""
        if signature:
            best_id: str | None = None
            best_score = 0.0
            for cand in self._backend.query(signature):
                rec = self.stories.get(cand)
                if not rec or not self._comparable(rec):
                    continue
                score = self._backend.jaccard(signature, rec["signature"])
                if score >= self.near_dup_threshold and score > best_score:
                    best_id, best_score = cand, score
            if best_id is not None:
                return best_id, "near_dup"

        if vector:
            best_id = None
            best_score = 0.0
            for sid, rec in self.stories.items():
                other = rec.get("vector")
                if not other:
                    continue
                score = cosine(vector, other)
                if score >= self.semantic_threshold and score > best_score:
                    best_id, best_score = sid, score
            if best_id is not None:
                return best_id, "semantic"

        return None, "new"

    def _absorb(self, rec: dict, item: dict, *, now: datetime) -> None:
        rec["last_seen"] = _iso(now)
        src = _source_key(item)
        sources = rec.setdefault("sources", {})
        if src and src not in sources:
            sources[src] = _iso(now)
        tier = str(item.get("source_tier", "") or "unknown")
        mix = rec.setdefault("tier_mix", {})
        mix[tier] = int(mix.get(tier, 0)) + 1
        members = rec.setdefault("members", [])
        iid = str(item.get("id", ""))
        if iid and iid not in members:
            members.append(iid)
            del members[:-self.max_members]
        self._absorb_engagement(rec, item)

    @staticmethod
    def _absorb_engagement(rec: dict, item: dict) -> None:
        """Fold observed engagement into the story record.

        The ONLY source is ``item["x_engagement"]``, which the existing
        twitterapi.io poller already receives in the SAME response body it
        already pays for (press_providers.parse_tweets). No new request, no new
        endpoint, no new spend path — and no first-party X scraping, ever.
        """
        eng = item.get("x_engagement")
        if not isinstance(eng, dict):
            return
        obs = rec.setdefault("observed_engagement",
                             {"likes": 0, "retweets": 0, "replies": 0,
                              "views": 0, "samples": 0})
        for field in ("likes", "retweets", "replies", "views"):
            try:
                obs[field] = int(obs.get(field, 0)) + int(eng.get(field, 0) or 0)
            except (TypeError, ValueError):
                continue
        obs["samples"] = int(obs.get("samples", 0)) + 1

    # -- views ----------------------------------------------------------------

    def view(self, story_id: str, *, now: datetime) -> dict:
        """Derived, JSON-safe view of a story record."""
        rec = self.stories.get(story_id) or {}
        sources: dict = rec.get("sources") or {}
        return {
            "story_id": story_id,
            "first_seen": rec.get("first_seen", ""),
            "last_seen": rec.get("last_seen", ""),
            "source_count": len(sources),
            "sources_15m": self._sources_within(sources, now, 15 * 60),
            "sources_60m": self._sources_within(sources, now, 60 * 60),
            "tier_mix": dict(rec.get("tier_mix") or {}),
            "observed_engagement": dict(rec.get("observed_engagement") or {}),
            "member_count": len(rec.get("members") or []),
        }

    @staticmethod
    def _sources_within(sources: dict, now: datetime, window_s: int) -> int:
        """Distinct sources whose FIRST sighting is inside the window.

        This is the corroboration-velocity numerator: how many INDEPENDENT
        surfaces carried the story in the last N minutes, which is the ≥2-source
        law's own evidence expressed as a rate.
        """
        cutoff = now.astimezone(timezone.utc) - timedelta(seconds=window_s)
        count = 0
        for ts in sources.values():
            dt = _parse_iso(ts)
            if dt is not None and dt >= cutoff:
                count += 1
        return count

    # -- maintenance ----------------------------------------------------------

    def prune(self, now: datetime) -> int:
        """Drop stories past the TTL and trim to max_stories. Returns #dropped."""
        cutoff = now.astimezone(timezone.utc) - timedelta(hours=self.ttl_h)
        dead = [
            sid for sid, rec in self.stories.items()
            if (_parse_iso(rec.get("last_seen")) or cutoff) < cutoff
        ]
        for sid in dead:
            self._drop(sid)

        if len(self.stories) > self.max_stories:
            ordered = sorted(
                self.stories.items(),
                key=lambda kv: str(kv[1].get("last_seen", "")),
            )
            for sid, _ in ordered[: len(self.stories) - self.max_stories]:
                self._drop(sid)
                dead.append(sid)

        if dead:
            gone = set(dead)
            for key in [k for k, v in self.keys.items() if v in gone]:
                del self.keys[key]
        return len(dead)

    def _drop(self, sid: str) -> None:
        self.stories.pop(sid, None)
        self._backend.drop(sid)
