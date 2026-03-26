"""Admin API routes for configuration management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field

from models.database import get_db
from models.entity_type_domain_mapping import EntityTypeDomainMapping
from agents.entity_classifier import EntityClassifier

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Pydantic Models ─────────────────────────────────────────────────────


class EntityMappingCreate(BaseModel):
    """Request model for creating/updating entity type mapping."""

    entity_type: str = Field(..., description="Entity type (e.g., 'Person', 'Organization')")
    primary_domain: str = Field(..., description="Primary domain (e.g., 'geopolitics', 'economics')")
    secondary_domains: List[str] = Field(default_factory=list, description="Secondary domains")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score (0-1)")


class EntityMappingResponse(BaseModel):
    """Response model for entity type mapping."""

    id: int
    entity_type: str
    primary_domain: str
    secondary_domains: List[str]
    confidence: float
    updated_at: Optional[str]


# ── Entity Type Mapping Endpoints ───────────────────────────────────────


@router.get("/entity-mappings", response_model=List[EntityMappingResponse])
async def get_all_entity_mappings(db: Session = Depends(get_db)):
    """
    Get all entity type to domain mappings.

    Returns all configured entity type classifications from the database.
    """
    classifier = EntityClassifier(db)
    mappings = classifier.get_all_mappings()

    return [
        EntityMappingResponse(
            id=i,
            entity_type=m["entity_type"],
            primary_domain=m["primary_domain"],
            secondary_domains=m["secondary_domains"],
            confidence=m["confidence"],
            updated_at=m["updated_at"],
        )
        for i, m in enumerate(mappings)
    ]


@router.get("/entity-mappings/{entity_type}", response_model=EntityMappingResponse)
async def get_entity_mapping(entity_type: str, db: Session = Depends(get_db)):
    """
    Get domain classification for a specific entity type.

    Args:
        entity_type: The entity type to look up (e.g., 'Person', 'Organization')

    Returns:
        The domain mapping for the entity type.

    Raises:
        HTTPException 404: If entity type is not found.
    """
    result = db.execute(
        select(EntityTypeDomainMapping).where(
            EntityTypeDomainMapping.entity_type == entity_type
        )
    ).scalar_one_or_none()

    if not result:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not found"
        )

    return EntityMappingResponse(
        id=result.id,
        entity_type=result.entity_type,
        primary_domain=result.primary_domain,
        secondary_domains=result.secondary_domains,
        confidence=result.confidence,
        updated_at=result.updated_at.isoformat() if result.updated_at else None,
    )


@router.post("/entity-mappings", response_model=EntityMappingResponse)
async def create_entity_mapping(
    mapping: EntityMappingCreate, db: Session = Depends(get_db)
):
    """
    Create a new entity type to domain mapping.

    Args:
        mapping: The mapping configuration to create.

    Returns:
        The created mapping.

    Raises:
        HTTPException 400: If entity type already exists.
    """
    # Check if already exists
    existing = db.execute(
        select(EntityTypeDomainMapping).where(
            EntityTypeDomainMapping.entity_type == mapping.entity_type
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Entity type '{mapping.entity_type}' already exists. Use PUT to update.",
        )

    # Create new mapping
    new_mapping = EntityTypeDomainMapping(
        entity_type=mapping.entity_type,
        primary_domain=mapping.primary_domain,
        secondary_domains=mapping.secondary_domains,
        confidence=mapping.confidence,
    )

    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    return EntityMappingResponse(
        id=new_mapping.id,
        entity_type=new_mapping.entity_type,
        primary_domain=new_mapping.primary_domain,
        secondary_domains=new_mapping.secondary_domains,
        confidence=new_mapping.confidence,
        updated_at=new_mapping.updated_at.isoformat() if new_mapping.updated_at else None,
    )


@router.put("/entity-mappings/{entity_type}", response_model=EntityMappingResponse)
async def update_entity_mapping(
    entity_type: str, mapping: EntityMappingCreate, db: Session = Depends(get_db)
):
    """
    Update an existing entity type to domain mapping.

    Args:
        entity_type: The entity type to update.
        mapping: The new mapping configuration.

    Returns:
        The updated mapping.

    Raises:
        HTTPException 404: If entity type is not found.
    """
    result = db.execute(
        select(EntityTypeDomainMapping).where(
            EntityTypeDomainMapping.entity_type == entity_type
        )
    ).scalar_one_or_none()

    if not result:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not found"
        )

    # Update fields
    result.primary_domain = mapping.primary_domain
    result.secondary_domains = mapping.secondary_domains
    result.confidence = mapping.confidence

    db.commit()
    db.refresh(result)

    return EntityMappingResponse(
        id=result.id,
        entity_type=result.entity_type,
        primary_domain=result.primary_domain,
        secondary_domains=result.secondary_domains,
        confidence=result.confidence,
        updated_at=result.updated_at.isoformat() if result.updated_at else None,
    )


@router.delete("/entity-mappings/{entity_type}")
async def delete_entity_mapping(entity_type: str, db: Session = Depends(get_db)):
    """
    Delete an entity type to domain mapping.

    Args:
        entity_type: The entity type to delete.

    Returns:
        Success message.

    Raises:
        HTTPException 404: If entity type is not found.
    """
    result = db.execute(
        select(EntityTypeDomainMapping).where(
            EntityTypeDomainMapping.entity_type == entity_type
        )
    ).scalar_one_or_none()

    if not result:
        raise HTTPException(
            status_code=404, detail=f"Entity type '{entity_type}' not found"
        )

    db.delete(result)
    db.commit()

    return {"status": "success", "message": f"Entity type '{entity_type}' deleted"}
