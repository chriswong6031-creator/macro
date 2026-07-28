"""engine.marketing.signal_features — L1 deterministic features (XG-W5 / IS-W2).

Six features, all deterministic, all computed from observable state, all landing
in the scored item's ``_components`` so any ordering decision is auditable and
re-weightable WITHOUT re-polling anything:

    corroboration_velocity  distinct independent sources per story per 15/60 min
                            (the ≥2-source law's own evidence, as a rate)
    keyword_heat            Kleinberg-lite burst z-score on our OWN ingest terms
    novelty                 temporal-IDF against the trailing 30-day corpus
    source_authority        per-source prior from OBSERVED engagement
    tone_extremity          GDELT V2Tone join where the story matches
    headline_shape          numbers present, entity count, length band

NO LLM ANYWHERE. DO_NOT_REBUILD: "LLM-originated signals, scores, or escalations
— FORBIDDEN". Every number below comes from arithmetic over counted events.

MARKETING-INTERNAL, DISPLAY-TIER. None of these features is a market signal and
none is ever rendered to a user; they order an internal wire queue.

HONEST NULLS (house epistemics law: nulls printed, not hidden). Three features
have a real "we do not know yet" state, and each SAYS SO in its detail block
rather than dressing a default up as a measurement:

    novelty          -> "cold-start" until the corpus holds `min_docs` documents;
                        value is the configured neutral, not a computed IDF.
    source_authority -> "neutral-prior" until a source has `min_samples`
                        engagement observations. THERE IS NO TELEMETRY YET, so on
                        day one EVERY source is neutral and this feature is inert
                        by construction — that is the documented, intended state,
                        not a bug (masterplan §3: the label loop accrues it).
    tone_extremity   -> "absent" whenever no GDELT tone join exists for the story.
                        There is no GDELT provider in the marketing lane today, so
                        this is the standing state; an absent join contributes
                        EXACTLY 0 and never renormalizes the other weights, so it
                        is rank-neutral across a corpus with no tone at all.

STATE. `SignalCorpus` and `AuthorityStore` wrap mutable JSON-persistable dicts
owned by the press daemon (data/marketing/press/state.json — GITIGNORED host
state). Zero repo writes; the nightly stays the sole advancer of tracked ledgers.

Public API:
    SignalCorpus(state, *, cfg=None)  .observe/.novelty/.keyword_heat/.prune
    AuthorityStore(state, *, cfg=None) .observe/.prior
    load_tone_lookup(root, *, cfg=None) -> dict
    tone_extremity(item, lookup, *, cfg=None) -> tuple[float, dict]
    headline_shape(item, *, matched=None, cfg=None) -> tuple[float, dict]
    compute_features(...) -> dict     {"values": {...}, "detail": {...}}
    rank_score(salience, values, *, cfg=None) -> tuple[float, dict]
    FEATURE_NAMES
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

FEATURE_NAMES: tuple[str, ...] = (
    "corroboration_velocity",
    "keyword_heat",
    "novelty",
    "source_authority",
    "tone_extremity",
    "headline_shape",
)

SCORING_VERSION = "xg-w5.1"

# ─────────────────────────────────────────────────────────────────────────────
# Defaults — EVERY ONE IS A CONFIG KEY (charter §8: "everything below ships as a
# config key with a pre-registered evaluation plan, not a constant").
# ─────────────────────────────────────────────────────────────────────────────

_CORROBORATION_DEFAULTS: dict[str, Any] = {
    "sources_15m_full": 3,
    "sources_60m_full": 5,
    "weight_15m": 0.7,
    "weight_60m": 0.3,
}

_CORPUS_DEFAULTS: dict[str, Any] = {
    "max_tokens_per_item": 12,
    "max_tokens_per_bucket": 2000,
    "burst_window_h": 72,
    "burst_recent_h": 1,
    "burst_min_hours": 6,
    "burst_min_std": 0.5,
    "burst_z_cap": 4.0,
    "novelty_window_d": 30,
    "novelty_min_docs": 50,
    "novelty_top_k": 3,
    "novelty_neutral": 0.5,
    "min_token_len": 3,
}

_AUTHORITY_DEFAULTS: dict[str, Any] = {
    "min_samples": 25,
    "neutral_prior": 0.5,
    "ewma_alpha": 0.1,
    "reference_engagement": 500.0,
    "like_weight": 1.0,
    "retweet_weight": 2.0,
    "reply_weight": 0.5,
    "view_weight": 0.01,
    "max_sources": 500,
}

_TONE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "tone_cap": 10.0,
    "paths": ("data/marketing/press/gdelt_tone.json",),
}

_SHAPE_DEFAULTS: dict[str, Any] = {
    "numbers_full": 2,
    "entities_full": 3,
    "short_max_chars": 50,
    "long_min_chars": 110,
    "band_short": 0.5,
    "band_medium": 1.0,
    "band_long": 0.6,
    "w_numbers": 0.4,
    "w_entities": 0.35,
    "w_band": 0.25,
}

# Rank weights. SALIENCE STAYS DOMINANT BY DESIGN: the L1 layer is a refinement
# of the existing deterministic salience, not a replacement for it, and no weight
# here is load-bearing until the golden-set precision@20 ranks it (charter §8).
_RANK_WEIGHT_DEFAULTS: dict[str, float] = {
    "salience": 0.50,
    "corroboration_velocity": 0.14,
    "keyword_heat": 0.10,
    "novelty": 0.08,
    "source_authority": 0.08,
    "tone_extremity": 0.04,
    "headline_shape": 0.06,
}

_TOKEN_RE = re.compile(r"[a-z0-9$%\.]+")
_NUMBER_RE = re.compile(r"(?<!\w)[-+$]?\d[\d,\.]*%?")
_CAPS_RUN_RE = re.compile(r"(?<!^)(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[A-Z]{2,})")

_STOPWORDS: frozenset[str] = frozenset("""
a an and are as at be been but by for from had has have he her his how i if in
into is it its of on or our out over said says she that the their them then
there these they this to up was we were what when where which who will with
you your after before more most new news over under after amid says say told
report reports reported breaking update updates live latest
""".split())


def _get(cfg: dict | None, key: str, defaults: dict[str, Any]) -> Any:
    if isinstance(cfg, dict) and key in cfg and cfg[key] is not None:
        return cfg[key]
    return defaults[key]


def _clamp01(value: float) -> float:
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _hour_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def _day_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d")


def tokenize(text: object, *, min_len: int = 3) -> list[str]:
    """Content tokens: lowercase, stopword-free, deduped, order preserved."""
    lowered = str(text or "").lower()
    seen: set[str] = set()
    out: list[str] = []
    for tok in _TOKEN_RE.findall(lowered):
        tok = tok.strip(".")
        if len(tok) < min_len or tok in _STOPWORDS or tok in seen:
            continue
        if tok.isdigit():
            continue
        seen.add(tok)
        out.append(tok)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# corroboration_velocity
# ─────────────────────────────────────────────────────────────────────────────

def corroboration_velocity(story: dict | None, *,
                           cfg: dict | None = None) -> tuple[float, dict]:
    """Distinct independent sources per story per 15/60 min, squashed to [0,1].

    The masterplan's "Techmeme insight": how fast a claim spreads across
    INDEPENDENT surfaces is the cheapest honest proxy for whether it is real and
    whether it matters. A single-source story scores 0 — which is also exactly
    what the corroboration GATE says about it, independently.
    """
    if not isinstance(story, dict):
        return 0.0, {"state": "no-story", "sources_15m": 0, "sources_60m": 0}
    n15 = int(story.get("sources_15m", 0) or 0)
    n60 = int(story.get("sources_60m", 0) or 0)
    full15 = max(2, int(_get(cfg, "sources_15m_full", _CORROBORATION_DEFAULTS)))
    full60 = max(2, int(_get(cfg, "sources_60m_full", _CORROBORATION_DEFAULTS)))
    w15 = float(_get(cfg, "weight_15m", _CORROBORATION_DEFAULTS))
    w60 = float(_get(cfg, "weight_60m", _CORROBORATION_DEFAULTS))

    v15 = _clamp01((n15 - 1) / (full15 - 1))
    v60 = _clamp01((n60 - 1) / (full60 - 1))
    value = _clamp01(v15 * w15 + v60 * w60)
    return value, {
        "state": "observed",
        "sources_15m": n15,
        "sources_60m": n60,
        "source_count": int(story.get("source_count", 0) or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# The trailing corpus — novelty (temporal-IDF) + keyword_heat (Kleinberg-lite)
# ─────────────────────────────────────────────────────────────────────────────

class SignalCorpus:
    """Rolling token/document counts over our OWN ingest stream.

    Two granularities, because the two features want different clocks:
      hours[HH]  -> burst detection (keyword_heat) over `burst_window_h` hours
      days[DD]   -> document frequency (novelty) over `novelty_window_d` days

    Both are bounded: buckets expire on prune, and each bucket keeps only its
    top `max_tokens_per_bucket` tokens, so the persisted state cannot grow
    without limit on a busy news day.
    """

    def __init__(self, state: dict | None, *, cfg: dict | None = None) -> None:
        self.cfg = cfg or {}
        self.state = state if isinstance(state, dict) else {}
        self.state.setdefault("version", 1)
        self.hours: dict[str, dict] = self.state.setdefault("hours", {})
        self.days: dict[str, dict] = self.state.setdefault("days", {})
        self.min_token_len = int(_get(self.cfg, "min_token_len", _CORPUS_DEFAULTS))
        self.max_tokens_per_item = int(_get(self.cfg, "max_tokens_per_item", _CORPUS_DEFAULTS))

    # -- ingest ---------------------------------------------------------------

    def item_tokens(self, item: dict) -> list[str]:
        text = f"{item.get('headline', '')} {str(item.get('body_snippet', '') or '')[:240]}"
        return tokenize(text, min_len=self.min_token_len)[: self.max_tokens_per_item]

    def observe(self, item: dict, *, now: datetime) -> list[str]:
        """Record one document. Returns the tokens recorded."""
        tokens = self.item_tokens(item)
        hkey = _hour_key(now)
        dkey = _day_key(now)
        hbucket = self.hours.setdefault(hkey, {"docs": 0, "tokens": {}})
        dbucket = self.days.setdefault(dkey, {"docs": 0, "tokens": {}})
        hbucket["docs"] = int(hbucket.get("docs", 0)) + 1
        dbucket["docs"] = int(dbucket.get("docs", 0)) + 1
        for tok in tokens:
            hbucket["tokens"][tok] = int(hbucket["tokens"].get(tok, 0)) + 1
            dbucket["tokens"][tok] = int(dbucket["tokens"].get(tok, 0)) + 1
        return tokens

    # -- novelty --------------------------------------------------------------

    def total_docs(self) -> int:
        return sum(int(b.get("docs", 0)) for b in self.days.values())

    def document_frequency(self, token: str) -> int:
        return sum(int(b.get("tokens", {}).get(token, 0)) for b in self.days.values())

    def novelty(self, item: dict, *, exclude_self: bool = True) -> tuple[float, dict]:
        """Temporal-IDF novelty against the trailing corpus (arXiv 1401.1456 shape).

        Mean IDF of the item's top-k rarest content tokens, normalized by the
        corpus's own maximum attainable IDF so the value stays in [0,1] as the
        corpus grows. `exclude_self` removes the item's own contribution, which
        matters enormously on a small corpus and not at all on a large one.
        """
        min_docs = int(_get(self.cfg, "novelty_min_docs", _CORPUS_DEFAULTS))
        neutral = float(_get(self.cfg, "novelty_neutral", _CORPUS_DEFAULTS))
        total = self.total_docs() - (1 if exclude_self else 0)
        if total < min_docs:
            return neutral, {
                "state": "cold-start",
                "corpus_docs": max(0, total),
                "min_docs": min_docs,
                "note": "corpus below min_docs — neutral value, NOT a measurement",
            }

        tokens = self.item_tokens(item)
        if not tokens:
            return neutral, {"state": "no-tokens", "corpus_docs": total}

        max_idf = math.log((total + 1.0) / 1.0)
        idfs = []
        for tok in tokens:
            df = self.document_frequency(tok) - (1 if exclude_self else 0)
            df = max(0, df)
            idfs.append(math.log((total + 1.0) / (df + 1.0)))
        idfs.sort(reverse=True)
        top_k = max(1, int(_get(self.cfg, "novelty_top_k", _CORPUS_DEFAULTS)))
        top = idfs[:top_k]
        value = _clamp01((sum(top) / len(top)) / max_idf) if max_idf > 0 else neutral
        return value, {
            "state": "observed",
            "corpus_docs": total,
            "tokens_scored": len(idfs),
            "top_idf": round(top[0], 4) if top else 0.0,
        }

    # -- keyword_heat ---------------------------------------------------------

    def _hour_keys_desc(self) -> list[str]:
        return sorted(self.hours.keys(), reverse=True)

    def burst_z(self, token: str, *, now: datetime) -> tuple[float, dict]:
        """Kleinberg-lite burst score for one token.

        Kleinberg's burst automaton is an infinite-state HMM over inter-arrival
        gaps; both PyPI implementations of it are dead, and the full machine is
        far more than a 120-second wire tick needs. This is the two-state
        reduction the masterplan asks for: compare the token's arrival RATE in
        the recent hour(s) against its own rate distribution over the trailing
        window, and call the high state when the z-score clears a threshold.
        Rates (not raw counts) are compared, so a busy news hour does not read as
        a burst for every token in it.
        """
        recent_h = max(1, int(_get(self.cfg, "burst_recent_h", _CORPUS_DEFAULTS)))
        min_hours = int(_get(self.cfg, "burst_min_hours", _CORPUS_DEFAULTS))
        min_std = float(_get(self.cfg, "burst_min_std", _CORPUS_DEFAULTS))

        keys = self._hour_keys_desc()
        if len(keys) < max(2, min_hours):
            return 0.0, {"state": "cold-start", "hours": len(keys),
                         "min_hours": min_hours}

        recent_keys = keys[:recent_h]
        base_keys = keys[recent_h:]
        if not base_keys:
            return 0.0, {"state": "cold-start", "hours": len(keys),
                         "min_hours": min_hours}

        def _rate(hkey: str) -> float:
            bucket = self.hours.get(hkey) or {}
            docs = int(bucket.get("docs", 0))
            if docs <= 0:
                return 0.0
            return int(bucket.get("tokens", {}).get(token, 0)) / docs

        recent_rate = sum(_rate(k) for k in recent_keys) / len(recent_keys)
        base_rates = [_rate(k) for k in base_keys]
        mean = sum(base_rates) / len(base_rates)
        var = sum((r - mean) ** 2 for r in base_rates) / len(base_rates)
        std = math.sqrt(var)
        z = (recent_rate - mean) / max(std, min_std)
        return z, {
            "state": "observed",
            "recent_rate": round(recent_rate, 5),
            "baseline_mean": round(mean, 5),
            "baseline_std": round(std, 5),
            "baseline_hours": len(base_keys),
        }

    def keyword_heat(self, item: dict, *, now: datetime) -> tuple[float, dict]:
        """Hottest burst among the item's own tokens, squashed to [0,1]."""
        tokens = self.item_tokens(item)
        if not tokens:
            return 0.0, {"state": "no-tokens"}
        z_cap = float(_get(self.cfg, "burst_z_cap", _CORPUS_DEFAULTS))
        best_z: float | None = None
        best_tok = ""
        best_detail: dict = {"state": "cold-start"}
        last_unobserved: dict = {"state": "cold-start"}
        for tok in tokens:
            z, detail = self.burst_z(tok, now=now)
            if detail.get("state") != "observed":
                last_unobserved = detail
                continue
            # `best_z is None` is load-bearing: every token can legitimately score
            # a NEGATIVE z (a quiet hour for a common term), and seeding the best
            # at 0.0 would leave the detail block reporting "cold-start" for a
            # corpus that is anything but — a null state that is a lie.
            if best_z is None or z > best_z:
                best_z, best_tok, best_detail = z, tok, detail
        if best_z is None:
            return 0.0, last_unobserved
        value = _clamp01(best_z / z_cap) if z_cap > 0 else 0.0
        threshold = float(self.cfg.get("burst_z_threshold", 2.0))
        return value, {
            **best_detail,
            "token": best_tok,
            "z": round(best_z, 4),
            "burst": bool(best_z >= threshold),
        }

    # -- maintenance ----------------------------------------------------------

    def prune(self, now: datetime) -> int:
        """Expire old buckets and cap per-bucket token maps. Returns #dropped."""
        window_h = int(_get(self.cfg, "burst_window_h", _CORPUS_DEFAULTS))
        window_d = int(_get(self.cfg, "novelty_window_d", _CORPUS_DEFAULTS))
        cap = int(_get(self.cfg, "max_tokens_per_bucket", _CORPUS_DEFAULTS))
        ref = now.astimezone(timezone.utc)

        h_cutoff = _hour_key(ref - timedelta(hours=window_h))
        d_cutoff = _day_key(ref - timedelta(days=window_d))
        dropped = 0
        for key in [k for k in self.hours if k < h_cutoff]:
            del self.hours[key]
            dropped += 1
        for key in [k for k in self.days if k < d_cutoff]:
            del self.days[key]
            dropped += 1
        for bucket in list(self.hours.values()) + list(self.days.values()):
            tokens = bucket.get("tokens") or {}
            if len(tokens) > cap:
                keep = sorted(tokens.items(), key=lambda kv: kv[1], reverse=True)[:cap]
                bucket["tokens"] = dict(keep)
        return dropped


# ─────────────────────────────────────────────────────────────────────────────
# source_authority
# ─────────────────────────────────────────────────────────────────────────────

class AuthorityStore:
    """Per-source engagement prior. NEUTRAL until telemetry exists.

    THE ONLY INPUT is ``item["x_engagement"]`` — like/retweet/reply/view counts
    that the twitterapi.io poller already receives inside the response body it
    already pays for (press_providers.parse_tweets). No new endpoint, no new
    request, no new spend path, and no first-party X scraping. Sources that never
    carry engagement (RSS wires, mirrors) therefore stay on the neutral prior
    forever, which is the honest answer: we have not measured them.
    """

    def __init__(self, state: dict | None, *, cfg: dict | None = None) -> None:
        self.cfg = cfg or {}
        self.state = state if isinstance(state, dict) else {}
        self.state.setdefault("version", 1)
        self.sources: dict[str, dict] = self.state.setdefault("sources", {})

    @staticmethod
    def _key(item: dict) -> str:
        return str(item.get("x_handle") or item.get("source") or "")

    def engagement_score(self, engagement: dict) -> float:
        try:
            return (
                float(engagement.get("likes", 0) or 0) * float(_get(self.cfg, "like_weight", _AUTHORITY_DEFAULTS))
                + float(engagement.get("retweets", 0) or 0) * float(_get(self.cfg, "retweet_weight", _AUTHORITY_DEFAULTS))
                + float(engagement.get("replies", 0) or 0) * float(_get(self.cfg, "reply_weight", _AUTHORITY_DEFAULTS))
                + float(engagement.get("views", 0) or 0) * float(_get(self.cfg, "view_weight", _AUTHORITY_DEFAULTS))
            )
        except (TypeError, ValueError):
            return 0.0

    def observe(self, item: dict, *, now: datetime | None = None) -> bool:
        """Fold one observed-engagement sample. False when the item carries none."""
        engagement = item.get("x_engagement")
        if not isinstance(engagement, dict):
            return False
        key = self._key(item)
        if not key:
            return False
        alpha = float(_get(self.cfg, "ewma_alpha", _AUTHORITY_DEFAULTS))
        rec = self.sources.setdefault(key, {"samples": 0, "ewma": 0.0})
        score = self.engagement_score(engagement)
        samples = int(rec.get("samples", 0))
        rec["ewma"] = score if samples == 0 else (
            alpha * score + (1.0 - alpha) * float(rec.get("ewma", 0.0))
        )
        rec["samples"] = samples + 1
        if now is not None:
            rec["last"] = _iso(now)
        self._trim()
        return True

    def _trim(self) -> None:
        cap = int(_get(self.cfg, "max_sources", _AUTHORITY_DEFAULTS))
        if len(self.sources) <= cap:
            return
        ordered = sorted(self.sources.items(), key=lambda kv: int(kv[1].get("samples", 0)))
        for key, _ in ordered[: len(self.sources) - cap]:
            del self.sources[key]

    def prior(self, item: dict) -> tuple[float, dict]:
        """The source's engagement prior, or the NEUTRAL prior when unmeasured."""
        neutral = float(_get(self.cfg, "neutral_prior", _AUTHORITY_DEFAULTS))
        min_samples = int(_get(self.cfg, "min_samples", _AUTHORITY_DEFAULTS))
        key = self._key(item)
        rec = self.sources.get(key) or {}
        samples = int(rec.get("samples", 0))
        if samples < min_samples:
            return neutral, {
                "state": "neutral-prior",
                "source": key,
                "samples": samples,
                "min_samples": min_samples,
                "note": "no engagement telemetry yet — neutral prior, NOT a measurement",
            }
        reference = float(_get(self.cfg, "reference_engagement", _AUTHORITY_DEFAULTS))
        ewma = max(0.0, float(rec.get("ewma", 0.0)))
        value = _clamp01(math.log1p(ewma) / math.log1p(max(reference, 1.0)))
        return value, {
            "state": "observed",
            "source": key,
            "samples": samples,
            "ewma": round(ewma, 3),
        }


# ─────────────────────────────────────────────────────────────────────────────
# tone_extremity (GDELT V2Tone join)
# ─────────────────────────────────────────────────────────────────────────────

def load_tone_lookup(root: Path | str | None = None, *,
                     cfg: dict | None = None) -> dict:
    """Load an optional local GDELT tone join. {} when nothing is present.

    THERE IS NO GDELT PROVIDER IN THE MARKETING LANE TODAY (IS-W1's provider is
    unbuilt), so {} is the standing state and `tone_extremity` contributes 0 for
    every item — deliberately rank-neutral. When the provider lands it writes
    ``{normalized_url_or_head_key: {"tone": float, ...}}`` to a host-local path;
    nothing here fetches, and nothing here writes.
    """
    cfg = cfg or {}
    if not bool(cfg.get("enabled", True)):
        return {}
    paths = cfg.get("paths") or _TONE_DEFAULTS["paths"]
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute() and root is not None:
            path = Path(root) / path
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken join file must never stop a tick
            continue
        if isinstance(data, dict):
            return data
    return {}


def tone_extremity(item: dict, lookup: dict | None, *,
                   cfg: dict | None = None) -> tuple[float, dict]:
    """|V2Tone| of the matched story, squashed to [0,1]. Absent -> 0-contribution.

    An absent join returns 0.0 WITHOUT renormalizing any other weight: when no
    item has tone, every item loses the identical amount and the ordering is
    untouched; when some do, they gain. That is the "null-safe, absent ->
    0-contribution" rule the wave was chartered with.
    """
    if not lookup:
        return 0.0, {"state": "absent", "note": "no GDELT tone join available"}
    from engine.marketing.story_spine import content_key, normalize_url  # noqa: PLC0415

    candidates = []
    url = normalize_url(item.get("url"))
    if url:
        candidates.append(url)
        candidates.append(f"url:{url}")
    candidates.append(content_key(item))

    row = None
    for key in candidates:
        hit = lookup.get(key)
        if isinstance(hit, dict):
            row = hit
            break
        if isinstance(hit, (int, float)):
            row = {"tone": float(hit)}
            break
    if row is None:
        return 0.0, {"state": "absent", "note": "no tone row matched this story"}

    try:
        tone = float(row.get("tone", 0.0))
    except (TypeError, ValueError):
        return 0.0, {"state": "absent", "note": "tone row unparseable"}
    cap = float(_get(cfg, "tone_cap", _TONE_DEFAULTS))
    value = _clamp01(abs(tone) / cap) if cap > 0 else 0.0
    return value, {"state": "observed", "tone": round(tone, 4), "cap": cap}


# ─────────────────────────────────────────────────────────────────────────────
# headline_shape
# ─────────────────────────────────────────────────────────────────────────────

def headline_shape(item: dict, *, matched: dict | None = None,
                   cfg: dict | None = None) -> tuple[float, dict]:
    """Numbers present, entity count, length band — a pure surface-form feature."""
    headline = str(item.get("headline", "") or "")
    numbers = _NUMBER_RE.findall(headline)
    entities = 0
    if isinstance(matched, dict):
        entities += len(matched.get("tickers") or [])
        entities += len(matched.get("macro_keys") or [])
        entities += len(matched.get("sectors") or [])
    entities += len(_CAPS_RUN_RE.findall(headline))

    chars = len(headline)
    short_max = int(_get(cfg, "short_max_chars", _SHAPE_DEFAULTS))
    long_min = int(_get(cfg, "long_min_chars", _SHAPE_DEFAULTS))
    if chars < short_max:
        band, band_value = "short", float(_get(cfg, "band_short", _SHAPE_DEFAULTS))
    elif chars > long_min:
        band, band_value = "long", float(_get(cfg, "band_long", _SHAPE_DEFAULTS))
    else:
        band, band_value = "medium", float(_get(cfg, "band_medium", _SHAPE_DEFAULTS))

    numbers_full = max(1, int(_get(cfg, "numbers_full", _SHAPE_DEFAULTS)))
    entities_full = max(1, int(_get(cfg, "entities_full", _SHAPE_DEFAULTS)))
    w_numbers = float(_get(cfg, "w_numbers", _SHAPE_DEFAULTS))
    w_entities = float(_get(cfg, "w_entities", _SHAPE_DEFAULTS))
    w_band = float(_get(cfg, "w_band", _SHAPE_DEFAULTS))
    total_w = w_numbers + w_entities + w_band or 1.0

    value = (
        w_numbers * _clamp01(len(numbers) / numbers_full)
        + w_entities * _clamp01(entities / entities_full)
        + w_band * _clamp01(band_value)
    ) / total_w
    return _clamp01(value), {
        "state": "observed",
        "numbers": len(numbers),
        "has_numbers": bool(numbers),
        "entities": entities,
        "chars": chars,
        "length_band": band,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def compute_features(
    item: dict,
    *,
    matched: dict | None = None,
    story: dict | None = None,
    corpus: "SignalCorpus | None" = None,
    authority: "AuthorityStore | None" = None,
    tone_lookup: dict | None = None,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict:
    """Compute all six L1 features. Returns {"values": {...}, "detail": {...}}.

    EVERY feature is present in the output for EVERY item, even when its input is
    missing — a missing input yields a documented state ("cold-start",
    "neutral-prior", "absent", "no-story"), never a silently dropped key. That is
    what makes "features computed for 100% of ingested items" checkable.
    """
    cfg = cfg or {}
    now = now or datetime.now(tz=timezone.utc)
    values: dict[str, float] = {}
    detail: dict[str, dict] = {}

    values["corroboration_velocity"], detail["corroboration_velocity"] = (
        corroboration_velocity(story, cfg=cfg.get("corroboration"))
    )

    if corpus is not None:
        values["keyword_heat"], detail["keyword_heat"] = corpus.keyword_heat(item, now=now)
        values["novelty"], detail["novelty"] = corpus.novelty(item)
    else:
        values["keyword_heat"] = 0.0
        detail["keyword_heat"] = {"state": "no-corpus"}
        values["novelty"] = float(_get(cfg.get("corpus"), "novelty_neutral", _CORPUS_DEFAULTS))
        detail["novelty"] = {"state": "no-corpus"}

    if authority is not None:
        values["source_authority"], detail["source_authority"] = authority.prior(item)
    else:
        values["source_authority"] = float(
            _get(cfg.get("authority"), "neutral_prior", _AUTHORITY_DEFAULTS)
        )
        detail["source_authority"] = {"state": "neutral-prior", "samples": 0}

    values["tone_extremity"], detail["tone_extremity"] = tone_extremity(
        item, tone_lookup, cfg=cfg.get("tone")
    )
    values["headline_shape"], detail["headline_shape"] = headline_shape(
        item, matched=matched, cfg=cfg.get("headline_shape")
    )

    return {"values": values, "detail": detail}


def rank_weights(cfg: dict | None = None) -> dict[str, float]:
    """Merged rank weights (config overrides the defaults key by key)."""
    weights = dict(_RANK_WEIGHT_DEFAULTS)
    raw = (cfg or {}).get("rank_weights")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in weights:
                try:
                    weights[key] = float(value)
                except (TypeError, ValueError):
                    continue
    return weights


def rank_score(salience: float, values: dict[str, float], *,
               cfg: dict | None = None) -> tuple[float, dict]:
    """The ORDERING score. Salience-dominant; every term is inspectable.

    THIS IS AN ORDERING NUMBER AND NOTHING ELSE. It is never compared against a
    publish floor, never fed to the corroboration gate, never fed to the sentinel
    or the language gates, and never surfaced to a user. See press_lane's
    "gate ordering" block for the enforced call order.
    """
    weights = rank_weights(cfg)
    contributions: dict[str, float] = {}
    total = 0.0
    salience_norm = _clamp01(float(salience or 0.0) / 100.0)
    contributions["salience"] = weights["salience"] * salience_norm
    total += contributions["salience"]
    for name in FEATURE_NAMES:
        contribution = weights.get(name, 0.0) * _clamp01(float(values.get(name, 0.0)))
        contributions[name] = contribution
        total += contribution
    return round(_clamp01(total), 6), {
        "weights": weights,
        "contributions": {k: round(v, 6) for k, v in contributions.items()},
        "salience_norm": round(salience_norm, 6),
    }
