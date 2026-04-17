from __future__ import annotations

import os

from dotenv import load_dotenv

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Telethon is required to generate a Theron session string. "
        "Install it with ./.venv/bin/pip install telethon"
    ) from exc


load_dotenv()


def main() -> int:
    api_id = (os.getenv("THERON_TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("THERON_TELEGRAM_API_HASH") or "").strip()

    if not api_id or not api_hash:
        raise SystemExit(
            "Set THERON_TELEGRAM_API_ID and THERON_TELEGRAM_API_HASH in your shell or .env first."
        )

    session = StringSession()
    client = TelegramClient(session, int(api_id), api_hash)

    with client:
        me = client.get_me()
        print("Theron Telegram session generated.")
        print(f"Logged in as: {getattr(me, 'username', None) or getattr(me, 'first_name', 'unknown')}")
        print()
        print("Paste this into your .env as THERON_TELEGRAM_SESSION_STRING:")
        print(session.save())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
