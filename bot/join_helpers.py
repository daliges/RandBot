import asyncio, re, app_context
from telethon.errors import UserAlreadyParticipantError
from telethon import functions

CHANNEL_LINK_RE = re.compile(r"(?:https?://)?t\.me/(?:joinchat/|\+)?([A-Za-z0-9_+-]+)")

def _extract_channel_link(text: str) -> str | None:
    match = CHANNEL_LINK_RE.search(text or "")
    return match.group(0) if match else None

def _is_invite_link(link: str) -> bool:
    lowered = link.lower()
    return "joinchat" in lowered or "/+" in lowered or lowered.startswith("+") or lowered.startswith("https://t.me/+")

async def _join_channel_async(link: str):
    client = app_context.telethon_client
    if not client:
        raise RuntimeError("Telethon client is unavailable")

    is_invite = _is_invite_link(link)
    try:
        if is_invite:
            invite_hash = link.rstrip("/").split("/")[-1].lstrip("+")
            await client(functions.messages.ImportChatInviteRequest(invite_hash))
        else:
            entity = await client.get_entity(link)
            await client(functions.channels.JoinChannelRequest(entity))
    except UserAlreadyParticipantError:
        pass

    # fetch the entity after joining so callers always receive it
    entity = await client.get_entity(link)
    return entity

def _join_channel(link: str):
    loop = app_context.telethon_loop
    if not loop:
        raise RuntimeError("Telethon loop is unavailable")
    future = asyncio.run_coroutine_threadsafe(_join_channel_async(link), loop)
    return future.result()

async def _forward_media_async(user_id: int, channel_id: int, message_id: int):
    client = app_context.telethon_client
    if not client:
        raise RuntimeError("Telethon client unavailable")
    return await client.forward_messages(
        entity=user_id,
        messages=[message_id],
        from_peer=channel_id
    )

def forward_media_with_telethon(user_id: int, channel_id: int, message_id: int):
    loop = app_context.telethon_loop
    if not loop:
        raise RuntimeError("Telethon loop unavailable")
    future = asyncio.run_coroutine_threadsafe(
        _forward_media_async(user_id, channel_id, message_id),
        loop,
    )
    return future.result()