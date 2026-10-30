from datetime import time
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_hhmm(value: str) -> time:
    hh, mm = value.strip().split(":")
    return time(int(hh), int(mm))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


    ha_url: str = ""
    ha_token: str = ""
    ha_feed_entity: str = "text.zhi_ma_guan_jia_manual_feed"


    feed_amount: int = 10
    cooldown_minutes: int = 120
    open_time: str = "07:00"
    close_time: str = "23:59"
    timezone: str = "Asia/Hong_Kong"


    ip_max_hits: int = 5
    ip_window_seconds: int = 60


    admin_token: str = ""
    admin_sig_window_seconds: int = 60


    client_ip_header: str = "cf-connecting-ip"
    cors_origins: str = "*"


    db_path: str = "./catcam.db"

    recordings_dir: str = "./recordings"
    recording_seconds: int = 60
    recording_retention_days: int = 7

    highlights_dir: str = "./highlights"

    buffer_dir: str = "./buffer"
    buffer_segment_seconds: int = 5
    buffer_window_seconds: int = 180
    pre_roll_seconds: int = 15
    post_roll_seconds: int = 45

    # stream liveness is read off the 24/7 buffer: if the newest segment's
    # mtime hasn't advanced within this many seconds, no frames are flowing
    # (upstream PetKit/HA WHEP stall) even if HA still reports "streaming"
    stream_stale_seconds: int = 30
    # a real ~5s segment is hundreds of KB; segments below this are the empty
    # churn of a starved/reconnecting ffmpeg and don't count as live frames
    buffer_min_segment_bytes: int = 20000
    # sustained outage before the watcher auto-runs recovery (reload PetKit
    # integration + restart go2rtc), and the min gap between two attempts so a
    # genuine cloud outage isn't hammered
    stream_recover_after_seconds: int = 75
    stream_recover_cooldown_seconds: int = 300
    stream_auto_recover: bool = True
    # touched by the backend to ask a root systemd path unit to restart go2rtc
    # (this CT has no sudo); see deploy/go2rtc-restart.{path,service}
    go2rtc_restart_trigger: str = "./go2rtc-restart.trigger"

    # optional Telegram push for stream outage/recovery alerts; both empty =
    # notifications off (the watchdog still detects + auto-recovers silently)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # push Telegram alerts after a feed clip is ready. Visitor alerts include
    # IP + country; auto-feed alerts deliberately contain no IP metadata.
    # Clip links are built off this public base.
    notify_visitor_feeds: bool = True
    notify_auto_feeds: bool = True
    public_base_url: str = "https://cat.kelvinp.work"

    @property
    def open_t(self) -> time:
        return _parse_hhmm(self.open_time)

    @property
    def close_t(self) -> time:
        return _parse_hhmm(self.close_time)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
