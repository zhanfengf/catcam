import httpx

from .config import get_settings


class HAError(Exception):
    """Raised when the Home Assistant call fails."""


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
