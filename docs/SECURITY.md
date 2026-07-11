# 安全边界说明

StudyMate 当前定位是课程设计级本地演示原型，不是可直接开放给不可信用户的生产系统。

## C++ 本地执行风险

默认配置：

```env
CPP_RUN_ENABLED=false
```

此时系统只做规则分析，不执行本地编译和样例运行。

如果设置为：

```env
CPP_RUN_ENABLED=true
```

后端会在本机临时目录调用 `g++` 编译，并在提供样例输入时运行程序。当前安全级别仅为：

```text
local_tempdir_timeout_only
```

这表示只有临时目录和超时限制，不是完整沙箱。不能用于执行不可信用户代码。

主要风险包括：

- 死循环、资源耗尽、巨量输出。
- 访问本机文件。
- 创建子进程或调用系统命令。
- 网络访问。
- 编译器或系统工具链漏洞。

生产化至少需要 Docker/Firecracker 等隔离沙箱、CPU/内存/磁盘/进程数限制、网络隔离、只读根文件系统、非特权用户和审计日志。

预留配置：

```env
CPP_RUN_SANDBOX=docker
```

当前版本只记录该配置边界，不默认启用 Docker 运行沙箱。
代码层面会拒绝 `CPP_RUN_SANDBOX=docker`，因为当前没有真实 Docker 沙箱实现；`APP_ENV=production` 下也会拒绝 `CPP_RUN_ENABLED=true`。

## Token 与 localStorage

前端将访问 token 存在 `localStorage`，适合课程设计演示，不适合高安全生产场景。生产化需要：

- HTTPS。
- 更严格的 token 生命周期。
- HttpOnly/SameSite Cookie 或更完善的前端安全策略。
- XSS 防护和内容安全策略。

后端当前使用 HMAC token。开发环境未配置 `AUTH_SECRET_KEY` 时会为当前进程生成随机值，进程重启后旧 token 自动失效；仓库不再提供可复用固定密钥。`APP_ENV=production` 必须显式注入至少 32 字符、非占位的随机密钥，否则启动失败。这只消除了明显错误配置，不代表已经具备生产级身份认证能力。

`ENABLE_DEMO_USER` 默认关闭，本地演示必须显式启用；生产环境即使误设为 `true` 也会拒绝启动。生产 Compose 覆盖文件使用 `${AUTH_SECRET_KEY:?required}`，并且 backend 服务没有宿主机端口映射，只能通过前端 Nginx 访问。

## BackgroundTasks 边界

资料解析、OCR、重新索引和知识点同步仍基于 FastAPI `BackgroundTasks` 或同步请求执行，不是可靠任务队列。服务进程重启后，内存中的 queued/running 任务不会自动恢复；启动恢复逻辑会把这些任务标记为失败，并提示用户确认结果后手动重试。

取消、完成、失败和重试使用带当前状态条件的 SQL 更新。后台 worker 持有过期 ORM 对象时，只有数据库中的状态仍允许该转换才会写入，从而避免已取消任务重新变成 completed。删除活动资料前会先取消相关任务，并把资料置为不可检索的 deleting 状态。

取消任务也是状态标记：OCR 会在处理循环下一次检查时尽量停止；资料解析、重新索引和知识点同步不能强制中断已经开始的工作，已经写入的结果会保留。生产化需要 Celery/RQ/Arq 等队列、幂等任务设计、任务租约、心跳、去重键和可观测性。

## SQLite 边界

数据库结构只由 Alembic revision 管理。应用启动不会执行 `create_all()` 或手写 `ALTER TABLE`；已知旧结构通过受限识别和 stamp 后升级，未知/残缺结构会拒绝启动。SQLite 每个应用连接都会执行并验证 `PRAGMA foreign_keys=ON`。

默认 SQLite 适合单机演示。限制包括：

- 并发写入能力有限。
- 缺少生产级备份、审计和权限治理。
- 本地文件损坏会影响全部数据。

生产化建议迁移 PostgreSQL，并增加迁移、备份、权限和审计策略。

## 上传文件与解析

当前上传支持 PDF/PPTX/DOCX/TXT/图片，并有基础大小限制。DOCX/PPTX 已增加 Office zip 防护：

- 限制 zip 内文件数量。
- 限制单个内部文件解压后大小。
- 限制总解压后大小。
- 拒绝异常路径（绝对路径或 `..`）。

生产化仍需补充：

- MIME 类型和文件头校验。
- 病毒/恶意文档扫描。
- 更细粒度大小、页数、解析时间限制。
- 上传目录隔离和对象存储。
- 解析任务队列和失败重试策略。

## OCR 与本地模型调用

OCR 和图片识别可能调用本地视觉模型或外部服务。限制包括：

- 扫描版 PDF 识别质量不稳定。
- 大文件会消耗大量 CPU/GPU/内存。
- 外部模型服务可能涉及数据出域。

生产化需要明确数据流、脱敏策略、请求限流、任务队列和模型服务隔离。

## RAG 与模型输出

RAG 已增加低置信拒答和来源 score，但仍是原型级可信度控制。生产化需要：

- 更强 embedding 和 rerank。
- 更细粒度引文级答案校验。
- 更强 Prompt 注入防护和红队测试。
- 对上传资料中的恶意指令做更系统的隔离。
- 输出内容审计和日志追踪。

当前已做的基础防护：

- 构建 RAG context 时明确标注资料片段是不可信内容。
- 系统 prompt 禁止执行资料片段中的指令。
- 生成后用来源片段做轻量 answer verification，不足时降级为 `low_confidence`。
- Chroma 只返回候选 ID；回答前回查 SQL 中仍存活且属于目标课程的 chunk、document 和 course，索引内文本及 course metadata 不被直接信任。
- 删除索引失败不会恢复 SQL 已删除内容；启动对账会清理 Chroma 陈旧条目和未完成的物理文件 tombstone。

## 接口限流

当前已增加简单进程内限流，覆盖登录、问答和上传。开发环境默认较宽松，生产环境建议使用 `.env.production.example` 中更严格的默认值。

注意：进程内限流只适合单实例原型。生产化应改为 Redis、网关或反向代理级限流，并按用户、IP、课程和文件大小组合限额。

## 密钥管理

`.env.example` 只用于本地开发说明。生产化不能把真实密钥写入仓库或前端代码，需要：

- Secret Manager 或 CI/CD 密钥管理。
- 环境隔离。
- 密钥轮换。
- 最小权限 API key。

## 生产化必做清单

- Docker 沙箱或更强隔离执行 C++。
- CPU、内存、磁盘、进程数和运行时间限制。
- 网络隔离。
- MIME 和文件头校验。
- 上传限流、接口限流和队列。
- PostgreSQL 或同等级生产数据库。
- 生产密钥管理。
- HTTPS、CSP、XSS/CSRF 防护。
- 监控、审计日志和异常告警。
