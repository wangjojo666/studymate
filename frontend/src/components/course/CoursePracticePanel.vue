<template>
  <div class="panel material-panel">
    <div class="panel-title">
      <div>
        <h2>专项练习</h2>
        <span>按难度和知识点生成基础题、提高题、考试题或易错题</span>
      </div>
      <div class="inline-actions">
        <el-select :model-value="difficulty" size="small" class="practice-select" @update:model-value="$emit('update:difficulty', $event)">
          <el-option label="基础题" value="basic" />
          <el-option label="提高题" value="advanced" />
          <el-option label="考试题" value="exam" />
          <el-option label="易错题" value="mistake" />
        </el-select>
        <el-select
          :model-value="knowledgePointId"
          size="small"
          class="practice-select"
          clearable
          filterable
          placeholder="知识点"
          @update:model-value="$emit('update:knowledgePointId', $event)"
        >
          <el-option
            v-for="point in knowledgePointOptions"
            :key="point.id"
            :label="point.name"
            :value="point.id"
          />
        </el-select>
        <el-input-number :model-value="count" :min="1" :max="30" size="small" @update:model-value="$emit('update:count', $event)" />
        <el-button :loading="generating" @click="$emit('generate')">
          <el-icon><EditPen /></el-icon>
          生成
        </el-button>
      </div>
    </div>
    <div v-if="items.length" class="practice-card-list">
      <div v-for="item in items" :key="practiceItemKey(item)" class="practice-card">
        <div class="practice-card-head">
          <el-tag>{{ item.question_type || item.type || "练习题" }}</el-tag>
          <span>{{ (item.knowledge_points || []).join(" / ") || "核心概念" }}</span>
        </div>
        <p class="practice-question">{{ item.question }}</p>
        <ol v-if="item.options?.length" class="practice-options">
          <li v-for="option in item.options" :key="option">{{ option }}</li>
        </ol>
        <div v-if="practiceAttemptState[practiceItemKey(item)]?.showAnswer" class="practice-answer">
          <strong>参考答案</strong>
          <p>{{ item.reference_answer || item.answer }}</p>
          <strong>解析</strong>
          <p>{{ item.explanation }}</p>
        </div>
        <el-input
          :model-value="ensurePracticeState(item).errorReason"
          type="textarea"
          :rows="2"
          placeholder="答错时填写错因，例如概念混淆、公式记忆错误、步骤跳跃"
          @update:model-value="ensurePracticeState(item).errorReason = $event"
        />
        <div class="practice-actions">
          <el-button size="small" @click="togglePracticeAnswer(item)">
            {{ practiceAttemptState[practiceItemKey(item)]?.showAnswer ? "收起答案" : "查看答案" }}
          </el-button>
          <el-button
            size="small"
            type="success"
            :loading="practiceAttemptState[practiceItemKey(item)]?.submitting === 'correct'"
            @click="submitPracticeResult(item, true)"
          >
            标记答对
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :loading="practiceAttemptState[practiceItemKey(item)]?.submitting === 'wrong'"
            @click="submitPracticeResult(item, false)"
          >
            标记答错
          </el-button>
          <span v-if="practiceAttemptState[practiceItemKey(item)]?.result" class="practice-result">
            {{ practiceAttemptState[practiceItemKey(item)].result }}
          </span>
        </div>
        <div v-if="item.sources?.length" class="source-strip">
          <button v-for="source in item.sources" :key="sourceKey(source)" type="button" @click="$emit('openSource', source)">
            《{{ source.document_name }}》P{{ source.page }}
          </button>
        </div>
      </div>
    </div>
    <template v-else>
      <pre>{{ content || "待生成" }}</pre>
      <div v-if="sources.length" class="source-strip">
        <button v-for="source in sources" :key="sourceKey(source)" type="button" @click="$emit('openSource', source)">
          《{{ source.document_name }}》P{{ source.page }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { practiceItemKey } from "../../composables/usePracticeAttempts";
import { sourceKey } from "../../composables/useSourceDrawer";

defineProps({
  count: { type: Number, default: 10 },
  difficulty: { type: String, default: "basic" },
  knowledgePointId: { type: [Number, String], default: null },
  knowledgePointOptions: { type: Array, default: () => [] },
  generating: { type: Boolean, default: false },
  content: { type: String, default: "" },
  sources: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
  practiceAttemptState: { type: Object, required: true },
  ensurePracticeState: { type: Function, required: true },
  togglePracticeAnswer: { type: Function, required: true },
  submitPracticeResult: { type: Function, required: true }
});

defineEmits([
  "generate",
  "openSource",
  "update:count",
  "update:difficulty",
  "update:knowledgePointId"
]);
</script>
