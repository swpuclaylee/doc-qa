from loguru import logger

from src.core.config import PROJECT_ROOT, settings


def format_record(record):
    """自定义格式化函数"""
    # 基础格式
    format_str = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    # 添加 extra 字段
    extra = record["extra"]
    if extra:
        filtered = {k: v for k, v in extra.items() if not k.startswith("log_")}
        if filtered:
            extra_str = " | " + " | ".join(f"{k}={v}" for k, v in filtered.items())
            format_str += extra_str

    format_str += "\n"

    # 如果有异常，添加异常信息
    if record["exception"]:
        format_str += "{exception}"

    return format_str


def setup_logger():
    """配置日志系统"""

    # 日志目录
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    # 移除默认输出
    logger.remove()

    # ========== 控制台输出（开发环境） ==========
    if settings.DEBUG:
        logger.add(
            sink=lambda msg: print(msg, end=""),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            colorize=True,
        )

    # ========== 通用日志文件 ==========
    logger.add(
        log_dir / "app.log",
        format=format_record,
        level="INFO",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    # ========== 错误日志文件 ==========
    logger.add(
        log_dir / "error.log",
        format=format_record,
        level="ERROR",
        rotation="50 MB",
        retention="60 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    # ========== 访问日志文件 ==========
    # 用于记录 API 请求（由中间件写入）
    logger.add(
        log_dir / "access.log",
        format=format_record,
        level="INFO",
        filter=lambda record: record["extra"].get("log_type") == "access",
        rotation="1 day",  # 每天轮转
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    logger.info("日志系统初始化完成")
