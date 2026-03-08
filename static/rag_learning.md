# RAG 项目学习文档

> 基于智能文档问答系统，系统学习 RAG 项目的原理、技术栈和工程设计。

---

## 一、RAG 是什么

### 1. RAG 解决了什么问题？为什么需要它？

LLM 有两个天然的局限性：

**局限一：知识截止日期**
LLM 的训练数据有截止日期，它不知道最新发生的事情。比如你问 GPT-4 "今天的股价是多少"，它答不了。

**局限二：不了解私有数据**
LLM 只知道公开训练数据里的内容，它不知道你公司内部的文档、你自己上传的报告、你的私有知识库。

RAG（Retrieval-Augmented Generation，检索增强生成）就是为了解决这两个问题：
**先从外部数据源检索相关内容，再把检索结果作为上下文提供给 LLM，让 LLM 基于这些内容回答。**

---

### 2. RAG 的完整流程是什么？

RAG 分两个阶段：

**阶段一：索引（Indexing）**，发生在文档上传时：

```
文档 → 解析文本 → 切片 → Embedding（文字变向量）→ 存入向量数据库
```

**阶段二：检索与生成（Retrieval & Generation）**，发生在用户提问时：

```
用户问题 → Embedding → 向量数据库检索 → 取出相关切片
         → 组装 Prompt（切片 + 历史 + 问题）→ LLM 生成回答 → 返回用户
```

---

### 3. RAG 和直接问 LLM 的区别是什么？

| | 直接问 LLM | RAG |
|---|---|---|
| 知识来源 | 训练数据 | 训练数据 + 外部文档 |
| 私有数据 | 不支持 | 支持 |
| 实时数据 | 不支持 | 支持 |
| 幻觉风险 | 高（可能编造） | 低（基于真实文档） |
| 成本 | 低 | 略高（多了检索步骤） |

---

## 二、技术栈详解

### LangChain 是什么？

LangChain 是一个专门用来构建 LLM 应用的 Python 框架。

它解决的问题是：LLM 应用里有大量重复的工程工作，比如管理 Prompt 模板、对接不同的 LLM、做文档切片、连接向量数据库等等。LangChain 把这些都封装好了，让你不用从零开始写。

我们项目里用到了 LangChain 的这些模块：

```
langchain-openai          → 对接 DeepSeek（兼容 OpenAI 接口）
langchain-community       → Document Loaders（PDF/Word/TXT 解析）
langchain-text-splitters  → RecursiveCharacterTextSplitter（文本切片）
langchain-chroma          → Chroma 向量数据库集成
langchain-core            → Document、消息类型（HumanMessage、AIMessage）
```

---

### ChromaDB 是什么？

ChromaDB 是一个专门为 AI 应用设计的向量数据库。

普通数据库（如 PostgreSQL）存的是结构化数据，按 ID 或条件查询。
向量数据库存的是向量（一组浮点数），按**相似度**查询：给一个向量，找出数据库里最相近的几个。

我们用 ChromaDB 的原因：
- 开源免费
- 支持 HTTP 模式（Server 模式），可以独立部署
- 和 LangChain 集成好
- 适合中小规模项目

---

### Embedding 模型是什么？

Embedding 模型的作用是把文本转成向量（一组数字）。

比如"今天天气很好"这句话，经过 Embedding 模型处理后，变成一个 768 维的向量：
```
[0.12, -0.34, 0.56, 0.78, ..., -0.23]  # 768 个数字
```

语义相近的文本，它们的向量在空间中距离也近。这就是为什么可以用向量相似度来做语义检索。

我们用的模型是 `BAAI/bge-small-zh-v1.5`：
- 北京智源研究院开源
- 专门针对中文优化
- 体积小（200MB），适合本地运行
- 免费，不需要调用外部 API

---

### DeepSeek 是什么？

DeepSeek 是国内的大语言模型，由深度求索公司开发。

我们用它的原因：
- 兼容 OpenAI 的 API 接口格式，代码几乎不需要改动
- 价格便宜，适合开发阶段
- 效果好，中文理解能力强

在代码里，我们通过 `langchain-openai` 的 `ChatOpenAI` 类来调用，只需要改 `base_url` 和 `api_key`：

```python
ChatOpenAI(
    model="deepseek-chat",
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)
```

---

## 三、文档处理链路

### 4. 文档上传之后经历了哪些步骤？

```
用户上传文件
  ↓
API 层（document.py）
  → 校验文件类型和大小
  → 读取文件字节流
  ↓
Service 层（document_service.upload）
  → 在 PostgreSQL 创建文档记录（status=PENDING）
  → 更新状态为 PROCESSING
  → 调用 _process()
      → 写入临时文件
      → _load_and_split()：用 Loader 解析文本，用 Splitter 切片
      → vector_store_manager.add_documents()：Embedding + 存入 Chroma
  → 更新状态为 DONE，记录 chunk_count
  → 返回 DocumentOut
```

---

### 5. 为什么要切片？不切行不行？

不切不行，原因有两个：

**原因一：Context Window 限制**
LLM 有输入长度限制（context window），比如 DeepSeek 支持 128K token，但一份几十页的 PDF 可能远超这个限制，直接塞进去会报错。

**原因二：检索精度**
如果把整篇文档作为一个单元存入向量数据库，检索时返回的是整篇文档，和用户问题相关的内容可能只占其中很小一部分，噪音太多影响 LLM 回答质量。

切成小块之后，每次只检索最相关的几个块，精度更高。

---

### 6. chunk_size 和 chunk_overlap 是什么？怎么选择？

```python
CHUNK_SIZE = 500     # 每个切片最大字符数
CHUNK_OVERLAP = 50   # 相邻切片的重叠字符数
```

**chunk_size**：每个切片的最大长度。
- 太大：检索不准，包含太多无关内容
- 太小：上下文不完整，语义被截断
- 中文场景通常选 300-800 字

**chunk_overlap**：相邻切片之间重叠的字符数。
- 作用：避免一句话被切断在两个切片的边界，导致语义丢失
- 比如"张三是一名..." 这句话如果正好在边界被截断，没有 overlap 的话两个切片都看不到完整的句子
- 通常设为 chunk_size 的 10% 左右

**RecursiveCharacterTextSplitter 的切片逻辑**：
按优先级依次尝试分隔符切割：

```
\n\n（段落）→ \n（换行）→ 。！？（句子）→ 空格 → 强制按字符数截断
```
尽量保持语义完整，实在太长才强制截断。

---

### 7. Embedding 是什么？它做了什么事？

Embedding 是把文本转换成向量的过程。

**为什么需要向量？**
计算机无法直接比较两段文字的语义相似度，但可以计算两个向量之间的距离。向量化之后，语义相近的文本距离也近，这样就能做语义检索。

**在我们项目里的具体流程：**
```
切片文本（字符串）
  → bge-small-zh-v1.5 模型处理
  → 768 维向量（768 个浮点数）
  → 存入 ChromaDB
```

**代码里的实现：**
```python
# core/embedding.py
self._model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
```

`normalize_embeddings=True` 表示对向量做归一化，使余弦相似度计算更准确。

---

### 8. 向量数据库存的是什么？怎么存的？

向量数据库里每条记录包含三部分：

```
id        → 唯一标识（自动生成）
vector    → 文本的向量表示（768 维浮点数组）
metadata  → 元数据（原始文本、来源文件等）
```

**我们的存储结构：**
每个文档对应 Chroma 里的一个独立 Collection，命名为 `doc_{document_id}`：
```
Collection: doc_1
  ├── chunk_1: vector=[...], metadata={page_content="第一章..."}
  ├── chunk_2: vector=[...], metadata={page_content="第二章..."}
  └── ...
```

**存储流程：**
```python
# core/vector_store.py
store = Chroma(
    collection_name=f"doc_{document_id}",
    embedding_function=embedding_manager.model,
    client=chromadb.HttpClient(host=..., port=...),
)
store.add_documents(docs)
# LangChain 自动完成：文本 → Embedding → 存入 Chroma
```

---

## 四、检索链路

### 9. 用户提问之后，检索是怎么做的？

```
用户问题（字符串）
  → Embedding 模型转成向量
  → 在 Chroma 对应的 Collection 里做相似度搜索
  → 返回最相似的 k 个切片
```

代码实现：
```python
# core/vector_store.py
store.similarity_search(query, k=4)
# LangChain 自动完成：问题文本 → Embedding → 向量检索 → 返回 Document 列表
```

---

### 10. 相似度检索的原理是什么？

我们用的是**余弦相似度**。

余弦相似度衡量的是两个向量的夹角，值域是 [-1, 1]：
- 1 表示完全相同方向（语义最相似）
- 0 表示垂直（语义无关）
- -1 表示完全相反方向

计算公式：
```
similarity = (A · B) / (|A| × |B|)
```

我们在 Embedding 时设置了 `normalize_embeddings=True`，向量长度都归一化为 1，所以余弦相似度就等于向量点积，计算更快。

ChromaDB 内部使用 **HNSW（Hierarchical Navigable Small World）** 索引做近似最近邻搜索，不需要和每条记录都算一遍，速度很快。

---

### 11. k=4 是什么意思？怎么选这个值？

`k=4` 表示返回最相似的 4 个切片。

**k 太小**：可能遗漏关键信息，LLM 回答不完整
**k 太大**：注入的 context 太长，超出 token 限制，且噪音增多

**选择依据：**
- chunk_size × k 的总 token 数要控制在 LLM context window 的合理范围内
- 我们 chunk_size=500 字，k=4，约 2000 字上下文，比较合理
- 可以根据实际效果调整，一般 3-6 是常用范围

---

### 12. 检索结果怎么用？怎么注入给 LLM？

检索到的 4 个切片，拼接成一段文本注入到 System Prompt 里：

```python
# service/chat.py
context = "\n\n".join([d.page_content for d in retrieved_docs])

SYSTEM_PROMPT = """你是一个专业的文档问答助手。
请根据以下从文档中检索到的相关内容，回答用户的问题。
...
相关文档内容：
{context}
"""
```

LLM 收到的完整消息结构：
```
SystemMessage: 角色设定 + 检索到的文档内容
HumanMessage:  历史用户消息1
AIMessage:     历史回答1
HumanMessage:  历史用户消息2
AIMessage:     历史回答2
HumanMessage:  当前问题（最新）
```

---

## 五、生成链路

### 13. Prompt 是怎么组装的？为什么这样组装？

```python
def _build_messages(self, context, history, question):
    messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    for msg in history[-10:]:
        if msg.role == MessageRole.USER:
            messages.append(HumanMessage(content=msg.content))
        else:
            messages.append(AIMessage(content=msg.content))
    messages.append(HumanMessage(content=question))
    return messages
```

**为什么 context 放在 System Prompt 里？**
System Prompt 是给 LLM 设定角色和背景的，把文档内容放这里，LLM 会把它作为"已知事实"来参考，而不是作为对话内容处理。

**为什么历史消息要区分 HumanMessage 和 AIMessage？**
LLM 需要知道哪句话是用户说的，哪句是自己说的，才能正确理解对话上下文。

---

### 14. 多轮对话是怎么实现的？

多轮对话不依赖连接持久化，而是靠**每次请求都携带历史记录**来实现。

```
第 1 轮：发送 [问题1]           → LLM 回答1 → 存入 PostgreSQL
第 2 轮：发送 [问题1+回答1+问题2] → LLM 回答2 → 存入 PostgreSQL
第 3 轮：发送 [问题1+回答1+问题2+回答2+问题3] → ...
```

**为什么只取最近 10 条？**
随着对话轮数增加，历史消息越来越多，Token 消耗越来越大。限制 10 条是在"记忆完整性"和"Token 成本"之间的平衡。

---

### 15. 流式输出是怎么实现的？为什么用 SSE？

**为什么用流式输出？**
LLM 生成回答需要几秒甚至十几秒，如果等完全生成再返回，用户体验很差。流式输出让用户看到 LLM 逐字生成的过程，感觉更快。

**SSE 的工作方式：**
```
客户端发起 POST 请求
  → 服务端建立连接，持续推送数据
  → 每生成一个 token，立即推送
  → 生成完毕，推送 [DONE]，关闭连接
```

**代码实现：**
```python
# service/chat.py
async for chunk in llm.astream(messages):  # 异步流式调用 LLM
    token = chunk.content
    if token:
        yield token  # 逐 token yield

# api/v1/endpoints/chat.py
async def event_stream():
    async for token in chat_service.chat_stream(...):
        yield f"data: {token}\n\n"  # SSE 格式
    yield "data: [DONE]\n\n"

return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**为什么用 SSE 而不用 WebSocket？**
LLM 流式输出是单向的（服务端 → 客户端），SSE 够用且更简单。WebSocket 是双向的，适合实时聊天、游戏等需要客户端也持续发数据的场景。

---

### 16. LLM 返回的内容是怎么存储的？

流式输出期间，每个 token 都追加到 `full_response` 列表里。
流式结束后，把完整回答存入 PostgreSQL：

```python
full_response = []
async for chunk in llm.astream(messages):
    token = chunk.content
    if token:
        full_response.append(token)
        yield token

# 流结束后存库
full_answer = "".join(full_response)
await conversation_repo.add_message(
    db, session_id, document_id, MessageRole.ASSISTANT, full_answer
)
```

**为什么用列表收集再 join，而不是字符串拼接？**
Python 字符串是不可变对象，每次拼接都会创建新字符串，性能差。列表 append 是 O(1)，最后 join 一次性完成，性能更好。

---

## 六、工程设计

### 17. 为什么用 PostgreSQL 存文档元数据，而不是全部放向量数据库？

向量数据库（ChromaDB）擅长的是向量相似度检索，不擅长结构化查询，比如：
- 查询所有状态为 `done` 的文档
- 按上传时间排序
- 统计文档数量

这些操作在 PostgreSQL 里很简单，在向量数据库里很麻烦甚至不支持。

所以两者各司其职：
- **PostgreSQL**：存文档元数据（filename、status、chunk_count 等），做结构化查询
- **ChromaDB**：存向量数据，做相似度检索

---

### 18. 每个文档用独立 collection 存储，这样设计的原因是什么？

```python
def _get_collection_name(self, document_id: int) -> str:
    return f"doc_{document_id}"
```

**原因一：检索隔离**
用户针对某个文档提问，只应该在这个文档的内容里检索，不应该混入其他文档的内容。独立 collection 天然实现了隔离。

**原因二：删除方便**
删除文档时，直接删掉整个 collection 就行，不需要按条件逐条删除向量数据。

**另一种设计方式**：所有文档放同一个 collection，用 metadata 里的 document_id 过滤。这种方式在文档数量很多时检索更高效，但删除和隔离的实现复杂一些。

---

### 19. 文档删除时为什么要同时删向量数据？

```python
# 先删向量数据
await vector_store_manager.delete_collection(document_id)
# 再删元数据
await document_repo.delete(db, document_id)
```

如果只删 PostgreSQL 的记录，ChromaDB 里的向量数据就成了孤儿数据，永远不会被清理，占用存储空间。

**为什么先删向量数据？**
如果先删了 PostgreSQL 记录，再删 ChromaDB 失败，就再也找不到这个 document_id 对应的 collection 了（因为元数据已经没了）。
先删向量数据，即使失败，PostgreSQL 记录还在，下次还可以重试。

---

### 20. 如果文档处理失败，怎么处理？

```python
try:
    await document_repo.update_status(db, doc.id, DocumentStatus.PROCESSING)
    chunk_count = await self._process(doc.id, file_type, file_bytes)
    await document_repo.update_status(db, doc.id, DocumentStatus.DONE, chunk_count=chunk_count)
except Exception as e:
    await document_repo.update_status(
        db, doc.id, DocumentStatus.FAILED, error_msg=str(e)
    )
    raise
```

失败时：
- 状态更新为 `FAILED`
- 错误信息存入 `error_msg` 字段
- 记录保留在数据库，方便排查问题
- 用户可以看到失败原因，决定是否重新上传

---

## 七、面试表达

### 21. 用一段话描述这个项目

> 我做了一个基于 RAG 的智能文档问答系统。用户上传 PDF、Word 或 TXT 文档后，系统会自动解析文本、切片、用 BGE 模型做向量化，存入 ChromaDB 向量数据库。用户提问时，先把问题向量化，在 ChromaDB 做相似度检索，取出最相关的切片作为上下文，结合对话历史，通过 SSE 流式调用 DeepSeek 大模型生成回答。整个服务用 FastAPI 构建，文档元数据和对话历史存在 PostgreSQL，支持多轮对话。

---

### 22. 这个项目的技术难点是什么？

**难点一：文档处理的工程化**
不同格式文件（PDF/Word/TXT）的解析方式不同，切片策略的选择（chunk_size、overlap、分隔符优先级）直接影响检索质量。

**难点二：流式输出的实现**
SSE + 异步生成器的组合，需要处理流式数据的收集、存储和错误处理，保证流结束后完整回答能正确存入数据库。

**难点三：多轮对话的上下文管理**
在 context window 限制内，如何平衡对话历史的完整性和 Token 成本。

---

### 23. 如果让你优化这个项目，你会从哪些方向入手？

**检索质量优化**
- 混合检索：向量检索 + 关键词检索（BM25）结合，提升召回率
- Rerank 重排序：对检索结果二次排序，提升精度
- 调整 chunk_size 和 k 值，针对不同文档类型优化

**工程性能优化**
- 文档处理改为异步任务（Celery），避免上传接口阻塞
- Embedding 批量计算，提升处理速度
- LLM 调用结果缓存，相同问题直接返回缓存

**功能扩展**
- 支持不选文档的自由对话模式
- 多文档联合检索
- 改造为 Agent，让 LLM 自主决定是否需要检索
- 对话历史的 token 数限制（替代现有的条数限制）

## 八. 其他

### 24. langchain loader 是什么？

在 LangChain 里，Loader（文档加载器） 是专门用来 把各种数据源读取并转换成统一文档格式 的组件。

简单理解：

> **Loader = 把文件 / 数据源读取成 LangChain 能处理的 Document 对象**

在 RAG 项目中，数据可能来自很多地方：

- PDF
- Word
- TXT
- Excel
- Web网页
- 数据库

但 LangChain 后续流程（切分、Embedding、向量库）只认识一种格式：

```
Document
```

所以需要 Loader 统一处理。

流程：

```
文件
 ↓
Loader
 ↓
Document
 ↓
Text Splitter
 ↓
Embedding
 ↓
Vector DB
```

### 25. Document 长什么样

LangChain 的 Document 结构类似：

```
Document(
    page_content="退款将在3个工作日到账",
    metadata={"source": "refund_policy.pdf"}
)
```

包含：

| 字段           | 说明                     |
| -------------- | ------------------------ |
| `page_content` | 文本内容                 |
| `metadata`     | 元数据（文件名、页码等） |

### 26. LangChain 内置 Loader

LangChain 内置很多 Loader。

1️⃣ PDF

```python
from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader("policy.pdf")
docs = loader.load()
```

------

2️⃣ Word

```python
from langchain_community.document_loaders import Docx2txtLoader

loader = Docx2txtLoader("file.docx")
docs = loader.load()
```

内部其实就是调用：

```
docx2txt
```

------

3️⃣ TXT

```python
from langchain_community.document_loaders import TextLoader

loader = TextLoader("notes.txt")
docs = loader.load()
```

------

4️⃣ Web网页

```python
from langchain_community.document_loaders import WebBaseLoader

loader = WebBaseLoader("https://example.com")
docs = loader.load()
```

------

5️⃣ 目录批量加载

```python
from langchain_community.document_loaders import DirectoryLoader

loader = DirectoryLoader("docs/")
docs = loader.load()
```

可以自动读取：

```
docs/
  a.pdf
  b.docx
  c.txt
```

### 27. 文本切片

RecursiveCharacterTextSplitter 是 LangChain 提供的递归字符切分器，是 RAG 里最常用的切片方案。

核心逻辑：按优先级依次尝试分隔符

```python
separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
```

从左到右优先级递减，逻辑是：

1. 先尝试用 `\n\n`（段落）切，切出来的块够小就用这个
2. 不够小再尝试 `\n`（换行）切
3. 还不够小再用 `。` 切
4. 以此类推，最后实在没有分隔符就按字符硬切（`""`）

目标是尽量在语义完整的边界切分，而不是无脑按固定长度截断。

***

两个关键参数：

~~~python
chunk_size=500      # 每个 chunk 最大字符数
chunk_overlap=50    # 相邻 chunk 重叠字符数
```

`chunk_overlap` 的作用是防止语义被切断：
```
chunk1: xxxxxxxxxxxxxxxx[重叠部分]
chunk2:             [重叠部分]xxxxxxxxxxxxxxxx
~~~

如果一句话恰好在边界被切开，重叠部分能保证两个 chunk 都包含这句话的上下文。

***

为什么不用简单的按长度切？

```python
# 简单按长度切 —— 会破坏语义
text[0:500]
text[500:1000]
# 可能把"张三因为..." 切成 "张三因" 和 "为..."
```

RecursiveCharacterTextSplitter 尽量在自然边界切，语义保留更完整，检索质量更好。

### 28. Chroma

```
from langchain_chroma import Chroma

Chroma(
	collection_name=self._get_collection_name(document_id),
	embedding_function=embedding_manager.model,
	client=self._get_chroma_client(),
)
```

`Chroma` 是 LangChain 封装的向量数据库接口，返回一个向量数据库实例。

* collection_name：向量集合名称
* embedding_function：把文本转换成向量（embedding）
* client：Chroma 客户端实例

### 29. Embedding

```
HuggingFaceEmbeddings(
    model_name=settings.EMBEDDING_MODEL_NAME,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
```

* model_name：指定 embedding 模型
* model_kwargs：指定运行设备
  * CPU
  * CUDA：model_kwargs={"device": "cuda"}
  * MPS
* encode_kwargs={"normalize_embeddings": True}：这是一个 非常重要的优化，对向量做归一化。好处：
  * 计算更快
  * 相似度更稳定

加载 HuggingFace 的 embedding 模型并提供统一接口。

```
加载 embedding 模型
↓
提供两个方法
```

* embed_documents(texts)
* embed_query(text)

### 30. 向量数据库设计建议

| 建议                  | 说明                               |
| --------------------- | ---------------------------------- |
| 一 collection，多文档 | 默认，适合大多数场景               |
| metadata 区分文档     | document_id / filename / page      |
| 按业务分 collection   | 适合超大 KB（百万级 chunks）       |
| 控制 chunk size       | chunk_size=300~500, overlap=50~100 |
| embedding model       | 统一 model，避免向量维度不一致     |

- **小型 KB**：< 1k 文档
   → 可以每个文档一 collection（方便删除/迁移）
- **中型 KB**：1k ~ 50k 文档
   → 一 collection，多文档 + metadata
- **大型 KB**：>50k 文档
   → 多 collection 按业务或主题划分 + metadata

> 否则 Chroma 的启动时间、索引加载、内存占用都会爆炸。

### 31. token

**LLM 里的 token 是文本的最小处理单元。**

LLM 不是按字符或按词处理文本，而是按 token。大概的对应关系：

```
英文：一个单词 ≈ 1个token
      "hello" → 1 token

中文：一个汉字 ≈ 1个token
      "你好啊" → 3 tokens

长单词会被拆开：
      "unhappiness" → ["un", "happiness"] → 2 tokens
```

------

**流式返回时，LLM 是一个 token 一个 token 生成的：**

```
问题："你好"

LLM 生成过程：
  第1个token → "你"
  第2个token → "好"  
  第3个token → "！"
  第4个token → "有"
  ...
```

流式接口就是每生成一个 token 就立刻推给前端，所以你看到的是**字一个个出现**，而不是等全部生成完再显示。

### 32. LLM 的对话消息角色

**LLM 的对话消息有三种角色：**

```python
from langchain.schema import SystemMessage, HumanMessage, AIMessage

SystemMessage(content="你是一个助手")   # role: system  → 给LLM设定角色/行为规范
HumanMessage(content="你好")           # role: user    → 用户说的话
AIMessage(content="你好！有什么能帮你") # role: assistant → LLM回复的话
```

### 33. ChatOpenAI

```
model="deepseek-chat"        # DeepSeek 的模型名，不能写 gpt-3.5 这种
api_key=settings.DEEPSEEK_API_KEY   # DeepSeek 的 key，不是 OpenAI 的
base_url=settings.DEEPSEEK_BASE_URL # 指向 DeepSeek 的接口地址，覆盖默认的 OpenAI 地址
temperature=0.7              # 控制回答的随机性
streaming=True               # 开启流式返回
```

temperature：

* 0.0  → 每次回答几乎一样，适合问答/RAG场景（答案要准确）
* 0.7  → 有一定随机性，适合聊天/创作
* 1.0+ → 很随机，容易胡说

