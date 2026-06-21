# StudyMate 路线图

路线图按答辩可信度和工程风险排序。当前阶段不继续堆新功能，优先把已有闭环打磨得更可解释、更安全、更容易验证。

## P0：当前优先级

- RAG 可信度：低置信拒答、来源 score、上下文长度限制、严格来源 prompt。
- RAG 二次校验：生成后做轻量来源验证，默认规则 rerank，可通过 `RERANK_PROVIDER=none` 关闭。
- 可恢复处理任务：统一 `ProcessingJob` 记录上传解析、OCR、重新索引和知识点同步，支持任务历史、失败重试和取消。
- 学习诊断证据链：掌握度公式、最近练习摘要、来源页码、证据片段、下一步动作。
- C++ 安全边界：默认关闭本地编译运行，开启时明确只具备临时目录和超时限制。
- README 定位修正：明确课程设计级原型，不夸大默认 AI 能力。
- 基础回归测试：注册/登录、课程、上传、问答、低置信拒答、诊断解释、C++ disabled、PDF 报告。
- 安全小增强：登录、问答、上传内存限流；DOCX/PPTX zip bomb 防护。

## P1：下一阶段

- Docker 沙箱：隔离 C++ 编译运行，增加 CPU/内存/磁盘/网络限制。
- 基础 Docker 部署：已提供 backend/frontend Dockerfile、Compose 和 `.env.production.example`；C++ Docker 沙箱仍保持可选后续项。
- 真实 embedding：接入 sentence-transformers 或稳定 OpenAI-compatible embedding，并提供重新索引入口。
- RAG 评估增强：已输出 JSON/HTML 报告；后续可扩展更大固定测试集和趋势对比。
- E2E 测试：已用 Playwright 覆盖登录、新建课程、上传、问答来源、练习答错和诊断预览；后续可补报告导出。
- 文档截图补全：PDF 报告和 C++ 分析页截图待补充，不影响当前演示主流程。

## P2：长期增强

- 多用户权限：课程共享、助教/学生角色、资料访问控制。
- PostgreSQL：替换 SQLite，补充迁移、备份和部署说明。
- 部署文档：Docker Compose、环境变量、反向代理、HTTPS。
- 更多题型：填空、选择、简答、代码题、错题变式训练。
- 更强 RAG：rerank、引用级答案校验、prompt 注入防护。
- 生产级任务队列：解析、OCR、向量入库、报告生成异步化和可观测。
