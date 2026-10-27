import logging

import httpx

from .config import get_settings

log = logging.getLogger("catcam.notify")


async def send(text: str) -> None:
    """Push a short message to Telegram. No-op (and never raises) when the bot
    token / chat id aren't configured, so the rest of the app doesn't care
    whether notifications are turned on."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": s.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            })
        if resp.status_code >= 400:
            log.warning("telegram sendMessage %s: %s",
                        resp.status_code, resp.text[:200])
    except httpx.RequestError as exc:
        log.warning("telegram notify failed: %s", exc)
