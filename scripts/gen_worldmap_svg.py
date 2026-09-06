"""scripts/gen_worldmap_svg.py — one-shot, off-render-path generator for
templates/_worldmap_base.html.j2 from Natural Earth 1:110m Admin-0 country
geometry (public domain / CC0). NEVER invoked by the nightly.

This is provenance tooling: given a local Natural Earth GeoJSON/shapefile
export (not vendored into this repo — download from
https://www.naturalearthdata.com/downloads/110m-cultural-vectors/ and pass
its path), it projects each country polygon into the page's 1000x500
viewBox and emits one `<path class="wm-c" data-iso3="XXX">` per country,
with the Jinja `data-rung` conditional the template partial needs.

Usage:
  python3 scripts/gen_worldmap_svg.py <path-to-ne_110m_admin_0.geojson> \
      > templates/_worldmap_base.html.j2
"""
from __future__ import annotations

import json
import sys


def _project(lon: float, lat: float, w: int = 1000, h: int = 500) -> tuple[float, float]:
    """Equirectangular projection into the 1000x500 viewBox."""
    x = (lon + 180.0) / 360.0 * w
    y = (90.0 - lat) / 180.0 * h
    return round(x, 2), round(y, 2)


def _ring_to_path(ring: list[list[float]]) -> str:
    pts = [_project(lon, lat) for lon, lat in ring]
    d = f"M{pts[0][0]},{pts[0][1]} " + " ".join(f"L{x},{y}" for x, y in pts[1:]) + " Z"
    return d


def geometry_to_path(geom: dict) -> str:
    parts: list[str] = []
    if geom["type"] == "Polygon":
        for ring in geom["coordinates"]:
            parts.append(_ring_to_path(ring))
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            for ring in poly:
                parts.append(_ring_to_path(ring))
    return " ".join(parts)


def main(geojson_path: str) -> None:
    with open(geojson_path, encoding="utf-8") as fh:
        fc = json.load(fh)

    print(
        "{# World base geometry — Natural Earth 1:110m Admin 0 (public "
        "domain / CC0).\n"
        "   Regenerate: python3 scripts/gen_worldmap_svg.py <path> > "
        "templates/_worldmap_base.html.j2\n"
        "   Expects: `rungs` (dict iso3 -> 1|2|3) in the render context. #}"
    )
    print(
        '<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" '
        'aria-hidden="true" focusable="false">'
    )
    print(
        '<defs><pattern id="sm-hatch" width="5" height="5" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="5"/></pattern></defs>'
    )
    for feat in fc["features"]:
        iso3 = feat["properties"].get("ADM0_A3") or feat["properties"].get("ISO_A3")
        if not iso3 or iso3 == "-99":
            continue
        d = geometry_to_path(feat["geometry"])
        print(
            f'<path class="wm-c" data-iso3="{iso3}"'
            "{% if rungs.get('" + iso3 + "') %} data-rung=\"{{ rungs['"
            + iso3
            + "'] }}\"{% endif %} d=\"" + d + '"/>'
        )
    print("</svg>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1])
