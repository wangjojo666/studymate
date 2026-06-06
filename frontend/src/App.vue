<template>
  <el-container class="app-shell">
    <el-aside width="232px" class="side-nav">
      <div class="brand">
        <div class="brand-mark">
          <el-icon><Reading /></el-icon>
        </div>
        <div>
          <strong>StudyMate</strong>
          <span>课程资料复习</span>
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
        <span>qwen3-vl:30b</span>
      </div>
    </el-aside>

    <el-container>
      <el-header height="64px" class="topbar">
        <div>
          <strong>{{ pageTitle }}</strong>
          <span>RAG 问答 · 来源引用 · 复习资料生成</span>
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
  if (route.path.startsWith("/courses/")) return "课程详情";
  return "课程知识库";
});
</script>
