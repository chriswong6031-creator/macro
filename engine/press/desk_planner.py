"""engine.press.desk_planner — deterministic story/report selection for W1.

NO LLM.  NO NETWORK.  Same inputs => identical slots, every time.

Three desks:

  brief          The Brief.  Ranks the day's candidate stories from the
                 chronicle event store, the S&P/theme heatmaps (movers) and a
                 small set of first-party engine artifacts, then cuts to the
                 desk's cadence ceiling.
  research_desk  Research Desk.  Picks the top research-vault report(s) off the
                 W2R triage ranking (engine/press/research_triage.py) and hands
                 the writer that report's `summary_points` — our own analyst
                 summary, never the source PDF.
  research_note  W2R desk notes (XG-W8): the same beat at 300–500w on a cheaper
                 model, drawing BELOW the flagship tier's picks.  DARK until the
                 cold-start volume knob moves (config/press.yml
                 `research_triage.volume.stage`), which caps it at 0 slots today.

W2R TRIAGE INTAKE (XG-W8, masterplan D14 §5b).  The research desks no longer
sort by recency: `_triage_order` recomputes the deterministic W-score over the
eligible window and walks the reports in ranked order.  The tier only sets the
CAP, so a top-ranked report the planner cannot legally cover falls through to
the next one.  The LLM veto pass never runs here — the planner reads the
demotions the nightly already recorded, because a demotion is the one triage
input it cannot recompute without a model (and must never try to).

What a planner slot carries is the whole contract the rest of the pipeline
enforces:

  facts[]          every number the writer is allowed to use, each tagged
                   first_party / third_party.  validators.check_fact_anchor
                   rejects any number in the draft that is not in here.
  raw_documents[]  the source text the draft must NOT paraphrase closely.
                   validators.check_close_paraphrase scores against these.
  primary_source   {kind, name, url, ref}.  `kind` decides which source law
                   applies (masterplan §0 W1 gate 2, amended at review):
                   `external` slots must name the source in full and link it
                   above the fold; `first_party` slots carry their receipts
                   inline instead and link only PUBLIC pages from the config
                   allowlist.  Every W1 slot is first_party — external arrives
                   with PRESS-FEEDS.

POINT-IN-TIME: `as_of` is a hard right edge for facts as well as events.  The
engine artifacts are `latest.json` snapshots with no history, so every fact
carries its own `dated` and _pit_filter drops anything that postdates the run.

Dedupe is two-sided (both required — a staged-but-unemitted draft is not in the
ledger yet, and re-covering it would produce two pieces on one story):
  * data/press/published.jsonl  — sources[] and slug of everything emitted
  * data/press/staging/*.json   — sources[] and slug of everything staged

Fail-soft throughout: a missing artifact costs its candidates, never the run.
An honest thin day is the designed outcome, not a degradation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()

# ─────────────────────────────────────────────────────────────────────────────
# First-party engine artifacts The Brief may quote.
#
# Each entry: (key, relative path, extractor name).  Extractors live below and
# each returns a list of fact dicts.  Ordered by how quotable/stable the
# artifact is — the planner walks this order, so ranking is deterministic.
# EVERY artifact here is ours, so every fact it yields is tier=first_party.
# ─────────────────────────────────────────────────────────────────────────────
_ENGINE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("market_state", "data/market_state/latest.json"),
    ("gex", "data/gex/latest.json"),
    ("breadth_split", "site/basketdata/breadth_split.json"),
    ("fear_greed", "site/basketdata/fear_greed.json"),
    ("risk_radar", "data/risk_radar/forward_log.jsonl"),
)

# Chronicle sources whose events are OUR OWN measurement rather than a
# third-party publication.  A story built on one of these is first-party.
_FIRST_PARTY_CHRONICLE_SOURCES = frozenset({
    "prophet_ledger", "risk_band", "regime_flip", "earnings", "earnings_call",
    "macro_release",
})

_SITE_BASE = "https://www.mastermind-x.com"
_SHA256_RECEIPT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


# ─────────────────────────────────────────────────────────────────────────────
# Config + IO helpers (all fail-soft)
# ─────────────────────────────────────────────────────────────────────────────


def repo_root(root=None) -> Path:
    """Repo root.  ``root`` is the test-injection point (house convention)."""
    if root is not None:
        return Path(root)
    return _HERE.parent.parent.parent


# The one publication that never cuts over: it IS the existing /blog/ estate,
# built by scripts/build_free_content.py.  Giving it a property tree would put
# two builders on one corpus, so the loader refuses it by name.
FLAGSHIP_KEY = "flagship"


def _bad(problems: list[str], msg: str) -> None:
    problems.append(msg)


def _check_rel_under(value: str, prefix: str, label: str, problems: list[str]) -> None:
    """`value` must be a RELATIVE repo path whose first component is `prefix`.

    Absolute paths and `..` escapes are the interesting failures: both fields
    are joined onto the repo root and then written to, so an unchecked value is
    an arbitrary-write primitive dressed up as a config typo.
    """
    raw = str(value)
    parts = Path(raw).parts
    if Path(raw).is_absolute() or raw.startswith("/"):
        _bad(problems, f"{label} {raw!r} must be a RELATIVE path, not absolute")
        return
    if ".." in parts:
        _bad(problems, f"{label} {raw!r} must not escape the repo root ('..')")
        return
    if not parts or parts[0] != prefix:
        _bad(problems, f"{label} {raw!r} must live under {prefix}/")


def validate_publications(cfg: dict, source: str = "config/press.yml") -> None:
    """Validate the publication registry + the desk->publication mapping.

    FAIL LOUD, not fail soft.  Every other read in this module degrades to a
    thin day, which is the right answer for a missing artifact and the WRONG
    answer here: a desk pointing at a publication that does not exist, or a
    base_url whose host is not the publication's own domain, produces published
    URLs that 404 or point at somebody else's site.  There is no thin-day
    reading of that, so it raises at load rather than at emit.

    Raises ValueError listing EVERY violation found, not just the first — a
    config fixed one line per run is a config fixed over five runs.
    """
    problems: list[str] = []
    pubs = cfg.get("publications")
    if pubs is None:
        pubs = {}
    if not isinstance(pubs, dict):
        raise ValueError(f"{source}: `publications` must be a mapping, got {type(pubs).__name__}")

    desks = cfg.get("desks") or {}
    desks = desks if isinstance(desks, dict) else {}

    # 1. Every desk must point at a registered publication.
    mapped: set[str] = set()
    for name, desk in sorted(desks.items()):
        if not isinstance(desk, dict):
            continue
        key = str(desk.get("publication") or "")
        if not key:
            _bad(problems, f"desk {name!r} carries no `publication`")
            continue
        mapped.add(key)
        if key not in pubs:
            _bad(problems, f"desk {name!r} maps to unknown publication {key!r} "
                           f"(registered: {sorted(pubs)})")

    # 2. Per-publication field law.
    for key, pub in sorted(pubs.items()):
        if not isinstance(pub, dict):
            _bad(problems, f"publication {key!r} must be a mapping")
            continue
        base_url = pub.get("base_url")
        if base_url is not None:
            raw = str(base_url)
            domain = str(pub.get("domain") or "")
            if not raw.startswith("https://"):
                _bad(problems, f"publication {key!r} base_url {raw!r} must be https://")
            elif not domain:
                _bad(problems, f"publication {key!r} carries base_url but no `domain` to check it against")
            else:
                host = raw[len("https://"):].split("/", 1)[0].split(":", 1)[0].lower()
                # www.<domain> is legal because the flagship apex 301s to www;
                # anything else means the URL points at a site we do not own.
                if host not in (domain.lower(), f"www.{domain.lower()}"):
                    _bad(problems, f"publication {key!r} base_url host {host!r} is neither "
                                   f"{domain!r} nor www.{domain!r}")
            if raw.endswith("/"):
                _bad(problems, f"publication {key!r} base_url {raw!r} must not end in '/' "
                               "(every URL is built as base_url + '/path')")

        tree = pub.get("property_tree")
        if tree is not None:
            if key == FLAGSHIP_KEY:
                _bad(problems, f"publication {key!r} must NOT carry `property_tree` — the "
                               "flagship IS the /blog/ estate and is built by "
                               "scripts/build_free_content.py")
            _check_rel_under(tree, "properties", f"publication {key!r} property_tree", problems)

        content_dir = pub.get("content_dir")
        if content_dir is not None:
            _check_rel_under(content_dir, "content", f"publication {key!r} content_dir", problems)

    # 3. At cutover, a publication a desk actually emits to must be COMPLETE.
    #    Before cutover an incomplete entry is inert, so this stays quiet.
    if cfg.get("cutover") is True:
        for key in sorted(mapped):
            pub = pubs.get(key)
            if not isinstance(pub, dict) or pub.get("property_tree") is None:
                continue
            for field in ("base_url", "content_dir"):
                if not pub.get(field):
                    _bad(problems, f"cutover is true and publication {key!r} routes a desk "
                                   f"through property_tree, so it must carry `{field}`")

    if problems:
        raise ValueError(f"{source}: " + "; ".join(problems))


def load_config(root=None) -> dict:
    """Load config/press.yml.  Returns {} when absent or unparsable.

    BEHAVIOUR CHANGE (W1.5), stated plainly because it moves a contract every
    caller depends on: this used to be fail-soft for EVERY failure.  It still
    is for an absent or unparsable file — `{}` — but a config that is PRESENT
    and violates the publication contract now RAISES ValueError.

    CALLER CONTRACT: a caller that wants "is the press lane configured?" keeps
    checking the falsy return, unchanged.  A caller must NOT wrap this in a
    bare `except` to get a dict back: the raise is the report, and a lane that
    swallows it publishes to a URL nobody validated.  scripts/run_press.py and
    scripts/build_press_properties.py both let it propagate on purpose; the
    admin panel reads the YAML directly (admin/press.py::_read_yaml) and never
    calls this, so a bad config shows up there as data rather than a 500.

    See validate_publications for why that one class fails loud while every
    other read in this module fails soft.
    """
    import yaml  # noqa: PLC0415 — keep import cost off `import engine.press`

    path = repo_root(root) / "config" / "press.yml"
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("press.desk_planner: config/press.yml load failed: %s", exc)
        return {}
    if not isinstance(cfg, dict):
        log.warning("press.desk_planner: config/press.yml is not a mapping")
        return {}
    validate_publications(cfg, str(path))
    return cfg


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        if not path.exists():
            return []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


def _as_date(val, default: date | None = None) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return default


def slugify(text: str, limit: int = 70) -> str:
    """Deterministic slug: lowercase, non-alnum -> hyphen, collapse, truncate.

    Mirrors scripts.build_free_content._slugify plus the research-vault length
    cap so a press slug and a vault slug read the same way.
    """
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return s[:limit].strip("-")


def story_key(*parts: str) -> str:
    """Short stable hash over the identifying parts of a story."""
    raw = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Dedupe surfaces
# ─────────────────────────────────────────────────────────────────────────────


def published_refs(root=None, cfg: dict | None = None) -> tuple[set[str], set[str]]:
    """(source refs, slugs) already emitted, read from the ledger."""
    cfg = cfg if cfg is not None else load_config(root)
    rel = ((cfg.get("paths") or {}).get("ledger") or "data/press/published.jsonl")
    refs: set[str] = set()
    slugs: set[str] = set()
    for row in _read_jsonl(repo_root(root) / rel):
        for s in row.get("sources") or []:
            refs.add(str(s))
        for s in row.get("seed_refs") or []:
            refs.add(str(s))
        if row.get("slug"):
            slugs.add(str(row["slug"]))
    return refs, slugs


def staged_refs(root=None, cfg: dict | None = None) -> tuple[set[str], set[str]]:
    """(source refs, slugs) sitting in staging but not yet emitted.

    A staged draft is invisible to the ledger, so a planner that only checked
    the ledger would happily re-plan the same story on the next staging run and
    ship two pieces about it the moment both got emitted.
    """
    cfg = cfg if cfg is not None else load_config(root)
    rel = ((cfg.get("paths") or {}).get("staging_dir") or "data/press/staging")
    refs: set[str] = set()
    slugs: set[str] = set()
    stage = repo_root(root) / rel
    if not stage.exists():
        return refs, slugs
    for path in sorted(stage.glob("*.json")):
        if path.name.startswith("_"):
            continue          # `_run_summary.json` is a run artifact, not a slot
        obj = _read_json(path)
        if not isinstance(obj, dict):
            continue
        # A superseded record is retained as an audit trail, not as a live
        # draft.  Keeping its source ref or slug in the blocking sets would
        # prevent the corrected revision from ever being staged.
        if obj.get("status") in {"superseded", "resolved"}:
            continue
        for s in obj.get("sources") or []:
            refs.add(str(s))
        for s in obj.get("seed_refs") or []:
            refs.add(str(s))
        if obj.get("slug"):
            slugs.add(str(obj["slug"]))
    return refs, slugs


def earnings_call_revisions(root=None) -> dict[str, dict]:
    """Current canonical call-ledger revision by stable Press source ref.

    The stable ref identifies the company-period story; ``receipt`` identifies
    the exact transcript revision used to build it.  Invalid/missing receipts
    remain present with ``valid=False`` so emit-time reconciliation fails
    closed instead of treating an unverifiable event as unrelated.
    """

    from engine.chronicle.earnings_calls import load_call_events  # noqa: PLC0415

    out: dict[str, dict] = {}
    rows, gap = load_call_events(repo_root(root))
    if gap:
        log.warning("press.desk_planner: canonical earnings-call ledger gap: %s", gap)
        return out
    for event in rows:
        source_ref = str(event.get("source_record_id") or "").strip()
        if not source_ref:
            continue
        ref = f"chronicle:{source_ref}"
        source_hash = str(event.get("source_sha256") or "").lower()
        receipt = f"sha256:{source_hash}" if re.fullmatch(r"[0-9a-f]{64}", source_hash) else ""
        candidate = {
            "ref": ref,
            "receipt": receipt,
            "valid": bool(receipt),
            "event_id": str(event.get("id") or ""),
            "source_ref": source_ref,
            "date": str(event.get("call_date") or ""),
            "title": (
                f"Earnings call: {event.get('ticker')} {event.get('quarter')} "
                f"FY{event.get('year')}"
            ),
        }
        # Chronicle is append-only in normal operation.  If a malformed fixture
        # or hand edit leaves two rows for one source ref, deterministic event
        # time/id ordering chooses one rather than filesystem order.
        prior = out.get(ref)
        key = (candidate["date"], candidate["event_id"], candidate["receipt"])
        prior_key = (
            prior.get("date", ""), prior.get("event_id", ""), prior.get("receipt", "")
        ) if prior else None
        if prior_key is None or key >= prior_key:
            out[ref] = candidate
    return out


def taken_slugs(root=None) -> set[str]:
    """Slugs already occupied by a committed content/seo/blog/*.md file."""
    out: set[str] = set()
    blog = repo_root(root) / "content" / "seo" / "blog"
    if blog.exists():
        for p in blog.glob("*.md"):
            out.add(p.stem)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fact builders
# ─────────────────────────────────────────────────────────────────────────────


# Artifact labels that collide with the press lexicon.  These are OUR labels on
# OUR dashboards, written for a chart legend where the word is fine; in press
# prose "regime" is banned house vocabulary (copywriter._BANNED_WORD_BOUNDARY).
# Rewriting the label here is the honest fix — the alternative is a planner that
# feeds the writer a forbidden word and then quarantines it for using it.
_LABEL_ALIASES: dict[str, str] = {
    "volatility regime": "volatility backdrop",
}


def _press_label(label: str) -> str:
    low = str(label or "").strip().lower()
    return _LABEL_ALIASES.get(low, str(label or "").strip())


def _press_safe(text: str) -> bool:
    """False when a fact's own text would trip the press lexicons.

    A fact that cannot legally be written about is not a fact this desk can
    use, so it is DROPPED rather than handed to the writer as a trap.  Import,
    never fork: the lists live in the marketing lane.
    """
    try:
        from engine.marketing.copywriter import (  # noqa: PLC0415
            _BANNED_SUBSTRINGS, _BANNED_VOCAB, _BANNED_WORD_BOUNDARY,
        )
    except Exception:  # noqa: BLE001 — never let a lexicon import break planning
        return True
    low = str(text or "").lower()
    if any(term in low for term in _BANNED_SUBSTRINGS):
        return False
    for term in tuple(_BANNED_VOCAB) + tuple(_BANNED_WORD_BOUNDARY):
        if re.search(rf"\b{re.escape(term)}\b", low):
            return False
    return True


def _fact(fid: str, text: str, *, ref: str, tier: str,
          values: list | None = None, url: str | None = None,
          source_name: str = "", dated: str | None = None) -> dict:
    return {
        "id": fid,
        "text": text,
        "ref": ref,
        "tier": tier,                    # first_party | third_party
        "values": [str(v) for v in (values or [])],
        "url": url,
        "source_name": source_name,
        # The fact's OWN as-of. `None` means undated, which is treated as
        # unusable under a point-in-time query — see _pit_filter.
        "dated": str(dated)[:10] if dated else None,
    }


def _pit_filter(facts: list[dict], as_of: date, label: str) -> list[dict]:
    """Drop facts whose own as-of postdates the run date.

    THE DEFECT THIS CLOSES: the engine artifacts are `latest.json` snapshots
    with no history.  Reading them without checking their `asof` means a run
    dated 2026-07-20 quotes a 2026-07-24 measurement — an article that cites
    numbers from its own future.  Undated facts are dropped for the same reason:
    a fact that cannot prove it predates the run cannot be point-in-time.

    Loud on purpose.  A silently thinner fact pool is how a desk starts writing
    padding, and the thinness has a cause the operator needs to see.
    """
    kept, dropped = [], []
    edge = as_of.isoformat()
    for f in facts:
        if f.get("dated") and f["dated"] <= edge:
            kept.append(f)
        else:
            dropped.append(f"{f['id']}@{f.get('dated') or 'undated'}")
    if dropped:
        log.warning("press.desk_planner: %s — %d fact(s) dropped as of %s "
                    "(artifact postdates the run date or carries no date): %s",
                    label, len(dropped), edge, ", ".join(dropped[:8]))
    return kept


def _market_state_facts(obj: dict, rel: str) -> list[dict]:
    if not isinstance(obj, dict):
        return []
    facts: list[dict] = []
    asof = obj.get("asof") or ""
    score = obj.get("score")
    verdict = obj.get("verdict")
    if score is not None and verdict:
        facts.append(_fact(
            "market_state_score",
            f"Mastermind's market-state composite reads {score} of 100 "
            f"({verdict}) as of {asof}.",
            ref=f"artifact:{rel}", tier="first_party", dated=asof,
            values=[score], source_name="Mastermind market-state engine",
        ))
    for comp in (obj.get("components") or [])[:4]:
        if not isinstance(comp, dict):
            continue
        label = _press_label(comp.get("label_en") or comp.get("key") or "")
        cscore = comp.get("score")
        if not label or cscore is None:
            continue
        facts.append(_fact(
            f"market_state_{comp.get('key') or label}",
            f"Market-state component {label} scores {cscore} "
            f"(weight {comp.get('weight')}).",
            ref=f"artifact:{rel}", tier="first_party", dated=asof,
            values=[cscore, comp.get("weight")],
            source_name="Mastermind market-state engine",
        ))
    return facts


def _gex_facts(obj: dict, rel: str) -> list[dict]:
    if not isinstance(obj, dict):
        return []
    facts: list[dict] = []
    asof = obj.get("asof") or ""
    for sym, blk in sorted((obj.get("indices") or {}).items()):
        if not isinstance(blk, dict):
            continue
        net = blk.get("net_gex_bn")
        flip = blk.get("gamma_flip")
        dist = blk.get("dist_to_flip_pct")
        # NOTE: blk["regime"] is deliberately NOT rendered into fact text.
        # "regime" is on copywriter._BANNED_WORD_BOUNDARY, and a planner that
        # seeds banned vocabulary into the writer's context is manufacturing the
        # validator failure it will then quarantine.  Facts are written in the
        # words the draft is allowed to use.
        if net is None and flip is None:
            continue
        facts.append(_fact(
            f"gex_{sym.lower()}",
            f"{sym} dealer gamma is {net}bn net with the gamma flip at {flip}; "
            f"spot sits {dist}% from it as of {asof}.",
            ref=f"artifact:{rel}", tier="first_party", dated=asof,
            values=[net, flip, dist, blk.get("spot")],
            source_name="Mastermind dealer-positioning engine",
        ))
    return facts


def _breadth_facts(obj: dict, rel: str) -> list[dict]:
    if not isinstance(obj, dict):
        return []
    latest = obj.get("latest") or {}
    if not isinstance(latest, dict) or not latest:
        return []
    asof = obj.get("as_of") or ""
    ai50, non50 = latest.get("ai_pct50"), latest.get("nonai_pct50")
    if ai50 is None or non50 is None:
        return []
    return [_fact(
        "breadth_split",
        f"As of {asof}, {ai50}% of the AI cohort is above its 50-day average "
        f"against {non50}% of the non-AI cohort — a {latest.get('spread_50')} "
        f"point spread.",
        ref=f"artifact:{rel}", tier="first_party", dated=asof,
        values=[ai50, non50, latest.get("spread_50"),
                latest.get("ai_adv_share"), latest.get("nonai_adv_share")],
        source_name="Mastermind breadth engine",
    )]


def _fear_greed_facts(obj: dict, rel: str) -> list[dict]:
    if not isinstance(obj, dict):
        return []
    dial, label = obj.get("dial"), obj.get("label_en")
    if dial is None or not label:
        return []
    return [_fact(
        "fear_greed",
        f"The Mastermind fear/greed dial reads {dial} ({label}) as of "
        f"{obj.get('as_of') or ''}, built from "
        f"{obj.get('n_legs_qualifying')} qualifying legs.",
        ref=f"artifact:{rel}", tier="first_party", dated=obj.get("as_of"),
        values=[dial, obj.get("n_legs_qualifying")],
        source_name="Mastermind sentiment engine",
    )]


def _risk_radar_facts(rows: list[dict], rel: str) -> list[dict]:
    # This artifact is the one with real history: an append-only forward log.
    # `rows[-1]` is the latest row, which under a back-dated run is a row from
    # the future — so take the latest row that is not, and let _pit_filter drop
    # the fact entirely if even that one postdates the run.
    if not rows:
        return []
    row = next((r for r in reversed(rows) if isinstance(r, dict) and r.get("state")), None)
    if row is None:
        return []
    dd = row.get("drawdown_prob") or {}
    return [_fact(
        "risk_radar",
        f"The risk radar is in `{row['state']}` with {row.get('dominant_scare')} the "
        f"dominant scare (score {row.get('top_score')}); modelled 21-session "
        f"drawdown probability {dd.get('h21')} as of {row.get('asof')}.",
        ref=f"artifact:{rel}", tier="first_party", dated=row.get("asof"),
        values=[row.get("top_score"), dd.get("h21"), dd.get("h10"), dd.get("h5")],
        source_name="Mastermind risk radar",
    )]


_ARTIFACT_EXTRACTORS = {
    "market_state": _market_state_facts,
    "gex": _gex_facts,
    "breadth_split": _breadth_facts,
    "fear_greed": _fear_greed_facts,
    "risk_radar": _risk_radar_facts,
}


def engine_stat_facts(root=None, *, as_of=None) -> list[dict]:
    """First-party engine facts, in a deterministic artifact order.

    POINT-IN-TIME: `as_of` is REQUIRED for any run that is not "today".  Every
    artifact in _ENGINE_ARTIFACTS is a `latest.json` snapshot with no history,
    so reading one without checking its own `asof` hands a back-dated run
    numbers from its own future.  Facts dated after `as_of` — and facts that
    carry no date at all — are dropped by _pit_filter, loudly.

    Fail-soft per artifact: a missing or malformed file costs its own facts and
    nothing else.
    """
    repo = repo_root(root)
    out: list[dict] = []
    for key, rel in _ENGINE_ARTIFACTS:
        path = repo / rel
        if not path.exists():
            continue
        try:
            payload = _read_jsonl(path) if path.suffix == ".jsonl" else _read_json(path)
            for fact in (_ARTIFACT_EXTRACTORS[key](payload, rel) or []):
                if _press_safe(fact["text"]):
                    out.append(fact)
                else:
                    log.info("press.desk_planner: dropped fact %s — its own text "
                             "trips the press lexicon", fact["id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("press.desk_planner: artifact %s failed: %s", rel, exc)
    edge = _as_date(as_of)
    return _pit_filter(out, edge, "engine artifacts") if edge else out


#: Where a mover row came from → (artifact path, human source name). The board
#: stopped being one file on 2026-08-02 (masterplan §3 PR-B.3): `top_movers` now
#: also returns hot-tape-pack rows for liquid names the S&P heatmap does not
#: carry. Citing those to the heatmap would point a reader at a file that does
#: not contain the ticker, and dating them by the heatmap's stamp would be the
#: mixed-asof claim movers_source exists to prevent — so the citation follows
#: the ROW, exactly as its `asof` already does.
_MOVER_SOURCES: dict[str, tuple[str, str]] = {
    "sp500_heatmap": ("site/marketdata/sp500_heatmap.json",
                      "Mastermind S&P 500 heatmap"),
    "hot_tape_pack": ("data/marketing/hot_tape_pack.json",
                      "Mastermind hot-tape pack"),
}


def mover_facts(root=None, *, n: int = 3, as_of=None) -> list[dict]:
    """Top gainers/losers from the committed heatmaps (first-party).

    Same point-in-time law as engine_stat_facts: each source is a snapshot, and
    the `asof` of the ROW's own source is the date that fact belongs to.
    """
    try:
        from engine.marketing import movers_source  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    repo = repo_root(root)
    try:
        data = movers_source.load_movers(repo)
        if not data:
            return []
        picks = movers_source.top_movers(data, tf="1D", n=n, min_abs=3.0)
    except Exception as exc:  # noqa: BLE001
        log.warning("press.desk_planner: movers load failed: %s", exc)
        return []
    payload_asof = (data or {}).get("asof") or ""
    out: list[dict] = []
    for side in ("gainers", "losers"):
        for m in (picks.get(side) or []):
            tk, pct = m.get("ticker"), m.get("pct")
            if not tk or pct is None:
                continue
            rel, source_name = _MOVER_SOURCES.get(
                str(m.get("source") or "sp500_heatmap"),
                _MOVER_SOURCES["sp500_heatmap"])
            asof = str(m.get("asof") or payload_asof or "")
            # The pack has no company names and only tags its index members with
            # a sector, so build the parenthetical from what is actually known
            # rather than printing "AAPL (AAPL, )".
            bits = [str(b) for b in (m.get("name"), m.get("sector"))
                    if b and str(b) != str(tk)]
            label = f" ({', '.join(bits)})" if bits else ""
            fact = _fact(
                f"mover_{side}_{tk}",
                f"{tk}{label} closed {pct}% on the session of {asof}.",
                ref=f"artifact:{rel}#{tk}", tier="first_party", dated=asof,
                values=[pct], source_name=source_name,
            )
            # A company name can collide with the house lexicon ("Vertical
            # Aerospace" trips _BANNED_SUBSTRINGS). Drop the fact rather than
            # hand the writer a word it will be quarantined for using.
            if _press_safe(fact["text"]):
                out.append(fact)
    edge = _as_date(as_of)
    return _pit_filter(out, edge, "movers heatmap") if edge else out


# ─────────────────────────────────────────────────────────────────────────────
# Chronicle candidates
# ─────────────────────────────────────────────────────────────────────────────


def _chronicle_events(root=None) -> list[dict]:
    return _read_jsonl(repo_root(root) / "data" / "chronicle" / "events.jsonl")


def _event_candidates(events: list[dict], as_of: date, window_days: int) -> list[dict]:
    """Events in (as_of - window_days, as_of], ranked deterministically.

    Rank: weight_hint DESC, date DESC, id ASC.  `as_of` is a hard right edge —
    the planner never sees an event dated after the run date.
    """
    lo = (as_of - timedelta(days=int(window_days))).isoformat()
    hi = as_of.isoformat()
    picked = [
        e for e in events
        if isinstance(e, dict) and e.get("date") and lo <= str(e["date"]) <= hi
    ]
    picked.sort(key=lambda e: (
        -int(e.get("weight_hint") or 0),
        _neg_ordinal(e.get("date")),
        str(e.get("id") or ""),
    ))
    return picked


def _neg_ordinal(d) -> int:
    dd = _as_date(d)
    return -dd.toordinal() if dd else 0


def _event_fact(ev: dict) -> dict:
    src = str(ev.get("source") or "")
    tier = "first_party" if src in _FIRST_PARTY_CHRONICLE_SOURCES else "third_party"
    title = str(ev.get("title") or "")
    facts = [str(f) for f in (ev.get("facts") or [])]
    if src == "earnings_call":
        from engine.chronicle.earnings_calls import sanitize_untrusted_prose  # noqa: PLC0415

        title = sanitize_untrusted_prose(title, max_len=300)
        facts = [sanitize_untrusted_prose(fact, max_len=1600) for fact in facts]
        facts = [fact for fact in facts if fact]
    facts_txt = "; ".join(facts)
    text = f"[{ev.get('date')}] {title}"
    if facts_txt:
        text += f" — {facts_txt}"
    links = ev.get("links") or {}
    site = links.get("site")
    # Earnings-call rows carry a public-safe source URL/hash even when the URL
    # is not on Press's logged-out article-link allowlist.  Preserve that
    # provenance in the staged slot for audit/correction handling; the writer
    # still receives only ``allowed_links`` and therefore cannot emit it unless
    # the publication policy explicitly opens that path later.
    source_url = links.get("source") if src == "earnings_call" else None
    fact = _fact(
        f"chronicle_{ev.get('id')}",
        text,
        ref=f"chronicle:{ev.get('source_ref') or ev.get('id')}",
        tier=tier,
        values=[],
        dated=ev.get("date"),
        url=site or source_url,
        source_name=_source_label(src),
    )
    if src == "earnings_call" and links.get("receipt"):
        fact["receipt"] = str(links["receipt"])
    return fact


def _source_label(src: str) -> str:
    return {
        "earnings": "Mastermind earnings store",
        "earnings_call": "Mastermind earnings-call analysis",
        "prophet_ledger": "Mastermind Prophet ledger",
        "risk_band": "Mastermind risk radar",
        "regime_flip": "Mastermind regime engine",
        "macro_release": "Mastermind macro release store",
        "research_vault": "Mastermind Research vault",
    }.get(src, src or "Mastermind")


# ─────────────────────────────────────────────────────────────────────────────
# Chronicle narrative context (engine.chronicle.context_pack — CALL, never edit)
# ─────────────────────────────────────────────────────────────────────────────


def chronicle_context(as_of: date, *, tickers=None, topics=None,
                      token_budget: int = 1200, window: str = "14d",
                      root=None) -> dict:
    """The one chronicle API every consumer binds.  Fail-soft to an empty pack."""
    try:
        from engine.chronicle import context_pack  # noqa: PLC0415
        return context_pack.pack(
            topics=topics, tickers=tickers, horizons=("short", "medium"),
            token_budget=token_budget, as_of=as_of.isoformat(), window=window,
            root=repo_root(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("press.desk_planner: context_pack failed: %s", exc)
        return {"lines": [], "narratives": [], "budget_used": 0,
                "coverage": {"start": None, "end": None,
                             "note": f"context_pack unavailable ({exc})"}}


# ─────────────────────────────────────────────────────────────────────────────
# The Brief
# ─────────────────────────────────────────────────────────────────────────────


def _plan_brief(cfg: dict, desk_cfg: dict, as_of: date, root,
                blocked_refs: set[str], *, name: str = "brief") -> list[dict]:
    events = _chronicle_events(root)
    window = int(desk_cfg.get("window_days") or 3)
    excluded = {str(s) for s in (desk_cfg.get("exclude_sources") or [])}

    cands = [
        e for e in _event_candidates(events, as_of, window)
        if str(e.get("source") or "") not in excluded
    ][: int(desk_cfg.get("candidate_pool") or 12)]

    stats = engine_stat_facts(root, as_of=as_of)
    movers = mover_facts(root, as_of=as_of)
    publication = str(desk_cfg.get("publication") or "flagship")
    cap = int(desk_cfg.get("cadence_per_day") or 1)

    slots: list[dict] = []
    for ev in cands:
        if len(slots) >= cap:
            break
        ref = f"chronicle:{ev.get('source_ref') or ev.get('id')}"
        # Cross-namespace block: the same underlying document reaches the two
        # desks under two ref spellings, and a set that only holds one of them
        # is not a dedupe.
        alias = f"{ev.get('source')}:{ev.get('source_ref') or ev.get('id')}"
        if ref in blocked_refs or alias in blocked_refs:
            continue

        lead = _event_fact(ev)
        revision_receipt = str(lead.get("receipt") or "").lower()
        if ev.get("source") == "earnings_call" and not _SHA256_RECEIPT_RE.fullmatch(
            revision_receipt
        ):
            log.warning(
                "press.desk_planner: earnings-call candidate %s has no valid "
                "revision receipt — skipped fail-closed",
                ref,
            )
            continue
        if not _press_safe(lead["text"]):
            # The story cannot be told without a banned word. Skip it rather
            # than plan a piece that is guaranteed to be quarantined.
            log.info("press.desk_planner: brief candidate %s skipped — its lead "
                     "fact trips the press lexicon", ref)
            continue
        # A brief must be OUR read of the day, not a wire rewrite: every slot
        # carries the day's first-party engine context alongside the event so
        # the our-value floor is reachable without padding.
        facts = [lead] + stats + movers
        tickers = [str(t) for t in (ev.get("tickers") or [])]
        ctx = chronicle_context(as_of, tickers=tickers or None, root=root)

        # SOURCE LAW (amended at W1 review — masterplan §0 W1 gate 2).
        # A Brief slot is FULLY FIRST-PARTY: the story is our own chronicle
        # event and our own engine measurements. It carries its receipts inline
        # (dated, fact-anchored numbers). Only the separately computed
        # ``allowed_links`` list may reach the article body.
        #
        # W1 originally pointed these slots at /us_track_record.html,
        # /radar.html and /macro.html as their "primary source" — all three
        # answer 302 to /?signin=1, so the validator was forcing every public
        # article to cite a login wall. `url: None` is the honest state when a
        # first-party desk has no source page to show. An earnings-call event
        # retains its public-safe evidence URL/hash in the staged audit record,
        # but the link allowlist below keeps that URL out of prose unless its
        # logged-out path is separately approved.
        primary_url = lead.get("url")
        source_revisions = (
            {ref: revision_receipt} if ev.get("source") == "earnings_call" else {}
        )
        event_title = str(ev.get("title") or "")
        if ev.get("source") == "earnings_call":
            from engine.chronicle.earnings_calls import sanitize_untrusted_prose  # noqa: PLC0415

            event_title = sanitize_untrusted_prose(event_title, max_len=300)
            if not event_title:
                ticker_label = tickers[0] if tickers else "company"
                event_title = f"Earnings call update: {ticker_label}"
        identity_parts = [name, ref]
        if revision_receipt:
            # Stable story ref, revision-specific staging identity.  The former
            # powers dedupe; the latter preserves both audit records when a
            # pending draft is superseded by a corrected transcript.
            identity_parts.append(revision_receipt)
        slots.append({
            "id": (
                f"press-{name}-{as_of.isoformat()}-"
                f"{story_key(*identity_parts)}"
            ),
            "desk": name,
            "publication": publication,
            "byline": str(desk_cfg.get("byline") or "The Brief"),
            "cluster": str(desk_cfg.get("cluster") or "market-brief"),
            "as_of": as_of.isoformat(),
            "model_key": str(desk_cfg.get("model_key") or "press_brief"),
            "min_words": int(desk_cfg.get("min_words") or 300),
            "max_words": int(desk_cfg.get("max_words") or 600),
            "min_anchored_receipts": int(desk_cfg.get("min_anchored_receipts") or 0),
            # What the writer may link. Usually empty for a Brief: the pages
            # that carry these numbers are gated, so the piece carries dated
            # receipts instead. Vault coverage is the existing public exception.
            "allowed_links": _allowed_links(cfg, [primary_url]),
            "story": {
                "kind": ev.get("kind"),
                "title_hint": event_title,
                "tickers": tickers,
                "themes": [str(t) for t in (ev.get("themes") or [])],
                "event_date": ev.get("date"),
            },
            "primary_source": {
                "kind": "first_party",
                "name": lead.get("source_name") or "Mastermind",
                "url": _absolute(primary_url) if primary_url else None,
                "ref": ref,
                "receipt": lead.get("receipt"),
            },
            "sources": [ref],
            "source_revisions": source_revisions,
            "seed_refs": sorted({f["ref"] for f in facts}),
            "facts": facts,
            "raw_documents": _raw_documents_for_event(ev),
            "chronicle_context": ctx,
            "slug_hint": slugify(event_title or "market brief"),
        })
        blocked_refs.add(ref)
    return slots


def _raw_documents_for_event(ev: dict) -> list[dict]:
    """The source text a Brief must not closely paraphrase."""
    body = " ".join([str(ev.get("title") or "")] + [str(f) for f in (ev.get("facts") or [])])
    if not body.strip():
        return []
    return [{"ref": f"chronicle:{ev.get('source_ref') or ev.get('id')}", "text": body}]


def _allowed_links(cfg: dict, urls) -> list[str]:
    """The subset of `urls` a draft may legally link.

    A URL survives only if its path sits under one of
    config/press.yml `public_link_prefixes` — the prefixes verified to answer
    200 to a logged-out reader.  Everything else on the estate is a regwall
    302, and validators.check_link_allowlist fails a draft that links one.
    """
    prefixes = [str(p) for p in (cfg.get("public_link_prefixes") or [])]
    out: list[str] = []
    for u in urls:
        if not u:
            continue
        full = _absolute(str(u))
        path = "/" + full.split("//", 1)[-1].split("/", 1)[-1] if "//" in full else str(u)
        if any(path.startswith(p) for p in prefixes) and full not in out:
            out.append(full)
    return out


def _absolute(url: str) -> str:
    u = str(url or "")
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return f"{_SITE_BASE}/{u.lstrip('/')}"


# ─────────────────────────────────────────────────────────────────────────────
# Research Desk
# ─────────────────────────────────────────────────────────────────────────────


def vault_slug(item: dict, all_items: list[dict]) -> str:
    """The report's live /research/<slug>.html slug.

    Delegates to engine.research_vault.slugs.slug_map so the URL the press piece
    links is byte-identical to the page the estate actually serves — a slug
    reimplemented here would drift the day that module changes.
    """
    try:
        from engine.research_vault import slugs as _slugs  # noqa: PLC0415
        return _slugs.slug_map(all_items).get(item.get("id"), "") or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("press.desk_planner: vault slug_map failed: %s", exc)
        return ""


def _triage_order(cfg: dict, as_of: date, root,
                  eligible: list[dict]) -> tuple[list[str], dict]:
    """W2R ranked order + per-report triage metadata.  ([], {}) when unavailable.

    THE PLANNER'S ONE INTAKE SEAM (XG-W8, masterplan §5b).  The W-score is
    deterministic, offline and cheap, so it is RECOMPUTED here rather than read
    from the nightly's ledger — that keeps the planner reproducible from the
    committed tree alone.  What the planner DOES read from the ledger is the
    nightly veto pass's demotions, because those are the one input the planner
    cannot recompute without an LLM (and must never try to).

    Fail-soft by design: any failure returns ([], {}) and the caller falls back
    to the W1 sort (top_pick, recency, id).  A broken triage costs the desk its
    ordering, never its day.
    """
    tcfg_present = isinstance(cfg.get("research_triage"), dict)
    if not tcfg_present:
        return [], {}
    tcfg = cfg["research_triage"]
    if not bool(tcfg.get("enabled", True)):
        return [], {}
    try:
        from engine.press import research_triage as _rt  # noqa: PLC0415

        result = _rt.rank(eligible, as_of=as_of, root=root, cfg=cfg)
        vetoes = _rt.recorded_vetoes(root, cfg, as_of=as_of)
        if vetoes:
            result = _rt.apply_vetoes(result, vetoes, cfg=tcfg)
        meta = {str(r.get("report_id")): r for r in (result.get("rows") or [])}
        # DIVERGENCE IS DISCLOSED, NOT ASSUMED AWAY.  The planner recomputes the
        # W-score; the nightly computed its own on a host that may have had the
        # optional `datasketch` wheel when this one does not (the workflow
        # installs it, a local checkout usually has not).  cluster_density then
        # differs between the two, so the planner's score can differ from the
        # ledger's for the same report on the same day.  Rather than pretend the
        # two are one number, every slot states which one it is holding and
        # whether the near-dup pass was available when it was computed.
        for row in meta.values():
            row["score_source"] = "planner-recomputed"
            row["datasketch_present"] = bool(result.get("near_dup_enabled"))
        return _rt.ranked_order(result), meta
    except Exception as exc:  # noqa: BLE001 — triage must never break planning
        log.warning("press.desk_planner: research triage unavailable (%s) — "
                    "falling back to the W1 recency sort", exc)
        return [], {}


#: The W2R tiers a desk may declare, mapped to their volume-knob key.
_TIER_VOLUME_KEY = {"flagship": "flagship_per_day", "desk_note": "desk_notes_per_day"}


def _triage_cap(cfg: dict, desk_cfg: dict, *, name: str = "") -> int:
    """STRICTER-OF (desk cadence ceiling, this tier's volume knob).  FAILS CLOSED.

    Both halves honour an explicit 0.  ``int(x or 1)`` — the W1 idiom — reads a
    configured 0 as 1, which would have armed the dark desk-note lane the moment
    it was added, so neither number is resolved that way here.

    FAIL-CLOSED IS THE WHOLE POINT, and it is a correction of the first version
    of this function.  A desk that declares ``triage_tier`` is W2R-GOVERNED: its
    volume comes from ``research_triage.volume``, and its own
    ``cadence_per_day`` is only ever the second half of a stricter-of.  The
    first version returned that desk ceiling whenever the triage layer could not
    be consulted — triage disabled, config block deleted, ``volume()`` raising,
    a typo'd tier — which made the FEATURE'S OFF SWITCH the ARMING SWITCH for
    the dark desk-note lane: `research_note` shipped a ceiling of 12, so
    `enabled: false` would have published twelve notes a day.

    So: a desk with no ``triage_tier`` is not a W2R desk and keeps its own
    cadence, unchanged.  A desk WITH one resolves through an ENABLED triage
    layer or gets **0**.  Every closed path logs its reason.
    """
    raw = desk_cfg.get("cadence_per_day")
    try:
        cap = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        cap = 1
    cap = max(0, cap)

    tier = str(desk_cfg.get("triage_tier") or "")
    if not tier:
        return cap          # not a W2R desk — W1 behaviour, untouched

    label = name or str(desk_cfg.get("byline") or "research")
    tcfg = cfg.get("research_triage")
    if not isinstance(tcfg, dict):
        log.warning("press.desk_planner: desk %s declares triage_tier=%r but "
                    "config carries no `research_triage` block — capped at 0 "
                    "(fail-closed: a W2R desk without its governor does not publish)",
                    label, tier)
        return 0
    if not bool(tcfg.get("enabled", True)):
        log.info("press.desk_planner: desk %s is W2R-governed and research_triage "
                 "is disabled — capped at 0", label)
        return 0
    try:
        from engine.press import research_triage as _rt  # noqa: PLC0415

        vol = _rt.volume(tcfg.get("volume") if isinstance(tcfg.get("volume"), dict) else None)
    except Exception as exc:  # noqa: BLE001
        log.warning("press.desk_planner: desk %s — volume knob unreadable (%s) — "
                    "capped at 0 (fail-closed)", label, exc)
        return 0
    key = _TIER_VOLUME_KEY.get(tier)
    if key is None:
        log.warning("press.desk_planner: desk %s declares triage_tier=%r, which is "
                    "not a W2R tier (%s) — capped at 0 (fail-closed: a typo must "
                    "not publish at the desk ceiling)",
                    label, tier, sorted(_TIER_VOLUME_KEY))
        return 0
    try:
        return min(cap, max(0, int(vol.get(key, 0))))
    except (TypeError, ValueError):
        log.warning("press.desk_planner: desk %s — volume.%s is not an integer — "
                    "capped at 0 (fail-closed)", label, key)
        return 0


def _plan_research(cfg: dict, desk_cfg: dict, as_of: date, root,
                   blocked_refs: set[str], *, name: str = "research_desk") -> list[dict]:
    catalog = _read_json(repo_root(root) / "data" / "research_vault" / "catalog.json")
    items = (catalog or {}).get("items") or []
    if not isinstance(items, list) or not items:
        return []

    window = int(desk_cfg.get("window_days") or 21)
    lo = as_of - timedelta(days=window)

    eligible: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        pub = _as_date(it.get("published_at"))
        # `as_of` is a hard right edge: a report published after the run date
        # cannot be covered by that run.
        if pub is None or pub > as_of or pub < lo:
            continue
        if not (it.get("summary_points") or []):
            continue
        eligible.append(it)

    # W2R (XG-W8): the ranked shortlist replaces the W1 recency sort when the
    # triage layer is configured and healthy. The tier only sets the CAP — the
    # desk walks the WHOLE ranked order, so a top-ranked report the planner
    # cannot legally cover (already published, already staged, banned vocabulary
    # in every summary point) falls through to the next one instead of costing
    # the desk its day.
    order, triage_meta = _triage_order(cfg, as_of, root, eligible)
    if order:
        by_id = {str(it.get("id") or ""): it for it in eligible}
        ranked = [by_id[rid] for rid in order if rid in by_id]
        # A report the triage did not rank must fall to the BACK of the queue,
        # never off it. The two windows are independent config keys
        # (desks.*.window_days vs research_triage.ledger.window_days), so a desk
        # widened past the triage window would otherwise lose its extra
        # candidates silently — an intake seam that quietly shrinks the pool is
        # worse than one that does not exist.
        seen = {str(it.get("id") or "") for it in ranked}
        tail = [it for it in eligible if str(it.get("id") or "") not in seen]
        if tail:
            log.info("press.desk_planner: %d eligible report(s) fell outside the "
                     "triage window and were appended unranked", len(tail))
        eligible = ranked + tail
    else:
        # W1 fallback: tier first (top_pick), then recency, then id.
        eligible.sort(key=lambda it: (
            0 if it.get("top_pick") else 1,
            -(_as_date(it.get("published_at")) or date.min).toordinal(),
            str(it.get("id") or ""),
        ))

    publication = str(desk_cfg.get("publication") or "flagship")
    cap = _triage_cap(cfg, desk_cfg, name=name)
    if cap <= 0:
        # A dark tier is a NORMAL outcome, not a failure: the cold-start volume
        # knob holds desk_notes_per_day at 0 until the GSC evidence opens it.
        log.info("press.desk_planner: desk %s is capped at 0 slots "
                 "(triage_tier=%s) — nothing planned",
                 desk_cfg.get("byline") or "research", desk_cfg.get("triage_tier"))
        return []
    stats = engine_stat_facts(root, as_of=as_of)

    slots: list[dict] = []
    for it in eligible[: int(desk_cfg.get("candidate_pool") or 8)]:
        if len(slots) >= cap:
            break
        ref = f"research_vault:{it.get('id')}"
        if ref in blocked_refs:
            continue

        slug = vault_slug(it, items)
        url = _absolute(f"/research/{slug}.html") if slug else f"{_SITE_BASE}/research/"
        inst = str(it.get("institution") or "the desk")

        # The vault summary is OUR analyst summary of the report, so it is a
        # first-party ref — but the report itself is somebody else's document,
        # which is exactly why close-paraphrase scores against these points.
        facts = [
            f for f in (
                _fact(
                    f"vault_point_{i}",
                    _strip_md(str(pt)),
                    ref=ref, tier="first_party",
                    dated=str(it.get("published_at") or "")[:10],
                    url=url, source_name=f"Mastermind Research coverage of {inst}",
                )
                for i, pt in enumerate(it.get("summary_points") or [])
            )
            # A summary point written in banned house vocabulary is one the
            # desk cannot quote. It stays in raw_documents (so paraphrase is
            # still scored against it) but leaves the writer's fact list.
            if _press_safe(f["text"])
        ]
        if not facts:
            log.info("press.desk_planner: research candidate %s skipped — every "
                     "summary point trips the press lexicon", ref)
            continue
        facts.append(_fact(
            "vault_meta",
            f"The report is {inst} research published {str(it.get('published_at'))[:10]}"
            + (f", {it.get('pages')} pages" if it.get("pages") else "") + ".",
            ref=ref, tier="first_party",
            dated=str(it.get("published_at") or "")[:10],
            values=[it.get("pages")], url=url,
            source_name="Mastermind Research vault",
        ))
        facts.extend(stats)

        ctx = chronicle_context(as_of, topics=[inst], root=root)
        # W2R audit trail. Carried on the slot so the staging record, the
        # validator report and the published ledger all state WHY this report
        # was the one covered — including its score, its rank, and any veto the
        # nightly recorded against it.
        triage_row = triage_meta.get(str(it.get("id") or "")) or {}
        slots.append({
            "id": f"press-{name}-{as_of.isoformat()}-{story_key(name, ref)}",
            "desk": name,
            "publication": publication,
            "byline": str(desk_cfg.get("byline") or "Research Desk"),
            "cluster": str(desk_cfg.get("cluster") or "research-desk"),
            "as_of": as_of.isoformat(),
            "model_key": str(desk_cfg.get("model_key") or "press_research"),
            "min_words": int(desk_cfg.get("min_words") or 500),
            "max_words": int(desk_cfg.get("max_words") or 900),
            "min_anchored_receipts": int(desk_cfg.get("min_anchored_receipts") or 0),
            # /research/<slug>.html is our own PUBLIC coverage page (verified
            # 200 logged-out), so it is on the allowlist and may be linked.
            "allowed_links": _allowed_links(cfg, [url]),
            "story": {
                "kind": "research_report",
                "title_hint": it.get("title"),
                "institution": inst,
                "side": it.get("side"),
                "published_at": it.get("published_at"),
                "tickers": [],
                "themes": [],
            },
            # First-party too: /research/<slug>.html is OUR coverage page and it
            # is PUBLIC (verified 200 logged-out), so it is on the config
            # allowlist and the piece may link it.
            "primary_source": {
                "kind": "first_party",
                "name": f"Mastermind Research: {it.get('title')}",
                "url": url,
                "ref": ref,
            },
            "sources": [ref],
            "seed_refs": sorted({f["ref"] for f in facts}),
            "facts": facts,
            "raw_documents": [{
                "ref": ref,
                "text": " ".join(_strip_md(str(p)) for p in (it.get("summary_points") or [])),
            }],
            "chronicle_context": ctx,
            "slug_hint": slugify(str(it.get("title") or "research note")),
            "triage": {
                "tier": str(desk_cfg.get("triage_tier") or ""),
                "rank": triage_row.get("rank"),
                "w_score": triage_row.get("w_score"),
                "w_score_pre_veto": triage_row.get("w_score_pre_veto"),
                "components": triage_row.get("components") or {},
                "veto": triage_row.get("veto"),
                "scoring_version": triage_row.get("scoring_version"),
                # Which number this is, and what it was computed with. The
                # nightly ledger's score for the same report on the same day can
                # differ when the two hosts disagree about the optional
                # near-dup backend — see _triage_order.
                "score_source": triage_row.get("score_source"),
                "datasketch_present": triage_row.get("datasketch_present"),
                # `ordered` is false when the triage layer was unavailable and
                # the desk fell back to the W1 recency sort — a state the
                # staging record must show rather than imply.
                "ordered": bool(order),
            },
        })
        blocked_refs.add(ref)
    return slots


_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _strip_md(text: str) -> str:
    """Drop the catalog's markdown bold so shingles compare on words, not syntax."""
    return _MD_BOLD_RE.sub(r"\1", text).replace("**", "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

# W2R (XG-W8): `research_note` shares the research planner. The two differ only
# in their config entry — cadence ceiling, word budget, model tier and
# `triage_tier` — because the note lane is the SAME beat at a smaller size, not
# a second beat. Growing a near-copy of _plan_research for it would have given
# the two desks two dedupe surfaces over one corpus.
_PLANNERS = {
    "brief": _plan_brief,
    "research_desk": _plan_research,
    "research_note": _plan_research,
}


def plan(desks=None, *, as_of=None, root=None, cfg: dict | None = None,
         extra_blocked_refs=None) -> list[dict]:
    """Plan today's slots for `desks` (default: every desk in config order).

    Deterministic and offline.  Returns a list of slot dicts (see the module
    docstring for the contract).  Never raises: a broken desk logs and yields
    nothing.
    """
    cfg = cfg if cfg is not None else load_config(root)
    desk_cfgs = cfg.get("desks") or {}
    want = list(desks) if desks else list(desk_cfgs.keys())

    run_date = _as_date(as_of, default=None) or date.today()

    pub_refs, _pub_slugs = published_refs(root, cfg)
    stg_refs, _stg_slugs = staged_refs(root, cfg)
    blocked = set(pub_refs) | set(stg_refs) | {str(r) for r in (extra_blocked_refs or [])}

    slots: list[dict] = []
    for name in want:
        desk_cfg = desk_cfgs.get(name)
        if not isinstance(desk_cfg, dict):
            log.warning("press.desk_planner: unknown desk %r — skipped", name)
            continue
        fn = _PLANNERS.get(name)
        if fn is None:
            log.warning("press.desk_planner: no planner for desk %r — skipped", name)
            continue
        try:
            slots.extend(fn(cfg, desk_cfg, run_date, root, blocked, name=name))
        except Exception as exc:  # noqa: BLE001
            log.warning("press.desk_planner: desk %s planning failed: %s", name, exc)
    return slots
