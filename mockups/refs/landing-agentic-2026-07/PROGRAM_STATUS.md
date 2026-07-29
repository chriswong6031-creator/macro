# Program status — 2026-07-29

W1 (foundation+hero, identity preserved) ✓ · W2 (proof bands) ✓ · W3 (story bands) ✓ —
all audited, contracts green, shipped via PR #3962.

**W4 (motion & consistency sweep) ✓ EXECUTED** — commits 42759337603 + 320eb723def
(+ 1af4e131e22 falsifier-vocabulary adjudication), audited by the commissioning session,
shipped as the follow-up PR stacked on #3962. Delivered: one h2 system
`clamp(30px,3.2vw,42px)/800/-.018em` (ceiling measured DOWN from the sheet's 48 —
"Bitcoin. Gold. The dollar." wraps at 46px; floor 30 keeps 390 wrap-free), hover +
focus-visible on every interactive element (46-stop keyboard walk, `--focus:#6ea8ff`
on dark bands), .rv-rule retired + all 7 interior seams on .bandrule, receipts verified
mono, seven interior bands unified on clamp(96px,11vw,148px), one lede trim
(beyond, 119→88 chars, zh twin), landing.css 106,930 B (ceiling 110,000).

**Bug found & fixed in-wave:** `*{animation:none!important}` does NOT match
`::before/::after` — both motion-kill blocks (reduced-motion + .still) were leaking
`ping` (live pill) and `mtPulse` (AI dots). Kill blocks now enumerate pseudos;
getAnimations() = 0 under both gates.

**Adjudication (commissioning session):** the AI demo tool-line `checking falsifiers /
核对反证` was the landing's last front-facing falsifier-family string (#3821 ruling:
that vocabulary never ships front-facing). Swapped to `checking tripwires / 核对警戒线` —
the register the demo's own answer already uses. Flagged for operator review in the PR.

**Deviations accepted:** h2 scale 30-42 (not 32-48; measured, de-inflating), .ai-wrap
.74/1.26 → .92/1.08 (fixes pre-existing orphan wrap; joins the house 42-46% proportion).

**W5 candidates (deliberately left):** .mk size-ramp consolidation (~20 inline recipes →
.mk-9/10/11, wants its own verification pass), editorial restructure of the three 3-line
ledes (filings/funds/AI — each trim costs a fact), 390 headroom on ai/pricing heads
(~11px slack at the 30px floor).

Playwright note: host-flaky launches — retry loop, foreground only; channel="chrome".
