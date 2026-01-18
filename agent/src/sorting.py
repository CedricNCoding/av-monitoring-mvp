# agent/src/sorting.py
"""
Utilitaires de tri pour la localisation des équipements.
"""
from __future__ import annotations

import re
from typing import Tuple


def normalize_floor_key(floor_str: str) -> Tuple[int, int, str]:
    """
    Normalise un nom d'étage pour un tri naturel.

    Règles de tri :
    - Sous-sols (SS1, S-1, -1) : négatifs, triés numériquement
    - RDC, RC, Rez, Ground : 0
    - Étages numériques (1, 2, 10) : triés numériquement
    - Autres textes : après les numériques, ordre alphabétique

    Exemples de tri :
    SS2 < SS1 < S-1 < RDC < 1 < 2 < 10 < Mezzanine < Terrasse

    Returns:
        Tuple (priority, numeric_value, text_value) pour le tri
        - priority: 0 pour numériques/RDC, 1 pour texte
        - numeric_value: valeur numérique de l'étage
        - text_value: texte normalisé pour tri alphabétique
    """
    if not floor_str:
        # Chaîne vide => avant tout (ou après, selon préférence)
        return (0, 999999, "")

    floor_normalized = floor_str.strip().lower()

    # RDC, RC, Rez, Ground => 0
    if floor_normalized in ("rdc", "rc", "rez", "ground", "g", "0"):
        return (0, 0, "")

    # Sous-sol : SS1, S-1, -1, SS-1, etc.
    # Pattern: SS(\d+), S-(\d+), -(\d+)
    basement_patterns = [
        r'^ss[-]?(\d+)$',  # SS1, SS-1
        r'^s[-](\d+)$',     # S-1
        r'^[-](\d+)$',      # -1
        r'^sous[-\s]?sol[-\s]?(\d+)?$',  # sous-sol, sous sol, sous-sol1
    ]

    for pattern in basement_patterns:
        match = re.match(pattern, floor_normalized)
        if match:
            num = match.group(1) if match.group(1) else "1"
            try:
                floor_num = -int(num)
                return (0, floor_num, "")
            except ValueError:
                pass

    # Étage numérique simple : 1, 2, 10, etc.
    if floor_normalized.isdigit():
        return (0, int(floor_normalized), "")

    # Pattern : "1er", "2ème", "3e", etc.
    ordinal_match = re.match(r'^(\d+)(?:er|ème|e)?$', floor_normalized)
    if ordinal_match:
        try:
            floor_num = int(ordinal_match.group(1))
            return (0, floor_num, "")
        except ValueError:
            pass

    # Tout le reste => tri alphabétique, après les numériques
    return (1, 0, floor_normalized)


def sort_devices_by_location(devices: list, reverse: bool = False) -> list:
    """
    Trie une liste de devices par localisation (building, floor, room, ip).

    Args:
        devices: Liste de dictionnaires avec clés 'building', 'floor', 'room', 'ip'
        reverse: Si True, tri inversé

    Returns:
        Liste triée de devices
    """
    def location_key(device: dict):
        building = (device.get("building") or "").strip().lower() or "zzz"
        floor = device.get("floor") or ""
        room = (device.get("room") or "").strip().lower() or "zzz"
        ip = (device.get("ip") or "").lower()

        floor_key = normalize_floor_key(floor)

        return (building, floor_key, room, ip)

    return sorted(devices, key=location_key, reverse=reverse)
