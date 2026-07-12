# 网络舆情事件智能分析系统 - 智能开发规则

## 核心开发记忆

1. **前端工程架构**：基于 **Vue Pure Admin 7.0** 模板（Vue 3 + Vite 8 + TypeScript + Element Plus + Tailwind CSS 4 + Pinia 3 + ECharts 6），位于 `frontend/`。

2. **后端工程架构**：Flask + SQLAlchemy + JWT + DeepSeek LLM，位于 `backend/`。已实现爬虫/清洗/分析/聚合/情感/报告全链路。

3. **融合状态**：前后端已于 2026-07-12 完成合并（`branchhu` 分支），最新合并基点 `f7d5fe1` + `origin/main`。

4. **必读文档**（新会话启动必须按顺序阅读）：
   - `docs/integration_report.md` — 前后端融合全部改动记录（最重要）
   - `docs/backend_api_data_format.md` — 后端接口返回格式规范 + 差距标注
   - `docs/frontend_changelog_and_memory.md` — 前端变更日志完整记录
   - `docs/crawler_usage_guide.md` — 爬虫使用说明
   - `docs/backend_user_management_api_requirements.md` — 用户管理 API

5. **项目根目录结构**：
   ```
   frontend/     Vue Pure Admin 前端（端口 8848）
   backend/      Flask 后端（端口 5000）
   docs/         所有文档
   data/         样例数据 + 爬虫探测结果
   tests/        测试文件
   tools/        工具脚本
   ```

---

## AI 助手行为规则

### 开发前
1. **必须阅读** `docs/integration_report.md` 和 `docs/frontend_changelog_and_memory.md`
2. 所有前端修改必须在 Vue Pure Admin 风格体系内进行
3. 禁止引入新的 UI 样式库或修改核心布局

### 开发后
1. 更新 `docs/frontend_changelog_and_memory.md`
2. `git commit`（commit message 用中文描述 + Co-Authored-By: Claude）

---

## 关键约定

### 命名规范
| 事项 | 约定 |
|------|------|
| 生命周期 | `潜伏期` `成长期` `高潮期` `消退期`（不是"爆发期"） |
| 情感标签 | `正面` `中立` `负面`（不是"中性"） |
| 7 平台中文名 | `微博热搜` `微博搜索` `知乎` `B站` `小红书` `百度热搜` `百度搜索` |
| 后端英文代码→中文 | 通过 `constants/platforms.ts` 的 `resolvePlatformName()` 转换 |
| 响应格式 | `{code: 200, message: "success", data: {...}}` |
| 用户名规则 | `[A-Za-z0-9_-]{3,50}` |
| 密码规则 | 6-128 位 |

### 端口与代理
- 前端开发：`localhost:8848`
- 后端：`localhost:5000`
- Vite 代理 `/api` → `http://127.0.0.1:5000`

### 默认账号
- `admin / admin123`（首次登录自动播种，role=admin）

### 路由结构
```
📊 舆情分析系统（rank 1）
├── /dashboard     舆情看板
├── /events/:id    事件详情（隐藏菜单）
├── /qa            智能问答
├── /user          个人中心
└── /admin         运维管理（admin only）

⚙️ 系统管理（rank 99, admin only）
├── /system/users   用户管理
└── /system/events  事件管理
```

### 权限体系
- 路由级：`meta.roles: ["admin"]` → `filterNoPermissionTree` 过滤菜单
- 守卫级：`router/index.ts` line 154 拦截直接 URL 访问 → 403
- 后端：`@admin_required` 装饰器

---

## 已知问题与提醒

1. **`python run.py` 不要反复启动**：`debug=True` 的 reloader 会产生僵尸子进程堆积端口 5000。建议 `debug=False`。
2. **端口冲突**：如 5000 端口被占，`Get-Process python* | Stop-Process -Force` 清理。
3. **百度千帆 DNS**：`api.qianfan.baidubce.com` 不存在（正确域名是 `qianfan.baidubce.com`，代码已修复）。
4. **抖音 403、小红书空数据**：第三方平台已知限制，非代码问题。
5. **`.env` 不能提交 Git**：API Key 敏感信息。
6. **前端包体积**：~15.6 MB（清理后从 25 MB 减少了 37%）。
7. **事件详情`summary`为 None**：后端报告生成模块部分实现，`overview_text` 和 `summary` 可能为空。
8. **关键词为空**：小数据量测试时后端关键词接口返回空数组，正常现象。
9. **BGE 模型已安装**：`sentence-transformers==5.5.1`，首次运行需下载 `BAAI/bge-small-zh-v1.5`（~400MB），国内需 `HF_ENDPOINT=https://hf-mirror.com`。
10. **聚合阈值已调优**：`attach_threshold=0.55`、`bge_weight=0.55`（默认值在 `config.py`）。
11. **前端 Mock 数据已全部清理**：传播图/情感趋势/平台Badge/影响排行/趋势模拟 均使用后端真实数据。
12. **路由新增**：`/analysis` 事件定向分析页已注册。

---

## 开发日志

### 2026-07-13 会话

| 时间 | Commit | 内容 |
|------|--------|------|
| 01:40 | `5292627` | **feat**: 新增事件定向分析页面 `/analysis`（平台卡片选择 + el-steps 进度 + 2s 轮询）。修复 crawl_service 空平台 Bug、tasks/jobs 平台传递、event_service keywords。 |
| 02:30 | `28738a5` | **debug**: 全链路端到端测试脚本。59 篇真数据从百度/B站/微博/知乎爬取，BGE 向量失败（缺依赖+墙）。 |
| 02:55 | `d7f4b1e` | **fix**: 聚合阈值调优 `attach_threshold 0.72→0.55`、`bge_weight 0.45→0.55`。40 个孤簇 → 3 个有意义事件（34+13+1）。`.env` 加 `HF_ENDPOINT` 镜像。 |
| 03:10 | `ace41cb` | **fix**: 清理前端 6 处 Mock 数据。传播图接入 `/propagation` API+force 布局、情感趋势用 `daily_trend`、平台 Badge 从 API 读、影响排行去噪声、趋势不模拟。tikhub 爬虫加 `_strip_html()`。config.py 阈值默认值更新。 |
| 03:12 | `a6f2792` | **fix**: EventCard.vue 缺 `getPlatform`/`resolvePlatformName` import 导致页面崩溃。 |
| 03:15 | `87a0f66` | **fix**: `getSentimentAreaOption` 函数提取时残留 `});` 语法错误。 |
| 03:25 | `fef3b26` | **feat**: AI 元数据全补全。`_extract_location`/`_extract_key_figures`/`_extract_cause` 从文章聚合。`_postprocess_published_event` 加基础热度公式。传播阈值 `_SIMILARITY_MIN 0.12→0.05`。 |
| 03:45 | `0565b83` | **fix**: 传播图 category 字符串→数字映射。词云权重 max-normalize。`_cluster_title()` 标题截断 ≤80 字。文章正文 tooltip 截断 150 字 + `line-clamp-2`。 |
| 04:00 | `0ce0ca6` | **docs**: integration_report.md 新增第十八章（全链路调试记录）。 |

### 最终状态

- **全链路打通**：爬虫→预处理→内容分析(TF-IDF+BGE)→事件聚合→情感分析(LLM)→前端看板
- **事件数**：3 个（34篇+13篇+1篇），覆盖百度/B站/微博/知乎
- **API 字段**：30/30 全部对齐
- **前端 Mock**：0 处残留

---

## 依赖安装

```powershell
# 后端
cd backend
pip install -r requirements.txt
# 注意：sentence-transformers 可能编译失败，不影响核心功能（设置 BGE_ENABLED=false）

# 前端
cd frontend
npm install
```
