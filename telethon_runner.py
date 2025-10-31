import asyncio, threading, os
from telethon import TelegramClient
from dotenv import load_dotenv
import app_context

load_dotenv()

API_ID = int(os.getenv("TELETHON_API_ID", 0))
API_HASH = os.getenv("TELETHON_API_HASH", "")
SESSION = os.getenv("TELETHON_SESSION_NAME", "telethon_session")

def _loop_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = TelegramClient(SESSION, API_ID, API_HASH)

    # let Telethon run its own startup; pass the bot token to skip prompts
    client.start()

    app_context.telethon_loop = loop
    app_context.telethon_client = client
    loop.run_forever()

def init_telethon():
    if not API_ID or not API_HASH:
        print("Telethon credentials missing; channel mapping skipped.")
        return

    thread = threading.Thread(target=_loop_thread, daemon=True)
    thread.start()
    print("Telethon client started on dedicated loop.")

