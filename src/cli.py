import argparse
import asyncio
import sys
from loguru import logger

from src.clients.churchtools import ChurchToolsClient
from src.clients.nextcloud import NextcloudClient
from src.config import AppConfig
from src.logger import setup_logger
from src.sync import SyncEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize ChurchTools groups/roles to Nextcloud users."
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Apply changes to Nextcloud (active synchronization).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate synchronization without modifying Nextcloud.",
    )
    parser.add_argument(
        "--remove-extra",
        action="store_true",
        default=None,
        help="Remove groups with prefix if user is no longer a member in ChurchTools.",
    )
    parser.add_argument(
        "--no-remove-extra",
        action="store_true",
        help="Prevent removing extra groups (only add missing groups).",
    )
    parser.add_argument(
        "--claim",
        choices=["groups", "roles"],
        default=None,
        help="Claim type: 'groups' (default) or 'roles'.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Group prefix for Nextcloud (e.g. 'ChurchTools-').",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Set logging level (overrides environment variable).",
    )
    parser.add_argument(
        "--log-format",
        default=None,
        help="Log format preset ('simple', 'detailed', 'compact', 'plain') or custom format string.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional path to log file (default: console logging only).",
    )
    return parser.parse_args()


async def async_run() -> int:
    args = parse_args()

    try:
        config = AppConfig.load()
    except Exception as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        return 1

    # Override config with CLI arguments if provided
    log_level = args.log_level if args.log_level is not None else config.log_level
    log_format = args.log_format if args.log_format is not None else config.log_format
    log_file = args.log_file if args.log_file is not None else config.log_file

    setup_logger(
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_rotation=config.log_rotation,
        log_retention=config.log_retention,
    )

    group_prefix = args.prefix if args.prefix is not None else config.nc_group_prefix
    groups_claim = args.claim if args.claim is not None else config.nc_groups_claim

    if args.sync:
        dry_run = False
    elif args.dry_run:
        dry_run = True
    else:
        dry_run = config.dry_run

    if args.no_remove_extra:
        remove_extra = False
    elif args.remove_extra is not None:
        remove_extra = args.remove_extra
    else:
        remove_extra = config.remove_extra_groups

    mode_label = "DRY-RUN (PREVIEW ONLY)" if dry_run else "ACTIVE SYNC (APPLYING CHANGES)"

    logger.info("=" * 60)
    logger.info("ChurchTools <-> Nextcloud Group Sync Service")
    logger.info(f"Mode:          {mode_label}")
    logger.info(f"Group Prefix:  '{group_prefix}'")
    logger.info(f"Claim Type:    '{groups_claim}'")
    logger.info(f"Remove Extra:  {remove_extra}")
    logger.info("=" * 60)

    try:
        # Initialize clients
        nc_client = NextcloudClient(
            base_url=config.nc_base_url,
            auth_user=config.nc_username,
            auth_pass=config.nc_password,
        )
        ct_client = ChurchToolsClient(
            base_url=config.ct_base_url,
            login_token=config.ct_login_token,
        )

        # 1. Fetch Nextcloud users
        nc_users = await nc_client.get_all_users()
        if not nc_users:
            logger.warning("No users found in Nextcloud. Aborting.")
            return 0

        # 2. Fetch ChurchTools persons & memberships
        ct_persons = ct_client.fetch_all_persons_with_groups()

        # 3. Fetch existing Nextcloud groups
        existing_groups = await nc_client.get_existing_groups()

        # 4. Run Sync Engine
        engine = SyncEngine(
            nc_client=nc_client,
            group_prefix=group_prefix,
            claim_type=groups_claim,
            dry_run=dry_run,
            remove_extra_groups=remove_extra,
        )

        diffs = engine.compute_diffs(nc_users, ct_persons)
        stats = await engine.execute_sync(diffs, existing_groups)

        # Summary
        logger.info("=" * 60)
        logger.info("SUMMARY:")
        logger.info(f"  Total Nextcloud users:       {stats.total_nc_users}")
        logger.info(f"  Matched with ChurchTools:    {stats.matched_users}")
        logger.info(f"  Unmatched users:             {stats.unmatched_users}")
        logger.info(f"  Users with missing groups:   {stats.users_with_missing_groups}")
        logger.info(f"  Users with extra groups:     {stats.users_with_extra_groups}")
        if not dry_run:
            logger.info(f"  New Nextcloud groups created: {stats.new_nc_groups_created}")
            logger.info(f"  Total group assignments added:   {stats.total_groups_added}")
            logger.info(f"  Total group assignments removed: {stats.total_groups_removed}")
        else:
            logger.info("  [Dry-Run completed - no changes were applied to Nextcloud]")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.exception(f"Unexpected error during sync execution: {e}")
        return 1


def main():
    sys.exit(asyncio.run(async_run()))
