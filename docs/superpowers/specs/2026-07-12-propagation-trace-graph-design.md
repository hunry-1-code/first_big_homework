# 事件溯源与关键传播路径图设计

## 1. 目标

重构现有“标题两两相似即连边”的稠密关系网，生成基于当前可观测公开数据的、可解释的稀疏传播有向图，并在事件详情页提供传播关系图和关键阶段时间线。

系统不得宣称完整还原互联网真实传播过程。明确关系与算法推测关系必须在数据和视觉上区分。

## 2. 参考方法

- FakeNewsNet：新闻、社交帖子、转发及用户信息分层保存，传播关系优先使用真实社交参与数据。
- PHEME / TreeLSTM：传播级联组织为以源帖为根的树或森林，而不是全连接相似度图。
- CasFlow：保留级联层级和传播不确定性，推测关系具有置信度。
- 本地《事件溯源与关键传播路径设计草案》：明确关系优先，缺失时使用时间、文本、实体和跨平台证据推断。

第一版不引入图数据库、GNN 或深度级联预测模型，使用当前 SQLAlchemy 数据和确定性规则完成可稳定演示的传播森林。

## 3. 模块结构

新增：

```text
backend/app/propagation/
├── __init__.py
├── result.py      节点、边、阶段和图结果数据类型
├── evidence.py    平台明确关系、来源文本和实体证据提取
├── scorer.py      推测父节点评分
├── phases.py      传播阶段与关键节点识别
└── builder.py     排序、建边、裁剪和图结果编排
```

`event_service.get_propagation_data()` 只负责查询文章、调用构建器和序列化，不再包含核心图算法。

## 4. 输入数据

使用 Article 的以下字段：

- id、event_id、platform、source_article_id、source_url
- title、clean_content、raw_content、raw_json
- author、author_id、author_followers、author_verified、author_type
- publish_time、first_crawled_at
- likes_count、comments_count、reposts_count、views_count
- keywords、tokens 或可获得的文档特征

发布时间优先级：`publish_time` 高于 `first_crawled_at`。两者均缺失时保留节点，但不作为可靠父节点或源头候选。

## 5. 节点

节点代表文章、帖子、视频或媒体报道。每个节点包含：

```text
id / article_id
title / author / platform
publish_time / time_confidence
node_type
importance_score
is_key_node / key_node_reasons
interaction_count
symbol_size / category
```

节点类型：

- origin_candidate
- platform_first
- influencer_amplification
- media_intervention
- official_response
- turning_point
- peak_content
- revival_content
- ordinary

同一节点可具有多个关键原因，但只选择一个主要 node_type 用于前端颜色。

## 6. 明确关系

从 raw_json 和正文中提取：

- retweeted_status、quoted_status、reposted_from、parent_id、root_id
- 原微博、原帖、原视频 ID
- 引用 URL
- “来源：”“转自”“据某媒体”“原文链接”等来源文本

能够匹配到事件内文章时建立明确边：

```text
evidence_type = explicit
confidence = 0.95～1.0
```

明确关系可覆盖单父节点限制；如存在多个明确引用，选择最直接的主边，其余作为 secondary_links 返回但默认不绘制。

## 7. 推测关系

只有没有明确主边时才推测父节点。候选父节点必须满足：

- 时间早于目标节点；或目标时间不可靠但候选具有明确引用证据。
- 属于同一事件。
- 不会产生环。

评分组成：

```text
标题/正文相似度  0.35
实体和关键词重合 0.25
时间接近度       0.20
来源文本证据     0.15
跨平台合理性     0.05
```

第一版实体使用现有关键词、标题词组和简单机构/人名线索，不新增大型 NER 模型。总分低于 0.55 不建边。0.55～0.74 为低/中置信度，0.75 以上为高置信度推测。

每个推测节点最多一条主入边，选择得分最高者。分数接近时优先时间更近、证据类型更多、重要性更高的候选。

## 8. 图结构约束

- 主图是有向无环图，可包含多个源头候选，即传播森林。
- 边始终从较早节点指向较晚节点。
- 不对所有文章两两保留边。
- 默认最多展示 40 个重要节点和 50 条主边。
- 裁剪时必须保留源头候选、平台首发、大V、媒体、官方回应、峰值及连接它们所需的中间节点。
- 数据不足或所有推测分数低于阈值时只返回时间线节点，不强行连边。

## 9. 关键节点和阶段

关键节点识别：

- 当前数据中最早的高质量文章：源头候选。
- 每个平台最早文章：平台首发。
- 非官媒且粉丝数达到 50 万：大V放大候选。
- 官媒名单或媒体类型匹配：媒体介入。
- author_type、标题或正文包含官方回应语义：官方回应。
- 互动量达到事件内高分位：峰值内容。
- 与前一活跃期相隔至少三天后重新活跃：二次传播。

阶段输出：起始、扩散、媒体介入、官方回应、峰值、衰退、二次传播。没有证据的阶段不返回。

## 10. API

继续使用：

```text
GET /api/events/<event_id>/propagation
```

响应：

```json
{
  "code": 200,
  "data": {
    "summary": {
      "node_count": 20,
      "edge_count": 16,
      "explicit_edge_count": 4,
      "inferred_edge_count": 12,
      "origin_candidate_count": 2,
      "platforms": ["微博搜索", "知乎", "B站"],
      "coverage_notice": "仅反映当前已采集公开数据"
    },
    "key_nodes": [],
    "phases": [],
    "graph": {
      "nodes": [],
      "links": [],
      "secondary_links": []
    }
  }
}
```

主边包含：source、target、relation_type、evidence_type、confidence、evidence、time_gap_hours。节点和平台名称使用现有 API 数据契约映射。

## 11. 前端

新增：

```text
frontend/src/api/events.js                  getEventPropagation(id)
frontend/src/components/PropagationGraph.vue
frontend/src/components/PropagationTimeline.vue
```

事件详情页增加“传播路径”页签。

### 11.1 关系图

使用 ECharts graph，采用从左到右的时间分层布局。节点横向位置由发布时间决定，纵向位置按平台或传播分支分层。

- 实线：explicit
- 虚线：inferred
- 红色：origin_candidate
- 紫色：influencer_amplification
- 蓝色：media_intervention
- 金色：official_response
- 橙色：peak_content / turning_point
- 灰色：ordinary

点击节点显示文章、作者、平台、时间、互动量和关键原因。点击边显示关系类型、置信度与证据。

默认只展示重要节点，提供“展开普通节点”开关。图为空时展示时间线和数据不足说明。

### 11.2 时间线

展示传播阶段、代表节点、时间、平台和阶段说明。页面固定显示覆盖提示，明确虚线为算法推测。

## 12. 测试

后端测试必须直接调用传播构建器和真实 API 服务：

- 明确转发链优先于推测。
- 跨平台推测链。
- 多源头传播森林。
- 低相似内容不连边。
- 每个推测节点最多一个父节点。
- 不存在环和时间倒流。
- 缺少发布时间保留节点但降低可信度。
- 大V、媒体、官方回应、平台首发和峰值识别。
- 节点裁剪后关键路径完整。
- 空事件返回稳定空结构。

前端执行构建验证，并通过组件测试或静态断言确认图例、明确/推测边样式、空状态和 API 调用。

## 13. 完成条件

- 当前全连接相似关系网被替换为证据优先的稀疏传播森林。
- API 返回可解释边、置信度、证据、关键节点和阶段。
- 前端事件详情可展示关系图和阶段时间线。
- 数据不足时不伪造传播关系。
- 完整后端测试和前端构建通过。
- 启动系统后可以使用真实或准备好的事件数据展示传播图效果。
