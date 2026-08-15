"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("fakturama_automation")
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
