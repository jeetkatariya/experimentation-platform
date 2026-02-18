"""
Experiment results and analytics endpoints.

Provides flexible reporting for experiment performance analysis.
Supports multiple use cases: real-time monitoring, deep analysis, executive summaries.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from typing import Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

from app.database import get_db
from app.auth import verify_token
from app.models import Experiment, Variant, Assignment, Event, ExperimentStatus
from app.schemas import (
    ExperimentResults,
    ResultsSummary,
    VariantMetrics,
    TimeSeriesDataPoint,
    ExperimentStatus as SchemaExperimentStatus
)

router = APIRouter(
    prefix="/experiments",
    tags=["results"],
    dependencies=[Depends(verify_token)]
)


def calculate_confidence_level(
    control_conversions: int,
    control_total: int,
    treatment_conversions: int,
    treatment_total: int
) -> str:
    """
    Calculate a qualitative confidence level for the experiment.
    
    In production, this would use proper statistical testing (chi-squared, etc.).
    For simplicity, we use a heuristic based on sample size and effect size.
    """
    if control_total < 30 or treatment_total < 30:
        return "low"  # Not enough data
    
    if control_total == 0 or treatment_total == 0:
        return "low"
    
    control_rate = control_conversions / control_total
    treatment_rate = treatment_conversions / treatment_total
    
    # Calculate relative lift
    if control_rate == 0:
        lift = 1.0 if treatment_rate > 0 else 0.0
    else:
        lift = (treatment_rate - control_rate) / control_rate
    
    # Heuristic confidence based on sample size and effect size
    min_sample = min(control_total, treatment_total)
    
    if min_sample >= 1000 and abs(lift) >= 0.1:
        return "significant"
    elif min_sample >= 500 and abs(lift) >= 0.15:
        return "high"
    elif min_sample >= 100 and abs(lift) >= 0.2:
        return "medium"
    else:
        return "low"


@router.get("/{experiment_id}/results", response_model=ExperimentResults)
async def get_experiment_results(
    experiment_id: int,
    # Time range filters
    start_date: Optional[datetime] = Query(
        None, 
        description="Analysis start date (defaults to experiment start)"
    ),
    end_date: Optional[datetime] = Query(
        None, 
        description="Analysis end date (defaults to now)"
    ),
    # Event filters
    event_types: Optional[str] = Query(
        None, 
        description="Comma-separated event types to include (defaults to all)"
    ),
    # Response format control
    include_time_series: bool = Query(
        False, 
        description="Include time series data for charts"
    ),
    time_series_granularity: str = Query(
        "day",
        description="Time series granularity: 'hour', 'day', 'week'"
    ),
    format: str = Query(
        "full",
        description="Response format: 'full', 'summary', 'metrics_only'"
    ),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive experiment results and analytics.
    
    **Design Philosophy:**
    This endpoint is designed to serve multiple stakeholders:
    
    1. **Real-time Monitoring** (format=summary)
       - Quick health check on running experiments
       - Key metrics at a glance: conversion rates, leading variant
       
    2. **Deep Analysis** (format=full, include_time_series=true)
       - Full breakdown by variant with statistical details
       - Time series for trend analysis
       - Event type breakdown for funnel analysis
       
    3. **Executive Summaries** (format=summary)
       - High-level metrics for stakeholder updates
       - Clear winner indication with confidence level
    
    **Key Behaviors:**
    - Only counts events that occur AFTER a user's assignment timestamp
    - Respects time range filters for flexible analysis windows
    - Event type filtering enables funnel-specific analysis
    
    **Query Parameters:**
    - start_date/end_date: Define analysis window
    - event_types: Filter to specific events (e.g., "purchase,signup")
    - include_time_series: Add temporal data for charts
    - time_series_granularity: hour/day/week grouping
    - format: full/summary/metrics_only
    """
    # Fetch experiment
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    # Set analysis time range
    analysis_start = start_date or experiment.started_at or experiment.created_at
    analysis_end = end_date or datetime.utcnow()
    
    # Parse event types filter
    event_type_filter = None
    if event_types:
        event_type_filter = [t.strip() for t in event_types.split(",")]
    
    # Get all variants for this experiment
    variants = {v.id: v for v in experiment.variants}
    
    # Get assignment counts per variant
    # Note: We don't filter assignments by time range - all assignments to this
    # experiment are valid. Time filtering only applies to events for flexible analysis.
    assignment_query = db.query(
        Assignment.variant_id,
        func.count(Assignment.id).label("count")
    ).filter(
        Assignment.experiment_id == experiment_id
    ).group_by(Assignment.variant_id)
    
    assignment_counts = {r.variant_id: r.count for r in assignment_query.all()}
    
    # Get assigned users with their assignment times
    assignments = db.query(Assignment).filter(
        Assignment.experiment_id == experiment_id
    ).all()
    
    user_assignments = {a.user_id: a for a in assignments}
    assigned_user_ids = set(user_assignments.keys())
    
    # Build event query - only events from assigned users, after their assignment
    event_subquery_conditions = [
        Event.user_id.in_(assigned_user_ids),
        Event.timestamp >= analysis_start,
        Event.timestamp <= analysis_end
    ]
    
    if event_type_filter:
        event_subquery_conditions.append(Event.event_type.in_(event_type_filter))
    
    # Get all relevant events
    events = db.query(Event).filter(and_(*event_subquery_conditions)).all()
    
    # Filter events to only those at or after user's assignment
    # Using >= to include events that happen at the same second as assignment
    # (common in rapid testing scenarios and immediate post-assignment actions)
    valid_events = []
    for event in events:
        user_assignment = user_assignments.get(event.user_id)
        if user_assignment and event.timestamp >= user_assignment.assigned_at:
            valid_events.append((event, user_assignment.variant_id))
    
    # Aggregate metrics per variant
    variant_events = defaultdict(list)
    variant_users_with_events = defaultdict(set)
    events_by_type = defaultdict(int)
    
    for event, variant_id in valid_events:
        variant_events[variant_id].append(event)
        variant_users_with_events[variant_id].add(event.user_id)
        events_by_type[event.event_type] += 1
    
    # Build variant metrics
    variant_metrics_list = []
    total_assignments = 0
    total_events = 0
    
    for variant_id, variant in variants.items():
        assignments_count = assignment_counts.get(variant_id, 0)
        events_count = len(variant_events.get(variant_id, []))
        unique_users = len(variant_users_with_events.get(variant_id, set()))
        
        # Calculate conversion rate
        conversion_rate = (unique_users / assignments_count * 100) if assignments_count > 0 else 0.0
        
        # Events by type for this variant
        variant_events_by_type = defaultdict(int)
        for event in variant_events.get(variant_id, []):
            variant_events_by_type[event.event_type] += 1
        
        variant_metrics_list.append(VariantMetrics(
            variant_id=variant_id,
            variant_name=variant.name,
            total_assignments=assignments_count,
            total_events=events_count,
            unique_users_with_events=unique_users,
            conversion_rate=round(conversion_rate, 2),
            events_by_type=dict(variant_events_by_type),
            events_per_user=round(events_count / assignments_count, 2) if assignments_count > 0 else 0.0
        ))
        
        total_assignments += assignments_count
        total_events += events_count
    
    # Sort variants by ID for consistent ordering
    variant_metrics_list.sort(key=lambda x: x.variant_id)
    
    # Determine leading variant and confidence
    leading_variant = None
    confidence_level = "low"
    
    if len(variant_metrics_list) >= 2:
        sorted_by_conversion = sorted(variant_metrics_list, key=lambda x: x.conversion_rate, reverse=True)
        if sorted_by_conversion[0].conversion_rate > 0:
            leading_variant = sorted_by_conversion[0].variant_name
            
            # Calculate confidence (comparing top 2 variants)
            top = sorted_by_conversion[0]
            second = sorted_by_conversion[1]
            confidence_level = calculate_confidence_level(
                int(second.conversion_rate * second.total_assignments / 100),
                second.total_assignments,
                int(top.conversion_rate * top.total_assignments / 100),
                top.total_assignments
            )
    
    # Build summary
    overall_conversion = (
        sum(m.unique_users_with_events for m in variant_metrics_list) / 
        total_assignments * 100
    ) if total_assignments > 0 else 0.0
    
    summary = ResultsSummary(
        total_assignments=total_assignments,
        total_events=total_events,
        overall_conversion_rate=round(overall_conversion, 2),
        leading_variant=leading_variant,
        confidence_level=confidence_level
    )
    
    # Build time series if requested
    time_series = None
    if include_time_series:
        time_series = build_time_series(
            valid_events,
            assignments,
            variants,
            analysis_start,
            analysis_end,
            time_series_granularity
        )
    
    # Build response based on format
    result = ExperimentResults(
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        experiment_status=SchemaExperimentStatus(experiment.status.value),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        summary=summary,
        variant_metrics=variant_metrics_list if format != "summary" else [],
        time_series=time_series if format == "full" else None,
        events_by_type=dict(events_by_type) if format != "summary" else {}
    )
    
    return result


def build_time_series(
    valid_events: list,
    assignments: list,
    variants: dict,
    start: datetime,
    end: datetime,
    granularity: str
) -> List[TimeSeriesDataPoint]:
    """
    Build time series data for visualization.
    
    Groups data into buckets based on granularity (hour/day/week).
    """
    # Determine bucket size
    if granularity == "hour":
        bucket_delta = timedelta(hours=1)
    elif granularity == "week":
        bucket_delta = timedelta(weeks=1)
    else:  # day
        bucket_delta = timedelta(days=1)
    
    # Initialize buckets for each variant
    buckets = defaultdict(lambda: defaultdict(lambda: {"assignments": 0, "events": 0, "conversions": set()}))
    
    # Bucket assignments
    for assignment in assignments:
        bucket_time = truncate_to_bucket(assignment.assigned_at, granularity)
        if start <= bucket_time <= end:
            buckets[bucket_time][assignment.variant_id]["assignments"] += 1
    
    # Bucket events
    for event, variant_id in valid_events:
        bucket_time = truncate_to_bucket(event.timestamp, granularity)
        if start <= bucket_time <= end:
            buckets[bucket_time][variant_id]["events"] += 1
            buckets[bucket_time][variant_id]["conversions"].add(event.user_id)
    
    # Convert to time series points
    time_series = []
    for bucket_time in sorted(buckets.keys()):
        for variant_id, data in buckets[bucket_time].items():
            if variant_id in variants:
                time_series.append(TimeSeriesDataPoint(
                    timestamp=bucket_time,
                    variant_id=variant_id,
                    variant_name=variants[variant_id].name,
                    assignments=data["assignments"],
                    events=data["events"],
                    conversions=len(data["conversions"])
                ))
    
    return time_series


def truncate_to_bucket(dt: datetime, granularity: str) -> datetime:
    """Truncate datetime to the start of its bucket."""
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif granularity == "week":
        # Start of week (Monday)
        days_since_monday = dt.weekday()
        return (dt - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # day
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/{experiment_id}/results/export", response_model=dict)
async def export_experiment_data(
    experiment_id: int,
    include_assignments: bool = Query(True, description="Include raw assignment data"),
    include_events: bool = Query(True, description="Include raw event data"),
    db: Session = Depends(get_db)
):
    """
    Export raw experiment data for external analysis.
    
    Returns denormalized data suitable for CSV export or loading into
    analytics tools (e.g., Jupyter notebooks, BI tools).
    """
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment {experiment_id} not found"
        )
    
    result = {
        "experiment": {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status.value,
            "created_at": experiment.created_at.isoformat(),
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None
        },
        "variants": [
            {
                "id": v.id,
                "name": v.name,
                "traffic_allocation": v.traffic_allocation
            }
            for v in experiment.variants
        ]
    }
    
    if include_assignments:
        assignments = db.query(Assignment).filter(
            Assignment.experiment_id == experiment_id
        ).all()
        
        result["assignments"] = [
            {
                "user_id": a.user_id,
                "variant_id": a.variant_id,
                "variant_name": a.variant.name,
                "assigned_at": a.assigned_at.isoformat(),
                "context": a.context
            }
            for a in assignments
        ]
    
    if include_events:
        # Get all users assigned to this experiment
        assigned_users = db.query(Assignment.user_id).filter(
            Assignment.experiment_id == experiment_id
        ).all()
        user_ids = [u.user_id for u in assigned_users]
        
        # Get events for those users
        events = db.query(Event).filter(Event.user_id.in_(user_ids)).all()
        
        result["events"] = [
            {
                "id": e.id,
                "user_id": e.user_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "properties": e.properties
            }
            for e in events
        ]
    
    return result

