from time import time

import jwt

from sdk.server.livekit_tokens import mint_token


def test_mint_token_scopes_identity_room_permissions_and_ttl() -> None:
    api_secret = "a-test-secret-that-is-safely-over-32-bytes"
    token = mint_token(
        api_key="test-key",
        api_secret=api_secret,
        identity="user",
        room="sess_abc",
        ttl_seconds=300,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    claims = jwt.decode(
        token,
        api_secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )

    assert claims["sub"] == "user"
    assert claims["iss"] == "test-key"
    assert claims["video"] == {
        "roomJoin": True,
        "room": "sess_abc",
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": True,
    }
    assert 295 <= claims["exp"] - time() <= 300
