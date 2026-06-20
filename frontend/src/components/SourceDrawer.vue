<template>
  <el-drawer
    :model-value="modelValue"
    title="来源片段"
    size="min(560px, 92vw)"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-if="source" class="source-drawer-body">
      <div class="source-drawer-title">
        <strong>{{ source.document_name || "未知资料" }}</strong>
        <span>P{{ source.page || "-" }} · chunk {{ source.chunk_index ?? "-" }}</span>
      </div>
      <div class="source-drawer-tags">
        <el-tag v-if="source.score !== null && source.score !== undefined" type="info">
          score {{ formatScore(source.score) }}
        </el-tag>
        <el-tag v-if="source.retrieval_provider" effect="plain">
          {{ source.retrieval_provider }}
        </el-tag>
      </div>

      <el-skeleton v-if="loading" :rows="8" animated />
      <pre v-else>{{ source.content || source.preview || "暂无可展示片段。" }}</pre>

      <div class="source-drawer-actions">
        <el-button type="primary" @click="$emit('copy')">
          <el-icon><CopyDocument /></el-icon>
          复制引用
        </el-button>
      </div>
    </div>
    <el-empty v-else description="未选择来源" />
  </el-drawer>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, required: true },
  source: { type: Object, default: null },
  loading: { type: Boolean, default: false }
});

defineEmits(["update:modelValue", "copy"]);

function formatScore(score) {
  const value = Number(score);
  return Number.isFinite(value) ? value.toFixed(3) : "-";
}
</script>

<style scoped>
.source-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 100%;
}

.source-drawer-title strong,
.source-drawer-title span {
  display: block;
}

.source-drawer-title span {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.source-drawer-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-drawer-body pre {
  min-height: 300px;
  max-height: calc(100vh - 260px);
  overflow: auto;
  padding: 12px;
  border: 1px solid #e8eef6;
  border-radius: 8px;
  background: #f8fafc;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.source-drawer-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
