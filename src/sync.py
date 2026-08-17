from typing import List, Dict, Set, Tuple
from loguru import logger

from src.clients.nextcloud import NextcloudClient
from src.models import (
    ChurchToolsPerson,
    NextcloudUser,
    SyncStats,
    UserGroupDiff,
)


class SyncEngine:
    """Core synchronization engine for ChurchTools and Nextcloud groups."""

    def __init__(
        self,
        nc_client: NextcloudClient,
        group_prefix: str = "ChurchTools-",
        claim_type: str = "groups",
        dry_run: bool = True,
        remove_extra_groups: bool = True,
    ):
        self.nc_client = nc_client
        self.group_prefix = group_prefix
        self.claim_type = claim_type
        self.dry_run = dry_run
        self.remove_extra_groups = remove_extra_groups

    def compute_diffs(
        self,
        nc_users: List[NextcloudUser],
        ct_persons: List[ChurchToolsPerson],
    ) -> List[UserGroupDiff]:
        """
        Matches Nextcloud users with ChurchTools persons by:
        1. Email address (case-insensitive)
        2. User ID / Person ID (e.g. '123' or 'ct_123')
        
        Calculates missing and extra groups with respect to prefix and claim type.
        """
        ct_by_email: Dict[str, ChurchToolsPerson] = {}
        ct_by_id: Dict[str, ChurchToolsPerson] = {}

        for person in ct_persons:
            ct_by_id[str(person.id)] = person
            ct_by_id[f"ct_{person.id}"] = person
            if person.email:
                ct_by_email[person.email.lower()] = person

        diff_list: List[UserGroupDiff] = []

        for nc_user in nc_users:
            matched_ct = None
            if nc_user.email and nc_user.email.lower() in ct_by_email:
                matched_ct = ct_by_email[nc_user.email.lower()]
            elif nc_user.user_id in ct_by_id:
                matched_ct = ct_by_id[nc_user.user_id]
            elif nc_user.user_id.lower() in ct_by_email:
                matched_ct = ct_by_email[nc_user.user_id.lower()]

            nc_groups_set = set(nc_user.groups)

            if matched_ct:
                expected_nc_groups = matched_ct.get_expected_nc_groups(
                    prefix=self.group_prefix, claim_type=self.claim_type
                )
            else:
                expected_nc_groups = set()

            # Missing target groups
            missing_in_nc = expected_nc_groups - nc_groups_set

            # Extra groups: only consider groups matching the prefix to protect system groups like 'admin'
            if self.group_prefix:
                nc_prefixed_groups = {g for g in nc_groups_set if g.startswith(self.group_prefix)}
                extra_in_nc = nc_prefixed_groups - expected_nc_groups
            else:
                extra_in_nc = nc_groups_set - expected_nc_groups

            diff_list.append(
                UserGroupDiff(
                    nc_user=nc_user,
                    ct_person=matched_ct,
                    missing_in_nc=missing_in_nc,
                    extra_in_nc=extra_in_nc,
                )
            )

        return diff_list

    async def execute_sync(
        self,
        diffs: List[UserGroupDiff],
        existing_groups: Set[str],
    ) -> SyncStats:
        """
        Executes group additions and removals or prints dry-run actions.
        Returns aggregate SyncStats.
        """
        stats = SyncStats(total_nc_users=len(diffs))

        for diff in diffs:
            nc_user = diff.nc_user
            ct_person = diff.ct_person

            if not ct_person:
                stats.unmatched_users += 1
                logger.debug(
                    f"No ChurchTools match for Nextcloud user '{nc_user.user_id}' "
                    f"({nc_user.display_name} | {nc_user.email})"
                )
                continue

            stats.matched_users += 1

            if diff.missing_in_nc:
                stats.users_with_missing_groups += 1

            if diff.extra_in_nc:
                stats.users_with_extra_groups += 1

            if not diff.has_changes:
                logger.debug(f"User '{nc_user.user_id}' is already in sync.")
                continue

            user_label = f"{nc_user.display_name} ({nc_user.user_id} <-> CT-ID: {ct_person.id})"

            if self.dry_run:
                if diff.missing_in_nc:
                    details = []
                    for g in sorted(diff.missing_in_nc):
                        if g not in existing_groups:
                            details.append(f"{g} [will create new NC group]")
                        else:
                            details.append(g)
                    logger.info(f"[DRY-RUN] {user_label} -> Missing groups to ADD: {details}")

                if diff.extra_in_nc:
                    if self.remove_extra_groups:
                        logger.info(f"[DRY-RUN] {user_label} -> Extra groups to REMOVE: {sorted(list(diff.extra_in_nc))}")
                    else:
                        logger.debug(f"[DRY-RUN] {user_label} -> Extra groups (removal skipped): {sorted(list(diff.extra_in_nc))}")
            else:
                # 1. Add missing groups
                for group_name in sorted(diff.missing_in_nc):
                    try:
                        created = await self.nc_client.ensure_group_exists(group_name, existing_groups)
                        if created:
                            stats.new_nc_groups_created += 1

                        await self.nc_client.add_user_to_group(nc_user.user_id, group_name)
                        stats.total_groups_added += 1
                        logger.info(f"Added '{nc_user.user_id}' to group '{group_name}'")
                    except Exception as e:
                        logger.error(f"Failed to add '{nc_user.user_id}' to group '{group_name}': {e}")

                # 2. Remove extra groups
                if self.remove_extra_groups:
                    for group_name in sorted(diff.extra_in_nc):
                        try:
                            await self.nc_client.remove_user_from_group(nc_user.user_id, group_name)
                            stats.total_groups_removed += 1
                            logger.info(f"Removed '{nc_user.user_id}' from group '{group_name}'")
                        except Exception as e:
                            logger.error(f"Failed to remove '{nc_user.user_id}' from group '{group_name}': {e}")

        return stats
