<template>
  <div class="workspace course-detail" v-loading="loading">
    <section class="toolbar-band">
      <div>
        <el-button text @click="router.push('/courses')">
          <el-icon><Back /></el-icon>
          返回课程
        </el-button>
        <h1>{{ course?.name || "课程详情" }}</h1>
        <p>{{ course?.description || "上传课程资料后即可构建知识库。" }}</p>
      </div>
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
    </section>

    <section class="detail-grid">
      <div class="documents-panel panel">
        <div class="panel-title">
          <h2>课程资料</h2>
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
            </div>
            <div class="document-actions">
              <el-tag :type="statusType(document.status)">{{ statusText(document.status) }}</el-tag>
              <el-button
                v-if="document.status === 'needs_ocr'"
                size="small"
                :loading="ocrRunningId === document.id"
                @click="runOcr(document)"
              >
                OCR 入库
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <div class="qa-panel panel">
        <div class="panel-title">
          <h2>智能问答</h2>
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
            placeholder="例如：第三章的重点是什么？"
            @keyup.enter="ask"
          />
          <el-button type="primary" size="large" :loading="asking" @click="ask">
            <el-icon><Promotion /></el-icon>
            提问
          </el-button>
        </div>
      </div>
    </section>

    <section class="material-grid">
      <div class="panel material-panel">
        <div class="panel-title">
          <h2>复习提纲</h2>
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

      <div class="panel material-panel">
        <div class="panel-title">
          <h2>练习题</h2>
          <div class="inline-actions">
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
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import {
  askCourse,
  generateOutline,
  generatePractice,
  getCourse,
  ocrDocument,
  uploadDocument
} from "../api/client";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const course = ref(null);
const loading = ref(false);
const uploading = ref(false);
const asking = ref(false);
const generatingOutline = ref(false);
const generatingPractice = ref(false);
const question = ref("");
const messages = ref([]);
const outline = ref("");
const outlineSources = ref([]);
const practice = ref("");
const practiceSources = ref([]);
const practiceCount = ref(10);
const lastProvider = ref("ollama/qwen3-vl:30b");
const ocrRunningId = ref(null);

onMounted(loadCourse);

async function loadCourse() {
  loading.value = true;
  try {
    course.value = await getCourse(props.id);
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
    ElMessage.error(error.response?.data?.detail || "上传失败，请检查后端服务和文件格式");
  } finally {
    uploading.value = false;
  }
}

async function runOcr(document) {
  let value = "10";
  try {
    const result = await ElMessageBox.prompt(
      `这份 PDF 共 ${document.page_count} 页。建议先识别 5-10 页验证效果，单次最多 50 页。`,
      "扫描版 PDF OCR 入库",
      {
        inputValue: "10",
        inputPattern: /^([1-9]|[1-4][0-9]|50)$/,
        inputErrorMessage: "请输入 1-50 之间的页数",
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
    const result = await ocrDocument(props.id, document.id, {
      start_page: 1,
      max_pages: Number(value)
    });
    await loadCourse();
    if (result.status === "indexed") {
      ElMessage.success(result.error_message || "OCR 入库完成");
    } else {
      ElMessage.warning(result.error_message || "OCR 未生成可检索片段");
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "OCR 失败，请确认 Ollama 和 qwen3-vl:30b 已启动");
    await loadCourse();
  } finally {
    ocrRunningId.value = null;
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
    lastProvider.value = result.provider;
    messages.value.push({
      id: Date.now(),
      question: currentQuestion,
      answer: result.answer,
      sources: result.sources
    });
    await loadCourse();
  } finally {
    asking.value = false;
  }
}

async function makeOutline() {
  generatingOutline.value = true;
  try {
    const result = await generateOutline(props.id);
    lastProvider.value = result.provider;
    outline.value = result.content;
    outlineSources.value = result.sources;
  } finally {
    generatingOutline.value = false;
  }
}

async function makePractice() {
  generatingPractice.value = true;
  try {
    const result = await generatePractice(props.id, practiceCount.value);
    lastProvider.value = result.provider;
    practice.value = result.content;
    practiceSources.value = result.sources;
  } finally {
    generatingPractice.value = false;
  }
}

function statusText(status) {
  return {
    indexed: "已入库",
    processing: "解析中",
    needs_ocr: "需 OCR",
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
    ocr_processing: "warning",
    failed: "danger",
    empty: "info"
  }[status] || "info";
}

function sourceKey(source) {
  return `${source.document_id}-${source.page}-${source.chunk_index}`;
}
</script>
