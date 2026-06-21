import { computed, onBeforeUnmount, ref, unref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  cancelOcrJob,
  cancelProcessingJob,
  deleteDocument,
  getOcrJob,
  getProcessingJobs,
  ocrDocument,
  reindexCourse,
  reindexDocument,
  retryProcessingJob,
  uploadDocument,
  visionDocument
} from "../api/client";
import { getApiErrorMessage } from "../api/errors";

export function useCourseDocumentProcessing({ courseId, course, loadCourse }) {
  const uploading = ref(false);
  const ocrRunningId = ref(null);
  const visionRunningId = ref(null);
  const reindexingCourse = ref(false);
  const reindexingDocumentId = ref(null);
  const ocrJobs = ref({});
  const ocrPollTimer = ref(null);
  const documentPollTimer = ref(null);
  const jobs = ref([]);
  const jobsLoading = ref(false);
  const jobsDrawerOpen = ref(false);

  const hasProcessingDocuments = computed(() =>
    (course.value?.documents || []).some((document) => isDocumentProcessing(document))
  );

  onBeforeUnmount(() => {
    stopOcrPolling();
    stopDocumentPolling();
  });

  async function handleUpload(options) {
    uploading.value = true;
    try {
      const document = await uploadDocument(unref(courseId), options.file);
      await refreshCourseAndJobs();
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
      const job = await ocrDocument(unref(courseId), document.id, {
        start_page: Number(parts[0]),
        max_pages: Number(parts[1]),
        mode: parts[2] || "fast"
      });
      setOcrJob(job);
      startOcrPolling(job);
      await refreshCourseAndJobs();
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
      const latest = await cancelOcrJob(unref(courseId), document.id, job.id);
      setOcrJob(latest);
      stopOcrPolling();
      ocrRunningId.value = null;
      await refreshCourseAndJobs();
      ElMessage.success(latest.error_message || "OCR 已停止");
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "停止 OCR 失败"));
    }
  }

  async function runVision(document) {
    visionRunningId.value = document.id;
    try {
      const updated = await visionDocument(unref(courseId), document.id);
      await refreshCourseAndJobs();
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
      await deleteDocument(unref(courseId), document.id);
      ElMessage.success("资料已删除");
      await refreshCourseAndJobs();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "资料删除失败，请检查后端服务是否启动"));
    }
  }

  async function runCourseReindex() {
    reindexingCourse.value = true;
    try {
      const result = await reindexCourse(unref(courseId));
      ElMessage.success(`已重新索引 ${result.chunk_count || 0} 个片段`);
      await refreshCourseAndJobs();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "重新索引失败，请检查后端服务是否启动"));
    } finally {
      reindexingCourse.value = false;
    }
  }

  async function runDocumentReindex(document) {
    reindexingDocumentId.value = document.id;
    try {
      const result = await reindexDocument(unref(courseId), document.id);
      ElMessage.success(`资料已重新索引：${result.chunk_count || 0} 个片段`);
      await refreshCourseAndJobs();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "资料重新索引失败，请检查后端服务是否启动"));
    } finally {
      reindexingDocumentId.value = null;
    }
  }

  async function loadJobs() {
    jobsLoading.value = true;
    try {
      jobs.value = await getProcessingJobs(unref(courseId));
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "任务历史加载失败"));
    } finally {
      jobsLoading.value = false;
    }
  }

  async function openJobHistory() {
    jobsDrawerOpen.value = true;
    await loadJobs();
  }

  async function retryJob(job) {
    try {
      const result = await retryProcessingJob(unref(courseId), job.id);
      if (result.ocr_job) {
        setOcrJob(result.ocr_job);
        startOcrPolling(result.ocr_job);
      }
      ElMessage.success("任务已重新加入处理队列");
      await refreshCourseAndJobs();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "任务重试失败"));
    }
  }

  async function cancelJob(job) {
    try {
      await cancelProcessingJob(unref(courseId), job.id);
      ElMessage.success("任务已取消");
      await refreshCourseAndJobs();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "任务取消失败"));
    }
  }

  function syncDocumentPolling(documents) {
    if (documents.some((document) => isDocumentProcessing(document))) {
      startDocumentPolling();
    } else {
      stopDocumentPolling();
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

  function startDocumentPolling() {
    if (documentPollTimer.value) return;
    documentPollTimer.value = window.setInterval(() => {
      refreshCourseAndJobs();
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
      const latest = await getOcrJob(unref(courseId), job.document_id, job.id);
      setOcrJob(latest);
      if (["completed", "failed", "cancelled"].includes(latest.status)) {
        stopOcrPolling();
        ocrRunningId.value = null;
        await refreshCourseAndJobs();
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

  async function refreshCourseAndJobs() {
    await loadCourse();
    if (jobsDrawerOpen.value) {
      await loadJobs();
    }
  }

  return {
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
    loadJobs,
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
  };

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
}

export function statusText(status) {
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

export function statusType(status) {
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

export function isDocumentProcessing(document) {
  return ["uploaded", "queued", "parsing", "chunking", "indexing", "syncing_knowledge_points"].includes(document.status);
}

export function canRunOcr(document) {
  if (document.file_type !== "pdf") return false;
  if (document.status === "ocr_queued" || document.status === "ocr_processing") return false;
  return document.status === "needs_ocr" || document.error_message?.includes("OCR");
}

export function canRunVision(document) {
  if (!["png", "jpg", "jpeg", "webp"].includes(document.file_type)) return false;
  return document.status === "needs_vision" || document.status === "empty";
}

export function ocrProgress(job) {
  if (job.status === "completed") return 100;
  return Math.min(100, Math.round((job.processed_pages / Math.max(1, job.max_pages)) * 100));
}

export function ocrProgressStatus(job) {
  if (job.status === "failed") return "exception";
  if (job.status === "completed") return "success";
  return undefined;
}

export function ocrJobText(job) {
  if (job.status === "queued") return "OCR 任务排队中";
  if (job.status === "failed") return job.error_message || "OCR 失败";
  return job.error_message || `已完成 ${job.processed_pages}/${job.max_pages} 页`;
}
