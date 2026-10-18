import unittest
from unittest.mock import AsyncMock, Mock

import requests

from src.clients.churchtools import ChurchToolsClient
from src.models import ChurchToolsPerson, NextcloudUser, UserGroupDiff
from src.sync import SyncEngine


class FailedMembershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ct = ChurchToolsClient("https://example.invalid", "test-token")
        self.ct._roles_map = {}
        self.ct._get = Mock()
        self.ct.get_all_persons = Mock(return_value=[
            {"id": 94, "firstName": "Test", "lastName": "Person", "email": "test@example.invalid"},
        ])
        self.nc = Mock()
        self.nc.add_user_to_group = AsyncMock()
        self.nc.remove_user_from_group = AsyncMock()
        self.engine = SyncEngine(self.nc, dry_run=False)
        self.user = NextcloudUser(
            "ChurchTools-94", "Test Person", "test@example.invalid",
            groups=["admin", "ChurchTools-Escape-Room"],
        )

    async def test_failed_or_invalid_lookup_never_changes_groups(self):
        cases = [
            requests.Timeout("timeout"),
            requests.HTTPError("503 Service Unavailable"),
            ValueError("Invalid JSON"),
            {},
            {"data": None},
            {"data": {}},
            {"data": [{"group": {}}]},
            {"data": [{"group": {"title": "Valid"}}, {"group": {}}]},
        ]
        for case in cases:
            with self.subTest(response=case):
                self.ct._get.side_effect = case if isinstance(case, Exception) else None
                self.ct._get.return_value = case
                persons = self.ct.fetch_all_persons_with_groups()
                self.assertEqual(len(persons), 1)
                self.assertIsNone(persons[0].memberships)
                diffs = self.engine.compute_diffs([self.user], persons)
                self.assertIs(diffs[0].ct_person, persons[0])
                self.assertFalse(diffs[0].has_changes)
                stats = await self.engine.execute_sync(diffs, set(self.user.groups))
                self.assertEqual(stats.users_with_failed_memberships, 1)
                self.nc.add_user_to_group.assert_not_awaited()
                self.nc.remove_user_from_group.assert_not_awaited()
                self.nc.ensure_group_exists.assert_not_called()

    async def test_successful_empty_lookup_still_removes_obsolete_groups(self):
        self.ct._get.return_value = {"data": []}
        persons = self.ct.fetch_all_persons_with_groups()
        self.assertEqual(persons[0].memberships, [])
        diffs = self.engine.compute_diffs([self.user], persons)
        stats = await self.engine.execute_sync(diffs, set(self.user.groups))
        self.nc.remove_user_from_group.assert_awaited_once_with(
            "ChurchTools-94", "ChurchTools-Escape-Room"
        )
        self.assertEqual(stats.total_groups_removed, 1)
        self.assertEqual(stats.users_with_failed_memberships, 0)

    async def test_next_successful_lookup_restores_normal_sync(self):
        self.ct._get.side_effect = requests.Timeout("timeout")
        persons = self.ct.fetch_all_persons_with_groups()
        await self.engine.execute_sync(self.engine.compute_diffs([self.user], persons), set())
        self.ct._get.side_effect = None
        self.ct._get.return_value = {"data": [{"group": {"title": "Escape-Room"}}]}
        persons = self.ct.fetch_all_persons_with_groups()
        self.user.groups = ["admin"]
        self.nc.ensure_group_exists = AsyncMock(return_value=False)
        stats = await self.engine.execute_sync(self.engine.compute_diffs([self.user], persons), set())
        self.nc.add_user_to_group.assert_awaited_once_with(
            "ChurchTools-94", "ChurchTools-Escape-Room"
        )
        self.assertEqual(stats.total_groups_added, 1)
        self.nc.remove_user_from_group.assert_not_awaited()

    async def test_execution_also_rejects_changes_for_failed_lookup(self):
        person = ChurchToolsPerson(94, "Test", "Person", self.user.email, memberships=None)
        diff = UserGroupDiff(self.user, person, {"ChurchTools-New"}, {"ChurchTools-Escape-Room"})
        stats = await self.engine.execute_sync([diff], set())
        self.assertEqual(stats.users_with_failed_memberships, 1)
        self.nc.add_user_to_group.assert_not_awaited()
        self.nc.remove_user_from_group.assert_not_awaited()

    async def test_archived_membership_is_requested_and_preserved(self):
        self.ct._get.return_value = {"data": [{
            "group": {
                "title": "Escape-Room",
                "domainAttributes": {"groupStatusId": 3},
            },
            "groupMemberStatus": "active",
        }]}
        persons = self.ct.fetch_all_persons_with_groups()
        self.ct._get.assert_called_once_with(
            "persons/94/groups", params={"show_inactive_groups": "true"}
        )
        diffs = self.engine.compute_diffs([self.user], persons)
        self.assertFalse(diffs[0].has_changes)
        stats = await self.engine.execute_sync(diffs, set(self.user.groups))
        self.assertEqual(stats.total_groups_removed, 0)
        self.nc.remove_user_from_group.assert_not_awaited()

    async def test_missing_archived_membership_is_added(self):
        self.ct._get.return_value = {"data": [{
            "group": {
                "title": "Escape-Room",
                "domainAttributes": {"groupStatusId": 3},
            },
            "groupMemberStatus": "active",
        }]}
        persons = self.ct.fetch_all_persons_with_groups()
        self.user.groups = ["admin"]
        self.nc.ensure_group_exists = AsyncMock(return_value=False)
        stats = await self.engine.execute_sync(
            self.engine.compute_diffs([self.user], persons), {"ChurchTools-Escape-Room"}
        )
        self.assertEqual(stats.total_groups_added, 1)
        self.nc.add_user_to_group.assert_awaited_once_with(
            "ChurchTools-94", "ChurchTools-Escape-Room"
        )
        self.nc.remove_user_from_group.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
