<template>
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
            <button
              v-for="source in message.sources"
              :key="sourceKey(source)"
              type="button"
              @click="$emit('openSource', source, message.retrieval_provider)"
            >
              《{{ source.document_name }}》P{{ source.page }} · score {{ formatScore(source.score) }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="ask-bar">
      <el-input
        :model-value="question"
        size="large"
        placeholder="例如：第六章空间解析几何的重点是什么？"
        @update:model-value="$emit('update:question', $event)"
        @keyup.enter="$emit('ask')"
      />
      <el-button type="primary" size="large" :loading="asking" @click="$emit('ask')">
        <el-icon><Promotion /></el-icon>
        提问
      </el-button>
      <small v-if="hasProcessingDocuments" class="ask-hint">资料入库后效果更好</small>
    </div>
  </div>
</template>

<script setup>
import { formatScore, sourceKey } from "../../composables/useSourceDrawer";

defineProps({
  messages: { type: Array, default: () => [] },
  question: { type: String, default: "" },
  asking: { type: Boolean, default: false },
  hasProcessingDocuments: { type: Boolean, default: false },
  lastAnswerStatus: { type: String, default: "未调用" },
  lastConfidence: { type: String, default: "low" },
  lastRetrievalProvider: { type: String, default: "未调用" },
  lastLlmProvider: { type: String, default: "未调用" }
});

defineEmits(["ask", "openSource", "update:question"]);

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
</script>
