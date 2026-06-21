<template>
  <div class="panel">
    <div class="panel-title">
      <div>
        <h2>课程资料</h2>
        <span>支持文档、扫描版 PDF 和公式/流程图/代码/电路图片入库</span>
      </div>
      <div class="provider-tags">
        <el-tag type="info">{{ props.course?.document_count || 0 }} 份</el-tag>
        <el-tag effect="plain">Embedding：{{ props.course?.embedding_provider || "未配置" }}</el-tag>
        <el-button size="small" @click="$emit('openJobHistory')">任务历史</el-button>
        <el-button
          size="small"
          :loading="props.reindexingCourse"
          :disabled="props.hasProcessingDocuments"
          @click="props.runCourseReindex"
        >
          <el-icon><Refresh /></el-icon>
          重新索引
        </el-button>
      </div>
    </div>
    <el-empty v-if="!props.course?.documents?.length" description="暂无资料" />
    <div v-else class="document-list">
      <div v-for="document in props.course.documents" :key="document.id" class="document-item">
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
          <small v-if="document.latest_job" class="job-line">
            最近任务：{{ jobTypeText(document.latest_job.job_type) }} ·
            {{ jobStatusText(document.latest_job.status) }} ·
            {{ document.latest_job.progress }}%
            <template v-if="document.latest_job.error_message"> · {{ document.latest_job.error_message }}</template>
          </small>
          <div v-if="props.activeOcrJob(document.id)" class="ocr-progress">
            <el-progress
              :percentage="props.ocrProgress(props.activeOcrJob(document.id))"
              :status="props.ocrProgressStatus(props.activeOcrJob(document.id))"
            />
            <small>{{ props.ocrJobText(props.activeOcrJob(document.id)) }}</small>
          </div>
          <div v-else-if="props.isDocumentProcessing(document)" class="ocr-progress">
            <el-progress :percentage="document.processing_progress || 0" />
            <small>{{ props.statusText(document.status) }}</small>
          </div>
        </div>
        <div class="document-actions">
          <el-tag :type="props.statusType(document.status)">{{ props.statusText(document.status) }}</el-tag>
          <el-button
            v-if="canRetry(document.latest_job)"
            size="small"
            type="warning"
            plain
            @click="props.retryJob(document.latest_job)"
          >
            重试任务
          </el-button>
          <el-button
            v-if="props.canRunOcr(document)"
            size="small"
            :loading="props.ocrRunningId === document.id || document.status === 'ocr_queued' || document.status === 'ocr_processing'"
            @click="props.runOcr(document)"
          >
            OCR 入库
          </el-button>
          <el-button
            v-if="props.canRunVision(document)"
            size="small"
            :loading="props.visionRunningId === document.id || document.status === 'vision_processing'"
            @click="props.runVision(document)"
          >
            识别入库
          </el-button>
          <el-button
            size="small"
            :loading="props.reindexingDocumentId === document.id"
            :disabled="Boolean(props.activeOcrJob(document.id)) || props.isDocumentProcessing(document) || !document.chunk_count"
            @click="props.runDocumentReindex(document)"
          >
            <el-icon><Refresh /></el-icon>
            重新索引
          </el-button>
          <el-button
            v-if="props.activeOcrJob(document.id)"
            size="small"
            type="danger"
            plain
            @click="props.stopOcr(document)"
          >
            停止
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="Boolean(props.activeOcrJob(document.id)) || props.isDocumentProcessing(document)"
            @click="props.removeDocument(document)"
          >
            删除
          </el-button>
        </div>
      </div>
    </div>

    <el-drawer
      :model-value="props.jobHistoryOpen"
      title="资料处理任务"
      size="520px"
      @update:model-value="$emit('update:jobHistoryOpen', $event)"
      @open="$emit('openJobHistory')"
    >
      <div v-loading="props.jobsLoading" class="job-history">
        <el-empty v-if="!props.jobs.length" description="暂无任务记录" />
        <template v-else>
          <div v-for="job in props.jobs" :key="job.id" class="job-history-item">
            <div>
              <strong>{{ jobTypeText(job.job_type) }}</strong>
              <span>{{ job.document?.original_filename || "课程级任务" }}</span>
            </div>
            <el-tag :type="jobTagType(job.status)">{{ jobStatusText(job.status) }}</el-tag>
            <el-progress :percentage="job.progress || 0" :status="job.status === 'failed' ? 'exception' : undefined" />
            <small>{{ job.stage }}{{ job.error_message ? ` · ${job.error_message}` : "" }}</small>
            <div class="inline-actions">
              <el-button v-if="canRetry(job)" size="small" type="warning" plain @click="props.retryJob(job)">
                重试
              </el-button>
              <el-button v-if="canCancel(job)" size="small" type="danger" plain @click="props.cancelJob(job)">
                取消
              </el-button>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
const props = defineProps({
  course: { type: Object, default: null },
  hasProcessingDocuments: { type: Boolean, default: false },
  reindexingCourse: { type: Boolean, default: false },
  reindexingDocumentId: { type: [Number, String], default: null },
  ocrRunningId: { type: [Number, String], default: null },
  visionRunningId: { type: [Number, String], default: null },
  jobs: { type: Array, default: () => [] },
  jobsLoading: { type: Boolean, default: false },
  jobHistoryOpen: { type: Boolean, default: false },
  runCourseReindex: { type: Function, required: true },
  runDocumentReindex: { type: Function, required: true },
  runOcr: { type: Function, required: true },
  stopOcr: { type: Function, required: true },
  runVision: { type: Function, required: true },
  removeDocument: { type: Function, required: true },
  retryJob: { type: Function, required: true },
  cancelJob: { type: Function, required: true },
  activeOcrJob: { type: Function, required: true },
  ocrProgress: { type: Function, required: true },
  ocrProgressStatus: { type: Function, required: true },
  ocrJobText: { type: Function, required: true },
  statusText: { type: Function, required: true },
  statusType: { type: Function, required: true },
  isDocumentProcessing: { type: Function, required: true },
  canRunOcr: { type: Function, required: true },
  canRunVision: { type: Function, required: true }
});

defineEmits(["openJobHistory", "update:jobHistoryOpen"]);

function canRetry(job) {
  return job && ["failed", "cancelled"].includes(job.status);
}

function canCancel(job) {
  return job && ["queued", "running"].includes(job.status);
}

function jobTypeText(type) {
  return {
    document_parse: "资料解析",
    ocr: "OCR 入库",
    reindex: "重新索引",
    knowledge_sync: "知识点同步"
  }[type] || type;
}

function jobStatusText(status) {
  return {
    queued: "排队中",
    running: "处理中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消"
  }[status] || status;
}

function jobTagType(status) {
  return {
    queued: "info",
    running: "warning",
    completed: "success",
    failed: "danger",
    cancelled: "info"
  }[status] || "info";
}
</script>
