import { ref, unref } from "vue";
import { ElMessage } from "element-plus";

import { getSourceChunk } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

export function useSourceDrawer({ courseId, lastRetrievalProvider }) {
  const sourceDrawerOpen = ref(false);
  const activeSource = ref(null);
  const sourceLoading = ref(false);

  async function openSource(source, retrievalProvider = "") {
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
      });
      activeSource.value = {
        ...source,
        ...detail,
        retrieval_provider: detail.retrieval_provider || provider
      };
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "来源片段加载失败"));
    } finally {
      sourceLoading.value = false;
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

  return {
    sourceDrawerOpen,
    activeSource,
    sourceLoading,
    openSource,
    copySourceReference
  };
}

export function sourceKey(source) {
  return `${source.chunk_id || source.document_id}-${source.page}-${source.chunk_index}`;
}

export function formatScore(score) {
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(3) : "-";
}
