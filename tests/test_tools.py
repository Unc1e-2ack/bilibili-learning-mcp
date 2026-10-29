"""Tests for the MCP tool layer: registration, docstrings and rendering."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from bilibili_learning_mcp import bilibili_api, server

IMG_KEY = "7cd084941338484aae1ad9425b84077c"
SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

Handler = Callable[[httpx.Request], httpx.Response]

VIEW_PAYLOAD: dict[str, Any] = {
    "bvid": "BV1GJ411x7h7",
    "aid": 8047632,
    "title": "线性代数的本质",
    "desc": "从几何角度看线性代数。",
    "owner": {"name": "3Blue1Brown"},
    "duration": 3723,
    "stat": {"view": 12345000, "like": 89000, "favorite": 32000, "coin": 11000, "reply": 4321},
    "pages": [{"page": 1, "cid": 111, "part": "向量是什么", "duration": 754}],
    "pubdate": 1588291200,
}


@pytest.fixture(autouse=True)
def reset_client() -> Iterator[None]:
    """Restore the process-wide client after every test.

    Yields:
        Control back to the test.
    """
    yield
    bilibili_api.set_client(None)


def install(handler: Handler, *, cookie: str = "SESSDATA=test") -> None:
    """Install a mocked client as the shared one.

    Args:
        handler: Mock transport handler.
        cookie: Cookie value exposed to the client.
    """
    bilibili_api.set_client(
        bilibili_api.BilibiliClient(
            cookie=cookie,
            transport=httpx.MockTransport(handler),
            min_interval=0.0,
        )
    )


def nav(request: httpx.Request) -> httpx.Response:
    """Serve the WBI key payload."""
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{SUB_KEY}.png",
                }
            },
        },
    )


def ok(data: object) -> httpx.Response:
    """Wrap a payload in a successful envelope.

    Args:
        data: Value of the ``data`` field.

    Returns:
        A mocked response.
    """
    return httpx.Response(200, json={"code": 0, "data": data})


async def test_four_tools_are_registered() -> None:
    """The P0 surface is exactly four tools."""
    tools = await server.mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "search_videos",
        "get_video_info",
        "get_subtitles",
        "get_hot_comments",
    ]


async def test_tool_descriptions_are_llm_instructions() -> None:
    """Every docstring explains when to call it, its params and its output."""
    tools = await server.mcp.list_tools()

    for tool in tools:
        description = tool.description or ""
        assert "何时调用" in description, tool.name
        assert "参数" in description, tool.name
        assert "返回示例" in description, tool.name


async def test_search_videos_renders_a_readable_list() -> None:
    """Search output carries title, author, play count, BV id and URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/nav"):
            return nav(request)
        return ok(
            {
                "result": [
                    {
                        "title": "<em>线性代数</em> 期末速成",
                        "author": "某老师",
                        "bvid": "BV1xx411c7mD",
                        "duration": "4:12:30",
                        "play": 1205000,
                    }
                ]
            }
        )

    install(handler)
    text = await server.search_videos("线性代数", 5)

    assert "搜索「线性代数」找到 1 个视频" in text
    assert "线性代数 期末速成" in text
    assert "播放：120.5万" in text
    assert "https://www.bilibili.com/video/BV1xx411c7mD" in text


async def test_search_videos_turns_anonymous_block_into_instructions() -> None:
    """A 412 without Cookie becomes setup instructions, not a stack trace."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/nav"):
            return nav(request)
        return httpx.Response(412)

    install(handler, cookie="")
    text = await server.search_videos("线性代数", 5)

    assert text.startswith("搜索失败")
    assert "BILIBILI_COOKIE" in text


async def test_get_video_info_renders_metadata() -> None:
    """Metadata output includes parts and follow-up advice."""
    install(lambda request: ok(VIEW_PAYLOAD))
    text = await server.get_video_info("https://www.bilibili.com/video/BV1GJ411x7h7")

    assert "标题：线性代数的本质" in text
    assert "AV号：8047632" in text
    assert "时长：1:02:03（3723 秒）" in text
    assert "P1 | cid=111 | 12:34 | 向量是什么" in text
    assert "get_subtitles" in text


async def test_get_video_info_reports_bad_input() -> None:
    """Bad BV input is explained instead of raising."""
    install(lambda request: ok(VIEW_PAYLOAD))
    text = await server.get_video_info("not-a-bv")

    assert text.startswith("获取视频信息失败")
    assert "无法识别 BV 号" in text


async def test_get_subtitles_renders_window_and_lines() -> None:
    """Subtitle output shows the chosen window and timestamped lines."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/nav"):
            return nav(request)
        if path.endswith("/view"):
            return ok(VIEW_PAYLOAD)
        if path.endswith("/x/player/wbi/v2"):
            return ok(
                {
                    "subtitle": {
                        "subtitles": [
                            {
                                "lan": "zh-Hans",
                                "lan_doc": "中文（自动生成）",
                                "subtitle_url": "https://aisubtitle.hdslb.com/bfs/ai/x.json",
                            }
                        ]
                    }
                }
            )
        return httpx.Response(
            200,
            json={
                "body": [
                    {"from": 0.0, "to": 3.0, "content": "第一句"},
                    {"from": 61.0, "to": 64.0, "content": "第二句"},
                ]
            },
        )

    install(handler)
    text = await server.get_subtitles("BV1GJ411x7h7", 1, 60, 120)

    assert "共 1 行" in text
    assert "时间范围：01:00 - 02:00" in text
    assert "[01:01] 第二句" in text
    assert "[00:00] 第一句" not in text


async def test_get_subtitles_explains_missing_track() -> None:
    """A video without subtitles gets the documented fallback hint."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/nav"):
            return nav(request)
        if path.endswith("/view"):
            return ok(VIEW_PAYLOAD)
        return ok({"subtitle": {"subtitles": []}})

    install(handler)
    text = await server.get_subtitles("BV1GJ411x7h7")

    assert text.startswith("读取字幕失败")
    assert "没有可用字幕" in text
    assert "get_video_info" in text


async def test_get_hot_comments_renders_ranked_comments() -> None:
    """Comments are ranked by likes and stripped of newlines."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/view"):
            return ok(VIEW_PAYLOAD)
        return ok(
            {
                "replies": [
                    {"member": {"uname": "a"}, "like": 5, "content": {"message": "low"}},
                    {
                        "member": {"uname": "b"},
                        "like": 99,
                        "content": {"message": "high\nscore"},
                    },
                ],
                "page": {"count": 2},
            }
        )

    install(handler)
    text = await server.get_hot_comments("BV1GJ411x7h7", 5)

    assert "热门评论" in text
    assert text.index("👍 99") < text.index("👍 5")
    assert "high score" in text


async def test_get_hot_comments_handles_empty_section() -> None:
    """A closed comment section produces guidance, not an empty string."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/view"):
            return ok(VIEW_PAYLOAD)
        return ok({"replies": None, "page": {"count": 0}})

    install(handler)
    text = await server.get_hot_comments("BV1GJ411x7h7")

    assert "暂无可显示的评论" in text
    assert "get_subtitles" in text


async def test_dotenv_is_loaded_without_overriding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .env file fills gaps but never wins over an exported variable."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("# comment\nBILIBILI_COOKIE=SESSDATA=from-file\n", encoding="utf-8")

    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    server._load_dotenv(dotenv)
    assert os.environ["BILIBILI_COOKIE"] == "SESSDATA=from-file"

    monkeypatch.setenv("BILIBILI_COOKIE", "existing")
    server._load_dotenv(dotenv)
    assert os.environ["BILIBILI_COOKIE"] == "existing"
