# 管理员用户 API、数据契约与小红书采集修复设计

## 1. 目标与范围

本轮只修改后端，不新增或调整 Vue 页面。目标包括：

1. 按 TikHub 官方 OpenAPI 修复小红书搜索请求和真实验证方式。
2. 实现 `/api/admin/users` 用户管理 API。
3. 按 `D:/newbigwork/backend_api_data_format.md` 对齐事件列表和详情的后端响应格式。
4. 保持现有分析、聚合、情感和数据库内部语义兼容，避免为了前端显示文案重写内部算法。

## 2. 兼容性原则

- 数据库和分析模块继续使用当前内部平台代码，例如 `weibo_hot`、`weibo`、`zhihu`、`bilibili`、`xiaohongshu`、`baidu_hot`、`baidu`。
- 生命周期算法继续使用当前内部值 `潜伏期`、`成长期`、`高潮期`、`衰退期`。
- API 序列化出口负责转换成前端契约需要的中文平台名和生命周期名称。
- 已有 API 路径保持不变；只新增 `/api/admin` 路径。
- 所有响应继续使用 `{code, message, data}` 包装格式。

## 3. 小红书采集修复

### 3.1 官方接口

权威来源为 `https://api.tikhub.io/openapi.json` 和 `https://docs.tikhub.io/`。使用接口：

```text
GET /api/v1/xiaohongshu/app_v2/search_notes
```

请求参数：

- `keyword`：必填，UTF-8 中文搜索词。
- `page`：从 1 开始。
- `sort_type`：默认 `general`。
- `note_type`：默认 `不限`。
- `time_filter`：默认 `不限`。
- `search_id`：翻页时传入首次响应返回值。
- `search_session_id`：翻页时传入首次响应返回值。
- `source`：默认 `explore_feed`。
- `ai_mode`：默认 0。

### 3.2 空结果根因

此前十次验证由 PowerShell 内联脚本直接包含中文字符串，当前 Windows 终端编码将中文转换成了 `?`。TikHub 实际收到的不是有效中文关键词，因此十次 `EMPTY_SUCCESS` 不能作为平台无数据的证据。

修复方式：

- 验证脚本内置关键词使用 Unicode 转义或从 UTF-8 JSON 文件读取。
- 命令行接收关键词时显式使用 Python Unicode 字符串，不依赖 PowerShell 代码页。
- 验证结果记录关键词的 Unicode 码点摘要，防止再次无声变成问号。

### 3.3 响应处理

- 从 `data.data.items` 提取笔记项。
- 过滤 `hot_query` 等无笔记 ID、无标题、无描述的占位项。
- 支持 `note_card` 包装结构。
- 首次响应的 `search_id` 和 `search_session_id` 保存到批次元数据，供后续翻页。
- 有效笔记必须至少具备笔记 ID，以及标题或描述之一。
- 搜索成功但无有效笔记时返回合法空列表，不制造“小红书笔记”占位文档。

## 4. 用户模型与迁移

### 4.1 User 模型

新增：

```python
status = db.Column(db.Integer, nullable=False, default=1, server_default="1")
```

状态只允许：

- `1`：启用
- `0`：停用

现有用户迁移后统一设为启用。

### 4.2 数据库迁移

新增 SQL 与 Python 迁移器，同时支持当前 SQLite 开发库和 MySQL 正式配置。迁移必须幂等：字段已存在时不重复添加。

## 5. 管理员用户 API

新增 `admin_bp`，注册前缀 `/api/admin`。所有端点使用 `@admin_required`。

### 5.1 用户列表

```text
GET /api/admin/users?page=1&size=20&keyword=&role=&status=
```

规则：

- `page >= 1`。
- `size` 默认 20，范围 1～100。
- `keyword` 模糊匹配 username 和 nickname。
- `role` 只允许 `admin`、`user`。
- `status` 只允许 0、1。
- 默认按 `id` 升序。

每项返回：`id`、`username`、`nickname`、`role`、`status`、`last_login_at`、`created_at`。

### 5.2 新建用户

```text
POST /api/admin/users
```

规则：

- username 去除首尾空格，长度 3～50，只允许字母、数字、下划线和短横线。
- username 唯一，不区分前端是否先检查。
- password 长度 6～128。
- nickname 最长 50。
- role 只允许 `admin`、`user`，默认 `user`。
- status 默认 1。
- 密码继续使用项目现有 PBKDF2-SHA256 格式，避免破坏现有登录。

### 5.3 编辑用户

```text
PUT /api/admin/users/<id>
```

只更新传入字段：nickname、role、status。username 不允许通过编辑接口修改。

保护规则：

- 不允许停用当前登录管理员自己。
- 不允许将最后一个启用管理员降级或停用。

### 5.4 重置密码

```text
PUT /api/admin/users/<id>/password
```

校验新密码长度并重新生成密码哈希。响应不返回哈希或明文。

### 5.5 删除用户

```text
DELETE /api/admin/users/<id>
```

保护规则：

- 不允许删除自己。
- 不允许删除最后一个启用管理员。
- 用户不存在返回 404。
- 存在关联数据且数据库拒绝删除时返回 409，不级联删除舆情业务数据。

### 5.6 角色列表

```text
GET /api/admin/roles
```

返回固定角色列表 `admin`、`user`，便于接口契约完整。

## 6. 登录与用户状态

- 登录成功前检查 `User.status`。
- 停用账号返回 403 和明确提示。
- 登录成功更新 `last_login_at`。
- `/api/auth/me` 从数据库读取最新昵称、角色和状态，避免 JWT 中旧角色长期有效。
- 已停用用户访问受保护接口时应被拒绝。该检查放在鉴权装饰器公共入口，而不是只放登录接口。

## 7. API 数据格式映射

### 7.1 平台名称

API 输出统一映射：

| 内部代码 | API 名称 |
|---|---|
| `weibo_hot` | `微博热搜` |
| `weibo` | `微博搜索` |
| `zhihu`、`zhihu_hot` | `知乎` |
| `bilibili` | `B站` |
| `xiaohongshu` | `小红书` |
| `baidu_hot` | `百度热搜` |
| `baidu` | `百度搜索` |

未知平台不返回任意内部代码；统一映射为最接近的数据源，无法识别时跳过平台分布项，文章项使用 `百度搜索` 作为网页新闻降级值并记录服务日志警告。

### 7.2 生命周期名称

API 输出映射：

- `潜伏期` → `潜伏期`
- `成长期` → `成长期`
- `高潮期` → `爆发期`
- `衰退期` → `消退期`

内部数据库值不迁移。

### 7.3 情感比例和标签

- 正面、负面、中性比例限制在 0～1。
- 三项和不为 1 时进行归一化；全为零时返回 `0, 0, 1`。
- 文章标签统一映射为 `正面`、`中性`、`负面`。
- `neutral`、`中立`、空值均输出 `中性`。

### 7.4 热度

API 输出 `heat_index` 限制在 0～100。内部原始热度和快照不修改。

### 7.5 趋势

- 从文章发布时间或首次采集时间按日统计。
- 日期输出为 `M/D`。
- 有真实数据时返回实际时间跨度内最多 14 个点。
- 不伪造不存在的日期或报道量；不足 7 个点允许返回实际点数。
- `key_points` 包括首次报道、热度峰值和最新动态；重复坐标去重。

### 7.6 事件详情稳定结构

详情始终返回：

- 基本字段：id、title、summary、heat_index、lifecycle_stage、情感比例、time_code、location、key_figures、cause。
- `report`：overview_text、risk_data.level、risk_data.score。
- `trend`：dates、counts、key_points。
- `platform`：platforms 数组，每项为 platform、count。
- `keywords`：keywords 数组，每项为 word、weight，权重限制 0～1。
- `articles`：total、articles。

文章字段包含：id、platform、title、author、publish_time、互动量、clean_content、sentiment_label、is_suspicious、suspicious_score。可疑分数统一为 0～1。

## 8. 错误响应

- 参数错误：400。
- 未登录：401。
- 非管理员或停用账号：403。
- 用户不存在：404。
- username 冲突、最后管理员保护、关联数据冲突：409。
- 不向客户端返回 SQL、堆栈、密码哈希或外部 API 密钥。

## 9. 测试策略

### 9.1 小红书

- 官方请求参数测试。
- Unicode 中文关键词不变测试。
- `search_id` / `search_session_id` 翻页参数测试。
- `note_card` 映射和占位项过滤测试。
- 使用专用 Key 进行有限真实验证。

### 9.2 用户管理

- 普通用户访问管理员接口返回 403。
- 列表分页、关键词、角色和状态筛选。
- 新建用户、重复 username、非法字段。
- 编辑昵称、角色和状态。
- 禁止停用自己、禁止移除最后管理员。
- 密码重置后旧密码失败、新密码成功。
- 删除自己和最后管理员保护。
- 停用账号不能登录或继续访问受保护 API。
- SQLite/MySQL 迁移幂等验证。

### 9.3 数据合同

- 事件列表字段、平台名称、生命周期、热度和情感比例。
- 事件详情所有稳定子结构。
- 日期短格式和关键节点。
- 文章情感中文标签、可疑分数和平台名称。
- 空数据事件仍返回合法结构。

### 9.4 全量回归

完整执行 `python -m pytest -q backend/tests tests`，确保现有采集、清洗、分析、聚合、情感和任务链不回归。

## 10. 完成条件

- 小红书验证使用正确 UTF-8 关键词，能够区分有效笔记、真实空结果和占位项。
- `/api/admin/users` 全部要求端点实现并通过权限及保护规则测试。
- User.status 迁移可在 SQLite 和 MySQL 重复执行。
- 事件列表与详情满足数据格式文档的字段和枚举要求。
- 所有后端离线测试通过。
- 真实验证输出不包含任何 API Key 或 Authorization 内容。
