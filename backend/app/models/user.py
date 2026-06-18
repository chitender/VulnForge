import enum
import uuid

from sqlalchemy import Column, Enum, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
