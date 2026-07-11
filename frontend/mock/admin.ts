import { defineFakeRoute } from "vite-plugin-fake-server/client";

const mockUsers = [
  { id: 1, username: "admin", nickname: "管理员", role: "admin", status: 1, last_login_at: "2026-07-12 14:30:00", created_at: "2026-07-01" },
  { id: 2, username: "zhangsan", nickname: "张三", role: "user", status: 1, last_login_at: "2026-07-11 09:15:00", created_at: "2026-07-05" },
  { id: 3, username: "lisi", nickname: "李四", role: "user", status: 1, last_login_at: "2026-07-10 16:20:00", created_at: "2026-07-06" },
  { id: 4, username: "wangwu", nickname: "王五", role: "user", status: 0, last_login_at: null, created_at: "2026-07-08" },
  { id: 5, username: "zhaoliu", nickname: "赵六", role: "admin", status: 1, last_login_at: "2026-07-12 08:00:00", created_at: "2026-07-03" },
  { id: 6, username: "sunqi", nickname: "孙七", role: "user", status: 1, last_login_at: "2026-07-09 11:45:00", created_at: "2026-07-07" }
];
let nextId = 7;

function getId(path: string, params?: any, query?: any): number {
  // 优先从 params 取（path-to-regexp 模式），回退从 URL path 解析
  if (params?.id) return parseInt(params.id);
  const match = path.match(/\/api\/admin\/users\/(\d+)/);
  return match ? parseInt(match[1]) : 0;
}

export default defineFakeRoute([
  {
    url: "/api/admin/users",
    method: "get",
    response: ({ query }) => {
      let list = [...mockUsers];
      if (query.keyword) {
        const kw = query.keyword.toLowerCase();
        list = list.filter((u: any) => u.username.includes(kw) || u.nickname.includes(kw));
      }
      if (query.role) list = list.filter((u: any) => u.role === query.role);
      if (query.status !== undefined && query.status !== "") list = list.filter((u: any) => String(u.status) === String(query.status));
      const page = parseInt(query.page) || 1;
      const size = parseInt(query.size) || 20;
      const total = list.length;
      const start = (page - 1) * size;
      return { code: 200, data: { users: list.slice(start, start + size), total, page, size } };
    }
  },
  {
    url: "/api/admin/users",
    method: "post",
    response: ({ body }) => {
      const u = { id: nextId++, username: body.username, nickname: body.nickname || body.username, role: body.role || "user", status: 1, last_login_at: null, created_at: new Date().toISOString().slice(0, 10) };
      mockUsers.unshift(u);
      return { code: 200, data: { id: u.id } };
    }
  },
  {
    url: "/api/admin/users/:id",
    method: "put",
    response: ({ body, params }) => {
      const id = parseInt(params?.id || "0");
      const u = mockUsers.find((x: any) => x.id === id);
      if (u) {
        if (body.nickname !== undefined) u.nickname = body.nickname;
        if (body.role !== undefined) u.role = body.role;
        if (body.status !== undefined) u.status = body.status;
      }
      return { code: 200, message: "ok" };
    }
  },
  {
    url: "/api/admin/users/:id/password",
    method: "put",
    response: () => ({ code: 200, message: "ok" })
  },
  {
    url: "/api/admin/users/:id",
    method: "delete",
    response: ({ params }) => {
      const id = parseInt(params?.id || "0");
      const idx = mockUsers.findIndex((u: any) => u.id === id);
      if (idx >= 0) mockUsers.splice(idx, 1);
      return { code: 200, message: "ok" };
    }
  }
]);
