import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


class MRType(enum.StrEnum):
    FEATURE = "FEATURE"
    HOTFIX = "HOTFIX"


class MRTargetKind(enum.StrEnum):
    BASE_DOCKERFILE = "BASE_DOCKERFILE"
    APP_DOCKERFILE = "APP_DOCKERFILE"


class MRState(enum.StrEnum):
    OPENED = "OPENED"
    MERGED = "MERGED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class PipelineStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class MergeRequest(Base, TimestampMixin):
    __tablename__ = "merge_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    mr_type = Column(Enum(MRType), nullable=False)
    target_kind = Column(Enum(MRTargetKind), nullable=False)
    gitlab_project_id = Column(String, nullable=False)
    gitlab_mr_iid = Column(Integer, nullable=True)
    gitlab_mr_url = Column(String, nullable=True)
    gitlab_pipeline_id = Column(Integer, nullable=True)
    pipeline_status = Column(Enum(PipelineStatus), nullable=True, default=PipelineStatus.UNKNOWN)
    source_branch = Column(String, nullable=True)
    target_branch = Column(String, nullable=False)
    state = Column(Enum(MRState), nullable=False, default=MRState.OPENED)
    finding_ids = Column(JSONB, nullable=False, default=list)
    image_digest = Column(String, nullable=False)
