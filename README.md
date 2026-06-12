# StudyMate：课程资料智能学习辅助原型系统

StudyMate 是一个面向大一软件工程课程设计的前后端分离项目。项目目标不是做成熟商业学习平台，而是展示一个“课程资料上传、解析、检索、问答、练习、学习诊断、报告导出”的完整原型流程。

默认配置不需要真实大模型 API key：文本生成走 mock/offline 模式，embedding 使用轻量 hash 方案，适合 clone 后快速演示。需要更真实的语义检索或文本生成时，可以按 `.env.example` 切换到 sentence-transformers、OpenAI-compatible API 或本地 Ollama。

## 项目简介

StudyMate 围绕大学课程复习场景设计。学生可以创建课程、上传 PDF/PPTX/DOCX/TXT/图片资料，系统将资料解析成知识片段并建立检索索引。之后用户可以围绕资料提问、生成复习提纲和练习题，并在学习诊断页面查看知识点掌握度、薄弱点、错题记录和复习计划。

适合大一课程设计的说明：本项目重点展示前后端分离、文档解析、数据库建模、RAG 基础流程和可视化学习诊断。默认 AI 能力采用可离线演示的简化实现，核心价值在于系统流程完整、模块边界清楚、功能可以稳定跑通。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Element Plus、ECharts、Axios |
| 后端 | FastAPI、SQLAlchemy、SQLite、Alembic |
| 文档解析 | python-docx、python-pptx、pypdf、PyMuPDF |
| 检索 | Chroma（可选）+ SQLite 稀疏检索兜底 |
| AI 调用 | mock/offline、Ollama、OpenAI-compatible API |
| 测试与 CI | pytest、GitHub Actions、npm build |

## 系统架构

```text
frontend/ Vue 3 页面
  -> src/api/client.js 统一调用后端 API
  -> 课程、问答、练习、诊断、报告页面

backend/ FastAPI 服务
  -> routers/      路由层：认证、课程、资料、问答、学习诊断、C++ 助教
  -> services/     业务层：文档解析、切片、检索、RAG、学习画像、报告生成
  -> models/       SQLAlchemy 数据模型
  -> tests/        pytest 回归测试

storage/ 本地演示数据目录
  -> uploads/      上传资料
  -> chroma/       Chroma 向量索引
```

## 功能模块

1. 用户登录与课程管理
   支持注册、登录、课程创建、课程列表和课程详情。课程数据按登录用户隔离。

2. 课程资料上传与入库
   支持 PDF、PPTX、DOCX、TXT 和图片课件。上传后先返回资料记录，再通过后台任务推进解析、切片、索引和知识点同步状态。

3. RAG 资料问答
   问答基于课程资料片段构建上下文，回答会返回来源文件、页码、片段预览、`retrieval_provider` 和 `llm_provider`。没有资料或检索不到有效内容时，会给出明确提示，不硬编答案。

4. 复习提纲与练习生成
   根据已上传资料生成复习提纲和练习题。默认 mock/offline 模式也能演示完整流程。

5. 学习诊断与错题记录
   根据答题记录计算知识点掌握度，展示薄弱知识点、错因分类、复习建议和复习计划。

6. C++ 代码分析
   支持本地 `g++` 编译诊断、规则考点识别和离线/LLM 解释。未安装 g++ 时会友好降级，不影响其他功能。

7. PDF 学习报告
   导出课程学习诊断报告，汇总资料、问答、练习、薄弱知识点和复习计划。

## 运行步骤

### 1. 后端启动

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

### 2. 前端启动

```powershell
cd D:\sunny\studymate\frontend
npm install
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173
```

### 3. 回归测试

```powershell
cd D:\sunny\studymate
python -m pytest backend/tests -q
```

### 4. 前端构建

```powershell
cd D:\sunny\studymate\frontend
npm run build
```

### 5. 后端 smoke test

先启动后端，再在项目根目录运行：

```powershell
python scripts\smoke_test.py
```

## 演示流程

1. 登录系统。
2. 新建课程，例如“C++ 程序设计”。
3. 上传一份 TXT、PDF、PPTX 或 DOCX 课程资料。
4. 等待资料状态从“已上传/解析中”变为“已入库”。
5. 在问答区提问，例如“这份资料的核心知识点是什么？”。
6. 查看回答下方的来源文件名、页码和片段预览。
7. 生成复习提纲。
8. 生成 5 道基础练习题。
9. 在学习诊断页记录一次答题结果，查看学习画像和薄弱知识点。
10. 导出 PDF 学习报告。

## 答辩演示路线

登录 → 新建课程 → 上传资料 → 等待入库 → 提问 → 查看来源 → 生成提纲 → 生成练习 → 查看学习画像 → 导出报告。

建议演示时使用一份较小的 TXT 或 PDF 资料，避免现场等待大文件解析。默认 mock/offline 模式即可展示系统闭环；如果现场有本地 Ollama 或 API key，再演示更真实的模型回答。

## 核心接口说明

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/auth/register` | 注册用户 |
| POST | `/api/auth/login` | 登录并返回 token |
| GET | `/api/auth/me` | 获取当前用户 |
| GET | `/api/courses` | 获取课程列表 |
| POST | `/api/courses` | 创建课程 |
| GET | `/api/courses/{course_id}` | 获取课程详情、资料和最近问答 |
| POST | `/api/courses/{course_id}/documents` | 上传课程资料 |
| POST | `/api/courses/{course_id}/ask` | 基于资料问答 |
| POST | `/api/courses/{course_id}/review-outline` | 生成复习提纲 |
| POST | `/api/courses/{course_id}/practice` | 生成练习题 |
| GET | `/api/courses/{course_id}/learning/profile` | 获取学习画像 |
| POST | `/api/courses/{course_id}/learning/attempts` | 记录练习结果 |
| GET | `/api/courses/{course_id}/learning/report.pdf` | 导出学习报告 |
| POST | `/api/courses/{course_id}/cpp/analyze` | C++ 代码分析 |

## 项目亮点

- 前后端分离结构清晰，适合课程设计讲解。
- 上传资料后有明确状态流转，避免大文件上传时页面卡死。
- RAG 问答返回来源片段，便于答辩时解释“答案从哪里来”。
- 学习画像有掌握度公式、错因分类和解释文本。
- 默认 mock/offline 模式可以无 API key 跑通核心演示。
- pytest 和 GitHub Actions 覆盖基础回归流程。

## 已知不足

- 默认 SQLite 适合本地演示，不适合高并发生产环境。
- 默认 hash embedding 是轻量演示方案，不等同于真实深度语义模型。
- OCR 依赖本地视觉模型或外部 OCR 工具，普通电脑建议先使用带文本层的 PDF。
- C++ 编译诊断依赖本机 `g++`，没有容器级安全沙箱。
- 学习画像是规则模型，主要用于课程设计展示，不是复杂认知诊断模型。

## 后续改进方向

- 接入更稳定的本地 embedding 模型或学校私有模型服务。
- 增加课程资料批量上传和解析队列管理。
- 增加前端单元测试和端到端测试。
- 优化 PDF 报告版式和图表展示。
- 将 SQLite 切换为 PostgreSQL，并补充更完整的权限模型。

## 本地验收结果

* python -m pytest backend/tests -q：passed
* cd frontend && npm run build：passed
* python scripts/smoke_test.py：passed
