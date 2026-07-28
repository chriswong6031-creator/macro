from __future__ import annotations

import json
import struct
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_DIR = ROOT / "mockups" / "x-ads-2026-07"
ASSET_DIR = ROOT / "site" / "assets" / "marketing" / "x-ads-2026-07"


def _manifest() -> dict:
    return json.loads((CAMPAIGN_DIR / "manifest.json").read_text())


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    assert raw[12:16] == b"IHDR", f"{path} has no PNG IHDR"
    return struct.unpack(">II", raw[16:24])


def test_campaign_has_ten_complete_ab_pairs() -> None:
    creatives = _manifest()["creatives"]
    assert len(creatives) == 20
    assert Counter(item["variant"] for item in creatives) == {"A": 10, "B": 10}
    assert Counter(item["pair"] for item in creatives) == {pair: 2 for pair in range(1, 11)}


def test_ids_copy_and_destinations_are_launch_safe() -> None:
    creatives = _manifest()["creatives"]
    ids = [item["id"] for item in creatives]
    assert len(ids) == len(set(ids))

    for item in creatives:
        assert 50 <= len(item["primary_text"]) <= 100
        assert len(item["headline"]) <= 70
        assert item["cta"] in {"Sign up", "Learn more"}

        parsed = urlparse(item["destination"])
        query = parse_qs(parsed.query)
        assert parsed.scheme == "https"
        assert parsed.netloc == "mastermind-x.com"
        assert query["utm_source"] == ["x"]
        assert query["utm_medium"] == ["paid"]
        assert query["utm_content"] == [item["id"]]


def test_offer_math_and_wording_are_precise() -> None:
    manifest = _manifest()
    terms = manifest["offer_terms"]
    assert terms["monthly_pro_usd"] * 12 - terms["founding_pro_annual_usd"] == 888
    assert terms["founding_pro_annual_usd"] // 12 == terms["founding_pro_monthly_equivalent_usd"]
    assert "standard annual" in terms["claim_guidance"]

    offer_copy = " ".join(
        item["primary_text"] + " " + item["headline"]
        for item in manifest["creatives"]
        if item["pair"] == 10
    )
    assert "about 50%" in offer_copy.lower()
    assert "50% off annual" not in offer_copy.lower()


def test_every_manifest_asset_is_a_1200_by_628_png() -> None:
    for item in _manifest()["creatives"]:
        path = ROOT / item["asset"]
        assert path.is_file(), f"missing rendered asset: {path}"
        assert _png_dimensions(path) == (1200, 628)


def test_artboard_contains_every_creative_id() -> None:
    html = (CAMPAIGN_DIR / "index.html").read_text()
    for item in _manifest()["creatives"]:
        assert item["id"] in html
