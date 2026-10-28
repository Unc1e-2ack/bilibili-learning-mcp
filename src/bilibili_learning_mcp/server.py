"""FastMCP application: tool registration and process entry point.

This module is the only place that knows about MCP. Bilibili HTTP access lives
in :mod:`bilibili_learning_mcp.bilibili_api`, so the tools stay thin: they
validate input via the signature, call the API, and render text that an LLM
can read directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

from bilibili_learning_mcp import bilibili_api
from bilibili_learning_mcp.bilibili_api import BilibiliError

BEIJING = timezone(timedelta(hours=8))

mcp = FastMCP(
    name="bilibili-learning-mcp",
    instructions=(
        "B站学习助手。search_videos 找视频，get_video_info 看简介和分P，"
        "get_subtitles 读字幕（做笔记和总结的最佳素材），"
        "get_hot_comments 判断视频口碑。"
        "本服务只提供数据，不调用 LLM，总结由你完成。"
        "如果工具返回 Cookie 相关的提示，请把配置方法转告用户，不要原样重复调用。"
    ),
)


def _human_count(value: int) -> str:
    """Render a counter using the 万/亿 notation Chinese users expect.

    Args:
        value: Non-negative counter such as a play or like count.

    Returns:
        A compact string, e.g. ``1.2万`` or ``3.4亿``.
    """
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)


def _format_date(timestamp: int) -> str:
    """Format a unix timestamp as Beijing time.

    Args:
        timestamp: Unix seconds; 0 means unknown.

    Returns:
        ``YYYY-MM-DD`` or ``未知`` when the timestamp is unavailable.
    """
    if timestamp <= 0:
        return "未知"
    return datetime.fromtimestamp(timestamp, tz=BEIJING).strftime("%Y-%m-%d")


def _error_text(exc: Exception) -> str:
    """Turn an unexpected exception into an actionable message.

    Args:
        exc: Exception raised while serving a tool.

    Returns:
        A short Chinese message the model can act on.
    """
    if isinstance(exc, BilibiliError):
        return str(exc)
    return (
        f"内部错误（{exc.__class__.__name__}）：{exc}。"
        "请重试一次；若持续失败，请把这条信息反馈给用户并建议提交 issue。"
    )


@mcp.tool(name="search_videos", title="Search Bilibili videos")
async def search_videos(keyword: str, limit: int = 5) -> str:
    """在 B 站搜索学习类视频，返回标题、UP主、BV号、时长、播放量和链接。

    何时调用：
        - 用户想找某个主题的教程、课程或讲解，而手上还没有具体视频时，先用本工具。
        - 需要给用户一份候选清单让他挑选时。
        - 已经知道 BV 号时不要用本工具，直接调用 get_video_info。

    参数：
        keyword: 搜索关键词，建议 1-4 个词，例如 "线性代数 期末速成"、"MIT 6.824"。
            支持中英文和空格；不要传 URL 或 BV 号。
        limit: 返回条数，范围 1-50，默认 5。给用户做选择时 5-10 条足够。

    返回示例：
        搜索「线性代数」找到 2 个视频：

        1. 线性代数 期末速成（4小时）
           UP主：某老师 | 时长：4:12:30 | 播放：120.5万
           BV号：BV1xx411c7mD
           链接：https://www.bilibili.com/video/BV1xx411c7mD

    失败时：
        返回以「搜索失败：」开头的中文说明。B 站搜索接口需要登录 Cookie，
        若提示 Cookie 未配置或已失效，请把配置方法转告用户，不要用相同参数反复重试。
    """
    try:
        videos = await bilibili_api.get_client().search_videos(keyword, limit)
    except BilibiliError as exc:
        return f"搜索失败：{exc}"
    except Exception as exc:
        return f"搜索失败：{_error_text(exc)}"

    lines = [f"搜索「{keyword}」找到 {len(videos)} 个视频：", ""]
    for index, video in enumerate(videos, start=1):
        lines.extend(
            [
                f"{index}. {video['title']}",
                f"   UP主：{video['author']} | 时长：{video['duration'] or '未知'}"
                f" | 播放：{_human_count(video['play'])}",
                f"   BV号：{video['bvid']}",
                f"   链接：{video['url']}",
                "",
            ]
        )
    lines.append(
        '下一步：用 get_video_info(bv_id="上面的BV号") 查看简介和分P，'
        "再用 get_subtitles 读取字幕。"
    )
    return "\n".join(lines)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()