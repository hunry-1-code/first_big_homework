# 舆情系统跨模块工作流修复设计

## 目标

修复真实流程中“搜索聚类发布为正式事件”后的派生数据断链，并完成事件问答、报告和 SQLite 后台任务稳定性，使系统按“采集→清洗→内容分析→聚合→情感/热点→正式事件→趋势/溯源/报告/问答”闭环运行。

## 方案选择

采用“发布编排器 + 可重复派生计算”方案。`publish_cluster` 只负责原子地建立正式事件和文章归属；提交成功后由统一编排服务补齐情感、热度和报告。每个步骤必须幂等，失败只记录警告，不回滚已经成功的事件发布，并允许重试。

相比直接复制搜索快照，本方案优先创建正式 `publish/global` 情感运行：文章级结果可复用缓存，但事件快照按正式事件重新聚合，保证 `event_id`、权重和当前摘要一致。热点运行按同一 `analysis_run_id` 查找已有主题结果并重新执行热度收尾。若没有热点主题，跳过而不是伪造热点。

## 数据流

1. 发布搜索聚类并提交正式 Event、Article.event_id、membership 和 publish aggregation run。
2. 创建并执行该 publish aggregation run 对应的 global sentiment run，更新 Event 当前情感快照。
3. 查找同 analysis run 的成功 hotspot run，重新计算事件热度并移除 `EVENT_AGGREGATION_PENDING`。
4. 生成并持久化 Report；概述优先使用事件摘要，否则由标题、规模、平台、情感和风险生成确定性概述。
5. QA 根据 event_id 读取事件详情、文章摘要、情感、趋势和风险，调用现有 OpenAI-compatible LLM；无 key 或调用失败时返回明确的降级回答和 warning，不再返回占位文案。

## 一致性与错误处理

- 发布本身与派生计算分事务，避免外部 LLM 调用占用发布事务。
- 重复发布复用同一事件，并再次检查缺失派生数据。
- 派生步骤逐项捕获异常，响应包含 `postprocess` 状态及 warnings，便于重试和诊断。
- SQLite 同步执行模式不启动独立心跳写线程；任务本身的阶段更新已承担活跃证明，避免同库并发写锁。异步/生产数据库继续使用心跳线程。

## 验收

- 发布后 `/events/:id/sentiment` 不再返回 `SENTIMENT_SNAPSHOT_UNAVAILABLE`。
- 已有热点主题时，发布后 heat 状态可完成且 Event 有热度快照。
- 报告 overview 非空，导出 HTML 包含有效事件内容。
- QA 的响应标记 `method=llm`，并包含真实模型名；故障时标记 fallback 和 warning。
- 重复发布、重复后处理不产生重复 Event。
- 单元/集成测试通过，并至少执行三轮真实顺序工作流。
