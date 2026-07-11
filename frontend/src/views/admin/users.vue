<template>
  <div class="users-container p-6 space-y-6">
    <!-- 头部横幅 -->
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <span>👥 用户管理</span>
        </h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          管理系统用户账号，包括创建、编辑、重置密码、删除等操作。
        </p>
      </div>
      <el-button type="primary" size="large" @click="openCreateUser">新增用户</el-button>
    </div>

    <!-- 搜索与筛选 -->
    <div class="flex items-center gap-3 bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm">
      <el-input
        v-model="userKeyword"
        placeholder="搜索用户名 / 昵称"
        size="default"
        clearable
        class="!w-[240px]"
        @keyup.enter="loadUsers"
        @clear="loadUsers"
      >
        <template #prefix>
          <span class="text-slate-400">🔍</span>
        </template>
      </el-input>
      <el-select v-model="userRoleFilter" size="default" class="!w-[120px]" clearable placeholder="全部角色" @change="loadUsers">
        <el-option label="管理员" value="admin" />
        <el-option label="普通用户" value="user" />
      </el-select>
      <el-button size="default" @click="loadUsers">搜索</el-button>
    </div>

    <!-- 用户表格 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <el-table :data="userList" v-loading="userLoading" stripe size="default">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small" effect="light">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 0 ? 'danger' : 'success'" size="small" effect="dark">
              {{ row.status === 0 ? '停用' : '启用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="160">
          <template #default="{ row }">
            <span class="text-xs text-slate-500 dark:text-slate-400">{{ row.last_login_at || '从未登录' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEditUser(row)">编辑</el-button>
            <el-button type="warning" link size="small" @click="openResetPwd(row)">重置密码</el-button>
            <el-button type="danger" link size="small" @click="handleDeleteUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="userPage"
          v-model:page-size="userPageSize"
          :total="userTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          small
          @current-change="loadUsers"
          @size-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 新增/编辑用户弹窗 -->
    <el-dialog v-model="userDialogVisible" :title="userDialogTitle" width="420px" destroy-on-close>
      <el-form :model="userForm" label-width="80px" size="default">
        <el-form-item label="用户名" required>
          <el-input v-model="userForm.username" :disabled="!!userForm.id" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!userForm.id" label="密码" required>
          <el-input v-model="userForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="userForm.nickname" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="userForm.role" class="w-full">
            <el-option label="管理员 (admin)" value="admin" />
            <el-option label="普通用户 (user)" value="user" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleUserSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="resetPwdDialogVisible" title="重置密码" width="360px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="新密码" required>
          <el-input v-model="resetPwdNew" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from "vue";
import {
  getUserList,
  createUser,
  updateUser,
  resetUserPassword,
  deleteUser,
  type AdminUser,
  type UserFormData
} from "@/api/admin";
import { message } from "@/utils/message";

defineOptions({
  name: "AdminUsers"
});

// 列表状态
const userLoading = ref(false);
const userList = ref<AdminUser[]>([]);
const userTotal = ref(0);
const userPage = ref(1);
const userPageSize = ref(20);
const userKeyword = ref("");
const userRoleFilter = ref("");

// 弹窗状态
const userDialogVisible = ref(false);
const userDialogTitle = ref("新增用户");
const userForm = reactive<UserFormData & { id?: number }>({
  username: "",
  password: "",
  nickname: "",
  role: "user"
});
const resetPwdDialogVisible = ref(false);
const resetPwdUserId = ref(0);
const resetPwdNew = ref("");

onMounted(() => {
  loadUsers();
});

async function loadUsers() {
  userLoading.value = true;
  try {
    const res = await getUserList({
      page: userPage.value,
      size: userPageSize.value,
      keyword: userKeyword.value || undefined,
      role: userRoleFilter.value || undefined
    });
    if (res.code === 200) {
      userList.value = res.data.users;
      userTotal.value = res.data.total;
    }
  } catch {
    userList.value = [];
    userTotal.value = 0;
  } finally {
    userLoading.value = false;
  }
}

function openCreateUser() {
  userDialogTitle.value = "新增用户";
  userForm.id = undefined;
  userForm.username = "";
  userForm.password = "";
  userForm.nickname = "";
  userForm.role = "user";
  userDialogVisible.value = true;
}

function openEditUser(row: AdminUser) {
  userDialogTitle.value = "编辑用户";
  userForm.id = row.id;
  userForm.username = row.username;
  userForm.password = "";
  userForm.nickname = row.nickname;
  userForm.role = row.role;
  userDialogVisible.value = true;
}

async function handleUserSubmit() {
  try {
    if (userForm.id) {
      await updateUser(userForm.id, {
        nickname: userForm.nickname,
        role: userForm.role
      });
      message("用户更新成功", { type: "success" });
    } else {
      await createUser({
        username: userForm.username,
        password: userForm.password || "123456",
        nickname: userForm.nickname,
        role: userForm.role
      });
      message("用户创建成功", { type: "success" });
    }
    userDialogVisible.value = false;
    loadUsers();
  } catch {
    message("操作失败，请确认后端接口已部署", { type: "error" });
  }
}

function openResetPwd(row: AdminUser) {
  resetPwdUserId.value = row.id;
  resetPwdNew.value = "";
  resetPwdDialogVisible.value = true;
}

async function handleResetPwd() {
  try {
    await resetUserPassword(resetPwdUserId.value, resetPwdNew.value || "123456");
    message("密码重置成功", { type: "success" });
    resetPwdDialogVisible.value = false;
  } catch {
    message("操作失败", { type: "error" });
  }
}

async function handleDeleteUser(row: AdminUser) {
  try {
    await deleteUser(row.id);
    message("用户已删除", { type: "success" });
    loadUsers();
  } catch {
    message("删除失败", { type: "error" });
  }
}
</script>

<style scoped>
.users-container {
  min-height: calc(100vh - 120px);
}
</style>
