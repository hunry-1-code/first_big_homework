# 项目基础框架说明

本文档说明当前代码骨架如何把各功能板块连接起来。具体爬虫、清洗、NLP、LLM、报告生成和图表实现后续按模块补充。

## 1. 总体链路

```text
Vue 前端
  -> Axios API Client
  -> Flask Blueprint
  -> Service 层
  -> Model/Task/Analysis/Crawler/LLM 模块
```

后台耗时流程不在 HTTP 请求中直接跑完。API 只负责校验权限、创建任务、返回 `task_id`，实际流程由 `backend/app/tasks` 和服务层串起来：

```text
采集/导入 -> article.raw_content/raw_json
清洗 -> article.clean_content
分词/TF-IDF/聚合 -> event
LLM 情感/摘要/问答 -> report/qa_history
前端 -> 看板/详情/问答/个人中心/系统管理
```

## 2. 后端模块边界

| 模块 | 路径 | 后续负责人主要改哪里 |
| --- | --- | --- |
| API 接口 | `backend/app/api` | 请求参数、鉴权、响应格式 |
| 数据模型 | `backend/app/models` | SQLAlchemy 字段和关系 |
| 服务编排 | `backend/app/services` | 把 API、任务、模型和算法串起来 |
| 爬虫 | `backend/app/crawler` | 平台适配器、公开数据采集 |
| 清洗预处理 | `backend/app/preprocessing` | 正文提取、清洗、jieba 分词 |
| 分析算法 | `backend/app/analysis` | LDA、TF-IDF、聚合、趋势、风险 |
| LLM 接入 | `backend/app/llm` | DeepSeek/OpenAI 兼容客户端和 Prompt |
| 后台任务 | `backend/app/tasks` | APScheduler 定时任务和任务状态更新 |

## 3. 前端页面边界

| 页面 | 路由 | 作用 |
| --- | --- | --- |
| 登录 | `/login` | 获取 24 小时 JWT |
| 舆情看板 | `/` | 热点事件列表、搜索、关键词采集入口 |
| 事件详情 | `/events/:id` | 概述、趋势、情感、平台、关键词、报道列表 |
| 智能问答 | `/qa` | 调用问答接口 |
| 个人中心 | `/user` | 用户信息、关键词、数据源、本人任务 |
| 系统管理 | `/admin` | 管理员采集、JSON 导入、系统任务 |

## 4. 已预留接口

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/events`
- `GET /api/events/:id`
- `GET /api/events/search`
- `GET /api/events/:id/report`
- `GET /api/events/:id/report/export?format=html|pdf`
- `POST /api/qa/ask`
- `POST /api/qa/ask/stream`
- `GET /api/qa/history`
- `GET/PUT /api/user/profile`
- `GET/PUT /api/user/config`
- `GET /api/user/sources`
- `POST /api/crawler/trigger`
- `POST /api/crawler/search`
- `GET /api/crawler/status`
- `POST /api/import/json`
- `GET /api/tasks/:id`
- `GET /api/tasks/my`
- `GET /api/tasks`

除 `POST /api/auth/login` 外，业务接口均需要 JWT。`/api/crawler/trigger`、`/api/import/json`、`/api/tasks` 仅管理员可用。

## 5. 启动方式

后端：

```powershell
cd D:\111bighomework\first_big_homework\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

前端：

```powershell
cd D:\111bighomework\first_big_homework\frontend
npm install
npm run dev
```

默认登录账号：

```text
admin / admin123
```

## 6. 分工建议

1. 爬虫组实现 `backend/app/crawler`，输出字段必须满足 `data/samples/opinion_events.sample.json` 的格式。
2. 清洗组实现 `backend/app/preprocessing`，将 `raw_content` 转为 `clean_content`。
3. 算法组实现 `backend/app/analysis`，负责 TF-IDF、LDA、事件聚合、热度和生命周期。
4. LLM 组实现 `backend/app/llm` 和问答/情感/摘要调用，保留 SnowNLP 降级。
5. 前端组在 `frontend/src/views` 和 `frontend/src/components` 内替换占位展示，API 调用路径不要随意改。

## 7. 已实现的爬虫与预处理链路

当前已将原有占位实现替换为以下可运行模块：

```text
平台适配器
  -> RawDocument
  -> CrawlService 数量分配与错误汇总
  -> article + article_snapshot
  -> normalizer
  -> extractor（trafilatura -> readability -> BS4 -> fallback）
  -> cleaner
  -> quality
  -> deduplicator（SHA-256 + Jaccard + SimHash，BGE 保留边界状态）
  -> segmenter（jieba，失败时简单分词降级）
  -> document_features + processing_log
```

已实现的平台适配器：

- 百度千帆网页搜索、百度热搜。
- 知乎搜索、知乎热榜。
- B站公开视频搜索。
- 微博公开热搜。
- TikHub 微博、小红书、抖音关键词搜索。
- RSS/Atom 和本地样例适配器。

所有外部请求统一经过 `backend/app/crawler/http.py`，包含域名白名单、超时、429/5xx 最多三次指数退避，以及 401/403 立即停止。自动化测试使用本地假响应，不会消耗 TikHub 或千帆额度。

后台接口现已连接实际任务：

```text
POST /api/crawler/search
POST /api/crawler/trigger
POST /api/import/json
```

API 创建任务后由轻量线程池执行采集、预处理和持久化。测试环境可设置 `TASKS_RUN_SYNC=true`，便于同步验证；正常运行保持 `false`。

任务提交时会先原子领取数据库中的 `pending` 记录，并生成本次执行专属的 `lease_token`。执行线程按 `TASK_HEARTBEAT_INTERVAL_SECONDS` 更新任务心跳，所有状态更新都必须匹配当前租约；每篇文章的持久化事务还会锁定并校验对应任务行，任务被重新领取后，旧执行实例不能再提交文章或覆盖新状态。应用启动时和运行期间会定期扫描未领取任务及心跳超过 `TASK_RUNNING_TIMEOUT_SECONDS` 的中断任务，扫描周期由 `TASK_RECOVERY_SCAN_SECONDS` 控制。恢复时如果本地队列已满，任务继续保持 `pending`，等待下次扫描。相同用户在 `CRAWL_DUPLICATE_WINDOW_SECONDS` 时间窗内提交相同关键词、平台和数量时，会通过进程锁或 MySQL 命名锁原子复用已有任务，避免并发请求重复消耗外部接口额度。

旧版 MySQL 表结构迁移：

```powershell
cd D:\111bighomework\first_big_homework\backend
python migrations\migrate_crawler_preprocessing.py
```

迁移器会调用运行时的 `normalize_url` 后再生成 `url_hash`；不能直接执行迁移 SQL 文件。

## 8. 测试方式

```powershell
cd D:\111bighomework\first_big_homework\backend
python -m pip install -r requirements.txt

python tests\test_contracts.py -v
python tests\test_crawler_core.py -v
python tests\test_crawler_adapters.py -v
python tests\test_crawl_service.py -v
python tests\test_preprocessing.py -v
python tests\test_pipeline.py -v
python tests\test_persistence.py -v
python tests\test_jobs.py -v
python tests\test_crawler_api.py -v
python tests\test_migration.py -v
```

项目根目录公开入口探测工具测试：

```powershell
python -m unittest discover -s tests -v
```

当前没有对真实付费接口执行自动化请求。正式使用前应先在测试关键词上进行少量人工联调，并检查各平台返回结构是否发生变更。
