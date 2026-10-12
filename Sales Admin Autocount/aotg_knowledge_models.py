"""Database models for AOTG knowledge, policy, actions, and LLM auditing.

Import this module before ``Base.metadata.create_all()`` so its tables are
registered on the application's shared SQLAlchemy ``Base``.

This schema deliberately does not store AOTG, Telegram, or LLM credentials.
Accounting documents remain authoritative in AutoCount; only identifiers,
redacted summaries, and short-lived encrypted pending payloads belong here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# Enums


class RiskLevel(str, enum.Enum):
    READ_ONLY = "read_only"
    BUSINESS_WRITE = "business_write"
    FINANCIAL_WRITE = "financial_write"
    DESTRUCTIVE = "destructive"


class ConfirmationMode(str, enum.Enum):
    NONE = "none"
    REQUESTER = "requester"
    SECOND_APPROVER = "second_approver"


class KnowledgeStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageProcessingStatus(str, enum.Enum):
    RECEIVED = "received"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


class ActionStatus(str, enum.Enum):
    PROPOSED = "proposed"
    PENDING_CONFIRMATION = "pending_confirmation"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(str, enum.Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ToolCallStatus(str, enum.Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


# AOTG catalog and deterministic command/policy layer


class AOTGSpecSnapshot(Base):
    """Immutable identity of one imported Swagger/OpenAPI document."""

    __tablename__ = "aotg_spec_snapshots"

    id = Column(String(36), primary_key=True, default=new_uuid)
    source_url = Column(String(500), nullable=False)
    base_url = Column(String(500), nullable=False)
    document_version = Column(String(50), nullable=True)
    swagger_version = Column(String(20), nullable=False)
    document_sha256 = Column(String(64), nullable=False, unique=True)
    operation_count = Column(Integer, nullable=False)
    imported_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    active = Column(Boolean, default=True, nullable=False, index=True)

    operations = relationship(
        "AOTGOperation", back_populates="spec_snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("operation_count >= 0", name="ck_aotg_spec_operation_count"),
    )


class AOTGOperation(Base):
    """One allowlistable AOTG API operation derived from the API specification."""

    __tablename__ = "aotg_operations"

    id = Column(Integer, primary_key=True)
    spec_snapshot_id = Column(
        String(36), ForeignKey("aotg_spec_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    operation_id = Column(String(200), nullable=False)
    tag = Column(String(80), nullable=False, index=True)
    http_method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    summary = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    parameters_schema = Column(JSON, nullable=False, default=list)
    request_schema = Column(JSON, nullable=True)
    success_schema = Column(JSON, nullable=True)
    risk_level = Column(
        SQLEnum(RiskLevel, native_enum=False, name="aotg_risk_level"),
        nullable=False,
        index=True,
    )
    enabled_for_agent = Column(Boolean, default=False, nullable=False, index=True)
    llm_may_propose = Column(Boolean, default=False, nullable=False)
    execution_verified = Column(Boolean, default=False, nullable=False)
    supports_idempotency = Column(Boolean, default=False, nullable=False)
    default_timeout_seconds = Column(Integer, default=30, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    spec_snapshot = relationship("AOTGSpecSnapshot", back_populates="operations")
    commands = relationship("AgentCommand", back_populates="operation")
    policies = relationship(
        "OperationPolicy", back_populates="operation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "spec_snapshot_id", "http_method", "path", name="uq_aotg_snapshot_method_path"
        ),
        CheckConstraint(
            "http_method IN ('GET','POST','PUT','PATCH','DELETE')",
            name="ck_aotg_http_method",
        ),
        CheckConstraint(
            "default_timeout_seconds BETWEEN 1 AND 120", name="ck_aotg_timeout"
        ),
        Index("ix_aotg_operation_tag_method", "tag", "http_method"),
    )


class AgentCommand(Base):
    """Curated user intent/command mapped to an approved operation or workflow."""

    __tablename__ = "agent_commands"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    telegram_command = Column(String(80), nullable=True, unique=True)
    description = Column(Text, nullable=False)
    operation_id = Column(Integer, ForeignKey("aotg_operations.id"), nullable=True)
    input_schema = Column(JSON, nullable=False, default=dict)
    response_fields = Column(JSON, nullable=False, default=list)
    workflow_key = Column(String(100), nullable=True)
    prompt_instruction = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    operation = relationship("AOTGOperation", back_populates="commands")

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_agent_command_version"),
    )


class OperationPolicy(Base):
    """Default-deny role policy evaluated before an action reaches the adapter."""

    __tablename__ = "aotg_operation_policies"

    id = Column(Integer, primary_key=True)
    operation_id = Column(
        Integer, ForeignKey("aotg_operations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(32), nullable=False)
    allow_llm_proposal = Column(Boolean, default=False, nullable=False)
    allow_execution = Column(Boolean, default=False, nullable=False)
    confirmation_mode = Column(
        SQLEnum(ConfirmationMode, native_enum=False, name="aotg_confirmation_mode"),
        default=ConfirmationMode.NONE,
        nullable=False,
    )
    maximum_amount = Column(Numeric(19, 4), nullable=True)
    currency_code = Column(String(3), nullable=True)
    require_fresh_entity_lookup = Column(Boolean, default=True, nullable=False)
    policy_version = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    operation = relationship("AOTGOperation", back_populates="policies")

    __table_args__ = (
        UniqueConstraint("operation_id", "role", name="uq_aotg_policy_operation_role"),
        CheckConstraint(
            "role IN ('admin','salesperson','accountant')", name="ck_aotg_policy_role"
        ),
        CheckConstraint(
            "maximum_amount IS NULL OR maximum_amount >= 0", name="ck_aotg_policy_amount"
        ),
        CheckConstraint("policy_version >= 1", name="ck_aotg_policy_version"),
    )


# Curated operational knowledge and entity-reference cache


class AgentKnowledgeRecord(Base):
    """Approved business knowledge that may be supplied to the LLM."""

    __tablename__ = "agent_knowledge"

    id = Column(String(36), primary_key=True, default=new_uuid)
    source_type = Column(String(50), nullable=False, index=True)
    source_key = Column(String(200), nullable=False)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    content_sha256 = Column(String(64), nullable=False)
    status = Column(
        SQLEnum(KnowledgeStatus, native_enum=False, name="agent_knowledge_status"),
        default=KnowledgeStatus.DRAFT,
        nullable=False,
        index=True,
    )
    version = Column(Integer, default=1, nullable=False)
    approved_by_staff_id = Column(
        Integer, ForeignKey("staff_allowlist.id"), nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_key", "version", name="uq_agent_knowledge_source_version"
        ),
        CheckConstraint("version >= 1", name="ck_agent_knowledge_version"),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_agent_knowledge_validity",
        ),
    )


class AOTGEntityReference(Base):
    """Small, refreshable lookup cache; never a replacement for AutoCount."""

    __tablename__ = "aotg_entity_references"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)
    external_id = Column(String(100), nullable=False)
    entity_code = Column(String(100), nullable=True)
    display_name = Column(String(300), nullable=True)
    normalized_search_text = Column(Text, nullable=False)
    attributes_redacted = Column(JSON, nullable=False, default=dict)
    source_modified_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    active = Column(Boolean, default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("entity_type", "external_id", name="uq_aotg_entity_type_external"),
        Index("ix_aotg_entity_type_code", "entity_type", "entity_code"),
        CheckConstraint("expires_at > synced_at", name="ck_aotg_entity_cache_expiry"),
    )


# Conversation ingestion and privacy-safe message records


class AgentConversation(Base):
    """Channel-neutral conversation state linked to an allowlisted staff member."""

    __tablename__ = "agent_conversations"

    id = Column(String(36), primary_key=True, default=new_uuid)
    channel = Column(String(20), nullable=False)
    external_conversation_id = Column(String(100), nullable=False)
    external_participant_id = Column(String(100), nullable=False, index=True)
    staff_id = Column(Integer, ForeignKey("staff_allowlist.id"), nullable=True, index=True)
    status = Column(
        SQLEnum(ConversationStatus, native_enum=False, name="agent_conversation_status"),
        default=ConversationStatus.ACTIVE,
        nullable=False,
    )
    current_command_id = Column(Integer, ForeignKey("agent_commands.id"), nullable=True)
    state_json = Column(JSON, nullable=False, default=dict)
    state_version = Column(Integer, default=1, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    messages = relationship(
        "AgentMessage", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "channel", "external_conversation_id", name="uq_agent_conversation_channel_external"
        ),
        CheckConstraint("channel IN ('telegram','whatsapp')", name="ck_agent_channel"),
        CheckConstraint("state_version >= 1", name="ck_agent_conversation_state_version"),
    )


class AgentMessage(Base):
    """Idempotent message receipt with redacted content and optional encryption."""

    __tablename__ = "agent_messages"

    id = Column(String(36), primary_key=True, default=new_uuid)
    conversation_id = Column(
        String(36), ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False
    )
    external_message_id = Column(String(100), nullable=False)
    direction = Column(
        SQLEnum(MessageDirection, native_enum=False, name="agent_message_direction"),
        nullable=False,
    )
    content_redacted = Column(Text, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    content_ciphertext = Column(LargeBinary, nullable=True)
    encryption_key_reference = Column(String(200), nullable=True)
    status = Column(
        SQLEnum(
            MessageProcessingStatus,
            native_enum=False,
            name="agent_message_processing_status",
        ),
        default=MessageProcessingStatus.RECEIVED,
        nullable=False,
        index=True,
    )
    rejection_reason_code = Column(String(80), nullable=True)
    received_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)

    conversation = relationship("AgentConversation", back_populates="messages")

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "external_message_id", name="uq_agent_message_external"
        ),
        CheckConstraint(
            "content_ciphertext IS NULL OR encryption_key_reference IS NOT NULL",
            name="ck_agent_message_cipher_key",
        ),
    )


# Proposed actions, confirmation, approval, and execution audit


class AgentActionRequest(Base):
    """Validated proposal; execution is impossible until policy gates are satisfied."""

    __tablename__ = "agent_action_requests"

    id = Column(String(36), primary_key=True, default=new_uuid)
    idempotency_key = Column(String(100), nullable=False, unique=True)
    request_message_id = Column(String(36), ForeignKey("agent_messages.id"), nullable=False)
    requested_by_staff_id = Column(Integer, ForeignKey("staff_allowlist.id"), nullable=False)
    command_id = Column(Integer, ForeignKey("agent_commands.id"), nullable=True)
    operation_id = Column(Integer, ForeignKey("aotg_operations.id"), nullable=False)
    status = Column(
        SQLEnum(ActionStatus, native_enum=False, name="agent_action_status"),
        default=ActionStatus.PROPOSED,
        nullable=False,
        index=True,
    )
    request_sha256 = Column(String(64), nullable=False)
    payload_redacted = Column(JSON, nullable=False, default=dict)
    payload_ciphertext = Column(LargeBinary, nullable=True)
    encryption_key_reference = Column(String(200), nullable=True)
    policy_snapshot = Column(JSON, nullable=False, default=dict)
    amount = Column(Numeric(19, 4), nullable=True)
    currency_code = Column(String(3), nullable=True)
    expected_external_version = Column(String(100), nullable=True)
    confirmation_nonce_hash = Column(String(64), nullable=True)
    confirmation_expires_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_staff_id = Column(Integer, ForeignKey("staff_allowlist.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    external_resource_id = Column(String(100), nullable=True, index=True)
    external_document_number = Column(String(100), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    row_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    approvals = relationship(
        "AgentActionApproval", back_populates="action", cascade="all, delete-orphan"
    )
    executions = relationship(
        "AgentActionExecution", back_populates="action", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_agent_action_amount"),
        CheckConstraint("expires_at > created_at", name="ck_agent_action_expiry"),
        CheckConstraint(
            "payload_ciphertext IS NULL OR encryption_key_reference IS NOT NULL",
            name="ck_agent_action_cipher_key",
        ),
        CheckConstraint("row_version >= 1", name="ck_agent_action_row_version"),
        Index("ix_agent_action_status_expiry", "status", "expires_at"),
    )


class AgentActionApproval(Base):
    """Second-person approval or rejection for a material action."""

    __tablename__ = "agent_action_approvals"

    id = Column(String(36), primary_key=True, default=new_uuid)
    action_id = Column(
        String(36), ForeignKey("agent_action_requests.id", ondelete="CASCADE"), nullable=False
    )
    approver_staff_id = Column(Integer, ForeignKey("staff_allowlist.id"), nullable=False)
    decision = Column(
        SQLEnum(ApprovalDecision, native_enum=False, name="agent_approval_decision"),
        nullable=False,
    )
    reason = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    action = relationship("AgentActionRequest", back_populates="approvals")

    __table_args__ = (
        UniqueConstraint("action_id", "approver_staff_id", name="uq_action_approver"),
    )


class AgentActionExecution(Base):
    """Append-only execution attempt; UNKNOWN prevents unsafe blind retries."""

    __tablename__ = "agent_action_executions"

    id = Column(String(36), primary_key=True, default=new_uuid)
    action_id = Column(
        String(36), ForeignKey("agent_action_requests.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number = Column(Integer, nullable=False)
    adapter_request_id = Column(String(100), nullable=False, unique=True)
    status = Column(
        SQLEnum(ExecutionStatus, native_enum=False, name="agent_execution_status"),
        default=ExecutionStatus.STARTED,
        nullable=False,
    )
    http_status_code = Column(Integer, nullable=True)
    response_sha256 = Column(String(64), nullable=True)
    response_summary_redacted = Column(JSON, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message_sanitized = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    retry_authorized_by_staff_id = Column(
        Integer, ForeignKey("staff_allowlist.id"), nullable=True
    )
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    action = relationship("AgentActionRequest", back_populates="executions")

    __table_args__ = (
        UniqueConstraint("action_id", "attempt_number", name="uq_action_execution_attempt"),
        CheckConstraint("attempt_number >= 1", name="ck_action_execution_attempt"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_action_latency"),
        CheckConstraint(
            "http_status_code IS NULL OR http_status_code BETWEEN 100 AND 599",
            name="ck_action_http_status",
        ),
    )


# LLM and tool-call observability


class AgentLLMRun(Base):
    """Privacy-aware record of one LLM decision, without plaintext prompts."""

    __tablename__ = "agent_llm_runs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    message_id = Column(String(36), ForeignKey("agent_messages.id"), nullable=False)
    model = Column(String(100), nullable=False)
    prompt_template_version = Column(String(50), nullable=False)
    knowledge_snapshot_sha256 = Column(String(64), nullable=False)
    allowed_operation_ids = Column(JSON, nullable=False, default=list)
    input_sha256 = Column(String(64), nullable=False)
    output_sha256 = Column(String(64), nullable=True)
    output_summary_redacted = Column(Text, nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Numeric(19, 8), default=0, nullable=False)
    safety_decision = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    tool_calls = relationship(
        "AgentToolCall", back_populates="llm_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="ck_llm_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_llm_output_tokens"),
        CheckConstraint("cost_usd >= 0", name="ck_llm_cost"),
    )


class AgentToolCall(Base):
    """An LLM tool proposal; policy validation must create an action separately."""

    __tablename__ = "agent_tool_calls"

    id = Column(String(36), primary_key=True, default=new_uuid)
    llm_run_id = Column(
        String(36), ForeignKey("agent_llm_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number = Column(Integer, nullable=False)
    operation_id = Column(Integer, ForeignKey("aotg_operations.id"), nullable=False)
    action_request_id = Column(
        String(36), ForeignKey("agent_action_requests.id"), nullable=True
    )
    tool_name = Column(String(150), nullable=False)
    arguments_sha256 = Column(String(64), nullable=False)
    arguments_redacted = Column(JSON, nullable=False, default=dict)
    status = Column(
        SQLEnum(ToolCallStatus, native_enum=False, name="agent_tool_call_status"),
        default=ToolCallStatus.PROPOSED,
        nullable=False,
    )
    validation_error_code = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    llm_run = relationship("AgentLLMRun", back_populates="tool_calls")

    __table_args__ = (
        UniqueConstraint("llm_run_id", "sequence_number", name="uq_llm_tool_sequence"),
        CheckConstraint("sequence_number >= 1", name="ck_llm_tool_sequence"),
    )
