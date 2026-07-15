# 后端改动与前端接口交接文档

更新时间：2026-07-15  
适用分支：`branchhu`  
范围：本次只涉及后端；前端目录未修改。

## 1. 今日后端改动概览

本次后端改动主要覆盖以下几块：

1. **平台目录、用户关注和搜索历史**
   - 增加平台目录服务，统一提供平台官网、站内搜索地址、采集能力和评论能力。
   - 用户可以关注或取消关注平台。
   - 关键词搜索会自动保存关键词、所选平台和目标采集数量。
   - 支持分页查看、删除和复用搜索历史。

2. **主流新闻网站采集**
   - 增加人民网、36氪、澎湃、InfoQ、少数派的采集适配及 RSS/评论相关后端能力。
   - 平台能力通过现有爬虫平台接口暴露，前端不需要改变调用入口。

3. **评论统一处理**
   - B站评论与其他平台评论进入同一套预处理、事件级分析和情感分析流程。
   - 情感分析优先使用 DeepSeek 批量复核，SnowNLP 作为降级方案。
   - 已有 LLM 结果不会因为重复采集被基础模型结果覆盖。

4. **事件分析**
   - 事件详情增加生命周期预测结果。
   - 增加事件预测、传播路径、关键词、平台、文章、情感等独立查询接口。
   - 传播分析使用词云 Top 5 关键词构造有限节点和有向路径。

5. **豆包全网溯源**
   - 新增独立的火山方舟 Responses API 客户端。
   - 豆包仅用于全网联网溯源；DeepSeek 原有分析职责保持不变。
   - 溯源失败时返回明确的不足状态，不把失败伪装成完整结果。

6. **每日热点**
   - 每日热点默认结果数量调整为 20 条。
   - 当前汇总微博热搜、百度热搜、知乎热榜，并保留原有热点接口。

## 2. 服务地址与通用约定

本地服务：

```text
后端：http://localhost:5000
前端：http://localhost:8848
```

所有接口均使用 JSON。需要登录的接口应携带现有登录凭证（Cookie/Token 方式以项目现有认证实现为准）。统一响应结构为：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

接口失败时使用非 2xx HTTP 状态码，并在 `message` 中说明原因。前端不要只根据 `data` 是否为空判断成功，应同时检查 HTTP 状态和 `code`。

## 3. 用户平台目录与搜索历史接口

### 3.1 获取平台目录

```http
GET /api/user/sources
```

响应示例：

```json
{
  "code": 0,
  "data": {
    "presets": [
      {
        "code": "bilibili",
        "name": "哔哩哔哩",
        "homepage_url": "https://www.bilibili.com",
        "search_url": "https://search.bilibili.com/all?keyword={keyword}",
        "crawlable": true,
        "commentable": true,
        "requires_key": false,
        "followed": false
      }
    ]
  }
}
```

`search_url` 中的 `{keyword}` 是占位符，前端展示或跳转时替换为 URL 编码后的关键词。目录中包含微博、百度、知乎、B站、抖音、小红书以及主流新闻/RSS 平台等共 12 个预置平台，具体以接口返回为准，不要在前端硬编码平台列表。

### 3.2 关注平台

```http
POST /api/user/sources/{code}/follow
```

无需请求体。成功后返回更新后的平台配置。

### 3.3 取消关注平台

```http
DELETE /api/user/sources/{code}/follow
```

平台编码不存在时返回 404。关注状态是用户级数据，不同用户互不影响。

### 3.4 查看搜索历史

```http
GET /api/user/search-history?page=1&size=20
```

参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `page` | integer | 1 | 页码 |
| `size` | integer | 20 | 每页数量 |

前端应使用响应中的总数和分页字段渲染分页，不要假设历史记录只有一页。

### 3.5 删除搜索历史

```http
DELETE /api/user/search-history/{history_id}
```

### 3.6 复用搜索历史

```http
POST /api/user/search-history/{history_id}/repeat
```

响应中的 `search_payload` 可直接作为关键词搜索接口的请求参数：

```json
{
  "code": 0,
  "data": {
    "search_payload": {
      "keyword": "张雪峰",
      "platforms": ["bilibili", "weibo"],
      "target_count": 50
    }
  }
}
```

## 4. 关键词搜索与采集接口

### 4.1 关键词搜索

```http
POST /api/crawler/search
Content-Type: application/json
```

请求体：

```json
{
  "keyword": "张雪峰",
  "platforms": ["bilibili", "weibo", "news_people"],
  "target_count": 50,
  "force": false
}
```

约束：`keyword` 非空；`target_count` 范围为 1–200。接口会立即记录搜索历史并返回任务信息，实际采集和分析在后台执行。

响应重点字段：

```json
{
  "task_id": 123,
  "reused": false,
  "cached": false,
  "stale": false,
  "aggregation_run_id": 456
}
```

如果命中有效缓存，`task_id` 可能为 `null`，此时应使用 `aggregation_run_id` 获取已有结果；如果 `stale=true`，表示返回旧结果的同时后台已启动增量刷新。

### 4.2 查询采集任务状态

```http
GET /api/crawler/status
```

前端可轮询该接口显示任务状态。不要在浏览器端自行推断后台任务是否完成。

### 4.3 获取可用爬虫平台

```http
GET /api/crawler/platforms
```

响应包含：

```json
{
  "platforms": ["bilibili", "weibo"],
  "rss": ["rss_people", "rss_36kr"]
}
```

主流新闻平台作为独立平台目录展示时，优先使用 `/api/user/sources`；需要渲染实际可搜索爬虫列表时使用本接口。

## 5. 事件分析接口

以下接口均需要登录，`{event_id}` 为事件 ID：

| 接口 | 用途 |
|---|---|
| `GET /api/events` | 事件分页列表 |
| `GET /api/events/search?q=关键词` | 搜索事件 |
| `GET /api/events/{event_id}` | 事件详情，详情中包含 `prediction` |
| `GET /api/events/{event_id}/trend` | 趋势数据 |
| `GET /api/events/{event_id}/prediction` | 生命周期预测与发展趋势 |
| `GET /api/events/{event_id}/sentiment` | 事件情感汇总 |
| `GET /api/events/{event_id}/platform` | 平台分布 |
| `GET /api/events/{event_id}/keywords` | 关键词/词云数据 |
| `GET /api/events/{event_id}/articles` | 事件文章列表 |
| `GET /api/events/{event_id}/propagation` | 豆包溯源和关键传播路径 |
| `GET /api/events/{event_id}/similar?limit=5` | 相似事件，limit 范围 1–20 |

### 5.1 生命周期预测字段

`/prediction` 返回当前生命周期、置信度、下一阶段、趋势及模型说明。前端应同时展示 `confidence` 和模型/降级状态；预测结果不是确定性事实。

### 5.2 传播路径字段

`/propagation` 返回溯源状态、疑似源头、引用信息、关键词节点和有向边。正常结果最多约 6 个节点（1 个源头 + Top 5 高频词）及 5 条路径。豆包联网失败时应展示“溯源不足/待重试”，不要把结果显示成已确认源头。

## 6. 每日热点接口

### 6.1 获取今日热点

```http
GET /api/hotspots/today?limit=20
```

`limit` 范围为 1–100，默认配置为 20。当前来源包括微博、百度、知乎，响应为去重汇总后的热点条目，并带有来源和主题分类信息。

### 6.2 刷新今日热点（管理员）

```http
POST /api/hotspots/today/refresh
```

该接口需要管理员权限，普通前端用户只调用查询接口。

## 7. 推荐前端调用流程

1. 登录后调用 `/api/user/sources`，渲染平台目录和关注状态。
2. 用户点击关注/取消关注时调用对应 POST/DELETE 接口，然后用返回值更新卡片状态。
3. 搜索页提交 `/api/crawler/search`；后端会自动保存搜索历史。
4. 根据返回的 `task_id` 轮询 `/api/crawler/status`，任务完成后刷新事件列表。
5. 打开事件详情时优先调用详情接口；需要独立刷新模块时分别调用 prediction、sentiment、keywords、propagation 等接口。
6. 个人中心调用 `/api/user/search-history` 展示记录；点击再次搜索时调用 repeat 接口，再把 `search_payload` 回填到搜索表单。
7. 首页热点使用 `/api/hotspots/today?limit=20`，不要在前端自行拼接三个热榜。

## 8. 联调注意事项

- 认证失败、无权限和资源不存在分别按 HTTP 401/403/404 处理。
- 采集、LLM 溯源和生命周期分析都是后台或远程调用，前端应提供加载中、超时和降级状态。
- 豆包溯源与 DeepSeek 分工不同：豆包负责全网联网溯源，DeepSeek 负责原有评论复核和生命周期等分析。
- 评论数据已经走文章同样的预处理和事件级分析流程，前端无需为 B站评论单独设计另一套分析入口。
- 平台列表、官网和搜索地址以后端返回为准，避免前端复制一份容易过期的目录。

## 9. 验证记录

- 后端专项测试：`3 passed`
- 后端全量测试：`369 passed`
- Python `compileall`：通过
- `git diff --check`：通过
- `frontend/`：无 Git 差异，本次未修改前端代码

## 10. 当前限制

- 每日热点当前接入微博、百度、知乎三个热榜，定时调度器仍未启用。
- 主流新闻网站的实际抓取数量受站点限流、RSS 可用性和网络环境影响。
- 豆包联网溯源依赖火山方舟 API Key 和模型权限；调用失败时接口会返回不足状态。
- 本次改动尚未统一提交或推送，交接前请确认工作区改动属于本次后端功能。
