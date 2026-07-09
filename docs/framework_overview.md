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
