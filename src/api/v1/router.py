from fastapi import APIRouter

from src.api.v1.endpoints.chat import router as chat_router
from src.api.v1.endpoints.document import router as document_router

# 创建 v1 版本的总路由
api_v1_router = APIRouter()

# 聚合各个子路由
api_v1_router.include_router(document_router)
api_v1_router.include_router(chat_router)
