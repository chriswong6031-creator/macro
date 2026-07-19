# Bilingual (EN ↔ 中文) glossary

Canonical Chinese translations for the dashboard's recurring terms. Use these
verbatim everywhere (templates, `engine/*.py` display dicts, build scripts) so the
Chinese interface reads consistently. **Tickers and individual company/stock names
stay English** (per user). RSI / MACD / StochRSI / ETF / OAS kept as-is.

## Color convention note
In Chinese mode the green/red price convention inverts: **红 = 上涨/看多 (up/bullish)**,
**绿 = 下跌/看空 (down/bearish)**. Quadrant green/red pair flips (Goldilocks→red,
Stagflation→green). Status colors (data health "ok", warnings, danger/alerts) are
NOT price-direction and are left as-is.

## Regimes / quadrants
| EN | 中文 |
|---|---|
| Goldilocks | 理想增长（金发女孩） |
| Reflation | 再通胀 |
| Stagflation | 滞胀 |
| Growth scare / Deflation | 增长恐慌／通缩 |
| Macro Regime Dashboard | 宏观周期仪表盘 |
| regime | 周期／状态 |
| growth | 增长 |
| inflation | 通胀 |
| transition radar | 转换雷达 |
| STABLE / WEAKENING / TRANSITIONING / NEW REGIME | 稳定／走弱／转换中／新周期 |
| signal agreement | 信号一致度 |
| Fed liquidity | 美联储流动性 |
| expanding / neutral / contracting | 扩张／中性／收缩 |
| business-cycle: early / mid / late | 商业周期：早期／中期／晚期 |

## Cycle ladder (state → action)
| EN label · action | 中文 标签 · 操作 |
|---|---|
| DOWNTREND · AVOID | 下跌趋势 · 回避 |
| NEARING A LOW · GET READY | 接近低点 · 准备 |
| BOTTOMING · BUY SETUP | 筑底中 · 买入预备 |
| BUY ZONE · BUY | 买入区 · 买入 |
| UPTREND · HOLD | 上涨趋势 · 持有 |
| NEARING A HIGH · TAKE PROFITS | 接近高点 · 止盈 |
| TOPPING · SELL SETUP | 做顶中 · 卖出预备 |
| UNCONFIRMED TURN · HIGH-RISK · NIMBLE ONLY | 未确认转向 · 高风险 · 仅限灵活操作 |
| TURN IN PROGRESS · WATCH — DON'T CHASE | 转向进行中 · 观察 — 勿追高 |
| LIMITED (new listing, insufficient history) | 历史不足 |
| COUNTER-TREND BOUNCE (legacy log label) | 逆势反弹 |
| daily cycle | 日线周期 |
| weekly (investor) cycle | 周线（投资者）周期 |

## Action board
| EN | 中文 |
|---|---|
| What to act on now | 当前可操作 |
| BUY ZONE — confirmed now | 买入区 — 已确认 |
| SETTING UP — buy soon | 构筑中 — 即将买入 |
| TAKE PROFITS / topping | 止盈／做顶 |
| HOLD / avoid | 持有／回避 |
| BUY NOW / BUY SOON / WATCH / WAIT / HOLD / TAKE PROFITS / SELL · REDUCE / AVOID | 立即买入／即将买入／观察／等待／持有／止盈／卖出·减仓／回避 |

## Posture (exposure dial)
| EN | 中文 |
|---|---|
| AGGRESSIVE | 进取 |
| CONSTRUCTIVE | 偏多 |
| NEUTRAL | 中性 |
| CAREFUL | 谨慎 |
| DEFENSIVE | 防御 |

## Heat board bands
| EN | 中文 |
|---|---|
| OVERHEATED | 过热 |
| HOT | 偏热 |
| NEUTRAL | 中性 |
| COLD | 偏冷 |
| rotation: leading / weakening / improving / lagging | 轮动：领先／走弱／改善／落后 |

## Sectors (category labels — translated; tickers stay English)
| Ticker | EN | 中文 |
|---|---|---|
| XLB | Materials | 原材料 |
| XLC | Communications | 通讯 |
| XLE | Energy | 能源 |
| XLF | Financials | 金融 |
| XLI | Industrials | 工业 |
| XLK | Technology | 科技 |
| XLP | Consumer Staples | 必需消费 |
| XLRE | Real Estate | 房地产 |
| XLU | Utilities | 公用事业 |
| XLV | Health Care | 医疗保健 |
| XLY | Consumer Discretionary | 可选消费 |
| SMH | Semiconductors | 半导体 |
| IWM | Small Caps | 小盘股 |
| RSP | Equal-Weight S&P | 等权标普 |
| QUAL | Quality factor | 质量因子 |
| MTUM | Momentum factor | 动量因子 |
| USMV | Min-vol factor | 低波因子 |
| LQD | IG Corporate Bonds | 投资级公司债 |
| GC=F | Gold | 黄金 |

## Bitcoin Vector
| EN | 中文 |
|---|---|
| Bitcoin Vector | 比特币向量 |
| Market State · Long term | 市场状态 · 长期 |
| BTC Allocation · Optimal strategy | BTC 仓位 · 最优策略 |
| Mid term · Environment | 中期 · 环境 |
| Short term · Scenarios (3 days) | 短期 · 情景（3 天） |
| Risk Index vs Strategy · backtested | 风险指数 vs 策略 · 已回测 |
| Momentum & Structure | 动量与结构 |
| Momentum / Structure Shift | 动量／结构转变 |
| Bitcoin Fundamental Index (BFI) | 比特币基本面指数（BFI） |
| Network Growth | 网络增长 |
| Liquidity | 流动性 |
| Cross-Asset Regime Map | 跨资产周期图 |
| Risk ON / OFF | 风险开启／关闭 |
| High Risk / Low Risk | 高风险／低风险 |
| bull / neutral / bear | 看多／中性／看空 |
| constructive / neutral / broken | 偏多／中性／走坏 |
| positive / negative (BFI zone) | 正向／负向 |
| Defensive / Fragile / Recovery / Expansion | 防御／脆弱／复苏／扩张 |
| Strategic / Tactical | 战略／战术 |
| BTC / ETH / Alts | BTC／ETH／山寨币 |
| Allocation | 仓位 |
| BTC price | BTC 价格 |
| Optimal strategy | 最优策略 |

## Common UI chrome
| EN | 中文 |
|---|---|
| Home | 首页 |
| Macro | 宏观 |
| Dashboard | 仪表盘 |
| Any stock | 任意股票 |
| Daily brief | 每日简报 |
| History & charts | 历史与图表 |
| Stock analyzer | 个股分析 |
| Chart | 图表 |
| Light / Dark | 浅色／深色 |
| data through | 数据截至 |
| Generated … UTC | 生成于 … UTC |
| not investment advice | 非投资建议 |
| Open → | 打开 → |
| None today | 今日无 |
