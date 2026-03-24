"""Entry point for python -m quartermaster."""

import asyncio
import sys
from pathlib import Path

import structlog


def configure_logging() -> None:
    """Configure structlog for JSON output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stdout.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def main() -> None:
    """Launch the Quartermaster application."""
    configure_logging()
    logger = structlog.get_logger()

    config_paths = [
        Path("/app/config/settings.yaml"),
        Path("config/settings.yaml"),
        Path("settings.yaml"),
    ]

    config_path = None
    for path in config_paths:
        if path.exists():
            config_path = path
            break

    if config_path is None:
        logger.error("no_config_found", searched=str(config_paths))
        sys.exit(1)

    logger.info("quartermaster_init", config=str(config_path))

    from quartermaster.core.app import QuartermasterApp

    app = QuartermasterApp(config_path)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
