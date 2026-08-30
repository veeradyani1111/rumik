from __future__ import annotations

from datetime import timedelta

from livekit import api


def mint_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    ttl_seconds: int,
    can_publish: bool,
    can_subscribe: bool,
    can_publish_data: bool,
) -> str:
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
        can_publish_data=can_publish_data,
    )
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(seconds=ttl_seconds))
        .with_grants(grants)
        .to_jwt()
    )
