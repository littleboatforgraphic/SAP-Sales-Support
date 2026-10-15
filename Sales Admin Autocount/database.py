from sqlalchemy import create_engine, Column, String, Integer, Float, Numeric, Boolean, DateTime, Text, ForeignKey, Date, Enum as SQLEnum, JSON, CheckConstraint, LargeBinary, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import enum
import uuid


def new_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())

Base = declarative_base()


class Role(str, enum.Enum):
    ADMIN = "admin"
    SALES = "sales"
    FINANCE = "finance"
    LOGISTICS = "logistics"


class GlossaryStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class GlossaryCategory(str, enum.Enum):
    PRODUCT_SPEC = "product_spec"
    UNIT = "unit"
    BUSINESS_TERM = "business_term"
    CUSTOMER_SPECIFIC = "customer_specific"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_ADMIN = "pending_admin"
    APPROVED = "approved"
    SENT = "sent"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    DRAFTED = "drafted"
    RECONCILED_CONFIRMED = "reconciled_confirmed"
    REJECTED = "rejected"


class ActorType(str, enum.Enum):
    AGENT = "agent"
    ADMIN = "admin"
    SALESPERSON = "salesperson"
    ACCOUNTANT = "accountant"


class StaffAllowlistEntry(Base):
    __tablename__ = "staff_allowlist"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=True, index=True)
    telegram_user_id = Column(String(20), unique=True, nullable=True, index=True)  # Telegram numeric user ID
    name = Column(String(100), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    added_by = Column(String(100), nullable=False)

    # Relationship to roles (many-to-many)
    roles = relationship("StaffRole", back_populates="staff", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "phone_number IS NOT NULL OR telegram_user_id IS NOT NULL",
            name="ck_staff_allowlist_has_identifier"
        ),
    )


class StaffRole(Base):
    """Join table for staff roles (many-to-many relationship)."""
    __tablename__ = "staff_roles"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff_allowlist.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(Role), nullable=False)
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship back to staff
    staff = relationship("StaffAllowlistEntry", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("staff_id", "role", name="uq_staff_role"),
    )


class GlossaryEntry(Base):
    __tablename__ = "glossary"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(String(200), nullable=False, index=True)
    canonical_value = Column(String(200), nullable=False)
    category = Column(SQLEnum(GlossaryCategory), nullable=False)
    status = Column(SQLEnum(GlossaryStatus), default=GlossaryStatus.PENDING, nullable=False, index=True)
    created_from_conversation = Column(String(100), nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)


class SKUIndexEntry(Base):
    __tablename__ = "sku_index"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    spec_attributes = Column(JSON, nullable=True)  # JSON with validation
    last_synced_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class PriceReferenceEntry(Base):
    __tablename__ = "price_reference"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), nullable=False, index=True)
    price = Column(Numeric(15,2), nullable=False)
    updated_by = Column(String(100), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    effective_from = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    effective_to = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_price_reference_non_negative"),
    )


class OrderRecord(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(50), unique=True, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    customer_id = Column(String(50), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    items = Column(JSON, nullable=False)  # JSON with validation
    total_amount = Column(Numeric(15,2), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.DRAFT, nullable=False, index=True)
    salesperson_thread_id = Column(String(100), nullable=False, index=True)
    salesperson_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    sent_via_whatsapp_at = Column(DateTime, nullable=True)
    sent_via_email_at = Column(DateTime, nullable=True)
    parent_version = Column(Integer, nullable=True)
    edit_reason = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_orders_non_negative_total"),
        CheckConstraint("version >= 1", name="ck_orders_version_positive"),
    )

    # Optimistic locking: increment version on update, check version matches before commit
    # Application layer must handle: WHERE id = ? AND version = ?; UPDATE SET version = version + 1


class PaymentDraftEntry(Base):
    __tablename__ = "payment_drafts"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(50), unique=True, nullable=False, index=True)
    source_pdf_ref = Column(String(200), nullable=False)
    extracted_amount = Column(Float, nullable=False)
    extracted_date = Column(Date, nullable=False)
    extracted_payer_ref = Column(String(100), nullable=False)
    extracted_payer_name = Column(String(200), nullable=True)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.DRAFTED, nullable=False, index=True)
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("extracted_amount >= 0", name="ck_payment_drafts_non_negative_amount"),
    )


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(100), unique=True, nullable=False, index=True)
    participant_id = Column(String(20), nullable=False, index=True)  # Channel-specific: phone number or Telegram user ID
    active_agent = Column(String(50), nullable=True)
    last_agent_action_at = Column(DateTime, nullable=True)
    admin_takeover_active = Column(Boolean, default=False, nullable=False)
    admin_takeover_started_at = Column(DateTime, nullable=True)
    admin_takeover_ends_at = Column(DateTime, nullable=True)
    pending_confirmation = Column(JSON, nullable=True)  # JSON with validation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id = Column(String(50), primary_key=True)  # UUID
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_reference = Column(String(255), nullable=False, index=True)  # e.g. RFC822 Message-ID
    action = Column(String(50), nullable=False)
    actor = Column(String(100), nullable=False)
    actor_type = Column(SQLEnum(ActorType), nullable=False)
    details = Column(JSON, nullable=True)  # JSON with validation
    related_conversation_id = Column(String(100), nullable=True, index=True)

    # Note: Append-only access should be enforced at application layer
    # For production, consider using database triggers or a separate audit table
    # TODO: Implement payload redaction for sensitive fields (passwords, tokens, API keys)


class AddressValidationResult(Base):
    __tablename__ = "address_validation_results"

    id = Column(Integer, primary_key=True, index=True)
    order_reference = Column(String(50), nullable=False, index=True)
    customer_id = Column(String(50), nullable=False, index=True)
    po_delivery_address = Column(Text, nullable=False)
    registered_addresses = Column(JSON, nullable=False)  # JSON with validation
    is_trading_house = Column(Boolean, nullable=False)
    match_found = Column(Boolean, nullable=False)
    validation_level = Column(String(50), nullable=False)  # "match" | "trading_house_mismatch" | "high_risk_mismatch"
    requires_admin_approval = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class EmailConfig(Base):
    __tablename__ = "email_config"

    id = Column(Integer, primary_key=True, index=True)
    imap_server = Column(String(200), nullable=False)
    imap_port = Column(Integer, nullable=False)
    username = Column(String(200), nullable=False)
    password = Column(String(500), nullable=False)  # Should use SecretStr or encryption - TODO: migrate to encrypted storage
    folder = Column(String(100), default="INBOX", nullable=False)
    po_sender_allowlist = Column(JSON, nullable=False)  # JSON with validation
    po_keywords = Column(JSON, nullable=False)  # JSON with validation
    active = Column(Boolean, default=True, nullable=False)
    last_polled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class MessageRoutingLog(Base):
    """Log of message routing decisions for dynamic learning."""
    __tablename__ = "message_routing_log"

    id = Column(String(36), primary_key=True, default=new_uuid)
    message = Column(Text(2000), nullable=False)
    detected_agent = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=True)
    method = Column(String(20), nullable=False)  # "keyword" or "llm_classify"
    user_feedback = Column(String(20), nullable=True)  # "correct", "incorrect", None
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_routing_confidence"),
        CheckConstraint("method IN ('keyword', 'llm_classify')", name="ck_routing_method"),
    )


class LearnedTriggerKeyword(Base):
    """Dynamically learned trigger keywords from user interactions."""
    __tablename__ = "learned_trigger_keywords"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(100), nullable=False, unique=True, index=True)
    agent_type = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_learned_keyword_confidence"),
        CheckConstraint("usage_count >= 0", name="ck_learned_keyword_usage"),
    )


class OutboundAllowlistEntry(Base):
    """
    Learned outbound email allowlist.

    Entries are added automatically when an inbound email's buyer matches a
    known AutoCount customer ("matched" status) — that is the signal that the
    sender is a real trading partner, so replies to them are permitted.
    `source` distinguishes learned entries from manually seeded ones, and
    `active` lets staff revoke an entry without deleting history.
    """
    __tablename__ = "outbound_allowlist"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    debtor_code = Column(String(50), nullable=True, index=True)  # matched AutoCount customer
    source = Column(String(10), nullable=False, default="auto")  # "auto" | "manual"
    times_seen = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("source IN ('auto', 'manual')", name="ck_outbound_source"),
    )


def get_engine(database_url: str):
    """Create database engine."""
    return create_engine(database_url, echo=False)


def get_sessionmaker(engine):
    """Create session factory."""
    return sessionmaker(bind=engine)


# Global engine and session factory (shared across all modules)
_engine = None
_SessionLocal = None


def init_database(database_url: str):
    """Initialize database with all tables."""
    global _engine, _SessionLocal
    _engine = get_engine(database_url)
    _SessionLocal = get_sessionmaker(_engine)
    Base.metadata.create_all(bind=_engine)
    return _engine


def get_db_engine():
    """Get the global database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _engine


def get_db_session_factory():
    """Get the global session factory."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _SessionLocal


# Import AOTG knowledge models to register them with Base
# This must be imported before Base.metadata.create_all() is called
from aotg_knowledge_models import (  # noqa: F401
    AOTGSpecSnapshot,
    AOTGOperation,
    AgentCommand,
    OperationPolicy,
    AgentKnowledgeRecord,
    AOTGEntityReference,
    AgentConversation,
    AgentMessage,
    AgentActionRequest,
    AgentActionApproval,
    AgentActionExecution,
)
