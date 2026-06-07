<template>
  <div class="workspace diagnosis-view" v-loading="loading">
    <section class="diagnosis-hero">
      <div>
        <el-button text @click="router.push(`/courses/${id}?tab=diagnosis`)">
          <el-icon><Back /></el-icon>
          返回课程
        </el-button>
        <span class="eyebrow">Learning Profile</span>
        <h1>AI 学习画像中心</h1>
        <p>{{ course?.name || "课程" }} · 系统根据提问、练习和错题记录动态评估每个知识点的掌握程度。</p>
      </div>
      <el-button @click="loadAll">
        <el-icon><Refresh /></el-icon>
        刷新诊断
      </el-button>
    </section>

    <section class="diagnosis-top-grid">
      <div class="panel mastery-spotlight">
        <div class="panel-title">
          <div>
            <h2>总体掌握度</h2>
            <span>综合知识点掌握、练习正确率和复习记录</span>
          </div>
        </div>
        <VChart class="spotlight-chart" :option="gaugeOption" autoresize />
      </div>

      <div class="panel chart-panel">
        <div class="panel-title">
          <div>
            <h2>知识点掌握雷达</h2>
            <span>{{ profile?.summary.knowledge_point_count || 0 }} 个知识点</span>
          </div>
        </div>
        <VChart class="chart-box" :option="radarOption" autoresize />
      </div>

      <div class="panel today-panel">
        <div class="panel-title">
          <div>
            <h2>今日推荐复习任务</h2>
            <span>优先处理低掌握度知识点</span>
          </div>
          <el-tag type="success">自适应</el-tag>
        </div>
        <div v-if="recommendations.length" class="recommendation-list">
          <div v-for="item in recommendations.slice(0, 4)" :key="item.knowledge_point_id" class="recommendation-item">
            <b>{{ item.rank }}</b>
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.reason }}</span>
              <p>{{ item.action }}</p>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无推荐" />
      </div>
    </section>

    <section class="metrics-grid diagnosis-metrics">
      <div class="metric accent-indigo">
        <span>学习行为</span>
        <strong>{{ profile?.summary.study_actions || 0 }}</strong>
      </div>
      <div class="metric accent-blue">
        <span>提问次数</span>
        <strong>{{ profile?.summary.question_count || 0 }}</strong>
      </div>
      <div class="metric accent-emerald">
        <span>练习正确率</span>
        <strong>{{ profile?.summary.practice_accuracy || 0 }}%</strong>
      </div>
      <div class="metric accent-rose">
        <span>薄弱知识点</span>
        <strong>{{ weakPoints.length }}</strong>
      </div>
    </section>

    <section class="diagnosis-grid">
      <div class="panel chart-panel">
        <div class="panel-title">
          <div>
            <h2>知识点掌握条形图</h2>
            <span>越低越需要进入专项练习</span>
          </div>
        </div>
        <VChart class="chart-box wide" :option="barOption" autoresize />
      </div>

      <div class="panel chart-panel">
        <div class="panel-title">
          <div>
            <h2>错题归因分布</h2>
            <span>按错因聚合最近错题</span>
          </div>
        </div>
        <VChart class="chart-box wide" :option="wrongPieOption" autoresize />
      </div>

      <div class="panel graph-panel">
        <div class="panel-title">
          <div>
            <h2>课程知识图谱</h2>
            <span>节点颜色表示掌握状态，连线表示资料中的关联</span>
          </div>
          <el-tag type="info">{{ graph?.edges.length || 0 }} 条关系</el-tag>
        </div>
        <VChart class="knowledge-graph" :option="graphOption" autoresize />
      </div>

      <div class="panel weak-panel">
        <div class="panel-title">
          <div>
            <h2>薄弱知识点 Top 5</h2>
            <span>点击后可直接写入错题或练习记录</span>
          </div>
          <el-tag type="danger">{{ weakPoints.length }}</el-tag>
        </div>
        <el-empty v-if="weakPoints.length === 0" description="暂无薄弱知识点" />
        <div v-else class="weak-list">
          <div v-for="point in weakPoints.slice(0, 5)" :key="point.id" class="weak-item">
            <div>
              <strong>{{ point.name }}</strong>
              <span>{{ point.mastery_score }}% · 错题 {{ point.wrong_count }} 次</span>
            </div>
            <el-button size="small" @click="prepareAttempt(point)">记录练习</el-button>
          </div>
        </div>
      </div>
    </section>

    <section class="diagnosis-grid lower-grid">
      <div class="panel wrongbook-panel">
        <div class="panel-title">
          <div>
            <h2>错题本与错因分析</h2>
            <span>答题结果会反向更新知识点掌握度</span>
          </div>
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
          <div>
            <h2>考试倒计时复习规划</h2>
            <span>根据考试日期和薄弱点自动排优先级</span>
          </div>
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

        <div class="timeline-list">
          <div v-for="task in visibleTasks" :key="task.id" class="timeline-item">
            <i></i>
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
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart, GaugeChart, GraphChart, PieChart, RadarChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import {
  generateReviewPlan,
  getCourse,
  getKnowledgeGraph,
  getLearningProfile,
  getWrongAttempts,
  submitPracticeAttempt,
  updateReviewTask
} from "../api/client";

use([
  BarChart,
  GaugeChart,
  GraphChart,
  PieChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer
]);

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
const visibleTasks = computed(() => {
  if (plan.value?.tasks?.length) return plan.value.tasks;
  return profile.value?.pending_tasks || [];
});

const gaugeOption = computed(() => ({
  series: [
    {
      type: "gauge",
      min: 0,
      max: 100,
      radius: "92%",
      progress: { show: true, width: 16, itemStyle: { color: "#4f46e5" } },
      axisLine: { lineStyle: { width: 16, color: [[1, "#e2e8f0"]] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        formatter: "{value}%",
        color: "#0f172a",
        fontSize: 34,
        fontWeight: 800,
        offsetCenter: [0, "4%"]
      },
      data: [{ value: profile.value?.summary.overall_mastery || 0 }]
    }
  ]
}));

const radarOption = computed(() => {
  const points = topKnowledgePoints.value.slice(0, 6);
  return {
    tooltip: {},
    radar: {
      radius: "68%",
      indicator: points.map((point) => ({ name: point.name, max: 100 })),
      splitArea: { areaStyle: { color: ["#f8fafc", "#eef2ff"] } },
      axisName: { color: "#334155" }
    },
    series: [
      {
        type: "radar",
        areaStyle: { color: "rgba(79, 70, 229, 0.2)" },
        lineStyle: { color: "#4f46e5", width: 2 },
        data: [{ value: points.map((point) => point.mastery_score), name: "掌握度" }]
      }
    ]
  };
});

const barOption = computed(() => {
  const points = [...pointOptions.value].sort((a, b) => a.mastery_score - b.mastery_score).slice(0, 8);
  return {
    tooltip: {},
    grid: { left: 8, right: 18, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: "value", max: 100, axisLabel: { color: "#64748b" }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
    yAxis: {
      type: "category",
      data: points.map((point) => point.name),
      axisLabel: { color: "#334155" }
    },
    series: [
      {
        type: "bar",
        data: points.map((point) => ({
          value: point.mastery_score,
          itemStyle: { color: point.mastery_score < 60 ? "#ef4444" : point.mastery_score < 80 ? "#f59e0b" : "#16a34a" }
        })),
        barWidth: 12,
        borderRadius: 6
      }
    ]
  };
});

const wrongPieOption = computed(() => {
  const counts = wrongAttempts.value.reduce((map, attempt) => {
    const key = attempt.error_reason || "未标注";
    map[key] = (map[key] || 0) + 1;
    return map;
  }, {});
  const data = Object.entries(counts).map(([name, value]) => ({ name, value }));
  return {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#64748b" } },
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["50%", "43%"],
        data: data.length ? data : [{ name: "暂无错题", value: 1 }],
        color: ["#4f46e5", "#0ea5e9", "#f59e0b", "#ef4444", "#16a34a"]
      }
    ]
  };
});

const graphOption = computed(() => {
  const nodes = graphNodes.value.slice(0, 18).map((node) => ({
    id: String(node.id),
    name: node.name,
    value: node.mastery_score,
    symbolSize: Math.max(34, Math.min(68, 86 - node.mastery_score / 1.5)),
    itemStyle: {
      color: node.state === "weak" ? "#ef4444" : node.state === "solid" ? "#16a34a" : "#4f46e5"
    },
    label: { show: true, color: "#0f172a", fontWeight: 700 }
  }));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = (graph.value?.edges || [])
    .filter((edge) => nodeIds.has(String(edge.source)) && nodeIds.has(String(edge.target)))
    .slice(0, 32)
    .map((edge) => ({ source: String(edge.source), target: String(edge.target), value: edge.relation }));
  return {
    tooltip: {},
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        data: nodes,
        links,
        force: { repulsion: 180, edgeLength: 85 },
        lineStyle: { color: "#94a3b8", width: 1.4, opacity: 0.7 },
        labelLayout: { hideOverlap: true },
        emphasis: { focus: "adjacency" }
      }
    ]
  };
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
