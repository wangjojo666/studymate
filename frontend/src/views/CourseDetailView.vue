<template>
  <div class="workspace course-detail" v-loading="loading">
    <section class="course-hero">
      <div>
        <el-button text @click="router.push('/courses')">
          <el-icon><Back /></el-icon>
          返回课程
        </el-button>
        <span class="eyebrow">Course Workspace</span>
        <h1>{{ course?.name || "课程详情" }}</h1>
        <p>{{ course?.description || "上传课程资料后即可构建知识库和学习画像。" }}</p>
      </div>
      <div class="toolbar-actions">
        <el-button @click="router.push(`/courses/${props.id}/diagnosis`)">
          <el-icon><DataAnalysis /></el-icon>
          AI 学习画像
        </el-button>
        <el-upload
          :show-file-list="false"
          :http-request="handleUpload"
          accept=".pdf,.pptx,.docx,.txt"
        >
          <el-button type="primary" :loading="uploading">
            <el-icon><Upload /></el-icon>
            上传资料
          </el-button>
        </el-upload>
      </div>
    </section>

    <el-tabs v-model="activeTab" class="course-tabs">
      <el-tab-pane label="资料库" name="docs">
        <div class="panel">
          <div class="panel-title">
            <div>
              <h2>课程资料</h2>
              <span>扫描版 PDF 可先用快速索引模式入库</span>
            </div>
            <el-tag type="info">{{ course?.document_count || 0 }} 份</el-tag>
          </div>
          <el-empty v-if="!course?.documents?.length" description="暂无资料" />
          <div v-else class="document-list">
            <div v-for="document in course.documents" :key="document.id" class="document-item">
              <div class="doc-icon">
                <el-icon><Document /></el-icon>
              </div>
              <div>
                <strong>{{ document.original_filename }}</strong>
                <span>
                  {{ document.file_type.toUpperCase() }} · {{ document.page_count }} 页 ·
                  {{ document.chunk_count }} 片段
                </span>
                <small v-if="document.error_message">{{ document.error_message }}</small>
                <div v-if="activeOcrJob(document.id)" class="ocr-progress">
                  <el-progress
                    :percentage="ocrProgress(activeOcrJob(document.id))"
                    :status="ocrProgressStatus(activeOcrJob(document.id))"
                  />
                  <small>{{ ocrJobText(activeOcrJob(document.id)) }}</small>
                </div>
              </div>
              <div class="document-actions">
                <el-tag :type="statusType(document.status)">{{ statusText(document.status) }}</el-tag>
                <el-button
                  v-if="canRunOcr(document)"
                  size="small"
                  :loading="ocrRunningId === document.id || document.status === 'ocr_queued' || document.status === 'ocr_processing'"
                  @click="runOcr(document)"
                >
                  OCR 入库
                </el-button>
                <el-button
                  v-if="activeOcrJob(document.id)"
                  size="small"
                  type="danger"
                  plain
                  @click="stopOcr(document)"
                >
                  停止
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="Boolean(activeOcrJob(document.id))"
                  @click="removeDocument(document)"
                >
                  删除
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="AI 问答" name="qa">
        <div class="qa-panel panel">
          <div class="panel-title">
            <div>
              <h2>智能问答</h2>
              <span>回答基于已入库课程片段，并展示来源页码</span>
            </div>
            <el-tag>{{ lastProvider }}</el-tag>
          </div>
          <div class="chat-area">
            <div v-if="messages.length === 0" class="empty-chat">
              <el-icon><ChatLineRound /></el-icon>
              <span>向课程资料提问</span>
            </div>
            <div v-for="message in messages" :key="message.id" class="message-pair">
              <div class="question">{{ message.question }}</div>
              <div class="answer">
                <pre>{{ message.answer }}</pre>
                <div v-if="message.sources?.length" class="source-strip">
                  <button v-for="source in message.sources" :key="sourceKey(source)">
                    《{{ source.document_name }}》P{{ source.page }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="ask-bar">
            <el-input
              v-model="question"
              size="large"
              placeholder="例如：第六章空间解析几何的重点是什么？"
              @keyup.enter="ask"
            />
            <el-button type="primary" size="large" :loading="asking" @click="ask">
              <el-icon><Promotion /></el-icon>
              提问
            </el-button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="复习提纲" name="outline">
        <div class="panel material-panel">
          <div class="panel-title">
            <div>
              <h2>复习提纲</h2>
              <span>自动整理核心概念、公式、易错点和可能考法</span>
            </div>
            <el-button :loading="generatingOutline" @click="makeOutline">
              <el-icon><Memo /></el-icon>
              生成
            </el-button>
          </div>
          <pre>{{ outline || "待生成" }}</pre>
          <div v-if="outlineSources.length" class="source-strip">
            <button v-for="source in outlineSources" :key="sourceKey(source)">
              《{{ source.document_name }}》P{{ source.page }}
            </button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="专项练习" name="practice">
        <div class="panel material-panel">
          <div class="panel-title">
            <div>
              <h2>专项练习</h2>
              <span>按难度和知识点生成基础题、提高题、考试题或易错题</span>
            </div>
            <div class="inline-actions">
              <el-select v-model="practiceDifficulty" size="small" class="practice-select">
                <el-option label="基础题" value="basic" />
                <el-option label="提高题" value="advanced" />
                <el-option label="考试题" value="exam" />
                <el-option label="易错题" value="mistake" />
              </el-select>
              <el-select
                v-model="practiceKnowledgePointId"
                size="small"
                class="practice-select"
                clearable
                filterable
                placeholder="知识点"
              >
                <el-option
                  v-for="point in knowledgePointOptions"
                  :key="point.id"
                  :label="point.name"
                  :value="point.id"
                />
              </el-select>
              <el-input-number v-model="practiceCount" :min="1" :max="30" size="small" />
              <el-button :loading="generatingPractice" @click="makePractice">
                <el-icon><EditPen /></el-icon>
                生成
              </el-button>
            </div>
          </div>
          <pre>{{ practice || "待生成" }}</pre>
          <div v-if="practiceSources.length" class="source-strip">
            <button v-for="source in practiceSources" :key="sourceKey(source)">
              《{{ source.document_name }}》P{{ source.page }}
            </button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="学习诊断" name="diagnosis">
        <div class="diagnosis-preview-grid">
          <div class="panel">
            <div class="panel-title">
              <div>
                <h2>总体掌握度</h2>
                <span>根据提问、练习和错题动态更新</span>
              </div>
            </div>
            <div class="mastery-ring compact" :style="ringStyle">
              <span>{{ learningProfile?.summary.overall_mastery || 0 }}%</span>
            </div>
          </div>
          <div class="panel">
            <div class="panel-title">
              <div>
                <h2>薄弱知识点</h2>
                <span>优先进入专项训练</span>
              </div>
              <el-button text @click="router.push(`/courses/${props.id}/diagnosis`)">完整诊断</el-button>
            </div>
            <div class="weak-list">
              <div v-for="point in diagnosisWeakPoints" :key="point.id" class="weak-item">
                <div>
                  <strong>{{ point.name }}</strong>
                  <span>{{ point.mastery_score }}% · 错题 {{ point.wrong_count }} 次</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import {
  askCourse,
  cancelOcrJob,
  deleteDocument,
  generateOutline,
  generatePractice,
  getLearningProfile,
  getOcrJob,
  getCourse,
  ocrDocument,
  uploadDocument
} from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const route = useRoute();
const course = ref(null);
const learningProfile = ref(null);
const loading = ref(false);
const uploading = ref(false);
const asking = ref(false);
const generatingOutline = ref(false);
const generatingPractice = ref(false);
const activeTab = ref(tabFromQuery(route.query.tab));
const question = ref("");
const messages = ref([]);
const outline = ref("");
const outlineSources = ref([]);
const practice = ref("");
const practiceSources = ref([]);
const practiceCount = ref(10);
const practiceDifficulty = ref("basic");
const practiceKnowledgePointId = ref(null);
const lastProvider = ref("未调用");
const ocrRunningId = ref(null);
const ocrJobs = ref({});
const ocrPollTimer = ref(null);

const knowledgePointOptions = computed(() => learningProfile.value?.knowledge_points || []);
const diagnosisWeakPoints = computed(() => (learningProfile.value?.weak_points || []).slice(0, 5));
const ringStyle = computed(() => {
  const score = learningProfile.value?.summary.overall_mastery || 0;
  const deg = Math.min(360, Math.max(0, score * 3.6));
  return {
    background: `conic-gradient(#16a34a 0deg ${deg}deg, #e5e7eb ${deg}deg 360deg)`
  };
});

onMounted(loadCourse);
onBeforeUnmount(stopOcrPolling);

watch(
  () => route.query.tab,
  (tab) => {
    activeTab.value = tabFromQuery(tab);
  }
);

async function loadCourse() {
  loading.value = true;
  try {
    const [courseData, profileData] = await Promise.all([
      getCourse(props.id),
      getLearningProfile(props.id)
    ]);
    course.value = courseData;
    learningProfile.value = profileData;
    messages.value = (courseData.recent_messages || [])
      .slice()
      .reverse()
      .map((message) => ({
        id: message.id,
        question: message.question,
        answer: message.answer,
        sources: message.sources || []
      }));
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "课程加载失败，请检查后端服务是否启动"));
  } finally {
    loading.value = false;
  }
}

async function handleUpload(options) {
  uploading.value = true;
  try {
    const document = await uploadDocument(props.id, options.file);
    await loadCourse();
    if (document.status === "failed") {
      ElMessage.error(document.error_message || "解析失败");
    } else if (document.status === "needs_ocr") {
      ElMessage.warning(document.error_message || "该 PDF 需要 OCR 后才能检索");
    } else if (document.status === "empty") {
      ElMessage.warning(document.error_message || "未解析到可检索文本");
    } else {
      ElMessage.success("资料解析完成");
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "上传失败，请检查后端服务和文件格式"));
  } finally {
    uploading.value = false;
  }
}

async function runOcr(document) {
  let value = nextOcrInput(document);
  try {
    const result = await ElMessageBox.prompt(
      `这份 PDF 共 ${document.page_count} 页。请输入“起始页,页数,模式”，例如 40,8,fast；需要逐字 OCR 时用 full。`,
      "扫描版 PDF OCR 入库",
      {
        inputValue: value,
        inputPattern: /^\s*([1-9]\d*)\s*[,，]\s*([1-9]|[1-4][0-9]|50)(\s*[,，]\s*(fast|full))?\s*$/,
        inputErrorMessage: "请输入类似 40,8,fast 的格式，模式可选 fast 或 full",
        confirmButtonText: "开始 OCR",
        cancelButtonText: "取消"
      }
    );
    value = result.value;
  } catch {
    return;
  }

  ocrRunningId.value = document.id;
  try {
    const parts = value.split(/[,，]/).map((item) => item.trim());
    const startPage = Number(parts[0]);
    const maxPages = Number(parts[1]);
    const mode = parts[2] || "fast";
    const job = await ocrDocument(props.id, document.id, {
      start_page: startPage,
      max_pages: maxPages,
      mode
    });
    setOcrJob(job);
    startOcrPolling(job);
    await loadCourse();
    ElMessage.info("OCR 后台任务已启动，可继续使用页面");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "OCR 启动失败，请确认后端服务正常"));
    await loadCourse();
    ocrRunningId.value = null;
  }
}

async function stopOcr(document) {
  const job = activeOcrJob(document.id);
  if (!job) return;
  try {
    const latest = await cancelOcrJob(props.id, document.id, job.id);
    setOcrJob(latest);
    stopOcrPolling();
    ocrRunningId.value = null;
    await loadCourse();
    ElMessage.success(latest.error_message || "OCR 已停止");
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "停止 OCR 失败"));
  }
}

async function removeDocument(document) {
  try {
    await ElMessageBox.confirm(
      `确定删除资料“${document.original_filename}”吗？相关知识片段和 OCR 任务也会删除。`,
      "删除资料",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning"
      }
    );
  } catch {
    return;
  }

  try {
    await deleteDocument(props.id, document.id);
    ElMessage.success("资料已删除");
    await loadCourse();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "资料删除失败，请检查后端服务是否启动"));
  }
}

function setOcrJob(job) {
  ocrJobs.value = {
    ...ocrJobs.value,
    [job.document_id]: job
  };
}

function startOcrPolling(job) {
  stopOcrPolling();
  pollOcrJob(job);
  ocrPollTimer.value = window.setInterval(() => pollOcrJob(job), 2500);
}

function stopOcrPolling() {
  if (ocrPollTimer.value) {
    window.clearInterval(ocrPollTimer.value);
    ocrPollTimer.value = null;
  }
}

async function pollOcrJob(job) {
  try {
    const latest = await getOcrJob(props.id, job.document_id, job.id);
    setOcrJob(latest);
    if (["completed", "failed", "cancelled"].includes(latest.status)) {
      stopOcrPolling();
      ocrRunningId.value = null;
      await loadCourse();
      if (latest.status === "completed") {
        ElMessage.success(latest.error_message || "OCR 入库完成");
      } else if (latest.status === "failed") {
        ElMessage.error(latest.error_message || "OCR 失败，请确认 Ollama 和视觉模型已启动");
      }
    }
  } catch (error) {
    stopOcrPolling();
    ocrRunningId.value = null;
    ElMessage.error(getApiErrorMessage(error, "OCR 状态刷新失败，请检查后端服务是否启动"));
  }
}

async function ask() {
  if (!question.value.trim()) {
    ElMessage.warning("请输入问题");
    return;
  }
  asking.value = true;
  const currentQuestion = question.value.trim();
  question.value = "";
  try {
    const result = await askCourse(props.id, currentQuestion);
    lastProvider.value = result.provider || "unknown";
    messages.value.push({
      id: Date.now(),
      question: currentQuestion,
      answer: result.answer,
      sources: result.sources
    });
    await loadCourse();
  } catch (error) {
    question.value = currentQuestion;
    ElMessage.error(getApiErrorMessage(error, "请求失败，请检查后端服务是否启动"));
  } finally {
    asking.value = false;
  }
}

async function makeOutline() {
  generatingOutline.value = true;
  try {
    const result = await generateOutline(props.id);
    lastProvider.value = result.provider || "unknown";
    outline.value = result.content;
    outlineSources.value = result.sources;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "复习提纲生成失败，请检查后端服务是否启动"));
  } finally {
    generatingOutline.value = false;
  }
}

async function makePractice() {
  generatingPractice.value = true;
  try {
    const result = await generatePractice(props.id, {
      count: practiceCount.value,
      difficulty: practiceDifficulty.value,
      knowledge_point_id: practiceKnowledgePointId.value || null
    });
    lastProvider.value = result.provider || "unknown";
    practice.value = result.content;
    practiceSources.value = result.sources;
    await loadCourse();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "练习题生成失败，请检查后端服务是否启动"));
  } finally {
    generatingPractice.value = false;
  }
}

function statusText(status) {
  return {
    indexed: "已入库",
    processing: "解析中",
    needs_ocr: "需 OCR",
    ocr_queued: "OCR 排队",
    ocr_processing: "OCR 中",
    failed: "失败",
    empty: "空文档"
  }[status] || status;
}

function statusType(status) {
  return {
    indexed: "success",
    processing: "warning",
    needs_ocr: "warning",
    ocr_queued: "warning",
    ocr_processing: "warning",
    failed: "danger",
    empty: "info"
  }[status] || "info";
}

function canRunOcr(document) {
  if (document.file_type !== "pdf") return false;
  if (document.status === "ocr_queued" || document.status === "ocr_processing") return false;
  return document.status === "needs_ocr" || document.error_message?.includes("OCR");
}

function nextOcrInput(document) {
  const job = activeOcrJob(document.id);
  const start = job?.current_page ? Math.min(document.page_count, job.current_page + 1) : 1;
  return `${start},8,fast`;
}

function activeOcrJob(documentId) {
  const job = ocrJobs.value[documentId];
  if (!job || ["completed", "failed", "cancelled"].includes(job.status)) return null;
  return job;
}

function ocrProgress(job) {
  if (job.status === "completed") return 100;
  return Math.min(100, Math.round((job.processed_pages / Math.max(1, job.max_pages)) * 100));
}

function ocrProgressStatus(job) {
  if (job.status === "failed") return "exception";
  if (job.status === "completed") return "success";
  return undefined;
}

function ocrJobText(job) {
  if (job.status === "queued") return "OCR 任务排队中";
  if (job.status === "failed") return job.error_message || "OCR 失败";
  return job.error_message || `已完成 ${job.processed_pages}/${job.max_pages} 页`;
}

function sourceKey(source) {
  return `${source.document_id}-${source.page}-${source.chunk_index}`;
}

function tabFromQuery(tab) {
  return ["docs", "qa", "outline", "practice", "diagnosis"].includes(tab) ? tab : "qa";
}
</script>
