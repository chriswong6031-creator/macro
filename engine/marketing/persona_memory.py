"""engine/marketing/persona_memory.py — per-persona memory stores (XG-W3).

Three stores per account, under `data/marketing/personas/<id>/`:

  promises.jsonl  open loops with due conditions — every promise closed or
                  explicitly released (constitution §11.6: "An open loop without
                  a follow-up trains distrust")
  phrases.jsonl   one record per EMITTED POST, which is what makes the XG-W1
                  per-quirk frequency caps enforceable across days
  relations.jsonl public interaction context per author handle — topics, stage,
                  last contact. NOTHING SENSITIVE INFERRED (constitution §10
                  relationship-memory law, charter §4).

`theses.jsonl` (the opinion ledger) already exists as a declared path in every
persona spec and is graded by the forward-ledger machinery; this module does not
touch it.

THE NIGHTLY-SOLE-ADVANCER LAW (charter §2 amendment 13).  Emission-time counters
accumulate in HOST state — zero tracked-repo writes intraday, the same posture as
the daemon's `items-host.jsonl` spool and the poller cursors. A nightly
consolidator is the ONLY writer of the tracked ledgers. Concretely:

    data/marketing/personas_host/<id>/*.jsonl   gitignored, appended intraday
    data/marketing/personas/<id>/*.jsonl        tracked, advanced by consolidate()

The split is not decorative. The VPS daemon runs inside a checkout that `git
pull`s every 3 minutes; an intraday writer touching a tracked file collides with
that pull and with the render lane's resets. `tests/test_marketing_desk_feeds.py`
carries an AST guard (modelled on XG-W2's hand-rolled-writer guard) asserting
that `consolidate()` is the only code path that opens a write handle under the
tracked directory — a RENAMED intraday writer has to fail it too.

WHY phrases.jsonl STORES POST TEXT.  `expression_dial.frequency_violations(text,
*, codex, as_of, recent)` re-runs each marker's own pattern over `recent`, where
recent is `[{"text": ..., "date": "YYYY-MM-DD"}, ...]`. It returns `[]` when
`recent` is empty — so before this module existed, `max_per_day` / `max_share_7d`
were declared-but-unenforced beyond a single batch (`copywriter.py` says so in
its own comment). Storing the emitted text is what arms them. Derived n-grams
ride along for topic-fatigue diagnostics; they are NOT the cap mechanism, because
re-deriving a marker from an n-gram would duplicate the codex's patterns and the
two copies would drift.

Public API:
    recent_posts(account, *, now, days=7, root=None)   -> list[{text, date}]
    record_post(account, text, *, now, ...)            -> dict     (host write)
    open_promises(account, *, now=None, root=None)     -> list[dict]
    record_promise(account, text, *, due_condition, now, ...) -> dict (host)
    close_promise(account, promise_id, *, now, outcome, ...)  -> dict (host)
    relations(account, *, root=None)                   -> dict[handle, dict]
    record_relation(account, handle, *, now, topics=(), stage="") -> dict (host)
    ngram_fatigue(account, *, now, days=7, n=3, root=None) -> dict[str, int]
    consolidate(*, now, root=None, accounts=None)      -> dict  (THE ONLY tracked writer)
    host_dir(root, account) / repo_dir(root, account)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "STORES",
    "RELATION_STAGES",
    "host_dir",
    "repo_dir",
    "recent_posts",
    "record_post",
    "open_promises",
    "record_promise",
    "close_promise",
    "relations",
    "record_relation",
    "ngram_fatigue",
    "consolidate",
]

#: The three stores this module owns. `theses.jsonl` is deliberately absent —
#: the opinion ledger is graded by the existing forward-ledger machinery and a
#: second writer would race it.
STORES: tuple[str, ...] = ("promises", "phrases", "relations")

#: Relationship stages (constitution §9.2 target tiers, reused). A closed
#: vocabulary because "stage" is the only judgment this store holds, and a
#: free-text stage would be an invitation to infer something about a person.
RELATION_STAGES: frozenset[str] = frozenset({"", "cold", "engaged", "reciprocal", "declined"})

#: How much history the tracked ledgers keep. The caps that consume this store
#: look back 7 days (expression_dial.SHARE_WINDOW_DAYS); 90 days leaves ample
#: room for the XG-W6 diagnostics without unbounded growth in a tracked file.
RETENTION_DAYS: int = 90

_DAY_FMT = "%Y-%m-%d"


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
def _root_path(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parent.parent.parent
    return Path(root)


def repo_dir(root: Path | str | None, account: str) -> Path:
    """The TRACKED ledger dir. Only `consolidate()` may write here."""
    return _root_path(root) / "data" / "marketing" / "personas" / str(account)


def host_dir(root: Path | str | None, account: str) -> Path:
    """The GITIGNORED intraday spool dir (see `.gitignore`).

    Mirrors `outbox._host_items_path`'s posture: a gitignored sibling, not a
    filesystem-external path, so a developer can inspect it and the daemon can
    write it without dirtying the checkout.
    """
    return _root_path(root) / "data" / "marketing" / "personas_host" / str(account)


def _store_path(base: Path, store: str) -> Path:
    if store not in STORES:
        raise ValueError(f"unknown store {store!r}; allowed: {sorted(STORES)}")
    return base / f"{store}.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# JSONL I/O — fail-soft on read, atomic on write
# ─────────────────────────────────────────────────────────────────────────────
def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, skipping unparseable lines.

    Fail-soft: a half-written final line (the daemon killed mid-append) must not
    blind a guard to the 400 good records above it.
    """
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except FileNotFoundError:
        return []
    except OSError:
        return []
    return out


def _append_host(root: Path | str | None, account: str, store: str, rec: dict) -> dict:
    """Append one record to the HOST spool. The only write path used intraday."""
    d = host_dir(root, account)
    path = _store_path(d, store)
    d.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


def _write_tracked(path: Path, rows: Sequence[dict]) -> None:
    """Atomic replace of a TRACKED ledger. Called ONLY by `consolidate()`.

    Kept as a single private helper so the AST guard has exactly one symbol to
    allowlist, and so a second tracked writer cannot appear by accident.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".pm-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_union(root: Path | str | None, account: str, store: str) -> list[dict]:
    """Tracked ledger PLUS the host spool.

    Readers always see the union — exactly like `outbox.read_items_all`. This is
    load-bearing: a cap that ignored today's un-consolidated posts would let an
    account spend its whole daily quirk budget between two nightlies.
    """
    return _read_jsonl(_store_path(repo_dir(root, account), store)) + _read_jsonl(
        _store_path(host_dir(root, account), store)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────
def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_of(rec: dict) -> str:
    """The record's calendar day, preferring an explicit `date`."""
    d = str(rec.get("date") or "").strip()
    if d:
        return d[:10]
    at = str(rec.get("at") or "").strip()
    return at[:10]


def _parse_day(s: str) -> datetime | None:
    try:
        return datetime.strptime(str(s)[:10], _DAY_FMT).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _record_key(store: str, rec: dict) -> str:
    """A stable identity for dedup at consolidation.

    Explicit `id` wins; otherwise a hash of the fields that make the record what
    it is. Without this, a consolidator re-run (a retried nightly) would double
    every counter and silently tighten every cap.
    """
    rid = str(rec.get("id") or "").strip()
    if rid:
        return rid
    if store == "phrases":
        # (DATE, text) — NOT (at, text) (review F9). The `at` timestamp is
        # wall-clock at write, so a plan-build re-run that re-emits the same
        # post a minute later produces a DIFFERENT key and the record survives
        # dedup twice. Two copies of one post inflate both the numerator and
        # the denominator of `max_share_7d` and double-count `max_per_day` —
        # i.e. a retried run would silently TIGHTEN the caps it is supposed to
        # measure. The business day plus the text is the post's real identity.
        basis = f"{_day_of(rec)}|{rec.get('text','')}"
    elif store == "relations":
        basis = f"{rec.get('handle','')}|{rec.get('at','')}"
    else:
        basis = f"{rec.get('at','')}|{rec.get('text','')}"
    return hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# phrases.jsonl — the store that arms the quirk caps
# ─────────────────────────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"[a-z0-9']+")


def _ngrams(text: str, n: int = 3) -> list[str]:
    """Lowercased word n-grams, for topic/phrase fatigue diagnostics."""
    words = _WORD_RE.findall(str(text).lower())
    if len(words) < n:
        return []
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def record_post(
    account: str,
    text: str,
    *,
    now: datetime,
    as_of: str = "",
    franchise: str = "",
    kind: str = "",
    item_id: str = "",
    root: Path | str | None = None,
) -> dict:
    """Record an EMITTED post into the host spool (intraday).

    `text` should be the full emitted copy (`headline + " " + body`), because
    that is what `expression_dial.frequency_violations` re-scans for markers.

    DAY BASIS MUST MATCH THE EVALUATOR (review F18). The caps are evaluated by
    `frequency_violations(..., as_of=<business date>, recent=[{date: ...}])`,
    which compares each record's `date` against the item's `as_of` — the
    CONTENT PLAN's business date, not a wall clock. Storing a UTC-derived date
    here would put the two on different calendars: Cici's 08:00 Hong Kong post
    is still the previous UTC day, so her second signature opener of the HK
    morning would land on a different `date` than the plan's `as_of` and slip
    the ≤1/day cap entirely. When the caller knows the business date it wins;
    `now` is only the fallback.
    """
    at = _as_utc(now)
    day = str(as_of or "").strip()[:10] or at.strftime(_DAY_FMT)
    rec = {
        "account": str(account),
        "at": at.isoformat(),
        "date": day,
        "text": str(text),
        "franchise": str(franchise or ""),
        "kind": str(kind or ""),
        "item_id": str(item_id or ""),
        "ngrams": _ngrams(text),
    }
    rec["id"] = _record_key("phrases", rec)
    return _append_host(root, account, "phrases", rec)


def recent_posts(
    account: str,
    *,
    now: datetime,
    days: int = 7,
    root: Path | str | None = None,
) -> list[dict]:
    """The `recent` argument `expression_dial.frequency_violations` wants.

    Returns `[{"text": str, "date": "YYYY-MM-DD"}, ...]` for the trailing
    `days` window, oldest-first. This is THE wiring that turns the XG-W1
    per-quirk caps (`max_per_day`, `max_per_7d`, `max_share_7d`) from declared
    numbers into enforced ones — `frequency_violations` returns `[]` on an empty
    `recent`, so an account with no store is simply uncapped, exactly as it was
    before this module.
    """
    cutoff = (_as_utc(now) - timedelta(days=days)).strftime(_DAY_FMT)
    rows = _read_union(root, account, "phrases")
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        day = _day_of(r)
        if not day or day < cutoff:
            continue
        key = _record_key("phrases", r)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": str(r.get("text") or ""), "date": day})
    out.sort(key=lambda x: x["date"])
    return out


def ngram_fatigue(
    account: str,
    *,
    now: datetime,
    days: int = 7,
    n: int = 3,
    root: Path | str | None = None,
    min_count: int = 2,
) -> dict[str, int]:
    """Rolling n-gram counts over the window — the anti-sameness diagnostic.

    Distinct from the quirk caps: those police WHITELISTED signatures against
    their declared budget; this surfaces UNDECLARED repetition (the same stock
    phrase three days running). Feeds the `topic_overused` abstention reason.
    """
    cutoff = (_as_utc(now) - timedelta(days=days)).strftime(_DAY_FMT)
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for r in _read_union(root, account, "phrases"):
        day = _day_of(r)
        if not day or day < cutoff:
            continue
        key = _record_key("phrases", r)
        if key in seen:
            continue
        seen.add(key)
        grams = r.get("ngrams")
        if not isinstance(grams, list) or (n != 3):
            grams = _ngrams(r.get("text") or "", n)
        for g in grams:
            g = str(g)
            counts[g] = counts.get(g, 0) + 1
    return {g: c for g, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c >= min_count}


# ─────────────────────────────────────────────────────────────────────────────
# promises.jsonl — open loops
# ─────────────────────────────────────────────────────────────────────────────
def record_promise(
    account: str,
    text: str,
    *,
    due_condition: str,
    now: datetime,
    due_by: str = "",
    franchise: str = "",
    item_id: str = "",
    root: Path | str | None = None,
) -> dict:
    """Open a loop. `due_condition` is mandatory and non-empty by design.

    Constitution §11.6: a promise without a condition cannot be closed, and an
    unclosable promise is precisely the thing that trains distrust. An empty
    condition raises rather than silently recording an unfollowable loop.
    """
    cond = str(due_condition or "").strip()
    if not cond:
        raise ValueError("due_condition is required — an open loop needs a closing condition")
    at = _as_utc(now)
    rec = {
        "account": str(account),
        "at": at.isoformat(),
        "date": at.strftime(_DAY_FMT),
        "text": str(text),
        "due_condition": cond,
        "due_by": str(due_by or ""),
        "franchise": str(franchise or ""),
        "item_id": str(item_id or ""),
        "status": "open",
    }
    rec["id"] = _record_key("promises", rec)
    return _append_host(root, account, "promises", rec)


def close_promise(
    account: str,
    promise_id: str,
    *,
    now: datetime,
    outcome: str = "",
    released: bool = False,
    root: Path | str | None = None,
) -> dict:
    """Close (or explicitly RELEASE) an open loop.

    A release is a first-class outcome, not a failure: the constitution asks for
    "every promise closed or explicitly released", and a condition that stopped
    being relevant deserves an honest release rather than a silent drop.
    Recorded as a new host record; `consolidate()` folds status onto the id.
    """
    at = _as_utc(now)
    rec = {
        "account": str(account),
        "at": at.isoformat(),
        "date": at.strftime(_DAY_FMT),
        "id": str(promise_id),
        "status": "released" if released else "closed",
        "closed_at": at.isoformat(),
        "outcome": str(outcome or ""),
    }
    return _append_host(root, account, "promises", rec)


def _fold_promises(rows: Iterable[dict]) -> dict[str, dict]:
    """Fold append-only promise records into current state, by id."""
    state: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: str(x.get("at") or "")):
        pid = str(r.get("id") or _record_key("promises", r))
        if pid in state:
            cur = dict(state[pid])
            cur.update({k: v for k, v in r.items() if v not in (None, "")})
            state[pid] = cur
        else:
            state[pid] = dict(r)
    return state


def open_promises(
    account: str,
    *,
    now: datetime | None = None,
    root: Path | str | None = None,
) -> list[dict]:
    """Every still-open loop, oldest-first, with `overdue` stamped when due_by passed."""
    state = _fold_promises(_read_union(root, account, "promises"))
    out = [r for r in state.values() if str(r.get("status") or "open") == "open"]
    if now is not None:
        today = _as_utc(now).strftime(_DAY_FMT)
        for r in out:
            due = str(r.get("due_by") or "")
            r["overdue"] = bool(due and due < today)
    out.sort(key=lambda r: str(r.get("at") or ""))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# relations.jsonl — public interaction context
# ─────────────────────────────────────────────────────────────────────────────
def record_relation(
    account: str,
    handle: str,
    *,
    now: datetime,
    topics: Sequence[str] = (),
    stage: str = "",
    root: Path | str | None = None,
) -> dict:
    """Record a PUBLIC interaction with an author handle.

    NOTHING SENSITIVE INFERRED (constitution §10, charter §4). The schema admits
    exactly three things — the handle, the public topics discussed, and a stage
    from a closed vocabulary. There is deliberately no field for demographics,
    affiliation, location, employer, or any inferred trait, so there is nowhere
    for one to be written even by a future careless caller. An out-of-vocabulary
    stage raises.
    """
    st = str(stage or "").strip().lower()
    if st not in RELATION_STAGES:
        raise ValueError(f"unknown relation stage {st!r}; allowed: {sorted(RELATION_STAGES)}")
    at = _as_utc(now)
    rec = {
        "account": str(account),
        "handle": str(handle).lstrip("@"),
        "at": at.isoformat(),
        "date": at.strftime(_DAY_FMT),
        "topics": [str(t) for t in topics],
        "stage": st,
    }
    rec["id"] = _record_key("relations", rec)
    return _append_host(root, account, "relations", rec)


def relations(account: str, *, root: Path | str | None = None) -> dict[str, dict]:
    """Fold interaction records into per-handle context: topics, stage, last contact."""
    out: dict[str, dict] = {}
    for r in sorted(_read_union(root, account, "relations"), key=lambda x: str(x.get("at") or "")):
        h = str(r.get("handle") or "").lstrip("@")
        if not h:
            continue
        cur = out.setdefault(h, {"handle": h, "topics": [], "stage": "", "last_contact": "", "touches": 0})
        for t in r.get("topics") or []:
            if t not in cur["topics"]:
                cur["topics"].append(str(t))
        if r.get("stage"):
            cur["stage"] = str(r["stage"])
        cur["last_contact"] = str(r.get("at") or cur["last_contact"])
        cur["touches"] += 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# THE CONSOLIDATOR — the only writer of data/marketing/personas/
# ─────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def _spool_lock(root: Path | str | None, timeout_s: float = 2.0):
    """Advisory flock over the host spool, mirroring `outbox._outbox_lock`.

    THE READ→TRUNCATE WINDOW IS THE RACE (review F10). `consolidate()` reads a
    spool, writes the tracked ledger, then unlinks the spool. A daemon
    appending a post between the read and the unlink loses that post outright —
    it was never folded in and its file is gone. On the VPS the fastlane daemon
    appends at press-tick cadence while the nightly runs, so the window is real,
    not theoretical.

    Yields True when held, False when proceeding unlocked (flock unsupported or
    busy) — same fail-soft contract as the outbox lock, because a lock failure
    must not stop the nightly from advancing ledgers.
    """
    lock_fh = None
    acquired = False
    try:
        try:
            import fcntl  # noqa: PLC0415  (POSIX only; fail-soft elsewhere)

            d = _root_path(root) / "data" / "marketing" / "personas_host"
            d.mkdir(parents=True, exist_ok=True)
            lock_fh = open(d / ".lock", "a", encoding="utf-8")  # noqa: SIM115
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        print(
                            "::warning title=persona_memory::host spool lock busy after "
                            f"{timeout_s:.1f}s — consolidating unlocked; a concurrent "
                            "append may be lost",
                            flush=True,
                        )
                        break
                    time.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            print(
                f"::warning title=persona_memory::advisory lock unavailable ({exc}) — "
                "consolidating unlocked",
                flush=True,
            )
        yield acquired
    finally:
        if lock_fh is not None:
            try:
                if acquired:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            try:
                lock_fh.close()
            except Exception:  # noqa: BLE001
                pass


def _accounts_with_host_state(root: Path | str | None) -> list[str]:
    base = _root_path(root) / "data" / "marketing" / "personas_host"
    try:
        return sorted(p.name for p in base.iterdir() if p.is_dir())
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []


def consolidate(
    *,
    now: datetime,
    root: Path | str | None = None,
    accounts: Sequence[str] | None = None,
    retention_days: int = RETENTION_DAYS,
    clear_host: bool = True,
) -> dict[str, Any]:
    """Advance the TRACKED persona ledgers from the host spools. Nightly only.

    This is the sole writer of `data/marketing/personas/` (charter §2 amendment
    13; the nightly-sole-advancer law). It is idempotent: records dedup on their
    stable key, so a retried nightly cannot double a counter — which matters
    because those counters bound how often a persona may use its own signature.

    `clear_host=True` truncates each consolidated host spool AFTER the tracked
    write lands, so an interrupted run loses nothing (the records are still in
    the spool and the next run re-folds them).

    TODO(xg-w3-review): F11 — SPOOL STRANDING ACROSS HOSTS. This consolidator
    only ever sees the spool on the machine it runs on. The nightly runs on the
    Mac Studio; the fastlane daemon writes its spool on the VPS. Posts the VPS
    ships therefore accumulate in a spool the nightly never reads, and the caps
    they should feed stay blind to them — while the Mac Studio's own spool
    consolidates normally, so the failure is SILENT and partial rather than
    obvious. Closing it needs a decision this wave does not own: either the VPS
    ships its spool to R2 for the nightly to drain, or the publisher writes
    straight to a shared store. Until then the caps are armed for
    nightly-emitted posts and under-count VPS-emitted ones; the honest reading
    of a cap today is "at least this many", not "exactly this many".

    Returns a per-account, per-store summary of counts for the nightly log.
    """
    # THE KNOB MUST BE REAL (review F12). daily.yml sets
    # MARKETING_PERSONA_MEMORY_ENABLED on this step; a step that ignores its own
    # env gate is a fake knob — an operator who sets it to 0 to stop ledger
    # growth would see the ledgers advance anyway. Default ON: absent means
    # "nobody expressed an opinion", which for a nightly consolidation is
    # correct, and only an explicit off-value disables it.
    flag = os.environ.get("MARKETING_PERSONA_MEMORY_ENABLED")
    if flag is not None and flag.strip().lower() in ("0", "false", "no", "off"):
        print(
            "::notice title=persona_memory::MARKETING_PERSONA_MEMORY_ENABLED="
            f"{flag!r} — skipping consolidation; tracked ledgers not advanced",
            flush=True,
        )
        return {"as_of": _as_utc(now).isoformat(), "accounts": {}, "skipped": "disabled"}

    # HOLD THE SPOOL LOCK ACROSS THE WHOLE read→write→truncate SEQUENCE
    # (review F10) — see `_spool_lock`. Taking it per-store would reopen the
    # same window between stores.
    with _spool_lock(root):
        return _consolidate_locked(
            now=now, root=root, accounts=accounts,
            retention_days=retention_days, clear_host=clear_host,
        )


def _consolidate_locked(
    *,
    now: datetime,
    root: Path | str | None,
    accounts: Sequence[str] | None,
    retention_days: int,
    clear_host: bool,
) -> dict[str, Any]:
    """The body of `consolidate()`, run under the host-spool lock."""
    ids = list(accounts) if accounts is not None else _accounts_with_host_state(root)
    cutoff_dt = _as_utc(now) - timedelta(days=max(0, int(retention_days)))
    cutoff = cutoff_dt.strftime(_DAY_FMT)
    summary: dict[str, Any] = {"as_of": _as_utc(now).isoformat(), "accounts": {}}

    for account in ids:
        acct_summary: dict[str, Any] = {}
        for store in STORES:
            host_path = _store_path(host_dir(root, account), store)
            tracked_path = _store_path(repo_dir(root, account), store)
            host_rows = _read_jsonl(host_path)
            tracked_rows = _read_jsonl(tracked_path)
            if not host_rows and not tracked_rows:
                continue

            if store == "promises":
                # Fold status updates onto their promise id, then keep every
                # still-open loop REGARDLESS of age — an old open promise is
                # exactly the one most in need of closing, so retention must
                # never quietly retire it.
                folded = _fold_promises(tracked_rows + host_rows)
                merged = []
                for r in folded.values():
                    day = _day_of(r)
                    if str(r.get("status") or "open") == "open" or not day or day >= cutoff:
                        merged.append(r)
                merged.sort(key=lambda r: str(r.get("at") or ""))
            else:
                seen: set[str] = set()
                merged = []
                for r in tracked_rows + host_rows:
                    day = _day_of(r)
                    if day and day < cutoff:
                        continue
                    key = _record_key(store, r)
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(r)
                merged.sort(key=lambda r: str(r.get("at") or ""))

            _write_tracked(tracked_path, merged)
            acct_summary[store] = {
                "host": len(host_rows),
                "tracked_before": len(tracked_rows),
                "tracked_after": len(merged),
            }
            if clear_host and host_rows:
                try:
                    host_path.unlink()
                except OSError:
                    pass
        if acct_summary:
            summary["accounts"][account] = acct_summary
    return summary


def _main(argv: Sequence[str] | None = None) -> int:
    """CLI entry for the nightly step: `python -m engine.marketing.persona_memory`."""
    import argparse

    ap = argparse.ArgumentParser(description="Consolidate persona memory host spools into the tracked ledgers.")
    ap.add_argument("--root", default=None)
    ap.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    ap.add_argument("--keep-host", action="store_true", help="do not truncate host spools")
    args = ap.parse_args(list(argv) if argv is not None else None)

    out = consolidate(
        now=datetime.now(timezone.utc),
        root=args.root,
        retention_days=args.retention_days,
        clear_host=not args.keep_host,
    )
    n = len(out.get("accounts") or {})
    # Bare print at line start — a logger would prefix the annotation and
    # GitHub would silently drop it (house law).
    print(f"persona_memory: consolidated {n} account(s)", flush=True)
    if not n:
        print("::notice title=persona_memory::no host spools to consolidate", flush=True)
    print(json.dumps(out, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
