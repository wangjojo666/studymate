<template>
  <div v-loading="loading" class="workspace course-detail">
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
          multiple
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
        <CourseDocumentsPanel
          v-model:job-history-open="jobsDrawerOpen"
          :course="course"
          :has-processing-documents="hasProcessingDocuments"
          :reindexing-course="reindexingCourse"
          :reindexing-document-id="reindexingDocumentId"
          :ocr-running-id="ocrRunningId"
          :vision-running-id="visionRunningId"
          :jobs="jobs"
          :jobs-loading="jobsLoading"
          :run-course-reindex="runCourseReindex"
          :run-document-reindex="runDocumentReindex"
          :run-ocr="runOcr"
          :stop-ocr="stopOcr"
          :run-vision="runVision"
          :remove-document="removeDocument"
          :retry-job="retryJob"
          :cancel-job="cancelJob"
          :active-ocr-job="activeOcrJob"
          :ocr-progress="ocrProgress"
          :ocr-progress-status="ocrProgressStatus"
          :ocr-job-text="ocrJobText"
          :status-text="statusText"
          :status-type="statusType"
          :is-document-processing="isDocumentProcessing"
          :can-run-ocr="canRunOcr"
          :can-run-vision="canRunVision"
          @open-job-history="openJobHistory"
        />
      </el-tab-pane>

      <el-tab-pane label="AI 问答" name="qa">
        <CourseQaPanel
          v-model:question="question"
          :messages="messages"
          :asking="asking"
          :has-processing-documents="hasProcessingDocuments"
          :last-answer-status="lastAnswerStatus"
          :last-confidence="lastConfidence"
          :last-retrieval-provider="lastRetrievalProvider"
          :last-llm-provider="lastLlmProvider"
          @ask="ask"
          @open-source="openSource"
        />
      </el-tab-pane>

      <el-tab-pane label="复习提纲" name="outline">
        <CourseOutlinePanel
          :outline="outline"
          :sources="outlineSources"
          :generating="generatingOutline"
          @generate="makeOutline"
          @open-source="openSource"
        />
      </el-tab-pane>

      <el-tab-pane label="专项练习" name="practice">
        <CoursePracticePanel
          v-model:count="practiceCount"
          v-model:difficulty="practiceDifficulty"
          v-model:knowledge-point-id="practiceKnowledgePointId"
          :knowledge-point-options="knowledgePointOptions"
          :generating="generatingPractice"
          :content="practice"
          :sources="practiceSources"
          :items="practiceItems"
          :practice-attempt-state="practiceAttemptState"
          :ensure-practice-state="ensurePracticeState"
          :toggle-practice-answer="togglePracticeAnswer"
          :submit-practice-result="submitPracticeResult"
          @generate="makePractice"
          @open-source="openSource"
        />
      </el-tab-pane>

      <el-tab-pane label="C++ 代码" name="cpp">
        <CourseCppPanel
          :form="cppForm"
          :analysis="cppAnalysis"
          :analyzing="analyzingCpp"
          @analyze="analyzeCpp"
          @read-file="readCppFile"
          @update-form="updateCppForm"
        />
      </el-tab-pane>

      <el-tab-pane label="学习诊断" name="diagnosis">
        <CourseDiagnosisPreview
          :learning-profile="learningProfile"
          :weak-points="diagnosisWeakPoints"
          :ring-style="ringStyle"
          @open-full-diagnosis="router.push(`/courses/${props.id}/diagnosis`)"
        />
      </el-tab-pane>
    </el-tabs>

    <SourceDrawer
      v-model="sourceDrawerOpen"
      :source="activeSource"
      :loading="sourceLoading"
      @copy="copySourceReference"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import SourceDrawer from "../components/SourceDrawer.vue";
import CourseCppPanel from "../components/course/CourseCppPanel.vue";
import CourseDiagnosisPreview from "../components/course/CourseDiagnosisPreview.vue";
import CourseDocumentsPanel from "../components/course/CourseDocumentsPanel.vue";
import CourseOutlinePanel from "../components/course/CourseOutlinePanel.vue";
import CoursePracticePanel from "../components/course/CoursePracticePanel.vue";
import CourseQaPanel from "../components/course/CourseQaPanel.vue";
import {
  analyzeCppCode,
  askCourse,
  generateOutline,
  generatePractice,
  getCourse,
  getLearningProfile,
  isRequestCanceled
} from "../api/client";
import { getApiErrorMessage } from "../api/errors";
import { useCourseDocumentProcessing } from "../composables/useCourseDocumentProcessing";
import { usePracticeAttempts } from "../composables/usePracticeAttempts";
import { useSourceDrawer } from "../composables/useSourceDrawer";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const route = useRoute();
const courseId = computed(() => props.id);
const course = ref(null);
const learningProfile = ref(null);
const loading = ref(false);
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
const practiceItems = ref([]);
const practiceCount = ref(10);
const practiceDifficulty = ref("basic");
const practiceKnowledgePointId = ref(null);
const lastLlmProvider = ref("未调用");
const lastRetrievalProvider = ref("未调用");
const lastAnswerStatus = ref("未调用");
const lastConfidence = ref("low");
const analyzingCpp = ref(false);
const cppAnalysis = ref(null);
const cppForm = reactive({
  problem_text: "",
  code_text: "",
  user_code: "",
  sample_input: ""
});

let loadController = null;
let sessionController = new AbortController();
let loadSequence = 0;
let loadPromise = null;

const knowledgePointOptions = computed(() => learningProfile.value?.knowledge_points || []);
const diagnosisWeakPoints = computed(() => (learningProfile.value?.weak_points || []).slice(0, 5));
const ringStyle = computed(() => {
  const score = learningProfile.value?.summary.overall_mastery || 0;
  const deg = Math.min(360, Math.max(0, score * 3.6));
  return {
    background: `conic-gradient(#16a34a 0deg ${deg}deg, #e5e7eb ${deg}deg 360deg)`
  };
});

const {
  uploading,
  ocrRunningId,
  visionRunningId,
  reindexingCourse,
  reindexingDocumentId,
  jobs,
  jobsLoading,
  jobsDrawerOpen,
  hasProcessingDocuments,
  handleUpload,
  runOcr,
  stopOcr,
  runVision,
  removeDocument,
  runCourseReindex,
  runDocumentReindex,
  openJobHistory,
  retryJob,
  cancelJob,
  syncDocumentPolling,
  resetProcessingState,
  activeOcrJob,
  ocrProgress,
  ocrProgressStatus,
  ocrJobText,
  statusText,
  statusType,
  isDocumentProcessing,
  canRunOcr,
  canRunVision
} = useCourseDocumentProcessing({ courseId, course, loadCourse });

const {
  sourceDrawerOpen,
  activeSource,
  sourceLoading,
  openSource,
  copySourceReference,
  resetSourceDrawer
} = useSourceDrawer({ courseId, lastRetrievalProvider });

const {
  practiceAttemptState,
  resetPracticeState,
  togglePracticeAnswer,
  submitPracticeResult,
  ensurePracticeState
} = usePracticeAttempts({
  courseId,
  practiceDifficulty,
  practiceKnowledgePointId,
  knowledgePointOptions,
  loadCourse
});

watch(
  () => route.query.tab,
  (tab) => {
    activeTab.value = tabFromQuery(tab);
  },
  { immediate: true }
);

watch(
  activeTab,
  (tab) => {
    if (route.query.tab === tab) return;
    const destination = { query: { ...route.query, tab } };
    if (route.query.tab) {
      void router.push(destination);
    } else {
      void router.replace(destination);
    }
  },
  { immediate: true }
);

watch(
  () => props.id,
  () => {
    beginCourseSession();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  loadController?.abort();
  sessionController.abort();
});

async function loadCourse({ silent = false, force = false, signal, expectedCourseId } = {}) {
  const requestCourseId = String(expectedCourseId ?? props.id);
  if (requestCourseId !== String(props.id)) return null;
  if (loadPromise && !force) return loadPromise;
  if (force) loadController?.abort();

  const sequence = ++loadSequence;
  const controller = new AbortController();
  const sessionSignal = sessionController.signal;
  const abortFromExternal = () => controller.abort();
  signal?.addEventListener("abort", abortFromExternal, { once: true });
  if (signal?.aborted || sessionSignal.aborted) controller.abort();
  const abortFromSession = () => controller.abort();
  sessionSignal.addEventListener("abort", abortFromSession, { once: true });
  loadController = controller;
  if (!silent) loading.value = true;

  const request = (async () => {
    try {
      const [courseResult, profileResult] = await Promise.allSettled([
        getCourse(requestCourseId, { signal: controller.signal }),
        getLearningProfile(requestCourseId, { signal: controller.signal })
      ]);
      if (!isLatestCourseRequest(sequence, requestCourseId)) return null;
      if (courseResult.status === "rejected") throw courseResult.reason;

      const courseData = courseResult.value;
      course.value = courseData;
      learningProfile.value = profileResult.status === "fulfilled" ? profileResult.value : null;
      syncDocumentPolling(courseData.documents || []);
      messages.value = mapRecentMessages(courseData.recent_messages || []);
      const latestMessage = messages.value[messages.value.length - 1];
      if (latestMessage) {
        lastAnswerStatus.value = latestMessage.answer_status || "answered";
        lastConfidence.value = latestMessage.confidence || "medium";
        lastRetrievalProvider.value = courseData.recent_messages?.[0]?.retrieval_provider || "未调用";
        lastLlmProvider.value = courseData.recent_messages?.[0]?.llm_provider || "未调用";
      }
      if (profileResult.status === "rejected" && !isRequestCanceled(profileResult.reason) && !silent) {
        ElMessage.warning("课程已加载，但学习画像暂时不可用");
      }
      return courseData;
    } catch (error) {
      if (!isRequestCanceled(error) && isLatestCourseRequest(sequence, requestCourseId) && !silent) {
        ElMessage.error(getApiErrorMessage(error, "课程加载失败，请检查后端服务是否启动"));
      }
      return null;
    } finally {
      signal?.removeEventListener("abort", abortFromExternal);
      sessionSignal.removeEventListener("abort", abortFromSession);
      if (sequence === loadSequence) {
        loadController = null;
        loadPromise = null;
        if (!silent) loading.value = false;
      }
    }
  })();
  loadPromise = request;
  return request;
}

async function ask() {
  if (!question.value.trim()) {
    ElMessage.warning("请输入问题");
    return;
  }
  asking.value = true;
  const requestCourseId = String(props.id);
  const currentQuestion = question.value.trim();
  question.value = "";
  try {
    const result = await askCourse(requestCourseId, currentQuestion, sessionOptions());
    if (!isCurrentCourse(requestCourseId)) return;
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
      sources: result.sources || [],
      retrieval_provider: result.retrieval_provider || "",
      llm_provider: result.llm_provider || result.provider || ""
    });
    await loadCourse({ silent: true, force: true, expectedCourseId: requestCourseId });
  } catch (error) {
    if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
      question.value = currentQuestion;
      ElMessage.error(getApiErrorMessage(error, "请求失败，请检查后端服务是否启动"));
    }
  } finally {
    if (isCurrentCourse(requestCourseId)) asking.value = false;
  }
}

async function makeOutline() {
  const requestCourseId = String(props.id);
  generatingOutline.value = true;
  try {
    const result = await generateOutline(requestCourseId, sessionOptions());
    if (!isCurrentCourse(requestCourseId)) return;
    lastLlmProvider.value = result.provider || "unknown";
    outline.value = result.content;
    outlineSources.value = result.sources;
  } catch (error) {
    if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
      ElMessage.error(getApiErrorMessage(error, "复习提纲生成失败，请检查后端服务是否启动"));
    }
  } finally {
    if (isCurrentCourse(requestCourseId)) generatingOutline.value = false;
  }
}

async function makePractice() {
  const requestCourseId = String(props.id);
  generatingPractice.value = true;
  try {
    const result = await generatePractice(requestCourseId, {
      count: practiceCount.value,
      difficulty: practiceDifficulty.value,
      knowledge_point_id: practiceKnowledgePointId.value || null
    }, sessionOptions());
    if (!isCurrentCourse(requestCourseId)) return;
    lastLlmProvider.value = result.provider || "unknown";
    practice.value = result.content;
    practiceSources.value = result.sources || [];
    practiceItems.value = result.items || [];
    resetPracticeState(practiceItems.value);
    await loadCourse({ silent: true, force: true, expectedCourseId: requestCourseId });
  } catch (error) {
    if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
      ElMessage.error(getApiErrorMessage(error, "练习题生成失败，请检查后端服务是否启动"));
    }
  } finally {
    if (isCurrentCourse(requestCourseId)) generatingPractice.value = false;
  }
}

async function analyzeCpp() {
  if (!cppForm.problem_text.trim() && !cppForm.code_text.trim() && !cppForm.user_code.trim()) {
    ElMessage.warning("请先填写题干或 C++ 代码");
    return;
  }
  const requestCourseId = String(props.id);
  analyzingCpp.value = true;
  try {
    const result = await analyzeCppCode(requestCourseId, cppForm, sessionOptions());
    if (!isCurrentCourse(requestCourseId)) return;
    cppAnalysis.value = result;
    lastLlmProvider.value = result.provider || "rule/offline";
  } catch (error) {
    if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
      ElMessage.error(getApiErrorMessage(error, "C++ 代码分析失败，请检查后端服务是否启动"));
    }
  } finally {
    if (isCurrentCourse(requestCourseId)) analyzingCpp.value = false;
  }
}

function beginCourseSession() {
  loadSequence += 1;
  loadController?.abort();
  loadController = null;
  loadPromise = null;
  sessionController.abort();
  sessionController = new AbortController();
  resetCourseState();
  resetProcessingState();
  resetSourceDrawer();
  resetPracticeState([]);
  void loadCourse({ force: true, expectedCourseId: props.id });
}

function resetCourseState() {
  course.value = null;
  learningProfile.value = null;
  loading.value = false;
  asking.value = false;
  generatingOutline.value = false;
  generatingPractice.value = false;
  analyzingCpp.value = false;
  question.value = "";
  messages.value = [];
  outline.value = "";
  outlineSources.value = [];
  practice.value = "";
  practiceSources.value = [];
  practiceItems.value = [];
  practiceCount.value = 10;
  practiceDifficulty.value = "basic";
  practiceKnowledgePointId.value = null;
  lastLlmProvider.value = "未调用";
  lastRetrievalProvider.value = "未调用";
  lastAnswerStatus.value = "未调用";
  lastConfidence.value = "low";
  cppAnalysis.value = null;
  Object.assign(cppForm, {
    problem_text: "",
    code_text: "",
    user_code: "",
    sample_input: ""
  });
}

function mapRecentMessages(recentMessages) {
  return recentMessages
    .slice()
    .reverse()
    .map((message) => ({
      id: message.id,
      question: message.question,
      answer: message.answer,
      answer_status: message.answer_status || "answered",
      confidence: message.confidence || "medium",
      source_count: message.source_count ?? message.sources?.length ?? 0,
      sources: message.sources || [],
      retrieval_provider: message.retrieval_provider || "",
      llm_provider: message.llm_provider || ""
    }));
}

function isLatestCourseRequest(sequence, requestCourseId) {
  return sequence === loadSequence && isCurrentCourse(requestCourseId);
}

function isCurrentCourse(requestCourseId) {
  return String(props.id) === String(requestCourseId);
}

function sessionOptions() {
  return { signal: sessionController.signal };
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

function updateCppForm(field, value) {
  if (Object.hasOwn(cppForm, field)) cppForm[field] = value;
}

function tabFromQuery(tab) {
  return ["docs", "qa", "outline", "practice", "cpp", "diagnosis"].includes(tab) ? tab : "qa";
}
</script>
