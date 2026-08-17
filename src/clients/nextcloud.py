import asyncio
from typing import List, Optional, Set
from loguru import logger
from nc_py_api import AsyncNextcloud
from nc_py_api.users import UserInfo

from src.models import NextcloudUser


class NextcloudClient:
    """Asynchronous client for interacting with Nextcloud Provisioning API."""

    def __init__(self, base_url: str, auth_user: str, auth_pass: str):
        self.client = AsyncNextcloud(
            nextcloud_url=base_url.rstrip("/"),
            nc_auth_user=auth_user,
            nc_auth_pass=auth_pass,
        )

    async def fetch_all_user_ids(self, page_size: int = 100) -> List[str]:
        """Retrieves all Nextcloud user IDs using pagination."""
        all_user_ids: List[str] = []
        offset = 0

        while True:
            users_batch = await self.client.users.get_list(limit=page_size, offset=offset)
            if not users_batch:
                break

            all_user_ids.extend(users_batch)

            if len(users_batch) < page_size:
                break

            offset += page_size

        return all_user_ids

    async def get_all_users(self, concurrency: int = 10) -> List[NextcloudUser]:
        """Loads all Nextcloud users with their details and groups concurrently."""
        user_ids = await self.fetch_all_user_ids()
        logger.info(f"Retrieved {len(user_ids)} users from Nextcloud. Loading user details...")

        semaphore = asyncio.Semaphore(concurrency)
        users_data: List[NextcloudUser] = []

        async def fetch_single_user(uid: str) -> Optional[NextcloudUser]:
            async with semaphore:
                try:
                    info: UserInfo = await self.client.users.get_user(uid)
                    return NextcloudUser(
                        user_id=info.user_id,
                        display_name=info.display_name,
                        email=info.email.strip() if info.email else "",
                        groups=info.groups or [],
                        enabled=info.enabled,
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch details for Nextcloud user '{uid}': {e}")
                    return None

        tasks = [fetch_single_user(uid) for uid in user_ids]
        results = await asyncio.gather(*tasks)

        for res in results:
            if res is not None:
                users_data.append(res)

        logger.info(f"Finished loading {len(users_data)} Nextcloud users.")
        return users_data

    async def get_existing_groups(self) -> Set[str]:
        """Retrieves the set of all existing group IDs in Nextcloud."""
        try:
            groups = await self.client.users_groups.get_list()
            return set(groups) if groups else set()
        except Exception as e:
            logger.error(f"Failed to fetch existing Nextcloud groups: {e}")
            return set()

    async def ensure_group_exists(self, group_name: str, existing_groups: Set[str]) -> bool:
        """
        Ensures a Nextcloud group exists, creating it if necessary.
        Returns True if a new group was created, False otherwise.
        """
        if group_name not in existing_groups:
            try:
                await self.client.users_groups.create(group_name)
                existing_groups.add(group_name)
                logger.info(f"Created new Nextcloud group: '{group_name}'")
                return True
            except Exception as e:
                logger.warning(f"Group creation check for '{group_name}': {e}")
                existing_groups.add(group_name)
        return False

    async def add_user_to_group(self, user_id: str, group_name: str) -> None:
        """Adds a user to a Nextcloud group."""
        await self.client.users.add_to_group(user_id, group_name)

    async def remove_user_from_group(self, user_id: str, group_name: str) -> None:
        """Removes a user from a Nextcloud group."""
        await self.client.users.remove_from_group(user_id, group_name)
