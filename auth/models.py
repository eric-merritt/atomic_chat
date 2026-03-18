"""SQLAlchemy models for authentication."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from flask_login import UserMixin


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base, UserMixin):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    auth_method = Column(String(16), nullable=False, default="local")  # "local" or "oauth"
    oauth_provider = Column(String(32), nullable=True)
    oauth_provider_id = Column(String(255), nullable=True)
    role = Column(String(16), nullable=False, default="user")
    avatar_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    last_login = Column(DateTime(timezone=True), default=_now)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")

    def get_id(self) -> str:
        return self.id


class UserSession(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    user = relationship("User", back_populates="sessions")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(8), nullable=False)
    label = Column(String(128), nullable=True)
    role_override = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    last_used = Column(DateTime(timezone=True), nullable=True)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="api_keys")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    scopes = Column(String(512), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="oauth_tokens")
