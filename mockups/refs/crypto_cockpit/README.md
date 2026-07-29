# Crypto Cockpit W0 references

These are the approved-build reference surfaces for the staged Crypto Cockpit
program described in `research/CRYPTO_COCKPIT_MASTERPLAN.md`.

- `vector.html` pins the six-shelf BTC Vector information architecture.
- `crypto.html` pins the eight-shelf Crypto Intelligence hub.
- `cockpit.css` is mockup-only styling built from shared `theme.css` tokens.
- `build_refs.py` replaces the marked chart fragments with `regime_tape()`
  output sourced from the committed `site/vector_timeline.json`.
- `shots/` contains full-page light, dark, and Chinese reference proofs at
  1280px desktop and 375px mobile widths.

The mockups are intentionally static. W1 implements the Vector rebuild; W2
implements the hub and production promotion. Until those waves, the shelf
governor remains unarmed against the legacy templates.

Serve the repository root, then use query parameters to inspect a reference:

```text
http://127.0.0.1:8765/mockups/refs/crypto_cockpit/vector.html?theme=dark&lang=en
http://127.0.0.1:8765/mockups/refs/crypto_cockpit/crypto.html?theme=light&lang=zh
```
