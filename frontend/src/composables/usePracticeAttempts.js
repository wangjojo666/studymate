import { ref, unref } from "vue";
import { ElMessage } from "element-plus";

import { submitPracticeAttempt } from "../api/client";
import { getApiErrorMessage } from "../api/errors";

export function usePracticeAttempts({
  courseId,
  practiceDifficulty,
  practiceKnowledgePointId,
  knowledgePointOptions,
  loadCourse
}) {
  const practiceAttemptState = ref({});

  function resetPracticeState(items) {
    practiceAttemptState.value = Object.fromEntries(
      items.map((item) => [
        practiceItemKey(item),
        { showAnswer: false, errorReason: "", submitting: "", result: "" }
      ])
    );
  }

  function togglePracticeAnswer(item) {
    const state = ensurePracticeState(item);
    state.showAnswer = !state.showAnswer;
  }

  async function submitPracticeResult(item, isCorrect) {
    const key = practiceItemKey(item);
    const state = ensurePracticeState(item);
    state.submitting = isCorrect ? "correct" : "wrong";
    try {
      await submitPracticeAttempt(unref(courseId), {
        knowledge_point_id: resolvePracticeKnowledgePointId(item),
        question_text: item.question,
        user_answer: isCorrect ? (item.reference_answer || item.answer || "已掌握") : "答错",
        correct_answer: item.reference_answer || item.answer || "",
        is_correct: isCorrect,
        error_reason: isCorrect ? "" : (state.errorReason || "未标注错因"),
        difficulty: unref(practiceDifficulty)
      });
      state.result = isCorrect ? "已标记答对" : "已记录错因";
      practiceAttemptState.value = { ...practiceAttemptState.value, [key]: state };
      await loadCourse();
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, "练习记录提交失败"));
    } finally {
      state.submitting = "";
    }
  }

  function ensurePracticeState(item) {
    const key = practiceItemKey(item);
    if (!practiceAttemptState.value[key]) {
      practiceAttemptState.value[key] = { showAnswer: false, errorReason: "", submitting: "", result: "" };
    }
    return practiceAttemptState.value[key];
  }

  function resolvePracticeKnowledgePointId(item) {
    if (unref(practiceKnowledgePointId)) return unref(practiceKnowledgePointId);
    const names = item.knowledge_points || [];
    const matched = (unref(knowledgePointOptions) || []).find((point) =>
      names.some((name) => point.name === name || point.name.includes(name) || name.includes(point.name))
    );
    return matched?.id || null;
  }

  return {
    practiceAttemptState,
    resetPracticeState,
    togglePracticeAnswer,
    submitPracticeResult,
    ensurePracticeState
  };
}

export function practiceItemKey(item) {
  return item.id || `${item.question_type || item.type}-${item.question}`;
}
