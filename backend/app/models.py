from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.sql import func
from .db import Base


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    token = Column(String, nullable=False, unique=True)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)

    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)

    # Inventaire / UX
    name = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    driver = Column(String, nullable=False, default="ping")

    # État runtime
    last_seen = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="unknown")
    detail = Column(String, nullable=True)

    # 🔥 NOUVEAU : métriques techniques (SNMP, erreurs, etc.)
    metrics = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("site_id", "ip", name="uq_site_ip"),
    )