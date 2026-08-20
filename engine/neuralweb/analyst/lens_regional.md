---
id: lens_regional
kind: lens
version: 1
title: Non-US boards — Hong Kong, mainland China, Canada
priority: 36
triggers:
  - .HK
  - .SS
  - .SZ
  - .TO
  - hong kong
  - hang seng
  - HSI
  - HSCEI
  - HSTECH
  - southbound
  - northbound
  - stock connect
  - HKMA
  - HIBOR
  - a-share
  - a shares
  - china market
  - shanghai
  - shenzhen
  - CSI 300
  - CSI300
  - SSE
  - ChiNext
  - STAR market
  - PBoC
  - LPR
  - canada
  - canadian
  - TSX
  - toronto
  - USDCAD
  - bank of canada
  - 港股
  - 恒生
  - 恒指
  - 南向
  - 北向
  - 港股通
  - A股
  - 沪深
  - 上证
  - 深证
  - 沪深300
  - 创业板
  - 科创板
  - 涨停
  - 央行
  - 加拿大
  - 多伦多
---
NON-US BOARDS LENS — a Hong Kong, A-share or TSX question is not a US question with different tickers. Read the board on its own mechanics, then check what the US tape does to it.

WHICH CLOCK. Each board is stamped with its OWN session (packet REGIONAL block). HK and the mainland close before the US opens; Canada closes with it. A board's nightly artifact is routinely a session behind another's — never carry one board's date onto another, and never describe an Asian close as a reaction to a US session that had not happened yet. When the boards disagree, check the clock before you reach for a story.

HONG KONG. The HKD is pegged in a 7.75–7.85 band, so HK imports US policy rates through HIBOR whatever mainland growth is doing — the classic vise is US rates tightening while earnings sit in China. The packet's peg reading (strong/weak side) is the flow tell: weak-side pressure means capital leaving and the HKMA draining aggregate balance, which tightens HIBOR with a lag. Index composition decides what a move means: HSI is broad, HSCEI is mainland-incorporated H-shares, HSTECH is a concentrated platform/tech book — quoting "Hong Kong" off HSTECH overstates a tech day badly. Southbound Connect is mainland money buying HK; sustained southbound into a falling tape is a different read from a bounce with no flow behind it. Many large HK names have US ADRs, so an HK gap often only prices what New York already did overnight — check before calling it new information.

MAINLAND CHINA. A-shares are retail-heavy and policy-transmitted, so the ordering is inverted from the US: policy and liquidity lead, earnings confirm later. Read PBoC operations, LPR and the credit impulse before fundamentals. Mechanics that have no US analogue and that change what a price means: daily limits (±10% on main-board names — since 2026-07-06 including ST/risk-warning names, which traded ±5% before the 2026 rules revision — ±20% on ChiNext and STAR) mean a limit-locked stock has an unknown clearing price, not a −10% opinion; margin balances and turnover are the participation gauge; state-linked buying can hold an index while breadth underneath is still deteriorating. SSE Composite and CSI 300 are NOT interchangeable — the Composite is a Shanghai all-share, CSI 300 is a large-cap cross-market book; name which one you are quoting. An A/H premium is a fact about two listings of the same company, so it measures capital mobility and sentiment gap, not value.

CANADA. The TSX is a concentrated index: energy, materials and financials dominate, so it usually trades as a commodity-and-rates expression with an equity wrapper. Ask what oil, gold and copper did before you ask what "Canadian stocks" did. Bank of Canada versus Fed divergence drives USDCAD, and USDCAD then decides whether a Canadian investor's US exposure helped or hurt — a flat TSX with a sharply weaker CAD is not a flat year. Many large names are interlisted with New York; a CAD-line move can be pure currency.

WHAT THE DATA CAN AND CANNOT SHOW HERE. Per-name Hong Kong and A-share history carries true intraday highs, lows and volume. The TSX single names, the index series (HSI, SSE Composite, S&P/TSX) and the sector ETFs are CLOSING PRICES ONLY — the chart tool reports this as its bar basis. On those symbols there is no wick, no intraday range and no volume, and gaps cannot be measured at all: the tool says so explicitly rather than returning an empty list. Never describe such a chart as gap-free, never read a candle body as a rejection, and never call volume dry or heavy. Trend, closes, swing structure and levels remain fully readable — say which of the two you are working from when the distinction changes the call.
