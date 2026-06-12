# StudyMate 架构说明

StudyMate 采用前后端分离结构，核心目标是把课程资料学习辅助流程做成可演示、可解释、可测试的原型闭环。

## 前端模块

- `frontend/src/views/DashboardView.vue`：课程总览、快速入口、最近学习状态。
- `frontend/src/views/CoursesView.vue`：课程列表与课程创建。
- `frontend/src/views/CourseDetailView.vue`：资料上传、RAG 问答、提纲生成、练习生成、C++ 代码分析、诊断预览。
- `frontend/src/views/LearningDiagnosisView.vue`：掌握度图表、薄弱知识点证据链、错题记录、复习计划、PDF 报告导出。
- `frontend/src/api/client.js`：Axios API 封装、登录 token 存储、统一错误处理。

## 后端路由

- `app/routers/auth.py`：注册、登录、当前用户。
- `app/routers/courses.py`：课程增删查、课程详情、最近问答。
- `app/routers/documents.py`：资料上传、解析入库、OCR、图片识别、删除资料。
- `app/routers/assistant.py`：RAG 问答、复习提纲、专项练习。
- `app/routers/learning.py`：学习画像、知识图谱、错题记录、复习计划、PDF 报告。
- `app/routers/cpp_tools.py`：C++ 代码规则分析与可选本地编译运行。

## 服务层

- `document_parser.py`：解析 PDF/PPTX/DOCX/TXT。
- `chunker.py`：将页面文本切成可检索片段。
- `vector_store.py`：Chroma 可选向量检索与 SQLite 稀疏检索兜底。
- `rag_service.py`：RAG 检索、置信判断、上下文构造、模型调用、来源返回。
- `llm_service.py`：mock/offline、Ollama、OpenAI-compatible 文本生成适配。
- `learning_service.py` / `mastery_service.py`：知识点抽取、掌握度公式、薄弱点、复习计划。
- `report_service.py`：PDF 学习报告生成。
- `cpp_service.py` / `cpp_compile_service.py`：C++ 考点识别、规则诊断、可选本地编译运行。

## 数据库模型

- `User`：登录用户。
- `Course`：课程。
- `Document`：上传资料及处理状态。
- `DocumentChunk`：资料片段、页码、稀疏检索权重。
- `KnowledgePoint`：知识点、来源资料、来源页码、证据片段。
- `ChunkKnowledgePoint`：片段与知识点关联。
- `UserKnowledgeStatus`：用户在知识点上的掌握状态。
- `QuestionAttempt`：练习或错题记录。
- `ReviewTask`：复习任务。
- `ChatMessage`：课程问答记录和来源元信息。
- `GeneratedMaterial`：提纲、练习等生成材料。
- `OcrJob`：扫描版 PDF OCR 任务状态。

## 资料入库流程

1. 前端上传 PDF/PPTX/DOCX/TXT/图片。
2. 后端创建 `Document`，状态从 `queued` 开始。
3. 后台任务解析文本或调用图片识别/OCR。
4. `chunker` 将文本切成 `DocumentChunk`。
5. `vector_store` 写入 SQLite 稀疏检索字段，并在 Chroma 可用时写入向量库。
6. `learning_service` 从 chunk 中抽取知识点并建立证据来源。
7. 文档状态变为 `indexed`；扫描版 PDF 可能变为 `needs_ocr`。

## RAG 问答流程

1. 用户在课程内提问。
2. `rag_service` 按 `RAG_TOP_K` 检索课程 chunk。
3. 检索结果带 `score`、文件名、页码、`chunk_index`。
4. 如果知识库为空、资料处理中或需要 OCR，返回对应 `answer_status`。
5. 如果最高分低于 `RAG_MIN_SCORE` 且开启严格来源模式，直接拒答，不调用 LLM。
6. 如果证据足够，按 `RAG_CONTEXT_MAX_CHARS` 构造上下文并调用模型或 offline 生成。
7. 返回 `answer_status`、`confidence`、`source_count`、`sources`、`retrieval_provider`、`llm_provider`。

## 学习诊断流程

1. 上传资料后同步知识点和证据片段。
2. 用户记录练习结果或错题。
3. `mastery_service` 从初始 60 分开始，根据难度、答对/答错和时间权重计算掌握度。
4. 最近 7 天记录权重更高，薄弱点优先进入复习建议。
5. 前端展示掌握度、公式解释、最近记录摘要、来源页码、证据片段和下一步动作。
6. PDF 报告汇总学习总览、薄弱点、错因、复习计划和建议。
