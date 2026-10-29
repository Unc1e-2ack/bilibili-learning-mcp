"""Behaviour tests for the Bilibili client, served entirely by mocked HTTP."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx
import pytest

from bilibili_learning_mcp import bilibili_api
from bilibili_learning_mcp.bilibili_api import BilibiliError, normalize_bvid

IMG_KEY = "7cd084941338484aae1ad9425b84077c"
SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

Handler = Callable[[httpx.Request], httpx.Response]
T = TypeVar("T")

_PATH_HINTS = {
    "nav": "/nav",
    "search": "/search/type",
    "view": "/view",
    "player": "/x/player/wbi/v2",
    "reply": "/x/v2/reply",
    "cdn": "aisubtitle.hdslb.com",
}

VIEW_PAYLOAD: dict[str, Any] = {
    "bvid": "BV1GJ411x7h7",
    "aid": 8047632,
    "title": "线性代数的本质",
    "desc": "从几何角度看线性代数。",
    "owner": {"name": "3Blue1Brown"},
    "duration": 3723,
    "stat": {"view": 12345000, "like": 89000, "favorite": 32000, "coin": 11000, "reply": 4321},
    "pages": [
        {"page": 1, "cid": 111, "part": "向量是什么", "duration": 754},
        {"page": 2, "cid": 222, "part": "线性组合", "duration": 901},
    ],
    "pubdate": 1588291200,
}


def route(**handlers: Handler) -> Handler:
    """Dispatch mocked requests by short path name or host.

    Args:
        **handlers: Mapping of short names (``nav``, ``search``, ``view``,
            ``player``, ``reply``, ``cdn``) to response factories.

    Returns:
        A handler suitable for ``httpx.MockTransport``.
    """

    def dispatch(request: httpx.Request) -> httpx.Response:
        for name, handler in handlers.items():
            hint = _PATH_HINTS.get(name, name)
            if request.url.path.endswith(hint) or hint == request.url.host:
                return handler(request)
        return httpx.Response(404, json={"code": -404})

    return dispatch


def nav(request: httpx.Request) -> httpx.Response:
    """Serve the WBI key payload used by every signed endpoint."""
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "isLogin": True,
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{SUB_KEY}.png",
                },
            },
        },
    )


def ok(data: object) -> httpx.Response:
    """Wrap a payload in a successful Bilibili envelope.

    Args:
        data: Value of the ``data`` field.

    Returns:
        A mocked 200 response.
    """
    return httpx.Response(200, json={"code": 0, "data": data})


def test_normalize_bvid_accepts_ids_and_urls() -> None:
    """Plain ids, lower-case prefixes and URLs all resolve to one form."""
    assert normalize_bvid("BV1GJ411x7h7") == "BV1GJ411x7h7"
    assert normalize_bvid("bv1GJ411x7h7") == "BV1GJ411x7h7"
    assert normalize_bvid("https://www.bilibili.com/video/BV1GJ411x7h7?p=2") == "BV1GJ411x7h7"


def test_normalize_bvid_preserves_payload_case() -> None:
    """BV payloads are case sensitive, so only the prefix is normalised."""
    assert normalize_bvid("bv1gj411x7h7") == "BV1gj411x7h7"


def test_normalize_bvid_rejects_garbage() -> None:
    """A useless input produces an actionable hint."""
    with pytest.raises(BilibiliError, match="无法识别 BV 号"):
        normalize_bvid("definitely-not-a-video")


def test_search_works_without_cookie(make_client: Callable[..., Any]) -> None:
    """Anonymous search succeeds and the Cookie header stays off the wire."""
    seen: list[httpx.Request] = []

    def search(request: httpx.Request) -> httpx.Response:
        seen.append(request)
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

    client = make_client(route(nav=nav, search=search), cookie="")
    videos = _run(client.search_videos("线代", 1))

    assert videos[0]["bvid"] == "BV1xx411c7mD"
    assert "cookie" not in seen[0].headers


def test_search_412_without_cookie_suggests_cookie(
    make_client: Callable[..., Any],
) -> None:
    """Anonymous risk-control blocks become setup instructions."""
    client = make_client(
        route(nav=nav, search=lambda _: httpx.Response(412)),
        cookie="",
    )

    with pytest.raises(BilibiliError, match="BILIBILI_COOKIE"):
        _run(client.search_videos("线代", 1))


def test_search_parses_results_and_signs_request(make_client: Callable[..., Any]) -> None:
    """Search strips highlight markup and sends wts/w_rid."""
    seen: list[httpx.Request] = []

    def search(request: httpx.Request) -> httpx.Response:
        seen.append(request)
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

    client = make_client(route(nav=nav, search=search))
    videos = _run(client.search_videos("线代", 5))

    assert videos == [
        {
            "title": "线性代数 期末速成",
            "author": "某老师",
            "bvid": "BV1xx411c7mD",
            "duration": "4:12:30",
            "play": 1205000,
            "url": "https://www.bilibili.com/video/BV1xx411c7mD",
        }
    ]
    query = seen[0].url.params
    assert "w_rid" in query
    assert "wts" in query


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion for synchronous assertions.

    Args:
        coro: Coroutine to execute.

    Returns:
        Its result.
    """
    return asyncio.run(coro)


def test_wbi_keys_are_cached(make_client: Callable[..., Any]) -> None:
    """Two signed calls must hit the nav endpoint only once."""
    nav_calls: list[httpx.Request] = []

    def counting_nav(request: httpx.Request) -> httpx.Response:
        nav_calls.append(request)
        return nav(request)

    client = make_client(
        route(
            nav=counting_nav,
            search=lambda _: ok(
                {
                    "result": [
                        {
                            "title": "t",
                            "author": "a",
                            "bvid": "BV1xx411c7mD",
                            "duration": "1:00",
                            "play": 1,
                        }
                    ]
                }
            ),
        )
    )

    _run(client.search_videos("a", 1))
    _run(client.search_videos("b", 1))

    assert len(nav_calls) == 1


def test_http_412_points_at_cookie(make_client: Callable[..., Any]) -> None:
    """HTTP-level rate limiting is explained in terms of the Cookie."""

    def blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(412, text="blocked")

    client = make_client(route(nav=blocked))
    with pytest.raises(BilibiliError, match="412"):
        _run(client.search_videos("线代", 1))


def test_business_error_code_is_mapped(make_client: Callable[..., Any]) -> None:
    """Login errors from the envelope become actionable text."""

    def not_logged_in(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": -101, "message": "账号未登录"})

    client = make_client(route(nav=nav, search=not_logged_in))
    with pytest.raises(BilibiliError) as excinfo:
        _run(client.search_videos("线代", 1))

    assert excinfo.value.code == -101
    assert "Cookie" in str(excinfo.value)


def test_timeout_is_reported(make_client: Callable[..., Any]) -> None:
    """Transport timeouts mention the 10 second budget."""

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(route(nav=slow))
    with pytest.raises(BilibiliError, match="超时"):
        _run(client.search_videos("线代", 1))


def test_non_json_body_is_reported(make_client: Callable[..., Any]) -> None:
    """An anti-bot HTML page does not leak a JSON traceback."""

    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>risk control</html>")

    client = make_client(route(nav=html))
    with pytest.raises(BilibiliError, match="非 JSON"):
        _run(client.search_videos("线代", 1))


def test_get_video_info_parses_metadata(make_client: Callable[..., Any]) -> None:
    """Metadata, counters and parts are normalised."""
    client = make_client(route(view=lambda _: ok(VIEW_PAYLOAD)))
    info = _run(client.get_video_info("https://www.bilibili.com/video/BV1GJ411x7h7"))

    assert info["bvid"] == "BV1GJ411x7h7"
    assert info["aid"] == 8047632
    assert info["duration_text"] == "1:02:03"
    assert info["stats"]["like"] == 89000
    assert [part["cid"] for part in info["pages"]] == [111, 222]
    assert info["owner"] == "3Blue1Brown"


def test_get_subtitles_formats_and_filters(make_client: Callable[..., Any]) -> None:
    """Lines are timestamped and the window is honoured."""

    def player(request: httpx.Request) -> httpx.Response:
        return ok(
            {
                "subtitle": {
                    "subtitles": [
                        {
                            "lan": "zh-Hans",
                            "lan_doc": "中文（自动生成）",
                            "subtitle_url": "//aisubtitle.hdslb.com/bfs/ai/x.json",
                        }
                    ]
                }
            }
        )

    def cdn(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "body": [
                    {"from": 0.0, "to": 3.0, "content": "第一句"},
                    {"from": 61.5, "to": 64.0, "content": "第二句"},
                ]
            },
        )

    client = make_client(route(nav=nav, view=lambda _: ok(VIEW_PAYLOAD), player=player, cdn=cdn))
    payload = _run(client.get_subtitles("BV1GJ411x7h7", 1, 60, 120))

    assert payload["available"] is True
    assert payload["lines"] == ["[01:01] 第二句"]
    assert payload["lan_doc"] == "中文（自动生成）"
    assert payload["page"] == 1


def test_get_subtitles_without_track_explains_why(make_client: Callable[..., Any]) -> None:
    """Missing subtitles produce the documented hint, not an exception."""

    def player(request: httpx.Request) -> httpx.Response:
        return ok({"subtitle": {"subtitles": []}})

    client = make_client(route(nav=nav, view=lambda _: ok(VIEW_PAYLOAD), player=player))
    payload = _run(client.get_subtitles("BV1GJ411x7h7"))

    assert payload["available"] is False
    assert "没有可用字幕" in payload["reason"]
    assert payload["lines"] == []


def test_get_subtitles_truncates_long_tracks(
    make_client: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracks longer than the limit are trimmed and flagged."""
    monkeypatch.setattr(bilibili_api, "MAX_SUBTITLE_LINES", 2)

    def player(request: httpx.Request) -> httpx.Response:
        return ok(
            {
                "subtitle": {
                    "subtitles": [
                        {
                            "lan": "ai-zh",
                            "lan_doc": "AI",
                            "subtitle_url": "https://aisubtitle.hdslb.com/bfs/ai/x.json",
                        }
                    ]
                }
            }
        )

    def cdn(request: httpx.Request) -> httpx.Response:
        body = [
            {"from": float(index), "to": float(index) + 1, "content": f"第{index}句"}
            for index in range(5)
        ]
        return httpx.Response(200, json={"body": body})

    client = make_client(route(nav=nav, view=lambda _: ok(VIEW_PAYLOAD), player=player, cdn=cdn))
    payload = _run(client.get_subtitles("BV1GJ411x7h7"))

    assert payload["truncated"] is True
    assert payload["total_lines"] == 5
    assert len(payload["lines"]) == 2


def test_get_subtitles_rejects_out_of_range_page(make_client: Callable[..., Any]) -> None:
    """The error tells the model how many parts exist."""
    client = make_client(route(view=lambda _: ok(VIEW_PAYLOAD)))
    with pytest.raises(BilibiliError, match="分P"):
        _run(client.get_subtitles("BV1GJ411x7h7", page=9))


def test_get_hot_comments_sorted_by_likes(make_client: Callable[..., Any]) -> None:
    """Comments come back ordered by like count."""

    def reply(request: httpx.Request) -> httpx.Response:
        return ok(
            {
                "replies": [
                    {"member": {"uname": "a"}, "like": 5, "content": {"message": "low"}},
                    {"member": {"uname": "b"}, "like": 99, "content": {"message": "high"}},
                ],
                "page": {"count": 2},
            }
        )

    client = make_client(route(view=lambda _: ok(VIEW_PAYLOAD), reply=reply))
    payload = _run(client.get_hot_comments("BV1GJ411x7h7", 5))

    assert [comment["user"] for comment in payload["comments"]] == ["b", "a"]
    assert payload["total"] == 2


def test_get_hot_comments_handles_closed_section(make_client: Callable[..., Any]) -> None:
    """A closed comment section yields an empty list, not a crash."""

    def reply(request: httpx.Request) -> httpx.Response:
        return ok({"replies": None, "page": {"count": 0}})

    client = make_client(route(view=lambda _: ok(VIEW_PAYLOAD), reply=reply))
    payload = _run(client.get_hot_comments("BV1GJ411x7h7"))

    assert payload["comments"] == []
    assert payload["comments_open"] is False
