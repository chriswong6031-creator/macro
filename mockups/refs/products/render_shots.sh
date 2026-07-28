#!/usr/bin/env bash
# Render committed review shots of the three flagship product pages.
# Mirrors mockups/x-ads-2026-07/render.sh (same playwright binary contract).
# Prereq: a static server on :8848 serving site/ from the worktree, e.g.
#   python3 -c "import functools,http.server;h=functools.partial(http.server.SimpleHTTPRequestHandler,directory='site');http.server.ThreadingHTTPServer(('127.0.0.1',8848),h).serve_forever()"
# ?still freezes reveal/draw animation (landing capture hook) so shots are deterministic.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT_DIR="$ROOT_DIR/mockups/refs/products/shots"
PLAYWRIGHT_BIN="${PLAYWRIGHT_BIN:-/opt/homebrew/Caskroom/miniconda/base/bin/playwright}"
BASE="${BASE:-http://localhost:8848}"

mkdir -p "$OUT_DIR"

for page in market-terminal mastermind-ai market-dashboards; do
  "$PLAYWRIGHT_BIN" screenshot --browser chromium --full-page \
    --viewport-size "1440,900" --wait-for-timeout 1200 \
    "$BASE/products/$page.html?still" "$OUT_DIR/$page-desktop-en.png"
  "$PLAYWRIGHT_BIN" screenshot --browser chromium --full-page \
    --viewport-size "1440,900" --wait-for-timeout 1200 \
    "$BASE/products/$page.html?still&lang=zh" "$OUT_DIR/$page-desktop-zh.png"
  "$PLAYWRIGHT_BIN" screenshot --browser chromium --full-page \
    --viewport-size "390,844" --wait-for-timeout 1200 \
    "$BASE/products/$page.html?still" "$OUT_DIR/$page-mobile-en.png"
done
echo "shots -> $OUT_DIR"
