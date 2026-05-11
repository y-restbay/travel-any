# WanderBot 漫游指南

基于 AI 的旅行规划助手。用户通过自然语言描述旅行需求，WanderBot 生成定制化的旅行路线和推荐。

## 架构概览

```
[React 前端 :6789] -- HTTP/SSE --> [FastAPI 后端 :6688] -- SQLAlchemy --> [SQLite]
                                        |
                                    LangChain
                                        |
                           OpenAI / Gemini / Mock
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端框架 | React 18 + TypeScript (strict mode) |
| 构建工具 | Vite 5 |
| 样式 | Tailwind CSS 3 + lucide-react 图标 |
| 路由 | react-router-dom v6 |
| 后端框架 | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 |
| LLM 编排 | LangChain 0.3 (langchain-openai / langchain-google-genai) |
| 数据库 | SQLite (文件: `wanderbot.db`) |

## 快速开始

```bash
# 安装前端依赖
npm --prefix frontend install

# 安装 Python 依赖
cd backend && source .venv/bin/activate && pip install -r requirements.txt

# 启动开发服务器（前后端同时启动）
npm run dev

# 验证后端健康状态
npm run test:backend
```

- 前端: http://127.0.0.1:6789
- 后端: http://127.0.0.1:6688
- API 文档（自动生成）: http://127.0.0.1:6688/docs

## 项目结构

```
travel-any/
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── main.tsx           # 入口 + 路由定义
│   │   ├── api.ts             # 所有后端 API 调用
│   │   ├── types.ts           # TypeScript 类型定义
│   │   ├── styles.css         # Tailwind + 全局样式
│   │   ├── pages/
│   │   │   ├── App.tsx        # 聊天主页 (/)
│   │   │   └── Admin.tsx      # 管理员配置页 (/admin)
│   │   └── components/
│   │       └── ShellNav.tsx   # 全局导航栏
│   ├── vite.config.ts
│   └── tailwind.config.ts     # 自定义暖色主题
├── backend/                   # FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 应用工厂 + CORS + 路由注册
│   │   ├── core/config.py     # pydantic-settings 配置
│   │   ├── db/                # 数据库引擎与会话
│   │   ├── models/            # SQLAlchemy ORM 模型
│   │   ├── schemas/           # Pydantic 验证模型
│   │   ├── api/               # 路由处理器
│   │   │   ├── health.py      # GET /api/health
│   │   │   ├── chat.py        # POST /api/chat/stream
│   │   │   └── admin.py       # 管理配置 CRUD
│   │   └── services/          # 业务逻辑
│   │       ├── chat_service.py    # LLM 流式聊天
│   │       └── config_service.py  # 配置管理
│   └── requirements.txt
├── package.json               # 根级脚本（dev / build / test）
└── wanderbot.db               # SQLite 数据库文件
```

## 数据库

### llm_configs
| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| provider | String(80) | 供应商: Mock / OpenAI / Gemini 等 |
| model_name | String(120) | 模型名称 |
| api_key | Text | API 密钥 |
| base_url | String(500) | 自定义 API 地址 |
| is_active | Boolean | 是否启用（同一时间仅一个有效） |

### system_prompts
| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| name | String(120) | 提示词名称 |
| content | Text | 提示词内容 |
| is_active | Boolean | 是否启用（同一时间仅一个有效） |

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat/stream` | 流式聊天（SSE） |
| GET | `/api/admin/config` | 获取当前活跃配置 |
| PUT | `/api/admin/config` | 更新活跃配置 |
| GET | `/api/admin/config/llm` | 列出所有 LLM 配置 |
| POST | `/api/admin/config/llm` | 创建 LLM 配置 |
| PATCH | `/api/admin/config/llm/{id}` | 部分更新 LLM 配置 |
| DELETE | `/api/admin/config/llm/{id}` | 删除 LLM 配置 |
| GET | `/api/admin/config/prompts` | 列出所有系统提示词 |
| POST | `/api/admin/config/prompts` | 创建系统提示词 |
| PATCH | `/api/admin/config/prompts/{id}` | 部分更新系统提示词 |

## 关键开发模式

### 流式聊天（chat_stream）
- 前端通过 `ReadableStream` 消费 SSE 事件
- 事件类型: `meta` / `delta` / `done` / `error`
- 使用 `Mock` provider 或无 API Key 时走 mock 模式，每字符 15ms 延迟模拟流式返回
- 非 Mock 模式下通过 LangChain `astream` 输出

### 配置管理
- `is_active` 字段确保同一时间只有一个 LLM 配置和一个系统提示词生效
- 设置某个配置为 `is_active=True` 时会自动禁用其他配置
- 启动时数据库为空则自动创建默认记录（Mock provider + 中文旅行规划提示词）

### Mock 模式
- provider 不区分大小写，`"Mock"` 即触发 mock
- 也适用于不配置 API Key 的情况
- mock 返回预设的中文旅行规划回复

## 编码约定

- 前端使用 Tailwind 自定义主题色（canvas / paper / ink / muted / clay / sage / moss）
- 后端遵循 FastAPI + SQLAlchemy 标准模式：路由 → 服务层 → ORM
- CORS 仅允许 localhost:6789 和 127.0.0.1:6789
- 数据库初始化在 `startup` 事件中自动执行
