"""Utilitaires partagés par tous les collecteurs."""

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger("collector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def load_json_fixture(fixture_path: str | Path) -> Any:
    """Charge un fichier JSON de données simulées (fixtures/*.json)."""
    path = Path(fixture_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text_fixture(fixture_path: str | Path) -> str:
    """Charge un fichier texte de données simulées (ex: sortie CLI, syslog)."""
    path = Path(fixture_path)
    return path.read_text(encoding="utf-8")


def fixtures_dir(module_file: str) -> Path:
    """Retourne le dossier fixtures/ voisin du module appelant.

    Usage dans un collecteur : fixtures_dir(__file__) / "interface_stats.json"
    """
    return Path(module_file).resolve().parent / "fixtures"


# --- Résolution des identifiants d'équipement --------------------------------
# Les fixtures sont écrites avec la casse canonique du nom de noeud de lab
# ("R1", "R2") alors que l'appelant envoie tantôt l'IP de gestion
# ("172.20.20.11"), tantôt le nom tel quel ("r1"). Sans cette traduction,
# le mode simulé renvoie "Équipement inconnu dans les fixtures" (ou pire,
# un résultat vide silencieux) pour un équipement pourtant présent dans
# l'inventaire.

_INVENTORY_CACHE: dict[str, str] | None = None


def _inventory_path() -> Path | None:
    """Chemin vers mcp_server/resources/inventory.json, s'il existe.

    collector/common/utils.py -> parents[2] = racine du dépôt.
    """
    candidate = Path(__file__).resolve().parents[2] / "mcp_server" / "resources" / "inventory.json"
    return candidate if candidate.is_file() else None


def _device_aliases() -> dict[str, str]:
    """Table alias -> clé canonique de fixture, construite depuis l'inventaire.

    Mise en cache ; l'inventaire est un fichier statique du lab. Renvoie une
    table vide si l'inventaire est absent ou illisible (le collecteur reste
    utilisable, il se contente alors de ne pas résoudre l'alias).
    """
    global _INVENTORY_CACHE
    if _INVENTORY_CACHE is None:
        aliases: dict[str, str] = {}
        path = _inventory_path()
        if path is not None:
            try:
                devices = json.loads(path.read_text(encoding="utf-8")).get("devices", [])
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("inventaire illisible (%s) : alias d'équipements non résolus", exc)
                devices = []
            for device in devices:
                name = str(device.get("name") or "").strip()
                if not name:
                    continue
                key = name.upper()
                for alias in (name, name.lower(), name.upper(), str(device.get("ip") or "").strip()):
                    if alias:
                        aliases[alias] = key
        _INVENTORY_CACHE = aliases
    return _INVENTORY_CACHE


def resolve_device_key(device: str) -> str:
    """Traduit un identifiant d'équipement (IP, nom, casse variable) en la clé
    canonique utilisée par les fixtures ("R1", "R2", ...).

    Renvoie la valeur d'entrée si elle n'est pas dans l'inventaire : les
    collecteurs dont les fixtures sont indexées autrement (ex: ping, indexé
    sur la cible) doivent alors continuer à chercher avec l'identifiant brut.
    """
    if not isinstance(device, str) or not device:
        return device
    return _device_aliases().get(device, device)


def is_known_device(device: str) -> bool:
    """Vrai si l'identifiant correspond à un équipement de l'inventaire."""
    if not isinstance(device, str) or not device:
        return False
    return device in _device_aliases()


def unknown_device_message(device: str, label: str) -> str:
    """Message explicite quand les fixtures ne couvrent pas un équipement.

    Deux situations auparavant confondues en « Équipement inconnu » :
      - l'équipement est connu de l'inventaire mais n'a pas d'agent pour ce
        domaine (les hôtes client/serviciel n'ont ni snmpd, ni QoS, ni
        collecteur de flux dans le lab) ;
      - l'identifiant n'existe tout simplement pas.
    """
    if is_known_device(device):
        return (
            f"Équipement {device} connu de l'inventaire mais aucune donnée "
            f"{label} : pas d'agent correspondant sur cet hôte dans le lab"
        )
    return "Équipement inconnu dans les fixtures"


# --- Données non fiables (B.6 : injection indirecte par la télémétrie) -------
TRUNCATION_MARKER = " …[tronqué]"
_ALLOWED_WHITESPACE = {"\n", "\t"}


def sanitize_untrusted_text(text: str, max_len: int = 2000) -> str:
    """Nettoie un texte venant d'un équipement (description, syslog, bannière...).

    Ce nettoyage NE rend PAS le texte digne de confiance : il retire seulement
    ce qui sert à le dissimuler (caractères de contrôle, séquences ANSI,
    caractères Unicode invisibles ou de réorientation du texte) et borne sa
    taille. Le contenu reste une donnée non fiable, à signaler comme telle
    (champs "untrusted"/"untrusted_fields" du schéma).
    """
    cleaned = []
    for char in str(text):
        if char in _ALLOWED_WHITESPACE:
            cleaned.append(char)
        elif unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp"):
            continue  # contrôle, format invisible/bidi, séparateurs de ligne/paragraphe
        else:
            cleaned.append(char)
    result = "".join(cleaned)
    if len(result) > max_len:
        result = result[:max_len] + TRUNCATION_MARKER
    return result


def sanitize_untrusted(value: Any, max_len: int = 2000) -> Any:
    """Applique sanitize_untrusted_text récursivement à toute structure JSON."""
    if isinstance(value, str):
        return sanitize_untrusted_text(value, max_len)
    if isinstance(value, dict):
        return {
            sanitize_untrusted_text(str(k), 200): sanitize_untrusted(v, max_len) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_untrusted(v, max_len) for v in value]
    return value