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
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import SourceDrawer from "../components/SourceDrawer.vue";
import CourseCppPanel from "../components/course/CourseCppPanel.vue";
import CourseDiagnosisPreview from "../components/course/CourseDiagnosisPreview.vue";
import CourseDocumentsPanel from "../components/course/CourseDocumentsPanel.vue";
import CourseOutlinePanel from "../components/course/CourseOutlinePanel.vue";
import CoursePracticePanel from "../components/course/CoursePracticePanel.vue";
import CourseQaPanel from "../components/course/CourseQaPanel.vue";
import { analyzeCppCode, askCourse, generateOutline, generatePractice, getCourse, getLearningProfile } from "../api/client";
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
  copySourceReference
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

onMounted(loadCourse);

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
        sources: message.sources || [],
        retrieval_provider: message.retrieval_provider || "",
        llm_provider: message.llm_provider || ""
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
      sources: result.sources || [],
      retrieval_provider: result.retrieval_provider || "",
      llm_provider: result.llm_provider || result.provider || ""
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
    practiceSources.value = result.sources || [];
    practiceItems.value = result.items || [];
    resetPracticeState(practiceItems.value);
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

function tabFromQuery(tab) {
  return ["docs", "qa", "outline", "practice", "cpp", "diagnosis"].includes(tab) ? tab : "qa";
}
</script>
