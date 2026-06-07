# StudyMate：基于 RAG 的课程资料智能问答与复习系统

StudyMate 聚焦课程资料复习。学生上传 PDF、PPT、Word 或 TXT 后，系统解析文本、切分片段、建立课程知识库，并基于检索结果调用文本大模型生成问答、复习提纲和练习题；扫描版 PDF 可单独调用本地视觉模型做 OCR。

## 功能闭环

1. 课程管理：创建高等数学、C++、大学物理等课程。
2. 资料上传：支持 PDF、PPTX、DOCX、TXT，第一版以 PDF 课程资料为核心演示。
3. 文档解析：按页码或幻灯片页提取文本。
4. 知识库构建：切分 chunk，写入 SQLite，并保存稀疏向量权重。
5. AI 问答：用户提问后先检索课程资料，再把片段交给本地模型回答。
6. 来源引用：答案下方展示资料名、页码和片段预览。
7. 复习提纲：生成核心概念、重点公式、易错点、可能考法。
8. 练习题：生成选择题、填空题、简答题，并附答案解析。

## 技术路线

- 前端：Vue 3 + Vite + Element Plus
- 后端：FastAPI + SQLAlchemy
- 数据库：SQLite
- 文档解析：`pypdf` / `PyMuPDF`、`python-pptx`、`python-docx`
- 检索：本地 TF-IDF 稀疏向量检索，后续可替换为 Chroma
- 文本大模型：DeepSeek API / OpenAI-compatible API / 本地 Ollama
- OCR 视觉模型：本地 Ollama `qwen3-vl:30b`

## 本地运行

后端：

```powershell
cd D:\sunny\studymate\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd D:\sunny\studymate\frontend
npm.cmd install
npm.cmd run dev
```

本地模型：

```powershell
ollama list
ollama run qwen3-vl:30b
```

后端默认读取 `backend/.env`：

```env
TEXT_LLM_PROVIDER=deepseek
TEXT_LLM_MODEL=deepseek-v4-flash
TEXT_LLM_BASE_URL=https://api.deepseek.com
TEXT_LLM_API_KEY=

TEXT_LLM_FALLBACK_PROVIDER=ollama
TEXT_LLM_FALLBACK_MODEL=qwen3-vl:30b
TEXT_LLM_FALLBACK_BASE_URL=http://127.0.0.1:11434

OCR_LLM_PROVIDER=ollama
OCR_LLM_MODEL=qwen3-vl:30b
OCR_LLM_BASE_URL=http://127.0.0.1:11434
```

如果 DeepSeek API 不可用，后端会尝试使用本地 Ollama fallback；如果本地模型也不可用，则降级为本地演示回答，方便先验证上传、解析、检索和引用链路。

注意：扫描版/图片版 PDF 没有文字层，普通 PDF 解析库无法提取内容。系统会把这类文件标记为“需 OCR”，并显示页数与提示；要让它进入知识库，需要先用 OCR 工具生成带文本层的 PDF，或后续接入 OCR 服务。

当前项目已接入本地 `qwen3-vl:30b` 作为 OCR 方案：上传扫描版 PDF 后，资料卡片会出现“需 OCR”和“OCR 入库”按钮。点击后填写“起始页,页数”（例如 `1,10` 或 `11,10`），系统会创建后台 OCR 任务，把 PDF 页面渲染为图片，交给 Ollama 中的 `qwen3-vl:30b` 识别文字，再切分入库。识别 340 页教材会很慢，建议先识别前 5-10 页做演示。

如果你的文本问答不想使用 DeepSeek，也可以改成其他 OpenAI-compatible 服务：

```env
TEXT_LLM_PROVIDER=openai_compatible
TEXT_LLM_MODEL=your-model
TEXT_LLM_BASE_URL=http://127.0.0.1:1234/v1
TEXT_LLM_API_KEY=
```

## 系统流程

```text
上传课程资料
    ↓
解析 PDF/PPT/Word/TXT 文本
    ↓
按页码或幻灯片切分 chunk
    ↓
生成本地稀疏向量权重
    ↓
写入课程知识库
    ↓
用户提问
    ↓
检索相关片段
    ↓
调用文本大模型（如 DeepSeek）
    ↓
返回答案 + 来源页码
```

## 第一版和 Chroma 的关系

第一版为了保证本地演示稳定，向量检索使用 SQLite + TF-IDF 稀疏向量实现，接口集中在 `backend/app/services/vector_store.py`。后续要切到 Chroma 时，只需要把该服务改为：

1. 上传后调用 embedding 模型生成向量。
2. 按课程写入 Chroma collection。
3. `search_course()` 改为 Chroma query。
4. 保持返回的 `document_name`、`page_number`、`content`、`score` 字段不变，前端和 RAG 层不用改。

## 展示脚本

1. 打开课程列表，新建或选择一门课程。
2. 上传一份真实课程 PDF。
3. 页面显示资料状态为“已入库”。
4. 提问“第三章的重点是什么？”
5. 查看回答下方的《资料名》P 页码来源。
6. 点击生成复习提纲。
7. 点击生成 10 道练习题。

## 项目亮点

本项目基于 Vue + FastAPI + SQLite 构建课程资料智能问答系统，实现课程资料上传、文档解析、知识库构建、基于 RAG 的智能问答、复习提纲生成和练习题生成。系统通过检索增强生成技术，使 AI 回答基于用户上传的课程资料，并提供来源引用，提高回答的准确性和可追溯性。文本生成和扫描版 PDF OCR 已拆分配置，方便同时使用云端文本 API 和本地视觉模型。

