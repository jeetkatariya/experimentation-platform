"""
Pydantic schemas for request validation and response serialization.

Organized by domain:
- Variant schemas
- Experiment schemas  
- Assignment schemas
- Event schemas
- Results schemas
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum



class VariantBase(BaseModel):
    """Base variant properties."""
    name: str = Field(..., min_length=1, max_length=255, description="Unique name within experiment")
    description: Optional[str] = Field(None, description="Human-readable description")
    traffic_allocation: float = Field(
        50.0, 
        ge=0, 
        le=100, 
        description="Traffic percentage (0-100)"
    )
    config: Optional[Dict[str, Any]] = Field(None, description="Variant-specific configuration")


class VariantCreate(VariantBase):
    """Schema for creating a variant."""
    pass


class VariantResponse(VariantBase):
    """Schema for variant in responses."""
    id: int
    experiment_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True



class ExperimentStatus(str, Enum):
    """Experiment lifecycle states."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class ExperimentBase(BaseModel):
    """Base experiment properties."""
    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: Optional[str] = Field(None, description="Experiment description")


class ExperimentCreate(ExperimentBase):
    """Schema for creating an experiment with variants."""
    variants: List[VariantCreate] = Field(
        ..., 
        min_length=2,
        description="At least 2 variants required for an experiment"
    )
    
    @field_validator("variants")
    @classmethod
    def validate_traffic_allocation(cls, variants: List[VariantCreate]) -> List[VariantCreate]:
        """Ensure traffic allocations sum to 100%."""
        total = sum(v.traffic_allocation for v in variants)
        if abs(total - 100.0) > 0.01:  # Allow small floating point tolerance
            raise ValueError(f"Traffic allocations must sum to 100%, got {total}%")
        return variants


class ExperimentUpdate(BaseModel):
    """Schema for updating an experiment."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ExperimentStatus] = None


class ExperimentResponse(ExperimentBase):
    """Schema for experiment in responses."""
    id: int
    status: ExperimentStatus
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    variants: List[VariantResponse] = []
    
    class Config:
        from_attributes = True


class ExperimentListResponse(BaseModel):
    """Schema for listing experiments."""
    experiments: List[ExperimentResponse]
    total: int



class AssignmentContext(BaseModel):
    """Optional context captured at assignment time."""
    device_type: Optional[str] = None
    platform: Optional[str] = None
    country: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class AssignmentResponse(BaseModel):
    """Response when getting/creating an assignment."""
    experiment_id: int
    experiment_name: str
    user_id: str
    variant_id: int
    variant_name: str
    variant_config: Optional[Dict[str, Any]] = None
    assigned_at: datetime
    is_new_assignment: bool = Field(
        description="True if this is a new assignment, False if returning existing"
    )
    
    class Config:
        from_attributes = True



class EventCreate(BaseModel):
    """Schema for recording an event."""
    user_id: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=255, alias="event_type")
    timestamp: datetime = Field(..., description="When the event occurred")
    properties: Optional[Dict[str, Any]] = Field(
        None, 
        description="Flexible properties for additional context"
    )
    
    class Config:
        populate_by_name = True


class EventResponse(BaseModel):
    """Schema for event in responses."""
    id: int
    user_id: str
    event_type: str
    timestamp: datetime
    properties: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class EventBatchCreate(BaseModel):
    """Schema for recording multiple events at once."""
    events: List[EventCreate] = Field(..., min_length=1, max_length=1000)


class EventBatchResponse(BaseModel):
    """Response for batch event creation."""
    created_count: int
    events: List[EventResponse]



class VariantMetrics(BaseModel):
    """Metrics for a single variant."""
    variant_id: int
    variant_name: str
    
    total_assignments: int
    
    total_events: int
    unique_users_with_events: int
    
    conversion_rate: float = Field(description="Percentage of assigned users with at least one event")
    
    events_by_type: Dict[str, int]
    
    events_per_user: float = Field(description="Average events per assigned user")


class TimeSeriesDataPoint(BaseModel):
    """A single data point in a time series."""
    timestamp: datetime
    variant_id: int
    variant_name: str
    assignments: int
    events: int
    conversions: int


class ResultsSummary(BaseModel):
    """High-level summary for executive dashboards."""
    total_assignments: int
    total_events: int
    overall_conversion_rate: float
    leading_variant: Optional[str] = None
    confidence_level: Optional[str] = Field(
        None, 
        description="Qualitative confidence: 'low', 'medium', 'high', 'significant'"
    )


class ExperimentResults(BaseModel):
    """
    Comprehensive experiment results response.
    
    Designed to support multiple use cases:
    - Real-time monitoring: summary + variant_metrics
    - Deep analysis: time_series + events_by_type
    - Executive summaries: summary only
    """
    experiment_id: int
    experiment_name: str
    experiment_status: ExperimentStatus
    
    analysis_start: datetime
    analysis_end: datetime
    
    summary: ResultsSummary
    
    variant_metrics: List[VariantMetrics]
    
    time_series: Optional[List[TimeSeriesDataPoint]] = None
    
    events_by_type: Dict[str, int]
    
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ResultsQueryParams(BaseModel):
    """Query parameters for results endpoint."""
    start_date: Optional[datetime] = Field(None, description="Start of analysis window")
    end_date: Optional[datetime] = Field(None, description="End of analysis window")
    event_types: Optional[List[str]] = Field(None, description="Filter to specific event types")
    include_time_series: bool = Field(False, description="Include time series data")
    time_series_granularity: str = Field(
        "day", 
        description="Granularity for time series: 'hour', 'day', 'week'"
    )
    format: str = Field(
        "full",
        description="Response format: 'full', 'summary', 'metrics_only'"
    )

