# 《功夫女足》电影全链路实跑与前端质量验收设计

## 1. 目标

以“《功夫女足》电影”为唯一舆情事件关键词，执行一次真实、可追踪、可复现的完整工作周期：

```text
前端定向分析语义
→ 后端多平台搜索采集
→ 原始文档持久化
→ 标准化/正文提取/清洗/质量/去重/分词
→ TF-IDF/关键词/BGE 表示
→ 搜索作用域事件聚合
→ 文章和簇级情感分析
→ 管理员发布正式事件
→ AI 元数据、情感、热度、生命周期、风险和报告后处理
→ 事件列表/详情/传播/报告/问答 API
→ Vue Dashboard 和 Event Detail 实际呈现
→ 用户视角数据质量验收
```

全过程保存阶段请求、响应、数据库中间状态、前端 DOM 和截图。真实密钥、JWT、Cookie 和请求头不进入产物。

## 2. 约束来源

执行遵循：

- `D:\newbigwork\frontend_architecture_and_api_integration.md`
- `docs/后端系统现状与接口说明.md`
- `docs/backend_api_data_format.md`
- 当前前端 `api/`、Pinia store、`analysis`、`welcome` 和 `events/detail` 实际代码

前端视觉重设计不在范围内，但发现固定 mock、字段错位、`undefined`、NaN、空白图表或误导性呈现时，必须修复数据消费或后端契约。

## 3. 隔离运行环境

使用专用临时运行目录和 SQLite：

```text
artifacts/kung_fu_women_football/
```

后端进程继承 `backend/.env` 的真实爬虫和 LLM 配置，但覆盖：

- 专用 SQLite URI；
- `TASK_RECOVER_ON_STARTUP=false`；
- `TASKS_RUN_SYNC=false`，保留真实异步任务和轮询；
- `AUTO_CREATE_DB=true`；
- 禁止调试 reloader；
- 固定监听 `127.0.0.1:5000`。

前端使用正式 Vite 代理和端口 8848。所有进程在验收结束后显式终止。

## 4. 采集策略

关键词严格使用：

```text
《功夫女足》电影
```

搜索平台：

- `baidu`
- `weibo`
- `zhihu`
- `bilibili`

首次目标数量使用 24。若有效文档不足以形成可发布簇，可在同一隔离数据库中将目标数量提高到 40，但必须在 manifest 记录重试原因、请求参数和新增数据量。

不使用 sample 数据替代真实搜索。某个平台失败时记录认证、配额、网络、平台拦截、空响应或结构变化，不伪造成功。

## 5. 阶段记录

输出目录保存：

| 文件 | 内容 |
|---|---|
| `00_manifest.json` | 关键词、时间、代码提交、运行配置摘要、阶段状态 |
| `01_login.json` | 登录状态和用户角色，不含 token |
| `02_search_submission.json` | 搜索请求和任务响应 |
| `03_task_poll_history.json` | 每次轮询的 status/progress/message/result 摘要 |
| `04_raw_articles.json` | 平台、标题、URL、原文长度/哈希、原文摘录、互动和时间 |
| `05_preprocessing.json` | 正文、质量、权重、去重、分词和警告 |
| `06_content_analysis.json` | AnalysisRun、关键词、实体、主题、向量元数据 |
| `07_aggregation.json` | AggregationRun、簇、成员、分配得分和警告 |
| `08_sentiment.json` | SentimentRun、文章结果和簇级聚合 |
| `09_publish.json` | 选簇依据、发布响应、正式 Event ID 和后处理 |
| `10_dashboard_api.json` | `GET /api/events` 的前端看板数据 |
| `11_event_detail_api.json` | 详情嵌套结构 |
| `12_propagation_api.json` | 传播图、覆盖状态和限制 |
| `13_report_api.json` | 报告结构和导出摘要 |
| `14_qa_api.json` | 一次基于事件上下文的真实问答摘要 |
| `15_frontend_dom.html` | 事件详情页面最终 DOM |
| `16_dashboard.png` | 看板截图 |
| `17_event_detail.png` | 事件详情截图 |
| `18_quality_assessment.json` | 自动质量规则与通过/失败 |
| `19_user_quality_report.md` | 用户视角结论、问题和修复记录 |

正文和原始 payload 只保留受控摘录、长度和哈希；专用数据库不提交 Git。

## 6. 正式事件选择与发布

搜索任务会生成 search scope 聚合簇，但不会自动进入正式事件库。发布前对簇进行：

1. 关键词覆盖；
2. 标题与“功夫女足/电影”的语义相关性；
3. 成员数量；
4. 平台覆盖；
5. 代表文章可读性；
6. 误混入体育女足、功夫足球旧作品或无关影视内容的比例。

选择相关性最高且证据足够的簇，通过：

```text
POST /api/aggregation/clusters/{id}/publish
```

若所有簇均不相关，不发布错误事件；记录质量失败并调整采集数量或搜索平台后重试。

## 7. 前端实际验收

使用 Selenium + 已安装 Chrome 进行真实浏览器验证：

1. 登录管理员；
2. 打开 `/analysis`，输入关键词并验证缓存/任务结果状态；
3. 打开 `/dashboard` 并使用关键词“《功夫女足》电影”筛选，验证目标事件卡片；
4. 打开 `/events/{event_id}`；
5. 等待详情和传播 API；
6. 保存 DOM 和截图；
7. 检查页面无 `undefined`、`NaN`、`[object Object]`、接口错误提示和主要区域空白；
8. 检查事件标题、报道数、热度、生命周期、情感、平台、关键词、风险、传播、文章和 AI 摘要是否与 API 一致。

## 8. 用户视角质量门槛

### 8.1 必须通过

- 正式事件标题与《功夫女足》电影明确相关；
- 至少 3 篇有效非重复报道，或明确标记数据不足；
- 文章相关率不低于 70%；
- 至少 2 个实际来源平台，若不足必须明确展示限制；
- 看板 title、summary、heat、lifecycle、sentiment 和关键词不为错误占位；
- 情感比例为有限数且总和接近 1；
- 趋势 dates/counts 长度一致；
- 平台 count 总和与文章数一致；
- 关键词不全是查询词或通用停用词；
- 风险必须解释为风险评估，不可显示为事实真假；
- 传播证据不足时允许空边，但必须显示 coverage/limitations；
- 前端不得用固定 45 等 mock 数值冒充真实风险维度；
- DOM 不出现未定义值和明显乱码；
- API 通用响应结构和前端解包方式一致。

### 8.2 建议通过

- 元数据地点、人物和起因有证据文章；
- AI 摘要与报道基本一致；
- QA 回答引用当前事件语境；
- 页面主要图表均有可解释数据或清晰空状态；
- 报告 HTML 可以下载并包含事件核心字段。

## 9. 缺陷处理

发现问题时：

1. 保存失败证据；
2. 判断属于外部数据、后端算法/API、前端字段消费还是展示语义；
3. 对代码问题先写失败测试；
4. 实施最小修复；
5. 重跑相关阶段；
6. 产物中同时记录修复前后结果。

不得通过手工修改最终 JSON 来掩盖真实管线问题。

## 10. 验收完成条件

- 真实爬虫和 LLM 至少完成一次有效调用；
- 搜索任务、分析、聚合和情感成功或有准确外部失败分类；
- 发布一个相关正式事件；
- 所有约定 API 返回并记录；
- Vue 前端构建成功；
- Chrome 实际页面截图和 DOM 已保存；
- 用户质量门槛有逐项结论；
- 发现的代码缺陷已修复并回归；
- 全量自动化测试零失败；
- 产物无密钥、JWT、Cookie 或认证头；
- 专用数据库不提交，开发数据库不被污染。
