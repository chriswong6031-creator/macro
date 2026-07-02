# qbus audit report
**generated:** 2026-07-02T11:50:41.831220+00:00  
**lookback:** 30d  
**bus size:** 1404 items  

## (a) Echo — top events by cross-desk corroboration
Items in window: 1396  Unique event_keys: 1261  Multi-desk (top 20): 0

| event_key | n_items | n_sources | n_desks | desks | sample_title |
|-----------|---------|-----------|---------|-------|--------------|
| `ev_1e4c7e3…` | 3 | 3 | 1 | china_news_intel | 字节跳动发布豆包大模型2.1 Pro |
| `ev_45d0279…` | 3 | 3 | 1 | china_news_intel | 约旦外长：应立即制止以色列各种非法行径 |
| `ev_496d62b…` | 3 | 3 | 1 | china_news_intel | 中国-上海合作组织科技创新合作大会在青岛举行 |
| `ev_5574507…` | 3 | 3 | 1 | china_news_intel | 中信证券：算力、电力相关产业链具备中长期配置价值 |
| `ev_5ea3e91…` | 3 | 3 | 1 | china_news_intel | 伊朗称将适时启动伊美最终协议谈判 |
| `ev_62f711e…` | 3 | 3 | 1 | china_news_intel | 卓越睿新：与阿里云签署全面深度合作框架协议 |
| `ev_6532a97…` | 3 | 3 | 1 | china_news_intel | 惠康科技：公司目前对欧洲市场的销售占整体营收比例较低，对公司业绩贡献有限 |
| `ev_8166339…` | 3 | 3 | 1 | china_news_intel | 国家外汇管理局局长朱鹤新会见花旗集团董事会主席兼首席执行官范洁恩 |
| `ev_84a8ba4…` | 3 | 3 | 1 | china_news_intel | 中国信通院启动“算力Token出海生态计划” |
| `ev_8af7b77…` | 3 | 3 | 1 | china_news_intel | 国家能源局：“十五五”时期将重点围绕三个方向 进一步加快布局建设新型能源基础设施 |

## (b) Novelty distribution
Insufficient data: insufficient history for novelty_z

## (c) Per-desk mix
Total items: 1396  Desks: 3

| desk | n_items | n_unique_events | timestamp_quality |
|------|---------|-----------------|-------------------|
| china_news_intel | 930 | 795 | SNAPSHOT_DATE:920, CRAWL_BOUNDED:10 |
| financial_news | 406 | 406 | PUBLISHER_STATED:404, CRAWL_BOUNDED:2 |
| news_vector | 60 | 60 | CRAWL_BOUNDED:60 |

## (d) Duplicate rate
Raw items: 1396  Unique events: 1261  Ratio: 1.11×  Multi-source events: 116
