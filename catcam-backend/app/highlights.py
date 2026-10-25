import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from . import recorder
from .config import get_settings
from .scheduling import tz

_WEEK_DAYS = 7

_task: asyncio.Task | None = None


def highlights_dir() -> Path:
    d = Path(get_settings().highlights_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _first_clip_per_day(week_start: datetime, days: int) -> list[Path]:
    """Earliest recording for each of the `days` dates starting at
    week_start, skipping any day with no recording."""
    by_day: dict[str, tuple[datetime, Path]] = {}
    for f in recorder.recordings_dir().glob("*.mp4"):
        try:
            stamp = datetime.strptime(f.stem, recorder.FILENAME_FMT).replace(tzinfo=tz())
        except ValueError:
            continue
        day_key = stamp.strftime("%Y-%m-%d")
        if day_key not in by_day or stamp < by_day[day_key][0]:
            by_day[day_key] = (stamp, f)

    selected = []
    for i in range(days):
        day_key = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
        if day_key in by_day:
            selected.append(by_day[day_key])

    selected.sort(key=lambda x: x[0])
    return [p for _, p in selected]


async def compile_week(week_start: datetime) -> Path | None:
    """Concatenate each day's first clip for the 7-day window starting at
    week_start into one file under highlights_dir. Returns the output path,
    or None if there was nothing to compile / it already exists."""
    clips = _first_clip_per_day(week_start, _WEEK_DAYS)
    if not clips:
        return None

    week_end = week_start + timedelta(days=_WEEK_DAYS - 1)
    out_name = f"highlight_{week_start:%Y-%m-%d}_to_{week_end:%Y-%m-%d}.mp4"
    out_path = highlights_dir() / out_name
    if out_path.exists():
        return None

    list_path = highlights_dir() / f".{out_name}.txt"
    list_path.write_text("".join(f"file '{p.resolve()}'\n" for p in clips))

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c", "copy", str(out_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    finally:
        list_path.unlink(missing_ok=True)

    return out_path if out_path.exists() else None


def _seconds_until_next_sunday_midnight() -> float:
    now = datetime.now(tz())
    days_ahead = (6 - now.weekday()) % 7  # Monday=0 ... Sunday=6
    next_sunday = (now + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if next_sunday <= now:
        next_sunday += timedelta(days=7)
    return (next_sunday - now).total_seconds()


async def _schedule_loop() -> None:
    while True:
        await asyncio.sleep(_seconds_until_next_sunday_midnight())
        run_at = datetime.now(tz())
        week_start = (run_at - timedelta(days=_WEEK_DAYS)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        try:
            await compile_week(week_start)
        except Exception:
            # one bad week (ffmpeg hiccup, disk issue, etc.) must not kill
            # the loop for every week after it
            pass


def start() -> None:
    global _task
    _task = asyncio.create_task(_schedule_loop())


def stop() -> None:
    if _task:
        _task.cancel()
