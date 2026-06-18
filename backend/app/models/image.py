import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TeamScopedMixin


class ServiceType(enum.StrEnum):
    UI = "UI"
    BACKEND = "BACKEND"


class Image(Base, TeamScopedMixin):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    registry_id = Column(UUID(as_uuid=True), ForeignKey("registries.id"), nullable=False)
    repository = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    last_digest = Column(String, nullable=True)
    service_type = Column(Enum(ServiceType), nullable=False)
    base_dockerfile_path = Column(String, nullable=False)
    app_dockerfile_path = Column(String, nullable=False)
    gitlab_project_id = Column(String, nullable=False)
    gitlab_default_branch = Column(String, nullable=False, default="main")

    registry = relationship("Registry", back_populates="images")
    scans = relationship("Scan", back_populates="image", lazy="select")
