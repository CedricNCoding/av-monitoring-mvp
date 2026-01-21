#!/usr/bin/env python3
"""
Script pour forcer l'enregistrement d'événements pour tous les devices.
Cela va créer un event pour chaque device, peu importe la logique des 60 minutes.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from app.database import SessionLocal
from app.models import Device, DeviceEvent

def force_record_all_events():
    db = SessionLocal()
    try:
        devices = db.query(Device).all()
        print(f"📊 Found {len(devices)} devices")

        if not devices:
            print("❌ No devices found!")
            return

        now = datetime.now(timezone.utc)
        created_count = 0

        for device in devices:
            try:
                # Créer un event pour ce device
                event = DeviceEvent(
                    device_id=device.id,
                    site_id=device.site_id,
                    ip=device.ip,
                    name=device.name,
                    building=device.building,
                    room=device.room,
                    device_type=device.device_type,
                    driver=device.driver,
                    status=device.status or "unknown",
                    verdict=device.verdict,
                    detail=device.detail,
                    metrics_json=device.metrics or {},
                    created_at=now,
                )
                db.add(event)
                db.flush()  # Pour obtenir l'ID

                print(f"✅ Event created for device {device.id} ({device.ip}): event_id={event.id}, status={device.status}")
                created_count += 1

            except Exception as e:
                print(f"❌ Failed to create event for device {device.id} ({device.ip}): {e}")
                import traceback
                traceback.print_exc()

        # Commit tous les events
        db.commit()
        print(f"\n✅ Successfully created {created_count} events!")

        # Vérifier le total
        from app.models import DeviceEvent as DE
        total_events = db.query(DE).count()
        print(f"📊 Total events in database: {total_events}")

        # Afficher les derniers events
        print("\n📋 Last 10 events:")
        last_events = db.query(DE).order_by(DE.created_at.desc()).limit(10).all()
        for e in last_events:
            print(f"  - ID={e.id}, Device={e.device_id}, IP={e.ip}, Status={e.status}, Date={e.created_at}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Forcing event recording for all devices...")
    force_record_all_events()
