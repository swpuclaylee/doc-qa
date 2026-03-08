from celery import Celery
from celery.signals import worker_process_init

from src.core.config import settings

# 创建 Celery 应用
celery_app = Celery(
    "docqa_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.tasks"],  # 引入任务模块
)

# Celery 配置
celery_app.conf.update(
    # 任务配置
    task_serializer="json",  # 任务序列化格式
    accept_content=["json"],  # 接受的内容格式
    result_serializer="json",  # 结果序列化格式
    timezone="Asia/Shanghai",  # 时区
    enable_utc=True,  # 使用 UTC 时间
    # 任务结果配置
    result_expires=3600,  # 结果过期时间（1小时）
    result_backend_transport_options={
        "master_name": "mymaster"  # Redis Sentinel 配置（可选）
    },
    # Worker 配置
    worker_prefetch_multiplier=4,  # Worker 预取任务数
    worker_max_tasks_per_child=1000,  # Worker 执行任务数后重启
    # 任务路由, 将不同类型的任务分配到不同的队列
    task_routes={
        "src.tasks.email.*": {"queue": "email"},  # 邮件任务路由到 email 队列
    },
    # 任务限流， 限制任务执行频率（防止 API 限流、资源耗尽）
    task_annotations={
        "src.tasks.email.send_email": {"rate_limit": "100/m"},  # 每分钟最多100个
    },
)


@worker_process_init.connect
def setup_loguru(**kwargs):
    """
    Celery Worker 启动时配置 loguru

    让 tasks 中的 loguru 日志写入文件
    """
    import sys
    from pathlib import Path

    from loguru import logger

    # 日志目录
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # 移除默认配置
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # Celery 任务日志文件
    logger.add(
        log_dir / "celery_tasks.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    # Celery 错误日志
    logger.add(
        log_dir / "celery_error.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="50 MB",
        retention="60 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    logger.info("Celery Worker loguru 已配置")
