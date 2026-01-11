from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, JSON
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

    name = Column(String, nullable=False)
    device_type = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    driver = Column(String, nullable=False, default="ping")

    # ✅ Inventaire : pour tri bâtiment/salle
    building = Column(String, nullable=False, default="")
    room = Column(String, nullable=False, default="")

    last_seen = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="unknown")
    detail = Column(String, nullable=True)

    # ✅ SNMP/diagnostic : message technique
    metrics = Column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("site_id", "ip", name="uq_site_ip"),)