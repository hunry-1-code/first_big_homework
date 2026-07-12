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

