"""The zh half of a macro alert body must be fully Chinese.

Six rules used to interpolate an English-valued token straight into their
`message_zh` f-string, so the wrapper punctuation and the surrounding nouns
translated while the clause inside them did not — the shape that shipped

    EN  GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)
    ZH  GEX：net GEX changed sign（净 +79bn，现价相对翻转点 -0.7%）

to the landing hub's "What changed" rows and the macro dashboard's
`ms-sig-detail`. The emitter is the only path the dashboard has (it renders
freshly-evaluated Alert objects, never the log), so a leak there is unrecoverable
downstream.

Three properties are pinned here:

  1. no English prose survives in an emitted `message_zh`;
  2. the emitter and `_translate_macro_detail` — build_vector's backlog translator
     for rows that predate the `message_zh` column — produce the SAME Chinese for
     the same alert. They disagreed for six rules, the emitter (which wins) was
     the wrong one, and nothing noticed;
  3. the already-baked half-translated rows in alerts_log.parquet still render
     fully Chinese through the hub's resolution, because log_and_dedup keys on
     (date, rule, message) and the English message never changes — no corrected
     row will ever supersede them.

`cycle_falsifier_fired:*` is the same defect one level up and is fenced in the
final section. It quotes a market thesis the curator WROTE — free prose, not a
finite label — so no vocabulary map can render it; the fix was a `claim_zh`
column in data/cycle_ontology/falsifiers.json plus a `_CYCLE_ZH` map for the
lowercase cycle slug the message also interpolates. The three properties above
apply to it unchanged.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import alerts  # noqa: E402
from engine.alerts import (  # noqa: E402
    _GEX_WHAT_ZH,
    _HOLDINGS_VERB_ZH,
    _RECESSION_BAND_ZH,
    _RISK_STATE_ZH,
    _TS_PLAIN_ZH,
)
from engine.falsifier_tripwires import (  # noqa: E402
    _CYCLE_ZH,
    TripwireResult,
    alert_bodies,
)
from engine.i18n import LEX as _LEX  # noqa: E402
from scripts.build_vector import (  # noqa: E402
    _ZH_HALF_TRANSLATED_PREFIXES,
    _ZH_HALF_TRANSLATED_RULES,
    _translate_macro_detail,
    _zh_needs_rebuild,
)

# Latin that is a NAME keeps its letters by design: tickers (XLRE, PSA), funds,
# quoted source slugs, and the few indicator names the Chinese copy also uses
# untranslated (NFCI, GEX, Sahm, RS, gamma, contango, and pp/bn/dma units).
_NAME_LIKE = re.compile(
    r"'[^']*'"                                          # 'sentiment_naaim'
    r"|\bgamma\b|\bcontango\b|\bpp\b|\bbn\b|\bdma\b|\bSahm\b")

# ALL-CAPS is NOT evidence of a name: the state labels that leaked here are also
# all-caps (WEAKENING, UNCONFIRMED TURN, RISK-OFF), so exempting uppercase runs
# wholesale would blind this check to half the defect. Tickers are separated from
# state labels by membership in the finite display vocabulary instead — every
# label below has a Chinese rendering and must never survive into zh copy.
_MUST_TRANSLATE_LABELS = frozenset(
    set(_TS_PLAIN_ZH) | set(_RISK_STATE_ZH)
    | {k for k in _LEX if isinstance(k, str) and k.isupper() and len(k) > 2})

_LOWER_PROSE = re.compile(r"[a-z]{3,}")


def _english_prose_in(zh: str) -> list[str]:
    """English left in a Chinese string: lowercase prose, or a finite-vocab label
    that has a Chinese rendering and should have been used."""
    found = _LOWER_PROSE.findall(_NAME_LIKE.sub(" ", zh))
    found += sorted(lbl for lbl in _MUST_TRANSLATE_LABELS if lbl in zh)
    return found


def _mk_hist(states: list[str]) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(states))
    return pd.DataFrame({
        "quad": "Q1", "transition_state": states, "n_flags": [3] * len(states),
        "growth_confidence": 0.5, "inflation_confidence": 0.5,
    }, index=idx)


# --------------------------------------------------------------------------- #
# Drive each formerly-leaking rule to a fired Alert.
# --------------------------------------------------------------------------- #

def _gex(monkeypatch, crossed_flip: bool):
    g = pd.DataFrame({
        "net_gex_bn":       [-40.0, 79.0] if not crossed_flip else [50.0, 60.0],
        "spot_vs_flip_pct": [-0.7, -0.9] if not crossed_flip else [0.8, -0.7],
    })
    monkeypatch.setattr(alerts.store, "read", lambda *a, **k: g)
    return alerts.gex_flip_cross(None, pd.DataFrame())


def _holdings(monkeypatch, chg_pct: float):
    ch = pd.DataFrame(
        {"active_chg_pct": [chg_pct],
         "window_start": ["2026-07-24"], "window_end": ["2026-07-31"]},
        index=["FIG"])
    import collectors.holdings as ch_mod
    monkeypatch.setattr(ch_mod, "active_changes", lambda t: ch if t == "ARKK" else None)
    return alerts.holdings_active_changes(None, pd.DataFrame())


def _sector(monkeypatch, direction: str):
    sig = {"fund": "XLRE", "ticker": "PSA", "active_change": 0.26,
           "direction": direction, "est_flow_mn": 23.0, "confirmed": True,
           "t0": "2026-07-17", "t1": "2026-07-24",
           "ladder": {"label": "UNCONFIRMED TURN", "action": "HIGH-RISK · NIMBLE ONLY"}}
    import engine.holdings_signals as hs
    monkeypatch.setattr(hs, "all_accumulation_signals", lambda: [sig])
    return alerts.sector_holdings_accumulation(None, pd.DataFrame())


def _recession(monkeypatch, prev_score: float, cur_score: float):
    monkeypatch.setattr(alerts, "_conditions_frame",
                        lambda f: pd.DataFrame({"recession_risk": [prev_score, cur_score]}))
    return alerts.conditions_recession_state_change(None, pd.DataFrame())


def _risk_state(monkeypatch, cur: float):
    import engine.risk_state as rs
    bands = rs._cfg()["bands"]
    monkeypatch.setattr(rs, "core_series",
                        lambda f: pd.Series([float(bands["elevated"]) - 5.0, cur]))
    return alerts.risk_state_elevated(None, pd.DataFrame())


def _fired(monkeypatch) -> list:
    """One fired Alert per formerly-leaking rule, both branches where they differ."""
    out = [
        alerts.transition_state_change(_mk_hist(["STABLE"] * 5 + ["WEAKENING"]), pd.DataFrame()),
        alerts.transition_state_change(_mk_hist(["WEAKENING"] * 5 + ["NEW_REGIME"]), pd.DataFrame()),
        _gex(monkeypatch, crossed_flip=False),
        _gex(monkeypatch, crossed_flip=True),
        *_holdings(monkeypatch, -100.0),
        *_holdings(monkeypatch, +45.0),
        *_sector(monkeypatch, "accumulating"),
        *_sector(monkeypatch, "trimming"),
    ]
    rc = alerts.config.load()["engine"]["conditions"]["recession"]
    out.append(_recession(monkeypatch, rc["elevated_score"] - 10, rc["high_score"] + 5))
    out.append(_recession(monkeypatch, rc["high_score"] + 5, rc["elevated_score"] - 10))
    bands = __import__("engine.risk_state", fromlist=["x"])._cfg()["bands"]
    out.append(_risk_state(monkeypatch, float(bands["risk_off"]) + 2))
    out.append(_risk_state(monkeypatch, float(bands["elevated"]) + 1))
    fired = [a for a in out if a is not None]
    assert len(fired) == len(out), "a fixture stopped firing — the rule shapes moved"
    return fired


# --------------------------------------------------------------------------- #

def test_emitted_zh_carries_no_english_prose(monkeypatch):
    """Property 1 — the defect itself."""
    leaked = {}
    for a in _fired(monkeypatch):
        words = _english_prose_in(a.message_zh)
        if words:
            leaked[a.rule] = (a.message_zh, words)
    assert not leaked, (
        "message_zh interpolates untranslated English — the half-translated shape "
        "that reaches the hub feed and ms-sig-detail:\n"
        + "\n".join(f"  {r}: {zh}\n      leaked: {w}" for r, (zh, w) in leaked.items()))


def test_emitter_agrees_with_backlog_translator(monkeypatch):
    """Property 2 — the two zh paths must not drift apart again.

    build_vector._translate_macro_detail rebuilds zh from the canonical English
    for rows that predate the message_zh column. When it and the emitter disagree
    one of them is wrong, and the stored value silently wins on the hub.
    """
    drift = {}
    for a in _fired(monkeypatch):
        rebuilt = _translate_macro_detail(a.message)
        if not rebuilt:
            continue          # rule has no backlog branch — nothing to agree with
        if rebuilt != a.message_zh:
            drift[a.rule] = (a.message_zh, rebuilt)
    assert not drift, (
        "engine/alerts.py and scripts/build_vector._translate_macro_detail render "
        "the same alert differently:\n"
        + "\n".join(f"  {r}\n    emitter   : {e}\n    translator: {t}"
                    for r, (e, t) in drift.items()))


def test_state_vocabularies_cover_the_emitters_domain():
    """Property 1, statically — a new state must not fall through to English."""
    # transition_state_change's own severity map is the state domain
    src = __import__("inspect").getsource(alerts.transition_state_change)
    states = set(re.findall(r'"([A-Z_]{4,})":\s*"(?:info|warn|act)"', src))
    assert states, "severity map shape moved — this test can no longer see the domain"
    assert states <= set(_TS_PLAIN_ZH), (
        f"transition states with no Chinese: {sorted(states - set(_TS_PLAIN_ZH))}")

    gex_src = __import__("inspect").getsource(alerts.gex_flip_cross)
    whats = set(re.findall(r'what = "([^"]+)" if crossed_flip else "([^"]+)"', gex_src)[0])
    assert whats <= set(_GEX_WHAT_ZH), (
        f"GEX clauses with no Chinese: {sorted(whats - set(_GEX_WHAT_ZH))}")

    assert {"added", "cut"} <= set(_HOLDINGS_VERB_ZH)
    assert {"low", "elevated", "high"} <= set(_RECESSION_BAND_ZH)
    assert {"RISK-OFF", "ELEVATED"} <= set(_RISK_STATE_ZH)


def test_hub_feed_heals_baked_half_translated_rows(monkeypatch):
    """Property 3, through the REAL resolution — not a re-implementation of it.

    Drives scripts.build_vector.home_alert_feed over a parquet of poisoned rows,
    so emptying _ZH_HALF_TRANSLATED_RULES or dropping the heal branch reds here.
    """
    import scripts.build_vector as bv

    poisoned = pd.DataFrame([
        {"date": "2026-08-04", "rule": "gex_flip_cross", "severity": "warn",
         "message": "GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)",
         "message_zh": "GEX：net GEX changed sign（净 +79bn，现价相对翻转点 -0.7%）"},
        {"date": "2026-08-03", "rule": "transition_state_change", "severity": "act",
         "message": "Transition state WEAKENING -> TRANSITIONING (3 flags active)",
         "message_zh": "转换状态 WEAKENING -> TRANSITIONING（3 个预警激活）"},
        {"date": "2026-08-02", "rule": "sector_holdings_accumulation", "severity": "warn",
         "message": ("XLRE: PSA weight +0.26pp beyond price (≈+$23M est. rebalance flow) "
                     "(accumulating), 2026-07-17..2026-07-24 — cycle UNCONFIRMED TURN·"
                     "HIGH-RISK · NIMBLE ONLY"),
         "message_zh": ("XLRE：PSA 权重较价格多变动 +0.26pp（≈+$23M 估算再平衡资金流）（增持），"
                        "2026-07-17..2026-07-24 — 周期 UNCONFIRMED TURN·HIGH-RISK · NIMBLE ONLY")},
    ])
    monkeypatch.setattr(bv.pd, "read_parquet", lambda *a, **k: poisoned)

    feed = [i for i in bv.home_alert_feed() if i["source"] == "macro"]
    assert len(feed) == len(poisoned), "the poisoned rows did not reach the feed"
    bad = [f"  {i['type']}: {i['detail_zh']}\n      leaked: {_english_prose_in(i['detail_zh'])}"
           for i in feed if _english_prose_in(i["detail_zh"])]
    assert not bad, (
        "home_alert_feed still serves the stored half-translated zh — the heal "
        "branch or _ZH_HALF_TRANSLATED_RULES stopped covering these rules:\n"
        + "\n".join(bad))


def test_baked_log_rows_still_render_chinese():
    """The real shipped log, so a row shape the translator cannot parse is caught."""
    pytest.importorskip("pyarrow")
    p = ROOT / "data" / "alerts" / "alerts_log.parquet"
    if not p.exists():
        pytest.skip("alerts_log.parquet not present")
    df = pd.read_parquet(p)
    bad = []
    for _, r in df[df["rule"].isin(_ZH_HALF_TRANSLATED_RULES)].iterrows():
        stored = str(r.get("message_zh", "") or "").strip()
        resolved = _translate_macro_detail(r["message"]) or stored or r["message"]
        words = _english_prose_in(resolved)
        if words:
            bad.append(f"  {r['rule']} [{r['date']}]: {resolved}\n      leaked: {words}")
    assert not bad, (
        "half-translated backlog rows still reach the hub feed — the translator "
        "lost a branch these rows depend on:\n" + "\n".join(bad[:8]))


def test_leaky_rule_set_matches_the_translator_coverage():
    """Every rule listed as needing the heal must actually have a branch to heal with."""
    samples = {
        "gex_flip_cross": "GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)",
        "transition_state_change": "Transition state WEAKENING -> TRANSITIONING (3 flags active)",
        "conditions_recession_state_change": "Recession-risk band low -> elevated (score 62/100)",
        "risk_state_elevated": (
            "Equity risk-state crossed into RISK-OFF (78/100) — positioning/vol/breadth "
            "fragility building; de-gross, favor entries over chasing leaders"),
        "holdings_active_change": (
            "ARKK: manager cut FIG by -100% of position "
            "(2026-07-24..2026-07-31, flow-normalized)"),
        "sector_holdings_accumulation": (
            "XLRE: PSA weight +0.26pp beyond price (≈+$23M est. rebalance flow) "
            "(accumulating), 2026-07-17..2026-07-24 — cycle UNCONFIRMED TURN·"
            "HIGH-RISK · NIMBLE ONLY"),
    }
    assert set(samples) == set(_ZH_HALF_TRANSLATED_RULES), (
        "_ZH_HALF_TRANSLATED_RULES changed — update the sample messages so the "
        "heal stays covered")
    for rule, msg in samples.items():
        zh = _translate_macro_detail(msg)
        assert zh, f"{rule}: translator has no branch, so the heal is a no-op"
        assert not _english_prose_in(zh), f"{rule}: heal output still English: {zh}"


# --------------------------------------------------------------------------- #
# cycle_falsifier_fired:* — the authored-prose half of the same defect.
#
#   ZH  周期改判条件触发 — long-bonds：'Long bonds have bottomed; 30yr yield peak
#       and TLT recovery confirm duration is buyable'（与原判断相反）。
#
# Two English values reach the zh body: the curator's `claim` (free prose — only
# a written `claim_zh` can render it) and the `cycle` slug, which is lowercase
# English and so leaks even when the claim is Chinese.
# --------------------------------------------------------------------------- #
FALSIFIERS_JSON = ROOT / "data" / "cycle_ontology" / "falsifiers.json"
FALSIFIERS_RETIRED_JSON = ROOT / "data" / "cycle_ontology" / "falsifiers_retired.json"


def _registry() -> list[dict]:
    if not FALSIFIERS_JSON.exists():
        pytest.skip("falsifiers.json not present")
    return json.loads(FALSIFIERS_JSON.read_text(encoding="utf-8"))


def _retired_registry() -> list[dict]:
    """Claim pairs kept alive only so baked alert rows stay healable.

    Deliberately NOT folded into `_registry()`: the property tests above sweep
    the LIVE registry (every row must carry claim_zh, drive the emitter, and
    name a cycle in the vocabulary), and a retired row is not a live falsifier —
    it has no dsl, no direction, and never fires again.  It is a translation
    fallback, so only the lookup below sees it.
    """
    if not FALSIFIERS_RETIRED_JSON.exists():
        return []
    return json.loads(FALSIFIERS_RETIRED_JSON.read_text(encoding="utf-8"))


def _entry(fid: str) -> dict:
    """The registry row for `fid`, live first, then retired.

    A row re-authored in place (v1 → v2) leaves the log holding rows keyed to
    the retired id, so a test that builds one of those rows has to be able to
    reach the retired pair — the same resolution order the healer itself uses.
    """
    for row in list(_registry()) + list(_retired_registry()):
        if row.get("id") == fid:
            return row
    raise AssertionError(
        f"{fid} is in neither falsifiers.json nor falsifiers_retired.json — a "
        "baked alert row keyed to it can no longer be healed")


def _as_fired(entry: dict) -> TripwireResult:
    """A registry row as the FIRED result the emitter would be handed.

    Built from the JSON rather than evaluate_all() so the fence runs without the
    price tapes — and so a missing `claim_zh` reaches the emitter exactly as the
    nightly would deliver it.
    """
    return TripwireResult(
        id=entry["id"], cycle=entry["cycle"], version=entry.get("version", 1),
        state="FIRED", fired_on="2026-08-06", latched=True, current_leg=True,
        claim=entry.get("claim", ""), claim_zh=entry.get("claim_zh", ""),
        direction=entry.get("direction", "refutes"),
        coverage=entry.get("coverage", "none"), expires=entry.get("expires"),
    )


def test_every_registered_claim_carries_written_chinese():
    """Property 1 at the source — the claim is prose, so the copy must exist."""
    missing = [e["id"] for e in _registry() if not str(e.get("claim_zh") or "").strip()]
    assert not missing, (
        "falsifiers.json entries with no claim_zh — their alert body will quote "
        f"the English thesis to a Chinese reader: {missing}")


def test_registered_chinese_claims_carry_no_english_prose():
    leaked = {e["id"]: (e["claim_zh"], _english_prose_in(e["claim_zh"]))
              for e in _registry()
              if _english_prose_in(str(e.get("claim_zh") or ""))}
    assert not leaked, (
        "authored claim_zh still carries English:\n"
        + "\n".join(f"  {i}: {zh}\n      leaked: {w}" for i, (zh, w) in leaked.items()))


def test_cycle_vocabulary_covers_the_registry():
    """A new cycle must not fall through to its lowercase English slug."""
    cycles = {e["cycle"] for e in _registry()}
    assert cycles <= set(_CYCLE_ZH), (
        f"cycles with no Chinese name: {sorted(cycles - set(_CYCLE_ZH))}")


def test_cycle_read_change_emitter_zh_carries_no_english_prose():
    """Property 1 — every registry row driven through the real emitter."""
    leaked = {}
    for entry in _registry():
        _, zh = alert_bodies(_as_fired(entry))
        words = _english_prose_in(zh)
        if words:
            leaked[entry["id"]] = (zh, words)
    assert not leaked, (
        "cycle read-change message_zh interpolates untranslated English:\n"
        + "\n".join(f"  {i}: {zh}\n      leaked: {w}" for i, (zh, w) in leaked.items()))


def test_cycle_read_change_emitter_agrees_with_backlog_translator():
    """Property 2 — both translator lookup paths must match the emitter.

    The translator resolves the zh claim by falsifier id when the caller passes
    the rule, and by claim text when it does not; a disagreement on either path
    means the hub can serve a different sentence than the dashboard.
    """
    drift = {}
    for entry in _registry():
        r = _as_fired(entry)
        en, zh = alert_bodies(r)
        for label, rebuilt in (
            ("by id", _translate_macro_detail(en, f"cycle_falsifier_fired:{r.id}")),
            ("by claim", _translate_macro_detail(en)),
        ):
            if rebuilt != zh:
                drift[f"{r.id} ({label})"] = (zh, rebuilt)
    assert not drift, (
        "engine/falsifier_tripwires.alert_bodies and _translate_macro_detail "
        "render the same alert differently:\n"
        + "\n".join(f"  {k}\n    emitter   : {e}\n    translator: {t}"
                    for k, (e, t) in drift.items()))


def test_cycle_read_change_rule_ids_are_matched_by_prefix():
    """The heal set is keyed by exact rule id; this rule's id is per-tripwire."""
    rule = "cycle_falsifier_fired:long-bonds.bear_steepener.v1"
    assert rule not in _ZH_HALF_TRANSLATED_RULES, (
        "per-tripwire rule ids can never be enumerated in the exact-match set")
    assert _zh_needs_rebuild(rule), (
        "home_alert_feed would serve the stored half-translated zh for "
        f"{rule} — _ZH_HALF_TRANSLATED_PREFIXES stopped covering it")
    assert not _zh_needs_rebuild("gold_breakout"), (
        "an unrelated rule must keep its stored zh — a prefix that matches "
        "everything would silently downgrade richer emitter copy")
    assert any(p.startswith("cycle_falsifier_fired") for p in _ZH_HALF_TRANSLATED_PREFIXES)


def test_the_completeness_check_can_actually_see_a_leaked_claim():
    """The assertions above are only real if the emitter keeps English visible.

    _NAME_LIKE strips '...' spans before looking for English, so quoting the
    claim in ASCII single quotes — the shape that shipped — hides the very leak
    these tests exist to catch, and every cycle assertion in this file passes on
    a body that is still half English. Drive the REAL emitter with English in
    both interpolated slots and require the guard to see each one.
    """
    claim_en = "Long bonds have bottomed; 30yr yield peak and TLT recovery confirm"
    entry = next(e for e in _registry() if e["id"] == "long-bonds.bear_steepener.v1")

    untranslated_claim = _as_fired({**entry, "claim": claim_en, "claim_zh": ""})
    _, zh = alert_bodies(untranslated_claim)
    assert _english_prose_in(zh), (
        "an English claim survives the completeness check inside the emitted "
        f"body — the quote style exempts it from _NAME_LIKE:\n  {zh}")

    unknown_cycle = _as_fired({**entry, "cycle": "long-bonds-v2"})
    _, zh = alert_bodies(unknown_cycle)
    assert _english_prose_in(zh), (
        "a cycle slug with no _CYCLE_ZH entry is invisible to the check — a new "
        f"cycle would ship its lowercase English name to zh readers:\n  {zh}")


def test_direction_is_read_from_the_suffix_not_the_claim():
    """Both directions round-trip, and a claim that quotes the direction phrase
    does not flip it — the registry has only `refutes` rows today, so the
    `confirms` half of the map is otherwise never exercised.
    """
    entry = next(e for e in _registry() if e["id"] == "gold.bull_intact.v1")
    for direction, expect_zh in (("refutes", "与原判断相反"), ("confirms", "支持原判断")):
        r = _as_fired({**entry, "direction": direction})
        en, zh = alert_bodies(r)
        assert expect_zh in zh, f"{direction} rendered as {zh}"
        assert _translate_macro_detail(en, f"cycle_falsifier_fired:{r.id}") == zh

    # A claim is free prose and may itself contain the direction phrase; only
    # the metadata suffix decides. (The zh CLAIM here comes from the registry by
    # id, not from this fixture — that re-worded-claim resilience is the point of
    # the id lookup and is asserted below.)
    trap = _as_fired({**entry, "claim": "Gold supports the read that real rates have peaked"})
    en, _ = alert_bodies(trap)       # direction stays refutes
    rebuilt = _translate_macro_detail(en, f"cycle_falsifier_fired:{trap.id}")
    assert "与原判断相反" in rebuilt, (
        f"the direction was read out of the claim prose, not the suffix: {rebuilt}")
    assert entry["claim_zh"] in rebuilt, (
        "a logged row whose claim text was later re-worded lost its Chinese — "
        "the id lookup must outrank the claim-text match")
    assert not _english_prose_in(rebuilt)


def test_translator_reads_both_logged_message_shapes():
    """The backlog rows predate the current emitter; neither shape may go dark.

    The live shape quotes the claim and trails "(coverage: X, direction: Y).";
    the older one trails ". Direction: X. Coverage: Y." unquoted. Both are in
    the register-swept vocabulary, and #3821's "Cycle falsifier FIRED" prefix
    still sits in the oldest rows.
    """
    entry = next(e for e in _registry() if e["id"] == "credit.spread_regime.v1")
    shapes = [
        (f"Cycle read-change condition HIT — credit: '{entry['claim']}' "
         "(coverage: partial, direction: cuts against the read)."),
        (f"Cycle read-change condition HIT — credit: {entry['claim']}. "
         "Direction: cuts against the read. Coverage: partial."),
        (f"Cycle falsifier FIRED — credit: '{entry['claim']}' "
         "(coverage: partial, direction: cuts against the read)."),
    ]
    for msg in shapes:
        zh = _translate_macro_detail(msg, f"cycle_falsifier_fired:{entry['id']}")
        assert zh, f"translator lost a logged shape: {msg}"
        assert entry["claim_zh"] in zh, f"claim not rendered for shape: {msg}"
        assert not _english_prose_in(zh), f"{zh}\n  leaked: {_english_prose_in(zh)}"


# The two shapes the log actually holds: rows written before the message_zh
# column existed (healed by the translator alone) and the 2026-07-29 row that
# persisted a zh body with the English thesis inside it (healed only if the
# rebuild outranks the stored value). One row per case — every cycle read-change
# row shares alert_view's generic plain_en, so the feed's concept-dedupe
# collapses two of them into a single card.
#
# bitcoin.cycle_position.v1 is RETIRED (re-authored to .v2 on 2026-08-10 with new
# claim text) and is resolved out of falsifiers_retired.json — which is the point
# of the case: the live registry can no longer answer for it by id OR by claim,
# so the row only heals if the retired pairs are merged into both maps.
_BAKED_ROW_SHAPES = {
    "stored-half-translated": ("long-bonds.bear_steepener.v1", True),
    "pre-zh-column": ("bitcoin.cycle_position.v1", False),
}


@pytest.mark.parametrize("shape", sorted(_BAKED_ROW_SHAPES))
def test_hub_feed_heals_baked_cycle_read_change_rows(monkeypatch, shape):
    """Property 3, through the REAL home_alert_feed — not a re-implementation."""
    import scripts.build_vector as bv

    fid, has_stored_zh = _BAKED_ROW_SHAPES[shape]
    entry = _entry(fid)
    # A retired pair carries no `coverage` (it never fires again); the token only
    # rides the stripped metadata suffix, so any value exercises the same path.
    en_msg = (
        f"Cycle read-change condition HIT — {entry['cycle']}: "
        f"'{entry['claim']}' (coverage: {entry.get('coverage', 'full')}, "
        "direction: cuts against the read).")
    stored_zh = (f"周期改判条件触发 — {entry['cycle']}：'{entry['claim']}'（与原判断相反）。"
                 if has_stored_zh else "")
    poisoned = pd.DataFrame([{
        "date": "2026-07-29", "rule": f"cycle_falsifier_fired:{fid}",
        "severity": "warn", "message": en_msg, "message_zh": stored_zh,
    }])
    monkeypatch.setattr(bv.pd, "read_parquet", lambda *a, **k: poisoned)

    feed = [i for i in bv.home_alert_feed() if i["source"] == "macro"]
    assert len(feed) == 1, "the poisoned row did not reach the feed"
    detail_zh = feed[0]["detail_zh"]
    assert not _english_prose_in(detail_zh), (
        "home_alert_feed still serves English inside the Chinese wrapper for a "
        f"cycle read-change row:\n  {detail_zh}\n"
        f"      leaked: {_english_prose_in(detail_zh)}")
    assert "周期改判条件触发" in detail_zh, "the sanctioned register wording was lost"
    assert entry["claim_zh"] in detail_zh, "the authored zh claim is not the one served"


# --------------------------------------------------------------------------- #
# Retired claim pairs.
#
# Re-authoring a row in place (v1 → v2, the #5194 convention) is the house way to
# register a successor thesis, and it deletes the old id.  While the successor
# keeps the SAME claim text the healer still resolves the baked row by_claim —
# which is why the pgms/agriculture renames were invisible here.  bitcoin's v2
# changed the claim text too, so BOTH lookups went dark at once and the English
# thesis reached the Chinese feed.  falsifiers_retired.json is the fix, and these
# pin each half of it.
# --------------------------------------------------------------------------- #
_RETIRED_BITCOIN_V1 = "bitcoin.cycle_position.v1"


def _retired_entry(fid: str) -> dict:
    for row in _retired_registry():
        if row.get("id") == fid:
            return row
    pytest.skip(f"{fid} not present in falsifiers_retired.json")


def test_retired_pair_heals_a_baked_row_by_id():
    """by_id path — the id is gone from the live registry, so only retired answers."""
    entry = _retired_entry(_RETIRED_BITCOIN_V1)
    assert not any(e["id"] == _RETIRED_BITCOIN_V1 for e in _registry()), (
        f"{_RETIRED_BITCOIN_V1} is live again — this test no longer proves the "
        "retired lookup, move it to a genuinely retired id")

    msg = (f"Cycle read-change condition HIT — {entry['cycle']}: "
           f"'{entry['claim']}' (coverage: full, direction: cuts against the read).")
    zh = _translate_macro_detail(msg, f"cycle_falsifier_fired:{_RETIRED_BITCOIN_V1}")

    assert zh, "the translator dropped a retired-id row entirely"
    assert entry["claim_zh"] in zh, (
        "the retired pair's authored Chinese was not served — the baked row's "
        f"English claim leaks instead:\n  {zh}")
    assert entry["claim"] not in zh, f"the English claim survived into the zh body:\n  {zh}"
    assert not _english_prose_in(zh), f"{zh}\n      leaked: {_english_prose_in(zh)}"


def test_retired_pair_heals_a_baked_row_by_claim_with_no_rule():
    """by_claim path — the oldest rows reach the translator with no rule to hand.

    This is the half a claim-text-preserving rename would have kept working on
    its own; with bitcoin v2's new claim text it survives only through retired.
    """
    entry = _retired_entry(_RETIRED_BITCOIN_V1)
    live_claims = {str(e.get("claim")) for e in _registry()}
    assert entry["claim"] not in live_claims, (
        "the retired claim text is still live — by_claim would resolve without "
        "the retired file, so this test would pass for the wrong reason")

    msg = (f"Cycle read-change condition HIT — {entry['cycle']}: "
           f"'{entry['claim']}' (coverage: full, direction: cuts against the read).")
    zh = _translate_macro_detail(msg, "")

    assert zh, "the translator dropped a retired-claim row with no rule"
    assert entry["claim_zh"] in zh, (
        f"by_claim did not reach the retired pair:\n  {zh}")
    assert not _english_prose_in(zh), f"{zh}\n      leaked: {_english_prose_in(zh)}"


def test_live_registry_outranks_a_colliding_retired_row(tmp_path, monkeypatch):
    """A retired copy must never shadow the current registry, in either map.

    Retirement is append-only bookkeeping and nothing prunes it, so the day an
    id or a claim string is reused the live row is the one a reader must see.
    """
    import scripts.build_vector as bv

    onto = tmp_path / "data" / "cycle_ontology"
    onto.mkdir(parents=True)
    (onto / "falsifiers.json").write_text(json.dumps([{
        "id": "collide.v1", "cycle": "bitcoin", "version": 1,
        "direction": "refutes", "claim": "shared claim text",
        "claim_zh": "现行注册表的中文", "coverage": "full",
    }], ensure_ascii=False), encoding="utf-8")
    (onto / "falsifiers_retired.json").write_text(json.dumps([{
        "id": "collide.v1", "cycle": "bitcoin", "claim": "shared claim text",
        "claim_zh": "已退役的旧中文", "retired": "2026-08-10",
    }], ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(bv.config, "ROOT", tmp_path)
    bv._falsifier_registry.cache_clear()
    try:
        by_id, by_claim = bv._falsifier_registry()
        assert by_id["collide.v1"]["claim_zh"] == "现行注册表的中文", (
            "a retired row shadowed the live registry by id")
        assert by_claim["shared claim text"]["claim_zh"] == "现行注册表的中文", (
            "a retired row shadowed the live registry by claim text")
    finally:
        bv._falsifier_registry.cache_clear()


def test_missing_retired_file_falls_back_to_the_live_registry(tmp_path, monkeypatch):
    """No retired file is the pre-existing state, not an error."""
    import scripts.build_vector as bv

    onto = tmp_path / "data" / "cycle_ontology"
    onto.mkdir(parents=True)
    (onto / "falsifiers.json").write_text(json.dumps([{
        "id": "solo.v1", "cycle": "bitcoin", "claim": "only live",
        "claim_zh": "只有现行的",
    }], ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(bv.config, "ROOT", tmp_path)
    bv._falsifier_registry.cache_clear()
    try:
        by_id, by_claim = bv._falsifier_registry()
        assert set(by_id) == {"solo.v1"}
        assert set(by_claim) == {"only live"}
    finally:
        bv._falsifier_registry.cache_clear()
