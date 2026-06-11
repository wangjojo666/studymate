<template>
  <section class="login-layout">
    <div class="login-panel">
      <div class="section-heading">
        <span>Account</span>
        <h1>StudyMate</h1>
        <p>登录后课程、资料、错题、复习任务和学习报告都会绑定到当前账号。</p>
      </div>

      <el-tabs v-model="mode" class="login-tabs">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form label-position="top" @submit.prevent>
        <el-form-item v-if="mode === 'register'" label="昵称">
          <el-input v-model="form.display_name" size="large" placeholder="例如：Sunny" />
        </el-form-item>
        <el-form-item label="账号邮箱">
          <el-input v-model="form.email" size="large" placeholder="demo@studymate.local" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" size="large" placeholder="studymate-demo" show-password />
        </el-form-item>
        <el-button type="primary" size="large" :loading="submitting" @click="submit">
          <el-icon><Right /></el-icon>
          {{ mode === "login" ? "登录" : "注册并登录" }}
        </el-button>
      </el-form>
    </div>
    <div class="login-visual" aria-hidden="true">
      <div class="paper-stack">
        <div></div>
        <div></div>
        <div></div>
      </div>
      <div class="quote-line">上传资料 -> 提问 -> 做题 -> 出报告</div>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { login, register } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const route = useRoute();
const router = useRouter();
const mode = ref("login");
const submitting = ref(false);
const form = reactive({
  display_name: "",
  email: "demo@studymate.local",
  password: "studymate-demo"
});

async function submit() {
  if (!form.email.trim() || !form.password) {
    ElMessage.warning("请填写账号和密码");
    return;
  }
  submitting.value = true;
  try {
    if (mode.value === "login") {
      await login({ email: form.email.trim(), password: form.password });
    } else {
      await register({
        email: form.email.trim(),
        password: form.password,
        display_name: form.display_name.trim()
      });
    }
    ElMessage.success("已登录");
    router.replace(route.query.redirect || "/");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, mode.value === "login" ? "登录失败" : "注册失败"));
  } finally {
    submitting.value = false;
  }
}
</script>
