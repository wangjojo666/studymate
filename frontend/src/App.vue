<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="side-nav">
      <div class="brand" @click="router.push('/')">
        <div class="brand-mark">
          <el-icon><Reading /></el-icon>
        </div>
        <div>
          <strong>StudyMate</strong>
          <span>AI 学习画像系统</span>
        </div>
      </div>

      <el-menu :default-active="activePath" class="nav-menu" @select="handleSelect">
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>学习首页</span>
        </el-menu-item>
        <el-menu-item index="/courses">
          <el-icon><Collection /></el-icon>
          <span>课程知识库</span>
        </el-menu-item>
        <el-menu-item index="/courses?module=qa">
          <el-icon><ChatLineRound /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="/courses?module=diagnosis">
          <el-icon><DataAnalysis /></el-icon>
          <span>学习诊断</span>
        </el-menu-item>
        <el-menu-item index="/courses?module=wrongbook">
          <el-icon><Notebook /></el-icon>
          <span>错题本</span>
        </el-menu-item>
        <el-menu-item index="/courses?module=plan">
          <el-icon><Calendar /></el-icon>
          <span>复习计划</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <span>报告亮点</span>
        </el-menu-item>
        <el-menu-item index="/login">
          <el-icon><Setting /></el-icon>
          <span>账号</span>
        </el-menu-item>
      </el-menu>

      <div class="model-chip">
        <el-icon><Cpu /></el-icon>
        <span>DeepSeek · 本地 OCR · 学习画像</span>
      </div>
    </el-aside>

    <el-container>
      <el-header height="68px" class="topbar">
        <div>
          <strong>{{ pageTitle }}</strong>
          <span>{{ pageSubtitle }}</span>
        </div>
        <div v-if="currentUser" class="account-strip">
          <span>{{ currentUser.display_name || currentUser.email }}</span>
          <el-button text @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { clearAuthSession, getStoredUser } from "./api/client";

const route = useRoute();
const router = useRouter();
const currentUser = ref(getStoredUser());

const moduleTitleMap = {
  qa: "智能问答",
  diagnosis: "学习诊断",
  wrongbook: "错题本",
  plan: "复习计划"
};

const activePath = computed(() => {
  if (route.path === "/courses" && route.query.module) {
    return `/courses?module=${route.query.module}`;
  }
  if (route.path.startsWith("/courses/") && route.path.endsWith("/diagnosis")) {
    return "/courses?module=diagnosis";
  }
  if (route.path.startsWith("/courses/")) {
    return "/courses";
  }
  return route.path;
});

const pageTitle = computed(() => {
  if (route.path === "/") return "学习首页";
  if (route.path === "/login") return "账号登录";
  if (route.path === "/reports") return "学习报告导出";
  if (route.path.endsWith("/diagnosis")) return "AI 学习画像中心";
  if (route.path.startsWith("/courses/")) return "课程工作台";
  if (route.query.module) return moduleTitleMap[route.query.module] || "课程知识库";
  return "课程知识库";
});

const pageSubtitle = computed(() => {
  if (route.path === "/") return "今天应该复习什么，一屏看清楚";
  if (route.path === "/login") return "真实用户登录后按账号隔离课程和学习数据";
  if (route.path === "/reports") return "上传资料、提问、做题、导出 PDF 报告";
  if (route.path.endsWith("/diagnosis")) return "掌握度、错题归因、知识图谱和复习计划";
  if (route.path.startsWith("/courses/")) return "资料库、AI 问答、提纲和专项练习";
  if (route.query.module) return "选择一门课程进入对应学习模块";
  return "管理课程资料和本地知识库";
});

function handleSelect(index) {
  router.push(index);
}

function logout() {
  clearAuthSession();
  currentUser.value = null;
  router.replace("/login");
}

watch(
  () => route.fullPath,
  () => {
    currentUser.value = getStoredUser();
  }
);
</script>
