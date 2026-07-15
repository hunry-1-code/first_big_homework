<script setup lang="ts">
import { ref, reactive } from "vue";
import Motion from "../utils/motion";
import { message } from "@/utils/message";
import type { FormInstance } from "element-plus";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useUserStoreHook } from "@/store/modules/user";
import { http } from "@/utils/http";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";
import Nickname from "~icons/ri/account-pin-circle-line";

const loading = ref(false);
const ruleFormRef = ref<FormInstance>();
const ruleForm = reactive({
  username: "",
  nickname: "",
  password: "",
  repeatPassword: ""
});

const repeatPasswordRule = [
  {
    validator: (_rule: any, value: string, callback: any) => {
      if (value === "") {
        callback(new Error("请再次输入密码"));
      } else if (ruleForm.password !== value) {
        callback(new Error("两次输入的密码不一致"));
      } else {
        callback();
      }
    },
    trigger: "blur"
  }
];

const onRegister = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      const res = await http.request<any>("post", "/api/auth/register", {
        data: {
          username: ruleForm.username,
          password: ruleForm.password,
          nickname: ruleForm.nickname || ruleForm.username
        }
      });
      if (res.code === 200) {
        message("注册成功，初始密码: " + ruleForm.password + "，请返回登录", { type: "success", duration: 8000 });
        useUserStoreHook().SET_CURRENTPAGE(0);
      } else {
        message(res.message || "注册失败", { type: "error" });
      }
    } catch {
      message("注册失败，请稍后重试", { type: "error" });
    } finally {
      loading.value = false;
    }
  });
};

function onBack() {
  useUserStoreHook().SET_CURRENTPAGE(0);
}
</script>

<template>
  <el-form
    ref="ruleFormRef"
    :model="ruleForm"
    size="large"
  >
    <Motion>
      <el-form-item
        :rules="[{ required: true, message: '请输入用户名', trigger: 'blur' }, { pattern: /^[A-Za-z0-9_-]{3,50}$/, message: '3-50位字母、数字、下划线或短横线', trigger: 'blur' }]"
        prop="username"
      >
        <el-input
          v-model="ruleForm.username"
          clearable
          placeholder="用户名（3-50位字母、数字）"
          :prefix-icon="useRenderIcon(User)"
        />
      </el-form-item>
    </Motion>

    <Motion :delay="80">
      <el-form-item prop="nickname">
        <el-input
          v-model="ruleForm.nickname"
          clearable
          placeholder="昵称（可选，留空同用户名）"
          :prefix-icon="useRenderIcon(Nickname)"
        />
      </el-form-item>
    </Motion>

    <Motion :delay="100">
      <el-form-item
        :rules="[{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, max: 128, message: '密码长度 6-128 位', trigger: 'blur' }]"
        prop="password"
      >
        <el-input
          v-model="ruleForm.password"
          clearable
          show-password
          placeholder="密码（6-128位）"
          :prefix-icon="useRenderIcon(Lock)"
        />
      </el-form-item>
    </Motion>

    <Motion :delay="120">
      <el-form-item :rules="repeatPasswordRule" prop="repeatPassword">
        <el-input
          v-model="ruleForm.repeatPassword"
          clearable
          show-password
          placeholder="确认密码"
          :prefix-icon="useRenderIcon(Lock)"
        />
      </el-form-item>
    </Motion>

    <Motion :delay="150">
      <el-form-item>
        <el-button
          class="w-full"
          size="default"
          type="primary"
          :loading="loading"
          @click="onRegister(ruleFormRef)"
        >
          注 册
        </el-button>
      </el-form-item>
    </Motion>

    <Motion :delay="200">
      <el-form-item>
        <el-button class="w-full" size="default" @click="onBack">
          返回登录
        </el-button>
      </el-form-item>
    </Motion>
  </el-form>
</template>
