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
          accept=".pdf,.pptx,.docx,.txt,.png,.jpg,.jpeg,.webp"
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
              <span>支持文档、扫描版 PDF 和公式/流程图/代码/电路图片入库</span>
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
                <div v-else-if="isDocumentProcessing(document)" class="ocr-progress">
                  <el-progress :percentage="document.processing_progress || 0" />
                  <small>{{ statusText(document.status) }}</small>
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
                  v-if="canRunVision(document)"
                  size="small"
                  :loading="visionRunningId === document.id || document.status === 'vision_processing'"
                  @click="runVision(document)"
                >
                  识别入库
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
                  :disabled="Boolean(activeOcrJob(document.id)) || isDocumentProcessing(document)"
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
            <div class="provider-tags">
              <el-tag :type="answerStatusType(lastAnswerStatus)">状态：{{ answerStatusText(lastAnswerStatus) }}</el-tag>
              <el-tag :type="confidenceTagType(lastConfidence)">置信度：{{ confidenceText(lastConfidence) }}</el-tag>
              <el-tag type="info">检索：{{ lastRetrievalProvider }}</el-tag>
              <el-tag>模型：{{ lastLlmProvider }}</el-tag>
            </div>
          </div>
          <div class="chat-area">
            <div v-if="messages.length === 0" class="empty-chat">
              <el-icon><ChatLineRound /></el-icon>
              <span>向课程资料提问</span>
            </div>
            <div v-for="message in messages" :key="message.id" class="message-pair">
              <div class="question">{{ message.question }}</div>
              <div class="answer" :class="{ 'answer-warning': message.answer_status === 'low_confidence' }">
                <div class="answer-meta">
                  <el-tag size="small" :type="answerStatusType(message.answer_status)">
                    {{ answerStatusText(message.answer_status) }}
                  </el-tag>
                  <el-tag size="small" :type="confidenceTagType(message.confidence)" effect="plain">
                    置信度：{{ confidenceText(message.confidence) }}
                  </el-tag>
                  <el-tag size="small" type="info" effect="plain">
                    来源 {{ message.source_count ?? message.sources?.length ?? 0 }}
                  </el-tag>
                </div>
                <pre>{{ message.answer }}</pre>
                <div v-if="message.sources?.length" class="source-strip">
                  <button v-for="source in message.sources" :key="sourceKey(source)">
                    《{{ source.document_name }}》P{{ source.page }} · score {{ formatScore(source.score) }}
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
            <small v-if="hasProcessingDocuments" class="ask-hint">资料入库后效果更好</small>
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

      <el-tab-pane label="C++ 代码" name="cpp">
        <div class="panel cpp-panel">
          <div class="panel-title">
            <div>
              <h2>C++ 课程专项能力</h2>
              <span>解释代码、识别继承/虚函数/友元/运算符重载等考点，并诊断用户代码</span>
            </div>
            <div class="inline-actions">
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                accept=".cpp,.cc,.cxx,.h,.hpp,.txt"
                :on-change="readCppFile"
              >
                <el-button>
                  <el-icon><FolderOpened /></el-icon>
                  读取代码文件
                </el-button>
              </el-upload>
              <el-button type="primary" :loading="analyzingCpp" @click="analyzeCpp">
                <el-icon><Cpu /></el-icon>
                分析代码
              </el-button>
            </div>
          </div>

          <div class="cpp-form-grid">
            <el-form label-position="top" @submit.prevent>
              <el-form-item label="代码题/题干">
                <el-input
                  v-model="cppForm.problem_text"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：分析下面程序输出，说明虚函数如何实现运行时多态。"
                />
              </el-form-item>
              <el-form-item label="题目代码或参考代码">
                <el-input
                  v-model="cppForm.code_text"
                  type="textarea"
                  :rows="12"
                  placeholder="粘贴 C++ 题目代码、参考代码或截图识别后的代码文本"
                />
              </el-form-item>
              <el-form-item label="用户代码">
                <el-input
                  v-model="cppForm.user_code"
                  type="textarea"
                  :rows="8"
                  placeholder="可选：粘贴自己的答案，系统会判断可能的错误和遗漏考点"
                />
              </el-form-item>
              <el-form-item label="样例输入">
                <el-input
                  v-model="cppForm.sample_input"
                  type="textarea"
                  :rows="3"
                  placeholder="可选：提供 stdin 样例，编译通过后会限时运行"
                />
              </el-form-item>
            </el-form>

            <div class="cpp-result">
              <div v-if="!cppAnalysis" class="empty-chat cpp-empty">
                <el-icon><Cpu /></el-icon>
                <span>上传或粘贴 C++ 代码后开始分析</span>
              </div>
              <template v-else>
                <div class="cpp-summary">
                  <strong>{{ cppAnalysis.summary }}</strong>
                  <div class="cpp-summary-tags">
                    <el-tag :type="cppAnalysis.sandbox_level === 'disabled' ? 'warning' : 'success'">
                      {{ sandboxText(cppAnalysis.sandbox_level) }}
                    </el-tag>
                    <el-tag>{{ cppAnalysis.provider }}</el-tag>
                  </div>
                </div>
                <div class="cpp-section">
                  <h3>编译诊断</h3>
                  <el-alert
                    v-if="cppAnalysis.sandbox_level === 'disabled'"
                    title="当前处于安全演示模式，未执行本地编译运行。"
                    type="warning"
                    show-icon
                    :closable="false"
                    class="cpp-safe-alert"
                  />
                  <div class="cpp-issue-list">
                    <div class="cpp-issue">
                      <el-tag :type="compileTagType(cppAnalysis)">
                        {{ compileStatusText(cppAnalysis) }}
                      </el-tag>
                      <div>
                        <strong>{{ compileCommandText(cppAnalysis) }}</strong>
                        <span>{{ cppAnalysis.compile_result?.stderr || "无编译错误输出" }}</span>
                      </div>
                    </div>
                    <div v-if="cppAnalysis.run_result?.executed" class="cpp-issue">
                      <el-tag :type="cppAnalysis.run_result?.success ? 'success' : 'danger'">
                        {{ cppAnalysis.run_result?.timeout ? "运行超时" : cppAnalysis.run_result?.success ? "运行成功" : "运行失败" }}
                      </el-tag>
                      <div>
                        <strong>样例运行输出</strong>
                        <span>{{ cppAnalysis.run_result?.stdout || cppAnalysis.run_result?.stderr || "程序无输出" }}</span>
                      </div>
                    </div>
                    <div v-else class="cpp-issue">
                      <el-tag type="info">未运行</el-tag>
                      <div>
                        <strong>样例运行</strong>
                        <span>{{ cppAnalysis.sandbox_level === 'disabled' ? "安全模式下未执行" : "未提供样例输入或编译未通过" }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="cpp-section">
                  <h3>考点识别</h3>
                  <div class="cpp-point-list">
                    <div v-for="point in cppAnalysis.exam_points" :key="point.name" class="cpp-point">
                      <strong>{{ point.name }}</strong>
                      <span>{{ point.exam_hint }}</span>
                      <small>{{ point.evidence }}</small>
                    </div>
                  </div>
                </div>
                <div class="cpp-section">
                  <h3>代码解释</h3>
                  <pre>{{ cppAnalysis.explanation }}</pre>
                </div>
                <div class="cpp-section">
                  <h3>错误诊断</h3>
                  <div class="cpp-issue-list">
                    <div v-for="issue in cppAnalysis.error_diagnosis" :key="`${issue.level}-${issue.title}`" class="cpp-issue">
                      <el-tag :type="issueTagType(issue.level)">{{ issue.level }}</el-tag>
                      <div>
                        <strong>{{ issue.title }}</strong>
                        <span>{{ issue.detail }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="cpp-section">
                  <h3>同类练习题</h3>
                  <div class="cpp-exercise-list">
                    <div v-for="exercise in cppAnalysis.similar_exercises" :key="exercise.title" class="cpp-exercise">
                      <strong>{{ exercise.title }}</strong>
                      <span>{{ exercise.prompt }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </div>
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
                  <span>{{ point.mastery_score }}% · {{ point.level_label }} · 错题 {{ point.wrong_count }} 次</span>
                  <p>{{ point.mastery_formula || point.explanation }}</p>
                  <small>来源：{{ point.source_page ? `P${point.source_page}` : "暂无页码" }} · {{ point.evidence || "暂无证据片段" }}</small>
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
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import {
  analyzeCppCode,
  askCourse,
  cancelOcrJob,
  deleteDocument,
  generateOutline,
  generatePractice,
  getLearningProfile,
  getOcrJob,
  getCourse,
  ocrDocument,
  uploadDocument,
  visionDocument
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
const lastLlmProvider = ref("未调用");
const lastRetrievalProvider = ref("未调用");
const lastAnswerStatus = ref("未调用");
const lastConfidence = ref("low");
const ocrRunningId = ref(null);
const visionRunningId = ref(null);
const ocrJobs = ref({});
const ocrPollTimer = ref(null);
const documentPollTimer = ref(null);
const analyzingCpp = ref(false);
const cppAnalysis = ref(null);
const cppForm = reactive({
  problem_text: "",
  code_text: "",
  user_code: "",
  sample_input: ""
});

const knowledgePointOptions = computed(() => learningProfile.value?.knowledge_points || []);
const diagnosisWeakPoints = computed(() => (learningProfile.value?.weak_points || []).slice(0, 5));
const hasProcessingDocuments = computed(() =>
  (course.value?.documents || []).some((document) => isDocumentProcessing(document))
);
const ringStyle = computed(() => {
  const score = learningProfile.value?.summary.overall_mastery || 0;
  const deg = Math.min(360, Math.max(0, score * 3.6));
  return {
    background: `conic-gradient(#16a34a 0deg ${deg}deg, #e5e7eb ${deg}deg 360deg)`
  };
});

onMounted(loadCourse);
onBeforeUnmount(() => {
  stopOcrPolling();
  stopDocumentPolling();
});

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
    syncDocumentPolling(courseData.documents || []);
    messages.value = (courseData.recent_messages || [])
      .slice()
      .reverse()
      .map((message) => ({
        id: message.id,
        question: message.question,
        answer: message.answer,
        answer_status: message.answer_status || "answered",
        confidence: message.confidence || "medium",
        source_count: message.source_count ?? message.sources?.length ?? 0,
        sources: message.sources || []
      }));
    const latestMessage = messages.value[messages.value.length - 1];
    if (latestMessage) {
      lastAnswerStatus.value = latestMessage.answer_status || "answered";
      lastConfidence.value = latestMessage.confidence || "medium";
      lastRetrievalProvider.value = courseData.recent_messages?.[0]?.retrieval_provider || lastRetrievalProvider.value;
      lastLlmProvider.value = courseData.recent_messages?.[0]?.llm_provider || lastLlmProvider.value;
    }
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
      ElMessage.info("资料已上传，后台解析入库中");
      startDocumentPolling();
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

async function runVision(document) {
  visionRunningId.value = document.id;
  try {
    const updated = await visionDocument(props.id, document.id);
    await loadCourse();
    if (updated.status === "indexed") {
      ElMessage.success(updated.error_message || "图片课件已识别入库");
    } else {
      ElMessage.warning(updated.error_message || "图片课件暂未识别成功");
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "图片识别失败，请确认后端和视觉模型已启动"));
  } finally {
    visionRunningId.value = null;
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

function syncDocumentPolling(documents) {
  if (documents.some((document) => isDocumentProcessing(document))) {
    startDocumentPolling();
  } else {
    stopDocumentPolling();
  }
}

function startDocumentPolling() {
  if (documentPollTimer.value) return;
  documentPollTimer.value = window.setInterval(() => {
    loadCourse();
  }, 2500);
}

function stopDocumentPolling() {
  if (documentPollTimer.value) {
    window.clearInterval(documentPollTimer.value);
    documentPollTimer.value = null;
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
    lastLlmProvider.value = result.llm_provider || result.provider || "unknown";
    lastRetrievalProvider.value = result.retrieval_provider || "unknown";
    lastAnswerStatus.value = result.answer_status || "answered";
    lastConfidence.value = result.confidence || "medium";
    messages.value.push({
      id: Date.now(),
      question: currentQuestion,
      answer: result.answer,
      answer_status: result.answer_status || "answered",
      confidence: result.confidence || "medium",
      source_count: result.source_count ?? result.sources?.length ?? 0,
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
    lastLlmProvider.value = result.provider || "unknown";
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
    lastLlmProvider.value = result.provider || "unknown";
    practice.value = result.content;
    practiceSources.value = result.sources;
    await loadCourse();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "练习题生成失败，请检查后端服务是否启动"));
  } finally {
    generatingPractice.value = false;
  }
}

async function analyzeCpp() {
  if (!cppForm.problem_text.trim() && !cppForm.code_text.trim() && !cppForm.user_code.trim()) {
    ElMessage.warning("请先填写题干或 C++ 代码");
    return;
  }
  analyzingCpp.value = true;
  try {
    cppAnalysis.value = await analyzeCppCode(props.id, cppForm);
    lastLlmProvider.value = cppAnalysis.value.provider || "rule/offline";
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "C++ 代码分析失败，请检查后端服务是否启动"));
  } finally {
    analyzingCpp.value = false;
  }
}

function readCppFile(uploadFile) {
  const rawFile = uploadFile.raw;
  if (!rawFile) return;
  const reader = new FileReader();
  reader.onload = () => {
    cppForm.code_text = String(reader.result || "");
    ElMessage.success("代码文件已读取");
  };
  reader.onerror = () => {
    ElMessage.error("代码文件读取失败");
  };
  reader.readAsText(rawFile, "utf-8");
}

function statusText(status) {
  return {
    uploaded: "已上传，等待解析",
    queued: "已上传，等待解析",
    parsing: "正在解析文本",
    chunking: "正在切分知识片段",
    indexing: "正在写入向量库",
    syncing_knowledge_points: "正在同步知识点",
    indexed: "已入库",
    processing: "解析中",
    needs_ocr: "需 OCR",
    needs_vision: "需识别",
    ocr_queued: "OCR 排队",
    ocr_processing: "OCR 中",
    vision_processing: "识别中",
    failed: "失败",
    empty: "空文档"
  }[status] || status;
}

function statusType(status) {
  return {
    uploaded: "info",
    queued: "info",
    parsing: "warning",
    chunking: "warning",
    indexing: "warning",
    syncing_knowledge_points: "warning",
    indexed: "success",
    processing: "warning",
    needs_ocr: "warning",
    needs_vision: "warning",
    ocr_queued: "warning",
    ocr_processing: "warning",
    vision_processing: "warning",
    failed: "danger",
    empty: "info"
  }[status] || "info";
}

function isDocumentProcessing(document) {
  return ["uploaded", "queued", "parsing", "chunking", "indexing", "syncing_knowledge_points"].includes(document.status);
}

function canRunOcr(document) {
  if (document.file_type !== "pdf") return false;
  if (document.status === "ocr_queued" || document.status === "ocr_processing") return false;
  return document.status === "needs_ocr" || document.error_message?.includes("OCR");
}

function canRunVision(document) {
  if (!["png", "jpg", "jpeg", "webp"].includes(document.file_type)) return false;
  return document.status === "needs_vision" || document.status === "empty";
}

function issueTagType(level) {
  return {
    ok: "success",
    info: "info",
    suggestion: "info",
    warning: "warning",
    error: "danger"
  }[level] || "info";
}

function answerStatusText(status) {
  return {
    answered: "已回答",
    low_confidence: "依据不足",
    empty_knowledge_base: "空知识库",
    processing: "资料处理中",
    needs_ocr: "需要 OCR",
    "未调用": "未调用"
  }[status] || status || "未知";
}

function answerStatusType(status) {
  return {
    answered: "success",
    low_confidence: "warning",
    empty_knowledge_base: "info",
    processing: "warning",
    needs_ocr: "warning",
    "未调用": "info"
  }[status] || "info";
}

function confidenceText(confidence) {
  return {
    high: "高",
    medium: "中",
    low: "低"
  }[confidence] || "低";
}

function confidenceTagType(confidence) {
  return {
    high: "success",
    medium: "warning",
    low: "info"
  }[confidence] || "info";
}

function formatScore(score) {
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(3) : "-";
}

function sandboxText(level) {
  return level === "local_tempdir_timeout_only" ? "本地临时目录+超时" : "安全演示模式";
}

function compileTagType(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "info";
  return analysis?.compile_result?.success ? "success" : "danger";
}

function compileStatusText(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "安全模式下未执行";
  return analysis?.compile_result?.success ? "编译成功" : "编译未通过";
}

function compileCommandText(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "未执行本地编译命令";
  return analysis?.compile_result?.command || "g++ main.cpp -std=c++17";
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
  return ["docs", "qa", "outline", "practice", "cpp", "diagnosis"].includes(tab) ? tab : "qa";
}
</script>
