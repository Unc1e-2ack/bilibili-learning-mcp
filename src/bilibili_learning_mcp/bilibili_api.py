"""Async Bilibili client used by the MCP tools.

This module is intentionally MCP-free: it only knows HTTP, Bilibili's
response envelope and the error messages a model can act on. That keeps it
testable with ``httpx.MockTransport`` and reusable from plain scripts.

All requests are spaced by at least :data:`MIN_REQUEST_INTERVAL` seconds and
nothing is downloaded besides JSON documents already held in memory; the
client never persists video or subtitle content.
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from bilibili_learning_mcp.wbi_sign import extract_key_from_url, sign_params

API_BASE_URL = "https://api.bilibili.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
REFERER = "https://www.bilibili.com/"
REQUEST_TIMEOUT = 10.0
MIN_REQUEST_INTERVAL = 1.0
WBI_KEY_TTL = 6 * 60 * 60
COOKIE_ENV = "BILIBILI_COOKIE"
MAX_SUBTITLE_LINES = 8000

COOKIE_HINT = "请在环境变量 BILIBILI_COOKIE 中配置 B 站登录 Cookie 后重试"
COOKIE_HOWTO = (
    "获取方法：浏览器登录 bilibili.com，打开开发者工具 → Network，随便点一个 "
    "api.bilibili.com 请求，复制请求头里完整的 Cookie 值（至少包含 SESSDATA），"
    "写入 .env 或执行 export BILIBILI_COOKIE='...' 后重启 MCP server。"
)
NO_SUBTITLE_HINT = (
    "该视频没有可用字幕（B站AI字幕需要登录Cookie，且部分视频未生成字幕），"
    "可以改用 get_video_info 获取视频简介了解内容"
)

_ERROR_HINTS: dict[int, str] = {
    -101: "账号未登录或 Cookie 已失效：请重新登录 B 站并更新 BILIBILI_COOKIE。",
    -102: "账号被封禁：请更换一个可用的 B 站账号 Cookie。",
    -352: (
        "被 B 站风控校验拦截（-352）：WBI 签名 key 可能已过期，请稍后重试；"
        "持续失败请更新 Cookie。"
    ),
    -400: "请求参数有误（-400）：请检查 BV 号、分P页码是否正确。",
    -403: "访问被拒绝（-403）：该资源可能要求登录，或当前账号权限不足。",
    -404: "资源不存在（-404）：请确认 BV 号是否正确。",
    -500: "B 站服务器内部错误（-500）：请稍后重试。",
    -509: "请求过于频繁（-509）：请等待几分钟后再试。",
    62002: "该稿件不可见（可能已删除、设为私密或被下架）。",
    62004: "该稿件正在审核中，暂时无法访问。",
    62012: "该稿件仅 UP 主自己可见。",
}

_BV_PATTERN = re.compile(r"bv([0-9a-z]{10})", re.IGNORECASE)


class BilibiliError(Exception):
    """Error whose message is meant to be shown to the LLM verbatim.

    Args:
        message: Actionable description telling the model what to do next.
        code: Bilibili business code, when the failure came from the API.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """Store the message and the optional business code.

        Args:
            message: Actionable description for the model.
            code: Bilibili business code when the failure came from the API.
        """
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_bvid(value: str) -> str:
    """Extract a canonical BV id from a raw id or a full video URL.

    Bilibili BV ids are case sensitive after the ``BV`` prefix, so only the
    prefix is upper-cased; the payload is preserved exactly as given.

    Args:
        value: ``BV1GJ411x7h7``, ``bv1gj411x7h7`` or any URL containing it.

    Returns:
        The normalised ``BV...`` identifier.

    Raises:
        BilibiliError: If no BV id can be found in ``value``.
    """
    match = _BV_PATTERN.search(value or "")
    if match is None:
        raise BilibiliError(
            "无法识别 BV 号：请传入形如 BV1GJ411x7h7 的 BV 号，"
            "或包含 BV 号的完整链接（如 https://www.bilibili.com/video/BV1GJ411x7h7）。"
            "注意 BV 号主体区分大小写，请勿手动改写。"
        )
    return f"BV{match.group(1)}"


def strip_html(text: str) -> str:
    """Remove the ``<em>`` highlight markup Bilibili adds to search results.

    Args:
        text: Raw title that may contain HTML tags and entities.

    Returns:
        Plain text with entities unescaped and tags removed.
    """
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def format_duration(seconds: float) -> str:
    """Format a duration as ``mm:ss`` or ``h:mm:ss``.

    Args:
        seconds: Duration in seconds; negative values are clamped to zero.

    Returns:
        Human readable duration without brackets.
    """
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_timestamp(seconds: float) -> str:
    """Format a subtitle offset as ``[mm:ss]``.

    Args:
        seconds: Offset in seconds.

    Returns:
        The bracketed timestamp used in subtitle lines.
    """
    return f"[{format_duration(seconds)}]"


def _to_int(value: object) -> int:
    """Convert a loosely typed API value to ``int``, defaulting to 0.

    Args:
        value: Number or numeric string returned by the API.

    Returns:
        The parsed integer, or 0 when parsing fails.
    """
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _pick_subtitle(tracks: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Choose the most useful subtitle track.

    Human Chinese subtitles win over AI ones, which win over any other
    language; ties keep the server-provided order.

    Args:
        tracks: ``data.subtitle.subtitles`` from the player endpoint.

    Returns:
        The selected track.
    """

    def rank(track: Mapping[str, Any]) -> int:
        language = str(track.get("lan") or "").lower()
        if language.startswith("zh") and "ai" not in language:
            return 0
        if "ai" in language:
            return 1
        return 2

    return min(tracks, key=rank)


class BilibiliClient:
    """Rate-limited async client for Bilibili's public web APIs.

    Args:
        cookie: Cookie header value; defaults to ``$BILIBILI_COOKIE``.
        transport: Custom ``httpx`` transport, used by tests.
        min_interval: Minimum seconds between two HTTP requests.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        *,
        cookie: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Create the client and its HTTP connection pool.

        Args:
            cookie: Cookie header value; read from the environment when None.
            transport: Custom transport, used to mock HTTP in tests.
            min_interval: Minimum seconds between two requests.
            timeout: Per-request timeout in seconds.
        """
        self._cookie = cookie
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._wbi_keys: tuple[str, str, float] | None = None
        self._http = httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": REFERER,
                "Accept": "application/json, text/plain, */*",
            },
        )

    @property
    def cookie_configured(self) -> bool:
        """Whether a non-empty Cookie is available.

        Returns:
            ``True`` when the constructor or the environment provides one.
        """
        return self._resolve_cookie(required=False) is not None

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        await self._http.aclose()

    def _resolve_cookie(self, *, required: bool = True) -> str | None:
        """Read the Cookie from the constructor or the environment.

        Args:
            required: Raise instead of returning ``None`` when it is absent.

        Returns:
            The Cookie header value, or ``None`` when not configured.

        Raises:
            BilibiliError: If ``required`` is true and no Cookie is set.
        """
        raw = self._cookie if self._cookie is not None else os.environ.get(COOKIE_ENV, "")
        cookie = (raw or "").strip()
        if cookie:
            return cookie
        if required:
            raise BilibiliError(f"未配置 B 站 Cookie：{COOKIE_HINT}。{COOKIE_HOWTO}")
        return None

    async def _throttle(self) -> None:
        """Sleep so consecutive requests stay ``min_interval`` apart."""
        if self._min_interval <= 0:
            return
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_at = time.monotonic()

    async def _get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        cookie: str | None = None,
    ) -> httpx.Response:
        """Perform a rate-limited GET, translating transport failures.

        Args:
            url: Path relative to ``api.bilibili.com`` or an absolute URL.
            params: Query parameters.
            cookie: Cookie header value; omitted when ``None`` so the Cookie is
                never forwarded to third-party hosts such as subtitle CDNs.

        Returns:
            The raw response.

        Raises:
            BilibiliError: On timeout or connection failure.
        """
        await self._throttle()
        headers = {"Cookie": cookie} if cookie else None
        try:
            return await self._http.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise BilibiliError(
                "请求 B 站超时（10 秒）：可能是网络不稳定或被限流。请稍后重试。"
            ) from exc
        except httpx.HTTPError as exc:
            raise BilibiliError(
                f"无法连接 B 站 API（{exc.__class__.__name__}）：请检查网络或代理设置后重试。"
            ) from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Translate HTTP status codes into actionable errors.

        Args:
            response: Response returned by :meth:`_get`.

        Raises:
            BilibiliError: On 4xx/5xx responses.
        """
        if response.status_code == 412:
            raise BilibiliError(
                f"B 站返回 HTTP 412（风控拦截）：{COOKIE_HINT}。{COOKIE_HOWTO}"
                " 若已配置 Cookie，请降低调用频率或稍后重试。"
            )
        if response.status_code >= 400:
            raise BilibiliError(
                f"B 站接口返回 HTTP {response.status_code}：请稍后重试，"
                "持续失败时请检查网络是否被拦截。"
            )

    @staticmethod
    def _decode_json(response: httpx.Response, *, hint: str) -> dict[str, Any]:
        """Parse a JSON object body, mapping decode errors to a hint.

        Args:
            response: Response to decode.
            hint: Actionable suffix explaining how to recover.

        Returns:
            The decoded object.

        Raises:
            BilibiliError: If the body is not a JSON object.
        """
        try:
            payload = response.json()
        except ValueError as exc:
            raise BilibiliError(f"B 站返回了非 JSON 内容（通常是被风控页面拦截）。{hint}") from exc
        if not isinstance(payload, dict):
            raise BilibiliError(f"B 站返回的数据格式异常。{hint}")
        return payload

    async def _get_api(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        require_cookie: bool = False,
        signed: bool = False,
        allowed_codes: frozenset[int] | None = None,
    ) -> dict[str, Any]:
        """Call a Bilibili JSON endpoint and return its ``data`` object.

        Args:
            path: API path such as ``/x/web-interface/view``.
            params: Business query parameters.
            require_cookie: Fail fast when no Cookie is configured.
            signed: Apply WBI signing before sending.
            allowed_codes: Non-zero business codes to tolerate.

        Returns:
            The ``data`` field of the response; an empty dict when absent.

        Raises:
            BilibiliError: On transport, HTTP or business-level failures.
        """
        cookie = self._resolve_cookie(required=require_cookie)
        query: Mapping[str, Any] | None = params
        if signed:
            img_key, sub_key = await self._get_wbi_keys()
            query = sign_params(params or {}, img_key, sub_key)

        response = await self._get(path, query, cookie=cookie)
        self._raise_for_status(response)
        payload = self._decode_json(
            response, hint=f"请检查 Cookie 是否有效，或稍后重试。{COOKIE_HOWTO}"
        )

        code = _to_int(payload.get("code", -1))
        tolerated = allowed_codes or frozenset()
        if code != 0 and code not in tolerated:
            api_message = str(payload.get("message") or "").strip()
            detail = f"（接口原文：{api_message}）" if api_message else ""
            hint = _ERROR_HINTS.get(code, f"B 站接口返回错误码 {code}：请稍后重试。")
            raise BilibiliError(f"{hint}{detail}", code=code)

        data = payload.get("data")
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise BilibiliError("B 站返回的 data 字段格式异常：请稍后重试。")
        return data

    async def _get_wbi_keys(self) -> tuple[str, str]:
        """Return cached WBI keys, refreshing them when they expire.

        Returns:
            The ``(img_key, sub_key)`` pair used for signing.

        Raises:
            BilibiliError: If the nav endpoint cannot provide usable keys.
        """
        cached = self._wbi_keys
        if cached is not None and time.monotonic() < cached[2]:
            return cached[0], cached[1]

        data = await self._get_api("/x/web-interface/nav", allowed_codes=frozenset({-101}))
        wbi = data.get("wbi_img") or {}
        img_key = extract_key_from_url(str(wbi.get("img_url") or ""))
        sub_key = extract_key_from_url(str(wbi.get("sub_url") or ""))
        if len(img_key) < 16 or len(sub_key) < 16:
            raise BilibiliError(
                "无法从 nav 接口解析 WBI 签名 key（可能被风控）：请稍后重试，"
                "若持续失败请更新 BILIBILI_COOKIE。"
            )
        self._wbi_keys = (img_key, sub_key, time.monotonic() + WBI_KEY_TTL)
        return img_key, sub_key
    async def search_videos(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search Bilibili videos by keyword.

        Args:
            keyword: Search terms, e.g. ``"线性代数 期末速成"``.
            limit: Maximum number of results, clamped to ``1..50``.

        Returns:
            Normalised summaries ordered by Bilibili relevance.

        Raises:
            BilibiliError: When the keyword is empty, the Cookie is missing or
                the request fails.
        """
        keyword = keyword.strip()
        if not keyword:
            raise BilibiliError(
                "keyword 不能为空：请传入要搜索的关键词，例如「线性代数 期末速成」。"
            )

        page_size = max(1, min(limit, 50))
        data = await self._get_api(
            "/x/web-interface/wbi/search/type",
            {
                "search_type": "video",
                "keyword": keyword,
                "page": 1,
                "page_size": page_size,
            },
            require_cookie=True,
            signed=True,
        )

        raw_results = data.get("result")
        if not isinstance(raw_results, list) or not raw_results:
            raise BilibiliError(
                f"没有搜到「{keyword}」相关的视频：请换一个更常见的关键词，"
                f"或确认 Cookie 是否仍然有效。{COOKIE_HINT}。"
            )

        videos: list[dict[str, Any]] = []
        for item in raw_results[:page_size]:
            if not isinstance(item, dict):
                continue
            bvid = str(item.get("bvid") or "")
            if not bvid:
                continue
            videos.append(
                {
                    "title": strip_html(str(item.get("title") or "")),
                    "author": str(item.get("author") or ""),
                    "bvid": bvid,
                    "duration": str(item.get("duration") or ""),
                    "play": _to_int(item.get("play")),
                    "url": f"https://www.bilibili.com/video/{bvid}",
                }
            )
        if not videos:
            raise BilibiliError(f"「{keyword}」没有返回可解析的视频结果：请调整关键词后重试。")
        return videos

    async def get_video_info(self, bv_id: str) -> dict[str, Any]:
        """Fetch metadata for one video, including every part (分P).

        Args:
            bv_id: BV id or a URL containing it.

        Returns:
            Normalised metadata containing ``aid``, ``pages`` and counters.

        Raises:
            BilibiliError: When the BV id is invalid or the request fails.
        """
        data = await self._get_api("/x/web-interface/view", {"bvid": normalize_bvid(bv_id)})

        pages: list[dict[str, Any]] = []
        raw_pages = data.get("pages")
        if isinstance(raw_pages, list):
            for index, page in enumerate(raw_pages, start=1):
                if not isinstance(page, dict):
                    continue
                pages.append(
                    {
                        "page": _to_int(page.get("page")) or index,
                        "cid": _to_int(page.get("cid")),
                        "title": str(page.get("part") or ""),
                        "duration_sec": _to_int(page.get("duration")),
                    }
                )

        stat = data.get("stat") if isinstance(data.get("stat"), dict) else {}
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        bvid = str(data.get("bvid") or normalize_bvid(bv_id))
        duration = _to_int(data.get("duration"))

        return {
            "bvid": bvid,
            "aid": _to_int(data.get("aid")),
            "title": str(data.get("title") or ""),
            "desc": str(data.get("desc") or ""),
            "owner": str(owner.get("name") or ""),
            "duration_sec": duration,
            "duration_text": format_duration(duration),
            "stats": {
                "view": _to_int(stat.get("view")),
                "like": _to_int(stat.get("like")),
                "favorite": _to_int(stat.get("favorite")),
                "coin": _to_int(stat.get("coin")),
                "reply": _to_int(stat.get("reply")),
            },
            "pages": pages,
            "pubdate": _to_int(data.get("pubdate")),
            "url": f"https://www.bilibili.com/video/{bvid}",
        }

    async def get_subtitles(
        self,
        bv_id: str,
        page: int = 1,
        start_sec: int | None = None,
        end_sec: int | None = None,
    ) -> dict[str, Any]:
        """Fetch the subtitle track of one part as timestamped lines.

        Args:
            bv_id: BV id or a URL containing it.
            page: One-based part index; defaults to the first part.
            start_sec: Keep lines starting at or after this offset.
            end_sec: Keep lines starting at or before this offset.

        Returns:
            A dict with ``available``, ``lines`` (``[mm:ss] text``),
            ``total_lines``, ``truncated`` and the chosen track metadata.

        Raises:
            BilibiliError: When metadata is invalid or a request fails.
        """
        info = await self.get_video_info(bv_id)
        pages = info["pages"]
        if not pages:
            raise BilibiliError("该视频没有分P信息，无法定位字幕：请改用 get_video_info 查看简介。")
        if page < 1 or page > len(pages):
            raise BilibiliError(
                f"page 超出范围：该视频共有 {len(pages)} 个分P，"
                f"请传入 1 到 {len(pages)} 之间的整数。"
            )

        part = pages[page - 1]
        cid = part["cid"]
        data = await self._get_api(
            "/x/player/wbi/v2",
            {"bvid": info["bvid"], "cid": cid},
            signed=True,
        )

        subtitle = data.get("subtitle") if isinstance(data.get("subtitle"), dict) else {}
        tracks = subtitle.get("subtitles") if isinstance(subtitle.get("subtitles"), list) else []
        tracks = [
            track
            for track in tracks
            if isinstance(track, dict) and track.get("subtitle_url")
        ]
        if not tracks:
            return {
                "available": False,
                "bvid": info["bvid"],
                "page": page,
                "cid": cid,
                "reason": NO_SUBTITLE_HINT,
                "lines": [],
                "total_lines": 0,
                "truncated": False,
            }

        track = _pick_subtitle(tracks)
        url = str(track.get("subtitle_url") or "")
        if url.startswith("//"):
            url = f"https:{url}"
        payload = await self._get_raw_json(url)

        body = payload.get("body")
        if not isinstance(body, list):
            raise BilibiliError("字幕文件结构异常（缺少 body 数组）：请换一个视频重试。")

        lines: list[str] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            start = float(item.get("from") or 0.0)
            if start_sec is not None and start < start_sec:
                continue
            if end_sec is not None and start > end_sec:
                continue
            text = str(item.get("content") or "").replace("\n", " ").strip()
            if not text:
                continue
            lines.append(f"{format_timestamp(start)} {text}")

        total_lines = len(lines)
        truncated = total_lines > MAX_SUBTITLE_LINES
        if truncated:
            lines = lines[:MAX_SUBTITLE_LINES]

        return {
            "available": True,
            "bvid": info["bvid"],
            "page": page,
            "page_title": part["title"],
            "cid": cid,
            "lan": str(track.get("lan") or ""),
            "lan_doc": str(track.get("lan_doc") or ""),
            "lines": lines,
            "total_lines": total_lines,
            "truncated": truncated,
            "truncate_limit": MAX_SUBTITLE_LINES,
            "window": {"start_sec": start_sec, "end_sec": end_sec},
        }

    async def get_hot_comments(self, bv_id: str, limit: int = 10) -> dict[str, Any]:
        """Fetch the most liked comments of a video.

        Args:
            bv_id: BV id or a URL containing it.
            limit: Number of comments to return, clamped to ``1..49``.

        Returns:
            A dict with ``comments`` sorted by like count and the total count.

        Raises:
            BilibiliError: When metadata is invalid or the request fails.
        """
        info = await self.get_video_info(bv_id)
        aid = info["aid"]
        if aid <= 0:
            raise BilibiliError("无法获取该视频的 aid，评论区不可用：请确认 BV 号是否正确。")

        page_size = max(1, min(max(limit * 2, 20), 49))
        data = await self._get_api(
            "/x/v2/reply",
            {"type": 1, "oid": aid, "sort": 1, "pn": 1, "ps": page_size},
        )

        raw_replies = data.get("replies")
        comments: list[dict[str, Any]] = []
        if isinstance(raw_replies, list):
            for reply in raw_replies:
                if not isinstance(reply, dict):
                    continue
                member = reply.get("member") if isinstance(reply.get("member"), dict) else {}
                content = reply.get("content") if isinstance(reply.get("content"), dict) else {}
                message = str(content.get("message") or "").strip()
                if not message:
                    continue
                comments.append(
                    {
                        "user": str(member.get("uname") or "匿名用户"),
                        "like": _to_int(reply.get("like")),
                        "content": message,
                    }
                )

        comments.sort(key=lambda comment: comment["like"], reverse=True)
        page_info = data.get("page") if isinstance(data.get("page"), dict) else {}

        return {
            "bvid": info["bvid"],
            "aid": aid,
            "total": _to_int(page_info.get("count")),
            "returned": len(comments[: max(1, limit)]),
            "comments": comments[: max(1, limit)],
            "comments_open": bool(raw_replies),
        }

    async def _get_raw_json(self, url: str) -> dict[str, Any]:
        """GET an absolute JSON URL that does not use the Bilibili envelope.

        Args:
            url: Absolute subtitle URL served by Bilibili's CDN.

        Returns:
            The decoded JSON object.

        Raises:
            BilibiliError: On transport, HTTP or decoding failures.
        """
        response = await self._get(url)
        self._raise_for_status(response)
        return self._decode_json(
            response,
            hint="字幕文件可能已失效：请换一个视频重试，或改用 get_video_info 查看简介。",
        )


_default_client: BilibiliClient | None = None


def get_client() -> BilibiliClient:
    """Return the process-wide client, creating it on first use.

    Returns:
        The shared :class:`BilibiliClient` instance.
    """
    global _default_client
    if _default_client is None:
        _default_client = BilibiliClient()
    return _default_client


def set_client(client: BilibiliClient | None) -> None:
    """Replace the shared client, mainly for tests.

    Args:
        client: New shared client, or ``None`` to reset it.
    """
    global _default_client
    _default_client = client


async def search_videos(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Bilibili videos using the shared client.

    Args:
        keyword: Search terms.
        limit: Maximum number of results.

    Returns:
        Normalised video summaries.
    """
    return await get_client().search_videos(keyword, limit)


async def get_video_info(bv_id: str) -> dict[str, Any]:
    """Fetch one video's metadata using the shared client.

    Args:
        bv_id: BV id or a URL containing it.

    Returns:
        Normalised metadata.
    """
    return await get_client().get_video_info(bv_id)


async def get_subtitles(
    bv_id: str,
    page: int = 1,
    start_sec: int | None = None,
    end_sec: int | None = None,
) -> dict[str, Any]:
    """Fetch one video's subtitles using the shared client.

    Args:
        bv_id: BV id or a URL containing it.
        page: One-based part index.
        start_sec: Keep lines starting at or after this offset.
        end_sec: Keep lines starting at or before this offset.

    Returns:
        The subtitle payload described by :meth:`BilibiliClient.get_subtitles`.
    """
    return await get_client().get_subtitles(bv_id, page, start_sec, end_sec)


async def get_hot_comments(bv_id: str, limit: int = 10) -> dict[str, Any]:
    """Fetch a video's most liked comments using the shared client.

    Args:
        bv_id: BV id or a URL containing it.
        limit: Number of comments to return.

    Returns:
        The comment payload described by :meth:`BilibiliClient.get_hot_comments`.
    """
    return await get_client().get_hot_comments(bv_id, limit)