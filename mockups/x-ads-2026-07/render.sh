#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAGE_PATH="$ROOT_DIR/mockups/x-ads-2026-07/index.html"
OUT_DIR="$ROOT_DIR/site/assets/landing/x-category-ads-2026-07"
PLAYWRIGHT_BIN="${PLAYWRIGHT_BIN:-/opt/homebrew/Caskroom/miniconda/base/bin/playwright}"

mkdir -p "$OUT_DIR"

for ad_id in mx-cat-01 mx-cat-02 mx-cat-03 mx-cat-04 mx-cat-05; do
  "$PLAYWRIGHT_BIN" screenshot \
    --browser chromium \
    --viewport-size "1440,1800" \
    --wait-for-timeout 800 \
    "file://$PAGE_PATH?ad=$ad_id" \
    "$OUT_DIR/$ad_id.png"
done
