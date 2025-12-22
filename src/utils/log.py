import logging
import os
import colorlog

LOG_LEVEL = ["debug", "info", "warning", "error", "critical"]


def init_logger(level="INFO", log_file=None):
    """
    初始化全局日志配置，只需要调用一次
    """

    log_level = getattr(logging, level.upper(), logging.INFO)

    # 获取 root logger（全局唯一）
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # 如果重复初始化，防止重复添加 handler
    if logger.handlers:
        logger.handlers.clear()

    # 控制台输出
    console_handler = colorlog.StreamHandler()
    color_format = colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR':'red',
            'CRITICAL':'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    console_handler.setFormatter(color_format)
    logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_format = logging.Formatter(
            "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    logger.info("Logger initialized. level=%s file=%s", level, os.path.abspath(log_file))


def get_logger(name):
    """
    获取模块级 logger
    全局共用 root 配置
    """
    return logging.getLogger(name)