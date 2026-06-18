import enum
import uuid

from sqlalchemy import Column, Enum, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TeamScopedMixin


class RegistryType(enum.StrEnum):
    ECR = "ECR"
    ACR = "ACR"
    DOCKERHUB = "DOCKERHUB"
    GAR = "GAR"
    GENERIC_OCI = "GENERIC_OCI"


class Registry(Base, TeamScopedMixin):
    __tablename__ = "registries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(Enum(RegistryType), nullable=False)
    registry_url = Column(String, nullable=False)
    region = Column(String, nullable=True)
    auth_ciphertext = Column(LargeBinary, nullable=False)
    auth_dek_enc = Column(LargeBinary, nullable=False)

    images = relationship("Image", back_populates="registry", lazy="select")
