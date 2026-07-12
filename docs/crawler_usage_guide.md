# 爬虫模块使用说明

本文档由爬虫开发组提供，描述爬虫模块的完整使用方法。

---

## 一、爬虫模块目前怎么工作

项目提供两种主要采集模式：

**关键词搜索**：`/api/crawler/search`
**热榜采集**：`/api/crawler/trigger`

它们并不只是"爬取并返回数据"，而是会继续执行后续流程：

```
网络爬虫
→ 字段标准化
→ 正文提取
→ 清洗和去重
→ 内容分析
→ 事件聚合
→ 情感分析
→ 保存任务结果
```

热榜模式还会继续执行：

```
热榜种子采集
→ 根据热榜词扩展搜索
→ 热点主题发现
→ 正式事件聚合
→ 热度计算
```

### 支持的平台标识

**关键词搜索平台：**

| 标识 | 平台 | 所需配置 |
|------|------|----------|
| baidu | 百度搜索 | QIANFAN_API_KEY |
| zhihu | 知乎搜索 | ZHIHU_ACCESS_SECRET |
| weibo | 微博搜索 | TikHub Key |
| bilibili | B站搜索 | 不需要 Key |
| xiaohongshu | 小红书 | TikHub Key |
| douyin | 抖音 | TikHub Key |
| rss | RSS | RSS_FEED_URL |
| sample | 本地测试爬虫 | 不需要联网 |

**热榜平台：**

| 标识 | 平台 |
|------|------|
| weibo_hot | 微博热搜 |
| baidu_hot | 百度热榜 |
| zhihu_hot | 知乎热榜 |

`target_count` 是所有选定平台**合计**的目标数量，并不是每个平台各爬这么多。

---

## 二、准备 .env

关键配置项：

```dotenv
QIANFAN_API_KEY=你的百度千帆Key
ZHIHU_ACCESS_SECRET=你的知乎Key

TIKHUB_API_KEY=通用TikHubKey
TIKHUB_WEIBO_API_KEY=微博单独Key
TIKHUB_XIAOHONGSHU_API_KEY=小红书单独Key
TIKHUB_DOUYIN_API_KEY=抖音单独Key

TIKHUB_ENABLED_PLATFORMS=weibo,xiaohongshu,douyin

LLM_API_KEY=你的DeepSeekKey
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL_NAME=deepseek-chat
```

没有配置对应 Key 的平台**不会注册**到爬虫列表中。例如没有 `QIANFAN_API_KEY`，则 `baidu` 和 `baidu_hot` 不可用。

开发时建议：

```dotenv
TASKS_RUN_SYNC=true
BGE_ENABLED=false
```

- `TASKS_RUN_SYNC=true`：接口返回前完成任务，方便调试
- `BGE_ENABLED=false`：暂时关闭较慢的 BGE 模型，使用 TF-IDF
- 正式运行时可以改回异步任务并启用 BGE

**不要把 .env 上传到 Git。**

---

## 三、启动后端

```powershell
cd backend
python -m pip install -r requirements.txt
python run.py
```

后端默认运行在 `http://127.0.0.1:5000`

健康检查：`curl http://127.0.0.1:5000/api/health`

---

## 四、先登录并取得 Token

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5000/api/auth/login" `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ username = "admin"; password = "admin123" } | ConvertTo-Json)

$token = $login.data.token
$headers = @{ Authorization = "Bearer $token" }
```

默认管理员账号在 `.env` 中配置：

```dotenv
DEMO_ADMIN_USERNAME=admin
DEMO_ADMIN_PASSWORD=admin123
```

---

## 五、使用关键词搜索爬虫

### 1. 小规模测试（建议先 12 条）

```powershell
$body = @{
  keyword = "人工智能"
  platforms = @("baidu", "zhihu", "weibo", "bilibili")
  target_count = 12
} | ConvertTo-Json

$result = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5000/api/crawler/search" `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

正常返回：

```json
{
  "code": 200,
  "data": { "task_id": 1, "reused": false, "cached": false }
}
```

### 2. 查询任务结果

```powershell
$taskId = $result.data.task_id
$task = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/tasks/$taskId" -Headers $headers
```

成功结果应包含：

```json
{
  "status": "success",
  "result": {
    "collected": 12,
    "processed": 12,
    "failed": 0,
    "platform_counts": { "baidu": 3, "zhihu": 3, "weibo": 3, "bilibili": 3 },
    "analysis_run_id": 1,
    "aggregation_run_id": 1,
    "sentiment_run_id": 1
  }
}
```

异步模式下轮询：

```powershell
do {
  Start-Sleep -Seconds 2
  $task = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/tasks/$taskId" -Headers $headers
  Write-Host "状态:" $task.data.status "进度:" $task.data.progress
} while ($task.data.status -in @("pending", "running"))
```

### 3. 查看聚合结果并发布正式事件

```powershell
$aggregationRunId = $task.data.result.aggregation_run_id
$clusters = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/aggregation/runs/$aggregationRunId/clusters" -Headers $headers

# 发布第一个事件簇
$clusterId = $clusters.data.clusters[0].id
$published = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/aggregation/clusters/$clusterId/publish" -Headers $headers
$eventId = $published.data.event_id

# 查看正式事件
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/events/$eventId" -Headers $headers
```

---

## 六、使用热榜爬虫

```powershell
$body = @{
  platforms = @("weibo_hot", "baidu_hot", "zhihu_hot")
  target_count = 3
} | ConvertTo-Json

$result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/crawler/trigger" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $body
```

成功结果应包含：`analysis_run_id`, `hotspot_run_id`, `aggregation_run_id`, `sentiment_run_id`

检查热点运行：

```powershell
$hotspot = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/hotspots/runs/$hotspotRunId" -Headers $headers
```

正常情况下：`status=success, topic_status=success, heat_status=success`

---

## 七、不联网测试（sample 平台）

```powershell
$body = @{
  keyword = "公共事件"
  platforms = @("sample")
  target_count = 1
} | ConvertTo-Json

$result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/crawler/search" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $body
```

如果 sample 成功但真实平台失败，说明后端业务流程正常，问题在 API Key/网络/第三方接口。如果 sample 也失败，应检查后端任务、数据库、清洗或分析流程。

---

## 八、自动化测试

```powershell
cd D:\newbigwork\first_big_homework

# 爬虫核心测试
python -m pytest backend/tests/test_crawler_core.py -q

# 平台适配器测试
python -m pytest backend/tests/test_crawler_adapters.py -q

# 爬虫 API 测试
python -m pytest backend/tests/test_crawler_api.py -q

# 采集服务测试
python -m pytest backend/tests/test_crawl_service.py -q

# 爬虫到分析的联合测试
python -m pytest backend/tests/test_jobs.py -q

# 全部爬虫测试
python -m pytest backend/tests/test_crawler_core.py backend/tests/test_crawler_adapters.py backend/tests/test_crawler_api.py backend/tests/test_crawl_service.py backend/tests/test_jobs.py -q

# 全后端回归（263 passed, 0 failed）
python -m pytest backend/tests -q
```

---

## 九、真实联网测试检查清单

- [ ] task status = success
- [ ] collected > 0
- [ ] processed > 0
- [ ] failed = 0 或可解释
- [ ] platform_counts 包含目标平台
- [ ] errors 为空
- [ ] analysis_run_id 存在
- [ ] aggregation_run_id 存在
- [ ] sentiment_run_id 存在

热榜额外检查：

- [ ] expanded > 0
- [ ] hotspot_run_id 存在
- [ ] topic_status = success
- [ ] heat_status = success
- [ ] 正式事件数量 > 0

**推荐测试顺序：**

1. sample 单平台
2. B站单平台
3. 百度、知乎等有 Key 的单平台
4. 微博、小红书、抖音等 TikHub 平台
5. 四个平台组合搜索
6. 三个平台热榜完整流程
7. 最后运行全量后端测试

---

## 十、已知实际情况

- 百度、知乎、微博、B站均曾成功返回数据
- 四个平台组合测试每轮采集 12 条，连续三轮成功
- 微博大多数请求有效，但曾出现一次 TikHub SSL EOF
- 小红书对部分关键词可以返回接口成功但无数据
- 抖音扩展接口曾持续返回 HTTP 403
- 热榜完整流程连续三轮的主题发现和热度计算均成功

测试报告中应区分：系统解析失败 / 第三方接口失败 / 鉴权或配额失败 / 接口成功但当前关键词无数据。"接口返回 200 但无数据"不能直接算作爬虫完全成功，也不能直接说明解析器有问题，需要结合第三方原始响应判断。
