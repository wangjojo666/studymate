# StudyMate：基于 RAG 与学习画像的个性化课程复习诊断系统

StudyMate 面向大学生课程复习场景，不只做“上传资料后问答”，而是在 RAG 文档问答的基础上加入知识点抽取、掌握度评估、错题归因和自适应复习推荐，形成“资料上传—知识点建模—智能问答—练习测评—错因分析—复习规划”的学习闭环。

学生上传 PDF、PPT、Word 或 TXT 后，系统解析文本、切分片段、建立课程知识库，并自动识别课程知识点。后续提问、做题和错题记录会持续更新个人学习画像，诊断薄弱知识点，并根据考试时间生成复习任务；扫描版 PDF 可单独调用本地视觉模型做 OCR。

## 功能闭环

1. 课程管理：创建高等数学、C++、大学物理等课程。
2. 资料上传：支持 PDF、PPTX、DOCX、TXT，第一版以 PDF 课程资料为核心演示。
3. 文档解析：按页码或幻灯片页提取文本。
4. 知识库构建：切分 chunk，写入 SQLite，并保存稀疏向量权重。
5. 知识点建模：从课程 chunk 中抽取“格林公式、二重积分换序、虚函数、多态”等知识点，并绑定来源页码。
6. AI 问答：用户提问后先检索课程资料，再把片段交给文本大模型回答。
7. 来源引用：答案下方展示资料名、页码和片段预览。
8. 复习提纲：生成核心概念、重点公式、易错点、可能考法。
9. 自适应练习：按基础题、提高题、考试题、易错题生成专项练习。
10. 错题闭环：记录题目、用户答案、参考答案、错因分析和关联知识点。
11. 学习画像：计算知识点掌握度、薄弱知识点 Top 5、练习正确率和最近复习任务。
12. 复习规划：根据考试日期、每天可复习时长和薄弱知识点生成倒计时复习计划。

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

当前项目已接入本地 `qwen3-vl:30b` 作为 OCR 方案：上传扫描版 PDF 后，资料卡片会出现“需 OCR”和“OCR 入库”按钮。点击后填写“起始页,页数,模式”（例如 `40,8,fast` 或 `40,2,full`），系统会创建后台 OCR 任务，把 PDF 页面渲染为图片，交给 Ollama 中的 `qwen3-vl:30b` 处理，再切分入库。

大教材不要一次全文 OCR 50 页以上。建议默认使用 `fast` 快速索引模式，每次处理 5-10 页，先抽取标题、概念、公式、题型和易错点，让问答尽快可用；`full` 精确 OCR 会逐字识别整页，适合少量关键页，速度明显更慢。任务太慢时可以在资料卡片中点击“停止”，已入库的页面片段会保留。

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
抽取知识点并绑定来源页码
    ↓
用户提问
    ↓
检索相关片段
    ↓
调用文本大模型（如 DeepSeek）
    ↓
返回答案 + 来源页码
    ↓
学生做题并记录结果
    ↓
更新知识点掌握度与错题本
    ↓
生成个性化复习路径
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
7. 在练习题区域选择“易错题”和薄弱知识点，生成专项练习。
8. 进入“学习诊断中心”，查看知识点掌握度、薄弱排名和知识图谱。
9. 把一道错题写入错题本，查看系统生成的错因和后续训练建议。
10. 填写考试日期、每天复习时长和目标，生成倒计时复习计划。

## 项目亮点

本项目不是传统的课程资料问答系统，而是面向大学生课程复习场景构建的个性化学习诊断平台。系统在 RAG 文档问答的基础上，引入知识点抽取、错题归因、掌握度评估和自适应复习推荐机制，实现“资料上传—知识点建模—智能问答—练习测评—错因分析—复习规划”的完整学习闭环。

相比普通 PDF 问答系统，StudyMate 不仅能够回答资料中的问题，还能持续记录学生的学习行为和答题结果，动态生成个人知识画像，识别薄弱知识点，并根据考试时间和掌握程度自动推荐复习路径。文本生成和扫描版 PDF OCR 已拆分配置，方便同时使用云端文本 API 和本地视觉模型。

