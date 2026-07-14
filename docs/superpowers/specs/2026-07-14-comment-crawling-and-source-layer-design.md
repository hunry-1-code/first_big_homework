# 评论采集与信源分层设计

日期：2026-07-14

状态：待用户审阅

## 1. 目标

为知乎、微博、抖音和 B 站增加正文之外的评论/回复采集能力，并将评论纳入公众意见分析，同时避免评论污染文章数量、事件聚类和正式事件生成。

系统同时增加信源分析层，用于区分机构/媒体叙事与公众叙事。机构侧没有样本时，系统只输出公众内部的情感、观点、诉求和分歧，不计算机构—公众叙事张力，也不把“未采集到”解释为“官方沉默”。

## 2. 设计原则

1. 评论是文章、回答、微博、视频或专栏的子内容，不是独立报道。
2. 评论共享标准化、清洗、质量和情感分析能力，但不进入事件聚类主输入。
3. 评论采集失败不影响正文入库和其他平台任务。
4. `source_type` 保留现有内容形态语义，新增分析层字段，不破坏旧数据。
5. 分析结果必须带样本量、覆盖状态和降级原因。
6. 不绕过验证码、登录验证或平台访问控制，只使用公开或已授权的低频接口。

## 3. 数据模型

### 3.1 Comment

新增 `comment` 表，核心字段包括：

- `id`、`article_id`、`platform`
- `source_comment_id`：平台评论 ID，与平台组成唯一键
- `parent_comment_id`、`root_comment_id`、`depth`
- `content`、`clean_content`、`clean_status`、`clean_error`
- `author`、`author_id`、`author_verified`
- `publish_time`
- `likes_count`、`replies_count`
- `raw_json`、`content_hash`
- `source_layer`、`source_role`
- `sentiment_label`、`sentiment_score`、`sentiment_confidence`
- `sentiment_dimension`、`sentiment_target`、`sentiment_reason`
- `analysis_status`、`analysis_version`
- `created_at`、`updated_at`

平台和 `source_comment_id` 建立唯一约束；父评论不存在时允许为空。评论只通过 `article_id` 关联到已采集文章，不直接关联正式事件，事件归属通过文章反向获得。

### 3.2 Article 扩展

保留现有 `source_type`，新增：

- `source_layer`：`institutional`、`media`、`public`、`unknown`
- `source_role`：如 `government_statement`、`official_media`、`professional_media`、`public_post`、`comment`

默认映射只作为初始值，不能仅按平台名称判断。官方微博属于机构层，普通微博帖子属于公众层；媒体报道需要结合作者、来源和内容类型判断。无法判断时使用 `unknown`。

## 4. 采集契约

在现有 `RawDocument` 之外增加评论内部契约 `RawComment`，至少包含：

```text
platform
article_id/source_article_id
source_comment_id
parent_comment_id/root_comment_id
content
author/author_id
publish_time
likes_count/replies_count
raw_json
```

正文采集器返回文章；评论采集器根据正文中的平台内容 ID 执行二阶段采集。评论分页、数量上限和回复深度由任务配置控制。

默认策略：每篇内容最多 50 条一级评论，最多 20 条高互动子评论；同时兼顾热门评论和最新评论。评论/弹幕不计入原始文章 `target_count`。

## 5. 平台适配

### 5.1 知乎

使用 TikHub 的回答评论接口获取一级评论，使用子评论接口补充回复。必须保存 `answer_id`，并区分回答、专栏和想法等内容类型。当前官方搜索适配器只返回评论数量，新增评论阶段不改变其正文搜索职责。

### 5.2 微博

使用 TikHub 的微博评论和评论回复接口。搜索结果中的微博 ID 作为 `source_article_id`；分页游标和热门/最新排序状态写入任务诊断，不写入业务正文。

### 5.3 抖音

使用 TikHub 视频评论和评论回复接口。抖音搜索当前存在 403/权限不稳定问题，正文成功而评论失败时保留正文并标记 `comment_fetch_status=blocked`。

### 5.4 B 站

不依赖 TikHub。扩展现有 B 站采集器支持视频搜索和专栏搜索：

- 视频：标题、简介、UP 主、发布时间、互动数据、可用字幕。
- 专栏：标题、正文和互动数据。
- 评论：公开评论接口和回复接口。
- 弹幕：作为独立 `content_kind=danmaku` 子内容，单独限量，不与评论数量混算。

公开接口限流、登录态或内容不可见时，记录稳定错误码并继续处理其他内容。

## 6. 分析流程

```text
正文采集
→ 正文入库和预处理
→ 文章进入内容分析与事件聚类
→ 正式事件确定后
→ 采集关联文章评论
→ 评论共享清洗、质量、分词和情感流程
→ 生成公众意见快照
```

评论不进入 `AggregationRun` 的文章聚类集合，不增加 `independent_report_count`。评论分析结果汇总到事件级公众快照：

- 情感和情绪强度分布
- 观点/诉求主题
- 支持、质疑、反对等立场
- 平台差异
- 高互动意见
- 评论样本量、覆盖平台和失败原因

评论的默认情感维度偏向 `stance`，但由模型根据文本判断，不强制把公众内容判定为负面；机构内容默认关注 `factual`、`impact` 或 `stance`，同样需要模型给出实际维度。

## 7. 叙事张力与缺失降级

事件输出新增结构化字段：

```text
institutional_status: present / not_observed / insufficient
public_status: present / insufficient
narrative_gap_status: comparable / authority_not_observed / insufficient
narrative_gap_score: nullable
institutional_summary: nullable
public_summary: nullable
dispute_topics: []
public_demands: []
limitations: []
```

只有机构层和公众层都达到最低样本量时才计算张力。机构层缺失时：

- 不计算 `narrative_gap_score`。
- 正常输出公众内部观点、情感、诉求和平台分歧。
- 使用“当前采集范围内未发现机构侧样本”，不使用“官方沉默”。

## 8. 配置

在 `backend/.env` 和 `.env.example` 中增加空配置及限制项：

```dotenv
TIKHUB_ZHIHU_API_KEY=
TIKHUB_WEIBO_API_KEY=
TIKHUB_DOUYIN_API_KEY=
COMMENT_COLLECTION_ENABLED=true
COMMENT_MAX_PER_ARTICLE=50
COMMENT_REPLY_LIMIT=20
DANMAKU_COLLECTION_ENABLED=true
DANMAKU_MAX_PER_VIDEO=100
```

真实密钥只由用户填写，不写入 Git、测试证据或日志。

## 9. 失败与安全

- 每个平台、每篇正文、每个评论分页独立记录错误。
- 评论接口 401/403/429、空响应、解析错误均转换为稳定错误码。
- 原始评论 JSON 做敏感字段脱敏，不能保存 Authorization、Cookie 或 API Key。
- 评论内容按平台 ID 和内容哈希去重，重复采集只更新互动快照。
- 任务幂等键包含文章 ID、平台、评论配置版本和采集窗口。

## 10. 测试验收

### 单元和适配器测试

- 四个平台评论字段映射、分页和父子关系。
- B 站视频、专栏、评论、回复和弹幕解析。
- 空评论、403、429、部分平台失败的降级。
- 评论去重和重复任务复用。

### 分析测试

- 评论不进入文章聚类和文章计数。
- 评论情感和关键词进入公众快照。
- 机构层缺失时张力分数为空，但公众分析仍成功。
- 机构和公众样本充足时生成可解释的张力证据。

### 回归测试

- 既有正文采集、预处理、聚类、情感和事件详情测试全部保持通过。
- `backend/.env` 中只出现空占位配置，不输出密钥。

## 11. 非目标

- 第一版不保证所有平台长期稳定可用。
- 不把评论或弹幕当成独立事件报道。
- 不用情感差异直接裁定事实真假。
- 不把未抓到机构信息等同于官方没有回应。
- 不在本阶段实现复杂用户画像或评论者关系图。
