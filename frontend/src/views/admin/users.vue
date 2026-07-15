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
              新建用户
            </el-button>
            <el-button type="success" plain size="default" :icon="useRenderIcon('ri:user-add-line')" @click="openBatchDialog">
              批量生成账户
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
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small" effect="light">
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
        <el-table-column label="最后登录" min-width="140">
          <template #default="{ row }">
            <span class="text-xs text-slate-500 dark:text-slate-400">{{ fmtDate(row.last_login_at) || '从未登录' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="140">
          <template #default="{ row }">
            <span class="text-xs text-slate-500 dark:text-slate-400">{{ fmtDate(row.created_at) }}</span>
          </template>
        </el-table-column>
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

    <!-- 新建/编辑用户弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="460px" destroy-on-close>
      <el-form ref="userFormRef" :model="userForm" :rules="formRules" label-width="80px" size="default" @submit.prevent>
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="userForm.username"
            :disabled="isEdit"
            placeholder="3-50位字母、数字、下划线或短横线"
            maxlength="50"
          />
          <template v-if="!isEdit" #extra>
            <span class="text-[11px] text-slate-400">允许字母、数字、下划线(_)和短横线(-)，3-50位</span>
          </template>
        </el-form-item>
        <el-form-item v-if="!isEdit" label="登录密码" prop="password">
          <el-input v-model="userForm.password" type="password" placeholder="6-128位字符" show-password maxlength="128" />
          <template #extra>
            <span class="text-[11px] text-slate-400">长度 6-128 位，建议包含字母和数字</span>
          </template>
        </el-form-item>
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="userForm.nickname" placeholder="可选，留空则使用用户名" maxlength="50" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
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

    <!-- 批量生成账户弹窗 -->
    <el-dialog v-model="batchVisible" title="批量生成账户" width="560px" destroy-on-close :close-on-click-modal="false">
      <div class="space-y-4">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名前缀" label-width="80px">
              <el-input v-model="batchForm.prefix" placeholder="如 user、stu" maxlength="20" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="生成数量" label-width="80px">
              <el-input-number v-model="batchForm.count" :min="1" :max="50" class="!w-full" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="起始编号" label-width="80px">
              <el-input-number v-model="batchForm.startNo" :min="1" :max="9999" class="!w-full" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色" label-width="80px">
              <el-select v-model="batchForm.role" class="!w-full">
                <el-option label="普通用户" value="user" />
                <el-option label="管理员" value="admin" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="默认密码" label-width="80px">
          <el-input v-model="batchForm.password" placeholder="留空则使用随机密码" maxlength="32" />
        </el-form-item>

        <!-- 预览 -->
        <div class="bg-slate-50 dark:bg-slate-800 rounded-lg p-3">
          <div class="text-xs text-slate-500 dark:text-slate-400 mb-2">
            预览（将生成 {{ batchForm.count }} 个账户）
          </div>
          <div class="text-xs font-mono text-slate-600 dark:text-slate-300 max-h-[100px] overflow-y-auto space-y-0.5">
            <div v-for="u in batchPreview" :key="u.username"
              :class="u.conflict ? 'text-red-500 line-through' : ''">
              {{ u.username }} / {{ u.password }} / {{ batchForm.role === 'admin' ? '管理员' : '普通用户' }}
              <span v-if="u.conflict" class="text-red-400 text-[11px]"> ⚠ 已存在</span>
            </div>
          </div>
        </div>

        <!-- 生成结果 -->
        <div v-if="batchResults.length > 0" class="bg-emerald-50 dark:bg-emerald-950/30 rounded-lg p-3">
          <div class="text-xs text-emerald-600 dark:text-emerald-400 mb-2 font-medium">
            生成完成：成功 {{ batchResults.filter(r => r.ok).length }} / {{ batchResults.length }}
          </div>
          <div class="max-h-[180px] overflow-y-auto border border-emerald-200 dark:border-emerald-800 rounded text-xs">
            <div
              v-for="r in batchResults"
              :key="r.username"
              class="flex items-center justify-between px-3 py-1.5 border-b border-emerald-100 dark:border-emerald-800/50 last:border-0 font-mono"
            >
              <span :class="r.ok ? 'text-slate-700 dark:text-slate-200' : 'text-red-400 line-through'">
                {{ r.username }} / {{ r.password || batchForm.password }}
              </span>
              <span :class="r.ok ? 'text-emerald-500' : 'text-red-400'" class="text-[10px]">
                {{ r.ok ? '✓' : r.error }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="batchVisible = false">关闭</el-button>
        <el-button type="primary" :loading="generating" :disabled="batchHasConflict" @click="doBatchGenerate">
          {{ batchHasConflict ? '存在冲突用户名' : generating ? '生成中...' : '开始生成' }}
        </el-button>
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
import { onMounted, ref, reactive, computed } from "vue";
import type { FormInstance, FormRules } from "element-plus";
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

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return iso.replace("T", " ").replace(/\.\d+Z?/, "").replace("Z", "").slice(0, 19);
}

// 批量生成
const generating = ref(false);
const batchVisible = ref(false);
const batchForm = reactive({ prefix: "user", count: 5, startNo: 1, role: "user", password: "" });
const batchResults = ref<{ username: string; password: string; ok: boolean; error?: string }[]>([]);

const existingUsernames = ref<Set<string>>(new Set());
const batchPreview = computed(() => {
  const list: { username: string; password: string; conflict: boolean }[] = [];
  for (let i = 0; i < batchForm.count; i++) {
    const no = batchForm.startNo + i;
    const uname = `${batchForm.prefix}${pad(no, 3)}`;
    list.push({
      username: uname,
      password: batchForm.password || randomPwd(),
      conflict: existingUsernames.value.has(uname)
    });
  }
  return list;
});
const batchHasConflict = computed(() => batchPreview.value.some(u => u.conflict));

function pad(n: number, len: number): string {
  return String(n).padStart(len, "0");
}

function randomPwd(): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  let pwd = "";
  for (let i = 0; i < 8; i++) pwd += chars[Math.floor(Math.random() * chars.length)];
  return pwd;
}

async function openBatchDialog() {
  batchForm.prefix = "user";
  batchForm.count = 5;
  batchForm.startNo = 1;
  batchForm.role = "user";
  batchForm.password = "";
  batchResults.value = [];
  try {
    const res = await getUserList({ size: 1000 });
    existingUsernames.value = new Set((res.data.users || []).map((u: any) => u.username));
  } catch { existingUsernames.value = new Set(); }
  batchVisible.value = true;
}

async function doBatchGenerate() {
  generating.value = true;
  batchResults.value = [];
  for (const u of batchPreview.value) {
    try {
      await createUser({ username: u.username, password: u.password, nickname: u.username, role: batchForm.role });
      batchResults.value.push({ username: u.username, password: u.password, ok: true });
    } catch (e) {
      batchResults.value.push({ username: u.username, password: u.password, ok: false, error: (e as any)?.response?.data?.message || "失败" });
    }
  }
  generating.value = false;
  loadUsers();
}

const tableRef = ref();
const loading = ref(false);
const dataList = ref<AdminUser[]>([]);
const selectedIds = ref<number[]>([]);
const pagination = reactive({ total: 0, pageSize: 20, currentPage: 1 });

const form = reactive({ username: "", role: "", status: "" });

// 弹窗
const userFormRef = ref<FormInstance>();
const dialogVisible = ref(false);
const dialogTitle = ref("新建用户");

const formRules: FormRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { pattern: /^[A-Za-z0-9_-]{3,50}$/, message: "3-50位字母、数字、下划线或短横线", trigger: "blur" }
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度 6-128 位", trigger: "blur" }
  ]
};
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
  } catch (e) {
    message(e?.response?.data?.message || e?.message || "删除失败", { type: "error" });
  }
}

function openDialog(title = "新建用户", row?: AdminUser) {
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
  const valid = await userFormRef.value?.validate().catch(() => false);
  if (!valid) return;
  try {
    if (isEdit.value) {
      await updateUser(userForm.id, { nickname: userForm.nickname, role: userForm.role });
      message("修改成功", { type: "success" });
    } else {
      const pwd = userForm.password || "123456";
      await createUser({
        username: userForm.username,
        password: pwd,
        nickname: userForm.nickname,
        role: userForm.role
      });
      message(`新增成功，初始密码: ${pwd}`, { type: "success", duration: 8000 });
    }
    dialogVisible.value = false;
    loadUsers();
  } catch (e) {
    message(e?.response?.data?.message || e?.message || "操作失败", { type: "error" });
  }
}

async function handleDelete(row: AdminUser) {
  try {
    await deleteUser(row.id);
    message("删除成功", { type: "success" });
    loadUsers();
  } catch (e) {
    message(e?.response?.data?.message || e?.message || "删除失败", { type: "error" });
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
  } catch (e) {
    message(e?.response?.data?.message || e?.message || "操作失败", { type: "error" });
  }
}

async function handleToggleStatus(row: AdminUser) {
  try {
    const newStatus = row.status === 1 ? 0 : 1;
    await updateUser(row.id, { status: newStatus });
    message(newStatus === 1 ? "已启用" : "已停用", { type: "success" });
    loadUsers();
  } catch (e) {
    message(e?.response?.data?.message || e?.message || "操作失败", { type: "error" });
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
