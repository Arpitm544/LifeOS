from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class ClerkUserId(TypeDecorator):
    """Tenant identifier supplied by Clerk (for example ``user_abc``)."""
    impl = String(128)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    title: Mapped[str] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20), default="other")
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    effort_est_min: Mapped[int] = mapped_column(Integer, default=30)
    effort_actual_min: Mapped[Optional[int]] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    priority_score: Mapped[float] = mapped_column(default=0)
    priority_band: Mapped[str] = mapped_column(String(2), default="P3")
    priority_why: Mapped[Optional[str]] = mapped_column(Text)
    priority_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_rrule: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

class ActionLog(Base):
    __tablename__ = "action_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    before: Mapped[Optional[dict]] = mapped_column(JSONB)
    after: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    undone_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)

class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    item_type: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20))
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    action_taken: Mapped[Optional[str]] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), primary_key=True, index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    title: Mapped[str] = mapped_column(String(120))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    rrule: Mapped[Optional[str]] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(16), default="manual")
    external_id: Mapped[Optional[str]] = mapped_column(String(200))
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

class Preference(Base):
    __tablename__ = "preferences"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16), default="stated")
    confidence: Mapped[float] = mapped_column(default=1.0)
    status: Mapped[str] = mapped_column(String(16), default="active")

class Routine(Base):
    __tablename__ = "routines"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    title: Mapped[str] = mapped_column(String(120))
    rrule: Mapped[str] = mapped_column(String(512))
    start_time: Mapped[str] = mapped_column(String(8))
    duration_min: Mapped[int] = mapped_column(Integer)
    movable: Mapped[bool] = mapped_column(Boolean, default=True)
    anchor_date: Mapped[str] = mapped_column(String(10), default=lambda: datetime.utcnow().date().isoformat())
    overrides: Mapped[dict] = mapped_column(JSONB, default=dict)

class PlanBlock(Base):
    __tablename__ = "plan_blocks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    plan_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    needed_min: Mapped[int] = mapped_column(Integer)
    free_min: Mapped[int] = mapped_column(Integer)
    task_ids: Mapped[list] = mapped_column(JSONB)
    options: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="open")


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(ClerkUserId(), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default='UTC')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TaskDependency(Base):
    __tablename__ = 'task_dependencies'
    user_id: Mapped[str] = mapped_column(ClerkUserId(), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    role: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'
    __table_args__ = (UniqueConstraint('user_id', 'endpoint'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = 'worker_heartbeats'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    worker_name: Mapped[str] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)



class Suggestion(Base):
    """Insight suggestions shown on the Insights screen (Apply / Dismiss)."""
    __tablename__ = 'suggestions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), index=True)
    type: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GoogleConnection(Base):
    """A user's link to Google Calendar. The refresh token is stored encrypted (see services/google_calendar.py)."""
    __tablename__ = 'google_connections'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(ClerkUserId(), unique=True, index=True)
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(String(200))


class WorkerStatus(Base):
    """Worker liveness, not tenant data: written only by the administrative worker."""
    __tablename__ = 'worker_status'
    worker_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_jobs: Mapped[dict] = mapped_column(JSONB, default=dict)
