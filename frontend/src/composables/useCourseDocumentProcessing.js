import { computed, onBeforeUnmount, ref, unref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  cancelOcrJob,
  cancelProcessingJob,
  deleteDocument,
  getOcrJob,
  getProcessingJobs,
  isRequestCanceled,
  ocrDocument,
  reindexCourse,
  reindexDocument,
  retryProcessingJob,
  uploadDocument,
  visionDocument
} from "../api/client";
import { getApiErrorMessage } from "../api/errors";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);
const TERMINAL_OCR_STATUSES = new Set(["completed", "failed", "cancelled"]);
const POLL_DELAY_MS = 2500;

export function useCourseDocumentProcessing({ courseId, course, loadCourse }) {
  const uploadCount = ref(0);
  const uploading = computed(() => uploadCount.value > 0);
  const ocrRunningId = ref(null);
  const visionRunningId = ref(null);
  const reindexingCourse = ref(false);
  const reindexingDocumentId = ref(null);
  const ocrJobs = ref({});
  const jobs = ref([]);
  const jobsLoading = ref(false);
  const jobsDrawerOpen = ref(false);
  const pollInFlight = ref(false);

  let pollTimer = null;
  let pollController = null;
  let actionController = new AbortController();
  let lifecycleVersion = 0;
  let disposed = false;

  const hasProcessingDocuments = computed(() =>
    (course.value?.documents || []).some((document) => isDocumentProcessing(document))
  );

  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", handleVisibilityChange);
  }

  onBeforeUnmount(dispose);

  async function handleUpload(options) {
    const requestCourseId = currentCourseId();
    uploadCount.value += 1;
    try {
      const uploaded = await uploadDocument(requestCourseId, options.file, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      await refreshCourseAndJobs();
      if (uploaded.status === "failed") {
        ElMessage.error(uploaded.error_message || "解析失败");
      } else if (uploaded.status === "needs_ocr") {
        ElMessage.warning(uploaded.error_message || "该 PDF 需要 OCR 后才能检索");
      } else if (uploaded.status === "empty") {
        ElMessage.warning(uploaded.error_message || "未解析到可检索文本");
      } else {
        ElMessage.info("资料已上传，后台正在解析入库");
        schedulePoll(0);
      }
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "上传失败，请检查后端服务和文件格式"));
      }
    } finally {
      uploadCount.value = Math.max(0, uploadCount.value - 1);
    }
  }

  async function runOcr(documentItem) {
    let value = nextOcrInput(documentItem);
    try {
      const result = await ElMessageBox.prompt(
        `这份 PDF 共 ${documentItem.page_count} 页。请输入“起始页,页数,模式”，例如 40,8,fast；需要逐字 OCR 时用 full。`,
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

    const requestCourseId = currentCourseId();
    ocrRunningId.value = documentItem.id;
    try {
      const parts = value.split(/[,，]/).map((item) => item.trim());
      const job = await ocrDocument(requestCourseId, documentItem.id, {
        start_page: Number(parts[0]),
        max_pages: Number(parts[1]),
        mode: parts[2] || "fast"
      }, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      setOcrJob(job);
      if (job.processing_job) mergeProcessingJobs([job.processing_job]);
      await refreshCourseAndJobs();
      schedulePoll(0);
      ElMessage.info("OCR 后台任务已启动，可继续使用页面");
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "OCR 启动失败，请确认后端服务正常"));
        await loadCourse({ silent: true, force: true });
      }
    } finally {
      if (isCurrentCourse(requestCourseId)) ocrRunningId.value = null;
    }
  }

  async function stopOcr(documentItem) {
    const job = activeOcrJob(documentItem.id);
    if (!job) return;
    const requestCourseId = currentCourseId();
    try {
      let latest;
      if (job._processingJob || (!job.processed_pages && job.processing_job_id)) {
        latest = await cancelProcessingJob(
          requestCourseId,
          job.processing_job_id || job.id,
          actionOptions()
        );
      } else {
        latest = await cancelOcrJob(requestCourseId, documentItem.id, job.id, actionOptions());
        setOcrJob(latest);
      }
      if (!isCurrentCourse(requestCourseId)) return;
      await refreshCourseAndJobs();
      ElMessage.info(latest.error_message || "OCR 已标记取消，后台会在下一检查点停止");
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "停止 OCR 失败"));
      }
    }
  }

  async function runVision(documentItem) {
    const requestCourseId = currentCourseId();
    visionRunningId.value = documentItem.id;
    try {
      const updated = await visionDocument(requestCourseId, documentItem.id, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      await refreshCourseAndJobs();
      if (updated.status === "indexed") {
        ElMessage.success(updated.error_message || "图片课件已识别入库");
      } else {
        ElMessage.warning(updated.error_message || "图片课件暂未识别成功");
      }
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "图片识别失败，请确认后端和视觉模型已启动"));
      }
    } finally {
      if (isCurrentCourse(requestCourseId)) visionRunningId.value = null;
    }
  }

  async function removeDocument(documentItem) {
    try {
      await ElMessageBox.confirm(
        `确定删除资料“${documentItem.original_filename}”吗？相关知识片段和处理任务也会删除。`,
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

    const requestCourseId = currentCourseId();
    try {
      await deleteDocument(requestCourseId, documentItem.id, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      ElMessage.success("资料已删除");
      delete ocrJobs.value[documentItem.id];
      await refreshCourseAndJobs();
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "资料删除失败，请检查后端服务"));
      }
    }
  }

  async function runCourseReindex() {
    const requestCourseId = currentCourseId();
    reindexingCourse.value = true;
    try {
      const result = await reindexCourse(requestCourseId, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      ElMessage.success(`已重新索引 ${result.chunk_count || 0} 个片段`);
      await refreshCourseAndJobs();
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "重新索引失败，请检查后端服务"));
      }
    } finally {
      if (isCurrentCourse(requestCourseId)) reindexingCourse.value = false;
    }
  }

  async function runDocumentReindex(documentItem) {
    const requestCourseId = currentCourseId();
    reindexingDocumentId.value = documentItem.id;
    try {
      const result = await reindexDocument(requestCourseId, documentItem.id, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      ElMessage.success(`资料已重新索引：${result.chunk_count || 0} 个片段`);
      await refreshCourseAndJobs();
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "资料重新索引失败，请检查后端服务"));
      }
    } finally {
      if (isCurrentCourse(requestCourseId)) reindexingDocumentId.value = null;
    }
  }

  async function loadJobs({ silent = false, signal } = {}) {
    const requestCourseId = currentCourseId();
    if (!silent) jobsLoading.value = true;
    try {
      const result = await getProcessingJobs(requestCourseId, signal ? { signal } : actionOptions());
      if (!isCurrentCourse(requestCourseId)) return [];
      jobs.value = result;
      await restoreOcrJobs(result, requestCourseId, signal);
      return result;
    } catch (error) {
      if (!silent && !isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "任务历史加载失败"));
      }
      return [];
    } finally {
      if (!silent && isCurrentCourse(requestCourseId)) jobsLoading.value = false;
    }
  }

  async function openJobHistory() {
    jobsDrawerOpen.value = true;
    await loadJobs();
  }

  async function retryJob(job) {
    const requestCourseId = currentCourseId();
    try {
      const result = await retryProcessingJob(requestCourseId, job.id, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      if (result.ocr_job) setOcrJob(result.ocr_job);
      if (result.processing_job) mergeProcessingJobs([result.processing_job]);
      ElMessage.success("任务已重新加入处理队列");
      await refreshCourseAndJobs();
      schedulePoll(0);
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "任务重试失败"));
      }
    }
  }

  async function cancelJob(job) {
    const requestCourseId = currentCourseId();
    try {
      const updated = await cancelProcessingJob(requestCourseId, job.id, actionOptions());
      if (!isCurrentCourse(requestCourseId)) return;
      ElMessage.info(updated.error_message || "任务已标记取消，后台会在下一检查点停止");
      await refreshCourseAndJobs();
    } catch (error) {
      if (!isRequestCanceled(error) && isCurrentCourse(requestCourseId)) {
        ElMessage.error(getApiErrorMessage(error, "任务取消失败"));
      }
    }
  }

  function syncDocumentPolling(documents) {
    const latestJobs = documents.map((item) => item.latest_job).filter(Boolean);
    if (latestJobs.length) mergeProcessingJobs(latestJobs);
    if (shouldKeepPolling()) schedulePoll();
    else clearPollTimer();
  }

  function mergeProcessingJobs(nextJobs) {
    const byId = new Map(jobs.value.map((job) => [job.id, job]));
    for (const job of nextJobs) byId.set(job.id, { ...byId.get(job.id), ...job });
    jobs.value = [...byId.values()].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  }

  function setOcrJob(job, processingJob = null) {
    if (!job?.document_id) return;
    ocrJobs.value = {
      ...ocrJobs.value,
      [job.document_id]: {
        ...job,
        processing_job_id: processingJob?.id || job.processing_job_id
      }
    };
  }

  async function restoreOcrJobs(processingJobs, requestCourseId, signal) {
    const active = processingJobs.filter(
      (job) => job.job_type === "ocr" && ACTIVE_JOB_STATUSES.has(job.status) && job.ocr_job_id && job.document_id
    );
    if (!active.length) return;
    const results = await Promise.allSettled(
      active.map(async (processingJob) => ({
        processingJob,
        ocrJob: await getOcrJob(
          requestCourseId,
          processingJob.document_id,
          processingJob.ocr_job_id,
          signal ? { signal } : actionOptions()
        )
      }))
    );
    if (!isCurrentCourse(requestCourseId)) return;
    for (const result of results) {
      if (result.status === "fulfilled") {
        setOcrJob(result.value.ocrJob, result.value.processingJob);
      }
    }
  }

  function schedulePoll(delay = POLL_DELAY_MS) {
    if (disposed || isPageHidden() || pollTimer || pollInFlight.value || !shouldKeepPolling()) return;
    const version = lifecycleVersion;
    pollTimer = window.setTimeout(() => {
      pollTimer = null;
      void runPoll(version);
    }, delay);
  }

  async function runPoll(version) {
    if (disposed || version !== lifecycleVersion || isPageHidden() || pollInFlight.value) return;
    const requestCourseId = currentCourseId();
    pollInFlight.value = true;
    pollController = new AbortController();
    try {
      await loadCourse({
        silent: true,
        force: true,
        signal: pollController.signal,
        expectedCourseId: requestCourseId
      });
      if (version !== lifecycleVersion || !isCurrentCourse(requestCourseId)) return;
      await loadJobs({ silent: true, signal: pollController.signal });
    } finally {
      if (version === lifecycleVersion) {
        pollInFlight.value = false;
        pollController = null;
        if (shouldKeepPolling()) schedulePoll();
      }
    }
  }

  async function refreshCourseAndJobs() {
    const requestCourseId = currentCourseId();
    await loadCourse({ silent: true, force: true, expectedCourseId: requestCourseId });
    if (!isCurrentCourse(requestCourseId)) return;
    await loadJobs({ silent: true });
    if (shouldKeepPolling()) schedulePoll();
  }

  function resetProcessingState() {
    lifecycleVersion += 1;
    clearPollTimer();
    pollController?.abort();
    pollController = null;
    pollInFlight.value = false;
    actionController.abort();
    actionController = new AbortController();
    uploadCount.value = 0;
    ocrRunningId.value = null;
    visionRunningId.value = null;
    reindexingCourse.value = false;
    reindexingDocumentId.value = null;
    ocrJobs.value = {};
    jobs.value = [];
    jobsLoading.value = false;
    jobsDrawerOpen.value = false;
  }

  function handleVisibilityChange() {
    if (isPageHidden()) {
      clearPollTimer();
      pollController?.abort();
      return;
    }
    if (shouldKeepPolling()) schedulePoll(0);
  }

  function clearPollTimer() {
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function shouldKeepPolling() {
    if (hasProcessingDocuments.value) return true;
    if (jobs.value.some((job) => ACTIVE_JOB_STATUSES.has(job.status))) return true;
    return Object.values(ocrJobs.value).some((job) => !TERMINAL_OCR_STATUSES.has(job.status));
  }

  function activeOcrJob(documentId) {
    const detailed = ocrJobs.value[documentId];
    if (detailed && !TERMINAL_OCR_STATUSES.has(detailed.status)) return detailed;
    const processingJob = jobs.value.find(
      (job) => job.document_id === documentId && job.job_type === "ocr" && ACTIVE_JOB_STATUSES.has(job.status)
    );
    return processingJob ? { ...processingJob, _processingJob: true, processing_job_id: processingJob.id } : null;
  }

  function nextOcrInput(documentItem) {
    const job = activeOcrJob(documentItem.id);
    const start = job?.current_page ? Math.min(documentItem.page_count, job.current_page + 1) : 1;
    return `${start},8,fast`;
  }

  function currentCourseId() {
    return unref(courseId);
  }

  function isCurrentCourse(requestCourseId) {
    return String(currentCourseId()) === String(requestCourseId);
  }

  function actionOptions() {
    return { signal: actionController.signal };
  }

  function isPageHidden() {
    return typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  function dispose() {
    disposed = true;
    resetProcessingState();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
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
    pollInFlight,
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
  };
}

export function statusText(status) {
  return {
    uploaded: "已上传，等待解析",
    queued: "已上传，等待解析",
    parsing: "正在解析文本",
    chunking: "正在切分知识片段",
    indexing: "正在写入检索索引",
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

export function isDocumentProcessing(documentItem) {
  return [
    "uploaded",
    "queued",
    "parsing",
    "chunking",
    "indexing",
    "syncing_knowledge_points",
    "ocr_queued",
    "ocr_processing",
    "vision_processing"
  ].includes(documentItem.status);
}

export function canRunOcr(documentItem) {
  if (documentItem.file_type !== "pdf") return false;
  if (["ocr_queued", "ocr_processing"].includes(documentItem.status)) return false;
  return documentItem.status === "needs_ocr" || documentItem.error_message?.includes("OCR");
}

export function canRunVision(documentItem) {
  if (!["png", "jpg", "jpeg", "webp"].includes(documentItem.file_type)) return false;
  return documentItem.status === "needs_vision" || documentItem.status === "empty";
}

export function ocrProgress(job) {
  if (job.status === "completed") return 100;
  if (Number.isFinite(job.progress)) return Math.min(100, Math.max(0, Math.round(job.progress)));
  return Math.min(100, Math.round(((job.processed_pages || 0) / Math.max(1, job.max_pages || 1)) * 100));
}

export function ocrProgressStatus(job) {
  if (job.status === "failed") return "exception";
  if (job.status === "completed") return "success";
  return undefined;
}

export function ocrJobText(job) {
  if (job.status === "queued") return "OCR 任务排队中";
  if (job.status === "failed") return job.error_message || "OCR 失败";
  if (Number.isFinite(job.progress)) return job.error_message || `${job.stage || "OCR 处理中"} · ${job.progress}%`;
  return job.error_message || `已完成 ${job.processed_pages || 0}/${job.max_pages || 0} 页`;
}
