<template>
  <section class="login-layout">
    <div class="login-panel">
      <div class="section-heading">
        <span>Demo Access</span>
        <h1>StudyMate</h1>
        <p>第一版采用演示登录，后续可接入真实账号与班级权限。</p>
      </div>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="username" size="large" placeholder="student" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" size="large" placeholder="任意输入" show-password />
        </el-form-item>
        <el-button type="primary" size="large" @click="enter">
          <el-icon><Right /></el-icon>
          进入课程
        </el-button>
      </el-form>
    </div>
    <div class="login-visual" aria-hidden="true">
      <div class="paper-stack">
        <div></div>
        <div></div>
        <div></div>
      </div>
      <div class="quote-line">上传资料 → 解析切分 → 检索增强 → 来源可追溯</div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const username = ref("student");
const password = ref("");

function enter() {
  router.push("/courses");
}
</script>
