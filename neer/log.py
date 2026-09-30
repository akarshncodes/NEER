"""Tiny logging helper (rich console) so every module prints the same way."""
from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="%H:%M:%S",
                            handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True, show_path=False)])  # stderr: stdout belongs to MCP
        logging.getLogger("wntr").setLevel(logging.ERROR)
        _configured = True
    return logging.getLogger(name)
