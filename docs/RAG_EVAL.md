# RAG 评估说明

`scripts/rag_eval.py` 对 StudyMate 的检索、拒答、引用与延迟做固定回归评估，并同时生成 JSON 和 HTML 报告。默认示例集覆盖：正常可回答、无资料、低置信拒答、多文档来源、资料内 Prompt 注入，以及删除/重建索引后的资料。

## 准备隔离的评估课程

请只在专用测试账号和测试课程中运行评估，不要把生产课程 ID 写入用例。复制 `docs/rag_eval_cases.example.json` 后，按本地测试数据修改 `course_id` 和来源文件提示：

- `expected_answer_status`：期望的 `answered`、`low_confidence`、`empty_knowledge_base` 等状态。
- `expect_refusal`：是否应拒答。
- `expected_keywords`：答案必须覆盖的关键词。
- `forbidden_answer_keywords`：答案不得出现的注入成功标记、已删除内容或无依据结论。
- `expected_source_hints`：应命中的文件名或片段提示；用于 Hit@K、MRR 和引用正确率。
- `expected_chunk_ids`：可选，比文件提示更精确的相关 chunk ID。
- `minimum_source_documents`：多文档问题至少应引用的不同资料数。

删除/重新索引用例的推荐准备方式：先上传含唯一标记 `OBSOLETE_DELETED_MARKER` 的旧资料并确认可检索，删除旧资料，再上传或重新索引当前资料。评估答案不得出现旧标记，来源必须指向当前资料。删除动作不由脚本自动执行，避免误删非测试数据。

## 运行

```powershell
# 从仓库根目录运行
python scripts\rag_eval.py docs\rag_eval_cases.example.json --output-dir rag_eval_reports
```

生产配置默认不创建 demo 用户。推荐通过已有测试账号登录后传入 token：

```powershell
$env:STUDYMATE_API_TOKEN="..."
$env:STUDYMATE_API_BASE_URL="http://127.0.0.1:8000/api"
python scripts\rag_eval.py docs\rag_eval_cases.example.json
```

开发环境明确启用 demo 用户时，也可设置 `STUDYMATE_DEMO_EMAIL` 和 `STUDYMATE_DEMO_PASSWORD` 让脚本登录。

## 指标

- `Hit@K`：有相关性标签的用例中，前 K 个来源至少命中一个相关来源的比例。
- `MRR`：第一个相关来源排名的倒数均值。
- `refusal_accuracy`：标注了拒答预期的用例中，回答/拒答决策正确的比例。
- `citation_correctness`：期望来源、chunk 和最小多文档数均满足的用例比例。
- `average_latency_ms` / `p95_latency_ms`：端到端平均和 P95 延迟。
- `pass_rate`：状态、关键词、禁止关键词、拒答和引用检查全部通过的用例比例。

未提供相应标签的指标显示为 `null`/`n/a`，不会被错误计为失败。

## 与历史基线比较

```powershell
python scripts\rag_eval.py docs\rag_eval_cases.local.json `
  --baseline rag_eval_reports\baseline.json `
  --max-quality-drop 0.02 `
  --max-latency-increase-pct 25 `
  --fail-on-regression
```

质量指标按绝对下降值比较；平均/P95 延迟按百分比增幅比较。`--fail-on-regression` 会在超过阈值时返回退出码 2。普通用例检查失败返回退出码 1。

## 报告与 CI

默认输出：

- `rag_eval_reports/rag_eval_report.json`
- `rag_eval_reports/rag_eval_report.html`

后端测试包含不依赖外部模型或 Chroma 的轻量确定性 RAG 回归，覆盖 SQL 权威回查、拒答、多文档引用、Prompt 注入标记和删除后不再检索。CI 应运行该测试；连接真实模型的完整评估保留为显式任务，避免网络和模型漂移造成不稳定。

默认 `EMBEDDING_PROVIDER=hash` 适合稳定回归，但不代表真实语义模型能力。切换到 BGE 等 embedding 后应重新索引，并用同一固定用例与历史基线比较。
