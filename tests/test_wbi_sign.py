"""Tests for :mod:`bilibili_learning_mcp.wbi_sign`."""

from __future__ import annotations

from bilibili_learning_mcp.wbi_sign import (
    extract_key_from_url,
    mixin_key,
    sanitize_value,
    sign_params,
)

IMG_KEY = "7cd084941338484aae1ad9425b84077c"
SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"
FIXED_TS = 1702204169


def test_mixin_key_matches_documented_vector() -> None:
    """The permutation table must reproduce the key from the API docs."""
    assert mixin_key(IMG_KEY + SUB_KEY) == "ea1db124af3c7062474693fa704f4ff8"


def test_extract_key_from_url_strips_path_and_extension() -> None:
    """Only the bare file name is used as key material."""
    url = f"https://i0.hdslb.com/bfs/wbi/{IMG_KEY}.png"
    assert extract_key_from_url(url) == IMG_KEY
    assert extract_key_from_url(f"//i0.hdslb.com/bfs/wbi/{SUB_KEY}.png") == SUB_KEY


def test_extract_key_from_url_tolerates_query_string() -> None:
    """Query strings and fragments must not leak into the key."""
    url = f"https://i0.hdslb.com/bfs/wbi/{IMG_KEY}.png?x=1#frag"
    assert extract_key_from_url(url) == IMG_KEY


def test_sanitize_value_removes_protocol_reserved_characters() -> None:
    """Bilibili strips !'()* before signing and sending."""
    assert sanitize_value("a!b'c(d)e*f") == "abcdef"


def test_sign_params_adds_sorted_params_and_signature() -> None:
    """Signing is deterministic for a pinned timestamp."""
    signed = sign_params(
        {"foo": "114", "bar": "514", "zab": 1919810},
        IMG_KEY,
        SUB_KEY,
        timestamp=FIXED_TS,
    )

    assert list(signed) == ["bar", "foo", "wts", "zab", "w_rid"]
    assert signed["wts"] == str(FIXED_TS)
    assert signed["w_rid"] == "8f6f2b5b3d485fe1886cec6a0be8c5d4"


def test_sign_params_drops_none_values() -> None:
    """Optional parameters that are unset must not be sent."""
    signed = sign_params({"keyword": "线代", "page": None}, IMG_KEY, SUB_KEY, timestamp=FIXED_TS)
    assert "page" not in signed
    assert signed["keyword"] == "线代"


def test_sign_params_signature_changes_with_parameters() -> None:
    """Different parameters must not share a signature."""
    first = sign_params({"keyword": "a"}, IMG_KEY, SUB_KEY, timestamp=FIXED_TS)
    second = sign_params({"keyword": "b"}, IMG_KEY, SUB_KEY, timestamp=FIXED_TS)
    assert first["w_rid"] != second["w_rid"]