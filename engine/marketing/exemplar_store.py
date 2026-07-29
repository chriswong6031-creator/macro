"""engine/marketing/exemplar_store.py — the OPERATOR-RATIFIED exemplar store (E3).

Masterplan §10 E3: "auto-distilled exemplar candidates -> **operator-ratified**
exemplar store versions -> writer/critic prompts load exemplars from the store
(config-pinned version, never auto-flipped)".

    harvester  ->  propose_candidates()  ->  PENDING pool   (automatic, cheap)
                                                  |
                                    promote_pending()       (OPERATOR act #1)
                                                  v
                                            a numbered VERSION
                                                  |
                            config: intel.exemplar_store.active_version = N
                                                  |                (OPERATOR act #2)
                                                  v
                                  active_exemplars(register, k)  ->  the writer

**TWO OPERATOR ACTS, ON PURPOSE.** Minting a version and ACTIVATING one are
separate. ``promote_pending`` writes a new numbered version into the store and
changes nothing about what the writer sees; the writer sees exactly the version
pinned in ``config/marketing.yml`` ``intel.exemplar_store.active_version``, which
only a config edit (a reviewable diff on a tracked file) can move. So a promotion
cannot flip house voice, and a rollback is `git revert` on one config line.

**NOTHING HERE IS AUTOMATIC ABOVE THE PENDING POOL.** The harvester may append
candidates all night. It cannot promote, and it cannot activate. An unpinned
store means the writer sees NO exemplars — dark by default, which is the correct
launch state for a mechanism that changes how every desk sounds.

**The candidates are ranked deterministically** (interaction rate over observed
counters). An LLM may later *distil style notes* from a ratified version; it may
not choose which posts get in, and it may not score them (LLM-never-scores law).

Public API:
    STORE_SCHEMA
    store_path(root) / load_store(root) / save_store(store, root)
    propose_candidates(rows, *, cfg=None, now) -> list[dict]
    add_pending(candidates, *, root=None, cfg=None, now) -> dict
    promote_pending(version_note, *, ratified_by, root=None, cfg=None, now,
                    clear_pending=True) -> dict          # OPERATOR/ADMIN ONLY
    versions(root=None) -> list[dict]
    pinned_version(cfg) -> int | None
    active_version_meta(*, root=None, cfg=None) -> dict
    active_exemplars(register, k=6, *, root=None, cfg=None) -> list[dict]
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from engine.marketing.x_intel import (
    HOUSE_REGISTER_MAP,
    REGISTERS,
    intel_dir,
    iso_stamp,
    resolve_cfg,
    write_json_atomic,
)

log = logging.getLogger(__name__)

STORE_SCHEMA = "marketing.x_exemplar_store/v1"

_RE_WS = re.compile(r"\s+")


def store_path(root: Path | str | None = None) -> Path:
    return intel_dir(root) / "exemplar_store.json"


def _empty_store() -> dict:
    return {
        "schema": STORE_SCHEMA,
        "latest_version": 0,
        "versions": [],
        "pending": [],
        "updated_at": "",
        "note": (
            "Candidates land in `pending` automatically. A numbered `versions` "
            "entry is minted ONLY by exemplar_store.promote_pending(), and the "
            "writer reads ONLY the version pinned at "
            "config/marketing.yml intel.exemplar_store.active_version."
        ),
    }


def load_store(root: Path | str | None = None) -> dict:
    """The store, fail-soft. A missing/torn/foreign-schema file reads as EMPTY.

    Empty is the safe read: an empty store has no versions, so ``pinned_version``
    resolves to nothing and the writer gets zero exemplars. A corrupt store
    therefore degrades to "no exemplars", never to "some other version's voice".

    SCHEMA IS CHECKED ON READ, and it has to be, because ``save_store`` stamps
    ``STORE_SCHEMA`` unconditionally on whatever dict it is handed. Adopting a
    blob wholesale and then re-stamping it relabels a store written under a
    different (older, or another tool's) schema as current — silently, on the
    next write, with the entry shape assumed rather than verified. Since the
    entries feed the WRITER PROMPT, a mislabelled store is a voice change nobody
    approved. A schema mismatch is announced at line start and treated as empty.
    """
    import json  # noqa: PLC0415

    path = store_path(root)
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_store()
    except Exception as exc:  # noqa: BLE001
        print(
            f"::warning title=x-intel-exemplars::exemplar store at {path} is "
            f"unreadable ({exc}) — treating it as EMPTY, so the writer gets no "
            f"exemplars this run rather than a stale or partial voice",
            flush=True,
        )
        return _empty_store()
    if not isinstance(blob, dict):
        return _empty_store()
    schema = str(blob.get("schema") or "")
    if schema != STORE_SCHEMA:
        print(
            f"::warning title=x-intel-exemplars::exemplar store at {path} declares "
            f"schema {schema or '(none)'!r}, not {STORE_SCHEMA!r} — treating it as "
            f"EMPTY (the writer gets no exemplars this run) rather than adopting "
            f"entries of an unknown shape and re-stamping them as current",
            flush=True,
        )
        return _empty_store()
    base = _empty_store()
    base.update(blob)
    base.setdefault("versions", [])
    base.setdefault("pending", [])
    return base


def save_store(store: dict, root: Path | str | None = None, *,
               now: datetime | None = None) -> bool:
    try:
        payload = dict(store)
        payload["schema"] = STORE_SCHEMA
        payload["updated_at"] = iso_stamp(now or datetime.now(tz=timezone.utc))
        write_json_atomic(store_path(root), payload)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("exemplar_store.save_store: cannot write %s: %s", store_path(root), exc)
        return False


# ---------------------------------------------------------------------------
# Candidate proposal — deterministic, from the corpus
# ---------------------------------------------------------------------------
def _text_key(text: str) -> str:
    """Dedup key: whitespace-normalised, case-folded, hashed.

    Wire desks relay the same headline within minutes of each other, and the
    same account re-posts a template with one number changed. Both are ONE
    exemplar as far as a style store is concerned.
    """
    norm = _RE_WS.sub(" ", str(text or "")).strip().lower()
    return hashlib.sha1(norm.encode("utf-8", "replace")).hexdigest()[:16]  # noqa: S324


def _interaction_rate(row: dict) -> float | None:
    views = row.get("views")
    if not isinstance(views, int) or views <= 0:
        return None
    inter = sum(int(row.get(k) or 0) for k in ("likes", "retweets", "replies"))
    return inter / views


def propose_candidates(rows: Sequence[dict], *, cfg: dict | None = None,
                       now: datetime) -> list[dict]:
    """Top-interaction-rate posts per register, deduped and capped.

    Deliberately a RATE, not a like count: a wire desk with 1.1M views on a
    headline and a trader with 40k views on a setup are not comparable on raw
    likes, and ranking on raw likes would fill every register with whichever
    account is biggest. Posts under ``min_views`` are excluded outright — a rate
    over a denominator that thin is noise wearing a decimal point.
    """
    conf = resolve_cfg(cfg)
    es = conf.get("exemplar_store") or {}
    min_views = int(es.get("min_views") or 0)
    per_register = max(1, int(es.get("per_register") or 8))
    max_total = max(1, int(es.get("max_pending") or 40))
    stamped = iso_stamp(now)

    by_register: dict[str, list[tuple]] = {}
    #: THE TIE-BREAKER THAT KEEPS `sorted` OFF THE DICT. Every element of the key
    #: before `row` must be scalar AND the run of them must be unique, or Python
    #: falls through to comparing two dicts and raises
    #: `TypeError: '<' not supported between instances of 'dict' and 'dict'`.
    #: Two corpus rows with no `id` (the field is absent on some providers) and
    #: the same rate and views tie on all three of the earlier elements, so the
    #: harvest died on step 3 — and the workflow's `success()`-gated commit then
    #: threw away the state.json written back in step 1, AFTER the money was
    #: spent, re-opening the whole monthly budget on the next run. Corpus order is
    #: deterministic (the file is append-only), so the enumerate index keeps the
    #: proposal deterministic as well.
    seq = 0
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        views = row.get("views")
        if not isinstance(views, int) or views < min_views or views <= 0:
            continue
        rate = _interaction_rate(row)
        if rate is None:
            continue
        reg = str(row.get("author_register") or "unknown")
        # Sort key is fully determined by observed numbers plus the tweet id, so
        # two runs over the same corpus propose the SAME list in the SAME order.
        by_register.setdefault(reg, []).append(
            (-rate, -int(views), str(row.get("id") or ""), seq, row, rate)
        )
        seq += 1

    picked: list[dict] = []
    seen: set[str] = set()
    for reg in sorted(by_register):
        for neg_rate, neg_views, _tid, _seq, row, rate in sorted(
                by_register[reg])[: per_register * 3]:
            key = _text_key(row.get("text"))
            if key in seen:
                continue
            seen.add(key)
            picked.append({
                "register": reg,
                "text": str(row.get("text") or ""),
                "author": str(row.get("author") or ""),
                "url": str(row.get("url") or ""),
                "post_id": str(row.get("id") or ""),
                "created_at": str(row.get("created_at") or ""),
                "shape": str((row.get("tags") or {}).get("shape") or "unknown"),
                "engagement": {
                    "views": row.get("views"),
                    "likes": row.get("likes"),
                    "retweets": row.get("retweets"),
                    "replies": row.get("replies"),
                    "interaction_rate": round(float(rate), 8),
                },
                "text_key": key,
                "added": stamped,
            })
            if sum(1 for p in picked if p["register"] == reg) >= per_register:
                break

    picked.sort(key=lambda c: (c["register"],
                               -float(c["engagement"]["interaction_rate"]),
                               c["post_id"]))
    return picked[:max_total]


def add_pending(candidates: Sequence[dict], *, root: Path | str | None = None,
                cfg: dict | None = None, now: datetime,
                store: dict | None = None) -> dict:
    """Merge candidates into the PENDING pool. NEVER activates anything.

    This is the only automatic write in this module. It touches ``pending`` and
    nothing else — not ``versions``, not the config pin. A caller that wanted to
    promote has to say so, out loud, in a different function.
    """
    st = store if store is not None else load_store(root)
    conf = resolve_cfg(cfg)
    cap = max(1, int((conf.get("exemplar_store") or {}).get("max_pending") or 40))

    pending = list(st.get("pending") or [])
    have = {str(c.get("text_key") or _text_key(c.get("text"))) for c in pending}
    # Text already inside a ratified version is not a candidate again.
    for ver in st.get("versions") or []:
        for entry in ver.get("entries") or []:
            have.add(str(entry.get("text_key") or _text_key(entry.get("text"))))

    added = 0
    for cand in candidates:
        key = str(cand.get("text_key") or _text_key(cand.get("text")))
        if key in have:
            continue
        have.add(key)
        pending.append({**cand, "text_key": key})
        added += 1

    # Keep the strongest when the pool overflows — dropping the newest arrivals
    # would make the pool a function of arrival order rather than of evidence.
    pending.sort(key=lambda c: (-float((c.get("engagement") or {}).get("interaction_rate") or 0.0),
                                str(c.get("post_id") or "")))
    dropped = max(0, len(pending) - cap)
    st["pending"] = pending[:cap]
    st["updated_at"] = iso_stamp(now)
    return {"added": added, "dropped": dropped, "pending": len(st["pending"]), "store": st}


# ---------------------------------------------------------------------------
# Promotion — OPERATOR/ADMIN ONLY. Never called by the harvester.
# ---------------------------------------------------------------------------
def promote_pending(
    version_note: str,
    *,
    ratified_by: str,
    root: Path | str | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    clear_pending: bool = True,
    store: dict | None = None,
    save: bool = True,
) -> dict:
    """Mint a NEW numbered version from the pending pool. THE OPERATOR ACT.

    Nothing in the harvest path calls this, and nothing may: promotion is the
    moment a competitor's writing becomes an input to our own voice, and that is
    a judgement the operator makes, not a threshold a job crosses.

    IT DOES NOT ACTIVATE THE VERSION. The writer reads whatever
    ``intel.exemplar_store.active_version`` pins; this function only makes a
    version available to pin. The returned dict carries ``activation_hint`` with
    the exact config line, because the second act is easy to forget and a minted
    but unpinned version looks identical to a promotion that "did nothing".

    ``ratified_by`` is REQUIRED and non-empty: an unattributed ratification is
    indistinguishable from an automatic one, which is the thing this gate exists
    to prevent.
    """
    who = str(ratified_by or "").strip()
    if not who:
        raise ValueError(
            "promote_pending requires ratified_by — an exemplar version with no "
            "named ratifier is indistinguishable from an automatic promotion"
        )
    stamp = now or datetime.now(tz=timezone.utc)
    st = store if store is not None else load_store(root)
    pending = list(st.get("pending") or [])
    if not pending:
        return {"ok": False, "reason": "pending pool is empty — nothing to promote",
                "version": None, "store": st}

    version = int(st.get("latest_version") or 0) + 1
    # Entries are copied, not aliased: a version is a FROZEN artifact and must
    # not move because someone later mutates the pending list it came from.
    entries = [dict(cand) for cand in pending]
    st.setdefault("versions", []).append({
        "version": version,
        "ratified_by": who,
        "ratified_at": iso_stamp(stamp),
        "note": str(version_note or ""),
        "n_entries": len(entries),
        "registers": sorted({str(e.get("register") or "unknown") for e in entries}),
        "entries": entries,
    })
    st["latest_version"] = version
    if clear_pending:
        st["pending"] = []
    if save:
        save_store(st, root, now=stamp)

    print(
        f"::notice title=x-intel-exemplars::exemplar store version {version} minted "
        f"by {who} ({len(entries)} entries). IT IS NOT LIVE: set "
        f"intel.exemplar_store.active_version: {version} in config/marketing.yml "
        f"to let the writer read it.",
        flush=True,
    )
    return {
        "ok": True,
        "version": version,
        "n_entries": len(entries),
        "ratified_by": who,
        "activation_hint": (
            "config/marketing.yml -> intel: exemplar_store: active_version: "
            f"{version}"
        ),
        "store": st,
    }


def versions(root: Path | str | None = None) -> list[dict]:
    """Version headers (no entry bodies) — the audit trail, newest last."""
    out = []
    for ver in load_store(root).get("versions") or []:
        out.append({k: v for k, v in ver.items() if k != "entries"})
    return out


# ---------------------------------------------------------------------------
# The writer hook
# ---------------------------------------------------------------------------
def pinned_version(cfg: dict | None) -> int | None:
    """The version the CONFIG pins, or None. The only thing the writer may read."""
    raw = (resolve_cfg(cfg).get("exemplar_store") or {}).get("active_version")
    if raw is None or raw == "" or raw is False:
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        print(
            f"::warning title=x-intel-exemplars::intel.exemplar_store.active_version "
            f"is {raw!r}, which is not a version number — the writer will read NO "
            f"exemplars until it is an integer or null",
            flush=True,
        )
        return None
    return val if val > 0 else None


def _registers_for(register: str | None) -> tuple[str, ...]:
    """Accept either vocabulary: house dial names or intel corpus registers.

    ``labels.REGISTER_NAMES`` calls them wire/analysis/persona; the corpus calls
    them wire/aggregator/commentary/trader/macro_color. The writer hook should
    not have to know which one it is holding.
    """
    key = str(register or "").strip().lower()
    if not key:
        return tuple(REGISTERS)
    if key in HOUSE_REGISTER_MAP:
        return HOUSE_REGISTER_MAP[key]
    if key in REGISTERS:
        return (key,)
    return tuple(REGISTERS)


def active_version_meta(*, root: Path | str | None = None,
                        cfg: dict | None = None) -> dict:
    """What the writer would see, and why — the inspectable half of the hook."""
    pin = pinned_version(cfg)
    st = load_store(root)
    found = next((v for v in (st.get("versions") or [])
                  if int(v.get("version") or 0) == pin), None) if pin else None
    if pin is None:
        reason = ("no version pinned (intel.exemplar_store.active_version is null) "
                  "— the writer reads NO exemplars, which is the dark default")
    elif found is None:
        reason = (f"version {pin} is pinned but the store has no such version "
                  f"(latest is {st.get('latest_version') or 0}) — the writer reads "
                  f"NO exemplars rather than silently falling back to another one")
    else:
        reason = ""
    return {
        "pinned": pin,
        "exists": found is not None,
        "latest_version": int(st.get("latest_version") or 0),
        "n_entries": int((found or {}).get("n_entries") or 0),
        "ratified_by": (found or {}).get("ratified_by"),
        "ratified_at": (found or {}).get("ratified_at"),
        "n_pending": len(st.get("pending") or []),
        "reason": reason,
    }


def active_exemplars(register: str | None = None, k: int = 6, *,
                     root: Path | str | None = None,
                     cfg: dict | None = None) -> list[dict]:
    """THE WRITER HOOK. Exemplars from the PINNED version only.

    WIRED IN PRODUCTION (E-wave review, BLOCKER 3 — this shipped with no caller
    at all, so the whole harvest -> pending -> promotion -> pin chain ended at a
    function only tests ran). The two callers, both of which pass ``cfg`` and
    ``root`` down and add nothing to any numeric whitelist:

        engine/marketing/copywriter.py   store_exemplar_block()
                                         -> _v2_system_prompt -> write_posts_llm_v2
        engine/marketing/reply_voice.py  system_prompt()
                                         -> voice_or_fallback

    The dependency still points ONE WAY: this module imports neither of them.

        from engine.marketing import exemplar_store
        shots = exemplar_store.active_exemplars(register, k=4, cfg=cfg)
        # each: {register, text, author, url, shape, engagement, ...}
        # -> render into the writer prompt as verbatim style references.
        # STYLE ONLY: the figures inside an exemplar are somebody else's, and
        # must never widen the item's own numbers_whitelist.

    Guarantees the caller can rely on:
      * an UNPINNED store returns ``[]`` (dark default) — never "the latest";
      * a pin at a version the store does not have returns ``[]`` — never a
        neighbouring version;
      * the pending pool is NEVER visible here, however full it is;
      * the order is deterministic (interaction rate, then post id), so the same
        corpus and the same pin build the same prompt.
    """
    pin = pinned_version(cfg)
    if pin is None:
        return []
    st = load_store(root)
    ver = next((v for v in (st.get("versions") or [])
                if int(v.get("version") or 0) == pin), None)
    if ver is None:
        print(
            f"::warning title=x-intel-exemplars::intel.exemplar_store.active_version "
            f"pins version {pin}, which does not exist in "
            f"{store_path(root)} (latest={st.get('latest_version') or 0}) — the "
            f"writer gets NO exemplars this run",
            flush=True,
        )
        return []
    want = _registers_for(register)
    rows = [e for e in (ver.get("entries") or [])
            if str(e.get("register") or "unknown") in want]
    rows.sort(key=lambda e: (-float((e.get("engagement") or {}).get("interaction_rate") or 0.0),
                             str(e.get("post_id") or "")))
    out = [dict(e) for e in rows[: max(0, int(k))]]
    for entry in out:
        entry["exemplar_version"] = pin
    return out


__all__ = [
    "STORE_SCHEMA", "store_path", "load_store", "save_store",
    "propose_candidates", "add_pending", "promote_pending", "versions",
    "pinned_version", "active_version_meta", "active_exemplars",
]
