"""
Bornes des cibles réseau accessibles aux outils (cahier B.6).

Seuls les équipements décrits dans l'inventaire et le plan d'adressage
(IPAM) du laboratoire sont joignables : un appelant ne peut pas utiliser
le serveur comme relais vers n'importe quelle adresse. Une extension
explicite est possible via la variable ALLOWED_TARGETS (adresses séparées
par des virgules), utile pour un banc d'essai hors labo.
"""

from __future__ import annotations

import ipaddress
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


@lru_cache(maxsize=1)
def _inventory_ips() -> frozenset[str]:
    ips: set[str] = set()
    for name in ("inventory.json", "ipam.json"):
        path = RESOURCES_DIR / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for device in data.get("devices", []):
            if device.get("ip"):
                ips.add(device["ip"])
        for address in data.get("addresses", []):
            if address.get("ip"):
                ips.add(address["ip"])
        for node in data.get("nodes", []):
            if node.get("mgmt_ip"):
                ips.add(node["mgmt_ip"])
            if node.get("loopback"):
                ips.add(node["loopback"])
    return frozenset(ips)


@lru_cache(maxsize=1)
def allowed_targets() -> frozenset[str]:
    extra = {
        item.strip()
        for item in os.environ.get("ALLOWED_TARGETS", "").split(",")
        if item.strip()
    }
    return frozenset(set(_inventory_ips()) | extra)


def target_error(target: str) -> dict[str, Any] | None:
    """Renvoie un dict d'erreur si la cible est hors bornes, sinon None."""
    try:
        ipaddress.ip_address(target)
    except ValueError:
        return {
            "status": "error",
            "host": target,
            "error": f"Adresse IP invalide : {target!r}",
        }

    if target not in allowed_targets():
        return {
            "status": "error",
            "host": target,
            "error": (
                f"Cible {target} hors inventaire : le serveur n'accepte que les "
                f"equipements du laboratoire ({', '.join(sorted(allowed_targets()))}). "
                "Extension possible via ALLOWED_TARGETS."
            ),
        }
    return None
