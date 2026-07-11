<template>
  <div v-loading="loading" class="workspace dashboard-view">
    <section class="dashboard-hero">
      <div class="hero-copy">
        <span class="eyebrow">StudyMate</span>
        <h1>智能课程复习助手</h1>
        <p>围绕课程资料、知识图谱、错题归因和复习计划，生成今天最该完成的学习任务。</p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="goPrimaryCourse('docs')">
            <el-icon><Upload /></el-icon>
            上传资料
          </el-button>
          <el-button size="large" @click="router.push('/courses')">
            <el-icon><Collection /></el-icon>
            进入课程知识库
          </el-button>
        </div>
      </div>
      <div class="today-focus">
        <span>今日建议</span>
        <strong>{{ primaryWeakPoint?.name || "先建立一门课程知识库" }}</strong>
        <p>{{ todayAdvice }}</p>
        <el-button text @click="goPrimaryCourse('diagnosis')">
          查看学习画像
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </section>

    <section class="metrics-grid dashboard-metrics">
      <div class="metric accent-indigo">
        <span>课程数</span>
        <strong>{{ courses.length }}</strong>
      </div>
      <div class="metric accent-blue">
        <span>资料数</span>
        <strong>{{ totalDocuments }}</strong>
      </div>
      <div class="metric accent-emerald">
        <span>知识点</span>
        <strong>{{ totalKnowledgePoints }}</strong>
      </div>
      <div class="metric accent-rose">
        <span>薄弱点</span>
        <strong>{{ totalWeakPoints }}</strong>
      </div>
    </section>

    <section class="learning-cue-grid">
      <div class="panel cue-panel">
        <span>今日待复习</span>
        <strong>{{ todayTasks.length }}</strong>
        <p>{{ todayTasks[0]?.title || todayTasks[0]?.action || "暂无待办，先生成复习计划" }}</p>
      </div>
      <div class="panel cue-panel">
        <span>最近一次提问</span>
        <strong>{{ recentQuestion ? formatDate(recentQuestion.created_at) : "未提问" }}</strong>
        <p>{{ recentQuestion?.question || "进入课程后向资料提一个问题" }}</p>
      </div>
      <div class="panel cue-panel">
        <span>最近错题</span>
        <strong>{{ recentWrongAttempt?.knowledge_point_name || "暂无错题" }}</strong>
        <p>{{ recentWrongAttempt?.error_reason || "记录练习结果后会自动归因" }}</p>
      </div>
      <div class="panel cue-panel">
        <span>考试倒计时</span>
        <strong>{{ examCountdownText }}</strong>
        <p>{{ nearestTask?.title || "生成复习计划后自动显示最近节点" }}</p>
      </div>
      <div class="panel cue-panel trend-panel">
        <span>本周学习趋势</span>
        <div class="trend-bars" aria-label="本周学习趋势">
          <i
            v-for="item in weeklyTrend"
            :key="item.label"
            :style="{ height: `${Math.min(58, Math.max(16, item.value * 18))}px` }"
            :title="`${item.label}：${item.value} 次`"
          ></i>
        </div>
        <p>{{ weeklyTrendTotal }} 次学习行为</p>
      </div>
    </section>

    <section class="dashboard-grid">
      <div class="panel quick-ask-panel">
        <div class="panel-title">
          <div>
            <h2>快速提问</h2>
            <span>默认基于最近课程资料回答</span>
          </div>
          <el-tag>{{ selectedCourse?.name || "未选择课程" }}</el-tag>
        </div>
        <div class="quick-ask-controls">
          <el-select v-model="selectedCourseId" placeholder="选择课程">
            <el-option
              v-for="course in courses"
              :key="course.id"
              :label="course.name"
              :value="course.id"
            />
          </el-select>
          <el-input
            v-model="quickQuestion"
            placeholder="例如：第六章空间解析几何的重点是什么？"
            @keyup.enter="ask"
          />
          <el-button type="primary" :loading="asking" @click="ask">
            <el-icon><Promotion /></el-icon>
            提问
          </el-button>
        </div>
        <pre v-if="quickAnswer" class="quick-answer">{{ quickAnswer }}</pre>
      </div>

      <div class="panel recommendations-panel">
        <div class="panel-title">
          <div>
            <h2>今日推荐复习任务</h2>
            <span>根据薄弱知识点和待办任务生成</span>
          </div>
          <el-button text @click="goPrimaryCourse('diagnosis')">全部</el-button>
        </div>
        <div v-if="todayTasks.length" class="task-list compact-list">
          <div v-for="task in todayTasks" :key="task.id || task.title" class="task-item">
            <div>
              <strong>{{ task.title }}</strong>
              <span>{{ task.description || task.action }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无推荐任务，先上传资料或记录练习结果" />
      </div>

      <div class="panel recent-panel">
        <div class="panel-title">
          <div>
            <h2>最近课程</h2>
            <span>继续上次的学习进度</span>
          </div>
          <el-button text @click="router.push('/courses')">管理</el-button>
        </div>
        <div class="recent-course-list">
          <router-link
            v-for="course in recentCourses"
            :key="course.id"
            class="recent-course"
            :to="`/courses/${course.id}`"
          >
            <div>
              <strong>{{ course.name }}</strong>
              <span>{{ course.document_count }} 份资料 · {{ course.chunk_count }} 个片段</span>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </router-link>
        </div>
      </div>

      <div class="panel weak-panel">
        <div class="panel-title">
          <div>
            <h2>薄弱知识点提醒</h2>
            <span>优先复习掌握度较低的内容</span>
          </div>
        </div>
        <div v-if="weakPoints.length" class="weak-list">
          <div v-for="point in weakPoints.slice(0, 5)" :key="point.id" class="weak-item">
            <div>
              <strong>{{ point.name }}</strong>
              <span>{{ point.mastery_score }}% · 错题 {{ point.wrong_count }} 次</span>
            </div>
            <el-tag :type="point.mastery_score < 50 ? 'danger' : 'warning'">
              {{ point.state === "weak" ? "需补弱" : "待巩固" }}
            </el-tag>
          </div>
        </div>
        <el-empty v-else description="暂无薄弱知识点" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { askCourse, getDashboardSummary } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const router = useRouter();
const loading = ref(false);
const asking = ref(false);
const courses = ref([]);
const profiles = ref([]);
const dashboardSummary = ref(null);
const selectedCourseId = ref(null);
const quickQuestion = ref("");
const quickAnswer = ref("");
let askSequence = 0;

const totalDocuments = computed(() =>
  dashboardSummary.value?.summary?.document_count
    ?? courses.value.reduce((sum, course) => sum + course.document_count, 0)
);
const totalKnowledgePoints = computed(() =>
  dashboardSummary.value?.summary?.knowledge_point_count
    ?? profiles.value.reduce((sum, profile) => sum + (profile?.summary?.knowledge_point_count || 0), 0)
);
const weakPoints = computed(() =>
  (dashboardSummary.value?.weak_points || profiles.value.flatMap((profile) => profile?.weak_points || []))
    .slice()
    .sort((a, b) => a.mastery_score - b.mastery_score)
);
const totalWeakPoints = computed(() =>
  dashboardSummary.value?.summary?.weak_point_count ?? weakPoints.value.length
);
const primaryWeakPoint = computed(() => weakPoints.value[0]);
const recentCourses = computed(() => courses.value.slice(0, 4));
const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value));
const primaryCourse = computed(() => selectedCourse.value || courses.value[0]);
const todayTasks = computed(() => {
  const pending = dashboardSummary.value?.pending_tasks
    || profiles.value.flatMap((profile) => profile?.pending_tasks || []);
  if (pending.length) return pending.slice(0, 4);
  return (dashboardSummary.value?.recommendations
    || profiles.value.flatMap((profile) => profile?.recommendations || [])).slice(0, 4);
});
const recentQuestion = computed(() =>
  newestByDate(dashboardSummary.value?.recent_questions
    || profiles.value.flatMap((profile) => profile?.recent_questions || []))
);
const recentWrongAttempt = computed(() =>
  newestByDate(
    (dashboardSummary.value?.recent_attempts
      || profiles.value.flatMap((profile) => profile?.recent_attempts || []))
      .filter((attempt) => !attempt.is_correct)
  )
);
const nearestTask = computed(() => {
  const datedTasks = (dashboardSummary.value?.pending_tasks
    || profiles.value.flatMap((profile) => profile?.pending_tasks || []))
    .filter((task) => task.deadline)
    .sort((a, b) => new Date(a.deadline) - new Date(b.deadline));
  return datedTasks[0] || null;
});
const examCountdownText = computed(() => {
  if (!nearestTask.value?.deadline) return "未安排";
  const days = Math.max(0, Math.ceil((new Date(nearestTask.value.deadline) - new Date()) / 86400000));
  return `${days} 天`;
});
const weeklyTrend = computed(() => {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - (6 - index));
    return {
      key: date.toISOString().slice(0, 10),
      label: ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()],
      value: 0
    };
  });
  const byKey = Object.fromEntries(days.map((day) => [day.key, day]));
  const events = dashboardSummary.value
    ? [
        ...(dashboardSummary.value.recent_questions || []),
        ...(dashboardSummary.value.recent_attempts || [])
      ]
    : profiles.value.flatMap((profile) => [
        ...(profile?.recent_questions || []),
        ...(profile?.recent_attempts || [])
      ]);
  for (const event of events) {
    const key = event.created_at ? new Date(event.created_at).toISOString().slice(0, 10) : "";
    if (byKey[key]) byKey[key].value += 1;
  }
  if (events.length && days.every((day) => day.value === 0)) {
    days[days.length - 1].value = events.length;
  }
  return days;
});
const weeklyTrendTotal = computed(() => weeklyTrend.value.reduce((sum, item) => sum + item.value, 0));
const todayAdvice = computed(() => {
  if (!courses.value.length) return "先创建课程并上传资料，系统会自动生成学习画像。";
  if (primaryWeakPoint.value) {
    return `建议先复习 ${primaryWeakPoint.value.name}，再完成一组易错题。`;
  }
  return "继续提问或记录练习结果，系统会动态调整复习路径。";
});

onMounted(loadDashboard);

async function loadDashboard() {
  loading.value = true;
  try {
    const payload = normalizeDashboardSummary(await getDashboardSummary());
    dashboardSummary.value = payload;
    courses.value = payload.courses;
    profiles.value = [];
    if (!courses.value.some((course) => course.id === selectedCourseId.value)) {
      selectedCourseId.value = courses.value[0]?.id || null;
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "首页数据加载失败，请检查后端服务是否启动"));
  } finally {
    loading.value = false;
  }
}

async function ask() {
  if (!selectedCourseId.value) {
    ElMessage.warning("请先创建或选择课程");
    return;
  }
  if (!quickQuestion.value.trim()) {
    ElMessage.warning("请输入问题");
    return;
  }
  const requestCourseId = selectedCourseId.value;
  const sequence = ++askSequence;
  asking.value = true;
  try {
    const result = await askCourse(requestCourseId, quickQuestion.value.trim());
    if (sequence !== askSequence || requestCourseId !== selectedCourseId.value) return;
    quickAnswer.value = result.answer;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "请求失败，请检查后端服务是否启动"));
  } finally {
    if (sequence === askSequence) asking.value = false;
  }
}

function normalizeDashboardSummary(payload) {
  const data = payload?.data || payload || {};
  return {
    ...data,
    courses: Array.isArray(data.courses) ? data.courses : [],
    summary: data.summary || {},
    weak_points: Array.isArray(data.weak_points) ? data.weak_points : [],
    pending_tasks: Array.isArray(data.pending_tasks) ? data.pending_tasks : [],
    recommendations: Array.isArray(data.recommendations) ? data.recommendations : [],
    recent_questions: Array.isArray(data.recent_questions) ? data.recent_questions : [],
    recent_attempts: Array.isArray(data.recent_attempts) ? data.recent_attempts : []
  };
}

function goPrimaryCourse(tab) {
  if (!primaryCourse.value) {
    router.push("/courses");
    return;
  }
  router.push({ path: `/courses/${primaryCourse.value.id}`, query: { tab } });
}

function newestByDate(items) {
  return [...items].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0] || null;
}

function formatDate(value) {
  if (!value) return "未记录";
  return new Date(value).toLocaleString();
}
</script>
