## 技术栈

```
后端框架        FastAPI
LLM            DeepSeek API（国内便宜，兼容 OpenAI SDK）
LLM 框架       LangChain
向量数据库      Chroma（本地，开发阶段够用）
Embedding      BGE-small（开源，本地运行，免费）
文档处理       LangChain Document Loaders
对话历史存储   PostgreSQL
缓存           Redis
部署           Docker Compose
```

## 系统架构

```
用户
 │
 ▼
FastAPI
 ├── 文档上传接口
 │    └── 文档解析 → 切片 → Embedding → 存入 Chroma
 │
 └── 问答接口（SSE 流式）
      └── 问题 Embedding → Chroma 检索 → 注入 Prompt
           → DeepSeek 生成 → 流式返回
```

## 目录结构

```
doc-qa/
├── src/
│   ├── __init__.py                  # create_app()
│   ├── main.py                      # 入口
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── __init__.py
│   │       │   ├── document.py
│   │       │   └── chat.py
│   │       └── router.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                # Settings / get_settings()
│   │   ├── events.py                # lifespan
│   │   ├── logger.py                # setup_logger()
│   │   └── cache/
│   │       ├── __init__.py
│   │       ├── cache.py             # init_redis / close_redis
│   │       └── redis_ops.py         # Redis 操作封装
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py               # DatabaseManager / db_manager
│   │   └── init_db.py               # close_db()
│   │
│   ├── middleware/
│   │   ├── logging.py               # LoggingMiddleware
│   │   └── request_context.py       # RequestContextMiddleware
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                  # DeclarativeBase
│   │   ├── document.py
│   │   └── conversation.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── base.py                  # ResponseModel / PaginatedResponse
│   │   ├── mixins.py                # TimestampMixin / IDMixin / ORMConfigMixin
│   │   ├── document.py
│   │   └── chat.py
│   │
│   ├── repository/
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseRepository
│   │   ├── document.py
│   │   └── conversation.py
│   │
│   ├── service/
│   │   ├── __init__.py
│   │   ├── document.py
│   │   └── chat.py
│   │
│   └── utils/
│
├── alembic/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

## 核心数据模型

**Document 表**（文档元数据）

```
id, filename, file_type, file_size,
chunk_count,        # 切片数量
status,             # pending/processing/done/failed
created_at, updated_at
```

**Conversation 表**（对话历史）

```
id, session_id, document_id,
role,               # user/assistant
content,
created_at
```

------

## 技术决策

| 决策点         | 选择                           | 原因               |
| -------------- | ------------------------------ | ------------------ |
| Embedding 模型 | bge-small-zh-v1.5              | 中文效果好，体积小 |
| 向量存储       | Chroma（HTTP 模式连接）        | 已经跑起来了       |
| 文档切片       | RecursiveCharacterTextSplitter | LangChain 默认推荐 |
| 流式输出       | SSE                            | 你已有经验         |
| 对话历史       | PostgreSQL 持久化              | 多轮对话支持       |

------

## 接口设计

```
POST   /api/v1/documents/upload     上传文档
GET    /api/v1/documents            文档列表
DELETE /api/v1/documents/{id}       删除文档

POST   /api/v1/chat                 问答（SSE 流式）
GET    /api/v1/chat/{session_id}    获取对话历史
DELETE /api/v1/chat/{session_id}    清空对话历史
```
