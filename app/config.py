from __future__ import annotations

from functools import cached_property

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(validation_alias="BOT_TOKEN", min_length=1)
    database_url: str = Field(validation_alias="DATABASE_URL", min_length=1)
    owner_telegram_id: int = Field(validation_alias="OWNER_TELEGRAM_ID", gt=0)
    admin_ids_raw: str = Field(default="", validation_alias="ADMIN_IDS")
    env: str = Field(default="development", validation_alias="ENV")
    port: int = Field(default=8080, validation_alias="PORT", ge=1, le=65535)

    @field_validator("admin_ids_raw")
    @classmethod
    def valid_admins(cls, value: str) -> str:
        for item in filter(None, (part.strip() for part in value.split(","))):
            if not item.isdigit() or int(item) <= 0:
                raise ValueError("ADMIN_IDS must be a comma-separated list of positive Telegram IDs")
        return value

    @cached_property
    def admin_ids(self) -> frozenset[int]:
        ids = {self.owner_telegram_id}
        ids.update(int(item) for item in self.admin_ids_raw.split(",") if item.strip())
        return frozenset(ids)

