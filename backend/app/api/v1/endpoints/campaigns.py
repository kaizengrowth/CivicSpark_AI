from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models import Campaign, CampaignMembership, User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignMembershipResponse,
    CampaignResponse,
    CampaignUpdate,
    UserCampaignSummary,
)
from app.services.auth import get_current_active_user

router = APIRouter()


def add_user_membership_info(
    campaign: Campaign, user_id: int | None = None
) -> CampaignResponse:
    """Add user membership information to campaign response"""
    campaign_data = CampaignResponse.model_validate(campaign)

    if user_id:
        # Check if user is a member
        membership = next(
            (m for m in campaign.memberships if m.user_id == user_id), None
        )
        if membership:
            campaign_data.is_member = True
            campaign_data.membership_role = membership.role
        else:
            campaign_data.is_member = False
            campaign_data.membership_role = None

    return campaign_data


@router.get("/", response_model=CampaignListResponse)
async def list_campaigns(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    status: str | None = Query("active"),
    featured: bool | None = Query(None),
    search: str | None = Query(None),
):
    """Get list of campaigns with pagination and filtering"""

    query = db.query(Campaign).options(selectinload(Campaign.memberships))

    # Filter by public campaigns (unless user is authenticated)
    if not current_user:
        query = query.filter(Campaign.is_public == True)

    # Apply filters
    if category:
        query = query.filter(Campaign.category == category)

    if status:
        query = query.filter(Campaign.status == status)

    if featured is not None:
        query = query.filter(Campaign.featured == featured)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Campaign.title.ilike(search_term),
                Campaign.description.ilike(search_term),
                Campaign.short_description.ilike(search_term),
            )
        )

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    campaigns = (
        query.order_by(desc(Campaign.featured), desc(Campaign.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Add user membership info
    campaign_responses = []
    for campaign in campaigns:
        campaign_data = add_user_membership_info(
            campaign, current_user.id if current_user else None
        )
        campaign_responses.append(campaign_data)

    total_pages = (total + limit - 1) // limit

    return CampaignListResponse(
        campaigns=campaign_responses,
        total=total,
        page=(skip // limit) + 1,
        per_page=limit,
        total_pages=total_pages,
    )


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_data: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new campaign"""

    # Create campaign
    campaign = Campaign(creator_id=current_user.id, **campaign_data.model_dump())

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    # Automatically make creator an admin member
    membership = CampaignMembership(
        campaign_id=campaign.id,
        user_id=current_user.id,
        role="admin",
        can_post_updates=True,
        can_manage_members=True,
        can_edit_campaign=True,
    )

    db.add(membership)
    campaign.member_count = 1
    db.commit()
    db.refresh(campaign)

    # Load memberships for response
    db.refresh(campaign)
    campaign = (
        db.query(Campaign)
        .options(selectinload(Campaign.memberships))
        .filter(Campaign.id == campaign.id)
        .first()
    )

    return add_user_membership_info(campaign, current_user.id)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_active_user),
):
    """Get a specific campaign by ID"""

    campaign = (
        db.query(Campaign)
        .options(selectinload(Campaign.memberships))
        .filter(Campaign.id == campaign_id)
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )

    # Check if user can view this campaign
    if not campaign.is_public and (
        not current_user or campaign.creator_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to private campaign",
        )

    # Increment view count
    campaign.views += 1
    db.commit()

    return add_user_membership_info(campaign, current_user.id if current_user else None)


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    campaign_update: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a campaign"""

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )

    # Check permissions
    membership = (
        db.query(CampaignMembership)
        .filter(
            and_(
                CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == current_user.id,
                or_(
                    CampaignMembership.can_edit_campaign == True,
                    CampaignMembership.role == "admin",
                ),
            )
        )
        .first()
    )

    if not membership and campaign.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to edit this campaign",
        )

    # Update campaign
    update_data = campaign_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    campaign.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(campaign)

    # Load with memberships
    campaign = (
        db.query(Campaign)
        .options(selectinload(Campaign.memberships))
        .filter(Campaign.id == campaign.id)
        .first()
    )

    return add_user_membership_info(campaign, current_user.id)


@router.post("/{campaign_id}/join", response_model=CampaignMembershipResponse)
async def join_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Join a campaign as a member"""

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )

    if not campaign.allow_new_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This campaign is not accepting new members",
        )

    # Check if user is already a member
    existing_membership = (
        db.query(CampaignMembership)
        .filter(
            and_(
                CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == current_user.id,
            )
        )
        .first()
    )

    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this campaign",
        )

    # Create membership
    membership = CampaignMembership(
        campaign_id=campaign_id,
        user_id=current_user.id,
        role="member",
    )

    db.add(membership)

    # Update member count
    campaign.member_count += 1
    db.commit()
    db.refresh(membership)

    return CampaignMembershipResponse.model_validate(membership)


@router.delete("/{campaign_id}/leave")
async def leave_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Leave a campaign"""

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )

    # Can't leave if you're the creator
    if campaign.creator_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign creator cannot leave their own campaign",
        )

    membership = (
        db.query(CampaignMembership)
        .filter(
            and_(
                CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == current_user.id,
            )
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this campaign",
        )

    db.delete(membership)

    # Update member count
    campaign.member_count = max(0, campaign.member_count - 1)
    db.commit()

    return {"message": "Successfully left campaign"}


@router.get("/me/subscriptions", response_model=UserCampaignSummary)
async def get_user_campaign_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get user's campaign subscriptions for dashboard"""

    # Get user's campaign memberships
    memberships = (
        db.query(CampaignMembership)
        .options(selectinload(CampaignMembership.campaign))
        .filter(CampaignMembership.user_id == current_user.id)
        .all()
    )

    # Filter active campaigns
    active_campaigns = []
    for membership in memberships:
        if membership.campaign.status == "active":
            campaign_data = add_user_membership_info(
                membership.campaign, current_user.id
            )
            active_campaigns.append(campaign_data)

    return UserCampaignSummary(
        total_subscribed=len(memberships),
        active_campaigns=active_campaigns,
        recent_updates=0,  # TODO: Implement campaign updates count
    )
