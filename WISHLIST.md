# WanderBot 未实现功能清单

> 基于代码审查整理，标记了哪些是"有计划但未落地"、哪些是"可以做的改进"。

---

## 一、有计划但未落地的代码痕迹

### 1. `conversation_id` 未使用

- **位置**: `backend/app/schemas/chat.py:16`
- **状态**: `ChatStreamRequest` 中定义了 `conversation_id: Optional[str] = None`，但整个后端链路 (`chat.py` → `chat_service.py`) 从未读取或使用此字段
- **需要补的**:
  - 聊天记录持久化到 SQLite（新建 `conversations` 和 `messages` 表）
  - 流式返回时写入数据库
  - 前端支持恢复历史对话

### 2. 完整 CRUD 未接入管理界面

- **位置**: `backend/app/api/admin.py` / `frontend/src/pages/Admin.tsx`
- **状态**: 后端实现了 LLM 配置和 System Prompt 的完整 CRUD（list/create/update/delete），但前端的 Admin 页面只对接了 `GET/PUT /admin/config`（仅读写当前激活的配置），创建多组配置、切换历史配置、删除等功能从未暴露
- **需要补的**:
  - Admin 页面增加配置列表/切换/删除界面
  - 支持保存多组 LLM 配置并一键切换

### 3. 没有测试文件

- `backend/` 下无 `tests/` 目录，无 pytest 用例
- `frontend/` 下无测试框架配置，无组件测试

---

## 二、用户已提出的需求

### 4. LLM 配置连接测试（待实现）

- 管理界面保存配置后，无法验证 LLM 是否能连通
- **需要补的**:
  - 后端 `POST /api/admin/config/test` 端点：用当前配置发一条简单请求，返回成功/失败及错误信息
  - 前端在 LLM 配置面板增加"测试连接"按钮，展示测试结果（耗时、是否成功、错误详情）

### 5. 符合系统功能（待澄清）

- 用户此前表述"渡河系统"，后更正为"符合系统"
- 需求待明确

---

## 三、项目完整度缺口

### 6. 缺少部署基础设施

| 项目 | 说明 |
|---|---|
| Dockerfile | 无容器化构建 |
| docker-compose.yml | 无编排配置（需要至少 backend + db） |
| nginx 配置 | 无生产级反向代理/静态文件托管配置 |
| CI/CD | 无 GitHub Actions / 类似流水线 |

### 7. 缺少可观测性

| 项目 | 说明 |
|---|---|
| 日志 | 无结构化日志（目前只有 print / 无日志） |
| 请求追踪 | 无 request_id 中间件 |
| 告警/监控 | 无健康检查以外的监控 |

### 8. 前端改进点

| 项目 | 说明 |
|---|---|
| Error Boundary | 无 React Error Boundary 包裹，组件崩溃会导致白屏 |
| 加载骨架屏 | Admin 页面 loading 状态仅文字，无骨架屏 |
| 对话管理 | 无保存/加载/删除历史对话功能 |
| 消息重试 | 流式失败后无重试按钮 |
| 国际化 | 仅支持中文，无 i18n 框架 |
| 响应式 | 未在移动端充分测试 |
| 暗色模式 | 无主题切换 |

### 9. 后端改进点

| 项目 | 说明 |
|---|---|
| 限流 | 无请求频率限制 |
| 认证鉴权 | Admin 接口无任何保护 |
| 数据库迁移 | 无 Alembic 迁移，启动时直接 `create_all` |
| 环境校验 | 无启动时环境检查（API Key 为空时直接 Mock，用户无感知） |
| WebSocket | 当前使用 SSE，可考虑提供 WebSocket 版 |

---

## 四、低优先级 / 可做可不做

| 项目 | 说明 |
|---|---|
| PWA | 离线访问、消息推送 |
| 对话分享 | 生成分享链接 |
| 出行规划模板 | 预设旅行方案模板 |
| 第三方地图集成 | 路线可视化 |
| vLLM / Ollama | 本地模型支持（当前仅 OpenAI / Gemini） |

---

> **说明**: 此文件仅记录当前代码中尚未实现的功能和有改进空间的地方，供后续开发参考。标记为"有计划但未落地"的三项（`conversation_id`、完整 CRUD 接入、测试）是代码中已有意图但中途停止的部分。
