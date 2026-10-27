import asyncio
import logging
import time

from . import buffer, ha, notify
from .config import get_settings

log = logging.getLogger("catcam.streamwatch")

_CHECK_SECONDS = 15

_online = True
_down_since: float | None = None
_last_recover: float = 0.0
_notified_down = False
_task: asyncio.Task | None = None
_bg: set[asyncio.Task] = set()


def is_online() -> bool:
    return _online


def _push(text: str) -> None:
    """Fire-and-forget a Telegram alert without blocking the watch loop (and
    without the task getting garbage-collected mid-flight)."""
    t = asyncio.create_task(notify.send(text))
    _bg.add(t)
    t.add_done_callback(_bg.discard)


def _restart_go2rtc() -> bool:
    """Request a go2rtc restart without any root privilege: touch a trigger
    file the catcam user owns. A root-run systemd path unit
    (go2rtc-restart.path → go2rtc-restart.service, in deploy/) watches it and
    runs `systemctl restart go2rtc` on modification. This CT has no sudo, and
    this keeps catcam's extra capability to exactly one action."""
    from pathlib import Path
    try:
        Path(get_settings().go2rtc_restart_trigger).touch()
        return True
    except OSError as exc:
        log.warning("could not touch go2rtc restart trigger: %s", exc)
        return False


async def _recover() -> None:
    """Same sequence as scripts/fix-catcam-stream.sh, run in-process: reload the
    PetKit integration (the real fix), then restart go2rtc so it re-pulls a
    fresh WHEP session."""
    log.info("stream down — auto-recovery: reload PetKit integration")
    try:
        await ha.reload_petkit()
    except ha.HAError as exc:
        log.warning("PetKit reload failed: %s", exc)
    await asyncio.sleep(25)
    ok = _restart_go2rtc()
    log.info("auto-recovery go2rtc restart requested ok=%s", ok)


async def _loop() -> None:
    global _online, _down_since, _last_recover, _notified_down
    while True:
        _online = buffer.stream_online()
        s = get_settings()
        if _online:
            if _down_since is not None and _notified_down:
                down_s = int(time.monotonic() - _down_since)
                _push(f"🟢 Roll Roll 直播復原咗(斷咗約 {down_s} 秒)")
            _down_since = None
            _notified_down = False
        else:
            now = time.monotonic()
            if _down_since is None:
                _down_since = now
            down_for = now - _down_since
            # one alert per outage, only after it's sustained (no flapping)
            if down_for >= s.stream_recover_after_seconds and not _notified_down:
                _notified_down = True
                msg = f"🔴 Roll Roll 直播斷咗(已持續約 {int(down_for)} 秒)"
                if s.stream_auto_recover:
                    msg += "，自動修復緊:reload PetKit + 重啟 go2rtc…"
                _push(msg)
            if (s.stream_auto_recover
                    and down_for >= s.stream_recover_after_seconds
                    and now - _last_recover >= s.stream_recover_cooldown_seconds):
                _last_recover = now
                await _recover()
        await asyncio.sleep(_CHECK_SECONDS)


def start() -> None:
    global _task
    _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task:
        _task.cancel()
