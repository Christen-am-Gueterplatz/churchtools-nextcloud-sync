import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class AppConfig:
    """Application configuration settings loaded from environment variables."""

    # ChurchTools
    ct_base_url: str
    ct_login_token: str

    # Nextcloud
    nc_base_url: str
    nc_username: str
    nc_password: str
    nc_group_prefix: str
    nc_groups_claim: str  # 'groups' or 'roles'

    # Sync behavior
    dry_run: bool
    remove_extra_groups: bool

    # Logging
    log_level: str
    log_format: str
    log_file: str | None
    log_rotation: str
    log_retention: str

    @classmethod
    def load(cls) -> "AppConfig":
        """Loads configuration from .env file and environment variables."""
        load_dotenv()

        ct_base_url = os.getenv("CT_BASE_URL", "").strip()
        ct_login_token = os.getenv("CT_LOGIN_TOKEN", "").strip()
        nc_base_url = os.getenv("NC_BASE_URL", "").strip()
        nc_username = os.getenv("NC_USERNAME", "").strip()
        nc_password = os.getenv("NC_PASSWORD", "").strip()

        missing_fields = []
        if not ct_base_url:
            missing_fields.append("CT_BASE_URL")
        if not ct_login_token:
            missing_fields.append("CT_LOGIN_TOKEN")
        if not nc_base_url:
            missing_fields.append("NC_BASE_URL")
        if not nc_username:
            missing_fields.append("NC_USERNAME")
        if not nc_password:
            missing_fields.append("NC_PASSWORD")

        if missing_fields:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_fields)}. "
                "Please configure them in your .env file."
            )

        dry_run_env = os.getenv("DRY_RUN", "true").lower().strip()
        dry_run = dry_run_env not in ("0", "false", "no", "off")

        remove_extra_env = os.getenv("REMOVE_EXTRA_GROUPS", "true").lower().strip()
        remove_extra_groups = remove_extra_env not in ("0", "false", "no", "off")

        log_file_env = os.getenv("LOG_FILE", "").strip()
        log_file = log_file_env if log_file_env else None

        return cls(
            ct_base_url=ct_base_url.rstrip("/"),
            ct_login_token=ct_login_token,
            nc_base_url=nc_base_url.rstrip("/"),
            nc_username=nc_username,
            nc_password=nc_password,
            nc_group_prefix=os.getenv("NC_GROUP_PREFIX", "ChurchTools-"),
            nc_groups_claim=os.getenv("NC_GROUPS_CLAIM", "groups").lower().strip(),
            dry_run=dry_run,
            remove_extra_groups=remove_extra_groups,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_format=os.getenv("LOG_FORMAT", "simple").strip(),
            log_file=log_file,
            log_rotation=os.getenv("LOG_ROTATION", "10 MB"),
            log_retention=os.getenv("LOG_RETENTION", "30 days"),
        )
