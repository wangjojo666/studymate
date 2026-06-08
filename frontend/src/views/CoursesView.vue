<template>
  <div class="workspace courses-view">
    <section class="library-hero">
      <div>
        <span class="eyebrow">Course Library</span>
        <h1>{{ moduleTitle }}</h1>
        <p>{{ moduleSubtitle }}</p>
      </div>
      <el-button type="primary" size="large" @click="dialogVisible = true">
        <el-icon><Plus /></el-icon>
        新建课程
      </el-button>
    </section>

    <section class="metrics-grid">
      <div class="metric accent-indigo">
        <span>课程数</span>
        <strong>{{ courses.length }}</strong>
      </div>
      <div class="metric accent-blue">
        <span>资料数</span>
        <strong>{{ totalDocuments }}</strong>
      </div>
      <div class="metric accent-emerald">
        <span>知识片段</span>
        <strong>{{ totalChunks }}</strong>
      </div>
    </section>

    <el-skeleton :loading="loading" animated :rows="6">
      <section class="course-grid">
        <article
          v-for="course in courses"
          :key="course.id"
          class="course-card"
          @click="openCourse(course)"
        >
          <div class="course-card-header">
            <div>
              <span class="course-pill">{{ course.document_count }} 份资料</span>
              <h2>{{ course.name }}</h2>
              <p>{{ course.description || "暂无课程说明" }}</p>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </div>
          <div class="course-stats">
            <span>{{ course.chunk_count }} 个片段</span>
            <span>{{ formatDate(course.last_asked_at) }}</span>
          </div>
        </article>
      </section>
    </el-skeleton>

    <el-dialog v-model="dialogVisible" title="新建课程" width="420px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="课程名称">
          <el-input v-model="form.name" placeholder="例如：高等数学" />
        </el-form-item>
        <el-form-item label="课程说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCourse">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { createCourse, getCourses } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const router = useRouter();
const route = useRoute();
const loading = ref(true);
const saving = ref(false);
const dialogVisible = ref(false);
const courses = ref([]);
const form = reactive({ name: "", description: "" });

const moduleCopy = {
  qa: ["选择课程进入智能问答", "基于课程资料提问，回答会保留来源页码。"],
  diagnosis: ["选择课程查看学习诊断", "查看掌握度、薄弱知识点、知识图谱和推荐任务。"],
  wrongbook: ["选择课程查看错题本", "记录错题、分析错因，并把薄弱知识点加入复习任务。"],
  plan: ["选择课程生成复习计划", "根据考试时间和掌握度，安排倒计时复习路径。"]
};

const moduleTitle = computed(() => moduleCopy[route.query.module]?.[0] || "课程知识库");
const moduleSubtitle = computed(() =>
  moduleCopy[route.query.module]?.[1] || "按课程组织资料、知识库、问答记录和学习画像。"
);
const totalDocuments = computed(() =>
  courses.value.reduce((sum, course) => sum + course.document_count, 0)
);
const totalChunks = computed(() => courses.value.reduce((sum, course) => sum + course.chunk_count, 0));

onMounted(loadCourses);

async function loadCourses() {
  loading.value = true;
  try {
    courses.value = await getCourses();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "课程列表加载失败，请检查后端服务是否启动"));
  } finally {
    loading.value = false;
  }
}

async function saveCourse() {
  if (!form.name.trim()) {
    ElMessage.warning("请输入课程名称");
    return;
  }
  saving.value = true;
  try {
    const course = await createCourse({ name: form.name, description: form.description });
    dialogVisible.value = false;
    form.name = "";
    form.description = "";
    courses.value.unshift(course);
    ElMessage.success("课程已创建");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "创建失败，请检查后端服务是否启动"));
  } finally {
    saving.value = false;
  }
}

function openCourse(course) {
  const tabByModule = {
    qa: "qa",
    diagnosis: "diagnosis",
    wrongbook: "diagnosis",
    plan: "diagnosis"
  };
  const tab = tabByModule[route.query.module];
  router.push({
    path: `/courses/${course.id}`,
    query: tab ? { tab } : {}
  });
}

function formatDate(value) {
  if (!value) return "未提问";
  return new Date(value).toLocaleString();
}
</script>
