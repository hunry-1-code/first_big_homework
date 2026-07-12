<template>
  <div class="users-container p-6 space-y-4">
    <!-- 搜索表单 -->
    <div class="bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-4 rounded-xl shadow-sm">
      <el-form :model="form" inline class="search-form">
        <el-form-item label="用户名称：">
          <el-input v-model="form.username" placeholder="请输入用户名" clearable class="!w-[200px]" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="角色：">
          <el-select v-model="form.role" placeholder="全部" clearable class="!w-[140px]" @change="onSearch">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态：">
          <el-select v-model="form.status" placeholder="全部" clearable class="!w-[120px]" @change="onSearch">
            <el-option label="启用" value="1" />
            <el-option label="停用" value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="useRenderIcon('ri/search-line')" :loading="loading" @click="onSearch">
            搜索
          </el-button>
          <el-button :icon="useRenderIcon(Refresh)" @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 表格卡片 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold text-slate-800 dark:text-slate-100">用户列表</span>
          <div class="flex items-center gap-2">
            <el-button type="primary" :icon="useRenderIcon(AddFill)" @click="openDialog()">
              新增用户
            </el-button>
            <el-button :icon="useRenderIcon(Refresh)" @click="loadUsers">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 批量操作栏 -->
      <div
        v-if="selectedIds.length > 0"
        class="bg-slate-50 dark:bg-slate-800 w-full h-10 mb-3 px-4 flex items-center rounded-lg text-sm"
      >
        <span class="flex-auto text-slate-500 dark:text-slate-400">
          已选 {{ selectedIds.length }} 项
        </span>
        <el-button type="primary" text size="small" @click="selectedIds = []">取消选择</el-button>
        <el-popconfirm title="是否确认批量删除?" @confirm="onBatchDel">
          <template #reference>
            <el-button type="danger" text size="small">批量删除</el-button>
          </template>
        </el-popconfirm>
      </div>

      <el-table
        ref="tableRef"
        :data="dataList"
        stripe
        size="default"
        v-loading="loading"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="编号" width="70" align="center" />
        <el-table-column prop="username" label="用户名" min-width="110" />
        <el-table-column prop="nickname" label="昵称" min-width="110" />
        <el-table-column prop="role" label="角色" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : ''" size="small" effect="light">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 0 ? 'danger' : 'success'" size="small" effect="dark">
              {{ row.status === 0 ? '停用' : '启用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" min-width="150">
          <template #default="{ row }">
            <span class="text-xs text-slate-500 dark:text-slate-400">{{ row.last_login_at || '从未登录' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="110" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :icon="useRenderIcon(EditPen)" @click="openDialog('修改', row)">
              修改
            </el-button>
            <el-popconfirm title="是否确认删除?" @confirm="handleDelete(row)">
              <template #reference>
                <el-button link type="danger" size="small" :icon="useRenderIcon(Delete)">删除</el-button>
              </template>
            </el-popconfirm>
            <el-dropdown>
              <el-button link type="primary" size="small" :icon="useRenderIcon(More)" class="ml-1!" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="handleResetPwd(row)">
                    <el-button link type="warning" size="small" :icon="useRenderIcon(Password)">
                      重置密码
                    </el-button>
                  </el-dropdown-item>
                  <el-dropdown-item @click="handleToggleStatus(row)">
                    <el-button link type="info" size="small" :icon="useRenderIcon('ri:toggle-line')">
                      {{ row.status === 1 ? '停用账号' : '启用账号' }}
                    </el-button>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          small
          background
          @size-change="loadUsers"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="440px" destroy-on-close>
      <el-form ref="userFormRef" :model="userForm" label-width="80px" size="default">
        <el-form-item label="用户名" required>
          <el-input v-model="userForm.username" :disabled="isEdit" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" required>
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
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="resetPwdVisible" title="重置密码" width="360px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="新密码" required>
          <el-input v-model="resetPwdValue" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" @click="doResetPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from "vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { message } from "@/utils/message";
import {
  getUserList,
  createUser,
  updateUser,
  resetUserPassword,
  deleteUser,
  type AdminUser
} from "@/api/admin";

import Refresh from "~icons/ep/refresh";
import AddFill from "~icons/ri/add-circle-line";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import More from "~icons/ep/more-filled";
import Password from "~icons/ri/lock-password-line";

defineOptions({ name: "AdminUsers" });

const tableRef = ref();
const loading = ref(false);
const dataList = ref<AdminUser[]>([]);
const selectedIds = ref<number[]>([]);
const pagination = reactive({ total: 0, pageSize: 20, currentPage: 1 });

const form = reactive({ username: "", role: "", status: "" });

// 弹窗
const dialogVisible = ref(false);
const dialogTitle = ref("新增用户");
const isEdit = ref(false);
const userForm = reactive({ id: 0, username: "", password: "", nickname: "", role: "user" });
const resetPwdVisible = ref(false);
const resetPwdId = ref(0);
const resetPwdValue = ref("");

onMounted(() => loadUsers());

async function loadUsers() {
  loading.value = true;
  try {
    const res = await getUserList({
      page: pagination.currentPage,
      size: pagination.pageSize,
      keyword: form.username || undefined,
      role: form.role || undefined,
      status: form.status || undefined
    });
    dataList.value = res.data.users;
    pagination.total = res.data.total;
  } catch {
    dataList.value = [];
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.currentPage = 1;
  loadUsers();
}

function resetForm() {
  form.username = "";
  form.role = "";
  form.status = "";
  onSearch();
}

function onSelectionChange(selection: AdminUser[]) {
  selectedIds.value = selection.map((r: AdminUser) => r.id);
}

async function onBatchDel() {
  try {
    for (const id of selectedIds.value) {
      await deleteUser(id);
    }
    message("批量删除成功", { type: "success" });
    selectedIds.value = [];
    loadUsers();
  } catch {
    message("删除失败", { type: "error" });
  }
}

function openDialog(title = "新增用户", row?: AdminUser) {
  dialogTitle.value = title;
  if (row) {
    isEdit.value = true;
    userForm.id = row.id;
    userForm.username = row.username;
    userForm.password = "";
    userForm.nickname = row.nickname;
    userForm.role = row.role;
  } else {
    isEdit.value = false;
    userForm.id = 0;
    userForm.username = "";
    userForm.password = "";
    userForm.nickname = "";
    userForm.role = "user";
  }
  dialogVisible.value = true;
}

async function handleSubmit() {
  try {
    if (isEdit.value) {
      await updateUser(userForm.id, { nickname: userForm.nickname, role: userForm.role });
      message("修改成功", { type: "success" });
    } else {
      await createUser({
        username: userForm.username,
        password: userForm.password || "123456",
        nickname: userForm.nickname,
        role: userForm.role
      });
      message("新增成功", { type: "success" });
    }
    dialogVisible.value = false;
    loadUsers();
  } catch {
    message("操作失败", { type: "error" });
  }
}

async function handleDelete(row: AdminUser) {
  try {
    await deleteUser(row.id);
    message("删除成功", { type: "success" });
    loadUsers();
  } catch {
    message("删除失败", { type: "error" });
  }
}

function handleResetPwd(row: AdminUser) {
  resetPwdId.value = row.id;
  resetPwdValue.value = "";
  resetPwdVisible.value = true;
}

async function doResetPwd() {
  try {
    await resetUserPassword(resetPwdId.value, resetPwdValue.value || "123456");
    message("密码重置成功", { type: "success" });
    resetPwdVisible.value = false;
  } catch {
    message("操作失败", { type: "error" });
  }
}

async function handleToggleStatus(row: AdminUser) {
  try {
    const newStatus = row.status === 1 ? 0 : 1;
    await updateUser(row.id, { status: newStatus });
    message(newStatus === 1 ? "已启用" : "已停用", { type: "success" });
    loadUsers();
  } catch {
    message("操作失败", { type: "error" });
  }
}
</script>

<style scoped>
.users-container {
  min-height: calc(100vh - 120px);
}

.search-form :deep(.el-form-item) {
  margin-bottom: 0;
}

:deep(.el-dropdown-menu__item .el-button) {
  justify-content: flex-start;
  width: 100%;
}
</style>
