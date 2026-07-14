# 舆情系统八项改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将主流新闻、传播/生命周期解释、算法验证、每日热点手动抓取和后台稳定性真正打通并形成可复核报告。

**Architecture:** 真实数据和规则算法是主链路，LLM 只消费已采集证据并提供可降级解释。每日热点拆分为“只采榜单”和“用户单条抓详情”，调度统一复用现有恢复调度器。

**Tech Stack:** Flask、SQLAlchemy、pytest、APScheduler、Vue 3、TypeScript、Vitest、ECharts、HDBSCAN、现有 LLMClient。

---

### Task 1: 修复真实平台展示契约

**Files:**
- Create: `frontend/src/views/events/platformPresentation.ts`
- Create: `frontend/src/views/events/platformPresentation.test.ts`
- Modify: `frontend/src/views/events/detail.vue`
- Test: `backend/tests/test_event_service.py`

- [ ] 写后端测试，断言五个 `news_*` 平台按真实计数返回，未知/空平台不会变成百度搜索。
- [ ] 运行目标测试确认失败原因是错误回退或缺少覆盖。
- [ ] 写前端纯函数测试：优先后端平台，回退实际文章平台，单平台仍只返回一个，空数据返回空数组。
- [ ] 删除 `PLATFORMS.slice(0, 4)` 和文章平台的伪造默认值，接入纯函数。
- [ ] 运行后端测试、Vitest 和前端构建。

### Task 2: 验证主流新闻评论进入后续分析

**Files:**
- Modify: `backend/tests/test_mainstream_news_crawler.py`
- Modify: `backend/tests/test_jobs.py`
- Modify: `backend/app/tasks/jobs.py`
- Test: `backend/tests/test_comment_service.py`

- [ ] 写失败测试：新闻评论落库后能被公众意见快照统计，`unsupported` 与 `empty` 状态分开。
- [ ] 运行测试确认当前缺口。
- [ ] 最小修改评论补全状态和任务摘要，保证五站文章仍进入同一分析文章集合。
- [ ] 运行新闻、任务、评论、内容分析、聚合和事件详情回归。

### Task 3: 增加基于证据的传播解释

**Files:**
- Create: `backend/app/propagation/keyword_relations.py`
- Create: `backend/app/services/propagation_analysis_service.py`
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/app/propagation/builder.py`
- Modify: `backend/tests/test_propagation.py`
- Modify: `frontend/src/views/events/detail.vue`

- [ ] 写关键词共现测试，断言关系包含共同文章 ID、平台数和示例标题。
- [ ] 写 LLM 解析测试，覆盖合法 JSON、引用不存在文章、非 JSON 和客户端不可用。
- [ ] 运行测试确认服务尚不存在。
- [ ] 实现确定性关键词关系和统一 `LLMClient` 的结构化解释；限制输入长度并校验证据引用。
- [ ] 将 `origin_analysis`、`keyword_relations`、`llm_analysis` 合并到传播 API，规则图始终保留。
- [ ] 前端展示解释状态和“仅基于已采集材料”的限制，删除误导性“左到右固定链路”文案。
- [ ] 运行传播、事件 API、前端测试和构建。

### Task 4: 对齐生命周期序列并增加趋势解释

**Files:**
- Modify: `backend/app/services/lifecycle_service.py`
- Create: `backend/app/services/lifecycle_explanation_service.py`
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/app/services/hotspot_service.py`
- Modify: `backend/app/services/event_service.py`
- Replace: `backend/tests/test_trend_predictor.py`
- Modify: `frontend/src/views/events/lifecyclePresentation.ts`
- Create: `frontend/src/views/events/lifecyclePresentation.test.ts`

- [ ] 用当前公开 API 重写已过期趋势测试，先确认旧导入导致收集失败。
- [ ] 写按统一日期轴生成报道、评论、情感和平台序列的失败测试。
- [ ] 写 LLM 趋势解释解析/降级测试，断言规则阶段不被覆盖。
- [ ] 实现统一序列和 `trend_explanation`、`next_stage_hint`、`momentum` 持久化。
- [ ] 前端展示置信度、样本限制、趋势解释与下一阶段提示。
- [ ] 运行趋势、聚合、热点、事件详情和前端回归。

### Task 5: 修复并真实验证 B 站评论

**Files:**
- Modify: `backend/app/crawler/bilibili.py`
- Modify: `backend/tests/test_crawler_adapters.py`
- Modify: `backend/tests/test_jobs.py`
- Create: `docs/verification/2026-07-15-bilibili-comments-live-check.md`

- [ ] 写 BV 转 aid 后评论请求必须携带设备 Cookie/Referer 的失败测试。
- [ ] 写顶级评论、内嵌回复、空响应、风控错误和非法 ID 测试。
- [ ] 运行测试确认请求头或状态处理缺口。
- [ ] 最小修复请求头复用和错误状态，不绕过访问控制。
- [ ] 对一条公开 BV 低频请求并记录脱敏输入、HTTP/API 状态、评论数量和示例文本。

### Task 6: 修复 HDBSCAN 健壮性并生成端到端报告

**Files:**
- Modify: `backend/app/analysis/event_clusterer.py`
- Modify: `backend/tests/test_event_aggregation_algorithms.py`
- Modify: `backend/tests/test_event_aggregation_service.py`
- Create: `backend/scripts/verify_hdbscan_pipeline.py`
- Create: `docs/verification/2026-07-15-hdbscan-pipeline-report.md`

- [ ] 写不同特征维度、全零特征、噪声点和依赖不可用的失败测试。
- [ ] 运行测试并记录当前矩阵构建或未捕获异常。
- [ ] 实现固定维度矩阵、有效特征过滤、显式 warning 和可控回退。
- [ ] 用内容分析实际输出执行聚合，报告每篇文章输入、特征维度、簇/噪声分配和发布结果。
- [ ] 运行算法、服务和脚本验证。

### Task 7: 生成虚假文本检测端到端报告

**Files:**
- Modify: `backend/tests/test_fake_detector.py`
- Create: `backend/scripts/verify_fake_detection_pipeline.py`
- Create: `docs/verification/2026-07-15-fake-detection-pipeline-report.md`

- [ ] 写脚本输出结构测试，要求包含输入文章、上下文、特征分、LLM 状态、判断和免责声明。
- [ ] 运行测试确认脚本缺失。
- [ ] 实现脚本，复用 `batch_assess_articles`，不复制检测逻辑。
- [ ] 使用真实已采集数据；不足时补充固定对照样本，并清晰标记来源。
- [ ] 运行 fake detector 测试和脚本，检查报告不泄露密钥。

### Task 8: 将每日热点改为分类后手动抓详情

**Files:**
- Modify: `backend/app/models/daily_hot.py`
- Modify: `backend/app/services/event_topic_service.py`
- Modify: `backend/app/services/daily_hot_service.py`
- Modify: `backend/app/api/hotspots.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/tests/test_daily_hot_service.py`
- Modify: `backend/tests/test_hotspots_api.py`
- Modify: `backend/tests/test_jobs.py`
- Modify: `frontend/src/api/dailyHot.ts`
- Modify: `frontend/src/api/types/opinion.ts`
- Modify: `frontend/src/views/welcome/index.vue`

- [ ] 写测试证明采集完成不会自动创建 enrichment 任务。
- [ ] 写分类测试，热点尚无事件时也返回 category/topic_name/topic_keywords/category_counts。
- [ ] 写单条 `POST /hotspots/today/items/<id>/enrich` 测试，覆盖新建、复用、合并条目和不存在。
- [ ] 运行测试确认当前自动补全和分类死代码问题。
- [ ] 将分类字段持久化到热点条目；移除刷新/定时任务的自动补全。
- [ ] 实现单条手动补全 API 和任务复用。
- [ ] 前端增加类别筛选、来源提示、状态按钮和任务跳转/事件跳转。
- [ ] 运行热点、任务、API、前端测试和构建。

### Task 9: 统一调度器并消除僵尸任务风险

**Files:**
- Modify: `backend/app/tasks/runner.py`
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/api/daily_hot_admin.py`
- Modify: `backend/tests/test_task_runner.py`
- Modify: `backend/tests/test_daily_hot_admin.py`

- [ ] 写重复启动只保留一个 scheduler/job 的失败测试。
- [ ] 写关闭、改间隔、读取 next_run 和恢复任务去重测试。
- [ ] 运行测试确认双调度器、`datetime.replace` 和重复查询问题。
- [ ] 管理 API 改为操作 `task_recovery_scheduler` 内的 job；修复恢复查询和幂等关闭。
- [ ] 运行 runner、scheduler、admin API 回归。

### Task 10: 全栈验证与最终报告

**Files:**
- Create: `docs/verification/2026-07-15-system-improvement-final-report.md`

- [ ] 运行完整后端 pytest，修复本轮相关失败并记录剩余既有问题。
- [ ] 运行前端 Vitest、typecheck 和生产构建，修复本轮引入问题。
- [ ] 启动前后端，检查 health、登录、热榜、手动详情抓取、事件详情、传播和生命周期接口。
- [ ] 检查 5000/8848 端口、Python/Node 进程、APScheduler job、任务表 pending/running 状态和线程名称。
- [ ] 亲自打开报告中列出的本地 URL 和数据样例，确认主流新闻、B 站评论、热点分类、虚假检测和 HDBSCAN 输出可供用户复核。
- [ ] 写最终报告：改动文件、测试命令与结果、真实网络限制、未解决问题、用户验证步骤。
