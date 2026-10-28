"""FastMCP application: tool registration and process entry point.

This module is the only place that knows about MCP. All Bilibili HTTP access
lives in :mod:`bilibili_learning_mcp.bilibili_api`, so the API layer can be
tested without starting a server.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="bilibili-learning-mcp",
    instructions=(
        "Bilibili learning assistant. Use search_videos to find videos, "
        "get_video_info to inspect one video, get_subtitles to read its "
        "transcript (best source for notes and summaries) and "
        "get_hot_comments to judge community reception. "
        "The server returns raw data only; the client is responsible for "
        "summarising. Ask the user for a BILIBILI_COOKIE if a tool reports "
        "that login is required."
    ),
)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()