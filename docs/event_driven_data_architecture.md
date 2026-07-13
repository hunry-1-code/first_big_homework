# 事件驱动的舆情数据架构设计

## 一、核心原则

```
事件是主体，文章是证据。
先识别事件主题，再按主题采集证据，而非先采集再找事件。
```

| 原则 | 说明 |
|------|------|
| **事件优先** | Event 是第一公民。所有爬取、分析、展示都围绕 Event 展开 |
| **主题去重** | 不同来源对同一事件的不同表述，应在爬取前合并为同一主题 |
| **来源绑定** | 每篇文章记录其归属的爬取任务和触发主题 |
| **粒度一致** | 搜索分析、每日热点、手动导入统一走「主题 → 爬取 → 分析 → 事件」 |
| **生命周期** | 热点事件有 TTL，搜索事件可持久化，过期自动清理 |

## 二、统一数据模型

```
┌──────────────┐     1:N     ┌──────────────┐     N:1     ┌──────────────┐
│  CrawlTask   │ ─────────→  │   Article     │ ←─────────  │    Event     │
│              │             │               │            │              │
│ id           │             │ id            │            │ id           │
│ keyword      │             │ crawl_task_id │            │ title        │
│ source_type  │             │ event_id      │            │ source       │
│    search    │             │ platform      │            │   search     │
│    daily_hot │             │ title         │            │   daily_hot  │
│    manual    │             │ ...           │            │   manual     │
│ status       │             └──────────────┘            │ ttl_days     │
│ created_at   │                                         │ created_at   │
└──────────────┘                                         └──────────────┘
       │                                                        │
       │ 1:1                                                    │
       ▼                                                        │
┌──────────────┐                                               │
│  HotTopic    │  (仅 daily_hot)                                │
│              │                                               │
│ id           │                                               │
│ raw_title    │                                               │
│ merged_into  │──→ 同一事件的标题合并到这里                       │
│ crawl_task_id│──→ 对应的爬取任务                               │
│ event_id     │──→ 最终产生的事件 ◄─────────────────────────────┘
└──────────────┘
```

## 三、统一流程

### 3.1 搜索分析

```
用户输入关键词 → 创建 CrawlTask(source=search)
    ↓
多平台爬取 → Article(crawl_task_id=task.id)
    ↓
内容分析 → 事件聚合 → Event(source=search, ttl_days=null 永久)
    ↓
看板展示
```

### 3.2 每日热点

```
APScheduler 定时触发 daily_hot_job
    ↓
┌─ Step 1: 采集热榜标题 ──────────────────────────┐
│  微博热搜 + 百度热搜 + 知乎热搜 → 50 条原始标题    │
│  写入 HotTopic(status=raw)                       │
└─────────────────────────────────────────────────┘
    ↓
┌─ Step 2: LLM 主题聚合 ──────────────────────────┐
│  输入: 50 条 HotTopic 标题                        │
│  LLM 输出: [{canonical_name, merged_ids, keywords}] │
│  例: "现货黄金失守4040"+"金价跌破4000"+"黄金 创年内新低" │
│      → "国际金价大幅下跌"                          │
│  更新: HotTopic(merged_into=canonical_id)        │
└─────────────────────────────────────────────────┘
    ↓
┌─ Step 3: 按主题搜索爬取 ────────────────────────┐
│  对每个去重后的主题 (约 10-15 个)                   │
│  创建 CrawlTask(source=daily_hot, keyword=canonical_name) │
│  执行 search crawl                               │
│  Article(crawl_task_id=task.id)                  │
└─────────────────────────────────────────────────┘
    ↓
┌─ Step 4: 分析 + 聚合 ──────────────────────────┐
│  content_analysis → event_aggregation             │
│  → Event(source=daily_hot, ttl_days=7)           │
│  HotTopic(event_id=event.id)                     │
└─────────────────────────────────────────────────┘
    ↓
看板「今日热点」展示
```

### 3.3 手动导入

```
用户粘贴 JSON → 创建 CrawlTask(source=manual)
    ↓
Article(crawl_task_id=task.id)
    ↓
分析 → Event(source=manual, ttl_days=null)
```

## 四、数据隔离规则

| 规则 | 实现方式 |
|------|------|
| **爬取阶段** | `Article.crawl_task_id` 记录归属任务 |
| **分析阶段** | `create_analysis_run` 按 `crawl_task_id` 过滤，只取本任务文章 |
| **展示阶段** | 看板默认显示所有事件；daily_hot 事件可标记 `source` 区分 |
| **清理阶段** | 定时任务：`Event.ttl_days` 非空且 `created_at + ttl_days < now` → 删除事件及文章 |

## 五、LLM 主题聚合算法

### 输入

50 条 HotTopic 标题，每条格式 `{id, title, platform, rank}`

### 去重策略（两级）

**L1 — 快速语义去重（BGE 向量）**

```
对 50 条标题做 BGE embedding
→ 余弦相似度矩阵
→ 相似度 > 0.75 的标题对归入同一候选组
→ 连通分量 → 候选主题组
```

**L2 — LLM 精细合并（仅对 L1 边界模糊的组）**

```
L1 产生的候选组之间相似度 0.55-0.75 的边界案例
→ 送给 LLM 判断是否应合并
→ 提示词: "以下两组热榜标题是否描述同一事件？只需回答是或否。"
```

### 输出

每组合并后产生一个 TopicGroup：

```
{
  canonical_name: "国际金价大幅下跌",      // LLM 生成的规范名称
  keywords: ["黄金", "金价", "暴跌"],      // LLM 提取的关键词
  merged_hot_ids: [5, 12, 23],            // 合并的原始 HotTopic ID
  category: "经济与市场",                  // LLM 分类
  confidence: 0.92
}
```

## 六、存储变更

### 新增表

| 表 | 用途 |
|------|------|
| `hot_topic` | 热榜原始标题 + 去重状态 + 关联的 crawl_task 和 event |

### 修改表

| 表 | 新增列 | 用途 |
|------|------|------|
| `article` | `crawl_task_id` | 已加，记录爬取任务归属 |
| `event` | `source` | `search` / `daily_hot` / `manual`，区分事件来源 |
| `event` | `ttl_days` | 热点事件 7 天过期，搜索事件 null |

## 七、定时任务

| 任务 | 频率 | 功能 |
|------|:---:|------|
| `daily_hot_job` | 每 30 分钟 | Step 1-4 全流程：采集 → 去重 → 爬取 → 分析 |
| `cleanup_expired_events` | 每天凌晨 | 删除 `ttl_days` 到期的事件及关联文章 |
| `cleanup_failed_tasks` | 每天凌晨 | 清理超过 24h 的失败 enrichment 任务 |

## 八、可行性评估

| 维度 | 评估 |
|------|------|
| **代码改动量** | Article 表新增 1 列（已加），Event 表新增 2 列，新增 HotTopic 表。LLM 调用新增 1 次（每隔 30 分钟）。`create_analysis_run` 隔离逻辑已写完 |
| **LLM 成本** | 主题去重每次 ~50 标题，约 2000 tokens × 每日 48 次 ≈ 10 万 tokens/天 ≈ $0.02/天 |
| **性能影响** | BGE 向量计算 50 标题 ≈ 2 秒；LLM 调用边界判断约 3-5 秒；其余与现有流程相同 |
| **兼容性** | 搜索分析流程不变，仅增强数据隔离。daily_hot 改为主题聚合后每批 10-15 次 crawl（原来 50 次），反而减少 |
| **回滚** | 新增字段均为 nullable，不影响现有数据 |

---

> 设计时间：2026-07-14  
> 当前状态：Article.crawl_task_id 已实现。Event.source/ttl_days、HotTopic 表、LLM 主题聚合、定时清理待实现。
