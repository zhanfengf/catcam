import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

from .config import get_settings
from .scheduling import tz

FILENAME_FMT = "%Y-%m-%d_%H%M%S"

_run_task: asyncio.Task | None = None
_cleanup_task: asyncio.Task | None = None
_proc: asyncio.subprocess.Process | None = None


def buffer_dir() -> Path:
    d = Path(get_settings().buffer_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def segments_covering(start: datetime, end: datetime) -> list[Path]:
    seg_seconds = get_settings().buffer_segment_seconds
    items: list[tuple[datetime, Path]] = []
    for f in buffer_dir().glob("*.mp4"):
        try:
            stamp = datetime.strptime(f.stem, FILENAME_FMT).replace(tzinfo=tz())
        except ValueError:
            continue
        # a segment roughly covers [stamp, stamp + seg_seconds) — keep it if
        # that window overlaps the requested [start, end] at all
        if stamp + timedelta(seconds=seg_seconds) >= start and stamp <= end:
            items.append((stamp, f))
    items.sort(key=lambda x: x[0])
    return [p for _, p in items]


def _cleanup_old() -> None:
    cutoff = datetime.now(tz()) - timedelta(seconds=get_settings().buffer_window_seconds)
    for f in buffer_dir().glob("*.mp4"):
        try:
            stamp = datetime.strptime(f.stem, FILENAME_FMT).replace(tzinfo=tz())
        except ValueError:
            continue
        if stamp < cutoff:
            f.unlink(missing_ok=True)


async def _run_loop() -> None:
    global _proc
    s = get_settings()
    out_pattern = str(buffer_dir() / "%Y-%m-%d_%H%M%S.mp4")
    # ffmpeg's -strftime filenames use the process's wall clock. catcam.service
    # doesn't set TZ (unlike go2rtc.service), so without this the CT's default
    # UTC clock gets written into filenames that recorder.py/segments_covering
    # then interpret as HK time — files look ~8h "old" the instant they're
    # created and _cleanup_old() deletes them within one cleanup cycle.
    env = {**os.environ, "TZ": "Asia/Hong_Kong"}
    while True:
        _proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-v", "error",
            "-rtsp_transport", "tcp",
            "-i", "rtsp://127.0.0.1:8554/petkit_h264",
            "-c", "copy",
            "-f", "segment", "-segment_time", str(s.buffer_segment_seconds),
            "-reset_timestamps", "1", "-strftime", "1",
            out_pattern,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await _proc.wait()
        # ffmpeg died (go2rtc restart, brief network hiccup) — respawn after
        # a short backoff rather than leaving the buffer silently empty
        await asyncio.sleep(3)


async def _cleanup_loop() -> None:
    while True:
        try:
            _cleanup_old()
        except Exception:
            pass
        await asyncio.sleep(get_settings().buffer_segment_seconds)


def start() -> None:
    global _run_task, _cleanup_task
    _run_task = asyncio.create_task(_run_loop())
    _cleanup_task = asyncio.create_task(_cleanup_loop())


def stop() -> None:
    if _run_task:
        _run_task.cancel()
    if _cleanup_task:
        _cleanup_task.cancel()
    if _proc:
        _proc.terminate()
