from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    token = Column(String, nullable=False, unique=True)

    # Contact SAV (nouveau)
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
    device_type = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    driver = Column(String, nullable=False, default="ping_only")
    last_seen = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="unknown")
    detail = Column(String, nullable=True)

    # si vous avez déjà ajouté metrics au Device, gardez votre colonne existante ici.
    # metrics = Column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("site_id", "ip", name="uq_site_ip"),)

class DeviceEvent(Base):
    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)

    site_id = Column(Integer, nullable=False, index=True)
    ip = Column(String, nullable=False)

    status = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    metrics = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)