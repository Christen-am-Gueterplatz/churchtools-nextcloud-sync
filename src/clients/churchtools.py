from typing import List, Optional, Dict
from urllib.parse import urljoin
import requests
from loguru import logger

from src.models import ChurchToolsPerson, GroupMembership


class ChurchToolsClient:
    """HTTP Client for ChurchTools REST API with Login Token authentication."""

    def __init__(self, base_url: str, login_token: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.login_token = login_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Login {login_token}",
            "Accept": "application/json",
        })
        self._roles_map: Optional[Dict[int, str]] = None

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        url = urljoin(self.base_url, f"api/{endpoint.lstrip('/')}")
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_roles_masterdata(self) -> Dict[int, str]:
        """Loads group role definitions from ChurchTools master data."""
        if self._roles_map is not None:
            return self._roles_map

        roles_map: Dict[int, str] = {}
        for ep in ["person/masterdata", "masterdata/person", "groups/roles"]:
            try:
                res = self._get(ep)
                data = res.get("data", res)
                if isinstance(data, dict):
                    for key in ["roles", "groupTypeRoles", "groupRoles"]:
                        if key in data and isinstance(data[key], list):
                            for r in data[key]:
                                if isinstance(r, dict) and "id" in r:
                                    name = r.get("name") or r.get("title") or r.get("shorty")
                                    if name:
                                        roles_map[int(r["id"])] = str(name).strip()
                elif isinstance(data, list):
                    for r in data:
                        if isinstance(r, dict) and "id" in r:
                            name = r.get("name") or r.get("title")
                            if name:
                                roles_map[int(r["id"])] = str(name).strip()
                if roles_map:
                    break
            except Exception as e:
                logger.debug(f"Could not load roles masterdata from '{ep}': {e}")
                continue

        self._roles_map = roles_map
        logger.debug(f"Loaded {len(roles_map)} roles from ChurchTools masterdata.")
        return self._roles_map

    def get_all_persons(self, limit: int = 100) -> List[dict]:
        """Retrieves all persons from ChurchTools with pagination."""
        persons = []
        page = 1

        while True:
            res = self._get("persons", params={"limit": limit, "page": page, "status_ids": []})
            data = res.get("data", [])
            if not data:
                break

            persons.extend(data)

            meta = res.get("meta", {})
            pagination = meta.get("pagination", {})
            total_pages = pagination.get("lastPage", page)

            if page >= total_pages or len(data) < limit:
                break

            page += 1

        return persons

    def get_person_memberships(self, person_id: int) -> List[GroupMembership]:
        """Retrieves all group memberships and roles for a specific person."""
        try:
            roles_map = self.get_roles_masterdata()
            res = self._get(f"persons/{person_id}/groups")
            groups_data = res.get("data", [])
            memberships: List[GroupMembership] = []

            for item in groups_data:
                group_info = item.get("group", {}) if isinstance(item.get("group"), dict) else {}
                title = (
                    group_info.get("title")
                    or group_info.get("name")
                    or item.get("title")
                    or item.get("name")
                )

                if not title:
                    continue

                role_name = None
                role_field = item.get("role")
                if isinstance(role_field, dict):
                    role_name = role_field.get("name") or role_field.get("title")
                elif isinstance(role_field, str):
                    role_name = role_field

                if not role_name:
                    role_name = item.get("roleName")

                if not role_name:
                    role_id = item.get("groupTypeRoleId") or item.get("roleId") or item.get("groupRoleId")
                    if role_id is not None:
                        try:
                            role_id_int = int(role_id)
                            role_name = roles_map.get(role_id_int)
                        except (ValueError, TypeError):
                            pass

                memberships.append(
                    GroupMembership(
                        group_name=str(title).strip(),
                        role_name=str(role_name).strip() if role_name else None,
                    )
                )

            return memberships
        except Exception as e:
            logger.warning(f"Could not retrieve groups for CT Person ID {person_id}: {e}")
            return []

    def fetch_all_persons_with_groups(self) -> List[ChurchToolsPerson]:
        """Loads all persons including their group memberships and roles."""
        raw_persons = self.get_all_persons()
        logger.info(f"Retrieved {len(raw_persons)} persons from ChurchTools. Fetching memberships...")

        ct_persons: List[ChurchToolsPerson] = []
        for p in raw_persons:
            pid = p.get("id")
            first_name = p.get("firstName", "")
            last_name = p.get("lastName", "")
            email = p.get("email")
            if email:
                email = email.strip()

            memberships = self.get_person_memberships(pid)

            ct_persons.append(
                ChurchToolsPerson(
                    id=pid,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    memberships=memberships,
                )
            )

        logger.info(f"Finished loading ChurchTools memberships for {len(ct_persons)} persons.")
        return ct_persons
