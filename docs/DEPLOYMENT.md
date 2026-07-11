# 部署说明

## 配置分层

`docker-compose.yml` 是本地演示配置，`docker-compose.prod.yml` 是生产覆盖文件。两者共享同一镜像和命名卷，但认证和暴露边界不同。

| 项目 | 本地演示 | 生产覆盖 |
| --- | --- | --- |
| `APP_ENV` | `development` | 强制 `production` |
| demo 用户 | 显式启用 | 强制关闭 |
| `AUTH_SECRET_KEY` | 进程启动时随机生成 | 必须从外部注入，缺失即失败 |
| 后端端口 | 仅 Compose 网络中的 `8000` | 仅 Compose 网络中的 `8000` |
| 前端端口 | 默认 `127.0.0.1:8080` | 默认仍为回环，可显式覆盖 |
| 数据 | Docker 命名卷 `studymate-data` | Docker 命名卷 `studymate-data` |

后端没有 `ports` 映射。所有浏览器 API 请求都经过前端 Nginx 的 `/api/` 反向代理。

## 本地演示

```powershell
docker compose config --quiet
docker compose up --build
```

打开 `http://127.0.0.1:8080`。默认 provider 是离线规则生成、Hash 检索和 mock OCR；健康详情及页面页脚必须反映这些真实能力。

## 生产启动

1. 复制示例环境文件，但不要提交副本。
2. 用密码管理器或 Secret Manager 生成至少 32 个字符的随机认证密钥。
3. 先渲染配置并确认没有意外端口或空变量，再启动服务。

```powershell
Copy-Item .env.production.example .env.production
# 编辑 .env.production，填入 AUTH_SECRET_KEY

docker compose --env-file .env.production `
  -f docker-compose.yml -f docker-compose.prod.yml config --quiet

docker compose --env-file .env.production `
  -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

以下配置会 fail closed：

- 未提供或提供空的 `AUTH_SECRET_KEY` 时，Compose 不生成配置。
- 生产环境密钥过短或命中示例占位值时，后端拒绝启动。
- 生产环境试图启用 `ENABLE_DEMO_USER=true` 时，后端拒绝启动。
- 数据库不是 Alembic head 或 SQLite 外键未启用时，启动检查失败。

Compose 会把 `.env.production` 中的文本生成、fallback、embedding、OCR、RAG、上传限制、限流和超时配置传给后端。保持示例中的 mock/hash 可得到确定性的离线模式；只有显式填写 provider、model、base URL 和对应 Secret 后才会启用真实模型。

`NGINX_CLIENT_MAX_BODY_SIZE` 限制整个 multipart 请求，必须大于 `DOCUMENT_UPLOAD_MAX_BYTES` 并预留编码开销；默认后端文件上限为 100 MiB，Nginx 默认使用 `110m`。提高后端上传限制时必须同步提高该边缘上限。

若 HTTPS 反向代理不与 Compose 同机，只有在完成 TLS、主机防火墙和代理信任配置后，才设置 `FRONTEND_BIND_ADDRESS` 为明确的非回环接口。不要给 backend 服务增加宿主机端口。

## 数据库迁移

Uvicorn lifespan 会先校验生产安全配置，再执行 Alembic upgrade；迁移和启动检查成功后才接受请求。迁移是唯一结构来源，不允许用 `create_all()` 或运行期 `ALTER TABLE` 绕过 revision 管理。

部署前应对数据库卷做一致性备份，并在相同数据库引擎的副本上验证升级：

```powershell
cd backend
$migrationCopy = Join-Path $env:TEMP ("studymate-migration-" + [guid]::NewGuid().ToString("N") + ".db")
$env:DATABASE_URL = "sqlite:///$($migrationCopy.Replace('\', '/'))"
python -m alembic upgrade head
python -m alembic check
```

迁移会把旧的全局课程名唯一约束改为 `(user_id, name)` 唯一，并补齐课程用户外键、文档处理状态和消息索引。旧结构中没有归属的课程会进入专用的 `legacy-owner@invalid.local` 隔离账号；该账号使用不可登录的禁用密码标记，不会把资料授予任一真实用户。若保留邮箱已被登录账号占用、存在孤儿引用或同一归属内课程重名，迁移会 fail-closed，需先在备份副本中修复数据，不能静默删除或改名。

## 可选 Chroma

生产镜像默认不安装 Chroma。需要它时：

```powershell
docker compose build --build-arg INSTALL_CHROMA=true backend
```

Chroma 只提高检索能力，不是权限或删除状态的权威来源。SQL 回查会过滤陈旧或越权索引项；应用启动时会枚举索引并按 SQL 中仍存活的 course、document、chunk 对账，同时重试清理上次删除遗留的 `.deleting` 文件。

## 健康检查与回滚

- `GET /api/health`：基本存活状态。
- `GET /api/health/detail`：检索后端、配置 provider，以及已经实际使用或回退后的 embedding provider；未调用过的可选 embedding 会明确标为“已配置，未验证”。
- Compose 等待后端健康后才启动前端代理依赖。

应用代码可回滚，但已经执行的数据库迁移不能通过替换旧镜像自动撤销。回滚前先停止写入，恢复部署前备份，或按 Alembic downgrade 语义在数据库副本上验证后再操作。不要对唯一生产数据库直接试验 downgrade。
