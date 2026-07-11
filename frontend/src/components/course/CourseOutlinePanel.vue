<template>
  <div class="panel material-panel">
    <div class="panel-title">
      <div>
        <h2>复习提纲</h2>
        <span>自动整理核心概念、公式、易错点和可能考法</span>
      </div>
      <el-button :loading="generating" @click="$emit('generate')">
        <el-icon><Memo /></el-icon>
        生成
      </el-button>
    </div>
    <pre>{{ outline || "待生成" }}</pre>
    <div v-if="sources.length" class="source-strip">
      <button v-for="source in sources" :key="sourceKey(source)" type="button" @click="$emit('openSource', source)">
        《{{ source.document_name }}》P{{ source.page }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { sourceKey } from "../../composables/useSourceDrawer";

defineProps({
  outline: { type: String, default: "" },
  sources: { type: Array, default: () => [] },
  generating: { type: Boolean, default: false }
});

defineEmits(["generate", "openSource"]);
</script>
