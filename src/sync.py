import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
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

    def _build_indices(
        self, ct_persons: List[ChurchToolsPerson]
    ) -> Tuple[
        Dict[str, ChurchToolsPerson],
        Dict[int, ChurchToolsPerson],
        Dict[str, List[ChurchToolsPerson]],
        Dict[str, List[ChurchToolsPerson]],
    ]:
        """
        Builds lookup dictionaries for ChurchTools persons:
        - ct_by_id_str: Normalized string ID -> Person (e.g. '123', 'ct-123', 'churchtools-123')
        - ct_by_int_id: Integer ID -> Person (e.g. 123)
        - ct_by_email: Lowercase email -> List[Person] (supports multiple persons sharing one email)
        - ct_by_name: Normalized full name -> List[Person]
        """
        ct_by_id_str: Dict[str, ChurchToolsPerson] = {}
        ct_by_int_id: Dict[int, ChurchToolsPerson] = {}
        ct_by_email: Dict[str, List[ChurchToolsPerson]] = defaultdict(list)
        ct_by_name: Dict[str, List[ChurchToolsPerson]] = defaultdict(list)

        prefix_clean = self.group_prefix.strip("-_").lower() if self.group_prefix else ""

        for person in ct_persons:
            pid = person.id
            ct_by_int_id[pid] = person

            # String ID patterns for lookup
            pid_str = str(pid)
            ct_by_id_str[pid_str] = person
            ct_by_id_str[f"ct_{pid}"] = person
            ct_by_id_str[f"ct-{pid}"] = person
            ct_by_id_str[f"churchtools_{pid}"] = person
            ct_by_id_str[f"churchtools-{pid}"] = person

            if prefix_clean:
                ct_by_id_str[f"{prefix_clean}_{pid}"] = person
                ct_by_id_str[f"{prefix_clean}-{pid}"] = person
                if self.group_prefix:
                    ct_by_id_str[f"{self.group_prefix.lower()}{pid}"] = person

            # Email indexing (allows multiple persons per email, e.g. families)
            if person.email and person.email.strip():
                ct_by_email[person.email.strip().lower()].append(person)

            # Name indexing
            fn = person.first_name.strip().lower()
            ln = person.last_name.strip().lower()
            if fn and ln:
                ct_by_name[f"{fn} {ln}"].append(person)
                ct_by_name[f"{ln}, {fn}"].append(person)
                ct_by_name[f"{ln} {fn}"].append(person)
            elif fn:
                ct_by_name[fn].append(person)
            elif ln:
                ct_by_name[ln].append(person)

        return ct_by_id_str, ct_by_int_id, ct_by_email, ct_by_name

    def _disambiguate_email_candidates(
        self, nc_user: NextcloudUser, candidates: List[ChurchToolsPerson]
    ) -> Optional[ChurchToolsPerson]:
        """
        When multiple ChurchTools persons share the same email address (e.g. couples/families),
        disambiguates using display name and user ID signals.
        Returns the unique best match or None if ambiguous.
        """
        nc_display = nc_user.display_name.strip().lower()
        nc_uid = nc_user.user_id.strip().lower()

        candidate_scores: List[Tuple[int, ChurchToolsPerson]] = []

        for c in candidates:
            score = 0
            c_first = c.first_name.strip().lower()
            c_last = c.last_name.strip().lower()
            c_full = f"{c_first} {c_last}".strip()

            # 1. Exact full name match in display name
            if nc_display and (
                nc_display == c_full
                or nc_display == f"{c_last} {c_first}"
                or nc_display == f"{c_last}, {c_first}"
            ):
                score += 100

            # 2. Both first and last name present in display name
            elif c_first and c_last and c_first in nc_display and c_last in nc_display:
                score += 70

            # 3. First name match in display name (e.g. "Steffen" vs "Sabine")
            elif c_first and (
                c_first == nc_display
                or c_first in nc_display.split()
                or nc_display.startswith(f"{c_first} ")
                or nc_display.endswith(f" {c_first}")
            ):
                score += 40

            # 4. User ID signals (e.g. username containing first/last name)
            if c_first and c_last and (c_first in nc_uid and c_last in nc_uid):
                score += 50
            elif c_first and (c_first in nc_uid.split(".") or c_first in nc_uid.split("_") or c_first in nc_uid):
                score += 30

            candidate_scores.append((score, c))

        # Sort by score descending
        candidate_scores.sort(key=lambda x: x[0], reverse=True)
        top_score, best_candidate = candidate_scores[0]

        if top_score > 0:
            # Check if there is a tie for the top score
            if len(candidate_scores) > 1 and candidate_scores[1][0] == top_score:
                return None
            return best_candidate

        return None

    def match_user(
        self,
        nc_user: NextcloudUser,
        ct_by_id_str: Dict[str, ChurchToolsPerson],
        ct_by_int_id: Dict[int, ChurchToolsPerson],
        ct_by_email: Dict[str, List[ChurchToolsPerson]],
        ct_by_name: Dict[str, List[ChurchToolsPerson]],
    ) -> Tuple[Optional[ChurchToolsPerson], bool]:
        """
        Matches a Nextcloud user to a ChurchTools person with the following priority:
        1. User ID / CT Person ID (e.g. 'ChurchTools-123', 'ct-123', '123')
        2. Email address (with smart name disambiguation if multiple persons share the same email)
        3. Unique display name match (fallback)

        Returns a tuple of (matched_ct_person, is_ambiguous).
        """
        uid = nc_user.user_id.strip()
        uid_lower = uid.lower()

        # --- Priority 1: User ID / Person ID Match ---
        # 1a. Direct lookup in indexed ID strings
        if uid_lower in ct_by_id_str:
            return ct_by_id_str[uid_lower], False

        # 1b. Extract numeric ID from username pattern (e.g. 'provider-123', 'user_123', '123')
        id_match = re.match(r"^(?:[a-zA-Z0-9_-]+?[_-])?(\d+)$", uid)
        if id_match:
            try:
                extracted_id = int(id_match.group(1))
                if extracted_id in ct_by_int_id:
                    return ct_by_int_id[extracted_id], False
            except ValueError:
                pass

        # --- Priority 2: Email Match (with Disambiguation) ---
        user_email = nc_user.email.strip().lower() if nc_user.email else ""
        if not user_email and "@" in uid:
            user_email = uid_lower

        if user_email and user_email in ct_by_email:
            candidates = ct_by_email[user_email]
            if len(candidates) == 1:
                return candidates[0], False

            # Multiple persons share this email address
            best_match = self._disambiguate_email_candidates(nc_user, candidates)
            if best_match:
                logger.debug(
                    f"Disambiguated shared email '{user_email}' for Nextcloud user '{nc_user.user_id}' "
                    f"({nc_user.display_name}) -> matched CT person '{best_match.full_name}' (CT-ID: {best_match.id})"
                )
                return best_match, False
            else:
                candidates_str = ", ".join(f"'{c.full_name}' (ID: {c.id})" for c in candidates)
                logger.warning(
                    f"Ambiguous match: Nextcloud user '{nc_user.user_id}' ({nc_user.display_name}) "
                    f"shares email '{user_email}' with multiple ChurchTools persons [{candidates_str}]. "
                    "Skipping user to prevent assigning incorrect groups."
                )
                return None, True

        # --- Priority 3: Display Name Match (Fallback) ---
        nc_display = nc_user.display_name.strip().lower()
        if nc_display and nc_display in ct_by_name:
            candidates = ct_by_name[nc_display]
            if len(candidates) == 1:
                logger.debug(
                    f"Matched Nextcloud user '{nc_user.user_id}' to CT person "
                    f"'{candidates[0].full_name}' (CT-ID: {candidates[0].id}) via display name."
                )
                return candidates[0], False

        return None, False

    def compute_diffs(
        self,
        nc_users: List[NextcloudUser],
        ct_persons: List[ChurchToolsPerson],
    ) -> List[UserGroupDiff]:
        """
        Matches Nextcloud users with ChurchTools persons by:
        1. User ID / Person ID (e.g. 'ChurchTools-123', 'ct-123', '123')
        2. Email address (with automatic name disambiguation when persons share an email)
        3. Unique display name (fallback)

        Calculates missing and extra groups with respect to prefix and claim type.
        """
        ct_by_id_str, ct_by_int_id, ct_by_email, ct_by_name = self._build_indices(ct_persons)

        diff_list: List[UserGroupDiff] = []

        for nc_user in nc_users:
            matched_ct, is_ambiguous = self.match_user(
                nc_user=nc_user,
                ct_by_id_str=ct_by_id_str,
                ct_by_int_id=ct_by_int_id,
                ct_by_email=ct_by_email,
                ct_by_name=ct_by_name,
            )

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
                    is_ambiguous=is_ambiguous,
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
                if diff.is_ambiguous:
                    stats.ambiguous_users += 1
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
