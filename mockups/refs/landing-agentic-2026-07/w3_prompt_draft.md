# W3 draft (finalize after W2 audit)

WAVE 3 — Story bands: Special situations, 13F funds, Beyond, Mastermind AI, Pricing polish, Closing band + footer polish. Fully pinned spec.

Worktree: (same). W1+W2 foundations in place — reuse utilities.

READ: DIRECTION.md §6.4 (sits+funds), §6.5 (beyond), §6.6 (AI stage window + SCRIPTED DEMO tag EN/ZH), §6.7 (pricing visual-only; matrix DOM pinned), §6.8 (cband dark curtain + arcs; footer CSS only), §5, §7, §9. Refs: attio-09/11/12/14.png (dark band language, footer), ours-en-03/06/08.png (before).

SCOPE:
- #f-sits + #f-funds + #f-beyond: §6.4/6.5 treatment (same as W2's rotations/filings pattern — match it exactly for consistency; read W2's diff first).
- #ai: §6.6 stage window (top bar, three decorative dots, title, .mk SCRIPTED DEMO tag with data-zh 「脚本演示」), receipt chips, capability chips hover. Chat script JS untouched; caret keeps blinking.
- #pricing: §6.7 — tier card anatomy, Pro featured treatment (1px --blue + --sh-float), founding meter restyle (track --hair-weak, blue fill; mechanics untouched), matrix VISUAL polish only (group headers .mk blue, row hover #fafbfc) — DOM/rows/labels byte-pinned by tests/test_onboard_compare_matrix.py; applyPricing() substrings pinned.
- .cband + footer: §6.8 — dark curtain + arcs, benefit pill anatomy, footer .mk column labels + hover; footer anchor set byte-pinned (test_public_chrome).
- ZH parity everywhere; responsive check at 390.

CONTRACTS: same list; plus do not touch hero/terminal/belt/rotations/filings beyond shared-utility consumption.

WORKFLOW: as W2; shots to shots/w3/; commit "landing W3: story bands — sits/funds/beyond, AI stage, pricing polish, closing"; NO push/PR.

REPORT: same format.
