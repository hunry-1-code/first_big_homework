# 前端架构与后端技术对接文档

> 本文档描述前端完整代码结构、各组件职责、数据流、与后端 API 的对接关系。供后端开发者理解前端数据消费方式，也方便后续维护者快速定位代码。

---

## 一、技术栈

| 层次 | 技术 | 版本 |
|------|------|:---:|
| 框架 | Vue 3 (Composition API + `<script setup>`) | 3.5 |
| 构建 | Vite | 8.x |
| 语言 | TypeScript | 6.x |
| UI 库 | Element Plus | 2.13 |
| 样式 | Tailwind CSS + SCSS | 4.x |
| 状态管理 | Pinia | 3.x |
| 路由 | Vue Router | 5.x |
| 图表 | ECharts + echarts-wordcloud | 6.x / 2.1 |
| HTTP | Axios（双实例） | 1.14 |
| 图标 | Iconify (offline + online) + unplugin-icons | — |
| 工具 | @pureadmin/utils, @vueuse/core, dayjs, mitt | — |

## 二、目录结构

```
frontend/
├── index.html                     # SPA 入口
├── vite.config.ts                 # Vite 配置（代理 /api → 127.0.0.1:5000, 端口 8848）
├── package.json                   # 依赖声明（基于 vue-pure-admin v7.0.0）
│
├── build/                         # Vite 构建插件与优化配置
│   ├── plugins.ts                 # 插件注册（Vue/JSX/压缩/CDN/SVG/图标等）
│   ├── optimize.ts                # 预构建依赖排除（echarts-wordcloud 等）
│   └── utils.ts                   # 路径别名、环境变量封装
│
├── src/
│   ├── main.ts                    # Vue 应用初始化入口
│   │   ├── 注册全局组件：IconifyIconOffline/Online, FontIcon, Auth, Perms
│   │   ├── 注册全局指令：auth, perms, copy, longpress, ripple, optimize
│   │   ├── 注册插件：Pinia, Router, i18n, ElementPlus, ECharts, PureTable,
│   │   │            PureDescriptions, VxeTable, Motion, VueTippy
│   │   └── 加载 platform-config.json → 注入响应式存储 → mount
│   │
│   ├── App.vue                    # 根组件（el-config-provider + router-view）
│   │
│   ├── api/                       # 📡 API 层 — 所有后端请求的定义
│   │   ├── client.ts              # Axios 实例（baseURL=/api, timeout=15s, Bearer 注入, 401→登出）
│   │   ├── events.ts              # GET /events, GET /events/:id, /report, /propagation
│   │   ├── crawler.ts             # POST /crawler/search, POST /crawler/trigger, GET /crawler/status
│   │   ├── qa.ts                  # POST /qa/ask, GET /qa/history
│   │   ├── tasks.ts               # GET /tasks/:id, GET /tasks/my, GET /tasks
│   │   ├── admin.ts               # GET/POST/PUT/DELETE /api/admin/users
│   │   ├── user.ts                # POST /api/auth/login, GET /api/user/profile
│   │   ├── routes.ts              # GET /get-async-routes（动态路由）
│   │   ├── importData.ts          # POST /import/json
│   │   ├── opinionUser.ts         # GET/PUT /user/profile, /user/config, /user/sources
│   │   └── mock.ts                # 仅用于头像上传的 mock 端点
│   │
│   ├── components/                # 🧩 组件层
│   │   ├── EventCard.vue          # 事件卡片（看板使用）
│   │   ├── TaskList.vue           # 任务进度表格（运维管理/分析页使用）
│   │   ├── PropagationGraph.vue   # 传播网络图（独立组件，当前未接入）
│   │   ├── PropagationTimeline.vue # 传播时间轴（独立组件，当前未接入）
│   │   ├── ReDialog/              # 全局对话框系统
│   │   ├── ReDrawer/              # 全局抽屉系统
│   │   ├── ReIcon/                # 图标系统（Iconify + iconfont + 离线 SVG）
│   │   ├── ReAuth/                # 按钮级权限控制
│   │   ├── RePerms/               # 按钮级权限检查
│   │   ├── ReSegmented/           # 分段控制器
│   │   ├── ReText/                # 文本编辑/展示
│   │   ├── ReTypeit/              # 打字机动画
│   │   ├── ReCropper/             # 图片裁剪
│   │   ├── ReCropperPreview/      # 裁剪预览
│   │   ├── ReImageVerify/         # 图片验证码
│   │   └── ReQrcode/              # 二维码生成
│   │
│   ├── views/                     # 📄 页面层
│   │   ├── welcome/index.vue      # 舆情看板（首页 Dashboard）
│   │   ├── events/detail.vue      # 事件详情分析报告
│   │   ├── analysis/index.vue     # 事件定向分析（新建）
│   │   ├── qa/index.vue           # 智能问答
│   │   ├── user/index.vue         # 个人中心
│   │   ├── login/index.vue        # 登录页
│   │   ├── admin/index.vue        # 运维管理（爬虫/导入/任务）
│   │   ├── admin/events.vue       # 事件管理（CRUD + 聚合/合并）
│   │   ├── admin/users.vue        # 用户管理（CRUD）
│   │   ├── error/                 # 错误页（403/404/500）
│   │   ├── empty/index.vue        # 空白页
│   │   └── account-settings/      # 账户设置
│   │
│   ├── router/                    # 🗺 路由层
│   │   ├── index.ts               # 路由实例 + 守卫（token校验/权限过滤/动态路由注入）
│   │   ├── utils.ts               # initRouter() 获取后端动态路由 + 菜单拍平/过滤
│   │   ├── modules/opinion.ts     # 业务路由定义
│   │   └── modules/remaining.ts   # 登录/错误/设置等非业务路由
│   │
│   ├── store/                     # 📦 状态管理层（Pinia）
│   │   └── modules/
│   │       ├── user.ts            # 用户登录态/角色/权限/Token
│   │       ├── permission.ts      # 菜单/路由/keep-alive 缓存
│   │       ├── app.ts             # 侧边栏/布局/设备类型
│   │       ├── settings.ts        # 系统设置（标题/固定头/隐藏侧边栏）
│   │       ├── multiTags.ts       # 多标签页状态（持久化 localStorage）
│   │       ├── epTheme.ts         # Element Plus 主题色
│   │       └── events.ts          # 舆情事件列表（业务 store）
│   │
│   ├── layout/                    # 🖼 布局层
│   │   ├── index.vue              # 主 Layout 壳（侧边栏+导航+内容+页脚+标签）
│   │   └── components/            # Layout 子组件（侧边栏/导航/内容/页脚/标签页/搜索/通知/设置面板）
│   │
│   ├── constants/
│   │   └── platforms.ts           # 7 平台配置 + SEARCH_PLATFORMS 搜索平台映射
│   │
│   ├── plugins/                   # 插件初始化
│   │   ├── echarts.ts             # ECharts 全局注册
│   │   ├── elementPlus.ts         # Element Plus 全局组件注册
│   │   ├── i18n.ts                # 国际化
│   │   └── vxeTable.ts            # VXE Table 注册
│   │
│   ├── directives/                # 自定义指令
│   │   ├── auth/                  # 权限可见性
│   │   ├── perms/                 # 权限检查
│   │   ├── copy/                  # 一键复制
│   │   ├── longpress/             # 长按事件
│   │   ├── optimize/              # 性能优化（懒加载）
│   │   └── ripple/                # 水波纹效果
│   │
│   ├── utils/                     # 工具函数
│   │   ├── http/index.ts          # PureHttp 类（认证/管理类 API 的 HTTP 客户端，带 Token 刷新队列）
│   │   ├── auth.ts                # Token 读写（js-cookie + localStorage）
│   │   ├── message.ts             # Toast 消息封装
│   │   ├── mitt.ts                # 事件总线
│   │   ├── progress/              # NProgress 路由进度条
│   │   ├── tree.ts                # 数组→树转换
│   │   └── ...                    # 其他工具（打印/防抖/区域数据/头像等）
│   │
│   ├── style/                     # 全局样式
│   │   ├── reset.scss             # CSS Reset
│   │   ├── index.scss             # 全局公共样式
│   │   ├── tailwind.css           # Tailwind 入口
│   │   └── login.css              # 登录页专用样式
│   │
│   └── config/
│       └── index.ts               # 平台配置加载（platform-config.json）
```

## 三、页面—API 对接矩阵

### 3.1 舆情看板 (`views/welcome/index.vue`)

**路由**: `/dashboard`

**依赖的 API**:

| API | 方法 | 用途 | 调用时机 |
|------|:---:|------|------|
| `GET /api/events` | `listEvents(params)` | 获取事件列表 | 页面加载 + 搜索/采集后刷新 |
| `POST /api/crawler/search` | `searchCrawler(keyword)` | 关键词搜索采集 | 用户输入关键词点击搜索 |
| `POST /api/crawler/trigger` | `triggerCrawler({})` | 全网热点采集（admin only） | 点击"手动触发全网采集" |

**数据流**:
```
eventsStore.loadEvents() → listEvents() → GET /api/events
    ↓
eventData[] → EventCard 组件渲染
    ├── title, summary, heat_index, lifecycle_stage
    ├── sentiment_positive/negative/neutral
    ├── top_keywords[3]（情感着色标签）
    └── platforms[]（信源标签）
```

**后端需返回的字段**（`_event_item()`）:
```
id, title, summary, heat_index, core_heat, spread_heat, is_hot, hot_rank,
lifecycle_stage, sentiment_positive/negative/neutral, platform_count, platforms[],
top_keywords[{word, sentiment}], first_publish_time, last_activity_time
```

### 3.2 事件详情 (`views/events/detail.vue`)

**路由**: `/events/:id`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `GET /api/events/:id` | `getEvent(id)` | 事件完整详情 |
| `GET /api/events/:id/propagation` | `getEventPropagation(id)` | 传播图数据 |
| `GET /api/events/:id/report/export` | `exportEventReport(id)` | 导出 HTML 报告 |

**组件—数据对应关系**:

| 前端组件 | 数据来源 | 后端字段路径 |
|------|------|------|
| **统计卡片行** | 详情 API | `heat_index`, `sentiment_positive/negative/neutral`, `report.risk_data`, `articles.total` |
| **生命周期指示器** | 详情 API | `lifecycle_stage`（四阶段 CSS 进度条） |
| **报道量趋势图** | 详情 API | `trend.dates[]`, `trend.counts[]`, `trend.key_points[{name, coord}]` |
| **情感堆叠面积图** | 详情 API | `sentiment.daily[{positive, neutral, negative}]` 或 `sentiment.daily_trend` |
| **情感环形图** | 详情 API | `sentiment_positive/negative/neutral`（三个比例值） |
| **平台分布柱状图** | 详情 API | `platform.platforms[{platform, count, percentage}]` |
| **风险雷达图** | 详情 API | `heat_index`, `sentiment_negative`, `report.risk_data.score`, `platform.platforms.length` |
| **AI 研判摘要** | 详情 API | `report.overview_text`, `report.risk_data`（元数据栏: `time_code/location/key_figures/cause`） |
| **关键词云** | 详情 API | `keywords.keywords[{word, weight, sentiment, entity_type}]` |
| **传播网络图** | 传播 API | `propagation.graph.nodes[{id,name,category,symbolSize}], links[{source,target,value}]` |
| **关键节点时间轴** | 详情 API | `trend.key_points`（需 ≥1 个点） |
| **影响力排行** | 详情 API | `articles.articles[{title, platform, reposts_count, comments_count, likes_count}]` |
| **关联报道列表** | 详情 API | `articles.articles` 全部字段（含 `sentiment_label`, `is_suspicious`, `keywords`） |

**当前图表状态**:

| 图表 | 数据状态 | 备注 |
|------|:---:|------|
| 趋势折线图 | ✅ 真实 | `trend.dates/counts`，关键节点标注真实 |
| 情感堆叠面积图 | ✅ 真实 | `sentiment.daily`，无数据时用基础比例生成单点 |
| 情感环形图 | ✅ 真实 | 三值比例 |
| 平台柱状图 | ✅ 真实 | 品牌色 + 图标 + 报道量 |
| 风险雷达图 | ⚠️ 部分真实 | 6 维中有 2 维（传播速度/波及平台）来自现有字段，虚假风险/持续时间是固定值 45 |
| 词云 | ✅ 真实 | LLM 提取 30 词，金字塔字号，情感着色 |
| 传播网络图 | ✅ 真实 | 后端 propagation API，force 布局 |
| 时间轴 | ✅ 真实 | `trend.key_points` |
| 影响力排行 | ✅ 真实 | 无噪声，`??0` 处理 None 值 |
| AI 研判 | ✅ 真实 | LLM 生成摘要 + 关键词上下文 |
| 元数据栏 | ✅ 真实 | `time_code/location/key_figures/cause` LLM 提取 |

### 3.3 事件定向分析 (`views/analysis/index.vue`)

**路由**: `/analysis`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `POST /api/crawler/search` | `searchCrawler(kw, platforms, count)` | 提交定向分析任务 |
| `GET /api/tasks/:id` | `getTask(id)` | 2s 轮询任务进度 |
| `GET /api/tasks/my` | `getMyTasks()` | 历史任务列表 |

**状态机**: `idle → running（轮询） → completed（el-result） / failed（el-result error）`

### 3.4 智能问答 (`views/qa/index.vue`)

**路由**: `/qa`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `POST /api/qa/ask` | `askQuestion({event_id, question})` | 发送问题 |
| `GET /api/qa/history` | `getQaHistory()` | 历史记录 |

### 3.5 运维管理 (`views/admin/index.vue`)

**路由**: `/admin`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `POST /api/crawler/trigger` | `triggerCrawler({})` | 全网爬取 |
| `GET /api/crawler/status` | `getCrawlerStatus()` | 爬虫状态 |
| `POST /api/import/json` | `importJsonDocuments(docs)` | 导入样例数据 |
| `GET /api/tasks` | `getAllTasks()` | 全局任务列表 |

### 3.6 事件管理 (`views/admin/events.vue`)

**路由**: `/system/events`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `GET /api/events` | `listEvents()` | 事件列表（分页/搜索/删除） |
| `DELETE /api/events/:id` | `http.delete()` | 删除事件 |
| `GET /api/aggregation/runs` | `http.get()` | 聚合运行列表 |
| `GET /api/aggregation/runs/:id/clusters` | `http.get()` | 事件簇列表 |
| `POST /api/aggregation/clusters/:id/publish` | `http.post()` | 发布簇为事件 |
| `GET /api/aggregation/merge-candidates` | `http.get()` | 合并候选 |
| `POST /api/aggregation/merge-candidates/:id/confirm` | `http.post()` | 确认合并 |
| `POST /api/aggregation/merge-candidates/:id/reject` | `http.post()` | 拒绝合并 |

### 3.7 用户管理 (`views/admin/users.vue`)

**路由**: `/system/users`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `GET /api/admin/users` | `getUserList()` | 用户列表（分页/搜索/筛选） |
| `POST /api/admin/users` | `createUser()` | 新建用户 |
| `PUT /api/admin/users/:id` | `updateUser()` | 编辑用户 |
| `DELETE /api/admin/users/:id` | `deleteUser()` | 删除用户 |
| `PUT /api/admin/users/:id/password` | `resetUserPassword()` | 重置密码 |

### 3.8 登录 (`views/login/index.vue`)

**路由**: `/login`

**依赖的 API**:

| API | 方法 | 用途 |
|------|:---:|------|
| `POST /api/auth/login` | `loginByUsername({username, password})` | 登录获取 JWT |
| `POST /api/auth/register` | 注册组件使用 | 注册新用户 |

## 四、双重 HTTP 客户端

前端有两个 Axios 实例，分工不同：

### 4.1 `apiClient`（`api/client.ts`）

**用途**: 舆情业务 API（events/crawler/qa/tasks/import/opinionUser）

- `baseURL: "/api"`, `timeout: 15s`
- 请求拦截器：注入 `Bearer <token>`
- 响应拦截器：`return response.data`（解包 Axios response → 业务 JSON body）
- 401 时直接调用 `logOut()` 登出

### 4.2 `PureHttp`（`utils/http/index.ts`）

**用途**: 认证和管理类 API（auth/login, admin/users, routes, mock 上传）

- `baseURL: "/"`, `timeout: 10s`
- 请求拦截器：注入 `Bearer <token>` + 支持 `beforeRequestCallback` 钩子
- 响应拦截器：`return response.data`
- **Token 刷新队列**：401 时自动调用 `/refresh-token`，成功后重放队列中的所有请求，失败则登出

## 五、数据格式约定

### 5.1 通用响应格式

所有后端 API 必须返回：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

前端 `apiClient` 和 `PureHttp` 的响应拦截器都做了 `response.data` 解包，所以业务代码中 `response.data` 拿到的是 `data` 字段的内容。

### 5.2 事件列表 vs 事件详情

事件列表（看板用）返回轻量字段，事件详情返回完整嵌套结构。详见 `docs/backend_api_data_format.md`。

### 5.3 平台名约定

后端内部用英文代码（`weibo`/`zhihu`/`bilibili`/`baidu`），前端用 7 个中文名。`constants/platforms.ts` 的 `resolvePlatformName()` 负责转换。`api_contract_service.py` 的 `api_platform_name()` 负责后端侧转换。

## 六、路由与权限

### 6.1 路由表

```
/ (Layout, rank 1)
├── /dashboard          舆情看板（所有人）
├── /events/:id         事件详情（隐藏菜单）
├── /analysis           事件定向分析（所有人）
├── /qa                 智能问答（所有人）
├── /user               个人中心（所有人）
└── /admin              运维管理（admin only）

/system (Layout, rank 99, admin only)
├── /system/users       用户管理
└── /system/events      事件管理

/login                  登录（无 Layout）
/access-denied          403
/server-error           500
/:pathMatch(.*)*        404
```

### 6.2 权限控制

- **路由级**: `meta.roles: ["admin"]` → `filterNoPermissionTree()` 过滤菜单 → 路由守卫拦截直接 URL 访问
- **按钮级**: `<Auth>` / `<Perms>` 组件 + `v-auth` / `v-perms` 指令（当前未实际启用，`permissions: ["*:*:*"]`）

### 6.3 动态路由

`initRouter()` 调用 `GET /get-async-routes` 获取后端动态路由。`vite-plugin-fake-server` 拦截此请求，`mock/asyncRoutes.ts` 当前返回空数组 `[]`（已清理模板残留）。

## 七、状态管理 (Pinia)

| Store | 文件 | 核心状态 | 持久化 |
|------|------|------|:---:|
| `useUserStore` | `store/user.ts` | username, roles, permissions, token, avatar | Cookie + localStorage |
| `usePermissionStore` | `store/permission.ts` | constantMenus, wholeMenus, flatteningRoutes | 无（每次刷新重建） |
| `useAppStore` | `store/app.ts` | sidebar, layout, device, viewportSize | localStorage |
| `useSettingStore` | `store/settings.ts` | title, fixedHeader, hiddenSideBar | localStorage |
| `useMultiTagsStore` | `store/multiTags.ts` | multiTags[]（标签页列表） | localStorage |
| `useEpThemeStore` | `store/epTheme.ts` | epThemeColor, epTheme | localStorage |
| `useEventsStore` | `store/events.ts` | events[], total, loading | 无 |

## 八、关键全局注册

`main.ts` 按顺序执行：

1. 自定义指令（auth, perms, copy, longpress, ripple, optimize）
2. 全局图标组件（IconifyIconOffline, IconifyIconOnline, FontIcon）
3. 权限组件（Auth, Perms）
4. vue-tippy（tooltip）
5. `getPlatformConfig()` → Pinia → Router → 响应式存储注入 → 插件链 → mount

## 九、数据流向总图

```
浏览器 URL → Vue Router → 路由守卫（token校验）
    ↓
Layout 壳渲染（侧边栏+导航+标签）
    ↓
Page Component 加载
    ↓
┌──────────────────────────────────┐
│  onMounted / watch               │
│    ↓                             │
│  apiClient.get/post(...)         │  ← Axios 拦截器注入 Bearer Token
│    ↓                             │
│  Vite Proxy /api → Flask :5000   │
│    ↓                             │
│  JSON Response                   │
│    ↓                             │
│  Axios 拦截器: response.data     │  ← 解包
│    ↓                             │
│  ref.value = data                │  ← 响应式绑定
│    ↓                             │
│  ECharts setOption() / v-for     │  ← 渲染
└──────────────────────────────────┘
```

---

## 十、与后端算法的对接点速查

| 前端组件 | 前端文件 | 后端算法文件 | 关键函数 |
|------|------|------|------|
| 词云 | `detail.vue:780-900` | `llm_keywords.py` + `event_service.py:_event_keywords()` | `extract_keywords_llm()`, 排名衰减聚合 |
| 传播图 | `detail.vue:621-680` | `propagation/builder.py` | `build_propagation_graph()` |
| 情感图 | `detail.vue:290-430` | `sentiment_analyzer.py` + `sentiment_aggregator.py` | `analyze_sentiment()`, `summarize_sentiment()` |
| 趋势图 | `detail.vue:226-286` | `event_service.py:304-322` | `trend.dates/counts` 从 `EventHeatSnapshot` 构建 |
| 风险雷达 | `detail.vue:562-618` | `fake_detector.py` | `batch_assess_articles()`, `assess_suspicious_risk()` |
| 生命周期 | `detail.vue:44-55` | `trend_predictor.py` | `predict_lifecycle_stage()` |
| 热度卡片 | `detail.vue:1020-1060` | `heat_calculator.py` + `event_aggregation_service.py:91-93` | fallback 公式 |
| AI 标题 | `EventCard.vue` | `event_aggregation_service.py:_ai_generate_title()` | LLM 生成 ≤20 字标题 |
| AI 摘要 | `detail.vue:1150-1190` | `event_aggregation_service.py:_ai_generate_summary()` | LLM 生成 + 关键词上下文 |
| 元数据 | `detail.vue:1150-1165` | `event_service.py:_extract_event_metadata()` | LLM 提取 time_code/location/key_figures/cause |

---

> 本文档随代码变更持续更新。最近更新：2026-07-13
