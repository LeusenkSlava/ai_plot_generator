import logging
import sys

from src.main.config.settings import settings


def setup_logging() -> None:
    log_level = settings.app.LOGGING_LEVEL
    print(f"Logging level set to {log_level}")

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    logging.getLogger("aiokafka").setLevel(logging.WARNING)
