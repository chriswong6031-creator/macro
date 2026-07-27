"""tests/press_fixtures.py — shared fixtures for the D14 press-engine suites.

NOT collected by pytest (the filename does not match test_*.py).  Imported by
tests/test_press_*.py.

Everything here is synthetic.  No fixture reads or writes the real data/ or
site/ trees — the MM_DATA_GUARD tripwire in tests/conftest.py fails the whole
run on a stray write, and a press test that quietly published into the repo's
own blog would be exactly the accident this engine exists to prevent.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

REPO = _REPO

# ─────────────────────────────────────────────────────────────────────────────
# A raw "source document" — shaped like a research-vault summary_points blob.
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_DOC = (
    "Middle East oil supply shock: renewed geopolitical tension across the "
    "Strait of Hormuz drives Brent December contracts toward 120 dollars per "
    "barrel, triggering leveraged binary call structures for energy and credit "
    "exposure hedging across the desk's institutional book. "
    "Gas storage crisis: north west European storage sits at fourteen year lows "
    "of 28 percent end season while an Asian liquefied natural gas demand "
    "recovery forces the Dutch benchmark toward 65 euros per megawatt hour, "
    "risking demand destruction into the winter contract."
)

# Copied verbatim out of SOURCE_DOC — this must FAIL close_paraphrase.
LIFTED_PARAGRAPH = (
    "renewed geopolitical tension across the Strait of Hormuz drives Brent "
    "December contracts toward 120 dollars per barrel, triggering leveraged "
    "binary call structures for energy and credit exposure hedging across the "
    "desk's institutional book"
)

# The same facts, actually rewritten — this must PASS close_paraphrase.
REWRITTEN_PARAGRAPH = (
    "The desk's case rests on two prices. It puts Brent's December contract at "
    "120 dollars, and it reaches that number through Hormuz rather than through "
    "demand — a supply argument, not a growth one. Its hedge of choice is a "
    "levered binary structure, which tells you the desk is buying a jump, not a "
    "drift"
)


# Six paragraphs of ordinary original prose, used to give a fixture piece a
# REALISTIC length.  The document-level-Jaccard demonstration needs it: the
# whole failure mode being pinned is that one lifted paragraph disappears into
# a full-length article when the metric is not length-normalised.
FILLER_PARAGRAPHS = (
    "Two things happened on the same afternoon and only one of them was priced. "
    "The first was procedural and the second was not, which is usually the order "
    "in which these weeks go wrong for people who read only the headline.",
    "Our own reading starts from what we can measure rather than from what the "
    "tape felt like. That is a slower way to be right and a much slower way to "
    "be wrong, and on a week like this one the difference is the whole story.",
    "The obvious objection is that any one session tells you very little. That "
    "objection is correct. What follows is not an argument about the session; it "
    "is an argument about where the burden of proof now sits.",
    "Positioning explains part of it. Flows explain another part. Neither "
    "explains the piece that showed up in our own record, which is why we are "
    "writing about the piece nobody has an easy story for yet.",
    "Anyone who has watched this corner for a few years will recognise the "
    "shape. Recognising a shape is not the same as knowing what comes next, and "
    "the honest version of this paragraph stops at the recognition.",
    "So the useful question is not what to do about it today. The useful "
    "question is which single number would tell you the picture had changed, and "
    "whether you would actually notice it in time.",
)


def facts(*, first_party_values=(56, 65.7), third_party_values=(120,)) -> list[dict]:
    """A planner-shaped fact list with both tiers represented."""
    out = [
        {
            "id": "fp_state", "ref": "artifact:data/market_state/latest.json",
            "tier": "first_party", "values": [first_party_values[0]],
            "text": f"Mastermind's market-state composite reads "
                    f"{first_party_values[0]} of 100 as of 2026-07-24.",
            "dated": "2026-07-24",
            "url": None, "source_name": "Mastermind market-state engine",
        },
        {
            "id": "fp_risk", "ref": "artifact:data/risk_radar/forward_log.jsonl",
            "tier": "first_party", "values": [first_party_values[1]],
            "text": f"The risk radar's dominant scare scores "
                    f"{first_party_values[1]} as of 2026-07-24.",
            "dated": "2026-07-24",
            "url": None, "source_name": "Mastermind risk radar",
        },
    ]
    for i, v in enumerate(third_party_values):
        out.append({
            "id": f"tp_{i}", "ref": "research_vault:demo-report",
            "tier": "third_party", "values": [v],
            "text": f"The desk puts the December contract at {v} dollars.",
            "dated": "2026-07-24",
            "url": "https://www.mastermind-x.com/research/demo-report.html",
            "source_name": "Outside desk research",
        })
    return out


def slot(**overrides) -> dict:
    """A planner slot good enough for every validator."""
    base = {
        "id": "press-brief-2026-07-26-testslot01",
        "desk": "brief",
        "publication": "mastermind_news",
        "byline": "The Brief — Mastermind News desk",
        "cluster": "market-brief",
        "as_of": "2026-07-26",
        "model_key": "press_brief",
        "min_words": 60,
        "max_words": 900,
        "min_anchored_receipts": 0,   # per-test override; see receipts_slot()
        "story": {"kind": "risk_band", "title_hint": "Risk radar flips to caution"},
        # Every W1 slot is FIRST-PARTY: receipts inline, no source link.
        # /radar.html — the URL W1 originally used here — is a regwall 302.
        "primary_source": {
            "kind": "first_party",
            "name": "Mastermind risk radar",
            "url": None,
            "ref": "chronicle:risk_radar_forward_log#2026-07-24",
        },
        "sources": ["chronicle:risk_radar_forward_log#2026-07-24"],
        "seed_refs": ["artifact:data/market_state/latest.json"],
        "facts": facts(),
        "raw_documents": [{"ref": "research_vault:demo-report", "text": SOURCE_DOC}],
        "chronicle_context": {"lines": [], "narratives": [], "budget_used": 0,
                              "coverage": {"start": None, "end": None, "note": ""}},
        "slug_hint": "risk-radar-flips-to-caution",
    }
    base.update(overrides)
    return base


BYLINE_HTML = '<p class="press-byline">The Brief — Mastermind News desk</p>'
FOOTER_HTML = ('<p class="press-footer">Educational content — not investment '
               'advice. Markets involve risk.</p>')

# First-party fold: names the desk, carries a dated receipt, links NOTHING.
# (W1 originally linked /radar.html here — a 302 to the signin page.)
ABOVE_FOLD = (
    '<p>The Mastermind risk radar moved to caution on 2026-07-24, and the '
    'dominant scare scored 65.7 — worth reading before the next session '
    'opens.</p>'
)

# A gated internal link, for the allowlist test. Verified 2026-07-26: this URL
# answers 302 to https://www.mastermind-x.com/?signin=1&ret=/radar.html
GATED_LINK_HTML = (
    '<p>See <a href="https://www.mastermind-x.com/radar.html">the radar</a>.</p>'
)
# A public one — /research/ is on the config allowlist (verified 200).
PUBLIC_LINK_HTML = (
    '<p>See <a href="https://www.mastermind-x.com/research/demo-report.html">'
    'our coverage</a>.</p>'
)


def external_slot(**overrides) -> dict:
    """A slot carrying an EXTERNAL primary source — the only kind the
    above-the-fold named+linked source law applies to (PRESS-FEEDS shape)."""
    base = slot(**overrides)
    base["primary_source"] = {
        "kind": "external",
        "name": "Bureau of Labor Statistics",
        "url": "https://www.bls.gov/news.release/empsit.nr0.htm",
        "ref": "feed:bls-empsit-2026-07-24",
    }
    return base


def body(*paragraphs: str, byline: bool = True, footer: bool = True,
         fold: bool = True) -> str:
    """Assemble a compliant body fragment around the paragraphs given."""
    parts: list[str] = []
    if byline:
        parts.append(BYLINE_HTML)
    if fold:
        parts.append(ABOVE_FOLD)
    parts.extend(f"<p>{p}</p>" for p in paragraphs)
    if footer:
        parts.append(FOOTER_HTML)
    return "\n".join(parts)


def draft(*paragraphs: str, title: str = "Risk radar moves to caution",
          description: str | None = None, slug: str = "risk-radar-moves-to-caution",
          **body_kwargs) -> dict:
    if description is None:
        # 120–155 chars is a hard contract with the estate builder.
        description = (
            "The risk radar moved to caution this week. Here is what our own "
            "measurements say about it, and the level that would settle it."
        )
    return {
        "title": title,
        "description": description,
        "slug": slug,
        "body_html": body(*paragraphs, **body_kwargs),
    }


def config(**overrides) -> dict:
    """The REAL config/press.yml, so thresholds under test are the shipped ones."""
    import yaml

    cfg = yaml.safe_load((REPO / "config" / "press.yml").read_text(encoding="utf-8"))
    cfg.update(overrides)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# A minimal repo root for orchestrator / planner tests
# ─────────────────────────────────────────────────────────────────────────────

_EVENTS = [
    {"id": "cev-risk-1", "ts": "2026-07-24T00:00:00Z", "date": "2026-07-24",
     "source": "risk_band", "source_ref": "risk_radar_forward_log#2026-07-24",
     "kind": "risk", "title": "Risk radar: watch to caution",
     "facts": ["watch to caution; dominant scare: growth; top score 65.7"],
     "tickers": [], "themes": ["risk"], "horizon_hint": "short", "weight_hint": 2,
     "links": {"site": None, "source": None, "receipt": None}},
    {"id": "cev-prophet-1", "ts": "2026-07-24T00:00:00Z", "date": "2026-07-24",
     "source": "prophet_ledger", "source_ref": "UBER-BULL-20260623",
     "kind": "plan_close", "title": "Prophet close: UBER BULL to INVALIDATED",
     "facts": ["outcome=INVALIDATED; stock -11.41% (plan result); held 31d"],
     "tickers": ["UBER"], "themes": [], "horizon_hint": "short", "weight_hint": 2,
     "links": {"site": None, "source": None, "receipt": None}},
    {"id": "cev-vault-1", "ts": "2026-07-25T00:00:00Z", "date": "2026-07-25",
     "source": "research_vault", "source_ref": "demo-vault-001",
     "kind": "research", "title": "Outside desk: the winter gas trade",
     "facts": ["storage at fourteen year lows"],
     "tickers": [], "themes": [], "horizon_hint": "medium", "weight_hint": 3,
     "links": {"site": "/research/demo-report.html", "source": None, "receipt": None}},
    # Dated AFTER as_of — the hard right edge must exclude it.
    {"id": "cev-future-1", "ts": "2026-08-01T00:00:00Z", "date": "2026-08-01",
     "source": "risk_band", "source_ref": "risk_radar_forward_log#2026-08-01",
     "kind": "risk", "title": "Risk radar: caution to alarm",
     "facts": ["caution to alarm"], "tickers": [], "themes": ["risk"],
     "horizon_hint": "short", "weight_hint": 3,
     "links": {"site": None, "source": None, "receipt": None}},
]

_CATALOG = {
    "schema": "research_vault.catalog.v1",
    "generated_at": "2026-07-26T00:00:00+00:00",
    "count": 2,
    "institutions": ["Outside Desk", "Another Desk"],
    "items": [
        {"id": "marketdesk-demo1-aaa111", "title": "The Winter Gas Trade",
         "institution": "Outside Desk", "side": "sell", "desk": "",
         "published_at": "2026-07-25T09:00:00Z",
         "summary_points": [SOURCE_DOC], "tags": [], "tickers": [],
         "top_pick": True, "pages": 12, "needs_metadata": False},
        {"id": "marketdesk-demo2-bbb222", "title": "Rates Into The Autumn",
         "institution": "Another Desk", "side": "sell", "desk": "",
         "published_at": "2026-07-20T09:00:00Z",
         "summary_points": ["Front-end pricing has moved 18 basis points."],
         "tags": [], "tickers": [], "top_pick": False, "pages": 8,
         "needs_metadata": False},
    ],
}


# Two engine artifacts with DELIBERATELY different as-of dates.
#
# market_state is dated inside the window: it is what gives a fixture slot real
# receipts to anchor against.  gex is dated in the FUTURE, and it is the whole
# point of the point-in-time test — before the W1 review the planner read these
# snapshots without checking their `asof`, so a run dated 2026-07-26 happily
# quoted a 2026-08-05 measurement.  A fixture with no engine artifacts at all
# (the original) made that test vacuously green.
_MARKET_STATE_IN_WINDOW = {
    "schema": "market_state.v1", "asof": "2026-07-24", "score": 56,
    "verdict": "MIXED", "headline_en": "Mixed / transition.",
    "components": [
        {"key": "trend", "label_en": "Trend & technicals", "score": 62, "weight": 0.24},
        {"key": "risk", "label_en": "Risk appetite", "score": 70, "weight": 0.18},
        {"key": "breadth", "label_en": "Breadth & participation", "score": 68, "weight": 0.16},
        {"key": "liquidity", "label_en": "Liquidity & credit", "score": 76, "weight": 0.14},
    ],
}
_GEX_FROM_THE_FUTURE = {
    "asof": "2026-08-05",
    "indices": {"SPX": {"spot": 7412.0, "net_gex_bn": -99.9, "gamma_flip": 7443.92,
                        "dist_to_flip_pct": -0.43}},
}


def fixture_root(tmp_path: Path, *, ledger_rows=None, staged=None,
                 engine_artifacts: bool = True) -> Path:
    """Build a minimal repo root under tmp_path.

    Carries config/press.yml (the real one), a small chronicle store, a small
    vault catalog, the press data tree, and two dated engine artifacts — one
    inside the point-in-time window, one after it.  Pass
    ``engine_artifacts=False`` for the fail-soft case (no artifacts at all).
    """
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "config" / "press.yml", root / "config" / "press.yml")

    chron = root / "data" / "chronicle"
    chron.mkdir(parents=True, exist_ok=True)
    (chron / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in _EVENTS), encoding="utf-8")

    vault = root / "data" / "research_vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "catalog.json").write_text(json.dumps(_CATALOG), encoding="utf-8")

    press = root / "data" / "press"
    (press / "staging").mkdir(parents=True, exist_ok=True)
    (press / "published.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in (ledger_rows or [])), encoding="utf-8")

    for name, obj in (staged or {}).items():
        (press / "staging" / name).write_text(json.dumps(obj), encoding="utf-8")

    if engine_artifacts:
        ms = root / "data" / "market_state"
        ms.mkdir(parents=True, exist_ok=True)
        (ms / "latest.json").write_text(json.dumps(_MARKET_STATE_IN_WINDOW), encoding="utf-8")
        gx = root / "data" / "gex"
        gx.mkdir(parents=True, exist_ok=True)
        (gx / "latest.json").write_text(json.dumps(_GEX_FROM_THE_FUTURE), encoding="utf-8")

    (root / "content" / "seo" / "blog").mkdir(parents=True, exist_ok=True)
    return root


def draft_from_slot(slot: dict, n: int = 0, *, extra_filler: int = 0) -> dict:
    """A COMPLIANT draft built out of the slot's own facts.

    A stub writer that invents its numbers produces a draft that fails
    fact_anchor, which makes every orchestrator test vacuous: 'passed +
    quarantined == planned' holds just as well when nothing ever passes.  This
    derives its receipts from the slot, so the passing path is genuinely
    exercised.
    """
    import re as _re

    values: list[str] = []
    for f in slot.get("facts") or []:
        for v in f.get("values") or []:
            if v not in values and _re.fullmatch(r"-?\d+(?:\.\d+)?", str(v)):
                values.append(str(v))
        if len(values) >= 8:
            break
    receipts = values[:8] or ["56"]

    # Anchored sentences scale with the desk's word budget. A longer piece needs
    # MORE receipts, not more filler — which is exactly the pressure the
    # sentence-granularity share is supposed to apply to a real writer.
    reps = 2 if int(slot.get("min_words") or 300) > 400 else 1
    sentences = [
        f"Our own reading puts that number at {v} on the session we are "
        f"describing, which is the figure the rest of this piece leans on."
        for v in receipts * reps
    ]
    # The fold is built from the SLOT, not from a module constant: a hardcoded
    # number is a number some other slot's fact pool has never heard of, and
    # fact_anchor is right to reject it.
    fold = (f'<p>{slot["primary_source"]["name"]} moved on the session we are '
            f'describing, and our own reading of it starts at {receipts[0]}.</p>')
    half = max(1, len(sentences) // 2)
    paras = [fold,
             "<p>" + " ".join(sentences[:half]) + "</p>",
             "<p>" + " ".join(sentences[half:]) + "</p>"]
    filler = list(FILLER_PARAGRAPHS)[: 4 + extra_filler]
    body = "\n".join([BYLINE_HTML.replace("The Brief — Mastermind News desk",
                                          str(slot.get("byline") or ""))] + paras
                      + [f"<p>{t}</p>" for t in filler] + [FOOTER_HTML])
    suffix = f"-{n}" if n else ""
    return {
        "title": f"A first-party read of the session{suffix}",
        "description": ("Our own measurements moved this week. Here is what the "
                        "composite and the radar say about it, and the level "
                        "that would settle the question."),
        "slug": f"a-first-party-read-of-the-session{suffix}",
        "body_html": body,
    }
