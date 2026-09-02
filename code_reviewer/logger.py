"""日志模块：控制台 + 滚动文件双输出。"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("code_reviewer")

_configured = False


def setup_logging(
    level: int = logging.INFO,
    log_file: str = "",
    console: bool = True,
) -> None:
    """初始化日志。重复调用只生效一次（默认配置），CLI 显式传参时重置。"""
    global _configured
    logger.handlers.clear()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)) or ".", exist_ok=True)
        fh = RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    _configured = True


def get_logger() -> logging.Logger:
    return logger
