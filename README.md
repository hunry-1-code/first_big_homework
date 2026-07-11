# 网络舆情事件智能分析系统

本仓库是课程大作业工程，已按 `项目需求规格说明书.md` 搭好前后端框架，并实现第一版爬虫与数据清洗预处理链路。

## 当前包含

- `backend/`：Flask API、SQLAlchemy 模型、JWT 鉴权、数据库后台任务、平台采集适配器和数据预处理管线。
- `frontend/`：Vue 3、Pinia、Vue Router、Element Plus 页面骨架。
- `data/samples/`：JSON 样例数据导入格式。
- `docs/framework_overview.md`：模块连接方式和分工说明。

## 快速启动

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

首次启动会在已存在的数据库中创建缺失表。MySQL 数据库本身需要提前创建；已有旧版表结构时应先备份并在 `backend` 目录执行 `python migrations\migrate_crawler_preprocessing.py`，或重建开发数据库。不要直接执行迁移 SQL，因为 Python 迁移器负责按运行时规则规范化旧 URL。

前端：

```powershell
cd frontend
npm install
npm run dev
```

默认管理员账号：

```text
admin / admin123
```

## 主要页面

- `/login`：登录页。
- `/`：舆情事件看板。
- `/events/:id`：事件详情报告。
- `/qa`：智能问答。
- `/user`：个人中心。
- `/admin`：系统管理，仅管理员可见。

## 模块入口

- 爬虫：`backend/app/crawler`，已实现千帆、知乎、B站、微博热搜、TikHub、RSS 和样例适配器。
- 清洗和分词：`backend/app/preprocessing`，已实现标准化、四级提取、清洗、质量、去重、jieba 和管线编排。
- 事件聚合和分析：`backend/app/analysis`
- LLM：`backend/app/llm`
- 报告：`backend/app/services/report_service.py`
- 前端页面：`frontend/src/views`、`frontend/src/components`
