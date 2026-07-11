import { onBeforeUnmount, ref, unref } from "vue";
import { ElMessage } from "element-plus";

import { getSourceChunk, isRequestCanceled } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

export function useSourceDrawer({ courseId, lastRetrievalProvider }) {
  const sourceDrawerOpen = ref(false);
  const activeSource = ref(null);
  const sourceLoading = ref(false);
  let requestController = null;
  let requestVersion = 0;

  onBeforeUnmount(resetSourceDrawer);

  async function openSource(source, retrievalProvider = "") {
    requestController?.abort();
    requestController = new AbortController();
    const version = ++requestVersion;
    const requestCourseId = String(unref(courseId));
    const provider = source.retrieval_provider || retrievalProvider || unref(lastRetrievalProvider) || "";
    activeSource.value = {
      ...source,
      retrieval_provider: provider,
      content: source.content || ""
    };
    sourceDrawerOpen.value = true;
    if (!source.chunk_id) {
      sourceLoading.value = false;
      return;
    }
    sourceLoading.value = true;
    try {
      const detail = await getSourceChunk(unref(courseId), source.chunk_id, {
        score: source.score,
        retrieval_provider: provider
      }, { signal: requestController.signal });
      if (version !== requestVersion || requestCourseId !== String(unref(courseId))) return;
      activeSource.value = {
        ...source,
        ...detail,
        retrieval_provider: detail.retrieval_provider || provider
      };
    } catch (error) {
      if (!isRequestCanceled(error) && version === requestVersion) {
        ElMessage.error(getApiErrorMessage(error, "来源片段加载失败"));
      }
    } finally {
      if (version === requestVersion) sourceLoading.value = false;
    }
  }

  async function copySourceReference() {
    if (!activeSource.value) return;
    const source = activeSource.value;
    const reference = [
      `《${source.document_name || "未知资料"}》P${source.page || "-"} chunk ${source.chunk_index ?? "-"}`,
      source.score !== null && source.score !== undefined ? `score ${formatScore(source.score)}` : "",
      source.retrieval_provider ? `provider ${source.retrieval_provider}` : "",
      source.content || source.preview || ""
    ].filter(Boolean).join("\n");
    try {
      await window.navigator.clipboard.writeText(reference);
      ElMessage.success("引用已复制");
    } catch {
      ElMessage.warning("浏览器暂不允许复制，请手动选中文本");
    }
  }

  function resetSourceDrawer() {
    requestVersion += 1;
    requestController?.abort();
    requestController = null;
    sourceDrawerOpen.value = false;
    activeSource.value = null;
    sourceLoading.value = false;
  }

  return {
    sourceDrawerOpen,
    activeSource,
    sourceLoading,
    openSource,
    copySourceReference,
    resetSourceDrawer
  };
}

export function sourceKey(source) {
  return `${source.chunk_id || source.document_id}-${source.page}-${source.chunk_index}`;
}

export function formatScore(score) {
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(3) : "-";
}
