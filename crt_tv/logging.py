import sys

from loguru import logger

# TODO: Add a critical error hanlder to send me an email
# TODO: Add logging configuration to send logs to a file
# TODO: Set up log rotation
# TODO: Syslog handler


def configure_logging(stdout_level: str = "INFO") -> None:
    # remove the default hanlder
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        level=stdout_level,
        format="[{thread.name}] {time:YYYY-MM-DD HH:mm:ss} <level>{level}</level> {message}",
    )
