# 网络舆情事件智能分析系统

本仓库是课程大作业的基础框架，已按 `项目需求规格说明书.md` 搭好前后端目录、接口边界、服务层、任务层和前端页面。复杂功能先保留稳定接口，后续按模块分工实现。

## 当前包含

- `backend/`：Flask API、SQLAlchemy 模型、JWT 鉴权、管理员权限、后台任务占位。
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

## 后续实现入口

- 爬虫：`backend/app/crawler`
- 清洗和分词：`backend/app/preprocessing`
- 事件聚合和分析：`backend/app/analysis`
- LLM：`backend/app/llm`
- 报告：`backend/app/services/report_service.py`
- 前端页面：`frontend/src/views`、`frontend/src/components`
