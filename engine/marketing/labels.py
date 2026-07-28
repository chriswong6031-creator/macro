"""engine/marketing/labels.py — the ONE feedback loop (XG-W6 / IS-W5).

Four charters asked for a feedback loop and described the same machine four
times: D05 §7's wire loop, IS-W5's telemetry->labels->scorecard, Persona W4's
report card, and Media W2's scorecards. Charter §6 reconciles them into ONE
loop with four named consumers (``CONSUMERS``). This module is that loop.

    per-post telemetry  ->  labels store  ->  weekly scorecard
    (LIVE metrics poll)     (this module)     (hook x format x register x account)

**Where the telemetry actually comes from (verified in-tree 2026-07-28).**
Two pipelines exist and only one of them is fed:

  * ``scripts/marketing_metrics_poll.py`` is LIVE. It runs as a step in
    ``.github/workflows/marketing-publish.yml`` ("poll post metrics"), reads
    Buffer analytics for every recently-posted item, and the workflow commits
    ``data/marketing/post_metrics.jsonl`` back. That ledger is this module's
    post-telemetry source.
  * ``engine/marketing/telemetry.py`` (the Lab roll-up) is TEST-FED ONLY:
    ``ingest_rows`` has no production caller and ``data/marketing/telemetry/``
    does not exist in the checkout, so ``lab_rollup.json`` reports n=0 forever.
    This module deliberately does NOT write into it — a second writer racing an
    unfed store buys nothing. Bridging the Lab roll-up onto post_metrics is a
    separate, small change and is left to whoever owns that surface.

**THE NIGHTLY-SOLE-ADVANCER LAW** (charter §2 amendment 13). Intraday writers
touch only host state; a nightly consolidator is the ONLY writer of the tracked
ledgers:

    data/marketing/learning_host/labels.jsonl   gitignored, appended intraday
    data/marketing/learning/labels.jsonl        tracked, advanced by consolidate()
    data/marketing/learning/scorecard.json      tracked, written by consolidate()

``tests/test_marketing_learning.py`` carries an AST guard (modelled on XG-W3's)
asserting ``_write_tracked`` is the only path that opens a write handle under
the tracked directory, so a RENAMED intraday writer fails it too.

**NO SCORE OR LABEL IS EVER USER-FACING.** Every row here is an operator-console
artifact. Nothing in ``site/`` reads this store and nothing may.

**LLM never scores** (charter §2 amendment 9). Every field below is arithmetic
over observed counters. This module imports no model client and must not.

Public API:
    CONSUMERS / DIMS / LABEL_SCHEMA
    host_dir(root) / repo_dir(root) / labels_path(root) / scorecard_path(root)
    new_row(**fields) -> dict                      # THE row constructor
    record_observation(row, *, root=None)          -> dict   (HOST write, intraday)
    harvest_post_labels(*, root, cfg=None, now)    -> list[dict]
    harvest_reply_labels(*, store, root, cfg=None, now) -> list[dict]
    parent_adjust(rows, *, cfg=None)               -> list[dict]
    scorecard(rows, *, cfg=None, now)              -> dict
    bottleneck_table(rows, *, cfg=None, now)       -> dict
    north_star(rows, *, cfg=None, now)             -> dict
    consolidate(*, now, root=None, store=None, cfg=None) -> dict  (SOLE tracked writer)
    load_labels(root=None) -> list[dict]
    load_scorecard(root=None) -> dict
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

LABEL_SCHEMA = "marketing.label/v1"
SCORECARD_SCHEMA = "marketing.learning_scorecard/v1"

#: The four charters that asked for a feedback loop. Recorded on the scorecard
#: so a future reader cannot re-charter a fifth one by accident: if you are
#: about to build a loop, it is one of these and it already exists.
CONSUMERS: tuple[str, ...] = (
    "d05_wire_loop",            # D05 §7 — press/wire lane learning
    "is_w5_ranker",             # IS-W5 — ranker retrain + template-pool tuning
    "persona_w4_report_card",   # Persona W4 — per-account report card
    "media_w2_scorecard",       # Media W2 — property scorecards
)

#: The scorecard's cell key. Charter/IS-W5 wording: "hook family x format x
#: register x account".
DIMS: tuple[str, ...] = ("account", "format", "register", "hook_family")

#: Rows below this per cell never carry a verdict. Mirrors telemetry.py's
#: _N_FLOOR so the two surfaces cannot disagree about what "enough" means.
DEFAULT_N_FLOOR: int = 20

#: How much history the tracked ledger keeps.
RETENTION_DAYS: int = 180

_DAY_FMT = "%Y-%m-%d"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
#: EVERY THRESHOLD IS A CONFIG KEY (charter §8). These are the documented
#: defaults; ``config/marketing.yml`` ``learning:`` overrides them.
DEFAULTS: dict[str, Any] = {
    "n_floor": DEFAULT_N_FLOOR,
    "retention_days": RETENTION_DAYS,
    "scorecard_window_days": 7,
    # THE NORTH STAR IS UNDEFINED AT ZERO (charter §8). "Qualified retained
    # followers per 100 contributions" divides by a follower base that does not
    # exist yet, so it activates only above this floor; below it the bottleneck
    # table on RAW COUNTS is the honest instrument.
    "north_star_follower_floor": 250,
    "parent_adjust": {
        # START AT 2-3 COVARIATES (charter §8 ruling). The constitution's
        # 8-covariate model is over-parameterized at launch volume.
        "covariates": ["parent_size", "post_age", "market_intensity"],
        # The expansion is ENCODED AS CONFIG, not left to a future judgement
        # call: each extra covariate unlocks at a declared sample size.
        "expansion_pool": [
            "author_tier", "beat_fit", "time_of_day",
            "reply_family", "thread_saturation",
        ],
        # Rule of thumb the gate implements: one covariate per this many
        # samples. 3 covariates therefore need 120 rows before a 4th is legal.
        "samples_per_covariate": 40,
        # A stratum thinner than this yields adjusted=None with the reason
        # printed. A null is printed, never hidden (house epistemics law).
        "stratum_n_floor": 5,
        "buckets": {
            # Parent size: engagement on the PARENT post at draft time.
            "parent_size": [50, 500],
            # Post age at draft time, in minutes (charter §3's 5-15 window).
            "post_age": [5, 15],
            # Market intensity: breaking+wire emissions on the day.
            "market_intensity": [3, 12],
        },
    },
}


def _cfg(cfg: dict | None) -> dict:
    """Merge ``config/marketing.yml`` ``learning:`` over the documented defaults."""
    raw = ((cfg or {}).get("learning") or {})
    out = dict(DEFAULTS)
    for key, val in raw.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            for k2, v2 in val.items():
                if isinstance(v2, dict) and isinstance(merged.get(k2), dict):
                    merged[k2] = {**merged[k2], **v2}
                else:
                    merged[k2] = v2
            out[key] = merged
        else:
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _root_path(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parent.parent.parent
    return Path(root)


def repo_dir(root: Path | str | None = None) -> Path:
    """The TRACKED ledger dir. Only ``consolidate()`` may write here."""
    return _root_path(root) / "data" / "marketing" / "learning"


def host_dir(root: Path | str | None = None) -> Path:
    """The GITIGNORED intraday spool (see ``.gitignore``).

    Same posture as ``persona_memory.host_dir`` and the outbox's host spool: a
    gitignored sibling, so the VPS daemon can append at tick cadence without
    dirtying a checkout that ``git pull``s every three minutes.
    """
    return _root_path(root) / "data" / "marketing" / "learning_host"


def labels_path(root: Path | str | None = None) -> Path:
    return repo_dir(root) / "labels.jsonl"


def scorecard_path(root: Path | str | None = None) -> Path:
    return repo_dir(root) / "scorecard.json"


def _host_labels_path(root: Path | str | None = None) -> Path:
    return host_dir(root) / "labels.jsonl"


def _post_metrics_path(root: Path | str | None = None) -> Path:
    """The LIVE ledger — written by scripts/marketing_metrics_poll.py and
    committed back by .github/workflows/marketing-publish.yml."""
    return _root_path(root) / "data" / "marketing" / "post_metrics.jsonl"


# ---------------------------------------------------------------------------
# JSONL I/O — fail-soft on read, atomic on write
# ---------------------------------------------------------------------------
def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 — a torn final line must not
                    continue       # blind us to the good rows above it
                if isinstance(rec, dict):
                    out.append(rec)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []
    return out


def _write_tracked(path: Path, rows: Sequence[dict]) -> None:
    """Atomic replace of a TRACKED ledger. Called ONLY by ``consolidate()``.

    One private helper so the AST guard has exactly one symbol to allowlist and
    a second tracked writer cannot appear by accident.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".lb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _write_tracked_json(path: Path, payload: dict) -> None:
    """Atomic replace of a TRACKED json artifact. ``consolidate()`` only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".lb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def _spool_lock(root: Path | str | None, timeout_s: float = 2.0):
    """Advisory flock over the host spool (persona_memory posture).

    The read->write->truncate window is the race: a daemon appending between the
    read and the unlink loses that row outright. Fail-soft — a lock we cannot
    take must never stop the nightly from advancing ledgers.
    """
    lock_fh = None
    acquired = False
    try:
        try:
            import fcntl  # noqa: PLC0415  (POSIX only; fail-soft elsewhere)

            d = host_dir(root)
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
                            "::warning title=labels::host spool lock busy after "
                            f"{timeout_s:.1f}s — consolidating unlocked; a concurrent "
                            "append may be lost",
                            flush=True,
                        )
                        break
                    time.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            print(
                f"::warning title=labels::advisory lock unavailable ({exc}) — "
                "consolidating unlocked",
                flush=True,
            )
        yield acquired
    finally:
        if lock_fh is not None:
            with contextlib.suppress(Exception):
                if acquired:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                lock_fh.close()


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _parse_iso(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    for candidate in (s, s.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], _DAY_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _day(value: object) -> str:
    return str(value or "")[:10]


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Row identity + shape
# ---------------------------------------------------------------------------
def row_id(row: dict) -> str:
    """Stable identity for dedup at consolidation.

    An explicit ``id`` wins. Otherwise the (surface, subject, day) triple — NOT
    the observation timestamp, which is wall-clock and would let a retried
    nightly land the same post twice and double every cell's n.
    """
    rid = str(row.get("id") or "").strip()
    if rid:
        return rid
    basis = f"{row.get('surface','')}|{row.get('subject_id','')}|{_day(row.get('as_of'))}"
    return "lb-" + hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16]  # noqa: S324


def new_row(**over: Any) -> dict:
    """The label row shape. THE constructor — two modules build rows.

    Public because ``reply_producer`` builds rows too: a second module
    hand-rolling the dict is how a store grows two schemas that agree until
    they don't.

    Deliberately L2-RETRAIN-SHAPED and nothing more (the retrain job is out of
    scope this wave — there is no labels corpus yet). ``features`` is the
    inspectable feature vector a future ranker would train on, ``label`` is the
    supervised target, ``weight`` lets a retrain down-weight thin strata, and
    ``label_version`` makes a corpus rebuild diffable. Leaving these shaped now
    costs nothing; retrofitting them onto months of rows costs the corpus.
    """
    row: dict[str, Any] = {
        "schema": LABEL_SCHEMA,
        "label_version": 1,
        "surface": "",          # "post" | "reply"
        "subject_id": "",       # outbox item id / reply queue item id
        "as_of": "",
        "account": "",
        "format": "",           # outbox kind, or "reply"
        "register": "",         # expression-dial level name
        "hook_family": "",      # franchise id, or the reply family
        "observed": {},         # raw counters, exactly as polled
        "features": {},         # deterministic inputs (no LLM, ever)
        "label": None,          # supervised target in [0, 1] or None
        "weight": 1.0,
        "covariates": {},       # parent-adjustment strata
        "adjusted": None,       # parent-adjusted lift, or None with a reason
        "adjusted_reason": None,
        "observed_at": "",
    }
    row.update(over)
    row["id"] = row_id(row)
    return row


def validate_row(row: dict) -> list[str]:
    """Errors in a label row; [] means valid."""
    errors: list[str] = []
    if not isinstance(row, dict):
        return ["row must be a mapping"]
    if row.get("schema") != LABEL_SCHEMA:
        errors.append(f"schema must be {LABEL_SCHEMA!r}; got {row.get('schema')!r}")
    if str(row.get("surface") or "") not in {"post", "reply"}:
        errors.append(f"surface must be 'post' or 'reply'; got {row.get('surface')!r}")
    for field in ("subject_id", "as_of", "account"):
        if not str(row.get(field) or "").strip():
            errors.append(f"field {field!r} must be non-empty")
    if not isinstance(row.get("observed"), dict):
        errors.append("observed must be a dict")
    if not isinstance(row.get("features"), dict):
        errors.append("features must be a dict (inspectable: charter §8)")
    label = row.get("label")
    if label is not None and not isinstance(label, (int, float)):
        errors.append("label must be numeric or None")
    return errors


# ---------------------------------------------------------------------------
# Intraday write path (host spool only)
# ---------------------------------------------------------------------------
def record_observation(row: dict, *, root: Path | str | None = None) -> dict:
    """Append ONE observation to the HOST spool. The only intraday write path.

    Called by ``reply_producer`` at enqueue time to bank the deterministic
    draft-time features (the covariates a later outcome has to be adjusted
    against, which are unrecoverable once the thread has moved on). Invalid rows
    are refused rather than written — a corpus is only worth what its worst row
    is worth.
    """
    errors = validate_row(row)
    if errors:
        log.warning("labels.record_observation: refusing invalid row: %s", errors)
        return {"ok": False, "errors": errors}
    d = host_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(_host_labels_path(root), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True, "id": row["id"]}


# ---------------------------------------------------------------------------
# Dimension resolution
# ---------------------------------------------------------------------------
#: Expression-dial level -> the register name the scorecard groups on. The dial
#: is the house's own register authority (0 = wire voice, 1 = analysis, 2 =
#: persona-forward), so the scorecard reuses it rather than inventing a scale.
REGISTER_NAMES: dict[int, str] = {0: "wire", 1: "analysis", 2: "persona"}


def register_for(kind: str, *, account: str, root: Path | str | None = None) -> str:
    """The register name for one (account, kind), via the expression dial.

    Fail-soft: an account with no codex (a dark or planned desk) reports
    ``"unknown"`` rather than guessing. An unknown register is printed in the
    scorecard, not silently folded into ``analysis``.
    """
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        codex = _dial.codex_for(str(account), root=root)
        profile = getattr(codex, "dial_profile", None) if codex is not None else None
        if not profile:
            return "unknown"
        return REGISTER_NAMES.get(_dial.dial_for(str(kind), profile=str(profile)), "unknown")
    except Exception as exc:  # noqa: BLE001
        log.warning("labels.register_for: dial unavailable for %r/%r: %s", account, kind, exc)
        return "unknown"


def _hook_family_for(item: dict) -> str:
    """The hook family of an outbox item.

    XG-W3 put the franchise id in ``item["source"]["franchise"]`` (never as a
    kind — see ``franchises.py``), which is the closest thing the post rail has
    to a hook family. Falls back to the lane slug so a non-franchise post still
    lands in a named cell instead of an empty one.
    """
    src = item.get("source")
    src = src if isinstance(src, dict) else {}
    fr = src.get("franchise")
    if isinstance(fr, dict):
        fr = fr.get("id") or fr.get("franchise")
    fam = str(fr or "").strip()
    if fam:
        return fam
    return str(item.get("provenance") or "unattributed").strip() or "unattributed"


# ---------------------------------------------------------------------------
# Harvest: posts (from the LIVE metrics poll)
# ---------------------------------------------------------------------------
def _latest_metrics_by_remote_id(root: Path | str | None) -> dict[str, dict]:
    """Fold post_metrics.jsonl to the newest row per Buffer post id.

    Same fold the admin publisher panel uses (``admin/marketing.py``
    ``_latest_metrics_by_remote_id``). Metrics are CUMULATIVE, so the latest
    poll is the current truth and older rows are history, not evidence.
    """
    out: dict[str, dict] = {}
    best: dict[str, str] = {}
    for row in _read_jsonl(_post_metrics_path(root)):
        rid = str(row.get("remote_id") or "").strip()
        if not rid:
            continue
        ts = str(row.get("polled_at") or "")
        if rid in best and ts < best[rid]:
            continue
        best[rid] = ts
        out[rid] = row
    return out


def _engagement(metrics: dict) -> int:
    return (_int(metrics.get("likes")) + _int(metrics.get("reposts"))
            + _int(metrics.get("comments")) + _int(metrics.get("replies")))


def _post_label(metrics: dict) -> tuple[float | None, str | None]:
    """Supervised target for a post: engagement per impression.

    Returns (label, reason_when_null). ZERO IMPRESSIONS IS NOT A ZERO RATE —
    it is an unmeasured post, and folding it in as 0.0 would drag every cell
    median toward zero in exact proportion to how many posts the poller had not
    yet seen. The null is printed instead (house epistemics law: endpoint-null
    is not one half, and it is not zero either).
    """
    impressions = _int(metrics.get("impressions"))
    if impressions <= 0:
        return None, "no_impressions_yet"
    return round(_engagement(metrics) / impressions, 6), None


def harvest_post_labels(
    *,
    root: Path | str | None = None,
    cfg: dict | None = None,
    now: datetime,
) -> list[dict]:
    """Per-post label rows from the LIVE metrics poll, joined to the outbox.

    The join is receipt-based: ``post_metrics.remote_id`` is the Buffer post id,
    which the outbox status ledger carries as ``receipt.external_id`` on every
    ``posted`` transition. A metrics row whose id has no outbox item is an
    ORPHAN and is kept with ``format="unknown"`` rather than dropped — an
    unattributable post is a fact about our provenance, not a row to hide.
    """
    metrics_by_id = _latest_metrics_by_remote_id(root)
    if not metrics_by_id:
        return []

    # Receipt id -> outbox item, from the fold the publisher already maintains.
    item_by_remote: dict[str, dict] = {}
    posted_day: dict[str, str] = {}
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        state = _ob.fold_state(_root_path(root))
        items = state.get("items") or {}
        last = state.get("last") or {}
        for iid, st in (state.get("status") or {}).items():
            if st != "posted":
                continue
            rec = (last.get(iid) or {}).get("receipt")
            rec = rec if isinstance(rec, dict) else {}
            remote = str(rec.get("external_id") or "").strip()
            if not remote:
                continue
            item_by_remote[remote] = items.get(iid) or {}
            posted_day[remote] = _day(rec.get("at") or (last.get(iid) or {}).get("at"))
    except Exception as exc:  # noqa: BLE001
        log.warning("labels.harvest_post_labels: outbox fold unavailable: %s", exc)

    intensity = _market_intensity_by_day(root)
    observed_at = _as_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[dict] = []
    for remote, mrow in sorted(metrics_by_id.items()):
        metrics = mrow.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        item = item_by_remote.get(remote) or {}
        account = str(item.get("account") or mrow.get("account") or "").strip()
        if not account:
            continue
        kind = str(item.get("kind") or item.get("type") or "unknown")
        as_of = _day(item.get("as_of") or posted_day.get(remote) or mrow.get("polled_at"))
        label, reason = _post_label(metrics)
        rows.append(new_row(
            surface="post",
            subject_id=str(item.get("id") or remote),
            as_of=as_of,
            account=account,
            format=kind,
            register=register_for(kind, account=account, root=root),
            hook_family=_hook_family_for(item),
            observed={
                "impressions": _int(metrics.get("impressions")),
                "likes": _int(metrics.get("likes")),
                "reposts": _int(metrics.get("reposts")),
                "comments": _int(metrics.get("comments")),
                "clicks": _int(metrics.get("clicks")),
                "remote_id": remote,
                "orphan": remote not in item_by_remote,
            },
            features={
                "slot": str(item.get("slot") or ""),
                "has_media": bool(item.get("media")),
                "priority": _int(item.get("priority"), 5),
                "market_intensity": _int(intensity.get(as_of)),
            },
            label=label,
            weight=1.0,
            observed_at=observed_at,
        ))
        if reason:
            rows[-1]["adjusted_reason"] = reason
    return rows


def _market_intensity_by_day(root: Path | str | None) -> dict[str, int]:
    """Breaking + wire emissions per day — the MEASURED market-intensity input.

    Charter §2 amendment 10 (a crowd-state claim requires a measured input)
    applies to covariates too: "market intensity" has to be counted from
    something, and the wire/breaking emission count is a number we already own.
    """
    out: dict[str, int] = {}
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        for item in (_ob.fold_state(_root_path(root)).get("items") or {}).values():
            if str(item.get("kind") or "") not in {"breaking", "wire"}:
                continue
            day = _day(item.get("as_of"))
            if day:
                out[day] = out.get(day, 0) + 1
    except Exception as exc:  # noqa: BLE001
        log.warning("labels._market_intensity_by_day: outbox unavailable: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Harvest: replies (from the reply desk's host store)
# ---------------------------------------------------------------------------
def _reply_label(outcome: dict) -> tuple[float | None, str | None]:
    """Supervised target for a reply: did the parent author answer.

    Charter §3: "Author reply-back is the highest-value outcome; relationship
    tier > vanity reach." So the label IS the reply-back, not the like count.
    An item with no outcome row yet is NULL, not 0.0 — a reply we have not
    polled and a reply that was ignored are different facts, and collapsing
    them makes every early cohort look like a failure.
    """
    if outcome.get("author_replied") is None:
        return None, "outcome_not_polled"
    return (1.0 if outcome.get("author_replied") else 0.0), None


def harvest_reply_labels(
    *,
    store: Path | str | None = None,
    root: Path | str | None = None,
    cfg: dict | None = None,
    now: datetime,
) -> list[dict]:
    """Per-reply label rows from the reply desk's HOST store.

    ``store`` is the reply desk's host-state root (``reply_queue.state_dir``);
    ``root`` is the repo checkout. The two are different directories and
    conflating them is how a poller ends up dirtying the render tree.

    Only SENT items produce labels: a draft that never left says nothing about
    what the audience does, and counting it would make the denominator our own
    productivity rather than our reach.
    """
    try:
        from engine.marketing import reply_queue as _rq  # noqa: PLC0415

        state = _rq.fold_state(store)
        outcomes = _rq.outcomes(store)
    except Exception as exc:  # noqa: BLE001
        log.warning("labels.harvest_reply_labels: reply store unavailable: %s", exc)
        return []

    intensity = _market_intensity_by_day(root)
    observed_at = _as_utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[dict] = []
    for iid, item in sorted(state.get("items", {}).items()):
        if state.get("status", {}).get(iid) != "sent":
            continue
        account = str(item.get("account") or "").strip()
        if not account:
            continue
        outcome = outcomes.get(iid) or {}
        label, reason = _reply_label(outcome)
        # Draft-time score features were banked on the item by the producer, so
        # the covariates survive even after the thread has moved on.
        feats = item.get("score_features")
        feats = feats if isinstance(feats, dict) else {}
        ctx = feats.get("_context")
        ctx = ctx if isinstance(ctx, dict) else {}
        as_of = _day(item.get("as_of"))
        rows.append(new_row(
            surface="reply",
            subject_id=iid,
            as_of=as_of,
            account=account,
            format="reply",
            register=register_for("reply", account=account, root=root),
            hook_family=str(item.get("family") or "unassigned"),
            observed={
                "author_replied": outcome.get("author_replied"),
                "likes": outcome.get("likes"),
                "follower_delta": outcome.get("follower_delta"),
                "sent_at": outcome.get("sent_at") or item.get("sent_at"),
                "tier": item.get("tier"),
            },
            features={
                "score": _float(item.get("score")),
                "tier": str(item.get("tier") or ""),
                "has_chart": bool(item.get("chart")),
                "parent_engagement": _float(ctx.get("engagement")),
                "post_age_min": ctx.get("age_min"),
                "market_intensity": _int(intensity.get(as_of)),
            },
            label=label,
            weight=1.0,
            observed_at=observed_at,
        ))
        if reason:
            rows[-1]["adjusted_reason"] = reason
    return rows


# ---------------------------------------------------------------------------
# Parent-adjusted labels (charter §8: 2-3 covariates at launch volume)
# ---------------------------------------------------------------------------
def _bucket(value: float | None, edges: Sequence[float]) -> str:
    """Name the stratum a value falls in. ``None`` is its own stratum.

    An unknown covariate is NOT folded into the low bucket: "we did not observe
    the parent's size" and "the parent was small" are different facts, and
    merging them puts unmeasured rows into a stratum they may not belong to.
    """
    if value is None:
        return "unknown"
    lo = f"lt{_num(edges[0])}"
    if value < float(edges[0]):
        return lo
    for i in range(len(edges) - 1):
        if value < float(edges[i + 1]):
            return f"{_num(edges[i])}to{_num(edges[i + 1])}"
    return f"ge{_num(edges[-1])}"


def _num(v: float) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _covariate_values(row: dict) -> dict[str, float | None]:
    """The raw covariate readings a row carries, before bucketing."""
    feats = row.get("features") or {}
    return {
        "parent_size": _opt_float(feats.get("parent_engagement")),
        "post_age": _opt_float(feats.get("post_age_min")),
        "market_intensity": _opt_float(feats.get("market_intensity")),
        # Expansion pool — read now so an expansion is a config edit, not a
        # code change. Absent readings bucket as "unknown" like any other.
        "author_tier": _tier_rank(feats.get("tier")),
        "beat_fit": _opt_float(feats.get("beat_fit")),
        "time_of_day": _hour_of(row.get("observed", {}).get("sent_at")),
        "reply_family": None,
        "thread_saturation": _opt_float(feats.get("thread_saturation")),
    }


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


_TIER_RANKS: dict[str, float] = {
    "relationship": 3.0, "inbound": 2.5, "conversion": 2.0, "breakout": 1.0,
}


def _tier_rank(value: object) -> float | None:
    return _TIER_RANKS.get(str(value or "").strip().lower())


def _hour_of(value: object) -> float | None:
    dt = _parse_iso(value)
    return float(dt.hour) if dt is not None else None


def active_covariates(rows: Sequence[dict], *, cfg: dict | None = None,
                      announce: bool = True) -> tuple[list[str], dict]:
    """Which covariates the current sample size actually supports.

    THE 8-COVARIATE MODEL IS OVER-PARAMETERIZED AT LAUNCH (charter §8). The
    expansion is encoded here rather than deferred to a judgement call: the
    configured list is truncated to ``n // samples_per_covariate``, floored at
    one, and the truncation is ANNOUNCED. A config that asks for five covariates
    on forty rows gets one and is told so, instead of silently fitting noise.
    """
    conf = _cfg(cfg)["parent_adjust"]
    want = [str(c) for c in (conf.get("covariates") or [])]
    per = max(1, _int(conf.get("samples_per_covariate"), 40))
    n = sum(1 for r in rows if r.get("label") is not None)
    allowed = max(1, n // per)
    meta = {
        "requested": list(want),
        "n_labelled": n,
        "samples_per_covariate": per,
        "max_supported": allowed,
        "expansion_pool": list(conf.get("expansion_pool") or []),
    }
    # Announce a real truncation only. With ZERO labelled rows there is nothing
    # to over-parameterize, and warning about it every night on an empty store
    # trains the operator to ignore the annotation that matters later.
    if announce and len(want) > allowed and n > 0:
        print(
            f"::warning title=labels-covariates::parent adjustment requested "
            f"{len(want)} covariates on {n} labelled rows — {allowed} supported at "
            f"{per} samples each; using {want[:allowed]} (charter §8: the "
            f"8-covariate model is over-parameterized at launch volume)",
            flush=True,
        )
    meta["active"] = want[:allowed]
    return list(meta["active"]), meta


def parent_adjust(rows: list[dict], *, cfg: dict | None = None) -> list[dict]:
    """Stratified parent adjustment. Returns the SAME rows, adjusted in place-copy.

    Deliberately a STRATIFIED LIFT, not a regression. With launch-scale samples
    a fitted model would be reporting its own priors back to us; a lift against
    the mean of the row's own stratum is arithmetic anyone can check by hand:

        adjusted = label - mean(label over the same covariate cell)

    A stratum thinner than ``stratum_n_floor`` yields ``adjusted=None`` with
    ``adjusted_reason`` set. Nulls are PRINTED, not hidden.
    """
    conf = _cfg(cfg)["parent_adjust"]
    buckets = conf.get("buckets") or {}
    floor = max(1, _int(conf.get("stratum_n_floor"), 5))
    active, _meta = active_covariates(rows, cfg=cfg)

    def _edges_for(name: str) -> Sequence[float]:
        edges = buckets.get(name)
        return edges if isinstance(edges, (list, tuple)) and edges else [0]

    out = [dict(r) for r in rows]
    for row in out:
        vals = _covariate_values(row)
        row["covariates"] = {c: _bucket(vals.get(c), _edges_for(c)) for c in active}

    strata: dict[tuple, list[float]] = {}
    for row in out:
        if row.get("label") is None:
            continue
        key = tuple(sorted((row.get("covariates") or {}).items()))
        strata.setdefault(key, []).append(float(row["label"]))

    for row in out:
        if row.get("label") is None:
            row["adjusted"] = None
            # Keep a harvest-time reason ("no_impressions_yet",
            # "outcome_not_polled") if one is already there — it says WHY the
            # label is missing, which is strictly more useful than "it is".
            if not row.get("adjusted_reason"):
                row["adjusted_reason"] = "label_null"
            continue
        key = tuple(sorted((row.get("covariates") or {}).items()))
        peers = strata.get(key) or []
        if len(peers) < floor:
            row["adjusted"] = None
            row["adjusted_reason"] = f"stratum_n_{len(peers)}_below_floor_{floor}"
            continue
        row["adjusted"] = round(float(row["label"]) - statistics.fmean(peers), 6)
        row["adjusted_reason"] = None
        row["stratum_n"] = len(peers)
    return out


# ---------------------------------------------------------------------------
# The scorecard — hook family x format x register x account
# ---------------------------------------------------------------------------
def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def scorecard(rows: list[dict], *, cfg: dict | None = None, now: datetime) -> dict:
    """The weekly operator scorecard. One artifact, four named consumers.

    N-floor law: a cell with fewer than ``n_floor`` labelled rows carries
    ``verdict="seeding"`` and no ranking claim. The cell is still PRINTED —
    hiding thin cells is how a surface starts looking more certain than it is.
    """
    conf = _cfg(cfg)
    floor = max(1, _int(conf.get("n_floor"), DEFAULT_N_FLOOR))
    window = max(1, _int(conf.get("scorecard_window_days"), 7))
    cutoff = (_as_utc(now) - timedelta(days=window)).strftime(_DAY_FMT)

    in_window = [r for r in rows if _day(r.get("as_of")) >= cutoff]

    cells: dict[tuple, dict] = {}
    for row in in_window:
        key = tuple(str(row.get(d) or "unknown") for d in DIMS)
        cell = cells.setdefault(key, {
            "dims": dict(zip(DIMS, key)),
            "n": 0, "n_labelled": 0, "n_null": 0,
            "_labels": [], "_adjusted": [], "_impressions": [],
        })
        cell["n"] += 1
        if row.get("label") is None:
            cell["n_null"] += 1
        else:
            cell["n_labelled"] += 1
            cell["_labels"].append(float(row["label"]))
        if row.get("adjusted") is not None:
            cell["_adjusted"].append(float(row["adjusted"]))
        imp = (row.get("observed") or {}).get("impressions")
        if isinstance(imp, int) and imp > 0:
            cell["_impressions"].append(float(imp))

    out_cells: list[dict] = []
    for cell in cells.values():
        entry = {
            "dims": cell["dims"],
            "n": cell["n"],
            "n_labelled": cell["n_labelled"],
            "n_null": cell["n_null"],
            "med_label": _median(cell["_labels"]),
            "med_adjusted": _median(cell["_adjusted"]),
            "med_impressions": _median(cell["_impressions"]),
        }
        if cell["n_labelled"] < floor:
            entry["verdict"] = "seeding"
            entry["verdict_note"] = (
                f"{cell['n_labelled']} labelled rows against an n-floor of {floor} — "
                "no ranking claim is made from this cell"
            )
        out_cells.append(entry)
    out_cells.sort(key=lambda c: (-int(c["n"]), tuple(sorted(c["dims"].items()))))

    # announce=False: `parent_adjust` already warned about any truncation on
    # this same corpus during the nightly. Two identical annotations per run
    # reads as two problems.
    _active, cov_meta = active_covariates(in_window, cfg=cfg, announce=False)
    return {
        "schema": SCORECARD_SCHEMA,
        "produced_by": "engine/marketing/labels.py",
        "as_of": _as_utc(now).strftime(_DAY_FMT),
        "window_days": window,
        "n_floor": floor,
        "consumers": list(CONSUMERS),
        "dims": list(DIMS),
        "n_rows": len(in_window),
        "n_rows_all_time": len(rows),
        "cells": out_cells,
        "covariates": cov_meta,
        "bottleneck": bottleneck_table(in_window, cfg=cfg, now=now),
        "north_star": north_star(in_window, cfg=cfg, now=now),
        "note": (
            "Operator console artifact. No score or label on this surface is "
            "user-facing, and nothing in site/ reads this file."
        ),
    }


def bottleneck_table(rows: list[dict], *, cfg: dict | None = None, now: datetime) -> dict:
    """The cold-start instrument: RAW COUNTS, per account, no ratios.

    Charter §8 ruling: the north-star metric is undefined at zero, so during
    cold start the simple bottleneck table on raw counts is what the operator
    reads. Ratios over a follower base of ~0 are noise wearing a decimal point.
    """
    per: dict[str, dict] = {}
    for row in rows:
        acc = str(row.get("account") or "unknown")
        block = per.setdefault(acc, {
            "account": acc, "contributions": 0, "measured": 0, "unmeasured": 0,
            "impressions": 0, "engagements": 0, "replies_sent": 0, "author_replies": 0,
        })
        block["contributions"] += 1
        if row.get("label") is None:
            block["unmeasured"] += 1
        else:
            block["measured"] += 1
        obs = row.get("observed") or {}
        block["impressions"] += _int(obs.get("impressions"))
        block["engagements"] += (_int(obs.get("likes")) + _int(obs.get("reposts"))
                                 + _int(obs.get("comments")))
        if row.get("surface") == "reply":
            block["replies_sent"] += 1
            if obs.get("author_replied"):
                block["author_replies"] += 1
    return {
        "basis": "raw_counts",
        "why": (
            "north-star (qualified retained followers per 100 contributions) is "
            "undefined at zero followers — charter §8"
        ),
        "accounts": sorted(per.values(), key=lambda b: b["account"]),
    }


def north_star(rows: list[dict], *, cfg: dict | None = None, now: datetime) -> dict:
    """Qualified retained followers per 100 contributions — INACTIVE at cold start.

    Returns ``{"active": False, ...}`` until an account clears the configured
    follower floor. The metric is not computed-and-hidden: it is not computed,
    and the reason is printed. A ratio whose denominator is zero is not a small
    number, it is not a number.
    """
    conf = _cfg(cfg)
    floor = _int(conf.get("north_star_follower_floor"), 250)
    followers: dict[str, int] = {}
    for row in rows:
        acc = str(row.get("account") or "unknown")
        obs = row.get("observed") or {}
        fa = obs.get("followers_at_post")
        if isinstance(fa, int):
            followers[acc] = max(followers.get(acc, 0), fa)
    eligible = sorted(a for a, f in followers.items() if f >= floor)
    if not eligible:
        return {
            "active": False,
            "follower_floor": floor,
            "observed_followers": followers,
            "reason": (
                "no account clears the follower floor — undefined at zero; read "
                "the bottleneck table on raw counts instead (charter §8)"
            ),
        }
    per: dict[str, dict] = {}
    for acc in eligible:
        contribs = sum(1 for r in rows if str(r.get("account") or "") == acc)
        per[acc] = {
            "contributions": contribs,
            "followers_observed": followers[acc],
            "per_100": None,
            "note": (
                "retention needs a follower-cohort series the poller does not "
                "yet return; the denominator is live, the numerator is not"
            ),
        }
    return {"active": True, "follower_floor": floor, "accounts": per}


# ---------------------------------------------------------------------------
# THE CONSOLIDATOR — the only writer of data/marketing/learning/
# ---------------------------------------------------------------------------
def load_labels(root: Path | str | None = None) -> list[dict]:
    """The tracked corpus. Readers get the tracked ledger PLUS the host spool,
    so a same-day consumer is never blind to today's un-consolidated rows."""
    return _read_jsonl(labels_path(root)) + _read_jsonl(_host_labels_path(root))


def load_scorecard(root: Path | str | None = None) -> dict:
    try:
        return json.loads(scorecard_path(root).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def consolidate(
    *,
    now: datetime,
    root: Path | str | None = None,
    store: Path | str | None = None,
    cfg: dict | None = None,
    clear_host: bool = True,
) -> dict[str, Any]:
    """Advance the TRACKED labels ledger + scorecard. NIGHTLY ONLY.

    Sole writer of ``data/marketing/learning/`` (charter §2 amendment 13). It is
    idempotent: rows dedup on ``row_id``, so a retried nightly cannot double a
    cell's n — which matters because those n's are what the n-floor gates on.

    Order: harvest post labels (LIVE metrics poll) + reply labels (reply desk
    host store) + the intraday host spool, merge, parent-adjust, write, then
    truncate the spool AFTER the tracked write lands so an interrupted run
    loses nothing.
    """
    flag = os.environ.get("MARKETING_LEARNING_ENABLED")
    if flag is not None and flag.strip().lower() in ("0", "false", "no", "off"):
        print(
            f"::notice title=labels::MARKETING_LEARNING_ENABLED={flag!r} — skipping "
            "consolidation; tracked label ledgers not advanced",
            flush=True,
        )
        return {"as_of": _as_utc(now).isoformat(), "skipped": "disabled"}

    with _spool_lock(root):
        return _consolidate_locked(now=now, root=root, store=store, cfg=cfg,
                                   clear_host=clear_host)


def _consolidate_locked(
    *,
    now: datetime,
    root: Path | str | None,
    store: Path | str | None,
    cfg: dict | None,
    clear_host: bool,
) -> dict[str, Any]:
    conf = _cfg(cfg)
    retention = max(1, _int(conf.get("retention_days"), RETENTION_DAYS))
    cutoff = (_as_utc(now) - timedelta(days=retention)).strftime(_DAY_FMT)

    tracked = _read_jsonl(labels_path(root))
    host = _read_jsonl(_host_labels_path(root))
    harvested_posts = harvest_post_labels(root=root, cfg=cfg, now=now)
    harvested_replies = harvest_reply_labels(store=store, root=root, cfg=cfg, now=now)

    # LAST WINS on a repeated id: a re-harvest of the same post carries fresher
    # cumulative counters, and the freshest observation is the current truth.
    merged: dict[str, dict] = {}
    for row in tracked + host + harvested_posts + harvested_replies:
        if not isinstance(row, dict):
            continue
        day = _day(row.get("as_of"))
        if day and day < cutoff:
            continue
        merged[row_id(row)] = row

    rows = sorted(merged.values(), key=lambda r: (_day(r.get("as_of")), str(r.get("id"))))
    rows = parent_adjust(rows, cfg=cfg)

    _write_tracked(labels_path(root), rows)
    card = scorecard(rows, cfg=cfg, now=now)
    _write_tracked_json(scorecard_path(root), card)

    if clear_host and host:
        with contextlib.suppress(OSError):
            _host_labels_path(root).unlink()

    return {
        "as_of": _as_utc(now).isoformat(),
        "tracked_before": len(tracked),
        "host": len(host),
        "harvested_posts": len(harvested_posts),
        "harvested_replies": len(harvested_replies),
        "tracked_after": len(rows),
        "cells": len(card.get("cells") or []),
        "labels_path": str(labels_path(root)),
        "scorecard_path": str(scorecard_path(root)),
    }


__all__ = [
    "LABEL_SCHEMA", "SCORECARD_SCHEMA", "CONSUMERS", "DIMS", "DEFAULTS",
    "REGISTER_NAMES", "DEFAULT_N_FLOOR", "RETENTION_DAYS",
    "host_dir", "repo_dir", "labels_path", "scorecard_path",
    "new_row", "row_id", "validate_row", "record_observation", "register_for",
    "harvest_post_labels", "harvest_reply_labels",
    "active_covariates", "parent_adjust", "scorecard", "bottleneck_table",
    "north_star", "consolidate", "load_labels", "load_scorecard",
]
