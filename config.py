"""
Configuration for Program Tracker bot.
All secrets come from environment variables.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Config:
    # Telegram Bot
    telegram_bot_token: str
    telegram_chat_id: str

    # GitHub (for Gist state storage)
    github_token: str
    gist_id: Optional[str]  # None on first run; will be created

    # Behavior
    check_interval_minutes: int
    data_source_url: str
    user_agent: str

    @classmethod
    def from_env(cls) -> "Config":
        missing = []
        for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN"):
            if not os.environ.get(var):
                missing.append(var)
        if missing:
            raise RuntimeError(
                f"Missing required env vars: {', '.join(missing)}. "
                f"See README.md for setup instructions."
            )

        return cls(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            github_token=os.environ["GITHUB_TOKEN"],
            gist_id=os.environ.get("GIST_ID") or None,  # created on first run
            check_interval_minutes=int(
                os.environ.get("CHECK_INTERVAL_MINUTES", "15")
            ),
            data_source_url=os.environ.get(
                "DATA_SOURCE_URL",
                "https://raw.githubusercontent.com/projectdiscovery/"
                "public-bugbounty-programs/main/dist/data.json",
            ),
            user_agent=os.environ.get(
                "USER_AGENT",
                "ProgramTracker/1.0 (bug bounty monitoring bot)",
            ),
        )


config = Config.from_env()
