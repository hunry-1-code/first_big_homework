<script setup lang="ts">
import Motion from "./utils/motion";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { loginRules } from "./utils/rule";
import { useNav } from "@/layout/hooks/useNav";
import type { FormInstance } from "element-plus";
import { useUserStoreHook } from "@/store/modules/user";
import { initRouter, getTopMenu } from "@/router/utils";
import { bg, avatar } from "./utils/static";
import { ref, reactive } from "vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";

defineOptions({ name: "Login" });

const router = useRouter();
const loading = ref(false);
const ruleFormRef = ref<FormInstance>();

const { initStorage } = useLayout();
initStorage();
const { dataTheme, themeMode, dataThemeChange } = useDataThemeChange();
dataThemeChange(themeMode.value);
const { title } = useNav();

const ruleForm = reactive({
  username: "admin",
  password: "admin123"
});

const onLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      await useUserStoreHook().loginByUsername({ username: ruleForm.username, password: ruleForm.password });
      await initRouter();
      router.push(getTopMenu(true).path).then(() => {
        message("登录成功", { type: "success" });
      });
    } catch {
      message("用户名或密码错误", { type: "error" });
    } finally {
      loading.value = false;
    }
  });
};
</script>

<template>
  <div class="select-none">
    <img :src="bg" class="wave" />
    <!-- 主题切换 -->
    <div class="flex-c absolute right-5 top-3">
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>
    <div class="login-container">
      <div class="login-box">
        <div class="login-form">
          <avatar class="avatar" />
          <Motion>
            <h2 class="outline-hidden">{{ title }}</h2>
          </Motion>

          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="loginRules"
            size="large"
            @keyup.enter="onLogin(ruleFormRef)"
          >
            <Motion :delay="100">
              <el-form-item
                :rules="[{ required: true, message: '请输入用户名', trigger: 'blur' }]"
                prop="username"
              >
                <el-input
                  v-model="ruleForm.username"
                  clearable
                  placeholder="请输入用户名"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="150">
              <el-form-item prop="password">
                <el-input
                  v-model="ruleForm.password"
                  clearable
                  show-password
                  placeholder="请输入密码"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="200">
              <el-form-item>
                <el-button
                  class="w-full mt-4!"
                  size="default"
                  type="primary"
                  :loading="loading"
                  @click="onLogin(ruleFormRef)"
                >
                  登 录
                </el-button>
              </el-form-item>
            </Motion>
          </el-form>
        </div>
      </div>
    </div>
    <!-- 页脚 -->
    <div class="w-full flex-c absolute bottom-3 text-sm text-[rgba(0,0,0,0.4)] dark:text-[rgba(220,220,242,0.5)]">
      网络舆情事件智能分析系统
    </div>
  </div>
</template>

<style scoped>
@import url("@/style/login.css");
</style>
