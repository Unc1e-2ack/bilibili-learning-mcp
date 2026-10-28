"""Executable entry point.

Usage:
    uv run main.py

The real implementation lives in :mod:`bilibili_learning_mcp.server`; this
file exists so the server can also be started from a checkout without
installing the console script.
"""

from __future__ import annotations

from bilibili_learning_mcp.server import main

if __name__ == "__main__":
    main()