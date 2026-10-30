import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from . import buffer, db, notify
from .config import get_settings
from .scheduling import tz

logger = logging.getLogger(__name__)

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


async def _notify_visitor_feed(when: datetime, visitor: dict, clip_name: str | None) -> None:
    s = get_settings()
    ip = visitor.get("ip") or "?"
    country = visitor.get("country") or "?"
    lines = [
        "🍚 有訪客餵咗 Roll Roll",
        f"🕐 {when.strftime('%Y-%m-%d %H:%M')}",
        f"🌐 {ip} · {country}",
    ]
    if clip_name:
        lines.append(f"📹 {s.public_base_url.rstrip('/')}/clips/{clip_name}")
    else:
        lines.append("📹（今次錄影整唔到）")
    await notify.send("\n".join(lines))


async def _notify_auto_feed(when: datetime, clip_name: str | None) -> None:
    """Notify the owner about a CatCam scheduler feed, without IP metadata."""
    s = get_settings()
    lines = [
        "🤖 自動餵食咗 Roll Roll",
        f"🕐 {when.strftime('%Y-%m-%d %H:%M')}",
    ]
    if clip_name:
        lines.append(
            f"📹 錄影片段：{s.public_base_url.rstrip('/')}/clips/{clip_name}"
        )
    else:
        lines.append("📹 錄影片段整唔到")
    await notify.send("\n".join(lines))


async def _record_clip(
    when: datetime,
    visitor: dict | None = None,
    source: str = "visitor",
) -> None:
    s = get_settings()
    final_path = recordings_dir() / (when.strftime(FILENAME_FMT) + ".mp4")

    # wait for the 24/7 ring buffer to actually have footage past `when` —
    # the pre-roll segments covering before `when` already exist by now,
    # it's the post-roll ones we have to wait for
    await asyncio.sleep(s.post_roll_seconds)

    splice_start = when - timedelta(seconds=s.pre_roll_seconds)
    splice_end = when + timedelta(seconds=s.post_roll_seconds)
    segments = buffer.segments_covering(splice_start, splice_end)

    if not segments:
        # buffer empty/not running (e.g. just after a restart, before the
        # first segment lands) — fall back to a plain post-trigger export
        # so a feed event never silently produces nothing, just without
        # the pre-roll
        logger.warning("recorder: no buffer segments covering %s, falling back to live export", when)
        await _record_clip_live_export(final_path, s.recording_seconds)
    else:
        # segments are whole 5s chunks, so concatenating them raw would
        # start the clip at the start of whichever segment happens to
        # overlap splice_start — not necessarily `pre_roll_seconds` before
        # `when`. Concat first, then trim the concatenated stream to the
        # exact [splice_start, splice_end] window. -c copy can only cut on
        # a keyframe, not an arbitrary frame, but at this encode's GOP
        # size (50 @ ~27.5fps) that's ~1.8s accuracy — far tighter than
        # the 5s segment boundary, with no re-encode cost.
        first_stamp = datetime.strptime(segments[0].stem, buffer.FILENAME_FMT).replace(tzinfo=tz())
        offset = max(0.0, (splice_start - first_stamp).total_seconds())
        duration = s.pre_roll_seconds + s.post_roll_seconds

        list_path = recordings_dir() / f".{final_path.name}.txt"
        concat_raw = recordings_dir() / f".{final_path.name}.raw.mp4"
        list_path.write_text("".join(f"file '{p.resolve()}'\n" for p in segments))
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-c", "copy", str(concat_raw),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if concat_raw.exists():
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-ss", str(offset), "-i", str(concat_raw),
                    "-t", str(duration), "-c", "copy", "-movflags", "+faststart",
                    str(final_path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
        finally:
            list_path.unlink(missing_ok=True)
            concat_raw.unlink(missing_ok=True)

    clip_name: str | None = None
    if final_path.exists():
        # phase 2 of the activity feed — attach the finished clip to the "fed"
        # event already logged at detection time in _poll_loop
        clip_name = final_path.name
        db.set_feed_event_clip(when, clip_name, datetime.now(tz()))
        _cleanup_old()
    else:
        logger.warning("recorder: no clip produced for trigger at %s", when)

    # Telegram alerts are sent after recording so every successful message
    # carries a ready-to-play clip. Visitor alerts include IP/country; an
    # auto-feed alert deliberately has no IP because no visitor triggered it.
    if visitor and get_settings().notify_visitor_feeds:
        await _notify_visitor_feed(when, visitor, clip_name)
    elif source == "auto" and get_settings().notify_auto_feeds:
        await _notify_auto_feed(when, clip_name)


async def _record_clip_live_export(final_path: Path, seconds: int) -> None:
    raw_path = final_path.with_suffix(".part")
    url = f"http://127.0.0.1:1984/api/stream.mp4?src=petkit_h264&duration={seconds}"
    timeout = httpx.Timeout(10.0, read=seconds + 15)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    logger.warning("recorder: live export got HTTP %s from petkit_h264", resp.status_code)
                    return
                with open(raw_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
    except httpx.RequestError as e:
        logger.warning("recorder: live export request to petkit_h264 failed: %s", e)
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


def _cleanup_old() -> None:
    cutoff = datetime.now(tz()) - timedelta(days=get_settings().recording_retention_days)
    db.prune_feed_events(cutoff)
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


def _resolve_feed_source(when: datetime) -> tuple[str, str | None, dict | None]:
    """Consume pending trigger metadata for one detected PetKit dispense.

    Auto-feed wins first because it carries a window note; an owner force-feed
    is next; a genuine site visitor carries notification metadata. Anything
    else keeps the historical ``visitor`` fallback used for PetKit app and
    physical-button dispenses.
    """
    auto_window = db.pop_auto_feed_pending(when, 90)
    if auto_window:
        return "auto", auto_window, None
    if db.pop_admin_feed_pending(when, 90):
        return "admin", None, None
    if db.pop_admin_test_pending(when, 90):
        return "admin_test", None, None
    visitor = db.pop_visitor_feed_pending(when, 90)
    if visitor:
        return "visitor", None, visitor
    return "petkit", None, None


def _record_detected_feed(when: datetime) -> tuple[str, str | None, dict | None]:
    """Persist one counter-detected dispense and return its trigger metadata."""
    source, note, visitor = _resolve_feed_source(when)
    if source == "petkit":
        # App, physical-button and PetKit schedule dispenses are real meals.
        # They do not belong in website feed_log, but they do restart the
        # public cooldown from detection time.
        db.set_last_fed_at(when)
    db.add_feed_event(when, source=source, note=note)
    return source, note, visitor


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
                when = datetime.now(tz())
                # phase 1 of the activity feed: log "fed" immediately so the
                # site can show it ~1 min before the clip finishes rendering.
                # if the scheduler just dispensed (marker set <90s ago), tag
                # this event as that auto-feed so the feed shows the 🤖 line
                source, note, visitor = _record_detected_feed(when)
                asyncio.create_task(_record_clip(when, visitor, source))
            last_val = val


def start() -> None:
    global _task
    if not get_settings().ha_token:
        return
    _task = asyncio.create_task(_poll_loop())


def stop() -> None:
    if _task:
        _task.cancel()
