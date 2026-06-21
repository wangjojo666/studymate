<template>
  <div class="panel cpp-panel">
    <div class="panel-title">
      <div>
        <h2>C++ 课程专项能力</h2>
        <span>解释代码、识别继承/虚函数/友元/运算符重载等考点，并诊断用户代码</span>
      </div>
      <div class="inline-actions">
        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          accept=".cpp,.cc,.cxx,.h,.hpp,.txt"
          :on-change="readFile"
        >
          <el-button>
            <el-icon><FolderOpened /></el-icon>
            读取代码文件
          </el-button>
        </el-upload>
        <el-button type="primary" :loading="analyzing" @click="$emit('analyze')">
          <el-icon><Cpu /></el-icon>
          分析代码
        </el-button>
      </div>
    </div>

    <div class="cpp-form-grid">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="代码题/题干">
          <el-input
            :model-value="form.problem_text"
            type="textarea"
            :rows="3"
            placeholder="例如：分析下面程序输出，说明虚函数如何实现运行时多态。"
            @update:model-value="form.problem_text = $event"
          />
        </el-form-item>
        <el-form-item label="题目代码或参考代码">
          <el-input
            :model-value="form.code_text"
            type="textarea"
            :rows="12"
            placeholder="粘贴 C++ 题目代码、参考代码或截图识别后的代码文本"
            @update:model-value="form.code_text = $event"
          />
        </el-form-item>
        <el-form-item label="用户代码">
          <el-input
            :model-value="form.user_code"
            type="textarea"
            :rows="8"
            placeholder="可选：粘贴自己的答案，系统会判断可能的错误和遗漏考点"
            @update:model-value="form.user_code = $event"
          />
        </el-form-item>
        <el-form-item label="样例输入">
          <el-input
            :model-value="form.sample_input"
            type="textarea"
            :rows="3"
            placeholder="可选：提供 stdin 样例，编译通过后会限时运行"
            @update:model-value="form.sample_input = $event"
          />
        </el-form-item>
      </el-form>

      <div class="cpp-result">
        <div v-if="!analysis" class="empty-chat cpp-empty">
          <el-icon><Cpu /></el-icon>
          <span>上传或粘贴 C++ 代码后开始分析</span>
        </div>
        <template v-else>
          <div class="cpp-summary">
            <strong>{{ analysis.summary }}</strong>
            <div class="cpp-summary-tags">
              <el-tag :type="analysis.sandbox_level === 'disabled' ? 'warning' : 'success'">
                {{ sandboxText(analysis.sandbox_level) }}
              </el-tag>
              <el-tag>{{ analysis.provider }}</el-tag>
            </div>
          </div>
          <div class="cpp-section">
            <h3>编译诊断</h3>
            <el-alert
              v-if="analysis.sandbox_level === 'disabled'"
              title="当前处于安全演示模式，未执行本地编译运行。"
              type="warning"
              show-icon
              :closable="false"
              class="cpp-safe-alert"
            />
            <div class="cpp-issue-list">
              <div class="cpp-issue">
                <el-tag :type="compileTagType(analysis)">
                  {{ compileStatusText(analysis) }}
                </el-tag>
                <div>
                  <strong>{{ compileCommandText(analysis) }}</strong>
                  <span>{{ analysis.compile_result?.stderr || "无编译错误输出" }}</span>
                </div>
              </div>
              <div v-if="analysis.run_result?.executed" class="cpp-issue">
                <el-tag :type="analysis.run_result?.success ? 'success' : 'danger'">
                  {{ analysis.run_result?.timeout ? "运行超时" : analysis.run_result?.success ? "运行成功" : "运行失败" }}
                </el-tag>
                <div>
                  <strong>样例运行输出</strong>
                  <span>{{ analysis.run_result?.stdout || analysis.run_result?.stderr || "程序无输出" }}</span>
                </div>
              </div>
              <div v-else class="cpp-issue">
                <el-tag type="info">未运行</el-tag>
                <div>
                  <strong>样例运行</strong>
                  <span>{{ analysis.sandbox_level === 'disabled' ? "安全模式下未执行" : "未提供样例输入或编译未通过" }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="cpp-section">
            <h3>考点识别</h3>
            <div class="cpp-point-list">
              <div v-for="point in analysis.exam_points" :key="point.name" class="cpp-point">
                <strong>{{ point.name }}</strong>
                <span>{{ point.exam_hint }}</span>
                <small>{{ point.evidence }}</small>
              </div>
            </div>
          </div>
          <div class="cpp-section">
            <h3>代码解释</h3>
            <pre>{{ analysis.explanation }}</pre>
          </div>
          <div class="cpp-section">
            <h3>错误诊断</h3>
            <div class="cpp-issue-list">
              <div v-for="issue in analysis.error_diagnosis" :key="`${issue.level}-${issue.title}`" class="cpp-issue">
                <el-tag :type="issueTagType(issue.level)">{{ issue.level }}</el-tag>
                <div>
                  <strong>{{ issue.title }}</strong>
                  <span>{{ issue.detail }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="cpp-section">
            <h3>同类练习题</h3>
            <div class="cpp-exercise-list">
              <div v-for="exercise in analysis.similar_exercises" :key="exercise.title" class="cpp-exercise">
                <strong>{{ exercise.title }}</strong>
                <span>{{ exercise.prompt }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  form: { type: Object, required: true },
  analysis: { type: Object, default: null },
  analyzing: { type: Boolean, default: false }
});

const emit = defineEmits(["analyze", "readFile"]);

function readFile(uploadFile) {
  emit("readFile", uploadFile);
}

function issueTagType(level) {
  return {
    ok: "success",
    info: "info",
    suggestion: "info",
    warning: "warning",
    error: "danger"
  }[level] || "info";
}

function sandboxText(level) {
  return level === "local_tempdir_timeout_only" ? "本地临时目录+超时" : "安全演示模式";
}

function compileTagType(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "info";
  return analysis?.compile_result?.success ? "success" : "danger";
}

function compileStatusText(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "安全模式下未执行";
  return analysis?.compile_result?.success ? "编译成功" : "编译未通过";
}

function compileCommandText(analysis) {
  if (analysis?.sandbox_level === "disabled" || analysis?.compile_result?.executed === false) return "未执行本地编译命令";
  return analysis?.compile_result?.command || "g++ main.cpp -std=c++17";
}
</script>
