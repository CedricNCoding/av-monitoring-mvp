#!/usr/bin/env python3
"""
Script de test pour vérifier que les events sont bien enregistrés.
Usage: python test_events.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Device, DeviceEvent

def test_event_creation():
    db = SessionLocal()
    try:
        # Récupérer un device existant
        device = db.query(Device).first()
        if not device:
            print("❌ Aucun device trouvé dans la base de données")
            return

        print(f"✅ Device trouvé: {device.id} - {device.ip} - {device.name}")

        # Créer un event de test
        now = datetime.now(timezone.utc)
        test_event = DeviceEvent(
            device_id=device.id,
            site_id=device.site_id,
            ip=device.ip,
            name=device.name,
            building=device.building,
            room=device.room,
            device_type=device.device_type,
            driver=device.driver,
            status="online",
            verdict="ok",
            detail="Test event",
            metrics_json={},
            created_at=now,
        )

        db.add(test_event)
        db.commit()
        db.refresh(test_event)

        print(f"✅ Event de test créé avec succès: ID={test_event.id}")

        # Compter les events
        count = db.query(DeviceEvent).count()
        print(f"✅ Total d'events dans la table: {count}")

        # Voir les 5 derniers events
        print("\n📊 Les 5 derniers events:")
        events = db.query(DeviceEvent).order_by(DeviceEvent.created_at.desc()).limit(5).all()
        for e in events:
            print(f"  - ID={e.id}, Device={e.device_id}, IP={e.ip}, Status={e.status}, Date={e.created_at}")

    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_event_creation()
