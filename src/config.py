"""Configuration helpers and path constants for the Facebook autoposter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
STATE_DIR = ROOT_DIR / "state"
GENERATED_DIR = ROOT_DIR / "generated"

ARCHETYPES_PATH = DATA_DIR / "top_50_archetypes.json"
QUOTE_VAULT_PATH = DATA_DIR / "quote_vault.json"
HISTORY_PATH = STATE_DIR / "posted_history.json"


@dataclass(frozen=True)
class AppConfig:
    """Runtime settings read from environment variables."""

    brand_name: str
    brand_monogram: str
    brand_handle: str
    composio_api_key: str
    composio_user_id: str
    composio_mcp_url: str
    composio_facebook_account: str
    facebook_page_id: str
    gemini_api_key: str
    openai_api_key: str
    hf_token: str
    pollinations_api_key: str
    cloudflare_account_id: str
    cloudflare_api_token: str
    use_composio_fal: bool
    public_media_base_url: str
    image_width: int = 1080
    image_height: int = 1350
    max_history_items: int = 4000

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build configuration from environment variables with safe defaults."""
        repo = os.getenv("GITHUB_REPOSITORY", "").strip()
        media_branch = os.getenv("MEDIA_BRANCH", "media").strip() or "media"
        explicit_base = os.getenv("PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
        auto_base = (
            f"https://raw.githubusercontent.com/{repo}/{media_branch}"
            if repo and os.getenv("REPO_IS_PUBLIC", "false").lower() == "true"
            else ""
        )

        return cls(
            brand_name=os.getenv("BRAND_NAME", "Attitude | Motivation | Mindset").strip(),
            brand_monogram=os.getenv("BRAND_MONOGRAM", "AP").strip()[:4] or "AP",
            brand_handle=os.getenv("BRAND_HANDLE", "@attitude__mindset").strip(),
            composio_api_key=os.getenv("COMPOSIO_API_KEY", "").strip(),
            composio_user_id=os.getenv("COMPOSIO_USER_ID", "default").strip() or "default",
            composio_mcp_url=os.getenv("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp").strip(),
            composio_facebook_account=os.getenv("COMPOSIO_FACEBOOK_ACCOUNT", "").strip(),
            facebook_page_id=os.getenv("FACEBOOK_PAGE_ID", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            hf_token=os.getenv("HF_TOKEN", "").strip(),
            pollinations_api_key=os.getenv("POLLINATIONS_API_KEY", "").strip(),
            cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            use_composio_fal=os.getenv("USE_COMPOSIO_FAL", "false").lower() == "true",
            public_media_base_url=explicit_base or auto_base,
        )
