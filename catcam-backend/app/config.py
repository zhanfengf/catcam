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


    client_ip_header: str = "cf-connecting-ip"
    cors_origins: str = "*"


    db_path: str = "./catcam.db"

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
