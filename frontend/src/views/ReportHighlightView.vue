<template>
  <div class="workspace report-view" v-loading="loading">
    <section class="report-hero">
      <div>
        <span class="eyebrow">Report Showcase</span>
        <h1>学习报告导出</h1>
        <p>把课程资料、RAG 问答、练习诊断和复习计划汇总成一份可下载的 PDF 学习报告。</p>
      </div>
      <div class="report-actions">
        <el-select v-model="selectedCourseId" placeholder="选择课程" size="large">
          <el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id" />
        </el-select>
        <el-button type="primary" size="large" :disabled="!selectedCourseId" :loading="exporting" @click="exportReport">
          <el-icon><Download /></el-icon>
          导出报告
        </el-button>
      </div>
    </section>

    <section class="report-flow">
      <button v-for="step in flowSteps" :key="step.key" type="button" @click="openCourse(step.tab)">
        <el-icon><component :is="step.icon" /></el-icon>
        <strong>{{ step.title }}</strong>
        <span>{{ step.meta }}</span>
      </button>
    </section>

    <section class="metrics-grid dashboard-metrics">
      <div class="metric accent-indigo">
        <span>资料数</span>
        <strong>{{ summary.document_count || 0 }}</strong>
      </div>
      <div class="metric accent-blue">
        <span>知识片段</span>
        <strong>{{ summary.chunk_count || 0 }}</strong>
      </div>
      <div class="metric accent-emerald">
        <span>总体掌握度</span>
        <strong>{{ summary.overall_mastery || 0 }}%</strong>
      </div>
      <div class="metric accent-rose">
        <span>薄弱知识点</span>
        <strong>{{ weakPoints.length }}</strong>
      </div>
    </section>

    <section class="report-grid">
      <div class="panel">
        <div class="panel-title">
          <div>
            <h2>报告内容</h2>
            <span>{{ selectedCourse?.name || "选择课程后生成预览" }}</span>
          </div>
        </div>
        <div class="report-section-list">
          <div v-for="section in reportSections" :key="section">
            <el-icon><CircleCheck /></el-icon>
            <span>{{ section }}</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <div>
            <h2>薄弱点 Top 5</h2>
            <span>导出 PDF 时会写入表格和 AI 建议</span>
          </div>
          <el-button text :disabled="!selectedCourseId" @click="openCourse('diagnosis')">查看诊断</el-button>
        </div>
        <div v-if="weakPoints.length" class="weak-list">
          <div v-for="point in weakPoints.slice(0, 5)" :key="point.id" class="weak-item">
            <div>
              <strong>{{ point.name }}</strong>
              <span>{{ point.mastery_score }}% · 错题 {{ point.wrong_count }} 次</span>
            </div>
            <el-tag :type="point.state === 'weak' ? 'danger' : 'warning'">{{ point.state }}</el-tag>
          </div>
        </div>
        <el-empty v-else description="暂无学习画像数据" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { downloadLearningReport, getCourses, getLearningProfile } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const router = useRouter();
const loading = ref(false);
const exporting = ref(false);
const courses = ref([]);
const selectedCourseId = ref(null);
const profile = ref(null);

const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value));
const summary = computed(() => profile.value?.summary || {});
const weakPoints = computed(() => profile.value?.weak_points || []);
const flowSteps = [
  { key: "upload", title: "上传资料", meta: "PDF / PPTX / DOCX / TXT", tab: "docs", icon: "Upload" },
  { key: "ask", title: "智能问答", meta: "Embedding + Chroma 检索", tab: "qa", icon: "ChatLineRound" },
  { key: "practice", title: "专项练习", meta: "按薄弱点生成题目", tab: "practice", icon: "EditPen" },
  { key: "report", title: "导出报告", meta: "PDF 学习诊断", tab: "diagnosis", icon: "Document" }
];
const reportSections = [
  "课程名称与学习总览",
  "薄弱知识点 Top 5",
  "错题原因分布",
  "最近练习记录",
  "下周复习计划",
  "AI 学习建议"
];

onMounted(loadCourses);

watch(selectedCourseId, async (courseId) => {
  if (!courseId) {
    profile.value = null;
    return;
  }
  await loadProfile(courseId);
});

async function loadCourses() {
  loading.value = true;
  try {
    courses.value = await getCourses();
    selectedCourseId.value = courses.value[0]?.id || null;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "报告页数据加载失败"));
  } finally {
    loading.value = false;
  }
}

async function loadProfile(courseId) {
  try {
    profile.value = await getLearningProfile(courseId);
  } catch {
    profile.value = null;
  }
}

function openCourse(tab) {
  if (!selectedCourseId.value) {
    router.push("/courses");
    return;
  }
  router.push({ path: `/courses/${selectedCourseId.value}`, query: { tab } });
}

async function exportReport() {
  if (!selectedCourseId.value) return;
  exporting.value = true;
  try {
    const blob = await downloadLearningReport(selectedCourseId.value);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `studymate-course-${selectedCourseId.value}-learning-report.pdf`;
    link.click();
    URL.revokeObjectURL(url);
    ElMessage.success("报告已导出");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "报告导出失败"));
  } finally {
    exporting.value = false;
  }
}
</script>
