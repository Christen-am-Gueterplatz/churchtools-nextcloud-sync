from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass(frozen=True)
class GroupMembership:
    """Represents a person's membership in a ChurchTools group including their role."""
    group_name: str
    role_name: Optional[str] = None


@dataclass
class ChurchToolsPerson:
    """Represents a person retrieved from ChurchTools."""
    id: int
    first_name: str
    last_name: str
    email: Optional[str]
    memberships: List[GroupMembership] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else f"Person #{self.id}"

    def get_expected_nc_groups(self, prefix: str = "", claim_type: str = "groups") -> Set[str]:
        """
        Generates the target Nextcloud group names based on prefix and claim type.
        - 'groups' claim: <Prefix><GroupName> (e.g. 'ChurchTools-TechTeam')
        - 'roles' claim:  <Prefix><GroupName>_<RoleName> (e.g. 'ChurchTools-TechTeam_Leader')
        """
        groups: Set[str] = set()
        for m in self.memberships:
            if not m.group_name:
                continue
            if claim_type == "roles":
                if m.role_name:
                    groups.add(f"{prefix}{m.group_name}_{m.role_name}")
                else:
                    groups.add(f"{prefix}{m.group_name}")
            else:
                groups.add(f"{prefix}{m.group_name}")
        return groups


@dataclass
class NextcloudUser:
    """Represents a user retrieved from Nextcloud."""
    user_id: str
    display_name: str
    email: str
    groups: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class UserGroupDiff:
    """Calculated difference between Nextcloud groups and target ChurchTools groups for a user."""
    nc_user: NextcloudUser
    ct_person: Optional[ChurchToolsPerson]
    missing_in_nc: Set[str]  # Target groups present in CT but missing in NC
    extra_in_nc: Set[str]    # Groups in NC that are no longer present in CT (with prefix)
    is_ambiguous: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.missing_in_nc or self.extra_in_nc)


@dataclass
class SyncStats:
    """Statistics summary for a sync run."""
    total_nc_users: int = 0
    matched_users: int = 0
    unmatched_users: int = 0
    ambiguous_users: int = 0
    users_with_missing_groups: int = 0
    users_with_extra_groups: int = 0
    total_groups_added: int = 0
    total_groups_removed: int = 0
    new_nc_groups_created: int = 0

