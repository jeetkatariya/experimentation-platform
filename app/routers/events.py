"""
Event recording endpoints.

Handles recording user events/conversions that can be analyzed per experiment.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.auth import verify_token
from app.models import Event
from app.schemas import EventCreate, EventResponse, EventBatchCreate, EventBatchResponse

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(verify_token)]
)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def record_event(
    event_data: EventCreate,
    db: Session = Depends(get_db)
):
    """
    Record a single event.
    
    Events are associated with users, not directly with experiments.
    This allows:
    - One event to be counted across multiple experiments
    - Flexible event types (not just predefined conversions)
    - Rich properties for deep analysis
    
    The experiment results endpoint filters events to only count those
    that occurred AFTER a user's assignment to an experiment.
    """
    event = Event(
        user_id=event_data.user_id,
        event_type=event_data.type,
        timestamp=event_data.timestamp,
        properties=event_data.properties
    )
    
    db.add(event)
    db.commit()
    db.refresh(event)
    
    return EventResponse(
        id=event.id,
        user_id=event.user_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        properties=event.properties,
        created_at=event.created_at
    )


@router.post("/batch", response_model=EventBatchResponse, status_code=status.HTTP_201_CREATED)
async def record_events_batch(
    batch_data: EventBatchCreate,
    db: Session = Depends(get_db)
):
    """
    Record multiple events in a single request.
    
    More efficient than individual event calls for high-volume scenarios.
    Limited to 1000 events per batch to prevent timeouts.
    """
    events = []
    
    for event_data in batch_data.events:
        event = Event(
            user_id=event_data.user_id,
            event_type=event_data.type,
            timestamp=event_data.timestamp,
            properties=event_data.properties
        )
        db.add(event)
        events.append(event)
    
    db.commit()
    
    # Refresh all events to get IDs and timestamps
    for event in events:
        db.refresh(event)
    
    return EventBatchResponse(
        created_count=len(events),
        events=[
            EventResponse(
                id=e.id,
                user_id=e.user_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                properties=e.properties,
                created_at=e.created_at
            )
            for e in events
        ]
    )


@router.get("", response_model=dict)
async def list_events(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Events after this timestamp"),
    end_date: Optional[datetime] = Query(None, description="Events before this timestamp"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Query events with optional filtering.
    
    Useful for debugging and auditing event data.
    """
    query = db.query(Event)
    
    if user_id:
        query = query.filter(Event.user_id == user_id)
    
    if event_type:
        query = query.filter(Event.event_type == event_type)
    
    if start_date:
        query = query.filter(Event.timestamp >= start_date)
    
    if end_date:
        query = query.filter(Event.timestamp <= end_date)
    
    total = query.count()
    events = query.order_by(Event.timestamp.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "events": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "properties": e.properties,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    }


@router.get("/types", response_model=dict)
async def list_event_types(
    db: Session = Depends(get_db)
):
    """
    Get a list of all distinct event types in the system.
    
    Useful for building UI filters and understanding available event taxonomy.
    """
    from sqlalchemy import distinct, func
    
    results = db.query(
        Event.event_type,
        func.count(Event.id).label("count")
    ).group_by(Event.event_type).all()
    
    return {
        "event_types": [
            {"type": r.event_type, "count": r.count}
            for r in results
        ]
    }

