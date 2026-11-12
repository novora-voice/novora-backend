"""Organization and RBAC management routes."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from novora.api.auth import get_current_user
from novora.api.auth_utils import UserOrm, get_db
from novora.core.enums import OrgRole
from novora.core.rbac import (
    ROLE_LEVELS,
    get_user_membership,
    verify_org_access,
)
from novora.persistence.models import DBOrganization, DBOrganizationMembership

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned) or "org"


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: Optional[str] = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: str
    role: Optional[str] = None


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    created_at: str


class AddMemberRequest(BaseModel):
    email: str
    role: str = Field(default="member", pattern=r"^(owner|admin|member|viewer)$")


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member|viewer)$")


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    req: CreateOrganizationRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Create a new organization. The creator automatically becomes the OWNER."""
    slug_base = req.slug or _slugify(req.name)
    existing_slug = db.query(DBOrganization).filter(DBOrganization.slug == slug_base).first()
    slug = f"{slug_base}-{uuid.uuid4().hex[:6]}" if existing_slug else slug_base

    org = DBOrganization(
        id=f"org_{uuid.uuid4().hex[:12]}",
        name=req.name.strip(),
        slug=slug,
    )
    db.add(org)
    db.flush()

    # Add current user as OWNER
    membership = DBOrganizationMembership(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        org_id=org.id,
        user_id=current_user.id,
        role=OrgRole.OWNER.value,
    )
    db.add(membership)
    db.commit()
    db.refresh(org)

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at.isoformat() if org.created_at else "",
        role=OrgRole.OWNER.value,
    )


@router.get("", response_model=List[OrganizationResponse])
def list_user_organizations(
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[OrganizationResponse]:
    """List all organizations the authenticated user belongs to."""
    memberships = (
        db.query(DBOrganizationMembership)
        .filter(DBOrganizationMembership.user_id == current_user.id)
        .all()
    )
    if not memberships:
        return []

    org_map = {m.org_id: m.role for m in memberships}
    orgs = db.query(DBOrganization).filter(DBOrganization.id.in_(org_map.keys())).all()

    return [
        OrganizationResponse(
            id=o.id,
            name=o.name,
            slug=o.slug,
            created_at=o.created_at.isoformat() if o.created_at else "",
            role=org_map.get(o.id),
        )
        for o in orgs
    ]


@router.get("/{org_id}", response_model=OrganizationResponse)
def get_organization(
    org_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Get organization details. Requires VIEWER role or higher."""
    membership = verify_org_access(db, current_user.id, org_id, min_role=OrgRole.VIEWER)
    org = db.query(DBOrganization).filter(DBOrganization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at.isoformat() if org.created_at else "",
        role=membership.role,
    )


# ---------------------------------------------------------------------------
# Organization Membership Management
# ---------------------------------------------------------------------------

@router.get("/{org_id}/members", response_model=List[MemberResponse])
def list_organization_members(
    org_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[MemberResponse]:
    """List all members of an organization. Requires VIEWER role or higher."""
    verify_org_access(db, current_user.id, org_id, min_role=OrgRole.VIEWER)

    memberships = (
        db.query(DBOrganizationMembership)
        .filter(DBOrganizationMembership.org_id == org_id)
        .all()
    )
    user_ids = [m.user_id for m in memberships]
    users = db.query(UserOrm).filter(UserOrm.id.in_(user_ids)).all()
    user_dict = {u.id: u for u in users}

    result = []
    for m in memberships:
        user = user_dict.get(m.user_id)
        result.append(
            MemberResponse(
                id=m.id,
                user_id=m.user_id,
                email=user.email if user else None,
                full_name=user.full_name if user else None,
                role=m.role,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
        )
    return result


@router.post("/{org_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_organization_member(
    org_id: str,
    req: AddMemberRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberResponse:
    """Add or invite a member to the organization. Requires ADMIN role or higher."""
    caller_membership = verify_org_access(db, current_user.id, org_id, min_role=OrgRole.ADMIN)

    # Only OWNER can grant OWNER role
    if req.role == OrgRole.OWNER.value and caller_membership.role != OrgRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization Owner can assign the Owner role.",
        )

    # Look up target user by email
    target_user = db.query(UserOrm).filter(UserOrm.email == req.email.strip()).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{req.email}' not found.",
        )

    existing = get_user_membership(db, target_user.id, org_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization.",
        )

    membership = DBOrganizationMembership(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        user_id=target_user.id,
        role=req.role.lower(),
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return MemberResponse(
        id=membership.id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=membership.role,
        created_at=membership.created_at.isoformat() if membership.created_at else "",
    )


@router.patch("/{org_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(
    org_id: str,
    user_id: str,
    req: UpdateMemberRoleRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberResponse:
    """Update a member's role. Requires ADMIN role or higher."""
    caller = verify_org_access(db, current_user.id, org_id, min_role=OrgRole.ADMIN)

    target_membership = get_user_membership(db, user_id, org_id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found in organization.")

    # Only OWNER can modify another OWNER or promote to OWNER
    if (target_membership.role == OrgRole.OWNER.value or req.role == OrgRole.OWNER.value) and caller.role != OrgRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Owner can transfer ownership or modify an Owner's role.",
        )

    target_membership.role = req.role.lower()
    db.commit()
    db.refresh(target_membership)

    target_user = db.query(UserOrm).filter(UserOrm.id == user_id).first()
    return MemberResponse(
        id=target_membership.id,
        user_id=user_id,
        email=target_user.email if target_user else None,
        full_name=target_user.full_name if target_user else None,
        role=target_membership.role,
        created_at=target_membership.created_at.isoformat() if target_membership.created_at else "",
    )


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_organization_member(
    org_id: str,
    user_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a member from the organization. Requires ADMIN or higher. Users can also remove themselves."""
    caller = verify_org_access(db, current_user.id, org_id, min_role=OrgRole.VIEWER)

    # A user can remove themselves, or an ADMIN can remove others
    is_self = caller.user_id == user_id
    if not is_self and not (caller.role in (OrgRole.OWNER.value, OrgRole.ADMIN.value)):
        raise HTTPException(status_code=403, detail="Insufficient permissions to remove members.")

    target_membership = get_user_membership(db, user_id, org_id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found in organization.")

    # Cannot remove an OWNER unless caller is also OWNER and there's another OWNER
    if target_membership.role == OrgRole.OWNER.value and not is_self:
        raise HTTPException(status_code=403, detail="Cannot remove an Owner.")

    db.delete(target_membership)
    db.commit()
