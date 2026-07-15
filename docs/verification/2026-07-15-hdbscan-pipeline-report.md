# HDBSCAN 聚合端到端验证报告

- 内容分析运行 ID：6
- 聚合运行 ID：8
- 输入文章数：9
- 噪声/延迟分配数：6

## 内容分析输入

| 文章 ID | 平台 | 标题 | BGE 维度 | TF-IDF 维度 |
|---:|---|---|---:|---:|
| 61 | news_people | 剑桥中英人工智能商业论坛探讨人工智能发展新机遇 | 512 | 5000 |
| 62 | news_people | 加强人工智能全栈生态建设 推动人工智能产业高质量发展 | 512 | 5000 |
| 63 | news_people | 2026世界人工智能大会暨人工智能全球治理高级别会议整体情况 | 512 | 5000 |
| 65 | news_people | 在北京,看见人工智能 | 512 | 5000 |
| 69 | news_36kr | 36氪首发 \| 浙大系桌面CNC团队获商汤国香、首形科技等近亿元天使轮,要用AI技术降低制造门槛 | 512 | 5000 |
| 70 | news_36kr | 36氪首发 \| 前博世自动驾驶算法工程师创业,用合成数据做触觉大模型 | 512 | 5000 |
| 71 | news_thepaper | 开盘暴跌22%!IBM警告业绩不及预期,AI基建热潮抢占企业软件支出预算 | 512 | 5000 |
| 73 | news_infoq | Claude Artifacts 一夜打通“全网公开分享+多人编辑”,AI 交付闭环彻底杀疯了 | 512 | 5000 |
| 79 | news_sspai | 你这图「保真」吗?AI 生图时代的信息防伪 | 512 | 5000 |

## 簇分配输出

| 文章 ID | 簇 | 动作 | 判断理由 |
|---:|---:|---|---|
| 61 | 0 | attach | ["HDBSCAN_CLUSTER"] |
| 62 | 0 | attach | ["HDBSCAN_CLUSTER"] |
| 63 | 0 | attach | ["HDBSCAN_CLUSTER"] |
| 65 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |
| 69 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |
| 70 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |
| 71 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |
| 73 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |
| 79 | 0 | soft_attach | ["HDBSCAN_NOISE_SOFT_ATTACH"] |

## 运行警告与回退

- HDBSCAN: 1 clusters, 6 noise points
