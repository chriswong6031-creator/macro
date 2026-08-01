"""engine.chronicle.schema — chronicle.event.v1 field allowlist + validation.

The schema IS the public-safe allowlist (masterplan §0 gate 6): every adapter
projects INTO these exact fields; no field outside this list may ever appear on
an emitted event. ``validate_event`` is called by :func:`new_event` at assembly
time (so a schema violation degrades an adapter to a per-item skip, never a
crash) and again directly by tests/test_chronicle.py as the CI-enforced gate.
"""
from __future__ import annotations

import hashlib
import re

FACT_MAX_LEN = 200
TITLE_MAX_LEN = 400  # defensive cap only — not a masterplan-specified fact cap

# W1: per-adapter SOURCE-field allowlists (beyond this global EVENT_FIELDS
# allowlist) and content-level debranding of third-party report titles are
# real gaps, but a design question for W1 — deferred, not fixed here
# (adversarial review DEFER item, 2026-07-26).
EVENT_FIELDS: tuple[str, ...] = (
    "id", "ts", "date", "source", "source_ref", "kind", "title",
    "facts", "tickers", "themes", "horizon_hint", "weight_hint", "links",
)

LINK_FIELDS: tuple[str, ...] = ("site", "source", "receipt")

SOURCES: tuple[str, ...] = (
    "research_vault", "prophet_ledger", "macro_release",
    "earnings", "earnings_call", "regime_flip", "risk_band",
)
KINDS: tuple[str, ...] = ("report", "signal_close", "print", "earnings", "state_flip")
HORIZONS: tuple[str, ...] = ("short", "medium", "long")

# Deterministic horizon_hint-by-kind mapping (masterplan event schema comment).
HORIZON_BY_KIND: dict[str, str] = {
    "report": "medium",
    "signal_close": "short",
    "print": "short",
    "earnings": "short",
    "state_flip": "medium",
}


def make_id(source: str, source_ref: str, date: str = "") -> str:
    """Stable idempotency key: cev-<source>-<sha256(source|source_ref|date)[:12]>.

    Deterministic given unchanged source data — this is what lets the spine
    fully regenerate events.jsonl on every run and still land on an identical
    file (masterplan §0 gates 1+2).
    """
    h = hashlib.sha256(f"{source}|{source_ref}|{date}".encode("utf-8")).hexdigest()[:12]
    return f"cev-{source}-{h}"


def make_links(site: str | None = None, source: str | None = None,
                receipt: str | None = None) -> dict:
    return {"site": site, "source": source, "receipt": receipt}


_DIGIT_RE = re.compile(r"\d")


def truncate_fact(text: object, max_len: int = FACT_MAX_LEN) -> str | None:
    """Hard-cap a fact string at max_len chars (masterplan third-party-derived-
    events constraint, AM-R4 rev-3) -- truncating on a WORD boundary, never
    mid-token, and never leaving a partial number that reads as a different,
    wrong figure (M5: a naive char-cut can land inside a number, e.g.
    '...surprise 12.5%' -> '...surprise 12.' silently mutates the fact).

    Returns None when nothing meaningful survives the cut (too-short/no safe
    boundary) -- callers must drop the fact rather than ship a mangled stub.
    """
    s = str(text or "").strip()
    if len(s) <= max_len:
        return s
    budget = max_len - 1  # reserve 1 char for the ellipsis
    cut = s[:budget]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else ""
    # Drop a trailing token that contains a digit -- truncation must never
    # leave a partial number looking like a complete one.
    tokens = cut.split(" ") if cut else []
    while tokens and _DIGIT_RE.search(tokens[-1]):
        tokens.pop()
    cut = " ".join(tokens).rstrip(" ,;:·—-")
    if len(cut) < 20:  # too short to be a meaningful fact fragment
        return None
    return cut + "…"


def new_event(
    *,
    id: str,  # noqa: A002 - matches the schema field name
    ts: str,
    date: str,
    source: str,
    source_ref: str,
    kind: str,
    title: str,
    facts: list | None,
    tickers: list | None,
    themes: list | None,
    weight_hint: int,
    links: dict | None = None,
    horizon_hint: str | None = None,
) -> dict:
    """Assemble + validate one chronicle.event.v1 dict.

    Raises ValueError on a schema violation. Callers (adapters) run this inside
    a per-item try/except so a violation degrades to a skipped item + gap note,
    never an adapter-wide crash (fail-soft law).
    """
    ev = {
        "id": id,
        "ts": ts,
        "date": date,
        "source": source,
        "source_ref": source_ref,
        "kind": kind,
        "title": str(title or "").strip()[:TITLE_MAX_LEN],
        # truncate_fact returns None when nothing meaningful survives a
        # word-boundary/digit-safe truncation (M5) -- drop those, never ship
        # a mangled stub.
        "facts": [tf for f in (facts or []) if str(f or "").strip()
                  for tf in (truncate_fact(f),) if tf is not None],
        "tickers": [str(t).strip() for t in (tickers or []) if str(t or "").strip()],
        "themes": [str(t).strip() for t in (themes or []) if str(t or "").strip()],
        "horizon_hint": horizon_hint or HORIZON_BY_KIND.get(kind, "medium"),
        "weight_hint": int(weight_hint),
        "links": links if links is not None else make_links(),
    }
    problems = validate_event(ev)
    if problems:
        raise ValueError(f"event schema violation ({id}): {'; '.join(problems)}")
    return ev


def validate_event(ev: dict) -> list[str]:
    """Return a list of problems with *ev* (empty = schema-clean). Never raises."""
    problems: list[str] = []
    if not isinstance(ev, dict):
        return ["event is not a dict"]

    keys = set(ev.keys())
    allowed = set(EVENT_FIELDS)
    missing = allowed - keys
    extra = keys - allowed
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    if extra:
        problems.append(f"unexpected fields (public-safe violation): {sorted(extra)}")

    if ev.get("source") not in SOURCES:
        problems.append(f"unknown source: {ev.get('source')!r}")
    if ev.get("kind") not in KINDS:
        problems.append(f"unknown kind: {ev.get('kind')!r}")
    if ev.get("horizon_hint") not in HORIZONS:
        problems.append(f"unknown horizon_hint: {ev.get('horizon_hint')!r}")

    wh = ev.get("weight_hint")
    if not isinstance(wh, int) or isinstance(wh, bool) or not (0 <= wh <= 3):
        problems.append(f"weight_hint out of range 0-3: {wh!r}")

    facts = ev.get("facts")
    if not isinstance(facts, list):
        problems.append("facts is not a list")
    else:
        for f in facts:
            if not isinstance(f, str):
                problems.append(f"fact is not a string: {f!r}")
            elif len(f) > FACT_MAX_LEN:
                problems.append(f"fact exceeds {FACT_MAX_LEN} chars: {f[:40]!r}...")

    if not isinstance(ev.get("tickers"), list):
        problems.append("tickers is not a list")
    if not isinstance(ev.get("themes"), list):
        problems.append("themes is not a list")

    links = ev.get("links")
    if not isinstance(links, dict) or set(links.keys()) != set(LINK_FIELDS):
        problems.append(f"links must have exactly these keys: {LINK_FIELDS}")

    for k in ("id", "ts", "date", "source", "source_ref", "kind", "title"):
        v = ev.get(k)
        if not isinstance(v, str) or not v:
            problems.append(f"{k!r} must be a non-empty string")

    return problems
