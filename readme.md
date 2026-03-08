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

## 分阶段实现

第一阶段：跑通核心链路

- FastAPI 项目初始化
- 接入 DeepSeek API，验证基本调用
- LangChain 实现文档加载 + 切片 + Embedding + 存入 Chroma
- 实现最简单的检索问答接口

第二阶段：工程化

- SSE 流式输出
- 多轮对话（对话历史管理）
- 对话历史存入 PostgreSQL
- 文档管理（上传、列表、删除）
- 错误处理、日志、限流

第三阶段：加入 Agent

- 定义工具（Tool）：比如获取当前时间、查询天气
- 用 LangChain Agent 替换简单的 Chain
- 让模型自主决定是检索文档还是调用工具

## deepseek api key

sk-01fd15dfd7124a4d9a8179feedd767a8

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

## 开发流程

**第一阶段：跑通核心链路**

按这个顺序写：

```
1. models/document.py         文档元数据表
2. models/conversation.py     对话历史表
3. alembic 初始化 + 生成迁移
4. schemas/document.py        文档相关 schema
5. schemas/chat.py            对话相关 schema
6. repository/document.py     文档 CRUD
7. repository/conversation.py 对话历史 CRUD
8. core/vector_store.py       Chroma 连接封装
9. core/embedding.py          Embedding 模型封装
10. service/document.py       文档处理：解析、切片、embedding、存储
11. service/chat.py           问答：检索、生成
12. api/v1/endpoints/document.py  上传、列表、删除接口
13. api/v1/endpoints/chat.py      问答接口（SSE 流式）
```

------

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

## 知识点

**Chroma 封装**：负责和向量数据库通信，存向量、查向量。每个文档的切片会以向量的形式存在 Chroma 里，查询时把问题也转成向量，找最相似的切片。

**Embedding 封装**：负责把文本转成向量。用的是本地运行的 `bge-small-zh-v1.5` 模型，不需要调用外部 API，免费且速度快。

这两个是相互独立的，Embedding 负责"文字变向量"，Chroma 负责"向量的存取"。

***

整个流程（RAG 系统）

```
文档 -> Sentence-Transformers -> embedding -> Chroma/ChromaDB -> 存储

用户问题 -> Sentence-Transformers -> embedding -> Chroma/ChromaDB -> TopK文档

TopK文档 + 用户问题 -> LangChain -> 调用 DeepSeek/OpenAI -> 生成答案
```

- `sentence-transformers`：文本 -> 向量
- `chromadb`：存储/搜索向量
- `langchain-chroma`：让 LangChain 用 Chroma
- `langchain` + `langchain-community`：RAG 流程管理
- `langchain-openai`：调用 LLM 生成回答

***

架构说明

1. **文档处理 & Embedding**
   - 文档 PDF/Word → `pypdf` / `python-docx`
   - 文本 → `sentence-transformers` → embedding 向量
   - 存入向量数据库 `chromadb`
2. **向量数据库**
   - `chromadb`：存储向量并支持相似度搜索
   - `langchain-chroma`：提供 LangChain Retriever 接口
3. **问题查询**
   - 用户问题 → `sentence-transformers` → embedding
   - 向量搜索 → TopK 相关文档
4. **RAG 答案生成**
   - `langchain`：管理整个 RAG 流程
   - `langchain-community`：提供扩展功能
   - `langchain-openai`：调用 DeepSeek 或 OpenAI 模型生成回答
5. **Web/API 层**
   - `FastAPI + Uvicorn/Gunicorn` 提供接口
   - `Redis`/`Celery` 支持缓存和异步任务

***

上传一个 PDF/Word/TXT 文件之后，这个 service 要完成以下几步：

```
文件字节流
  → 识别文件类型，用对应的 loader 解析出文本
  → 用 TextSplitter 把长文本切成小块（chunk）
  → 把每个 chunk 转成向量存入 Chroma
  → 把文档元数据存入 PostgreSQL
```

**为什么用临时文件**

LangChain 的 Loader 设计是接收文件路径而不是字节流，所以需要先把上传的文件内容写到临时文件，用完自动删除（`delete=True`）。

**RecursiveCharacterTextSplitter 的 separators**

切片时优先按段落（`\n\n`）切，其次按行（`\n`），再按句子（`。！？`），最后才按字符强制切。这样切出来的每个 chunk 语义更完整。

**为什么先删向量数据再删元数据**

顺序很重要。如果先删了 PostgreSQL 的记录，Chroma 那边的数据就变成了孤儿数据，无法通过 document_id 找到再删除。

**CHUNK_SIZE = 500**

中文 500 字大约是一段话，对于 RAG 检索来说是比较合适的粒度，太大检索不准，太小上下文不完整。

***

`service/chat.py`，这是整个项目最核心的文件。

先说清楚它要做什么：

```
用户发来一个问题
  → 从 PostgreSQL 拉取该会话的历史消息
  → 用问题去 Chroma 检索最相关的文档切片
  → 把 检索结果 + 对话历史 + 问题 组装成 Prompt
  → 调用 DeepSeek 流式生成回答
  → 把用户问题和回答都存入 PostgreSQL
  → 通过 SSE 把回答逐 token 流式返回给前端
```

几个关键点说明：

**为什么历史消息只取最近 10 条**

LLM 有 context window 限制，历史消息太多会超出 token 限制导致报错，同时成本也会增加。10 条是一个合理的平衡点，实际可以根据需要调整。

**为什么先存用户消息再调用 LLM**

如果 LLM 调用失败，用户的问题已经记录了，方便排查问题。如果顺序反过来，LLM 失败后用户消息也丢了。

**full_response 为什么用列表拼接**

流式返回时每次只有一个 token，用列表收集再 `join` 比字符串拼接性能更好

***

**向量数据库 = 存储向量 + 高效相似度检索**

普通数据库（PostgreSQL）也能做相似度计算，但数据量大了之后是**全量暴力计算**，性能很差。

向量数据库的核心价值在于它内置了近似最近邻（ANN）索引算法（比如 HNSW），能在百万、千万级向量中**快速**找到最相似的结果，而不是一条条算。

------

类比一下：

| 类比                         | 对应概念               |
| ---------------------------- | ---------------------- |
| 普通数据库存文本 + LIKE 查询 | 全量暴力相似度计算     |
| 普通数据库 + B-Tree 索引     | 向量数据库 + HNSW 索引 |

------

所以本质上向量数据库就是**为相似度检索这个场景专门优化的数据库**，RAG 用它完全对口。

***

**独立 collection** 的意思就是：每个文档在向量数据库里有自己单独的"表"（类比关系型数据库的表），用 `doc_1`、`doc_2` 这样的名字区分。

对应的另一种设计就是你说的——所有文档放一张"表"里，靠 `where document_id = 1` 来过滤。

------

你这个设计的取舍其实你的注释里已经说清楚了：

- **文档数量少**（比如几十、几百个）→ 独立 collection 没问题，隔离和删除都方便
- **文档数量很多**（比如几万个）→ collection 数量会爆炸，向量数据库管理大量 collection 性能会下降，这时候应该用单 collection + metadata 过滤

***

collection：**一组向量的容器**，类比关系型数据库里的"表"。

***

**每个 collection 都是独立的索引结构（比如 HNSW 图），需要单独加载到内存。**

具体来说：

- collection 少：几个索引常驻内存，检索直接命中
- collection 多：内存放不下所有索引，频繁换入换出，产生大量 I/O

另外每个 collection 还有独立的元数据管理开销，collection 数量一多，光是管理这些元数据就有额外消耗。

------

**类比**：就像你同时开了100个 Excel 文件，每次要查某个文件里的数据都得先打开它，而不是在一个已经打开的大表里直接查。

## 项目扩展

这个项目严格来说是 **RAG 项目**，不是 Agent。

区别很清晰：

- **RAG**：用户问问题 → 检索文档 → LLM 生成回答，流程是固定的
- **Agent**：LLM 自主决策，决定调用哪些工具、调用几次，流程是动态的

***

RAG 本身就是 Agent 最常用的一个工具。把这个项目改造成 Agent 项目，只需要做一件事：**把现在固定的"检索 → 生成"流程，替换成让 LLM 自主决策是否检索、何时检索**。

改造后的 Agent 会有多个工具可以调用：



```
工具一：search_document   → 检索文档内容（现有的 RAG 链路）
工具二：get_current_time  → 获取当前时间
工具三：calculator        → 计算器
... 后续可以继续扩展
```

LLM 收到问题后自己判断：这个问题需要查文档吗？需要查几次？还是直接回答？

------

改造量

不大，主要改 `service/chat.py`：

- 现在：手动检索 + 手动组装 Prompt
- 改造后：用 LangChain Agent + Tools，让 LLM 自己决策

其他层（API、repository、models）基本不动。

------

所以建议：**先把当前 RAG 项目跑通联调，再在此基础上改造成 Agent**。

## 联调

```
报错：File "E:\myproject\doc-qa\src\service\document.py", line 4, in <module>
    from langchain.text_splitter import RecursiveCharacterTextSplitter
ModuleNotFoundError: No module named 'langchain.text_splitter'
原因：
这个错误是因为新版本的 LangChain 将文本分割器相关的功能拆分到了独立的包中。
这个包由 LangChain 官方维护，专门用于文本分割
修复：
pip install langchain-text-splitters
from langchain.text_splitter import RecursiveCharacterTextSplitter改为from langchain_text_splitters import RecursiveCharacterTextSplitter

```

```
PermissionError: [Errno 13] Permission denied: 'C:\\Users\\10935\\AppData\\Local\\Temp\\tmpt_t2cnk8.docx'，
_load_and_split中的docs = loader.load()报错了

```

## RAG

第一阶段：RAG 是什么

```
1. RAG 解决了什么问题？为什么需要它？
2. RAG 的完整流程是什么？
3. RAG 和直接问 LLM 的区别是什么？
```

第二阶段：文档处理链路

```
4. 文档上传之后经历了哪些步骤？
5. 为什么要切片？不切行不行？
6. chunk_size 和 chunk_overlap 是什么？怎么选择？
7. Embedding 是什么？它做了什么事？
8. 向量数据库存的是什么？怎么存的？
```

第三阶段：检索链路

```
9.  用户提问之后，检索是怎么做的？
10. 相似度检索的原理是什么？
11. k=4 是什么意思？怎么选这个值？
12. 检索结果怎么用？怎么注入给 LLM？
```

第四阶段：生成链路

```
13. Prompt 是怎么组装的？为什么这样组装？
14. 多轮对话是怎么实现的？
15. 流式输出是怎么实现的？为什么用 SSE？
16. LLM 返回的内容是怎么存储的？
```

第五阶段：工程设计

```
17. 为什么用 PostgreSQL 存文档元数据，而不是全部放向量数据库？
18. 每个文档用独立 collection 存储，这样设计的原因是什么？
19. 文档删除时为什么要同时删向量数据？
20. 如果文档处理失败，怎么处理？
```

第六阶段：面试表达

```
21. 用一段话描述这个项目
22. 这个项目的技术难点是什么？
23. 如果让你优化这个项目，你会从哪些方向入手？
```

