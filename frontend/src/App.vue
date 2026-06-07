<template>
  <el-container class="app-shell">
    <el-aside width="232px" class="side-nav">
      <div class="brand">
        <div class="brand-mark">
          <el-icon><Reading /></el-icon>
        </div>
        <div>
          <strong>StudyMate</strong>
          <span>个性化复习诊断</span>
        </div>
      </div>

      <el-menu :default-active="activePath" router class="nav-menu">
        <el-menu-item index="/courses">
          <el-icon><Collection /></el-icon>
          <span>课程知识库</span>
        </el-menu-item>
        <el-menu-item index="/login">
          <el-icon><User /></el-icon>
          <span>演示登录</span>
        </el-menu-item>
      </el-menu>

      <div class="model-chip">
        <el-icon><Cpu /></el-icon>
        <span>DeepSeek · 本地 OCR</span>
      </div>
    </el-aside>

    <el-container>
      <el-header height="64px" class="topbar">
        <div>
          <strong>{{ pageTitle }}</strong>
        <span>RAG 问答 · 掌握度评估 · 自适应复习</span>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const activePath = computed(() => (route.path.startsWith("/courses") ? "/courses" : route.path));
const pageTitle = computed(() => {
  if (route.path === "/login") return "演示登录";
  if (route.path.endsWith("/diagnosis")) return "学习诊断中心";
  if (route.path.startsWith("/courses/")) return "课程详情";
  return "课程知识库";
});
</script>
