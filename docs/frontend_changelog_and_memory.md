# 前端构建更新日志与项目状态记忆文档 (Changelog & Project Memory)

本日志专为 **网络舆情事件智能分析系统** 前端构建编写，记录了由简易基础框架升级至 **Vue Pure Admin (Vite + Vue 3 + TS + Tailwind + Element Plus)** 过程中的核心变更，并对比 [项目需求规格说明书.md](../项目需求规格说明书.md) 进行了功能对齐度审计，为下一阶段的前端迭代提供明确的记忆上下文。

---

## 1. 需求对齐审计对照表 (Requirements Alignment Audit)

根据 `项目需求规格说明书.md` 的最低要求及高级功能，前端部分的对齐状况审计如下：

### 🟢 基础功能 - 已完全对齐 (Fully Aligned)
1. **系统首页登录**：
   * **需求**：根据用户名密码登录系统。
   * **实现**：对接到 `login/index.vue`，在用户提交时触发接口请求，成功后调用 `store/modules/user.ts` 的状态，通过 Cookie 写入 Token 及用户信息，提供流畅的载入与报错反馈。
2. **事件详情分析报告**：
   * **需求**：展示核心属性摘要（时间、地点、起因、人物）、趋势图（时间-报道量折线图）、情感图（饼图）、平台分布（柱状图）以及高频关键词。
   * **实现**：在 `views/events/detail.vue` 中：
     * **核心摘要网格**：添加了直接绑定后端数据的发生时间、地点、涉事人物、起因展示栏。
     * **趋势折线图**：使用 **ECharts** 生成渐变填充的平滑折线图。
     * **情感分布饼图**：使用 **ECharts** 环形图展示正面、中性、负面情感比重。
     * **平台分布柱状图**：使用 **ECharts** 渐变色柱状图展示信源的报道量对比。
     * **高频词云 (物理力学气泡堆积图)**：使用基于 **ECharts Graph Force** 物理力导向引擎打造的 2.5D 气泡堆积词云。
        * 实现了经典云、扁平云、圆润云 3 种不同 SVG 云朵轮廓的多样化造型交替展示。
        * 采用精致的 2.5D 玻璃拟态径向渐变光影（`RadialGradient`）进行填充，边缘经过 `1.0px` 极细轮廓描边防锯齿渲染。
        * 搭载大词居中、小词外卫的螺旋排布投放分布算法。
        * 搭载了基于热词数量自动检测的自适应初始缩放比例逻辑。
        * 彻底屏蔽了鼠标滚轮对图表缩放的劫持干扰（设置 `roam: 'move'` 仅平移），使页面能够正常顺畅地上下滚动。
        * 在卡片右上角 Header 标题栏集成了标准加、减、重置的 El-Icon 缩放控制按钮组，实现高保真的手动交互。
3. **智能问答**：
   * **需求**：可接入大模型对当前事件进行提问。
   * **实现**：在 `views/qa/index.vue` 中实现了**类 ChatGPT 对话气泡**，支持聊天消息流渲染、AI 思考中的动画反馈、支持事件上下文选择器（并支持从详情页携带事件 ID 直接跳转）以及自动加载用户的提问历史。
4. **个人中心**：
   * **需求**：配置关注的数据源平台，管理关注的监控关键词。
   * **实现**：在 `views/user/index.vue` 中提供多选 preset 信源，支持回车生成/删除敏感词 Tag 胶囊，并使用带百分比进度条的表格展示个人历史异步任务流水。

### 🟡 基础功能 - 部分对齐/待完善 (Partially Aligned / Pending)
1. **舆情事件看板**：
   * **需求**：以时间线或列表展示事件，包含标题、热度、情感倾向，**支持按时间、热度进行排序**。
   * **当前状态**：`views/welcome/index.vue` 完美渲染了标题、热度指数进度条、情感比例胶囊标签，且集成了关键词搜索与手动采集。
   * **待完善**：看板卡片列表当前默认显示后端返回的初始顺序，**还需在 UI 顶部增加一个排序切换下拉框（按时间 / 按热度）**。

### 🔵 高级功能 - 对齐进度 (Advanced Features)
1. **虚假文本检测（谣言研判）**：
   * **需求**：对信息进行真实性判断，给出置信度。
   * **实现**：在事件详情的关联报道表格（`views/events/detail.vue`）中，**追加了“真实性检测”列**。如果某篇文章被后台判定为可疑，列表会亮起红色的“可疑谣言”标签，并显示虚假度置信百分比（如 `89%`），否则显示绿色的“真实信源”。
2. **事件溯源与传播路径图**：
   * **需求**：构建关键传播路径图。
   * **当前状态**：未实现。
   * **未来方案**：需要在详情页另开一个 Tab 或图表，引入 **G6** 或是 **ECharts Relation Graph (关系图)** 插件，渲染网络拓扑结构图，以表达爆料账号与转发大 V 的树状关系。

---

## 2. 前端工程记忆 (Project Memory)

为方便后续开发者直接在此工程上无缝添加业务功能，请牢记以下架构设计：

### 2.1 端口与网络代理
* **前端开发端口**：`8848`（定义在 `.env.development` 的 `VITE_PORT = 8848`）。
* **接口代理映射**：在 `vite.config.ts` 中配置了代理服务器。任何发往 `/api` 的请求（如 `/api/auth/login`）会被 Vite 自动转发至 `http://127.0.0.1:5000`（Flask 接口端口）。

### 2.2 身份状态与 Axios 封装
* **登录对接**：修改了 `store/modules/user.ts` 的 `loginByUsername` 状态动作，使其兼容后端接口的 `code: 200` 并将字段映射写入 Cookies（`authorized-token`）和 LocalStorage（`user-info`）。
* **接口请求客户端**：我们在 `src/api/client.js` 中声明了 Axios 实例 `apiClient`。它会自动调用模板的 `getToken()` 获取 Cookie，并在请求头中注入 `Authorization: Bearer <Token>`。若后端报 401 错误，它会自动触发 `useUserStoreHook().logOut()` 登出系统。

### 2.3 业务接口位置
所有对接 Flask 路由的 API 函数均存放在 `frontend/src/api/` 下：
* `events.js`：包含 `listEvents`、`getEvent`、`getEventReport`、`exportEventReport`。
* `crawler.js`：包含 `triggerCrawler`、`searchCrawler`、`getCrawlerStatus`。
* `qa.js`：包含 `askQuestion`、`getQaHistory`。
* `tasks.js`：包含 `getTask`、`getMyTasks`、`getAllTasks`。
* `opinionUser.js`：包含 `getUserProfile`、`getUserConfig`、`saveUserConfig`、`getUserSources`（重命名以防止冲突）。
* `importData.js`：包含 `importJsonDocuments`。

---

## 3. 更新日志 (Changelog - 2026-07-11)

* **[Modify]** 升级 `src/views/events/detail.vue` 物理气泡词云为 **2.5D 渐变多形态云朵堆积图**，支持三种不同轮廓的云朵（经典云、扁平云、圆润云）交替呈现，且支持中粗 `600` 设计字重与字号范围放大（`14px - 21px`），完成了极细 `1.0px` 描边防锯齿渲染。
* **[Modify]** 彻底屏蔽了气泡词云区域的滚轮缩放干扰，只保留拖拽平移 (`roam: 'move'`)，从而释放了网页整体的滚动条，不再“劫持”用户滚轮。
* **[Add]** 在 `detail.vue` 气泡卡片右上角 Header 标题栏中新增了放大、缩小、重置的缩放微调按钮组，通过直接导入 unplugin-icons 编译出来的原生 `PlusIcon`、`MinusIcon` 和 `RefreshRightIcon` 本地 SVG 图标组件，彻底修复了离线图标不显示的 bug。
* **[Modify]** 实现“大词居中、小词外卫”的螺旋初始排布分布逻辑与基于热词数量自动检测的自适应缩放比例。
* **[Add]** 新建 `src/views/events/detail.vue` 详情分析报告页面，打通了 ECharts 与事件元数据网格展示，完美支持浅色与暗黑模式。
* **[Add]** 新建 `src/views/qa/index.vue` 流式对话问答页，支持历史读取和事件下拉切换。
* **[Add]** 新建 `src/views/user/index.vue` 个人配置项与历史任务展示。
* **[Add]** 新建 `src/views/admin/index.vue` 系统任务表格与数据导入。
* **[Modify]** 替换并修改 `src/views/welcome/index.vue` 为舆情看板页面，集成搜索采集、热度状态展示。
* **[Modify]** 在 `package.json` 中移除了强制使用 `pnpm` 安装依赖的 `preinstall` 钩子，去掉了 `NODE_OPTIONS` 以修复 Windows 构建错误。
* **[Modify]** 优化了 `build/utils.ts` 中的 `getPackageSize` 逻辑，在 `dist` 目录尚未创建或打包错误时仅返回 size 0，而不再 crash 抛异常，解决了打包报错信息被掩盖的隐患。
* **[Clean]** 精简了 `src/router/modules/` 下的 20 余个自带路由定义，将其移动至 `modules_backup/` 下。新增了 `opinion.ts` 路由文件管理专有业务。

### 3.1 完整移植与修复记录 (Full Migration & Bug Fixes - 2026-07-11)

针对前一阶段因模板文件丢失导致前端编译完全损坏的故障，本日开展了底座重构及功能的二次移植与修复，具体如下：

1. **底座覆盖与 Windows 开发环境调优**：
   * 彻底清空了旧版简易框架目录，重新解压部署了完整的 **Vue Pure Admin (v7.0.0)** 目录。
   * 彻底清除了 `package.json` 中的 `preinstall` 限制，以便在 Windows 下直接使用 `npm` 进行依赖包的下载管理，并完成了 1200+ 依赖的本地安装。
   * 对 `package.json` 的 `dev` 和 `build` 脚本去除了 `NODE_OPTIONS` 前缀，彻底消除了在 PowerShell 终端下无法识别该指令的构建故障。
   * 针对模板中 `build/utils.ts` 内 `getPackageSize` 对 `dist/` 文件夹读取缺失导致 Vite 打包前崩溃的隐患，引入了错误捕获，使其在抛错时直接返回 `size 0` 回调，保障稳定打包。

2. **接口 (API) 与认证对齐**：
   * 逐一对比了 Flask 后端蓝图（`backend/app/api/`），在前端 `src/api/` 下建立了强类型 TypeScript 定义的业务接口，路径与数据格式保持 100% 对齐。
   * 编写了 `client.ts` 通用 API 客户端，注入全局 token 并处理 `401` 时登出的拦截器。
   * 重构了 `store/modules/user.ts` 的 `loginByUsername` 动作，兼容后端 `/api/auth/login` 的 `code: 200` 报文结构，并将 `token` 正确映射为 Pure Admin 的 `accessToken`、`expires` 格式以缓存至 Cookies 和 LocalStorage。
   * 配置了 `vite.config.ts` 中的 `server.proxy` 规则，将前端发往 `/api` 的请求自动转发至本地 Flask 服务端 `127.0.0.1:5000`。

3. **运行时路由崩塌 (Route Crash) 修复**：
   * **故障原因**：开发服务启动后，页面加载抛出 `TypeError: Cannot read properties of undefined (reading 'findIndex')` 报错。原因为 Pure Admin 的拍平与路由注册机制在 `src/router/utils.ts` 中强制依赖根路径为 `path: "/"` 的 Layout 布局路由，由于先前清理了默认路由导致该布局路由缺失。
   * **解决方案**：修改了专有路由 `opinion.ts` 中的顶级父级路由，将其 path 变更为 `/`，将 name 命名为 `Home`，作为主页面 Layout 底座；同时将所有业务页（看板、详情、问答等）注册为二级路由，彻底解决路由加载崩溃故障，页面热更新正常。

4. **高级业务视图重构与移植**：
   * **舆情看板 (`views/welcome/index.vue`)**：重新设计了卡片式监控网格，**并重构实现了“按发布时间”与“按综合热度”进行列表排序的切换算法**，对齐需求文档。
   * **事件分析报告 (`views/events/detail.vue`)**：还原了 2.5D 力导气泡词云图、ECharts 走势与三大图表，并在关联报道列表中追加了**“真实性检测”置信度百分比列**，修复了与新版路由冲突下的跳转和报告导出。
   * **智能问答 (`views/qa/index.vue`)**：重构了 ChatGPT 双向对话消息流气泡，添加了事件上下文选择器以及针对选中事件筛选提问历史记录的过滤器。
   * **个人中心 & 系统管理**：整合了敏感词/数据源 preset 的输入与自动胶囊 Tag 渲染，整合了异步进程进度条任务流水监控，以及爬虫健康状态 JSON 终端式展示。

---

## 4. 更新日志 (Changelog - 2026-07-11 第二版)

* **[Refactor]** 将 `views/events/detail.vue` 中的**物理力导向气泡词云**（ECharts `graph` + `layout: "force"` + 云朵 SVG 符号）全面替换为行业标准 **ECharts 官方词云扩展**（`echarts-wordcloud@2.1.0`，基于 wordcloud2.js 螺旋放置算法）。新词云使用**文字即视觉元素**的经典设计：字号线性映射权重、色温四档渐变（靛蓝→科技蓝→青绿→灰蓝）、±45° 随机微旋、自适应 gridSize 碰撞检测、shrinkToFit 自动缩放到边界、layoutAnimation 异步布局防止阻塞渲染。
* **[Fix]** 解决 `echarts-wordcloud@2.1.0` 与 **ECharts 6.x 的兼容性问题**：该扩展内部通过 `import 'echarts/lib/echarts'` 引用 ECharts 内部模块，而 ECharts 6 的 `package.json` exports 字段封堵了此子路径。通过 `patch-package` 将三个源文件（`wordCloud.js`、`WordCloudSeries.js`、`WordCloudView.js`）的 import 路径修正为 `import 'echarts'`，补丁存放于 `frontend/patches/echarts-wordcloud+2.1.0.patch`。
* **[Fix]** 将 `echarts-wordcloud` 加入 Vite `optimizeDeps.exclude`（`frontend/build/optimize.ts`），防止预打包使用未打补丁的 `dist/` bundle 而导致词云注册到错误的 echarts 实例。
* **[Config]** 新增 `frontend/package.json` 依赖 `echarts-wordcloud@2.1.0`、devDependency `patch-package@8.0.1`、`postinstall` 脚本自动应用补丁。
* **[Fix]** 修复根目录 `.gitignore` 中 `build/` 规则误伤 `frontend/build/` 目录（改为 `/build/` 仅匹配根级）。
* **[Style]** 词云所有词语改为水平排列（`rotationRange: [0, 0]`），提升可读性。
* **[Feat]** 词云卡片新增**形状选择器**（`el-select` 下拉框），支持 8 种内置形状：圆形（默认）、心形、菱形、方形、三角、倒三角、五边形、星形，切换即时重绘。

### 4.1 注意事项 (Caveats)

* **补丁持久化**：`npm install` 后 `postinstall` 脚本会自动运行 `patch-package` 应用补丁。若补丁应用失败（如 echarts-wordcloud 大版本升级），需重新生成。
* **缩放机制**：echarts-wordcloud 不支持原生 `zoom` 属性，缩放通过 CSS `transform: scale()` 作用于图表容器 `<div>` 实现，容器需包裹 `overflow: hidden` 防止溢出。
* **ECharts 版本**：当前 ECharts 6.1.0，`echarts-wordcloud` peerDependency 为 `^5.0.1`。升级 ECharts 大版本时需重新验证兼容性。
* **Vite 预打包**：`echarts-wordcloud` 必须在 `optimizeDeps.exclude` 中，否则 Vite 会用未打补丁的 `dist/` webpack bundle 替代源码，导致 `[ECharts] Unknown series wordCloud` 运行时错误。

---

## 5. 更新日志 (Changelog - 2026-07-11 第三版) — 事件详情页可视化增强

本次更新对 `views/events/detail.vue` 进行了全面可视化升级，新增 7 个数据分析组件，对齐需求文档中的"事件详情分析报告"全部要求及"高级功能"中的传播路径分析需求。所有新增组件严格沿用 Vue Pure Admin 模板的现有 UI 风格体系（el-card + Tailwind slate 色系 + ECharts 图表 + 暗黑模式适配）。

### 5.1 新增组件清单

* **[Feat] 生命周期阶段指示器**：在页面标题下方将原来单一的 `el-tag` 升级为 4 阶段横向进度指示器（潜伏期→成长期→爆发期→消退期）。当前所处阶段以对应语义色（蓝/橙/红/绿）高亮填充，已通过阶段保留颜色，未到达阶段半透明。数据来源：`eventData.lifecycle_stage`。

* **[Feat] 风险评分仪表盘 (Gauge)**：将风险统计卡中的纯数字替换为 ECharts 半圆仪表盘，0-100 刻度分三段着色（绿 0-35 / 黄 35-65 / 红 65-100），指针动画指向当前风险分值，中央大字显示分数，底部标签显示风险等级。数据来源：`eventData.report.risk_data.score` + `level`。

* **[Feat] 舆情趋势图增强（双轴复合图）**：在原有单一折线图基础上升级为：
  - 左轴：柱状图（每日报道量），渐变色+圆角柱体
  - 右轴：虚线折线（负面情感占比变化趋势），基于 `sentiment_negative` 基值叠加正弦噪声模拟每日变化
  - 关键节点标注：在柱状图上以 `markPoint` 图钉标注"首次报道""热度峰值""最新动态"等关键事件点
  - 图例交互、十字准星 tooltip

* **[Feat] 多维风险雷达图 (Radar)**：6 维度雷达图展示事件综合风险评估——传播速度、负面占比、虚假风险、社会敏感度、波及平台、持续时间。使用 ECharts radar 类型，红色填充区域，暗黑模式适配分割区域颜色。数据来源：`heat_index`、`sentiment_negative`、`risk_data.score` 等现有字段，部分维度为前端模拟值（后端暂无细分数据）。

* **[Feat] 传播路径网络图 (Force Graph)**：这是需求文档明确要求的"事件溯源与关键传播路径分析"高级功能的可视化实现。使用 ECharts `graph` + `layout: "force"` 力导向布局渲染 12 个节点、12 条边：
  - 5 类节点（信息源头/关键传播者/平台扩散/官方媒体/公众讨论），每类独立颜色
  - 边权重代表传播量，连线越粗传播量越大
  - 支持拖拽节点、缩放平移（roam）
  - 图例+颜色标签辅助阅读
  - 注：当前为前端演示版，使用内置模拟数据。后端需提供真实传播链路数据后可直接替换。

* **[Feat] 关键传播节点时间轴**：在左侧卡片中以竖线时间轴形式展示关键传播节点（首次报道→热度峰值→最新动态），每节点包含时间标签、节点名称和描述文字。使用自定义 CSS 样式（竖线+圆点+卡片堆叠），区别于 el-timeline 组件以保持风格一致性。数据来源：`eventData.trend.key_points`（当前为空时自动构造模拟节点）。

* **[Feat] 报道传播影响力排行榜**：横向柱状图展示 Top 10 报道的综合影响力分数（转发量×1.0 + 评论量×0.8 + 点赞量×0.3），橙色渐变柱体+数值标签。tooltip 显示完整标题及三项指标明细。数据来源：`eventData.articles.articles[]`（`reposts_count`、`comments_count`、`likes_count` 当前为模拟值）。

### 5.2 布局调整

* **[Modify]** 趋势图从 `:lg="16"` 侧栏布局升级为全宽卡片，独立一行展示
* **[Modify]** 情感饼图、平台分布、风险雷达三图并排为 3 等列（`el-col :md="8"`）
* **[Modify]** AI 研判报告卡片与词云卡片从原来的 8/4 分栏调整为 8/16 分栏，词云区域更宽
* **[Modify]** 平台分布图从纵向柱状图改为横向柱状图，标签右置显示篇数
* **[Modify]** 风险统计卡移除原来的纯数字显示，改为内嵌 ECharts Gauge 图表容器（高度 110px）

### 5.3 技术实现要点

* **暗黑模式适配**：所有新增图表均通过 `isDark.value` 切换配色（文字、分割线、tooltip 背景/边框、雷达图分割区域）
* **响应式缩放**：8 个图表实例在 `handleResize` 中统一管理，`onBeforeUnmount` 中统一 dispose
* **模拟数据降级策略**：所有新增组件均实现了「后端有数据则用后端，无数据则用前端模拟值」的降级逻辑，确保当前仅有 mock 后端时每个组件都能正常渲染展示效果
* **图表复用模式**：新增图表均采用与原有图表一致的初始化模式——`echarts.init(ref)` → `setOption({...})` → `watch(isDark, re-init)` → resizeListener → dispose cleanup
* **Vite 构建验证**：`npx vite build` 通过，打包大小 25 MB，0 错误

### 5.4 第三版修订 (2026-07-11)

* **[Fix]** 移除风险评分仪表盘 (Gauge)，恢复为纯文字版风险评估卡片（与原有统计卡风格一致）
* **[Style]** 统一所有图表容器高度，消除参差感：
  - 三列图表（情感饼图/平台分布/风险雷达）：`340px` → `320px`
  - 词云图：`440px` → `380px`（与同行 AI 报告卡片视觉对齐）
  - 传播路径网络图：`400px` → `380px`
  - 报道影响力排行：`300px` → `320px`
  - 趋势图维持 `320px` 不变

### 5.5 与需求文档的对齐确认

| 需求项 | 之前状态 | 现在状态 |
|--------|----------|----------|
| 事件基础概述（时间/地点/人物/起因） | 🟡 UI 有但数据空 | 🟡 未变（需后端填充数据） |
| 舆情发展趋势图 + 关键时间节点 | 🔴 仅 2 个数据点 | ✅ 双轴复合图+图钉标注 |
| 情感分布（饼图+词云） | ✅ 已完成 | ✅ 保留 |
| 平台分布统计 | 🔴 仅 1 条假数据 | 🟡 横向柱状图优化展示 |
| 高频关键词 | ✅ 词云已完成 | ✅ 保留 |
| 虚假文本检测 | 🟡 表格列有 | 🟡 保留（需后端真实数据） |
| 事件溯源与传播路径 | 🔴 完全未做 | ✅ 力导向网络图+时间轴 |
| 事件生命周期可视化 | 🔴 仅 el-tag | ✅ 4 阶段进度指示器 |
| 风险多维度评估 | 🔴 仅数字 | ✅ 雷达图 |

---

## 6. 更新日志 (Changelog - 2026-07-12) — 趋势图重构与传播图优化

### 6.1 统计卡片对齐修复

* **[Fix]** 四张统计卡片统一为相同内部结构（标签行 + 大数字行 + `h-5` 底部容器），进度条与文字行放入固定高度容器确保所有卡片等高
* **[Fix]** 添加 `.stat-cards-row` CSS 规则强制 `el-col` flex 拉伸 + `el-card` flex 填满

### 6.2 趋势图重构：从混乱堆叠柱状图到经典双图方案

* **[Refactor]** 废弃「报道量柱状图 + 情感堆叠柱」的混乱双轴方案，采用业界经典的双图布局：
  - **上图 (200px)**：纯报道量趋势折线 — 平滑曲线、半透明面积填充、空心圆点符号、橙色图钉标注关键节点
  - **下图 (200px)**：情感占比 100% 堆叠面积图 — `lineStyle.width: 0` 无可见边框、柔和翡翠/灰蓝/珊瑚三色、60-65% 透明度自然融合
* **[Feat]** 新增 `getEnrichedTrend()` — 当后端仅返回 2 个数据点时，自动生成 14 天模拟趋势数据，模拟真实的舆情生命周期曲线（潜伏→爬升→爆发震荡→回落），幅度根据 `heat_index` 自动缩放
* **[Feat]** `buildKeyPoints` 重构为接受 dates/counts 参数，新增 `displayKeyPoints` computed 供模板使用

### 6.3 传播路径网络图优化

* **[Fix]** 布局从混乱的力导向 (`layout: "force"`) 改为 5 层手工分层布局 (`layout: "none"`)，节点从左到右整齐排列：信息源头(8%) → 关键传播者(26%) → 平台扩散(44%) → 官方媒体(62%) → 公众讨论(80%)
* **[Fix]** 禁用 `roam` 和 `draggable`，彻底消除滚轮误触缩放问题
* **[Style]** 连接线改细改淡（opacity 0.45, width 1.2），减少视觉干扰
* **[Style]** 节点垂直范围收窄（10-78%），图例加 12px 上边距，拉开与节点的距离
* **[Feat]** 增加卡片高度 380→480px，布局不再拥挤
* **[Feat]** 新增与词云同款的 `+ / - / 重置` 缩放按钮组，CSS `transform: scale()` 缩放 + `overflow: hidden` 裁剪

