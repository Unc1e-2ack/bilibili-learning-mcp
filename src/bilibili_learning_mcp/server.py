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

@mcp.tool(name="get_video_info", title="Get Bilibili video info")
async def get_video_info(bv_id: str) -> str:
    """读取单个 B 站视频的详细信息：标题、简介、UP主、分P列表（含 cid）、互动数据、时长。

    何时调用：
        - 用户给了 BV 号或视频链接，想了解这个视频讲了什么时。
        - 调用 get_subtitles 或 get_hot_comments 之前，先确认分P数量和 cid。
        - 视频没有字幕时，用简介判断内容是否值得看。

    参数：
        bv_id: BV 号或完整链接。支持 "BV1GJ411x7h7"、
            "https://www.bilibili.com/video/BV1GJ411x7h7"、
            "https://www.bilibili.com/video/BV1GJ411x7h7?p=2" 等写法。
            注意 BV 号主体区分大小写，请原样复制，不要手打。

    返回示例：
        标题：线性代数的本质
        BV号：BV1GJ411x7h7 | AV号：8047632
        UP主：3Blue1Brown
        时长：1:02:03（3723 秒）
        播放：1234.5万 | 点赞：8.9万 | 收藏：3.2万 | 投币：1.1万 | 评论：4321
        发布时间：2020-05-01
        链接：https://www.bilibili.com/video/BV1GJ411x7h7

        简介：
        （最多 800 字，超出会标注「已截断」）

        分P列表（共 2 P）：
        P1 | cid=12345678 | 00:12:34 | 向量是什么
        P2 | cid=12345679 | 00:15:01 | 线性组合

    失败时：
        返回以「获取视频信息失败：」开头的说明。BV 号格式错误时会提示正确写法，
        视频不存在或被删除时会说明原因，不要用同样的参数重试。
    """
    try:
        info = await bilibili_api.get_client().get_video_info(bv_id)
    except BilibiliError as exc:
        return f"获取视频信息失败：{exc}"
    except Exception as exc:
        return f"获取视频信息失败：{_error_text(exc)}"

    stats = info["stats"]
    desc = info["desc"].strip() or "（无简介）"
    if len(desc) > 800:
        desc = f"{desc[:800]}……（简介已截断）"

    lines = [
        f"标题：{info['title']}",
        f"BV号：{info['bvid']} | AV号：{info['aid']}",
        f"UP主：{info['owner'] or '未知'}",
        f"时长：{info['duration_text']}（{info['duration_sec']} 秒）",
        f"播放：{_human_count(stats['view'])} | 点赞：{_human_count(stats['like'])}"
        f" | 收藏：{_human_count(stats['favorite'])} | 投币：{_human_count(stats['coin'])}"
        f" | 评论：{_human_count(stats['reply'])}",
        f"发布时间：{_format_date(info['pubdate'])}",
        f"链接：{info['url']}",
        "",
        "简介：",
        desc,
        "",
    ]

    pages = info["pages"]
    if pages:
        lines.append(f"分P列表（共 {len(pages)} P）：")
        for part in pages:
            lines.append(
                f"P{part['page']} | cid={part['cid']}"
                f" | {bilibili_api.format_duration(part['duration_sec'])} | {part['title']}"
            )
        lines.append("")
        lines.append(
            '下一步：用 get_subtitles(bv_id="{}", page=1) 读取第 1 P 字幕，'
            "或用 get_hot_comments 看看观众怎么说。".format(info["bvid"])
        )
    else:
        lines.append("分P列表：接口未返回分P信息，可能是不支持分P的稿件。")

    return "\n".join(lines)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()