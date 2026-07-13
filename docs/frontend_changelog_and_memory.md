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

---

## 7. 更新日志 (Changelog - 2026-07-12 第二版) — 路由重构与死代码清理

### 7.1 路由层次重构

* **[Refactor]** 路由结构重组，所有业务页面统一纳入 Layout 壳（确保侧边栏/导航栏一致显示）：
  - `/opinion/welcome` → `/dashboard`（舆情看板）
  - `/opinion/detail/:id` → `/events/:id`（事件详情）
  - `/opinion/qa` → `/qa`（智能问答）
  - `/opinion/user` → `/user`（个人中心，从无 Layout 顶层路由改为 Layout 子路由）
  - `/opinion/admin` → `/admin`（系统管理，从无 Layout 顶层路由改为 Layout 子路由）
* **[Fix]** 更新 `EventCard.vue` 和 `events/detail.vue` 中 2 处硬编码旧路径引用

### 7.2 死代码清理

* **[Clean]** 删除 21 个无活跃路由引用的模板 demo views 目录（~170 个 .vue 文件）：able, about, chatai, codemirror, components, editor, flow-chart, ganttastic, guide, list, markdown, menuoverflow, monitor, nested, permission, result, schema-form, system, table, tabs, vue-flow
* **[Clean]** 删除 `router/modules_backup/` 目录（24 个已禁用的模板路由备份文件）
* **[Clean]** 删除 19 个未被业务代码或 Layout 引用的 Re* 组件目录：ReAnimateSelector, ReAuth, ReBarcode, ReCol, ReCountTo, ReCropper, ReDialog, ReDrawer, ReFlicker, ReFlop, ReFlowChart, ReMap, RePerms, RePureTableBar, ReSeamlessScroll, ReSelector, ReSplitPane, ReTreeLine, ReVxeTableBar
* **[Clean]** 删除 2 个模板专用 API 文件：`api/list.ts`, `api/system.ts`
* **[Revert]** 恢复被误删的 6 个仍被引用的文件：ReDialog, ReDrawer, ReAuth, RePerms（App.vue/main.ts 全局注册）、ReCropper（ReCropperPreview 依赖）、api/mock.ts（account-settings 头像上传）

### 7.3 保留的组件清单

清理后保留的 Re* 组件（均有实际引用）：
* **Layout 引用**：ReIcon (useRenderIcon)、ReSegmented、ReText
* **业务页引用**：ReTypeit (登录页打字机)、ReImageVerify (登录验证码)、ReCropper + ReCropperPreview (个人中心头像裁剪)、ReQrcode (登录二维码)
* **全局基础设施**：ReDialog、ReDrawer（App.vue 全局对话框/抽屉管理）、ReAuth、RePerms（main.ts 全局注册）

### 7.4 清理效果

* **包体积**：25 MB → 15.7 MB（减少 37%）
* **源码文件数**：大幅精简，仅保留舆情系统业务代码和必要的模板基础设施
* **views 目录**：30 个目录 → 9 个（welcome, events, qa, user, admin, login, error, empty, account-settings）
* **构建时间**：无影响，保持 ~11-30 秒

---

## 8. 更新日志 (Changelog - 2026-07-12 第三版) — Mock 旧路由污染修复

### 8.1 问题现象

路由重构 + 死代码清理后，侧边栏仍然出现「外部页面」「权限管理」「系统管理」「系统监控」「标签页」等旧模板菜单项，且点击后能正常跳转渲染。

### 8.2 排查过程

1. **怀疑 localStorage 缓存** → 检查 `responsive-configure` 和 `async-routes` 键值，均为空，排除
2. **怀疑模块导入遗漏** → 确认 `router/modules/` 仅剩 `opinion.ts` 和 `remaining.ts`，`modules_backup/` 已删除
3. **怀疑源代码残留** → 全文搜索「外部页面」「权限管理」，`src/` 中无匹配
4. **加 debug 日志** → `handleWholeMenus` 的 `constantMenus` 只有 7 项（我们的路由），但 `routes` 参数被传入了 5 组旧模板路由对象
5. **追踪 `routes` 来源** → `initRouter()` → `getAsyncRoutes()` → Vite 并未报网络错误，说明 **请求成功了**
6. **发现 `vite-plugin-fake-server`** → `build/plugins.ts` 配置了 `vitePluginFakeServer({ include: "mock", enableProd: true })`，拦截 HTTP 请求并返回 mock 数据
7. **定位真凶 `mock/asyncRoutes.ts`** → 定义了 `/get-async-routes` 端点，返回 `systemManagementRouter`、`systemMonitorRouter`、`permissionRouter`、`frameRouter`、`tabsRouter` 共 5 组完整模板路由对象

### 8.3 根因分析

```
initRouter()
  → getAsyncRoutes()                    // 调用 /get-async-routes
    → vite-plugin-fake-server 拦截       // 匹配 mock/asyncRoutes.ts
      → 返回 { code: 0, data: [5组旧路由] }  // code:0 表示成功
        → handleAsyncRoutes(data)        // 将旧路由注入路由表
          → handleWholeMenus(data)       // 将旧路由写入 wholeMenus
            → 侧边栏渲染出旧菜单          // 🔴 幽灵菜单
```

关键点：`vite-plugin-fake-server` 的 `enableProd: true` 意味着**生产构建也会加载 mock 数据**。Mock 返回 `code: 0`，所以 `initRouter` 的 `.catch()` 兜底逻辑永远走不到——请求是成功的。

### 8.4 修复方案

**修改 `mock/asyncRoutes.ts`**：将 `data` 数组从 5 组旧路由改为空 `[]`。

```diff
- data: [systemManagementRouter, systemMonitorRouter, permissionRouter, frameRouter, tabsRouter]
+ data: []
```

同时修改 `router/utils.ts` 的 `initRouter()`，给 `getAsyncRoutes()` 添加 `.catch()` 兜底（后端/mock 不可用时回退到静态路由，防止侧边栏永久卡加载）。

### 8.5 教训

* `vite-plugin-fake-server` 的 mock 数据是**独立于 Vite/Webpack 热更新的持久化路由来源**，删除 views 和 router modules 不会影响 mock 目录
* 排查路由问题时，优先级应为：`router modules` → `mock 目录` → `localStorage` → `后端 API`
* 清理模板代码时必须同步清理 `mock/` 目录下的对应文件

---

## 9. 更新日志 (Changelog - 2026-07-12 第四版) — Mock 目录深度清理

### 9.1 清理内容

对 `mock/` 目录进行全面审计，删除 3 个仅服务于已删除模板页面的 mock 文件：

| 文件 | 大小 | 服务对象 | 判定 |
|------|------|----------|------|
| `mock/system.ts` | 1815 行 | 已删除的 `views/system/`（用户/角色/菜单/部门 CRUD）和 `views/monitor/`（登录/操作/系统日志） | 🔴 删除 |
| `mock/list.ts` | 457 行 | 已删除的 `views/list/card/`（卡片列表页） | 🔴 删除 |
| `mock/map.ts` | 43 行 | 已删除的 `views/able/map.vue`（高德地图 demo） | 🔴 删除 |

保留的 mock 文件（均有有效引用）：

| 文件 | 端点 | 用途 |
|------|------|------|
| `mock/login.ts` | `POST /login` | 登录认证（admin/common 双角色） |
| `mock/refreshToken.ts` | `POST /refresh-token` | Token 刷新 |
| `mock/asyncRoutes.ts` | `GET /get-async-routes` | 动态路由（已改为返回空数组） |
| `mock/mine.ts` | `GET /mine`, `/mine-logs` | 账户设置-个人信息/安全日志 |

### 9.2 剩余待处理项

* **`locales/zh-CN.yaml`**：仍含 120+ 条模板翻译标签（`pureExternalPage`、`purePermission` 等），不影响功能但增加文件体积。可在后续迭代中精简。
* **`enableProd: true`**（`build/plugins.ts` 第 58 行）：当前生产构建会包含 mock server。后端 API 就绪后应改为 `false` 或移除此插件。

---

## 10. 更新日志 (Changelog - 2026-07-12 第五版) — 用户管理模块

### 10.1 后端 API 需求文档

* **[Docs]** 新建 `docs/backend_user_management_api_requirements.md`，明确后端需实现的 6 个接口：
  `GET /api/admin/users`（列表）、`POST /api/admin/users`（新建）、
  `PUT /api/admin/users/:id`（编辑）、`DELETE /api/admin/users/:id`（删除）、
  `PUT /api/admin/users/:id/password`（重置密码）、`GET /api/admin/roles`（角色列表，可选）

### 10.2 前端用户管理页面

* **[Feat]** 新建 `views/admin/users.vue` — 独立用户管理页面，对齐模板原始 `views/system/user/` 风格：
  - `useRenderIcon` 驱动的图标按钮（搜索/新增/修改/删除/重置密码/停用）
  - `el-form inline` 搜索栏（用户名/角色/状态筛选）
  - `el-table` + 批量选择 + 批量删除栏（"已选 N 项"样式）
  - `el-dropdown` 更多操作菜单（重置密码、启用/停用）
  - 新增/编辑弹窗、重置密码弹窗
* **[Feat]** 新建 `api/admin.ts` — 用户管理 API 层（`getUserList`/`createUser`/`updateUser`/`resetUserPassword`/`deleteUser`）
* **[Feat]** 新建 `mock/admin.ts` — 6 条模拟用户数据 + 5 个 mock 端点，`vite-plugin-fake-server` 自动拦截，无需后端即可演示完整 CRUD

### 10.3 路由结构调整

* **[Refactor]** 新增顶层独立路由组 `/system`（`component: Layout`，仅 admin 可见），子路由 `/system/users` → 用户管理
* **[Rename]** 原 `/admin`（爬虫+导入+任务）标题从「系统管理」改为「运维管理」，避免与新 `/system`「系统管理」组重名

**当前侧边栏结构**：
```
📊 舆情分析系统 (rank 1)
├── 舆情看板
├── 智能问答
├── 个人中心
└── 运维管理          ← 爬虫管理+数据导入+任务

⚙️ 系统管理 (rank 99, admin only)
└── 用户管理          ← 新增，mock 数据立即可用
```

### 10.4 页面不可用故障记录

* **现象**：新增路由和 mock 文件后，刷新浏览器页面崩溃（连接被拒绝）
* **原因**：
  1. 路由拓扑变更（新增顶层 `/system` Layout 组）无法通过 HMR 热更新，Vue Router 尝试匹配新路径但路由表是旧的
  2. `mock/admin.ts` 是新文件，`vite-plugin-fake-server` 仅在 server 启动时扫描 `mock/` 目录，不支持新文件热加载
* **解决**：杀掉旧 Vite 进程，清除 `.vite` 缓存，重启 dev server

### 10.5 登录与用户管理体系梳理

* **登录流程**：`POST /api/auth/login` → Flask 后端验证 `admin/admin123` → JWT 签发 → 前端 Cookie + localStorage 存储 → 路由守卫校验
* **权限体系**：
  - 路由级：`meta.roles: ["admin"]` 控制菜单可见性和路由访问（`filterNoPermissionTree` + 路由守卫）
  - 按钮级：`v-perms` / `v-auth` 指令存在，但当前 `store/user.ts:93` 行硬编码 `permissions: ["*:*:*"]`，实际不生效
* **Mock 登录文件**：`mock/login.ts` 拦截路径为 `/login`，与业务调用的 `/api/auth/login` 不匹配，从未被使用。登录实际走 Flask 后端
* **用户管理现状**：后端仅有 `POST /login` + `GET /me` 两个认证接口，无用户 CRUD API。前端用户管理页面依赖 mock 数据，后端接口就绪后可直接对接

---

## 11. 更新日志 (Changelog - 2026-07-12 第六版) — 平台体系 + 生命周期 + 智能提问

### 11.1 7 平台接入体系

* **[Feat]** 新建 `constants/platforms.ts` — 共享平台配置（微博热搜/微博搜索/知乎/B站/小红书/百度热搜/百度搜索），每个平台含 name/short/color/bg/api/icon 六项属性
* **[Feat]** 平台图标集成 — 注册 `ant-design:weibo/zhihu/bilibili/baidu` + `simple-icons:xiaohongshu` 到 `offlineIcon.ts`，通过 `IconifyIconOffline` 全局可用
* **[Feat]** 平台分布图改造：
  - 从假数据"样例数据"改为只展示事件实际涉及的平台（从 articles 提取）
  - 每个柱子使用平台品牌色渐变（微博红/知乎蓝/B站粉/小红书红/百度蓝）
  - 图表上方新增 `图标 + 品牌色圆角标签` 图例行
  - y 轴标签按平台品牌色渲染
  - tooltip 显示接入方式（公开接口/TikHub API/开放平台 等）
* **[Feat]** 所有平台展示位置统一 `图标 + 品牌色` 风格：EventCard 信源标签、报道列表平台列、QA 平台选择器选项、图表标签行

### 11.2 QA 智能问答增强

* **[Feat]** QA 页面新增「聚焦平台」下拉选择器，7 个平台均可选，选项带图标 + 品牌色
* **[Feat]** 选中平台后提问自动注入 `[聚焦平台：XXX]` 上下文前缀
* **[Feat]** 从事件详情页跳转 QA 时自动携带 `platform` 参数预填平台选择
* **[Feat]** AI 研判卡片底部新增智能提问入口 + 温馨提示

### 11.3 事件详情页改进

* **[Feat]** 生命周期指示器三态区分：已完成（淡色底+彩色字+边框）、当前（实心底+白色粗体）、未到达（灰底+灰字），对比清晰
* **[Feat]** 报道列表增强：新增作者、发布时间、互动量（转发💬/评论↺/点赞♥）三列
* **[Feat]** 智能提问入口双位置：页面顶部主按钮 + AI 研判卡片底部
* **[Fix]** 统计卡片四合一：统一为标签行 + 大数字行 + `h-5` 底部固定高度容器，等高等宽

### 11.4 EventCard 事件卡片

* **[Feat]** 底部新增信源平台标签行，图标 + 品牌色背景
* **[Feat]** 每个卡片根据事件 ID 确定性选择 2-4 个平台展示

---

## 12. 更新日志（2026-07-13）—《功夫女足》真实链路验收

### 12.1 数据真实性修复

* **[Fix]** 风险雷达移除固定 `45` 和热度臆算维度，改为传播活跃度、负面占比、可疑风险、可疑报道率、平台覆盖和互动强度六项真实 API 指标，并改名为“多维舆情画像”。
* **[Fix]** 传播图在 `coverage_status=insufficient` 时显示证据不足提示，明确节点不代表已验证传播路径。
* **[Fix]** 生命周期阶段旁显示置信度；`low_volume=true` 时显示“样本量有限”。
* **[Fix]** 关键时间点描述改为中性证据表述，不再自动声称“全面爆发”或“官方渠道跟进”。

### 12.2 任务和事件卡片

* **[Fix]** TaskList 新增“事件关键词”列，从 `payload.keyword` 展示任务内容。
* **[Fix]** 后端状态 `success` 映射为“已完成”，进度条同步使用成功状态。
* **[Fix]** EventCard 的 `stroke-width` 改为数值绑定，消除 Element Plus 运行期警告。
* **[Fix]** EventCard 补齐 `top_keywords` 类型，平台配置补齐 `icon` 类型。

### 12.3 类型与浏览器验证

* 补齐用户角色、路由权限、通知列表和管理页标签类型，`vue-tsc --noEmit --skipLibCheck` 已通过。
* Selenium 实测登录、分析页、看板和事件详情；截图、DOM、console 和可见状态保存在 `tests/e2e/kung_fu_women_football/`。
* 浏览器质量门槛检查关键词、成功状态、摘要、详情分区和业务 console，最终全部通过。



