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
