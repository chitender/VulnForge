import enum
import uuid

from sqlalchemy import Boolean, Column, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    SELECTED = "SELECTED"
    MR_RAISED = "MR_RAISED"
    IGNORED = "IGNORED"
    RESOLVED = "RESOLVED"


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    vuln_id = Column(String, nullable=False)
    pkg_name = Column(String, nullable=False)
    installed_version = Column(String, nullable=False)
    fixed_version = Column(String, nullable=True)
    severity = Column(Enum(Severity), nullable=False)
    target = Column(String, nullable=True)
    title = Column(Text, nullable=True)
    primary_url = Column(String, nullable=True)
    is_fixable = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(FindingStatus), nullable=False, default=FindingStatus.OPEN)

    scan = relationship("Scan", back_populates="findings")
