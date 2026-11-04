"""Organization-level Role-Based Access Control (RBAC) and tenant isolation."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from novora.core.enums import OrgRole
from novora.core.exceptions import TenantIsolationError
from novora.persistence.models import DBOrganization, DBOrganizationMembership

logger = logging.getLogger(__name__)

# Numeric role hierarchy: higher number = more privileges
ROLE_LEVELS: Dict[str, int] = {
    OrgRole.VIEWER.value: 10,
    OrgRole.MEMBER.value: 20,
    OrgRole.ADMIN.value: 30,
    OrgRole.OWNER.value: 40,
}


def has_sufficient_role(user_role: str, required_role: str | OrgRole) -> bool:
    """Return True if user_role level is >= required_role level."""
    req_val = required_role.value if isinstance(required_role, OrgRole) else str(required_role).lower()
    user_val = str(user_role).lower()
    return ROLE_LEVELS.get(user_val, 0) >= ROLE_LEVELS.get(req_val, 0)


def get_user_membership(db: Any, user_id: str, org_id: str) -> Optional[DBOrganizationMembership]:
    """Retrieve membership record for a user in a specific organization."""
    return (
        db.query(DBOrganizationMembership)
        .filter(
            DBOrganizationMembership.org_id == org_id,
            DBOrganizationMembership.user_id == user_id,
        )
        .first()
    )


def verify_org_access(
    db: Any,
    user_id: str,
    org_id: str,
    min_role: str | OrgRole = OrgRole.VIEWER,
) -> DBOrganizationMembership:
    """Verify user belongs to org with at least min_role."""
    from fastapi import HTTPException, status

    if not org_id or not org_id.strip():
        raise TenantIsolationError("Organization ID must be provided.")

    membership = get_user_membership(db, user_id, org_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: User is not a member of organization '{org_id}'.",
        )

    if not has_sufficient_role(membership.role, min_role):
        req_name = min_role.value if isinstance(min_role, OrgRole) else str(min_role)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: Action requires '{req_name}' role or higher in this organization.",
        )

    return membership


def verify_tenant_isolation(resource_org_id: str, target_org_id: str, resource_name: str = "Resource") -> None:
    """Strictly assert that a resource belongs to the target organization."""
    if not resource_org_id or not target_org_id or resource_org_id != target_org_id:
        logger.warning(
            "Tenant isolation violation detected: resource_org=%s target_org=%s resource=%s",
            resource_org_id,
            target_org_id,
            resource_name,
        )
        raise TenantIsolationError(
            f"Tenant isolation error: {resource_name} does not belong to the requested organization."
        )
