from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .db import Base


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    token = Column(String, nullable=False, unique=True)

    # Contact (dashboard / escalade)
    contact_first_name = Column(String, nullable=True)
    contact_last_name = Column(String, nullable=True)
    contact_title = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)

    name = Column(String, nullable=False)
    device_type = Column(String, nullable=False, default="unknown")
    ip = Column(String, nullable=False)

    driver = Column(String, nullable=False, default="ping")
    building = Column(String, nullable=True)
    room = Column(String, nullable=True)

    last_seen = Column(DateTime(timezone=True), nullable=True)
    last_ok_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="unknown")
    detail = Column(String, nullable=True)
    verdict = Column(String, nullable=True)

    # Metrics SNMP / autres drivers
    metrics = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("site_id", "ip", name="uq_site_ip"),)


class DeviceEvent(Base):
    """
    Historique d'état (purge via rétention).
    """
    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)

    ip = Column(String, nullable=False)
    name = Column(String, nullable=True)
    building = Column(String, nullable=True)
    room = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    driver = Column(String, nullable=True)

    status = Column(String, nullable=False)
    verdict = Column(String, nullable=True)
    detail = Column(String, nullable=True)

    metrics_json = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_device_events_device_created", "device_id", "created_at"),
        Index("ix_device_events_created", "created_at"),
    )


class DeviceAlert(Base):
    """
    Alertes ouvertes/fermées avec gestion de l'acknowledgment.
    """
    __tablename__ = "device_alerts"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)

    severity = Column(String, nullable=False, default="warning")  # critical, warning, info
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)

    status = Column(String, nullable=False)  # offline, unknown, etc.
    verdict = Column(String, nullable=True)  # fault, doubt, etc.
    detail = Column(String, nullable=True)

    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_device_alerts_device_closed", "device_id", "closed_at"),
    )