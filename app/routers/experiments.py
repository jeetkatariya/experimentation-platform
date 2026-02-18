"""
Experiment management endpoints.

Handles CRUD operations for experiments and their variants.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.auth import verify_token
from app.models import Experiment, Variant, ExperimentStatus as ModelExperimentStatus
from app.schemas import (
    ExperimentCreate,
    ExperimentUpdate,
    ExperimentResponse,
    ExperimentListResponse,
    ExperimentStatus
)

router = APIRouter(
    prefix="/experiments",
    tags=["experiments"],
    dependencies=[Depends(verify_token)]
)


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    experiment_data: ExperimentCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new experiment with variants.
    
    Requirements:
    - At least 2 variants required
    - Variant traffic allocations must sum to 100%
    - Variant names must be unique within the experiment
    """
    # Check for duplicate variant names
    variant_names = [v.name for v in experiment_data.variants]
    if len(variant_names) != len(set(variant_names)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant names must be unique within an experiment"
        )
    
    # Create experiment
    experiment = Experiment(
        name=experiment_data.name,
        description=experiment_data.description,
        status=ModelExperimentStatus.DRAFT
    )
    db.add(experiment)
    db.flush()  # Get the experiment ID
    
    # Create variants
    for variant_data in experiment_data.variants:
        variant = Variant(
            experiment_id=experiment.id,
            name=variant_data.name,
            description=variant_data.description,
            traffic_allocation=variant_data.traffic_allocation,
            config=variant_data.config
        )
        db.add(variant)
    
    db.commit()
    db.refresh(experiment)
    
    return experiment


@router.get("", response_model=ExperimentListResponse)
async def list_experiments(
    status_filter: Optional[ExperimentStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    List all experiments with optional filtering.
    
    Query Parameters:
    - status: Filter by experiment status
    - limit: Maximum number of results (default 100)
    - offset: Pagination offset
    """
    query = db.query(Experiment)
    
    if status_filter:
        query = query.filter(Experiment.status == status_filter.value)
    
    total = query.count()
    experiments = query.order_by(Experiment.created_at.desc()).offset(offset).limit(limit).all()
    
    return ExperimentListResponse(experiments=experiments, total=total)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific experiment by ID."""
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    return experiment


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment(
    experiment_id: int,
    update_data: ExperimentUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an experiment.
    
    Status transitions:
    - draft -> running (starts the experiment)
    - running -> paused (temporarily stops new assignments)
    - paused -> running (resumes)
    - running/paused -> completed (ends the experiment)
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    # Handle status transitions
    if update_data.status:
        new_status = ModelExperimentStatus(update_data.status.value)
        current_status = experiment.status
        
        # Validate transitions
        valid_transitions = {
            ModelExperimentStatus.DRAFT: [ModelExperimentStatus.RUNNING],
            ModelExperimentStatus.RUNNING: [ModelExperimentStatus.PAUSED, ModelExperimentStatus.COMPLETED],
            ModelExperimentStatus.PAUSED: [ModelExperimentStatus.RUNNING, ModelExperimentStatus.COMPLETED],
            ModelExperimentStatus.COMPLETED: []  # Terminal state
        }
        
        if new_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from {current_status.value} to {new_status.value}"
            )
        
        experiment.status = new_status
        
        # Track lifecycle timestamps
        if new_status == ModelExperimentStatus.RUNNING and not experiment.started_at:
            experiment.started_at = datetime.utcnow()
        elif new_status == ModelExperimentStatus.COMPLETED:
            experiment.ended_at = datetime.utcnow()
    
    # Update other fields
    if update_data.name is not None:
        experiment.name = update_data.name
    if update_data.description is not None:
        experiment.description = update_data.description
    
    db.commit()
    db.refresh(experiment)
    
    return experiment


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment(
    experiment_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an experiment.
    
    Warning: This will cascade delete all variants and assignments.
    Only draft experiments can be deleted.
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    if experiment.status != ModelExperimentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft experiments can be deleted. Complete or archive running experiments instead."
        )
    
    db.delete(experiment)
    db.commit()

