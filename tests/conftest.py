"""Shared fixtures for the test suite."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from bilibili_learning_mcp.bilibili_api import BilibiliClient

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def make_client() -> Callable[..., BilibiliClient]:
    """Build clients backed by an ``httpx.MockTransport``.

    Returns:
        A factory ``make_client(handler, cookie=..., min_interval=0)``.
    """

    def factory(
        handler: Handler,
        *,
        cookie: str = "SESSDATA=test",
        min_interval: float = 0.0,
    ) -> BilibiliClient:
        return BilibiliClient(
            cookie=cookie,
            transport=httpx.MockTransport(handler),
            min_interval=min_interval,
        )

    return factory
