from __future__ import annotations

import json
import struct
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_DIR = ROOT / "mockups" / "x-mobile-ads-2026-07"
ASSET_DIR = ROOT / "site" / "assets" / "landing" / "x-mobile-ads-2026-07"


def _manifest() -> dict:
    return json.loads((CAMPAIGN_DIR / "manifest.json").read_text())


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    assert raw[12:16] == b"IHDR", f"{path} has no PNG IHDR"
    return struct.unpack(">II", raw[16:24])


def _campaigns() -> list[dict]:
    manifest = _manifest()
    return manifest["hero_creatives"] + manifest["carousel_creatives"]


def test_campaign_has_five_heroes_and_five_three_card_carousels() -> None:
    manifest = _manifest()
    assert len(manifest["hero_creatives"]) == 5
    assert len(manifest["carousel_creatives"]) == 5
    assert all(len(item["assets"]) == 3 for item in manifest["carousel_creatives"])
    assert len({item["angle"] for item in manifest["hero_creatives"]}) == 5
    assert [item["angle"] for item in manifest["hero_creatives"]] == [
        item["angle"] for item in manifest["carousel_creatives"]
    ]


def test_post_copy_destinations_and_utm_ids_are_launch_safe() -> None:
    ids: set[str] = set()
    for item in _campaigns():
        assert item["id"] not in ids
        ids.add(item["id"])
        assert 50 <= len(item["primary_text"]) <= 100
        assert len(item["headline"]) <= 70
        assert item["cta"] == "Sign up"
        parsed = urlparse(item["destination"])
        query = parse_qs(parsed.query)
        assert parsed.scheme == "https"
        assert parsed.netloc == "mastermind-x.com"
        assert query["utm_source"] == ["x"]
        assert query["utm_medium"] == ["paid"]
        assert query["utm_content"] == [item["id"]]


def test_offer_math_and_claim_are_precise() -> None:
    manifest = _manifest()
    terms = manifest["offer_terms"]
    assert terms["monthly_pro_usd"] * 12 - terms["founding_pro_annual_usd"] == 888
    assert terms["founding_pro_annual_usd"] // 12 == terms["founding_pro_monthly_equivalent_usd"]
    assert "standard annual" in terms["claim_guidance"]
    html = (CAMPAIGN_DIR / "index.html").read_text()
    assert "About 50% less" in html
    assert "50% off" not in html
    assert "Start 7-day trial" in html
    assert "Start your 7-day trial" in html


def test_every_asset_is_an_exact_mobile_first_png() -> None:
    expected = {
        Path(item["asset"]).name for item in _manifest()["hero_creatives"]
    }
    expected.update(
        Path(asset).name
        for item in _manifest()["carousel_creatives"]
        for asset in item["assets"]
    )
    assert len(expected) == 20
    assert ASSET_DIR.is_dir()
    assert {path.name for path in ASSET_DIR.glob("*.png")} == expected
    for filename in expected:
        path = ASSET_DIR / filename
        assert _png_dimensions(path) == (1440, 1800)
        assert path.stat().st_size < 5 * 1024 * 1024


def test_artboard_contains_every_asset_id() -> None:
    html = (CAMPAIGN_DIR / "index.html").read_text()
    assert 'id:`mx-mobile-${c.n}`' in html
    assert 'id:`mx-carousel-${c.n}-1`' in html
    assert 'id:`mx-carousel-${c.n}-2`' in html
    assert 'id:`mx-carousel-${c.n}-3`' in html
    assert html.count('n:"0') == 5


def test_mobile_type_scale_and_content_limits_are_explicit() -> None:
    html = (CAMPAIGN_DIR / "index.html").read_text()
    readme = (CAMPAIGN_DIR / "README.md").read_text()
    assert "--display:" in html
    assert "font-size:126px" in html
    assert "font-size:46px" in html
    assert "Three evidence points maximum" in readme
    assert "390 px rendered width" in readme
