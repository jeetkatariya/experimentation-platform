"""
User assignment endpoints.

Handles assigning users to experiment variants with idempotency guarantees.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import hashlib

from app.database import get_db
from app.auth import verify_token
from app.models import Experiment, Variant, Assignment, ExperimentStatus
from app.schemas import AssignmentResponse, AssignmentContext

router = APIRouter(
    prefix="/experiments",
    tags=["assignments"],
    dependencies=[Depends(verify_token)]
)


def deterministic_variant_assignment(
    experiment_id: int,
    user_id: str,
    variants: list[Variant]
) -> Variant:
    """
    Deterministically assign a user to a variant based on traffic allocation.
    
    Uses a hash of (experiment_id, user_id) to generate a consistent bucket value.
    This ensures:
    1. Same user always gets same variant (before DB persistence)
    2. Distribution matches configured traffic allocation
    3. Assignment is independent of call order or timing
    
    Algorithm:
    1. Hash experiment_id + user_id to get a value 0-99
    2. Walk through variants, accumulating traffic allocation
    3. Return variant when accumulated allocation exceeds hash value
    """
    # Create deterministic hash
    hash_input = f"{experiment_id}:{user_id}"
    hash_bytes = hashlib.sha256(hash_input.encode()).digest()
    # Use first 8 bytes as integer, mod 100 for percentage bucket
    bucket = int.from_bytes(hash_bytes[:8], byteorder='big') % 100
    
    # Sort variants by ID for consistent ordering
    sorted_variants = sorted(variants, key=lambda v: v.id)
    
    # Walk through variants by traffic allocation
    cumulative = 0.0
    for variant in sorted_variants:
        cumulative += variant.traffic_allocation
        if bucket < cumulative:
            return variant
    
    # Fallback to last variant (handles floating point edge cases)
    return sorted_variants[-1]


@router.get("/{experiment_id}/assignment/{user_id}", response_model=AssignmentResponse)
async def get_or_create_assignment(
    experiment_id: int,
    user_id: str,
    context: Optional[str] = Query(None, description="JSON context for new assignments"),
    db: Session = Depends(get_db)
):
    """
    Get a user's variant assignment for an experiment.
    
    **Idempotency Guarantee**: Once a user receives a variant assignment,
    all subsequent calls will return the same assignment.
    
    Behavior:
    - If user already assigned: Returns existing assignment (is_new_assignment=False)
    - If user not assigned and experiment is RUNNING: Creates assignment (is_new_assignment=True)
    - If experiment is not RUNNING: Returns 400 error
    
    The assignment algorithm uses a deterministic hash to ensure:
    - Consistent variant selection even before persistence
    - Traffic distribution matches configured percentages
    """
    # Fetch experiment with variants
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    # Check for existing assignment first (idempotency)
    existing_assignment = db.query(Assignment).filter(
        Assignment.experiment_id == experiment_id,
        Assignment.user_id == user_id
    ).first()
    
    if existing_assignment:
        variant = existing_assignment.variant
        return AssignmentResponse(
            experiment_id=experiment.id,
            experiment_name=experiment.name,
            user_id=user_id,
            variant_id=variant.id,
            variant_name=variant.name,
            variant_config=variant.config,
            assigned_at=existing_assignment.assigned_at,
            is_new_assignment=False
        )
    
    # New assignment - check if experiment is running
    if experiment.status != ExperimentStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment is not running (status: {experiment.status.value}). "
                   f"New assignments cannot be created."
        )
    
    # Get variants for this experiment
    variants = experiment.variants
    if not variants:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Experiment has no variants configured"
        )
    
    # Determine variant using deterministic algorithm
    selected_variant = deterministic_variant_assignment(experiment_id, user_id, variants)
    
    # Parse context if provided
    assignment_context = None
    if context:
        import json
        try:
            assignment_context = json.loads(context)
        except json.JSONDecodeError:
            pass  # Ignore invalid JSON context
    
    # Create assignment
    assignment = Assignment(
        experiment_id=experiment_id,
        variant_id=selected_variant.id,
        user_id=user_id,
        context=assignment_context
    )
    
    try:
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
    except IntegrityError:
        # Race condition - another request created the assignment
        db.rollback()
        existing_assignment = db.query(Assignment).filter(
            Assignment.experiment_id == experiment_id,
            Assignment.user_id == user_id
        ).first()
        
        if existing_assignment:
            variant = existing_assignment.variant
            return AssignmentResponse(
                experiment_id=experiment.id,
                experiment_name=experiment.name,
                user_id=user_id,
                variant_id=variant.id,
                variant_name=variant.name,
                variant_config=variant.config,
                assigned_at=existing_assignment.assigned_at,
                is_new_assignment=False
            )
        raise
    
    return AssignmentResponse(
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        user_id=user_id,
        variant_id=selected_variant.id,
        variant_name=selected_variant.name,
        variant_config=selected_variant.config,
        assigned_at=assignment.assigned_at,
        is_new_assignment=True
    )


@router.get("/{experiment_id}/assignments", response_model=dict)
async def list_assignments(
    experiment_id: int,
    variant_id: Optional[int] = Query(None, description="Filter by variant"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List all assignments for an experiment.
    
    Useful for auditing and debugging assignment distribution.
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    query = db.query(Assignment).filter(Assignment.experiment_id == experiment_id)
    
    if variant_id:
        query = query.filter(Assignment.variant_id == variant_id)
    
    total = query.count()
    assignments = query.order_by(Assignment.assigned_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "experiment_id": experiment_id,
        "total": total,
        "assignments": [
            {
                "user_id": a.user_id,
                "variant_id": a.variant_id,
                "variant_name": a.variant.name,
                "assigned_at": a.assigned_at.isoformat(),
                "context": a.context
            }
            for a in assignments
        ]
    }

