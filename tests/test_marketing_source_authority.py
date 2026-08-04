"""tests/test_marketing_source_authority.py — A CITATION MUST EARN ITS PLACE.

Fixture-driven; ZERO live network, ZERO live LLM.

OPERATOR LAW, 2026-08-04: "Reduce the citing unless it's a popular news outlet
that can help to give us authority. We shouldn't be citing some random site like
ForexLive or citing other X accounts. But we can say WSJ, Reuters, NYT... We gain
when we cite from big shots, we gain nothing and even lose prestige by citing
places no one knows about."

THE STRING THIS REPLACES. Every single-source item carried "-- wire reports".
There is no masthead called Wire — it was an anonymiser written on 2026-08-02 to
stop an X relay shipping "-- @FirstSquawk reporting", and it solved de-branding
by making EVERY credit read as a source nobody has heard of, including the ones
we could have credited to Reuters.

WHAT IS PINNED, and the mutation each pin is armed against:
  1. The tiering itself, by host / feed key / display name.
  2. "wire reports" is GONE from every composed path.
  3. An X relay is never a citation EVEN when it relays a marquee newsroom —
     what we hold is the relay, not the newsroom's copy (the 2026-07-31
     fabricated-dateline lesson, applied to credits).
  4. THE HALF THAT KEEPS THE SILENCE HONEST: dropping a credit is only lawful
     when the item can stand without one. An uncreditable CLAIM is downgraded to
     the digest, not posted bare — otherwise "cite less" would quietly become
     "present unverified hearsay as our own reporting".
  5. The direct-quote VENUE ("on Truth Social") survives: it says where the words
     were said, which is evidence, not borrowed standing.
  6. The gate can only be TIGHTENED by this layer, never loosened.
  7. Config promotes and retires without a code change; `never_cite` is absolute.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import source_authority as sa  # noqa: E402
from engine.marketing.press_corroboration import corroboration_decision  # noqa: E402


def _item(**kw):
    base = {
        "id": "t1", "source": "x", "source_name": "X", "source_tier": "wire",
        "event_class": "macro_print", "corroboration_class": "hearsay",
        "headline": "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate",
        "url": "",
    }
    base.update(kw)
    return base


# ── 1. Tiering ────────────────────────────────────────────────────────────────

class TestTiers:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.reuters.com/markets/x", "marquee"),
        ("https://eu.reuters.com/markets/x", "marquee"),   # subdomain
        ("https://www.wsj.com/articles/x", "marquee"),
        ("https://www.nytimes.com/2026/x", "marquee"),
        ("https://www.bls.gov/news.release/x", "primary"),
        ("https://www.federalreserve.gov/x", "primary"),
        ("https://investinglive.com/news/x", "unnamed"),
        ("https://www.zerohedge.com/x", "unnamed"),
        ("https://some-blog.substack.com/p/x", "unnamed"),
    ])
    def test_host_is_the_durable_key(self, url, expected):
        """Hosts, not display names: a feed key gets renamed and a brand gets
        rebranded (forexlive.com 301s to investinglive.com today), but the host
        is what the item actually arrived from."""
        assert sa.authority_tier(_item(url=url)) == expected

    def test_display_name_resolves_when_there_is_no_url(self):
        assert sa.authority_tier(_item(source_name="Reuters")) == "marquee"
        assert sa.authority_tier(_item(source_name="Federal Reserve")) == "primary"
        assert sa.authority_tier(_item(source_name="ForexLive")) == "unnamed"

    def test_a_body_mentioning_reuters_does_not_promote_a_no_name_relay(self):
        """Exact match on the configured name, never a substring — otherwise any
        item whose text says "Reuters" would launder itself into the tier."""
        it = _item(source_name="ForexLive",
                   headline="Reuters reports the ECB is weighing a cut")
        assert sa.authority_tier(it) == "unnamed"


# ── 2-3. The credit clause ───────────────────────────────────────────────────

class TestCredit:
    def test_wire_reports_is_gone(self):
        """The string itself, from the path that emitted it. The old code
        returned it for every single-source hearsay item."""
        it = _item(source="forexlive_news", source_name="ForexLive",
                   url="https://investinglive.com/news/x")
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        assert decision["attribution"] == "wire reports"        # unchanged upstream
        resolved = sa.resolve_attribution(it, decision)
        assert resolved["attribution"] == ""                    # ...and dropped here

    def test_a_marquee_source_is_named(self):
        it = _item(source="reuters_top", source_name="Reuters",
                   url="https://www.reuters.com/markets/x")
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        assert sa.resolve_attribution(it, decision)["attribution"] == "Reuters"

    def test_a_primary_source_is_named(self):
        it = _item(source="bls_news", source_name="Bureau of Labor Statistics",
                   source_tier="official", url="https://www.bls.gov/x")
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        r = sa.resolve_attribution(it, decision)
        assert r["attribution"] == "Bureau of Labor Statistics"
        assert r["tier"] == "primary"

    def test_an_x_relay_is_never_a_citation(self):
        """Even relaying a marquee newsroom. What we hold is the RELAY, not the
        newsroom's own copy — citing Reuters for a tweet we read on someone
        else's account is a provenance claim we cannot support."""
        it = _item(source="x_FirstSquawk", source_name="Reuters",
                   source_tier="x_relay", x_handle="FirstSquawk")
        assert sa.authority_tier(it) == "unnamed"

    def test_a_mirror_parenthetical_is_stripped_not_posted(self):
        it = _item(source_name="Reuters (via someone's mirror)",
                   url="https://www.reuters.com/x")
        assert sa.citation(it)["credit"] == "Reuters"


# ── 4. The half that keeps the silence honest ────────────────────────────────

class TestSelfEvidence:
    @pytest.mark.parametrize("kw", [
        {"event_class": "macro_print"},
        {"source_tier": "official"},
        {"event_class": "none",
         "headline": "German factory orders fell 2.4% vs -0.8% expected"},
    ])
    def test_a_checkable_fact_posts_with_no_credit(self, kw):
        it = _item(source_name="ForexLive", url="https://investinglive.com/x", **kw)
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        r = sa.resolve_attribution(it, decision)
        assert r["attribution"] == ""
        assert r["gate"] != "digest"

    @pytest.mark.parametrize("kw", [
        {"event_class": "none",
         "headline": "Sources say the White House is preparing a new tariff package"},
        {"event_class": "none",
         "headline": "Exclusive: chipmaker weighs a $4bn plant, people familiar say"},
    ])
    def test_an_uncreditable_claim_goes_to_the_digest(self, kw):
        """"Cite less" must not become "present unverified hearsay as our own
        reporting". With no name to offer the reader, a claim has nothing left to
        stand on."""
        it = _item(source_name="ForexLive", url="https://investinglive.com/x", **kw)
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        r = sa.resolve_attribution(it, decision)
        assert r["gate"] == "digest"
        assert r["downgraded"] is True

    def test_the_same_claim_posts_when_a_masthead_is_on_it(self):
        """The asymmetry IS the design — the claim is identical, the standing is
        not."""
        head = "Sources say the White House is preparing a new tariff package"
        it = _item(source_name="Reuters", url="https://www.reuters.com/x",
                   event_class="none", headline=head)
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        r = sa.resolve_attribution(it, decision)
        assert r["gate"] != "digest"
        assert r["attribution"] == "Reuters"


# ── 5-6. What this layer may not touch ───────────────────────────────────────

class TestBoundaries:
    def test_the_direct_quote_venue_survives(self):
        """"on Truth Social" is locative evidence, not borrowed standing — and it
        is what makes quoting a Truth Social post honest at all."""
        it = _item(source="trumpstruth", source_name="Truth Social (via trumpstruth.org)",
                   source_tier="mirror", corroboration_class="direct-quote",
                   headline="Talks begin later today")
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        assert decision["attribution"] == "on Truth Social"
        r = sa.resolve_attribution(it, decision)
        assert r["attribution"] == "on Truth Social"
        assert r["tier"] == "venue"

    def test_the_gate_is_never_loosened(self):
        """This layer decides whose name appears and may REFUSE a post. It can
        never promote one the corroboration law already refused."""
        it = _item(source_name="Reuters", url="https://www.reuters.com/x",
                   event_class="geopolitical")
        decision = corroboration_decision(it, corroborated_sources=1, window_ok=False)
        assert decision["gate"] == "digest"
        assert sa.resolve_attribution(it, decision)["gate"] == "digest"


# ── 7. Config ────────────────────────────────────────────────────────────────

class TestConfig:
    def test_never_cite_is_absolute(self):
        it = _item(source_name="Reuters", url="https://www.reuters.com/x")
        assert sa.authority_tier(it, cfg={"never_cite": ["reuters.com"]}) == "unnamed"

    def test_marquee_extra_promotes(self):
        it = _item(source_name="Some Desk", url="https://somedesk.example/x")
        assert sa.authority_tier(it) == "unnamed"
        assert sa.authority_tier(
            it, cfg={"marquee_extra": ["somedesk.example"]}) == "marquee"

    def test_the_shipped_config_parses_and_retires_the_three_named_sources(self):
        import yaml
        cfg = (yaml.safe_load((ROOT / "config" / "press_sources.yml")
                              .read_text(encoding="utf-8")) or {}).get("citation", {})
        assert isinstance(cfg, dict) and "never_cite" in cfg
        for host in ("investinglive.com", "zerohedge.com", "investing.com"):
            assert sa.authority_tier(
                _item(url=f"https://{host}/x"), cfg=cfg) == "unnamed"
