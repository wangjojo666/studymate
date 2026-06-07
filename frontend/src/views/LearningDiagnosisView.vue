<template>
  <div class="workspace diagnosis-view" v-loading="loading">
    <section class="toolbar-band">
      <div>
        <el-button text @click="router.push(`/courses/${id}`)">
          <el-icon><Back /></el-icon>
          返回课程
        </el-button>
        <h1>学习诊断中心</h1>
        <p>{{ course?.name || "课程" }} · 学习画像、错题归因与复习计划</p>
      </div>
      <el-button @click="loadAll">
        <el-icon><Refresh /></el-icon>
        刷新诊断
      </el-button>
    </section>

    <section class="metrics-grid">
      <div class="metric">
        <span>学习行为</span>
        <strong>{{ profile?.summary.study_actions || 0 }}</strong>
      </div>
      <div class="metric">
        <span>提问次数</span>
        <strong>{{ profile?.summary.question_count || 0 }}</strong>
      </div>
      <div class="metric">
        <span>练习正确率</span>
        <strong>{{ profile?.summary.practice_accuracy || 0 }}%</strong>
      </div>
      <div class="metric">
        <span>总体掌握度</span>
        <strong>{{ profile?.summary.overall_mastery || 0 }}%</strong>
      </div>
    </section>

    <section class="diagnosis-grid">
      <div class="panel mastery-panel">
        <div class="panel-title">
          <h2>知识点掌握雷达</h2>
          <el-tag>{{ profile?.summary.knowledge_point_count || 0 }} 个知识点</el-tag>
        </div>
        <div class="mastery-overview">
          <div class="mastery-ring" :style="ringStyle">
            <span>{{ profile?.summary.overall_mastery || 0 }}%</span>
          </div>
          <div class="mastery-bars">
            <div v-for="point in topKnowledgePoints" :key="point.id" class="mastery-row">
              <div>
                <strong>{{ point.name }}</strong>
                <small>{{ point.review_count }} 次复习 · {{ point.wrong_count }} 次错题</small>
              </div>
              <div class="progress-track">
                <i :class="point.state" :style="{ width: `${point.mastery_score}%` }"></i>
              </div>
              <span>{{ point.mastery_score }}%</span>
            </div>
          </div>
        </div>
      </div>

      <div class="panel weak-panel">
        <div class="panel-title">
          <h2>薄弱知识点 Top 5</h2>
          <el-tag type="danger">{{ weakPoints.length }}</el-tag>
        </div>
        <el-empty v-if="weakPoints.length === 0" description="暂无薄弱知识点" />
        <div v-else class="weak-list">
          <div v-for="point in weakPoints" :key="point.id" class="weak-item">
            <div>
              <strong>{{ point.name }}</strong>
              <span>{{ point.mastery_score }}% · 错题 {{ point.wrong_count }} 次</span>
            </div>
            <el-button size="small" @click="prepareAttempt(point)">记录练习</el-button>
          </div>
        </div>
      </div>

      <div class="panel recommendation-panel">
        <div class="panel-title">
          <h2>推荐复习路径</h2>
          <el-tag type="success">自适应</el-tag>
        </div>
        <el-empty v-if="recommendations.length === 0" description="暂无推荐" />
        <div v-else class="recommendation-list">
          <div v-for="item in recommendations" :key="item.knowledge_point_id" class="recommendation-item">
            <b>{{ item.rank }}</b>
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.reason }}</span>
              <p>{{ item.action }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="panel graph-panel">
        <div class="panel-title">
          <h2>课程知识图谱</h2>
          <el-tag type="info">{{ graph?.edges.length || 0 }} 条关系</el-tag>
        </div>
        <div class="graph-node-cloud">
          <button
            v-for="point in graphNodes"
            :key="point.id"
            :class="['graph-node', point.state]"
            @click="prepareAttempt(point)"
          >
            {{ point.name }}
          </button>
        </div>
        <div v-if="edgeLines.length" class="edge-list">
          <span v-for="edge in edgeLines" :key="edge">{{ edge }}</span>
        </div>
      </div>
    </section>

    <section class="diagnosis-grid lower-grid">
      <div class="panel wrongbook-panel">
        <div class="panel-title">
          <h2>错题本与错因分析</h2>
          <el-tag type="warning">{{ wrongAttempts.length }} 条</el-tag>
        </div>
        <el-form class="attempt-form" label-position="top" @submit.prevent>
          <div class="attempt-form-row">
            <el-form-item label="关联知识点">
              <el-select v-model="attemptForm.knowledge_point_id" clearable filterable placeholder="选择知识点">
                <el-option
                  v-for="point in pointOptions"
                  :key="point.id"
                  :label="point.name"
                  :value="point.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="难度">
              <el-select v-model="attemptForm.difficulty">
                <el-option label="基础题" value="basic" />
                <el-option label="提高题" value="advanced" />
                <el-option label="考试题" value="exam" />
                <el-option label="易错题" value="mistake" />
              </el-select>
            </el-form-item>
            <el-form-item label="结果">
              <el-switch v-model="attemptForm.is_correct" active-text="答对" inactive-text="答错" />
            </el-form-item>
          </div>
          <el-form-item label="题目">
            <el-input v-model="attemptForm.question_text" type="textarea" :rows="2" />
          </el-form-item>
          <div class="attempt-form-row">
            <el-form-item label="我的答案">
              <el-input v-model="attemptForm.user_answer" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="参考答案">
              <el-input v-model="attemptForm.correct_answer" type="textarea" :rows="2" />
            </el-form-item>
          </div>
          <el-form-item label="错因">
            <el-input v-model="attemptForm.error_reason" placeholder="可留空，系统会自动归因" />
          </el-form-item>
          <el-button type="primary" :loading="submittingAttempt" @click="saveAttempt">
            <el-icon><CircleCheck /></el-icon>
            写入学习画像
          </el-button>
        </el-form>

        <div class="wrong-list">
          <div v-for="attempt in wrongAttempts" :key="attempt.id" class="wrong-item">
            <div>
              <strong>{{ attempt.knowledge_point_name || "未标注知识点" }}</strong>
              <span>{{ attempt.difficulty_label }} · {{ attempt.error_reason }} · {{ formatDate(attempt.created_at) }}</span>
            </div>
            <p>{{ attempt.question_text }}</p>
            <small>你的答案：{{ attempt.user_answer || "未填写" }}</small>
            <small>参考答案：{{ attempt.correct_answer || "未填写" }}</small>
          </div>
        </div>
      </div>

      <div class="panel review-plan-panel">
        <div class="panel-title">
          <h2>考试倒计时复习规划</h2>
          <el-tag>{{ plan?.days_left ? `${plan.days_left} 天` : "未生成" }}</el-tag>
        </div>
        <el-form class="review-form" label-position="top" @submit.prevent>
          <div class="attempt-form-row">
            <el-form-item label="考试日期">
              <el-date-picker
                v-model="reviewForm.exam_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
              />
            </el-form-item>
            <el-form-item label="每天可复习">
              <el-input-number v-model="reviewForm.daily_minutes" :min="20" :max="480" :step="10" />
            </el-form-item>
          </div>
          <el-form-item label="复习目标">
            <el-input v-model="reviewForm.goals" placeholder="例如：曲线积分、多重积分、虚函数" />
          </el-form-item>
          <el-button type="primary" :loading="generatingPlan" @click="makeReviewPlan">
            <el-icon><Calendar /></el-icon>
            生成复习计划
          </el-button>
        </el-form>

        <div class="task-list">
          <div v-for="task in visibleTasks" :key="task.id" class="task-item">
            <div>
              <strong>{{ task.title }}</strong>
              <span>{{ formatDate(task.deadline) }} · {{ task.estimated_minutes }} 分钟</span>
              <p>{{ task.description }}</p>
            </div>
            <el-button
              v-if="task.status !== 'done'"
              size="small"
              @click="markTaskDone(task)"
            >
              完成
            </el-button>
            <el-tag v-else type="success">已完成</el-tag>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import {
  generateReviewPlan,
  getCourse,
  getKnowledgeGraph,
  getLearningProfile,
  getWrongAttempts,
  submitPracticeAttempt,
  updateReviewTask
} from "../api/client";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const course = ref(null);
const profile = ref(null);
const graph = ref(null);
const wrongAttempts = ref([]);
const plan = ref(null);
const loading = ref(false);
const submittingAttempt = ref(false);
const generatingPlan = ref(false);

const attemptForm = reactive({
  knowledge_point_id: null,
  difficulty: "basic",
  question_text: "",
  user_answer: "",
  correct_answer: "",
  is_correct: false,
  error_reason: ""
});

const reviewForm = reactive({
  exam_date: "",
  daily_minutes: 90,
  goals: ""
});

const id = computed(() => props.id);
const pointOptions = computed(() => profile.value?.knowledge_points || []);
const weakPoints = computed(() => profile.value?.weak_points || []);
const recommendations = computed(() => profile.value?.recommendations || []);
const topKnowledgePoints = computed(() =>
  [...pointOptions.value].sort((a, b) => b.mastery_score - a.mastery_score).slice(0, 8)
);
const graphNodes = computed(() => graph.value?.nodes || pointOptions.value);
const edgeLines = computed(() => {
  if (!graph.value?.edges?.length) return [];
  const nodeMap = new Map(graphNodes.value.map((node) => [node.id, node.name]));
  return graph.value.edges.slice(0, 8).map((edge) => {
    const relation = edge.relation === "parent" ? "包含" : "关联";
    return `${nodeMap.get(edge.source) || edge.source} ${relation} ${nodeMap.get(edge.target) || edge.target}`;
  });
});
const ringStyle = computed(() => {
  const score = profile.value?.summary.overall_mastery || 0;
  const deg = Math.min(360, Math.max(0, score * 3.6));
  return {
    background: `conic-gradient(#16a34a 0deg ${deg}deg, #e5e7eb ${deg}deg 360deg)`
  };
});
const visibleTasks = computed(() => {
  if (plan.value?.tasks?.length) return plan.value.tasks;
  return profile.value?.pending_tasks || [];
});

onMounted(loadAll);

async function loadAll() {
  loading.value = true;
  try {
    const [courseData, profileData, graphData, wrongData] = await Promise.all([
      getCourse(props.id),
      getLearningProfile(props.id),
      getKnowledgeGraph(props.id),
      getWrongAttempts(props.id)
    ]);
    course.value = courseData;
    profile.value = profileData;
    graph.value = graphData;
    wrongAttempts.value = wrongData;
  } finally {
    loading.value = false;
  }
}

function prepareAttempt(point) {
  attemptForm.knowledge_point_id = point.id;
  attemptForm.difficulty = point.state === "weak" ? "mistake" : "basic";
}

async function saveAttempt() {
  if (!attemptForm.question_text.trim()) {
    ElMessage.warning("请填写题目");
    return;
  }
  submittingAttempt.value = true;
  try {
    const result = await submitPracticeAttempt(props.id, {
      ...attemptForm,
      knowledge_point_id: attemptForm.knowledge_point_id || null
    });
    ElMessage.success(result.next_training?.description || "练习结果已记录");
    resetAttemptForm();
    await loadAll();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "记录失败");
  } finally {
    submittingAttempt.value = false;
  }
}

async function makeReviewPlan() {
  if (!reviewForm.exam_date) {
    ElMessage.warning("请选择考试日期");
    return;
  }
  generatingPlan.value = true;
  try {
    plan.value = await generateReviewPlan(props.id, reviewForm);
    await loadAll();
    ElMessage.success("复习计划已生成");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "复习计划生成失败");
  } finally {
    generatingPlan.value = false;
  }
}

async function markTaskDone(task) {
  const updated = await updateReviewTask(props.id, task.id, "done");
  if (plan.value?.tasks?.length) {
    plan.value.tasks = plan.value.tasks.map((item) => (item.id === updated.id ? updated : item));
  }
  ElMessage.success("已更新掌握度");
  await loadAll();
}

function resetAttemptForm() {
  attemptForm.knowledge_point_id = null;
  attemptForm.difficulty = "basic";
  attemptForm.question_text = "";
  attemptForm.user_answer = "";
  attemptForm.correct_answer = "";
  attemptForm.is_correct = false;
  attemptForm.error_reason = "";
}

function formatDate(value) {
  if (!value) return "未安排";
  return new Date(value).toLocaleString();
}
</script>
