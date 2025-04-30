import sys

from loguru import logger

# TODO: Add a critical error hanlder to send me an email


def configure_logging(stdout_level: str = "INFO") -> None:
    # remove the default hanlder
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        level=stdout_level,
        format="<level>{level}</level> {message}",
    )
