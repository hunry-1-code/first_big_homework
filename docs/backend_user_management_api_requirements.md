# 后端用户管理 API 需求文档

本文档描述前端用户管理模块所需的后端 API 接口规范。供后端开发同学参考实现。

---

## 1. 当前状态

| 已有 | 缺失 |
|------|------|
| `POST /api/auth/login` 登录 | 用户列表查询 |
| `GET /api/auth/me` 查当前用户 | 用户增删改 |
| `User` 数据模型（id/username/password_hash/nickname/role） | 重置密码 |
| `admin_required` 装饰器（已定义） | 角色列表查询 |
| `login_required` 装饰器 | — |

---

## 2. 需要新增的 API

所有接口前缀 `/api/admin`，均需 `@admin_required` 权限。

### 2.1 用户列表

```
GET /api/admin/users?page=1&size=20&keyword=&role=&status=
```

**响应**：
```json
{
  "code": 200,
  "data": {
    "users": [
      {
        "id": 1,
        "username": "admin",
        "nickname": "管理员",
        "role": "admin",
        "status": 1,
        "last_login_at": "2026-07-12T10:30:00Z",
        "created_at": "2026-07-01T00:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

**查询参数说明**：
- `page` / `size`：分页，默认 page=1, size=20
- `keyword`：模糊匹配 username 或 nickname
- `role`：按角色筛选（admin / user）
- `status`：按状态筛选（1 启用 / 0 停用）

### 2.2 新建用户

```
POST /api/admin/users
```

**请求体**：
```json
{
  "username": "zhangsan",
  "password": "123456",
  "nickname": "张三",
  "role": "user"
}
```

**响应**：
```json
{
  "code": 200,
  "data": { "id": 3 }
}
```

### 2.3 编辑用户

```
PUT /api/admin/users/:id
```

**请求体**（所有字段可选，只更新传入的字段）：
```json
{
  "nickname": "张三丰",
  "role": "admin",
  "status": 0
}
```

**响应**：
```json
{ "code": 200, "message": "更新成功" }
```

### 2.4 重置密码

```
PUT /api/admin/users/:id/password
```

**请求体**：
```json
{
  "password": "newpassword123"
}
```

**响应**：
```json
{ "code": 200, "message": "密码重置成功" }
```

### 2.5 删除用户

```
DELETE /api/admin/users/:id
```

**响应**：
```json
{ "code": 200, "message": "删除成功" }
```
- 不允许删除自己
- 不允许删除最后一个 admin 角色用户

### 2.6 角色列表（可选）

```
GET /api/admin/roles
```

**响应**：
```json
{
  "code": 200,
  "data": {
    "roles": ["admin", "user"]
  }
}
```
- 如果角色体系简单（只有 admin/user 两种），此接口可暂不实现，前端使用硬编码列表

---

## 3. 数据模型参考

当前 `backend/app/models/user.py` 已定义：

```python
class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(50))
    role = db.Column(db.String(20), default="user")
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
```

建议新增 `status` 字段（1 启用 / 0 停用）。如不新增，前端默认所有用户 status=1。

---

## 4. 实现建议

1. 新建 `backend/app/api/admin.py` 蓝图，注册到 `url_prefix="/api/admin"`
2. 所有端点加 `@admin_required` 装饰器（已在 `app/core/security.py` 定义）
3. 密码存储使用 `werkzeug.security.generate_password_hash` / `check_password_hash`
4. 新建 `backend/app/services/admin_service.py` 存放业务逻辑
5. 在 `app/api/__init__.py` 中注册新蓝图
