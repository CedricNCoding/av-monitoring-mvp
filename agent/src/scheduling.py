# agent/src/scheduling.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class DevicePolicy:
    """
    Politique locale d'un équipement, utilisée pour réduire les fausses alertes.

    - expected_on: plages horaires où l'équipement est censé être ON (ex: horaires d'ouverture)
    - critical: si True => si l'équipement est OFF, c'est une panne (alerte) quel que soit l'horaire
    - allow_off: si True => OFF peut être acceptable hors expected_on (ex: économie d'énergie)
    """
    expected_on: List[Tuple[time, time]]  # (start, end) en heure locale
    critical: bool
    allow_off: bool


def _parse_hhmm(s: str) -> Optional[time]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception:
        return None


def _parse_expected_on(value: Any) -> List[Tuple[time, time]]:
    """
    Accepte:
    - [] ou None
    - liste de dicts: [{"start":"08:00","end":"18:00"}, ...]
    - liste de strings: ["08:00-18:00", ...]
    """
    out: List[Tuple[time, time]] = []

    if not value:
        return out

    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                st = _parse_hhmm(str(item.get("start") or ""))
                en = _parse_hhmm(str(item.get("end") or ""))
                if st and en:
                    out.append((st, en))
            elif isinstance(item, str):
                part = item.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    st = _parse_hhmm(a.strip())
                    en = _parse_hhmm(b.strip())
                    if st and en:
                        out.append((st, en))

    return out


def device_policy_from_config(device: Dict[str, Any]) -> DevicePolicy:
    """
    Lit la policy depuis le device config.
    Champs supportés (tolérants, sans casser les anciens JSON):
    - critical: bool
    - expected_on: [...] (voir _parse_expected_on)
    - allow_off: bool (si True, OFF est acceptable hors expected_on)
    """
    critical = bool(device.get("critical") or False)
    expected_on = _parse_expected_on(device.get("expected_on"))
    allow_off = bool(device.get("allow_off") or False)
    return DevicePolicy(expected_on=expected_on, critical=critical, allow_off=allow_off)


def is_within_expected_on(now_local: datetime, policy: DevicePolicy) -> bool:
    """
    True si now_local est dans AU MOINS une plage expected_on.
    Supporte les plages qui traversent minuit (ex: 22:00-02:00).
    """
    if not policy.expected_on:
        return False

    t = now_local.time()  # naive local time
    for start, end in policy.expected_on:
        if start <= end:
            if start <= t <= end:
                return True
        else:
            # traverse minuit
            if t >= start or t <= end:
                return True
    return False


def classify_observation(
    *,
    now_utc: datetime,
    tz_name: str,
    policy: DevicePolicy,
    observed_status: str,
    last_ok_utc: Optional[datetime],
    doubt_after_days: int,
) -> str:
    """
    Retourne un 'verdict' stable:
    - ok
    - expected_off   (OFF acceptable selon policy/plage)
    - fault          (OFF alors qu'attendu ON, ou critical OFF, ou always_on OFF)
    - doubt          (pas vu OK depuis N jours)
    - unknown
    """
    status = (observed_status or "unknown").strip().lower()

    # 1) DOUTE: basé sur dernier OK
    if last_ok_utc is not None and doubt_after_days > 0:
        if (now_utc - last_ok_utc) >= timedelta(days=doubt_after_days):
            return "doubt"

    # 2) ONLINE => OK
    if status == "online":
        return "ok"

    # 3) OFFLINE => expected_off ou fault
    if status == "offline":
        # Critical => fault immédiat
        if policy.critical:
            return "fault"

        # Si aucune plage n'est définie: comportement "always_on" par défaut.
        # OFF est considéré comme une panne, sauf si allow_off=True.
        if not policy.expected_on:
            return "expected_off" if policy.allow_off else "fault"

        # Sinon, on est en mode planning
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        now_local = now_utc.astimezone(tz)
        within = is_within_expected_on(now_local, policy)

        # OFF alors que ON attendu => fault
        if within:
            return "fault"

        # OFF hors plage: acceptable si allow_off=True, sinon c'est quand même fault
        return "expected_off" if policy.allow_off else "fault"

    return "unknown"


def compute_next_collect_interval_s(
    *,
    any_fault: bool,
    ok_interval_s: int,
    ko_interval_s: int,
    min_ok_s: int = 60,
    min_ko_s: int = 15,
) -> int:
    """
    Collecte adaptative:
    - si au moins 1 équipement en "fault" => ko_interval_s
    - sinon => ok_interval_s
    """
    try:
        ok = max(min_ok_s, int(ok_interval_s))
    except Exception:
        ok = 300

    try:
        ko = max(min_ko_s, int(ko_interval_s))
    except Exception:
        ko = 60

    return ko if any_fault else ok