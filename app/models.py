"""
SQLAlchemy ORM models for the experimentation platform.

Schema Design Decisions:
- Experiments and Variants are separate tables for flexibility (N variants per experiment)
- Assignments use composite unique constraint on (experiment_id, user_id) for idempotency
- Events store flexible JSON properties and reference the user assignment
- Indexes optimized for common query patterns (assignments by user, events by time)
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey,
    UniqueConstraint, Index, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.database import Base


class ExperimentStatus(str, enum.Enum):
    """Lifecycle states for experiments."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class Experiment(Base):
    """
    Represents an A/B test experiment.
    
    An experiment has multiple variants with configurable traffic allocation.
    Status controls whether new assignments can be made.
    """
    __tablename__ = "experiments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(ExperimentStatus), default=ExperimentStatus.DRAFT, nullable=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)  
    ended_at = Column(DateTime, nullable=True)    
    
    
    variants = relationship("Variant", back_populates="experiment", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="experiment", cascade="all, delete-orphan")


class Variant(Base):
    """
    A variant within an experiment (e.g., "control", "treatment_a", "treatment_b").
    
    Traffic allocation is specified as a percentage (0-100).
    Sum of all variant allocations for an experiment should equal 100.
    """
    __tablename__ = "variants"
    
    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    traffic_allocation = Column(Float, nullable=False, default=50.0)
    
    config = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    experiment = relationship("Experiment", back_populates="variants")
    assignments = relationship("Assignment", back_populates="variant")
    
    __table_args__ = (
        UniqueConstraint("experiment_id", "name", name="uq_variant_name_per_experiment"),
        Index("ix_variants_experiment_id", "experiment_id"),
    )


class Assignment(Base):
    """
    Records a user's assignment to a specific variant.
    
    Key properties:
    - Composite unique constraint ensures idempotency (one assignment per user per experiment)
    - assignment_timestamp used to filter events (only count events after assignment)
    - Deterministic assignment based on hash of (experiment_id, user_id) for consistency
    """
    __tablename__ = "assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column(Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), nullable=False)
    
    assigned_at = Column(DateTime, default=func.now(), nullable=False)
    
    context = Column(JSON, nullable=True)
    
    experiment = relationship("Experiment", back_populates="assignments")
    variant = relationship("Variant", back_populates="assignments")
    
    __table_args__ = (
        UniqueConstraint("experiment_id", "user_id", name="uq_user_experiment_assignment"),
        Index("ix_assignments_experiment_user", "experiment_id", "user_id"),
        Index("ix_assignments_user_id", "user_id"),
        Index("ix_assignments_variant_id", "variant_id"),
    )


class Event(Base):
    """
    Records user events/conversions.
    
    Events are not directly tied to experiments - they're tied to users.
    This allows:
    - One event to be counted across multiple experiments
    - Flexible event types beyond predefined conversion goals
    - Rich property storage for deep analysis
    """
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    
    event_type = Column(String(255), nullable=False)  
    
    timestamp = Column(DateTime, nullable=False)
    
    properties = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_events_user_timestamp", "user_id", "timestamp"),
        Index("ix_events_type_timestamp", "event_type", "timestamp"),
        Index("ix_events_timestamp", "timestamp"),
    )

