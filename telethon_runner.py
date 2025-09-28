import asyncio, threading, os
from telethon import TelegramClient
from dotenv import load_dotenv
import app_context

load_dotenv()

API_ID = int(os.getenv("TELETHON_API_ID", 0))
API_HASH = os.getenv("TELETHON_API_HASH", "")
SESSION = os.getenv("TELETHON_SESSION_NAME", "telethon_session")

def _loop_thread(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()

def init_telethon() -> None:
    if not API_ID or not API_HASH:
        print("Telethon credentials missing; channel mapping skipped.")
        return

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=_loop_thread, args=(loop,), daemon=True)   
    thread.start()

    client = TelegramClient(SESSION, API_ID, API_HASH, loop=loop)

    async def _start_client():
        await client.start()

    try:
        asyncio.run_coroutine_threadsafe(_start_client(), loop).result()
    except Exception as exc:
        print(f"Failed to start Telethon client: {exc}")
        loop.call_soon_threadsafe(loop.stop)
        return

    app_context.telethon_loop = loop
    app_context.telethon_client = client
    print("Telethon client started on dedicated loop.")
