from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.organization import Organization
from app.schemas.base import PaginationParams, StandardListResponse
from app.schemas.organization import Organization as OrganizationSchema
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
)

router = APIRouter()


@router.get("/", response_model=StandardListResponse[OrganizationSchema])
def list_organizations(
    pagination: PaginationParams = Depends(),
    search: str | None = Query(
        None, description="Search in organization name and description"
    ),
    organization_type: str | None = Query(
        None, description="Filter by organization type"
    ),
    focus_area: str | None = Query(None, description="Filter by focus area"),
    verified_only: bool = Query(False, description="Show only verified organizations"),
    active_only: bool = Query(True, description="Show only active organizations"),
    db: Session = Depends(get_db),
):
    """
    Get a list of organizations with optional filtering and search
    """
    query = db.query(Organization)

    # Apply filters
    if active_only:
        query = query.filter(Organization.is_active)

    if verified_only:
        query = query.filter(Organization.is_verified == True)

    if organization_type:
        query = query.filter(Organization.organization_type == organization_type)

    if focus_area:
        # Search in the JSON focus_areas field
        query = query.filter(Organization.focus_areas.contains([focus_area]))

    if search:
        search_filter = or_(
            Organization.name.ilike(f"%{search}%"),
            Organization.description.ilike(f"%{search}%"),
            Organization.short_description.ilike(f"%{search}%"),
        )
        query = query.filter(search_filter)

    # Get total count before applying pagination
    total = query.count()

    # Apply pagination and ordering
    organizations = (
        query.order_by(
            Organization.is_verified.desc(),  # Verified organizations first
            Organization.name.asc(),
        )
        .offset(pagination.skip)
        .limit(pagination.limit)
        .all()
    )

    return StandardListResponse[OrganizationSchema].create(
        items=organizations, total=total, skip=pagination.skip, limit=pagination.limit
    )


@router.get("/{organization_id}", response_model=OrganizationSchema)
def get_organization(organization_id: int, db: Session = Depends(get_db)):
    """
    Get a single organization by ID
    """
    organization = (
        db.query(Organization)
        .filter(
            and_(Organization.id == organization_id, Organization.is_active == True)
        )
        .first()
    )

    if not organization:
        raise NotFoundError("Organization", organization_id)

    return organization


@router.get("/slug/{slug}", response_model=OrganizationSchema)
def get_organization_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Get a single organization by slug
    """
    organization = (
        db.query(Organization)
        .filter(and_(Organization.slug == slug, Organization.is_active == True))
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    return organization


@router.post(
    "/", response_model=OrganizationSchema, status_code=status.HTTP_201_CREATED
)
def create_organization(
    organization_data: OrganizationCreate,
    db: Session = Depends(get_db),
    # TODO: Add authentication dependency when user auth is implemented
    # current_user: User = Depends(get_current_active_user)
):
    """
    Create a new organization (admin only for now)
    """
    # Check if slug already exists
    existing_org = (
        db.query(Organization)
        .filter(Organization.slug == organization_data.slug)
        .first()
    )
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization with this slug already exists",
        )

    # Create organization
    organization = Organization(**organization_data.dict())
    db.add(organization)
    db.commit()
    db.refresh(organization)

    return organization


@router.put("/{organization_id}", response_model=OrganizationSchema)
def update_organization(
    organization_id: int,
    organization_data: OrganizationUpdate,
    db: Session = Depends(get_db),
    # TODO: Add authentication dependency when user auth is implemented
    # current_user: User = Depends(get_current_active_user)
):
    """
    Update an organization (admin or organization account only)
    """
    organization = (
        db.query(Organization).filter(Organization.id == organization_id).first()
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Update fields
    update_data = organization_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(organization, field, value)

    db.commit()
    db.refresh(organization)

    return organization


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    # TODO: Add authentication dependency when user auth is implemented
    # current_user: User = Depends(get_current_active_user)
):
    """
    Soft delete an organization (admin only)
    """
    organization = (
        db.query(Organization).filter(Organization.id == organization_id).first()
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Soft delete by marking as inactive
    organization.is_active = False
    db.commit()


@router.get("/types/list", response_model=list[str])
def get_organization_types(db: Session = Depends(get_db)):
    """
    Get list of all organization types currently in use
    """
    types = (
        db.query(Organization.organization_type)
        .distinct()
        .filter(
            Organization.organization_type.isnot(None), Organization.is_active == True
        )
        .all()
    )

    return [t[0] for t in types if t[0]]


@router.get("/focus-areas/list", response_model=list[str])
def get_focus_areas(db: Session = Depends(get_db)):
    """
    Get list of all focus areas currently in use
    """
    # This is a simplified version - in production, you might want to use a more sophisticated query
    organizations = (
        db.query(Organization.focus_areas)
        .filter(Organization.focus_areas.isnot(None), Organization.is_active == True)
        .all()
    )

    focus_areas = set()
    for org in organizations:
        if org[0]:  # focus_areas is a JSON field
            focus_areas.update(org[0])

    return sorted(list(focus_areas))


@router.get("/stats", response_model=dict)
def get_organization_stats(db: Session = Depends(get_db)):
    """
    Get organization statistics for dashboard/overview
    """
    total_orgs = db.query(Organization).filter(Organization.is_active == True).count()
    verified_orgs = (
        db.query(Organization)
        .filter(and_(Organization.is_active == True, Organization.is_verified == True))
        .count()
    )

    # Count by type
    type_stats = (
        db.query(
            Organization.organization_type, func.count(Organization.id).label("count")
        )
        .filter(
            Organization.is_active == True, Organization.organization_type.isnot(None)
        )
        .group_by(Organization.organization_type)
        .all()
    )

    return {
        "total_organizations": total_orgs,
        "verified_organizations": verified_orgs,
        "organizations_by_type": {stat[0]: stat[1] for stat in type_stats},
    }
