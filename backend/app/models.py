from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
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
    status = Column(String, nullable=False, default="unknown")
    detail = Column(String, nullable=True)

    # Metrics SNMP / autres drivers
    metrics = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("site_id", "ip", name="uq_site_ip"),)


class DeviceEvent(Base):
    """
    Historique d'état (purge via rétention).
    """
    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)

    ip = Column(String, nullable=False)
    status = Column(String, nullable=False)
    detail = Column(String, nullable=True)

    metrics = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)