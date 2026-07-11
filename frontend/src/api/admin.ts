import { http } from "@/utils/http";

export type AdminUser = {
  id: number;
  username: string;
  nickname: string;
  role: string;
  status: number;
  last_login_at: string | null;
  created_at: string;
};

export type UserListResult = {
  code: number;
  data: {
    users: AdminUser[];
    total: number;
    page: number;
    size: number;
  };
};

export type UserFormData = {
  username?: string;
  password?: string;
  nickname?: string;
  role?: string;
  status?: number;
};

/** 获取用户列表 */
export function getUserList(params?: {
  page?: number;
  size?: number;
  keyword?: string;
  role?: string;
  status?: string;
}) {
  return http.request<UserListResult>("get", "/api/admin/users", { params });
}

/** 新建用户 */
export function createUser(data: UserFormData) {
  return http.request("post", "/api/admin/users", { data });
}

/** 编辑用户 */
export function updateUser(id: number, data: UserFormData) {
  return http.request("put", `/api/admin/users/${id}`, { data });
}

/** 重置密码 */
export function resetUserPassword(id: number, password: string) {
  return http.request("put", `/api/admin/users/${id}/password`, {
    data: { password }
  });
}

/** 删除用户 */
export function deleteUser(id: number) {
  return http.request("delete", `/api/admin/users/${id}`);
}
