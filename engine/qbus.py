"""qbus — the unified qualitative item/event store (W2, spec §2.4 / §2.5 / probe P2).

LEAF · CONTEXT-ONLY · DETERMINISTIC. Imports only leaf primitives (engine.qkernel);
nothing in the scoring path imports it. Every public function returns plain data
and NEVER raises into the build. NO ambient-time calls in library code — every
`asof` is passed in by the caller (PIT discipline; matches the whole qual suite).

qbus is the ONE place a wire item lands after a desk ingests it, so the SAME story
is counted once across desks instead of three times. It provides:

  • ONE row schema with the [P2] timestamp_quality enum and a body-hash column.
  • Append storage at data/qbus/items.parquet, keep-FIRST on item_id (PIT: the
    first print of an item wins; restatements never overwrite the original seen
    time).
  • event_key clustering — cheap shingled-title similarity within a trailing window,
    scoped per entity/theme. NO embeddings, NO LLM in the hot path. Collapses
    restatements/mirrors of one story into a single event_key.
  • novelty_z(entity_or_theme, asof) — z-score of today's item volume for a
    subject vs its own trailing-window volume (the "is attention unusually high?"
    primitive).
  • echo_stats(event_key) → {n_sources, n_desks, first_seen, breadth} — the
    cross-desk corroboration primitive (how broadly was this ONE event carried?).

Nothing here is a scoring input; these are dedup / clustering / novelty / echo
context reads.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from engine import qkernel

log = logging.getLogger(__name__)

SCHEMA = "qbus.v1"

# --------------------------------------------------------------------------- #
# timestamp_quality enum [P2] — how trustworthy is an item's timestamp as an
# entry anchor. The grader (qledger, W1) reads this to pick embargo rules; qbus
# only stores and validates the value.
# --------------------------------------------------------------------------- #
TIMESTAMP_QUALITY = (
    "CRAWL_BOUNDED",     # only bounded by our crawl time (no publisher stamp) — no embargo
    "PUBLISHER_STATED",  # publisher-stated pubDate — +15min, reject pubDate < crawl−48h
    "DISCLOSURE_DATE",   # regulatory disclosure date (EDGAR) — +1 business day
    "EVENT_DATE",        # date the event refers to — NEVER an entry anchor
    "SNAPSHOT_DATE",     # a point-in-time snapshot — display-only
    "CORRUPTED",         # timestamp failed sanity checks — blocked + alert
)
_DEFAULT_TQ = "CRAWL_BOUNDED"

# --------------------------------------------------------------------------- #
# Row schema — the ONE item shape every desk writes through qbus. List/enum-valued
# fields (entities, themes) are stored as comma-joined strings in parquet and
# re-split on read (the china_news_intel precedent); callers pass Python lists.
# --------------------------------------------------------------------------- #
COLUMNS: tuple[str, ...] = (
    "item_id",            # qkernel.item_id(source,url,title) — keep-FIRST key
    "event_key",          # cross-source/desk story cluster id (assigned by clustering)
    "desk",               # emitting desk (financial_news, china_news_intel, …)
    "source",             # source token (em, rss, reuters, …)
    "source_tier",        # qkernel.source_tier → 1/2/3/0
    "lang",               # "en" | "zh" | "auto" (drives norm/shingle branch)
    "url",
    "title",
    "body_sha256",        # sha256 of the body when a body exists, else "" (nullable)
    "seendate",           # publisher/crawl timestamp (ISO), PIT-cleaned by the desk
    "_crawled_at",        # when WE first crawled the item (ISO, injected by caller)
    "timestamp_quality",  # one of TIMESTAMP_QUALITY
    "entities",           # comma-joined tickers/entity ids
    "themes",             # comma-joined theme ids
    "importance_raw",     # desk's own pre-calibration importance (float; display/context)
)

_LIST_FIELDS = ("entities", "themes")


def _events_path() -> Path:
    from lib import config
    p = config.data_dir() / "qbus" / "items.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def body_sha256(body: str | bytes | None) -> str:
    """sha256 hex of a body, or '' when there is no body. PURE."""
    if body is None or body == "" or body == b"":
        return ""
    b = body.encode("utf-8") if isinstance(body, str) else body
    return hashlib.sha256(b).hexdigest()


def _join(v) -> str:
    """List/tuple → comma-joined string; scalar → str. PURE."""
    if isinstance(v, (list, tuple, set)):
        return ",".join(str(x) for x in v if str(x))
    return "" if v is None else str(v)


def _split(v) -> list[str]:
    """Comma-joined string (or list) → list of non-empty tokens. PURE."""
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x)]
    return [x for x in str(v or "").split(",") if x]


# --------------------------------------------------------------------------- #
# Row normalization — coerce a caller dict into the canonical schema.
# --------------------------------------------------------------------------- #
def normalize_row(row: dict) -> dict:
    """Coerce a caller item dict into the canonical schema (fills item_id, tier,
    timestamp_quality; joins list fields). PURE (no clock — _crawled_at must be
    supplied by the caller). Never raises; missing fields default sanely."""
    source = str(row.get("source") or "")
    url = str(row.get("url") or "")
    title = str(row.get("title") or "")
    lang = str(row.get("lang") or "auto")
    iid = row.get("item_id") or qkernel.item_id(source, url, title, lang)

    tier = row.get("source_tier")
    if tier is None:
        tier = qkernel.source_tier(qkernel._host(url) or "", source)

    tq = str(row.get("timestamp_quality") or _DEFAULT_TQ)
    if tq not in TIMESTAMP_QUALITY:
        tq = _DEFAULT_TQ

    try:
        imp = float(row.get("importance_raw")) if row.get("importance_raw") is not None else 0.0
    except (TypeError, ValueError):
        imp = 0.0

    return {
        "item_id": str(iid),
        "event_key": str(row.get("event_key") or ""),
        "desk": str(row.get("desk") or ""),
        "source": source,
        "source_tier": int(tier or 0),
        "lang": lang,
        "url": url,
        "title": title,
        "body_sha256": str(row.get("body_sha256") or ""),
        "seendate": str(row.get("seendate") or ""),
        "_crawled_at": str(row.get("_crawled_at") or ""),
        "timestamp_quality": tq,
        "entities": _join(row.get("entities")),
        "themes": _join(row.get("themes")),
        "importance_raw": imp,
    }


# --------------------------------------------------------------------------- #
# event_key clustering — cheap shingled-title similarity within a trailing window,
# scoped per shared entity/theme. NO embeddings, NO LLM. Deterministic.
# --------------------------------------------------------------------------- #
def _norm_rows(rows: list[dict]) -> list[dict]:
    return [normalize_row(r) for r in rows]


def _crawl_day(r: dict) -> str:
    return (str(r.get("seendate") or "")[:10] or str(r.get("_crawled_at") or "")[:10])


def _shares_subject(a: dict, b: dict) -> bool:
    """True if two rows share at least one entity OR one theme. PURE."""
    ea, eb = set(_split(a.get("entities"))), set(_split(b.get("entities")))
    if ea & eb:
        return True
    ta, tb = set(_split(a.get("themes"))), set(_split(b.get("themes")))
    return bool(ta & tb)


def assign_event_keys(rows: list[dict], thresh: float = 0.6,
                      window_days: int = 3) -> list[dict]:
    """Assign an `event_key` to each row by collapsing near-duplicate/restatement
    titles. Two rows join the same cluster when they SHARE an entity-or-theme AND
    their crawl days are within `window_days` AND their shingled-title Jaccard
    (qkernel.title_similarity, language-aware) ≥ thresh.

    The event_key is a stable 16-char hash of the cluster REPRESENTATIVE (lowest
    source_tier value, then earliest _crawled_at, then item_id) so it is
    deterministic regardless of input order within a cluster. Returns NEW row dicts
    with event_key set. PURE (no clock). Never raises."""
    norm = _norm_rows(rows)
    # index each row's shingles + parsed crawl day-ordinal once.
    shs = [qkernel.shingles(r.get("title", ""), r.get("lang", "auto")) for r in norm]

    def _ord(r: dict) -> int | None:
        d = _crawl_day(r)
        try:
            return date.fromisoformat(d).toordinal() if d else None
        except (ValueError, TypeError):
            return None

    ords = [_ord(r) for r in norm]

    parent = list(range(len(norm)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    n = len(norm)
    for i in range(n):
        for j in range(i + 1, n):
            if not _shares_subject(norm[i], norm[j]):
                continue
            oi, oj = ords[i], ords[j]
            if oi is not None and oj is not None and abs(oi - oj) > window_days:
                continue
            if qkernel.jaccard(shs[i], shs[j]) >= thresh:
                union(i, j)

    # collect clusters, pick a deterministic representative, hash it into a key.
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    out = [dict(r) for r in norm]
    for members in clusters.values():
        rep_i = min(members, key=lambda k: (int(norm[k].get("source_tier") or 9),
                                            str(norm[k].get("_crawled_at") or ""),
                                            str(norm[k].get("item_id") or "")))
        rep = norm[rep_i]
        basis = (qkernel.norm_title(rep.get("title", ""), rep.get("lang", "auto"))
                 + "|" + str(rep.get("item_id", "")))
        key = "ev_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:13]
        for k in members:
            out[k]["event_key"] = key
    return out


# --------------------------------------------------------------------------- #
# append storage — keep-FIRST on item_id (PIT discipline)
# --------------------------------------------------------------------------- #
def append_items(rows: list[dict], assign_keys: bool = True,
                 cluster_thresh: float = 0.6, window_days: int = 3):
    """Normalize `rows`, (optionally) assign event_keys within the batch, and
    append to data/qbus/items.parquet keeping the FIRST occurrence of each item_id
    (the original print wins — a restatement never overwrites the seen time).

    Returns the merged DataFrame (or None on failure). Deterministic: no clock read
    — callers stamp `_crawled_at`. Never raises into the build."""
    try:
        import pandas as pd
        norm = assign_event_keys(rows, cluster_thresh, window_days) if assign_keys \
            else _norm_rows(rows)
        new_df = pd.DataFrame(norm, columns=list(COLUMNS))
        path = _events_path()
        if path.exists():
            existing = pd.read_parquet(path).reindex(columns=list(COLUMNS))
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = new_df
        merged = merged.drop_duplicates(subset=["item_id"], keep="first")
        merged = merged.sort_values(["_crawled_at", "item_id"]).reset_index(drop=True)
        merged.to_parquet(path, index=False)
        return merged
    except Exception as e:  # noqa: BLE001
        log.error("qbus.append_items failed (%s)", e)
        return None


def read_items():
    """The full accrued item store as a DataFrame, or None. Never raises."""
    try:
        import pandas as pd
        path = _events_path()
        if not path.exists():
            return None
        return pd.read_parquet(path).reindex(columns=list(COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.error("qbus.read_items failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# novelty — z-score of a subject's item volume vs its trailing window
# --------------------------------------------------------------------------- #
def _asof_date(asof) -> date | None:
    if isinstance(asof, date) and not isinstance(asof, datetime):
        return asof
    if isinstance(asof, datetime):
        return asof.date()
    try:
        return date.fromisoformat(str(asof)[:10])
    except (ValueError, TypeError):
        return None


def _subject_daily_counts(df, subject: str, asof: date,
                          window_days: int) -> tuple[float, list[float]]:
    """(today_count, trailing_daily_counts) for a subject (entity OR theme) over the
    `window_days` days BEFORE asof. Matches a row if `subject` is in its entities OR
    themes. PURE (df + asof passed). Uses the seendate day (fallback _crawled_at).

    Tz-mixed seendate handling: the store may contain a mix of tz-aware (ISO 8601
    with +00:00 / Z) and tz-naive (plain datetime string) values in the same column.
    A plain pd.to_datetime call without utc=True coerces tz-aware strings to NaT,
    silently nulling the entire CN lane (~938 rows).  We parse with format="mixed"
    and utc=True so all formats (tz-aware, tz-naive, Z-suffix) are first normalised
    to UTC then stripped to a date.  Rows where BOTH seendate AND _crawled_at are
    unparseable (empty / corrupted) map to None and never raise.
    """
    import pandas as pd
    day = pd.to_datetime(df["seendate"], errors="coerce", format="mixed", utc=True)
    fallback = pd.to_datetime(df["_crawled_at"], errors="coerce", format="mixed", utc=True)
    day = day.fillna(fallback)
    # Convert to date objects; rows with NaT in both columns → None (not a crash).
    day = day.map(lambda ts: ts.date() if pd.notna(ts) else None)

    def _hit(row_ents, row_thms) -> bool:
        return (subject in _split(row_ents)) or (subject in _split(row_thms))

    mask = [
        _hit(e, t) for e, t in zip(df["entities"].tolist(), df["themes"].tolist())
    ]
    sub = df[mask]
    sub_days = day[mask]
    today = float(sum(1 for d in sub_days if d == asof))
    trailing: dict[date, int] = {}
    lo = asof - timedelta(days=window_days)
    for d in sub_days:
        if d is not None and lo <= d < asof:
            trailing[d] = trailing.get(d, 0) + 1
    # dense series over the window (missing days = 0) so a quiet subject that
    # suddenly spikes reads as high novelty.
    series = [float(trailing.get(lo + timedelta(days=k), 0)) for k in range(window_days)]
    return today, series


def novelty_z(entity_or_theme: str, asof, window_days: int = 30,
              df=None) -> float | None:
    """z-score of today's (asof) item volume for a subject vs its trailing
    `window_days` daily volume. High z = attention is unusually elevated.

    Deterministic: `asof` is REQUIRED (no clock). Returns None when there is no
    store or the trailing window has no variance to standardize against. PURE-ish
    (reads the parquet unless a df is injected for testing). Never raises.

    Return semantics for the flat-window branch (sd <= 1e-9):
      today > mean  (spike over flat baseline)  → 3.0  (maximally novel)
      today == mean > 0  (quiet day matching flat nonzero baseline) → 0.0  (not novel)
      today == 0 AND mean == 0  (subject entirely absent from store) → None
        ("no evidence" is not the same as "zero novelty"; the template renders
        None as "—" via the fmt_nov macro, which is the honest display.)
    """
    try:
        if df is None:
            df = read_items()
        if df is None or len(df) == 0:
            return None
        a = _asof_date(asof)
        if a is None:
            return None
        today, series = _subject_daily_counts(df, entity_or_theme, a, window_days)
        if not series:
            return None
        n = len(series)
        mean = sum(series) / n
        var = sum((x - mean) ** 2 for x in series) / n
        sd = var ** 0.5
        if sd <= 1e-9:
            # no trailing variance — three distinct cases:
            if today > mean:
                return 3.0    # spike over flat baseline: maximally novel
            if mean > 0:
                return 0.0    # quiet day matching flat nonzero baseline: not novel
            # today == 0 AND mean == 0: subject is entirely absent from the store.
            # This is "no evidence", not "zero novelty" — return None so the
            # template renders "—" (fmt_nov) rather than a misleading z=+0.0.
            return None
        return round((today - mean) / sd, 3)
    except Exception as e:  # noqa: BLE001
        log.debug("qbus.novelty_z failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# echo — cross-desk corroboration for one event_key
# --------------------------------------------------------------------------- #
def echo_stats(event_key: str, df=None, asof=None) -> dict | None:
    """Cross-source/desk corroboration for one event_key:
      {n_sources, n_desks, n_items, first_seen, breadth}
    where breadth = distinct desks that carried the event (the "many independent
    desks saw this" primitive; 1 desk = no corroboration). first_seen = earliest
    _crawled_at (fallback seendate) across the cluster. Returns None if the key is
    absent. Never raises.

    asof (optional date | str): when supplied, only items whose _crawled_at (or
    seendate when _crawled_at is absent) is <= asof are counted.  This is the
    PIT discipline fix: the W3 backfill ran echo_stats WITHOUT an asof filter, so
    future corroboration items (crawled AFTER the item's own seendate) could
    inflate the breadth score.  Callers should always pass the item's own asof.
    """
    try:
        if df is None:
            df = read_items()
        if df is None or len(df) == 0 or not event_key:
            return None
        sub = df[df["event_key"] == event_key]
        # PIT filter — restrict to items seen on or before `asof`.
        if asof is not None:
            a = _asof_date(asof)
            if a is not None:
                import pandas as pd
                crawl = pd.to_datetime(sub["_crawled_at"], errors="coerce",
                                       format="mixed", utc=True)
                seen = pd.to_datetime(sub["seendate"], errors="coerce",
                                      format="mixed", utc=True)
                stamp = crawl.fillna(seen)
                stamp_date = stamp.map(lambda ts: ts.date() if pd.notna(ts) else None)
                sub = sub[[d is not None and d <= a for d in stamp_date]]
        if len(sub) == 0:
            return None
        sources = {str(s) for s in sub["source"].tolist() if str(s)}
        desks = {str(d) for d in sub["desk"].tolist() if str(d)}
        stamps = [str(x) for x in sub["_crawled_at"].tolist() if str(x)]
        stamps += [str(x) for x in sub["seendate"].tolist() if str(x)]
        first_seen = min(stamps) if stamps else ""
        return {
            "n_sources": len(sources),
            "n_desks": len(desks),
            "n_items": int(len(sub)),
            "first_seen": first_seen,
            "breadth": len(desks),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("qbus.echo_stats failed (%s)", e)
        return None


# thin ISO-now helper for callers that need to stamp _crawled_at at the ingest
# boundary (NOT called anywhere in library logic — the caller owns the clock).
def now_iso() -> str:
    """UTC now as ISO — a convenience for the INGEST BOUNDARY only. Library
    functions never call this; they take asof/_crawled_at from the caller."""
    return datetime.now(timezone.utc).isoformat()
