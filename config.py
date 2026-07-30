"""
Application settings, loaded from .env.local.

Kept separate from app.py so every module (routers, rendering, etc.) can
import `settings` without pulling in FastAPI app / Mongo wiring.
"""
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" -- .env.local is shared with agent.py (PIPER_MODEL_PATH,
    # CLOUDFLARE_R2_*, etc.); this class only needs the keys the dashboard
    # itself reads.
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    mongodb_uri: str = Field("mongodb://localhost:27017", validation_alias="MONGODB_URI")
    # Matches docker-compose's MONGODB_DATABASE so the dashboard and any
    # other tooling always agree on which database they're pointed at.
    mongodb_database: str = Field("voice_agent_db", validation_alias="MONGODB_DATABASE")
    slack_webhook_url: Optional[str] = Field(None, validation_alias="SLACK_WEBHOOK_URL")
    public_base_url: str = Field("http://localhost:8000", validation_alias="PUBLIC_BASE_URL")

    # Needed only for the "place an outbound call" screen. Optional so the
    # dashboard still runs fine (inbound-only) if these aren't set yet.
    livekit_url: Optional[str] = Field(None, validation_alias="LIVEKIT_URL")
    livekit_api_key: Optional[str] = Field(None, validation_alias="LIVEKIT_API_KEY")
    livekit_api_secret: Optional[str] = Field(None, validation_alias="LIVEKIT_API_SECRET")
    sip_outbound_trunk_id: Optional[str] = Field(None, validation_alias="SIP_OUTBOUND_TRUNK_ID")
    voice_agent_name: str = Field("urdu-voicebot", validation_alias="VOICE_AGENT_NAME")

    # Safety cap for the "call multiple numbers" screen so a mis-paste of a
    # huge list can't fire off hundreds of calls by accident.
    max_bulk_call_numbers: int = Field(25, validation_alias="MAX_BULK_CALL_NUMBERS")


settings = Settings()
