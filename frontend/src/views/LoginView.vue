<template>
  <section class="login-layout">
    <div class="login-panel">
      <div class="section-heading">
        <span>Single-user Demo</span>
        <h1>StudyMate</h1>
        <p>当前版本为单用户本地演示版，学习画像、错题和复习任务默认绑定 demo-user。</p>
      </div>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="username" size="large" placeholder="demo-user" />
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
const username = ref("demo-user");
const password = ref("");

function enter() {
  router.push("/courses");
}
</script>
