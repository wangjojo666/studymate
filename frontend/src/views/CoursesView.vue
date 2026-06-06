<template>
  <div class="workspace">
    <section class="toolbar-band">
      <div>
        <h1>课程列表</h1>
        <p>按课程组织资料、知识库与问答记录。</p>
      </div>
      <el-button type="primary" @click="dialogVisible = true">
        <el-icon><Plus /></el-icon>
        新建课程
      </el-button>
    </section>

    <section class="metrics-grid">
      <div class="metric">
        <span>课程数</span>
        <strong>{{ courses.length }}</strong>
      </div>
      <div class="metric">
        <span>资料数</span>
        <strong>{{ totalDocuments }}</strong>
      </div>
      <div class="metric">
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
          @click="router.push(`/courses/${course.id}`)"
        >
          <div class="course-card-header">
            <div>
              <h2>{{ course.name }}</h2>
              <p>{{ course.description || "暂无课程说明" }}</p>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </div>
          <div class="course-stats">
            <span>{{ course.document_count }} 份资料</span>
            <span>{{ course.chunk_count }} 个片段</span>
            <span>{{ formatDate(course.last_asked_at) }}</span>
          </div>
        </article>
      </section>
    </el-skeleton>

    <el-dialog v-model="dialogVisible" title="新建课程" width="420px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="课程名称">
          <el-input v-model="form.name" placeholder="例如：数据结构" />
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
import { useRouter } from "vue-router";

import { createCourse, getCourses } from "../api/client";

const router = useRouter();
const loading = ref(true);
const saving = ref(false);
const dialogVisible = ref(false);
const courses = ref([]);
const form = reactive({ name: "", description: "" });

const totalDocuments = computed(() =>
  courses.value.reduce((sum, course) => sum + course.document_count, 0)
);
const totalChunks = computed(() => courses.value.reduce((sum, course) => sum + course.chunk_count, 0));

onMounted(loadCourses);

async function loadCourses() {
  loading.value = true;
  try {
    courses.value = await getCourses();
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
    ElMessage.error(error.response?.data?.detail || "创建失败");
  } finally {
    saving.value = false;
  }
}

function formatDate(value) {
  if (!value) return "未提问";
  return new Date(value).toLocaleString();
}
</script>
