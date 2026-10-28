"""Bilibili learning MCP server.

An MCP server that lets LLM clients search Bilibili videos, read metadata,
fetch subtitles and inspect hot comments. The server never calls an LLM:
it only returns structured, LLM-friendly text.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
