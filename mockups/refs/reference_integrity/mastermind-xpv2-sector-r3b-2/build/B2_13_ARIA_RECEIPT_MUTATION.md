# B2-13 aria_receipt_audit.py — mutation proof
Mutation target: the literal `aria-controls="r3-receipt"` on the `[data-r3b1="02"]` Overview methodology button — the ONLY literal (non-variable-built) occurrence in the built candidate. Applied to an in-memory COPY inside a throwaway temp directory; the real proposal file is never touched.
**Pristine baseline green:** YES (0 failing assertions)
**Mutation produced a unique red (shared-panel-wiring only):** YES

## Mutated-copy failing assertions
- [en] shared-panel-wiring: 1 control(s) missing aria-controls="r3-receipt": [{'marker': '02', 'cls': 'r3-rcpt r3-rcpt--named', 'ariaControls': None}]
- [zh] shared-panel-wiring: 1 control(s) missing aria-controls="r3-receipt": [{'marker': '02', 'cls': 'r3-rcpt r3-rcpt--named', 'ariaControls': None}]
