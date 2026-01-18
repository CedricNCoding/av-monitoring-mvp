# agent/src/scheduling.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


# ------------------------------------------------------------
# Data model (agent-side policy)
# ------------------------------------------------------------
@dataclass(frozen=True)
class DevicePolicy:
    """
    Politique locale d'un équipement, utilisée pour réduire les fausses alertes.

    - always_on: si True => OFF = fault quel que soit l'horaire (ex: automate, infra critique)
    - expected_on: plages horaires où l'équipement est censé être ON
    - timezone: timezone de la schedule (ex: Europe/Paris)
    - alert_after_s: délai minimum OFF avant de conclure à "fault" (anti-flap / boot long)
    """
    always_on: bool
    expected_on: List[Tuple[time, time, List[str]]]  # (start, end, days) en heure locale
    timezone: str
    alert_after_s: int


# ------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------
_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _parse_hhmm(s: str) -> Optional[time]:
    s = (s or "").strip()
    if not s or ":" not in s:
        return None
    try:
        hh, mm = s.split(":", 1)
        h = int(hh)
        m = int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(hour=h, minute=m)
    except Exception:
        return None
    return None


def _normalize_days(value: Any) -> List[str]:
    """
    Accepte:
      - "mon,tue,wed"
      - ["mon","tue"]
      - ["Monday","Tue"] (on normalise)
    """
    if not value:
        return []

    raw: List[str] = []
    if isinstance(value, str):
        raw = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, list):
        raw = [str(p).strip() for p in value if str(p).strip()]

    mapping = {
        "monday": "mon",
        "mon": "mon",
        "tuesday": "tue",
        "tue": "tue",
        "wednesday": "wed",
        "wed": "wed",
        "thursday": "thu",
        "thu": "thu",
        "friday": "fri",
        "fri": "fri",
        "saturday": "sat",
        "sat": "sat",
        "sunday": "sun",
        "sun": "sun",
    }

    out: List[str] = []
    for d in raw:
        key = d.lower()
        v = mapping.get(key)
        if v and v in _VALID_DAYS and v not in out:
            out.append(v)

    return out


def _as_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


# ------------------------------------------------------------
# Migration / extraction policy from device config
# ------------------------------------------------------------
def _parse_expected_on_from_expectations(device: Dict[str, Any]) -> Tuple[str, List[Tuple[time, time, List[str]]]]:
    """
    Attendu:
      device["expectations"]["schedule"] = {
        "timezone": "Europe/Paris",
        "rules": [{"days":[...],"start":"07:30","end":"19:00"}, ...]
      }

    Retour:
      (timezone, [(start,end,days), ...])
    """
    exp = device.get("expectations") or {}
    if not isinstance(exp, dict):
        exp = {}

    schedule = exp.get("schedule") or {}
    if not isinstance(schedule, dict):
        schedule = {}

    tz = (schedule.get("timezone") or device.get("timezone") or "").strip() or "UTC"

    rules = schedule.get("rules") or []
    if not isinstance(rules, list):
        rules = []

    out: List[Tuple[time, time, List[str]]] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        days = _normalize_days(r.get("days"))
        st = _parse_hhmm(str(r.get("start") or ""))
        en = _parse_hhmm(str(r.get("end") or ""))
        if not days or not st or not en:
            continue
        out.append((st, en, days))

    return tz, out


def _parse_expected_on_legacy(device: Dict[str, Any]) -> Tuple[str, List[Tuple[time, time, List[str]]]]:
    """
    Legacy support:
      - device["expected_on"] = [{"start":"08:00","end":"18:00"}, ...] ou ["08:00-18:00"]
      - aucun "days" => on suppose 7/7
      - timezone => device["timezone"] si présent sinon UTC
    """
    tz = (device.get("timezone") or "").strip() or "UTC"
    value = device.get("expected_on")
    out: List[Tuple[time, time, List[str]]] = []

    if not value:
        return tz, out

    days_all = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                st = _parse_hhmm(str(item.get("start") or ""))
                en = _parse_hhmm(str(item.get("end") or ""))
                if st and en:
                    out.append((st, en, days_all))
            elif isinstance(item, str):
                part = item.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    st = _parse_hhmm(a.strip())
                    en = _parse_hhmm(b.strip())
                    if st and en:
                        out.append((st, en, days_all))

    return tz, out


def device_policy_from_config(device: Dict[str, Any], default_tz: str = "UTC") -> DevicePolicy:
    """
    Lit la policy depuis le device config, sans casser les anciens JSON.

    Supporte:
      - Nouveau schéma:
        device.expectations.always_on
        device.expectations.alert_after_s
        device.expectations.schedule.timezone + rules
      - Legacy:
        device.critical (bool)
        device.expected_on (plages sans jours)
        device.timezone
    """
    if not isinstance(device, dict):
        device = {}

    # always_on: nouveau champ expectations.always_on OU legacy critical
    exp = device.get("expectations") or {}
    if not isinstance(exp, dict):
        exp = {}

    always_on = _truthy(exp.get("always_on")) or _truthy(device.get("critical"))

    alert_after_s = _as_int(exp.get("alert_after_s") if "alert_after_s" in exp else exp.get("alert_after"), 300)
    alert_after_s = max(15, alert_after_s)

    tz, expected = _parse_expected_on_from_expectations(device)
    if not expected:
        # fallback legacy expected_on
        tz, expected = _parse_expected_on_legacy(device)

    tz = (tz or "").strip() or (default_tz or "UTC")

    return DevicePolicy(always_on=always_on, expected_on=expected, timezone=tz, alert_after_s=alert_after_s)


# ------------------------------------------------------------
# Evaluation helpers
# ------------------------------------------------------------
def _weekday_key(dt_local: datetime) -> str:
    # Python: Monday=0 ... Sunday=6
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt_local.weekday()]


def is_within_expected_on(now_local: datetime, policy: DevicePolicy) -> bool:
    """
    True si now_local est dans AU MOINS une plage expected_on ET que le jour correspond.
    Supporte les plages qui traversent minuit (ex: 22:00-02:00).

    Règle "midnight-crossing":
      - Pour une plage 22:00-02:00 donnée pour "fri",
        on considère:
          - vendredi 22:00 -> vendredi 23:59
          - samedi 00:00 -> samedi 02:00
        Donc si now_local est après minuit, on accepte la plage si le "jour précédent" est inclus.
    """
    if not policy.expected_on:
        return False

    t = now_local.timetz().replace(tzinfo=None)
    day = _weekday_key(now_local)

    for start, end, days in policy.expected_on:
        days_norm = [d for d in days if d in _VALID_DAYS]
        if not days_norm:
            continue

        if start <= end:
            # plage classique: le jour doit correspondre
            if day in days_norm and start <= t <= end:
                return True
        else:
            # traverse minuit
            # 1) partie "avant minuit" (jour courant)
            if day in days_norm and t >= start:
                return True
            # 2) partie "après minuit" (jour +1), on regarde si le "jour précédent" était dans days
            prev_day = _VALID_DAYS_ORDERED[(_VALID_DAYS_ORDERED.index(day) - 1) % 7]
            if prev_day in days_norm and t <= end:
                return True

    return False


# Order helper for prev_day computation
_VALID_DAYS_ORDERED = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def classify_observation(
    *,
    now_utc: datetime,
    policy: DevicePolicy,
    observed_status: str,
    last_ok_utc: Optional[datetime],
    doubt_after_days: int,
    offline_for_s: Optional[int] = None,
) -> str:
    """
    Retourne un 'verdict' stable:
      - ok
      - expected_off   (OFF mais hors horaires attendus)
      - fault          (OFF alors qu'attendu ON, ou always_on)
      - doubt          (pas vu OK depuis N jours)
      - unknown

    Notes:
      - offline_for_s permet de respecter policy.alert_after_s (anti faux positifs)
    """
    status = (observed_status or "unknown").strip().lower()

    # 1) DOUTE: basé sur dernier OK (si on ne l'a pas vu depuis N jours)
    if last_ok_utc is not None and doubt_after_days > 0:
        delta = now_utc - last_ok_utc
        if delta >= timedelta(days=doubt_after_days):
            return "doubt"

    # 2) Evaluation ON/OFF
    if status == "online":
        return "ok"

    if status == "offline":
        # anti-faux-positifs: tant qu'on n'a pas dépassé alert_after_s, on n'alourdit pas
        if offline_for_s is not None and offline_for_s < policy.alert_after_s:
            return "unknown"

        if policy.always_on:
            return "fault"

        try:
            tz = ZoneInfo(policy.timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        now_local = now_utc.astimezone(tz)
        within = is_within_expected_on(now_local, policy)

        # OFF alors que ON attendu => fault
        if within:
            return "fault"

        # OFF hors plage attendue => expected_off
        return "expected_off"

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

    Garde-fous: min 60s pour ok, min 15s pour ko.
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