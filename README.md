# RandBot

A Telegram bot that serves random media from linked channels — think TikTok-style discovery, but for Telegram. Users scroll through posts from random channels in a private chat; channel owners get organic exposure to new subscribers.

---

## How it works

1. A channel admin adds the bot as an administrator.
2. The bot scans the channel's history and indexes all media messages.
3. Any user can send `/random` in a private chat with the bot to receive a random post from a random linked channel, with a Subscribe button attached.
4. New subscriptions are tracked against the channel's active bundle quota.

```
User → /random → Bot picks random channel → copies random media post
                                           → Subscribe button → channel link
```

---

## Architecture

| Layer | Tech |
|---|---|
| Bot framework | [aiogram 3](https://docs.aiogram.dev/) (async, webhook mode) |
| Telegram user API | [Telethon](https://docs.telethon.dev/) (separate thread + event loop) |
| Web server | aiohttp |
| Primary database | SQLite |
| Cache | Redis |
| Infrastructure | AWS + Docker Compose |
| CI/CD | GitHub Actions |

**Two Telegram clients run concurrently:**
- `aiogram` bot — handles all user-facing commands, payments, and callbacks via webhook.
- `telethon` client (helper account) — joins channels to stream new/deleted messages and keep media indexes up to date in real time.

The Telethon client runs on a dedicated thread with its own event loop. The aiogram bot dispatches blocking DB calls to a thread pool via `asyncio.to_thread` to avoid blocking the main loop.

---

## Project structure

```
.
├── main.py                  # Entry point: webhook server, bot + dispatcher setup
├── app_context.py           # Global references to bot, Telethon client, and loop
├── telethon_runner.py       # Starts Telethon on a background thread
├── check.py                 # Standalone script: process pending intents & expired bundles
├── bot/
│   ├── private_handlers.py  # /start, /random, /help, /admin, subscribe callbacks
│   ├── channel_handlers.py  # Admin promotion, payment flow, new member tracking
│   ├── channel_watchers.py  # Telethon event handlers (new/deleted messages)
│   ├── mapping.py           # Initial full-history scan when a channel is linked
│   ├── inviter.py           # Invite helper account into channels, send deep links
│   └── utils.py             # Shared keyboards, bundle options, helpers
├── data/
│   ├── databases.py         # SQLite schema, all read/write operations, Redis client
│   └── pay_databases.py     # Bundle and subscription accounting
├── migrations/              # SQL migration files applied at startup
├── scripts/
│   └── migrate_sqlite.py    # Migration runner (applied by entrypoint.sh)
├── entrypoint.sh            # Runs migrations then starts main.py
├── Dockerfile
└── docker-compose.yml
```

---

## Payments

The bot uses **Telegram Stars** (`XTR`) as the payment currency. Channel owners buy subscriber quota bundles:

| Bundle | Quota | Price |
|---|---|---|
| Starter | 20 subs | 100 ⭐ |
| Growth | 50 subs | 250 ⭐ |
| Pro | 100 subs | 500 ⭐ |
| Scale | 500 subs | 2,500 ⭐ |
| Max | 1,000 subs | 5,000 ⭐ |

Every channel gets **10 free trial subscribers** on first link. Free quota is consumed before paid quota. If free quota is exhausted with no paid bundle, the channel is paused and the admin is prompted to buy. Bundles with zero consumption after 30 days are auto-refunded.

Subscription is counted only once per user per channel, and only after the user stays for a verification window (tracked via `subscription_intents` and confirmed by `check.py`).

---

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- A Telegram bot token ([BotFather](https://t.me/BotFather))
- A Telegram API app (`api_id` + `api_hash`) for the Telethon helper account — [my.telegram.org](https://my.telegram.org)
- A public HTTPS URL for the webhook (e.g. via nginx reverse proxy or a cloud load balancer)

### Environment variables

Create a `.env` file at the repo root:

```env
BOT_TOKEN=your_bot_token

# Webhook
WEBHOOK_BASE=https://your-domain.com
WEBHOOK_SECRET=a_random_secret_string
PORT=8484

# Telethon helper account
TELETHON_API_ID=12345678
TELETHON_API_HASH=your_api_hash
TELETHON_SESSION_NAME=randbot_session

# Database
CHANNELS_DB_PATH=/app/channels.db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Optional
CHANNEL_IDS_CACHE_KEY=channel_ids_cache
CHANNEL_IDS_TTL=300
```

### Running locally

```bash
# First run: authenticate the Telethon session interactively
python -c "from telethon.sync import TelegramClient; TelegramClient('randbot_session', API_ID, API_HASH).start()"

# Start services
docker compose up --build
```

The bot starts on port `8484` by default (mapped to `127.0.0.1:8484` in docker-compose). Point your reverse proxy or tunnel there.

### Running the maintenance job

`check.py` is a standalone script meant to be run on a schedule (e.g. daily cron or GitHub Actions scheduled workflow). It:
- Confirms or denies pending subscription intents older than 24 hours
- Refunds or credits bundles that expired with zero consumption

```bash
python check.py
```

---

## Database schema

The SQLite database has the following tables:

- `channels` — registered channels and their admin
- `mappings` — per-channel list of media message IDs (JSON array)
- `channel_users` — deep-link join tracking (user → channel)
- `bundles` — payment bundles with quota and consumption counters
- `subscriptions` — one row per user/channel pair, tied to a bundle
- `subscription_intents` — click-to-subscribe events pending verification
- `refunds` — refund/credit records per bundle
- `schema_migrations` — applied migration versions

Migrations in `migrations/` are applied automatically at startup by `entrypoint.sh`.

---

## Key design decisions

**Why two Telegram clients?**
The bot API doesn't provide a way to read channel history or stream deletion events. Telethon (user API) fills that gap. Running it on a dedicated thread prevents it from interfering with the aiogram event loop.

**Why Redis alongside SQLite?**
SQLite is the source of truth. Redis caches the media ID lists and active channel IDs to avoid repeated DB reads on every `/random` call. Cache is invalidated on writes.

**Why copy_message instead of forwarding?**
`copy_message` lets the bot attach its own inline keyboard (Subscribe / Next) without the "Forwarded from" header cluttering the post.

---

## License

MIT
