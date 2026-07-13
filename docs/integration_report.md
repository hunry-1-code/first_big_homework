# 前后端融合改动报告

融合基点：`f7d5fe1`（前端路由重构+死代码清理后的纯净 Vue Pure Admin 前端）
后端基代码：`origin/main`（后端团队完整 Flask 实现，含爬虫/分析/LLM/聚合/情感全链路）
融合时间：2026-07-12 ~ 2026-07-13

---

## 一、融合过程

### 1.1 Merge 冲突解决

```
git merge origin/main → 4 个冲突文件
```

| 文件 | 冲突原因 | 解决方案 |
|------|----------|----------|
| `backend/app/services/event_service.py` | 我们：旧 mock 数据 / 后端：真实 DB 实现 | 使用后端真实实现 |
| `frontend/src/api/events.ts` | 我们：TS 格式 / 后端：JS 格式，新增 getEventPropagation | 合并双方，保留 TS + 新函数 |
| `frontend/src/styles.css` | 我们已删 / 后端修改过 | 保持删除（我们用 Tailwind） |
| `frontend/src/views/DetailView.vue` | 我们已删 / 后端修改过 | 保持删除（我们有 events/detail.vue） |

### 1.2 命名对齐

后端内部用英文代码（`weibo`/`zhihu`），前端用中文名（`微博热搜`/`知乎`）。API 契约层 `api_contract_service.py` 负责转换。

**冲突修正**：
- `api_lifecycle_stage`：后端原映射 `高潮期→爆发期`，改为保持 `高潮期`（与 PPT 源材料一致）
- 前端同步改名：`爆发期→高潮期`、`中性→中立`
- 前端 `constants/platforms.ts` 新增 `resolvePlatformName()` 转换器

---

## 二、数据库配置

| 阶段 | 数据库 | 问题 | 解决 |
|------|--------|------|------|
| 初始 | MySQL | FK 类型不匹配（BIGINT vs INTEGER） | 9 个模型文件统一为 `db.Integer` |
| 测试 | SQLite | `.env` 默认配置 | 直接使用 |
| 生产 | 用户本地 MySQL | `root:060422@localhost` | 按需切换 |

---

## 三、登录与认证体系

### 3.1 登录流程

```
POST /api/auth/login → Flask auth.py → DB 查询 → PBKDF2 验证 → JWT 签发
```

- 首次登录自动播种 admin 用户
- 支持数据库多用户登录（非硬编码）
- Token 24 小时有效，存入 Cookie + localStorage

### 3.2 登录页改动

| 删除 | 保留/新增 |
|------|-----------|
| 手机登录 | 账号密码登录 |
| 二维码登录 | 忘记密码 |
| 第三方登录（QQ/微信/支付宝/微博） | 注册（对接真实 API） |
| 国际化切换下拉 | 主题切换 |

### 3.3 注册功能

- 新增后端 `POST /api/auth/register` 公开端点
- 登录页注册表单对接真实 API
- 校验规则：用户名 `[A-Za-z0-9_-]{3,50}`，密码 6-128 位

### 3.4 密码校验修复

- 删除登录页 `REGEXP_PWD` 严格正则（要求 8-18 位混合字符），改为仅非空校验
- 后端做实际密码验证，前端不做复杂度拦截

---

## 四、用户管理模块

### 4.1 后端接口

后端已实现全部 6 个管理员接口：

```
GET    /api/admin/users         分页/搜索/筛选
POST   /api/admin/users         创建用户
PUT    /api/admin/users/{id}    编辑用户
PUT    /api/admin/users/{id}/password  重置密码
DELETE /api/admin/users/{id}    删除用户
GET    /api/admin/roles         角色列表
```

### 4.2 前端页面

- 新建 `views/admin/users.vue`，路由 `/system/users`
- 表单项校验：用户名正则、密码长度
- 批量生成账户：可配置前缀/数量/起始编号/角色/密码
- 自动生成 8 位随机密码（无歧义字符）
- 结果表格显示成功/失败明细
- 日期格式化：ISO → `yyyy-MM-dd HH:mm:ss`

### 4.3 权限分级

三层防护全部到位：
1. **路由 meta**：`roles: ["admin"]`
2. **菜单过滤**：`filterNoPermissionTree` 自动隐藏
3. **路由守卫**：非 admin 直接访问 → 403

---

## 五、侧边栏与路由

### 5.1 路由结构

```
📊 舆情分析系统
├── 舆情看板      /dashboard
├── 智能问答      /qa
├── 个人中心      /user
└── 运维管理      /admin      ← 爬虫/导入/任务（admin only）

⚙️ 系统管理                    ← admin only
├── 用户管理      /system/users
└── 事件管理      /system/events  ← 新增
```

### 5.2 RouterArrays 修复

`layout/types.ts` 硬编码 `/welcome` → 改为 `/dashboard`

### 5.3 幽灵菜单修复

根因：`mock/asyncRoutes.ts` 被 `vite-plugin-fake-server` 加载，返回旧模板路由。
修复：清空 mock 数据数组 + `initRouter` 添加 `.catch()` 处理。

---

## 六、事件详情页增强

### 6.1 可视化组件

| 组件 | 类型 | 位置 |
|------|------|------|
| 生命周期指示器 | 4 阶段彩色步骤条 | 页面标题下方 |
| 趋势图 | 报道量折线 + 情感堆叠面积图（双图） | 全宽卡片 |
| 情感饼图 | 环形图 + 中心文字 | 三列左 |
| 平台分布 | 横向品牌色柱状图 + 图标标签行 | 三列中 |
| 风险雷达图 | 6 维度 ECharts Radar | 三列右 |
| 传播路径图 | 5 层手工布局 + 缩放按钮 | 全宽卡片 |
| 关键事件时间轴 | 自定义 CSS Timeline | 半宽 |
| 报道影响力排行 | 横向柱状图 | 半宽 |
| 词云 | echarts-wordcloud + 8 形状选择 | 宽卡片 |

### 6.2 智能提问入口

- 页面顶部标题栏主按钮
- AI 研判卡片底部入口 + 温馨提示

### 6.3 生命周期指示器

三态设计：
- 已完成：Tailwind 50 级淡色底 + 彩色字 + 边框
- 当前：实心品牌色 + 白色粗体
- 未到达：灰字灰点，可见不刺眼

### 6.4 报道列表增强

新增列：作者、发布时间、互动量（转发/评论/点赞）

---

## 七、平台体系

### 7.1 7 平台配置

`constants/platforms.ts`：微博热搜/微博搜索/知乎/B站/小红书/百度热搜/百度搜索

每个平台含：name / short / color / bg / api / icon

### 7.2 官方图标

从已安装的 `@iconify/json` 中注册：
- `ant-design:weibo-circle-filled`
- `ant-design:zhihu-circle-filled`
- `ant-design:bilibili-filled`
- `ant-design:baidu-outlined`
- `simple-icons:xiaohongshu`

### 7.3 统一展示

所有平台出现位置统一 `图标 + 品牌色`：
- EventCard 信源标签
- 报道列表平台列
- 平台分布图标签行 + y 轴颜色
- QA 平台选择器下拉选项

### 7.4 英文→中文转换

后端返回英文代码时，`resolvePlatformName()` 自动转换。映射表：

```
weibo/weibo_hot → 微博热搜
weibo_search → 微博搜索
zhihu/zhihu_hot → 知乎
bilibili → B站
xiaohongshu → 小红书
baidu/baidu_news/rss → 百度搜索
baidu_hot → 百度热搜
```

---

## 八、账户设置

### 8.1 头像系统

- 新建 `utils/avatar.ts`：用户名 hash → 15 色选 1 + 中文末字/英文首字母
- SVG data URI 格式，零网络请求
- navbar + 账户设置侧边栏 + Profile 页三处统一

### 8.2 Profile 页面对接

- 对接 `GET/PUT /api/user/profile`
- 仅展示后端支持字段：用户名（只读）、昵称（可编辑）、角色（只读）
- 头像上传标记为"即将上线"

### 8.3 其他 Tab 清理

偏好设置/安全日志/账户管理 → "功能开发中"占位

---

## 九、通知与导航栏

### 9.1 通知铃铛

清空全部 mock 消息和待办数据，改为空状态"暂无通知/暂无消息"

### 9.2 导航栏

- 删除国际化翻译切换下拉
- `t()` 调用替换为中文硬编码
- 页脚版权改为"网络舆情事件智能分析系统"
- 系统标题改为"舆情分析系统"

---

## 十、事件管理页

新建 `views/admin/events.vue`，三个 Tab：

| Tab | 功能 |
|-----|------|
| 正式事件 | 搜索/分页/批量选择/批量删除/单行删除 |
| 事件簇 | 查看聚合运行 → 发布事件簇为正式事件 |
| 合并候选 | 相似度审查 → 确认合并 / 拒绝 |

后端新增 `DELETE /api/events/:id` 接口。

---

## 十一、QA 智能问答

- 新增平台选择器（7 平台下拉）
- 选中平台后自动注入 `[聚焦平台：XXX]` 前缀
- 详情页跳转自动携带 `event_id` + `platform` 参数

---

## 十二、爬虫测试

### 12.1 环境准备

- `.env` 配置 API Key（千帆/知乎/TikHub/DeepSeek）
- `TASKS_RUN_SYNC=true` 同步模式便于调试
- `BGE_ENABLED=false` 使用 TF-IDF

### 12.2 测试结果

| 平台 | 关键词搜索 | 热榜 | 备注 |
|------|:--:|:--:|------|
| 知乎 | ✅ | ✅ | |
| 微博 | ✅ | ✅ | |
| B站 | ✅ | — | DNS 恢复后可用 |
| 百度 | ✅ | — | |
| 小红书 | 🟡 | — | 接口成功但无数据 |
| 抖音 | ❌ | — | HTTP 403 |

全链路验证：爬虫→清洗→分析→聚合→情感→事件生成，25+ 正式事件发布。

### 12.3 DNS 问题

VPN 断开后 DNS 残留 `10.3.9.x`：
- `api.qianfan.baidubce.com` 不存在（代码实际用 `qianfan.baidubce.com`）
- B站 DNS 被劫持到 `198.18.x`（重启后恢复）
- 解决：WLAN 属性改 DNS 为 `8.8.8.8` 或重启电脑

---

## 十三、Mock 数据清理

| 文件 | 处理 |
|------|------|
| `mock/asyncRoutes.ts` | 返回空数组 |
| `mock/system.ts`（1815 行） | 删除 |
| `mock/list.ts`（457 行） | 删除 |
| `mock/map.ts`（43 行） | 删除 |
| `mock/admin.ts` | 删除（真实后端接管） |
| `mock/login.ts` | 保留（但实际未被使用） |
| `mock/refreshToken.ts` | 保留 |
| `mock/mine.ts` | 保留 |

---

## 十四、项目文件整理

| 操作 | 文件 |
|------|------|
| 🔴 删除 | 根目录 `.env`（含 API Key，移至 `backend/.env`） |
| 🔴 删除 | `README_后端方案.md`（已过时） |
| 📁 移动 | `crawl_probe_results.*` → `data/` |
| 📁 移动 | `crawl_live_validation_results*.json` → `tests/` |
| 📁 移动 | `参考项目分析*.md`、`技术选型详解.md`、`项目需求规格说明书.md`、`后端系统现状与接口说明.md` → `docs/` |
| ✅ 保留 | 根 `package.json`（echarts-wordcloud 依赖） |

---

## 十五、文档产出

| 文档 | 路径 | 用途 |
|------|------|------|
| 后端 API 数据格式 | `docs/backend_api_data_format.md` | 后端接口字段规范 + 差距标注 |
| 后端用户管理 API 需求 | `docs/backend_user_management_api_requirements.md` | admin CRUD 接口需求 |
| 爬虫使用指南 | `docs/crawler_usage_guide.md` | 爬虫操作手册 |
| 前后端融合报告 | `docs/integration_report.md` | 本文档 |
| 前端变更日志 | `docs/frontend_changelog_and_memory.md` | 持续更新的前端改动记录 |

---

## 十六、注意事项

1. **不要用 `debug=True` + reloader 反复启动** → 会产生僵尸子进程堆积端口
2. **`.env` 不能提交 Git** → 已在 `.gitignore` 中
3. **端口**：前端 8848，后端 5000。前端 `/api` 代理到后端
4. **启动顺序**：先 `python run.py` 再 `npm run dev`
5. **默认账号**：`admin / admin123`（首次登录自动播种）
6. **平台名必须用 7 个中文名之一**，英文代码通过 `resolvePlatformName()` 转换
7. **生命周期四选一**：潜伏期/成长期/高潮期/消退期
8. **情感标签**：正面/中立/负面（不是"中性"）
9. **`python run.py` 用 `debug=False`** 避免 reloader 僵尸进程

---

## 十七、事件定向分析功能（2026-07-13）

### 17.1 问题诊断

前端看板搜索实际为**空操作**——`searchCrawler()` 只传 `keyword`，不传 `platforms`。后端 `crawl_service.py` 中 `if platforms is not None` 判断将空数组 `[]` 当作"用户显式指定空平台"而非"未指定"，导致搜索模式不调用任何爬虫，链路完全断裂。

### 17.2 修复清单

| # | 文件 | 类型 | 说明 |
|---|------|:---:|------|
| 1 | `backend/app/services/crawl_service.py:27` | 🔧 Bug 修复 | `if platforms is not None:` → `if platforms:`，空数组走默认选择全部搜索爬虫 |
| 2 | `backend/app/tasks/jobs.py:290` | 🔧 Bug 修复 | 搜索模式下 `platforms=platforms or []` → `effective_platforms = platforms or list(batch.platform_counts.keys())`，将爬虫实际使用的平台传给下游分析 |
| 3 | `backend/app/services/event_service.py` | 🔧 数据补全 | 新增 `_event_keywords()` 函数，从 `AnalysisRunArticle.keywords` 聚合事件关键词（之前硬编码空数组） |
| 4 | `frontend/src/constants/platforms.ts` | ✨ 新增 | `SEARCH_PLATFORMS` 配置——6 个搜索平台映射（B站/百度/知乎/微博/小红书/抖音），含 `always` 标识和 `needKey` 提示 |
| 5 | `frontend/src/api/crawler.ts` | ✨ 增强 | `searchCrawler(keyword, platforms?, targetCount?)` 支持可选平台和采集量参数 |
| 6 | `frontend/src/views/analysis/index.vue` | ✨ 新页面 | **事件定向分析页**：平台卡片多选 + el-steps 进度 + el-result 结果 + el-descriptions 摘要 + 2s 轮询 |
| 7 | `frontend/src/router/modules/opinion.ts` | ✨ 路由 | 注册 `/analysis` 路由，icon `ep:search`，标题"事件分析" |
| 8 | `frontend/src/views/welcome/index.vue` | ✨ 入口 | 搜索栏旁增加"新建事件分析 →"引导按钮 |

### 17.3 新页面架构

```
/analysis (EventAnalysis)
├── ① 分析配置卡片
│   ├── 关键词输入 (el-input)
│   ├── 平台卡片选择 (SEARCH_PLATFORMS 网格, 点击切换)
│   ├── 采集数量滑块 (el-slider, 10-200)
│   └── 开始/重置按钮
├── ② 分析进度卡片 (v-if="state==='running'")
│   ├── el-steps (4阶段: 爬取→内容分析→事件聚合→情感分析)
│   ├── el-progress (百分比)
│   └── 状态消息
├── ③ 分析结果卡片 (v-if="state==='completed'")
│   ├── el-result (成功/失败图标+标题)
│   └── el-descriptions (采集数/处理数/平台/状态)
└── ④ 历史任务 (TaskList 组件)
```

### 17.4 状态机

```
idle → startAnalysis() → running (2s 轮询 GET /api/tasks/:id)
  ├─ task.status=success → completed (el-result 成功)
  ├─ task.status=failed  → failed (el-result 失败)
  └─ 命中缓存           → completed (跳过采集)
```

### 17.5 模板资源复用

| 组件 | 来源 | 用途 |
|------|------|------|
| `el-result` | Element Plus | 完成/失败结果展示（参照模板 `views/result/success.vue`） |
| `el-steps` | Element Plus | 流水线阶段指示器 |
| `el-descriptions` | Element Plus | 分析结果数据摘要 |
| `PureDescriptions` | `@pureadmin/descriptions` | 已全局注册，备用 |
| `PlusCheckCardGroup` | `plus-pro-components` | 已安装，备用平台选择方案 |
| `TaskList` | 项目组件 | 历史任务表格 |

### 17.6 全链路调试发现

针对"台风巴威"关键词执行全链路真实采集+分析：

| 阶段 | 结果 | 详情 |
|------|:---:|------|
| 爬虫 | ✅ 59篇 | 百度17 + B站17 + 微博15 + 知乎10（抖音403，小红书空响应） |
| 预处理 | ✅ 46篇成功 | 78% 清洗成功率，13篇失败 |
| 内容分析 | ✅ 运行 | TF-IDF + BGE embedding 完成 |
| 事件聚合 | ⚠️ 待诊断 | 聚合运行成功但 Event 表暂未产出事件，需进一步排查 |
| 情感分析 | ✅ 45篇 | LLM (DeepSeek) 成功标注情感标签 |

### 17.7 前后端对齐差距

| 前端详情页使用的数据 | 后端实际提供 | 差距 |
|------|:---:|------|
| 基础字段 (title/heat/lifecycle/sentiment) | ✅ | 完全对齐 |
| trend.dates/counts/key_points | ✅ | 完全对齐 |
| platform.platforms | ✅ | 完全对齐 |
| articles.articles (含 sentiment_label) | ✅ | 完全对齐 |
| report.overview_text | ✅ | 完全对齐 |
| report.risk_data | ✅ | 完全对齐 |
| keywords.keywords | ✅ (修复后) | 修复前为空数组 |
| 传播图谱 (propagation) | ✅ | **前端未接入**，用硬编码假数据 |
| 情感趋势 (sentiment.daily_trend) | ✅ | **前端未接入**，用 sin/cos 模拟 |
| 情感堆叠面积图数据 | ✅ | **前端未接入**，全量模拟 |
| AI 元数据 (time/location/figures/cause) | ❌ | Event 表缺字段，前端显示"待后端录入" |

---

## 十八、全链路调试与修复（2026-07-13 第二阶段）

### 18.1 聚类碎片化问题

**现象**：59 篇文章聚类出 40 个事件簇，其中 35 个只有 1 篇文章。

**根因链**：
1. `sentence-transformers` 未安装 → BGE 语义向量全部失败
2. HuggingFace 被墙 → 模型无法下载
3. 仅靠 TF-IDF 向量聚类，相似度不足以突破 `attach_threshold=0.72`
4. 最终分值 ~0.60-0.65，永远达不到 0.72

**修复**：
- `pip install sentence-transformers` + `.env` 加 `HF_ENDPOINT=https://hf-mirror.com`
- `config.py` 默认阈值：`attach_threshold 0.72→0.55`，`bge_weight 0.45→0.55`
- 效果：40 个孤簇 → **3 个有意义事件**（34+13+1），45/48 篇文章正确归入

### 18.2 搜索链路修复

- `crawl_service.py:27`：`if platforms is not None` → `if platforms`
- `tasks/jobs.py:290`：`effective_platforms = platforms or list(batch.platform_counts.keys())`
- `event_service.py`：新增 `_event_keywords()` 从 `AnalysisRunArticle` 聚合真实关键词

### 18.3 前端 Mock 数据清理

| 组件 | 修复前 | 修复后 |
|------|------|------|
| 传播网络图 | `buildPropagationData()` 硬编码 14 个假节点 | 调用 `/propagation` API + force 布局 |
| 情感趋势图 | sin/cos 模拟曲线 | `sentiment.daily_trend` 真实数据 |
| 平台 Badge | `eventId % 3` 随机 | `event.platforms` 真实平台名 |
| 影响排行 | `Math.random()` 加噪声 | 真实互动数据 |
| 趋势曲线 | 数据 <7 点就模拟 14 天 | `getEnrichedTrend()` 只用真实数据 |
| 词云 | 权重归一化 sum=1 导致全等 | max-normalize 保留差异 |

### 18.4 数据质量修复

| 问题 | 根因 | 修复 |
|------|------|------|
| 事件标题 HTML/URL 乱码 | TikHub 微博爬虫 `_map_item` 未清洗 HTML | 新增 `_strip_html()` |
| 标题过长（154 字） | 微博文章全文当标题 | `_cluster_title()` 截断 ≤80 字 |
| AI 元数据 "待后端录入" | `get_event_detail` 未填充 | `_extract_location`/`_extract_key_figures`/`_extract_cause` |
| heat=0 | 搜索模式不走热点计算 | `_postprocess_published_event` 加基础热度公式 |
| 传播图仅 2 条边 | `inferred_score` 阈值 0.38 | 降至 0.15 + category 修复为数字索引 |
| 文章正文 tooltip 溢出 | `show-overflow-tooltip` 显示全文 | 截断至 150 字 + CSS `line-clamp-2` |

### 18.5 最终全链路结果

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| 爬取 | 0 篇（链路断裂） | 59 篇（百度17+B站17+微博15+知乎10） |
| BGE 向量 | 0 | 48 个（512 维） |
| 事件数 | 0 | 3 个（34+13+1） |
| 关键词 | 空数组 | 30 词/事件 |
| API 字段完整度 | 25/30 | 30/30 |
| 标题乱码 | 3/3 | 0/3 |
| 前端 Mock | 8 处 | 0 处 |

### 18.6 CI/CD 注意事项

1. **`sentence-transformers` 已在 `requirements.txt`**，首次运行需下载 BGE 模型（~400MB），国内需配 `HF_ENDPOINT=https://hf-mirror.com`
2. **BGE 在 CPU 上 ~3.7 秒/篇**，49 篇约 3 分钟
3. **DeepSeek LLM API Key 必须配置**，否则情感分析降级 SnowNLP
4. **抖音/小红书暂不可用**，不影响百度/B站/微博/知乎
5. **搜索模式需手动 publish 事件簇**，不会自动创建 Event

### 18.7 待解决问题

| 问题 | 影响 | 建议 |
|------|------|------|
| `analysis/index.vue` 未上线验证 | 新功能不可见 | 启动前端测试 |
| 搜索模式不触发热点计算 | 热度排名缺失 | publish 后自动创建 hotspot_run |
| `TASKS_RUN_SYNC=true` 不适合生产 | 单次调用可能数分钟 | 生产改 false，前端轮询 |

---

## 十九、开发日志（2026-07-13）

| # | Commit | 时间 | 内容 |
|:---:|--------|------|------|
| 1 | `5292627` | 01:40 | **feat**: 新增事件定向分析页 `/analysis`。修复 crawl_service 空平台 Bug、tasks/jobs 平台传递链路、event_service keywords 硬编码空数组。前端 SEARCH_PLATFORMS 常量 + el-steps 进度 + 2s 轮询。 |
| 2 | `28738a5` | 02:30 | **debug**: 全链路端到端测试脚本。59 篇真实数据从百度/B站/微博/知乎爬取。BGE 向量失败（`sentence-transformers` 未安装 + HuggingFace 被墙）。 |
| 3 | `d7f4b1e` | 02:55 | **fix**: 聚合阈值调优。`attach_threshold 0.72→0.55`、`bge_weight 0.45→0.55`。40 个孤簇 → 3 个事件（34+13+1 篇）。`.env` 加 `HF_ENDPOINT` 镜像。 |
| 4 | `ace41cb` | 03:10 | **fix**: 清理前端 6 处 Mock。传播图 API+force 布局、情感趋势 `daily_trend`、平台 Badge 读 API、影响排行去噪声、趋势不模拟。tikhub 爬虫加 `_strip_html()`。config.py 阈值默认值更新。 |
| 5 | `a6f2792` | 03:12 | **fix**: EventCard 缺 `getPlatform`/`resolvePlatformName` import，页面崩溃。 |
| 6 | `87a0f66` | 03:15 | **fix**: `getSentimentAreaOption` 提取时残留 `});` → 编译错误。 |
| 7 | `fef3b26` | 03:25 | **feat**: AI 元数据全补全（`_extract_location`/`_extract_key_figures`/`_extract_cause`）。publish 后加基础热度公式。传播阈值 `_SIMILARITY_MIN 0.12→0.05`。 |
| 8 | `0565b83` | 03:45 | **fix**: 传播图 category 字符串→数字映射。词云权重 max-normalize。`_cluster_title()` 标题截断 ≤80 字。文章正文 tooltip 截断 150 字。 |
| 9 | `0ce0ca6` | 03:50 | **docs**: 本文档新增第十八章。 |
| 10 | `22ca38b` | 03:55 | **docs**: `.agents/AGENTS.md` 更新规则和状态。 |

### 最终状态

- **全链路打通**：爬虫→预处理→TF-IDF+BGE→聚类→LLM情感→看板
- **事件数**：3 个（34+13+1 篇），覆盖百度/B站/微博/知乎 4 平台
- **API 字段**：30/30 全部对齐
- **前端 Mock**：0 处残留
- **待解决**：搜索模式不触发热点计算、`analysis/index.vue` 未上线验证

---

## 二十、词云算法与关键词体系重构（2026-07-13 第三阶段）

### 20.1 词云渲染优化历程

| 轮次 | Commit | 问题 | 修复 | 效果 |
|:---:|--------|------|------|------|
| 1 | `ccbf044` | 词云权重全部相等（归一化 sum=1） | 改为 max-normalize | 无效，TF-IDF 给每个词 score=1.0 |
| 2 | `480eb16` | `echarts-wordcloud` 未安装 | pnpm install | 依赖就绪 |
| 3 | `fde5530` | Vite 双 echarts 实例 | `vite.config.ts` 加 `resolve.dedupe: ["echarts"]` | 注册成功 |
| 4 | `81275a9` | 权重极端分布（1个1.0 + 29个0.03） | sqrt + power(t,0.6) 映射 | 仍只有2-4个不同字号 |
| 5 | `5f668bc` | 查询词"台风巴威"占满关键词 | 过滤 query_terms + 过滤乱码 + 排名衰减 30 级 | 词干净了，但 TF-IDF 词质量差 |
| 6 | `823be51` | TF-IDF 分词烂（"一风""全力打"） | LLM 提取关键词 | 48篇 LLM 成功，词质量飞跃 |
| 7 | `cc8b716` | 字号层次平（pow(t,0.6) 压缩） | `pow(rank_ratio, 0.35)` 陡峭金字塔 | 前6词40-64px，中层22-38px，底层12-20px |
| 8 | `2520242` | 全蓝缺乏区分 | sentiment 着色：负红/正绿/中灰 | 一眼识别舆论焦点 |

### 20.2 LLM 多维度关键词提取

重写 `llm_keywords.py`，提示词返回四维度：

| 维度 | 说明 | 适用场景 |
|------|------|------|
| term | 2-8字中文关键词 | 词云展示 |
| score | 重要性 0-1 | 字号映射 |
| sentiment | positive/negative/neutral | 情感着色 |
| entity_type | location/organization/person/event/concept | 实体分类、图标区分 |

**领域无关设计**：提示词无任何领域绑定词。TF-IDF 仅作 LLM 失败的 fallback。

### 20.3 关键词数据复用

关键词多维数据推广到 3 个展示面：

| # | 位置 | 改动 | Commit |
|:---:|------|------|:---:|
| 1 | 看板 EventCard | top-3 关键词标签，情感着色 | `844d108` |
| 2 | 详情页文章列表 | "正文摘要"列 → 关键词标签列 | `844d108` |
| 3 | AI 研判摘要 | 提示词加入"负面焦点/正面焦点/涉及地域" | `844d108` |

### 20.4 生命周期预测修复

`trend_predictor.py` 阈值从绝对值改为相对值：
- `LATENT_MAX_DAILY: 10→3`，`LATENT_MAX_TOTAL: 30→10`
- `PEAK_MIN_DAILY` 删除，改为 `PEAK_TO_GROWTH_RATIO`
- Event #1 从永久"潜伏期"→"成长期"

### 20.5 LLM 缺口全连接

将已有的 `EVENT_SUMMARY_PROMPT` 挂到 `_extract_event_metadata()`，一次 LLM 调用替换 3 个规则函数：

| 函数 | 修复前 | 修复后 |
|------|------|------|
| `_extract_location` | 83 个地名字符串匹配 | LLM NER 提取 |
| `_extract_key_figures` | 取 author 字段去重 | LLM 从正文提取人物/机构 |
| `_extract_cause` | 截断 overview_text 前 100 字 | LLM 综合文章生成起因概述 |
| `summarize_sentiment` | 纯数学比例 | LLM 一句话总结 + 数学数据 |
| `fake_detector` | 仅 ≥70 分调 LLM | ≥40 分全调 LLM |
| `trend_key_points` | 固定标签"首次报道""热度峰值" | 标签带报道数量 |

### 20.6 未记录提交（20.6-20.20）

| # | Commit | 内容 |
|:---:|--------|------|
| 11 | `4d41e8b` | docs: 开发日志从 AGENTS.md 移入本文档 |
| 12 | `ccbf044` | fix: 词云权重 max-normalize |
| 13 | `480eb16` | fix: 安装 echarts-wordcloud + 调试日志 |
| 14 | `fde5530` | fix: Vite dedupe echarts |
| 15 | `1ceca25` | feat: AI 生成事件标题和摘要 |
| 16 | `77c5ee7` | refactor: 提取 _llm_client() 统一工厂 |
| 17 | `612b783` | fix: LLM 缺口全连接（6 处） |
| 18 | `94c5056` | fix: 生命周期相对阈值 |
| 19 | `81275a9` | fix: 词云 sqrt+power 曲线 |
| 20 | `5f668bc` | fix: 关键词过滤查询词+排名衰减 |
| 21 | `afb5740` | docs: AGENTS.md 开发日志规则 |
| 22 | `823be51` | feat: LLM 关键词提取替代 TF-IDF |
| 23 | `cc8b716` | fix: 词云金字塔布局 |
| 24 | `2520242` | feat: 多维度关键词+情感着色 |
| 25 | `844d108` | feat: 关键词数据 3 处复用 |

### 最终状态（截至 2026-07-13）

- **全链路打通**：爬虫→预处理→TF-IDF+BGE→聚类→LLM情感/关键词→看板
- **事件数**：3 个（34+13+1 篇），覆盖百度/B站/微博/知乎 4 平台
- **API 字段**：30/30 全部对齐，新增 sentiment/entity_type 维度
- **前端 Mock**：0 处残留
- **词云算法**：LLM 多维度提取 + 金字塔字号 + 情感着色
- **生命周期**：相对阈值正常运作
- **待解决**：搜索模式不触发热点计算、`analysis/index.vue` 未上线验证

---

## 二十一、后端成熟化与今日 Top10 设计启动（2026-07-13）

项目后续不再以“第一版雏形”为验收标准，工作重心调整为后端算法可靠性、后台任务稳定性和前后端 API 契约正确性，前端视觉设计不在本轮范围内。

已完成设计文档：

`docs/superpowers/specs/2026-07-13-backend-maturity-and-daily-top10-design.md`

设计覆盖：

- 当前内容分析 JSON 序列化和 BGE 连锁回归；
- 事件聚合二次重分配与相似度修正；
- 传播路径证据门槛和证据不足状态；
- 生命周期四阶段兼容、置信度和单调状态机；
- 风险、关键词、情感、热度与 AI 元数据成熟化；
- 微博热搜、百度热榜、知乎热榜的今日 Top10 排名融合；
- 逐问题 TDD、下游回归和最终全量验证。

关键设计选择：传播路径证据不足时允许空边，不使用关键词共现图冒充传播关系；生命周期继续保持四阶段枚举；今日 Top10 先保存快速热榜快照，再异步补齐正式事件分析。

实施工作拆分为四份计划：

- `docs/superpowers/plans/2026-07-13-backend-baseline-and-contract-repair.md`
- `docs/superpowers/plans/2026-07-13-core-algorithm-reliability.md`
- `docs/superpowers/plans/2026-07-13-analysis-quality-and-persistence.md`
- `docs/superpowers/plans/2026-07-13-daily-top10-hotspots.md`

2026-07-13 实施前重新运行全量自动化测试，基线仍为 `244 passed, 31 failed, 5 warnings`。失败分组与交接总结一致：内容分析 JSON 序列化造成主要连锁失败，另外包含 API 枚举、聚合默认值、传播误连和生命周期算法/命名问题。

### 21.1 内容分析 JSON 持久化修复

根因确认：`extract_article_keywords()` 返回 `ArticleKeyword` 领域对象，服务正常路径将对象直接赋给 `AnalysisRunArticle.keywords`。SQLAlchemy 在 BGE 缓存查询或最终提交时自动刷新 JSON 字段，导致序列化异常，并使编码器调用次数保持为 0。

修复方式：在内容分析服务持久化边界统一将关键词转换为普通字典，正常路径和 BGE 降级回滚路径复用同一份 JSON-safe 映射。

验证：

- 聚焦红色测试修复前稳定失败，错误为 `ArticleKeyword is not JSON serializable` 和 `encoder.calls == 0`；
- 修复后聚焦测试 `2 passed`；
- `backend/tests/test_content_analysis_service.py` 完整套件 `11 passed`。
- 爬虫 API、热点服务和后台任务下游套件共 `36 passed`，未再出现由关键词 JSON 序列化引发的连锁失败。

### 21.2 API 枚举契约统一

前端和后端的正式 v2 契约统一为：生命周期阶段使用“潜伏期 / 成长期 / 高潮期 / 消退期”，文章情感标签使用“正面 / 中立 / 负面”。后端兼容接收旧值“中性”，但对外规范化为“中立”；无效生命周期值回退到“潜伏期”，无效情感值回退到“中立”。

TDD 验证：修改后的契约测试首先稳定复现 `neutral` 被错误映射为“中性”；修复映射后运行 `python -m pytest backend/tests/test_contracts.py -q`，结果为 `8 passed`。

### 21.3 事件聚合默认参数统一

应用配置此前已经使用调优参数，但纯算法 `AggregationConfig` 和 `.env.example` 仍保留旧参数，导致测试、离线算法和部署示例可能采用不同聚类边界。本次统一为：加入阈值 `0.55`、创建阈值 `0.40`、移动分差 `0.10`，BGE/TF-IDF/实体/时间权重分别为 `0.55/0.20/0.15/0.10`。真实 `backend/.env` 未读取、未修改。

验证：配置测试修改后先复现 dataclass 与应用配置不一致；修复后事件聚合纯算法套件 `9 passed`，事件聚合服务套件 `13 passed, 1 warning`。同时更新了缺少 BGE 时按新权重重归一化的过期测试期望。

### 21.4 基线修复后全量回归

运行 `python -m pytest backend/tests tests -q`，结果为 `270 passed, 5 failed, 5 warnings`。剩余失败已准确收敛为：

- `test_unrelated_articles_remain_multiple_roots`：暴雨预警和电影票房仍被推断为传播边；
- 两个生命周期测试仍使用旧名称“衰退期”，正式契约应为“消退期”；
- `[3,4,5,3,5]` 低报道量被错误判为“高潮期”；
- `[80,100,120,115,118,116,114]` 稳定高位被错误判为“成长期”。

因此基线阶段已经清除原有 31 项失败中的内容分析、BGE、热点/任务连锁、API 契约和聚合配置问题，但尚未宣称全量测试通过。剩余 5 项由下一阶段的传播证据与生命周期结构化分析任务处理。

### 21.5 事件相似度语义与时间衰减修正

负余弦相似度此前被平移为正值，例如方向相反但非完全相反的向量仍可能获得约 `0.146` 的相似度；事件间隔超过最大天数后，时间兼容度又会突然降为零。修复后负余弦统一截断为零，时间维度采用以 `maximum_event_gap_days` 为半衰期的指数衰减，长期相关事件保留很小但非零的时间证据。

TDD 验证：新增的负向量和 60 天间隔测试修复前均失败；修复后事件聚合纯算法套件 `11 passed`，事件聚合服务套件 `13 passed, 1 warning`。

### 21.6 三段式聚类与确定性重分配

聚类决策由原来的“达到加入阈值就附着，否则立即创建”改为创建区、歧义区、加入区三段式流程。歧义文章先不作为事件种子，待首轮清晰簇形成后重新评分；仍无法达到加入阈值的文章才创建独立簇。已经附着的文章只有在新候选至少提升 `move_margin` 且达到加入阈值时才移动，防止边界文章在多个簇之间抖动。簇和成员在完成后统一按时间及文章 ID 重排，保证输入顺序不影响最终分区。

TDD 验证覆盖歧义文章在后续簇出现后重新附着、乱序输入得到相同分区，以及已有成员仅在明显提升时移动。事件聚合纯算法套件 `14 passed`，事件聚合服务套件 `13 passed, 1 warning`。

### 21.7 传播路径证据门槛修复

传播边不再把同一个文本 Jaccard 分数重复充当“语义”和“共享证据”。推断结果现在分别计算语义、时间、来源作者、关键词/实体和跨平台分量，并要求语义不低于 `0.20`、存在来源或关键词/实体支持、综合分不低于 `0.38`。时间接近和跨平台状态不能单独创建传播边。每个子节点至多选择一个父节点，显式转发/引用始终优先。

显式证据解析除平台原始 parent/root/repost 字段外，还支持微博 `//@作者`、`转自作者` 和 `来源：作者` 文本，并使用至少两字符的规范化作者名双向包含匹配。边对象保持原有 `evidence` 字符串数组以兼容前端，同时新增 `evidence_components` 供后端审计。

TDD 验证修复前同时复现不相关文章误连、文本转发被误判为推断关系、推断边缺少分量证据；修复后传播测试套件 `11 passed`。

### 21.8 传播覆盖状态与单一实现

传播结果新增 `coverage_status`、`graph_mode="propagation"` 和 `limitations`。没有可靠边时返回 `coverage_status="insufficient"` 和空边数组，不再为了图形效果强制连接起源节点；只有推断边而没有平台显式关系时，也会在限制说明中明确标注。

`event_service.get_propagation_data()` 现在只调用 `build_propagation_graph()`，删除了早期 `return` 之后永远不会执行的旧标题 bigram 建图、强制起源出边和重复关键节点实现。传播测试套件验证结果为 `11 passed`。计划中的 `-k "event and propagation"` 在当前测试命名下选中 0 项，因此以传播构建器完整套件作为本步有效验证，并将在阶段性全量测试中覆盖事件 API 回归。

### 21.9 可解释生命周期判定

生命周期算法新增 `LifecyclePrediction`，包含 `stage`、`status`、`confidence`、`evidence` 和 `reactivated`。少于 4 个时间点时不再用微小波动强行判断高潮，而是返回 `data_insufficient`、低置信度并沿用已有阶段或潜伏期。充分数据使用峰值比、近期归一化斜率、近期波动、持续下降和低报道量证据判定四阶段。

状态机约束为：高潮期不能无依据回退为成长期；消退期默认保持，只有最近三点持续上升、斜率和恢复比例同时达到门槛时才以 `reactivated=true` 进入成长期。旧测试中的“衰退期”统一改为正式契约“消退期”。

显式案例结果：`[3,4,5,3,5]` 为潜伏期，持续快速上升为成长期，稳定高位为高潮期，从峰值持续回落为消退期。生命周期测试套件 `23 passed`。

### 21.10 核心算法修复后阶段性全量回归

运行 `python -m pytest backend/tests tests -q`，结果为 `286 passed, 0 failed, 5 warnings`。实施前的 `244 passed, 31 failed` 已全部转绿，基线修复后仍存在的传播误连和 4 项生命周期失败也已消除。

这表示当前已有测试覆盖范围内实现了自动化零失败，不代表整个成熟化计划完成。生命周期结果持久化、分析质量改进、事件元数据/热度快照和今日 Top10 仍按后续计划继续实施。5 条警告均为 SQLAlchemy `Query.get()` 旧接口和 jieba 依赖相关弃用警告，不影响本次测试退出状态，后续应单独消除。

### 21.11 生命周期持久化与详情只读化

Event 新增 `lifecycle_status`、`lifecycle_confidence`、`lifecycle_evidence` 和 `lifecycle_updated_at`。`lifecycle_service` 负责按文章发布日期生成日计数，并调用结构化生命周期算法更新 Event；助手本身不提交事务，由事件聚合或热点计算的原有事务统一提交。MySQL 迁移文件 `20260713_event_maturity.sql` 使用幂等加列，并提供对应 Python 执行入口。

事件详情不再实时改写生命周期阶段或单独提交 Event，而是返回已持久化的阶段、状态、置信度、证据和更新时间。趋势变化点仍可在读取时纯计算，但不产生数据库副作用。

TDD 验证：修复前聚合和热点流程因字段不存在失败，详情结果也缺少结构化字段；修复后聚合/热点/生命周期三个核心套件 `51 passed, 2 warnings`。完整回归 `287 passed, 0 failed, 6 warnings`。

### 21.12 可疑信息改为文章级跨平台佐证

风险评估不再用事件总体平台数替代单篇文章的交叉验证。上下文优先根据 `duplicate_of_id` 和 `content_hash` 建立跨平台重复证据；如文章提供关键词或实体，还可在跨平台、共享实体且文本相似度不低于 `0.60` 时建立高相似佐证。每篇文章分别保存佐证平台集合和证据文章 ID。

兼容输出 `score/reason/method/is_suspicious` 保持不变，并新增 `feature_scores`、`evidence`、`limitations` 和 `rule_version=suspicious-risk-v2`。没有文章级佐证时明确记录“缺少跨平台佐证”，不会因事件内其他无关平台报道而免除该风险，也不会惩罚已经存在跨平台重复证据的文章。

TDD 验证修复前复现文章级上下文字段缺失、跨平台重复证据不生效和结构化输出缺失；修复后可疑信息测试 `22 passed`，事件聚合/详情下游套件 `14 passed, 2 warnings`。

### 21.13 短标题友好的标题正文一致性

标题正文一致性由“至少 6 个不同汉字才检查”的布尔规则改为 0～1 分数。默认实现对中文连续片段使用 bigram、对英文和数字使用词元，四字标题“台风登陆”可以与包含“台风”和“登陆”的长正文建立有效重合；两字通知或过短正文返回 `None`，明确表示证据不足而不是误判不一致。

接口支持注入 `semantic_similarity(title, content)`，有可用 BGE/语义编码器时可直接返回并截断到 0～1，但当前不增加强制模型依赖。风险输出中的 `title_content_consistency` 改为连续特征，并在 evidence 中返回原始一致性分数和数据状态；低于 `0.30` 时仍保持旧的 5 分兼容风险规则。

TDD 覆盖短标题相关正文、短标题无关正文、注入语义提供器和短文本证据不足。可疑信息测试套件结果为 `25 passed`。

### 21.14 连续风险特征与 LLM 灰区

可疑信息评分移除固定 25 分底座，改为六个 0～1 连续特征的经验加权和：来源可追溯性、文章级跨平台佐证、标题正文一致性、互动异常、煽动性表达、广告或外链。权重分别为 `0.20/0.20/0.15/0.15/0.15/0.15`，最终分数限制在 0～100，并标记 `rule_version=suspicious-risk-v3-empirical`，明确它不是训练得到的事实概率。

负面情绪和官方介入仍作为诊断证据返回，但负面情绪不再直接等同于虚假风险。互动异常由相对事件平均互动量的连续比例计算；煽动性按命中词数量递增；单独外链的风险低于明确广告引流。

LLM 默认只审查 `30～70` 分灰区，可通过 `RISK_LLM_MIN_SCORE` 和 `RISK_LLM_MAX_SCORE` 配置。低风险和高规则风险不调用 LLM；LLM 必须返回 JSON，解析成功后作为 `evidence.llm_review` 追加，不能覆盖规则分数和已有证据。修复同时移除了此前错误导入不存在的 `settings`、导致 LLM 分支实际无法调用的问题。

TDD 验证风险特征范围、加权分数重建、灰区调用次数和结构化审查证据。结果：可疑信息测试 `27 passed`，事件聚合下游 `14 passed, 2 warnings`，契约测试 `8 passed`。

### 21.15 事件摘要关键词输入与查询词降权

`_ai_generate_summary()` 改为通过关键字参数接收已经聚合好的 `event_keywords` payload，不再从第一篇 Article 调用只接受 Event 的 `_event_keywords()`。报告后处理先用正式 Event 加载一次关键词，再将同一 payload 传入摘要生成，避免对象类型错配和重复数据库查询。

文章关键词提取保留精确查询词并固定 `source=query`，得分按当前最高事件特异词的 `0.6` 降权；展示规范化相同的 TF-IDF 词元会被查询词版本替换，避免“重庆 暴雨”和“重庆暴雨”同时出现。事件关键词聚合也不再删除查询词，而是追加 `source=query`，权重最高为 `0.6` 且低于排名第一的事件特异词。

TDD 验证摘要 prompt 获得显式关键词 payload、文章查询词来源和降权、事件词云查询词保留。聚焦测试 `3 passed`，内容分析特征与事件聚合套件 `28 passed, 1 warning`。

### 21.16 LLM 关键词批量提取与逐篇回退

LLM 关键词提取从逐篇请求改为批量请求。输入以 JSON 数组传递 `article_id` 和文本，返回值必须是以文章 ID 为键的 JSON 对象。解析器只接受当前批次中的 ID，对非法 ID、空关键词、错误分数和无效枚举逐项过滤，单条错误不会使整批结果失效。

批大小由 `LLM_KEYWORD_BATCH_SIZE` 控制，默认 5、范围 1～20，并支持测试或扩展场景注入 client。某篇文章只有在获得至少 3 个有效 LLM 关键词时才采用模型结果；模型漏项、批次失败或有效词不足时，该文章单独回退原有 TF-IDF/实体/主题结果，不影响其他文章。异常处理不记录 API Key、请求头或原始鉴权信息。

TDD 覆盖批次数量、批大小、越界 ID、坏条目、部分返回和 TF-IDF 回退。独立关键词测试 `3 passed`；LLM 关键词、内容分析特征和内容分析服务联合套件 `26 passed`。

### 21.17 情感传播权重与确定性摘要

文章传播热度的情感聚合因子由 `1.0～2.0` 收紧为 `1.0～1.5`。热度先使用 `log1p` 相对事件最大热度归一化，再仅提供最多 50% 的传播加权，避免单篇高互动文章压倒其余报道；质量、垃圾和重复文章权重仍独立保留在计算明细中。

事件、每日和平台摘要不再调用第二次 LLM。`summarize_sentiment()` 现在根据文章数、主导标签、加权比例和平均分生成确定性文本；事件快照额外保存最多三条非继承文章的代表性判断依据。`_serialize_snapshot()` 只读取 `calculation_details.summary`，因此事件详情和情感接口不会因读取产生模型请求，历史快照缺少该字段时安全返回空摘要。

SnowNLP 降级结果同时标记 `SNOWNLP_FALLBACK` 和 `DOMAIN_MISMATCH_FALLBACK`，置信度继续受 `snownlp_confidence_cap` 限制，明确通用情感模型在舆情领域的适配限制。

TDD 红灯稳定复现传播因子为 `2.0`、摘要为 `None`、额外摘要 LLM 调用 4 次以及缺少领域降级警告。修复后运行 `python -m pytest backend/tests/test_sentiment_algorithms.py backend/tests/test_sentiment_service.py -q`，结果为 `20 passed, 1 warning`；警告是既有 SQLAlchemy `Query.get()` 弃用提示。

### 21.18 事件 AI 元数据持久化与详情只读化

Event 新增 `metadata_status`、`metadata_version`、`metadata_confidence`、`metadata_evidence` 和 `metadata_updated_at`。元数据版本为 `event-metadata-v2`，证据中保存字段级置信度、证据文章 ID、模型、警告和代表性文章集合指纹。MySQL 迁移 SQL 已补充五个字段；Python 迁移入口同时支持对既有 SQLite 开发库逐列升级。

元数据生成从 `get_event_detail()` 移至事件成员更新边界。`_update_event()` 在正式事件发布或活跃成员发生实质变化时提取一次；代表性文章 ID 集合未变化时直接复用持久化结果。严格提示词要求四个字段分别返回 `value/confidence/evidence_article_ids`，证据 ID 必须来自输入文章。解析失败时保留已有非空地点、人物和起因，不用空字符串覆盖。

`time_code` 优先使用 `first_publish_time` 的确定性格式。LLM 时间与首发时间不一致时保存 `TIME_CODE_CONFLICT`，但不会覆盖可靠时间。详情接口直接返回已持久化的元数据状态、版本、置信度、证据和更新时间，不再调用元数据 LLM；可疑信息风险在读取时仅做规则计算，不调用灰区 LLM，也不再修改 Article 或提交事务。

TDD 红灯复现 Event 字段缺失、聚合更新零元数据调用、迁移缺列和详情读取副作用。聚焦元数据测试为 `5 passed`；事件聚合、迁移、QA 和情感详情下游联合验证为 `33 passed, 8 warnings`。警告均为既有 SQLAlchemy `Query.get()`、jieba/pkg_resources 弃用提示。

### 21.19 搜索发布事件的真实热度快照

搜索或手动事件簇发布后不再使用只更新 Event 三个数字的临时公式。新增 `calculate_single_event_heat()` 复用正式热点公式：独立报道量、24/48 小时增长、平台覆盖、`log1p` 互动强度和指数半衰期仍由同一 `HotspotConfig` 与 `formula_version` 控制。相同报道和互动条件下，较旧事件因 freshness 分量衰减而获得更低热度。

新增 `persist_event_heat_snapshot()`，在没有 HotspotRun 时创建来源为 `aggregation_publish` 的 `EventHeatSnapshot`。快照保存原始统计、分项得分、核心/传播/最终热度、权重、时间置信度、公式版本、警告和来源 `aggregation_run_id`，并同步 Event 的当前快照指针及展示字段。同一发布运行重复后处理时按 `aggregation_run_id` 复用快照，避免重复记录。

`EventHeatSnapshot.hotspot_run_id` 改为可空，表示快照可由 HotspotRun 或 AggregationRun 产生，而不是创建伪造热点运行。新建 MySQL 表定义和成熟度迁移均已调整；SQLite 迁移会保留原数据并重建热度快照表，使既有非空约束安全变为可空。

TDD 红灯复现搜索发布零快照、模型来源强制非空和迁移缺失；时间半衰期对比测试在现有正式公式上通过。修复后聚焦测试 `5 passed`，热点算法、热点服务、事件聚合与迁移联合验证 `57 passed, 3 warnings`。

### 21.20 分析质量阶段全量回归

按分析质量计划运行风险、内容分析、情感、事件聚合和热点专项套件，结果为 `102 passed, 3 warnings`。随后运行 `python -m pytest backend/tests tests -q`，结果为 `308 passed, 0 failed, 7 warnings`。

本轮从分析质量计划开始前的可疑信息、关键词、情感、AI 元数据和搜索热度缺陷出发，完成了文章级佐证、连续经验特征、LLM 灰区、查询词降权保留、批量关键词提取、情感确定性摘要、事件元数据持久化和无 HotspotRun 热度快照。当前自动化覆盖范围内无失败。

7 条警告来自 SQLAlchemy `Query.get()` 旧接口与 jieba/pkg_resources 依赖弃用，不影响退出状态。审计文档仍明确保留跨领域参数标定、标注事实核查数据、平台真实转发关系、领域情感模型、SSE 和 PDF 等长期限制，不把测试全绿描述为算法已获得真实世界准确率证明。

### 21.21 今日 Top10 标题归一化与 RRF

新增纯算法模块 `daily_hot.py`。热榜标题先进行 NFKC Unicode 规范化，移除话题井号、外层括号、重复空格和尾部热度数字；展示标题保留有意义的内部标点，归并键则移除空白与装饰符号并统一大小写。

跨平台排名采用 Reciprocal Rank Fusion：每个平台对同一归并标题只贡献最佳名次，得分为 `sum(1 / (rrf_k + rank))`。结果按融合分、来源数量、最佳名次和规范化标题确定性排序，并支持限制返回数量。该算法不依赖各平台不可比的原始热度数值。

TDD 覆盖 Unicode/话题符号规范化、同标题合并、同来源去重、独立来源贡献、稳定排序、limit 和无效输入过滤。聚焦结果为 `6 passed`。

### 21.22 今日 Top10 持久化模型与迁移

新增 `DailyHotRun` 和 `DailyHotItem`，原始/融合热榜与正式 Event 分表保存。Run 记录日期、状态、成功/失败来源、脱敏错误、条目数和配置哈希；Item 记录归并键、展示标题、RRF 得分、榜位、各来源名次与原始 payload，以及独立补全状态。

一个 Run 同时包含多个来源，因此使用 `run_date + config_hash` 唯一约束，来源集合和算法参数进入配置哈希。Item 使用 `run_id + normalized_key` 和 `run_id + rank` 两个唯一约束。`event_id` 与 `analysis_task_id` 均可空，只有后续补全成功后才建立正式事件或任务关联。

新增 MySQL 幂等建表 SQL 和 SQLite/Python 迁移入口；迁移只创建独立热榜表，不修改已有 Event。聚焦迁移测试 `4 passed`，全部迁移测试联合结果 `31 passed`。

### 21.23 多平台直接热榜采集与失败隔离

新增 `collect_daily_hot()`，对配置的 `weibo_hot / baidu_hot / zhihu_hot` 分别发起一次 `mode=hot` 请求，每个平台独立使用 source limit。榜位优先读取 `raw_json.rank/realpos`，缺失时使用稳定列表位置；随后调用同一 RRF 纯算法并在一个事务中保存 Run 与 TopN Item。

单个平台未配置、认证失败、空响应或意外异常只记入该来源诊断，其余来源继续融合。Run 状态分为 `success/partial/failed`。错误不保存原始异常消息，原始 payload 会递归删除 Authorization、API Key、token、secret 和 cookie 等敏感键，并对 Bearer 值脱敏。

TTL 内的 `success/partial` Run 直接复用；失败或过期时创建新尝试。为满足同日多次刷新，`DailyHotRun` 新增 `attempt`，唯一约束修正为 `run_date + config_hash + attempt`。配置哈希包含来源集合、source limit、result limit 和 RRF K。

TDD 覆盖第三方单源失败仍生成融合结果、密钥不进入 errors/payload、热模式参数、全源失败、TTL 复用和 stale attempt。Top10 与爬虫核心联合结果为 `43 passed`。

### 21.24 今日 Top10 查询与管理员刷新 API

新增 `GET /api/hotspots/today`，登录用户可读取最近持久化热榜。默认返回 Top10，`limit` 只接受 1～100。无缓存时返回 `status=empty`、空 items 和 `stale=true`；有缓存时返回日期、生成时间、TTL 过期标记、成功/失败来源、脱敏错误和融合条目。

条目响应包含榜位、标题、RRF 得分、来源名次、安全来源 URL、补全状态以及可空的 event/task ID，不返回原始平台 payload。GET 路由不触发外部爬虫。新增管理员 `POST /api/hotspots/today/refresh`，使用配置的来源、source limit、TopN、RRF K 和 TTL 强制采集新 attempt；普通用户返回 403。

新增配置默认值：三大直接热榜来源、每来源 30 条、结果 10 条、`rrf_k=60`、TTL 900 秒，并同步 `.env.example`，未读取或修改真实 `.env`。Top10 API 聚焦测试与服务测试通过；和正式热点、契约联合验证为 `29 passed, 1 warning`，原 `GET /api/hotspots` 语义未改变。

### 21.25 租约后台刷新与定时调度

新增 `daily_hot_job(task_id)`，通过现有 runner 租约领取执行，按逐来源采集、RRF 融合和持久化边界更新任务进度。部分来源失败时 Run 为 `partial`、Task 仍成功；所有来源失败时 Task 明确失败。重复提交同一个 Task 时第二次无法再次领取，因此不会重复采集。

`daily_hot` 已加入默认恢复注册表，进程重启后 pending 或租约超时任务可重新排队。任务 payload 中的 `sources` 与原 `platforms` 一样按去重、大小写和排序规范化，来源顺序变化仍会复用等价任务。

恢复 scheduler 同时注册 `daily-hot-refresh` 间隔任务，默认 900 秒。调度器按 `DAILY_HOT_SYSTEM_USERNAME` 查找已存在、启用且角色为 admin/system 的用户，创建或复用最近等价 Task；找不到合法 actor 时明确抛错，不创建 `created_by` 为空的任务，也不自动创建管理员。部署需预先配置有效用户。

新增 `DAILY_HOT_REFRESH_INTERVAL_SECONDS` 和 `DAILY_HOT_SYSTEM_USERNAME` 示例配置。聚焦 job/recovery/scheduler 测试 `5 passed`，Top10、任务和爬虫 API 联合结果 `43 passed, 1 warning`。

### 21.26 Top10 条目独立事件补全

每个 DailyHotItem 现在拥有独立 `daily_hot_enrichment` Task，状态为 `pending/running/completed/failed/no_event`。Run 采集成功或部分成功后为每个未完成条目创建任务；管理员手动刷新也会触发同一入队函数。Item 已关联 pending/running Task 时直接复用，不创建或重复提交另一个 active Task。

默认补全链复用现有后端能力：以热榜标题作为查询词，调用已配置的非热榜搜索爬虫，持久化文章，创建搜索内容分析和共享聚合运行，选择证据最充分的事件簇并发布为正式 Event。只有发布或匹配得到正式事件 ID 后才写 `event_id`；无可用搜索平台或无事件簇时标记 `no_event`。

单项异常只将该 Item 和 Task 标记为 failed，DailyHotRun 状态与其他条目不受影响。Item 仅保存异常类型码和固定消息 `item enrichment failed`，不会保存原始异常、Authorization 或密钥。`daily_hot_enrichment` 已加入默认恢复注册表。

新增 `DAILY_HOT_ENRICH_TARGET_COUNT=20`。三条目隔离、active task 幂等与 API 入队聚焦测试 `10 passed`；Top10、任务和事件聚合联合验证 `56 passed, 3 warnings`。

### 21.27 正式热点与今日 Top10 接口兼容性

补充服务层和 API 层兼容契约测试，明确 `GET /api/hotspots` 只返回已经完成分析并具有正式热度状态的 `Event`，响应保持 `events/total` 结构；`GET /api/hotspots/today` 只返回独立持久化的原始/RRF 热榜条目，响应保持 `items/total` 结构，并允许补全成功后携带可空的 `event_id`。

测试同时覆盖了一个重要边界：DailyHotItem 即使已经关联 Event，也不能仅凭热榜名次进入正式热点接口；正式热点仍由 Event 的 `is_hot/hot_rank` 和热度快照语义决定。两个接口的条目字段不会互相渗透，今日榜单不返回正式事件热度字段，正式热点不返回来源名次字段。

新增的两项兼容测试直接在现有实现上通过，因此本步骤未修改生产代码。`test_hotspot_service.py` 与 `test_daily_hot_api.py` 完整联合回归结果为 `20 passed, 1 warning`；警告来自既有 jieba/pkg_resources 弃用提示。

### 21.28 隔离式后端真实验证工具

首次直接使用默认 `create_app()` 进行最小 Top10 服务验证时，采集和融合成功，但默认 `TASK_RECOVER_ON_STARTUP=true` 同时启动了长期任务恢复调度器。短命令退出期间出现 APScheduler 解释器关闭异常、SQLite 锁竞争和非必要 BGE 模型加载。根因是一次性验证错误继承了生产后台服务配置，并非热榜爬虫或 RRF 融合失败。

新增 `tools/validate_backend_live.py`。工具保留 `.env` 中的真实爬虫和 LLM 配置，但强制使用临时 SQLite、同步任务、关闭启动恢复和 BGE；Top10 只请求三个直接热榜来源各 1 条并返回 1 条融合结果，LLM 只发送一次最多 30 token 的固定 JSON 探针。输出只保留状态、来源、数量、模型名和契约布尔值，不保存标题、URL、原始平台 payload 或模型正文。

写入结果文件前递归删除敏感字段，替换已配置密钥和 Bearer/header 值，并再次扫描已知密钥与 Authorization、Bearer、Cookie、API Key 等标记。认证、配额和网络失败作为外部状态记录；内部异常、格式错误或安全扫描失败才使验证命令非零退出。

TDD 首先稳定复现模块缺失错误，随后覆盖隔离配置、递归脱敏、敏感文本扫描、LLM JSON 契约、外部错误分类、真实配置密钥集合、最小 Top10 参数、单次 LLM 调用和退出状态。首次隔离运行进一步复现了 Windows 下临时 SQLite 文件无法删除：应用上下文结束后 SQLAlchemy 连接池仍持有文件句柄。验证工具现于 `finally` 中显式移除 session 并释放 engine，回归测试证明探针返回后数据库文件可立即删除。验证工具与原爬虫验证器联合测试结果更新为 `15 passed, 5 subtests passed`。

### 21.29 Top10 与 LLM 低频真实验证结果

2026-07-13 19:17（Asia/Shanghai）执行隔离式最终探针。三个直接热榜来源 `weibo_hot / baidu_hot / zhihu_hot` 均成功返回有效数据；最小融合 Run 状态为 `success`，可用来源 3、失败来源 0，持久化和序列化均返回 1 条，响应包含可空 `event_id`，且 `scheduler_started=false`。

同一进程仅进行一次 LLM 固定 JSON 探针调用，结果为 `SUCCESS`，实际返回模型名 `deepseek-v4-flash`，`content_valid=true`。该结果只证明当前密钥、网络、OpenAI-compatible 接口和最小结构化输出可用，不代表模型在情感、事件摘要、风险或问答任务上的准确率已经得到验证。

原三平台爬虫验证结果保存于 `tests/daily_hot_live_validation_results.json`，隔离 Top10/LLM 结果保存于 `tests/final_backend_live_validation_results.json`。两份结果对当前配置中的所有已知密钥扫描命中数均为 0，Authorization、Bearer、Cookie、API Key 和 access token 文本标记扫描无命中。此前直接探针产生的 `backend/instance/opinion_analysis_dev.db` 修改已恢复，最终隔离探针没有修改跟踪数据库。

### 21.30 后端算法科学性、合理性与完整性自评

新增 `docs/后端算法科学性合理性完整性自评.md`，覆盖多平台采集、预处理、文本表示、LDA、事件聚合、今日 Top10、情感、热度、生命周期、可疑风险、传播图、LLM 元数据/问答/报告和任务/API 工程保障共 13 个模块。

评价使用科学性、工程合理性和完整性三个 1～5 分维度，并使用 E0～E5 证据等级约束结论。当前平均分约为科学性 `3.3/5`、合理性 `3.5/5`、完整性 `3.9/5`；仓库没有足够证据支持任何核心算法达到代表性标注评估 E4 或长期线上证据 E5。

自评结论是：项目已经达到较成熟课程项目/可运行原型的工程完整度，核心方法选择大体科学且完成明显纠偏；真实世界有效性仍需要事件簇、情感、生命周期、风险、传播边、关键词和 Top10 排序标注集。文档同时列出不应对外宣称的能力、用户展示警示以及 P0/P1/P2 改进路线。

---

## 二十二、《功夫女足》电影全链路实跑

### 22.1 隔离式 E2E 驱动器

新增 `tools/run_keyword_e2e.py` 和对应测试，以“《功夫女足》电影”为默认关键词。驱动器使用专用 SQLite 和隐藏子进程启动正式 Flask 服务，保持异步 Task 语义并轮询进度；随后通过正式 API 完成登录、搜索、聚合簇读取与选择、情感读取、正式发布、事件列表/详情、传播、报告、HTML 导出和 QA。

驱动器按阶段导出原始文章、预处理、内容分析、聚合、情感、正式事件、热度、生命周期、元数据、报告和 Task 记录。原文只保留长度、SHA-256 和受控摘录，JWT、密码、Cookie、认证头和真实密钥递归移除。运行数据库和服务日志写入 Git 忽略的 `artifacts/`，可提交的脱敏证据写入 `tests/e2e/kung_fu_women_football/`。

簇选择明确惩罚普通女足比赛和旧《功夫足球》内容，只有包含“功夫女足”及电影语境、且综合选择分不低于 6 的簇才允许发布。用户质量门槛检查文章相关率、平台覆盖、情感和趋势一致性、关键词多样性、传播限制、风险语义、固定 45 mock 值以及 DOM 中的 undefined/NaN。

TDD 首先复现模块缺失和真实 CLI 导入路径错误，修复后 E2E 驱动器核心测试为 `10 passed`。前端构建、真实 API 运行和浏览器截图仍按后续步骤执行。

### 22.2 真实 API 全链路结果

使用真实 `.env` 配置执行关键词“《功夫女足》电影”。百度搜索、微博搜索、知乎和 B站各采集 6 条，共 24 条；22 条清洗成功，2 条 B站正文为空而失败。内容分析保存 24 条特征、20 条关键词结果和 20 条 BGE embedding。

聚合生成 6 个事件簇、20 条文章分配。选择器以 29 分选中“周星驰功夫女足上映引热议”簇，包含 11 篇文章和 3 个平台。人工检查与自动规则均判定 11 篇属于电影事件。正式发布得到 Event 1，情感为正面 18.18%、负面 72.73%、中立 9.09%，热度 58.664074，风险 28.3（低风险），QA 使用 `deepseek-v4-flash` 返回有效回答。

全部 API、数据库和任务中间状态保存于 `tests/e2e/kung_fu_women_football/`；运行数据库和日志位于忽略目录 `artifacts/kung_fu_women_football/`。

### 22.3 真实浏览器验收与缺陷修复

驱动器新增 `--reuse-database`，可复用隔离数据库重新执行发布后处理和浏览器验收，不重复消耗爬虫配额。Selenium 使用 Chrome headless 通过真实登录表单进入 `/analysis`、`/dashboard` 和 `/events/1`，保存 DOM、控制台、可见状态以及分析页、看板、详情顶部/中部/底部截图。

真实页面复现并修复：Event.summary 未同步、报道趋势被单个热度快照压缩、风险雷达固定 45、任务历史无关键词、`success` 未本地化、传播证据不足未提示、生命周期低样本限制不可见、EventCard 数值 prop 类型错误、前端类型声明缺口和 E2E SQLite 心跳锁竞争。

修复后质量门槛 `passed=true`：11/11 相关文章，平台文章数与总数一致，情感和为 1，趋势为 5 个日点，20 个关键词，摘要和风险存在；分析关键词/成功状态、看板事件/摘要、详情全部核心分区和浏览器控制台检查均通过。传播仍为 11 节点、0 条边，但页面明确显示“不代表已验证传播路径”。

完整报告见 `docs/功夫女足电影全链路实跑与前端数据质量报告.md`。

### 22.4 最终构建、回归和安全扫描

前端 `vue-tsc --noEmit --skipLibCheck` 通过；Node 专项测试 `10 passed`；Vite 8.0.3 生产构建转换 3119 个模块并成功生成 `dist`。E2E、真实验证、事件聚合和任务聚焦测试为 `63 passed, 3 warnings, 5 subtests passed`。

最终执行 `python -m pytest backend/tests tests -q`，结果为 `359 passed, 0 failed, 7 warnings, 5 subtests passed`。7 条警告均为既有 SQLAlchemy `Query.get()` 弃用提示。

对 `tests/e2e/kung_fu_women_football/` 的全部文本证据扫描当前配置中的 4 个真实密钥，命中 0；Authorization、Bearer、Cookie、API Key、access token 和 secret 标记命中 0。`backend/.env` 仍未被 Git 跟踪，运行数据库和日志继续由 `artifacts/` 忽略。

---

## 二十三、merge 与最终修复（2026-07-13 ~ 2026-07-14）

### 23.1 合并过程

队友 `qxq` 在 branchhu 上 force-pushed 大量后端优化（40+ commits），涵盖算法重写、新模块、E2E 测试。本地与远程历史分叉。处理方式：

```
本地 branchhu (ad36cba) ← 分叉 → 远程 branchhu (70a0b36)
                                    ↓
                               git reset --hard origin/branchhu
                                    ↓
                               cherry-pick ad36cba (前端架构文档)
                                    ↓
                               backup-local-20260713 保留全部本地历史
```

合并后本地 = 队友后端优化 + 我们的前端架构文档。

### 23.2 后端新增模块概览（队友 qxq）

| 模块 | 文件 | 功能 |
|------|------|------|
| 每日热榜 Top10 | `daily_hot.py` + `daily_hot_service.py` + API | 多平台热榜采集、RRF 融合、定时刷新、enrichment 链 |
| 事件成熟度 | `lifecycle_service.py` + migration | 新版 `analyze_lifecycle`（confidence/evidence/status） |
| 传播图重写 | `propagation/scorer.py` + `builder.py` | 修复 `shared=sim` 重复变量，四维结构化 evidence |
| 风险评估重写 | `fake_detector.py` | 六维度加权评分，bigram 标题一致性，文章级交叉验证 |
| 聚类优化 | `event_clusterer.py` | 歧义区二次重分配，余弦 clamp 修正 |
| 热度快照 | `persist_event_heat_snapshot()` | 搜索模式 publish 后持久化热度 |
| AI 元数据持久化 | `event_service.py` | metadata_status/version/confidence 字段 |
| 功夫女足 E2E | `tests/e2e/kung_fu_women_football/` | 18 步全链路验证 + 截图 |
| 前端适配模块 | `riskRadar.ts` + `propagationPresentation.ts` + `lifecyclePresentation.ts` + `taskPresentation.ts` | 风险雷达/传播提示/生命周期提示/任务展示 |

### 23.3 发现并修复的问题

| # | 问题 | 根因 | 修复 | Commit |
|:---:|------|------|------|:---:|
| 1 | 热度全是 ~58.7 | `calculate_single_event_heat` 单事件百分位排名退化 | 改为绝对公式：`articles×2×(1+platforms×0.3)×decay + engagement` | `ce1fdca` |
| 2 | 标题"女子嘴角水疱致脑死亡" | DB 有队友功夫女足测试数据残留，聚类时混入台风事件 | 删除 DB + 全新爬取 + `_ai_generate_title` 单篇也调用 | `ce1fdca` |
| 3 | 微博标题 100+ 字带 hashtag | `_cluster_title` 单篇跳过 AI；微博 text_raw = 全文 | 单篇也走 LLM；fallback 去 hashtag+截断 | `ce1fdca` |
| 4 | 热度 publish 时为 0 | APScheduler 恢复任务锁 DB，`persist_event_heat_snapshot` commit 失败 | SQLite WAL 模式允许并发读写 | `e7526cd` |
| 5 | 每日热点 API 未接入前端 | 后端完整实现（`GET /api/hotspots/today`），前端无调用 | 看板新增「🔥 今日热点 Top10」标签行 | `e7526cd` |
| 6 | 看板默认时间排序 | `sortBy` 默认 "time" | 改为默认 "heat" | `e7526cd` |
| 7 | Event 表缺新列 | migration 脚本未运行 | 手动 ALTER TABLE 加 lifecycle_*/metadata_* | `ce1fdca` |
| 8 | SQLite WAL/SHM 文件被 git 追踪 | WAL 模式下产生附加文件 | `.gitignore` 加 `*.db-shm` `*.db-wal` | `e7526cd` |

### 23.4 模块调用审计

对全部后端/前端模块进行全面调用审计，发现：

- ✅ **13/14 模块正常运作**（extract_keywords_llm、_ai_generate_title/summary、persist_event_heat_snapshot、update_event_lifecycle、build_propagation_graph、fake_detector、daily_hot_job 等全部已接入）
- 🔴 **1 处前端未接入**：`GET /api/hotspots/today` — 已修复
- 🟡 **1 处半失效**：`persist_event_heat_snapshot` 被 DB 锁阻塞 — 已通过 WAL 修复

### 23.5 全链路重跑结果（台风巴威，干净 DB）

| 指标 | 数值 |
|------|:---:|
| 爬取 | 40 篇（百度/B站/微博/知乎） |
| 聚类 | 7 个事件（最大 25 篇） |
| AI 标题 | 全部干净（"台风巴威影响多地""沈阳青岛遭台风巴威袭击"等） |
| 热度 | 43.1 / 25.2 / 22.6（有区分） |
| 生命周期 | 成长期 + 潜伏期 |
| 关键词 | 30 词/事件，情感着色 |

### 23.6 待解决问题

| 问题 | 说明 |
|------|------|
| 旧数据时间戳导致衰减过重 | Event #1 的 `first_publish_time` 是旧爬虫的 2025 年时间戳，decay=0.21 |
| 互动量全为 0 | 百度新闻源无转评赞数据，TikHub 返回的互动字段未正确映射 |
| `daily_hot_enrichment_job` 未触发验证 | 定时任务注册了但未手动触发过完整 enrich 链路 |

---

### 23.7 开发日志

| # | Commit | 内容 |
|:---:|--------|------|
| — | `2c54aba` | **docs**: 前端架构与后端技术对接文档（cherry-pick） |
| — | `ce1fdca` | **fix**: 热度百分位退化 + AI 标题单篇 + 数据污染清理 |
| — | `d68f10d` | **fix**: 取消 DB 文件追踪 |
| — | `e7526cd` | **fix**: 看板默认热度排序 + 今日热点 Top10 + SQLite WAL |

---

