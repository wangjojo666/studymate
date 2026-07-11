<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="side-nav" aria-label="桌面端主导航">
      <router-link class="brand" to="/" aria-label="返回学习首页">
        <div class="brand-mark" aria-hidden="true">
          <el-icon><Reading /></el-icon>
        </div>
        <div>
          <strong>StudyMate</strong>
          <span>AI 学习画像系统</span>
        </div>
      </router-link>

      <el-menu :default-active="activePath" class="nav-menu" router>
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="model-chip" aria-live="polite" :title="modelLabel">
        <el-icon><Cpu /></el-icon>
        <span>{{ modelLabel }}</span>
      </div>
    </el-aside>

    <el-drawer
      v-model="mobileNavOpen"
      class="mobile-nav-drawer"
      direction="ltr"
      size="min(84vw, 320px)"
      :with-header="false"
      append-to-body
      aria-label="移动端导航抽屉"
    >
      <nav class="mobile-drawer-content" aria-label="移动端主导航">
        <router-link class="brand" to="/" @click="mobileNavOpen = false">
          <div class="brand-mark" aria-hidden="true">
            <el-icon><Reading /></el-icon>
          </div>
          <div>
            <strong>StudyMate</strong>
            <span>AI 学习画像系统</span>
          </div>
        </router-link>
        <el-menu :default-active="activePath" class="nav-menu" router @select="mobileNavOpen = false">
          <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu>
        <div class="model-chip" aria-live="polite">
          <el-icon><Cpu /></el-icon>
          <span>{{ modelLabel }}</span>
        </div>
      </nav>
    </el-drawer>

    <el-container>
      <el-header height="68px" class="topbar">
        <el-button
          class="mobile-menu-button"
          text
          aria-label="打开主导航"
          :aria-expanded="mobileNavOpen"
          @click="mobileNavOpen = true"
        >
          <el-icon><Expand /></el-icon>
        </el-button>
        <div class="topbar-copy">
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
import { computed, markRaw, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ChatLineRound, Collection, DataAnalysis, Document, House } from "@element-plus/icons-vue";

import { clearAuthSession, getHealthDetail, getStoredUser } from "./api/client";

const route = useRoute();
const router = useRouter();
const currentUser = ref(getStoredUser());
const mobileNavOpen = ref(false);
const healthDetail = ref(null);
const healthUnavailable = ref(false);
const HEALTH_REFRESH_MS = 60_000;
let healthRefreshTimer = null;
let healthRequestInFlight = false;
let healthRefreshDisposed = false;

const navItems = [
  { path: "/", label: "学习首页", icon: markRaw(House) },
  { path: "/courses", label: "课程知识库", icon: markRaw(Collection) },
  { path: "/courses?module=qa", label: "智能问答", icon: markRaw(ChatLineRound) },
  { path: "/courses?module=diagnosis", label: "学习诊断", icon: markRaw(DataAnalysis) },
  { path: "/reports", label: "学习报告", icon: markRaw(Document) }
];

const moduleTitleMap = {
  qa: "智能问答",
  diagnosis: "学习诊断"
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
  if (route.path === "/login") return "登录后按账号隔离课程和学习数据";
  if (route.path === "/reports") return "汇总资料、问答、练习与诊断结果";
  if (route.path.endsWith("/diagnosis")) return "掌握度、错题归因、知识图谱和复习计划";
  if (route.path.startsWith("/courses/")) return "资料库、问答、提纲和专项练习";
  if (route.query.module) return "选择一门课程进入对应学习模块";
  return "管理课程资料和本地知识库";
});

const modelLabel = computed(() => {
  if (healthUnavailable.value) return "模型能力暂不可用";
  if (!healthDetail.value) return "正在读取模型能力";
  return providerLabel(healthDetail.value);
});

onMounted(() => {
  document.addEventListener("visibilitychange", handleHealthVisibilityChange);
  void loadHealthDetail();
});

onBeforeUnmount(() => {
  healthRefreshDisposed = true;
  clearHealthRefreshTimer();
  document.removeEventListener("visibilitychange", handleHealthVisibilityChange);
});

async function loadHealthDetail() {
  if (healthRequestInFlight || healthRefreshDisposed || document.hidden) return;
  healthRequestInFlight = true;
  try {
    healthDetail.value = await getHealthDetail();
    healthUnavailable.value = false;
  } catch {
    healthUnavailable.value = true;
  } finally {
    healthRequestInFlight = false;
    scheduleHealthRefresh();
  }
}

function scheduleHealthRefresh() {
  clearHealthRefreshTimer();
  if (healthRefreshDisposed || document.hidden) return;
  healthRefreshTimer = window.setTimeout(() => void loadHealthDetail(), HEALTH_REFRESH_MS);
}

function clearHealthRefreshTimer() {
  if (healthRefreshTimer !== null) {
    window.clearTimeout(healthRefreshTimer);
    healthRefreshTimer = null;
  }
}

function handleHealthVisibilityChange() {
  if (document.hidden) {
    clearHealthRefreshTimer();
    return;
  }
  void loadHealthDetail();
}

function logout() {
  clearAuthSession();
  currentUser.value = null;
  mobileNavOpen.value = false;
  router.replace("/login");
}

watch(
  () => route.fullPath,
  () => {
    currentUser.value = getStoredUser();
    mobileNavOpen.value = false;
  }
);

function providerLabel(payload) {
  if (payload.capability_label) return payload.capability_label;
  const providers = payload.providers || {};
  const retrieval = payload.retrieval || {};
  const textProvider = firstProvider(
    providers.text_generation,
    providers.text,
    payload.text_llm_provider,
    payload.llm_provider,
    payload.text_generation?.provider
  );
  const embeddingProvider = firstProvider(
    providers.embedding,
    retrieval.embedding_provider,
    payload.embedding_provider
  );
  const retrievalProvider = firstProvider(
    providers.retrieval,
    retrieval.active_backend,
    payload.retrieval_provider
  );
  const ocrProvider = firstProvider(
    providers.ocr,
    payload.ocr_llm_provider,
    payload.ocr_provider,
    payload.ocr?.provider
  );

  const generation = generationProviderText(textProvider);
  const search = retrievalProviderText(retrievalProvider, embeddingProvider);
  const ocr = ocrProviderText(ocrProvider);
  return [generation, search, ocr].filter(Boolean).join(" · ");
}

function firstProvider(...values) {
  const value = values.find((item) => item !== undefined && item !== null && item !== "");
  if (typeof value === "object") return String(value.active || value.provider || value.name || "").toLowerCase();
  return String(value || "").toLowerCase();
}

function generationProviderText(provider) {
  if (!provider || ["mock", "offline", "rule", "rules", "system", "none"].includes(provider)) {
    return "离线规则生成";
  }
  if (provider.includes("deepseek")) return "DeepSeek";
  if (provider.includes("ollama")) return "Ollama";
  if (provider.includes("openai")) return "OpenAI 兼容模型";
  return provider;
}

function retrievalProviderText(retrievalProvider, embeddingProvider) {
  const combined = `${retrievalProvider}/${embeddingProvider}`;
  if (combined.includes("hash") || combined.includes("sqlite_sparse") || !combined.replace("/", "")) {
    return "Hash 检索";
  }
  if (combined.includes("bge")) return "BGE Embedding";
  if (retrievalProvider.includes("chroma")) {
    return embeddingProvider ? `${providerName(embeddingProvider)} Embedding` : "Chroma 向量检索";
  }
  return `${providerName(embeddingProvider || retrievalProvider)} 检索`;
}

function ocrProviderText(provider) {
  if (!provider || ["mock", "offline", "none", "disabled"].includes(provider)) return "";
  if (provider.includes("ollama")) return "本地 OCR";
  return `${providerName(provider)} OCR`;
}

function providerName(provider) {
  if (provider.includes("deepseek")) return "DeepSeek";
  if (provider.includes("ollama")) return "Ollama";
  if (provider.includes("openai")) return "OpenAI 兼容";
  return provider;
}
</script>
