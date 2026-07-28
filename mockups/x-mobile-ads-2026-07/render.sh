#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAGE_PATH="$ROOT_DIR/mockups/x-mobile-ads-2026-07/index.html"
OUT_DIR="$ROOT_DIR/site/assets/landing/x-mobile-ads-2026-07"
PLAYWRIGHT_BIN="${PLAYWRIGHT_BIN:-/opt/homebrew/Caskroom/miniconda/base/bin/playwright}"

mkdir -p "$OUT_DIR"

for number in 01 02 03 04 05; do
  hero_id="mx-mobile-$number"
  "$PLAYWRIGHT_BIN" screenshot \
    --browser chromium \
    --viewport-size "1440,1800" \
    --wait-for-timeout 900 \
    "file://$PAGE_PATH?creative=$hero_id" \
    "$OUT_DIR/$hero_id.png"

  for slide in 1 2 3; do
    carousel_id="mx-carousel-$number-$slide"
    "$PLAYWRIGHT_BIN" screenshot \
      --browser chromium \
      --viewport-size "1440,1800" \
      --wait-for-timeout 900 \
      "file://$PAGE_PATH?creative=$carousel_id" \
      "$OUT_DIR/$carousel_id.png"
  done
done
