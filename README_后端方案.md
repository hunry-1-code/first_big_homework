# 网络舆情事件智能分析系统后端方案

## 1. 项目定位

本项目面向突发公共事件、社会热点话题和网络舆情信息，设计一个能够采集、清洗、分析、聚合、预测并生成报告的舆情事件智能分析系统。

系统目标不是实现“全网实时、全平台、绝对准确”的商业级舆情平台，而是完成一个课程项目可落地的原型系统：通过有限但可扩展的数据源，形成从数据采集到事件分析、风险评估、传播路径展示和智能问答的完整闭环。

## 2. 功能范围

### 2.1 前端最低功能对应的后端支持

| 前端功能 | 后端支持 |
| --- | --- |
| 登录 | 用户账号、密码校验、JWT 登录态 |
| 系统首页 | 返回概览指标、热点事件数量、风险事件数量、采集状态 |
| 舆情事件看板 | 事件列表、热度指数、情感比例、按时间/热度排序 |
| 事件详情分析报告 | 事件概述、时间线、趋势、情感、平台分布、关键词、风险等级 |
| 可视化图表 | 返回 ECharts 可直接渲染的数据结构 |
| 智能问答 | 基于当前事件文档和分析报告的 RAG 问答 |
| 个人中心 | 用户关注平台、关键词、领域配置 |

### 2.2 后端基础功能

1. 网络爬虫  
   对新闻网站、RSS、微博/贴吧等公开数据源进行采集，保留多平台扩展接口。

2. 数据清洗及预处理  
   完成正文抽取、字段标准化、噪声过滤、URL 规范化、去重和发布时间标准化。

3. 内容分析  
   实现正文提取、中文分词、关键词提取、实体识别和文本向量化。

4. 热点事件发现  
   基于时间窗口、报道数量、增长率、平台扩散数和互动量计算热度指数，识别热点事件。

5. 舆情事件聚合  
   通过文本向量相似度、关键词重合度、实体重合度和时间窗口，将同一事件的多篇报道聚合为一个事件。

6. 情感倾向分析  
   对事件相关文本计算正面、负面、中立比例，并记录情感关键词。

7. 事件舆情预测  
   根据报道量时间序列和增长趋势，判断事件生命周期阶段：潜伏期、成长期、高潮期、衰退期。

### 2.3 高级功能

1. 虚假文本检测  
   本项目定位为“虚假/可疑信息风险评估”，不直接宣称绝对判定真伪。系统综合来源可信度、多源一致性、官方回应状态、文本煽动性特征和模型概率，给出可疑风险分数和置信度。

2. 事件溯源与关键传播路径  
   构建传播节点和传播边，识别最早发布节点、首次高影响力账号传播、首次官方媒体介入和关键传播路径。

3. 创新设计  
   支持自动生成结构化舆情分析报告，并通过大模型对当前事件进行基于证据的问答。

## 3. 技术栈

### 3.1 推荐落地技术栈

| 类型 | 技术 |
| --- | --- |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL |
| 缓存/队列 | Redis |
| 异步任务 | Celery 或 RQ |
| 向量检索 | pgvector |
| 爬虫 | Scrapy、requests、Playwright |
| 正文抽取 | trafilatura、readability-lxml、BeautifulSoup |
| 中文分词 | jieba |
| 情感分析 | SnowNLP 或中文 RoBERTa 情感模型 |
| 文本向量 | sentence-transformers、bge-small-zh、text2vec |
| 大模型问答 | OpenAI/DeepSeek/通义等 API，可配置 |
| 部署 | Docker Compose |

### 3.2 暂不强制引入的技术

以下技术适合增强版，但第一版不建议强制使用：

- Elasticsearch / OpenSearch
- Neo4j
- MinIO
- Prophet / LSTM
- 完整微服务架构

原因是课程项目工期有限，第一版优先保证核心流程可运行。

## 4. 总体架构

```text
前端页面
  |
  v
FastAPI API 服务
  |
  +-- 用户认证与权限
  +-- 事件看板 API
  +-- 分析报告 API
  +-- 智能问答 API
  +-- 个人中心 API
  |
  v
任务调度与异步队列
  |
  +-- 爬虫任务
  +-- 清洗任务
  +-- NLP 分析任务
  +-- 事件聚合任务
  +-- 风险评估任务
  +-- 报告生成任务
  |
  v
数据存储
  |
  +-- PostgreSQL: 业务数据、事件、报告
  +-- pgvector: 文本向量和相似检索
  +-- Redis: 缓存、任务队列、限流状态
```

## 5. 数据处理流程

```text
用户配置关键词/平台
  -> 生成采集任务
  -> 爬虫采集原始数据
  -> 原始数据入库
  -> 正文提取和字段标准化
  -> 去重和噪声过滤
  -> 分词、关键词、实体识别、向量化
  -> 热点事件发现
  -> 事件聚合
  -> 情感分析
  -> 生命周期预测
  -> 虚假风险评估
  -> 传播路径生成
  -> 分析报告生成
  -> 前端展示和智能问答
```

## 6. 后端模块设计

### 6.1 用户与权限模块

职责：

- 用户注册、登录、退出
- JWT Token 签发和校验
- 用户个人配置管理
- 按用户配置过滤事件和数据源

核心接口：

```text
POST /api/auth/login
GET  /api/users/me
GET  /api/users/me/preferences
PUT  /api/users/me/preferences
```

### 6.2 数据源与爬虫模块

职责：

- 管理用户关注的平台和关键词
- 调度新闻、RSS、微博/贴吧等采集任务
- 记录采集状态、失败原因和增量游标
- 对不同平台做字段适配

建议第一版支持：

```text
新闻网站/RSS
微博或贴吧
本地样例数据导入
```

多平台爬虫统一输出 `RawDocument`：

```json
{
  "platform": "weibo",
  "source_url": "https://example.com/post/1",
  "title": "事件标题",
  "content": "原始正文",
  "author": "发布者",
  "publish_time": "2026-07-06T10:00:00",
  "like_count": 0,
  "comment_count": 0,
  "repost_count": 0
}
```

合规与反爬策略：

- 只采集公开数据
- 配置请求频率和最大页数
- 支持失败重试和任务暂停
- 尊重 robots 和平台规则
- 不绕过验证码
- 登录态平台只支持用户授权 Cookie 导入

### 6.3 清洗与预处理模块

职责：

- HTML 正文提取
- 去广告、去导航、去空白
- URL 规范化
- 发布时间标准化
- 文档级去重
- 平台字段统一

去重策略：

```text
第一层：source_url hash
第二层：title + content SimHash
第三层：正文 embedding 相似度
```

### 6.4 NLP 内容分析模块

职责：

- 中文分词
- 关键词提取
- 命名实体识别
- 文本向量化
- 主题分类

推荐实现：

```text
关键词：TF-IDF + TextRank
分词：jieba
向量化：bge-small-zh 或 text2vec
主题分类：SVM / 朴素贝叶斯 / BERT 分类器
情感分析：SnowNLP 起步，中文 RoBERTa 增强
```

### 6.5 热点事件发现模块

职责：

- 按时间窗口统计报道数量
- 计算热度指数
- 发现新热点事件
- 触发事件聚合任务

热度指数建议：

```text
hot_score =
  0.30 * 报道数量增长率
+ 0.25 * 报道总量
+ 0.20 * 点赞/评论/转发量
+ 0.15 * 平台扩散数量
+ 0.10 * 负面情绪比例
```

### 6.6 事件聚合与相似检索模块

职责：

- 将相似报道聚合为同一事件
- 支持历史相似事件检索
- 维护事件和文档之间的关联关系

聚合依据：

```text
文本向量相似度
标题关键词重合度
人物/地点/机构实体重合度
发布时间窗口
平台来源差异
```

聚合逻辑：

```text
如果新文档与已有事件相似度 >= 阈值：
    并入已有事件
否则：
    创建新事件
```

### 6.7 情感分析模块

职责：

- 对单篇文档计算情感倾向
- 对事件整体统计正面、负面、中立比例
- 提取负面高频词

输出示例：

```json
{
  "positive_ratio": 0.18,
  "neutral_ratio": 0.47,
  "negative_ratio": 0.35,
  "sentiment_score": -0.22,
  "negative_keywords": ["质疑", "投诉", "风险"]
}
```

### 6.8 生命周期预测模块

职责：

- 生成事件报道量时间序列
- 预测舆情阶段
- 给出趋势解释

四阶段判断：

| 阶段 | 判断依据 |
| --- | --- |
| 潜伏期 | 报道量低，增长缓慢 |
| 成长期 | 报道量连续上升，增长率较高 |
| 高潮期 | 报道量处于高位，增长放缓 |
| 衰退期 | 报道量连续下降，热度下降 |

建议使用滑动窗口，避免单个时间点波动造成误判。

### 6.9 虚假/可疑信息风险评估模块

职责：

- 给出文本可疑风险分数
- 给出置信度
- 给出可解释原因

评分依据：

```text
来源可信度
是否有多源交叉验证
是否有官方媒体或权威机构回应
是否存在夸张煽动性表达
是否与已有权威报道存在语义冲突
谣言检测模型输出概率
```

输出示例：

```json
{
  "fake_probability": 0.67,
  "confidence": 0.74,
  "reasons": [
    "来源可信度较低",
    "缺少权威媒体交叉验证",
    "标题存在明显煽动性表达"
  ]
}
```

### 6.10 传播溯源与路径分析模块

职责：

- 构建传播节点和传播边
- 识别最早发布节点
- 识别首次高影响力账号传播
- 识别首次官方媒体介入
- 生成传播路径图数据

节点类型：

```text
文章
账号
平台
媒体
事件
```

边类型：

```text
转发
评论
引用
回复
时间先后关系
内容相似关系
```

强关系来自转发、评论、引用；弱关系来自发布时间先后和内容相似度。新闻网站无法获取真实转发链时，使用弱关系推断传播路径，并在报告中标注为推断关系。

### 6.11 分析报告与智能问答模块

职责：

- 生成事件结构化分析报告
- 支持用户围绕当前事件提问
- 问答必须基于当前事件材料，不允许脱离证据自由发挥

RAG 流程：

```text
用户问题
  -> 检索当前事件相关文档、报告、时间线、传播节点
  -> 构造提示词
  -> 调用大模型
  -> 返回答案和引用依据
```

大模型不可用时，返回基于检索结果的摘要，保证系统仍可演示。

## 7. 数据库表设计

建议核心表：

```text
users                       用户表
user_preferences            用户关注关键词、平台、领域
source_configs              数据源配置
crawl_tasks                 采集任务
raw_documents               原始采集数据
clean_documents             清洗后的文档
document_features           分词、关键词、实体、向量
events                      聚合后的舆情事件
event_documents             事件和文档关联表
event_metrics               事件统计指标
event_time_series           事件时序趋势
sentiment_results           情感分析结果
risk_assessments            风险等级和风险原因
fake_detection_results      虚假/可疑信息评估
propagation_nodes           传播图节点
propagation_edges           传播图边
analysis_reports            分析报告
qa_sessions                 智能问答会话
qa_messages                 智能问答消息
```

## 8. API 设计

### 8.1 认证与用户

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/users/me
GET  /api/users/me/preferences
PUT  /api/users/me/preferences
```

### 8.2 数据源与采集任务

```text
GET  /api/sources
POST /api/sources
PUT  /api/sources/{source_id}
POST /api/crawl-tasks
GET  /api/crawl-tasks/{task_id}
GET  /api/crawl-tasks
```

### 8.3 舆情事件

```text
GET /api/events
GET /api/events/{event_id}
GET /api/search/events
GET /api/events/{event_id}/similar
```

事件列表支持：

```text
sort_by=time|hot_score|risk_score
order=asc|desc
keyword=...
platform=...
risk_level=...
```

### 8.4 分析图表

```text
GET /api/events/{event_id}/trend
GET /api/events/{event_id}/sentiment
GET /api/events/{event_id}/platforms
GET /api/events/{event_id}/keywords
GET /api/events/{event_id}/propagation
GET /api/events/{event_id}/risk
```

### 8.5 报告与问答

```text
GET  /api/events/{event_id}/report
POST /api/events/{event_id}/report/regenerate
POST /api/events/{event_id}/qa
GET  /api/events/{event_id}/qa/sessions
```

## 9. 风险等级设计

风险等级由多因素综合计算：

```text
risk_score =
  0.25 * 负面情绪比例
+ 0.20 * 传播速度
+ 0.15 * 平台扩散数量
+ 0.15 * 虚假/可疑信息概率
+ 0.15 * 敏感关键词命中
+ 0.10 * 官方媒体介入状态
```

等级划分：

```text
0 - 30    低风险
31 - 60   中风险
61 - 80   高风险
81 - 100  严重风险
```

风险评估必须保存可解释原因，例如：

```text
负面情绪比例较高
传播速度明显上升
疑似虚假信息概率较高
多个平台同时扩散
官方尚未回应
```

## 10. 异常与降级方案

| 异常场景 | 处理方案 |
| --- | --- |
| 爬虫失败 | 记录失败原因，任务状态设为 failed，支持重试 |
| 反爬限制 | 降低频率，暂停该数据源，保留已有数据 |
| 正文抽取失败 | 使用标题、摘要和原始片段兜底 |
| NLP 模型超时 | 使用规则模型或缓存结果 |
| 大模型问答超时 | 返回检索摘要和“模型暂不可用”提示 |
| 无热点事件 | 返回空列表和推荐关键词 |
| 数据重复 | URL hash、SimHash、向量相似度多层去重 |
| 平台字段缺失 | 允许字段为空，但保留平台原始 JSON |

## 11. 项目目录建议

```text
opinion-analysis-system/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  ├─ crawlers/
│  │  ├─ tasks/
│  │  └─ main.py
│  ├─ tests/
│  ├─ alembic/
│  └─ pyproject.toml
├─ frontend/
├─ docs/
├─ data_samples/
├─ docker-compose.yml
├─ .env.example
├─ .gitignore
└─ README.md
```

## 12. 5 人小组分工

| 成员 | 负责模块 |
| --- | --- |
| 成员 1 | 爬虫、数据源配置、任务调度 |
| 成员 2 | 数据库、清洗、去重、正文提取 |
| 成员 3 | NLP、情感分析、关键词、事件聚合、生命周期预测 |
| 成员 4 | FastAPI、登录权限、报告生成、智能问答接口 |
| 成员 5 | 前端看板、图表、个人中心、接口联调 |

## 13. 开发顺序

建议按以下顺序实现：

1. 初始化 Git 仓库和项目目录。
2. 搭建 FastAPI、PostgreSQL、Redis 基础环境。
3. 实现用户登录和个人配置。
4. 实现数据源配置和采集任务。
5. 实现原始数据入库和清洗流程。
6. 实现关键词、分词、情感分析。
7. 实现事件发现和事件聚合。
8. 实现热度指数和风险评分。
9. 实现生命周期预测。
10. 实现虚假/可疑信息风险评估。
11. 实现传播路径节点和边。
12. 实现报告生成和智能问答。
13. 联调前端可视化。
14. 准备样例数据、演示脚本和答辩材料。

## 14. 可行性边界

本方案可以覆盖课程要求的基本功能和高级功能，但需要明确以下边界：

- 第一版不承诺所有主流平台都稳定采集。
- 虚假文本检测输出的是风险评估，不是司法或事实层面的最终真伪判断。
- 新闻网站传播路径多为基于时间和内容相似度的推断关系。
- 生命周期预测以规则和简单趋势模型为主，不承诺高精度预测。
- 大模型问答必须基于系统内已采集材料，不能脱离证据回答。

## 15. 参考项目

本方案参考了以下开源项目的设计思路，但不照搬代码：

- NanmiCoder/MediaCrawler：多平台采集适配器思路
- 666ghj/BettaFish：智能舆情分析、报告生成和问答思路
- stay-leave/weibo-public-opinion-analysis：微博主题分析、情感分析和热度分析思路
- Astianjy/Weibo_PublicOpinion_AnalysisSystem：完整舆情分析系统功能拆分
- froginwe11/campus_sentiment_analysis_share：课程项目形态和可视化展示思路
- dataabc/weiboSpider：微博采集字段设计
- 666ghj/MindSpider：面向舆情分析的 AI 爬虫流程
