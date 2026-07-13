# 后端 API 返回数据格式对齐文档

本文档描述前端各页面实际消费的数据字段，供后端开发同学对齐接口返回格式。

> v2 契约对齐日期：2026-07-13。生命周期统一使用“潜伏期 / 成长期 / 高潮期 / 消退期”，文章情感标签统一使用“正面 / 中立 / 负面”。

> 通用约定：所有接口返回 `{ "code": 200, "data": {...} }` 格式。`code !== 200` 视为错误。

---

## 1. 事件列表 `GET /api/events`

前端页面：舆情看板 (`views/welcome/index.vue`) + EventCard 组件

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `id` | int | ✅ | 事件唯一 ID |
| `title` | string | ✅ | 事件标题（限 50 字） |
| `summary` | string | ✅ | 事件摘要描述 |
| `heat_index` | float | ✅ | 综合热度指数，0-100，前端按 ≥80 红 / ≥50 橙 / <50 蓝 着色 |
| `lifecycle_stage` | string | ✅ | 生命周期阶段：`"潜伏期"` / `"成长期"` / `"高潮期"` / `"消退期"` |
| `lifecycle_status` | string | ✅ | 数据状态：`"sufficient"` / `"data_insufficient"`，历史人工状态可原样返回 |
| `lifecycle_confidence` | float | ✅ | 生命周期判定置信度，0-1 |
| `lifecycle_evidence` | object | ✅ | 点数、峰值比、近期斜率、波动和下降等可解释证据 |
| `lifecycle_updated_at` | string/null | ✅ | 生命周期最近一次更新的 ISO 时间；详情 GET 不会修改该值 |
| `sentiment_positive` | float | ✅ | 正面情感占比，0-1，如 `0.05` |
| `sentiment_negative` | float | ✅ | 负面情感占比，0-1 |
| `sentiment_neutral` | float | ✅ | 中立情感占比，0-1 |

**查询参数**：`?page=1&size=20&keyword=xxx`

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "events": [
      {
        "id": 1,
        "title": "某知名互联网企业疑似发生大规模用户数据泄露事件",
        "summary": "近日有网民爆料称...",
        "heat_index": 92.3,
        "lifecycle_stage": "高潮期",
        "sentiment_positive": 0.05,
        "sentiment_negative": 0.82,
        "sentiment_neutral": 0.13
      }
    ],
    "total": 10,
    "page": 1,
    "size": 20
  }
}
```

---

## 2. 事件详情 `GET /api/events/:id`

前端页面：事件详情分析报告 (`views/events/detail.vue`)

### 2.1 基本信息

> 现有框架状态：✅ Event 模型已定义所有字段。⚠️ 当前 mock 未填充 `time_code/location/cause/key_figures`，需实现 service 层时补上。

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `id` | int | ✅ | |
| `title` | string | ✅ | |
| `summary` | string | ✅ | |
| `heat_index` | float | ✅ | |
| `lifecycle_stage` | string | ✅ | `"潜伏期"` / `"成长期"` / `"高潮期"` / `"消退期"` |
| `lifecycle_status` | string | ✅ | `"sufficient"` / `"data_insufficient"` 或已持久化的审核状态 |
| `lifecycle_confidence` | float | ✅ | 0-1 |
| `lifecycle_evidence` | object | ✅ | 生命周期判定依据 |
| `lifecycle_updated_at` | string/null | ✅ | ISO 时间 |
| `sentiment_positive` | float | ✅ | 0-1 |
| `sentiment_negative` | float | ✅ | 0-1 |
| `sentiment_neutral` | float | ✅ | 0-1 |
| `time_code` | string | 🟡 | 发生时间，如 `"2026-07-11"`。前端缺省显示"待后端录入" |
| `location` | string | 🟡 | 发生地点 |
| `key_figures` | string | 🟡 | 涉事人物，逗号分隔 |
| `cause` | string | 🟡 | 事件起因 |

### 2.2 AI 研判报告 `report`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `report.overview_text` | string | ✅ | AI 生成的研判概述文本（支持换行） |
| `report.risk_data.level` | string | ✅ | 风险等级：`"高风险"` / `"中风险"` / `"低风险"` |
| `report.risk_data.score` | int | ✅ | 风险分值，0-100 |

### 2.3 趋势数据 `trend`

> 现有框架状态：⚠️ mock 仅返回 2 个 ISO 格式日期。需改为 7-14 个短格式 (`"M/D"`) 点，并填充 `key_points`。

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `trend.dates[]` | string[] | ✅ | 日期序列，如 `["7/1", "7/2", ...]`，**建议 7-14 个点** |
| `trend.counts[]` | int[] | ✅ | 每日报道量，与 dates 一一对应 |
| `trend.key_points[]` | object[] | 🟡 | 关键节点标注，缺省时前端自动生成 |

`key_points` 元素格式：
```json
{ "name": "首次报道", "coord": ["7/1", 5] }
```

### 2.4 平台分布 `platform`

> 现有框架状态：⚠️ mock 用 `"name"` 字段且值为 `"样例数据"`。需改为 `"platform"` 字段，取 7 个合法值之一。

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `platform.platforms[].platform` | string | ✅ | **必须使用以下 7 个平台名之一**：`"微博热搜"` `"微博搜索"` `"知乎"` `"B站"` `"小红书"` `"百度热搜"` `"百度搜索"` |
| `platform.platforms[].count` | int | ✅ | 该平台相关报道数 |

### 2.5 关键词 `keywords`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `keywords.keywords[].word` | string | ✅ | 关键词文本 |
| `keywords.keywords[].weight` | float | ✅ | 权重，0-1，值越大字号越大 |

### 2.6 关联报道 `articles`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `articles.total` | int | ✅ | 报道总数 |
| `articles.articles[].id` | int | ✅ | |
| `articles.articles[].platform` | string | ✅ | **必须是 7 平台名之一** |
| `articles.articles[].title` | string | ✅ | 报道标题 |
| `articles.articles[].author` | string | 🟡 | 作者/发布账号 |
| `articles.articles[].publish_time` | string | 🟡 | 发布时间，如 `"2026-07-11 14:20"` |
| `articles.articles[].reposts_count` | int | 🟡 | 转发数 |
| `articles.articles[].comments_count` | int | 🟡 | 评论数 |
| `articles.articles[].likes_count` | int | 🟡 | 点赞数 |
| `articles.articles[].clean_content` | string | ✅ | 清洗后的正文摘要 |
| `articles.articles[].sentiment_label` | string | ✅ | `"正面"` / `"中立"` / `"负面"` |
| `articles.articles[].is_suspicious` | bool | ✅ | 是否可疑（虚假检测） |
| `articles.articles[].suspicious_score` | float | 🟡 | 可疑度分值 0-1，仅 `is_suspicious=true` 时需要 |

### 2.7 完整响应示例

```json
{
  "code": 200,
  "data": {
    "id": 1,
    "title": "某知名互联网企业疑似发生大规模用户数据泄露事件",
    "summary": "近日有网民爆料称某头部互联网公司发生用户隐私数据泄露...",
    "heat_index": 92.3,
    "lifecycle_stage": "高潮期",
    "sentiment_positive": 0.05,
    "sentiment_negative": 0.82,
    "sentiment_neutral": 0.13,
    "time_code": "2026-07-11",
    "location": "北京市",
    "key_figures": "张某、李某",
    "cause": "暗网出现疑似该平台用户数据库挂牌出售信息",

    "report": {
      "overview_text": "该事件自7月8日首次在社交媒体出现以来，报道量呈爆发式增长...",
      "risk_data": { "level": "高风险", "score": 82 }
    },

    "trend": {
      "dates": ["7/1","7/2","7/3","7/4","7/5","7/6","7/7","7/8","7/9","7/10","7/11","7/12","7/13","7/14"],
      "counts": [3,5,8,12,28,45,68,82,78,85,72,55,35,22],
      "key_points": [
        { "name": "首次报道", "coord": ["7/1", 3] },
        { "name": "热度峰值", "coord": ["7/10", 85] },
        { "name": "最新动态", "coord": ["7/14", 22] }
      ]
    },

    "platform": {
      "platforms": [
        { "platform": "微博热搜", "count": 28 },
        { "platform": "知乎", "count": 12 },
        { "platform": "B站", "count": 8 },
        { "platform": "百度热搜", "count": 5 }
      ]
    },

    "keywords": {
      "keywords": [
        { "word": "数据泄露", "weight": 0.95 },
        { "word": "用户信息", "weight": 0.88 },
        { "word": "暗网", "weight": 0.72 }
      ]
    },

    "articles": {
      "total": 5,
      "articles": [
        {
          "id": 1,
          "platform": "微博热搜",
          "title": "网传某平台用户数据遭泄露，官方尚未回应",
          "author": "科技圈那些事",
          "publish_time": "2026-07-11 14:20",
          "reposts_count": 4521,
          "comments_count": 2830,
          "likes_count": 12056,
          "clean_content": "近日有网友爆料称某大型互联网平台发生用户数据泄露事件...",
          "sentiment_label": "负面",
          "is_suspicious": false,
          "suspicious_score": 0
        }
      ]
    }
  }
}
```

---

## 3. 智能问答 `POST /api/qa/ask`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `question` | string | ✅ | 用户问题。选了平台前会加 `[聚焦平台：XXX]` 前缀 |
| `event_id` | int | 🟡 | 关联事件 ID |

**请求**：
```json
{ "question": "这个事件的舆论走向如何？", "event_id": 1 }
```

**响应**：
```json
{ "code": 200, "data": { "answer": "根据目前的舆情数据...", "event_id": 1 } }
```

---

## 4. 用户管理 `GET/POST/PUT/DELETE /api/admin/users`

详见 `docs/backend_user_management_api_requirements.md`

---

## 5. 与现有后端框架的差距标注

> 以下基于 `backend/app/` 现有代码逐项对照，标注每一项是否需要后端改动。

### 5.1 模型层面

| 需求字段 | 后端模型现状 | 差距 |
|----------|-------------|:--:|
| Event: `time_code/location/cause/key_figures` | ✅ 已在 `models/event.py` 定义 | 无 |
| Article: `author/reposts_count/comments_count/likes_count/publish_time` | ✅ 已在 `models/article.py` 定义 | 无 |
| Article: `suspicious_score` | ✅ 已有 | 无 |
| User: `status`（启用/停用） | 🔴 **缺失**，需在 `models/user.py` 新增 `status = db.Column(db.Integer, default=1)` | ⚠️ 需改动 |
| `lifecycle_stage` 四选一约束 | 🟡 无 CHECK 约束，建议加应用层校验 | 建议加 |
| `sentiment_*` 和为 1 | 🟡 无约束，建议加应用层校验 | 建议加 |

### 5.2 API 层面

| 端点 | 后端现状 | 差距 |
|------|----------|:--:|
| `GET /api/events` 列表 | ✅ 已有 | 无 |
| `GET /api/events/:id` 详情 | ✅ 已有（含全部子资源内联） | 无 |
| `POST /api/qa/ask` | ✅ 已有 | 无 |
| `/api/admin/users` 用户 CRUD | 🔴 **整个 `/api/admin` 蓝图不存在**，需新建 | ⚠️ 需新建 |
| `admin_required` 装饰器 | ✅ 已在 `security.py:53` 定义，crawler/import/tasks 已在使用 | 无 |

### 5.3 数据格式层面

| 问题 | 当前 mock | 要求 |
|------|-----------|------|
| ⚠️ **平台字段名** | `"name": "样例数据"` | `"platform": "微博热搜"`（7 选 1） |
| ⚠️ **趋势日期格式** | `"2026-07-08"`（ISO 全格式） | `"7/8"`（短格式 M/D） |
| ⚠️ **趋势数据量** | 仅 2 个点 | 建议 7-14 个点 |
| ⚠️ **情感标签** | 出现 `"中性"` 或未知值 | 统一规范化为 `"中立"` |
| 🔴 **User 表缺 status** | 无此字段 | 新增 `status` int 列 |

### 5.4 结论

**没有超出框架能力的需求**。所有缺失项都是实现层问题（mock 数据格式、新增 admin 蓝图、User 模型加字段），不是架构限制。Flask + SQLAlchemy + JWT + `admin_required` 全套基础设施已就绪。

---

## 6. 关键约束

| 约束 | 说明 |
|------|------|
| **平台名必须精确** | `platform` 字段只能使用 7 个值：`"微博热搜"` / `"微博搜索"` / `"知乎"` / `"B站"` / `"小红书"` / `"百度热搜"` / `"百度搜索"`。用错则图标和品牌色失效 |
| `lifecycle_stage` 四选一 | 只能返回 4 个字符串之一，前端按值做阶段指示器 |
| `sentiment_*` 三者之和应为 1.0 | 正面+中立+负面 = 1.0，前端饼图依赖此比例 |
| `heat_index` 建议 0-100 | 前端进度条和颜色阈值基于此范围 |
| `trend` 建议 7-14 个点 | 少于 7 个点时前端自动生成模拟数据（影响准确性） |
