import sys

from loguru import logger


def configure_logging(stdout_level: str = "INFO") -> None:
    # remove the default hanlder
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        level=stdout_level,
        format="[{thread.name}] {time:YYYY-MM-DD HH:mm:ss} <level>{level}</level> {message}",
    )
