import sys
from pathlib import Path
from loguru import logger

LOG_FORMAT_PRESETS = {
    "simple": "<level>{message}</level>",
    "plain": "{message}",
    "detailed": (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    "compact": "<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> <level>{message}</level>",
}


def resolve_format(fmt: str) -> str:
    """Resolves a preset format name or returns the custom format string."""
    return LOG_FORMAT_PRESETS.get(fmt.lower(), fmt)


def setup_logger(
    log_level: str = "INFO",
    log_format: str = "simple",
    log_file: str | None = None,
    log_rotation: str = "10 MB",
    log_retention: str = "30 days",
) -> None:
    """
    Configures loguru logger with customizable console format
    and optional rotating file output.
    """
    logger.remove()

    console_format = resolve_format(log_format)

    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format=console_format,
        colorize=True,
    )

    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_format = resolve_format("detailed") if log_format in ("simple", "plain") else console_format

        logger.add(
            str(file_path),
            level=log_level.upper(),
            format=file_format,
            rotation=log_rotation,
            retention=log_retention,
            encoding="utf-8",
        )
