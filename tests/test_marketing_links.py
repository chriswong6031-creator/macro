"""tests/test_marketing_links.py — Funnel W1a (D07): UTM link builder + short-link lane tests.

Test list:
1. test_canonical_link_format — exact string equality, fixed param order, encoding, empty→"unknown"
2. test_short_code_deterministic — same id → same code, 10 chars, charset, two ids differ
3. test_tag_text_rewrites_untagged — base-domain collapses to ONE canonical; example.com untouched;
   trailing punctuation not eaten; idempotent
4. test_attach_links_every_item — every item gets link/short_code/short_link; summary counts correct; idempotent
5. test_content_plan_integration — full plan via content_plan(); every item has is_tagged_canonical link;
   utm params match item fields; posts_linked equals total queue items; exactly-once rule
6. test_short_link_pages_deterministic — build twice → same file set, byte-identical; meta-refresh correct;
   robots noindex; no timestamp; path = <code>/index.html
7. test_codes_stable_across_rebuilds — post_id→short_code and link identical across two independent builds
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone as _tz
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Root helper (mirrors test_marketing_content.py convention)
# ─────────────────────────────────────────────────────────────────────────────

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures (mirror _SAMPLE_PLANS / _SAMPLE_ACCOUNTS from test_marketing_content.py)
# ─────────────────────────────────────────────────────────────────────────────

_FRESH = (datetime.now(_tz.utc).date() - timedelta(days=5)).isoformat()

_SAMPLE_PLANS = [
    {
        "id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL",
        "entry": 120.0, "invalidation": 100.0, "targets": [150.0, 180.0],
        "trigger": 125.0, "_conviction_score": 90, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 66.0, "what_to_do_now": [],
    },
    {
        "id": "SBUX-BULL", "asset": "SBUX", "direction": "BULL",
        "entry": 82.0, "invalidation": 75.0, "targets": [95.0, 110.0],
        "trigger": 84.0, "_conviction_score": 85, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 61.0, "what_to_do_now": [],
    },
    {
        "id": "BA-BEAR", "asset": "BA", "direction": "BEAR",
        "entry": 180.0, "invalidation": 200.0, "targets": [155.0, 130.0],
        "trigger": 178.0, "_conviction_score": 75, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 58.0, "what_to_do_now": [],
    },
]

_SAMPLE_ACCOUNTS = [
    {"id": "flagship", "kind": "branded", "beat": "What changed", "voice": "authoritative desk",
     "tilt": {"signal": 0.32, "chart": 0.10, "education": 0.08, "macro": 0.14,
               "receipt": 0.08, "watchlist": 0.05, "event": 0.05,
               "mover": 0.10, "theme_list": 0.08}},
    {"id": "receipts", "kind": "branded", "beat": "Receipt", "voice": "dry, receipts-forward",
     "tilt": {"signal": 0.26, "chart": 0.18, "education": 0.05, "macro": 0.07,
               "receipt": 0.18, "watchlist": 0.05, "event": 0.05,
               "mover": 0.08, "theme_list": 0.08}},
    {"id": "theme_desk", "kind": "branded", "beat": "Theme", "voice": "specialist",
     "tilt": {"signal": 0.28, "chart": 0.10, "education": 0.08, "macro": 0.08,
               "receipt": 0.06, "watchlist": 0.05, "event": 0.14,
               "mover": 0.10, "theme_list": 0.11}},
    {"id": "research_a", "kind": "generic", "beat": "Macro", "voice": "educational",
     "tilt": {"signal": 0.24, "chart": 0.08, "education": 0.18, "macro": 0.20,
               "receipt": 0.05, "watchlist": 0.05, "event": 0.03,
               "mover": 0.10, "theme_list": 0.07}},
    {"id": "research_b", "kind": "generic", "beat": "Fast", "voice": "fast, reactive",
     "tilt": {"signal": 0.30, "chart": 0.16, "education": 0.04, "macro": 0.06,
               "receipt": 0.06, "watchlist": 0.04, "event": 0.08,
               "mover": 0.14, "theme_list": 0.12}},
    {"id": "research_c", "kind": "generic", "beat": "Charts", "voice": "pattern/history",
     "tilt": {"signal": 0.26, "chart": 0.22, "education": 0.06, "macro": 0.06,
               "receipt": 0.05, "watchlist": 0.13, "event": 0.05,
               "mover": 0.10, "theme_list": 0.07}},
]

_MINIMAL_CFG = {
    "desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS},
    "links": {
        "base_url": "https://mastermind-x.com/",
        "utm_source": "x",
        "short_links": True,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. canonical_link format
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_link_format():
    from engine.marketing.links import canonical_link

    # Exact string equality for known input
    url = canonical_link("flagship", "signal", "post-123")
    assert url == (
        "https://mastermind-x.com/"
        "?utm_source=x"
        "&utm_medium=flagship"
        "&utm_campaign=signal"
        "&utm_content=post-123"
    ), f"Unexpected canonical link: {url}"

    # Params are in fixed order: source, medium, campaign, content
    parsed = urllib.parse.urlsplit(url)
    qs_pairs = urllib.parse.parse_qsl(parsed.query)
    keys = [k for k, _ in qs_pairs]
    assert keys == ["utm_source", "utm_medium", "utm_campaign", "utm_content"], (
        f"Param order wrong: {keys}"
    )

    # Percent-encoding of a kind containing a space and a unicode char
    url2 = canonical_link("acc", "signal type/β", "id-1")
    parsed2 = urllib.parse.urlsplit(url2)
    qs2 = urllib.parse.parse_qs(parsed2.query)
    assert qs2["utm_campaign"] == ["signal type/β"], (
        f"Encoding round-trip failed: {qs2.get('utm_campaign')}"
    )
    # The raw query must contain percent-encoded space (%20) and unicode (%CE%B2 or similar)
    raw_q = parsed2.query
    assert "+" not in raw_q or "%20" in raw_q or "%20" in urllib.parse.unquote_plus(raw_q), (
        "Space not percent-encoded"
    )

    # Empty account → "unknown"
    url3 = canonical_link("", "signal", "pid")
    qs3 = urllib.parse.parse_qs(urllib.parse.urlsplit(url3).query)
    assert qs3["utm_medium"] == ["unknown"], (
        f"Empty account should yield 'unknown', got: {qs3.get('utm_medium')}"
    )

    # None account also → "unknown"
    url4 = canonical_link(None, "signal", "pid")  # type: ignore[arg-type]
    qs4 = urllib.parse.parse_qs(urllib.parse.urlsplit(url4).query)
    assert qs4["utm_medium"] == ["unknown"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. short_code determinism and charset
# ─────────────────────────────────────────────────────────────────────────────

def test_short_code_deterministic():
    from engine.marketing.links import short_code

    # Same id → same code across multiple calls
    code1 = short_code("PLTR-BULL-signal-001")
    code2 = short_code("PLTR-BULL-signal-001")
    assert code1 == code2, "short_code is not deterministic"

    # Exactly 10 characters
    assert len(code1) == 10, f"Expected 10 chars, got {len(code1)}"

    # Charset: only [a-z2-7] (base32 lowercase)
    assert re.fullmatch(r"[a-z2-7]+", code1), (
        f"short_code contains invalid chars: {code1}"
    )

    # Two different ids → different codes (collision extremely unlikely for sha256)
    code_a = short_code("ALPHA-001")
    code_b = short_code("BETA-002")
    assert code_a != code_b, "Different ids produced the same short_code"


# ─────────────────────────────────────────────────────────────────────────────
# 3. tag_text rewrites untagged URLs
# ─────────────────────────────────────────────────────────────────────────────

def test_tag_text_rewrites_untagged():
    from engine.marketing.links import tag_text

    canonical = (
        "https://mastermind-x.com/"
        "?utm_source=x&utm_medium=flagship&utm_campaign=signal&utm_content=p1"
    )

    # Body with: bare domain, full URL, and unrelated URL
    body = (
        "Check mastermind-x.com for details. "
        "Also see https://mastermind-x.com/pricing for pricing. "
        "More at https://example.com/x for reference."
    )
    new_body, n = tag_text(body, canonical)

    # The two base-domain occurrences collapse to exactly ONE canonical occurrence
    assert new_body.count(canonical) == 1, (
        f"Expected exactly 1 canonical occurrence, found {new_body.count(canonical)}: {new_body}"
    )
    # example.com is untouched
    assert "https://example.com/x" in new_body, "example.com URL was incorrectly modified"

    # Trailing punctuation case: the sentence period after the domain must be
    # preserved as prose, separated by a space so it can never pollute the
    # canonical query string ("…utm_content=p1." would corrupt attribution).
    body2 = "Visit mastermind-x.com. See you there."
    new_body2, n2 = tag_text(body2, canonical)
    assert new_body2 == f"Visit {canonical} . See you there.", (
        f"Trailing period eaten or text mangled: {new_body2}"
    )
    assert n2 == 1

    # "?" directly after the domain: must not be fused onto the query string —
    # utm_content parsed from the emitted text must stay exactly the post id.
    body2q = "Have you seen mastermind-x.com?"
    new_body2q, n2q = tag_text(body2q, canonical)
    assert f"{canonical} ?" in new_body2q, f"'?' fused onto URL: {new_body2q}"
    url_in_text = re.search(r"https?://\S+", new_body2q).group(0)
    parsed_q = urllib.parse.parse_qs(urllib.parse.urlsplit(url_in_text).query)
    assert parsed_q["utm_content"] == ["p1"], f"utm_content polluted: {url_in_text}"

    # Already-canonical link followed by a period: untouched, 0 rewrites
    body2b = f"Visit {canonical}. See you there."
    new_body2b, n2b = tag_text(body2b, canonical)
    assert new_body2b == body2b and n2b == 0

    # Idempotent: second call → 0 rewrites, identical text
    new_body3, n3 = tag_text(new_body, canonical)
    assert n3 == 0, f"Second tag_text call should rewrite 0 URLs, got {n3}"
    assert new_body3 == new_body, "tag_text is not idempotent"


# ─────────────────────────────────────────────────────────────────────────────
# 4. attach_links — every item gets link/short_code/short_link; idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_attach_links_every_item():
    from engine.marketing.links import attach_links, canonical_link, short_code, short_link, is_tagged_canonical

    # Synthetic account_rows: 2 accounts × 3 items; one item's body carries an untagged URL
    account_rows = [
        {
            "id": "acct1",
            "queue": [
                {"id": "p1", "account": "acct1", "type": "signal",
                 "headline": "Check this out", "body": "Visit mastermind-x.com for details."},
                {"id": "p2", "account": "acct1", "type": "chart",
                 "headline": "Chart post", "body": "No domain links here."},
                {"id": "p3", "account": "acct1", "type": "education",
                 "headline": "Learn here", "body": "Go to https://mastermind-x.com/learn to learn."},
            ],
        },
        {
            "id": "acct2",
            "queue": [
                {"id": "p4", "account": "acct2", "type": "macro",
                 "headline": "Macro update", "body": "Plain body."},
                {"id": "p5", "account": "acct2", "type": "receipt",
                 "headline": "Receipt", "body": "Done."},
                {"id": "p6", "account": "acct2", "type": "watchlist",
                 "headline": "Watch this", "body": "Nothing to link."},
            ],
        },
    ]
    cfg = {"links": {"base_url": "https://mastermind-x.com/", "utm_source": "x", "short_links": True}}

    summary = attach_links(account_rows, cfg=cfg)

    # Every item has link, short_code, short_link
    all_items = [item for acct in account_rows for item in acct["queue"]]
    assert len(all_items) == 6

    for item in all_items:
        assert "link" in item, f"item {item['id']} missing 'link'"
        assert "short_code" in item, f"item {item['id']} missing 'short_code'"
        assert "short_link" in item, f"item {item['id']} missing 'short_link'"
        # link is the canonical link for this item
        expected = canonical_link(
            item["account"], item["type"], item["id"],
            base_url="https://mastermind-x.com/", utm_source="x",
        )
        assert item["link"] == expected, (
            f"item {item['id']} link mismatch: {item['link']} != {expected}"
        )
        assert is_tagged_canonical(item["link"]), f"item {item['id']} link not tagged canonical"
        assert item["short_code"] == short_code(item["id"]), "short_code mismatch"
        assert item["short_link"] == short_link(item["id"], base_url="https://mastermind-x.com/")

    # Summary counts
    assert summary["posts_linked"] == 6
    # p1 body had "mastermind-x.com" → retagged; p3 body had full URL → retagged
    assert summary["urls_rewritten"] >= 2

    # Idempotent: calling attach_links twice → identical items
    import copy
    rows_copy = copy.deepcopy(account_rows)
    summary2 = attach_links(rows_copy, cfg=cfg)
    for orig_acct, copy_acct in zip(account_rows, rows_copy):
        for orig_item, copy_item in zip(orig_acct["queue"], copy_acct["queue"]):
            assert orig_item["link"] == copy_item["link"]
            assert orig_item["short_code"] == copy_item["short_code"]
            assert orig_item["headline"] == copy_item["headline"]
            assert orig_item["body"] == copy_item["body"]
    # Second pass: urls_rewritten should be 0 (already canonical — idempotent)
    assert summary2["urls_rewritten"] == 0, (
        f"attach_links not idempotent: second pass rewrote {summary2['urls_rewritten']} URLs"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. content_plan integration
# ─────────────────────────────────────────────────────────────────────────────

def test_content_plan_integration():
    from engine.marketing.content_studio import content_plan
    from engine.marketing.links import is_tagged_canonical

    plan = content_plan(cfg=_MINIMAL_CFG, plans=_SAMPLE_PLANS, closes_loader=None)

    all_items = [item for acct in plan["accounts"] for item in acct.get("queue", [])]
    total = len(all_items)
    assert total > 0, "content_plan produced no queue items"

    # Every queue item has a link that is_tagged_canonical
    for item in all_items:
        assert "link" in item, f"item {item.get('id')} missing 'link'"
        assert is_tagged_canonical(item["link"]), (
            f"item {item.get('id')} link not tagged canonical: {item.get('link')}"
        )

        # utm params match item fields
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(item["link"]).query)
        assert qs.get("utm_medium", [None])[0] == item.get("account"), (
            f"utm_medium mismatch for {item.get('id')}"
        )
        assert qs.get("utm_campaign", [None])[0] == item.get("type"), (
            f"utm_campaign mismatch for {item.get('id')}"
        )
        assert qs.get("utm_content", [None])[0] == item.get("id"), (
            f"utm_content mismatch for {item.get('id')}"
        )

    # content.links.posts_linked equals total queue items
    links_block = plan.get("content", {}).get("links", {})
    assert links_block.get("posts_linked") == total, (
        f"posts_linked={links_block.get('posts_linked')} != total={total}"
    )

    # Exactly-once rule: any http(s) URL found in headline/body that is a base-domain URL
    # must equal the item's canonical link exactly (not a different tagged or untagged form)
    base_domain_re = re.compile(r"https?://(?:www\.)?mastermind-x\.com[^\s]*", re.IGNORECASE)
    for item in all_items:
        for field in ("headline", "body"):
            text = item.get(field, "") or ""
            matches = base_domain_re.findall(text)
            for m in matches:
                assert m == item["link"], (
                    f"item {item.get('id')} {field} contains non-canonical base-domain URL: {m!r} "
                    f"(expected {item['link']!r})"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 6. short_link_pages deterministic
# ─────────────────────────────────────────────────────────────────────────────

def test_short_link_pages_deterministic(tmp_path):
    from engine.marketing.content_studio import content_plan
    from engine.marketing.links import build_short_link_pages

    plan = content_plan(cfg=_MINIMAL_CFG, plans=_SAMPLE_PLANS, closes_loader=None)

    out1 = tmp_path / "go1"
    out2 = tmp_path / "go2"

    result1 = build_short_link_pages(plan, out1, cfg=_MINIMAL_CFG)
    result2 = build_short_link_pages(plan, out2, cfg=_MINIMAL_CFG)

    assert result1["pages_written"] > 0, "No pages written"
    assert result1["pages_written"] == result2["pages_written"], "Page count differs between runs"

    # Same file set
    files1 = sorted(str(p.relative_to(out1)) for p in out1.rglob("index.html"))
    files2 = sorted(str(p.relative_to(out2)) for p in out2.rglob("index.html"))
    assert files1 == files2, f"File sets differ: {files1} vs {files2}"

    # Byte-identical contents
    for rel in files1:
        content1 = (out1 / rel).read_text(encoding="utf-8")
        content2 = (out2 / rel).read_text(encoding="utf-8")
        assert content1 == content2, f"File {rel} differs between runs"

    # Each page: contains meta-refresh to item's link, robots noindex, NO timestamp-like content
    from engine.marketing.links import iter_plan_posts
    for item in iter_plan_posts(plan):
        code = item.get("short_code", "")
        if not code:
            from engine.marketing.links import short_code as _sc
            code = _sc(item.get("id", ""))
        page_path = out1 / code / "index.html"
        assert page_path.exists(), f"Expected page at {page_path}"
        # Path is <code>/index.html
        assert page_path.name == "index.html"
        assert page_path.parent.name == code

        content = page_path.read_text(encoding="utf-8")
        # meta-refresh present and points to item's link.
        # The page uses html.escape so & → &amp; in the HTML source.
        assert 'http-equiv="refresh"' in content, "meta-refresh missing"
        import html as _html
        escaped_link = _html.escape(item["link"], quote=True)
        assert escaped_link in content, (
            f"item link not in page: {item['link']!r}\npage: {content[:300]}"
        )
        # robots noindex
        assert "noindex" in content, "robots noindex missing"
        assert "nofollow" in content, "robots nofollow missing"
        # No timestamp-like content (no ISO datetime or epoch)
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", content), (
            f"Timestamp found in page: {content[:200]}"
        )
        assert not re.search(r"\b17\d{8}\b", content), "Epoch timestamp found in page"


# ─────────────────────────────────────────────────────────────────────────────
# 7. codes stable across rebuilds
# ─────────────────────────────────────────────────────────────────────────────

def test_codes_stable_across_rebuilds():
    from engine.marketing.content_studio import content_plan
    from engine.marketing.links import iter_plan_posts

    plan1 = content_plan(cfg=_MINIMAL_CFG, plans=_SAMPLE_PLANS, closes_loader=None)
    plan2 = content_plan(cfg=_MINIMAL_CFG, plans=_SAMPLE_PLANS, closes_loader=None)

    codes1 = {item["id"]: item.get("short_code") for item in iter_plan_posts(plan1)}
    codes2 = {item["id"]: item.get("short_code") for item in iter_plan_posts(plan2)}

    links1 = {item["id"]: item.get("link") for item in iter_plan_posts(plan1)}
    links2 = {item["id"]: item.get("link") for item in iter_plan_posts(plan2)}

    assert codes1 == codes2, (
        f"short_code mapping differs between rebuilds: {set(codes1.items()) ^ set(codes2.items())}"
    )
    assert links1 == links2, (
        f"link mapping differs between rebuilds: {set(links1.items()) ^ set(links2.items())}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. short_links flag respected (reviewer fix 3)
# ─────────────────────────────────────────────────────────────────────────────

def test_short_links_disabled(tmp_path):
    from engine.marketing.links import attach_links, build_short_link_pages

    cfg = {"links": {"short_links": False}}
    rows = [{"id": "flagship", "queue": [
        {"id": "post-flagship-001", "type": "signal", "account": "flagship",
         "headline": "H", "body": "B"},
    ]}]
    attach_links(rows, cfg=cfg)
    item = rows[0]["queue"][0]
    assert "short_code" not in item and "short_link" not in item
    assert "link" in item  # canonical link still attached

    plan = {"accounts": rows}
    res = build_short_link_pages(plan, tmp_path / "go", cfg=cfg)
    assert res["pages_written"] == 0
    assert not (tmp_path / "go").exists() or not any((tmp_path / "go").iterdir())


# ─────────────────────────────────────────────────────────────────────────────
# 9. post-tag length re-check (reviewer fix 2): validated copy that a retag
#    pushes past the copywriter budget falls back to the short link in-text;
#    if still over (short links off), the item is flagged — printed, not hidden.
# ─────────────────────────────────────────────────────────────────────────────

def test_overflow_falls_back_to_short_link():
    from engine.marketing.links import attach_links

    # Body sized so it passes 275 with the bare domain but not with the ~100-char
    # canonical link; the ~40-char short link fits again.
    filler = "x" * 230
    body = f"{filler} mastermind-x.com"
    rows = [{"id": "flagship", "queue": [
        {"id": "post-flagship-001", "type": "signal", "account": "flagship",
         "headline": "H", "body": body},
    ]}]
    summary = attach_links(rows, cfg=None)
    item = rows[0]["queue"][0]
    assert item["short_link"] in item["body"], f"short-link fallback missing: {item['body'][-80:]}"
    assert item["link"] not in item["body"]
    assert summary["overflow_shortened"] == 1
    assert "_link_overflow" not in item

    # Same overflow with short links disabled → canonical stays, item flagged
    rows2 = [{"id": "flagship", "queue": [
        {"id": "post-flagship-001", "type": "signal", "account": "flagship",
         "headline": "H", "body": body},
    ]}]
    summary2 = attach_links(rows2, cfg={"links": {"short_links": False}})
    item2 = rows2[0]["queue"][0]
    assert item2["link"] in item2["body"]
    assert item2.get("_link_overflow") is True
    assert summary2["overflow_flagged"] == 1

    # Idempotent: re-running on the shortened item changes nothing
    summary3 = attach_links(rows, cfg=None)
    assert rows[0]["queue"][0]["body"] == item["body"]
    assert summary3["urls_rewritten"] == 0
