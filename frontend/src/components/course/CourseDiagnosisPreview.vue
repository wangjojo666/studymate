<template>
  <div class="diagnosis-preview-grid">
    <div class="panel">
      <div class="panel-title">
        <div>
          <h2>总体掌握度</h2>
          <span>根据提问、练习和错题动态更新</span>
        </div>
      </div>
      <div class="mastery-ring compact" :style="ringStyle">
        <span>{{ learningProfile?.summary.overall_mastery || 0 }}%</span>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">
        <div>
          <h2>薄弱知识点</h2>
          <span>优先进入专项训练</span>
        </div>
        <el-button text @click="$emit('openFullDiagnosis')">完整诊断</el-button>
      </div>
      <div class="weak-list">
        <div v-for="point in weakPoints" :key="point.id" class="weak-item">
          <div>
            <strong>{{ point.name }}</strong>
            <span>{{ point.mastery_score }}% · {{ point.level_label }} · 错题 {{ point.wrong_count }} 次</span>
            <p>{{ point.mastery_formula || point.explanation }}</p>
            <small>来源：{{ point.source_page ? `P${point.source_page}` : "暂无页码" }} · {{ point.evidence || "暂无证据片段" }}</small>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  learningProfile: { type: Object, default: null },
  weakPoints: { type: Array, default: () => [] },
  ringStyle: { type: Object, default: () => ({}) }
});

defineEmits(["openFullDiagnosis"]);
</script>
