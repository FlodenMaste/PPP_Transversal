import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from fastmcp import FastMCP

from tools.network import ping_host as network_ping
from tools.network import traceroute_host as network_traceroute

from tools.snmp import (
    snmp_get as snmp_get_function,
    snmp_walk as snmp_walk_function,
    get_interface_stats as interface_stats_function,
)

from tools.routing import (
    get_bgp_peers as bgp_function,
    get_ospf_neighbors as ospf_function,
)

from tools.netconf import netconf_get as netconf_function


# --------------------------------------------------
# CHEMINS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = BASE_DIR / "resources"

# Identifiants du laboratoire (SNMPv3, SSH) lus depuis .env
load_dotenv(BASE_DIR / ".env")

TOPOLOGY_FILE = RESOURCES_DIR / "topology.json"
INVENTORY_FILE = RESOURCES_DIR / "inventory.json"
IPAM_FILE = RESOURCES_DIR / "ipam.json"
RUNBOOK_FILE = RESOURCES_DIR / "runbooks" / "restart_switch.md"


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    filename=BASE_DIR / "server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("noc-mcp")


# --------------------------------------------------
# SERVEUR MCP
# --------------------------------------------------

mcp = FastMCP(
    "NOC MCP Server"
)


# --------------------------------------------------
# FONCTIONS UTILITAIRES
# --------------------------------------------------

def read_json_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------
# TOOL 1 — PING
# --------------------------------------------------

@mcp.tool
def ping_host(ip: str) -> dict:
    """Teste la connectivité IP vers un équipement."""

    logger.info("Ping demandé vers %s", ip)

    return network_ping(ip)


# --------------------------------------------------
# TOOL 2 — TRACEROUTE
# --------------------------------------------------

@mcp.tool
def traceroute_host(ip: str) -> dict:
    """Affiche le chemin réseau vers une adresse IP."""

    logger.info("Traceroute demandé vers %s", ip)

    return network_traceroute(ip)


# --------------------------------------------------
# TOOL 3 — SNMP GET
# --------------------------------------------------

@mcp.tool
def snmp_get(
    ip: str,
    oid: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:
    """Effectue une requête SNMP GET (SNMPv3 authPriv si username renseigné,
    sinon SNMPv2c). Sans argument, les identifiants SNMPv3 sont lus dans le .env."""

    logger.info(
        "SNMP GET demandé vers %s OID=%s",
        ip,
        oid,
    )

    return snmp_get_function(
        ip,
        oid,
        community,
        username,
        auth_key,
        priv_key,
        port,
    )


# --------------------------------------------------
# TOOL 4 — SNMP WALK
# --------------------------------------------------

@mcp.tool
def snmp_walk(
    ip: str,
    oid: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:
    """Parcourt une branche SNMP (SNMPv3 authPriv si username renseigné,
    sinon SNMPv2c). Sans argument, les identifiants SNMPv3 sont lus dans le .env."""

    logger.info(
        "SNMP WALK demandé vers %s OID=%s",
        ip,
        oid,
    )

    return snmp_walk_function(
        ip,
        oid,
        community,
        username,
        auth_key,
        priv_key,
        port,
    )


# --------------------------------------------------
# TOOL 5 — STATISTIQUES INTERFACES
# --------------------------------------------------

@mcp.tool
def get_interface_stats(
    ip: str,
    community: str = "public",
    username: str = "",
    auth_key: str = "",
    priv_key: str = "",
    port: int = 161,
) -> dict:
    """Récupère les statistiques SNMP sur les interfaces."""

    logger.info(
        "Interface stats demandées pour %s",
        ip,
    )

    return interface_stats_function(
        ip,
        community,
        username,
        auth_key,
        priv_key,
        port,
    )


# --------------------------------------------------
# TOOL 6 — BGP
# --------------------------------------------------

@mcp.tool
def get_bgp_peers(ip: str) -> dict:
    """Récupère les voisins BGP depuis FRRouting (SSH, lecture seule)."""

    logger.info("Consultation des voisins BGP sur %s", ip)

    return bgp_function(ip)


# --------------------------------------------------
# TOOL 7 — OSPF
# --------------------------------------------------

@mcp.tool
def get_ospf_neighbors(ip: str) -> dict:
    """Récupère les voisins OSPF depuis FRRouting (SSH, lecture seule)."""

    logger.info("Consultation des voisins OSPF sur %s", ip)

    return ospf_function(ip)


# --------------------------------------------------
# TOOL 8 — NETCONF
# --------------------------------------------------

@mcp.tool
def netconf_get(
    host: str,
    username: str,
    password: str,
    port: int = 830,
    filter_xml: str = "<filter type='subtree'></filter>",
) -> dict:
    """Effectue une opération NETCONF GET."""

    logger.info(
        "NETCONF GET demandé vers %s:%s",
        host,
        port,
    )

    return netconf_function(
        host,
        username,
        password,
        port,
        filter_xml,
    )


# --------------------------------------------------
# TOOL 9 — DEVICE STATUS
# --------------------------------------------------

@mcp.tool
def get_device_status(name: str) -> dict:
    """Retourne les informations d'un équipement de l'inventaire."""

    logger.info(
        "Recherche équipement : %s",
        name,
    )

    inventory = read_json_file(
        INVENTORY_FILE
    )

    for device in inventory.get("devices", []):

        if device.get("name", "").lower() == name.lower():

            return {
                "status": "found",
                "device": device,
            }

    return {
        "status": "not_found",
        "device": name,
    }


# --------------------------------------------------
# RESOURCE — TOPOLOGY
# --------------------------------------------------

@mcp.resource("noc://topology")
def get_topology() -> str:
    """Retourne la topologie du réseau."""

    logger.info("Lecture resource topology")

    return TOPOLOGY_FILE.read_text(
        encoding="utf-8"
    )


# --------------------------------------------------
# RESOURCE — INVENTORY
# --------------------------------------------------

@mcp.resource("noc://inventory")
def get_inventory() -> str:
    """Retourne l'inventaire réseau."""

    logger.info("Lecture resource inventory")

    return INVENTORY_FILE.read_text(
        encoding="utf-8"
    )


# --------------------------------------------------
# RESOURCE — IPAM
# --------------------------------------------------

@mcp.resource("noc://ipam")
def get_ipam() -> str:
    """Retourne les informations IPAM."""

    logger.info("Lecture resource IPAM")

    return IPAM_FILE.read_text(
        encoding="utf-8"
    )


# --------------------------------------------------
# RESOURCE — RUNBOOK
# --------------------------------------------------

@mcp.resource("noc://runbook/restart-switch")
def get_restart_switch_runbook() -> str:
    """Retourne le runbook de diagnostic d'un switch."""

    logger.info(
        "Lecture du runbook switch"
    )

    return RUNBOOK_FILE.read_text(
        encoding="utf-8"
    )


# --------------------------------------------------
# PROMPT
# --------------------------------------------------

@mcp.prompt
def network_diagnosis(device: str) -> str:
    """Génère un prompt structuré de diagnostic réseau."""

    return f"""
Tu es un ingénieur NOC chargé de diagnostiquer
un problème concernant l'équipement {device}.

Utilise si nécessaire les informations disponibles :

- noc://topology
- noc://inventory
- noc://ipam
- noc://runbook/restart-switch

Utilise les outils appropriés :

- ping_host
- traceroute_host
- snmp_get
- snmp_walk
- get_interface_stats
- get_bgp_peers
- get_ospf_neighbors
- netconf_get
- get_device_status

Procédure :

1. Identifier le problème.
2. Vérifier l'équipement dans l'inventaire.
3. Identifier son adresse IP.
4. Vérifier la connectivité.
5. Examiner le chemin réseau.
6. Vérifier les informations SNMP si disponibles.
7. Vérifier BGP ou OSPF si nécessaire.
8. Vérifier NETCONF si disponible.
9. Comparer avec la topologie et l'IPAM.
10. Donner les causes probables.
11. Proposer une procédure de résolution.
12. Signaler les risques.

Ne redémarre et ne modifie aucun équipement réel
sans autorisation humaine.
"""


logger.info(
    "NOC MCP Server initialisé"
)


if __name__ == "__main__":
    mcp.run()

