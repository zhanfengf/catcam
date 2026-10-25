from datetime import datetime, timedelta, timezone

import httpx

from .config import get_settings


class HAError(Exception):
    """Raised when the Home Assistant call fails."""


# PetKit's own per-dispense-event timestamp, independent of how the feed was
# triggered (this site, the PetKit app, the device's own button, or a
# scheduled auto-feed) — the closest thing to ground truth we have.
_FEED_EVENT_ENTITY = "image.zhi_ma_guan_jia_last_feed_event"


async def get_feed_history(hours: int = 72, chunk_hours: int = 6) -> list[str]:
    """Return PetKit's own feed-event timestamps (HK-local, naive ISO
    strings) from HA's history API, newest first, deduplicated.

    HA's /api/history/period caps each response at a handful of rows
    (observed: 5) counted from the *start* of the requested window, not
    the most recent ones — a wide single request silently drops everything
    after the cap and never reaches "now". Walking backward in small
    chunks with an explicit end_time keeps each request's real row count
    under that cap.
    """
    s = get_settings()
    if not s.ha_token:
        raise HAError("HA_TOKEN is not configured")

    headers = {"Authorization": f"Bearer {s.ha_token}"}
    seen: set[str] = set()
    events: list[str] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        chunk_end = datetime.now(timezone.utc)
        elapsed = 0
        while elapsed < hours:
            chunk_start = chunk_end - timedelta(hours=chunk_hours)
            url = f"{s.ha_url.rstrip('/')}/api/history/period/{chunk_start.isoformat()}"
            try:
                resp = await client.get(
                    url,
                    headers=headers,
                    params={
                        "filter_entity_id": _FEED_EVENT_ENTITY,
                        "end_time": chunk_end.isoformat(),
                    },
                )
            except httpx.RequestError as exc:
                raise HAError(f"Cannot reach Home Assistant: {exc}") from exc

            if resp.status_code >= 400:
                raise HAError(f"HA returned {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            if data:
                for entry in data[0]:
                    state = entry.get("state")
                    if not state or state in ("unknown", "unavailable") or state in seen:
                        continue
                    seen.add(state)
                    events.append(state)

            chunk_end = chunk_start
            elapsed += chunk_hours

    return sorted(events, reverse=True)


async def dispense(amount: int) -> None:
    """Set the PetKit manual-feed text entity, which triggers dispensing."""
    s = get_settings()
    if not s.ha_token:
        raise HAError("HA_TOKEN is not configured")

    url = f"{s.ha_url.rstrip('/')}/api/services/text/set_value"
    headers = {
        "Authorization": f"Bearer {s.ha_token}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": s.ha_feed_entity, "value": str(amount)}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise HAError(f"Cannot reach Home Assistant: {exc}") from exc

    if resp.status_code >= 400:
        raise HAError(f"HA returned {resp.status_code}: {resp.text[:200]}")
