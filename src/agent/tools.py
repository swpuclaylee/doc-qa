from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """
    获取当前日期和时间。
    当用户询问当前时间、今天日期、现在几点等问题时调用此工具。
    """
    now = datetime.now()
    return now.strftime("%Y年%m月%d日 %H:%M:%S")


@tool
def calculator(expression: str) -> str:
    """
    执行数学计算。
    当用户需要进行数学运算时调用此工具。
    参数 expression 是数学表达式字符串，例如 '100 * 0.85' 或 '(20 + 30) / 5'。
    """
    try:
        # 只允许安全的数学运算
        allowed = set("0123456789+-*/()., ")
        if not all(c in allowed for c in expression):
            return "错误：只支持基本数学运算（+、-、*、/）"
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


def get_search_document_tool(document_id: int, session_db):
    """
    动态创建文档检索工具

    为什么动态创建：
    search_document 需要 document_id 和 db session，
    这两个参数在运行时才能确定，所以不能用静态的 @tool 装饰器，
    需要在每次请求时动态生成工具实例。
    """
    from src.core.hybrid_search import hybrid_searcher

    @tool
    async def search_document(query: str) -> str:
        """
        在当前文档中检索与问题相关的内容。
        当用户询问文档相关内容时调用此工具。
        参数 query 是检索关键词或问题。
        """
        docs = await hybrid_searcher.search(
            db=session_db,
            document_id=document_id,
            query=query,
            k=4,
            fetch_k=20,
        )
        if not docs:
            return "未找到相关内容"

        results = []
        for i, doc in enumerate(docs, 1):
            results.append(f"[片段{i}]\n{doc.page_content}")

        return "\n\n".join(results)

    return search_document


# def get_search_documents_tool(document_ids: list[int], session_db):
#     """
#     动态创建多文档检索工具
#
#     支持跨多个文档并发检索，结果以 RRF 融合后返回。
#     每条结果标注来源文档 ID，为后续引用溯源做准备。
#     """
#     from src.core.hybrid_search import hybrid_searcher
#
#     @tool
#     async def search_documents(query: str) -> str:
#         """
#         在指定的多个文档中检索与问题相关的内容。
#         当用户询问文档相关内容时调用此工具。
#         参数 query 是检索关键词或问题。
#         """
#         docs = await hybrid_searcher.search_multi(
#             db=session_db,
#             document_ids=document_ids,
#             query=query,
#             k=6,
#             fetch_k=20,
#         )
#         if not docs:
#             return "未找到相关内容"
#
#         results = []
#         for i, doc in enumerate(docs, 1):
#             doc_id = doc.metadata.get("document_id", "?")
#             results.append(f"[片段{i} | 文档ID:{doc_id}]\n{doc.page_content}")
#
#         return "\n\n".join(results)
#
#     return search_documents


def get_search_documents_tool(document_ids: list[int], session_db):
    from src.core.hybrid_search import hybrid_searcher

    @tool
    async def search_documents(query: str) -> str:
        """
        在指定的多个文档中检索与问题相关的内容。
        当用户询问文档相关内容时调用此工具。
        参数 query 是检索关键词或问题。
        """
        docs = await hybrid_searcher.search_multi(
            db=session_db,
            document_ids=document_ids,
            query=query,
            k=6,
            fetch_k=20,
        )
        if not docs:
            return "未找到相关内容\n__SOURCES__:[]"

        results = []
        source_list = []

        for i, doc in enumerate(docs, 1):
            doc_id = doc.metadata.get("document_id", 0)
            chunk_idx = doc.metadata.get("chunk_index", 0)
            content = doc.page_content

            results.append(f"[片段{i} | 文档ID:{doc_id} | 序号:{chunk_idx}]\n{content}")
            source_list.append(
                {
                    "document_id": doc_id,
                    "chunk_index": chunk_idx,
                    "snippet": content[:150],
                }
            )

        import json

        # 将来源信息以特殊标记附在文本末尾，执行器解析时提取
        text = "\n\n".join(results)
        text += f"\n__SOURCES__:{json.dumps(source_list, ensure_ascii=False)}"
        return text

    return search_documents
