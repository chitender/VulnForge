import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class ScanStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Scan(Base, TimestampMixin):
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(Enum(ScanStatus), nullable=False, default=ScanStatus.QUEUED)
    trivy_version = Column(String, nullable=True)
    db_version = Column(String, nullable=True)
    image_digest = Column(String, nullable=True)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    summary_jsonb = Column(JSONB, nullable=True)
    raw_report_jsonb = Column(JSONB, nullable=True)
    error_text = Column(Text, nullable=True)

    image = relationship("Image", back_populates="scans")
    findings = relationship("Finding", back_populates="scan", lazy="select")
