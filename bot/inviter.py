import asyncio
import app_context
from telebot import TeleBot
from telebot.apihelper import ApiException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telethon import errors as telethon_errors, functions

# Function to send a message with a deep link to the channel
def send_channel_message_with_deep_link(bot: TeleBot, channel_id: int) -> None:
    bot_username = bot.get_me().username
    deep_link_url = f"https://t.me/{bot_username}?start=channel_{channel_id}"

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Interact with the Bot", url=deep_link_url)
    )

    bot.send_message(
        channel_id,
        "Hello! To get random media from the channel, please click the button below to start a private chat.",
        reply_markup=keyboard
    )

def ensure_mapping_account_added(channel_id: int, bot: TeleBot) -> bool:
    loop = app_context.telethon_loop
    client = app_context.telethon_client
    if not loop or not client:
        print("Telethon client is not ready; helper account cannot be invited.")
        return False

    async def _already_present() -> bool:
        try:
            await client.get_entity(channel_id)
            return True
        except (ValueError, telethon_errors.rpcerrorlist.ChannelPrivateError):
            return False

    if asyncio.run_coroutine_threadsafe(_already_present(), loop).result():
        return True

    try:
        invite = bot.create_chat_invite_link(
            channel_id,
            name="RandBot helper access",
            creates_join_request=False,
        )
    except ApiException as api_exc:
        print(f"Failed to create invite link for {channel_id}: {api_exc}")
        bot.send_message(
            channel_id,
            "I need the 'Add Users' permission to invite my helper account. "
            "Please grant that permission and try again.",
        )
        return False

    invite_hash = _extract_invite_hash(invite.invite_link)

    async def _join_via_invite() -> bool:
        try:
            await client(functions.messages.ImportChatInviteRequest(invite_hash))
            print(f"Helper account joined channel {channel_id}.")
            return True
        except telethon_errors.UserAlreadyParticipantError:
            return True
        except telethon_errors.InviteRequestSentError:
            print("Join request sent; waiting for approval.")
            return False
        except telethon_errors.rpcerrorlist.ChatAdminRequiredError as exc:
            print(f"Channel denied helper join: {exc}")
            return False
        except telethon_errors.rpcbase.TelegramError as exc:
            print(f"Join failed for {channel_id}: {exc}")
            return False

    return asyncio.run_coroutine_threadsafe(_join_via_invite(), loop).result()


def _extract_invite_hash(invite_link: str) -> str:
    if "+" in invite_link:
        return invite_link.split("+", 1)[1]
    if "joinchat/" in invite_link:
        return invite_link.rsplit("/", 1)[1]
    raise ValueError(f"Unsupported invite link format: {invite_link}")