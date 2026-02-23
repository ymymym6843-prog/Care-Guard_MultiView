"""
SENTIO 로깅 설정

Python logging 모듈 기반 중앙 로깅 설정.
서비스별 named logger를 제공합니다.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """애플리케이션 로깅 초기화"""
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("app")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """서비스별 로거 반환

    사용 예:
        logger = get_logger("app.services.camera")
        logger.info("카메라 시작")
    """
    return logging.getLogger(name)
