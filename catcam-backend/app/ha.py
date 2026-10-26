import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .config import get_settings
from .scheduling import tz

# PetKit's daily dispense counter. Tried image.zhi_ma_guan_jia_last_feed_event
# (its state *is* an event timestamp) first, but that entity lags several
# minutes to hours behind — it waits on a snapshot image upload from the
# device. This counter updates within seconds of a real dispense (confirmed:
# ticked up ~6s after a manual feed), because it's a plain number with no
# image attached. It resets to 0 at local midnight, which conveniently also
# means every value-increase in today's history is exactly one feed event —
# we use the HA state-change's own timestamp (last_changed) for the time.
_FEED_COUNT_ENTITY = "sensor.zhi_ma_guan_jia_times_dispensed"


class HAError(Exception):
    """Raised when the Home Assistant call fails."""


async def get_feed_history(hours: int = 72, chunk_hours: int = 6) -> list[str]:
    """Return PetKit's own feed-event timestamps (HK-local, naive ISO
    strings) derived from the times-dispensed counter's history, newest
    first.

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
    raw: set[tuple[str, str]] = set()

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
                        "filter_entity_id": _FEED_COUNT_ENTITY,
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
                    changed = entry.get("last_changed")
                    if state is None or changed is None:
                        continue
                    raw.add((changed, state))

            chunk_end = chunk_start
            elapsed += chunk_hours

    # walk chronologically, keep only genuine increases — this naturally
    # skips the daily reset-to-0 and the carried-over baseline row at the
    # start of each chunk
    events: list[str] = []
    prev_val: int | None = None
    for changed, state in sorted(raw):
        try:
            val = int(state)
        except ValueError:
            continue
        if prev_val is not None and val > prev_val:
            dt = datetime.fromisoformat(changed).astimezone(tz())
            events.append(dt.strftime("%Y-%m-%dT%H:%M:%S"))
        prev_val = val

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


# background connectivity check, polled independently of /feed attempts so
# /status can report "offline" and the frontend can disable the feed button
# before a visitor ever tries and hits a 502
_online = True
_POLL_SECONDS = 15
_task: asyncio.Task | None = None


async def _check_online() -> bool:
    s = get_settings()
    if not s.ha_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{s.ha_url.rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {s.ha_token}"},
            )
        return resp.status_code < 400
    except httpx.RequestError:
        return False


async def _poll_loop() -> None:
    global _online
    while True:
        _online = await _check_online()
        await asyncio.sleep(_POLL_SECONDS)


def is_online() -> bool:
    return _online


def start() -> None:
    global _task
    _task = asyncio.create_task(_poll_loop())


def stop() -> None:
    if _task:
        _task.cancel()
