# StudyMate：课程资料智能学习辅助原型

StudyMate 是面向课程设计和答辩展示的学习辅助系统。它覆盖资料上传、解析、检索增强问答、练习、复习计划、学习诊断和 PDF 报告，但默认离线配置不调用真实大模型，也不应被描述为生产级 AI 平台。

## 能力边界

| 能力 | 默认配置 | 说明 |
| --- | --- | --- |
| 文本生成 | `TEXT_LLM_PROVIDER=mock` | 离线规则生成，不调用大模型 |
| Embedding | `EMBEDDING_PROVIDER=hash` | 确定性 Hash 检索兜底，不是语义模型 |
| 向量索引 | 可选 Chroma | 只作检索索引；SQL 数据库始终是权限和数据存活状态的权威来源 |
| OCR | `OCR_LLM_PROVIDER=mock` | 默认不具备真实 OCR；可显式配置 Ollama 视觉模型 |
| C++ 执行 | `CPP_RUN_ENABLED=false` | 默认仅规则分析；本地执行不是安全沙箱 |

页面从 `GET /api/health/detail` 读取实际 provider，因此 mock/hash 模式不会显示成 DeepSeek、BGE 或本地 OCR。可选的 Ollama、OpenAI-compatible、sentence-transformers 和 Chroma 依赖必须显式配置。

## 环境要求

- Python 3.11
- Node.js 20 与 npm
- Docker Engine 24+ 和 Docker Compose v2（仅容器部署需要）

## 本地开发

从仓库根目录开始。

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

开发配置可通过 `ENABLE_DEMO_USER=true` 创建演示账号：

```text
demo@studymate.local / studymate-demo
```

生产环境会拒绝启用 demo 用户。数据库结构只由 Alembic 管理；应用启动不会用 `create_all()` 或手写 `ALTER TABLE` 静默修改结构。

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`。

## Docker Compose

### 本地演示

```powershell
docker compose up --build
```

本地只发布 `127.0.0.1:8080` 的前端 Nginx。后端 `8000` 端口只存在于内部 Docker 网络，持久数据位于命名卷 `studymate-data`。

### 生产配置

```powershell
Copy-Item .env.production.example .env.production
# 在 .env.production 中填入独立生成的 AUTH_SECRET_KEY
docker compose --env-file .env.production `
  -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production `
  -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

生产覆盖文件强制：

- `APP_ENV=production`
- `ENABLE_DEMO_USER=false`
- `AUTH_SECRET_KEY` 必须由 shell、CI Secret 或未提交的环境文件注入；缺失或空值时 Compose 直接失败
- 后端不向宿主机发布端口
- provider、model、base URL、RAG、限流和上传限制均从未提交的 `.env.production` 透传；示例默认仍为 mock/hash

默认仍把前端绑定到回环地址。需要由外部反向代理访问时，显式设置 `FRONTEND_BIND_ADDRESS`，并同时配置 HTTPS、代理信任和网络防火墙。
Nginx 的 `NGINX_CLIENT_MAX_BODY_SIZE` 是 multipart 请求的边缘上限，默认 `110m`，需始终高于后端文件本体限制并预留表单编码开销。

## 依赖分层

- `backend/requirements.txt`：生产运行时
- `backend/requirements-dev.txt`：pytest、httpx、Ruff 等开发工具
- `backend/requirements-optional-chroma.txt`：可选 Chroma 索引

生产镜像默认不安装测试工具或 Chroma。需要 Chroma 时可设置 Docker build 参数 `INSTALL_CHROMA=true`，并配置相应持久化与资源限制。

## 关键配置

```env
APP_ENV=development
ENABLE_DEMO_USER=true
TEXT_LLM_PROVIDER=mock
TEXT_LLM_FALLBACK_PROVIDER=none
EMBEDDING_PROVIDER=hash
OCR_LLM_PROVIDER=mock
RERANK_PROVIDER=rule
RAG_TOP_K=5
RAG_MIN_SCORE=0.12
RAG_ENABLE_STRICT_SOURCE_MODE=true
CPP_RUN_ENABLED=false
RATE_LIMIT_ENABLED=false
```

完整说明见 [`backend/.env.example`](backend/.env.example) 和 [`.env.production.example`](.env.production.example)。真实模型密钥只应进入本机环境、CI Secret 或 Secret Manager，不得写入仓库或前端构建产物。

## 数据与迁移

```powershell
cd backend
$tempDb = Join-Path $env:TEMP ("studymate-alembic-" + [guid]::NewGuid().ToString("N") + ".db")
$env:DATABASE_URL = "sqlite:///$($tempDb.Replace('\', '/'))"
python -m alembic upgrade head
python -m alembic check
```

迁移验证应始终使用临时数据库。SQLite 的每个连接都会启用 `PRAGMA foreign_keys=ON`，启动检查在外键未生效或数据库 revision 落后时失败。课程名只要求在同一用户内唯一。

## RAG 可信边界与评估

Chroma 返回的 ID、文本和课程元数据不会直接成为回答依据。服务会回查 SQL 中仍存活、属于当前用户和课程的 chunk、document、course 后才构造上下文。资料删除后，即使外部索引清理暂时失败，陈旧索引项也不能重新进入回答。

确定性评估集覆盖正常回答、无资料、低置信拒答、多文档来源、资料内 Prompt 注入以及删除/重新索引场景，并输出 Hit@K、MRR、拒答准确率、引用正确率和平均/P95 延迟：

```powershell
python scripts/rag_eval.py docs/rag_eval_cases.example.json `
  --output-dir rag_eval_reports
```

详见 [RAG 评估说明](docs/RAG_EVAL.md)。

## 验证

后端：

```powershell
cd backend
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m ruff check . ..\scripts
.\.venv\Scripts\python -m ruff format --check . ..\scripts
.\.venv\Scripts\python -m pytest tests -q
```

前端：

```powershell
cd frontend
npm ci
npm run lint
npm run test:unit
npm run build
npm run test:e2e
npm audit
```

容器：

```powershell
docker compose config --quiet
$env:AUTH_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose build
```

## 文档

- [API 说明](docs/API.md)
- [架构说明](docs/ARCHITECTURE.md)
- [RAG 评估说明](docs/RAG_EVAL.md)
- [安全边界说明](docs/SECURITY.md)
- [部署说明](docs/DEPLOYMENT.md)
- [演示指南](docs/demo-guide.md)

## 已知边界

- SQLite 和进程内限流适合单机演示，不适合多实例高并发生产环境。
- FastAPI `BackgroundTasks` 不是可靠任务队列；生产环境仍需持久化队列、租约和监控。
- token 存储在 `localStorage`，生产化仍需 HTTPS、HttpOnly/SameSite Cookie、CSP/XSS/CSRF 防护和审计。
- OCR 质量、模型数据出域和 C++ 执行风险需要按实际 provider 与部署环境单独评估。
- 学习诊断是可解释规则模型，不是医学或心理测量意义上的认知诊断。
