import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from .config import get_settings
from .scheduling import tz

# same counter driving /admin/history — watching it here too means every
# real dispense gets a clip, regardless of trigger (site, app, physical
# button, scheduled auto-feed), not just the ones this backend itself
# triggers via /feed or /admin/feed
_FEED_COUNT_ENTITY = "sensor.zhi_ma_guan_jia_times_dispensed"
_POLL_SECONDS = 10

FILENAME_FMT = "%Y-%m-%d_%H%M%S"

_task: asyncio.Task | None = None


def recordings_dir() -> Path:
    d = Path(get_settings().recordings_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _get_times_dispensed(client: httpx.AsyncClient) -> int | None:
    s = get_settings()
    url = f"{s.ha_url.rstrip('/')}/api/states/{_FEED_COUNT_ENTITY}"
    headers = {"Authorization": f"Bearer {s.ha_token}"}
    try:
        resp = await client.get(url, headers=headers, timeout=10.0)
    except httpx.RequestError:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return int(resp.json()["state"])
    except (KeyError, ValueError, TypeError):
        return None


async def _record_clip(when: datetime) -> None:
    s = get_settings()
    final_path = recordings_dir() / (when.strftime(FILENAME_FMT) + ".mp4")
    raw_path = final_path.with_suffix(".part")
    url = (
        f"http://127.0.0.1:1984/api/stream.mp4"
        f"?src=petkit_h264&duration={s.recording_seconds}"
    )
    timeout = httpx.Timeout(10.0, read=s.recording_seconds + 15)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return
                with open(raw_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
    except httpx.RequestError:
        raw_path.unlink(missing_ok=True)
        return

    # go2rtc's export is fragmented MP4 (the same format it streams over
    # MSE) — a plain <video src> tag can fail to ever load it (confirmed:
    # readyState stuck at 0, no error, just never starts). Remux (lossless,
    # ~0.4s for a 60s clip) into a standard faststart MP4 for the recorder
    # to actually be watchable.
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(raw_path), "-c", "copy", "-movflags", "+faststart",
        str(final_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    raw_path.unlink(missing_ok=True)

    if not final_path.exists():
        return

    _cleanup_old()


def _cleanup_old() -> None:
    cutoff = datetime.now(tz()) - timedelta(days=get_settings().recording_retention_days)
    for f in recordings_dir().glob("*.mp4"):
        try:
            stamp = datetime.strptime(f.stem, FILENAME_FMT).replace(tzinfo=tz())
        except ValueError:
            continue
        if stamp < cutoff:
            f.unlink(missing_ok=True)

    # orphaned downloads from a crash mid-recording — anything older than
    # one poll+remux cycle is definitely stale, not an in-progress one
    part_cutoff = datetime.now(tz()) - timedelta(minutes=10)
    for f in recordings_dir().glob("*.part"):
        if datetime.fromtimestamp(f.stat().st_mtime, tz()) < part_cutoff:
            f.unlink(missing_ok=True)


def list_recordings() -> list[dict]:
    items = []
    for f in recordings_dir().glob("*.mp4"):
        try:
            stamp = datetime.strptime(f.stem, FILENAME_FMT).replace(tzinfo=tz())
        except ValueError:
            continue
        items.append({"filename": f.name, "recorded_at": stamp.isoformat()})
    items.sort(key=lambda x: x["recorded_at"], reverse=True)
    return items


async def _poll_loop() -> None:
    async with httpx.AsyncClient() as client:
        # baseline on startup — don't treat whatever today's count already
        # is as a brand-new event
        last_val = await _get_times_dispensed(client)
        while True:
            await asyncio.sleep(_POLL_SECONDS)
            val = await _get_times_dispensed(client)
            if val is None:
                continue
            if last_val is not None and val > last_val:
                asyncio.create_task(_record_clip(datetime.now(tz())))
            last_val = val


def start() -> None:
    global _task
    if not get_settings().ha_token:
        return
    _task = asyncio.create_task(_poll_loop())


def stop() -> None:
    if _task:
        _task.cancel()
