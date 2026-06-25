"""SQLAlchemy models for Strava authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    firstname: Mapped[Optional[str]] = mapped_column(String(128))
    lastname: Mapped[Optional[str]] = mapped_column(String(128))
    username: Mapped[Optional[str]] = mapped_column(String(128))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    strava_account: Mapped[Optional["StravaAccount"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class StravaAccount(Base):
    """Strava OAuth connection and token storage for a user."""

    __tablename__ = "strava_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    athlete_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Bearer")
    scope: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="strava_account")
