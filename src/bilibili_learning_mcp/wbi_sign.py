"""WBI request signing for Bilibili web endpoints.

Many ``/x/web-interface/wbi/*`` endpoints reject unsigned requests. Bilibili
derives the signing key from the two WBI images returned by
``GET https://api.bilibili.com/x/web-interface/nav``:

1. take the file name of ``img_url`` and ``sub_url`` without the extension;
2. concatenate ``img_key + sub_key`` (64 characters);
3. permute them through :data:`MIXIN_KEY_ENC_TAB` and keep 32 characters;
4. append ``wts`` (unix time) to the query, sort the parameters, urlencode;
5. ``w_rid = md5(query + mixin_key)``.

Reference: https://github.com/SocialSisterYi/bilibili-API-collect (WBI 绛惧悕).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from urllib.parse import urlencode, urlparse

MIXIN_KEY_ENC_TAB: tuple[int, ...] = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)
"""Permutation applied to ``img_key + sub_key`` (64 chars -> 32 chars)."""

MIXIN_KEY_LENGTH = 32

_UNSAFE_CHARS = "!'()*"


def extract_key_from_url(url: str) -> str:
    """Extract a WBI key (``img_key`` / ``sub_key``) from a nav image URL.

    Args:
        url: Absolute or protocol-relative URL such as
            ``https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png``.

    Returns:
        The file name without directory and extension, e.g.
        ``7cd084941338484aae1ad9425b84077c``.
    """
    file_name = urlparse(url).path.rsplit("/", 1)[-1]
    return file_name.split(".", 1)[0]


def mixin_key(orig: str) -> str:
    """Build the 32-character mixed key from ``img_key + sub_key``.

    Args:
        orig: Concatenation of the image key and the sub key (64 chars).

    Returns:
        The permuted, truncated key used as the md5 salt.
    """
    return "".join(orig[index] for index in MIXIN_KEY_ENC_TAB)[:MIXIN_KEY_LENGTH]


def sanitize_value(value: object) -> str:
    """Remove characters Bilibili strips before signing.

    Args:
        value: Any query value; it is converted with :func:`str` first.

    Returns:
        The string without ``!'()*``.
    """
    return "".join(char for char in str(value) if char not in _UNSAFE_CHARS)


def sign_params(
    params: Mapping[str, object],
    img_key: str,
    sub_key: str,
    *,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Sign query parameters for a WBI endpoint.

    Args:
        params: Business parameters, e.g. ``{"keyword": "绾挎€т唬鏁?}``.
        img_key: Key extracted from ``data.wbi_img.img_url``.
        sub_key: Key extracted from ``data.wbi_img.sub_url``.
        timestamp: Unix seconds for ``wts``; defaults to the current time and
            exists so tests can pin the signature.

    Returns:
        A new dict containing the sanitised, key-sorted parameters plus
        ``wts`` and ``w_rid``, ready to be passed to ``httpx`` as ``params``.
    """
    signed: dict[str, str] = {"wts": str(timestamp if timestamp is not None else int(time.time()))}
    for key, value in params.items():
        if value is None:
            continue
        signed[key] = sanitize_value(value)

    ordered = dict(sorted(signed.items()))
    query = urlencode(ordered)
    salt = mixin_key(img_key + sub_key)
    digest = hashlib.md5((query + salt).encode()).hexdigest()
    ordered["w_rid"] = digest
    return ordered