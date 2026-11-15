"""Shared column mixins and helpers for ORM models."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def string_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Store an enum as VARCHAR + CHECK constraint using its *values*.

    Non-native enums avoid PostgreSQL ``ALTER TYPE`` migrations when values are added.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )
