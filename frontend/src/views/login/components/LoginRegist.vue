<script setup lang="ts">
import { ref, reactive } from "vue";
import Motion from "../utils/motion";
import { message } from "@/utils/message";
import type { FormInstance } from "element-plus";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useUserStoreHook } from "@/store/modules/user";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";

const loading = ref(false);
const ruleFormRef = ref<FormInstance>();
const ruleForm = reactive({
  username: "",
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
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: ruleForm.username,
          password: ruleForm.password,
          nickname: ruleForm.username
        })
      });
      const data = await res.json();
      if (res.ok && data.code === 200) {
        message("注册成功，请返回登录", { type: "success" });
        useUserStoreHook().SET_CURRENTPAGE(0);
      } else {
        message(data.message || "注册失败", { type: "error" });
      }
    } catch {
      message("注册功能暂未开放，请联系管理员", { type: "warning" });
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
          placeholder="用户名（3-50位字母、数字、下划线）"
          :prefix-icon="useRenderIcon(User)"
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

    <Motion :delay="150">
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

    <Motion :delay="200">
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

    <Motion :delay="250">
      <el-form-item>
        <el-button class="w-full" size="default" @click="onBack">
          返回登录
        </el-button>
      </el-form-item>
    </Motion>
  </el-form>
</template>
