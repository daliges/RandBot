import asyncio
from typing import Optional

from aiogram import Bot
from telethon import TelegramClient

bot: Optional[Bot] = None
telethon_client: Optional[TelegramClient] = None
telethon_loop: Optional[asyncio.AbstractEventLoop] = None
