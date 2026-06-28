"""SQLAlchemy 2.0 Database Models for Log Templates and Incidents."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Index,
)
from pgvector.sqlalchemy import Vector

from src.db.session import Base


class LogTemplate(Base):
    """Cluster template discovered by Drain3 log miner."""

    __tablename__ = "log_templates"

    # Primary key matching Drain3 cluster ID
    template_id = Column(Integer, primary_key=True, index=True)
    # The parameterized pattern string, e.g. "Connection lost to <*>:<*> timeout"
    pattern_str = Column(Text, nullable=False, index=True)
    # Total count of logs clustered under this template
    occurrence_count = Column(Integer, default=1, nullable=False)
    # Anomaly indicator triggered when statistical Z-score > 3.0
    is_anomaly = Column(Boolean, default=False, nullable=False, index=True)
    # Timestamps
    first_seen = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # 384-dimensional dense vector embedding from all-MiniLM-L6-v2
    embedding = Column(Vector(384), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LogTemplate(id={self.template_id}, anomaly={self.is_anomaly}, "
            f"count={self.occurrence_count}, pattern='{self.pattern_str[:30]}...')>"
        )


class Incident(Base):
    """Historical post-mortem record for root-cause retrieval."""

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    # High-level incident title
    title = Column(String(255), nullable=False)
    # Microservice or component boundary, e.g. "payment-service"
    service_name = Column(String(100), nullable=False, index=True)
    # Summary of root cause from historical post-mortem
    root_cause_summary = Column(Text, nullable=False)
    # Actionable remediation instructions
    remediation_steps = Column(Text, nullable=True)
    # Dense vector embedding of the post-mortem text (vector(384))
    content_embedding = Column(Vector(384), nullable=True)
    # Incident timestamp
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Incident(id={self.id}, service='{self.service_name}', title='{self.title}')>"
