# B2-12 thin_reliability_audit.py — mutation proof
Mutation target: `L('Low confidence', '低置信度')` — the ONLY occurrence in the built candidate — restored to the withdrawn `Thin data \u2014 read with caution / 数据稀疏 \u2014 请谨慎解读` chip label. Applied to an in-memory COPY inside a throwaway temp directory; the real proposal file is never touched.
**Pristine baseline green:** YES (0 failing assertions)
**Mutation produced a unique red (chip-name / thin-word-collision only, zero coverage-sentence collateral):** YES

## Mutated-copy failing assertions
- [en] chip-name: bad values ['Thin data — read with caution', 'Thin data — read with caution', 'Thin data — read with caution', 'Thin data — read with caution', 'Thin data — read with caution'], want all 'Low confidence' (5 chips)
- [en] thin-word-collision: 'thin' painted OUTSIDE the coverage sentence: [('Thin data — read with caution', 'l-en'), ('Thin data — read with caution', 'l-en'), ('Thin data — read with caution', 'l-en'), ('Thin data — read with caution', 'l-en'), ('Thin data — read with caution', 'l-en')]
- [zh] chip-name: bad values ['数据稀疏 — 请谨慎解读', '数据稀疏 — 请谨慎解读', '数据稀疏 — 请谨慎解读', '数据稀疏 — 请谨慎解读', '数据稀疏 — 请谨慎解读'], want all '低置信度' (5 chips)
- [zh] thin-word-collision: '稀疏' painted OUTSIDE the coverage sentence: [('数据稀疏 — 请谨慎解读', 'l-zh'), ('数据稀疏 — 请谨慎解读', 'l-zh'), ('数据稀疏 — 请谨慎解读', 'l-zh'), ('数据稀疏 — 请谨慎解读', 'l-zh'), ('数据稀疏 — 请谨慎解读', 'l-zh')]
