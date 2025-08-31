import os
import sys

from loguru import logger

# 移除默认的 logger 配置
logger.remove()

# 定义日志文件路径，保存在项目根目录下的 logs 文件夹中
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "email_agent.log")

# 配置日志格式
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# 添加日志处理器：输出到控制台
logger.add(
    sys.stderr,
    format=log_format,
    level="INFO",  # 控制台只显示 INFO 级别及以上的日志
    colorize=True
)

# 添加日志处理器：保存到文件
logger.add(
    log_file_path,
    format=log_format,
    rotation="10 MB",  # 单个日志文件最大 10MB
    compression="zip",  # 自动压缩旧日志文件
    level="DEBUG",  # 文件中记录所有 DEBUG 级别及以上的日志
    encoding="utf-8"
)

# 确保 logger 实例被正确导出，供其他模块调用
__all__ = ["logger"]
