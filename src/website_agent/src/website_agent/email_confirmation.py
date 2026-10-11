"""Email-based two-way confirmation workflow for manually executed trades."""

from __future__ import annotations

import argparse
import email
import html
import imaplib
import json
import logging
import re
import secrets
import smtplib
import sqlite3
import ssl
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.message import Message
from email.mime.text import MIMEText
from email.utils import parseaddr
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Literal
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

ConfirmationStatus = Literal["FILLED", "PARTIAL", "CANCELLED"]
PlanStatus = Literal["PENDING", "CONFIRMED", "EXPIRED", "MANUAL"]
_CONFIRMATION_CODE_PATTERN = re.compile(
    r"确认码\s*[:：]\s*([A-Z0-9]{6})",
    re.IGNORECASE,
)
_SYMBOL_PATTERN = r"(?P<symbol>\d{6}(?:\.(?:SH|SZ|BJ))?)"
_FILL_PATTERN = re.compile(
    rf"^{_SYMBOL_PATTERN}\s*[:：]\s*"
    r"(?P<state>部分成交|成交)\s*"
    r"(?P<quantity>\d+(?:\.\d+)?)\s*股?\s*@\s*"
    r"(?P<price>\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
_CANCEL_PATTERN = re.compile(
    rf"^{_SYMBOL_PATTERN}\s*[:：]\s*未成交\s*$",
    re.IGNORECASE,
)
_FUZZY_FILL_PATTERN = re.compile(
    r"(?:买了|卖了|成交)\s*(?P<quantity>\d+(?:\.\d+)?)?\s*股?"
    r"(?:[，, ]*(?P<price>\d+(?:\.\d+)?))?"
)


class ConfirmationError(ValueError):
    """Raised when a confirmation email cannot be safely applied."""


@dataclass(frozen=True)
class TradePlanLeg:
    """One manually executable order in a trade plan."""

    symbol: str
    name: str
    side: str
    quantity: float
    price: float

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", self.symbol.upper()):
            raise ValueError(f"Invalid trade-plan symbol: {self.symbol!r}")
        if not self.name.strip():
            raise ValueError("Trade-plan leg name cannot be empty.")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported trade-plan side: {self.side!r}")
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("Trade-plan quantity and price must be positive.")

    def to_dict(self) -> dict[str, object]:
        """Serialize the plan leg for persistence."""
        return {
            "symbol": self.symbol.upper(),
            "name": self.name,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TradePlanLeg:
        """Deserialize a plan leg from persistent storage."""
        return cls(
            symbol=_required_string(value, "symbol"),
            name=_required_string(value, "name"),
            side=_required_string(value, "side"),
            quantity=_required_positive_number(value, "quantity"),
            price=_required_positive_number(value, "price"),
        )


@dataclass(frozen=True)
class TradePlan:
    """A pending trade plan protected by a unique confirmation code."""

    plan_id: str
    confirmation_code: str
    trace_id: str
    created_at: datetime
    expires_at: datetime
    status: PlanStatus
    legs: tuple[TradePlanLeg, ...]


@dataclass(frozen=True)
class ConfirmationRecord:
    """One parsed execution result from a reply email."""

    symbol: str
    status: ConfirmationStatus
    quantity: float | None
    price: float | None
    price_needs_review: bool = False


@dataclass(frozen=True)
class InboundEmail:
    """The data required to validate and process a received reply."""

    message_id: str
    sender: str
    subject: str
    body: str
    in_reply_to: str | None = None


@dataclass(frozen=True)
class ConfirmationOutcome:
    """The outcome of processing one inbound email."""

    accepted: bool
    reason: str
    records: tuple[ConfirmationRecord, ...] = ()


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP connection settings for plan and reminder delivery."""

    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_starttls: bool = True


@dataclass(frozen=True)
class ImapSettings:
    """IMAP SSL connection settings for reply collection."""

    host: str
    port: int
    username: str
    password: str
    mailbox: str = "INBOX"


class EmailConfirmationRepository:
    """Persist trade plans, executions, and parse failures in SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._initialize_database()

    def create_plan(self, plan: TradePlan) -> None:
        """Store a newly-created trade plan."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trade_plans (
                    plan_id, confirmation_code, trace_id, created_at, expires_at,
                    status, legs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.confirmation_code,
                    plan.trace_id,
                    _serialize_datetime(plan.created_at),
                    _serialize_datetime(plan.expires_at),
                    plan.status,
                    json.dumps(
                        [leg.to_dict() for leg in plan.legs],
                        ensure_ascii=False,
                    ),
                ),
            )

    def get_plan_by_code(self, confirmation_code: str) -> TradePlan | None:
        """Return a plan by confirmation code, if it exists."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trade_plans WHERE confirmation_code = ?",
                (confirmation_code,),
            ).fetchone()
        return _row_to_plan(row) if row is not None else None

    def get_plan_by_id(self, plan_id: str) -> TradePlan | None:
        """Return a plan by its caller-provided identifier, if it exists."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trade_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        return _row_to_plan(row) if row is not None else None

    def code_exists(self, confirmation_code: str) -> bool:
        """Return whether a confirmation code is already assigned."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM trade_plans WHERE confirmation_code = ?",
                (confirmation_code,),
            ).fetchone()
        return row is not None

    def apply_confirmation(
        self,
        plan: TradePlan,
        message_id: str,
        records: Sequence[ConfirmationRecord],
        processed_at: datetime,
    ) -> bool:
        """Atomically persist a first valid reply and its execution records."""
        with self._connect() as connection:
            marker = connection.execute(
                """
                INSERT OR IGNORE INTO processed_email_messages (
                    confirmation_code, message_id, processed_at
                ) VALUES (?, ?, ?)
                """,
                (
                    plan.confirmation_code,
                    message_id,
                    _serialize_datetime(processed_at),
                ),
            )
            if marker.rowcount != 1:
                return False
            cursor = connection.execute(
                """
                UPDATE trade_plans
                SET status = ?, processed_message_id = ?, processed_at = ?
                WHERE plan_id = ? AND status = ?
                """,
                (
                    "CONFIRMED",
                    message_id,
                    _serialize_datetime(processed_at),
                    plan.plan_id,
                    "PENDING",
                ),
            )
            if cursor.rowcount != 1:
                return False
            connection.executemany(
                """
                INSERT INTO order_confirmations (
                    plan_id, message_id, symbol, status, quantity, price,
                    price_needs_review, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        plan.plan_id,
                        message_id,
                        record.symbol,
                        record.status,
                        record.quantity,
                        record.price,
                        int(record.price_needs_review),
                        _serialize_datetime(processed_at),
                    )
                    for record in records
                ],
            )
        return True

    def add_manual_confirmation(
        self,
        plan: TradePlan,
        record: ConfirmationRecord,
        recorded_at: datetime,
    ) -> None:
        """Persist an operator-entered confirmation without consuming reply code."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO order_confirmations (
                    plan_id, message_id, symbol, status, quantity, price,
                    price_needs_review, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    "manual",
                    record.symbol,
                    record.status,
                    record.quantity,
                    record.price,
                    0,
                    _serialize_datetime(recorded_at),
                ),
            )
            connection.execute(
                """
                UPDATE trade_plans
                SET status = CASE WHEN status = ? THEN ? ELSE status END
                WHERE plan_id = ?
                """,
                ("PENDING", "MANUAL", plan.plan_id),
            )

    def expire_due_plans(self, now: datetime) -> list[TradePlan]:
        """Mark pending, expired plans and return their prior representations."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM trade_plans
                WHERE status = ? AND expires_at <= ?
                """,
                ("PENDING", _serialize_datetime(now)),
            ).fetchall()
            connection.execute(
                """
                UPDATE trade_plans
                SET status = ?
                WHERE status = ? AND expires_at <= ?
                """,
                ("EXPIRED", "PENDING", _serialize_datetime(now)),
            )
        return [_row_to_plan(row) for row in rows]

    def plans_needing_reminder(
        self,
        now: datetime,
        reminder_window: timedelta,
    ) -> list[TradePlan]:
        """Return pending plans that expire in the requested reminder window."""
        upper_bound = now + reminder_window
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM trade_plans
                WHERE status = ? AND expires_at > ? AND expires_at <= ?
                """,
                (
                    "PENDING",
                    _serialize_datetime(now),
                    _serialize_datetime(upper_bound),
                ),
            ).fetchall()
        return [_row_to_plan(row) for row in rows]

    def record_parse_failure(
        self,
        email_message: InboundEmail,
        reason: str,
        confirmation_code: str | None,
        recorded_at: datetime,
    ) -> bool:
        """Persist an unprocessable or suspicious inbound email once."""
        with self._connect() as connection:
            if confirmation_code is not None:
                marker = connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_email_messages (
                        confirmation_code, message_id, processed_at
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        confirmation_code,
                        email_message.message_id,
                        _serialize_datetime(recorded_at),
                    ),
                )
                if marker.rowcount != 1:
                    return False
            connection.execute(
                """
                INSERT INTO email_parse_failures (
                    message_id, confirmation_code, sender, subject, body, reason,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_message.message_id,
                    confirmation_code,
                    email_message.sender,
                    email_message.subject,
                    email_message.body,
                    reason,
                    _serialize_datetime(recorded_at),
                ),
            )
        return True

    def _initialize_database(self) -> None:
        """Create the durable confirmation workflow tables."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trade_plans (
                    plan_id TEXT PRIMARY KEY,
                    confirmation_code TEXT NOT NULL UNIQUE,
                    trace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    legs_json TEXT NOT NULL,
                    processed_message_id TEXT,
                    processed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS order_confirmations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity REAL,
                    price REAL,
                    price_needs_review INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processed_email_messages (
                    confirmation_code TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (confirmation_code, message_id)
                );
                CREATE TABLE IF NOT EXISTS email_parse_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    confirmation_code TEXT,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with mapping-style rows."""
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


class SmtpPlanSender:
    """Deliver rendered trade-plan and reminder emails through SMTP."""

    def __init__(
        self,
        settings: SmtpSettings,
        smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
    ) -> None:
        self._settings = settings
        self._smtp_factory = smtp_factory

    def send_html(self, subject: str, body: str) -> None:
        """Send an HTML email to the configured confirmation recipient."""
        message = MIMEText(body, "html", "utf-8")
        message["Subject"] = subject
        message["From"] = self._settings.sender
        message["To"] = self._settings.recipient
        with self._smtp_factory(self._settings.host, self._settings.port) as client:
            client.ehlo()
            if self._settings.use_starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            client.login(self._settings.username, self._settings.password)
            client.sendmail(
                self._settings.sender,
                [self._settings.recipient],
                message.as_string(),
            )


class EmailConfirmationService:
    """Create plans, validate replies, and emit order confirmation events."""

    def __init__(
        self,
        repository: EmailConfirmationRepository,
        allowed_senders: Iterable[str],
        event_publisher: Callable[[str, Mapping[str, object]], None],
        mail_sender: SmtpPlanSender | None = None,
    ) -> None:
        normalized_senders = {
            sender.strip().lower()
            for sender in allowed_senders
            if sender.strip()
        }
        if not normalized_senders:
            raise ValueError("At least one allowed confirmation sender is required.")
        self._repository = repository
        self._allowed_senders = normalized_senders
        self._event_publisher = event_publisher
        self._mail_sender = mail_sender

    def register_with_event_engine(self, event_engine: object) -> None:
        """Subscribe this service to ``trade.plan_ready`` on an event engine."""
        register = getattr(event_engine, "register", None)
        if not callable(register):
            raise TypeError("event_engine must expose a callable register method.")
        register("trade.plan_ready", self.handle_trade_plan_ready)

    def create_plan(
        self,
        plan_id: str,
        legs: Sequence[TradePlanLeg],
        trace_id: str = "",
        now: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> TradePlan:
        """Create and persist a protected trade plan.

        Args:
            plan_id: Stable execution-layer trade plan identifier.
            legs: Proposed orders for the user to manually execute.
            trace_id: Correlation identifier propagated to order events.
            now: Creation instant, supplied by tests or callers requiring control.
            expires_at: Optional explicit expiry; defaults to 16 hours or next
                day 10:00 UTC, whichever occurs first.
        """
        if not plan_id.strip():
            raise ValueError("plan_id cannot be empty.")
        if not legs:
            raise ValueError("A trade plan must contain at least one leg.")
        created_at = _as_utc(now or datetime.now(timezone.utc))
        plan_expiry = _as_utc(expires_at) if expires_at else _default_expiry(created_at)
        if plan_expiry <= created_at:
            raise ValueError("expires_at must be after plan creation.")
        confirmation_code = self._generate_confirmation_code()
        plan = TradePlan(
            plan_id=plan_id,
            confirmation_code=confirmation_code,
            trace_id=trace_id,
            created_at=created_at,
            expires_at=plan_expiry,
            status="PENDING",
            legs=tuple(legs),
        )
        self._repository.create_plan(plan)
        return plan

    def create_and_send_plan(
        self,
        plan_id: str,
        legs: Sequence[TradePlanLeg],
        trace_id: str = "",
        now: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> TradePlan:
        """Create a plan and send its HTML confirmation email."""
        if self._mail_sender is None:
            raise RuntimeError("A mail sender is required to send trade plans.")
        plan = self.create_plan(plan_id, legs, trace_id, now, expires_at)
        subject, body = render_trade_plan_email(plan)
        self._mail_sender.send_html(subject, body)
        return plan

    def handle_trade_plan_ready(self, event_data: Mapping[str, object]) -> TradePlan:
        """Create and send a plan from a ``trade.plan_ready`` event payload."""
        plan_id = _required_string(event_data, "plan_id")
        raw_legs = event_data.get("legs")
        if not isinstance(raw_legs, list):
            raise ValueError("trade.plan_ready requires a legs list.")
        legs = tuple(
            TradePlanLeg.from_dict(leg)
            for leg in raw_legs
            if isinstance(leg, Mapping)
        )
        if len(legs) != len(raw_legs):
            raise ValueError("trade.plan_ready legs must be mappings.")
        trace_id = event_data.get("trace_id", "")
        if not isinstance(trace_id, str):
            raise ValueError("trade.plan_ready trace_id must be a string.")
        return self.create_and_send_plan(plan_id, legs, trace_id)

    def process_email(
        self,
        inbound_email: InboundEmail,
        now: datetime | None = None,
    ) -> ConfirmationOutcome:
        """Validate, parse, persist, and publish a single reply email."""
        processed_at = _as_utc(now or datetime.now(timezone.utc))
        confirmation_code = _extract_confirmation_code(
            inbound_email.subject,
            inbound_email.body,
        )
        if confirmation_code is None:
            return self._reject_email(
                inbound_email,
                "Confirmation code is missing.",
                None,
                processed_at,
            )
        sender_address = parseaddr(inbound_email.sender)[1].lower()
        if sender_address not in self._allowed_senders:
            return self._reject_email(
                inbound_email,
                "Sender is not on the confirmation whitelist.",
                confirmation_code,
                processed_at,
            )
        if not _is_reply(inbound_email):
            return self._reject_email(
                inbound_email,
                "Inbound message is not a reply to a trade plan.",
                confirmation_code,
                processed_at,
            )
        plan = self._repository.get_plan_by_code(confirmation_code)
        if plan is None:
            return self._reject_email(
                inbound_email,
                "Confirmation code does not match a trade plan.",
                confirmation_code,
                processed_at,
            )
        if plan.status != "PENDING":
            return ConfirmationOutcome(False, "Confirmation code was already processed.")
        if plan.expires_at <= processed_at:
            self._repository.expire_due_plans(processed_at)
            self._publish_plan_event("order.expired", plan)
            return ConfirmationOutcome(False, "Confirmation code has expired.")

        try:
            records = parse_confirmation_reply(inbound_email.body, plan)
        except ConfirmationError as exc:
            return self._reject_email(
                inbound_email,
                str(exc),
                confirmation_code,
                processed_at,
                plan,
            )
        if not self._repository.apply_confirmation(
            plan,
            inbound_email.message_id,
            records,
            processed_at,
        ):
            return ConfirmationOutcome(False, "Confirmation code was already processed.")
        logger.info(
            "Accepted confirmation for plan %s from message %s.",
            plan.plan_id,
            inbound_email.message_id,
        )
        for record in records:
            event_name = (
                "order.cancelled"
                if record.status == "CANCELLED"
                else "order.filled"
            )
            self._event_publisher(
                event_name,
                {
                    "plan_id": plan.plan_id,
                    "trace_id": plan.trace_id,
                    "symbol": record.symbol,
                    "status": record.status,
                    "quantity": record.quantity,
                    "price": record.price,
                    "price_needs_review": record.price_needs_review,
                },
            )
            if record.price_needs_review:
                self._event_publisher(
                    "order.price_review_required",
                    {
                        "plan_id": plan.plan_id,
                        "trace_id": plan.trace_id,
                        "symbol": record.symbol,
                        "message_id": inbound_email.message_id,
                    },
                )
        return ConfirmationOutcome(True, "Confirmation accepted.", records)

    def expire_due_plans(self, now: datetime | None = None) -> int:
        """Expire overdue plans and publish an event for each one."""
        expired_plans = self._repository.expire_due_plans(
            _as_utc(now or datetime.now(timezone.utc))
        )
        for plan in expired_plans:
            self._publish_plan_event("order.expired", plan)
        return len(expired_plans)

    def send_expiry_reminders(
        self,
        now: datetime | None = None,
        reminder_window: timedelta = timedelta(hours=2),
    ) -> int:
        """Send reminders for plans close to expiration."""
        if self._mail_sender is None:
            raise RuntimeError("A mail sender is required to send reminders.")
        reminder_time = _as_utc(now or datetime.now(timezone.utc))
        plans = self._repository.plans_needing_reminder(reminder_time, reminder_window)
        for plan in plans:
            subject = f"[交易计划提醒] 确认码: {plan.confirmation_code}"
            body = (
                "<p>您的交易计划将在 "
                f"{html.escape(plan.expires_at.isoformat())} 到期。</p>"
                f"<p>确认码: <strong>{html.escape(plan.confirmation_code)}</strong></p>"
            )
            self._mail_sender.send_html(subject, body)
        return len(plans)

    def manual_confirm(
        self,
        plan_id: str,
        symbol: str,
        price: float,
        quantity: float,
        now: datetime | None = None,
    ) -> ConfirmationRecord:
        """Record an operator-entered filled execution for a plan leg."""
        plan = self._repository.get_plan_by_id(plan_id)
        if plan is None:
            raise ValueError(f"Unknown trade plan: {plan_id}")
        normalized_symbol = _normalize_symbol(symbol, plan)
        leg = _find_leg(normalized_symbol, plan)
        if quantity <= 0 or quantity > leg.quantity or price <= 0:
            raise ValueError("Manual quantity and price must be within the plan.")
        record = ConfirmationRecord(
            normalized_symbol,
            "FILLED" if quantity == leg.quantity else "PARTIAL",
            quantity,
            price,
        )
        recorded_at = _as_utc(now or datetime.now(timezone.utc))
        self._repository.add_manual_confirmation(plan, record, recorded_at)
        self._event_publisher(
            "order.filled",
            {
                "plan_id": plan.plan_id,
                "trace_id": plan.trace_id,
                "symbol": record.symbol,
                "status": record.status,
                "quantity": record.quantity,
                "price": record.price,
                "manual": True,
            },
        )
        return record

    def _generate_confirmation_code(self) -> str:
        """Generate a collision-free six-character confirmation code."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not self._repository.code_exists(code):
                return code
        raise RuntimeError("Unable to allocate a unique confirmation code.")

    def _reject_email(
        self,
        inbound_email: InboundEmail,
        reason: str,
        confirmation_code: str | None,
        processed_at: datetime,
        plan: TradePlan | None = None,
    ) -> ConfirmationOutcome:
        """Store a rejected email and notify the event bus."""
        was_recorded = self._repository.record_parse_failure(
            inbound_email,
            reason,
            confirmation_code,
            processed_at,
        )
        if not was_recorded:
            return ConfirmationOutcome(False, "Confirmation email was already processed.")
        logger.warning(
            "Rejected confirmation email %s: %s",
            inbound_email.message_id,
            reason,
        )
        payload: dict[str, object] = {
            "message_id": inbound_email.message_id,
            "reason": reason,
            "confirmation_code": confirmation_code,
        }
        if plan is not None:
            payload["plan_id"] = plan.plan_id
            payload["trace_id"] = plan.trace_id
        self._event_publisher("order.parse_failed", payload)
        return ConfirmationOutcome(False, reason)

    def _publish_plan_event(self, event_name: str, plan: TradePlan) -> None:
        """Publish a plan-level event with original trace context."""
        self._event_publisher(
            event_name,
            {
                "plan_id": plan.plan_id,
                "trace_id": plan.trace_id,
                "confirmation_code": plan.confirmation_code,
            },
        )


class ImapConfirmationPoller:
    """Fetch unread confirmation replies through IMAP SSL."""

    def __init__(
        self,
        settings: ImapSettings,
        service: EmailConfirmationService,
        imap_factory: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
        alert_publisher: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> None:
        self._settings = settings
        self._service = service
        self._imap_factory = imap_factory
        self._alert_publisher = alert_publisher

    def poll_once(self) -> int:
        """Process unread reply emails once and mark inspected messages seen."""
        processed_count = 0
        with self._imap_factory(self._settings.host, self._settings.port) as client:
            client.login(self._settings.username, self._settings.password)
            status, _ = client.select(self._settings.mailbox)
            if status != "OK":
                raise ConnectionError(f"Could not select IMAP mailbox {self._settings.mailbox}.")
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                raise ConnectionError("Could not search unread IMAP messages.")
            message_numbers = data[0].split() if data else []
            for message_number in message_numbers:
                status, message_data = client.fetch(message_number, "(RFC822)")
                if status != "OK" or not message_data:
                    raise ConnectionError(f"Could not fetch IMAP message {message_number!r}.")
                raw_message = _extract_raw_message(message_data)
                inbound_email = _to_inbound_email(raw_message)
                if _is_reply(inbound_email) and "[交易计划]" in inbound_email.subject:
                    self._service.process_email(inbound_email)
                    processed_count += 1
                client.store(message_number, "+FLAGS", "\\Seen")
        return processed_count

    def run_forever(
        self,
        stop_event: Event,
        poll_interval_seconds: int = 300,
    ) -> None:
        """Poll IMAP until stopped, reconnecting with capped exponential backoff."""
        disconnected_since: datetime | None = None
        delay = 1
        while not stop_event.is_set():
            try:
                self.poll_once()
                disconnected_since = None
                delay = 1
                stop_event.wait(poll_interval_seconds)
            except (ConnectionError, imaplib.IMAP4.error, OSError) as exc:
                now = datetime.now(timezone.utc)
                disconnected_since = disconnected_since or now
                logger.warning("IMAP confirmation polling failed: %s", exc)
                if (
                    self._alert_publisher is not None
                    and now - disconnected_since >= timedelta(minutes=30)
                ):
                    self._alert_publisher(
                        "system.alert",
                        {
                            "component": "email_confirmation_imap",
                            "reason": "IMAP unavailable for at least 30 minutes.",
                        },
                    )
                stop_event.wait(delay)
                delay = min(delay * 2, 300)


def render_trade_plan_email(plan: TradePlan) -> tuple[str, str]:
    """Render the required HTML plan email subject and reply template."""
    date_text = plan.created_at.date().isoformat()
    subject = (
        f"[交易计划] {date_text} 共{len(plan.legs)}笔 | "
        f"确认码: {plan.confirmation_code}"
    )
    leg_blocks = []
    reply_lines = [f"确认码: {plan.confirmation_code}"]
    for index, leg in enumerate(plan.legs, start=1):
        action = "买入" if leg.side == "BUY" else "卖出"
        leg_blocks.append(
            "<p>"
            f"<strong>【计划{index}】{action} "
            f"{html.escape(leg.name)}({html.escape(leg.symbol)})</strong><br>"
            f"建议价格: {leg.price:.2f}<br>"
            f"建议数量: {leg.quantity:g}股<br>"
            f"方向: 限价{action}"
            "</p>"
        )
        reply_lines.append(
            f"{leg.symbol}: 成交 {leg.quantity:g}股 @ {leg.price:.2f}"
        )
    reply_template = "<br>".join(html.escape(line) for line in reply_lines)
    body = (
        "<html><body>"
        "<p>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br>"
        "量化交易系统 - 交易计划书<br>"
        f"日期: {html.escape(date_text)}<br>"
        f"确认码: <strong>{html.escape(plan.confirmation_code)}</strong><br>"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</p>"
        f"{''.join(leg_blocks)}"
        "<p>操作完成后，请直接回复此邮件，格式如下：</p>"
        f"<pre>{reply_template}</pre>"
        "</body></html>"
    )
    return subject, body


def parse_confirmation_reply(
    body: str,
    plan: TradePlan,
) -> tuple[ConfirmationRecord, ...]:
    """Parse strict reply rows first, then approved fuzzy reply patterns."""
    records: list[ConfirmationRecord] = []
    for line in body.splitlines():
        text = line.strip()
        fill_match = _FILL_PATTERN.fullmatch(text)
        if fill_match is not None:
            symbol = _normalize_symbol(fill_match.group("symbol"), plan)
            quantity = float(fill_match.group("quantity"))
            price = float(fill_match.group("price"))
            leg = _find_leg(symbol, plan)
            if quantity > leg.quantity:
                raise ConfirmationError(f"Filled quantity exceeds plan for {symbol}.")
            status: ConfirmationStatus = (
                "FILLED" if quantity == leg.quantity else "PARTIAL"
            )
            records.append(ConfirmationRecord(symbol, status, quantity, price))
            continue
        cancel_match = _CANCEL_PATTERN.fullmatch(text)
        if cancel_match is not None:
            symbol = _normalize_symbol(cancel_match.group("symbol"), plan)
            records.append(ConfirmationRecord(symbol, "CANCELLED", None, None))

    if records:
        _ensure_unique_symbols(records)
        return tuple(records)

    normalized_body = body.strip()
    if "都买了" in normalized_body or "都卖了" in normalized_body:
        return tuple(
            ConfirmationRecord(
                leg.symbol,
                "FILLED",
                leg.quantity,
                leg.price,
            )
            for leg in plan.legs
        )
    if "没买" in normalized_body or "未执行" in normalized_body:
        return tuple(
            ConfirmationRecord(leg.symbol, "CANCELLED", None, None)
            for leg in plan.legs
        )

    for leg in plan.legs:
        if not _matches_leg_name(leg.name, normalized_body):
            continue
        match = _FUZZY_FILL_PATTERN.search(normalized_body)
        if match is None:
            continue
        quantity_text = match.group("quantity")
        price_text = match.group("price")
        quantity = float(quantity_text) if quantity_text else leg.quantity
        if quantity <= 0 or quantity > leg.quantity:
            raise ConfirmationError(f"Filled quantity exceeds plan for {leg.symbol}.")
        price = float(price_text) if price_text else leg.price
        return (
            ConfirmationRecord(
                leg.symbol,
                "FILLED" if quantity == leg.quantity else "PARTIAL",
                quantity,
                price,
                price_needs_review=price_text is None,
            ),
        )
    raise ConfirmationError("Reply body does not contain recognizable trade results.")


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the ``quantcli confirm`` manual confirmation command."""
    parser = argparse.ArgumentParser(prog="quantcli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    confirm_parser = subparsers.add_parser("confirm")
    confirm_parser.add_argument("--database", required=True)
    confirm_parser.add_argument("--plan-id", required=True)
    confirm_parser.add_argument("--code", required=True)
    confirm_parser.add_argument("--price", required=True, type=float)
    confirm_parser.add_argument("--qty", required=True, type=float)
    args = parser.parse_args(arguments)
    if args.command != "confirm":
        return 1
    repository = EmailConfirmationRepository(args.database)
    service = EmailConfirmationService(
        repository,
        allowed_senders={"manual@localhost"},
        event_publisher=lambda _event_name, _payload: None,
    )
    record = service.manual_confirm(
        args.plan_id,
        args.code,
        args.price,
        args.qty,
    )
    print(
        f"Recorded {record.status} confirmation for {record.symbol}: "
        f"{record.quantity:g} @ {record.price:.2f}"
    )
    return 0


def _required_string(value: Mapping[str, object], key: str) -> str:
    """Read a non-empty string from a mapping."""
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return result


def _required_positive_number(value: Mapping[str, object], key: str) -> float:
    """Read a positive numeric value from a mapping."""
    result = value.get(key)
    if not isinstance(result, int | float) or result <= 0:
        raise ValueError(f"{key} must be a positive number.")
    return float(result)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a datetime in a consistent UTC ISO-8601 form."""
    return _as_utc(value).isoformat()


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC and require explicit intent for naive values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_expiry(created_at: datetime) -> datetime:
    """Set expiry to the earlier of 16 hours or next day 10:00 China time."""
    china_time = created_at.astimezone(ZoneInfo("Asia/Shanghai"))
    next_day_ten = (china_time + timedelta(days=1)).replace(
        hour=10,
        minute=0,
        second=0,
        microsecond=0,
    )
    return min(
        created_at + timedelta(hours=16),
        next_day_ten.astimezone(timezone.utc),
    )


def _row_to_plan(row: sqlite3.Row) -> TradePlan:
    """Construct a trade plan object from one database row."""
    raw_legs = json.loads(row["legs_json"])
    if not isinstance(raw_legs, list):
        raise ValueError("Stored trade plan legs are invalid.")
    return TradePlan(
        plan_id=row["plan_id"],
        confirmation_code=row["confirmation_code"],
        trace_id=row["trace_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        status=row["status"],
        legs=tuple(
            TradePlanLeg.from_dict(leg)
            for leg in raw_legs
            if isinstance(leg, Mapping)
        ),
    )


def _extract_confirmation_code(subject: str, body: str) -> str | None:
    """Extract a six-character confirmation code from body or subject."""
    for value in (body, subject):
        match = _CONFIRMATION_CODE_PATTERN.search(value)
        if match is not None:
            return match.group(1).upper()
    return None


def _is_reply(inbound_email: InboundEmail) -> bool:
    """Return whether the inbound email is structurally a reply."""
    return (
        inbound_email.subject.strip().lower().startswith("re:")
        or bool(inbound_email.in_reply_to)
    )


def _normalize_symbol(value: str, plan: TradePlan) -> str:
    """Resolve a reply symbol against exactly one plan leg."""
    candidate = value.upper()
    if re.fullmatch(r"\d{6}", candidate):
        matches = [leg.symbol for leg in plan.legs if leg.symbol.startswith(candidate)]
        if len(matches) == 1:
            return matches[0]
    if any(leg.symbol == candidate for leg in plan.legs):
        return candidate
    raise ConfirmationError(f"Symbol is not in trade plan: {value}")


def _find_leg(symbol: str, plan: TradePlan) -> TradePlanLeg:
    """Return the planned leg for a normalized symbol."""
    for leg in plan.legs:
        if leg.symbol == symbol:
            return leg
    raise ConfirmationError(f"Symbol is not in trade plan: {symbol}")


def _matches_leg_name(name: str, body: str) -> bool:
    """Match a plan name by full name or an unambiguous two-character suffix."""
    if name in body:
        return True
    short_name = name[-2:]
    return len(short_name) == 2 and short_name in body


def _ensure_unique_symbols(records: Sequence[ConfirmationRecord]) -> None:
    """Reject replies that provide multiple conflicting results for one symbol."""
    symbols = [record.symbol for record in records]
    if len(symbols) != len(set(symbols)):
        raise ConfirmationError("Reply contains duplicate symbol confirmations.")


def _extract_raw_message(message_data: object) -> bytes:
    """Extract RFC822 bytes from an IMAP fetch response."""
    if not isinstance(message_data, list):
        raise ConnectionError("Unexpected IMAP fetch response.")
    for item in message_data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    raise ConnectionError("IMAP fetch response does not contain an email message.")


def _to_inbound_email(raw_message: bytes) -> InboundEmail:
    """Decode an RFC822 message into the confirmation processing model."""
    message = email.message_from_bytes(raw_message)
    return InboundEmail(
        message_id=message.get("Message-ID", "").strip() or _message_fallback_id(raw_message),
        sender=message.get("From", "").strip(),
        subject=_decode_header_value(message.get("Subject", "")),
        body=_extract_email_body(message),
        in_reply_to=message.get("In-Reply-To"),
    )


def _decode_header_value(value: str) -> str:
    """Decode an RFC2047 email header into text."""
    parts = []
    for content, encoding in decode_header(value):
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(content)
    return "".join(parts)


def _extract_email_body(message: Message) -> str:
    """Extract the preferred plain-text body from a multipart email."""
    if message.is_multipart():
        plain_parts = [
            _decode_message_part(part)
            for part in message.walk()
            if part.get_content_type() == "text/plain"
            and not part.get_filename()
        ]
        if plain_parts:
            return "\n".join(plain_parts)
    return _decode_message_part(message)


def _decode_message_part(message: Message) -> str:
    """Decode one email message part using its declared charset."""
    payload = message.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    return payload.decode(message.get_content_charset() or "utf-8", errors="replace")


def _message_fallback_id(raw_message: bytes) -> str:
    """Build a stable identifier for malformed emails missing Message-ID."""
    return f"missing-message-id:{sha256(raw_message).hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
