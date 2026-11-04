"""`without_key_ids`: the random `kid` of a log row does not fail a scan for a short word.

The `kid` is 43 random base64url characters. The word "eyJ" is in one by chance (about 1 in 6000).
"""

from __future__ import annotations

import pytest

from tests.s2.conftest import without_key_ids

KID = "8mvFLMXL3w-WNR0cXeZ-IzDTwme9_qlbRQTLXS2KjWs"  # 43 characters
KID_WITH_EYJ = "eyJ" + KID[3:]


def test_a_kid_with_eyj_is_removed() -> None:
    text = f'{{"signature": "verified keyid={KID_WITH_EYJ}"}}'
    assert "eyJ" in text
    assert without_key_ids(text) == '{"signature": "verified keyid="}'


def test_text_without_keyid_is_not_changed() -> None:
    assert without_key_ids('{"a": "token eyJhbGciOi"}') == '{"a": "token eyJhbGciOi"}'


def test_other_text_stays_so_a_scan_still_finds_it() -> None:
    text = f"verified keyid={KID} and eyJhbGciOiJFUzI1NiJ9.x.y and token"
    out = without_key_ids(text)
    assert "eyJ" in out and "token" in out


@pytest.mark.parametrize(
    "value",
    ["", "short", KID + "x", KID[:-1], "eyJhbGciOiJFUzI1NiJ9.e30.sig", "a b" + KID],
)
def test_a_keyid_value_that_is_not_a_thumbprint_fails(value: str) -> None:
    with pytest.raises(AssertionError, match="bad keyid"):
        without_key_ids(f"verified keyid={value}")
