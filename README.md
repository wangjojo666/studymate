# StudyMate：课程资料智能学习辅助原型系统

StudyMate 是面向课程设计/答辩展示的课程资料智能学习辅助原型系统，不是成熟商业 AI 学习平台。项目重点是把一条可解释、可演示的工程闭环跑通：

课程资料上传 → 文档解析 → 切片入库 → RAG 问答 → 练习生成 → 错题记录 → 学习诊断 → PDF 报告。

默认配置采用 mock/offline 文本生成和 hash embedding，保证无 API key、无联网环境也能稳定演示。真实语义检索和真实大模型生成是可选增强，不能把默认模式夸大成完整 AI 能力。

## 项目定位

- 面向课程设计和答辩展示，强调工程流程完整、模块边界清楚、结果可解释。
- 默认 mock/offline 模式适合现场演示：稳定、无需 API key、不会因为模型服务不可用而中断。
- 默认 hash embedding 是轻量兜底方案，能演示检索链路，但不等同于真实语义模型。
- sentence-transformers 或 OpenAI-compatible embedding 可用于更真实的语义检索。
- Ollama 或 OpenAI-compatible 文本模型可用于更自然的回答、提纲和练习生成。
- 扫描版 PDF/OCR、C++ 本地编译运行都属于本地演示能力，不是生产级服务。

## 演示模式 vs 真实模型模式

| 模式 | 配置 | 适用场景 | 说明 |
| --- | --- | --- | --- |
| mock/offline | `TEXT_LLM_PROVIDER=mock` | 答辩演示、离线运行 | 不调用外部模型，用规则和片段摘要保证稳定 |
| hash embedding | `EMBEDDING_PROVIDER=hash` | 默认检索兜底 | 轻量、可运行，但不是深度语义检索 |
| sentence-transformers | `EMBEDDING_PROVIDER=sentence_transformers` | 更真实的本地语义检索 | 需要额外安装模型依赖和下载模型 |
| OpenAI-compatible embedding | `EMBEDDING_PROVIDER=openai_compatible` | 接入外部 embedding 服务 | 需要 base URL 和 key |
| Ollama/OpenAI-compatible LLM | `TEXT_LLM_PROVIDER=ollama/openai_compatible` | 更真实文本生成 | 需要本地模型或 API 服务 |

## 功能模块

1. 用户登录与课程管理：注册、登录、课程创建、课程详情，课程数据按用户隔离。
2. 课程资料上传与入库：支持 PDF、PPTX、DOCX、TXT、图片课件，后台完成解析、切片、索引和知识点同步。
3. RAG 资料问答：返回回答状态、置信度、来源文件、页码、chunk、score、检索 provider 和模型 provider；证据不足时拒答。
4. 复习提纲与练习生成：基于已入库资料生成提纲和练习题，默认离线模式也可演示。
5. 可解释学习诊断：返回知识点掌握度、薄弱原因、证据片段、来源页码、最近练习摘要和下一步动作。
6. C++ 代码分析：默认安全演示模式只做规则分析；显式开启后才调用本地 g++ 编译/运行。
7. PDF 学习报告：导出课程资料、问答、薄弱点、错题、复习计划和建议。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Element Plus、ECharts、Axios |
| 后端 | FastAPI、SQLAlchemy、SQLite、Alembic |
| 文档解析 | python-docx、python-pptx、pypdf、PyMuPDF |
| 检索 | Chroma（可选）+ SQLite 稀疏检索兜底 |
| AI 调用 | mock/offline、Ollama、OpenAI-compatible API |
| 测试与 CI | pytest、GitHub Actions、npm build |

## 运行步骤

### 后端

```powershell
cd D:\sunny\studymate\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

默认演示账号：

```text
demo@studymate.local / studymate-demo
```

### 前端

```powershell
cd D:\sunny\studymate\frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 关键配置

```env
TEXT_LLM_PROVIDER=mock
EMBEDDING_PROVIDER=hash
RAG_TOP_K=5
RAG_MIN_SCORE=0.12
RAG_CONTEXT_MAX_CHARS=6000
RAG_ENABLE_STRICT_SOURCE_MODE=true
CPP_RUN_ENABLED=false
CPP_COMPILE_TIMEOUT_SECONDS=8
CPP_RUN_TIMEOUT_SECONDS=5
```

`RAG_ENABLE_STRICT_SOURCE_MODE=true` 时，如果最高检索分数低于 `RAG_MIN_SCORE`，后端不会调用 LLM，而是返回“资料中没有找到足够依据回答这个问题，请补充资料或换一个更贴近资料的问题。”

`CPP_RUN_ENABLED=false` 是默认安全演示模式。设置为 `true` 后会在本机临时目录调用 `g++`，仅有超时限制，不是完整沙箱。

## 答辩推荐话术

- 本项目重点不是训练大模型，而是实现课程资料学习辅助的完整工程闭环。
- 默认 mock/offline 和 hash embedding 是为了稳定演示；真实语义检索和真实大模型可以替换 provider 增强。
- RAG 回答会尽量基于上传资料来源片段，并展示文件名、页码、chunk 和 score。
- 如果资料证据不足，系统会拒答，不会硬编一个看似合理的答案。
- 学习画像是规则模型，不是认知诊断大模型；每个分数都有公式、练习记录和证据片段。
- 扫描版 PDF/OCR、C++ 编译运行是本地可信演示能力；开放环境必须增加沙箱、资源限制和安全隔离。

## 项目截图占位

| 场景 | 路径 | 说明 |
| --- | --- | --- |
| 首页 | `docs/images/dashboard.png` | 已有示例图 |
| 课程资料上传 | `docs/images/course-workspace.png` | 已有示例图 |
| 问答带来源 | `docs/images/qa-source.png` | 已有示例图 |
| 学习画像 | `docs/images/learning-profile.png` | 已有示例图 |
| PDF 报告 | `docs/images/pdf-report.png` | 待补截图，占位路径 |
| C++ 代码分析 | `docs/images/cpp-analysis.png` | 待补截图，占位路径 |

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [RAG 评估说明](docs/RAG_EVAL.md)
- [安全边界说明](docs/SECURITY.md)
- [路线图](docs/ROADMAP.md)
- [API 说明](docs/API.md)
- [答辩演示脚本](docs/demo-guide.md)

## 验证

```powershell
cd D:\sunny\studymate\backend
python -m pytest tests -q
```

```powershell
cd D:\sunny\studymate\frontend
npm install
npm run build
```

如后端已经启动，可在项目根目录运行：

```powershell
python scripts\smoke_test.py
```

RAG 简单评估：

```powershell
python scripts\rag_eval.py docs\rag_eval_cases.example.json
```

运行前先把示例 JSON 中的 `course_id` 改成本地已上传资料的课程 ID。

## 已知边界

- SQLite 适合本地演示，不适合高并发生产环境。
- 默认 hash embedding 不是真实语义模型。
- 默认 mock/offline 不是大模型推理。
- OCR 依赖本地视觉模型或外部工具，扫描版 PDF 效果受模型和机器性能影响。
- C++ 本地执行默认关闭；即使开启，也只有临时目录和超时限制，不是安全沙箱。
- 学习诊断是可解释规则模型，不是医学/心理测量意义上的认知诊断。
