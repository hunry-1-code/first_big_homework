<script setup lang="ts">
import { message } from "@/utils/message";
import { onMounted, reactive, ref, computed } from "vue";
import { getMine } from "@/api/user";
import { http } from "@/utils/http";
import { useUserStoreHook } from "@/store/modules/user";
import type { FormInstance } from "element-plus";
import { deviceDetection } from "@pureadmin/utils";
import { avatarDataUri } from "@/utils/avatar";

defineOptions({ name: "Profile" });

const userInfoFormRef = ref<FormInstance>();
const saving = ref(false);
const userInfos = reactive({
  username: "",
  nickname: "",
  role: ""
});

onMounted(async () => {
  try {
    const { code, data } = await getMine();
    if (code === 200) {
      userInfos.username = data.username || "";
      userInfos.nickname = data.nickname || data.username || "";
      userInfos.role = data.role || "user";
    }
  } catch {
    // 后端不可用，显示 store 中的数据
    const store = useUserStoreHook();
    userInfos.username = store.username || "";
    userInfos.nickname = store.nickname || store.username || "";
    userInfos.role = store.roles?.[0] || "user";
  }
});

const onSubmit = async (formEl: FormInstance) => {
  if (!formEl) return;
  await formEl.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await http.request("put", "/api/user/profile", { data: { nickname: userInfos.nickname } });
      // 同步更新 store
      useUserStoreHook().SET_NICKNAME(userInfos.nickname);
      message("个人信息更新成功", { type: "success" });
    } catch {
      message("保存失败，请稍后重试", { type: "error" });
    } finally {
      saving.value = false;
    }
  });
};

const avatarSrc = computed(() => avatarDataUri(userInfos.username || "U", userInfos.nickname));
</script>

<template>
  <div :class="['min-w-45', deviceDetection() ? 'max-w-full' : 'max-w-[70%]']">
    <h3 class="my-8!">个人信息</h3>

    <!-- 头像 -->
    <div class="flex items-center gap-4 mb-6">
      <img :src="avatarSrc" class="w-16 h-16 rounded-full" alt="avatar" />
      <div>
        <div class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ userInfos.nickname }}</div>
        <div class="text-xs text-slate-400 mt-1">系统自动生成默认头像，自定义头像功能即将上线</div>
      </div>
    </div>

    <el-form
      ref="userInfoFormRef"
      label-position="top"
      :model="userInfos"
      size="large"
    >
      <el-row :gutter="24">
        <el-col :span="12">
          <el-form-item label="用户名">
            <el-input :model-value="userInfos.username" disabled />
            <template #extra>
              <span class="text-[11px] text-slate-400">用户名不可修改</span>
            </template>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="角色">
            <el-input :model-value="userInfos.role === 'admin' ? '管理员' : '普通用户'" disabled />
            <template #extra>
              <span class="text-[11px] text-slate-400">请联系管理员修改角色</span>
            </template>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="昵称" prop="nickname">
        <el-input
          v-model="userInfos.nickname"
          maxlength="50"
          placeholder="请输入昵称"
        />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="onSubmit(userInfoFormRef)">
          保存修改
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>
